from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar

from app.market_api.models import (
    MarketAvailability,
    MarketAvailabilityDetail,
    MarketBreadthView,
    MarketFreshnessStatus,
    MarketFreshnessView,
    MarketIndexView,
    MarketLimitationView,
    MarketMeta,
    MarketProviderView,
    MarketQualityView,
    MarketSectionAvailability,
    MarketSectorView,
    MarketSessionStatus,
    MarketSessionView,
    MarketSnapshot,
    MarketUniverseView,
    MarketVolumeView,
)
from app.providers.market_data import (
    MarketDataProvider,
    MarketProviderMode,
    MarketQualityObservation,
    UnavailableMarketDataProvider,
)


T = TypeVar("T")
FRESH_MAX_AGE_SECONDS = 15 * 60
AGING_MAX_AGE_SECONDS = 24 * 60 * 60
PCT_QUANTUM = Decimal("0.0001")


class MarketIntelligenceService:
    """Failure-isolated projection from provider observations to the V1 API contract."""

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market Intelligence clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _quality(observation: MarketQualityObservation) -> MarketQualityView:
        coverage_pct = None
        if observation.expected_count:
            coverage_pct = (
                Decimal(observation.coverage_count)
                / Decimal(observation.expected_count)
                * Decimal("100")
            ).quantize(PCT_QUANTUM)
        return MarketQualityView(
            coverage_count=observation.coverage_count,
            expected_count=observation.expected_count,
            coverage_pct=coverage_pct,
            missing_count=observation.missing_count,
        )

    @staticmethod
    def _detail(status: MarketAvailability, reason: str | None = None) -> MarketAvailabilityDetail:
        return MarketAvailabilityDetail(status=status, reason=reason)

    @staticmethod
    def _freshness_status(source_timestamp: datetime | None, received_at: datetime) -> tuple[int | None, MarketFreshnessStatus]:
        if source_timestamp is None:
            return None, MarketFreshnessStatus.UNKNOWN
        source_utc = source_timestamp.astimezone(timezone.utc)
        age_seconds = max(int((received_at - source_utc).total_seconds()), 0)
        if age_seconds <= FRESH_MAX_AGE_SECONDS:
            status = MarketFreshnessStatus.FRESH
        elif age_seconds <= AGING_MAX_AGE_SECONDS:
            status = MarketFreshnessStatus.AGING
        else:
            status = MarketFreshnessStatus.STALE
        return age_seconds, status

    def get_snapshot(self) -> MarketSnapshot:
        generated_at = self._now()
        failed_sections: list[str] = []

        def read(name: str, operation: Callable[[], T], fallback: T) -> T:
            try:
                return operation()
            except Exception:
                failed_sections.append(name)
                return fallback

        raw_session = read("session", self._provider.get_market_status, None)
        freshness_observation = read("freshness", self._provider.get_freshness, None)
        source_timestamp = freshness_observation.source_timestamp if freshness_observation else None
        age_seconds, freshness_status = self._freshness_status(source_timestamp, generated_at)
        freshness = MarketFreshnessView(
            source_timestamp=source_timestamp,
            received_at=generated_at,
            age_seconds=age_seconds,
            freshness_status=freshness_status,
        )

        raw_indices = read("indices", self._provider.get_index_snapshot, ())
        indices = tuple(
            MarketIndexView(
                symbol=row.symbol,
                name=row.name,
                value=row.value,
                change=row.change,
                change_pct=row.change_pct,
                previous_close=row.previous_close,
                timestamp=row.timestamp,
                source=row.source,
                freshness=freshness_status,
            )
            for row in raw_indices
        )
        if not indices:
            indices_availability = self._detail(MarketAvailability.UNAVAILABLE, "NO_INDEX_OBSERVATIONS")
        elif {row.symbol for row in indices} >= {"NIFTY_500", "NIFTY_50"}:
            indices_availability = self._detail(MarketAvailability.AVAILABLE)
        else:
            indices_availability = self._detail(MarketAvailability.PARTIAL, "REFERENCE_INDEX_INCOMPLETE")

        raw_universe = read("universe", self._provider.get_universe_snapshot, None)
        universe = (
            MarketUniverseView(
                name=raw_universe.name,
                member_count=raw_universe.member_count,
                as_of_date=raw_universe.as_of_date,
                membership_kind=raw_universe.membership_kind,
                source=raw_universe.source,
            )
            if raw_universe
            else None
        )
        universe_availability = self._detail(
            MarketAvailability.AVAILABLE if universe else MarketAvailability.UNAVAILABLE,
            None if universe else "CURRENT_MEMBERSHIP_UNAVAILABLE",
        )

        raw_breadth = read("breadth", self._provider.get_breadth_snapshot, None)
        breadth = (
            MarketBreadthView(
                advancers=raw_breadth.advancers,
                decliners=raw_breadth.decliners,
                unchanged=raw_breadth.unchanged,
                positive_pct=raw_breadth.positive_pct,
                negative_pct=raw_breadth.negative_pct,
                above_vwap_pct=raw_breadth.above_vwap_pct,
                above_prior_close_pct=raw_breadth.above_prior_close_pct,
                quality=self._quality(raw_breadth.quality),
            )
            if raw_breadth
            else None
        )
        if breadth is None:
            breadth_availability = self._detail(MarketAvailability.UNAVAILABLE, "EOD_UNIVERSE_BARS_UNAVAILABLE")
        elif breadth.above_vwap_pct is None or breadth.quality.missing_count:
            breadth_availability = self._detail(MarketAvailability.PARTIAL, "UNSUPPORTED_OR_MISSING_BREADTH_FIELDS")
        else:
            breadth_availability = self._detail(MarketAvailability.AVAILABLE)

        raw_sectors = read("sectors", self._provider.get_sector_snapshot, ())
        sectors = tuple(
            MarketSectorView(
                sector=row.sector,
                return_pct=row.return_pct,
                advancers=row.advancers,
                decliners=row.decliners,
                unchanged=row.unchanged,
                breadth_pct=row.breadth_pct,
                relative_strength=row.relative_strength,
                volume_context=row.volume_context,
                quality=self._quality(row.quality),
            )
            for row in raw_sectors
        )
        if not sectors:
            sectors_availability = self._detail(MarketAvailability.UNAVAILABLE, "SECTOR_CONTEXT_UNAVAILABLE")
        elif any(
            row.return_pct is None
            or row.breadth_pct is None
            or row.volume_context is None
            or row.quality.missing_count
            for row in sectors
        ):
            sectors_availability = self._detail(MarketAvailability.PARTIAL, "SECTOR_FIELDS_OR_COVERAGE_PARTIAL")
        else:
            sectors_availability = self._detail(MarketAvailability.AVAILABLE)

        raw_volume = read("volume", self._provider.get_volume_snapshot, None)
        volume = (
            MarketVolumeView(
                aggregate_traded_value=raw_volume.aggregate_traded_value,
                traded_value_unit=raw_volume.traded_value_unit,
                median_relative_volume=raw_volume.median_relative_volume,
                above_20d_volume_count=raw_volume.above_20d_volume_count,
                above_20d_volume_pct=raw_volume.above_20d_volume_pct,
                quality=self._quality(raw_volume.quality),
            )
            if raw_volume
            else None
        )
        if volume is None:
            volume_availability = self._detail(MarketAvailability.UNAVAILABLE, "EOD_VOLUME_HISTORY_UNAVAILABLE")
        elif volume.median_relative_volume is None or volume.quality.missing_count:
            volume_availability = self._detail(MarketAvailability.PARTIAL, "VOLUME_BASELINE_OR_COVERAGE_PARTIAL")
        else:
            volume_availability = self._detail(MarketAvailability.AVAILABLE)

        session = (
            MarketSessionView(
                status=MarketSessionStatus(raw_session.status),
                market_date=raw_session.market_date,
                session_timestamp=raw_session.session_timestamp,
            )
            if raw_session and raw_session.status in MarketSessionStatus
            else None
        )
        if session is None:
            session_availability = self._detail(MarketAvailability.UNAVAILABLE, "SESSION_STATUS_UNAVAILABLE")
        elif session.status == MarketSessionStatus.UNKNOWN:
            session_availability = self._detail(MarketAvailability.PARTIAL, "SESSION_STATUS_UNKNOWN")
        else:
            session_availability = self._detail(MarketAvailability.AVAILABLE)

        availability = MarketSectionAvailability(
            indices=indices_availability,
            universe=universe_availability,
            breadth=breadth_availability,
            sectors=sectors_availability,
            volume=volume_availability,
            session=session_availability,
        )
        details = tuple(availability.model_dump().values())
        if all(row["status"] == MarketAvailability.UNAVAILABLE for row in details):
            overall_status = MarketAvailability.UNAVAILABLE
        elif any(row["status"] != MarketAvailability.AVAILABLE for row in details):
            overall_status = MarketAvailability.PARTIAL
        else:
            overall_status = MarketAvailability.AVAILABLE

        limitations: list[MarketLimitationView] = []

        def add_limitation(limitation_id: str, section: str, summary: str) -> None:
            limitations.append(
                MarketLimitationView(
                    limitation_id=limitation_id,
                    section=section,
                    summary=summary,
                )
            )

        if self._provider.mode == MarketProviderMode.SEEDED:
            add_limitation(
                "LIMIT-LIVE-SOURCE-NOT-CONFIGURED",
                "provider",
                "The snapshot is recorded NSE end-of-day data; no live market source is configured.",
            )
        if self._provider.mode == MarketProviderMode.UNAVAILABLE:
            reason = self._provider.unavailable_reason or (
                self._provider.reason
                if isinstance(self._provider, UnavailableMarketDataProvider)
                else "MARKET_PROVIDER_UNAVAILABLE"
            )
            add_limitation("LIMIT-PROVIDER-UNAVAILABLE", "provider", reason)
        if universe and universe.membership_kind == "CURRENT_EFFECTIVE_ONLY":
            add_limitation(
                "LIMIT-CURRENT-MEMBERSHIP-ONLY",
                "universe",
                "Current-session metrics use current effective NIFTY 500 membership; it is not projected backward for historical logic.",
            )
        if breadth and breadth.above_vwap_pct is None:
            add_limitation(
                "LIMIT-ABOVE-VWAP-UNAVAILABLE",
                "breadth",
                "Above-VWAP breadth is unavailable because the recorded source does not provide a trusted session VWAP.",
            )
        if breadth and breadth.quality.missing_count:
            add_limitation(
                "LIMIT-BREADTH-COVERAGE-PARTIAL",
                "breadth",
                f"Breadth covers {breadth.quality.coverage_count} of {breadth.quality.expected_count} current members.",
            )
        if sectors_availability.status == MarketAvailability.PARTIAL:
            add_limitation(
                "LIMIT-SECTOR-CONTEXT-PARTIAL",
                "sectors",
                "Official sector-index returns are available, while member breadth and volume depend on current-only mappings and recorded EOD coverage.",
            )
        if volume is None:
            add_limitation(
                "LIMIT-VOLUME-BASELINE-UNAVAILABLE",
                "volume",
                "Recorded member-level EOD volume history is unavailable; no volume metrics were fabricated.",
            )
        elif volume.quality.missing_count:
            add_limitation(
                "LIMIT-VOLUME-COVERAGE-PARTIAL",
                "volume",
                f"Twenty-session relative-volume coverage is {volume.quality.coverage_count} of {volume.quality.expected_count} current members.",
            )
        for section in failed_sections:
            add_limitation(
                f"LIMIT-{section.upper()}-PROVIDER-FAILURE",
                section,
                f"The {section} section failed safely and was omitted from this snapshot.",
            )

        unavailable_sections = tuple(
            name
            for name, detail in availability
            if detail.status == MarketAvailability.UNAVAILABLE
        )
        return MarketSnapshot(
            generated_at=generated_at,
            status=overall_status,
            provider=MarketProviderView(
                provider_name=self._provider.provider_name,
                mode=self._provider.mode,
                market=self._provider.market,
                capabilities=self._provider.capabilities,
            ),
            freshness=freshness,
            indices=indices,
            universe=universe,
            breadth=breadth,
            sectors=sectors,
            volume=volume,
            session=session,
            availability=availability,
            limitations=tuple(limitations),
            meta=MarketMeta(
                unavailable_sections=unavailable_sections,
                live_provider_implemented=self._provider.provider_name == "GROWW",
            ),
        )


__all__ = (
    "AGING_MAX_AGE_SECONDS",
    "FRESH_MAX_AGE_SECONDS",
    "MarketIntelligenceService",
)

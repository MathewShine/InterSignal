from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.market_api.workspace_models import (
    MarketCandleView,
    MarketCandlesResponse,
    MarketDepthLevelView,
    MarketIndexDetailResponse,
    MarketIndicesResponse,
    MarketIndexWorkspaceView,
    MarketInstrumentView,
    MarketProviderStatusResponse,
    MarketQuoteResponse,
    MarketQuoteView,
    MarketSearchResponse,
    MarketSectorDetailResponse,
    MarketSectorsResponse,
    MarketSectorWorkspaceView,
    OptionChainResponse,
)
from app.providers.groww.exceptions import GrowwProviderNotConfiguredError, GrowwRateLimitError
from app.providers.market_data import (
    InterSignalInstrument,
    MarketCandleObservation,
    MarketDataProvider,
    MarketProviderCapability,
    MarketQuoteObservation,
)


RANGE_DAYS = {"1D": 1, "5D": 5, "1M": 31, "3M": 93, "6M": 186, "1Y": 366}
RANGE_INTERVALS = {"1D": "5m", "5D": "15m", "1M": "30m", "3M": "1h", "6M": "4h", "1Y": "4h"}


class MarketWorkspaceService:
    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        feed_manager: object | None = None,
        session_manager: object | None = None,
    ) -> None:
        self.provider = provider
        self.feed_manager = feed_manager
        self.session_manager = session_manager

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _instrument(value: InterSignalInstrument) -> MarketInstrumentView:
        return MarketInstrumentView(
            instrument_id=value.instrument_id,
            symbol=value.symbol,
            display_name=value.display_name,
            exchange=value.exchange,
            segment=value.segment,
            instrument_type=value.instrument_type,
            underlying=value.underlying,
            expiry=value.expiry,
        )

    @staticmethod
    def _depth(rows) -> tuple[MarketDepthLevelView, ...]:
        return tuple(MarketDepthLevelView(price=row.price, quantity=row.quantity) for row in rows)

    def _quote(self, value: MarketQuoteObservation) -> MarketQuoteView:
        age = max((self._now() - value.timestamp.astimezone(timezone.utc)).total_seconds(), 0)
        freshness = "FRESH" if age <= 900 else "AGING" if age <= 86400 else "STALE"
        return MarketQuoteView(
            instrument=self._instrument(value.instrument),
            timestamp=value.timestamp,
            ltp=value.ltp,
            change=value.change,
            change_pct=value.change_pct,
            open=value.open,
            high=value.high,
            low=value.low,
            close=value.close,
            previous_close=value.previous_close,
            volume=value.volume,
            bid=value.bid,
            ask=value.ask,
            buy_depth=self._depth(value.buy_depth),
            sell_depth=self._depth(value.sell_depth),
            source=value.source,
            freshness=freshness,
            market_session=value.session_status,
        )

    def _reason(self, error: Exception) -> str:
        if isinstance(error, GrowwProviderNotConfiguredError):
            if self.session_manager:
                self.session_manager.record_provider_error("PROVIDER_UNAVAILABLE", detail=type(error).__name__)
            return "GROWW_NOT_CONFIGURED"
        if isinstance(error, GrowwRateLimitError):
            if self.session_manager:
                self.session_manager.record_rate_limited()
            return "PROVIDER_RATE_LIMITED"
        if self.session_manager:
            self.session_manager.record_provider_error("PROVIDER_FEATURE_UNAVAILABLE", detail=type(error).__name__)
        return "PROVIDER_FEATURE_UNAVAILABLE"

    def provider_status(self) -> MarketProviderStatusResponse:
        session_failed = False
        try:
            session = self.provider.get_market_status()
        except Exception:
            session = None
            session_failed = True
        connected = bool(getattr(self.provider, "connected", False))
        stream_state = str(getattr(getattr(self.feed_manager, "state", None), "value", None) or ("CONNECTED" if connected else "NOT_AVAILABLE"))
        return MarketProviderStatusResponse(
            generated_at=self._now(),
            provider=self.provider.provider_name,
            mode=self.provider.mode.value,
            configured=self.provider.configured,
            connected=connected,
            stream_state=stream_state,
            last_message_at=getattr(self.feed_manager, "last_message_at", None) or getattr(self.provider, "last_message_at", None),
            capabilities=tuple(str(getattr(value, "value", value)) for value in self.provider.capabilities),
            market_session=session.status if session else "UNKNOWN",
            reason=self.provider.unavailable_reason or ("PROVIDER_STATUS_UNAVAILABLE" if session_failed else None),
            code_ready=True,
            credential_ready=self.provider.provider_name == "GROWW" and self.provider.configured,
        )

    def search(self, query: str, *, limit: int = 20) -> MarketSearchResponse:
        try:
            items = self.provider.search_instruments(query, limit=limit)
            status = "AVAILABLE"
        except Exception:
            items = ()
            status = "UNAVAILABLE"
        cache = getattr(self.provider, "instrument_cache", None)
        refreshed_at = getattr(cache, "refreshed_at", None)
        if callable(refreshed_at):
            refreshed_at = refreshed_at()
        if refreshed_at is None:
            try:
                refreshed_at = self.provider.get_freshness().source_timestamp
            except Exception:
                refreshed_at = None
        return MarketSearchResponse(
            generated_at=self._now(),
            status=status,
            query=query,
            total_count=len(items),
            instrument_master_refreshed_at=refreshed_at,
            items=tuple(self._instrument(item) for item in items),
        )

    def quote(self, symbol: str) -> MarketQuoteResponse:
        try:
            quote = self.provider.get_quote(symbol)
        except Exception as error:
            return MarketQuoteResponse(
                generated_at=self._now(),
                status="UNAVAILABLE",
                reason=self._reason(error),
                provider=self.provider.provider_name,
                provider_mode=self.provider.mode.value,
                capabilities=tuple(str(getattr(value, "value", value)) for value in self.provider.capabilities),
            )
        return MarketQuoteResponse(
            generated_at=self._now(),
            status="AVAILABLE" if quote else "UNAVAILABLE",
            reason=None if quote else "INSTRUMENT_QUOTE_UNAVAILABLE",
            provider=self.provider.provider_name,
            provider_mode=self.provider.mode.value,
            capabilities=tuple(str(getattr(value, "value", value)) for value in self.provider.capabilities),
            quote=self._quote(quote) if quote else None,
        )

    def candles(
        self,
        symbol: str,
        *,
        range_name: str,
        interval: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketCandlesResponse:
        canonical_range = range_name.strip().upper()
        if canonical_range not in RANGE_DAYS:
            canonical_range = "1M"
        selected_interval = (interval or RANGE_INTERVALS[canonical_range]).strip().lower()
        if self.provider.mode.value == "SEEDED" and selected_interval != "1d":
            selected_interval = "1d"
        try:
            source_end = self.provider.get_freshness().source_timestamp
        except Exception:
            source_end = None
        window_end = end or source_end or self._now()
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=timezone.utc)
        window_start = start or window_end - timedelta(days=RANGE_DAYS[canonical_range])
        try:
            instrument = next(
                (
                    item for item in self.provider.search_instruments(symbol, limit=50)
                    if item.symbol.upper() == symbol.strip().upper()
                    or item.instrument_id.upper() == symbol.strip().upper()
                    or (item.groww_symbol or "").upper() == symbol.strip().upper()
                ),
                None,
            )
        except Exception:
            instrument = None
        try:
            rows = self.provider.get_candles(
                symbol,
                interval=selected_interval,
                start=window_start,
                end=window_end,
            )
            reason = None if rows else "HISTORICAL_CANDLES_UNAVAILABLE"
        except Exception as error:
            rows = ()
            reason = self._reason(error)
        return MarketCandlesResponse(
            generated_at=self._now(),
            status="AVAILABLE" if rows else "UNAVAILABLE",
            reason=reason,
            instrument=self._instrument(instrument) if instrument else None,
            source=self.provider.provider_name,
            interval=selected_interval,
            range=canonical_range,
            start=window_start,
            end=window_end,
            freshness="RECORDED" if self.provider.mode.value == "SEEDED" else "PROVIDER_HISTORICAL",
            candles=tuple(self._candle(row) for row in rows),
            last_recorded_candle_at=rows[-1].timestamp if rows else None,
        )

    @staticmethod
    def _candle(value: MarketCandleObservation) -> MarketCandleView:
        return MarketCandleView(
            timestamp=value.timestamp,
            open=value.open,
            high=value.high,
            low=value.low,
            close=value.close,
            volume=value.volume,
            open_interest=value.open_interest,
        )

    def indices(self) -> MarketIndicesResponse:
        try:
            observations = self.provider.get_index_snapshot()
        except Exception:
            observations = ()
        try:
            session = self.provider.get_market_status()
        except Exception:
            session = None
        observation_status = "RECORDED" if self.provider.mode.value == "SEEDED" else session.status if session else "UNKNOWN"
        return MarketIndicesResponse(
            generated_at=self._now(),
            status="AVAILABLE" if observations else "UNAVAILABLE",
            provider=self.provider.provider_name,
            items=tuple(
                MarketIndexWorkspaceView(
                    symbol=row.symbol,
                    name=row.name,
                    value=row.value,
                    change=row.change,
                    change_pct=row.change_pct,
                    previous_close=row.previous_close,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    timestamp=row.timestamp,
                    source=row.source,
                    status=observation_status,
                )
                for row in observations
            ),
        )

    def index_detail(self, symbol: str) -> MarketIndexDetailResponse:
        response = self.indices()
        aliases = {
            "NIFTY": "NIFTY_50",
            "NIFTY50": "NIFTY_50",
            "NIFTY500": "NIFTY_500",
            "BANKNIFTY": "BANK_NIFTY",
            "NIFTYBANK": "BANK_NIFTY",
        }
        canonical = aliases.get(symbol.strip().upper().replace("-", "").replace("_", ""), symbol.strip().upper())
        item = next((row for row in response.items if row.symbol == canonical), None)
        try:
            breadth = self.provider.get_breadth_snapshot() if canonical == "NIFTY_500" else None
        except Exception:
            breadth = None
        return MarketIndexDetailResponse(
            generated_at=self._now(),
            status="AVAILABLE" if item else "UNAVAILABLE",
            reason=None if item else "INDEX_UNAVAILABLE",
            item=item,
            breadth=(
                {
                    "advancers": breadth.advancers,
                    "decliners": breadth.decliners,
                    "unchanged": breadth.unchanged,
                    "positive_pct": str(breadth.positive_pct),
                }
                if breadth else None
            ),
            coverage=(
                {
                    "coverage_count": breadth.quality.coverage_count,
                    "expected_count": breadth.quality.expected_count,
                    "missing_count": breadth.quality.missing_count,
                }
                if breadth else None
            ),
        )

    @staticmethod
    def _sector_id(name: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")

    def sectors(self) -> MarketSectorsResponse:
        try:
            rows = self.provider.get_sector_snapshot()
        except Exception:
            rows = ()
        items = tuple(
            MarketSectorWorkspaceView(
                sector_id=self._sector_id(row.sector),
                name=row.sector,
                index_value=row.index_value,
                change_pct=row.return_pct,
                breadth_pct=row.breadth_pct,
                relative_volume=row.volume_context,
                coverage_count=row.quality.coverage_count,
                expected_count=row.quality.expected_count,
                advancers=row.advancers,
                decliners=row.decliners,
                unchanged=row.unchanged,
            )
            for row in rows
        )
        return MarketSectorsResponse(
            generated_at=self._now(),
            status="AVAILABLE" if items else "UNAVAILABLE",
            provider=self.provider.provider_name,
            items=items,
        )

    def sector_detail(self, sector_id: str) -> MarketSectorDetailResponse:
        sectors = self.sectors()
        canonical = self._sector_id(sector_id)
        item = next((row for row in sectors.items if row.sector_id == canonical), None)
        try:
            constituents = self.provider.get_sector_constituents(canonical) if item else ()
        except Exception:
            constituents = ()
        quoted: list[tuple[Decimal, InterSignalInstrument]] = []
        for instrument in constituents:
            try:
                quote = self.provider.get_quote(instrument.symbol)
            except Exception:
                quote = None
            if quote and quote.change_pct is not None:
                quoted.append((quote.change_pct, instrument))
        quoted.sort(key=lambda row: (row[0], row[1].symbol), reverse=True)
        return MarketSectorDetailResponse(
            generated_at=self._now(),
            status="AVAILABLE" if item else "UNAVAILABLE",
            reason=None if item else "SECTOR_UNAVAILABLE",
            item=item,
            constituents=tuple(self._instrument(value) for value in constituents),
            leaders=tuple(self._instrument(value) for _, value in quoted[:5]),
            laggards=tuple(self._instrument(value) for _, value in reversed(quoted[-5:])),
        )

    def option_chain(self, underlying: str, expiry: str) -> OptionChainResponse:
        if MarketProviderCapability.OPTION_CHAIN not in self.provider.capabilities:
            return OptionChainResponse(
                generated_at=self._now(), status="UNAVAILABLE", reason="OPTION_CHAIN_UNSUPPORTED",
                underlying=underlying.upper(), expiry=expiry,
            )
        try:
            rows = self.provider.get_option_chain(underlying, expiry)
            reason = None if rows else "OPTION_CHAIN_UNAVAILABLE"
        except Exception as error:
            rows = ()
            reason = self._reason(error)
        return OptionChainResponse(
            generated_at=self._now(),
            status="AVAILABLE" if rows else "UNAVAILABLE",
            reason=reason,
            underlying=underlying.upper(),
            expiry=expiry,
            items=rows,
        )


__all__ = ("MarketWorkspaceService", "RANGE_DAYS", "RANGE_INTERVALS")

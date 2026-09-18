from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TypeVar

from app.data_api.models import (
    DataAvailability,
    DataLimitationView,
    DataLimitationsResponse,
    DataLineageResponse,
    DataMeta,
    DataOverviewResponse,
    DataSourcesResponse,
    DataSourceView,
    LineageNodeView,
    LineageSummaryView,
)
from app.home.sources import PlatformDataHealthHomeSource
from app.platform.repositories import JsonFilePlatformRepository


T = TypeVar("T")


class DataHealthApplicationService:
    """Failure-isolated, read-only projection of persisted platform data health."""

    def __init__(
        self,
        *,
        platform: JsonFilePlatformRepository,
        health: PlatformDataHealthHomeSource,
        continuity: dict[str, Any],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._platform = platform
        self._health = health
        self._continuity = dict(continuity)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _generated_at(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Data API clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _meta(unavailable: list[str]) -> DataMeta:
        return DataMeta(unavailable_sections=tuple(dict.fromkeys(unavailable)))

    def _sources(self) -> tuple[DataSourceView, ...]:
        health = self._health.read()
        coverage = Decimal(str(self._continuity.get("coverage_pct", "77.826177")))
        gaps = int(self._continuity.get("unresolved_gap_count", 217))
        return (
            DataSourceView(
                source_id="daily-history",
                name="Daily market history",
                domain="MARKET_DATA",
                status=health.daily_history_status,
                research_use="AVAILABLE",
                summary="Frozen daily price and volume history is available to the research platform.",
                freshness=health.freshness_summary,
            ),
            DataSourceView(
                source_id="corporate-actions",
                name="Corporate actions",
                domain="REFERENCE_DATA",
                status=health.corporate_actions_status,
                research_use="AVAILABLE_WITH_CAVEATS",
                summary="Corporate-action records are available with documented continuity and adjustment caveats.",
                freshness=health.freshness_summary,
                limitations=("Documented adjustment and continuity caveats apply.",),
            ),
            DataSourceView(
                source_id="intraday-continuity",
                name="Intraday research",
                domain="MARKET_DATA",
                status=health.intraday_status,
                research_use="INSUFFICIENT_FOR_TRUSTWORTHY_FORMAL_EVALUATION",
                summary="Intraday data quality is insufficient for trustworthy formal evaluation.",
                freshness=health.freshness_summary,
                coverage_pct=coverage,
                gap_count=gaps,
                limitations=("Research evaluation is blocked; this is not a strategy failure.",),
                evidence_refs=("EVIDENCE-D-DATA-BLOCKED-001",),
            ),
            DataSourceView(
                source_id="catalyst-history",
                name="Historical catalyst events",
                domain="EVENT_DATA",
                status=health.catalyst_status,
                research_use="NOT_AUTHORIZED_FOR_FULL_RESEARCH_USE",
                summary="Historical catalyst source is not yet authorized for full research use.",
                freshness=health.freshness_summary,
                limitations=("A reproducible authorized historical catalyst source is required.",),
                evidence_refs=("EVIDENCE-F-SOURCE-BLOCKED-001",),
            ),
        )

    def _lineage(self) -> LineageSummaryView:
        health = self._health.read()
        nodes = self._platform.list_lineage_nodes()
        edges = self._platform.list_lineage_edges()
        parent_counts = Counter(row.child_node_id for row in edges)
        child_counts = Counter(row.parent_node_id for row in edges)
        latest = sorted(nodes, key=lambda row: (row.created_at, row.node_id), reverse=True)[:18]
        return LineageSummaryView(
            integrity_status=health.lineage_integrity,
            broken_reference_count=health.broken_reference_count,
            node_count=len(nodes),
            edge_count=len(edges),
            artifact_count=len(self._platform.list_artifacts()),
            stage_counts=dict(sorted(Counter(row.stage.value for row in nodes).items())),
            nodes=tuple(
                LineageNodeView(
                    node_id=row.node_id,
                    stage=row.stage.value,
                    entity_type=row.entity_type,
                    label=row.entity_type.replace("_", " ").title(),
                    version=row.version,
                    source_system=row.source_system,
                    status=row.status.value,
                    created_at=row.created_at,
                    parent_count=parent_counts[row.node_id],
                    child_count=child_counts[row.node_id],
                )
                for row in latest
            ),
        )

    @staticmethod
    def _limitations() -> tuple[DataLimitationView, ...]:
        return (
            DataLimitationView(
                limitation_id="LIMIT-INTRADAY-CONTINUITY",
                title="Intraday continuity below frozen threshold",
                status="OPEN",
                severity="BLOCKING",
                summary="77.826177% exact prior-20 continuity leaves 217 unresolved gaps.",
                impact="Insufficient for trustworthy formal evaluation of Family D.",
                resolution="Provide an approved intraday source meeting the frozen continuity threshold.",
                related_source_id="intraday-continuity",
            ),
            DataLimitationView(
                limitation_id="LIMIT-CATALYST-AUTHORIZATION",
                title="Catalyst source authorization unresolved",
                status="OPEN",
                severity="BLOCKING",
                summary="Historical catalyst acquisition is not authorized for full research use.",
                impact="Family F remains source-blocked; no performance conclusion exists.",
                resolution="Authorize a reproducible historical catalyst source and record its licensing terms.",
                related_source_id="catalyst-history",
            ),
            DataLimitationView(
                limitation_id="LIMIT-CORPORATE-ACTIONS-CAVEATS",
                title="Corporate-action caveats",
                status="DOCUMENTED",
                severity="ADVISORY",
                summary="Corporate-action data is available with documented adjustment and continuity caveats.",
                impact="Consumers must preserve the recorded adjusted-versus-raw semantics.",
                resolution="Retain caveat-aware use and provenance checks.",
                related_source_id="corporate-actions",
            ),
        )

    def _base(self, unavailable: list[str]) -> dict[str, Any]:
        return {
            "generated_at": self._generated_at(),
            "status": DataAvailability.PARTIAL if unavailable else DataAvailability.AVAILABLE,
            "reason": "DATA_SECTIONS_UNAVAILABLE" if unavailable else None,
            "meta": self._meta(unavailable),
        }

    def get_overview(self) -> DataOverviewResponse:
        unavailable: list[str] = []

        def read(name: str, operation: Callable[[], T], fallback: T) -> T:
            try:
                return operation()
            except Exception:
                unavailable.append(name)
                return fallback

        sources = read("sources", self._sources, ())
        lineage = read("lineage", self._lineage, None)
        limitations = read("limitations", self._limitations, ())
        return DataOverviewResponse(
            **self._base(unavailable),
            sources=sources,
            lineage=lineage,
            limitations=limitations,
        )

    def get_sources(self) -> DataSourcesResponse:
        items = self._sources()
        return DataSourcesResponse(**self._base([]), items=items, total_count=len(items))

    def get_lineage(self) -> DataLineageResponse:
        return DataLineageResponse(**self._base([]), lineage=self._lineage())

    def get_limitations(self) -> DataLimitationsResponse:
        items = self._limitations()
        return DataLimitationsResponse(**self._base([]), items=items, total_count=len(items))


__all__ = ("DataHealthApplicationService",)

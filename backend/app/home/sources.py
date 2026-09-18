from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.governance_audit.models import ReadinessStatus, ReadinessType
from app.governance_audit.service import GovernanceService
from app.home.models import (
    AvailabilityStatus,
    BlockedResearchItem,
    DataHealthHomeSnapshot,
    GovernanceHomeSnapshot,
    PortfolioHomeSnapshot,
    RecentActivityItem,
    ResearchEvidenceItem,
    ResearchHomeSnapshot,
)
from app.portfolio_os.models import Portfolio, PortfolioType
from app.portfolio_os.service import PortfolioOSService
from app.research_workbench.service import ResearchWorkbenchService


PERCENT = Decimal("100")


@runtime_checkable
class ResearchHomeSource(Protocol):
    def read(self) -> ResearchHomeSnapshot: ...


@runtime_checkable
class PortfolioHomeSource(Protocol):
    def read(self) -> PortfolioHomeSnapshot: ...


@runtime_checkable
class GovernanceHomeSource(Protocol):
    def read(self) -> GovernanceHomeSnapshot: ...


@runtime_checkable
class DataHealthHomeSource(Protocol):
    def read(self) -> DataHealthHomeSnapshot: ...


@runtime_checkable
class ActivityHomeSource(Protocol):
    def read(self) -> tuple[RecentActivityItem, ...]: ...


class ResearchWorkbenchHomeSource:
    EVIDENCE_ID = "EDGE-EVIDENCE-C-COMPRESSION-001"

    def __init__(self, service: ResearchWorkbenchService) -> None:
        self._service = service

    def read(self) -> ResearchHomeSnapshot:
        programme = self._service.get_programme_summary()
        families = self._service.list_research_families()
        evidence = self._service.get_evidence_detail(self.EVIDENCE_ID)
        blocked = self._service.list_blocked_research()
        return ResearchHomeSnapshot(
            status=AvailabilityStatus.AVAILABLE,
            programme_status=programme.strategy_research_status,
            family_count=len(families),
            production_candidate_count=programme.production_candidate_count,
            validated_production_strategy_count=programme.validated_strategy_count,
            strategy_v2_status=programme.strategy_v2_status,
            reusable_evidence=(
                ResearchEvidenceItem(
                    id=evidence.evidence_id,
                    title=evidence.title,
                    summary=evidence.description,
                    family=evidence.strategy_linkage.removeprefix("FAMILY_"),
                    status=evidence.status.value,
                    production_strategy=False,
                ),
            ),
            blocked_research=tuple(
                BlockedResearchItem(
                    family=row.family_id,
                    reason_code=row.block_type,
                    reason=row.reason,
                    source_ref=row.related_evidence[0],
                )
                for row in sorted(blocked, key=lambda item: item.family_id)
            ),
            latest_research_state=programme.a_to_g_cycle_status,
        )


class PortfolioOSHomeSource:
    def __init__(self, service: PortfolioOSService) -> None:
        self._service = service

    @staticmethod
    def _primary_portfolio(portfolios: list[Portfolio]) -> Portfolio:
        priority = {PortfolioType.MANUAL: 0, PortfolioType.RESEARCH: 1}
        return sorted(
            portfolios,
            key=lambda row: (priority.get(row.portfolio_type, 99), row.portfolio_id),
        )[0]

    def read(self) -> PortfolioHomeSnapshot:
        portfolios = self._service.list_portfolios()
        if not portfolios:
            return PortfolioHomeSnapshot(
                status=AvailabilityStatus.AVAILABLE,
                reason="NO_PORTFOLIO_CONFIGURED",
                has_portfolio=False,
                portfolio_count=0,
            )

        portfolio = self._primary_portfolio(portfolios)
        valuation = self._service.get_valuation(portfolio.portfolio_id)
        exposure = self._service.get_exposure(portfolio.portfolio_id)
        risk = self._service.get_risk(portfolio.portfolio_id)
        comparison = self._service.get_benchmark_comparison(portfolio.portfolio_id)
        missing = tuple(
            name
            for name, value in (
                ("VALUATION", valuation),
                ("EXPOSURE", exposure),
                ("RISK", risk),
                ("BENCHMARK_COMPARISON", comparison),
            )
            if value is None
        )
        synthetic = bool(portfolio.metadata.get("synthetic", False))
        return PortfolioHomeSnapshot(
            status=(
                AvailabilityStatus.PARTIAL
                if missing
                else AvailabilityStatus.AVAILABLE
            ),
            reason=("MISSING_" + "_AND_".join(missing)) if missing else None,
            has_portfolio=True,
            portfolio_count=len(portfolios),
            portfolio_id=portfolio.portfolio_id,
            name=portfolio.name,
            source_type="SYNTHETIC" if synthetic else "PLATFORM",
            currency=valuation.currency if valuation else portfolio.base_currency,
            valuation=valuation.net_liquidation_value if valuation else None,
            cash=valuation.cash if valuation else None,
            invested_value=valuation.gross_market_value if valuation else None,
            invested_pct=(exposure.gross_exposure * PERCENT) if exposure else None,
            period_change=(comparison.portfolio_return * PERCENT)
            if comparison
            else None,
            benchmark_delta=(comparison.active_return * PERCENT)
            if comparison
            else None,
            concentration=(risk.concentration * PERCENT) if risk else None,
            sector_exposure={
                key: value * PERCENT
                for key, value in sorted(
                    (exposure.sector_exposure if exposure else {}).items()
                )
            },
            holding_count=len(self._service.get_holdings(portfolio.portfolio_id)),
            valuation_timestamp=valuation.as_of if valuation else None,
        )


class GovernanceAuditHomeSource:
    def __init__(self, service: GovernanceService) -> None:
        self._service = service

    def read(self) -> GovernanceHomeSnapshot:
        summary = self._service.get_governance_summary()
        broker = summary.readiness_by_type.get(
            ReadinessType.BROKER_READINESS,
            ReadinessStatus.NOT_READY,
        )
        return GovernanceHomeSnapshot(
            status=AvailabilityStatus.AVAILABLE,
            paper_readiness=summary.paper_readiness.value,
            live_readiness=summary.live_readiness.value,
            broker_readiness=broker.value,
            production_readiness=summary.production_readiness.value,
            blocking_violation_count=summary.blocking_violations,
            pending_authorization_count=summary.open_authorizations,
            policy_summary={
                key: value.value for key, value in sorted(summary.policy_status.items())
            },
        )


class PlatformDataHealthHomeSource:
    def __init__(
        self,
        *,
        research: ResearchWorkbenchService,
        portfolio: PortfolioOSService,
        governance: GovernanceService,
    ) -> None:
        self._research = research
        self._portfolio = portfolio
        self._governance = governance

    def read(self) -> DataHealthHomeSnapshot:
        research = self._research.get_integrity_summary()
        portfolio = self._portfolio.get_integrity_summary()
        governance = self._governance.get_integrity_summary()
        blocked = {
            row.family_id: row for row in self._research.list_blocked_research()
        }
        broken_references = sum(
            (
                research.broken_strategy_refs,
                research.broken_evidence_refs,
                research.broken_artifact_refs,
                research.broken_lineage_refs,
                portfolio.broken_refs,
                governance.broken_subject_refs,
                governance.invalid_authorization_references,
            )
        )
        integrity_statuses = {
            research.status.value,
            portfolio.status.value,
            governance.status.value,
        }
        lineage_integrity = (
            "HEALTHY" if integrity_statuses == {"HEALTHY"} else "ERROR"
        )
        intraday_status = (
            "BLOCKED_FOR_RESEARCH_USE"
            if blocked.get("D") and blocked["D"].block_type == "DATA_BLOCKED"
            else "AVAILABLE"
        )
        catalyst_status = (
            "SOURCE_BLOCKED"
            if blocked.get("F") and blocked["F"].block_type == "SOURCE_BLOCKED"
            else "AVAILABLE"
        )
        limitations = tuple(
            sorted(
                {
                    "CORPORATE_ACTIONS_AVAILABLE_WITH_DOCUMENTED_CAVEATS",
                    *(
                        {"FAMILY_D_INTRADAY_CONTINUITY_DATA_BLOCKED"}
                        if intraday_status != "AVAILABLE"
                        else set()
                    ),
                    *(
                        {"FAMILY_F_CATALYST_AUTHORIZED_SOURCE_REQUIRED"}
                        if catalyst_status != "AVAILABLE"
                        else set()
                    ),
                }
            )
        )
        status = (
            AvailabilityStatus.PARTIAL
            if limitations or lineage_integrity != "HEALTHY"
            else AvailabilityStatus.AVAILABLE
        )
        return DataHealthHomeSnapshot(
            status=status,
            lineage_integrity=lineage_integrity,
            broken_reference_count=broken_references,
            daily_history_status="AVAILABLE",
            corporate_actions_status="AVAILABLE_WITH_CAVEATS",
            intraday_status=intraday_status,
            catalyst_status=catalyst_status,
            freshness_summary="STATIC_SEEDED_PLATFORM_STATE",
            data_limitations=limitations,
        )


class PlatformActivityHomeSource:
    ALLOWED_EVENT_TYPES = {
        "AUTHORIZATION_REQUESTED",
        "PORTFOLIO_EVENT",
        "READINESS_ASSESSMENT",
        "STRATEGY_STATE_CHANGE",
    }

    def __init__(self, service: GovernanceService, *, limit: int = 6) -> None:
        if limit <= 0:
            raise ValueError("activity limit must be positive")
        self._service = service
        self._limit = limit

    @staticmethod
    def _title(event_type: str, action: str) -> str:
        if event_type == "AUTHORIZATION_REQUESTED":
            return "Authorization requested"
        if event_type == "READINESS_ASSESSMENT":
            return "Readiness assessment recorded"
        if event_type == "STRATEGY_STATE_CHANGE":
            return "Research family state recorded"
        return action.replace("_", " ").title()

    def read(self) -> tuple[RecentActivityItem, ...]:
        rows = [
            row
            for row in self._service.get_combined_audit_timeline()
            if row.event_type in self.ALLOWED_EVENT_TYPES
        ]
        rows.sort(
            key=lambda row: (row.timestamp, row.source.value, row.source_event_id),
            reverse=True,
        )
        return tuple(
            RecentActivityItem(
                id=row.source_event_id,
                title=self._title(row.event_type, row.action),
                summary=row.reason,
                source_domain=row.domain,
                source_ref=f"{row.source.value}:{row.subject_id}",
                occurred_at=row.timestamp,
            )
            for row in rows[: self._limit]
        )


__all__ = (
    "ActivityHomeSource",
    "DataHealthHomeSource",
    "GovernanceAuditHomeSource",
    "GovernanceHomeSource",
    "PlatformActivityHomeSource",
    "PlatformDataHealthHomeSource",
    "PortfolioHomeSource",
    "PortfolioOSHomeSource",
    "ResearchHomeSource",
    "ResearchWorkbenchHomeSource",
)

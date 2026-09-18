from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.home.models import (
    AttentionItem,
    AttentionSeverity,
    AvailabilityDetail,
    AvailabilityStatus,
    DataHealthHomeSnapshot,
    GovernanceHomeSnapshot,
    HomeAvailability,
    HomeMeta,
    HomeSnapshot,
    MarketHomeSnapshot,
    PortfolioHomeSnapshot,
    RecentActivityItem,
    ResearchHomeSnapshot,
)
from app.home.sources import (
    ActivityHomeSource,
    DataHealthHomeSource,
    GovernanceHomeSource,
    PortfolioHomeSource,
    ResearchHomeSource,
)


class HomeApplicationService:
    """Read-only, failure-isolated aggregation for the Home API contract."""

    def __init__(
        self,
        *,
        research: ResearchHomeSource,
        portfolio: PortfolioHomeSource,
        governance: GovernanceHomeSource,
        data_health: DataHealthHomeSource,
        activity: ActivityHomeSource,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._research = research
        self._portfolio = portfolio
        self._governance = governance
        self._data_health = data_health
        self._activity = activity
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _read_research(source: ResearchHomeSource) -> ResearchHomeSnapshot:
        try:
            return source.read()
        except Exception:
            return ResearchHomeSnapshot(
                status=AvailabilityStatus.UNAVAILABLE,
                reason="RESEARCH_SOURCE_UNAVAILABLE",
            )

    @staticmethod
    def _read_portfolio(source: PortfolioHomeSource) -> PortfolioHomeSnapshot:
        try:
            return source.read()
        except Exception:
            return PortfolioHomeSnapshot(
                status=AvailabilityStatus.UNAVAILABLE,
                reason="PORTFOLIO_SOURCE_UNAVAILABLE",
                has_portfolio=False,
                portfolio_count=0,
            )

    @staticmethod
    def _read_governance(source: GovernanceHomeSource) -> GovernanceHomeSnapshot:
        try:
            return source.read()
        except Exception:
            return GovernanceHomeSnapshot(
                status=AvailabilityStatus.UNAVAILABLE,
                reason="GOVERNANCE_SOURCE_UNAVAILABLE",
            )

    @staticmethod
    def _read_data_health(source: DataHealthHomeSource) -> DataHealthHomeSnapshot:
        try:
            return source.read()
        except Exception:
            return DataHealthHomeSnapshot(
                status=AvailabilityStatus.UNAVAILABLE,
                reason="DATA_HEALTH_SOURCE_UNAVAILABLE",
            )

    @staticmethod
    def _read_activity(
        source: ActivityHomeSource,
    ) -> tuple[tuple[RecentActivityItem, ...], AvailabilityDetail]:
        try:
            return (
                source.read(),
                AvailabilityDetail(status=AvailabilityStatus.AVAILABLE),
            )
        except Exception:
            return (
                (),
                AvailabilityDetail(
                    status=AvailabilityStatus.UNAVAILABLE,
                    reason="ACTIVITY_SOURCE_UNAVAILABLE",
                ),
            )

    @staticmethod
    def _availability(
        status: AvailabilityStatus,
        reason: str | None,
    ) -> AvailabilityDetail:
        return AvailabilityDetail(status=status, reason=reason)

    @staticmethod
    def _attention(
        *,
        research: ResearchHomeSnapshot,
        portfolio: PortfolioHomeSnapshot,
        governance: GovernanceHomeSnapshot,
    ) -> tuple[AttentionItem, ...]:
        rows: list[AttentionItem] = []
        if (
            research.status != AvailabilityStatus.UNAVAILABLE
            and research.programme_status == "PAUSED"
        ):
            rows.append(
                AttentionItem(
                    id="research-programme-paused",
                    category="Research",
                    title="Research programme is paused.",
                    summary=(
                        "The A-G cycle is complete with no validated production strategy."
                    ),
                    severity=AttentionSeverity.NOTICE,
                    source_domain="RESEARCH",
                    source_ref="RESEARCH_PROGRAMME",
                    research_context=research.latest_research_state,
                    action_target="/app/research",
                    metadata={"investment_recommendation": False},
                )
            )
        for blocked in research.blocked_research:
            rows.append(
                AttentionItem(
                    id=f"research-family-{blocked.family.lower()}-blocked",
                    category="Research data",
                    title=f"Family {blocked.family} research remains blocked.",
                    summary=blocked.reason,
                    severity=AttentionSeverity.WARNING,
                    source_domain="RESEARCH",
                    source_ref=blocked.source_ref,
                    research_context=blocked.reason_code,
                    action_target="/app/research",
                    metadata={
                        "family": blocked.family,
                        "investment_recommendation": False,
                    },
                )
            )
        if (
            governance.status != AvailabilityStatus.UNAVAILABLE
            and governance.paper_readiness != "READY"
        ):
            rows.append(
                AttentionItem(
                    id="governance-paper-not-ready",
                    category="Governance",
                    title="Paper readiness is not ready.",
                    summary="Current governance state does not authorize paper trading.",
                    severity=AttentionSeverity.NOTICE,
                    source_domain="GOVERNANCE",
                    source_ref="PAPER_TRADING_READINESS",
                    action_target="/app/governance",
                    metadata={"investment_recommendation": False},
                )
            )
        if (
            governance.status != AvailabilityStatus.UNAVAILABLE
            and governance.broker_readiness != "READY"
        ):
            rows.append(
                AttentionItem(
                    id="governance-broker-not-ready",
                    category="Connectivity",
                    title="Broker connection is not configured.",
                    summary="No broker connection or execution path is active.",
                    severity=AttentionSeverity.INFO,
                    source_domain="GOVERNANCE",
                    source_ref="BROKER_READINESS",
                    action_target="/app/governance",
                    metadata={"investment_recommendation": False},
                )
            )
        if (
            portfolio.status != AvailabilityStatus.UNAVAILABLE
            and portfolio.has_portfolio
            and portfolio.source_type == "SYNTHETIC"
        ):
            rows.append(
                AttentionItem(
                    id="portfolio-synthetic-source",
                    category="Portfolio context",
                    title="Portfolio context is synthetic.",
                    summary="Seeded Portfolio OS data is for platform verification only.",
                    severity=AttentionSeverity.INFO,
                    source_domain="PORTFOLIO",
                    source_ref=portfolio.portfolio_id or "PORTFOLIO_OS",
                    portfolio_context="SYNTHETIC",
                    action_target="/app/portfolio",
                    metadata={"investment_recommendation": False},
                )
            )
        severity_order = {
            AttentionSeverity.WARNING: 0,
            AttentionSeverity.NOTICE: 1,
            AttentionSeverity.INFO: 2,
        }
        return tuple(sorted(rows, key=lambda row: (severity_order[row.severity], row.id)))

    def get_snapshot(self) -> HomeSnapshot:
        research = self._read_research(self._research)
        portfolio = self._read_portfolio(self._portfolio)
        governance = self._read_governance(self._governance)
        data_health = self._read_data_health(self._data_health)
        activity, activity_availability = self._read_activity(self._activity)
        market = MarketHomeSnapshot()
        availability = HomeAvailability(
            market=self._availability(market.status, market.reason),
            portfolio=self._availability(portfolio.status, portfolio.reason),
            research=self._availability(research.status, research.reason),
            data_health=self._availability(data_health.status, data_health.reason),
            governance=self._availability(governance.status, governance.reason),
            activity=activity_availability,
        )
        partial_response = any(
            item.status != AvailabilityStatus.AVAILABLE
            for item in (
                availability.market,
                availability.portfolio,
                availability.research,
                availability.data_health,
                availability.governance,
                availability.activity,
            )
        )
        generated_at = self._clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        return HomeSnapshot(
            generated_at=generated_at,
            availability=availability,
            market=market,
            portfolio=portfolio,
            research=research,
            data_health=data_health,
            governance=governance,
            attention=self._attention(
                research=research,
                portfolio=portfolio,
                governance=governance,
            ),
            recent_activity=activity,
            meta=HomeMeta(
                partial_response=partial_response,
                source_contracts=(
                    "INTERSIGNAL_RESEARCH_WORKBENCH_SNAPSHOT_V1",
                    "INTERSIGNAL_PORTFOLIO_OS_SNAPSHOT_V1",
                    "INTERSIGNAL_GOVERNANCE_AUDIT_SNAPSHOT_V1",
                ),
            ),
        )


__all__ = ("HomeApplicationService",)

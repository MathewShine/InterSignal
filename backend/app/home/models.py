from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_HOME_SNAPSHOT_V1 = "INTERSIGNAL_HOME_SNAPSHOT_V1"


class HomeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("generated_at", "valuation_timestamp", "occurred_at", check_fields=False)
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class AvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class AttentionSeverity(StrEnum):
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"


class AvailabilityDetail(HomeModel):
    status: AvailabilityStatus
    reason: str | None = None


class HomeAvailability(HomeModel):
    market: AvailabilityDetail
    portfolio: AvailabilityDetail
    research: AvailabilityDetail
    data_health: AvailabilityDetail
    governance: AvailabilityDetail
    activity: AvailabilityDetail


class MarketHomeSnapshot(HomeModel):
    status: AvailabilityStatus = AvailabilityStatus.UNAVAILABLE
    reason: str = "LIVE_MARKET_SERVICE_NOT_CONFIGURED"
    source: str = "NOT_CONFIGURED"


class ResearchEvidenceItem(HomeModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    family: str = Field(min_length=1)
    status: str = Field(min_length=1)
    production_strategy: bool = False


class BlockedResearchItem(HomeModel):
    family: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)


class ResearchHomeSnapshot(HomeModel):
    status: AvailabilityStatus
    reason: str | None = None
    programme_status: str = "UNAVAILABLE"
    family_count: int = Field(default=0, ge=0)
    production_candidate_count: int = Field(default=0, ge=0)
    validated_production_strategy_count: int = Field(default=0, ge=0)
    strategy_v2_status: str = "UNAVAILABLE"
    reusable_evidence: tuple[ResearchEvidenceItem, ...] = ()
    blocked_research: tuple[BlockedResearchItem, ...] = ()
    latest_research_state: str = "UNAVAILABLE"


class PortfolioHomeSnapshot(HomeModel):
    status: AvailabilityStatus
    reason: str | None = None
    has_portfolio: bool
    portfolio_count: int = Field(ge=0)
    portfolio_id: str | None = None
    name: str | None = None
    source_type: str = "NONE"
    currency: str | None = None
    valuation: Decimal | None = None
    cash: Decimal | None = None
    invested_value: Decimal | None = None
    invested_pct: Decimal | None = None
    period_change: Decimal | None = None
    benchmark_delta: Decimal | None = None
    concentration: Decimal | None = None
    sector_exposure: dict[str, Decimal] = Field(default_factory=dict)
    holding_count: int = Field(default=0, ge=0)
    valuation_timestamp: datetime | None = None


class GovernanceHomeSnapshot(HomeModel):
    status: AvailabilityStatus
    reason: str | None = None
    paper_readiness: str = "UNAVAILABLE"
    live_readiness: str = "UNAVAILABLE"
    broker_readiness: str = "UNAVAILABLE"
    production_readiness: str = "UNAVAILABLE"
    blocking_violation_count: int = Field(default=0, ge=0)
    pending_authorization_count: int = Field(default=0, ge=0)
    policy_summary: dict[str, str] = Field(default_factory=dict)


class DataHealthHomeSnapshot(HomeModel):
    status: AvailabilityStatus
    reason: str | None = None
    lineage_integrity: str = "UNAVAILABLE"
    broken_reference_count: int = Field(default=0, ge=0)
    daily_history_status: str = "UNAVAILABLE"
    corporate_actions_status: str = "UNAVAILABLE"
    intraday_status: str = "UNAVAILABLE"
    catalyst_status: str = "UNAVAILABLE"
    freshness_summary: str = "UNAVAILABLE"
    data_limitations: tuple[str, ...] = ()


class AttentionItem(HomeModel):
    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    severity: AttentionSeverity
    source_domain: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    portfolio_context: str | None = None
    research_context: str | None = None
    action_target: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecentActivityItem(HomeModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_domain: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    occurred_at: datetime


class HomeMeta(HomeModel):
    read_only: bool = True
    auth_enforcement: str = "NOT_IMPLEMENTED"
    market_integration: str = "NOT_CONFIGURED"
    broker_integration: str = "NOT_IMPLEMENTED"
    data_scope: str = "SEEDED_LOCAL_PLATFORM_STATE"
    partial_response: bool
    source_contracts: tuple[str, ...]


class HomeSnapshot(HomeModel):
    version: str = INTERSIGNAL_HOME_SNAPSHOT_V1
    generated_at: datetime
    mode: str = "BACKEND_READ_ONLY_PROTOTYPE"
    availability: HomeAvailability
    market: MarketHomeSnapshot
    portfolio: PortfolioHomeSnapshot
    research: ResearchHomeSnapshot
    data_health: DataHealthHomeSnapshot
    governance: GovernanceHomeSnapshot
    attention: tuple[AttentionItem, ...]
    recent_activity: tuple[RecentActivityItem, ...]
    meta: HomeMeta


__all__ = (
    "INTERSIGNAL_HOME_SNAPSHOT_V1",
    "AttentionItem",
    "AttentionSeverity",
    "AvailabilityDetail",
    "AvailabilityStatus",
    "BlockedResearchItem",
    "DataHealthHomeSnapshot",
    "GovernanceHomeSnapshot",
    "HomeAvailability",
    "HomeMeta",
    "HomeSnapshot",
    "MarketHomeSnapshot",
    "PortfolioHomeSnapshot",
    "RecentActivityItem",
    "ResearchEvidenceItem",
    "ResearchHomeSnapshot",
)

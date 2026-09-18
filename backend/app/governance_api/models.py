from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_GOVERNANCE_V1 = "INTERSIGNAL_GOVERNANCE_V1"


class GovernanceApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator(
        "generated_at", "assessed_at", "evaluated_at", "requested_at",
        "decided_at", "expires_at", "occurred_at", "created_at",
        check_fields=False,
    )
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Governance API timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class GovernanceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class GovernanceMeta(GovernanceApiModel):
    read_only: bool = True
    source_contract: str = "INTERSIGNAL_GOVERNANCE_AUDIT_SNAPSHOT_V1"
    broker_integration: str = "NOT_CONNECTED"
    live_market_integration: str = "NOT_CONFIGURED"
    auth_enforcement: str = "NOT_IMPLEMENTED"
    internal_paths_exposed: bool = False
    runtime_fixtures: bool = False
    unavailable_sections: tuple[str, ...] = ()


class ReadinessView(GovernanceApiModel):
    assessment_id: str
    readiness_type: str
    label: str
    subject_id: str
    status: str
    assessed_at: datetime
    passed_criteria: int = Field(ge=0)
    total_criteria: int = Field(ge=0)
    failed_criteria: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    connection_state: str | None = None


class PolicyView(GovernanceApiModel):
    policy_id: str
    name: str
    version: str
    domain: str
    description: str
    severity: str
    enabled: bool
    evaluation_status: str
    evaluated_at: datetime | None = None
    passed_checks: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class AuthorizationView(GovernanceApiModel):
    authorization_id: str
    authorization_type: str
    subject_id: str
    subject_type: str
    status: str
    requested_by: str
    requested_at: datetime
    decided_at: datetime | None = None
    reason: str
    conditions: tuple[str, ...] = ()
    expires_at: datetime | None = None


class AuditView(GovernanceApiModel):
    event_id: str
    source: str
    event_type: str
    domain: str
    subject_id: str
    subject_type: str
    actor: str
    occurred_at: datetime
    action: str
    result: str
    reason: str
    authorization_id: str | None = None


class OverrideView(GovernanceApiModel):
    override_id: str
    subject_id: str
    override_type: str
    requested_by: str
    approved_by: str
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    authorization_id: str


class GovernanceSummaryView(GovernanceApiModel):
    paper_readiness: str
    live_readiness: str
    broker_readiness: str
    production_readiness: str
    broker_connection_state: str
    blocking_violation_count: int = Field(ge=0)
    open_violation_count: int = Field(ge=0)
    pending_authorization_count: int = Field(ge=0)
    approved_authorization_count: int = Field(ge=0)
    passing_policy_count: int = Field(ge=0)
    total_policy_count: int = Field(ge=0)
    policy_passes_imply_readiness: bool = False
    integrity_status: str


class GovernanceResponse(GovernanceApiModel):
    version: str = INTERSIGNAL_GOVERNANCE_V1
    generated_at: datetime
    status: GovernanceAvailability
    reason: str | None = None
    meta: GovernanceMeta = Field(default_factory=GovernanceMeta)


class GovernanceOverviewResponse(GovernanceResponse):
    summary: GovernanceSummaryView | None = None
    readiness: tuple[ReadinessView, ...] = ()
    policies: tuple[PolicyView, ...] = ()
    authorizations: tuple[AuthorizationView, ...] = ()
    recent_audit: tuple[AuditView, ...] = ()
    manual_overrides: tuple[OverrideView, ...] = ()


class GovernanceReadinessResponse(GovernanceResponse):
    items: tuple[ReadinessView, ...] = ()
    total_count: int = Field(ge=0)


class GovernancePoliciesResponse(GovernanceResponse):
    items: tuple[PolicyView, ...] = ()
    passing_count: int = Field(ge=0)
    total_count: int = Field(ge=0)


class GovernanceAuthorizationsResponse(GovernanceResponse):
    items: tuple[AuthorizationView, ...] = ()
    pending_count: int = Field(ge=0)
    total_count: int = Field(ge=0)


class GovernanceAuditResponse(GovernanceResponse):
    items: tuple[AuditView, ...] = ()
    manual_overrides: tuple[OverrideView, ...] = ()
    total_count: int = Field(ge=0)


__all__ = (
    "INTERSIGNAL_GOVERNANCE_V1",
    "GovernanceAuditResponse",
    "GovernanceAuthorizationsResponse",
    "GovernanceOverviewResponse",
    "GovernancePoliciesResponse",
    "GovernanceReadinessResponse",
)

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.platform.hashing import canonical_hash
from app.platform.models import ImmutableDomainModel


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GovernanceModel(ImmutableDomainModel):
    @field_validator(
        "requested_at",
        "decided_at",
        "expires_at",
        "assessed_at",
        "created_at",
        "evaluated_at",
        "detected_at",
        "resolved_at",
        "timestamp",
        "generated_at",
        check_fields=False,
    )
    @classmethod
    def require_aware_governance_timestamp(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Governance timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class GovernanceSubjectType(StrEnum):
    STRATEGY = "STRATEGY"
    EVIDENCE = "EVIDENCE"
    VALIDATION = "VALIDATION"
    PORTFOLIO = "PORTFOLIO"
    ACCOUNT = "ACCOUNT"
    BROKER_CONNECTION = "BROKER_CONNECTION"
    DATA_SOURCE = "DATA_SOURCE"
    RESEARCH_PROGRAM = "RESEARCH_PROGRAM"
    PLATFORM_MODULE = "PLATFORM_MODULE"


class AuthorizationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    NOT_REQUIRED = "NOT_REQUIRED"


class AuthorizationType(StrEnum):
    RESEARCH_RUN = "RESEARCH_RUN"
    VALIDATION_RUN = "VALIDATION_RUN"
    POST_OUTCOME_EVALUATION = "POST_OUTCOME_EVALUATION"
    DATA_ACQUISITION = "DATA_ACQUISITION"
    BROKER_CONNECTION = "BROKER_CONNECTION"
    SHADOW_MODE = "SHADOW_MODE"
    PAPER_TRADING = "PAPER_TRADING"
    LIVE_TRADING = "LIVE_TRADING"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    STRATEGY_PROMOTION = "STRATEGY_PROMOTION"
    PRODUCTION_ENABLEMENT = "PRODUCTION_ENABLEMENT"


class ReadinessStatus(StrEnum):
    READY = "READY"
    READY_WITH_LIMITATIONS = "READY_WITH_LIMITATIONS"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReadinessType(StrEnum):
    RESEARCH_READINESS = "RESEARCH_READINESS"
    VALIDATION_READINESS = "VALIDATION_READINESS"
    DATA_READINESS = "DATA_READINESS"
    SHADOW_READINESS = "SHADOW_READINESS"
    PAPER_TRADING_READINESS = "PAPER_TRADING_READINESS"
    LIVE_TRADING_READINESS = "LIVE_TRADING_READINESS"
    PRODUCTION_READINESS = "PRODUCTION_READINESS"
    BROKER_READINESS = "BROKER_READINESS"
    PLATFORM_MODULE_READINESS = "PLATFORM_MODULE_READINESS"


class PolicySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    MATERIAL = "MATERIAL"
    CRITICAL = "CRITICAL"
    BLOCKING = "BLOCKING"


class PolicyOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    TRUTHY = "TRUTHY"
    FALSY = "FALSY"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"


class PolicyEvaluationStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ViolationStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"


class AuditEventType(StrEnum):
    DATA_INGEST = "DATA_INGEST"
    RESEARCH_RUN = "RESEARCH_RUN"
    CONFIG_FREEZE = "CONFIG_FREEZE"
    AUTHORIZATION_REQUESTED = "AUTHORIZATION_REQUESTED"
    AUTHORIZATION_GRANTED = "AUTHORIZATION_GRANTED"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    VALIDATION_RUN = "VALIDATION_RUN"
    STRATEGY_STATE_CHANGE = "STRATEGY_STATE_CHANGE"
    PORTFOLIO_EVENT = "PORTFOLIO_EVENT"
    BROKER_ACTION = "BROKER_ACTION"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    VIOLATION_DETECTED = "VIOLATION_DETECTED"
    VIOLATION_RESOLVED = "VIOLATION_RESOLVED"
    READINESS_ASSESSMENT = "READINESS_ASSESSMENT"
    PLATFORM_STATE_CHANGE = "PLATFORM_STATE_CHANGE"


class IntegrityStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ERROR = "ERROR"


class TimelineSource(StrEnum):
    REGISTRY = "REGISTRY"
    PORTFOLIO = "PORTFOLIO"
    GOVERNANCE = "GOVERNANCE"


class GovernanceSubject(GovernanceModel):
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    current_state: str = Field(min_length=1)
    readiness_state: str = Field(min_length=1)
    related_artifact_ids: tuple[str, ...] = ()
    related_lineage_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorizationRecord(GovernanceModel):
    authorization_id: str = Field(min_length=1)
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    authorization_type: AuthorizationType
    status: AuthorizationStatus
    requested_by: str = Field(min_length=1)
    approved_by: str | None = None
    requested_at: datetime
    decided_at: datetime | None = None
    reason: str = Field(min_length=1)
    conditions: tuple[str, ...] = ()
    expires_at: datetime | None = None
    related_artifact_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_authorization(self) -> "AuthorizationRecord":
        decided = {
            AuthorizationStatus.APPROVED,
            AuthorizationStatus.REJECTED,
            AuthorizationStatus.REVOKED,
            AuthorizationStatus.EXPIRED,
            AuthorizationStatus.NOT_REQUIRED,
        }
        if self.status == AuthorizationStatus.REQUESTED:
            if self.approved_by is not None or self.decided_at is not None:
                raise ValueError("REQUESTED authorization cannot contain decision fields")
        elif self.status in decided:
            if self.approved_by is None or self.decided_at is None:
                raise ValueError("Decided authorization requires actor and timestamp")
            if self.decided_at < self.requested_at:
                raise ValueError("decided_at cannot precede requested_at")
        if self.expires_at is not None and self.expires_at <= self.requested_at:
            raise ValueError("expires_at must follow requested_at")
        return self


class ReadinessAssessment(GovernanceModel):
    assessment_id: str = Field(min_length=1)
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    readiness_type: ReadinessType
    status: ReadinessStatus
    criteria: dict[str, bool]
    failed_criteria: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    assessed_at: datetime
    evidence_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_failed_criteria(self) -> "ReadinessAssessment":
        expected = {key for key, passed in self.criteria.items() if not passed}
        if set(self.failed_criteria) != expected:
            raise ValueError("failed_criteria must exactly identify false criteria")
        if self.status == ReadinessStatus.READY and self.failed_criteria:
            raise ValueError("READY assessment cannot contain failed criteria")
        return self


class PolicyRule(GovernanceModel):
    rule_id: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    operator: PolicyOperator
    expected: Any = None
    message: str = Field(min_length=1)
    warning_only: bool = False


class GovernancePolicy(GovernanceModel):
    policy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: PolicySeverity
    enabled: bool
    rules: tuple[PolicyRule, ...] = Field(min_length=1)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEvaluation(GovernanceModel):
    evaluation_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    status: PolicyEvaluationStatus
    evaluated_at: datetime
    passed_checks: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    details: dict[str, Any] = Field(default_factory=dict)
    related_artifacts: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceViolation(GovernanceModel):
    violation_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    severity: PolicySeverity
    status: ViolationStatus
    description: str = Field(min_length=1)
    detected_at: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None
    related_artifact_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_resolution(self) -> "GovernanceViolation":
        closed = self.status in {ViolationStatus.RESOLVED, ViolationStatus.WAIVED}
        if closed and (self.resolved_at is None or not self.resolution):
            raise ValueError("Resolved or waived violation requires resolution details")
        if not closed and self.resolved_at is not None:
            raise ValueError("Open violation state cannot contain resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.detected_at:
            raise ValueError("resolved_at cannot precede detected_at")
        return self


class ManualOverride(GovernanceModel):
    override_id: str = Field(min_length=1)
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    override_type: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None = None
    authorization_id: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_override(self) -> "ManualOverride":
        if self.before_state == self.after_state:
            raise ValueError("Override must describe a state change")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("Override expiry must follow creation")
        return self


class AuditEvent(GovernanceModel):
    audit_event_id: str = Field(min_length=1)
    event_type: AuditEventType
    domain: str = Field(min_length=1)
    subject_type: GovernanceSubjectType
    subject_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    timestamp: datetime
    action: str = Field(min_length=1)
    result: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authorization_id: str | None = None
    related_artifact_ids: tuple[str, ...] = ()
    lineage_node_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditTimelineEntry(GovernanceModel):
    source: TimelineSource
    source_event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    timestamp: datetime
    action: str = Field(min_length=1)
    result: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authorization_id: str | None = None
    related_artifact_ids: tuple[str, ...] = ()
    lineage_node_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlatformModuleState(GovernanceModel):
    module_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    command_version: str = Field(min_length=1)
    foundation_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("foundation_hash")
    @classmethod
    def validate_foundation_hash(cls, value: str | None) -> str | None:
        if value is not None and not HASH_PATTERN.fullmatch(value):
            raise ValueError("foundation_hash must be a lowercase SHA-256 digest")
        return value


class GovernanceSummary(GovernanceModel):
    open_authorizations: int = Field(ge=0)
    approved_authorizations: int = Field(ge=0)
    open_violations: int = Field(ge=0)
    blocking_violations: int = Field(ge=0)
    readiness_by_type: dict[ReadinessType, ReadinessStatus]
    policy_status: dict[str, PolicyEvaluationStatus]
    latest_audit_event: AuditTimelineEntry | None = None
    production_readiness: ReadinessStatus
    paper_readiness: ReadinessStatus
    live_readiness: ReadinessStatus


class GovernanceIntegritySummary(GovernanceModel):
    broken_subject_refs: int = Field(ge=0)
    invalid_authorization_references: int = Field(ge=0)
    expired_approval_usage: int = Field(ge=0)
    override_without_authorization: int = Field(ge=0)
    duplicate_ids: int = Field(ge=0)
    audit_sequence_errors: int = Field(ge=0)
    policy_version_conflicts: int = Field(ge=0)
    hash_mismatches: int = Field(ge=0)
    status: IntegrityStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceSnapshot(GovernanceModel):
    snapshot_version: str = Field(min_length=1)
    generated_at: datetime
    summary: GovernanceSummary
    subjects: tuple[GovernanceSubject, ...]
    authorizations: tuple[AuthorizationRecord, ...]
    readiness: tuple[ReadinessAssessment, ...]
    policies: tuple[GovernancePolicy, ...]
    policy_evaluations: tuple[PolicyEvaluation, ...]
    violations: tuple[GovernanceViolation, ...]
    manual_overrides: tuple[ManualOverride, ...]
    audit_timeline: tuple[AuditTimelineEntry, ...]
    module_state: tuple[PlatformModuleState, ...]
    integrity: GovernanceIntegritySummary
    snapshot_hash: str

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("snapshot_hash must be a lowercase SHA-256 digest")
        return value


def governance_record_hash(record: GovernanceModel) -> str:
    return canonical_hash(record)


__all__ = tuple(
    name
    for name in globals()
    if name[0].isupper() and name not in {"Any", "Field"}
) + ("governance_record_hash",)

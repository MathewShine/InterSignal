from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from app.platform.hashing import canonical_hash, deterministic_id
from app.platform.models import RegistryEntityType, RegistryEvent
from app.portfolio_os.models import PortfolioEvent
from app.governance_audit.errors import (
    AuthorizationExpired,
    AuthorizationNotFound,
    GovernanceIntegrityError,
    GovernanceSubjectNotFound,
    InvalidAuthorizationTransition,
    InvalidOverride,
    PolicyNotFound,
    ViolationNotFound,
)
from app.governance_audit.models import (
    AuditEvent,
    AuditEventType,
    AuditTimelineEntry,
    AuthorizationRecord,
    AuthorizationStatus,
    AuthorizationType,
    GovernanceIntegritySummary,
    GovernancePolicy,
    GovernanceSnapshot,
    GovernanceSubject,
    GovernanceSubjectType,
    GovernanceSummary,
    IntegrityStatus,
    ManualOverride,
    PlatformModuleState,
    PolicyEvaluation,
    PolicyEvaluationStatus,
    PolicySeverity,
    ReadinessAssessment,
    ReadinessStatus,
    ReadinessType,
    TimelineSource,
    GovernanceViolation,
    ViolationStatus,
)
from app.governance_audit.policy_engine import DeterministicPolicyEngine
from app.governance_audit.repositories import (
    AuditEventRepository,
    AuthorizationRepository,
    ManualOverrideRepository,
    PolicyEvaluationRepository,
    PolicyRepository,
    ReadinessRepository,
    ViolationRepository,
)


SNAPSHOT_VERSION = "INTERSIGNAL_GOVERNANCE_AUDIT_SNAPSHOT_V1"


class GovernanceService:
    """Governance orchestration that never mutates an owning domain record."""

    def __init__(
        self,
        *,
        authorizations: AuthorizationRepository,
        readiness: ReadinessRepository,
        policies: PolicyRepository,
        policy_evaluations: PolicyEvaluationRepository,
        violations: ViolationRepository,
        manual_overrides: ManualOverrideRepository,
        audit_events: AuditEventRepository,
        subject_store: object,
        registry_events: Sequence[RegistryEvent] = (),
        portfolio_events: Sequence[PortfolioEvent] = (),
        valid_artifact_ids: Iterable[str] | None = None,
        valid_evidence_ids: Iterable[str] | None = None,
        valid_lineage_node_ids: Iterable[str] | None = None,
    ) -> None:
        for method in ("append_subject", "get_subject", "list_subjects", "get_subject_history"):
            if not hasattr(subject_store, method):
                raise TypeError(f"Subject store lacks required method: {method}")
        self._authorizations = authorizations
        self._readiness = readiness
        self._policies = policies
        self._policy_evaluations = policy_evaluations
        self._violations = violations
        self._manual_overrides = manual_overrides
        self._audit_events = audit_events
        self._subject_store = subject_store
        self._registry_events = tuple(registry_events)
        self._portfolio_events = tuple(portfolio_events)
        self._valid_artifact_ids = (
            frozenset(valid_artifact_ids) if valid_artifact_ids is not None else None
        )
        self._valid_evidence_ids = (
            frozenset(valid_evidence_ids) if valid_evidence_ids is not None else None
        )
        self._valid_lineage_node_ids = (
            frozenset(valid_lineage_node_ids)
            if valid_lineage_node_ids is not None
            else None
        )
        self._engine = DeterministicPolicyEngine()

    @classmethod
    def from_repository(
        cls,
        repository: object,
        **kwargs: object,
    ) -> "GovernanceService":
        required = (
            AuthorizationRepository,
            ReadinessRepository,
            PolicyRepository,
            PolicyEvaluationRepository,
            ViolationRepository,
            ManualOverrideRepository,
            AuditEventRepository,
        )
        if not all(isinstance(repository, interface) for interface in required):
            raise TypeError("Repository does not implement all governance interfaces")
        return cls(
            authorizations=repository,
            readiness=repository,
            policies=repository,
            policy_evaluations=repository,
            violations=repository,
            manual_overrides=repository,
            audit_events=repository,
            subject_store=repository,
            **kwargs,
        )

    @staticmethod
    def _time(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Governance timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _subject(self, subject_id: str) -> GovernanceSubject:
        subject = self._subject_store.get_subject(subject_id)
        if subject is None:
            raise GovernanceSubjectNotFound(subject_id)
        return subject

    def _authorization(self, authorization_id: str) -> AuthorizationRecord:
        record = self._authorizations.get_authorization(authorization_id)
        if record is None:
            raise AuthorizationNotFound(authorization_id)
        return record

    def _policy(self, policy_id: str) -> GovernancePolicy:
        policy = self._policies.get_policy(policy_id)
        if policy is None:
            raise PolicyNotFound(policy_id)
        return policy

    def _violation(self, violation_id: str) -> GovernanceViolation:
        violation = self._violations.get_violation(violation_id)
        if violation is None:
            raise ViolationNotFound(violation_id)
        return violation

    def _append_generated_audit(
        self,
        *,
        event_type: AuditEventType,
        subject: GovernanceSubject,
        actor: str,
        timestamp: datetime,
        action: str,
        result: str,
        reason: str,
        authorization_id: str | None = None,
        related_artifact_ids: tuple[str, ...] = (),
        lineage_node_ids: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        occurred_at = self._time(timestamp)
        event = AuditEvent(
            audit_event_id=deterministic_id(
                "AUDIT",
                event_type,
                subject.subject_type,
                subject.subject_id,
                action,
                occurred_at,
                authorization_id,
            ),
            event_type=event_type,
            domain=subject.domain,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            actor=actor,
            timestamp=occurred_at,
            action=action,
            result=result,
            reason=reason,
            authorization_id=authorization_id,
            related_artifact_ids=related_artifact_ids,
            lineage_node_ids=lineage_node_ids,
            metadata=dict(metadata or {}),
        )
        self._audit_events.append_audit_event(event)
        return event

    # Required reads.
    def get_subject(self, subject_id: str) -> GovernanceSubject:
        return self._subject(subject_id)

    def list_subjects(self) -> list[GovernanceSubject]:
        return self._subject_store.list_subjects()

    def get_authorizations(
        self,
        *,
        subject_id: str | None = None,
        authorization_type: AuthorizationType | None = None,
    ) -> list[AuthorizationRecord]:
        rows = self._authorizations.list_authorizations()
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        if authorization_type is not None:
            rows = [row for row in rows if row.authorization_type == authorization_type]
        return rows

    def get_readiness(
        self,
        *,
        subject_id: str | None = None,
        readiness_type: ReadinessType | None = None,
    ) -> list[ReadinessAssessment]:
        rows = self._readiness.list_readiness()
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        if readiness_type is not None:
            rows = [row for row in rows if row.readiness_type == readiness_type]
        return rows

    def get_policy_evaluations(
        self,
        *,
        policy_id: str | None = None,
        subject_id: str | None = None,
    ) -> list[PolicyEvaluation]:
        rows = self._policy_evaluations.list_policy_evaluations()
        if policy_id is not None:
            rows = [row for row in rows if row.policy_id == policy_id]
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        return rows

    def get_violations(
        self,
        *,
        subject_id: str | None = None,
        status: ViolationStatus | None = None,
    ) -> list[GovernanceViolation]:
        rows = self._violations.list_violations()
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        return rows

    def get_manual_overrides(
        self, *, subject_id: str | None = None
    ) -> list[ManualOverride]:
        rows = self._manual_overrides.list_manual_overrides()
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        return rows

    def get_audit_history(
        self, *, subject_id: str | None = None
    ) -> list[AuditEvent]:
        rows = self._audit_events.list_audit_events()
        if subject_id is not None:
            rows = [row for row in rows if row.subject_id == subject_id]
        return rows

    # Supporting subject/policy writes used by deterministic foundation seeding.
    def register_subject(
        self,
        subject: GovernanceSubject,
        *,
        actor: str,
        reason: str,
        timestamp: datetime,
    ) -> GovernanceSubject:
        if self._subject_store.get_subject(subject.subject_id) is not None:
            raise ValueError(f"Governance subject already exists: {subject.subject_id}")
        self._subject_store.append_subject(subject)
        self._append_generated_audit(
            event_type=AuditEventType.PLATFORM_STATE_CHANGE,
            subject=subject,
            actor=actor,
            timestamp=timestamp,
            action="REGISTER_GOVERNANCE_SUBJECT",
            result="RECORDED",
            reason=reason,
            related_artifact_ids=subject.related_artifact_ids,
            lineage_node_ids=subject.related_lineage_ids,
        )
        return subject

    def transition_subject(
        self,
        subject_id: str,
        *,
        current_state: str,
        readiness_state: str,
        actor: str,
        reason: str,
        timestamp: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> GovernanceSubject:
        previous = self._subject(subject_id)
        updated = GovernanceSubject.model_validate(
            {
                **previous.model_dump(mode="python"),
                "current_state": current_state,
                "readiness_state": readiness_state,
                "metadata": {**previous.metadata, **dict(metadata or {})},
            }
        )
        self._subject_store.append_subject(updated)
        self._append_generated_audit(
            event_type=AuditEventType.PLATFORM_STATE_CHANGE,
            subject=updated,
            actor=actor,
            timestamp=timestamp,
            action="TRANSITION_GOVERNANCE_SUBJECT",
            result=current_state,
            reason=reason,
            metadata={"previous_state": previous.current_state},
        )
        return updated

    def register_policy(
        self,
        policy: GovernancePolicy,
        *,
        actor: str,
        reason: str,
        timestamp: datetime,
        audit_subject_id: str,
    ) -> GovernancePolicy:
        subject = self._subject(audit_subject_id)
        self._policies.add_policy(policy)
        self._append_generated_audit(
            event_type=AuditEventType.CONFIG_FREEZE,
            subject=subject,
            actor=actor,
            timestamp=timestamp,
            action=f"REGISTER_POLICY:{policy.policy_id}:{policy.version}",
            result="FROZEN",
            reason=reason,
            metadata={"policy_hash": canonical_hash(policy)},
        )
        return policy

    # Required guarded writes.
    def request_authorization(
        self,
        record: AuthorizationRecord,
    ) -> AuthorizationRecord:
        if record.status != AuthorizationStatus.REQUESTED:
            raise InvalidAuthorizationTransition("New authorization must be REQUESTED")
        subject = self._subject(record.subject_id)
        if subject.subject_type != record.subject_type:
            raise InvalidAuthorizationTransition("Authorization subject type mismatch")
        self._authorizations.append_authorization(record)
        self._append_generated_audit(
            event_type=AuditEventType.AUTHORIZATION_REQUESTED,
            subject=subject,
            actor=record.requested_by,
            timestamp=record.requested_at,
            action=f"REQUEST:{record.authorization_type.value}",
            result=record.status.value,
            reason=record.reason,
            authorization_id=record.authorization_id,
            related_artifact_ids=record.related_artifact_ids,
            metadata={"conditions": record.conditions, "expires_at": record.expires_at},
        )
        return record

    def _decide_authorization(
        self,
        authorization_id: str,
        *,
        status: AuthorizationStatus,
        decided_by: str,
        decided_at: datetime,
        reason: str,
    ) -> AuthorizationRecord:
        current = self._authorization(authorization_id)
        allowed = {
            AuthorizationStatus.REQUESTED: {
                AuthorizationStatus.APPROVED,
                AuthorizationStatus.REJECTED,
                AuthorizationStatus.NOT_REQUIRED,
            },
            AuthorizationStatus.APPROVED: {
                AuthorizationStatus.REVOKED,
                AuthorizationStatus.EXPIRED,
            },
        }
        if status not in allowed.get(current.status, set()):
            raise InvalidAuthorizationTransition(
                f"Cannot transition {current.status.value} to {status.value}"
            )
        moment = self._time(decided_at)
        if current.expires_at is not None and moment >= current.expires_at:
            raise AuthorizationExpired(authorization_id)
        updated = AuthorizationRecord.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": status,
                "approved_by": decided_by,
                "decided_at": moment,
                "reason": reason,
            }
        )
        self._authorizations.append_authorization(updated)
        subject = self._subject(updated.subject_id)
        event_type = (
            AuditEventType.AUTHORIZATION_GRANTED
            if status == AuthorizationStatus.APPROVED
            else AuditEventType.AUTHORIZATION_REJECTED
        )
        self._append_generated_audit(
            event_type=event_type,
            subject=subject,
            actor=decided_by,
            timestamp=moment,
            action=f"AUTHORIZATION_{status.value}",
            result=status.value,
            reason=reason,
            authorization_id=authorization_id,
            related_artifact_ids=updated.related_artifact_ids,
        )
        return updated

    def approve_authorization(
        self,
        authorization_id: str,
        *,
        approved_by: str,
        decided_at: datetime,
        reason: str,
    ) -> AuthorizationRecord:
        return self._decide_authorization(
            authorization_id,
            status=AuthorizationStatus.APPROVED,
            decided_by=approved_by,
            decided_at=decided_at,
            reason=reason,
        )

    def reject_authorization(
        self,
        authorization_id: str,
        *,
        rejected_by: str,
        decided_at: datetime,
        reason: str,
    ) -> AuthorizationRecord:
        return self._decide_authorization(
            authorization_id,
            status=AuthorizationStatus.REJECTED,
            decided_by=rejected_by,
            decided_at=decided_at,
            reason=reason,
        )

    def revoke_authorization(
        self,
        authorization_id: str,
        *,
        revoked_by: str,
        decided_at: datetime,
        reason: str,
    ) -> AuthorizationRecord:
        return self._decide_authorization(
            authorization_id,
            status=AuthorizationStatus.REVOKED,
            decided_by=revoked_by,
            decided_at=decided_at,
            reason=reason,
        )

    def authorization_is_active(
        self, authorization_id: str, *, at: datetime
    ) -> bool:
        record = self._authorization(authorization_id)
        moment = self._time(at)
        return record.status == AuthorizationStatus.APPROVED and (
            record.expires_at is None or moment < record.expires_at
        )

    def require_active_authorization(
        self,
        authorization_id: str,
        *,
        authorization_type: AuthorizationType,
        subject_id: str,
        at: datetime,
    ) -> AuthorizationRecord:
        record = self._authorization(authorization_id)
        if record.authorization_type != authorization_type or record.subject_id != subject_id:
            raise InvalidAuthorizationTransition("Authorization scope mismatch")
        if not self.authorization_is_active(authorization_id, at=at):
            if record.expires_at is not None and self._time(at) >= record.expires_at:
                raise AuthorizationExpired(authorization_id)
            raise InvalidAuthorizationTransition("Authorization is not approved")
        return record

    def record_readiness_assessment(
        self,
        assessment: ReadinessAssessment,
        *,
        actor: str,
        reason: str,
    ) -> ReadinessAssessment:
        subject = self._subject(assessment.subject_id)
        if subject.subject_type != assessment.subject_type:
            raise ValueError("Readiness subject type mismatch")
        self._readiness.append_readiness(assessment)
        self._append_generated_audit(
            event_type=AuditEventType.READINESS_ASSESSMENT,
            subject=subject,
            actor=actor,
            timestamp=assessment.assessed_at,
            action=f"ASSESS:{assessment.readiness_type.value}",
            result=assessment.status.value,
            reason=reason,
            related_artifact_ids=assessment.artifact_ids,
            metadata={
                "failed_criteria": assessment.failed_criteria,
                "warnings": assessment.warnings,
            },
        )
        return assessment

    def evaluate_policy(
        self,
        policy_id: str,
        *,
        subject_id: str,
        context: Mapping[str, Any],
        evaluated_at: datetime,
        related_artifacts: tuple[str, ...] = (),
    ) -> PolicyEvaluation:
        self._subject(subject_id)
        policy = self._policy(policy_id)
        return self._engine.evaluate(
            policy=policy,
            subject_id=subject_id,
            context=context,
            evaluated_at=evaluated_at,
            related_artifacts=related_artifacts,
        )

    def record_policy_evaluation(
        self,
        evaluation: PolicyEvaluation,
        *,
        actor: str,
        reason: str,
    ) -> PolicyEvaluation:
        policy = self._policy(evaluation.policy_id)
        subject = self._subject(evaluation.subject_id)
        self._policy_evaluations.append_policy_evaluation(evaluation)
        self._append_generated_audit(
            event_type=AuditEventType.POLICY_EVALUATION,
            subject=subject,
            actor=actor,
            timestamp=evaluation.evaluated_at,
            action=f"EVALUATE:{policy.policy_id}:{policy.version}",
            result=evaluation.status.value,
            reason=reason,
            related_artifact_ids=evaluation.related_artifacts,
            metadata={
                "passed_checks": evaluation.passed_checks,
                "failed_checks": evaluation.failed_checks,
            },
        )
        return evaluation

    def record_violation(
        self,
        violation: GovernanceViolation,
        *,
        actor: str,
        reason: str,
    ) -> GovernanceViolation:
        if violation.status != ViolationStatus.OPEN:
            raise ValueError("New violation must be OPEN")
        self._policy(violation.policy_id)
        subject = self._subject(violation.subject_id)
        self._violations.append_violation(violation)
        self._append_generated_audit(
            event_type=AuditEventType.VIOLATION_DETECTED,
            subject=subject,
            actor=actor,
            timestamp=violation.detected_at,
            action=f"DETECT_VIOLATION:{violation.policy_id}",
            result=violation.status.value,
            reason=reason,
            related_artifact_ids=violation.related_artifact_ids,
            metadata={"severity": violation.severity.value},
        )
        return violation

    def acknowledge_violation(
        self,
        violation_id: str,
        *,
        actor: str,
        timestamp: datetime,
        reason: str,
    ) -> GovernanceViolation:
        current = self._violation(violation_id)
        if current.status != ViolationStatus.OPEN:
            raise ValueError("Only OPEN violations may be acknowledged")
        updated = GovernanceViolation.model_validate(
            {**current.model_dump(mode="python"), "status": ViolationStatus.ACKNOWLEDGED}
        )
        self._violations.append_violation(updated)
        subject = self._subject(updated.subject_id)
        self._append_generated_audit(
            event_type=AuditEventType.VIOLATION_DETECTED,
            subject=subject,
            actor=actor,
            timestamp=timestamp,
            action="ACKNOWLEDGE_VIOLATION",
            result=updated.status.value,
            reason=reason,
            related_artifact_ids=updated.related_artifact_ids,
        )
        return updated

    def resolve_violation(
        self,
        violation_id: str,
        *,
        actor: str,
        resolved_at: datetime,
        resolution: str,
    ) -> GovernanceViolation:
        current = self._violation(violation_id)
        if current.status not in {ViolationStatus.OPEN, ViolationStatus.ACKNOWLEDGED}:
            raise ValueError("Violation is not open for resolution")
        updated = GovernanceViolation.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": ViolationStatus.RESOLVED,
                "resolved_at": resolved_at,
                "resolution": resolution,
            }
        )
        self._violations.append_violation(updated)
        subject = self._subject(updated.subject_id)
        self._append_generated_audit(
            event_type=AuditEventType.VIOLATION_RESOLVED,
            subject=subject,
            actor=actor,
            timestamp=resolved_at,
            action="RESOLVE_VIOLATION",
            result=updated.status.value,
            reason=resolution,
            related_artifact_ids=updated.related_artifact_ids,
        )
        return updated

    def waive_violation(
        self,
        violation_id: str,
        *,
        authorization_id: str,
        actor: str,
        waived_at: datetime,
        resolution: str,
    ) -> GovernanceViolation:
        current = self._violation(violation_id)
        if current.status not in {ViolationStatus.OPEN, ViolationStatus.ACKNOWLEDGED}:
            raise ValueError("Violation is not open for waiver")
        self.require_active_authorization(
            authorization_id,
            authorization_type=AuthorizationType.MANUAL_OVERRIDE,
            subject_id=current.subject_id,
            at=waived_at,
        )
        updated = GovernanceViolation.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": ViolationStatus.WAIVED,
                "resolved_at": waived_at,
                "resolution": resolution,
                "metadata": {
                    **current.metadata,
                    "waiver_authorization_id": authorization_id,
                },
            }
        )
        self._violations.append_violation(updated)
        subject = self._subject(updated.subject_id)
        self._append_generated_audit(
            event_type=AuditEventType.VIOLATION_RESOLVED,
            subject=subject,
            actor=actor,
            timestamp=waived_at,
            action="WAIVE_VIOLATION",
            result=updated.status.value,
            reason=resolution,
            authorization_id=authorization_id,
            related_artifact_ids=updated.related_artifact_ids,
        )
        return updated

    def record_manual_override(
        self,
        override: ManualOverride,
    ) -> ManualOverride:
        subject = self._subject(override.subject_id)
        authorization = self.require_active_authorization(
            override.authorization_id,
            authorization_type=AuthorizationType.MANUAL_OVERRIDE,
            subject_id=override.subject_id,
            at=override.created_at,
        )
        if authorization.approved_by != override.approved_by:
            raise InvalidOverride("Override approver must match authorization approver")
        if subject.subject_type != override.subject_type:
            raise InvalidOverride("Override subject type mismatch")
        self._manual_overrides.add_manual_override(override)
        self._append_generated_audit(
            event_type=AuditEventType.MANUAL_OVERRIDE,
            subject=subject,
            actor=override.approved_by,
            timestamp=override.created_at,
            action=override.override_type,
            result="RECORDED_ONLY_NO_DOMAIN_MUTATION",
            reason=override.reason,
            authorization_id=override.authorization_id,
            metadata={
                "before_state_hash": canonical_hash(override.before_state),
                "after_state_hash": canonical_hash(override.after_state),
            },
        )
        return override

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        subject = self._subject(event.subject_id)
        if subject.subject_type != event.subject_type:
            raise ValueError("Audit event subject type mismatch")
        if event.authorization_id is not None:
            self._authorization(event.authorization_id)
        self._audit_events.append_audit_event(event)
        return event

    # Projection and summary.
    def get_combined_audit_timeline(self) -> list[AuditTimelineEntry]:
        rows: list[AuditTimelineEntry] = []
        for event in self._registry_events:
            if event.entity_type == RegistryEntityType.STRATEGY:
                event_type = AuditEventType.STRATEGY_STATE_CHANGE.value
            elif event.entity_type in {RegistryEntityType.ARTIFACT, RegistryEntityType.EVIDENCE}:
                event_type = AuditEventType.CONFIG_FREEZE.value
            else:
                event_type = AuditEventType.PLATFORM_STATE_CHANGE.value
            rows.append(
                AuditTimelineEntry(
                    source=TimelineSource.REGISTRY,
                    source_event_id=event.event_id,
                    event_type=event_type,
                    domain="PLATFORM_REGISTRY",
                    subject_type=event.entity_type.value,
                    subject_id=event.entity_id,
                    actor=event.actor,
                    timestamp=event.created_at,
                    action=event.event_type.value,
                    result="RECORDED",
                    reason=event.reason,
                    related_artifact_ids=event.related_artifact_ids,
                    metadata={"source_metadata": event.metadata},
                )
            )
        for event in self._portfolio_events:
            rows.append(
                AuditTimelineEntry(
                    source=TimelineSource.PORTFOLIO,
                    source_event_id=event.event_id,
                    event_type=AuditEventType.PORTFOLIO_EVENT.value,
                    domain="PORTFOLIO_OS",
                    subject_type="PORTFOLIO",
                    subject_id=event.portfolio_id,
                    actor=event.actor,
                    timestamp=event.timestamp,
                    action=event.event_type.value,
                    result="RECORDED",
                    reason=event.reason,
                    metadata={
                        "entity_type": event.entity_type,
                        "entity_id": event.entity_id,
                        "source_metadata": event.metadata,
                    },
                )
            )
        for event in self._audit_events.list_audit_events():
            rows.append(
                AuditTimelineEntry(
                    source=TimelineSource.GOVERNANCE,
                    source_event_id=event.audit_event_id,
                    event_type=event.event_type.value,
                    domain=event.domain,
                    subject_type=event.subject_type.value,
                    subject_id=event.subject_id,
                    actor=event.actor,
                    timestamp=event.timestamp,
                    action=event.action,
                    result=event.result,
                    reason=event.reason,
                    authorization_id=event.authorization_id,
                    related_artifact_ids=event.related_artifact_ids,
                    lineage_node_ids=event.lineage_node_ids,
                    metadata=event.metadata,
                )
            )
        source_order = {
            TimelineSource.REGISTRY: 0,
            TimelineSource.PORTFOLIO: 1,
            TimelineSource.GOVERNANCE: 2,
        }
        return sorted(
            rows,
            key=lambda row: (
                row.timestamp,
                source_order[row.source],
                row.source_event_id,
            ),
        )

    def _latest_readiness_by_type(self) -> dict[ReadinessType, ReadinessAssessment]:
        latest: dict[ReadinessType, ReadinessAssessment] = {}
        for row in self._readiness.list_readiness():
            previous = latest.get(row.readiness_type)
            if previous is None or (row.assessed_at, row.assessment_id) > (
                previous.assessed_at,
                previous.assessment_id,
            ):
                latest[row.readiness_type] = row
        return latest

    def get_governance_summary(self) -> GovernanceSummary:
        authorizations = self._authorizations.list_authorizations()
        latest_readiness = self._latest_readiness_by_type()
        evaluations: dict[str, PolicyEvaluation] = {}
        for row in self._policy_evaluations.list_policy_evaluations():
            previous = evaluations.get(row.policy_id)
            if previous is None or (row.evaluated_at, row.evaluation_id) > (
                previous.evaluated_at,
                previous.evaluation_id,
            ):
                evaluations[row.policy_id] = row
        violations = self._violations.list_violations()
        open_states = {ViolationStatus.OPEN, ViolationStatus.ACKNOWLEDGED}
        timeline = self.get_combined_audit_timeline()
        fallback = ReadinessStatus.NOT_READY
        return GovernanceSummary(
            open_authorizations=sum(
                row.status == AuthorizationStatus.REQUESTED for row in authorizations
            ),
            approved_authorizations=sum(
                row.status == AuthorizationStatus.APPROVED for row in authorizations
            ),
            open_violations=sum(row.status in open_states for row in violations),
            blocking_violations=sum(
                row.status in open_states
                and row.severity in {PolicySeverity.BLOCKING, PolicySeverity.CRITICAL}
                for row in violations
            ),
            readiness_by_type={key: row.status for key, row in sorted(latest_readiness.items(), key=lambda item: item[0].value)},
            policy_status={key: row.status for key, row in sorted(evaluations.items())},
            latest_audit_event=timeline[-1] if timeline else None,
            production_readiness=latest_readiness.get(
                ReadinessType.PRODUCTION_READINESS
            ).status
            if ReadinessType.PRODUCTION_READINESS in latest_readiness
            else fallback,
            paper_readiness=latest_readiness.get(ReadinessType.PAPER_TRADING_READINESS).status
            if ReadinessType.PAPER_TRADING_READINESS in latest_readiness
            else fallback,
            live_readiness=latest_readiness.get(ReadinessType.LIVE_TRADING_READINESS).status
            if ReadinessType.LIVE_TRADING_READINESS in latest_readiness
            else fallback,
        )

    def get_integrity_summary(self) -> GovernanceIntegritySummary:
        subjects = {row.subject_id: row for row in self.list_subjects()}
        policies = self._policies.list_policies()
        policy_ids = {row.policy_id for row in policies}
        broken = 0
        invalid_authorizations = 0
        expired_usage = 0
        override_without_auth = 0
        external_ref_errors = 0

        def count_refs(values: Iterable[str], allowed: frozenset[str] | None) -> int:
            if allowed is None:
                return 0
            return sum(value not in allowed for value in values)

        for subject in subjects.values():
            external_ref_errors += count_refs(
                subject.related_artifact_ids, self._valid_artifact_ids
            )
            external_ref_errors += count_refs(
                subject.related_lineage_ids, self._valid_lineage_node_ids
            )
        allowed_transitions = {
            AuthorizationStatus.REQUESTED: {
                AuthorizationStatus.APPROVED,
                AuthorizationStatus.REJECTED,
                AuthorizationStatus.NOT_REQUIRED,
            },
            AuthorizationStatus.APPROVED: {
                AuthorizationStatus.REVOKED,
                AuthorizationStatus.EXPIRED,
            },
        }
        for authorization in self._authorizations.list_authorizations():
            broken += int(authorization.subject_id not in subjects)
            external_ref_errors += count_refs(
                authorization.related_artifact_ids, self._valid_artifact_ids
            )
            history = self._authorizations.get_authorization_history(
                authorization.authorization_id
            )
            if not history or history[0].status != AuthorizationStatus.REQUESTED:
                invalid_authorizations += 1
            for previous, current in zip(history, history[1:]):
                invalid_authorizations += int(
                    current.status not in allowed_transitions.get(previous.status, set())
                )
        for assessment in self._readiness.list_readiness():
            broken += int(assessment.subject_id not in subjects)
            external_ref_errors += count_refs(
                assessment.artifact_ids, self._valid_artifact_ids
            )
            external_ref_errors += count_refs(
                assessment.evidence_ids, self._valid_evidence_ids
            )
        for evaluation in self._policy_evaluations.list_policy_evaluations():
            broken += int(evaluation.subject_id not in subjects)
            broken += int(evaluation.policy_id not in policy_ids)
            external_ref_errors += count_refs(
                evaluation.related_artifacts, self._valid_artifact_ids
            )
        for violation in self._violations.list_violations():
            broken += int(violation.subject_id not in subjects)
            broken += int(violation.policy_id not in policy_ids)
            external_ref_errors += count_refs(
                violation.related_artifact_ids, self._valid_artifact_ids
            )
            if violation.status == ViolationStatus.WAIVED:
                waiver_id = violation.metadata.get("waiver_authorization_id")
                if not waiver_id:
                    override_without_auth += 1
        for override in self._manual_overrides.list_manual_overrides():
            broken += int(override.subject_id not in subjects)
            authorization = self._authorizations.get_authorization(
                override.authorization_id
            )
            if (
                authorization is None
                or authorization.status != AuthorizationStatus.APPROVED
                or authorization.authorization_type != AuthorizationType.MANUAL_OVERRIDE
                or authorization.subject_id != override.subject_id
            ):
                override_without_auth += 1
            elif authorization.expires_at is not None and override.created_at >= authorization.expires_at:
                expired_usage += 1
        audit_rows = self._audit_events.list_audit_events()
        for event in audit_rows:
            broken += int(event.subject_id not in subjects)
            external_ref_errors += count_refs(
                event.related_artifact_ids, self._valid_artifact_ids
            )
            external_ref_errors += count_refs(
                event.lineage_node_ids, self._valid_lineage_node_ids
            )
            if event.authorization_id is not None:
                authorization = self._authorizations.get_authorization(event.authorization_id)
                if authorization is None:
                    invalid_authorizations += 1
        duplicate_ids = 0
        id_groups = (
            [row.subject_id for row in self.list_subjects()],
            [row.authorization_id for row in self._authorizations.list_authorizations()],
            [row.assessment_id for row in self._readiness.list_readiness()],
            [row.evaluation_id for row in self._policy_evaluations.list_policy_evaluations()],
            [row.violation_id for row in self._violations.list_violations()],
            [row.override_id for row in self._manual_overrides.list_manual_overrides()],
            [row.audit_event_id for row in audit_rows],
        )
        for values in id_groups:
            duplicate_ids += sum(
                count - 1 for count in Counter(values).values() if count > 1
            )
        audit_sequence_errors = sum(
            audit_rows[index].timestamp < audit_rows[index - 1].timestamp
            for index in range(1, len(audit_rows))
        )
        enabled_versions: dict[str, set[str]] = defaultdict(set)
        for policy in policies:
            if policy.enabled:
                enabled_versions[policy.policy_id].add(policy.version)
        version_conflicts = sum(
            len(versions) - 1
            for versions in enabled_versions.values()
            if len(versions) > 1
        )
        repositories = {
            id(repository): repository
            for repository in (
                self._authorizations,
                self._readiness,
                self._policies,
                self._policy_evaluations,
                self._violations,
                self._manual_overrides,
                self._audit_events,
                self._subject_store,
            )
        }
        hash_mismatches = sum(
            int(getattr(repository, "hash_mismatch_count", 0))
            for repository in repositories.values()
        )
        broken += external_ref_errors
        values = (
            broken,
            invalid_authorizations,
            expired_usage,
            override_without_auth,
            duplicate_ids,
            audit_sequence_errors,
            version_conflicts,
            hash_mismatches,
        )
        return GovernanceIntegritySummary(
            broken_subject_refs=broken,
            invalid_authorization_references=invalid_authorizations,
            expired_approval_usage=expired_usage,
            override_without_authorization=override_without_auth,
            duplicate_ids=duplicate_ids,
            audit_sequence_errors=audit_sequence_errors,
            policy_version_conflicts=version_conflicts,
            hash_mismatches=hash_mismatches,
            status=IntegrityStatus.HEALTHY if not any(values) else IntegrityStatus.ERROR,
            metadata={
                "subject_count": len(subjects),
                "external_reference_errors": external_ref_errors,
            },
        )

    def require_integrity(self) -> GovernanceIntegritySummary:
        summary = self.get_integrity_summary()
        if summary.status != IntegrityStatus.HEALTHY:
            raise GovernanceIntegrityError(str(summary.model_dump(mode="json")))
        return summary

    def _module_state(self) -> tuple[PlatformModuleState, ...]:
        rows: list[PlatformModuleState] = []
        for subject in self.list_subjects():
            if subject.subject_type != GovernanceSubjectType.PLATFORM_MODULE:
                continue
            module_id = subject.metadata.get("module_id")
            command_version = subject.metadata.get("command_version")
            if not module_id or not command_version:
                continue
            rows.append(
                PlatformModuleState(
                    module_id=str(module_id),
                    status=subject.current_state,
                    command_version=str(command_version),
                    foundation_hash=subject.metadata.get("foundation_hash"),
                    metadata={
                        key: value
                        for key, value in subject.metadata.items()
                        if key not in {"module_id", "command_version", "foundation_hash"}
                    },
                )
            )
        return tuple(sorted(rows, key=lambda row: row.module_id))

    def export_governance_snapshot(self) -> GovernanceSnapshot:
        timeline = tuple(self.get_combined_audit_timeline())
        generated_at = max(
            (row.timestamp for row in timeline),
            default=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
        payload = {
            "snapshot_version": SNAPSHOT_VERSION,
            "generated_at": generated_at,
            "summary": self.get_governance_summary(),
            "subjects": tuple(self.list_subjects()),
            "authorizations": tuple(self._authorizations.list_authorizations()),
            "readiness": tuple(self._readiness.list_readiness()),
            "policies": tuple(self._policies.list_policies()),
            "policy_evaluations": tuple(
                self._policy_evaluations.list_policy_evaluations()
            ),
            "violations": tuple(self._violations.list_violations()),
            "manual_overrides": tuple(
                self._manual_overrides.list_manual_overrides()
            ),
            "audit_timeline": timeline,
            "module_state": self._module_state(),
            "integrity": self.get_integrity_summary(),
        }
        return GovernanceSnapshot(
            **payload,
            snapshot_hash=canonical_hash(payload),
        )


__all__ = ("GovernanceService", "SNAPSHOT_VERSION")

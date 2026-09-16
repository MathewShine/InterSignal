from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.platform.hashing import canonical_hash
from app.governance_audit.errors import GovernanceIntegrityError
from app.governance_audit.models import (
    AuditEvent,
    AuthorizationRecord,
    GovernanceModel,
    GovernancePolicy,
    GovernanceSubject,
    ManualOverride,
    PolicyEvaluation,
    ReadinessAssessment,
    GovernanceViolation,
)


class DuplicateGovernanceIdentity(ValueError):
    pass


class GovernanceAppendOnlyViolation(ValueError):
    pass


@runtime_checkable
class AuthorizationRepository(Protocol):
    def append_authorization(self, record: AuthorizationRecord) -> None: ...

    def get_authorization(self, authorization_id: str) -> AuthorizationRecord | None: ...

    def list_authorizations(self) -> list[AuthorizationRecord]: ...

    def get_authorization_history(
        self, authorization_id: str
    ) -> list[AuthorizationRecord]: ...


@runtime_checkable
class ReadinessRepository(Protocol):
    def append_readiness(self, assessment: ReadinessAssessment) -> None: ...

    def list_readiness(self) -> list[ReadinessAssessment]: ...

    def get_latest_readiness(
        self, subject_id: str, readiness_type: object
    ) -> ReadinessAssessment | None: ...


@runtime_checkable
class PolicyRepository(Protocol):
    def add_policy(self, policy: GovernancePolicy) -> None: ...

    def get_policy(self, policy_id: str) -> GovernancePolicy | None: ...

    def list_policies(self) -> list[GovernancePolicy]: ...


@runtime_checkable
class PolicyEvaluationRepository(Protocol):
    def append_policy_evaluation(self, evaluation: PolicyEvaluation) -> None: ...

    def list_policy_evaluations(self) -> list[PolicyEvaluation]: ...

    def get_latest_policy_evaluation(
        self, policy_id: str, subject_id: str
    ) -> PolicyEvaluation | None: ...


@runtime_checkable
class ViolationRepository(Protocol):
    def append_violation(self, violation: GovernanceViolation) -> None: ...

    def get_violation(self, violation_id: str) -> GovernanceViolation | None: ...

    def list_violations(self) -> list[GovernanceViolation]: ...

    def get_violation_history(
        self, violation_id: str
    ) -> list[GovernanceViolation]: ...


@runtime_checkable
class ManualOverrideRepository(Protocol):
    def add_manual_override(self, override: ManualOverride) -> None: ...

    def list_manual_overrides(self) -> list[ManualOverride]: ...


@runtime_checkable
class AuditEventRepository(Protocol):
    def append_audit_event(self, event: AuditEvent) -> None: ...

    def list_audit_events(self) -> list[AuditEvent]: ...


class InMemoryGovernanceRepository:
    """Append-only implementation of all Governance / Audit repositories."""

    def __init__(self) -> None:
        self._subject_history: dict[str, list[GovernanceSubject]] = defaultdict(list)
        self._authorization_history: dict[str, list[AuthorizationRecord]] = defaultdict(list)
        self._readiness: dict[str, ReadinessAssessment] = {}
        self._policies: dict[tuple[str, str], GovernancePolicy] = {}
        self._evaluations: dict[str, PolicyEvaluation] = {}
        self._violation_history: dict[str, list[GovernanceViolation]] = defaultdict(list)
        self._overrides: dict[str, ManualOverride] = {}
        self._audit_events: list[AuditEvent] = []
        self._audit_ids: set[str] = set()
        self.hash_mismatch_count = 0

    # Subject persistence is a concrete repository capability. The seven public
    # interfaces remain exactly those required by the command.
    def append_subject(self, subject: GovernanceSubject) -> None:
        history = self._subject_history[subject.subject_id]
        if history:
            previous = history[-1]
            if previous.subject_type != subject.subject_type:
                raise GovernanceAppendOnlyViolation("Subject type cannot change")
            if canonical_hash(previous) == canonical_hash(subject):
                raise DuplicateGovernanceIdentity(
                    f"Duplicate governance subject state: {subject.subject_id}"
                )
        history.append(subject)

    def get_subject(self, subject_id: str) -> GovernanceSubject | None:
        history = self._subject_history.get(subject_id, [])
        return history[-1] if history else None

    def list_subjects(self) -> list[GovernanceSubject]:
        return [self._subject_history[key][-1] for key in sorted(self._subject_history)]

    def get_subject_history(self, subject_id: str) -> list[GovernanceSubject]:
        return list(self._subject_history.get(subject_id, []))

    def append_authorization(self, record: AuthorizationRecord) -> None:
        history = self._authorization_history[record.authorization_id]
        if history:
            previous = history[-1]
            identity = (
                previous.subject_type,
                previous.subject_id,
                previous.authorization_type,
                previous.requested_by,
                previous.requested_at,
            )
            incoming = (
                record.subject_type,
                record.subject_id,
                record.authorization_type,
                record.requested_by,
                record.requested_at,
            )
            if identity != incoming:
                raise GovernanceAppendOnlyViolation(
                    "Authorization request identity cannot change"
                )
            if canonical_hash(previous) == canonical_hash(record):
                raise DuplicateGovernanceIdentity(
                    f"Duplicate authorization state: {record.authorization_id}"
                )
            previous_time = previous.decided_at or previous.requested_at
            incoming_time = record.decided_at or record.requested_at
            if incoming_time <= previous_time:
                raise GovernanceAppendOnlyViolation(
                    "Authorization transition requires a later timestamp"
                )
        history.append(record)

    def get_authorization(self, authorization_id: str) -> AuthorizationRecord | None:
        history = self._authorization_history.get(authorization_id, [])
        return history[-1] if history else None

    def list_authorizations(self) -> list[AuthorizationRecord]:
        return [
            self._authorization_history[key][-1]
            for key in sorted(self._authorization_history)
        ]

    def get_authorization_history(
        self, authorization_id: str
    ) -> list[AuthorizationRecord]:
        return list(self._authorization_history.get(authorization_id, []))

    def append_readiness(self, assessment: ReadinessAssessment) -> None:
        if assessment.assessment_id in self._readiness:
            raise DuplicateGovernanceIdentity(
                f"Duplicate readiness assessment: {assessment.assessment_id}"
            )
        latest = self.get_latest_readiness(
            assessment.subject_id, assessment.readiness_type
        )
        if latest and assessment.assessed_at <= latest.assessed_at:
            raise GovernanceAppendOnlyViolation(
                "Readiness assessment requires a later assessed_at"
            )
        self._readiness[assessment.assessment_id] = assessment

    def list_readiness(self) -> list[ReadinessAssessment]:
        return sorted(
            self._readiness.values(),
            key=lambda row: (row.assessed_at, row.assessment_id),
        )

    def get_latest_readiness(
        self, subject_id: str, readiness_type: object
    ) -> ReadinessAssessment | None:
        rows = [
            row
            for row in self._readiness.values()
            if row.subject_id == subject_id and row.readiness_type == readiness_type
        ]
        return max(rows, key=lambda row: (row.assessed_at, row.assessment_id)) if rows else None

    def add_policy(self, policy: GovernancePolicy) -> None:
        key = (policy.policy_id, policy.version)
        if key in self._policies:
            raise DuplicateGovernanceIdentity(
                f"Duplicate policy version: {policy.policy_id}:{policy.version}"
            )
        self._policies[key] = policy

    def get_policy(self, policy_id: str) -> GovernancePolicy | None:
        rows = [row for (item, _), row in self._policies.items() if item == policy_id]
        return max(rows, key=lambda row: (row.created_at, row.version)) if rows else None

    def list_policies(self) -> list[GovernancePolicy]:
        return sorted(self._policies.values(), key=lambda row: (row.policy_id, row.version))

    def append_policy_evaluation(self, evaluation: PolicyEvaluation) -> None:
        if evaluation.evaluation_id in self._evaluations:
            raise DuplicateGovernanceIdentity(
                f"Duplicate policy evaluation: {evaluation.evaluation_id}"
            )
        latest = self.get_latest_policy_evaluation(
            evaluation.policy_id, evaluation.subject_id
        )
        if latest and evaluation.evaluated_at <= latest.evaluated_at:
            raise GovernanceAppendOnlyViolation(
                "Policy evaluation requires a later evaluated_at"
            )
        self._evaluations[evaluation.evaluation_id] = evaluation

    def list_policy_evaluations(self) -> list[PolicyEvaluation]:
        return sorted(
            self._evaluations.values(),
            key=lambda row: (row.evaluated_at, row.evaluation_id),
        )

    def get_latest_policy_evaluation(
        self, policy_id: str, subject_id: str
    ) -> PolicyEvaluation | None:
        rows = [
            row
            for row in self._evaluations.values()
            if row.policy_id == policy_id and row.subject_id == subject_id
        ]
        return max(rows, key=lambda row: (row.evaluated_at, row.evaluation_id)) if rows else None

    def append_violation(self, violation: GovernanceViolation) -> None:
        history = self._violation_history[violation.violation_id]
        if history:
            previous = history[-1]
            if (
                previous.policy_id,
                previous.subject_type,
                previous.subject_id,
                previous.detected_at,
            ) != (
                violation.policy_id,
                violation.subject_type,
                violation.subject_id,
                violation.detected_at,
            ):
                raise GovernanceAppendOnlyViolation(
                    "Violation identity cannot change across history"
                )
            if canonical_hash(previous) == canonical_hash(violation):
                raise DuplicateGovernanceIdentity(
                    f"Duplicate violation state: {violation.violation_id}"
                )
        history.append(violation)

    def get_violation(self, violation_id: str) -> GovernanceViolation | None:
        history = self._violation_history.get(violation_id, [])
        return history[-1] if history else None

    def list_violations(self) -> list[GovernanceViolation]:
        return [
            self._violation_history[key][-1]
            for key in sorted(self._violation_history)
        ]

    def get_violation_history(
        self, violation_id: str
    ) -> list[GovernanceViolation]:
        return list(self._violation_history.get(violation_id, []))

    def add_manual_override(self, override: ManualOverride) -> None:
        if override.override_id in self._overrides:
            raise DuplicateGovernanceIdentity(
                f"Duplicate manual override: {override.override_id}"
            )
        self._overrides[override.override_id] = override

    def list_manual_overrides(self) -> list[ManualOverride]:
        return [self._overrides[key] for key in sorted(self._overrides)]

    def append_audit_event(self, event: AuditEvent) -> None:
        if event.audit_event_id in self._audit_ids:
            raise DuplicateGovernanceIdentity(
                f"Duplicate audit event: {event.audit_event_id}"
            )
        self._audit_events.append(event)
        self._audit_ids.add(event.audit_event_id)

    def list_audit_events(self) -> list[AuditEvent]:
        return list(self._audit_events)


class JsonFileGovernanceRepository(InMemoryGovernanceRepository):
    """Hash-verified append-only JSONL governance repository."""

    _FILES = {
        "subjects": Path("subjects/subjects.jsonl"),
        "authorizations": Path("authorizations/authorizations.jsonl"),
        "readiness": Path("readiness/readiness.jsonl"),
        "policies": Path("policies/policies.jsonl"),
        "evaluations": Path("evaluations/evaluations.jsonl"),
        "violations": Path("violations/violations.jsonl"),
        "overrides": Path("overrides/overrides.jsonl"),
        "audit": Path("audit/audit_events.jsonl"),
    }

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        super().__init__()
        self._load()

    def _path(self, kind: str) -> Path:
        return self.root / self._FILES[kind]

    def _read(self, kind: str, model: type[GovernanceModel]) -> list[GovernanceModel]:
        path = self._path(kind)
        if not path.exists():
            return []
        rows: list[GovernanceModel] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    envelope = json.loads(line)
                    record = model.model_validate(envelope["record"])
                    if envelope["record_hash"] != canonical_hash(record):
                        self.hash_mismatch_count += 1
                        raise GovernanceIntegrityError(
                            f"Governance hash mismatch in {path} line {line_number}"
                        )
                    rows.append(record)
                except (json.JSONDecodeError, KeyError, TypeError) as error:
                    self.hash_mismatch_count += 1
                    raise GovernanceIntegrityError(
                        f"Invalid governance JSONL in {path} line {line_number}"
                    ) from error
        return rows

    def _load(self) -> None:
        specs = (
            ("subjects", GovernanceSubject, super().append_subject),
            ("authorizations", AuthorizationRecord, super().append_authorization),
            ("readiness", ReadinessAssessment, super().append_readiness),
            ("policies", GovernancePolicy, super().add_policy),
            ("evaluations", PolicyEvaluation, super().append_policy_evaluation),
            ("violations", GovernanceViolation, super().append_violation),
            ("overrides", ManualOverride, super().add_manual_override),
            ("audit", AuditEvent, super().append_audit_event),
        )
        for kind, model, operation in specs:
            for record in self._read(kind, model):
                operation(record)

    def _append(self, kind: str, model: GovernanceModel) -> None:
        path = self._path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "record": model.model_dump(mode="json"),
            "record_hash": canonical_hash(model),
        }
        payload = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append_subject(self, subject: GovernanceSubject) -> None:
        super().append_subject(subject)
        self._append("subjects", subject)

    def append_authorization(self, record: AuthorizationRecord) -> None:
        super().append_authorization(record)
        self._append("authorizations", record)

    def append_readiness(self, assessment: ReadinessAssessment) -> None:
        super().append_readiness(assessment)
        self._append("readiness", assessment)

    def add_policy(self, policy: GovernancePolicy) -> None:
        super().add_policy(policy)
        self._append("policies", policy)

    def append_policy_evaluation(self, evaluation: PolicyEvaluation) -> None:
        super().append_policy_evaluation(evaluation)
        self._append("evaluations", evaluation)

    def append_violation(self, violation: GovernanceViolation) -> None:
        super().append_violation(violation)
        self._append("violations", violation)

    def add_manual_override(self, override: ManualOverride) -> None:
        super().add_manual_override(override)
        self._append("overrides", override)

    def append_audit_event(self, event: AuditEvent) -> None:
        super().append_audit_event(event)
        self._append("audit", event)


__all__ = (
    "AuditEventRepository",
    "AuthorizationRepository",
    "DuplicateGovernanceIdentity",
    "GovernanceAppendOnlyViolation",
    "InMemoryGovernanceRepository",
    "JsonFileGovernanceRepository",
    "ManualOverrideRepository",
    "PolicyEvaluationRepository",
    "PolicyRepository",
    "ReadinessRepository",
    "ViolationRepository",
)

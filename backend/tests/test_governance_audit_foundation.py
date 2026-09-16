from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.hashing import canonical_hash
from app.platform.models import RegistryEntityType, RegistryEvent, RegistryEventType
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.models import PortfolioEvent, PortfolioEventType
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.governance_audit.builder import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    MANIFEST_VERSION,
    PLATFORM_FOUNDATION_HASH,
    PORTFOLIO_OS_HASH,
    REQUIRED_CHECKPOINT,
    RESEARCH_WORKBENCH_HASH,
    prior_artifact_paths,
    verify_governance_audit_inputs,
)
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
    AuthorizationRecord,
    AuthorizationStatus,
    AuthorizationType,
    GovernancePolicy,
    GovernanceSubject,
    GovernanceSubjectType,
    IntegrityStatus,
    ManualOverride,
    PolicyEvaluationStatus,
    PolicyOperator,
    PolicyRule,
    PolicySeverity,
    ReadinessAssessment,
    ReadinessStatus,
    ReadinessType,
    TimelineSource,
    GovernanceViolation,
    ViolationStatus,
    governance_record_hash,
)
from app.governance_audit.policy_engine import DeterministicPolicyEngine
from app.governance_audit.repositories import (
    AuditEventRepository,
    AuthorizationRepository,
    DuplicateGovernanceIdentity,
    InMemoryGovernanceRepository,
    JsonFileGovernanceRepository,
    ManualOverrideRepository,
    PolicyEvaluationRepository,
    PolicyRepository,
    ReadinessRepository,
    ViolationRepository,
)
from app.governance_audit.service import GovernanceService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)


def _subject(
    subject_id: str = "SUBJECT-TEST-001",
    subject_type: GovernanceSubjectType = GovernanceSubjectType.PLATFORM_MODULE,
) -> GovernanceSubject:
    return GovernanceSubject(
        subject_type=subject_type,
        subject_id=subject_id,
        domain="TEST",
        current_state="OBSERVED",
        readiness_state="INCONCLUSIVE",
        metadata={"synthetic": True},
    )


def _service(
    *,
    repository: InMemoryGovernanceRepository | None = None,
    subject: GovernanceSubject | None = None,
    registry_events: tuple[RegistryEvent, ...] = (),
    portfolio_events: tuple[PortfolioEvent, ...] = (),
) -> tuple[GovernanceService, InMemoryGovernanceRepository]:
    store = repository or InMemoryGovernanceRepository()
    service = GovernanceService.from_repository(
        store,
        registry_events=registry_events,
        portfolio_events=portfolio_events,
    )
    subject_value = subject or _subject()
    service.register_subject(
        subject_value,
        actor="TEST",
        reason="Register synthetic governance subject",
        timestamp=T0,
    )
    return service, store


def _authorization(
    *,
    authorization_id: str = "AUTH-TEST-001",
    subject_id: str = "SUBJECT-TEST-001",
    subject_type: GovernanceSubjectType = GovernanceSubjectType.PLATFORM_MODULE,
    authorization_type: AuthorizationType = AuthorizationType.MANUAL_OVERRIDE,
    expires_at: datetime | None = None,
) -> AuthorizationRecord:
    return AuthorizationRecord(
        authorization_id=authorization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        authorization_type=authorization_type,
        status=AuthorizationStatus.REQUESTED,
        requested_by="REQUESTER",
        requested_at=T0 + timedelta(minutes=1),
        reason="Synthetic explicit request",
        conditions=("CONDITION_REMAINS_EXPLICIT",),
        expires_at=expires_at,
        metadata={"automatic_permission": False},
    )


def _policy(
    *,
    policy_id: str = "POLICY-TEST-001",
    severity: PolicySeverity = PolicySeverity.BLOCKING,
    warning_only: bool = False,
    enabled: bool = True,
) -> GovernancePolicy:
    return GovernancePolicy(
        policy_id=policy_id,
        name="Synthetic policy",
        version="V1",
        domain="TEST",
        description="Deterministic synthetic policy",
        severity=severity,
        enabled=enabled,
        rules=(
            PolicyRule(
                rule_id=f"{policy_id}:RULE",
                fact="enabled",
                operator=PolicyOperator.TRUTHY,
                message="Fact must be enabled",
                warning_only=warning_only,
            ),
        ),
        created_at=T0,
    )


def _generated_service() -> GovernanceService:
    platform = JsonFilePlatformRepository(PROJECT_ROOT / "data/platform")
    portfolio = JsonFilePortfolioOSRepository(PROJECT_ROOT / "data/platform/portfolio_os")
    governance = JsonFileGovernanceRepository(PROJECT_ROOT / "data/platform/governance")
    portfolio_events = tuple(
        event
        for row in portfolio.list_portfolios()
        for event in portfolio.list_portfolio_events(row.portfolio_id)
    )
    return GovernanceService.from_repository(
        governance,
        registry_events=tuple(platform.list_events()),
        portfolio_events=portfolio_events,
        valid_artifact_ids={row.artifact_id for row in platform.list_artifacts()},
        valid_evidence_ids={row.evidence_id for row in platform.list_evidence()},
        valid_lineage_node_ids={row.node_id for row in platform.list_lineage_nodes()},
    )


def test_command_identity_and_checkpoint_are_exact() -> None:
    assert COMMAND_VERSION == "INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_V1"
    assert COMMAND_PROFILE == "POLICY_AUTHORIZATION_READINESS_AUDIT_V1"
    assert MANIFEST_VERSION == "INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_MANIFEST_V1"
    assert REQUIRED_CHECKPOINT == "0f7936bd482b05758546b2ce58915a93aeab7e02"
    assert PLATFORM_FOUNDATION_HASH == "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
    assert RESEARCH_WORKBENCH_HASH == "c0c1ba634f584b4532e99e4f015be83e7e0c069eafb3cd5ca6a1fc7cfaf8f52b"
    assert PORTFOLIO_OS_HASH == "6941ae2713b707908106ffb8d50be113d181e9339fd3e030338b2da637f026de"


def test_input_verifier_accepts_checkpoint_and_three_prior_hashes() -> None:
    inputs = verify_governance_audit_inputs(PROJECT_ROOT)
    assert inputs["head"] == REQUIRED_CHECKPOINT
    assert inputs["platform"]["platform_foundation_hash"] == PLATFORM_FOUNDATION_HASH
    assert inputs["workbench"]["research_workbench_backend_hash"] == RESEARCH_WORKBENCH_HASH
    assert inputs["portfolio"]["portfolio_os_foundation_hash"] == PORTFOLIO_OS_HASH


def test_subject_model_is_immutable_and_complete() -> None:
    subject = _subject()
    assert subject.subject_type == GovernanceSubjectType.PLATFORM_MODULE
    assert subject.current_state == "OBSERVED"
    with pytest.raises(ValidationError):
        subject.current_state = "CHANGED"


def test_authorization_statuses_and_types_are_complete() -> None:
    assert {row.value for row in AuthorizationStatus} == {
        "REQUESTED", "APPROVED", "REJECTED", "REVOKED", "EXPIRED", "NOT_REQUIRED"
    }
    assert {row.value for row in AuthorizationType} == {
        "RESEARCH_RUN", "VALIDATION_RUN", "POST_OUTCOME_EVALUATION",
        "DATA_ACQUISITION", "BROKER_CONNECTION", "SHADOW_MODE", "PAPER_TRADING",
        "LIVE_TRADING", "MANUAL_OVERRIDE", "STRATEGY_PROMOTION", "PRODUCTION_ENABLEMENT",
    }


def test_authorization_model_rejects_decision_fields_on_request() -> None:
    data = _authorization().model_dump(mode="python")
    data["approved_by"] = "APPROVER"
    with pytest.raises(ValidationError):
        AuthorizationRecord.model_validate(data)


def test_request_and_approval_append_history_and_audit() -> None:
    service, store = _service()
    requested = service.request_authorization(_authorization())
    approved = service.approve_authorization(
        requested.authorization_id,
        approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=2),
        reason="Explicit approval",
    )
    assert approved.status == AuthorizationStatus.APPROVED
    assert len(store.get_authorization_history(requested.authorization_id)) == 2
    assert [row.event_type for row in service.get_audit_history()][-2:] == [
        AuditEventType.AUTHORIZATION_REQUESTED,
        AuditEventType.AUTHORIZATION_GRANTED,
    ]


def test_rejection_and_invalid_transition() -> None:
    service, _ = _service()
    requested = service.request_authorization(_authorization())
    rejected = service.reject_authorization(
        requested.authorization_id,
        rejected_by="REVIEWER",
        decided_at=T0 + timedelta(minutes=2),
        reason="Rejected",
    )
    assert rejected.status == AuthorizationStatus.REJECTED
    with pytest.raises(InvalidAuthorizationTransition):
        service.approve_authorization(
            requested.authorization_id,
            approved_by="APPROVER",
            decided_at=T0 + timedelta(minutes=3),
            reason="Cannot reverse rejection",
        )


def test_approved_authorization_can_be_revoked() -> None:
    service, _ = _service()
    requested = service.request_authorization(_authorization())
    service.approve_authorization(
        requested.authorization_id,
        approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=2),
        reason="Approve",
    )
    revoked = service.revoke_authorization(
        requested.authorization_id,
        revoked_by="APPROVER",
        decided_at=T0 + timedelta(minutes=3),
        reason="Revoke",
    )
    assert revoked.status == AuthorizationStatus.REVOKED
    assert not service.authorization_is_active(
        requested.authorization_id, at=T0 + timedelta(minutes=4)
    )


def test_expired_authorization_cannot_be_used() -> None:
    service, _ = _service()
    requested = service.request_authorization(
        _authorization(expires_at=T0 + timedelta(minutes=5))
    )
    service.approve_authorization(
        requested.authorization_id,
        approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=2),
        reason="Temporary approval",
    )
    with pytest.raises(AuthorizationExpired):
        service.require_active_authorization(
            requested.authorization_id,
            authorization_type=AuthorizationType.MANUAL_OVERRIDE,
            subject_id="SUBJECT-TEST-001",
            at=T0 + timedelta(minutes=5),
        )


def test_conditions_are_explicit_and_not_implicitly_satisfied() -> None:
    service, _ = _service()
    requested = service.request_authorization(_authorization())
    assert requested.conditions == ("CONDITION_REMAINS_EXPLICIT",)
    assert requested.status == AuthorizationStatus.REQUESTED
    assert not service.authorization_is_active(
        requested.authorization_id, at=T0 + timedelta(minutes=2)
    )


def test_readiness_types_and_statuses_are_complete() -> None:
    assert {row.value for row in ReadinessStatus} == {
        "READY", "READY_WITH_LIMITATIONS", "NOT_READY", "BLOCKED", "INCONCLUSIVE"
    }
    assert "LIVE_TRADING_READINESS" in {row.value for row in ReadinessType}
    assert "PLATFORM_MODULE_READINESS" in {row.value for row in ReadinessType}


def test_readiness_requires_exact_failed_criteria() -> None:
    with pytest.raises(ValidationError):
        ReadinessAssessment(
            assessment_id="R",
            subject_type=GovernanceSubjectType.PLATFORM_MODULE,
            subject_id="S",
            readiness_type=ReadinessType.PLATFORM_MODULE_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={"required": False},
            failed_criteria=(),
            assessed_at=T0,
        )


def test_readiness_write_appends_audit() -> None:
    service, _ = _service()
    assessment = ReadinessAssessment(
        assessment_id="READINESS-TEST",
        subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001",
        readiness_type=ReadinessType.PLATFORM_MODULE_READINESS,
        status=ReadinessStatus.READY_WITH_LIMITATIONS,
        criteria={"foundation_exists": True},
        warnings=("LIMITED",),
        assessed_at=T0 + timedelta(minutes=1),
    )
    service.record_readiness_assessment(assessment, actor="TEST", reason="Assess")
    assert service.get_readiness(subject_id="SUBJECT-TEST-001") == [assessment]
    assert service.get_audit_history()[-1].event_type == AuditEventType.READINESS_ASSESSMENT


def test_policy_engine_pass_block_warning_and_missing() -> None:
    engine = DeterministicPolicyEngine()
    passed = engine.evaluate(
        policy=_policy(), subject_id="S", context={"enabled": True},
        evaluated_at=T0
    )
    blocked = engine.evaluate(
        policy=_policy(policy_id="BLOCK"), subject_id="S", context={"enabled": False},
        evaluated_at=T0
    )
    warning = engine.evaluate(
        policy=_policy(policy_id="WARN", severity=PolicySeverity.WARNING, warning_only=True),
        subject_id="S", context={"enabled": False}, evaluated_at=T0
    )
    missing = engine.evaluate(
        policy=_policy(policy_id="MISS"), subject_id="S", context={}, evaluated_at=T0
    )
    assert passed.status == PolicyEvaluationStatus.PASS
    assert blocked.status == PolicyEvaluationStatus.BLOCKED
    assert warning.status == PolicyEvaluationStatus.PASS_WITH_WARNINGS
    assert missing.status == PolicyEvaluationStatus.INCONCLUSIVE


def test_policy_service_records_evaluation_and_audit() -> None:
    service, _ = _service()
    policy = _policy()
    service.register_policy(
        policy, actor="TEST", reason="Freeze", timestamp=T0 + timedelta(minutes=1),
        audit_subject_id="SUBJECT-TEST-001"
    )
    evaluation = service.evaluate_policy(
        policy.policy_id, subject_id="SUBJECT-TEST-001", context={"enabled": True},
        evaluated_at=T0 + timedelta(minutes=2)
    )
    service.record_policy_evaluation(evaluation, actor="TEST", reason="Evaluate")
    assert service.get_policy_evaluations(policy_id=policy.policy_id) == [evaluation]
    assert service.get_audit_history()[-1].event_type == AuditEventType.POLICY_EVALUATION


def test_violation_lifecycle_is_append_only() -> None:
    service, store = _service()
    service.register_policy(
        _policy(), actor="TEST", reason="Freeze", timestamp=T0 + timedelta(minutes=1),
        audit_subject_id="SUBJECT-TEST-001"
    )
    violation = GovernanceViolation(
        violation_id="VIOLATION-TEST",
        policy_id="POLICY-TEST-001",
        subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001",
        severity=PolicySeverity.MATERIAL,
        status=ViolationStatus.OPEN,
        description="Synthetic finding",
        detected_at=T0 + timedelta(minutes=2),
    )
    service.record_violation(violation, actor="TEST", reason="Detected")
    service.acknowledge_violation(
        violation.violation_id, actor="OWNER", timestamp=T0 + timedelta(minutes=3),
        reason="Acknowledged"
    )
    resolved = service.resolve_violation(
        violation.violation_id, actor="OWNER", resolved_at=T0 + timedelta(minutes=4),
        resolution="Resolved with evidence"
    )
    assert resolved.status == ViolationStatus.RESOLVED
    assert len(store.get_violation_history(violation.violation_id)) == 3
    assert service.get_audit_history()[-1].event_type == AuditEventType.VIOLATION_RESOLVED


def test_waiver_requires_explicit_manual_override_authorization() -> None:
    service, _ = _service()
    service.register_policy(
        _policy(), actor="TEST", reason="Freeze", timestamp=T0 + timedelta(minutes=1),
        audit_subject_id="SUBJECT-TEST-001"
    )
    violation = GovernanceViolation(
        violation_id="V-WAIVE", policy_id="POLICY-TEST-001",
        subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001", severity=PolicySeverity.WARNING,
        status=ViolationStatus.OPEN, description="Synthetic", detected_at=T0 + timedelta(minutes=2)
    )
    service.record_violation(violation, actor="TEST", reason="Detected")
    with pytest.raises(AuthorizationNotFound):
        service.waive_violation(
            violation.violation_id, authorization_id="MISSING", actor="OWNER",
            waived_at=T0 + timedelta(minutes=3), resolution="No authorization"
        )
    request = service.request_authorization(
        _authorization(authorization_id="AUTH-WAIVER")
    )
    service.approve_authorization(
        request.authorization_id, approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=3), reason="Explicit waiver authority"
    )
    waived = service.waive_violation(
        violation.violation_id, authorization_id=request.authorization_id,
        actor="APPROVER", waived_at=T0 + timedelta(minutes=4), resolution="Accepted limitation"
    )
    assert waived.status == ViolationStatus.WAIVED
    assert waived.metadata["waiver_authorization_id"] == request.authorization_id


def test_manual_override_requires_authorization_and_does_not_mutate_subject() -> None:
    service, _ = _service()
    before = service.get_subject("SUBJECT-TEST-001")
    override = ManualOverride(
        override_id="OVERRIDE-TEST",
        subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001",
        override_type="RECORD_EXCEPTION",
        requested_by="REQUESTER",
        approved_by="APPROVER",
        reason="Synthetic exception",
        before_state={"state": "A"},
        after_state={"state": "B"},
        created_at=T0 + timedelta(minutes=3),
        authorization_id="AUTH-OVERRIDE",
    )
    with pytest.raises(AuthorizationNotFound):
        service.record_manual_override(override)
    request = service.request_authorization(
        _authorization(authorization_id="AUTH-OVERRIDE")
    )
    service.approve_authorization(
        request.authorization_id, approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=2), reason="Approve override record"
    )
    service.record_manual_override(override)
    assert service.get_subject("SUBJECT-TEST-001") == before
    assert service.get_manual_overrides() == [override]


def test_override_approver_must_match_authorization() -> None:
    service, _ = _service()
    request = service.request_authorization(_authorization())
    service.approve_authorization(
        request.authorization_id, approved_by="APPROVER",
        decided_at=T0 + timedelta(minutes=2), reason="Approve"
    )
    override = ManualOverride(
        override_id="BAD-OVERRIDE", subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001", override_type="TEST", requested_by="REQUESTER",
        approved_by="OTHER", reason="Mismatch", before_state={"x": 1},
        after_state={"x": 2}, created_at=T0 + timedelta(minutes=3),
        authorization_id=request.authorization_id
    )
    with pytest.raises(InvalidOverride):
        service.record_manual_override(override)


def test_append_only_audit_rejects_duplicate_id() -> None:
    service, _ = _service()
    event = AuditEvent(
        audit_event_id="AUDIT-EXTERNAL", event_type=AuditEventType.PLATFORM_STATE_CHANGE,
        domain="TEST", subject_type=GovernanceSubjectType.PLATFORM_MODULE,
        subject_id="SUBJECT-TEST-001", actor="TEST", timestamp=T0 + timedelta(minutes=1),
        action="OBSERVE", result="RECORDED", reason="Synthetic"
    )
    service.append_audit_event(event)
    with pytest.raises(DuplicateGovernanceIdentity):
        service.append_audit_event(event)


def test_seven_repository_interfaces_are_implemented() -> None:
    repository = InMemoryGovernanceRepository()
    interfaces = (
        AuthorizationRepository, ReadinessRepository, PolicyRepository,
        PolicyEvaluationRepository, ViolationRepository, ManualOverrideRepository,
        AuditEventRepository,
    )
    assert all(isinstance(repository, interface) for interface in interfaces)


def test_jsonl_repository_round_trip_and_hash_envelopes(tmp_path: Path) -> None:
    root = tmp_path / "governance"
    repository = JsonFileGovernanceRepository(root)
    service, _ = _service(repository=repository)
    service.request_authorization(_authorization())
    restored = GovernanceService.from_repository(JsonFileGovernanceRepository(root))
    assert restored.get_subject("SUBJECT-TEST-001").current_state == "OBSERVED"
    assert restored.get_authorizations()[0].status == AuthorizationStatus.REQUESTED
    envelope = json.loads((root / "subjects/subjects.jsonl").read_text().splitlines()[0])
    assert len(envelope["record_hash"]) == 64
    assert "record" in envelope


def test_jsonl_repository_rejects_hash_tampering(tmp_path: Path) -> None:
    root = tmp_path / "governance"
    repository = JsonFileGovernanceRepository(root)
    _service(repository=repository)
    path = root / "subjects/subjects.jsonl"
    envelope = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    envelope["record"]["current_state"] = "TAMPERED"
    path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    with pytest.raises(GovernanceIntegrityError):
        JsonFileGovernanceRepository(root)


def test_registry_event_projection_is_read_only() -> None:
    registry_event = RegistryEvent(
        event_id="REG-1", entity_type=RegistryEntityType.STRATEGY,
        entity_id="FAMILY-X", event_type=RegistryEventType.TRANSITIONED,
        new_state={"status": "PAUSED"}, actor="TEST", reason="Projection",
        created_at=T0
    )
    service, _ = _service(registry_events=(registry_event,))
    projected = [row for row in service.get_combined_audit_timeline() if row.source == TimelineSource.REGISTRY]
    assert projected[0].event_type == AuditEventType.STRATEGY_STATE_CHANGE.value
    assert registry_event.new_state == {"status": "PAUSED"}


def test_portfolio_event_projection_is_read_only() -> None:
    portfolio_event = PortfolioEvent(
        event_id="PORT-EVENT-1", portfolio_id="PORT-X",
        event_type=PortfolioEventType.TRANSACTION_RECORDED,
        entity_type="PortfolioTransaction", entity_id="TXN-X", actor="TEST",
        timestamp=T0, reason="Projection"
    )
    service, _ = _service(portfolio_events=(portfolio_event,))
    projected = [row for row in service.get_combined_audit_timeline() if row.source == TimelineSource.PORTFOLIO]
    assert projected[0].event_type == AuditEventType.PORTFOLIO_EVENT.value
    assert projected[0].metadata["entity_id"] == "TXN-X"
    assert portfolio_event.entity_id == "TXN-X"


def test_combined_timeline_has_deterministic_source_order() -> None:
    registry_event = RegistryEvent(
        event_id="REG-1", entity_type=RegistryEntityType.ARTIFACT, entity_id="ART-1",
        event_type=RegistryEventType.REGISTERED, new_state={"state": "A"}, actor="TEST",
        reason="Registry", created_at=T0
    )
    portfolio_event = PortfolioEvent(
        event_id="PORT-1", portfolio_id="P", event_type=PortfolioEventType.PORTFOLIO_CREATED,
        entity_type="Portfolio", entity_id="P", actor="TEST", timestamp=T0, reason="Portfolio"
    )
    service, _ = _service(registry_events=(registry_event,), portfolio_events=(portfolio_event,))
    sources = [row.source for row in service.get_combined_audit_timeline()[:3]]
    assert sources == [TimelineSource.REGISTRY, TimelineSource.PORTFOLIO, TimelineSource.GOVERNANCE]


def test_generated_core_policies_all_pass() -> None:
    service = _generated_service()
    evaluations = service.get_policy_evaluations()
    assert len(evaluations) == 8
    assert {row.status for row in evaluations} == {PolicyEvaluationStatus.PASS}
    assert {row.policy_id for row in evaluations} == {
        "NO_LIVE_WITHOUT_VALIDATED_STRATEGY",
        "NO_PAPER_WITHOUT_APPROVED_CANDIDATE",
        "NO_BROKER_CONNECTION_WITHOUT_AUTHORIZATION",
        "NO_DATA_ACQUISITION_WITHOUT_AUTHORIZATION",
        "NO_STRATEGY_PROMOTION_WITHOUT_VALIDATION",
        "NO_POST_OUTCOME_AS_PRISTINE_VALIDATION",
        "NO_PRODUCTION_WITH_OPEN_BLOCKING_VIOLATIONS",
        "NO_DESTRUCTIVE_RESEARCH_MUTATION",
    }


def test_family_a_formal_and_post_outcome_distinction() -> None:
    subject = _generated_service().get_subject("VALIDATION-FAMILY-A")
    history = subject.metadata["validation_history"]
    assert [row["classification"] for row in history] == [
        "FORMAL", "INVALIDATED_ATTEMPT", "CA_AUDIT", "CA_REMEDIATION", "POST_OUTCOME"
    ]
    assert history[0]["status"] == "INCONCLUSIVE"
    assert history[-1]["status"] == "UNSUPPORTIVE"
    assert subject.metadata["post_outcome_pristine_holdout"] is False


def test_family_d_and_f_blocker_projections() -> None:
    service = _generated_service()
    family_d = service.get_subject("FAMILY_D")
    family_f = service.get_subject("FAMILY_F")
    assert family_d.current_state == "DATA_BLOCKED"
    assert family_d.metadata["interpretation"] == "DATA_BLOCKED_NOT_STRATEGY_FAILURE"
    assert family_d.metadata["resume_requirements"]
    assert family_f.current_state == "SOURCE_BLOCKED"
    assert family_f.metadata["historical_acquisition_approved"] is False
    requests = service.get_authorizations(subject_id="DATA-SOURCE-CATALYST-HISTORY")
    assert requests[0].status == AuthorizationStatus.REQUESTED


def test_current_readiness_gates_are_not_ready() -> None:
    summary = _generated_service().get_governance_summary()
    assert summary.paper_readiness == ReadinessStatus.NOT_READY
    assert summary.live_readiness == ReadinessStatus.NOT_READY
    assert summary.production_readiness == ReadinessStatus.NOT_READY
    assert summary.readiness_by_type[ReadinessType.BROKER_READINESS] == ReadinessStatus.NOT_READY
    assert summary.readiness_by_type[ReadinessType.PLATFORM_MODULE_READINESS] == ReadinessStatus.READY_WITH_LIMITATIONS


def test_governance_summary_has_no_automatic_permission() -> None:
    summary = _generated_service().get_governance_summary()
    assert summary.open_authorizations == 1
    assert summary.approved_authorizations == 0
    assert summary.open_violations == 0
    assert summary.blocking_violations == 0
    assert set(summary.policy_status.values()) == {PolicyEvaluationStatus.PASS}


def test_platform_module_states_are_current() -> None:
    snapshot = _generated_service().export_governance_snapshot()
    states = {row.module_id: row.status for row in snapshot.module_state}
    assert states == {
        "04.01": "COMPLETE",
        "04.02": "COMPLETE",
        "04.03": "COMPLETE",
        "04.04": "COMPLETE",
        "04.05": "NOT_STARTED",
    }


def test_generated_combined_timeline_contains_all_three_sources() -> None:
    timeline = _generated_service().get_combined_audit_timeline()
    assert len(timeline) == 159
    assert {row.source for row in timeline} == {
        TimelineSource.REGISTRY,
        TimelineSource.PORTFOLIO,
        TimelineSource.GOVERNANCE,
    }
    assert all(timeline[index].timestamp <= timeline[index + 1].timestamp for index in range(len(timeline) - 1))


def test_snapshot_export_and_integrity_are_healthy() -> None:
    snapshot = _generated_service().export_governance_snapshot()
    integrity = snapshot.integrity
    assert integrity.status == IntegrityStatus.HEALTHY
    assert integrity.broken_subject_refs == 0
    assert integrity.invalid_authorization_references == 0
    assert integrity.expired_approval_usage == 0
    assert integrity.override_without_authorization == 0
    assert integrity.duplicate_ids == 0
    assert integrity.audit_sequence_errors == 0
    assert integrity.policy_version_conflicts == 0
    assert integrity.hash_mismatches == 0
    assert len(snapshot.snapshot_hash) == 64


def test_exported_snapshot_hash_is_reproducible_from_saved_document() -> None:
    path = PROJECT_ROOT / "data/platform/governance/governance_snapshot_v1.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    recorded = snapshot.pop("snapshot_hash")
    assert recorded == canonical_hash(snapshot)


def test_governance_record_hash_uses_canonical_sha256() -> None:
    subject = _subject()
    assert governance_record_hash(subject) == canonical_hash(subject)
    assert len(governance_record_hash(subject)) == 64


def test_generated_manifest_hash_and_prior_immutability() -> None:
    path = PROJECT_ROOT / "data/platform/manifests/intersignal_governance_audit_foundation_manifest_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    recorded = manifest.pop("governance_audit_foundation_hash")
    assert recorded == canonical_hash(manifest)
    assert manifest["integrity"]["status"] == "HEALTHY"
    assert manifest["existing_platform_artifacts_unchanged"]["unchanged"] is True
    for relative in prior_artifact_paths(PROJECT_ROOT):
        assert (PROJECT_ROOT / relative).is_file()


def test_reports_and_documentation_exist() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "data/platform/manifests/intersignal_governance_audit_foundation_manifest_v1.json").read_text(encoding="utf-8")
    )
    for report in manifest["reports"]:
        assert (PROJECT_ROOT / "data/reports" / report).is_file()
    for document in manifest["documentation"]:
        assert (PROJECT_ROOT / document).is_file()


def test_generated_state_has_zero_activation_or_external_writes() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "data/platform/manifests/intersignal_governance_audit_foundation_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["security"] == {
        "broker_calls": 0, "credentials_written": 0, "external_writes": 0,
        "live_orders": 0, "live_signals": 0, "migrations": 0,
        "network_required": False, "supabase_writes": 0,
    }
    assert manifest["direct_domain_mutations"] == 0
    assert manifest["ui_implemented"] is False
    assert manifest["broker_connected"] is False
    assert manifest["real_time_feed_added"] is False
    assert manifest["paper_trading_started"] is False
    assert manifest["live_trading_started"] is False
    assert manifest["strategy_v2_created"] is False


def test_stable_not_found_errors() -> None:
    service = GovernanceService.from_repository(InMemoryGovernanceRepository())
    with pytest.raises(GovernanceSubjectNotFound):
        service.get_subject("MISSING")
    with pytest.raises(AuthorizationNotFound):
        service.approve_authorization(
            "MISSING", approved_by="X", decided_at=T0, reason="Missing"
        )
    service.register_subject(
        _subject(),
        actor="TEST",
        reason="Register subject for policy lookup",
        timestamp=T0,
    )
    with pytest.raises(PolicyNotFound):
        service.evaluate_policy(
            "MISSING",
            subject_id="SUBJECT-TEST-001",
            context={},
            evaluated_at=T0,
        )
    with pytest.raises(ViolationNotFound):
        service.resolve_violation(
            "MISSING", actor="X", resolved_at=T0, resolution="Missing"
        )


def test_audit_event_types_are_complete() -> None:
    assert {row.value for row in AuditEventType} == {
        "DATA_INGEST", "RESEARCH_RUN", "CONFIG_FREEZE", "AUTHORIZATION_REQUESTED",
        "AUTHORIZATION_GRANTED", "AUTHORIZATION_REJECTED", "VALIDATION_RUN",
        "STRATEGY_STATE_CHANGE", "PORTFOLIO_EVENT", "BROKER_ACTION", "MANUAL_OVERRIDE",
        "POLICY_EVALUATION", "VIOLATION_DETECTED", "VIOLATION_RESOLVED",
        "READINESS_ASSESSMENT", "PLATFORM_STATE_CHANGE",
    }

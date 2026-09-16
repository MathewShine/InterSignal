from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.platform.hashing import deterministic_id
from app.platform.repositories import InMemoryPlatformRepository
from app.portfolio_os.repositories import InMemoryPortfolioOSRepository
from app.governance_audit.models import (
    AuthorizationRecord,
    AuthorizationStatus,
    AuthorizationType,
    GovernancePolicy,
    GovernanceSubject,
    GovernanceSubjectType,
    PolicyOperator,
    PolicyRule,
    PolicySeverity,
    ReadinessAssessment,
    ReadinessStatus,
    ReadinessType,
)
from app.governance_audit.service import GovernanceService


SEED_BASE_TIME = datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc)
SEED_ACTOR = "SYSTEM_GOVERNANCE_PROJECTION"


def _time(minutes: int) -> datetime:
    return SEED_BASE_TIME + timedelta(minutes=minutes)


def _subject(
    subject_type: GovernanceSubjectType,
    subject_id: str,
    domain: str,
    current_state: str,
    readiness_state: str,
    *,
    artifacts: tuple[str, ...] = (),
    lineage: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> GovernanceSubject:
    return GovernanceSubject(
        subject_type=subject_type,
        subject_id=subject_id,
        domain=domain,
        current_state=current_state,
        readiness_state=readiness_state,
        related_artifact_ids=artifacts,
        related_lineage_ids=lineage,
        metadata=dict(metadata or {}),
    )


def _register(
    service: GovernanceService,
    subject: GovernanceSubject,
    minute: int,
    reason: str,
) -> None:
    service.register_subject(
        subject,
        actor=SEED_ACTOR,
        reason=reason,
        timestamp=_time(minute),
    )


def _policy(
    policy_id: str,
    name: str,
    domain: str,
    description: str,
    severity: PolicySeverity,
    fact: str,
    operator: PolicyOperator,
    expected: Any,
    message: str,
    minute: int,
) -> GovernancePolicy:
    return GovernancePolicy(
        policy_id=policy_id,
        name=name,
        version="V1",
        domain=domain,
        description=description,
        severity=severity,
        enabled=True,
        rules=(
            PolicyRule(
                rule_id=f"{policy_id}:RULE-001",
                fact=fact,
                operator=operator,
                expected=expected,
                message=message,
            ),
        ),
        created_at=_time(minute),
        metadata={"declarative": True, "automatic_authorization": False},
    )


def seed_current_governance_state(
    service: GovernanceService,
    *,
    platform_repository: InMemoryPlatformRepository,
    portfolio_repository: InMemoryPortfolioOSRepository,
    workbench_snapshot: Mapping[str, Any],
    platform_foundation_hash: str,
    research_workbench_hash: str,
    portfolio_os_hash: str,
) -> dict[str, Any]:
    strategies = {row.strategy_id: row for row in platform_repository.list_strategies()}
    evidence = {row.evidence_id: row for row in platform_repository.list_evidence()}
    blocked = {
        row["family_id"]: row for row in workbench_snapshot["blocked_studies"]
    }
    family_a = strategies["FAMILY_A"]
    family_d = strategies["FAMILY_D"]
    family_f = strategies["FAMILY_F"]
    formal = evidence["EVIDENCE-A-FORMAL-VALIDATION-001"]
    post_outcome = evidence["EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001"]

    subjects = (
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "PLATFORM-CORE",
            "PLATFORM",
            "ACTIVE_FOUNDATION_BUILD",
            "READY_WITH_LIMITATIONS",
            metadata={"governance_principle": ["OBSERVE", "VALIDATE", "AUTHORIZE", "RECORD"]},
        ),
        _subject(
            GovernanceSubjectType.RESEARCH_PROGRAM,
            "RESEARCH-PROGRAM-A-TO-G",
            "RESEARCH",
            "PAUSED",
            "NOT_READY",
            metadata={
                "a_to_g": "COMPLETE_NO_VALIDATED_STRATEGY",
                "strategy_v2": "NOT_CREATED",
                "family_h": "NOT_PLANNED",
                "active_discovery": False,
            },
        ),
        _subject(
            GovernanceSubjectType.STRATEGY,
            "FAMILY_A",
            "RESEARCH",
            "CLOSED_NOT_ADVANCED",
            "NOT_READY",
            artifacts=tuple(family_a.metadata.get("source_artifact_ids", ())),
            lineage=tuple(sorted({*formal.lineage_node_ids, *post_outcome.lineage_node_ids})),
            metadata={
                "formal_validation": "INCONCLUSIVE",
                "post_outcome_evidence": "UNSUPPORTIVE",
                "production_advancement": "NO",
                "promotion_allowed": False,
            },
        ),
        _subject(
            GovernanceSubjectType.VALIDATION,
            "VALIDATION-FAMILY-A",
            "RESEARCH",
            "INCONCLUSIVE_WITH_UNSUPPORTIVE_POST_OUTCOME_EVIDENCE",
            "NOT_READY",
            artifacts=tuple(sorted({*formal.source_artifact_ids, *post_outcome.source_artifact_ids})),
            lineage=tuple(sorted({*formal.lineage_node_ids, *post_outcome.lineage_node_ids})),
            metadata={
                "validation_history": [
                    {"classification": "FORMAL", "status": "INCONCLUSIVE"},
                    {
                        "classification": "INVALIDATED_ATTEMPT",
                        "status": "SERIALIZER_INVALIDATION_RECORDED",
                    },
                    {
                        "classification": "CA_AUDIT",
                        "status": "IMPLEMENTATION_LOGIC_DEFECT",
                    },
                    {
                        "classification": "CA_REMEDIATION",
                        "status": "FIX_VERIFIED_STRUCTURALLY",
                    },
                    {"classification": "POST_OUTCOME", "status": "UNSUPPORTIVE"},
                ],
                "formal_one_shot_replaced": False,
                "post_outcome_pristine_holdout": False,
            },
        ),
        _subject(
            GovernanceSubjectType.STRATEGY,
            "FAMILY_D",
            "RESEARCH",
            "DATA_BLOCKED",
            "BLOCKED",
            artifacts=tuple(family_d.metadata.get("source_artifact_ids", ())),
            metadata={
                "resume_requirements": blocked["D"]["resume_requirements"],
                "block_reason": blocked["D"]["reason"],
                "interpretation": "DATA_BLOCKED_NOT_STRATEGY_FAILURE",
            },
        ),
        _subject(
            GovernanceSubjectType.DATA_SOURCE,
            "DATA-SOURCE-INTRADAY-CONTINUITY",
            "DATA",
            "DATA_BLOCKED",
            "BLOCKED",
            artifacts=tuple(blocked["D"]["related_artifacts"]),
            metadata={
                "resume_requirements": blocked["D"]["resume_requirements"],
                "acquisition_running": False,
            },
        ),
        _subject(
            GovernanceSubjectType.STRATEGY,
            "FAMILY_F",
            "RESEARCH",
            "SOURCE_BLOCKED",
            "BLOCKED",
            artifacts=tuple(family_f.metadata.get("source_artifact_ids", ())),
            metadata={
                "resume_requirements": blocked["F"]["resume_requirements"],
                "block_reason": blocked["F"]["reason"],
                "interpretation": "SOURCE_BLOCKED_NOT_STRATEGY_FAILURE",
                "historical_acquisition_approved": False,
            },
        ),
        _subject(
            GovernanceSubjectType.DATA_SOURCE,
            "DATA-SOURCE-CATALYST-HISTORY",
            "DATA",
            "SOURCE_BLOCKED",
            "BLOCKED",
            artifacts=tuple(blocked["F"]["related_artifacts"]),
            metadata={
                "resume_requirements": blocked["F"]["resume_requirements"],
                "required_authorization": AuthorizationType.DATA_ACQUISITION.value,
                "licensing_gate": True,
                "acquisition_running": False,
            },
        ),
        _subject(
            GovernanceSubjectType.BROKER_CONNECTION,
            "BROKER-CONNECTION-PRIMARY",
            "BROKER",
            "NOT_CONNECTED",
            "NOT_READY",
            metadata={
                "required_authorization": AuthorizationType.BROKER_CONNECTION.value,
                "connector_calls": 0,
            },
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "CAPABILITY-PAPER-TRADING",
            "PLATFORM",
            "DISABLED",
            "NOT_READY",
            metadata={"paper_trading_started": False},
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "CAPABILITY-LIVE-TRADING",
            "PLATFORM",
            "DISABLED",
            "NOT_READY",
            metadata={"live_trading_started": False},
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "CAPABILITY-PRODUCTION",
            "PLATFORM",
            "DISABLED",
            "NOT_READY",
            metadata={"production_candidates": 0, "validated_production_strategies": 0},
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "MODULE-04.01",
            "PLATFORM",
            "COMPLETE",
            "READY",
            metadata={
                "module_id": "04.01",
                "command_version": "INTERSIGNAL_PLATFORM_FOUNDATION_V1",
                "foundation_hash": platform_foundation_hash,
            },
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "MODULE-04.02",
            "PLATFORM",
            "COMPLETE",
            "READY",
            metadata={
                "module_id": "04.02",
                "command_version": "INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_V1",
                "foundation_hash": research_workbench_hash,
            },
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "MODULE-04.03",
            "PLATFORM",
            "COMPLETE",
            "READY",
            metadata={
                "module_id": "04.03",
                "command_version": "INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_V1",
                "foundation_hash": portfolio_os_hash,
            },
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "MODULE-04.04",
            "PLATFORM",
            "IN_PROGRESS",
            "INCONCLUSIVE",
            metadata={
                "module_id": "04.04",
                "command_version": "INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_V1",
            },
        ),
        _subject(
            GovernanceSubjectType.PLATFORM_MODULE,
            "MODULE-04.05",
            "PLATFORM",
            "NOT_STARTED",
            "NOT_READY",
            metadata={
                "module_id": "04.05",
                "command_version": "NOT_STARTED",
            },
        ),
    )
    minute = 0
    for subject in subjects:
        _register(
            service,
            subject,
            minute,
            "Project current state into governance without domain mutation",
        )
        minute += 1
    for portfolio in portfolio_repository.list_portfolios():
        _register(
            service,
            _subject(
                GovernanceSubjectType.PORTFOLIO,
                portfolio.portfolio_id,
                "PORTFOLIO",
                portfolio.status.value,
                "READY_WITH_LIMITATIONS",
                metadata={
                    "synthetic": portfolio.metadata.get("synthetic", False),
                    "source_of_truth": "PORTFOLIO_OS",
                    "direct_mutation_allowed": False,
                },
            ),
            minute,
            "Register read-only Portfolio OS governance subject",
        )
        minute += 1

    service.transition_subject(
        "MODULE-04.04",
        current_state="COMPLETE",
        readiness_state="READY_WITH_LIMITATIONS",
        actor=SEED_ACTOR,
        reason="Governance foundation construction completed before verification export",
        timestamp=_time(20),
        metadata={"verification_state": "FOUNDATION_BUILT"},
    )

    readiness_rows = (
        ReadinessAssessment(
            assessment_id="READINESS-RESEARCH-CURRENT-001",
            subject_type=GovernanceSubjectType.RESEARCH_PROGRAM,
            subject_id="RESEARCH-PROGRAM-A-TO-G",
            readiness_type=ReadinessType.RESEARCH_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={
                "programme_state_recorded": True,
                "active_discovery_authorized": False,
            },
            failed_criteria=("active_discovery_authorized",),
            warnings=("PROGRAMME_PAUSED", "NOT_ACTIVE_DISCOVERY"),
            assessed_at=_time(21),
            metadata={"operational_state": "PAUSED"},
        ),
        ReadinessAssessment(
            assessment_id="READINESS-PLATFORM-CURRENT-001",
            subject_type=GovernanceSubjectType.PLATFORM_MODULE,
            subject_id="PLATFORM-CORE",
            readiness_type=ReadinessType.PLATFORM_MODULE_READINESS,
            status=ReadinessStatus.READY_WITH_LIMITATIONS,
            criteria={
                "module_04_01_complete": True,
                "module_04_02_complete": True,
                "module_04_03_complete": True,
                "module_04_04_complete": True,
            },
            warnings=("MODULE_04_05_NOT_STARTED",),
            assessed_at=_time(22),
            metadata={"scope": "BACKEND_FOUNDATIONS_ONLY"},
        ),
        ReadinessAssessment(
            assessment_id="READINESS-PAPER-CURRENT-001",
            subject_type=GovernanceSubjectType.PLATFORM_MODULE,
            subject_id="CAPABILITY-PAPER-TRADING",
            readiness_type=ReadinessType.PAPER_TRADING_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={
                "validated_candidate_exists": False,
                "candidate_approved_for_paper": False,
            },
            failed_criteria=(
                "validated_candidate_exists",
                "candidate_approved_for_paper",
            ),
            assessed_at=_time(23),
            metadata={"production_candidate_count": 0},
        ),
        ReadinessAssessment(
            assessment_id="READINESS-LIVE-CURRENT-001",
            subject_type=GovernanceSubjectType.PLATFORM_MODULE,
            subject_id="CAPABILITY-LIVE-TRADING",
            readiness_type=ReadinessType.LIVE_TRADING_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={
                "validated_candidate_exists": False,
                "paper_or_shadow_evidence_ready": False,
                "risk_ready": False,
                "broker_ready": False,
                "data_ready": False,
                "production_authorized": False,
            },
            failed_criteria=(
                "validated_candidate_exists",
                "paper_or_shadow_evidence_ready",
                "risk_ready",
                "broker_ready",
                "data_ready",
                "production_authorized",
            ),
            assessed_at=_time(24),
        ),
        ReadinessAssessment(
            assessment_id="READINESS-PRODUCTION-CURRENT-001",
            subject_type=GovernanceSubjectType.PLATFORM_MODULE,
            subject_id="CAPABILITY-PRODUCTION",
            readiness_type=ReadinessType.PRODUCTION_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={
                "production_candidate_exists": False,
                "validated_production_strategy_exists": False,
            },
            failed_criteria=(
                "production_candidate_exists",
                "validated_production_strategy_exists",
            ),
            assessed_at=_time(25),
            metadata={
                "production_candidate_count": 0,
                "validated_production_strategy_count": 0,
            },
        ),
        ReadinessAssessment(
            assessment_id="READINESS-BROKER-CURRENT-001",
            subject_type=GovernanceSubjectType.BROKER_CONNECTION,
            subject_id="BROKER-CONNECTION-PRIMARY",
            readiness_type=ReadinessType.BROKER_READINESS,
            status=ReadinessStatus.NOT_READY,
            criteria={
                "broker_connected": False,
                "broker_connection_authorized": False,
            },
            failed_criteria=(
                "broker_connected",
                "broker_connection_authorized",
            ),
            assessed_at=_time(26),
            metadata={"connection_state": "NOT_CONNECTED"},
        ),
    )
    for row in readiness_rows:
        service.record_readiness_assessment(
            row,
            actor=SEED_ACTOR,
            reason="Record deterministic current readiness projection",
        )

    policy_specs = (
        (
            "NO_LIVE_WITHOUT_VALIDATED_STRATEGY",
            "No live trading without a validated strategy",
            "TRADING",
            "Live operation must remain disabled without a validated strategy.",
            PolicySeverity.BLOCKING,
            "live_trading_started",
            PolicyOperator.FALSY,
            None,
            "Live trading must remain disabled",
            "CAPABILITY-LIVE-TRADING",
            {"live_trading_started": False},
        ),
        (
            "NO_PAPER_WITHOUT_APPROVED_CANDIDATE",
            "No paper trading without an approved candidate",
            "TRADING",
            "Paper trading requires a separately approved candidate.",
            PolicySeverity.BLOCKING,
            "paper_trading_started",
            PolicyOperator.FALSY,
            None,
            "Paper trading must remain disabled",
            "CAPABILITY-PAPER-TRADING",
            {"paper_trading_started": False},
        ),
        (
            "NO_BROKER_CONNECTION_WITHOUT_AUTHORIZATION",
            "No broker connection without authorization",
            "BROKER",
            "Broker connectivity requires explicit authorization.",
            PolicySeverity.BLOCKING,
            "broker_connected",
            PolicyOperator.FALSY,
            None,
            "Broker must remain disconnected",
            "BROKER-CONNECTION-PRIMARY",
            {"broker_connected": False},
        ),
        (
            "NO_DATA_ACQUISITION_WITHOUT_AUTHORIZATION",
            "No data acquisition without authorization",
            "DATA",
            "Historical or licensed acquisition requires explicit authorization.",
            PolicySeverity.BLOCKING,
            "data_acquisition_running",
            PolicyOperator.FALSY,
            None,
            "Data acquisition must not be running",
            "DATA-SOURCE-CATALYST-HISTORY",
            {"data_acquisition_running": False},
        ),
        (
            "NO_STRATEGY_PROMOTION_WITHOUT_VALIDATION",
            "No strategy promotion without validation",
            "RESEARCH",
            "Promotion requires valid supporting validation.",
            PolicySeverity.BLOCKING,
            "strategy_promotion_in_progress",
            PolicyOperator.FALSY,
            None,
            "Promotion must remain inactive",
            "FAMILY_A",
            {"strategy_promotion_in_progress": False},
        ),
        (
            "NO_POST_OUTCOME_AS_PRISTINE_VALIDATION",
            "Do not treat post-outcome evidence as pristine validation",
            "RESEARCH",
            "Formal and post-outcome evidence classifications must remain distinct.",
            PolicySeverity.CRITICAL,
            "formal_post_outcome_distinction_preserved",
            PolicyOperator.TRUTHY,
            None,
            "Evidence distinction must be preserved",
            "VALIDATION-FAMILY-A",
            {"formal_post_outcome_distinction_preserved": True},
        ),
        (
            "NO_PRODUCTION_WITH_OPEN_BLOCKING_VIOLATIONS",
            "No production with open blocking violations",
            "PLATFORM",
            "Production remains disabled until governance requirements pass.",
            PolicySeverity.BLOCKING,
            "production_enabled",
            PolicyOperator.FALSY,
            None,
            "Production must remain disabled",
            "CAPABILITY-PRODUCTION",
            {"production_enabled": False, "open_blocking_violations": 0},
        ),
        (
            "NO_DESTRUCTIVE_RESEARCH_MUTATION",
            "No destructive research mutation",
            "RESEARCH",
            "Frozen research history is append-only and immutable.",
            PolicySeverity.BLOCKING,
            "destructive_research_mutation",
            PolicyOperator.FALSY,
            None,
            "Research history must remain immutable",
            "RESEARCH-PROGRAM-A-TO-G",
            {"destructive_research_mutation": False},
        ),
    )
    policies: list[GovernancePolicy] = []
    for index, spec in enumerate(policy_specs, start=27):
        policy = _policy(*spec[:9], minute=index)
        service.register_policy(
            policy,
            actor=SEED_ACTOR,
            reason="Freeze initial deterministic core governance policy",
            timestamp=_time(index),
            audit_subject_id="PLATFORM-CORE",
        )
        policies.append(policy)

    authorization = AuthorizationRecord(
        authorization_id="AUTH-FAMILY-F-DATA-ACQUISITION-001",
        subject_type=GovernanceSubjectType.DATA_SOURCE,
        subject_id="DATA-SOURCE-CATALYST-HISTORY",
        authorization_type=AuthorizationType.DATA_ACQUISITION,
        status=AuthorizationStatus.REQUESTED,
        requested_by=SEED_ACTOR,
        requested_at=_time(35),
        reason="Record unresolved authorization and licensing gate; do not acquire data",
        conditions=(
            "Authorized or licensed historical catalyst source",
            "Reproducible bounded acquisition plan",
            "Retention and redistribution terms recorded",
        ),
        related_artifact_ids=tuple(blocked["F"]["related_artifacts"]),
        metadata={"acquisition_started": False, "automatic_permission": False},
    )
    service.request_authorization(authorization)

    evaluations = []
    for index, (policy, spec) in enumerate(zip(policies, policy_specs), start=36):
        subject_id = spec[9]
        context = spec[10]
        evaluation = service.evaluate_policy(
            policy.policy_id,
            subject_id=subject_id,
            context=context,
            evaluated_at=_time(index),
        )
        service.record_policy_evaluation(
            evaluation,
            actor=SEED_ACTOR,
            reason="Evaluate current platform state against frozen core policy",
        )
        evaluations.append(evaluation)

    return {
        "subjects": service.list_subjects(),
        "readiness": readiness_rows,
        "policies": tuple(policies),
        "evaluations": tuple(evaluations),
        "authorization": authorization,
    }


__all__ = (
    "SEED_ACTOR",
    "SEED_BASE_TIME",
    "seed_current_governance_state",
)

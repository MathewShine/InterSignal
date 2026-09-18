from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypeVar

from app.governance_api.models import (
    AuditView,
    AuthorizationView,
    GovernanceAuditResponse,
    GovernanceAuthorizationsResponse,
    GovernanceAvailability,
    GovernanceMeta,
    GovernanceOverviewResponse,
    GovernancePoliciesResponse,
    GovernanceReadinessResponse,
    GovernanceSummaryView,
    OverrideView,
    PolicyView,
    ReadinessView,
)
from app.governance_audit.models import PolicyEvaluationStatus, ReadinessType
from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.service import GovernanceService


T = TypeVar("T")


class GovernanceApplicationService:
    """Failure-isolated, read-only projection of canonical governance records."""

    def __init__(
        self,
        governance: GovernanceService,
        repository: JsonFileGovernanceRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._governance = governance
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _generated_at(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Governance API clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _meta(unavailable: list[str]) -> GovernanceMeta:
        return GovernanceMeta(unavailable_sections=tuple(dict.fromkeys(unavailable)))

    def _base(self, unavailable: list[str]) -> dict[str, Any]:
        return {
            "generated_at": self._generated_at(),
            "status": GovernanceAvailability.PARTIAL if unavailable else GovernanceAvailability.AVAILABLE,
            "reason": "GOVERNANCE_SECTIONS_UNAVAILABLE" if unavailable else None,
            "meta": self._meta(unavailable),
        }

    def _readiness(self) -> tuple[ReadinessView, ...]:
        latest = {}
        for row in self._governance.get_readiness():
            previous = latest.get(row.readiness_type)
            if previous is None or (row.assessed_at, row.assessment_id) > (previous.assessed_at, previous.assessment_id):
                latest[row.readiness_type] = row
        order = {
            ReadinessType.PAPER_TRADING_READINESS: 0,
            ReadinessType.LIVE_TRADING_READINESS: 1,
            ReadinessType.BROKER_READINESS: 2,
            ReadinessType.PRODUCTION_READINESS: 3,
        }
        return tuple(
            ReadinessView(
                assessment_id=row.assessment_id,
                readiness_type=row.readiness_type.value,
                label=row.readiness_type.value.replace("_READINESS", "").replace("_", " ").title(),
                subject_id=row.subject_id,
                status=row.status.value,
                assessed_at=row.assessed_at,
                passed_criteria=sum(row.criteria.values()),
                total_criteria=len(row.criteria),
                failed_criteria=row.failed_criteria,
                warnings=row.warnings,
                connection_state=str(row.metadata.get("connection_state")) if row.metadata.get("connection_state") else None,
            )
            for row in sorted(latest.values(), key=lambda item: (order.get(item.readiness_type, 9), item.readiness_type.value))
        )

    def _policies(self) -> tuple[PolicyView, ...]:
        latest = {}
        for row in self._governance.get_policy_evaluations():
            previous = latest.get(row.policy_id)
            if previous is None or (row.evaluated_at, row.evaluation_id) > (previous.evaluated_at, previous.evaluation_id):
                latest[row.policy_id] = row
        return tuple(
            PolicyView(
                policy_id=policy.policy_id,
                name=policy.name,
                version=policy.version,
                domain=policy.domain,
                description=policy.description,
                severity=policy.severity.value,
                enabled=policy.enabled,
                evaluation_status=(latest[policy.policy_id].status.value if policy.policy_id in latest else "NOT_EVALUATED"),
                evaluated_at=(latest[policy.policy_id].evaluated_at if policy.policy_id in latest else None),
                passed_checks=(latest[policy.policy_id].passed_checks if policy.policy_id in latest else ()),
                failed_checks=(latest[policy.policy_id].failed_checks if policy.policy_id in latest else ()),
                warnings=(latest[policy.policy_id].warnings if policy.policy_id in latest else ()),
            )
            for policy in sorted(self._repository.list_policies(), key=lambda item: (item.domain, item.name))
        )

    def _authorizations(self) -> tuple[AuthorizationView, ...]:
        return tuple(
            AuthorizationView(
                authorization_id=row.authorization_id,
                authorization_type=row.authorization_type.value,
                subject_id=row.subject_id,
                subject_type=row.subject_type.value,
                status=row.status.value,
                requested_by=row.requested_by,
                requested_at=row.requested_at,
                decided_at=row.decided_at,
                reason=row.reason,
                conditions=row.conditions,
                expires_at=row.expires_at,
            )
            for row in sorted(self._governance.get_authorizations(), key=lambda item: (item.requested_at, item.authorization_id), reverse=True)
        )

    def _audit(self) -> tuple[AuditView, ...]:
        return tuple(
            AuditView(
                event_id=row.source_event_id,
                source=row.source.value,
                event_type=row.event_type,
                domain=row.domain,
                subject_id=row.subject_id,
                subject_type=row.subject_type,
                actor=row.actor,
                occurred_at=row.timestamp,
                action=row.action,
                result=row.result,
                reason=row.reason,
                authorization_id=row.authorization_id,
            )
            for row in reversed(self._governance.get_combined_audit_timeline())
        )

    def _overrides(self) -> tuple[OverrideView, ...]:
        return tuple(
            OverrideView(
                override_id=row.override_id,
                subject_id=row.subject_id,
                override_type=row.override_type,
                requested_by=row.requested_by,
                approved_by=row.approved_by,
                reason=row.reason,
                created_at=row.created_at,
                expires_at=row.expires_at,
                authorization_id=row.authorization_id,
            )
            for row in sorted(self._governance.get_manual_overrides(), key=lambda item: (item.created_at, item.override_id), reverse=True)
        )

    def _summary(self, readiness: tuple[ReadinessView, ...], policies: tuple[PolicyView, ...]) -> GovernanceSummaryView:
        summary = self._governance.get_governance_summary()
        integrity = self._governance.get_integrity_summary()
        by_type = {row.readiness_type: row for row in readiness}
        broker = by_type.get(ReadinessType.BROKER_READINESS.value)
        return GovernanceSummaryView(
            paper_readiness=summary.paper_readiness.value,
            live_readiness=summary.live_readiness.value,
            broker_readiness=(broker.status if broker else "NOT_READY"),
            production_readiness=summary.production_readiness.value,
            broker_connection_state=(broker.connection_state if broker and broker.connection_state else "NOT_CONNECTED"),
            blocking_violation_count=summary.blocking_violations,
            open_violation_count=summary.open_violations,
            pending_authorization_count=summary.open_authorizations,
            approved_authorization_count=summary.approved_authorizations,
            passing_policy_count=sum(row.evaluation_status == PolicyEvaluationStatus.PASS.value for row in policies),
            total_policy_count=len(policies),
            integrity_status=integrity.status.value,
        )

    def get_overview(self) -> GovernanceOverviewResponse:
        unavailable: list[str] = []

        def read(name: str, operation: Callable[[], T], fallback: T) -> T:
            try:
                return operation()
            except Exception:
                unavailable.append(name)
                return fallback

        readiness = read("readiness", self._readiness, ())
        policies = read("policies", self._policies, ())
        authorizations = read("authorizations", self._authorizations, ())
        audit = read("audit", self._audit, ())
        overrides = read("manual_overrides", self._overrides, ())
        summary = read("summary", lambda: self._summary(readiness, policies), None)
        return GovernanceOverviewResponse(
            **self._base(unavailable),
            summary=summary,
            readiness=readiness,
            policies=policies,
            authorizations=authorizations,
            recent_audit=audit[:8],
            manual_overrides=overrides,
        )

    def get_readiness(self) -> GovernanceReadinessResponse:
        items = self._readiness()
        return GovernanceReadinessResponse(**self._base([]), items=items, total_count=len(items))

    def get_policies(self) -> GovernancePoliciesResponse:
        items = self._policies()
        return GovernancePoliciesResponse(
            **self._base([]), items=items,
            passing_count=sum(row.evaluation_status == PolicyEvaluationStatus.PASS.value for row in items),
            total_count=len(items),
        )

    def get_authorizations(self) -> GovernanceAuthorizationsResponse:
        items = self._authorizations()
        return GovernanceAuthorizationsResponse(
            **self._base([]), items=items,
            pending_count=sum(row.status == "REQUESTED" for row in items),
            total_count=len(items),
        )

    def get_audit(self) -> GovernanceAuditResponse:
        items = self._audit()
        return GovernanceAuditResponse(
            **self._base([]), items=items, manual_overrides=self._overrides(), total_count=len(items)
        )


__all__ = ("GovernanceApplicationService",)

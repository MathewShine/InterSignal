from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app.platform.hashing import canonical_hash, deterministic_id
from app.governance_audit.models import (
    GovernancePolicy,
    PolicyEvaluation,
    PolicyEvaluationStatus,
    PolicyOperator,
    PolicySeverity,
)


_MISSING = object()


class DeterministicPolicyEngine:
    """Small declarative policy evaluator with no inference or AI decisions."""

    @staticmethod
    def _fact(context: Mapping[str, Any], path: str) -> Any:
        current: Any = context
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return _MISSING
            current = current[part]
        return current

    @staticmethod
    def _passes(observed: Any, operator: PolicyOperator, expected: Any) -> bool:
        if operator == PolicyOperator.EQUALS:
            return observed == expected
        if operator == PolicyOperator.NOT_EQUALS:
            return observed != expected
        if operator == PolicyOperator.IN:
            return observed in expected
        if operator == PolicyOperator.NOT_IN:
            return observed not in expected
        if operator == PolicyOperator.TRUTHY:
            return bool(observed)
        if operator == PolicyOperator.FALSY:
            return not bool(observed)
        if operator == PolicyOperator.LESS_THAN_OR_EQUAL:
            return observed <= expected
        if operator == PolicyOperator.GREATER_THAN_OR_EQUAL:
            return observed >= expected
        raise ValueError(f"Unsupported policy operator: {operator}")

    def evaluate(
        self,
        *,
        policy: GovernancePolicy,
        subject_id: str,
        context: Mapping[str, Any],
        evaluated_at: datetime,
        related_artifacts: tuple[str, ...] = (),
    ) -> PolicyEvaluation:
        context_hash = canonical_hash(context)
        evaluation_id = deterministic_id(
            "GEVAL",
            policy.policy_id,
            policy.version,
            subject_id,
            evaluated_at,
            context_hash,
        )
        if not policy.enabled:
            return PolicyEvaluation(
                evaluation_id=evaluation_id,
                policy_id=policy.policy_id,
                subject_id=subject_id,
                status=PolicyEvaluationStatus.INCONCLUSIVE,
                evaluated_at=evaluated_at,
                warnings=("POLICY_DISABLED",),
                details={"context_hash": context_hash, "policy_version": policy.version},
                related_artifacts=related_artifacts,
                metadata={"engine": "DETERMINISTIC_DECLARATIVE_V1"},
            )
        passed: list[str] = []
        failed: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []
        observations: dict[str, Any] = {}
        for rule in policy.rules:
            observed = self._fact(context, rule.fact)
            if observed is _MISSING:
                missing.append(rule.rule_id)
                failed.append(rule.rule_id)
                observations[rule.rule_id] = {
                    "fact": rule.fact,
                    "observed": "MISSING",
                    "expected": rule.expected,
                    "operator": rule.operator.value,
                }
                continue
            result = self._passes(observed, rule.operator, rule.expected)
            observations[rule.rule_id] = {
                "fact": rule.fact,
                "observed": observed,
                "expected": rule.expected,
                "operator": rule.operator.value,
            }
            if result:
                passed.append(rule.rule_id)
            elif rule.warning_only:
                warnings.append(f"{rule.rule_id}:{rule.message}")
            else:
                failed.append(rule.rule_id)
        if missing:
            status = PolicyEvaluationStatus.INCONCLUSIVE
        elif failed and policy.severity == PolicySeverity.BLOCKING:
            status = PolicyEvaluationStatus.BLOCKED
        elif failed:
            status = PolicyEvaluationStatus.FAIL
        elif warnings:
            status = PolicyEvaluationStatus.PASS_WITH_WARNINGS
        else:
            status = PolicyEvaluationStatus.PASS
        return PolicyEvaluation(
            evaluation_id=evaluation_id,
            policy_id=policy.policy_id,
            subject_id=subject_id,
            status=status,
            evaluated_at=evaluated_at,
            passed_checks=tuple(passed),
            failed_checks=tuple(failed),
            warnings=tuple(warnings),
            details={
                "context_hash": context_hash,
                "policy_version": policy.version,
                "observations": observations,
                "missing_facts": missing,
            },
            related_artifacts=related_artifacts,
            metadata={"engine": "DETERMINISTIC_DECLARATIVE_V1"},
        )


__all__ = ("DeterministicPolicyEngine",)

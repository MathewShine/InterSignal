from __future__ import annotations

from typing import Any, Sequence

from app.strategy.entry_config import EntryEvaluationConfig
from app.strategy.entry_penalties import blocking_penalty_present, severe_penalty_present
from app.strategy.momentum_candidates import split_codes


def evaluate_entry_gates(
    *,
    candidate_row: dict[str, Any] | None,
    setup_row: dict[str, Any] | None,
    regime_row: dict[str, Any] | None,
    penalties: Sequence[dict[str, Any]],
    exceptional_long_candidate: bool,
    config: EntryEvaluationConfig,
) -> dict[str, dict[str, Any]]:
    return {
        "research": research_gate(candidate_row=candidate_row, setup_row=setup_row, regime_row=regime_row),
        "candidate": candidate_gate(candidate_row=candidate_row, setup_row=setup_row),
        "setup": setup_gate(setup_row=setup_row, config=config),
        "regime": regime_gate(
            setup_row=setup_row,
            regime_row=regime_row,
            penalties=penalties,
            exceptional_long_candidate=exceptional_long_candidate,
            config=config,
        ),
        "extension": extension_gate(setup_row=setup_row, config=config),
        "technical_rejection": technical_rejection_gate(setup_row=setup_row, config=config),
    }


def research_gate(
    *,
    candidate_row: dict[str, Any] | None,
    setup_row: dict[str, Any] | None,
    regime_row: dict[str, Any] | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    if candidate_row is None:
        reasons.append("CANDIDATE_UNAVAILABLE")
    if setup_row is None:
        reasons.append("SETUP_UNAVAILABLE")
    if regime_row is None:
        reasons.append("REGIME_UNAVAILABLE")
    if setup_row and str(setup_row.get("research_status", "")).upper() == "BLOCKED":
        reasons.append("RESEARCH_DATA_BLOCKED")
    if setup_row and "CORPORATE_ACTION" in str(setup_row.get("setup_rejection_reasons", "")).upper():
        reasons.append("CORPORATE_ACTION_EXCLUSION")
    combined_warnings = ";".join(
        str(row.get("warning_flags", ""))
        for row in (candidate_row or {}, setup_row or {})
        if isinstance(row, dict)
    )
    if "MEMBERSHIP_UNCERTAIN" in combined_warnings:
        warnings.append("MEMBERSHIP_UNCERTAIN")
    if setup_row and "CONTAMINATED_LOOKBACK" in str(setup_row.get("setup_rejection_reasons", "")).upper():
        reasons.append("CONTAMINATED_LOOKBACK")
    status = "BLOCKED" if reasons else "READY"
    return gate(
        "DATA_RESEARCH_SAFETY",
        status=status,
        passed=not reasons,
        reason_codes=reasons + warnings,
        evidence={
            "candidate_row_available": candidate_row is not None,
            "setup_row_available": setup_row is not None,
            "regime_row_available": regime_row is not None,
            "research_status": (setup_row or {}).get("research_status", ""),
            "candidate_membership_status": (candidate_row or {}).get("membership_status", ""),
            "setup_warning_flags": (setup_row or {}).get("warning_flags", ""),
        },
    )


def candidate_gate(*, candidate_row: dict[str, Any] | None, setup_row: dict[str, Any] | None) -> dict[str, Any]:
    row = candidate_row or setup_row or {}
    candidate_state = str(row.get("candidate_state", "")).upper()
    passed = candidate_state in {"EMERGING", "CONFIRMED"}
    reasons = [] if passed else ["CANDIDATE_NOT_EMERGING_OR_CONFIRMED"]
    if candidate_row is None:
        reasons.append("CANDIDATE_UNAVAILABLE")
    return gate(
        "CANDIDATE_ELIGIBILITY",
        status="READY" if passed else "BLOCKED",
        passed=passed,
        reason_codes=reasons,
        evidence={
            "candidate_state": candidate_state,
            "emerging_eligible": truthy(row.get("emerging_eligible")),
            "confirmed_eligible": truthy(row.get("confirmed_eligible")),
            "both_eligible": truthy(row.get("both_eligible")),
        },
    )


def setup_gate(*, setup_row: dict[str, Any] | None, config: EntryEvaluationConfig) -> dict[str, Any]:
    if setup_row is None:
        return gate(
            "SETUP_ELIGIBILITY",
            status="BLOCKED",
            passed=False,
            reason_codes=["SETUP_UNAVAILABLE"],
            evidence={},
        )
    setup_quality = str(setup_row.get("setup_quality", "")).upper()
    setup_eligible = truthy(setup_row.get("setup_eligible"))
    reasons: list[str] = []
    status = "READY"
    passed = True
    if not setup_eligible:
        passed = False
        status = "PARTIAL" if setup_quality == "WATCH" else "BLOCKED"
        reasons.append("SETUP_NOT_ELIGIBLE")
    if setup_quality == "WATCH":
        passed = False
        status = "PARTIAL"
        reasons.append("SETUP_WATCH_ONLY")
    elif setup_quality == "POOR":
        passed = False
        status = "BLOCKED"
        reasons.append("SETUP_POOR")
    elif setup_quality not in set(config.acceptable_setup_qualities):
        passed = False
        status = "BLOCKED"
        reasons.append("NO_CREDIBLE_BREAKOUT_OR_CONTINUATION")
    return gate(
        "SETUP_ELIGIBILITY",
        status=status,
        passed=passed,
        reason_codes=dedupe(reasons + list(split_codes(setup_row.get("setup_rejection_reasons", "")))),
        evidence={
            "setup_eligible": setup_eligible,
            "setup_quality": setup_quality,
            "setup_type_flags": setup_row.get("setup_type_flags", ""),
            "breakout_state": setup_row.get("breakout_state", ""),
        },
    )


def regime_gate(
    *,
    setup_row: dict[str, Any] | None,
    regime_row: dict[str, Any] | None,
    penalties: Sequence[dict[str, Any]],
    exceptional_long_candidate: bool,
    config: EntryEvaluationConfig,
) -> dict[str, Any]:
    regime_state = str((regime_row or {}).get("regime_state", "") or "UNAVAILABLE").upper()
    permission = regime_permission(regime_state=regime_state, config=config)
    reasons: list[str] = []
    passed = True
    status = "READY"
    if regime_row is None:
        permission = config.regime.unavailable_permission
        status = "PARTIAL"
        reasons.append("REGIME_UNAVAILABLE")
    elif regime_state == "BULLISH":
        permission = config.regime.bullish_permission
    elif regime_state == "NEUTRAL":
        permission = config.regime.neutral_permission
        if not neutral_strict_requirements_met(setup_row or {}, penalties, config):
            status = "PARTIAL"
            reasons.append("NEUTRAL_STRICT_REQUIREMENTS_NOT_MET")
    elif regime_state == "BEARISH":
        permission = config.regime.bearish_permission
        if not exceptional_long_candidate:
            status = "BLOCKED"
            passed = False
            reasons.append("BEARISH_NORMAL_LONG_BLOCKED")
    else:
        permission = config.regime.unavailable_permission
        status = "PARTIAL"
        reasons.append("REGIME_UNAVAILABLE")
    return gate(
        "MARKET_REGIME_PERMISSION",
        status=status,
        passed=passed,
        reason_codes=reasons,
        evidence={
            "regime_state": regime_state,
            "regime_permission": permission,
            "regime_score_normalized": (regime_row or {}).get("regime_score_normalized", ""),
            "confidence_score": (regime_row or {}).get("confidence_score", ""),
            "confidence_state": (regime_row or {}).get("confidence_state", ""),
            "available_weight_pct": (regime_row or {}).get("available_weight_pct", ""),
            "exceptional_long_candidate": exceptional_long_candidate,
        },
    )


def extension_gate(*, setup_row: dict[str, Any] | None, config: EntryEvaluationConfig) -> dict[str, Any]:
    extension = str((setup_row or {}).get("extension_risk", "") or "UNAVAILABLE").upper()
    if extension in set(config.extension.blocking):
        return gate(
            "EXTENSION_SAFETY",
            status="BLOCKED",
            passed=False,
            reason_codes=["EXTREME_EXTENSION"],
            evidence={"extension_risk": extension},
        )
    reasons = ["HIGH_EXTENSION"] if extension in set(config.extension.warning) else []
    return gate(
        "EXTENSION_SAFETY",
        status="PARTIAL" if reasons else "READY",
        passed=True,
        reason_codes=reasons,
        evidence={"extension_risk": extension},
    )


def technical_rejection_gate(*, setup_row: dict[str, Any] | None, config: EntryEvaluationConfig) -> dict[str, Any]:
    setup_row = setup_row or {}
    false_flags = split_codes(setup_row.get("false_breakout_flags", ""))
    breakout_state = str(setup_row.get("breakout_state", "")).upper()
    blocking_flags = false_flags & set(config.technical_rejection.blocking_false_breakout_flags)
    reasons = sorted(blocking_flags)
    if breakout_state in set(config.technical_rejection.blocking_breakout_states):
        reasons.append("FAILED_BREAKOUT")
    warning_flags = sorted(false_flags & set(config.technical_rejection.warning_false_breakout_flags))
    return gate(
        "TECHNICAL_REJECTION_SAFETY",
        status="BLOCKED" if reasons else "PARTIAL" if warning_flags else "READY",
        passed=not reasons,
        reason_codes=dedupe(reasons + warning_flags),
        evidence={
            "false_breakout_flags": sorted(false_flags),
            "breakout_state": breakout_state,
        },
    )


def regime_permission(*, regime_state: str, config: EntryEvaluationConfig) -> str:
    return {
        "BULLISH": config.regime.bullish_permission,
        "NEUTRAL": config.regime.neutral_permission,
        "BEARISH": config.regime.bearish_permission,
        "UNAVAILABLE": config.regime.unavailable_permission,
    }.get(regime_state, config.regime.unavailable_permission)


def neutral_strict_requirements_met(
    setup_row: dict[str, Any],
    penalties: Sequence[dict[str, Any]],
    config: EntryEvaluationConfig,
) -> bool:
    setup_quality = str(setup_row.get("setup_quality", "")).upper()
    if setup_quality in set(config.neutral.strong_setup_qualities):
        return True
    if setup_quality not in set(config.neutral.valid_setup_qualities):
        return False
    candidate_confirmed_or_both = str(setup_row.get("candidate_state", "")).upper() == "CONFIRMED" or truthy(
        setup_row.get("both_eligible")
    )
    if config.neutral.valid_requires_confirmed_or_both and not candidate_confirmed_or_both:
        return False
    if str(setup_row.get("benchmark_rs_context", "")).upper() not in set(config.neutral.required_benchmark_rs):
        return False
    if severe_penalty_present(penalties) or blocking_penalty_present(penalties):
        return False
    return True


def gate(
    gate_name: str,
    *,
    status: str,
    passed: bool,
    reason_codes: Sequence[str],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_name": gate_name,
        "gate_status": status,
        "passed": passed,
        "reason_codes": dedupe(reason_codes),
        "evidence": evidence,
    }


def dedupe(values: Sequence[str]) -> list[str]:
    output = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"

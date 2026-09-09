from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from app.strategy.entry_config import EntryEvaluationConfig
from app.strategy.momentum_candidates import parse_decimal, split_codes


def build_entry_penalties(
    *,
    setup_row: dict[str, Any],
    regime_row: dict[str, Any] | None,
    config: EntryEvaluationConfig,
    exceptional_long_candidate: bool = False,
) -> list[dict[str, Any]]:
    penalties: list[dict[str, Any]] = []
    candidate_state = str(setup_row.get("candidate_state", "")).upper()
    setup_quality = str(setup_row.get("setup_quality", "")).upper()
    volume = str(setup_row.get("volume_confirmation", "")).upper()
    benchmark_rs = str(setup_row.get("benchmark_rs_context", "")).upper()
    extension = str(setup_row.get("extension_risk", "")).upper()
    candle = str(setup_row.get("candle_quality", "")).upper()
    false_flags = split_codes(setup_row.get("false_breakout_flags", ""))
    regime_state = str((regime_row or {}).get("regime_state", "") or "UNAVAILABLE").upper()
    confidence_state = str((regime_row or {}).get("confidence_state", "") or "").upper()
    available_weight = parse_decimal((regime_row or {}).get("available_weight_pct"))

    if setup_quality == "POOR":
        penalties.append(entry_penalty("SETUP_POOR", config, blocking=True, evidence={"setup_quality": setup_quality}))
    elif setup_quality == "WATCH":
        penalties.append(entry_penalty("SETUP_WATCH_ONLY", config, evidence={"setup_quality": setup_quality}))

    if candle == "POOR":
        penalties.append(entry_penalty("POOR_CANDLE_CONTEXT", config, evidence={"candle_quality": candle}))
    if "UPPER_WICK_REJECTION" in false_flags:
        penalties.append(entry_penalty("UPPER_WICK_REJECTION", config, evidence={"false_breakout_flags": sorted(false_flags)}))
    if volume in {"WEAK", "UNKNOWN", "UNAVAILABLE", ""}:
        penalties.append(entry_penalty("LOW_VOLUME_CONFIRMATION", config, evidence={"volume_confirmation": volume}))
    if benchmark_rs == "WEAK":
        penalties.append(entry_penalty("WEAK_BENCHMARK_RS", config, evidence={"benchmark_rs_context": benchmark_rs}))
    if extension == "HIGH":
        penalties.append(entry_penalty("HIGH_EXTENSION", config, evidence={"extension_risk": extension}))
    if extension == "EXTREME":
        penalties.append(entry_penalty("EXTREME_EXTENSION", config, blocking=True, evidence={"extension_risk": extension}))
    if str(setup_row.get("overhead_resistance", "")).upper() in {"HIGH", "NEAR"}:
        penalties.append(
            entry_penalty(
                "OVERHEAD_RESISTANCE",
                config,
                evidence={"overhead_resistance": setup_row.get("overhead_resistance", "")},
            )
        )
    if false_flags:
        blocking = bool(false_flags & set(config.technical_rejection.blocking_false_breakout_flags))
        penalties.append(
            entry_penalty(
                "FALSE_BREAKOUT_WARNING",
                config,
                blocking=blocking,
                evidence={"false_breakout_flags": sorted(false_flags)},
            )
        )
    if regime_state == "NEUTRAL":
        penalties.append(entry_penalty("NEUTRAL_REGIME", config, evidence={"regime_state": regime_state}))
    if regime_state == "BEARISH":
        penalties.append(
            entry_penalty(
                "BEARISH_REGIME",
                config,
                blocking=not exceptional_long_candidate,
                evidence={"regime_state": regime_state, "exceptional_long_candidate": exceptional_long_candidate},
            )
        )
        if not exceptional_long_candidate:
            penalties.append(
                entry_penalty(
                    "BEARISH_NORMAL_LONG_BLOCKED",
                    config,
                    blocking=True,
                    evidence={"regime_state": regime_state},
                )
            )
    if regime_state == "UNAVAILABLE":
        penalties.append(entry_penalty("REGIME_UNAVAILABLE", config, evidence={"regime_state": regime_state}))
    if confidence_state in {"LOW", "MEDIUM"} or (available_weight is not None and available_weight < Decimal("75")):
        penalties.append(
            entry_penalty(
                "LIMITED_REGIME_CONFIDENCE",
                config,
                evidence={
                    "confidence_state": confidence_state,
                    "available_weight_pct": available_weight,
                },
            )
        )
    if candidate_state == "EMERGING" and not truthy(setup_row.get("confirmed_eligible")):
        penalties.append(entry_penalty("EMERGING_ONLY", config, evidence={"candidate_state": candidate_state}))

    return penalties


def entry_penalty(
    code: str,
    config: EntryEvaluationConfig,
    *,
    blocking: bool | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    severity = config.penalties.severity_by_code.get(code, "INFO")
    is_blocking = blocking if blocking is not None else code in set(config.penalties.blocking_codes) or severity == "BLOCKING"
    return {
        "penalty_code": code,
        "severity": "BLOCKING" if is_blocking else severity,
        "blocking": is_blocking,
        "future_score_penalty_placeholder": "NOT_APPLIED",
        "evidence": evidence or {},
    }


def penalty_codes(penalties: Sequence[dict[str, Any]]) -> list[str]:
    return [str(item["penalty_code"]) for item in penalties]


def max_penalty_severity(penalties: Sequence[dict[str, Any]], config: EntryEvaluationConfig) -> str:
    if not penalties:
        return "INFO"
    order = {severity: index for index, severity in enumerate(config.penalties.severity_order)}
    return max((str(item.get("severity", "INFO")) for item in penalties), key=lambda severity: order.get(severity, 0))


def blocking_penalty_present(penalties: Sequence[dict[str, Any]]) -> bool:
    return any(truthy(item.get("blocking")) for item in penalties)


def severe_penalty_present(penalties: Sequence[dict[str, Any]]) -> bool:
    return any(str(item.get("severity", "")) in {"HIGH", "BLOCKING"} for item in penalties)


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"

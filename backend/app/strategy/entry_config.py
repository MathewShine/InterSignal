from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

ENTRY_EVALUATION_VERSION = "ENTRY_EVALUATION_V1"


@dataclass(frozen=True, slots=True)
class NeutralEntryRules:
    strong_setup_qualities: tuple[str, ...] = ("STRONG",)
    valid_setup_qualities: tuple[str, ...] = ("VALID",)
    valid_requires_confirmed_or_both: bool = True
    required_benchmark_rs: tuple[str, ...] = ("POSITIVE", "STRONG")
    disallowed_penalty_severities: tuple[str, ...] = ("HIGH", "BLOCKING")


@dataclass(frozen=True, slots=True)
class BearishExceptionalLongRules:
    required_setup_quality: str = "STRONG"
    required_candidate_states: tuple[str, ...] = ("CONFIRMED",)
    allow_both_eligible: bool = True
    required_benchmark_rs: tuple[str, ...] = ("STRONG",)
    required_volume: tuple[str, ...] = ("STRONG", "EXCEPTIONAL")
    required_breakout_states: tuple[str, ...] = ("CLOSE_ACCEPTED",)
    allowed_setup_type_flags: tuple[str, ...] = ("MOMENTUM_CONTINUATION",)
    required_candle_quality: tuple[str, ...] = ("GOOD", "STRONG")
    allowed_extension_risk: tuple[str, ...] = ("LOW", "MODERATE")
    required_consolidation_quality: tuple[str, ...] = ("GOOD", "STRONG")
    blocking_false_breakout_flags: tuple[str, ...] = (
        "POSSIBLE_FALSE_BREAKOUT",
        "INTRADAY_BREAK_FAILED",
        "UPPER_WICK_REJECTION",
    )


@dataclass(frozen=True, slots=True)
class RegimePermissionRules:
    bullish_permission: str = "NORMAL_LONG_ALLOWED"
    neutral_permission: str = "STRICT_LONG_ONLY"
    bearish_permission: str = "EXCEPTIONAL_LONG_ONLY"
    unavailable_permission: str = "INSUFFICIENT_REGIME_CONTEXT"
    unavailable_allows_max_readiness: str = "CONDITIONALLY_READY"


@dataclass(frozen=True, slots=True)
class ExtensionEntryRules:
    no_issue: tuple[str, ...] = ("LOW",)
    acceptable: tuple[str, ...] = ("MODERATE",)
    warning: tuple[str, ...] = ("HIGH",)
    blocking: tuple[str, ...] = ("EXTREME",)


@dataclass(frozen=True, slots=True)
class TechnicalRejectionRules:
    blocking_false_breakout_flags: tuple[str, ...] = (
        "POSSIBLE_FALSE_BREAKOUT",
        "INTRADAY_BREAK_FAILED",
    )
    warning_false_breakout_flags: tuple[str, ...] = (
        "CLOSE_REJECTION",
        "UPPER_WICK_REJECTION",
        "GAP_FADE",
    )
    blocking_breakout_states: tuple[str, ...] = ("FAILED_BREAK",)


@dataclass(frozen=True, slots=True)
class PenaltyRules:
    severity_order: tuple[str, ...] = ("INFO", "LOW", "MEDIUM", "HIGH", "BLOCKING")
    severity_by_code: dict[str, str] = field(
        default_factory=lambda: {
            "POOR_CANDLE_CONTEXT": "HIGH",
            "UPPER_WICK_REJECTION": "HIGH",
            "LOW_VOLUME_CONFIRMATION": "MEDIUM",
            "HIGH_EXTENSION": "MEDIUM",
            "EXTREME_EXTENSION": "BLOCKING",
            "OVERHEAD_RESISTANCE": "MEDIUM",
            "FALSE_BREAKOUT_WARNING": "HIGH",
            "NEUTRAL_REGIME": "LOW",
            "BEARISH_REGIME": "HIGH",
            "LIMITED_REGIME_CONFIDENCE": "LOW",
            "EMERGING_ONLY": "LOW",
            "WEAK_BENCHMARK_RS": "MEDIUM",
            "REGIME_UNAVAILABLE": "HIGH",
            "SETUP_WATCH_ONLY": "MEDIUM",
            "SETUP_POOR": "BLOCKING",
            "BEARISH_NORMAL_LONG_BLOCKED": "BLOCKING",
        }
    )
    blocking_codes: tuple[str, ...] = (
        "EXTREME_EXTENSION",
        "SETUP_POOR",
        "BEARISH_NORMAL_LONG_BLOCKED",
    )


@dataclass(frozen=True, slots=True)
class EntryEvidenceRules:
    strong_volume_states: tuple[str, ...] = ("STRONG", "EXCEPTIONAL")
    positive_volume_states: tuple[str, ...] = ("GOOD", "STRONG", "EXCEPTIONAL")
    positive_benchmark_rs_states: tuple[str, ...] = ("POSITIVE", "STRONG")
    strong_benchmark_rs_states: tuple[str, ...] = ("STRONG",)
    positive_candle_states: tuple[str, ...] = ("GOOD", "STRONG")
    strong_candle_states: tuple[str, ...] = ("STRONG",)


@dataclass(frozen=True, slots=True)
class EntryRankingRules:
    eligible_readiness_states: tuple[str, ...] = (
        "CONDITIONALLY_READY",
        "READY_FOR_RISK_EVALUATION",
        "EXCEPTIONAL_LONG_REVIEW",
    )


@dataclass(frozen=True, slots=True)
class EntryEvaluationConfig:
    entry_version: str = ENTRY_EVALUATION_VERSION
    entry_availability: str = "EOD"
    decision_use: str = "NEXT_SESSION_ENTRY_RESEARCH"
    strategy_direction: str = "LONG_ONLY"
    acceptable_setup_qualities: tuple[str, ...] = ("VALID", "STRONG")
    ready_readiness_states: tuple[str, ...] = (
        "CONDITIONALLY_READY",
        "READY_FOR_RISK_EVALUATION",
        "EXCEPTIONAL_LONG_REVIEW",
    )
    neutral: NeutralEntryRules = NeutralEntryRules()
    bearish_exceptional: BearishExceptionalLongRules = BearishExceptionalLongRules()
    regime: RegimePermissionRules = RegimePermissionRules()
    extension: ExtensionEntryRules = ExtensionEntryRules()
    technical_rejection: TechnicalRejectionRules = TechnicalRejectionRules()
    penalties: PenaltyRules = PenaltyRules()
    evidence: EntryEvidenceRules = EntryEvidenceRules()
    ranking: EntryRankingRules = EntryRankingRules()
    stock_sector_rs_status: str = "UNAVAILABLE"
    catalyst_context_status: str = "UNAVAILABLE"
    risk_reward_status: str = "NOT_EVALUATED"
    final_score_status: str = "NOT_IMPLEMENTED"
    notes: str = "Strategy V1 entry evaluation foundation only; no final score, risk/reward, signal, backtest, or execution."

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

STRATEGY_OUTCOME_VERSION = "STRATEGY_OUTCOME_V1"
SWING_DAILY_OUTCOME_PROFILE = "SWING_DAILY_OUTCOME_V1"
FUTURE_INTRADAY_OUTCOME_PROFILE = "INTRADAY_OUTCOME_V1"


@dataclass(frozen=True, slots=True)
class GapDiagnosticThresholds:
    flat_absolute_pct: Decimal = Decimal("0.25")
    material_gap_up_pct: Decimal = Decimal("2.00")
    extreme_gap_up_pct: Decimal = Decimal("5.00")


@dataclass(frozen=True, slots=True)
class StrategyOutcomeConfig:
    outcome_version: str = STRATEGY_OUTCOME_VERSION
    outcome_profile: str = SWING_DAILY_OUTCOME_PROFILE
    entry_model: str = "NEXT_SESSION_OPEN"
    max_hold_sessions: int = 4
    minimum_effective_reward_risk: Decimal = Decimal("1.50")
    research_capital_rupees: Decimal = Decimal("100000")
    max_risk_per_trade_pct: Decimal = Decimal("1.00")
    same_bar_ambiguity_policy: str = "AMBIGUOUS_EXCLUDE_FROM_DETERMINISTIC_CLASSIFICATION"
    mae_convention: str = "POSITIVE_ADVERSE_MAGNITUDE"
    transaction_cost_status: str = "NOT_MODELED"
    slippage_status: str = "NOT_MODELED"
    historical_execution_status: str = "NOT_EXECUTED"
    trade_signal_status: str = "SOURCE_FROZEN_RESEARCH_ONLY"
    gap_thresholds: GapDiagnosticThresholds = GapDiagnosticThresholds()
    comparison_cohorts: tuple[str, ...] = (
        "COUNTERFACTUAL_RESEARCH_COHORT",
        "EXCEPTIONAL_REVIEW_RESEARCH",
        "PREVIEW_RESEARCH_ONLY",
    )
    notes: str = (
        "Future-looking evaluation labels only. Frozen Strategy V1 score, stop, and target "
        "remain read-only; no signal generation, execution, optimization, or persistence."
    )

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

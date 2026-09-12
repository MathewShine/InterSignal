from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

TEMPORAL_RESEARCH_HARNESS_VERSION = "TEMPORAL_RESEARCH_HARNESS_V1"
TEMPORAL_VALIDATION_PROTOCOL_VERSION = "TEMPORAL_VALIDATION_PROTOCOL_V1"
TEMPORAL_RESEARCH_PROFILE = "SWING_TEMPORAL_VALIDATION_V1"
DEVELOPMENT_WINDOW_VERSION = "DEVELOPMENT_WINDOW_V1"
VALIDATION_WINDOW_VERSION = "VALIDATION_WINDOW_V1"

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
VALIDATION_START = date(2025, 1, 1)
# Frozen from the latest decision_date in the 3,296-row, forward-safe,
# frozen mechanical portfolio source-opportunity pool. A later date requires V2.
VALIDATION_TERMINAL_DATE = date(2026, 8, 13)

SEALED = "SEALED"
AUTHORIZED_TO_EVALUATE = "AUTHORIZED_TO_EVALUATE"
EVALUATED = "EVALUATED"
FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE = "FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE"

DEVELOPMENT_RUN = "DEVELOPMENT_RUN"
VALIDATION_RUN = "VALIDATION_RUN"
REPRODUCTION_RUN = "REPRODUCTION_RUN"
STRUCTURAL_METADATA = "STRUCTURAL_METADATA"
PERFORMANCE_ACCESS = "PERFORMANCE_ACCESS"

CONTINUOUS_CONTEXT_ANALYSIS = "CONTINUOUS_CONTEXT_ANALYSIS"
INDEPENDENT_WINDOW_BACKTEST = "INDEPENDENT_WINDOW_BACKTEST"

SAMPLE_SIZE_THRESHOLDS = (
    (30, "NOT_INFERENTIAL"),
    (100, "SMALL"),
    (300, "LIMITED"),
)


@dataclass(frozen=True, slots=True)
class TemporalResearchConfig:
    harness_version: str = TEMPORAL_RESEARCH_HARNESS_VERSION
    protocol_version: str = TEMPORAL_VALIDATION_PROTOCOL_VERSION
    profile: str = TEMPORAL_RESEARCH_PROFILE
    development_window_version: str = DEVELOPMENT_WINDOW_VERSION
    development_start: date = DEVELOPMENT_START
    development_end: date = DEVELOPMENT_END
    validation_window_version: str = VALIDATION_WINDOW_VERSION
    validation_start: date = VALIDATION_START
    validation_terminal_date: date = VALIDATION_TERMINAL_DATE
    partition_basis: str = "DECISION_DATE"
    validation_state: str = SEALED
    validation_pristine_status: str = FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE
    terminal_date_source: str = "MAX_DECISION_DATE_IN_FROZEN_FORWARD_SAFE_PORTFOLIO_SOURCE_POOL"
    terminal_date_extension_policy: str = "REQUIRES_VALIDATION_WINDOW_V2"
    split_selection_basis: str = "CALENDAR_BASED_DECLARED_BEFORE_STRATEGY_V2_EXPERIMENTS"
    development_initial_capital_rupees: Decimal = Decimal("100000")
    validation_initial_capital_rupees: Decimal = Decimal("100000")
    future_primary_evaluation_mode: str = INDEPENDENT_WINDOW_BACKTEST
    descriptive_context_mode: str = CONTINUOUS_CONTEXT_ANALYSIS
    maximum_validation_run_count: int = 1
    required_cost_model: str = "INDIA_EQUITY_COST_MODEL_V1"
    required_cost_profile: str = "NSE_CASH_DELIVERY_RESEARCH_V1"
    future_validation_requires_nonzero_costs: bool = True
    score_date_field: str = "trading_date"
    outcome_date_field: str = "decision_date"
    backtest_source_date_field: str = "decision_date"
    categorical_low_shift_pp: Decimal = Decimal("5")
    categorical_high_shift_pp: Decimal = Decimal("10")
    standardized_low_shift: Decimal = Decimal("0.10")
    standardized_high_shift: Decimal = Decimal("0.25")

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        return canonical_hash(self.snapshot())


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    return value


def canonical_hash(value: Any) -> str:
    payload = json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_sample_size(count: int) -> str:
    for upper, label in SAMPLE_SIZE_THRESHOLDS:
        if count < upper:
            return label
    return "ADEQUATE_FOR_DESCRIPTION"


DEFAULT_TEMPORAL_CONFIG = TemporalResearchConfig()
# Regression guard for the source-controlled V1 contract above.
EXPECTED_HARNESS_CONFIG_HASH = "20c656c24a5b6f328ca0d0cae0ce5daf042fb2e70dca5a2aea28eba5b7594a0e"

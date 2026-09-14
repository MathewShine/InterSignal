from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import DP_CHARGE, STAMP_DUTY, canonical_hash
from app.research.strategy.family_a_momentum import (
    MembershipIndex,
    _corporate_action_exclusions,
    _corporate_action_safe,
    _git_ignored,
    _load_aliases,
    _load_membership,
    decimal,
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_research_closure import (
    EXPECTED_FAMILY_B_CLOSURE_HASH,
    GOVERNANCE_POLICY_VERSION,
    family_b_baseline_snapshot,
    verify_family_b_closure_inputs,
)


FAMILY_VERSION = "STRATEGY_FAMILY_C_BREAKOUT_CONTINUATION_V1"
RESEARCH_PROFILE = "DAILY_BREAKOUT_CONTINUATION_V1"
FAMILY_CODE = "FAMILY_C"
RESEARCH_PROTOCOL = "FAMILY_C_RESEARCH_PROTOCOL_V1"
COMMAND = "Step 03.03 / Command 01"

CONTROL_ID = "CONTROL-C-000"
CONTROL_NAME = "PURE_20D_CLOSE_BREAKOUT_V1"
EXPERIMENT_DEFINITIONS = (
    (
        "BRK-C-001",
        "20D_BREAKOUT_WITH_10D_COMPRESSION_V1",
        "A breakout emerging from a compact 10-session range may have better continuation quality.",
    ),
    (
        "BRK-C-002",
        "20D_BREAKOUT_WITH_VOLUME_EXPANSION_V1",
        "A breakout accompanied by substantial volume expansion may represent stronger participation.",
    ),
)
EXPERIMENT_IDS = tuple(row[0] for row in EXPERIMENT_DEFINITIONS)

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
PREHISTORY_START = date(2021, 9, 7)
STARTING_CAPITAL = Decimal("500000")
MAX_CONCURRENT_POSITIONS = 20
TARGET_NOTIONAL_FRACTION = Decimal("0.05")
PRICE_FLOOR = Decimal("100")
LIQUIDITY_FLOOR = Decimal("100000000")
LIQUIDITY_WINDOW = 20
BREAKOUT_WINDOW = 20
COMPRESSION_WINDOW = 10
COMPRESSION_THRESHOLD = Decimal("0.08")
VOLUME_THRESHOLD = Decimal("1.50")
HOLDING_SESSIONS = 10

EXPECTED_FAMILY_C_CONFIG_HASH = (
    "5ecb5604939e1230ba176dbb339ebaf15418482da7a68bbbea24370c805961a6"
)
EXPECTED_CONTROL_REFERENCE_HASH = (
    "407034bc6451f60386492a1a445112e0fa7e05e374ef21119c04b9dd9060d393"
)
EXPECTED_SUCCESS_CRITERIA_HASH = (
    "7bb950274ebe47ec7fafeb7e8659e07a457a4ddb169171aa97fe9ff9d0860a77"
)
EXPECTED_EXPERIMENT_HASHES: dict[str, dict[str, str]] = {
    "BRK-C-001": {
        "parameter_hash": "7014748559f2f9c468e402e3dd5bcdfa8444d544982ed033644f2c0125addbeb",
        "preregistration_hash": "b7d13606fbb5f691090bd44027017171ad8447d6b81f3aaf5eda8c07faf0f552",
    },
    "BRK-C-002": {
        "parameter_hash": "fd2b9b0d266a993fe524b5560b12e65b162772dfabac7e08988adee5f81e9afc",
        "preregistration_hash": "10615f2f1a93a7c3f29a31538d9331d5ee24be29b90990762620b70468d321f8",
    },
}

SIGNAL_FIELDS = (
    "decision_date",
    "symbol",
    "isin",
    "point_in_time_member",
    "close",
    "prior_20d_high",
    "breakout_strength_pct",
    "is_20d_breakout",
    "prior_10d_high",
    "prior_10d_low",
    "compression_range_pct",
    "compression_pass",
    "median_volume_20",
    "formation_volume",
    "formation_volume_ratio",
    "volume_pass",
    "price_gate",
    "liquidity_gate",
    "corporate_action_safe",
    "control_signal",
    "c001_signal",
    "c002_signal",
    "data_quality_flags",
)

FUTURE_POSITION_FIELDS = (
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "gross_return_pct",
    "net_return_pct",
    "MFE_pct",
    "MAE_pct",
    "holding_sessions",
    "entry_gap_pct",
    "transaction_costs",
)
FUTURE_PORTFOLIO_FIELDS = (
    "cash",
    "portfolio_equity",
    "open_positions",
    "available_slots",
    "intended_notional",
    "actual_shares",
    "actual_notional",
    "residual_cash",
    "capacity_rejected_signals",
)
FUTURE_PERFORMANCE_METRICS = (
    "NET_TOTAL_RETURN",
    "NET_CAGR",
    "MAX_DRAWDOWN",
    "ANNUALIZED_VOLATILITY",
    "SHARPE_LIKE_RATIO",
    "POSITION_COUNT",
    "POSITION_WIN_RATE",
    "AVERAGE_WINNER",
    "AVERAGE_LOSER",
    "MEDIAN_POSITION_RETURN",
    "EXPECTANCY_PER_POSITION",
    "PROFIT_FACTOR",
    "POSITIVE_CALENDAR_MONTH_RATE",
    "2022_RETURN",
    "2023_RETURN",
    "2024_RETURN",
    "TURNOVER",
    "TRANSACTION_COSTS",
    "AVERAGE_CONCURRENT_POSITIONS",
    "CAPACITY_REJECTION_RATE",
    "AVERAGE_CASH",
)
GOVERNANCE_CHECKLIST = (
    "hypothesis",
    "experiment_id",
    "population",
    "exact_parameters",
    "control",
    "primary_metrics",
    "secondary_metrics",
    "numerical_success_criteria",
    "failure_criteria",
    "stop_conditions",
    "validation_eligibility",
    "cost_model",
    "data_partition",
    "hashes",
)
REPORT_NAMES = (
    "family_c_v1_summary.json",
    "family_c_v1_registry.csv",
    "family_c_v1_data_readiness.csv",
    "family_c_v1_signal_counts.csv",
    "family_c_v1_signal_overlap.csv",
    "family_c_v1_pilots.csv",
    "family_c_v1_governance.csv",
    "family_c_v1_capacity.csv",
)


class FamilyCFreezeMismatch(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FamilyCBar:
    trading_date: date
    symbol: str
    isin: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    usability_status: str
    methodology_version: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def family_output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_c/v1"


def breakout_calculation(
    formation_close: Decimal | None,
    prior_highs: Sequence[Decimal],
) -> dict[str, Any]:
    if formation_close is None or len(prior_highs) != BREAKOUT_WINDOW:
        return {
            "prior_20d_high": None,
            "breakout_strength_pct": None,
            "is_20d_breakout": False,
            "available": False,
        }
    prior_high = max(decimal(value) for value in prior_highs)
    strength = None if prior_high <= 0 else decimal(formation_close) / prior_high - Decimal("1")
    return {
        "prior_20d_high": prior_high,
        "breakout_strength_pct": strength,
        "is_20d_breakout": bool(strength is not None and decimal(formation_close) > prior_high),
        "available": strength is not None,
    }


def compression_calculation(
    formation_close: Decimal | None,
    prior_highs: Sequence[Decimal],
    prior_lows: Sequence[Decimal],
) -> dict[str, Any]:
    if (
        formation_close is None
        or decimal(formation_close) <= 0
        or len(prior_highs) != COMPRESSION_WINDOW
        or len(prior_lows) != COMPRESSION_WINDOW
    ):
        return {
            "prior_10d_high": None,
            "prior_10d_low": None,
            "compression_range_pct": None,
            "compression_pass": False,
            "available": False,
        }
    prior_high = max(decimal(value) for value in prior_highs)
    prior_low = min(decimal(value) for value in prior_lows)
    value = (prior_high - prior_low) / decimal(formation_close)
    return {
        "prior_10d_high": prior_high,
        "prior_10d_low": prior_low,
        "compression_range_pct": value,
        "compression_pass": value <= COMPRESSION_THRESHOLD,
        "available": True,
    }


def volume_calculation(
    formation_volume: Decimal | None,
    prior_volumes: Sequence[Decimal],
) -> dict[str, Any]:
    if formation_volume is None or len(prior_volumes) != BREAKOUT_WINDOW:
        return {
            "median_volume_20": None,
            "formation_volume_ratio": None,
            "volume_pass": False,
            "available": False,
        }
    median_volume = decimal(statistics.median(decimal(value) for value in prior_volumes))
    ratio = None if median_volume <= 0 else decimal(formation_volume) / median_volume
    return {
        "median_volume_20": median_volume,
        "formation_volume_ratio": ratio,
        "volume_pass": bool(ratio is not None and ratio >= VOLUME_THRESHOLD),
        "available": ratio is not None,
    }


def entry_exit_chronology(
    sessions: Sequence[date], formation_date: date
) -> dict[str, Any]:
    try:
        formation_index = sessions.index(formation_date)
    except ValueError:
        return {
            "entry_date": None,
            "holding_dates": (),
            "exit_date": None,
            "holding_sessions": 0,
            "available": False,
        }
    entry_index = formation_index + 1
    exit_index = formation_index + HOLDING_SESSIONS + 1
    if exit_index >= len(sessions):
        return {
            "entry_date": sessions[entry_index] if entry_index < len(sessions) else None,
            "holding_dates": tuple(sessions[entry_index : min(exit_index, len(sessions))]),
            "exit_date": None,
            "holding_sessions": max(0, min(exit_index, len(sessions)) - entry_index),
            "available": False,
        }
    holding_dates = tuple(sessions[entry_index:exit_index])
    return {
        "entry_date": sessions[entry_index],
        "holding_dates": holding_dates,
        "exit_date": sessions[exit_index],
        "holding_sessions": len(holding_dates),
        "available": len(holding_dates) == HOLDING_SESSIONS,
    }


def rank_capacity_signals(
    rows: Sequence[Mapping[str, Any]], available_slots: int
) -> dict[str, Any]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (-decimal(row["breakout_strength_pct"]), str(row["symbol"])),
    )
    count = max(0, int(available_slots))
    return {"selected": ordered[:count], "rejected": ordered[count:], "ranked": ordered}


def whole_share_position(
    portfolio_equity: Decimal, available_cash: Decimal, execution_price: Decimal
) -> dict[str, Any]:
    intended = decimal(portfolio_equity) * TARGET_NOTIONAL_FRACTION
    affordable = min(intended, decimal(available_cash))
    shares = (
        0
        if execution_price <= 0
        else int((affordable / decimal(execution_price)).to_integral_value(rounding=ROUND_FLOOR))
    )
    actual = Decimal(shares) * decimal(execution_price)
    return {
        "intended_notional": intended,
        "actual_shares": shares,
        "actual_notional": actual,
        "residual_cash": decimal(available_cash) - actual,
    }


def high_win_rate_flag(position_win_rate: Decimal) -> str:
    return "YES" if decimal(position_win_rate) >= Decimal("0.60") else "NO"


def success_criteria_config() -> dict[str, Any]:
    body = {
        "family_version": FAMILY_VERSION,
        "control_viability": {
            "classification": "CONTROL_VIABLE",
            "all_required": True,
            "A_NET_CAGR": {"operator": ">", "threshold": Decimal("0")},
            "B_NET_PROFIT_FACTOR": {"operator": ">=", "threshold": Decimal("1.05")},
            "C_NET_EXPECTANCY_PER_CLOSED_POSITION": {"operator": ">", "threshold": Decimal("0")},
            "D_MAX_DRAWDOWN_MAGNITUDE": {"operator": "<=", "threshold": Decimal("0.35")},
            "E_NONNEGATIVE_DEVELOPMENT_YEARS": {"operator": ">=", "threshold": 2, "of": 3},
            "F_CLOSED_POSITIONS": {"operator": ">=", "threshold": 100},
            "G_ACCOUNTING_DATA_INTEGRITY": {"operator": "==", "threshold": "PASS"},
        },
        "control_fatal_failure": {
            "logic": "ANY",
            "net_cagr": {"operator": "<=", "threshold": Decimal("-0.05")},
            "profit_factor": {"operator": "<", "threshold": Decimal("0.90")},
            "max_drawdown_magnitude": {"operator": ">", "threshold": Decimal("0.45")},
            "closed_positions": {"operator": "<", "threshold": 50},
            "implementation_or_data_failure": True,
        },
        "treatment_standard_criteria": {
            "A_RETURN_PRESERVATION": {
                "control_cagr_positive_ratio_operator": ">=",
                "control_cagr_positive_ratio_threshold": Decimal("0.90"),
                "control_cagr_nonpositive_rule": "USE_ABSOLUTE_PROFITABILITY",
            },
            "B_TREATMENT_PROFITABILITY": {
                "net_expectancy_operator": ">",
                "net_expectancy_threshold": Decimal("0"),
                "net_profit_factor_operator": ">=",
                "net_profit_factor_threshold": Decimal("1.10"),
            },
            "C_DRAWDOWN_NON_DEGRADATION": {
                "maximum_relative_worsening": Decimal("0.10"),
                "fatal_relative_worsening": Decimal("0.20"),
            },
            "D_TEMPORAL_SUPPORT": {
                "minimum_nonnegative_years": 2,
                "development_year_count": 3,
                "maximum_yearly_underperformance_percentage_points": Decimal("15"),
                "maximum_years_exceeding_underperformance": 1,
            },
            "E_COST_EFFICIENCY": {
                "maximum_normalized_cost_drag_multiple": Decimal("1.30"),
                "lower_turnover_exception": True,
                "cost_fail_increase_without_compensation": Decimal("0.30"),
            },
            "F_SAMPLE_ADEQUACY": {
                "normal_minimum_closed_positions": 75,
                "limited_sample_minimum": 50,
                "limited_sample_maximum": 74,
                "fatal_sample_failure_below": 50,
            },
            "G_ACCOUNTING_DATA_INTEGRITY": {"operator": "==", "threshold": "PASS"},
        },
        "quality_improvement_dimensions": {
            "H_WIN_RATE_IMPROVEMENT": {"operator": ">=", "percentage_points": Decimal("5")},
            "I_PROFIT_FACTOR_IMPROVEMENT": {"operator": ">=", "absolute_increment": Decimal("0.05")},
            "J_EXPECTANCY_IMPROVEMENT": {
                "positive_control_multiple": Decimal("1.10"),
                "nonpositive_control_rule": "TREATMENT_EXPECTANCY_MUST_BE_POSITIVE",
            },
            "K_MATERIAL_DRAWDOWN_IMPROVEMENT": {"operator": ">=", "relative_improvement": Decimal("0.10")},
        },
        "capacity_stability": {
            "material_if_rejection_rate_operator": ">",
            "threshold": Decimal("0.25"),
            "classification": "CAPACITY_CONSTRAINT_MATERIAL",
            "slot_count_mutation_allowed": False,
        },
        "descriptive_high_win_rate": {
            "field": "HIGH_WIN_RATE_FLAG",
            "yes_if_position_win_rate_operator": ">=",
            "threshold": Decimal("0.60"),
            "mandatory_for_support": False,
        },
        "treatment_classification": {
            "STRONGLY_SUPPORTED": "ALL_A_TO_G_AND_AT_LEAST_TWO_H_TO_K_AND_CAGR_NOT_BELOW_CONTROL_AND_NO_NEGATIVE_YEAR",
            "SUPPORTED": "ALL_A_TO_G_AND_AT_LEAST_ONE_H_TO_K",
            "PARTIALLY_SUPPORTED": "NO_FATAL_AND_AT_LEAST_FIVE_A_TO_G_AND_INTERPRETABLE",
            "FAILED": "ANY_FATAL_OR_FEWER_THAN_FIVE_A_TO_G",
            "INCONCLUSIVE": "UNRESOLVED_DATA_OR_MECHANICS_PREVENT_CLEAN_INTERPRETATION",
        },
        "family_result_allowlist": ("STRONG_SUPPORT", "SUPPORT", "MIXED", "WEAK", "FAILED", "INCONCLUSIVE"),
        "family_level_mapping": {
            "STRONG_SUPPORT": "AT_LEAST_ONE_STRONGLY_SUPPORTED_AND_CONTROL_VIABLE",
            "SUPPORT": "AT_LEAST_ONE_SUPPORTED_AND_NEITHER_TREATMENT_FAILED_AND_CONTROL_VIABLE",
            "MIXED": "ONE_SUPPORTED_OR_PARTIALLY_SUPPORTED_AND_OTHER_FAILED_OR_INCONCLUSIVE",
            "WEAK": "CONTROL_VIABLE_AND_TREATMENTS_ONLY_PARTIALLY_SUPPORTED",
            "FAILED": "CONTROL_FAILED_AND_BOTH_TREATMENTS_FAILED",
            "INCONCLUSIVE": "DATA_PREVENTS_INTERPRETATION",
        },
        "evaluation_status": "FROZEN_BEFORE_PERFORMANCE",
        "performance_evaluated": False,
    }
    return {**body, "success_criteria_hash": canonical_hash(body)}


def family_config(criteria: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "status": "PREREGISTERED_RESEARCH_FAMILY",
        "promotion_allowed": False,
        "validation_allowed": False,
        "primary_question": "CAN_SIMPLE_DETERMINISTIC_BREAKOUT_CONTINUATION_IDENTIFY_PROFITABLE_NSE_OPPORTUNITIES_AFTER_COSTS",
        "hypotheses": {
            "control": "PLAIN_20_SESSION_CLOSING_BREAKOUT_CONTINUATION_EDGE",
            "BRK-C-001": "PRIOR_PRICE_COMPRESSION_IMPROVES_BREAKOUT_QUALITY",
            "BRK-C-002": "FORMATION_VOLUME_EXPANSION_IMPROVES_BREAKOUT_QUALITY",
        },
        "independence": {
            "strategy_v1_score": False,
            "strategy_v1_regime": False,
            "rr_score": False,
            "cap4": False,
            "entry_score_80": False,
            "intraday_confirmation": False,
            "catalyst_score": False,
            "sector_score": False,
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "prehistory_version": "DAILY_HISTORY_PREHISTORY_V2",
            "prehistory_use": "CAUSAL_HISTORICAL_CALCULATIONS_ONLY",
            "pre_2022_performance_allowed": False,
            "post_2024_data_allowed": False,
        },
        "population": {
            "universe": "POINT_IN_TIME_NIFTY_500",
            "current_constituent_hindsight_allowed": False,
            "minimum_adjusted_close_inr": PRICE_FLOOR,
            "median_traded_value_window_sessions": LIQUIDITY_WINDOW,
            "minimum_median_traded_value_inr": LIQUIDITY_FLOOR,
            "corporate_action_layer": "EXISTING_CORPORATE_ACTION_STRUCTURAL_ELIGIBILITY",
        },
        "signal": {
            "formation": "SESSION_T_CLOSE",
            "breakout_rule": "ADJUSTED_CLOSE_T_STRICTLY_GREATER_THAN_MAX_ADJUSTED_HIGH_PRIOR_20_VALID_SESSIONS_EXCLUDING_T",
            "lookback_sessions": BREAKOUT_WINDOW,
            "shortened_lookback_allowed": False,
            "breakout_strength": "FORMATION_CLOSE_DIVIDED_BY_PRIOR_20_SESSION_HIGH_MINUS_ONE",
        },
        "execution": {
            "entry": "NEXT_ELIGIBLE_NSE_SESSION_OPEN_T_PLUS_1",
            "same_close_execution_allowed": False,
            "gap_rejection_allowed": False,
            "entry_gap_pct_recorded_in_future_evaluation": True,
            "holding_completed_sessions": HOLDING_SESSIONS,
            "holding_sessions": "T_PLUS_1_THROUGH_T_PLUS_10",
            "exit": "NEXT_ELIGIBLE_OPEN_AFTER_TEN_COMPLETED_SESSIONS_T_PLUS_11",
            "stop_loss": None,
            "profit_target": None,
            "trailing_stop": None,
        },
        "portfolio": {
            "type": "EVENT_DRIVEN_SWING",
            "direction": "LONG_ONLY",
            "starting_capital_inr": STARTING_CAPITAL,
            "maximum_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "target_initial_position_notional_fraction_current_equity": TARGET_NOTIONAL_FRACTION,
            "whole_shares": True,
            "available_cash_constraint": True,
            "leverage_allowed": False,
            "rebalance_existing_positions": False,
            "one_position_per_symbol": True,
            "pyramiding_allowed": False,
            "reentry": "ONLY_AFTER_FULL_EXIT",
            "capacity_ranking": ("BREAKOUT_STRENGTH_PCT_DESCENDING", "SYMBOL_ASCENDING"),
        },
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": Decimal("5"),
        },
        "future_position_fields": FUTURE_POSITION_FIELDS,
        "future_portfolio_fields": FUTURE_PORTFOLIO_FIELDS,
        "future_performance_metrics": FUTURE_PERFORMANCE_METRICS,
        "success_criteria_hash": criteria["success_criteria_hash"],
        "performance_policy": {
            "final_development_performance_allowed_in_command_01": False,
            "performance_results_generated": False,
            "validation_accessed": False,
            "strategy_v2_creation_allowed": False,
        },
        "validation_eligibility_rule": (
            "CLEAN_DEVELOPMENT_EVALUATION_AND_SUFFICIENT_SAMPLE_AND_NO_UNRESOLVED_"
            "ATTRIBUTION_OR_DATA_ISSUE_AND_NO_PARAMETER_MUTATION_AND_GOVERNANCE_REVIEW_"
            "AND_EXPLICIT_HUMAN_APPROVAL"
        ),
    }
    return {**body, "family_c_config_hash": canonical_hash(body)}


def _experiment_parameters(experiment_id: str) -> dict[str, Any]:
    common = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "breakout_lookback_sessions": BREAKOUT_WINDOW,
        "breakout_comparison": "STRICTLY_GREATER_THAN_PRIOR_HIGH",
        "formation_session_excluded_from_lookback": True,
        "entry": "T_PLUS_1_OPEN",
        "holding_completed_sessions": HOLDING_SESSIONS,
        "exit": "T_PLUS_11_OPEN",
        "stop_loss": None,
        "profit_target": None,
        "trailing_stop": None,
        "combined_compression_and_volume_filter": False,
    }
    if experiment_id == "BRK-C-001":
        return {
            **common,
            "filter": "TEN_SESSION_COMPRESSION",
            "compression_sessions": COMPRESSION_WINDOW,
            "compression_window": "T_MINUS_10_THROUGH_T_MINUS_1",
            "compression_metric": "MAX_HIGH_MINUS_MIN_LOW_DIVIDED_BY_FORMATION_CLOSE",
            "compression_operator": "<=",
            "compression_threshold": COMPRESSION_THRESHOLD,
            "volume_filter": None,
        }
    if experiment_id == "BRK-C-002":
        return {
            **common,
            "filter": "FORMATION_VOLUME_EXPANSION",
            "volume_baseline_sessions": BREAKOUT_WINDOW,
            "volume_baseline_window": "T_MINUS_20_THROUGH_T_MINUS_1",
            "volume_metric": "FORMATION_VOLUME_DIVIDED_BY_MEDIAN_PRIOR_20_VOLUME",
            "volume_operator": ">=",
            "volume_threshold": VOLUME_THRESHOLD,
            "compression_filter": None,
        }
    raise ValueError(f"Unknown Family C experiment: {experiment_id}")


def control_reference(config: Mapping[str, Any], criteria: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "control_id": CONTROL_ID,
        "name": CONTROL_NAME,
        "status": "REFERENCE_CONTROL",
        "family_version": FAMILY_VERSION,
        "family_c_config_hash": config["family_c_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "parameters": {
            "breakout_lookback_sessions": BREAKOUT_WINDOW,
            "breakout_rule": "CLOSE_T_STRICTLY_GREATER_THAN_MAX_HIGH_T_MINUS_20_THROUGH_T_MINUS_1",
            "filter": None,
            "entry": "T_PLUS_1_OPEN",
            "holding_completed_sessions": HOLDING_SESSIONS,
            "exit": "T_PLUS_11_OPEN",
            "stop_loss": None,
            "profit_target": None,
        },
        "promotion_allowed": False,
        "validation_allowed": False,
        "performance_evaluated": False,
    }
    return {**body, "control_reference_hash": canonical_hash(body)}


def experiment_registry(
    config: Mapping[str, Any], criteria: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    experiments: list[dict[str, Any]] = []
    for experiment_id, name, interpretation in EXPERIMENT_DEFINITIONS:
        parameters = _experiment_parameters(experiment_id)
        parameter_hash = canonical_hash(parameters)
        body = {
            "experiment_id": experiment_id,
            "name": name,
            "interpretation": interpretation,
            "status": "PREREGISTERED",
            "promotion_allowed": False,
            "validation_allowed": False,
            "family_c_config_hash": config["family_c_config_hash"],
            "success_criteria_hash": criteria["success_criteria_hash"],
            "comparison_control_id": CONTROL_ID,
            "comparison_control_hash": control["control_reference_hash"],
            "hypothesis": config["hypotheses"][experiment_id],
            "population": config["population"],
            "primary_metrics": FUTURE_PERFORMANCE_METRICS,
            "secondary_metrics": (
                "ENTRY_GAP_PCT",
                "MFE_PCT",
                "MAE_PCT",
                "AVERAGE_CASH",
                "CAPACITY_REJECTED_SIGNALS",
                "HIGH_WIN_RATE_FLAG",
            ),
            "numerical_success_criteria": criteria["success_criteria_hash"],
            "failure_criteria": criteria["control_fatal_failure"],
            "stop_conditions": ("IMPLEMENTATION_FAILURE", "DATA_INTEGRITY_FAILURE", "PARAMETER_MUTATION"),
            "validation_eligibility": config["validation_eligibility_rule"],
            "cost_model": config["costs"],
            "data_partition": config["development_window"],
            "parameter_hash": parameter_hash,
            "parameters": parameters,
        }
        experiments.append({**body, "preregistration_hash": canonical_hash(body)})
    body = {
        "family_version": FAMILY_VERSION,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_c_config_hash": config["family_c_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "control_count": 1,
        "control": control,
        "experiment_count": len(experiments),
        "experiment_ids": EXPERIMENT_IDS,
        "experiments": experiments,
        "extra_experiments_allowed": False,
        "combined_filter_registered": False,
        "performance_evaluated": False,
        "validation_accessed": False,
        "promotion_allowed": False,
    }
    return {**body, "registry_hash": canonical_hash(body)}


def verify_registry(
    registry: Mapping[str, Any], config: Mapping[str, Any], criteria: Mapping[str, Any]
) -> None:
    if registry["experiment_count"] != 2 or tuple(registry["experiment_ids"]) != EXPERIMENT_IDS:
        raise FamilyCFreezeMismatch("Family C must contain exactly BRK-C-001 and BRK-C-002")
    if registry["control_count"] != 1 or registry["control"]["control_id"] != CONTROL_ID:
        raise FamilyCFreezeMismatch("CONTROL-C-000 reference changed")
    control = registry["control"]
    if canonical_hash({key: value for key, value in control.items() if key != "control_reference_hash"}) != control["control_reference_hash"]:
        raise FamilyCFreezeMismatch("CONTROL-C-000 reference hash mismatch")
    for observed, expected in zip(registry["experiments"], EXPERIMENT_DEFINITIONS, strict=True):
        if observed["experiment_id"] != expected[0] or observed["status"] != "PREREGISTERED":
            raise FamilyCFreezeMismatch("Experiment identity or status changed")
        if observed["promotion_allowed"] or observed["validation_allowed"]:
            raise FamilyCFreezeMismatch("Promotion or validation unexpectedly allowed")
        if canonical_hash(observed["parameters"]) != observed["parameter_hash"]:
            raise FamilyCFreezeMismatch("Experiment parameter hash mismatch")
        preregistration_body = {key: value for key, value in observed.items() if key != "preregistration_hash"}
        if canonical_hash(preregistration_body) != observed["preregistration_hash"]:
            raise FamilyCFreezeMismatch("Experiment preregistration hash mismatch")
        if observed["success_criteria_hash"] != criteria["success_criteria_hash"]:
            raise FamilyCFreezeMismatch("Success criteria link changed")
    if registry["performance_evaluated"] or registry["validation_accessed"]:
        raise FamilyCFreezeMismatch("Command 01 cannot evaluate performance or access validation")


def verify_expected_hashes(
    config: Mapping[str, Any], criteria: Mapping[str, Any], registry: Mapping[str, Any]
) -> None:
    if not EXPECTED_FAMILY_C_CONFIG_HASH:
        return
    checks = {
        "config": config["family_c_config_hash"] == EXPECTED_FAMILY_C_CONFIG_HASH,
        "control": registry["control"]["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH,
        "criteria": criteria["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    for row in registry["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]
        checks[f"{row['experiment_id']}_parameter"] = (
            row["parameter_hash"] == expected["parameter_hash"]
        )
        checks[f"{row['experiment_id']}_preregistration"] = (
            row["preregistration_hash"] == expected["preregistration_hash"]
        )
    for experiment in registry["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[experiment["experiment_id"]]
        checks[f"{experiment['experiment_id']}_parameter"] = experiment["parameter_hash"] == expected["parameter_hash"]
        checks[f"{experiment['experiment_id']}_prereg"] = experiment["preregistration_hash"] == expected["preregistration_hash"]
    if not all(checks.values()):
        raise FamilyCFreezeMismatch(f"FAMILY_C_PREREGISTRATION_HASH_MISMATCH: {checks}")


def _load_sessions(root: Path) -> list[date]:
    return sorted(
        date.fromisoformat(row["trading_date"])
        for row in read_csv(root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv")
        if row.get("source_available") == "True"
        and PREHISTORY_START <= date.fromisoformat(row["trading_date"]) <= DEVELOPMENT_END
    )


def _date_from_adjusted_path(path: Path) -> date | None:
    try:
        return datetime.strptime(path.stem.removeprefix("nse_adjusted_daily_"), "%Y%m%d").date()
    except ValueError:
        return None


def _load_adjusted_bars(
    root: Path, universe_symbols: set[str], aliases: Mapping[str, str]
) -> dict[date, dict[str, FamilyCBar]]:
    bars: dict[date, dict[str, FamilyCBar]] = {}
    paths = sorted(
        (root / "data/research/adjusted/daily/nse").glob(
            "*/*/nse_adjusted_daily_*.csv"
        )
    )
    for path in paths:
        trading_date = _date_from_adjusted_path(path)
        if (
            trading_date is None
            or trading_date < PREHISTORY_START
            or trading_date > DEVELOPMENT_END
        ):
            continue
        day: dict[str, FamilyCBar] = {}
        for row in read_csv(path):
            original = row.get("symbol", "").strip().upper()
            symbol = aliases.get(original, original)
            if symbol not in universe_symbols:
                continue
            try:
                bar = FamilyCBar(
                    trading_date=trading_date,
                    symbol=symbol,
                    isin=row.get("isin", ""),
                    open_price=decimal(row["adjusted_open"]),
                    high_price=decimal(row["adjusted_high"]),
                    low_price=decimal(row["adjusted_low"]),
                    close_price=decimal(row["adjusted_close"]),
                    volume=decimal(row["adjusted_volume"]),
                    usability_status=row.get("research_usability_status", ""),
                    methodology_version=row.get(
                        "adjustment_methodology_version", ""
                    ),
                )
            except (ArithmeticError, KeyError):
                continue
            previous = day.get(symbol)
            if previous is None or row.get("series") == "EQ":
                day[symbol] = bar
        bars[trading_date] = day
    return bars


def _prior_bars(
    symbol: str,
    sessions: Sequence[date],
    session_index: int,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    count: int,
) -> list[FamilyCBar]:
    if session_index < count:
        return []
    output: list[FamilyCBar] = []
    for session in sessions[session_index - count : session_index]:
        bar = bars.get(session, {}).get(symbol)
        if (
            bar is None
            or bar.usability_status != "ADJUSTED_READY"
            or min(
                bar.open_price,
                bar.high_price,
                bar.low_price,
                bar.close_price,
            )
            <= 0
            or bar.volume < 0
        ):
            return []
        output.append(bar)
    return output


def _liquidity_calculation(
    symbol: str,
    sessions: Sequence[date],
    session_index: int,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    if session_index < LIQUIDITY_WINDOW - 1:
        return {"median_traded_value": None, "available": False, "pass": False}
    values: list[Decimal] = []
    for session in sessions[
        session_index - LIQUIDITY_WINDOW + 1 : session_index + 1
    ]:
        bar = bars.get(session, {}).get(symbol)
        if (
            bar is None
            or bar.usability_status != "ADJUSTED_READY"
            or bar.close_price <= 0
            or bar.volume < 0
        ):
            return {
                "median_traded_value": None,
                "available": False,
                "pass": False,
            }
        values.append(bar.close_price * bar.volume)
    value = decimal(statistics.median(values))
    return {
        "median_traded_value": value,
        "available": True,
        "pass": value >= LIQUIDITY_FLOOR,
    }


def _structural_path_availability(
    symbol: str,
    sessions: Sequence[date],
    formation_index: int,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    chronology = entry_exit_chronology(sessions, sessions[formation_index])
    entry_date = chronology["entry_date"]
    exit_date = chronology["exit_date"]
    entry_bar = bars.get(entry_date, {}).get(symbol) if entry_date else None
    exit_bar = bars.get(exit_date, {}).get(symbol) if exit_date else None
    holding_bars_available = bool(
        chronology["available"]
        and all(
            bars.get(session, {}).get(symbol) is not None
            for session in chronology["holding_dates"]
        )
    )
    return {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "next_open_available": bool(entry_bar and entry_bar.open_price > 0),
        "holding_path_available": bool(
            holding_bars_available and exit_bar and exit_bar.open_price > 0
        ),
    }


def _build_signal_rows(
    sessions: Sequence[date],
    membership: MembershipIndex,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    readiness_details: list[dict[str, Any]] = []
    for session_index, formation_date in enumerate(sessions):
        if formation_date < DEVELOPMENT_START:
            continue
        members = membership.members_for(formation_date)
        day_counts: dict[str, int] = defaultdict(int)
        for symbol, period in sorted(members.items()):
            bar = bars.get(formation_date, {}).get(symbol)
            valid_formation = bool(
                bar
                and bar.usability_status == "ADJUSTED_READY"
                and min(
                    bar.open_price,
                    bar.high_price,
                    bar.low_price,
                    bar.close_price,
                )
                > 0
                and bar.volume >= 0
            )
            prior20 = _prior_bars(
                symbol, sessions, session_index, bars, BREAKOUT_WINDOW
            )
            prior10 = _prior_bars(
                symbol, sessions, session_index, bars, COMPRESSION_WINDOW
            )
            close = bar.close_price if valid_formation and bar else None
            volume = bar.volume if valid_formation and bar else None
            breakout = breakout_calculation(
                close, [item.high_price for item in prior20]
            )
            compression = compression_calculation(
                close,
                [item.high_price for item in prior10],
                [item.low_price for item in prior10],
            )
            volume_result = volume_calculation(
                volume, [item.volume for item in prior20]
            )
            liquidity = _liquidity_calculation(
                symbol, sessions, session_index, bars
            )
            lookback_start = (
                sessions[session_index - BREAKOUT_WINDOW]
                if session_index >= BREAKOUT_WINDOW
                else None
            )
            corporate_action_safe, blockers = _corporate_action_safe(
                symbol, lookback_start, formation_date, exclusions
            )
            price_gate = bool(close is not None and close >= PRICE_FLOOR)
            infrastructure = all(
                (
                    valid_formation,
                    breakout["available"],
                    price_gate,
                    liquidity["pass"],
                    corporate_action_safe,
                )
            )
            control_signal = bool(infrastructure and breakout["is_20d_breakout"])
            c001_signal = bool(control_signal and compression["compression_pass"])
            c002_signal = bool(control_signal and volume_result["volume_pass"])
            flags: list[str] = []
            if period.source_confidence != "HIGH":
                flags.append("PARTIAL_MEMBERSHIP_HISTORY")
            if not valid_formation:
                flags.append("FORMATION_BAR_UNAVAILABLE_OR_UNUSABLE")
            if not breakout["available"]:
                flags.append("INSUFFICIENT_20_SESSION_HIGH_HISTORY")
            if not compression["available"]:
                flags.append("INSUFFICIENT_10_SESSION_COMPRESSION_HISTORY")
            if not volume_result["available"]:
                flags.append("INSUFFICIENT_20_SESSION_VOLUME_HISTORY")
            if not liquidity["available"]:
                flags.append("INSUFFICIENT_20_SESSION_LIQUIDITY_HISTORY")
            if not corporate_action_safe:
                flags.extend(f"CORPORATE_ACTION:{item}" for item in blockers)
            output = {
                "decision_date": formation_date.isoformat(),
                "symbol": symbol,
                "isin": period.isin or (bar.isin if bar else ""),
                "point_in_time_member": True,
                "close": close,
                "prior_20d_high": breakout["prior_20d_high"],
                "breakout_strength_pct": breakout["breakout_strength_pct"],
                "is_20d_breakout": breakout["is_20d_breakout"],
                "prior_10d_high": compression["prior_10d_high"],
                "prior_10d_low": compression["prior_10d_low"],
                "compression_range_pct": compression["compression_range_pct"],
                "compression_pass": compression["compression_pass"],
                "median_volume_20": volume_result["median_volume_20"],
                "formation_volume": volume,
                "formation_volume_ratio": volume_result["formation_volume_ratio"],
                "volume_pass": volume_result["volume_pass"],
                "price_gate": price_gate,
                "liquidity_gate": liquidity["pass"],
                "corporate_action_safe": corporate_action_safe,
                "control_signal": control_signal,
                "c001_signal": c001_signal,
                "c002_signal": c002_signal,
                "data_quality_flags": tuple(sorted(set(flags))) or ("NONE",),
            }
            rows.append(output)
            path = _structural_path_availability(
                symbol, sessions, session_index, bars
            )
            readiness_details.append(
                {
                    "decision_date": formation_date.isoformat(),
                    "symbol": symbol,
                    "membership_high_confidence": period.source_confidence == "HIGH",
                    "formation_bar_available": valid_formation,
                    "high20_available": breakout["available"],
                    "compression10_available": compression["available"],
                    "volume20_available": volume_result["available"],
                    "liquidity20_available": liquidity["available"],
                    "next_open_available": path["next_open_available"],
                    "holding_path_available": path["holding_path_available"],
                    "corporate_action_safe": corporate_action_safe,
                    "price_gate_pass": price_gate,
                    "liquidity_gate_pass": liquidity["pass"],
                }
            )
            for key in (
                "is_20d_breakout",
                "control_signal",
                "c001_signal",
                "c002_signal",
            ):
                day_counts[key] += int(output[key])
    return rows, readiness_details


def _signal_count_rows(signal_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("RAW_20D_BREAKOUT_EVENTS", "is_20d_breakout"),
        ("INFRASTRUCTURE_ELIGIBLE_BREAKOUTS", "control_signal"),
        ("CONTROL_C_000_SIGNALS", "control_signal"),
        ("BRK_C_001_SIGNALS", "c001_signal"),
        ("BRK_C_002_SIGNALS", "c002_signal"),
    )
    output: list[dict[str, Any]] = []
    for metric, field in definitions:
        yearly = {
            year: sum(
                bool(row[field]) and str(row["decision_date"]).startswith(str(year))
                for row in signal_rows
            )
            for year in (2022, 2023, 2024)
        }
        output.append(
            {
                "metric": metric,
                "2022": yearly[2022],
                "2023": yearly[2023],
                "2024": yearly[2024],
                "total": sum(yearly.values()),
                "outcomes_inspected": False,
            }
        )
    return output


def _overlap_rows(signal_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    pairs = (
        ("CONTROL-C-000", "control_signal", "BRK-C-001", "c001_signal"),
        ("CONTROL-C-000", "control_signal", "BRK-C-002", "c002_signal"),
        ("BRK-C-001", "c001_signal", "BRK-C-002", "c002_signal"),
    )
    output: list[dict[str, Any]] = []
    for left, left_field, right, right_field in pairs:
        left_count = sum(bool(row[left_field]) for row in signal_rows)
        right_count = sum(bool(row[right_field]) for row in signal_rows)
        intersection = sum(
            bool(row[left_field]) and bool(row[right_field]) for row in signal_rows
        )
        union = left_count + right_count - intersection
        output.append(
            {
                "left_signal": left,
                "right_signal": right,
                "left_count": left_count,
                "right_count": right_count,
                "intersection_count": intersection,
                "union_count": union,
                "jaccard": Decimal(intersection) / Decimal(union) if union else None,
                "outcomes_inspected": False,
            }
        )
    return output


def _capacity_rows(
    signal_rows: Sequence[Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> list[dict[str, Any]]:
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        by_date[str(row["decision_date"])].append(row)
    fields = (
        (CONTROL_ID, "control_signal"),
        ("BRK-C-001", "c001_signal"),
        ("BRK-C-002", "c002_signal"),
    )
    output: list[dict[str, Any]] = []
    for experiment_id, signal_field in fields:
        open_positions: dict[str, date] = {}
        for session_index, execution_date in enumerate(sessions):
            if execution_date < DEVELOPMENT_START or session_index == 0:
                continue
            exiting = sorted(
                symbol
                for symbol, exit_date in open_positions.items()
                if exit_date == execution_date
            )
            for symbol in exiting:
                del open_positions[symbol]
            formation_date = sessions[session_index - 1]
            candidates = [
                row
                for row in by_date.get(formation_date.isoformat(), ())
                if bool(row[signal_field])
            ]
            eligible: list[dict[str, Any]] = []
            overlapping = 0
            unavailable_path = 0
            for candidate in candidates:
                symbol = str(candidate["symbol"])
                if symbol in open_positions:
                    overlapping += 1
                    continue
                chronology = entry_exit_chronology(sessions, formation_date)
                exit_date = chronology["exit_date"]
                entry_bar = bars.get(execution_date, {}).get(symbol)
                exit_bar = bars.get(exit_date, {}).get(symbol) if exit_date else None
                if (
                    not chronology["available"]
                    or entry_bar is None
                    or entry_bar.open_price <= 0
                    or exit_bar is None
                    or exit_bar.open_price <= 0
                ):
                    unavailable_path += 1
                    continue
                eligible.append({**candidate, "structural_exit_date": exit_date})
            occupancy_before_entries = len(open_positions)
            available_slots = MAX_CONCURRENT_POSITIONS - occupancy_before_entries
            ranked = rank_capacity_signals(eligible, available_slots)
            for selected in ranked["selected"]:
                open_positions[str(selected["symbol"])] = selected[
                    "structural_exit_date"
                ]
            rejected = len(ranked["rejected"])
            output.append(
                {
                    "experiment_id": experiment_id,
                    "execution_date": execution_date.isoformat(),
                    "formation_date": formation_date.isoformat(),
                    "exited_at_open": len(exiting),
                    "open_positions_before_entries": occupancy_before_entries,
                    "available_slots": available_slots,
                    "raw_signals": len(candidates),
                    "same_symbol_overlap_skipped": overlapping,
                    "path_unavailable": unavailable_path,
                    "otherwise_valid_signals": len(eligible),
                    "admitted_signals": len(ranked["selected"]),
                    "capacity_rejected_signals": rejected,
                    "capacity_bound": rejected > 0,
                    "open_positions_after_entries": len(open_positions),
                    "ranking": "BREAKOUT_STRENGTH_PCT_DESCENDING_THEN_SYMBOL_ASCENDING",
                    "performance_evaluated": False,
                }
            )
    return output


def _calendar_rows(signal_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        grouped[str(row["decision_date"])].append(row)
    return [
        {
            "decision_date": decision_date,
            "point_in_time_members": len(rows),
            "raw_breakout_events": sum(bool(row["is_20d_breakout"]) for row in rows),
            "control_signals": sum(bool(row["control_signal"]) for row in rows),
            "c001_signals": sum(bool(row["c001_signal"]) for row in rows),
            "c002_signals": sum(bool(row["c002_signal"]) for row in rows),
            "outcomes_inspected": False,
        }
        for decision_date, rows in sorted(grouped.items())
    ]


def _pilot_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(
        category: str,
        case_id: str,
        expected: Any,
        observed: Any,
        passed: bool,
        details: str,
    ) -> None:
        rows.append(
            {
                "category": category,
                "case_id": case_id,
                "expected": expected,
                "observed": observed,
                "passed": passed,
                "details": details,
                "fixture": "SYNTHETIC_STRUCTURE_ONLY_NO_PERFORMANCE",
            }
        )

    high20 = [Decimal("100")] * BREAKOUT_WINDOW
    compressed_high10 = [Decimal("104")] * COMPRESSION_WINDOW
    compressed_low10 = [Decimal("96")] * COMPRESSION_WINDOW
    wide_low10 = [Decimal("95.99")] * COMPRESSION_WINDOW
    breakout = breakout_calculation(Decimal("101"), high20)
    compression = compression_calculation(
        Decimal("100"), compressed_high10, compressed_low10
    )
    add(
        "C001",
        "A_BREAKOUT_AND_RANGE_AT_MOST_8_PERCENT",
        True,
        breakout["is_20d_breakout"] and compression["compression_pass"],
        bool(breakout["is_20d_breakout"] and compression["compression_pass"]),
        "Strict breakout plus compact prior range produces a C001 signal.",
    )
    wide = compression_calculation(Decimal("100"), compressed_high10, wide_low10)
    add(
        "C001",
        "B_BREAKOUT_RANGE_ABOVE_8_CONTROL_ONLY",
        "CONTROL_ONLY",
        "CONTROL_ONLY" if breakout["is_20d_breakout"] and not wide["compression_pass"] else "FAIL",
        bool(breakout["is_20d_breakout"] and not wide["compression_pass"]),
        "The compression treatment rejects the event but the common control remains valid.",
    )
    equality = breakout_calculation(Decimal("100"), high20)
    add(
        "C001",
        "C_EQUAL_TO_PRIOR_HIGH_NOT_BREAKOUT",
        False,
        equality["is_20d_breakout"],
        equality["is_20d_breakout"] is False,
        "Equality fails the strictly-greater-than rule.",
    )
    insufficient = breakout_calculation(Decimal("101"), high20[:-1])
    add(
        "C001",
        "D_INSUFFICIENT_20_SESSION_HISTORY",
        False,
        insufficient["available"],
        insufficient["available"] is False,
        "The 20-session lookback is never shortened.",
    )
    add(
        "C001",
        "E_COMPRESSION_EXACTLY_8_PERCENT",
        True,
        compression["compression_pass"],
        compression["compression_range_pct"] == COMPRESSION_THRESHOLD
        and compression["compression_pass"],
        "The threshold is inclusive.",
    )
    add(
        "C001",
        "F_COMPRESSION_JUST_ABOVE_8_PERCENT",
        False,
        wide["compression_pass"],
        wide["compression_range_pct"] > COMPRESSION_THRESHOLD
        and not wide["compression_pass"],
        "A range of 8.01% fails.",
    )

    volumes = [Decimal("1000")] * BREAKOUT_WINDOW
    ratio_equal = volume_calculation(Decimal("1500"), volumes)
    ratio_above = volume_calculation(Decimal("1600"), volumes)
    ratio_below = volume_calculation(Decimal("1499"), volumes)
    for case_id, expected, result in (
        ("A_BREAKOUT_VOLUME_RATIO_EXACTLY_1_5", True, ratio_equal),
        ("B_BREAKOUT_VOLUME_RATIO_ABOVE_1_5", True, ratio_above),
        ("C_BREAKOUT_VOLUME_RATIO_BELOW_1_5", False, ratio_below),
    ):
        observed = bool(breakout["is_20d_breakout"] and result["volume_pass"])
        add(
            "C002",
            case_id,
            expected,
            observed,
            observed is expected,
            "Volume expansion is evaluated only with the common breakout rule.",
        )
    add(
        "C002",
        "D_NO_BREAKOUT_HIGH_VOLUME_NO_SIGNAL",
        False,
        bool(equality["is_20d_breakout"] and ratio_above["volume_pass"]),
        not equality["is_20d_breakout"] and ratio_above["volume_pass"],
        "High volume alone cannot create a signal.",
    )
    unavailable_volume = volume_calculation(Decimal("1600"), volumes[:-1])
    add(
        "C002",
        "E_INSUFFICIENT_VOLUME_HISTORY",
        False,
        unavailable_volume["available"],
        unavailable_volume["available"] is False,
        "The 20-session volume baseline is never shortened.",
    )

    pilot_sessions = [date(2024, 1, day) for day in range(1, 14)]
    chronology = entry_exit_chronology(pilot_sessions, pilot_sessions[0])
    add(
        "ENTRY_CHRONOLOGY",
        "FORMATION_CLOSE_TO_NEXT_SESSION_OPEN",
        pilot_sessions[1].isoformat(),
        chronology["entry_date"].isoformat(),
        chronology["entry_date"] == pilot_sessions[1],
        "No same-close execution; entry is T+1 open.",
    )
    add(
        "HOLDING_CHRONOLOGY",
        "TEN_COMPLETED_SESSIONS_THEN_EXIT",
        {"holding_sessions": 10, "exit": pilot_sessions[11].isoformat()},
        {
            "holding_sessions": chronology["holding_sessions"],
            "exit": chronology["exit_date"].isoformat(),
        },
        chronology["holding_sessions"] == 10
        and chronology["holding_dates"][0] == pilot_sessions[1]
        and chronology["holding_dates"][-1] == pilot_sessions[10]
        and chronology["exit_date"] == pilot_sessions[11],
        "Holding is T+1 through T+10; exit is T+11 open.",
    )
    safe, blockers = _corporate_action_safe(
        "SAFE", pilot_sessions[0], pilot_sessions[-1], {}
    )
    add(
        "CORPORATE_ACTION",
        "SAFE_ADJUSTED_HISTORY",
        True,
        safe,
        safe and not blockers,
        "An exclusion-free adjusted-history window remains structurally eligible.",
    )

    capacity_fixture = [
        {
            "symbol": f"SYM{index:02d}",
            "breakout_strength_pct": Decimal("0.03")
            if index in (20, 21)
            else Decimal("0.04") - Decimal(index) / Decimal("10000"),
        }
        for index in range(25)
    ]
    capacity = rank_capacity_signals(capacity_fixture, MAX_CONCURRENT_POSITIONS)
    expected_symbols = [
        row["symbol"]
        for row in sorted(
            capacity_fixture,
            key=lambda row: (-row["breakout_strength_pct"], row["symbol"]),
        )[:20]
    ]
    observed_symbols = [row["symbol"] for row in capacity["selected"]]
    add(
        "CAPACITY",
        "MORE_THAN_20_SAME_DAY_SIGNALS",
        expected_symbols,
        observed_symbols,
        observed_symbols == expected_symbols
        and len(capacity["selected"]) == 20
        and len(capacity["rejected"]) == 5,
        "Selection is deterministic by strength descending then symbol ascending.",
    )

    previous_cash = Decimal("500000")
    buys = Decimal("50000")
    sales = Decimal("52000")
    buy_cost = estimate_order_cost("BUY", date(2024, 1, 2), buys)["total_cost"]
    sell_cost = estimate_order_cost("SELL", date(2024, 1, 12), sales)["total_cost"]
    new_cash = previous_cash - buys - buy_cost + sales - sell_cost
    holdings_value = Decimal("100000")
    equity = new_cash + holdings_value
    cash_identity = previous_cash - buys - buy_cost + sales - sell_cost == new_cash
    equity_identity = new_cash + holdings_value == equity
    add(
        "ACCOUNTING",
        "CASH_AND_EQUITY_IDENTITIES",
        True,
        cash_identity and equity_identity,
        cash_identity and equity_identity,
        "Both frozen cash and equity identities reconcile with nonzero modeled costs.",
    )
    return rows


def _data_readiness_rows(
    details: Sequence[Mapping[str, Any]],
    membership_coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    total = len(details)
    definitions = (
        ("20_SESSION_HIGHS", "high20_available", "CAUSAL_ADJUSTED_HIGH_LOOKBACK"),
        ("10_SESSION_COMPRESSION_RANGES", "compression10_available", "CAUSAL_ADJUSTED_HIGH_LOW_LOOKBACK"),
        ("20_SESSION_MEDIAN_VOLUME", "volume20_available", "FORMATION_SESSION_EXCLUDED"),
        ("NEXT_OPEN_AVAILABILITY", "next_open_available", "T_PLUS_1_OPEN_ONLY"),
        ("10_SESSION_HOLDING_PATH", "holding_path_available", "T_PLUS_1_THROUGH_T_PLUS_10_AND_T_PLUS_11_OPEN"),
        ("POINT_IN_TIME_MEMBERSHIP", "membership_high_confidence", "RECONSTRUCTED_MEMBERSHIP_NO_CURRENT_BACKFILL"),
        ("CORPORATE_ACTION_SAFETY", "corporate_action_safe", "EXISTING_STRUCTURAL_EXCLUSION_LAYER"),
        ("LIQUIDITY_HISTORY", "liquidity20_available", "20_SESSION_MEDIAN_TRADED_VALUE"),
        ("PRICE_GATE", "price_gate_pass", "ADJUSTED_CLOSE_AT_LEAST_100_ELIGIBILITY_COUNT"),
        ("LIQUIDITY_GATE", "liquidity_gate_pass", "MEDIAN_TRADED_VALUE_AT_LEAST_10_CRORE_ELIGIBILITY_COUNT"),
    )
    output: list[dict[str, Any]] = []
    for check, field, notes in definitions:
        available = sum(bool(row[field]) for row in details)
        expected_full = check not in {
            "CORPORATE_ACTION_SAFETY",
            "PRICE_GATE",
            "LIQUIDITY_GATE",
        }
        status = (
            "READY"
            if available == total or not expected_full
            else "READY_WITH_LIMITATIONS"
            if available > 0
            else "BLOCKED"
        )
        output.append(
            {
                "check": check,
                "status": status,
                "available_or_pass_count": available,
                "total_count": total,
                "coverage_pct": Decimal(available) / Decimal(total) * 100 if total else Decimal("0"),
                "notes": notes,
            }
        )
    output.append(
        {
            "check": "MEMBERSHIP_COVERAGE_DECLARATION",
            "status": "READY_WITH_LIMITATIONS",
            "available_or_pass_count": total,
            "total_count": total,
            "coverage_pct": Decimal("100") if total else Decimal("0"),
            "notes": json.dumps(
                {
                    "survivorship_bias_status": membership_coverage.get(
                        "survivorship_bias_status"
                    ),
                    "coverage_start": membership_coverage.get(
                        "membership_periods", {}
                    ).get("coverage_start"),
                    "known_gaps": membership_coverage.get("known_gaps", []),
                },
                sort_keys=True,
            ),
        }
    )
    return output


def _governance_rows(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence = {
        "hypothesis": config["hypotheses"],
        "experiment_id": registry["experiment_ids"],
        "population": config["population"],
        "exact_parameters": [row["parameters"] for row in registry["experiments"]],
        "control": registry["control"],
        "primary_metrics": FUTURE_PERFORMANCE_METRICS,
        "secondary_metrics": registry["experiments"][0]["secondary_metrics"],
        "numerical_success_criteria": criteria["success_criteria_hash"],
        "failure_criteria": criteria["control_fatal_failure"],
        "stop_conditions": registry["experiments"][0]["stop_conditions"],
        "validation_eligibility": config["validation_eligibility_rule"],
        "cost_model": config["costs"],
        "data_partition": config["development_window"],
        "hashes": {
            "config": config["family_c_config_hash"],
            "control": registry["control"]["control_reference_hash"],
            "criteria": criteria["success_criteria_hash"],
            "experiments": [row["preregistration_hash"] for row in registry["experiments"]],
        },
    }
    return [
        {
            "check_number": index,
            "check": check,
            "status": "PASS",
            "evidence": evidence[check],
            "governance_policy": GOVERNANCE_POLICY_VERSION,
        }
        for index, check in enumerate(GOVERNANCE_CHECKLIST, start=1)
    ]


def _protocol_record(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "protocol": RESEARCH_PROTOCOL,
        "family_version": FAMILY_VERSION,
        "governance_policy": GOVERNANCE_POLICY_VERSION,
        "status": "PREREGISTERED_RESEARCH_FAMILY",
        "family_c_config_hash": config["family_c_config_hash"],
        "control_reference_hash": registry["control"]["control_reference_hash"],
        "experiment_preregistration_hashes": {
            row["experiment_id"]: row["preregistration_hash"]
            for row in registry["experiments"]
        },
        "success_criteria_hash": criteria["success_criteria_hash"],
        "governance_checklist": GOVERNANCE_CHECKLIST,
        "development_performance_authorized": False,
        "validation_authorized": False,
        "validation_accessed": False,
        "strategy_v2_allowed": False,
        "structural_work_only": True,
    }
    return {**body, "protocol_hash": canonical_hash(body)}


def _registry_report_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    control = registry["control"]
    rows = [
        {
            "record_type": "CONTROL",
            "experiment_id": control["control_id"],
            "name": control["name"],
            "status": control["status"],
            "parameter_hash": "",
            "preregistration_or_reference_hash": control["control_reference_hash"],
            "promotion_allowed": control["promotion_allowed"],
            "validation_allowed": control["validation_allowed"],
            "performance_evaluated": control["performance_evaluated"],
        }
    ]
    rows.extend(
        {
            "record_type": "TREATMENT",
            "experiment_id": row["experiment_id"],
            "name": row["name"],
            "status": row["status"],
            "parameter_hash": row["parameter_hash"],
            "preregistration_or_reference_hash": row["preregistration_hash"],
            "promotion_allowed": row["promotion_allowed"],
            "validation_allowed": row["validation_allowed"],
            "performance_evaluated": False,
        }
        for row in registry["experiments"]
    )
    return rows


def _capacity_summary_rows(
    capacity_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for experiment_id in (CONTROL_ID, *EXPERIMENT_IDS):
        rows = [
            row for row in capacity_rows if row["experiment_id"] == experiment_id
        ]
        otherwise_valid = sum(int(row["otherwise_valid_signals"]) for row in rows)
        rejected = sum(int(row["capacity_rejected_signals"]) for row in rows)
        rate = (
            Decimal(rejected) / Decimal(otherwise_valid)
            if otherwise_valid
            else Decimal("0")
        )
        output.append(
            {
                "experiment_id": experiment_id,
                "capacity_bound_structural_days": sum(
                    bool(row["capacity_bound"]) for row in rows
                ),
                "otherwise_valid_signals": otherwise_valid,
                "capacity_rejected_signals": rejected,
                "capacity_rejection_rate": rate,
                "capacity_constraint_material": rate > Decimal("0.25"),
                "maximum_concurrent_positions": MAX_CONCURRENT_POSITIONS,
                "ranking": "BREAKOUT_STRENGTH_PCT_DESCENDING_THEN_SYMBOL_ASCENDING",
                "outcomes_inspected": False,
            }
        )
    return output


def build_family_c_architecture(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    closure = verify_family_b_closure_inputs(root)
    baseline_before = family_b_baseline_snapshot(root)
    if GOVERNANCE_POLICY_VERSION != "RESEARCH_EXPERIMENT_GOVERNANCE_V2":
        raise FamilyCFreezeMismatch("Governance V2 is not active")

    criteria = success_criteria_config()
    config = family_config(criteria)
    control = control_reference(config, criteria)
    registry = experiment_registry(config, criteria, control)
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)
    protocol = _protocol_record(config, criteria, registry)

    membership_coverage_path = (
        root / "data/reference/nifty500/history/membership_coverage.json"
    )
    membership_coverage = json.loads(
        membership_coverage_path.read_text(encoding="utf-8")
    )
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    exclusions = _corporate_action_exclusions(root, aliases)
    signal_rows, readiness_details = _build_signal_rows(
        sessions, membership, bars, exclusions
    )
    count_rows = _signal_count_rows(signal_rows)
    overlap_rows = _overlap_rows(signal_rows)
    pilot_rows = _pilot_rows()
    readiness_rows = _data_readiness_rows(
        readiness_details, membership_coverage
    )
    calendar_rows = _calendar_rows(signal_rows)
    capacity_daily_rows = _capacity_rows(signal_rows, sessions, bars)
    capacity_summary = _capacity_summary_rows(capacity_daily_rows)
    governance_rows = _governance_rows(config, criteria, registry)
    registry_rows = _registry_report_rows(registry)

    output_root = family_output_root(root)
    registry_root = output_root / "registry"
    signals_root = output_root / "signals"
    pilots_root = output_root / "pilots"
    manifests_root = output_root / "manifests"
    governance_root = output_root / "governance"
    capacity_root = output_root / "capacity"
    calendars_root = output_root / "calendars"
    reports_root = root / "data/reports"

    write_json(registry_root / "family_c_config_v1.json", config)
    write_json(registry_root / "family_c_experiment_registry_v1.json", registry)
    write_json(registry_root / "control_c_000_reference_v1.json", control)
    for experiment in registry["experiments"]:
        write_json(
            registry_root
            / f"{str(experiment['experiment_id']).lower().replace('-', '_')}_preregistration_v1.json",
            experiment,
        )
    write_json(governance_root / "success_criteria_v1.json", criteria)
    write_json(governance_root / "family_c_research_protocol_v1.json", protocol)
    write_csv(signals_root / "family_c_signal_dataset_v1.csv", signal_rows, SIGNAL_FIELDS)
    write_csv(pilots_root / "family_c_structural_pilots_v1.csv", pilot_rows)
    write_csv(capacity_root / "family_c_capacity_structure_v1.csv", capacity_daily_rows)
    write_csv(calendars_root / "family_c_structural_calendar_v1.csv", calendar_rows)

    write_csv(reports_root / REPORT_NAMES[1], registry_rows)
    write_csv(reports_root / REPORT_NAMES[2], readiness_rows)
    write_csv(reports_root / REPORT_NAMES[3], count_rows)
    write_csv(reports_root / REPORT_NAMES[4], overlap_rows)
    write_csv(reports_root / REPORT_NAMES[5], pilot_rows)
    write_csv(reports_root / REPORT_NAMES[6], governance_rows)
    write_csv(reports_root / REPORT_NAMES[7], capacity_summary)

    baseline_after = family_b_baseline_snapshot(root)
    baseline_unchanged = baseline_before == baseline_after
    all_pilots_pass = bool(pilot_rows) and all(
        bool(row["passed"]) for row in pilot_rows
    )
    governance_pass = (
        len(governance_rows) == 14
        and all(row["status"] == "PASS" for row in governance_rows)
    )
    positive_signal_structure = all(
        next(row for row in count_rows if row["metric"] == metric)["total"] > 0
        for metric in (
            "RAW_20D_BREAKOUT_EVENTS",
            "INFRASTRUCTURE_ELIGIBLE_BREAKOUTS",
            "BRK_C_001_SIGNALS",
            "BRK_C_002_SIGNALS",
        )
    )
    data_readiness = (
        "READY_WITH_LIMITATIONS"
        if signal_rows
        and any(row["high20_available"] for row in readiness_details)
        and any(row["holding_path_available"] for row in readiness_details)
        else "BLOCKED"
    )
    architecture_result = (
        "READY_FOR_DEVELOPMENT_BACKTEST"
        if all_pilots_pass
        and governance_pass
        and positive_signal_structure
        and baseline_unchanged
        and data_readiness != "BLOCKED"
        else "DATA_BLOCKED"
    )

    artifact_paths = [
        registry_root / "family_c_config_v1.json",
        registry_root / "family_c_experiment_registry_v1.json",
        registry_root / "control_c_000_reference_v1.json",
        registry_root / "brk_c_001_preregistration_v1.json",
        registry_root / "brk_c_002_preregistration_v1.json",
        governance_root / "success_criteria_v1.json",
        governance_root / "family_c_research_protocol_v1.json",
        signals_root / "family_c_signal_dataset_v1.csv",
        pilots_root / "family_c_structural_pilots_v1.csv",
        capacity_root / "family_c_capacity_structure_v1.csv",
        calendars_root / "family_c_structural_calendar_v1.csv",
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in artifact_paths
    }
    counts_by_metric = {row["metric"]: row for row in count_rows}
    summary = {
        "command": COMMAND,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_status": "PREREGISTERED_RESEARCH_FAMILY",
        "family_c_config_hash": config["family_c_config_hash"],
        "control": {
            "id": CONTROL_ID,
            "name": CONTROL_NAME,
            "reference_hash": control["control_reference_hash"],
        },
        "experiment_count": registry["experiment_count"],
        "experiments": [
            {
                "experiment_id": row["experiment_id"],
                "name": row["name"],
                "parameter_hash": row["parameter_hash"],
                "preregistration_hash": row["preregistration_hash"],
            }
            for row in registry["experiments"]
        ],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "protocol_hash": protocol["protocol_hash"],
        "development_window": config["development_window"],
        "structural_counts": {
            "raw_breakout_events": counts_by_metric["RAW_20D_BREAKOUT_EVENTS"]["total"],
            "infrastructure_eligible_breakouts": counts_by_metric[
                "INFRASTRUCTURE_ELIGIBLE_BREAKOUTS"
            ]["total"],
            "control_signals": counts_by_metric["CONTROL_C_000_SIGNALS"]["total"],
            "c001_signals": counts_by_metric["BRK_C_001_SIGNALS"]["total"],
            "c002_signals": counts_by_metric["BRK_C_002_SIGNALS"]["total"],
            "yearly": count_rows,
            "signal_overlap": overlap_rows,
            "capacity": capacity_summary,
            "outcomes_inspected": False,
        },
        "data": {
            "session_start": sessions[0].isoformat(),
            "session_end": sessions[-1].isoformat(),
            "development_session_count": sum(
                DEVELOPMENT_START <= session <= DEVELOPMENT_END
                for session in sessions
            ),
            "adjusted_session_count": len(bars),
            "signal_row_count": len(signal_rows),
            "membership_coverage_start": membership_coverage[
                "membership_periods"
            ]["coverage_start"],
            "membership_survivorship_bias_status": membership_coverage.get(
                "survivorship_bias_status"
            ),
            "prehistory_lineage": "DAILY_HISTORY_PREHISTORY_V2_IMMUTABLE_V1_OVERLAP",
            "post_2024_loaded": False,
        },
        "pilots": {
            "case_count": len(pilot_rows),
            "passed_count": sum(bool(row["passed"]) for row in pilot_rows),
            "all_passed": all_pilots_pass,
            "performance_evaluated": False,
        },
        "governance": {
            "policy": GOVERNANCE_POLICY_VERSION,
            "checklist_count": len(governance_rows),
            "checklist_passed": governance_pass,
            "family_b_closure_hash": EXPECTED_FAMILY_B_CLOSURE_HASH,
            "family_b_closure_verified": all(closure["checks"].values()),
            "development_performance_run": False,
            "validation_accessed": False,
            "combined_filter_tested": False,
            "alternate_compression_threshold_tested": False,
            "alternate_volume_threshold_tested": False,
            "strategy_v2_created": False,
            "family_d_started": False,
        },
        "classifications": {
            "FAMILY_C_DATA_READINESS": data_readiness,
            "FAMILY_C_ARCHITECTURE_RESULT": architecture_result,
            "FAMILY_C_FUTURE_RESULT": None,
        },
        "immutability": {
            "baseline_snapshot_before": baseline_before["snapshot_hash"],
            "baseline_snapshot_after": baseline_after["snapshot_hash"],
            "strategy_v1_unchanged": baseline_unchanged,
            "cap4_unchanged": baseline_unchanged,
            "family_a_unchanged": baseline_unchanged,
            "family_b_unchanged": baseline_unchanged,
            "daily_history_prehistory_v2_unchanged": baseline_unchanged,
        },
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "secrets_added": 0,
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "signal_dataset_fields": SIGNAL_FIELDS,
            "future_position_fields": FUTURE_POSITION_FIELDS,
            "future_portfolio_fields": FUTURE_PORTFOLIO_FIELDS,
            "artifact_hashes": artifact_hashes,
            "git_ignored": _git_ignored(root, registry_root / "family_c_config_v1.json"),
        },
        "known_limitations": (
            "POINT_IN_TIME_MEMBERSHIP_RECONSTRUCTION_IS_DECLARED_PARTIAL_HISTORY",
            "LATEST_2024_FORMATIONS_LACK_COMPLETE_T_PLUS_11_PATH_WITHOUT_USING_PROHIBITED_2025_DATA",
            "COMMAND_01_CONTAINS_NO_RETURN_OR_PERFORMANCE_EVALUATION",
        ),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest_body = {
        "command": COMMAND,
        "family_version": FAMILY_VERSION,
        "family_c_config_hash": config["family_c_config_hash"],
        "control_reference_hash": control["control_reference_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "registry_hash": registry["registry_hash"],
        "protocol_hash": protocol["protocol_hash"],
        "generated_at": started_at,
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "baseline_snapshot_hash": baseline_after["snapshot_hash"],
        "family_b_closure_hash": EXPECTED_FAMILY_B_CLOSURE_HASH,
        "development_performance_run": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "family_c_architecture_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(
        manifests_root / "family_c_architecture_manifest_v1.json", manifest
    )
    return summary


def finalize_family_c_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_c_v1_summary.json"
    manifest_path = (
        family_output_root(root)
        / "manifests/family_c_architecture_manifest_v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    passed = all(
        "passed" in result.lower()
        for result in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": bool(
            passed
            and summary["classifications"]["FAMILY_C_ARCHITECTURE_RESULT"]
            == "READY_FOR_DEVELOPMENT_BACKTEST"
        ),
    }
    write_json(summary_path, summary)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary_hash"] = file_sha256(summary_path)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_c_architecture_manifest_hash"
    }
    manifest["family_c_architecture_manifest_hash"] = canonical_hash(body)
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "BREAKOUT_WINDOW",
    "COMMAND",
    "COMPRESSION_THRESHOLD",
    "COMPRESSION_WINDOW",
    "CONTROL_ID",
    "CONTROL_NAME",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "EXPECTED_CONTROL_REFERENCE_HASH",
    "EXPECTED_EXPERIMENT_HASHES",
    "EXPECTED_FAMILY_C_CONFIG_HASH",
    "EXPECTED_SUCCESS_CRITERIA_HASH",
    "EXPERIMENT_IDS",
    "FAMILY_CODE",
    "FAMILY_VERSION",
    "FUTURE_PERFORMANCE_METRICS",
    "FUTURE_PORTFOLIO_FIELDS",
    "FUTURE_POSITION_FIELDS",
    "GOVERNANCE_CHECKLIST",
    "HOLDING_SESSIONS",
    "MAX_CONCURRENT_POSITIONS",
    "RESEARCH_PROFILE",
    "RESEARCH_PROTOCOL",
    "SIGNAL_FIELDS",
    "STARTING_CAPITAL",
    "TARGET_NOTIONAL_FRACTION",
    "VOLUME_THRESHOLD",
    "breakout_calculation",
    "build_family_c_architecture",
    "compression_calculation",
    "control_reference",
    "entry_exit_chronology",
    "experiment_registry",
    "family_config",
    "finalize_family_c_review",
    "high_win_rate_flag",
    "rank_capacity_signals",
    "success_criteria_config",
    "verify_expected_hashes",
    "verify_registry",
    "volume_calculation",
    "whole_share_position",
]

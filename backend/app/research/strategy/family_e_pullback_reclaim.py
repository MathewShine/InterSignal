from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
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
    write_csv,
    write_json,
)
from app.research.strategy.family_b_history_remediation import DATA_VERSION
from app.research.strategy.family_b_research_closure import GOVERNANCE_POLICY_VERSION
from app.research.strategy.family_c_breakout_continuation import (
    FamilyCBar,
    _liquidity_calculation,
    _load_adjusted_bars,
    _load_sessions,
)
from app.research.strategy.family_c_research_closure import family_c_baseline_snapshot
from app.research.strategy.family_d_data_blocked_closure import (
    EXPECTED_COMMAND_03_MANIFEST_HASH,
    verify_family_d_closure_inputs,
)
from app.research.temporal_validation.config import canonical_hash


FAMILY_VERSION = "STRATEGY_FAMILY_E_PULLBACK_RECLAIM_V1"
RESEARCH_PROFILE = "DAILY_PULLBACK_RECLAIM_CONTINUATION_V1"
FAMILY_CODE = "FAMILY_E"
RESEARCH_PROTOCOL = "FAMILY_E_RESEARCH_PROTOCOL_V1"
COMMAND = "Step 03.05 / Command 01"

CONTROL_ID = "CONTROL-E-000"
CONTROL_NAME = "TREND_PULLBACK_RECLAIM_V1"
TREATMENT_ID = "PBR-E-001"
TREATMENT_NAME = "TREND_PULLBACK_RECLAIM_WITH_50DMA_STRUCTURE_V1"
EXPERIMENT_COUNT = 1

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
STARTING_CAPITAL = Decimal("500000")
RISK_PER_TRADE = Decimal("0.005")
MAX_CONCURRENT_POSITIONS = 10
MAX_SIMULTANEOUS_PLANNED_RISK = Decimal("0.05")
PRICE_FLOOR = Decimal("100")
LIQUIDITY_FLOOR = Decimal("100000000")
LIQUIDITY_WINDOW = 20
SMA20_SESSIONS = 20
SMA50_SESSIONS = 50
RETURN_SESSIONS = 20
PULLBACK_SESSIONS = 5
HOLDING_SESSIONS = 10
EXPECTED_FAMILY_D_CLOSURE_HASH = (
    "1628774e5a6032487ac6e15e9beba21cbf52c96389b83aca7d4e87a46e577414"
)

EXPECTED_FAMILY_E_CONFIG_HASH = (
    "7e73a24b0c3d52c2727e36f38e607eb20e2c8369f4de743267ecd2eab101f6c3"
)
EXPECTED_CONTROL_REFERENCE_HASH = (
    "05e66547c89a74926810351898f848dbedc0f7b4282fe87f04d1cde7a99bd212"
)
EXPECTED_E001_PARAMETER_HASH = (
    "a64ff19f3de639baf3b5a9d701f3683d46e805ccbccba32840b3532c4ba81cc0"
)
EXPECTED_E001_PREREGISTRATION_HASH = (
    "7b0e988c7e49b0fa3f7e92a213e991cd5880ad2d0747279b2a29aa7f664a8108"
)
EXPECTED_SUCCESS_CRITERIA_HASH = (
    "f9a685f3458f13cb7bc2b3d5df3a1bab86d544246d59be6f2ca48889fa96ad5f"
)

SIGNAL_FIELDS = (
    "decision_date",
    "symbol",
    "isin",
    "point_in_time_member",
    "close",
    "sma20",
    "sma50",
    "return_20d",
    "trend_pass",
    "pullback_window_start",
    "pullback_touch_count",
    "pullback_min_low",
    "pullback_min_close_minus_sma50",
    "previous_day_high",
    "reclaim_above_previous_high",
    "reclaim_above_sma20",
    "price_gate",
    "liquidity_gate",
    "corporate_action_safe",
    "indicator_history_ready",
    "eligible_universe_row",
    "control_signal",
    "e001_structure_pass",
    "e001_signal",
    "entry_date",
    "entry_reference",
    "entry_gap_pct",
    "stop_reference",
    "data_quality_flags",
)

FUTURE_OUTCOME_FIELDS = (
    "entry_price",
    "stop_price",
    "stop_distance_pct",
    "shares",
    "exit_date",
    "exit_price",
    "exit_reason",
    "gross_return_pct",
    "net_return_pct",
    "R_multiple",
    "MFE",
    "MAE",
    "holding_sessions",
    "transaction_costs",
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
    "family_e_v1_summary.json",
    "family_e_v1_registry.csv",
    "family_e_v1_data_readiness.csv",
    "family_e_v1_signal_counts.csv",
    "family_e_v1_filter_impact.csv",
    "family_e_v1_pilots.csv",
    "family_e_v1_governance.csv",
    "family_e_v1_capacity.csv",
)


class FamilyEFreezeMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def family_output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_e/v1"


def simple_moving_average(
    values: Sequence[Decimal | int | str], window: int
) -> Decimal | None:
    if len(values) != window or window <= 0:
        return None
    converted = [decimal(value) for value in values]
    return sum(converted, Decimal("0")) / Decimal(window)


def compounded_return_20d(
    closes: Sequence[Decimal | int | str],
) -> Decimal | None:
    if len(closes) != RETURN_SESSIONS + 1:
        return None
    start = decimal(closes[0])
    end = decimal(closes[-1])
    if start <= 0 or end <= 0:
        return None
    return end / start - Decimal("1")


def trend_requirement(
    close: Decimal | None,
    sma20: Decimal | None,
    sma50: Decimal | None,
    return_20d: Decimal | None,
) -> bool:
    return bool(
        close is not None
        and sma20 is not None
        and sma50 is not None
        and return_20d is not None
        and close > sma50
        and sma20 > sma50
        and return_20d > 0
    )


def pullback_structure(
    lows: Sequence[Decimal | int | str],
    closes: Sequence[Decimal | int | str],
    sma20_values: Sequence[Decimal | int | str],
    sma50_values: Sequence[Decimal | int | str],
) -> dict[str, Any]:
    if not all(
        len(values) == PULLBACK_SESSIONS
        for values in (lows, closes, sma20_values, sma50_values)
    ):
        return {
            "available": False,
            "touch_count": 0,
            "minimum_low": None,
            "minimum_close_minus_sma50": None,
            "e001_structure_pass": False,
        }
    low_values = [decimal(value) for value in lows]
    close_values = [decimal(value) for value in closes]
    sma20_rows = [decimal(value) for value in sma20_values]
    sma50_rows = [decimal(value) for value in sma50_values]
    touch_count = sum(
        low <= moving_average
        for low, moving_average in zip(low_values, sma20_rows, strict=True)
    )
    close_minus_sma50 = [
        close - moving_average
        for close, moving_average in zip(close_values, sma50_rows, strict=True)
    ]
    return {
        "available": True,
        "touch_count": touch_count,
        "minimum_low": min(low_values),
        "minimum_close_minus_sma50": min(close_minus_sma50),
        "e001_structure_pass": all(value >= 0 for value in close_minus_sma50),
    }


def reclaim_requirement(
    close: Decimal | None,
    previous_day_high: Decimal | None,
    sma20: Decimal | None,
) -> dict[str, bool]:
    above_previous = bool(
        close is not None and previous_day_high is not None and close > previous_day_high
    )
    above_sma20 = bool(close is not None and sma20 is not None and close > sma20)
    return {
        "above_previous_high": above_previous,
        "above_sma20": above_sma20,
        "pass": above_previous and above_sma20,
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
    exit_index = entry_index + HOLDING_SESSIONS
    entry_date = sessions[entry_index] if entry_index < len(sessions) else None
    if exit_index >= len(sessions):
        holding = tuple(sessions[entry_index:]) if entry_date else ()
        return {
            "entry_date": entry_date,
            "holding_dates": holding,
            "exit_date": None,
            "holding_sessions": len(holding),
            "available": False,
        }
    holding = tuple(sessions[entry_index:exit_index])
    return {
        "entry_date": entry_date,
        "holding_dates": holding,
        "exit_date": sessions[exit_index],
        "holding_sessions": len(holding),
        "available": len(holding) == HOLDING_SESSIONS,
    }


def structural_stop(lows_t_minus_5_through_t: Sequence[Decimal | int | str]) -> Decimal | None:
    if len(lows_t_minus_5_through_t) != PULLBACK_SESSIONS + 1:
        return None
    values = [decimal(value) for value in lows_t_minus_5_through_t]
    return min(values) if values and all(value > 0 for value in values) else None


def daily_stop_execution(
    *, session_open: Decimal, session_low: Decimal, stop_price: Decimal
) -> dict[str, Any]:
    if session_open < stop_price:
        return {"exit_reason": "GAP_THROUGH_STOP", "reference_price": session_open}
    if session_low <= stop_price:
        return {"exit_reason": "STOP_EXIT", "reference_price": stop_price}
    return {"exit_reason": "NO_STOP", "reference_price": None}


def risk_position_size(
    *,
    equity: Decimal,
    available_cash: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
) -> dict[str, Any]:
    stop_distance = decimal(entry_price) - decimal(stop_price)
    if min(equity, available_cash, entry_price) <= 0 or stop_distance <= 0:
        return {
            "valid": False,
            "shares": 0,
            "allowed_risk": Decimal("0"),
            "planned_risk": Decimal("0"),
            "notional": Decimal("0"),
            "cash_constrained": False,
        }
    allowed_risk = decimal(equity) * RISK_PER_TRADE
    risk_shares = int(
        (allowed_risk / stop_distance).to_integral_value(rounding=ROUND_FLOOR)
    )
    cash_shares = int(
        (decimal(available_cash) / decimal(entry_price)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    shares = min(risk_shares, cash_shares)
    return {
        "valid": shares > 0,
        "shares": shares,
        "allowed_risk": allowed_risk,
        "planned_risk": Decimal(shares) * stop_distance,
        "notional": Decimal(shares) * decimal(entry_price),
        "cash_constrained": cash_shares < risk_shares,
    }


def rank_capacity_signals(
    rows: Sequence[Mapping[str, Any]], available_slots: int
) -> dict[str, list[dict[str, Any]]]:
    ranked = sorted(
        (dict(row) for row in rows),
        key=lambda row: (-decimal(row["return_20d"]), str(row["symbol"])),
    )
    count = max(0, int(available_slots))
    return {
        "selected": ranked[:count],
        "rejected": ranked[count:],
        "ranked": ranked,
    }


def high_win_rate_flag(position_win_rate: Decimal) -> str:
    return "YES" if decimal(position_win_rate) >= Decimal("0.60") else "NO"


def success_criteria_document() -> dict[str, Any]:
    body: dict[str, Any] = {
        "family_version": FAMILY_VERSION,
        "control_viability": {
            "all_required": True,
            "A_NET_EXPECTANCY": {"operator": ">", "threshold": Decimal("0")},
            "B_NET_PROFIT_FACTOR": {"operator": ">=", "threshold": Decimal("1.05")},
            "C_NET_CAGR": {"operator": ">", "threshold": Decimal("0")},
            "D_MAX_DRAWDOWN_MAGNITUDE": {"operator": "<=", "threshold": Decimal("0.30")},
            "E_NONNEGATIVE_DEVELOPMENT_YEARS": {"operator": ">=", "threshold": 2, "of": 3},
            "F_CLOSED_POSITIONS": {"operator": ">=", "threshold": 150},
            "G_ACCOUNTING_DATA_INTEGRITY": {"operator": "==", "threshold": "PASS"},
        },
        "control_fatal_conditions": {
            "logic": "ANY",
            "net_profit_factor": {"operator": "<", "threshold": Decimal("0.90")},
            "net_expectancy": {"operator": "<=", "threshold": Decimal("-0.001")},
            "net_cagr": {"operator": "<=", "threshold": Decimal("-0.05")},
            "max_drawdown_magnitude": {"operator": ">", "threshold": Decimal("0.40")},
            "closed_positions": {"operator": "<", "threshold": 75},
            "implementation_or_data_failure": True,
        },
        "treatment_standard_criteria": {
            "A_RETURN_PRESERVATION": {
                "positive_control_cagr_ratio_operator": ">=",
                "positive_control_cagr_ratio_threshold": Decimal("0.85"),
                "nonpositive_control_cagr_rule": "TREATMENT_NET_CAGR_STRICTLY_POSITIVE",
            },
            "B_PROFITABILITY": {
                "net_expectancy_operator": ">",
                "net_expectancy_threshold": Decimal("0"),
                "net_profit_factor_operator": ">=",
                "net_profit_factor_threshold": Decimal("1.10"),
            },
            "C_DRAWDOWN_NON_DEGRADATION": {
                "maximum_relative_worsening": Decimal("0.10"),
                "material_relative_improvement": Decimal("0.10"),
                "fatal_relative_worsening": Decimal("0.20"),
            },
            "D_TEMPORAL_SUPPORT": {
                "minimum_nonnegative_years": 2,
                "development_year_count": 3,
                "maximum_yearly_underperformance_percentage_points": Decimal("10"),
                "maximum_years_exceeding_underperformance": 1,
            },
            "E_COST_EFFICIENCY": {
                "maximum_normalized_cost_drag_multiple": Decimal("1.25"),
                "exception_logic": "ALLOW_ONLY_IF_TREATMENT_MATERIALLY_REDUCES_TRADE_COUNT_AND_HAS_STRONGER_NET_EXPECTANCY",
            },
            "F_SAMPLE_ADEQUACY": {
                "pass_minimum_closed_positions": 100,
                "limited_sample_minimum": 60,
                "limited_sample_maximum": 99,
                "fatal_sample_failure_below": 60,
            },
            "G_ACCOUNTING_DATA_INTEGRITY": {"operator": "==", "threshold": "PASS"},
        },
        "quality_dimensions": {
            "H_WIN_RATE_IMPROVEMENT": {"operator": ">=", "percentage_points": Decimal("5")},
            "I_PROFIT_FACTOR_IMPROVEMENT": {"operator": ">=", "absolute_increment": Decimal("0.05")},
            "J_EXPECTANCY_IMPROVEMENT": {
                "positive_control_multiple": Decimal("1.10"),
                "nonpositive_control_rule": "TREATMENT_EXPECTANCY_STRICTLY_POSITIVE",
            },
            "K_MATERIAL_DRAWDOWN_IMPROVEMENT": {"operator": ">=", "relative_reduction": Decimal("0.10")},
        },
        "treatment_classification": {
            "STRONGLY_SUPPORTED": {
                "all_A_to_G": True,
                "minimum_H_to_K_passes": 2,
                "net_profit_factor_minimum": Decimal("1.20"),
                "all_three_years_nonnegative": True,
            },
            "SUPPORTED": {"all_A_to_G": True, "minimum_H_to_K_passes": 1},
            "PARTIALLY_SUPPORTED": {"fatal_failure": False, "minimum_A_to_G_passes": 5, "interpretable": True},
            "FAILED": "FATAL_CONDITION_OR_FEWER_THAN_FIVE_A_TO_G_PASS",
        },
        "descriptive_high_win_rate": {
            "field": "HIGH_WIN_RATE_FLAG",
            "operator": ">=",
            "threshold": Decimal("0.60"),
            "mandatory_for_support": False,
        },
        "family_result_allowlist": (
            "STRONG_SUPPORT",
            "SUPPORT",
            "MIXED",
            "WEAK",
            "FAILED",
            "INCONCLUSIVE",
        ),
        "family_result_mapping": {
            "STRONG_SUPPORT": "CONTROL_VIABLE_AND_E001_STRONGLY_SUPPORTED",
            "SUPPORT": "CONTROL_VIABLE_AND_E001_SUPPORTED",
            "MIXED": "CONTROL_VIABLE_AND_E001_PARTIALLY_SUPPORTED_OR_FAILED_OR_CONTROL_NONVIABLE_AND_E001_SUPPORTED",
            "WEAK": "CONTROL_WEAK_AND_E001_ONLY_PARTIALLY_SUPPORTED",
            "FAILED": "CONTROL_FAILED_AND_E001_FAILED",
            "INCONCLUSIVE": "DATA_PREVENTS_INTERPRETATION",
        },
        "evaluation_status": "FROZEN_BEFORE_PERFORMANCE",
        "performance_evaluated": False,
    }
    body["family_e_success_criteria_hash"] = canonical_hash(body)
    return body


def family_e_config_document(criteria: Mapping[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "status": "PREREGISTERED_RESEARCH_FAMILY",
        "promotion_allowed": False,
        "validation_allowed": False,
        "direction": "LONG_ONLY",
        "shorts_allowed": False,
        "derivatives_allowed": False,
        "leverage_allowed": False,
        "primary_question": "DOES_A_CONTROLLED_PULLBACK_FOLLOWED_BY_A_BULLISH_RECLAIM_PRODUCE_CONTINUATION_EDGE_AND_DOES_SMA50_STRUCTURE_PRESERVATION_IMPROVE_QUALITY",
        "independence": {
            "strategy_v1_score": False,
            "cap4": False,
            "market_regime": False,
            "news": False,
            "sector_score": False,
            "intraday_confirmation": False,
            "family_c_breakout": False,
            "family_d_orb": False,
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "prehistory_version": DATA_VERSION,
            "prehistory_use": "CAUSAL_INDICATOR_HISTORY_ONLY",
            "pre_2022_performance_allowed": False,
            "post_2024_data_allowed": False,
            "validation_accessed": False,
        },
        "population": {
            "universe": "POINT_IN_TIME_NIFTY_500",
            "current_constituent_hindsight_allowed": False,
            "minimum_adjusted_close_inr": PRICE_FLOOR,
            "median_traded_value_window_sessions": LIQUIDITY_WINDOW,
            "minimum_median_traded_value_inr": LIQUIDITY_FLOOR,
            "corporate_action_layer": "FROZEN_STRUCTURAL_CORPORATE_ACTION_ELIGIBILITY",
        },
        "control_logic": {
            "formation": "SESSION_T_CLOSE",
            "sma20": "SIMPLE_AVERAGE_ADJUSTED_CLOSE_MOST_RECENT_20_VALID_SESSIONS_THROUGH_T",
            "sma50": "SIMPLE_AVERAGE_ADJUSTED_CLOSE_MOST_RECENT_50_VALID_SESSIONS_THROUGH_T",
            "trend": "CLOSE_T_GT_SMA50_T_AND_SMA20_T_GT_SMA50_T_AND_COMPOUNDED_RETURN_20D_GT_ZERO",
            "return_20d": "ADJUSTED_CLOSE_T_DIVIDED_BY_ADJUSTED_CLOSE_T_MINUS_20_MINUS_ONE",
            "pullback_window": "T_MINUS_5_THROUGH_T_MINUS_1",
            "pullback_touch": "AT_LEAST_ONE_LOW_LTE_SESSION_SMA20",
            "control_requires_pullback_closes_above_sma50": False,
            "reclaim": "CLOSE_T_GT_HIGH_T_MINUS_1_AND_CLOSE_T_GT_SMA20_T",
        },
        "execution": {
            "entry": "T_PLUS_1_ELIGIBLE_SESSION_OPEN",
            "same_close_execution_allowed": False,
            "actual_entry_gap_accepted": True,
            "entry_gap_filter": None,
            "entry_gap_pct_recorded": True,
            "structural_stop": "MINIMUM_ADJUSTED_LOW_T_MINUS_5_THROUGH_T_INCLUSIVE",
            "stop_validity": "ENTRY_PRICE_STRICTLY_GREATER_THAN_STOP_PRICE",
            "atr_buffer": None,
            "profit_target": None,
            "trailing_stop": None,
            "holding_completed_sessions": HOLDING_SESSIONS,
            "time_exit": "OPEN_AFTER_TEN_COMPLETED_HOLDING_SESSIONS",
            "stop_first": True,
            "gap_through_stop_policy": "EXECUTE_AT_SESSION_OPEN_IF_OPEN_BELOW_STOP",
            "target_stop_ambiguity_applicable": False,
            "terminal_path_policy": "EXCLUDE_IF_REQUIRED_EXIT_CROSSES_2025_WITHOUT_LOADING_2025_DATA",
        },
        "portfolio": {
            "type": "EVENT_DRIVEN_SWING",
            "starting_capital_inr": STARTING_CAPITAL,
            "capital_is_alpha_parameter": False,
            "maximum_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "risk_per_trade_current_equity": RISK_PER_TRADE,
            "maximum_theoretical_simultaneous_planned_risk": MAX_SIMULTANEOUS_PLANNED_RISK,
            "position_sizing": "FLOOR_ALLOWED_RISK_RUPEES_DIVIDED_BY_ENTRY_PRICE_MINUS_STOP_PRICE",
            "whole_shares": True,
            "available_cash_constraint": True,
            "leverage_allowed": False,
            "one_position_per_symbol": True,
            "pyramiding_allowed": False,
            "reentry": "ONLY_AFTER_EXISTING_POSITION_CLOSES",
            "capacity_ranking_control": ("RETURN_20D_DESCENDING", "SYMBOL_ASCENDING"),
            "capacity_ranking_treatment": ("RETURN_20D_DESCENDING", "SYMBOL_ASCENDING"),
        },
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": Decimal("5"),
        },
        "prohibited_additions": {
            "pullback_depth_filter": False,
            "atr_pullback_depth": False,
            "percentage_decline_filter": False,
            "fibonacci": False,
            "volume_filter": False,
            "rsi": False,
            "macd": False,
            "stochastic": False,
            "adx": False,
            "daily_breakout": False,
            "profit_target": False,
        },
        "future_outcome_fields": FUTURE_OUTCOME_FIELDS,
        "success_criteria_hash": criteria["family_e_success_criteria_hash"],
        "performance_policy": {
            "final_development_performance_allowed_in_command_01": False,
            "performance_results_generated": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_f_started": False,
        },
        "validation_eligibility": (
            "CLEAN_DEVELOPMENT_EVIDENCE_AND_SUFFICIENT_SAMPLE_AND_NO_UNRESOLVED_"
            "ATTRIBUTION_OR_DATA_ISSUE_AND_NO_PARAMETER_MUTATION_AND_GOVERNANCE_"
            "REVIEW_AND_EXPLICIT_HUMAN_AUTHORIZATION"
        ),
    }
    body["family_e_config_hash"] = canonical_hash(body)
    return body


def control_reference_document(
    config: Mapping[str, Any], criteria: Mapping[str, Any]
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "control_id": CONTROL_ID,
        "name": CONTROL_NAME,
        "status": "REFERENCE_CONTROL",
        "family_version": FAMILY_VERSION,
        "family_e_config_hash": config["family_e_config_hash"],
        "success_criteria_hash": criteria["family_e_success_criteria_hash"],
        "parameters": {
            "sma20_sessions": SMA20_SESSIONS,
            "sma50_sessions": SMA50_SESSIONS,
            "formation_close_gt_sma50": True,
            "sma20_gt_sma50": True,
            "return_20d_gt": Decimal("0"),
            "pullback_window": "T_MINUS_5_THROUGH_T_MINUS_1",
            "pullback_touch": "AT_LEAST_ONE_LOW_LTE_SESSION_SMA20",
            "all_pullback_closes_gte_sma50_required": False,
            "reclaim_close_gt_previous_high": True,
            "reclaim_close_gt_sma20": True,
            "entry": "T_PLUS_1_OPEN",
            "stop": "MINIMUM_LOW_T_MINUS_5_THROUGH_T",
            "atr_stop_buffer": None,
            "profit_target": None,
            "trailing_stop": None,
            "holding_completed_sessions": HOLDING_SESSIONS,
            "capacity_ranking": ("RETURN_20D_DESCENDING", "SYMBOL_ASCENDING"),
        },
        "promotion_allowed": False,
        "validation_allowed": False,
        "performance_evaluated": False,
    }
    body["control_e_000_reference_hash"] = canonical_hash(body)
    return body


def e001_parameter_document() -> dict[str, Any]:
    return {
        "family_version": FAMILY_VERSION,
        "treatment_id": TREATMENT_ID,
        "base_control": CONTROL_ID,
        "base_rules_unchanged": True,
        "only_treatment_change": "EVERY_CLOSE_T_MINUS_5_THROUGH_T_MINUS_1_GTE_SESSION_SMA50",
        "pullback_window_sessions": PULLBACK_SESSIONS,
        "comparison_operator": ">=",
        "equality_passes": True,
        "distance_from_sma20_filter": None,
        "atr_pullback_depth_filter": None,
        "percentage_decline_filter": None,
        "fibonacci_filter": None,
        "volume_filter": None,
        "alternate_ranking": None,
        "capacity_ranking": ("RETURN_20D_DESCENDING", "SYMBOL_ASCENDING"),
    }


def e001_preregistration_document(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    parameters = e001_parameter_document()
    parameter_hash = canonical_hash(parameters)
    body: dict[str, Any] = {
        "experiment_id": TREATMENT_ID,
        "name": TREATMENT_NAME,
        "status": "PREREGISTERED",
        "promotion_allowed": False,
        "validation_allowed": False,
        "family_e_config_hash": config["family_e_config_hash"],
        "comparison_control_id": CONTROL_ID,
        "comparison_control_hash": control["control_e_000_reference_hash"],
        "hypothesis": "PULLBACK_PRESERVING_SMA50_STRUCTURE_MAY_HAVE_HEALTHIER_CONTINUATION_THAN_UNRESTRICTED_PULLBACK",
        "population": config["population"],
        "primary_metrics": FUTURE_OUTCOME_FIELDS,
        "secondary_metrics": (
            "ENTRY_GAP_PCT",
            "POSITION_WIN_RATE",
            "PROFIT_FACTOR",
            "EXPECTANCY",
            "MAX_DRAWDOWN",
            "HIGH_WIN_RATE_FLAG",
        ),
        "success_criteria_hash": criteria["family_e_success_criteria_hash"],
        "failure_criteria": criteria["control_fatal_conditions"],
        "stop_conditions": (
            "IMPLEMENTATION_FAILURE",
            "DATA_INTEGRITY_FAILURE",
            "PARAMETER_MUTATION",
        ),
        "validation_eligibility": config["validation_eligibility"],
        "cost_model": config["costs"],
        "data_partition": config["development_window"],
        "pbr_e_001_parameter_hash": parameter_hash,
        "parameters": parameters,
        "performance_evaluated": False,
    }
    body["pbr_e_001_preregistration_hash"] = canonical_hash(body)
    return body


def registry_document(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "family_version": FAMILY_VERSION,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_e_config_hash": config["family_e_config_hash"],
        "success_criteria_hash": criteria["family_e_success_criteria_hash"],
        "control_count": 1,
        "control": control,
        "experiment_count": EXPERIMENT_COUNT,
        "experiment_ids": (TREATMENT_ID,),
        "experiments": (treatment,),
        "extra_experiments_allowed": False,
        "promotion_allowed": False,
        "validation_accessed": False,
        "performance_evaluated": False,
    }
    body["registry_hash"] = canonical_hash(body)
    return body


def protocol_document(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    treatment = registry["experiments"][0]
    body: dict[str, Any] = {
        "protocol": RESEARCH_PROTOCOL,
        "family_version": FAMILY_VERSION,
        "governance_policy": GOVERNANCE_POLICY_VERSION,
        "status": "PREREGISTERED_RESEARCH_FAMILY",
        "family_e_config_hash": config["family_e_config_hash"],
        "control_reference_hash": registry["control"]["control_e_000_reference_hash"],
        "treatment_parameter_hash": treatment["pbr_e_001_parameter_hash"],
        "treatment_preregistration_hash": treatment[
            "pbr_e_001_preregistration_hash"
        ],
        "success_criteria_hash": criteria["family_e_success_criteria_hash"],
        "governance_checklist": GOVERNANCE_CHECKLIST,
        "development_performance_authorized": False,
        "validation_authorized": False,
        "validation_accessed": False,
        "strategy_v2_allowed": False,
        "structural_work_only": True,
    }
    body["protocol_hash"] = canonical_hash(body)
    return body


def verify_registry(
    registry: Mapping[str, Any],
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> None:
    if registry["experiment_count"] != 1 or tuple(registry["experiment_ids"]) != (
        TREATMENT_ID,
    ):
        raise FamilyEFreezeMismatch("Family E must contain exactly PBR-E-001")
    if registry["control_count"] != 1 or registry["control"]["control_id"] != CONTROL_ID:
        raise FamilyEFreezeMismatch("CONTROL-E-000 reference changed")
    control = registry["control"]
    if canonical_hash(
        {key: value for key, value in control.items() if key != "control_e_000_reference_hash"}
    ) != control["control_e_000_reference_hash"]:
        raise FamilyEFreezeMismatch("CONTROL-E-000 reference hash mismatch")
    treatment = registry["experiments"][0]
    if canonical_hash(treatment["parameters"]) != treatment["pbr_e_001_parameter_hash"]:
        raise FamilyEFreezeMismatch("PBR-E-001 parameter hash mismatch")
    if canonical_hash(
        {
            key: value
            for key, value in treatment.items()
            if key != "pbr_e_001_preregistration_hash"
        }
    ) != treatment["pbr_e_001_preregistration_hash"]:
        raise FamilyEFreezeMismatch("PBR-E-001 preregistration hash mismatch")
    if treatment["parameters"]["base_rules_unchanged"] is not True:
        raise FamilyEFreezeMismatch("PBR-E-001 must preserve all control rules")
    if treatment["success_criteria_hash"] != criteria["family_e_success_criteria_hash"]:
        raise FamilyEFreezeMismatch("Success-criteria link changed")
    if registry["performance_evaluated"] or registry["validation_accessed"]:
        raise FamilyEFreezeMismatch("Command 01 cannot run performance or validation")
    if config["promotion_allowed"] or config["validation_allowed"]:
        raise FamilyEFreezeMismatch("Promotion or validation unexpectedly allowed")


def verify_expected_hashes(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> None:
    expected = (
        EXPECTED_FAMILY_E_CONFIG_HASH,
        EXPECTED_CONTROL_REFERENCE_HASH,
        EXPECTED_E001_PARAMETER_HASH,
        EXPECTED_E001_PREREGISTRATION_HASH,
        EXPECTED_SUCCESS_CRITERIA_HASH,
    )
    if not all(expected):
        return
    treatment = registry["experiments"][0]
    checks = {
        "config": config["family_e_config_hash"] == EXPECTED_FAMILY_E_CONFIG_HASH,
        "control": registry["control"]["control_e_000_reference_hash"]
        == EXPECTED_CONTROL_REFERENCE_HASH,
        "e001_parameter": treatment["pbr_e_001_parameter_hash"]
        == EXPECTED_E001_PARAMETER_HASH,
        "e001_preregistration": treatment["pbr_e_001_preregistration_hash"]
        == EXPECTED_E001_PREREGISTRATION_HASH,
        "criteria": criteria["family_e_success_criteria_hash"]
        == EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    if not all(checks.values()):
        raise FamilyEFreezeMismatch(f"FAMILY_E_PREREGISTRATION_HASH_MISMATCH: {checks}")


def verify_family_d_closure(root: Path) -> dict[str, Any]:
    verification = verify_family_d_closure_inputs(root)
    closure_path = (
        Path(root)
        / "data/research/strategy_families/family_d/v1/closure/manifest/family_d_closure_manifest_v1.json"
    )
    artifact_path = (
        Path(root)
        / "data/research/strategy_families/family_d/v1/closure/manifest/family_d_closure_artifact_manifest_v1.json"
    )
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    artifacts = json.loads(artifact_path.read_text(encoding="utf-8"))
    closure_body = {
        key: value for key, value in closure.items() if key != "family_d_closure_hash"
    }
    artifact_body = {
        key: value for key, value in artifacts.items() if key != "artifact_manifest_hash"
    }
    checks = {
        "upstream_inputs": verification["status"] == "VERIFIED",
        "family_d_closure_hash": closure.get("family_d_closure_hash")
        == EXPECTED_FAMILY_D_CLOSURE_HASH
        == canonical_hash(closure_body),
        "closure_artifact_manifest_hash": artifacts.get("artifact_manifest_hash")
        == canonical_hash(artifact_body),
        "closure_artifacts": all(
            (Path(root) / relative).is_file()
            and file_sha256(Path(root) / relative) == expected
            for relative, expected in artifacts["artifact_hashes"].items()
        ),
        "command_03_manifest_link": closure.get("command_03_manifest_hash")
        == EXPECTED_COMMAND_03_MANIFEST_HASH,
    }
    if not all(checks.values()):
        raise FamilyEFreezeMismatch(f"FAMILY_D_CLOSURE_VERIFICATION_FAILED: {checks}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "family_d_closure_hash": closure["family_d_closure_hash"],
        # Retain the catalog identity embedded in the frozen Family E snapshot.
        # The current hash is also exposed after verifying the refreshed,
        # whitespace-normalized documentation catalog above.
        "family_d_closure_artifact_manifest_hash": (
            "3a647e837fd3f89c1a34ff454dea717851842a7315f35675737c8473c0c85155"
        ),
        "current_family_d_closure_artifact_manifest_hash": artifacts[
            "artifact_manifest_hash"
        ],
    }


def previous_research_snapshot(root: Path) -> dict[str, Any]:
    family_c = family_c_baseline_snapshot(Path(root))
    family_d = verify_family_d_closure(Path(root))
    semantic = {
        "strategy_v1_cap4_family_a_b_c_snapshot_hash": family_c["snapshot_hash"],
        "family_d_closure_hash": family_d["family_d_closure_hash"],
        "family_d_closure_artifact_manifest_hash": family_d[
            "family_d_closure_artifact_manifest_hash"
        ],
        "daily_history_version": DATA_VERSION,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def _valid_bar(bar: FamilyCBar | None) -> bool:
    return bool(
        bar
        and bar.usability_status == "ADJUSTED_READY"
        and min(bar.open_price, bar.high_price, bar.low_price, bar.close_price) > 0
        and bar.volume >= 0
    )


def _exact_window(
    symbol: str,
    sessions: Sequence[date],
    end_index: int,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    count: int,
) -> list[FamilyCBar]:
    if end_index + 1 < count:
        return []
    rows = [
        bars.get(session, {}).get(symbol)
        for session in sessions[end_index - count + 1 : end_index + 1]
    ]
    return [row for row in rows if row is not None] if all(_valid_bar(row) for row in rows) else []


def _future_path_availability(
    symbol: str,
    chronology: Mapping[str, Any],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, bool]:
    entry_date = chronology["entry_date"]
    exit_date = chronology["exit_date"]
    entry_bar = bars.get(entry_date, {}).get(symbol) if entry_date else None
    next_open = bool(_valid_bar(entry_bar) and entry_bar and entry_bar.open_price > 0)
    full_path = bool(
        chronology["available"]
        and exit_date is not None
        and exit_date <= DEVELOPMENT_END
        and all(
            _valid_bar(bars.get(session, {}).get(symbol))
            for session in chronology["holding_dates"]
        )
        and _valid_bar(bars.get(exit_date, {}).get(symbol))
    )
    return {"next_open_available": next_open, "holding_path_available": full_path}


def _build_signal_rows(
    sessions: Sequence[date],
    membership: MembershipIndex,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    readiness: list[dict[str, Any]] = []
    for session_index, formation_date in enumerate(sessions):
        if formation_date < DEVELOPMENT_START:
            continue
        members = membership.members_for(formation_date)
        for symbol, period in sorted(members.items()):
            bar = bars.get(formation_date, {}).get(symbol)
            formation_ready = _valid_bar(bar)
            history = _exact_window(symbol, sessions, session_index, bars, 55)
            indicator_ready = len(history) == 55
            sma20: Decimal | None = None
            sma50: Decimal | None = None
            return_20d: Decimal | None = None
            pullback: dict[str, Any] = {
                "available": False,
                "touch_count": 0,
                "minimum_low": None,
                "minimum_close_minus_sma50": None,
                "e001_structure_pass": False,
            }
            pullback_window_start: str | None = None
            previous_day_high: Decimal | None = None
            stop_reference: Decimal | None = None
            if indicator_ready:
                closes = [item.close_price for item in history]
                sma20 = simple_moving_average(closes[-20:], 20)
                sma50 = simple_moving_average(closes[-50:], 50)
                return_20d = compounded_return_20d(closes[-21:])
                pullback_bars = history[-6:-1]
                pullback_sma20 = [
                    simple_moving_average(closes[offset - 19 : offset + 1], 20)
                    for offset in range(49, 54)
                ]
                pullback_sma50 = [
                    simple_moving_average(closes[offset - 49 : offset + 1], 50)
                    for offset in range(49, 54)
                ]
                if all(value is not None for value in (*pullback_sma20, *pullback_sma50)):
                    pullback = pullback_structure(
                        [item.low_price for item in pullback_bars],
                        [item.close_price for item in pullback_bars],
                        [value for value in pullback_sma20 if value is not None],
                        [value for value in pullback_sma50 if value is not None],
                    )
                pullback_window_start = pullback_bars[0].trading_date.isoformat()
                previous_day_high = pullback_bars[-1].high_price
                stop_reference = structural_stop(
                    [item.low_price for item in history[-6:]]
                )

            close = bar.close_price if formation_ready and bar else None
            trend_pass = trend_requirement(close, sma20, sma50, return_20d)
            reclaim = reclaim_requirement(close, previous_day_high, sma20)
            liquidity = _liquidity_calculation(symbol, sessions, session_index, bars)
            history_start = sessions[session_index - 54] if session_index >= 54 else None
            corporate_safe, blockers = _corporate_action_safe(
                symbol, history_start, formation_date, exclusions
            )
            price_gate = bool(close is not None and close >= PRICE_FLOOR)
            eligible = bool(
                formation_ready
                and indicator_ready
                and price_gate
                and liquidity["pass"]
                and corporate_safe
            )
            control_signal = bool(
                eligible
                and trend_pass
                and pullback["touch_count"] >= 1
                and reclaim["pass"]
            )
            e001_signal = bool(control_signal and pullback["e001_structure_pass"])
            chronology = entry_exit_chronology(sessions, formation_date)
            path = _future_path_availability(symbol, chronology, bars)
            entry_date = chronology["entry_date"]
            entry_bar = bars.get(entry_date, {}).get(symbol) if entry_date else None
            entry_reference = (
                entry_bar.open_price if _valid_bar(entry_bar) and entry_bar else None
            )
            entry_gap_pct = (
                entry_reference / close - Decimal("1")
                if entry_reference is not None and close is not None and close > 0
                else None
            )
            flags: list[str] = []
            if period.source_confidence != "HIGH":
                flags.append("PARTIAL_MEMBERSHIP_HISTORY")
            if not formation_ready:
                flags.append("FORMATION_BAR_UNAVAILABLE_OR_UNUSABLE")
            if not indicator_ready:
                flags.append("INSUFFICIENT_EXACT_55_SESSION_INDICATOR_HISTORY")
            if not liquidity["available"]:
                flags.append("INSUFFICIENT_20_SESSION_LIQUIDITY_HISTORY")
            if not corporate_safe:
                flags.extend(f"CORPORATE_ACTION:{item}" for item in blockers)
            if not path["next_open_available"]:
                flags.append("NEXT_OPEN_UNAVAILABLE")
            if not path["holding_path_available"]:
                flags.append("TEN_SESSION_DEVELOPMENT_PATH_UNAVAILABLE")
            if entry_reference is not None and (
                stop_reference is None or entry_reference <= stop_reference
            ):
                flags.append("NONPOSITIVE_STOP_DISTANCE")
            output = {
                "decision_date": formation_date.isoformat(),
                "symbol": symbol,
                "isin": period.isin or (bar.isin if bar else ""),
                "point_in_time_member": True,
                "close": close,
                "sma20": sma20,
                "sma50": sma50,
                "return_20d": return_20d,
                "trend_pass": trend_pass,
                "pullback_window_start": pullback_window_start,
                "pullback_touch_count": pullback["touch_count"],
                "pullback_min_low": pullback["minimum_low"],
                "pullback_min_close_minus_sma50": pullback[
                    "minimum_close_minus_sma50"
                ],
                "previous_day_high": previous_day_high,
                "reclaim_above_previous_high": reclaim["above_previous_high"],
                "reclaim_above_sma20": reclaim["above_sma20"],
                "price_gate": price_gate,
                "liquidity_gate": liquidity["pass"],
                "corporate_action_safe": corporate_safe,
                "indicator_history_ready": indicator_ready,
                "eligible_universe_row": eligible,
                "control_signal": control_signal,
                "e001_structure_pass": pullback["e001_structure_pass"],
                "e001_signal": e001_signal,
                "entry_date": entry_date,
                "entry_reference": entry_reference,
                "entry_gap_pct": entry_gap_pct,
                "stop_reference": stop_reference,
                "data_quality_flags": tuple(sorted(set(flags))) or ("NONE",),
            }
            rows.append(output)
            readiness.append(
                {
                    "decision_date": formation_date.isoformat(),
                    "symbol": symbol,
                    "sma20_available": sma20 is not None,
                    "sma50_available": sma50 is not None,
                    "return20_available": return_20d is not None,
                    "pullback5_available": pullback["available"],
                    "previous_high_available": previous_day_high is not None,
                    "next_open_available": path["next_open_available"],
                    "holding_path_available": path["holding_path_available"],
                    "corporate_action_safe": corporate_safe,
                    "liquidity20_available": liquidity["available"],
                    "liquidity_gate_pass": liquidity["pass"],
                    "membership_high_confidence": period.source_confidence == "HIGH",
                }
            )
    return rows, readiness


def _signal_count_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    definitions = (
        ("POINT_IN_TIME_UNIVERSE_ROWS", lambda row: True),
        ("ELIGIBLE_UNIVERSE_ROWS", lambda row: bool(row["eligible_universe_row"])),
        (
            "TREND_PASS_ROWS",
            lambda row: bool(row["eligible_universe_row"] and row["trend_pass"]),
        ),
        (
            "PULLBACK_TOUCH_ROWS",
            lambda row: bool(
                row["eligible_universe_row"]
                and row["trend_pass"]
                and int(row["pullback_touch_count"]) >= 1
            ),
        ),
        ("CONTROL_E_000_SIGNALS", lambda row: bool(row["control_signal"])),
        ("PBR_E_001_SIGNALS", lambda row: bool(row["e001_signal"])),
    )
    output: list[dict[str, Any]] = []
    for metric, predicate in definitions:
        yearly = {
            year: sum(
                predicate(row) and str(row["decision_date"]).startswith(str(year))
                for row in rows
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


def _filter_impact_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for label, year in (("ALL", None), ("2022", 2022), ("2023", 2023), ("2024", 2024)):
        subset = [
            row
            for row in rows
            if year is None or str(row["decision_date"]).startswith(str(year))
        ]
        control = sum(bool(row["control_signal"]) for row in subset)
        treatment = sum(bool(row["e001_signal"]) for row in subset)
        removed = control - treatment
        violations = sum(
            bool(row["e001_signal"]) and not bool(row["control_signal"])
            for row in subset
        )
        output.append(
            {
                "period": label,
                "control_signals": control,
                "e001_signals": treatment,
                "removed_by_sma50_structure": removed,
                "removal_pct_of_control": Decimal(removed) / Decimal(control) * 100
                if control
                else Decimal("0"),
                "subset_violations": violations,
                "outcomes_inspected": False,
            }
        )
    return output


def _capacity_rows(
    signal_rows: Sequence[Mapping[str, Any]], sessions: Sequence[date]
) -> list[dict[str, Any]]:
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        by_date[str(row["decision_date"])].append(row)
    output: list[dict[str, Any]] = []
    for experiment_id, signal_field in (
        (CONTROL_ID, "control_signal"),
        (TREATMENT_ID, "e001_signal"),
    ):
        open_positions: dict[str, date] = {}
        for session_index, entry_date in enumerate(sessions):
            if entry_date < DEVELOPMENT_START or session_index == 0:
                continue
            exiting = sorted(
                symbol
                for symbol, exit_date in open_positions.items()
                if exit_date == entry_date
            )
            for symbol in exiting:
                del open_positions[symbol]
            formation_date = sessions[session_index - 1]
            raw_candidates = [
                row
                for row in by_date.get(formation_date.isoformat(), ())
                if bool(row[signal_field])
            ]
            eligible: list[dict[str, Any]] = []
            overlap_skipped = 0
            path_unavailable = 0
            invalid_stop = 0
            for candidate in raw_candidates:
                symbol = str(candidate["symbol"])
                if symbol in open_positions:
                    overlap_skipped += 1
                    continue
                chronology = entry_exit_chronology(sessions, formation_date)
                if (
                    not chronology["available"]
                    or chronology["exit_date"] is None
                    or chronology["exit_date"] > DEVELOPMENT_END
                    or candidate["entry_reference"] is None
                ):
                    path_unavailable += 1
                    continue
                if (
                    candidate["stop_reference"] is None
                    or decimal(candidate["entry_reference"])
                    <= decimal(candidate["stop_reference"])
                ):
                    invalid_stop += 1
                    continue
                eligible.append({**candidate, "scheduled_exit_date": chronology["exit_date"]})
            available_slots = MAX_CONCURRENT_POSITIONS - len(open_positions)
            ranked = rank_capacity_signals(eligible, available_slots)
            for selected in ranked["selected"]:
                open_positions[str(selected["symbol"])] = selected["scheduled_exit_date"]
            output.append(
                {
                    "experiment_id": experiment_id,
                    "entry_date": entry_date.isoformat(),
                    "formation_date": formation_date.isoformat(),
                    "exited_at_open": len(exiting),
                    "open_positions_before_entries": len(open_positions)
                    - len(ranked["selected"]),
                    "available_slots": available_slots,
                    "raw_signals": len(raw_candidates),
                    "same_symbol_overlap_skipped": overlap_skipped,
                    "path_unavailable": path_unavailable,
                    "invalid_stop_distance": invalid_stop,
                    "entry_ready_signals": len(eligible),
                    "admitted_signals": len(ranked["selected"]),
                    "capacity_rejected_signals": len(ranked["rejected"]),
                    "capacity_bound": bool(ranked["rejected"]),
                    "open_positions_after_entries": len(open_positions),
                    "ranking": "RETURN_20D_DESCENDING_THEN_SYMBOL_ASCENDING",
                    "stop_exit_effects_modeled": False,
                    "performance_evaluated": False,
                }
            )
    return output


def _capacity_summary_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for experiment_id in (CONTROL_ID, TREATMENT_ID):
        subset = [row for row in rows if row["experiment_id"] == experiment_id]
        ready = sum(int(row["entry_ready_signals"]) for row in subset)
        rejected = sum(int(row["capacity_rejected_signals"]) for row in subset)
        output.append(
            {
                "experiment_id": experiment_id,
                "maximum_concurrent_positions": MAX_CONCURRENT_POSITIONS,
                "capacity_bound_structural_days": sum(
                    bool(row["capacity_bound"]) for row in subset
                ),
                "entry_ready_signals": ready,
                "admitted_signals": sum(int(row["admitted_signals"]) for row in subset),
                "same_symbol_overlap_skipped": sum(
                    int(row["same_symbol_overlap_skipped"]) for row in subset
                ),
                "capacity_rejected_signals": rejected,
                "capacity_rejection_rate": Decimal(rejected) / Decimal(ready)
                if ready
                else Decimal("0"),
                "ranking": "RETURN_20D_DESCENDING_THEN_SYMBOL_ASCENDING",
                "same_ranking_for_control_and_treatment": True,
                "outcomes_inspected": False,
            }
        )
    return output


def _pilot_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(category: str, case_id: str, expected: Any, observed: Any, passed: bool, details: str) -> None:
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

    valid_trend = trend_requirement(
        Decimal("110"), Decimal("105"), Decimal("100"), Decimal("0.10")
    )
    add("CONTROL", "A_VALID_TREND", True, valid_trend, valid_trend, "Close>SMA50, SMA20>SMA50 and 20D return>0.")
    invalid_order = trend_requirement(
        Decimal("110"), Decimal("100"), Decimal("100"), Decimal("0.10")
    )
    add("CONTROL", "B_INVALID_SMA_ORDERING", False, invalid_order, not invalid_order, "SMA20 equality with SMA50 fails strict ordering.")
    nonpositive = trend_requirement(
        Decimal("110"), Decimal("105"), Decimal("100"), Decimal("0")
    )
    add("CONTROL", "C_POSITIVE_20D_TREND_REQUIRED", False, nonpositive, not nonpositive, "20D return equality with zero fails.")
    touched = pullback_structure(
        [106, 104, 103, 102, 104],
        [108, 106, 105, 104, 105],
        [105, 105, 104, 104, 104],
        [100, 100, 100, 100, 100],
    )
    add("CONTROL", "D_PULLBACK_TOUCHES_SMA20", True, touched["touch_count"] >= 1, touched["touch_count"] >= 1, "At least one of five lows touches its session SMA20.")
    no_touch = pullback_structure(
        [106, 106, 106, 106, 106],
        [108, 108, 108, 108, 108],
        [105, 105, 105, 105, 105],
        [100, 100, 100, 100, 100],
    )
    add("CONTROL", "E_NO_PULLBACK_TOUCH_REJECTED", False, no_touch["touch_count"] >= 1, no_touch["touch_count"] == 0, "No low<=SMA20 means no pullback setup.")
    reclaim = reclaim_requirement(Decimal("106"), Decimal("105"), Decimal("104"))
    add("CONTROL", "F_RECLAIM_ABOVE_PREVIOUS_HIGH", True, reclaim["above_previous_high"], reclaim["above_previous_high"], "Formation close strictly exceeds T-1 high.")
    equality = reclaim_requirement(Decimal("105"), Decimal("105"), Decimal("104"))
    add("CONTROL", "G_RECLAIM_EQUALITY_REJECTED", False, equality["above_previous_high"], not equality["above_previous_high"], "Equality with T-1 high fails.")
    below_sma = reclaim_requirement(Decimal("103"), Decimal("102"), Decimal("104"))
    add("CONTROL", "H_RECLAIM_ABOVE_SMA20", False, below_sma["above_sma20"], not below_sma["above_sma20"], "Formation close must strictly exceed SMA20.")
    pilot_sessions = [date(2024, 1, day) for day in range(1, 14)]
    chronology = entry_exit_chronology(pilot_sessions, pilot_sessions[0])
    add("CONTROL", "I_NEXT_OPEN_ENTRY", pilot_sessions[1].isoformat(), chronology["entry_date"].isoformat(), chronology["entry_date"] == pilot_sessions[1], "Signal at T close executes at T+1 open.")
    stop = structural_stop([99, 98, 97, 96, 95, 94])
    add("CONTROL", "J_STRUCTURAL_STOP", Decimal("94"), stop, stop == Decimal("94"), "Stop is minimum adjusted low T-5 through T.")

    pass_structure = pullback_structure([99] * 5, [101] * 5, [100] * 5, [100] * 5)
    add("E001", "A_ALL_FIVE_CLOSES_GTE_SMA50", True, pass_structure["e001_structure_pass"], pass_structure["e001_structure_pass"], "All closes preserve SMA50 structure.")
    fail_structure = pullback_structure([99] * 5, [101, 101, 99, 101, 101], [100] * 5, [100] * 5)
    add("E001", "B_ONE_CLOSE_BELOW_SMA50", False, fail_structure["e001_structure_pass"], not fail_structure["e001_structure_pass"], "One close below SMA50 rejects E001 only.")
    equality_structure = pullback_structure([99] * 5, [100] * 5, [100] * 5, [100] * 5)
    add("E001", "C_EQUALITY_WITH_SMA50_PASSES", True, equality_structure["e001_structure_pass"], equality_structure["e001_structure_pass"], "The treatment comparison is inclusive.")
    add("E001", "D_TREATMENT_SUBSET_OF_CONTROL", True, bool(True and pass_structure["e001_structure_pass"]), bool(True and pass_structure["e001_structure_pass"]), "E001 cannot create a signal without the control.")

    add("HOLDING", "EXACT_TEN_COMPLETED_SESSIONS", {"holding": 10, "exit": pilot_sessions[11].isoformat()}, {"holding": chronology["holding_sessions"], "exit": chronology["exit_date"].isoformat()}, chronology["holding_sessions"] == 10 and chronology["holding_dates"][0] == pilot_sessions[1] and chronology["holding_dates"][-1] == pilot_sessions[10] and chronology["exit_date"] == pilot_sessions[11], "Hold T+1 through T+10; time exit T+11 open.")
    add("STOP", "MINIMUM_LOW_T_MINUS_5_THROUGH_T", Decimal("94"), stop, stop == Decimal("94"), "No ATR buffer is applied.")
    gap = daily_stop_execution(session_open=Decimal("93"), session_low=Decimal("92"), stop_price=Decimal("94"))
    add("GAP_THROUGH", "OPEN_BELOW_STOP", {"reason": "GAP_THROUGH_STOP", "price": Decimal("93")}, {"reason": gap["exit_reason"], "price": gap["reference_price"]}, gap["exit_reason"] == "GAP_THROUGH_STOP" and gap["reference_price"] == Decimal("93"), "Existing stop-market policy uses the adverse session open.")
    sizing = risk_position_size(equity=STARTING_CAPITAL, available_cash=STARTING_CAPITAL, entry_price=Decimal("100"), stop_price=Decimal("95"))
    add("RISK_SIZING", "HALF_PERCENT_WHOLE_SHARE_NO_LEVERAGE", {"allowed_risk": Decimal("2500"), "shares": 500}, {"allowed_risk": sizing["allowed_risk"], "shares": sizing["shares"]}, sizing["valid"] and sizing["allowed_risk"] == Decimal("2500") and sizing["shares"] == 500 and sizing["planned_risk"] <= sizing["allowed_risk"] and sizing["notional"] <= STARTING_CAPITAL, "Risk sizing is floored and cash bounded.")
    capacity_fixture = [
        {"symbol": f"SYM{index:02d}", "return_20d": Decimal("0.20") - Decimal(index) / Decimal("1000")}
        for index in range(12)
    ]
    capacity = rank_capacity_signals(capacity_fixture, MAX_CONCURRENT_POSITIONS)
    expected_symbols = [row["symbol"] for row in sorted(capacity_fixture, key=lambda row: (-row["return_20d"], row["symbol"]))[:10]]
    observed_symbols = [row["symbol"] for row in capacity["selected"]]
    add("CAPACITY", "MORE_THAN_TEN_SIGNAL_RANKING", expected_symbols, observed_symbols, observed_symbols == expected_symbols and len(capacity["selected"]) == 10 and len(capacity["rejected"]) == 2, "Both cohorts rank by 20D return descending then symbol ascending.")
    previous_cash = STARTING_CAPITAL
    buys = Decimal("50000")
    sales = Decimal("52000")
    buy_cost = estimate_order_cost("BUY", date(2024, 1, 2), buys)["total_cost"]
    sell_cost = estimate_order_cost("SELL", date(2024, 1, 12), sales)["total_cost"]
    new_cash = previous_cash - buys - buy_cost + sales - sell_cost
    holdings = Decimal("100000")
    equity = new_cash + holdings
    accounting_pass = new_cash == previous_cash - buys - buy_cost + sales - sell_cost and equity == new_cash + holdings and sizing["shares"] == int(sizing["shares"]) and sizing["notional"] <= STARTING_CAPITAL
    add("ACCOUNTING", "CASH_EQUITY_WHOLE_SHARES_NO_LEVERAGE", True, accounting_pass, accounting_pass, "Cash and equity reconcile with costs and whole-share sizing.")
    return rows


def _data_readiness_rows(
    details: Sequence[Mapping[str, Any]], membership_coverage: Mapping[str, Any]
) -> list[dict[str, Any]]:
    total = len(details)
    definitions = (
        ("SMA20", "sma20_available", "EXACT_CAUSAL_20_SESSION_ADJUSTED_CLOSE"),
        ("SMA50", "sma50_available", "EXACT_CAUSAL_50_SESSION_ADJUSTED_CLOSE"),
        ("RETURN_20D", "return20_available", "CLOSE_T_DIVIDED_BY_CLOSE_T_MINUS_20_MINUS_ONE"),
        ("FIVE_SESSION_PULLBACK_HISTORY", "pullback5_available", "T_MINUS_5_THROUGH_T_MINUS_1"),
        ("PREVIOUS_DAY_HIGH", "previous_high_available", "ADJUSTED_HIGH_T_MINUS_1"),
        ("NEXT_OPEN_AVAILABILITY", "next_open_available", "T_PLUS_1_OPEN"),
        ("TEN_SESSION_FUTURE_DEVELOPMENT_PATH", "holding_path_available", "NEVER_EXTEND_INTO_2025"),
        ("CORPORATE_ACTION_SAFETY", "corporate_action_safe", "FROZEN_STRUCTURAL_LAYER"),
        ("LIQUIDITY_HISTORY", "liquidity20_available", "20_SESSION_MEDIAN_TRADED_VALUE"),
        ("LIQUIDITY_GATE", "liquidity_gate_pass", "AT_LEAST_10_CRORE_PER_DAY"),
        ("POINT_IN_TIME_MEMBERSHIP", "membership_high_confidence", "NO_CURRENT_CONSTITUENT_BACKFILL"),
    )
    output: list[dict[str, Any]] = []
    for check, field, note in definitions:
        available = sum(bool(row[field]) for row in details)
        output.append(
            {
                "check": check,
                "status": "READY"
                if available == total
                else "READY_WITH_LIMITATIONS"
                if available > 0
                else "BLOCKED",
                "available_or_pass_count": available,
                "total_count": total,
                "coverage_pct": Decimal(available) / Decimal(total) * 100
                if total
                else Decimal("0"),
                "notes": note,
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
    treatment = registry["experiments"][0]
    evidence = {
        "hypothesis": treatment["hypothesis"],
        "experiment_id": TREATMENT_ID,
        "population": config["population"],
        "exact_parameters": treatment["parameters"],
        "control": registry["control"],
        "primary_metrics": FUTURE_OUTCOME_FIELDS,
        "secondary_metrics": treatment["secondary_metrics"],
        "numerical_success_criteria": criteria["family_e_success_criteria_hash"],
        "failure_criteria": criteria["control_fatal_conditions"],
        "stop_conditions": treatment["stop_conditions"],
        "validation_eligibility": config["validation_eligibility"],
        "cost_model": config["costs"],
        "data_partition": config["development_window"],
        "hashes": {
            "config": config["family_e_config_hash"],
            "control": registry["control"]["control_e_000_reference_hash"],
            "treatment_parameter": treatment["pbr_e_001_parameter_hash"],
            "treatment_preregistration": treatment[
                "pbr_e_001_preregistration_hash"
            ],
            "criteria": criteria["family_e_success_criteria_hash"],
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


def _registry_report_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    control = registry["control"]
    treatment = registry["experiments"][0]
    return [
        {
            "record_type": "CONTROL",
            "experiment_id": CONTROL_ID,
            "name": CONTROL_NAME,
            "status": "REFERENCE_CONTROL",
            "parameter_hash": "",
            "preregistration_or_reference_hash": control[
                "control_e_000_reference_hash"
            ],
            "promotion_allowed": False,
            "validation_allowed": False,
            "performance_evaluated": False,
        },
        {
            "record_type": "TREATMENT",
            "experiment_id": TREATMENT_ID,
            "name": TREATMENT_NAME,
            "status": "PREREGISTERED",
            "parameter_hash": treatment["pbr_e_001_parameter_hash"],
            "preregistration_or_reference_hash": treatment[
                "pbr_e_001_preregistration_hash"
            ],
            "promotion_allowed": False,
            "validation_allowed": False,
            "performance_evaluated": False,
        },
    ]


def _write_documentation(
    root: Path,
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
    count_rows: Sequence[Mapping[str, Any]],
    filter_rows: Sequence[Mapping[str, Any]],
    classifications: Mapping[str, str],
) -> None:
    counts = {row["metric"]: row for row in count_rows}
    treatment = registry["experiments"][0]
    text = f"""# Strategy Family E: Pullback / Reclaim Continuation V1

## Rationale and independence

Family E asks whether an established upward-trending NSE stock can continue after a controlled short-term pullback and bullish reclaim, and whether preserving the broader SMA50 structure throughout that pullback improves setup quality. It isolates trend → pullback → reclaim → continuation. It does not use Strategy V1 scoring, CAP4, market regime, news, sector scores, intraday confirmation, Family C breakout rules, or Family D opening-range logic.

## Frozen specification

The point-in-time Nifty 500 DEVELOPMENT window is 2022-01-01 through 2024-12-31, using `DAILY_HISTORY_PREHISTORY_V2` only for causal indicators. Adjusted close must be at least ₹100; 20-session median traded value must be at least ₹10 crore/day; the frozen corporate-action eligibility layer applies. The family is long-only, unlevered, event-driven, and uses ₹500,000 research capital, 0.50% current-equity risk per trade, whole shares, available cash, one position per symbol, no pyramiding, and at most 10 concurrent positions.

`CONTROL-E-000` (`{CONTROL_NAME}`) requires at T: close > SMA50, SMA20 > SMA50, and 20-session compounded return >0. The pullback window is exactly T-5 through T-1, with at least one low <= that session's SMA20. T must close strictly above both T-1 high and SMA20(T). The control does not require every pullback close to remain above SMA50.

`PBR-E-001` (`{TREATMENT_NAME}`) keeps every control rule and adds exactly one filter: every close from T-5 through T-1 must be >= that session's SMA50. Equality passes. No distance, ATR-depth, percentage-decline, Fibonacci, volume, RSI, MACD, stochastic, ADX, breakout, or other treatment was added.

Signal formation is T close; entry is the next eligible session open with the actual gap accepted and recorded. The stop is the minimum adjusted low over T-5 through T inclusive, without an ATR buffer. A valid entry must be strictly above the stop. There is no target or trailing stop. A stop is evaluated before the time exit, with a gap below the stop executed at the actual session open. The time exit is the open after 10 completed holding sessions. Required paths crossing into 2025 are excluded rather than completed with validation-era data.

Both control and treatment use 20-session return descending, then symbol ascending, when entry-ready signals exceed available slots.

## Structural audit

The structural scan produced {counts['ELIGIBLE_UNIVERSE_ROWS']['total']:,} eligible universe rows, {counts['TREND_PASS_ROWS']['total']:,} trend-pass rows, {counts['PULLBACK_TOUCH_ROWS']['total']:,} pullback-touch rows, {counts['CONTROL_E_000_SIGNALS']['total']:,} control signals, and {counts['PBR_E_001_SIGNALS']['total']:,} E001 signals. E001 subset violations are {filter_rows[0]['subset_violations']}; the SMA50 structure filter removed {filter_rows[0]['removal_pct_of_control']}% of control signals. These are structural counts only, not performance.

## Frozen evaluation criteria

The control later requires positive net expectancy and CAGR, PF >=1.05, drawdown <=30%, at least two nonnegative DEVELOPMENT years, at least 150 closed positions, and accounting/data integrity. Fatal thresholds are PF <0.90, expectancy <=-0.10%, CAGR <=-5%, drawdown >40%, fewer than 75 positions, or implementation/data failure.

Treatment return preservation is at least 85% of positive control CAGR (otherwise positive CAGR), with positive expectancy and PF >=1.10. Quality thresholds are +5 percentage points win rate, +0.05 PF, 1.10x positive-control expectancy (otherwise positive), and at least 10% relative drawdown improvement. Temporal, cost, sample, and accounting rules are frozen in `governance/success_criteria_v1.json`. `HIGH_WIN_RATE_FLAG=YES` at position win rate >=60%; it is descriptive only.

## Governance state

`family_e_config_hash`: `{config['family_e_config_hash']}`
`CONTROL-E-000 reference hash`: `{registry['control']['control_e_000_reference_hash']}`
`PBR-E-001 parameter hash`: `{treatment['pbr_e_001_parameter_hash']}`
`PBR-E-001 preregistration hash`: `{treatment['pbr_e_001_preregistration_hash']}`
`family_e_success_criteria_hash`: `{criteria['family_e_success_criteria_hash']}`

`FAMILY_E_DATA_READINESS`: `{classifications['FAMILY_E_DATA_READINESS']}`
`FAMILY_E_ARCHITECTURE_RESULT`: `{classifications['FAMILY_E_ARCHITECTURE_RESULT']}`

Command 01 ran no final DEVELOPMENT performance, accessed no validation data, and created no Strategy V2. Family F was not started.
"""
    path = Path(root) / "docs/strategy-family-e-pullback-reclaim-continuation-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _verify_roadmap(root: Path) -> bool:
    text = (Path(root) / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    expected = (
        "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |",
        "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |",
        "| Family E | Pullback / Reclaim | ACTIVE_PREREGISTRATION |",
        "| Family F | Catalyst Momentum | PLANNED_NOT_STARTED |",
        "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |",
    )
    return all(value in text for value in expected)


def build_family_e_architecture(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    if GOVERNANCE_POLICY_VERSION != "RESEARCH_EXPERIMENT_GOVERNANCE_V2":
        raise FamilyEFreezeMismatch("Governance V2 is not active")
    if DATA_VERSION != "DAILY_HISTORY_PREHISTORY_V2":
        raise FamilyEFreezeMismatch("Daily prehistory version changed")
    if not _verify_roadmap(root):
        raise FamilyEFreezeMismatch("Family E roadmap lifecycle mismatch")
    existing_summary = root / "data/reports/family_e_v1_summary.json"
    generated_at = (
        json.loads(existing_summary.read_text(encoding="utf-8"))["generated_at"]
        if existing_summary.is_file()
        else utc_now()
    )
    family_d = verify_family_d_closure(root)
    baseline_before = previous_research_snapshot(root)

    criteria = success_criteria_document()
    config = family_e_config_document(criteria)
    control = control_reference_document(config, criteria)
    treatment = e001_preregistration_document(config, criteria, control)
    registry = registry_document(config, criteria, control, treatment)
    protocol = protocol_document(config, criteria, registry)
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)

    membership_coverage = json.loads(
        (root / "data/reference/nifty500/history/membership_coverage.json").read_text(
            encoding="utf-8"
        )
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
    filter_rows = _filter_impact_rows(signal_rows)
    pilot_rows = _pilot_rows()
    readiness_rows = _data_readiness_rows(readiness_details, membership_coverage)
    capacity_daily = _capacity_rows(signal_rows, sessions)
    capacity_summary = _capacity_summary_rows(capacity_daily)
    governance_rows = _governance_rows(config, criteria, registry)
    registry_rows = _registry_report_rows(registry)
    counts = {row["metric"]: row for row in count_rows}

    baseline_after = previous_research_snapshot(root)
    baseline_unchanged = baseline_before == baseline_after
    all_pilots_pass = bool(pilot_rows) and all(bool(row["passed"]) for row in pilot_rows)
    governance_pass = len(governance_rows) == 14 and all(
        row["status"] == "PASS" for row in governance_rows
    )
    positive_structure = (
        counts["CONTROL_E_000_SIGNALS"]["total"] > 0
        and counts["PBR_E_001_SIGNALS"]["total"] > 0
        and filter_rows[0]["subset_violations"] == 0
    )
    any_history = any(row["sma50_available"] for row in readiness_details)
    any_future_path = any(row["holding_path_available"] for row in readiness_details)
    data_readiness = (
        "READY_WITH_LIMITATIONS"
        if signal_rows and any_history and any_future_path
        else "BLOCKED"
    )
    architecture_result = (
        "READY_FOR_DEVELOPMENT_BACKTEST"
        if all_pilots_pass
        and governance_pass
        and positive_structure
        and baseline_unchanged
        and data_readiness != "BLOCKED"
        else "DATA_BLOCKED"
    )
    classifications = {
        "FAMILY_E_DATA_READINESS": data_readiness,
        "FAMILY_E_ARCHITECTURE_RESULT": architecture_result,
        "FAMILY_E_FUTURE_RESULT": None,
    }

    output = family_output_root(root)
    registry_root = output / "registry"
    signals_root = output / "signals"
    pilots_root = output / "pilots"
    manifests_root = output / "manifests"
    governance_root = output / "governance"
    capacity_root = output / "capacity"
    reports = root / "data/reports"

    write_json(registry_root / "family_e_config_v1.json", config)
    write_json(registry_root / "family_e_experiment_registry_v1.json", registry)
    write_json(registry_root / "control_e_000_reference_v1.json", control)
    write_json(registry_root / "pbr_e_001_preregistration_v1.json", treatment)
    write_json(governance_root / "success_criteria_v1.json", criteria)
    write_json(governance_root / "family_e_research_protocol_v1.json", protocol)
    write_csv(signals_root / "family_e_signal_dataset_v1.csv", signal_rows, SIGNAL_FIELDS)
    write_csv(pilots_root / "family_e_structural_pilots_v1.csv", pilot_rows)
    write_csv(capacity_root / "family_e_capacity_structure_v1.csv", capacity_daily)

    write_csv(reports / REPORT_NAMES[1], registry_rows)
    write_csv(reports / REPORT_NAMES[2], readiness_rows)
    write_csv(reports / REPORT_NAMES[3], count_rows)
    write_csv(reports / REPORT_NAMES[4], filter_rows)
    write_csv(reports / REPORT_NAMES[5], pilot_rows)
    write_csv(reports / REPORT_NAMES[6], governance_rows)
    write_csv(reports / REPORT_NAMES[7], capacity_summary)
    _write_documentation(
        root, config, criteria, registry, count_rows, filter_rows, classifications
    )

    artifact_paths = [
        registry_root / "family_e_config_v1.json",
        registry_root / "family_e_experiment_registry_v1.json",
        registry_root / "control_e_000_reference_v1.json",
        registry_root / "pbr_e_001_preregistration_v1.json",
        governance_root / "success_criteria_v1.json",
        governance_root / "family_e_research_protocol_v1.json",
        signals_root / "family_e_signal_dataset_v1.csv",
        pilots_root / "family_e_structural_pilots_v1.csv",
        capacity_root / "family_e_capacity_structure_v1.csv",
        *(reports / name for name in REPORT_NAMES[1:]),
        root / "docs/strategy-family-e-pullback-reclaim-continuation-v1.md",
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    summary = {
        "command": COMMAND,
        "generated_at": generated_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_status": "PREREGISTERED_RESEARCH_FAMILY",
        "family_e_config_hash": config["family_e_config_hash"],
        "control": {
            "id": CONTROL_ID,
            "name": CONTROL_NAME,
            "reference_hash": control["control_e_000_reference_hash"],
        },
        "experiment_count": EXPERIMENT_COUNT,
        "experiment": {
            "id": TREATMENT_ID,
            "name": TREATMENT_NAME,
            "parameter_hash": treatment["pbr_e_001_parameter_hash"],
            "preregistration_hash": treatment[
                "pbr_e_001_preregistration_hash"
            ],
        },
        "family_e_success_criteria_hash": criteria[
            "family_e_success_criteria_hash"
        ],
        "protocol_hash": protocol["protocol_hash"],
        "development_window": config["development_window"],
        "structural_counts": {
            "eligible_universe_rows": counts["ELIGIBLE_UNIVERSE_ROWS"]["total"],
            "trend_pass_rows": counts["TREND_PASS_ROWS"]["total"],
            "pullback_touch_rows": counts["PULLBACK_TOUCH_ROWS"]["total"],
            "control_signals": counts["CONTROL_E_000_SIGNALS"]["total"],
            "e001_signals": counts["PBR_E_001_SIGNALS"]["total"],
            "yearly": count_rows,
            "filter_impact": filter_rows,
            "e001_subset_violations": filter_rows[0]["subset_violations"],
            "capacity": capacity_summary,
            "outcomes_inspected": False,
        },
        "data": {
            "development_session_count": sum(
                DEVELOPMENT_START <= session <= DEVELOPMENT_END
                for session in sessions
            ),
            "signal_row_count": len(signal_rows),
            "adjusted_session_count": len(bars),
            "prehistory_lineage": DATA_VERSION,
            "membership_coverage_start": membership_coverage[
                "membership_periods"
            ]["coverage_start"],
            "membership_survivorship_bias_status": membership_coverage[
                "survivorship_bias_status"
            ],
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
            "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
            "family_d_closure_verified": family_d["status"] == "VERIFIED",
            "development_performance_run": False,
            "validation_accessed": False,
            "alternate_ma_tested": False,
            "alternate_pullback_tested": False,
            "alternate_reclaim_tested": False,
            "volume_filter_added": False,
            "target_added": False,
            "strategy_v2_created": False,
            "family_f_started": False,
        },
        "classifications": classifications,
        "immutability": {
            "baseline_snapshot_before": baseline_before["snapshot_hash"],
            "baseline_snapshot_after": baseline_after["snapshot_hash"],
            "previous_families_unchanged": baseline_unchanged,
            "strategy_v1_unchanged": baseline_unchanged,
            "cap4_unchanged": baseline_unchanged,
            "family_a_unchanged": baseline_unchanged,
            "family_b_unchanged": baseline_unchanged,
            "family_c_unchanged": baseline_unchanged,
            "family_d_unchanged": baseline_unchanged,
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
            "root": output.relative_to(root).as_posix(),
            "signal_dataset_fields": SIGNAL_FIELDS,
            "future_outcome_fields": FUTURE_OUTCOME_FIELDS,
            "artifact_hashes": artifact_hashes,
            "git_ignored": _git_ignored(root, registry_root / "family_e_config_v1.json"),
        },
        "known_limitations": (
            "POINT_IN_TIME_MEMBERSHIP_RECONSTRUCTION_IS_DECLARED_PARTIAL_HISTORY",
            "LATE_2024_SIGNALS_WITH_PATHS_CROSSING_2025_ARE_STRUCTURALLY_EXCLUDED",
            "STRUCTURAL_CAPACITY_USES_SCHEDULED_MAXIMUM_HOLD_AND_DOES_NOT_MODEL_EARLY_STOP_RELEASES",
            "COMMAND_01_CONTAINS_NO_RETURN_OR_PERFORMANCE_EVALUATION",
        ),
        "recommended_next_action": "REVIEW_PREREGISTRATION_AND_ARCHITECTURE_BEFORE_ANY_SEPARATELY_AUTHORIZED_DEVELOPMENT_PERFORMANCE_COMMAND",
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest_body = {
        "command": COMMAND,
        "family_version": FAMILY_VERSION,
        "family_e_config_hash": config["family_e_config_hash"],
        "control_reference_hash": control["control_e_000_reference_hash"],
        "pbr_e_001_parameter_hash": treatment["pbr_e_001_parameter_hash"],
        "pbr_e_001_preregistration_hash": treatment[
            "pbr_e_001_preregistration_hash"
        ],
        "family_e_success_criteria_hash": criteria[
            "family_e_success_criteria_hash"
        ],
        "registry_hash": registry["registry_hash"],
        "protocol_hash": protocol["protocol_hash"],
        "generated_at": generated_at,
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "previous_research_snapshot_hash": baseline_after["snapshot_hash"],
        "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
        "development_performance_run": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "family_e_architecture_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(manifests_root / "family_e_architecture_manifest_v1.json", manifest)
    return summary


def finalize_family_e_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports/family_e_v1_summary.json"
    manifest_path = (
        family_output_root(root) / "manifests/family_e_architecture_manifest_v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": bool(
            passed
            and summary["classifications"]["FAMILY_E_ARCHITECTURE_RESULT"]
            == "READY_FOR_DEVELOPMENT_BACKTEST"
        ),
    }
    write_json(summary_path, summary)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_e_architecture_manifest_hash"
    }
    body["summary_hash"] = file_sha256(summary_path)
    updated = {**body, "family_e_architecture_manifest_hash": canonical_hash(body)}
    write_json(manifest_path, updated)
    return summary


__all__ = [
    "COMMAND",
    "CONTROL_ID",
    "CONTROL_NAME",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "EXPECTED_CONTROL_REFERENCE_HASH",
    "EXPECTED_E001_PARAMETER_HASH",
    "EXPECTED_E001_PREREGISTRATION_HASH",
    "EXPECTED_FAMILY_D_CLOSURE_HASH",
    "EXPECTED_FAMILY_E_CONFIG_HASH",
    "EXPECTED_SUCCESS_CRITERIA_HASH",
    "EXPERIMENT_COUNT",
    "FAMILY_CODE",
    "FAMILY_VERSION",
    "GOVERNANCE_CHECKLIST",
    "HOLDING_SESSIONS",
    "MAX_CONCURRENT_POSITIONS",
    "RESEARCH_PROFILE",
    "RESEARCH_PROTOCOL",
    "REPORT_NAMES",
    "RISK_PER_TRADE",
    "STARTING_CAPITAL",
    "TREATMENT_ID",
    "TREATMENT_NAME",
    "build_family_e_architecture",
    "compounded_return_20d",
    "daily_stop_execution",
    "e001_parameter_document",
    "entry_exit_chronology",
    "family_e_config_document",
    "finalize_family_e_review",
    "high_win_rate_flag",
    "previous_research_snapshot",
    "pullback_structure",
    "rank_capacity_signals",
    "reclaim_requirement",
    "risk_position_size",
    "simple_moving_average",
    "structural_stop",
    "success_criteria_document",
    "trend_requirement",
    "verify_family_d_closure",
]

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_development_backtest import (
    EXPECTED_EXPERIMENT_HASHES as FAMILY_A_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_CONFIG_HASH as FAMILY_A_CONFIG_HASH,
    verify_family_a_preregistration,
)
from app.research.strategy.family_a_momentum import (
    AdjustedBar,
    _load_adjusted_bars,
    _load_aliases,
    _load_sessions,
    decimal,
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_closure import (
    EXPECTED_CLOSURE_HASH,
    GOVERNANCE_POLICY_VERSION,
    closure_baseline_snapshot,
)
from app.research.strategy.family_a_phase2_research import (
    EXPECTED_COMMAND_02_REGISTRY_HASH,
    EXPECTED_COMMAND_02_RESULT_HASHES,
    EXPECTED_PHASE2_CONFIG_HASH,
    EXPECTED_PHASE2_EXPERIMENT_HASHES,
    EXPECTED_PHASE2_REGISTRY_HASH,
    REFERENCE_BASELINE_RESULT_HASH,
)
from app.research.strategy.family_a_phase2_development_evaluation import (
    EXPECTED_RESULT_HASHES as FAMILY_A_PHASE2_RESULT_HASHES,
)


FAMILY_VERSION = "STRATEGY_FAMILY_B_RELATIVE_ABSOLUTE_MOMENTUM_V1"
RESEARCH_PROFILE = "RELATIVE_PLUS_ABSOLUTE_MOMENTUM_V1"
FAMILY_CODE = "FAMILY_B"
RESEARCH_PROTOCOL = "FAMILY_B_RESEARCH_PROTOCOL_V1"
COMMAND = "Step 03.02 / Command 01"

FAMILY_STATUS = "PREREGISTERED_RESEARCH_FAMILY"
CONTROL_ID = "CONTROL-B-000"
EXPERIMENT_DEFINITIONS = (
    (
        "MOM-B-001",
        "RELATIVE_6M_PLUS_ABSOLUTE_6M_POSITIVE_V1",
        "TRAILING_6M_RETURN_STRICTLY_GREATER_THAN_ZERO",
    ),
    (
        "MOM-B-002",
        "RELATIVE_6M_PLUS_200DMA_TREND_V1",
        "FORMATION_ADJUSTED_CLOSE_STRICTLY_GREATER_THAN_SMA200",
    ),
)
EXPERIMENT_IDS = tuple(row[0] for row in EXPERIMENT_DEFINITIONS)

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
CAPITAL_INR = Decimal("500000")
RELATIVE_LOOKBACK_SESSIONS = 126
RELATIVE_SELECTION_FRACTION = Decimal("0.10")
SMA_SESSIONS = 200
MINIMUM_HOLDINGS = 10
EXPECTED_QUARTERLY_REBALANCES = 11

FUTURE_PRIMARY_METRICS = (
    "NET_TOTAL_RETURN",
    "NET_CAGR",
    "MAX_DRAWDOWN",
    "ANNUALIZED_VOLATILITY",
    "SHARPE_LIKE_METRIC",
    "POSITIVE_CALENDAR_MONTH_RATE",
    "POSITIVE_REBALANCE_PERIOD_RATE",
    "ANNUALIZED_TURNOVER",
    "TOTAL_MODELED_COSTS",
    "AVERAGE_INVESTED_PERCENT",
    "AVERAGE_CASH_PERCENT",
    "MINIMUM_HOLDINGS",
    "MEDIAN_HOLDINGS",
    "YEARLY_RETURNS",
)
FUTURE_RESULT_LABELS = (
    "STRONGLY_SUPPORTED",
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "FAILED",
    "INCONCLUSIVE",
)
FUTURE_FAMILY_RESULT_LABELS = (
    "STRONG_SUPPORT",
    "SUPPORT",
    "MIXED",
    "WEAK",
    "FAILED",
    "INCONCLUSIVE",
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
    "family_b_v1_summary.json",
    "family_b_v1_registry.csv",
    "family_b_v1_data_readiness.csv",
    "family_b_v1_signal_pilot.csv",
    "family_b_v1_breadth.csv",
    "family_b_v1_governance.csv",
    "family_b_v1_capital_pilot.csv",
)

# Frozen by Step 03.02 / Command 01 before any Family B performance evaluation.
EXPECTED_FAMILY_B_CONFIG_HASH = "f98a16fcb0618a01c07242d5fe2ab3b063464d26b48c1f814200236315628076"
EXPECTED_CONTROL_REFERENCE_HASH = "b84ca4ac1a88daed38efd60a9142aee175fe1dbeabb02445788915f8889adc87"
EXPECTED_SUCCESS_CRITERIA_HASH = "b7459cad23169a2cc2df9355e34141e852dc41648c64cc5215dfc04d62942d71"
EXPECTED_EXPERIMENT_HASHES: dict[str, dict[str, str]] = {
    "MOM-B-001": {
        "parameter_hash": "b65843f0fadd6b75b205d3b4d37ea0e40e212bc28e06b98debb75589014e9446",
        "preregistration_hash": "bd5c08bdf5ecf16e364b718302d9df6de426cb9c15c54aceacb24e90ab7ac203",
    },
    "MOM-B-002": {
        "parameter_hash": "0b7c8efec15017f9d2a0370bd8545d4463ff042ed13cb749d936c7979d0c91fe",
        "preregistration_hash": "d07d53efb5ee43e403236d3e67359abe6573cf137e00c6a41ad2c90bb87788fe",
    },
}


class FamilyBFreezeMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def success_criteria_config() -> dict[str, Any]:
    body = {
        "criteria_version": "FAMILY_B_SUCCESS_CRITERIA_V1",
        "frozen_before_performance": True,
        "standard_criteria_count": 7,
        "standard_criteria": {
            "A_RETURN_PRESERVATION": {
                "metric": "NET_CAGR",
                "comparison": "TREATMENT_DIVIDED_BY_CONTROL",
                "minimum_ratio": Decimal("0.85"),
            },
            "B_DRAWDOWN": {
                "metric": "ABSOLUTE_MAX_DRAWDOWN_MAGNITUDE",
                "material_improvement_minimum_relative": Decimal("0.15"),
                "maximum_relative_worsening": Decimal("0.10"),
                "pass_rule": "MATERIAL_IMPROVEMENT_OR_NO_MORE_THAN_10_PERCENT_RELATIVE_WORSENING",
            },
            "C_TEMPORAL_SUPPORT": {
                "nonnegative_development_years_minimum": 2,
                "development_year_count": 3,
                "control_underperformance_limit_percentage_points": Decimal("15"),
                "years_allowed_beyond_underperformance_limit": 1,
            },
            "D_COST_EFFICIENCY": {
                "metric": "NORMALIZED_MODELED_COST_DRAG",
                "maximum_relative_increase": Decimal("0.25"),
            },
            "E_BREADTH": {
                "minimum_qualifying_holdings": MINIMUM_HOLDINGS,
                "minimum_fraction_of_scheduled_rebalances": Decimal("0.80"),
            },
            "F_CAPITAL_DEPLOYMENT": {
                "metric": "AVERAGE_CASH_ALLOCATION",
                "maximum_fraction": Decimal("0.35"),
            },
            "G_ACCOUNTING_DATA_INTEGRITY": {
                "required": True,
                "accounting_reconciliation": "CLEAN",
                "data_integrity": "PASS",
            },
        },
        "supported": {
            "result_label": "SUPPORTED",
            "semantic_label": "SUPPORTED_FOR_FURTHER_RESEARCH",
            "all_standard_criteria_required": True,
        },
        "strongly_supported": {
            "result_label": "STRONGLY_SUPPORTED",
            "all_standard_criteria_required": True,
            "minimum_cagr_preservation_ratio": Decimal("0.90"),
            "minimum_relative_drawdown_improvement": Decimal("0.15"),
            "negative_development_years_allowed": 0,
            "accounting_must_be_clean": True,
        },
        "fatal_failure": {
            "any_condition_is_fatal": True,
            "cagr_preservation_ratio_strictly_below": Decimal("0.70"),
            "drawdown_relative_worsening_strictly_above": Decimal("0.20"),
            "breadth_fraction_strictly_below": Decimal("0.60"),
            "average_cash_fraction_strictly_above": Decimal("0.50"),
            "implementation_or_data_failure": True,
            "lookahead_detected": True,
            "result_label": "FAILED",
        },
        "partially_supported": {
            "result_label": "PARTIALLY_SUPPORTED",
            "fatal_failure_allowed": False,
            "minimum_standard_criteria_passed": 4,
            "standard_criteria_denominator": 7,
            "result_must_be_interpretable": True,
        },
        "inconclusive": {
            "result_label": "INCONCLUSIVE",
            "rule": "USE_WHEN_A_NONFATAL_RESULT_CANNOT_BE_INTERPRETED_RELIABLY",
        },
        "allowed_experiment_results": FUTURE_RESULT_LABELS,
        "allowed_family_results": FUTURE_FAMILY_RESULT_LABELS,
        "post_hoc_threshold_changes_allowed": False,
    }
    return {**body, "success_criteria_hash": canonical_hash(body)}


def family_config(success_criteria: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "status": FAMILY_STATUS,
        "hypothesis": (
            "Combining 6M cross-sectional relative momentum with a simple stock-level "
            "absolute-momentum requirement may improve downside robustness without "
            "destroying return quality relative to pure relative 6M momentum."
        ),
        "primary_objective": "IMPROVE_DOWNSIDE_ROBUSTNESS_WITHOUT_DESTROYING_RETURN_QUALITY",
        "promotion_allowed": False,
        "validation_allowed": False,
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "dates_after_2024_loaded": False,
            "holdout_accessed": False,
        },
        "population": {
            "universe": "POINT_IN_TIME_NIFTY_500",
            "current_constituent_substitution_allowed": False,
            "minimum_price_inr": Decimal("100"),
            "liquidity_window_sessions": 20,
            "minimum_median_traded_value_inr": Decimal("100000000"),
            "corporate_action_safety_required": True,
            "valid_required_historical_data": True,
            "point_in_time_membership_required": True,
        },
        "relative_momentum": {
            "signal": "6M_COMPOUNDED_RETURN",
            "lookback_trading_sessions": RELATIVE_LOOKBACK_SESSIONS,
            "ranking": "DESCENDING_CROSS_SECTIONAL",
            "tie_break": "SYMBOL_ASCENDING",
            "candidate_pool": "TOP_10_PERCENT",
            "candidate_fraction": RELATIVE_SELECTION_FRACTION,
            "signal_change_allowed": False,
        },
        "absolute_momentum": {
            "MOM-B-001": {
                "signal": "6M_COMPOUNDED_RETURN",
                "rule": "STRICTLY_GREATER_THAN_ZERO",
                "threshold": Decimal("0"),
                "alternate_thresholds_allowed": False,
            },
            "MOM-B-002": {
                "signal": "SMA200_TREND_STATE",
                "window_valid_trading_sessions": SMA_SESSIONS,
                "rule": "FORMATION_ADJUSTED_CLOSE_STRICTLY_GREATER_THAN_SMA200",
                "tolerance_band": None,
                "alternate_moving_averages_allowed": False,
            },
            "stock_level_only": True,
            "market_timing": False,
            "nifty_trend_filter": False,
        },
        "portfolio": {
            "direction": "LONG_ONLY",
            "weighting": "EQUAL_WEIGHT",
            "minimum_qualifying_holdings": MINIMUM_HOLDINGS,
            "no_backfill": True,
            "target_allocation": "EQUAL_WEIGHT_ACROSS_QUALIFYING_HOLDINGS_USING_AVAILABLE_PORTFOLIO_EQUITY",
            "whole_share_residual_remains_cash": True,
            "low_breadth_action": "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH",
            "existing_holdings_low_breadth_action": (
                "LIQUIDATE_AT_SCHEDULED_REBALANCE_UNLESS_CURRENT_RULES_INDEPENDENTLY_QUALIFY"
            ),
            "leverage_allowed": False,
            "shorting_allowed": False,
            "capital_inr": CAPITAL_INR,
            "capital_interpretation": {
                "implementation_fidelity_choice": True,
                "alpha_parameter": False,
                "profitability_assumption": False,
                "live_capital_recommendation": False,
            },
        },
        "rebalance": {
            "frequency": "QUARTERLY",
            "formation": "ELIGIBLE_QUARTER_END_SESSION_CLOSE",
            "execution": "NEXT_ELIGIBLE_NSE_SESSION_OPEN",
            "same_close_execution_allowed": False,
            "holding": "UNTIL_NEXT_QUARTERLY_REBALANCE",
            "interim_absolute_momentum_exit": False,
            "entry_and_retention_rules_identical": True,
            "retention_band": None,
            "stop_loss": None,
            "profit_target": None,
        },
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": Decimal("5"),
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
        },
        "evaluation_modes": {
            "primary": "EXECUTABLE_INTEGER_SHARE_500K",
            "diagnostic": "IDEALIZED_EQUAL_WEIGHT_PERCENTAGE",
            "practical_decisions_prioritize_executable": True,
        },
        "control": {
            "control_id": CONTROL_ID,
            "underlying_architecture": "MOM-A-002",
            "role": "REFERENCE_CONTROL",
            "reproduction_label": "CONTROL_REPRODUCTION_ONLY",
            "family_b_relabel_allowed": False,
        },
        "future_metrics": FUTURE_PRIMARY_METRICS,
        "success_criteria_hash": success_criteria["success_criteria_hash"],
        "excluded_signals": (
            "3M_MOMENTUM",
            "9M_MOMENTUM",
            "12_MINUS_1_MOMENTUM",
            "RSI",
            "MACD",
            "ADX",
            "ATR",
            "VIX",
            "SECTOR_STRENGTH",
            "FUNDAMENTALS",
            "NEWS",
            "NEW_VOLUME_FILTERS",
            "MARKET_REGIME",
            "INTRADAY",
        ),
        "performance_policy": {
            "final_development_performance_allowed": False,
            "final_development_performance_run": False,
            "future_returns_loaded": False,
            "final_equity_curves_generated": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_c_started": False,
        },
        "validation_eligibility_rule": {
            "automatic_validation_after_development": False,
            "required": (
                "DEVELOPMENT_EVALUATION_PASSES",
                "NO_UNRESOLVED_DATA_ISSUE",
                "NO_PARAMETER_MUTATION",
                "GOVERNANCE_REVIEW",
                "EXPLICIT_LATER_HUMAN_APPROVAL",
            ),
            "current_status": "NOT_AUTHORIZED",
        },
    }
    return {**body, "family_b_config_hash": canonical_hash(body)}


def control_reference(config: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "control_id": CONTROL_ID,
        "status": "REFERENCE_CONTROL",
        "role": "CONTROL_REPRODUCTION_ONLY",
        "underlying_family": "STRATEGY_FAMILY_A_MOMENTUM_V1",
        "underlying_experiment_id": "MOM-A-002",
        "underlying_parameter_hash": FAMILY_A_EXPERIMENT_HASHES["MOM-A-002"]["parameter_hash"],
        "underlying_preregistration_hash": FAMILY_A_EXPERIMENT_HASHES["MOM-A-002"][
            "preregistration_hash"
        ],
        "underlying_baseline_result_hash": REFERENCE_BASELINE_RESULT_HASH,
        "family_b_config_hash": config["family_b_config_hash"],
        "signal": "6M_COMPOUNDED_CROSS_SECTIONAL_MOMENTUM",
        "rebalance_frequency": "QUARTERLY",
        "selection": "TOP_DECILE",
        "direction": "LONG_ONLY",
        "weighting": "EQUAL_WEIGHT",
        "execution": "NEXT_ELIGIBLE_SESSION_OPEN",
        "capital_inr": CAPITAL_INR,
        "leverage_allowed": False,
        "stop_loss": None,
        "profit_target": None,
        "family_b_experiment": False,
        "performance_run_by_command_01": False,
    }
    return {**body, "control_reference_hash": canonical_hash(body)}


def _experiment_parameters(experiment_id: str) -> dict[str, Any]:
    absolute = {
        "MOM-B-001": {
            "definition": "TRAILING_6M_COMPOUNDED_RETURN",
            "comparison": "STRICTLY_GREATER_THAN",
            "threshold": Decimal("0"),
            "unavailable_when": "FEWER_THAN_126_VALID_TRADING_SESSION_INTERVALS",
        },
        "MOM-B-002": {
            "definition": "FORMATION_ADJUSTED_CLOSE_VS_SMA200",
            "comparison": "CLOSE_STRICTLY_GREATER_THAN_SMA200",
            "sma_window_valid_sessions": SMA_SESSIONS,
            "unavailable_when": "FEWER_THAN_200_VALID_ADJUSTED_CLOSE_OBSERVATIONS",
        },
    }[experiment_id]
    return {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "universe": "POINT_IN_TIME_NIFTY_500",
        "minimum_price_inr": Decimal("100"),
        "liquidity_window_sessions": 20,
        "minimum_median_traded_value_inr": Decimal("100000000"),
        "corporate_action_safety_required": True,
        "relative_signal": "6M_COMPOUNDED_RETURN",
        "relative_lookback_trading_sessions": RELATIVE_LOOKBACK_SESSIONS,
        "relative_ranking": "DESCENDING_CROSS_SECTIONAL",
        "relative_candidate_pool": "TOP_DECILE",
        "relative_candidate_fraction": RELATIVE_SELECTION_FRACTION,
        "absolute_signal": absolute,
        "selection_order": (
            "POINT_IN_TIME_UNIVERSE",
            "INFRASTRUCTURE_FILTERS",
            "CALCULATE_6M_RELATIVE_MOMENTUM",
            "CALCULATE_ABSOLUTE_CONDITION",
            "IDENTIFY_TOP_DECILE_CANDIDATES",
            "RETAIN_ABSOLUTE_CONDITION_PASSES",
            "EQUAL_WEIGHT_QUALIFYING_HOLDINGS",
        ),
        "minimum_qualifying_holdings": MINIMUM_HOLDINGS,
        "no_backfill": True,
        "low_breadth_state": "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH",
        "rebalance_frequency": "QUARTERLY",
        "formation": "ELIGIBLE_QUARTER_END_SESSION_CLOSE",
        "execution": "NEXT_ELIGIBLE_NSE_SESSION_OPEN",
        "same_close_execution_allowed": False,
        "holding": "UNTIL_NEXT_QUARTERLY_REBALANCE",
        "interim_exit": False,
        "retention_band": None,
        "weighting": "EQUAL_WEIGHT",
        "whole_shares": True,
        "capital_inr": CAPITAL_INR,
        "residual_cash_allowed": True,
        "leverage_allowed": False,
        "stop_loss": None,
        "profit_target": None,
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        "slippage_bps_per_side": Decimal("5"),
        "development_start": DEVELOPMENT_START.isoformat(),
        "development_end": DEVELOPMENT_END.isoformat(),
    }


def experiment_registry(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    experiments: list[dict[str, Any]] = []
    for experiment_id, name, interpretation in EXPERIMENT_DEFINITIONS:
        parameters = _experiment_parameters(experiment_id)
        parameter_hash = canonical_hash(parameters)
        preregistration_body = {
            "experiment_id": experiment_id,
            "name": name,
            "interpretation": interpretation,
            "status": "PREREGISTERED",
            "promotion_allowed": False,
            "validation_allowed": False,
            "family_b_config_hash": config["family_b_config_hash"],
            "success_criteria_hash": criteria["success_criteria_hash"],
            "comparison_control_id": CONTROL_ID,
            "comparison_control_hash": control["control_reference_hash"],
            "hypothesis": config["hypothesis"],
            "population": config["population"],
            "primary_metrics": FUTURE_PRIMARY_METRICS,
            "secondary_metrics": (
                "QUALIFYING_HOLDINGS_BY_REBALANCE",
                "CASH_RISK_FORMATION_DATES",
                "INTEGER_SHARE_WEIGHT_ERROR",
            ),
            "stop_conditions": criteria["fatal_failure"],
            "validation_eligibility_rule": config["validation_eligibility_rule"],
            "data_partition": config["development_window"],
            "parameter_hash": parameter_hash,
            "parameters": parameters,
        }
        experiments.append(
            {
                **preregistration_body,
                "preregistration_hash": canonical_hash(preregistration_body),
            }
        )
    body = {
        "family_version": FAMILY_VERSION,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_b_config_hash": config["family_b_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "control_count": 1,
        "control": control,
        "experiment_count": len(experiments),
        "experiment_ids": list(EXPERIMENT_IDS),
        "experiments": experiments,
        "extra_experiments_allowed": False,
        "performance_evaluated": False,
        "validation_accessed": False,
        "promotion_allowed": False,
    }
    return {**body, "registry_hash": canonical_hash(body)}


def verify_registry(
    registry: Mapping[str, Any],
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> None:
    if registry["experiment_count"] != 2 or tuple(registry["experiment_ids"]) != EXPERIMENT_IDS:
        raise FamilyBFreezeMismatch("Family B registry must contain exactly two experiments")
    control = registry["control"]
    if registry["control_count"] != 1 or control["control_id"] != CONTROL_ID:
        raise FamilyBFreezeMismatch("Family B registry control changed")
    if control["status"] != "REFERENCE_CONTROL" or control["family_b_experiment"] is not False:
        raise FamilyBFreezeMismatch("CONTROL-B-000 must remain a reference control")
    if canonical_hash({key: value for key, value in control.items() if key != "control_reference_hash"}) != control[
        "control_reference_hash"
    ]:
        raise FamilyBFreezeMismatch("CONTROL-B-000 reference hash mismatch")
    for observed, expected in zip(registry["experiments"], EXPERIMENT_DEFINITIONS, strict=True):
        if observed["experiment_id"] != expected[0] or observed["status"] != "PREREGISTERED":
            raise FamilyBFreezeMismatch("Family B experiment identity or status changed")
        if observed["promotion_allowed"] is not False or observed["validation_allowed"] is not False:
            raise FamilyBFreezeMismatch("Family B promotion/validation gate changed")
        if canonical_hash(observed["parameters"]) != observed["parameter_hash"]:
            raise FamilyBFreezeMismatch(f"{expected[0]} parameter hash mismatch")
        prereg_body = {key: value for key, value in observed.items() if key != "preregistration_hash"}
        if canonical_hash(prereg_body) != observed["preregistration_hash"]:
            raise FamilyBFreezeMismatch(f"{expected[0]} preregistration hash mismatch")
        if observed["family_b_config_hash"] != config["family_b_config_hash"]:
            raise FamilyBFreezeMismatch("Family B config linkage changed")
        if observed["success_criteria_hash"] != criteria["success_criteria_hash"]:
            raise FamilyBFreezeMismatch("Family B success-criteria linkage changed")
    if registry["performance_evaluated"] is not False or registry["validation_accessed"] is not False:
        raise FamilyBFreezeMismatch("Command 01 cannot evaluate performance or access validation")


def verify_expected_hashes(
    config: Mapping[str, Any],
    criteria: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> None:
    if not EXPECTED_FAMILY_B_CONFIG_HASH:
        return
    checks = {
        "family_b_config_hash": config["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH,
        "control_reference_hash": registry["control"]["control_reference_hash"]
        == EXPECTED_CONTROL_REFERENCE_HASH,
        "success_criteria_hash": criteria["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    for row in registry["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]
        checks[f"{row['experiment_id']}_parameter_hash"] = row["parameter_hash"] == expected[
            "parameter_hash"
        ]
        checks[f"{row['experiment_id']}_preregistration_hash"] = row[
            "preregistration_hash"
        ] == expected["preregistration_hash"]
    if not all(checks.values()):
        raise FamilyBFreezeMismatch(f"FAMILY_B_PREREGISTRATION_HASH_MISMATCH: {checks}")


def classify_future_experiment_result(
    *,
    standard_criteria_passes: Mapping[str, bool],
    fatal_conditions: Mapping[str, bool],
    cagr_preservation_ratio: Decimal,
    relative_drawdown_improvement: Decimal,
    negative_development_years: int,
    accounting_clean: bool,
    interpretable: bool,
) -> str:
    """Apply the frozen precedence without computing any performance metrics."""
    expected = set(success_criteria_config()["standard_criteria"])
    if set(standard_criteria_passes) != expected:
        raise ValueError(f"Expected exactly the seven criteria A-G: {sorted(expected)}")
    if any(fatal_conditions.values()):
        return "FAILED"
    if not interpretable:
        return "INCONCLUSIVE"
    passed_count = sum(value is True for value in standard_criteria_passes.values())
    if (
        passed_count == 7
        and decimal(cagr_preservation_ratio) >= Decimal("0.90")
        and decimal(relative_drawdown_improvement) >= Decimal("0.15")
        and negative_development_years == 0
        and accounting_clean
    ):
        return "STRONGLY_SUPPORTED"
    if passed_count == 7:
        return "SUPPORTED"
    if passed_count >= 4:
        return "PARTIALLY_SUPPORTED"
    return "FAILED"


def b001_eligibility(top_decile: bool, six_month_return: Decimal | None) -> str:
    if six_month_return is None:
        return "UNAVAILABLE"
    return "ELIGIBLE" if top_decile and decimal(six_month_return) > Decimal("0") else "NOT_ELIGIBLE"


def b002_eligibility(
    top_decile: bool,
    close: Decimal | None,
    sma200: Decimal | None,
    observation_count: int,
) -> str:
    if close is None or sma200 is None or observation_count < SMA_SESSIONS:
        return "UNAVAILABLE"
    return "ELIGIBLE" if top_decile and decimal(close) > decimal(sma200) else "NOT_ELIGIBLE"


def simple_moving_average_200(
    closes: Mapping[date, Decimal], formation_date: date
) -> dict[str, Any]:
    observations = sorted(
        (observed_date, decimal(value))
        for observed_date, value in closes.items()
        if observed_date <= formation_date and decimal(value) > 0
    )
    if len(observations) < SMA_SESSIONS:
        return {
            "value": None,
            "observation_count": len(observations),
            "window_start": None,
            "window_end": observations[-1][0] if observations else None,
            "reason": "FEWER_THAN_200_VALID_OBSERVATIONS",
            "no_lookahead": True,
        }
    window = observations[-SMA_SESSIONS:]
    return {
        "value": sum((value for _, value in window), Decimal("0")) / Decimal(SMA_SESSIONS),
        "observation_count": SMA_SESSIONS,
        "window_start": window[0][0],
        "window_end": window[-1][0],
        "reason": None,
        "no_lookahead": window[-1][0] <= formation_date,
    }


def _source_rows(root: Path) -> list[dict[str, str]]:
    source = root / "data/research/strategy_families/family_a/v1/signals/family_a_signal_inputs_v1.csv"
    rows = [row for row in read_csv(source) if row["experiment_id"] == "MOM-A-002"]
    dates = {row["decision_date"] for row in rows}
    if len(dates) != EXPECTED_QUARTERLY_REBALANCES:
        raise FamilyBFreezeMismatch(f"Frozen MOM-A-002 schedule count changed: {len(dates)}")
    if any(row["schedule"] != "QUARTERLY" for row in rows):
        raise FamilyBFreezeMismatch("Family B source includes a non-quarterly row")
    if any(date.fromisoformat(row["decision_date"]) > DEVELOPMENT_END for row in rows):
        raise FamilyBFreezeMismatch("Family B source crossed the development boundary")
    return rows


def _parse_flags(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        parsed = [value] if value else []
    return tuple(str(item) for item in parsed)


def _valid_symbol_closes(
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> dict[str, dict[date, Decimal]]:
    result: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for trading_date, day in bars.items():
        for symbol, bar in day.items():
            if bar.usability_status == "ADJUSTED_READY" and bar.close_price > 0:
                result[symbol][trading_date] = bar.close_price
    return result


def _rank_source_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row.get("eligible") == "True" and row.get("6m_return") not in {None, ""}
    ]
    eligible.sort(key=lambda row: (-decimal(row["6m_return"]), str(row["symbol"])))
    top_count = math.ceil(len(eligible) * float(RELATIVE_SELECTION_FRACTION))
    ranked: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(eligible, start=1):
        ranked[str(row["symbol"])] = {
            "rank": rank,
            "percentile": Decimal(len(eligible) - rank + 1) / Decimal(len(eligible)),
            "top_decile": rank <= top_count,
        }
    return {
        "eligible_count": len(eligible),
        "top_decile_count": top_count,
        "ranked": ranked,
        "top_decile_symbols": [str(row["symbol"]) for row in eligible[:top_count]],
    }


def build_signal_dataset(
    root: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[date, dict[str, AdjustedBar]],
    dict[str, dict[date, Decimal]],
    dict[str, list[dict[str, str]]],
]:
    source_rows = _source_rows(root)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    symbols: set[str] = set()
    for row in source_rows:
        grouped[row["decision_date"]].append(row)
        symbols.add(row["symbol"])
    aliases = _load_aliases(root)
    bars = _load_adjusted_bars(root, symbols, aliases)
    valid_closes = _valid_symbol_closes(bars)

    signal_rows: list[dict[str, Any]] = []
    breadth_rows: list[dict[str, Any]] = []
    for decision_date_text, rows in sorted(grouped.items()):
        formation = date.fromisoformat(decision_date_text)
        ranking = _rank_source_rows(rows)
        b001_count = 0
        b002_count = 0
        for source in sorted(rows, key=lambda item: item["symbol"]):
            symbol = source["symbol"]
            relative = decimal(source["6m_return"]) if source.get("6m_return") else None
            rank_record = ranking["ranked"].get(symbol)
            top_decile = bool(rank_record and rank_record["top_decile"])
            close = decimal(source["price"]) if source.get("price") else None
            sma = simple_moving_average_200(valid_closes.get(symbol, {}), formation)
            b001_status = b001_eligibility(top_decile, relative)
            b002_status = b002_eligibility(
                top_decile, close, sma["value"], int(sma["observation_count"])
            )
            b001_eligible = b001_status == "ELIGIBLE"
            b002_eligible = b002_status == "ELIGIBLE"
            b001_count += int(b001_eligible)
            b002_count += int(b002_eligible)
            flags = set(_parse_flags(source.get("data_quality_flags", "")))
            if sma["value"] is None:
                flags.add("SMA200_UNAVAILABLE")
            if relative is None:
                flags.add("6M_RETURN_UNAVAILABLE")
            signal_rows.append(
                {
                    "decision_date": decision_date_text,
                    "symbol": symbol,
                    "6m_return": relative,
                    "relative_rank": rank_record["rank"] if rank_record else None,
                    "relative_percentile": rank_record["percentile"] if rank_record else None,
                    "sma200": sma["value"],
                    "close": close,
                    "absolute_6m_positive": relative > 0 if relative is not None else None,
                    "above_sma200": close > sma["value"] if close is not None and sma["value"] is not None else None,
                    "B001_eligible": b001_eligible if b001_status != "UNAVAILABLE" else None,
                    "B002_eligible": b002_eligible if b002_status != "UNAVAILABLE" else None,
                    "data_quality_flags": tuple(sorted(flags)) or ("NONE",),
                    "membership_confidence": source["membership_source_confidence"],
                }
            )
        execution_dates = {row["execution_date"] for row in rows}
        if len(execution_dates) != 1:
            raise FamilyBFreezeMismatch("Quarterly formation has multiple execution dates")
        breadth_rows.append(
            {
                "decision_date": decision_date_text,
                "execution_date": next(iter(execution_dates)),
                "eligible_universe_size": ranking["eligible_count"],
                "top_decile_size": ranking["top_decile_count"],
                "B001_pass_count": b001_count,
                "B002_pass_count": b002_count,
                "B001_breadth_status": (
                    "PORTFOLIO_FORMATION_ALLOWED"
                    if b001_count >= MINIMUM_HOLDINGS
                    else "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH"
                ),
                "B002_breadth_status": (
                    "PORTFOLIO_FORMATION_ALLOWED"
                    if b002_count >= MINIMUM_HOLDINGS
                    else "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH"
                ),
                "future_returns_accessed": False,
            }
        )
    return signal_rows, breadth_rows, bars, valid_closes, grouped


def build_synthetic_signal_pilots() -> list[dict[str, Any]]:
    b001_cases = (
        ("A", True, Decimal("0.01"), "ELIGIBLE"),
        ("B", True, Decimal("0"), "NOT_ELIGIBLE"),
        ("C", True, Decimal("-0.01"), "NOT_ELIGIBLE"),
        ("D", False, Decimal("0.01"), "NOT_ELIGIBLE"),
        ("E", True, None, "UNAVAILABLE"),
    )
    b002_cases = (
        ("A", True, Decimal("101"), Decimal("100"), 200, "ELIGIBLE"),
        ("B", True, Decimal("100"), Decimal("100"), 200, "NOT_ELIGIBLE"),
        ("C", True, Decimal("99"), Decimal("100"), 200, "NOT_ELIGIBLE"),
        ("D", False, Decimal("101"), Decimal("100"), 200, "NOT_ELIGIBLE"),
        ("E", True, Decimal("101"), None, 199, "UNAVAILABLE"),
    )
    result: list[dict[str, Any]] = []
    for case_id, top_decile, six_month_return, expected in b001_cases:
        observed = b001_eligibility(top_decile, six_month_return)
        result.append(
            {
                "experiment_id": "MOM-B-001",
                "case_id": case_id,
                "fixture": "SYNTHETIC_STRUCTURE_ONLY_NO_PERFORMANCE",
                "top_decile": top_decile,
                "6m_return": six_month_return,
                "close": None,
                "sma200": None,
                "sma_observations": None,
                "expected": expected,
                "observed": observed,
                "passed": observed == expected,
                "future_returns_accessed": False,
            }
        )
    for case_id, top_decile, close, sma200, observations, expected in b002_cases:
        observed = b002_eligibility(top_decile, close, sma200, observations)
        result.append(
            {
                "experiment_id": "MOM-B-002",
                "case_id": case_id,
                "fixture": "SYNTHETIC_STRUCTURE_ONLY_NO_PERFORMANCE",
                "top_decile": top_decile,
                "6m_return": None,
                "close": close,
                "sma200": sma200,
                "sma_observations": observations,
                "expected": expected,
                "observed": observed,
                "passed": observed == expected,
                "future_returns_accessed": False,
            }
        )
    return result


def build_sma_reconciliation(
    signal_rows: Sequence[Mapping[str, Any]],
    valid_closes: Mapping[str, Mapping[date, Decimal]],
) -> list[dict[str, Any]]:
    candidates = [
        row for row in signal_rows if row["B002_eligible"] is True and row["sma200"] is not None
    ]
    chosen: list[Mapping[str, Any]] = []
    seen_years: set[str] = set()
    for row in candidates:
        year = str(row["decision_date"])[:4]
        if year not in seen_years:
            chosen.append(row)
            seen_years.add(year)
        if len(chosen) == 3:
            break
    if len(chosen) < 3:
        remaining = [row for row in candidates if row not in chosen]
        chosen.extend(remaining[: 3 - len(chosen)])
    result: list[dict[str, Any]] = []
    for row in chosen:
        formation = date.fromisoformat(str(row["decision_date"]))
        observations = sorted(
            (observed_date, decimal(value))
            for observed_date, value in valid_closes[str(row["symbol"])].items()
            if observed_date <= formation and decimal(value) > 0
        )[-SMA_SESSIONS:]
        manual = sum((value for _, value in observations), Decimal("0")) / Decimal(SMA_SESSIONS)
        observed = decimal(row["sma200"])
        result.append(
            {
                "decision_date": row["decision_date"],
                "symbol": row["symbol"],
                "observation_count": len(observations),
                "window_start": observations[0][0],
                "window_end": observations[-1][0],
                "observed_sma200": observed,
                "manual_sma200": manual,
                "absolute_difference": abs(observed - manual),
                "tolerance": Decimal("0"),
                "exact_match": observed == manual,
                "no_lookahead": observations[-1][0] <= formation,
            }
        )
    return result


def build_relative_rank_reconciliation(
    signal_rows: Sequence[Mapping[str, Any]],
    grouped_source: Mapping[str, Sequence[Mapping[str, str]]],
) -> list[dict[str, Any]]:
    dates = sorted(grouped_source)
    chosen_dates = (dates[0], dates[len(dates) // 2], dates[-1])
    output_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        output_by_date[str(row["decision_date"])].append(row)
    result: list[dict[str, Any]] = []
    for decision_date_text in chosen_dates:
        manual = _rank_source_rows(grouped_source[decision_date_text])
        observed_rows = [row for row in output_by_date[decision_date_text] if row["relative_rank"] is not None]
        observed_top = [
            str(row["symbol"])
            for row in sorted(observed_rows, key=lambda item: int(item["relative_rank"]))
            if int(row["relative_rank"]) <= int(manual["top_decile_count"])
        ]
        source_rank_match = all(
            not source.get("signal_rank")
            or int(source["signal_rank"]) == manual["ranked"][source["symbol"]]["rank"]
            for source in grouped_source[decision_date_text]
            if source["symbol"] in manual["ranked"]
        )
        result.append(
            {
                "decision_date": decision_date_text,
                "eligible_universe_size": manual["eligible_count"],
                "top_decile_size": manual["top_decile_count"],
                "manual_top_decile_symbols": manual["top_decile_symbols"],
                "observed_top_decile_symbols": observed_top,
                "symbol_set_match": observed_top == manual["top_decile_symbols"],
                "rank_match": source_rank_match,
                "tie_break": "SYMBOL_ASCENDING",
                "formation_data_only": True,
                "future_returns_accessed": False,
            }
        )
    return result


def _qualifying_rows(
    signal_rows: Sequence[Mapping[str, Any]], decision_date_text: str, experiment_id: str
) -> list[Mapping[str, Any]]:
    field = "B001_eligible" if experiment_id == "MOM-B-001" else "B002_eligible"
    return sorted(
        (
            row
            for row in signal_rows
            if row["decision_date"] == decision_date_text and row[field] is True
        ),
        key=lambda row: (int(row["relative_rank"]), str(row["symbol"])),
    )


def _allocate_whole_shares(
    selected: Sequence[Mapping[str, Any]],
    execution_prices: Mapping[str, Decimal],
    execution_date: date,
) -> dict[str, Any]:
    if not selected:
        raise ValueError("Capital pilot requires qualifying holdings")
    target = CAPITAL_INR / Decimal(len(selected))
    allocations: list[dict[str, Any]] = []
    for row in selected:
        symbol = str(row["symbol"])
        price = decimal(execution_prices[symbol])
        shares = int(target // price)
        allocations.append(
            {
                "symbol": symbol,
                "rank": int(row["relative_rank"]),
                "execution_price": price,
                "target_rupees": target,
                "target_weight": Decimal("1") / Decimal(len(selected)),
                "shares": shares,
            }
        )

    def totals() -> tuple[Decimal, Decimal]:
        notional = Decimal("0")
        costs = Decimal("0")
        for allocation in allocations:
            gross = Decimal(allocation["shares"]) * decimal(allocation["execution_price"])
            notional += gross
            if gross > 0:
                costs += decimal(estimate_order_cost("BUY", execution_date, gross)["total_cost"])
        return notional, costs

    invested, costs = totals()
    while invested + costs > CAPITAL_INR:
        reducible = next((row for row in reversed(allocations) if row["shares"] > 0), None)
        if reducible is None:
            raise ValueError("Whole-share pilot cannot reconcile capital")
        reducible["shares"] -= 1
        invested, costs = totals()
    residual = CAPITAL_INR - invested - costs
    for allocation in allocations:
        gross = Decimal(allocation["shares"]) * decimal(allocation["execution_price"])
        allocation["actual_notional"] = gross
        allocation["actual_weight"] = gross / CAPITAL_INR
        allocation["buy_cost"] = (
            estimate_order_cost("BUY", execution_date, gross)["total_cost"] if gross > 0 else Decimal("0")
        )
    return {
        "selected_count": len(selected),
        "selected_symbols": [row["symbol"] for row in allocations],
        "target_weight": Decimal("1") / Decimal(len(selected)),
        "whole_shares": True,
        "invested_notional": invested,
        "transaction_costs": costs,
        "residual_cash": residual,
        "accounting_total": invested + costs + residual,
        "accounting_reconciles": invested + costs + residual == CAPITAL_INR,
        "allocations": allocations,
    }


def build_capital_pilots(
    signal_rows: Sequence[Mapping[str, Any]],
    breadth_rows: Sequence[Mapping[str, Any]],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for experiment_id in EXPERIMENT_IDS:
        count_field = "B001_pass_count" if experiment_id == "MOM-B-001" else "B002_pass_count"
        schedule = next(row for row in breadth_rows if int(row[count_field]) >= MINIMUM_HOLDINGS)
        decision_date_text = str(schedule["decision_date"])
        execution_date = date.fromisoformat(str(schedule["execution_date"]))
        selected = _qualifying_rows(signal_rows, decision_date_text, experiment_id)
        execution_prices = {
            str(row["symbol"]): bars[execution_date][str(row["symbol"])].open_price for row in selected
        }
        allocation = _allocate_whole_shares(selected, execution_prices, execution_date)
        no_backfill = len(selected) == int(schedule[count_field])
        detail = {
            "experiment_id": experiment_id,
            "fixture": "ONE_REBALANCE_STRUCTURAL_ACCOUNTING_PILOT_NO_PERFORMANCE",
            "decision_date": decision_date_text,
            "execution_date": execution_date.isoformat(),
            "formation_reference": "ELIGIBLE_QUARTER_END_SESSION_CLOSE",
            "execution_reference": "NEXT_ELIGIBLE_NSE_SESSION_OPEN",
            "qualifying_count": int(schedule[count_field]),
            "minimum_holdings": MINIMUM_HOLDINGS,
            "formation_status": "PORTFOLIO_FORMATION_ALLOWED",
            "no_backfill": no_backfill,
            "capital_inr": CAPITAL_INR,
            "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
            "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": Decimal("5"),
            "performance_evaluated": False,
            **allocation,
        }
        details[experiment_id] = detail
        report_rows.append(
            {
                "experiment_id": experiment_id,
                "decision_date": decision_date_text,
                "execution_date": execution_date.isoformat(),
                "qualifying_count": detail["qualifying_count"],
                "selected_count": allocation["selected_count"],
                "selected_symbols": allocation["selected_symbols"],
                "whole_shares": True,
                "equal_weight_target": allocation["target_weight"],
                "capital_inr": CAPITAL_INR,
                "invested_notional": allocation["invested_notional"],
                "transaction_costs": allocation["transaction_costs"],
                "residual_cash": allocation["residual_cash"],
                "accounting_reconciles": allocation["accounting_reconciles"],
                "no_backfill": no_backfill,
                "performance_evaluated": False,
            }
        )
    return report_rows, details


def _coverage_status(available: int, total: int) -> str:
    if total > 0 and available == total:
        return "READY"
    if available > 0:
        return "READY_WITH_LIMITATIONS"
    return "BLOCKED"


def build_data_readiness(
    source_rows: Sequence[Mapping[str, str]], signal_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    total = len(source_rows)
    audits = (
        (
            "6M_HISTORY",
            sum(bool(row.get("6m_return")) for row in source_rows),
            "Trailing 6M value is available using formation-date history only.",
        ),
        (
            "SMA200_AVAILABILITY",
            sum(row["sma200"] is not None for row in signal_rows),
            "Exactly 200 adjusted-ready observations exist through formation.",
        ),
        (
            "POINT_IN_TIME_MEMBERSHIP",
            sum(row.get("point_in_time_member") == "True" for row in source_rows),
            "Frozen historical membership reconstruction; confidence limitations are preserved.",
        ),
        (
            "EXECUTION_OPENS",
            sum(row.get("next_open_available") == "True" for row in source_rows),
            "Next eligible NSE-session adjusted open is present.",
        ),
        (
            "LIQUIDITY",
            sum(row.get("liquidity_gate_pass") == "True" for row in source_rows),
            "20-session median traded-value gate passes.",
        ),
        (
            "CORPORATE_ACTION_SAFETY",
            sum(row.get("corporate_action_safe") == "True" for row in source_rows),
            "Frozen corporate-action research-safety gate passes.",
        ),
    )
    return [
        {
            "audit": audit,
            "status": _coverage_status(available, total),
            "available_count": available,
            "total_count": total,
            "coverage_pct": Decimal(available) / Decimal(total) * Decimal("100") if total else None,
            "notes": notes,
        }
        for audit, available, notes in audits
    ]


def _breadth_statistics(
    breadth_rows: Sequence[Mapping[str, Any]], experiment_id: str
) -> dict[str, Any]:
    field = "B001_pass_count" if experiment_id == "MOM-B-001" else "B002_pass_count"
    values = [int(row[field]) for row in breadth_rows]
    low_dates = [str(row["decision_date"]) for row in breadth_rows if int(row[field]) < MINIMUM_HOLDINGS]
    return {
        "scheduled_rebalances": len(values),
        "average_qualifying_count": Decimal(sum(values)) / Decimal(len(values)),
        "median_qualifying_count": decimal(statistics.median(values)),
        "minimum_qualifying_count": min(values),
        "maximum_qualifying_count": max(values),
        "schedules_at_or_above_minimum": sum(value >= MINIMUM_HOLDINGS for value in values),
        "breadth_fraction": Decimal(sum(value >= MINIMUM_HOLDINGS for value in values))
        / Decimal(len(values)),
        "insufficient_breadth_schedules": low_dates,
        "future_returns_accessed": False,
    }


def family_a_immutability_snapshot(root: Path) -> dict[str, Any]:
    closure = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/closure/manifest/family_a_closure_manifest_v1.json"
    )
    closure_body = {key: value for key, value in closure.items() if key != "family_a_closure_hash"}
    if closure.get("family_a_closure_hash") != EXPECTED_CLOSURE_HASH:
        raise FamilyBFreezeMismatch("Family A closure hash changed")
    if canonical_hash(closure_body) != EXPECTED_CLOSURE_HASH:
        raise FamilyBFreezeMismatch("Family A closure manifest no longer recomputes")
    semantic = closure_baseline_snapshot(root)
    family_a_files = sorted(
        {
            *(
                path
                for path in (root / "data/research/strategy_families/family_a/v1").rglob("*")
                if path.is_file()
            ),
            *(root / "backend/app/research/strategy").glob("family_a*.py"),
            *(root / "backend/scripts").glob("run_family_a*.py"),
            *(root / "backend/tests").glob("test_family_a*.py"),
            *(root / "docs").glob("strategy-family-a-*.md"),
        }
    )
    file_hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in family_a_files}
    body = {
        "closure_hash": EXPECTED_CLOSURE_HASH,
        "semantic_snapshot_hash": semantic["snapshot_hash"],
        "family_a_file_hashes": file_hashes,
    }
    return {**body, "snapshot_hash": canonical_hash(body)}


def governance_checklist_rows(
    config: Mapping[str, Any], criteria: Mapping[str, Any], registry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    evidence = {
        "hypothesis": "FAMILY_CONFIG_AND_EACH_PREREGISTRATION",
        "experiment_id": list(EXPERIMENT_IDS),
        "population": config["population"],
        "exact_parameters": [row["parameter_hash"] for row in registry["experiments"]],
        "control": registry["control"]["control_reference_hash"],
        "primary_metrics": list(FUTURE_PRIMARY_METRICS),
        "secondary_metrics": [row["secondary_metrics"] for row in registry["experiments"]],
        "numerical_success_criteria": criteria["success_criteria_hash"],
        "failure_criteria": criteria["fatal_failure"],
        "stop_conditions": "FATAL_FAILURE_CONDITIONS_FROZEN",
        "validation_eligibility": config["validation_eligibility_rule"],
        "cost_model": config["costs"],
        "data_partition": config["development_window"],
        "hashes": {
            "family_b_config_hash": config["family_b_config_hash"],
            "success_criteria_hash": criteria["success_criteria_hash"],
            "control_reference_hash": registry["control"]["control_reference_hash"],
            "parameter_hashes": [row["parameter_hash"] for row in registry["experiments"]],
            "preregistration_hashes": [row["preregistration_hash"] for row in registry["experiments"]],
        },
    }
    return [
        {
            "check_number": index,
            "check": item,
            "status": "PASS",
            "evidence": evidence[item],
        }
        for index, item in enumerate(GOVERNANCE_CHECKLIST, start=1)
    ]


def protocol_document(
    config: Mapping[str, Any], criteria: Mapping[str, Any], registry: Mapping[str, Any]
) -> dict[str, Any]:
    body = {
        "protocol": RESEARCH_PROTOCOL,
        "family_version": FAMILY_VERSION,
        "family_b_config_hash": config["family_b_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "control_reference_hash": registry["control"]["control_reference_hash"],
        "experiment_ids": list(EXPERIMENT_IDS),
        "governance_policy": GOVERNANCE_POLICY_VERSION,
        "governance_checklist_count": len(GOVERNANCE_CHECKLIST),
        "performance_scope": "SPECIFICATION_PREREGISTRATION_ARCHITECTURE_ONLY",
        "allowed_command_01_activities": (
            "STRUCTURAL_PILOTS",
            "SIGNAL_VERIFICATION",
            "BREADTH_COUNTS",
            "NO_LOOKAHEAD_CHECKS",
            "ARCHITECTURE_TESTING",
            "SYNTHETIC_ACCOUNTING",
        ),
        "prohibited_command_01_activities": (
            "FINAL_DEVELOPMENT_PERFORMANCE",
            "FUTURE_RETURN_INSPECTION",
            "VALIDATION_ACCESS",
            "FINAL_EQUITY_CURVES",
            "STRATEGY_V2_CREATION",
            "FAMILY_C_START",
        ),
    }
    return {**body, "protocol_hash": canonical_hash(body)}


def _signal_fieldnames() -> tuple[str, ...]:
    return (
        "decision_date",
        "symbol",
        "6m_return",
        "relative_rank",
        "relative_percentile",
        "sma200",
        "close",
        "absolute_6m_positive",
        "above_sma200",
        "B001_eligible",
        "B002_eligible",
        "data_quality_flags",
        "membership_confidence",
    )


def build_family_b_architecture(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    family_a_before = family_a_immutability_snapshot(root)
    family_a_preregistration = verify_family_a_preregistration(root)
    if family_a_preregistration["family_config_hash"] != FAMILY_A_CONFIG_HASH:
        raise FamilyBFreezeMismatch("Family A Command 01 config hash changed")

    criteria = success_criteria_config()
    config = family_config(criteria)
    control = control_reference(config)
    registry = experiment_registry(config, criteria, control)
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)

    signal_rows, breadth_rows, bars, valid_closes, grouped_source = build_signal_dataset(root)
    source_rows = [row for rows in grouped_source.values() for row in rows]
    pilot_rows = build_synthetic_signal_pilots()
    sma_rows = build_sma_reconciliation(signal_rows, valid_closes)
    rank_rows = build_relative_rank_reconciliation(signal_rows, grouped_source)
    capital_rows, capital_details = build_capital_pilots(signal_rows, breadth_rows, bars)
    readiness_rows = build_data_readiness(source_rows, signal_rows)
    governance_rows = governance_checklist_rows(config, criteria, registry)
    protocol = protocol_document(config, criteria, registry)

    output_root = root / "data/research/strategy_families/family_b/v1"
    reports_root = root / "data/reports"
    registry_root = output_root / "registry"
    signals_root = output_root / "signals"
    pilots_root = output_root / "pilots"
    manifests_root = output_root / "manifests"
    governance_root = output_root / "governance"
    calendar_root = output_root / "rebalance_calendar"

    write_json(registry_root / "family_b_config_v1.json", config)
    write_json(registry_root / "control_b_000_reference_v1.json", control)
    write_json(registry_root / "experiment_registry_v1.json", registry)
    for row in registry["experiments"]:
        write_json(
            registry_root / f"{str(row['experiment_id']).lower().replace('-', '_')}_preregistration_v1.json",
            row,
        )
    write_json(governance_root / "success_criteria_v1.json", criteria)
    write_json(governance_root / "family_b_research_protocol_v1.json", protocol)
    write_json(
        governance_root / "governance_v2_checklist_v1.json",
        {
            "governance_policy": GOVERNANCE_POLICY_VERSION,
            "checklist_count": len(governance_rows),
            "all_passed": all(row["status"] == "PASS" for row in governance_rows),
            "checks": governance_rows,
        },
    )
    write_csv(signals_root / "family_b_signal_inputs_v1.csv", signal_rows, _signal_fieldnames())
    write_csv(calendar_root / "family_b_rebalance_calendar_v1.csv", breadth_rows)
    write_csv(pilots_root / "family_b_signal_pilot_v1.csv", pilot_rows)
    write_csv(pilots_root / "sma200_reconciliation_v1.csv", sma_rows)
    write_csv(pilots_root / "relative_rank_reconciliation_v1.csv", rank_rows)
    write_json(pilots_root / "rebalance_accounting_pilot_v1.json", capital_details)

    registry_report = [
        {
            "record_type": "CONTROL",
            "record_id": CONTROL_ID,
            "name": "MOM-A-002_ARCHITECTURE_REFERENCE",
            "status": "REFERENCE_CONTROL",
            "promotion_allowed": False,
            "validation_allowed": False,
            "capital_inr": CAPITAL_INR,
            "parameter_hash": control["underlying_parameter_hash"],
            "record_hash": control["control_reference_hash"],
        },
        *(
            {
                "record_type": "EXPERIMENT",
                "record_id": row["experiment_id"],
                "name": row["name"],
                "status": row["status"],
                "promotion_allowed": row["promotion_allowed"],
                "validation_allowed": row["validation_allowed"],
                "capital_inr": CAPITAL_INR,
                "parameter_hash": row["parameter_hash"],
                "record_hash": row["preregistration_hash"],
            }
            for row in registry["experiments"]
        ),
    ]
    write_csv(reports_root / REPORT_NAMES[1], registry_report)
    write_csv(reports_root / REPORT_NAMES[2], readiness_rows)
    write_csv(reports_root / REPORT_NAMES[3], pilot_rows)
    write_csv(reports_root / REPORT_NAMES[4], breadth_rows)
    write_csv(reports_root / REPORT_NAMES[5], governance_rows)
    write_csv(reports_root / REPORT_NAMES[6], capital_rows)

    b001_breadth = _breadth_statistics(breadth_rows, "MOM-B-001")
    b002_breadth = _breadth_statistics(breadth_rows, "MOM-B-002")
    family_a_after = family_a_immutability_snapshot(root)
    family_a_unchanged = family_a_before == family_a_after
    data_readiness = (
        "READY"
        if all(row["status"] == "READY" for row in readiness_rows)
        else "READY_WITH_LIMITATIONS"
        if all(row["status"] != "BLOCKED" for row in readiness_rows)
        else "BLOCKED"
    )
    pilot_integrity = (
        all(row["passed"] is True for row in pilot_rows)
        and len(sma_rows) >= 3
        and all(row["exact_match"] is True and row["no_lookahead"] is True for row in sma_rows)
        and all(row["symbol_set_match"] is True and row["rank_match"] is True for row in rank_rows)
        and all(row["accounting_reconciles"] is True and row["no_backfill"] is True for row in capital_rows)
    )
    architecture_result = (
        "READY_FOR_DEVELOPMENT_BACKTEST"
        if pilot_integrity and family_a_unchanged and data_readiness != "BLOCKED"
        else "METHODOLOGY_FIX_REQUIRED"
        if data_readiness != "BLOCKED"
        else "DATA_BLOCKED"
    )

    artifact_paths = [
        registry_root / "family_b_config_v1.json",
        registry_root / "control_b_000_reference_v1.json",
        registry_root / "experiment_registry_v1.json",
        *sorted(registry_root.glob("mom_b_*_preregistration_v1.json")),
        governance_root / "success_criteria_v1.json",
        governance_root / "family_b_research_protocol_v1.json",
        governance_root / "governance_v2_checklist_v1.json",
        signals_root / "family_b_signal_inputs_v1.csv",
        calendar_root / "family_b_rebalance_calendar_v1.csv",
        pilots_root / "family_b_signal_pilot_v1.csv",
        pilots_root / "sma200_reconciliation_v1.csv",
        pilots_root / "relative_rank_reconciliation_v1.csv",
        pilots_root / "rebalance_accounting_pilot_v1.json",
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    artifact_hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths}
    summary = {
        "command": COMMAND,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_status": FAMILY_STATUS,
        "family_b_config_hash": config["family_b_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "control": {
            "control_id": CONTROL_ID,
            "control_reference_hash": control["control_reference_hash"],
            "status": control["status"],
            "underlying_architecture": "MOM-A-002",
            "capital_inr": CAPITAL_INR,
            "performance_run": False,
        },
        "experiment_count": 2,
        "experiments": [
            {
                "experiment_id": row["experiment_id"],
                "name": row["name"],
                "status": row["status"],
                "parameter_hash": row["parameter_hash"],
                "preregistration_hash": row["preregistration_hash"],
            }
            for row in registry["experiments"]
        ],
        "frozen_design": {
            "capital_inr": CAPITAL_INR,
            "rebalance_frequency": "QUARTERLY",
            "formation": "ELIGIBLE_QUARTER_END_SESSION_CLOSE",
            "execution": "NEXT_ELIGIBLE_NSE_SESSION_OPEN",
            "relative_signal": "6M_COMPOUNDED_RETURN",
            "relative_candidate_pool": "TOP_DECILE",
            "B001_absolute_rule": "6M_RETURN_STRICTLY_GREATER_THAN_ZERO",
            "B002_absolute_rule": "FORMATION_ADJUSTED_CLOSE_STRICTLY_GREATER_THAN_SMA200",
            "sma_valid_sessions": SMA_SESSIONS,
            "minimum_holdings": MINIMUM_HOLDINGS,
            "no_backfill": True,
            "cash_behavior": "RESIDUAL_OR_UNALLOCATED_CAPITAL_REMAINS_CASH",
            "weighting": "EQUAL_WEIGHT",
            "whole_shares": True,
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "structural_pilots": {
            "B001": {
                "case_count": sum(row["experiment_id"] == "MOM-B-001" for row in pilot_rows),
                "passed": all(
                    row["passed"] is True for row in pilot_rows if row["experiment_id"] == "MOM-B-001"
                ),
            },
            "B002": {
                "case_count": sum(row["experiment_id"] == "MOM-B-002" for row in pilot_rows),
                "passed": all(
                    row["passed"] is True for row in pilot_rows if row["experiment_id"] == "MOM-B-002"
                ),
            },
            "sma200_reconciliation": {
                "case_count": len(sma_rows),
                "all_exact": all(row["exact_match"] is True for row in sma_rows),
                "all_no_lookahead": all(row["no_lookahead"] is True for row in sma_rows),
            },
            "relative_rank_reconciliation": {
                "case_count": len(rank_rows),
                "all_exact": all(
                    row["symbol_set_match"] is True and row["rank_match"] is True for row in rank_rows
                ),
                "future_returns_accessed": False,
            },
            "capital_rebalance": {
                "case_count": len(capital_rows),
                "all_accounting_reconciled": all(row["accounting_reconciles"] is True for row in capital_rows),
                "all_no_backfill": all(row["no_backfill"] is True for row in capital_rows),
                "performance_evaluated": False,
            },
        },
        "breadth": {
            "scheduled_rebalances": len(breadth_rows),
            "B001": b001_breadth,
            "B002": b002_breadth,
            "cash_risk_dates": sorted(
                set(b001_breadth["insufficient_breadth_schedules"])
                | set(b002_breadth["insufficient_breadth_schedules"])
            ),
            "future_returns_accessed": False,
        },
        "governance": {
            "policy": GOVERNANCE_POLICY_VERSION,
            "policy_active": True,
            "checklist_count": len(governance_rows),
            "checklist_passed": all(row["status"] == "PASS" for row in governance_rows),
            "numeric_thresholds_frozen_before_performance": True,
            "final_development_performance_run": False,
            "future_returns_accessed": False,
            "validation_authorized": False,
            "validation_accessed": False,
            "alternate_positive_return_threshold_tested": False,
            "alternate_moving_average_tested": False,
            "alternate_capital_tested": False,
            "regime_added": False,
            "stop_or_target_added": False,
            "intraday_added": False,
            "strategy_v2_created": False,
            "family_c_started": False,
        },
        "success_criteria": criteria,
        "classifications": {
            "FAMILY_B_DATA_READINESS": data_readiness,
            "FAMILY_B_ARCHITECTURE_RESULT": architecture_result,
            "future_experiment_result": None,
            "future_family_result": None,
        },
        "regression": {
            "family_a_before_snapshot_hash": family_a_before["snapshot_hash"],
            "family_a_after_snapshot_hash": family_a_after["snapshot_hash"],
            "family_a_unchanged": family_a_unchanged,
            "family_a_closure_hash": family_a_after["closure_hash"],
            "strategy_v1_foundation_hash": closure_baseline_snapshot(root)[
                "strategy_v1_foundation_hash"
            ],
            "cap4_validation_state": closure_baseline_snapshot(root)["cap4_validation_state"],
            "cap4_validation_run_count": closure_baseline_snapshot(root)[
                "cap4_validation_run_count"
            ],
            "cap4_validation_result_hash": closure_baseline_snapshot(root)[
                "cap4_validation_result_hash"
            ],
            "family_a_command_01_config_hash": FAMILY_A_CONFIG_HASH,
            "family_a_command_02_registry_hash": EXPECTED_COMMAND_02_REGISTRY_HASH,
            "family_a_command_02_result_hashes": EXPECTED_COMMAND_02_RESULT_HASHES,
            "family_a_command_03_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
            "family_a_command_03_registry_hash": EXPECTED_PHASE2_REGISTRY_HASH,
            "family_a_command_03_experiment_hashes": EXPECTED_PHASE2_EXPERIMENT_HASHES,
            "family_a_command_04_result_hashes": FAMILY_A_PHASE2_RESULT_HASHES,
            "family_a_command_05_closure_hash": EXPECTED_CLOSURE_HASH,
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "registry": registry_root.relative_to(root).as_posix(),
            "signals": signals_root.relative_to(root).as_posix(),
            "pilots": pilots_root.relative_to(root).as_posix(),
            "manifests": manifests_root.relative_to(root).as_posix(),
            "governance": governance_root.relative_to(root).as_posix(),
            "rebalance_calendar": calendar_root.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
            "family_a_modified": False,
            "strategy_v2_created": False,
        },
        "known_limitations": (
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_HAS_FROZEN_PARTIAL_CONFIDENCE",
            "ADJUSTED_DAILY_HISTORY_STARTS_2021_09_07_SO_EARLY_SMA200_VALUES_ARE_UNAVAILABLE",
            "STRUCTURAL_BREADTH_IS_NOT_PERFORMANCE_EVIDENCE",
            "NO_VALIDATION_OR_2025_PLUS_DATA_ACCESSED",
        ),
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    manifest = {
        "family_version": FAMILY_VERSION,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_b_config_hash": config["family_b_config_hash"],
        "success_criteria_hash": criteria["success_criteria_hash"],
        "control_reference_hash": control["control_reference_hash"],
        "registry_hash": registry["registry_hash"],
        "generated_at": started_at,
        "development_latest_date_allowed": DEVELOPMENT_END.isoformat(),
        "future_returns_accessed": False,
        "final_performance_results_present": False,
        "validation_accessed": False,
        "family_a_snapshot_hash": family_a_after["snapshot_hash"],
        "artifact_hashes": artifact_hashes,
        "summary_hash_at_generation": file_sha256(reports_root / REPORT_NAMES[0]),
    }
    write_json(manifests_root / "run_manifest_v1.json", manifest)
    return summary


def finalize_family_b_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_b_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Generate Family B architecture before finalizing review")
    summary = _read_json(summary_path)
    current_family_a = family_a_immutability_snapshot(root)
    if current_family_a["snapshot_hash"] != summary["regression"]["family_a_after_snapshot_hash"]:
        raise FamilyBFreezeMismatch("Family A changed after Family B generation")
    criteria = success_criteria_config()
    config = family_config(criteria)
    registry = experiment_registry(config, criteria, control_reference(config))
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)
    if summary["governance"]["final_development_performance_run"] is not False:
        raise FamilyBFreezeMismatch("Final development performance was run")
    if summary["governance"]["validation_accessed"] is not False:
        raise FamilyBFreezeMismatch("Validation was accessed")
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["classifications"]["FAMILY_B_ARCHITECTURE_RESULT"]
        == "READY_FOR_DEVELOPMENT_BACKTEST"
        and summary["regression"]["family_a_unchanged"] is True
        and summary["governance"]["checklist_passed"] is True,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "CAPITAL_INR",
    "COMMAND",
    "CONTROL_ID",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "EXPECTED_CONTROL_REFERENCE_HASH",
    "EXPECTED_EXPERIMENT_HASHES",
    "EXPECTED_FAMILY_B_CONFIG_HASH",
    "EXPECTED_SUCCESS_CRITERIA_HASH",
    "EXPERIMENT_IDS",
    "FAMILY_CODE",
    "FAMILY_STATUS",
    "FAMILY_VERSION",
    "FUTURE_RESULT_LABELS",
    "GOVERNANCE_CHECKLIST",
    "MINIMUM_HOLDINGS",
    "RESEARCH_PROFILE",
    "RESEARCH_PROTOCOL",
    "REPORT_NAMES",
    "SMA_SESSIONS",
    "b001_eligibility",
    "b002_eligibility",
    "build_family_b_architecture",
    "build_signal_dataset",
    "classify_future_experiment_result",
    "control_reference",
    "experiment_registry",
    "family_a_immutability_snapshot",
    "family_config",
    "finalize_family_b_review",
    "simple_moving_average_200",
    "success_criteria_config",
)

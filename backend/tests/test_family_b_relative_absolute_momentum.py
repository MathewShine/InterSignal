from __future__ import annotations

import json
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_phase2_closure import EXPECTED_CLOSURE_HASH
from app.research.strategy.family_b_relative_absolute_momentum import (
    CAPITAL_INR,
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_IDS,
    FAMILY_CODE,
    FAMILY_STATUS,
    FAMILY_VERSION,
    FUTURE_RESULT_LABELS,
    GOVERNANCE_CHECKLIST,
    MINIMUM_HOLDINGS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    REPORT_NAMES,
    SMA_SESSIONS,
    _rank_source_rows,
    b001_eligibility,
    b002_eligibility,
    classify_future_experiment_result,
    control_reference,
    experiment_registry,
    family_a_immutability_snapshot,
    family_config,
    simple_moving_average_200,
    success_criteria_config,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_v1_summary.json"


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def frozen_documents() -> tuple[dict, dict, dict, dict]:
    criteria = success_criteria_config()
    config = family_config(criteria)
    control = control_reference(config)
    registry = experiment_registry(config, criteria, control)
    return criteria, config, control, registry


def test_exact_family_identity_profile_code_protocol_and_status() -> None:
    assert FAMILY_VERSION == "STRATEGY_FAMILY_B_RELATIVE_ABSOLUTE_MOMENTUM_V1"
    assert RESEARCH_PROFILE == "RELATIVE_PLUS_ABSOLUTE_MOMENTUM_V1"
    assert FAMILY_CODE == "FAMILY_B"
    assert RESEARCH_PROTOCOL == "FAMILY_B_RESEARCH_PROTOCOL_V1"
    assert FAMILY_STATUS == "PREREGISTERED_RESEARCH_FAMILY"


def test_registry_has_exactly_two_experiments_and_one_control() -> None:
    _, _, _, registry = frozen_documents()
    assert registry["experiment_count"] == 2
    assert tuple(registry["experiment_ids"]) == EXPERIMENT_IDS == ("MOM-B-001", "MOM-B-002")
    assert registry["control_count"] == 1
    assert registry["control"]["control_id"] == CONTROL_ID == "CONTROL-B-000"
    assert registry["control"]["status"] == "REFERENCE_CONTROL"
    assert registry["control"]["family_b_experiment"] is False


def test_all_preregistration_hashes_are_exact_and_recompute() -> None:
    criteria, config, control, registry = frozen_documents()
    assert config["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH
    assert criteria["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert control["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    assert canonical_hash({key: value for key, value in config.items() if key != "family_b_config_hash"}) == EXPECTED_FAMILY_B_CONFIG_HASH
    assert canonical_hash({key: value for key, value in criteria.items() if key != "success_criteria_hash"}) == EXPECTED_SUCCESS_CRITERIA_HASH
    assert canonical_hash({key: value for key, value in control.items() if key != "control_reference_hash"}) == EXPECTED_CONTROL_REFERENCE_HASH
    for row in registry["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]
        assert row["parameter_hash"] == expected["parameter_hash"]
        assert canonical_hash(row["parameters"]) == expected["parameter_hash"]
        assert row["preregistration_hash"] == expected["preregistration_hash"]
        preregistration = {key: value for key, value in row.items() if key != "preregistration_hash"}
        assert canonical_hash(preregistration) == expected["preregistration_hash"]


def test_control_is_frozen_mom_a_002_at_500k_without_performance() -> None:
    _, _, control, _ = frozen_documents()
    assert control["underlying_experiment_id"] == "MOM-A-002"
    assert control["role"] == "CONTROL_REPRODUCTION_ONLY"
    assert control["capital_inr"] == CAPITAL_INR == Decimal("500000")
    assert control["performance_run_by_command_01"] is False


def test_relative_rule_is_six_month_descending_top_decile() -> None:
    _, config, _, _ = frozen_documents()
    rule = config["relative_momentum"]
    assert rule["signal"] == "6M_COMPOUNDED_RETURN"
    assert rule["lookback_trading_sessions"] == 126
    assert rule["ranking"] == "DESCENDING_CROSS_SECTIONAL"
    assert rule["candidate_pool"] == "TOP_10_PERCENT"
    assert rule["candidate_fraction"] == Decimal("0.10")


def test_relative_rank_and_top_decile_round_up_with_symbol_tie_break() -> None:
    rows = [
        {"symbol": f"S{index:02d}", "eligible": "True", "6m_return": str(index // 2)}
        for index in range(21)
    ]
    ranked = _rank_source_rows(rows)
    assert ranked["top_decile_count"] == math.ceil(21 * 0.10) == 3
    assert ranked["top_decile_symbols"] == ["S20", "S18", "S19"]
    assert ranked["ranked"]["S20"]["rank"] == 1


def test_b001_strict_positive_rule_and_zero_rejection() -> None:
    assert b001_eligibility(True, Decimal("0.0000001")) == "ELIGIBLE"
    assert b001_eligibility(True, Decimal("0")) == "NOT_ELIGIBLE"
    assert b001_eligibility(True, Decimal("-0.0000001")) == "NOT_ELIGIBLE"
    assert b001_eligibility(False, Decimal("1")) == "NOT_ELIGIBLE"
    assert b001_eligibility(True, None) == "UNAVAILABLE"


def test_b002_strict_above_sma_rule_and_equality_rejection() -> None:
    assert b002_eligibility(True, Decimal("100.01"), Decimal("100"), 200) == "ELIGIBLE"
    assert b002_eligibility(True, Decimal("100"), Decimal("100"), 200) == "NOT_ELIGIBLE"
    assert b002_eligibility(True, Decimal("99.99"), Decimal("100"), 200) == "NOT_ELIGIBLE"
    assert b002_eligibility(False, Decimal("101"), Decimal("100"), 200) == "NOT_ELIGIBLE"
    assert b002_eligibility(True, Decimal("101"), None, 199) == "UNAVAILABLE"


def test_sma_uses_exactly_200_valid_observations_and_no_future_data() -> None:
    formation = date(2024, 1, 1)
    start = formation - timedelta(days=205)
    closes = {start + timedelta(days=index): Decimal(index + 1) for index in range(206)}
    closes[formation + timedelta(days=1)] = Decimal("1000000")
    observed = simple_moving_average_200(closes, formation)
    expected_values = [value for observed_date, value in sorted(closes.items()) if observed_date <= formation][-200:]
    assert observed["observation_count"] == SMA_SESSIONS == 200
    assert observed["value"] == sum(expected_values, Decimal("0")) / Decimal("200")
    assert observed["window_end"] == formation
    assert observed["no_lookahead"] is True


def test_sma_is_unavailable_with_199_observations() -> None:
    formation = date(2024, 1, 1)
    closes = {formation - timedelta(days=index): Decimal("100") for index in range(199)}
    observed = simple_moving_average_200(closes, formation)
    assert observed["value"] is None
    assert observed["observation_count"] == 199
    assert observed["reason"] == "FEWER_THAN_200_VALID_OBSERVATIONS"


def test_portfolio_has_minimum_ten_no_backfill_and_cash_behavior() -> None:
    _, config, _, registry = frozen_documents()
    portfolio = config["portfolio"]
    assert portfolio["minimum_qualifying_holdings"] == MINIMUM_HOLDINGS == 10
    assert portfolio["no_backfill"] is True
    assert portfolio["whole_share_residual_remains_cash"] is True
    assert portfolio["low_breadth_action"] == "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH"
    assert all(row["parameters"]["no_backfill"] is True for row in registry["experiments"])


def test_quarterly_next_open_equal_weight_whole_shares_and_costs_are_frozen() -> None:
    _, config, _, registry = frozen_documents()
    assert config["rebalance"]["frequency"] == "QUARTERLY"
    assert config["rebalance"]["execution"] == "NEXT_ELIGIBLE_NSE_SESSION_OPEN"
    assert config["rebalance"]["same_close_execution_allowed"] is False
    assert config["portfolio"]["weighting"] == "EQUAL_WEIGHT"
    assert config["evaluation_modes"]["primary"] == "EXECUTABLE_INTEGER_SHARE_500K"
    assert all(row["parameters"]["whole_shares"] is True for row in registry["experiments"])
    assert config["costs"]["model"] == "INDIA_EQUITY_COST_MODEL_V1"
    assert config["costs"]["profile"] == "NSE_CASH_DELIVERY_RESEARCH_V1"
    assert config["costs"]["scenario"] == "COST-SCENARIO-002"
    assert config["costs"]["slippage_bps_per_side"] == Decimal("5")


def test_exact_standard_success_criteria_are_frozen() -> None:
    criteria = success_criteria_config()
    standard = criteria["standard_criteria"]
    assert criteria["standard_criteria_count"] == 7
    assert standard["A_RETURN_PRESERVATION"]["minimum_ratio"] == Decimal("0.85")
    assert standard["B_DRAWDOWN"]["material_improvement_minimum_relative"] == Decimal("0.15")
    assert standard["B_DRAWDOWN"]["maximum_relative_worsening"] == Decimal("0.10")
    assert standard["C_TEMPORAL_SUPPORT"]["nonnegative_development_years_minimum"] == 2
    assert standard["C_TEMPORAL_SUPPORT"]["control_underperformance_limit_percentage_points"] == Decimal("15")
    assert standard["C_TEMPORAL_SUPPORT"]["years_allowed_beyond_underperformance_limit"] == 1
    assert standard["D_COST_EFFICIENCY"]["maximum_relative_increase"] == Decimal("0.25")
    assert standard["E_BREADTH"]["minimum_fraction_of_scheduled_rebalances"] == Decimal("0.80")
    assert standard["F_CAPITAL_DEPLOYMENT"]["maximum_fraction"] == Decimal("0.35")
    assert standard["G_ACCOUNTING_DATA_INTEGRITY"]["required"] is True


def test_strong_partial_and_fatal_classification_rules_are_frozen() -> None:
    criteria = success_criteria_config()
    strong = criteria["strongly_supported"]
    fatal = criteria["fatal_failure"]
    partial = criteria["partially_supported"]
    assert strong["minimum_cagr_preservation_ratio"] == Decimal("0.90")
    assert strong["minimum_relative_drawdown_improvement"] == Decimal("0.15")
    assert strong["negative_development_years_allowed"] == 0
    assert fatal["cagr_preservation_ratio_strictly_below"] == Decimal("0.70")
    assert fatal["drawdown_relative_worsening_strictly_above"] == Decimal("0.20")
    assert fatal["breadth_fraction_strictly_below"] == Decimal("0.60")
    assert fatal["average_cash_fraction_strictly_above"] == Decimal("0.50")
    assert fatal["implementation_or_data_failure"] is True
    assert fatal["lookahead_detected"] is True
    assert partial["fatal_failure_allowed"] is False
    assert partial["minimum_standard_criteria_passed"] == 4
    assert tuple(criteria["allowed_experiment_results"]) == FUTURE_RESULT_LABELS


def test_future_classification_precedence_is_encoded_before_performance() -> None:
    keys = tuple(success_criteria_config()["standard_criteria"])
    all_pass = {key: True for key in keys}
    four_pass = {key: index < 4 for index, key in enumerate(keys)}
    three_pass = {key: index < 3 for index, key in enumerate(keys)}
    common = {
        "fatal_conditions": {"lookahead": False, "data_failure": False},
        "cagr_preservation_ratio": Decimal("0.90"),
        "relative_drawdown_improvement": Decimal("0.15"),
        "negative_development_years": 0,
        "accounting_clean": True,
        "interpretable": True,
    }
    assert classify_future_experiment_result(standard_criteria_passes=all_pass, **common) == "STRONGLY_SUPPORTED"
    assert classify_future_experiment_result(
        standard_criteria_passes=all_pass,
        **{**common, "cagr_preservation_ratio": Decimal("0.89")},
    ) == "SUPPORTED"
    assert classify_future_experiment_result(standard_criteria_passes=four_pass, **common) == "PARTIALLY_SUPPORTED"
    assert classify_future_experiment_result(standard_criteria_passes=three_pass, **common) == "FAILED"
    assert classify_future_experiment_result(
        standard_criteria_passes=all_pass,
        **{**common, "interpretable": False},
    ) == "INCONCLUSIVE"
    assert classify_future_experiment_result(
        standard_criteria_passes=all_pass,
        **{**common, "fatal_conditions": {"lookahead": True}},
    ) == "FAILED"


def test_governance_v2_checklist_has_all_fourteen_items() -> None:
    result = summary()
    assert result["governance"]["policy"] == "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
    assert result["governance"]["policy_active"] is True
    assert len(GOVERNANCE_CHECKLIST) == 14
    assert result["governance"]["checklist_count"] == 14
    assert result["governance"]["checklist_passed"] is True


def test_structural_pilots_all_pass_without_performance() -> None:
    result = summary()
    pilots = result["structural_pilots"]
    assert pilots["B001"] == {"case_count": 5, "passed": True}
    assert pilots["B002"] == {"case_count": 5, "passed": True}
    assert pilots["sma200_reconciliation"]["case_count"] >= 3
    assert pilots["sma200_reconciliation"]["all_exact"] is True
    assert pilots["sma200_reconciliation"]["all_no_lookahead"] is True
    assert pilots["relative_rank_reconciliation"]["all_exact"] is True
    assert pilots["relative_rank_reconciliation"]["future_returns_accessed"] is False
    assert pilots["capital_rebalance"]["all_accounting_reconciled"] is True
    assert pilots["capital_rebalance"]["all_no_backfill"] is True
    assert pilots["capital_rebalance"]["performance_evaluated"] is False


def test_breadth_report_contains_only_structural_counts() -> None:
    result = summary()
    assert result["breadth"]["scheduled_rebalances"] == 11
    assert result["breadth"]["B001"]["minimum_qualifying_count"] == 19
    assert result["breadth"]["B001"]["maximum_qualifying_count"] == 35
    assert result["breadth"]["B001"]["insufficient_breadth_schedules"] == []
    assert result["breadth"]["B002"]["minimum_qualifying_count"] == 0
    assert result["breadth"]["B002"]["maximum_qualifying_count"] == 34
    assert result["breadth"]["B002"]["insufficient_breadth_schedules"] == ["2022-03-31"]
    assert result["breadth"]["future_returns_accessed"] is False


def test_command_did_not_run_performance_validation_or_alternates() -> None:
    governance = summary()["governance"]
    assert governance["final_development_performance_run"] is False
    assert governance["future_returns_accessed"] is False
    assert governance["validation_authorized"] is False
    assert governance["validation_accessed"] is False
    assert governance["alternate_positive_return_threshold_tested"] is False
    assert governance["alternate_moving_average_tested"] is False
    assert governance["alternate_capital_tested"] is False
    assert governance["regime_added"] is False
    assert governance["stop_or_target_added"] is False
    assert governance["intraday_added"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["family_c_started"] is False


def test_data_and_architecture_results_are_reviewable() -> None:
    classifications = summary()["classifications"]
    assert classifications["FAMILY_B_DATA_READINESS"] == "READY_WITH_LIMITATIONS"
    assert classifications["FAMILY_B_ARCHITECTURE_RESULT"] == "READY_FOR_DEVELOPMENT_BACKTEST"
    assert classifications["future_experiment_result"] is None
    assert classifications["future_family_result"] is None


def test_development_partition_is_exact_and_validation_is_not_authorized() -> None:
    _, config, _, _ = frozen_documents()
    assert DEVELOPMENT_START == date(2022, 1, 1)
    assert DEVELOPMENT_END == date(2024, 12, 31)
    assert config["development_window"]["start"] == "2022-01-01"
    assert config["development_window"]["end"] == "2024-12-31"
    assert config["development_window"]["dates_after_2024_loaded"] is False
    assert config["validation_eligibility_rule"]["current_status"] == "NOT_AUTHORIZED"
    assert config["validation_eligibility_rule"]["automatic_validation_after_development"] is False


def test_family_a_closure_and_all_prior_command_hashes_are_preserved() -> None:
    result = summary()["regression"]
    assert result["family_a_unchanged"] is True
    assert result["family_a_closure_hash"] == EXPECTED_CLOSURE_HASH
    assert result["family_a_command_01_config_hash"] == "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3"
    assert result["family_a_command_02_registry_hash"] == "533509cf3735a5b86781d7b3865e4fd2e96e561ab98afe00804504547de84b43"
    assert result["family_a_command_03_config_hash"] == "8800738a5716ccbd1464ff564c5dea3b2891c523063eee01d5ad85fb583672cc"
    assert result["family_a_command_03_registry_hash"] == "bdb431c0962183942a1d1253a07abd9df359cec6db18ca58686622bf0c603f20"
    assert result["family_a_command_05_closure_hash"] == EXPECTED_CLOSURE_HASH
    assert result["cap4_validation_state"] == "EVALUATED"
    assert result["cap4_validation_run_count"] == 1


def test_family_a_snapshot_is_currently_stable() -> None:
    before = family_a_immutability_snapshot(REPO_ROOT)
    after = family_a_immutability_snapshot(REPO_ROOT)
    assert before == after
    assert before["closure_hash"] == EXPECTED_CLOSURE_HASH


def test_all_storage_subdirectories_and_reports_exist() -> None:
    result = summary()
    output_root = REPO_ROOT / result["storage"]["root"]
    for subdirectory in (
        "registry",
        "signals",
        "pilots",
        "manifests",
        "governance",
        "rebalance_calendar",
    ):
        assert (output_root / subdirectory).is_dir()
    assert len(REPORT_NAMES) == 7
    assert all((REPO_ROOT / "data/reports" / name).exists() for name in REPORT_NAMES)


def test_signal_dataset_has_exact_required_fields() -> None:
    path = REPO_ROOT / "data/research/strategy_families/family_b/v1/signals/family_b_signal_inputs_v1.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == [
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
    ]


def test_security_and_zero_external_side_effects() -> None:
    safety = summary()["safety"]
    assert safety["live_signals_generated"] == 0
    assert safety["live_orders_placed"] == 0
    assert safety["broker_calls"] == 0
    assert safety["remote_migrations"] == 0
    assert safety["supabase_persistence"] == 0
    assert safety["secrets_written"] == 0
    assert safety["strategy_v2_created"] is False


def test_roadmap_preserves_family_b_lineage_after_later_closure() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |" in roadmap
    for family in "EFG":
        assert f"| Family {family} |" in roadmap
    assert roadmap.count("PLANNED_NOT_STARTED") >= 3

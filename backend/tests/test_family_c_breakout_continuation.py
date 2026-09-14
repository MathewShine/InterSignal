from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import estimate_order_cost
from app.research.strategy.family_b_research_closure import (
    EXPECTED_FAMILY_B_CLOSURE_HASH,
    family_b_baseline_snapshot,
)
from app.research.strategy.family_c_breakout_continuation import (
    BREAKOUT_WINDOW,
    COMPRESSION_THRESHOLD,
    COMPRESSION_WINDOW,
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_IDS,
    FAMILY_CODE,
    FAMILY_VERSION,
    FUTURE_PORTFOLIO_FIELDS,
    FUTURE_POSITION_FIELDS,
    GOVERNANCE_CHECKLIST,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    REPORT_NAMES,
    SIGNAL_FIELDS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    VOLUME_THRESHOLD,
    breakout_calculation,
    compression_calculation,
    control_reference,
    entry_exit_chronology,
    experiment_registry,
    family_config,
    high_win_rate_flag,
    rank_capacity_signals,
    success_criteria_config,
    verify_expected_hashes,
    verify_registry,
    volume_calculation,
    whole_share_position,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data/research/strategy_families/family_c/v1"


def frozen_records():
    criteria = success_criteria_config()
    config = family_config(criteria)
    control = control_reference(config, criteria)
    registry = experiment_registry(config, criteria, control)
    return criteria, config, control, registry


def test_exact_family_identity_ids_and_experiment_count() -> None:
    criteria, config, control, registry = frozen_records()
    assert FAMILY_VERSION == "STRATEGY_FAMILY_C_BREAKOUT_CONTINUATION_V1"
    assert RESEARCH_PROFILE == "DAILY_BREAKOUT_CONTINUATION_V1"
    assert FAMILY_CODE == "FAMILY_C"
    assert RESEARCH_PROTOCOL == "FAMILY_C_RESEARCH_PROTOCOL_V1"
    assert CONTROL_ID == "CONTROL-C-000"
    assert control["name"] == "PURE_20D_CLOSE_BREAKOUT_V1"
    assert EXPERIMENT_IDS == ("BRK-C-001", "BRK-C-002")
    assert registry["experiment_count"] == 2
    assert [row["name"] for row in registry["experiments"]] == [
        "20D_BREAKOUT_WITH_10D_COMPRESSION_V1",
        "20D_BREAKOUT_WITH_VOLUME_EXPANSION_V1",
    ]
    verify_registry(registry, config, criteria)


def test_all_preregistration_hashes_are_exact_and_recomputable() -> None:
    criteria, config, control, registry = frozen_records()
    assert config["family_c_config_hash"] == EXPECTED_FAMILY_C_CONFIG_HASH
    assert control["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    assert criteria["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert canonical_hash(
        {key: value for key, value in config.items() if key != "family_c_config_hash"}
    ) == EXPECTED_FAMILY_C_CONFIG_HASH
    assert canonical_hash(
        {key: value for key, value in criteria.items() if key != "success_criteria_hash"}
    ) == EXPECTED_SUCCESS_CRITERIA_HASH
    for row in registry["experiments"]:
        expected = EXPECTED_EXPERIMENT_HASHES[row["experiment_id"]]
        assert row["parameter_hash"] == expected["parameter_hash"]
        assert row["preregistration_hash"] == expected["preregistration_hash"]
        assert canonical_hash(row["parameters"]) == row["parameter_hash"]
        assert canonical_hash(
            {key: value for key, value in row.items() if key != "preregistration_hash"}
        ) == row["preregistration_hash"]
    verify_expected_hashes(config, criteria, registry)


def test_breakout_uses_exact_prior_20_highs_and_excludes_formation() -> None:
    prior = [Decimal(value) for value in range(81, 101)]
    result = breakout_calculation(Decimal("101"), prior)
    assert len(prior) == BREAKOUT_WINDOW == 20
    assert result["prior_20d_high"] == Decimal("100")
    assert result["breakout_strength_pct"] == Decimal("0.01")
    assert result["is_20d_breakout"] is True
    # Formation high is intentionally not an input; only formation close is accepted.
    assert set(result) == {
        "prior_20d_high",
        "breakout_strength_pct",
        "is_20d_breakout",
        "available",
    }


def test_equality_is_not_breakout_and_history_is_never_shortened() -> None:
    prior = [Decimal("100")] * 20
    assert breakout_calculation(Decimal("100"), prior)["is_20d_breakout"] is False
    unavailable = breakout_calculation(Decimal("101"), prior[:-1])
    assert unavailable["available"] is False
    assert unavailable["is_20d_breakout"] is False


def test_compression_is_exact_prior_10_range_with_inclusive_8_percent() -> None:
    exact = compression_calculation(
        Decimal("100"),
        [Decimal("104")] * 10,
        [Decimal("96")] * 10,
    )
    above = compression_calculation(
        Decimal("100"),
        [Decimal("104")] * 10,
        [Decimal("95.99")] * 10,
    )
    assert COMPRESSION_WINDOW == 10
    assert COMPRESSION_THRESHOLD == Decimal("0.08")
    assert exact["compression_range_pct"] == Decimal("0.08")
    assert exact["compression_pass"] is True
    assert above["compression_range_pct"] == Decimal("0.0801")
    assert above["compression_pass"] is False
    assert compression_calculation(
        Decimal("100"), [Decimal("104")] * 9, [Decimal("96")] * 9
    )["available"] is False


def test_volume_uses_exact_prior_20_median_and_inclusive_1_5_ratio() -> None:
    prior = [Decimal(value) for value in range(991, 1011)]
    result = volume_calculation(Decimal("1500.75"), prior)
    assert result["median_volume_20"] == Decimal("1000.5")
    assert result["formation_volume_ratio"] == Decimal("1.5")
    assert VOLUME_THRESHOLD == Decimal("1.50")
    assert result["volume_pass"] is True
    assert volume_calculation(Decimal("1500.74"), prior)["volume_pass"] is False
    assert volume_calculation(Decimal("1501"), prior[:-1])["available"] is False


def test_treatments_are_isolated_and_no_combined_filter_exists() -> None:
    _, _, _, registry = frozen_records()
    c001, c002 = registry["experiments"]
    assert c001["parameters"]["volume_filter"] is None
    assert c002["parameters"]["compression_filter"] is None
    assert c001["parameters"]["combined_compression_and_volume_filter"] is False
    assert c002["parameters"]["combined_compression_and_volume_filter"] is False
    assert registry["combined_filter_registered"] is False


def test_next_open_entry_and_exact_ten_session_t_plus_11_exit() -> None:
    sessions = [date(2024, 1, 1) + timedelta(days=index) for index in range(13)]
    result = entry_exit_chronology(sessions, sessions[0])
    assert result["entry_date"] == sessions[1]
    assert result["holding_dates"] == tuple(sessions[1:11])
    assert result["holding_sessions"] == HOLDING_SESSIONS == 10
    assert result["exit_date"] == sessions[11]
    assert result["available"] is True


def test_portfolio_freeze_no_stop_target_pyramid_or_rebalance() -> None:
    _, config, _, _ = frozen_records()
    portfolio = config["portfolio"]
    execution = config["execution"]
    assert STARTING_CAPITAL == Decimal("500000")
    assert portfolio["maximum_concurrent_positions"] == MAX_CONCURRENT_POSITIONS == 20
    assert portfolio["target_initial_position_notional_fraction_current_equity"] == TARGET_NOTIONAL_FRACTION == Decimal("0.05")
    assert portfolio["whole_shares"] is True
    assert portfolio["one_position_per_symbol"] is True
    assert portfolio["pyramiding_allowed"] is False
    assert portfolio["reentry"] == "ONLY_AFTER_FULL_EXIT"
    assert portfolio["rebalance_existing_positions"] is False
    assert execution["stop_loss"] is None
    assert execution["profit_target"] is None
    assert execution["trailing_stop"] is None


def test_capacity_ranking_and_whole_share_position_are_deterministic() -> None:
    fixture = [
        {"symbol": "B", "breakout_strength_pct": Decimal("0.10")},
        {"symbol": "A", "breakout_strength_pct": Decimal("0.10")},
        {"symbol": "C", "breakout_strength_pct": Decimal("0.20")},
    ]
    ranked = rank_capacity_signals(fixture, 2)
    assert [row["symbol"] for row in ranked["selected"]] == ["C", "A"]
    assert [row["symbol"] for row in ranked["rejected"]] == ["B"]
    position = whole_share_position(
        Decimal("500000"), Decimal("500000"), Decimal("333")
    )
    assert position["intended_notional"] == Decimal("25000.00")
    assert position["actual_shares"] == 75
    assert position["actual_notional"] == Decimal("24975")


def test_cost_model_and_architecture_fields_are_frozen() -> None:
    _, config, _, _ = frozen_records()
    assert config["costs"] == {
        "model": "INDIA_EQUITY_COST_MODEL_V1",
        "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "scenario": SCENARIO_BASELINE_SLIPPAGE,
        "slippage_bps_per_side": Decimal("5"),
    }
    buy = estimate_order_cost("BUY", date(2024, 1, 2), Decimal("25000"))
    sell = estimate_order_cost("SELL", date(2024, 1, 12), Decimal("25000"))
    assert buy["cost_config_hash"] == sell["cost_config_hash"] == EXPECTED_COST_CONFIG_HASH
    assert buy["scenario_id"] == sell["scenario_id"] == "COST-SCENARIO-002"
    assert buy["components"]["STAMP_DUTY"] > 0
    assert sell["components"]["DP_CHARGE"] > 0
    assert len(SIGNAL_FIELDS) == 23
    assert set(FUTURE_POSITION_FIELDS) == {
        "entry_date", "entry_price", "exit_date", "exit_price", "gross_return_pct",
        "net_return_pct", "MFE_pct", "MAE_pct", "holding_sessions", "entry_gap_pct",
        "transaction_costs",
    }
    assert len(FUTURE_PORTFOLIO_FIELDS) == 9


def test_success_criteria_and_high_win_rate_threshold_are_exact() -> None:
    criteria = success_criteria_config()
    control = criteria["control_viability"]
    standard = criteria["treatment_standard_criteria"]
    quality = criteria["quality_improvement_dimensions"]
    assert control["A_NET_CAGR"]["threshold"] == 0
    assert control["B_NET_PROFIT_FACTOR"]["threshold"] == Decimal("1.05")
    assert control["D_MAX_DRAWDOWN_MAGNITUDE"]["threshold"] == Decimal("0.35")
    assert control["F_CLOSED_POSITIONS"]["threshold"] == 100
    assert standard["A_RETURN_PRESERVATION"]["control_cagr_positive_ratio_threshold"] == Decimal("0.90")
    assert standard["B_TREATMENT_PROFITABILITY"]["net_profit_factor_threshold"] == Decimal("1.10")
    assert standard["C_DRAWDOWN_NON_DEGRADATION"]["maximum_relative_worsening"] == Decimal("0.10")
    assert standard["D_TEMPORAL_SUPPORT"]["maximum_yearly_underperformance_percentage_points"] == Decimal("15")
    assert standard["E_COST_EFFICIENCY"]["maximum_normalized_cost_drag_multiple"] == Decimal("1.30")
    assert standard["F_SAMPLE_ADEQUACY"]["normal_minimum_closed_positions"] == 75
    assert quality["H_WIN_RATE_IMPROVEMENT"]["percentage_points"] == Decimal("5")
    assert quality["I_PROFIT_FACTOR_IMPROVEMENT"]["absolute_increment"] == Decimal("0.05")
    assert quality["J_EXPECTANCY_IMPROVEMENT"]["positive_control_multiple"] == Decimal("1.10")
    assert quality["K_MATERIAL_DRAWDOWN_IMPROVEMENT"]["relative_improvement"] == Decimal("0.10")
    assert criteria["capacity_stability"]["threshold"] == Decimal("0.25")
    assert high_win_rate_flag(Decimal("0.60")) == "YES"
    assert high_win_rate_flag(Decimal("0.5999")) == "NO"


def test_governance_v2_no_performance_validation_or_strategy_v2() -> None:
    _, config, _, registry = frozen_records()
    assert len(GOVERNANCE_CHECKLIST) == 14
    assert GOVERNANCE_CHECKLIST == (
        "hypothesis", "experiment_id", "population", "exact_parameters", "control",
        "primary_metrics", "secondary_metrics", "numerical_success_criteria",
        "failure_criteria", "stop_conditions", "validation_eligibility", "cost_model",
        "data_partition", "hashes",
    )
    assert config["performance_policy"]["performance_results_generated"] is False
    assert config["performance_policy"]["validation_accessed"] is False
    assert config["performance_policy"]["strategy_v2_creation_allowed"] is False
    assert registry["performance_evaluated"] is False
    assert registry["validation_accessed"] is False
    assert DEVELOPMENT_START == date(2022, 1, 1)
    assert DEVELOPMENT_END == date(2024, 12, 31)


def test_family_b_closure_and_complete_upstream_snapshot_verify() -> None:
    snapshot = family_b_baseline_snapshot(REPO_ROOT)
    assert snapshot["validation_accessed"] is False
    assert snapshot["daily_history_version"] == "DAILY_HISTORY_PREHISTORY_V2"
    manifest = json.loads(
        (
            REPO_ROOT
            / "data/research/strategy_families/family_b/v1/closure/manifest/family_b_closure_manifest_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["family_b_closure_hash"] == EXPECTED_FAMILY_B_CLOSURE_HASH


def test_generated_reports_protocol_pilots_and_manifest() -> None:
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).is_file()
    for directory in (
        "registry", "signals", "pilots", "manifests", "governance", "capacity", "calendars"
    ):
        assert (OUTPUT_ROOT / directory).is_dir()
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_v1_summary.json").read_text(encoding="utf-8")
    )
    assert summary["family_c_config_hash"] == EXPECTED_FAMILY_C_CONFIG_HASH
    assert summary["classifications"]["FAMILY_C_DATA_READINESS"] in {
        "READY", "READY_WITH_LIMITATIONS"
    }
    assert summary["classifications"]["FAMILY_C_ARCHITECTURE_RESULT"] == "READY_FOR_DEVELOPMENT_BACKTEST"
    assert summary["pilots"]["all_passed"] is True
    assert summary["governance"]["checklist_count"] == 14
    assert summary["governance"]["development_performance_run"] is False
    assert summary["security"] == {
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "external_writes": 0,
        "secrets_added": 0,
    }


def test_roadmap_advances_only_family_c_lifecycle() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |" in roadmap
    for family in "EFG":
        line = next(row for row in roadmap.splitlines() if row.startswith(f"| Family {family} |"))
        assert "PLANNED_NOT_STARTED" in line

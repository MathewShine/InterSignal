from __future__ import annotations

import ast
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_g_regime_volatility import (
    CASH_RETURN,
    CONTROL_ID,
    CONTROL_NAME,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_F_CLOSURE_HASH,
    EXPECTED_FAMILY_G_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPECTED_TREATMENT_PARAMETER_HASH,
    EXPECTED_TREATMENT_PREREGISTRATION_HASH,
    EXPERIMENT_COUNT,
    FAMILY_CODE,
    FAMILY_VERSION,
    GOVERNANCE_CHECKLIST,
    MARKET_INDEX_NAME,
    REGIME_DATASET_FIELDS,
    REPORT_NAMES,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    SMA_WINDOW,
    STARTING_CAPITAL,
    TREATMENT_ID,
    TREATMENT_NAME,
    accounting_pilot_document,
    build_regime_dataset,
    market_trend_gate,
    previous_family_snapshot,
    simple_moving_average,
    success_criteria_document,
    verify_family_a_reference,
    verify_family_f_closure,
    verify_governance_v2,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_ROOT = REPO_ROOT / "data/research/strategy_families/family_g/v1"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _regime_rows() -> list[dict[str, str]]:
    return read_csv(FAMILY_ROOT / "regime/family_g_rebalance_regime_v1.csv")


def test_family_f_closure_hash_is_exactly_verified() -> None:
    result = verify_family_f_closure(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert all(result["checks"].values())
    assert result["family_f_closure_hash"] == EXPECTED_FAMILY_F_CLOSURE_HASH
    assert EXPECTED_FAMILY_F_CLOSURE_HASH == (
        "515bd3dc996c1e119e3e422f182ba82abfa8f2d312346df2c7a5751322d7716d"
    )


def test_exact_family_identity_and_treatment_count() -> None:
    summary = _summary()
    assert FAMILY_VERSION == "STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1"
    assert RESEARCH_PROFILE == "QUARTERLY_MOMENTUM_REGIME_PARTICIPATION_V1"
    assert FAMILY_CODE == "FAMILY_G"
    assert RESEARCH_PROTOCOL == "FAMILY_G_RESEARCH_PROTOCOL_V1"
    assert CONTROL_ID == "CONTROL-G-000"
    assert CONTROL_NAME == "QUARTERLY_6M_MOMENTUM_ALWAYS_PARTICIPATE_V1"
    assert TREATMENT_ID == "REGIME-G-001"
    assert TREATMENT_NAME == (
        "QUARTERLY_6M_MOMENTUM_WITH_MARKET_TREND_GATE_V1"
    )
    assert EXPERIMENT_COUNT == summary["treatment_count"] == 1


def test_all_frozen_hashes_are_exact_and_canonical() -> None:
    config = _json(FAMILY_ROOT / "registry/family_g_config_v1.json")
    control = _json(FAMILY_ROOT / "registry/control_g_000_reference_v1.json")
    treatment = _json(FAMILY_ROOT / "registry/regime_g_001_parameters_v1.json")
    preregistration = _json(
        FAMILY_ROOT / "registry/regime_g_001_preregistration_v1.json"
    )
    criteria = _json(
        FAMILY_ROOT / "governance/family_g_success_criteria_v1.json"
    )
    assert (
        canonical_hash(
            {key: value for key, value in config.items() if key != "family_g_config_hash"}
        )
        == config["family_g_config_hash"]
        == EXPECTED_FAMILY_G_CONFIG_HASH
    )
    assert (
        canonical_hash(
            {
                key: value
                for key, value in control.items()
                if key != "control_g_000_reference_hash"
            }
        )
        == control["control_g_000_reference_hash"]
        == EXPECTED_CONTROL_REFERENCE_HASH
    )
    assert (
        canonical_hash(treatment["parameters"])
        == treatment["regime_g_001_parameter_hash"]
        == EXPECTED_TREATMENT_PARAMETER_HASH
    )
    assert (
        canonical_hash(
            {
                key: value
                for key, value in preregistration.items()
                if key != "regime_g_001_preregistration_hash"
            }
        )
        == preregistration["regime_g_001_preregistration_hash"]
        == EXPECTED_TREATMENT_PREREGISTRATION_HASH
    )
    assert (
        canonical_hash(
            {
                key: value
                for key, value in criteria.items()
                if key != "family_g_success_criteria_hash"
            }
        )
        == criteria["family_g_success_criteria_hash"]
        == EXPECTED_SUCCESS_CRITERIA_HASH
    )


def test_registry_statuses_and_promotion_gate_are_exact() -> None:
    registry = _json(
        FAMILY_ROOT / "registry/family_g_experiment_registry_v1.json"
    )
    assert registry["control_count"] == registry["treatment_count"] == 1
    assert len(registry["entries"]) == 2
    entries = {row["experiment_id"]: row for row in registry["entries"]}
    assert entries[CONTROL_ID]["status"] == "REFERENCE_CONTROL"
    assert entries[TREATMENT_ID]["status"] == "PREREGISTERED"
    assert all(row["promotion_allowed"] is False for row in entries.values())


def test_exact_family_a_control_reuse_and_integrity_references() -> None:
    result = verify_family_a_reference(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert all(result["checks"].values())
    config = _json(FAMILY_ROOT / "registry/family_g_config_v1.json")
    reference = config["underlying_strategy"]
    rules = config["frozen_family_a_rules"]
    assert reference["reference_experiment_id"] == "MOM-A-002"
    assert reference["implementation_evidence_id"] == "A2-002"
    assert rules["signal"] == "6M"
    assert rules["lookback_trading_sessions"] == 126
    assert rules["rebalance_frequency"] == "QUARTERLY"
    assert rules["selection"] == "TOP_DECILE"
    assert rules["selection_fraction"] == "0.10"
    assert rules["weighting"] == "EQUAL_WEIGHT"
    assert rules["whole_share_execution"] is True
    assert rules["universe"] == "POINT_IN_TIME_NIFTY_500"
    assert rules["minimum_price_inr"] == "100"
    assert rules["liquidity_window_sessions"] == 20
    assert rules["minimum_median_traded_value_inr"] == "100000000"
    assert rules["cost_model"] == "INDIA_EQUITY_COST_MODEL_V1"
    control = _json(FAMILY_ROOT / "registry/control_g_000_reference_v1.json")
    integrity = control["expected_development_result_integrity_reference_only"]
    assert integrity["net_ending_equity_inr"] == "955331.6799"
    assert integrity["net_total_return_pct"] == "91.0663359800"
    assert integrity["net_cagr_pct"] == "24.105850672292473"
    assert integrity["max_drawdown_pct"] == "-22.92216992201015671886716806"
    assert integrity["success_thresholds"] is False
    assert integrity["calculated_in_command_01"] is False


def test_exact_quarterly_schedule_is_reused() -> None:
    expected = [
        "2022-03-31",
        "2022-06-30",
        "2022-09-30",
        "2022-12-30",
        "2023-03-31",
        "2023-06-30",
        "2023-09-29",
        "2023-12-29",
        "2024-03-28",
        "2024-06-28",
        "2024-09-30",
    ]
    rows = _regime_rows()
    assert [row["rebalance_date"] for row in rows] == expected
    assert len(rows) == 11
    assert all(row["decision_frequency"] == "QUARTERLY_ONLY" for row in rows)


def test_sma200_is_simple_causal_including_t_and_strict() -> None:
    closes = [Decimal(index) for index in range(1, 201)]
    assert SMA_WINDOW == 200
    assert simple_moving_average(closes) == Decimal("100.5")
    assert simple_moving_average(closes[:-1]) is None
    assert simple_moving_average([*closes, Decimal("1000")]) == (
        sum([*closes[1:], Decimal("1000")], Decimal("0")) / Decimal("200")
    )
    assert market_trend_gate(Decimal("101"), Decimal("100")) is True
    assert market_trend_gate(Decimal("99"), Decimal("100")) is False
    assert market_trend_gate(Decimal("100"), Decimal("100")) is False
    assert market_trend_gate(Decimal("100"), None) is None


def test_exact_nifty500_regime_counts_and_early_history_limitation() -> None:
    summary = _summary()
    counts = summary["structural_counts"]
    assert summary["market_index"]["index_name"] == MARKET_INDEX_NAME == "NIFTY 500"
    assert counts["total_quarterly_rebalances"] == 11
    assert counts["gate_pass_count"] == 8
    assert counts["gate_fail_count"] == 2
    assert counts["gate_unavailable_count"] == 1
    assert counts["control_selected_count"] == 306
    assert counts["treatment_selected_count"] == 238
    assert (
        counts["yearly"]["2022"]["gate_pass_count"],
        counts["yearly"]["2022"]["gate_fail_count"],
        counts["yearly"]["2022"]["gate_unavailable_count"],
    ) == (2, 1, 1)
    assert (
        counts["yearly"]["2023"]["gate_pass_count"],
        counts["yearly"]["2023"]["gate_fail_count"],
    ) == (3, 1)
    assert (
        counts["yearly"]["2024"]["gate_pass_count"],
        counts["yearly"]["2024"]["gate_fail_count"],
    ) == (3, 0)
    first = _regime_rows()[0]
    assert first["sma_history_session_count"] == "141"
    assert first["market_sma200"] == ""
    assert first["gate_pass"] == ""
    assert "INSUFFICIENT_SMA200_PREHISTORY" in first["data_quality_flags"]


def test_required_structural_dataset_fields_and_no_future_rows() -> None:
    rows = _regime_rows()
    assert set(REGIME_DATASET_FIELDS) <= set(rows[0])
    assert DEVELOPMENT_START.isoformat() == "2022-01-01"
    assert DEVELOPMENT_END.isoformat() == "2024-12-31"
    assert all(
        DEVELOPMENT_START
        <= date.fromisoformat(row["rebalance_date"])
        <= DEVELOPMENT_END
        for row in rows
    )
    assert all(row["performance_evaluated"] == "False" for row in rows)


def test_pass_holdings_equal_control_and_fail_dates_are_cash_only() -> None:
    rows = _regime_rows()
    passed = [row for row in rows if row["gate_pass"] == "True"]
    failed = [row for row in rows if row["gate_pass"] == "False"]
    assert len(passed) == 8
    assert all(
        row["holdings_identical_on_pass"] == "True"
        and row["control_holdings_hash"] == row["treatment_holdings_hash"]
        and row["control_selected_count"] == row["treatment_selected_count"]
        for row in passed
    )
    assert len(failed) == 2
    assert all(
        row["treatment_selected_count"] == "0"
        and row["treatment_zero_holdings_on_fail"] == "True"
        and row["treatment_cash_state"]
        == "CASH_ONLY_UNTIL_NEXT_SCHEDULED_REBALANCE"
        for row in failed
    )
    assert all(row["mid_quarter_change_allowed"] == "False" for row in rows)


def test_regime_and_accounting_pilots_are_structural_only() -> None:
    pilots = read_csv(REPORT_ROOT / REPORT_NAMES[4])
    by_id = {row["case_id"]: row for row in pilots}
    assert len(pilots) == 13
    assert by_id["REGIME_A_ABOVE_SMA200_PARTICIPATE"]["passed"] == "True"
    assert by_id["REGIME_B_BELOW_SMA200_CASH"]["passed"] == "True"
    assert by_id["REGIME_C_EQUALITY_CASH"]["passed"] == "True"
    assert by_id["REGIME_D_EARLY_2022_CAUSAL_SMA200"]["status"] == (
        "FAIL_INSUFFICIENT_PREHISTORY"
    )
    assert by_id["REGIME_F_SAME_HOLDINGS_ON_PASS"]["observed"] == "8"
    assert by_id["REGIME_G_ZERO_HOLDINGS_ON_FAIL"]["observed"] == "2"
    assert by_id["REGIME_H_NO_MID_QUARTER_CHANGE"]["passed"] == "True"
    accounting = accounting_pilot_document()
    assert accounting["all_passed"] is True
    assert accounting["cash_only_holding_count"] == 0
    assert accounting["buy_cost_inr"] > 0
    assert accounting["sell_cost_inr"] > 0
    assert accounting["participating_equity_inr"] == (
        STARTING_CAPITAL - accounting["buy_cost_inr"]
    )


def test_success_criteria_are_frozen_before_performance() -> None:
    criteria = success_criteria_document()
    standard = criteria["standard_treatment_criteria"]
    quality = criteria["quality_dimensions"]
    assert standard["A_RETURN_PRESERVATION"]["control_cagr_multiple"] == "0.85"
    assert standard["B_DRAWDOWN_IMPROVEMENT"][
        "maximum_control_drawdown_multiple"
    ] == "0.85"
    assert standard["C_ABSOLUTE_PROFITABILITY"]["net_cagr_threshold"] == "0"
    assert standard["D_TEMPORAL_SUPPORT"][
        "nonnegative_development_years_minimum"
    ] == 2
    assert standard["E_COST_EFFICIENCY"]["exception"] == (
        "DOCUMENTED_IMPLEMENTATION_ARTIFACT_ONLY"
    )
    assert standard["F_SAMPLE_ADEQUACY"] == {
        "pass_minimum_invested_quarters": 6,
        "limited_sample_minimum": 4,
        "limited_sample_maximum": 5,
        "fatal_sample_failure_below": 4,
    }
    assert standard["G_ACCOUNTING_DATA_INTEGRITY"][
        "cash_reconciliation_violations"
    ] == 0
    assert list(quality) == [
        "H_LOWER_VOLATILITY",
        "I_BETTER_SHARPE_LIKE",
        "J_FEWER_NEGATIVE_QUARTERS",
        "K_BETTER_WORST_QUARTER",
    ]
    strong = criteria["evidence_classification"]["STRONGLY_SUPPORTED"]
    assert strong["quality_dimensions_minimum"] == 2
    assert strong["minimum_relative_drawdown_reduction"] == "0.20"
    assert strong["minimum_control_cagr_multiple"] == "0.90"
    assert criteria["family_result_assigned"] is None
    assert criteria["performance_evaluated"] is False


def test_governance_v2_full_checklist_is_present_and_passes() -> None:
    verified = verify_governance_v2(REPO_ROOT)
    assert verified["status"] == "VERIFIED"
    assert all(verified["checks"].values())
    preregistration = _json(
        FAMILY_ROOT / "registry/regime_g_001_preregistration_v1.json"
    )
    assert len(GOVERNANCE_CHECKLIST) == 14
    assert all(item in preregistration for item in GOVERNANCE_CHECKLIST)
    report = read_csv(REPORT_ROOT / REPORT_NAMES[5])
    assert len(report) == 14
    assert all(row["status"] == "PASS" for row in report)
    assert all(
        row["governance_policy"] == "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
        for row in report
    )


def test_data_readiness_and_architecture_result_are_honest() -> None:
    summary = _summary()
    assert summary["classifications"]["FAMILY_G_DATA_READINESS"] == (
        "READY_WITH_LIMITATIONS"
    )
    assert summary["classifications"]["FAMILY_G_ARCHITECTURE_RESULT"] == (
        "METHODOLOGY_FIX_REQUIRED"
    )
    readiness = {
        row["check"]: row for row in read_csv(REPORT_ROOT / REPORT_NAMES[2])
    }
    assert readiness["CAUSAL_SMA200_ALL_REBALANCES"]["status"] == "LIMITATION"
    assert readiness["CAUSAL_SMA200_ALL_REBALANCES"]["observed"] == "10/11"
    assert readiness["GATE_PASS_SAMPLE_ADEQUACY_STRUCTURE"]["observed"] == "8"


def test_no_vix_breadth_performance_validation_or_strategy_v2() -> None:
    summary = _summary()
    governance = summary["governance"]
    assert governance["development_performance_run"] is False
    assert governance["vix_used"] is False
    assert governance["breadth_used"] is False
    assert governance["alternate_sma_tested"] is False
    assert governance["second_treatment_created"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    treatment = _json(FAMILY_ROOT / "registry/regime_g_001_parameters_v1.json")
    parameters = treatment["parameters"]
    assert parameters["volatility_filter"] is None
    assert parameters["breadth_filter"] is None
    assert parameters["second_condition"] is None
    assert parameters["cash_return_percent"] == "0"
    assert CASH_RETURN == Decimal("0")
    source_path = (
        REPO_ROOT
        / "backend/app/research/strategy/family_g_regime_volatility.py"
    )
    source = source_path.read_text(encoding="utf-8")
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("backtest" in module for module in imports)
    assert "simulate_strategy(" not in source


def test_previous_families_and_baselines_are_immutable() -> None:
    summary = _summary()
    snapshot = previous_family_snapshot(REPO_ROOT)
    immutability = summary["immutability"]
    assert immutability["previous_family_snapshot_before"] == snapshot[
        "snapshot_hash"
    ]
    assert immutability["previous_family_snapshot_after"] == snapshot[
        "snapshot_hash"
    ]
    for field in (
        "previous_families_unchanged",
        "strategy_v1_unchanged",
        "cap4_unchanged",
        "family_a_unchanged",
        "family_b_unchanged",
        "family_c_unchanged",
        "family_d_unchanged",
        "family_e_unchanged",
        "family_f_unchanged",
        "daily_history_prehistory_v2_unchanged",
    ):
        assert immutability[field] is True


def test_manifest_reports_documentation_storage_and_security() -> None:
    manifest_path = (
        FAMILY_ROOT / "manifests/family_g_architecture_manifest_v1.json"
    )
    manifest = _json(manifest_path)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_g_architecture_manifest_hash"
    }
    assert manifest["family_g_architecture_manifest_hash"] == canonical_hash(body)
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert (
        REPO_ROOT / "docs/strategy-family-g-regime-volatility-v1.md"
    ).is_file()
    for directory in ("registry", "regime", "pilots", "governance", "manifests"):
        assert (FAMILY_ROOT / directory).is_dir()
    security = _summary()["security"]
    assert security == {
        "credentials_added": 0,
        "network_accessed": False,
        "external_writes": 0,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
    }


def test_roadmap_has_exact_live_family_states() -> None:
    roadmap = (
        REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md"
    ).read_text(encoding="utf-8")
    expected = _summary()["roadmap"]
    labels = {
        "family_A": ("Family A", "Medium-Term Momentum"),
        "family_B": ("Family B", "Relative + Absolute Momentum"),
        "family_C": ("Family C", "Breakout Continuation"),
        "family_D": ("Family D", "Opening Range / Stocks-in-Play"),
        "family_E": ("Family E", "Pullback / Reclaim"),
        "family_F": ("Family F", "Catalyst Momentum"),
        "family_G": ("Family G", "Regime / Volatility"),
    }
    for key, status in expected.items():
        family, direction = labels[key]
        assert f"| {family} | {direction} | {status} |" in roadmap


def test_builder_reconstructs_same_structural_rows_without_outcomes() -> None:
    rows, holdings = build_regime_dataset(REPO_ROOT)
    assert len(rows) == len(holdings) == 11
    assert sum(row["gate_pass"] is True for row in rows) == 8
    assert sum(row["gate_pass"] is False for row in rows) == 2
    assert sum(row["gate_pass"] is None for row in rows) == 1
    assert all(row["performance_evaluated"] is False for row in rows)

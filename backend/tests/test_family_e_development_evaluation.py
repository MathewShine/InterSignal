from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.research.strategy.family_a_momentum import (
    estimate_order_cost,
    file_sha256,
    read_csv,
)
from app.research.strategy.family_e_development_evaluation import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_ARCHITECTURE_MANIFEST_HASH,
    CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH,
    REPORT_NAMES,
    SIGNAL_QUALITY_MODE,
    admission_overlap,
    cohort_summary,
    evaluate_control,
    evaluate_treatment,
    map_family_result,
    next_research_stage,
    reproduce_structural_counts,
    structure_filter_attribution,
    verify_freeze_gate,
)
from app.research.strategy.family_e_pullback_reclaim import (
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_E001_PARAMETER_HASH,
    EXPECTED_E001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CLOSURE_HASH,
    EXPECTED_FAMILY_E_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    MAX_CONCURRENT_POSITIONS,
    TREATMENT_ID,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_ROOT = REPO_ROOT / "data/research/strategy_families/family_e/v1"
EVALUATION_ROOT = FAMILY_ROOT / "development_evaluation"
SUMMARY_PATH = REPO_ROOT / "data/reports/family_e_dev_v1_summary.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _metrics(experiment_id: str) -> dict:
    return _summary()["results"][experiment_id]["portfolio_metrics"]


def test_command_identity_and_all_freeze_hashes() -> None:
    summary = _summary()
    gate = verify_freeze_gate(REPO_ROOT)
    assert COMMAND_VERSION == "FAMILY_E_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "PULLBACK_RECLAIM_DEVELOPMENT_V1"
    assert summary["command_version"] == COMMAND_VERSION
    assert gate["status"] == "VERIFIED"
    assert all(gate["checks"].values())
    assert summary["freeze_gate"] == {
        "status": "VERIFIED",
        "checks": gate["checks"],
        "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
        "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "pbr_e_001_parameter_hash": EXPECTED_E001_PARAMETER_HASH,
        "pbr_e_001_preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
        "family_e_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
    }


def test_architecture_manifest_and_command_01_artifacts_are_immutable() -> None:
    manifest = _json(FAMILY_ROOT / "manifests/family_e_architecture_manifest_v1.json")
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_e_architecture_manifest_hash"
    }
    assert canonical_hash(body) == manifest["family_e_architecture_manifest_hash"]
    assert (
        manifest["family_e_architecture_manifest_hash"]
        == CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH
    )
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )
    assert _summary()["immutability"]["command_01_unchanged"] is True


def test_development_partition_and_terminal_paths_never_access_2025() -> None:
    summary = _summary()
    assert DEVELOPMENT_START == date(2022, 1, 1)
    assert DEVELOPMENT_END == date(2024, 12, 31)
    assert summary["development_partition"]["pre_2022_performance_included"] is False
    assert summary["development_partition"]["post_2024_data_accessed"] is False
    assert summary["development_partition"]["validation_accessed"] is False
    for experiment_id in (CONTROL_ID, TREATMENT_ID):
        metrics = _metrics(experiment_id)
        expected_structural = 10754 if experiment_id == CONTROL_ID else 8343
        expected_terminal = 119 if experiment_id == CONTROL_ID else 92
        assert metrics["terminal_path_unavailable"] == expected_terminal
        assert (
            metrics["entry_ready_signals"]
            + metrics["terminal_path_unavailable"]
            + metrics["invalid_stop_rejections"]
            == expected_structural
        )
        positions = read_csv(
            EVALUATION_ROOT
            / "positions"
            / f"{experiment_id.lower().replace('-', '_')}_portfolio_positions_v1.csv"
        )
        assert positions
        assert all(row["exit_date"] <= "2024-12-31" for row in positions)


def test_exact_structural_reproduction_and_treatment_subset() -> None:
    structural = _summary()["structural_reproduction"]
    assert structural == {
        "status": "VERIFIED",
        "eligible_universe_rows": 199915,
        "trend_pass_rows": 84980,
        "pullback_touch_rows": 39150,
        "control_signals": 10754,
        "e001_signals": 8343,
        "treatment_filter_removals": 2411,
        "treatment_subset_violations": 0,
    }
    rows = read_csv(FAMILY_ROOT / "signals/family_e_signal_dataset_v1.csv")
    assert reproduce_structural_counts(rows)["status"] == "VERIFIED"


def test_portfolio_mechanics_costs_stops_hold_and_risk() -> None:
    for experiment_id in (CONTROL_ID, TREATMENT_ID):
        path = (
            EVALUATION_ROOT
            / "positions"
            / f"{experiment_id.lower().replace('-', '_')}_portfolio_positions_v1.csv"
        )
        positions = read_csv(path)
        assert all(row["formation_date"] < row["entry_date"] <= row["exit_date"] for row in positions)
        assert all(Decimal(row["entry_price"]) > Decimal(row["stop_price"]) for row in positions)
        assert all(int(row["shares"]) > 0 for row in positions)
        assert all(Decimal(row["planned_risk"]) <= Decimal(row["allowed_risk"]) for row in positions)
        assert all(row["exit_reason"] in {"STOP_EXIT", "GAP_THROUGH_STOP", "TIME_EXIT"} for row in positions)
        assert all(row["exit_category"] != "TIME_EXIT" or int(row["holding_sessions"]) == 10 for row in positions)
        for row in positions[:25]:
            notional = Decimal(row["entry_notional"])
            exit_notional = Decimal(row["exit_notional"])
            assert Decimal(row["buy_cost"]) == estimate_order_cost(
                "BUY", date.fromisoformat(row["entry_date"]), notional
            )["total_cost"]
            assert Decimal(row["sell_cost"]) == estimate_order_cost(
                "SELL", date.fromisoformat(row["exit_date"]), exit_notional
            )["total_cost"]


def test_capacity_max_ten_one_symbol_and_accounting() -> None:
    for experiment_id in (CONTROL_ID, TREATMENT_ID):
        metrics = _metrics(experiment_id)
        assert metrics["maximum_concurrent_positions"] <= MAX_CONCURRENT_POSITIONS == 10
        assert metrics["CAPACITY_CONSTRAINT_MATERIAL"] == "YES"
        assert Decimal(metrics["capacity_rejection_rate"]) > Decimal("0.25")
        integrity = metrics["accounting_data_integrity"]
        assert integrity["status"] == "PASS"
        assert all(integrity["checks"].values())
        ledger = read_csv(
            EVALUATION_ROOT
            / "ledgers"
            / f"{experiment_id.lower().replace('-', '_')}_portfolio_ledger_v1.csv"
        )
        assert all(int(row["open_positions"]) <= 10 for row in ledger)
        assert all(Decimal(row["net_cash"]) >= 0 for row in ledger)


def test_position_and_portfolio_metrics_are_complete() -> None:
    required = {
        "closed_positions", "wins", "losses", "flat", "position_win_rate",
        "HIGH_WIN_RATE_FLAG", "average_winner", "average_loser", "median_return",
        "gross_expectancy", "net_expectancy", "gross_profit_factor",
        "net_profit_factor", "median_MFE", "median_MAE", "p25_MFE", "p75_MFE",
        "p25_MAE", "p75_MAE", "median_stop_distance_pct", "median_R_multiple",
        "stop_exit_count", "time_exit_count", "average_holding_sessions",
        "starting_equity", "gross_ending_equity", "net_ending_equity",
        "gross_total_return", "net_total_return", "gross_CAGR", "net_CAGR",
        "max_drawdown", "annualized_volatility", "sharpe_like_metric",
        "positive_month_rate", "yearly_returns", "turnover", "transaction_costs",
        "average_cash", "average_concurrent_positions", "maximum_concurrent_positions",
        "capacity_rejected_signals", "capacity_rejection_rate",
    }
    for experiment_id in (CONTROL_ID, TREATMENT_ID):
        metrics = _metrics(experiment_id)
        assert required <= set(metrics)
        assert metrics["wins"] + metrics["losses"] + metrics["flat"] == metrics["closed_positions"]
        assert set(metrics["yearly_returns"]) == {"2022", "2023", "2024"}


def _criteria_fixture() -> dict:
    return {
        "net_expectancy": Decimal("0.01"),
        "net_profit_factor": Decimal("1.30"),
        "net_CAGR": Decimal("0.10"),
        "max_drawdown": Decimal("0.10"),
        "yearly_returns": {"2022": Decimal("0.1"), "2023": Decimal("0.1"), "2024": Decimal("0.1")},
        "closed_positions": 200,
        "position_win_rate": Decimal("0.50"),
        "turnover": Decimal("10"),
        "normalized_cost_drag": Decimal("0.02"),
        "accounting_data_integrity": {"status": "PASS"},
    }


def test_control_and_treatment_criteria_and_classification_logic() -> None:
    control = _criteria_fixture()
    control_result = evaluate_control(control)
    assert control_result["CONTROL_VIABLE"] is True
    assert control_result["CONTROL_FAILED"] is False
    treatment = deepcopy(control)
    treatment.update(
        {
            "net_expectancy": Decimal("0.012"),
            "net_profit_factor": Decimal("1.36"),
            "net_CAGR": Decimal("0.09"),
            "max_drawdown": Decimal("0.08"),
            "position_win_rate": Decimal("0.56"),
            "closed_positions": 160,
            "normalized_cost_drag": Decimal("0.02"),
        }
    )
    result = evaluate_treatment(treatment, control)
    assert all(result["criteria_A_G"].values())
    assert all(result["quality_H_K"].values())
    assert result["classification"] == "STRONGLY_SUPPORTED"
    assert map_family_result(control_result, result["classification"]) == "STRONG_SUPPORT"
    assert next_research_stage(
        treatment_result=result["classification"],
        family_result="STRONG_SUPPORT",
        attribution_label="CLEAR_POSITIVE",
    ) == "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"


def test_actual_criteria_h_k_and_family_decisions_are_frozen() -> None:
    summary = _summary()
    control = summary["results"][CONTROL_ID]["evaluation"]
    treatment = summary["results"][TREATMENT_ID]["evaluation"]
    assert set(control["criteria_A_G"]) == {
        "A_NET_EXPECTANCY", "B_NET_PROFIT_FACTOR", "C_NET_CAGR",
        "D_MAX_DRAWDOWN_MAGNITUDE", "E_NONNEGATIVE_DEVELOPMENT_YEARS",
        "F_CLOSED_POSITIONS", "G_ACCOUNTING_DATA_INTEGRITY",
    }
    assert set(treatment["criteria_A_G"]) == {
        "A_RETURN_PRESERVATION", "B_PROFITABILITY", "C_DRAWDOWN_NON_DEGRADATION",
        "D_TEMPORAL_SUPPORT", "E_COST_EFFICIENCY", "F_SAMPLE_ADEQUACY",
        "G_ACCOUNTING_DATA_INTEGRITY",
    }
    assert set(treatment["quality_H_K"]) == {
        "H_WIN_RATE_IMPROVEMENT", "I_PROFIT_FACTOR_IMPROVEMENT",
        "J_EXPECTANCY_IMPROVEMENT", "K_MATERIAL_DRAWDOWN_IMPROVEMENT",
    }
    assert summary["classifications"]["PBR_E_001_DEVELOPMENT_RESULT"] in {
        "STRONGLY_SUPPORTED", "SUPPORTED", "PARTIALLY_SUPPORTED", "FAILED", "INCONCLUSIVE"
    }
    assert summary["classifications"]["FAMILY_E_DEVELOPMENT_RESULT"] in {
        "STRONG_SUPPORT", "SUPPORT", "MIXED", "WEAK", "FAILED", "INCONCLUSIVE"
    }


def test_signal_quality_cohorts_and_structure_attribution() -> None:
    summary = _summary()
    attribution = summary["attribution"]
    assert attribution["filtered_out"]["structural_signal_count"] == 2411
    assert attribution["retained"]["structural_signal_count"] == 8343
    assert attribution["filtered_out"]["mode"] == SIGNAL_QUALITY_MODE
    assert attribution["retained"]["mode"] == SIGNAL_QUALITY_MODE
    assert attribution["structure_filter"]["E001_STRUCTURE_FILTER_SIGNAL_QUALITY"] in {
        "CLEAR_POSITIVE", "MODEST_POSITIVE", "NO_MEANINGFUL_DIFFERENCE",
        "NEGATIVE", "MIXED", "INCONCLUSIVE",
    }
    sample = read_csv(
        EVALUATION_ROOT / "positions/control_e_000_signal_quality_cohort_v1.csv"
    )
    assert sample and all(row["mode"] == SIGNAL_QUALITY_MODE for row in sample)
    assert all(row["simultaneously_deployable"] == "False" for row in sample)


def test_cohort_and_admission_overlap_helpers() -> None:
    positions = [
        {
            "formation_date": "2022-01-01", "symbol": "A",
            "net_return_pct": Decimal("0.1"), "net_pnl": Decimal("10"),
            "MFE_pct": Decimal("0.2"), "MAE_pct": Decimal("-0.1"),
        }
    ]
    cohort = cohort_summary(positions, structural_count=1, label="TEST")
    assert cohort["complete_event_count"] == 1
    assert cohort["win_rate"] == Decimal("1")
    positive = structure_filter_attribution(cohort, {
        **cohort,
        "win_rate": Decimal("0"),
        "net_expectancy": Decimal("-0.1"),
        "net_profit_factor": Decimal("0.5"),
    })
    assert positive["E001_STRUCTURE_FILTER_SIGNAL_QUALITY"] == "CLEAR_POSITIVE"
    overlap = admission_overlap(
        {"positions": [{"formation_date": "2022-01-01", "symbol": "A"}]},
        {"positions": [{"formation_date": "2022-01-01", "symbol": "B"}]},
    )
    assert overlap["control_only_admitted"] == 1
    assert overlap["treatment_only_admitted"] == 1
    assert overlap["jaccard"] == 0


def test_exit_capacity_and_all_diagnostic_reports_exist() -> None:
    reports = REPO_ROOT / "data/reports"
    assert len(REPORT_NAMES) == 16
    assert all((reports / name).is_file() for name in REPORT_NAMES)
    assert len(read_csv(reports / REPORT_NAMES[4])) == 6
    assert len(read_csv(reports / REPORT_NAMES[7])) == 4
    assert len(read_csv(reports / REPORT_NAMES[8])) == 2
    assert len(read_csv(reports / REPORT_NAMES[9])) == 10
    assert len(read_csv(reports / REPORT_NAMES[10])) == 10
    assert len(read_csv(reports / REPORT_NAMES[11])) == 10
    assert len(read_csv(reports / REPORT_NAMES[13])) == 2
    assert len(read_csv(reports / REPORT_NAMES[14])) == 8


def test_result_and_registry_hashes_are_canonical_and_status_updated() -> None:
    summary = _summary()
    control = summary["results"][CONTROL_ID]
    treatment = summary["results"][TREATMENT_ID]
    registry = summary["registry"]
    assert canonical_hash({key: value for key, value in control.items() if key != "control_e_000_result_hash"}) == control["control_e_000_result_hash"]
    assert canonical_hash({key: value for key, value in treatment.items() if key != "pbr_e_001_result_hash"}) == treatment["pbr_e_001_result_hash"]
    assert canonical_hash({key: value for key, value in registry.items() if key != "family_e_development_registry_hash"}) == registry["family_e_development_registry_hash"]
    experiment = registry["experiments"][0]
    assert experiment["status_before"] == "PREREGISTERED"
    assert experiment["status"] == "DEVELOPMENT_EVALUATED"
    assert experiment["parameter_hash"] == EXPECTED_E001_PARAMETER_HASH
    assert experiment["preregistration_hash"] == EXPECTED_E001_PREREGISTRATION_HASH


def test_development_manifest_artifacts_and_summary_hash() -> None:
    manifest = _json(
        EVALUATION_ROOT
        / "manifests/family_e_development_evaluation_manifest_v1.json"
    )
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_e_development_evaluation_manifest_hash"
    }
    assert canonical_hash(body) == manifest["family_e_development_evaluation_manifest_hash"]
    assert file_sha256(SUMMARY_PATH) == manifest["summary_hash"]
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_no_tuning_validation_v2_family_f_or_external_effects() -> None:
    summary = _summary()
    governance = summary["governance"]
    assert all(
        governance[field] is False
        for field in (
            "validation_accessed", "strategy_v2_created", "family_f_started",
            "second_treatment_created", "alternate_ma_tested",
            "alternate_pullback_tested", "alternate_reclaim_tested",
            "volume_filter_added", "target_added", "trailing_stop_added",
            "holding_period_changed", "risk_changed", "capacity_changed",
        )
    )
    assert summary["immutability"]["parameter_mutations"] == 0
    assert summary["immutability"]["success_criteria_mutations"] == 0
    assert all(value == 0 for value in summary["security"].values())
    assert (REPO_ROOT / "docs/strategy-family-e-development-evaluation-v1.md").is_file()

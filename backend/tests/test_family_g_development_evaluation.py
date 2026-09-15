from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_g_benchmark_prehistory import (
    EXPECTED_NORMALIZED_HASH,
    EXPECTED_OVERLAP_HASH,
    EXPECTED_POST_READINESS_HASH,
    EXPECTED_RAW_HASH,
    EXPECTED_REGIME_MATRIX_HASH,
    EXPECTED_REMEDIATION_CONFIG_HASH,
    FROZEN_REBALANCE_DATES,
)
from app.research.strategy.family_g_development_evaluation import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTROL_ID,
    EXPECTED_PREHISTORY_MANIFEST_HASH,
    MANIFEST_VERSION,
    REGISTRY_VERSION,
    REPORT_NAMES,
    TREATMENT_ID,
    evaluate_criteria,
    family_result,
    next_stage,
    verify_freeze_gate,
)
from app.research.strategy.family_g_regime_volatility import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_F_CLOSURE_HASH,
    EXPECTED_FAMILY_G_CONFIG_HASH,
    EXPECTED_GOVERNANCE_V2_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPECTED_TREATMENT_PARAMETER_HASH,
    EXPECTED_TREATMENT_PREREGISTRATION_HASH,
)


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "data/reports"
OUTPUT_ROOT = (
    ROOT
    / "data/research/strategy_families/family_g/v1/development_evaluation"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict:
    return load_json(REPORT_ROOT / "family_g_dev_v1_summary.json")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return load_json(
        OUTPUT_ROOT
        / "manifests/family_g_development_evaluation_manifest_v1.json"
    )


def test_command_identity() -> None:
    assert COMMAND_VERSION == "FAMILY_G_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "QUARTERLY_REGIME_PARTICIPATION_DEVELOPMENT_V1"
    assert MANIFEST_VERSION == "FAMILY_G_DEVELOPMENT_EVALUATION_MANIFEST_V1"
    assert REGISTRY_VERSION == "FAMILY_G_DEVELOPMENT_REGISTRY_V1"


def test_freeze_gate_verifies_all_inputs() -> None:
    result = verify_freeze_gate(ROOT)
    assert result["status"] == "VERIFIED"
    assert all(result["checks"].values())
    assert result["family_g_hashes"] == {
        "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
        "control_g_000_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "regime_g_001_parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
        "regime_g_001_preregistration_hash": (
            EXPECTED_TREATMENT_PREREGISTRATION_HASH
        ),
        "family_g_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    assert result["governance_policy_hash"] == EXPECTED_GOVERNANCE_V2_HASH
    assert result["family_f_closure_hash"] == EXPECTED_FAMILY_F_CLOSURE_HASH


def test_command_02_hashes_are_exact(summary: dict) -> None:
    expected = {
        "family_g_prehistory_remediation_config_hash": (
            EXPECTED_REMEDIATION_CONFIG_HASH
        ),
        "nifty500_prehistory_raw_hash": EXPECTED_RAW_HASH,
        "nifty500_prehistory_normalized_hash": EXPECTED_NORMALIZED_HASH,
        "nifty500_overlap_reconciliation_hash": EXPECTED_OVERLAP_HASH,
        "family_g_regime_matrix_hash": EXPECTED_REGIME_MATRIX_HASH,
        "family_g_post_remediation_readiness_hash": (
            EXPECTED_POST_READINESS_HASH
        ),
    }
    assert summary["freeze_verification"]["prehistory_hashes"] == expected
    assert (
        summary["freeze_verification"]["prehistory_manifest_hash"]
        == EXPECTED_PREHISTORY_MANIFEST_HASH
    )


def test_development_partition_is_exact_and_validation_is_absent(
    summary: dict,
) -> None:
    window = summary["development_window"]
    assert window == {
        "start": "2022-01-01",
        "end": "2024-12-31",
        "session_count": 743,
        "development_only": True,
        "validation_accessed": False,
        "validation_rows_loaded": 0,
    }
    treatment_daily = read_csv(OUTPUT_ROOT / "regime_g_001/daily.csv")
    assert min(row["date"] for row in treatment_daily) >= "2022-01-01"
    assert max(row["date"] for row in treatment_daily) == "2024-12-31"
    assert not any(row["date"] >= "2025-01-01" for row in treatment_daily)


def test_exact_rebalance_dates_and_gate_states() -> None:
    matrix = load_json(
        ROOT
        / "data/research/strategy_families/family_g/v1/benchmark_prehistory/"
        "regime_matrix/family_g_regime_matrix_v1.json"
    )
    rows = matrix["rows"]
    assert tuple(row["rebalance_date"] for row in rows) == FROZEN_REBALANCE_DATES
    assert [row["gate_pass"] for row in rows] == [
        True,
        False,
        True,
        True,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
    ]
    assert matrix["family_g_regime_matrix_hash"] == EXPECTED_REGIME_MATRIX_HASH


def test_control_reproduction_is_within_frozen_tolerance(summary: dict) -> None:
    reproduction = summary["control"]["reproduction"]
    assert reproduction["status"] == "PASS"
    assert all(reproduction["checks"].values())
    metrics = summary["control"]["metrics"]
    assert Decimal(metrics["starting_equity"]) == Decimal("500000")
    assert Decimal(metrics["net_ending_equity"]) == Decimal("955331.6799")
    assert Decimal(metrics["net_total_return_pct"]) == Decimal("91.0663359800")
    assert Decimal(metrics["net_cagr_pct"]) == Decimal("24.105850672292473")
    assert Decimal(metrics["net_max_drawdown_pct"]) == Decimal(
        "-22.92216992201015671886716806"
    )


def test_family_a_holdings_identity_matches_all_rebalances(summary: dict) -> None:
    integrity = summary["control"]["reproduction"]["holdings_integrity"]
    assert integrity["status"] == "PASS"
    assert integrity["matched_rebalances"] == integrity["total_rebalances"] == 11
    assert all(row["matches"] for row in integrity["checks"])


def test_pass_date_selected_symbol_jaccard_is_one(summary: dict) -> None:
    rows = summary["attribution"]["pass_date_identity"]
    passes = [row for row in rows if row["gate_pass"]]
    assert len(passes) == 9
    assert all(Decimal(row["jaccard_before_sizing"]) == 1 for row in passes)
    assert all(Decimal(row["realized_symbol_jaccard"]) == 1 for row in passes)
    assert all(not row["realized_symbol_divergence"] for row in passes)
    assert all(row["input_holdings_identical"] for row in passes)


def test_fail_dates_are_cash_only_without_midquarter_reentry(summary: dict) -> None:
    utilization = summary["attribution"]["cash_utilization"]
    assert len(utilization["gate_fail_durations"]) == 2
    assert [row["cash_sessions"] for row in utilization["gate_fail_durations"]] == [63, 60]
    assert all(
        row["all_sessions_fully_cash"]
        for row in utilization["gate_fail_durations"]
    )
    accounting = load_json(
        OUTPUT_ROOT / "regime_g_001/regime_g_001_result_v1.json"
    )["accounting"]
    assert accounting["checks"]["no_mid_quarter_change"] is True
    assert accounting["checks"]["fail_date_cash_state"] is True


def test_whole_share_cost_and_accounting_semantics(summary: dict) -> None:
    treatment = load_json(
        OUTPUT_ROOT / "regime_g_001/regime_g_001_result_v1.json"
    )
    checks = treatment["accounting"]["checks"]
    assert checks["whole_share_mechanics"] is True
    assert checks["cash_reconciliation"] is True
    assert checks["equity_reconciliation"] is True
    assert checks["cost_reconciliation"] is True
    holdings = read_csv(OUTPUT_ROOT / "regime_g_001/holdings.csv")
    assert holdings
    assert all(Decimal(row["quantity"]) == int(row["quantity"]) > 0 for row in holdings)
    assert summary["treatment"]["metrics"]["cost_model_status"] == "FULL_FROZEN_COST_MODEL"


def test_treatment_gate_counts_and_fraction(summary: dict) -> None:
    treatment = summary["treatment"]
    assert treatment["gate_pass_count"] == treatment["invested_quarter_count"] == 9
    assert treatment["gate_fail_count"] == treatment["cash_quarter_count"] == 2
    assert Decimal(treatment["fraction_invested"]) == Decimal(9) / Decimal(11)


def test_criteria_a_through_g_are_frozen(summary: dict) -> None:
    rows = {row["criterion"]: row["result"] for row in summary["criteria_rows"]}
    assert {key: rows[key] for key in "ABCDEFG"} == {
        "A": "FAIL",
        "B": "FAIL",
        "C": "PASS",
        "D": "PASS",
        "E": "PASS",
        "F": "PASS",
        "G": "PASS",
    }
    assert summary["criteria"]["primary_pass_count"] == 5
    assert summary["criteria"]["fatal_failure"] is False


def test_quality_h_through_k_are_frozen(summary: dict) -> None:
    rows = {row["criterion"]: row["result"] for row in summary["criteria_rows"]}
    assert {key: rows[key] for key in "HIJK"} == {
        "H": "PASS",
        "I": "FAIL",
        "J": "FAIL",
        "K": "FAIL",
    }
    assert summary["criteria"]["quality_pass_count"] == 1


def test_treatment_and_family_classification(summary: dict) -> None:
    assert (
        summary["classifications"]["REGIME_G_001_DEVELOPMENT_RESULT"]
        == "PARTIALLY_SUPPORTED"
    )
    assert summary["classifications"]["FAMILY_G_DEVELOPMENT_RESULT"] == "MIXED"
    assert summary["classifications"]["FAMILY_G_NEXT_RESEARCH_STAGE"] == "PAUSE_FAMILY_G"
    assert family_result("PASS", "PARTIALLY_SUPPORTED") == "MIXED"
    assert next_stage("PARTIALLY_SUPPORTED")[0] == "PAUSE_FAMILY_G"


def test_cash_quarter_attribution_is_descriptive_only(summary: dict) -> None:
    rows = summary["attribution"]["cash_quarters"]
    assert [(row["rebalance_date"], row["classification"]) for row in rows] == [
        ("2022-06-30", "MISSED_GAIN"),
        ("2023-03-31", "MISSED_GAIN"),
    ]
    assert all(Decimal(row["control_return_pct"]) > 0 for row in rows)
    assert all(Decimal(row["treatment_return_pct"]) == 0 for row in rows)


def test_normalized_quarter_diagnostic_is_gate_only(summary: dict) -> None:
    rows = summary["attribution"]["path_effect"]["rows"]
    assert len(rows) == 11
    for row in rows:
        if row["gate_state"] == "PASS":
            assert Decimal(row["normalized_treatment_return_pct"]) == Decimal(
                row["control_return_pct"]
            )
            assert Decimal(row["direct_gate_effect_pp"]) == 0
        else:
            assert Decimal(row["normalized_treatment_return_pct"]) == 0
            assert Decimal(row["direct_gate_effect_pp"]) == -Decimal(
                row["control_return_pct"]
            )


def test_path_effect_separation_reconciles(summary: dict) -> None:
    path = summary["attribution"]["path_effect"]
    actual_gap = Decimal(path["actual_treatment_minus_control_rupees"])
    assert actual_gap == (
        Decimal(path["direct_gate_effect_rupees"])
        + Decimal(path["capital_path_effect_rupees"])
    )
    assert Decimal(path["direct_gate_effect_rupees"]) < 0


def test_drawdown_attribution(summary: dict) -> None:
    control, treatment = summary["attribution"]["drawdown"]
    assert control["peak_date"] == "2022-04-18"
    assert control["trough_date"] == "2022-06-20"
    assert control["gate_fail_overlap_peak_to_trough"] is False
    assert control["gate_fail_overlap_full_episode"] is True
    assert treatment["peak_date"] == "2022-04-18"
    assert treatment["trough_date"] == "2023-03-28"
    assert treatment["gate_fail_overlap_peak_to_trough"] is True
    assert treatment["gate_fail_overlap_full_episode"] is True
    assert Decimal(summary["criteria"]["relative_drawdown_improvement_pct"]) < 0


def test_yearly_attribution_has_no_validation_year(summary: dict) -> None:
    rows = summary["attribution"]["yearly"]
    assert [row["year"] for row in rows] == [2022, 2023, 2024]
    assert [(row["invested_rebalance_count"], row["cash_rebalance_count"]) for row in rows] == [(3, 1), (3, 1), (3, 0)]


def test_cost_and_turnover_attribution(summary: dict) -> None:
    attribution = summary["attribution"]
    assert Decimal(attribution["cost_reduction_rupees"]) == Decimal("3659.37")
    assert Decimal(attribution["cost_reduction_pct"]) > Decimal("20")
    assert Decimal(attribution["turnover_reduction_x"]) > 0
    assert Decimal(attribution["turnover_reduction_pct"]) > 0


def test_result_hashes_are_canonical(summary: dict) -> None:
    control = load_json(OUTPUT_ROOT / "control/control_g_000_result_v1.json")
    treatment = load_json(
        OUTPUT_ROOT / "regime_g_001/regime_g_001_result_v1.json"
    )
    registry = load_json(
        OUTPUT_ROOT / "manifests/family_g_development_registry_v1.json"
    )
    for document, field in (
        (control, "control_g_000_result_hash"),
        (treatment, "regime_g_001_result_hash"),
        (registry, "family_g_development_registry_hash"),
    ):
        assert document[field] == canonical_hash(
            {key: value for key, value in document.items() if key != field}
        )
    assert summary["result_hashes"] == {
        "control_g_000_result_hash": control["control_g_000_result_hash"],
        "regime_g_001_result_hash": treatment["regime_g_001_result_hash"],
        "family_g_development_registry_hash": registry[
            "family_g_development_registry_hash"
        ],
    }


def test_registry_updates_only_the_frozen_treatment(summary: dict) -> None:
    registry = summary["registry"]
    assert registry["registry_version"] == REGISTRY_VERSION
    by_id = {row["experiment_id"]: row for row in registry["experiments"]}
    assert by_id[CONTROL_ID]["status"] == "REFERENCE_REPRODUCED"
    assert by_id[TREATMENT_ID]["status_before"] == "PREREGISTERED"
    assert by_id[TREATMENT_ID]["status"] == "DEVELOPMENT_EVALUATED"
    assert by_id[TREATMENT_ID]["parameter_hash"] == EXPECTED_TREATMENT_PARAMETER_HASH
    assert by_id[TREATMENT_ID]["preregistration_hash"] == EXPECTED_TREATMENT_PREREGISTRATION_HASH
    assert len(by_id) == 2


def test_no_tuning_vix_breadth_second_treatment_or_validation(summary: dict) -> None:
    assert summary["immutability"] == {
        "command_02_snapshot_before": summary["immutability"]["command_02_snapshot_after"],
        "command_02_snapshot_after": summary["immutability"]["command_02_snapshot_before"],
        "command_02_unchanged": True,
        "family_a_control_unchanged": True,
        "strategy_parameter_changed": False,
        "success_criteria_changed": False,
        "benchmark_changed": False,
        "sma_period_changed": False,
        "rebalance_schedule_changed": False,
    }
    assert summary["governance"] == {
        "development_performance_run": True,
        "validation_accessed": False,
        "vix_added": False,
        "breadth_added": False,
        "market_score_added": False,
        "second_treatment_created": False,
        "strategy_v2_created": False,
        "parameter_tuning_after_results": False,
    }


def test_reports_and_manifest_are_complete(manifest: dict) -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    for relative, expected in manifest["artifact_hashes"].items():
        path = ROOT / relative
        assert path.is_file()
        assert file_sha256(path) == expected
    field = "family_g_development_evaluation_manifest_hash"
    assert manifest[field] == canonical_hash(
        {key: value for key, value in manifest.items() if key != field}
    )


def test_documentation_records_governance_and_attribution() -> None:
    text = (
        ROOT / "docs/strategy-family-g-development-evaluation-v1.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "PARTIALLY_SUPPORTED",
        "MIXED",
        "PAUSE_FAMILY_G",
        "MISSED_GAIN",
        "No validation data",
        "no mid-quarter re-entry",
        "not changed after observing results",
    ):
        assert phrase in text


def test_criteria_function_sample_boundaries() -> None:
    control = {
        "net_cagr_pct": Decimal("10"),
        "net_max_drawdown_pct": Decimal("-20"),
        "net_annualized_volatility_pct": Decimal("10"),
        "net_sharpe_like": Decimal("1"),
        "negative_quarter_count": 2,
        "worst_quarter_return_pct": Decimal("-5"),
        "total_cost": Decimal("100"),
    }
    treatment = {
        "net_cagr_pct": Decimal("9"),
        "net_max_drawdown_pct": Decimal("-15"),
        "net_annualized_volatility_pct": Decimal("9"),
        "net_sharpe_like": Decimal("1.1"),
        "negative_quarter_count": 1,
        "worst_quarter_return_pct": Decimal("-4"),
        "total_cost": Decimal("90"),
        "net_ending_equity": Decimal("550000"),
        "starting_equity": Decimal("500000"),
        "yearly": [
            {"net_return_pct": Decimal("1")},
            {"net_return_pct": Decimal("0")},
            {"net_return_pct": Decimal("-1")},
        ],
    }
    rows, result = evaluate_criteria(
        control, treatment, {"status": "PASS"}, 6
    )
    assert next(row for row in rows if row["criterion"] == "F")["result"] == "PASS"
    assert result["REGIME_G_001_DEVELOPMENT_RESULT"] == "STRONGLY_SUPPORTED"
    rows, result = evaluate_criteria(
        control, treatment, {"status": "PASS"}, 5
    )
    assert next(row for row in rows if row["criterion"] == "F")["result"] == "LIMITED_SAMPLE"
    assert result["fatal_failure"] is False
    rows, result = evaluate_criteria(
        control, treatment, {"status": "PASS"}, 3
    )
    assert next(row for row in rows if row["criterion"] == "F")["result"] == "FATAL_SAMPLE_FAILURE"
    assert result["fatal_failure"] is True

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_c_breakout_continuation import (
    COMPRESSION_THRESHOLD,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
)
from app.research.strategy.family_c_c001_implementation_development import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTANCY_THRESHOLD,
    EXPECTED_ATTRIBUTION_HASH,
    EXPECTED_IMPLEMENTATION_CONFIG_HASH,
    EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
    EXPECTED_PARAMETER_HASH,
    EXPECTED_PREREGISTRATION_HASH,
    EXPECTED_SIGNAL_SET_HASH,
    MAX_DRAWDOWN_CAP,
    NET_CAGR_FLOOR,
    NORMALIZED_COST_DRAG_CAP,
    PROFIT_FACTOR_THRESHOLD,
    REPORT_NAMES,
    WIN_RATE_THRESHOLD,
    classify_replacement_quality,
    rank_treatment_candidates,
    verify_freeze_gate,
)
from app.research.strategy.family_c_c001_implementation_research import (
    EXPERIMENT_ID,
    TREATMENT_RANKING,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    REPO_ROOT
    / "data/research/strategy_families/family_c/v1/implementation_research"
    / "development_evaluation"
)
SUMMARY_PATH = REPO_ROOT / "data/reports/family_c_imp001_dev_v1_summary.json"


def _summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_command_identity_and_all_frozen_hashes() -> None:
    assert COMMAND_VERSION == "C1_IMP_001_DEVELOPMENT_EVALUATION_V1"
    assert COMMAND_PROFILE == "COMPRESSION_PRIORITY_CAPACITY_EVALUATION_V1"
    assert EXPECTED_IMPLEMENTATION_CONFIG_HASH == "d9de8dbbf0e288066565fcf9a4ef2b4cd494ed3f07760529298669226a119662"
    assert EXPECTED_PARAMETER_HASH == "6a5b49423e3fb30c708c9e1ae6a7cf5a5c0cf7306666d4f35f7428123d36915c"
    assert EXPECTED_PREREGISTRATION_HASH == "a5939b4d11282d0c8e40a2e1d9cebde79d8b62bf5d4a315adfcb8f853c366c7a"
    assert EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH == "90365ad9e45328a918bb714e03df78dfc049c0e335e9c6893216594c690978c0"
    assert EXPECTED_SIGNAL_SET_HASH == "096a11a85a72138176fb02b28efec52030e00c819c1bc67bca6fd8ae41abce9f"
    assert EXPECTED_ATTRIBUTION_HASH == "26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b"
    assert verify_freeze_gate(REPO_ROOT)["status"] == "VERIFIED"


def test_compression_priority_and_tie_break_order_are_exact() -> None:
    rows = [
        {"symbol": "ECHO", "compression_range_pct": "0.06", "breakout_strength_pct": "0.09"},
        {"symbol": "CHARLIE", "compression_range_pct": "0.05", "breakout_strength_pct": "0.01"},
        {"symbol": "ALPHA", "compression_range_pct": "0.05", "breakout_strength_pct": "0.03"},
        {"symbol": "BRAVO", "compression_range_pct": "0.05", "breakout_strength_pct": "0.03"},
        {"symbol": "DELTA", "compression_range_pct": "0.04", "breakout_strength_pct": "0.01"},
    ]
    result = rank_treatment_candidates(rows, 3)
    assert [row["symbol"] for row in result["ranked"]] == [
        "DELTA",
        "ALPHA",
        "BRAVO",
        "CHARLIE",
        "ECHO",
    ]
    assert [row["symbol"] for row in result["selected"]] == [
        "DELTA",
        "ALPHA",
        "BRAVO",
    ]
    assert TREATMENT_RANKING == (
        "COMPRESSION_RANGE_PCT_ASCENDING",
        "BREAKOUT_STRENGTH_PCT_DESCENDING",
        "SYMBOL_ASCENDING",
    )


def test_ranking_does_not_reject_when_capacity_is_available() -> None:
    rows = [
        {"symbol": "B", "compression_range_pct": "0.07", "breakout_strength_pct": "0.02"},
        {"symbol": "A", "compression_range_pct": "0.06", "breakout_strength_pct": "0.01"},
    ]
    result = rank_treatment_candidates(rows, 20)
    assert len(result["selected"]) == len(rows)
    assert result["rejected"] == []


def test_signal_set_identity_and_development_partition() -> None:
    summary = _summary()
    assert summary["signal_set"] == {
        "equal": True,
        "frozen_count": 4247,
        "treatment_count": 4247,
        "missing_count": 0,
        "extra_count": 0,
        "field_mismatch_count": 0,
        "c001_signal_set_hash": EXPECTED_SIGNAL_SET_HASH,
        "all_signal_compression_pass_cohort_unchanged": True,
    }
    assert summary["development_partition"] == {
        "start": "2022-01-01",
        "end": "2024-12-31",
        "post_2024_accessed": False,
        "validation_accessed": False,
    }


def test_frozen_strategy_mechanics_and_cost_model() -> None:
    mechanics = _summary()["mechanics"]
    assert mechanics["compression_threshold"] == str(COMPRESSION_THRESHOLD) == "0.08"
    assert mechanics["starting_capital"] == str(STARTING_CAPITAL) == "500000"
    assert mechanics["maximum_positions"] == MAX_CONCURRENT_POSITIONS == 20
    assert mechanics["target_notional_fraction"] == str(TARGET_NOTIONAL_FRACTION) == "0.05"
    assert mechanics["holding_completed_sessions"] == HOLDING_SESSIONS == 10
    assert mechanics["whole_shares"] is True
    assert mechanics["stop"] is None and mechanics["target"] is None
    assert mechanics["cost_model"] == "INDIA_EQUITY_COST_MODEL_V1"
    assert mechanics["cost_profile"] == "NSE_CASH_DELIVERY_RESEARCH_V1"
    assert mechanics["cost_scenario"] == "COST-SCENARIO-002"


def test_primary_treatment_portfolio_is_frozen() -> None:
    metrics = _summary()["treatment_portfolio"]
    assert metrics["experiment_id"] == EXPERIMENT_ID
    assert metrics["mode"] == "EXECUTABLE_INTEGER_SHARE_500K"
    assert metrics["closed_positions"] == 1167
    assert metrics["net_ending_equity"] == "503077.3245"
    assert metrics["net_total_return"] == "0.006154649"
    assert metrics["net_CAGR"] == "0.0020473551429776027"
    assert metrics["max_drawdown"] == "0.1914689006088537622946025426"
    assert metrics["accounting_data_integrity"]["status"] == "PASS"


def test_admitted_quality_and_frozen_thresholds() -> None:
    summary = _summary()
    quality = summary["admitted_event_quality"]
    assert quality["event_count"] == 1167
    assert quality["win_rate"] == "0.4935732647814910025706940874"
    assert quality["net_expectancy"] == "0.0005367555462879039402266836727"
    assert quality["net_profit_factor"] == "1.024040676023638195074848948"
    assert EXPECTANCY_THRESHOLD == Decimal("0.002451889062206648204628463672")
    assert PROFIT_FACTOR_THRESHOLD == Decimal("1.139795625568447941013450018")
    assert WIN_RATE_THRESHOLD == Decimal("0.5282905982905982905982905983")
    assert NET_CAGR_FLOOR == Decimal("0.0285576287541669630")
    assert MAX_DRAWDOWN_CAP == Decimal("0.2429287610199157994929078367")
    assert NORMALIZED_COST_DRAG_CAP == Decimal("0.2619728640")
    assert summary["evaluation"]["quality_pass_count"] == 0
    assert not any(
        row["pass"]
        for row in summary["evaluation"]["quality_dimensions"].values()
    )


def test_criteria_classification_and_next_stage_are_exact() -> None:
    summary = _summary()
    criteria = summary["evaluation"]["criteria_A_H"]
    assert criteria == {
        "A_CAPACITY_QUALITY_IMPROVEMENT": False,
        "B_PORTFOLIO_PROFITABILITY": False,
        "C_RETURN_NON_DEGRADATION": False,
        "D_DRAWDOWN_NON_DEGRADATION": True,
        "E_TEMPORAL_SUPPORT": True,
        "F_COST_NON_DEGRADATION": True,
        "G_SAMPLE_ADEQUACY": True,
        "H_ACCOUNTING_DATA_INTEGRITY": True,
    }
    assert summary["evaluation"]["criteria_pass_count"] == 5
    assert summary["evaluation"]["fatal_failure"] is False
    assert summary["C1_IMP_001_DEVELOPMENT_RESULT"] == "FAILED"
    assert summary["FAMILY_C_C001_POST_IMPLEMENTATION_STAGE"] == "CLOSE_IMPLEMENTATION_HYPOTHESIS"


def test_admission_intersection_and_replacement_quality() -> None:
    summary = _summary()
    comparison = summary["admission_comparison"]
    assert comparison["intersection_count"] == 761
    assert comparison["old_only_admitted_count"] == 409
    assert comparison["new_only_admitted_count"] == 406
    assert comparison["changed_admission_count"] == 815
    assert comparison["jaccard"] == "0.4828680203045685279187817259"
    assert classify_replacement_quality(
        comparison["old_only_quality"], comparison["new_only_quality"]
    ) == "WORSE"
    assert summary["COMPRESSION_PRIORITY_REPLACEMENT_QUALITY"] == "WORSE"


def test_same_day_and_yearly_admitted_diagnostics() -> None:
    summary = _summary()
    same_day = summary["same_day_matched_analysis"]
    assert same_day["changed_formation_date_count"] == 301
    assert Decimal(same_day["new_minus_old"]["win_rate"]) < 0
    assert Decimal(same_day["new_minus_old"]["median_return"]) < 0
    assert Decimal(same_day["new_minus_old"]["net_expectancy"]) < 0
    assert Decimal(same_day["new_minus_old"]["net_profit_factor"]) < 0
    yearly = summary["yearly_admitted_quality"]
    assert [row["year"] for row in yearly] == [2022, 2023, 2024]
    assert [row["treatment_count"] for row in yearly] == [305, 455, 407]


def test_no_mutation_second_experiment_stop_target_or_validation() -> None:
    summary = _summary()
    governance = summary["governance"]
    for field in (
        "signal_parameter_changed",
        "ranking_changed_after_result",
        "second_ranking_tested",
        "capacity_changed",
        "holding_period_changed",
        "position_sizing_changed",
        "stop_added",
        "target_added",
        "validation_accessed",
        "strategy_v2_created",
        "family_d_started",
    ):
        assert governance[field] is False
    assert summary["immutability"]["command_04_unchanged"] is True


def test_result_registry_manifest_and_artifact_hashes() -> None:
    result = json.loads(
        (OUTPUT_ROOT / "treatment/c1_imp_001_development_result_v1.json").read_text(
            encoding="utf-8"
        )
    )
    registry = json.loads(
        (OUTPUT_ROOT / "comparison/implementation_development_registry_v1.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (OUTPUT_ROOT / "manifests/c1_imp_001_development_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    for document, field in (
        (result, "c1_imp_001_result_hash"),
        (registry, "implementation_development_registry_hash"),
        (manifest, "c1_imp_001_development_manifest_hash"),
    ):
        assert canonical_hash(
            {key: value for key, value in document.items() if key != field}
        ) == document[field]
    assert result["c1_imp_001_result_hash"] == "013ce88f6b87ee6611065774a898345fd3e7bdf941002025195b844693dc15ee"
    assert registry["implementation_development_registry_hash"] == "a56210f2bb06cde7cd867a4549771c113369ea27b958433ef3090c67736ef5e8"
    assert registry["experiment_count"] == 1
    assert registry["experiments"][0]["status"] == "DEVELOPMENT_EVALUATED"
    assert manifest["summary_hash"] == file_sha256(SUMMARY_PATH)
    assert all(
        file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_reports_storage_and_documentation_exist() -> None:
    assert len(REPORT_NAMES) == 10
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    for directory in (
        "control",
        "treatment",
        "comparison",
        "admissions",
        "ledgers",
        "diagnostics",
        "manifests",
    ):
        assert (OUTPUT_ROOT / directory).is_dir()
    assert (
        REPO_ROOT / "docs/strategy-family-c-c001-implementation-development-v1.md"
    ).is_file()
    rows = read_csv(REPO_ROOT / "data/reports/family_c_imp001_dev_v1_admission_changes.csv")
    assert len(rows) == 4247
    assert sum(row["admission_changed"] == "True" for row in rows) == 815


def test_security_counters_are_zero() -> None:
    security = _summary()["security"]
    assert all(value == 0 for value in security.values())

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_b_b002_clean_reevaluation import (
    CLEAN_RECORD_ID,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_B002_CLEAN_REEVALUATION_HASH,
    EXPECTED_CLEAN_B002_RESULT_HASH,
    EXPECTED_CLEAN_CONTROL_RESULT_HASH,
    EXPECTED_CLEAN_RUN_MANIFEST_HASH,
    FILTER_CATEGORIES,
    REPORT_NAMES,
    clean_b002_inputs,
    output_root,
    verify_freeze_gate,
)
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
)
from app.research.strategy.family_b_development_evaluation import (
    CONTROL_ROLE,
    EXECUTABLE_MODE,
    EXPECTED_RESULT_HASHES,
)
from app.research.strategy.family_b_history_remediation import (
    EXPECTED_ADJUSTED_EXTENSION_HASH,
    EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
    EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    EXPECTED_RAW_EXTENSION_HASH,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    MINIMUM_HOLDINGS,
    SMA_SESSIONS,
)
from app.research.strategy.family_a_momentum import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_b002_clean_v1_summary.json"
OUTPUT_ROOT = output_root(REPO_ROOT)


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def recompute_document_hash(path: Path, hash_field: str) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    observed = document.pop(hash_field)
    assert canonical_hash(document) == observed
    return observed


def test_exact_command_identity_and_frozen_b002_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_B_B002_CLEAN_DEVELOPMENT_REEVALUATION_V1"
    assert COMMAND_PROFILE == "SMA200_REMEDIATED_DEVELOPMENT_EVALUATION_V1"
    assert CLEAN_RECORD_ID == "MOM-B-002-CLEAN-REEVALUATION"
    assert EXPECTED_EXPERIMENT_HASHES["MOM-B-002"] == {
        "parameter_hash": "0b7c8efec15017f9d2a0370bd8545d4463ff042ed13cb749d936c7979d0c91fe",
        "preregistration_hash": "d07d53efb5ee43e403236d3e67359abe6573cf137e00c6a41ad2c90bb87788fe",
    }


def test_prerun_freeze_gate_verifies_every_required_hash() -> None:
    freeze = verify_freeze_gate(REPO_ROOT)
    assert freeze["status"] == "VERIFIED"
    assert all(freeze["checks"].values())
    snapshot = freeze["snapshot"]
    assert snapshot["family_b_config_hash"] == EXPECTED_FAMILY_B_CONFIG_HASH
    assert snapshot["success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert snapshot["attribution_audit_hash"] == EXPECTED_ATTRIBUTION_AUDIT_HASH
    assert snapshot["history_remediation_config_hash"] == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH
    assert snapshot["raw_extension_hash"] == EXPECTED_RAW_EXTENSION_HASH
    assert snapshot["adjusted_extension_hash"] == EXPECTED_ADJUSTED_EXTENSION_HASH
    assert snapshot["family_b_sma_readiness_hash"] == EXPECTED_FAMILY_B_SMA_READINESS_HASH
    assert snapshot["history_remediation_manifest_hash"] == EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH


def test_development_partition_is_exact_and_prehistory_is_not_performance() -> None:
    result = summary()
    assert result["development_window"] == {
        "start": "2022-01-01",
        "end": "2024-12-31",
        "first_performance_session": "2022-01-03",
        "last_performance_session": "2024-12-31",
        "prehistory_performance_observations": 0,
        "development_only": True,
    }
    assert result["clean_B002"]["prehistory_performance_observations"] == 0
    assert result["governance"]["post_2024_rows_loaded"] is False


def test_clean_inputs_use_exact_causal_sma200_and_preserve_frozen_candidates() -> None:
    rows, calendar = clean_b002_inputs(REPO_ROOT)
    candidates = [row for row in rows if row["frozen_B002_top_decile_candidate"]]
    assert len(rows) == 5490
    assert len(calendar) == 11
    assert len(candidates) == 302
    assert all(row["history_data_version"] == "DAILY_HISTORY_PREHISTORY_V2" for row in rows)
    assert all(row["no_future_observations"] is True for row in rows)
    assert all(
        (row["sma200"] is None and row["SMA_observation_count"] == 0)
        or (row["sma200"] is not None and row["SMA_observation_count"] == SMA_SESSIONS)
        for row in rows
    )


def test_legitimate_unavailable_rows_are_not_imputed_and_no_truncation_leaks() -> None:
    rows, _ = clean_b002_inputs(REPO_ROOT)
    candidates = [row for row in rows if row["frozen_B002_top_decile_candidate"]]
    unavailable = [row for row in candidates if row["sma200"] is None]
    assert len(unavailable) == 7
    assert sum(row["SMA_availability_reason"] == "GENUINE_RECENT_LISTING" for row in unavailable) == 5
    assert sum(row["SMA_availability_reason"] == "CORPORATE_ACTION_EXCLUDED" for row in unavailable) == 2
    assert all(row["B002_eligible"] is None for row in unavailable)
    assert all(row["SMA_availability_reason"] != "DATASET_TRUNCATION" for row in candidates)
    assert summary()["filter_impact"]["dataset_truncation_leakage_count"] == 0


def test_control_is_an_exact_non_overwriting_reproduction() -> None:
    control = summary()["control"]
    assert control["role"] == CONTROL_ROLE == "CONTROL_REPRODUCTION_ONLY"
    assert control["source_control_result_hash"] == EXPECTED_RESULT_HASHES["CONTROL-B-000"]
    assert control["control_reproduction"]["all_metrics_exact"] is True
    assert all(control["control_reproduction"]["metric_checks"].values())
    assert control["source_control_overwritten"] is False
    assert control["performance"]["net_ending_equity"] == "955331.6799"


def test_clean_b002_selection_is_next_open_no_backfill_and_meets_minimum() -> None:
    result = summary()
    breadth = result["clean_B002"]["qualifying_breadth"]
    assert MINIMUM_HOLDINGS == 10
    assert breadth["minimum_qualifying_count"] == 18
    assert breadth["median_qualifying_count"] == "27"
    assert breadth["maximum_qualifying_count"] == 34
    assert breadth["insufficient_breadth_schedules"] == []
    calendar = csv_rows(OUTPUT_ROOT / "comparison/clean_b002_rebalance_calendar_v1.csv")
    assert len(calendar) == 11
    assert all(row["future_returns_accessed"] == "False" for row in calendar)
    assert all(int(row["B002_pass_count"]) >= MINIMUM_HOLDINGS for row in calendar)
    rebalances = csv_rows(
        OUTPUT_ROOT / "b002/executable_integer_share_500k/rebalances.csv"
    )
    assert all(row["execution_date"] > row["formation_date"] for row in rebalances)
    assert all(row["status"] == "EXECUTED" for row in rebalances)


def test_both_performance_modes_and_frozen_cost_model_are_explicit() -> None:
    result = summary()["clean_B002"]
    assert result["performance"]["mode"] == EXECUTABLE_MODE
    assert result["idealized_performance"]["mode"] == "IDEALIZED_EQUAL_WEIGHT_PERCENTAGE"
    assert result["performance"]["starting_equity"] == "500000"
    assert result["idealized_performance"]["starting_equity"] == "500000"
    assert result["idealized_vs_executable"]["primary_decision_mode"] == EXECUTABLE_MODE
    assert result["cost_model"] == {
        "model": "INDIA_EQUITY_COST_MODEL_V1",
        "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "scenario": "COST-SCENARIO-002",
        "slippage_bps_per_side": "5",
        "cost_config_hash": "9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48",
    }
    assert Decimal(result["performance"]["total_cost"]) == Decimal("18208.31")


def test_accounting_and_data_integrity_are_all_clean() -> None:
    result = summary()
    for record in (result["control"], result["clean_B002"]):
        assert all(record["accounting"].values())
        assert record["performance"]["cash_reconciliation_violations"] == 0
        assert record["performance"]["equity_reconciliation_violations"] == 0
        assert record["cash"]["reconciles_to_average_cash"] is True


def test_filter_categories_counts_rates_and_qualifying_count_are_exact() -> None:
    impact = summary()["filter_impact"]
    assert tuple(impact["category_counts"]) == FILTER_CATEGORIES
    assert impact["top_decile_candidate_count"] == 302
    assert impact["qualifying_count"] == 294
    assert impact["true_below_SMA_removal_count"] == 1
    assert impact["SMA_unavailable_count"] == 7
    assert impact["category_counts"] == {
        "TRUE_BELOW_SMA200": 1,
        "GENUINE_SMA_UNAVAILABLE_RECENT_LISTING": 5,
        "CORPORATE_ACTION_UNAVAILABLE": 2,
        "OTHER_LEGITIMATE_UNAVAILABLE": 0,
    }
    assert Decimal(impact["true_below_SMA_removal_rate"]) == Decimal(1) / Decimal(302)
    assert Decimal(impact["legitimate_unavailable_removal_rate"]) == Decimal(7) / Decimal(302)


def test_frozen_criteria_a_to_g_all_pass_without_fatal_failure() -> None:
    criteria = summary()["criteria"]
    assert list(criteria["criteria"]) == [
        "A_RETURN_PRESERVATION",
        "B_DRAWDOWN",
        "C_TEMPORAL_SUPPORT",
        "D_COST_EFFICIENCY",
        "E_BREADTH",
        "F_CAPITAL_DEPLOYMENT",
        "G_ACCOUNTING_DATA_INTEGRITY",
    ]
    assert all(criteria["criteria"].values())
    assert criteria["criteria_pass_count"] == 7
    assert criteria["fatal_failure_triggered"] is False
    assert Decimal(criteria["RETURN_PRESERVATION_RATIO"]) == Decimal(
        "1.015622051786901775745295693"
    )
    assert Decimal(criteria["DRAWDOWN_RELATIVE_IMPROVEMENT"]) == Decimal(
        "-0.07070795028291001305297245526"
    )


def test_result_and_readiness_use_allowed_frozen_classifications() -> None:
    decisions = summary()["decisions"]
    assert decisions == {
        "MOM_B_002_CLEAN_REEVALUATION_RESULT": "SUPPORTED",
        "B002_CLEAN_TREND_FILTER_EVIDENCE": "WEAK",
        "B002_CLEAN_DEVELOPMENT_ATTRIBUTION": "EVIDENCE_TOO_SPARSE",
        "B002_VALIDATION_DESIGN_READINESS": "MORE_DEVELOPMENT_EVIDENCE_REQUIRED",
        "FAMILY_B_POST_REMEDIATION_STATUS": "CONTINUE_DEVELOPMENT_RESEARCH",
        "B001_STATUS": "NO_DISTINCT_FILTER_EVIDENCE",
    }


def test_true_filter_attribution_is_exact_and_descriptive_only() -> None:
    rows = csv_rows(REPO_ROOT / "data/reports/family_b_b002_clean_v1_attribution.csv")
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AUBANK"
    assert row["formation_date"] == "2022-06-30"
    assert row["execution_date"] == "2022-07-01"
    assert row["removal_category"] == "TRUE_BELOW_SMA200"
    assert row["control_inclusion"] == "False"
    assert Decimal(row["control_subsequent_realized_contribution_if_held_rupees"]) == 0
    assert Decimal(row["portfolio_weight_redistribution_effect_pp"]) != 0
    assert row["isolated_true_filter_effect_interpretable"] == "False"
    assert row["descriptive_only"] == "True"


def test_original_clean_and_yearly_attribution_are_exact() -> None:
    comparison = summary()["comparison"]
    assert comparison["original_B002_net_CAGR_pct"] == "31.505630395280136"
    assert comparison["clean_B002_net_CAGR_pct"] == "24.482433519862347"
    assert comparison["clean_minus_original_CAGR_pp"] == "-7.023196875417789"
    assert comparison["original_B002_2022_return_pct"] == "19.3778511400"
    assert comparison["clean_B002_2022_return_pct"] == "2.0420744200"
    assert comparison["clean_minus_original_2022_pp"] == "-17.3357767200"
    assert comparison["previous_2022_advantage_finding"] == "REDUCED_BUT_REMAINS"
    assert comparison["clean_minus_control_2023_pp"] == "-0.71316705347697262964878150"
    assert comparison["clean_minus_control_2024_pp"] == "0.22323722980344153698187520"
    assert comparison["clean_2023_2024_compounded_return_pct"] == "88.95119233504112450010304280"


def test_no_b001_b003_alternate_sma_combined_filter_or_validation() -> None:
    governance = summary()["governance"]
    assert governance["B002_parameters_changed"] is False
    assert governance["alternate_SMA_tested"] is False
    assert governance["B001_rerun"] is False
    assert governance["B003_created"] is False
    assert governance["combined_filter_tested"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["family_c_started"] is False


def test_all_immutable_result_hashes_recompute_exactly() -> None:
    assert recompute_document_hash(
        OUTPUT_ROOT / "control/clean_control_result_v1.json",
        "clean_control_result_hash",
    ) == EXPECTED_CLEAN_CONTROL_RESULT_HASH
    assert recompute_document_hash(
        OUTPUT_ROOT / "b002/clean_b002_result_v1.json",
        "clean_b002_result_hash",
    ) == EXPECTED_CLEAN_B002_RESULT_HASH
    assert recompute_document_hash(
        OUTPUT_ROOT / "manifests/b002_clean_reevaluation_v1.json",
        "b002_clean_reevaluation_hash",
    ) == EXPECTED_B002_CLEAN_REEVALUATION_HASH
    assert recompute_document_hash(
        OUTPUT_ROOT / "manifests/run_manifest_v1.json",
        "clean_run_manifest_hash",
    ) == EXPECTED_CLEAN_RUN_MANIFEST_HASH


def test_manifest_artifacts_exist_and_match_their_sha256() -> None:
    manifest = json.loads(
        (OUTPUT_ROOT / "manifests/run_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["validation_accessed"] is False
    for relative_path, expected_hash in manifest["artifact_hashes"].items():
        path = REPO_ROOT / relative_path
        assert path.is_file()
        assert file_sha256(path) == expected_hash


def test_baselines_and_original_family_b_records_are_immutable() -> None:
    regression = summary()["regression"]
    assert regression["freeze_snapshot_before"] == regression["freeze_snapshot_after"]
    assert regression["baseline_unchanged"] is True
    assert all(value == "UNCHANGED" for key, value in regression.items() if key not in {
        "freeze_snapshot_before", "freeze_snapshot_after", "baseline_unchanged"
    })


def test_required_reports_storage_and_documentation_exist() -> None:
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).is_file()
    assert {path.name for path in OUTPUT_ROOT.iterdir() if path.is_dir()} == {
        "control",
        "b002",
        "comparison",
        "ledgers",
        "manifests",
    }
    assert (REPO_ROOT / "docs/strategy-family-b-b002-clean-reevaluation-v1.md").is_file()


def test_security_and_external_side_effect_counters_are_zero() -> None:
    governance = summary()["governance"]
    for key in (
        "live_signals_generated",
        "live_orders_placed",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "database_writes",
        "network_calls",
        "secrets_written",
    ):
        assert governance[key] == 0

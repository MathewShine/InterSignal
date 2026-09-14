from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
)
from app.research.strategy.family_b_history_remediation import (
    AVAILABILITY_REASONS,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    DATA_VERSION,
    EXPECTED_ADJUSTED_EXTENSION_HASH,
    EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
    EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    EXPECTED_RAW_EXTENSION_HASH,
    REPORT_NAMES,
    SMA_SESSIONS,
    TARGET_START,
    _classify_unavailable,
    _sma,
    history_remediation_config,
    verify_frozen_inputs,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = REPO_ROOT / "data/reports/family_b_history_remediation_v1_summary.json"
OUTPUT_ROOT = (
    REPO_ROOT
    / "data/research/strategy_families/family_b/v1/history_remediation"
)


def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def report_rows(name: str) -> list[dict[str, str]]:
    with (REPO_ROOT / "data/reports" / name).open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


def test_exact_command_profile_data_version_and_frozen_attribution_hash() -> None:
    assert COMMAND_VERSION == "FAMILY_B_DEVELOPMENT_HISTORY_REMEDIATION_V1"
    assert COMMAND_PROFILE == "SMA200_PREHISTORY_READINESS_V1"
    assert DATA_VERSION == "DAILY_HISTORY_PREHISTORY_V2"
    frozen = verify_frozen_inputs(REPO_ROOT)
    assert frozen["status"] == "VERIFIED"
    assert all(frozen["checks"].values())
    assert frozen["snapshot"]["attribution_audit_hash"] == EXPECTED_ATTRIBUTION_AUDIT_HASH


def test_remediation_config_hash_is_frozen_and_recomputes() -> None:
    config = history_remediation_config(REPO_ROOT)
    observed = config.pop("history_remediation_config_hash")
    assert observed == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH
    assert canonical_hash(config) == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH


def test_prehistory_begins_2020_and_development_remains_2022_through_2024() -> None:
    result = summary()
    assert TARGET_START == date(2020, 1, 1)
    assert result["actual_history"]["earliest_daily_date"] == "2020-01-01"
    assert result["SMA_readiness"]["development_window"] == {
        "start": "2022-01-01",
        "end": "2024-12-31",
        "changed": False,
    }


def test_prehistory_rows_are_never_performance_observations() -> None:
    rows = report_rows("family_b_history_remediation_v1_sma_before_after.csv")
    assert rows
    assert all(row["performance_observation"] == "False" for row in rows)
    assert summary()["SMA_readiness"]["prehistory_rows_are_performance"] is False
    assert summary()["runtime"]["performance_runs"] == 0


def test_sma_uses_exactly_200_valid_observations_and_no_future_values() -> None:
    formation = date(2024, 1, 1)
    start = formation - timedelta(days=205)
    values = {start + timedelta(days=index): Decimal(index + 1) for index in range(206)}
    values[formation + timedelta(days=1)] = Decimal("999999")
    observed = _sma(values, formation)
    causal_values = [
        value for observed_date, value in sorted(values.items()) if observed_date <= formation
    ][-SMA_SESSIONS:]
    assert observed["available"] is True
    assert observed["observation_count_used"] == SMA_SESSIONS == 200
    assert observed["value"] == sum(causal_values, Decimal("0")) / Decimal("200")
    assert observed["window_end"] <= formation
    assert observed["no_future_observations"] is True


def test_sma_never_uses_a_partial_window() -> None:
    formation = date(2024, 1, 1)
    values = {
        formation - timedelta(days=index): Decimal("100")
        for index in range(SMA_SESSIONS - 1)
    }
    observed = _sma(values, formation)
    assert observed["available"] is False
    assert observed["history_count"] == 199
    assert observed["observation_count_used"] == 0
    rows = report_rows("family_b_history_remediation_v1_sma_before_after.csv")
    assert all(row["no_partial_SMA"] == "True" for row in rows)


def test_genuine_listing_age_classification_requires_200_real_sessions() -> None:
    formation = date(2022, 3, 31)
    earliest = date(2021, 11, 1)
    sessions = {earliest + timedelta(days=index) for index in range(120)}
    assert (
        _classify_unavailable(
            symbol="RECENT",
            formation_date=formation,
            new_sma={"available": False, "history_count": 120},
            observed_dates=sessions,
            excluded_count=0,
            sessions=sessions,
        )
        == "GENUINE_RECENT_LISTING"
    )


def test_dataset_truncation_and_identity_cases_are_classified_as_resolved() -> None:
    rows = report_rows("family_b_history_remediation_v1_sma_before_after.csv")
    candidates = [row for row in rows if row["frozen_B002_top_decile_candidate"] == "True"]
    truncation = [row for row in candidates if row["remediation_outcome"] == "DATASET_TRUNCATION_RESOLVED"]
    identity = [row for row in candidates if row["remediation_outcome"] == "IDENTITY_MAPPING_RESOLVED"]
    assert len(truncation) == 20
    assert len(identity) == 3
    assert {row["symbol"] for row in identity} == {"POONAWALLA", "RHIM", "ARE&M"}
    assert all(row["new_SMA200_available"] == "True" for row in truncation + identity)


def test_every_formation_symbol_has_one_closed_reason_and_is_causal() -> None:
    rows = report_rows("family_b_history_remediation_v1_sma_before_after.csv")
    assert len(rows) == 5490
    assert all(row["availability_reason"] in AVAILABILITY_REASONS for row in rows)
    assert all(row["no_future_observations"] == "True" for row in rows)
    assert all(row["frozen_formation_member"] == "True" for row in rows)
    assert all(row["development_window_changed"] == "False" for row in rows)


def test_point_in_time_candidate_population_is_exactly_frozen() -> None:
    result = summary()["SMA_readiness"]
    assert result["old_B002_candidate_count"] == 302
    assert result["old_SMA_unavailable_count"] == 30
    rows = report_rows("family_b_history_remediation_v1_sma_before_after.csv")
    assert sum(row["frozen_B002_top_decile_candidate"] == "True" for row in rows) == 302


def test_overlap_reconciliation_has_no_unexplained_difference() -> None:
    result = summary()["reconciliation"]
    assert result["overlap_rows_compared"] == 503221
    assert result["exact_overlap_rows"] == 502692
    assert result["explained_overlap_differences"] == 529
    assert result["unexplained_overlap_differences"] == 0
    assert result["DAILY_HISTORY_REMEDIATION_RECONCILIATION"] == "EXPLAINED_VERSIONED_DIFFERENCES"


def test_corporate_action_extension_is_applied_without_mutating_v1() -> None:
    result = summary()
    corporate = result["corporate_action_extension"]
    assert corporate["result"] == "EXTENDED_AND_APPLIED"
    assert corporate["event_count"] == 3376
    assert corporate["factor_count"] == 56
    assert corporate["adjusted_row_count"] > 0
    assert result["reconciliation"]["old_frozen_files_modified"] is False
    assert result["regression"]["old_adjusted_hash_before"] == result["regression"]["old_adjusted_hash_after"]


def test_before_after_coverage_and_remaining_reasons_are_exact() -> None:
    result = summary()["SMA_readiness"]
    assert result["new_SMA_unavailable_count"] == 7
    assert result["dataset_truncation_resolved_count"] == 20
    assert result["identity_mapping_resolved_count"] == 3
    assert result["new_unavailability_reasons"]["GENUINE_RECENT_LISTING"] == 5
    assert result["new_unavailability_reasons"]["CORPORATE_ACTION_EXCLUDED"] == 2
    assert result["new_unavailability_reasons"]["OFFICIAL_SOURCE_GAP"] == 0
    assert result["new_unavailability_reasons"]["IDENTITY_MAPPING_UNRESOLVED"] == 0
    assert Decimal(result["SMA200_STRUCTURAL_COVERAGE_RATE"]) == Decimal(295) / Decimal(302) * 100
    assert Decimal(result["SMA200_REMEDIABLE_COVERAGE_RATE"]) == Decimal(295) / Decimal(297) * 100
    assert result["coverage_classification"] == "STRONG"


def test_first_formation_audit_is_complete() -> None:
    result = summary()["SMA_readiness"]
    assert result["first_formation_original_candidate_count"] == 23
    assert result["first_formation_new_SMA_available_count"] == 20
    assert result["first_formation_still_unavailable_count"] == 3
    rows = report_rows("family_b_history_remediation_v1_first_formation.csv")
    assert len(rows) == 23
    assert all(row["formation_date"] == "2022-03-31" for row in rows)


def test_readiness_hashes_are_frozen_and_recompute() -> None:
    result = summary()
    assert result["hashes"] == {
        "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
        "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
        "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
        "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    }
    readiness_path = OUTPUT_ROOT / "manifests/family_b_sma_readiness_v1.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    observed = readiness.pop("family_b_sma_readiness_hash")
    assert observed == EXPECTED_FAMILY_B_SMA_READINESS_HASH
    assert canonical_hash(readiness) == EXPECTED_FAMILY_B_SMA_READINESS_HASH


def test_remediation_manifest_is_immutable_and_recomputes() -> None:
    manifest_path = OUTPUT_ROOT / "manifests/history_remediation_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed = manifest.pop("history_remediation_manifest_hash")
    assert observed == EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH
    assert canonical_hash(manifest) == EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH


def test_no_performance_parameter_change_validation_b003_or_v2() -> None:
    governance = summary()["governance"]
    assert governance["performance_run"] is False
    assert governance["performance_metrics_computed"] is False
    assert governance["B002_parameters_changed"] is False
    assert governance["alternate_SMA_used"] is False
    assert governance["partial_SMA_used"] is False
    assert governance["validation_accessed"] is False
    assert governance["post_2024_price_rows_loaded"] is False
    assert governance["B003_created"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["family_c_started"] is False


def test_decisions_preserve_b001_and_b002_statuses() -> None:
    decisions = summary()["decisions"]
    assert decisions["FAMILY_B_HISTORY_REMEDIATION_RESULT"] == "READY_FOR_CLEAN_DEVELOPMENT_REEVALUATION"
    assert decisions["FAMILY_B_B002_REEVALUATION_READINESS"] == "YES"
    assert decisions["B001_STATUS_AFTER_ATTRIBUTION"] == "NO_DISTINCT_FILTER_EVIDENCE"
    assert decisions["B002_STATUS_BEFORE_REEVALUATION"] == "CONFOUNDED_BY_HISTORY_AVAILABILITY"


def test_all_six_pilot_cases_exist() -> None:
    with (OUTPUT_ROOT / "pilots/pilot_cases.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        cases = {row["case"] for row in csv.DictReader(file)}
    assert cases == {
        "A_DATASET_TRUNCATION_RESOLVED",
        "B_GENUINE_RECENT_LISTING",
        "C_FULL_200_SESSION_HISTORY",
        "D_CORPORATE_ACTION_SAFE",
        "E_OVERLAP_RECONCILIATION",
        "F_IDENTITY_MAPPING",
    }


def test_required_reports_storage_and_documentation_exist() -> None:
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).is_file()
    assert {path.name for path in OUTPUT_ROOT.iterdir() if path.is_dir()} == {
        "raw_manifest",
        "reconciliation",
        "sma_readiness",
        "pilots",
        "manifests",
    }
    assert (REPO_ROOT / "docs/strategy-family-b-history-remediation-v1.md").is_file()


def test_all_frozen_regressions_and_security_controls_remain_clean() -> None:
    result = summary()
    assert result["regression"]["baseline_unchanged"] is True
    assert all(
        result["regression"][key] == "UNCHANGED"
        for key in (
            "strategy_v1",
            "CAP4",
            "family_a_commands_01_05",
            "family_a_closure",
            "family_b_command_01",
            "family_b_command_02",
            "family_b_command_03",
        )
    )
    governance = result["governance"]
    assert governance["live_signals_generated"] == 0
    assert governance["live_orders_placed"] == 0
    assert governance["broker_calls"] == 0
    assert governance["remote_migrations"] == 0
    assert governance["supabase_persistence"] == 0
    assert governance["database_writes"] == 0
    assert governance["network_writes_other_than_approved_NSE_sources"] == 0
    assert governance["secrets_written"] == 0

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_d_exact_gap_recovery import (
    COMMAND_VERSION,
    EXPECTED_COMMAND_02_HASHES,
    EXPECTED_COMMAND_02_MANIFEST_HASH,
    EXPECTED_CONTROL_SIGNAL_COUNT,
    EXPECTED_STARTING_GAPS,
    PROFILE,
    RECOVERY_DATA_VERSION,
    _document_hash,
    _load_plan,
    exact_gap_recovery_config_document,
    inspect_approved_alternate_source,
    one_source_session_choice,
    quality_failure_cause,
    verify_exact_gap_inputs,
)
from app.research.strategy.family_d_opening_range import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data/research/strategy_families/family_d/v1/exact_gap_recovery"
REPORT_ROOT = REPO_ROOT / "data/reports"
IST = ZoneInfo("Asia/Kolkata")


def _summary() -> dict:
    return json.loads(
        (REPORT_ROOT / "family_d_gap_recovery_v1_summary.json").read_text(encoding="utf-8")
    )


def test_command_identity_and_frozen_family_d_hashes() -> None:
    assert (COMMAND_VERSION, PROFILE, RECOVERY_DATA_VERSION) == (
        "FAMILY_D_EXACT_GAP_RECOVERY_V1",
        "PRIOR20_EXACT_INTRADAY_GAP_RECOVERY_V1",
        "FAMILY_D_EXACT_GAP_RECOVERY_DATA_V1",
    )
    assert exact_gap_recovery_config_document()["frozen_family_d_hashes"] == {
        "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
        "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
        "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
        "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
    }


def test_command_02_hashes_manifest_and_all_artifacts_verify() -> None:
    verification = verify_exact_gap_inputs(REPO_ROOT)
    assert verification["result"] == "VERIFIED"
    assert all(verification["command_02_hash_checks"].values())
    assert verification["command_02_artifact_count"] == 1086
    assert exact_gap_recovery_config_document()["frozen_command_02_hashes"] == EXPECTED_COMMAND_02_HASHES
    assert exact_gap_recovery_config_document()["frozen_command_02_manifest_hash"] == EXPECTED_COMMAND_02_MANIFEST_HASH


def test_exact_217_gap_population_and_reason_breakdown() -> None:
    _, population, _ = _load_plan(REPO_ROOT)
    assert population["population_count"] == EXPECTED_STARTING_GAPS == 217
    assert len({(row["symbol"], row["required_session_date"]) for row in population["rows"]}) == 217
    assert Counter(row["current_reason"] for row in population["rows"]) == Counter(
        {
            "MISSING_OPENING_BARS": 105,
            "PROVIDER_HISTORY_UNAVAILABLE": 48,
            "SESSION_QUALITY_FAILURE": 64,
        }
    )
    assert all(row["isin"] and row["target_sessions_affected_count"] > 0 for row in population["rows"])


def test_no_population_expansion_and_exact_small_groww_windows() -> None:
    _, population, plan = _load_plan(REPO_ROOT)
    frozen = {(row["symbol"], row["required_session_date"]) for row in population["rows"]}
    planned = {
        (request["symbol"], value)
        for request in plan["requests"]
        for value in request["required_sessions"]
    }
    assert planned == frozen
    assert plan["population_expansion_count"] == 0
    assert plan["network_requests_made_while_planning"] == 0
    assert len({row["request_id"] for row in plan["requests"]}) == plan["request_count"]
    assert all(row["window_calendar_days"] <= 7 for row in plan["requests"])
    assert all(row["provider_instrument"] and row["interval"] == "5m" for row in plan["requests"])


def test_missing_opening_retries_explicitly_verify_all_three_bars() -> None:
    rows = json.loads(
        (OUTPUT_ROOT / "normalized/exact_gap_normalized_manifest_v1.json").read_text(encoding="utf-8")
    )
    quality_path = OUTPUT_ROOT / "normalized/exact_gap_session_quality_v1.csv"
    quality_text = quality_path.read_text(encoding="utf-8")
    assert rows["one_source_per_symbol_session"] is True
    assert all(value in quality_text for value in ("opening_0915_available", "opening_0920_available", "opening_0925_available"))


def test_identity_handling_uses_project_evidence_only() -> None:
    summary = _summary()
    assert summary["identity"]["invented_aliases"] == 0
    assert summary["identity"]["identity_recovered_sessions"] == 0


def test_alternate_source_authorization_gate() -> None:
    audit = inspect_approved_alternate_source(REPO_ROOT)
    assert audit["result"] == "NO_APPROVED_ALTERNATE_SOURCE"
    assert audit["approved_alternate_source_available"] is False
    assert audit["alternate_provider_contacted"] is False
    assert audit["authorization_gate"] == "ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED"


def test_one_source_per_session_rule_never_stitches() -> None:
    current = {"strict": False, "source": "COMMAND_02"}
    exact = {"strict": True, "source": "GROWW_EXACT"}
    assert one_source_session_choice(current, exact) is exact
    assert one_source_session_choice(current, {"strict": False}) is current
    manifest = json.loads(
        (OUTPUT_ROOT / "normalized/exact_gap_normalized_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["mixed_bar_sessions"] == 0


def test_quality_failure_classification() -> None:
    assert quality_failure_cause(None) == "MISSING_BAR"
    assert quality_failure_cause({"exists": True, "strict": True}) == "RESOLVED_ON_EXACT_RETRIEVAL"
    assert quality_failure_cause({"exists": True, "strict": False, "reason": "MISSING_OPENING_BARS"}) == "MISSING_BAR"
    assert quality_failure_cause({"exists": True, "strict": False, "quality_statuses": ["NEGATIVE_VOLUME"]}) == "VOLUME_ISSUE"
    assert quality_failure_cause({"exists": True, "strict": False, "quality_statuses": ["SESSION_MISMATCH"]}) == "TIMESTAMP_ISSUE"


def test_volume_compatibility_prevents_unapproved_alternate_use() -> None:
    summary = _summary()
    assert summary["volume_compatibility"]["ALTERNATE_VOLUME_COMPATIBILITY"] == "INCONCLUSIVE"
    assert summary["volume_compatibility"]["alternate_source_used"] is False
    assert summary["volume_compatibility"]["d001_alternate_volume_rows_used"] == 0


def test_strict_quality_and_continuity_recomputation() -> None:
    summary = _summary()
    matrix = json.loads(
        (OUTPUT_ROOT / "continuity/recovered_continuity_matrix_v1.json").read_text(encoding="utf-8")
    )
    assert len(matrix["rows"]) == 4821
    assert all(row["required_prior_20_count"] == 20 for row in matrix["rows"])
    assert sum(row["activity_baseline_available"] for row in matrix["rows"]) == summary["continuity"]["complete_target_sessions"]
    assert all(row["strict_prior_20_count"] == 20 for row in matrix["rows"] if row["activity_baseline_available"])


def test_control_count_and_d001_subset_invariants() -> None:
    structural = _summary()["structural"]
    assert structural["control_signal_count"] == EXPECTED_CONTROL_SIGNAL_COUNT == 2292
    assert structural["control_count_invariant"] == "PASS"
    assert structural["d001_subset_violations"] == 0


def test_coverage_classification_and_95_percent_backtest_gate() -> None:
    summary = _summary()
    coverage = Decimal(str(summary["continuity"]["coverage_after_pct"]))
    expected = "YES" if coverage >= Decimal("95") else "NO"
    assert summary["FAMILY_D_DEVELOPMENT_BACKTEST_READINESS"] == expected
    assert summary["continuity"]["coverage_classification"] in {
        "EXCELLENT",
        "STRONG",
        "USABLE_WITH_LIMITATIONS",
        "INSUFFICIENT",
    }


def test_no_performance_no_validation_and_zero_external_side_effects() -> None:
    governance = _summary()["governance"]
    assert governance["strategy_parameter_changed"] is False
    assert governance["prior20_rule_weakened"] is False
    assert governance["performance_run"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["new_provider_contacted"] is False
    assert governance["live_signals"] == governance["live_orders"] == governance["broker_order_calls"] == 0
    assert governance["remote_migrations"] == governance["supabase_persistence"] == 0


def test_all_required_hashes_and_manifest_recompute() -> None:
    summary = _summary()
    documents = (
        (OUTPUT_ROOT / "request_plan/exact_gap_recovery_config_v1.json", "exact_gap_recovery_config_hash"),
        (OUTPUT_ROOT / "population/exact_gap_population_v1.json", "exact_gap_population_hash"),
        (OUTPUT_ROOT / "request_plan/exact_gap_request_plan_v1.json", "exact_gap_request_plan_hash"),
        (OUTPUT_ROOT / "groww_retry/exact_gap_raw_manifest_v1.json", "exact_gap_raw_hash"),
        (OUTPUT_ROOT / "normalized/exact_gap_normalized_manifest_v1.json", "exact_gap_normalized_hash"),
        (OUTPUT_ROOT / "continuity/recovered_continuity_matrix_v1.json", "recovered_continuity_matrix_hash"),
        (OUTPUT_ROOT / "readiness/family_d_post_recovery_readiness_v1.json", "family_d_post_recovery_readiness_hash"),
    )
    for path, field in documents:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert _document_hash(document, field) == document[field] == summary["hashes"][field]
    manifest = json.loads(
        (OUTPUT_ROOT / "manifests/family_d_exact_gap_recovery_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert _document_hash(manifest, "manifest_hash") == manifest["manifest_hash"]
    assert all(
        (REPO_ROOT / relative).is_file() and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_reports_documentation_and_propagation_are_complete() -> None:
    assert all((REPORT_ROOT / name).stat().st_size > 0 for name in (
        "family_d_gap_recovery_v1_summary.json",
        "family_d_gap_recovery_v1_population.csv",
        "family_d_gap_recovery_v1_groww_retry.csv",
        "family_d_gap_recovery_v1_unresolved.csv",
        "family_d_gap_recovery_v1_source_reconciliation.csv",
        "family_d_gap_recovery_v1_volume_compatibility.csv",
        "family_d_gap_recovery_v1_continuity.csv",
        "family_d_gap_recovery_v1_propagation.csv",
        "family_d_gap_recovery_v1_activity.csv",
        "family_d_gap_recovery_v1_readiness.csv",
    ))
    assert (REPO_ROOT / "docs/strategy-family-d-exact-gap-recovery-v1.md").stat().st_size > 0
    propagation = (REPORT_ROOT / "family_d_gap_recovery_v1_propagation.csv").read_text(encoding="utf-8").splitlines()
    assert len(propagation) == _summary()["continuity"]["remaining_unique_gaps"] + 1

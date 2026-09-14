from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.research.strategy.family_c_research_closure import EXPECTED_FAMILY_C_CLOSURE_HASH
from app.research.strategy.family_d_continuity_remediation import (
    AVAILABILITY_REASONS,
    COMMAND_VERSION,
    CONTINUITY_DATA_VERSION,
    PROFILE,
    _document_hash,
    _load_plan,
    _target_reason,
    classify_overlap,
    continuity_config_document,
    coverage_classification,
    prior_market_sessions,
    verify_continuity_inputs,
)
from app.research.strategy.family_d_opening_range import (
    ACTIVITY_THRESHOLD,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    opening_activity_ratio,
    opening_range_15m,
)
from app.research.strategy.family_a_momentum import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data/research/strategy_families/family_d/v1/continuity_remediation"
REPORT_ROOT = REPO_ROOT / "data/reports"
IST = ZoneInfo("Asia/Kolkata")


def _bar(hh: int, mm: int, *, volume: int = 100, close: str = "100") -> SimpleNamespace:
    start = datetime(2024, 1, 2, hh, mm, tzinfo=IST)
    return SimpleNamespace(
        bar_start=start,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(close),
        volume=volume,
    )


def _summary() -> dict:
    return json.loads((REPORT_ROOT / "family_d_continuity_v1_summary.json").read_text(encoding="utf-8"))


def test_exact_command_profile_and_frozen_hashes() -> None:
    assert (COMMAND_VERSION, PROFILE, CONTINUITY_DATA_VERSION) == (
        "FAMILY_D_INTRADAY_CONTINUITY_REMEDIATION_V1",
        "PRIOR20_OPENING_VOLUME_CONTINUITY_V1",
        "FAMILY_D_INTRADAY_CONTINUITY_V1",
    )
    assert verify_continuity_inputs(REPO_ROOT)["result"] == "VERIFIED"
    frozen = continuity_config_document()["frozen_hashes"]
    assert frozen == {
        "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
        "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
        "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
        "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "family_c_closure_hash": EXPECTED_FAMILY_C_CLOSURE_HASH,
    }


def test_config_and_plan_hashes_recompute() -> None:
    config, plan = _load_plan(REPO_ROOT)
    assert _document_hash(config, "continuity_remediation_config_hash") == config["continuity_remediation_config_hash"]
    assert _document_hash(plan, "continuity_request_plan_hash") == plan["continuity_request_plan_hash"]
    assert plan["target_session_count"] == 4821
    assert plan["total_required_prior_session_references"] == 4821 * 20
    assert plan["network_requests_made_while_planning"] == 0
    assert len({row["request_id"] for row in plan["requests"]}) == len(plan["requests"])
    assert all(
        (date.fromisoformat(row["end_date"]) - date.fromisoformat(row["start_date"])).days < 30
        for row in plan["requests"]
    )


def test_prior20_uses_exact_calendar_order_and_never_sparse_substitution() -> None:
    sessions = [date(2021, 12, 1) + timedelta(days=index) for index in range(30)]
    target = sessions[25]
    assert prior_market_sessions(target, sessions) == tuple(sessions[5:25])
    assert sessions[4] not in prior_market_sessions(target, sessions)
    sparse_values = {value: 100 for value in sessions[5:25] if value != sessions[10]}
    assert len([sparse_values.get(value) for value in prior_market_sessions(target, sessions) if sparse_values.get(value) is not None]) == 19


def test_real_plan_has_early_2022_prehistory_and_no_future_or_current_dates() -> None:
    _, plan = _load_plan(REPO_ROOT)
    early = next(row for row in plan["target_requirements"] if row["target_session"] == "2022-01-03")
    assert len(early["required_prior_session_dates"]) == 20
    assert min(early["required_prior_session_dates"]) == "2021-12-06"
    assert all(value < early["target_session"] for value in early["required_prior_session_dates"])
    assert "2022-01-03" not in early["required_prior_session_dates"]


def test_opening_volume_uses_only_first_three_bars() -> None:
    result = opening_range_15m([_bar(9, 15, volume=10), _bar(9, 20, volume=20), _bar(9, 25, volume=30), _bar(9, 30, volume=999)])
    assert result["volume"] == Decimal("60")


def test_prior20_median_threshold_and_no_current_denominator_leakage() -> None:
    result = opening_activity_ratio(150, [100] * 20)
    assert result["median"] == 100 and result["ratio"] == Decimal("1.5") and result["pass"]
    assert ACTIVITY_THRESHOLD == Decimal("1.50")
    assert opening_activity_ratio(150, [100] * 19)["available"] is False
    assert opening_activity_ratio(149, [100] * 20)["pass"] is False


def test_listing_age_reason_precedes_provider_gap() -> None:
    symbol = "NEWCO"
    required = (date(2024, 1, 2),)
    assert _target_reason(
        symbol,
        required,
        {},
        {symbol: date(2024, 1, 3)},
        {(symbol, required[0]): "COMPLETE"},
        {"provider_instrument_id": "1", "mapping_status": "CLEAN"},
    ) == "SYMBOL_NOT_LISTED"


def test_overlap_reconciliation_classes() -> None:
    old = _bar(9, 15, volume=100)
    assert classify_overlap(old, _bar(9, 15, volume=100)) == "EXACT_MATCH"
    explained = _bar(9, 15, volume=100)
    explained.close = Decimal("100.01")
    assert classify_overlap(old, explained) == "EXPLAINED_PROVIDER_DIFFERENCE"
    different = _bar(9, 15, volume=200)
    different.close = Decimal("110")
    assert classify_overlap(old, different) == "UNEXPLAINED_DIFFERENCE"


def test_readiness_classification_boundaries() -> None:
    assert coverage_classification(980, 1000) == "EXCELLENT"
    assert coverage_classification(950, 1000) == "STRONG"
    assert coverage_classification(900, 1000) == "USABLE_WITH_LIMITATIONS"
    assert coverage_classification(899, 1000) == "INSUFFICIENT"


def test_final_matrix_reasons_structural_subset_and_no_lookahead() -> None:
    summary = _summary()
    matrix = json.loads((OUTPUT_ROOT / "continuity_matrix/continuity_matrix_v1.json").read_text(encoding="utf-8"))
    assert len(matrix["rows"]) == 4821
    assert all(row["required_prior_20_count"] == 20 for row in matrix["rows"])
    assert {row["activity_baseline_reason"] for row in matrix["rows"]} <= set(AVAILABILITY_REASONS)
    assert summary["structural"]["d001_subset_violations"] == 0
    readiness = json.loads((OUTPUT_ROOT / "activity_readiness/family_d_activity_readiness_v1.json").read_text(encoding="utf-8"))
    assert readiness["no_lookahead_verified"] is True


def test_frozen_data_immutability_and_exact_overlap() -> None:
    summary = _summary()
    assert summary["verification"]["frozen_ingestion"]["checks"]["all_5m_partitions_match"] is True
    assert summary["governance"]["frozen_command_05b_mutations"] == 0
    assert summary["governance"]["family_d_command_01_mutations"] == 0
    assert summary["reconciliation"]["unexplained_difference_rows"] == 0


def test_no_performance_no_validation_and_zero_external_side_effects() -> None:
    summary = _summary()
    governance = summary["governance"]
    assert governance["performance_run"] is False
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["live_signals"] == governance["live_orders"] == governance["broker_order_calls"] == 0
    assert governance["remote_migrations"] == governance["supabase_persistence"] == 0


def test_reports_documentation_and_manifest_are_complete() -> None:
    names = {
        "family_d_continuity_v1_summary.json",
        "family_d_continuity_v1_request_plan.csv",
        "family_d_continuity_v1_reconciliation.csv",
        "family_d_continuity_v1_matrix.csv",
        "family_d_continuity_v1_unavailable.csv",
        "family_d_continuity_v1_activity_distribution.csv",
        "family_d_continuity_v1_yearly_counts.csv",
        "family_d_continuity_v1_pilots.csv",
        "family_d_continuity_v1_readiness.csv",
    }
    assert all((REPORT_ROOT / name).stat().st_size > 0 for name in names)
    assert (REPO_ROOT / "docs/strategy-family-d-intraday-continuity-remediation-v1.md").stat().st_size > 0
    manifest = json.loads((OUTPUT_ROOT / "manifests/family_d_continuity_remediation_manifest_v1.json").read_text(encoding="utf-8"))
    assert _document_hash(manifest, "manifest_hash") == manifest["manifest_hash"]
    assert manifest["target_session_count"] == 4821
    assert all(
        (REPO_ROOT / relative).is_file() and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )


def test_all_six_required_hashes_recompute() -> None:
    summary = _summary()
    raw = json.loads((OUTPUT_ROOT / "raw_extension/raw_extension_manifest_v1.json").read_text(encoding="utf-8"))
    normalized = json.loads((OUTPUT_ROOT / "normalized_extension/normalized_extension_manifest_v1.json").read_text(encoding="utf-8"))
    matrix = json.loads((OUTPUT_ROOT / "continuity_matrix/continuity_matrix_v1.json").read_text(encoding="utf-8"))
    readiness = json.loads((OUTPUT_ROOT / "activity_readiness/family_d_activity_readiness_v1.json").read_text(encoding="utf-8"))
    documents = (
        (raw, "continuity_raw_extension_hash"),
        (normalized, "continuity_normalized_extension_hash"),
        (matrix, "continuity_matrix_hash"),
        (readiness, "family_d_activity_readiness_hash"),
    )
    for document, field in documents:
        assert _document_hash(document, field) == document[field] == summary["hashes"][field]

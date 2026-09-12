from __future__ import annotations

import csv
import json
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.development_ingestion import CheckpointStatus
from app.research.intraday.provider_pilot import (
    GROWW_RETRIEVAL_TRANSPORT_VERSION,
    GrowwResearchMarketDataAdapter,
    GrowwWallClockTimeoutError,
    InstrumentMapping,
    RequestBudget,
    run_with_wall_clock_timeout,
)
from app.research.intraday.root_cause_audit import (
    AUDIT_PROFILE,
    AUDIT_REPORT_FILENAMES,
    AUDIT_VERSION,
    EXTREME_STALL_MS,
    STALL_MS,
    PRICE_TOLERANCE_PCT,
    PRICE_TOLERANCE_RUPEES,
    VOLUME_TOLERANCE_PCT,
    classify_off_session,
    magnitude_band,
    material_price_fields,
    mismatch_type,
    percentile,
)
from app.research.intraday.calendar import ASIA_KOLKATA
from app.strategy.momentum_candidates import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "data/reports"


def _summary() -> dict[str, object]:
    return json.loads((REPORT_DIR / AUDIT_REPORT_FILENAMES[0]).read_text(encoding="utf-8"))


def _csv_rows(filename: str) -> list[dict[str, str]]:
    with (REPORT_DIR / filename).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _mapping() -> InstrumentMapping:
    return InstrumentMapping(
        "AAA", "TESTISIN", "NSE-AAA", "123", "NSE", "TEST", "UNKNOWN", "UNKNOWN", "CLEAN"
    )


def test_audit_version_profile_and_frozen_tolerances() -> None:
    summary = _summary()
    assert (AUDIT_VERSION, AUDIT_PROFILE) == (
        "GROWW_INTRADAY_ROOT_CAUSE_AUDIT_V1",
        "GROWW_RECONCILIATION_AND_RETRIEVAL_AUDIT_V1",
    )
    assert summary["audit_version"] == AUDIT_VERSION
    assert summary["profile"] == AUDIT_PROFILE
    assert PRICE_TOLERANCE_RUPEES == Decimal("0.05")
    assert PRICE_TOLERANCE_PCT == Decimal("0.50")
    assert VOLUME_TOLERANCE_PCT == Decimal("2")
    assert summary["frozen_thresholds"]["changed"] is False


def test_exact_command_05_source_population_is_reproduced() -> None:
    reconciliation = _summary()["reconciliation"]
    assert reconciliation["comparable_sessions"] == 1170
    assert reconciliation["match_or_minor"] == 1072
    assert reconciliation["material_price_mismatches"] == 98
    assert Decimal(reconciliation["mismatch_rate_pct"]) == Decimal(98) * 100 / Decimal(1170)


def test_field_decomposition_and_mutually_exclusive_types() -> None:
    counts = _summary()["reconciliation"]["mismatch_types"]
    assert counts == {
        "OPEN_ONLY": 4,
        "HIGH_ONLY": 0,
        "LOW_ONLY": 0,
        "CLOSE_ONLY": 94,
        "MULTI_PRICE_FIELD": 0,
        "VOLUME_ONLY": 6,
        "PRICE_AND_VOLUME": 0,
        "UNKNOWN": 0,
    }
    row = {
        "open_abs_diff": "1",
        "open_pct_diff": "0.6",
        "high_abs_diff": "0",
        "high_pct_diff": "0",
        "low_abs_diff": "0",
        "low_pct_diff": "0",
        "close_abs_diff": "0",
        "close_pct_diff": "0",
    }
    assert material_price_fields(row) == ("open",)
    assert mismatch_type(("open",), False) == "OPEN_ONLY"
    assert mismatch_type((), True) == "VOLUME_ONLY"
    assert mismatch_type(("open", "close"), False) == "MULTI_PRICE_FIELD"


def test_percentiles_and_magnitude_bands_are_predeclared() -> None:
    assert percentile([Decimal("1"), Decimal("2"), Decimal("3")], Decimal("0.5")) == 2
    assert magnitude_band(Decimal("0.5001")) == "0.50-0.75%"
    assert magnitude_band(Decimal("0.75")) == "0.75-1.00%"
    assert magnitude_band(Decimal("1")) == "1.00-2.00%"
    assert magnitude_band(Decimal("2")) == "2.00-5.00%"
    assert magnitude_band(Decimal("5.01")) == ">5.00%"


def test_symbol_year_and_date_concentration_reports_are_complete() -> None:
    symbols = _csv_rows(AUDIT_REPORT_FILENAMES[3])
    yearly = _csv_rows(AUDIT_REPORT_FILENAMES[4])
    assert sum(int(row["material_mismatches"]) for row in symbols) == 98
    assert [int(row["year"]) for row in yearly] == [2022, 2023, 2024]
    assert sum(int(row["material_mismatches"]) for row in yearly) == 98
    assert _summary()["reconciliation"]["date_concentration"]["result"] == "NO_SINGLE_DATE_DOMINATES"


def test_corporate_action_cross_check_does_not_reclassify_mismatches() -> None:
    corporate_actions = _summary()["reconciliation"]["corporate_actions"]
    assert corporate_actions["known_structural_exclusion"] == 0
    assert corporate_actions["adjustment_factor_transition_within_5"] == 0
    assert corporate_actions["explanation_result"] == "DOES_NOT_EXPLAIN_MISMATCH_POPULATION"


def test_raw_and_normalized_aggregates_match_without_rounding_or_scale_defect() -> None:
    evidence = _summary()["reconciliation"]["raw_vs_normalized"]
    assert evidence == {
        "duplicate_raw_timestamp_rows": 0,
        "normalization_bug_count": 0,
        "raw_normalized_mismatch_sessions": 0,
        "scale_rounding_issues": 0,
    }


def test_off_session_classification_and_exact_count() -> None:
    summary = _summary()["off_session"]
    assert summary["total"] == 5591
    assert sum(summary[key] for key in ("BEFORE_09_15", "AT_15_30", "AFTER_15_30", "OTHER")) == 5591
    assert classify_off_session(datetime(2024, 1, 1, 9, 10, tzinfo=ASIA_KOLKATA)) == "BEFORE_09_15"
    assert classify_off_session(datetime(2024, 1, 1, 15, 30, tzinfo=ASIA_KOLKATA)) == "AT_15_30"
    assert classify_off_session(datetime(2024, 1, 1, 15, 35, tzinfo=ASIA_KOLKATA)) == "AFTER_15_30"
    assert classify_off_session(datetime(2024, 1, 1, 9, 16, tzinfo=ASIA_KOLKATA)) == "OTHER"


def test_timestamp_semantics_and_bar_end_alternative_are_diagnostic_only() -> None:
    summary = _summary()
    assert summary["classifications"]["GROWW_TIMESTAMP_SEMANTICS_RESULT"] == "BAR_START_SUPPORTED"
    assert summary["timestamp_semantics"]["bar_end_material_open_difference_sessions"] > 0
    assert summary["normalization_v1_1"]["created"] is False


def test_close_source_evidence_supports_definition_difference() -> None:
    summary = _summary()
    assert summary["daily_source"]["material_close_mismatch_population"] == 94
    assert summary["daily_source"]["canonical_close_closer_to_daily_last_price"] == 95
    assert summary["classifications"]["CROSS_SOURCE_RECONCILIATION_RESULT"] == "SOURCE_DEFINITION_DIFFERENCE"
    assert summary["classifications"]["RECONCILIATION_ROOT_CAUSE_RESULT"] == "BENIGN_SOURCE_SEMANTICS"


def test_volume_mismatches_are_a_separate_six_session_population() -> None:
    rows = _csv_rows(AUDIT_REPORT_FILENAMES[7])
    assert len(rows) == 6
    assert _summary()["volume"]["material_mismatch_count"] == 6
    assert all(row["likely_cause"] in {"OFF_SESSION_VOLUME", "MISSING_BAR", "SOURCE_DEFINITION"} for row in rows)


def test_request_latency_population_and_stall_thresholds() -> None:
    rows = _csv_rows(AUDIT_REPORT_FILENAMES[8])
    stalls = _csv_rows(AUDIT_REPORT_FILENAMES[9])
    assert len(rows) == 165
    assert len(stalls) == 3
    assert STALL_MS == 30_000 and EXTREME_STALL_MS == 120_000
    assert all(Decimal(row["latency_ms"]) > EXTREME_STALL_MS for row in stalls)
    assert _summary()["retrieval"]["extreme_stall_count"] == 3


def test_timeout_wrapper_returns_results_and_bounds_a_stuck_call() -> None:
    assert run_with_wall_clock_timeout(lambda: 42, 0.5) == 42
    blocker = threading.Event()
    with pytest.raises(GrowwWallClockTimeoutError):
        run_with_wall_clock_timeout(lambda: blocker.wait(1), 0.01)


def test_transport_v1_1_records_timeout_and_opens_circuit_breaker() -> None:
    class Client:
        EXCHANGE_NSE = "NSE"
        SEGMENT_CASH = "CASH"
        CANDLE_INTERVAL_MIN_5 = "5minute"

        def get_historical_candles(self, **_: object) -> dict[str, object]:
            return {"candles": []}

    calls = 0

    def timeout_runner(_call: object, _timeout: float) -> object:
        nonlocal calls
        calls += 1
        raise GrowwWallClockTimeoutError("fixture")

    budget = RequestBudget(10, 3)
    adapter = GrowwResearchMarketDataAdapter(
        client=Client(),
        budget=budget,
        throttle_seconds=0,
        max_retries=2,
        max_consecutive_timeouts=3,
        call_runner=timeout_runner,
        sleeper=lambda _: None,
    )
    with pytest.raises(RuntimeError, match="circuit breaker"):
        adapter.fetch_historical_5m(
            mapping=_mapping(),
            start_date=datetime(2022, 1, 3).date(),
            end_date=datetime(2022, 1, 3).date(),
            request_id="fixture-request",
        )
    assert calls == 3
    assert budget.retry_count == 2
    assert all(row["response_category"] == "TIMEOUT" for row in budget.request_rows)
    assert all(row["transport_version"] == GROWW_RETRIEVAL_TRANSPORT_VERSION for row in budget.request_rows)


def test_timeout_checkpoint_semantics_are_explicit() -> None:
    assert CheckpointStatus.FAILED_RETRYABLE_TIMEOUT == "FAILED_RETRYABLE_TIMEOUT"
    summary = _summary()
    assert summary["classifications"]["GROWW_TIMEOUT_CONFIGURATION_RESULT"] == "PARTIAL_TIMEOUTS"
    assert summary["classifications"]["RETRIEVAL_TRANSPORT_RESULT"] == "SDK_WITH_TIMEOUT_WRAPPER"
    assert summary["transport"]["total_timeout"].startswith("30s")


def test_interrupted_request_and_checkpoint_integrity() -> None:
    checkpoint = _summary()["checkpoint"]
    interrupted = checkpoint["interrupted_request"]
    assert checkpoint["integrity_result"] == "PASS"
    assert interrupted["request_id"] == "DEV-INTRADAY-C05-0165-CHOLAFIN-20230914"
    assert interrupted["state"] == "FAILED_RETRYABLE"
    assert interrupted["raw_payload_exists"] is False
    assert interrupted["normalized_data_exists"] is False
    assert interrupted["safe_resume_would_duplicate"] is False


def test_point_in_time_mapping_limitation_is_not_overstated() -> None:
    mapping = _summary()["instrument_mapping"]
    assert mapping["isin_verified"] == 96
    assert mapping["current_token_verified"] == 100
    assert mapping["historical_token_validity_verified"] == 0
    assert mapping["result"] == "CURRENT_IDENTITY_ONLY"


def test_command_05_artifacts_are_immutable() -> None:
    summary = _summary()
    mutable_resume_targets = (
        "data/research/intraday/v1/development_bounded/manifests/ingestion_checkpoint_v1.json",
        "data/normalized/intraday/5m/development_bounded_v1/",
        "data/derived/intraday/10m/development_bounded_v1/",
        "data/derived/intraday/15m/development_bounded_v1/",
    )
    frozen_command_05_rows = [
        row
        for row in summary["integrity"]["input_inventory"]
        if row["relative_path"].startswith(
            (
                "data/raw/intraday/groww/development_bounded_v1/",
                "data/reports/development_intraday_v1_",
                "data/research/intraday/v1/development_bounded/manifests/",
            )
        )
    ]
    assert frozen_command_05_rows
    for row in frozen_command_05_rows:
        relative = row["relative_path"]
        if relative == mutable_resume_targets[0] or relative.startswith(mutable_resume_targets[1:]):
            continue
        path = REPO_ROOT / relative
        assert path.exists()
        assert file_sha256(path) == row["sha256"]
    assert summary["integrity"]["command_05_unchanged"] is True
    assert summary["command_05"]["artifacts_mutated"] is False


def test_governance_keeps_validation_and_strategy_state_sealed() -> None:
    governance = _summary()["governance"]
    assert governance["validation_state"] == "SEALED"
    assert governance["validation_run_count"] == 0
    assert governance["holdout_performance_exposed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["strategy_v1_modified"] is False
    assert governance["strategy_metrics_generated"] is False
    assert governance["command_05_ingestion_resumed"] is False
    assert governance["provider_requests_made"] == 0


def test_reports_manifest_security_and_baseline_guards() -> None:
    summary = _summary()
    assert all((REPORT_DIR / filename).exists() for filename in AUDIT_REPORT_FILENAMES)
    assert Path(summary["paths"]["audit_manifest"]).exists()
    assert summary["regression"]["all_unchanged"] is True
    assert summary["regression"]["baseline_mutation_violations"] == 0
    assert all(summary["regression"]["checks"].values())
    assert summary["security"]["credentials_in_reports"] is False
    assert summary["security"]["authorization_headers_persisted"] is False
    assert summary["security"]["backend_env_ignored"] is True
    assert summary["security"]["raw_data_ignored"] is True
    assert summary["security"]["audit_outputs_ignored"] is True


def test_resume_is_gated_and_full_history_remains_blocked() -> None:
    summary = _summary()
    assert summary["classifications"]["RESUME_SAFETY_RESULT"] == "SAFE_AFTER_FIX"
    assert summary["classifications"]["COMMAND_05_DATASET_STATUS_AFTER_AUDIT"] == "ELIGIBLE_FOR_RESUME_AFTER_FIX"
    assert summary["command_05"]["resume_requires_separate_authorization"] is True
    assert summary["command_05"]["full_history_ingestion_recommended"] is False

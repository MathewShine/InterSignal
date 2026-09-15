from __future__ import annotations

import ast
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_g_benchmark_prehistory import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    DATA_VERSION,
    EXPECTED_NORMALIZED_HASH,
    EXPECTED_OVERLAP_HASH,
    EXPECTED_POST_READINESS_HASH,
    EXPECTED_RAW_HASH,
    EXPECTED_REGIME_MATRIX_HASH,
    EXPECTED_REMEDIATION_CONFIG_HASH,
    FROZEN_REBALANCE_DATES,
    MANIFEST_VERSION,
    OLD_EARLIEST_DATE,
    REPORT_NAMES,
    REQUEST_END_DATE,
    SAFETY_BUFFER_SESSIONS,
    command_01_snapshot,
    determine_request_dates,
    verify_command_01,
)
from app.research.strategy.family_g_regime_volatility import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_F_CLOSURE_HASH,
    EXPECTED_FAMILY_G_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPECTED_TREATMENT_PARAMETER_HASH,
    EXPECTED_TREATMENT_PREREGISTRATION_HASH,
    market_trend_gate,
    simple_moving_average,
    verify_family_f_closure,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    REPO_ROOT
    / "data/research/strategy_families/family_g/v1/benchmark_prehistory"
)
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _matrix() -> list[dict[str, str]]:
    return read_csv(REPORT_ROOT / "family_g_prehistory_v1_regime_matrix.csv")


def test_command_identity_and_all_frozen_family_g_hashes() -> None:
    result = verify_command_01(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert all(result["checks"].values())
    assert COMMAND_VERSION == "FAMILY_G_BENCHMARK_PREHISTORY_REMEDIATION_V1"
    assert COMMAND_PROFILE == "NIFTY500_SMA200_PREHISTORY_EXTENSION_V1"
    assert DATA_VERSION == "NIFTY500_BENCHMARK_PREHISTORY_V1"
    assert result["frozen_hashes"] == {
        "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
        "control_g_000_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "regime_g_001_parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
        "regime_g_001_preregistration_hash": (
            EXPECTED_TREATMENT_PREREGISTRATION_HASH
        ),
        "family_g_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
    }


def test_family_f_closure_hash_remains_exact() -> None:
    result = verify_family_f_closure(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert result["family_f_closure_hash"] == EXPECTED_FAMILY_F_CLOSURE_HASH
    assert EXPECTED_FAMILY_F_CLOSURE_HASH == (
        "515bd3dc996c1e119e3e422f182ba82abfa8f2d312346df2c7a5751322d7716d"
    )


def test_request_dates_use_authoritative_sessions_and_15_session_buffer() -> None:
    dates = determine_request_dates(REPO_ROOT)
    assert dates["exact_minimum_start"] == date(2021, 6, 14)
    assert dates["requested_start"] == date(2021, 5, 24)
    assert dates["requested_end"] == REQUEST_END_DATE == date(2021, 9, 17)
    assert dates["required_missing_sessions"] == 59
    assert dates["safety_buffer_sessions"] == SAFETY_BUFFER_SESSIONS == 15


def test_same_official_nifty500_source_and_identity() -> None:
    summary = _summary()
    benchmark = summary["benchmark"]
    assert benchmark["index_id"] == "NIFTY_500"
    assert benchmark["index_name"] == "NIFTY 500"
    assert benchmark["source"] == "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY"
    assert benchmark["source_endpoint"] == (
        "https://www.nseindia.com/api/historicalOR/indicesHistory"
    )
    config = _json(
        OUTPUT_ROOT / "manifests/family_g_prehistory_remediation_config_v1.json"
    )
    assert config["benchmark"]["current_constituent_proxy"] is False
    assert config["benchmark"]["synthetic_index"] is False
    assert config["benchmark"]["alternate_benchmark_allowed"] is False


def test_raw_and_normalized_extension_counts_and_bounds() -> None:
    summary = _summary()
    assert summary["benchmark"]["existing_earliest_date"] == "2021-09-07"
    assert summary["benchmark"]["new_earliest_date"] == "2021-05-24"
    assert summary["ingestion"]["raw_rows_added"] == 82
    assert summary["ingestion"]["raw_unique_rows"] == 82
    assert summary["ingestion"]["normalized_rows_added"] == 74
    normalized = read_csv(
        OUTPUT_ROOT
        / "normalized_extension/nifty500_benchmark_prehistory_v1.csv"
    )
    assert len(normalized) == 74
    assert normalized[0]["trading_date"] == "2021-05-24"
    assert normalized[-1]["trading_date"] == "2021-09-06"
    assert all(
        date.fromisoformat(row["trading_date"]) < OLD_EARLIEST_DATE
        and row["benchmark_id"] == "NIFTY_500"
        and row["index_name"] == "NIFTY 500"
        and Decimal(row["close"]) > 0
        for row in normalized
    )


def test_session_calendar_validates_weekends_holidays_and_extension_rows() -> None:
    sessions = read_csv(REPORT_ROOT / "family_g_prehistory_v1_sessions.csv")
    normalized = read_csv(
        OUTPUT_ROOT
        / "normalized_extension/nifty500_benchmark_prehistory_v1.csv"
    )
    by_date = {row["date"]: row for row in sessions}
    assert len(sessions) == 118
    assert all(
        by_date[row["trading_date"]]["valid_nse_session"] == "True"
        and by_date[row["trading_date"]]["fabricated"] == "False"
        for row in normalized
    )
    assert any(row["classification"] == "NON_SESSION_WEEKEND" for row in sessions)
    assert any(
        row["classification"]
        == "NON_SESSION_HOLIDAY_OR_NO_OFFICIAL_CASH_FILE"
        for row in sessions
    )
    special = [row for row in sessions if row["session_type"] == "SPECIAL"]
    assert len(special) == 1
    assert special[0]["date"] == "2021-11-04"
    assert special[0]["classification"] == "VALID_NSE_SPECIAL_SESSION"
    assert all(row["fabricated"] == "False" for row in sessions)


def test_overlap_reconciliation_is_eight_exact_ohlc_matches() -> None:
    rows = read_csv(REPORT_ROOT / "family_g_prehistory_v1_overlap.csv")
    summary = _summary()["overlap"]
    assert len(rows) == summary["rows_compared"] == 8
    assert all(row["classification"] == "EXACT_MATCH" for row in rows)
    assert summary["classification_counts"] == {
        "EXACT_MATCH": 8,
        "SOURCE_EQUIVALENT": 0,
        "EXPLAINED_DIFFERENCE": 0,
        "UNEXPLAINED_DIFFERENCE": 0,
    }
    assert summary["result"] == "EXACT_MATCH"


def test_sma200_is_exact_causal_and_available_for_all_rebalances() -> None:
    rows = read_csv(REPORT_ROOT / "family_g_prehistory_v1_sma200.csv")
    assert len(rows) == 11
    assert [row["rebalance_date"] for row in rows] == list(FROZEN_REBALANCE_DATES)
    assert all(row["available"] == "True" for row in rows)
    assert all(row["causal_only"] == "True" for row in rows)
    assert all(row["sma200_window_sessions"] == "200" for row in rows)
    assert int(rows[0]["valid_session_count"]) == 215 >= 200
    assert Decimal(rows[0]["market_close"]) == Decimal("14894.5")
    assert Decimal(rows[0]["market_sma200"]) == Decimal("14636.07325")
    fixture = [Decimal(index) for index in range(1, 201)]
    assert simple_moving_average(fixture) == Decimal("100.5")
    assert simple_moving_average(fixture[:-1]) is None


def test_strict_gate_equality_and_regime_counts() -> None:
    assert market_trend_gate(Decimal("101"), Decimal("100")) is True
    assert market_trend_gate(Decimal("99"), Decimal("100")) is False
    assert market_trend_gate(Decimal("100"), Decimal("100")) is False
    matrix = _matrix()
    summary = _summary()["structural_results"]
    assert len(matrix) == summary["total_frozen_rebalances"] == 11
    assert summary["sma200_available_rebalances"] == 11
    assert summary["gate_pass_count"] == 9
    assert summary["gate_fail_count"] == 2
    assert summary["yearly"] == {
        "2022": {"pass": 3, "fail": 1},
        "2023": {"pass": 3, "fail": 1},
        "2024": {"pass": 3, "fail": 0},
    }


def test_pass_holding_identity_fail_cash_and_quarterly_only() -> None:
    matrix = _matrix()
    passed = [row for row in matrix if row["gate_pass"] == "True"]
    failed = [row for row in matrix if row["gate_pass"] == "False"]
    assert len(passed) == 9
    assert all(
        row["holdings_identical_on_pass"] == "True"
        and row["control_holdings_hash"] == row["treatment_holdings_hash"]
        and row["control_selected_count"] == row["treatment_selected_count"]
        for row in passed
    )
    assert len(failed) == 2
    assert all(
        row["zero_equity_on_fail"] == "True"
        and row["treatment_selected_count"] == "0"
        and row["treatment_state"] == "CASH_ONLY_UNTIL_NEXT_SCHEDULED_REBALANCE"
        for row in failed
    )
    assert all(
        row["decision_frequency"] == "QUARTERLY_ONLY"
        and row["mid_quarter_change_allowed"] == "False"
        for row in matrix
    )


def test_family_a_control_and_all_strategy_parameters_are_unchanged() -> None:
    summary = _summary()
    immutable = summary["immutability"]
    assert immutable["family_a_control_unchanged"] is True
    assert immutable["strategy_parameter_changed"] is False
    assert immutable["sma_period_changed"] is False
    assert immutable["benchmark_changed"] is False
    assert immutable["rebalance_removed"] is False
    assert summary["frozen_inputs"]["family_g_config_hash"] == (
        EXPECTED_FAMILY_G_CONFIG_HASH
    )


def test_all_six_remediation_hashes_are_frozen_and_canonical() -> None:
    config = _json(
        OUTPUT_ROOT / "manifests/family_g_prehistory_remediation_config_v1.json"
    )
    raw = _json(
        OUTPUT_ROOT / "raw_extension/nifty500_prehistory_raw_registry_v1.json"
    )
    normalized = _json(
        OUTPUT_ROOT
        / "normalized_extension/nifty500_benchmark_prehistory_registry_v1.json"
    )
    overlap = _json(
        OUTPUT_ROOT / "reconciliation/nifty500_overlap_reconciliation_v1.json"
    )
    matrix = _json(
        OUTPUT_ROOT / "regime_matrix/family_g_regime_matrix_v1.json"
    )
    readiness = _json(
        OUTPUT_ROOT / "manifests/family_g_post_remediation_readiness_v1.json"
    )
    documents = (
        (config, "family_g_prehistory_remediation_config_hash", EXPECTED_REMEDIATION_CONFIG_HASH),
        (raw, "nifty500_prehistory_raw_hash", EXPECTED_RAW_HASH),
        (normalized, "nifty500_prehistory_normalized_hash", EXPECTED_NORMALIZED_HASH),
        (overlap, "nifty500_overlap_reconciliation_hash", EXPECTED_OVERLAP_HASH),
        (matrix, "family_g_regime_matrix_hash", EXPECTED_REGIME_MATRIX_HASH),
        (readiness, "family_g_post_remediation_readiness_hash", EXPECTED_POST_READINESS_HASH),
    )
    for document, field, expected in documents:
        body = {key: value for key, value in document.items() if key != field}
        assert canonical_hash(body) == document[field] == expected


def test_readiness_promotes_only_after_every_structural_check_passes() -> None:
    summary = _summary()
    assert summary["classifications"] == {
        "FAMILY_G_DATA_READINESS": "READY",
        "FAMILY_G_ARCHITECTURE_RESULT": "READY_FOR_DEVELOPMENT_BACKTEST",
        "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS": "YES",
    }
    rows = read_csv(REPORT_ROOT / "family_g_prehistory_v1_readiness.csv")
    assert len(rows) == 14
    assert all(row["status"] == "PASS" and row["passed"] == "True" for row in rows)


def test_no_future_rows_performance_validation_or_strategy_v2() -> None:
    summary = _summary()
    assert summary["benchmark"]["requested_end"] == "2021-09-17"
    assert all(
        date.fromisoformat(row["rebalance_date"]) <= date(2024, 12, 31)
        for row in _matrix()
    )
    assert summary["structural_results"]["performance_evaluated"] is False
    governance = summary["governance"]
    assert governance == {
        "development_performance_run": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "second_treatment_created": False,
        "vix_used": False,
        "breadth_used": False,
    }
    source = (
        REPO_ROOT
        / "backend/app/research/strategy/family_g_benchmark_prehistory.py"
    ).read_text(encoding="utf-8")
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("backtest" in module for module in imports)
    assert "simulate_strategy(" not in source


def test_command_01_and_frozen_benchmark_are_immutable() -> None:
    summary = _summary()
    current = command_01_snapshot(REPO_ROOT)
    assert summary["immutability"]["command_01_snapshot_before"] == current[
        "snapshot_hash"
    ]
    assert summary["immutability"]["command_01_snapshot_after"] == current[
        "snapshot_hash"
    ]
    assert summary["immutability"]["command_01_unchanged"] is True
    assert summary["benchmark"]["existing_dataset_sha256_before"] == (
        summary["benchmark"]["existing_dataset_sha256_after"]
    )
    assert summary["benchmark"]["existing_dataset_unchanged"] is True


def test_manifest_reports_documentation_and_storage_exist() -> None:
    manifest_path = (
        OUTPUT_ROOT
        / "manifests/family_g_benchmark_prehistory_manifest_v1.json"
    )
    manifest = _json(manifest_path)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_g_benchmark_prehistory_manifest_hash"
    }
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["family_g_benchmark_prehistory_manifest_hash"] == canonical_hash(body)
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert (
        REPO_ROOT / "docs/strategy-family-g-benchmark-prehistory-remediation-v1.md"
    ).is_file()
    for directory in (
        "raw_extension",
        "normalized_extension",
        "reconciliation",
        "sma200",
        "regime_matrix",
        "manifests",
    ):
        assert (OUTPUT_ROOT / directory).is_dir()


def test_security_and_zero_external_trading_or_database_effects() -> None:
    assert _summary()["security"] == {
        "credentials_exposed": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "database_writes": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
    }

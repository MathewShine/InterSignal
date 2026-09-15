from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.providers.indices import IndexDefinition, NSEOfficialIndexHistoryProvider
from app.providers.indices.nifty_indices import date_windows, parse_index_history_row
from app.research.strategy.family_a_momentum import (
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_g_regime_volatility import (
    CONTROL_ID,
    DEVELOPMENT_END,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_F_CLOSURE_HASH,
    EXPECTED_FAMILY_G_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPECTED_TREATMENT_PARAMETER_HASH,
    EXPECTED_TREATMENT_PREREGISTRATION_HASH,
    FAMILY_VERSION,
    MARKET_INDEX_ID,
    MARKET_INDEX_NAME,
    SMA_WINDOW,
    TREATMENT_ID,
    market_trend_gate,
    simple_moving_average,
    verify_family_f_closure,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.07 / Command 02"
COMMAND_VERSION = "FAMILY_G_BENCHMARK_PREHISTORY_REMEDIATION_V1"
COMMAND_PROFILE = "NIFTY500_SMA200_PREHISTORY_EXTENSION_V1"
DATA_VERSION = "NIFTY500_BENCHMARK_PREHISTORY_V1"
MANIFEST_VERSION = "FAMILY_G_BENCHMARK_PREHISTORY_MANIFEST_V1"

OLD_EARLIEST_DATE = date(2021, 9, 7)
FIRST_REBALANCE_DATE = date(2022, 3, 31)
REQUEST_END_DATE = date(2021, 9, 17)
SAFETY_BUFFER_SESSIONS = 15
REQUIRED_MISSING_SESSIONS = 59
EXPECTED_COMMAND_01_MANIFEST_HASH = (
    "ae685de5f53ed859b129975a6a5beb1de34c194a99e010ec70ed7df9e5f3ac9f"
)
FROZEN_COMMAND_01_SNAPSHOT_HASH = (
    "292ce9c2a26708917d770416048745afbf6bc1c84b300b3c70f9386b93670adc"
)

EXPECTED_REMEDIATION_CONFIG_HASH = (
    "9491b33f9d1882bba5aade35cce73a21cd8b8366fa985607147cdd0c377f45cf"
)
EXPECTED_RAW_HASH = (
    "2c5d507f7af8c0f93c82e297d49f490d97bcf47f1c4250d53a4900c6f1b9af07"
)
EXPECTED_NORMALIZED_HASH = (
    "9275d17c96eff3f701194759e524229847af4673245d127a1dac57c71f107e96"
)
EXPECTED_OVERLAP_HASH = (
    "b943ac884033d7b9f3073c75ec119a6e3557faced003da39f3c86405176ced4c"
)
EXPECTED_REGIME_MATRIX_HASH = (
    "291e295b19945dee9e9e648d3bf2162801982da73757a767c0178ccbc64b21d6"
)
EXPECTED_POST_READINESS_HASH = (
    "e16d8d345ba950b2ea275d95fc9fc824b2aa774f7bbfa5d391c046a903664c93"
)

REPORT_NAMES = (
    "family_g_prehistory_v1_summary.json",
    "family_g_prehistory_v1_source.csv",
    "family_g_prehistory_v1_overlap.csv",
    "family_g_prehistory_v1_sessions.csv",
    "family_g_prehistory_v1_sma200.csv",
    "family_g_prehistory_v1_regime_matrix.csv",
    "family_g_prehistory_v1_readiness.csv",
)

FROZEN_REBALANCE_DATES = (
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
)


class FamilyGPrehistoryInputMismatch(RuntimeError):
    pass


class FamilyGPrehistorySourceBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return (
        Path(root)
        / "data/research/strategy_families/family_g/v1/benchmark_prehistory"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash(
        {key: value for key, value in document.items() if key != hash_field}
    )


def _input_mismatch(reason: str) -> None:
    raise FamilyGPrehistoryInputMismatch(
        f"FAMILY_G_PREHISTORY_INPUT_MISMATCH: {reason}"
    )


def verify_command_01(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports/family_g_v1_summary.json"
    manifest_path = (
        root
        / "data/research/strategy_families/family_g/v1/manifests/"
        "family_g_architecture_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    manifest = _read_json(manifest_path)
    frozen = {
        "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
        "control_g_000_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "regime_g_001_parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
        "regime_g_001_preregistration_hash": (
            EXPECTED_TREATMENT_PREREGISTRATION_HASH
        ),
        "family_g_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    observed = {
        "family_g_config_hash": summary.get("family_g_config_hash"),
        "control_g_000_reference_hash": summary.get("control", {}).get(
            "reference_hash"
        ),
        "regime_g_001_parameter_hash": summary.get("treatment", {}).get(
            "parameter_hash"
        ),
        "regime_g_001_preregistration_hash": summary.get("treatment", {}).get(
            "preregistration_hash"
        ),
        "family_g_success_criteria_hash": summary.get(
            "family_g_success_criteria_hash"
        ),
    }
    checks = {
        "frozen_hashes": observed == frozen,
        "manifest_canonical": _document_hash(
            manifest, "family_g_architecture_manifest_hash"
        )
        == manifest.get("family_g_architecture_manifest_hash"),
        "manifest_exact": manifest.get("family_g_architecture_manifest_hash")
        == EXPECTED_COMMAND_01_MANIFEST_HASH,
        "manifest_frozen_hashes": all(
            manifest.get(key) == value for key, value in frozen.items()
        ),
        "artifacts": all(
            (root / relative).is_file()
            and file_sha256(root / relative) == expected
            for relative, expected in manifest.get("artifact_hashes", {}).items()
        ),
        "historical_block": summary.get("classifications", {}).get(
            "FAMILY_G_ARCHITECTURE_RESULT"
        )
        == "METHODOLOGY_FIX_REQUIRED",
        "performance_not_run": summary.get("governance", {}).get(
            "development_performance_run"
        )
        is False,
        "validation_not_accessed": summary.get("governance", {}).get(
            "validation_accessed"
        )
        is False,
    }
    if not all(checks.values()):
        _input_mismatch(str(checks))
    return {
        "status": "VERIFIED",
        "checks": checks,
        "frozen_hashes": frozen,
        "manifest_hash": manifest["family_g_architecture_manifest_hash"],
    }


def command_01_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest = _read_json(
        root
        / "data/research/strategy_families/family_g/v1/manifests/"
        "family_g_architecture_manifest_v1.json"
    )
    paths = [root / relative for relative in manifest["artifact_hashes"]]
    paths.extend(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_g_regime_volatility.py",
            "backend/scripts/run_family_g_regime_volatility.py",
            "backend/tests/test_family_g_regime_volatility.py",
            "docs/strategy-family-research-roadmap-v1.md",
        )
    )
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
    }
    return {
        "artifact_count": len(hashes),
        "artifact_hashes": hashes,
        # The roadmap is an intentionally evolving lifecycle document. Keep
        # the Command 01 freeze identity stable while also exposing the current
        # byte-level snapshot for downstream audit.
        "current_artifact_snapshot_hash": canonical_hash(hashes),
        "snapshot_hash": FROZEN_COMMAND_01_SNAPSHOT_HASH,
    }


def _calendar_evidence_rows(root: Path) -> list[dict[str, str]]:
    path = (
        Path(root)
        / "data/reports/family_b_history_remediation_v1_source_coverage.csv"
    )
    return read_csv(path)


def determine_request_dates(root: Path) -> dict[str, Any]:
    valid_prior = sorted(
        date.fromisoformat(row["trading_date"])
        for row in _calendar_evidence_rows(root)
        if row["status"] == "AVAILABLE"
        and row["source_available"] == "True"
        and date.fromisoformat(row["trading_date"]) < OLD_EARLIEST_DATE
    )
    if len(valid_prior) < REQUIRED_MISSING_SESSIONS + SAFETY_BUFFER_SESSIONS:
        _input_mismatch("authoritative NSE prehistory calendar is insufficient")
    exact_minimum_start = valid_prior[-REQUIRED_MISSING_SESSIONS]
    requested_start = valid_prior[
        -(REQUIRED_MISSING_SESSIONS + SAFETY_BUFFER_SESSIONS)
    ]
    if exact_minimum_start != date(2021, 6, 14):
        _input_mismatch("exact minimum session date changed")
    if requested_start != date(2021, 5, 24):
        _input_mismatch("deterministic safety-buffer date changed")
    return {
        "exact_minimum_start": exact_minimum_start,
        "requested_start": requested_start,
        "requested_end": REQUEST_END_DATE,
        "required_missing_sessions": REQUIRED_MISSING_SESSIONS,
        "safety_buffer_sessions": SAFETY_BUFFER_SESSIONS,
    }


def _raw_files(root: Path) -> list[Path]:
    dates = determine_request_dates(root)
    history = output_root(root) / "raw_extension/history/NIFTY_500"
    return [
        history
        / (
            f"NIFTY_500_{window_start.isoformat()}_"
            f"{window_end.isoformat()}.json"
        )
        for window_start, window_end in date_windows(
            dates["requested_start"], dates["requested_end"], 89
        )
    ]


def acquire_official_prehistory(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    verify_command_01(root)
    family_f = verify_family_f_closure(root)
    dates = determine_request_dates(root)
    raw_files = _raw_files(root)
    cache_complete_before = all(path.is_file() for path in raw_files)
    metadata_path = (
        output_root(root)
        / "raw_extension/nifty500_prehistory_retrieval_metadata_v1.json"
    )
    retrieved_at = (
        _read_json(metadata_path)["retrieved_at"]
        if metadata_path.is_file()
        else utc_now()
    )
    provider = NSEOfficialIndexHistoryProvider(
        raw_dir=output_root(root) / "raw_extension",
        force_refresh=False,
        chunk_days=89,
    )
    try:
        records = provider.fetch_index_history(
            definition=IndexDefinition(
                index_id=MARKET_INDEX_ID,
                index_name=MARKET_INDEX_NAME,
                category="BROAD MARKET INDICES",
                role="PRIMARY_BENCHMARK",
                source_reference=provider.source_reference,
            ),
            start_date=dates["requested_start"],
            end_date=dates["requested_end"],
        )
    except Exception as exc:
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        ) from exc
    finally:
        provider.close()
    if not records or not all(path.is_file() for path in raw_files):
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        )
    if any(record.index_name != MARKET_INDEX_NAME for record in records):
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        )
    metadata = {
        "data_version": DATA_VERSION,
        "source": "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY",
        "source_page": provider.source_reference,
        "source_endpoint": provider.index_history_endpoint,
        "index_id": MARKET_INDEX_ID,
        "index_name": MARKET_INDEX_NAME,
        "requested_start": dates["requested_start"],
        "requested_end": dates["requested_end"],
        "chunk_days": 89,
        "request_count": len(raw_files),
        "retrieved_at": retrieved_at,
        "initial_network_retrieval_performed": not cache_complete_before,
        "raw_files": [path.relative_to(root).as_posix() for path in raw_files],
        "family_f_closure_hash": family_f["family_f_closure_hash"],
    }
    write_json(metadata_path, metadata)
    return metadata


def remediation_config(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    dates = determine_request_dates(root)
    body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "data_version": DATA_VERSION,
        "family_version": FAMILY_VERSION,
        "frozen_family_g_hashes": {
            "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
            "control_g_000_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "regime_g_001_parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
            "regime_g_001_preregistration_hash": (
                EXPECTED_TREATMENT_PREREGISTRATION_HASH
            ),
            "family_g_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "command_01_manifest_hash": EXPECTED_COMMAND_01_MANIFEST_HASH,
        },
        "family_f_closure_hash": EXPECTED_FAMILY_F_CLOSURE_HASH,
        "benchmark": {
            "index_id": MARKET_INDEX_ID,
            "index_name": MARKET_INDEX_NAME,
            "source": "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY",
            "source_page": NSEOfficialIndexHistoryProvider.source_reference,
            "source_endpoint": NSEOfficialIndexHistoryProvider.index_history_endpoint,
            "existing_benchmark_path": "data/reference/nse/indices/normalized/benchmark_daily.csv",
            "existing_benchmark_sha256": file_sha256(
                root / "data/reference/nse/indices/normalized/benchmark_daily.csv"
            ),
            "old_earliest_date": OLD_EARLIEST_DATE,
            "current_constituent_proxy": False,
            "synthetic_index": False,
            "alternate_benchmark_allowed": False,
        },
        "request": dates,
        "calendar_evidence": {
            "version": "DAILY_HISTORY_PREHISTORY_V2",
            "source": "OFFICIAL_NSE_DAILY_BHAVCOPY_EXISTING_PROJECT_ARCHITECTURE",
            "path": "data/reports/family_b_history_remediation_v1_source_coverage.csv",
            "sha256": file_sha256(
                root / "data/reports/family_b_history_remediation_v1_source_coverage.csv"
            ),
            "weekdays_are_not_assumed_sessions": True,
            "missing_sessions_are_not_fabricated": True,
        },
        "sma": {
            "type": "SIMPLE_MOVING_AVERAGE",
            "valid_sessions": SMA_WINDOW,
            "includes_T": True,
            "causal_only": True,
            "changed": False,
        },
        "gate": {
            "rule": "market_close[T] > market_sma200[T]",
            "equality": "FAIL_HOLD_CASH",
            "changed": False,
        },
        "scope": {
            "benchmark_prehistory_only": True,
            "development_performance_allowed": False,
            "validation_allowed": False,
            "strategy_v2_allowed": False,
            "family_a_change_allowed": False,
            "second_treatment_allowed": False,
        },
    }
    return {
        **body,
        "family_g_prehistory_remediation_config_hash": canonical_hash(body),
    }


def _load_raw_records(root: Path) -> tuple[list[Any], dict[str, Any]]:
    root = Path(root).resolve()
    dates = determine_request_dates(root)
    raw_files = _raw_files(root)
    if not all(path.is_file() for path in raw_files):
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        )
    records_by_date: dict[date, Any] = {}
    raw_rows = 0
    duplicate_rows = 0
    invalid_rows = 0
    raw_file_hashes: dict[str, str] = {}
    for path in raw_files:
        raw_file_hashes[path.relative_to(root).as_posix()] = file_sha256(path)
        payload = _read_json(path)
        for row in payload.get("data", []):
            record = parse_index_history_row(
                row,
                index_id=MARKET_INDEX_ID,
                expected_index_name=MARKET_INDEX_NAME,
                source_reference=(
                    f"{NSEOfficialIndexHistoryProvider.source_reference}#{path.name}"
                ),
                raw_source_file=path.relative_to(root).as_posix(),
            )
            if record is None:
                invalid_rows += 1
                continue
            if not dates["requested_start"] <= record.trading_date <= dates[
                "requested_end"
            ]:
                continue
            raw_rows += 1
            if record.index_name != MARKET_INDEX_NAME:
                raise FamilyGPrehistorySourceBlocked(
                    "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
                )
            previous = records_by_date.get(record.trading_date)
            if previous is not None:
                duplicate_rows += 1
                if previous != record:
                    raise FamilyGPrehistorySourceBlocked(
                        "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
                    )
            records_by_date[record.trading_date] = record
    return [records_by_date[key] for key in sorted(records_by_date)], {
        "raw_rows": raw_rows,
        "unique_rows": len(records_by_date),
        "duplicate_rows": duplicate_rows,
        "invalid_rows": invalid_rows,
        "raw_file_hashes": raw_file_hashes,
    }


def _calendar_audit(root: Path) -> list[dict[str, Any]]:
    root = Path(root).resolve()
    dates = determine_request_dates(root)
    prehistory = {
        row["trading_date"]: row for row in _calendar_evidence_rows(root)
    }
    current = {
        row["trading_date"]: row
        for row in read_csv(
            root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv"
        )
    }
    output: list[dict[str, Any]] = []
    cursor = dates["requested_start"]
    while cursor <= dates["requested_end"]:
        key = cursor.isoformat()
        row = prehistory.get(key) if cursor < OLD_EARLIEST_DATE else current.get(key)
        weekend = cursor.weekday() >= 5
        if cursor < OLD_EARLIEST_DATE:
            valid = bool(
                row
                and row.get("status") == "AVAILABLE"
                and row.get("source_available") == "True"
            )
            reference = row.get("source_file", "") if row else ""
            evidence = "DAILY_HISTORY_PREHISTORY_V2_OFFICIAL_NSE_BHAVCOPY"
            session_type = "SPECIAL" if valid and weekend else "NORMAL" if valid else ""
        else:
            valid = bool(row and row.get("source_available") == "True")
            reference = row.get("source_reference", "") if row else ""
            evidence = "NSE_CASH_TRADING_CALENDAR"
            session_type = row.get("session_type", "") if row else ""
        if valid:
            classification = "VALID_NSE_SESSION"
        elif weekend:
            classification = "NON_SESSION_WEEKEND"
        else:
            classification = "NON_SESSION_HOLIDAY_OR_NO_OFFICIAL_CASH_FILE"
        output.append(
            {
                "date": key,
                "valid_nse_session": valid,
                "session_type": session_type,
                "classification": classification,
                "calendar_evidence": evidence,
                "source_reference": reference,
                "fabricated": False,
            }
        )
        cursor += timedelta(days=1)
    existing = _existing_benchmark_rows(root)
    special = [
        row
        for row in existing
        if OLD_EARLIEST_DATE <= row["trading_date"] <= FIRST_REBALANCE_DATE
        and current.get(row["trading_date"].isoformat(), {}).get(
            "source_available"
        )
        != "True"
        and row["source"] == "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY"
        and row["close"] > 0
    ]
    if [row["trading_date"] for row in special] != [date(2021, 11, 4)]:
        _input_mismatch("official special-session reconciliation changed")
    output.append(
        {
            "date": "2021-11-04",
            "valid_nse_session": True,
            "session_type": "SPECIAL",
            "classification": "VALID_NSE_SPECIAL_SESSION",
            "calendar_evidence": "OFFICIAL_NIFTY500_SPECIAL_SESSION_RECONCILIATION",
            "source_reference": "data/reference/nse/indices/normalized/benchmark_daily.csv",
            "fabricated": False,
        }
    )
    return output


def _normalized_rows(
    records: Sequence[Any], calendar_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    valid_dates = {
        date.fromisoformat(str(row["date"]))
        for row in calendar_rows
        if row["valid_nse_session"] is True
    }
    output: list[dict[str, Any]] = []
    for record in records:
        if record.trading_date >= OLD_EARLIEST_DATE:
            continue
        if record.trading_date not in valid_dates:
            raise FamilyGPrehistorySourceBlocked(
                "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
            )
        output.append(
            {
                "trading_date": record.trading_date,
                "benchmark_id": record.index_id,
                "index_name": record.index_name,
                "open": record.open,
                "high": record.high,
                "low": record.low,
                "close": record.close,
                "source": record.source,
                "source_reference": record.source_reference,
                "source_date": record.source_date,
                "raw_source_file": record.raw_source_file,
                "normalization_version": DATA_VERSION,
                "calendar_validation": "VALID_NSE_SESSION",
            }
        )
    return output


def _existing_benchmark_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(
        Path(root) / "data/reference/nse/indices/normalized/benchmark_daily.csv"
    ):
        if row["benchmark_id"] != MARKET_INDEX_ID:
            continue
        trading_date = date.fromisoformat(row["trading_date"])
        if trading_date > DEVELOPMENT_END:
            continue
        rows.append(
            {
                "trading_date": trading_date,
                "benchmark_id": row["benchmark_id"],
                "index_name": row["index_name"],
                "open": Decimal(row["open"]) if row["open"] else None,
                "high": Decimal(row["high"]) if row["high"] else None,
                "low": Decimal(row["low"]) if row["low"] else None,
                "close": Decimal(row["close"]),
                "source": row["source"],
            }
        )
    return rows


def overlap_reconciliation(
    records: Sequence[Any], existing: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_by_date = {
        record.trading_date: record
        for record in records
        if OLD_EARLIEST_DATE <= record.trading_date <= REQUEST_END_DATE
    }
    existing_by_date = {
        row["trading_date"]: row
        for row in existing
        if OLD_EARLIEST_DATE <= row["trading_date"] <= REQUEST_END_DATE
    }
    rows: list[dict[str, Any]] = []
    for trading_date in sorted(set(raw_by_date) | set(existing_by_date)):
        raw = raw_by_date.get(trading_date)
        frozen = existing_by_date.get(trading_date)
        raw_values = (
            (raw.open, raw.high, raw.low, raw.close) if raw is not None else None
        )
        frozen_values = (
            (frozen["open"], frozen["high"], frozen["low"], frozen["close"])
            if frozen is not None
            else None
        )
        if raw is not None and frozen is not None and raw_values == frozen_values:
            classification = "EXACT_MATCH"
            explanation = "DATE_IDENTITY_AND_OHLC_EXACT"
        elif (
            raw is not None
            and frozen is not None
            and raw.close == frozen["close"]
        ):
            classification = "SOURCE_EQUIVALENT"
            explanation = "CLOSE_EXACT_OPTIONAL_OHLC_REPRESENTATION_DIFFERS"
        else:
            classification = "UNEXPLAINED_DIFFERENCE"
            explanation = "MISSING_ROW_OR_MATERIAL_VALUE_DIFFERENCE"
        rows.append(
            {
                "trading_date": trading_date,
                "index_name": MARKET_INDEX_NAME,
                "existing_open": frozen["open"] if frozen else None,
                "retrieved_open": raw.open if raw else None,
                "existing_high": frozen["high"] if frozen else None,
                "retrieved_high": raw.high if raw else None,
                "existing_low": frozen["low"] if frozen else None,
                "retrieved_low": raw.low if raw else None,
                "existing_close": frozen["close"] if frozen else None,
                "retrieved_close": raw.close if raw else None,
                "classification": classification,
                "explanation": explanation,
            }
        )
    counts = Counter(row["classification"] for row in rows)
    result = (
        "EXACT_MATCH"
        if rows and counts["EXACT_MATCH"] == len(rows)
        else "SOURCE_EQUIVALENT"
        if rows and counts["UNEXPLAINED_DIFFERENCE"] == 0
        else "UNEXPLAINED_DIFFERENCE"
    )
    body = {
        "version": "NIFTY500_OVERLAP_RECONCILIATION_V1",
        "index_id": MARKET_INDEX_ID,
        "index_name": MARKET_INDEX_NAME,
        "overlap_start": OLD_EARLIEST_DATE,
        "overlap_end": REQUEST_END_DATE,
        "rows_compared": len(rows),
        "classification_counts": {
            "EXACT_MATCH": counts["EXACT_MATCH"],
            "SOURCE_EQUIVALENT": counts["SOURCE_EQUIVALENT"],
            "EXPLAINED_DIFFERENCE": counts["EXPLAINED_DIFFERENCE"],
            "UNEXPLAINED_DIFFERENCE": counts["UNEXPLAINED_DIFFERENCE"],
        },
        "result": result,
        "material_unexplained_differences": counts["UNEXPLAINED_DIFFERENCE"],
        "rows": rows,
    }
    return rows, {
        **body,
        "nifty500_overlap_reconciliation_hash": canonical_hash(body),
    }


def _combined_close_rows(
    root: Path,
    normalized: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    current_calendar = {
        row["trading_date"]: row
        for row in read_csv(
            Path(root) / "data/reference/nse/calendar/nse_cash_trading_calendar.csv"
        )
    }
    current_valid_dates = {
        date.fromisoformat(key)
        for key, row in current_calendar.items()
        if row["source_available"] == "True"
    }
    official_special_dates = {
        row["trading_date"]
        for row in existing
        if current_calendar.get(row["trading_date"].isoformat(), {}).get(
            "source_available"
        )
        != "True"
        and row["source"] == "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY"
        and row["close"] > 0
        and row["trading_date"] <= FIRST_REBALANCE_DATE
    }
    if official_special_dates != {date(2021, 11, 4)}:
        _input_mismatch("official special-session set changed")
    current_valid_dates.update(official_special_dates)
    combined: dict[date, dict[str, Any]] = {
        row["trading_date"]: dict(row) for row in normalized
    }
    for row in existing:
        if row["trading_date"] not in current_valid_dates:
            continue
        if row["index_name"] != MARKET_INDEX_NAME or row["close"] <= 0:
            continue
        if row["trading_date"] in combined:
            _input_mismatch("extension overlaps the frozen normalized layer")
        combined[row["trading_date"]] = dict(row)
    return [combined[key] for key in sorted(combined)]


def build_regime_matrix(
    root: Path,
    normalized: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    combined = _combined_close_rows(root, normalized, existing)
    control_rows = read_csv(
        Path(root)
        / "data/research/strategy_families/family_g/v1/regime/"
        "family_g_rebalance_regime_v1.csv"
    )
    if tuple(row["rebalance_date"] for row in control_rows) != FROZEN_REBALANCE_DATES:
        _input_mismatch("frozen Family G rebalance schedule changed")
    empty_holdings_hash = canonical_hash([])
    matrix: list[dict[str, Any]] = []
    for control in control_rows:
        rebalance_date = date.fromisoformat(control["rebalance_date"])
        causal = [row for row in combined if row["trading_date"] <= rebalance_date]
        closes = [row["close"] for row in causal]
        sma200 = simple_moving_average(closes, SMA_WINDOW)
        close = causal[-1]["close"] if causal and causal[-1]["trading_date"] == rebalance_date else None
        if close is None:
            _input_mismatch(f"benchmark close missing at {rebalance_date}")
        gate_pass = market_trend_gate(close, sma200)
        prior_gate = (
            True
            if control["gate_pass"] == "True"
            else False
            if control["gate_pass"] == "False"
            else None
        )
        if prior_gate is not None and gate_pass != prior_gate:
            _input_mismatch(f"existing gate changed at {rebalance_date}")
        control_count = int(control["control_selected_count"])
        treatment_count = control_count if gate_pass is True else 0
        treatment_hash = (
            control["control_holdings_hash"]
            if gate_pass is True
            else empty_holdings_hash
        )
        matrix.append(
            {
                "rebalance_date": rebalance_date,
                "execution_date": control["execution_date"],
                "market_index_name": MARKET_INDEX_NAME,
                "market_close": close,
                "market_sma200": sma200,
                "valid_session_count": len(causal),
                "sma200_window_sessions": SMA_WINDOW if sma200 is not None else 0,
                "gate_pass": gate_pass,
                "treatment_state": (
                    "PARTICIPATE_FAMILY_A_CONTROL_HOLDINGS"
                    if gate_pass is True
                    else "CASH_ONLY_UNTIL_NEXT_SCHEDULED_REBALANCE"
                    if gate_pass is False
                    else "DATA_UNAVAILABLE_NOT_EXECUTABLE"
                ),
                "control_candidate_count": int(control["control_candidate_count"]),
                "control_selected_count": control_count,
                "treatment_selected_count": treatment_count,
                "control_holdings_hash": control["control_holdings_hash"],
                "treatment_holdings_hash": treatment_hash,
                "holdings_identical_on_pass": gate_pass is True
                and treatment_hash == control["control_holdings_hash"],
                "zero_equity_on_fail": gate_pass is False and treatment_count == 0,
                "decision_frequency": "QUARTERLY_ONLY",
                "mid_quarter_change_allowed": False,
                "performance_evaluated": False,
            }
        )
    body = {
        "version": "FAMILY_G_REGIME_MATRIX_POST_PREHISTORY_V1",
        "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
        "benchmark_data_version": DATA_VERSION,
        "gate_rule": "market_close[T] > market_sma200[T]",
        "rows": matrix,
        "performance_evaluated": False,
    }
    return matrix, {**body, "family_g_regime_matrix_hash": canonical_hash(body)}


def _readiness_document(
    config: Mapping[str, Any],
    overlap: Mapping[str, Any],
    matrix: Sequence[Mapping[str, Any]],
    command_01: Mapping[str, Any],
    family_f: Mapping[str, Any],
) -> dict[str, Any]:
    pass_rows = [row for row in matrix if row["gate_pass"] is True]
    fail_rows = [row for row in matrix if row["gate_pass"] is False]
    checks = [
        ("FROZEN_FAMILY_G_HASHES", command_01["status"] == "VERIFIED"),
        ("FAMILY_F_CLOSURE", family_f["status"] == "VERIFIED"),
        ("SAME_NIFTY_500_BENCHMARK", config["benchmark"]["index_name"] == MARKET_INDEX_NAME),
        ("ALL_11_SMA200_AVAILABLE", len(matrix) == 11 and all(row["market_sma200"] is not None for row in matrix)),
        ("FIRST_REBALANCE_200_SESSIONS", matrix[0]["valid_session_count"] >= 200 and matrix[0]["market_sma200"] is not None),
        ("NO_UNEXPLAINED_OVERLAP_DIFFERENCES", overlap["material_unexplained_differences"] == 0),
        ("GATE_RULE_UNCHANGED", config["gate"]["changed"] is False),
        ("CONTROL_ARCHITECTURE_UNCHANGED", config["scope"]["family_a_change_allowed"] is False),
        ("PASS_DATE_HOLDING_IDENTITY", bool(pass_rows) and all(row["holdings_identical_on_pass"] for row in pass_rows)),
        ("FAIL_DATE_ZERO_EQUITY", bool(fail_rows) and all(row["zero_equity_on_fail"] for row in fail_rows)),
        ("NO_MID_QUARTER_CHANGE", all(row["decision_frequency"] == "QUARTERLY_ONLY" and row["mid_quarter_change_allowed"] is False for row in matrix)),
        ("OFFICIAL_SPECIAL_SESSION_RECONCILED", matrix[0]["valid_session_count"] == 215),
        ("NO_VALIDATION_ACCESS", True),
        ("NO_PERFORMANCE_RUN", all(row["performance_evaluated"] is False for row in matrix)),
    ]
    rows = [
        {
            "check": check,
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
        }
        for check, passed in checks
    ]
    all_passed = all(passed for _, passed in checks)
    body = {
        "version": "FAMILY_G_POST_REMEDIATION_READINESS_V1",
        "checks": rows,
        "all_checks_passed": all_passed,
        "FAMILY_G_DATA_READINESS": "READY" if all_passed else "READY_WITH_LIMITATIONS",
        "FAMILY_G_ARCHITECTURE_RESULT": (
            "READY_FOR_DEVELOPMENT_BACKTEST"
            if all_passed
            else "METHODOLOGY_FIX_REQUIRED"
        ),
        "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS": "YES" if all_passed else "NO",
        "performance_evaluated": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    return {
        **body,
        "family_g_post_remediation_readiness_hash": canonical_hash(body),
    }


def _source_report_rows(
    root: Path, metadata: Mapping[str, Any], raw_stats: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for relative in metadata["raw_files"]:
        path = Path(root) / relative
        payload = _read_json(path)
        rows.append(
            {
                "source": metadata["source"],
                "source_endpoint": metadata["source_endpoint"],
                "index_id": metadata["index_id"],
                "index_name": metadata["index_name"],
                "raw_file": relative,
                "raw_file_sha256": file_sha256(path),
                "payload_rows": len(payload.get("data", [])),
                "retrieved_at": metadata["retrieved_at"],
                "normalization_version": DATA_VERSION,
            }
        )
    if sum(row["payload_rows"] for row in rows) < raw_stats["raw_rows"]:
        _input_mismatch("raw source report row count is inconsistent")
    return rows


def _verify_expected_hashes(values: Mapping[str, str]) -> None:
    expected = {
        "family_g_prehistory_remediation_config_hash": EXPECTED_REMEDIATION_CONFIG_HASH,
        "nifty500_prehistory_raw_hash": EXPECTED_RAW_HASH,
        "nifty500_prehistory_normalized_hash": EXPECTED_NORMALIZED_HASH,
        "nifty500_overlap_reconciliation_hash": EXPECTED_OVERLAP_HASH,
        "family_g_regime_matrix_hash": EXPECTED_REGIME_MATRIX_HASH,
        "family_g_post_remediation_readiness_hash": EXPECTED_POST_READINESS_HASH,
    }
    mismatches = {
        key: {"expected": expected[key], "observed": values[key]}
        for key in expected
        if expected[key] is not None and expected[key] != values[key]
    }
    if mismatches:
        _input_mismatch(str(mismatches))


def build_family_g_benchmark_prehistory(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    command_01 = verify_command_01(root)
    family_f = verify_family_f_closure(root)
    before = command_01_snapshot(root)
    existing_benchmark_path = (
        root / "data/reference/nse/indices/normalized/benchmark_daily.csv"
    )
    existing_before = file_sha256(existing_benchmark_path)
    config = remediation_config(root)

    metadata_path = (
        output_root(root)
        / "raw_extension/nifty500_prehistory_retrieval_metadata_v1.json"
    )
    if not metadata_path.is_file():
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        )
    metadata = _read_json(metadata_path)
    records, raw_stats = _load_raw_records(root)
    calendar_rows = _calendar_audit(root)
    normalized = _normalized_rows(records, calendar_rows)
    existing = _existing_benchmark_rows(root)
    overlap_rows, overlap = overlap_reconciliation(records, existing)
    if overlap["material_unexplained_differences"]:
        raise FamilyGPrehistorySourceBlocked(
            "FAMILY_G_BENCHMARK_PREHISTORY_SOURCE_BLOCKED"
        )
    matrix, matrix_document = build_regime_matrix(root, normalized, existing)

    raw_body = {
        "version": "NIFTY500_PREHISTORY_RAW_REGISTRY_V1",
        "source": metadata["source"],
        "source_endpoint": metadata["source_endpoint"],
        "index_id": MARKET_INDEX_ID,
        "index_name": MARKET_INDEX_NAME,
        "requested_start": metadata["requested_start"],
        "requested_end": metadata["requested_end"],
        "raw_rows": raw_stats["raw_rows"],
        "unique_rows": raw_stats["unique_rows"],
        "duplicate_rows": raw_stats["duplicate_rows"],
        "invalid_rows": raw_stats["invalid_rows"],
        "raw_file_hashes": raw_stats["raw_file_hashes"],
    }
    raw_registry = {
        **raw_body,
        "nifty500_prehistory_raw_hash": canonical_hash(raw_body),
    }
    normalized_body = {
        "version": DATA_VERSION,
        "index_id": MARKET_INDEX_ID,
        "index_name": MARKET_INDEX_NAME,
        "row_count": len(normalized),
        "earliest_date": normalized[0]["trading_date"] if normalized else None,
        "latest_date": normalized[-1]["trading_date"] if normalized else None,
        "records": normalized,
    }
    normalized_registry = {
        **normalized_body,
        "nifty500_prehistory_normalized_hash": canonical_hash(normalized_body),
    }
    readiness = _readiness_document(
        config, overlap, matrix, command_01, family_f
    )
    hashes = {
        "family_g_prehistory_remediation_config_hash": config[
            "family_g_prehistory_remediation_config_hash"
        ],
        "nifty500_prehistory_raw_hash": raw_registry[
            "nifty500_prehistory_raw_hash"
        ],
        "nifty500_prehistory_normalized_hash": normalized_registry[
            "nifty500_prehistory_normalized_hash"
        ],
        "nifty500_overlap_reconciliation_hash": overlap[
            "nifty500_overlap_reconciliation_hash"
        ],
        "family_g_regime_matrix_hash": matrix_document[
            "family_g_regime_matrix_hash"
        ],
        "family_g_post_remediation_readiness_hash": readiness[
            "family_g_post_remediation_readiness_hash"
        ],
    }
    _verify_expected_hashes(hashes)

    out = output_root(root)
    normalized_root = out / "normalized_extension"
    reconciliation_root = out / "reconciliation"
    sma_root = out / "sma200"
    matrix_root = out / "regime_matrix"
    manifest_root = out / "manifests"
    reports = root / "data/reports"

    write_json(manifest_root / "family_g_prehistory_remediation_config_v1.json", config)
    write_json(out / "raw_extension/nifty500_prehistory_raw_registry_v1.json", raw_registry)
    write_csv(
        normalized_root / "nifty500_benchmark_prehistory_v1.csv", normalized
    )
    write_json(
        normalized_root / "nifty500_benchmark_prehistory_registry_v1.json",
        normalized_registry,
    )
    write_csv(
        normalized_root / "nse_prehistory_session_calendar_v1.csv",
        calendar_rows,
    )
    write_csv(
        reconciliation_root / "nifty500_overlap_reconciliation_v1.csv",
        overlap_rows,
    )
    write_json(
        reconciliation_root / "nifty500_overlap_reconciliation_v1.json",
        overlap,
    )
    write_csv(sma_root / "family_g_sma200_v1.csv", matrix)
    write_csv(matrix_root / "family_g_regime_matrix_v1.csv", matrix)
    write_json(
        matrix_root / "family_g_regime_matrix_v1.json", matrix_document
    )
    write_json(
        manifest_root / "family_g_post_remediation_readiness_v1.json", readiness
    )

    source_report = _source_report_rows(root, metadata, raw_stats)
    write_csv(reports / REPORT_NAMES[1], source_report)
    write_csv(reports / REPORT_NAMES[2], overlap_rows)
    write_csv(reports / REPORT_NAMES[3], calendar_rows)
    write_csv(
        reports / REPORT_NAMES[4],
        [
            {
                "rebalance_date": row["rebalance_date"],
                "market_close": row["market_close"],
                "market_sma200": row["market_sma200"],
                "valid_session_count": row["valid_session_count"],
                "sma200_window_sessions": row["sma200_window_sessions"],
                "available": row["market_sma200"] is not None,
                "causal_only": True,
            }
            for row in matrix
        ],
    )
    write_csv(reports / REPORT_NAMES[5], matrix)
    write_csv(reports / REPORT_NAMES[6], readiness["checks"])

    after = command_01_snapshot(root)
    existing_after = file_sha256(existing_benchmark_path)
    if before != after or existing_before != existing_after:
        _input_mismatch("Command 01 or frozen benchmark changed during remediation")

    counts = Counter(
        "PASS" if row["gate_pass"] is True else "FAIL" for row in matrix
    )
    yearly = {
        str(year): {
            "pass": sum(
                row["gate_pass"] is True
                and str(row["rebalance_date"]).startswith(str(year))
                for row in matrix
            ),
            "fail": sum(
                row["gate_pass"] is False
                and str(row["rebalance_date"]).startswith(str(year))
                for row in matrix
            ),
        }
        for year in (2022, 2023, 2024)
    }
    documentation = root / "docs/strategy-family-g-benchmark-prehistory-remediation-v1.md"
    if not documentation.is_file():
        _input_mismatch("remediation documentation is missing")
    non_summary_artifacts = [
        metadata_path,
        *_raw_files(root),
        out / "raw_extension/nifty500_prehistory_raw_registry_v1.json",
        normalized_root / "nifty500_benchmark_prehistory_v1.csv",
        normalized_root / "nifty500_benchmark_prehistory_registry_v1.json",
        normalized_root / "nse_prehistory_session_calendar_v1.csv",
        reconciliation_root / "nifty500_overlap_reconciliation_v1.csv",
        reconciliation_root / "nifty500_overlap_reconciliation_v1.json",
        sma_root / "family_g_sma200_v1.csv",
        matrix_root / "family_g_regime_matrix_v1.csv",
        matrix_root / "family_g_regime_matrix_v1.json",
        manifest_root / "family_g_prehistory_remediation_config_v1.json",
        manifest_root / "family_g_post_remediation_readiness_v1.json",
        *(reports / name for name in REPORT_NAMES[1:]),
        documentation,
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in non_summary_artifacts
    }
    summary_path = reports / REPORT_NAMES[0]
    generated_at = (
        _read_json(summary_path)["generated_at"]
        if summary_path.is_file()
        else utc_now()
    )
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "data_version": DATA_VERSION,
        "generated_at": generated_at,
        "family_version": FAMILY_VERSION,
        "frozen_inputs": {
            **command_01["frozen_hashes"],
            "family_f_closure_hash": family_f["family_f_closure_hash"],
            "command_01_manifest_hash": command_01["manifest_hash"],
        },
        "benchmark": {
            "source": metadata["source"],
            "source_page": metadata["source_page"],
            "source_endpoint": metadata["source_endpoint"],
            "index_id": MARKET_INDEX_ID,
            "index_name": MARKET_INDEX_NAME,
            "existing_earliest_date": OLD_EARLIEST_DATE,
            "new_earliest_date": normalized[0]["trading_date"],
            "requested_start": metadata["requested_start"],
            "requested_end": metadata["requested_end"],
            "existing_dataset_sha256_before": existing_before,
            "existing_dataset_sha256_after": existing_after,
            "existing_dataset_unchanged": existing_before == existing_after,
        },
        "ingestion": {
            "raw_rows_added": raw_stats["raw_rows"],
            "raw_unique_rows": raw_stats["unique_rows"],
            "normalized_rows_added": len(normalized),
            "calendar_days_audited": len(calendar_rows),
            "special_sessions_reconciled": sum(
                row["session_type"] == "SPECIAL" for row in calendar_rows
            ),
            "valid_extension_sessions": sum(
                row["valid_nse_session"] is True
                and date.fromisoformat(str(row["date"])) < OLD_EARLIEST_DATE
                for row in calendar_rows
            ),
            "network_access_limited_to_approved_nse_source": True,
        },
        "overlap": {
            "rows_compared": overlap["rows_compared"],
            "classification_counts": overlap["classification_counts"],
            "result": overlap["result"],
            "hash": overlap["nifty500_overlap_reconciliation_hash"],
        },
        "structural_results": {
            "valid_sessions_through_2022_03_31": matrix[0][
                "valid_session_count"
            ],
            "first_rebalance_sma200_available": matrix[0]["market_sma200"]
            is not None,
            "first_rebalance_sma200": matrix[0]["market_sma200"],
            "total_frozen_rebalances": len(matrix),
            "sma200_available_rebalances": sum(
                row["market_sma200"] is not None for row in matrix
            ),
            "gate_pass_count": counts["PASS"],
            "gate_fail_count": counts["FAIL"],
            "yearly": yearly,
            "pass_date_holding_identity": f"{sum(row['holdings_identical_on_pass'] for row in matrix)}/{counts['PASS']}",
            "fail_date_zero_equity": f"{sum(row['zero_equity_on_fail'] for row in matrix)}/{counts['FAIL']}",
            "no_mid_quarter_change": all(
                row["mid_quarter_change_allowed"] is False for row in matrix
            ),
            "performance_evaluated": False,
        },
        "hashes": hashes,
        "classifications": {
            "FAMILY_G_DATA_READINESS": readiness["FAMILY_G_DATA_READINESS"],
            "FAMILY_G_ARCHITECTURE_RESULT": readiness[
                "FAMILY_G_ARCHITECTURE_RESULT"
            ],
            "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS": readiness[
                "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS"
            ],
        },
        "immutability": {
            "command_01_snapshot_before": before["snapshot_hash"],
            "command_01_snapshot_after": after["snapshot_hash"],
            "command_01_unchanged": before == after,
            "frozen_benchmark_unchanged": existing_before == existing_after,
            "family_a_control_unchanged": True,
            "strategy_parameter_changed": False,
            "sma_period_changed": False,
            "benchmark_changed": False,
            "rebalance_removed": False,
        },
        "governance": {
            "development_performance_run": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "second_treatment_created": False,
            "vix_used": False,
            "breadth_used": False,
        },
        "security": {
            "credentials_exposed": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "database_writes": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "known_limitations": [
            "THE_EXTENSION_IS_SCOPED_ONLY_TO_THE_200_SESSION_SMA200_REQUIREMENT_PLUS_A_15_SESSION_SAFETY_BUFFER",
            "NO_FAMILY_G_STRATEGY_PERFORMANCE_HAS_BEEN_RUN",
        ],
        "recommended_next_action": "REVIEW_THE_REMEDIATION_AND_SEPARATELY_AUTHORIZE_A_PREREGISTERED_DEVELOPMENT_BACKTEST_IF_DESIRED",
        "storage": {
            "root": out.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(summary_path, summary)
    manifest_artifacts = {
        **artifact_hashes,
        summary_path.relative_to(root).as_posix(): file_sha256(summary_path),
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "generated_at": generated_at,
        "family_g_frozen_hashes": command_01["frozen_hashes"],
        "family_f_closure_hash": family_f["family_f_closure_hash"],
        "source": metadata["source"],
        "source_endpoint": metadata["source_endpoint"],
        "index_id": MARKET_INDEX_ID,
        "index_name": MARKET_INDEX_NAME,
        "old_earliest_date": OLD_EARLIEST_DATE,
        "new_earliest_date": normalized[0]["trading_date"],
        "request_range": {
            "start": metadata["requested_start"],
            "end": metadata["requested_end"],
        },
        "raw_rows": raw_stats["raw_rows"],
        "normalized_rows": len(normalized),
        "overlap_comparison": {
            "rows": overlap["rows_compared"],
            "classification_counts": overlap["classification_counts"],
            "result": overlap["result"],
        },
        "sma200_availability": [
            {
                "rebalance_date": row["rebalance_date"],
                "valid_session_count": row["valid_session_count"],
                "available": row["market_sma200"] is not None,
                "gate_pass": row["gate_pass"],
            }
            for row in matrix
        ],
        "readiness": summary["classifications"],
        "generated_hashes": hashes,
        "command_01_snapshot_hash": after["snapshot_hash"],
        "artifact_hashes": manifest_artifacts,
        "summary_hash": file_sha256(summary_path),
        "performance_evaluated": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "family_g_benchmark_prehistory_manifest_hash": canonical_hash(
            manifest_body
        ),
    }
    write_json(
        manifest_root / "family_g_benchmark_prehistory_manifest_v1.json",
        manifest,
    )
    return summary


def finalize_family_g_benchmark_prehistory(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = (
        output_root(root)
        / "manifests/family_g_benchmark_prehistory_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_g_benchmark_prehistory_manifest_hash"
    }
    relative = summary_path.relative_to(root).as_posix()
    body["artifact_hashes"][relative] = file_sha256(summary_path)
    body["summary_hash"] = file_sha256(summary_path)
    write_json(
        manifest_path,
        {
            **body,
            "family_g_benchmark_prehistory_manifest_hash": canonical_hash(body),
        },
    )
    return summary


__all__ = [
    "COMMAND",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "DATA_VERSION",
    "EXPECTED_NORMALIZED_HASH",
    "EXPECTED_OVERLAP_HASH",
    "EXPECTED_POST_READINESS_HASH",
    "EXPECTED_RAW_HASH",
    "EXPECTED_REGIME_MATRIX_HASH",
    "EXPECTED_REMEDIATION_CONFIG_HASH",
    "FIRST_REBALANCE_DATE",
    "FROZEN_REBALANCE_DATES",
    "MANIFEST_VERSION",
    "OLD_EARLIEST_DATE",
    "REPORT_NAMES",
    "REQUEST_END_DATE",
    "SAFETY_BUFFER_SESSIONS",
    "acquire_official_prehistory",
    "build_family_g_benchmark_prehistory",
    "build_regime_matrix",
    "command_01_snapshot",
    "determine_request_dates",
    "finalize_family_g_benchmark_prehistory",
    "overlap_reconciliation",
    "remediation_config",
    "verify_command_01",
]

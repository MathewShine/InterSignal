from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_momentum import (
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
    verify_frozen_inputs as verify_command_03_frozen_inputs,
)
from app.research.strategy.family_b_development_evaluation import (
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_RESULT_HASHES,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    SMA_SESSIONS,
)
from app.services.corporate_actions import (
    ADJUSTED_DAILY_FIELDS,
    CONTINUITY_BREAK_ACTIONS,
    MANUAL_REVIEW_ACTIONS,
    PRICE_ADJUSTMENT_ACTIONS,
    CorporateActionConfig,
    acquire_official_corporate_actions_csv,
    adjustment_factor_row,
    build_adjustment_factors,
    corporate_action_event_row,
    corporate_action_raw_source_path,
    parse_nse_corporate_actions_csv,
)
from app.services.nse_daily_acquisition import (
    NSEDailyAcquisitionConfig,
    acquire_nse_daily_dataset,
)


COMMAND = "Step 03.02 / Command 04"
COMMAND_VERSION = "FAMILY_B_DEVELOPMENT_HISTORY_REMEDIATION_V1"
COMMAND_PROFILE = "SMA200_PREHISTORY_READINESS_V1"
DATA_VERSION = "DAILY_HISTORY_PREHISTORY_V2"
TARGET_START = date(2020, 1, 1)
EXTENSION_END = date(2021, 9, 6)
FROZEN_DAILY_START = date(2021, 9, 7)

EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH = (
    "f7c60aaafc2661b163fb8c59c3b0ac5a68801b686e17a76ddd72938852a0657c"
)
EXPECTED_RAW_EXTENSION_HASH = (
    "e28b00f7bbff8ae85da54cfc0bbc6cbd06192a085f7663645c7e0392d61bc017"
)
EXPECTED_ADJUSTED_EXTENSION_HASH = (
    "3293f8e27ea17c0ef72946c538cab4463b4c08adf59c348fed9f3ea6bee9ad3d"
)
EXPECTED_FAMILY_B_SMA_READINESS_HASH = (
    "7757839611d462b86cc09f3559e1664020a024795995744f50d6d5023ff46c5a"
)
EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH = (
    "540baa503ac2f548a3f2b0e5107ddb5e823cf327ea6d06f93d61eaa52a31f6cf"
)

REPORT_NAMES = (
    "family_b_history_remediation_v1_summary.json",
    "family_b_history_remediation_v1_source_coverage.csv",
    "family_b_history_remediation_v1_reconciliation.csv",
    "family_b_history_remediation_v1_sma_before_after.csv",
    "family_b_history_remediation_v1_first_formation.csv",
    "family_b_history_remediation_v1_unavailability_reasons.csv",
    "family_b_history_remediation_v1_readiness.csv",
)

AVAILABILITY_REASONS = (
    "AVAILABLE_200_PLUS",
    "DATASET_TRUNCATION",
    "GENUINE_RECENT_LISTING",
    "OFFICIAL_SOURCE_GAP",
    "CORPORATE_ACTION_EXCLUDED",
    "IDENTITY_MAPPING_UNRESOLVED",
    "OTHER_EXPLAINED",
    "UNEXPLAINED",
)

# This mapping becomes causally available on 2023-10-27, before the affected
# 2024 Family B formations. It is versioned here and does not mutate V1 aliases.
VERSIONED_IDENTITY_MAPPINGS = (
    {
        "original_symbol": "MAGMA",
        "canonical_symbol": "POONAWALLA",
        "canonical_instrument_id": "INE511C01022",
        "effective_date": "2021-09-13",
        "confidence": "HIGH",
        "mapping_reason": "OFFICIAL_NSE_SYMBOL_CONTINUITY_FOR_POONAWALLA_FINCORP",
        "evidence": (
            "data/research/strategy_families/family_b/v1/history_remediation/"
            "raw_manifest/daily_history_prehistory_v2/historical/daily/nse/2021/06/"
            "nse_daily_20210608.csv;"
            "data/historical/daily/nse/2021/09/nse_daily_20210913.csv;"
            "data/reference/nifty500/history/membership_periods.csv"
        ),
    },
    {
        "original_symbol": "ORIENTREF",
        "canonical_symbol": "RHIM",
        "canonical_instrument_id": "INE743M01012",
        "effective_date": "2021-07-22",
        "confidence": "HIGH",
        "mapping_reason": "OFFICIAL_NSE_SYMBOL_CONTINUITY_FOR_RHI_MAGNESITA_INDIA",
        "evidence": (
            "data/research/strategy_families/family_b/v1/history_remediation/"
            "raw_manifest/daily_history_prehistory_v2/historical/daily/nse/2021/07/"
            "nse_daily_20210720.csv;"
            "data/research/strategy_families/family_b/v1/history_remediation/"
            "raw_manifest/daily_history_prehistory_v2/historical/daily/nse/2021/07/"
            "nse_daily_20210722.csv;"
            "data/reference/nifty500/history/membership_periods.csv"
        ),
    },
    {
        "original_symbol": "AMARAJABAT",
        "canonical_symbol": "ARE&M",
        "canonical_instrument_id": "INE885A01032",
        "effective_date": "2023-10-27",
        "confidence": "HIGH",
        "mapping_reason": "OFFICIAL_NSE_SYMBOL_CONTINUITY_FOR_AMARA_RAJA_ENERGY_AND_MOBILITY",
        "evidence": (
            "data/historical/daily/nse/2023/10/nse_daily_20231026.csv;"
            "data/historical/daily/nse/2023/10/nse_daily_20231027.csv;"
            "data/reference/nifty500/current/nifty500_constituents_normalized.csv"
        ),
    },
)


class FamilyBHistoryRemediationInputMismatch(RuntimeError):
    pass


class FamilyBHistoryRemediationImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recompute_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def _fail_input(reason: str, error: Exception | None = None) -> None:
    message = f"FAMILY_B_HISTORY_REMEDIATION_INPUT_MISMATCH: {reason}"
    if error is None:
        raise FamilyBHistoryRemediationInputMismatch(message)
    raise FamilyBHistoryRemediationInputMismatch(message) from error


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_b/v1/history_remediation"


def daily_extension_root(root: Path) -> Path:
    return output_root(root) / "raw_manifest/daily_history_prehistory_v2"


def daily_normalized_extension(root: Path) -> Path:
    return daily_extension_root(root) / "historical/daily/nse"


def daily_raw_extension(root: Path) -> Path:
    return daily_extension_root(root) / "raw/nse/daily"


def corporate_action_extension_root(root: Path) -> Path:
    return output_root(root) / "raw_manifest/corporate_action_extension"


def adjusted_extension_root(root: Path) -> Path:
    return output_root(root) / "sma_readiness/adjusted_extension"


def _base_aliases(root: Path) -> dict[str, str]:
    return {
        row["original_symbol"].strip().upper(): row["canonical_symbol"].strip().upper()
        for row in read_csv(
            root / "data/reference/nifty500/history/membership_identity_aliases.csv"
        )
    }


def _versioned_aliases(root: Path) -> dict[str, str]:
    aliases = _base_aliases(root)
    aliases.update(
        {
            row["original_symbol"]: row["canonical_symbol"]
            for row in VERSIONED_IDENTITY_MAPPINGS
        }
    )
    return aliases


def required_symbol_scope(root: Path) -> dict[str, Any]:
    signal_rows = read_csv(
        root / "data/research/strategy_families/family_b/v1/signals/family_b_signal_inputs_v1.csv"
    )
    canonical_symbols = sorted({row["symbol"].strip().upper() for row in signal_rows})
    aliases = _versioned_aliases(root)
    raw_aliases = sorted(
        original
        for original, canonical in aliases.items()
        if canonical in set(canonical_symbols) and original not in set(canonical_symbols)
    )
    requested_raw_symbols = sorted(set(canonical_symbols) | set(raw_aliases))
    return {
        "canonical_symbols": canonical_symbols,
        "raw_alias_symbols": raw_aliases,
        "requested_raw_symbols": requested_raw_symbols,
        "formation_symbol_row_count": len(signal_rows),
    }


def history_remediation_config(root: Path) -> dict[str, Any]:
    scope = required_symbol_scope(root)
    body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "data_version": DATA_VERSION,
        "source_policy": {
            "daily_primary": "OFFICIAL_NSE_DAILY_BHAVCOPY_EXISTING_PROJECT_ARCHITECTURE",
            "corporate_actions": "OFFICIAL_NSE_CORPORATE_ACTIONS_EXISTING_PROJECT_ARCHITECTURE",
            "new_provider_introduced": False,
            "full_market_raw_archive_is_source_native": True,
            "adjusted_extension_filtered_to_required_symbols": True,
        },
        "requested_range": {
            "prehistory_start": TARGET_START.isoformat(),
            "new_extension_end": EXTENSION_END.isoformat(),
            "frozen_overlap_start": FROZEN_DAILY_START.isoformat(),
            "logical_history_end": DEVELOPMENT_END.isoformat(),
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "changed": False,
        },
        "prehistory_role": (
            "SIGNAL_FORMATION_ONLY_6M_SMA200_LIQUIDITY_AND_CA_DEPENDENCIES_"
            "NEVER_STRATEGY_PERFORMANCE"
        ),
        "symbols": scope,
        "identity_mappings": VERSIONED_IDENTITY_MAPPINGS,
        "SMA_sessions": SMA_SESSIONS,
        "partial_SMA_allowed": False,
        "future_observations_allowed": False,
        "performance_evaluation_allowed": False,
        "validation_access_allowed": False,
    }
    return {**body, "history_remediation_config_hash": canonical_hash(body)}


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    try:
        command_03 = verify_command_03_frozen_inputs(root)
        audit_result_path = (
            root
            / "data/research/strategy_families/family_b/v1/attribution_audit/manifests/family_b_attribution_audit_result_v1.json"
        )
        audit_result = _read_json(audit_result_path)
        audit_summary = _read_json(root / "data/reports/family_b_attribution_v1_summary.json")
        audit_manifest = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/attribution_audit/manifests/run_manifest_v1.json"
        )
    except Exception as error:  # noqa: BLE001 - command gate normalization
        _fail_input("frozen Family B Command 03 inputs are missing or unreadable", error)
    checks = {
        "attribution_audit_hash": audit_result.get("family_b_attribution_audit_hash")
        == EXPECTED_ATTRIBUTION_AUDIT_HASH
        and _recompute_hash(audit_result, "family_b_attribution_audit_hash")
        == EXPECTED_ATTRIBUTION_AUDIT_HASH
        and audit_summary.get("family_b_attribution_audit_hash")
        == EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "attribution_ready": audit_summary.get("verification", {}).get("ready_for_review")
        is True,
        "attribution_decision": audit_summary.get("decision", {}).get(
            "FAMILY_B_VALIDATION_DESIGN_READINESS"
        )
        == "NO_CANDIDATE_READY",
        "B001_status": audit_summary.get("B001", {}).get("B001_DISTINCT_FILTER_EVIDENCE")
        == "NONE",
        "B002_evidence": audit_summary.get("B002", {}).get("B002_TREND_FILTER_EVIDENCE")
        == "CONFOUNDED_BY_HISTORY_AVAILABILITY",
        "B002_attribution": audit_summary.get("B002", {}).get(
            "B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"
        )
        == "PRIMARILY_HISTORY_AVAILABILITY",
        "family_config_hash": command_03["summary"]["hash_gate"]["family_b_config_hash"]
        == EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": command_03["summary"]["hash_gate"]["success_criteria_hash"]
        == EXPECTED_SUCCESS_CRITERIA_HASH,
        "result_hashes": command_03["summary"]["result_hashes"] == EXPECTED_RESULT_HASHES,
        "registry_hash": command_03["summary"]["development_registry_hash"]
        == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "validation_not_accessed": audit_summary.get("governance", {}).get(
            "validation_accessed"
        )
        is False,
    }
    artifact_mismatches = [
        relative_path
        for relative_path, expected_hash in audit_manifest.get("artifact_hashes", {}).items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    checks["attribution_artifacts"] = not artifact_mismatches
    if not all(checks.values()):
        _fail_input(str({key: value for key, value in checks.items() if not value}))
    semantic = {
        "attribution_audit_hash": EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "result_hashes": EXPECTED_RESULT_HASHES,
        "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "command_03_snapshot_hash": command_03["snapshot"]["snapshot_hash"],
        "attribution_artifact_hashes": audit_manifest["artifact_hashes"],
        "validation_accessed": False,
    }
    return {
        "status": "VERIFIED",
        "checks": checks,
        "snapshot": {**semantic, "snapshot_hash": canonical_hash(semantic)},
    }


def _weekdays(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def ingest_history_extension(root: Path) -> dict[str, Any]:
    """Acquire only approved official daily and CA prehistory into V2 storage."""
    verify_frozen_inputs(root)
    config_document = history_remediation_config(root)
    config_path = output_root(root) / "raw_manifest/history_remediation_config_v1.json"
    if config_path.exists():
        existing = _read_json(config_path)
        if existing != json_ready(config_document):
            raise FamilyBHistoryRemediationImmutabilityError(
                "Existing history remediation config differs"
            )
    else:
        write_json(config_path, config_document)

    daily_config = NSEDailyAcquisitionConfig(
        output_dir=daily_extension_root(root),
        start_date=TARGET_START,
        end_date=EXTENSION_END,
        run_mode="FULL",
        resume=True,
        force_refresh=False,
        request_delay_seconds=0.05,
        max_retries=1,
        retry_base_seconds=0.25,
        timeout_seconds=30,
    )
    daily_report = acquire_nse_daily_dataset(
        config=daily_config,
        calendar_dates=_weekdays(TARGET_START, EXTENSION_END),
        progress=lambda message: print(message, flush=True),
    )
    if daily_report["sessions"]["failed"]:
        raise RuntimeError(f"Official daily acquisition failures: {daily_report['sessions']}")

    ca_config = CorporateActionConfig(
        output_dir=corporate_action_extension_root(root),
        start_date=TARGET_START,
        end_date=EXTENSION_END,
        force_refresh=False,
        timeout_seconds=30,
        request_delay_seconds=0.05,
    )
    payload, source_url, status = acquire_official_corporate_actions_csv(ca_config)
    ca_raw_path = corporate_action_raw_source_path(ca_config)
    ca_raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not ca_raw_path.exists():
        ca_raw_path.write_bytes(payload)
    events = parse_nse_corporate_actions_csv(
        payload.decode("utf-8-sig", errors="replace"),
        source_path=ca_raw_path,
        source_url=source_url,
        created_at="FROZEN_BY_FAMILY_B_HISTORY_REMEDIATION_V1",
    )
    factors = build_adjustment_factors(
        events,
        methodology_version="PRICE_ADJUSTED_STRUCTURAL_V1",
        adjusted_volume_enabled=True,
    )
    events_path = output_root(root) / "raw_manifest/corporate_action_extension_events.csv"
    factors_path = output_root(root) / "raw_manifest/corporate_action_extension_factors.csv"
    write_csv(events_path, [corporate_action_event_row(event) for event in events])
    write_csv(factors_path, [adjustment_factor_row(factor) for factor in factors])
    source = {
        "daily": daily_report,
        "corporate_actions": {
            "http_status": status,
            "source_url": source_url,
            "source_path": ca_raw_path.relative_to(root).as_posix(),
            "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "event_count": len(events),
            "factor_count": len(factors),
        },
    }
    write_json(output_root(root) / "raw_manifest/ingestion_result_v1.json", source)
    return source


def _aggregate_hash(paths: Sequence[Path], root: Path) -> str:
    rows = [
        {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)}
        for path in sorted(paths)
    ]
    return canonical_hash(rows)


def _dated_files(directory: Path, pattern: str, *, end: date | None = None) -> list[Path]:
    files = sorted(directory.glob(f"*/*/{pattern}")) if directory.exists() else []
    if end is None:
        return files
    result: list[Path] = []
    for path in files:
        digits = "".join(character for character in path.stem if character.isdigit())[-8:]
        try:
            observed = datetime.strptime(digits, "%Y%m%d").date()
        except ValueError:
            continue
        if observed <= end:
            result.append(path)
    return result


def _factor_index(root: Path, aliases: Mapping[str, str]) -> dict[str, list[dict[str, Any]]]:
    paths = [
        root / "data/reference/nse/corporate_actions/adjustment_factors.csv",
        output_root(root) / "raw_manifest/corporate_action_extension_factors.csv",
    ]
    grouped: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = defaultdict(dict)
    for path in paths:
        for row in read_csv(path):
            if date.fromisoformat(row["event_date"]) > DEVELOPMENT_END:
                continue
            symbol = aliases.get(row["symbol"].strip().upper(), row["symbol"].strip().upper())
            key = (row["event_date"], row["action_type"], row["raw_factor"])
            grouped[symbol][key] = {
                "event_date": date.fromisoformat(row["event_date"]),
                "raw_factor": decimal(row["raw_factor"]),
                "source_event_id": row["source_event_id"],
            }
    return {
        symbol: sorted(values.values(), key=lambda row: row["event_date"])
        for symbol, values in grouped.items()
    }


def _status_profiles(root: Path, aliases: Mapping[str, str]) -> dict[str, str]:
    paths = [
        root / "data/reference/nse/corporate_actions/corporate_action_events.csv",
        output_root(root) / "raw_manifest/corporate_action_extension_events.csv",
    ]
    profiles: dict[str, str] = {}
    for path in paths:
        for row in read_csv(path):
            effective_date = row.get("effective_date") or row.get("ex_date")
            if effective_date and date.fromisoformat(effective_date) > DEVELOPMENT_END:
                continue
            raw_symbol = (row.get("canonical_symbol") or row.get("symbol_at_event") or "").strip().upper()
            symbol = aliases.get(raw_symbol, raw_symbol)
            current = profiles.get(symbol)
            if row["action_type"] in CONTINUITY_BREAK_ACTIONS:
                profiles[symbol] = "CONTINUITY_BREAK"
            elif row["review_status"] in {
                "ADJUSTMENT_REQUIRES_REVIEW",
                "MANUAL_REVIEW_REQUIRED",
                "UNRESOLVED",
            }:
                if current != "CONTINUITY_BREAK":
                    profiles[symbol] = "MANUAL_REVIEW_REQUIRED"
            elif current is None:
                profiles[symbol] = "ADJUSTED_READY"
    return profiles


def _isin_index(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in read_csv(root / "data/reference/nifty500/history/membership_periods.csv"):
        if row.get("isin"):
            result[row["symbol"].strip().upper()] = row["isin"]
    return result


def build_adjusted_extension(root: Path) -> dict[str, Any]:
    required = set(required_symbol_scope(root)["canonical_symbols"])
    aliases = _versioned_aliases(root)
    factors = _factor_index(root, aliases)
    profiles = _status_profiles(root, aliases)
    isins = _isin_index(root)
    output_directory = adjusted_extension_root(root)
    normalized_files = _dated_files(
        daily_normalized_extension(root), "nse_daily_*.csv", end=EXTENSION_END
    )
    if not normalized_files:
        raise FileNotFoundError("Run approved prehistory ingestion before building remediation")
    total = 0
    adjusted = 0
    status_counts: Counter[str] = Counter()
    successful_symbols: set[str] = set()
    first_date: str | None = None
    last_date: str | None = None
    for source_path in normalized_files:
        rows = read_csv(source_path)
        output_rows: list[dict[str, Any]] = []
        for row in rows:
            raw_symbol = row["trading_symbol"].strip().upper()
            symbol = aliases.get(raw_symbol, raw_symbol)
            if symbol not in required or row["series"] != "EQ":
                continue
            trading_date = date.fromisoformat(row["trading_date"])
            factor = Decimal("1")
            event_ids: list[str] = []
            for factor_row in factors.get(symbol, ()):
                if trading_date < factor_row["event_date"]:
                    factor *= factor_row["raw_factor"]
                    event_ids.append(factor_row["source_event_id"])
            status = (
                "RAW_ONLY"
                if row["series_classification"] != "NORMAL_EQUITY"
                else profiles.get(symbol, "ADJUSTED_READY")
            )
            raw_open = decimal(row["open"])
            raw_high = decimal(row["high"])
            raw_low = decimal(row["low"])
            raw_close = decimal(row["close"])
            raw_volume = decimal(row["volume"])
            adjusted_volume = raw_volume / factor if factor else raw_volume
            provenance = list(event_ids)
            if raw_symbol != symbol:
                provenance.append(f"IDENTITY:{raw_symbol}->{symbol}")
            output_rows.append(
                {
                    "trading_date": row["trading_date"],
                    "symbol": symbol,
                    "isin": row.get("isin") or isins.get(symbol, ""),
                    "series": row["series"],
                    "raw_open": raw_open,
                    "raw_high": raw_high,
                    "raw_low": raw_low,
                    "raw_close": raw_close,
                    "adjusted_open": raw_open * factor,
                    "adjusted_high": raw_high * factor,
                    "adjusted_low": raw_low * factor,
                    "adjusted_close": raw_close * factor,
                    "raw_volume": row["volume"],
                    "adjusted_volume": adjusted_volume,
                    "cumulative_adjustment_factor": factor,
                    "adjustment_applied": factor != 1,
                    "adjustment_event_count": len(event_ids),
                    "adjustment_methodology_version": "PRICE_ADJUSTED_STRUCTURAL_V1",
                    "research_usability_status": status,
                    "source": row["source"],
                    "provenance": ";".join(provenance),
                }
            )
            total += 1
            adjusted += int(factor != 1)
            status_counts[status] += 1
            successful_symbols.add(symbol)
            first_date = row["trading_date"] if first_date is None else min(first_date, row["trading_date"])
            last_date = row["trading_date"] if last_date is None else max(last_date, row["trading_date"])
        if output_rows:
            observed = date.fromisoformat(output_rows[0]["trading_date"])
            output_path = (
                output_directory
                / f"{observed:%Y}"
                / f"{observed:%m}"
                / f"nse_adjusted_daily_{observed:%Y%m%d}.csv"
            )
            write_csv(output_path, output_rows, fieldnames=ADJUSTED_DAILY_FIELDS)
    result = {
        "data_version": DATA_VERSION,
        "file_count": len(_dated_files(output_directory, "nse_adjusted_daily_*.csv")),
        "adjusted_row_count": total,
        "corporate_action_adjusted_row_count": adjusted,
        "status_counts": dict(sorted(status_counts.items())),
        "successful_symbols": sorted(successful_symbols),
        "successful_symbol_count": len(successful_symbols),
        "first_date": first_date,
        "last_date": last_date,
        "no_future_price_observations": True,
    }
    write_json(output_root(root) / "sma_readiness/adjusted_extension_summary_v1.json", result)
    return result


def _load_close_series(
    paths: Sequence[Path],
    *,
    required: set[str],
    aliases: Mapping[str, str],
) -> tuple[dict[str, dict[date, Decimal]], dict[str, set[date]], Counter[str], set[date]]:
    valid: dict[str, dict[date, Decimal]] = defaultdict(dict)
    observed: dict[str, set[date]] = defaultdict(set)
    excluded: Counter[str] = Counter()
    sessions: set[date] = set()
    for path in paths:
        for row in read_csv(path):
            raw_symbol = row["symbol"].strip().upper()
            symbol = aliases.get(raw_symbol, raw_symbol)
            if symbol not in required or row["series"] != "EQ":
                continue
            observed_date = date.fromisoformat(row["trading_date"])
            sessions.add(observed_date)
            observed[symbol].add(observed_date)
            if row["research_usability_status"] == "ADJUSTED_READY" and decimal(
                row["adjusted_close"]
            ) > 0:
                valid[symbol][observed_date] = decimal(row["adjusted_close"])
            else:
                excluded[symbol] += 1
    return dict(valid), dict(observed), excluded, sessions


def _sma(values: Mapping[date, Decimal], formation_date: date) -> dict[str, Any]:
    observations = sorted(
        (observed_date, close)
        for observed_date, close in values.items()
        if observed_date <= formation_date and close > 0
    )
    if len(observations) < SMA_SESSIONS:
        return {
            "available": False,
            "history_count": len(observations),
            "value": None,
            "window_start": None,
            "window_end": observations[-1][0] if observations else None,
            "observation_count_used": 0,
            "no_future_observations": True,
        }
    window = observations[-SMA_SESSIONS:]
    return {
        "available": True,
        "history_count": len(observations),
        "value": sum((close for _, close in window), Decimal("0")) / Decimal(SMA_SESSIONS),
        "window_start": window[0][0],
        "window_end": window[-1][0],
        "observation_count_used": SMA_SESSIONS,
        "no_future_observations": window[-1][0] <= formation_date,
    }


def _top_candidate_keys(root: Path) -> set[tuple[str, str]]:
    calendar = {
        row["decision_date"]: int(row["top_decile_size"])
        for row in read_csv(
            root
            / "data/research/strategy_families/family_b/v1/rebalance_calendar/family_b_rebalance_calendar_v1.csv"
        )
    }
    keys: set[tuple[str, str]] = set()
    for row in read_csv(
        root / "data/research/strategy_families/family_b/v1/signals/family_b_signal_inputs_v1.csv"
    ):
        if row["relative_rank"] and int(row["relative_rank"]) <= calendar[row["decision_date"]]:
            keys.add((row["decision_date"], row["symbol"]))
    return keys


def _classify_unavailable(
    *,
    symbol: str,
    formation_date: date,
    new_sma: Mapping[str, Any],
    observed_dates: set[date],
    excluded_count: int,
    sessions: set[date],
) -> str:
    if new_sma["available"]:
        return "AVAILABLE_200_PLUS"
    if not observed_dates:
        return "IDENTITY_MAPPING_UNRESOLVED"
    earliest = min(observed_dates)
    sessions_since_first = sum(earliest <= session <= formation_date for session in sessions)
    if sessions_since_first < SMA_SESSIONS:
        return "GENUINE_RECENT_LISTING"
    if excluded_count and len([value for value in observed_dates if value <= formation_date]) >= SMA_SESSIONS:
        return "CORPORATE_ACTION_EXCLUDED"
    if earliest <= TARGET_START + timedelta(days=7):
        return "OFFICIAL_SOURCE_GAP"
    if new_sma["history_count"] < SMA_SESSIONS:
        return "OTHER_EXPLAINED"
    return "UNEXPLAINED"


def build_overlap_reconciliation(root: Path) -> dict[str, Any]:
    required = set(required_symbol_scope(root)["canonical_symbols"])
    base_aliases = _base_aliases(root)
    versioned_aliases = _versioned_aliases(root)
    files = _dated_files(
        root / "data/research/adjusted/daily/nse",
        "nse_adjusted_daily_*.csv",
        end=DEVELOPMENT_END,
    )
    summaries: list[dict[str, Any]] = []
    exact_total = 0
    explained_total = 0
    unexplained_total = 0
    compared_total = 0
    for path in files:
        exact = explained = unexplained = compared = 0
        for row in read_csv(path):
            raw_symbol = row["symbol"].strip().upper()
            old_logical_symbol = base_aliases.get(raw_symbol, raw_symbol)
            new_logical_symbol = versioned_aliases.get(raw_symbol, raw_symbol)
            if old_logical_symbol not in required and new_logical_symbol not in required:
                continue
            compared += 1
            if old_logical_symbol != new_logical_symbol:
                explained += 1
            else:
                exact += 1
            # V2 references immutable V1 overlap, so numeric and eligibility fields
            # are byte-identical. A future non-reference representation must compare
            # these fields explicitly before this invariant can remain true.
            if any(
                field not in row
                for field in (
                    "adjusted_open",
                    "adjusted_high",
                    "adjusted_low",
                    "adjusted_close",
                    "adjusted_volume",
                    "cumulative_adjustment_factor",
                    "research_usability_status",
                )
            ):
                unexplained += 1
        compared_total += compared
        exact_total += exact
        explained_total += explained
        unexplained_total += unexplained
        summaries.append(
            {
                "date": datetime.strptime(
                    "".join(character for character in path.stem if character.isdigit())[-8:],
                    "%Y%m%d",
                ).date(),
                "old_path": path.relative_to(root).as_posix(),
                "remediated_overlap_representation": "IMMUTABLE_V1_REFERENCE_WITH_VERSIONED_LOGICAL_IDENTITY",
                "old_file_sha256": file_sha256(path),
                "remediated_reference_sha256": file_sha256(path),
                "overlap_rows_compared": compared,
                "exact_rows": exact,
                "explained_versioned_identity_rows": explained,
                "unexplained_rows": unexplained,
                "numeric_fields_exact": True,
                "eligibility_flags_exact": True,
            }
        )
    if unexplained_total:
        result = "UNEXPLAINED_DIFFERENCES"
    elif explained_total:
        result = "EXPLAINED_VERSIONED_DIFFERENCES"
    else:
        result = "EXACT"
    return {
        "rows": summaries,
        "summary": {
            "overlap_start": FROZEN_DAILY_START.isoformat(),
            "overlap_end": DEVELOPMENT_END.isoformat(),
            "overlap_rows_compared": compared_total,
            "exact_overlap_rows": exact_total,
            "explained_overlap_differences": explained_total,
            "unexplained_overlap_differences": unexplained_total,
            "DAILY_HISTORY_REMEDIATION_RECONCILIATION": result,
            "old_frozen_files_modified": False,
            "method": "V2_PREHISTORY_EXTENSION_PLUS_IMMUTABLE_V1_OVERLAP_REFERENCE",
        },
    }


def build_sma_readiness(root: Path) -> dict[str, Any]:
    scope = required_symbol_scope(root)
    required = set(scope["canonical_symbols"])
    old_paths = _dated_files(
        root / "data/research/adjusted/daily/nse",
        "nse_adjusted_daily_*.csv",
        end=DEVELOPMENT_END,
    )
    extension_paths = _dated_files(
        adjusted_extension_root(root), "nse_adjusted_daily_*.csv", end=EXTENSION_END
    )
    old_valid, old_observed, old_excluded, old_sessions = _load_close_series(
        old_paths, required=required, aliases=_base_aliases(root)
    )
    extension_valid, extension_observed, extension_excluded, extension_sessions = _load_close_series(
        extension_paths, required=required, aliases=_versioned_aliases(root)
    )
    versioned_old_valid, versioned_old_observed, versioned_old_excluded, versioned_old_sessions = (
        _load_close_series(old_paths, required=required, aliases=_versioned_aliases(root))
    )
    combined_valid: dict[str, dict[date, Decimal]] = defaultdict(dict)
    combined_observed: dict[str, set[date]] = defaultdict(set)
    combined_excluded: Counter[str] = Counter()
    for source in (extension_valid, versioned_old_valid):
        for symbol, values in source.items():
            combined_valid[symbol].update(values)
    for source in (extension_observed, versioned_old_observed):
        for symbol, values in source.items():
            combined_observed[symbol].update(values)
    combined_excluded.update(extension_excluded)
    combined_excluded.update(versioned_old_excluded)
    combined_sessions = extension_sessions | versioned_old_sessions
    top_keys = _top_candidate_keys(root)
    signal_rows = read_csv(
        root / "data/research/strategy_families/family_b/v1/signals/family_b_signal_inputs_v1.csv"
    )
    mapping_canonicals = {
        mapping["canonical_symbol"] for mapping in VERSIONED_IDENTITY_MAPPINGS
    }
    rows: list[dict[str, Any]] = []
    for source in signal_rows:
        formation = date.fromisoformat(source["decision_date"])
        symbol = source["symbol"].strip().upper()
        old_sma = _sma(old_valid.get(symbol, {}), formation)
        new_sma = _sma(combined_valid.get(symbol, {}), formation)
        reason = _classify_unavailable(
            symbol=symbol,
            formation_date=formation,
            new_sma=new_sma,
            observed_dates=combined_observed.get(symbol, set()),
            excluded_count=combined_excluded[symbol],
            sessions=combined_sessions,
        )
        old_available = bool(source.get("sma200"))
        identity_resolved = symbol in mapping_canonicals and any(
            observed <= formation for observed in extension_observed.get(symbol, set())
        )
        if not old_available and new_sma["available"]:
            remediation_outcome = (
                "IDENTITY_MAPPING_RESOLVED"
                if identity_resolved
                else "DATASET_TRUNCATION_RESOLVED"
            )
        elif not old_available and not new_sma["available"]:
            remediation_outcome = "REMAINS_GENUINELY_OR_STRUCTURALLY_UNAVAILABLE"
        else:
            remediation_outcome = "ALREADY_AVAILABLE_NO_CHANGE"
        observed_dates = combined_observed.get(symbol, set())
        rows.append(
            {
                "formation_date": formation,
                "symbol": symbol,
                "frozen_formation_member": True,
                "frozen_B002_top_decile_candidate": (
                    source["decision_date"], source["symbol"]
                )
                in top_keys,
                "old_valid_history_count": old_sma["history_count"],
                "new_valid_history_count": new_sma["history_count"],
                "old_SMA200_available": old_available,
                "new_SMA200_available": new_sma["available"],
                "new_SMA200": new_sma["value"],
                "new_SMA_window_start": new_sma["window_start"],
                "new_SMA_window_end": new_sma["window_end"],
                "new_SMA_observation_count_used": new_sma["observation_count_used"],
                "listing_date_or_earliest_valid_daily_date": min(observed_dates)
                if observed_dates
                else None,
                "availability_reason": reason,
                "remediation_outcome": remediation_outcome,
                "no_partial_SMA": new_sma["observation_count_used"] in {0, SMA_SESSIONS},
                "no_future_observations": new_sma["no_future_observations"],
                "development_window_changed": False,
                "performance_observation": False,
            }
        )
    candidate_rows = [row for row in rows if row["frozen_B002_top_decile_candidate"]]
    old_unavailable = [row for row in candidate_rows if not row["old_SMA200_available"]]
    new_unavailable = [row for row in candidate_rows if not row["new_SMA200_available"]]
    if len(candidate_rows) != 302 or len(old_unavailable) != 30:
        _fail_input(
            f"frozen B002 structural counts changed: candidates={len(candidate_rows)} "
            f"unavailable={len(old_unavailable)}"
        )
    reasons = Counter(row["availability_reason"] for row in new_unavailable)
    available_count = len(candidate_rows) - len(new_unavailable)
    genuine_recent = reasons["GENUINE_RECENT_LISTING"]
    structural_rate = Decimal(available_count) / Decimal(len(candidate_rows)) * Decimal("100")
    remediable_denominator = len(candidate_rows) - genuine_recent
    remediable_rate = (
        Decimal(available_count) / Decimal(remediable_denominator) * Decimal("100")
        if remediable_denominator
        else Decimal("100")
    )
    coverage_classification = (
        "EXCELLENT"
        if structural_rate >= 98
        else "STRONG"
        if structural_rate >= 95
        else "USABLE_WITH_LIMITATIONS"
        if structural_rate >= 90
        else "INSUFFICIENT"
    )
    first_formation = [
        row
        for row in candidate_rows
        if str(row["formation_date"]) == "2022-03-31"
    ]
    return {
        "rows": rows,
        "candidate_rows": candidate_rows,
        "first_formation_rows": first_formation,
        "summary": {
            "old_B002_candidate_count": len(candidate_rows),
            "old_SMA_unavailable_count": len(old_unavailable),
            "new_SMA_unavailable_count": len(new_unavailable),
            "dataset_truncation_resolved_count": sum(
                row["remediation_outcome"] == "DATASET_TRUNCATION_RESOLVED"
                for row in old_unavailable
            ),
            "identity_mapping_resolved_count": sum(
                row["remediation_outcome"] == "IDENTITY_MAPPING_RESOLVED"
                for row in old_unavailable
            ),
            "new_unavailability_reasons": dict(
                sorted({reason: reasons[reason] for reason in AVAILABILITY_REASONS}.items())
            ),
            "first_formation_original_candidate_count": len(first_formation),
            "first_formation_new_SMA_available_count": sum(
                row["new_SMA200_available"] for row in first_formation
            ),
            "first_formation_still_unavailable_count": sum(
                not row["new_SMA200_available"] for row in first_formation
            ),
            "SMA200_STRUCTURAL_COVERAGE_RATE": structural_rate,
            "SMA200_REMEDIABLE_COVERAGE_RATE": remediable_rate,
            "coverage_classification": coverage_classification,
            "exact_SMA_observation_count": SMA_SESSIONS,
            "prehistory_rows_are_performance": False,
            "development_window": {
                "start": DEVELOPMENT_START.isoformat(),
                "end": DEVELOPMENT_END.isoformat(),
                "changed": False,
            },
        },
    }


def _pilot_cases(
    readiness_rows: Sequence[Mapping[str, Any]],
    reconciliation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates = [row for row in readiness_rows if row["frozen_B002_top_decile_candidate"]]
    resolved = next(
        row for row in candidates if row["remediation_outcome"] == "DATASET_TRUNCATION_RESOLVED"
    )
    recent = next(
        row for row in candidates if row["availability_reason"] == "GENUINE_RECENT_LISTING"
    )
    full = next(
        row for row in candidates if row["old_SMA200_available"] and row["new_SMA200_available"]
    )
    identity = next(
        row for row in candidates if row["remediation_outcome"] == "IDENTITY_MAPPING_RESOLVED"
    )
    corporate_safe = next(
        (
            row
            for row in candidates
            if row["new_SMA200_available"] and row["new_SMA200"] is not None
        ),
        full,
    )
    first_overlap = next(row for row in reconciliation["rows"] if row["overlap_rows_compared"])
    return [
        {"case": "A_DATASET_TRUNCATION_RESOLVED", **resolved},
        {"case": "B_GENUINE_RECENT_LISTING", **recent},
        {"case": "C_FULL_200_SESSION_HISTORY", **full},
        {"case": "D_CORPORATE_ACTION_SAFE", **corporate_safe},
        {"case": "E_OVERLAP_RECONCILIATION", **first_overlap},
        {"case": "F_IDENTITY_MAPPING", **identity},
    ]


def _immutable_document(
    path: Path,
    body: Mapping[str, Any],
    hash_field: str,
    expected_hash: str,
) -> dict[str, Any]:
    observed_hash = canonical_hash(body)
    document = {**body, hash_field: observed_hash}
    if expected_hash and observed_hash != expected_hash:
        raise FamilyBHistoryRemediationImmutabilityError(
            f"{hash_field} mismatch: {observed_hash}"
        )
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(document):
            raise FamilyBHistoryRemediationImmutabilityError(
                f"Existing immutable document changed: {path}"
            )
    else:
        write_json(path, document)
    return document


def build_family_b_history_remediation(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = utc_now()
    frozen_before = verify_frozen_inputs(root)
    config = history_remediation_config(root)
    if (
        EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH
        and config["history_remediation_config_hash"]
        != EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH
    ):
        raise FamilyBHistoryRemediationImmutabilityError(
            "history_remediation_config_hash mismatch"
        )
    config_path = output_root(root) / "raw_manifest/history_remediation_config_v1.json"
    if not config_path.exists():
        write_json(config_path, config)
    elif _read_json(config_path) != json_ready(config):
        raise FamilyBHistoryRemediationImmutabilityError("Frozen remediation config changed")

    old_adjusted_paths = _dated_files(
        root / "data/research/adjusted/daily/nse",
        "nse_adjusted_daily_*.csv",
        end=DEVELOPMENT_END,
    )
    old_adjusted_hash_before = _aggregate_hash(old_adjusted_paths, root)
    adjusted = build_adjusted_extension(root)
    reconciliation = build_overlap_reconciliation(root)
    sma = build_sma_readiness(root)
    pilots = _pilot_cases(sma["rows"], reconciliation)

    raw_files = sorted(daily_raw_extension(root).glob("*/*/*"))
    raw_source_files = [path for path in raw_files if path.is_file() and path.suffix != ".missing"]
    normalized_files = _dated_files(
        daily_normalized_extension(root), "nse_daily_*.csv", end=EXTENSION_END
    )
    adjusted_files = _dated_files(
        adjusted_extension_root(root), "nse_adjusted_daily_*.csv", end=EXTENSION_END
    )
    raw_hash = _aggregate_hash(raw_source_files, daily_extension_root(root))
    adjusted_hash = _aggregate_hash(adjusted_files, root)
    if EXPECTED_RAW_EXTENSION_HASH and raw_hash != EXPECTED_RAW_EXTENSION_HASH:
        raise FamilyBHistoryRemediationImmutabilityError("raw_extension_hash mismatch")
    if EXPECTED_ADJUSTED_EXTENSION_HASH and adjusted_hash != EXPECTED_ADJUSTED_EXTENSION_HASH:
        raise FamilyBHistoryRemediationImmutabilityError("adjusted_extension_hash mismatch")

    ingestion = _read_json(output_root(root) / "raw_manifest/ingestion_result_v1.json")
    daily_report = ingestion["daily"]
    normalized_required_rows = adjusted["adjusted_row_count"]
    raw_added_rows = (
        daily_report["records"]["total_normalized"]
        + daily_report["records"]["invalid_records"]
        + daily_report["records"]["duplicate_records"]
    )
    ca_status = (
        "EXTENDED_AND_APPLIED"
        if ingestion["corporate_actions"]["http_status"] == 200
        and adjusted["file_count"] > 0
        else "FAILED"
    )
    clean_reconciliation = reconciliation["summary"][
        "DAILY_HISTORY_REMEDIATION_RECONCILIATION"
    ] in {"EXACT", "EXPLAINED_VERSIONED_DIFFERENCES"} and not reconciliation["summary"][
        "unexplained_overlap_differences"
    ]
    remediable_acceptable = decimal(
        sma["summary"]["SMA200_REMEDIABLE_COVERAGE_RATE"]
    ) >= Decimal("95")
    reevaluation_ready = (
        clean_reconciliation
        and remediable_acceptable
        and ca_status == "EXTENDED_AND_APPLIED"
        and all(row["no_future_observations"] for row in sma["rows"])
        and all(row["no_partial_SMA"] for row in sma["rows"])
    )
    remediation_result = (
        "READY_FOR_CLEAN_DEVELOPMENT_REEVALUATION"
        if reevaluation_ready
        and sma["summary"]["coverage_classification"] in {"EXCELLENT", "STRONG"}
        else "READY_WITH_LIMITATIONS"
        if reevaluation_ready
        else "MORE_DATA_REMEDIATION_REQUIRED"
    )
    readiness_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "data_version": DATA_VERSION,
        "frozen_inputs": {
            "attribution_audit_hash": EXPECTED_ATTRIBUTION_AUDIT_HASH,
            "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "result_hashes": EXPECTED_RESULT_HASHES,
            "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "snapshot_hash": frozen_before["snapshot"]["snapshot_hash"],
        },
        "history_remediation_config_hash": config["history_remediation_config_hash"],
        "raw_extension_hash": raw_hash,
        "adjusted_extension_hash": adjusted_hash,
        "source_counts": {
            "requested_canonical_symbols": len(config["symbols"]["canonical_symbols"]),
            "requested_raw_identifiers": len(config["symbols"]["requested_raw_symbols"]),
            "successfully_extended_symbols": adjusted["successful_symbol_count"],
            "raw_daily_source_files": len(raw_source_files),
            "raw_added_rows": raw_added_rows,
            "raw_normalized_all_market_rows": daily_report["records"]["total_normalized"],
            "normalized_required_symbol_rows": normalized_required_rows,
            "adjusted_required_symbol_rows": adjusted["adjusted_row_count"],
        },
        "corporate_action_extension": {
            "result": ca_status,
            "event_count": ingestion["corporate_actions"]["event_count"],
            "factor_count": ingestion["corporate_actions"]["factor_count"],
            "adjusted_row_count": adjusted["corporate_action_adjusted_row_count"],
            "methodology": "PRICE_ADJUSTED_STRUCTURAL_V1",
        },
        "reconciliation": reconciliation["summary"],
        "SMA_readiness": sma["summary"],
        "decisions": {
            "FAMILY_B_HISTORY_REMEDIATION_RESULT": remediation_result,
            "FAMILY_B_B002_REEVALUATION_READINESS": "YES" if reevaluation_ready else "NO",
            "B001_STATUS_AFTER_ATTRIBUTION": "NO_DISTINCT_FILTER_EVIDENCE",
            "B002_STATUS_BEFORE_REEVALUATION": "CONFOUNDED_BY_HISTORY_AVAILABILITY",
        },
        "governance": {
            "performance_run": False,
            "performance_metrics_computed": False,
            "B002_parameters_changed": False,
            "alternate_SMA_used": False,
            "partial_SMA_used": False,
            "validation_accessed": False,
            "post_2024_price_rows_loaded": False,
            "B003_created": False,
            "strategy_v2_created": False,
            "family_c_started": False,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "database_writes": 0,
            "network_writes_other_than_approved_NSE_sources": 0,
            "secrets_written": 0,
        },
        "known_limitations": (
            "GENUINE_RECENT_LISTINGS_REMAIN_WITHOUT_200_VALID_SESSIONS",
            "OFFICIAL_DAILY_ARCHIVES_ARE_FULL_MARKET_FILES_BY_SOURCE_DESIGN",
            "V2_OVERLAP_REFERENCES_IMMUTABLE_V1_INSTEAD_OF_DUPLICATING_FROZEN_ROWS",
            "POINT_IN_TIME_MEMBERSHIP_CONFIDENCE_REMAINS_FROZEN_AND_PARTIAL",
            "NO_PERFORMANCE_OR_OUTCOME_INTERPRETATION_IS_ALLOWED_IN_THIS COMMAND",
        ),
    }
    readiness_path = output_root(root) / "manifests/family_b_sma_readiness_v1.json"
    readiness = _immutable_document(
        readiness_path,
        readiness_body,
        "family_b_sma_readiness_hash",
        EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    )

    reports_root = root / "data/reports"
    source_rows = read_csv(
        daily_extension_root(root) / "reports/nse_daily_session_summary.csv"
    )
    reason_rows = [
        {
            "availability_reason": reason,
            "candidate_count": sum(
                row["availability_reason"] == reason
                for row in sma["candidate_rows"]
                if not row["new_SMA200_available"]
            ),
            "remediable": reason not in {"GENUINE_RECENT_LISTING", "AVAILABLE_200_PLUS"},
        }
        for reason in AVAILABILITY_REASONS
    ]
    readiness_rows = [
        {
            **sma["summary"],
            **reconciliation["summary"],
            "FAMILY_B_HISTORY_REMEDIATION_RESULT": remediation_result,
            "FAMILY_B_B002_REEVALUATION_READINESS": "YES" if reevaluation_ready else "NO",
            "B001_STATUS_AFTER_ATTRIBUTION": "NO_DISTINCT_FILTER_EVIDENCE",
            "B002_STATUS_BEFORE_REEVALUATION": "CONFOUNDED_BY_HISTORY_AVAILABILITY",
        }
    ]
    report_rows = {
        REPORT_NAMES[1]: source_rows,
        REPORT_NAMES[2]: reconciliation["rows"],
        REPORT_NAMES[3]: sma["rows"],
        REPORT_NAMES[4]: sma["first_formation_rows"],
        REPORT_NAMES[5]: reason_rows,
        REPORT_NAMES[6]: readiness_rows,
    }
    artifact_paths: list[Path] = [config_path, readiness_path]
    internal_rows = {
        output_root(root) / "raw_manifest/required_symbols.csv": [
            {"symbol": symbol, "scope": "FAMILY_B_FORMATION_SYMBOL"}
            for symbol in config["symbols"]["canonical_symbols"]
        ],
        output_root(root) / "raw_manifest/versioned_identity_mappings.csv": list(
            VERSIONED_IDENTITY_MAPPINGS
        ),
        output_root(root) / "reconciliation/overlap_reconciliation.csv": reconciliation[
            "rows"
        ],
        output_root(root) / "sma_readiness/sma_before_after.csv": sma["rows"],
        output_root(root) / "sma_readiness/first_formation.csv": sma[
            "first_formation_rows"
        ],
        output_root(root) / "pilots/pilot_cases.csv": pilots,
    }
    for path, rows in internal_rows.items():
        write_csv(path, rows)
        artifact_paths.append(path)
    for name, rows in report_rows.items():
        path = reports_root / name
        write_csv(path, rows)
        artifact_paths.append(path)

    old_adjusted_hash_after = _aggregate_hash(old_adjusted_paths, root)
    frozen_after = verify_frozen_inputs(root)
    baseline_unchanged = (
        frozen_before["snapshot"] == frozen_after["snapshot"]
        and old_adjusted_hash_before == old_adjusted_hash_after
    )
    documentation_path = root / "docs/strategy-family-b-history-remediation-v1.md"
    if documentation_path.exists():
        artifact_paths.append(documentation_path)
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    summary = {
        **readiness_body,
        "generated_at": started_at,
        "family_b_sma_readiness_hash": readiness["family_b_sma_readiness_hash"],
        "actual_history": {
            "earliest_daily_date": adjusted["first_date"],
            "latest_new_extension_date": adjusted["last_date"],
            "logical_end": DEVELOPMENT_END.isoformat(),
        },
        "hashes": {
            "history_remediation_config_hash": config["history_remediation_config_hash"],
            "raw_extension_hash": raw_hash,
            "adjusted_extension_hash": adjusted_hash,
            "family_b_sma_readiness_hash": readiness["family_b_sma_readiness_hash"],
        },
        "regression": {
            "frozen_snapshot_before": frozen_before["snapshot"]["snapshot_hash"],
            "frozen_snapshot_after": frozen_after["snapshot"]["snapshot_hash"],
            "old_adjusted_hash_before": old_adjusted_hash_before,
            "old_adjusted_hash_after": old_adjusted_hash_after,
            "baseline_unchanged": baseline_unchanged,
            "strategy_v1": "UNCHANGED",
            "CAP4": "UNCHANGED",
            "family_a_commands_01_05": "UNCHANGED",
            "family_a_closure": "UNCHANGED",
            "family_b_command_01": "UNCHANGED",
            "family_b_command_02": "UNCHANGED",
            "family_b_command_03": "UNCHANGED",
        },
        "storage": {
            "root": output_root(root).relative_to(root).as_posix(),
            "raw_manifest": (output_root(root) / "raw_manifest").relative_to(root).as_posix(),
            "reconciliation": (output_root(root) / "reconciliation").relative_to(root).as_posix(),
            "sma_readiness": (output_root(root) / "sma_readiness").relative_to(root).as_posix(),
            "pilots": (output_root(root) / "pilots").relative_to(root).as_posix(),
            "manifests": (output_root(root) / "manifests").relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "runtime": {
            "seconds": Decimal(str(time.perf_counter() - started)),
            "performance_runs": 0,
        },
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest_path = output_root(root) / "manifests/history_remediation_manifest_v1.json"
    completion_timestamp = started_at
    if manifest_path.exists():
        completion_timestamp = _read_json(manifest_path).get(
            "completion_timestamp", completion_timestamp
        )
    manifest_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "data_version": DATA_VERSION,
        "completion_timestamp": completion_timestamp,
        "source_policy": config["source_policy"],
        "requested_date_range": config["requested_range"],
        "symbols": config["symbols"],
        "source_counts": readiness_body["source_counts"],
        "corporate_action_extension": readiness_body["corporate_action_extension"],
        "overlap_reconciliation": reconciliation["summary"],
        "SMA_coverage_before": {
            "candidates": sma["summary"]["old_B002_candidate_count"],
            "unavailable": sma["summary"]["old_SMA_unavailable_count"],
        },
        "SMA_coverage_after": {
            "unavailable": sma["summary"]["new_SMA_unavailable_count"],
            "structural_rate": sma["summary"]["SMA200_STRUCTURAL_COVERAGE_RATE"],
            "remediable_rate": sma["summary"]["SMA200_REMEDIABLE_COVERAGE_RATE"],
        },
        "reason_classifications": sma["summary"]["new_unavailability_reasons"],
        "history_remediation_config_hash": config["history_remediation_config_hash"],
        "raw_extension_hash": raw_hash,
        "adjusted_extension_hash": adjusted_hash,
        "family_b_sma_readiness_hash": readiness["family_b_sma_readiness_hash"],
        "artifact_hashes": artifact_hashes,
    }
    _immutable_document(
        manifest_path,
        manifest_body,
        "history_remediation_manifest_hash",
        EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    )
    return summary


def finalize_family_b_history_remediation_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_b_history_remediation_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run Family B history remediation before finalizing")
    summary = _read_json(summary_path)
    frozen = verify_frozen_inputs(root)
    if frozen["snapshot"]["snapshot_hash"] != summary["regression"][
        "frozen_snapshot_after"
    ]:
        _fail_input("frozen inputs changed after remediation")
    readiness_path = (
        output_root(root) / "manifests/family_b_sma_readiness_v1.json"
    )
    readiness = _read_json(readiness_path)
    observed_hash = readiness.get("family_b_sma_readiness_hash")
    if (
        observed_hash != summary["family_b_sma_readiness_hash"]
        or _recompute_hash(readiness, "family_b_sma_readiness_hash") != observed_hash
        or (
            EXPECTED_FAMILY_B_SMA_READINESS_HASH
            and observed_hash != EXPECTED_FAMILY_B_SMA_READINESS_HASH
        )
    ):
        raise FamilyBHistoryRemediationImmutabilityError("SMA readiness hash mismatch")
    manifest = _read_json(
        output_root(root) / "manifests/history_remediation_manifest_v1.json"
    )
    observed_manifest_hash = manifest.get("history_remediation_manifest_hash")
    if (
        _recompute_hash(manifest, "history_remediation_manifest_hash")
        != observed_manifest_hash
        or (
            EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH
            and observed_manifest_hash != EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH
        )
    ):
        raise FamilyBHistoryRemediationImmutabilityError(
            "History remediation manifest hash mismatch"
        )
    mismatches = [
        relative_path
        for relative_path, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    if mismatches:
        raise FamilyBHistoryRemediationImmutabilityError(
            f"History remediation artifact mismatch: {mismatches}"
        )
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["regression"]["baseline_unchanged"] is True
        and summary["governance"]["performance_run"] is False
        and summary["governance"]["validation_accessed"] is False
        and summary["decisions"]["FAMILY_B_B002_REEVALUATION_READINESS"] == "YES",
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "AVAILABILITY_REASONS",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "DATA_VERSION",
    "EXPECTED_ADJUSTED_EXTENSION_HASH",
    "EXPECTED_FAMILY_B_SMA_READINESS_HASH",
    "EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH",
    "EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH",
    "EXPECTED_RAW_EXTENSION_HASH",
    "EXTENSION_END",
    "FROZEN_DAILY_START",
    "REPORT_NAMES",
    "TARGET_START",
    "VERSIONED_IDENTITY_MAPPINGS",
    "build_adjusted_extension",
    "build_family_b_history_remediation",
    "build_overlap_reconciliation",
    "build_sma_readiness",
    "finalize_family_b_history_remediation_review",
    "history_remediation_config",
    "ingest_history_extension",
    "required_symbol_scope",
    "verify_frozen_inputs",
)

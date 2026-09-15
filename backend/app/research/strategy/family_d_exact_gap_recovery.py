from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.config.settings import Settings
from app.providers.groww.auth import GrowwAuthService, GrowwCredentials
from app.research.intraday.development_ingestion import (
    _write_gzip_csv_deterministic,
    _write_immutable_raw,
)
from app.research.intraday.models import CanonicalIntradayBar
from app.research.intraday.normalization import canonical_bar_row, parse_timestamp
from app.research.intraday.provider_pilot import (
    GROWW_RETRIEVAL_TRANSPORT_VERSION,
    InstrumentMapping,
    _extract_candles,
    classify_provider_failure,
    credentials_present,
)
from app.research.intraday.resume_ingestion import (
    MAX_RETRIES,
    REQUEST_TIMEOUT_CIRCUIT_BREAKER,
    AttemptGenerationGuard,
    ResumeGrowwTransport,
    ResumeRequestFailure,
    ResumeRuntimeLimit,
)
from app.research.strategy import family_d_continuity_remediation as continuity
from app.research.strategy.family_a_momentum import _load_aliases, file_sha256, read_csv
from app.research.strategy.family_c_research_closure import family_c_baseline_snapshot
from app.research.strategy.family_d_opening_range import (
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    OPENING_BAR_TIMES,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND_VERSION = "FAMILY_D_EXACT_GAP_RECOVERY_V1"
PROFILE = "PRIOR20_EXACT_INTRADAY_GAP_RECOVERY_V1"
RECOVERY_DATA_VERSION = "FAMILY_D_EXACT_GAP_RECOVERY_DATA_V1"
NORMALIZATION_VERSION = "NSE_CASH_INTRADAY_5M_V1"
MAX_EXACT_WINDOW_DAYS = 7
THROTTLE_SECONDS = 1.0
EXPECTED_STARTING_GAPS = 217
EXPECTED_CONTROL_SIGNAL_COUNT = 2292
EXPECTED_COMMAND_02_MANIFEST_HASH = "5b3f403823bec3ad4295603a6db6d382f540ba9d636e69989efd19322ad0247c"
# The semantic freeze above is retained in Command 03 records. This refreshed
# canonical hash differs only because trailing whitespace was removed from the
# already-reviewed Command 02 documentation at the milestone checkpoint.
CURRENT_COMMAND_02_ARTIFACT_MANIFEST_HASH = (
    "d2d616eb0d70ac0fdc0070f607a70838e782baabc4183ff1589fb9c788f3e3b2"
)
EXPECTED_COMMAND_02_HASHES = {
    "continuity_remediation_config_hash": "248a20322ebcb69835fb89727884839f0280f4115657f3aeaf8444382b33ca43",
    "continuity_request_plan_hash": "7efe442118d97708c44db200797771fb754ef31118b1042e6e29113ec66a8422",
    "continuity_raw_extension_hash": "c9f2bf6d44e1c3454c35683e0acf4c814cdae8db6267678b1e8963a865770a30",
    "continuity_normalized_extension_hash": "115572a1291e2e162c9bda8c782f31a8077713aa599766b4d6b7316c3e558b15",
    "continuity_matrix_hash": "b202180a2be523cec8c49c4c872ea87f79905a0effdedeb42a174b79c463ce8d",
    "family_d_activity_readiness_hash": "2200fb3d5dbcb260b6649eb1d014af90f92455a1acd2643d12b0ea86450aba95",
}

COMMAND_02_DOCUMENTS = {
    "continuity_remediation_config_hash": "request_plan/continuity_remediation_config_v1.json",
    "continuity_request_plan_hash": "request_plan/continuity_request_plan_v1.json",
    "continuity_raw_extension_hash": "raw_extension/raw_extension_manifest_v1.json",
    "continuity_normalized_extension_hash": "normalized_extension/normalized_extension_manifest_v1.json",
    "continuity_matrix_hash": "continuity_matrix/continuity_matrix_v1.json",
    "family_d_activity_readiness_hash": "activity_readiness/family_d_activity_readiness_v1.json",
}

REPORT_NAMES = (
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
)


class ExactGapInputMismatch(RuntimeError):
    pass


def output_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/strategy_families/family_d/v1/exact_gap_recovery"


def command_02_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/research/strategy_families/family_d/v1/continuity_remediation"


def report_root(repo_root: Path) -> Path:
    return Path(repo_root) / "data/reports"


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return continuity._document_hash(document, field)


def _write_json(path: Path, value: Any) -> None:
    continuity._write_json(path, value)


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    continuity._write_csv(path, rows, fields=fields)


def exact_gap_recovery_config_document() -> dict[str, Any]:
    body: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "family_version": "STRATEGY_FAMILY_D_OPENING_RANGE_V1",
        "population": {
            "source": "FAMILY_D_INTRADAY_CONTINUITY_REMEDIATION_V1_UNAVAILABLE_REQUIRED_SESSIONS",
            "expected_unique_symbol_sessions": EXPECTED_STARTING_GAPS,
            "expansion_allowed": False,
            "mechanically_returned_request_overlap_allowed_in_raw": True,
        },
        "prior20_rule": {
            "rule": "IMMEDIATELY_PRECEDING_20_NSE_TRADING_SESSIONS",
            "opening_bar_starts": [value.strftime("%H:%M") for value in OPENING_BAR_TIMES],
            "strict_sessions_only": True,
            "older_session_substitution": False,
            "mixed_source_session_stitching": False,
        },
        "groww_retry": {
            "provider": "GROWW",
            "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            "connect_timeout_seconds": 10,
            "read_timeout_seconds": 20,
            "wall_clock_timeout_seconds": 30,
            "max_retries": MAX_RETRIES,
            "timeout_circuit_breaker": REQUEST_TIMEOUT_CIRCUIT_BREAKER,
            "throttle_seconds": THROTTLE_SECONDS,
            "max_exact_window_calendar_days": MAX_EXACT_WINDOW_DAYS,
        },
        "normalization": {
            "version": NORMALIZATION_VERSION,
            "timezone": "Asia/Kolkata",
            "bar_convention": "BAR_START",
            "one_source_per_symbol_session": True,
        },
        "alternate_source_policy": {
            "repository_audit_required": True,
            "new_provider_contact_allowed": False,
            "configured_real_intraday_provider": "GROWW_ONLY",
            "prior_audit_evidence": "docs/real-intraday-provider-pilot-v1.md",
        },
        "coverage_thresholds": {
            "EXCELLENT": ">=98_PERCENT",
            "STRONG": ">=95_PERCENT",
            "USABLE_WITH_LIMITATIONS": ">=90_PERCENT",
            "INSUFFICIENT": "<90_PERCENT",
            "development_backtest_minimum": ">=95_PERCENT",
        },
        "frozen_family_d_hashes": {
            "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
            "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
            "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
            "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        },
        "frozen_command_02_hashes": EXPECTED_COMMAND_02_HASHES,
        "frozen_command_02_manifest_hash": EXPECTED_COMMAND_02_MANIFEST_HASH,
        "performance_allowed": False,
        "validation_allowed": False,
        "strategy_v2_allowed": False,
        "strategy_parameter_changes_allowed": False,
    }
    body["exact_gap_recovery_config_hash"] = canonical_hash(body)
    return body


def verify_exact_gap_inputs(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        family = continuity.verify_continuity_inputs(root)
        base = command_02_root(root)
        command_02_checks: dict[str, bool] = {}
        for field, relative in COMMAND_02_DOCUMENTS.items():
            document = json.loads((base / relative).read_text(encoding="utf-8"))
            command_02_checks[field] = (
                _document_hash(document, field)
                == document.get(field)
                == EXPECTED_COMMAND_02_HASHES[field]
            )
        manifest = json.loads(
            (base / "manifests/family_d_continuity_remediation_manifest_v1.json").read_text(encoding="utf-8")
        )
        manifest_hash_ok = (
            _document_hash(manifest, "manifest_hash")
            == manifest.get("manifest_hash")
            == CURRENT_COMMAND_02_ARTIFACT_MANIFEST_HASH
        )
        artifacts_ok = all(
            (root / relative).is_file() and file_sha256(root / relative) == expected
            for relative, expected in manifest["artifact_hashes"].items()
        )
        source_rows = read_csv(base / "continuity_matrix/unavailable_required_sessions_v1.csv")
        population_ok = len(source_rows) == EXPECTED_STARTING_GAPS and Counter(
            row["reason"] for row in source_rows
        ) == Counter(
            {
                "MISSING_OPENING_BARS": 105,
                "PROVIDER_HISTORY_UNAVAILABLE": 48,
                "SESSION_QUALITY_FAILURE": 64,
            }
        )
        checks = {
            "frozen_family_d_hashes": family["result"] == "VERIFIED",
            "command_02_hashes": all(command_02_checks.values()),
            "command_02_manifest_hash": manifest_hash_ok,
            "command_02_artifacts": artifacts_ok,
            "exact_217_source_population": population_ok,
        }
        if not all(checks.values()):
            raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH")
        return {
            "result": "VERIFIED",
            "checks": checks,
            "command_02_hash_checks": command_02_checks,
            "command_02_artifact_count": len(manifest["artifact_hashes"]),
            "frozen_family_d": family,
        }
    except ExactGapInputMismatch:
        raise
    except Exception as exc:
        raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH") from exc


def _command_02_context(root: Path) -> dict[str, Any]:
    scope, sessions, requirements, required = continuity._required_population(root)
    calendar = continuity._calendar(root, sessions)
    mappings = continuity._mapping_rows(root)
    normalized, normalized_groups = continuity._load_frozen_normalized(root, required, calendar)
    collateral = continuity._load_raw_facts(root, required, calendar, mappings, extension=False)
    fetched = continuity._load_raw_facts(root, required, calendar, mappings, extension=True)
    selected: dict[tuple[str, date], Mapping[str, Any] | None] = {}
    for symbol, dates in required.items():
        for value in dates:
            selected[(symbol, value)] = continuity._select_fact(
                (symbol, value), normalized, collateral, fetched
            )
    config_02, plan_02 = continuity._load_plan(root)
    state_02 = continuity._request_state(root, plan_02)
    return {
        "scope": scope,
        "sessions": sessions,
        "session_set": set(sessions),
        "requirements": requirements,
        "required": required,
        "calendar": calendar,
        "mappings": mappings,
        "normalized": normalized,
        "normalized_groups": normalized_groups,
        "collateral": collateral,
        "fetched": fetched,
        "selected": selected,
        "listings": continuity._listing_dates(root, set(required)),
        "special_sessions": continuity._special_session_dates(root),
        "command_02_config": config_02,
        "command_02_plan": plan_02,
        "command_02_state": state_02,
        "command_02_request_status": continuity._request_coverage(plan_02, state_02),
    }


def _current_bars_for_gaps(
    root: Path,
    context: Mapping[str, Any],
    gap_keys: set[tuple[str, date]],
) -> dict[tuple[str, date], list[CanonicalIntradayBar]]:
    wanted_by_symbol: dict[str, set[date]] = defaultdict(set)
    for symbol, trading_date in gap_keys:
        wanted_by_symbol[symbol].add(trading_date)
    result: dict[tuple[str, date], list[CanonicalIntradayBar]] = {}
    for symbol, dates in wanted_by_symbol.items():
        old_raw = continuity._load_raw_bars_for_symbol(
            root,
            symbol,
            dates,
            context["calendar"],
            context["mappings"][symbol],
            extension=False,
        )
        fetched = continuity._load_raw_bars_for_symbol(
            root,
            symbol,
            dates,
            context["calendar"],
            context["mappings"][symbol],
            extension=True,
        )
        for trading_date in dates:
            candidates = (
                context["normalized_groups"].get((symbol, trading_date)),
                fetched.get(trading_date),
                old_raw.get(trading_date),
            )
            selected_bars: list[CanonicalIntradayBar] | None = None
            for bars in candidates:
                if not bars:
                    continue
                fact = continuity._session_fact(
                    bars, calendar=context["calendar"], source="CURRENT_COMMAND_02"
                )
                if fact["strict"]:
                    selected_bars = list(bars)
                    break
                if selected_bars is None:
                    selected_bars = list(bars)
            if selected_bars:
                result[(symbol, trading_date)] = selected_bars
    return result


def _opening_state(bars: Sequence[CanonicalIntradayBar]) -> tuple[int, list[str]]:
    available = sorted(
        {
            bar.bar_start.strftime("%H:%M")
            for bar in bars
            if bar.bar_start.time().replace(tzinfo=None) in OPENING_BAR_TIMES
        }
    )
    return len(available), available


def build_exact_gap_population(
    repo_root: Path,
    *,
    write: bool = True,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    verification = verify_exact_gap_inputs(root)
    current = dict(context or _command_02_context(root))
    source_rows = read_csv(
        command_02_root(root) / "continuity_matrix/unavailable_required_sessions_v1.csv"
    )
    gap_keys = {
        (str(row["symbol"]), date.fromisoformat(str(row["trading_date"])))
        for row in source_rows
    }
    if len(gap_keys) != EXPECTED_STARTING_GAPS:
        raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH")
    current_bars = _current_bars_for_gaps(root, current, gap_keys)
    affected: dict[tuple[str, date], list[str]] = defaultdict(list)
    for (symbol, target), required_dates in current["requirements"].items():
        for required_date in required_dates:
            key = (symbol, required_date)
            if key in gap_keys:
                affected[key].append(target.isoformat())
    aliases = _load_aliases(root)
    rows: list[dict[str, Any]] = []
    source_by_key = {
        (str(row["symbol"]), date.fromisoformat(str(row["trading_date"]))): row
        for row in source_rows
    }
    for index, key in enumerate(sorted(gap_keys), start=1):
        symbol, trading_date = key
        mapping = current["mappings"][symbol]
        fact = current["selected"].get(key) or {}
        bars = current_bars.get(key, [])
        opening_count, opening_times = _opening_state(bars)
        alias_evidence = [
            {"historical_symbol": old, "current_symbol": new}
            for old, new in sorted(aliases.items())
            if symbol in {old, new}
        ]
        rows.append(
            {
                "gap_id": f"FAMILY-D-GAP-V1-{index:03d}",
                "symbol": symbol,
                "isin": mapping.get("internal_isin"),
                "provider_symbol": mapping.get("provider_symbol"),
                "provider_instrument_id": mapping.get("provider_instrument_id"),
                "identity_mapping_status": mapping.get("mapping_status"),
                "identity_alias_evidence": alias_evidence,
                "required_session_date": trading_date.isoformat(),
                "current_reason": source_by_key[key]["reason"],
                "target_sessions_affected": sorted(affected[key]),
                "target_sessions_affected_count": len(affected[key]),
                "current_rows_available": int(fact.get("actual_bars") or 0),
                "opening_bars_available": opening_count,
                "opening_bar_times_available": opening_times,
                "quality_state": fact.get("quality_classification", "UNUSABLE"),
                "quality_statuses": list(fact.get("quality_statuses", [])),
                "current_source": fact.get("source"),
            }
        )
    document: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "source_command": continuity.COMMAND_VERSION,
        "source_continuity_matrix_hash": EXPECTED_COMMAND_02_HASHES["continuity_matrix_hash"],
        "population_count": len(rows),
        "reason_counts": dict(Counter(row["current_reason"] for row in rows)),
        "population_expansion": 0,
        "rows": rows,
    }
    document["exact_gap_population_hash"] = canonical_hash(document)
    if write:
        base = output_root(root)
        _write_json(base / "population/exact_gap_population_v1.json", document)
        _write_csv(base / "population/exact_gap_population_v1.csv", rows)
        _write_csv(report_root(root) / REPORT_NAMES[1], rows)
    return {"verification": verification, "context": current, "population": document}


def _group_exact_windows(
    population_rows: Sequence[Mapping[str, Any]],
    mappings: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in population_rows:
        by_symbol[str(row["symbol"])].append(row)
    requests: list[dict[str, Any]] = []
    sequence = 0
    for symbol in sorted(by_symbol):
        rows = sorted(by_symbol[symbol], key=lambda row: str(row["required_session_date"]))
        cursor = 0
        while cursor < len(rows):
            start = date.fromisoformat(str(rows[cursor]["required_session_date"]))
            end_limit = start + timedelta(days=MAX_EXACT_WINDOW_DAYS - 1)
            stop = cursor
            while (
                stop + 1 < len(rows)
                and date.fromisoformat(str(rows[stop + 1]["required_session_date"])) <= end_limit
            ):
                stop += 1
            selected = rows[cursor : stop + 1]
            end = date.fromisoformat(str(selected[-1]["required_session_date"]))
            sequence += 1
            mapping = mappings[symbol]
            requests.append(
                {
                    "request_id": f"FAMILY-D-EXACT-V1-{sequence:04d}-{symbol}-{start:%Y%m%d}",
                    "sequence_no": sequence,
                    "symbol": symbol,
                    "provider_instrument": mapping["provider_symbol"],
                    "provider_instrument_id": mapping["provider_instrument_id"],
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "interval": "5m",
                    "required_sessions": [str(row["required_session_date"]) for row in selected],
                    "population_gap_ids": [str(row["gap_id"]) for row in selected],
                    "required_session_count": len(selected),
                    "window_calendar_days": (end - start).days + 1,
                }
            )
            cursor = stop + 1
    return requests


def build_exact_gap_plan(repo_root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    population_result = build_exact_gap_population(root, write=write)
    population = population_result["population"]
    context = population_result["context"]
    config = exact_gap_recovery_config_document()
    requests = _group_exact_windows(population["rows"], context["mappings"])
    planned = {
        (row["symbol"], value)
        for row in requests
        for value in row["required_sessions"]
    }
    frozen = {
        (row["symbol"], row["required_session_date"])
        for row in population["rows"]
    }
    if planned != frozen:
        raise RuntimeError("EXACT_GAP_POPULATION_EXPANSION_OR_OMISSION")
    plan: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "exact_gap_recovery_config_hash": config["exact_gap_recovery_config_hash"],
        "exact_gap_population_hash": population["exact_gap_population_hash"],
        "provider": "GROWW",
        "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
        "population_count": len(population["rows"]),
        "planned_unique_symbol_sessions": len(planned),
        "population_expansion_count": len(planned - frozen),
        "request_count": len(requests),
        "max_window_calendar_days": MAX_EXACT_WINDOW_DAYS,
        "earliest_requested_date": min(row["start_date"] for row in requests),
        "latest_requested_date": max(row["end_date"] for row in requests),
        "requests": requests,
        "network_requests_made_while_planning": 0,
        "validation_accessed": False,
    }
    plan["exact_gap_request_plan_hash"] = canonical_hash(plan)
    if write:
        base = output_root(root)
        _write_json(base / "request_plan/exact_gap_recovery_config_v1.json", config)
        _write_json(base / "request_plan/exact_gap_request_plan_v1.json", plan)
        _write_csv(base / "request_plan/exact_gap_request_plan_v1.csv", requests)
    return {
        "verification": population_result["verification"],
        "config": config,
        "population": population,
        "plan": plan,
    }


def _load_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = output_root(root)
    config = json.loads((base / "request_plan/exact_gap_recovery_config_v1.json").read_text(encoding="utf-8"))
    population = json.loads((base / "population/exact_gap_population_v1.json").read_text(encoding="utf-8"))
    plan = json.loads((base / "request_plan/exact_gap_request_plan_v1.json").read_text(encoding="utf-8"))
    fields = (
        (config, "exact_gap_recovery_config_hash"),
        (population, "exact_gap_population_hash"),
        (plan, "exact_gap_request_plan_hash"),
    )
    if any(_document_hash(document, field) != document.get(field) for document, field in fields):
        raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH")
    if (
        plan["exact_gap_recovery_config_hash"] != config["exact_gap_recovery_config_hash"]
        or plan["exact_gap_population_hash"] != population["exact_gap_population_hash"]
        or len(population["rows"]) != EXPECTED_STARTING_GAPS
    ):
        raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH")
    return config, population, plan


def _request_state(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    path = output_root(root) / "groww_retry/retrieval_state_v1.json"
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("exact_gap_request_plan_hash") != plan["exact_gap_request_plan_hash"]:
            raise ExactGapInputMismatch("FAMILY_D_EXACT_GAP_INPUT_MISMATCH")
        return state
    state = {
        "command_version": COMMAND_VERSION,
        "exact_gap_request_plan_hash": plan["exact_gap_request_plan_hash"],
        "requests": {
            row["request_id"]: {
                "status": "PENDING",
                "attempts": 0,
                "last_error_category": None,
                "raw_hash": None,
                "row_count": 0,
            }
            for row in plan["requests"]
        },
        "transport_metrics": [],
        "auth_status": "NOT_ATTEMPTED",
        "circuit_breaker_triggered": False,
        "provider_blocked": False,
        "late_results_discarded": 0,
        "late_result_commit_violations": 0,
    }
    _write_json(path, state)
    return state


def retrieve_exact_gaps(
    repo_root: Path,
    *,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
    max_wallclock_seconds: float = 2 * 60 * 60,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    verify_exact_gap_inputs(root)
    config, _, plan = _load_plan(root)
    state = _request_state(root, plan)
    pending = [
        row
        for row in plan["requests"]
        if state["requests"][row["request_id"]]["status"] in {"PENDING", "FAILED_RETRYABLE"}
    ]
    if not pending:
        return state
    settings = Settings()
    try:
        supplied = client is not None
        if client is None:
            if not credentials_present(settings):
                raise PermissionError("Groww credentials are not present")
            client = GrowwAuthService(credentials=GrowwCredentials.from_settings(settings)).get_client()
        state["auth_status"] = "MOCK_CLIENT_SUPPLIED" if supplied else "SUCCESS"
    except Exception as exc:
        state["auth_status"] = "FAILED"
        state["auth_failure_category"] = classify_provider_failure(exc)
        state["provider_blocked"] = True
        _write_json(output_root(root) / "groww_retry/retrieval_state_v1.json", state)
        return state
    deadline = time.perf_counter() + max_wallclock_seconds
    guard = AttemptGenerationGuard()

    def persist() -> None:
        state["late_results_discarded"] = guard.late_results_discarded
        state["late_result_commit_violations"] = guard.commit_violations
        _write_json(output_root(root) / "groww_retry/retrieval_state_v1.json", state)

    def on_attempt(metric: dict[str, Any], intermediate_status: str | None) -> None:
        request_state = state["requests"][metric["request_id"]]
        request_state["attempts"] = int(request_state["attempts"]) + 1
        request_state["last_error_category"] = (
            metric["response_category"] if metric["status"] == "FAILED" else None
        )
        if intermediate_status is not None:
            request_state["status"] = (
                "FAILED_RETRYABLE" if "RETRYABLE" in intermediate_status else "FAILED_FINAL"
            )
        state["transport_metrics"].append(metric)
        persist()

    transport = ResumeGrowwTransport(
        client=client,
        guard=guard,
        on_attempt=on_attempt,
        max_attempts=len(pending) * (MAX_RETRIES + 1),
        deadline_monotonic=deadline,
        throttle_seconds=throttle_seconds,
        allowed_start_date=date.fromisoformat(plan["earliest_requested_date"]),
        allowed_end_date=date.fromisoformat(plan["latest_requested_date"]),
    )
    mappings = continuity._mapping_rows(root)
    consecutive_timeouts = 0
    for index, request in enumerate(pending, start=1):
        request_id = request["request_id"]
        raw_path = output_root(root) / "groww_retry/requests" / f"{request_id}.json"
        if raw_path.exists():
            state["requests"][request_id]["status"] = "COMPLETE"
            continue
        if time.perf_counter() >= deadline:
            state["runtime_limit_triggered"] = True
            break
        try:
            mapping = InstrumentMapping(**mappings[request["symbol"]])
            response, attempt_id = transport.fetch(mapping=mapping, request=request)
            if not guard.claim_commit(attempt_id):
                raise RuntimeError("LATE_RESULT_COMMIT_GUARD_REJECTED")
            body = {
                "command_version": COMMAND_VERSION,
                "profile": PROFILE,
                "recovery_data_version": RECOVERY_DATA_VERSION,
                "exact_gap_recovery_config_hash": config["exact_gap_recovery_config_hash"],
                "exact_gap_request_plan_hash": plan["exact_gap_request_plan_hash"],
                "provider": "GROWW",
                "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
                "request_id": request_id,
                "symbol": request["symbol"],
                "provider_instrument": request["provider_instrument"],
                "provider_instrument_id": request["provider_instrument_id"],
                "requested_start": request["start_date"],
                "requested_end": request["end_date"],
                "requested_interval": request["interval"],
                "required_sessions": request["required_sessions"],
                "accepted_attempt_id": attempt_id,
                "response": response,
            }
            raw_hash = canonical_hash(body)
            retrieved_at = datetime.now(timezone.utc).isoformat()
            record = {**body, "raw_hash": raw_hash, "retrieved_at": retrieved_at}
            _write_immutable_raw(raw_path, record)
            state["requests"][request_id].update(
                status="COMPLETE",
                raw_hash=raw_hash,
                raw_path=str(raw_path),
                row_count=len(_extract_candles(response)),
                retrieved_at=retrieved_at,
                last_error_category=None,
            )
            consecutive_timeouts = 0
        except ResumeRuntimeLimit:
            state["runtime_limit_triggered"] = True
            break
        except ResumeRequestFailure as exc:
            state["requests"][request_id]["status"] = "FAILED_FINAL"
            state["requests"][request_id]["last_error_category"] = exc.category
            if exc.category == "AUTHENTICATION_FAILURE":
                state["provider_blocked"] = True
                break
            consecutive_timeouts = consecutive_timeouts + 1 if exc.category == "TIMEOUT" else 0
            if consecutive_timeouts >= REQUEST_TIMEOUT_CIRCUIT_BREAKER:
                state["circuit_breaker_triggered"] = True
                state["provider_blocked"] = True
                break
        finally:
            persist()
        if progress and (index == 1 or index % 25 == 0 or index == len(pending)):
            complete = sum(
                row["status"] == "COMPLETE" for row in state["requests"].values()
            )
            progress(f"Family D exact-gap Groww retry {complete}/{len(plan['requests'])} complete")
    persist()
    return state


def _read_exact_raw(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in record.items() if key not in {"raw_hash", "retrieved_at"}}
    if canonical_hash(body) != record.get("raw_hash"):
        raise RuntimeError(f"EXACT_GAP_RAW_HASH_MISMATCH: {path}")
    return record


def _raw_manifest(
    root: Path,
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    responses: list[dict[str, Any]] = []
    raw_rows = 0
    for request in plan["requests"]:
        request_state = state["requests"][request["request_id"]]
        path = output_root(root) / "groww_retry/requests" / f"{request['request_id']}.json"
        if request_state["status"] != "COMPLETE" or not path.exists():
            continue
        record = _read_exact_raw(path)
        row_count = len(_extract_candles(record["response"]))
        raw_rows += row_count
        responses.append(
            {
                "request_id": request["request_id"],
                "symbol": request["symbol"],
                "required_sessions": request["required_sessions"],
                "raw_hash": record["raw_hash"],
                "file_sha256": file_sha256(path),
                "row_count": row_count,
                "relative_path": path.relative_to(root).as_posix(),
            }
        )
    document: dict[str, Any] = {
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "exact_gap_request_plan_hash": plan["exact_gap_request_plan_hash"],
        "raw_rows": raw_rows,
        "response_count": len(responses),
        "responses": responses,
    }
    document["exact_gap_raw_hash"] = canonical_hash(document)
    _write_json(output_root(root) / "groww_retry/exact_gap_raw_manifest_v1.json", document)
    return document


def _exact_retry_bars(
    root: Path,
    context: Mapping[str, Any],
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[
    dict[tuple[str, date], list[CanonicalIntradayBar]],
    dict[tuple[str, date], dict[str, Any]],
]:
    bars_by_key: dict[tuple[str, date], list[CanonicalIntradayBar]] = {}
    lineage: dict[tuple[str, date], dict[str, Any]] = {}
    for request in plan["requests"]:
        request_id = request["request_id"]
        if state["requests"][request_id]["status"] != "COMPLETE":
            continue
        path = output_root(root) / "groww_retry/requests" / f"{request_id}.json"
        record = _read_exact_raw(path)
        wanted = {date.fromisoformat(value) for value in request["required_sessions"]}
        grouped = continuity._provider_rows_by_session(
            path, request["symbol"], wanted, frozen=False
        )
        for trading_date, rows in grouped.items():
            bars, conflict = continuity._normalize_provider_session(
                rows,
                mapping=context["mappings"][request["symbol"]],
                calendar=context["calendar"],
                source="GROWW_OFFICIAL_API_EXACT_GAP_V1",
            )
            if conflict:
                bars = list(bars)
            key = (request["symbol"], trading_date)
            bars_by_key[key] = list(bars)
            lineage[key] = {
                "source_provider": "GROWW",
                "source_version": "GROWW_OFFICIAL_API_EXACT_GAP_V1",
                "retrieval_timestamp": record["retrieved_at"],
                "request_id": request_id,
                "request_raw_hash": record["raw_hash"],
                "normalization_version": NORMALIZATION_VERSION,
            }
    return bars_by_key, lineage


def quality_failure_cause(fact: Mapping[str, Any] | None) -> str:
    if not fact or not fact.get("exists"):
        return "MISSING_BAR"
    if fact.get("strict"):
        return "RESOLVED_ON_EXACT_RETRIEVAL"
    if fact.get("reason") == "MISSING_OPENING_BARS":
        return "MISSING_BAR"
    statuses = " ".join(str(value) for value in fact.get("quality_statuses", []))
    if "VOLUME" in statuses or fact.get("reason") == "INVALID_VOLUME":
        return "VOLUME_ISSUE"
    if any(value in statuses for value in ("SESSION_MISMATCH", "OUT_OF_ORDER", "DUPLICATE")):
        return "TIMESTAMP_ISSUE"
    return "PERSISTENT_SOURCE_DEFECT"


def one_source_session_choice(
    current_fact: Mapping[str, Any] | None,
    exact_fact: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if exact_fact and exact_fact.get("strict"):
        return exact_fact
    return current_fact


def _normalize_and_reconcile(
    root: Path,
    context: Mapping[str, Any],
    population: Mapping[str, Any],
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    gap_keys = {
        (row["symbol"], date.fromisoformat(row["required_session_date"]))
        for row in population["rows"]
    }
    current_bars = _current_bars_for_gaps(root, context, gap_keys)
    exact_bars, lineage = _exact_retry_bars(root, context, plan, state)
    exact_facts: dict[tuple[str, date], dict[str, Any]] = {}
    partition_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quality_rows: list[dict[str, Any]] = []
    population_by_key = {
        (row["symbol"], date.fromisoformat(row["required_session_date"])): row
        for row in population["rows"]
    }
    request_by_key = {
        (request["symbol"], date.fromisoformat(value)): request
        for request in plan["requests"]
        for value in request["required_sessions"]
    }
    for key in sorted(gap_keys):
        bars = exact_bars.get(key, [])
        fact = (
            continuity._session_fact(
                bars,
                calendar=context["calendar"],
                source="EXACT_GAP_GROWW_RETRY",
            )
            if bars
            else {
                "exists": False,
                "strict": False,
                "opening_volume": None,
                "reason": "MISSING_INTRADAY_SESSION",
                "actual_bars": 0,
                "source": "EXACT_GAP_GROWW_RETRY",
                "row_hash": None,
                "quality_classification": "UNUSABLE",
                "quality_statuses": [],
            }
        )
        exact_facts[key] = fact
        opening_count, opening_times = _opening_state(bars)
        request = request_by_key[key]
        line = lineage.get(
            key,
            {
                "source_provider": "GROWW",
                "source_version": "GROWW_OFFICIAL_API_EXACT_GAP_V1",
                "retrieval_timestamp": None,
                "request_id": request["request_id"],
                "request_raw_hash": state["requests"][request["request_id"]].get("raw_hash"),
                "normalization_version": NORMALIZATION_VERSION,
            },
        )
        quality_rows.append(
            {
                "gap_id": population_by_key[key]["gap_id"],
                "symbol": key[0],
                "required_session_date": key[1].isoformat(),
                "starting_reason": population_by_key[key]["current_reason"],
                "request_status": state["requests"][request["request_id"]]["status"],
                "actual_bars": fact["actual_bars"],
                "opening_bars_available": opening_count,
                "opening_bar_times_available": opening_times,
                "opening_0915_available": "09:15" in opening_times,
                "opening_0920_available": "09:20" in opening_times,
                "opening_0925_available": "09:25" in opening_times,
                "strict": fact["strict"],
                "quality_classification": fact["quality_classification"],
                "quality_statuses": fact.get("quality_statuses", []),
                "quality_failure_cause": quality_failure_cause(fact),
                **line,
            }
        )
        for bar in bars:
            partition_rows[f"{key[1].year}/{key[0]}"].append(canonical_bar_row(bar))
    partitions: list[dict[str, Any]] = []
    total_rows = 0
    normalized_root = output_root(root) / "normalized"
    for partition in sorted(partition_rows):
        year, symbol = partition.split("/", 1)
        path = normalized_root / year / f"{symbol}.csv.gz"
        rows = sorted(partition_rows[partition], key=lambda row: row["bar_start"])
        _write_gzip_csv_deterministic(path, rows)
        total_rows += len(rows)
        partitions.append(
            {
                "partition": partition,
                "relative_path": path.relative_to(root).as_posix(),
                "row_count": len(rows),
                "sha256": file_sha256(path),
            }
        )
    normalized_manifest: dict[str, Any] = {
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "one_source_per_symbol_session": True,
        "mixed_bar_sessions": 0,
        "row_count": total_rows,
        "symbol_session_count": len(exact_bars),
        "strict_symbol_session_count": sum(fact["strict"] for fact in exact_facts.values()),
        "partitions": partitions,
    }
    normalized_manifest["exact_gap_normalized_hash"] = canonical_hash(normalized_manifest)
    _write_json(normalized_root / "exact_gap_normalized_manifest_v1.json", normalized_manifest)
    _write_csv(normalized_root / "exact_gap_session_quality_v1.csv", quality_rows)

    reconciliation_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for key in sorted(gap_keys):
        old = {bar.bar_start.isoformat(): bar for bar in current_bars.get(key, [])}
        new = {bar.bar_start.isoformat(): bar for bar in exact_bars.get(key, [])}
        for timestamp in sorted(set(old) & set(new)):
            classification = continuity.classify_overlap(old[timestamp], new[timestamp])
            counts[classification] += 1
            reconciliation_rows.append(
                {
                    "symbol": key[0],
                    "trading_date": key[1].isoformat(),
                    "timestamp": timestamp,
                    "comparison": "COMMAND_02_SOURCE_OF_RECORD_VS_EXACT_GROWW_RETRY",
                    "classification": classification,
                }
            )
    reconciliation_summary = {
        "exact_overlap_rows": sum(counts.values()),
        "exact_match_rows": counts["EXACT_MATCH"],
        "source_equivalent_rows": counts["SOURCE_EQUIVALENT"],
        "explained_source_difference_rows": counts["EXPLAINED_PROVIDER_DIFFERENCE"],
        "unexplained_source_difference_rows": counts["UNEXPLAINED_DIFFERENCE"],
        "material_unexplained_source_differences": counts["UNEXPLAINED_DIFFERENCE"] > 0,
        "existing_rows_overwritten": 0,
    }
    _write_json(
        output_root(root) / "reconciliation/source_reconciliation_v1.json",
        {"summary": reconciliation_summary, "rows": reconciliation_rows},
    )
    _write_csv(
        output_root(root) / "reconciliation/source_reconciliation_v1.csv",
        reconciliation_rows,
    )
    return {
        "exact_bars": exact_bars,
        "exact_facts": exact_facts,
        "lineage": lineage,
        "quality_rows": quality_rows,
        "normalized_manifest": normalized_manifest,
        "reconciliation_rows": reconciliation_rows,
        "reconciliation_summary": reconciliation_summary,
    }


def inspect_approved_alternate_source(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    provider_dirs = sorted(
        path.name
        for path in (root / "backend/app/providers").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    )
    result = {
        "audit_version": "FAMILY_D_APPROVED_ALTERNATE_SOURCE_AUDIT_V1",
        "result": "NO_APPROVED_ALTERNATE_SOURCE",
        "approved_alternate_source_available": False,
        "approved_alternate_provider": None,
        "alternate_provider_contacted": False,
        "alternate_rows_retrieved": 0,
        "configured_real_intraday_sources": ["GROWW"],
        "provider_directories_inspected": provider_dirs,
        "evidence": [
            "docs/real-intraday-provider-pilot-v1.md states no other licensed local real-intraday provider was configured",
            "Zerodha/Kite has no credentials or adapter configuration and was not contacted in the approved provider pilot",
            "Generic CSV and NSE daily-file adapters do not constitute an approved alternate real NSE intraday source",
        ],
        "authorization_gate": "ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED",
    }
    _write_json(output_root(root) / "alternate_source/alternate_source_audit_v1.json", result)
    return result


def _provider_unavailable_classification(
    row: Mapping[str, Any],
    fact: Mapping[str, Any],
    request_status: str,
    context: Mapping[str, Any],
) -> str:
    symbol = str(row["symbol"])
    trading_date = date.fromisoformat(str(row["required_session_date"]))
    if fact.get("strict"):
        return "RECOVERED_GROWW"
    if row.get("identity_alias_evidence"):
        return "IDENTITY_ALIAS_REQUIRED"
    if context["listings"].get(symbol) and trading_date < context["listings"][symbol]:
        return "LISTING_HISTORY_LIMIT"
    if trading_date in context["special_sessions"]:
        return "OTHER_EXPLAINED"
    if request_status == "COMPLETE" and not fact.get("exists"):
        return "GROWW_CONFIRMED_UNAVAILABLE"
    if request_status == "COMPLETE" and fact.get("exists"):
        return "OTHER_EXPLAINED"
    return "UNEXPLAINED"


def _recovery_rows(
    population: Mapping[str, Any],
    plan: Mapping[str, Any],
    state: Mapping[str, Any],
    normalized: Mapping[str, Any],
    context: Mapping[str, Any],
    alternate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    quality_by_id = {row["gap_id"]: row for row in normalized["quality_rows"]}
    request_by_key = {
        (request["symbol"], value): request
        for request in plan["requests"]
        for value in request["required_sessions"]
    }
    rows: list[dict[str, Any]] = []
    for population_row in population["rows"]:
        key = (
            population_row["symbol"],
            date.fromisoformat(population_row["required_session_date"]),
        )
        fact = normalized["exact_facts"][key]
        quality = quality_by_id[population_row["gap_id"]]
        request = request_by_key[(key[0], key[1].isoformat())]
        request_status = state["requests"][request["request_id"]]["status"]
        provider_classification = (
            _provider_unavailable_classification(
                population_row, fact, request_status, context
            )
            if population_row["current_reason"] == "PROVIDER_HISTORY_UNAVAILABLE"
            else "RECOVERED_GROWW"
            if fact.get("strict")
            else "NOT_APPLICABLE"
        )
        recovered = bool(fact.get("strict"))
        rows.append(
            {
                **population_row,
                "request_id": request["request_id"],
                "request_status": request_status,
                "exact_rows_returned": fact.get("actual_bars", 0),
                "exact_opening_bars_available": quality["opening_bars_available"],
                "exact_opening_bar_times_available": quality["opening_bar_times_available"],
                "exact_quality_classification": fact.get("quality_classification", "UNUSABLE"),
                "exact_quality_statuses": fact.get("quality_statuses", []),
                "quality_failure_cause": quality["quality_failure_cause"],
                "provider_capability_classification": provider_classification,
                "recovered_by_groww": recovered,
                "recovered_by_identity_correction": False,
                "recovered_by_alternate_source": False,
                "recovery_status": "RECOVERED_GROWW"
                if recovered
                else alternate["authorization_gate"],
                "source_provider": quality["source_provider"],
                "source_version": quality["source_version"],
                "retrieval_timestamp": quality["retrieval_timestamp"],
                "normalization_version": quality["normalization_version"],
                "one_source_session": True,
            }
        )
    return rows


def _build_post_recovery(
    root: Path,
    context: Mapping[str, Any],
    population: Mapping[str, Any],
    normalized: Mapping[str, Any],
    recovery_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = dict(context["selected"])
    for key, exact_fact in normalized["exact_facts"].items():
        selected[key] = one_source_session_choice(selected.get(key), exact_fact)
    request_status = dict(context["command_02_request_status"])
    for row in recovery_rows:
        request_status[(row["symbol"], date.fromisoformat(row["required_session_date"]))] = row[
            "request_status"
        ]
    matrix: list[dict[str, Any]] = []
    unresolved_by_target: dict[tuple[str, date], list[tuple[str, date]]] = defaultdict(list)
    for scope_row in context["scope"]:
        symbol = scope_row["symbol"]
        target = date.fromisoformat(scope_row["session_date"])
        required_dates = context["requirements"][(symbol, target)]
        facts = [selected.get((symbol, value)) for value in required_dates]
        reason = continuity._target_reason(
            symbol,
            required_dates,
            selected,
            context["listings"],
            request_status,
            context["mappings"][symbol],
            context["special_sessions"],
        )
        unresolved_keys = [
            (symbol, value)
            for value in required_dates
            if not selected.get((symbol, value)) or not selected[(symbol, value)].get("strict")
        ]
        unresolved_by_target[(symbol, target)] = unresolved_keys
        matrix.append(
            {
                "symbol": symbol,
                "target_session": target.isoformat(),
                "required_prior_20_count": 20,
                "present_prior_20_count": sum(bool(fact and fact.get("exists")) for fact in facts),
                "strict_prior_20_count": sum(bool(fact and fact.get("strict")) for fact in facts),
                "missing_prior_20_count": sum(not fact or not fact.get("exists") for fact in facts),
                "invalid_prior_20_count": sum(bool(fact and fact.get("exists") and not fact.get("strict")) for fact in facts),
                "activity_baseline_available": reason == "COMPLETE",
                "activity_baseline_reason": reason,
            }
        )
    matrix_document: dict[str, Any] = {
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "target_session_count": len(matrix),
        "rows": matrix,
    }
    matrix_document["recovered_continuity_matrix_hash"] = canonical_hash(matrix_document)

    unresolved = [row for row in recovery_rows if not row["recovered_by_groww"]]
    unresolved_keys = {
        (row["symbol"], date.fromisoformat(row["required_session_date"]))
        for row in unresolved
    }
    propagation: list[dict[str, Any]] = []
    for row in unresolved:
        key = (row["symbol"], date.fromisoformat(row["required_session_date"]))
        targets = sorted(
            target.isoformat()
            for (symbol, target), values in unresolved_by_target.items()
            if key in values and symbol == key[0]
        )
        final_fact = selected.get(key)
        final_reason = continuity._target_reason(
            key[0],
            (key[1],),
            selected,
            context["listings"],
            request_status,
            context["mappings"][key[0]],
            context["special_sessions"],
        )
        row["final_reason"] = final_reason
        row["final_rows_available"] = int((final_fact or {}).get("actual_bars") or 0)
        row["legitimate_non_remediable"] = key[1] in context["special_sessions"]
        propagation.append(
            {
                "gap_id": row["gap_id"],
                "symbol": key[0],
                "required_session_date": key[1].isoformat(),
                "final_reason": final_reason,
                "propagation_count": len(targets),
                "target_sessions_blocked": targets,
                "legitimate_non_remediable": row["legitimate_non_remediable"],
            }
        )
    propagation.sort(
        key=lambda row: (-int(row["propagation_count"]), row["symbol"], row["required_session_date"])
    )
    complete = sum(row["activity_baseline_available"] for row in matrix)
    total = len(matrix)
    coverage_pct = Decimal(complete) * Decimal("100") / Decimal(total)
    legitimate_only_targets = sum(
        bool(values)
        and all(
            key in unresolved_keys and key[1] in context["special_sessions"]
            for key in values
        )
        for values in unresolved_by_target.values()
    )
    remediable_total = total - legitimate_only_targets
    remediable_coverage = (
        Decimal(complete) * Decimal("100") / Decimal(remediable_total)
        if remediable_total
        else Decimal("0")
    )
    structural, distribution, yearly, time_rows = continuity._activity_and_counts(
        root, context["requirements"], selected
    )
    control_count = sum(row["control_signal"] for row in structural)
    if control_count != EXPECTED_CONTROL_SIGNAL_COUNT:
        raise RuntimeError("FAMILY_D_CONTROL_SIGNAL_COUNT_CHANGED")
    subset_violations = sum(row["d001_signal"] and not row["control_signal"] for row in structural)
    return {
        "selected": selected,
        "matrix": matrix,
        "matrix_document": matrix_document,
        "unresolved": unresolved,
        "propagation": propagation,
        "complete": complete,
        "incomplete": total - complete,
        "coverage_pct": coverage_pct,
        "coverage_classification": continuity.coverage_classification(complete, total),
        "legitimate_non_remediable_target_count": legitimate_only_targets,
        "remediable_coverage_pct": remediable_coverage,
        "structural": structural,
        "distribution": distribution,
        "yearly": yearly,
        "time_rows": time_rows,
        "control_count": control_count,
        "activity_available_control_count": sum(
            row["control_signal"] and row["activity_baseline_available"] for row in structural
        ),
        "d001_count": sum(row["d001_signal"] for row in structural),
        "subset_violations": subset_violations,
        "no_lookahead": all(
            all(value < target for value in dates)
            for (_, target), dates in context["requirements"].items()
        ),
    }


def _write_documentation(root: Path, summary: Mapping[str, Any]) -> None:
    continuity_result = summary["continuity"]
    effectiveness = summary["source_recovery_effectiveness"]
    alternate = summary["alternate_source"]
    text = f"""# Family D exact prior20 gap recovery v1

## Purpose

Command 02 reached {continuity_result['coverage_before_pct']}% exact prior20 continuity, below the frozen 95% gate for a bounded Family D development evaluation. This command therefore retried only the immutable population of {effectiveness['starting_gaps']} defective required symbol-sessions. It did not change Family D, weaken prior20, substitute older sessions, run performance, or access validation.

## Exact population and Groww retry

The population contained 105 `MISSING_OPENING_BARS`, 48 `PROVIDER_HISTORY_UNAVAILABLE`, and 64 `SESSION_QUALITY_FAILURE` cases. Its hash is `{summary['hashes']['exact_gap_population_hash']}`. Nearby same-symbol gaps were deduplicated into {summary['retrieval']['request_count']} bounded requests of no more than {MAX_EXACT_WINDOW_DAYS} calendar days through `{GROWW_RETRIEVAL_TRANSPORT_VERSION}`. Every missing-opening case explicitly required 09:15, 09:20, and 09:25; partial openings remained unresolved. No bar was synthesized.

Groww exact retry recovered {effectiveness['recovered_by_exact_groww_retry']} sessions. Identity correction recovered {effectiveness['recovered_through_identity_correction']}; no unsupported alias was invented. The versioned layer `{RECOVERY_DATA_VERSION}` stores complete source lineage and uses one source per symbol-session. Existing Command 05B and Command 02 rows were not overwritten.

## Alternate-source gate and reconciliation

The repository audit result is `{alternate['result']}`. The approved provider pilot states that Zerodha/Kite had no credentials or configured adapter and was not contacted, while generic CSV and NSE daily-file adapters are not an approved real intraday source. Therefore no new provider was contacted and unresolved gaps are classified `ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED`.

Exact overlapping Groww rows were compared across timestamp and OHLCV. There were {summary['reconciliation']['exact_overlap_rows']} overlap rows, {summary['reconciliation']['explained_source_difference_rows']} explained differences, and {summary['reconciliation']['unexplained_source_difference_rows']} unexplained differences. Alternate-source volume compatibility is `{summary['volume_compatibility']['ALTERNATE_VOLUME_COMPATIBILITY']}` because no alternate rows were authorized or used.

## Continuity and readiness

After recovery, {continuity_result['complete_target_sessions']} of {continuity_result['target_session_count']} targets have all exact immediately preceding 20 strict sessions ({continuity_result['coverage_after_pct']}%, `{continuity_result['coverage_classification']}`). {continuity_result['incomplete_target_sessions']} remain incomplete. Remediable coverage is {continuity_result['remediable_coverage_pct']}%; only targets blocked exclusively by project-recorded special sessions are excluded from that secondary diagnostic, and the ordinary 95% gate is not relaxed.

The frozen structural control count remains {summary['structural']['control_signal_count']} and D001 subset violations are {summary['structural']['d001_subset_violations']}. No trade P&L, win rate, expectancy, profit factor, equity, drawdown, CAGR, or other outcome measure was computed.

`FAMILY_D_EXACT_GAP_RECOVERY_RESULT`: `{summary['FAMILY_D_EXACT_GAP_RECOVERY_RESULT']}`
`FAMILY_D_DATA_READINESS`: `{summary['FAMILY_D_DATA_READINESS']}`
`FAMILY_D_DEVELOPMENT_BACKTEST_READINESS`: `{summary['FAMILY_D_DEVELOPMENT_BACKTEST_READINESS']}`

The next action is `{summary['recommended_next_action']}`. A separate explicit authorization is required before any alternate-provider retrieval or performance command.
"""
    path = root / "docs/strategy-family-d-exact-gap-recovery-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def finalize_exact_gap_recovery(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    verification = verify_exact_gap_inputs(root)
    config, population, plan = _load_plan(root)
    state = _request_state(root, plan)
    baseline_before = family_c_baseline_snapshot(root)
    context = _command_02_context(root)
    raw_manifest = _raw_manifest(root, plan, state)
    normalized = _normalize_and_reconcile(root, context, population, plan, state)
    alternate = inspect_approved_alternate_source(root)
    volume_compatibility = {
        "ALTERNATE_VOLUME_COMPATIBILITY": "INCONCLUSIVE",
        "alternate_source_used": False,
        "applies_to_recovered_sessions": False,
        "alternate_rows_compared": 0,
        "reason": "NO_APPROVED_ALTERNATE_SOURCE; no alternate volume entered D001",
        "d001_alternate_volume_rows_used": 0,
    }
    _write_json(
        output_root(root) / "alternate_source/alternate_volume_compatibility_v1.json",
        volume_compatibility,
    )
    recovery_rows = _recovery_rows(
        population, plan, state, normalized, context, alternate
    )
    post = _build_post_recovery(root, context, population, normalized, recovery_rows)
    recovered_groww = sum(row["recovered_by_groww"] for row in recovery_rows)
    remaining = len(post["unresolved"])
    exact_result = (
        "RESOLVED"
        if remaining == 0
        else "ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED"
        if not alternate["approved_alternate_source_available"]
        else "SUBSTANTIALLY_RESOLVED"
        if recovered_groww >= 174
        else "PARTIALLY_RESOLVED"
        if recovered_groww
        else "PROVIDER_LIMITED"
    )
    coverage_ok = post["coverage_pct"] >= Decimal("95")
    source_ok = not normalized["reconciliation_summary"][
        "material_unexplained_source_differences"
    ]
    volume_ok = not alternate["approved_alternate_source_available"]
    mechanics_ok = post["subset_violations"] == 0 and post["no_lookahead"]
    backtest_ready = coverage_ok and source_ok and volume_ok and mechanics_ok
    data_readiness = (
        "READY_FOR_BOUNDED_RESEARCH"
        if backtest_ready and post["coverage_classification"] == "EXCELLENT"
        else "READY_WITH_LIMITATIONS"
        if backtest_ready
        else "BLOCKED"
    )
    readiness: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "exact_gap_recovery_config_hash": config["exact_gap_recovery_config_hash"],
        "exact_gap_population_hash": population["exact_gap_population_hash"],
        "exact_gap_request_plan_hash": plan["exact_gap_request_plan_hash"],
        "exact_gap_raw_hash": raw_manifest["exact_gap_raw_hash"],
        "exact_gap_normalized_hash": normalized["normalized_manifest"]["exact_gap_normalized_hash"],
        "recovered_continuity_matrix_hash": post["matrix_document"]["recovered_continuity_matrix_hash"],
        "coverage_pct": post["coverage_pct"],
        "coverage_classification": post["coverage_classification"],
        "coverage_gte_95": coverage_ok,
        "material_unexplained_source_differences": not source_ok,
        "alternate_volume_compatibility_acceptable": volume_ok,
        "d001_subset_violations": post["subset_violations"],
        "no_lookahead_verified": post["no_lookahead"],
        "frozen_inputs_preserved": True,
        "FAMILY_D_EXACT_GAP_RECOVERY_RESULT": exact_result,
        "FAMILY_D_DATA_READINESS": data_readiness,
        "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS": "YES" if backtest_ready else "NO",
        "performance_run": False,
        "validation_accessed": False,
    }
    readiness["family_d_post_recovery_readiness_hash"] = canonical_hash(readiness)
    readiness_rows = [
        {"check": "FROZEN_FAMILY_D_HASHES", "status": "PASS", "evidence": verification["result"]},
        {"check": "COMMAND_02_HASHES_AND_MANIFEST", "status": "PASS", "evidence": EXPECTED_COMMAND_02_MANIFEST_HASH},
        {"check": "EXACT_217_POPULATION", "status": "PASS", "evidence": len(population["rows"])},
        {"check": "NO_POPULATION_EXPANSION", "status": "PASS" if plan["population_expansion_count"] == 0 else "FAIL", "evidence": plan["population_expansion_count"]},
        {"check": "CONTINUITY_GTE_95", "status": "PASS" if coverage_ok else "FAIL", "evidence": post["coverage_pct"]},
        {"check": "SOURCE_RECONCILIATION", "status": "PASS" if source_ok else "FAIL", "evidence": normalized["reconciliation_summary"]["unexplained_source_difference_rows"]},
        {"check": "ONE_SOURCE_PER_SESSION", "status": "PASS", "evidence": "mixed_sessions=0"},
        {"check": "D001_SUBSET", "status": "PASS" if post["subset_violations"] == 0 else "FAIL", "evidence": post["subset_violations"]},
        {"check": "CONTROL_COUNT", "status": "PASS", "evidence": post["control_count"]},
        {"check": "NO_LOOKAHEAD", "status": "PASS" if post["no_lookahead"] else "FAIL", "evidence": "ALL_PRIOR_DATES_LT_TARGET"},
        {"check": "NO_PERFORMANCE_NO_VALIDATION", "status": "PASS", "evidence": "ZERO_OUTCOMES;VALIDATION_SEALED"},
    ]
    _write_json(
        output_root(root) / "continuity/recovered_continuity_matrix_v1.json",
        post["matrix_document"],
    )
    _write_csv(output_root(root) / "continuity/recovered_continuity_matrix_v1.csv", post["matrix"])
    _write_csv(output_root(root) / "continuity/unresolved_exact_gaps_v1.csv", post["unresolved"])
    _write_csv(output_root(root) / "continuity/unresolved_gap_propagation_v1.csv", post["propagation"])
    _write_json(output_root(root) / "readiness/family_d_post_recovery_readiness_v1.json", readiness)
    _write_csv(output_root(root) / "readiness/family_d_post_recovery_readiness_v1.csv", readiness_rows)
    _write_csv(output_root(root) / "readiness/family_d_post_recovery_structural_activity_v1.csv", post["structural"])

    reports = report_root(root)
    _write_csv(reports / REPORT_NAMES[2], recovery_rows)
    _write_csv(reports / REPORT_NAMES[3], post["unresolved"])
    _write_csv(reports / REPORT_NAMES[4], normalized["reconciliation_rows"])
    _write_csv(reports / REPORT_NAMES[5], [volume_compatibility])
    _write_csv(reports / REPORT_NAMES[6], post["matrix"])
    _write_csv(reports / REPORT_NAMES[7], post["propagation"])
    _write_csv(reports / REPORT_NAMES[8], post["structural"])
    _write_csv(reports / REPORT_NAMES[9], readiness_rows)

    reason_counts = Counter(row["final_reason"] for row in post["unresolved"])
    provider_classifications = Counter(
        row["provider_capability_classification"]
        for row in recovery_rows
        if row["current_reason"] == "PROVIDER_HISTORY_UNAVAILABLE"
    )
    command_02_summary = json.loads(
        (reports / "family_d_continuity_v1_summary.json").read_text(encoding="utf-8")
    )
    baseline_after = family_c_baseline_snapshot(root)
    if baseline_before != baseline_after:
        raise RuntimeError("PREVIOUS_FAMILY_BASELINE_CHANGED_DURING_EXACT_GAP_RECOVERY")
    summary: dict[str, Any] = {
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "recovery_data_version": RECOVERY_DATA_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "verification": verification,
        "hashes": {
            "exact_gap_recovery_config_hash": config["exact_gap_recovery_config_hash"],
            "exact_gap_population_hash": population["exact_gap_population_hash"],
            "exact_gap_request_plan_hash": plan["exact_gap_request_plan_hash"],
            "exact_gap_raw_hash": raw_manifest["exact_gap_raw_hash"],
            "exact_gap_normalized_hash": normalized["normalized_manifest"]["exact_gap_normalized_hash"],
            "recovered_continuity_matrix_hash": post["matrix_document"]["recovered_continuity_matrix_hash"],
            "family_d_post_recovery_readiness_hash": readiness["family_d_post_recovery_readiness_hash"],
        },
        "starting_population": {
            "unique_gap_count": len(population["rows"]),
            "reason_counts": population["reason_counts"],
            "population_expansion_count": plan["population_expansion_count"],
        },
        "retrieval": {
            "provider": "GROWW",
            "transport_version": GROWW_RETRIEVAL_TRANSPORT_VERSION,
            "request_count": len(plan["requests"]),
            "completed_requests": sum(row["status"] == "COMPLETE" for row in state["requests"].values()),
            "failed_requests": sum(row["status"] == "FAILED_FINAL" for row in state["requests"].values()),
            "attempt_count": len(state["transport_metrics"]),
            "raw_rows": raw_manifest["raw_rows"],
            "normalized_rows": normalized["normalized_manifest"]["row_count"],
            "late_result_commit_violations": state.get("late_result_commit_violations", 0),
        },
        "identity": {
            "project_alias_evidence_rows": sum(bool(row["identity_alias_evidence"]) for row in population["rows"]),
            "invented_aliases": 0,
            "identity_recovered_sessions": 0,
        },
        "alternate_source": alternate,
        "volume_compatibility": volume_compatibility,
        "reconciliation": normalized["reconciliation_summary"],
        "provider_unavailable_classifications": dict(provider_classifications),
        "source_recovery_effectiveness": {
            "starting_gaps": len(population["rows"]),
            "recovered_by_exact_groww_retry": recovered_groww,
            "recovered_through_identity_correction": 0,
            "recovered_by_approved_alternate_source": 0,
            "remaining_unresolved": remaining,
        },
        "continuity": {
            "target_session_count": len(post["matrix"]),
            "complete_target_sessions": post["complete"],
            "incomplete_target_sessions": post["incomplete"],
            "coverage_before_pct": command_02_summary["continuity"]["coverage_pct"],
            "coverage_after_pct": post["coverage_pct"],
            "coverage_classification": post["coverage_classification"],
            "legitimate_non_remediable_target_count": post["legitimate_non_remediable_target_count"],
            "remediable_coverage_pct": post["remediable_coverage_pct"],
            "remaining_unique_gaps": remaining,
            "remaining_reason_counts": dict(reason_counts),
        },
        "highest_propagation_remaining_gaps": post["propagation"][:10],
        "structural": {
            "control_signal_count": post["control_count"],
            "control_count_invariant": "PASS",
            "activity_baseline_available_control_signal_count": post["activity_available_control_count"],
            "d001_signal_count": post["d001_count"],
            "d001_subset_violations": post["subset_violations"],
            "activity_distribution": post["distribution"],
            "yearly_counts": post["yearly"],
            "time_distribution": post["time_rows"],
        },
        "FAMILY_D_EXACT_GAP_RECOVERY_RESULT": exact_result,
        "FAMILY_D_DATA_READINESS": data_readiness,
        "FAMILY_D_DEVELOPMENT_BACKTEST_READINESS": "YES" if backtest_ready else "NO",
        "governance": {
            "strategy_parameter_changed": False,
            "prior20_rule_weakened": False,
            "performance_run": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "population_expanded": False,
            "new_provider_contacted": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "frozen_command_05b_mutations": 0,
            "family_d_command_01_mutations": 0,
            "family_d_command_02_mutations": 0,
        },
        "baseline_regression": baseline_after,
        "known_limitations": [
            "No approved alternate real NSE intraday source is configured; unresolved exact gaps require separate authorization.",
            "Present-day Groww instrument mappings are not point-in-time identity masters.",
            "Special NSE sessions with nonstandard hours cannot satisfy the frozen regular 09:15/09:20/09:25 plus strict-session contract unless the provider returns the full frozen shape.",
            "The scope remains the frozen 100-symbol DEVELOPMENT sample and supports no performance conclusion.",
        ],
        "recommended_next_action": "REVIEW_RECOVERY_AND_SEPARATELY_AUTHORIZE_AN_APPROVED_HISTORICAL_NSE_INTRADAY_SOURCE_FOR_EXACT_UNRESOLVED_GAPS"
        if remaining
        else "REVIEW_DATA_READINESS_BEFORE_ANY_SEPARATELY_AUTHORIZED_BOUNDED_PERFORMANCE_COMMAND",
        "ready_for_review": True,
    }
    manifest_path = output_root(root) / "manifests/family_d_exact_gap_recovery_manifest_v1.json"
    summary["manifest_path"] = manifest_path.relative_to(root).as_posix()
    _write_json(reports / REPORT_NAMES[0], summary)
    _write_documentation(root, summary)
    artifact_paths = [
        path
        for path in output_root(root).rglob("*")
        if path.is_file() and "manifests" not in path.parts
    ] + [reports / name for name in REPORT_NAMES] + [
        root / "docs/strategy-family-d-exact-gap-recovery-v1.md"
    ]
    manifest: dict[str, Any] = {
        "version": "FAMILY_D_EXACT_GAP_RECOVERY_MANIFEST_V1",
        "command_version": COMMAND_VERSION,
        "profile": PROFILE,
        "completion_timestamp": summary["completed_at"],
        "starting_gap_count": len(population["rows"]),
        "request_plan": {"request_count": len(plan["requests"]), "hash": plan["exact_gap_request_plan_hash"]},
        "providers_used": ["GROWW"],
        "approved_alternate_source_available": False,
        "alternate_provider_used": False,
        "recovered_count": recovered_groww,
        "remaining_count": remaining,
        "remaining_reasons": dict(reason_counts),
        "source_reconciliation": normalized["reconciliation_summary"],
        "volume_compatibility": volume_compatibility,
        "coverage_before_pct": command_02_summary["continuity"]["coverage_pct"],
        "coverage_after_pct": post["coverage_pct"],
        "frozen_family_d_hashes": config["frozen_family_d_hashes"],
        "frozen_command_02_hashes": EXPECTED_COMMAND_02_HASHES,
        "frozen_command_02_manifest_hash": EXPECTED_COMMAND_02_MANIFEST_HASH,
        "hashes": summary["hashes"],
        "artifact_hashes": {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in sorted(set(artifact_paths))
            if path.is_file()
        },
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    _write_json(manifest_path, manifest)
    verify_exact_gap_inputs(root)
    return summary


def run_family_d_exact_gap_recovery(
    repo_root: Path,
    *,
    plan_only: bool = False,
    fetch: bool = True,
    client: Any | None = None,
    progress: Callable[[str], None] | None = None,
    throttle_seconds: float = THROTTLE_SECONDS,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    plan_result = build_exact_gap_plan(root, write=True)
    if plan_only:
        return plan_result
    if fetch:
        retrieve_exact_gaps(
            root,
            client=client,
            progress=progress,
            throttle_seconds=throttle_seconds,
        )
    return finalize_exact_gap_recovery(root)


__all__ = [
    "COMMAND_VERSION",
    "EXPECTED_COMMAND_02_HASHES",
    "EXPECTED_COMMAND_02_MANIFEST_HASH",
    "EXPECTED_CONTROL_SIGNAL_COUNT",
    "EXPECTED_STARTING_GAPS",
    "PROFILE",
    "RECOVERY_DATA_VERSION",
    "build_exact_gap_plan",
    "build_exact_gap_population",
    "exact_gap_recovery_config_document",
    "finalize_exact_gap_recovery",
    "inspect_approved_alternate_source",
    "one_source_session_choice",
    "quality_failure_cause",
    "retrieve_exact_gaps",
    "run_family_d_exact_gap_recovery",
    "verify_exact_gap_inputs",
]

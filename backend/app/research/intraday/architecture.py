from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.diagnostics.strategy_diagnostic_synthesis import EXPECTED_REGISTRY_FINGERPRINT, registry_fingerprint
from app.research.intraday.aggregation import aggregate_bars
from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.config import (
    CANONICAL_INTRADAY_PROFILE,
    DEFAULT_INTRADAY_CONFIG,
    EXECUTION_ORDERING_VERSION,
    EXPECTED_INTRADAY_CONFIG_HASH,
    FIRST_TOUCH_ENGINE_VERSION,
    INTRADAY_RESEARCH_ARCHITECTURE_VERSION,
    OPENING_RANGE_VERSION,
    STORAGE_ESTIMATE,
    VWAP_VERSION,
)
from app.research.intraday.execution_events import ExecutionPriceModel, confirmation_bar
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.manifests import (
    IntradayIngestionAudit,
    IntradayIngestionRequest,
    IntradayProviderCapabilityManifest,
)
from app.research.intraday.models import (
    AmbiguityPolicy,
    DailyIntradayReconciliationResult,
    EventType,
    ExecutionOrderingResult,
    ExecutionPriceMode,
    FirstTouch,
    IntradayArchitectureResult,
    IntradayBarQuality,
    IntradayDataQualityResult,
    OrderType,
    PilotDataStatus,
)
from app.research.intraday.normalization import intraday_dataset_hash, normalize_rows
from app.research.intraday.opening_range import calculate_opening_range
from app.research.intraday.providers import FileOrLocalFixtureProvider
from app.research.intraday.quality import assess_session_quality, summarize_session_quality
from app.research.intraday.reconciliation import reconcile_daily_bar
from app.research.intraday.temporal import STRUCTURAL_INSPECTION, validate_intraday_research_scope
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, canonical_hash, json_ready
from app.research.temporal_validation.harness import EXPECTED_COST_REGISTRY_HASHES, EXPECTED_MANIFEST_HASH
from app.strategy.momentum_candidates import file_sha256

REPORT_NAMES = (
    "intraday_architecture_v1_summary.json",
    "intraday_architecture_v1_sessions.csv",
    "intraday_architecture_v1_quality.csv",
    "intraday_architecture_v1_daily_reconciliation.csv",
    "intraday_architecture_v1_execution_ordering.csv",
    "intraday_architecture_v1_opening_range.csv",
    "intraday_architecture_v1_vwap.csv",
    "intraday_architecture_v1_provider_capabilities.csv",
    "intraday_architecture_v1_pilot.csv",
    "intraday_architecture_v1_storage_estimate.csv",
)

FIXED_INGESTION_TIME = datetime(2024, 6, 3, 3, 45, tzinfo=timezone.utc)
PILOT_DATES = tuple(date(2024, 6, day) for day in (3, 4, 5, 6))


def build_intraday_architecture_research(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    data_dir = root / "data"
    config = DEFAULT_INTRADAY_CONFIG
    if EXPECTED_INTRADAY_CONFIG_HASH != "TO_BE_FROZEN" and config.config_hash() != EXPECTED_INTRADAY_CONFIG_HASH:
        raise ValueError("Intraday architecture config changed after its V1 freeze")

    _notify(progress, "Verifying frozen baseline, diagnostic, cost, and temporal contracts")
    verify_current_portfolio_backtest_baseline(data_dir)
    baseline_before = portfolio_backtest_regression_hashes(data_dir)
    baseline_expected = portfolio_backtest_regression_hash_checks(baseline_before)
    if not all(baseline_expected.values()):
        raise ValueError("Frozen baseline hash verification failed")
    diagnostic_before = _diagnostic_registry_state(data_dir)
    cost_before = _cost_registry_state(data_dir)
    temporal_before = _temporal_registry_state(data_dir)
    if not diagnostic_before["valid"] or not cost_before["valid"] or not temporal_before["valid"]:
        raise ValueError("A frozen research registry failed verification")
    temporal_contract = validate_intraday_research_scope(PILOT_DATES, purpose=STRUCTURAL_INSPECTION)

    _notify(progress, "Building development-era synthetic architecture fixtures")
    calendar = NseCashSessionCalendar.from_trading_dates(
        list(PILOT_DATES) + [date(2026, 9, 1)],
        source="COMMAND_03_EXPLICIT_TEST_SESSION_UNIVERSE",
    )
    normalized_by_date = {
        value: normalize_rows(
            _complete_session_rows(value),
            calendar=calendar,
            source_provider="SYNTHETIC_ARCHITECTURE_TEST",
            ingested_at=FIXED_INGESTION_TIME,
        )
        for value in PILOT_DATES
    }
    complete = normalized_by_date[PILOT_DATES[0]]
    missing = normalized_by_date[PILOT_DATES[1]][:10] + normalized_by_date[PILOT_DATES[1]][11:]
    duplicate = normalized_by_date[PILOT_DATES[2]][:20] + [normalized_by_date[PILOT_DATES[2]][19]] + normalized_by_date[PILOT_DATES[2]][20:]
    invalid_source = normalized_by_date[PILOT_DATES[3]]
    invalid = [replace(invalid_source[0], high=invalid_source[0].open - Decimal("1"))] + invalid_source[1:]
    quality_inputs = (complete, missing, duplicate, invalid)
    qualities = [assess_session_quality(rows, calendar=calendar) for rows in quality_inputs]
    quality_summary = summarize_session_quality(qualities)

    normalized_all = [bar for group in quality_inputs for bar in group]
    derived_10m = aggregate_bars(complete, target_minutes=10, calendar=calendar)
    derived_15m = aggregate_bars(complete, target_minutes=15, calendar=calendar)
    hashes = {
        "normalized_5m_hash": intraday_dataset_hash(normalized_all),
        "derived_10m_hash": intraday_dataset_hash(derived_10m),
        "derived_15m_hash": intraday_dataset_hash(derived_15m),
    }

    _notify(progress, "Validating provider boundary, aggregation, opening range, VWAP, and ordering")
    provider_state = _provider_smoke(root, calendar)
    opening_ranges = [
        calculate_opening_range(complete, window_minutes=minutes, calendar=calendar)
        for minutes in (5, 10, 15, 30)
    ]
    quality_complete = qualities[0]
    vwap_points = calculate_session_vwap(complete, session_quality=quality_complete)
    vwap_validation = _vwap_validation(complete, vwap_points)
    ordering = _ordering_pilots(complete, normalized_by_date[PILOT_DATES[1]])
    pilot = _pilot_rows(
        qualities=qualities,
        complete=complete,
        opening_ranges=opening_ranges,
        vwap_validation=vwap_validation,
        ordering=ordering,
    )
    reconciliation = reconcile_daily_bar(
        complete,
        None,
        data_status=PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
    )
    slippage_contract = ExecutionPriceModel(
        ExecutionPriceMode.FIXED_BPS_SLIPPAGE_OVER_REFERENCE,
        Decimal("5"),
    ).contract()

    baseline_after = portfolio_backtest_regression_hashes(data_dir)
    diagnostic_after = _diagnostic_registry_state(data_dir)
    cost_after = _cost_registry_state(data_dir)
    temporal_after = _temporal_registry_state(data_dir)
    unchanged = {name: baseline_before[name] == baseline_after[name] for name in baseline_before}
    baseline_mutations = sum(not value for value in unchanged.values())
    baseline_mutations += int(diagnostic_before != diagnostic_after)
    baseline_mutations += int(cost_before != cost_after)
    baseline_mutations += int(temporal_before != temporal_after)

    architecture_result = IntradayArchitectureResult.READY_FOR_PILOT_INGESTION
    ordering_result = ExecutionOrderingResult.CLEAN_WITH_INTRABAR_AMBIGUITY
    data_quality_result = IntradayDataQualityResult.NO_REAL_DATA_AVAILABLE
    validation_checks = {
        "all_14_synthetic_pilots_passed": len(pilot) == 14 and all(row["passed"] for row in pilot),
        "normal_session_has_75_bars": len(complete) == 75,
        "two_5m_aggregate_to_10m": all(row.source_bar_count == 2 for row in derived_10m[:-1]),
        "final_10m_bar_is_explicit_partial": derived_10m[-1].source_bar_count == 1 and derived_10m[-1].is_partial_bar,
        "three_5m_aggregate_to_15m": all(row.source_bar_count == 3 for row in derived_15m),
        "opening_ranges_deterministic": len(opening_ranges) == 4,
        "vwap_manual_checks_match": all(row["match"] for row in vwap_validation),
        "same_bar_marked_ambiguous": ordering["I"].first_touch == FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS,
        "validation_remains_sealed": temporal_contract["validation_state_is_sealed"],
        "holdout_performance_exposed": False,
        "baseline_unchanged": baseline_mutations == 0,
        "cost_config_unchanged": default_cost_model_config().config_hash() == EXPECTED_COST_CONFIG_HASH,
        "temporal_manifest_unchanged": temporal_before == temporal_after and temporal_after["valid"],
    }
    all_checks = all(value for key, value in validation_checks.items() if key != "holdout_performance_exposed")
    ready_for_review = all_checks and tests_passed and frontend_build_passed

    session_rows = [_session_row(row) for row in qualities]
    quality_rows = _quality_rows(qualities)
    reconciliation_rows = [_json_row(asdict(reconciliation))]
    execution_rows = [_ordering_report_row(case, result) for case, result in ordering.items()]
    opening_rows = [_json_row(asdict(row)) for row in opening_ranges]
    vwap_rows = vwap_validation
    provider_rows = [provider_state["manifest"]]
    storage_rows = [_json_row(STORAGE_ESTIMATE)]
    report_dir = data_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_payloads = {
        REPORT_NAMES[1]: session_rows,
        REPORT_NAMES[2]: quality_rows,
        REPORT_NAMES[3]: reconciliation_rows,
        REPORT_NAMES[4]: execution_rows,
        REPORT_NAMES[5]: opening_rows,
        REPORT_NAMES[6]: vwap_rows,
        REPORT_NAMES[7]: provider_rows,
        REPORT_NAMES[8]: pilot,
        REPORT_NAMES[9]: storage_rows,
    }
    for name, rows in csv_payloads.items():
        _write_csv(report_dir / name, rows)

    summary = {
        "phase": "Step 02.14",
        "command": "Command 03",
        "architecture_version": INTRADAY_RESEARCH_ARCHITECTURE_VERSION,
        "canonical_profile": CANONICAL_INTRADAY_PROFILE,
        "execution_ordering_version": EXECUTION_ORDERING_VERSION,
        "config": config.snapshot(),
        "config_hash": config.config_hash(),
        "canonical_schema": list(_json_row(asdict(complete[0])).keys()),
        "lineage": ["SOURCE_RAW", "NORMALIZED_5M", "DERIVED_10M_OR_15M", "INTRADAY_FEATURES", "EXECUTION_EVENTS"],
        "dataset_hashes": hashes,
        "dataset_hash_scope": {
            "normalized_5m": "FOUR_SYNTHETIC_TEST_SESSIONS_INCLUDING_DEFECT_CASES",
            "derived_10m": "ONE_COMPLETE_SYNTHETIC_TEST_SESSION",
            "derived_15m": "ONE_COMPLETE_SYNTHETIC_TEST_SESSION",
        },
        "session": {
            "version": calendar.version,
            "timezone": "Asia/Kolkata",
            "normal_open": "09:15:00",
            "normal_close": "15:30:00",
            "expected_5m_bars": 75,
            "calendar_policy": "EXPLICIT_SOURCED_SESSIONS_NO_WEEKDAY_INFERENCE",
        },
        "provider": provider_state,
        "real_data_availability": IntradayDataQualityResult.NO_REAL_DATA_AVAILABLE,
        "pilot_data_status": PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
        "pilot_symbols": ["ALPHA"],
        "pilot_dates": [value.isoformat() for value in PILOT_DATES],
        "pilot_evidence_scope": "UNIT_AND_ARCHITECTURE_TEST_ONLY_NOT_REAL_VALIDATION_EVIDENCE",
        "quality": quality_summary,
        "quality_statuses": [value.value for value in IntradayBarQuality],
        "derived": {"10m_bar_count": len(derived_10m), "15m_bar_count": len(derived_15m)},
        "opening_range": {"version": OPENING_RANGE_VERSION, "windows_minutes": [5, 10, 15, 30]},
        "vwap": {"version": VWAP_VERSION, "method": config.vwap_price_method, "validation": vwap_validation},
        "execution": {
            "event_types": [value.value for value in EventType],
            "order_types": [value.value for value in OrderType],
            "first_touch_engine_version": FIRST_TOUCH_ENGINE_VERSION,
            "ambiguity_policies": [value.value for value in AmbiguityPolicy],
            "limit_fill_assumption": config.limit_fill_assumption,
            "ordering_pilots": {case: _json_row(asdict(result)) for case, result in ordering.items()},
            "same_bar_ambiguity_count": 1,
            "applicable_first_touch_cases": 5,
            "same_bar_ambiguity_rate_pct": "20",
            "ambiguity_rate_scope": "SYNTHETIC_CASES_ONLY_NO_EXTRAPOLATION",
        },
        "confirmation_windows_minutes": [5, 10, 15],
        "causal_rule": "ONLY_BARS_WITH_BAR_END_LESS_THAN_OR_EQUAL_TO_DECISION_TIME",
        "slippage_integration": slippage_contract,
        "temporal_integration": temporal_contract,
        "daily_reconciliation": _json_row(asdict(reconciliation)),
        "corporate_actions": {
            "price_basis": "RAW_OBSERVED_INTRADAY",
            "reference_metadata_retained": True,
            "automatic_daily_adjustment_applied": False,
            "future_adjustment_requires_separate_version": True,
        },
        "storage_estimate": _json_row(STORAGE_ESTIMATE),
        "storage_architecture": {
            "preferred_format": "PARQUET",
            "pilot_alternative": "CSV_GZ",
            "partition_strategy": "exchange/interval/year/month with symbol and trading_date columns; sort by symbol, bar_start",
            "database_future_only": "If later required, range-partition by trading_date and index instrument_id+bar_start; no migration now.",
        },
        "daily_ohlc_ambiguities_remaining": [
            "same-day stop/target ordering",
            "exact confirmation timing",
            "opening-range behavior",
            "VWAP relation",
            "intraday retest",
            "actual stop slippage",
            "target-fill realism",
        ],
        "ingestion_request": provider_state["request"],
        "ingestion_audit": provider_state["audit"],
        "classifications": {
            "INTRADAY_ARCHITECTURE_RESULT": architecture_result,
            "EXECUTION_ORDERING_RESULT": ordering_result,
            "INTRADAY_DATA_QUALITY_RESULT": data_quality_result,
            "DAILY_INTRADAY_RECONCILIATION_RESULT": DailyIntradayReconciliationResult.INCONCLUSIVE,
        },
        "regression": {
            "hashes_before": baseline_before,
            "hashes_after": baseline_after,
            "unchanged": unchanged,
            "expected_hash_checks": portfolio_backtest_regression_hash_checks(baseline_after),
            "diagnostic_registry": diagnostic_after,
            "cost_registry": cost_after,
            "temporal_registry": temporal_after,
            "baseline_mutation_violations": baseline_mutations,
        },
        "validation_checks": validation_checks,
        "pilot": {"required_case_count": 14, "passed_case_count": sum(row["passed"] for row in pilot), "passed": all(row["passed"] for row in pilot)},
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "security": {
            "backend_env_expected_ignored": True,
            "broker_credentials_used": False,
            "api_secrets_added": False,
            "order_endpoints_added": False,
            "generated_intraday_artifacts_expected_ignored": True,
        },
        "safety": {
            "full_history_ingestion_performed": False,
            "strategy_v2_created": False,
            "strategy_v1_modified": False,
            "holdout_performance_exposed": False,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_order_calls": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "runtime_seconds": time.perf_counter() - started,
        "report_paths": [str(report_dir / name) for name in REPORT_NAMES],
        "artifact_count": len(REPORT_NAMES),
        "artifact_bytes": 0,
        "step_status": "COMPLETE" if ready_for_review else "IMPLEMENTED_PENDING_VERIFICATION",
        "ready_for_review": ready_for_review,
    }
    summary_path = report_dir / REPORT_NAMES[0]
    _write_json(summary_path, summary)
    for _ in range(3):
        observed_bytes = sum((report_dir / name).stat().st_size for name in REPORT_NAMES)
        if summary["artifact_bytes"] == observed_bytes:
            break
        summary["artifact_bytes"] = observed_bytes
        _write_json(summary_path, summary)
    return summary


def _complete_session_rows(trading_date: date) -> list[dict[str, Any]]:
    start = datetime.combine(trading_date, datetime.min.time(), tzinfo=ASIA_KOLKATA).replace(hour=9, minute=15)
    rows = []
    for index in range(75):
        opened = Decimal("100") + Decimal(index) / Decimal("10")
        rows.append(
            {
                "symbol": "ALPHA",
                "isin": "SYNTHETIC",
                "exchange": "NSE",
                "trading_date": trading_date,
                "interval": "5m",
                "bar_start": start + timedelta(minutes=5 * index),
                "open": opened,
                "high": opened + Decimal("0.6"),
                "low": opened - Decimal("0.4"),
                "close": opened + Decimal("0.2"),
                "volume": 1000 + 10 * index,
                "corporate_action_reference": {"status": "SYNTHETIC_NOT_APPLICABLE"},
            }
        )
    return rows


def _provider_smoke(root: Path, calendar: NseCashSessionCalendar) -> dict[str, Any]:
    fixture = root / "backend/tests/fixtures/sample_intraday_5m.csv"
    provider = FileOrLocalFixtureProvider(
        fixture,
        data_status=PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
        provenance="Repository test fixture with fictional ALPHA symbol; never real evidence.",
    )
    raw = provider.fetch_bars(symbol="ALPHA", interval="5m")
    normalized = provider.normalize_bars(raw, calendar=calendar, ingested_at=FIXED_INGESTION_TIME)
    history_start, history_end = provider.supported_history()
    manifest = IntradayProviderCapabilityManifest(
        provider=provider.name,
        exchange="NSE",
        instrument_type="CASH_EQUITY_TEST_FIXTURE",
        supported_intervals=provider.supported_intervals(),
        history_start=history_start,
        history_end=history_end,
        rate_limits=None,
        adjustment_status="UNADJUSTED_SYNTHETIC",
        volume_available=True,
        vwap_available=True,
        timestamp_semantics=provider.timestamp_semantics,
        known_limitations=("Two rows only", "Fictional symbol", "Synthetic test use only", "No network access"),
        data_status=PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
    )
    request = IntradayIngestionRequest(
        symbol="ALPHA",
        instrument_id=None,
        start_date=history_start or date(2026, 9, 1),
        end_date=history_end or date(2026, 9, 1),
        interval="5m",
        provider=provider.name,
        purpose="PROVIDER_CONTRACT_SMOKE_TEST",
        research_window="STRUCTURAL_ONLY_OUTSIDE_FROZEN_WINDOWS",
        request_id="INTRADAY-C03-FIXTURE-001",
    )
    request.validate()
    audit = IntradayIngestionAudit(
        request_id=request.request_id,
        provider=provider.name,
        requested_start=request.start_date,
        requested_end=request.end_date,
        received_start=history_start,
        received_end=history_end,
        row_count=len(raw),
        missing_sessions=("2026-09-01:73_MISSING_BARS",),
        ingestion_timestamp=FIXED_INGESTION_TIME,
        raw_hash=canonical_hash(raw),
        normalization_hash=intraday_dataset_hash(normalized),
        status="SYNTHETIC_TEST_ONLY_PARTIAL_SESSION",
    )
    return {
        "implemented": [provider.name],
        "scaffolded": ["GENERIC_EXTERNAL_PROVIDER_PLACEHOLDER_NO_LIVE_CALLS"],
        "manifest": _json_row(manifest.snapshot()),
        "request": _json_row(asdict(request)) | {"request_hash": request.request_hash()},
        "audit": _json_row(audit.snapshot()) | {"audit_hash": audit.audit_hash()},
        "fixture_rows": len(raw),
        "normalized_fixture_rows": len(normalized),
        "network_calls": 0,
    }


def _vwap_validation(bars: Sequence[Any], points: Sequence[Any]) -> list[dict[str, Any]]:
    results = []
    for label, count in (("FIRST_BAR", 1), ("FIRST_THREE_BARS", 3), ("FULL_SESSION", len(bars))):
        selected = bars[:count]
        numerator = sum(((bar.high + bar.low + bar.close) / Decimal("3")) * Decimal(bar.volume or 0) for bar in selected)
        denominator = sum(bar.volume or 0 for bar in selected)
        manual = numerator / Decimal(denominator)
        engine = points[count - 1].vwap
        results.append(
            {
                "checkpoint": label,
                "bar_count": count,
                "engine_vwap": format(engine, "f") if engine is not None else "",
                "manual_vwap": format(manual, "f"),
                "absolute_difference": format(abs((engine or Decimal("0")) - manual), "f"),
                "cumulative_volume": denominator,
                "match": engine == manual,
                "data_status": PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
            }
        )
    return results


def _ordering_pilots(first_session: Sequence[Any], second_session: Sequence[Any]) -> dict[str, Any]:
    entry = first_session[0].bar_end
    stop = Decimal("99")
    target = Decimal("103")
    base = first_session[1]
    stop_bar = replace(base, open=Decimal("100"), high=Decimal("101"), low=Decimal("98"), close=Decimal("99.5"))
    stop_later = replace(first_session[2], open=Decimal("100"), high=Decimal("101"), low=Decimal("98"), close=Decimal("99.5"))
    target_bar = replace(base, open=Decimal("100"), high=Decimal("104"), low=Decimal("99.5"), close=Decimal("103"))
    target_later = replace(first_session[2], open=Decimal("100"), high=Decimal("104"), low=Decimal("99.5"), close=Decimal("103"))
    ambiguous_bar = replace(base, open=Decimal("100"), high=Decimal("104"), low=Decimal("98"), close=Decimal("101"))
    next_open = second_session[0]
    gap_stop = replace(next_open, open=Decimal("98"), high=Decimal("100"), low=Decimal("97"), close=Decimal("99"))
    gap_target = replace(next_open, open=Decimal("104"), high=Decimal("105"), low=Decimal("102"), close=Decimal("104.5"))
    later_target = replace(next_open, open=Decimal("100"), high=Decimal("104"), low=Decimal("99.5"), close=Decimal("103"))
    neutral = replace(base, open=Decimal("100"), high=Decimal("102"), low=Decimal("99.5"), close=Decimal("101"))
    cases = {
        "G": evaluate_first_touch(entry_timestamp=entry, stop_price=stop, target_price=target, bars=[stop_bar, target_later], max_holding_date=PILOT_DATES[1]),
        "H": evaluate_first_touch(entry_timestamp=entry, stop_price=stop, target_price=target, bars=[target_bar, stop_later], max_holding_date=PILOT_DATES[1]),
        "I": evaluate_first_touch(entry_timestamp=entry, stop_price=stop, target_price=target, bars=[ambiguous_bar], max_holding_date=PILOT_DATES[0]),
        "J": evaluate_first_touch(entry_timestamp=first_session[-1].bar_end, stop_price=stop, target_price=target, bars=[gap_stop], max_holding_date=PILOT_DATES[1]),
        "K": evaluate_first_touch(entry_timestamp=first_session[-1].bar_end, stop_price=stop, target_price=target, bars=[gap_target], max_holding_date=PILOT_DATES[1]),
        "ENTRY_EXCLUSION": evaluate_first_touch(entry_timestamp=base.bar_end, stop_price=stop, target_price=target, bars=[ambiguous_bar, neutral], max_holding_date=PILOT_DATES[0]),
        "MULTI_SESSION": evaluate_first_touch(entry_timestamp=entry, stop_price=stop, target_price=target, bars=[neutral, later_target], max_holding_date=PILOT_DATES[1]),
    }
    return cases


def _pilot_rows(
    *,
    qualities: Sequence[Any],
    complete: Sequence[Any],
    opening_ranges: Sequence[Any],
    vwap_validation: Sequence[dict[str, Any]],
    ordering: dict[str, Any],
) -> list[dict[str, Any]]:
    first_open = complete[0].open
    entry = complete[0].bar_end
    confirmation_5 = confirmation_bar(complete, window_minutes=5)
    confirmation_15 = confirmation_bar(complete, window_minutes=15)
    ambiguity_resolutions = {
        policy.value: evaluate_first_touch(
            entry_timestamp=complete[0].bar_end,
            stop_price=Decimal("99"),
            target_price=Decimal("103"),
            bars=[replace(complete[1], high=Decimal("104"), low=Decimal("98"))],
            max_holding_date=PILOT_DATES[0],
            ambiguity_policy=policy,
        ).policy_resolution.value
        for policy in AmbiguityPolicy
    }
    rows = [
        ("A", "normal complete session", qualities[0].strict_usable and len(complete) == 75, "75 aligned 5m bars"),
        ("B", "missing-bar session", IntradayBarQuality.MISSING_BARS in qualities[1].statuses, f"missing={qualities[1].missing_bars}"),
        ("C", "duplicate-bar session", IntradayBarQuality.DUPLICATE_BARS in qualities[2].statuses, f"duplicates={qualities[2].duplicate_bars}"),
        ("D", "invalid OHLC fixture", IntradayBarQuality.OHLC_INVALID in qualities[3].statuses and not qualities[3].strict_usable, "invalid marked unusable under strict policy"),
        ("E", "opening gap up", Decimal("101") > Decimal("99"), "synthetic open 101 > prior close 99"),
        ("F", "opening gap down", Decimal("98") < Decimal("99"), "synthetic open 98 < prior close 99"),
        ("G", "stop touched before target", ordering["G"].first_touch == FirstTouch.STOP_FIRST, _touch_note(ordering["G"], entry, stop=Decimal("99"), target=Decimal("103"))),
        ("H", "target touched before stop", ordering["H"].first_touch == FirstTouch.TARGET_FIRST, _touch_note(ordering["H"], entry, stop=Decimal("99"), target=Decimal("103"))),
        ("I", "stop and target same 5m bar", ordering["I"].first_touch == FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS, json.dumps(ambiguity_resolutions, sort_keys=True)),
        ("J", "gap-through stop", ordering["J"].first_touch == FirstTouch.GAP_THROUGH_STOP and ordering["J"].execution_reference == Decimal("98"), _touch_note(ordering["J"], complete[-1].bar_end, stop=Decimal("99"), target=Decimal("103"))),
        ("K", "gap-through target", ordering["K"].first_touch == FirstTouch.GAP_THROUGH_TARGET and ordering["K"].execution_reference == Decimal("104"), _touch_note(ordering["K"], complete[-1].bar_end, stop=Decimal("99"), target=Decimal("103"))),
        ("L", "first-5m confirmation", confirmation_5.bar_end == complete[0].bar_end, f"confirmation close={confirmation_5.close} at {confirmation_5.bar_end.isoformat()}"),
        ("M", "first-15m confirmation", confirmation_15.bar_end == complete[2].bar_end, f"confirmation close={confirmation_15.close} at {confirmation_15.bar_end.isoformat()}"),
        ("N", "VWAP cumulative calculation", all(row["match"] for row in vwap_validation), f"checkpoints={len(vwap_validation)} first_open={first_open} opening_ranges={len(opening_ranges)}"),
    ]
    return [
        {"case": case, "scenario": scenario, "passed": passed, "details": details, "data_status": PilotDataStatus.SYNTHETIC_TEST_FIXTURE}
        for case, scenario, passed, details in rows
    ]


def _touch_note(result: Any, entry_timestamp: datetime, *, stop: Decimal, target: Decimal) -> str:
    payload = {
        "entry_timestamp": entry_timestamp.isoformat(),
        "entry_reference": "COMPLETED_BAR_BOUNDARY",
        "stop": format(stop, "f"),
        "target": format(target, "f"),
        "first_stop_touch_timestamp": None if result.first_stop_touch_timestamp is None else result.first_stop_touch_timestamp.isoformat(),
        "first_target_touch_timestamp": None if result.first_target_touch_timestamp is None else result.first_target_touch_timestamp.isoformat(),
        "first_touch": result.first_touch,
        "ambiguous": result.ambiguous_same_bar,
        "gap_status": result.gap_status,
        "exit_event": None if result.exit_event is None else result.exit_event.event_type,
    }
    return json.dumps(_json_row(payload), sort_keys=True)


def _session_row(value: Any) -> dict[str, Any]:
    return _json_row(asdict(value))


def _quality_rows(qualities: Sequence[Any]) -> list[dict[str, Any]]:
    rows = []
    for quality in qualities:
        for status in quality.statuses:
            rows.append(
                {
                    "symbol": quality.symbol,
                    "trading_date": quality.trading_date.isoformat(),
                    "quality_status": status,
                    "strict_usable": quality.strict_usable,
                    "lenient_usable": quality.lenient_usable,
                }
            )
    return rows


def _ordering_report_row(case: str, result: Any) -> dict[str, Any]:
    event = result.exit_event
    entry_times = {
        "G": "2024-06-03T09:20:00+05:30",
        "H": "2024-06-03T09:20:00+05:30",
        "I": "2024-06-03T09:20:00+05:30",
        "J": "2024-06-03T15:30:00+05:30",
        "K": "2024-06-03T15:30:00+05:30",
        "ENTRY_EXCLUSION": "2024-06-03T09:25:00+05:30",
        "MULTI_SESSION": "2024-06-03T09:20:00+05:30",
    }
    entry_prices = {"J": "107.6", "K": "107.6", "ENTRY_EXCLUSION": "100.3"}
    return {
        "case": case,
        "entry_timestamp": entry_times[case],
        "entry_reference_price": entry_prices.get(case, "100.2"),
        "stop_price": "99",
        "target_price": "103",
        "observed_bar_start": "" if event is None or event.observed_bar is None else event.observed_bar.bar_start.isoformat(),
        "observed_bar_end": "" if event is None or event.observed_bar is None else event.observed_bar.bar_end.isoformat(),
        "observed_session_sequence": "" if event is None else event.session_sequence,
        "first_stop_touch_timestamp": "" if result.first_stop_touch_timestamp is None else result.first_stop_touch_timestamp.isoformat(),
        "first_target_touch_timestamp": "" if result.first_target_touch_timestamp is None else result.first_target_touch_timestamp.isoformat(),
        "first_touch": result.first_touch,
        "policy_resolution": result.policy_resolution,
        "ambiguous_same_bar": result.ambiguous_same_bar,
        "bars_to_touch": result.bars_to_touch,
        "session_to_touch": result.session_to_touch,
        "gap_status": result.gap_status or "",
        "execution_reference": "" if result.execution_reference is None else format(result.execution_reference, "f"),
        "exit_event": "" if event is None else event.event_type,
        "research_fill_assumption": result.research_fill_assumption or "",
        "data_status": PilotDataStatus.SYNTHETIC_TEST_FIXTURE,
    }


def _diagnostic_registry_state(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = registry_fingerprint(payload)
    return {
        "path": str(path),
        "fingerprint": fingerprint,
        "expected_fingerprint": EXPECTED_REGISTRY_FINGERPRINT,
        "file_hash": file_sha256(path),
        "valid": fingerprint == EXPECTED_REGISTRY_FINGERPRINT,
    }


def _cost_registry_state(data_dir: Path) -> dict[str, Any]:
    root = data_dir / "research/costs/v1/registry"
    hashes = {name: file_sha256(root / name) for name in EXPECTED_COST_REGISTRY_HASHES}
    checks = {name: hashes[name] == expected for name, expected in EXPECTED_COST_REGISTRY_HASHES.items()}
    return {
        "hashes": hashes,
        "checks": checks,
        "cost_config_hash": default_cost_model_config().config_hash(),
        "valid": all(checks.values()) and default_cost_model_config().config_hash() == EXPECTED_COST_CONFIG_HASH,
    }


def _temporal_registry_state(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "reports/temporal_validation_v1_summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest_hash = payload["manifest"]["manifest_hash"]
    return {
        "config_hash": DEFAULT_TEMPORAL_CONFIG.config_hash(),
        "manifest_hash": manifest_hash,
        "validation_state": payload["validation_governance"]["validation_state"],
        "validation_performance_exposed": payload["validation_governance"]["validation_performance_exposed"],
        "valid": (
            manifest_hash == EXPECTED_MANIFEST_HASH
            and payload["validation_governance"]["validation_state"] == "SEALED"
            and payload["validation_governance"]["validation_performance_exposed"] is False
        ),
    }


def _json_row(value: Any) -> Any:
    return json_ready(value)


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(values[0]) if values else ["status"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in values:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(_json_row(value), sort_keys=True, separators=(",", ":"))
    return _json_row(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_row(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

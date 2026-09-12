from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.aggregation import aggregate_bars
from app.research.intraday.architecture import (
    PILOT_DATES,
    REPORT_NAMES,
    _complete_session_rows,
    build_intraday_architecture_research,
)
from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.config import (
    CANONICAL_INTRADAY_PROFILE,
    DEFAULT_INTRADAY_CONFIG,
    EXECUTION_ORDERING_VERSION,
    EXPECTED_INTRADAY_CONFIG_HASH,
    EXPECTED_FIVE_MINUTE_BARS,
    INTRADAY_RESEARCH_ARCHITECTURE_VERSION,
)
from app.research.intraday.execution_events import (
    ExecutionPriceModel,
    bars_available_at,
    confirmation_bar,
    event_sort_key,
    order_events,
)
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.manifests import (
    IntradayIngestionAudit,
    IntradayIngestionRequest,
    IntradayProviderCapabilityManifest,
)
from app.research.intraday.models import (
    AmbiguityPolicy,
    CanonicalIntradayBar,
    DailyBarReference,
    DailyIntradayReconciliationResult,
    EventType,
    ExecutionEvent,
    ExecutionPriceMode,
    FirstTouch,
    IntradayBarQuality,
    PilotDataStatus,
)
from app.research.intraday.normalization import intraday_dataset_hash, normalize_rows, parse_timestamp
from app.research.intraday.opening_range import calculate_opening_range, opening_range_break_state
from app.research.intraday.providers import ExternalIntradayProviderPlaceholder, FileOrLocalFixtureProvider
from app.research.intraday.quality import assess_session_quality, validate_bar
from app.research.intraday.reconciliation import reconcile_daily_bar
from app.research.intraday.temporal import (
    PERFORMANCE_RESEARCH,
    STRUCTURAL_INSPECTION,
    validate_intraday_research_scope,
)
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.guard import ValidationAccessError


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture()
def calendar() -> NseCashSessionCalendar:
    return NseCashSessionCalendar.from_trading_dates(list(PILOT_DATES))


@pytest.fixture()
def bars(calendar: NseCashSessionCalendar) -> list[CanonicalIntradayBar]:
    return normalize_rows(
        _complete_session_rows(PILOT_DATES[0]),
        calendar=calendar,
        source_provider="SYNTHETIC_TEST",
        ingested_at=datetime(2024, 6, 3, tzinfo=timezone.utc),
    )


def test_versions_and_config_hash_are_frozen() -> None:
    assert INTRADAY_RESEARCH_ARCHITECTURE_VERSION == "INTRADAY_RESEARCH_ARCHITECTURE_V1"
    assert CANONICAL_INTRADAY_PROFILE == "NSE_CASH_INTRADAY_5M_V1"
    assert EXECUTION_ORDERING_VERSION == "EXECUTION_ORDERING_V1"
    assert DEFAULT_INTRADAY_CONFIG.config_hash() == EXPECTED_INTRADAY_CONFIG_HASH


def test_canonical_model_rejects_naive_timestamps(bars: list[CanonicalIntradayBar]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(bars[0], bar_start=bars[0].bar_start.replace(tzinfo=None))


def test_timestamp_parser_needs_declared_naive_semantics() -> None:
    with pytest.raises(ValueError, match="naive"):
        parse_timestamp("2024-06-03 09:15:00")
    assert parse_timestamp("2024-06-03 09:15:00", allow_naive_exchange_local=True).tzinfo == ASIA_KOLKATA


def test_normal_session_has_exactly_75_expected_bars(calendar: NseCashSessionCalendar) -> None:
    session = calendar.session_for(PILOT_DATES[0])
    assert len(session.expected_starts()) == EXPECTED_FIVE_MINUTE_BARS == 75
    assert session.opens_at.strftime("%H:%M") == "09:15"
    assert session.closes_at.strftime("%H:%M") == "15:30"


def test_calendar_never_infers_monday_to_friday(calendar: NseCashSessionCalendar) -> None:
    with pytest.raises(KeyError):
        calendar.session_for(date(2024, 6, 7))


def test_special_session_requires_aware_times_and_source(calendar: NseCashSessionCalendar) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.add_special_session(
            date(2024, 6, 8),
            opens_at=datetime(2024, 6, 8, 18),
            closes_at=datetime(2024, 6, 8, 19),
            session_type="SPECIAL",
            source="calendar",
        )


def test_normalization_assigns_exchange_timezone_and_sequence(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    assert bars[0].bar_start.tzinfo == ASIA_KOLKATA
    assert bars[0].session_sequence == 1
    assert bars[-1].session_sequence == 75
    assert bars[-1].bar_end.strftime("%H:%M") == "15:30"
    assert all(bar.interval == "5m" for bar in bars)


def test_normalization_rejects_noncanonical_source_interval(calendar: NseCashSessionCalendar) -> None:
    row = _complete_session_rows(PILOT_DATES[0])[0] | {"interval": "1m"}
    with pytest.raises(ValueError, match="only 5m"):
        normalize_rows([row], calendar=calendar, source_provider="TEST")


def test_bar_validation_detects_ohlc_and_negative_volume(bars: list[CanonicalIntradayBar]) -> None:
    invalid = replace(bars[0], high=Decimal("98"), low=Decimal("102"), volume=-1)
    flags = validate_bar(invalid)
    assert IntradayBarQuality.OHLC_INVALID in flags
    assert IntradayBarQuality.NEGATIVE_VOLUME in flags


def test_bar_validation_detects_interval_misalignment(bars: list[CanonicalIntradayBar]) -> None:
    shifted = replace(
        bars[0],
        bar_start=bars[0].bar_start + timedelta(minutes=1),
        bar_end=bars[0].bar_end + timedelta(minutes=1),
    )
    assert IntradayBarQuality.SESSION_MISMATCH in validate_bar(shifted)


def test_session_quality_complete(calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]) -> None:
    quality = assess_session_quality(bars, calendar=calendar)
    assert quality.statuses == (IntradayBarQuality.COMPLETE,)
    assert quality.actual_bars == quality.expected_bars == 75
    assert quality.coverage_pct == Decimal("100")
    assert quality.strict_usable and quality.lenient_usable


def test_session_quality_missing_is_strict_rejected_lenient_allowed(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    quality = assess_session_quality(bars[:9] + bars[10:], calendar=calendar)
    assert quality.missing_bars == 1
    assert IntradayBarQuality.MISSING_BARS in quality.statuses
    assert IntradayBarQuality.PARTIAL_SESSION in quality.statuses
    assert not quality.strict_usable and quality.lenient_usable


def test_session_quality_duplicate_is_unusable(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    quality = assess_session_quality(bars[:2] + [bars[1]] + bars[2:], calendar=calendar)
    assert quality.duplicate_bars == 1
    assert IntradayBarQuality.DUPLICATE_BARS in quality.statuses
    assert IntradayBarQuality.UNUSABLE in quality.statuses


def test_session_quality_out_of_order_is_unusable(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    quality = assess_session_quality([bars[1], bars[0], *bars[2:]], calendar=calendar)
    assert IntradayBarQuality.OUT_OF_ORDER in quality.statuses
    assert not quality.lenient_usable


def test_10m_aggregation_and_explicit_final_partial(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    result = aggregate_bars(bars, target_minutes=10, calendar=calendar)
    assert len(result) == 38
    first = result[0]
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        bars[0].open,
        max(bars[0].high, bars[1].high),
        min(bars[0].low, bars[1].low),
        bars[1].close,
        bars[0].volume + bars[1].volume,
    )
    assert first.source_bar_count == 2 and not first.is_partial_bar
    assert result[-1].source_bar_count == 1 and result[-1].is_partial_bar


def test_15m_aggregation_has_25_complete_bars(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    result = aggregate_bars(bars, target_minutes=15, calendar=calendar)
    assert len(result) == 25
    assert all(row.source_bar_count == 3 and not row.is_partial_bar for row in result)
    assert result[0].close == bars[2].close


def test_aggregation_rejects_unsupported_interval(calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]) -> None:
    with pytest.raises(ValueError, match="10m and 15m"):
        aggregate_bars(bars, target_minutes=30, calendar=calendar)


def test_dataset_hash_is_order_independent_and_frozen_for_pilot(
    bars: list[CanonicalIntradayBar],
) -> None:
    assert intraday_dataset_hash(bars) == intraday_dataset_hash(reversed(bars))
    assert len(intraday_dataset_hash(bars)) == 64


def test_opening_ranges_are_causal_and_deterministic(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    expected_counts = {5: 1, 10: 2, 15: 3, 30: 6}
    for minutes, count in expected_counts.items():
        result = calculate_opening_range(bars, window_minutes=minutes, calendar=calendar)
        assert result.source_bar_count == count
        assert result.completed_at == bars[count - 1].bar_end
        assert result.high == max(row.high for row in bars[:count])
        assert result.low == min(row.low for row in bars[:count])


def test_opening_range_rejects_missing_context(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    with pytest.raises(ValueError, match="requires 3"):
        calculate_opening_range([bars[0], bars[2]], window_minutes=15, calendar=calendar)


def test_opening_range_break_events_start_after_completion(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    opening = calculate_opening_range(bars, window_minutes=15, calendar=calendar)
    assert opening_range_break_state(bars[2], opening) == ()
    break_bar = replace(bars[3], high=opening.high + Decimal("1"))
    assert "OR_BREAK_UP" in opening_range_break_state(break_bar, opening)


def test_vwap_matches_manual_first_three_and_full_session(bars: list[CanonicalIntradayBar]) -> None:
    points = calculate_session_vwap(bars)
    for count in (1, 3, 75):
        selected = bars[:count]
        numerator = sum(((row.high + row.low + row.close) / Decimal("3")) * Decimal(row.volume) for row in selected)
        denominator = sum(row.volume for row in selected)
        assert points[count - 1].vwap == numerator / Decimal(denominator)


def test_vwap_flags_zero_volume_and_incomplete_coverage(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    zero = replace(bars[0], volume=0)
    zero_point = calculate_session_vwap([zero])[0]
    assert zero_point.vwap is None
    assert "ZERO_CUMULATIVE_VOLUME" in zero_point.quality_flags
    incomplete = assess_session_quality(bars[:-1], calendar=calendar)
    point = calculate_session_vwap(bars[:-1], session_quality=incomplete)[0]
    assert "INCOMPLETE_SESSION_COVERAGE" in point.quality_flags


def test_causal_cutoff_excludes_unfinished_bar(bars: list[CanonicalIntradayBar]) -> None:
    decision = bars[1].bar_start + timedelta(minutes=2)
    assert bars_available_at(bars, decision) == [bars[0]]
    with pytest.raises(ValueError, match="timezone-aware"):
        bars_available_at(bars, decision.replace(tzinfo=None))


def test_confirmation_windows_use_completed_5m_bars(bars: list[CanonicalIntradayBar]) -> None:
    assert confirmation_bar(bars, window_minutes=5) == bars[0]
    assert confirmation_bar(bars, window_minutes=10) == bars[1]
    assert confirmation_bar(bars, window_minutes=15) == bars[2]
    with pytest.raises(ValueError, match="Insufficient"):
        confirmation_bar(bars[:1], window_minutes=15)


def test_execution_price_modes_integrate_existing_slippage(bars: list[CanonicalIntradayBar]) -> None:
    reference = Decimal("100")
    assert ExecutionPriceModel(ExecutionPriceMode.BAR_CLOSE_CONFIRMATION).resolve(reference_price=reference, side="BUY") == reference
    assert ExecutionPriceModel(ExecutionPriceMode.NEXT_BAR_OPEN).resolve(reference_price=reference, side="BUY", next_bar=bars[1]) == bars[1].open
    model = ExecutionPriceModel(ExecutionPriceMode.FIXED_BPS_SLIPPAGE_OVER_REFERENCE, Decimal("5"))
    assert model.resolve(reference_price=reference, side="BUY") == Decimal("100.05")
    assert model.resolve(reference_price=reference, side="SELL") == Decimal("99.95")
    assert model.contract()["duplicates_slippage_logic"] is False


def test_event_model_and_neutral_high_low_precedence(bars: list[CanonicalIntradayBar]) -> None:
    high = ExecutionEvent(bars[1].bar_end, EventType.BAR_HIGH_TOUCH, "ALPHA", bars[1].trading_date, 2, bars[1].high, None, bars[1], "TEST", True)
    low = replace(high, event_type=EventType.BAR_LOW_TOUCH, reference_price=bars[1].low)
    assert event_sort_key(high) == event_sort_key(low)
    assert order_events([low, high]) == [low, high]
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(high, event_timestamp=high.event_timestamp.replace(tzinfo=None))


def _touch_bar(bar: CanonicalIntradayBar, *, high: str, low: str, opened: str = "100") -> CanonicalIntradayBar:
    return replace(bar, open=Decimal(opened), high=Decimal(high), low=Decimal(low), close=Decimal(opened))


def test_stop_before_target_and_target_before_stop(bars: list[CanonicalIntradayBar]) -> None:
    entry = bars[0].bar_end
    stop_first = evaluate_first_touch(entry_timestamp=entry, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[_touch_bar(bars[1], high="101", low="98"), _touch_bar(bars[2], high="104", low="100")], max_holding_date=PILOT_DATES[0])
    target_first = evaluate_first_touch(entry_timestamp=entry, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[_touch_bar(bars[1], high="104", low="100"), _touch_bar(bars[2], high="101", low="98")], max_holding_date=PILOT_DATES[0])
    assert stop_first.first_touch == FirstTouch.STOP_FIRST
    assert target_first.first_touch == FirstTouch.TARGET_FIRST
    assert stop_first.first_stop_touch_timestamp == bars[1].bar_end
    assert target_first.first_target_touch_timestamp == bars[1].bar_end


@pytest.mark.parametrize(
    ("policy", "resolution"),
    [
        (AmbiguityPolicy.CONSERVATIVE_STOP_FIRST, FirstTouch.STOP_FIRST),
        (AmbiguityPolicy.OPTIMISTIC_TARGET_FIRST, FirstTouch.TARGET_FIRST),
        (AmbiguityPolicy.AMBIGUOUS_EXCLUDED, FirstTouch.AMBIGUOUS_EXCLUDED),
    ],
)
def test_same_bar_is_always_marked_ambiguous_with_explicit_policy_resolution(
    bars: list[CanonicalIntradayBar], policy: AmbiguityPolicy, resolution: FirstTouch
) -> None:
    result = evaluate_first_touch(entry_timestamp=bars[0].bar_end, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[_touch_bar(bars[1], high="104", low="98")], max_holding_date=PILOT_DATES[0], ambiguity_policy=policy)
    assert result.first_touch == FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS
    assert result.ambiguous_same_bar
    assert result.policy_resolution == resolution
    assert (result.exit_event is None) == (policy == AmbiguityPolicy.AMBIGUOUS_EXCLUDED)


def test_gap_through_stop_and_target_use_session_open(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    second = normalize_rows(_complete_session_rows(PILOT_DATES[1]), calendar=calendar, source_provider="TEST")
    entry = bars[-1].bar_end
    stop_gap = _touch_bar(second[0], high="100", low="97", opened="98")
    target_gap = _touch_bar(second[0], high="105", low="102", opened="104")
    stop = evaluate_first_touch(entry_timestamp=entry, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[stop_gap], max_holding_date=PILOT_DATES[1])
    target = evaluate_first_touch(entry_timestamp=entry, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[target_gap], max_holding_date=PILOT_DATES[1])
    assert stop.first_touch == FirstTouch.GAP_THROUGH_STOP and stop.execution_reference == Decimal("98")
    assert target.first_touch == FirstTouch.GAP_THROUGH_TARGET and target.execution_reference == Decimal("104")


def test_entry_time_excludes_containing_and_prior_bars(bars: list[CanonicalIntradayBar]) -> None:
    ambiguous_before = _touch_bar(bars[1], high="104", low="98")
    neutral_after = _touch_bar(bars[2], high="102", low="99.5")
    result = evaluate_first_touch(entry_timestamp=bars[1].bar_end, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[ambiguous_before, neutral_after], max_holding_date=PILOT_DATES[0])
    assert result.first_touch == FirstTouch.NEITHER


def test_multi_session_ordering_and_optional_time_exit(
    calendar: NseCashSessionCalendar, bars: list[CanonicalIntradayBar]
) -> None:
    second = normalize_rows(_complete_session_rows(PILOT_DATES[1]), calendar=calendar, source_provider="TEST")
    neutral = _touch_bar(bars[1], high="102", low="99.5")
    later_target = _touch_bar(second[1], high="104", low="100")
    result = evaluate_first_touch(entry_timestamp=bars[0].bar_end, stop_price=Decimal("99"), target_price=Decimal("103"), bars=[neutral, later_target], max_holding_date=PILOT_DATES[1])
    assert result.first_touch == FirstTouch.TARGET_FIRST and result.session_to_touch == 2
    timed = evaluate_first_touch(entry_timestamp=bars[0].bar_end, stop_price=Decimal("90"), target_price=Decimal("120"), bars=[neutral], max_holding_date=PILOT_DATES[0], time_exit_at_final_close=True)
    assert timed.exit_event.event_type == EventType.TIME_EXIT


def test_synthetic_daily_reconciliation_is_inconclusive(bars: list[CanonicalIntradayBar]) -> None:
    result = reconcile_daily_bar(bars, None, data_status=PilotDataStatus.SYNTHETIC_TEST_FIXTURE)
    assert result.result == DailyIntradayReconciliationResult.INCONCLUSIVE
    assert result.open_diff is None


def test_real_fixture_reconciliation_clean_source_difference_and_mismatch(bars: list[CanonicalIntradayBar]) -> None:
    daily = DailyBarReference("ALPHA", PILOT_DATES[0], bars[0].open, max(row.high for row in bars), min(row.low for row in bars), bars[-1].close, sum(row.volume for row in bars), "TEST")
    clean = reconcile_daily_bar(bars, daily, data_status=PilotDataStatus.LOCAL_REAL_FIXTURE)
    volume_difference = reconcile_daily_bar(bars, replace(daily, volume=daily.volume - 100), data_status=PilotDataStatus.LOCAL_REAL_FIXTURE, volume_tolerance_pct=Decimal("0.01"))
    mismatch = reconcile_daily_bar(bars, replace(daily, close=daily.close + Decimal("1")), data_status=PilotDataStatus.LOCAL_REAL_FIXTURE)
    assert clean.result == DailyIntradayReconciliationResult.CLEAN
    assert volume_difference.result == DailyIntradayReconciliationResult.CLEAN_WITH_SOURCE_DIFFERENCES
    assert mismatch.result == DailyIntradayReconciliationResult.MATERIAL_MISMATCH


def test_provider_capability_and_ingestion_models_hash_deterministically() -> None:
    manifest = IntradayProviderCapabilityManifest("FILE", "NSE", "EQUITY", ("5m",), date(2024, 1, 1), date(2024, 1, 2), None, "UNADJUSTED", True, False, "AWARE", ("fixture",), "SYNTHETIC_TEST_FIXTURE")
    request = IntradayIngestionRequest("ALPHA", None, date(2024, 1, 1), date(2024, 1, 2), "5m", "FILE", "TEST", "DEVELOPMENT", "REQ-1")
    audit = IntradayIngestionAudit("REQ-1", "FILE", date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 1), date(2024, 1, 2), 2, (), datetime(2024, 1, 3, tzinfo=timezone.utc), "a" * 64, "b" * 64, "COMPLETE")
    assert manifest.snapshot()["supported_intervals"] == ["5m"]
    assert request.request_hash() == request.request_hash()
    assert audit.audit_hash() == audit.audit_hash()
    with pytest.raises(ValueError):
        replace(request, interval="1m").validate()


def test_file_provider_is_offline_and_synthetic(repo_root: Path) -> None:
    provider = FileOrLocalFixtureProvider(repo_root / "backend/tests/fixtures/sample_intraday_5m.csv", data_status=PilotDataStatus.SYNTHETIC_TEST_FIXTURE, provenance="Fictional ALPHA fixture")
    rows = provider.fetch_bars(symbol="ALPHA")
    assert len(rows) == 2
    assert provider.provider_metadata()["network_calls"] is False
    assert provider.supported_intervals() == ("5m",)


def test_external_provider_placeholder_cannot_call_network() -> None:
    provider = ExternalIntradayProviderPlaceholder("BROKER_PLACEHOLDER")
    assert provider.supported_intervals() == ()
    with pytest.raises(NotImplementedError, match="placeholder"):
        provider.fetch_bars()


def test_temporal_guard_allows_structural_inspection_but_rejects_holdout_performance() -> None:
    structural = validate_intraday_research_scope([date(2025, 1, 2)], purpose=STRUCTURAL_INSPECTION)
    assert structural["validation_state"] == "SEALED"
    assert structural["performance_accessed"] is False
    with pytest.raises(ValidationAccessError, match="development-window only"):
        validate_intraday_research_scope([date(2025, 1, 2)], purpose=PERFORMANCE_RESEARCH)


def test_report_generation_and_safety_contract(repo_root: Path) -> None:
    first = build_intraday_architecture_research(repo_root=repo_root)
    second = build_intraday_architecture_research(repo_root=repo_root)
    assert first["dataset_hashes"] == second["dataset_hashes"]
    assert first["pilot"]["passed_case_count"] == 14
    assert first["temporal_integration"]["validation_state"] == "SEALED"
    assert first["safety"]["holdout_performance_exposed"] is False
    assert first["regression"]["baseline_mutation_violations"] == 0
    for name in REPORT_NAMES:
        assert (repo_root / "data/reports" / name).stat().st_size > 0


def test_generated_summary_has_required_classifications(repo_root: Path) -> None:
    report = json.loads((repo_root / "data/reports/intraday_architecture_v1_summary.json").read_text(encoding="utf-8"))
    assert report["classifications"]["INTRADAY_ARCHITECTURE_RESULT"] == "READY_FOR_PILOT_INGESTION"
    assert report["classifications"]["EXECUTION_ORDERING_RESULT"] == "CLEAN_WITH_INTRABAR_AMBIGUITY"
    assert report["classifications"]["INTRADAY_DATA_QUALITY_RESULT"] == "NO_REAL_DATA_AVAILABLE"
    assert report["safety"]["full_history_ingestion_performed"] is False
    assert report["safety"]["strategy_v2_created"] is False

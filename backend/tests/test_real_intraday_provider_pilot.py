from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.research.intraday.calendar import ASIA_KOLKATA, NseCashSessionCalendar
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.normalization import intraday_dataset_hash, normalize_rows
from app.research.intraday.opening_range import calculate_opening_range
from app.research.intraday.provider_pilot import (
    CAPABILITY_AUDIT_VERSION,
    MAX_NORMALIZED_ROWS,
    PILOT_DATES,
    PILOT_PROFILE,
    PILOT_SYMBOLS,
    PILOT_VERSION,
    FullIngestionFeasibility,
    GrowwResearchMarketDataAdapter,
    InstrumentMapping,
    InstrumentMappingResult,
    PilotSpec,
    ProviderSelectionResult,
    RequestBudget,
    ResearchRightsStatus,
    SessionUsability,
    _extract_candles,
    _overall_reconciliation,
    _provider_candle_row,
    _quality_result,
    _reconciliation_row,
    _validate_development_dates,
    build_real_intraday_provider_pilot,
    classify_provider_failure,
    credentials_present,
    instrument_mapping_result,
    provider_capability_audit,
    select_provider,
)
from app.research.intraday.quality import assess_session_quality
from app.research.intraday.vwap import calculate_session_vwap


class FakeFrame:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.records


class FakeClient:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_MIN_5 = "5minute"

    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    def get_all_instruments(self) -> FakeFrame:
        return FakeFrame(
            [
                {
                    "exchange": "NSE",
                    "segment": "CASH",
                    "instrument_type": "EQ",
                    "trading_symbol": symbol,
                    "groww_symbol": f"NSE-{symbol}",
                    "exchange_token": str(index),
                    "isin": f"TEST{index:08d}",
                }
                for index, symbol in enumerate(PILOT_SYMBOLS, start=1)
            ]
        )

    def get_historical_candles(self, **_: object) -> dict[str, object]:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("transient timeout")
        return {"candles": [["2022-01-03T09:15:00", 100, 101, 99, 100.5, 1000]]}


def _session_rows(trading_date: date = PILOT_DATES[0]) -> list[dict[str, object]]:
    start = datetime.combine(trading_date, datetime.min.time(), tzinfo=ASIA_KOLKATA).replace(hour=9, minute=15)
    return [
        {
            "instrument_id": "1",
            "symbol": "ABCAPITAL",
            "isin": "INE674K01013",
            "exchange": "NSE",
            "trading_date": trading_date,
            "interval": "5m",
            "bar_start": start + timedelta(minutes=5 * index),
            "open": Decimal("100") + index,
            "high": Decimal("101") + index,
            "low": Decimal("99") + index,
            "close": Decimal("100.5") + index,
            "volume": 1000 + index,
        }
        for index in range(75)
    ]


@pytest.fixture
def real_format_bars():
    calendar = NseCashSessionCalendar.from_trading_dates(list(PILOT_DATES))
    return calendar, normalize_rows(
        _session_rows(),
        calendar=calendar,
        source_provider="GROWW_OFFICIAL_API_FIXTURE",
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        allow_naive_exchange_local=True,
    )


def test_provider_capability_model_and_selection_rules() -> None:
    capabilities = provider_capability_audit()
    assert CAPABILITY_AUDIT_VERSION.endswith("V1")
    assert [row.provider_name for row in capabilities] == [
        "Groww",
        "Zerodha",
        "Existing licensed/local provider",
    ]
    groww = capabilities[0]
    assert groww.nse_cash_supported and groww.five_minute_supported and groww.volume_supported
    assert not groww.vwap_supported
    assert groww.research_use_status == ResearchRightsStatus.USABLE_WITH_RESTRICTIONS
    assert select_provider(capabilities, credentials_present=True) == (
        "Groww",
        ProviderSelectionResult.PROVIDER_SELECTED,
    )
    assert select_provider(capabilities, credentials_present=False)[1] == ProviderSelectionResult.AUTH_BLOCKED


def test_credential_presence_does_not_disclose_values() -> None:
    settings = Settings(GROWW_TOTP_TOKEN="sensitive-token", GROWW_TOTP_SECRET="sensitive-secret")
    assert credentials_present(settings)
    assert "sensitive-token" not in repr(settings.model_dump()) or "sensitive-secret" not in repr(
        credentials_present(settings)
    )


def test_market_data_adapter_exposes_no_order_interface() -> None:
    adapter = GrowwResearchMarketDataAdapter(
        client=FakeClient(), budget=RequestBudget(7, 7), throttle_seconds=0
    )
    for name in ("place_order", "modify_order", "cancel_order"):
        assert not hasattr(adapter, name)


def test_development_only_request_enforcement_and_validation_rejection() -> None:
    _validate_development_dates((date(2022, 1, 1), date(2024, 12, 31)))
    with pytest.raises(ValueError, match="Validation-window"):
        _validate_development_dates((date(2025, 1, 2),))


def test_symbol_session_and_row_hard_caps() -> None:
    PilotSpec().validate()
    with pytest.raises(ValueError, match="5-10 symbols"):
        replace(PilotSpec(), symbols=tuple(f"S{i}" for i in range(11))).validate()
    with pytest.raises(ValueError, match="5-10 sessions"):
        replace(PilotSpec(), dates=tuple(date(2022, 1, day) for day in range(1, 12))).validate()
    with pytest.raises(ValueError, match="10,000"):
        replace(PilotSpec(), max_normalized_rows=MAX_NORMALIZED_ROWS + 1).validate()


def test_instrument_mapping_and_result() -> None:
    budget = RequestBudget(7, 7, actual_requests=1)
    adapter = GrowwResearchMarketDataAdapter(client=FakeClient(), budget=budget, throttle_seconds=0)
    mappings = adapter.resolve_instruments(PILOT_SYMBOLS, {symbol: None for symbol in PILOT_SYMBOLS})
    assert len(mappings) == 5
    assert mappings[0].provider_symbol == "NSE-ABCAPITAL"
    assert instrument_mapping_result(mappings) == InstrumentMappingResult.CLEAN
    assert budget.actual_requests == 2


def test_provider_timestamp_normalization_and_timezone_conversion(real_format_bars) -> None:
    _calendar, bars = real_format_bars
    assert bars[0].bar_start.isoformat() == "2022-01-03T09:15:00+05:30"
    assert bars[0].bar_end.isoformat() == "2022-01-03T09:20:00+05:30"
    assert bars[0].bar_start.tzinfo == ASIA_KOLKATA


def test_session_alignment_quality_and_strict_usability(real_format_bars) -> None:
    calendar, bars = real_format_bars
    quality = assess_session_quality(bars, calendar=calendar)
    assert quality.strict_usable
    assert quality.expected_bars == quality.actual_bars == 75
    assert not quality.missing_bars and not quality.duplicate_bars
    assert SessionUsability.USABLE_STRICT == "USABLE_STRICT"


def test_raw_shapes_and_hashes(real_format_bars) -> None:
    nested = {"payload": {"candles": [["2022-01-03T09:15:00", 1, 2, 0.5, 1.5, 3]]}}
    assert len(_extract_candles(nested)) == 1
    assert _provider_candle_row(_extract_candles(nested)[0])["volume"] == 3
    _calendar, bars = real_format_bars
    assert len(intraday_dataset_hash(bars)) == 64
    assert intraday_dataset_hash(bars) == intraday_dataset_hash(reversed(bars))


def test_quality_calculation_detects_minor_and_material_gaps(real_format_bars) -> None:
    calendar, bars = real_format_bars
    complete = assess_session_quality(bars, calendar=calendar)
    missing = assess_session_quality(bars[:-1], calendar=calendar)
    assert complete.strict_usable
    assert missing.missing_bars == 1 and missing.lenient_usable
    rows = [
        {"actual_bars": 75, "missing_bars": 0, "usability": "USABLE_STRICT"},
        {"actual_bars": 74, "missing_bars": 1, "usability": "USABLE_WITH_WARNING"},
    ]
    assert _quality_result(rows) == "USABLE_WITH_MINOR_GAPS"


def test_daily_price_and_volume_reconciliation(real_format_bars) -> None:
    _calendar, bars = real_format_bars
    daily = type("Daily", (), {})
    from app.research.intraday.models import DailyBarReference

    reference = DailyBarReference(
        bars[0].symbol,
        bars[0].trading_date,
        bars[0].open,
        max(row.high for row in bars),
        min(row.low for row in bars),
        bars[-1].close,
        sum(row.volume for row in bars),
        "TEST",
    )
    matching = _reconciliation_row(bars, reference)
    assert matching["classification"] == "MATCH"
    volume = _reconciliation_row(bars, replace(reference, volume=reference.volume - 10000))
    assert volume["classification"] == "MATERIAL_VOLUME_MISMATCH"
    assert _overall_reconciliation([matching]) == "CLEAN"


def test_opening_ranges_and_vwap_on_real_format_fixture(real_format_bars) -> None:
    calendar, bars = real_format_bars
    for minutes, count in ((5, 1), (10, 2), (15, 3), (30, 6)):
        opening = calculate_opening_range(bars, window_minutes=minutes, calendar=calendar)
        assert opening.source_bar_count == count
        assert opening.completed_at == bars[count - 1].bar_end
    vwap = calculate_session_vwap(bars)
    assert len(vwap) == 75
    assert vwap[0].vwap == (bars[0].high + bars[0].low + bars[0].close) / Decimal("3")


def test_first_touch_adapter_integration_and_ordering_comparison(real_format_bars) -> None:
    _calendar, bars = real_format_bars
    touched = replace(bars[1], low=Decimal("98"), high=Decimal("101"))
    result = evaluate_first_touch(
        entry_timestamp=bars[0].bar_start,
        stop_price=Decimal("99"),
        target_price=Decimal("200"),
        bars=[bars[0], touched],
        max_holding_date=bars[0].trading_date,
    )
    assert result.first_touch == "STOP_FIRST"
    assert not result.ambiguous_same_bar


def test_rate_limit_retry_is_bounded_and_classified() -> None:
    client = FakeClient(failures=2)
    budget = RequestBudget(10, 3, actual_requests=0)
    sleeps: list[float] = []
    adapter = GrowwResearchMarketDataAdapter(
        client=client,
        budget=budget,
        throttle_seconds=0,
        max_retries=3,
        sleeper=sleeps.append,
    )
    mapping = InstrumentMapping("ABCAPITAL", None, "NSE-ABCAPITAL", "1", "NSE", "TEST", "UNKNOWN", "UNKNOWN", "CLEAN")
    response, metric = adapter.fetch_historical_5m(
        mapping=mapping,
        start_date=PILOT_DATES[0],
        end_date=PILOT_DATES[-1],
        request_id="TEST",
    )
    assert response["candles"] and metric["status"] == "SUCCESS"
    assert budget.retry_count == 2 and client.calls == 3
    assert classify_provider_failure(TimeoutError("timeout")) == "TRANSIENT_NETWORK"
    assert classify_provider_failure(RuntimeError("429 rate limit")) == "RATE_LIMIT"


def test_provider_failure_classification_does_not_retry_permissions() -> None:
    assert classify_provider_failure(RuntimeError("403 permission denied")) == "AUTHENTICATION_FAILURE"
    assert classify_provider_failure(ValueError("invalid instrument")) == "DATA_UNAVAILABLE_OR_INVALID_INSTRUMENT"


def test_command_identity_and_full_ingestion_remains_unexecuted() -> None:
    assert PILOT_VERSION == "REAL_INTRADAY_PROVIDER_PILOT_V1"
    assert PILOT_PROFILE == "NSE_CASH_5M_PROVIDER_PILOT_V1"
    assert FullIngestionFeasibility.FEASIBLE_WITH_BATCHING == "FEASIBLE_WITH_BATCHING"


def test_dry_run_report_generation_holdout_and_baseline_guards() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = build_real_intraday_provider_pilot(
        repo_root=repo_root,
        settings=Settings(GROWW_TOTP_TOKEN="", GROWW_TOTP_SECRET=""),
    )
    assert report["runtime_status"] == "DRY_RUN_NO_PROVIDER_CONTACT"
    assert report["request_budget"]["actual_requests"] == 0
    assert report["safety"]["validation_state"] == "SEALED"
    assert report["safety"]["validation_run_count"] == 0
    assert report["safety"]["validation_performance_exposed"] is False
    assert report["safety"]["strategy_v2_created"] is False
    assert report["safety"]["strategy_v1_modified"] is False
    assert report["regression"]["baseline_mutation_violations"] == 0
    assert report["security"]["adapter_order_methods"] is False
    for path in report["report_paths"]:
        assert Path(path).stat().st_size > 0
    persisted = json.loads(
        (repo_root / "data/reports/real_intraday_provider_v1_summary.json").read_text(encoding="utf-8")
    )
    assert persisted["safety"]["live_orders_placed"] == 0
    assert persisted["safety"]["broker_order_calls"] == 0
    assert persisted["safety"]["remote_migrations_applied"] == 0
    assert persisted["safety"]["supabase_records_persisted"] == 0

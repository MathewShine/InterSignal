from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.market_api.factory import build_market_data_provider
from app.market_api.service import MarketIntelligenceService
from app.providers.market_data import MarketProviderMode
from app.providers.market_seeded import SeededMarketDataProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
FIXED_NOW = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)


def _copy_recorded_references(target: Path) -> Path:
    paths = (
        "reference/nse/indices/normalized/benchmark_daily.csv",
        "reference/nse/indices/normalized/sector_index_daily.csv",
        "reference/nse/indices/normalized/stock_sector_mapping.csv",
        "reference/nse/calendar/nse_cash_trading_calendar.csv",
        "reference/nifty500/current/nifty500_constituents_normalized.csv",
    )
    for relative in paths:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DATA_ROOT / relative, destination)
    return target


def test_seeded_provider_is_deterministic_normalized_and_explicit() -> None:
    provider = SeededMarketDataProvider(DATA_ROOT)

    first = (
        provider.get_index_snapshot(),
        provider.get_universe_snapshot(),
        provider.get_breadth_snapshot(),
        provider.get_sector_snapshot(),
        provider.get_volume_snapshot(),
        provider.get_market_status(),
        provider.get_freshness(),
    )
    second = (
        provider.get_index_snapshot(),
        provider.get_universe_snapshot(),
        provider.get_breadth_snapshot(),
        provider.get_sector_snapshot(),
        provider.get_volume_snapshot(),
        provider.get_market_status(),
        provider.get_freshness(),
    )

    assert first == second
    assert provider.mode == MarketProviderMode.SEEDED
    assert provider.provider_name == "INTERSIGNAL_RECORDED_NSE"
    assert provider.market == "INDIA_NSE"
    indices = {row.symbol: row for row in first[0]}
    assert set(indices) == {"NIFTY_500", "NIFTY_50"}
    assert indices["NIFTY_500"].name == "NIFTY 500"
    assert indices["NIFTY_500"].source == "NSE_OFFICIAL_RECORDED_EOD"
    assert indices["NIFTY_500"].timestamp.tzinfo is not None
    assert first[1] is not None
    assert first[1].membership_kind == "CURRENT_EFFECTIVE_ONLY"


def test_seeded_provider_omits_unsupported_fields_and_handles_partial_sources(tmp_path: Path) -> None:
    provider = SeededMarketDataProvider(_copy_recorded_references(tmp_path))

    assert provider.get_index_snapshot()
    assert provider.get_universe_snapshot() is not None
    assert provider.get_sector_snapshot()
    assert provider.get_breadth_snapshot() is None
    assert provider.get_volume_snapshot() is None
    assert "EOD_BREADTH" not in provider.capabilities
    assert "EOD_VOLUME_CONTEXT" not in provider.capabilities

    snapshot = MarketIntelligenceService(provider=provider, clock=lambda: FIXED_NOW).get_snapshot()
    assert snapshot.status == "PARTIAL"
    assert snapshot.availability.indices.status == "AVAILABLE"
    assert snapshot.availability.breadth.status == "UNAVAILABLE"
    assert snapshot.availability.volume.status == "UNAVAILABLE"
    assert snapshot.breadth is None
    assert snapshot.volume is None


def test_empty_seed_source_returns_controlled_unavailable_snapshot(tmp_path: Path) -> None:
    provider = SeededMarketDataProvider(tmp_path)
    snapshot = MarketIntelligenceService(provider=provider, clock=lambda: FIXED_NOW).get_snapshot()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.indices == ()
    assert snapshot.universe is None
    assert snapshot.breadth is None
    assert snapshot.sectors == ()
    assert snapshot.volume is None
    assert snapshot.session is None
    assert snapshot.freshness.freshness_status == "UNKNOWN"


def test_provider_selection_never_claims_unimplemented_groww_live_mode(tmp_path: Path) -> None:
    build_market_data_provider.cache_clear()
    groww = build_market_data_provider(tmp_path, "groww")
    none = build_market_data_provider(tmp_path, "none")
    unsupported = build_market_data_provider(tmp_path, "vendor-x")

    assert groww.mode == MarketProviderMode.UNAVAILABLE
    assert groww.provider_name == "GROWW"
    assert groww.reason == "GROWW_LIVE_MARKET_PROVIDER_NOT_IMPLEMENTED"
    assert none.mode == MarketProviderMode.UNAVAILABLE
    assert unsupported.mode == MarketProviderMode.UNAVAILABLE
    assert all(provider.mode != MarketProviderMode.LIVE for provider in (groww, none, unsupported))

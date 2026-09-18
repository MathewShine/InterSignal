from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config.settings import Settings
from app.market_api.service import MarketIntelligenceService
from app.providers.market_data import MarketDataProvider, UnavailableMarketDataProvider
from app.providers.market_seeded import SeededMarketDataProvider


@lru_cache(maxsize=8)
def build_market_data_provider(data_root: Path, selection: str) -> MarketDataProvider:
    normalized = selection.strip().lower()
    if normalized == "seeded":
        return SeededMarketDataProvider(data_root)
    if normalized == "groww":
        return UnavailableMarketDataProvider(
            requested_provider="groww",
            reason="GROWW_LIVE_MARKET_PROVIDER_NOT_IMPLEMENTED",
        )
    if normalized in {"none", "unavailable", ""}:
        return UnavailableMarketDataProvider(
            requested_provider="none",
            reason="MARKET_DATA_PROVIDER_NOT_CONFIGURED",
        )
    return UnavailableMarketDataProvider(
        requested_provider=normalized,
        reason="MARKET_DATA_PROVIDER_SELECTION_UNSUPPORTED",
    )


def build_market_intelligence_service(settings: Settings) -> MarketIntelligenceService:
    provider = build_market_data_provider(
        Path(settings.market_data_root).resolve(),
        settings.market_data_provider,
    )
    return MarketIntelligenceService(provider=provider)


__all__ = ("build_market_data_provider", "build_market_intelligence_service")

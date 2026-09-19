from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config.settings import Settings
from app.market_api.live import MarketLiveCache, MarketStreamHub
from app.market_api.service import MarketIntelligenceService
from app.market_api.workspace_service import MarketWorkspaceService
from app.providers.groww import (
    GrowwAuthService,
    GrowwCredentials,
    GrowwFeedManager,
    GrowwInstrumentCache,
    GrowwMarketDataProvider,
)
from app.providers.market_data import MarketDataProvider, UnavailableMarketDataProvider
from app.providers.market_seeded import SeededMarketDataProvider


@lru_cache(maxsize=16)
def build_market_data_provider(
    data_root: Path,
    selection: str,
    groww_access_token: str | None = None,
    groww_api_key: str | None = None,
    groww_api_secret: str | None = None,
    groww_totp_token: str | None = None,
    groww_totp_secret: str | None = None,
    instrument_cache_path: Path | None = None,
) -> MarketDataProvider:
    normalized = selection.strip().lower()
    if normalized == "seeded":
        return SeededMarketDataProvider(data_root)
    if normalized == "groww":
        credentials = GrowwCredentials(
            access_token=groww_access_token,
            api_key=groww_api_key,
            api_secret=groww_api_secret,
            totp_token=groww_totp_token,
            totp_secret=groww_totp_secret,
        )
        return GrowwMarketDataProvider(
            auth_service=GrowwAuthService(credentials=credentials if credentials.configured else None),
            instrument_cache=GrowwInstrumentCache(
                instrument_cache_path or data_root / "cache/market/groww-instruments.csv"
            ),
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
    return MarketIntelligenceService(provider=build_selected_market_data_provider(settings))


def build_selected_market_data_provider(settings: Settings) -> MarketDataProvider:
    return build_market_data_provider(
        Path(settings.market_data_root).resolve(),
        settings.market_data_provider,
        settings.groww_api_access_token,
        settings.groww_api_key,
        settings.groww_api_secret,
        settings.groww_totp_token,
        settings.groww_totp_secret,
        Path(settings.market_instrument_cache).resolve(),
    )


@dataclass(slots=True)
class MarketRuntime:
    provider: MarketDataProvider
    intelligence: MarketIntelligenceService
    workspace: MarketWorkspaceService
    cache: MarketLiveCache
    stream: MarketStreamHub
    feed: GrowwFeedManager | None


def build_market_runtime(settings: Settings) -> MarketRuntime:
    provider = build_selected_market_data_provider(settings)
    cache = MarketLiveCache()
    stream = MarketStreamHub(cache=cache)
    feed = None
    if isinstance(provider, GrowwMarketDataProvider):
        feed = GrowwFeedManager(
            auth_service=provider.auth_service,
            instrument_cache=provider.instrument_cache,
            on_tick=stream.publish_observation,
        )
    return MarketRuntime(
        provider=provider,
        intelligence=MarketIntelligenceService(provider=provider),
        workspace=MarketWorkspaceService(provider=provider, feed_manager=feed),
        cache=cache,
        stream=stream,
        feed=feed,
    )


__all__ = (
    "MarketRuntime",
    "build_market_data_provider",
    "build_market_intelligence_service",
    "build_market_runtime",
    "build_selected_market_data_provider",
)

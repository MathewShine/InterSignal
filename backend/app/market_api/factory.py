from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config.settings import Settings
from app.market_api.live import MarketLiveCache, MarketStreamHub
from app.market_api.session_manager import DEFAULT_MONITORED_INSTRUMENTS, MarketSessionManager
from app.market_api.session_models import TickRecordingMode
from app.market_api.session_repository import JsonlMarketObservationStore
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
    sessions: MarketSessionManager


def build_market_runtime(settings: Settings) -> MarketRuntime:
    provider = build_selected_market_data_provider(settings)
    cache = MarketLiveCache()
    stream = MarketStreamHub(cache=cache)
    feed = None
    if isinstance(provider, GrowwMarketDataProvider):
        feed = GrowwFeedManager(
            auth_service=provider.auth_service,
            instrument_cache=provider.instrument_cache,
        )
    store = JsonlMarketObservationStore(Path(settings.market_session_data_root).resolve())
    try:
        recording_mode = TickRecordingMode(settings.market_tick_recording_mode.strip().upper())
    except ValueError:
        recording_mode = TickRecordingMode.SELECTED
    selected_instruments = tuple(
        item.strip() for item in settings.market_observation_instruments.split(",") if item.strip()
    ) or DEFAULT_MONITORED_INSTRUMENTS
    sessions = MarketSessionManager(
        provider=provider,
        feed_manager=feed,
        live_cache=cache,
        session_repository=store,
        observation_repository=store,
        recording_mode=recording_mode,
        selected_instruments=selected_instruments,
        sample_interval_seconds=settings.market_observation_sample_seconds,
        summary_interval_seconds=settings.market_session_summary_seconds,
        stale_threshold_seconds=settings.market_stale_threshold_seconds,
    )
    if feed:
        async def publish_observation(tick):
            await stream.publish_observation(tick)
            await sessions.observe_tick(tick)

        async def record_feed_state(state):
            await sessions.record_provider_state(str(getattr(state, "value", state)))

        feed.on_tick = publish_observation
        feed.on_state_change = record_feed_state
    workspace = MarketWorkspaceService(provider=provider, feed_manager=feed, session_manager=sessions)
    return MarketRuntime(
        provider=provider,
        intelligence=MarketIntelligenceService(provider=provider),
        workspace=workspace,
        cache=cache,
        stream=stream,
        feed=feed,
        sessions=sessions,
    )


__all__ = (
    "MarketRuntime",
    "build_market_data_provider",
    "build_market_intelligence_service",
    "build_market_runtime",
    "build_selected_market_data_provider",
)

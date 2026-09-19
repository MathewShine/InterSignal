from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect

from app.market_api.factory import MarketRuntime, build_market_intelligence_service, build_market_runtime
from app.market_api.models import MarketSnapshot
from app.market_api.service import MarketIntelligenceService
from app.market_api.session_manager import MarketSessionManager
from app.market_api.session_models import (
    MarketCurrentSessionResponse,
    MarketObservationSession,
    MarketSessionEventsResponse,
    MarketSessionListResponse,
    MarketSessionSummary,
)
from app.market_api.workspace_models import (
    INTERSIGNAL_MARKET_STREAM_V1,
    MarketCandlesResponse,
    MarketIndexDetailResponse,
    MarketIndicesResponse,
    MarketProviderStatusResponse,
    MarketQuoteResponse,
    MarketSearchResponse,
    MarketSectorDetailResponse,
    MarketSectorsResponse,
    OptionChainResponse,
)
from app.market_api.workspace_service import MarketWorkspaceService


router = APIRouter(prefix="/market", tags=["market"])


def get_market_intelligence_service(request: Request) -> MarketIntelligenceService:
    runtime = getattr(request.app.state, "market_runtime", None)
    return runtime.intelligence if runtime else build_market_intelligence_service(request.app.state.settings)


def get_market_runtime(request: Request) -> MarketRuntime:
    runtime = getattr(request.app.state, "market_runtime", None)
    if runtime is None:
        runtime = build_market_runtime(request.app.state.settings)
        request.app.state.market_runtime = runtime
    return runtime


def get_market_workspace_service(request: Request) -> MarketWorkspaceService:
    return get_market_runtime(request).workspace


def get_market_session_manager(request: Request) -> MarketSessionManager:
    return get_market_runtime(request).sessions


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/snapshot", response_model=MarketSnapshot)
def market_snapshot(
    response: Response,
    service: MarketIntelligenceService = Depends(get_market_intelligence_service),
) -> MarketSnapshot:
    _no_store(response)
    return service.get_snapshot()


@router.get("/provider/status", response_model=MarketProviderStatusResponse)
def provider_status(response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketProviderStatusResponse:
    _no_store(response)
    return service.provider_status()


@router.get("/instruments/search", response_model=MarketSearchResponse)
def instrument_search(
    response: Response,
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    service: MarketWorkspaceService = Depends(get_market_workspace_service),
) -> MarketSearchResponse:
    _no_store(response)
    return service.search(q, limit=limit)


@router.get("/instruments/{symbol}/quote", response_model=MarketQuoteResponse)
def instrument_quote(symbol: str, response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketQuoteResponse:
    _no_store(response)
    return service.quote(symbol)


@router.get("/instruments/{symbol}/candles", response_model=MarketCandlesResponse)
def instrument_candles(
    symbol: str,
    response: Response,
    range_name: str = Query(default="1M", alias="range"),
    interval: str | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    service: MarketWorkspaceService = Depends(get_market_workspace_service),
) -> MarketCandlesResponse:
    _no_store(response)
    return service.candles(symbol, range_name=range_name, interval=interval, start=from_time, end=to_time)


@router.get("/indices", response_model=MarketIndicesResponse)
def indices(response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketIndicesResponse:
    _no_store(response)
    return service.indices()


@router.get("/indices/{symbol}", response_model=MarketIndexDetailResponse)
def index_detail(symbol: str, response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketIndexDetailResponse:
    _no_store(response)
    return service.index_detail(symbol)


@router.get("/sectors", response_model=MarketSectorsResponse)
def sectors(response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketSectorsResponse:
    _no_store(response)
    return service.sectors()


@router.get("/sectors/{sector_id}", response_model=MarketSectorDetailResponse)
def sector_detail(sector_id: str, response: Response, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> MarketSectorDetailResponse:
    _no_store(response)
    return service.sector_detail(sector_id)


def _option_items(runtime: MarketRuntime, method: str, *arguments: str) -> tuple[object, ...]:
    try:
        return tuple(getattr(runtime.provider, method)(*arguments))
    except Exception:
        return ()


@router.get("/options/expiries")
def option_expiries(response: Response, underlying: str, runtime: MarketRuntime = Depends(get_market_runtime)) -> dict[str, object]:
    _no_store(response)
    items = _option_items(runtime, "get_option_expiries", underlying)
    return {"version": "INTERSIGNAL_OPTION_CHAIN_V1", "status": "AVAILABLE" if items else "UNAVAILABLE", "underlying": underlying.upper(), "items": items, "read_only": True}


@router.get("/options/contracts")
def option_contracts(response: Response, underlying: str, expiry: str, runtime: MarketRuntime = Depends(get_market_runtime)) -> dict[str, object]:
    _no_store(response)
    items = _option_items(runtime, "get_option_contracts", underlying, expiry)
    return {"version": "INTERSIGNAL_OPTION_CHAIN_V1", "status": "AVAILABLE" if items else "UNAVAILABLE", "underlying": underlying.upper(), "expiry": expiry, "items": items, "read_only": True}


@router.get("/options/chain", response_model=OptionChainResponse)
def option_chain(response: Response, underlying: str, expiry: str, service: MarketWorkspaceService = Depends(get_market_workspace_service)) -> OptionChainResponse:
    _no_store(response)
    return service.option_chain(underlying, expiry)


@router.post("/session/start", response_model=MarketObservationSession)
async def start_market_session(
    response: Response,
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketObservationSession:
    _no_store(response)
    return await manager.start()


@router.post("/session/stop", response_model=MarketSessionSummary)
async def stop_market_session(
    response: Response,
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketSessionSummary:
    _no_store(response)
    try:
        return await manager.stop()
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": str(error), "message": "No active market observation session."}) from None


@router.get("/session/current", response_model=MarketCurrentSessionResponse)
def current_market_session(
    response: Response,
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketCurrentSessionResponse:
    _no_store(response)
    return MarketCurrentSessionResponse(generated_at=datetime.now().astimezone(), session=manager.current())


@router.get("/sessions", response_model=MarketSessionListResponse)
def market_sessions(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketSessionListResponse:
    _no_store(response)
    return MarketSessionListResponse(generated_at=datetime.now().astimezone(), items=manager.list(limit=limit))


@router.get("/sessions/{session_id}", response_model=MarketObservationSession)
def market_session_detail(
    session_id: str,
    response: Response,
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketObservationSession:
    _no_store(response)
    session = manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "MARKET_SESSION_NOT_FOUND", "message": "Market session not found."})
    return session


@router.get("/sessions/{session_id}/events", response_model=MarketSessionEventsResponse)
def market_session_events(
    session_id: str,
    response: Response,
    limit: int = Query(default=500, ge=1, le=2000),
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketSessionEventsResponse:
    _no_store(response)
    if not manager.get(session_id):
        raise HTTPException(status_code=404, detail={"code": "MARKET_SESSION_NOT_FOUND", "message": "Market session not found."})
    return MarketSessionEventsResponse(
        generated_at=datetime.now().astimezone(),
        session_id=session_id,
        items=manager.observation_repository.list_events(session_id, limit=limit),
    )


@router.get("/sessions/{session_id}/summary", response_model=MarketSessionSummary)
def market_session_summary(
    session_id: str,
    response: Response,
    manager: MarketSessionManager = Depends(get_market_session_manager),
) -> MarketSessionSummary:
    _no_store(response)
    try:
        return manager.summary(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "MARKET_SESSION_NOT_FOUND", "message": "Market session not found."}) from None


async def _stream_receive(websocket: WebSocket, client_id: str, runtime: MarketRuntime) -> None:
    while True:
        message = await websocket.receive_json()
        action = str(message.get("action") or message.get("type") or "").strip().lower()
        raw_symbols = message.get("instruments") or message.get("symbols") or ()
        symbols = tuple(str(value) for value in raw_symbols) if isinstance(raw_symbols, list) else ()
        if action == "subscribe":
            try:
                added = runtime.stream.subscribe(client_id, symbols)
                if runtime.feed and added:
                    await runtime.feed.subscribe(added)
                await websocket.send_json(runtime.stream.acknowledgement("subscribed", added))
            except ValueError as error:
                await websocket.send_json({"version": INTERSIGNAL_MARKET_STREAM_V1, "event": "ERROR", "code": str(error)})
        elif action == "unsubscribe":
            removed = runtime.stream.unsubscribe(client_id, symbols)
            if runtime.feed and removed:
                await runtime.feed.unsubscribe(removed)
            await websocket.send_json(runtime.stream.acknowledgement("unsubscribed", removed))
        elif action == "ping":
            await websocket.send_json({"version": INTERSIGNAL_MARKET_STREAM_V1, "event": "PONG"})


async def _stream_send(websocket: WebSocket, queue: asyncio.Queue[dict[str, object]]) -> None:
    while True:
        await websocket.send_json(await queue.get())


@router.websocket("/stream")
async def market_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime: MarketRuntime = websocket.app.state.market_runtime
    client_id = uuid4().hex
    queue = runtime.stream.register(client_id)
    await websocket.send_json({
        "version": INTERSIGNAL_MARKET_STREAM_V1,
        "event": "PROVIDER_STATUS",
        "provider": runtime.provider.provider_name,
        "mode": runtime.provider.mode.value,
        "stream_state": str(getattr(getattr(runtime.feed, "state", None), "value", "NOT_AVAILABLE")),
    })
    receiver = asyncio.create_task(_stream_receive(websocket, client_id, runtime))
    sender = asyncio.create_task(_stream_send(websocket, queue))
    try:
        done, pending = await asyncio.wait((receiver, sender), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        removed = runtime.stream.unregister(client_id)
        if runtime.feed and removed:
            await runtime.feed.unsubscribe(removed)


__all__ = (
    "get_market_intelligence_service",
    "get_market_session_manager",
    "get_market_workspace_service",
    "router",
)

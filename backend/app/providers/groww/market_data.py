from __future__ import annotations

from collections import deque
from contextlib import redirect_stdout
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from threading import Event, Lock
from time import monotonic
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.providers.groww.auth import GrowwAuthService
from app.providers.groww.exceptions import (
    GrowwMarketDataError,
    GrowwProviderNotConfiguredError,
    GrowwRateLimitError,
)
from app.providers.groww.historical import INTERVAL_CONSTANTS, INTERVAL_LIMIT_DAYS
from app.providers.groww.instruments import GrowwInstrumentCache
from app.providers.market_data import (
    InterSignalInstrument,
    MarketBreadthObservation,
    MarketCandleObservation,
    MarketDataProvider,
    MarketDepthLevelObservation,
    MarketFreshnessObservation,
    MarketIndexObservation,
    MarketProviderCapability,
    MarketProviderMode,
    MarketQualityObservation,
    MarketQuoteObservation,
    MarketSectorObservation,
    MarketSessionObservation,
    MarketUniverseObservation,
    MarketVolumeObservation,
)


class _GrowwLiveRateLimiter:
    """Enforces the documented shared live-data REST limits before SDK calls."""

    def __init__(self, *, per_second: int = 10, per_minute: int = 300) -> None:
        self.per_second = per_second
        self.per_minute = per_minute
        self._requests: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        now = monotonic()
        with self._lock:
            while self._requests and now - self._requests[0] >= 60:
                self._requests.popleft()
            recent_second = sum(now - value < 1 for value in self._requests)
            if recent_second >= self.per_second or len(self._requests) >= self.per_minute:
                raise GrowwRateLimitError()
            self._requests.append(now)


class GrowwMarketDataProvider(MarketDataProvider):
    """Read-only Groww adapter. Raw SDK payloads never cross this boundary."""

    QUOTE_TTL_SECONDS = 2.0
    SOURCE = "GROWW_TRADING_API"
    INDEX_SYMBOLS = (
        ("NIFTY_50", "NIFTY"),
        ("NIFTY_500", "NIFTY500"),
        ("BANK_NIFTY", "BANKNIFTY"),
        ("FINNIFTY", "FINNIFTY"),
    )
    SECTOR_SYMBOLS = (
        "BANKNIFTY",
        "FINNIFTY",
        "NIFTYAUTO",
        "NIFTYFMCG",
        "NIFTYIT",
        "NIFTYMEDIA",
        "NIFTYMETAL",
        "NIFTYPHARMA",
        "NIFTYPSUBANK",
        "NIFTYPVTBANK",
        "NIFTYREALTY",
    )

    def __init__(
        self,
        *,
        auth_service: GrowwAuthService,
        instrument_cache: GrowwInstrumentCache,
        clock: Callable[[], datetime] | None = None,
        rate_limiter: _GrowwLiveRateLimiter | None = None,
    ) -> None:
        self.auth_service = auth_service
        self.instrument_cache = instrument_cache
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rate_limiter = rate_limiter or _GrowwLiveRateLimiter()
        self._quote_cache: dict[str, tuple[float, MarketQuoteObservation]] = {}
        self._quote_lock = Lock()
        self._quote_inflight: dict[str, Event] = {}
        self._last_message_at: datetime | None = None
        self._last_session_status: str | None = None
        self._connected = False
        self._context_cache: tuple[
            float,
            tuple[InterSignalInstrument, ...],
            dict[str, Decimal],
            dict[str, dict[str, Decimal | None]],
        ] | None = None

    @property
    def provider_name(self) -> str:
        return "GROWW"

    @property
    def configured(self) -> bool:
        return self.auth_service.is_configured

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> MarketProviderMode:
        return MarketProviderMode.LIVE if self.configured else MarketProviderMode.UNAVAILABLE

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.configured else "GROWW_NOT_CONFIGURED"

    @property
    def capabilities(self) -> tuple[MarketProviderCapability, ...]:
        return (
            MarketProviderCapability.INSTRUMENT_MASTER,
            MarketProviderCapability.SEARCH,
            MarketProviderCapability.QUOTE,
            MarketProviderCapability.LTP,
            MarketProviderCapability.OHLC,
            MarketProviderCapability.MARKET_DEPTH,
            MarketProviderCapability.HISTORICAL_CANDLES,
            MarketProviderCapability.STREAMING_QUOTES,
            MarketProviderCapability.STREAMING_DEPTH,
            MarketProviderCapability.INDICES,
            MarketProviderCapability.SECTORS,
            MarketProviderCapability.SECTOR_INDEX_CONTEXT,
            MarketProviderCapability.FNO,
            MarketProviderCapability.OPTION_CHAIN,
        )

    @property
    def last_message_at(self) -> datetime | None:
        return self._last_message_at

    def list_instruments(self) -> tuple[InterSignalInstrument, ...]:
        instruments = self.instrument_cache.instruments()
        if instruments:
            return instruments
        return self.instrument_cache.refresh()

    def search_instruments(self, query: str, *, limit: int = 20) -> tuple[InterSignalInstrument, ...]:
        if not self.instrument_cache.instruments():
            self.instrument_cache.refresh()
        return self.instrument_cache.search(query, limit=limit)

    def get_quote(self, symbol: str) -> MarketQuoteObservation | None:
        self._ensure_configured()
        instrument = self._find_instrument(symbol)
        if instrument is None:
            return None
        cache_key = instrument.instrument_id
        while True:
            with self._quote_lock:
                cached = self._quote_cache.get(cache_key)
                now = monotonic()
                if cached and now - cached[0] < self.QUOTE_TTL_SECONDS:
                    return cached[1]
                pending = self._quote_inflight.get(cache_key)
                if pending is None:
                    pending = Event()
                    self._quote_inflight[cache_key] = pending
                    break
            if not pending.wait(timeout=30):
                raise GrowwMarketDataError()

        try:
            payload = self._request(
                "get_quote",
                exchange=instrument.exchange,
                segment=instrument.segment,
                trading_symbol=instrument.symbol,
            )
            quote = self._normalize_quote(instrument, payload)
            with self._quote_lock:
                self._quote_cache[cache_key] = (monotonic(), quote)
            self._last_message_at = quote.timestamp
            self._last_session_status = quote.session_status
            self._connected = True
            return quote
        finally:
            with self._quote_lock:
                completed = self._quote_inflight.pop(cache_key, None)
                if completed is not None:
                    completed.set()

    def get_ltp(self, symbols: tuple[str, ...]) -> dict[str, Decimal]:
        self._ensure_configured()
        instruments = tuple(filter(None, (self._find_instrument(symbol) for symbol in symbols)))
        grouped: dict[str, list[InterSignalInstrument]] = {}
        for instrument in instruments:
            grouped.setdefault(instrument.segment, []).append(instrument)
        normalized: dict[str, Decimal] = {}
        for segment, rows in grouped.items():
            payload = self._request(
                "get_ltp",
                segment=segment,
                exchange_trading_symbols=tuple(f"{row.exchange}_{row.symbol}" for row in rows),
            )
            values = self._payload(payload)
            for row in rows:
                value = values.get(f"{row.exchange}_{row.symbol}") if isinstance(values, dict) else None
                parsed = self._decimal(value)
                if parsed is not None:
                    normalized[row.instrument_id] = parsed
        return normalized

    def get_ohlc(self, symbols: tuple[str, ...]) -> dict[str, dict[str, Decimal | None]]:
        self._ensure_configured()
        instruments = tuple(filter(None, (self._find_instrument(symbol) for symbol in symbols)))
        grouped: dict[str, list[InterSignalInstrument]] = {}
        for instrument in instruments:
            grouped.setdefault(instrument.segment, []).append(instrument)
        normalized: dict[str, dict[str, Decimal | None]] = {}
        for segment, rows in grouped.items():
            payload = self._request(
                "get_ohlc",
                segment=segment,
                exchange_trading_symbols=tuple(f"{row.exchange}_{row.symbol}" for row in rows),
            )
            values = self._payload(payload)
            for row in rows:
                raw = values.get(f"{row.exchange}_{row.symbol}") if isinstance(values, dict) else None
                if isinstance(raw, dict):
                    normalized[row.instrument_id] = {
                        field: self._decimal(raw.get(field)) for field in ("open", "high", "low", "close")
                    }
        return normalized

    def get_candles(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> tuple[MarketCandleObservation, ...]:
        self._ensure_configured()
        instrument = self._find_instrument(symbol)
        if instrument is None or interval not in INTERVAL_CONSTANTS:
            return ()
        client = self.auth_service.get_client()
        constant_name, fallback = INTERVAL_CONSTANTS[interval]
        maximum_days = INTERVAL_LIMIT_DAYS[interval]
        cursor = start
        normalized: dict[datetime, MarketCandleObservation] = {}
        while cursor < end:
            chunk_end = min(end, cursor + timedelta(days=maximum_days - 1))
            payload = self._request(
                "get_historical_candles",
                live_limit=False,
                exchange=getattr(client, f"EXCHANGE_{instrument.exchange}", instrument.exchange),
                segment=getattr(client, f"SEGMENT_{instrument.segment}", instrument.segment),
                groww_symbol=instrument.groww_symbol or f"{instrument.exchange}-{instrument.symbol}",
                start_time=cursor.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                end_time=chunk_end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                candle_interval=getattr(client, constant_name, fallback),
            )
            raw = self._payload(payload)
            candles = raw.get("candles", []) if isinstance(raw, dict) else []
            for row in candles:
                candle = self._normalize_candle(row)
                if candle is not None:
                    normalized[candle.timestamp] = candle
            cursor = chunk_end + timedelta(seconds=1)
        return tuple(normalized[key] for key in sorted(normalized))

    def get_index_snapshot(self) -> tuple[MarketIndexObservation, ...]:
        if self._last_message_at is None:
            self.get_market_status()
        instruments, ltp, ohlc = self._context_market_values()
        by_symbol = {instrument.symbol: instrument for instrument in instruments}
        observations: list[MarketIndexObservation] = []
        for canonical_symbol, provider_symbol in self.INDEX_SYMBOLS:
            instrument = by_symbol.get(provider_symbol)
            if instrument is None or instrument.instrument_id not in ltp:
                continue
            value = ltp[instrument.instrument_id]
            values = ohlc.get(instrument.instrument_id) or {}
            previous_close = values.get("close")
            change = value - previous_close if previous_close is not None else None
            change_pct = (
                change / previous_close * Decimal("100")
                if change is not None and previous_close not in (None, Decimal("0"))
                else None
            )
            observations.append(
                MarketIndexObservation(
                    symbol=canonical_symbol,
                    name=instrument.display_name,
                    value=value,
                    change=change,
                    change_pct=change_pct,
                    previous_close=previous_close,
                    timestamp=self._last_message_at or self.clock().astimezone(timezone.utc),
                    source=self.SOURCE,
                    open=values.get("open"),
                    high=values.get("high"),
                    low=values.get("low"),
                )
            )
        return tuple(observations)

    def get_universe_snapshot(self) -> MarketUniverseObservation | None:
        return None

    def get_sector_snapshot(self) -> tuple[MarketSectorObservation, ...]:
        instruments, ltp, ohlc = self._context_market_values()
        sector_symbols = set(self.SECTOR_SYMBOLS)
        instruments = tuple(instrument for instrument in instruments if instrument.symbol in sector_symbols)
        if not instruments:
            return ()
        quality = MarketQualityObservation(coverage_count=1, expected_count=1, missing_count=0)
        rows: list[MarketSectorObservation] = []
        for instrument in instruments:
            value = ltp.get(instrument.instrument_id)
            close = (ohlc.get(instrument.instrument_id) or {}).get("close")
            if value is None:
                continue
            change_pct = ((value - close) / close * Decimal("100")) if close not in (None, Decimal("0")) else None
            rows.append(
                MarketSectorObservation(
                    sector=instrument.display_name,
                    return_pct=change_pct,
                    advancers=None,
                    decliners=None,
                    unchanged=None,
                    breadth_pct=None,
                    relative_strength=None,
                    volume_context=None,
                    quality=quality,
                    index_value=value,
                )
            )
        return tuple(rows)

    def _context_market_values(
        self,
    ) -> tuple[
        tuple[InterSignalInstrument, ...],
        dict[str, Decimal],
        dict[str, dict[str, Decimal | None]],
    ]:
        now = monotonic()
        if self._context_cache and now - self._context_cache[0] < self.QUOTE_TTL_SECONDS:
            return self._context_cache[1], self._context_cache[2], self._context_cache[3]
        requested = tuple(provider_symbol for _, provider_symbol in self.INDEX_SYMBOLS) + self.SECTOR_SYMBOLS
        unique: dict[str, InterSignalInstrument] = {}
        for symbol in requested:
            instrument = self._find_instrument(symbol)
            if instrument is not None:
                unique[instrument.instrument_id] = instrument
        instruments = tuple(unique.values())
        instrument_ids = tuple(instrument.instrument_id for instrument in instruments)
        ltp = self.get_ltp(instrument_ids)
        ohlc = self.get_ohlc(instrument_ids)
        self._context_cache = (monotonic(), instruments, ltp, ohlc)
        return instruments, ltp, ohlc

    def get_breadth_snapshot(self) -> MarketBreadthObservation | None:
        return None

    def get_volume_snapshot(self) -> MarketVolumeObservation | None:
        return None

    def get_market_status(self) -> MarketSessionObservation | None:
        if self._last_message_at is None or self._last_session_status is None:
            try:
                self.get_quote("RELIANCE")
            except Exception:
                return None
        if self._last_message_at is None or self._last_session_status is None:
            return None
        return MarketSessionObservation(
            status=self._last_session_status,
            market_date=self._last_message_at.astimezone(ZoneInfo("Asia/Kolkata")).date(),
            session_timestamp=self._last_message_at,
        )

    def get_freshness(self) -> MarketFreshnessObservation:
        return MarketFreshnessObservation(source_timestamp=self._last_message_at)

    def get_option_expiries(self, underlying: str) -> tuple[str, ...]:
        self._ensure_configured()
        payload = self._request(
            "get_expiries",
            live_limit=False,
            exchange="NSE",
            underlying_symbol=underlying.strip().upper(),
        )
        values = self._payload(payload)
        return tuple(values.get("expiries", ())) if isinstance(values, dict) else ()

    def get_option_contracts(self, underlying: str, expiry: str) -> tuple[str, ...]:
        self._ensure_configured()
        payload = self._request(
            "get_contracts",
            live_limit=False,
            exchange="NSE",
            underlying_symbol=underlying.strip().upper(),
            expiry_date=expiry,
        )
        values = self._payload(payload)
        return tuple(values.get("contracts", ())) if isinstance(values, dict) else ()

    def get_option_chain(self, underlying: str, expiry: str) -> tuple[dict[str, object], ...]:
        self._ensure_configured()
        payload = self._request(
            "get_option_chain",
            exchange="NSE",
            underlying=underlying.strip().upper(),
            expiry_date=expiry,
        )
        values = self._payload(payload)
        strikes = values.get("strikes", {}) if isinstance(values, dict) else {}
        if not isinstance(strikes, dict):
            return ()
        rows: list[dict[str, object]] = []
        for strike, contracts in strikes.items():
            parsed_strike = self._decimal(strike)
            if parsed_strike is None or not isinstance(contracts, dict):
                continue
            rows.append(
                {
                    "strike": parsed_strike,
                    "ce": self._option_leg(contracts.get("CE")),
                    "pe": self._option_leg(contracts.get("PE")),
                }
            )
        return tuple(sorted(rows, key=lambda row: row["strike"]))

    @classmethod
    def _option_leg(cls, value: object) -> dict[str, object] | None:
        if not isinstance(value, dict):
            return None
        greeks = value.get("greeks") if isinstance(value.get("greeks"), dict) else {}
        symbol = str(value.get("trading_symbol") or "").strip().upper()
        if not symbol:
            return None
        return {
            "trading_symbol": symbol,
            "ltp": cls._decimal(value.get("ltp")),
            "open_interest": cls._integer(value.get("open_interest")),
            "volume": cls._integer(value.get("volume")),
            "delta": cls._decimal(greeks.get("delta")),
            "gamma": cls._decimal(greeks.get("gamma")),
            "theta": cls._decimal(greeks.get("theta")),
            "vega": cls._decimal(greeks.get("vega")),
            "rho": cls._decimal(greeks.get("rho")),
            "iv": cls._decimal(greeks.get("iv")),
        }

    def _find_instrument(self, symbol: str) -> InterSignalInstrument | None:
        aliases = {
            "NIFTY_50": ("NIFTY_50", "NIFTY", "NSE-NIFTY"),
            "NIFTY_500": ("NIFTY_500", "NIFTY500", "NSE-NIFTY500"),
            "BANK_NIFTY": ("BANK_NIFTY", "BANKNIFTY", "NSE-BANKNIFTY"),
            "NIFTY_BANK": ("NIFTY_BANK", "BANKNIFTY", "NSE-BANKNIFTY"),
        }
        normalized = symbol.strip().upper().replace(" ", "_")
        candidates = aliases.get(normalized, (symbol,))
        for candidate in candidates:
            match = self.instrument_cache.find(candidate)
            if match:
                return match
        return None

    def _request(self, method_name: str, *, live_limit: bool = True, **kwargs: object) -> Any:
        if live_limit:
            self.rate_limiter.acquire()
        client = self.auth_service.get_client()
        try:
            method = getattr(client, method_name)
            with redirect_stdout(StringIO()):
                return method(**kwargs)
        except GrowwRateLimitError:
            raise
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None)
            if status_code == 429 or "429" in str(exc):
                raise GrowwRateLimitError() from None
            raise GrowwMarketDataError() from None

    @staticmethod
    def _payload(response: Any) -> Any:
        if isinstance(response, dict) and "payload" in response:
            return response["payload"]
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response

    def _normalize_quote(self, instrument: InterSignalInstrument, response: Any) -> MarketQuoteObservation:
        payload = self._payload(response)
        if not isinstance(payload, dict):
            raise GrowwMarketDataError()
        ohlc = payload.get("ohlc") if isinstance(payload.get("ohlc"), dict) else {}
        raw_depth = payload.get("depth") or payload.get("market_depth")
        depth = raw_depth if isinstance(raw_depth, dict) else {}
        raw_timestamp = payload.get("last_trade_time") or payload.get("timestamp")
        timestamp = self._timestamp(raw_timestamp) if raw_timestamp else self._last_message_at or self.clock().astimezone(timezone.utc)
        ltp = self._decimal(payload.get("last_price") or payload.get("ltp"))
        if ltp is None:
            raise GrowwMarketDataError()
        previous_close = self._decimal(ohlc.get("close") or payload.get("previous_close"))
        change = self._decimal(payload.get("day_change"))
        if change is None and previous_close is not None:
            change = ltp - previous_close
        change_pct = self._decimal(payload.get("day_change_perc") or payload.get("day_change_percentage"))
        session_status = self._session_status(
            payload.get("market_status") or payload.get("session_status"),
            timestamp,
        )
        return MarketQuoteObservation(
            instrument=instrument,
            timestamp=timestamp,
            ltp=ltp,
            change=change,
            change_pct=change_pct,
            open=self._decimal(ohlc.get("open") or payload.get("open")),
            high=self._decimal(ohlc.get("high") or payload.get("high")),
            low=self._decimal(ohlc.get("low") or payload.get("low")),
            close=self._decimal(ohlc.get("close") or payload.get("close")),
            previous_close=previous_close,
            volume=self._integer(payload.get("volume") or payload.get("total_traded_quantity")),
            bid=self._decimal(payload.get("bid_price")),
            ask=self._decimal(payload.get("offer_price") or payload.get("ask_price")),
            buy_depth=self._depth(depth.get("buy") or depth.get("buyBook") or depth.get("bids")),
            sell_depth=self._depth(depth.get("sell") or depth.get("sellBook") or depth.get("asks")),
            source=self.SOURCE,
            session_status=session_status,
        )

    def _session_status(self, raw_status: object, timestamp: datetime) -> str:
        normalized = str(raw_status or "").strip().upper()
        if normalized in {"OPEN", "LIVE"}:
            return "OPEN"
        if normalized in {"CLOSED", "CLOSE", "ENDED"}:
            return "CLOSED"
        india = ZoneInfo("Asia/Kolkata")
        now = self.clock().astimezone(india)
        observed = timestamp.astimezone(india)
        if now.weekday() >= 5 or observed.date() < now.date():
            return "CLOSED"
        within_session = time(9, 15) <= now.time().replace(tzinfo=None) <= time(15, 30)
        recent = abs((now - observed).total_seconds()) <= 900
        return "OPEN" if within_session and recent else "CLOSED"

    def _normalize_candle(self, row: Any) -> MarketCandleObservation | None:
        if isinstance(row, dict):
            values = (row.get("timestamp"), row.get("open"), row.get("high"), row.get("low"), row.get("close"), row.get("volume"), row.get("open_interest"))
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            padded = tuple(row[:7]) + (None,) * max(0, 7 - len(row))
            values = padded[:7]
        else:
            return None
        timestamp = self._timestamp(values[0])
        prices = tuple(self._decimal(value) for value in values[1:5])
        if any(value is None for value in prices):
            return None
        return MarketCandleObservation(
            timestamp=timestamp,
            open=prices[0],
            high=prices[1],
            low=prices[2],
            close=prices[3],
            volume=self._integer(values[5]),
            open_interest=self._integer(values[6]),
        )

    @staticmethod
    def _depth(value: Any) -> tuple[MarketDepthLevelObservation, ...]:
        rows = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
        normalized: list[MarketDepthLevelObservation] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = GrowwMarketDataProvider._decimal(row.get("price"))
            quantity = GrowwMarketDataProvider._integer(row.get("quantity") or row.get("qty"))
            if price is not None and quantity is not None:
                normalized.append(MarketDepthLevelObservation(price=price, quantity=quantity))
        return tuple(normalized[:10])

    def _timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            divisor = 1000 if value > 10_000_000_000 else 1
            return datetime.fromtimestamp(value / divisor, tz=timezone.utc)
        if value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return self.clock().astimezone(timezone.utc)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        decimal = GrowwMarketDataProvider._decimal(value)
        return int(decimal) if decimal is not None else None

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise GrowwProviderNotConfiguredError()


__all__ = ("GrowwMarketDataProvider",)

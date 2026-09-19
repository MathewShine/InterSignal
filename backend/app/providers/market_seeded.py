from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from functools import cached_property
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from app.providers.market_data import (
    InterSignalInstrument,
    MarketBreadthObservation,
    MarketCandleObservation,
    MarketDataProvider,
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


PRIMARY_INDEX = "NIFTY_500"
SUPPORTED_INDEXES = (PRIMARY_INDEX, "NIFTY_50")
SOURCE_NAME = "NSE_OFFICIAL_RECORDED_EOD"
PCT_QUANTUM = Decimal("0.0001")
INDIA_ZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class _DailyBar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    traded_value: Decimal | None


class SeededMarketDataProvider(MarketDataProvider):
    """Deterministic EOD provider backed only by recorded NSE project data."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)

    @property
    def provider_name(self) -> str:
        return "INTERSIGNAL_RECORDED_NSE"

    @property
    def mode(self) -> MarketProviderMode:
        return MarketProviderMode.SEEDED

    @property
    def capabilities(self) -> tuple[MarketProviderCapability, ...]:
        capabilities = [
            MarketProviderCapability.INSTRUMENT_MASTER,
            MarketProviderCapability.SEARCH,
            MarketProviderCapability.QUOTE,
            MarketProviderCapability.LTP,
            MarketProviderCapability.OHLC,
            MarketProviderCapability.HISTORICAL_CANDLES,
            MarketProviderCapability.INDICES,
            MarketProviderCapability.INDEX_SNAPSHOT,
            MarketProviderCapability.SESSION_STATUS,
        ]
        if self._constituent_path.exists():
            capabilities.append(MarketProviderCapability.CURRENT_UNIVERSE)
        if self._sector_index_path.exists():
            capabilities.extend((MarketProviderCapability.SECTORS, MarketProviderCapability.SECTOR_INDEX_CONTEXT))
        if self._daily_files:
            capabilities.extend(
                (
                    MarketProviderCapability.BREADTH,
                    MarketProviderCapability.VOLUME,
                    MarketProviderCapability.EOD_BREADTH,
                    MarketProviderCapability.EOD_VOLUME_CONTEXT,
                )
            )
        return tuple(capabilities)

    @cached_property
    def _benchmark_path(self) -> Path:
        return self.data_root / "reference/nse/indices/normalized/benchmark_daily.csv"

    @cached_property
    def _sector_index_path(self) -> Path:
        return self.data_root / "reference/nse/indices/normalized/sector_index_daily.csv"

    @cached_property
    def _sector_mapping_path(self) -> Path:
        return self.data_root / "reference/nse/indices/normalized/stock_sector_mapping.csv"

    @cached_property
    def _constituent_path(self) -> Path:
        current = self.data_root / "reference/nifty500/current/nifty500_constituents_normalized.csv"
        if current.exists():
            return current
        return self.data_root / "reference/nifty500/nifty500_constituents_normalized.csv"

    @cached_property
    def _calendar_path(self) -> Path:
        return self.data_root / "reference/nse/calendar/nse_cash_trading_calendar.csv"

    @cached_property
    def _daily_files(self) -> tuple[Path, ...]:
        root = self.data_root / "historical/daily/nse"
        if not root.exists():
            return ()
        return tuple(sorted(root.rglob("nse_daily_*.csv"), key=lambda path: path.name)[-21:])

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        if value is None or not value.strip():
            return None
        try:
            return Decimal(value.replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
        if denominator == 0:
            return None
        return ((numerator / denominator) * Decimal("100")).quantize(PCT_QUANTUM)

    @staticmethod
    def _market_close_timestamp(value: date) -> datetime:
        return datetime.combine(value, time(hour=15, minute=30), tzinfo=INDIA_ZONE)

    @cached_property
    def _benchmark_rows(self) -> dict[str, tuple[dict[str, str], ...]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._read_csv(self._benchmark_path):
            benchmark_id = row.get("benchmark_id", "").strip().upper()
            if benchmark_id in SUPPORTED_INDEXES and self._decimal(row.get("close")) is not None:
                grouped[benchmark_id].append(row)
        return {
            key: tuple(sorted(rows, key=lambda row: row["trading_date"]))
            for key, rows in grouped.items()
        }

    @cached_property
    def _members(self) -> tuple[dict[str, str], ...]:
        return tuple(
            row for row in self._read_csv(self._constituent_path)
            if row.get("symbol", "").strip()
        )

    @cached_property
    def _member_symbols(self) -> frozenset[str]:
        return frozenset(row["symbol"].strip().upper() for row in self._members)

    @cached_property
    def _daily_history(self) -> tuple[tuple[date, dict[str, _DailyBar]], ...]:
        sessions: list[tuple[date, dict[str, _DailyBar]]] = []
        for path in self._daily_files:
            rows = self._read_csv(path)
            if not rows:
                continue
            try:
                trading_date = date.fromisoformat(rows[0]["trading_date"])
            except (KeyError, ValueError):
                continue
            bars: dict[str, _DailyBar] = {}
            for row in rows:
                symbol = row.get("trading_symbol", "").strip().upper()
                if symbol not in self._member_symbols or row.get("series", "").strip().upper() != "EQ":
                    continue
                close = self._decimal(row.get("close"))
                open_ = self._decimal(row.get("open"))
                high = self._decimal(row.get("high"))
                low = self._decimal(row.get("low"))
                volume = self._decimal(row.get("volume"))
                if None in (open_, high, low, close, volume):
                    continue
                bars[symbol] = _DailyBar(
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    traded_value=self._decimal(row.get("traded_value")),
                )
            sessions.append((trading_date, bars))
        return tuple(sorted(sessions, key=lambda item: item[0]))

    @cached_property
    def _paired_changes(self) -> dict[str, Decimal]:
        if len(self._daily_history) < 2:
            return {}
        current = self._daily_history[-1][1]
        previous = self._daily_history[-2][1]
        return {
            symbol: current[symbol].close - previous[symbol].close
            for symbol in sorted(current.keys() & previous.keys())
            if previous[symbol].close > 0
        }

    @cached_property
    def _volume_ratios(self) -> dict[str, Decimal]:
        if len(self._daily_history) < 21:
            return {}
        current = self._daily_history[-1][1]
        prior_sessions = self._daily_history[-21:-1]
        ratios: dict[str, Decimal] = {}
        for symbol, bar in current.items():
            values = [rows[symbol].volume for _, rows in prior_sessions if symbol in rows]
            if len(values) != 20:
                continue
            baseline = median(values)
            if baseline > 0:
                ratios[symbol] = bar.volume / baseline
        return ratios

    def get_index_snapshot(self) -> tuple[MarketIndexObservation, ...]:
        observations: list[MarketIndexObservation] = []
        for benchmark_id in SUPPORTED_INDEXES:
            rows = self._benchmark_rows.get(benchmark_id, ())
            if not rows:
                continue
            latest = rows[-1]
            value = self._decimal(latest.get("close"))
            if value is None:
                continue
            previous_close = self._decimal(rows[-2].get("close")) if len(rows) > 1 else None
            change = value - previous_close if previous_close is not None else None
            observations.append(
                MarketIndexObservation(
                    symbol=benchmark_id,
                    name=latest.get("index_name", benchmark_id).strip() or benchmark_id,
                    value=value,
                    change=change,
                    change_pct=self._pct(change, previous_close) if change is not None and previous_close is not None else None,
                    previous_close=previous_close,
                    timestamp=self._market_close_timestamp(date.fromisoformat(latest["trading_date"])),
                    source=SOURCE_NAME,
                    open=self._decimal(latest.get("open")),
                    high=self._decimal(latest.get("high")),
                    low=self._decimal(latest.get("low")),
                )
            )
        return tuple(observations)

    def get_universe_snapshot(self) -> MarketUniverseObservation | None:
        if not self._members:
            return None
        source_dates = [row.get("source_date", "") for row in self._members if row.get("source_date")]
        if not source_dates:
            return None
        return MarketUniverseObservation(
            name="NIFTY 500",
            member_count=len(self._members),
            as_of_date=date.fromisoformat(max(source_dates)),
            membership_kind="CURRENT_EFFECTIVE_ONLY",
            source="NIFTY_INDICES_OFFICIAL_CONSTITUENT_SNAPSHOT",
        )

    def get_breadth_snapshot(self) -> MarketBreadthObservation | None:
        if not self._paired_changes:
            return None
        advancers = sum(change > 0 for change in self._paired_changes.values())
        decliners = sum(change < 0 for change in self._paired_changes.values())
        unchanged = len(self._paired_changes) - advancers - decliners
        count = len(self._paired_changes)
        expected = len(self._member_symbols)
        return MarketBreadthObservation(
            advancers=advancers,
            decliners=decliners,
            unchanged=unchanged,
            positive_pct=self._pct(Decimal(advancers), Decimal(count)) or Decimal("0"),
            negative_pct=self._pct(Decimal(decliners), Decimal(count)) or Decimal("0"),
            above_vwap_pct=None,
            above_prior_close_pct=self._pct(Decimal(advancers), Decimal(count)) or Decimal("0"),
            quality=MarketQualityObservation(
                coverage_count=count,
                expected_count=expected,
                missing_count=max(expected - count, 0),
            ),
        )

    @cached_property
    def _sector_members(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(self._sector_mapping_path):
            symbol = row.get("symbol", "").strip().upper()
            sector_id = row.get("sector_index_id", "").strip().upper()
            if symbol in self._member_symbols and sector_id:
                grouped[sector_id].append(symbol)
        return {key: tuple(sorted(set(symbols))) for key, symbols in grouped.items()}

    @cached_property
    def _sector_index_rows(self) -> dict[str, tuple[dict[str, str], ...]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self._read_csv(self._sector_index_path):
            sector_id = row.get("sector_index_id", "").strip().upper()
            if sector_id and self._decimal(row.get("close")) is not None:
                grouped[sector_id].append(row)
        return {
            key: tuple(sorted(rows, key=lambda row: row["trading_date"]))
            for key, rows in grouped.items()
        }

    def get_sector_snapshot(self) -> tuple[MarketSectorObservation, ...]:
        primary = next((row for row in self.get_index_snapshot() if row.symbol == PRIMARY_INDEX), None)
        primary_return = primary.change_pct if primary else None
        observations: list[MarketSectorObservation] = []
        for sector_id, rows in sorted(self._sector_index_rows.items()):
            if not rows:
                continue
            latest = rows[-1]
            latest_close = self._decimal(latest.get("close"))
            previous_close = self._decimal(rows[-2].get("close")) if len(rows) > 1 else None
            sector_return = None
            if latest_close is not None and previous_close is not None:
                sector_return = self._pct(latest_close - previous_close, previous_close)
            members = self._sector_members.get(sector_id, ())
            changes = [self._paired_changes[symbol] for symbol in members if symbol in self._paired_changes]
            advancers = sum(change > 0 for change in changes) if changes else None
            decliners = sum(change < 0 for change in changes) if changes else None
            unchanged = len(changes) - advancers - decliners if changes and advancers is not None and decliners is not None else None
            ratios = [self._volume_ratios[symbol] for symbol in members if symbol in self._volume_ratios]
            observations.append(
                MarketSectorObservation(
                    sector=latest.get("index_name", sector_id).strip() or sector_id,
                    return_pct=sector_return,
                    advancers=advancers,
                    decliners=decliners,
                    unchanged=unchanged,
                    breadth_pct=(
                        self._pct(Decimal(advancers), Decimal(len(changes)))
                        if advancers is not None and changes
                        else None
                    ),
                    relative_strength=(
                        (sector_return - primary_return).quantize(PCT_QUANTUM)
                        if sector_return is not None and primary_return is not None
                        else None
                    ),
                    volume_context=median(ratios).quantize(PCT_QUANTUM) if ratios else None,
                    quality=MarketQualityObservation(
                        coverage_count=len(changes),
                        expected_count=len(members),
                        missing_count=max(len(members) - len(changes), 0),
                    ),
                    index_value=latest_close,
                )
            )
        return tuple(observations)

    def get_volume_snapshot(self) -> MarketVolumeObservation | None:
        if not self._daily_history:
            return None
        current = self._daily_history[-1][1]
        traded_values = [bar.traded_value for bar in current.values() if bar.traded_value is not None]
        if not traded_values:
            return None
        ratios = tuple(self._volume_ratios.values())
        above_count = sum(value > 1 for value in ratios)
        expected = len(self._member_symbols)
        return MarketVolumeObservation(
            aggregate_traded_value=sum(traded_values, Decimal("0")),
            traded_value_unit="INR_LAKH",
            median_relative_volume=median(ratios).quantize(PCT_QUANTUM) if ratios else None,
            above_20d_volume_count=above_count,
            above_20d_volume_pct=(
                self._pct(Decimal(above_count), Decimal(len(ratios))) if ratios else None
            ),
            quality=MarketQualityObservation(
                coverage_count=len(ratios),
                expected_count=expected,
                missing_count=max(expected - len(ratios), 0),
            ),
        )

    def get_market_status(self) -> MarketSessionObservation | None:
        freshness = self.get_freshness()
        if freshness.source_timestamp is None:
            return None
        market_date = freshness.source_timestamp.astimezone(INDIA_ZONE).date()
        calendar_row = next(
            (
                row for row in self._read_csv(self._calendar_path)
                if row.get("trading_date") == market_date.isoformat()
            ),
            None,
        )
        status = "UNKNOWN"
        if calendar_row and calendar_row.get("session_type") == "NORMAL" and calendar_row.get("source_available") == "True":
            status = "CLOSED"
        return MarketSessionObservation(
            status=status,
            market_date=market_date,
            session_timestamp=freshness.source_timestamp,
        )

    def get_freshness(self) -> MarketFreshnessObservation:
        primary_rows = self._benchmark_rows.get(PRIMARY_INDEX, ())
        if not primary_rows:
            return MarketFreshnessObservation(source_timestamp=None)
        latest_date = date.fromisoformat(primary_rows[-1]["trading_date"])
        return MarketFreshnessObservation(source_timestamp=self._market_close_timestamp(latest_date))

    @cached_property
    def _instruments(self) -> tuple[InterSignalInstrument, ...]:
        members = tuple(
            InterSignalInstrument(
                instrument_id=f"NSE:CASH:{row['symbol'].strip().upper()}",
                symbol=row["symbol"].strip().upper(),
                display_name=row.get("company_name", "").strip() or row["symbol"].strip().upper(),
                exchange="NSE",
                segment="CASH",
                instrument_type="EQUITY",
                groww_symbol=f"NSE-{row['symbol'].strip().upper()}",
                series="EQ",
                isin=row.get("isin", "").strip() or None,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )
            for row in self._members
        )
        indices = tuple(
            InterSignalInstrument(
                instrument_id=f"NSE:INDEX:{symbol}",
                symbol=symbol,
                display_name=rows[-1].get("index_name", symbol).strip() or symbol,
                exchange="NSE",
                segment="CASH",
                instrument_type="INDEX",
                exchange_token=symbol.replace("_", ""),
                groww_symbol=f"NSE-{symbol.replace('_', '')}",
            )
            for symbol, rows in sorted(self._benchmark_rows.items())
            if rows
        )
        sector_indices = tuple(
            InterSignalInstrument(
                instrument_id=f"NSE:INDEX:{symbol}",
                symbol=symbol,
                display_name=rows[-1].get("index_name", symbol).strip() or symbol,
                exchange="NSE",
                segment="CASH",
                instrument_type="INDEX",
                exchange_token=symbol.replace("_", ""),
                groww_symbol=f"NSE-{symbol.replace('_', '')}",
            )
            for symbol, rows in sorted(self._sector_index_rows.items())
            if rows and symbol not in self._benchmark_rows
        )
        return tuple(sorted((*indices, *sector_indices, *members), key=lambda item: (item.instrument_type != "INDEX", item.symbol)))

    def list_instruments(self) -> tuple[InterSignalInstrument, ...]:
        return self._instruments

    @staticmethod
    def _canonical_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {"NIFTY50": "NIFTY_50", "NIFTY500": "NIFTY_500", "NIFTY": "NIFTY_50"}
        return aliases.get(normalized, normalized)

    def _instrument(self, symbol: str) -> InterSignalInstrument | None:
        canonical = self._canonical_symbol(symbol)
        return next((item for item in self._instruments if item.symbol == canonical), None)

    def get_quote(self, symbol: str) -> MarketQuoteObservation | None:
        instrument = self._instrument(symbol)
        if instrument is None:
            return None
        if instrument.instrument_type == "INDEX":
            rows = self._benchmark_rows.get(instrument.symbol, ()) or self._sector_index_rows.get(instrument.symbol, ())
            if not rows:
                return None
            latest = rows[-1]
            close = self._decimal(latest.get("close"))
            previous_close = self._decimal(rows[-2].get("close")) if len(rows) > 1 else None
            if close is None:
                return None
            change = close - previous_close if previous_close is not None else None
            return MarketQuoteObservation(
                instrument=instrument,
                timestamp=self._market_close_timestamp(date.fromisoformat(latest["trading_date"])),
                ltp=close,
                change=change,
                change_pct=self._pct(change, previous_close) if change is not None and previous_close else None,
                open=self._decimal(latest.get("open")),
                high=self._decimal(latest.get("high")),
                low=self._decimal(latest.get("low")),
                close=close,
                previous_close=previous_close,
                source=SOURCE_NAME,
                session_status="CLOSED",
            )
        history = [(session, bars[instrument.symbol]) for session, bars in self._daily_history if instrument.symbol in bars]
        if not history:
            return None
        trading_date, latest = history[-1]
        previous_close = history[-2][1].close if len(history) > 1 else None
        change = latest.close - previous_close if previous_close is not None else None
        return MarketQuoteObservation(
            instrument=instrument,
            timestamp=self._market_close_timestamp(trading_date),
            ltp=latest.close,
            change=change,
            change_pct=self._pct(change, previous_close) if change is not None and previous_close else None,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            close=latest.close,
            previous_close=previous_close,
            volume=int(latest.volume),
            source=SOURCE_NAME,
            session_status="CLOSED",
        )

    def get_candles(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> tuple[MarketCandleObservation, ...]:
        if interval not in {"1d", "day", "daily"}:
            return ()
        instrument = self._instrument(symbol)
        if instrument is None:
            return ()
        rows: list[MarketCandleObservation] = []
        if instrument.instrument_type == "INDEX":
            source_rows = self._benchmark_rows.get(instrument.symbol, ()) or self._sector_index_rows.get(instrument.symbol, ())
            for row in source_rows:
                trading_date = date.fromisoformat(row["trading_date"])
                timestamp = self._market_close_timestamp(trading_date)
                values = tuple(self._decimal(row.get(name)) for name in ("open", "high", "low", "close"))
                if timestamp < start or timestamp > end or any(value is None for value in values):
                    continue
                rows.append(MarketCandleObservation(timestamp, values[0], values[1], values[2], values[3]))
            return tuple(rows)
        for trading_date, bars in self._daily_history:
            bar = bars.get(instrument.symbol)
            timestamp = self._market_close_timestamp(trading_date)
            if bar and start <= timestamp <= end:
                rows.append(
                    MarketCandleObservation(
                        timestamp=timestamp,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=int(bar.volume),
                    )
                )
        return tuple(rows)

    def get_sector_constituents(self, sector_id: str) -> tuple[InterSignalInstrument, ...]:
        normalized = sector_id.strip().upper().replace("-", "_").replace(" ", "_")
        symbols = self._sector_members.get(normalized, ())
        if not symbols:
            match = next(
                (
                    key for key, rows in self._sector_index_rows.items()
                    if rows and rows[-1].get("index_name", "").strip().upper().replace(" ", "_") == normalized
                ),
                None,
            )
            symbols = self._sector_members.get(match or "", ())
        by_symbol = {item.symbol: item for item in self._instruments}
        return tuple(by_symbol[symbol] for symbol in symbols if symbol in by_symbol)


__all__ = ("SeededMarketDataProvider",)

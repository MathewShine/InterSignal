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
    MarketBreadthObservation,
    MarketDataProvider,
    MarketFreshnessObservation,
    MarketIndexObservation,
    MarketProviderMode,
    MarketQualityObservation,
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
    def capabilities(self) -> tuple[str, ...]:
        capabilities = ["INDEX_SNAPSHOT", "SESSION_STATUS"]
        if self._constituent_path.exists():
            capabilities.append("CURRENT_UNIVERSE")
        if self._sector_index_path.exists():
            capabilities.append("SECTOR_INDEX_CONTEXT")
        if self._daily_files:
            capabilities.extend(("EOD_BREADTH", "EOD_VOLUME_CONTEXT"))
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
                volume = self._decimal(row.get("volume"))
                if close is None or volume is None:
                    continue
                bars[symbol] = _DailyBar(
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


__all__ = ("SeededMarketDataProvider",)

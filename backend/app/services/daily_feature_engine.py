from __future__ import annotations

import csv
import gzip
import json
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.features import breakout_context, daily, liquidity, momentum, volatility
from app.features.base import (
    AVAILABILITY_TIME,
    NEXT_SESSION_DECISION_INPUT,
    STATUS_BENCHMARK_UNAVAILABLE,
    STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED,
    STATUS_INSUFFICIENT_HISTORY,
    STATUS_INVALID_SOURCE_ROW,
    STATUS_MISSING_INPUT_DATA,
    STATUS_NOT_APPLICABLE,
    STATUS_READY,
    STATUS_SECTOR_CONTEXT_UNAVAILABLE,
    STATUS_SECTOR_MAPPING_UNAVAILABLE,
    TIMEFRAME,
    AdjustedDailyBar,
    DailyFeatureConfig,
    mean_decimal,
    median_decimal,
    parse_decimal,
    safe_divide,
    sample_stdev_decimal,
    simple_return,
)
from app.features.registry import FEATURE_GROUPS, FEATURE_OUTPUT_FIELDS
from app.features.relative_strength import LocalOfficialIndexContextProvider, resolve_relative_strength_context_provider
from app.providers.indices.base import (
    ALLOWED_SECTOR_MAPPING_STATUSES,
    PRIMARY_BENCHMARK_ID,
    SECONDARY_BENCHMARK_ID,
)
from app.services.corporate_actions import METHODOLOGY_VERSION, fingerprint_directory
from app.services.nifty500_ca_final_readiness import (
    EXCLUSION_POLICY_VERSION,
    intervals_overlap,
    lookback_start_date,
)
from app.services.nifty500_membership import canonical_symbol


PILOT_SYMBOLS = (
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "SUNPHARMA",
    "360ONE",
    "3MINDIA",
    "INFIBEAM",
    "AADHARHFC",
)

QUALITY_SUMMARY_FIELDS = ["metric", "value", "notes"]
RELATIVE_STRENGTH_QUALITY_FIELDS = ["metric", "value", "notes"]
PILOT_VALIDATION_FIELDS = ["symbol", "trading_date", "feature", "calculated", "expected", "difference", "tolerance", "result"]
USABILITY_SCENARIOS = (5, 20, 60, 200)
DECIMAL_OUTPUT_QUANT = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class DailyFeatureEngineConfig:
    data_dir: Path
    start_date: date
    end_date: date
    feature_config: DailyFeatureConfig = DailyFeatureConfig()
    full_generation: bool = True

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.data_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def raw_daily_dir(self) -> Path:
        return self.data_dir / "raw" / "nse" / "daily"

    @property
    def normalized_daily_dir(self) -> Path:
        return self.data_dir / "historical" / "daily" / "nse"

    @property
    def membership_periods_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "history" / "membership_periods.csv"

    @property
    def membership_coverage_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "history" / "membership_coverage.json"

    @property
    def current_constituents_path(self) -> Path:
        return self.data_dir / "reference" / "nifty500" / "current" / "nifty500_constituents_normalized.csv"

    @property
    def eligibility_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "corporate_actions" / "research_eligibility.csv"

    @property
    def calendar_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"

    @property
    def features_dir(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1"

    @property
    def feature_dataset_path(self) -> Path:
        return self.features_dir / "daily_features_v1.csv.gz"

    @property
    def pilot_dataset_path(self) -> Path:
        return self.features_dir / "daily_features_v1_pilot.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "daily_feature_engine_summary.json"

    @property
    def quality_summary_path(self) -> Path:
        return self.reports_dir / "daily_feature_quality_summary.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "daily_feature_pilot_validation.csv"

    @property
    def relative_strength_quality_path(self) -> Path:
        return self.reports_dir / "relative_strength_feature_quality.csv"

    @property
    def benchmark_context_summary_path(self) -> Path:
        return self.reports_dir / "benchmark_context_summary.json"

    @property
    def sector_context_summary_path(self) -> Path:
        return self.reports_dir / "sector_context_summary.json"


@dataclass(frozen=True, slots=True)
class MembershipPeriod:
    symbol: str
    isin: str
    valid_from: date
    valid_to: date | None
    reconstruction_method: str
    source_confidence: str
    provenance: str


@dataclass(frozen=True, slots=True)
class WindowState:
    status: str
    reason_codes: tuple[str, ...] = ()
    blocking_events: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SymbolFeatureCache:
    values: dict[str, list[Any]]

    def get(self, field: str, index: int) -> Any:
        return self.values[field][index]


class Nifty500MembershipIndex:
    def __init__(self, periods: Sequence[MembershipPeriod]) -> None:
        grouped: dict[str, list[MembershipPeriod]] = defaultdict(list)
        for period in periods:
            grouped[period.symbol].append(period)
        self.grouped = {symbol: sorted(rows, key=lambda row: row.valid_from) for symbol, rows in grouped.items()}

    def period_for(self, symbol: str, as_of_date: date) -> MembershipPeriod | None:
        normalized = canonical_symbol(symbol)
        for period in self.grouped.get(normalized, []):
            if period.valid_from <= as_of_date and (period.valid_to is None or as_of_date <= period.valid_to):
                return period
        return None

    def members_for(self, as_of_date: date) -> dict[str, MembershipPeriod]:
        members: dict[str, MembershipPeriod] = {}
        for symbol, periods in self.grouped.items():
            for period in periods:
                if period.valid_from <= as_of_date and (period.valid_to is None or as_of_date <= period.valid_to):
                    members[symbol] = period
                    break
        return members


class ResearchEligibilityIndex:
    def __init__(self, rows: Sequence[dict[str, str]], trading_sessions: Sequence[date]) -> None:
        self.trading_sessions = tuple(sorted(trading_sessions))
        self.blockers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("eligibility_status") not in {
                "EXCLUDE_CORPORATE_ACTION_WINDOW",
                "EXCLUDE_SECURITY_RANGE",
                "MANUAL_REVIEW_REQUIRED",
            }:
                continue
            start = parse_date(row.get("start_date"))
            end = parse_date(row.get("end_date"))
            if start is None or end is None:
                continue
            self.blockers[canonical_symbol(row.get("symbol", ""))].append(
                {
                    "start": start,
                    "end": end,
                    "reason_code": row.get("reason_code", ""),
                    "source_event_id": row.get("source_event_id", ""),
                    "confidence": row.get("confidence", ""),
                }
            )

    def check(self, *, symbol: str, as_of_date: date, lookback_sessions: int = 0) -> dict[str, Any]:
        window_start = lookback_start_date(as_of_date, lookback_sessions, self.trading_sessions)
        blockers = [
            row
            for row in self.blockers.get(canonical_symbol(symbol), [])
            if intervals_overlap(window_start, as_of_date, row["start"], row["end"])
        ]
        return {
            "eligible": not blockers,
            "status": "ELIGIBLE" if not blockers else "INELIGIBLE",
            "reason_codes": sorted({row["reason_code"] for row in blockers if row["reason_code"]}),
            "blocking_events": sorted({row["source_event_id"] for row in blockers if row["source_event_id"]}),
            "confidence": "HIGH" if not blockers else ",".join(sorted({row["confidence"] for row in blockers if row["confidence"]})),
            "lookback_start_date": window_start.isoformat(),
            "as_of_date": as_of_date.isoformat(),
        }


class FeatureRowBuilder:
    def __init__(
        self,
        *,
        bars: Sequence[AdjustedDailyBar],
        index: int,
        membership: MembershipPeriod,
        membership_status: str,
        universe_version: str,
        sector: str,
        feature_cache: SymbolFeatureCache,
        eligibility_index: ResearchEligibilityIndex,
        trading_sessions: Sequence[date],
        trading_session_index: dict[date, int],
        feature_config: DailyFeatureConfig,
        relative_strength_context: LocalOfficialIndexContextProvider,
    ) -> None:
        self.bars = bars
        self.index = index
        self.bar = bars[index]
        self.membership = membership
        self.membership_status = membership_status
        self.universe_version = universe_version
        self.sector = sector
        self.feature_cache = feature_cache
        self.eligibility_index = eligibility_index
        self.trading_sessions = trading_sessions
        self.session_index = trading_session_index
        self.feature_config = feature_config
        self.relative_strength_context = relative_strength_context
        self.states: dict[int, WindowState] = {}
        self.row: dict[str, Any] = {}
        self.group_status: dict[str, str] = {
            "returns": STATUS_READY,
            "momentum": STATUS_READY,
            "liquidity": STATUS_READY,
            "relative_volume": STATUS_READY,
            "volatility": STATUS_READY,
            "levels": STATUS_READY,
            "trend": STATUS_READY,
            "candle": STATUS_READY,
            "consolidation": STATUS_READY,
            "benchmark": STATUS_READY if relative_strength_context.is_available() else STATUS_BENCHMARK_UNAVAILABLE,
            "sector": STATUS_READY if relative_strength_context.sector_context_available() else STATUS_SECTOR_CONTEXT_UNAVAILABLE,
        }
        self.null_reasons: set[str] = set()
        self.eligibility_reasons: set[str] = set()
        self.blocking_events: set[str] = set()

    def build(self) -> dict[str, Any]:
        self.row.update(self.identity_fields())
        self.row.update({field: None for fields in FEATURE_GROUPS.values() for field in fields})

        base_state = self.window_state(0)
        if base_state.status != STATUS_READY:
            self.mark_all_local_groups(base_state.status)
            self.add_state_reason("row", base_state)
        else:
            self.compute_returns()
            self.compute_momentum()
            self.compute_liquidity()
            self.compute_relative_volume()
            atr_values = self.compute_volatility()
            level_values = self.compute_levels()
            self.compute_trend()
            self.compute_candle()
            self.compute_consolidation(atr_values, level_values)

        self.compute_benchmark()
        self.compute_sector()
        self.finish_status_fields()
        return self.row

    def identity_fields(self) -> dict[str, Any]:
        return {
            "trading_date": self.bar.trading_date,
            "symbol": self.bar.symbol,
            "isin": self.bar.isin or self.membership.isin,
            "universe_name": self.feature_config.universe_name,
            "universe_membership_status": self.membership_status,
            "universe_membership_confidence": self.membership.source_confidence,
            "universe_membership_source": self.membership.provenance,
            "universe_version": self.universe_version,
            "sector": self.sector,
            "sector_metadata_status": "CURRENT_SNAPSHOT_ONLY_NOT_USED_FOR_HISTORY" if self.sector else "UNAVAILABLE",
            "feature_date": self.bar.trading_date,
            "availability_time": AVAILABILITY_TIME,
            "decision_input_time": NEXT_SESSION_DECISION_INPUT,
            "timeframe": TIMEFRAME,
            "feature_version": self.feature_config.feature_version,
            "adjustment_methodology": self.bar.adjustment_methodology_version,
            "exclusion_policy": EXCLUSION_POLICY_VERSION,
            "source_dataset": self.feature_config.source_dataset,
            "source_file": self.bar.source_file,
            "source_completeness_status": self.bar.research_usability_status,
            "traded_value_method": self.feature_config.traded_value_method,
            "atr_methodology": self.feature_config.atr_methodology,
            "volatility_methodology": self.feature_config.volatility_methodology,
            "benchmark_context_version": self.feature_config.benchmark_context_version,
            "sector_context_version": self.feature_config.sector_context_version,
        }

    def window_state(self, lookback: int) -> WindowState:
        if lookback in self.states:
            return self.states[lookback]
        current_date = self.bar.trading_date
        current_session_index = self.session_index.get(current_date)
        if current_session_index is None:
            state = WindowState(STATUS_MISSING_INPUT_DATA, ("trading_session_missing",))
        elif current_session_index < lookback or self.index < lookback:
            state = WindowState(STATUS_INSUFFICIENT_HISTORY, (f"requires_{lookback}_prior_sessions",))
        elif self.bars[self.index - lookback].trading_date != self.trading_sessions[current_session_index - lookback]:
            state = WindowState(STATUS_MISSING_INPUT_DATA, ("missing_trading_session_in_window",))
        else:
            eligibility = self.eligibility_index.check(
                symbol=self.bar.symbol,
                as_of_date=current_date,
                lookback_sessions=lookback,
            )
            if not eligibility["eligible"]:
                state = WindowState(
                    STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED,
                    tuple(eligibility["reason_codes"]),
                    tuple(eligibility["blocking_events"]),
                )
            else:
                state = WindowState(STATUS_READY)
        self.states[lookback] = state
        return state

    def assign(self, group: str, field: str, lookback: int, value: Any) -> bool:
        state = self.window_state(lookback)
        if state.status != STATUS_READY:
            self.row[field] = None
            self.promote_group_status(group, state.status)
            self.add_state_reason(field, state)
            return False
        if value is None:
            self.row[field] = None
            self.promote_group_status(group, STATUS_MISSING_INPUT_DATA)
            self.null_reasons.add(f"{field}:{STATUS_MISSING_INPUT_DATA}")
            return False
        self.row[field] = value
        return True

    def compute_returns(self) -> None:
        for window in self.feature_config.return_windows:
            value = self.feature_cache.get(f"return_{window}d", self.index)
            self.assign("returns", f"return_{window}d", window, value)

    def compute_momentum(self) -> None:
        for window in self.feature_config.momentum_windows:
            value = self.feature_cache.get(f"momentum_{window}d", self.index)
            self.assign("momentum", f"momentum_{window}d", window, value)
        for window in self.feature_config.positive_day_windows:
            count = self.feature_cache.get(f"positive_days_{window}", self.index)
            self.assign("momentum", f"positive_days_{window}", window, count)
            ratio = self.feature_cache.get(f"up_days_ratio_{window}", self.index)
            self.assign("momentum", f"up_days_ratio_{window}", window, ratio)

    def compute_liquidity(self) -> None:
        self.assign("liquidity", "daily_traded_value", 0, self.feature_cache.get("daily_traded_value", self.index))
        for window in self.feature_config.volume_windows:
            median_value = self.feature_cache.get(f"median_traded_value_{window}d", self.index)
            self.assign("liquidity", f"median_traded_value_{window}d", window, median_value)
            avg_volume = self.feature_cache.get(f"avg_volume_{window}d", self.index)
            self.assign("liquidity", f"avg_volume_{window}d", window, avg_volume)

    def compute_relative_volume(self) -> None:
        for window in self.feature_config.relative_volume_windows:
            value = self.feature_cache.get(f"relative_volume_{window}d", self.index)
            self.assign("relative_volume", f"relative_volume_{window}d", window, value)

    def compute_volatility(self) -> dict[int, Decimal | None]:
        true_range = self.feature_cache.get("true_range", self.index)
        self.assign("volatility", "true_range", 1, true_range)
        atr_values: dict[int, Decimal | None] = {}
        for window in self.feature_config.atr_windows:
            value = self.feature_cache.get(f"atr_{window}", self.index)
            atr_values[window] = value
            self.assign("volatility", f"atr_{window}", window, value)
        self.assign("volatility", "atr_percent_14", 14, self.feature_cache.get("atr_percent_14", self.index))
        for window in self.feature_config.volatility_windows:
            value = self.feature_cache.get(f"return_volatility_{window}d", self.index)
            self.assign("volatility", f"return_volatility_{window}d", window, value)
        return atr_values

    def compute_levels(self) -> dict[str, Decimal | None]:
        levels: dict[str, Decimal | None] = {}
        for window in self.feature_config.level_windows:
            label = level_label(window)
            high_value = self.feature_cache.get(f"high_{label}", self.index)
            low_value = self.feature_cache.get(f"low_{label}", self.index)
            levels[f"high_{label}"] = high_value
            levels[f"low_{label}"] = low_value
            self.assign("levels", f"high_{label}", window, high_value)
            self.assign("levels", f"low_{label}", window, low_value)
        for window in self.feature_config.prior_level_windows:
            label = level_label(window)
            high_value = self.feature_cache.get(f"prior_high_{label}", self.index)
            low_value = self.feature_cache.get(f"prior_low_{label}", self.index)
            levels[f"prior_high_{label}"] = high_value
            levels[f"prior_low_{label}"] = low_value
            self.assign("levels", f"prior_high_{label}", window, high_value)
            if window in {5, 20}:
                self.assign("levels", f"prior_low_{label}", window, low_value)
            distance = self.feature_cache.get(f"distance_to_prior_{label}_high_pct", self.index)
            self.assign("levels", f"distance_to_prior_{label}_high_pct", window, distance)
        return levels

    def compute_trend(self) -> None:
        sma_values: dict[int, Decimal | None] = {}
        for window in self.feature_config.sma_windows:
            value = self.feature_cache.get(f"sma_{window}", self.index)
            sma_values[window] = value
            self.assign("trend", f"sma_{window}", window, value)
        for window in (20, 50, 200):
            distance = self.feature_cache.get(f"distance_from_sma_{window}_pct", self.index)
            self.assign("trend", f"distance_from_sma_{window}_pct", window, distance)

    def compute_candle(self) -> None:
        for field in FEATURE_GROUPS["candle"]:
            if field == "gap_open_pct":
                continue
            value = self.feature_cache.get(field, self.index)
            assigned = self.assign("candle", field, 0, value)
            if field == "close_location_value" and not assigned and self.bar.high == self.bar.low:
                self.null_reasons.add("close_location_value:ZERO_RANGE_CANDLE")
        self.assign("candle", "gap_open_pct", 1, self.feature_cache.get("gap_open_pct", self.index))

    def compute_consolidation(self, atr_values: dict[int, Decimal | None], levels: dict[str, Decimal | None]) -> None:
        for window in self.feature_config.range_windows:
            value = self.feature_cache.get(f"range_width_{window}d_pct", self.index)
            self.assign("consolidation", f"range_width_{window}d_pct", window, value)
        self.assign("consolidation", "above_prior_5d_high", 5, self.feature_cache.get("above_prior_5d_high", self.index))
        self.assign("consolidation", "above_prior_20d_high", 20, self.feature_cache.get("above_prior_20d_high", self.index))
        self.assign("consolidation", "above_prior_52w_high", 252, self.feature_cache.get("above_prior_52w_high", self.index))
        self.assign("consolidation", "intraday_high_above_prior_20d_high", 20, self.feature_cache.get("intraday_high_above_prior_20d_high", self.index))
        self.assign("consolidation", "atr_contraction_ratio", 20, self.feature_cache.get("atr_contraction_ratio", self.index))

    def compute_benchmark(self) -> None:
        primary_id = self.feature_config.primary_benchmark_id
        secondary_id = self.feature_config.secondary_benchmark_id
        self.row["benchmark_symbol"] = primary_id
        self.row["primary_benchmark_id"] = primary_id
        self.row["secondary_benchmark_id"] = secondary_id

        if not self.relative_strength_context.is_available():
            self.group_status["benchmark"] = STATUS_BENCHMARK_UNAVAILABLE
            self.null_reasons.add("benchmark_relative_strength:BENCHMARK_UNAVAILABLE")
            return

        for window in self.feature_config.benchmark_return_windows:
            field = f"benchmark_return_{window}d"
            value = self.relative_strength_context.benchmark_return_for(primary_id, self.bar.trading_date, window)
            self.row[field] = value
            if value is None:
                self.promote_group_status("benchmark", STATUS_MISSING_INPUT_DATA)
                self.null_reasons.add(f"{field}:{STATUS_MISSING_INPUT_DATA}")

        for window in self.feature_config.benchmark_relative_windows:
            self.assign_benchmark_relative(
                field=f"relative_return_{window}d_vs_nifty500",
                window=window,
                benchmark_id=primary_id,
            )

        for window in self.feature_config.secondary_benchmark_windows:
            field = f"nifty50_return_{window}d"
            value = self.relative_strength_context.benchmark_return_for(secondary_id, self.bar.trading_date, window)
            self.row[field] = value
            if value is None:
                self.promote_group_status("benchmark", STATUS_MISSING_INPUT_DATA)
                self.null_reasons.add(f"{field}:{STATUS_MISSING_INPUT_DATA}")
            self.assign_benchmark_relative(
                field=f"relative_return_{window}d_vs_nifty50",
                window=window,
                benchmark_id=secondary_id,
            )

        self.row["relative_return_5d_vs_benchmark"] = self.row.get("relative_return_5d_vs_nifty500")
        self.row["relative_return_20d_vs_benchmark"] = self.row.get("relative_return_20d_vs_nifty500")

    def compute_sector(self) -> None:
        mapping = self.relative_strength_context.sector_mapping_for(self.bar.symbol, self.bar.trading_date)
        self.row["sector_index_id"] = mapping.sector_index_id or None
        self.row["sector_index_name"] = (
            self.relative_strength_context.sector_index_name(mapping.sector_index_id)
            if mapping.sector_index_id
            else None
        )
        self.row["sector_mapping_status"] = mapping.mapping_status
        self.row["sector_mapping_confidence"] = mapping.confidence
        self.row["sector_mapping_source"] = mapping.mapping_source

        if not self.relative_strength_context.sector_context_available():
            self.group_status["sector"] = STATUS_SECTOR_CONTEXT_UNAVAILABLE
            self.null_reasons.add("sector_relative_features:SECTOR_CONTEXT_UNAVAILABLE")
            return

        if mapping.mapping_status not in ALLOWED_SECTOR_MAPPING_STATUSES or not mapping.sector_index_id:
            self.group_status["sector"] = STATUS_SECTOR_MAPPING_UNAVAILABLE
            self.null_reasons.add(f"sector_relative_features:{mapping.mapping_status}_MAPPING_NOT_USED")
            self.row["sector_momentum_available"] = False
            return

        for window in self.feature_config.sector_return_windows:
            field = f"sector_return_{window}d"
            value = self.relative_strength_context.sector_return_for(mapping.sector_index_id, self.bar.trading_date, window)
            self.row[field] = value
            if value is None:
                self.promote_group_status("sector", STATUS_MISSING_INPUT_DATA)
                self.null_reasons.add(f"{field}:{STATUS_MISSING_INPUT_DATA}")
            self.assign_sector_relative(
                field=f"relative_return_{window}d_vs_sector",
                window=window,
                sector_return=value,
            )

        for window in (1, 5, 20):
            self.row[f"sector_index_return_{window}d"] = self.row.get(f"sector_return_{window}d")
        self.row["sector_above_sma20"] = self.relative_strength_context.sector_above_sma20(
            mapping.sector_index_id,
            self.bar.trading_date,
        )
        self.row["sector_momentum_available"] = all(
            self.row.get(f"sector_return_{window}d") is not None for window in (1, 5, 20)
        )

    def assign_benchmark_relative(self, *, field: str, window: int, benchmark_id: str) -> None:
        state = self.window_state(window)
        if state.status != STATUS_READY:
            self.row[field] = None
            self.promote_group_status("benchmark", state.status)
            self.add_state_reason(field, state)
            return
        stock_return = self.feature_cache.get(f"return_{window}d", self.index)
        benchmark_return = self.relative_strength_context.benchmark_return_for(benchmark_id, self.bar.trading_date, window)
        if stock_return is None:
            self.row[field] = None
            self.promote_group_status("benchmark", STATUS_MISSING_INPUT_DATA)
            self.null_reasons.add(f"{field}:STOCK_RETURN_UNAVAILABLE")
            return
        if benchmark_return is None:
            self.row[field] = None
            self.promote_group_status("benchmark", STATUS_MISSING_INPUT_DATA)
            self.null_reasons.add(f"{field}:BENCHMARK_RETURN_UNAVAILABLE")
            return
        self.row[field] = stock_return - benchmark_return

    def assign_sector_relative(self, *, field: str, window: int, sector_return: Decimal | None) -> None:
        state = self.window_state(window)
        if state.status != STATUS_READY:
            self.row[field] = None
            self.promote_group_status("sector", state.status)
            self.add_state_reason(field, state)
            return
        stock_return = self.feature_cache.get(f"return_{window}d", self.index)
        if stock_return is None:
            self.row[field] = None
            self.promote_group_status("sector", STATUS_MISSING_INPUT_DATA)
            self.null_reasons.add(f"{field}:STOCK_RETURN_UNAVAILABLE")
            return
        if sector_return is None:
            self.row[field] = None
            self.promote_group_status("sector", STATUS_MISSING_INPUT_DATA)
            self.null_reasons.add(f"{field}:SECTOR_RETURN_UNAVAILABLE")
            return
        self.row[field] = stock_return - sector_return

    def finish_status_fields(self) -> None:
        local_statuses = [
            self.group_status[group]
            for group in (
                "returns",
                "momentum",
                "liquidity",
                "relative_volume",
                "volatility",
                "levels",
                "trend",
                "candle",
                "consolidation",
            )
        ]
        self.row["feature_status"] = aggregate_status(local_statuses)
        self.row["feature_null_reasons"] = ";".join(sorted(self.null_reasons))
        self.row["eligibility_reason_codes"] = ";".join(sorted(self.eligibility_reasons))
        self.row["blocking_events"] = ";".join(sorted(self.blocking_events))
        for group, status in self.group_status.items():
            self.row[f"{group}_status"] = status

    def mark_all_local_groups(self, status: str) -> None:
        for group in (
            "returns",
            "momentum",
            "liquidity",
            "relative_volume",
            "volatility",
            "levels",
            "trend",
            "candle",
            "consolidation",
        ):
            self.group_status[group] = status

    def add_state_reason(self, field: str, state: WindowState) -> None:
        if state.reason_codes:
            for reason in state.reason_codes:
                self.null_reasons.add(f"{field}:{state.status}:{reason}")
                if state.status == STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED:
                    self.eligibility_reasons.add(reason)
        else:
            self.null_reasons.add(f"{field}:{state.status}")
        self.blocking_events.update(state.blocking_events)

    def promote_group_status(self, group: str, status: str) -> None:
        if status_priority(status) > status_priority(self.group_status[group]):
            self.group_status[group] = status


def build_daily_feature_engine(*, config: DailyFeatureEngineConfig, progress: Any | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    raw_before = fingerprint_directory(config.raw_daily_dir)
    adjusted_before = fingerprint_directory(config.adjusted_daily_dir)

    membership_coverage = load_json(config.membership_coverage_path)
    membership_status = membership_coverage.get("survivorship_bias_status", "PARTIAL_HISTORY")
    universe_version = membership_coverage.get("phase", config.feature_config.universe_version)
    periods = load_membership_periods(config.membership_periods_path)
    membership_index = Nifty500MembershipIndex(periods)
    trading_sessions = load_trading_sessions(config.calendar_path, config.start_date, config.end_date)
    eligibility_index = ResearchEligibilityIndex(read_csv(config.eligibility_path), trading_sessions)
    sector_lookup = load_sector_lookup(config.current_constituents_path)
    relative_strength_context = resolve_relative_strength_context_provider(config.data_dir, trading_sessions)

    if progress:
        progress("Loading adjusted point-in-time Nifty 500 bars")
    bars_by_symbol, load_summary = load_adjusted_nifty500_bars(
        adjusted_daily_dir=config.adjusted_daily_dir,
        membership_index=membership_index,
        start_date=config.start_date,
        end_date=config.end_date,
        trading_sessions=trading_sessions,
    )

    if progress:
        progress("Running pilot feature generation")
    pilot_rows = list(
        iter_feature_rows(
            bars_by_symbol=bars_by_symbol,
            membership_index=membership_index,
            membership_status=membership_status,
            universe_version=universe_version,
            sector_lookup=sector_lookup,
            eligibility_index=eligibility_index,
            trading_sessions=trading_sessions,
            feature_config=config.feature_config,
            relative_strength_context=relative_strength_context,
            symbols=PILOT_SYMBOLS,
        )
    )
    write_feature_rows(config.pilot_dataset_path, pilot_rows)
    pilot_validation = validate_pilot_rows(pilot_rows, bars_by_symbol, relative_strength_context)
    write_csv(config.pilot_validation_path, pilot_validation["rows"], PILOT_VALIDATION_FIELDS)

    full_result = empty_generation_result(config.feature_dataset_path)
    full_generation_completed = False
    if config.full_generation and pilot_validation["passed"]:
        if progress:
            progress("Generating full DAILY_FEATURES_V1 dataset")
        full_result = write_full_feature_dataset(
            path=config.feature_dataset_path,
            bars_by_symbol=bars_by_symbol,
            membership_index=membership_index,
            membership_status=membership_status,
            universe_version=universe_version,
            sector_lookup=sector_lookup,
            eligibility_index=eligibility_index,
            trading_sessions=trading_sessions,
            feature_config=config.feature_config,
            relative_strength_context=relative_strength_context,
        )
        full_generation_completed = True

    quality_rows = quality_summary_rows(full_result)
    write_csv(config.quality_summary_path, quality_rows, QUALITY_SUMMARY_FIELDS)
    write_csv(config.relative_strength_quality_path, relative_strength_quality_rows(full_result), RELATIVE_STRENGTH_QUALITY_FIELDS)

    raw_after = fingerprint_directory(config.raw_daily_dir)
    adjusted_after = fingerprint_directory(config.adjusted_daily_dir)
    benchmark_context_summary = load_json(config.benchmark_context_summary_path)
    sector_context_summary = load_json(config.sector_context_summary_path)
    benchmark_ready = relative_strength_context.is_available() and SECONDARY_BENCHMARK_ID in relative_strength_context.benchmark_records
    report = {
        "phase": "Step 02.4",
        "command": "Command 02",
        "generated_at": generated_at,
        "feature_engine": {
            "architecture": "Adjusted research prices + point-in-time Nifty 500 membership + corporate-action research eligibility + NSE trading calendar",
            "feature_version": config.feature_config.feature_version,
            "timeframe": TIMEFRAME,
            "availability_time": AVAILABILITY_TIME,
            "decision_input_time": NEXT_SESSION_DECISION_INPUT,
            "output_format": "compressed CSV",
            "dataset_path": str(config.feature_dataset_path),
            "pilot_dataset_path": str(config.pilot_dataset_path),
        },
        "methodology": {
            "input_dataset": config.feature_config.source_dataset,
            "adjustment_methodology": METHODOLOGY_VERSION,
            "exclusion_policy": EXCLUSION_POLICY_VERSION,
            "traded_value_method": config.feature_config.traded_value_method,
            "atr_methodology": config.feature_config.atr_methodology,
            "volatility_methodology": config.feature_config.volatility_methodology,
            "benchmark_context_version": config.feature_config.benchmark_context_version,
            "sector_context_version": config.feature_config.sector_context_version,
            "feature_windows": feature_windows(config.feature_config),
        },
        "membership": {
            "status": membership_status,
            "version": universe_version,
            "period_count": len(periods),
            "integration_status": "POINT_IN_TIME_MEMBERSHIP_APPLIED",
            "uncertain_rows": full_result["membership_uncertain_rows"],
        },
        "corporate_action_eligibility": {
            "integration_status": "LOOKBACK_AWARE_ELIGIBILITY_APPLIED",
            "service": "ResearchEligibilityIndex equivalent to is_research_eligible(symbol, as_of_date, lookback_sessions)",
            "blocked_rows": full_result["corporate_action_blocked_rows"],
        },
        "benchmark": {
            "status": "AVAILABLE" if benchmark_ready else "UNAVAILABLE",
            "provider": relative_strength_context.name,
            "primary_benchmark_id": config.feature_config.primary_benchmark_id,
            "secondary_benchmark_id": config.feature_config.secondary_benchmark_id,
            "context_version": config.feature_config.benchmark_context_version,
            "reason": "" if benchmark_ready else relative_strength_context.reason,
            "coverage": benchmark_context_summary.get("benchmarks", {}),
        },
        "sector": {
            "status": "LIMITED" if relative_strength_context.sector_context_available() else "UNAVAILABLE",
            "context_version": config.feature_config.sector_context_version,
            "mapping_policy": "Only POINT_IN_TIME_VERIFIED and INFERRED_WITH_EVIDENCE mappings are eligible for sector-relative features.",
            "reason": "Current-only sector metadata is retained but not projected backward.",
            "coverage": sector_context_summary.get("sector_indices", {}),
            "mapping_status_counts": sector_context_summary.get("mapping_status_counts", {}),
        },
        "pilot": {
            "symbols_requested": list(PILOT_SYMBOLS),
            "symbols_generated": sorted({row["symbol"] for row in pilot_rows}),
            "row_count": len(pilot_rows),
            "validation_passed": pilot_validation["passed"],
            "validation_rows": len(pilot_validation["rows"]),
            "dates_sampled": sorted({row["trading_date"] for row in pilot_rows})[:3]
            + sorted({row["trading_date"] for row in pilot_rows})[-3:],
        },
        "generation": full_result
        | {
            "full_generation_completed": full_generation_completed,
            "total_potential_symbol_date_observations": load_summary["loaded_bars"],
        },
        "input_load": load_summary,
        "integrity": {
            "raw_nse_unchanged": raw_before == raw_after,
            "adjusted_dataset_unchanged": adjusted_before == adjusted_after,
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_scores_calculated": 0,
            "strategy_signals_generated": 0,
        },
        "outputs": {
            "feature_dataset": str(config.feature_dataset_path),
            "pilot_dataset": str(config.pilot_dataset_path),
            "summary_json": str(config.summary_path),
            "quality_summary_csv": str(config.quality_summary_path),
            "relative_strength_quality_csv": str(config.relative_strength_quality_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "markdown": "docs/daily-feature-engine.md",
            "benchmark_sector_markdown": "docs/benchmark-and-sector-context.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": file_size(config.feature_dataset_path) + file_size(config.pilot_dataset_path),
        },
        "ready_for_review": bool(
            full_generation_completed
            and pilot_validation["passed"]
            and raw_before == raw_after
            and adjusted_before == adjusted_after
            and benchmark_ready
        ),
    }
    write_json(config.summary_path, report)
    return report


def iter_feature_rows(
    *,
    bars_by_symbol: dict[str, list[AdjustedDailyBar]],
    membership_index: Nifty500MembershipIndex,
    membership_status: str,
    universe_version: str,
    sector_lookup: dict[str, str],
    eligibility_index: ResearchEligibilityIndex,
    trading_sessions: Sequence[date],
    feature_config: DailyFeatureConfig,
    relative_strength_context: LocalOfficialIndexContextProvider,
    symbols: Sequence[str] | None = None,
) -> Iterable[dict[str, Any]]:
    symbol_filter = {canonical_symbol(symbol) for symbol in symbols} if symbols else None
    trading_session_index = {session: offset for offset, session in enumerate(trading_sessions)}
    for symbol in sorted(bars_by_symbol):
        if symbol_filter is not None and symbol not in symbol_filter:
            continue
        bars = bars_by_symbol[symbol]
        feature_cache = build_symbol_feature_cache(bars, feature_config)
        for index, bar in enumerate(bars):
            membership = membership_index.period_for(symbol, bar.trading_date)
            if membership is None:
                continue
            yield FeatureRowBuilder(
                bars=bars,
                index=index,
                membership=membership,
                membership_status=membership_status,
                universe_version=universe_version,
                sector=sector_lookup.get(symbol, ""),
                feature_cache=feature_cache,
                eligibility_index=eligibility_index,
                trading_sessions=trading_sessions,
                trading_session_index=trading_session_index,
                feature_config=feature_config,
                relative_strength_context=relative_strength_context,
            ).build()


def build_symbol_feature_cache(bars: Sequence[AdjustedDailyBar], config: DailyFeatureConfig) -> SymbolFeatureCache:
    count = len(bars)
    values: dict[str, list[Any]] = {}
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    traded_values = [bar.close * bar.volume for bar in bars]
    true_ranges = [None] + [
        max(
            bars[index].high - bars[index].low,
            abs(bars[index].high - bars[index - 1].close),
            abs(bars[index].low - bars[index - 1].close),
        )
        for index in range(1, count)
    ]
    daily_returns = [None] + [simple_return(closes[index], closes[index - 1]) for index in range(1, count)]

    values["daily_traded_value"] = traded_values
    values["true_range"] = true_ranges
    values["gap_open_pct"] = [None] + [simple_return(bars[index].open, closes[index - 1]) for index in range(1, count)]

    candle_values = [breakout_context.candle_anatomy(bar) for bar in bars]
    for field in ("daily_range_pct", "body_pct", "upper_wick_pct", "lower_wick_pct", "close_location_value"):
        values[field] = [row[field] for row in candle_values]

    for window in config.return_windows:
        values[f"return_{window}d"] = trailing_return_values(closes, window)
    for window in config.momentum_windows:
        values[f"momentum_{window}d"] = trailing_return_values(closes, window)
    for window in config.positive_day_windows:
        positive_counts = positive_day_counts(daily_returns, window)
        values[f"positive_days_{window}"] = positive_counts
        values[f"up_days_ratio_{window}"] = [
            safe_divide(Decimal(value), Decimal(window)) if value is not None else None
            for value in positive_counts
        ]
    for window in config.volume_windows:
        values[f"median_traded_value_{window}d"] = trailing_medians(traded_values, window, include_current=True)
        values[f"avg_volume_{window}d"] = trailing_means(volumes, window)
    for window in config.relative_volume_windows:
        prior_medians = trailing_medians(volumes, window, include_current=False)
        values[f"relative_volume_{window}d"] = [
            safe_divide(volumes[index], prior_medians[index]) if prior_medians[index] is not None else None
            for index in range(count)
        ]
    for window in config.atr_windows:
        values[f"atr_{window}"] = trailing_means(true_ranges, window)
    values["atr_percent_14"] = [
        safe_divide(values["atr_14"][index], closes[index]) if values["atr_14"][index] is not None else None
        for index in range(count)
    ]
    for window in config.volatility_windows:
        values[f"return_volatility_{window}d"] = trailing_stdevs(daily_returns, window)
    for window in config.level_windows:
        label = level_label(window)
        values[f"high_{label}"] = trailing_extreme(highs, window, max)
        values[f"low_{label}"] = trailing_extreme(lows, window, min)
    for window in config.prior_level_windows:
        label = level_label(window)
        values[f"prior_high_{label}"] = prior_extreme(highs, window, max)
        values[f"prior_low_{label}"] = prior_extreme(lows, window, min)
        values[f"distance_to_prior_{label}_high_pct"] = [
            breakout_context.distance_to_level(closes[index], values[f"prior_high_{label}"][index])
            for index in range(count)
        ]
    for window in config.sma_windows:
        values[f"sma_{window}"] = trailing_means(closes, window)
    for window in (20, 50, 200):
        values[f"distance_from_sma_{window}_pct"] = [
            breakout_context.distance_to_level(closes[index], values[f"sma_{window}"][index])
            for index in range(count)
        ]
    for window in config.range_windows:
        high_values = values[f"high_{level_label(window)}"]
        low_values = values[f"low_{level_label(window)}"]
        values[f"range_width_{window}d_pct"] = [
            safe_divide(high_values[index] - low_values[index], closes[index])
            if high_values[index] is not None and low_values[index] is not None
            else None
            for index in range(count)
        ]
    values["above_prior_5d_high"] = compare_close_to_prior(closes, values["prior_high_5d"])
    values["above_prior_20d_high"] = compare_close_to_prior(closes, values["prior_high_20d"])
    values["above_prior_52w_high"] = compare_close_to_prior(closes, values["prior_high_52w"])
    values["intraday_high_above_prior_20d_high"] = [
        bool(highs[index] > values["prior_high_20d"][index]) if values["prior_high_20d"][index] is not None else None
        for index in range(count)
    ]
    values["atr_contraction_ratio"] = [
        safe_divide(values["atr_5"][index], values["atr_20"][index])
        if values["atr_5"][index] is not None and values["atr_20"][index] is not None
        else None
        for index in range(count)
    ]
    return SymbolFeatureCache(values)


def trailing_return_values(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    for index in range(window, len(values)):
        output[index] = simple_return(values[index], values[index - window])
    return output


def positive_day_counts(returns: Sequence[Decimal | None], window: int) -> list[int | None]:
    output: list[int | None] = [None] * len(returns)
    for index in range(window, len(returns)):
        current = returns[index - window + 1 : index + 1]
        if any(value is None for value in current):
            continue
        output[index] = sum(1 for value in current if value is not None and value > 0)
    return output


def trailing_means(values: Sequence[Decimal | None], window: int) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    running = Decimal("0")
    missing = 0
    for index, value in enumerate(values):
        if value is None:
            missing += 1
        else:
            running += value
        if index >= window:
            leaving = values[index - window]
            if leaving is None:
                missing -= 1
            else:
                running -= leaving
        if index + 1 >= window and missing == 0:
            output[index] = running / Decimal(window)
    return output


def trailing_medians(values: Sequence[Decimal], window: int, *, include_current: bool) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    for index in range(len(values)):
        end = index + 1 if include_current else index
        start = end - window
        if start < 0:
            continue
        output[index] = median_decimal(values[start:end])
    return output


def trailing_stdevs(values: Sequence[Decimal | None], window: int) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    for index in range(window, len(values)):
        current = values[index - window + 1 : index + 1]
        if any(value is None for value in current):
            continue
        output[index] = sample_stdev_decimal([value for value in current if value is not None])
    return output


def trailing_extreme(values: Sequence[Decimal], window: int, reducer: Any) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    prefer_higher = reducer is max
    candidates: deque[int] = deque()
    for index, value in enumerate(values):
        while candidates and candidates[0] <= index - window:
            candidates.popleft()
        while candidates and (
            values[candidates[-1]] <= value if prefer_higher else values[candidates[-1]] >= value
        ):
            candidates.pop()
        candidates.append(index)
        if index + 1 >= window:
            output[index] = values[candidates[0]]
    return output


def prior_extreme(values: Sequence[Decimal], window: int, reducer: Any) -> list[Decimal | None]:
    output: list[Decimal | None] = [None] * len(values)
    trailing = trailing_extreme(values, window, reducer)
    for index in range(window, len(values)):
        output[index] = trailing[index - 1]
    return output


def compare_close_to_prior(closes: Sequence[Decimal], prior_values: Sequence[Decimal | None]) -> list[bool | None]:
    return [
        bool(closes[index] > prior_values[index]) if prior_values[index] is not None else None
        for index in range(len(closes))
    ]


def write_full_feature_dataset(
    *,
    path: Path,
    bars_by_symbol: dict[str, list[AdjustedDailyBar]],
    membership_index: Nifty500MembershipIndex,
    membership_status: str,
    universe_version: str,
    sector_lookup: dict[str, str],
    eligibility_index: ResearchEligibilityIndex,
    trading_sessions: Sequence[date],
    feature_config: DailyFeatureConfig,
    relative_strength_context: LocalOfficialIndexContextProvider,
) -> dict[str, Any]:
    result = empty_generation_result(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_feature_csv(path) as file:
        writer = csv.DictWriter(file, fieldnames=FEATURE_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in iter_feature_rows(
            bars_by_symbol=bars_by_symbol,
            membership_index=membership_index,
            membership_status=membership_status,
            universe_version=universe_version,
            sector_lookup=sector_lookup,
            eligibility_index=eligibility_index,
            trading_sessions=trading_sessions,
            feature_config=feature_config,
            relative_strength_context=relative_strength_context,
        ):
            writer.writerow(json_safe(row))
            update_generation_result(result, row)
    result["dataset_path"] = str(path)
    result["storage_size_bytes"] = file_size(path)
    result["usable_percent_by_lookback"] = usable_percent_by_lookback(result)
    finalize_relative_strength_percentages(result)
    return result


def update_generation_result(result: dict[str, Any], row: dict[str, Any]) -> None:
    result["generated_feature_rows"] += 1
    status = row["feature_status"]
    result["feature_status_counts"][status] += 1
    if status == STATUS_READY:
        result["ready_rows"] += 1
    if row.get("feature_null_reasons"):
        result["rows_with_partial_or_null_features"] += 1
    if STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED in row.get("feature_null_reasons", ""):
        result["corporate_action_blocked_rows"] += 1
    if STATUS_INSUFFICIENT_HISTORY in row.get("feature_null_reasons", ""):
        result["insufficient_history_rows"] += 1
    if row.get("universe_membership_status") != "SURVIVORSHIP_SAFE":
        result["membership_uncertain_rows"] += 1
    if row.get("benchmark_status") == STATUS_BENCHMARK_UNAVAILABLE:
        result["benchmark_unavailable_rows"] += 1
    if all(has_value(row.get(f"relative_return_{window}d_vs_nifty500")) for window in (1, 3, 5, 10, 20)):
        result["benchmark_relative_available_rows"] += 1
    else:
        result["benchmark_relative_unavailable_rows"] += 1
    if all(has_value(row.get(f"relative_return_{window}d_vs_sector")) for window in (1, 3, 5, 10, 20)):
        result["sector_relative_available_rows"] += 1
    else:
        result["sector_relative_unavailable_rows"] += 1
    if has_value(row.get("relative_return_5d_vs_nifty500")):
        result["relative_strength_5d_usable_rows"] += 1
    if has_value(row.get("relative_return_20d_vs_nifty500")):
        result["relative_strength_20d_usable_rows"] += 1
    result["sector_mapping_status_counts"][row.get("sector_mapping_status") or "UNAVAILABLE"] += 1
    for lookback in USABILITY_SCENARIOS:
        group_status = scenario_status_for_row(row, lookback)
        result["lookback_usability"][str(lookback)]["total"] += 1
        if group_status == STATUS_READY:
            result["lookback_usability"][str(lookback)]["usable"] += 1
        else:
            result["lookback_usability"][str(lookback)]["unusable"] += 1


def scenario_status_for_row(row: dict[str, Any], lookback: int) -> str:
    if lookback == 5:
        fields = ("return_5d", "median_traded_value_5d", "relative_volume_5d", "atr_5", "high_5d", "sma_5")
    elif lookback == 20:
        fields = ("return_20d", "median_traded_value_20d", "relative_volume_20d", "atr_20", "high_20d", "sma_20")
    elif lookback == 60:
        fields = ("return_20d", "atr_20", "high_20d", "sma_50")
    else:
        fields = ("sma_200",)
    return STATUS_READY if all(row.get(field) not in {"", None} for field in fields) else "UNUSABLE"


def usable_percent_by_lookback(result: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for lookback, counts in result["lookback_usability"].items():
        total = counts["total"]
        usable = counts["usable"]
        output[lookback] = str((Decimal(usable) / Decimal(total) * Decimal("100")).quantize(Decimal("0.0001"))) if total else "0"
    return output


def empty_generation_result(path: Path) -> dict[str, Any]:
    return {
        "dataset_path": str(path),
        "generated_feature_rows": 0,
        "ready_rows": 0,
        "rows_with_partial_or_null_features": 0,
        "corporate_action_blocked_rows": 0,
        "insufficient_history_rows": 0,
        "membership_uncertain_rows": 0,
        "benchmark_unavailable_rows": 0,
        "benchmark_relative_available_rows": 0,
        "benchmark_relative_unavailable_rows": 0,
        "benchmark_relative_coverage_percent": "0",
        "sector_relative_available_rows": 0,
        "sector_relative_unavailable_rows": 0,
        "sector_relative_coverage_percent": "0",
        "relative_strength_5d_usable_rows": 0,
        "relative_strength_5d_usable_percent": "0",
        "relative_strength_20d_usable_rows": 0,
        "relative_strength_20d_usable_percent": "0",
        "sector_mapping_status_counts": Counter(),
        "feature_status_counts": Counter(),
        "lookback_usability": {str(lookback): Counter() for lookback in USABILITY_SCENARIOS},
        "usable_percent_by_lookback": {str(lookback): "0" for lookback in USABILITY_SCENARIOS},
        "storage_size_bytes": 0,
    }


def finalize_relative_strength_percentages(result: dict[str, Any]) -> None:
    total = result["generated_feature_rows"]
    result["benchmark_relative_coverage_percent"] = percent(result["benchmark_relative_available_rows"], total)
    result["sector_relative_coverage_percent"] = percent(result["sector_relative_available_rows"], total)
    result["relative_strength_5d_usable_percent"] = percent(result["relative_strength_5d_usable_rows"], total)
    result["relative_strength_20d_usable_percent"] = percent(result["relative_strength_20d_usable_rows"], total)


def percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0"
    return str((Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(Decimal("0.0001")))


def has_value(value: Any) -> bool:
    return value not in {"", None}


def validate_pilot_rows(
    pilot_rows: Sequence[dict[str, Any]],
    bars_by_symbol: dict[str, list[AdjustedDailyBar]],
    relative_strength_context: LocalOfficialIndexContextProvider,
) -> dict[str, Any]:
    required_features = (
        "return_5d",
        "median_traded_value_20d",
        "relative_volume_20d",
        "true_range",
        "atr_14",
        "prior_high_20d",
        "sma_20",
        "gap_open_pct",
    )
    target = next(
        (
            row
            for row in reversed(pilot_rows)
            if row["symbol"] == "RELIANCE" and all(row.get(feature) is not None for feature in required_features)
        ),
        None,
    )
    if target is None:
        return {"passed": False, "rows": []}
    symbol = target["symbol"]
    trading_date = parse_date(str(target["trading_date"]))
    bars = bars_by_symbol[symbol]
    index = next(offset for offset, bar in enumerate(bars) if bar.trading_date == trading_date)
    expected = {
        "return_5d": daily.trailing_return(bars, index, 5),
        "median_traded_value_20d": liquidity.rolling_median_traded_value(bars, index, 20),
        "relative_volume_20d": liquidity.relative_volume_vs_prior_median(bars, index, 20),
        "true_range": volatility.true_range(bars, index),
        "atr_14": volatility.simple_atr(bars, index, 14),
        "prior_high_20d": breakout_context.prior_high(bars, index, 20),
        "sma_20": daily.simple_moving_average(bars, index, 20),
        "gap_open_pct": breakout_context.gap_open_pct(bars, index),
    }
    tolerance = Decimal("0.000000000001")
    rows: list[dict[str, Any]] = []
    for feature, expected_value in expected.items():
        calculated = parse_decimal(target.get(feature))
        difference = abs((calculated or Decimal("0")) - (expected_value or Decimal("0")))
        rows.append(
            {
                "symbol": symbol,
                "trading_date": trading_date,
                "feature": feature,
                "calculated": calculated,
                "expected": expected_value,
                "difference": difference,
                "tolerance": tolerance,
                "result": "PASS" if difference <= tolerance else "FAIL",
            }
        )

    benchmark_expected = {
        "benchmark_return_5d": relative_strength_context.benchmark_return_for(PRIMARY_BENCHMARK_ID, trading_date, 5),
        "nifty50_return_20d": relative_strength_context.benchmark_return_for(SECONDARY_BENCHMARK_ID, trading_date, 20),
    }
    if benchmark_expected["benchmark_return_5d"] is not None and expected["return_5d"] is not None:
        benchmark_expected["relative_return_5d_vs_nifty500"] = (
            expected["return_5d"] - benchmark_expected["benchmark_return_5d"]
        )
    for feature, expected_value in benchmark_expected.items():
        calculated = parse_decimal(target.get(feature))
        difference = abs((calculated or Decimal("0")) - (expected_value or Decimal("0")))
        rows.append(
            {
                "symbol": symbol,
                "trading_date": trading_date,
                "feature": feature,
                "calculated": calculated,
                "expected": expected_value,
                "difference": difference,
                "tolerance": tolerance,
                "result": "PASS" if expected_value is not None and difference <= tolerance else "FAIL",
            }
        )

    sector_target = next(
        (
            row
            for row in reversed(pilot_rows)
            if row.get("sector_mapping_status") in ALLOWED_SECTOR_MAPPING_STATUSES
            and row.get("sector_return_5d") is not None
            and row.get("relative_return_5d_vs_sector") is not None
        ),
        None,
    )
    if sector_target is not None:
        sector_symbol = str(sector_target["symbol"])
        sector_date = parse_date(str(sector_target["trading_date"]))
        sector_bars = bars_by_symbol[sector_symbol]
        sector_index = next(offset for offset, bar in enumerate(sector_bars) if bar.trading_date == sector_date)
        sector_stock_return = daily.trailing_return(sector_bars, sector_index, 5)
        sector_return = relative_strength_context.sector_return_for(str(sector_target["sector_index_id"]), sector_date, 5)
        sector_expected = {
            "sector_return_5d": sector_return,
            "relative_return_5d_vs_sector": (
                sector_stock_return - sector_return if sector_stock_return is not None and sector_return is not None else None
            ),
        }
        for feature, expected_value in sector_expected.items():
            calculated = parse_decimal(sector_target.get(feature))
            difference = abs((calculated or Decimal("0")) - (expected_value or Decimal("0")))
            rows.append(
                {
                    "symbol": sector_symbol,
                    "trading_date": sector_date,
                    "feature": feature,
                    "calculated": calculated,
                    "expected": expected_value,
                    "difference": difference,
                    "tolerance": tolerance,
                    "result": "PASS" if expected_value is not None and difference <= tolerance else "FAIL",
                }
            )
    else:
        current_only_target = next(
            (row for row in reversed(pilot_rows) if row.get("sector_mapping_status") == "CURRENT_ONLY"),
            None,
        )
        rows.append(
            {
                "symbol": current_only_target["symbol"] if current_only_target else "",
                "trading_date": current_only_target["trading_date"] if current_only_target else "",
                "feature": "sector_relative_null_policy",
                "calculated": current_only_target.get("relative_return_5d_vs_sector") if current_only_target else None,
                "expected": None,
                "difference": 0,
                "tolerance": tolerance,
                "result": (
                    "PASS"
                    if current_only_target is not None and current_only_target.get("relative_return_5d_vs_sector") is None
                    else "FAIL"
                ),
            }
        )
    return {"passed": all(row["result"] == "PASS" for row in rows), "rows": rows}


def write_feature_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_feature_csv(path) as file:
        writer = csv.DictWriter(file, fieldnames=FEATURE_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def load_adjusted_nifty500_bars(
    *,
    adjusted_daily_dir: Path,
    membership_index: Nifty500MembershipIndex,
    start_date: date,
    end_date: date,
    trading_sessions: Sequence[date],
) -> tuple[dict[str, list[AdjustedDailyBar]], dict[str, Any]]:
    session_set = set(trading_sessions)
    bars_by_symbol: dict[str, list[AdjustedDailyBar]] = defaultdict(list)
    summary = Counter()
    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None or trading_date < start_date or trading_date > end_date or trading_date not in session_set:
            continue
        summary["files_read"] += 1
        for row in read_csv_iter(path):
            if row.get("series") != "EQ":
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            membership = membership_index.period_for(symbol, trading_date)
            if membership is None:
                continue
            summary["potential_rows"] += 1
            bar = parse_adjusted_bar(row, path)
            if bar is None:
                summary["invalid_rows"] += 1
                continue
            bars_by_symbol[symbol].append(bar)
            summary["loaded_bars"] += 1
    for symbol in bars_by_symbol:
        bars_by_symbol[symbol].sort(key=lambda bar: bar.trading_date)
    return dict(bars_by_symbol), dict(summary)


def parse_adjusted_bar(row: dict[str, str], path: Path) -> AdjustedDailyBar | None:
    trading_date = parse_date(row.get("trading_date"))
    open_value = parse_decimal(row.get("adjusted_open"))
    high_value = parse_decimal(row.get("adjusted_high"))
    low_value = parse_decimal(row.get("adjusted_low"))
    close_value = parse_decimal(row.get("adjusted_close"))
    volume_value = parse_decimal(row.get("adjusted_volume"))
    if None in {trading_date, open_value, high_value, low_value, close_value, volume_value}:
        return None
    if close_value <= 0 or high_value < low_value or volume_value < 0:
        return None
    return AdjustedDailyBar(
        trading_date=trading_date,
        symbol=canonical_symbol(row.get("symbol", "")),
        isin=row.get("isin", ""),
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=volume_value,
        source_file=path.name,
        source=row.get("source", ""),
        research_usability_status=row.get("research_usability_status", ""),
        adjustment_methodology_version=row.get("adjustment_methodology_version", ""),
        provenance=row.get("provenance", ""),
    )


def quality_summary_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {"metric": "generated_feature_rows", "value": result["generated_feature_rows"], "notes": ""},
        {"metric": "ready_rows", "value": result["ready_rows"], "notes": ""},
        {"metric": "rows_with_partial_or_null_features", "value": result["rows_with_partial_or_null_features"], "notes": "Includes unavailable benchmark and sector-relative fields."},
        {"metric": "corporate_action_blocked_rows", "value": result["corporate_action_blocked_rows"], "notes": ""},
        {"metric": "insufficient_history_rows", "value": result["insufficient_history_rows"], "notes": ""},
        {"metric": "membership_uncertain_rows", "value": result["membership_uncertain_rows"], "notes": "Historical membership remains PARTIAL_HISTORY."},
        {"metric": "benchmark_unavailable_rows", "value": result["benchmark_unavailable_rows"], "notes": ""},
        {"metric": "benchmark_relative_available_rows", "value": result["benchmark_relative_available_rows"], "notes": f"{result['benchmark_relative_coverage_percent']}%"},
        {"metric": "benchmark_relative_unavailable_rows", "value": result["benchmark_relative_unavailable_rows"], "notes": ""},
        {"metric": "sector_relative_available_rows", "value": result["sector_relative_available_rows"], "notes": f"{result['sector_relative_coverage_percent']}%"},
        {"metric": "sector_relative_unavailable_rows", "value": result["sector_relative_unavailable_rows"], "notes": ""},
        {"metric": "relative_strength_5d_usable_rows", "value": result["relative_strength_5d_usable_rows"], "notes": f"{result['relative_strength_5d_usable_percent']}%"},
        {"metric": "relative_strength_20d_usable_rows", "value": result["relative_strength_20d_usable_rows"], "notes": f"{result['relative_strength_20d_usable_percent']}%"},
    ]
    for status, count in sorted(result["feature_status_counts"].items()):
        rows.append({"metric": f"feature_status.{status}", "value": count, "notes": ""})
    for status, count in sorted(result["sector_mapping_status_counts"].items()):
        rows.append({"metric": f"sector_mapping_status.{status}", "value": count, "notes": ""})
    for lookback, counts in sorted(result["lookback_usability"].items(), key=lambda item: int(item[0])):
        rows.append({"metric": f"lookback_{lookback}.usable", "value": counts["usable"], "notes": f"{result['usable_percent_by_lookback'][lookback]}%"})
        rows.append({"metric": f"lookback_{lookback}.unusable", "value": counts["unusable"], "notes": ""})
    return rows


def relative_strength_quality_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"metric": "generated_feature_rows", "value": result["generated_feature_rows"], "notes": ""},
        {"metric": "benchmark_relative_available_rows", "value": result["benchmark_relative_available_rows"], "notes": f"{result['benchmark_relative_coverage_percent']}%"},
        {"metric": "benchmark_relative_unavailable_rows", "value": result["benchmark_relative_unavailable_rows"], "notes": ""},
        {"metric": "sector_relative_available_rows", "value": result["sector_relative_available_rows"], "notes": f"{result['sector_relative_coverage_percent']}%"},
        {"metric": "sector_relative_unavailable_rows", "value": result["sector_relative_unavailable_rows"], "notes": ""},
        {"metric": "relative_strength_5d_usable_rows", "value": result["relative_strength_5d_usable_rows"], "notes": f"{result['relative_strength_5d_usable_percent']}%"},
        {"metric": "relative_strength_20d_usable_rows", "value": result["relative_strength_20d_usable_rows"], "notes": f"{result['relative_strength_20d_usable_percent']}%"},
    ] + [
        {"metric": f"sector_mapping_status.{status}", "value": count, "notes": ""}
        for status, count in sorted(result["sector_mapping_status_counts"].items())
    ]


def write_daily_feature_engine_markdown(report: dict[str, Any], path: Path) -> None:
    features = FEATURE_GROUPS
    generation = report["generation"]
    lines = [
        "# Daily Feature Engine",
        "",
        "Current phase: Step 02.4 / Command 02 - benchmark and sector relative-strength context",
        "",
        "## Status",
        "",
        f"- Feature methodology: {report['feature_engine']['feature_version']}",
        f"- Benchmark context version: {report['methodology']['benchmark_context_version']}",
        f"- Sector context version: {report['methodology']['sector_context_version']}",
        f"- Full generation completed: {generation['full_generation_completed']}",
        f"- Ready for review: {report['ready_for_review']}",
        f"- Feature dataset: {report['feature_engine']['dataset_path']}",
        "",
        "## Architecture",
        "",
        "- Inputs: adjusted NSE research daily prices, point-in-time Nifty 500 membership, corporate-action research eligibility, and official NSE trading sessions.",
        "- Output: DAILY_EOD feature snapshots that are available only after the close of the feature date and usable as NEXT_SESSION_DECISION_INPUT.",
        "- No strategy scoring, trade signals, outcome labels, order logic, remote migrations, or Supabase feature writes are performed.",
        "",
        "## Methodology",
        "",
        f"- Adjustment methodology: {report['methodology']['adjustment_methodology']}",
        f"- Exclusion policy: {report['methodology']['exclusion_policy']}",
        f"- Traded value: {report['methodology']['traded_value_method']}",
        f"- ATR: {report['methodology']['atr_methodology']}",
        f"- Return volatility: {report['methodology']['volatility_methodology']}",
        "- Rolling windows use trading sessions, not calendar days.",
        "- Relative volume denominators use prior sessions only and exclude the current date.",
        "- Prior highs/lows exclude the current date; inclusive rolling highs/lows are stored separately.",
        "- Benchmark and sector index closes are official DAILY_EOD context and are not treated as intraday inputs.",
        "- DAILY_FEATURES_V1 is retained; benchmark_context_version and sector_context_version record this Command 02 enhancement.",
        "",
        "## Feature Groups",
        "",
    ]
    for group, fields in features.items():
        lines.append(f"- {group}: {', '.join(fields)}")
    lines.extend(
        [
            "",
            "## Membership And Eligibility",
            "",
            f"- Membership status: {report['membership']['status']}",
            "- Membership metadata is retained on every feature row.",
            f"- Corporate-action eligibility: {report['corporate_action_eligibility']['integration_status']}",
            "- Features crossing an exclusion or continuity-break interval are null with explicit reason codes.",
            "",
            "## Benchmark And Sector",
            "",
            f"- Benchmark status: {report['benchmark']['status']}",
            f"- Primary benchmark: {report['benchmark']['primary_benchmark_id']}",
            f"- Secondary benchmark: {report['benchmark']['secondary_benchmark_id']}",
            f"- Benchmark reason: {report['benchmark']['reason']}",
            f"- Sector status: {report['sector']['status']}",
            f"- Sector reason: {report['sector']['reason']}",
            f"- Sector mapping policy: {report['sector']['mapping_policy']}",
            "",
            "## Pilot",
            "",
            f"- Symbols requested: {', '.join(report['pilot']['symbols_requested'])}",
            f"- Symbols generated: {', '.join(report['pilot']['symbols_generated'])}",
            f"- Pilot rows: {report['pilot']['row_count']}",
            f"- Manual validation rows: {report['pilot']['validation_rows']}",
            f"- Manual validation passed: {report['pilot']['validation_passed']}",
            "",
            "## Full Generation",
            "",
            f"- Total potential Nifty 500 symbol-date observations: {generation['total_potential_symbol_date_observations']}",
            f"- Generated feature rows: {generation['generated_feature_rows']}",
            f"- READY rows: {generation['ready_rows']}",
            f"- Rows with partial/null features: {generation['rows_with_partial_or_null_features']}",
            f"- Corporate-action-blocked rows: {generation['corporate_action_blocked_rows']}",
            f"- Insufficient-history rows: {generation['insufficient_history_rows']}",
            f"- Membership-uncertain rows: {generation['membership_uncertain_rows']}",
            f"- Benchmark-relative rows: {generation['benchmark_relative_available_rows']} ({generation['benchmark_relative_coverage_percent']}%)",
            f"- Sector-relative rows: {generation['sector_relative_available_rows']} ({generation['sector_relative_coverage_percent']}%)",
            f"- 5-session relative strength usable: {generation['relative_strength_5d_usable_percent']}%",
            f"- 20-session relative strength usable: {generation['relative_strength_20d_usable_percent']}%",
            f"- 5-session usable: {generation['usable_percent_by_lookback']['5']}%",
            f"- 20-session usable: {generation['usable_percent_by_lookback']['20']}%",
            f"- 60-session usable: {generation['usable_percent_by_lookback']['60']}%",
            f"- 200-session usable: {generation['usable_percent_by_lookback']['200']}%",
            f"- Storage bytes: {report['processing']['storage_size_bytes']}",
            f"- Processing seconds: {report['processing']['duration_seconds']}",
            "",
            "## Integrity And Safety",
            "",
            f"- Raw NSE unchanged: {report['integrity']['raw_nse_unchanged']}",
            f"- Adjusted dataset unchanged: {report['integrity']['adjusted_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "",
            "## Known Limitations",
            "",
            "- Sector index history is available where official NSE publishes it, but point-in-time stock-sector mapping remains limited.",
            "- CURRENT_ONLY sector mappings are retained for diagnostics and deliberately produce null sector-relative fields.",
            "- Historical Nifty 500 membership remains PARTIAL_HISTORY and must be considered by future backtests.",
            "- EMA features are deferred; SMA descriptors are implemented for Command 01.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_benchmark_and_sector_context_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    benchmark_coverage = report["benchmark"].get("coverage", {})
    sector_coverage = report["sector"].get("coverage", {})
    lines = [
        "# Benchmark And Sector Context",
        "",
        "Current phase: Step 02.4 / Command 02 - official benchmark and sector relative-strength foundation",
        "",
        "## Status",
        "",
        f"- Benchmark context version: {report['methodology']['benchmark_context_version']}",
        f"- Sector context version: {report['methodology']['sector_context_version']}",
        f"- Feature version decision: {report['feature_engine']['feature_version']} retained with context-version metadata.",
        f"- Full feature regeneration completed: {generation['full_generation_completed']}",
        f"- Ready for review: {report['ready_for_review']}",
        "",
        "## Official Sources",
        "",
        "- Official NSE historical index data endpoint: https://www.nseindia.com/api/historicalOR/indicesHistory",
        "- Official NSE historical index page: https://www.nseindia.com/reports-indices-historical-index-data",
        "- Official NSE live index inventory endpoint: https://www.nseindia.com/api/allIndices",
        "- Current official Nifty 500 constituent CSV: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "",
        "## Formulas And Timing",
        "",
        "- benchmark_return_Nd = index_close_T / index_close_T-N - 1.",
        "- relative_return_Nd_vs_nifty500 = adjusted_stock_return_Nd - NIFTY_500_return_Nd.",
        "- relative_return_Nd_vs_sector = adjusted_stock_return_Nd - sector_index_return_Nd when mapping is approved for T.",
        "- All benchmark and sector features are DAILY_EOD and become NEXT_SESSION_DECISION_INPUT for the next session.",
        "- Missing official index sessions are not forward-filled.",
        "- Corporate-action blocked stock windows also block benchmark and sector relative returns.",
        "",
        "## Benchmark Coverage",
        "",
    ]
    for benchmark_id, row in sorted(benchmark_coverage.items()):
        lines.append(
            "- "
            f"{benchmark_id} ({row.get('index_name', '')}): {row.get('first_date', '')} to {row.get('last_date', '')}, "
            f"{row.get('available_sessions', 0)}/{row.get('target_sessions', 0)} sessions, "
            f"{row.get('missing_sessions', 0)} missing, {row.get('coverage_percent', '0')}% coverage"
        )
    lines.extend(["", "## Sector Index Coverage", ""])
    for sector_id, row in sorted(sector_coverage.items()):
        lines.append(
            "- "
            f"{sector_id} ({row.get('index_name', '')}): {row.get('first_date', '')} to {row.get('last_date', '')}, "
            f"{row.get('available_sessions', 0)}/{row.get('target_sessions', 0)} sessions, "
            f"{row.get('missing_sessions', 0)} missing, {row.get('coverage_percent', '0')}% coverage, usable={row.get('usable', False)}"
        )
    lines.extend(
        [
            "",
            "## Stock-Sector Mapping",
            "",
            f"- Mapping policy: {report['sector']['mapping_policy']}",
            "- POINT_IN_TIME_VERIFIED and INFERRED_WITH_EVIDENCE are eligible for sector-relative features.",
            "- CURRENT_ONLY is not projected backward and produces null sector-relative fields.",
        ]
    )
    for status, count in sorted(generation["sector_mapping_status_counts"].items()):
        lines.append(f"- Generated rows with {status}: {count}")
    lines.extend(
        [
            "",
            "## Regenerated Feature Coverage",
            "",
            f"- Total feature rows: {generation['generated_feature_rows']}",
            f"- Benchmark-relative rows available: {generation['benchmark_relative_available_rows']} ({generation['benchmark_relative_coverage_percent']}%)",
            f"- Sector-relative rows available: {generation['sector_relative_available_rows']} ({generation['sector_relative_coverage_percent']}%)",
            f"- 5-session relative-strength usable: {generation['relative_strength_5d_usable_percent']}%",
            f"- 20-session relative-strength usable: {generation['relative_strength_20d_usable_percent']}%",
            "",
            "## Known Limitations",
            "",
            "- Historical Nifty 500 membership remains PARTIAL_HISTORY.",
            "- Public point-in-time stock-sector membership archives were not available inside this command scope.",
            "- No strategy scores, candidate selection, labels, backtests, orders, remote migrations, or Supabase bulk writes are performed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def aggregate_status(statuses: Sequence[str]) -> str:
    if not statuses:
        return STATUS_READY
    return max(statuses, key=status_priority)


def status_priority(status: str) -> int:
    order = {
        STATUS_READY: 0,
        STATUS_NOT_APPLICABLE: 0,
        STATUS_BENCHMARK_UNAVAILABLE: 1,
        STATUS_SECTOR_CONTEXT_UNAVAILABLE: 1,
        STATUS_SECTOR_MAPPING_UNAVAILABLE: 1,
        STATUS_INSUFFICIENT_HISTORY: 2,
        STATUS_MISSING_INPUT_DATA: 3,
        STATUS_INVALID_SOURCE_ROW: 4,
        STATUS_CORPORATE_ACTION_LOOKBACK_BLOCKED: 5,
    }
    return order.get(status, 0)


def level_label(window: int) -> str:
    return "52w" if window == 252 else f"{window}d"


def feature_windows(config: DailyFeatureConfig) -> dict[str, Any]:
    return {
        "returns": list(config.return_windows),
        "momentum": list(config.momentum_windows),
        "positive_days": list(config.positive_day_windows),
        "volume": list(config.volume_windows),
        "relative_volume": list(config.relative_volume_windows),
        "atr": list(config.atr_windows),
        "levels": list(config.level_windows),
        "sma": list(config.sma_windows),
        "volatility": list(config.volatility_windows),
        "range": list(config.range_windows),
        "benchmark_returns": list(config.benchmark_return_windows),
        "benchmark_relative": list(config.benchmark_relative_windows),
        "secondary_benchmark": list(config.secondary_benchmark_windows),
        "sector_returns": list(config.sector_return_windows),
    }


def load_membership_periods(path: Path) -> list[MembershipPeriod]:
    periods: list[MembershipPeriod] = []
    for row in read_csv(path):
        valid_from = parse_date(row.get("valid_from"))
        if valid_from is None:
            continue
        periods.append(
            MembershipPeriod(
                symbol=canonical_symbol(row.get("symbol", "")),
                isin=row.get("isin", ""),
                valid_from=valid_from,
                valid_to=parse_date(row.get("valid_to")),
                reconstruction_method=row.get("reconstruction_method", ""),
                source_confidence=row.get("source_confidence", ""),
                provenance=row.get("provenance", ""),
            )
        )
    return periods


def load_trading_sessions(path: Path, start_date: date, end_date: date) -> list[date]:
    sessions: list[date] = []
    for row in read_csv(path):
        trading_date = parse_date(row.get("trading_date"))
        if trading_date and start_date <= trading_date <= end_date and row.get("source_available") == "True":
            sessions.append(trading_date)
    return sorted(sessions)


def load_sector_lookup(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    lookup: dict[str, str] = {}
    for row in read_csv(path):
        symbol = canonical_symbol(row.get("symbol", ""))
        value = row.get("sector") or row.get("industry") or ""
        lookup[symbol] = value
    return lookup


def adjusted_daily_files(adjusted_daily_dir: Path) -> list[Path]:
    if not adjusted_daily_dir.exists():
        return []
    return sorted(adjusted_daily_dir.glob("*/*/nse_adjusted_daily_*.csv"))


def date_from_adjusted_path(path: Path) -> date | None:
    token = path.stem.replace("nse_adjusted_daily_", "")
    try:
        return datetime.strptime(token, "%Y%m%d").date()
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_csv_iter(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def open_feature_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "wt", encoding="utf-8", newline="")
    return path.open("w", encoding="utf-8", newline="")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(value), indent=2), encoding="utf-8")


def parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format_decimal_for_output(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def format_decimal_for_output(value: Decimal) -> str:
    try:
        quantized = value.quantize(DECIMAL_OUTPUT_QUANT)
    except InvalidOperation:
        quantized = value
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text

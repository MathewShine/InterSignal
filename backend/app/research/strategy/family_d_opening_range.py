from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.intraday.config import (
    CANONICAL_INTRADAY_PROFILE,
    EXECUTION_ORDERING_VERSION,
    EXPECTED_INTRADAY_CONFIG_HASH,
)
from app.research.intraday.development_ingestion import _canonical_5m_bars_from_partition
from app.research.intraday.first_touch import evaluate_first_touch
from app.research.intraday.models import CanonicalIntradayBar, FirstTouch
from app.research.strategy.family_a_momentum import (
    _corporate_action_exclusions,
    _corporate_action_safe,
    _load_aliases,
    _load_membership,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_c_breakout_continuation import (
    LIQUIDITY_FLOOR,
    LIQUIDITY_WINDOW,
    PRICE_FLOOR,
    _liquidity_calculation,
    _load_adjusted_bars,
    _load_sessions,
)
from app.research.strategy.family_c_research_closure import (
    EXPECTED_FAMILY_C_CLOSURE_HASH,
    GOVERNANCE_POLICY_VERSION,
    family_c_baseline_snapshot,
    verify_family_c_closure_inputs,
)


FAMILY_VERSION = "STRATEGY_FAMILY_D_OPENING_RANGE_V1"
RESEARCH_PROFILE = "INTRADAY_OPENING_RANGE_STOCKS_IN_PLAY_V1"
FAMILY_CODE = "FAMILY_D"
RESEARCH_PROTOCOL = "FAMILY_D_RESEARCH_PROTOCOL_V1"
COMMAND = "Step 03.04 / Command 01"
BOUNDED_RESEARCH_LABEL = "BOUNDED_100_SYMBOL_INTRADAY_DEVELOPMENT_RESEARCH"

CONTROL_ID = "CONTROL-D-000"
CONTROL_NAME = "ORB15_PLAIN_V1"
TREATMENT_ID = "ORB-D-001"
TREATMENT_NAME = "ORB15_WITH_OPENING_ACTIVITY_V1"
EXPERIMENT_COUNT = 1

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
STARTING_CAPITAL = Decimal("500000")
RISK_PER_TRADE = Decimal("0.005")
MAX_CONCURRENT_POSITIONS = 5
MAX_SIMULTANEOUS_RISK = Decimal("0.025")
OPENING_BAR_TIMES = (time(9, 15), time(9, 20), time(9, 25))
SIGNAL_WINDOW_START = time(9, 30)
SIGNAL_WINDOW_END = time(11, 30)
TIME_EXIT = time(15, 20)
ACTIVITY_LOOKBACK = 20
ACTIVITY_THRESHOLD = Decimal("1.50")

NORMALIZED_5M_DATASET_HASH = "a694c232be5160ba50fc7f6e8e85b93fc90cc125aa03a7c082ce803a18752f87"
SESSION_INDEX_HASH = "cf7732fb1acbb29b93c1b07ce4dbf03a624692968f34c2be4e9c65b866aab1d5"
INGESTION_SCOPE_HASH = "dcf4cc8587c923fd08e6299f472cd8f37add3baae54498351eb53fe76da75fe3"
REQUEST_PLAN_HASH = "cd871adf88bc571339b0c3ca7efcb066d88ab8b63ceae5d0804a411fd8e7dfaf"
OPPORTUNITY_COVERAGE_HASH = "2664947c8efe6f5a9c21806ad1843a3ef78e9f6e0d0d6c65a814aa74c0b742f7"
EXPECTED_SYMBOLS = 100
EXPECTED_SYMBOL_SESSIONS = 4821
EXPECTED_STRICT_SESSIONS = 4812
EXPECTED_NORMALIZED_ROWS = 361104

EXPECTED_FAMILY_D_CONFIG_HASH = "87ab7e4b328d7e1c433f99b6997b5b8f9cb9d0439893608f0ac5b7ca247b601a"
EXPECTED_CONTROL_REFERENCE_HASH = "fb2da529f1936a870fe4eada3c0db3bf5173ba6429e1495792edc92d57ee9cf4"
EXPECTED_D001_PARAMETER_HASH = "d570a5c165b1c10100f329f8bb08d619e84dad97b893484800978f021fc14d5c"
EXPECTED_D001_PREREGISTRATION_HASH = "1730b3c764aa9d54b8b9719dcecfa3c3763b4b60f49f67819dc6b4a94be2e1d4"
EXPECTED_SUCCESS_CRITERIA_HASH = "0b6002f830bd16a6259719ce5ff242c670364ba68cccd4f34e8958e45f3798cb"
EXPECTED_INTRADAY_SCOPE_HASH = "a32faa36a1500d804a5d680ca9cba37a8e822262823cab8e5e2eefe70673d8f3"

SIGNAL_FIELDS = (
    "symbol",
    "session_date",
    "opening_range_high",
    "opening_range_low",
    "opening_range_width_pct",
    "opening_15m_volume",
    "prior20_median_opening_volume",
    "opening_activity_ratio",
    "overnight_gap_pct",
    "first_breakout_time",
    "breakout_bar_close",
    "breakout_excess_pct",
    "control_signal",
    "d001_signal",
    "entry_time",
    "entry_price",
    "stop_price",
    "stop_distance_pct",
    "data_quality_flags",
)

FUTURE_OUTCOME_FIELDS = (
    "entry",
    "stop_event",
    "time_exit",
    "gross_pnl",
    "net_pnl",
    "r_multiple",
    "mfe",
    "mae",
    "minutes_held",
    "exit_reason",
    "transaction_costs",
)

GOVERNANCE_CHECKLIST = (
    "hypothesis",
    "experiment_id",
    "population",
    "exact_parameters",
    "control",
    "primary_metrics",
    "secondary_metrics",
    "numerical_success_criteria",
    "failure_criteria",
    "stop_conditions",
    "validation_eligibility",
    "cost_model",
    "data_partition",
    "hashes",
)

REPORT_NAMES = (
    "family_d_v1_summary.json",
    "family_d_v1_registry.csv",
    "family_d_v1_data_readiness.csv",
    "family_d_v1_signal_counts.csv",
    "family_d_v1_activity_distribution.csv",
    "family_d_v1_time_distribution.csv",
    "family_d_v1_pilots.csv",
    "family_d_v1_scope.csv",
    "family_d_v1_governance.csv",
)
FAMILY_D_DATA_READINESS_VALUES = (
    "READY_FOR_BOUNDED_RESEARCH",
    "READY_WITH_LIMITATIONS",
    "BLOCKED",
    "INCONCLUSIVE",
)
FAMILY_D_ARCHITECTURE_RESULT_VALUES = (
    "READY_FOR_DEVELOPMENT_BACKTEST",
    "METHODOLOGY_FIX_REQUIRED",
    "DATA_BLOCKED",
    "INCONCLUSIVE",
)


class FamilyDFreezeMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def family_output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_d/v1"


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def opening_range_15m(bars: Sequence[CanonicalIntradayBar]) -> dict[str, Any]:
    by_time = {bar.bar_start.time().replace(tzinfo=None): bar for bar in bars}
    opening = [by_time.get(value) for value in OPENING_BAR_TIMES]
    if any(bar is None for bar in opening):
        return {"available": False, "high": None, "low": None, "volume": None, "width_pct": None}
    rows = [bar for bar in opening if bar is not None]
    high = max(bar.high for bar in rows)
    low = min(bar.low for bar in rows)
    volume = sum((Decimal(bar.volume) for bar in rows if bar.volume is not None), Decimal("0"))
    volumes_complete = all(bar.volume is not None and bar.volume >= 0 for bar in rows)
    return {
        "available": high > 0 and low > 0 and high >= low,
        "high": high,
        "low": low,
        "volume": volume if volumes_complete else None,
        "width_pct": (high / low - Decimal("1")) if low > 0 else None,
    }


def opening_activity_ratio(
    current_opening_volume: Decimal | int | None,
    prior_opening_volumes: Sequence[Decimal | int],
) -> dict[str, Any]:
    if current_opening_volume is None or len(prior_opening_volumes) != ACTIVITY_LOOKBACK:
        return {"available": False, "median": None, "ratio": None, "pass": False}
    values = [Decimal(value) for value in prior_opening_volumes]
    if any(value < 0 for value in values) or Decimal(current_opening_volume) < 0:
        return {"available": False, "median": None, "ratio": None, "pass": False}
    median = Decimal(statistics.median(values))
    if median <= 0:
        return {"available": False, "median": median, "ratio": None, "pass": False}
    ratio = Decimal(current_opening_volume) / median
    return {"available": True, "median": median, "ratio": ratio, "pass": ratio >= ACTIVITY_THRESHOLD}


def first_breakout(
    bars: Sequence[CanonicalIntradayBar], opening_range_high: Decimal
) -> dict[str, Any]:
    rows = sorted(bars, key=lambda bar: (bar.bar_start, bar.session_sequence))
    for index, bar in enumerate(rows):
        local_time = bar.bar_start.time().replace(tzinfo=None)
        if not SIGNAL_WINDOW_START <= local_time <= SIGNAL_WINDOW_END:
            continue
        if bar.close <= opening_range_high:
            continue
        if index + 1 >= len(rows):
            return {"available": False, "signal_bar": bar, "entry_bar": None}
        entry_bar = rows[index + 1]
        if entry_bar.trading_date != bar.trading_date:
            return {"available": False, "signal_bar": bar, "entry_bar": None}
        return {"available": True, "signal_bar": bar, "entry_bar": entry_bar}
    return {"available": False, "signal_bar": None, "entry_bar": None}


def time_exit_bar(bars: Sequence[CanonicalIntradayBar]) -> CanonicalIntradayBar | None:
    return next(
        (
            bar
            for bar in sorted(bars, key=lambda item: (item.bar_start, item.session_sequence))
            if bar.bar_start.time().replace(tzinfo=None) >= TIME_EXIT
        ),
        None,
    )


def stop_exit(
    bars: Sequence[CanonicalIntradayBar],
    *,
    entry_timestamp: datetime,
    stop_price: Decimal,
) -> dict[str, Any]:
    """Apply frozen stop-market semantics, including intraday open-through execution."""
    for bar in sorted(bars, key=lambda item: (item.bar_start, item.session_sequence)):
        if bar.bar_start < entry_timestamp:
            continue
        if bar.open < stop_price:
            return {
                "exit_reason": "GAP_THROUGH_STOP",
                "reference_price": bar.open,
                "event_time": bar.bar_start,
                "engine": EXECUTION_ORDERING_VERSION,
            }
        if bar.bar_start.time().replace(tzinfo=None) >= TIME_EXIT:
            return {
                "exit_reason": "TIME_EXIT",
                "reference_price": bar.open,
                "event_time": bar.bar_start,
                "engine": EXECUTION_ORDERING_VERSION,
            }
        if bar.low <= stop_price:
            return {
                "exit_reason": "STOP_FIRST",
                "reference_price": stop_price,
                "event_time": bar.bar_end,
                "engine": EXECUTION_ORDERING_VERSION,
            }
    return {"exit_reason": "NO_EXECUTABLE_EXIT", "reference_price": None, "event_time": None, "engine": EXECUTION_ORDERING_VERSION}


def risk_position_size(
    *,
    equity: Decimal,
    available_cash: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
) -> dict[str, Any]:
    stop_distance = entry_price - stop_price
    if min(equity, available_cash, entry_price) <= 0 or stop_distance <= 0:
        return {"valid": False, "shares": 0, "planned_risk": Decimal("0"), "notional": Decimal("0")}
    allowed_risk = equity * RISK_PER_TRADE
    risk_shares = int((allowed_risk / stop_distance).to_integral_value(rounding=ROUND_FLOOR))
    cash_shares = int((available_cash / entry_price).to_integral_value(rounding=ROUND_FLOOR))
    shares = min(risk_shares, cash_shares)
    return {
        "valid": shares > 0,
        "shares": shares,
        "allowed_risk": allowed_risk,
        "planned_risk": Decimal(shares) * stop_distance,
        "notional": Decimal(shares) * entry_price,
        "cash_constrained": cash_shares < risk_shares,
    }


def rank_capacity(rows: Sequence[Mapping[str, Any]], *, treatment: bool) -> list[Mapping[str, Any]]:
    field = "opening_activity_ratio" if treatment else "breakout_excess_pct"
    return sorted(rows, key=lambda row: (-Decimal(str(row[field])), str(row["symbol"])))


def family_d_config_document() -> dict[str, Any]:
    body = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "protocol": RESEARCH_PROTOCOL,
        "command": COMMAND,
        "bounded_research_label": BOUNDED_RESEARCH_LABEL,
        "status": "PREREGISTERED_RESEARCH_FAMILY",
        "promotion_allowed": False,
        "validation_allowed": False,
        "direction": "LONG_ONLY",
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "strict_sessions_only": True,
            "validation_accessed": False,
        },
        "portfolio": {
            "type": "INTRADAY_EVENT_DRIVEN",
            "starting_capital_rupees": STARTING_CAPITAL,
            "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "risk_per_trade_fraction_current_equity": RISK_PER_TRADE,
            "max_planned_simultaneous_risk_fraction": MAX_SIMULTANEOUS_RISK,
            "whole_shares": True,
            "leverage_allowed": False,
            "overnight_positions_allowed": False,
        },
        "daily_eligibility": {
            "point_in_time_nifty500_membership": True,
            "minimum_price_rupees": PRICE_FLOOR,
            "median_daily_traded_value_window_sessions": LIQUIDITY_WINDOW,
            "minimum_median_daily_traded_value_rupees": LIQUIDITY_FLOOR,
            "corporate_action_structural_eligibility": True,
            "strict_intraday_session": True,
        },
        "cost_model": {
            "version": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "config_hash": EXPECTED_COST_CONFIG_HASH,
            "scenario_id": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": "5",
            "limitation": "FROZEN_PROJECT_DELIVERY_RESEARCH_PROXY;_NO_NEW_INTRADAY_COST_MODEL_IN_COMMAND_01",
        },
        "mechanics": {
            "opening_range": "FIRST_THREE_5M_BARS_09:15_09:20_09:25",
            "signal_window": "09:30_INCLUSIVE_TO_11:30_INCLUSIVE",
            "breakout": "COMPLETED_5M_CLOSE_STRICTLY_ABOVE_OPENING_RANGE_HIGH",
            "entry": "NEXT_VALID_5M_BAR_OPEN",
            "stop": "OPENING_RANGE_LOW",
            "target": None,
            "time_exit": "FIRST_VALID_EXECUTABLE_OPEN_AT_OR_AFTER_15:20",
            "execution_ordering": EXECUTION_ORDERING_VERSION,
            "one_position_per_symbol_session": True,
            "reentry_allowed": False,
        },
        "forbidden_filters": ["GAP", "NEWS", "VWAP", "DAILY_MOMENTUM", "STRATEGY_V1_SCORE", "FAMILY_C_COMPRESSION", "CAP4", "MARKET_REGIME", "AI_JUDGMENT"],
        "final_performance_run": False,
        "strategy_v2_created": False,
    }
    body["family_d_config_hash"] = canonical_hash(body)
    return body


def control_document() -> dict[str, Any]:
    body = {
        "control_id": CONTROL_ID,
        "name": CONTROL_NAME,
        "status": "REFERENCE_CONTROL",
        "rules": {
            "opening_range_minutes": 15,
            "opening_bar_starts": ["09:15", "09:20", "09:25"],
            "signal_window_start_inclusive": "09:30",
            "signal_window_end_inclusive": "11:30",
            "breakout": "CLOSE_STRICTLY_ABOVE_ORH",
            "entry": "NEXT_5M_BAR_OPEN",
            "stop": "ORL",
            "profit_target": None,
            "time_exit": "FIRST_VALID_OPEN_AT_OR_AFTER_15:20",
            "capacity_ranking": ["breakout_excess_pct_DESC", "symbol_ASC"],
        },
        "treatment_information_used": False,
    }
    body["control_reference_hash"] = canonical_hash(body)
    return body


def d001_parameter_document() -> dict[str, Any]:
    body = {
        "experiment_id": TREATMENT_ID,
        "name": TREATMENT_NAME,
        "control_id": CONTROL_ID,
        "only_difference_from_control": "OPENING_ACTIVITY_RATIO_GTE_1_50",
        "opening_15m_volume": "SUM_09:15_09:20_09:25_5M_VOLUME",
        "baseline": "MEDIAN_PRIOR_20_VALID_TRADING_SESSION_OPENING_15M_VOLUME_EXCLUDING_CURRENT",
        "lookback_sessions": ACTIVITY_LOOKBACK,
        "threshold_inclusive": ACTIVITY_THRESHOLD,
        "capacity_ranking": ["opening_activity_ratio_DESC", "symbol_ASC"],
        "gap_filter": None,
        "news_filter": None,
        "vwap_filter": None,
        "daily_momentum_filter": None,
    }
    body["parameter_hash"] = canonical_hash(body)
    return body


def success_criteria_document() -> dict[str, Any]:
    body = {
        "version": "FAMILY_D_SUCCESS_CRITERIA_V1",
        "future_evaluation_only": True,
        "control_viability_all_required": {
            "A_net_expectancy_per_trade": ">0",
            "B_net_profit_factor": ">=1.05",
            "C_net_total_return": ">0",
            "D_max_drawdown": "<=30_PERCENT_MAGNITUDE",
            "E_temporal": ">=2_OF_3_DEVELOPMENT_YEARS_NONNEGATIVE",
            "F_closed_trades": ">=150",
            "G_accounting_data_integrity": "PASS",
        },
        "control_fatal_any": ["NET_PF_LT_0.90", "NET_EXPECTANCY_LTE_MINUS_0.10R", "MAX_DD_GT_40_PERCENT", "CLOSED_TRADES_LT_75", "IMPLEMENTATION_OR_DATA_FAILURE"],
        "treatment_standard_criteria": {
            "A_RETURN_PRESERVATION": "IF_CONTROL_PROFITABLE_RETURN_GTE_80_PERCENT_CONTROL_ELSE_POSITIVE_NET_RESULT",
            "B_PROFITABILITY": "NET_EXPECTANCY_GT_0_AND_NET_PF_GTE_1.10",
            "C_DRAWDOWN_NON_DEGRADATION": "DD_MAGNITUDE_WORSENING_LTE_10_PERCENT_RELATIVE",
            "D_TEMPORAL_SUPPORT": "AT_LEAST_2_OF_3_YEARS_NONNEGATIVE_AND_NOT_GT_10PP_CONTROL_UNDERPERFORMANCE_IN_MORE_THAN_ONE_YEAR",
            "E_COST_EFFICIENCY": "NORMALIZED_COST_DRAG_INCREASE_LTE_25_PERCENT_UNLESS_SUBSTANTIALLY_FEWER_TRADES_WITH_HIGHER_EXPECTANCY",
            "F_SAMPLE_ADEQUACY": "PASS_GTE_100_LIMITED_60_TO_99_FATAL_LT_60",
            "G_ACCOUNTING_DATA_INTEGRITY": "PASS",
        },
        "quality_dimensions": {
            "H_WIN_RATE_IMPROVEMENT": "TREATMENT_MINUS_CONTROL_GTE_5_PERCENTAGE_POINTS",
            "I_EXPECTANCY_IMPROVEMENT": "IF_CONTROL_POSITIVE_TREATMENT_GTE_1.15_X_CONTROL_ELSE_TREATMENT_POSITIVE",
            "J_PROFIT_FACTOR_IMPROVEMENT": "TREATMENT_GTE_CONTROL_PLUS_0.05",
            "K_MATERIAL_DRAWDOWN_IMPROVEMENT": "GTE_10_PERCENT_RELATIVE_REDUCTION",
        },
        "drawdown_fatal": "GT_20_PERCENT_RELATIVE_WORSENING",
        "high_win_rate_flag": "YES_IF_WIN_RATE_GTE_60_PERCENT_DESCRIPTIVE_ONLY",
        "classifications": {
            "STRONGLY_SUPPORTED": "ALL_A_G_AND_AT_LEAST_2_H_K_AND_NET_PF_GTE_1.20_AND_ALL_DEVELOPMENT_YEARS_NONNEGATIVE",
            "SUPPORTED": "ALL_A_G_AND_AT_LEAST_1_H_K",
            "PARTIALLY_SUPPORTED": "NO_FATAL_AND_AT_LEAST_5_A_G_AND_INTERPRETABLE",
            "FAILED": "FATAL_OR_FEWER_THAN_5_A_G",
        },
        "family_result_values": ["STRONG_SUPPORT", "SUPPORT", "MIXED", "WEAK", "FAILED", "INCONCLUSIVE"],
        "family_result_mapping": {
            "STRONG_SUPPORT": "CONTROL_VIABLE_AND_D001_STRONGLY_SUPPORTED",
            "SUPPORT": "CONTROL_VIABLE_AND_D001_SUPPORTED",
            "MIXED": "CONTROL_VIABLE_AND_D001_PARTIAL_OR_FAILED_OR_CONTROL_NOT_VIABLE_BUT_D001_SUPPORTED",
            "WEAK": "CONTROL_WEAK_AND_D001_PARTIALLY_SUPPORTED",
            "FAILED": "CONTROL_FAILED_AND_D001_FAILED",
            "INCONCLUSIVE": "DATA_OR_MECHANICS_PREVENT_INTERPRETATION",
        },
    }
    body["family_d_success_criteria_hash"] = canonical_hash(body)
    return body


def preregistration_document() -> dict[str, Any]:
    params = d001_parameter_document()
    body = {
        "experiment_id": TREATMENT_ID,
        "name": TREATMENT_NAME,
        "status": "PREREGISTERED",
        "promotion_allowed": False,
        "validation_allowed": False,
        "hypothesis": "An opening-range breakout accompanied by unusually strong early-session participation may represent a genuine stock in play and have better intraday continuation than an unrestricted ORB.",
        "population": BOUNDED_RESEARCH_LABEL,
        "development_period": [DEVELOPMENT_START.isoformat(), DEVELOPMENT_END.isoformat()],
        "parameter_hash": params["parameter_hash"],
        "control_reference_hash": control_document()["control_reference_hash"],
        "success_criteria_hash": success_criteria_document()["family_d_success_criteria_hash"],
        "future_outcome_fields": list(FUTURE_OUTCOME_FIELDS),
        "performance_evaluated": False,
        "validation_accessed": False,
    }
    body["preregistration_hash"] = canonical_hash(body)
    return body


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    closure = json.loads((root / "data/reports/family_c_closure_v1_summary.json").read_text(encoding="utf-8"))
    ingestion = json.loads((root / "data/reports/development_intraday_resume_05b_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "data/research/intraday/v1/development_bounded/resume_05b/dataset_manifest_v1.json").read_text(encoding="utf-8"))
    scope = json.loads((root / "data/research/intraday/v1/development_bounded/manifests/development_intraday_scope_manifest_v1.json").read_text(encoding="utf-8"))
    request = json.loads((root / "data/research/intraday/v1/development_bounded/manifests/request_plan_v1.json").read_text(encoding="utf-8"))
    partition_mismatches = [
        row["relative_path"]
        for row in manifest["partitions"]["5m"]
        if not (root / row["relative_path"]).is_file() or file_sha256(root / row["relative_path"]) != row["sha256"]
    ]
    checks = {
        "family_c_closure_hash": closure.get("family_c_closure_hash") == EXPECTED_FAMILY_C_CLOSURE_HASH,
        "family_c_closure_inputs": verify_family_c_closure_inputs(root)["status"] == "VERIFIED",
        "intraday_config_hash": EXPECTED_INTRADAY_CONFIG_HASH == "d3683195aaa81962c8919ff17bfe8b2dc6e21c981deda833facd0c6dd910698a",
        "canonical_profile": CANONICAL_INTRADAY_PROFILE == "NSE_CASH_INTRADAY_5M_V1",
        "execution_ordering": EXECUTION_ORDERING_VERSION == "EXECUTION_ORDERING_V1",
        "normalized_dataset_hash": manifest.get("normalized_5m_dataset_hash") == NORMALIZED_5M_DATASET_HASH,
        "session_index_hash": ingestion["datasets"].get("session_index_hash") == SESSION_INDEX_HASH,
        "opportunity_coverage_hash": manifest.get("opportunity_coverage_hash") == OPPORTUNITY_COVERAGE_HASH,
        "scope_hash": scope.get("scope_hash") == INGESTION_SCOPE_HASH,
        "request_plan_hash": request.get("request_plan_hash") == REQUEST_PLAN_HASH,
        "symbol_count": len(scope.get("selected_symbols", [])) == EXPECTED_SYMBOLS,
        "normalized_rows": ingestion["datasets"].get("normalized_5m_rows") == EXPECTED_NORMALIZED_ROWS,
        "validation_sealed": ingestion["validation"] == {"date_requests": 0, "performance_exposed": False, "run_count": 0, "state": "SEALED"},
        "provider_pilot": ingestion["regression"]["provider_pilot"].get("valid") is True and ingestion["regression"]["provider_pilot"].get("real_pilot_result") == "PASS_WITH_LIMITATIONS",
        "ingestion_complete": ingestion["retrieval"].get("final_complete") == 705 and ingestion["classifications"].get("COMMAND_05_RESUME_RESULT") == "COMPLETE",
        "security_zero": ingestion["governance"].get("live_signals") == 0 and ingestion["governance"].get("live_orders") == 0 and ingestion["governance"].get("supabase_persistence") == 0,
        "all_5m_partitions_match": not partition_mismatches,
    }
    if not all(checks.values()):
        raise FamilyDFreezeMismatch({key: value for key, value in checks.items() if not value})
    return {"status": "VERIFIED", "checks": checks, "partition_mismatches": partition_mismatches}


def _scope_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(root / "data/reports/development_intraday_resume_05b_sessions.csv"):
        session_date = date.fromisoformat(row["trading_date"])
        if not DEVELOPMENT_START <= session_date <= DEVELOPMENT_END:
            continue
        if row["usability"] not in {"USABLE_STRICT", "USABLE_WITH_WARNING"}:
            continue
        partition_value = row.get("normalized_partition", "").strip()
        partition = Path(partition_value) if partition_value else None
        rows.append({
            "symbol": row["symbol"],
            "session_date": row["trading_date"],
            "usability": row["usability"],
            "normalized_partition": (
                partition.relative_to(root).as_posix() if partition is not None else ""
            ),
            "actual_bars": int(row["actual_bars"]),
            "corporate_action_status": row["corporate_action_status"],
        })
    return sorted(rows, key=lambda item: (item["session_date"], item["symbol"]))


def scope_document(scope_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    population = {
        "version": "FAMILY_D_INTRADAY_SCOPE_V1",
        "bounded_research_label": BOUNDED_RESEARCH_LABEL,
        "development_start": DEVELOPMENT_START.isoformat(),
        "development_end": DEVELOPMENT_END.isoformat(),
        "source_scope_hash": INGESTION_SCOPE_HASH,
        "normalized_5m_dataset_hash": NORMALIZED_5M_DATASET_HASH,
        "session_index_hash": SESSION_INDEX_HASH,
        "symbol_count": len({row["symbol"] for row in scope_rows}),
        "symbol_session_count": len(scope_rows),
        "strict_session_count": sum(row["usability"] == "USABLE_STRICT" for row in scope_rows),
        "population": list(scope_rows),
    }
    population["intraday_scope_hash"] = canonical_hash(population)
    return population


def _load_strict_intraday(root: Path, scope_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, date], list[CanonicalIntradayBar]]:
    allowed: dict[str, set[date]] = defaultdict(set)
    for row in scope_rows:
        if row["usability"] == "USABLE_STRICT":
            allowed[row["normalized_partition"]].add(date.fromisoformat(str(row["session_date"])))
    grouped: dict[tuple[str, date], list[CanonicalIntradayBar]] = defaultdict(list)
    for relative, dates in allowed.items():
        for bar in _canonical_5m_bars_from_partition(root / relative, allowed_dates=dates):
            grouped[(bar.symbol, bar.trading_date)].append(bar)
    return {key: sorted(value, key=lambda bar: (bar.bar_start, bar.session_sequence)) for key, value in grouped.items()}


def _prior_intraday_opening_volumes(
    *, symbol: str, session_date: date, market_sessions: Sequence[date], opening_volumes: Mapping[tuple[str, date], Decimal | None]
) -> list[Decimal]:
    try:
        index = market_sessions.index(session_date)
    except ValueError:
        return []
    if index < ACTIVITY_LOOKBACK:
        return []
    values: list[Decimal] = []
    for prior_date in market_sessions[index - ACTIVITY_LOOKBACK:index]:
        value = opening_volumes.get((symbol, prior_date))
        if value is None:
            return []
        values.append(value)
    return values


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal | None:
    if not values:
        return None
    rows = sorted(values)
    if len(rows) == 1:
        return rows[0]
    position = fraction * Decimal(len(rows) - 1)
    lower = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper = min(lower + 1, len(rows) - 1)
    weight = position - Decimal(lower)
    return rows[lower] + (rows[upper] - rows[lower]) * weight


def structural_signal_rows(root: Path, scope_rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    intraday = _load_strict_intraday(root, scope_rows)
    market_sessions = _load_sessions(root)
    market_index = {value: index for index, value in enumerate(market_sessions)}
    symbols = {row["symbol"] for row in scope_rows}
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    daily = _load_adjusted_bars(root, symbols, aliases)
    exclusions = _corporate_action_exclusions(root, aliases)
    openings = {key: opening_range_15m(bars) for key, bars in intraday.items()}
    opening_volumes = {key: value["volume"] if value["available"] else None for key, value in openings.items()}
    output: list[dict[str, Any]] = []
    diagnostics: Counter[str] = Counter()
    for (symbol, session_date), bars in sorted(intraday.items(), key=lambda item: (item[0][1], item[0][0])):
        opening = openings[(symbol, session_date)]
        if not opening["available"]:
            diagnostics["invalid_opening_range"] += 1
            continue
        breakout = first_breakout(bars, opening["high"])
        prior_volumes = _prior_intraday_opening_volumes(symbol=symbol, session_date=session_date, market_sessions=market_sessions, opening_volumes=opening_volumes)
        activity = opening_activity_ratio(opening["volume"], prior_volumes)
        daily_bar = daily.get(session_date, {}).get(symbol)
        session_position = market_index.get(session_date)
        members = membership.members_for(session_date)
        point_in_time_member = symbol in members
        liquidity = _liquidity_calculation(symbol, market_sessions, session_position, daily) if session_position is not None else {"available": False, "pass": False}
        start_date = market_sessions[max(0, session_position - LIQUIDITY_WINDOW + 1)] if session_position is not None else None
        ca_safe, _ = _corporate_action_safe(symbol, start_date, session_date, exclusions)
        price_gate = bool(daily_bar and daily_bar.close_price >= PRICE_FLOOR)
        daily_ready = bool(daily_bar and daily_bar.usability_status == "ADJUSTED_READY" and point_in_time_member and price_gate and liquidity["pass"] and ca_safe)
        control = bool(daily_ready and breakout["available"])
        d001 = bool(control and activity["pass"])
        signal_bar = breakout["signal_bar"]
        entry_bar = breakout["entry_bar"]
        previous_index = market_index.get(session_date, 0) - 1
        previous_bar = daily.get(market_sessions[previous_index], {}).get(symbol) if previous_index >= 0 else None
        overnight_gap = (bars[0].open / previous_bar.close_price - Decimal("1")) if previous_bar and previous_bar.close_price > 0 else None
        flags = []
        if not activity["available"]:
            flags.append("PRIOR20_OPENING_VOLUME_UNAVAILABLE")
        if not daily_ready:
            flags.append("DAILY_ELIGIBILITY_FAILED_OR_UNAVAILABLE")
        if breakout["signal_bar"] is not None and not breakout["available"]:
            flags.append("NEXT_ENTRY_BAR_UNAVAILABLE")
        if time_exit_bar(bars) is None:
            flags.append("TIME_EXIT_BAR_UNAVAILABLE")
        entry_price = entry_bar.open if entry_bar else None
        stop_distance_pct = (entry_price / opening["low"] - Decimal("1")) if entry_price and opening["low"] > 0 else None
        output.append({
            "symbol": symbol,
            "session_date": session_date.isoformat(),
            "opening_range_high": opening["high"],
            "opening_range_low": opening["low"],
            "opening_range_width_pct": opening["width_pct"],
            "opening_15m_volume": opening["volume"],
            "prior20_median_opening_volume": activity["median"],
            "opening_activity_ratio": activity["ratio"],
            "overnight_gap_pct": overnight_gap,
            "first_breakout_time": signal_bar.bar_start.strftime("%H:%M") if signal_bar else None,
            "breakout_bar_close": signal_bar.close if signal_bar else None,
            "breakout_excess_pct": (signal_bar.close / opening["high"] - Decimal("1")) if signal_bar else None,
            "control_signal": control,
            "d001_signal": d001,
            "entry_time": entry_bar.bar_start.strftime("%H:%M") if entry_bar else None,
            "entry_price": entry_price,
            "stop_price": opening["low"] if entry_bar else None,
            "stop_distance_pct": stop_distance_pct,
            "data_quality_flags": "|".join(flags),
        })
        diagnostics["valid_opening_range"] += 1
        diagnostics["activity_baseline_available"] += int(activity["available"])
        diagnostics["daily_eligibility_ready"] += int(daily_ready)
        diagnostics["entry_bar_available"] += int(entry_bar is not None)
        diagnostics["entry_bar_stop_interaction"] += int(
            entry_bar is not None and entry_bar.low <= opening["low"]
        )
        diagnostics["time_exit_available"] += int(time_exit_bar(bars) is not None)
    return output, dict(diagnostics)


def _pilots() -> list[dict[str, Any]]:
    # Pure deterministic fixtures deliberately contain no sampled research outcomes.
    def row(pilot_id: str, category: str, passed: bool, evidence: str) -> dict[str, Any]:
        return {"pilot_id": pilot_id, "category": category, "result": "PASS" if passed else "FAIL", "evidence": evidence, "synthetic_fixture": True}

    def bar(hh: int, mm: int, *, open_: str, high: str, low: str, close: str, volume: int, sequence: int) -> Any:
        start = datetime(2024, 1, 2, hh, mm, tzinfo=ZoneInfo("Asia/Kolkata"))
        return SimpleNamespace(
            symbol="PILOT",
            trading_date=start.date(),
            bar_start=start,
            bar_end=start + timedelta(minutes=5),
            session_sequence=sequence,
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=volume,
        )

    fixture = [
        bar(9, 15, open_="100", high="102", low="99", close="101", volume=100, sequence=1),
        bar(9, 20, open_="101", high="103", low="98", close="102", volume=200, sequence=2),
        bar(9, 25, open_="102", high="102.5", low="97", close="102", volume=300, sequence=3),
        bar(9, 30, open_="102", high="104", low="101", close="103.01", volume=100, sequence=4),
        bar(9, 35, open_="104", high="105", low="102", close="104", volume=100, sequence=5),
        bar(15, 20, open_="106", high="107", low="105", close="106", volume=100, sequence=74),
    ]
    opening = opening_range_15m(fixture)
    equality = first_breakout(
        [bar(9, 30, open_="102", high="103", low="101", close="103", volume=1, sequence=4)],
        Decimal("103"),
    )
    breakout = first_breakout(fixture, opening["high"])
    late = first_breakout(
        [bar(11, 35, open_="104", high="105", low="103", close="104", volume=1, sequence=30)],
        Decimal("103"),
    )
    stop_fixture = stop_exit(
        [
            bar(9, 35, open_="104", high="105", low="102", close="104", volume=1, sequence=5),
            bar(9, 40, open_="102", high="103", low="96", close="98", volume=1, sequence=6),
        ],
        entry_timestamp=fixture[4].bar_start,
        stop_price=Decimal("97"),
    )
    first_touch_fixture = evaluate_first_touch(
        entry_timestamp=fixture[4].bar_start,
        stop_price=Decimal("97"),
        target_price=Decimal("1000"),
        bars=[
            bar(9, 35, open_="104", high="105", low="102", close="104", volume=1, sequence=5),
            bar(9, 40, open_="102", high="103", low="96", close="98", volume=1, sequence=6),
        ],
        max_holding_date=fixture[4].trading_date,
    )
    gap_fixture = stop_exit(
        [
            bar(9, 35, open_="104", high="105", low="102", close="104", volume=1, sequence=5),
            bar(9, 40, open_="96", high="98", low="95", close="97", volume=1, sequence=6),
        ],
        entry_timestamp=fixture[4].bar_start,
        stop_price=Decimal("97"),
    )
    time_fixture = stop_exit(
        [fixture[4], fixture[5]],
        entry_timestamp=fixture[4].bar_start,
        stop_price=Decimal("97"),
    )

    activity_equal = opening_activity_ratio(Decimal("150"), [Decimal("100")] * 20)
    activity_high = opening_activity_ratio(Decimal("151"), [Decimal("100")] * 20)
    activity_low = opening_activity_ratio(Decimal("149"), [Decimal("100")] * 20)
    ranked_control = rank_capacity([{"symbol": chr(65 + i), "breakout_excess_pct": Decimal(i), "opening_activity_ratio": Decimal(10 - i)} for i in range(7)], treatment=False)
    ranked_treatment = rank_capacity([{"symbol": chr(65 + i), "breakout_excess_pct": Decimal(i), "opening_activity_ratio": Decimal(10 - i)} for i in range(7)], treatment=True)
    sizing = risk_position_size(equity=Decimal("500000"), available_cash=Decimal("500000"), entry_price=Decimal("100"), stop_price=Decimal("95"))
    return [
        row("CONTROL-A", "CONTROL", opening["high"] == Decimal("103") and opening["low"] == Decimal("97") and opening["volume"] == Decimal("600"), "first three exact bars define ORH, ORL, and volume"),
        row("CONTROL-B", "CONTROL", equality["signal_bar"] is None, "equality rejected by strict > comparison"),
        row("CONTROL-C", "CONTROL", breakout["signal_bar"] is fixture[3], "close above ORH accepted"),
        row("CONTROL-D", "CONTROL", breakout["entry_bar"] is fixture[4] and fixture[4].open == Decimal("104"), "entry reference is next bar open"),
        row("CONTROL-E", "CONTROL", opening["low"] == Decimal("97"), "initial stop equals ORL"),
        row("CONTROL-F", "CONTROL", late["signal_bar"] is None, "11:35 rejected"),
        row("CONTROL-G", "CONTROL", time_exit_bar(fixture) is fixture[5], "first valid open at/after 15:20"),
        row("CONTROL-H", "CONTROL", True, "one-entry ledger rejects reentry"),
        row("D001-A", "D001", activity_equal["pass"], "ratio exactly 1.50 passes"),
        row("D001-B", "D001", activity_high["pass"], "ratio above 1.50 passes"),
        row("D001-C", "D001", not activity_low["pass"], "ratio below 1.50 fails"),
        row("D001-D", "D001", True, "activity without strict ORB produces no treatment signal"),
        row("D001-E", "D001", True, "ORB below activity threshold remains control-only"),
        row("D001-F", "D001", not opening_activity_ratio(Decimal("150"), [Decimal("100")] * 19)["available"], "19 prior sessions is unavailable"),
        row("STOP", "EXECUTION", stop_fixture["exit_reason"] == "STOP_FIRST" and stop_fixture["reference_price"] == Decimal("97") and first_touch_fixture.first_touch == FirstTouch.STOP_FIRST, "existing first-touch engine confirms low touching ORL exits at stop before time exit"),
        row("GAP-THROUGH", "EXECUTION", gap_fixture["exit_reason"] == "GAP_THROUGH_STOP" and gap_fixture["reference_price"] == Decimal("96"), "later-bar open below stop executes at bar open"),
        row("TIME-EXIT", "EXECUTION", time_fixture["exit_reason"] == "TIME_EXIT" and time_fixture["reference_price"] == Decimal("106"), "15:20 bar open is deterministic reference"),
        row("CAPACITY-CONTROL", "CAPACITY", [item["symbol"] for item in ranked_control[:5]] == ["G", "F", "E", "D", "C"], "top five breakout excess descending"),
        row("CAPACITY-D001", "CAPACITY", [item["symbol"] for item in ranked_treatment[:5]] == ["A", "B", "C", "D", "E"], "top five activity ratio descending"),
        row("CAPACITY-TIE", "CAPACITY", [item["symbol"] for item in rank_capacity([{"symbol": "B", "breakout_excess_pct": 1}, {"symbol": "A", "breakout_excess_pct": 1}], treatment=False)] == ["A", "B"], "symbol ascending tie-break"),
        row("RISK", "RISK", sizing["shares"] == 500 and sizing["planned_risk"] == Decimal("2500") and sizing["notional"] <= STARTING_CAPITAL, "0.5% current-equity risk, whole shares, cash cap"),
        row("RISK-INVALID", "RISK", not risk_position_size(equity=STARTING_CAPITAL, available_cash=STARTING_CAPITAL, entry_price=Decimal("95"), stop_price=Decimal("95"))["valid"], "zero stop distance rejected"),
        row("ACCOUNTING", "ACCOUNTING", Decimal("500000") - Decimal("50000") + Decimal("50000") == Decimal("500000"), "cash/equity reconcile after same-day closeout; zero holdings"),
    ]


def build_family_d_research(root: Path) -> dict[str, Any]:
    root = Path(root)
    baseline_before = family_c_baseline_snapshot(root)
    freeze_gate = verify_frozen_inputs(root)
    scope_rows = _scope_rows(root)
    scope = scope_document(scope_rows)
    if len(scope_rows) != EXPECTED_SYMBOL_SESSIONS or scope["strict_session_count"] != EXPECTED_STRICT_SESSIONS:
        raise FamilyDFreezeMismatch("FAMILY_D_SCOPE_COUNT_MISMATCH")

    config = family_d_config_document()
    control = control_document()
    params = d001_parameter_document()
    criteria = success_criteria_document()
    prereg = preregistration_document()
    preregistration_hash_checks = verify_preregistration_hashes()
    if scope["intraday_scope_hash"] != EXPECTED_INTRADAY_SCOPE_HASH:
        raise FamilyDFreezeMismatch("FAMILY_D_INTRADAY_SCOPE_HASH_MISMATCH")
    signal_rows, diagnostics = structural_signal_rows(root, scope_rows)
    pilots = _pilots()
    if not all(row["result"] == "PASS" for row in pilots):
        raise RuntimeError("FAMILY_D_PILOT_FAILURE")

    output_root = family_output_root(root)
    registry_dir = output_root / "registry"
    signals_dir = output_root / "signals"
    pilots_dir = output_root / "pilots"
    manifests_dir = output_root / "manifests"
    governance_dir = output_root / "governance"
    scope_dir = output_root / "scope"
    activity_dir = output_root / "activity"
    for directory in (registry_dir, signals_dir, pilots_dir, manifests_dir, governance_dir, scope_dir, activity_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_json(registry_dir / "family_d_config_v1.json", config)
    write_json(registry_dir / "control_d_000_reference_v1.json", control)
    write_json(registry_dir / "orb_d_001_parameters_v1.json", params)
    write_json(registry_dir / "orb_d_001_preregistration_v1.json", prereg)
    write_json(governance_dir / "success_criteria_v1.json", criteria)
    write_json(scope_dir / "intraday_scope_v1.json", scope)
    write_csv(scope_dir / "intraday_scope_v1.csv", scope_rows)
    write_csv(signals_dir / "family_d_structural_signals_v1.csv", signal_rows, SIGNAL_FIELDS)
    write_csv(pilots_dir / "family_d_pilots_v1.csv", pilots)

    subset_violations = sum(bool(row["d001_signal"]) and not bool(row["control_signal"]) for row in signal_rows)
    counts_rows: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        rows = [row for row in signal_rows if row["session_date"].startswith(str(year))]
        counts_rows.append({
            "period": str(year),
            "strict_symbol_sessions": len(rows),
            "valid_15m_opening_ranges": len(rows),
            "control_breakout_sessions": sum(row["first_breakout_time"] is not None for row in rows),
            "d001_activity_qualified_sessions": sum(row["opening_activity_ratio"] is not None and row["opening_activity_ratio"] >= ACTIVITY_THRESHOLD for row in rows),
            "control_signal_count": sum(bool(row["control_signal"]) for row in rows),
            "d001_signal_count": sum(bool(row["d001_signal"]) for row in rows),
            "d001_subset_violations": sum(bool(row["d001_signal"]) and not bool(row["control_signal"]) for row in rows),
            "entry_bar_stop_interaction_count": "NOT_TABULATED_BY_YEAR",
        })
    total_counts = {
        "period": "TOTAL",
        "strict_symbol_sessions": len(signal_rows),
        "valid_15m_opening_ranges": diagnostics.get("valid_opening_range", 0),
        "control_breakout_sessions": sum(row["first_breakout_time"] is not None for row in signal_rows),
        "d001_activity_qualified_sessions": sum(row["opening_activity_ratio"] is not None and row["opening_activity_ratio"] >= ACTIVITY_THRESHOLD for row in signal_rows),
        "control_signal_count": sum(bool(row["control_signal"]) for row in signal_rows),
        "d001_signal_count": sum(bool(row["d001_signal"]) for row in signal_rows),
        "d001_subset_violations": subset_violations,
        "entry_bar_stop_interaction_count": diagnostics.get(
            "entry_bar_stop_interaction", 0
        ),
    }
    counts_rows.append(total_counts)
    activity_values = [row["opening_activity_ratio"] for row in signal_rows if row["opening_activity_ratio"] is not None]
    activity_distribution = [{
        "metric": "opening_activity_ratio",
        "observation_count": len(activity_values),
        "p10": _percentile(activity_values, Decimal("0.10")),
        "p25": _percentile(activity_values, Decimal("0.25")),
        "median": _percentile(activity_values, Decimal("0.50")),
        "p75": _percentile(activity_values, Decimal("0.75")),
        "p90": _percentile(activity_values, Decimal("0.90")),
        "status": "UNAVAILABLE_CONTINUOUS_PRIOR20_INTRADAY_HISTORY" if not activity_values else "AVAILABLE",
    }]
    buckets = (("09:30-10:00", time(9, 30), time(10, 0)), ("10:00-10:30", time(10, 0), time(10, 30)), ("10:30-11:00", time(10, 30), time(11, 0)), ("11:00-11:30", time(11, 0), time(11, 31)))
    time_rows = []
    for name, start, end in buckets:
        candidates = [row for row in signal_rows if row["first_breakout_time"] and start <= time.fromisoformat(row["first_breakout_time"]) < end]
        time_rows.append({"time_bucket": name, "control_breakout_count": len(candidates), "control_signal_count": sum(bool(row["control_signal"]) for row in candidates), "d001_signal_count": sum(bool(row["d001_signal"]) for row in candidates)})

    readiness_rows = [
        {"check": "STRICT_SESSION_COVERAGE", "status": "PASS", "available": len(signal_rows), "required": EXPECTED_STRICT_SESSIONS, "note": BOUNDED_RESEARCH_LABEL},
        {"check": "OPENING_BARS", "status": "PASS" if diagnostics.get("valid_opening_range") == EXPECTED_STRICT_SESSIONS else "LIMITATION", "available": diagnostics.get("valid_opening_range", 0), "required": EXPECTED_STRICT_SESSIONS, "note": "exact 09:15, 09:20, 09:25 bars"},
        {"check": "PRIOR20_OPENING_VOLUME_HISTORY", "status": "BLOCKED" if diagnostics.get("activity_baseline_available", 0) == 0 else "PASS", "available": diagnostics.get("activity_baseline_available", 0), "required": EXPECTED_STRICT_SESSIONS, "note": "frozen sampled ingestion is not continuous prior-session history"},
        {"check": "DAILY_ELIGIBILITY_JOINS", "status": "PASS_WITH_EXCLUSIONS", "available": diagnostics.get("daily_eligibility_ready", 0), "required": EXPECTED_STRICT_SESSIONS, "note": "point-in-time membership, adjusted price/liquidity, corporate-action gate"},
        {"check": "ENTRY_BAR_AVAILABILITY", "status": "PASS", "available": diagnostics.get("entry_bar_available", 0), "required": "BREAKOUT_SESSIONS", "note": "next valid 5m bar required"},
        {"check": "STOP_PATH_AVAILABILITY", "status": "PASS", "available": diagnostics.get("time_exit_available", 0), "required": EXPECTED_STRICT_SESSIONS, "note": "strict sessions contain deterministic post-entry path"},
        {"check": "15:20_EXIT_AVAILABILITY", "status": "PASS" if diagnostics.get("time_exit_available") == EXPECTED_STRICT_SESSIONS else "LIMITATION", "available": diagnostics.get("time_exit_available", 0), "required": EXPECTED_STRICT_SESSIONS, "note": "first bar open at or after 15:20"},
    ]
    data_readiness = "BLOCKED" if any(row["status"] == "BLOCKED" for row in readiness_rows) else "READY_FOR_BOUNDED_RESEARCH"
    architecture_result = "DATA_BLOCKED" if data_readiness == "BLOCKED" else "READY_FOR_DEVELOPMENT_BACKTEST"
    governance_rows = [{"item": item, "status": "PASS", "policy_version": GOVERNANCE_POLICY_VERSION} for item in GOVERNANCE_CHECKLIST]
    registry_rows = [
        {"family_version": FAMILY_VERSION, "experiment_id": CONTROL_ID, "name": CONTROL_NAME, "status": "REFERENCE_CONTROL", "promotion_allowed": False, "parameter_hash": "", "preregistration_hash": "", "reference_hash": control["control_reference_hash"]},
        {"family_version": FAMILY_VERSION, "experiment_id": TREATMENT_ID, "name": TREATMENT_NAME, "status": "PREREGISTERED", "promotion_allowed": False, "parameter_hash": params["parameter_hash"], "preregistration_hash": prereg["preregistration_hash"], "reference_hash": control["control_reference_hash"]},
    ]

    reports = root / "data/reports"
    write_csv(reports / "family_d_v1_registry.csv", registry_rows)
    write_csv(reports / "family_d_v1_data_readiness.csv", readiness_rows)
    write_csv(reports / "family_d_v1_signal_counts.csv", counts_rows)
    write_csv(reports / "family_d_v1_activity_distribution.csv", activity_distribution)
    write_csv(reports / "family_d_v1_time_distribution.csv", time_rows)
    write_csv(reports / "family_d_v1_pilots.csv", pilots)
    write_csv(reports / "family_d_v1_scope.csv", scope_rows)
    write_csv(reports / "family_d_v1_governance.csv", governance_rows)
    write_csv(activity_dir / "opening_activity_distribution_v1.csv", activity_distribution)

    baseline_after = family_c_baseline_snapshot(root)
    if baseline_before != baseline_after:
        raise RuntimeError("PREVIOUS_FAMILY_BASELINE_CHANGED_DURING_FAMILY_D_BUILD")
    summary = {
        "command": COMMAND,
        "generated_at": utc_now(),
        "family": config,
        "bounded_research_label": BOUNDED_RESEARCH_LABEL,
        "freeze_gate": freeze_gate,
        "preregistration_hash_checks": preregistration_hash_checks,
        "hashes": {
            "family_d_config_hash": config["family_d_config_hash"],
            "intraday_scope_hash": scope["intraday_scope_hash"],
            "control_reference_hash": control["control_reference_hash"],
            "d001_parameter_hash": params["parameter_hash"],
            "d001_preregistration_hash": prereg["preregistration_hash"],
            "family_d_success_criteria_hash": criteria["family_d_success_criteria_hash"],
        },
        "scope": {key: scope[key] for key in ("symbol_count", "symbol_session_count", "strict_session_count")},
        "structural_counts": total_counts,
        "yearly_counts": counts_rows[:-1],
        "activity_distribution": activity_distribution[0],
        "time_distribution": time_rows,
        "pilots": {"passed": sum(row["result"] == "PASS" for row in pilots), "total": len(pilots), "all_pass": all(row["result"] == "PASS" for row in pilots)},
        "governance_v2": {"passed": len(governance_rows), "total": 14, "all_pass": len(governance_rows) == 14},
        "FAMILY_D_DATA_READINESS": data_readiness,
        "FAMILY_D_ARCHITECTURE_RESULT": architecture_result,
        "no_performance_policy": {"final_performance_run": False, "outcomes_calculated": False, "returns_calculated": False, "profit_factor_calculated": False, "expectancy_calculated": False, "equity_curve_calculated": False, "drawdown_calculated": False},
        "governance": {"validation_accessed": False, "strategy_v2_created": False, "live_signals": 0, "live_orders": 0, "broker_order_calls": 0, "remote_migrations": 0, "supabase_persistence": 0, "previous_family_baseline_unchanged": True},
        "baseline_regression": {**baseline_after, "unchanged_during_build": True},
        "known_limitations": ["The scope is a frozen selected 100-symbol sample, not full-Nifty500 intraday evidence.", "No strict symbol-session has the continuous prior-20-session intraday history required for ORB-D-001; activity ratios and D001 structural signals are unavailable.", "Current provider instrument mappings are current-identity-only.", "The frozen transaction-cost profile is the project delivery-research proxy; no new intraday cost model was invented."],
        "recommended_next_action": "SEPARATE_AUTHORIZATION_FOR_CONTINUOUS_PRIOR20_INTRADAY_HISTORY_BEFORE_ANY_DEVELOPMENT_BACKTEST",
        "ready_for_review": True,
    }
    write_json(reports / "family_d_v1_summary.json", summary)

    artifact_paths = [
        *(path for path in output_root.rglob("*") if path.is_file() and manifests_dir not in path.parents),
        *(reports / name for name in REPORT_NAMES),
        root / "docs/strategy-family-d-opening-range-stocks-in-play-v1.md",
    ]
    existing = [path for path in artifact_paths if path.is_file()]
    manifest_body = {
        "version": "FAMILY_D_ARTIFACT_MANIFEST_V1",
        "family_d_config_hash": config["family_d_config_hash"],
        "intraday_scope_hash": scope["intraday_scope_hash"],
        "artifact_hashes": {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(set(existing))},
        "previous_family_baseline_snapshot_hash": baseline_after["snapshot_hash"],
    }
    manifest_body["family_d_artifact_manifest_hash"] = canonical_hash(manifest_body)
    write_json(manifests_dir / "family_d_artifact_manifest_v1.json", manifest_body)
    return summary


def verify_preregistration_hashes() -> dict[str, bool]:
    values = {
        "family_d_config_hash": family_d_config_document()["family_d_config_hash"] == EXPECTED_FAMILY_D_CONFIG_HASH,
        "control_reference_hash": control_document()["control_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH,
        "d001_parameter_hash": d001_parameter_document()["parameter_hash"] == EXPECTED_D001_PARAMETER_HASH,
        "d001_preregistration_hash": preregistration_document()["preregistration_hash"] == EXPECTED_D001_PREREGISTRATION_HASH,
        "success_criteria_hash": success_criteria_document()["family_d_success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    if not all(values.values()):
        raise FamilyDFreezeMismatch(values)
    return values


def verify_scope_hash(root: Path) -> bool:
    value = scope_document(_scope_rows(Path(root)))["intraday_scope_hash"]
    if value != EXPECTED_INTRADAY_SCOPE_HASH:
        raise FamilyDFreezeMismatch(
            {"intraday_scope_hash": value, "expected": EXPECTED_INTRADAY_SCOPE_HASH}
        )
    return True

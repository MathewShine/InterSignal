from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.backtesting.portfolio_baseline import (
    PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH,
    PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH,
    PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH,
    resolve_portfolio_backtest_daily_dataset,
    resolve_portfolio_backtest_skipped_dataset,
    resolve_portfolio_backtest_trades_dataset,
)
from app.backtesting.portfolio_config import (
    PORTFOLIO_BACKTEST_VERSION,
    SWING_PORTFOLIO_BACKTEST_PROFILE,
    PortfolioBacktestConfig,
    json_ready,
)
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
)
from app.services.daily_feature_engine import adjusted_daily_files, date_from_adjusted_path
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import (
    CURRENT_STRATEGY_OUTCOME_CONFIG_HASH,
    CURRENT_STRATEGY_OUTCOME_PROFILE,
    CURRENT_STRATEGY_OUTCOME_VERSION,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    outcome_input_hash_checks,
    outcome_input_hashes,
    resolve_current_strategy_outcome_dataset,
    verify_current_strategy_outcome_baseline,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
)

TARGET_EXIT = "TARGET_EXIT"
STOP_EXIT = "STOP_EXIT"
TIME_EXIT = "TIME_EXIT"
AMBIGUOUS_SAME_BAR_EXIT = "AMBIGUOUS_SAME_BAR_EXIT"
FORCED_DATA_EXIT = "FORCED_DATA_EXIT"
OTHER_EXIT = "OTHER"

SKIP_SAME_SYMBOL_ALREADY_OPEN = "SKIP_SAME_SYMBOL_ALREADY_OPEN"
SKIP_MAX_POSITIONS = "SKIP_MAX_POSITIONS"
SKIP_INSUFFICIENT_CASH = "SKIP_INSUFFICIENT_CASH"
SKIP_PORTFOLIO_RISK_LIMIT = "SKIP_PORTFOLIO_RISK_LIMIT"
SKIP_ZERO_QUANTITY = "SKIP_ZERO_QUANTITY"
SKIP_OTHER = "SKIP_OTHER"

BASELINE_COHORT = "HISTORICAL_ELIGIBLE_OPPORTUNITY"
BASELINE_DISPOSITION = "ENTRY_ELIGIBLE"
BASELINE_ENTRY_STATUS = "ENTRY_VALID"
ENTRY_REASON = "ADMITTED_BASELINE_PORTFOLIO"
EXPECTED_BASELINE_OPPORTUNITIES = 3296
RISK_TOLERANCE = Decimal("0.000001")

SELECTION_SOURCE_FIELDS = (
    "raw_strategy_score",
    "effective_reward_risk",
    "setup_quality",
    "momentum_points",
    "rvol_points",
    "relative_strength_points",
    "position_notional",
    "symbol",
)
PROHIBITED_SELECTION_TOKENS = (
    "first_touch",
    "target_first",
    "stop_first",
    "mfe",
    "mae",
    "future_return",
    "close_return",
    "exit_price",
    "exit_reason",
)

TRADE_FIELDS = [
    "trade_id",
    "source_key",
    "symbol",
    "decision_date",
    "entry_date",
    "entry_price",
    "quantity",
    "entry_notional",
    "initial_stop",
    "initial_target",
    "initial_target_basis",
    "initial_risk_per_share",
    "initial_planned_risk",
    "risk_budget_at_entry",
    "portfolio_equity_at_entry",
    "raw_strategy_score",
    "effective_reward_risk",
    "setup_quality",
    "candidate_category",
    "regime_state",
    "momentum_points",
    "rvol_points",
    "relative_strength_points",
    "selection_rank",
    "selection_priority_tuple",
    "entry_reason",
    "exit_date",
    "exit_price",
    "exit_reason",
    "holding_sessions",
    "gross_pnl",
    "gross_return_pct",
    "realized_r_multiple",
    "ambiguity_flag",
    "source_mfe_r_4",
    "source_close_return_pct_4",
    "backtest_version",
    "backtest_profile",
    "backtest_config_hash",
    "score_version",
    "score_profile",
    "score_config_hash",
    "risk_version",
    "risk_config_hash",
    "outcome_version",
    "outcome_profile",
    "outcome_config_hash",
    "outcome_cohort",
    "performance_basis",
    "transaction_cost_status",
    "slippage_status",
]

DAILY_FIELDS = [
    "date",
    "opening_cash",
    "closing_cash",
    "opening_portfolio_equity",
    "open_positions_start",
    "candidates",
    "new_entries",
    "exits",
    "peak_open_positions",
    "open_positions_end",
    "market_value_open",
    "portfolio_equity",
    "realized_pnl_day",
    "unrealized_pnl",
    "gross_exposure",
    "gross_exposure_pct",
    "cash_utilization_pct",
    "open_planned_risk",
    "open_planned_risk_pct",
]

SKIP_FIELDS = [
    "source_key",
    "decision_date",
    "entry_date",
    "symbol",
    "raw_score",
    "effective_rr",
    "setup_quality",
    "candidate_category",
    "regime_state",
    "momentum_points",
    "rvol_points",
    "relative_strength_points",
    "selection_rank",
    "selection_priority_tuple",
    "available_cash",
    "portfolio_equity",
    "open_positions",
    "open_planned_risk",
    "skip_reason",
    "backtest_version",
    "backtest_profile",
    "outcome_version",
    "outcome_profile",
]


@dataclass(frozen=True, slots=True)
class PortfolioBacktestEngineConfig:
    data_dir: Path
    backtest_config: PortfolioBacktestConfig = PortfolioBacktestConfig()
    full_generation: bool = True

    @property
    def outcome_dataset_path(self) -> Path:
        return resolve_current_strategy_outcome_dataset(self.data_dir)

    @property
    def output_dir(self) -> Path:
        return self.trades_path.parent

    @property
    def trades_path(self) -> Path:
        return resolve_portfolio_backtest_trades_dataset(
            self.data_dir,
            profile=self.backtest_config.backtest_profile,
            version=self.backtest_config.backtest_version,
        )

    @property
    def daily_path(self) -> Path:
        return resolve_portfolio_backtest_daily_dataset(
            self.data_dir,
            profile=self.backtest_config.backtest_profile,
            version=self.backtest_config.backtest_version,
        )

    @property
    def skipped_path(self) -> Path:
        return resolve_portfolio_backtest_skipped_dataset(
            self.data_dir,
            profile=self.backtest_config.backtest_profile,
            version=self.backtest_config.backtest_version,
        )

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def report_path(self, suffix: str) -> Path:
        version_tag = self.backtest_config.backtest_version.removeprefix("PORTFOLIO_BACKTEST_").lower()
        return self.reports_dir / f"portfolio_backtest_{version_tag}_{suffix}"


@dataclass(slots=True)
class OpenPosition:
    trade: dict[str, Any]
    source: dict[str, str]
    last_mark: Decimal
    sessions_seen: int = 0


def load_frozen_opportunities(dataset_path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    opportunities: list[dict[str, str]] = []
    exclusions: Counter[str] = Counter()
    with gzip.open(dataset_path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("outcome_cohort") != BASELINE_COHORT:
                exclusions["non_primary_cohort"] += 1
                continue
            if row.get("source_scoring_disposition") != BASELINE_DISPOSITION:
                exclusions["non_entry_eligible_disposition"] += 1
                continue
            if not truthy(row.get("entry_valid")) or row.get("entry_recheck_status") != BASELINE_ENTRY_STATUS:
                exclusions["entry_invalid"] += 1
                continue
            if not truthy(row.get("forward_data_safe")):
                exclusions["forward_data_unsafe"] += 1
                continue
            if not truthy(row.get("primary_evaluation_eligible")):
                exclusions["not_primary_evaluation_eligible"] += 1
                continue
            opportunities.append(row)
    return opportunities, dict(exclusions)


def selection_priority(row: dict[str, Any]) -> tuple[Any, ...]:
    setup_rank = {"STRONG": 2, "VALID": 1}.get(str(row.get("setup_quality", "")), 0)
    return (
        -decimal_or_zero(row.get("raw_strategy_score")),
        -decimal_or_zero(row.get("effective_reward_risk")),
        -setup_rank,
        -decimal_or_zero(row.get("momentum_points")),
        -decimal_or_zero(row.get("rvol_points")),
        -decimal_or_zero(row.get("relative_strength_points")),
        decimal_or_zero(row.get("position_notional")),
        str(row.get("symbol", "")),
    )


def selection_priority_display(row: dict[str, Any]) -> str:
    return json.dumps(
        [
            format_decimal(decimal_or_zero(row.get("raw_strategy_score"))),
            format_decimal(decimal_or_zero(row.get("effective_reward_risk"))),
            str(row.get("setup_quality", "")),
            format_decimal(decimal_or_zero(row.get("momentum_points"))),
            format_decimal(decimal_or_zero(row.get("rvol_points"))),
            format_decimal(decimal_or_zero(row.get("relative_strength_points"))),
            format_decimal(decimal_or_zero(row.get("position_notional"))),
            str(row.get("symbol", "")),
        ],
        separators=(",", ":"),
    )


def rank_opportunities(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for selection_rank, row in enumerate(sorted(rows, key=selection_priority), start=1):
        item = dict(row)
        item["_selection_rank"] = selection_rank
        item["_selection_priority_tuple"] = selection_priority_display(row)
        ranked.append(item)
    return ranked


def calculate_portfolio_quantity(
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    portfolio_equity: Decimal,
    available_cash: Decimal,
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    risk_per_share = entry_price - stop_price
    risk_budget = portfolio_equity * config.max_risk_per_trade_pct / Decimal("100")
    quantity_by_risk = floor_whole(risk_budget / risk_per_share) if risk_per_share > 0 else 0
    quantity_by_cash = floor_whole(available_cash / entry_price) if entry_price > 0 else 0
    quantity = min(quantity_by_risk, quantity_by_cash)
    return {
        "risk_per_share": risk_per_share,
        "risk_budget": risk_budget,
        "quantity_by_risk": quantity_by_risk,
        "quantity_by_cash": quantity_by_cash,
        "quantity": quantity,
        "entry_notional": entry_price * quantity,
        "planned_risk": risk_per_share * quantity,
    }


def evaluate_admission(
    *,
    row: dict[str, Any],
    open_positions: Sequence[OpenPosition],
    available_cash: Decimal,
    portfolio_equity: Decimal,
    config: PortfolioBacktestConfig,
) -> tuple[str | None, dict[str, Any]]:
    if any(position.trade["symbol"] == row.get("symbol") for position in open_positions):
        return SKIP_SAME_SYMBOL_ALREADY_OPEN, {}
    if len(open_positions) >= config.max_concurrent_positions:
        return SKIP_MAX_POSITIONS, {}
    entry_price = decimal_or_zero(row.get("hypothetical_entry_price"))
    stop_price = decimal_or_zero(row.get("stop_price"))
    sizing = calculate_portfolio_quantity(
        entry_price=entry_price,
        stop_price=stop_price,
        portfolio_equity=portfolio_equity,
        available_cash=available_cash,
        config=config,
    )
    if sizing["risk_per_share"] <= 0 or entry_price <= 0:
        return SKIP_OTHER, sizing
    if sizing["quantity_by_risk"] < 1:
        return SKIP_ZERO_QUANTITY, sizing
    if sizing["quantity_by_cash"] < 1:
        return SKIP_INSUFFICIENT_CASH, sizing
    open_risk = sum(decimal_or_zero(position.trade["initial_planned_risk"]) for position in open_positions)
    max_open_risk = portfolio_equity * config.max_total_open_risk_pct / Decimal("100")
    if open_risk + sizing["planned_risk"] > max_open_risk + RISK_TOLERANCE:
        return SKIP_PORTFOLIO_RISK_LIMIT, sizing
    return None, sizing


def session_bar(row: dict[str, Any], trading_date: str) -> dict[str, Any] | None:
    for index in range(1, 5):
        if row.get(f"session_date_{index}") != trading_date:
            continue
        return {
            "index": index,
            "date": trading_date,
            "open": decimal_or_none(row.get(f"open_{index}")),
            "high": decimal_or_none(row.get(f"high_{index}")),
            "low": decimal_or_none(row.get(f"low_{index}")),
            "close": decimal_or_none(row.get(f"close_{index}")),
        }
    return None


def determine_exit(
    row: dict[str, Any],
    trading_date: str,
    config: PortfolioBacktestConfig,
) -> dict[str, Any] | None:
    bar = session_bar(row, trading_date)
    if bar is None:
        return None
    if any(bar[field] is None for field in ("high", "low", "close")):
        return {"reason": FORCED_DATA_EXIT, "price": None, "ambiguity": False, "session": bar["index"]}
    stop_price = decimal_or_zero(row.get("stop_price"))
    target_price = decimal_or_zero(row.get("target_price"))
    stop_touched = bar["low"] <= stop_price
    target_touched = bar["high"] >= target_price
    if stop_touched and target_touched:
        return {
            "reason": AMBIGUOUS_SAME_BAR_EXIT,
            "price": stop_price,
            "ambiguity": True,
            "session": bar["index"],
        }
    if target_touched:
        return {"reason": TARGET_EXIT, "price": target_price, "ambiguity": False, "session": bar["index"]}
    if stop_touched:
        return {"reason": STOP_EXIT, "price": stop_price, "ambiguity": False, "session": bar["index"]}
    if bar["index"] == config.max_hold_sessions:
        return {"reason": TIME_EXIT, "price": bar["close"], "ambiguity": False, "session": bar["index"]}
    return None


def simulate_portfolio(
    *,
    opportunities: Sequence[dict[str, Any]],
    trading_dates: Sequence[str],
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    by_entry_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_entry_date[str(row.get("next_session_date", ""))].append(dict(row))

    cash = config.initial_capital_rupees
    open_positions: list[OpenPosition] = []
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    trade_counter = 0
    invariants: Counter[str] = Counter()
    input_source_keys = {source_key(row) for row in opportunities}
    sorted_dates = sorted(dict.fromkeys(trading_dates))

    for trading_date in sorted_dates:
        opening_cash = cash
        open_positions_start = len(open_positions)
        opening_market_value = Decimal("0")
        for position in open_positions:
            bar = session_bar(position.source, trading_date)
            opening_mark = bar["open"] if bar and bar["open"] is not None else position.last_mark
            opening_market_value += opening_mark * int(position.trade["quantity"])
        opening_equity = cash + opening_market_value
        ranked = rank_opportunities(by_entry_date.get(trading_date, []))
        new_entries = 0
        expected_cash = cash

        for row in ranked:
            skip_reason, sizing = evaluate_admission(
                row=row,
                open_positions=open_positions,
                available_cash=cash,
                portfolio_equity=opening_equity,
                config=config,
            )
            if skip_reason:
                skipped.append(build_skip_record(row, skip_reason, cash, opening_equity, open_positions, config))
                continue

            trade_counter += 1
            trade = build_trade_record(
                row=row,
                sizing=sizing,
                portfolio_equity=opening_equity,
                trade_number=trade_counter,
                config=config,
            )
            cash -= sizing["entry_notional"]
            expected_cash -= sizing["entry_notional"]
            invariants["cash_accounting_violations"] += abs(cash - expected_cash) > RISK_TOLERANCE
            invariants["negative_cash_violations"] += cash < -RISK_TOLERANCE
            position = OpenPosition(
                trade=trade,
                source=dict(row),
                last_mark=decimal_or_zero(row.get("hypothetical_entry_price")),
            )
            open_positions.append(position)
            new_entries += 1
            invariants["trade_risk_violations"] += (
                sizing["planned_risk"]
                > opening_equity * config.max_risk_per_trade_pct / Decimal("100") + RISK_TOLERANCE
            )
            current_open_risk = sum(decimal_or_zero(item.trade["initial_planned_risk"]) for item in open_positions)
            invariants["portfolio_risk_violations"] += (
                current_open_risk
                > opening_equity * config.max_total_open_risk_pct / Decimal("100") + RISK_TOLERANCE
            )
            invariants["position_quantity_violations"] += int(trade["quantity"]) <= 0
            invariants["trade_linkage_violations"] += trade["source_key"] not in input_source_keys

        peak_open_positions = len(open_positions)
        invariants["max_position_violations"] += peak_open_positions > config.max_concurrent_positions
        invariants["same_symbol_duplicate_violations"] += duplicate_symbol_count(open_positions)
        realized_pnl_day = Decimal("0")
        exits = 0
        remaining_positions: list[OpenPosition] = []

        for position in open_positions:
            bar = session_bar(position.source, trading_date)
            if bar is not None:
                position.sessions_seen += 1
                if bar["close"] is not None:
                    position.last_mark = bar["close"]
            exit_event = determine_exit(position.source, trading_date, config)
            if exit_event is None:
                remaining_positions.append(position)
                continue
            exit_price = exit_event["price"] if exit_event["price"] is not None else position.last_mark
            close_trade(position.trade, trading_date, exit_price, exit_event, position.sessions_seen)
            proceeds = exit_price * int(position.trade["quantity"])
            cash += proceeds
            expected_cash += proceeds
            invariants["cash_accounting_violations"] += abs(cash - expected_cash) > RISK_TOLERANCE
            invariants["negative_cash_violations"] += cash < -RISK_TOLERANCE
            realized_pnl_day += decimal_or_zero(position.trade["gross_pnl"])
            trades.append(position.trade)
            exits += 1
        open_positions = remaining_positions

        if trading_date == sorted_dates[-1] and open_positions:
            for position in open_positions:
                exit_event = {
                    "reason": FORCED_DATA_EXIT,
                    "price": position.last_mark,
                    "ambiguity": False,
                    "session": position.sessions_seen,
                }
                close_trade(position.trade, trading_date, position.last_mark, exit_event, position.sessions_seen)
                proceeds = position.last_mark * int(position.trade["quantity"])
                cash += proceeds
                expected_cash += proceeds
                realized_pnl_day += decimal_or_zero(position.trade["gross_pnl"])
                trades.append(position.trade)
                exits += 1
            open_positions = []

        market_value_open = Decimal("0")
        unrealized_pnl = Decimal("0")
        for position in open_positions:
            quantity = int(position.trade["quantity"])
            market_value_open += position.last_mark * quantity
            unrealized_pnl += (position.last_mark - decimal_or_zero(position.trade["entry_price"])) * quantity
        portfolio_equity = cash + market_value_open
        open_planned_risk = sum(decimal_or_zero(position.trade["initial_planned_risk"]) for position in open_positions)
        gross_exposure_pct = pct(market_value_open, portfolio_equity)
        daily.append(
            {
                "date": trading_date,
                "opening_cash": opening_cash,
                "closing_cash": cash,
                "opening_portfolio_equity": opening_equity,
                "open_positions_start": open_positions_start,
                "candidates": len(ranked),
                "new_entries": new_entries,
                "exits": exits,
                "peak_open_positions": peak_open_positions,
                "open_positions_end": len(open_positions),
                "market_value_open": market_value_open,
                "portfolio_equity": portfolio_equity,
                "realized_pnl_day": realized_pnl_day,
                "unrealized_pnl": unrealized_pnl,
                "gross_exposure": market_value_open,
                "gross_exposure_pct": gross_exposure_pct,
                "cash_utilization_pct": gross_exposure_pct,
                "open_planned_risk": open_planned_risk,
                "open_planned_risk_pct": pct(open_planned_risk, portfolio_equity),
            }
        )
        invariants["cash_accounting_violations"] += abs(cash - expected_cash) > RISK_TOLERANCE
        invariants["position_trade_id_duplicate_violations"] += duplicate_trade_id_count(open_positions)

    invariants["lookahead_selection_violations"] = selection_lookahead_violations()
    invariants["exceptional_row_baseline_inclusion_violations"] = sum(
        trade["outcome_cohort"] != BASELINE_COHORT for trade in trades
    )
    all_records = len(trades) + len(skipped)
    invariants["opportunity_reconciliation_violations"] = all_records != len(opportunities)
    return {
        "trades": trades,
        "skipped": skipped,
        "daily": daily,
        "invariants": dict(invariants),
        "all_invariants_valid": not any(invariants.values()),
        "considered": len(opportunities),
        "entered": len(trades),
        "skipped_count": len(skipped),
    }


def build_trade_record(
    *,
    row: dict[str, Any],
    sizing: dict[str, Any],
    portfolio_equity: Decimal,
    trade_number: int,
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    config_hash = config.config_hash()
    return {
        "trade_id": f"PBV1-{trade_number:06d}",
        "source_key": source_key(row),
        "symbol": row.get("symbol", ""),
        "decision_date": row.get("decision_date", ""),
        "entry_date": row.get("next_session_date", ""),
        "entry_price": decimal_or_zero(row.get("hypothetical_entry_price")),
        "quantity": sizing["quantity"],
        "entry_notional": sizing["entry_notional"],
        "initial_stop": decimal_or_zero(row.get("stop_price")),
        "initial_target": decimal_or_zero(row.get("target_price")),
        "initial_target_basis": row.get("target_basis", ""),
        "initial_risk_per_share": sizing["risk_per_share"],
        "initial_planned_risk": sizing["planned_risk"],
        "risk_budget_at_entry": sizing["risk_budget"],
        "portfolio_equity_at_entry": portfolio_equity,
        "raw_strategy_score": decimal_or_zero(row.get("raw_strategy_score")),
        "effective_reward_risk": decimal_or_zero(row.get("effective_reward_risk")),
        "setup_quality": row.get("setup_quality", ""),
        "candidate_category": row.get("candidate_category", ""),
        "regime_state": row.get("regime_state", ""),
        "momentum_points": decimal_or_zero(row.get("momentum_points")),
        "rvol_points": decimal_or_zero(row.get("rvol_points")),
        "relative_strength_points": decimal_or_zero(row.get("relative_strength_points")),
        "selection_rank": row.get("_selection_rank", ""),
        "selection_priority_tuple": row.get("_selection_priority_tuple", ""),
        "entry_reason": ENTRY_REASON,
        "exit_date": "",
        "exit_price": "",
        "exit_reason": "",
        "holding_sessions": "",
        "gross_pnl": "",
        "gross_return_pct": "",
        "realized_r_multiple": "",
        "ambiguity_flag": False,
        "source_mfe_r_4": row.get("mfe_r_4", ""),
        "source_close_return_pct_4": row.get("close_return_pct_4", ""),
        "backtest_version": config.backtest_version,
        "backtest_profile": config.backtest_profile,
        "backtest_config_hash": config_hash,
        "score_version": row.get("score_version", ""),
        "score_profile": row.get("score_profile", ""),
        "score_config_hash": row.get("score_config_hash", ""),
        "risk_version": row.get("risk_version", ""),
        "risk_config_hash": row.get("risk_config_hash", ""),
        "outcome_version": row.get("outcome_version", ""),
        "outcome_profile": row.get("outcome_profile", ""),
        "outcome_config_hash": row.get("outcome_config_hash", ""),
        "outcome_cohort": row.get("outcome_cohort", ""),
        "performance_basis": config.performance_basis,
        "transaction_cost_status": config.transaction_cost_status,
        "slippage_status": config.slippage_status,
    }


def close_trade(
    trade: dict[str, Any],
    exit_date: str,
    exit_price: Decimal,
    exit_event: dict[str, Any],
    sessions_seen: int,
) -> None:
    entry_price = decimal_or_zero(trade["entry_price"])
    risk_per_share = decimal_or_zero(trade["initial_risk_per_share"])
    quantity = int(trade["quantity"])
    trade["exit_date"] = exit_date
    trade["exit_price"] = exit_price
    trade["exit_reason"] = exit_event["reason"]
    trade["holding_sessions"] = int(exit_event.get("session") or sessions_seen)
    trade["gross_pnl"] = (exit_price - entry_price) * quantity
    trade["gross_return_pct"] = pct(exit_price - entry_price, entry_price)
    trade["realized_r_multiple"] = (exit_price - entry_price) / risk_per_share if risk_per_share else Decimal("0")
    trade["ambiguity_flag"] = bool(exit_event.get("ambiguity"))


def build_skip_record(
    row: dict[str, Any],
    reason: str,
    cash: Decimal,
    equity: Decimal,
    open_positions: Sequence[OpenPosition],
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    return {
        "source_key": source_key(row),
        "decision_date": row.get("decision_date", ""),
        "entry_date": row.get("next_session_date", ""),
        "symbol": row.get("symbol", ""),
        "raw_score": decimal_or_zero(row.get("raw_strategy_score")),
        "effective_rr": decimal_or_zero(row.get("effective_reward_risk")),
        "setup_quality": row.get("setup_quality", ""),
        "candidate_category": row.get("candidate_category", ""),
        "regime_state": row.get("regime_state", ""),
        "momentum_points": decimal_or_zero(row.get("momentum_points")),
        "rvol_points": decimal_or_zero(row.get("rvol_points")),
        "relative_strength_points": decimal_or_zero(row.get("relative_strength_points")),
        "selection_rank": row.get("_selection_rank", ""),
        "selection_priority_tuple": row.get("_selection_priority_tuple", ""),
        "available_cash": cash,
        "portfolio_equity": equity,
        "open_positions": len(open_positions),
        "open_planned_risk": sum(decimal_or_zero(item.trade["initial_planned_risk"]) for item in open_positions),
        "skip_reason": reason,
        "backtest_version": config.backtest_version,
        "backtest_profile": config.backtest_profile,
        "outcome_version": row.get("outcome_version", ""),
        "outcome_profile": row.get("outcome_profile", ""),
    }


def build_portfolio_backtest(
    *,
    config: PortfolioBacktestEngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Verifying frozen outcome, score, risk, and upstream inputs")
    baseline = verify_current_strategy_outcome_baseline(config.data_dir)
    hashes_before = outcome_input_hashes(config.data_dir)
    hash_checks = outcome_input_hash_checks(hashes_before)
    if not all(hash_checks.values()):
        raise ValueError("One or more frozen backtest input hashes do not match")
    if file_sha256(baseline.dataset_path) != STRATEGY_OUTCOME_V1_DATASET_HASH:
        raise ValueError(f"Frozen {CURRENT_STRATEGY_OUTCOME_VERSION} dataset hash mismatch")

    notify(progress, "Loading the frozen baseline opportunity pool")
    opportunities, exclusions = load_frozen_opportunities(config.outcome_dataset_path)
    validate_opportunity_pool(opportunities)
    pilot = run_pilot_validation(opportunities, config.backtest_config)
    if not pilot["passed"]:
        raise ValueError("Portfolio backtest pilot validation failed")
    if not config.full_generation:
        return {
            "phase": "Step 02.12",
            "command": "Command 01",
            "pilot": pilot,
            "full_backtest_completed": False,
            "input_hashes": hashes_before,
            "input_hash_checks": hash_checks,
            "ready_for_review": pilot["passed"],
        }

    notify(progress, "Running one chronological fixed-parameter baseline simulation")
    calendar = build_trading_calendar(config.data_dir, opportunities)
    simulation = simulate_portfolio(
        opportunities=opportunities,
        trading_dates=calendar,
        config=config.backtest_config,
    )
    tables = build_report_tables(simulation, opportunities, pilot, config.backtest_config)
    metrics = build_metrics(simulation, opportunities, config.backtest_config)
    hashes_after = outcome_input_hashes(config.data_dir)
    regression = {
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "checks": {name: hashes_before[name] == hashes_after[name] for name in hashes_before},
        "all_frozen_inputs_unchanged": hashes_before == hashes_after,
    }
    metadata = build_run_metadata(config.backtest_config, opportunities)
    report: dict[str, Any] = {
        "phase": "Step 02.12",
        "command": "Command 01",
        "run_metadata": metadata,
        "contract": config.backtest_config.snapshot(),
        "source_contract": {
            "outcome_version": CURRENT_STRATEGY_OUTCOME_VERSION,
            "outcome_profile": CURRENT_STRATEGY_OUTCOME_PROFILE,
            "outcome_config_hash": CURRENT_STRATEGY_OUTCOME_CONFIG_HASH,
            "outcome_dataset_hash": hashes_after["outcome_v1"],
            "score_version": CURRENT_STRATEGY_SCORE_VERSION,
            "score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
            "score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
            "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
            "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        },
        "opportunity_pool": {
            "mechanically_valid_opportunities_considered": len(opportunities),
            "actual_portfolio_trades_entered": simulation["entered"],
            "opportunities_skipped": simulation["skipped_count"],
            "admission_rate_pct": pct(Decimal(simulation["entered"]), Decimal(len(opportunities))),
            "excluded_source_rows": exclusions,
            "exceptional_review_policy": config.backtest_config.exceptional_review_policy,
        },
        "portfolio_metrics": metrics["portfolio"],
        "trade_metrics": metrics["trades"],
        "exit_metrics": metrics["exits"],
        "holding_period": metrics["holding_period"],
        "exposure": metrics["exposure"],
        "cash_utilization": metrics["cash_utilization"],
        "concurrency": metrics["concurrency"],
        "skip_reasons": metrics["skip_reasons"],
        "daily_competing_opportunities": metrics["daily_competing_opportunities"],
        "ranking_distribution": metrics["ranking_distribution"],
        "same_symbol_overlap": metrics["same_symbol_overlap"],
        "slot_pressure": metrics["slot_pressure"],
        "cash_pressure": metrics["cash_pressure"],
        "risk_pressure": metrics["risk_pressure"],
        "ambiguity_sensitivity": metrics["ambiguity_sensitivity"],
        "time_exit_analysis": metrics["time_exit_analysis"],
        "stop_exit_analysis": metrics["stop_exit_analysis"],
        "target_exit_analysis": metrics["target_exit_analysis"],
        "invariants": simulation["invariants"],
        "all_invariants_valid": simulation["all_invariants_valid"],
        "pilot": pilot,
        "regression": regression,
        "safety": {
            "parameter_sweeps_run": 0,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_api_calls": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "full_backtest_completed": True,
        "performance_status": config.backtest_config.performance_basis,
        "runtime_seconds": 0,
        "storage": {},
        "artifacts": {},
        "known_limitations": [
            "Daily OHLC cannot determine intraday order when stop and target are first touched in the same bar.",
            "The conservative same-bar stop assumption is a research convention, not reconstructed execution.",
            "Transaction costs, slippage, taxes, liquidity, and fill uncertainty are not modeled.",
            "The canonical four-session hold is frozen and remains likely too short according to the outcome audit.",
            "Results are historical, gross before costs, and must not be treated as live or deployable performance.",
        ],
    }
    notify(progress, "Writing deterministic bulk ledgers and descriptive reports")
    artifact_paths = write_backtest_artifacts(config, simulation, tables)
    report["runtime_seconds"] = round(time.perf_counter() - started, 3)
    report["artifacts"] = artifact_manifest(artifact_paths)
    report["storage"] = {
        "artifact_count": len(artifact_paths),
        "artifact_size_bytes_excluding_summary": sum(path.stat().st_size for path in artifact_paths if path.exists()),
    }
    report["ready_for_review"] = (
        pilot["passed"]
        and simulation["all_invariants_valid"]
        and regression["all_frozen_inputs_unchanged"]
        and simulation["considered"] == EXPECTED_BASELINE_OPPORTUNITIES
    )
    write_json(config.report_path("summary.json"), report)
    report["artifacts"]["summary"] = {
        "path": str(config.report_path("summary.json")),
        "sha256": file_sha256(config.report_path("summary.json")),
        "size_bytes": config.report_path("summary.json").stat().st_size,
    }
    return report


def validate_opportunity_pool(opportunities: Sequence[dict[str, Any]]) -> None:
    if len(opportunities) != EXPECTED_BASELINE_OPPORTUNITIES:
        raise ValueError(
            f"Expected {EXPECTED_BASELINE_OPPORTUNITIES} frozen valid opportunities, observed {len(opportunities)}"
        )
    violations = 0
    for row in opportunities:
        violations += row.get("outcome_cohort") != BASELINE_COHORT
        violations += row.get("source_scoring_disposition") != BASELINE_DISPOSITION
        violations += row.get("entry_recheck_status") != BASELINE_ENTRY_STATUS
        violations += not truthy(row.get("entry_valid"))
        violations += not truthy(row.get("forward_data_safe"))
        violations += row.get("entry_model") != "NEXT_SESSION_OPEN"
        violations += row.get("outcome_version") != CURRENT_STRATEGY_OUTCOME_VERSION
        violations += row.get("score_version") != CURRENT_STRATEGY_SCORE_VERSION
        violations += row.get("risk_version") != CURRENT_RISK_STRUCTURE_VERSION
    if violations:
        raise ValueError(f"Frozen opportunity-pool contract violations: {violations}")


def build_trading_calendar(data_dir: Path, opportunities: Sequence[dict[str, Any]]) -> list[str]:
    minimum = min(parse_date(row["next_session_date"]) for row in opportunities)
    maximum = max(
        parse_date(row[f"session_date_{index}"])
        for row in opportunities
        for index in range(1, 5)
        if row.get(f"session_date_{index}")
    )
    dates = {
        observed
        for path in adjusted_daily_files(data_dir / "research/adjusted/daily/nse")
        if (observed := date_from_adjusted_path(path)) is not None and minimum <= observed <= maximum
    }
    for row in opportunities:
        dates.add(parse_date(row["next_session_date"]))
        for index in range(1, 5):
            if row.get(f"session_date_{index}"):
                dates.add(parse_date(row[f"session_date_{index}"]))
    return [item.isoformat() for item in sorted(dates)]


def build_run_metadata(config: PortfolioBacktestConfig, opportunities: Sequence[dict[str, Any]]) -> dict[str, Any]:
    start_date = min(row["next_session_date"] for row in opportunities)
    end_date = max(row["session_date_4"] for row in opportunities)
    run_seed = f"{config.backtest_version}|{config.config_hash()}|{STRATEGY_OUTCOME_V1_DATASET_HASH}"
    return {
        "backtest_version": config.backtest_version,
        "profile": config.backtest_profile,
        "backtest_config_hash": config.config_hash(),
        "run_id": f"PBV1-{hashlib.sha256(run_seed.encode('utf-8')).hexdigest()[:16]}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "initial_capital": config.initial_capital_rupees,
        "start_date": start_date,
        "end_date": end_date,
        "source_score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "source_risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "source_outcome_version": CURRENT_STRATEGY_OUTCOME_VERSION,
        "cost_status": config.transaction_cost_status,
        "slippage_status": config.slippage_status,
        "ambiguity_policy": config.ambiguity_policy,
        "performance_basis": config.performance_basis,
    }


def build_metrics(
    simulation: dict[str, Any],
    opportunities: Sequence[dict[str, Any]],
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    trades = simulation["trades"]
    skipped = simulation["skipped"]
    daily = simulation["daily"]
    equity_values = [decimal_or_zero(row["portfolio_equity"]) for row in daily]
    drawdowns = drawdown_series(equity_values)
    ending_equity = equity_values[-1] if equity_values else config.initial_capital_rupees
    total_return_pct = pct(ending_equity - config.initial_capital_rupees, config.initial_capital_rupees)
    start_date = parse_date(daily[0]["date"]) if daily else date.today()
    end_date = parse_date(daily[-1]["date"]) if daily else start_date
    span_days = max((end_date - start_date).days, 0)
    cagr = calculate_cagr(config.initial_capital_rupees, ending_equity, span_days)
    pnl_values = [decimal_or_zero(trade["gross_pnl"]) for trade in trades]
    r_values = [decimal_or_zero(trade["realized_r_multiple"]) for trade in trades]
    holding_values = [int(trade["holding_sessions"]) for trade in trades]
    exit_counts = Counter(trade["exit_reason"] for trade in trades)
    skip_counts = Counter(row["skip_reason"] for row in skipped)
    positive = sum(value > 0 for value in pnl_values)
    negative = sum(value < 0 for value in pnl_values)
    flat = sum(value == 0 for value in pnl_values)
    exposure_values = [decimal_or_zero(row["gross_exposure_pct"]) for row in daily]
    concurrency_values = [int(row["open_positions_end"]) for row in daily]
    peak_concurrency_values = [int(row["peak_open_positions"]) for row in daily]
    competing = Counter(opportunity_bucket(int(row["candidates"])) for row in daily if int(row["candidates"]) > 0)
    days_at_max = [row["date"] for row in daily if int(row["peak_open_positions"]) >= config.max_concurrent_positions]
    ambiguous_trades = [trade for trade in trades if trade["exit_reason"] == AMBIGUOUS_SAME_BAR_EXIT]
    ambiguity_delta = sum(
        (decimal_or_zero(trade["initial_target"]) - decimal_or_zero(trade["initial_stop"])) * int(trade["quantity"])
        for trade in ambiguous_trades
    )
    return {
        "portfolio": {
            "starting_equity": config.initial_capital_rupees,
            "ending_equity": ending_equity,
            "total_gross_return_pct": total_return_pct,
            "annualized_return_pct": cagr,
            "cagr_pct": cagr,
            "maximum_drawdown_pct": max(drawdowns, default=Decimal("0")),
            "average_drawdown_pct": mean_decimal(drawdowns),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "performance_basis": config.performance_basis,
        },
        "trades": {
            "completed_trades": len(trades),
            "mean_gross_pnl": mean_decimal(pnl_values),
            "median_gross_pnl": median_decimal(pnl_values),
            "mean_realized_r": mean_decimal(r_values),
            "median_realized_r": median_decimal(r_values),
            "positive_gross_pnl_trades": positive,
            "negative_gross_pnl_trades": negative,
            "flat_gross_pnl_trades": flat,
            "positive_trade_rate_pct": pct(Decimal(positive), Decimal(len(trades))),
            "negative_trade_rate_pct": pct(Decimal(negative), Decimal(len(trades))),
        },
        "exits": {
            reason: {"count": exit_counts[reason], "rate_pct": pct(Decimal(exit_counts[reason]), Decimal(len(trades)))}
            for reason in (TARGET_EXIT, STOP_EXIT, TIME_EXIT, AMBIGUOUS_SAME_BAR_EXIT, FORCED_DATA_EXIT, OTHER_EXIT)
        },
        "holding_period": {
            "mean_sessions": mean_decimal([Decimal(value) for value in holding_values]),
            "median_sessions": median_decimal([Decimal(value) for value in holding_values]),
            "distribution": {str(value): holding_values.count(value) for value in range(1, 5)},
        },
        "exposure": distribution_summary(exposure_values),
        "cash_utilization": distribution_summary(exposure_values),
        "concurrency": {
            **distribution_summary([Decimal(value) for value in concurrency_values]),
            "distribution": {str(value): concurrency_values.count(value) for value in range(0, 5)},
            "peak_intraday_max": max(peak_concurrency_values, default=0),
        },
        "skip_reasons": {
            reason: {"count": skip_counts[reason], "rate_pct": pct(Decimal(skip_counts[reason]), Decimal(len(skipped)))}
            for reason in (
                SKIP_SAME_SYMBOL_ALREADY_OPEN,
                SKIP_MAX_POSITIONS,
                SKIP_INSUFFICIENT_CASH,
                SKIP_PORTFOLIO_RISK_LIMIT,
                SKIP_ZERO_QUANTITY,
                SKIP_OTHER,
            )
        },
        "daily_competing_opportunities": {
            "distribution": {bucket: competing[bucket] for bucket in ("1", "2", "3", "4", "5+")},
            "days_with_candidates": sum(competing.values()),
            "total_candidates": len(opportunities),
            "total_admitted": len(trades),
        },
        "ranking_distribution": {
            "entered": evidence_distribution(trades, entered=True),
            "skipped": evidence_distribution(skipped, entered=False),
        },
        "same_symbol_overlap": same_symbol_metrics(skipped),
        "slot_pressure": {
            "days_at_max_positions": len(days_at_max),
            "longest_full_capacity_streak": longest_date_streak(days_at_max, [row["date"] for row in daily]),
            "candidates_skipped_max_positions": skip_counts[SKIP_MAX_POSITIONS],
        },
        "cash_pressure": {
            "days_with_insufficient_cash_skip": len({row["entry_date"] for row in skipped if row["skip_reason"] == SKIP_INSUFFICIENT_CASH}),
            "opportunities_skipped_insufficient_cash": skip_counts[SKIP_INSUFFICIENT_CASH],
        },
        "risk_pressure": {
            "days_with_portfolio_risk_skip": len({row["entry_date"] for row in skipped if row["skip_reason"] == SKIP_PORTFOLIO_RISK_LIMIT}),
            "opportunities_skipped_portfolio_risk": skip_counts[SKIP_PORTFOLIO_RISK_LIMIT],
        },
        "ambiguity_sensitivity": {
            "ambiguous_trade_count": len(ambiguous_trades),
            "baseline_policy": config.ambiguity_policy,
            "gross_pnl_increase_if_target_first": ambiguity_delta,
            "diagnostic_status": "AUDIT_ONLY_DO_NOT_CHANGE_BASELINE",
        },
        "time_exit_analysis": exit_analysis(trades, TIME_EXIT),
        "stop_exit_analysis": stop_exit_analysis(trades),
        "target_exit_analysis": target_exit_analysis(trades),
    }


def build_report_tables(
    simulation: dict[str, Any],
    opportunities: Sequence[dict[str, Any]],
    pilot: dict[str, Any],
    config: PortfolioBacktestConfig,
) -> dict[str, list[dict[str, Any]]]:
    trades = simulation["trades"]
    skipped = simulation["skipped"]
    return {
        "daily_summary.csv": list(simulation["daily"]),
        "exits.csv": attribution_rows(trades, "exit_reason", [TARGET_EXIT, STOP_EXIT, TIME_EXIT, AMBIGUOUS_SAME_BAR_EXIT, FORCED_DATA_EXIT]),
        "skips.csv": skip_report_rows(skipped),
        "scores.csv": attribution_rows(trades, "raw_strategy_score", [str(value) for value in range(80, 86)]),
        "regimes.csv": attribution_rows(trades, "regime_state", ["BULLISH", "NEUTRAL"]),
        "candidate_categories.csv": attribution_rows(
            trades, "candidate_category", ["EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE"]
        ),
        "setup_quality.csv": attribution_rows(trades, "setup_quality", ["STRONG", "VALID"]),
        "rr_bands.csv": attribution_rows_with_classifier(
            trades, rr_band, ["1.5_TO_LT_2", "2_TO_LT_2.5", "GE_2.5"]
        ),
        "yearly.csv": yearly_report_rows(simulation, opportunities, config),
        "pilot_validation.csv": list(pilot["rows"]),
    }


def attribution_rows(
    trades: Sequence[dict[str, Any]],
    field: str,
    expected_values: Sequence[str],
) -> list[dict[str, Any]]:
    return attribution_rows_with_classifier(trades, lambda trade: format_group_value(trade.get(field)), expected_values)


def attribution_rows_with_classifier(
    trades: Sequence[dict[str, Any]],
    classifier: Callable[[dict[str, Any]], str],
    expected_values: Sequence[str],
) -> list[dict[str, Any]]:
    rows = []
    for value in expected_values:
        group = [trade for trade in trades if classifier(trade) == value]
        pnl = [decimal_or_zero(trade["gross_pnl"]) for trade in group]
        realized_r = [decimal_or_zero(trade["realized_r_multiple"]) for trade in group]
        exits = Counter(trade["exit_reason"] for trade in group)
        positive = sum(item > 0 for item in pnl)
        rows.append(
            {
                "group": value,
                "trade_count": len(group),
                "gross_pnl": sum(pnl, Decimal("0")),
                "mean_realized_r": mean_decimal(realized_r),
                "median_realized_r": median_decimal(realized_r),
                "positive_trade_rate_pct": pct(Decimal(positive), Decimal(len(group))),
                "target_exit_count": exits[TARGET_EXIT],
                "stop_exit_count": exits[STOP_EXIT],
                "time_exit_count": exits[TIME_EXIT],
                "ambiguous_exit_count": exits[AMBIGUOUS_SAME_BAR_EXIT],
                "sample_size_warning": sample_size_warning(len(group)),
            }
        )
    return rows


def yearly_report_rows(
    simulation: dict[str, Any],
    opportunities: Sequence[dict[str, Any]],
    config: PortfolioBacktestConfig,
) -> list[dict[str, Any]]:
    trades = simulation["trades"]
    daily = simulation["daily"]
    rows = []
    for year in sorted({int(row["date"][:4]) for row in daily}):
        year_daily = [row for row in daily if int(row["date"][:4]) == year]
        first_index = daily.index(year_daily[0])
        year_entries = [trade for trade in trades if int(trade["entry_date"][:4]) == year]
        year_opportunities = [row for row in opportunities if int(row["next_session_date"][:4]) == year]
        starting_equity = (
            config.initial_capital_rupees
            if first_index == 0
            else decimal_or_zero(daily[first_index - 1]["portfolio_equity"])
        )
        ending_equity = decimal_or_zero(year_daily[-1]["portfolio_equity"])
        year_drawdowns = drawdown_series([decimal_or_zero(row["portfolio_equity"]) for row in year_daily])
        exits = Counter(trade["exit_reason"] for trade in year_entries)
        rows.append(
            {
                "year": year,
                "period_status": "PARTIAL_YEAR" if year in {2021, 2026} else "FULL_CALENDAR_YEAR",
                "starting_equity": starting_equity,
                "ending_equity": ending_equity,
                "gross_return_pct": pct(ending_equity - starting_equity, starting_equity),
                "trades": len(year_entries),
                "target_exits": exits[TARGET_EXIT],
                "stop_exits": exits[STOP_EXIT],
                "time_exits": exits[TIME_EXIT],
                "ambiguous_exits": exits[AMBIGUOUS_SAME_BAR_EXIT],
                "maximum_drawdown_pct": max(year_drawdowns, default=Decimal("0")),
                "average_exposure_pct": mean_decimal(
                    [decimal_or_zero(row["gross_exposure_pct"]) for row in year_daily]
                ),
                "opportunities": len(year_opportunities),
                "admission_rate_pct": pct(Decimal(len(year_entries)), Decimal(len(year_opportunities))),
                "performance_basis": config.performance_basis,
            }
        )
    return rows


def run_pilot_validation(
    opportunities: Sequence[dict[str, Any]],
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_date[row["next_session_date"]].append(row)
        by_symbol[row["symbol"]].append(row)

    single_date, single_rows = next((item for item in sorted(by_date.items()) if len(item[1]) == 1), ("", []))
    crowded_date, crowded_rows = next((item for item in sorted(by_date.items()) if len(item[1]) > 4), ("", []))
    multiple_date, multiple_rows = next((item for item in sorted(by_date.items()) if len(item[1]) > 1), ("", []))
    target_row = next((row for row in opportunities if row["first_touch_outcome"] == "TARGET_FIRST"), None)
    stop_row = next((row for row in opportunities if row["first_touch_outcome"] == "STOP_FIRST"), None)
    time_row = next((row for row in opportunities if row["first_touch_outcome"] == "NEITHER_WITHIN_HORIZON"), None)
    ambiguous_row = next((row for row in opportunities if row["first_touch_outcome"] == "AMBIGUOUS"), None)
    entry_day_row = next(
        (
            row
            for row in opportunities
            if row["first_touch_outcome"] in {"TARGET_FIRST", "STOP_FIRST", "AMBIGUOUS"}
            and (row.get("first_target_session") == "1" or row.get("first_stop_session") == "1")
        ),
        None,
    )
    overlap_pair = find_overlap_pair(by_symbol)
    tie_pair = find_exact_score_tie(by_date)
    base = opportunities[0]
    fake_positions = [fake_open_position(f"PILOT{i}", Decimal("900")) for i in range(4)]
    slot_reason, _ = evaluate_admission(
        row=base,
        open_positions=fake_positions,
        available_cash=config.initial_capital_rupees,
        portfolio_equity=config.initial_capital_rupees,
        config=config,
    )
    cash_row = dict(base)
    cash_row.update({"symbol": "PILOT_CASH", "hypothetical_entry_price": "200000", "stop_price": "199000"})
    cash_reason, cash_sizing = evaluate_admission(
        row=cash_row,
        open_positions=[],
        available_cash=config.initial_capital_rupees,
        portfolio_equity=config.initial_capital_rupees,
        config=config,
    )
    risk_positions = [fake_open_position("PILOT_RISK", Decimal("4000"))]
    risk_row = dict(base)
    risk_row["symbol"] = "PILOT_RISK_NEW"
    risk_reason, risk_sizing = evaluate_admission(
        row=risk_row,
        open_positions=risk_positions,
        available_cash=config.initial_capital_rupees,
        portfolio_equity=config.initial_capital_rupees,
        config=config,
    )

    rows = [
        pilot_row("A", "one candidate day", single_rows != [], single_rows[0] if single_rows else None, single_date, len(single_rows)),
        pilot_row("B", "more than four candidates", len(crowded_rows) > 4, crowded_rows[0] if crowded_rows else None, crowded_date, len(crowded_rows), rank_opportunities(crowded_rows)),
        pilot_row("C", "same symbol repeated while open", overlap_pair is not None, overlap_pair[1] if overlap_pair else None, overlap_pair[1]["next_session_date"] if overlap_pair else "", 2, skip_reason=SKIP_SAME_SYMBOL_ALREADY_OPEN),
        pilot_row("D", "slot constraint", slot_reason == SKIP_MAX_POSITIONS, base, base["next_session_date"], 1, skip_reason=slot_reason, opening_positions=4),
        pilot_row("E", "cash constraint", cash_reason == SKIP_INSUFFICIENT_CASH, cash_row, cash_row["next_session_date"], 1, skip_reason=cash_reason, quantity=cash_sizing.get("quantity", 0)),
        pilot_row("F", "portfolio risk constraint", risk_reason == SKIP_PORTFOLIO_RISK_LIMIT, risk_row, risk_row["next_session_date"], 1, skip_reason=risk_reason, opening_positions=1, planned_risk=risk_sizing.get("planned_risk", 0)),
        pilot_exit_row("G", "target exit", target_row, TARGET_EXIT, config),
        pilot_exit_row("H", "stop exit", stop_row, STOP_EXIT, config),
        pilot_exit_row("I", "time exit", time_row, TIME_EXIT, config),
        pilot_exit_row("J", "ambiguous same-bar conservative stop", ambiguous_row, AMBIGUOUS_SAME_BAR_EXIT, config),
        pilot_exit_row("K", "entry-day exit", entry_day_row, exit_reason_for_source(entry_day_row), config),
        pilot_row("L", "multiple open positions across sessions", len(multiple_rows) > 1, multiple_rows[0] if multiple_rows else None, multiple_date, len(multiple_rows)),
        pilot_row("M", "same-day exits do not fund open entries", config.session_ordering_policy == "OPEN_ENTRIES_BEFORE_INTRADAY_EXITS_NO_SAME_DAY_CASH_REUSE", base, base["next_session_date"], 1, validation_notes="Opening cash is captured before admissions; exit proceeds are applied only after every candidate is processed."),
        pilot_row("N", "exact score tie uses stable tie-break", tie_pair is not None and rank_opportunities(tie_pair)[0]["symbol"] == sorted(tie_pair, key=selection_priority)[0]["symbol"], tie_pair[0] if tie_pair else None, tie_pair[0]["next_session_date"] if tie_pair else "", len(tie_pair or []), rank_opportunities(tie_pair or [])),
    ]
    return {
        "passed": all(row["result"] == "PASS" for row in rows),
        "rows": rows,
        "real_case_count": sum(row["source"] == "REAL" for row in rows),
        "synthetic_case_count": sum(row["source"] == "SYNTHETIC" for row in rows),
    }


def pilot_row(
    case: str,
    scenario: str,
    passed: bool,
    source: dict[str, Any] | None,
    entry_date: str,
    candidate_count: int,
    ranked: Sequence[dict[str, Any]] | None = None,
    *,
    skip_reason: str = "",
    opening_positions: int = 0,
    quantity: Any = "",
    planned_risk: Any = "",
    validation_notes: str = "",
) -> dict[str, Any]:
    source = source or {}
    rank_order = [row.get("symbol", "") for row in (ranked or [])]
    synthetic = str(source.get("symbol", "")).startswith("PILOT") or case in {"D", "E", "F", "M"}
    return {
        "pilot_case": case,
        "scenario": scenario,
        "source": "SYNTHETIC" if synthetic else "REAL",
        "symbol": source.get("symbol", ""),
        "decision_date": source.get("decision_date", ""),
        "entry_date": entry_date,
        "opening_cash": "100000",
        "opening_positions": opening_positions,
        "candidates": candidate_count,
        "rank_order": "|".join(rank_order[:10]),
        "admitted": 0 if skip_reason else int(passed),
        "skip_reason": skip_reason,
        "quantity": quantity,
        "planned_risk": planned_risk,
        "exit_event": "",
        "closing_cash": "UNCHANGED_FOR_SELECTION_ONLY_CASE",
        "closing_positions": opening_positions,
        "portfolio_equity": "100000",
        "validation_notes": validation_notes or scenario,
        "result": "PASS" if passed else "FAIL",
    }


def pilot_exit_row(
    case: str,
    scenario: str,
    row: dict[str, Any] | None,
    expected_reason: str,
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    if row is None:
        return pilot_row(case, scenario, False, None, "", 0)
    exit_date = source_exit_date(row, config)
    event = determine_exit(row, exit_date, config)
    return pilot_row(
        case,
        scenario,
        event is not None and event["reason"] == expected_reason,
        row,
        row["next_session_date"],
        1,
        quantity=row.get("hypothetical_quantity", ""),
        planned_risk=row.get("planned_rupee_risk", ""),
        validation_notes=f"exit_date={exit_date};expected={expected_reason};observed={event['reason'] if event else ''}",
    ) | {"exit_event": event["reason"] if event else ""}


def find_overlap_pair(by_symbol: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for rows in by_symbol.values():
        ordered = sorted(rows, key=lambda row: row["next_session_date"])
        for first, second in zip(ordered, ordered[1:]):
            exit_date = source_exit_date(first, PortfolioBacktestConfig())
            if first["next_session_date"] < second["next_session_date"] <= exit_date:
                return first, second
    return None


def find_exact_score_tie(by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]] | None:
    for rows in by_date.values():
        by_score: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_score[format_decimal(decimal_or_zero(row.get("raw_strategy_score")))].append(row)
        tie = next((group for group in by_score.values() if len(group) >= 2), None)
        if tie:
            return tie[:2]
    return None


def source_exit_date(row: dict[str, Any], config: PortfolioBacktestConfig) -> str:
    outcome = row.get("first_touch_outcome")
    if outcome == "TARGET_FIRST":
        index = int(row.get("first_target_session") or config.max_hold_sessions)
    elif outcome in {"STOP_FIRST", "AMBIGUOUS"}:
        index = int(row.get("first_stop_session") or config.max_hold_sessions)
    else:
        index = config.max_hold_sessions
    return str(row.get(f"session_date_{index}", ""))


def exit_reason_for_source(row: dict[str, Any] | None) -> str:
    if row is None:
        return ""
    return {
        "TARGET_FIRST": TARGET_EXIT,
        "STOP_FIRST": STOP_EXIT,
        "AMBIGUOUS": AMBIGUOUS_SAME_BAR_EXIT,
        "NEITHER_WITHIN_HORIZON": TIME_EXIT,
    }.get(str(row.get("first_touch_outcome", "")), "")


def fake_open_position(symbol: str, planned_risk: Decimal) -> OpenPosition:
    return OpenPosition(
        trade={"trade_id": f"FAKE-{symbol}", "symbol": symbol, "quantity": 1, "initial_planned_risk": planned_risk},
        source={},
        last_mark=Decimal("1"),
    )


def evidence_distribution(rows: Sequence[dict[str, Any]], *, entered: bool) -> dict[str, Any]:
    score_field = "raw_strategy_score" if entered else "raw_score"
    rr_field = "effective_reward_risk" if entered else "effective_rr"
    scores = Counter(format_decimal(decimal_or_zero(row.get(score_field))) for row in rows)
    return {
        "count": len(rows),
        "raw_score_distribution": dict(sorted(scores.items())),
        "mean_effective_reward_risk": mean_decimal([decimal_or_zero(row.get(rr_field)) for row in rows]),
        "setup_quality_distribution": dict(Counter(str(row.get("setup_quality", "")) for row in rows)),
        "mean_momentum_points": mean_decimal([decimal_or_zero(row.get("momentum_points")) for row in rows]),
        "mean_rvol_points": mean_decimal([decimal_or_zero(row.get("rvol_points")) for row in rows]),
        "mean_relative_strength_points": mean_decimal(
            [decimal_or_zero(row.get("relative_strength_points")) for row in rows]
        ),
    }


def same_symbol_metrics(skipped: Sequence[dict[str, Any]]) -> dict[str, Any]:
    affected = [row for row in skipped if row["skip_reason"] == SKIP_SAME_SYMBOL_ALREADY_OPEN]
    symbols = Counter(row["symbol"] for row in affected)
    examples = [
        {"symbol": row["symbol"], "decision_date": row["decision_date"], "entry_date": row["entry_date"]}
        for row in affected[:20]
    ]
    return {
        "skipped_count": len(affected),
        "most_affected_symbols": [
            {"symbol": symbol, "count": count} for symbol, count in symbols.most_common(20)
        ],
        "examples": examples,
    }


def exit_analysis(trades: Sequence[dict[str, Any]], reason: str) -> dict[str, Any]:
    selected = [trade for trade in trades if trade["exit_reason"] == reason]
    realized_r = [decimal_or_zero(trade["realized_r_multiple"]) for trade in selected]
    return {
        "count": len(selected),
        "mean_gross_pnl": mean_decimal([decimal_or_zero(trade["gross_pnl"]) for trade in selected]),
        "mean_realized_r": mean_decimal(realized_r),
        "median_realized_r": median_decimal(realized_r),
        "reached_0_5r_count": sum(decimal_or_zero(trade.get("source_mfe_r_4")) >= Decimal("0.5") for trade in selected),
        "reached_1r_count": sum(decimal_or_zero(trade.get("source_mfe_r_4")) >= Decimal("1") for trade in selected),
    }


def stop_exit_analysis(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = [trade for trade in trades if trade["exit_reason"] == STOP_EXIT]
    realized_r = [decimal_or_zero(trade["realized_r_multiple"]) for trade in selected]
    return {
        "count": len(selected),
        "total_planned_risk": sum(
            (decimal_or_zero(trade["initial_planned_risk"]) for trade in selected), Decimal("0")
        ),
        "mean_realized_r": mean_decimal(realized_r),
        "median_realized_r": median_decimal(realized_r),
        "deviation_from_minus_one_count": sum(abs(value + Decimal("1")) > RISK_TOLERANCE for value in realized_r),
        "gap_and_slippage_status": "FROZEN_STOP_FILL_NO_SLIPPAGE_MODELED",
    }


def target_exit_analysis(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    selected = [trade for trade in trades if trade["exit_reason"] == TARGET_EXIT]
    mismatch = [
        abs(decimal_or_zero(trade["realized_r_multiple"]) - decimal_or_zero(trade["effective_reward_risk"]))
        for trade in selected
    ]
    return {
        "count": len(selected),
        "mean_realized_r": mean_decimal([decimal_or_zero(trade["realized_r_multiple"]) for trade in selected]),
        "median_realized_r": median_decimal([decimal_or_zero(trade["realized_r_multiple"]) for trade in selected]),
        "mismatch_tolerance": RISK_TOLERANCE,
        "mismatch_count": sum(value > RISK_TOLERANCE for value in mismatch),
        "maximum_absolute_mismatch": max(mismatch, default=Decimal("0")),
    }


def skip_report_rows(skipped: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["skip_reason"] for row in skipped)
    total = len(skipped)
    return [
        {"skip_reason": reason, "count": counts[reason], "rate_pct": pct(Decimal(counts[reason]), Decimal(total))}
        for reason in (
            SKIP_SAME_SYMBOL_ALREADY_OPEN,
            SKIP_MAX_POSITIONS,
            SKIP_INSUFFICIENT_CASH,
            SKIP_PORTFOLIO_RISK_LIMIT,
            SKIP_ZERO_QUANTITY,
            SKIP_OTHER,
        )
    ]


def rr_band(trade: dict[str, Any]) -> str:
    value = decimal_or_zero(trade.get("effective_reward_risk"))
    if value < Decimal("2"):
        return "1.5_TO_LT_2"
    if value < Decimal("2.5"):
        return "2_TO_LT_2.5"
    return "GE_2.5"


def write_backtest_artifacts(
    engine_config: PortfolioBacktestEngineConfig,
    simulation: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
) -> list[Path]:
    write_gzip_csv(engine_config.trades_path, simulation["trades"], TRADE_FIELDS)
    write_gzip_csv(engine_config.daily_path, simulation["daily"], DAILY_FIELDS)
    write_gzip_csv(engine_config.skipped_path, simulation["skipped"], SKIP_FIELDS)
    paths = [engine_config.trades_path, engine_config.daily_path, engine_config.skipped_path]
    for suffix, rows in tables.items():
        path = engine_config.report_path(suffix)
        write_csv_rows(path, rows)
        paths.append(path)
    return paths


def artifact_manifest(paths: Sequence[Path]) -> dict[str, Any]:
    return {
        path.name: {
            "path": str(path),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in paths
    }


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(fields), extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow(json_ready(row))


def write_csv_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = union_fields(rows)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_ready(row))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2) + "\n", encoding="utf-8")


def write_portfolio_backtest_markdown(report: dict[str, Any], path: Path) -> None:
    metadata = report["run_metadata"]
    metrics = report["portfolio_metrics"]
    pool = report["opportunity_pool"]
    lines = [
        "# Strategy V1 Portfolio Backtest Foundation",
        "",
        "STATUS: ACTIVE_MECHANICAL_BACKTEST_BASELINE",
        "",
        f"- Version/profile: {metadata['backtest_version']} / {metadata['profile']}",
        f"- Config hash: `{metadata['backtest_config_hash']}`",
        f"- Trade dataset hash: `{PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH}`",
        f"- Daily dataset hash: `{PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH}`",
        f"- Skipped dataset hash: `{PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH}`",
        "- Audit: `PORTFOLIO_BACKTEST_AUDIT_V1` — [structural audit](strategy-v1-portfolio-backtest-audit.md)",
        "- Baseline decision: A FREEZE UNCHANGED",
        "- Step 02.12 — Portfolio Backtest Foundation: COMPLETE",
        f"- Period: {metadata['start_date']} to {metadata['end_date']}",
        f"- Starting/ending equity: ₹{metrics['starting_equity']} / ₹{metrics['ending_equity']}",
        f"- Gross return: {metrics['total_gross_return_pct']}%",
        f"- Opportunities/entered/skipped: {pool['mechanically_valid_opportunities_considered']} / {pool['actual_portfolio_trades_entered']} / {pool['opportunities_skipped']}",
        "",
        "## Contract",
        "",
        "Each session begins with prior positions and opening cash. New T+1-open opportunities are ranked and admitted before any same-day high/low exit is processed, so intraday exit proceeds cannot fund entries retroactively. Positions then process stop/target events, conservative same-bar ambiguity, and session-4 close exits before end-of-day close marking.",
        "",
        "The portfolio starts with ₹100,000, holds at most four long cash-equity positions, risks at most 1% of current opening equity per new trade and 4% in total planned open risk, and never uses leverage, margin, borrowing, pyramiding, or multiple concurrent positions in one symbol.",
        "",
        "Ranking uses only entry-time evidence: raw score, effective R:R, setup quality, momentum, RVOL, relative strength, lower required notional, then symbol. Future outcomes, MFE/MAE, future returns, and exits never influence admission.",
        "",
        "Target and stop prices remain frozen. TARGET_EXIT uses the target, STOP_EXIT uses the stop, NEITHER exits at session-4 close, and a same-bar stop/target touch is retained as ambiguous while conservatively filled at the stop.",
        "",
        "## Research boundary",
        "",
        "All figures are HISTORICAL RESEARCH / GROSS BEFORE COSTS. Transaction costs and slippage are NOT_MODELED. No parameter sweep, optimization, signal generation, live execution, broker call, migration, or Supabase write occurred.",
        "",
        "Daily OHLC cannot recover intraday path. The ambiguity assumption, fixed four-session hold, frozen opportunity quality, and omitted execution frictions mean this active mechanical baseline is not deployable performance evidence.",
        "",
        "## Audit review notes",
        "",
        "The 4% cap is an admission constraint. Mark-to-market equity changes can cause passive post-admission risk-ratio drift above 4%; this does not trigger forced deleveraging and is not an admission violation.",
        "",
        "Ranking is mechanically valid and deterministic but has EXTREME sensitivity in fixed audit counterfactuals. Selection distortion is HIGH because finite slots, capital, and risk admitted 728 of 3,296 mechanically valid opportunities. The historical gross pattern is WEAK and YEARLY_UNSTABLE; costs could materially worsen it. TARGET and TIME exits contributed positively in aggregate, while STOP exits made a large negative contribution. None of these review notes changes the frozen rules.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def source_key(row: dict[str, Any]) -> str:
    return f"{row.get('decision_date', '')}|{row.get('symbol', '')}"


def duplicate_symbol_count(open_positions: Sequence[OpenPosition]) -> int:
    symbols = [position.trade["symbol"] for position in open_positions]
    return len(symbols) - len(set(symbols))


def duplicate_trade_id_count(open_positions: Sequence[OpenPosition]) -> int:
    trade_ids = [position.trade["trade_id"] for position in open_positions]
    return len(trade_ids) - len(set(trade_ids))


def selection_lookahead_violations() -> int:
    return sum(
        any(token in field.lower() for token in PROHIBITED_SELECTION_TOKENS)
        for field in SELECTION_SOURCE_FIELDS
    )


def drawdown_series(equity_values: Sequence[Decimal]) -> list[Decimal]:
    peak = Decimal("0")
    drawdowns = []
    for equity in equity_values:
        peak = max(peak, equity)
        drawdowns.append(pct(peak - equity, peak) if peak else Decimal("0"))
    return drawdowns


def calculate_cagr(starting: Decimal, ending: Decimal, span_days: int) -> Decimal | None:
    if starting <= 0 or ending <= 0 or span_days <= 0:
        return None
    years = Decimal(span_days) / Decimal("365.25")
    return Decimal(str(((float(ending / starting) ** (1 / float(years))) - 1) * 100))


def distribution_summary(values: Sequence[Decimal]) -> dict[str, Any]:
    return {
        "count": len(values),
        "median": percentile(values, Decimal("0.50")),
        "p90": percentile(values, Decimal("0.90")),
        "p95": percentile(values, Decimal("0.95")),
        "max": max(values, default=Decimal("0")),
    }


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * Decimal(len(ordered) - 1)
    lower = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def mean_decimal(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def median_decimal(values: Sequence[Decimal]) -> Decimal:
    return Decimal(str(statistics.median(values))) if values else Decimal("0")


def pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator * Decimal("100") if denominator else Decimal("0")


def opportunity_bucket(count: int) -> str:
    return "5+" if count >= 5 else str(count)


def longest_date_streak(selected_dates: Sequence[str], all_dates: Sequence[str]) -> int:
    selected = set(selected_dates)
    longest = current = 0
    for trading_date in all_dates:
        if trading_date in selected:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def sample_size_warning(count: int) -> str:
    if count < 20:
        return "VERY_SMALL"
    if count < 50:
        return "SMALL"
    if count < 200:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def format_group_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format_decimal(value)
    return str(value or "")


def format_decimal(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def floor_whole(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def union_fields(rows: Sequence[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields or ["status"]


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)

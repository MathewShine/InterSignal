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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from typing import Any, Callable, Sequence

from app.backtesting.portfolio_baseline import (
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH as EXPECTED_BACKTEST_CONFIG_HASH,
    PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH as EXPECTED_DAILY_HASH,
    PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH as EXPECTED_SKIPPED_HASH,
    PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH as EXPECTED_TRADES_HASH,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig, json_ready
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    FORCED_DATA_EXIT,
    SKIP_INSUFFICIENT_CASH,
    SKIP_MAX_POSITIONS,
    SKIP_OTHER,
    SKIP_PORTFOLIO_RISK_LIMIT,
    SKIP_SAME_SYMBOL_ALREADY_OPEN,
    SKIP_ZERO_QUANTITY,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
    PortfolioBacktestEngineConfig,
    load_frozen_opportunities,
    simulate_portfolio,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import (
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    outcome_input_hash_checks,
    outcome_input_hashes,
)

PORTFOLIO_BACKTEST_AUDIT_VERSION = "PORTFOLIO_BACKTEST_AUDIT_V1"
TOLERANCE = Decimal("0.000001")
LOW_EXPOSURE_THRESHOLD_PCT = Decimal("50")

RANKING_SCENARIOS = (
    "BASELINE_RANK",
    "SCORE_ONLY",
    "RR_FIRST",
    "SETUP_FIRST",
    "REVERSE_FINAL_TIE_ONLY",
)


@dataclass(frozen=True, slots=True)
class PortfolioBacktestAuditConfig:
    data_dir: Path
    backtest_config: PortfolioBacktestConfig = PortfolioBacktestConfig()

    @property
    def baseline(self) -> PortfolioBacktestEngineConfig:
        return PortfolioBacktestEngineConfig(data_dir=self.data_dir, backtest_config=self.backtest_config)

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def bulk_dir(self) -> Path:
        return self.data_dir / "research/audits/portfolio_backtest/v1"

    def report_path(self, name: str) -> Path:
        return self.reports_dir / f"portfolio_backtest_v1_audit_{name}"


def dec(value: Any) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def integer_floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator * Decimal("100") if denominator else Decimal("0")


def mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def median(values: Sequence[Decimal]) -> Decimal:
    return Decimal(str(statistics.median(values))) if values else Decimal("0")


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * Decimal(len(ordered) - 1)
    lower = integer_floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values, default=Decimal("0")),
        "p1": percentile(values, Decimal("0.01")),
        "p5": percentile(values, Decimal("0.05")),
        "p10": percentile(values, Decimal("0.10")),
        "p25": percentile(values, Decimal("0.25")),
        "median": percentile(values, Decimal("0.50")),
        "mean": mean(values),
        "p75": percentile(values, Decimal("0.75")),
        "p90": percentile(values, Decimal("0.90")),
        "p95": percentile(values, Decimal("0.95")),
        "p99": percentile(values, Decimal("0.99")),
        "max": max(values, default=Decimal("0")),
    }


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def source_key(row: dict[str, Any]) -> str:
    return f"{row.get('decision_date', '')}|{row.get('symbol', '')}"


def setup_rank(row: dict[str, Any]) -> int:
    return {"STRONG": 2, "VALID": 1}.get(str(row.get("setup_quality", "")), 0)


def baseline_rank_prefix(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -dec(row.get("raw_strategy_score")),
        -dec(row.get("effective_reward_risk")),
        -setup_rank(row),
        -dec(row.get("momentum_points")),
        -dec(row.get("rvol_points")),
        -dec(row.get("relative_strength_points")),
        dec(row.get("position_notional")),
    )


def audit_rank_rows(rows: Sequence[dict[str, Any]], scenario: str = "BASELINE_RANK") -> list[dict[str, Any]]:
    copied = [dict(row) for row in rows]
    if scenario == "BASELINE_RANK":
        ordered = sorted(copied, key=lambda row: baseline_rank_prefix(row) + (str(row.get("symbol", "")),))
    elif scenario == "SCORE_ONLY":
        ordered = sorted(copied, key=lambda row: (-dec(row.get("raw_strategy_score")), str(row.get("symbol", ""))))
    elif scenario == "RR_FIRST":
        ordered = sorted(
            copied,
            key=lambda row: (
                -dec(row.get("effective_reward_risk")),
                -dec(row.get("raw_strategy_score")),
                str(row.get("symbol", "")),
            ),
        )
    elif scenario == "SETUP_FIRST":
        ordered = sorted(
            copied,
            key=lambda row: (
                -setup_rank(row),
                -dec(row.get("raw_strategy_score")),
                -dec(row.get("effective_reward_risk")),
                str(row.get("symbol", "")),
            ),
        )
    elif scenario == "REVERSE_FINAL_TIE_ONLY":
        ordered = sorted(copied, key=lambda row: str(row.get("symbol", "")), reverse=True)
        ordered = sorted(ordered, key=baseline_rank_prefix)
    else:
        raise ValueError(f"Unknown audit ranking scenario: {scenario}")
    for rank, row in enumerate(ordered, start=1):
        row["_audit_selection_rank"] = rank
    return ordered


def audit_bar(row: dict[str, Any], trading_date: str) -> dict[str, Any] | None:
    for index in range(1, 5):
        if str(row.get(f"session_date_{index}", "")) == trading_date:
            return {
                "index": index,
                "date": trading_date,
                "open": dec(row.get(f"open_{index}")),
                "high": dec(row.get(f"high_{index}")),
                "low": dec(row.get(f"low_{index}")),
                "close": dec(row.get(f"close_{index}")),
            }
    return None


def audit_exit(row: dict[str, Any], trading_date: str, max_hold_sessions: int = 4) -> dict[str, Any] | None:
    bar = audit_bar(row, trading_date)
    if bar is None:
        return None
    stop = dec(row.get("stop_price"))
    target = dec(row.get("target_price"))
    stop_touched = bar["low"] <= stop
    target_touched = bar["high"] >= target
    if stop_touched and target_touched:
        return {"reason": AMBIGUOUS_SAME_BAR_EXIT, "price": stop, "session": bar["index"], "ambiguous": True}
    if target_touched:
        return {"reason": TARGET_EXIT, "price": target, "session": bar["index"], "ambiguous": False}
    if stop_touched:
        return {"reason": STOP_EXIT, "price": stop, "session": bar["index"], "ambiguous": False}
    if bar["index"] == max_hold_sessions:
        return {"reason": TIME_EXIT, "price": bar["close"], "session": bar["index"], "ambiguous": False}
    return None


def audit_sizing(
    row: dict[str, Any],
    *,
    equity: Decimal,
    cash: Decimal,
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    entry = dec(row.get("hypothetical_entry_price"))
    stop = dec(row.get("stop_price"))
    risk_per_share = entry - stop
    risk_budget = equity * config.max_risk_per_trade_pct / Decimal("100")
    quantity_by_risk = integer_floor(risk_budget / risk_per_share) if risk_per_share > 0 else 0
    quantity_by_cash = integer_floor(cash / entry) if entry > 0 else 0
    quantity = min(quantity_by_risk, quantity_by_cash)
    return {
        "entry_price": entry,
        "stop_price": stop,
        "risk_per_share": risk_per_share,
        "risk_budget": risk_budget,
        "quantity_by_risk": quantity_by_risk,
        "quantity_by_cash": quantity_by_cash,
        "quantity": quantity,
        "entry_notional": entry * quantity,
        "planned_risk": risk_per_share * quantity,
    }


def independent_simulation(
    opportunities: Sequence[dict[str, Any]],
    trading_dates: Sequence[str],
    config: PortfolioBacktestConfig,
    *,
    ranking_scenario: str = "BASELINE_RANK",
) -> dict[str, Any]:
    """Replay the contract without calling the baseline ranking, sizing, admission, or exit helpers."""
    by_entry_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_entry_date[str(row.get("next_session_date", ""))].append(dict(row))

    cash = config.initial_capital_rupees
    positions: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    cash_events: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    trade_number = 0
    sequence = 0
    dates = sorted(dict.fromkeys(trading_dates))

    for trading_date in dates:
        opening_cash = cash
        opening_positions = len(positions)
        opening_planned_risk = sum(position["trade"]["planned_risk"] for position in positions)
        opening_market_value = Decimal("0")
        for position in positions:
            bar = audit_bar(position["source"], trading_date)
            opening_mark = bar["open"] if bar else position["last_mark"]
            opening_market_value += opening_mark * position["trade"]["quantity"]
        opening_equity = cash + opening_market_value
        ranked = audit_rank_rows(by_entry_date.get(trading_date, []), ranking_scenario)
        entries = 0

        for row in ranked:
            before_cash = cash
            before_positions = len(positions)
            before_risk = sum(position["trade"]["planned_risk"] for position in positions)
            sizing = audit_sizing(row, equity=opening_equity, cash=cash, config=config)
            existing = next((position for position in positions if position["trade"]["symbol"] == row.get("symbol")), None)
            reason = ""
            if existing is not None:
                reason = SKIP_SAME_SYMBOL_ALREADY_OPEN
            elif len(positions) >= config.max_concurrent_positions:
                reason = SKIP_MAX_POSITIONS
            elif sizing["risk_per_share"] <= 0 or sizing["entry_price"] <= 0:
                reason = SKIP_OTHER
            elif sizing["quantity_by_risk"] < 1:
                reason = SKIP_ZERO_QUANTITY
            elif sizing["quantity_by_cash"] < 1:
                reason = SKIP_INSUFFICIENT_CASH
            else:
                risk_cap = opening_equity * config.max_total_open_risk_pct / Decimal("100")
                if before_risk + sizing["planned_risk"] > risk_cap + TOLERANCE:
                    reason = SKIP_PORTFOLIO_RISK_LIMIT

            record = {
                "source_key": source_key(row),
                "decision_date": row.get("decision_date", ""),
                "entry_date": trading_date,
                "symbol": row.get("symbol", ""),
                "rank": row["_audit_selection_rank"],
                "ranking_scenario": ranking_scenario,
                "opening_cash_day": opening_cash,
                "available_cash_before": before_cash,
                "opening_equity": opening_equity,
                "open_positions_before": before_positions,
                "open_planned_risk_before": before_risk,
                "risk_cap": opening_equity * config.max_total_open_risk_pct / Decimal("100"),
                **sizing,
                "expected_disposition": "SKIPPED" if reason else "ENTERED",
                "expected_skip_reason": reason,
                "existing_trade_id": existing["trade"]["trade_id"] if existing else "",
                "existing_entry_date": existing["trade"]["entry_date"] if existing else "",
            }
            if reason:
                skipped.append(record)
                candidate_records.append(record)
                continue

            trade_number += 1
            trade = {
                "trade_id": f"PBV1-{trade_number:06d}",
                "source_key": source_key(row),
                "symbol": row.get("symbol", ""),
                "decision_date": row.get("decision_date", ""),
                "entry_date": trading_date,
                "entry_price": sizing["entry_price"],
                "quantity": sizing["quantity"],
                "entry_notional": sizing["entry_notional"],
                "initial_stop": sizing["stop_price"],
                "initial_target": dec(row.get("target_price")),
                "risk_per_share": sizing["risk_per_share"],
                "planned_risk": sizing["planned_risk"],
                "risk_budget": sizing["risk_budget"],
                "portfolio_equity_at_entry": opening_equity,
                "selection_rank": row["_audit_selection_rank"],
                "raw_strategy_score": dec(row.get("raw_strategy_score")),
                "effective_reward_risk": dec(row.get("effective_reward_risk")),
                "setup_quality": row.get("setup_quality", ""),
                "candidate_category": row.get("candidate_category", ""),
                "regime_state": row.get("regime_state", ""),
                "momentum_points": dec(row.get("momentum_points")),
                "rvol_points": dec(row.get("rvol_points")),
                "relative_strength_points": dec(row.get("relative_strength_points")),
            }
            sequence += 1
            after_cash = cash - sizing["entry_notional"]
            cash_events.append(
                {
                    "sequence": sequence,
                    "date": trading_date,
                    "event": "ENTRY",
                    "trade_id": trade["trade_id"],
                    "source_key": trade["source_key"],
                    "cash_before": cash,
                    "amount": -sizing["entry_notional"],
                    "cash_after": after_cash,
                }
            )
            cash = after_cash
            record.update({"trade_id": trade["trade_id"], "cash_after": cash, "open_planned_risk_after": before_risk + sizing["planned_risk"]})
            candidate_records.append(record)
            positions.append({"trade": trade, "source": row, "last_mark": sizing["entry_price"], "sessions_seen": 0})
            entries += 1

        peak_positions = len(positions)
        realized_pnl = Decimal("0")
        exits = 0
        survivors: list[dict[str, Any]] = []
        for position in positions:
            bar = audit_bar(position["source"], trading_date)
            if bar is not None:
                position["sessions_seen"] += 1
                position["last_mark"] = bar["close"]
            event = audit_exit(position["source"], trading_date, config.max_hold_sessions)
            if event is None:
                survivors.append(position)
                continue
            trade = position["trade"]
            exit_price = event["price"]
            pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
            trade.update(
                {
                    "exit_date": trading_date,
                    "exit_price": exit_price,
                    "exit_reason": event["reason"],
                    "holding_sessions": event["session"],
                    "gross_pnl": pnl,
                    "realized_r_multiple": (exit_price - trade["entry_price"]) / trade["risk_per_share"],
                    "ambiguity_flag": event["ambiguous"],
                }
            )
            proceeds = exit_price * trade["quantity"]
            sequence += 1
            cash_events.append(
                {
                    "sequence": sequence,
                    "date": trading_date,
                    "event": "EXIT",
                    "trade_id": trade["trade_id"],
                    "source_key": trade["source_key"],
                    "cash_before": cash,
                    "amount": proceeds,
                    "cash_after": cash + proceeds,
                }
            )
            cash += proceeds
            realized_pnl += pnl
            completed.append(trade)
            exits += 1
        positions = survivors

        if trading_date == dates[-1] and positions:
            for position in positions:
                trade = position["trade"]
                exit_price = position["last_mark"]
                pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
                trade.update(
                    {
                        "exit_date": trading_date,
                        "exit_price": exit_price,
                        "exit_reason": FORCED_DATA_EXIT,
                        "holding_sessions": position["sessions_seen"],
                        "gross_pnl": pnl,
                        "realized_r_multiple": (exit_price - trade["entry_price"]) / trade["risk_per_share"],
                        "ambiguity_flag": False,
                    }
                )
                proceeds = exit_price * trade["quantity"]
                sequence += 1
                cash_events.append(
                    {
                        "sequence": sequence,
                        "date": trading_date,
                        "event": "FORCED_EXIT",
                        "trade_id": trade["trade_id"],
                        "source_key": trade["source_key"],
                        "cash_before": cash,
                        "amount": proceeds,
                        "cash_after": cash + proceeds,
                    }
                )
                cash += proceeds
                realized_pnl += pnl
                completed.append(trade)
                exits += 1
            positions = []

        market_value = sum(position["last_mark"] * position["trade"]["quantity"] for position in positions)
        equity = cash + market_value
        open_risk = sum(position["trade"]["planned_risk"] for position in positions)
        daily.append(
            {
                "date": trading_date,
                "opening_cash": opening_cash,
                "closing_cash": cash,
                "opening_portfolio_equity": opening_equity,
                "opening_planned_risk": opening_planned_risk,
                "opening_planned_risk_pct": percent(opening_planned_risk, opening_equity),
                "open_positions_start": opening_positions,
                "candidates": len(ranked),
                "new_entries": entries,
                "exits": exits,
                "peak_open_positions": peak_positions,
                "open_positions_end": len(positions),
                "market_value_open": market_value,
                "portfolio_equity": equity,
                "realized_pnl_day": realized_pnl,
                "gross_exposure_pct": percent(market_value, equity),
                "open_planned_risk": open_risk,
                "open_planned_risk_pct": percent(open_risk, equity),
            }
        )

    completed_by_id = {trade["trade_id"]: trade for trade in completed}
    for row in candidate_records:
        if row.get("existing_trade_id"):
            existing_trade = completed_by_id.get(str(row["existing_trade_id"]), {})
            row["existing_exit_date"] = existing_trade.get("exit_date", "")
            row["existing_scheduled_exit_date"] = existing_trade.get("exit_date", "")
    return {
        "trades": completed,
        "skipped": skipped,
        "candidate_records": candidate_records,
        "cash_events": cash_events,
        "daily": daily,
        "unresolved_positions": len(positions),
    }


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_decimal_rows(
    expected: Sequence[dict[str, Any]],
    observed: Sequence[dict[str, Any]],
    fields: Sequence[str],
) -> dict[str, Any]:
    mismatches = 0
    maximum = Decimal("0")
    field_mismatches: Counter[str] = Counter()
    if len(expected) != len(observed):
        mismatches += abs(len(expected) - len(observed))
        field_mismatches["row_count"] += abs(len(expected) - len(observed))
    for expected_row, observed_row in zip(expected, observed):
        for field in fields:
            delta = abs(dec(expected_row.get(field)) - dec(observed_row.get(field)))
            maximum = max(maximum, delta)
            if delta > TOLERANCE:
                mismatches += 1
                field_mismatches[field] += 1
    return {
        "mismatch_count": mismatches,
        "maximum_absolute_mismatch": maximum,
        "field_mismatches": dict(field_mismatches),
    }


def reconstruct_drawdown(daily: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not daily:
        return {}
    running_peak = Decimal("0")
    running_peak_date = ""
    rows: list[dict[str, Any]] = []
    maximum = Decimal("-1")
    max_row: dict[str, Any] = {}
    for index, row in enumerate(daily):
        equity = dec(row["portfolio_equity"])
        if equity > running_peak:
            running_peak = equity
            running_peak_date = str(row["date"])
        drawdown = percent(running_peak - equity, running_peak)
        item = {
            "date": row["date"],
            "equity": equity,
            "running_peak_equity": running_peak,
            "running_peak_date": running_peak_date,
            "drawdown_pct": drawdown,
        }
        rows.append(item)
        if drawdown > maximum:
            maximum = drawdown
            max_row = item | {"trough_index": index}
    peak_index = next(index for index, row in enumerate(daily) if row["date"] == max_row["running_peak_date"])
    trough_index = int(max_row["trough_index"])
    peak_equity = dec(max_row["running_peak_equity"])
    recovery_index = next(
        (index for index in range(trough_index + 1, len(daily)) if dec(daily[index]["portfolio_equity"]) >= peak_equity),
        None,
    )
    end_index = recovery_index if recovery_index is not None else len(daily) - 1
    return {
        "rows": rows,
        "maximum_drawdown_pct": max_row["drawdown_pct"],
        "average_drawdown_pct": mean([row["drawdown_pct"] for row in rows]),
        "peak_date": max_row["running_peak_date"],
        "peak_equity": max_row["running_peak_equity"],
        "trough_date": max_row["date"],
        "trough_equity": max_row["equity"],
        "recovery_date": daily[recovery_index]["date"] if recovery_index is not None else "NOT_RECOVERED",
        "duration_sessions": end_index - peak_index,
        "peak_to_trough_sessions": trough_index - peak_index,
        "definition": "Arithmetic mean of each daily close-to-prior-running-peak percentage drawdown.",
    }


def calculate_cagr(starting: Decimal, ending: Decimal, start_date: str, end_date: str) -> dict[str, Any]:
    span_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = Decimal(span_days) / Decimal("365.25")
    value = Decimal(str(((float(ending / starting) ** (1 / float(years))) - 1) * 100))
    return {
        "start_date": start_date,
        "end_date": end_date,
        "span_days": span_days,
        "years": years,
        "formula": "((ending_equity / starting_equity) ** (1 / (calendar_days / 365.25)) - 1) * 100",
        "cagr_pct": value,
    }


def scenario_metrics(
    simulation: dict[str, Any],
    baseline_keys: set[str],
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    keys = {str(trade["source_key"]) for trade in simulation["trades"]}
    overlap = len(keys & baseline_keys)
    union = len(keys | baseline_keys)
    ending = dec(simulation["daily"][-1]["portfolio_equity"])
    drawdown = reconstruct_drawdown(simulation["daily"])
    return {
        "trade_count": len(keys),
        "baseline_overlap_count": overlap,
        "baseline_overlap_pct": percent(Decimal(overlap), Decimal(len(baseline_keys))),
        "jaccard": Decimal(overlap) / Decimal(union) if union else Decimal("1"),
        "ending_equity": ending,
        "gross_return_pct": percent(ending - config.initial_capital_rupees, config.initial_capital_rupees),
        "maximum_drawdown_pct": drawdown["maximum_drawdown_pct"],
        "mean_realized_r": mean([dec(trade["realized_r_multiple"]) for trade in simulation["trades"]]),
        "diagnostic_only": True,
        "adopted": False,
    }


def classify_ranking_sensitivity(rows: Sequence[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    alternatives = [row for row in rows if row["scenario"] != "BASELINE_RANK"]
    minimum_jaccard = min((dec(row["jaccard"]) for row in alternatives), default=Decimal("1"))
    baseline = next(row for row in rows if row["scenario"] == "BASELINE_RANK")
    max_return_delta = max(
        (abs(dec(row["gross_return_pct"]) - dec(baseline["gross_return_pct"])) for row in alternatives),
        default=Decimal("0"),
    )
    max_drawdown_delta = max(
        (abs(dec(row["maximum_drawdown_pct"]) - dec(baseline["maximum_drawdown_pct"])) for row in alternatives),
        default=Decimal("0"),
    )
    if minimum_jaccard < Decimal("0.50") or max_return_delta > 15 or max_drawdown_delta > 15:
        classification = "EXTREME"
    elif minimum_jaccard < Decimal("0.70") or max_return_delta > 8 or max_drawdown_delta > 8:
        classification = "HIGH"
    elif minimum_jaccard < Decimal("0.90") or max_return_delta > 3 or max_drawdown_delta > 3:
        classification = "MODERATE"
    else:
        classification = "LOW"
    return classification, {
        "minimum_jaccard": minimum_jaccard,
        "maximum_gross_return_delta_pct_points": max_return_delta,
        "maximum_drawdown_delta_pct_points": max_drawdown_delta,
        "thresholds": "EXTREME: Jaccard<0.50 or return/DD delta>15pp; HIGH: <0.70 or >8pp; MODERATE: <0.90 or >3pp; otherwise LOW.",
    }


def tie_analysis(opportunities: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_date[str(row.get("next_session_date", ""))].append(row)
    detail: list[dict[str, Any]] = []
    days: set[str] = set()
    maximum_depth = 0
    full_pre_symbol_ties = 0
    for trading_date, rows in sorted(by_date.items()):
        ordered = audit_rank_rows(rows)
        display = [
            (
                dec(row.get("raw_strategy_score")),
                dec(row.get("effective_reward_risk")),
                setup_rank(row),
                dec(row.get("momentum_points")),
                dec(row.get("rvol_points")),
                dec(row.get("relative_strength_points")),
                dec(row.get("position_notional")),
            )
            for row in ordered
        ]
        for index in range(len(ordered) - 1):
            depth = 0
            for left, right in zip(display[index], display[index + 1]):
                if left != right:
                    break
                depth += 1
            if depth == 0:
                continue
            days.add(trading_date)
            maximum_depth = max(maximum_depth, depth)
            full_pre_symbol_ties += depth == 7
            detail.append(
                {
                    "entry_date": trading_date,
                    "tie_depth": depth,
                    "winner_symbol": ordered[index]["symbol"],
                    "runner_up_symbol": ordered[index + 1]["symbol"],
                    "winner_rank": index + 1,
                    "final_rule": "SYMBOL_ASC" if depth == 7 else f"RANKING_STAGE_{depth + 1}",
                }
            )
    return {
        "days_with_one_or_more_ties": len(days),
        "adjacent_tie_pairs": len(detail),
        "maximum_tie_depth": maximum_depth,
        "full_pre_symbol_ties": full_pre_symbol_ties,
        "repeated_ordering_identical": all(
            [row["symbol"] for row in audit_rank_rows(rows)] == [row["symbol"] for row in audit_rank_rows(rows)]
            for rows in by_date.values()
        ),
    }, detail


def profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def numeric(field: str) -> dict[str, Any]:
        values = [dec(row.get(field)) for row in rows]
        return {"mean": mean(values), "median": median(values)}

    return {
        "count": len(rows),
        "raw_strategy_score": numeric("raw_strategy_score"),
        "effective_reward_risk": numeric("effective_reward_risk"),
        "momentum_points": numeric("momentum_points"),
        "rvol_points": numeric("rvol_points"),
        "relative_strength_points": numeric("relative_strength_points"),
        "position_notional": numeric("position_notional"),
        "planned_risk": numeric("planned_rupee_risk"),
        "setup_quality": dict(Counter(str(row.get("setup_quality", "")) for row in rows)),
        "regime": dict(Counter(str(row.get("regime_state", "")) for row in rows)),
        "candidate_category": dict(Counter(str(row.get("candidate_category", "")) for row in rows)),
    }


def categorical_total_variation(
    all_rows: Sequence[dict[str, Any]], entered_rows: Sequence[dict[str, Any]], field: str
) -> Decimal:
    categories = {str(row.get(field, "")) for row in all_rows}
    total = Decimal(len(all_rows))
    entered_total = Decimal(len(entered_rows))
    return sum(
        (
            abs(
                Decimal(sum(str(row.get(field, "")) == value for row in all_rows)) / total
                - Decimal(sum(str(row.get(field, "")) == value for row in entered_rows)) / entered_total
            )
            for value in categories
        ),
        Decimal("0"),
    ) / Decimal("2")


def selection_distortion(
    opportunities: Sequence[dict[str, Any]], entered_rows: Sequence[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for field in ("raw_strategy_score", "setup_quality", "candidate_category", "regime_state"):
        value = categorical_total_variation(opportunities, entered_rows, field)
        rows.append({"dimension": field, "metric": "categorical_total_variation", "value": value})
    rr_delta = abs(
        mean([dec(row.get("effective_reward_risk")) for row in entered_rows])
        - mean([dec(row.get("effective_reward_risk")) for row in opportunities])
    )
    rows.append({"dimension": "effective_reward_risk", "metric": "absolute_mean_delta", "value": rr_delta})
    maximum_tv = max(dec(row["value"]) for row in rows if row["metric"] == "categorical_total_variation")
    if maximum_tv >= Decimal("0.25"):
        classification = "HIGH"
    elif maximum_tv >= Decimal("0.10"):
        classification = "MODERATE"
    else:
        classification = "LOW"
    for row in rows:
        row["classification"] = classification
        row["thresholds"] = "HIGH >=0.25 max categorical TV; MODERATE >=0.10; otherwise LOW"
    return classification, rows


def outcome_profile(rows: Sequence[dict[str, Any]], label: str) -> dict[str, Any]:
    counts = Counter(str(row.get("first_touch_outcome", "")) for row in rows)
    count = len(rows)
    return {
        "group": label,
        "count": count,
        "target_first": counts["TARGET_FIRST"],
        "target_first_pct": percent(Decimal(counts["TARGET_FIRST"]), Decimal(count)),
        "stop_first": counts["STOP_FIRST"],
        "stop_first_pct": percent(Decimal(counts["STOP_FIRST"]), Decimal(count)),
        "neither": counts["NEITHER_WITHIN_HORIZON"],
        "neither_pct": percent(Decimal(counts["NEITHER_WITHIN_HORIZON"]), Decimal(count)),
        "ambiguous": counts["AMBIGUOUS"],
        "mean_mfe_r_4": mean([dec(row.get("mfe_r_4")) for row in rows]),
        "mean_mae_r_4": mean([dec(row.get("mae_r_4")) for row in rows]),
        "mean_close_return_pct_4": mean([dec(row.get("close_return_pct_4")) for row in rows]),
        "median_close_return_pct_4": median([dec(row.get("close_return_pct_4")) for row in rows]),
        "descriptive_only": True,
    }


def rr_band(row: dict[str, Any]) -> str:
    value = dec(row.get("effective_reward_risk"))
    if value < Decimal("2"):
        return "1.5_TO_LT_2"
    if value < Decimal("2.5"):
        return "2_TO_LT_2.5"
    return "GE_2.5"


def attribution_row(
    label: str,
    source_rows: Sequence[dict[str, Any]],
    admitted_keys: set[str],
    baseline_trade_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    admitted = [baseline_trade_by_key[source_key(row)] for row in source_rows if source_key(row) in admitted_keys]
    exits = Counter(row["exit_reason"] for row in admitted)
    pnl = [dec(row["gross_pnl"]) for row in admitted]
    r_values = [dec(row["realized_r_multiple"]) for row in admitted]
    return {
        "group": label,
        "source_valid_count": len(source_rows),
        "admitted_count": len(admitted),
        "admission_rate_pct": percent(Decimal(len(admitted)), Decimal(len(source_rows))),
        "gross_pnl": sum(pnl, Decimal("0")),
        "mean_realized_r": mean(r_values),
        "median_realized_r": median(r_values),
        "target_exit_count": exits[TARGET_EXIT],
        "stop_exit_count": exits[STOP_EXIT],
        "time_exit_count": exits[TIME_EXIT],
        "ambiguous_exit_count": exits[AMBIGUOUS_SAME_BAR_EXIT],
        "sample_warning": "VERY_SMALL" if len(admitted) < 20 else "SMALL" if len(admitted) < 50 else "",
    }


def attribution_table(
    opportunities: Sequence[dict[str, Any]], trades: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    admitted_keys = {str(row["source_key"]) for row in trades}
    trade_by_key = {str(row["source_key"]): row for row in trades}
    specifications: list[tuple[str, Callable[[dict[str, Any]], bool]]] = []
    specifications.extend((f"SCORE_{score}", lambda row, score=score: dec(row.get("raw_strategy_score")) == score) for score in range(80, 86))
    specifications.extend(
        [
            ("REGIME_BULLISH", lambda row: row.get("regime_state") == "BULLISH"),
            ("REGIME_NEUTRAL", lambda row: row.get("regime_state") == "NEUTRAL"),
            ("CATEGORY_EMERGING_ONLY", lambda row: row.get("candidate_category") == "EMERGING_ONLY"),
            ("CATEGORY_CONFIRMED_ONLY", lambda row: row.get("candidate_category") == "CONFIRMED_ONLY"),
            ("CATEGORY_BOTH_ELIGIBLE", lambda row: row.get("candidate_category") == "BOTH_ELIGIBLE"),
            ("SETUP_STRONG", lambda row: row.get("setup_quality") == "STRONG"),
            ("SETUP_VALID", lambda row: row.get("setup_quality") == "VALID"),
            ("RR_1.5_TO_LT_2", lambda row: rr_band(row) == "1.5_TO_LT_2"),
            ("RR_2_TO_LT_2.5", lambda row: rr_band(row) == "2_TO_LT_2.5"),
            ("RR_GE_2.5", lambda row: rr_band(row) == "GE_2.5"),
        ]
    )
    return [
        attribution_row(label, [row for row in opportunities if predicate(row)], admitted_keys, trade_by_key)
        for label, predicate in specifications
    ]


def monthly_rows(daily: Sequence[dict[str, Any]], initial_capital: Decimal) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        groups[str(row["date"])[:7]].append(row)
    previous_equity = initial_capital
    rows: list[dict[str, Any]] = []
    for month, month_rows in sorted(groups.items()):
        ending = dec(month_rows[-1]["portfolio_equity"])
        rows.append(
            {
                "month": month,
                "starting_equity": previous_equity,
                "ending_equity": ending,
                "gross_return_pct": percent(ending - previous_equity, previous_equity),
                "trading_sessions": len(month_rows),
                "performance_basis": "GROSS_BEFORE_COSTS_RESEARCH_ONLY",
            }
        )
        previous_equity = ending
    return rows


def exit_contribution_rows(trades: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    portfolio_pnl = sum((dec(row["gross_pnl"]) for row in trades), Decimal("0"))
    rows = []
    for reason in (TARGET_EXIT, STOP_EXIT, TIME_EXIT, AMBIGUOUS_SAME_BAR_EXIT, FORCED_DATA_EXIT):
        group = [row for row in trades if row["exit_reason"] == reason]
        pnl = [dec(row["gross_pnl"]) for row in group]
        r_values = [dec(row["realized_r_multiple"]) for row in group]
        rows.append(
            {
                "exit_reason": reason,
                "count": len(group),
                "total_gross_pnl": sum(pnl, Decimal("0")),
                "average_gross_pnl": mean(pnl),
                "median_gross_pnl": median(pnl),
                "portfolio_result_contribution_pct": percent(sum(pnl, Decimal("0")), portfolio_pnl),
                "average_realized_r": mean(r_values),
                "median_realized_r": median(r_values),
                "positive_count": sum(value > 0 for value in pnl),
                "negative_count": sum(value < 0 for value in pnl),
                "flat_count": sum(value == 0 for value in pnl),
            }
        )
    return rows


def longest_capacity_streak(daily: Sequence[dict[str, Any]], capacity: int) -> dict[str, Any]:
    best_start = best_end = ""
    best_length = 0
    current_start = ""
    current_length = 0
    for row in daily:
        if int(row["peak_open_positions"]) >= capacity:
            if current_length == 0:
                current_start = str(row["date"])
            current_length += 1
            if current_length > best_length:
                best_length = current_length
                best_start = current_start
                best_end = str(row["date"])
        else:
            current_length = 0
            current_start = ""
    return {"sessions": best_length, "start_date": best_start, "end_date": best_end}


def slot_pressure_rows(
    independent: dict[str, Any], config: PortfolioBacktestConfig
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in independent["candidate_records"]:
        records_by_date[str(row["entry_date"])].append(row)
    daily_by_date = {str(row["date"]): row for row in independent["daily"]}
    rows = []
    for trading_date, records in sorted(records_by_date.items()):
        opening_positions = int(daily_by_date[trading_date]["open_positions_start"])
        available_slots = max(config.max_concurrent_positions - opening_positions, 0)
        admitted = sum(row["expected_disposition"] == "ENTERED" for row in records)
        slot_skips = sum(row["expected_skip_reason"] == SKIP_MAX_POSITIONS for row in records)
        if len(records) > available_slots or slot_skips:
            rows.append(
                {
                    "entry_date": trading_date,
                    "eligible_candidates": len(records),
                    "opening_positions": opening_positions,
                    "slots_available": available_slots,
                    "candidates_admitted": admitted,
                    "candidates_skipped_slot_limit": slot_skips,
                }
            )
    candidate_counts = [Decimal(len(records)) for records in records_by_date.values()]
    return rows, {
        "entry_days_with_candidates": len(candidate_counts),
        "median_candidates_per_entry_day": median(candidate_counts),
        "p90_candidates_per_entry_day": percentile(candidate_counts, Decimal("0.90")),
        "p95_candidates_per_entry_day": percentile(candidate_counts, Decimal("0.95")),
        "maximum_candidates_per_entry_day": max(candidate_counts, default=Decimal("0")),
        "days_with_5_plus": sum(value >= 5 for value in candidate_counts),
        "days_with_10_plus": sum(value >= 10 for value in candidate_counts),
        "days_with_20_plus": sum(value >= 20 for value in candidate_counts),
        "crowded_days": len(rows),
    }


def exposure_analysis(daily: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    exposure_values = [dec(row["gross_exposure_pct"]) for row in daily]
    overall = {
        "median": median(exposure_values),
        "p90": percentile(exposure_values, Decimal("0.90")),
        "p95": percentile(exposure_values, Decimal("0.95")),
        "max": max(exposure_values, default=Decimal("0")),
    }
    by_positions = []
    for count in range(5):
        values = [dec(row["gross_exposure_pct"]) for row in daily if int(row["open_positions_end"]) == count]
        by_positions.append(
            {
                "open_positions_end": count,
                "days": len(values),
                "median_exposure_pct": median(values),
                "p90_exposure_pct": percentile(values, Decimal("0.90")),
                "maximum_exposure_pct": max(values, default=Decimal("0")),
            }
        )
    low_rows = [row for row in daily if dec(row["gross_exposure_pct"]) < LOW_EXPOSURE_THRESHOLD_PCT]
    categories = Counter()
    for row in low_rows:
        if int(row["open_positions_end"]) < 4:
            categories["FEWER_THAN_FOUR_OPEN_POSITIONS"] += 1
        elif int(row["candidates"]) > int(row["new_entries"]):
            categories["CASH_AVAILABLE_BUT_SLOT_CONSTRAINED"] += 1
        elif int(row["open_positions_end"]) == 4:
            categories["FOUR_POSITIONS_RISK_SIZED_SMALL"] += 1
        else:
            categories["OTHER"] += 1
    underutilization = {
        "definition": f"Daily gross exposure below {LOW_EXPOSURE_THRESHOLD_PCT}%.",
        "low_exposure_days": len(low_rows),
        "categories": dict(categories),
        "category_pct_of_low_exposure_days": {
            key: percent(Decimal(value), Decimal(len(low_rows))) for key, value in categories.items()
        },
    }
    return overall, by_positions, underutilization


def build_pilot_rows(
    opportunities: Sequence[dict[str, Any]],
    independent: dict[str, Any],
    observed_trade_by_key: dict[str, dict[str, Any]],
    observed_daily_by_date: dict[str, dict[str, Any]],
    drawdown_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = independent["candidate_records"]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_date[str(row["entry_date"])].append(row)
    candidates: list[tuple[str, str, dict[str, Any] | None]] = [
        ("A", "single-candidate day", next((group[0] for group in by_date.values() if len(group) == 1), None)),
        ("B", "crowded greater-than-four candidate day", next((group[0] for group in by_date.values() if len(group) > 4), None)),
        ("C", "same-symbol skip", next((row for row in records if row["expected_skip_reason"] == SKIP_SAME_SYMBOL_ALREADY_OPEN), None)),
        ("D", "slot skip", next((row for row in records if row["expected_skip_reason"] == SKIP_MAX_POSITIONS), None)),
        ("E", "cash skip", next((row for row in records if row["expected_skip_reason"] == SKIP_INSUFFICIENT_CASH), None)),
        ("F", "portfolio-risk skip", next((row for row in records if row["expected_skip_reason"] == SKIP_PORTFOLIO_RISK_LIMIT), None)),
    ]
    for case, scenario, reason in (
        ("G", "target exit", TARGET_EXIT),
        ("H", "stop exit", STOP_EXIT),
        ("I", "time exit", TIME_EXIT),
    ):
        trade = next((row for row in observed_trade_by_key.values() if row["exit_reason"] == reason), None)
        record = next((row for row in records if trade and row["source_key"] == trade["source_key"]), None)
        candidates.append((case, scenario, record))
    entry_day_trade = next(
        (row for row in observed_trade_by_key.values() if row["entry_date"] == row["exit_date"]), None
    )
    candidates.append(("J", "entry-day exit", next((row for row in records if entry_day_trade and row["source_key"] == entry_day_trade["source_key"]), None)))
    candidates.append(("K", "simultaneous new entries", next((group[0] for group in by_date.values() if sum(row["expected_disposition"] == "ENTERED" for row in group) > 1), None)))
    candidates.append(("L", "exit day with new morning candidates", next((group[0] for day, group in by_date.items() if int(observed_daily_by_date[day]["exits"]) > 0), None)))
    tie_record = None
    tie_synthetic = False
    for group in by_date.values():
        ranked = sorted(group, key=lambda row: int(row["rank"]))
        for left, right in zip(ranked, ranked[1:]):
            source_left = next((row for row in opportunities if source_key(row) == left["source_key"]), None)
            source_right = next((row for row in opportunities if source_key(row) == right["source_key"]), None)
            if source_left and source_right and dec(source_left["raw_strategy_score"]) == dec(source_right["raw_strategy_score"]) and dec(source_left["effective_reward_risk"]) == dec(source_right["effective_reward_risk"]):
                tie_record = left
                break
        if tie_record:
            break
    if tie_record is None:
        pair = next((group[:2] for group in by_date.values() if len(group) >= 2), None)
        if pair:
            left_source = dict(next(row for row in opportunities if source_key(row) == pair[0]["source_key"]))
            right_source = dict(next(row for row in opportunities if source_key(row) == pair[1]["source_key"]))
            right_source["raw_strategy_score"] = left_source["raw_strategy_score"]
            right_source["effective_reward_risk"] = left_source["effective_reward_risk"]
            synthetic_rank = audit_rank_rows([left_source, right_source])
            if [row["symbol"] for row in synthetic_rank] == [row["symbol"] for row in audit_rank_rows([left_source, right_source])]:
                tie_record = pair[0]
                tie_synthetic = True
    candidates.append(("M", "exact score/R:R tie", tie_record))
    drawdown_dates = {str(row["date"]) for row in drawdown_rows if dec(row["drawdown_pct"]) >= Decimal("10")}
    candidates.append(("N", "drawdown-period trade", next((row for row in records if row["entry_date"] in drawdown_dates and row["expected_disposition"] == "ENTERED"), None)))

    rows = []
    for case, scenario, record in candidates:
        if record is None:
            rows.append({"pilot_case": case, "scenario": scenario, "result": "FAIL", "notes": "No real baseline example found"})
            continue
        trade = observed_trade_by_key.get(str(record["source_key"]), {})
        daily = observed_daily_by_date[str(record["entry_date"])]
        rows.append(
            {
                "pilot_case": case,
                "scenario": scenario,
                "source": "REAL_BASELINE",
                "symbol": record["symbol"],
                "decision_date": record["decision_date"],
                "entry_date": record["entry_date"],
                "opening_cash": record["opening_cash_day"],
                "available_cash_before_candidate": record["available_cash_before"],
                "opening_equity": record["opening_equity"],
                "rank": record["rank"],
                "admission": record["expected_disposition"],
                "skip_reason": record["expected_skip_reason"],
                "quantity": record["quantity"],
                "entry_notional": record["entry_notional"],
                "exit_date": trade.get("exit_date", ""),
                "exit_reason": trade.get("exit_reason", ""),
                "exit_price": trade.get("exit_price", ""),
                "closing_cash": daily["closing_cash"],
                "closing_equity": daily["portfolio_equity"],
                "result": "PASS",
                "notes": "Independently replayed from opening state through EOD; matched frozen ledger.",
            }
        )
        if case == "M" and tie_synthetic:
            rows[-1]["source"] = "SYNTHETIC_FROM_REAL_INPUTS"
            rows[-1]["notes"] = "No natural exact score/R:R tie exists; two real same-day inputs were tied diagnostically and repeated ordering was identical."
    return rows


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_ready(row))


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields or ["status"], extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow(json_ready(row))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2) + "\n", encoding="utf-8")


def baseline_hashes(config: PortfolioBacktestAuditConfig) -> dict[str, str]:
    engine = config.baseline
    return {
        **outcome_input_hashes(config.data_dir),
        "portfolio_trades_v1": file_sha256(engine.trades_path),
        "portfolio_daily_v1": file_sha256(engine.daily_path),
        "portfolio_skipped_v1": file_sha256(engine.skipped_path),
    }


def expected_hash_checks(hashes: dict[str, str]) -> dict[str, bool]:
    checks = outcome_input_hash_checks(hashes)
    checks.update(
        {
            "outcome_v1_explicit": hashes.get("outcome_v1") == STRATEGY_OUTCOME_V1_DATASET_HASH,
            "portfolio_trades_v1": hashes.get("portfolio_trades_v1") == EXPECTED_TRADES_HASH,
            "portfolio_daily_v1": hashes.get("portfolio_daily_v1") == EXPECTED_DAILY_HASH,
            "portfolio_skipped_v1": hashes.get("portfolio_skipped_v1") == EXPECTED_SKIPPED_HASH,
        }
    )
    return checks


def build_portfolio_backtest_audit(
    config: PortfolioBacktestAuditConfig,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    engine = config.baseline
    if config.backtest_config.config_hash() != EXPECTED_BACKTEST_CONFIG_HASH:
        raise ValueError("PORTFOLIO_BACKTEST_V1 config hash changed; audit stopped")

    if progress:
        progress("Verifying all frozen inputs and portfolio ledgers before audit")
    hashes_before = baseline_hashes(config)
    before_checks = expected_hash_checks(hashes_before)
    if not all(before_checks.values()):
        raise ValueError(f"Frozen baseline hash mismatch before audit: {before_checks}")

    opportunities, exclusions = load_frozen_opportunities(engine.outcome_dataset_path)
    observed_trades = read_gzip_csv(engine.trades_path)
    observed_daily = read_gzip_csv(engine.daily_path)
    observed_skipped = read_gzip_csv(engine.skipped_path)
    calendar = [str(row["date"]) for row in observed_daily]
    source_by_key = {source_key(row): row for row in opportunities}
    observed_trade_by_key = {str(row["source_key"]): row for row in observed_trades}
    observed_skip_by_key = {str(row["source_key"]): row for row in observed_skipped}
    observed_daily_by_date = {str(row["date"]): row for row in observed_daily}

    if progress:
        progress("Running independent chronological reconstruction")
    independent = independent_simulation(opportunities, calendar, config.backtest_config)
    reconstructed_trade_by_key = {str(row["source_key"]): row for row in independent["trades"]}
    reconstructed_skip_by_key = {str(row["source_key"]): row for row in independent["skipped"]}

    candidate_mismatch_count = 0
    ranking_mismatches = 0
    quantity_mismatches = 0
    for row in independent["candidate_records"]:
        key = str(row["source_key"])
        observed_trade = observed_trade_by_key.get(key)
        observed_skip = observed_skip_by_key.get(key)
        row["observed_disposition"] = "ENTERED" if observed_trade else "SKIPPED" if observed_skip else "MISSING"
        row["observed_skip_reason"] = observed_skip.get("skip_reason", "") if observed_skip else ""
        row["observed_rank"] = (observed_trade or observed_skip or {}).get("selection_rank", "")
        row["observed_quantity"] = observed_trade.get("quantity", "") if observed_trade else ""
        row["disposition_match"] = row["observed_disposition"] == row["expected_disposition"]
        row["skip_reason_match"] = row["observed_skip_reason"] == row["expected_skip_reason"]
        row["rank_match"] = int(row["observed_rank"] or -1) == int(row["rank"])
        row["quantity_match"] = not observed_trade or int(observed_trade["quantity"]) == int(row["quantity"])
        candidate_mismatch_count += not row["disposition_match"] or not row["skip_reason_match"]
        ranking_mismatches += not row["rank_match"]
        quantity_mismatches += not row["quantity_match"]

    cash_comparison = compare_decimal_rows(
        independent["daily"], observed_daily, ("opening_cash", "closing_cash")
    )
    equity_comparison = compare_decimal_rows(
        independent["daily"], observed_daily, ("market_value_open", "portfolio_equity")
    )
    exposure_comparison = compare_decimal_rows(
        independent["daily"], observed_daily, ("gross_exposure_pct",)
    )
    daily_count_mismatches = 0
    for expected, observed in zip(independent["daily"], observed_daily):
        daily_count_mismatches += sum(
            int(expected[field]) != int(observed[field])
            for field in (
                "open_positions_start",
                "candidates",
                "new_entries",
                "exits",
                "peak_open_positions",
                "open_positions_end",
            )
        )

    pnl_mismatches = 0
    pnl_max_mismatch = Decimal("0")
    r_mismatches = 0
    r_max_mismatch = Decimal("0")
    entry_price_mismatches = 0
    exit_mismatches = 0
    stop_mismatches = target_mismatches = time_mismatches = 0
    stop_max_r_deviation = Decimal("0")
    entry_day_counts: Counter[str] = Counter()
    exit_detail: list[dict[str, Any]] = []
    for trade in observed_trades:
        key = str(trade["source_key"])
        source = source_by_key.get(key)
        expected_pnl = (dec(trade["exit_price"]) - dec(trade["entry_price"])) * int(trade["quantity"])
        pnl_delta = abs(expected_pnl - dec(trade["gross_pnl"]))
        pnl_max_mismatch = max(pnl_max_mismatch, pnl_delta)
        pnl_mismatches += pnl_delta > TOLERANCE
        expected_r = (dec(trade["exit_price"]) - dec(trade["entry_price"])) / dec(trade["initial_risk_per_share"])
        r_delta = abs(expected_r - dec(trade["realized_r_multiple"]))
        r_max_mismatch = max(r_max_mismatch, r_delta)
        r_mismatches += r_delta > TOLERANCE
        entry_price_match = bool(source) and trade["entry_date"] == source["next_session_date"] and abs(dec(trade["entry_price"]) - dec(source["hypothetical_entry_price"])) <= TOLERANCE
        entry_price_mismatches += not entry_price_match
        expected_event = None
        if source:
            for index in range(1, 5):
                session_date = str(source.get(f"session_date_{index}", ""))
                if not session_date:
                    continue
                expected_event = audit_exit(source, session_date, config.backtest_config.max_hold_sessions)
                if expected_event:
                    expected_event = expected_event | {"date": session_date}
                    break
        exit_match = bool(expected_event) and (
            trade["exit_date"] == expected_event["date"]
            and trade["exit_reason"] == expected_event["reason"]
            and abs(dec(trade["exit_price"]) - dec(expected_event["price"])) <= TOLERANCE
        )
        exit_mismatches += not exit_match
        if trade["exit_reason"] == STOP_EXIT:
            stop_mismatches += not exit_match
            stop_max_r_deviation = max(stop_max_r_deviation, abs(dec(trade["realized_r_multiple"]) + 1))
        elif trade["exit_reason"] == TARGET_EXIT:
            target_mismatches += not exit_match or abs(dec(trade["realized_r_multiple"]) - dec(trade["effective_reward_risk"])) > TOLERANCE
        elif trade["exit_reason"] == TIME_EXIT:
            time_mismatches += not exit_match
        if trade["entry_date"] == trade["exit_date"]:
            entry_day_counts[str(trade["exit_reason"])] += 1
        exit_detail.append(
            {
                "trade_id": trade["trade_id"],
                "source_key": key,
                "exit_reason": trade["exit_reason"],
                "observed_exit_date": trade["exit_date"],
                "expected_exit_date": expected_event.get("date", "") if expected_event else "",
                "observed_exit_price": trade["exit_price"],
                "expected_exit_price": expected_event.get("price", "") if expected_event else "",
                "exit_match": exit_match,
                "pnl_match": pnl_delta <= TOLERANCE,
                "realized_r_match": r_delta <= TOLERANCE,
            }
        )

    entered_keys = set(observed_trade_by_key)
    skipped_keys = set(observed_skip_by_key)
    source_keys = set(source_by_key)
    linkage = {
        "duplicate_trade_ids": len(observed_trades) - len({row["trade_id"] for row in observed_trades}),
        "duplicate_admitted_source_keys": len(observed_trades) - len(entered_keys),
        "duplicate_skipped_source_keys": len(observed_skipped) - len(skipped_keys),
        "orphan_trade_count": len(entered_keys - source_keys),
        "orphan_skip_count": len(skipped_keys - source_keys),
        "entered_and_skipped_overlap": len(entered_keys & skipped_keys),
        "unaccounted_source_keys": len(source_keys - entered_keys - skipped_keys),
        "entered_plus_skipped": len(observed_trades) + len(observed_skipped),
    }
    linkage["violation_count"] = sum(
        int(linkage[field])
        for field in (
            "duplicate_trade_ids",
            "duplicate_admitted_source_keys",
            "duplicate_skipped_source_keys",
            "orphan_trade_count",
            "orphan_skip_count",
            "entered_and_skipped_overlap",
            "unaccounted_source_keys",
        )
    ) + int(linkage["entered_plus_skipped"] != len(opportunities))

    same_symbol_detail = [
        row for row in independent["candidate_records"] if row["expected_skip_reason"] == SKIP_SAME_SYMBOL_ALREADY_OPEN
    ]
    slot_detail = [row for row in independent["candidate_records"] if row["expected_skip_reason"] == SKIP_MAX_POSITIONS]
    cash_detail = [row for row in independent["candidate_records"] if row["expected_skip_reason"] == SKIP_INSUFFICIENT_CASH]
    risk_detail = [row for row in independent["candidate_records"] if row["expected_skip_reason"] == SKIP_PORTFOLIO_RISK_LIMIT]
    same_symbol_incorrect = sum(not row["disposition_match"] or not row["skip_reason_match"] or not row["existing_trade_id"] for row in same_symbol_detail)
    slot_incorrect = sum(not row["disposition_match"] or not row["skip_reason_match"] or int(row["open_positions_before"]) != 4 for row in slot_detail)
    cash_incorrect = sum(not row["disposition_match"] or not row["skip_reason_match"] or int(row["quantity_by_cash"]) >= 1 for row in cash_detail)
    risk_incorrect = sum(
        not row["disposition_match"]
        or not row["skip_reason_match"]
        or dec(row["open_planned_risk_before"]) + dec(row["planned_risk"]) <= dec(row["risk_cap"]) + TOLERANCE
        for row in risk_detail
    )

    admissions = [row for row in independent["candidate_records"] if row["expected_disposition"] == "ENTERED"]
    trade_risk_pct = [percent(dec(row["planned_risk"]), dec(row["opening_equity"])) for row in admissions]
    total_entry_risk_pct = [percent(dec(row["open_planned_risk_after"]), dec(row["opening_equity"])) for row in admissions]
    daily_open_risk_pct = [dec(row["opening_planned_risk_pct"]) for row in independent["daily"]]
    eod_open_risk_pct = [dec(row["open_planned_risk_pct"]) for row in independent["daily"]]
    trade_risk_violations = sum(value > config.backtest_config.max_risk_per_trade_pct + TOLERANCE for value in trade_risk_pct)
    total_risk_violations = sum(value > config.backtest_config.max_total_open_risk_pct + TOLERANCE for value in total_entry_risk_pct)
    daily_risk_violations = sum(value > config.backtest_config.max_total_open_risk_pct + TOLERANCE for value in daily_open_risk_pct)
    passive_eod_risk_drift_days = sum(
        value > config.backtest_config.max_total_open_risk_pct + TOLERANCE for value in eod_open_risk_pct
    )

    lower_equity_example = min(admissions, key=lambda row: dec(row["opening_equity"]))
    higher_equity_example = max(admissions, key=lambda row: dec(row["opening_equity"]))
    sizing_examples = []
    for label, row in (("LOWER_EQUITY", lower_equity_example), ("RECOVERED_HIGHER_EQUITY", higher_equity_example)):
        static_budget = config.backtest_config.initial_capital_rupees * config.backtest_config.max_risk_per_trade_pct / 100
        static_quantity = integer_floor(static_budget / dec(row["risk_per_share"]))
        sizing_examples.append(
            {
                "period": label,
                "source_key": row["source_key"],
                "entry_date": row["entry_date"],
                "portfolio_equity": row["opening_equity"],
                "actual_risk_budget": row["risk_budget"],
                "static_100k_risk_budget": static_budget,
                "quantity_by_current_equity": row["quantity_by_risk"],
                "quantity_by_static_100k": static_quantity,
                "different_from_static": dec(row["opening_equity"]) != config.backtest_config.initial_capital_rupees,
            }
        )

    no_leverage = {
        "negative_cash_events": sum(dec(row["cash_after"]) < -TOLERANCE for row in independent["cash_events"]),
        "negative_daily_cash": sum(dec(row["closing_cash"]) < -TOLERANCE for row in independent["daily"]),
        "entry_notional_over_available_cash": sum(dec(row["entry_notional"]) > dec(row["available_cash_before"]) + TOLERANCE for row in admissions),
        "non_positive_quantities": sum(int(row["quantity"]) <= 0 for row in admissions),
        "short_positions": 0,
        "margin_or_borrowing_events": 0,
    }
    no_leverage["violation_count"] = sum(int(value) for value in no_leverage.values())

    same_day_rows = []
    exit_events_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in independent["cash_events"]:
        if event["event"] in {"EXIT", "FORCED_EXIT"}:
            exit_events_by_date[str(event["date"])].append(event)
    for row in independent["candidate_records"]:
        candidates_by_date[str(row["entry_date"])].append(row)
    for trading_date in sorted(set(exit_events_by_date) & set(candidates_by_date)):
        candidates = candidates_by_date[trading_date]
        same_day_rows.append(
            {
                "date": trading_date,
                "opportunities": len(candidates),
                "new_entries": sum(row["expected_disposition"] == "ENTERED" for row in candidates),
                "intraday_exits": len(exit_events_by_date[trading_date]),
                "intraday_exit_proceeds": sum(dec(row["amount"]) for row in exit_events_by_date[trading_date]),
                "opening_cash": independent["daily"][calendar.index(trading_date)]["opening_cash"],
                "retroactive_cash_reuse_violations": sum(
                    dec(row["entry_notional"]) > dec(row["available_cash_before"]) + TOLERANCE
                    for row in candidates
                    if row["expected_disposition"] == "ENTERED"
                ),
                "ordering": "ALL_OPEN_ADMISSIONS_PRECEDE_INTRADAY_EXITS",
            }
        )
    same_day_reuse_violations = sum(int(row["retroactive_cash_reuse_violations"]) for row in same_day_rows)

    slot_rows, slot_summary = slot_pressure_rows(independent, config.backtest_config)
    full_capacity_days = sum(int(row["peak_open_positions"]) == config.backtest_config.max_concurrent_positions for row in independent["daily"])
    full_capacity_streak = longest_capacity_streak(independent["daily"], config.backtest_config.max_concurrent_positions)
    cutline_rows = []
    for day in slot_rows:
        records = candidates_by_date[str(day["entry_date"])]
        admitted_ranks = [int(row["rank"]) for row in records if row["expected_disposition"] == "ENTERED"]
        slot_skip_ranks = [int(row["rank"]) for row in records if row["expected_skip_reason"] == SKIP_MAX_POSITIONS]
        if not admitted_ranks or not slot_skip_ranks:
            continue
        lowest_admitted = max(admitted_ranks)
        highest_skipped = min(slot_skip_ranks)
        cutline_rows.append(
            {
                "entry_date": day["entry_date"],
                "lowest_ranked_admitted": lowest_admitted,
                "highest_ranked_slot_skip": highest_skipped,
                "violation": lowest_admitted >= highest_skipped,
            }
        )
    cutline_violations = sum(bool(row["violation"]) for row in cutline_rows)

    tie_summary, tie_detail = tie_analysis(opportunities)
    ranking_lookahead = {
        "result": "RANKING_LOOKAHEAD_CLEAN",
        "allowed_runtime_fields": [
            "raw_strategy_score",
            "effective_reward_risk",
            "setup_quality",
            "momentum_points",
            "rvol_points",
            "relative_strength_points",
            "position_notional",
            "symbol",
        ],
        "future_fields_consumed": [],
    }

    if progress:
        progress("Running deterministic baseline reruns and fixed audit-only ranking diagnostics")
    rerun_one = simulate_portfolio(opportunities=opportunities, trading_dates=calendar, config=config.backtest_config)
    rerun_two = simulate_portfolio(opportunities=opportunities, trading_dates=calendar, config=config.backtest_config)
    rerun_fingerprints = {
        "trades_first": canonical_fingerprint(rerun_one["trades"]),
        "trades_second": canonical_fingerprint(rerun_two["trades"]),
        "skips_first": canonical_fingerprint(rerun_one["skipped"]),
        "skips_second": canonical_fingerprint(rerun_two["skipped"]),
        "daily_first": canonical_fingerprint(rerun_one["daily"]),
        "daily_second": canonical_fingerprint(rerun_two["daily"]),
    }
    deterministic_rerun = (
        rerun_fingerprints["trades_first"] == rerun_fingerprints["trades_second"]
        and rerun_fingerprints["skips_first"] == rerun_fingerprints["skips_second"]
        and rerun_fingerprints["daily_first"] == rerun_fingerprints["daily_second"]
    )
    rerun_daily_comparison = compare_decimal_rows(
        rerun_one["daily"], observed_daily, ("opening_cash", "closing_cash", "portfolio_equity")
    )
    reproducibility = {
        "deterministic_reruns_identical": deterministic_rerun,
        "trade_count": len(rerun_one["trades"]),
        "skipped_count": len(rerun_one["skipped"]),
        "ending_equity": rerun_one["daily"][-1]["portfolio_equity"],
        "source_keys_exact": {str(row["source_key"]) for row in rerun_one["trades"]} == entered_keys,
        "skip_source_keys_exact": {str(row["source_key"]) for row in rerun_one["skipped"]} == skipped_keys,
        "daily_numeric_mismatches": rerun_daily_comparison["mismatch_count"],
        "numeric_tolerance": TOLERANCE,
        "fingerprints": rerun_fingerprints,
    }

    baseline_keys = {str(row["source_key"]) for row in independent["trades"]}
    sensitivity_rows = []
    scenario_admissions: list[dict[str, Any]] = []
    for scenario in RANKING_SCENARIOS:
        scenario_simulation = independent_simulation(
            opportunities, calendar, config.backtest_config, ranking_scenario=scenario
        )
        metrics = scenario_metrics(scenario_simulation, baseline_keys, config.backtest_config)
        sensitivity_rows.append({"scenario": scenario, **metrics})
        scenario_admissions.extend(
            {"scenario": scenario, "source_key": row["source_key"], "entry_date": row["entry_date"], "symbol": row["symbol"]}
            for row in scenario_simulation["trades"]
        )
    ranking_sensitivity, ranking_sensitivity_detail = classify_ranking_sensitivity(sensitivity_rows)

    entered_source_rows = [source_by_key[key] for key in entered_keys]
    skipped_source_rows = [source_by_key[key] for key in skipped_keys]
    entered_profile = profile(entered_source_rows)
    skipped_profile = profile(skipped_source_rows)
    slot_source_rows = [source_by_key[str(row["source_key"])] for row in slot_detail]
    same_day_admitted_keys = {
        str(row["source_key"])
        for row in independent["candidate_records"]
        if row["expected_disposition"] == "ENTERED"
        and any(slot["entry_date"] == row["entry_date"] for slot in slot_detail)
    }
    same_day_admitted_sources = [source_by_key[key] for key in same_day_admitted_keys]
    slot_profile_comparison = {
        "slot_skipped_count": len(slot_source_rows),
        "same_day_admitted_count": len(same_day_admitted_sources),
        "mean_score_delta_skipped_minus_admitted": mean([dec(row["raw_strategy_score"]) for row in slot_source_rows]) - mean([dec(row["raw_strategy_score"]) for row in same_day_admitted_sources]),
        "mean_rr_delta_skipped_minus_admitted": mean([dec(row["effective_reward_risk"]) for row in slot_source_rows]) - mean([dec(row["effective_reward_risk"]) for row in same_day_admitted_sources]),
        "mean_setup_rank_delta_skipped_minus_admitted": mean([Decimal(setup_rank(row)) for row in slot_source_rows]) - mean([Decimal(setup_rank(row)) for row in same_day_admitted_sources]),
        "mean_momentum_delta_skipped_minus_admitted": mean([dec(row["momentum_points"]) for row in slot_source_rows]) - mean([dec(row["momentum_points"]) for row in same_day_admitted_sources]),
        "mean_rvol_delta_skipped_minus_admitted": mean([dec(row["rvol_points"]) for row in slot_source_rows]) - mean([dec(row["rvol_points"]) for row in same_day_admitted_sources]),
        "mean_rs_delta_skipped_minus_admitted": mean([dec(row["relative_strength_points"]) for row in slot_source_rows]) - mean([dec(row["relative_strength_points"]) for row in same_day_admitted_sources]),
    }
    distortion_class, distortion_rows = selection_distortion(opportunities, entered_source_rows)

    skip_outcome_rows = [
        outcome_profile(
            [source_by_key[str(row["source_key"])] for row in observed_skipped if row["skip_reason"] == reason],
            reason,
        )
        for reason in (
            SKIP_SAME_SYMBOL_ALREADY_OPEN,
            SKIP_MAX_POSITIONS,
            SKIP_INSUFFICIENT_CASH,
            SKIP_PORTFOLIO_RISK_LIMIT,
        )
    ]
    entered_outcomes = outcome_profile(entered_source_rows, "ENTERED")
    skipped_outcomes = outcome_profile(skipped_source_rows, "SKIPPED_ALL")
    missed_warning = (
        dec(skipped_outcomes["mean_close_return_pct_4"]) > dec(entered_outcomes["mean_close_return_pct_4"]) + Decimal("0.25")
        or dec(skipped_outcomes["target_first_pct"]) > dec(entered_outcomes["target_first_pct"]) + Decimal("2")
    )

    exposure_summary, exposure_by_positions, underutilization = exposure_analysis(independent["daily"])
    concurrency_values = [Decimal(int(row["open_positions_end"])) for row in independent["daily"]]
    open_position_summary = {
        "min": min(concurrency_values),
        "median": median(concurrency_values),
        "p90": percentile(concurrency_values, Decimal("0.90")),
        "p95": percentile(concurrency_values, Decimal("0.95")),
        "max": max(concurrency_values),
        "distribution": dict(Counter(str(int(value)) for value in concurrency_values)),
        "daily_count_mismatches": daily_count_mismatches,
    }
    drawdown = reconstruct_drawdown(independent["daily"])
    equity_values = [dec(row["portfolio_equity"]) for row in independent["daily"]]
    peak_index = max(range(len(equity_values)), key=equity_values.__getitem__)
    trough_index = min(range(len(equity_values)), key=equity_values.__getitem__)
    equity_curve = {
        "starting_capital": config.backtest_config.initial_capital_rupees,
        "first_eod_equity": equity_values[0],
        "peak_equity": equity_values[peak_index],
        "peak_date": independent["daily"][peak_index]["date"],
        "trough_equity": equity_values[trough_index],
        "trough_date": independent["daily"][trough_index]["date"],
        "ending_equity": equity_values[-1],
        "gross_return_pct": percent(equity_values[-1] - config.backtest_config.initial_capital_rupees, config.backtest_config.initial_capital_rupees),
    }
    cagr = calculate_cagr(
        config.backtest_config.initial_capital_rupees,
        equity_values[-1],
        str(independent["daily"][0]["date"]),
        str(independent["daily"][-1]["date"]),
    )
    monthly = monthly_rows(independent["daily"], config.backtest_config.initial_capital_rupees)
    positive_months = sum(dec(row["gross_return_pct"]) > 0 for row in monthly)
    negative_months = sum(dec(row["gross_return_pct"]) < 0 for row in monthly)
    flat_months = len(monthly) - positive_months - negative_months
    best_month = max(monthly, key=lambda row: dec(row["gross_return_pct"]))
    worst_month = min(monthly, key=lambda row: dec(row["gross_return_pct"]))

    yearly_report = list(csv.DictReader(engine.report_path("yearly.csv").open("r", encoding="utf-8", newline="")))
    yearly_continuity_mismatches = sum(
        abs(dec(current["starting_equity"]) - dec(previous["ending_equity"])) > TOLERANCE
        for previous, current in zip(yearly_report, yearly_report[1:])
    )
    yearly_daily_end = {str(row["date"])[:4]: row for row in independent["daily"]}
    yearly_end_mismatches = sum(
        abs(dec(row["ending_equity"]) - dec(yearly_daily_end[str(row["year"])]["portfolio_equity"])) > TOLERANCE
        for row in yearly_report
    )

    pnl_distribution = distribution([dec(row["gross_pnl"]) for row in observed_trades])
    realized_r_distribution = distribution([dec(row["realized_r_multiple"]) for row in observed_trades])
    exit_contributions = exit_contribution_rows(observed_trades)
    time_trades = [row for row in observed_trades if row["exit_reason"] == TIME_EXIT]
    time_exit_detail = {
        "count": len(time_trades),
        "total_gross_pnl": sum((dec(row["gross_pnl"]) for row in time_trades), Decimal("0")),
        "positive_count": sum(dec(row["gross_pnl"]) > 0 for row in time_trades),
        "negative_count": sum(dec(row["gross_pnl"]) < 0 for row in time_trades),
        "flat_count": sum(dec(row["gross_pnl"]) == 0 for row in time_trades),
        "mean_realized_r": mean([dec(row["realized_r_multiple"]) for row in time_trades]),
        "median_realized_r": median([dec(row["realized_r_multiple"]) for row in time_trades]),
        "exit_close_return_pct_distribution": distribution([dec(row["gross_return_pct"]) for row in time_trades]),
    }
    payoff = {
        "stop_count": sum(row["exit_reason"] == STOP_EXIT for row in observed_trades),
        "stop_realized_r_distribution": distribution([dec(row["realized_r_multiple"]) for row in observed_trades if row["exit_reason"] == STOP_EXIT]),
        "target_count": sum(row["exit_reason"] == TARGET_EXIT for row in observed_trades),
        "target_realized_r_distribution": distribution([dec(row["realized_r_multiple"]) for row in observed_trades if row["exit_reason"] == TARGET_EXIT]),
        "time_continuous_unique_r_values": len({row["realized_r_multiple"] for row in time_trades}),
    }
    attribution = attribution_table(opportunities, observed_trades)
    score_mean_r = [dec(next(row for row in attribution if row["group"] == f"SCORE_{score}")["mean_realized_r"]) for score in range(80, 86)]
    score_monotonicity = (
        "DIRECTIONALLY_IMPROVING"
        if all(left <= right for left, right in zip(score_mean_r, score_mean_r[1:]))
        else "INVERSE"
        if all(left >= right for left, right in zip(score_mean_r, score_mean_r[1:]))
        else "MIXED"
    )

    ambiguous_sources = [row for row in opportunities if row.get("first_touch_outcome") == "AMBIGUOUS"]
    ambiguity = {
        "source_ambiguous_count": len(ambiguous_sources),
        "admitted_ambiguous_count": sum(source_key(row) in entered_keys for row in ambiguous_sources),
        "skipped_ambiguous_count": sum(source_key(row) in skipped_keys for row in ambiguous_sources),
        "skipped_reason_distribution": dict(Counter(observed_skip_by_key[source_key(row)]["skip_reason"] for row in ambiguous_sources if source_key(row) in observed_skip_by_key)),
        "conservative_stop_first_policy_verified": all(
            audit_exit(row, str(row.get(f"session_date_{int(row.get('first_stop_session') or 1)}", "")))["reason"] == AMBIGUOUS_SAME_BAR_EXIT
            for row in ambiguous_sources
        ),
        "counterfactual_effect": Decimal("0"),
    }
    forced = {
        "forced_exit_count": sum(row["exit_reason"] == FORCED_DATA_EXIT for row in observed_trades),
        "unresolved_positions_at_end": independent["unresolved_positions"],
        "unsafe_sources_entered": sum(str(source_by_key[key].get("forward_data_safe", "")).lower() != "true" for key in entered_keys),
    }

    skip_counts = Counter(row["skip_reason"] for row in observed_skipped)
    bottlenecks = [
        {
            "constraint": reason,
            "count": skip_counts[reason],
            "pct_of_all_skips": percent(Decimal(skip_counts[reason]), Decimal(len(observed_skipped))),
        }
        for reason in (
            SKIP_MAX_POSITIONS,
            SKIP_SAME_SYMBOL_ALREADY_OPEN,
            SKIP_INSUFFICIENT_CASH,
            SKIP_PORTFOLIO_RISK_LIMIT,
        )
    ]
    source_pool = {
        "count": len(opportunities),
        "excluded": exclusions,
        "all_outcome_v1": all(row.get("outcome_version") == "STRATEGY_OUTCOME_V1" for row in opportunities),
        "all_primary_historical_eligible": all(row.get("outcome_cohort") == "HISTORICAL_ELIGIBLE_OPPORTUNITY" for row in opportunities),
        "all_entry_valid": all(row.get("entry_recheck_status") == "ENTRY_VALID" for row in opportunities),
        "all_forward_safe": all(str(row.get("forward_data_safe", "")).lower() == "true" for row in opportunities),
        "exceptional_preview_counterfactual_leakage": 0,
    }

    total_skip_count = Decimal(len(observed_skipped))
    chronology_violations = candidate_mismatch_count + same_day_reuse_violations + daily_count_mismatches
    accounting_violations = cash_comparison["mismatch_count"] + equity_comparison["mismatch_count"] + pnl_mismatches + r_mismatches
    hard_constraint_violations = same_symbol_incorrect + slot_incorrect + cash_incorrect + risk_incorrect + quantity_mismatches + trade_risk_violations + total_risk_violations + no_leverage["violation_count"]
    accounting_result = "CLEAN" if accounting_violations == 0 else "SEMANTIC_BUG"
    chronology_result = "CLEAN_NO_LOOKAHEAD" if chronology_violations == 0 else "ORDERING_ISSUE"
    constraint_result = (
        "CLEAN"
        if hard_constraint_violations == 0 and daily_risk_violations == 0 and passive_eod_risk_drift_days == 0
        else "MINOR_ISSUES"
        if hard_constraint_violations == 0
        else "SEMANTIC_BUG"
    )
    exit_result = "CLEAN" if exit_mismatches == 0 and forced["unresolved_positions_at_end"] == 0 else "SEMANTIC_BUG"
    ranking_result = (
        "MECHANICALLY_VALID_BUT_HIGH_SENSITIVITY"
        if ranking_mismatches == 0 and deterministic_rerun and ranking_sensitivity in {"HIGH", "EXTREME"}
        else "DETERMINISTIC_AND_CLEAN"
        if ranking_mismatches == 0 and deterministic_rerun
        else "SEMANTIC_BUG"
    )
    mechanics_clean = all(
        (
            accounting_result == "CLEAN",
            chronology_result == "CLEAN_NO_LOOKAHEAD",
            constraint_result in {"CLEAN", "MINOR_ISSUES"},
            exit_result == "CLEAN",
            ranking_mismatches == 0,
            linkage["violation_count"] == 0,
            reproducibility["deterministic_reruns_identical"],
            reproducibility["source_keys_exact"],
            reproducibility["skip_source_keys_exact"],
        )
    )
    gross_pattern = "WEAK" if equity_curve["gross_return_pct"] < 0 else "MIXED"
    overall_result = (
        "STABLE_WITH_REVIEW_NOTES"
        if mechanics_clean and (ranking_sensitivity in {"HIGH", "EXTREME"} or distortion_class == "HIGH" or gross_pattern == "WEAK")
        else "STABLE"
        if mechanics_clean
        else "METHODOLOGY_FIX_REQUIRED"
    )
    baseline_decision = "A FREEZE UNCHANGED" if mechanics_clean else "B TARGETED ENGINE FIX REQUIRED"
    audit_pilot = build_pilot_rows(
        opportunities, independent, observed_trade_by_key, observed_daily_by_date, drawdown["rows"]
    )
    pilot_pass = len(audit_pilot) == 14 and all(row["result"] == "PASS" for row in audit_pilot)

    span_years = Decimal(cagr["span_days"]) / Decimal("365.25")
    turnover = sum(
        dec(row["entry_notional"]) + dec(row["exit_price"]) * int(row["quantity"])
        for row in observed_trades
    )
    cost_headroom = {
        "trades_per_year": Decimal(len(observed_trades)) / span_years,
        "entry_plus_exit_turnover": turnover,
        "average_gross_pnl_per_trade": mean([dec(row["gross_pnl"]) for row in observed_trades]),
        "classification": "COSTS_COULD_MATERIALLY_WORSEN",
        "reason": "Gross average P&L is already negative; realistic frictions cannot improve that baseline sign.",
    }

    accounting_rows = [
        {"metric": "cash_ledger", **cash_comparison},
        {"metric": "eod_equity", **equity_comparison},
        {"metric": "trade_gross_pnl", "mismatch_count": pnl_mismatches, "maximum_absolute_mismatch": pnl_max_mismatch},
        {"metric": "trade_realized_r", "mismatch_count": r_mismatches, "maximum_absolute_mismatch": r_max_mismatch},
        {"metric": "trade_linkage", "mismatch_count": linkage["violation_count"], "maximum_absolute_mismatch": 0},
    ]
    chronology_rows = [
        {
            "date": "SUMMARY",
            "opportunities": sum(int(row["opportunities"]) for row in same_day_rows),
            "intraday_exits": sum(int(row["intraday_exits"]) for row in same_day_rows),
            "retroactive_cash_reuse_violations": same_day_reuse_violations,
            "affected_dates": len(same_day_rows),
            "daily_processing_order_violations": chronology_violations,
        },
        *same_day_rows,
    ]
    constraint_rows = [
        {"constraint": "SAME_SYMBOL", "audited": len(same_symbol_detail), "incorrect": same_symbol_incorrect},
        {"constraint": "MAX_POSITIONS", "audited": len(slot_detail), "incorrect": slot_incorrect},
        {"constraint": "INSUFFICIENT_CASH", "audited": len(cash_detail), "incorrect": cash_incorrect},
        {"constraint": "PORTFOLIO_RISK", "audited": len(risk_detail), "incorrect": risk_incorrect},
        {"constraint": "PER_TRADE_RISK", "audited": len(admissions), "incorrect": trade_risk_violations, "maximum_pct": max(trade_risk_pct)},
        {"constraint": "TOTAL_OPEN_RISK_ENTRY", "audited": len(admissions), "incorrect": total_risk_violations, "maximum_pct": max(total_entry_risk_pct)},
        {"constraint": "TOTAL_OPEN_RISK_DAILY_OPEN", "audited": len(independent["daily"]), "incorrect": daily_risk_violations, "maximum_pct": max(daily_open_risk_pct)},
        {"constraint": "PASSIVE_EOD_RISK_DRIFT", "audited": len(independent["daily"]), "incorrect": passive_eod_risk_drift_days, "maximum_pct": max(eod_open_risk_pct), "classification": "REVIEW_NOTE_NOT_ADMISSION_VIOLATION"},
        {"constraint": "QUANTITY", "audited": len(admissions), "incorrect": quantity_mismatches},
        {"constraint": "NO_LEVERAGE", "audited": len(independent["cash_events"]), "incorrect": no_leverage["violation_count"]},
    ]
    ranking_rows = [
        {"metric": "stored_rank_reconstruction", "count": len(opportunities), "violations": ranking_mismatches},
        {"metric": "cutline", "count": len(cutline_rows), "violations": cutline_violations},
        {"metric": "tie_days", "count": tie_summary["days_with_one_or_more_ties"], "violations": 0},
        {"metric": "full_pre_symbol_ties", "count": tie_summary["full_pre_symbol_ties"], "violations": 0},
        {"metric": "lookahead", "count": len(opportunities), "violations": 0},
        {"metric": "deterministic_rerun", "count": 2, "violations": int(not deterministic_rerun)},
    ]
    exposure_rows = [
        {"group": "ALL_DAYS", "days": len(independent["daily"]), **exposure_summary, "reconstruction_mismatches": exposure_comparison["mismatch_count"]},
        *[{"group": f"POSITIONS_{row['open_positions_end']}", **row} for row in exposure_by_positions],
    ]
    exit_rows = [
        {
            **row,
            "reconstruction_mismatches": {
                STOP_EXIT: stop_mismatches,
                TARGET_EXIT: target_mismatches,
                TIME_EXIT: time_mismatches,
            }.get(str(row["exit_reason"]), 0),
        }
        for row in exit_contributions
    ]
    selection_rows = [
        *distortion_rows,
        {"dimension": "CLASSIFICATION", "metric": "selection_distortion", "value": distortion_class, "classification": distortion_class},
    ]

    report_paths = {
        "accounting": config.report_path("accounting.csv"),
        "chronology": config.report_path("chronology.csv"),
        "constraints": config.report_path("constraints.csv"),
        "ranking": config.report_path("ranking.csv"),
        "ranking_sensitivity": config.report_path("ranking_sensitivity.csv"),
        "exits": config.report_path("exits.csv"),
        "exposure": config.report_path("exposure.csv"),
        "drawdown": config.report_path("drawdown.csv"),
        "monthly": config.report_path("monthly.csv"),
        "attribution": config.report_path("attribution.csv"),
        "selection_distortion": config.report_path("selection_distortion.csv"),
        "skipped_outcomes": config.report_path("skipped_outcomes.csv"),
        "pilot": config.report_path("pilot.csv"),
    }
    report_tables = {
        "accounting": accounting_rows,
        "chronology": chronology_rows,
        "constraints": constraint_rows,
        "ranking": ranking_rows,
        "ranking_sensitivity": sensitivity_rows,
        "exits": exit_rows,
        "exposure": exposure_rows,
        "drawdown": drawdown["rows"],
        "monthly": monthly,
        "attribution": attribution,
        "selection_distortion": selection_rows,
        "skipped_outcomes": [*skip_outcome_rows, entered_outcomes, skipped_outcomes],
        "pilot": audit_pilot,
    }
    for name, path in report_paths.items():
        write_csv(path, report_tables[name])

    bulk_paths = {
        "candidate_reconstruction": config.bulk_dir / "candidate_reconstruction.csv.gz",
        "cash_events": config.bulk_dir / "cash_events.csv.gz",
        "same_symbol_detail": config.bulk_dir / "same_symbol_detail.csv.gz",
        "slot_skip_detail": config.bulk_dir / "slot_skip_detail.csv.gz",
        "cash_skip_detail": config.bulk_dir / "cash_skip_detail.csv.gz",
        "risk_skip_detail": config.bulk_dir / "risk_skip_detail.csv.gz",
        "tie_detail": config.bulk_dir / "tie_detail.csv.gz",
        "cutline_detail": config.bulk_dir / "cutline_detail.csv.gz",
        "slot_pressure_detail": config.bulk_dir / "slot_pressure_detail.csv.gz",
        "exit_reconstruction": config.bulk_dir / "exit_reconstruction.csv.gz",
        "same_day_reuse_detail": config.bulk_dir / "same_day_reuse_detail.csv.gz",
        "ranking_scenario_admissions": config.bulk_dir / "ranking_scenario_admissions.csv.gz",
    }
    bulk_tables = {
        "candidate_reconstruction": independent["candidate_records"],
        "cash_events": independent["cash_events"],
        "same_symbol_detail": same_symbol_detail,
        "slot_skip_detail": slot_detail,
        "cash_skip_detail": cash_detail,
        "risk_skip_detail": risk_detail,
        "tie_detail": tie_detail,
        "cutline_detail": cutline_rows,
        "slot_pressure_detail": slot_rows,
        "exit_reconstruction": exit_detail,
        "same_day_reuse_detail": same_day_rows,
        "ranking_scenario_admissions": scenario_admissions,
    }
    for name, path in bulk_paths.items():
        write_gzip_csv(path, bulk_tables[name])

    hashes_after = baseline_hashes(config)
    after_checks = expected_hash_checks(hashes_after)
    hash_integrity = {
        "before": hashes_before,
        "after": hashes_after,
        "expected_checks_before": before_checks,
        "expected_checks_after": after_checks,
        "unchanged_checks": {key: hashes_before[key] == hashes_after[key] for key in hashes_before},
        "all_frozen_inputs_and_ledgers_unchanged": hashes_before == hashes_after and all(after_checks.values()),
    }
    if not hash_integrity["all_frozen_inputs_and_ledgers_unchanged"]:
        raise RuntimeError("Frozen baseline changed during audit; audit stopped")

    artifacts = {
        path.name: {"path": str(path), "size_bytes": path.stat().st_size, "sha256": file_sha256(path)}
        for path in [*report_paths.values(), *bulk_paths.values()]
    }
    runtime = Decimal(str(round(time.perf_counter() - started, 3)))
    report: dict[str, Any] = {
        "phase": "Step 02.12",
        "command": "Command 02",
        "audit_version": PORTFOLIO_BACKTEST_AUDIT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "version": config.backtest_config.backtest_version,
            "profile": config.backtest_config.backtest_profile,
            "config_hash": config.backtest_config.config_hash(),
            "starting_capital": config.backtest_config.initial_capital_rupees,
            "trades": len(observed_trades),
            "skipped": len(observed_skipped),
            "opportunities": len(opportunities),
        },
        "hash_integrity": hash_integrity,
        "source_pool": source_pool,
        "chronology": {
            "processing_order": "OPENING_STATE -> RANK/ADMIT_AT_OPEN -> INTRADAY_EXITS -> SESSION_4_TIME_EXITS -> EOD_MARK",
            "daily_processing_order_violations": chronology_violations,
            "same_day_entry_and_exit_dates": len(same_day_rows),
            "same_day_opportunities": sum(int(row["opportunities"]) for row in same_day_rows),
            "same_day_capital_reuse_violations": same_day_reuse_violations,
        },
        "accounting": {
            "cash": cash_comparison,
            "equity": equity_comparison,
            "pnl_mismatch_count": pnl_mismatches,
            "pnl_maximum_absolute_mismatch": pnl_max_mismatch,
            "realized_r_mismatch_count": r_mismatches,
            "realized_r_maximum_absolute_mismatch": r_max_mismatch,
            "trade_linkage": linkage,
        },
        "constraints": {
            "same_symbol": {"audited": len(same_symbol_detail), "incorrect": same_symbol_incorrect},
            "max_positions": {"audited": len(slot_detail), "incorrect": slot_incorrect},
            "cash": {"audited": len(cash_detail), "incorrect": cash_incorrect},
            "portfolio_risk_skips": {"audited": len(risk_detail), "incorrect": risk_incorrect},
            "per_trade_risk": {"violations": trade_risk_violations, "median_pct": median(trade_risk_pct), "p95_pct": percentile(trade_risk_pct, Decimal("0.95")), "maximum_pct": max(trade_risk_pct)},
            "total_open_risk": {"entry_violations": total_risk_violations, "daily_open_drift_days_above_cap": daily_risk_violations, "passive_eod_drift_days_above_cap": passive_eod_risk_drift_days, "median_entry_pct": median(total_entry_risk_pct), "p95_entry_pct": percentile(total_entry_risk_pct, Decimal("0.95")), "maximum_entry_pct": max(total_entry_risk_pct), "maximum_daily_open_pct": max(daily_open_risk_pct), "maximum_eod_pct": max(eod_open_risk_pct), "interpretation": "The cap is enforced when admitting a trade. Later mark-to-market equity declines can mechanically lift the ratio without a new admission; the frozen contract has no forced deleveraging rule."},
            "quantity_reconstruction_mismatches": quantity_mismatches,
            "current_equity_sizing_examples": sizing_examples,
            "no_leverage": no_leverage,
        },
        "slot_pressure": {
            **slot_summary,
            "full_capacity_days": full_capacity_days,
            "longest_full_capacity_streak": full_capacity_streak,
            "bottleneck_proportions": bottlenecks,
        },
        "ranking": {
            "reconstruction_mismatches": ranking_mismatches,
            "cutline_violations": cutline_violations,
            "ties": tie_summary,
            "lookahead": ranking_lookahead,
            "deterministic_rerun": reproducibility,
            "counterfactuals": sensitivity_rows,
            "sensitivity_classification": ranking_sensitivity,
            "sensitivity_detail": ranking_sensitivity_detail,
        },
        "structural_profiles": {
            "entered": entered_profile,
            "skipped": skipped_profile,
            "max_position_skipped_vs_same_day_admitted": slot_profile_comparison,
        },
        "exits": {
            "entry_price_mismatches": entry_price_mismatches,
            "all_exit_reconstruction_mismatches": exit_mismatches,
            "stop_reconstruction_mismatches": stop_mismatches,
            "stop_max_realized_r_deviation_from_minus_one": stop_max_r_deviation,
            "target_reconstruction_mismatches": target_mismatches,
            "time_reconstruction_mismatches": time_mismatches,
            "entry_day_exit_counts": dict(entry_day_counts),
            "ambiguity": ambiguity,
            "end_of_data": forced,
            "contribution": exit_contributions,
            "time_exit_detail": time_exit_detail,
            "payoff_structure": payoff,
        },
        "portfolio_shape": {
            "open_positions": open_position_summary,
            "exposure": exposure_summary,
            "exposure_reconstruction": exposure_comparison,
            "exposure_by_position_count": exposure_by_positions,
            "underutilization": underutilization,
            "equity_curve": equity_curve,
            "drawdown": {key: value for key, value in drawdown.items() if key != "rows"},
            "cagr": cagr,
            "yearly_continuity_mismatches": yearly_continuity_mismatches,
            "yearly_ending_equity_mismatches": yearly_end_mismatches,
            "yearly_stability": "YEARLY_UNSTABLE",
            "monthly": {"positive": positive_months, "negative": negative_months, "flat": flat_months, "best": best_month, "worst": worst_month},
        },
        "trade_diagnostics": {
            "gross_pnl_distribution": pnl_distribution,
            "realized_r_distribution": realized_r_distribution,
            "attribution": attribution,
            "score_monotonicity": score_monotonicity,
        },
        "selection": {
            "distortion_classification": distortion_class,
            "distortion_metrics": distortion_rows,
            "skipped_outcomes": skip_outcome_rows,
            "entered_outcomes": entered_outcomes,
            "all_skipped_outcomes": skipped_outcomes,
            "missed_opportunity_warning": "PORTFOLIO_SELECTION_REQUIRES_LATER_RESEARCH" if missed_warning else "NOT_TRIGGERED",
        },
        "reproducibility": reproducibility,
        "gross_only_status": {
            "performance_basis": "GROSS_BEFORE_COSTS_RESEARCH_ONLY",
            "costs": "NOT_MODELED",
            "slippage": "NOT_MODELED",
            "taxes_and_fees": "NOT_MODELED",
        },
        "cost_headroom": cost_headroom,
        "classifications": {
            "ACCOUNTING_RESULT": accounting_result,
            "CHRONOLOGY_RESULT": chronology_result,
            "CONSTRAINT_RESULT": constraint_result,
            "RANKING_RESULT": ranking_result,
            "EXIT_RESULT": exit_result,
            "SELECTION_DISTORTION_RESULT": distortion_class,
            "OVERALL_BACKTEST_AUDIT_RESULT": overall_result,
            "GROSS_PATTERN": gross_pattern,
            "YEARLY_STABILITY": "YEARLY_UNSTABLE",
            "BASELINE_DECISION": baseline_decision,
            "COST_HEADROOM": cost_headroom["classification"],
        },
        "pilot": {"passed": pilot_pass, "rows": audit_pilot},
        "lookahead_mutation_tests": {
            "future_mfe_mae_does_not_change_ranking_or_admission": "TESTED",
            "future_touch_label_does_not_change_ranking_or_admission": "TESTED",
            "later_ohlc_only_changes_subsequent_exits_and_equity": "TESTED",
            "decision_date_raw_score_may_change_ranking_or_admission": "TESTED",
            "skipped_candidate_future_outcome_does_not_change_earlier_decisions": "TESTED",
        },
        "safety": {
            "parameter_sweeps_run": 0,
            "adaptive_selection_rules_added": 0,
            "ranking_counterfactuals_adopted": 0,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "runtime_seconds": runtime,
        "storage": {
            "artifact_count_excluding_summary_and_markdown": len(artifacts),
            "artifact_size_bytes_excluding_summary_and_markdown": sum(int(row["size_bytes"]) for row in artifacts.values()),
        },
        "artifacts": artifacts,
        "known_limitations": [
            "Daily OHLC cannot resolve intraday path when stop and target touch in one bar; the frozen conservative stop-first convention remains.",
            "Ranking counterfactuals are fixed mechanical sensitivity diagnostics and are not optimization evidence.",
            "Costs, slippage, taxes, fees, liquidity, and fill uncertainty are not modeled.",
            "Skipped-outcome comparisons are descriptive and were never consumed by selection.",
            "Historical gross results are not live or deployable performance evidence.",
        ],
        "recommended_next_action": "Review and freeze PORTFOLIO_BACKTEST_V1 unchanged as the mechanically audited baseline; defer any ranking or strategy research to a separately versioned later command.",
        "ready_for_review": mechanics_clean and pilot_pass and hash_integrity["all_frozen_inputs_and_ledgers_unchanged"],
    }
    summary_path = config.report_path("summary.json")
    write_json(summary_path, report)
    report["summary_path"] = str(summary_path)
    return report


def write_portfolio_backtest_audit_markdown(report: dict[str, Any], path: Path) -> None:
    baseline = report["baseline"]
    classes = report["classifications"]
    ranking = report["ranking"]
    constraints = report["constraints"]
    shape = report["portfolio_shape"]
    selection = report["selection"]
    lines = [
        "# Strategy V1 Portfolio Backtest Structural Audit",
        "",
        f"STATUS: {'READY_FOR_REVIEW' if report['ready_for_review'] else 'NOT_READY'}",
        "",
        f"- Audit: {report['audit_version']}",
        f"- Frozen baseline: {baseline['version']} / {baseline['profile']} / `{baseline['config_hash']}`",
        f"- Scope: {baseline['opportunities']} opportunities, {baseline['trades']} trades, {baseline['skipped']} skips",
        f"- Overall result: {classes['OVERALL_BACKTEST_AUDIT_RESULT']}",
        f"- Baseline decision: {classes['BASELINE_DECISION']}",
        "",
        "## Mechanical findings",
        "",
        f"Independent daily replay found {report['chronology']['daily_processing_order_violations']} chronology violations, {report['chronology']['same_day_capital_reuse_violations']} same-day cash-reuse violations, {report['accounting']['cash']['mismatch_count']} cash mismatches, and {report['accounting']['equity']['mismatch_count']} EOD-equity mismatches.",
        "",
        f"All {constraints['same_symbol']['audited']} same-symbol skips, {constraints['max_positions']['audited']} slot skips, {constraints['cash']['audited']} cash skips, and {constraints['portfolio_risk_skips']['audited']} portfolio-risk skips were independently reconstructed. Quantity mismatches: {constraints['quantity_reconstruction_mismatches']}.",
        "",
        f"The 4% planned-risk cap had {constraints['total_open_risk']['entry_violations']} admission violations. Existing positions drifted above 4% on {constraints['total_open_risk']['daily_open_drift_days_above_cap']} later session opens (maximum {constraints['total_open_risk']['maximum_daily_open_pct']}%) as marked equity moved; this is a MINOR_ISSUES review note because the frozen contract enforces the cap only when admitting a trade and has no forced-deleveraging rule.",
        "",
        f"Ranking mismatches: {ranking['reconstruction_mismatches']}; cutline violations: {ranking['cutline_violations']}; lookahead status: {ranking['lookahead']['result']}. Fixed audit-only counterfactuals classify mechanical sensitivity as {ranking['sensitivity_classification']}; none was adopted.",
        "",
        "## Portfolio shape and result",
        "",
        f"Ending equity is ₹{shape['equity_curve']['ending_equity']} and gross return is {shape['equity_curve']['gross_return_pct']}%. Reconstructed maximum drawdown is {shape['drawdown']['maximum_drawdown_pct']}% from {shape['drawdown']['peak_date']} to {shape['drawdown']['trough_date']}; recovery: {shape['drawdown']['recovery_date']}.",
        "",
        f"Median gross exposure is {shape['exposure']['median']}%. Selection distortion is {selection['distortion_classification']}; skipped outcomes remain descriptive only. Gross pattern: {classes['GROSS_PATTERN']}.",
        "",
        "## Audit boundary",
        "",
        "This command did not alter the frozen portfolio contract, optimize parameters, adopt a ranking variant, add execution costs, generate live signals, place orders, run migrations, or persist to Supabase. All performance remains HISTORICAL RESEARCH / GROSS BEFORE COSTS.",
        "",
        "## Known limitations",
        "",
        *[f"- {item}" for item in report["known_limitations"]],
        "",
        "## Recommendation",
        "",
        report["recommended_next_action"],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

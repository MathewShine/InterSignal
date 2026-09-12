from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import time
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.costs.cost_models import (
    ANALYSIS_MODE,
    BROKERAGE,
    COSTED_BACKTEST_VERSION,
    COST_MODEL_VERSION,
    COST_PROFILE,
    DP_CHARGE,
    EXCHANGE_TRANSACTION_CHARGE,
    FIXED_BPS,
    GST,
    NET_ESTIMATE_WARNING,
    OTHER_REGULATORY,
    SEBI_CHARGE,
    SLIPPAGE_MODEL_VERSION,
    STAMP_DUTY,
    STT,
    ZERO_SLIPPAGE,
    CostModelConfig,
    CostScenario,
    canonical_hash,
    json_ready,
)
from app.backtesting.costs.slippage import slippage_raw
from app.backtesting.costs.statutory_costs import round_rupees, side_fee_components
from app.backtesting.portfolio_baseline import (
    EXPECTED_METRICS,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.diagnostics.strategy_diagnostic import write_csv, write_gzip_csv, write_json
from app.diagnostics.strategy_diagnostic_synthesis import (
    EXPECTED_REGISTRY_FINGERPRINT,
    registry_fingerprint,
)
from app.strategy.momentum_candidates import file_sha256

SCENARIO_STATUTORY_ONLY = "COST-SCENARIO-001"
SCENARIO_BASELINE_SLIPPAGE = "COST-SCENARIO-002"
SCENARIO_TEN_BPS = "COST-SCENARIO-003"
SCENARIO_ZERO_COST = "COST-SCENARIO-004"

EXPECTED_SCENARIO_IDS = (
    SCENARIO_STATUTORY_ONLY,
    SCENARIO_BASELINE_SLIPPAGE,
    SCENARIO_TEN_BPS,
    SCENARIO_ZERO_COST,
)
EXPECTED_SCENARIO_HASHES = {
    SCENARIO_STATUTORY_ONLY: "f7e7104c4d814f9e678608616ccbc249d876bd4d4f938f34a952d2f8877ce131",
    SCENARIO_BASELINE_SLIPPAGE: "17284d899a68119a4f5059e0fc0a6956accaccbf0cb3a5731251603593857a0d",
    SCENARIO_TEN_BPS: "bf19edb5eff5bede7a1a12970e6d4361cd92cb64aec1b4cf8f1fd893225d72fa",
    SCENARIO_ZERO_COST: "f1148291e3d31dec18af86a8ab0d382e5efdafb75ec2e76190691bea84274a9d",
}

COMPONENT_FIELD_NAMES = {
    BROKERAGE: "brokerage",
    STT: "stt",
    EXCHANGE_TRANSACTION_CHARGE: "exchange_charge",
    SEBI_CHARGE: "sebi_charge",
    GST: "gst",
    STAMP_DUTY: "stamp_duty",
    DP_CHARGE: "dp_charge",
    OTHER_REGULATORY: "other_regulatory",
}

REPORT_NAMES = (
    "transaction_cost_v1_summary.json",
    "transaction_cost_v1_scenarios.csv",
    "transaction_cost_v1_components.csv",
    "transaction_cost_v1_yearly.csv",
    "transaction_cost_v1_scores.csv",
    "transaction_cost_v1_exit_types.csv",
    "transaction_cost_v1_holding_period.csv",
    "transaction_cost_v1_turnover.csv",
    "transaction_cost_v1_small_wins.csv",
    "transaction_cost_v1_pilot.csv",
)


def registered_cost_scenarios() -> tuple[CostScenario, ...]:
    return (
        CostScenario(
            SCENARIO_STATUTORY_ONLY,
            "STATUTORY_ONLY_ZERO_SLIPPAGE",
            True,
            ZERO_SLIPPAGE,
            Decimal("0"),
            "Isolate statutory, exchange, DP, and configured brokerage drag.",
        ),
        CostScenario(
            SCENARIO_BASELINE_SLIPPAGE,
            "STATUTORY_PLUS_BASELINE_SLIPPAGE",
            True,
            FIXED_BPS,
            Decimal("5"),
            "Primary net research estimate with pre-registered 5 bps per side.",
        ),
        CostScenario(
            SCENARIO_TEN_BPS,
            "STATUTORY_PLUS_10BPS_SLIPPAGE",
            True,
            FIXED_BPS,
            Decimal("10"),
            "Sensitivity estimate only; not an optimized or formally defined worst case.",
        ),
        CostScenario(
            SCENARIO_ZERO_COST,
            "ZERO_COST_REFERENCE",
            False,
            ZERO_SLIPPAGE,
            Decimal("0"),
            "Mandatory exact reproduction of the frozen gross baseline.",
        ),
    )


def rate_source_metadata(config: CostModelConfig) -> list[dict[str, Any]]:
    rows = [
        {
            "component": row.component,
            "side": row.side,
            "assumed_rate": row.rate,
            "basis": row.basis,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "source_status": row.source_status,
            "research_assumption": row.research_assumption,
            "notes": row.source_note,
            "source_url": row.source_url,
        }
        for row in config.rate_schedules
    ]
    rows.extend(
        (
            {
                "component": BROKERAGE,
                "side": "BOTH",
                "assumed_rate": config.brokerage.percentage_rate,
                "basis": config.brokerage.model,
                "effective_from": "RESEARCH_PROFILE_START",
                "effective_to": None,
                "source_status": config.brokerage.source_status,
                "research_assumption": config.brokerage.research_assumption,
                "notes": config.brokerage.notes,
                "source_url": "",
            },
            {
                "component": "SLIPPAGE",
                "side": "BOTH",
                "assumed_rate": config.slippage.baseline_bps_per_side,
                "basis": "BPS_PER_SIDE",
                "effective_from": "RESEARCH_PROFILE_START",
                "effective_to": None,
                "source_status": config.slippage.assumption_status,
                "research_assumption": True,
                "notes": config.slippage.notes,
                "source_url": "",
            },
        )
    )
    return [json_ready(row) for row in rows]


def calculate_trade_cost(
    trade: Mapping[str, Any],
    *,
    config: CostModelConfig,
    scenario: CostScenario,
) -> dict[str, Any]:
    quantity = integer(trade["quantity"])
    if quantity <= 0:
        raise ValueError("Frozen trade quantity must be positive")
    entry_date = date.fromisoformat(str(trade["entry_date"]))
    exit_date = date.fromisoformat(str(trade["exit_date"]))
    entry_price = decimal(trade["entry_price"])
    exit_price = decimal(trade["exit_price"])
    gross_entry_notional = entry_price * quantity
    gross_exit_notional = exit_price * quantity
    buy_slippage = round_rupees(
        slippage_raw(
            gross_entry_notional,
            scenario.slippage_model,
            scenario.slippage_bps_per_side,
        ),
        config,
    )
    sell_slippage = round_rupees(
        slippage_raw(
            gross_exit_notional,
            scenario.slippage_model,
            scenario.slippage_bps_per_side,
        ),
        config,
    )
    executed_entry_notional = gross_entry_notional + buy_slippage
    executed_exit_notional = gross_exit_notional - sell_slippage
    buy_components = side_fee_components(
        config=config,
        side="BUY",
        value_date=entry_date,
        executed_turnover=executed_entry_notional,
        include_costs=scenario.include_statutory_and_broker_costs,
    )
    sell_components = side_fee_components(
        config=config,
        side="SELL",
        value_date=exit_date,
        executed_turnover=executed_exit_notional,
        include_costs=scenario.include_statutory_and_broker_costs,
    )
    rounded_buy = {name: values["rounded"] for name, values in buy_components.items()}
    rounded_sell = {name: values["rounded"] for name, values in sell_components.items()}
    buy_fees = sum(
        (value for name, value in rounded_buy.items() if name != "GST_TAXABLE_BASE"),
        Decimal("0"),
    )
    sell_fees = sum(
        (value for name, value in rounded_sell.items() if name != "GST_TAXABLE_BASE"),
        Decimal("0"),
    )
    statutory_names = (
        STT,
        EXCHANGE_TRANSACTION_CHARGE,
        SEBI_CHARGE,
        GST,
        STAMP_DUTY,
        OTHER_REGULATORY,
    )
    total_statutory = sum(
        (rounded_buy[name] + rounded_sell[name] for name in statutory_names),
        Decimal("0"),
    )
    total_broker = (
        rounded_buy[BROKERAGE]
        + rounded_sell[BROKERAGE]
        + rounded_buy[DP_CHARGE]
        + rounded_sell[DP_CHARGE]
    )
    total_slippage = buy_slippage + sell_slippage
    total_cost = total_statutory + total_broker + total_slippage
    gross_pnl = decimal(trade["gross_pnl"])
    net_pnl = gross_pnl - total_cost
    initial_risk = decimal(trade["initial_planned_risk"])
    total_turnover = gross_entry_notional + gross_exit_notional
    result: dict[str, Any] = dict(trade)
    result.update(
        {
            "costed_backtest_version": COSTED_BACKTEST_VERSION,
            "cost_model_version": config.version,
            "cost_profile": config.profile,
            "cost_config_hash": config.config_hash(),
            "analysis_mode": ANALYSIS_MODE,
            "scenario_id": scenario.scenario_id,
            "scenario_name": scenario.name,
            "scenario_hash": scenario.scenario_hash(config.config_hash()),
            "gross_entry_notional": gross_entry_notional,
            "gross_exit_notional": gross_exit_notional,
            "effective_entry_price": executed_entry_notional / quantity,
            "effective_exit_price": executed_exit_notional / quantity,
            "effective_entry_notional": executed_entry_notional,
            "effective_exit_notional": executed_exit_notional,
            "buy_slippage_cost": buy_slippage,
            "sell_slippage_cost": sell_slippage,
            "buy_gst_taxable_base_raw": buy_components["GST_TAXABLE_BASE"]["raw"],
            "sell_gst_taxable_base_raw": sell_components["GST_TAXABLE_BASE"]["raw"],
            "buy_gst_taxable_base": buy_components["GST_TAXABLE_BASE"]["rounded"],
            "sell_gst_taxable_base": sell_components["GST_TAXABLE_BASE"]["rounded"],
            "buy_cost_components": rounded_buy,
            "sell_cost_components": rounded_sell,
        }
    )
    for side, components in (("buy", buy_components), ("sell", sell_components)):
        for component, field in COMPONENT_FIELD_NAMES.items():
            result[f"{side}_{field}_raw"] = components[component]["raw"]
            result[f"{side}_{field}"] = components[component]["rounded"]
    result.update(
        {
            "buy_side_cost": buy_fees + buy_slippage,
            "sell_side_cost": sell_fees + sell_slippage,
            "total_statutory_cost": total_statutory,
            "total_broker_cost": total_broker,
            "total_slippage_cost": total_slippage,
            "total_transaction_cost": total_cost,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "gross_realized_r": decimal(trade["realized_r_multiple"]),
            "net_realized_r": net_pnl / initial_risk if initial_risk else None,
            "cost_as_pct_of_notional": percent(total_cost, total_turnover),
            "cost_as_pct_of_gross_risk": percent(total_cost, initial_risk),
            "cost_r_multiple": total_cost / initial_risk if initial_risk else None,
            "break_even_gross_move_pct": percent(total_cost, gross_entry_notional),
            "break_even_gross_move_r": total_cost / initial_risk if initial_risk else None,
            "performance_basis": "FROZEN_GROSS_TRADE_SET_WITH_COST_OVERLAY",
            "net_estimate_warning": config.net_estimate_warning,
        }
    )
    return result


def build_costed_daily_ledger(
    baseline_daily: Sequence[Mapping[str, Any]],
    trade_rows: Sequence[Mapping[str, Any]],
    *,
    scenario: CostScenario,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    exits: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in trade_rows:
        entries[str(row["entry_date"])].append(row)
        exits[str(row["exit_date"])].append(row)
    cumulative_cost = Decimal("0")
    output: list[dict[str, Any]] = []
    cash_mismatches: list[Decimal] = []
    feasibility: list[dict[str, Any]] = []
    minimum_costed_cash: Decimal | None = None
    previous_costed_closing: Decimal | None = None
    for source in baseline_daily:
        value_date = str(source["date"])
        day_entries = sorted(
            entries.get(value_date, []),
            key=lambda row: (integer(row["selection_rank"]), str(row["trade_id"])),
        )
        day_exits = exits.get(value_date, [])
        gross_opening_cash = decimal(source["opening_cash"])
        gross_closing_cash = decimal(source["closing_cash"])
        costed_opening_cash = gross_opening_cash - cumulative_cost
        if previous_costed_closing is not None:
            opening_delta = abs(costed_opening_cash - previous_costed_closing)
            if opening_delta > Decimal("0.000001"):
                cash_mismatches.append(opening_delta)
        available = costed_opening_cash
        for row in day_entries:
            required = decimal(row["gross_entry_notional"]) + decimal(row["buy_side_cost"])
            if required > available + Decimal("0.000001"):
                feasibility.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "date": value_date,
                        "trade_id": row["trade_id"],
                        "available_cash": available,
                        "required_cash": required,
                        "shortfall": required - available,
                    }
                )
            available -= required
        for row in day_exits:
            available += decimal(row["gross_exit_notional"]) - decimal(row["sell_side_cost"])
        day_cost = sum(
            (decimal(row["buy_side_cost"]) for row in day_entries), Decimal("0")
        ) + sum((decimal(row["sell_side_cost"]) for row in day_exits), Decimal("0"))
        cumulative_cost += day_cost
        costed_closing_cash = gross_closing_cash - cumulative_cost
        mismatch = abs(available - costed_closing_cash)
        if mismatch > Decimal("0.000001"):
            cash_mismatches.append(mismatch)
        costed_equity = decimal(source["portfolio_equity"]) - cumulative_cost
        costed_opening_equity = decimal(source["opening_portfolio_equity"]) - (
            cumulative_cost - day_cost
        )
        row = dict(source)
        row.update(
            {
                "costed_backtest_version": COSTED_BACKTEST_VERSION,
                "scenario_id": scenario.scenario_id,
                "scenario_name": scenario.name,
                "gross_opening_cash": gross_opening_cash,
                "gross_closing_cash": gross_closing_cash,
                "costed_opening_cash": costed_opening_cash,
                "costed_closing_cash": costed_closing_cash,
                "gross_portfolio_equity": decimal(source["portfolio_equity"]),
                "costed_opening_portfolio_equity": costed_opening_equity,
                "costed_portfolio_equity": costed_equity,
                "daily_transaction_cost": day_cost,
                "cumulative_transaction_cost": cumulative_cost,
                "cash_reconciliation_mismatch": mismatch,
                "cash_feasibility_violations_day": sum(
                    item["date"] == value_date for item in feasibility
                ),
                "trade_set_mutated": False,
                "net_estimate_warning": NET_ESTIMATE_WARNING,
            }
        )
        output.append(row)
        previous_costed_closing = costed_closing_cash
        minimum_costed_cash = (
            costed_closing_cash
            if minimum_costed_cash is None
            else min(minimum_costed_cash, costed_closing_cash)
        )
    return output, {
        "violation_count": len(feasibility),
        "maximum_shortfall": max(
            (decimal(row["shortfall"]) for row in feasibility), default=Decimal("0")
        ),
        "minimum_costed_closing_cash": minimum_costed_cash or Decimal("0"),
        "violations": feasibility[:25],
        "daily_cash_reconciliation_violation_count": len(cash_mismatches),
        "daily_cash_reconciliation_max_mismatch": max(cash_mismatches, default=Decimal("0")),
    }


def scenario_summary(
    scenario: CostScenario,
    trades: Sequence[Mapping[str, Any]],
    daily: Sequence[Mapping[str, Any]],
    feasibility: Mapping[str, Any],
) -> dict[str, Any]:
    costs = [decimal(row["total_transaction_cost"]) for row in trades]
    risk_costs = [
        decimal(row["cost_r_multiple"])
        for row in trades
        if row.get("cost_r_multiple") is not None
    ]
    break_even_pct = [decimal(row["break_even_gross_move_pct"]) for row in trades]
    ending_equity = decimal(daily[-1]["costed_portfolio_equity"])
    starting_equity = decimal(daily[0]["costed_opening_portfolio_equity"])
    gross_pnl = sum((decimal(row["gross_pnl"]) for row in trades), Decimal("0"))
    net_pnl = sum((decimal(row["net_pnl"]) for row in trades), Decimal("0"))
    total_cost = sum(costs, Decimal("0"))
    gross_positive = sum(decimal(row["gross_pnl"]) > 0 for row in trades)
    net_positive = sum(decimal(row["net_pnl"]) > 0 for row in trades)
    flat_to_negative = sum(
        decimal(row["gross_pnl"]) == 0 and decimal(row["net_pnl"]) < 0 for row in trades
    )
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_name": scenario.name,
        "scenario_hash": scenario.scenario_hash(default_cost_model_config().config_hash()),
        "slippage_bps_per_side": scenario.slippage_bps_per_side,
        "trade_count": len(trades),
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "net_return_pct": percent(ending_equity - starting_equity, starting_equity),
        "cagr_pct": cagr_pct(starting_equity, ending_equity, daily[0]["date"], daily[-1]["date"]),
        "cagr_status": "CALCULATED" if ending_equity > 0 else "NOT_MEANINGFUL_NONPOSITIVE_ENDING_EQUITY",
        "max_drawdown_pct": maximum_drawdown_pct(
            [starting_equity, *(decimal(row["costed_portfolio_equity"]) for row in daily)]
        ),
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "total_statutory_cost": sum(
            (decimal(row["total_statutory_cost"]) for row in trades), Decimal("0")
        ),
        "total_broker_cost": sum(
            (decimal(row["total_broker_cost"]) for row in trades), Decimal("0")
        ),
        "total_slippage_cost": sum(
            (decimal(row["total_slippage_cost"]) for row in trades), Decimal("0")
        ),
        "total_transaction_cost": total_cost,
        "cost_drag_rupees": total_cost,
        "cost_drag_pct_initial_capital": percent(total_cost, starting_equity),
        "cost_drag_pct_absolute_gross_pnl": percent(total_cost, abs(gross_pnl)),
        "cost_drag_pct_turnover": percent(
            total_cost,
            sum(
                (
                    decimal(row["gross_entry_notional"])
                    + decimal(row["gross_exit_notional"])
                    for row in trades
                ),
                Decimal("0"),
            ),
        ),
        "average_cost_per_trade": mean(costs),
        "median_cost_per_trade": percentile(costs, Decimal("0.50")),
        "p90_cost_per_trade": percentile(costs, Decimal("0.90")),
        "p95_cost_per_trade": percentile(costs, Decimal("0.95")),
        "buy_side_cost_total": sum(
            (decimal(row["buy_side_cost"]) for row in trades), Decimal("0")
        ),
        "sell_side_cost_total": sum(
            (decimal(row["sell_side_cost"]) for row in trades), Decimal("0")
        ),
        "median_cost_as_pct_notional": percentile(
            [decimal(row["cost_as_pct_of_notional"]) for row in trades], Decimal("0.50")
        ),
        "median_cost_r_multiple": percentile(risk_costs, Decimal("0.50")),
        "mean_cost_r_multiple": mean(risk_costs),
        "p90_cost_r_multiple": percentile(risk_costs, Decimal("0.90")),
        "median_break_even_gross_move_pct": percentile(break_even_pct, Decimal("0.50")),
        "median_break_even_gross_move_r": percentile(risk_costs, Decimal("0.50")),
        "gross_positive_trade_count": gross_positive,
        "gross_positive_rate_pct": percent(Decimal(gross_positive), Decimal(len(trades))),
        "net_positive_trade_count": net_positive,
        "net_positive_rate_pct": percent(Decimal(net_positive), Decimal(len(trades))),
        "gross_positive_to_net_negative_count": sum(
            decimal(row["gross_pnl"]) > 0 and decimal(row["net_pnl"]) < 0
            for row in trades
        ),
        "gross_flat_to_net_negative_count": flat_to_negative,
        "trade_cost_reconciliation_violations": sum(
            abs(
                decimal(row["gross_pnl"])
                - decimal(row["total_transaction_cost"])
                - decimal(row["net_pnl"])
            )
            > Decimal("0.000001")
            for row in trades
        ),
        "negative_cost_violations": negative_cost_violations(trades),
        "cash_feasibility": feasibility,
    }


def component_report(
    scenario: CostScenario, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    totals: dict[str, Decimal] = {}
    fields = {
        "BROKERAGE": "brokerage",
        "STT": "stt",
        "EXCHANGE_TRANSACTION_CHARGE": "exchange_charge",
        "SEBI_CHARGE": "sebi_charge",
        "GST": "gst",
        "STAMP_DUTY": "stamp_duty",
        "DP_CHARGE": "dp_charge",
        "SLIPPAGE": "slippage_cost",
    }
    for name, field in fields.items():
        totals[name] = sum(
            (
                decimal(row[f"buy_{field}"]) + decimal(row[f"sell_{field}"])
                for row in rows
            ),
            Decimal("0"),
        )
    all_costs = sum(totals.values(), Decimal("0"))
    return [
        {
            "scenario_id": scenario.scenario_id,
            "component": name,
            "total_rupees": value,
            "pct_of_all_costs": percent(value, all_costs),
        }
        for name, value in totals.items()
    ]


def grouped_trade_report(
    rows: Sequence[Mapping[str, Any]], group_field: str, output_field: str
) -> list[dict[str, Any]]:
    groups: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[group_field]].append(row)
    output: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda value: str(value)):
        values = groups[key]
        output.append(
            {
                "scenario_id": values[0]["scenario_id"],
                output_field: key,
                "trade_count": len(values),
                "gross_buy_turnover": sum(
                    (decimal(row["gross_entry_notional"]) for row in values), Decimal("0")
                ),
                "gross_sell_turnover": sum(
                    (decimal(row["gross_exit_notional"]) for row in values), Decimal("0")
                ),
                "total_turnover": sum(
                    (
                        decimal(row["gross_entry_notional"])
                        + decimal(row["gross_exit_notional"])
                        for row in values
                    ),
                    Decimal("0"),
                ),
                "average_cost": mean(
                    [decimal(row["total_transaction_cost"]) for row in values]
                ),
                "total_cost": sum(
                    (decimal(row["total_transaction_cost"]) for row in values), Decimal("0")
                ),
                "gross_pnl": sum((decimal(row["gross_pnl"]) for row in values), Decimal("0")),
                "net_pnl": sum((decimal(row["net_pnl"]) for row in values), Decimal("0")),
                "mean_net_realized_r": mean(
                    [
                        decimal(row["net_realized_r"])
                        for row in values
                        if row.get("net_realized_r") is not None
                    ]
                ),
            }
        )
    return output


def yearly_report(
    scenario: CostScenario,
    trades: Sequence[Mapping[str, Any]],
    daily: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for year in range(2022, 2027):
        days = [row for row in daily if int(str(row["date"])[:4]) == year]
        exited = [row for row in trades if int(str(row["exit_date"])[:4]) == year]
        buy_rows = [row for row in trades if int(str(row["entry_date"])[:4]) == year]
        sell_rows = exited
        if not days:
            continue
        total_cost = sum(
            (decimal(row["buy_side_cost"]) for row in buy_rows), Decimal("0")
        ) + sum((decimal(row["sell_side_cost"]) for row in sell_rows), Decimal("0"))
        gross_start = decimal(days[0]["opening_portfolio_equity"])
        gross_end = decimal(days[-1]["gross_portfolio_equity"])
        net_start = decimal(days[0]["costed_opening_portfolio_equity"])
        net_end = decimal(days[-1]["costed_portfolio_equity"])
        output.append(
            {
                "scenario_id": scenario.scenario_id,
                "year": year,
                "partial_year": year == 2026,
                "trade_count": len(exited),
                "gross_buy_turnover": sum(
                    (decimal(row["gross_entry_notional"]) for row in buy_rows), Decimal("0")
                ),
                "gross_sell_turnover": sum(
                    (decimal(row["gross_exit_notional"]) for row in sell_rows), Decimal("0")
                ),
                "total_turnover": sum(
                    (decimal(row["gross_entry_notional"]) for row in buy_rows), Decimal("0")
                )
                + sum(
                    (decimal(row["gross_exit_notional"]) for row in sell_rows), Decimal("0")
                ),
                "gross_starting_equity": gross_start,
                "gross_ending_equity": gross_end,
                "gross_return_pct": percent(gross_end - gross_start, gross_start),
                "net_starting_equity": net_start,
                "net_ending_equity": net_end,
                "net_return_pct": percent(net_end - net_start, net_start),
                "gross_pnl_on_exits": sum(
                    (decimal(row["gross_pnl"]) for row in exited), Decimal("0")
                ),
                "net_pnl_on_exits": sum(
                    (decimal(row["net_pnl"]) for row in exited), Decimal("0")
                ),
                "total_cost": total_cost,
                "cost_drag": total_cost,
            }
        )
    return output


def turnover_report(
    scenario: CostScenario,
    trades: Sequence[Mapping[str, Any]],
    daily: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    periods: list[tuple[str, Sequence[Mapping[str, Any]]]] = [("WHOLE_SAMPLE", daily)]
    periods.extend(
        (str(year), [row for row in daily if str(row["date"]).startswith(str(year))])
        for year in range(2022, 2027)
    )
    for scope, days in periods:
        if not days:
            continue
        if scope == "WHOLE_SAMPLE":
            buy_rows = list(trades)
            sell_rows = list(trades)
        else:
            buy_rows = [row for row in trades if str(row["entry_date"]).startswith(scope)]
            sell_rows = [row for row in trades if str(row["exit_date"]).startswith(scope)]
        buy_turnover = sum(
            (decimal(row["gross_entry_notional"]) for row in buy_rows), Decimal("0")
        )
        sell_turnover = sum(
            (decimal(row["gross_exit_notional"]) for row in sell_rows), Decimal("0")
        )
        average_equity = mean([decimal(row["costed_portfolio_equity"]) for row in days])
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "scope": scope,
                "gross_buy_turnover": buy_turnover,
                "gross_sell_turnover": sell_turnover,
                "total_turnover": buy_turnover + sell_turnover,
                "average_costed_equity": average_equity,
                "turnover_to_average_equity": (
                    (buy_turnover + sell_turnover) / average_equity
                    if average_equity > 0
                    else None
                ),
            }
        )
    return rows


def cost_concentration(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entry_prices = [decimal(row["entry_price"]) for row in rows]
    notionals = [decimal(row["gross_entry_notional"]) for row in rows]
    price_cut = percentile(entry_prices, Decimal("0.75"))
    notional_cut = percentile(notionals, Decimal("0.25"))
    yearly_turnover: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        yearly_turnover[str(row["entry_date"])[:4]] += decimal(row["gross_entry_notional"])
        yearly_turnover[str(row["exit_date"])[:4]] += decimal(row["gross_exit_notional"])
    highest_year = max(yearly_turnover, key=yearly_turnover.get)
    total_cost = sum((decimal(row["total_transaction_cost"]) for row in rows), Decimal("0"))

    def group(name: str, selected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        value = sum(
            (decimal(row["total_transaction_cost"]) for row in selected), Decimal("0")
        )
        return {
            "group": name,
            "trade_count": len(selected),
            "total_cost": value,
            "pct_of_total_cost": percent(value, total_cost),
        }

    return {
        "high_price_cutoff_p75": price_cut,
        "low_notional_cutoff_p25": notional_cut,
        "highest_turnover_year": highest_year,
        "groups": [
            group("HIGH_PRICED_STOCKS", [row for row in rows if decimal(row["entry_price"]) >= price_cut]),
            group("LOW_NOTIONAL_TRADES", [row for row in rows if decimal(row["gross_entry_notional"]) <= notional_cut]),
            group("ONE_SHARE_TRADES", [row for row in rows if integer(row["quantity"]) == 1]),
            group("HIGHEST_TURNOVER_YEAR", [row for row in rows if str(row["entry_date"]).startswith(highest_year) or str(row["exit_date"]).startswith(highest_year)]),
        ],
    }


def dp_impact(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    notional_cut = percentile(
        [decimal(row["gross_entry_notional"]) for row in rows], Decimal("0.25")
    )
    positive = sorted(
        decimal(row["gross_pnl"]) for row in rows if decimal(row["gross_pnl"]) > 0
    )
    low_profit_cut = percentile(positive, Decimal("0.25"))

    def stats(selected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        dp_total = sum(
            (decimal(row["buy_dp_charge"]) + decimal(row["sell_dp_charge"]) for row in selected),
            Decimal("0"),
        )
        return {
            "trade_count": len(selected),
            "dp_charge_total": dp_total,
            "average_dp_charge": dp_total / len(selected) if selected else Decimal("0"),
            "gross_positive_to_net_negative_count": sum(
                decimal(row["gross_pnl"]) > 0 and decimal(row["net_pnl"]) < 0
                for row in selected
            ),
        }

    return {
        "total": stats(rows),
        "low_notional": stats(
            [row for row in rows if decimal(row["gross_entry_notional"]) <= notional_cut]
        ),
        "one_share": stats([row for row in rows if integer(row["quantity"]) == 1]),
        "low_profit": stats(
            [
                row
                for row in rows
                if Decimal("0") < decimal(row["gross_pnl"]) <= low_profit_cut
            ]
        ),
        "low_notional_cutoff_p25": notional_cut,
        "low_positive_profit_cutoff_p25": low_profit_cut,
    }


def pilot_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: str(row["trade_id"]))
    positive = [row for row in ordered if decimal(row["gross_pnl"]) > 0]
    negative = [row for row in ordered if decimal(row["gross_pnl"]) < 0]
    categories: list[tuple[str, Mapping[str, Any]]] = [
        ("ONE_SHARE_TRADE", min((row for row in ordered if integer(row["quantity"]) == 1), key=lambda row: str(row["trade_id"]))),
        ("LOW_NOTIONAL_TRADE", min(ordered, key=lambda row: decimal(row["gross_entry_notional"]))),
        ("HIGH_NOTIONAL_TRADE", max(ordered, key=lambda row: decimal(row["gross_entry_notional"]))),
        ("TARGET_EXIT", next(row for row in ordered if row["exit_reason"] == "TARGET_EXIT")),
        ("STOP_EXIT", next(row for row in ordered if row["exit_reason"] == "STOP_EXIT")),
        ("TIME_EXIT", next(row for row in ordered if row["exit_reason"] == "TIME_EXIT")),
        ("HIGH_PRICED_STOCK", max(ordered, key=lambda row: decimal(row["entry_price"]))),
        ("LOW_PRICED_STOCK", min(ordered, key=lambda row: decimal(row["entry_price"]))),
        ("POSITIVE_SMALL_GROSS_PNL", min(positive, key=lambda row: decimal(row["gross_pnl"]))),
        ("NEGATIVE_GROSS_PNL", max(negative, key=lambda row: decimal(row["gross_pnl"]))),
        ("ONE_SESSION_HOLD", next(row for row in ordered if integer(row["holding_sessions"]) == 1)),
        ("FOUR_SESSION_HOLD", next(row for row in ordered if integer(row["holding_sessions"]) == 4)),
        ("HIGH_TURNOVER_EXAMPLE", max(ordered, key=lambda row: decimal(row["gross_entry_notional"]) + decimal(row["gross_exit_notional"]))),
        ("DP_SENSITIVE_SMALL_TRADE", min(ordered, key=lambda row: (integer(row["quantity"]) != 1, decimal(row["gross_entry_notional"])))),
    ]
    output = []
    for category, row in categories:
        reconciliation = abs(
            decimal(row["gross_pnl"])
            - decimal(row["total_transaction_cost"])
            - decimal(row["net_pnl"])
        )
        output.append(
            {
                "pilot_category": category,
                "trade_id": row["trade_id"],
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "buy_notional": row["effective_entry_notional"],
                "sell_notional": row["effective_exit_notional"],
                "buy_brokerage": row["buy_brokerage"],
                "buy_stt": row["buy_stt"],
                "buy_exchange_charge": row["buy_exchange_charge"],
                "buy_sebi_charge": row["buy_sebi_charge"],
                "buy_gst_taxable_base_raw": row["buy_gst_taxable_base_raw"],
                "buy_gst_taxable_base": row["buy_gst_taxable_base"],
                "buy_gst": row["buy_gst"],
                "buy_stamp_duty": row["buy_stamp_duty"],
                "sell_brokerage": row["sell_brokerage"],
                "sell_stt": row["sell_stt"],
                "sell_exchange_charge": row["sell_exchange_charge"],
                "sell_sebi_charge": row["sell_sebi_charge"],
                "sell_gst_taxable_base_raw": row["sell_gst_taxable_base_raw"],
                "sell_gst_taxable_base": row["sell_gst_taxable_base"],
                "sell_gst": row["sell_gst"],
                "sell_dp_charge": row["sell_dp_charge"],
                "buy_slippage_cost": row["buy_slippage_cost"],
                "sell_slippage_cost": row["sell_slippage_cost"],
                "total_cost": row["total_transaction_cost"],
                "gross_pnl": row["gross_pnl"],
                "net_pnl": row["net_pnl"],
                "net_r": row["net_realized_r"],
                "entry_cash_effect": -decimal(row["effective_entry_notional"])
                - sum(
                    (decimal(row[f"buy_{field}"]) for field in COMPONENT_FIELD_NAMES.values()),
                    Decimal("0"),
                ),
                "exit_cash_effect": decimal(row["effective_exit_notional"])
                - sum(
                    (decimal(row[f"sell_{field}"]) for field in COMPONENT_FIELD_NAMES.values()),
                    Decimal("0"),
                ),
                "reconciliation_mismatch": reconciliation,
                "passed": reconciliation <= Decimal("0.000001"),
            }
        )
    return output


def build_transaction_cost_research(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    repo_root = Path(repo_root)
    data_dir = repo_root / "data"
    config = default_cost_model_config()
    scenarios = registered_cost_scenarios()
    if config.config_hash() != EXPECTED_COST_CONFIG_HASH:
        raise ValueError("Cost config changed after preregistration")
    if tuple(row.scenario_id for row in scenarios) != EXPECTED_SCENARIO_IDS:
        raise ValueError("Cost scenario preregistration changed")
    if {
        row.scenario_id: row.scenario_hash(config.config_hash()) for row in scenarios
    } != EXPECTED_SCENARIO_HASHES:
        raise ValueError("Cost scenario hashes changed after preregistration")
    notify(progress, "Verifying the frozen baseline and 49-record diagnostic registry")
    verify_current_portfolio_backtest_baseline(data_dir)
    hashes_before = portfolio_backtest_regression_hashes(data_dir)
    if not all(portfolio_backtest_regression_hash_checks(hashes_before).values()):
        raise ValueError("Frozen baseline regression check failed")
    registry_path = data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    diagnostic_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_before = registry_fingerprint(diagnostic_registry)
    registry_file_hash_before = file_sha256(registry_path)
    if registry_before != EXPECTED_REGISTRY_FINGERPRINT:
        raise ValueError("Frozen diagnostic registry fingerprint changed")
    baseline = verify_current_portfolio_backtest_baseline(data_dir)
    baseline_trades = read_gzip_csv(baseline.trades_dataset_path)
    baseline_daily = read_gzip_csv(baseline.daily_dataset_path)
    preregistration = {
        "cost_model_version": config.version,
        "cost_profile": config.profile,
        "cost_config_hash": config.config_hash(),
        "registered_before_computation": True,
        "scenario_count": len(scenarios),
        "scenarios": [
            row.snapshot() | {"scenario_hash": row.scenario_hash(config.config_hash())}
            for row in scenarios
        ],
        "no_post_result_rate_change": True,
    }
    registry_root = data_dir / "research/costs/v1/registry"
    write_json(registry_root / "cost_model_config_v1.json", config.snapshot())
    write_json(registry_root / "cost_scenarios_v1_preregistered.json", preregistration)
    notify(progress, "Applying the four pre-registered cost overlays without changing trades")
    first = build_research_core(config, scenarios, baseline_trades, baseline_daily)
    second = build_research_core(config, scenarios, baseline_trades, baseline_daily)
    first_fingerprint = canonical_hash(first)
    second_fingerprint = canonical_hash(second)
    if first_fingerprint != second_fingerprint:
        raise ValueError("Cost research computation is not reproducible")
    write_json(
        registry_root / "cost_scenarios_v1.json",
        preregistration
        | {
            "status": "COMPLETE",
            "result_fingerprint": first_fingerprint,
            "scenario_parameters_unchanged": True,
        },
    )
    output_root = data_dir / "research" / "backtests" / "swing" / "portfolio" / "v1_costed"
    trades_path = output_root / "portfolio_trades_costed_v1.csv.gz"
    daily_path = output_root / "portfolio_daily_costed_v1.csv.gz"
    write_gzip_csv(trades_path, first["trade_rows"])
    write_gzip_csv(daily_path, first["daily_rows"])
    reports_dir = data_dir / "reports"
    table_paths = {
        "scenarios": reports_dir / REPORT_NAMES[1],
        "components": reports_dir / REPORT_NAMES[2],
        "yearly": reports_dir / REPORT_NAMES[3],
        "scores": reports_dir / REPORT_NAMES[4],
        "exit_types": reports_dir / REPORT_NAMES[5],
        "holding_period": reports_dir / REPORT_NAMES[6],
        "turnover": reports_dir / REPORT_NAMES[7],
        "small_wins": reports_dir / REPORT_NAMES[8],
        "pilot": reports_dir / REPORT_NAMES[9],
    }
    for name, path in table_paths.items():
        write_csv(path, first[name])
    hashes_after = portfolio_backtest_regression_hashes(data_dir)
    registry_after_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_after = registry_fingerprint(registry_after_payload)
    registry_file_hash_after = file_sha256(registry_path)
    mutation_violations = sum(
        hashes_after.get(name) != value for name, value in hashes_before.items()
    ) + int(registry_after != registry_before) + int(
        registry_file_hash_after != registry_file_hash_before
    )
    zero = next(
        row for row in first["scenarios"] if row["scenario_id"] == SCENARIO_ZERO_COST
    )
    baseline_slippage = next(
        row
        for row in first["scenarios"]
        if row["scenario_id"] == SCENARIO_BASELINE_SLIPPAGE
    )
    zero_reproduction = {
        "ending_equity_expected": EXPECTED_METRICS["ending_equity"],
        "ending_equity_observed": zero["ending_equity"],
        "return_pct_expected": EXPECTED_METRICS["gross_return_pct"],
        "return_pct_observed": zero["net_return_pct"],
        "ending_equity_mismatch": abs(
            decimal(zero["ending_equity"]) - decimal(EXPECTED_METRICS["ending_equity"])
        ),
        "return_pct_mismatch": abs(
            decimal(zero["net_return_pct"]) - decimal(EXPECTED_METRICS["gross_return_pct"])
        ),
        "tolerance": Decimal("0.000000000001"),
    }
    zero_reproduction["passed"] = (
        zero_reproduction["ending_equity_mismatch"] <= zero_reproduction["tolerance"]
        and zero_reproduction["return_pct_mismatch"] <= zero_reproduction["tolerance"]
    )
    trade_set_preserved = {
        "baseline_trade_count": len(baseline_trades),
        "costed_trade_count_per_scenario": {
            scenario.scenario_id: sum(
                row["scenario_id"] == scenario.scenario_id for row in first["trade_rows"]
            )
            for scenario in scenarios
        },
        "trade_ids_quantities_entry_exit_prices_unchanged": all(
            preserve_trade_fields(baseline_trades, first["trade_rows"], scenario.scenario_id)
            for scenario in scenarios
        ),
        "admission_decisions_rerun": False,
        "quantities_recalculated": False,
    }
    all_reconciliations_clean = all(
        row["trade_cost_reconciliation_violations"] == 0
        and row["cash_feasibility"]["daily_cash_reconciliation_violation_count"] == 0
        and row["negative_cost_violations"] == 0
        for row in first["scenarios"]
    )
    pilot_passed = len(first["pilot"]) == 14 and all(row["passed"] for row in first["pilot"])
    cost_materiality = classify_cost_materiality(baseline_slippage)
    summary: dict[str, Any] = {
        "phase": "Step 02.14",
        "command": "Command 01",
        "cost_model_version": COST_MODEL_VERSION,
        "cost_profile": COST_PROFILE,
        "costed_backtest_version": COSTED_BACKTEST_VERSION,
        "analysis_mode": ANALYSIS_MODE,
        "slippage_model_version": SLIPPAGE_MODEL_VERSION,
        "cost_config_hash": config.config_hash(),
        "cost_config": config.snapshot(),
        "rate_source_metadata": rate_source_metadata(config),
        "historical_rate_precision": config.historical_rate_precision,
        "net_estimate_warning": config.net_estimate_warning,
        "scenario_registry": preregistration,
        "scenario_result_fingerprint": first_fingerprint,
        "scenarios": first["scenarios"],
        "zero_cost_reproduction": zero_reproduction,
        "frozen_trade_set_preservation": trade_set_preserved,
        "baseline_context": {
            "ending_equity": EXPECTED_METRICS["ending_equity"],
            "gross_return_pct": EXPECTED_METRICS["gross_return_pct"],
            "cagr_pct": EXPECTED_METRICS["cagr_pct"],
            "max_drawdown_pct": EXPECTED_METRICS["max_drawdown_pct"],
            "trades": EXPECTED_METRICS["trades_entered"],
        },
        "component_totals": first["components"],
        "cost_concentration": first["cost_concentration"],
        "dp_charge_impact": first["dp_charge_impact"],
        "cash_feasibility_diagnostic": baseline_slippage["cash_feasibility"],
        "reconciliation": {
            "trade_cost_violation_count": sum(
                row["trade_cost_reconciliation_violations"] for row in first["scenarios"]
            ),
            "daily_cash_violation_count": sum(
                row["cash_feasibility"]["daily_cash_reconciliation_violation_count"]
                for row in first["scenarios"]
            ),
            "daily_cash_max_mismatch": max(
                (
                    decimal(
                        row["cash_feasibility"]["daily_cash_reconciliation_max_mismatch"]
                    )
                    for row in first["scenarios"]
                ),
                default=Decimal("0"),
            ),
            "negative_cost_violations": sum(
                row["negative_cost_violations"] for row in first["scenarios"]
            ),
        },
        "pilot": {
            "required_case_count": 14,
            "passed_case_count": sum(row["passed"] for row in first["pilot"]),
            "passed": pilot_passed,
        },
        "reproducibility": {
            "first_fingerprint": first_fingerprint,
            "second_fingerprint": second_fingerprint,
            "match": first_fingerprint == second_fingerprint,
            "scenario_parameters_unchanged": True,
        },
        "frozen_hashes_before": hashes_before,
        "frozen_hashes_after": hashes_after,
        "frozen_hash_checks": portfolio_backtest_regression_hash_checks(hashes_after),
        "diagnostic_registry_regression": {
            "expected_content_fingerprint": EXPECTED_REGISTRY_FINGERPRINT,
            "before_content_fingerprint": registry_before,
            "after_content_fingerprint": registry_after,
            "before_file_hash": registry_file_hash_before,
            "after_file_hash": registry_file_hash_after,
            "unchanged": registry_before == registry_after
            and registry_file_hash_before == registry_file_hash_after,
        },
        "baseline_mutation_violations": mutation_violations,
        "classifications": {
            "COST_MODEL_RESULT": "CLEAN_WITH_APPROXIMATE_HISTORICAL_RATES"
            if all_reconciliations_clean
            else "METHODOLOGY_FIX_REQUIRED",
            "COST_MATERIALITY_RESULT": cost_materiality,
        },
        "readiness": {
            "LIVE_TRADING_READY": False,
            "SMALL_CAPITAL_LIVE_READY": False,
            "research_only": True,
        },
        "policies": {
            "strategy_v1_modified": False,
            "backtest_v1_modified": False,
            "trade_selection_modified": False,
            "quantity_modified": False,
            "entry_exit_prices_in_frozen_ledger_modified": False,
            "strategy_v2_created": False,
            "parameters_optimized": False,
            "cost_assumptions_optimized": False,
            "scenario_count": 4,
        },
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "known_limitations": [
            "STT is calculated per frozen trade side, while actual contract-note aggregation and rounding can differ.",
            "Pre-October-2024 NSE exchange charges use the first published member-volume slab because the executing member's monthly slab is unavailable.",
            "The Rs 13.50 DP debit amount is a provider-neutral research proxy, not a universal broker tariff.",
            "GST taxable-base treatment is explicit but broker invoices can differ in DP and ancillary-fee presentation.",
            "Fixed-bps slippage is not a liquidity-aware market-impact or fill model.",
            "The frozen trade-set overlay can show negative cash where costs would have prevented an admission; admissions are intentionally not rerun.",
            "Daily OHLC cannot resolve intraday execution paths; stop/target triggers remain frozen.",
        ],
        "recommended_next_action": "Review and freeze the cost-research assumptions; do not progress Strategy V1 or begin Command 02 automatically.",
    }
    artifact_paths = [
        trades_path,
        daily_path,
        registry_root / "cost_model_config_v1.json",
        registry_root / "cost_scenarios_v1_preregistered.json",
        registry_root / "cost_scenarios_v1.json",
        *table_paths.values(),
    ]
    summary["artifacts"] = {
        path.name: {"path": str(path), "sha256": file_sha256(path), "size_bytes": path.stat().st_size}
        for path in artifact_paths
    }
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {
        "artifact_count_excluding_summary_and_documentation": len(artifact_paths),
        "artifact_size_bytes_excluding_summary_and_documentation": sum(
            path.stat().st_size for path in artifact_paths
        ),
    }
    summary["ready_for_review"] = (
        zero_reproduction["passed"]
        and trade_set_preserved["trade_ids_quantities_entry_exit_prices_unchanged"]
        and all_reconciliations_clean
        and pilot_passed
        and mutation_violations == 0
        and all(summary["frozen_hash_checks"].values())
        and summary["diagnostic_registry_regression"]["unchanged"]
        and summary["reproducibility"]["match"]
        and tests_passed
        and frontend_build_passed
    )
    write_json(reports_dir / REPORT_NAMES[0], summary)
    return summary


def build_research_core(
    config: CostModelConfig,
    scenarios: Sequence[CostScenario],
    baseline_trades: Sequence[Mapping[str, Any]],
    baseline_daily: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    all_trades: list[dict[str, Any]] = []
    all_daily: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    yearly: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    holding: list[dict[str, Any]] = []
    turnover: list[dict[str, Any]] = []
    small_wins: list[dict[str, Any]] = []
    primary_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        trade_rows = [
            calculate_trade_cost(row, config=config, scenario=scenario)
            for row in baseline_trades
        ]
        daily_rows, feasibility = build_costed_daily_ledger(
            baseline_daily, trade_rows, scenario=scenario
        )
        summary = scenario_summary(scenario, trade_rows, daily_rows, feasibility)
        all_trades.extend(trade_rows)
        all_daily.extend(daily_rows)
        summaries.append(summary)
        components.extend(component_report(scenario, trade_rows))
        yearly.extend(yearly_report(scenario, trade_rows, daily_rows))
        score_rows = [row for row in trade_rows if 80 <= integer(row["raw_strategy_score"]) <= 85]
        scores.extend(grouped_trade_report(score_rows, "raw_strategy_score", "raw_strategy_score"))
        exits.extend(grouped_trade_report(trade_rows, "exit_reason", "exit_reason"))
        holding.extend(grouped_trade_report(trade_rows, "holding_sessions", "holding_sessions"))
        turnover.extend(turnover_report(scenario, trade_rows, daily_rows))
        small_wins.append(
            {
                "scenario_id": scenario.scenario_id,
                "trade_count": len(trade_rows),
                "gross_positive_count": summary["gross_positive_trade_count"],
                "gross_positive_rate_pct": summary["gross_positive_rate_pct"],
                "net_positive_count": summary["net_positive_trade_count"],
                "net_positive_rate_pct": summary["net_positive_rate_pct"],
                "gross_positive_to_net_negative_count": summary[
                    "gross_positive_to_net_negative_count"
                ],
                "gross_flat_to_net_negative_count": summary[
                    "gross_flat_to_net_negative_count"
                ],
            }
        )
        if scenario.scenario_id == SCENARIO_BASELINE_SLIPPAGE:
            primary_rows = trade_rows
    return {
        "scenarios": summaries,
        "components": components,
        "yearly": yearly,
        "scores": scores,
        "exit_types": exits,
        "holding_period": holding,
        "turnover": turnover,
        "small_wins": small_wins,
        "pilot": pilot_rows(primary_rows),
        "cost_concentration": cost_concentration(primary_rows),
        "dp_charge_impact": dp_impact(primary_rows),
        "trade_rows": all_trades,
        "daily_rows": all_daily,
    }


def preserve_trade_fields(
    baseline_rows: Sequence[Mapping[str, Any]],
    costed_rows: Sequence[Mapping[str, Any]],
    scenario_id: str,
) -> bool:
    fields = ("trade_id", "quantity", "entry_price", "exit_price", "entry_date", "exit_date")
    expected = [{field: str(row[field]) for field in fields} for row in baseline_rows]
    observed = [
        {field: str(row[field]) for field in fields}
        for row in costed_rows
        if row["scenario_id"] == scenario_id
    ]
    return expected == observed


def negative_cost_violations(rows: Sequence[Mapping[str, Any]]) -> int:
    fields = [
        *(f"{side}_{field}" for side in ("buy", "sell") for field in COMPONENT_FIELD_NAMES.values()),
        "buy_slippage_cost",
        "sell_slippage_cost",
        "total_statutory_cost",
        "total_broker_cost",
        "total_slippage_cost",
        "total_transaction_cost",
    ]
    return sum(decimal(row[field]) < 0 for row in rows for field in fields)


def classify_cost_materiality(summary: Mapping[str, Any]) -> str:
    total_cost = decimal(summary["total_transaction_cost"])
    gross_pnl = abs(decimal(summary["gross_pnl"]))
    flip_rate = percent(
        decimal(summary["gross_positive_to_net_negative_count"]),
        decimal(summary["gross_positive_trade_count"]),
    )
    if total_cost >= gross_pnl or flip_rate >= Decimal("20"):
        return "VERY_HIGH"
    if total_cost >= gross_pnl * Decimal("0.5") or flip_rate >= Decimal("10"):
        return "HIGH"
    if total_cost >= gross_pnl * Decimal("0.2") or flip_rate >= Decimal("5"):
        return "MODERATE"
    return "LOW"


def cagr_pct(starting: Decimal, ending: Decimal, start_date: Any, end_date: Any) -> Decimal | None:
    if starting <= 0 or ending <= 0:
        return None
    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))
    years = Decimal((end - start).days) / Decimal("365.25")
    if years <= 0:
        return None
    value = (math.pow(float(ending / starting), float(Decimal("1") / years)) - 1) * 100
    return Decimal(str(value))


def maximum_drawdown_pct(values: Sequence[Decimal]) -> Decimal:
    peak: Decimal | None = None
    maximum = Decimal("0")
    for value in values:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            maximum = max(maximum, (peak - value) / peak * Decimal("100"))
    return maximum


def decimal(value: Any) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    return Decimal(str(value))


def integer(value: Any) -> int:
    return int(Decimal(str(value)))


def percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator * Decimal("100") if denominator else Decimal("0")


def mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / len(values) if values else Decimal("0")


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

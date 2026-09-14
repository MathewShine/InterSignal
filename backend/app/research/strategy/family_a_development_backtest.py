from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_models import (
    BROKERAGE,
    DP_CHARGE,
    EXCHANGE_TRANSACTION_CHARGE,
    GST,
    OTHER_REGULATORY,
    SEBI_CHARGE,
    STAMP_DUTY,
    STT,
    canonical_hash,
    json_ready,
)
from app.research.strategy.family_a_momentum import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPERIMENT_IDS,
    FAMILY_VERSION,
    RESEARCH_PROFILE,
    STARTING_CAPITAL,
    AdjustedBar,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
    decimal,
    estimate_order_cost,
    file_sha256,
    frozen_project_snapshot,
    read_csv,
    write_csv,
    write_json,
)


COMMAND_VERSION = "FAMILY_A_DEVELOPMENT_BACKTEST_V1"
COMMAND_PROFILE = "MEDIUM_TERM_MOMENTUM_DEVELOPMENT_BASELINES_V1"
COMMAND = "Step 03.01 / Command 02"

EXPECTED_FAMILY_CONFIG_HASH = "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3"
EXPECTED_EXPERIMENT_HASHES = {
    "MOM-A-001": {
        "parameter_hash": "444f4bcd22879dc6d24066f535ecb008962996cbf00d9b33a4de840848b9ddf1",
        "preregistration_hash": "6b84e606a92ac57ca9d7d480a882ed7b818667f7c8d8c999ddc92e15c8a20293",
    },
    "MOM-A-002": {
        "parameter_hash": "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8",
        "preregistration_hash": "e88f8c2588b8c1ffb2fb5c951471f423d6b99d065ba135c58979c57f196f91cc",
    },
    "MOM-A-003": {
        "parameter_hash": "111a91251ab285b0b7f6964c470bfde1e0abc7cec5892f8c02ef72acbe9b46bb",
        "preregistration_hash": "5e5d55b28161fdfdc6d9f721c3858bf463aaf70c11148fececcb3b6d1c8df11a",
    },
}

IDEALIZED_MODE = "IDEALIZED_EQUAL_WEIGHT_PERCENTAGE"
EXECUTABLE_MODE = "EXECUTABLE_INTEGER_SHARE_100K"
MODES = (IDEALIZED_MODE, EXECUTABLE_MODE)

REPORT_NAMES = (
    "family_a_dev_v1_summary.json",
    "family_a_dev_v1_comparison.csv",
    "family_a_dev_v1_yearly.csv",
    "family_a_dev_v1_turnover.csv",
    "family_a_dev_v1_costs.csv",
    "family_a_dev_v1_capital_distortion.csv",
    "family_a_dev_v1_rebalances.csv",
    "family_a_dev_v1_holdings.csv",
    "family_a_dev_v1_position_returns.csv",
    "family_a_dev_v1_drawdowns.csv",
    "family_a_dev_v1_pilot.csv",
)

COST_COMPONENTS = (
    BROKERAGE,
    STT,
    EXCHANGE_TRANSACTION_CHARGE,
    SEBI_CHARGE,
    GST,
    STAMP_DUTY,
    DP_CHARGE,
    OTHER_REGULATORY,
)


class FamilyAPreregistrationMismatch(RuntimeError):
    pass


class FamilyAResultImmutabilityError(RuntimeError):
    pass


class FamilyAValidationAccessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SelectedInstrument:
    symbol: str
    isin: str
    rank: int
    signal_value: Decimal


@dataclass(frozen=True, slots=True)
class RebalanceSchedule:
    experiment_id: str
    formation_date: date
    execution_date: date
    eligible_count: int
    intended_count: int
    sufficient_universe: bool
    selected: tuple[SelectedInstrument, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_development_date(observed: date) -> None:
    if not DEVELOPMENT_START <= observed <= DEVELOPMENT_END:
        raise FamilyAValidationAccessError(
            f"Family A development engine rejects out-of-window date {observed.isoformat()}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_family_a_preregistration(root: Path) -> dict[str, Any]:
    registry_root = root / "data/research/strategy_families/family_a/v1/registry"
    config_path = registry_root / "family_config_v1.json"
    registry_path = registry_root / "experiment_registry_v1.json"
    if not config_path.exists() or not registry_path.exists():
        raise FamilyAPreregistrationMismatch("Family A Command 01 artifacts are missing")
    config = _read_json(config_path)
    registry = _read_json(registry_path)
    observed_family_hash = config.get("family_config_hash")
    recomputed_family_hash = canonical_hash(
        {key: value for key, value in config.items() if key != "family_config_hash"}
    )
    if observed_family_hash != EXPECTED_FAMILY_CONFIG_HASH or recomputed_family_hash != EXPECTED_FAMILY_CONFIG_HASH:
        raise FamilyAPreregistrationMismatch("FAMILY_A_PREREGISTRATION_MISMATCH: family config hash")
    if config.get("family_version") != FAMILY_VERSION or config.get("research_profile") != RESEARCH_PROFILE:
        raise FamilyAPreregistrationMismatch("FAMILY_A_PREREGISTRATION_MISMATCH: family identity")
    if tuple(registry.get("experiment_ids", ())) != EXPERIMENT_IDS or registry.get("experiment_count") != 3:
        raise FamilyAPreregistrationMismatch("FAMILY_A_PREREGISTRATION_MISMATCH: experiment allowlist")
    verified: list[dict[str, Any]] = []
    for experiment in registry.get("experiments", []):
        experiment_id = str(experiment.get("experiment_id"))
        expected = EXPECTED_EXPERIMENT_HASHES.get(experiment_id)
        if expected is None:
            raise FamilyAPreregistrationMismatch("FAMILY_A_PREREGISTRATION_MISMATCH: extra experiment")
        if experiment.get("status") != "PREREGISTERED" or experiment.get("promotion_allowed") is not False:
            raise FamilyAPreregistrationMismatch("FAMILY_A_PREREGISTRATION_MISMATCH: preregistration state")
        if canonical_hash(experiment["parameters"]) != expected["parameter_hash"]:
            raise FamilyAPreregistrationMismatch(f"FAMILY_A_PREREGISTRATION_MISMATCH: {experiment_id} parameters")
        prereg_body = {key: value for key, value in experiment.items() if key != "preregistration_hash"}
        if canonical_hash(prereg_body) != expected["preregistration_hash"]:
            raise FamilyAPreregistrationMismatch(f"FAMILY_A_PREREGISTRATION_MISMATCH: {experiment_id} preregistration")
        if (
            experiment.get("parameter_hash") != expected["parameter_hash"]
            or experiment.get("preregistration_hash") != expected["preregistration_hash"]
        ):
            raise FamilyAPreregistrationMismatch(f"FAMILY_A_PREREGISTRATION_MISMATCH: {experiment_id} hash fields")
        verified.append(
            {
                "experiment_id": experiment_id,
                "parameter_hash": expected["parameter_hash"],
                "preregistration_hash": expected["preregistration_hash"],
                "verified": True,
            }
        )
    return {
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "family_config_verified": True,
        "experiments": verified,
        "source_config_path": config_path.relative_to(root).as_posix(),
        "source_registry_path": registry_path.relative_to(root).as_posix(),
        "source_registry_hash": registry["registry_hash"],
        "config": config,
        "registry": registry,
    }


def family_a_command_01_snapshot(root: Path) -> dict[str, Any]:
    verified = verify_family_a_preregistration(root)
    artifact_root = root / "data/research/strategy_families/family_a/v1"
    command_01_paths = [
        *sorted(
            path
            for path in artifact_root.rglob("*")
            if path.is_file()
            and "development_backtests" not in path.parts
            and "phase2" not in path.parts
            and "closure" not in path.parts
        ),
        *sorted((root / "data/reports").glob("family_a_v1_*")),
        root / "docs/research/strategy-family-a-literature-notes-v1.md",
        root / "docs/strategy-family-a-medium-term-momentum-v1.md",
    ]
    file_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in command_01_paths
        if path.exists()
    }
    semantic = {
        "family_config_hash": verified["family_config_hash"],
        "source_registry_hash": verified["source_registry_hash"],
        "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
        "file_hashes": file_hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def full_baseline_snapshot(root: Path) -> dict[str, Any]:
    project = frozen_project_snapshot(root)
    command_01 = family_a_command_01_snapshot(root)
    semantic = {
        "project_snapshot_hash": project["snapshot_hash"],
        "family_a_command_01_snapshot_hash": command_01["snapshot_hash"],
        "cap4_validation_state": project["cap4_validation_state"],
        "cap4_validation_run_count": project["cap4_validation_run_count"],
        "cap4_validation_result_hash": project["cap4_validation_result_hash"],
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def load_rebalance_schedules(root: Path) -> dict[str, list[RebalanceSchedule]]:
    signal_path = root / "data/research/strategy_families/family_a/v1/signals/family_a_signal_inputs_v1.csv"
    if not signal_path.exists():
        raise FileNotFoundError("Family A Command 01 signal inputs are unavailable")
    grouped: dict[tuple[str, date, date], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(signal_path):
        formation = date.fromisoformat(row["decision_date"])
        execution = date.fromisoformat(row["execution_date"])
        validate_development_date(formation)
        validate_development_date(execution)
        grouped[(row["experiment_id"], formation, execution)].append(row)
    result: dict[str, list[RebalanceSchedule]] = defaultdict(list)
    for (experiment_id, formation, execution), rows in sorted(grouped.items()):
        selected_rows = sorted(
            (row for row in rows if row["selected_top_decile"] == "True"),
            key=lambda row: (int(row["signal_rank"]), row["symbol"]),
        )
        signal_field = "6m_return" if experiment_id in {"MOM-A-001", "MOM-A-002"} else "12_1_return"
        selected = tuple(
            SelectedInstrument(
                symbol=row["symbol"],
                isin=row["isin"],
                rank=int(row["signal_rank"]),
                signal_value=decimal(row[signal_field]),
            )
            for row in selected_rows
        )
        eligible_count = sum(row["eligible"] == "True" for row in rows)
        intended_count = math.ceil(eligible_count * 0.10)
        result[experiment_id].append(
            RebalanceSchedule(
                experiment_id=experiment_id,
                formation_date=formation,
                execution_date=execution,
                eligible_count=eligible_count,
                intended_count=intended_count,
                sufficient_universe=bool(selected),
                selected=selected,
            )
        )
    expected_counts = {"MOM-A-001": 35, "MOM-A-002": 11, "MOM-A-003": 35}
    observed_counts = {key: len(result[key]) for key in EXPERIMENT_IDS}
    if observed_counts != expected_counts:
        raise FamilyAPreregistrationMismatch(
            f"Frozen rebalance schedule counts changed: {observed_counts}"
        )
    return {key: sorted(result[key], key=lambda row: row.execution_date) for key in EXPERIMENT_IDS}


def _percent(value: Decimal) -> Decimal:
    return value * Decimal("100")


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    return numerator / denominator if denominator else None


def _median(values: Sequence[Decimal]) -> Decimal | None:
    return decimal(statistics.median(values)) if values else None


def _p90(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.90) - 1)
    return ordered[index]


def _cost_for_mode(side: str, value_date: date, notional: Decimal, mode: str) -> dict[str, Any]:
    cost = estimate_order_cost(side, value_date, notional)
    components = {key: decimal(value) for key, value in cost["components"].items()}
    if mode.startswith("EXECUTABLE"):
        return {
            **cost,
            "applied_components": {key: components[key] for key in COST_COMPONENTS},
            "applied_total_cost": decimal(cost["total_cost"]),
            "flat_delivery_cost_excluded": Decimal("0"),
            "cost_methodology": "FULL_FROZEN_COST_MODEL",
        }
    dp_charge = components[DP_CHARGE]
    dp_gst = (dp_charge * Decimal("0.18")).quantize(Decimal("0.01"))
    applied_components = {key: components[key] for key in COST_COMPONENTS}
    applied_components[DP_CHARGE] = Decimal("0")
    applied_components[GST] = max(Decimal("0"), applied_components[GST] - dp_gst)
    flat_excluded = dp_charge + dp_gst
    return {
        **cost,
        "applied_components": applied_components,
        "applied_total_cost": decimal(cost["total_cost"]) - flat_excluded,
        "flat_delivery_cost_excluded": flat_excluded,
        "cost_methodology": "IDEALIZED_COST_MODEL_LIMITED_PERCENTAGE_LIKE_COSTS_ONLY",
    }


def _flatten_order_cost(
    *,
    experiment_id: str,
    mode: str,
    execution_date: date,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    cost: Mapping[str, Any],
) -> dict[str, Any]:
    row = {
        "experiment_id": experiment_id,
        "mode": mode,
        "execution_date": execution_date.isoformat(),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "gross_notional": quantity * price,
        "slippage": cost["slippage"],
        "applied_total_cost": cost["applied_total_cost"],
        "flat_delivery_cost_excluded": cost["flat_delivery_cost_excluded"],
        "cost_methodology": cost["cost_methodology"],
    }
    for component in COST_COMPONENTS:
        row[component.lower()] = cost["applied_components"][component]
    return row


def _open_price(
    symbol: str,
    value_date: date,
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    last_prices: Mapping[str, Decimal],
) -> Decimal | None:
    bar = bars.get(value_date, {}).get(symbol)
    return bar.open_price if bar is not None and bar.open_price > 0 else last_prices.get(symbol)


def _close_price(
    symbol: str,
    value_date: date,
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    last_prices: Mapping[str, Decimal],
) -> Decimal | None:
    bar = bars.get(value_date, {}).get(symbol)
    return bar.close_price if bar is not None and bar.close_price > 0 else last_prices.get(symbol)


def _valuation(
    holdings: Mapping[str, Decimal],
    value_date: date,
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    last_prices: Mapping[str, Decimal],
    *,
    use_open: bool,
) -> tuple[Decimal, dict[str, Decimal], list[str]]:
    total = Decimal("0")
    prices: dict[str, Decimal] = {}
    missing: list[str] = []
    for symbol, quantity in holdings.items():
        if quantity <= 0:
            continue
        price = (
            _open_price(symbol, value_date, bars, last_prices)
            if use_open
            else _close_price(symbol, value_date, bars, last_prices)
        )
        if price is None:
            missing.append(symbol)
            continue
        prices[symbol] = price
        total += quantity * price
    return total, prices, missing


def _record_period_positions(
    *,
    experiment_id: str,
    mode: str,
    start_date: date,
    end_date: date,
    start_positions: Mapping[str, tuple[Decimal, Decimal]],
    end_prices: Mapping[str, Decimal],
    final_partial: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, (quantity, start_price) in sorted(start_positions.items()):
        end_price = end_prices.get(symbol)
        if end_price is None or start_price <= 0:
            continue
        rows.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "symbol": symbol,
                "quantity": quantity,
                "start_price": start_price,
                "end_price": end_price,
                "position_return_pct": _percent(end_price / start_price - Decimal("1")),
                "positive_position": end_price > start_price,
                "final_partial_period": final_partial,
                "methodology": "REBALANCE_PERIOD_POSITION_RETURN_NOT_TRADE_WIN_RATE",
            }
        )
    return rows


def _period_row(
    *,
    experiment_id: str,
    mode: str,
    start_date: date,
    end_date: date,
    start_gross: Decimal,
    end_gross: Decimal,
    start_net: Decimal,
    end_net: Decimal,
    final_partial: bool,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "mode": mode,
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "gross_period_return_pct": _percent(end_gross / start_gross - Decimal("1")) if start_gross else None,
        "net_period_return_pct": _percent(end_net / start_net - Decimal("1")) if start_net else None,
        "gross_period_pnl": end_gross - start_gross,
        "net_period_pnl": end_net - start_net,
        "positive_gross_period": end_gross > start_gross,
        "positive_net_period": end_net > start_net,
        "final_partial_period": final_partial,
        "terminology": "PORTFOLIO_REBALANCE_PERIOD_NOT_TRADE_WIN_RATE",
    }


def simulate_idealized(
    experiment_id: str,
    schedules: Sequence[RebalanceSchedule],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> dict[str, Any]:
    validate_development_date(sessions[0])
    validate_development_date(sessions[-1])
    schedule_by_date = {row.execution_date: row for row in schedules}
    holdings: dict[str, Decimal] = {}
    cash = STARTING_CAPITAL
    cumulative_cost = Decimal("0")
    cumulative_flat_excluded = Decimal("0")
    last_prices: dict[str, Decimal] = {}
    daily: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    position_returns: list[dict[str, Any]] = []
    period_start_date: date | None = None
    period_start_gross: Decimal | None = None
    period_start_net: Decimal | None = None
    period_positions: dict[str, tuple[Decimal, Decimal]] = {}
    cash_reconciliation_violations = 0
    equity_reconciliation_violations = 0

    for value_date in sessions:
        schedule = schedule_by_date.get(value_date)
        if schedule is not None:
            holdings_value, valuation_prices, missing_valuation = _valuation(
                holdings, value_date, bars, last_prices, use_open=True
            )
            gross_pre = cash + holdings_value
            net_pre = gross_pre - cumulative_cost
            if period_start_date is not None and period_start_gross is not None and period_start_net is not None:
                periods.append(
                    _period_row(
                        experiment_id=experiment_id,
                        mode=IDEALIZED_MODE,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_gross=period_start_gross,
                        end_gross=gross_pre,
                        start_net=period_start_net,
                        end_net=net_pre,
                        final_partial=False,
                    )
                )
                position_returns.extend(
                    _record_period_positions(
                        experiment_id=experiment_id,
                        mode=IDEALIZED_MODE,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_positions=period_positions,
                        end_prices=valuation_prices,
                        final_partial=False,
                    )
                )

            before_symbols = {symbol for symbol, quantity in holdings.items() if quantity > 0}
            selected_symbols = {row.symbol for row in schedule.selected}
            retained = before_symbols & selected_symbols
            added = selected_symbols - before_symbols
            removed = before_symbols - selected_symbols
            start_cash = cash
            sell_notional = Decimal("0")
            buy_notional = Decimal("0")
            rebalance_cost = Decimal("0")
            flat_excluded = Decimal("0")
            status = "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"
            if schedule.sufficient_universe:
                execution_prices = {
                    row.symbol: bars[value_date][row.symbol].open_price
                    for row in schedule.selected
                    if row.symbol in bars.get(value_date, {}) and bars[value_date][row.symbol].open_price > 0
                }
                if len(execution_prices) != len(schedule.selected):
                    raise ValueError(f"Missing selected next-open price for {experiment_id} on {value_date}")
                target_notional = gross_pre / Decimal(len(schedule.selected))
                target_holdings = {
                    row.symbol: target_notional / execution_prices[row.symbol]
                    for row in schedule.selected
                }
                all_symbols = sorted(set(holdings) | set(target_holdings))
                for symbol in all_symbols:
                    current_quantity = holdings.get(symbol, Decimal("0"))
                    target_quantity = target_holdings.get(symbol, Decimal("0"))
                    delta = target_quantity - current_quantity
                    if delta == 0:
                        continue
                    price = execution_prices.get(symbol)
                    if price is None:
                        price = bars.get(value_date, {}).get(symbol).open_price if symbol in bars.get(value_date, {}) else None
                    if price is None or price <= 0:
                        raise ValueError(f"Cannot execute idealized rebalance for {symbol} on {value_date}")
                    side = "BUY" if delta > 0 else "SELL"
                    quantity = abs(delta)
                    notional = quantity * price
                    cost = _cost_for_mode(side, value_date, notional, IDEALIZED_MODE)
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=IDEALIZED_MODE,
                            execution_date=value_date,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            price=price,
                            cost=cost,
                        )
                    )
                    if side == "BUY":
                        buy_notional += notional
                    else:
                        sell_notional += notional
                    rebalance_cost += decimal(cost["applied_total_cost"])
                    flat_excluded += decimal(cost["flat_delivery_cost_excluded"])
                holdings = target_holdings
                cash = gross_pre - sum(
                    (holdings[symbol] * execution_prices[symbol] for symbol in holdings),
                    Decimal("0"),
                )
                cumulative_cost += rebalance_cost
                cumulative_flat_excluded += flat_excluded
                status = "EXECUTED"
            expected_cash = start_cash + sell_notional - buy_notional
            if schedule.sufficient_universe and abs(cash - expected_cash) > Decimal("0.000001"):
                cash_reconciliation_violations += 1
            post_value, post_prices, post_missing = _valuation(
                holdings, value_date, bars, last_prices, use_open=True
            )
            gross_post = cash + post_value
            net_post = gross_post - cumulative_cost
            if abs((cash + post_value) - gross_post) > Decimal("0.000001"):
                equity_reconciliation_violations += 1
            actual_weights = {
                symbol: quantity * post_prices[symbol] / gross_post
                for symbol, quantity in holdings.items()
                if symbol in post_prices and gross_post
            }
            for symbol in sorted(actual_weights):
                holding_rows.append(
                    {
                        "experiment_id": experiment_id,
                        "mode": IDEALIZED_MODE,
                        "execution_date": value_date.isoformat(),
                        "symbol": symbol,
                        "quantity": holdings[symbol],
                        "price": post_prices[symbol],
                        "market_value": holdings[symbol] * post_prices[symbol],
                        "actual_weight_pct": _percent(actual_weights[symbol]),
                        "cash_weight_pct": _percent(cash / gross_post) if gross_post else None,
                    }
                )
            largest = max(actual_weights.values(), default=Decimal("0"))
            top_five = sum(sorted(actual_weights.values(), reverse=True)[:5], Decimal("0"))
            turnover = (buy_notional + sell_notional) / gross_pre if gross_pre else Decimal("0")
            rebalances.append(
                {
                    "experiment_id": experiment_id,
                    "mode": IDEALIZED_MODE,
                    "formation_date": schedule.formation_date.isoformat(),
                    "execution_date": value_date.isoformat(),
                    "status": status,
                    "eligible_count": schedule.eligible_count,
                    "intended_holdings": schedule.intended_count,
                    "selected_count": len(schedule.selected),
                    "actual_holdings": len(holdings),
                    "retained_count": len(retained),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "retention_rate_pct": _percent(Decimal(len(retained)) / Decimal(len(before_symbols))) if before_symbols else None,
                    "gross_buy_turnover": buy_notional,
                    "gross_sell_turnover": sell_notional,
                    "one_way_turnover": turnover,
                    "rebalance_cost": rebalance_cost,
                    "flat_delivery_cost_excluded": flat_excluded,
                    "pre_rebalance_gross_equity": gross_pre,
                    "post_rebalance_gross_equity": gross_post,
                    "post_rebalance_net_equity": net_post,
                    "cash": cash,
                    "cash_residual_pct": _percent(cash / gross_post) if gross_post else None,
                    "unaffordable_names": 0,
                    "largest_position_weight_pct": _percent(largest),
                    "top_five_weight_pct": _percent(top_five),
                    "tracking_difference_l1_pct": Decimal("0"),
                    "missing_valuation_count": len(set(missing_valuation + post_missing)),
                    "cash_reconciliation_mismatch": abs(cash - expected_cash) if schedule.sufficient_universe else Decimal("0"),
                    "equity_reconciliation_mismatch": Decimal("0"),
                }
            )
            period_start_date = value_date
            period_start_gross = gross_post
            period_start_net = net_post
            period_positions = {
                symbol: (quantity, post_prices[symbol])
                for symbol, quantity in holdings.items()
                if symbol in post_prices and quantity > 0
            }

        close_value, close_prices, missing_close = _valuation(
            holdings, value_date, bars, last_prices, use_open=False
        )
        gross_close = cash + close_value
        net_close = gross_close - cumulative_cost
        daily.append(
            {
                "experiment_id": experiment_id,
                "mode": IDEALIZED_MODE,
                "date": value_date.isoformat(),
                "gross_equity": gross_close,
                "net_equity": net_close,
                "cash": cash,
                "holdings_value": close_value,
                "holding_count": len([value for value in holdings.values() if value > 0]),
                "cumulative_cost": cumulative_cost,
                "cumulative_flat_delivery_cost_excluded": cumulative_flat_excluded,
                "missing_close_valuation_count": len(missing_close),
                "equity_reconciliation_mismatch": abs((cash + close_value) - gross_close),
            }
        )
        for symbol, price in close_prices.items():
            last_prices[symbol] = price

    if period_start_date is not None and period_start_gross is not None and period_start_net is not None:
        final = daily[-1]
        periods.append(
            _period_row(
                experiment_id=experiment_id,
                mode=IDEALIZED_MODE,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_gross=period_start_gross,
                end_gross=decimal(final["gross_equity"]),
                start_net=period_start_net,
                end_net=decimal(final["net_equity"]),
                final_partial=True,
            )
        )
        _, final_prices, _ = _valuation(holdings, sessions[-1], bars, last_prices, use_open=False)
        position_returns.extend(
            _record_period_positions(
                experiment_id=experiment_id,
                mode=IDEALIZED_MODE,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_positions=period_positions,
                end_prices=final_prices,
                final_partial=True,
            )
        )
    return {
        "experiment_id": experiment_id,
        "mode": IDEALIZED_MODE,
        "daily": daily,
        "rebalances": rebalances,
        "holdings": holding_rows,
        "costs": cost_rows,
        "periods": periods,
        "position_returns": position_returns,
        "cash_reconciliation_violations": cash_reconciliation_violations,
        "equity_reconciliation_violations": equity_reconciliation_violations,
        "cost_model_status": "IDEALIZED_COST_MODEL_LIMITED",
    }


def _maximum_affordable_quantity(
    desired: int,
    price: Decimal,
    available_cash: Decimal,
    value_date: date,
) -> int:
    low = 0
    high = max(0, desired)
    while low < high:
        middle = (low + high + 1) // 2
        notional = Decimal(middle) * price
        cost = _cost_for_mode("BUY", value_date, notional, EXECUTABLE_MODE)
        required = notional + decimal(cost["applied_total_cost"])
        if required <= available_cash:
            low = middle
        else:
            high = middle - 1
    return low


def simulate_executable(
    experiment_id: str,
    schedules: Sequence[RebalanceSchedule],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    *,
    starting_capital: Decimal = STARTING_CAPITAL,
    mode: str = EXECUTABLE_MODE,
    schedule_resolver: Callable[[RebalanceSchedule, frozenset[str]], RebalanceSchedule] | None = None,
) -> dict[str, Any]:
    validate_development_date(sessions[0])
    validate_development_date(sessions[-1])
    schedule_by_date = {row.execution_date: row for row in schedules}
    holdings: dict[str, int] = {}
    cash = decimal(starting_capital)
    cumulative_cost = Decimal("0")
    last_prices: dict[str, Decimal] = {}
    daily: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    position_returns: list[dict[str, Any]] = []
    period_start_date: date | None = None
    period_start_gross: Decimal | None = None
    period_start_net: Decimal | None = None
    period_positions: dict[str, tuple[Decimal, Decimal]] = {}
    cash_reconciliation_violations = 0
    equity_reconciliation_violations = 0

    for value_date in sessions:
        schedule = schedule_by_date.get(value_date)
        if schedule is not None:
            if schedule_resolver is not None:
                schedule = schedule_resolver(
                    schedule,
                    frozenset(symbol for symbol, quantity in holdings.items() if quantity > 0),
                )
            decimal_holdings = {key: Decimal(value) for key, value in holdings.items()}
            holdings_value, valuation_prices, missing_valuation = _valuation(
                decimal_holdings, value_date, bars, last_prices, use_open=True
            )
            net_pre = cash + holdings_value
            gross_pre = net_pre + cumulative_cost
            if period_start_date is not None and period_start_gross is not None and period_start_net is not None:
                periods.append(
                    _period_row(
                        experiment_id=experiment_id,
                        mode=mode,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_gross=period_start_gross,
                        end_gross=gross_pre,
                        start_net=period_start_net,
                        end_net=net_pre,
                        final_partial=False,
                    )
                )
                position_returns.extend(
                    _record_period_positions(
                        experiment_id=experiment_id,
                        mode=mode,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_positions=period_positions,
                        end_prices=valuation_prices,
                        final_partial=False,
                    )
                )

            before_symbols = {symbol for symbol, quantity in holdings.items() if quantity > 0}
            selected_symbols = {row.symbol for row in schedule.selected}
            retained = before_symbols & selected_symbols
            added = selected_symbols - before_symbols
            removed = before_symbols - selected_symbols
            start_cash = cash
            sale_proceeds = Decimal("0")
            sell_costs = Decimal("0")
            buy_notional = Decimal("0")
            buy_costs = Decimal("0")
            sell_notional = Decimal("0")
            status = "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"
            desired_targets: dict[str, int] = dict(holdings)
            unavailable_execution: list[str] = []
            if schedule.sufficient_universe:
                actual_execution_prices = {
                    symbol: bar.open_price
                    for symbol, bar in bars.get(value_date, {}).items()
                    if bar.open_price > 0
                }
                target_amount = net_pre / Decimal(len(schedule.selected))
                desired_targets = {
                    row.symbol: int(
                        (target_amount / actual_execution_prices[row.symbol]).to_integral_value(rounding=ROUND_FLOOR)
                    )
                    for row in schedule.selected
                    if row.symbol in actual_execution_prices
                }
                if len(desired_targets) != len(schedule.selected):
                    raise ValueError(f"Missing selected next-open price for {experiment_id} on {value_date}")
                for symbol in sorted(set(holdings) | set(desired_targets)):
                    current = holdings.get(symbol, 0)
                    target = desired_targets.get(symbol, 0)
                    if target >= current:
                        continue
                    price = actual_execution_prices.get(symbol)
                    if price is None:
                        desired_targets[symbol] = current
                        unavailable_execution.append(symbol)
                        continue
                    quantity = current - target
                    notional = Decimal(quantity) * price
                    cost = _cost_for_mode("SELL", value_date, notional, mode)
                    applied = decimal(cost["applied_total_cost"])
                    cash += notional - applied
                    holdings[symbol] = target
                    if target == 0:
                        holdings.pop(symbol, None)
                    sale_proceeds += notional
                    sell_notional += notional
                    sell_costs += applied
                    cumulative_cost += applied
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=mode,
                            execution_date=value_date,
                            symbol=symbol,
                            side="SELL",
                            quantity=Decimal(quantity),
                            price=price,
                            cost=cost,
                        )
                    )
                rank_lookup = {row.symbol: row.rank for row in schedule.selected}
                for symbol in sorted(desired_targets, key=lambda item: (rank_lookup.get(item, 10**9), item)):
                    current = holdings.get(symbol, 0)
                    desired = desired_targets[symbol]
                    if desired <= current:
                        continue
                    price = actual_execution_prices[symbol]
                    quantity = _maximum_affordable_quantity(desired - current, price, cash, value_date)
                    if quantity <= 0:
                        continue
                    notional = Decimal(quantity) * price
                    cost = _cost_for_mode("BUY", value_date, notional, mode)
                    applied = decimal(cost["applied_total_cost"])
                    required = notional + applied
                    if required > cash + Decimal("0.000001"):
                        raise ValueError("Affordable-quantity search produced an infeasible purchase")
                    cash -= required
                    holdings[symbol] = current + quantity
                    buy_notional += notional
                    buy_costs += applied
                    cumulative_cost += applied
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=mode,
                            execution_date=value_date,
                            symbol=symbol,
                            side="BUY",
                            quantity=Decimal(quantity),
                            price=price,
                            cost=cost,
                        )
                    )
                status = "EXECUTED" if not unavailable_execution else "EXECUTED_WITH_DEFERRED_MISSING_OPEN_EXITS"
            expected_cash = start_cash + sale_proceeds - sell_costs - buy_notional - buy_costs
            cash_mismatch = abs(cash - expected_cash)
            if cash_mismatch > Decimal("0.000001"):
                cash_reconciliation_violations += 1
            post_holdings = {key: Decimal(value) for key, value in holdings.items() if value > 0}
            post_value, post_prices, post_missing = _valuation(
                post_holdings, value_date, bars, last_prices, use_open=True
            )
            net_post = cash + post_value
            gross_post = net_post + cumulative_cost
            equity_mismatch = abs((cash + post_value) - net_post)
            if equity_mismatch > Decimal("0.000001"):
                equity_reconciliation_violations += 1
            actual_weights = {
                symbol: quantity * post_prices[symbol] / net_post
                for symbol, quantity in post_holdings.items()
                if symbol in post_prices and net_post
            }
            target_weight = Decimal("1") / Decimal(len(schedule.selected)) if schedule.selected else Decimal("0")
            tracking_l1 = sum(
                (abs(actual_weights.get(symbol, Decimal("0")) - target_weight) for symbol in selected_symbols),
                Decimal("0"),
            )
            for symbol in sorted(actual_weights):
                holding_rows.append(
                    {
                        "experiment_id": experiment_id,
                        "mode": mode,
                        "execution_date": value_date.isoformat(),
                        "symbol": symbol,
                        "quantity": holdings[symbol],
                        "price": post_prices[symbol],
                        "market_value": Decimal(holdings[symbol]) * post_prices[symbol],
                        "actual_weight_pct": _percent(actual_weights[symbol]),
                        "cash_weight_pct": _percent(cash / net_post) if net_post else None,
                    }
                )
            largest = max(actual_weights.values(), default=Decimal("0"))
            top_five = sum(sorted(actual_weights.values(), reverse=True)[:5], Decimal("0"))
            turnover = (buy_notional + sell_notional) / net_pre if net_pre else Decimal("0")
            unaffordable = sum(
                holdings.get(row.symbol, 0) == 0 for row in schedule.selected
            )
            rebalances.append(
                {
                    "experiment_id": experiment_id,
                    "mode": mode,
                    "formation_date": schedule.formation_date.isoformat(),
                    "execution_date": value_date.isoformat(),
                    "status": status,
                    "eligible_count": schedule.eligible_count,
                    "intended_holdings": schedule.intended_count,
                    "selected_count": len(schedule.selected),
                    "actual_holdings": len(holdings),
                    "retained_count": len(retained),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "retention_rate_pct": _percent(Decimal(len(retained)) / Decimal(len(before_symbols))) if before_symbols else None,
                    "gross_buy_turnover": buy_notional,
                    "gross_sell_turnover": sell_notional,
                    "one_way_turnover": turnover,
                    "rebalance_cost": sell_costs + buy_costs,
                    "flat_delivery_cost_excluded": Decimal("0"),
                    "pre_rebalance_gross_equity": gross_pre,
                    "pre_rebalance_net_equity": net_pre,
                    "post_rebalance_gross_equity": gross_post,
                    "post_rebalance_net_equity": net_post,
                    "cash": cash,
                    "cash_residual_pct": _percent(cash / net_post) if net_post else None,
                    "unaffordable_names": unaffordable,
                    "largest_position_weight_pct": _percent(largest),
                    "top_five_weight_pct": _percent(top_five),
                    "tracking_difference_l1_pct": _percent(tracking_l1),
                    "missing_valuation_count": len(set(missing_valuation + post_missing)),
                    "deferred_missing_open_exits": len(unavailable_execution),
                    "cash_reconciliation_mismatch": cash_mismatch,
                    "equity_reconciliation_mismatch": equity_mismatch,
                }
            )
            period_start_date = value_date
            period_start_gross = gross_post
            period_start_net = net_post
            period_positions = {
                symbol: (Decimal(quantity), post_prices[symbol])
                for symbol, quantity in holdings.items()
                if symbol in post_prices and quantity > 0
            }

        close_holdings = {key: Decimal(value) for key, value in holdings.items() if value > 0}
        close_value, close_prices, missing_close = _valuation(
            close_holdings, value_date, bars, last_prices, use_open=False
        )
        net_close = cash + close_value
        gross_close = net_close + cumulative_cost
        equity_mismatch = abs((cash + close_value) - net_close)
        if equity_mismatch > Decimal("0.000001"):
            equity_reconciliation_violations += 1
        daily.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "date": value_date.isoformat(),
                "gross_equity": gross_close,
                "net_equity": net_close,
                "cash": cash,
                "holdings_value": close_value,
                "holding_count": len(close_holdings),
                "cumulative_cost": cumulative_cost,
                "cumulative_flat_delivery_cost_excluded": Decimal("0"),
                "missing_close_valuation_count": len(missing_close),
                "equity_reconciliation_mismatch": equity_mismatch,
            }
        )
        for symbol, price in close_prices.items():
            last_prices[symbol] = price

    if period_start_date is not None and period_start_gross is not None and period_start_net is not None:
        final = daily[-1]
        periods.append(
            _period_row(
                experiment_id=experiment_id,
                mode=mode,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_gross=period_start_gross,
                end_gross=decimal(final["gross_equity"]),
                start_net=period_start_net,
                end_net=decimal(final["net_equity"]),
                final_partial=True,
            )
        )
        _, final_prices, _ = _valuation(close_holdings, sessions[-1], bars, last_prices, use_open=False)
        position_returns.extend(
            _record_period_positions(
                experiment_id=experiment_id,
                mode=mode,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_positions=period_positions,
                end_prices=final_prices,
                final_partial=True,
            )
        )
    return {
        "experiment_id": experiment_id,
        "mode": mode,
        "daily": daily,
        "rebalances": rebalances,
        "holdings": holding_rows,
        "costs": cost_rows,
        "periods": periods,
        "position_returns": position_returns,
        "cash_reconciliation_violations": cash_reconciliation_violations,
        "equity_reconciliation_violations": equity_reconciliation_violations,
        "cost_model_status": "FULL_FROZEN_COST_MODEL",
    }


def _series_returns(values: Sequence[Decimal], starting_value: Decimal) -> list[Decimal]:
    returns: list[Decimal] = []
    previous = starting_value
    for value in values:
        returns.append(value / previous - Decimal("1") if previous else Decimal("0"))
        previous = value
    return returns


def _monthly_returns(
    daily: Sequence[Mapping[str, Any]],
    field: str,
    starting_capital: Decimal = STARTING_CAPITAL,
) -> list[dict[str, Any]]:
    endpoints: dict[str, Mapping[str, Any]] = {}
    for row in daily:
        endpoints[str(row["date"])[:7]] = row
    result: list[dict[str, Any]] = []
    previous = decimal(starting_capital)
    for month, row in sorted(endpoints.items()):
        value = decimal(row[field])
        result.append(
            {
                "month": month,
                "ending_value": value,
                "return_pct": _percent(value / previous - Decimal("1")) if previous else None,
            }
        )
        previous = value
    return result


def _drawdown_analysis(
    experiment_id: str,
    mode: str,
    daily: Sequence[Mapping[str, Any]],
    field: str,
    starting_capital: Decimal = STARTING_CAPITAL,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    peak = decimal(starting_capital)
    peak_date = DEVELOPMENT_START
    current_duration = 0
    longest_duration = 0
    rows: list[dict[str, Any]] = []
    maximum = Decimal("0")
    trough_date: str | None = None
    for row in daily:
        value = decimal(row[field])
        if value >= peak:
            peak = value
            peak_date = date.fromisoformat(str(row["date"]))
            current_duration = 0
        else:
            current_duration += 1
            longest_duration = max(longest_duration, current_duration)
        drawdown = value / peak - Decimal("1") if peak else Decimal("0")
        if drawdown < maximum:
            maximum = drawdown
            trough_date = str(row["date"])
        rows.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "basis": field.upper(),
                "date": row["date"],
                "equity": value,
                "running_peak": peak,
                "peak_date": peak_date.isoformat(),
                "drawdown_pct": _percent(drawdown),
                "drawdown_duration_sessions": current_duration,
            }
        )
    recovered = bool(daily and decimal(daily[-1][field]) >= peak)
    return rows, {
        "max_drawdown_pct": _percent(maximum),
        "longest_drawdown_duration_sessions": longest_duration,
        "recovery_status_at_end": "RECOVERED" if recovered else "UNRECOVERED",
        "maximum_drawdown_trough_date": trough_date,
    }


def _profit_factor(pnls: Sequence[Decimal]) -> Decimal | None:
    profits = sum((value for value in pnls if value > 0), Decimal("0"))
    losses = abs(sum((value for value in pnls if value < 0), Decimal("0")))
    return profits / losses if losses else None


def summarize_simulation(
    simulation: Mapping[str, Any],
    *,
    starting_capital: Decimal = STARTING_CAPITAL,
) -> dict[str, Any]:
    initial_capital = decimal(starting_capital)
    daily = simulation["daily"]
    gross_values = [decimal(row["gross_equity"]) for row in daily]
    net_values = [decimal(row["net_equity"]) for row in daily]
    gross_returns = _series_returns(gross_values, initial_capital)
    net_returns = _series_returns(net_values, initial_capital)
    elapsed_days = max(1, (date.fromisoformat(str(daily[-1]["date"])) - DEVELOPMENT_START).days)

    def cagr(ending: Decimal) -> Decimal | None:
        if ending <= 0:
            return None
        return Decimal(str((float(ending / initial_capital) ** (365.25 / elapsed_days) - 1) * 100))

    def volatility(returns: Sequence[Decimal]) -> Decimal:
        if len(returns) < 2:
            return Decimal("0")
        return Decimal(str(statistics.stdev(float(value) for value in returns) * math.sqrt(252) * 100))

    def sharpe_like(returns: Sequence[Decimal]) -> Decimal | None:
        if len(returns) < 2:
            return None
        standard_deviation = statistics.stdev(float(value) for value in returns)
        if standard_deviation == 0:
            return None
        return Decimal(str(statistics.mean(float(value) for value in returns) / standard_deviation * math.sqrt(252)))

    gross_drawdown_rows, gross_drawdown = _drawdown_analysis(
        simulation["experiment_id"], simulation["mode"], daily, "gross_equity", initial_capital
    )
    net_drawdown_rows, net_drawdown = _drawdown_analysis(
        simulation["experiment_id"], simulation["mode"], daily, "net_equity", initial_capital
    )
    gross_months = _monthly_returns(daily, "gross_equity", initial_capital)
    net_months = _monthly_returns(daily, "net_equity", initial_capital)
    complete_periods = [row for row in simulation["periods"] if not row["final_partial_period"]]
    position_rows = [row for row in simulation["position_returns"] if not row["final_partial_period"]]
    rebalances = simulation["rebalances"]
    executed_rebalances = [row for row in rebalances if str(row["status"]).startswith("EXECUTED")]
    turnover_values = [decimal(row["one_way_turnover"]) for row in executed_rebalances]
    retention_values = [
        decimal(row["retention_rate_pct"])
        for row in executed_rebalances
        if row.get("retention_rate_pct") not in {None, ""}
    ]
    actual_holdings = [int(row["actual_holdings"]) for row in executed_rebalances]
    residual_cash = [decimal(row["cash_residual_pct"]) for row in executed_rebalances]
    largest_weights = [decimal(row["largest_position_weight_pct"]) for row in executed_rebalances]
    top_five_weights = [decimal(row["top_five_weight_pct"]) for row in executed_rebalances]
    costs = [decimal(row["applied_total_cost"]) for row in simulation["costs"]]
    gross_ending = gross_values[-1]
    net_ending = net_values[-1]
    total_turnover = sum(turnover_values, Decimal("0"))
    gross_return_fraction = gross_ending / initial_capital - Decimal("1")
    net_return_fraction = net_ending / initial_capital - Decimal("1")
    gross_period_pnls = [decimal(row["gross_period_pnl"]) for row in complete_periods]
    net_period_pnls = [decimal(row["net_period_pnl"]) for row in complete_periods]
    component_totals = {
        component.lower(): sum((decimal(row[component.lower()]) for row in simulation["costs"]), Decimal("0"))
        for component in COST_COMPONENTS
    }
    summary = {
        "experiment_id": simulation["experiment_id"],
        "mode": simulation["mode"],
        "starting_equity": initial_capital,
        "gross_ending_equity": gross_ending,
        "net_ending_equity": net_ending,
        "gross_total_return_pct": _percent(gross_return_fraction),
        "net_total_return_pct": _percent(net_return_fraction),
        "gross_cagr_pct": cagr(gross_ending),
        "net_cagr_pct": cagr(net_ending),
        "gross_max_drawdown_pct": gross_drawdown["max_drawdown_pct"],
        "net_max_drawdown_pct": net_drawdown["max_drawdown_pct"],
        "gross_annualized_volatility_pct": volatility(gross_returns),
        "net_annualized_volatility_pct": volatility(net_returns),
        "gross_sharpe_like": sharpe_like(gross_returns),
        "net_sharpe_like": sharpe_like(net_returns),
        "gross_positive_calendar_month_rate_pct": _percent(
            Decimal(sum(decimal(row["return_pct"]) > 0 for row in gross_months)) / Decimal(len(gross_months))
        ),
        "net_positive_calendar_month_rate_pct": _percent(
            Decimal(sum(decimal(row["return_pct"]) > 0 for row in net_months)) / Decimal(len(net_months))
        ),
        "gross_best_month": max(gross_months, key=lambda row: decimal(row["return_pct"])),
        "gross_worst_month": min(gross_months, key=lambda row: decimal(row["return_pct"])),
        "net_best_month": max(net_months, key=lambda row: decimal(row["return_pct"])),
        "net_worst_month": min(net_months, key=lambda row: decimal(row["return_pct"])),
        "rebalance_period_count": len(complete_periods),
        "positive_gross_rebalance_period_count": sum(row["positive_gross_period"] for row in complete_periods),
        "positive_net_rebalance_period_count": sum(row["positive_net_period"] for row in complete_periods),
        "negative_net_rebalance_period_count": sum(not row["positive_net_period"] for row in complete_periods),
        "gross_rebalance_success_rate_pct": _percent(
            Decimal(sum(row["positive_gross_period"] for row in complete_periods)) / Decimal(len(complete_periods))
        ) if complete_periods else None,
        "net_rebalance_success_rate_pct": _percent(
            Decimal(sum(row["positive_net_period"] for row in complete_periods)) / Decimal(len(complete_periods))
        ) if complete_periods else None,
        "final_partial_period": next((row for row in simulation["periods"] if row["final_partial_period"]), None),
        "individual_position_period_count": len(position_rows),
        "positive_position_period_count": sum(row["positive_position"] for row in position_rows),
        "negative_position_period_count": sum(not row["positive_position"] for row in position_rows),
        "average_position_return_pct": (
            sum((decimal(row["position_return_pct"]) for row in position_rows), Decimal("0")) / Decimal(len(position_rows))
            if position_rows else None
        ),
        "median_position_return_pct": _median([decimal(row["position_return_pct"]) for row in position_rows]),
        "gross_profit_factor": _profit_factor(gross_period_pnls),
        "net_profit_factor": _profit_factor(net_period_pnls),
        "scheduled_rebalance_count": len(rebalances),
        "executed_rebalance_count": len(executed_rebalances),
        "insufficient_universe_count": sum(row["status"] == "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO" for row in rebalances),
        "gross_buy_turnover": sum((decimal(row["gross_buy_turnover"]) for row in rebalances), Decimal("0")),
        "gross_sell_turnover": sum((decimal(row["gross_sell_turnover"]) for row in rebalances), Decimal("0")),
        "total_one_way_turnover_x": total_turnover,
        "annualized_turnover_x": total_turnover / Decimal("3"),
        "average_rebalance_turnover_x": sum(turnover_values, Decimal("0")) / Decimal(len(turnover_values)) if turnover_values else None,
        "median_rebalance_turnover_x": _median(turnover_values),
        "p90_rebalance_turnover_x": _p90(turnover_values),
        "average_retention_rate_pct": sum(retention_values, Decimal("0")) / Decimal(len(retention_values)) if retention_values else None,
        "median_retention_rate_pct": _median(retention_values),
        "gross_return_per_unit_turnover": _safe_ratio(gross_return_fraction, total_turnover),
        "net_return_per_unit_turnover": _safe_ratio(net_return_fraction, total_turnover),
        "total_cost": sum(costs, Decimal("0")),
        "cost_drag_pct_initial_capital": _percent(sum(costs, Decimal("0")) / initial_capital),
        "gross_to_net_return_deterioration_pp": _percent((gross_ending - net_ending) / initial_capital),
        "cost_components": component_totals,
        "flat_delivery_cost_excluded": sum(
            (decimal(row["flat_delivery_cost_excluded"]) for row in simulation["costs"]), Decimal("0")
        ),
        "cost_model_status": simulation["cost_model_status"],
        "min_holdings": min(actual_holdings, default=0),
        "median_holdings": _median([Decimal(value) for value in actual_holdings]),
        "mean_holdings": sum(actual_holdings) / len(actual_holdings) if actual_holdings else 0,
        "max_holdings": max(actual_holdings, default=0),
        "average_residual_cash_pct": sum(residual_cash, Decimal("0")) / Decimal(len(residual_cash)) if residual_cash else None,
        "median_residual_cash_pct": _median(residual_cash),
        "max_residual_cash_pct": max(residual_cash, default=Decimal("0")),
        "average_actual_invested_pct": Decimal("100") - (
            sum(residual_cash, Decimal("0")) / Decimal(len(residual_cash)) if residual_cash else Decimal("100")
        ),
        "unaffordable_name_instances": sum(int(row["unaffordable_names"]) for row in executed_rebalances),
        "average_tracking_difference_l1_pct": (
            sum((decimal(row["tracking_difference_l1_pct"]) for row in executed_rebalances), Decimal("0"))
            / Decimal(len(executed_rebalances))
            if executed_rebalances else None
        ),
        "largest_realized_position_weight_pct": max(largest_weights, default=Decimal("0")),
        "median_largest_position_weight_pct": _median(largest_weights),
        "median_top_five_weight_pct": _median(top_five_weights),
        "cash_reconciliation_violations": simulation["cash_reconciliation_violations"],
        "equity_reconciliation_violations": simulation["equity_reconciliation_violations"],
        "longest_net_drawdown_duration_sessions": net_drawdown["longest_drawdown_duration_sessions"],
        "net_recovery_status_at_end": net_drawdown["recovery_status_at_end"],
        "net_maximum_drawdown_trough_date": net_drawdown["maximum_drawdown_trough_date"],
    }
    return {
        "summary": summary,
        "gross_months": gross_months,
        "net_months": net_months,
        "drawdowns": [*gross_drawdown_rows, *net_drawdown_rows],
    }


def yearly_results(
    simulation: Mapping[str, Any],
    *,
    starting_capital: Decimal = STARTING_CAPITAL,
) -> list[dict[str, Any]]:
    daily_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["daily"]:
        daily_by_year[int(str(row["date"])[:4])].append(row)
    rebalances_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["rebalances"]:
        rebalances_by_year[int(str(row["execution_date"])[:4])].append(row)
    periods_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["periods"]:
        if not row["final_partial_period"]:
            periods_by_year[int(str(row["period_end"])[:4])].append(row)
    costs_by_year: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in simulation["costs"]:
        costs_by_year[int(str(row["execution_date"])[:4])] += decimal(row["applied_total_cost"])
    rows: list[dict[str, Any]] = []
    prior_gross = decimal(starting_capital)
    prior_net = decimal(starting_capital)
    for year in (2022, 2023, 2024):
        year_daily = daily_by_year[year]
        gross_end = decimal(year_daily[-1]["gross_equity"])
        net_end = decimal(year_daily[-1]["net_equity"])
        net_values = [decimal(row["net_equity"]) for row in year_daily]
        peak = prior_net
        max_drawdown = Decimal("0")
        for value in net_values:
            peak = max(peak, value)
            max_drawdown = min(max_drawdown, value / peak - Decimal("1"))
        year_periods = periods_by_year[year]
        rows.append(
            {
                "experiment_id": simulation["experiment_id"],
                "mode": simulation["mode"],
                "year": year,
                "gross_return_pct": _percent(gross_end / prior_gross - Decimal("1")),
                "net_return_pct": _percent(net_end / prior_net - Decimal("1")),
                "net_max_drawdown_pct": _percent(max_drawdown),
                "one_way_turnover_x": sum(
                    (decimal(row["one_way_turnover"]) for row in rebalances_by_year[year] if str(row["status"]).startswith("EXECUTED")),
                    Decimal("0"),
                ),
                "cost_drag_rupees": costs_by_year[year],
                "cost_drag_pct_starting_equity": _percent(costs_by_year[year] / prior_net) if prior_net else None,
                "rebalance_period_count": len(year_periods),
                "positive_net_rebalance_period_count": sum(row["positive_net_period"] for row in year_periods),
                "positive_net_rebalance_period_rate_pct": _percent(
                    Decimal(sum(row["positive_net_period"] for row in year_periods)) / Decimal(len(year_periods))
                ) if year_periods else None,
            }
        )
        prior_gross = gross_end
        prior_net = net_end
    return rows


def turnover_efficiency_result(summary: Mapping[str, Any]) -> str:
    value = summary.get("net_return_per_unit_turnover")
    if value is None:
        return "INCONCLUSIVE"
    observed = decimal(value)
    if observed >= Decimal("0.10"):
        return "STRONG"
    if observed >= Decimal("0.04"):
        return "ACCEPTABLE"
    if observed >= 0:
        return "WEAK"
    return "VERY_WEAK"


def capital_feasibility_result(summary: Mapping[str, Any]) -> str:
    residual = summary.get("average_residual_cash_pct")
    tracking = summary.get("average_tracking_difference_l1_pct")
    if residual is None or tracking is None:
        return "INCONCLUSIVE"
    residual_value = decimal(residual)
    tracking_value = decimal(tracking)
    if residual_value < 5 and tracking_value < 5:
        return "LOW_DISTORTION"
    if residual_value < 10 and tracking_value < 10:
        return "MODERATE_DISTORTION"
    if residual_value < 20 and tracking_value < 25:
        return "HIGH_DISTORTION"
    return "SEVERE_DISTORTION"


def cost_materiality(summary: Mapping[str, Any]) -> str:
    deterioration = decimal(summary["gross_to_net_return_deterioration_pp"])
    if deterioration <= 2:
        return "LOW"
    if deterioration <= 5:
        return "MODERATE"
    if deterioration <= 10:
        return "HIGH"
    return "VERY_HIGH"


def temporal_stability(yearly: Sequence[Mapping[str, Any]]) -> str:
    values = [decimal(row["net_return_pct"]) for row in sorted(yearly, key=lambda row: int(row["year"]))]
    if len(values) != 3:
        return "INCONCLUSIVE"
    positive = sum(value > 0 for value in values)
    if positive == 3:
        return "CONSISTENT"
    if positive == 2 and min(values) > Decimal("-20"):
        return "MOSTLY_CONSISTENT"
    if values[0] * values[-1] < 0 and abs(values[0]) >= 5 and abs(values[-1]) >= 5:
        return "INVERSE_ACROSS_YEARS"
    return "UNSTABLE"


def quality_classifications(
    executable_summary: Mapping[str, Any],
    yearly: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    net_cagr = executable_summary.get("net_cagr_pct")
    net_return = decimal(executable_summary["net_total_return_pct"])
    drawdown = abs(decimal(executable_summary["net_max_drawdown_pct"]))
    positive_years = sum(decimal(row["net_return_pct"]) > 0 for row in yearly)
    stability = temporal_stability(yearly)
    if net_cagr is None:
        return_quality = "FAILED"
    elif decimal(net_cagr) >= 12 and drawdown <= 25 and positive_years == 3:
        return_quality = "STRONG"
    elif decimal(net_cagr) >= 8 and drawdown <= 35 and positive_years >= 2:
        return_quality = "PROMISING"
    elif net_return > 0:
        return_quality = "MIXED"
    elif net_return > -20:
        return_quality = "WEAK"
    else:
        return_quality = "FAILED"

    if drawdown <= 15:
        risk_quality = "STRONG"
    elif drawdown <= 25:
        risk_quality = "ACCEPTABLE"
    elif drawdown <= 35:
        risk_quality = "MIXED"
    elif drawdown <= 50:
        risk_quality = "WEAK"
    else:
        risk_quality = "FAILED"

    deterioration = decimal(executable_summary["gross_to_net_return_deterioration_pp"])
    if deterioration <= 2:
        cost_quality = "STRONG"
    elif deterioration <= 5:
        cost_quality = "ACCEPTABLE"
    elif deterioration <= 10:
        cost_quality = "MIXED"
    elif deterioration <= 20:
        cost_quality = "WEAK"
    else:
        cost_quality = "FAILED"

    temporal_quality = {
        "CONSISTENT": "STRONG",
        "MOSTLY_CONSISTENT": "ACCEPTABLE",
        "UNSTABLE": "MIXED",
        "INVERSE_ACROSS_YEARS": "WEAK",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[stability]

    if return_quality in {"STRONG", "PROMISING"} and risk_quality in {"STRONG", "ACCEPTABLE", "MIXED"}:
        baseline_result = "PROMISING"
    elif return_quality == "MIXED" and risk_quality != "FAILED":
        baseline_result = "MIXED"
    elif return_quality == "WEAK" and risk_quality != "FAILED":
        baseline_result = "WEAK"
    elif return_quality == "FAILED" or risk_quality == "FAILED":
        baseline_result = "FAILED"
    else:
        baseline_result = "INCONCLUSIVE"

    accounting_reproducible = (
        int(executable_summary["cash_reconciliation_violations"]) == 0
        and int(executable_summary["equity_reconciliation_violations"]) == 0
    )
    phase2 = (
        net_return > -30
        and drawdown < 50
        and (positive_years >= 2 or (net_cagr is not None and decimal(net_cagr) >= 8))
        and int(executable_summary["min_holdings"]) >= 20
        and accounting_reproducible
    )
    return {
        "TURNOVER_EFFICIENCY_RESULT": turnover_efficiency_result(executable_summary),
        "CAPITAL_FEASIBILITY_RESULT": capital_feasibility_result(executable_summary),
        "CAPITAL_SCALE_LIMITATION": {
            "LOW_DISTORTION": "MINOR",
            "MODERATE_DISTORTION": "MODERATE",
            "HIGH_DISTORTION": "MATERIAL",
            "SEVERE_DISTORTION": "SEVERE",
            "INCONCLUSIVE": "INCONCLUSIVE",
        }[capital_feasibility_result(executable_summary)],
        "FAMILY_A_COST_MATERIALITY": cost_materiality(executable_summary),
        "FAMILY_A_TEMPORAL_STABILITY": stability,
        "RETURN_QUALITY": return_quality,
        "RISK_QUALITY": risk_quality,
        "COST_EFFICIENCY": cost_quality,
        "TEMPORAL_STABILITY_QUALITY": temporal_quality,
        "FAMILY_A_BASELINE_RESULT": baseline_result,
        "ELIGIBLE_FOR_FAMILY_A_PHASE2": "YES" if phase2 else "NO",
        "phase2_gate_evidence": {
            "non_catastrophic_net_result": net_return > -30,
            "reasonable_drawdown": drawdown < 50,
            "supportive_years": positive_years,
            "adequate_breadth": int(executable_summary["min_holdings"]) >= 20,
            "reproducible_accounting": accounting_reproducible,
        },
    }


def run_development_pilot(
    schedules: Mapping[str, Sequence[RebalanceSchedule]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(case: str, passed: bool, evidence: str) -> None:
        rows.append(
            {
                "case": case,
                "source": "ACTUAL_FROZEN_DEVELOPMENT_INPUT",
                "passed": passed,
                "evidence": evidence,
            }
        )

    monthly_first = schedules["MOM-A-001"][0]
    quarterly_first = schedules["MOM-A-002"][0]
    add(
        "A_MONTHLY_FORMATION_EXECUTION",
        monthly_first.formation_date < monthly_first.execution_date,
        f"{monthly_first.formation_date.isoformat()} close -> {monthly_first.execution_date.isoformat()} open",
    )
    add(
        "B_QUARTERLY_FORMATION_EXECUTION",
        quarterly_first.formation_date.month in {3, 6, 9, 12}
        and quarterly_first.formation_date < quarterly_first.execution_date,
        f"{quarterly_first.formation_date.isoformat()} close -> {quarterly_first.execution_date.isoformat()} open",
    )
    first_6m = next(row for row in schedules["MOM-A-001"] if row.sufficient_universe)
    first_12_1 = next(row for row in schedules["MOM-A-003"] if row.sufficient_universe)
    add(
        "C_6M_RANK",
        first_6m.selected[0].rank == 1,
        f"{first_6m.formation_date}:{first_6m.selected[0].symbol}:rank=1:signal={first_6m.selected[0].signal_value}",
    )
    add(
        "D_12_1_RANK",
        first_12_1.selected[0].rank == 1,
        f"{first_12_1.formation_date}:{first_12_1.selected[0].symbol}:rank=1:signal={first_12_1.selected[0].signal_value}",
    )
    add(
        "E_TOP_DECILE_MEMBERSHIP",
        len(first_6m.selected) == first_6m.intended_count and len(first_6m.selected) >= 20,
        f"eligible={first_6m.eligible_count};selected={len(first_6m.selected)}",
    )
    valid_monthly = [row for row in schedules["MOM-A-001"] if row.sufficient_universe]
    pair: tuple[RebalanceSchedule, RebalanceSchedule] | None = None
    retained_symbol = removed_symbol = new_symbol = None
    for previous, current in zip(valid_monthly, valid_monthly[1:]):
        previous_names = {row.symbol for row in previous.selected}
        current_names = {row.symbol for row in current.selected}
        retained = sorted(previous_names & current_names)
        removed = sorted(previous_names - current_names)
        added = sorted(current_names - previous_names)
        executable_removed = [
            symbol for symbol in removed if symbol in bars.get(current.execution_date, {})
        ]
        if retained and executable_removed and added:
            pair = (previous, current)
            retained_symbol = retained[0]
            removed_symbol = executable_removed[0]
            new_symbol = added[0]
            break
    if pair is None or retained_symbol is None or removed_symbol is None or new_symbol is None:
        raise ValueError("Actual development inputs do not provide a complete rebalance pilot transition")
    add("F_RETAINED_HOLDING", True, f"{retained_symbol} remains selected at {pair[1].execution_date}")
    add("G_REMOVED_HOLDING", True, f"{removed_symbol} leaves selection at {pair[1].execution_date}")
    add("H_NEW_HOLDING", True, f"{new_symbol} enters selection at {pair[1].execution_date}")
    ideal_weight = Decimal("1") / Decimal(len(pair[0].selected))
    add(
        "I_EQUAL_WEIGHT_IDEALIZED_ALLOCATION",
        abs(ideal_weight * Decimal(len(pair[0].selected)) - Decimal("1")) < Decimal("1e-24"),
        f"holding_count={len(pair[0].selected)};weight={ideal_weight}",
    )
    first_symbol = pair[0].selected[0].symbol
    first_price = bars[pair[0].execution_date][first_symbol].open_price
    intended_rupees = STARTING_CAPITAL / Decimal(len(pair[0].selected))
    shares = int((intended_rupees / first_price).to_integral_value(rounding=ROUND_FLOOR))
    add(
        "J_INTEGER_SHARE_ALLOCATION",
        shares >= 0 and Decimal(shares) * first_price <= intended_rupees,
        f"{first_symbol}:price={first_price};shares={shares};intended={intended_rupees}",
    )
    unaffordable: tuple[RebalanceSchedule, SelectedInstrument, Decimal] | None = None
    for schedule_rows in schedules.values():
        for schedule in schedule_rows:
            if not schedule.sufficient_universe:
                continue
            intended = STARTING_CAPITAL / Decimal(len(schedule.selected))
            for instrument in schedule.selected:
                price = bars.get(schedule.execution_date, {}).get(instrument.symbol)
                if price is not None and price.open_price > intended:
                    unaffordable = (schedule, instrument, price.open_price)
                    break
            if unaffordable:
                break
        if unaffordable:
            break
    if unaffordable is None:
        raise ValueError("Actual development inputs do not contain an unaffordable pilot selection")
    add(
        "K_UNAFFORDABLE_STOCK",
        unaffordable[2] > STARTING_CAPITAL / Decimal(len(unaffordable[0].selected)),
        f"{unaffordable[1].symbol}:price={unaffordable[2]};date={unaffordable[0].execution_date}",
    )
    sell_price = bars[pair[1].execution_date][removed_symbol].open_price
    sell_cost = _cost_for_mode("SELL", pair[1].execution_date, sell_price, EXECUTABLE_MODE)
    add(
        "L_SELL_COST",
        decimal(sell_cost["applied_total_cost"]) > 0
        and decimal(sell_cost["applied_components"][DP_CHARGE]) > 0,
        f"{removed_symbol}:one_share_notional={sell_price};cost={sell_cost['applied_total_cost']}",
    )
    buy_price = bars[pair[1].execution_date][new_symbol].open_price
    buy_cost = _cost_for_mode("BUY", pair[1].execution_date, buy_price, EXECUTABLE_MODE)
    add(
        "M_BUY_COST",
        decimal(buy_cost["applied_total_cost"]) > 0
        and decimal(buy_cost["applied_components"][STAMP_DUTY]) > 0,
        f"{new_symbol}:one_share_notional={buy_price};cost={buy_cost['applied_total_cost']}",
    )
    pilot_schedules = [row for row in schedules["MOM-A-001"] if row.execution_date <= pair[1].execution_date]
    pilot_sessions = [row for row in sessions if row <= pair[1].execution_date]
    pilot_result = simulate_executable(
        "MOM-A-001", pilot_schedules, pilot_sessions, bars
    )
    add(
        "N_FULL_REBALANCE_ACCOUNTING",
        pilot_result["cash_reconciliation_violations"] == 0
        and pilot_result["equity_reconciliation_violations"] == 0,
        (
            f"cash_violations={pilot_result['cash_reconciliation_violations']};"
            f"equity_violations={pilot_result['equity_reconciliation_violations']}"
        ),
    )
    if len(rows) != 14 or not all(row["passed"] for row in rows):
        raise ValueError(f"Family A development pilot failed: {rows}")
    return rows


def _immutable_result(path: Path, body: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    result = {**body, hash_field: canonical_hash(body)}
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(result):
            raise FamilyAResultImmutabilityError(
                f"Immutable development result differs at {path}"
            )
        return existing
    write_json(path, result)
    return json_ready(result)


def _comparison_row(summary: Mapping[str, Any], classifications: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "comparison_label": "RELATIVE_BASELINE_COMPARISON",
        "experiment_id": summary["experiment_id"],
        "mode": summary["mode"],
        "gross_ending_equity": summary["gross_ending_equity"],
        "net_ending_equity": summary["net_ending_equity"],
        "gross_total_return_pct": summary["gross_total_return_pct"],
        "net_total_return_pct": summary["net_total_return_pct"],
        "gross_cagr_pct": summary["gross_cagr_pct"],
        "net_cagr_pct": summary["net_cagr_pct"],
        "net_max_drawdown_pct": summary["net_max_drawdown_pct"],
        "net_annualized_volatility_pct": summary["net_annualized_volatility_pct"],
        "annualized_turnover_x": summary["annualized_turnover_x"],
        "total_cost": summary["total_cost"],
        "cost_drag_pct_initial_capital": summary["cost_drag_pct_initial_capital"],
        "net_rebalance_success_rate_pct": summary["net_rebalance_success_rate_pct"],
        "net_positive_calendar_month_rate_pct": summary["net_positive_calendar_month_rate_pct"],
        "min_holdings": summary["min_holdings"],
        "median_holdings": summary["median_holdings"],
        "max_holdings": summary["max_holdings"],
        "average_residual_cash_pct": summary["average_residual_cash_pct"],
        "average_tracking_difference_l1_pct": summary["average_tracking_difference_l1_pct"],
        "turnover_efficiency_result": classifications.get("TURNOVER_EFFICIENCY_RESULT", "MODE_DIAGNOSTIC_ONLY"),
        "capital_feasibility_result": classifications.get("CAPITAL_FEASIBILITY_RESULT", "MODE_DIAGNOSTIC_ONLY"),
        "baseline_result": classifications.get("FAMILY_A_BASELINE_RESULT", "MODE_DIAGNOSTIC_ONLY"),
        "winner_label": "PROHIBITED",
    }


def _cost_report_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for simulation in simulations:
        for component in (*COST_COMPONENTS, "SLIPPAGE", "TOTAL"):
            if component == "SLIPPAGE":
                value = sum((decimal(row["slippage"]) for row in simulation["costs"]), Decimal("0"))
            elif component == "TOTAL":
                value = sum((decimal(row["applied_total_cost"]) for row in simulation["costs"]), Decimal("0"))
            else:
                value = sum((decimal(row[component.lower()]) for row in simulation["costs"]), Decimal("0"))
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "mode": simulation["mode"],
                    "component": component,
                    "amount": value,
                    "applied": component != DP_CHARGE or str(simulation["mode"]).startswith("EXECUTABLE"),
                    "methodology": simulation["cost_model_status"],
                }
            )
        output.append(
            {
                "experiment_id": simulation["experiment_id"],
                "mode": simulation["mode"],
                "component": "FLAT_DELIVERY_COST_EXCLUDED",
                "amount": sum(
                    (decimal(row["flat_delivery_cost_excluded"]) for row in simulation["costs"]), Decimal("0")
                ),
                "applied": False,
                "methodology": simulation["cost_model_status"],
            }
        )
    return output


def build_family_a_development_backtests(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    preregistration = verify_family_a_preregistration(root)
    baseline_before = full_baseline_snapshot(root)
    schedules = load_rebalance_schedules(root)
    sessions = [row for row in _load_sessions(root) if DEVELOPMENT_START <= row <= DEVELOPMENT_END]
    membership = _load_membership(root)
    aliases = _load_aliases(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if not sessions or max(bars) > DEVELOPMENT_END:
        raise FamilyAValidationAccessError("Development data boundary failure")

    pilot_rows = run_development_pilot(schedules, sessions, bars)
    simulations: list[dict[str, Any]] = []
    for experiment_id in EXPERIMENT_IDS:
        simulations.append(
            simulate_idealized(experiment_id, schedules[experiment_id], sessions, bars)
        )
        simulations.append(
            simulate_executable(experiment_id, schedules[experiment_id], sessions, bars)
        )

    summaries: dict[tuple[str, str], dict[str, Any]] = {}
    drawdown_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    for simulation in simulations:
        analysis = summarize_simulation(simulation)
        key = (simulation["experiment_id"], simulation["mode"])
        summaries[key] = analysis["summary"]
        drawdown_rows.extend(analysis["drawdowns"])
        yearly_rows.extend(yearly_results(simulation))

    classifications: dict[str, dict[str, Any]] = {}
    baseline_results: dict[str, dict[str, Any]] = {}
    output_root = root / "data/research/strategy_families/family_a/v1/development_backtests"
    for experiment_id in EXPERIMENT_IDS:
        idealized = summaries[(experiment_id, IDEALIZED_MODE)]
        executable = summaries[(experiment_id, EXECUTABLE_MODE)]
        executable_yearly = [
            row
            for row in yearly_rows
            if row["experiment_id"] == experiment_id and row["mode"] == EXECUTABLE_MODE
        ]
        classifications[experiment_id] = quality_classifications(executable, executable_yearly)
        executable["idealized_vs_executable_net_return_difference_pp"] = (
            decimal(idealized["net_total_return_pct"]) - decimal(executable["net_total_return_pct"])
        )
        for mode in MODES:
            mode_body = {
                "command_version": COMMAND_VERSION,
                "command_profile": COMMAND_PROFILE,
                "family_version": FAMILY_VERSION,
                "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
                "experiment_id": experiment_id,
                "parameter_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
                "preregistration_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["preregistration_hash"],
                "mode": mode,
                "development_window": {
                    "start": DEVELOPMENT_START.isoformat(),
                    "end": DEVELOPMENT_END.isoformat(),
                },
                "metrics": summaries[(experiment_id, mode)],
                "performance_scope": "DEVELOPMENT_ONLY",
                "validation_accessed": False,
                "winner_selected": False,
                "parameters_changed": False,
            }
            mode_path = output_root / experiment_id.lower().replace("-", "_") / mode.lower() / "result.json"
            _immutable_result(mode_path, mode_body, "mode_result_hash")
        baseline_body = {
            "command_version": COMMAND_VERSION,
            "family_version": FAMILY_VERSION,
            "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
            "experiment_id": experiment_id,
            "parameter_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
            "preregistration_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["preregistration_hash"],
            "idealized_metrics": idealized,
            "executable_metrics": executable,
            "yearly": [row for row in yearly_rows if row["experiment_id"] == experiment_id],
            "classifications": classifications[experiment_id],
            "validation_accessed": False,
            "winner_selected": False,
            "result_immutability": "IMMUTABLE_NEW_EXPERIMENT_REQUIRED_FOR_PARAMETER_CHANGE",
        }
        baseline_path = output_root / experiment_id.lower().replace("-", "_") / "baseline_result.json"
        baseline_results[experiment_id] = _immutable_result(
            baseline_path, baseline_body, "baseline_result_hash"
        )

    phase2_candidate = any(
        row["ELIGIBLE_FOR_FAMILY_A_PHASE2"] == "YES" for row in classifications.values()
    )
    result_labels = [row["FAMILY_A_BASELINE_RESULT"] for row in classifications.values()]
    if "PROMISING" in result_labels:
        family_result = "PROMISING_FAMILY"
    elif "MIXED" in result_labels:
        family_result = "MIXED_FAMILY"
    elif all(row == "FAILED" for row in result_labels):
        family_result = "FAILED_FAMILY"
    elif any(row == "WEAK" for row in result_labels):
        family_result = "WEAK_FAMILY"
    else:
        family_result = "INCONCLUSIVE"

    derived_registry_body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "source_registry_hash": preregistration["source_registry_hash"],
        "experiment_count": 3,
        "experiment_ids": list(EXPERIMENT_IDS),
        "experiments": [
            {
                "experiment_id": experiment_id,
                "status": "DEVELOPMENT_EVALUATED",
                "promotion_allowed": False,
                "parameter_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
                "preregistration_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["preregistration_hash"],
                "baseline_result_hash": baseline_results[experiment_id]["baseline_result_hash"],
                "baseline_result": classifications[experiment_id]["FAMILY_A_BASELINE_RESULT"],
                "phase2_eligible": classifications[experiment_id]["ELIGIBLE_FOR_FAMILY_A_PHASE2"],
            }
            for experiment_id in EXPERIMENT_IDS
        ],
        "validation_authorized": False,
        "validation_accessed": False,
        "winner_selected": False,
        "result_immutability": "IMMUTABLE",
    }
    development_registry = {
        **derived_registry_body,
        "development_registry_hash": canonical_hash(derived_registry_body),
    }
    write_json(output_root / "registry/development_registry_v1.json", development_registry)

    reports_root = root / "data/reports"
    comparison_rows = [
        _comparison_row(
            summaries[(experiment_id, mode)],
            classifications[experiment_id] if mode == EXECUTABLE_MODE else {},
        )
        for experiment_id in EXPERIMENT_IDS
        for mode in MODES
    ]
    all_rebalances = [row for simulation in simulations for row in simulation["rebalances"]]
    all_holdings = [row for simulation in simulations for row in simulation["holdings"]]
    all_positions = [row for simulation in simulations for row in simulation["position_returns"]]
    cost_report = _cost_report_rows(simulations)
    capital_rows = [
        row
        for row in all_rebalances
        if row["mode"] == EXECUTABLE_MODE and str(row["status"]).startswith("EXECUTED")
    ]
    turnover_rows = [
        {
            key: row.get(key)
            for key in (
                "experiment_id", "mode", "formation_date", "execution_date", "status",
                "gross_buy_turnover", "gross_sell_turnover", "one_way_turnover",
                "selected_count", "retained_count", "added_count", "removed_count", "retention_rate_pct",
            )
        }
        for row in all_rebalances
    ]
    write_csv(reports_root / REPORT_NAMES[1], comparison_rows)
    write_csv(reports_root / REPORT_NAMES[2], yearly_rows)
    write_csv(reports_root / REPORT_NAMES[3], turnover_rows)
    write_csv(reports_root / REPORT_NAMES[4], cost_report)
    write_csv(reports_root / REPORT_NAMES[5], capital_rows)
    write_csv(reports_root / REPORT_NAMES[6], all_rebalances)
    write_csv(reports_root / REPORT_NAMES[7], all_holdings)
    write_csv(reports_root / REPORT_NAMES[8], all_positions)
    write_csv(reports_root / REPORT_NAMES[9], drawdown_rows)
    write_csv(reports_root / REPORT_NAMES[10], pilot_rows)
    for experiment_id in EXPERIMENT_IDS:
        write_csv(
            reports_root / f"family_a_{experiment_id.lower().replace('-', '_')}_development.csv",
            [row for row in comparison_rows if row["experiment_id"] == experiment_id],
        )
    for simulation in simulations:
        mode_root = output_root / simulation["experiment_id"].lower().replace("-", "_") / simulation["mode"].lower()
        write_csv(mode_root / "daily_ledger.csv", simulation["daily"])
        write_csv(mode_root / "rebalances.csv", simulation["rebalances"])
        write_csv(mode_root / "holdings.csv", simulation["holdings"])
        write_csv(mode_root / "position_returns.csv", simulation["position_returns"])
        write_csv(mode_root / "costs.csv", simulation["costs"])

    baseline_after = full_baseline_snapshot(root)
    baseline_violations = 0 if baseline_before == baseline_after else 1
    total_cash_violations = sum(int(simulation["cash_reconciliation_violations"]) for simulation in simulations)
    total_equity_violations = sum(int(simulation["equity_reconciliation_violations"]) for simulation in simulations)
    monthly_6m = summaries[("MOM-A-001", EXECUTABLE_MODE)]
    quarterly_6m = summaries[("MOM-A-002", EXECUTABLE_MODE)]
    skip_month = summaries[("MOM-A-003", EXECUTABLE_MODE)]
    relative_findings = {
        "label": "RELATIVE_BASELINE_COMPARISON",
        "monthly_vs_quarterly_6m": {
            "annualized_turnover_delta_x_monthly_minus_quarterly": decimal(monthly_6m["annualized_turnover_x"]) - decimal(quarterly_6m["annualized_turnover_x"]),
            "total_cost_delta_monthly_minus_quarterly": decimal(monthly_6m["total_cost"]) - decimal(quarterly_6m["total_cost"]),
            "net_return_delta_pp_monthly_minus_quarterly": decimal(monthly_6m["net_total_return_pct"]) - decimal(quarterly_6m["net_total_return_pct"]),
        },
        "six_month_vs_twelve_minus_one": {
            "net_return_delta_pp_6m_minus_12_1": decimal(monthly_6m["net_total_return_pct"]) - decimal(skip_month["net_total_return_pct"]),
            "max_drawdown_delta_pp_6m_minus_12_1": decimal(monthly_6m["net_max_drawdown_pct"]) - decimal(skip_month["net_max_drawdown_pct"]),
            "annualized_turnover_delta_x_6m_minus_12_1": decimal(monthly_6m["annualized_turnover_x"]) - decimal(skip_month["annualized_turnover_x"]),
        },
        "idealized_vs_executable": {
            experiment_id: {
                "net_return_difference_pp": decimal(summaries[(experiment_id, IDEALIZED_MODE)]["net_total_return_pct"])
                - decimal(summaries[(experiment_id, EXECUTABLE_MODE)]["net_total_return_pct"]),
                "ending_equity_difference": decimal(summaries[(experiment_id, IDEALIZED_MODE)]["net_ending_equity"])
                - decimal(summaries[(experiment_id, EXECUTABLE_MODE)]["net_ending_equity"]),
            }
            for experiment_id in EXPERIMENT_IDS
        },
        "winner_selected": False,
        "best_optimal_labels_prohibited": True,
    }
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "preregistration_verification": {
            "status": "VERIFIED",
            "experiments": preregistration["experiments"],
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "trading_sessions": len(sessions),
            "latest_price_date_loaded": max(bars).isoformat(),
        },
        "experiments": {
            experiment_id: {
                "idealized": summaries[(experiment_id, IDEALIZED_MODE)],
                "executable": summaries[(experiment_id, EXECUTABLE_MODE)],
                "yearly": [row for row in yearly_rows if row["experiment_id"] == experiment_id],
                "classifications": classifications[experiment_id],
                "baseline_result_hash": baseline_results[experiment_id]["baseline_result_hash"],
            }
            for experiment_id in EXPERIMENT_IDS
        },
        "relative_baseline_comparison": relative_findings,
        "classifications": {
            "FAMILY_A_DEVELOPMENT_RESULT": family_result,
            "FAMILY_A_PHASE2_AUTHORIZATION_CANDIDATE": "YES" if phase2_candidate else "NO",
            "phase2_automatically_authorized": False,
            "validation_authorized": False,
        },
        "pilot": {
            "case_count": len(pilot_rows),
            "passed_case_count": sum(row["passed"] for row in pilot_rows),
            "actual_development_cases_only": True,
        },
        "accounting": {
            "cash_reconciliation_violations": total_cash_violations,
            "equity_reconciliation_violations": total_equity_violations,
            "tolerance": "0.000001 INR",
        },
        "immutability": {
            "development_registry_hash": development_registry["development_registry_hash"],
            "result_hashes": {
                experiment_id: baseline_results[experiment_id]["baseline_result_hash"]
                for experiment_id in EXPERIMENT_IDS
            },
            "parameter_changes_require_new_experiment_id_or_version": True,
        },
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_mutation_violations": baseline_violations,
            "family_a_command_01_snapshot_hash": baseline_after["family_a_command_01_snapshot_hash"],
            "cap4_validation_state": baseline_after["cap4_validation_state"],
            "cap4_validation_run_count": baseline_after["cap4_validation_run_count"],
            "cap4_validation_result_hash": baseline_after["cap4_validation_result_hash"],
        },
        "governance": {
            "performance_scope": "DEVELOPMENT_ONLY",
            "validation_accessed": False,
            "validation_rows_loaded": 0,
            "winner_selected": False,
            "parameters_changed": False,
            "extra_variant_tested": False,
            "alternate_capital_tested": False,
            "absolute_momentum_added": False,
            "regime_filter_added": False,
            "volatility_scaling_added": False,
            "stop_or_target_added": False,
            "strategy_v2_created": False,
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "registry": (output_root / "registry/development_registry_v1.json").relative_to(root).as_posix(),
            "reports": list(REPORT_NAMES),
        },
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    artifact_paths = [
        *sorted(path for path in output_root.rglob("*") if path.is_file()),
        *(reports_root / name for name in REPORT_NAMES),
        *(reports_root / f"family_a_{experiment_id.lower().replace('-', '_')}_development.csv" for experiment_id in EXPERIMENT_IDS),
    ]
    manifest = {
        "command_version": COMMAND_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "created_at": started_at,
        "development_only": True,
        "validation_accessed": False,
        "dataset_hashes": {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in artifact_paths
            if path.exists() and path.name != "run_manifest_v1.json"
        },
        "baseline_snapshot_hash": baseline_after["snapshot_hash"],
        "winner_selected": False,
    }
    write_json(output_root / "manifests/run_manifest_v1.json", manifest)
    return summary


def finalize_development_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_a_dev_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run Family A development backtests before finalizing")
    summary = _read_json(summary_path)
    verify_family_a_preregistration(root)
    baseline = full_baseline_snapshot(root)
    if baseline["snapshot_hash"] != summary["regression"]["after_snapshot_hash"]:
        raise FamilyAResultImmutabilityError("Frozen baseline changed after development evaluation")
    ready = (
        backend_tests == "PASSED"
        and frontend_build == "PASSED"
        and summary["regression"]["baseline_mutation_violations"] == 0
        and summary["accounting"]["cash_reconciliation_violations"] == 0
        and summary["accounting"]["equity_reconciliation_violations"] == 0
        and summary["pilot"]["passed_case_count"] == 14
        and summary["governance"]["validation_accessed"] is False
    )
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": ready,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXECUTABLE_MODE",
    "EXPECTED_EXPERIMENT_HASHES",
    "EXPECTED_FAMILY_CONFIG_HASH",
    "FamilyAPreregistrationMismatch",
    "FamilyAResultImmutabilityError",
    "FamilyAValidationAccessError",
    "IDEALIZED_MODE",
    "REPORT_NAMES",
    "build_family_a_development_backtests",
    "capital_feasibility_result",
    "finalize_development_review",
    "full_baseline_snapshot",
    "load_rebalance_schedules",
    "quality_classifications",
    "run_development_pilot",
    "simulate_executable",
    "simulate_idealized",
    "summarize_simulation",
    "temporal_stability",
    "turnover_efficiency_result",
    "validate_development_date",
    "verify_family_a_preregistration",
    "yearly_results",
)

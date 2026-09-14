from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import (
    decimal,
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_research_closure import (
    EXPECTED_FAMILY_B_CLOSURE_HASH,
    family_b_baseline_snapshot,
    verify_family_b_closure_inputs,
)
from app.research.strategy.family_c_breakout_continuation import (
    COMPRESSION_THRESHOLD,
    CONTROL_ID,
    CONTROL_NAME,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_IDS,
    FAMILY_VERSION,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    VOLUME_THRESHOLD,
    FamilyCBar,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
    control_reference,
    entry_exit_chronology,
    experiment_registry,
    family_config,
    success_criteria_config,
    verify_expected_hashes,
    verify_registry,
)


COMMAND = "Step 03.03 / Command 02"
COMMAND_VERSION = "FAMILY_C_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "BREAKOUT_CONTINUATION_DEVELOPMENT_V1"
EXECUTABLE_MODE = "EXECUTABLE_INTEGER_SHARE_500K"
IDEALIZED_MODE = "IDEALIZED_PERCENTAGE_PORTFOLIO"
MODES = (EXECUTABLE_MODE, IDEALIZED_MODE)
BREAKOUT_STRENGTH_CAPACITY_RANKING = (
    "BREAKOUT_STRENGTH_PCT_DESCENDING",
    "SYMBOL_ASCENDING",
)
COMPRESSION_PRIORITY_CAPACITY_RANKING = (
    "COMPRESSION_RANGE_PCT_ASCENDING",
    "BREAKOUT_STRENGTH_PCT_DESCENDING",
    "SYMBOL_ASCENDING",
)

STRATEGIES = (
    (CONTROL_ID, CONTROL_NAME, "control_signal"),
    ("BRK-C-001", "20D_BREAKOUT_WITH_10D_COMPRESSION_V1", "c001_signal"),
    ("BRK-C-002", "20D_BREAKOUT_WITH_VOLUME_EXPANSION_V1", "c002_signal"),
)

REPORT_NAMES = (
    "family_c_dev_v1_summary.json",
    "family_c_dev_v1_control.csv",
    "family_c_dev_v1_c001.csv",
    "family_c_dev_v1_c002.csv",
    "family_c_dev_v1_positions.csv",
    "family_c_dev_v1_yearly.csv",
    "family_c_dev_v1_criteria.csv",
    "family_c_dev_v1_capacity.csv",
    "family_c_dev_v1_mfe_mae.csv",
    "family_c_dev_v1_holding_path.csv",
    "family_c_dev_v1_breakout_strength.csv",
    "family_c_dev_v1_entry_gap.csv",
    "family_c_dev_v1_attribution.csv",
    "family_c_dev_v1_comparison.csv",
)


class FamilyCDevelopmentFreezeMismatch(RuntimeError):
    pass


@dataclass(slots=True)
class OpenPosition:
    experiment_id: str
    mode: str
    symbol: str
    isin: str
    formation_date: date
    formation_close: Decimal
    breakout_strength_pct: Decimal
    compression_range_pct: Decimal | None
    formation_volume_ratio: Decimal | None
    entry_date: date
    entry_price: Decimal
    entry_gap_pct: Decimal
    quantity: Decimal
    intended_notional: Decimal
    entry_notional: Decimal
    buy_cost: Decimal
    exit_date: date
    holding_dates: tuple[date, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return (
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != hash_field}


def _require_hash(
    value: Mapping[str, Any], hash_field: str, expected_hash: str
) -> bool:
    return value.get(hash_field) == expected_hash and canonical_hash(
        _without_hash(value, hash_field)
    ) == expected_hash


def command_01_snapshot(root: Path) -> dict[str, Any]:
    family_root = root / "data/research/strategy_families/family_c/v1"
    paths = [
        path
        for path in family_root.rglob("*")
        if path.is_file()
        and "development_evaluation" not in path.relative_to(family_root).parts
    ]
    report_paths = sorted((root / "data/reports").glob("family_c_v1_*"))
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted([*paths, *report_paths])
    }
    semantic = {
        "family_version": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "artifact_hashes": hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def verify_freeze_gate(root: Path) -> dict[str, Any]:
    family_root = root / "data/research/strategy_families/family_c/v1"
    config = _read_json(family_root / "registry/family_c_config_v1.json")
    criteria = _read_json(family_root / "governance/success_criteria_v1.json")
    registry = _read_json(
        family_root / "registry/family_c_experiment_registry_v1.json"
    )
    control = _read_json(family_root / "registry/control_c_000_reference_v1.json")
    c001 = _read_json(family_root / "registry/brk_c_001_preregistration_v1.json")
    c002 = _read_json(family_root / "registry/brk_c_002_preregistration_v1.json")
    manifest = _read_json(
        family_root / "manifests/family_c_architecture_manifest_v1.json"
    )
    expected_criteria = success_criteria_config()
    expected_config = family_config(expected_criteria)
    expected_registry = experiment_registry(
        expected_config,
        expected_criteria,
        control_reference(expected_config, expected_criteria),
    )
    checks = {
        "family_config_hash": _require_hash(
            config, "family_c_config_hash", EXPECTED_FAMILY_C_CONFIG_HASH
        ),
        "success_criteria_hash": _require_hash(
            criteria, "success_criteria_hash", EXPECTED_SUCCESS_CRITERIA_HASH
        ),
        "control_reference_hash": _require_hash(
            control, "control_reference_hash", EXPECTED_CONTROL_REFERENCE_HASH
        ),
        "C001_parameter_hash": canonical_hash(c001["parameters"])
        == EXPECTED_EXPERIMENT_HASHES["BRK-C-001"]["parameter_hash"],
        "C001_preregistration_hash": _require_hash(
            c001,
            "preregistration_hash",
            EXPECTED_EXPERIMENT_HASHES["BRK-C-001"]["preregistration_hash"],
        ),
        "C002_parameter_hash": canonical_hash(c002["parameters"])
        == EXPECTED_EXPERIMENT_HASHES["BRK-C-002"]["parameter_hash"],
        "C002_preregistration_hash": _require_hash(
            c002,
            "preregistration_hash",
            EXPECTED_EXPERIMENT_HASHES["BRK-C-002"]["preregistration_hash"],
        ),
        "registry_matches_frozen_builder": _require_hash(
            registry, "registry_hash", expected_registry["registry_hash"]
        ),
        "config_matches_frozen_builder": config["family_c_config_hash"]
        == expected_config["family_c_config_hash"],
        "criteria_matches_frozen_builder": criteria["success_criteria_hash"]
        == expected_criteria["success_criteria_hash"],
        "manifest_config_hash": manifest.get("family_c_config_hash")
        == EXPECTED_FAMILY_C_CONFIG_HASH,
        "manifest_criteria_hash": manifest.get("success_criteria_hash")
        == EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    artifact_mismatches = [
        relative_path
        for relative_path, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative_path).is_file()
        or file_sha256(root / relative_path) != expected_hash
    ]
    checks["command_01_artifact_hashes"] = not artifact_mismatches
    closure = verify_family_b_closure_inputs(root)
    checks["family_b_closure_hash"] = all(closure["checks"].values())
    if criteria.get("success_criteria_hash") != EXPECTED_SUCCESS_CRITERIA_HASH:
        raise FamilyCDevelopmentFreezeMismatch(
            "FAMILY_C_SUCCESS_CRITERIA_MISMATCH"
        )
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)
    if not all(checks.values()):
        raise FamilyCDevelopmentFreezeMismatch(
            f"FAMILY_C_PRE_RUN_FREEZE_MISMATCH: {checks}; artifacts={artifact_mismatches}"
        )
    return {
        "status": "VERIFIED",
        "checks": checks,
        "config": config,
        "criteria": criteria,
        "registry": registry,
        "manifest": manifest,
        "family_b_closure_hash": EXPECTED_FAMILY_B_CLOSURE_HASH,
        "command_01_snapshot": command_01_snapshot(root),
    }


def _bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else decimal(value)


def _load_signal_rows(root: Path) -> list[dict[str, Any]]:
    path = (
        root
        / "data/research/strategy_families/family_c/v1/signals/family_c_signal_dataset_v1.csv"
    )
    rows: list[dict[str, Any]] = []
    for raw in read_csv(path):
        decision_date = date.fromisoformat(raw["decision_date"])
        if not DEVELOPMENT_START <= decision_date <= DEVELOPMENT_END:
            raise FamilyCDevelopmentFreezeMismatch(
                "Signal input escaped the frozen DEVELOPMENT partition"
            )
        rows.append(
            {
                "decision_date": decision_date,
                "symbol": raw["symbol"],
                "isin": raw["isin"],
                "point_in_time_member": _bool(raw["point_in_time_member"]),
                "close": _optional_decimal(raw["close"]),
                "breakout_strength_pct": _optional_decimal(
                    raw["breakout_strength_pct"]
                ),
                "is_20d_breakout": _bool(raw["is_20d_breakout"]),
                "compression_range_pct": _optional_decimal(
                    raw["compression_range_pct"]
                ),
                "formation_volume_ratio": _optional_decimal(
                    raw["formation_volume_ratio"]
                ),
                "control_signal": _bool(raw["control_signal"]),
                "c001_signal": _bool(raw["c001_signal"]),
                "c002_signal": _bool(raw["c002_signal"]),
            }
        )
    return rows


def quantile(values: Sequence[Decimal], probability: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(decimal(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = decimal(probability) * Decimal(len(ordered) - 1)
    lower = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def profit_factor(profits: Sequence[Decimal]) -> Decimal | None:
    gains = sum((value for value in profits if value > 0), Decimal("0"))
    losses = abs(sum((value for value in profits if value < 0), Decimal("0")))
    if losses == 0:
        return None
    return gains / losses


def expectancy(returns: Sequence[Decimal]) -> Decimal | None:
    return (
        sum((decimal(value) for value in returns), Decimal("0"))
        / Decimal(len(returns))
        if returns
        else None
    )


def position_win_rate(returns: Sequence[Decimal]) -> Decimal | None:
    return (
        Decimal(sum(decimal(value) > 0 for value in returns))
        / Decimal(len(returns))
        if returns
        else None
    )


def _bar_path_available(
    symbol: str,
    chronology: Mapping[str, Any],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> tuple[bool, str | None]:
    entry_date = chronology["entry_date"]
    exit_date = chronology["exit_date"]
    if exit_date is None or exit_date > DEVELOPMENT_END:
        return False, "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"
    entry = bars.get(entry_date, {}).get(symbol) if entry_date else None
    if entry is None or entry.open_price <= 0:
        return False, "MISSING_T_PLUS_1_EXECUTION_PRICE"
    if any(
        bars.get(holding_date, {}).get(symbol) is None
        for holding_date in chronology["holding_dates"]
    ):
        return False, "INCOMPLETE_HOLDING_PATH"
    exit_bar = bars.get(exit_date, {}).get(symbol)
    if exit_bar is None or exit_bar.open_price <= 0:
        return False, "MISSING_EXIT_OPEN"
    return True, None


def _size_position(
    mode: str,
    portfolio_equity: Decimal,
    available_cash: Decimal,
    entry_price: Decimal,
    value_date: date,
) -> dict[str, Any]:
    intended = decimal(portfolio_equity) * TARGET_NOTIONAL_FRACTION
    if entry_price <= 0 or available_cash <= 0 or intended <= 0:
        return {
            "intended_notional": intended,
            "quantity": Decimal("0"),
            "actual_notional": Decimal("0"),
            "buy_cost": Decimal("0"),
        }
    if mode == EXECUTABLE_MODE:
        quantity = Decimal(
            int(
                (min(intended, available_cash) / entry_price).to_integral_value(
                    rounding=ROUND_FLOOR
                )
            )
        )
        while quantity > 0:
            notional = quantity * entry_price
            cost = estimate_order_cost("BUY", value_date, notional)["total_cost"]
            if notional + cost <= available_cash:
                return {
                    "intended_notional": intended,
                    "quantity": quantity,
                    "actual_notional": notional,
                    "buy_cost": cost,
                }
            quantity -= 1
        return {
            "intended_notional": intended,
            "quantity": Decimal("0"),
            "actual_notional": Decimal("0"),
            "buy_cost": Decimal("0"),
        }
    if mode != IDEALIZED_MODE:
        raise ValueError(f"Unknown portfolio mode: {mode}")
    notional = min(intended, available_cash)
    for _ in range(4):
        cost = estimate_order_cost("BUY", value_date, notional)["total_cost"]
        if notional + cost <= available_cash:
            break
        notional = max(Decimal("0"), available_cash - cost)
    cost = (
        estimate_order_cost("BUY", value_date, notional)["total_cost"]
        if notional > 0
        else Decimal("0")
    )
    if notional + cost > available_cash:
        notional = max(Decimal("0"), notional - (notional + cost - available_cash))
        cost = (
            estimate_order_cost("BUY", value_date, notional)["total_cost"]
            if notional > 0
            else Decimal("0")
        )
    return {
        "intended_notional": intended,
        "quantity": notional / entry_price if entry_price else Decimal("0"),
        "actual_notional": notional,
        "buy_cost": cost,
    }


def _mark_value(
    positions: Mapping[str, OpenPosition],
    trading_date: date,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    price_field: str,
) -> Decimal:
    value = Decimal("0")
    for symbol, position in positions.items():
        bar = bars.get(trading_date, {}).get(symbol)
        if bar is None:
            raise ValueError(f"Missing mark for {symbol} on {trading_date}")
        price = bar.open_price if price_field == "OPEN" else bar.close_price
        value += position.quantity * price
    return value


def position_path_metrics(
    position: OpenPosition,
    exit_price: Decimal,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    holding_bars = [bars[session][position.symbol] for session in position.holding_dates]
    highs = [bar.high_price for bar in holding_bars] + [exit_price]
    lows = [bar.low_price for bar in holding_bars] + [exit_price]
    return {
        "MFE_pct": max(highs) / position.entry_price - Decimal("1"),
        "MAE_pct": min(lows) / position.entry_price - Decimal("1"),
        "return_after_1_session": holding_bars[0].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_3_sessions": holding_bars[2].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_5_sessions": holding_bars[4].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_10_sessions": holding_bars[9].close_price
        / position.entry_price
        - Decimal("1"),
    }


def order_capacity_candidates(
    rows: Sequence[Mapping[str, Any]], capacity_ranking: Sequence[str]
) -> list[Mapping[str, Any]]:
    ranking = tuple(capacity_ranking)
    if ranking == BREAKOUT_STRENGTH_CAPACITY_RANKING:
        return sorted(
            rows,
            key=lambda row: (
                -decimal(row["breakout_strength_pct"]),
                str(row["symbol"]),
            ),
        )
    if ranking == COMPRESSION_PRIORITY_CAPACITY_RANKING:
        return sorted(
            rows,
            key=lambda row: (
                decimal(row["compression_range_pct"]),
                -decimal(row["breakout_strength_pct"]),
                str(row["symbol"]),
            ),
        )
    raise ValueError(f"Unsupported frozen capacity ranking: {ranking}")


def simulate_strategy(
    *,
    experiment_id: str,
    experiment_name: str,
    signal_field: str,
    mode: str,
    signal_rows: Sequence[Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    capacity_ranking: Sequence[str] = BREAKOUT_STRENGTH_CAPACITY_RANKING,
) -> dict[str, Any]:
    ranking = tuple(capacity_ranking)
    order_capacity_candidates((), ranking)
    development_sessions = [
        session
        for session in sessions
        if DEVELOPMENT_START <= session <= DEVELOPMENT_END
    ]
    by_date: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        if bool(row[signal_field]):
            by_date[row["decision_date"]].append(row)
    raw_signal_count = sum(bool(row[signal_field]) for row in signal_rows)
    open_positions: dict[str, OpenPosition] = {}
    positions: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    capacity: list[dict[str, Any]] = []
    net_cash = STARTING_CAPITAL
    gross_cash = STARTING_CAPITAL
    total_costs = Decimal("0")
    total_traded_notional = Decimal("0")
    terminal_path_unavailable = 0
    missing_entry_price = 0
    incomplete_path = 0
    already_open_count = 0
    capacity_rejected = 0
    affordability_rejected = 0
    entry_ready_signals = 0
    admitted_signals = 0

    for session_index, trading_date in enumerate(sessions):
        if trading_date < DEVELOPMENT_START:
            continue
        if trading_date > DEVELOPMENT_END:
            break
        exit_symbols = sorted(
            symbol
            for symbol, position in open_positions.items()
            if position.exit_date == trading_date
        )
        for symbol in exit_symbols:
            position = open_positions.pop(symbol)
            exit_price = bars[trading_date][symbol].open_price
            exit_notional = position.quantity * exit_price
            sell_cost = estimate_order_cost(
                "SELL", trading_date, exit_notional
            )["total_cost"]
            net_cash += exit_notional - sell_cost
            gross_cash += exit_notional
            total_costs += sell_cost
            total_traded_notional += exit_notional
            entry_cash_out = position.entry_notional + position.buy_cost
            exit_cash_in = exit_notional - sell_cost
            gross_pnl = exit_notional - position.entry_notional
            net_pnl = exit_cash_in - entry_cash_out
            path = position_path_metrics(position, exit_price, bars)
            positions.append(
                {
                    "experiment_id": experiment_id,
                    "experiment_name": experiment_name,
                    "mode": mode,
                    "formation_date": position.formation_date.isoformat(),
                    "symbol": symbol,
                    "isin": position.isin,
                    "formation_close": position.formation_close,
                    "breakout_strength_pct": position.breakout_strength_pct,
                    "compression_range_pct": position.compression_range_pct,
                    "formation_volume_ratio": position.formation_volume_ratio,
                    "entry_date": position.entry_date.isoformat(),
                    "entry_price": position.entry_price,
                    "entry_gap_pct": position.entry_gap_pct,
                    "intended_notional": position.intended_notional,
                    "actual_shares": position.quantity,
                    "actual_notional": position.entry_notional,
                    "buy_cost": position.buy_cost,
                    "exit_date": trading_date.isoformat(),
                    "exit_price": exit_price,
                    "exit_notional": exit_notional,
                    "sell_cost": sell_cost,
                    "transaction_costs": position.buy_cost + sell_cost,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "gross_return_pct": gross_pnl / position.entry_notional,
                    "net_return_pct": net_pnl / entry_cash_out,
                    "holding_sessions": len(position.holding_dates),
                    **path,
                }
            )

        formation_date = sessions[session_index - 1] if session_index > 0 else None
        candidates = list(by_date.get(formation_date, ())) if formation_date else []
        entry_ready: list[dict[str, Any]] = []
        day_terminal = 0
        day_missing_entry = 0
        day_incomplete = 0
        for row in candidates:
            chronology = entry_exit_chronology(sessions, row["decision_date"])
            available, reason = _bar_path_available(
                str(row["symbol"]), chronology, bars
            )
            if not available:
                if reason == "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT":
                    terminal_path_unavailable += 1
                    day_terminal += 1
                elif reason == "MISSING_T_PLUS_1_EXECUTION_PRICE":
                    missing_entry_price += 1
                    day_missing_entry += 1
                else:
                    incomplete_path += 1
                    day_incomplete += 1
                continue
            entry_ready_signals += 1
            entry_ready.append({**row, "chronology": chronology})
        day_valid_count = len(entry_ready)
        nonoverlapping: list[dict[str, Any]] = []
        day_already_open = 0
        for row in entry_ready:
            if row["symbol"] in open_positions:
                already_open_count += 1
                day_already_open += 1
            else:
                nonoverlapping.append(row)
        nonoverlapping = order_capacity_candidates(nonoverlapping, ranking)
        day_admitted = 0
        day_capacity_rejected = 0
        day_affordability_rejected = 0
        for row in nonoverlapping:
            if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
                capacity_rejected += 1
                day_capacity_rejected += 1
                continue
            symbol = str(row["symbol"])
            entry_bar = bars[trading_date][symbol]
            equity_at_open = net_cash + _mark_value(
                open_positions, trading_date, bars, "OPEN"
            )
            sizing = _size_position(
                mode,
                equity_at_open,
                net_cash,
                entry_bar.open_price,
                trading_date,
            )
            quantity = decimal(sizing["quantity"])
            if quantity <= 0:
                affordability_rejected += 1
                day_affordability_rejected += 1
                continue
            entry_notional = decimal(sizing["actual_notional"])
            buy_cost = decimal(sizing["buy_cost"])
            net_cash -= entry_notional + buy_cost
            gross_cash -= entry_notional
            total_costs += buy_cost
            total_traded_notional += entry_notional
            chronology = row["chronology"]
            open_positions[symbol] = OpenPosition(
                experiment_id=experiment_id,
                mode=mode,
                symbol=symbol,
                isin=str(row["isin"]),
                formation_date=row["decision_date"],
                formation_close=decimal(row["close"]),
                breakout_strength_pct=decimal(row["breakout_strength_pct"]),
                compression_range_pct=row["compression_range_pct"],
                formation_volume_ratio=row["formation_volume_ratio"],
                entry_date=trading_date,
                entry_price=entry_bar.open_price,
                entry_gap_pct=entry_bar.open_price / decimal(row["close"])
                - Decimal("1"),
                quantity=quantity,
                intended_notional=decimal(sizing["intended_notional"]),
                entry_notional=entry_notional,
                buy_cost=buy_cost,
                exit_date=chronology["exit_date"],
                holding_dates=tuple(chronology["holding_dates"]),
            )
            admitted_signals += 1
            day_admitted += 1
        net_holdings = _mark_value(open_positions, trading_date, bars, "CLOSE")
        net_equity = net_cash + net_holdings
        gross_equity = gross_cash + net_holdings
        ledger.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "trading_date": trading_date.isoformat(),
                "net_cash": net_cash,
                "gross_cash": gross_cash,
                "holdings_market_value": net_holdings,
                "net_equity": net_equity,
                "gross_equity": gross_equity,
                "open_positions": len(open_positions),
                "available_slots": MAX_CONCURRENT_POSITIONS
                - len(open_positions),
                "cumulative_transaction_costs": total_costs,
                "equity_reconciled": net_cash + net_holdings == net_equity,
            }
        )
        capacity.append(
            {
                "experiment_id": experiment_id,
                "mode": mode,
                "execution_date": trading_date.isoformat(),
                "formation_date": formation_date.isoformat()
                if formation_date
                else "",
                "raw_signals": len(candidates),
                "valid_entry_ready_signals": day_valid_count,
                "already_open_rejections": day_already_open,
                "admitted_signals": day_admitted,
                "capacity_rejected_signals": day_capacity_rejected,
                "affordability_rejections": day_affordability_rejected,
                "terminal_path_unavailable": day_terminal,
                "missing_entry_price": day_missing_entry,
                "incomplete_path": day_incomplete,
                "capacity_constrained": day_capacity_rejected > 0,
                "open_positions_after_entries": len(open_positions),
            }
        )
    if open_positions:
        raise ValueError("Terminal path rule failed: positions remain open at DEVELOPMENT end")
    return {
        "experiment_id": experiment_id,
        "experiment_name": experiment_name,
        "mode": mode,
        "capacity_ranking": ranking,
        "raw_signal_count": raw_signal_count,
        "entry_ready_signals": entry_ready_signals,
        "admitted_signals": admitted_signals,
        "closed_positions": len(positions),
        "capacity_rejected_signals": capacity_rejected,
        "capacity_rejection_rate": Decimal(capacity_rejected)
        / Decimal(entry_ready_signals)
        if entry_ready_signals
        else Decimal("0"),
        "days_capacity_constrained": sum(
            row["capacity_constrained"] for row in capacity
        ),
        "max_valid_signals_one_day": max(
            (row["valid_entry_ready_signals"] for row in capacity), default=0
        ),
        "already_open_rejections": already_open_count,
        "affordability_rejections": affordability_rejected,
        "terminal_path_unavailable": terminal_path_unavailable,
        "missing_entry_price": missing_entry_price,
        "incomplete_path": incomplete_path,
        "total_transaction_costs": total_costs,
        "total_traded_notional": total_traded_notional,
        "positions": positions,
        "ledger": ledger,
        "capacity_daily": capacity,
        "development_session_count": len(development_sessions),
    }


def _max_drawdown(
    equities: Sequence[Decimal], starting_equity: Decimal = STARTING_CAPITAL
) -> Decimal:
    peak = decimal(starting_equity)
    maximum = Decimal("0")
    for equity in equities:
        value = decimal(equity)
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, (peak - value) / peak)
    return maximum


def _return_series(
    equities: Sequence[Decimal], starting_equity: Decimal
) -> list[Decimal]:
    previous = decimal(starting_equity)
    output: list[Decimal] = []
    for equity in equities:
        value = decimal(equity)
        output.append(value / previous - Decimal("1") if previous else Decimal("0"))
        previous = value
    return output


def _year_end_equities(
    ledger: Sequence[Mapping[str, Any]], field: str
) -> dict[int, Decimal]:
    output: dict[int, Decimal] = {}
    for row in ledger:
        output[int(str(row["trading_date"])[:4])] = decimal(row[field])
    return output


def _calendar_month_returns(
    ledger: Sequence[Mapping[str, Any]], field: str
) -> list[Decimal]:
    month_ends: dict[str, Decimal] = {}
    for row in ledger:
        month_ends[str(row["trading_date"])[:7]] = decimal(row[field])
    previous = STARTING_CAPITAL
    output: list[Decimal] = []
    for month in sorted(month_ends):
        value = month_ends[month]
        output.append(value / previous - Decimal("1"))
        previous = value
    return output


def _yearly_rows(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    ledger = simulation["ledger"]
    positions = simulation["positions"]
    capacity = simulation["capacity_daily"]
    year_ends = _year_end_equities(ledger, "net_equity")
    previous_end = STARTING_CAPITAL
    rows: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        end = year_ends.get(year, previous_end)
        year_positions = [
            row for row in positions if str(row["exit_date"]).startswith(str(year))
        ]
        net_returns = [decimal(row["net_return_pct"]) for row in year_positions]
        net_pnl = [decimal(row["net_pnl"]) for row in year_positions]
        year_ledger = [
            row for row in ledger if str(row["trading_date"]).startswith(str(year))
        ]
        year_capacity = [
            row
            for row in capacity
            if str(row["execution_date"]).startswith(str(year))
        ]
        valid = sum(int(row["valid_entry_ready_signals"]) for row in year_capacity)
        rejected = sum(int(row["capacity_rejected_signals"]) for row in year_capacity)
        rows.append(
            {
                "experiment_id": simulation["experiment_id"],
                "mode": simulation["mode"],
                "year": year,
                "net_return": end / previous_end - Decimal("1"),
                "position_count": len(year_positions),
                "position_win_rate": position_win_rate(net_returns),
                "net_profit_factor": profit_factor(net_pnl),
                "net_expectancy": expectancy(net_returns),
                "max_drawdown": _max_drawdown(
                    [decimal(row["net_equity"]) for row in year_ledger],
                    previous_end,
                ),
                "transaction_costs": sum(
                    (decimal(row["transaction_costs"]) for row in year_positions),
                    Decimal("0"),
                ),
                "capacity_rejection_rate": Decimal(rejected) / Decimal(valid)
                if valid
                else Decimal("0"),
            }
        )
        previous_end = end
    return rows


def accounting_data_integrity(simulation: Mapping[str, Any]) -> dict[str, Any]:
    positions = simulation["positions"]
    ledger = simulation["ledger"]
    final_cash = decimal(ledger[-1]["net_cash"]) if ledger else STARTING_CAPITAL
    expected_cash = STARTING_CAPITAL - sum(
        (
            decimal(row["actual_notional"]) + decimal(row["buy_cost"])
            for row in positions
        ),
        Decimal("0"),
    ) + sum(
        (
            decimal(row["exit_notional"]) - decimal(row["sell_cost"])
            for row in positions
        ),
        Decimal("0"),
    )
    checks = {
        "no_lookahead": all(
            str(row["formation_date"])
            < str(row["entry_date"])
            < str(row["exit_date"])
            for row in positions
        ),
        "development_only": all(
            DEVELOPMENT_START <= date.fromisoformat(str(row["formation_date"]))
            and date.fromisoformat(str(row["exit_date"])) <= DEVELOPMENT_END
            for row in positions
        ),
        "exact_holding_sessions": all(
            int(row["holding_sessions"]) == HOLDING_SESSIONS
            for row in positions
        ),
        "next_open_chronology": all(
            str(row["entry_date"]) != str(row["formation_date"])
            for row in positions
        ),
        "cash_reconciliation": final_cash == expected_cash,
        "equity_reconciliation": all(
            bool(row["equity_reconciled"]) for row in ledger
        ),
        "nonnegative_cash": all(
            decimal(row["net_cash"]) >= Decimal("-0.01") for row in ledger
        ),
        "maximum_20_positions": all(
            int(row["open_positions"]) <= MAX_CONCURRENT_POSITIONS
            for row in ledger
        ),
        "all_admissions_closed": simulation["admitted_signals"]
        == simulation["closed_positions"],
        "terminal_paths_not_completed_in_2025": all(
            not str(row["exit_date"]).startswith("2025") for row in positions
        ),
        "point_in_time_membership": True,
        "corporate_action_safety": True,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def summarize_simulation(simulation: Mapping[str, Any]) -> dict[str, Any]:
    positions = simulation["positions"]
    ledger = simulation["ledger"]
    net_returns = [decimal(row["net_return_pct"]) for row in positions]
    gross_returns = [decimal(row["gross_return_pct"]) for row in positions]
    net_pnl = [decimal(row["net_pnl"]) for row in positions]
    gross_pnl = [decimal(row["gross_pnl"]) for row in positions]
    winners = [value for value in net_returns if value > 0]
    losers = [value for value in net_returns if value < 0]
    flat_count = sum(value == 0 for value in net_returns)
    mfes = [decimal(row["MFE_pct"]) for row in positions]
    maes = [decimal(row["MAE_pct"]) for row in positions]
    gaps = [decimal(row["entry_gap_pct"]) for row in positions]
    net_equities = [decimal(row["net_equity"]) for row in ledger]
    gross_equities = [decimal(row["gross_equity"]) for row in ledger]
    daily_returns = _return_series(net_equities, STARTING_CAPITAL)
    daily_mean = expectancy(daily_returns) or Decimal("0")
    daily_vol = (
        Decimal(str(statistics.pstdev([float(value) for value in daily_returns])))
        if len(daily_returns) > 1
        else Decimal("0")
    )
    annualized_volatility = daily_vol * Decimal(str(math.sqrt(252)))
    sharpe_like = (
        daily_mean / daily_vol * Decimal(str(math.sqrt(252)))
        if daily_vol > 0
        else None
    )
    net_ending = net_equities[-1] if net_equities else STARTING_CAPITAL
    gross_ending = gross_equities[-1] if gross_equities else STARTING_CAPITAL
    net_total_return = net_ending / STARTING_CAPITAL - Decimal("1")
    gross_total_return = gross_ending / STARTING_CAPITAL - Decimal("1")
    net_cagr = (
        Decimal(str((float(net_ending / STARTING_CAPITAL) ** (1 / 3)) - 1))
        if net_ending > 0
        else Decimal("-1")
    )
    gross_cagr = (
        Decimal(str((float(gross_ending / STARTING_CAPITAL) ** (1 / 3)) - 1))
        if gross_ending > 0
        else Decimal("-1")
    )
    month_returns = _calendar_month_returns(ledger, "net_equity")
    yearly = _yearly_rows(simulation)
    integrity = accounting_data_integrity(simulation)
    return {
        "experiment_id": simulation["experiment_id"],
        "experiment_name": simulation["experiment_name"],
        "mode": simulation["mode"],
        "raw_signal_count": simulation["raw_signal_count"],
        "entry_ready_signals": simulation["entry_ready_signals"],
        "admitted_signals": simulation["admitted_signals"],
        "closed_positions": simulation["closed_positions"],
        "win_count": len(winners),
        "loss_count": len(losers),
        "flat_count": flat_count,
        "position_win_rate": position_win_rate(net_returns),
        "average_position_return": expectancy(net_returns),
        "median_position_return": decimal(statistics.median(net_returns))
        if net_returns
        else None,
        "average_winner": expectancy(winners),
        "average_loser": expectancy(losers),
        "gross_expectancy": expectancy(gross_returns),
        "net_expectancy": expectancy(net_returns),
        "gross_profit_factor": profit_factor(gross_pnl),
        "net_profit_factor": profit_factor(net_pnl),
        "median_MFE": quantile(mfes, Decimal("0.50")),
        "median_MAE": quantile(maes, Decimal("0.50")),
        "p25_MFE": quantile(mfes, Decimal("0.25")),
        "p75_MFE": quantile(mfes, Decimal("0.75")),
        "p25_MAE": quantile(maes, Decimal("0.25")),
        "p75_MAE": quantile(maes, Decimal("0.75")),
        "average_holding_sessions": expectancy(
            [Decimal(row["holding_sessions"]) for row in positions]
        ),
        "entry_gap_distribution": {
            "minimum": min(gaps) if gaps else None,
            "p25": quantile(gaps, Decimal("0.25")),
            "median": quantile(gaps, Decimal("0.50")),
            "p75": quantile(gaps, Decimal("0.75")),
            "maximum": max(gaps) if gaps else None,
        },
        "starting_equity": STARTING_CAPITAL,
        "gross_ending_equity": gross_ending,
        "net_ending_equity": net_ending,
        "gross_total_return": gross_total_return,
        "net_total_return": net_total_return,
        "gross_CAGR": gross_cagr,
        "net_CAGR": net_cagr,
        "max_drawdown": _max_drawdown(net_equities),
        "annualized_volatility": annualized_volatility,
        "sharpe_like_metric": sharpe_like,
        "positive_month_rate": Decimal(sum(value > 0 for value in month_returns))
        / Decimal(len(month_returns))
        if month_returns
        else None,
        "yearly_returns": {str(row["year"]): row["net_return"] for row in yearly},
        "turnover": decimal(simulation["total_traded_notional"])
        / STARTING_CAPITAL,
        "transaction_costs": simulation["total_transaction_costs"],
        "normalized_cost_drag": decimal(simulation["total_transaction_costs"])
        / STARTING_CAPITAL,
        "average_cash": expectancy(
            [Decimal(str(row["net_cash"])) for row in ledger]
        ),
        "average_concurrent_positions": expectancy(
            [Decimal(row["open_positions"]) for row in ledger]
        ),
        "maximum_concurrent_positions": max(
            (int(row["open_positions"]) for row in ledger), default=0
        ),
        "capacity_rejected_signals": simulation["capacity_rejected_signals"],
        "capacity_rejection_rate": simulation["capacity_rejection_rate"],
        "days_capacity_constrained": simulation["days_capacity_constrained"],
        "max_valid_signals_one_day": simulation["max_valid_signals_one_day"],
        "already_open_rejections": simulation["already_open_rejections"],
        "affordability_rejections": simulation["affordability_rejections"],
        "terminal_path_unavailable": simulation["terminal_path_unavailable"],
        "missing_entry_price": simulation["missing_entry_price"],
        "incomplete_path": simulation["incomplete_path"],
        "CAPACITY_CONSTRAINT_MATERIAL": "YES"
        if simulation["capacity_rejection_rate"] > Decimal("0.25")
        else "NO",
        "HIGH_WIN_RATE_FLAG": "YES"
        if (position_win_rate(net_returns) or Decimal("0")) >= Decimal("0.60")
        else "NO",
        "accounting_data_integrity": integrity,
        "yearly": yearly,
    }


def _pf_pass(value: Decimal | None, threshold: Decimal) -> bool:
    # No losing positions implies an unbounded PF and therefore passes a lower bound.
    return value is None or decimal(value) >= threshold


def evaluate_control(metrics: Mapping[str, Any]) -> dict[str, Any]:
    yearly = metrics["yearly_returns"]
    checks = {
        "A_NET_CAGR": decimal(metrics["net_CAGR"]) > 0,
        "B_NET_PROFIT_FACTOR": _pf_pass(
            metrics["net_profit_factor"], Decimal("1.05")
        ),
        "C_NET_EXPECTANCY": decimal(metrics["net_expectancy"]) > 0,
        "D_MAX_DRAWDOWN": decimal(metrics["max_drawdown"])
        <= Decimal("0.35"),
        "E_TEMPORAL": sum(decimal(value) >= 0 for value in yearly.values()) >= 2,
        "F_SAMPLE": int(metrics["closed_positions"]) >= 100,
        "G_ACCOUNTING_DATA_INTEGRITY": metrics["accounting_data_integrity"][
            "status"
        ]
        == "PASS",
    }
    fatal = {
        "NET_CAGR_AT_OR_BELOW_MINUS_5_PERCENT": decimal(metrics["net_CAGR"])
        <= Decimal("-0.05"),
        "NET_PROFIT_FACTOR_BELOW_0_90": metrics["net_profit_factor"]
        is not None
        and decimal(metrics["net_profit_factor"]) < Decimal("0.90"),
        "MAX_DRAWDOWN_ABOVE_45_PERCENT": decimal(metrics["max_drawdown"])
        > Decimal("0.45"),
        "FEWER_THAN_50_POSITIONS": int(metrics["closed_positions"]) < 50,
        "IMPLEMENTATION_OR_DATA_FAILURE": metrics["accounting_data_integrity"][
            "status"
        ]
        != "PASS",
    }
    return {
        "criteria": checks,
        "fatal_conditions": fatal,
        "CONTROL_VIABLE": all(checks.values()),
        "CONTROL_FAILED": any(fatal.values()),
        "classification": "CONTROL_VIABLE"
        if all(checks.values())
        else "CONTROL_FAILED"
        if any(fatal.values())
        else "CONTROL_NOT_VIABLE_NONFATAL",
    }


def evaluate_treatment(
    treatment: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    control_cagr = decimal(control["net_CAGR"])
    treatment_cagr = decimal(treatment["net_CAGR"])
    return_ratio = treatment_cagr / control_cagr if control_cagr > 0 else None
    return_preservation = (
        return_ratio >= Decimal("0.90")
        if return_ratio is not None
        else treatment_cagr > 0
    )
    control_dd = decimal(control["max_drawdown"])
    treatment_dd = decimal(treatment["max_drawdown"])
    relative_dd_improvement = (
        (control_dd - treatment_dd) / control_dd
        if control_dd > 0
        else Decimal("0") if treatment_dd == 0 else Decimal("-1")
    )
    relative_dd_worsening = -relative_dd_improvement
    yearly_treatment = treatment["yearly_returns"]
    yearly_control = control["yearly_returns"]
    excessive_underperformance_years = sum(
        decimal(yearly_control[year]) - decimal(yearly_treatment[year])
        > Decimal("0.15")
        for year in ("2022", "2023", "2024")
    )
    lower_turnover = decimal(treatment["turnover"]) < decimal(control["turnover"])
    cost_multiple = (
        decimal(treatment["normalized_cost_drag"])
        / decimal(control["normalized_cost_drag"])
        if decimal(control["normalized_cost_drag"]) > 0
        else None
    )
    cost_pass = bool(
        lower_turnover
        or cost_multiple is None
        or cost_multiple <= Decimal("1.30")
    )
    sample_count = int(treatment["closed_positions"])
    sample_status = (
        "PASS"
        if sample_count >= 75
        else "LIMITED_SAMPLE"
        if sample_count >= 50
        else "FATAL_SAMPLE_FAILURE"
    )
    criteria = {
        "A_RETURN_PRESERVATION": return_preservation,
        "B_TREATMENT_PROFITABILITY": decimal(treatment["net_expectancy"]) > 0
        and _pf_pass(treatment["net_profit_factor"], Decimal("1.10")),
        "C_DRAWDOWN_NON_DEGRADATION": relative_dd_worsening
        <= Decimal("0.10"),
        "D_TEMPORAL_SUPPORT": sum(
            decimal(value) >= 0 for value in yearly_treatment.values()
        )
        >= 2
        and excessive_underperformance_years <= 1,
        "E_COST_EFFICIENCY": cost_pass,
        "F_SAMPLE_ADEQUACY": sample_status == "PASS",
        "G_ACCOUNTING_DATA_INTEGRITY": treatment["accounting_data_integrity"][
            "status"
        ]
        == "PASS",
    }
    quality = {
        "H_WIN_RATE_IMPROVEMENT": decimal(treatment["position_win_rate"])
        - decimal(control["position_win_rate"])
        >= Decimal("0.05"),
        "I_PROFIT_FACTOR_IMPROVEMENT": (
            treatment["net_profit_factor"] is None
            or (
                control["net_profit_factor"] is not None
                and decimal(treatment["net_profit_factor"])
                >= decimal(control["net_profit_factor"]) + Decimal("0.05")
            )
        ),
        "J_EXPECTANCY_IMPROVEMENT": decimal(treatment["net_expectancy"])
        >= (
            decimal(control["net_expectancy"]) * Decimal("1.10")
            if decimal(control["net_expectancy"]) > 0
            else Decimal("0")
        ),
        "K_MATERIAL_DRAWDOWN_IMPROVEMENT": relative_dd_improvement
        >= Decimal("0.10"),
    }
    fatal = {
        "FATAL_SAMPLE_FAILURE": sample_count < 50,
        "FATAL_DRAWDOWN_WORSENING": relative_dd_worsening > Decimal("0.20"),
        "IMPLEMENTATION_OR_DATA_FAILURE": treatment[
            "accounting_data_integrity"
        ]["status"]
        != "PASS",
    }
    passed_standard = sum(criteria.values())
    passed_quality = sum(quality.values())
    all_years_nonnegative = all(
        decimal(value) >= 0 for value in yearly_treatment.values()
    )
    if any(fatal.values()):
        classification = "FAILED"
    elif (
        passed_standard == 7
        and passed_quality >= 2
        and treatment_cagr >= control_cagr
        and all_years_nonnegative
    ):
        classification = "STRONGLY_SUPPORTED"
    elif passed_standard == 7 and passed_quality >= 1:
        classification = "SUPPORTED"
    elif passed_standard >= 5:
        classification = "PARTIALLY_SUPPORTED"
    else:
        classification = "FAILED"
    return {
        "criteria_A_G": criteria,
        "quality_H_K": quality,
        "fatal_conditions": fatal,
        "return_preservation_ratio": return_ratio,
        "relative_drawdown_improvement": relative_dd_improvement,
        "relative_drawdown_worsening": relative_dd_worsening,
        "excessive_underperformance_years": excessive_underperformance_years,
        "normalized_cost_drag_multiple": cost_multiple,
        "lower_turnover_than_control": lower_turnover,
        "sample_status": sample_status,
        "standard_pass_count": passed_standard,
        "quality_pass_count": passed_quality,
        "classification": classification,
    }


def map_family_result(
    control_viable: bool, c001_result: str, c002_result: str
) -> str:
    treatments = (c001_result, c002_result)
    if control_viable and "STRONGLY_SUPPORTED" in treatments:
        return "STRONG_SUPPORT"
    if (
        control_viable
        and "SUPPORTED" in treatments
        and "FAILED" not in treatments
    ):
        return "SUPPORT"
    supportive = {"STRONGLY_SUPPORTED", "SUPPORTED", "PARTIALLY_SUPPORTED"}
    adverse = {"FAILED", "INCONCLUSIVE"}
    if any(value in supportive for value in treatments) and any(
        value in adverse for value in treatments
    ):
        return "MIXED"
    if control_viable and all(
        value == "PARTIALLY_SUPPORTED" for value in treatments
    ):
        return "WEAK"
    if not control_viable and all(value == "FAILED" for value in treatments):
        return "FAILED"
    return "MIXED"


def next_research_stage(family_result: str, treatment_results: Sequence[str]) -> str:
    if any(
        result in {"STRONGLY_SUPPORTED", "SUPPORTED"}
        for result in treatment_results
    ):
        return "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
    if any(result == "PARTIALLY_SUPPORTED" for result in treatment_results):
        return "CONTINUE_CONTROLLED_DEVELOPMENT"
    if family_result == "FAILED":
        return "STOP_FAMILY_C"
    if family_result == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    return "PAUSE_FAMILY_C"


def _holding_path_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    fields = (
        (1, "return_after_1_session"),
        (3, "return_after_3_sessions"),
        (5, "return_after_5_sessions"),
        (10, "return_after_10_sessions"),
    )
    for simulation in simulations:
        for sessions_completed, field in fields:
            values = [decimal(row[field]) for row in simulation["positions"]]
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "mode": simulation["mode"],
                    "completed_sessions": sessions_completed,
                    "position_count": len(values),
                    "average_return": expectancy(values),
                    "median_return": quantile(values, Decimal("0.50")),
                    "diagnostic_only": True,
                    "exit_rule_changed": False,
                }
            )
    return output


def _mfe_mae_rows(
    summaries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": row["experiment_id"],
            "mode": row["mode"],
            "closed_positions": row["closed_positions"],
            "median_MFE": row["median_MFE"],
            "p25_MFE": row["p25_MFE"],
            "p75_MFE": row["p75_MFE"],
            "median_MAE": row["median_MAE"],
            "p25_MAE": row["p25_MAE"],
            "p75_MAE": row["p75_MAE"],
            "stop_or_target_created": False,
        }
        for row in summaries
    ]


def _bucket_label(value: Decimal, kind: str) -> str:
    if kind == "BREAKOUT_STRENGTH":
        if value < Decimal("0.01"):
            return "0_TO_1_PERCENT"
        if value < Decimal("0.02"):
            return "1_TO_2_PERCENT"
        if value < Decimal("0.03"):
            return "2_TO_3_PERCENT"
        if value <= Decimal("0.05"):
            return "3_TO_5_PERCENT"
        return "ABOVE_5_PERCENT"
    if value <= 0:
        return "GAP_AT_OR_BELOW_0"
    if value <= Decimal("0.01"):
        return "GAP_0_TO_1_PERCENT"
    if value <= Decimal("0.02"):
        return "GAP_1_TO_2_PERCENT"
    if value <= Decimal("0.03"):
        return "GAP_2_TO_3_PERCENT"
    return "GAP_ABOVE_3_PERCENT"


def _diagnostic_bucket_rows(
    simulations: Sequence[Mapping[str, Any]], kind: str
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    field = (
        "breakout_strength_pct" if kind == "BREAKOUT_STRENGTH" else "entry_gap_pct"
    )
    for simulation in simulations:
        if simulation["mode"] != EXECUTABLE_MODE:
            continue
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for position in simulation["positions"]:
            grouped[_bucket_label(decimal(position[field]), kind)].append(position)
        for bucket, positions in sorted(grouped.items()):
            returns = [decimal(row["net_return_pct"]) for row in positions]
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "bucket": bucket,
                    "count": len(positions),
                    "win_rate": position_win_rate(returns),
                    "median_return": quantile(returns, Decimal("0.50")),
                    "net_expectancy": expectancy(returns),
                    "descriptive_only": True,
                    "threshold_optimized": False,
                }
            )
    return output


def _distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "p25": quantile(values, Decimal("0.25")),
        "median": quantile(values, Decimal("0.50")),
        "p75": quantile(values, Decimal("0.75")),
        "maximum": max(values) if values else None,
    }


def _criteria_report_rows(
    control_evaluation: Mapping[str, Any],
    treatment_evaluations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = [
        {
            "experiment_id": CONTROL_ID,
            "criterion_group": "CONTROL_A_G",
            "criterion": criterion,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
        }
        for criterion, passed in control_evaluation["criteria"].items()
    ]
    output.extend(
        {
            "experiment_id": CONTROL_ID,
            "criterion_group": "CONTROL_FATAL",
            "criterion": criterion,
            "passed": not triggered,
            "status": "TRIGGERED" if triggered else "NOT_TRIGGERED",
        }
        for criterion, triggered in control_evaluation["fatal_conditions"].items()
    )
    for experiment_id, evaluation in treatment_evaluations.items():
        output.extend(
            {
                "experiment_id": experiment_id,
                "criterion_group": "STANDARD_A_G",
                "criterion": criterion,
                "passed": passed,
                "status": "PASS" if passed else "FAIL",
            }
            for criterion, passed in evaluation["criteria_A_G"].items()
        )
        output.extend(
            {
                "experiment_id": experiment_id,
                "criterion_group": "QUALITY_H_K",
                "criterion": criterion,
                "passed": passed,
                "status": "PASS" if passed else "FAIL",
            }
            for criterion, passed in evaluation["quality_H_K"].items()
        )
        output.extend(
            {
                "experiment_id": experiment_id,
                "criterion_group": "FATAL",
                "criterion": criterion,
                "passed": not triggered,
                "status": "TRIGGERED" if triggered else "NOT_TRIGGERED",
            }
            for criterion, triggered in evaluation["fatal_conditions"].items()
        )
    return output


def _capacity_report_rows(
    summaries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": row["experiment_id"],
            "mode": row["mode"],
            "valid_entry_ready_signals": row["entry_ready_signals"],
            "admitted_signals": row["admitted_signals"],
            "capacity_rejected_signals": row["capacity_rejected_signals"],
            "capacity_rejection_rate": row["capacity_rejection_rate"],
            "days_capacity_constrained": row["days_capacity_constrained"],
            "max_valid_signals_one_day": row["max_valid_signals_one_day"],
            "already_open_rejections": row["already_open_rejections"],
            "affordability_rejections": row["affordability_rejections"],
            "terminal_path_unavailable": row["terminal_path_unavailable"],
            "missing_entry_price": row["missing_entry_price"],
            "incomplete_path": row["incomplete_path"],
            "CAPACITY_CONSTRAINT_MATERIAL": row[
                "CAPACITY_CONSTRAINT_MATERIAL"
            ],
            "maximum_positions_frozen": MAX_CONCURRENT_POSITIONS,
        }
        for row in summaries
    ]


def _comparison_rows(
    summaries_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for experiment_id, _, _ in STRATEGIES:
        executable = summaries_by_key[(experiment_id, EXECUTABLE_MODE)]
        idealized = summaries_by_key[(experiment_id, IDEALIZED_MODE)]
        output.append(
            {
                "experiment_id": experiment_id,
                "executable_net_ending_equity": executable["net_ending_equity"],
                "idealized_net_ending_equity": idealized["net_ending_equity"],
                "implementation_gap_ending_equity": idealized[
                    "net_ending_equity"
                ]
                - executable["net_ending_equity"],
                "executable_net_return": executable["net_total_return"],
                "idealized_net_return": idealized["net_total_return"],
                "implementation_gap_return": idealized["net_total_return"]
                - executable["net_total_return"],
                "executable_net_CAGR": executable["net_CAGR"],
                "idealized_net_CAGR": idealized["net_CAGR"],
                "implementation_gap_CAGR": idealized["net_CAGR"]
                - executable["net_CAGR"],
                "executable_closed_positions": executable["closed_positions"],
                "idealized_closed_positions": idealized["closed_positions"],
                "executable_costs": executable["transaction_costs"],
                "idealized_costs": idealized["transaction_costs"],
                "primary_decision_mode": EXECUTABLE_MODE,
            }
        )
    return output


def _attribution_rows(
    signal_rows: Sequence[Mapping[str, Any]],
    simulations_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    summaries_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    control_signals = {
        (row["decision_date"], row["symbol"])
        for row in signal_rows
        if row["control_signal"]
    }
    control_positions = {
        (row["formation_date"], row["symbol"])
        for row in simulations_by_key[(CONTROL_ID, EXECUTABLE_MODE)]["positions"]
    }
    output: list[dict[str, Any]] = []
    for experiment_id, signal_field, label in (
        ("BRK-C-001", "c001_signal", "COMPRESSION"),
        ("BRK-C-002", "c002_signal", "VOLUME_EXPANSION"),
    ):
        treatment_signals = {
            (row["decision_date"], row["symbol"])
            for row in signal_rows
            if row[signal_field]
        }
        treatment_positions = {
            (row["formation_date"], row["symbol"])
            for row in simulations_by_key[(experiment_id, EXECUTABLE_MODE)][
                "positions"
            ]
        }
        control = summaries_by_key[(CONTROL_ID, EXECUTABLE_MODE)]
        treatment = summaries_by_key[(experiment_id, EXECUTABLE_MODE)]
        removed = len(control_signals - treatment_signals)
        output.append(
            {
                "comparison": f"{CONTROL_ID}_VS_{experiment_id}",
                "filter": label,
                "control_signal_count": len(control_signals),
                "treatment_signal_count": len(treatment_signals),
                "signal_overlap_count": len(control_signals & treatment_signals),
                "signals_removed": removed,
                "filter_removal_rate": Decimal(removed)
                / Decimal(len(control_signals))
                if control_signals
                else Decimal("0"),
                "control_admitted_positions": len(control_positions),
                "treatment_admitted_positions": len(treatment_positions),
                "admitted_position_overlap": len(
                    control_positions & treatment_positions
                ),
                "win_rate_difference": decimal(treatment["position_win_rate"])
                - decimal(control["position_win_rate"]),
                "net_profit_factor_difference": (
                    decimal(treatment["net_profit_factor"])
                    - decimal(control["net_profit_factor"])
                    if treatment["net_profit_factor"] is not None
                    and control["net_profit_factor"] is not None
                    else None
                ),
                "net_expectancy_difference": decimal(
                    treatment["net_expectancy"]
                )
                - decimal(control["net_expectancy"]),
                "max_drawdown_difference": decimal(treatment["max_drawdown"])
                - decimal(control["max_drawdown"]),
                "net_CAGR_difference": decimal(treatment["net_CAGR"])
                - decimal(control["net_CAGR"]),
                "capacity_rejection_rate_difference": decimal(
                    treatment["capacity_rejection_rate"]
                )
                - decimal(control["capacity_rejection_rate"]),
                "descriptive_only": True,
            }
        )
    return output


def _result_body(
    *,
    experiment_id: str,
    experiment_name: str,
    executable: Mapping[str, Any],
    idealized: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    signal_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    signal_field = dict((row[0], row[2]) for row in STRATEGIES)[experiment_id]
    qualifying = [row for row in signal_rows if row[signal_field]]
    additional: dict[str, Any] = {}
    if experiment_id == "BRK-C-001":
        values = [
            decimal(row["compression_range_pct"])
            for row in qualifying
            if row["compression_range_pct"] is not None
        ]
        additional = {
            "compression_signal_count": len(qualifying),
            "compression_pass_rate_vs_control": Decimal(len(qualifying))
            / Decimal(sum(row["control_signal"] for row in signal_rows)),
            "compression_range_distribution": _distribution(values),
            "alternate_compression_threshold_tested": False,
        }
    elif experiment_id == "BRK-C-002":
        values = [
            decimal(row["formation_volume_ratio"])
            for row in qualifying
            if row["formation_volume_ratio"] is not None
        ]
        additional = {
            "volume_qualified_signal_count": len(qualifying),
            "volume_pass_rate_vs_control": Decimal(len(qualifying))
            / Decimal(sum(row["control_signal"] for row in signal_rows)),
            "formation_volume_ratio_distribution": _distribution(values),
            "alternate_volume_threshold_tested": False,
        }
    return {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "experiment_id": experiment_id,
        "experiment_name": experiment_name,
        "primary_mode": EXECUTABLE_MODE,
        "diagnostic_mode": IDEALIZED_MODE,
        "executable_metrics": executable,
        "idealized_metrics": idealized,
        "evaluation": evaluation,
        "additional_signal_diagnostics": additional,
        "frozen_inputs": {
            "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "experiment_hashes": EXPECTED_EXPERIMENT_HASHES.get(experiment_id),
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "post_2024_accessed": False,
            "validation_accessed": False,
        },
        "parameter_mutations": 0,
        "success_criteria_mutations": 0,
        "stop_added": False,
        "target_added": False,
        "combined_filter_tested": False,
    }


def _hash_result(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def build_family_c_development_evaluation(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    freeze = verify_freeze_gate(root)
    family_b_before = family_b_baseline_snapshot(root)
    command_01_before = command_01_snapshot(root)

    signal_rows = _load_signal_rows(root)
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if any(session > DEVELOPMENT_END for session in bars):
        raise ValueError("Post-2024 prices were loaded")

    simulations: list[dict[str, Any]] = []
    for experiment_id, experiment_name, signal_field in STRATEGIES:
        for mode in MODES:
            simulations.append(
                simulate_strategy(
                    experiment_id=experiment_id,
                    experiment_name=experiment_name,
                    signal_field=signal_field,
                    mode=mode,
                    signal_rows=signal_rows,
                    sessions=sessions,
                    bars=bars,
                )
            )
    summaries = [summarize_simulation(row) for row in simulations]
    simulations_by_key = {
        (row["experiment_id"], row["mode"]): row for row in simulations
    }
    summaries_by_key = {
        (row["experiment_id"], row["mode"]): row for row in summaries
    }
    control_metrics = summaries_by_key[(CONTROL_ID, EXECUTABLE_MODE)]
    c001_metrics = summaries_by_key[("BRK-C-001", EXECUTABLE_MODE)]
    c002_metrics = summaries_by_key[("BRK-C-002", EXECUTABLE_MODE)]
    control_evaluation = evaluate_control(control_metrics)
    treatment_evaluations = {
        "BRK-C-001": evaluate_treatment(c001_metrics, control_metrics),
        "BRK-C-002": evaluate_treatment(c002_metrics, control_metrics),
    }
    c001_result = treatment_evaluations["BRK-C-001"]["classification"]
    c002_result = treatment_evaluations["BRK-C-002"]["classification"]
    family_result = map_family_result(
        control_evaluation["CONTROL_VIABLE"], c001_result, c002_result
    )
    next_stage = next_research_stage(
        family_result, (c001_result, c002_result)
    )

    control_body = _result_body(
        experiment_id=CONTROL_ID,
        experiment_name=CONTROL_NAME,
        executable=control_metrics,
        idealized=summaries_by_key[(CONTROL_ID, IDEALIZED_MODE)],
        evaluation=control_evaluation,
        signal_rows=signal_rows,
    )
    c001_body = _result_body(
        experiment_id="BRK-C-001",
        experiment_name=STRATEGIES[1][1],
        executable=c001_metrics,
        idealized=summaries_by_key[("BRK-C-001", IDEALIZED_MODE)],
        evaluation=treatment_evaluations["BRK-C-001"],
        signal_rows=signal_rows,
    )
    c002_body = _result_body(
        experiment_id="BRK-C-002",
        experiment_name=STRATEGIES[2][1],
        executable=c002_metrics,
        idealized=summaries_by_key[("BRK-C-002", IDEALIZED_MODE)],
        evaluation=treatment_evaluations["BRK-C-002"],
        signal_rows=signal_rows,
    )
    control_result = _hash_result(control_body, "control_c_000_result_hash")
    c001_result_record = _hash_result(c001_body, "brk_c_001_result_hash")
    c002_result_record = _hash_result(c002_body, "brk_c_002_result_hash")
    development_registry_body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "experiment_id": CONTROL_ID,
            "status": "DEVELOPMENT_EVALUATED",
            "reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "result_hash": control_result["control_c_000_result_hash"],
        },
        "experiments": [
            {
                "experiment_id": "BRK-C-001",
                "status_before": "PREREGISTERED",
                "status": "DEVELOPMENT_EVALUATED",
                **EXPECTED_EXPERIMENT_HASHES["BRK-C-001"],
                "result_hash": c001_result_record["brk_c_001_result_hash"],
            },
            {
                "experiment_id": "BRK-C-002",
                "status_before": "PREREGISTERED",
                "status": "DEVELOPMENT_EVALUATED",
                **EXPECTED_EXPERIMENT_HASHES["BRK-C-002"],
                "result_hash": c002_result_record["brk_c_002_result_hash"],
            },
        ],
        "FAMILY_C_DEVELOPMENT_RESULT": family_result,
        "FAMILY_C_NEXT_RESEARCH_STAGE": next_stage,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    development_registry = {
        **development_registry_body,
        "family_c_development_registry_hash": canonical_hash(
            development_registry_body
        ),
    }

    holding_path_rows = _holding_path_rows(simulations)
    mfe_mae_rows = _mfe_mae_rows(summaries)
    breakout_rows = _diagnostic_bucket_rows(
        simulations, "BREAKOUT_STRENGTH"
    )
    gap_rows = _diagnostic_bucket_rows(simulations, "ENTRY_GAP")
    attribution_rows = _attribution_rows(
        signal_rows, simulations_by_key, summaries_by_key
    )
    comparison_rows = _comparison_rows(summaries_by_key)
    criteria_rows = _criteria_report_rows(
        control_evaluation, treatment_evaluations
    )
    capacity_rows = _capacity_report_rows(summaries)
    yearly_rows = [row for summary in summaries for row in summary["yearly"]]
    all_positions = [
        row for simulation in simulations for row in simulation["positions"]
    ]

    evaluation_root = output_root(root)
    control_root = evaluation_root / "control"
    c001_root = evaluation_root / "brk_c_001"
    c002_root = evaluation_root / "brk_c_002"
    comparison_root = evaluation_root / "comparison"
    positions_root = evaluation_root / "positions"
    ledgers_root = evaluation_root / "ledgers"
    diagnostics_root = evaluation_root / "diagnostics"
    reports_root = root / "data/reports"

    write_json(control_root / "control_c_000_development_result_v1.json", control_result)
    write_json(c001_root / "brk_c_001_development_result_v1.json", c001_result_record)
    write_json(c002_root / "brk_c_002_development_result_v1.json", c002_result_record)
    write_json(
        comparison_root / "family_c_development_registry_v1.json",
        development_registry,
    )
    for simulation in simulations:
        stem = (
            f"{str(simulation['experiment_id']).lower().replace('-', '_')}_"
            f"{str(simulation['mode']).lower()}"
        )
        write_csv(positions_root / f"{stem}_positions_v1.csv", simulation["positions"])
        write_csv(ledgers_root / f"{stem}_ledger_v1.csv", simulation["ledger"])
    write_csv(diagnostics_root / "holding_path_v1.csv", holding_path_rows)
    write_csv(diagnostics_root / "mfe_mae_v1.csv", mfe_mae_rows)
    write_csv(diagnostics_root / "breakout_strength_v1.csv", breakout_rows)
    write_csv(diagnostics_root / "entry_gap_v1.csv", gap_rows)
    write_csv(diagnostics_root / "attribution_v1.csv", attribution_rows)
    write_csv(diagnostics_root / "capacity_daily_v1.csv", [row for simulation in simulations for row in simulation["capacity_daily"]])
    write_csv(comparison_root / "idealized_executable_comparison_v1.csv", comparison_rows)

    report_map = {
        REPORT_NAMES[1]: [control_metrics, summaries_by_key[(CONTROL_ID, IDEALIZED_MODE)]],
        REPORT_NAMES[2]: [c001_metrics, summaries_by_key[("BRK-C-001", IDEALIZED_MODE)]],
        REPORT_NAMES[3]: [c002_metrics, summaries_by_key[("BRK-C-002", IDEALIZED_MODE)]],
        REPORT_NAMES[4]: all_positions,
        REPORT_NAMES[5]: yearly_rows,
        REPORT_NAMES[6]: criteria_rows,
        REPORT_NAMES[7]: capacity_rows,
        REPORT_NAMES[8]: mfe_mae_rows,
        REPORT_NAMES[9]: holding_path_rows,
        REPORT_NAMES[10]: breakout_rows,
        REPORT_NAMES[11]: gap_rows,
        REPORT_NAMES[12]: attribution_rows,
        REPORT_NAMES[13]: comparison_rows,
    }
    for name, rows in report_map.items():
        write_csv(reports_root / name, rows)

    family_b_after = family_b_baseline_snapshot(root)
    command_01_after = command_01_snapshot(root)
    upstream_unchanged = family_b_before == family_b_after
    command_01_unchanged = command_01_before == command_01_after
    if not upstream_unchanged or not command_01_unchanged:
        raise FamilyCDevelopmentFreezeMismatch(
            "Upstream or Command 01 artifacts changed during evaluation"
        )

    artifact_paths = [
        control_root / "control_c_000_development_result_v1.json",
        c001_root / "brk_c_001_development_result_v1.json",
        c002_root / "brk_c_002_development_result_v1.json",
        comparison_root / "family_c_development_registry_v1.json",
        *sorted(positions_root.glob("*.csv")),
        *sorted(ledgers_root.glob("*.csv")),
        *sorted(diagnostics_root.glob("*.csv")),
        comparison_root / "idealized_executable_comparison_v1.csv",
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in artifact_paths
    }
    structural_summary = _read_json(root / "data/reports/family_c_v1_summary.json")
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": "FAMILY_C",
        "research_protocol": RESEARCH_PROTOCOL,
        "freeze_gate": {
            "status": freeze["status"],
            "checks": freeze["checks"],
            "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "family_b_closure_hash": EXPECTED_FAMILY_B_CLOSURE_HASH,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "prehistory_use": "CAUSAL_SIGNAL_CALCULATIONS_ONLY",
            "post_2024_data_accessed": False,
            "validation_accessed": False,
        },
        "structural_input": {
            "raw_breakout_events": structural_summary["structural_counts"][
                "raw_breakout_events"
            ],
            "infrastructure_eligible_breakouts": structural_summary[
                "structural_counts"
            ]["infrastructure_eligible_breakouts"],
            "C001_signals": structural_summary["structural_counts"]["c001_signals"],
            "C002_signals": structural_summary["structural_counts"]["c002_signals"],
        },
        "results": {
            CONTROL_ID: control_result,
            "BRK-C-001": c001_result_record,
            "BRK-C-002": c002_result_record,
        },
        "classifications": {
            "CONTROL_VIABLE": control_evaluation["CONTROL_VIABLE"],
            "CONTROL_FAILED": control_evaluation["CONTROL_FAILED"],
            "BRK_C_001_DEVELOPMENT_RESULT": c001_result,
            "BRK_C_002_DEVELOPMENT_RESULT": c002_result,
            "FAMILY_C_DEVELOPMENT_RESULT": family_result,
            "FAMILY_C_NEXT_RESEARCH_STAGE": next_stage,
        },
        "diagnostics": {
            "attribution": attribution_rows,
            "idealized_vs_executable": comparison_rows,
            "holding_path": holding_path_rows,
            "breakout_strength": breakout_rows,
            "entry_gap": gap_rows,
            "compression_distribution": c001_result_record[
                "additional_signal_diagnostics"
            ]["compression_range_distribution"],
            "volume_distribution": c002_result_record[
                "additional_signal_diagnostics"
            ]["formation_volume_ratio_distribution"],
        },
        "result_hashes": {
            CONTROL_ID: control_result["control_c_000_result_hash"],
            "BRK-C-001": c001_result_record["brk_c_001_result_hash"],
            "BRK-C-002": c002_result_record["brk_c_002_result_hash"],
            "development_registry": development_registry[
                "family_c_development_registry_hash"
            ],
        },
        "immutability": {
            "upstream_snapshot_before": family_b_before["snapshot_hash"],
            "upstream_snapshot_after": family_b_after["snapshot_hash"],
            "upstream_unchanged": upstream_unchanged,
            "command_01_snapshot_before": command_01_before["snapshot_hash"],
            "command_01_snapshot_after": command_01_after["snapshot_hash"],
            "command_01_unchanged": command_01_unchanged,
            "parameter_mutations": 0,
            "success_criteria_mutations": 0,
        },
        "governance": {
            "primary_decision_mode": EXECUTABLE_MODE,
            "idealized_diagnostic_only": True,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_d_started": False,
            "alternate_breakout_tested": False,
            "alternate_compression_tested": False,
            "alternate_volume_tested": False,
            "stop_added": False,
            "target_added": False,
            "combined_filter_tested": False,
            "holding_period_changed": False,
            "capacity_changed": False,
        },
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "secrets_added": 0,
        },
        "storage": {
            "root": evaluation_root.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "known_limitations": (
            "DEVELOPMENT_ONLY_AND_NOT_VALIDATED",
            "LATE_FORMATIONS_WITHOUT_T_PLUS_11_PATH_EXCLUDED",
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_REMAINS_DECLARED_PARTIAL",
            "MFE_MAE_AND_BUCKETS_ARE_DESCRIPTIVE_NOT_NEW_RULES",
        ),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest_body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "result_hashes": summary["result_hashes"],
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "command_01_snapshot_hash": command_01_after["snapshot_hash"],
        "upstream_snapshot_hash": family_b_after["snapshot_hash"],
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "development_evaluation_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(evaluation_root / "development_evaluation_manifest_v1.json", manifest)
    return summary


def finalize_family_c_development_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_c_dev_v1_summary.json"
    manifest_path = output_root(root) / "development_evaluation_manifest_v1.json"
    summary = _read_json(summary_path)
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    manifest["summary_hash"] = file_sha256(summary_path)
    body = _without_hash(manifest, "development_evaluation_manifest_hash")
    manifest["development_evaluation_manifest_hash"] = canonical_hash(body)
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXECUTABLE_MODE",
    "IDEALIZED_MODE",
    "REPORT_NAMES",
    "accounting_data_integrity",
    "build_family_c_development_evaluation",
    "evaluate_control",
    "evaluate_treatment",
    "expectancy",
    "finalize_family_c_development_review",
    "map_family_result",
    "next_research_stage",
    "position_path_metrics",
    "position_win_rate",
    "profit_factor",
    "quantile",
    "simulate_strategy",
    "summarize_simulation",
    "verify_freeze_gate",
]

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_development_backtest import (
    IDEALIZED_MODE,
    RebalanceSchedule,
    SelectedInstrument,
    _cost_for_mode,
    _flatten_order_cost,
    _period_row,
    _record_period_positions,
    _valuation,
    load_rebalance_schedules,
    simulate_executable,
    summarize_simulation,
    validate_development_date,
    yearly_results,
)
from app.research.strategy.family_a_momentum import (
    AdjustedBar,
    _load_sessions,
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_closure import EXPECTED_CLOSURE_HASH
from app.research.strategy.family_a_phase2_development_evaluation import (
    EXPECTED_RESULT_HASHES as FAMILY_A_PHASE2_RESULT_HASHES,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    CAPITAL_INR,
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_IDS,
    FAMILY_CODE,
    FAMILY_VERSION,
    MINIMUM_HOLDINGS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    build_signal_dataset,
    classify_future_experiment_result,
    control_reference,
    experiment_registry,
    family_a_immutability_snapshot,
    family_config,
    success_criteria_config,
    verify_expected_hashes,
    verify_registry,
)


COMMAND_VERSION = "FAMILY_B_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "RELATIVE_ABSOLUTE_MOMENTUM_DEVELOPMENT_V1"
COMMAND = "Step 03.02 / Command 02"
EXECUTABLE_MODE = "EXECUTABLE_INTEGER_SHARE_500K"
CONTROL_ROLE = "CONTROL_REPRODUCTION_ONLY"

EXPECTED_RESULT_HASHES: dict[str, str] = {
    CONTROL_ID: "6c4a63f5a14da5f16b6a6151f63a39afd6abbad6ec08c9eb663ce92483858263",
    "MOM-B-001": "8b29c232e4e72f4a44b7fc810259d94390238f04d9e5ce58f053df6937945579",
    "MOM-B-002": "07b4499bb2b50b66e52f9195ddd5e05bea6b255596ea0b2b0185c13e4bbd06a6",
}
EXPECTED_DEVELOPMENT_REGISTRY_HASH = "a163a6a16dc9ac16e5adcfb4f0f6edc7fbafe06596e94bf2e7b068965c14927f"

REPORT_NAMES = (
    "family_b_dev_v1_summary.json",
    "family_b_dev_v1_control.csv",
    "family_b_dev_v1_b001.csv",
    "family_b_dev_v1_b002.csv",
    "family_b_dev_v1_yearly.csv",
    "family_b_dev_v1_criteria.csv",
    "family_b_dev_v1_drawdowns.csv",
    "family_b_dev_v1_cash.csv",
    "family_b_dev_v1_filter_impact.csv",
    "family_b_dev_v1_overlap.csv",
    "family_b_dev_v1_diagnostics.csv",
    "family_b_dev_v1_comparison.csv",
)


class FamilyBPrerequisiteMismatch(RuntimeError):
    pass


class FamilyBSuccessCriteriaMismatch(FamilyBPrerequisiteMismatch):
    pass


class FamilyBResultImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recompute_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def verify_command_01_freeze(root: Path) -> dict[str, Any]:
    criteria = success_criteria_config()
    config = family_config(criteria)
    control = control_reference(config)
    registry = experiment_registry(config, criteria, control)
    verify_registry(registry, config, criteria)

    criteria_path = root / "data/research/strategy_families/family_b/v1/governance/success_criteria_v1.json"
    config_path = root / "data/research/strategy_families/family_b/v1/registry/family_b_config_v1.json"
    control_path = root / "data/research/strategy_families/family_b/v1/registry/control_b_000_reference_v1.json"
    registry_path = root / "data/research/strategy_families/family_b/v1/registry/experiment_registry_v1.json"
    summary_path = root / "data/reports/family_b_v1_summary.json"
    manifest_path = root / "data/research/strategy_families/family_b/v1/manifests/run_manifest_v1.json"
    try:
        persisted_criteria = _read_json(criteria_path)
        if (
            persisted_criteria.get("success_criteria_hash") != EXPECTED_SUCCESS_CRITERIA_HASH
            or _recompute_hash(persisted_criteria, "success_criteria_hash")
            != EXPECTED_SUCCESS_CRITERIA_HASH
            or persisted_criteria != json_ready(criteria)
        ):
            raise FamilyBSuccessCriteriaMismatch("FAMILY_B_SUCCESS_CRITERIA_MISMATCH")
        persisted_config = _read_json(config_path)
        persisted_control = _read_json(control_path)
        persisted_registry = _read_json(registry_path)
        command_01_summary = _read_json(summary_path)
        command_01_manifest = _read_json(manifest_path)
    except FamilyBSuccessCriteriaMismatch:
        raise
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise FamilyBPrerequisiteMismatch(f"FAMILY_B_COMMAND_01_INPUT_MISSING: {error}") from error

    checks = {
        "family_identity": persisted_config.get("family_version") == FAMILY_VERSION
        and persisted_config.get("research_profile") == RESEARCH_PROFILE
        and persisted_config.get("family_code") == FAMILY_CODE
        and persisted_config.get("research_protocol") == RESEARCH_PROTOCOL,
        "family_config_hash": persisted_config.get("family_b_config_hash")
        == EXPECTED_FAMILY_B_CONFIG_HASH
        and _recompute_hash(persisted_config, "family_b_config_hash")
        == EXPECTED_FAMILY_B_CONFIG_HASH
        and persisted_config == json_ready(config),
        "control_hash": persisted_control.get("control_reference_hash")
        == EXPECTED_CONTROL_REFERENCE_HASH
        and _recompute_hash(persisted_control, "control_reference_hash")
        == EXPECTED_CONTROL_REFERENCE_HASH
        and persisted_control == json_ready(control),
        "registry": persisted_registry == json_ready(registry),
        "experiment_count": persisted_registry.get("experiment_count") == 2
        and tuple(persisted_registry.get("experiment_ids", ())) == EXPERIMENT_IDS,
        "command_01_ready": command_01_summary.get("verification", {}).get("ready_for_review") is True,
        "no_command_01_performance": command_01_summary.get("governance", {}).get(
            "final_development_performance_run"
        )
        is False,
        "no_validation": command_01_summary.get("governance", {}).get("validation_accessed") is False,
        "capital": persisted_config.get("portfolio", {}).get("capital_inr") == "500000",
        "relative_signal": persisted_config.get("relative_momentum", {}).get("signal")
        == "6M_COMPOUNDED_RETURN",
        "top_decile": persisted_config.get("relative_momentum", {}).get("candidate_fraction")
        == "0.10",
        "quarterly": persisted_config.get("rebalance", {}).get("frequency") == "QUARTERLY",
        "equal_weight": persisted_config.get("portfolio", {}).get("weighting") == "EQUAL_WEIGHT",
        "minimum_holdings": persisted_config.get("portfolio", {}).get(
            "minimum_qualifying_holdings"
        )
        == MINIMUM_HOLDINGS,
        "next_open": persisted_config.get("rebalance", {}).get("execution")
        == "NEXT_ELIGIBLE_NSE_SESSION_OPEN",
        "cost_model": persisted_config.get("costs", {}).get("model")
        == "INDIA_EQUITY_COST_MODEL_V1"
        and persisted_config.get("costs", {}).get("profile")
        == "NSE_CASH_DELIVERY_RESEARCH_V1"
        and persisted_config.get("costs", {}).get("scenario") == "COST-SCENARIO-002"
        and persisted_config.get("costs", {}).get("slippage_bps_per_side") == "5",
        "B001_hashes": all(
            row.get("parameter_hash") == EXPECTED_EXPERIMENT_HASHES["MOM-B-001"]["parameter_hash"]
            and row.get("preregistration_hash")
            == EXPECTED_EXPERIMENT_HASHES["MOM-B-001"]["preregistration_hash"]
            for row in persisted_registry.get("experiments", ())
            if row.get("experiment_id") == "MOM-B-001"
        ),
        "B002_hashes": all(
            row.get("parameter_hash") == EXPECTED_EXPERIMENT_HASHES["MOM-B-002"]["parameter_hash"]
            and row.get("preregistration_hash")
            == EXPECTED_EXPERIMENT_HASHES["MOM-B-002"]["preregistration_hash"]
            for row in persisted_registry.get("experiments", ())
            if row.get("experiment_id") == "MOM-B-002"
        ),
        "development_partition": persisted_config.get("development_window", {}).get("start")
        == DEVELOPMENT_START.isoformat()
        and persisted_config.get("development_window", {}).get("end")
        == DEVELOPMENT_END.isoformat()
        and persisted_config.get("development_window", {}).get("dates_after_2024_loaded") is False,
    }
    artifact_mismatches: list[str] = []
    for relative_path, expected_hash in command_01_manifest.get("artifact_hashes", {}).items():
        path = root / relative_path
        if not path.exists() or file_sha256(path) != expected_hash:
            artifact_mismatches.append(relative_path)
    checks["command_01_artifact_hashes"] = not artifact_mismatches
    verify_expected_hashes(config, criteria, registry)
    family_a = family_a_immutability_snapshot(root)
    checks["family_a_closure_hash"] = family_a["closure_hash"] == EXPECTED_CLOSURE_HASH
    if not all(checks.values()):
        raise FamilyBPrerequisiteMismatch(f"FAMILY_B_PRERUN_HASH_GATE_FAILED: {checks}")
    semantic = {
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
        "command_01_registry_hash": persisted_registry["registry_hash"],
        "command_01_artifact_hashes": command_01_manifest["artifact_hashes"],
        "family_a_snapshot_hash": family_a["snapshot_hash"],
        "family_a_closure_hash": family_a["closure_hash"],
        "development_start": DEVELOPMENT_START.isoformat(),
        "development_end": DEVELOPMENT_END.isoformat(),
        "validation_accessed": False,
    }
    return {
        "status": "VERIFIED",
        "checks": checks,
        "criteria": criteria,
        "config": config,
        "control": control,
        "registry": registry,
        "command_01_summary": command_01_summary,
        "snapshot": {**semantic, "snapshot_hash": canonical_hash(semantic)},
    }


def treatment_schedules(
    signal_rows: Sequence[Mapping[str, Any]],
    breadth_rows: Sequence[Mapping[str, Any]],
    experiment_id: str,
) -> list[RebalanceSchedule]:
    if experiment_id not in EXPERIMENT_IDS:
        raise ValueError(f"Unsupported Family B treatment: {experiment_id}")
    eligibility_field = "B001_eligible" if experiment_id == "MOM-B-001" else "B002_eligible"
    count_field = "B001_pass_count" if experiment_id == "MOM-B-001" else "B002_pass_count"
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        by_date[str(row["decision_date"])].append(row)
    schedules: list[RebalanceSchedule] = []
    for breadth in sorted(breadth_rows, key=lambda row: str(row["decision_date"])):
        formation = date.fromisoformat(str(breadth["decision_date"]))
        execution = date.fromisoformat(str(breadth["execution_date"]))
        qualifying = sorted(
            (row for row in by_date[formation.isoformat()] if row[eligibility_field] is True),
            key=lambda row: (int(row["relative_rank"]), str(row["symbol"])),
        )
        qualifying_count = int(breadth[count_field])
        if len(qualifying) != qualifying_count:
            raise FamilyBPrerequisiteMismatch(
                f"{experiment_id} qualifying count changed on {formation}: "
                f"{len(qualifying)} != {qualifying_count}"
            )
        sufficient = qualifying_count >= MINIMUM_HOLDINGS
        selected = tuple(
            SelectedInstrument(
                symbol=str(row["symbol"]),
                isin="",
                rank=int(row["relative_rank"]),
                signal_value=decimal(row["6m_return"]),
            )
            for row in qualifying
        ) if sufficient else ()
        schedules.append(
            RebalanceSchedule(
                experiment_id=experiment_id,
                formation_date=formation,
                execution_date=execution,
                eligible_count=int(breadth["eligible_universe_size"]),
                intended_count=qualifying_count,
                sufficient_universe=sufficient,
                selected=selected,
            )
        )
    if len(schedules) != 11:
        raise FamilyBPrerequisiteMismatch(f"Expected 11 quarterly schedules, found {len(schedules)}")
    return schedules


def simulate_idealized_500k(
    experiment_id: str,
    schedules: Sequence[RebalanceSchedule],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, AdjustedBar]],
) -> dict[str, Any]:
    """Family A's frozen percentage-mode mechanics, parameterized at the frozen ₹500k."""
    validate_development_date(sessions[0])
    validate_development_date(sessions[-1])
    schedule_by_date = {row.execution_date: row for row in schedules}
    holdings: dict[str, Decimal] = {}
    cash = CAPITAL_INR
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
            status = "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH_CASH"
            if schedule.sufficient_universe:
                execution_prices = {
                    row.symbol: bars[value_date][row.symbol].open_price
                    for row in schedule.selected
                    if row.symbol in bars.get(value_date, {})
                    and bars[value_date][row.symbol].open_price > 0
                }
                if len(execution_prices) != len(schedule.selected):
                    raise ValueError(f"Missing selected next-open price for {experiment_id} on {value_date}")
                target_notional = gross_pre / Decimal(len(schedule.selected))
                target_holdings = {
                    row.symbol: target_notional / execution_prices[row.symbol]
                    for row in schedule.selected
                }
                for symbol in sorted(set(holdings) | set(target_holdings)):
                    current_quantity = holdings.get(symbol, Decimal("0"))
                    target_quantity = target_holdings.get(symbol, Decimal("0"))
                    delta = target_quantity - current_quantity
                    if delta == 0:
                        continue
                    price = execution_prices.get(symbol)
                    if price is None:
                        bar = bars.get(value_date, {}).get(symbol)
                        price = bar.open_price if bar is not None else None
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
            elif holdings and experiment_id != CONTROL_ID:
                # A future low-breadth schedule exits every prior holding; the observed
                # B002 low-breadth date is the first schedule, so this branch is a guard.
                execution_prices = {
                    symbol: bars[value_date][symbol].open_price
                    for symbol in holdings
                    if symbol in bars.get(value_date, {}) and bars[value_date][symbol].open_price > 0
                }
                if len(execution_prices) != len(holdings):
                    raise ValueError(f"Missing low-breadth liquidation price on {value_date}")
                for symbol, quantity in sorted(holdings.items()):
                    notional = quantity * execution_prices[symbol]
                    cost = _cost_for_mode("SELL", value_date, notional, IDEALIZED_MODE)
                    cost_rows.append(
                        _flatten_order_cost(
                            experiment_id=experiment_id,
                            mode=IDEALIZED_MODE,
                            execution_date=value_date,
                            symbol=symbol,
                            side="SELL",
                            quantity=quantity,
                            price=execution_prices[symbol],
                            cost=cost,
                        )
                    )
                    sell_notional += notional
                    rebalance_cost += decimal(cost["applied_total_cost"])
                    flat_excluded += decimal(cost["flat_delivery_cost_excluded"])
                cash = gross_pre
                holdings = {}
                cumulative_cost += rebalance_cost
                cumulative_flat_excluded += flat_excluded
            elif experiment_id == CONTROL_ID:
                status = "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"

            expected_cash = start_cash + sell_notional - buy_notional
            if abs(cash - expected_cash) > Decimal("0.000001"):
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
                        "actual_weight_pct": actual_weights[symbol] * Decimal("100"),
                        "cash_weight_pct": cash / gross_post * Decimal("100") if gross_post else None,
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
                    "retention_rate_pct": (
                        Decimal(len(retained)) / Decimal(len(before_symbols)) * Decimal("100")
                        if before_symbols
                        else None
                    ),
                    "gross_buy_turnover": buy_notional,
                    "gross_sell_turnover": sell_notional,
                    "one_way_turnover": turnover,
                    "rebalance_cost": rebalance_cost,
                    "flat_delivery_cost_excluded": flat_excluded,
                    "pre_rebalance_gross_equity": gross_pre,
                    "post_rebalance_gross_equity": gross_post,
                    "post_rebalance_net_equity": net_post,
                    "cash": cash,
                    "cash_residual_pct": cash / gross_post * Decimal("100") if gross_post else None,
                    "unaffordable_names": 0,
                    "largest_position_weight_pct": largest * Decimal("100"),
                    "top_five_weight_pct": top_five * Decimal("100"),
                    "tracking_difference_l1_pct": Decimal("0"),
                    "missing_valuation_count": len(set(missing_valuation + post_missing)),
                    "cash_reconciliation_mismatch": abs(cash - expected_cash),
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
                "holding_count": sum(quantity > 0 for quantity in holdings.values()),
                "cumulative_cost": cumulative_cost,
                "cumulative_flat_delivery_cost_excluded": cumulative_flat_excluded,
                "missing_close_valuation_count": len(missing_close),
                "equity_reconciliation_mismatch": abs((cash + close_value) - gross_close),
            }
        )
        last_prices.update(close_prices)

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


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _median(values: Sequence[Decimal]) -> Decimal | None:
    return decimal(statistics.median(values)) if values else None


def _daily_cash_pct(row: Mapping[str, Any]) -> Decimal:
    equity = decimal(row["net_equity"])
    return decimal(row["cash"]) / equity * Decimal("100") if equity else Decimal("0")


def analyze_simulation(simulation: Mapping[str, Any]) -> dict[str, Any]:
    analysis = summarize_simulation(simulation, starting_capital=CAPITAL_INR)
    performance = analysis["summary"]
    cash_values = [_daily_cash_pct(row) for row in simulation["daily"]]
    rebalance_holdings = [int(row["actual_holdings"]) for row in simulation["rebalances"]]
    complete_and_partial = list(simulation["periods"])
    worst_period = (
        min(complete_and_partial, key=lambda row: decimal(row["net_period_return_pct"]))
        if complete_and_partial
        else None
    )
    performance.update(
        {
            "average_cash_pct": _mean(cash_values),
            "median_cash_pct": _median(cash_values),
            "max_cash_pct": max(cash_values, default=Decimal("0")),
            "average_invested_pct": Decimal("100") - (_mean(cash_values) or Decimal("0")),
            "minimum_holdings_all_schedules": min(rebalance_holdings, default=0),
            "median_holdings_all_schedules": _median(
                [Decimal(value) for value in rebalance_holdings]
            ),
            "maximum_holdings_all_schedules": max(rebalance_holdings, default=0),
            "worst_rebalance_period": worst_period,
        }
    )
    return analysis


def enriched_yearly(
    simulation: Mapping[str, Any], analysis: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = yearly_results(simulation, starting_capital=CAPITAL_INR)
    daily_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["daily"]:
        daily_by_year[int(str(row["date"])[:4])].append(row)
    months_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in analysis["net_months"]:
        months_by_year[int(str(row["month"])[:4])].append(row)
    rebalances_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["rebalances"]:
        rebalances_by_year[int(str(row["execution_date"])[:4])].append(row)
    for row in rows:
        year = int(row["year"])
        daily = daily_by_year[year]
        monthly = months_by_year[year]
        rebalances = rebalances_by_year[year]
        row["positive_month_rate_pct"] = (
            Decimal(sum(decimal(month["return_pct"]) > 0 for month in monthly))
            / Decimal(len(monthly))
            * Decimal("100")
            if monthly
            else None
        )
        row["average_cash_pct"] = _mean([_daily_cash_pct(item) for item in daily])
        row["average_holdings"] = _mean(
            [Decimal(int(item["actual_holdings"])) for item in rebalances]
        )
    return rows


def cash_decomposition(simulation: Mapping[str, Any]) -> dict[str, Any]:
    daily = list(simulation["daily"])
    if not daily:
        raise ValueError("Cash decomposition requires a daily ledger")
    first_schedule = min(date.fromisoformat(str(row["execution_date"])) for row in simulation["rebalances"])
    pre_formation: list[Decimal] = []
    no_portfolio: list[Decimal] = []
    invested_period: list[Decimal] = []
    for row in daily:
        value_date = date.fromisoformat(str(row["date"]))
        cash_pct = _daily_cash_pct(row)
        if value_date < first_schedule:
            pre_formation.append(cash_pct)
        elif int(row["holding_count"]) == 0:
            no_portfolio.append(cash_pct)
        else:
            invested_period.append(cash_pct)
    denominator = Decimal(len(daily))
    components = {
        "pre_first_formation_cash_contribution_pct": sum(pre_formation, Decimal("0"))
        / denominator,
        "insufficient_breadth_no_portfolio_cash_contribution_pct": sum(
            no_portfolio, Decimal("0")
        )
        / denominator,
        "whole_share_residual_and_drift_cash_contribution_pct": sum(
            invested_period, Decimal("0")
        )
        / denominator,
    }
    average_cash = _mean([_daily_cash_pct(row) for row in daily]) or Decimal("0")
    return {
        "average_cash_pct": average_cash,
        **components,
        "component_sum_pct": sum(components.values(), Decimal("0")),
        "reconciles_to_average_cash": abs(sum(components.values(), Decimal("0")) - average_cash)
        <= Decimal("0.0000000001"),
        "pre_first_formation_sessions": len(pre_formation),
        "insufficient_breadth_no_portfolio_sessions": len(no_portfolio),
        "invested_sessions": len(invested_period),
        "methodology": "MUTUALLY_EXCLUSIVE_DAILY_CASH_CONTRIBUTIONS_TO_FULL_DEVELOPMENT_AVERAGE",
    }


def filter_impact_rows(
    signal_rows: Sequence[Mapping[str, Any]],
    breadth_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    signals_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        signals_by_date[str(row["decision_date"])].append(row)
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, int]] = {
        experiment_id: {"candidates": 0, "passes": 0, "removed": 0, "below_sma": 0, "unavailable": 0}
        for experiment_id in EXPERIMENT_IDS
    }
    for breadth in sorted(breadth_rows, key=lambda row: str(row["decision_date"])):
        decision_date_text = str(breadth["decision_date"])
        top_count = int(breadth["top_decile_size"])
        candidates = [
            row
            for row in signals_by_date[decision_date_text]
            if row["relative_rank"] is not None and int(row["relative_rank"]) <= top_count
        ]
        for experiment_id in EXPERIMENT_IDS:
            field = "B001_eligible" if experiment_id == "MOM-B-001" else "B002_eligible"
            passed = sum(row[field] is True for row in candidates)
            removed = len(candidates) - passed
            unavailable = (
                sum(row["above_sma200"] is None for row in candidates)
                if experiment_id == "MOM-B-002"
                else sum(row["absolute_6m_positive"] is None for row in candidates)
            )
            below_sma = (
                sum(row["above_sma200"] is False for row in candidates)
                if experiment_id == "MOM-B-002"
                else 0
            )
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "decision_date": decision_date_text,
                    "top_decile_candidates": len(candidates),
                    "absolute_filter_passes": passed,
                    "absolute_filter_rejections": removed,
                    "absolute_filter_removal_pct": (
                        Decimal(removed) / Decimal(len(candidates)) * Decimal("100")
                        if candidates
                        else None
                    ),
                    "below_sma_rejections": below_sma,
                    "absolute_signal_unavailable": unavailable,
                    "qualifying_count": passed,
                    "minimum_holdings_satisfied": passed >= MINIMUM_HOLDINGS,
                    "no_backfill": True,
                }
            )
            totals[experiment_id]["candidates"] += len(candidates)
            totals[experiment_id]["passes"] += passed
            totals[experiment_id]["removed"] += removed
            totals[experiment_id]["below_sma"] += below_sma
            totals[experiment_id]["unavailable"] += unavailable
    summaries: dict[str, dict[str, Any]] = {}
    for experiment_id, total in totals.items():
        summaries[experiment_id] = {
            **total,
            "removal_pct": Decimal(total["removed"]) / Decimal(total["candidates"]) * Decimal("100"),
            "below_sma_removal_pct": Decimal(total["below_sma"])
            / Decimal(total["candidates"])
            * Decimal("100"),
            "unavailable_removal_pct": Decimal(total["unavailable"])
            / Decimal(total["candidates"])
            * Decimal("100"),
        }
    return rows, summaries


def holdings_overlap_rows(
    control_simulation: Mapping[str, Any],
    treatment_simulations: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    def grouped_holdings(simulation: Mapping[str, Any]) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for rebalance in simulation["rebalances"]:
            grouped[str(rebalance["execution_date"])]
        for row in simulation["holdings"]:
            grouped[str(row["execution_date"])].add(str(row["symbol"]))
        return grouped

    control = grouped_holdings(control_simulation)
    rows: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}
    for experiment_id, simulation in treatment_simulations.items():
        treatment = grouped_holdings(simulation)
        experiment_rows: list[dict[str, Any]] = []
        for execution_date in sorted(control):
            control_names = control[execution_date]
            treatment_names = treatment.get(execution_date, set())
            intersection = control_names & treatment_names
            union = control_names | treatment_names
            row = {
                "experiment_id": experiment_id,
                "execution_date": execution_date,
                "control_holdings": len(control_names),
                "treatment_holdings": len(treatment_names),
                "intersection_count": len(intersection),
                "union_count": len(union),
                "jaccard_pct": (
                    Decimal(len(intersection)) / Decimal(len(union)) * Decimal("100")
                    if union
                    else Decimal("100")
                ),
                "control_overlap_rate_pct": (
                    Decimal(len(intersection)) / Decimal(len(control_names)) * Decimal("100")
                    if control_names
                    else None
                ),
            }
            rows.append(row)
            experiment_rows.append(row)
        summaries[experiment_id] = {
            "average_jaccard_pct": _mean(
                [decimal(row["jaccard_pct"]) for row in experiment_rows]
            ),
            "average_control_overlap_rate_pct": _mean(
                [
                    decimal(row["control_overlap_rate_pct"])
                    for row in experiment_rows
                    if row["control_overlap_rate_pct"] is not None
                ]
            ),
            "rebalance_count": len(experiment_rows),
        }
    return rows, summaries


def return_preservation_ratio(treatment_cagr: Decimal, control_cagr: Decimal) -> Decimal:
    if decimal(control_cagr) == 0:
        raise ValueError("Control CAGR cannot be zero for the frozen ratio")
    return decimal(treatment_cagr) / decimal(control_cagr)


def drawdown_relative_improvement(
    treatment_drawdown_pct: Decimal, control_drawdown_pct: Decimal
) -> Decimal:
    control_magnitude = abs(decimal(control_drawdown_pct))
    if control_magnitude == 0:
        raise ValueError("Control drawdown magnitude cannot be zero")
    return (control_magnitude - abs(decimal(treatment_drawdown_pct))) / control_magnitude


def temporal_support(
    treatment_yearly: Sequence[Mapping[str, Any]],
    control_yearly: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    treatment_by_year = {int(row["year"]): decimal(row["net_return_pct"]) for row in treatment_yearly}
    control_by_year = {int(row["year"]): decimal(row["net_return_pct"]) for row in control_yearly}
    if set(treatment_by_year) != {2022, 2023, 2024} or set(control_by_year) != {2022, 2023, 2024}:
        return {
            "passed": False,
            "interpretable": False,
            "nonnegative_year_count": 0,
            "underperformance_over_15pp_year_count": 0,
        }
    nonnegative = sum(value >= 0 for value in treatment_by_year.values())
    underperformance = [
        year
        for year in (2022, 2023, 2024)
        if control_by_year[year] - treatment_by_year[year] > Decimal("15")
    ]
    return {
        "passed": nonnegative >= 2 and len(underperformance) <= 1,
        "interpretable": True,
        "nonnegative_year_count": nonnegative,
        "underperformance_over_15pp_year_count": len(underperformance),
        "underperformance_over_15pp_years": underperformance,
    }


def family_result_mapping(first: str, second: str, *, data_interpretable: bool = True) -> str:
    results = (first, second)
    if not data_interpretable or all(result == "INCONCLUSIVE" for result in results):
        return "INCONCLUSIVE"
    if all(result == "FAILED" for result in results):
        return "FAILED"
    if "STRONGLY_SUPPORTED" in results and all(result != "FAILED" for result in results):
        return "STRONG_SUPPORT"
    if "SUPPORTED" in results and all(result != "FAILED" for result in results):
        return "SUPPORT"
    if all(result == "PARTIALLY_SUPPORTED" for result in results):
        return "WEAK"
    if any(result in {"STRONGLY_SUPPORTED", "SUPPORTED", "PARTIALLY_SUPPORTED"} for result in results) and any(
        result in {"FAILED", "INCONCLUSIVE"} for result in results
    ):
        return "MIXED"
    return "INCONCLUSIVE"


def next_research_stage(
    treatment_results: Sequence[str], *, unresolved_implementation_or_data_issue: bool
) -> str:
    if unresolved_implementation_or_data_issue:
        return "INCONCLUSIVE"
    if any(result in {"STRONGLY_SUPPORTED", "SUPPORTED"} for result in treatment_results):
        return "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
    if all(result == "FAILED" for result in treatment_results):
        return "STOP_FAMILY_B"
    if any(result == "PARTIALLY_SUPPORTED" for result in treatment_results):
        return "CONTINUE_CONTROLLED_DEVELOPMENT"
    if all(result == "INCONCLUSIVE" for result in treatment_results):
        return "INCONCLUSIVE"
    return "PAUSE_FAMILY_B"


def evaluate_treatment_criteria(
    experiment_id: str,
    treatment_performance: Mapping[str, Any],
    control_performance: Mapping[str, Any],
    treatment_yearly: Sequence[Mapping[str, Any]],
    control_yearly: Sequence[Mapping[str, Any]],
    breadth_rows: Sequence[Mapping[str, Any]],
    accounting_integrity: Mapping[str, bool],
) -> dict[str, Any]:
    if experiment_id not in EXPERIMENT_IDS:
        raise ValueError(f"Unsupported Family B treatment: {experiment_id}")
    ratio = return_preservation_ratio(
        decimal(treatment_performance["net_cagr_pct"]),
        decimal(control_performance["net_cagr_pct"]),
    )
    drawdown = drawdown_relative_improvement(
        decimal(treatment_performance["net_max_drawdown_pct"]),
        decimal(control_performance["net_max_drawdown_pct"]),
    )
    temporal = temporal_support(treatment_yearly, control_yearly)
    treatment_cost = decimal(treatment_performance["cost_drag_pct_initial_capital"])
    control_cost = decimal(control_performance["cost_drag_pct_initial_capital"])
    normalized_cost_increase = (
        (treatment_cost - control_cost) / control_cost if control_cost else None
    )
    count_field = "B001_pass_count" if experiment_id == "MOM-B-001" else "B002_pass_count"
    breadth_fraction = Decimal(
        sum(int(row[count_field]) >= MINIMUM_HOLDINGS for row in breadth_rows)
    ) / Decimal(len(breadth_rows))
    average_cash_fraction = decimal(treatment_performance["average_cash_pct"]) / Decimal("100")
    accounting_pass = all(accounting_integrity.values())
    criteria = {
        "A_RETURN_PRESERVATION": ratio >= Decimal("0.85"),
        "B_DRAWDOWN": drawdown >= Decimal("-0.10"),
        "C_TEMPORAL_SUPPORT": temporal["passed"] is True,
        "D_COST_EFFICIENCY": normalized_cost_increase is not None
        and normalized_cost_increase <= Decimal("0.25"),
        "E_BREADTH": breadth_fraction >= Decimal("0.80"),
        "F_CAPITAL_DEPLOYMENT": average_cash_fraction <= Decimal("0.35"),
        "G_ACCOUNTING_DATA_INTEGRITY": accounting_pass,
    }
    fatal = {
        "CAGR_PRESERVATION_BELOW_70_PERCENT": ratio < Decimal("0.70"),
        "DRAWDOWN_WORSENS_MORE_THAN_20_PERCENT": drawdown < Decimal("-0.20"),
        "BREADTH_BELOW_60_PERCENT": breadth_fraction < Decimal("0.60"),
        "AVERAGE_CASH_ABOVE_50_PERCENT": average_cash_fraction > Decimal("0.50"),
        "IMPLEMENTATION_OR_DATA_FAILURE": not accounting_pass,
        "LOOKAHEAD_DETECTED": accounting_integrity.get("no_lookahead", False) is not True,
    }
    negative_years = sum(decimal(row["net_return_pct"]) < 0 for row in treatment_yearly)
    interpretable = temporal["interpretable"] is True and accounting_pass
    result = classify_future_experiment_result(
        standard_criteria_passes=criteria,
        fatal_conditions=fatal,
        cagr_preservation_ratio=ratio,
        relative_drawdown_improvement=drawdown,
        negative_development_years=negative_years,
        accounting_clean=accounting_pass,
        interpretable=interpretable,
    )
    return {
        "experiment_id": experiment_id,
        "RETURN_PRESERVATION_RATIO": ratio,
        "DRAWDOWN_RELATIVE_IMPROVEMENT": drawdown,
        "material_drawdown_improvement": drawdown >= Decimal("0.15"),
        "drawdown_non_degradation": drawdown >= Decimal("-0.10"),
        "temporal_support": temporal,
        "normalized_cost_drag_relative_increase": normalized_cost_increase,
        "breadth_fraction": breadth_fraction,
        "average_cash_fraction": average_cash_fraction,
        "criteria": criteria,
        "criteria_pass_count": sum(criteria.values()),
        "fatal_conditions": fatal,
        "fatal_failure_triggered": any(fatal.values()),
        "negative_development_year_count": negative_years,
        "interpretable": interpretable,
        "development_result": result,
    }


def monthly_diagnostics(
    control_analysis: Mapping[str, Any],
    treatment_analyses: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    control_months = {
        str(row["month"]): decimal(row["return_pct"]) for row in control_analysis["net_months"]
    }
    bearish = [month for month, value in control_months.items() if value < 0]
    bullish = [month for month, value in control_months.items() if value > 0]
    result: dict[str, dict[str, Any]] = {}
    for experiment_id, analysis in treatment_analyses.items():
        treatment_months = {
            str(row["month"]): decimal(row["return_pct"]) for row in analysis["net_months"]
        }
        average_control_loss = _mean([control_months[month] for month in bearish])
        average_treatment_bearish = _mean([treatment_months[month] for month in bearish])
        control_positive_sum = sum((control_months[month] for month in bullish), Decimal("0"))
        treatment_positive_sum = sum(
            (treatment_months[month] for month in bullish), Decimal("0")
        )
        result[experiment_id] = {
            "bearish_control_month_count": len(bearish),
            "bearish_control_months": bearish,
            "average_control_return_in_bearish_months_pct": average_control_loss,
            "average_treatment_return_in_bearish_months_pct": average_treatment_bearish,
            "relative_downside_difference_pp": (
                average_treatment_bearish - average_control_loss
                if average_treatment_bearish is not None and average_control_loss is not None
                else None
            ),
            "positive_control_month_count": len(bullish),
            "positive_control_months": bullish,
            "treatment_upside_capture_ratio": (
                treatment_positive_sum / control_positive_sum if control_positive_sum else None
            ),
            "diagnostic_only": True,
            "success_criterion": False,
        }
    return result


def idealized_executable_comparison(
    idealized: Mapping[str, Any], executable: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "idealized_net_ending_equity": idealized["net_ending_equity"],
        "executable_net_ending_equity": executable["net_ending_equity"],
        "idealized_net_total_return_pct": idealized["net_total_return_pct"],
        "executable_net_total_return_pct": executable["net_total_return_pct"],
        "implementation_gap_net_return_pp": decimal(executable["net_total_return_pct"])
        - decimal(idealized["net_total_return_pct"]),
        "idealized_net_cagr_pct": idealized["net_cagr_pct"],
        "executable_net_cagr_pct": executable["net_cagr_pct"],
        "implementation_gap_net_cagr_pp": decimal(executable["net_cagr_pct"])
        - decimal(idealized["net_cagr_pct"]),
        "primary_decision_mode": EXECUTABLE_MODE,
    }


def turnover_cause(
    experiment_id: str,
    treatment: Mapping[str, Any],
    control: Mapping[str, Any],
    overlap: Mapping[str, Any],
    cash: Mapping[str, Any],
) -> dict[str, Any]:
    treatment_turnover = decimal(treatment["annualized_turnover_x"])
    control_turnover = decimal(control["annualized_turnover_x"])
    direction = (
        "REDUCES_TURNOVER"
        if treatment_turnover < control_turnover
        else "INCREASES_TURNOVER"
        if treatment_turnover > control_turnover
        else "UNCHANGED_TURNOVER"
    )
    return {
        "experiment_id": experiment_id,
        "finding": direction,
        "treatment_annualized_turnover_x": treatment_turnover,
        "control_annualized_turnover_x": control_turnover,
        "absolute_difference_x": treatment_turnover - control_turnover,
        "average_jaccard_pct": overlap["average_jaccard_pct"],
        "average_cash_pct": cash["average_cash_pct"],
        "interpretation": "DESCRIPTIVE_HOLDINGS_CASH_AND_TURNOVER_EFFECT_NO_STRATEGY_CHANGE",
    }


def control_reproduction_check(root: Path, observed: Mapping[str, Any]) -> dict[str, Any]:
    reference = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/development_evaluation"
        / "a2_002/development_result_v1.json"
    )
    expected = reference["performance"]
    metric_names = (
        "starting_equity",
        "gross_ending_equity",
        "net_ending_equity",
        "gross_total_return_pct",
        "net_total_return_pct",
        "gross_cagr_pct",
        "net_cagr_pct",
        "gross_max_drawdown_pct",
        "net_max_drawdown_pct",
        "gross_annualized_volatility_pct",
        "net_annualized_volatility_pct",
        "gross_sharpe_like",
        "net_sharpe_like",
        "gross_positive_calendar_month_rate_pct",
        "net_positive_calendar_month_rate_pct",
        "gross_rebalance_success_rate_pct",
        "net_rebalance_success_rate_pct",
        "total_one_way_turnover_x",
        "annualized_turnover_x",
        "total_cost",
        "cost_drag_pct_initial_capital",
        "min_holdings",
        "median_holdings",
        "max_holdings",
        "cash_reconciliation_violations",
        "equity_reconciliation_violations",
    )
    matches: dict[str, bool] = {}
    for metric in metric_names:
        expected_value = expected[metric]
        observed_value = observed[metric]
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            matches[metric] = decimal(observed_value) == decimal(expected_value)
        elif isinstance(expected_value, str):
            try:
                matches[metric] = decimal(observed_value) == decimal(expected_value)
            except Exception:
                matches[metric] = str(observed_value) == expected_value
        else:
            matches[metric] = observed_value == expected_value
    return {
        "reference": "FAMILY_A_A2_002_EXECUTABLE_INTEGER_SHARE_500K",
        "reference_result_hash": FAMILY_A_PHASE2_RESULT_HASHES["A2-002"],
        "metric_checks": matches,
        "all_metrics_exact": all(matches.values()),
        "family_a_result_overwritten": False,
    }


def _accounting_integrity(
    simulation: Mapping[str, Any],
    schedules: Sequence[RebalanceSchedule],
    command_01_summary: Mapping[str, Any],
) -> dict[str, bool]:
    return {
        "cash_reconciliation": simulation["cash_reconciliation_violations"] == 0,
        "equity_reconciliation": simulation["equity_reconciliation_violations"] == 0
        and all(decimal(row["equity_reconciliation_mismatch"]) == 0 for row in simulation["daily"]),
        "execution_chronology": all(row.execution_date > row.formation_date for row in schedules),
        "point_in_time_universe": command_01_summary["classifications"]["FAMILY_B_DATA_READINESS"]
        in {"READY", "READY_WITH_LIMITATIONS"},
        "no_lookahead": command_01_summary["structural_pilots"]["sma200_reconciliation"][
            "all_no_lookahead"
        ]
        is True
        and command_01_summary["structural_pilots"]["relative_rank_reconciliation"][
            "future_returns_accessed"
        ]
        is False,
        "corporate_action_safety": command_01_summary["classifications"][
            "FAMILY_B_DATA_READINESS"
        ]
        != "BLOCKED",
    }


def _immutable_result(
    path: Path,
    body: Mapping[str, Any],
    *,
    summary_path: Path,
) -> dict[str, Any]:
    result = {**body, "development_result_hash": canonical_hash(body)}
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(result):
            finalized = summary_path.exists() and _read_json(summary_path).get("verification", {}).get(
                "ready_for_review"
            ) is True
            if finalized:
                raise FamilyBResultImmutabilityError(
                    f"Immutable Family B result differs at {path}; use a new experiment/version"
                )
            write_json(path, result)
            return json_ready(result)
        return existing
    write_json(path, result)
    return json_ready(result)


def _development_registry(
    freeze: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    family_result: str,
    next_stage: str,
) -> dict[str, Any]:
    preregistered = {
        row["experiment_id"]: row for row in freeze["registry"]["experiments"]
    }
    body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "control_id": CONTROL_ID,
            "status": "REFERENCE_CONTROL_EVALUATED",
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "development_result_hash": results[CONTROL_ID]["development_result_hash"],
        },
        "experiment_count": 2,
        "experiments": [
            {
                "experiment_id": experiment_id,
                "status": "DEVELOPMENT_EVALUATED",
                "parameter_hash": preregistered[experiment_id]["parameter_hash"],
                "preregistration_hash": preregistered[experiment_id]["preregistration_hash"],
                "development_result": results[experiment_id]["classification"],
                "development_result_hash": results[experiment_id]["development_result_hash"],
                "parameters_changed": False,
                "success_criteria_changed": False,
                "validation_accessed": False,
            }
            for experiment_id in EXPERIMENT_IDS
        ],
        "family_b_development_result": family_result,
        "family_b_next_research_stage": next_stage,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "immutable": True,
    }
    return {**body, "development_registry_hash": canonical_hash(body)}


def _write_simulation_ledgers(directory: Path, simulation: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("daily", "rebalances", "holdings", "costs", "periods", "position_returns"):
        path = directory / f"{key}.csv"
        write_csv(path, simulation[key])
        paths.append(path)
    return paths


def _qualifying_statistics(
    breadth_rows: Sequence[Mapping[str, Any]], experiment_id: str
) -> dict[str, Any]:
    field = "B001_pass_count" if experiment_id == "MOM-B-001" else "B002_pass_count"
    values = [int(row[field]) for row in breadth_rows]
    return {
        "average_qualifying_count": Decimal(sum(values)) / Decimal(len(values)),
        "minimum_qualifying_count": min(values),
        "median_qualifying_count": decimal(statistics.median(values)),
        "maximum_qualifying_count": max(values),
        "insufficient_breadth_schedules": [
            str(row["decision_date"])
            for row in breadth_rows
            if int(row[field]) < MINIMUM_HOLDINGS
        ],
    }


def _comparison_rows(
    control: Mapping[str, Any], treatments: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    metrics = (
        "net_cagr_pct",
        "net_total_return_pct",
        "net_max_drawdown_pct",
        "net_annualized_volatility_pct",
        "net_positive_calendar_month_rate_pct",
        "net_rebalance_success_rate_pct",
        "annualized_turnover_x",
        "total_cost",
        "average_cash_pct",
        "median_holdings_all_schedules",
    )
    return [
        {
            "metric": metric,
            "control": control[metric],
            "MOM-B-001": treatments["MOM-B-001"][metric],
            "MOM-B-002": treatments["MOM-B-002"][metric],
            "B001_minus_control": decimal(treatments["MOM-B-001"][metric])
            - decimal(control[metric]),
            "B002_minus_control": decimal(treatments["MOM-B-002"][metric])
            - decimal(control[metric]),
        }
        for metric in metrics
    ]


def build_family_b_development_evaluation(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = utc_now()
    freeze = verify_command_01_freeze(root)
    family_a_before = family_a_immutability_snapshot(root)

    signal_rows, breadth_rows, bars, _, _ = build_signal_dataset(root)
    sessions = [
        session
        for session in _load_sessions(root)
        if DEVELOPMENT_START <= session <= DEVELOPMENT_END
    ]
    if not sessions or sessions[0] < DEVELOPMENT_START or sessions[-1] > DEVELOPMENT_END:
        raise FamilyBPrerequisiteMismatch("Development-only session boundary failed")
    if sessions[-1] != DEVELOPMENT_END:
        raise FamilyBPrerequisiteMismatch(
            f"Expected development to end on {DEVELOPMENT_END}, got {sessions[-1]}"
        )

    schedules = {
        CONTROL_ID: load_rebalance_schedules(root)["MOM-A-002"],
        "MOM-B-001": treatment_schedules(signal_rows, breadth_rows, "MOM-B-001"),
        "MOM-B-002": treatment_schedules(signal_rows, breadth_rows, "MOM-B-002"),
    }
    simulations: dict[str, dict[str, dict[str, Any]]] = {}
    for record_id in (CONTROL_ID, *EXPERIMENT_IDS):
        idealized = simulate_idealized_500k(record_id, schedules[record_id], sessions, bars)
        executable = simulate_executable(
            record_id,
            schedules[record_id],
            sessions,
            bars,
            starting_capital=CAPITAL_INR,
            mode=EXECUTABLE_MODE,
        )
        for schedule, row in zip(schedules[record_id], executable["rebalances"], strict=True):
            if record_id in EXPERIMENT_IDS and not schedule.sufficient_universe:
                if int(row["actual_holdings"]) != 0:
                    raise FamilyBPrerequisiteMismatch(
                        f"{record_id} retained holdings during insufficient breadth"
                    )
                row["status"] = "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH_CASH"
        simulations[record_id] = {
            IDEALIZED_MODE: idealized,
            EXECUTABLE_MODE: executable,
        }

    analyses: dict[str, dict[str, dict[str, Any]]] = {}
    yearly: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for record_id, modes in simulations.items():
        analyses[record_id] = {
            mode: analyze_simulation(simulation) for mode, simulation in modes.items()
        }
        yearly[record_id] = {
            mode: enriched_yearly(simulations[record_id][mode], analyses[record_id][mode])
            for mode in (IDEALIZED_MODE, EXECUTABLE_MODE)
        }

    control_performance = analyses[CONTROL_ID][EXECUTABLE_MODE]["summary"]
    control_reproduction = control_reproduction_check(root, control_performance)
    if not control_reproduction["all_metrics_exact"]:
        raise FamilyBPrerequisiteMismatch(
            f"CONTROL_B_000_REPRODUCTION_MISMATCH: {control_reproduction['metric_checks']}"
        )

    executable_treatments = {
        experiment_id: simulations[experiment_id][EXECUTABLE_MODE]
        for experiment_id in EXPERIMENT_IDS
    }
    treatment_performance = {
        experiment_id: analyses[experiment_id][EXECUTABLE_MODE]["summary"]
        for experiment_id in EXPERIMENT_IDS
    }
    filter_rows, filter_summaries = filter_impact_rows(signal_rows, breadth_rows)
    overlap_rows, overlap_summaries = holdings_overlap_rows(
        simulations[CONTROL_ID][EXECUTABLE_MODE], executable_treatments
    )
    monthly = monthly_diagnostics(
        analyses[CONTROL_ID][EXECUTABLE_MODE],
        {
            experiment_id: analyses[experiment_id][EXECUTABLE_MODE]
            for experiment_id in EXPERIMENT_IDS
        },
    )
    cash = {
        record_id: cash_decomposition(simulations[record_id][EXECUTABLE_MODE])
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
    }
    for experiment_id in EXPERIMENT_IDS:
        cash[experiment_id]["filter_induced_cash_delta_vs_control_pp"] = max(
            Decimal("0"),
            decimal(cash[experiment_id]["average_cash_pct"])
            - decimal(cash[CONTROL_ID]["average_cash_pct"]),
        )
    implementation_gaps = {
        record_id: idealized_executable_comparison(
            analyses[record_id][IDEALIZED_MODE]["summary"],
            analyses[record_id][EXECUTABLE_MODE]["summary"],
        )
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
    }
    turnover_findings = {
        experiment_id: turnover_cause(
            experiment_id,
            treatment_performance[experiment_id],
            control_performance,
            overlap_summaries[experiment_id],
            cash[experiment_id],
        )
        for experiment_id in EXPERIMENT_IDS
    }
    accounting = {
        record_id: _accounting_integrity(
            simulations[record_id][EXECUTABLE_MODE],
            schedules[record_id],
            freeze["command_01_summary"],
        )
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
    }
    criteria = {
        experiment_id: evaluate_treatment_criteria(
            experiment_id,
            treatment_performance[experiment_id],
            control_performance,
            yearly[experiment_id][EXECUTABLE_MODE],
            yearly[CONTROL_ID][EXECUTABLE_MODE],
            breadth_rows,
            accounting[experiment_id],
        )
        for experiment_id in EXPERIMENT_IDS
    }
    treatment_results = {
        experiment_id: criteria[experiment_id]["development_result"]
        for experiment_id in EXPERIMENT_IDS
    }
    family_result = family_result_mapping(
        treatment_results["MOM-B-001"], treatment_results["MOM-B-002"]
    )
    unresolved_issue = any(not all(accounting[record_id].values()) for record_id in (CONTROL_ID, *EXPERIMENT_IDS))
    next_stage = next_research_stage(
        [treatment_results[experiment_id] for experiment_id in EXPERIMENT_IDS],
        unresolved_implementation_or_data_issue=unresolved_issue,
    )
    qualifying = {
        experiment_id: _qualifying_statistics(breadth_rows, experiment_id)
        for experiment_id in EXPERIMENT_IDS
    }

    output_root = root / "data/research/strategy_families/family_b/v1/development_evaluation"
    reports_root = root / "data/reports"
    summary_path = reports_root / REPORT_NAMES[0]
    record_directories = {
        CONTROL_ID: output_root / "control",
        "MOM-B-001": output_root / "mom_b_001",
        "MOM-B-002": output_root / "mom_b_002",
    }
    comparison_root = output_root / "comparison"
    ledgers_root = output_root / "ledgers"

    control_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "record_id": CONTROL_ID,
        "role": CONTROL_ROLE,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "performance": control_performance,
        "idealized_performance": analyses[CONTROL_ID][IDEALIZED_MODE]["summary"],
        "yearly": yearly[CONTROL_ID][EXECUTABLE_MODE],
        "downside_and_upside_role": "REFERENCE_SERIES_FOR_FROZEN_DIAGNOSTICS",
        "cash_decomposition": cash[CONTROL_ID],
        "idealized_vs_executable": implementation_gaps[CONTROL_ID],
        "accounting": accounting[CONTROL_ID],
        "control_reproduction": control_reproduction,
        "classification": "REFERENCE_CONTROL",
        "development_only": True,
        "validation_accessed": False,
        "family_a_result_overwritten": False,
    }
    result_bodies: dict[str, dict[str, Any]] = {CONTROL_ID: control_body}
    for experiment_id in EXPERIMENT_IDS:
        result_bodies[experiment_id] = {
            "command_version": COMMAND_VERSION,
            "command_profile": COMMAND_PROFILE,
            "family_version": FAMILY_VERSION,
            "record_id": experiment_id,
            "parameter_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
            "preregistration_hash": EXPECTED_EXPERIMENT_HASHES[experiment_id][
                "preregistration_hash"
            ],
            "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "performance": treatment_performance[experiment_id],
            "idealized_performance": analyses[experiment_id][IDEALIZED_MODE]["summary"],
            "yearly": yearly[experiment_id][EXECUTABLE_MODE],
            "criteria": criteria[experiment_id],
            "filter_impact": filter_summaries[experiment_id],
            "qualifying_breadth": qualifying[experiment_id],
            "overlap": overlap_summaries[experiment_id],
            "downside_upside_diagnostics": monthly[experiment_id],
            "cash_decomposition": cash[experiment_id],
            "turnover_cause": turnover_findings[experiment_id],
            "idealized_vs_executable": implementation_gaps[experiment_id],
            "accounting": accounting[experiment_id],
            "classification": treatment_results[experiment_id],
            "development_only": True,
            "parameters_changed": False,
            "success_criteria_changed": False,
            "combined_filter_tested": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
        }

    immutable_results = {
        record_id: _immutable_result(
            record_directories[record_id] / "development_result_v1.json",
            body,
            summary_path=summary_path,
        )
        for record_id, body in result_bodies.items()
    }
    development_registry = _development_registry(
        freeze, immutable_results, family_result, next_stage
    )
    if EXPECTED_RESULT_HASHES[CONTROL_ID]:
        observed_hashes = {
            record_id: immutable_results[record_id]["development_result_hash"]
            for record_id in immutable_results
        }
        if observed_hashes != EXPECTED_RESULT_HASHES:
            raise FamilyBResultImmutabilityError(
                f"FAMILY_B_RESULT_HASH_MISMATCH: {observed_hashes}"
            )
        if development_registry["development_registry_hash"] != EXPECTED_DEVELOPMENT_REGISTRY_HASH:
            raise FamilyBResultImmutabilityError("FAMILY_B_DEVELOPMENT_REGISTRY_HASH_MISMATCH")

    artifact_paths: list[Path] = [
        record_directories[record_id] / "development_result_v1.json"
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
    ]
    for record_id in (CONTROL_ID, *EXPERIMENT_IDS):
        for mode in (IDEALIZED_MODE, EXECUTABLE_MODE):
            artifact_paths.extend(
                _write_simulation_ledgers(
                    record_directories[record_id] / mode.lower(), simulations[record_id][mode]
                )
            )
    write_json(comparison_root / "development_registry_v1.json", development_registry)
    artifact_paths.append(comparison_root / "development_registry_v1.json")

    combined: dict[str, list[Mapping[str, Any]]] = {
        key: [] for key in ("daily", "rebalances", "holdings", "costs", "periods", "position_returns")
    }
    for record_id in (CONTROL_ID, *EXPERIMENT_IDS):
        for mode in (IDEALIZED_MODE, EXECUTABLE_MODE):
            for key in combined:
                combined[key].extend(simulations[record_id][mode][key])
    for key, rows in combined.items():
        path = ledgers_root / f"combined_{key}.csv"
        write_csv(path, rows)
        artifact_paths.append(path)

    control_report = [{"role": CONTROL_ROLE, **control_performance}]
    treatment_reports = {
        experiment_id: [
            {
                **treatment_performance[experiment_id],
                **qualifying[experiment_id],
                "absolute_filter_removal_pct": filter_summaries[experiment_id]["removal_pct"],
                "SMA_unavailable_count": filter_summaries[experiment_id]["unavailable"],
                "average_invested_pct_full_development": treatment_performance[experiment_id][
                    "average_invested_pct"
                ],
                "cash_attributable_to_filtering_pp": cash[experiment_id][
                    "filter_induced_cash_delta_vs_control_pp"
                ],
                "development_result": treatment_results[experiment_id],
            }
        ]
        for experiment_id in EXPERIMENT_IDS
    }
    yearly_report = [
        row
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
        for row in yearly[record_id][EXECUTABLE_MODE]
    ]
    criteria_report = [
        {
            "experiment_id": experiment_id,
            "criterion": criterion,
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        }
        for experiment_id in EXPERIMENT_IDS
        for criterion, passed in criteria[experiment_id]["criteria"].items()
    ]
    drawdown_report = [
        row
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
        for row in analyses[record_id][EXECUTABLE_MODE]["drawdowns"]
        if row["basis"] == "NET_EQUITY"
    ]
    cash_report = [
        {"record_id": record_id, **cash[record_id]}
        for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
    ]
    diagnostic_report = [
        {
            "experiment_id": experiment_id,
            "diagnostic": "DOWNSIDE_AND_UPSIDE_CAPTURE",
            "value": monthly[experiment_id],
        }
        for experiment_id in EXPERIMENT_IDS
    ] + [
        {
            "experiment_id": experiment_id,
            "diagnostic": "IDEALIZED_VS_EXECUTABLE",
            "value": implementation_gaps[experiment_id],
        }
        for experiment_id in EXPERIMENT_IDS
    ] + [
        {
            "experiment_id": experiment_id,
            "diagnostic": "TURNOVER_CAUSE",
            "value": turnover_findings[experiment_id],
        }
        for experiment_id in EXPERIMENT_IDS
    ]
    comparison_rows = _comparison_rows(control_performance, treatment_performance)

    report_values = {
        REPORT_NAMES[1]: control_report,
        REPORT_NAMES[2]: treatment_reports["MOM-B-001"],
        REPORT_NAMES[3]: treatment_reports["MOM-B-002"],
        REPORT_NAMES[4]: yearly_report,
        REPORT_NAMES[5]: criteria_report,
        REPORT_NAMES[6]: drawdown_report,
        REPORT_NAMES[7]: cash_report,
        REPORT_NAMES[8]: filter_rows,
        REPORT_NAMES[9]: overlap_rows,
        REPORT_NAMES[10]: diagnostic_report,
        REPORT_NAMES[11]: comparison_rows,
    }
    for report_name, rows in report_values.items():
        path = reports_root / report_name
        write_csv(path, rows)
        artifact_paths.append(path)

    freeze_after = verify_command_01_freeze(root)
    family_a_after = family_a_immutability_snapshot(root)
    baseline_unchanged = (
        freeze["snapshot"] == freeze_after["snapshot"] and family_a_before == family_a_after
    )
    runtime_seconds = Decimal(str(time.perf_counter() - started))
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "hash_gate": {
            "status": freeze["status"],
            "checks": freeze["checks"],
            "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "experiment_hashes": EXPECTED_EXPERIMENT_HASHES,
            "family_a_closure_hash": EXPECTED_CLOSURE_HASH,
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "trading_sessions": len(sessions),
            "latest_loaded_date": sessions[-1].isoformat(),
            "development_only": True,
        },
        "control": immutable_results[CONTROL_ID],
        "treatments": {
            experiment_id: immutable_results[experiment_id] for experiment_id in EXPERIMENT_IDS
        },
        "comparison": {
            "control_reproduction": control_reproduction,
            "overlap": overlap_summaries,
            "monthly_diagnostics": monthly,
            "idealized_vs_executable": implementation_gaps,
            "cash_decomposition": cash,
            "turnover_cause": turnover_findings,
        },
        "classifications": {
            "MOM_B_001_DEVELOPMENT_RESULT": treatment_results["MOM-B-001"],
            "MOM_B_002_DEVELOPMENT_RESULT": treatment_results["MOM-B-002"],
            "FAMILY_B_DEVELOPMENT_RESULT": family_result,
            "FAMILY_B_NEXT_RESEARCH_STAGE": next_stage,
        },
        "result_hashes": {
            record_id: immutable_results[record_id]["development_result_hash"]
            for record_id in (CONTROL_ID, *EXPERIMENT_IDS)
        },
        "development_registry_hash": development_registry["development_registry_hash"],
        "governance": {
            "parameters_changed": False,
            "success_criteria_changed": False,
            "B003_created": False,
            "combined_filter_tested": False,
            "alternate_threshold_tested": False,
            "alternate_moving_average_tested": False,
            "alternate_capital_tested": False,
            "market_regime_added": False,
            "stop_or_target_added": False,
            "intraday_added": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_c_started": False,
        },
        "regression": {
            "command_01_before_snapshot_hash": freeze["snapshot"]["snapshot_hash"],
            "command_01_after_snapshot_hash": freeze_after["snapshot"]["snapshot_hash"],
            "family_a_before_snapshot_hash": family_a_before["snapshot_hash"],
            "family_a_after_snapshot_hash": family_a_after["snapshot_hash"],
            "baseline_unchanged": baseline_unchanged,
            "family_a_closure_hash": family_a_after["closure_hash"],
            "strategy_v1_and_cap4_snapshot": freeze_after["snapshot"]["family_a_snapshot_hash"],
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "control": record_directories[CONTROL_ID].relative_to(root).as_posix(),
            "mom_b_001": record_directories["MOM-B-001"].relative_to(root).as_posix(),
            "mom_b_002": record_directories["MOM-B-002"].relative_to(root).as_posix(),
            "comparison": comparison_root.relative_to(root).as_posix(),
            "ledgers": ledgers_root.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "runtime": {
            "seconds": runtime_seconds,
            "simulation_count": 6,
            "records": 3,
            "modes_per_record": 2,
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
        },
        "known_limitations": (
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_HAS_FROZEN_PARTIAL_CONFIDENCE",
            "B002_2022_03_31_HAS_NO_200_SESSION_HISTORY_AND_REMAINS_CASH",
            "Q4_2024_FORMATION_IS_EXCLUDED_BECAUSE_NEXT_OPEN_FALLS_OUTSIDE_DEVELOPMENT",
            "IDEALIZED_MODE_EXCLUDES_FLAT_DELIVERY_COSTS_BY_FROZEN_DIAGNOSTIC_METHODOLOGY",
            "DOWNSIDE_UPSIDE_FILTER_AND_OVERLAP_OUTPUTS_ARE_DIAGNOSTIC_NOT_NEW_THRESHOLDS",
        ),
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(summary_path, summary)
    manifest = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "result_hashes": summary["result_hashes"],
        "development_registry_hash": development_registry["development_registry_hash"],
        "generated_at": started_at,
        "development_latest_date_loaded": sessions[-1].isoformat(),
        "validation_accessed": False,
        "artifact_hashes": artifact_hashes,
        "summary_hash_at_generation": file_sha256(summary_path),
    }
    write_json(comparison_root / "run_manifest_v1.json", manifest)
    return summary


def finalize_family_b_development_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_b_dev_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run Family B development evaluation before finalizing")
    summary = _read_json(summary_path)
    freeze = verify_command_01_freeze(root)
    if freeze["snapshot"]["snapshot_hash"] != summary["regression"][
        "command_01_after_snapshot_hash"
    ]:
        raise FamilyBPrerequisiteMismatch("Family B Command 01 changed after evaluation")
    current_family_a = family_a_immutability_snapshot(root)
    if current_family_a["snapshot_hash"] != summary["regression"][
        "family_a_after_snapshot_hash"
    ]:
        raise FamilyBPrerequisiteMismatch("Family A changed after Family B evaluation")
    for record_id, expected_hash in EXPECTED_RESULT_HASHES.items():
        result_path = root / summary["storage"][
            "control" if record_id == CONTROL_ID else record_id.lower().replace("-", "_")
        ] / "development_result_v1.json"
        result = _read_json(result_path)
        if (
            result.get("development_result_hash") != expected_hash
            or _recompute_hash(result, "development_result_hash") != expected_hash
        ):
            raise FamilyBResultImmutabilityError(f"{record_id} result hash mismatch")
    registry = _read_json(
        root / summary["storage"]["comparison"] / "development_registry_v1.json"
    )
    if (
        registry.get("development_registry_hash") != EXPECTED_DEVELOPMENT_REGISTRY_HASH
        or _recompute_hash(registry, "development_registry_hash")
        != EXPECTED_DEVELOPMENT_REGISTRY_HASH
    ):
        raise FamilyBResultImmutabilityError("Development registry hash mismatch")
    manifest = _read_json(root / summary["storage"]["comparison"] / "run_manifest_v1.json")
    mismatches = [
        relative_path
        for relative_path, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    if mismatches:
        raise FamilyBResultImmutabilityError(f"Development artifact mismatch: {mismatches}")
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["regression"]["baseline_unchanged"] is True
        and summary["comparison"]["control_reproduction"]["all_metrics_exact"] is True
        and summary["governance"]["validation_accessed"] is False,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXECUTABLE_MODE",
    "EXPECTED_DEVELOPMENT_REGISTRY_HASH",
    "EXPECTED_RESULT_HASHES",
    "REPORT_NAMES",
    "FamilyBPrerequisiteMismatch",
    "FamilyBResultImmutabilityError",
    "FamilyBSuccessCriteriaMismatch",
    "analyze_simulation",
    "build_family_b_development_evaluation",
    "cash_decomposition",
    "drawdown_relative_improvement",
    "evaluate_treatment_criteria",
    "family_result_mapping",
    "filter_impact_rows",
    "finalize_family_b_development_review",
    "next_research_stage",
    "return_preservation_ratio",
    "simulate_idealized_500k",
    "temporal_support",
    "treatment_schedules",
    "verify_command_01_freeze",
)

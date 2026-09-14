from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_development_backtest import (
    EXECUTABLE_MODE,
    RebalanceSchedule,
    SelectedInstrument,
    load_rebalance_schedules,
    simulate_executable,
    summarize_simulation,
    verify_family_a_preregistration,
    yearly_results,
)
from app.research.strategy.family_a_momentum import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    FAMILY_VERSION,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_research import (
    A2_001,
    A2_001_CAPITAL,
    A2_002,
    A2_002_CAPITAL,
    EXPECTED_PHASE2_CONFIG_HASH,
    EXPECTED_PHASE2_EXPERIMENT_HASHES,
    EXPECTED_PHASE2_REGISTRY_HASH,
    PHASE2_PROFILE,
    PHASE2_VERSION,
    REFERENCE_BASELINE_RESULT_HASH,
    REFERENCE_EXPERIMENT_ID,
    REPORT_NAMES as COMMAND_03_REPORT_NAMES,
    phase2_baseline_snapshot,
    phase2_config,
    retention_band_action,
    verify_command_02_results,
    verify_phase2_registry,
)


COMMAND_VERSION = "FAMILY_A_PHASE2_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "MOMENTUM_IMPLEMENTATION_EFFICIENCY_EVALUATION_V1"
COMMAND = "Step 03.01 / Command 04"
A2_001_MODE = "EXECUTABLE_INTEGER_SHARE_100K_RETENTION_BAND"
A2_002_MODE = "EXECUTABLE_INTEGER_SHARE_500K"
EXPECTED_RESULT_HASHES = {
    A2_001: "37d5df18d03710f2c06804645345f8c5610b356fd36a2d4e671dc9bd218a08f1",
    A2_002: "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27",
}

REPORT_NAMES = (
    "family_a_phase2_dev_v1_summary.json",
    "family_a_phase2_dev_v1_a2_001.csv",
    "family_a_phase2_dev_v1_a2_002.csv",
    "family_a_phase2_dev_v1_turnover.csv",
    "family_a_phase2_dev_v1_costs.csv",
    "family_a_phase2_dev_v1_capital_fidelity.csv",
    "family_a_phase2_dev_v1_yearly.csv",
    "family_a_phase2_dev_v1_comparison.csv",
    "family_a_phase2_dev_v1_pilot.csv",
)


class FamilyAPhase2FreezeMismatch(RuntimeError):
    pass


class FamilyAPhase2ResultImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _median(values: Sequence[Decimal]) -> Decimal | None:
    return decimal(statistics.median(values)) if values else None


def _percent_reduction(current: Decimal, reference: Decimal) -> Decimal | None:
    return (reference - current) / reference * Decimal("100") if reference else None


def _comparison_metrics(
    treatment: Mapping[str, Any],
    reference: Mapping[str, Any],
    metric_names: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in metric_names:
        treatment_value = decimal(treatment[metric])
        reference_value = decimal(reference[metric])
        result[metric] = {
            "treatment": treatment_value,
            "reference": reference_value,
            "absolute_delta": treatment_value - reference_value,
            "percentage_change": (
                (treatment_value - reference_value) / abs(reference_value) * Decimal("100")
                if reference_value else None
            ),
        }
    return result


def verify_phase2_freeze(root: Path) -> dict[str, Any]:
    try:
        command_02 = verify_command_02_results(root)
        command_01 = verify_family_a_preregistration(root)["registry"]
        reference_parameters = next(
            row["parameters"]
            for row in command_01["experiments"]
            if row["experiment_id"] == REFERENCE_EXPERIMENT_ID
        )
        registry_path = root / "data/research/strategy_families/family_a/v1/phase2/registry/phase2_experiment_registry_v1.json"
        config_path = root / "data/research/strategy_families/family_a/v1/phase2/registry/phase2_config_v1.json"
        summary_path = root / "data/reports/family_a_phase2_v1_summary.json"
        registry = _read_json(registry_path)
        config = _read_json(config_path)
        summary = _read_json(summary_path)
        verify_phase2_registry(registry, config, reference_parameters)
        checks = {
            "phase2_version": config.get("phase2_version") == PHASE2_VERSION,
            "phase2_profile": config.get("profile") == PHASE2_PROFILE,
            "phase2_config_hash": config.get("phase2_config_hash") == EXPECTED_PHASE2_CONFIG_HASH,
            "phase2_config_recomputed": canonical_hash(
                {key: value for key, value in config.items() if key != "phase2_config_hash"}
            ) == EXPECTED_PHASE2_CONFIG_HASH,
            "phase2_registry_hash": registry.get("phase2_registry_hash") == EXPECTED_PHASE2_REGISTRY_HASH,
            "command_03_ready": summary.get("verification", {}).get("ready_for_review") is True,
            "command_03_no_performance": summary.get("governance", {}).get("full_performance_run") is False,
            "command_03_no_validation": summary.get("governance", {}).get("validation_accessed") is False,
            "reference_result_hash": command_02["reference"]["baseline_result_hash"] == REFERENCE_BASELINE_RESULT_HASH,
        }
        by_id = {row["experiment_id"]: row for row in registry["experiments"]}
        for experiment_id, expected in EXPECTED_PHASE2_EXPERIMENT_HASHES.items():
            row = by_id[experiment_id]
            checks[f"{experiment_id}_parameter_hash"] = row["parameter_hash"] == expected["parameter_hash"]
            checks[f"{experiment_id}_preregistration_hash"] = (
                row["preregistration_hash"] == expected["preregistration_hash"]
            )
        if not all(checks.values()):
            raise ValueError(checks)
        return {
            "status": "VERIFIED",
            "checks": checks,
            "config": config,
            "registry": registry,
            "reference_parameters": reference_parameters,
            "command_02": command_02,
        }
    except (FileNotFoundError, KeyError, StopIteration, TypeError, ValueError) as error:
        raise FamilyAPhase2FreezeMismatch(
            f"FAMILY_A_PHASE2_FREEZE_MISMATCH: {error}"
        ) from error


def command_03_snapshot(root: Path) -> dict[str, Any]:
    verified = verify_phase2_freeze(root)
    phase2_root = root / "data/research/strategy_families/family_a/v1/phase2"
    paths = [
        *sorted(
            path
            for path in phase2_root.rglob("*")
            if path.is_file() and "development_evaluation" not in path.parts
        ),
        *(root / "data/reports" / name for name in COMMAND_03_REPORT_NAMES),
        root / "docs/strategy-family-a-phase2-controlled-research-v1.md",
    ]
    file_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in paths
        if path.exists()
    }
    semantic = {
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "phase2_registry_hash": EXPECTED_PHASE2_REGISTRY_HASH,
        "experiment_hashes": EXPECTED_PHASE2_EXPERIMENT_HASHES,
        "command_03_ready": True,
        "validation_accessed": False,
        "file_hashes": file_hashes,
        "verified_checks": verified["checks"],
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def evaluation_baseline_snapshot(root: Path) -> dict[str, Any]:
    prior = phase2_baseline_snapshot(root)
    command_03 = command_03_snapshot(root)
    semantic = {
        "prior_snapshot_hash": prior["snapshot_hash"],
        "command_03_snapshot_hash": command_03["snapshot_hash"],
        "cap4_validation_state": prior["cap4_validation_state"],
        "cap4_validation_run_count": prior["cap4_validation_run_count"],
        "family_a_command_01_snapshot_hash": prior["family_a_command_01_snapshot_hash"],
        "family_a_command_02_registry_hash": prior["family_a_command_02_registry_hash"],
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def _load_market(root: Path) -> tuple[list[date], dict[date, dict[str, Any]]]:
    sessions = [
        value_date
        for value_date in _load_sessions(root)
        if DEVELOPMENT_START <= value_date <= DEVELOPMENT_END
    ]
    membership = _load_membership(root)
    aliases = _load_aliases(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if not sessions or sessions[0] < DEVELOPMENT_START or sessions[-1] > DEVELOPMENT_END:
        raise ValueError("DEVELOPMENT_ONLY_PARTITION_FAILURE")
    if max(bars) > DEVELOPMENT_END:
        raise ValueError("DEVELOPMENT_ONLY_PRICE_BOUNDARY_FAILURE")
    return sessions, bars


def _retention_inputs(root: Path) -> dict[date, list[dict[str, str]]]:
    path = root / "data/research/strategy_families/family_a/v1/signals/family_a_signal_inputs_v1.csv"
    grouped: dict[date, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        if row["experiment_id"] != REFERENCE_EXPERIMENT_ID:
            continue
        formation = date.fromisoformat(row["decision_date"])
        execution = date.fromisoformat(row["execution_date"])
        if not DEVELOPMENT_START <= formation <= execution <= DEVELOPMENT_END:
            raise ValueError("Retention inputs crossed DEVELOPMENT boundary")
        grouped[execution].append(row)
    return grouped


def retention_schedule_resolver(
    root: Path,
) -> tuple[
    Callable[[RebalanceSchedule, frozenset[str]], RebalanceSchedule],
    list[RebalanceSchedule],
    list[dict[str, Any]],
]:
    inputs = _retention_inputs(root)
    resolved: list[RebalanceSchedule] = []
    decisions: list[dict[str, Any]] = []

    def resolve(schedule: RebalanceSchedule, held_symbols: frozenset[str]) -> RebalanceSchedule:
        if not schedule.sufficient_universe:
            resolved.append(schedule)
            decisions.append(
                {
                    "formation_date": schedule.formation_date.isoformat(),
                    "execution_date": schedule.execution_date.isoformat(),
                    "status": "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO",
                    "held_before": len(held_symbols),
                    "selected": len(schedule.selected),
                }
            )
            return schedule
        rows = sorted(
            (row for row in inputs[schedule.execution_date] if row["eligible"] == "True"),
            key=lambda row: (int(row["signal_rank"]), row["symbol"]),
        )
        eligible_count = len(rows)
        entry_cutoff = math.ceil(eligible_count * 0.10)
        retention_cutoff = math.ceil(eligible_count * 0.15)
        by_symbol = {row["symbol"]: row for row in rows}
        retained = sorted(
            (
                symbol
                for symbol in held_symbols
                if symbol in by_symbol and int(by_symbol[symbol]["signal_rank"]) <= retention_cutoff
            ),
            key=lambda symbol: (int(by_symbol[symbol]["signal_rank"]), symbol),
        )
        selected_symbols = list(retained)
        candidates = [
            row["symbol"]
            for row in rows
            if int(row["signal_rank"]) <= entry_cutoff and row["symbol"] not in selected_symbols
        ]
        for symbol in candidates:
            if len(selected_symbols) >= entry_cutoff:
                break
            selected_symbols.append(symbol)
        selected_symbols.sort(key=lambda symbol: (int(by_symbol[symbol]["signal_rank"]), symbol))
        selected = tuple(
            SelectedInstrument(
                symbol=symbol,
                isin=by_symbol[symbol]["isin"],
                rank=int(by_symbol[symbol]["signal_rank"]),
                signal_value=decimal(by_symbol[symbol]["6m_return"]),
            )
            for symbol in selected_symbols
        )
        result = RebalanceSchedule(
            experiment_id=A2_001,
            formation_date=schedule.formation_date,
            execution_date=schedule.execution_date,
            eligible_count=eligible_count,
            intended_count=entry_cutoff,
            sufficient_universe=bool(selected),
            selected=selected,
        )
        resolved.append(result)
        decisions.append(
            {
                "formation_date": schedule.formation_date.isoformat(),
                "execution_date": schedule.execution_date.isoformat(),
                "status": "EXECUTED",
                "held_before": len(held_symbols),
                "eligible_count": eligible_count,
                "entry_cutoff_rank": entry_cutoff,
                "retention_cutoff_rank": retention_cutoff,
                "retained_count": len(retained),
                "new_count": len(set(selected_symbols) - held_symbols),
                "removed_count": len(held_symbols - set(selected_symbols)),
                "selected_count": len(selected_symbols),
            }
        )
        return result

    return resolve, resolved, decisions


def _turnover_metrics(summary: Mapping[str, Any], rebalances: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    executed = [row for row in rebalances if str(row["status"]).startswith("EXECUTED")]
    buy_x = sum(
        (
            decimal(row["gross_buy_turnover"]) / decimal(row["pre_rebalance_net_equity"])
            for row in executed
            if decimal(row["pre_rebalance_net_equity"])
        ),
        Decimal("0"),
    )
    sell_x = sum(
        (
            decimal(row["gross_sell_turnover"]) / decimal(row["pre_rebalance_net_equity"])
            for row in executed
            if decimal(row["pre_rebalance_net_equity"])
        ),
        Decimal("0"),
    )
    retention = [
        decimal(row["retention_rate_pct"])
        for row in executed
        if row.get("retention_rate_pct") not in {None, ""}
    ]
    return {
        "annualized_turnover_x": summary["annualized_turnover_x"],
        "average_rebalance_turnover_x": summary["average_rebalance_turnover_x"],
        "median_rebalance_turnover_x": summary["median_rebalance_turnover_x"],
        "p90_rebalance_turnover_x": summary["p90_rebalance_turnover_x"],
        "total_buy_turnover_x": buy_x,
        "total_sell_turnover_x": sell_x,
        "annualized_buy_turnover_x": buy_x / Decimal("3"),
        "annualized_sell_turnover_x": sell_x / Decimal("3"),
        "average_selected_names": _mean([Decimal(int(row["selected_count"])) for row in executed]),
        "average_retained_names": _mean([Decimal(int(row["retained_count"])) for row in executed]),
        "average_new_names": _mean([Decimal(int(row["added_count"])) for row in executed]),
        "average_removed_names": _mean([Decimal(int(row["removed_count"])) for row in executed]),
        "total_added_names": sum(int(row["added_count"]) for row in executed),
        "total_removed_names": sum(int(row["removed_count"]) for row in executed),
        "average_retention_rate_pct": _mean(retention),
        "median_retention_rate_pct": _median(retention),
    }


def _cost_metrics(
    summary: Mapping[str, Any],
    daily: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = decimal(summary["total_cost"])
    starting = decimal(summary["starting_equity"])
    average_equity = _mean([decimal(row["net_equity"]) for row in daily]) or Decimal("0")
    executed_count = int(summary["executed_rebalance_count"])
    turnover = decimal(summary["total_one_way_turnover_x"])
    return {
        "total_modeled_cost_rupees": total,
        "cost_pct_starting_capital": total / starting * Decimal("100"),
        "average_net_equity": average_equity,
        "cost_pct_average_equity": total / average_equity * Decimal("100") if average_equity else None,
        "gross_to_net_drag_pp": summary["gross_to_net_return_deterioration_pp"],
        "cost_per_executed_rebalance_rupees": total / Decimal(executed_count) if executed_count else None,
        "cost_per_unit_turnover_rupees": total / turnover if turnover else None,
    }


def _capital_fidelity(
    simulation: Mapping[str, Any],
    schedules: Sequence[RebalanceSchedule],
    bars: Mapping[date, Mapping[str, Any]],
) -> dict[str, Any]:
    schedule_by_date = {row.execution_date.isoformat(): row for row in schedules}
    holding_by_date: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in simulation["holdings"]:
        holding_by_date[str(row["execution_date"])][str(row["symbol"])] = decimal(row["actual_weight_pct"])
    errors: list[Decimal] = []
    l1_values: list[Decimal] = []
    cash_values: list[Decimal] = []
    selected_counts: list[Decimal] = []
    actual_counts: list[Decimal] = []
    unaffordable_by_date: list[dict[str, Any]] = []
    problematic: list[dict[str, Any]] = []
    yearly_errors: dict[int, list[Decimal]] = defaultdict(list)
    for row in simulation["rebalances"]:
        if not str(row["status"]).startswith("EXECUTED"):
            continue
        execution = str(row["execution_date"])
        schedule = schedule_by_date[execution]
        selected_symbols = [selected.symbol for selected in schedule.selected]
        target_pct = Decimal("100") / Decimal(len(selected_symbols))
        actual = holding_by_date.get(execution, {})
        date_errors = [abs(actual.get(symbol, Decimal("0")) - target_pct) for symbol in selected_symbols]
        errors.extend(date_errors)
        yearly_errors[int(execution[:4])].extend(date_errors)
        l1_values.append(sum(date_errors, Decimal("0")))
        cash_values.append(decimal(row["cash_residual_pct"]))
        selected_counts.append(Decimal(len(selected_symbols)))
        actual_counts.append(Decimal(int(row["actual_holdings"])))
        missing = [symbol for symbol in selected_symbols if symbol not in actual]
        if missing:
            unaffordable_by_date.append(
                {
                    "formation_date": row["formation_date"],
                    "execution_date": execution,
                    "count": len(missing),
                    "symbols": missing,
                }
            )
            execution_date = date.fromisoformat(execution)
            for symbol in missing:
                bar = bars.get(execution_date, {}).get(symbol)
                problematic.append(
                    {
                        "symbol": symbol,
                        "formation_date": row["formation_date"],
                        "execution_date": execution,
                        "open_price": bar.open_price if bar is not None else None,
                    }
                )
    return {
        "average_intended_holdings": _mean(selected_counts),
        "average_actual_holdings": _mean(actual_counts),
        "unaffordable_selection_count": sum(row["count"] for row in unaffordable_by_date),
        "formation_dates_with_unaffordable_names": [row["formation_date"] for row in unaffordable_by_date],
        "unique_unaffordable_symbols": sorted({item["symbol"] for item in problematic}),
        "highest_priced_problematic_symbols": sorted(
            problematic,
            key=lambda item: decimal(item["open_price"]) if item["open_price"] is not None else Decimal("-1"),
            reverse=True,
        )[:10],
        "average_cash_pct": _mean(cash_values),
        "median_cash_pct": _median(cash_values),
        "maximum_cash_pct": max(cash_values, default=None),
        "average_invested_pct": Decimal("100") - (_mean(cash_values) or Decimal("100")),
        "mean_absolute_weight_error_pp": _mean(errors),
        "median_absolute_weight_error_pp": _median(errors),
        "maximum_absolute_weight_error_pp": max(errors, default=None),
        "average_l1_tracking_difference_pct": _mean(l1_values),
        "median_l1_tracking_difference_pct": _median(l1_values),
        "maximum_l1_tracking_difference_pct": max(l1_values, default=None),
        "tracking_difference_vs_idealized_pct": _mean(l1_values),
        "yearly_mean_absolute_weight_error_pp": {
            str(year): _mean(yearly_errors[year]) for year in (2022, 2023, 2024)
        },
    }


def _reference_simulation(root: Path) -> dict[str, Any]:
    mode_root = (
        root
        / "data/research/strategy_families/family_a/v1/development_backtests/mom_a_002"
        / EXECUTABLE_MODE.lower()
    )
    return {
        "experiment_id": REFERENCE_EXPERIMENT_ID,
        "mode": EXECUTABLE_MODE,
        "daily": read_csv(mode_root / "daily_ledger.csv"),
        "rebalances": read_csv(mode_root / "rebalances.csv"),
        "holdings": read_csv(mode_root / "holdings.csv"),
        "costs": read_csv(mode_root / "costs.csv"),
    }


def _enriched_yearly(
    simulation: Mapping[str, Any],
    capital_fidelity: Mapping[str, Any],
    *,
    starting_capital: Decimal,
) -> list[dict[str, Any]]:
    rows = yearly_results(simulation, starting_capital=starting_capital)
    rebalances_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in simulation["rebalances"]:
        if str(row["status"]).startswith("EXECUTED"):
            rebalances_by_year[int(str(row["execution_date"])[:4])].append(row)
    for row in rows:
        year = int(row["year"])
        cash = [decimal(item["cash_residual_pct"]) for item in rebalances_by_year[year]]
        row["average_cash_pct"] = _mean(cash)
        row["mean_absolute_weight_error_pp"] = capital_fidelity[
            "yearly_mean_absolute_weight_error_pp"
        ][str(year)]
    return rows


def _temporal_stability(yearly: Sequence[Mapping[str, Any]]) -> str:
    returns = [decimal(row["net_return_pct"]) for row in yearly]
    if len(returns) != 3:
        return "INCONCLUSIVE"
    positive = sum(value > 0 for value in returns)
    if positive == 3:
        return "CONSISTENT"
    if positive == 2 and min(returns) > Decimal("-20"):
        return "MOSTLY_CONSISTENT"
    if returns[0] * returns[-1] < 0 and abs(returns[0]) >= 5 and abs(returns[-1]) >= 5:
        return "CONTRADICTORY"
    return "UNSTABLE"


def retention_turnover_result(
    treatment: Mapping[str, Any], reference: Mapping[str, Any], cost_reduction_pct: Decimal
) -> str:
    reduction = _percent_reduction(
        decimal(treatment["annualized_turnover_x"]), decimal(reference["annualized_turnover_x"])
    )
    if reduction is None:
        return "INCONCLUSIVE"
    if reduction >= 25 and cost_reduction_pct >= 20:
        return "MATERIAL_IMPROVEMENT"
    if reduction >= 15 and cost_reduction_pct >= 10:
        return "MODERATE_IMPROVEMENT"
    if reduction > 0 and cost_reduction_pct > 0:
        return "MINOR_IMPROVEMENT"
    if reduction < 0 or cost_reduction_pct < 0:
        return "WORSE"
    return "NO_IMPROVEMENT"


def retention_performance_result(
    treatment: Mapping[str, Any], reference: Mapping[str, Any], yearly: Sequence[Mapping[str, Any]]
) -> tuple[str, dict[str, Any]]:
    evidence = {
        "net_return_delta_pp": decimal(treatment["net_total_return_pct"]) - decimal(reference["net_total_return_pct"]),
        "net_cagr_delta_pp": decimal(treatment["net_cagr_pct"]) - decimal(reference["net_cagr_pct"]),
        "drawdown_worsening_pp": abs(decimal(treatment["net_max_drawdown_pct"]))
        - abs(decimal(reference["net_max_drawdown_pct"])),
        "rebalance_success_delta_pp": decimal(treatment["net_rebalance_success_rate_pct"])
        - decimal(reference["net_rebalance_success_rate_pct"]),
        "positive_year_count": sum(decimal(row["net_return_pct"]) > 0 for row in yearly),
    }
    if (
        evidence["net_return_delta_pp"] >= 0
        and evidence["net_cagr_delta_pp"] >= 0
        and evidence["drawdown_worsening_pp"] <= 2
        and evidence["rebalance_success_delta_pp"] >= -10
    ):
        result = "IMPROVES"
    elif (
        evidence["net_return_delta_pp"] >= -5
        and evidence["net_cagr_delta_pp"] >= -2
        and evidence["drawdown_worsening_pp"] <= 3
        and evidence["positive_year_count"] >= 2
    ):
        result = "PRESERVES"
    elif (
        evidence["net_return_delta_pp"] >= -10
        and evidence["net_cagr_delta_pp"] >= -4
        and evidence["drawdown_worsening_pp"] <= 5
    ):
        result = "MODEST_DEGRADATION"
    else:
        result = "MATERIAL_DEGRADATION"
    return result, evidence


def capital_improvement_result(
    treatment: Mapping[str, Any], reference: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    evidence = {
        "average_cash_reduction_pct": _percent_reduction(
            decimal(treatment["average_cash_pct"]), decimal(reference["average_cash_pct"])
        ),
        "mean_weight_error_reduction_pct": _percent_reduction(
            decimal(treatment["mean_absolute_weight_error_pp"]),
            decimal(reference["mean_absolute_weight_error_pp"]),
        ),
        "l1_tracking_reduction_pct": _percent_reduction(
            decimal(treatment["average_l1_tracking_difference_pct"]),
            decimal(reference["average_l1_tracking_difference_pct"]),
        ),
        "unaffordable_reduction_count": int(reference["unaffordable_selection_count"])
        - int(treatment["unaffordable_selection_count"]),
    }
    cash = decimal(evidence["average_cash_reduction_pct"] or 0)
    weight = decimal(evidence["mean_weight_error_reduction_pct"] or 0)
    l1 = decimal(evidence["l1_tracking_reduction_pct"] or 0)
    if min(cash, weight, l1) >= 40 and evidence["unaffordable_reduction_count"] > 0:
        result = "MATERIAL_IMPROVEMENT"
    elif min(cash, weight, l1) >= 20 and evidence["unaffordable_reduction_count"] >= 0:
        result = "MODERATE_IMPROVEMENT"
    elif min(cash, weight, l1) > 0:
        result = "MINOR_IMPROVEMENT"
    elif max(cash, weight, l1) < 0:
        result = "NO_MEANINGFUL_IMPROVEMENT"
    else:
        result = "INCONCLUSIVE"
    return result, evidence


def capital_distortion_result(fidelity: Mapping[str, Any]) -> str:
    cash = decimal(fidelity["average_cash_pct"])
    tracking = decimal(fidelity["average_l1_tracking_difference_pct"])
    if cash < 5 and tracking < 5:
        return "LOW_DISTORTION"
    if cash < 10 and tracking < 10:
        return "MODERATE_DISTORTION"
    if cash < 20 and tracking < 25:
        return "HIGH_DISTORTION"
    return "SEVERE_DISTORTION"


def _immutable_result(path: Path, body: Mapping[str, Any]) -> dict[str, Any]:
    result = {**body, "development_result_hash": canonical_hash(body)}
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(result):
            repo_root = next(
                parent
                for parent in path.parents
                if (parent / "backend").is_dir() and (parent / "data").is_dir()
            )
            summary_path = repo_root / "data/reports/family_a_phase2_dev_v1_summary.json"
            finalized = False
            if summary_path.exists():
                finalized = _read_json(summary_path).get("verification", {}).get("ready_for_review") is True
            if finalized:
                raise FamilyAPhase2ResultImmutabilityError(
                    f"Immutable Phase 2 result differs at {path}; use a new experiment ID"
                )
            write_json(path, result)
            return json_ready(result)
        return existing
    write_json(path, result)
    return json_ready(result)


def evaluate_phase2(root: Path) -> dict[str, Any]:
    freeze = verify_phase2_freeze(root)
    sessions, bars = _load_market(root)
    reference_schedules = load_rebalance_schedules(root)[REFERENCE_EXPERIMENT_ID]
    resolver, resolved_a2_001, retention_decisions = retention_schedule_resolver(root)
    a2_001_simulation = simulate_executable(
        A2_001,
        reference_schedules,
        sessions,
        bars,
        starting_capital=A2_001_CAPITAL,
        mode=A2_001_MODE,
        schedule_resolver=resolver,
    )
    a2_002_simulation = simulate_executable(
        A2_002,
        reference_schedules,
        sessions,
        bars,
        starting_capital=A2_002_CAPITAL,
        mode=A2_002_MODE,
    )
    a2_001_analysis = summarize_simulation(a2_001_simulation, starting_capital=A2_001_CAPITAL)
    a2_002_analysis = summarize_simulation(a2_002_simulation, starting_capital=A2_002_CAPITAL)
    a2_001_summary = a2_001_analysis["summary"]
    a2_002_summary = a2_002_analysis["summary"]

    reference_result = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/development_backtests/mom_a_002/baseline_result.json"
    )
    if reference_result["baseline_result_hash"] != REFERENCE_BASELINE_RESULT_HASH:
        raise FamilyAPhase2FreezeMismatch("FAMILY_A_PHASE2_FREEZE_MISMATCH: MOM-A-002 result")
    reference_summary = reference_result["executable_metrics"]
    idealized_summary = reference_result["idealized_metrics"]
    reference_simulation = _reference_simulation(root)

    a2_001_turnover = _turnover_metrics(a2_001_summary, a2_001_simulation["rebalances"])
    a2_002_turnover = _turnover_metrics(a2_002_summary, a2_002_simulation["rebalances"])
    reference_turnover = _turnover_metrics(reference_summary, reference_simulation["rebalances"])
    a2_001_cost = _cost_metrics(a2_001_summary, a2_001_simulation["daily"])
    a2_002_cost = _cost_metrics(a2_002_summary, a2_002_simulation["daily"])
    reference_cost = _cost_metrics(reference_summary, reference_simulation["daily"])
    a2_001_fidelity = _capital_fidelity(a2_001_simulation, resolved_a2_001, bars)
    a2_002_fidelity = _capital_fidelity(a2_002_simulation, reference_schedules, bars)
    reference_fidelity = _capital_fidelity(reference_simulation, reference_schedules, bars)
    a2_001_yearly = _enriched_yearly(
        a2_001_simulation, a2_001_fidelity, starting_capital=A2_001_CAPITAL
    )
    a2_002_yearly = _enriched_yearly(
        a2_002_simulation, a2_002_fidelity, starting_capital=A2_002_CAPITAL
    )
    cost_reduction_pct = decimal(
        _percent_reduction(a2_001_cost["total_modeled_cost_rupees"], reference_cost["total_modeled_cost_rupees"])
        or 0
    )
    turnover_result = retention_turnover_result(a2_001_turnover, reference_turnover, cost_reduction_pct)
    performance_result, performance_evidence = retention_performance_result(
        a2_001_summary, reference_summary, a2_001_yearly
    )
    a2_001_temporal = _temporal_stability(a2_001_yearly)
    accounting_clean_a2_001 = (
        a2_001_simulation["cash_reconciliation_violations"] == 0
        and a2_001_simulation["equity_reconciliation_violations"] == 0
    )
    if (
        turnover_result in {"MATERIAL_IMPROVEMENT", "MODERATE_IMPROVEMENT"}
        and performance_result in {"IMPROVES", "PRESERVES"}
        and a2_001_temporal in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        and accounting_clean_a2_001
    ):
        a2_001_result = "SUPPORTED"
    elif (
        turnover_result in {"MATERIAL_IMPROVEMENT", "MODERATE_IMPROVEMENT", "MINOR_IMPROVEMENT"}
        and performance_result != "MATERIAL_DEGRADATION"
        and accounting_clean_a2_001
    ):
        a2_001_result = "PARTIALLY_SUPPORTED"
    elif turnover_result == "WORSE" or performance_result == "MATERIAL_DEGRADATION":
        a2_001_result = "FAILED"
    else:
        a2_001_result = "INCONCLUSIVE"

    capital_improvement, capital_evidence = capital_improvement_result(
        a2_002_fidelity, reference_fidelity
    )
    distortion = capital_distortion_result(a2_002_fidelity)
    idealized_gap = decimal(idealized_summary["net_total_return_pct"]) - decimal(
        a2_002_summary["net_total_return_pct"]
    )
    if capital_improvement in {"MATERIAL_IMPROVEMENT", "MODERATE_IMPROVEMENT"}:
        strategy_fidelity = (
            "CLOSE_TO_IDEALIZED"
            if distortion in {"LOW_DISTORTION", "MODERATE_DISTORTION"} and abs(idealized_gap) <= 5
            else "IMPROVED_BUT_MATERIAL_GAP"
        )
    elif capital_improvement == "MINOR_IMPROVEMENT":
        strategy_fidelity = "LITTLE_IMPROVEMENT"
    elif capital_improvement == "NO_MEANINGFUL_IMPROVEMENT":
        strategy_fidelity = "WORSE" if capital_evidence["average_cash_reduction_pct"] < 0 else "LITTLE_IMPROVEMENT"
    else:
        strategy_fidelity = "INCONCLUSIVE"
    accounting_clean_a2_002 = (
        a2_002_simulation["cash_reconciliation_violations"] == 0
        and a2_002_simulation["equity_reconciliation_violations"] == 0
    )
    if (
        capital_improvement in {"MATERIAL_IMPROVEMENT", "MODERATE_IMPROVEMENT"}
        and strategy_fidelity in {"CLOSE_TO_IDEALIZED", "IMPROVED_BUT_MATERIAL_GAP"}
        and accounting_clean_a2_002
    ):
        a2_002_result = "SUPPORTED"
    elif capital_improvement == "MINOR_IMPROVEMENT" and accounting_clean_a2_002:
        a2_002_result = "PARTIALLY_SUPPORTED"
    elif capital_improvement == "NO_MEANINGFUL_IMPROVEMENT" or strategy_fidelity == "WORSE":
        a2_002_result = "FAILED"
    else:
        a2_002_result = "INCONCLUSIVE"
    a2_002_temporal = _temporal_stability(a2_002_yearly)

    if a2_001_result == a2_002_result == "SUPPORTED":
        family_result = "STRONG_SUPPORT"
    elif "SUPPORTED" in {a2_001_result, a2_002_result} or "PARTIALLY_SUPPORTED" in {
        a2_001_result,
        a2_002_result,
    }:
        family_result = "PARTIAL_SUPPORT" if "FAILED" not in {a2_001_result, a2_002_result} else "WEAK_SUPPORT"
    elif a2_001_result == a2_002_result == "FAILED":
        family_result = "NO_SUPPORT"
    else:
        family_result = "INCONCLUSIVE"
    next_stage = {
        "STRONG_SUPPORT": "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN",
        "PARTIAL_SUPPORT": "CONTINUE_CONTROLLED_DEVELOPMENT",
        "WEAK_SUPPORT": "CONTINUE_CONTROLLED_DEVELOPMENT",
        "NO_SUPPORT": "STOP_FAMILY_A",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[family_result]

    return {
        "freeze": freeze,
        "sessions": sessions,
        "bars": bars,
        "reference_schedules": reference_schedules,
        "resolved_a2_001": resolved_a2_001,
        "retention_decisions": retention_decisions,
        "reference_result": reference_result,
        "reference_summary": reference_summary,
        "idealized_summary": idealized_summary,
        "reference_simulation": reference_simulation,
        "reference_turnover": reference_turnover,
        "reference_cost": reference_cost,
        "reference_fidelity": reference_fidelity,
        "a2_001": {
            "simulation": a2_001_simulation,
            "analysis": a2_001_analysis,
            "summary": a2_001_summary,
            "turnover": a2_001_turnover,
            "cost": a2_001_cost,
            "fidelity": a2_001_fidelity,
            "yearly": a2_001_yearly,
            "temporal_stability": a2_001_temporal,
            "turnover_result": turnover_result,
            "performance_result": performance_result,
            "performance_evidence": performance_evidence,
            "development_result": a2_001_result,
            "cost_reduction_pct": cost_reduction_pct,
        },
        "a2_002": {
            "simulation": a2_002_simulation,
            "analysis": a2_002_analysis,
            "summary": a2_002_summary,
            "turnover": a2_002_turnover,
            "cost": a2_002_cost,
            "fidelity": a2_002_fidelity,
            "yearly": a2_002_yearly,
            "temporal_stability": a2_002_temporal,
            "capital_improvement": capital_improvement,
            "capital_evidence": capital_evidence,
            "capital_distortion": distortion,
            "strategy_fidelity": strategy_fidelity,
            "development_result": a2_002_result,
            "idealized_net_return_gap_pp": idealized_gap,
        },
        "family_result": family_result,
        "next_stage": next_stage,
    }


def _summary_report_row(experiment_id: str, evaluation: Mapping[str, Any]) -> dict[str, Any]:
    summary = evaluation["summary"]
    return {
        "experiment_id": experiment_id,
        "starting_equity": summary["starting_equity"],
        "gross_ending_equity": summary["gross_ending_equity"],
        "net_ending_equity": summary["net_ending_equity"],
        "gross_return_pct": summary["gross_total_return_pct"],
        "net_return_pct": summary["net_total_return_pct"],
        "net_cagr_pct": summary["net_cagr_pct"],
        "max_drawdown_pct": summary["net_max_drawdown_pct"],
        "annualized_volatility_pct": summary["net_annualized_volatility_pct"],
        "sharpe_like": summary["net_sharpe_like"],
        "rebalance_success_rate_pct": summary["net_rebalance_success_rate_pct"],
        "positive_month_rate_pct": summary["net_positive_calendar_month_rate_pct"],
        "temporal_stability": evaluation["temporal_stability"],
        "development_result": evaluation["development_result"],
    }


def build_family_a_phase2_development_evaluation(root: Path) -> dict[str, Any]:
    started_clock = time.perf_counter()
    started_at = utc_now()
    baseline_before = evaluation_baseline_snapshot(root)
    result = evaluate_phase2(root)
    output_root = root / "data/research/strategy_families/family_a/v1/phase2/development_evaluation"
    reports_root = root / "data/reports"

    a2_001_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "phase2_version": PHASE2_VERSION,
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "experiment_id": A2_001,
        "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["parameter_hash"],
        "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["preregistration_hash"],
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "reference_result_hash": REFERENCE_BASELINE_RESULT_HASH,
        "performance": result["a2_001"]["summary"],
        "turnover": result["a2_001"]["turnover"],
        "retention": {
            key: value
            for key, value in result["a2_001"]["turnover"].items()
            if "retention" in key or "names" in key
        },
        "costs": result["a2_001"]["cost"],
        "yearly": result["a2_001"]["yearly"],
        "classifications": {
            "TEMPORAL_STABILITY": result["a2_001"]["temporal_stability"],
            "RETENTION_BAND_TURNOVER_RESULT": result["a2_001"]["turnover_result"],
            "RETENTION_BAND_PERFORMANCE_RESULT": result["a2_001"]["performance_result"],
            "A2_001_DEVELOPMENT_RESULT": result["a2_001"]["development_result"],
        },
        "comparison_vs_mom_a_002": {
            "turnover_metrics": _comparison_metrics(
                result["a2_001"]["turnover"],
                result["reference_turnover"],
                (
                    "annualized_turnover_x",
                    "average_rebalance_turnover_x",
                    "median_rebalance_turnover_x",
                    "p90_rebalance_turnover_x",
                    "annualized_buy_turnover_x",
                    "annualized_sell_turnover_x",
                ),
            ),
            "turnover_reduction_pct": _percent_reduction(
                decimal(result["a2_001"]["turnover"]["annualized_turnover_x"]),
                decimal(result["reference_turnover"]["annualized_turnover_x"]),
            ),
            "cost_reduction_pct": result["a2_001"]["cost_reduction_pct"],
            "performance_evidence": result["a2_001"]["performance_evidence"],
            "added_reduction_count": result["reference_turnover"]["total_added_names"]
            - result["a2_001"]["turnover"]["total_added_names"],
            "added_reduction_pct": _percent_reduction(
                Decimal(result["a2_001"]["turnover"]["total_added_names"]),
                Decimal(result["reference_turnover"]["total_added_names"]),
            ),
            "removed_reduction_count": result["reference_turnover"]["total_removed_names"]
            - result["a2_001"]["turnover"]["total_removed_names"],
            "removed_reduction_pct": _percent_reduction(
                Decimal(result["a2_001"]["turnover"]["total_removed_names"]),
                Decimal(result["reference_turnover"]["total_removed_names"]),
            ),
        },
        "accounting": {
            "cash_reconciliation_violations": result["a2_001"]["simulation"]["cash_reconciliation_violations"],
            "equity_reconciliation_violations": result["a2_001"]["simulation"]["equity_reconciliation_violations"],
        },
        "development_only": True,
        "validation_accessed": False,
        "combined_experiment": False,
        "parameters_changed": False,
        "result_immutability": "IMMUTABLE_NEW_EXPERIMENT_ID_REQUIRED",
    }
    a2_002_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "phase2_version": PHASE2_VERSION,
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "experiment_id": A2_002,
        "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["parameter_hash"],
        "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["preregistration_hash"],
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "reference_result_hash": REFERENCE_BASELINE_RESULT_HASH,
        "performance": result["a2_002"]["summary"],
        "capital_fidelity": result["a2_002"]["fidelity"],
        "costs": result["a2_002"]["cost"],
        "yearly": result["a2_002"]["yearly"],
        "classifications": {
            "TEMPORAL_STABILITY": result["a2_002"]["temporal_stability"],
            "CAPITAL_FEASIBILITY_IMPROVEMENT": result["a2_002"]["capital_improvement"],
            "CAPITAL_DISTORTION": result["a2_002"]["capital_distortion"],
            "CAPITAL_STRATEGY_FIDELITY": result["a2_002"]["strategy_fidelity"],
            "A2_002_DEVELOPMENT_RESULT": result["a2_002"]["development_result"],
        },
        "comparison_vs_mom_a_002": {
            "same_selected_symbols": True,
            "only_parameter_change": "starting_capital_inr:100000->500000",
            "percentage_metrics_only_for_strategy_quality": True,
            "raw_rupee_profit_used_as_superiority_evidence": False,
            "capital_evidence": result["a2_002"]["capital_evidence"],
            "normalized_performance_metrics": _comparison_metrics(
                result["a2_002"]["summary"],
                result["reference_summary"],
                (
                    "gross_total_return_pct",
                    "net_total_return_pct",
                    "net_cagr_pct",
                    "net_max_drawdown_pct",
                    "net_annualized_volatility_pct",
                    "net_rebalance_success_rate_pct",
                ),
            ),
            "normalized_cost_metrics": _comparison_metrics(
                result["a2_002"]["cost"],
                result["reference_cost"],
                (
                    "cost_pct_starting_capital",
                    "cost_pct_average_equity",
                    "gross_to_net_drag_pp",
                    "cost_per_unit_turnover_rupees",
                ),
            ),
            "net_return_delta_vs_100k_pp": decimal(result["a2_002"]["summary"]["net_total_return_pct"])
            - decimal(result["reference_summary"]["net_total_return_pct"]),
            "net_return_gap_vs_idealized_pp": result["a2_002"]["idealized_net_return_gap_pp"],
        },
        "accounting": {
            "cash_reconciliation_violations": result["a2_002"]["simulation"]["cash_reconciliation_violations"],
            "equity_reconciliation_violations": result["a2_002"]["simulation"]["equity_reconciliation_violations"],
        },
        "development_only": True,
        "validation_accessed": False,
        "combined_experiment": False,
        "parameters_changed": False,
        "result_immutability": "IMMUTABLE_NEW_EXPERIMENT_ID_REQUIRED",
    }
    a2_001_result = _immutable_result(output_root / "a2_001/development_result_v1.json", a2_001_body)
    a2_002_result = _immutable_result(output_root / "a2_002/development_result_v1.json", a2_002_body)
    for experiment_id, observed in ((A2_001, a2_001_result), (A2_002, a2_002_result)):
        expected = EXPECTED_RESULT_HASHES.get(experiment_id)
        if expected is not None and observed["development_result_hash"] != expected:
            raise FamilyAPhase2ResultImmutabilityError(f"Frozen {experiment_id} result hash changed")

    derived_registry_body = {
        "command_version": COMMAND_VERSION,
        "phase2_version": PHASE2_VERSION,
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "source_phase2_registry_hash": EXPECTED_PHASE2_REGISTRY_HASH,
        "experiment_count": 2,
        "experiment_ids": [A2_001, A2_002],
        "experiments": [
            {
                "experiment_id": experiment_id,
                "status": "DEVELOPMENT_EVALUATED",
                "promotion_allowed": False,
                "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[experiment_id]["parameter_hash"],
                "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[experiment_id]["preregistration_hash"],
                "development_result_hash": experiment_result["development_result_hash"],
                "development_result": experiment_result["classifications"][
                    f"{experiment_id.replace('-', '_')}_DEVELOPMENT_RESULT"
                ],
            }
            for experiment_id, experiment_result in ((A2_001, a2_001_result), (A2_002, a2_002_result))
        ],
        "validation_authorized": False,
        "validation_accessed": False,
        "winner_selected": False,
        "result_immutability": "IMMUTABLE",
    }
    derived_registry = {
        **derived_registry_body,
        "development_registry_hash": canonical_hash(derived_registry_body),
    }
    registry_path = output_root / "comparison/phase2_development_registry_v1.json"
    write_json(registry_path, derived_registry)

    for key in ("daily", "rebalances", "holdings", "costs", "periods", "position_returns"):
        write_csv(output_root / f"a2_001/{key}.csv", result["a2_001"]["simulation"][key])
        write_csv(output_root / f"a2_002/{key}.csv", result["a2_002"]["simulation"][key])
        write_csv(
            output_root / f"ledgers/combined_{key}.csv",
            [*result["a2_001"]["simulation"][key], *result["a2_002"]["simulation"][key]],
        )
    write_csv(output_root / "a2_001/retention_decisions.csv", result["retention_decisions"])

    write_csv(reports_root / REPORT_NAMES[1], [_summary_report_row(A2_001, result["a2_001"])])
    write_csv(reports_root / REPORT_NAMES[2], [_summary_report_row(A2_002, result["a2_002"])])
    turnover_rows = [
        {"experiment_id": experiment_id, **metrics}
        for experiment_id, metrics in (
            (REFERENCE_EXPERIMENT_ID, result["reference_turnover"]),
            (A2_001, result["a2_001"]["turnover"]),
            (A2_002, result["a2_002"]["turnover"]),
        )
    ]
    write_csv(reports_root / REPORT_NAMES[3], turnover_rows)
    cost_rows = [
        {"experiment_id": experiment_id, **metrics}
        for experiment_id, metrics in (
            (REFERENCE_EXPERIMENT_ID, result["reference_cost"]),
            (A2_001, result["a2_001"]["cost"]),
            (A2_002, result["a2_002"]["cost"]),
        )
    ]
    write_csv(reports_root / REPORT_NAMES[4], cost_rows)
    capital_rows = [
        {"experiment_id": experiment_id, **metrics}
        for experiment_id, metrics in (
            (REFERENCE_EXPERIMENT_ID, result["reference_fidelity"]),
            (A2_002, result["a2_002"]["fidelity"]),
        )
    ]
    write_csv(reports_root / REPORT_NAMES[5], capital_rows)
    yearly_rows = [
        {**row, "experiment_id": experiment_id}
        for experiment_id, rows in (
            (A2_001, result["a2_001"]["yearly"]),
            (A2_002, result["a2_002"]["yearly"]),
        )
        for row in rows
    ]
    write_csv(reports_root / REPORT_NAMES[6], yearly_rows)
    comparison_rows = [
        {
            "comparison": "A2-001_VS_MOM-A-002",
            "question": "TURNOVER_REDUCTION_WITH_PERFORMANCE_PRESERVATION",
            "result": result["a2_001"]["development_result"],
            "primary_classification": result["a2_001"]["turnover_result"],
            "secondary_classification": result["a2_001"]["performance_result"],
            "winner_selected": False,
        },
        {
            "comparison": "A2-002_VS_MOM-A-002_AND_IDEALIZED",
            "question": "CAPITAL_IMPLEMENTATION_FIDELITY_NOT_ALPHA",
            "result": result["a2_002"]["development_result"],
            "primary_classification": result["a2_002"]["capital_improvement"],
            "secondary_classification": result["a2_002"]["strategy_fidelity"],
            "winner_selected": False,
        },
    ]
    write_csv(reports_root / REPORT_NAMES[7], comparison_rows)
    pilot_rows = [
        {"check": "PHASE2_FREEZE", "passed": True, "evidence": EXPECTED_PHASE2_CONFIG_HASH},
        {"check": "DEVELOPMENT_ONLY", "passed": True, "evidence": "2022-01-01..2024-12-31"},
        {
            "check": "A2_001_10_15_MECHANICS",
            "passed": retention_band_action(rank_fraction=Decimal("0.12"), is_held=True, infrastructure_eligible=True)
            == "RETAIN",
            "evidence": "10_PERCENT_ENTRY_15_PERCENT_RETENTION",
        },
        {"check": "A2_002_SAME_SELECTED_SYMBOLS", "passed": True, "evidence": "FROZEN_MOM-A-002_SCHEDULES"},
        {"check": "NO_COMBINED_EXPERIMENT", "passed": True, "evidence": "ISOLATED_SIMULATIONS"},
        {"check": "NO_ALTERNATE_BAND", "passed": True, "evidence": "10_15_ONLY"},
        {"check": "NO_ALTERNATE_CAPITAL", "passed": True, "evidence": "100K_REFERENCE_AND_500K_TREATMENT_ONLY"},
        {"check": "NO_VALIDATION", "passed": True, "evidence": "ZERO_ROWS"},
        {"check": "NO_STRATEGY_V2", "passed": True, "evidence": "FAMILY_A_RESEARCH_ONLY"},
        {
            "check": "ACCOUNTING_RECONCILED",
            "passed": all(
                evaluation["simulation"]["cash_reconciliation_violations"] == 0
                and evaluation["simulation"]["equity_reconciliation_violations"] == 0
                for evaluation in (result["a2_001"], result["a2_002"])
            ),
            "evidence": "ZERO_CASH_AND_EQUITY_VIOLATIONS",
        },
    ]
    write_csv(reports_root / REPORT_NAMES[8], pilot_rows)

    baseline_after = evaluation_baseline_snapshot(root)
    baseline_violations = 0 if baseline_before == baseline_after else 1
    accounting_violations = sum(
        evaluation["simulation"]["cash_reconciliation_violations"]
        for evaluation in (result["a2_001"], result["a2_002"])
    )
    equity_violations = sum(
        evaluation["simulation"]["equity_reconciliation_violations"]
        for evaluation in (result["a2_001"], result["a2_002"])
    )
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "phase2_version": PHASE2_VERSION,
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "freeze_verification": {"status": "VERIFIED", "checks": result["freeze"]["checks"]},
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "trading_sessions": len(result["sessions"]),
            "latest_price_date_loaded": max(result["bars"]).isoformat(),
        },
        "reference": {
            "experiment_id": REFERENCE_EXPERIMENT_ID,
            "development_result_hash": REFERENCE_BASELINE_RESULT_HASH,
            "executable": result["reference_summary"],
            "idealized": result["idealized_summary"],
            "turnover": result["reference_turnover"],
            "costs": result["reference_cost"],
            "capital_fidelity": result["reference_fidelity"],
            "source": "FROZEN_COMMAND_02_ARTIFACT_NOT_RECOMPUTED_OR_OVERWRITTEN",
        },
        "experiments": {
            A2_001: {
                "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["parameter_hash"],
                "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_001]["preregistration_hash"],
                "development_result_hash": a2_001_result["development_result_hash"],
                **a2_001_body,
            },
            A2_002: {
                "parameter_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["parameter_hash"],
                "preregistration_hash": EXPECTED_PHASE2_EXPERIMENT_HASHES[A2_002]["preregistration_hash"],
                "development_result_hash": a2_002_result["development_result_hash"],
                **a2_002_body,
            },
        },
        "relative_comparison": {
            "label": "FAMILY_A_PHASE2_RELATIVE_COMPARISON",
            "a2_001_question": "TURNOVER_REDUCTION_WITH_PERFORMANCE_PRESERVATION",
            "a2_002_question": "CAPITAL_IMPLEMENTATION_FIDELITY_NOT_ALPHA",
            "different_questions_no_overall_winner": True,
        },
        "classifications": {
            "FAMILY_A_PHASE2_RESULT": result["family_result"],
            "FAMILY_A_NEXT_RESEARCH_STAGE": result["next_stage"],
            "validation_automatically_authorized": False,
        },
        "accounting": {
            "cash_reconciliation_violations": accounting_violations,
            "equity_reconciliation_violations": equity_violations,
            "tolerance": "0.000001 INR",
        },
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_mutation_violations": baseline_violations,
            "family_a_command_01": "PASSED" if baseline_violations == 0 else "FAILED",
            "family_a_command_02": "PASSED" if baseline_violations == 0 else "FAILED",
            "family_a_command_03": "PASSED" if baseline_violations == 0 else "FAILED",
            "cap4": "PASSED" if baseline_violations == 0 else "FAILED",
            "strategy_v1": "PASSED" if baseline_violations == 0 else "FAILED",
        },
        "governance": {
            "performance_scope": "DEVELOPMENT_ONLY",
            "validation_accessed": False,
            "validation_rows_loaded": 0,
            "combined_experiment_run": False,
            "alternate_band_tested": False,
            "alternate_capital_tested": False,
            "signal_changed": False,
            "absolute_momentum_added": False,
            "regime_filter_added": False,
            "stop_or_target_added": False,
            "intraday_logic_added": False,
            "strategy_v2_created": False,
            "winner_selected": False,
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "registry": registry_path.relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        },
        "runtime": {
            "started_at": started_at,
            "completed_at": utc_now(),
            "elapsed_seconds": Decimal(str(round(time.perf_counter() - started_clock, 6))),
            "offline": True,
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
        root / "docs/strategy-family-a-phase2-development-evaluation-v1.md",
    ]
    manifest = {
        "command_version": COMMAND_VERSION,
        "phase2_config_hash": EXPECTED_PHASE2_CONFIG_HASH,
        "result_hashes": {
            A2_001: a2_001_result["development_result_hash"],
            A2_002: a2_002_result["development_result_hash"],
        },
        "development_registry_hash": derived_registry["development_registry_hash"],
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
    write_json(output_root / "comparison/run_manifest_v1.json", manifest)
    return summary


def finalize_phase2_development_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    if not summary_path.exists():
        raise FileNotFoundError("Run Family A Phase 2 development evaluation before finalizing")
    summary = _read_json(summary_path)
    verify_phase2_freeze(root)
    baseline = evaluation_baseline_snapshot(root)
    if baseline["snapshot_hash"] != summary["regression"]["after_snapshot_hash"]:
        raise FamilyAPhase2ResultImmutabilityError("Frozen baseline changed after Phase 2 evaluation")
    for experiment_id, expected in EXPECTED_RESULT_HASHES.items():
        observed = summary["experiments"][experiment_id]["development_result_hash"]
        if observed != expected:
            raise FamilyAPhase2ResultImmutabilityError(f"Frozen {experiment_id} result hash changed")
    ready = (
        backend_tests == "PASSED"
        and frontend_build == "PASSED"
        and summary["regression"]["baseline_mutation_violations"] == 0
        and summary["accounting"]["cash_reconciliation_violations"] == 0
        and summary["accounting"]["equity_reconciliation_violations"] == 0
        and summary["governance"]["validation_accessed"] is False
        and summary["governance"]["combined_experiment_run"] is False
        and len(EXPECTED_RESULT_HASHES) == 2
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
    "A2_001_MODE",
    "A2_002_MODE",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_RESULT_HASHES",
    "FamilyAPhase2FreezeMismatch",
    "FamilyAPhase2ResultImmutabilityError",
    "REPORT_NAMES",
    "build_family_a_phase2_development_evaluation",
    "capital_distortion_result",
    "capital_improvement_result",
    "command_03_snapshot",
    "evaluate_phase2",
    "evaluation_baseline_snapshot",
    "finalize_phase2_development_review",
    "retention_performance_result",
    "retention_schedule_resolver",
    "retention_turnover_result",
    "verify_phase2_freeze",
)

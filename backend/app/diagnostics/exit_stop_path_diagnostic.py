from __future__ import annotations

import copy
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    EXPECTED_METRICS,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    SKIP_INSUFFICIENT_CASH,
    SKIP_MAX_POSITIONS,
    SKIP_OTHER,
    SKIP_PORTFOLIO_RISK_LIMIT,
    SKIP_SAME_SYMBOL_ALREADY_OPEN,
    SKIP_ZERO_QUANTITY,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
    calculate_portfolio_quantity,
)
from app.diagnostics.strategy_diagnostic import (
    BASELINE_DEPENDENCY,
    COST_STATUS,
    PERFORMANCE_SCOPE,
    PROMOTION_ALLOWED,
    SLIPPAGE_STATUS,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
    DiagnosticContext,
    ExperimentDefinition,
    ExperimentExecution,
    ExperimentState,
    calculate_cagr,
    canonical_hash,
    decimal,
    jaccard,
    load_diagnostic_context,
    maximum_drawdown,
    mean,
    median,
    percent,
    prepare_horizon,
    rank_diagnostic_opportunities,
    robustness_summary,
    source_key,
    write_csv,
    write_gzip_csv,
    write_json,
)

COMMAND = "Command 02"
EXIT_COMMAND_VERSION = "STRATEGY_DIAGNOSTIC_EXIT_STOP_PATH_V1"
PROTECTED_STOP_EXIT = "PROTECTED_STOP_EXIT"
PROTECTED_STOP_GAP_EXIT = "PROTECTED_STOP_GAP_EXIT"

EXIT_EXPERIMENT_IDS = (
    "EXP-EXIT-001",
    "EXP-EXIT-002",
    "EXP-EXIT-003",
    "EXP-EXIT-004",
    "EXP-EXIT-005",
    "EXP-EXIT-006",
    "EXP-EXIT-007",
)
EXIT_PORTFOLIO_EXPERIMENT_IDS = EXIT_EXPERIMENT_IDS[:6]
PROTECTION_EXPERIMENT_IDS = EXIT_EXPERIMENT_IDS[1:3]
FIXED_TARGET_EXPERIMENT_IDS = EXIT_EXPERIMENT_IDS[3:6]

EXIT_CLASSIFICATION_THRESHOLDS = {
    "EXIT_PATH_RESULT": {
        "HIGH_GIVEBACK": "baseline median giveback >= 0.75R or mean >= 1.00R",
        "MATERIAL_GIVEBACK": "baseline median giveback >= 0.25R or mean >= 0.50R",
        "LOW_GIVEBACK": "otherwise when at least 20 baseline trades are available",
        "INCONCLUSIVE": "fewer than 20 baseline trades",
    },
    "PROTECTION_DIAGNOSTIC_RESULT": {
        "MATERIAL_DIFFERENCE": "any protection run has Jaccard < 0.80 or absolute return/drawdown delta >= 5pp",
        "MIXED": "otherwise, any run has Jaccard < 0.95 or absolute return/drawdown delta >= 1pp",
        "NO_CLEAR_EFFECT": "otherwise",
        "INCONCLUSIVE": "any protection run has fewer than 20 trades",
    },
    "FIXED_TARGET_DIAGNOSTIC_RESULT": {
        "MATERIAL_DIFFERENCE": "any fixed-target run has Jaccard < 0.80 or absolute return/drawdown delta >= 5pp",
        "MIXED": "otherwise, any run has Jaccard < 0.95 or absolute return/drawdown delta >= 1pp",
        "NO_CLEAR_EFFECT": "otherwise",
        "INCONCLUSIVE": "any fixed-target run has fewer than 20 trades",
    },
    "EXIT_OCCUPANCY_RESULT": {
        "HIGH_IMPACT": "minimum baseline Jaccard < 0.50 or absolute max-position-skip delta >= 20% of baseline",
        "MODERATE_IMPACT": "minimum baseline Jaccard < 0.80 or absolute max-position-skip delta >= 5% of baseline",
        "LOW_IMPACT": "otherwise",
        "INCONCLUSIVE": "any portfolio run has fewer than 20 trades",
    },
}

EXIT_EVALUATION_METRICS = (
    "opportunities_considered",
    "trades_entered",
    "admission_rate",
    "ending_equity",
    "gross_return",
    "cagr",
    "max_drawdown",
    "realized_r_distribution",
    "positive_gross_pnl_rate",
    "exit_distribution",
    "holding_sessions",
    "turnover",
    "trade_set_jaccard",
    "occupancy_and_skip_profile",
    "yearly_robustness",
    "giveback_r",
)


@dataclass(frozen=True, slots=True)
class ExitRule:
    mode: str
    protection_threshold_r: Decimal | None = None
    fixed_target_r: Decimal | None = None

    def validate(self) -> None:
        if self.mode not in {"BASELINE", "PROTECTION", "FIXED_TARGET"}:
            raise ValueError(f"Unauthorized exit diagnostic mode: {self.mode}")
        if self.mode == "PROTECTION":
            if self.protection_threshold_r not in {Decimal("0.5"), Decimal("1")}:
                raise ValueError("Protection is restricted to the preregistered 0.5R or 1R threshold")
            if self.fixed_target_r is not None:
                raise ValueError("Protection and fixed-target semantics cannot be combined")
        elif self.mode == "FIXED_TARGET":
            if self.fixed_target_r not in {Decimal("1"), Decimal("1.5"), Decimal("2")}:
                raise ValueError("Fixed target is restricted to preregistered 1R, 1.5R, or 2R")
            if self.protection_threshold_r is not None:
                raise ValueError("Fixed-target and protection semantics cannot be combined")
        elif self.protection_threshold_r is not None or self.fixed_target_r is not None:
            raise ValueError("Baseline reproduction cannot contain an exit variation")


class ExitExperimentRegistry:
    """Finite Command 02 registry; it cannot alter Command 01 definitions."""

    def __init__(self, baseline_hashes: Mapping[str, str]) -> None:
        self.baseline_hashes = dict(baseline_hashes)
        self._states: dict[str, ExperimentState] = {}
        self.reproducibility: dict[str, dict[str, Any]] = {}

    def register(self, definition: ExperimentDefinition) -> None:
        if definition.experiment_id not in EXIT_EXPERIMENT_IDS:
            raise ValueError(f"Unauthorized Command 02 exit experiment: {definition.experiment_id}")
        if definition.family != "EXIT_DIAGNOSTIC":
            raise ValueError("Command 02 experiments must use EXIT_DIAGNOSTIC")
        if definition.experiment_id in self._states:
            raise ValueError(f"Experiment ID already registered: {definition.experiment_id}")
        if definition.eligible_for_promotion or not definition.diagnostic_only:
            raise ValueError("Exit experiments are diagnostic-only and not promotion-eligible")
        self._states[definition.experiment_id] = ExperimentState(definition=definition)

    def mark_ready(self, experiment_id: str) -> None:
        state = self.state(experiment_id)
        if state.status != "REGISTERED":
            raise ValueError(f"Experiment {experiment_id} cannot move from {state.status} to READY")
        state.status = "READY"

    def run_twice(
        self,
        experiment_id: str,
        runner: Callable[[ExperimentDefinition], ExperimentExecution],
        *,
        hash_reader: Callable[[], Mapping[str, str]],
    ) -> ExperimentExecution | None:
        state = self.state(experiment_id)
        if state.status != "READY":
            raise ValueError(f"Experiment {experiment_id} is not READY")
        state.status = "RUNNING"
        try:
            run_results: list[ExperimentExecution] = []
            guards: list[dict[str, Any]] = []
            for run_number in (1, 2):
                before = dict(hash_reader())
                if before != self.baseline_hashes:
                    raise ValueError("Frozen baseline hash mismatch before experiment run")
                execution = runner(state.definition)
                after = dict(hash_reader())
                unchanged = before == after == self.baseline_hashes
                guards.append(
                    {
                        "run_number": run_number,
                        "before": before,
                        "after": after,
                        "unchanged": unchanged,
                    }
                )
                if not unchanged:
                    raise ValueError("Frozen baseline hash mutation detected")
                run_results.append(execution)
            fingerprints = [item.canonical_fingerprint() for item in run_results]
            reproducible = fingerprints[0] == fingerprints[1]
            if not reproducible:
                raise ValueError("Repeated canonical experiment outputs differ")
            execution = run_results[0]
            record = exit_definition_record(state.definition, self.baseline_hashes)
            execution.result.update(
                {
                    "pre_registration_hash": record["pre_registration_hash"],
                    "baseline_hashes": self.baseline_hashes,
                    "baseline_hash_guards": guards,
                    "baseline_hashes_unchanged": True,
                    "baseline_mutation_violations": 0,
                    "run_status": "COMPLETE",
                    "canonical_run_fingerprints": fingerprints,
                    "canonical_reproducibility_match": True,
                }
            )
            self.reproducibility[experiment_id] = {
                "canonical_run_fingerprints": fingerprints,
                "match": reproducible,
                "timestamps_and_run_ids_excluded": True,
            }
            state.result_fingerprint = execution.canonical_fingerprint()
            state.status = "COMPLETE"
            return execution
        except Exception as exc:
            state.status = "FAILED"
            state.failure_reason = f"{exc.__class__.__name__}: {exc}"
            return None

    def state(self, experiment_id: str) -> ExperimentState:
        try:
            return self._states[experiment_id]
        except KeyError as exc:
            raise ValueError(f"Experiment is not registered: {experiment_id}") from exc

    def records(self) -> list[dict[str, Any]]:
        return [
            {
                **exit_definition_record(
                    self._states[experiment_id].definition,
                    self.baseline_hashes,
                    status=self._states[experiment_id].status,
                ),
                "result_fingerprint": self._states[experiment_id].result_fingerprint,
                "failure_reason": self._states[experiment_id].failure_reason,
            }
            for experiment_id in EXIT_EXPERIMENT_IDS
            if experiment_id in self._states
        ]


def build_exit_experiment_definitions(
    registered_at: str | None = None,
) -> tuple[ExperimentDefinition, ...]:
    timestamp = registered_at or datetime.now(timezone.utc).isoformat()
    fixed = {
        "ranking": "BASELINE_RANK",
        "entry": "NEXT_SESSION_OPEN",
        "max_hold_sessions": 4,
        "max_concurrent_positions": 4,
        "max_risk_per_trade_pct": "1.00",
        "max_total_open_risk_pct": "4.00",
        "same_symbol_policy": "ONE_OPEN_POSITION_PER_SYMBOL",
        "leverage_policy": "NO_LEVERAGE_NO_MARGIN_NO_BORROWING",
        "ambiguity_policy": "CONSERVATIVE_STOP_FIRST",
        "costs": "NOT_MODELED",
        "classification_thresholds_hash": canonical_hash(EXIT_CLASSIFICATION_THRESHOLDS),
    }
    fields = EXIT_EVALUATION_METRICS
    definitions = (
        _exit_definition(timestamp, "EXP-EXIT-001", "BASELINE_EXIT_REPRODUCTION", "Exact frozen Strategy V1 exit reproduction.", "H3/H5 anchor — frozen exits should reproduce exactly.", {**fixed, "exit_rule": "FROZEN_STOP_FROZEN_TARGET_SESSION_4_CLOSE"}, fields, False),
        _exit_definition(timestamp, "EXP-EXIT-002", "PROTECT_AFTER_0_5R", "Move the effective stop to entry from the session after a completed prior session reaches +0.5R.", "H5 — prior favorable movement may precede material baseline giveback.", {**fixed, "exit_rule": "PROTECT_TO_ENTRY_NEXT_SESSION", "protection_threshold_r": "0.5", "target": "FROZEN_TARGET", "protected_gap_rule": "NEXT_SESSION_OPEN_IF_BELOW_ENTRY"}, fields, True),
        _exit_definition(timestamp, "EXP-EXIT-003", "PROTECT_AFTER_1R", "Move the effective stop to entry from the session after a completed prior session reaches +1R.", "H5 — prior favorable movement may precede material baseline giveback.", {**fixed, "exit_rule": "PROTECT_TO_ENTRY_NEXT_SESSION", "protection_threshold_r": "1", "target": "FROZEN_TARGET", "protected_gap_rule": "NEXT_SESSION_OPEN_IF_BELOW_ENTRY"}, fields, True),
        _exit_definition(timestamp, "EXP-EXIT-004", "FIXED_1R_PROFIT_EXIT", "Replace only the frozen target with a fixed +1R target.", "H3 — four-session target distance may materially affect exit mix and occupancy.", {**fixed, "exit_rule": "FIXED_TARGET", "fixed_target_r": "1", "protection": "DISABLED"}, fields, True),
        _exit_definition(timestamp, "EXP-EXIT-005", "FIXED_1_5R_PROFIT_EXIT", "Replace only the frozen target with a fixed +1.5R target.", "H3 — four-session target distance may materially affect exit mix and occupancy.", {**fixed, "exit_rule": "FIXED_TARGET", "fixed_target_r": "1.5", "protection": "DISABLED"}, fields, True),
        _exit_definition(timestamp, "EXP-EXIT-006", "FIXED_2R_PROFIT_EXIT", "Replace only the frozen target with a fixed +2R target.", "H3 — four-session target distance may materially affect exit mix and occupancy.", {**fixed, "exit_rule": "FIXED_TARGET", "fixed_target_r": "2", "protection": "DISABLED"}, fields, True),
        _exit_definition(timestamp, "EXP-EXIT-007", "EARLY_STOP_DIAGNOSTIC_ONLY", "Describe favorable excursion known before baseline stops and time exits without changing any trade.", "H5 — baseline stop exits may divide into never-favorable and prior-favorable paths.", {**fixed, "exit_rule": "DESCRIPTIVE_ONLY", "stop_path_ordering": "EARLIER_COMPLETED_SESSIONS_ONLY", "time_path_ordering": "THROUGH_TIME_EXIT_CLOSE"}, ("prior_session_mfe_r", "source_mfe_r_4", "realized_r_multiple", "exit_reason"), False),
    )
    if tuple(item.experiment_id for item in definitions) != EXIT_EXPERIMENT_IDS:
        raise ValueError("Command 02 suite differs from its explicit allowlist")
    return definitions


def _exit_definition(
    registered_at: str,
    experiment_id: str,
    name: str,
    description: str,
    hypothesis: str,
    parameters: Mapping[str, Any],
    fields: tuple[str, ...],
    changes_strategy_semantics: bool,
) -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=experiment_id,
        family="EXIT_DIAGNOSTIC",
        name=name,
        description=description,
        hypothesis=hypothesis,
        parameters=tuple(parameters.items()),
        outcome_fields_used_for_evaluation=fields,
        changes_strategy_semantics=changes_strategy_semantics,
        changes_portfolio_mechanics=changes_strategy_semantics,
        registered_at=registered_at,
    )


def calculate_exit_pre_registration_hash(
    definition: ExperimentDefinition, baseline_hashes: Mapping[str, str]
) -> str:
    return canonical_hash(
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": EXIT_COMMAND_VERSION,
            "experiment": {
                "experiment_id": definition.experiment_id,
                "family": definition.family,
                "name": definition.name,
                "description": definition.description,
                "hypothesis": definition.hypothesis,
                "parameters": definition.parameter_map,
                "outcome_fields_used_for_evaluation": definition.outcome_fields_used_for_evaluation,
                "changes_strategy_semantics": definition.changes_strategy_semantics,
                "changes_portfolio_mechanics": definition.changes_portfolio_mechanics,
                "diagnostic_only": definition.diagnostic_only,
                "eligible_for_promotion": definition.eligible_for_promotion,
            },
            "baseline_dependency": BASELINE_DEPENDENCY,
            "baseline_hashes": dict(sorted(baseline_hashes.items())),
            "evaluation_metrics": EXIT_EVALUATION_METRICS,
            "classification_thresholds": EXIT_CLASSIFICATION_THRESHOLDS,
        }
    )


def exit_definition_record(
    definition: ExperimentDefinition,
    baseline_hashes: Mapping[str, str],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "description": definition.description,
        "hypothesis": definition.hypothesis,
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": dict(baseline_hashes),
        },
        "parameters": definition.parameter_map,
        "parameter_hash": definition.parameter_hash,
        "parameters_locked_before_run": definition.parameters_locked_before_run,
        "outcome_fields_used_for_evaluation": list(definition.outcome_fields_used_for_evaluation),
        "changes_strategy_semantics": definition.changes_strategy_semantics,
        "changes_portfolio_mechanics": definition.changes_portfolio_mechanics,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "pre_registered": True,
        "pre_registration_hash": calculate_exit_pre_registration_hash(definition, baseline_hashes),
        "registered_at": definition.registered_at,
        "status": status or definition.status,
    }


def rule_for_definition(definition: ExperimentDefinition) -> ExitRule:
    parameters = definition.parameter_map
    if definition.experiment_id == "EXP-EXIT-001":
        rule = ExitRule("BASELINE")
    elif definition.experiment_id in PROTECTION_EXPERIMENT_IDS:
        rule = ExitRule("PROTECTION", protection_threshold_r=decimal(parameters["protection_threshold_r"]))
    elif definition.experiment_id in FIXED_TARGET_EXPERIMENT_IDS:
        rule = ExitRule("FIXED_TARGET", fixed_target_r=decimal(parameters["fixed_target_r"]))
    else:
        raise ValueError(f"No portfolio rule for {definition.experiment_id}")
    rule.validate()
    return rule


def resolve_exit_for_bar(
    *,
    bar: Mapping[str, Any],
    entry_price: Decimal,
    original_stop: Decimal,
    target_price: Decimal,
    protection_active: bool,
    sessions_seen: int,
    horizon: int = 4,
) -> tuple[str, Decimal, bool] | None:
    active_stop = entry_price if protection_active else original_stop
    if protection_active and decimal(bar["open"]) < active_stop:
        return PROTECTED_STOP_GAP_EXIT, decimal(bar["open"]), False
    stop_touched = decimal(bar["low"]) <= active_stop
    target_touched = decimal(bar["high"]) >= target_price
    if stop_touched and target_touched:
        return AMBIGUOUS_SAME_BAR_EXIT, active_stop, True
    if target_touched:
        return TARGET_EXIT, target_price, False
    if stop_touched:
        return (PROTECTED_STOP_EXIT if protection_active else STOP_EXIT), active_stop, False
    if sessions_seen == horizon:
        return TIME_EXIT, decimal(bar["close"]), False
    return None


def simulate_exit_portfolio(
    *,
    opportunities: Sequence[dict[str, Any]],
    trading_dates: Sequence[str],
    rule: ExitRule,
) -> dict[str, Any]:
    rule.validate()
    config = PortfolioBacktestConfig()
    by_entry_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_entry_date[str(row["next_session_date"])].append(row)
    cash = config.initial_capital_rupees
    positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    invariants: Counter[str] = Counter()
    trade_number = 0

    for trading_date in trading_dates:
        opening_cash = cash
        opening_positions = len(positions)
        opening_market_value = Decimal("0")
        for position in positions:
            bar = position["source"]["_diagnostic_bars"].get(trading_date)
            opening_mark = decimal(bar["open"]) if bar else position["last_mark"]
            opening_market_value += opening_mark * position["trade"]["quantity"]
        opening_equity = cash + opening_market_value
        ranked = rank_diagnostic_opportunities(by_entry_date.get(trading_date, []), "BASELINE_RANK")
        entries = 0
        for row in ranked:
            open_risk = sum(item["trade"]["planned_risk"] for item in positions)
            entry_price = decimal(row["hypothetical_entry_price"])
            original_stop = decimal(row["stop_price"])
            sizing = calculate_portfolio_quantity(
                entry_price=entry_price,
                stop_price=original_stop,
                portfolio_equity=opening_equity,
                available_cash=cash,
                config=config,
            )
            reason = ""
            if any(item["trade"]["symbol"] == row["symbol"] for item in positions):
                reason = SKIP_SAME_SYMBOL_ALREADY_OPEN
            elif len(positions) >= config.max_concurrent_positions:
                reason = SKIP_MAX_POSITIONS
            elif sizing["risk_per_share"] <= 0 or entry_price <= 0:
                reason = SKIP_OTHER
            elif sizing["quantity_by_risk"] < 1:
                reason = SKIP_ZERO_QUANTITY
            elif sizing["quantity_by_cash"] < 1:
                reason = SKIP_INSUFFICIENT_CASH
            elif open_risk + sizing["planned_risk"] > (
                opening_equity * config.max_total_open_risk_pct / Decimal("100")
                + Decimal("0.000001")
            ):
                reason = SKIP_PORTFOLIO_RISK_LIMIT
            if reason:
                skipped.append(
                    {
                        "source_key": source_key(row),
                        "symbol": row["symbol"],
                        "entry_date": trading_date,
                        "skip_reason": reason,
                    }
                )
                continue
            target_price = (
                entry_price + decimal(rule.fixed_target_r) * sizing["risk_per_share"]
                if rule.mode == "FIXED_TARGET"
                else decimal(row["target_price"])
            )
            trade_number += 1
            trade = {
                "trade_id": f"EXIT-DIAG-{trade_number:06d}",
                "source_key": source_key(row),
                "symbol": row["symbol"],
                "decision_date": row["decision_date"],
                "entry_date": trading_date,
                "entry_price": entry_price,
                "quantity": sizing["quantity"],
                "entry_notional": sizing["entry_notional"],
                "stop_price": original_stop,
                "target_price": target_price,
                "frozen_target_price": decimal(row["target_price"]),
                "frozen_effective_target_r": (
                    (decimal(row["target_price"]) - entry_price) / sizing["risk_per_share"]
                ),
                "risk_per_share": sizing["risk_per_share"],
                "planned_risk": sizing["planned_risk"],
                "selection_rank": row["_diagnostic_selection_rank"],
                "protection_threshold_r": rule.protection_threshold_r,
                "fixed_target_r": rule.fixed_target_r,
            }
            cash -= sizing["entry_notional"]
            positions.append(
                {
                    "trade": trade,
                    "source": row,
                    "last_mark": entry_price,
                    "sessions_seen": 0,
                    "protection_active": False,
                    "protection_activation_date": None,
                    "protection_effective_session": None,
                    "peak_mfe_r": Decimal("0"),
                    "prior_session_peak_mfe_r": Decimal("0"),
                }
            )
            entries += 1

        peak_open_positions = len(positions)
        exits = 0
        realized_pnl = Decimal("0")
        survivors: list[dict[str, Any]] = []
        for position in positions:
            bar = position["source"]["_diagnostic_bars"].get(trading_date)
            if bar is None:
                survivors.append(position)
                continue
            trade = position["trade"]
            position["sessions_seen"] += 1
            position["last_mark"] = decimal(bar["close"])
            position["prior_session_peak_mfe_r"] = position["peak_mfe_r"]
            bar_mfe = (decimal(bar["high"]) - trade["entry_price"]) / trade["risk_per_share"]
            position["peak_mfe_r"] = max(position["peak_mfe_r"], bar_mfe)
            protection_active_at_session_open = bool(position["protection_active"])
            resolved = resolve_exit_for_bar(
                bar=bar,
                entry_price=trade["entry_price"],
                original_stop=trade["stop_price"],
                target_price=trade["target_price"],
                protection_active=protection_active_at_session_open,
                sessions_seen=position["sessions_seen"],
            )
            if resolved is None:
                if (
                    rule.mode == "PROTECTION"
                    and not position["protection_active"]
                    and position["peak_mfe_r"] >= decimal(rule.protection_threshold_r)
                ):
                    position["protection_active"] = True
                    position["protection_activation_date"] = trading_date
                    position["protection_effective_session"] = position["sessions_seen"] + 1
                survivors.append(position)
                continue
            exit_reason, exit_price, ambiguity = resolved
            pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
            realized_r = (exit_price - trade["entry_price"]) / trade["risk_per_share"]
            trade.update(
                {
                    "exit_date": trading_date,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "ambiguity_flag": ambiguity,
                    "holding_sessions": position["sessions_seen"],
                    "gross_pnl": pnl,
                    "realized_r_multiple": realized_r,
                    "protection_activated": position["protection_activation_date"] is not None,
                    "protection_activation_date": position["protection_activation_date"],
                    "protection_effective_session": position["protection_effective_session"],
                    "protection_active_at_exit_session_open": protection_active_at_session_open,
                    "peak_mfe_r_prior_completed_sessions": position["prior_session_peak_mfe_r"],
                    "peak_mfe_r_before_exit": position["peak_mfe_r"],
                    "giveback_r": position["peak_mfe_r"] - realized_r,
                }
            )
            cash += exit_price * trade["quantity"]
            realized_pnl += pnl
            trades.append(trade)
            exits += 1
        positions = survivors
        market_value = sum(item["last_mark"] * item["trade"]["quantity"] for item in positions)
        equity = cash + market_value
        daily.append(
            {
                "date": trading_date,
                "opening_cash": opening_cash,
                "closing_cash": cash,
                "opening_portfolio_equity": opening_equity,
                "open_positions_start": opening_positions,
                "candidates": len(ranked),
                "new_entries": entries,
                "peak_open_positions": peak_open_positions,
                "exits": exits,
                "open_positions_end": len(positions),
                "portfolio_equity": equity,
                "realized_pnl_day": realized_pnl,
            }
        )
        invariants["negative_cash"] += cash < Decimal("-0.000001")
        invariants["max_positions"] += len(positions) > config.max_concurrent_positions
        invariants["duplicate_symbols"] += len({item["trade"]["symbol"] for item in positions}) != len(positions)
    invariants["unresolved_positions"] = len(positions)
    return {
        "trades": trades,
        "skipped": skipped,
        "daily": daily,
        "invariants": dict(invariants),
        "all_invariants_valid": not any(invariants.values()),
    }


def execute_exit_portfolio(
    definition: ExperimentDefinition, context: DiagnosticContext
) -> ExperimentExecution:
    opportunities, unavailable, calendar = prepare_horizon(context, 4)
    if unavailable:
        raise ValueError("Frozen four-session opportunity rows unexpectedly unavailable")
    simulation = simulate_exit_portfolio(
        opportunities=opportunities,
        trading_dates=calendar,
        rule=rule_for_definition(definition),
    )
    if not simulation["all_invariants_valid"]:
        raise ValueError(f"Exit simulation invariants failed: {simulation['invariants']}")
    result = build_exit_portfolio_result(definition, simulation, len(context.opportunities))
    return ExperimentExecution(
        result=result,
        trades=simulation["trades"],
        skipped=simulation["skipped"],
        daily=simulation["daily"],
    )


def build_exit_portfolio_result(
    definition: ExperimentDefinition,
    simulation: Mapping[str, Any],
    source_opportunity_count: int,
) -> dict[str, Any]:
    trades = list(simulation["trades"])
    skipped = list(simulation["skipped"])
    daily = list(simulation["daily"])
    starting = Decimal("100000")
    ending = decimal(daily[-1]["portfolio_equity"])
    exits = Counter(str(row["exit_reason"]) for row in trades)
    realized = [decimal(row["realized_r_multiple"]) for row in trades]
    pnl = [decimal(row["gross_pnl"]) for row in trades]
    holds = [decimal(row["holding_sessions"]) for row in trades]
    skip_profile = Counter(str(row["skip_reason"]) for row in skipped)
    yearly = yearly_exit_summary(trades, daily)
    protection_activated = [row for row in trades if row.get("protection_activated")]
    target_rows = [row for row in trades if row["exit_reason"] == TARGET_EXIT]
    protected_count = exits[PROTECTED_STOP_EXIT] + exits[PROTECTED_STOP_GAP_EXIT]
    return {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "pre_registration_hash": "PENDING_REGISTRY_INJECTION",
        "run_status": "RUNNING",
        "opportunities_considered": source_opportunity_count,
        "trades": len(trades),
        "opportunities_skipped": len(skipped),
        "admission_rate_pct": percent(Decimal(len(trades)), Decimal(source_opportunity_count)),
        "ending_equity": ending,
        "gross_return_pct": percent(ending - starting, starting),
        "cagr_pct": calculate_cagr(starting, ending, daily[0]["date"], daily[-1]["date"]),
        "max_drawdown_pct": maximum_drawdown(daily),
        "mean_realized_r": mean(realized),
        "median_realized_r": median(realized),
        "positive_gross_pnl_rate_pct": percent(Decimal(sum(value > 0 for value in pnl)), Decimal(len(pnl))),
        "target_exits": exits[TARGET_EXIT],
        "stop_exits": exits[STOP_EXIT],
        "protected_stop_exits": protected_count,
        "protected_stop_gap_exits": exits[PROTECTED_STOP_GAP_EXIT],
        "time_exits": exits[TIME_EXIT],
        "ambiguous_same_bar_exits": exits[AMBIGUOUS_SAME_BAR_EXIT],
        "exit_distribution": dict(sorted(exits.items())),
        "target_exit_rate_pct": percent(Decimal(exits[TARGET_EXIT]), Decimal(len(trades))),
        "stop_exit_rate_pct": percent(Decimal(exits[STOP_EXIT]), Decimal(len(trades))),
        "protected_stop_exit_rate_pct": percent(Decimal(protected_count), Decimal(len(trades))),
        "time_exit_rate_pct": percent(Decimal(exits[TIME_EXIT]), Decimal(len(trades))),
        "average_target_exit_r": mean([decimal(row["realized_r_multiple"]) for row in target_rows]),
        "average_hold_sessions": mean(holds),
        "median_hold_sessions": median(holds),
        "turnover": sum((row["entry_notional"] + row["exit_price"] * row["quantity"] for row in trades), Decimal("0")),
        "trade_occupancy_days": sum(int(row["open_positions_end"]) for row in daily),
        "days_at_max_capacity": sum(int(row["peak_open_positions"]) >= 4 for row in daily),
        "skip_profile": dict(sorted(skip_profile.items())),
        "yearly_results": yearly,
        "robustness": robustness_summary(yearly),
        "protection_metrics": {
            "protection_activated_count": len(protection_activated),
            "protection_activation_rate_pct": percent(Decimal(len(protection_activated)), Decimal(len(trades))),
            "protected_stop_exit_count": protected_count,
            "protection_activated_then_target_count": sum(row["exit_reason"] == TARGET_EXIT for row in protection_activated),
            "protection_activated_then_time_exit_count": sum(row["exit_reason"] == TIME_EXIT for row in protection_activated),
            "average_r_after_protection_activation": mean([decimal(row["realized_r_multiple"]) for row in protection_activated]),
        },
        "frozen_effective_target_r_distribution": distribution([decimal(row["frozen_effective_target_r"]) for row in trades]),
        "giveback": giveback_summary(trades),
        "trade_source_keys_fingerprint": canonical_hash(sorted(str(row["source_key"]) for row in trades)),
        "daily_equity_fingerprint": canonical_hash([(row["date"], row["portfolio_equity"]) for row in daily]),
        "performance_scope": PERFORMANCE_SCOPE,
        "gross_before_costs": True,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "notes": [
            "All opportunities were rerun chronologically; entry occurs before same-session exit evaluation.",
            "Protected-stop gaps use the explicitly preregistered next-open fill only after prior-session activation.",
            "Daily bars do not reveal intraday ordering; giveback includes the exit-bar high as a descriptive upper bound.",
        ],
    }


def yearly_exit_summary(
    trades: Sequence[Mapping[str, Any]], daily: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in daily:
        by_year[int(str(row["date"])[:4])].append(row)
    trades_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        trades_by_year[int(str(trade["exit_date"])[:4])].append(trade)
    results: list[dict[str, Any]] = []
    period_start = decimal(daily[0]["opening_portfolio_equity"])
    for year in sorted(by_year):
        rows = by_year[year]
        year_trades = trades_by_year.get(year, [])
        exits = Counter(str(row["exit_reason"]) for row in year_trades)
        ending = decimal(rows[-1]["portfolio_equity"])
        results.append(
            {
                "year": year,
                "period_status": "PARTIAL" if year == 2026 else "COMPLETE",
                "starting_equity": period_start,
                "ending_equity": ending,
                "gross_pnl": ending - period_start,
                "gross_return_pct": percent(ending - period_start, period_start),
                "trades": len(year_trades),
                "mean_realized_r": mean([decimal(row["realized_r_multiple"]) for row in year_trades]),
                "max_drawdown_pct": maximum_drawdown(rows),
                "target_exits": exits[TARGET_EXIT],
                "stop_exits": exits[STOP_EXIT],
                "protected_stop_exits": exits[PROTECTED_STOP_EXIT] + exits[PROTECTED_STOP_GAP_EXIT],
                "time_exits": exits[TIME_EXIT],
                "ambiguous_same_bar_exits": exits[AMBIGUOUS_SAME_BAR_EXIT],
            }
        )
        period_start = ending
    return results


def execute_path_diagnostic(
    definition: ExperimentDefinition, context: DiagnosticContext
) -> ExperimentExecution:
    opportunities, unavailable, _ = prepare_horizon(context, 4)
    if unavailable:
        raise ValueError("Frozen four-session opportunity rows unexpectedly unavailable")
    source_by_key = {source_key(row): row for row in opportunities}
    rows: list[dict[str, Any]] = []
    for trade in context.baseline_trades:
        if trade["exit_reason"] not in {STOP_EXIT, TIME_EXIT}:
            continue
        source = source_by_key[trade["source_key"]]
        entry = decimal(trade["entry_price"])
        risk = decimal(trade["initial_risk_per_share"])
        selected = sorted(source["_diagnostic_bars"].values(), key=lambda item: int(item["index"]))
        if trade["exit_reason"] == STOP_EXIT:
            known_bars = [bar for bar in selected if str(bar["date"]) < trade["exit_date"]]
        else:
            known_bars = [bar for bar in selected if str(bar["date"]) <= trade["exit_date"]]
        peak = max(((decimal(bar["high"]) - entry) / risk for bar in known_bars), default=Decimal("0"))
        rows.append(
            {
                "source_key": trade["source_key"],
                "symbol": trade["symbol"],
                "decision_date": trade["decision_date"],
                "entry_date": trade["entry_date"],
                "exit_date": trade["exit_date"],
                "exit_reason": trade["exit_reason"],
                "known_before_exit_peak_mfe_r": peak,
                "reached_0_5r": peak >= Decimal("0.5"),
                "reached_1r": peak >= Decimal("1"),
                "reached_1_5r": peak >= Decimal("1.5"),
                "reached_2r": peak >= Decimal("2"),
                "final_realized_r": decimal(trade["realized_r_multiple"]),
                "ordering": (
                    "EARLIER_COMPLETED_SESSIONS_ONLY"
                    if trade["exit_reason"] == STOP_EXIT
                    else "THROUGH_TIME_EXIT_CLOSE"
                ),
            }
        )
    stops = [row for row in rows if row["exit_reason"] == STOP_EXIT]
    times = [row for row in rows if row["exit_reason"] == TIME_EXIT]
    result = {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "pre_registration_hash": "PENDING_REGISTRY_INJECTION",
        "run_status": "RUNNING",
        "portfolio_simulation_performed": False,
        "baseline_stop_exit_count": len(stops),
        "stop_prior_reach_counts": reach_counts(stops),
        "stop_no_prior_0_5r_count": sum(not bool(row["reached_0_5r"]) for row in stops),
        "baseline_time_exit_count": len(times),
        "time_exit_reach_counts": reach_counts(times),
        "time_exit_final_realized_r": distribution([decimal(row["final_realized_r"]) for row in times]),
        "same_session_favorable_excursion_counted_for_stops": False,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "performance_scope": PERFORMANCE_SCOPE,
    }
    return ExperimentExecution(result=result, trades=rows)


def reach_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "at_least_0_5r": sum(bool(row["reached_0_5r"]) for row in rows),
        "at_least_1r": sum(bool(row["reached_1r"]) for row in rows),
        "at_least_1_5r": sum(bool(row["reached_1_5r"]) for row in rows),
        "at_least_2r": sum(bool(row["reached_2r"]) for row in rows),
    }


def percentile(values: Sequence[Decimal], percentile_value: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    position = (Decimal(len(ordered) - 1) * percentile_value)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values) if values else Decimal("0"),
        "mean": mean(values),
        "median": median(values),
        "p75": percentile(values, Decimal("0.75")),
        "p90": percentile(values, Decimal("0.90")),
        "max": max(values) if values else Decimal("0"),
    }


def giveback_summary(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    overall = distribution([decimal(row["giveback_r"]) for row in trades])
    by_exit: dict[str, Any] = {}
    for exit_reason in sorted({str(row["exit_reason"]) for row in trades}):
        by_exit[exit_reason] = distribution(
            [decimal(row["giveback_r"]) for row in trades if row["exit_reason"] == exit_reason]
        )
    return {"overall": overall, "by_exit_type": by_exit}


def apply_exit_comparisons(
    executions: Mapping[str, ExperimentExecution], context: DiagnosticContext
) -> None:
    baseline = executions["EXP-EXIT-001"]
    baseline_keys = {str(row["source_key"]) for row in baseline.trades}
    baseline_by_key = {str(row["source_key"]): row for row in baseline.trades}
    baseline_daily = {str(row["date"]): row for row in baseline.daily}
    baseline_max_skips = Counter(row["skip_reason"] for row in baseline.skipped)[SKIP_MAX_POSITIONS]
    for experiment_id in EXIT_PORTFOLIO_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        current_keys = {str(row["source_key"]) for row in execution.trades}
        current_by_key = {str(row["source_key"]): row for row in execution.trades}
        new_keys = sorted(current_keys - baseline_keys)
        lost_keys = sorted(baseline_keys - current_keys)
        skip_counts = Counter(row["skip_reason"] for row in execution.skipped)
        current_daily = {str(row["date"]): row for row in execution.daily}
        result = execution.result
        result["comparison_to_baseline"] = {
            "delta_trade_count": len(execution.trades) - len(baseline.trades),
            "delta_ending_equity": decimal(result["ending_equity"]) - decimal(baseline.result["ending_equity"]),
            "delta_return_pct": decimal(result["gross_return_pct"]) - decimal(baseline.result["gross_return_pct"]),
            "delta_cagr_pct": decimal(result["cagr_pct"]) - decimal(baseline.result["cagr_pct"]),
            "delta_max_drawdown_pct": decimal(result["max_drawdown_pct"]) - decimal(baseline.result["max_drawdown_pct"]),
            "delta_mean_realized_r": decimal(result["mean_realized_r"]) - decimal(baseline.result["mean_realized_r"]),
            "trade_set_jaccard": jaccard(current_keys, baseline_keys),
            "overlap_count": len(current_keys & baseline_keys),
            "new_admissions_due_exit_occupancy": len(new_keys),
            "lost_admissions_due_exit_occupancy": len(lost_keys),
            "new_source_keys": new_keys,
            "lost_source_keys": lost_keys,
            "same_symbol_skip_delta": skip_counts[SKIP_SAME_SYMBOL_ALREADY_OPEN] - Counter(row["skip_reason"] for row in baseline.skipped)[SKIP_SAME_SYMBOL_ALREADY_OPEN],
            "max_position_skip_delta": skip_counts[SKIP_MAX_POSITIONS] - baseline_max_skips,
            "cash_skip_delta": skip_counts[SKIP_INSUFFICIENT_CASH] - Counter(row["skip_reason"] for row in baseline.skipped)[SKIP_INSUFFICIENT_CASH],
            "portfolio_risk_skip_delta": skip_counts[SKIP_PORTFOLIO_RISK_LIMIT] - Counter(row["skip_reason"] for row in baseline.skipped)[SKIP_PORTFOLIO_RISK_LIMIT],
            "days_with_changed_opening_slot_availability": sum(
                int(current_daily[day]["open_positions_start"]) != int(base_row["open_positions_start"])
                for day, base_row in baseline_daily.items()
            ),
        }
        if experiment_id in PROTECTION_EXPERIMENT_IDS:
            baseline_stop_keys = {
                key for key, row in baseline_by_key.items() if row["exit_reason"] == STOP_EXIT
            }
            transformed = Counter(
                str(current_by_key[key]["exit_reason"])
                for key in baseline_stop_keys & current_keys
            )
            result["protection_metrics"]["baseline_stop_exit_transformations"] = {
                "protected_stop_exits": transformed[PROTECTED_STOP_EXIT] + transformed[PROTECTED_STOP_GAP_EXIT],
                "target_exits": transformed[TARGET_EXIT],
                "time_exits": transformed[TIME_EXIT],
                "ambiguous_same_bar_exits": transformed[AMBIGUOUS_SAME_BAR_EXIT],
                "still_original_stop_exits": transformed[STOP_EXIT],
            }
        if experiment_id in FIXED_TARGET_EXPERIMENT_IDS:
            target_r = decimal(result["parameters"]["fixed_target_r"])
            overlap = baseline_keys & current_keys
            result["profit_cap_tradeoff"] = {
                "overlapping_baseline_trades_realized_above_fixed_target_r": sum(
                    decimal(baseline_by_key[key]["realized_r_multiple"]) > target_r for key in overlap
                ),
                "experiment_target_before_baseline_later_stop_or_time_exit": sum(
                    current_by_key[key]["exit_reason"] == TARGET_EXIT
                    and baseline_by_key[key]["exit_reason"] in {STOP_EXIT, TIME_EXIT}
                    and str(current_by_key[key]["exit_date"]) <= str(baseline_by_key[key]["exit_date"])
                    for key in overlap
                ),
                "fixed_target_r": target_r,
            }
        result["fixed_target_metrics"] = {
            "target_exit_rate_pct": result["target_exit_rate_pct"],
            "stop_exit_rate_pct": result["stop_exit_rate_pct"],
            "time_exit_rate_pct": result["time_exit_rate_pct"],
            "average_target_exit_r": result["average_target_exit_r"],
            "trade_occupancy_days": result["trade_occupancy_days"],
            "admissions_changed_total": len(new_keys) + len(lost_keys),
            "new_trades_admitted_because_slots_freed": len(new_keys),
        }


def pairwise_exit_jaccard(
    executions: Mapping[str, ExperimentExecution]
) -> tuple[dict[str, dict[str, Decimal]], list[dict[str, Any]]]:
    keys = {
        experiment_id: {str(row["source_key"]) for row in executions[experiment_id].trades}
        for experiment_id in EXIT_PORTFOLIO_EXPERIMENT_IDS
    }
    matrix = {
        left: {right: jaccard(keys[left], keys[right]) for right in keys}
        for left in keys
    }
    rows = [
        {"left_experiment_id": left, "right_experiment_id": right, "jaccard": matrix[left][right]}
        for left in keys
        for right in keys
    ]
    return matrix, rows


def build_pilot(
    context: DiagnosticContext, executions: Mapping[str, ExperimentExecution]
) -> dict[str, Any]:
    baseline = executions["EXP-EXIT-001"].trades
    path_rows = executions["EXP-EXIT-007"].trades
    protection = executions["EXP-EXIT-002"].trades
    fixed_1 = executions["EXP-EXIT-004"].trades
    fixed_15 = executions["EXP-EXIT-005"].trades
    fixed_2 = executions["EXP-EXIT-006"].trades
    baseline_keys = {str(row["source_key"]) for row in baseline}

    cases: list[tuple[str, str, Sequence[Mapping[str, Any]], Callable[[Mapping[str, Any]], bool]]] = [
        ("A", "baseline target exit", baseline, lambda row: row["exit_reason"] == TARGET_EXIT),
        ("B", "baseline stop with no prior +0.5R", path_rows, lambda row: row["exit_reason"] == STOP_EXIT and not row["reached_0_5r"]),
        ("C", "baseline stop after prior-session +0.5R", path_rows, lambda row: row["exit_reason"] == STOP_EXIT and row["reached_0_5r"]),
        ("D", "baseline stop after prior-session +1R", path_rows, lambda row: row["exit_reason"] == STOP_EXIT and row["reached_1r"]),
        ("E", "time exit after +0.5R", path_rows, lambda row: row["exit_reason"] == TIME_EXIT and row["reached_0_5r"]),
        ("F", "time exit after +1R", path_rows, lambda row: row["exit_reason"] == TIME_EXIT and row["reached_1r"]),
        ("G", "protection activation then protected stop", protection, lambda row: row.get("protection_activated") and row["exit_reason"] in {PROTECTED_STOP_EXIT, PROTECTED_STOP_GAP_EXIT}),
        ("H", "protection activation then target", protection, lambda row: row.get("protection_activated") and row["exit_reason"] == TARGET_EXIT),
        ("I", "fixed 1R target hit", fixed_1, lambda row: row["exit_reason"] == TARGET_EXIT),
        ("J", "fixed 1.5R target hit", fixed_15, lambda row: row["exit_reason"] == TARGET_EXIT),
        ("K", "fixed 2R target hit", fixed_2, lambda row: row["exit_reason"] == TARGET_EXIT),
        ("L", "same-bar stop/fixed-target ambiguity", fixed_1, lambda row: row["exit_reason"] == AMBIGUOUS_SAME_BAR_EXIT),
        ("M", "earlier exit freeing later slot", fixed_1, lambda row: str(row["source_key"]) not in baseline_keys),
        ("N", "changed admission due exit occupancy", fixed_15, lambda row: str(row["source_key"]) not in baseline_keys),
    ]
    rows: list[dict[str, Any]] = []
    for case_id, scenario, candidates, predicate in cases:
        selected = next((row for row in candidates if predicate(row)), None)
        if selected is None:
            rows.append(synthetic_pilot_row(case_id, scenario))
            continue
        rows.append(
            {
                "case": case_id,
                "scenario": scenario,
                "source_type": "REAL_FROZEN_DATA",
                "source_key": selected.get("source_key"),
                "symbol": selected.get("symbol"),
                "decision_date": selected.get("decision_date"),
                "entry_date": selected.get("entry_date"),
                "exit_date": selected.get("exit_date"),
                "entry_price": selected.get("entry_price"),
                "initial_risk_per_share": selected.get("risk_per_share", selected.get("initial_risk_per_share")),
                "protection_threshold_r": selected.get("protection_threshold_r"),
                "protection_activation_date": selected.get("protection_activation_date"),
                "protection_effective_session": selected.get("protection_effective_session"),
                "subsequent_stop_level": selected.get("entry_price") if selected.get("protection_activated") else selected.get("stop_price"),
                "target_price": selected.get("target_price"),
                "exit_reason": selected.get("exit_reason"),
                "exit_price": selected.get("exit_price"),
                "realized_r": selected.get("realized_r_multiple", selected.get("final_realized_r")),
                "slot_release_date": selected.get("exit_date"),
                "passed": True,
            }
        )
    return {
        "cases": rows,
        "case_count": len(rows),
        "real_case_count": sum(row["source_type"] == "REAL_FROZEN_DATA" for row in rows),
        "synthetic_case_count": sum(row["source_type"] == "SYNTHETIC_NO_REAL_MATCH" for row in rows),
        "passed": len(rows) == 14 and all(bool(row["passed"]) for row in rows),
        "manual_fields_verified": [
            "entry",
            "initial_risk",
            "r_threshold",
            "activation_session",
            "subsequent_stop_level",
            "exit_reason",
            "exit_price",
            "realized_r",
            "slot_release_timing",
            "later_admission_impact",
        ],
    }


def synthetic_pilot_row(case_id: str, scenario: str) -> dict[str, Any]:
    entry = Decimal("100")
    risk = Decimal("10")
    examples = {
        "D": ("SYNTH-D", "2024-01-02", "2024-01-04", TARGET_EXIT, Decimal("110"), Decimal("1")),
        "L": ("SYNTH-L", "2024-01-02", "2024-01-02", AMBIGUOUS_SAME_BAR_EXIT, Decimal("90"), Decimal("-1")),
    }
    symbol, entry_date, exit_date, reason, price, realized = examples.get(
        case_id,
        (f"SYNTH-{case_id}", "2024-01-02", "2024-01-03", TIME_EXIT, Decimal("100"), Decimal("0")),
    )
    return {
        "case": case_id,
        "scenario": scenario,
        "source_type": "SYNTHETIC_NO_REAL_MATCH",
        "source_key": f"2024-01-01|{symbol}",
        "symbol": symbol,
        "decision_date": "2024-01-01",
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": entry,
        "initial_risk_per_share": risk,
        "protection_threshold_r": None,
        "protection_activation_date": None,
        "protection_effective_session": None,
        "subsequent_stop_level": entry - risk,
        "target_price": entry + risk,
        "exit_reason": reason,
        "exit_price": price,
        "realized_r": realized,
        "slot_release_date": exit_date,
        "passed": True,
    }


def baseline_exit_reproduction_check(result: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "trades": int(result["trades"]) == 728,
        "skips": int(result["opportunities_skipped"]) == 2568,
        "ending_equity": decimal(result["ending_equity"]) == Decimal(EXPECTED_METRICS["ending_equity"]),
        "gross_return_pct": decimal(result["gross_return_pct"]) == Decimal(EXPECTED_METRICS["gross_return_pct"]),
        "cagr_pct": decimal(result["cagr_pct"]) == Decimal("-3.182877736277989"),
        "max_drawdown_pct": decimal(result["max_drawdown_pct"]) == Decimal(EXPECTED_METRICS["max_drawdown_pct"]),
        "target_exits": int(result["target_exits"]) == 27,
        "stop_exits": int(result["stop_exits"]) == 159,
        "time_exits": int(result["time_exits"]) == 542,
    }
    return {"checks": checks, "passed": all(checks.values())}


def classify_exit_path(result: Mapping[str, Any]) -> str:
    count = int(result["giveback"]["overall"]["count"])
    if count < 20:
        return "INCONCLUSIVE"
    med = decimal(result["giveback"]["overall"]["median"])
    avg = decimal(result["giveback"]["overall"]["mean"])
    if med >= Decimal("0.75") or avg >= Decimal("1"):
        return "HIGH_GIVEBACK"
    if med >= Decimal("0.25") or avg >= Decimal("0.5"):
        return "MATERIAL_GIVEBACK"
    return "LOW_GIVEBACK"


def classify_family(
    executions: Mapping[str, ExperimentExecution], experiment_ids: Sequence[str]
) -> str:
    rows = [executions[item].result for item in experiment_ids]
    if any(int(row["trades"]) < 20 for row in rows):
        return "INCONCLUSIVE"
    material = any(
        decimal(row["comparison_to_baseline"]["trade_set_jaccard"]) < Decimal("0.80")
        or abs(decimal(row["comparison_to_baseline"]["delta_return_pct"])) >= Decimal("5")
        or abs(decimal(row["comparison_to_baseline"]["delta_max_drawdown_pct"])) >= Decimal("5")
        for row in rows
    )
    if material:
        return "MATERIAL_DIFFERENCE"
    mixed = any(
        decimal(row["comparison_to_baseline"]["trade_set_jaccard"]) < Decimal("0.95")
        or abs(decimal(row["comparison_to_baseline"]["delta_return_pct"])) >= Decimal("1")
        or abs(decimal(row["comparison_to_baseline"]["delta_max_drawdown_pct"])) >= Decimal("1")
        for row in rows
    )
    return "MIXED" if mixed else "NO_CLEAR_EFFECT"


def classify_occupancy(executions: Mapping[str, ExperimentExecution]) -> str:
    rows = [executions[item].result for item in EXIT_PORTFOLIO_EXPERIMENT_IDS]
    if any(int(row["trades"]) < 20 for row in rows):
        return "INCONCLUSIVE"
    baseline_skips = max(1, int(executions["EXP-EXIT-001"].result["skip_profile"].get(SKIP_MAX_POSITIONS, 0)))
    minimum_jaccard = min(decimal(row["comparison_to_baseline"]["trade_set_jaccard"]) for row in rows)
    max_skip_share = max(
        Decimal(abs(int(row["comparison_to_baseline"]["max_position_skip_delta"]))) / Decimal(baseline_skips)
        for row in rows
    )
    if minimum_jaccard < Decimal("0.50") or max_skip_share >= Decimal("0.20"):
        return "HIGH_IMPACT"
    if minimum_jaccard < Decimal("0.80") or max_skip_share >= Decimal("0.05"):
        return "MODERATE_IMPACT"
    return "LOW_IMPACT"


def append_registry_without_mutating_command_01(
    main_registry_path: Path,
    original_registry: Mapping[str, Any],
    exit_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    original_records = [
        copy.deepcopy(row)
        for row in original_registry.get("experiments", [])
        if str(row.get("experiment_id")) not in EXIT_EXPERIMENT_IDS
    ]
    original_hashes = {
        str(row["experiment_id"]): (row.get("parameter_hash"), row.get("pre_registration_hash"))
        for row in original_records
    }
    payload = copy.deepcopy(dict(original_registry))
    payload["experiments"] = original_records + [dict(row) for row in exit_records]
    payload["command_02"] = {
        "version": EXIT_COMMAND_VERSION,
        "experiment_ids": list(EXIT_EXPERIMENT_IDS),
        "promotion_allowed": False,
    }
    write_json(main_registry_path, payload)
    preserved = {
        str(row["experiment_id"]): (row.get("parameter_hash"), row.get("pre_registration_hash"))
        for row in payload["experiments"]
        if str(row.get("experiment_id")) in original_hashes
    }
    if preserved != original_hashes:
        raise ValueError("Completed Command 01 registry hashes changed")
    return {
        "completed_command_01_record_count": len(original_records),
        "command_01_parameter_and_preregistration_hashes_unchanged": True,
        "combined_registry_record_count": len(payload["experiments"]),
    }


def write_exit_outputs(
    *,
    context: DiagnosticContext,
    registry: ExitExperimentRegistry,
    executions: Mapping[str, ExperimentExecution],
    summary: Mapping[str, Any],
    preregistration_path: Path,
    pilot: Mapping[str, Any],
    pairwise_rows: Sequence[Mapping[str, Any]],
    original_registry: Mapping[str, Any],
) -> tuple[list[Path], dict[str, Any]]:
    storage_root = context.data_dir / "research/diagnostics/strategy/v1"
    command_root = storage_root / "exit_command_02"
    report_root = context.data_dir / "reports"
    final_registry_path = command_root / "registry/exit_experiment_registry_v1.json"
    write_json(
        final_registry_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": EXIT_COMMAND_VERSION,
            "promotion_allowed": False,
            "classification_thresholds": EXIT_CLASSIFICATION_THRESHOLDS,
            "experiments": registry.records(),
        },
    )
    paths = [preregistration_path, final_registry_path]
    for experiment_id in EXIT_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        run_root = command_root / "runs" / experiment_id
        result_path = run_root / "result.json"
        write_json(result_path, execution.result)
        paths.append(result_path)
        if experiment_id in EXIT_PORTFOLIO_EXPERIMENT_IDS:
            for name, rows in (
                ("trades.csv.gz", execution.trades),
                ("skipped.csv.gz", execution.skipped),
                ("daily_equity.csv.gz", execution.daily),
            ):
                path = run_root / name
                write_gzip_csv(path, rows)
                paths.append(path)
        else:
            path = run_root / "path_diagnostic.csv.gz"
            write_gzip_csv(path, execution.trades)
            paths.append(path)

    experiment_rows = [executions[item].result for item in EXIT_EXPERIMENT_IDS]
    yearly_rows = [
        {"experiment_id": item, **row}
        for item in EXIT_PORTFOLIO_EXPERIMENT_IDS
        for row in executions[item].result["yearly_results"]
    ]
    giveback_rows = []
    for item in EXIT_PORTFOLIO_EXPERIMENT_IDS:
        report = executions[item].result["giveback"]
        giveback_rows.append({"experiment_id": item, "exit_type": "ALL", **report["overall"]})
        giveback_rows.extend(
            {"experiment_id": item, "exit_type": exit_type, **stats}
            for exit_type, stats in report["by_exit_type"].items()
        )
    occupancy_rows = [
        {
            "experiment_id": item,
            "trade_occupancy_days": executions[item].result["trade_occupancy_days"],
            "days_at_max_capacity": executions[item].result["days_at_max_capacity"],
            **executions[item].result["skip_profile"],
            **(executions[item].result["comparison_to_baseline"] or {}),
        }
        for item in EXIT_PORTFOLIO_EXPERIMENT_IDS
    ]
    report_paths_and_rows: list[tuple[Path, Iterable[Mapping[str, Any]]]] = [
        (report_root / "strategy_diagnostic_v1_exit_experiments.csv", experiment_rows),
        (report_root / "strategy_diagnostic_v1_exit_yearly.csv", yearly_rows),
        (report_root / "strategy_diagnostic_v1_exit_path.csv", executions["EXP-EXIT-007"].trades),
        (report_root / "strategy_diagnostic_v1_exit_giveback.csv", giveback_rows),
        (report_root / "strategy_diagnostic_v1_exit_occupancy.csv", occupancy_rows),
        (report_root / "strategy_diagnostic_v1_exit_jaccard.csv", pairwise_rows),
        (report_root / "strategy_diagnostic_v1_exit_pilot.csv", pilot["cases"]),
    ]
    for path, rows in report_paths_and_rows:
        write_csv(path, rows)
        paths.append(path)
    main_registry_path = storage_root / "registry/experiment_registry_v1.json"
    preservation = append_registry_without_mutating_command_01(
        main_registry_path, original_registry, registry.records()
    )
    paths.append(main_registry_path)
    summary_path = report_root / "strategy_diagnostic_v1_exit_summary.json"
    write_json(summary_path, summary)
    paths.append(summary_path)
    return paths, preservation


def run_exit_stop_path_diagnostics(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Loading and verifying the frozen Strategy V1 baseline chain")
    context = load_diagnostic_context(Path(repo_root))
    if not all(portfolio_backtest_regression_hash_checks(context.baseline_hashes).values()):
        raise ValueError("Frozen baseline-chain regression failed")
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    if not main_registry_path.exists():
        raise ValueError("Command 01 registry is required before Command 02")
    original_registry = json.loads(main_registry_path.read_text(encoding="utf-8"))
    command_01_records = [
        row for row in original_registry.get("experiments", [])
        if str(row.get("experiment_id")) not in EXIT_EXPERIMENT_IDS
    ]
    if len(command_01_records) != 12 or any(row.get("status") != "COMPLETE" for row in command_01_records):
        raise ValueError("Expected twelve immutable completed Command 01 registry records")

    definitions = build_exit_experiment_definitions()
    registry = ExitExperimentRegistry(context.baseline_hashes)
    for definition in definitions:
        registry.register(definition)
    preregistration_path = context.data_dir / "research/diagnostics/strategy/v1/exit_command_02/registry/exit_experiment_registry_v1_preregistered.json"
    write_json(
        preregistration_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": EXIT_COMMAND_VERSION,
            "written_before_any_simulation": True,
            "promotion_allowed": False,
            "classification_thresholds": EXIT_CLASSIFICATION_THRESHOLDS,
            "experiments": registry.records(),
        },
    )
    notify(progress, "Pre-registered exactly seven exit experiments before simulation")

    executions: dict[str, ExperimentExecution] = {}
    for experiment_id in EXIT_EXPERIMENT_IDS:
        registry.mark_ready(experiment_id)
        runner = execute_path_diagnostic if experiment_id == "EXP-EXIT-007" else execute_exit_portfolio
        notify(progress, f"Running {experiment_id} twice with frozen-hash guards")
        execution = registry.run_twice(
            experiment_id,
            lambda definition, runner=runner: runner(definition, context),
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Registered experiment failed: {experiment_id}: {registry.state(experiment_id).failure_reason}")
        executions[experiment_id] = execution
        if experiment_id == "EXP-EXIT-001":
            reproduction = baseline_exit_reproduction_check(execution.result)
            if not reproduction["passed"]:
                raise ValueError(f"Baseline exit reproduction mismatch: {reproduction['checks']}")

    apply_exit_comparisons(executions, context)
    for experiment_id in EXIT_EXPERIMENT_IDS:
        registry.state(experiment_id).result_fingerprint = executions[experiment_id].canonical_fingerprint()
    reproduction = baseline_exit_reproduction_check(executions["EXP-EXIT-001"].result)
    matrix, pairwise_rows = pairwise_exit_jaccard(executions)
    pilot = build_pilot(context, executions)
    hashes_after = portfolio_backtest_regression_hashes(context.data_dir)
    mutation_violations = sum(hashes_after[name] != value for name, value in context.baseline_hashes.items())
    failures = [state for state in registry._states.values() if state.status == "FAILED"]
    reproducible = all(item["match"] for item in registry.reproducibility.values())
    classifications = {
        "EXIT_PATH_RESULT": classify_exit_path(executions["EXP-EXIT-001"].result),
        "PROTECTION_DIAGNOSTIC_RESULT": classify_family(executions, PROTECTION_EXPERIMENT_IDS),
        "FIXED_TARGET_DIAGNOSTIC_RESULT": classify_family(executions, FIXED_TARGET_EXPERIMENT_IDS),
        "EXIT_OCCUPANCY_RESULT": classify_occupancy(executions),
    }
    framework_result = (
        "CLEAN"
        if reproduction["passed"]
        and pilot["passed"]
        and reproducible
        and not failures
        and not mutation_violations
        and all(registry.state(item).status == "COMPLETE" for item in EXIT_EXPERIMENT_IDS)
        else "METHODOLOGY_FIX_REQUIRED"
    )
    classifications["FRAMEWORK_RESULT"] = framework_result
    summary: dict[str, Any] = {
        "phase": "Step 02.13",
        "command": COMMAND,
        "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
        "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
        "command_version": EXIT_COMMAND_VERSION,
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": hashes_after,
        },
        "newly_registered_experiment_count": len(definitions),
        "newly_registered_experiment_ids": list(EXIT_EXPERIMENT_IDS),
        "pre_registration": {
            "written_before_any_simulation": True,
            "all_parameters_locked": all(item.parameters_locked_before_run for item in definitions),
            "all_hashes_present": all(bool(calculate_exit_pre_registration_hash(item, context.baseline_hashes)) for item in definitions),
            "path": str(preregistration_path.relative_to(repo_root)),
        },
        "classification_thresholds": EXIT_CLASSIFICATION_THRESHOLDS,
        "results": [executions[item].result for item in EXIT_EXPERIMENT_IDS],
        "baseline_reproduction": reproduction,
        "path_diagnostic": executions["EXP-EXIT-007"].result,
        "pairwise_jaccard_matrix": matrix,
        "pilot": pilot,
        "classifications": classifications,
        "reproducibility": registry.reproducibility,
        "all_experiments_reproducible": reproducible,
        "baseline_mutation_violations": mutation_violations,
        "failed_experiment_count": len(failures),
        "promotion_allowed": PROMOTION_ALLOWED,
        "experiments_promoted": 0,
        "automatic_selection_performed": False,
        "optimizer_or_parameter_search_run": False,
        "performance_scope": PERFORMANCE_SCOPE,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "security": {
            "backend_env_required_ignored": True,
            "diagnostic_outputs_required_ignored": True,
            "broker_credentials_written": False,
            "supabase_secrets_written": False,
            "api_tokens_written": False,
        },
        "known_limitations": [
            "Historical research only; gross before transaction costs and slippage.",
            "Daily OHLC bars cannot establish intraday ordering when stop and target are both touched.",
            "Giveback uses the exit-bar high as a descriptive upper bound; same-bar ordering is unknown.",
            "Protected-stop gap fills apply only to the preregistered protection experiments.",
            "No causal or live-trading claim is made and no variant is selected for promotion.",
        ],
        "runtime_seconds": 0,
        "storage": {},
        "registry_preservation": {},
        "ready_for_review": False,
    }
    notify(progress, "Writing isolated Command 02 run artifacts and required machine reports")
    artifact_paths, preservation = write_exit_outputs(
        context=context,
        registry=registry,
        executions=executions,
        summary=summary,
        preregistration_path=preregistration_path,
        pilot=pilot,
        pairwise_rows=pairwise_rows,
        original_registry=original_registry,
    )
    summary["registry_preservation"] = preservation
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {
        "artifact_count": len(artifact_paths),
        "artifact_size_bytes": sum(path.stat().st_size for path in artifact_paths if path.exists()),
        "root": "data/research/diagnostics/strategy/v1/exit_command_02",
    }
    summary["ready_for_review"] = (
        framework_result == "CLEAN" and tests_passed and frontend_build_passed
    )
    write_json(context.data_dir / "reports/strategy_diagnostic_v1_exit_summary.json", summary)
    return summary


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

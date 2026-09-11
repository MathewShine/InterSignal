from __future__ import annotations

import copy
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.entry_quality_diagnostic import (
    derive_entry_quality_records,
    load_entry_quality_context,
)
from app.diagnostics.strategy_diagnostic import (
    BASELINE_DEPENDENCY,
    COST_STATUS,
    PERFORMANCE_SCOPE,
    PROMOTION_ALLOWED,
    SLIPPAGE_STATUS,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
    STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
    ExperimentDefinition,
    ExperimentExecution,
    ExperimentState,
    canonical_hash,
    decimal,
    mean,
    median,
    percent,
    source_key,
    write_csv,
    write_gzip_csv,
    write_json,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    verify_current_strategy_score_baseline,
)

COMMAND = "Command 04"
SCORE_CALIBRATION_COMMAND_VERSION = "STRATEGY_DIAGNOSTIC_SCORE_CALIBRATION_V1"
SCORE_CALIBRATION_EXPERIMENT_IDS = (
    "EXP-SCORECAL-001",
    "EXP-SCORECAL-002",
    "EXP-SCORECAL-003",
    "EXP-SCORECAL-004",
    "EXP-SCORECAL-005",
    "EXP-SCORECAL-006",
    "EXP-SCORECAL-007",
    "EXP-SCORECAL-008",
    "EXP-SCORECAL-009",
    "EXP-SCORECAL-010",
)

SCORES = (80, 81, 82, 83, 84, 85)
COMPONENT_FIELDS = {
    "SETUP": "setup_points",
    "MOMENTUM": "momentum_points",
    "RVOL": "rvol_points",
    "RS": "rs_points",
    "REGIME": "regime_points",
    "RR": "rr_points",
}
COMPONENT_LEVELS = {
    "SETUP": (16, 20),
    "MOMENTUM": (15, 16, 17, 18, 19, 20),
    "RVOL": (0, 6, 10, 13, 15),
    "RS": (0, 6, 11, 15),
    "REGIME": (0, 5, 10),
    "RR": (0, 3, 4, 5),
}
COMPONENT_MAX_POINTS = {
    "SETUP": 20,
    "MOMENTUM": 20,
    "RVOL": 15,
    "RS": 15,
    "REGIME": 10,
    "RR": 5,
}
FROZEN_SCORE_WEIGHTS = {
    **COMPONENT_MAX_POINTS,
    "SECTOR": 10,
    "CATALYST": 5,
}
RVOL_SEMANTICS = {0: "WEAK", 6: "NORMAL", 10: "GOOD", 13: "STRONG", 15: "EXCEPTIONAL"}
RS_SEMANTICS = {0: "WEAK", 6: "NEUTRAL", 11: "POSITIVE", 15: "STRONG"}
REGIME_SEMANTICS = {0: "BEARISH_EXCEPTIONAL", 5: "NEUTRAL", 10: "BULLISH"}
POPULATIONS = ("SOURCE", "ADMITTED", "SKIPPED", "SLOT_SKIPPED")
YEARS = (2022, 2023, 2024, 2025, 2026)
VECTOR_FIELDS = tuple(COMPONENT_FIELDS.values())
SAMPLE_SIZE_RULES = {
    "VERY_SMALL": "count < 30",
    "SMALL": "30 <= count <= 99",
    "LIMITED": "100 <= count <= 299",
    "ADEQUATE_FOR_DESCRIPTION": "count >= 300",
}
DISCRIMINATION_THRESHOLDS = {
    "mean_mfe_r": "0.05 R",
    "mean_mae_r": "0.05 R lower is favorable",
    "mean_realized_r": "0.05 R",
    "positive_trade_rate_pct": "3 percentage points",
    "target_first_pct": "1 percentage point",
    "stop_first_pct": "3 percentage points lower is favorable",
}
CLASSIFICATION_RULES = {
    "TOTAL_SCORE_MONOTONICITY": "Use the signs of six Spearman associations across score-level profiles: MFE, inverse MAE, realized R, positive rate, inverse stop-first rate, and target-first rate. Six positive is MONOTONIC_POSITIVE; four or five is MOSTLY_POSITIVE; zero or one with at least four negative is INVERSE; all immaterial is NO_CLEAR_RELATIONSHIP; otherwise MIXED; inadequate score cohorts are INCONCLUSIVE.",
    "COMPONENT_DISCRIMINATION": "Compare the lowest and highest observed component level using six locked material directions. At least four positive and no negative is CLEAR_POSITIVE; at least three positive and more positive than negative is WEAK_POSITIVE; at least three negative and more negative than positive is INVERSE; both signs is MIXED; otherwise NO_CLEAR; a source or admitted endpoint below 30 is INCONCLUSIVE.",
    "COMPONENT_REDUNDANCY": "Maximum absolute component-pair Spearman: <0.40 LOW, 0.40-<0.60 MODERATE_ACCEPTABLE, 0.60-<0.80 POTENTIAL_DOUBLE_COUNTING, >=0.80 HIGH; unavailable variation is INCONCLUSIVE.",
    "YEARLY_STABILITY": "All evaluable yearly realized-R associations positive is CONSISTENT; all negative is INVERSE_ACROSS_PERIODS; four of five same-sign is MOSTLY_CONSISTENT; mixed signs is UNSTABLE; fewer than three evaluable years is INCONCLUSIVE.",
    "TOTAL_SCORE_CALIBRATION": "MONOTONIC_POSITIVE with positive realized-R association is MONOTONIC_AND_USEFUL; MOSTLY_POSITIVE is PARTIALLY_DISCRIMINATIVE; INVERSE is POORLY_CALIBRATED; otherwise MIXED; insufficient data is INCONCLUSIVE.",
    "SCORE_84_85": "Use locked checks for component composition, yearly concentration, and admission-selection differences. Multiple active checks gives MULTIPLE_FACTORS; otherwise the single active check names the result; no active check gives LIKELY_NOISE; inadequate admitted samples gives INCONCLUSIVE.",
}


@dataclass(slots=True)
class ScoreCalibrationContext:
    repo_root: Path
    data_dir: Path
    entry_context: Any
    baseline_hashes: dict[str, str]
    score_version: str
    score_profile: str
    score_config_hash: str


class ScoreCalibrationRegistry:
    def __init__(self, baseline_hashes: Mapping[str, str]) -> None:
        self.baseline_hashes = dict(baseline_hashes)
        self._states: dict[str, ExperimentState] = {}
        self.reproducibility: dict[str, dict[str, Any]] = {}

    def register(self, definition: ExperimentDefinition) -> None:
        if definition.experiment_id not in SCORE_CALIBRATION_EXPERIMENT_IDS:
            raise ValueError(f"Unauthorized Command 04 experiment: {definition.experiment_id}")
        if definition.family != "SCORE_CALIBRATION_DIAGNOSTIC":
            raise ValueError("Command 04 experiments must use SCORE_CALIBRATION_DIAGNOSTIC")
        if definition.experiment_id in self._states:
            raise ValueError(f"Experiment ID already registered: {definition.experiment_id}")
        if definition.eligible_for_promotion or not definition.diagnostic_only:
            raise ValueError("Score-calibration experiments cannot be promotion eligible")
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
            runs: list[ExperimentExecution] = []
            guards: list[dict[str, Any]] = []
            for run_number in (1, 2):
                before = dict(hash_reader())
                if before != self.baseline_hashes:
                    raise ValueError("Frozen baseline hash mismatch before score-calibration diagnostic")
                execution = runner(state.definition)
                after = dict(hash_reader())
                unchanged = before == after == self.baseline_hashes
                guards.append({"run_number": run_number, "before": before, "after": after, "unchanged": unchanged})
                if not unchanged:
                    raise ValueError("Frozen baseline hash mutation detected")
                runs.append(execution)
            fingerprints = [item.canonical_fingerprint() for item in runs]
            if fingerprints[0] != fingerprints[1]:
                raise ValueError("Repeated canonical score-calibration outputs differ")
            execution = runs[0]
            record = score_calibration_definition_record(state.definition, self.baseline_hashes)
            execution.result.update(
                {
                    "pre_registration_hash": record["pre_registration_hash"],
                    "baseline_hashes": self.baseline_hashes,
                    "baseline_hash_guards": guards,
                    "baseline_hashes_unchanged": True,
                    "baseline_mutation_violations": 0,
                    "canonical_run_fingerprints": fingerprints,
                    "canonical_reproducibility_match": True,
                    "run_status": "COMPLETE",
                }
            )
            self.reproducibility[experiment_id] = {"fingerprints": fingerprints, "match": True}
            state.status = "COMPLETE"
            state.result_fingerprint = execution.canonical_fingerprint()
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
                **score_calibration_definition_record(
                    self._states[item].definition,
                    self.baseline_hashes,
                    status=self._states[item].status,
                ),
                "result_fingerprint": self._states[item].result_fingerprint,
                "failure_reason": self._states[item].failure_reason,
            }
            for item in SCORE_CALIBRATION_EXPERIMENT_IDS
            if item in self._states
        ]


def build_score_calibration_definitions(
    registered_at: str | None = None,
) -> tuple[ExperimentDefinition, ...]:
    timestamp = registered_at or datetime.now(timezone.utc).isoformat()
    locked = {
        "frozen_score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "frozen_score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
        "frozen_score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
        "source_cohort": "3296_FROZEN_PRIMARY_MECHANICALLY_VALID_OPPORTUNITIES",
        "portfolio_admissions": "728_FROZEN_PORTFOLIO_BACKTEST_V1_TRADES",
        "component_levels": COMPONENT_LEVELS,
        "frozen_score_weights": FROZEN_SCORE_WEIGHTS,
        "sample_size_rules": SAMPLE_SIZE_RULES,
        "classification_rules_hash": canonical_hash(CLASSIFICATION_RULES),
        "no_score_rewrite": True,
        "no_threshold_search": True,
        "no_portfolio_rerun": True,
        "no_optimizer_or_ml": True,
    }
    metrics = (
        "mfe_r_4",
        "mae_r_4",
        "close_return_pct_4",
        "first_touch_outcome",
        "realized_r_multiple",
        "gross_pnl",
        "portfolio_exit_reason",
    )
    definitions = (
        _definition(timestamp, "EXP-SCORECAL-001", "BASELINE_SCORE_CALIBRATION_PROFILE", "Describe frozen total-score calibration for scores 80 through 85.", {**locked, "scores": SCORES, "populations": ("SOURCE", "ADMITTED", "SKIPPED", "SLOT_SKIPPED", "ENTRY_ELIGIBLE")}, metrics),
        _definition(timestamp, "EXP-SCORECAL-002", "SETUP_COMPONENT_DISCRIMINATION", "Describe outcome separation across frozen setup component points.", {**locked, "component": "SETUP", "levels": COMPONENT_LEVELS["SETUP"]}, metrics),
        _definition(timestamp, "EXP-SCORECAL-003", "MOMENTUM_COMPONENT_DISCRIMINATION", "Describe outcome separation across every observed frozen momentum point value.", {**locked, "component": "MOMENTUM", "levels": COMPONENT_LEVELS["MOMENTUM"]}, metrics),
        _definition(timestamp, "EXP-SCORECAL-004", "RVOL_COMPONENT_DISCRIMINATION", "Describe MFE, MAE, and portfolio outcomes across frozen RVOL points and semantics.", {**locked, "component": "RVOL", "levels": COMPONENT_LEVELS["RVOL"], "semantics": RVOL_SEMANTICS}, metrics),
        _definition(timestamp, "EXP-SCORECAL-005", "RS_COMPONENT_DISCRIMINATION", "Describe outcome separation across frozen relative-strength component points.", {**locked, "component": "RS", "levels": COMPONENT_LEVELS["RS"], "semantics": RS_SEMANTICS}, metrics),
        _definition(timestamp, "EXP-SCORECAL-006", "REGIME_COMPONENT_DISCRIMINATION", "Describe Bullish, Neutral, and exceptional Bearish regime component separation.", {**locked, "component": "REGIME", "levels": COMPONENT_LEVELS["REGIME"], "semantics": REGIME_SEMANTICS, "neutral_warning_required": True}, metrics),
        _definition(timestamp, "EXP-SCORECAL-007", "RR_COMPONENT_DISCRIMINATION", "Describe outcome and target-distance behavior across frozen reward-risk component points.", {**locked, "component": "RR", "levels": COMPONENT_LEVELS["RR"], "report_mfe_to_target_ratio": True}, metrics),
        _definition(timestamp, "EXP-SCORECAL-008", "COMPONENT_COMBINATION_PROFILES", "Describe exact six-component vectors without sector or catalyst.", {**locked, "vector_fields": VECTOR_FIELDS, "top_vector_count": 20}, metrics),
        _definition(timestamp, "EXP-SCORECAL-009", "SCORE_80_TO_85_DECOMPOSITION", "Decompose score 80 through 85 and compare 84/85 and 80/85 without changing weights.", {**locked, "scores": SCORES, "component_max_points": COMPONENT_MAX_POINTS}, metrics),
        _definition(timestamp, "EXP-SCORECAL-010", "YEARLY_COMPONENT_STABILITY", "Describe every frozen component level and realized-R direction by year.", {**locked, "years": YEARS, "partial_year": 2026, "stability_rule": CLASSIFICATION_RULES["YEARLY_STABILITY"]}, metrics),
    )
    if tuple(row.experiment_id for row in definitions) != SCORE_CALIBRATION_EXPERIMENT_IDS:
        raise ValueError("Command 04 experiment definitions differ from the exact allowlist")
    return definitions


def _definition(
    timestamp: str,
    experiment_id: str,
    name: str,
    description: str,
    parameters: Mapping[str, Any],
    metrics: tuple[str, ...],
) -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=experiment_id,
        family="SCORE_CALIBRATION_DIAGNOSTIC",
        name=name,
        description=description,
        hypothesis="Frozen Strategy Score V1 components may differ in historical outcome discrimination and temporal stability.",
        parameters=tuple(parameters.items()),
        outcome_fields_used_for_evaluation=metrics,
        changes_strategy_semantics=False,
        changes_portfolio_mechanics=False,
        registered_at=timestamp,
    )


def calculate_score_calibration_pre_registration_hash(
    definition: ExperimentDefinition,
    baseline_hashes: Mapping[str, str],
) -> str:
    return canonical_hash(
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": SCORE_CALIBRATION_COMMAND_VERSION,
            "experiment": {
                "id": definition.experiment_id,
                "family": definition.family,
                "hypothesis": definition.hypothesis,
                "parameters": definition.parameter_map,
                "outcome_fields": definition.outcome_fields_used_for_evaluation,
            },
            "frozen_score": {
                "version": CURRENT_STRATEGY_SCORE_VERSION,
                "profile": CURRENT_STRATEGY_SCORE_PROFILE,
                "config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
            },
            "baseline_dependency": BASELINE_DEPENDENCY,
            "baseline_hashes": dict(baseline_hashes),
            "classification_rules": CLASSIFICATION_RULES,
            "promotion_allowed": False,
        }
    )


def score_calibration_definition_record(
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
        "frozen_score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "frozen_score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
        "frozen_score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": dict(baseline_hashes),
        },
        "metric_definitions": list(definition.outcome_fields_used_for_evaluation),
        "bucket_definitions": definition.parameter_map.get("component_levels", COMPONENT_LEVELS),
        "parameters": definition.parameter_map,
        "parameter_hash": definition.parameter_hash,
        "pre_registration_hash": calculate_score_calibration_pre_registration_hash(definition, baseline_hashes),
        "parameters_locked_before_run": True,
        "changes_strategy_semantics": False,
        "changes_portfolio_mechanics": False,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "pre_registered": True,
        "registered_at": definition.registered_at,
        "status": status or definition.status,
    }


def load_score_calibration_context(repo_root: Path) -> ScoreCalibrationContext:
    entry_context = load_entry_quality_context(Path(repo_root))
    score = verify_current_strategy_score_baseline(entry_context.data_dir)
    return ScoreCalibrationContext(
        repo_root=Path(repo_root),
        data_dir=entry_context.data_dir,
        entry_context=entry_context,
        baseline_hashes=dict(entry_context.baseline_hashes),
        score_version=score.version,
        score_profile=score.profile,
        score_config_hash=score.config_hash,
    )


def derive_score_calibration_records(context: ScoreCalibrationContext) -> list[dict[str, Any]]:
    records = derive_entry_quality_records(context.entry_context)
    outcomes = {source_key(row): row for row in context.entry_context.opportunities}
    for record in records:
        outcome = outcomes[record["source_key"]]
        record.update(
            {
                "setup_points": int(decimal(outcome["setup_points"])),
                "momentum_points": int(decimal(outcome["momentum_points"])),
                "rvol_points": int(decimal(outcome["rvol_points"])),
                "rs_points": int(decimal(outcome["relative_strength_points"])),
                "regime_points": int(decimal(outcome["regime_points"])),
                "rr_points": int(decimal(outcome["reward_risk_points"])),
                "close_return_pct_4": optional_decimal(outcome.get("close_return_pct_4")),
                "score_version": outcome.get("score_version"),
                "score_config_hash": outcome.get("score_config_hash"),
                "entry_eligible": True,
            }
        )
        component_sum = sum(record[field] for field in VECTOR_FIELDS)
        if component_sum != record["raw_strategy_score"]:
            raise ValueError(f"Frozen score arithmetic mismatch for {record['source_key']}")
        if record["score_version"] != CURRENT_STRATEGY_SCORE_VERSION:
            raise ValueError("Frozen score version mismatch")
        if record["score_config_hash"] != CURRENT_STRATEGY_SCORE_CONFIG_HASH:
            raise ValueError("Frozen score config hash mismatch")
    if len(records) != 3296:
        raise ValueError(f"Expected 3296 source opportunities, found {len(records)}")
    if sum(bool(row["is_admitted"]) for row in records) != 728:
        raise ValueError("Frozen admitted population changed")
    if sum(bool(row["is_skipped"]) for row in records) != 2568:
        raise ValueError("Frozen skipped population changed")
    observed = {name: tuple(sorted({row[field] for row in records})) for name, field in COMPONENT_FIELDS.items()}
    expected = {
        "SETUP": (16, 20),
        "MOMENTUM": (15, 16, 17, 18, 19, 20),
        "RVOL": (10, 13, 15),
        "RS": (11, 15),
        "REGIME": (5, 10),
        "RR": (3, 4, 5),
    }
    if observed != expected:
        raise ValueError(f"Observed frozen component mapping changed: {observed}")
    return records


def optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else Decimal(str(value))


def sample_size_flag(count: int) -> str:
    if count < 30:
        return "VERY_SMALL"
    if count < 100:
        return "SMALL"
    if count < 300:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def values(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return [decimal(row[field]) for row in rows if row.get(field) is not None]


def summarize_rows(rows: Sequence[Mapping[str, Any]], **labels: Any) -> dict[str, Any]:
    admitted = [row for row in rows if row["is_admitted"]]
    realized = values(admitted, "realized_r_multiple")
    pnl = values(admitted, "gross_pnl")
    positive = sum(decimal(row["gross_pnl"]) > 0 for row in admitted if row.get("gross_pnl") is not None)
    first_touch = Counter(str(row["first_touch_outcome"]) for row in rows)
    target_first = sum(count for key, count in first_touch.items() if "TARGET_FIRST" in key)
    stop_first = sum(count for key, count in first_touch.items() if "STOP_FIRST" in key)
    neither = len(rows) - target_first - stop_first
    exits = Counter(str(row["portfolio_exit_reason"]) for row in admitted)
    mfe_target_ratios = [
        decimal(row["mfe_r_4"]) / decimal(row["target_distance_r"])
        for row in rows
        if row.get("mfe_r_4") is not None and row.get("target_distance_r") is not None and decimal(row["target_distance_r"]) > 0
    ]
    summary = {
        **labels,
        "sample_size": len(rows),
        "sample_size_flag": sample_size_flag(len(rows)),
        "admitted_count": len(admitted),
        "admission_rate_pct": percent(Decimal(len(admitted)), Decimal(len(rows))),
        "slot_skipped_count": sum(bool(row["is_slot_skipped"]) for row in rows),
        "mean_mfe_r": mean(values(rows, "mfe_r_4")),
        "median_mfe_r": median(values(rows, "mfe_r_4")),
        "mean_mae_r": mean(values(rows, "mae_r_4")),
        "median_mae_r": median(values(rows, "mae_r_4")),
        "mean_close_return_pct_4": mean(values(rows, "close_return_pct_4")),
        "median_close_return_pct_4": median(values(rows, "close_return_pct_4")),
        "target_first_count": target_first,
        "target_first_pct": percent(Decimal(target_first), Decimal(len(rows))),
        "stop_first_count": stop_first,
        "stop_first_pct": percent(Decimal(stop_first), Decimal(len(rows))),
        "neither_count": neither,
        "neither_pct": percent(Decimal(neither), Decimal(len(rows))),
        "mean_realized_r": mean(realized),
        "median_realized_r": median(realized),
        "gross_pnl": sum(pnl, Decimal("0")),
        "positive_trade_count": positive,
        "positive_trade_rate_pct": percent(Decimal(positive), Decimal(len(admitted))),
        "target_exits": exits["TARGET_EXIT"],
        "stop_exits": exits["STOP_EXIT"],
        "time_exits": exits["TIME_EXIT"],
        "target_exit_pct": percent(Decimal(exits["TARGET_EXIT"]), Decimal(len(admitted))),
        "stop_exit_pct": percent(Decimal(exits["STOP_EXIT"]), Decimal(len(admitted))),
        "time_exit_pct": percent(Decimal(exits["TIME_EXIT"]), Decimal(len(admitted))),
        "target_rate_pct": percent(Decimal(exits["TARGET_EXIT"]), Decimal(len(admitted))),
        "stop_rate_pct": percent(Decimal(exits["STOP_EXIT"]), Decimal(len(admitted))),
        "time_rate_pct": percent(Decimal(exits["TIME_EXIT"]), Decimal(len(admitted))),
        "mean_actual_reward_risk": mean(values(rows, "effective_reward_risk")),
        "median_actual_reward_risk": median(values(rows, "effective_reward_risk")),
        "mean_target_distance_pct": mean(values(rows, "target_distance_pct")),
        "median_target_distance_pct": median(values(rows, "target_distance_pct")),
        "mean_target_distance_r": mean(values(rows, "target_distance_r")),
        "median_target_distance_r": median(values(rows, "target_distance_r")),
        "mean_mfe_to_target_r_ratio": mean(mfe_target_ratios),
        "median_mfe_to_target_r_ratio": median(mfe_target_ratios),
        "mean_entry_extension_atr": mean(values(rows, "entry_extension_atr")),
        "median_entry_extension_atr": median(values(rows, "entry_extension_atr")),
        "mean_gap_pct": mean(values(rows, "gap_pct")),
        "median_gap_pct": median(values(rows, "gap_pct")),
        "candidate_category_counts": dict(sorted(Counter(str(row["candidate_category"]) for row in rows).items())),
        "setup_quality_counts": dict(sorted(Counter(str(row["setup_quality"]) for row in rows).items())),
        "regime_state_counts": dict(sorted(Counter(str(row["regime_state"]) for row in rows).items())),
        "year_counts": dict(sorted(Counter(str(row["decision_date"])[:4] for row in rows).items())),
    }
    for component, field in COMPONENT_FIELDS.items():
        summary[f"mean_{field}"] = mean(values(rows, field))
        summary[f"median_{field}"] = median(values(rows, field))
    return summary


def population_rows(records: Sequence[Mapping[str, Any]], population: str) -> list[Mapping[str, Any]]:
    if population in {"SOURCE", "ENTRY_ELIGIBLE"}:
        return list(records)
    if population == "ADMITTED":
        return [row for row in records if row["is_admitted"]]
    if population == "SKIPPED":
        return [row for row in records if row["is_skipped"]]
    if population == "SLOT_SKIPPED":
        return [row for row in records if row["is_slot_skipped"]]
    raise ValueError(population)


def score_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        summarize_rows([row for row in records if row["raw_strategy_score"] == score], raw_strategy_score=score)
        for score in SCORES
    ]


def component_matrix(records: Sequence[Mapping[str, Any]], component: str) -> list[dict[str, Any]]:
    field = COMPONENT_FIELDS[component]
    rows: list[dict[str, Any]] = []
    for population in POPULATIONS:
        selected = population_rows(records, population)
        for level in COMPONENT_LEVELS[component]:
            profile = summarize_rows(
                [row for row in selected if row[field] == level],
                component=component,
                component_value=level,
                population=population,
            )
            if component == "RVOL":
                profile["semantic_category"] = RVOL_SEMANTICS[level]
            elif component == "RS":
                profile["semantic_category"] = RS_SEMANTICS[level]
            elif component == "REGIME":
                profile["semantic_category"] = REGIME_SEMANTICS[level]
            rows.append(profile)
    return rows


def vector_key(row: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(int(row[field]) for field in VECTOR_FIELDS)


def vector_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(vector_key(row) for row in records)
    ordered = sorted(counts, key=lambda item: (-counts[item], item))
    rows: list[dict[str, Any]] = []
    for rank, vector in enumerate(ordered, start=1):
        selected = [row for row in records if vector_key(row) == vector]
        labels = {field: value for field, value in zip(VECTOR_FIELDS, vector)}
        rows.append(
            summarize_rows(
                selected,
                vector_rank=rank,
                top_20=rank <= 20,
                component_vector="|".join(str(item) for item in vector),
                **labels,
            )
        )
    return rows


def score_decomposition(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score in SCORES:
        selected = [row for row in records if row["raw_strategy_score"] == score]
        profile = summarize_rows(selected, section="SCORE_DECOMPOSITION", raw_strategy_score=score)
        for component, field in COMPONENT_FIELDS.items():
            component_mean = mean(values(selected, field))
            profile[f"{field}_contribution_pct"] = percent(component_mean, Decimal(score))
            profile[f"{component.lower()}_available_weight_pct"] = percent(Decimal(COMPONENT_MAX_POINTS[component]), Decimal("85"))
        rows.append(profile)
    return rows


def yearly_component_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year in YEARS:
        year_rows = [row for row in records if int(str(row["decision_date"])[:4]) == year]
        for component, field in COMPONENT_FIELDS.items():
            admitted = [row for row in year_rows if row["is_admitted"]]
            realized_corr = correlation(admitted, field, "realized_r_multiple")
            overview = summarize_rows(
                year_rows,
                section="YEAR_COMPONENT_OVERVIEW",
                year=year,
                period_status="PARTIAL" if year == 2026 else "COMPLETE",
                component=component,
                component_value="ALL",
            )
            overview["realized_r_pearson"] = realized_corr["pearson"]
            overview["realized_r_spearman"] = realized_corr["spearman"]
            overview["realized_r_direction"] = correlation_direction(realized_corr["spearman"])
            rows.append(overview)
            for level in COMPONENT_LEVELS[component]:
                rows.append(
                    summarize_rows(
                        [row for row in year_rows if row[field] == level],
                        section="YEAR_COMPONENT_LEVEL",
                        year=year,
                        period_status="PARTIAL" if year == 2026 else "COMPLETE",
                        component=component,
                        component_value=level,
                    )
                )
    return rows


def build_experiment_table(
    experiment_id: str,
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if experiment_id == "EXP-SCORECAL-001":
        return score_profiles(records)
    if experiment_id == "EXP-SCORECAL-002":
        return component_matrix(records, "SETUP")
    if experiment_id == "EXP-SCORECAL-003":
        return component_matrix(records, "MOMENTUM")
    if experiment_id == "EXP-SCORECAL-004":
        return component_matrix(records, "RVOL")
    if experiment_id == "EXP-SCORECAL-005":
        return component_matrix(records, "RS")
    if experiment_id == "EXP-SCORECAL-006":
        return component_matrix(records, "REGIME")
    if experiment_id == "EXP-SCORECAL-007":
        return component_matrix(records, "RR")
    if experiment_id == "EXP-SCORECAL-008":
        return vector_profiles(records)
    if experiment_id == "EXP-SCORECAL-009":
        return score_decomposition(records)
    if experiment_id == "EXP-SCORECAL-010":
        return yearly_component_rows(records)
    raise ValueError(f"Unsupported score-calibration experiment: {experiment_id}")


def execute_score_calibration_experiment(
    definition: ExperimentDefinition,
    records: Sequence[Mapping[str, Any]],
) -> ExperimentExecution:
    table = build_experiment_table(definition.experiment_id, records)
    result = {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "pre_registration_hash": "PENDING_REGISTRY_INJECTION",
        "run_status": "RUNNING",
        "source_opportunities": len(records),
        "admitted_trades": sum(bool(row["is_admitted"]) for row in records),
        "skipped_opportunities": sum(bool(row["is_skipped"]) for row in records),
        "table_row_count": len(table),
        "table_fingerprint": canonical_hash(table),
        "score_or_weight_change_applied": False,
        "threshold_search_performed": False,
        "portfolio_rerun_performed": False,
        "optimizer_or_ml_performed": False,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "performance_scope": PERFORMANCE_SCOPE,
        "gross_before_costs": True,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
    }
    return ExperimentExecution(result=result, trades=table)


def average_ranks(numbers: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(numbers), key=lambda item: item[1])
    ranks = [0.0] * len(numbers)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end + 2) / 2
        for position in range(index, end + 1):
            ranks[ordered[position][0]] = rank
        index = end + 1
    return ranks


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def correlation(
    rows: Sequence[Mapping[str, Any]],
    left_field: str,
    right_field: str,
) -> dict[str, Any]:
    pairs = [
        (float(row[left_field]), float(row[right_field]))
        for row in rows
        if row.get(left_field) is not None and row.get(right_field) is not None
    ]
    left = [item[0] for item in pairs]
    right = [item[1] for item in pairs]
    return {
        "count": len(pairs),
        "pearson": pearson(left, right),
        "spearman": pearson(average_ranks(left), average_ranks(right)),
    }


def correlation_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for population in ("SOURCE", "ADMITTED"):
        selected = population_rows(records, population)
        for left_name, right_name in combinations(COMPONENT_FIELDS, 2):
            result = correlation(selected, COMPONENT_FIELDS[left_name], COMPONENT_FIELDS[right_name])
            rows.append(
                {
                    "section": "COMPONENT_REDUNDANCY",
                    "population": population,
                    "left_metric": left_name,
                    "right_metric": right_name,
                    **result,
                    "sample_size_flag": sample_size_flag(result["count"]),
                    "descriptive_only": True,
                    "significance_tested": False,
                }
            )
        for component, field in COMPONENT_FIELDS.items():
            outcome_fields = ("mfe_r_4", "mae_r_4", "close_return_pct_4")
            if population == "ADMITTED":
                outcome_fields += ("realized_r_multiple",)
            for outcome_field in outcome_fields:
                result = correlation(selected, field, outcome_field)
                rows.append(
                    {
                        "section": "COMPONENT_OUTCOME",
                        "population": population,
                        "left_metric": component,
                        "right_metric": outcome_field,
                        **result,
                        "sample_size_flag": sample_size_flag(result["count"]),
                        "descriptive_only": True,
                        "significance_tested": False,
                    }
                )
    return rows


def correlation_direction(value: float | None) -> str:
    if value is None:
        return "INCONCLUSIVE"
    if value > 0.05:
        return "POSITIVE"
    if value < -0.05:
        return "NEGATIVE"
    return "NEUTRAL"


def discrimination_result(records: Sequence[Mapping[str, Any]], component: str) -> tuple[str, dict[str, Any]]:
    field = COMPONENT_FIELDS[component]
    observed = sorted({int(row[field]) for row in records})
    low_rows = [row for row in records if row[field] == observed[0]]
    high_rows = [row for row in records if row[field] == observed[-1]]
    low = summarize_rows(low_rows)
    high = summarize_rows(high_rows)
    if min(low["sample_size"], high["sample_size"], low["admitted_count"], high["admitted_count"]) < 30:
        return "INCONCLUSIVE", {"low": low, "high": high, "positive_votes": 0, "negative_votes": 0}
    deltas = {
        "mean_mfe_r": decimal(high["mean_mfe_r"]) - decimal(low["mean_mfe_r"]),
        "mean_mae_r": decimal(low["mean_mae_r"]) - decimal(high["mean_mae_r"]),
        "mean_realized_r": decimal(high["mean_realized_r"]) - decimal(low["mean_realized_r"]),
        "positive_trade_rate_pct": decimal(high["positive_trade_rate_pct"]) - decimal(low["positive_trade_rate_pct"]),
        "target_first_pct": decimal(high["target_first_pct"]) - decimal(low["target_first_pct"]),
        "stop_first_pct": decimal(low["stop_first_pct"]) - decimal(high["stop_first_pct"]),
    }
    material = {
        "mean_mfe_r": Decimal("0.05"),
        "mean_mae_r": Decimal("0.05"),
        "mean_realized_r": Decimal("0.05"),
        "positive_trade_rate_pct": Decimal("3"),
        "target_first_pct": Decimal("1"),
        "stop_first_pct": Decimal("3"),
    }
    positive = sum(value >= material[name] for name, value in deltas.items())
    negative = sum(value <= -material[name] for name, value in deltas.items())
    if positive >= 4 and negative == 0:
        classification = "CLEAR_POSITIVE_DISCRIMINATION"
    elif positive >= 3 and positive > negative:
        classification = "WEAK_POSITIVE_DISCRIMINATION"
    elif negative >= 3 and negative > positive:
        classification = "INVERSE"
    elif positive and negative:
        classification = "MIXED"
    else:
        classification = "NO_CLEAR_DISCRIMINATION"
    return classification, {
        "lowest_observed_level": observed[0],
        "highest_observed_level": observed[-1],
        "low": low,
        "high": high,
        "deltas_in_favorable_direction": deltas,
        "positive_votes": positive,
        "negative_votes": negative,
    }


def total_score_monotonicity(profiles: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    scores = [float(row["raw_strategy_score"]) for row in profiles]
    metrics = {
        "mean_mfe_r": 1,
        "mean_mae_r": -1,
        "mean_realized_r": 1,
        "positive_trade_rate_pct": 1,
        "stop_first_pct": -1,
        "target_first_pct": 1,
    }
    associations: dict[str, float | None] = {}
    for field, direction in metrics.items():
        values_for_field = [float(row[field]) for row in profiles]
        raw = pearson(average_ranks(scores), average_ranks(values_for_field))
        associations[field] = raw * direction if raw is not None else None
    if any(row["admitted_count"] < 30 for row in profiles):
        return "INCONCLUSIVE", {"favorable_direction_spearman": associations}
    positive = sum(value is not None and value > 0 for value in associations.values())
    negative = sum(value is not None and value < 0 for value in associations.values())
    material = sum(value is not None and abs(value) >= 0.20 for value in associations.values())
    if positive == 6:
        result = "MONOTONIC_POSITIVE"
    elif positive >= 4:
        result = "MOSTLY_POSITIVE"
    elif negative >= 4 and positive <= 1:
        result = "INVERSE"
    elif material == 0:
        result = "NO_CLEAR_RELATIONSHIP"
    else:
        result = "MIXED"
    return result, {
        "favorable_direction_spearman": associations,
        "positive_direction_count": positive,
        "negative_direction_count": negative,
        "material_association_count": material,
    }


def leave_one_out_dependency(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for component, field in COMPONENT_FIELDS.items():
        dropped = [row for row in records if row["raw_strategy_score"] - row[field] < 80]
        retained = [row for row in records if row["raw_strategy_score"] - row[field] >= 80]
        profile = summarize_rows(dropped, component=component)
        profile.update(
            {
                "source_opportunities": len(records),
                "drop_below_80_count": len(dropped),
                "drop_below_80_pct": percent(Decimal(len(dropped)), Decimal(len(records))),
                "retained_at_or_above_80_count": len(retained),
                "arithmetic_only": True,
                "renormalized": False,
                "portfolio_rerun": False,
            }
        )
        rows.append(profile)
    return rows


def population_component_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        summarize_rows(population_rows(records, population), population=population)
        for population in ("SOURCE", "ENTRY_ELIGIBLE", "ADMITTED", "SKIPPED", "SLOT_SKIPPED")
    ]


def yearly_stability(yearly_rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], list[str]]:
    results: dict[str, str] = {}
    one_year_positive: list[str] = []
    for component in COMPONENT_FIELDS:
        directions = [
            row["realized_r_direction"]
            for row in yearly_rows
            if row["section"] == "YEAR_COMPONENT_OVERVIEW" and row["component"] == component
        ]
        evaluable = [item for item in directions if item != "INCONCLUSIVE"]
        positive = evaluable.count("POSITIVE")
        negative = evaluable.count("NEGATIVE")
        if len(evaluable) < 3:
            result = "INCONCLUSIVE"
        elif positive == len(evaluable):
            result = "CONSISTENT"
        elif negative == len(evaluable):
            result = "INVERSE_ACROSS_PERIODS"
        elif max(positive, negative) >= 4:
            result = "MOSTLY_CONSISTENT"
        else:
            result = "UNSTABLE"
        if positive == 1:
            one_year_positive.append(component)
        results[component] = result
    return results, one_year_positive


def redundancy_result(correlations: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    pairs = [row for row in correlations if row["section"] == "COMPONENT_REDUNDANCY" and row["population"] == "SOURCE" and row["spearman"] is not None]
    if not pairs:
        return "INCONCLUSIVE", {}
    strongest = max(pairs, key=lambda row: abs(float(row["spearman"])))
    value = abs(float(strongest["spearman"]))
    if value >= 0.80:
        result = "HIGH"
    elif value >= 0.60:
        result = "POTENTIAL_DOUBLE_COUNTING"
    elif value >= 0.40:
        result = "MODERATE_ACCEPTABLE"
    else:
        result = "LOW"
    return result, {"strongest_pair": strongest, "maximum_absolute_source_spearman": value}


def score_pair_analysis(records: Sequence[Mapping[str, Any]], left_score: int, right_score: int) -> dict[str, Any]:
    left = summarize_rows([row for row in records if row["raw_strategy_score"] == left_score], raw_strategy_score=left_score)
    right = summarize_rows([row for row in records if row["raw_strategy_score"] == right_score], raw_strategy_score=right_score)
    component_differences = {
        component: decimal(right[f"mean_{field}"]) - decimal(left[f"mean_{field}"])
        for component, field in COMPONENT_FIELDS.items()
    }
    return {
        "left": left,
        "right": right,
        "right_minus_left_component_mean_points": component_differences,
        "right_minus_left_realized_r": decimal(right["mean_realized_r"]) - decimal(left["mean_realized_r"]),
        "right_minus_left_positive_rate_pct": decimal(right["positive_trade_rate_pct"]) - decimal(left["positive_trade_rate_pct"]),
        "right_minus_left_admission_rate_pct": decimal(right["admission_rate_pct"]) - decimal(left["admission_rate_pct"]),
        "descriptive_only": True,
    }


def score_84_85_result(analysis: Mapping[str, Any]) -> tuple[str, list[str]]:
    left = analysis["left"]
    right = analysis["right"]
    if min(int(left["admitted_count"]), int(right["admitted_count"])) < 30:
        return "INCONCLUSIVE", []
    component_difference = sum(abs(decimal(value)) >= Decimal("0.5") for value in analysis["right_minus_left_component_mean_points"].values()) >= 2
    left_years = {year: Decimal(count) / Decimal(left["sample_size"]) * 100 for year, count in left["year_counts"].items()}
    right_years = {year: Decimal(count) / Decimal(right["sample_size"]) * 100 for year, count in right["year_counts"].items()}
    temporal = max(abs(right_years.get(year, Decimal("0")) - left_years.get(year, Decimal("0"))) for year in set(left_years) | set(right_years)) >= 15
    selection = abs(decimal(analysis["right_minus_left_admission_rate_pct"])) >= 10
    reasons = []
    if component_difference:
        reasons.append("COMPONENT_COMPOSITION_DIFFERENCE")
    if temporal:
        reasons.append("TEMPORAL_CONCENTRATION")
    if selection:
        reasons.append("SELECTION_EFFECT")
    if len(reasons) > 1:
        return "MULTIPLE_FACTORS", reasons
    if reasons:
        return reasons[0], reasons
    return "LIKELY_NOISE", []


def build_pilot(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cases: list[tuple[str, str, Callable[[Mapping[str, Any]], bool]]] = [
        ("A", "score 80", lambda row: row["raw_strategy_score"] == 80),
        ("B", "score 81", lambda row: row["raw_strategy_score"] == 81),
        ("C", "score 82", lambda row: row["raw_strategy_score"] == 82),
        ("D", "score 83", lambda row: row["raw_strategy_score"] == 83),
        ("E", "score 84 positive portfolio trade", lambda row: row["raw_strategy_score"] == 84 and row["is_admitted"] and decimal(row["gross_pnl"]) > 0),
        ("F", "score 84 negative portfolio trade", lambda row: row["raw_strategy_score"] == 84 and row["is_admitted"] and decimal(row["gross_pnl"]) < 0),
        ("G", "score 85 positive portfolio trade", lambda row: row["raw_strategy_score"] == 85 and row["is_admitted"] and decimal(row["gross_pnl"]) > 0),
        ("H", "score 85 negative portfolio trade", lambda row: row["raw_strategy_score"] == 85 and row["is_admitted"] and decimal(row["gross_pnl"]) < 0),
        ("I", "strong setup / lowest available RVOL", lambda row: row["setup_points"] == 20 and row["rvol_points"] == 10),
        ("J", "strong momentum / weaker RS", lambda row: row["momentum_points"] == 20 and row["rs_points"] == 11),
        ("K", "high RVOL / lower momentum", lambda row: row["rvol_points"] == 15 and row["momentum_points"] < 20),
        ("L", "3-point R:R component", lambda row: row["rr_points"] == 3),
        ("M", "4-point R:R component", lambda row: row["rr_points"] == 4),
        ("N", "5-point R:R component", lambda row: row["rr_points"] == 5),
    ]
    ordered = sorted(records, key=lambda row: (str(row["decision_date"]), str(row["symbol"])))
    output: list[dict[str, Any]] = []
    for case, scenario, predicate in cases:
        selected = next((row for row in ordered if predicate(row)), None)
        if selected is None:
            raise ValueError(f"No real frozen pilot row found for case {case}: {scenario}")
        components = {field: selected[field] for field in VECTOR_FIELDS}
        arithmetic = sum(components.values())
        output.append(
            {
                "case": case,
                "scenario": scenario,
                "source_type": "REAL_FROZEN_DATA",
                "source_key": selected["source_key"],
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_date": selected["entry_date"],
                **components,
                "component_vector": "|".join(str(components[field]) for field in VECTOR_FIELDS),
                "raw_strategy_score": selected["raw_strategy_score"],
                "arithmetic_sum": arithmetic,
                "is_admitted": selected["is_admitted"],
                "is_slot_skipped": selected["is_slot_skipped"],
                "mfe_r_4": selected["mfe_r_4"],
                "mae_r_4": selected["mae_r_4"],
                "realized_r_multiple": selected["realized_r_multiple"],
                "gross_pnl": selected["gross_pnl"],
                "portfolio_exit_reason": selected["portfolio_exit_reason"],
                "year": int(str(selected["decision_date"])[:4]),
                "passed": arithmetic == selected["raw_strategy_score"],
            }
        )
    return {
        "cases": output,
        "case_count": len(output),
        "real_case_count": sum(row["source_type"] == "REAL_FROZEN_DATA" for row in output),
        "passed": len(output) == 14 and all(row["passed"] for row in output),
        "validated_fields": [
            "score_arithmetic",
            "component_points",
            "source_admitted_population",
            "frozen_outcome",
            "realized_r",
            "exit_state",
            "vector_assignment",
            "yearly_assignment",
        ],
        "availability_note": "The source cohort contains no RVOL 0/6 rows; case I uses the lowest available frozen RVOL level, 10 (GOOD).",
    }


def auxiliary_analyses(
    records: Sequence[Mapping[str, Any]],
    executions: Mapping[str, ExperimentExecution],
    correlations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    profiles = executions["EXP-SCORECAL-001"].trades
    monotonicity, monotonicity_evidence = total_score_monotonicity(profiles)
    component_results: dict[str, str] = {}
    component_evidence: dict[str, Any] = {}
    for component in COMPONENT_FIELDS:
        result, evidence = discrimination_result(records, component)
        component_results[component] = result
        component_evidence[component] = evidence
    leave_out = leave_one_out_dependency(records)
    population_profiles = population_component_profiles(records)
    vectors = executions["EXP-SCORECAL-008"].trades
    yearly = executions["EXP-SCORECAL-010"].trades
    stability, one_year_positive = yearly_stability(yearly)
    redundancy, redundancy_evidence = redundancy_result(correlations)
    pair_84_85 = score_pair_analysis(records, 84, 85)
    pair_80_85 = score_pair_analysis(records, 80, 85)
    pair_result, pair_reasons = score_84_85_result(pair_84_85)
    admitted_score_realized = correlation([row for row in records if row["is_admitted"]], "raw_strategy_score", "realized_r_multiple")
    if monotonicity == "MONOTONIC_POSITIVE" and (admitted_score_realized["spearman"] or 0) > 0:
        total_result = "MONOTONIC_AND_USEFUL"
    elif monotonicity == "MOSTLY_POSITIVE":
        total_result = "PARTIALLY_DISCRIMINATIVE"
    elif monotonicity == "INVERSE":
        total_result = "POORLY_CALIBRATED"
    elif monotonicity == "INCONCLUSIVE":
        total_result = "INCONCLUSIVE"
    else:
        total_result = "MIXED"
    source_vector_count = len(vectors)
    admitted_vector_count = len({vector_key(row) for row in records if row["is_admitted"]})
    return {
        "score_profiles": profiles,
        "population_component_profiles": population_profiles,
        "leave_one_out_dependency": leave_out,
        "unique_source_component_vectors": source_vector_count,
        "unique_admitted_component_vectors": admitted_vector_count,
        "top_20_component_vectors": vectors[:20],
        "total_score_monotonicity": monotonicity,
        "total_score_monotonicity_evidence": monotonicity_evidence,
        "component_results": component_results,
        "component_discrimination_evidence": component_evidence,
        "component_redundancy_result": redundancy,
        "component_redundancy_evidence": redundancy_evidence,
        "yearly_stability": stability,
        "temporal_positive_only_one_year": one_year_positive,
        "score_84_vs_85": pair_84_85,
        "score_80_vs_85": pair_80_85,
        "score_84_85_result": pair_result,
        "score_84_85_contributing_reasons": pair_reasons,
        "total_score_calibration_result": total_result,
        "admitted_total_score_realized_r_correlation": admitted_score_realized,
    }


def append_registry_preserving_previous(
    path: Path,
    original: Mapping[str, Any],
    new_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    previous = [copy.deepcopy(row) for row in original["experiments"] if row.get("experiment_id") not in SCORE_CALIBRATION_EXPERIMENT_IDS]
    if len(previous) != 29:
        raise ValueError(f"Expected 29 previous experiments, found {len(previous)}")
    prior_hashes = {row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"]) for row in previous}
    payload = copy.deepcopy(dict(original))
    payload["experiments"] = previous + [dict(row) for row in new_records]
    payload["command_04"] = {
        "version": SCORE_CALIBRATION_COMMAND_VERSION,
        "experiment_ids": list(SCORE_CALIBRATION_EXPERIMENT_IDS),
        "promotion_allowed": False,
    }
    write_json(path, payload)
    preserved = {
        row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"])
        for row in payload["experiments"]
        if row["experiment_id"] in prior_hashes
    }
    if preserved != prior_hashes or len(payload["experiments"]) != 39:
        raise ValueError("Previous registry hashes changed or combined registry count is not 39")
    return {
        "previous_experiment_count": 29,
        "previous_parameter_and_preregistration_hashes_unchanged": True,
        "combined_registry_count": 39,
    }


def write_outputs(
    *,
    context: ScoreCalibrationContext,
    registry: ScoreCalibrationRegistry,
    executions: Mapping[str, ExperimentExecution],
    summary: Mapping[str, Any],
    preregistration_path: Path,
    original_registry: Mapping[str, Any],
    correlations: Sequence[Mapping[str, Any]],
    pilot: Mapping[str, Any],
) -> tuple[list[Path], dict[str, Any]]:
    command_root = context.data_dir / "research/diagnostics/strategy/v1/score_calibration_command_04"
    report_root = context.data_dir / "reports"
    final_registry_path = command_root / "registry/score_calibration_experiment_registry_v1.json"
    write_json(
        final_registry_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": SCORE_CALIBRATION_COMMAND_VERSION,
            "promotion_allowed": False,
            "experiments": registry.records(),
        },
    )
    paths = [preregistration_path, final_registry_path]
    for experiment_id in SCORE_CALIBRATION_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        run_root = command_root / "runs" / experiment_id
        result_path = run_root / "result.json"
        table_path = run_root / "table.csv.gz"
        write_json(result_path, execution.result)
        write_gzip_csv(table_path, execution.trades)
        paths.extend((result_path, table_path))
    report_mapping = {
        "strategy_diagnostic_v1_score_calibration_totals.csv": "EXP-SCORECAL-001",
        "strategy_diagnostic_v1_score_calibration_setup.csv": "EXP-SCORECAL-002",
        "strategy_diagnostic_v1_score_calibration_momentum.csv": "EXP-SCORECAL-003",
        "strategy_diagnostic_v1_score_calibration_rvol.csv": "EXP-SCORECAL-004",
        "strategy_diagnostic_v1_score_calibration_rs.csv": "EXP-SCORECAL-005",
        "strategy_diagnostic_v1_score_calibration_regime.csv": "EXP-SCORECAL-006",
        "strategy_diagnostic_v1_score_calibration_rr.csv": "EXP-SCORECAL-007",
        "strategy_diagnostic_v1_score_calibration_vectors.csv": "EXP-SCORECAL-008",
        "strategy_diagnostic_v1_score_calibration_score_decomposition.csv": "EXP-SCORECAL-009",
        "strategy_diagnostic_v1_score_calibration_yearly.csv": "EXP-SCORECAL-010",
    }
    for filename, experiment_id in report_mapping.items():
        path = report_root / filename
        write_csv(path, executions[experiment_id].trades)
        paths.append(path)
    correlation_path = report_root / "strategy_diagnostic_v1_score_calibration_correlations.csv"
    pilot_path = report_root / "strategy_diagnostic_v1_score_calibration_pilot.csv"
    write_csv(correlation_path, correlations)
    write_csv(pilot_path, pilot["cases"])
    paths.extend((correlation_path, pilot_path))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    preservation = append_registry_preserving_previous(main_registry_path, original_registry, registry.records())
    paths.append(main_registry_path)
    summary_path = report_root / "strategy_diagnostic_v1_score_calibration_summary.json"
    write_json(summary_path, summary)
    paths.append(summary_path)
    return paths, preservation


def run_score_calibration_diagnostics(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Loading and verifying frozen score, outcome, and portfolio baselines")
    context = load_score_calibration_context(Path(repo_root))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    original_registry = json.loads(main_registry_path.read_text(encoding="utf-8"))
    previous = [row for row in original_registry["experiments"] if row.get("experiment_id") not in SCORE_CALIBRATION_EXPERIMENT_IDS]
    if len(previous) != 29 or any(row.get("status") != "COMPLETE" for row in previous):
        raise ValueError("Command 04 requires 29 immutable completed prior experiment records")
    definitions = build_score_calibration_definitions()
    registry = ScoreCalibrationRegistry(context.baseline_hashes)
    for definition in definitions:
        registry.register(definition)
    preregistration_path = context.data_dir / "research/diagnostics/strategy/v1/score_calibration_command_04/registry/score_calibration_experiment_registry_v1_preregistered.json"
    write_json(
        preregistration_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": SCORE_CALIBRATION_COMMAND_VERSION,
            "written_before_metric_derivation_or_results": True,
            "frozen_score_version": context.score_version,
            "frozen_score_profile": context.score_profile,
            "frozen_score_config_hash": context.score_config_hash,
            "component_levels": COMPONENT_LEVELS,
            "sample_size_rules": SAMPLE_SIZE_RULES,
            "classification_rules": CLASSIFICATION_RULES,
            "promotion_allowed": False,
            "experiments": registry.records(),
        },
    )
    notify(progress, "Pre-registered exactly ten immutable Command 04 experiments")
    records = derive_score_calibration_records(context)
    pilot = build_pilot(records)
    if not pilot["passed"]:
        raise ValueError("Real-data score-calibration pilot failed")
    notify(progress, "Validated fourteen real-data score and component pilot cases")
    executions: dict[str, ExperimentExecution] = {}
    for experiment_id in SCORE_CALIBRATION_EXPERIMENT_IDS:
        registry.mark_ready(experiment_id)
        notify(progress, f"Running {experiment_id} twice with frozen-hash guards")
        execution = registry.run_twice(
            experiment_id,
            lambda definition: execute_score_calibration_experiment(definition, records),
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Experiment failed: {experiment_id}: {registry.state(experiment_id).failure_reason}")
        executions[experiment_id] = execution
    correlations = correlation_rows(records)
    auxiliary = auxiliary_analyses(records, executions, correlations)
    classifications = {
        "TOTAL_SCORE_MONOTONICITY": auxiliary["total_score_monotonicity"],
        "SETUP_COMPONENT_RESULT": auxiliary["component_results"]["SETUP"],
        "MOMENTUM_COMPONENT_RESULT": auxiliary["component_results"]["MOMENTUM"],
        "RVOL_COMPONENT_RESULT": auxiliary["component_results"]["RVOL"],
        "RS_COMPONENT_RESULT": auxiliary["component_results"]["RS"],
        "REGIME_COMPONENT_RESULT": auxiliary["component_results"]["REGIME"],
        "RR_COMPONENT_RESULT": auxiliary["component_results"]["RR"],
        "COMPONENT_REDUNDANCY_RESULT": auxiliary["component_redundancy_result"],
        "TOTAL_SCORE_CALIBRATION_RESULT": auxiliary["total_score_calibration_result"],
        "SCORE_84_85_RESULT": auxiliary["score_84_85_result"],
        "FRAMEWORK_RESULT": "PENDING",
    }
    hashes_after = portfolio_backtest_regression_hashes(context.data_dir)
    mutation_violations = sum(hashes_after[name] != value for name, value in context.baseline_hashes.items())
    failures = [state for state in registry._states.values() if state.status == "FAILED"]
    reproducible = all(row["match"] for row in registry.reproducibility.values())
    population_unchanged = len(records) == 3296 and sum(bool(row["is_admitted"]) for row in records) == 728 and sum(bool(row["is_skipped"]) for row in records) == 2568
    framework_result = "CLEAN" if pilot["passed"] and reproducible and population_unchanged and not failures and mutation_violations == 0 else "METHODOLOGY_FIX_REQUIRED"
    classifications["FRAMEWORK_RESULT"] = framework_result
    hypothesis_supported = classifications["TOTAL_SCORE_CALIBRATION_RESULT"] in {"MIXED", "POORLY_CALIBRATED"} and any(
        value in {"NO_CLEAR_DISCRIMINATION", "MIXED", "INVERSE"}
        for key, value in classifications.items()
        if key.endswith("_COMPONENT_RESULT")
    )
    summary: dict[str, Any] = {
        "phase": "Step 02.13",
        "command": COMMAND,
        "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
        "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
        "command_version": SCORE_CALIBRATION_COMMAND_VERSION,
        "newly_registered_experiment_count": 10,
        "newly_registered_experiment_ids": list(SCORE_CALIBRATION_EXPERIMENT_IDS),
        "combined_registry_expected_count": 39,
        "pre_registration": {
            "written_before_metric_derivation_or_results": True,
            "component_levels_locked": True,
            "classifications_locked": True,
            "path": str(preregistration_path.relative_to(repo_root)),
        },
        "frozen_score": {
            "version": context.score_version,
            "profile": context.score_profile,
            "config_hash": context.score_config_hash,
            "component_levels": COMPONENT_LEVELS,
            "weights": FROZEN_SCORE_WEIGHTS,
            "historically_available_component_weights": COMPONENT_MAX_POINTS,
            "unavailable_historical_components": {"SECTOR": 10, "CATALYST": 5},
            "typical_available_weight": 85,
            "entry_eligible_threshold": 80,
            "high_conviction_threshold": 90,
            "score_rewrite_performed": False,
        },
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": hashes_after,
        },
        "population_integrity": {
            "source_opportunities": len(records),
            "entry_eligible_opportunities": sum(bool(row["entry_eligible"]) for row in records),
            "admitted_trades": sum(bool(row["is_admitted"]) for row in records),
            "skipped_opportunities": sum(bool(row["is_skipped"]) for row in records),
            "slot_skipped_opportunities": sum(bool(row["is_slot_skipped"]) for row in records),
            "unchanged": population_unchanged,
            "ranking_changed": False,
            "portfolio_rerun_performed": False,
        },
        "classification_rules": CLASSIFICATION_RULES,
        "score_profiles": executions["EXP-SCORECAL-001"].trades,
        "results": [executions[item].result for item in SCORE_CALIBRATION_EXPERIMENT_IDS],
        "tables": {item: executions[item].trades for item in SCORE_CALIBRATION_EXPERIMENT_IDS},
        "correlations": correlations,
        "auxiliary_analyses": auxiliary,
        "classifications": classifications,
        "SCORE_CALIBRATION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING": hypothesis_supported,
        "pilot": pilot,
        "reproducibility": registry.reproducibility,
        "all_experiments_reproducible": reproducible,
        "baseline_mutation_violations": mutation_violations,
        "failed_experiment_count": len(failures),
        "promotion_allowed": PROMOTION_ALLOWED,
        "experiments_promoted": 0,
        "automatic_selection_performed": False,
        "score_weight_changed": False,
        "score_threshold_changed": False,
        "optimizer_or_ml_run": False,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "performance_scope": PERFORMANCE_SCOPE,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
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
            "Historical association is descriptive and does not establish causal component value.",
            "Portfolio admission is a non-random subset, so source and admitted results can differ through selection distortion.",
            "Sector and catalyst were historically unavailable and are excluded from component vectors.",
            "Several component levels and vectors are absent or small in the frozen eligible population.",
            "Year-level component variation can be too small for a meaningful realized-R correlation.",
            "Results are historical and gross before transaction costs and slippage.",
        ],
        "runtime_seconds": 0,
        "storage": {},
        "registry_preservation": {},
        "ready_for_review": False,
    }
    notify(progress, "Writing isolated Command 04 artifacts and machine reports")
    paths, preservation = write_outputs(
        context=context,
        registry=registry,
        executions=executions,
        summary=summary,
        preregistration_path=preregistration_path,
        original_registry=original_registry,
        correlations=correlations,
        pilot=pilot,
    )
    summary["registry_preservation"] = preservation
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {
        "artifact_count": len(paths),
        "artifact_size_bytes": sum(path.stat().st_size for path in paths if path.exists()),
        "root": "data/research/diagnostics/strategy/v1/score_calibration_command_04",
    }
    summary["ready_for_review"] = framework_result == "CLEAN" and tests_passed and frontend_build_passed
    write_json(context.data_dir / "reports/strategy_diagnostic_v1_score_calibration_summary.json", summary)
    return summary


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

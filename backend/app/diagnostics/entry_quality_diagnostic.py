from __future__ import annotations

import copy
import csv
import gzip
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    get_current_portfolio_backtest_baseline,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.backtesting.portfolio_engine import load_frozen_opportunities
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
    read_gzip_csv,
    source_key,
    write_csv,
    write_gzip_csv,
    write_json,
)
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset

COMMAND = "Command 03"
ENTRY_QUALITY_COMMAND_VERSION = "STRATEGY_DIAGNOSTIC_ENTRY_QUALITY_V1"
ENTRY_QUALITY_EXPERIMENT_IDS = (
    "EXP-ENTRYQ-001",
    "EXP-ENTRYQ-002",
    "EXP-ENTRYQ-003",
    "EXP-ENTRYQ-004",
    "EXP-ENTRYQ-005",
    "EXP-ENTRYQ-006",
    "EXP-ENTRYQ-007",
    "EXP-ENTRYQ-008",
    "EXP-ENTRYQ-009",
    "EXP-ENTRYQ-010",
)

ATR_EXTENSION_BUCKETS = (
    "LT_0_5_ATR",
    "0_5_TO_LT_1_ATR",
    "1_TO_LT_1_5_ATR",
    "1_5_TO_LT_2_ATR",
    "2_TO_3_ATR",
    "GT_3_ATR",
    "UNAVAILABLE",
)
BREAKOUT_DISTANCE_BUCKETS = (
    "LE_1_PCT",
    "GT_1_TO_2_PCT",
    "GT_2_TO_3_PCT",
    "GT_3_TO_5_PCT",
    "GT_5_TO_8_PCT",
    "GT_8_PCT",
    "UNAVAILABLE",
)
PRIOR_MOVE_BUCKETS = (
    "LE_0_PCT",
    "GT_0_TO_2_PCT",
    "GT_2_TO_4_PCT",
    "GT_4_TO_6_PCT",
    "GT_6_TO_8_PCT",
    "GT_8_PCT",
    "UNAVAILABLE",
)
MOMENTUM_BUCKETS = {
    "return_5d_pct": ("LT_3_PCT", "3_TO_LT_6_PCT", "6_TO_LT_10_PCT", "10_TO_15_PCT", "GT_15_PCT", "UNAVAILABLE"),
    "return_10d_pct": ("LT_5_PCT", "5_TO_LT_10_PCT", "10_TO_LT_15_PCT", "15_TO_25_PCT", "GT_25_PCT", "UNAVAILABLE"),
    "return_20d_pct": ("LT_10_PCT", "10_TO_LT_20_PCT", "20_TO_LT_30_PCT", "30_TO_50_PCT", "GT_50_PCT", "UNAVAILABLE"),
}
MATURITY_CLASSES = ("EARLY", "DEVELOPING", "MATURE", "EXTENDED", "UNAVAILABLE")
GAP_BUCKETS = ("LE_0_PCT", "GT_0_TO_0_5_PCT", "GT_0_5_TO_1_PCT", "GT_1_TO_2_PCT", "GT_2_PCT", "UNAVAILABLE")
GAP_MATURITY_BUCKETS = ("LE_0_PCT", "GT_0_TO_0_5_PCT", "GT_0_5_PCT", "UNAVAILABLE")
PRIOR_CROSS_BUCKETS = ("LE_2_PCT", "GT_2_TO_4_PCT", "GT_4_TO_6_PCT", "GT_6_PCT", "UNAVAILABLE")
RVOL_STATES = ("WEAK", "NORMAL", "GOOD", "STRONG", "EXCEPTIONAL", "UNAVAILABLE")
RS_STATES = ("WEAK", "NEUTRAL", "POSITIVE", "STRONG", "UNAVAILABLE")
SCORES = (80, 81, 82, 83, 84, 85)
CANDIDATE_STAGES = ("EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE")
REALIZED_R_BUCKETS = ("LE_NEG_1R", "NEG_1_TO_NEG_0_25R", "NEG_0_25_TO_POS_0_25R", "POS_0_25_TO_1R", "GT_1R")
MFE_BUCKETS = ("LT_0_5R", "0_5_TO_LT_1R", "1_TO_LT_1_5R", "1_5_TO_LT_2R", "GE_2R")
MAE_BUCKETS = ("LT_0_25R", "0_25_TO_LT_0_5R", "0_5_TO_LT_1R", "1_TO_LT_1_5R", "GE_1_5R")

STRUCTURAL_REFERENCE_HIERARCHY = (
    "SETUP_PRIOR_HIGH_20D_BREAKOUT_OR_RECLAIM_REFERENCE",
    "RISK_V1_1_TECHNICAL_INVALIDATION_ANCHOR",
    "RISK_V1_1_ENTRY_REFERENCE_PRICE",
    "UNAVAILABLE",
)
MATURITY_MAPPING = {
    "EARLY": "5d <3%, 10d <5%, and 20d <10%",
    "EXTENDED": "5d >15%, or 10d >25%, or 20d >50%",
    "MATURE": "otherwise 5d >=10%, or 10d >=15%, or 20d >=30%",
    "DEVELOPING": "all other available combinations",
    "UNAVAILABLE": "one or more required returns unavailable",
}
SAMPLE_SIZE_RULES = {
    "VERY_SMALL": "count < 30",
    "SMALL": "30 <= count <= 99",
    "LIMITED": "100 <= count <= 299",
    "ADEQUATE_FOR_DESCRIPTION": "count >= 300",
}
CLASSIFICATION_RULES = {
    "ENTRY_EXHAUSTION_RESULT": "STRONG with >=4 of 5 preregistered exhaustion comparisons; MATERIAL with >=3; MIXED with 1-2; otherwise NO_CLEAR_EVIDENCE; comparison cohorts under 30 are INCONCLUSIVE.",
    "SCORE_MATURITY_RESULT": "Higher/lower when median Spearman association across extension and 1d/5d/10d/20d returns is >=0.15/<=-0.15 with consistent sign; mixed when any absolute association >=0.10; otherwise no clear relationship.",
    "GAP_MATURITY_RESULT": "POSITIVE_GAP_COMPOUNDS_MATURITY when >=2 of extension, prior move, and maturity-return comparisons are higher for gap >0.5% than gap <=0%; mixed for one; otherwise no clear relationship; cohorts under 30 are inconclusive.",
    "RVOL_EXTENSION_RESULT": "Within STRONG/EXCEPTIONAL RVOL, high extension is weaker/stronger when >=2 of mean MFE, mean realized R, and stop-first rate move consistently; otherwise mixed/no clear; cohorts under 30 are inconclusive.",
    "RS_EXTENSION_RESULT": "Within STRONG RS, high extension is weaker/stronger when >=2 of mean MFE, mean realized R, and stop-first rate move consistently; otherwise mixed/no clear; cohorts under 30 are inconclusive.",
    "CANDIDATE_STAGE_RESULT": "EMERGING_EARLIER_STAGE when >=3 of ATR extension and 5d/10d/20d returns are lower than BOTH_ELIGIBLE; BOTH_MORE_MATURE when reversed; otherwise mixed; cohorts under 30 are inconclusive.",
}


@dataclass(slots=True)
class EntryQualityContext:
    repo_root: Path
    data_dir: Path
    opportunities: list[dict[str, str]]
    baseline_trades: list[dict[str, str]]
    baseline_skipped: list[dict[str, str]]
    setup_rows: dict[str, dict[str, str]]
    risk_rows: dict[str, dict[str, str]]
    baseline_hashes: dict[str, str]


class EntryQualityRegistry:
    def __init__(self, baseline_hashes: Mapping[str, str]) -> None:
        self.baseline_hashes = dict(baseline_hashes)
        self._states: dict[str, ExperimentState] = {}
        self.reproducibility: dict[str, dict[str, Any]] = {}

    def register(self, definition: ExperimentDefinition) -> None:
        if definition.experiment_id not in ENTRY_QUALITY_EXPERIMENT_IDS:
            raise ValueError(f"Unauthorized Command 03 experiment: {definition.experiment_id}")
        if definition.family != "ENTRY_QUALITY_DIAGNOSTIC":
            raise ValueError("Command 03 experiments must use ENTRY_QUALITY_DIAGNOSTIC")
        if definition.experiment_id in self._states:
            raise ValueError(f"Experiment ID already registered: {definition.experiment_id}")
        if definition.eligible_for_promotion or not definition.diagnostic_only:
            raise ValueError("Entry-quality experiments cannot be promotion eligible")
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
                    raise ValueError("Frozen baseline hash mismatch before diagnostic")
                execution = runner(state.definition)
                after = dict(hash_reader())
                unchanged = before == after == self.baseline_hashes
                guards.append({"run_number": run_number, "before": before, "after": after, "unchanged": unchanged})
                if not unchanged:
                    raise ValueError("Frozen baseline hash mutation detected")
                runs.append(execution)
            fingerprints = [item.canonical_fingerprint() for item in runs]
            if fingerprints[0] != fingerprints[1]:
                raise ValueError("Repeated canonical entry-quality outputs differ")
            execution = runs[0]
            record = entry_quality_definition_record(state.definition, self.baseline_hashes)
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
                **entry_quality_definition_record(
                    self._states[item].definition,
                    self.baseline_hashes,
                    status=self._states[item].status,
                ),
                "result_fingerprint": self._states[item].result_fingerprint,
                "failure_reason": self._states[item].failure_reason,
            }
            for item in ENTRY_QUALITY_EXPERIMENT_IDS
            if item in self._states
        ]


def build_entry_quality_definitions(
    registered_at: str | None = None,
) -> tuple[ExperimentDefinition, ...]:
    timestamp = registered_at or datetime.now(timezone.utc).isoformat()
    locked = {
        "source_cohort": "FROZEN_PRIMARY_MECHANICALLY_VALID_OPPORTUNITIES",
        "portfolio_admissions": "FROZEN_PORTFOLIO_BACKTEST_V1",
        "no_filtering": True,
        "no_reranking": True,
        "structural_reference_hierarchy": STRUCTURAL_REFERENCE_HIERARCHY,
        "sample_size_rules": SAMPLE_SIZE_RULES,
        "classification_rules_hash": canonical_hash(CLASSIFICATION_RULES),
    }
    fields = (
        "entry_extension_atr",
        "entry_extension_pct",
        "prior_day_return_pct",
        "return_5d_pct",
        "return_10d_pct",
        "return_20d_pct",
        "relative_volume_20d",
        "benchmark_rs_context",
        "effective_reward_risk",
        "mfe_r_4",
        "mae_r_4",
        "first_touch_outcome",
        "realized_r_multiple",
    )
    definitions = (
        _definition(timestamp, "EXP-ENTRYQ-001", "BASELINE_ENTRY_QUALITY_PROFILE", "Profile causal entry quality for every frozen primary opportunity and admitted trade.", {**locked, "profile_metrics": fields}, fields),
        _definition(timestamp, "EXP-ENTRYQ-002", "ATR_EXTENSION_BUCKETS", "Describe outcomes across fixed ATR-normalized extension buckets.", {**locked, "buckets": ATR_EXTENSION_BUCKETS}, fields),
        _definition(timestamp, "EXP-ENTRYQ-003", "BREAKOUT_DISTANCE_BUCKETS", "Describe outcomes across fixed entry-to-structure percent-distance buckets.", {**locked, "buckets": BREAKOUT_DISTANCE_BUCKETS, "unavailable_reported": True}, fields),
        _definition(timestamp, "EXP-ENTRYQ-004", "PRIOR_DAY_MOVE_BUCKETS", "Describe outcomes across fixed causal decision-day return buckets.", {**locked, "buckets": PRIOR_MOVE_BUCKETS}, fields),
        _definition(timestamp, "EXP-ENTRYQ-005", "MULTI_DAY_MOMENTUM_MATURITY", "Describe 5d, 10d, and 20d return bands and a non-scoring maturity class.", {**locked, "momentum_buckets": MOMENTUM_BUCKETS, "maturity_mapping": MATURITY_MAPPING}, fields),
        _definition(timestamp, "EXP-ENTRYQ-006", "GAP_X_PRIOR_MOVE_INTERACTION", "Cross fixed next-open gap and causal prior-move buckets, plus maturity by gap.", {**locked, "gap_buckets": GAP_BUCKETS, "prior_move_buckets": PRIOR_CROSS_BUCKETS, "maturity_gap_buckets": GAP_MATURITY_BUCKETS}, fields),
        _definition(timestamp, "EXP-ENTRYQ-007", "RVOL_X_EXTENSION_INTERACTION", "Cross the upstream RVOL strength state with fixed ATR extension.", {**locked, "rvol_states": RVOL_STATES, "atr_buckets": ATR_EXTENSION_BUCKETS}, fields),
        _definition(timestamp, "EXP-ENTRYQ-008", "RS_X_EXTENSION_INTERACTION", "Cross the upstream benchmark-relative-strength state with fixed ATR extension.", {**locked, "rs_states": RS_STATES, "atr_buckets": ATR_EXTENSION_BUCKETS}, fields),
        _definition(timestamp, "EXP-ENTRYQ-009", "SCORE_X_EXTENSION_INTERACTION", "Cross frozen raw scores 80–85 with fixed ATR extension.", {**locked, "scores": SCORES, "atr_buckets": ATR_EXTENSION_BUCKETS, "high_extension_threshold_atr": "1.5"}, fields),
        _definition(timestamp, "EXP-ENTRYQ-010", "CANDIDATE_STAGE_X_EXTENSION", "Compare frozen candidate stages across extension and momentum maturity.", {**locked, "candidate_stages": CANDIDATE_STAGES, "atr_buckets": ATR_EXTENSION_BUCKETS}, fields),
    )
    if tuple(row.experiment_id for row in definitions) != ENTRY_QUALITY_EXPERIMENT_IDS:
        raise ValueError("Command 03 experiment definitions differ from the exact allowlist")
    return definitions


def _definition(
    timestamp: str,
    experiment_id: str,
    name: str,
    description: str,
    parameters: Mapping[str, Any],
    fields: tuple[str, ...],
) -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=experiment_id,
        family="ENTRY_QUALITY_DIAGNOSTIC",
        name=name,
        description=description,
        hypothesis="Technically valid Strategy V1 entries may occur after material momentum extension or maturity.",
        parameters=tuple(parameters.items()),
        outcome_fields_used_for_evaluation=fields,
        changes_strategy_semantics=False,
        changes_portfolio_mechanics=False,
        registered_at=timestamp,
    )


def calculate_entry_quality_pre_registration_hash(
    definition: ExperimentDefinition, baseline_hashes: Mapping[str, str]
) -> str:
    return canonical_hash(
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": ENTRY_QUALITY_COMMAND_VERSION,
            "experiment": {
                "id": definition.experiment_id,
                "family": definition.family,
                "name": definition.name,
                "description": definition.description,
                "hypothesis": definition.hypothesis,
                "parameters": definition.parameter_map,
                "fields": definition.outcome_fields_used_for_evaluation,
            },
            "baseline_dependency": BASELINE_DEPENDENCY,
            "baseline_hashes": dict(sorted(baseline_hashes.items())),
            "classification_rules": CLASSIFICATION_RULES,
            "promotion_allowed": False,
        }
    )


def entry_quality_definition_record(
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
        "pre_registration_hash": calculate_entry_quality_pre_registration_hash(definition, baseline_hashes),
        "parameters_locked_before_run": True,
        "outcome_fields_used_for_evaluation": list(definition.outcome_fields_used_for_evaluation),
        "changes_strategy_semantics": False,
        "changes_portfolio_mechanics": False,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "pre_registered": True,
        "registered_at": definition.registered_at,
        "status": status or definition.status,
    }


def load_entry_quality_context(repo_root: Path) -> EntryQualityContext:
    data_dir = Path(repo_root) / "data"
    verify_current_portfolio_backtest_baseline(data_dir)
    hashes = portfolio_backtest_regression_hashes(data_dir)
    if not all(portfolio_backtest_regression_hash_checks(hashes).values()):
        raise ValueError("Frozen baseline-chain hash verification failed")
    opportunities, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    baseline = get_current_portfolio_backtest_baseline(data_dir)
    trades = read_gzip_csv(baseline.trades_dataset_path)
    skipped = read_gzip_csv(baseline.skipped_dataset_path)
    wanted = {source_key(row) for row in opportunities}
    setup_path = data_dir / "research/setups/daily/v1/daily_setup_evaluations_v1.csv.gz"
    risk_path = data_dir / "research/risk_structures/daily/v1_1/risk_structures_v1_1.csv.gz"
    setup_rows = read_selected_rows(setup_path, wanted)
    risk_rows = read_selected_rows(risk_path, wanted)
    missing_setup = wanted - set(setup_rows)
    missing_risk = wanted - set(risk_rows)
    if missing_setup or missing_risk:
        raise ValueError(f"Missing frozen upstream rows: setup={len(missing_setup)}, risk={len(missing_risk)}")
    return EntryQualityContext(
        repo_root=Path(repo_root),
        data_dir=data_dir,
        opportunities=opportunities,
        baseline_trades=trades,
        baseline_skipped=skipped,
        setup_rows=setup_rows,
        risk_rows=risk_rows,
        baseline_hashes=hashes,
    )


def read_selected_rows(path: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            key = f"{row.get('trading_date', '')}|{row.get('symbol', '')}"
            if key in wanted:
                selected[key] = row
    return selected


def optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else Decimal(str(value))


def percent_return(value: Any) -> Decimal | None:
    number = optional_decimal(value)
    return number * Decimal("100") if number is not None else None


def select_structural_reference(
    setup: Mapping[str, Any], risk: Mapping[str, Any]
) -> tuple[Decimal | None, str]:
    prior_high = optional_decimal(setup.get("prior_high_20d"))
    if prior_high is not None and prior_high > 0:
        return prior_high, STRUCTURAL_REFERENCE_HIERARCHY[0]
    invalidation = optional_decimal(risk.get("technical_invalidation_level"))
    if invalidation is not None and invalidation > 0:
        return invalidation, STRUCTURAL_REFERENCE_HIERARCHY[1]
    entry_reference = optional_decimal(risk.get("entry_reference_price"))
    if entry_reference is not None and entry_reference > 0:
        return entry_reference, STRUCTURAL_REFERENCE_HIERARCHY[2]
    return None, STRUCTURAL_REFERENCE_HIERARCHY[3]


def calculate_extension(
    entry: Decimal | None, reference: Decimal | None, atr: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    if entry is None or reference is None or reference <= 0:
        return None, None
    extension_pct = (entry / reference - Decimal("1")) * Decimal("100")
    extension_atr = (entry - reference) / atr if atr is not None and atr > 0 else None
    return extension_pct, extension_atr


def derive_entry_quality_records(context: EntryQualityContext) -> list[dict[str, Any]]:
    trade_map = {row["source_key"]: row for row in context.baseline_trades}
    skip_map = {row["source_key"]: row for row in context.baseline_skipped}
    records: list[dict[str, Any]] = []
    for outcome in context.opportunities:
        key = source_key(outcome)
        setup = context.setup_rows[key]
        risk = context.risk_rows[key]
        trade = trade_map.get(key)
        skipped = skip_map.get(key)
        entry = optional_decimal(outcome.get("hypothetical_entry_price"))
        reference, basis = select_structural_reference(setup, risk)
        atr = optional_decimal(risk.get("atr_14"))
        extension_pct, extension_atr = calculate_extension(entry, reference, atr)
        breakout_distance = extension_pct if basis == STRUCTURAL_REFERENCE_HIERARCHY[0] else None
        stop = optional_decimal(outcome.get("stop_price"))
        target = optional_decimal(outcome.get("target_price"))
        risk_per_share = optional_decimal(outcome.get("effective_risk_per_share"))
        stop_distance_pct = (
            (entry - stop) / entry * Decimal("100")
            if entry is not None and stop is not None and entry > 0
            else None
        )
        stop_distance_atr = (
            (entry - stop) / atr
            if entry is not None and stop is not None and atr is not None and atr > 0
            else None
        )
        target_distance_pct = (
            (target - entry) / entry * Decimal("100")
            if entry is not None and target is not None and entry > 0
            else None
        )
        target_distance_r = (
            (target - entry) / risk_per_share
            if entry is not None and target is not None and risk_per_share is not None and risk_per_share > 0
            else None
        )
        returns = {
            "prior_day_return_pct": percent_return(setup.get("return_1d")),
            "return_3d_pct": percent_return(setup.get("return_3d")),
            "return_5d_pct": percent_return(setup.get("return_5d")),
            "return_10d_pct": percent_return(setup.get("return_10d")),
            "return_20d_pct": percent_return(setup.get("return_20d")),
        }
        records.append(
            {
                "source_key": key,
                "symbol": outcome["symbol"],
                "decision_date": outcome["decision_date"],
                "entry_date": outcome["next_session_date"],
                "is_admitted": trade is not None,
                "is_skipped": skipped is not None,
                "skip_reason": skipped.get("skip_reason", "") if skipped else "",
                "is_slot_skipped": bool(skipped and skipped.get("skip_reason") == "SKIP_MAX_POSITIONS"),
                "structural_reference": reference,
                "structural_reference_basis": basis,
                "atr_14": atr,
                "entry_price": entry,
                "entry_extension_pct": extension_pct,
                "entry_extension_atr": extension_atr,
                "breakout_distance_pct": breakout_distance,
                "stop_distance_pct": stop_distance_pct,
                "stop_distance_atr": stop_distance_atr,
                "target_distance_pct": target_distance_pct,
                "target_distance_r": target_distance_r,
                **returns,
                "up_days_ratio_5": optional_decimal(setup.get("up_days_ratio_5")),
                "up_days_ratio_10": optional_decimal(setup.get("up_days_ratio_10")),
                "up_days_ratio_20": optional_decimal(setup.get("up_days_ratio_20")),
                "gap_pct": optional_decimal(outcome.get("gap_from_t_close_pct")),
                "relative_volume_20d": optional_decimal(setup.get("relative_volume_20d")),
                "rs_relative_return_5d_pct": percent_return(setup.get("relative_return_5d_vs_nifty500")),
                "rs_relative_return_20d_pct": percent_return(setup.get("relative_return_20d_vs_nifty500")),
                "rvol_state": normalize_state(setup.get("volume_confirmation"), RVOL_STATES),
                "benchmark_rs_context": normalize_state(setup.get("benchmark_rs_context"), RS_STATES),
                "setup_quality": outcome.get("setup_quality"),
                "candidate_category": outcome.get("candidate_category"),
                "raw_strategy_score": int(decimal(outcome.get("raw_strategy_score"))),
                "effective_reward_risk": optional_decimal(outcome.get("effective_reward_risk")),
                "mfe_r_4": optional_decimal(outcome.get("mfe_r_4")),
                "mae_r_4": optional_decimal(outcome.get("mae_r_4")),
                "first_touch_outcome": outcome.get("first_touch_outcome"),
                "regime_state": outcome.get("regime_state"),
                "maturity_class": maturity_class(
                    returns["return_5d_pct"], returns["return_10d_pct"], returns["return_20d_pct"]
                ),
                "realized_r_multiple": optional_decimal(trade.get("realized_r_multiple")) if trade else None,
                "gross_pnl": optional_decimal(trade.get("gross_pnl")) if trade else None,
                "portfolio_exit_reason": trade.get("exit_reason") if trade else None,
            }
        )
    source_keys = {row["source_key"] for row in records}
    admitted_keys = {row["source_key"] for row in records if row["is_admitted"]}
    skipped_keys = {row["source_key"] for row in records if row["is_skipped"]}
    if len(records) != 3296 or len(admitted_keys) != 728 or len(skipped_keys) != 2568:
        raise ValueError("Entry-quality derivation changed the frozen opportunity/admission population")
    if admitted_keys | skipped_keys != source_keys or admitted_keys & skipped_keys:
        raise ValueError("Frozen admission and skip populations do not partition opportunities")
    return records


def normalize_state(value: Any, allowed: Sequence[str]) -> str:
    state = str(value or "UNAVAILABLE").upper()
    return state if state in allowed else "UNAVAILABLE"


def maturity_class(
    return_5d_pct: Decimal | None,
    return_10d_pct: Decimal | None,
    return_20d_pct: Decimal | None,
) -> str:
    if None in {return_5d_pct, return_10d_pct, return_20d_pct}:
        return "UNAVAILABLE"
    assert return_5d_pct is not None and return_10d_pct is not None and return_20d_pct is not None
    if return_5d_pct > 15 or return_10d_pct > 25 or return_20d_pct > 50:
        return "EXTENDED"
    if return_5d_pct >= 10 or return_10d_pct >= 15 or return_20d_pct >= 30:
        return "MATURE"
    if return_5d_pct < 3 and return_10d_pct < 5 and return_20d_pct < 10:
        return "EARLY"
    return "DEVELOPING"


def atr_extension_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value < Decimal("0.5"):
        return "LT_0_5_ATR"
    if value < 1:
        return "0_5_TO_LT_1_ATR"
    if value < Decimal("1.5"):
        return "1_TO_LT_1_5_ATR"
    if value < 2:
        return "1_5_TO_LT_2_ATR"
    if value <= 3:
        return "2_TO_3_ATR"
    return "GT_3_ATR"


def breakout_distance_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 1:
        return "LE_1_PCT"
    if value <= 2:
        return "GT_1_TO_2_PCT"
    if value <= 3:
        return "GT_2_TO_3_PCT"
    if value <= 5:
        return "GT_3_TO_5_PCT"
    if value <= 8:
        return "GT_5_TO_8_PCT"
    return "GT_8_PCT"


def prior_move_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 0:
        return "LE_0_PCT"
    if value <= 2:
        return "GT_0_TO_2_PCT"
    if value <= 4:
        return "GT_2_TO_4_PCT"
    if value <= 6:
        return "GT_4_TO_6_PCT"
    if value <= 8:
        return "GT_6_TO_8_PCT"
    return "GT_8_PCT"


def momentum_bucket(field: str, value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    thresholds = {
        "return_5d_pct": (3, 6, 10, 15),
        "return_10d_pct": (5, 10, 15, 25),
        "return_20d_pct": (10, 20, 30, 50),
    }[field]
    labels = MOMENTUM_BUCKETS[field]
    if value < thresholds[0]:
        return labels[0]
    if value < thresholds[1]:
        return labels[1]
    if value < thresholds[2]:
        return labels[2]
    if value <= thresholds[3]:
        return labels[3]
    return labels[4]


def gap_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 0:
        return "LE_0_PCT"
    if value <= Decimal("0.5"):
        return "GT_0_TO_0_5_PCT"
    if value <= 1:
        return "GT_0_5_TO_1_PCT"
    if value <= 2:
        return "GT_1_TO_2_PCT"
    return "GT_2_PCT"


def gap_maturity_bucket(value: Decimal | None) -> str:
    detailed = gap_bucket(value)
    if detailed == "LE_0_PCT":
        return detailed
    if detailed == "GT_0_TO_0_5_PCT":
        return detailed
    if detailed == "UNAVAILABLE":
        return detailed
    return "GT_0_5_PCT"


def prior_cross_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 2:
        return "LE_2_PCT"
    if value <= 4:
        return "GT_2_TO_4_PCT"
    if value <= 6:
        return "GT_4_TO_6_PCT"
    return "GT_6_PCT"


def realized_r_bucket(value: Decimal) -> str:
    if value <= -1:
        return "LE_NEG_1R"
    if value < Decimal("-0.25"):
        return "NEG_1_TO_NEG_0_25R"
    if value <= Decimal("0.25"):
        return "NEG_0_25_TO_POS_0_25R"
    if value <= 1:
        return "POS_0_25_TO_1R"
    return "GT_1R"


def mfe_bucket(value: Decimal) -> str:
    if value < Decimal("0.5"):
        return "LT_0_5R"
    if value < 1:
        return "0_5_TO_LT_1R"
    if value < Decimal("1.5"):
        return "1_TO_LT_1_5R"
    if value < 2:
        return "1_5_TO_LT_2R"
    return "GE_2R"


def mae_bucket(value: Decimal) -> str:
    if value < Decimal("0.25"):
        return "LT_0_25R"
    if value < Decimal("0.5"):
        return "0_25_TO_LT_0_5R"
    if value < 1:
        return "0_5_TO_LT_1R"
    if value < Decimal("1.5"):
        return "1_TO_LT_1_5R"
    return "GE_1_5R"


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


def metric_stats(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    selected = values(rows, field)
    return {
        "available_count": len(selected),
        "mean": mean(selected),
        "median": median(selected),
        "min": min(selected) if selected else None,
        "max": max(selected) if selected else None,
    }


def summarize_group(rows: Sequence[Mapping[str, Any]], **labels: Any) -> dict[str, Any]:
    admitted = [row for row in rows if row["is_admitted"]]
    first_touch = Counter(str(row["first_touch_outcome"]) for row in rows)
    exits = Counter(str(row["portfolio_exit_reason"]) for row in admitted)
    categorical_counts = {
        field: dict(sorted(Counter(str(row.get(field) or "UNAVAILABLE") for row in rows).items()))
        for field in (
            "rvol_state",
            "benchmark_rs_context",
            "setup_quality",
            "candidate_category",
            "maturity_class",
        )
    }
    realized = values(admitted, "realized_r_multiple")
    pnl = values(admitted, "gross_pnl")
    up_days_5 = values(rows, "up_days_ratio_5")
    up_days_10 = values(rows, "up_days_ratio_10")
    up_days_20 = values(rows, "up_days_ratio_20")
    target_first = sum("TARGET_FIRST" in key for key in first_touch for _ in range(first_touch[key]))
    stop_first = sum("STOP_FIRST" in key for key in first_touch for _ in range(first_touch[key]))
    neither = len(rows) - target_first - stop_first
    return {
        **labels,
        "source_opportunities": len(rows),
        "sample_size_flag": sample_size_flag(len(rows)),
        "admitted_trades": len(admitted),
        "admission_rate_pct": percent(Decimal(len(admitted)), Decimal(len(rows))),
        "slot_skipped_opportunities": sum(bool(row["is_slot_skipped"]) for row in rows),
        "mean_effective_reward_risk": mean(values(rows, "effective_reward_risk")),
        "median_effective_reward_risk": median(values(rows, "effective_reward_risk")),
        "mean_mfe_r": mean(values(rows, "mfe_r_4")),
        "median_mfe_r": median(values(rows, "mfe_r_4")),
        "mean_mae_r": mean(values(rows, "mae_r_4")),
        "median_mae_r": median(values(rows, "mae_r_4")),
        "target_first_count": target_first,
        "target_first_pct": percent(Decimal(target_first), Decimal(len(rows))),
        "stop_first_count": stop_first,
        "stop_first_pct": percent(Decimal(stop_first), Decimal(len(rows))),
        "neither_count": neither,
        "neither_pct": percent(Decimal(neither), Decimal(len(rows))),
        "mean_realized_r": mean(realized),
        "median_realized_r": median(realized),
        "portfolio_gross_pnl": sum(pnl, Decimal("0")),
        "target_exits": exits["TARGET_EXIT"],
        "stop_exits": exits["STOP_EXIT"],
        "time_exits": exits["TIME_EXIT"],
        "mean_entry_extension_atr": mean(values(rows, "entry_extension_atr")),
        "median_entry_extension_atr": median(values(rows, "entry_extension_atr")),
        "mean_entry_extension_pct": mean(values(rows, "entry_extension_pct")),
        "median_entry_extension_pct": median(values(rows, "entry_extension_pct")),
        "mean_breakout_distance_pct": mean(values(rows, "breakout_distance_pct")),
        "median_breakout_distance_pct": median(values(rows, "breakout_distance_pct")),
        "mean_gap_pct": mean(values(rows, "gap_pct")),
        "median_gap_pct": median(values(rows, "gap_pct")),
        "mean_stop_distance_pct": mean(values(rows, "stop_distance_pct")),
        "median_stop_distance_pct": median(values(rows, "stop_distance_pct")),
        "mean_stop_distance_atr": mean(values(rows, "stop_distance_atr")),
        "median_stop_distance_atr": median(values(rows, "stop_distance_atr")),
        "mean_prior_day_return_pct": mean(values(rows, "prior_day_return_pct")),
        "median_prior_day_return_pct": median(values(rows, "prior_day_return_pct")),
        "mean_return_3d_pct": mean(values(rows, "return_3d_pct")),
        "median_return_3d_pct": median(values(rows, "return_3d_pct")),
        "mean_return_5d_pct": mean(values(rows, "return_5d_pct")),
        "median_return_5d_pct": median(values(rows, "return_5d_pct")),
        "mean_return_10d_pct": mean(values(rows, "return_10d_pct")),
        "median_return_10d_pct": median(values(rows, "return_10d_pct")),
        "mean_return_20d_pct": mean(values(rows, "return_20d_pct")),
        "median_return_20d_pct": median(values(rows, "return_20d_pct")),
        "up_days_ratio_5_available_count": len(up_days_5),
        "mean_up_days_ratio_5": mean(up_days_5) if up_days_5 else None,
        "median_up_days_ratio_5": median(up_days_5) if up_days_5 else None,
        "up_days_ratio_10_available_count": len(up_days_10),
        "mean_up_days_ratio_10": mean(up_days_10) if up_days_10 else None,
        "median_up_days_ratio_10": median(up_days_10) if up_days_10 else None,
        "up_days_ratio_20_available_count": len(up_days_20),
        "mean_up_days_ratio_20": mean(up_days_20) if up_days_20 else None,
        "median_up_days_ratio_20": median(up_days_20) if up_days_20 else None,
        "mean_relative_volume_20d": mean(values(rows, "relative_volume_20d")),
        "median_relative_volume_20d": median(values(rows, "relative_volume_20d")),
        "mean_rs_relative_return_5d_pct": mean(values(rows, "rs_relative_return_5d_pct")),
        "median_rs_relative_return_5d_pct": median(values(rows, "rs_relative_return_5d_pct")),
        "mean_rs_relative_return_20d_pct": mean(values(rows, "rs_relative_return_20d_pct")),
        "median_rs_relative_return_20d_pct": median(values(rows, "rs_relative_return_20d_pct")),
        "mean_raw_strategy_score": mean(values(rows, "raw_strategy_score")),
        "median_raw_strategy_score": median(values(rows, "raw_strategy_score")),
        "rvol_state_counts": categorical_counts["rvol_state"],
        "rs_state_counts": categorical_counts["benchmark_rs_context"],
        "setup_quality_counts": categorical_counts["setup_quality"],
        "candidate_category_counts": categorical_counts["candidate_category"],
        "maturity_class_counts": categorical_counts["maturity_class"],
        "mean_target_distance_pct": mean(values(rows, "target_distance_pct")),
        "median_target_distance_pct": median(values(rows, "target_distance_pct")),
        "mean_target_distance_r": mean(values(rows, "target_distance_r")),
        "median_target_distance_r": median(values(rows, "target_distance_r")),
    }


def grouped_rows(
    records: Sequence[Mapping[str, Any]],
    labels: Sequence[Any],
    classifier: Callable[[Mapping[str, Any]], Any],
    label_name: str,
    *,
    section: str | None = None,
) -> list[dict[str, Any]]:
    return [
        summarize_group(
            [row for row in records if classifier(row) == label],
            **({"section": section} if section else {}),
            **{label_name: label},
        )
        for label in labels
    ]


def cross_rows(
    records: Sequence[Mapping[str, Any]],
    left_labels: Sequence[Any],
    right_labels: Sequence[Any],
    left_classifier: Callable[[Mapping[str, Any]], Any],
    right_classifier: Callable[[Mapping[str, Any]], Any],
    left_name: str,
    right_name: str,
    *,
    section: str | None = None,
) -> list[dict[str, Any]]:
    return [
        summarize_group(
            [row for row in records if left_classifier(row) == left and right_classifier(row) == right],
            **({"section": section} if section else {}),
            **{left_name: left, right_name: right},
        )
        for left in left_labels
        for right in right_labels
    ]


def build_experiment_table(
    experiment_id: str, records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if experiment_id == "EXP-ENTRYQ-001":
        return [
            summarize_group(
                [row for row in records if population_predicate(row, population)],
                population=population,
            )
            for population in ("SOURCE", "ADMITTED", "SKIPPED", "SLOT_SKIPPED")
        ]
    if experiment_id == "EXP-ENTRYQ-002":
        return grouped_rows(records, ATR_EXTENSION_BUCKETS, lambda row: atr_extension_bucket(row["entry_extension_atr"]), "atr_extension_bucket")
    if experiment_id == "EXP-ENTRYQ-003":
        return grouped_rows(records, BREAKOUT_DISTANCE_BUCKETS, lambda row: breakout_distance_bucket(row["breakout_distance_pct"]), "breakout_distance_bucket")
    if experiment_id == "EXP-ENTRYQ-004":
        return grouped_rows(records, PRIOR_MOVE_BUCKETS, lambda row: prior_move_bucket(row["prior_day_return_pct"]), "prior_move_bucket")
    if experiment_id == "EXP-ENTRYQ-005":
        rows: list[dict[str, Any]] = []
        for field, labels in MOMENTUM_BUCKETS.items():
            rows.extend(grouped_rows(records, labels, lambda row, field=field: momentum_bucket(field, row[field]), "momentum_bucket", section=field.upper()))
        rows.extend(grouped_rows(records, MATURITY_CLASSES, lambda row: row["maturity_class"], "maturity_class", section="MATURITY_CLASS"))
        return rows
    if experiment_id == "EXP-ENTRYQ-006":
        rows = cross_rows(records, GAP_BUCKETS, PRIOR_CROSS_BUCKETS, lambda row: gap_bucket(row["gap_pct"]), lambda row: prior_cross_bucket(row["prior_day_return_pct"]), "gap_bucket", "prior_move_bucket", section="GAP_X_PRIOR_MOVE")
        rows.extend(cross_rows(records, MATURITY_CLASSES, GAP_MATURITY_BUCKETS, lambda row: row["maturity_class"], lambda row: gap_maturity_bucket(row["gap_pct"]), "maturity_class", "gap_bucket", section="MATURITY_X_GAP"))
        return rows
    if experiment_id == "EXP-ENTRYQ-007":
        return cross_rows(records, RVOL_STATES, ATR_EXTENSION_BUCKETS, lambda row: row["rvol_state"], lambda row: atr_extension_bucket(row["entry_extension_atr"]), "rvol_state", "atr_extension_bucket")
    if experiment_id == "EXP-ENTRYQ-008":
        return cross_rows(records, RS_STATES, ATR_EXTENSION_BUCKETS, lambda row: row["benchmark_rs_context"], lambda row: atr_extension_bucket(row["entry_extension_atr"]), "rs_state", "atr_extension_bucket")
    if experiment_id == "EXP-ENTRYQ-009":
        return cross_rows(records, SCORES, ATR_EXTENSION_BUCKETS, lambda row: row["raw_strategy_score"], lambda row: atr_extension_bucket(row["entry_extension_atr"]), "raw_strategy_score", "atr_extension_bucket")
    if experiment_id == "EXP-ENTRYQ-010":
        aggregate = grouped_rows(records, CANDIDATE_STAGES, lambda row: row["candidate_category"], "candidate_stage", section="STAGE_PROFILE")
        aggregate.extend(cross_rows(records, CANDIDATE_STAGES, ATR_EXTENSION_BUCKETS, lambda row: row["candidate_category"], lambda row: atr_extension_bucket(row["entry_extension_atr"]), "candidate_stage", "atr_extension_bucket", section="STAGE_X_EXTENSION"))
        return aggregate
    raise ValueError(f"Unsupported entry-quality experiment: {experiment_id}")


def population_predicate(row: Mapping[str, Any], population: str) -> bool:
    if population == "SOURCE":
        return True
    if population == "ADMITTED":
        return bool(row["is_admitted"])
    if population == "SKIPPED":
        return bool(row["is_skipped"])
    if population == "SLOT_SKIPPED":
        return bool(row["is_slot_skipped"])
    raise ValueError(population)


def execute_entry_quality_experiment(
    definition: ExperimentDefinition, records: Sequence[Mapping[str, Any]]
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
        "admission_or_ranking_change_applied": False,
        "portfolio_equity_curve_generated": False,
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
    if len(left) < 3 or len(set(left)) < 2 or len(set(right)) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else None


def correlation_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "entry_extension_atr",
        "prior_day_return_pct",
        "return_5d_pct",
        "return_10d_pct",
        "return_20d_pct",
        "target_distance_pct",
        "target_distance_r",
        "effective_reward_risk",
    )
    results = []
    for population in ("SOURCE", "ADMITTED"):
        population_rows = [row for row in records if population == "SOURCE" or row["is_admitted"]]
        for field in fields:
            pairs = [
                (float(row["raw_strategy_score"]), float(row[field]))
                for row in population_rows
                if row.get(field) is not None
            ]
            left = [row[0] for row in pairs]
            right = [row[1] for row in pairs]
            results.append(
                {
                    "population": population,
                    "left_metric": "raw_strategy_score",
                    "right_metric": field,
                    "count": len(pairs),
                    "sample_size_flag": sample_size_flag(len(pairs)),
                    "pearson": pearson(left, right),
                    "spearman": pearson(average_ranks(left), average_ranks(right)),
                    "descriptive_only": True,
                    "significance_tested": False,
                }
            )
    return results


def auxiliary_analyses(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in records if row["is_admitted"]]
    score_profiles = [
        summarize_group([row for row in records if row["raw_strategy_score"] == score], raw_strategy_score=score)
        for score in SCORES
    ]
    exit_profiles = [
        summarize_group([row for row in admitted if row["portfolio_exit_reason"] == reason], portfolio_exit_reason=reason)
        for reason in ("STOP_EXIT", "TARGET_EXIT", "TIME_EXIT")
    ]
    realized_profiles = grouped_rows(admitted, REALIZED_R_BUCKETS, lambda row: realized_r_bucket(decimal(row["realized_r_multiple"])), "realized_r_bucket")
    mfe_profiles = grouped_rows(records, MFE_BUCKETS, lambda row: mfe_bucket(decimal(row["mfe_r_4"])), "mfe_r_bucket")
    mae_profiles = grouped_rows(records, MAE_BUCKETS, lambda row: mae_bucket(decimal(row["mae_r_4"])), "mae_r_bucket")
    headroom_by_extension = grouped_rows(records, ATR_EXTENSION_BUCKETS, lambda row: atr_extension_bucket(row["entry_extension_atr"]), "atr_extension_bucket")
    headroom_by_gap = grouped_rows(records, GAP_BUCKETS, lambda row: gap_bucket(row["gap_pct"]), "gap_bucket")
    cohorts = {}
    cohort_predicates = {
        "HIGH_SCORE_HIGH_EXTENSION": lambda row: row["raw_strategy_score"] >= 84 and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5"),
        "HIGH_SCORE_LOW_EXTENSION": lambda row: row["raw_strategy_score"] >= 84 and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5"),
        "HIGH_RVOL_HIGH_EXTENSION": lambda row: row["rvol_state"] in {"STRONG", "EXCEPTIONAL"} and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5"),
        "HIGH_RVOL_LOW_EXTENSION": lambda row: row["rvol_state"] in {"STRONG", "EXCEPTIONAL"} and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5"),
        "STRONG_RS_HIGH_EXTENSION": lambda row: row["benchmark_rs_context"] == "STRONG" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5"),
        "STRONG_RS_LOW_EXTENSION": lambda row: row["benchmark_rs_context"] == "STRONG" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5"),
    }
    for name, predicate in cohort_predicates.items():
        cohorts[name] = summarize_group([row for row in records if predicate(row)], cohort=name)
    years = tuple(range(2022, 2027))
    yearly = [
        summarize_group([row for row in records if int(str(row["decision_date"])[:4]) == year], year=year, period_status="PARTIAL" if year == 2026 else "COMPLETE")
        for year in years
    ]
    regime = [
        summarize_group([row for row in records if row["regime_state"] == state], regime_state=state)
        for state in ("BULLISH", "NEUTRAL")
    ]
    reference_counts = Counter(str(row["structural_reference_basis"]) for row in records)
    return {
        "score_profiles": score_profiles,
        "exit_profiles": exit_profiles,
        "realized_r_profiles": realized_profiles,
        "mfe_profiles": mfe_profiles,
        "mae_profiles": mae_profiles,
        "target_headroom_by_extension": headroom_by_extension,
        "target_headroom_by_gap": headroom_by_gap,
        "diagnostic_cohorts": cohorts,
        "yearly_profiles": yearly,
        "regime_profiles": regime,
        "reference_availability": {
            "counts": dict(reference_counts),
            "extension_available_count": sum(row["entry_extension_atr"] is not None for row in records),
            "breakout_distance_available_count": sum(row["breakout_distance_pct"] is not None for row in records),
            "source_count": len(records),
        },
    }


def build_pilot(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cases: list[tuple[str, str, Callable[[Mapping[str, Any]], bool]]] = [
        ("A", "low extension <0.5 ATR", lambda row: row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("0.5")),
        ("B", "moderate extension 1–1.5 ATR", lambda row: row["entry_extension_atr"] is not None and Decimal("1") <= row["entry_extension_atr"] < Decimal("1.5")),
        ("C", "high extension >2 ATR", lambda row: row["entry_extension_atr"] is not None and row["entry_extension_atr"] > 2),
        ("D", "prior-day move >6%", lambda row: row["prior_day_return_pct"] is not None and row["prior_day_return_pct"] > 6),
        ("E", "mature 10d/20d momentum", lambda row: row["maturity_class"] in {"MATURE", "EXTENDED"}),
        ("F", "score 85 high extension", lambda row: row["raw_strategy_score"] == 85 and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
        ("G", "score 84 low extension", lambda row: row["raw_strategy_score"] == 84 and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5")),
        ("H", "STRONG RVOL high extension", lambda row: row["rvol_state"] == "STRONG" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
        ("I", "STRONG RS high extension", lambda row: row["benchmark_rs_context"] == "STRONG" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
        ("J", "Emerging low extension", lambda row: row["candidate_category"] == "EMERGING_ONLY" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5")),
        ("K", "Both-eligible high extension", lambda row: row["candidate_category"] == "BOTH_ELIGIBLE" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
        ("L", "stop exit high extension", lambda row: row["portfolio_exit_reason"] == "STOP_EXIT" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
        ("M", "target exit lower extension", lambda row: row["portfolio_exit_reason"] == "TARGET_EXIT" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5")),
        ("N", "time exit high extension", lambda row: row["portfolio_exit_reason"] == "TIME_EXIT" and row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")),
    ]
    rows = []
    for case, scenario, predicate in cases:
        selected = next((row for row in records if predicate(row)), None)
        if selected is None:
            raise ValueError(f"Required real pilot scenario unavailable: {case} {scenario}")
        rows.append(
            {
                "case": case,
                "scenario": scenario,
                "source_type": "REAL_FROZEN_DATA",
                "source_key": selected["source_key"],
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_date": selected["entry_date"],
                "structural_reference": selected["structural_reference"],
                "structural_reference_basis": selected["structural_reference_basis"],
                "atr_14": selected["atr_14"],
                "entry_price": selected["entry_price"],
                "entry_extension_pct": selected["entry_extension_pct"],
                "entry_extension_atr": selected["entry_extension_atr"],
                "atr_bucket": atr_extension_bucket(selected["entry_extension_atr"]),
                "prior_day_return_pct": selected["prior_day_return_pct"],
                "return_5d_pct": selected["return_5d_pct"],
                "return_10d_pct": selected["return_10d_pct"],
                "return_20d_pct": selected["return_20d_pct"],
                "maturity_class": selected["maturity_class"],
                "gap_pct": selected["gap_pct"],
                "rvol_state": selected["rvol_state"],
                "rs_state": selected["benchmark_rs_context"],
                "first_touch_outcome": selected["first_touch_outcome"],
                "portfolio_exit_reason": selected["portfolio_exit_reason"],
                "passed": True,
            }
        )
    return {
        "cases": rows,
        "case_count": len(rows),
        "real_case_count": len(rows),
        "passed": len(rows) == 14 and all(row["passed"] for row in rows),
        "validated_fields": ["structural_reference", "atr_14", "entry_price", "entry_extension_pct", "entry_extension_atr", "prior_return", "momentum_returns", "gap", "rvol", "rs", "outcome", "bucket_assignment"],
    }


def source_correlation(correlations: Sequence[Mapping[str, Any]], field: str) -> float:
    row = next(item for item in correlations if item["population"] == "SOURCE" and item["right_metric"] == field)
    return float(row["spearman"] or 0)


def compare_high_low(
    high: Mapping[str, Any], low: Mapping[str, Any]
) -> tuple[int, int]:
    weaker = sum(
        (
            decimal(high["mean_mfe_r"]) < decimal(low["mean_mfe_r"]),
            decimal(high["mean_realized_r"]) < decimal(low["mean_realized_r"]),
            decimal(high["stop_first_pct"]) > decimal(low["stop_first_pct"]),
        )
    )
    stronger = 3 - weaker
    return weaker, stronger


def classifications(
    records: Sequence[Mapping[str, Any]],
    correlations: Sequence[Mapping[str, Any]],
    auxiliary: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    cohorts = auxiliary["diagnostic_cohorts"]
    high = [row for row in records if row["entry_extension_atr"] is not None and row["entry_extension_atr"] >= Decimal("1.5")]
    low = [row for row in records if row["entry_extension_atr"] is not None and row["entry_extension_atr"] < Decimal("1.5")]
    high_summary = summarize_group(high)
    low_summary = summarize_group(low)
    exhaustion_checks = {
        "high_extension_lower_mfe": decimal(high_summary["mean_mfe_r"]) < decimal(low_summary["mean_mfe_r"]),
        "high_extension_lower_realized_r": decimal(high_summary["mean_realized_r"]) < decimal(low_summary["mean_realized_r"]),
        "high_extension_more_stop_first": decimal(high_summary["stop_first_pct"]) > decimal(low_summary["stop_first_pct"]),
        "high_extension_lower_target_headroom_r": decimal(high_summary["mean_target_distance_r"]) < decimal(low_summary["mean_target_distance_r"]),
        "mature_or_extended_lower_mfe": mean(values([row for row in records if row["maturity_class"] in {"MATURE", "EXTENDED"}], "mfe_r_4")) < mean(values([row for row in records if row["maturity_class"] in {"EARLY", "DEVELOPING"}], "mfe_r_4")),
    }
    supported = sum(exhaustion_checks.values())
    if len(high) < 30 or len(low) < 30:
        exhaustion = "INCONCLUSIVE"
    elif supported >= 4:
        exhaustion = "STRONG_ASSOCIATION"
    elif supported >= 3:
        exhaustion = "MATERIAL_ASSOCIATION"
    elif supported:
        exhaustion = "MIXED"
    else:
        exhaustion = "NO_CLEAR_EVIDENCE"

    score_values = [source_correlation(correlations, field) for field in ("entry_extension_atr", "prior_day_return_pct", "return_5d_pct", "return_10d_pct", "return_20d_pct")]
    score_median = statistics_median(score_values)
    if score_median >= 0.15 and sum(value > 0 for value in score_values) >= 4:
        score_result = "HIGHER_SCORE_MORE_MATURE"
    elif score_median <= -0.15 and sum(value < 0 for value in score_values) >= 4:
        score_result = "HIGHER_SCORE_LESS_MATURE"
    elif any(abs(value) >= 0.10 for value in score_values):
        score_result = "MIXED"
    else:
        score_result = "NO_CLEAR_RELATIONSHIP"

    gap_high = summarize_group([row for row in records if row["gap_pct"] is not None and row["gap_pct"] > Decimal("0.5")])
    gap_low = summarize_group([row for row in records if row["gap_pct"] is not None and row["gap_pct"] <= 0])
    gap_checks = (
        decimal(gap_high["mean_entry_extension_atr"]) > decimal(gap_low["mean_entry_extension_atr"]),
        decimal(gap_high["mean_prior_day_return_pct"]) > decimal(gap_low["mean_prior_day_return_pct"]),
        decimal(gap_high["mean_return_10d_pct"]) > decimal(gap_low["mean_return_10d_pct"]),
    )
    if min(gap_high["source_opportunities"], gap_low["source_opportunities"]) < 30:
        gap_result = "INCONCLUSIVE"
    elif sum(gap_checks) >= 2:
        gap_result = "POSITIVE_GAP_COMPOUNDS_MATURITY"
    elif sum(gap_checks) == 1:
        gap_result = "MIXED"
    else:
        gap_result = "NO_CLEAR_RELATIONSHIP"

    rvol_high, rvol_low = cohorts["HIGH_RVOL_HIGH_EXTENSION"], cohorts["HIGH_RVOL_LOW_EXTENSION"]
    rs_high, rs_low = cohorts["STRONG_RS_HIGH_EXTENSION"], cohorts["STRONG_RS_LOW_EXTENSION"]
    rvol_weaker, rvol_stronger = compare_high_low(rvol_high, rvol_low)
    rs_weaker, rs_stronger = compare_high_low(rs_high, rs_low)
    rvol_result = directional_result(rvol_high, rvol_low, rvol_weaker, rvol_stronger, "HIGH_RVOL_HIGH_EXTENSION")
    rs_result = directional_result(rs_high, rs_low, rs_weaker, rs_stronger, "STRONG_RS_HIGH_EXTENSION")

    stage = {row["candidate_stage"]: row for row in auxiliary["candidate_stage_profiles"]}
    emerging, both = stage["EMERGING_ONLY"], stage["BOTH_ELIGIBLE"]
    if min(emerging["source_opportunities"], both["source_opportunities"]) < 30:
        candidate_result = "INCONCLUSIVE"
    else:
        earlier = sum(
            decimal(emerging[field]) < decimal(both[field])
            for field in ("median_entry_extension_atr", "median_return_5d_pct", "median_return_10d_pct", "median_return_20d_pct")
        )
        later = 4 - earlier
        candidate_result = "EMERGING_EARLIER_STAGE" if earlier >= 3 else "BOTH_MORE_MATURE" if later >= 3 else "MIXED"
    return (
        {
            "ENTRY_EXHAUSTION_RESULT": exhaustion,
            "SCORE_MATURITY_RESULT": score_result,
            "GAP_MATURITY_RESULT": gap_result,
            "RVOL_EXTENSION_RESULT": rvol_result,
            "RS_EXTENSION_RESULT": rs_result,
            "CANDIDATE_STAGE_RESULT": candidate_result,
        },
        {
            "entry_exhaustion_checks": exhaustion_checks,
            "entry_exhaustion_support_count": supported,
            "score_maturity_spearman_values": score_values,
            "gap_maturity_checks": gap_checks,
        },
    )


def statistics_median(values_: Sequence[float]) -> float:
    ordered = sorted(values_)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def directional_result(
    high: Mapping[str, Any],
    low: Mapping[str, Any],
    weaker: int,
    stronger: int,
    prefix: str,
) -> str:
    if min(int(high["source_opportunities"]), int(low["source_opportunities"])) < 30:
        return "INCONCLUSIVE"
    if weaker >= 2:
        return f"{prefix}_WEAKER"
    if stronger >= 2:
        return f"{prefix}_STRONGER"
    return "MIXED"


def append_registry_preserving_previous(
    path: Path,
    original: Mapping[str, Any],
    new_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    previous = [copy.deepcopy(row) for row in original["experiments"] if row.get("experiment_id") not in ENTRY_QUALITY_EXPERIMENT_IDS]
    if len(previous) != 19:
        raise ValueError(f"Expected 19 previous experiments, found {len(previous)}")
    prior_hashes = {row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"]) for row in previous}
    payload = copy.deepcopy(dict(original))
    payload["experiments"] = previous + [dict(row) for row in new_records]
    payload["command_03"] = {"version": ENTRY_QUALITY_COMMAND_VERSION, "experiment_ids": list(ENTRY_QUALITY_EXPERIMENT_IDS), "promotion_allowed": False}
    write_json(path, payload)
    preserved = {row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"]) for row in payload["experiments"] if row["experiment_id"] in prior_hashes}
    if preserved != prior_hashes or len(payload["experiments"]) != 29:
        raise ValueError("Previous registry hashes changed or combined registry count is not 29")
    return {"previous_experiment_count": 19, "previous_parameter_and_preregistration_hashes_unchanged": True, "combined_registry_count": 29}


def write_outputs(
    *,
    context: EntryQualityContext,
    registry: EntryQualityRegistry,
    executions: Mapping[str, ExperimentExecution],
    summary: Mapping[str, Any],
    preregistration_path: Path,
    original_registry: Mapping[str, Any],
    correlations: Sequence[Mapping[str, Any]],
    pilot: Mapping[str, Any],
) -> tuple[list[Path], dict[str, Any]]:
    command_root = context.data_dir / "research/diagnostics/strategy/v1/entry_quality_command_03"
    report_root = context.data_dir / "reports"
    final_registry_path = command_root / "registry/entry_quality_experiment_registry_v1.json"
    write_json(final_registry_path, {"framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION, "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE, "command_version": ENTRY_QUALITY_COMMAND_VERSION, "promotion_allowed": False, "experiments": registry.records()})
    paths = [preregistration_path, final_registry_path]
    for experiment_id in ENTRY_QUALITY_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        run_root = command_root / "runs" / experiment_id
        result_path = run_root / "result.json"
        table_path = run_root / "table.csv.gz"
        write_json(result_path, execution.result)
        write_gzip_csv(table_path, execution.trades)
        paths.extend((result_path, table_path))
    report_mapping = {
        "strategy_diagnostic_v1_entry_quality_atr.csv": "EXP-ENTRYQ-002",
        "strategy_diagnostic_v1_entry_quality_breakout_distance.csv": "EXP-ENTRYQ-003",
        "strategy_diagnostic_v1_entry_quality_prior_move.csv": "EXP-ENTRYQ-004",
        "strategy_diagnostic_v1_entry_quality_maturity.csv": "EXP-ENTRYQ-005",
        "strategy_diagnostic_v1_entry_quality_gap_prior.csv": "EXP-ENTRYQ-006",
        "strategy_diagnostic_v1_entry_quality_rvol_extension.csv": "EXP-ENTRYQ-007",
        "strategy_diagnostic_v1_entry_quality_rs_extension.csv": "EXP-ENTRYQ-008",
        "strategy_diagnostic_v1_entry_quality_score_extension.csv": "EXP-ENTRYQ-009",
        "strategy_diagnostic_v1_entry_quality_candidate_stage.csv": "EXP-ENTRYQ-010",
    }
    for filename, experiment_id in report_mapping.items():
        path = report_root / filename
        write_csv(path, executions[experiment_id].trades)
        paths.append(path)
    correlation_path = report_root / "strategy_diagnostic_v1_entry_quality_correlations.csv"
    pilot_path = report_root / "strategy_diagnostic_v1_entry_quality_pilot.csv"
    write_csv(correlation_path, correlations)
    write_csv(pilot_path, pilot["cases"])
    paths.extend((correlation_path, pilot_path))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    preservation = append_registry_preserving_previous(main_registry_path, original_registry, registry.records())
    paths.append(main_registry_path)
    summary_path = report_root / "strategy_diagnostic_v1_entry_quality_summary.json"
    write_json(summary_path, summary)
    paths.append(summary_path)
    return paths, preservation


def run_entry_quality_diagnostics(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Loading frozen opportunities, ledgers, setup context, and Risk V1.1")
    context = load_entry_quality_context(Path(repo_root))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    original_registry = json.loads(main_registry_path.read_text(encoding="utf-8"))
    previous = [row for row in original_registry["experiments"] if row.get("experiment_id") not in ENTRY_QUALITY_EXPERIMENT_IDS]
    if len(previous) != 19 or any(row.get("status") != "COMPLETE" for row in previous):
        raise ValueError("Command 03 requires 19 immutable completed prior experiment records")
    definitions = build_entry_quality_definitions()
    registry = EntryQualityRegistry(context.baseline_hashes)
    for definition in definitions:
        registry.register(definition)
    preregistration_path = context.data_dir / "research/diagnostics/strategy/v1/entry_quality_command_03/registry/entry_quality_experiment_registry_v1_preregistered.json"
    write_json(preregistration_path, {"framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION, "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE, "command_version": ENTRY_QUALITY_COMMAND_VERSION, "written_before_metric_derivation_or_results": True, "promotion_allowed": False, "structural_reference_hierarchy": STRUCTURAL_REFERENCE_HIERARCHY, "maturity_mapping": MATURITY_MAPPING, "classification_rules": CLASSIFICATION_RULES, "experiments": registry.records()})
    notify(progress, "Pre-registered exactly ten immutable Command 03 definitions")
    records = derive_entry_quality_records(context)
    pilot = build_pilot(records)
    if not pilot["passed"]:
        raise ValueError("Real-data entry-quality pilot failed")
    notify(progress, "Validated all fourteen real-data pilot scenarios before the full suite")
    executions: dict[str, ExperimentExecution] = {}
    for experiment_id in ENTRY_QUALITY_EXPERIMENT_IDS:
        registry.mark_ready(experiment_id)
        notify(progress, f"Running {experiment_id} twice with frozen-hash guards")
        execution = registry.run_twice(
            experiment_id,
            lambda definition: execute_entry_quality_experiment(definition, records),
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Experiment failed: {experiment_id}: {registry.state(experiment_id).failure_reason}")
        executions[experiment_id] = execution

    correlations = correlation_rows(records)
    auxiliary = auxiliary_analyses(records)
    auxiliary["candidate_stage_profiles"] = [row for row in executions["EXP-ENTRYQ-010"].trades if row.get("section") == "STAGE_PROFILE"]
    classification_values, classification_evidence = classifications(records, correlations, auxiliary)
    hashes_after = portfolio_backtest_regression_hashes(context.data_dir)
    mutation_violations = sum(hashes_after[name] != value for name, value in context.baseline_hashes.items())
    failures = [state for state in registry._states.values() if state.status == "FAILED"]
    reproducible = all(row["match"] for row in registry.reproducibility.values())
    population_unchanged = len(records) == 3296 and sum(row["is_admitted"] for row in records) == 728 and sum(row["is_skipped"] for row in records) == 2568
    framework_result = "CLEAN" if pilot["passed"] and reproducible and population_unchanged and not failures and mutation_violations == 0 else "METHODOLOGY_FIX_REQUIRED"
    classification_values["FRAMEWORK_RESULT"] = framework_result
    hypothesis_supported = classification_values["ENTRY_EXHAUSTION_RESULT"] in {"MATERIAL_ASSOCIATION", "STRONG_ASSOCIATION"}
    summary: dict[str, Any] = {
        "phase": "Step 02.13",
        "command": COMMAND,
        "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
        "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
        "command_version": ENTRY_QUALITY_COMMAND_VERSION,
        "newly_registered_experiment_count": 10,
        "newly_registered_experiment_ids": list(ENTRY_QUALITY_EXPERIMENT_IDS),
        "combined_registry_expected_count": 29,
        "pre_registration": {"written_before_metric_derivation_or_results": True, "buckets_locked": True, "maturity_mapping_locked": True, "path": str(preregistration_path.relative_to(repo_root))},
        "baseline_dependency": {"backtest_version": BASELINE_DEPENDENCY[0], "backtest_profile": BASELINE_DEPENDENCY[1], "backtest_config_hash": BASELINE_DEPENDENCY[2], "hashes": hashes_after},
        "structural_reference_hierarchy": STRUCTURAL_REFERENCE_HIERARCHY,
        "maturity_mapping": MATURITY_MAPPING,
        "classification_rules": CLASSIFICATION_RULES,
        "population_integrity": {"source_opportunities": len(records), "admitted_trades": sum(row["is_admitted"] for row in records), "skipped_opportunities": sum(row["is_skipped"] for row in records), "slot_skipped_opportunities": sum(row["is_slot_skipped"] for row in records), "unchanged": population_unchanged, "ranking_changed": False, "filter_applied": False, "portfolio_equity_curve_generated": False},
        "baseline_profile": executions["EXP-ENTRYQ-001"].trades,
        "results": [executions[item].result for item in ENTRY_QUALITY_EXPERIMENT_IDS],
        "tables": {item: executions[item].trades for item in ENTRY_QUALITY_EXPERIMENT_IDS},
        "correlations": correlations,
        "auxiliary_analyses": auxiliary,
        "pilot": pilot,
        "classifications": classification_values,
        "classification_evidence": classification_evidence,
        "ENTRY_EXHAUSTION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING": hypothesis_supported,
        "reproducibility": registry.reproducibility,
        "all_experiments_reproducible": reproducible,
        "baseline_mutation_violations": mutation_violations,
        "failed_experiment_count": len(failures),
        "promotion_allowed": PROMOTION_ALLOWED,
        "experiments_promoted": 0,
        "automatic_selection_performed": False,
        "entry_filter_applied": False,
        "optimizer_or_parameter_search_run": False,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "performance_scope": PERFORMANCE_SCOPE,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "safety": {"live_signals_generated": 0, "live_orders_placed": 0, "remote_migrations_applied": 0, "supabase_records_persisted": 0},
        "security": {"backend_env_required_ignored": True, "diagnostic_outputs_required_ignored": True, "broker_credentials_written": False, "supabase_secrets_written": False, "api_tokens_written": False},
        "known_limitations": ["Descriptive association is not causality or a strategy rule.", "Only frozen daily EOD and next-open information is used; no intraday entry-quality history is inferred.", "The prior 20-session high is a general structural proxy when a more specific frozen breakout level is unavailable.", "CONFIRMED_ONLY and some interaction cells require small-sample warnings.", "Performance is historical and gross before costs and slippage."],
        "runtime_seconds": 0,
        "storage": {},
        "registry_preservation": {},
        "ready_for_review": False,
    }
    notify(progress, "Writing isolated Command 03 artifacts and machine reports")
    paths, preservation = write_outputs(context=context, registry=registry, executions=executions, summary=summary, preregistration_path=preregistration_path, original_registry=original_registry, correlations=correlations, pilot=pilot)
    summary["registry_preservation"] = preservation
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {"artifact_count": len(paths), "artifact_size_bytes": sum(path.stat().st_size for path in paths if path.exists()), "root": "data/research/diagnostics/strategy/v1/entry_quality_command_03"}
    summary["ready_for_review"] = framework_result == "CLEAN" and tests_passed and frontend_build_passed
    write_json(context.data_dir / "reports/strategy_diagnostic_v1_entry_quality_summary.json", summary)
    return summary


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

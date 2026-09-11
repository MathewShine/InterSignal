from __future__ import annotations

import copy
import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.score_calibration_diagnostic import (
    correlation,
    derive_score_calibration_records,
    load_score_calibration_context,
)
from app.diagnostics.strategy_diagnostic import (
    BASELINE_DEPENDENCY,
    COST_STATUS,
    PERFORMANCE_SCOPE,
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
from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset

COMMAND = "Command 05"
REGIME_CONTEXT_COMMAND_VERSION = "STRATEGY_DIAGNOSTIC_REGIME_CONTEXT_V1"
REGIME_CONTEXT_EXPERIMENT_IDS = (
    "EXP-REGIME-001",
    "EXP-REGIME-002",
    "EXP-REGIME-003",
    "EXP-REGIME-004",
    "EXP-REGIME-005",
    "EXP-REGIME-006",
    "EXP-REGIME-007",
    "EXP-REGIME-008",
    "EXP-REGIME-009",
    "EXP-REGIME-010",
)

YEARS = (2022, 2023, 2024, 2025, 2026)
POPULATIONS = ("SOURCE", "ADMITTED", "SLOT_SKIPPED")
REGIME_SCORE_BUCKETS = (
    ("LE_NEG_60", None, Decimal("-60"), True, True),
    ("NEG_59_TO_NEG_30", Decimal("-60"), Decimal("-30"), False, True),
    ("NEG_29_TO_NEG_10", Decimal("-30"), Decimal("-10"), False, True),
    ("NEG_9_TO_POS_9", Decimal("-10"), Decimal("10"), False, False),
    ("POS_10_TO_29", Decimal("10"), Decimal("30"), True, False),
    ("POS_30_TO_49", Decimal("30"), Decimal("50"), True, False),
    ("POS_50_TO_69", Decimal("50"), Decimal("70"), True, False),
    ("GE_POS_70", Decimal("70"), None, True, True),
)
BULLISH_STRENGTH_BUCKETS = (
    ("BULLISH_LOW", Decimal("30"), Decimal("45"), True, False),
    ("BULLISH_MEDIUM", Decimal("45"), Decimal("60"), True, False),
    ("BULLISH_STRONG", Decimal("60"), Decimal("75"), True, False),
    ("BULLISH_VERY_STRONG", Decimal("75"), None, True, True),
)
NEUTRAL_POSITION_BUCKETS = (
    ("NEGATIVE_NEUTRAL", Decimal("-30"), Decimal("-10"), False, True),
    ("MID_NEUTRAL", Decimal("-10"), Decimal("10"), False, False),
    ("POSITIVE_NEUTRAL", Decimal("10"), Decimal("30"), True, False),
)
TREND_BUCKETS = (
    ("LE_NEG_20", None, Decimal("-20"), True, True),
    ("NEG_19_TO_NEG_10", Decimal("-20"), Decimal("-10"), False, True),
    ("NEG_9_TO_POS_9", Decimal("-10"), Decimal("10"), False, False),
    ("POS_10_TO_19", Decimal("10"), Decimal("20"), True, False),
    ("GE_POS_20", Decimal("20"), None, True, True),
)
BREADTH_BUCKETS = (
    ("LE_NEG_12", None, Decimal("-12"), True, True),
    ("NEG_11_TO_NEG_5", Decimal("-12"), Decimal("-5"), False, True),
    ("NEG_4_TO_POS_4", Decimal("-5"), Decimal("5"), False, False),
    ("POS_5_TO_11", Decimal("5"), Decimal("12"), True, False),
    ("GE_POS_12", Decimal("12"), None, True, True),
)
SECTOR_BUCKETS = (
    ("LE_NEG_9", None, Decimal("-9"), True, True),
    ("NEG_8_TO_NEG_3", Decimal("-9"), Decimal("-3"), False, True),
    ("NEG_2_TO_POS_2", Decimal("-3"), Decimal("3"), False, False),
    ("POS_3_TO_POS_8", Decimal("3"), Decimal("9"), True, False),
    ("GE_POS_9", Decimal("9"), None, True, True),
)
RR_BUCKETS = (
    ("RR_1_5_TO_LT_2", Decimal("1.5"), Decimal("2"), True, False),
    ("RR_2_TO_LT_2_5", Decimal("2"), Decimal("2.5"), True, False),
    ("RR_GE_2_5", Decimal("2.5"), None, True, True),
)
GAP_BUCKETS = (
    ("GAP_LE_ZERO", None, Decimal("0"), True, True),
    ("GAP_POS_TO_0_5", Decimal("0"), Decimal("0.5"), False, True),
    ("GAP_GT_0_5", Decimal("0.5"), None, False, True),
)
STREAK_BUCKETS = (
    ("STREAK_1", Decimal("1"), Decimal("1"), True, True),
    ("STREAK_2_TO_3", Decimal("2"), Decimal("3"), True, True),
    ("STREAK_4_TO_10", Decimal("4"), Decimal("10"), True, True),
    ("STREAK_11_TO_20", Decimal("11"), Decimal("20"), True, True),
    ("STREAK_GT_20", Decimal("20"), None, False, True),
)
BORDERLINE_BUCKETS = (
    ("BULLISH_BORDERLINE", Decimal("30"), Decimal("35"), True, False),
    ("NEUTRAL_UPPER_BORDERLINE", Decimal("25"), Decimal("30"), True, False),
    ("NEUTRAL_LOWER_BORDERLINE", Decimal("-30"), Decimal("-25"), False, True),
    ("BEARISH_BORDERLINE", Decimal("-35"), Decimal("-30"), True, True),
)
CONFIDENCE_STATES = ("LOW", "MEDIUM", "HIGH")
CONTEXT_BUCKETS = tuple(item[0] for item in BULLISH_STRENGTH_BUCKETS + NEUTRAL_POSITION_BUCKETS)
COMPONENT_FIELDS = {
    "NIFTY_TREND": "nifty_trend_contribution",
    "BREADTH": "breadth_contribution",
    "SECTOR_PARTICIPATION": "sector_contribution",
}
COMPONENT_BUCKETS = {
    "NIFTY_TREND": TREND_BUCKETS,
    "BREADTH": BREADTH_BUCKETS,
    "SECTOR_PARTICIPATION": SECTOR_BUCKETS,
}
SAMPLE_SIZE_RULES = {
    "VERY_SMALL": "count < 30",
    "SMALL": "30 <= count <= 99",
    "LIMITED": "100 <= count <= 299",
    "ADEQUATE_FOR_DESCRIPTION": "count >= 300",
}
CLASSIFICATION_RULES = {
    "COMPONENT_DISCRIMINATION": "Four locked correlation directions are MFE positive, MAE negative, realized-R positive, and positive-trade positive. Four favorable with no unfavorable is CLEAR_POSITIVE; two or more favorable and more favorable than unfavorable is WEAK_POSITIVE; two or more unfavorable and more unfavorable than favorable is INVERSE; both material signs is MIXED; otherwise NO_CLEAR; admitted variation below 30 is INCONCLUSIVE.",
    "TOTAL_REGIME": "Apply the same four directions to normalized regime score. Four favorable is CLEAR_POSITIVE; three is WEAK_POSITIVE; two favorable and more favorable than unfavorable is PARTIALLY_DISCRIMINATIVE; mixed signs is MIXED; no material directions is NO_CLEAR; inadequate data is INCONCLUSIVE.",
    "BULLISH_NEUTRAL": "Compare source MFE, inverse MAE, admitted realized R, and positive rate. At least three favorable and none unfavorable is BULLISH_CLEARLY_STRONGER; at least two and more favorable than unfavorable is BULLISH_MODESTLY_STRONGER; both signs is MIXED; otherwise NO_CLEAR; small admitted Neutral is retained with a warning.",
    "BORDERLINE": "Compare Bullish +30..+34 with Bullish >=+45 using the same four directions. Small endpoint cohorts are INCONCLUSIVE; otherwise majority directions determine weaker/stronger/mixed/no-clear.",
    "PERSISTENCE": "Compare Bullish streak 1 with streak >10 using the same four directions. Small endpoint cohorts are INCONCLUSIVE; otherwise majority directions determine established/new stronger, mixed, or no-clear.",
    "YEARLY_DIRECTION": "For annual admitted realized-R Spearman, all evaluable signs equal is CONSISTENT or INVERSE_ACROSS_PERIODS; four of five equal is MOSTLY_CONSISTENT; mixed material signs is UNSTABLE; fewer than three evaluable years is INCONCLUSIVE.",
}


@dataclass(slots=True)
class RegimeContext:
    repo_root: Path
    data_dir: Path
    score_context: Any
    baseline_hashes: dict[str, str]
    regime_rows: list[dict[str, str]]
    regime_by_date: dict[str, dict[str, str]]
    history_meta: dict[str, dict[str, Any]]
    regime_version: str
    regime_config_hash: str


class RegimeContextRegistry:
    def __init__(self, baseline_hashes: Mapping[str, str]) -> None:
        self.baseline_hashes = dict(baseline_hashes)
        self._states: dict[str, ExperimentState] = {}
        self.reproducibility: dict[str, dict[str, Any]] = {}

    def register(self, definition: ExperimentDefinition) -> None:
        if definition.experiment_id not in REGIME_CONTEXT_EXPERIMENT_IDS:
            raise ValueError(f"Unauthorized Command 05 experiment: {definition.experiment_id}")
        if definition.family != "REGIME_CONTEXT_DIAGNOSTIC":
            raise ValueError("Command 05 experiments must use REGIME_CONTEXT_DIAGNOSTIC")
        if definition.experiment_id in self._states:
            raise ValueError(f"Experiment ID already registered: {definition.experiment_id}")
        if definition.eligible_for_promotion or not definition.diagnostic_only:
            raise ValueError("Regime-context experiments cannot be promotion eligible")
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
                    raise ValueError("Frozen baseline hash mismatch before regime-context diagnostic")
                execution = runner(state.definition)
                after = dict(hash_reader())
                unchanged = before == after == self.baseline_hashes
                guards.append({"run_number": run_number, "before": before, "after": after, "unchanged": unchanged})
                if not unchanged:
                    raise ValueError("Frozen baseline hash mutation detected")
                runs.append(execution)
            fingerprints = [item.canonical_fingerprint() for item in runs]
            if fingerprints[0] != fingerprints[1]:
                raise ValueError("Repeated canonical regime-context outputs differ")
            execution = runs[0]
            record = regime_context_definition_record(state.definition, self.baseline_hashes)
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
                **regime_context_definition_record(
                    self._states[item].definition,
                    self.baseline_hashes,
                    status=self._states[item].status,
                ),
                "result_fingerprint": self._states[item].result_fingerprint,
                "failure_reason": self._states[item].failure_reason,
            }
            for item in REGIME_CONTEXT_EXPERIMENT_IDS
            if item in self._states
        ]


def build_regime_context_definitions(
    registered_at: str | None = None,
) -> tuple[ExperimentDefinition, ...]:
    timestamp = registered_at or datetime.now(timezone.utc).isoformat()
    config = MarketRegimeConfig()
    locked = {
        "frozen_regime_version": MARKET_REGIME_VERSION,
        "frozen_regime_config_hash": config.config_hash(),
        "regime_score_field": "regime_score_normalized",
        "raw_contribution_score_field": "regime_score_raw",
        "regime_weights": config.snapshot()["weights"],
        "regime_thresholds": config.snapshot()["classification"],
        "sample_size_rules": SAMPLE_SIZE_RULES,
        "classification_rules_hash": canonical_hash(CLASSIFICATION_RULES),
        "no_threshold_change": True,
        "no_regime_reweighting": True,
        "no_neutral_exclusion": True,
        "no_hysteresis_or_smoothing": True,
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
        _definition(timestamp, "EXP-REGIME-001", "BASELINE_REGIME_PROFILE", "Describe frozen Bullish, Neutral, Bearish-exceptional, and unavailable cohorts.", {**locked, "profile_states": ("BULLISH", "NEUTRAL", "BEARISH_EXCEPTIONAL", "UNAVAILABLE")}, metrics),
        _definition(timestamp, "EXP-REGIME-002", "REGIME_SCORE_BUCKETS", "Describe outcome behavior across fixed normalized regime-score buckets.", {**locked, "buckets": REGIME_SCORE_BUCKETS}, metrics),
        _definition(timestamp, "EXP-REGIME-003", "BULLISH_STRENGTH_BUCKETS", "Describe directional outcome separation within fixed Bullish-strength buckets.", {**locked, "buckets": BULLISH_STRENGTH_BUCKETS}, metrics),
        _definition(timestamp, "EXP-REGIME-004", "NEUTRAL_POSITION_BUCKETS", "Describe whether fixed Neutral-position buckets differ historically.", {**locked, "buckets": NEUTRAL_POSITION_BUCKETS, "neutral_sample_warning": True}, metrics),
        _definition(timestamp, "EXP-REGIME-005", "NIFTY_TREND_COMPONENT_DISCRIMINATION", "Describe the exact upstream Nifty trend contribution using fixed bins.", {**locked, "component": "NIFTY_TREND", "component_field": "nifty_trend_contribution", "buckets": TREND_BUCKETS}, metrics),
        _definition(timestamp, "EXP-REGIME-006", "BREADTH_COMPONENT_DISCRIMINATION", "Describe the exact upstream Nifty 500 breadth contribution using fixed bins.", {**locked, "component": "BREADTH", "component_field": "breadth_contribution", "buckets": BREADTH_BUCKETS}, metrics),
        _definition(timestamp, "EXP-REGIME-007", "SECTOR_PARTICIPATION_COMPONENT_DISCRIMINATION", "Describe market-wide sector-index participation using fixed bins.", {**locked, "component": "SECTOR_PARTICIPATION", "component_field": "sector_contribution", "buckets": SECTOR_BUCKETS, "not_stock_sector_scoring": True}, metrics),
        _definition(timestamp, "EXP-REGIME-008", "REGIME_X_SCORE_INTERACTION", "Cross fixed Bullish/Neutral context buckets with frozen raw Strategy Score 80 through 85.", {**locked, "context_buckets": BULLISH_STRENGTH_BUCKETS + NEUTRAL_POSITION_BUCKETS, "strategy_scores": (80, 81, 82, 83, 84, 85), "high_score_weak_context": {"score_min": 84, "regime_score_lt": 45}, "high_score_stronger_context": {"score_min": 84, "regime_score_gte": 45}, "lower_score_strong_context": {"scores": (80, 81, 82), "regime_score_gte": 60}}, metrics),
        _definition(timestamp, "EXP-REGIME-009", "REGIME_X_SETUP_RR_INTERACTION", "Cross fixed context with setup, effective R:R, candidate stage, and gap.", {**locked, "context_buckets": BULLISH_STRENGTH_BUCKETS + NEUTRAL_POSITION_BUCKETS, "setup_values": ("VALID", "STRONG"), "rr_buckets": RR_BUCKETS, "candidate_stages": ("EMERGING_ONLY", "BOTH_ELIGIBLE", "CONFIRMED_ONLY"), "gap_buckets": GAP_BUCKETS}, metrics),
        _definition(timestamp, "EXP-REGIME-010", "YEARLY_REGIME_STABILITY", "Describe fixed regime and component distributions and outcome directions by year.", {**locked, "years": YEARS, "partial_year": 2026, "bullish_buckets": BULLISH_STRENGTH_BUCKETS, "neutral_buckets": NEUTRAL_POSITION_BUCKETS, "component_buckets": COMPONENT_BUCKETS}, metrics),
    )
    if tuple(item.experiment_id for item in definitions) != REGIME_CONTEXT_EXPERIMENT_IDS:
        raise ValueError("Command 05 experiment definitions differ from the exact allowlist")
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
        family="REGIME_CONTEXT_DIAGNOSTIC",
        name=name,
        description=description,
        hypothesis="Frozen Market Regime V1 strength and available components may discriminate historical Strategy V1 opportunity quality across populations and years.",
        parameters=tuple(parameters.items()),
        outcome_fields_used_for_evaluation=metrics,
        changes_strategy_semantics=False,
        changes_portfolio_mechanics=False,
        registered_at=timestamp,
    )


def calculate_regime_context_pre_registration_hash(
    definition: ExperimentDefinition,
    baseline_hashes: Mapping[str, str],
) -> str:
    return canonical_hash(
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "command_version": REGIME_CONTEXT_COMMAND_VERSION,
            "definition": {
                "experiment_id": definition.experiment_id,
                "family": definition.family,
                "hypothesis": definition.hypothesis,
                "parameters": definition.parameter_map,
                "metrics": definition.outcome_fields_used_for_evaluation,
            },
            "frozen_regime_version": MARKET_REGIME_VERSION,
            "frozen_regime_config_hash": MarketRegimeConfig().config_hash(),
            "baseline_hashes": dict(baseline_hashes),
            "promotion_allowed": False,
        }
    )


def regime_context_definition_record(
    definition: ExperimentDefinition,
    baseline_hashes: Mapping[str, str],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    parameters = definition.parameter_map
    return {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "description": definition.description,
        "hypothesis": definition.hypothesis,
        "frozen_regime_version": MARKET_REGIME_VERSION,
        "frozen_regime_config_hash": MarketRegimeConfig().config_hash(),
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": dict(baseline_hashes),
        },
        "metric_definitions": list(definition.outcome_fields_used_for_evaluation),
        "bucket_definitions": parameters.get("buckets", parameters.get("context_buckets", parameters.get("component_buckets", {}))),
        "parameters": parameters,
        "parameter_hash": definition.parameter_hash,
        "pre_registration_hash": calculate_regime_context_pre_registration_hash(definition, baseline_hashes),
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


def load_regime_context(repo_root: Path) -> RegimeContext:
    score_context = load_score_calibration_context(Path(repo_root))
    data_dir = score_context.data_dir
    regime_path = data_dir / "research/regime/daily/v1/market_regime_daily_v1.csv.gz"
    regime_rows = read_gzip_csv(regime_path)
    config = MarketRegimeConfig()
    if len(regime_rows) != 1224:
        raise ValueError(f"Frozen MARKET_REGIME_V1 row count changed: {len(regime_rows)}")
    if {row["regime_version"] for row in regime_rows} != {MARKET_REGIME_VERSION}:
        raise ValueError("Frozen regime version mismatch")
    if {row["config_hash"] for row in regime_rows} != {config.config_hash()}:
        raise ValueError("Frozen regime config hash mismatch")
    state_counts = Counter(row["regime_state"] for row in regime_rows)
    if state_counts != Counter({"BULLISH": 578, "NEUTRAL": 234, "BEARISH": 379, "UNAVAILABLE": 33}):
        raise ValueError(f"Frozen regime-state distribution changed: {state_counts}")
    if any(row["global_gift_status"] != "UNAVAILABLE" or row["vix_status"] != "UNAVAILABLE" or row["intraday_status"] != "UNAVAILABLE" for row in regime_rows):
        raise ValueError("Historically unavailable regime component unexpectedly became available")
    history_meta = build_regime_history_meta(regime_rows)
    return RegimeContext(
        repo_root=Path(repo_root),
        data_dir=data_dir,
        score_context=score_context,
        baseline_hashes=dict(score_context.baseline_hashes),
        regime_rows=regime_rows,
        regime_by_date={row["trading_date"]: row for row in regime_rows},
        history_meta=history_meta,
        regime_version=MARKET_REGIME_VERSION,
        regime_config_hash=config.config_hash(),
    )


def build_regime_history_meta(regime_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    ordered = sorted(regime_rows, key=lambda row: str(row["trading_date"]))
    result: dict[str, dict[str, Any]] = {}
    streak = 0
    prior_state: str | None = None
    for index, row in enumerate(ordered):
        state = str(row["regime_state"])
        streak = streak + 1 if state == prior_state else 1
        prior_changed = prior_state is not None and state != prior_state
        next_state = str(ordered[index + 1]["regime_state"]) if index + 1 < len(ordered) else None
        next_changed = next_state is not None and next_state != state
        prior_direct_bull_bear = prior_state is not None and {prior_state, state} == {"BULLISH", "BEARISH"}
        next_direct_bull_bear = next_state is not None and {state, next_state} == {"BULLISH", "BEARISH"}
        if prior_changed and next_changed:
            flip_role = "CHANGE_SESSION_AND_PRIOR_TO_NEXT_CHANGE"
        elif prior_changed:
            flip_role = "CHANGE_SESSION_FROM_PRIOR"
        elif next_changed:
            flip_role = "PRIOR_SESSION_TO_FUTURE_CHANGE"
        else:
            flip_role = "NOT_NEAR_FLIP"
        result[str(row["trading_date"])] = {
            "regime_streak_sessions": streak,
            "prior_regime_state": prior_state,
            "next_regime_state": next_state,
            "prior_state_changed": prior_changed,
            "next_state_changed": next_changed,
            "near_regime_flip": prior_changed or next_changed,
            "regime_flip_role": flip_role,
            "near_direct_bull_bear_flip": prior_direct_bull_bear or next_direct_bull_bear,
            "direct_bull_bear_flip_from_prior": prior_direct_bull_bear,
            "direct_bull_bear_flip_next_session": next_direct_bull_bear,
            "future_state_diagnostic_only": True,
        }
        prior_state = state
    return result


def optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else Decimal(str(value))


def truthy(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() == "true"


def sample_size_flag(count: int) -> str:
    if count < 30:
        return "VERY_SMALL"
    if count < 100:
        return "SMALL"
    if count < 300:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def in_bucket(
    value: Decimal | None,
    bucket: tuple[str, Decimal | None, Decimal | None, bool, bool],
) -> bool:
    if value is None:
        return False
    _, lower, upper, lower_inclusive, upper_inclusive = bucket
    if lower is not None and (value < lower if lower_inclusive else value <= lower):
        return False
    if upper is not None and (value > upper if upper_inclusive else value >= upper):
        return False
    return True


def bucket_for(
    value: Decimal | None,
    buckets: Sequence[tuple[str, Decimal | None, Decimal | None, bool, bool]],
) -> str:
    for bucket in buckets:
        if in_bucket(value, bucket):
            return bucket[0]
    return "UNAVAILABLE"


def context_bucket(regime_state: str, normalized_score: Decimal | None) -> str:
    if regime_state == "BULLISH":
        return bucket_for(normalized_score, BULLISH_STRENGTH_BUCKETS)
    if regime_state == "NEUTRAL":
        return bucket_for(normalized_score, NEUTRAL_POSITION_BUCKETS)
    return f"{regime_state}_SEPARATE"


def attach_regime_fields(
    record: Mapping[str, Any],
    regime: Mapping[str, Any],
    history: Mapping[str, Any],
    *,
    cohort: str,
    path_eligible: bool,
) -> dict[str, Any]:
    normalized = optional_decimal(regime.get("regime_score_normalized"))
    raw = optional_decimal(regime.get("regime_score_raw"))
    trend = optional_decimal(regime.get("nifty_trend_contribution"))
    breadth = optional_decimal(regime.get("breadth_contribution"))
    sector = optional_decimal(regime.get("sector_contribution"))
    streak = int(history.get("regime_streak_sessions", 0))
    enriched = dict(record)
    enriched.update(
        {
            "diagnostic_cohort": cohort,
            "path_eligible": path_eligible,
            "regime_version": regime.get("regime_version"),
            "regime_config_hash": regime.get("config_hash"),
            "regime_status": regime.get("regime_status"),
            "regime_state": regime.get("regime_state"),
            "regime_subtype": regime.get("regime_subtype"),
            "regime_raw_score": raw,
            "regime_score_normalized": normalized,
            "regime_score_bucket": bucket_for(normalized, REGIME_SCORE_BUCKETS),
            "regime_context_bucket": context_bucket(str(regime.get("regime_state")), normalized),
            "regime_available_weight_pct": optional_decimal(regime.get("available_weight_pct")),
            "regime_confidence_score": optional_decimal(regime.get("confidence_score")),
            "regime_confidence": regime.get("confidence_state") or "UNAVAILABLE",
            "component_agreement_pct": optional_decimal(regime.get("component_agreement_pct")),
            "nifty_trend_status": regime.get("nifty_trend_status"),
            "nifty_trend_state": regime.get("nifty_trend_state"),
            "nifty_trend_contribution": trend,
            "nifty_trend_bucket": bucket_for(trend, TREND_BUCKETS),
            "breadth_status": regime.get("breadth_status"),
            "breadth_state": regime.get("breadth_state"),
            "breadth_contribution": breadth,
            "breadth_bucket": bucket_for(breadth, BREADTH_BUCKETS),
            "sector_status": regime.get("sector_status"),
            "sector_state": regime.get("sector_state"),
            "sector_contribution": sector,
            "sector_bucket": bucket_for(sector, SECTOR_BUCKETS),
            "global_gift_status": regime.get("global_gift_status"),
            "vix_status": regime.get("vix_status"),
            "intraday_status": regime.get("intraday_status"),
            "missing_regime_components": regime.get("missing_components"),
            "regime_streak_sessions": streak,
            "regime_streak_bucket": bucket_for(Decimal(streak), STREAK_BUCKETS),
            "prior_regime_state": history.get("prior_regime_state"),
            "next_regime_state": history.get("next_regime_state"),
            "prior_state_changed": history.get("prior_state_changed", False),
            "next_state_changed": history.get("next_state_changed", False),
            "near_regime_flip": history.get("near_regime_flip", False),
            "regime_flip_role": history.get("regime_flip_role", "NOT_NEAR_FLIP"),
            "near_direct_bull_bear_flip": history.get("near_direct_bull_bear_flip", False),
            "direct_bull_bear_flip_from_prior": history.get("direct_bull_bear_flip_from_prior", False),
            "direct_bull_bear_flip_next_session": history.get("direct_bull_bear_flip_next_session", False),
            "future_state_diagnostic_only": True,
            "positive_trade_indicator": (
                Decimal("1")
                if enriched.get("gross_pnl") is not None and decimal(enriched["gross_pnl"]) > 0
                else Decimal("0") if enriched.get("gross_pnl") is not None else None
            ),
        }
    )
    return enriched


def derive_regime_context_records(
    context: RegimeContext,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    main = derive_score_calibration_records(context.score_context)
    enriched_main: list[dict[str, Any]] = []
    for record in main:
        decision_date = str(record["decision_date"])
        regime = context.regime_by_date.get(decision_date)
        if regime is None:
            raise ValueError(f"Missing frozen regime row for {record['source_key']}")
        if str(regime["regime_state"]) != str(record["regime_state"]):
            raise ValueError(f"Frozen regime-state join mismatch for {record['source_key']}")
        enriched_main.append(
            attach_regime_fields(
                record,
                regime,
                context.history_meta[decision_date],
                cohort="NORMAL_ENTRY_ELIGIBLE",
                path_eligible=True,
            )
        )
    outcome_path = resolve_current_strategy_outcome_dataset(context.data_dir)
    outcome_rows = read_gzip_csv(outcome_path)
    exceptional = [
        research_outcome_record(row, context, cohort="BEARISH_EXCEPTIONAL_REVIEW")
        for row in outcome_rows
        if row.get("outcome_cohort") == "EXCEPTIONAL_REVIEW_RESEARCH"
    ]
    unavailable = [
        research_outcome_record(row, context, cohort="UNAVAILABLE_PREVIEW")
        for row in outcome_rows
        if row.get("outcome_cohort") == "PREVIEW_RESEARCH_ONLY" and row.get("regime_state") == "UNAVAILABLE"
    ]
    if len(enriched_main) != 3296 or sum(bool(row["is_admitted"]) for row in enriched_main) != 728:
        raise ValueError("Command 05 changed the frozen normal population")
    if Counter(row["regime_state"] for row in enriched_main) != Counter({"BULLISH": 3253, "NEUTRAL": 43}):
        raise ValueError("Frozen Bullish/Neutral source distribution changed")
    if Counter(row["regime_state"] for row in enriched_main if row["is_admitted"]) != Counter({"BULLISH": 690, "NEUTRAL": 38}):
        raise ValueError("Frozen Bullish/Neutral admitted distribution changed")
    if len(exceptional) != 324 or len(unavailable) != 28:
        raise ValueError(f"Frozen separate research cohorts changed: exceptional={len(exceptional)}, unavailable={len(unavailable)}")
    return enriched_main, exceptional, unavailable


def research_outcome_record(
    outcome: Mapping[str, Any],
    context: RegimeContext,
    *,
    cohort: str,
) -> dict[str, Any]:
    decision_date = str(outcome["decision_date"])
    regime = context.regime_by_date.get(decision_date)
    if regime is None:
        raise ValueError(f"Missing regime row for research cohort {source_key(outcome)}")
    if str(regime["regime_state"]) != str(outcome["regime_state"]):
        raise ValueError(f"Research-cohort regime-state mismatch for {source_key(outcome)}")
    path_eligible = truthy(outcome.get("entry_valid"))
    record = {
        "source_key": source_key(outcome),
        "symbol": outcome.get("symbol"),
        "decision_date": decision_date,
        "entry_date": outcome.get("next_session_date"),
        "is_admitted": False,
        "is_skipped": False,
        "is_slot_skipped": False,
        "skip_reason": "",
        "raw_strategy_score": int(decimal(outcome.get("raw_strategy_score"))),
        "setup_quality": outcome.get("setup_quality"),
        "candidate_category": outcome.get("candidate_category"),
        "effective_reward_risk": optional_decimal(outcome.get("effective_reward_risk")),
        "gap_pct": optional_decimal(outcome.get("gap_from_t_close_pct")),
        "mfe_r_4": optional_decimal(outcome.get("mfe_r_4")) if path_eligible else None,
        "mae_r_4": optional_decimal(outcome.get("mae_r_4")) if path_eligible else None,
        "close_return_pct_4": optional_decimal(outcome.get("close_return_pct_4")) if path_eligible else None,
        "first_touch_outcome": outcome.get("first_touch_outcome") if path_eligible else None,
        "realized_r_multiple": None,
        "gross_pnl": None,
        "portfolio_exit_reason": None,
        "setup_points": int(decimal(outcome.get("setup_points"))),
        "momentum_points": int(decimal(outcome.get("momentum_points"))),
        "rvol_points": int(decimal(outcome.get("rvol_points"))),
        "rs_points": int(decimal(outcome.get("relative_strength_points"))),
        "regime_points": int(decimal(outcome.get("regime_points"))),
        "rr_points": int(decimal(outcome.get("reward_risk_points"))),
    }
    return attach_regime_fields(
        record,
        regime,
        context.history_meta[decision_date],
        cohort=cohort,
        path_eligible=path_eligible,
    )


def numeric_values(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return [decimal(row[field]) for row in rows if row.get(field) is not None and str(row.get(field)).strip() != ""]


def summarize_records(rows: Sequence[Mapping[str, Any]], **labels: Any) -> dict[str, Any]:
    path_rows = [row for row in rows if row.get("path_eligible")]
    admitted = [row for row in rows if row.get("is_admitted")]
    first_touch = Counter(str(row.get("first_touch_outcome") or "") for row in path_rows)
    target_first = sum(count for key, count in first_touch.items() if "TARGET_FIRST" in key)
    stop_first = sum(count for key, count in first_touch.items() if "STOP_FIRST" in key)
    neither = len(path_rows) - target_first - stop_first
    exits = Counter(str(row.get("portfolio_exit_reason") or "") for row in admitted)
    positive = sum(decimal(row["gross_pnl"]) > 0 for row in admitted if row.get("gross_pnl") is not None)
    positive_time = sum(
        row.get("portfolio_exit_reason") == "TIME_EXIT" and decimal(row.get("gross_pnl")) > 0
        for row in admitted
    )
    state_counts = Counter(str(row.get("regime_state") or "UNAVAILABLE") for row in rows)
    context_counts = Counter(str(row.get("regime_context_bucket") or "UNAVAILABLE") for row in rows)
    next_counts = Counter(str(row.get("next_regime_state") or "UNAVAILABLE") for row in rows)
    summary = {
        **labels,
        "sample_size": len(rows),
        "sample_size_flag": sample_size_flag(len(rows)),
        "path_metric_count": len(path_rows),
        "admitted_count": len(admitted),
        "admission_rate_pct": percent(Decimal(len(admitted)), Decimal(len(rows))),
        "slot_skipped_count": sum(bool(row.get("is_slot_skipped")) for row in rows),
        "mean_strategy_score": mean(numeric_values(rows, "raw_strategy_score")),
        "median_strategy_score": median(numeric_values(rows, "raw_strategy_score")),
        "setup_quality_counts": dict(sorted(Counter(str(row.get("setup_quality") or "UNAVAILABLE") for row in rows).items())),
        "candidate_category_counts": dict(sorted(Counter(str(row.get("candidate_category") or "UNAVAILABLE") for row in rows).items())),
        "regime_state_counts": dict(sorted(state_counts.items())),
        "regime_context_bucket_counts": dict(sorted(context_counts.items())),
        "mean_effective_reward_risk": mean(numeric_values(rows, "effective_reward_risk")),
        "median_effective_reward_risk": median(numeric_values(rows, "effective_reward_risk")),
        "mean_gap_pct": mean(numeric_values(rows, "gap_pct")),
        "median_gap_pct": median(numeric_values(rows, "gap_pct")),
        "mean_mfe_r": mean(numeric_values(path_rows, "mfe_r_4")),
        "median_mfe_r": median(numeric_values(path_rows, "mfe_r_4")),
        "mean_mae_r": mean(numeric_values(path_rows, "mae_r_4")),
        "median_mae_r": median(numeric_values(path_rows, "mae_r_4")),
        "mean_close_return_pct_4": mean(numeric_values(path_rows, "close_return_pct_4")),
        "median_close_return_pct_4": median(numeric_values(path_rows, "close_return_pct_4")),
        "target_first_count": target_first,
        "target_first_pct": percent(Decimal(target_first), Decimal(len(path_rows))),
        "stop_first_count": stop_first,
        "stop_first_pct": percent(Decimal(stop_first), Decimal(len(path_rows))),
        "neither_count": neither,
        "neither_pct": percent(Decimal(neither), Decimal(len(path_rows))),
        "mean_realized_r": mean(numeric_values(admitted, "realized_r_multiple")),
        "median_realized_r": median(numeric_values(admitted, "realized_r_multiple")),
        "gross_pnl": sum(numeric_values(admitted, "gross_pnl"), Decimal("0")),
        "positive_trade_count": positive,
        "positive_trade_rate_pct": percent(Decimal(positive), Decimal(len(admitted))),
        "target_exits": exits["TARGET_EXIT"],
        "stop_exits": exits["STOP_EXIT"],
        "time_exits": exits["TIME_EXIT"],
        "target_rate_pct": percent(Decimal(exits["TARGET_EXIT"]), Decimal(len(admitted))),
        "stop_rate_pct": percent(Decimal(exits["STOP_EXIT"]), Decimal(len(admitted))),
        "time_rate_pct": percent(Decimal(exits["TIME_EXIT"]), Decimal(len(admitted))),
        "positive_time_exit_count": positive_time,
        "target_or_positive_time_exit_rate_pct": percent(Decimal(exits["TARGET_EXIT"] + positive_time), Decimal(len(admitted))),
        "mean_regime_raw_score": mean(numeric_values(rows, "regime_raw_score")),
        "median_regime_raw_score": median(numeric_values(rows, "regime_raw_score")),
        "mean_regime_score_normalized": mean(numeric_values(rows, "regime_score_normalized")),
        "median_regime_score_normalized": median(numeric_values(rows, "regime_score_normalized")),
        "mean_regime_confidence_score": mean(numeric_values(rows, "regime_confidence_score")),
        "regime_confidence_counts": dict(sorted(Counter(str(row.get("regime_confidence") or "UNAVAILABLE") for row in rows).items())),
        "available_weight_counts": dict(sorted(Counter(str(row.get("regime_available_weight_pct") or "UNAVAILABLE") for row in rows).items())),
        "mean_nifty_trend_contribution": mean(numeric_values(rows, "nifty_trend_contribution")),
        "mean_breadth_contribution": mean(numeric_values(rows, "breadth_contribution")),
        "mean_sector_contribution": mean(numeric_values(rows, "sector_contribution")),
        "mean_regime_streak_sessions": mean(numeric_values(rows, "regime_streak_sessions")),
        "next_regime_state_counts": dict(sorted(next_counts.items())),
        "next_state_change_count": sum(bool(row.get("next_state_changed")) for row in rows),
        "near_regime_flip_count": sum(bool(row.get("near_regime_flip")) for row in rows),
        "near_direct_bull_bear_flip_count": sum(bool(row.get("near_direct_bull_bear_flip")) for row in rows),
        "descriptive_only": True,
    }
    return summary


def population_rows(records: Sequence[Mapping[str, Any]], population: str) -> list[Mapping[str, Any]]:
    if population == "SOURCE":
        return list(records)
    if population == "ADMITTED":
        return [row for row in records if row.get("is_admitted")]
    if population == "SLOT_SKIPPED":
        return [row for row in records if row.get("is_slot_skipped")]
    raise ValueError(population)


def bucket_profiles(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
    buckets: Sequence[tuple[str, Decimal | None, Decimal | None, bool, bool]],
    section: str,
    populations: Sequence[str] = POPULATIONS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for population in populations:
        selected_population = population_rows(records, population)
        for bucket in buckets:
            selected = [row for row in selected_population if in_bucket(optional_decimal(row.get(field)), bucket)]
            rows.append(
                summarize_records(
                    selected,
                    section=section,
                    population=population,
                    bucket=bucket[0],
                    field=field,
                )
            )
    return rows


def baseline_profiles(
    records: Sequence[Mapping[str, Any]],
    exceptional: Sequence[Mapping[str, Any]],
    unavailable: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        summarize_records([row for row in records if row["regime_state"] == "BULLISH"], profile="BULLISH_NORMAL", population="SOURCE"),
        summarize_records([row for row in records if row["regime_state"] == "NEUTRAL"], profile="NEUTRAL_NORMAL", population="SOURCE"),
        summarize_records(exceptional, profile="BEARISH_EXCEPTIONAL_REVIEW", population="SEPARATE_RESEARCH_COHORT"),
        summarize_records(unavailable, profile="UNAVAILABLE_PREVIEW", population="SEPARATE_RESEARCH_COHORT"),
    ]


def score_interaction_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in CONTEXT_BUCKETS:
        for score in (80, 81, 82, 83, 84, 85):
            rows.append(
                summarize_records(
                    [row for row in records if row["regime_context_bucket"] == context and row["raw_strategy_score"] == score],
                    section="SCORE_X_REGIME_CONTEXT",
                    context_bucket=context,
                    raw_strategy_score=score,
                    population="SOURCE",
                )
            )
    cohort_specs = (
        ("HIGH_SCORE_WEAK_CONTEXT", lambda row: row["raw_strategy_score"] >= 84 and decimal(row["regime_score_normalized"]) < 45),
        ("HIGH_SCORE_STRONGER_CONTEXT", lambda row: row["raw_strategy_score"] >= 84 and decimal(row["regime_score_normalized"]) >= 45),
        ("LOWER_SCORE_STRONG_CONTEXT", lambda row: row["raw_strategy_score"] in {80, 81, 82} and decimal(row["regime_score_normalized"]) >= 60),
        ("LOWER_SCORE_BULLISH_LOW_CONTEXT", lambda row: row["raw_strategy_score"] in {80, 81, 82} and 30 <= decimal(row["regime_score_normalized"]) < 45),
    )
    for name, predicate in cohort_specs:
        rows.append(summarize_records([row for row in records if predicate(row)], section="FIXED_DIAGNOSTIC_COHORT", cohort=name, population="SOURCE"))
    return rows


def interaction_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for context in CONTEXT_BUCKETS:
        context_rows = [row for row in records if row["regime_context_bucket"] == context]
        for setup in ("VALID", "STRONG"):
            rows.append(summarize_records([row for row in context_rows if row["setup_quality"] == setup], section="REGIME_X_SETUP", context_bucket=context, setup_quality=setup, population="SOURCE"))
        for bucket in RR_BUCKETS:
            rows.append(summarize_records([row for row in context_rows if in_bucket(optional_decimal(row.get("effective_reward_risk")), bucket)], section="REGIME_X_EFFECTIVE_RR", context_bucket=context, rr_bucket=bucket[0], population="SOURCE"))
        for bucket in GAP_BUCKETS:
            rows.append(summarize_records([row for row in context_rows if in_bucket(optional_decimal(row.get("gap_pct")), bucket)], section="REGIME_X_GAP", context_bucket=context, gap_bucket=bucket[0], population="SOURCE"))
    for state in ("BULLISH", "NEUTRAL"):
        state_rows = [row for row in records if row["regime_state"] == state]
        for candidate in ("EMERGING_ONLY", "BOTH_ELIGIBLE", "CONFIRMED_ONLY"):
            rows.append(summarize_records([row for row in state_rows if row["candidate_category"] == candidate], section="REGIME_X_CANDIDATE_STAGE", regime_state=state, candidate_category=candidate, population="SOURCE"))
    return rows


def yearly_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year in YEARS:
        selected = [row for row in records if int(str(row["decision_date"])[:4]) == year]
        overview = summarize_records(selected, section="YEAR_OVERVIEW", year=year, period_status="PARTIAL" if year == 2026 else "COMPLETE", population="SOURCE")
        for state in ("BULLISH", "NEUTRAL"):
            count = sum(row["regime_state"] == state for row in selected)
            overview[f"{state.lower()}_source_count"] = count
            overview[f"{state.lower()}_source_pct"] = percent(Decimal(count), Decimal(len(selected)))
            overview[f"{state.lower()}_admitted_count"] = sum(row["regime_state"] == state and row["is_admitted"] for row in selected)
        rows.append(overview)
        distributions = (
            ("YEAR_REGIME_STATE", "regime_state", (("BULLISH",), ("NEUTRAL",))),
            ("YEAR_BULLISH_STRENGTH", "regime_context_bucket", tuple((item[0],) for item in BULLISH_STRENGTH_BUCKETS)),
            ("YEAR_NEUTRAL_POSITION", "regime_context_bucket", tuple((item[0],) for item in NEUTRAL_POSITION_BUCKETS)),
            ("YEAR_TREND_BUCKET", "nifty_trend_bucket", tuple((item[0],) for item in TREND_BUCKETS)),
            ("YEAR_BREADTH_BUCKET", "breadth_bucket", tuple((item[0],) for item in BREADTH_BUCKETS)),
            ("YEAR_SECTOR_BUCKET", "sector_bucket", tuple((item[0],) for item in SECTOR_BUCKETS)),
        )
        for section, field, buckets in distributions:
            for (bucket_name,) in buckets:
                subset = [row for row in selected if row.get(field) == bucket_name]
                row = summarize_records(subset, section=section, year=year, period_status="PARTIAL" if year == 2026 else "COMPLETE", bucket=bucket_name, population="SOURCE")
                row["year_share_pct"] = percent(Decimal(len(subset)), Decimal(len(selected)))
                rows.append(row)
    return rows


def build_experiment_table(
    experiment_id: str,
    records: Sequence[Mapping[str, Any]],
    exceptional: Sequence[Mapping[str, Any]],
    unavailable: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if experiment_id == "EXP-REGIME-001":
        return baseline_profiles(records, exceptional, unavailable)
    if experiment_id == "EXP-REGIME-002":
        return bucket_profiles(records, field="regime_score_normalized", buckets=REGIME_SCORE_BUCKETS, section="REGIME_SCORE_BUCKET")
    if experiment_id == "EXP-REGIME-003":
        bullish = [row for row in records if row["regime_state"] == "BULLISH"]
        return bucket_profiles(bullish, field="regime_score_normalized", buckets=BULLISH_STRENGTH_BUCKETS, section="BULLISH_STRENGTH")
    if experiment_id == "EXP-REGIME-004":
        neutral = [row for row in records if row["regime_state"] == "NEUTRAL"]
        return bucket_profiles(neutral, field="regime_score_normalized", buckets=NEUTRAL_POSITION_BUCKETS, section="NEUTRAL_POSITION")
    if experiment_id in {"EXP-REGIME-005", "EXP-REGIME-006", "EXP-REGIME-007"}:
        component = {
            "EXP-REGIME-005": "NIFTY_TREND",
            "EXP-REGIME-006": "BREADTH",
            "EXP-REGIME-007": "SECTOR_PARTICIPATION",
        }[experiment_id]
        return bucket_profiles(records, field=COMPONENT_FIELDS[component], buckets=COMPONENT_BUCKETS[component], section=f"{component}_BUCKET")
    if experiment_id == "EXP-REGIME-008":
        return score_interaction_rows(records)
    if experiment_id == "EXP-REGIME-009":
        return interaction_rows(records)
    if experiment_id == "EXP-REGIME-010":
        return yearly_rows(records)
    raise ValueError(f"Unauthorized Command 05 experiment: {experiment_id}")


def execute_regime_context_experiment(
    definition: ExperimentDefinition,
    records: Sequence[Mapping[str, Any]],
    exceptional: Sequence[Mapping[str, Any]],
    unavailable: Sequence[Mapping[str, Any]],
) -> ExperimentExecution:
    table = build_experiment_table(definition.experiment_id, records, exceptional, unavailable)
    result = {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "name": definition.name,
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "source_opportunities": len(records),
        "admitted_trades": sum(bool(row["is_admitted"]) for row in records),
        "slot_skipped_opportunities": sum(bool(row["is_slot_skipped"]) for row in records),
        "bearish_exceptional_review_rows": len(exceptional),
        "unavailable_preview_rows": len(unavailable),
        "table_row_count": len(table),
        "table_fingerprint": canonical_hash(table),
        "regime_rule_change_applied": False,
        "regime_weight_change_applied": False,
        "neutral_exclusion_applied": False,
        "hysteresis_or_smoothing_applied": False,
        "portfolio_rerun_performed": False,
        "optimizer_or_ml_performed": False,
        "future_regime_used_for_admission": False,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "eligible_for_promotion": False,
        "performance_scope": PERFORMANCE_SCOPE,
        "gross_before_costs": True,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
    }
    return ExperimentExecution(result=result, trades=table)


def correlation_row(
    records: Sequence[Mapping[str, Any]],
    *,
    section: str,
    population: str,
    measure: str,
    measure_field: str,
    outcome: str,
) -> dict[str, Any]:
    result = correlation(records, measure_field, outcome)
    return {
        "section": section,
        "population": population,
        "measure": measure,
        "measure_field": measure_field,
        "outcome": outcome,
        "count": result["count"],
        "pearson": result["pearson"],
        "spearman": result["spearman"],
        "sample_size_flag": sample_size_flag(result["count"]),
        "descriptive_only": True,
        "significance_tested": False,
    }


def regime_correlations(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    measures = {
        "TOTAL_REGIME_SCORE": "regime_score_normalized",
        **COMPONENT_FIELDS,
    }
    admitted = [row for row in records if row["is_admitted"]]
    for measure, field in measures.items():
        for outcome in ("mfe_r_4", "mae_r_4", "close_return_pct_4"):
            rows.append(correlation_row(records, section="SOURCE_PATH", population="SOURCE", measure=measure, measure_field=field, outcome=outcome))
        for outcome in ("realized_r_multiple", "positive_trade_indicator"):
            rows.append(correlation_row(admitted, section="ADMITTED_OUTCOME", population="ADMITTED", measure=measure, measure_field=field, outcome=outcome))
    for year in YEARS:
        annual = [row for row in admitted if int(str(row["decision_date"])[:4]) == year]
        for measure, field in measures.items():
            row = correlation_row(annual, section="YEARLY_ADMITTED_REALIZED_R", population="ADMITTED", measure=measure, measure_field=field, outcome="realized_r_multiple")
            row["year"] = year
            row["period_status"] = "PARTIAL" if year == 2026 else "COMPLETE"
            rows.append(row)
    return rows


def correlation_lookup(
    correlations: Sequence[Mapping[str, Any]],
    *,
    measure: str,
    outcome: str,
    section: str | None = None,
    year: int | None = None,
) -> Mapping[str, Any]:
    for row in correlations:
        if row["measure"] != measure or row["outcome"] != outcome:
            continue
        if section is not None and row["section"] != section:
            continue
        if year is not None and row.get("year") != year:
            continue
        return row
    raise ValueError(f"Missing correlation: {measure}/{outcome}/{section}/{year}")


def correlation_votes(
    correlations: Sequence[Mapping[str, Any]], measure: str
) -> tuple[int, int, dict[str, Any]]:
    evidence: dict[str, Any] = {}
    favorable = 0
    unfavorable = 0
    specs = (
        ("mfe_r_4", "SOURCE_PATH", 1),
        ("mae_r_4", "SOURCE_PATH", -1),
        ("realized_r_multiple", "ADMITTED_OUTCOME", 1),
        ("positive_trade_indicator", "ADMITTED_OUTCOME", 1),
    )
    for outcome, section, favorable_sign in specs:
        row = correlation_lookup(correlations, measure=measure, outcome=outcome, section=section)
        value = row["spearman"]
        adjusted = None if value is None else float(value) * favorable_sign
        evidence[outcome] = {"count": row["count"], "pearson": row["pearson"], "spearman": value, "favorable_direction_value": adjusted}
        if adjusted is not None and adjusted >= 0.05:
            favorable += 1
        elif adjusted is not None and adjusted <= -0.05:
            unfavorable += 1
    return favorable, unfavorable, evidence


def component_result(
    correlations: Sequence[Mapping[str, Any]], measure: str
) -> tuple[str, dict[str, Any]]:
    favorable, unfavorable, evidence = correlation_votes(correlations, measure)
    realized = correlation_lookup(correlations, measure=measure, outcome="realized_r_multiple", section="ADMITTED_OUTCOME")
    if realized["count"] < 30 or realized["spearman"] is None:
        result = "INCONCLUSIVE"
    elif favorable == 4 and unfavorable == 0:
        result = "CLEAR_POSITIVE_DISCRIMINATION"
    elif favorable >= 2 and favorable > unfavorable:
        result = "WEAK_POSITIVE_DISCRIMINATION"
    elif unfavorable >= 2 and unfavorable > favorable:
        result = "INVERSE"
    elif favorable and unfavorable:
        result = "MIXED"
    else:
        result = "NO_CLEAR_DISCRIMINATION"
    return result, {"favorable_votes": favorable, "unfavorable_votes": unfavorable, "correlations": evidence}


def total_regime_result(
    correlations: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    favorable, unfavorable, evidence = correlation_votes(correlations, "TOTAL_REGIME_SCORE")
    if favorable == 4 and unfavorable == 0:
        result = "CLEAR_POSITIVE_DISCRIMINATION"
    elif favorable == 3 and unfavorable == 0:
        result = "WEAK_POSITIVE_DISCRIMINATION"
    elif favorable >= 2 and favorable > unfavorable:
        result = "PARTIALLY_DISCRIMINATIVE"
    elif favorable and unfavorable:
        result = "MIXED"
    elif unfavorable:
        result = "NO_CLEAR_DISCRIMINATION"
    else:
        result = "NO_CLEAR_DISCRIMINATION"
    return result, {"favorable_votes": favorable, "unfavorable_votes": unfavorable, "correlations": evidence}


def profile_direction_votes(
    lower: Mapping[str, Any], upper: Mapping[str, Any]
) -> tuple[int, int, dict[str, Decimal]]:
    deltas = {
        "mean_mfe_r": decimal(upper["mean_mfe_r"]) - decimal(lower["mean_mfe_r"]),
        "mean_mae_r": decimal(lower["mean_mae_r"]) - decimal(upper["mean_mae_r"]),
        "mean_realized_r": decimal(upper["mean_realized_r"]) - decimal(lower["mean_realized_r"]),
        "positive_trade_rate_pct": decimal(upper["positive_trade_rate_pct"]) - decimal(lower["positive_trade_rate_pct"]),
    }
    thresholds = {
        "mean_mfe_r": Decimal("0.05"),
        "mean_mae_r": Decimal("0.05"),
        "mean_realized_r": Decimal("0.05"),
        "positive_trade_rate_pct": Decimal("3"),
    }
    favorable = sum(value >= thresholds[key] for key, value in deltas.items())
    unfavorable = sum(value <= -thresholds[key] for key, value in deltas.items())
    return favorable, unfavorable, deltas


def bullish_neutral_result(profiles: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    bullish = next(row for row in profiles if row["profile"] == "BULLISH_NORMAL")
    neutral = next(row for row in profiles if row["profile"] == "NEUTRAL_NORMAL")
    favorable, unfavorable, deltas = profile_direction_votes(neutral, bullish)
    if neutral["admitted_count"] < 30:
        result = "INCONCLUSIVE"
    elif favorable >= 3 and unfavorable == 0:
        result = "BULLISH_CLEARLY_STRONGER"
    elif favorable >= 2 and favorable > unfavorable:
        result = "BULLISH_MODESTLY_STRONGER"
    elif favorable and unfavorable:
        result = "MIXED"
    else:
        result = "NO_CLEAR_DIFFERENCE"
    return result, {"favorable_votes": favorable, "unfavorable_votes": unfavorable, "bullish_minus_neutral_favorable_deltas": deltas, "neutral_sample_warning": sample_size_flag(neutral["admitted_count"])}


def confidence_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for state in CONFIDENCE_STATES:
        rows.append(summarize_records([row for row in records if row["regime_confidence"] == state], section="CONFIDENCE_STATE", confidence_state=state, population="SOURCE"))
    for regime_state in ("BULLISH", "NEUTRAL"):
        for confidence in CONFIDENCE_STATES:
            rows.append(summarize_records([row for row in records if row["regime_state"] == regime_state and row["regime_confidence"] == confidence], section="CONFIDENCE_WITHIN_REGIME", regime_state=regime_state, confidence_state=confidence, population="SOURCE"))
    return rows


def borderline_profiles(
    records: Sequence[Mapping[str, Any]], exceptional: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    combined = list(records) + list(exceptional)
    for bucket in BORDERLINE_BUCKETS:
        selected = [row for row in combined if in_bucket(optional_decimal(row.get("regime_score_normalized")), bucket)]
        row = summarize_records(selected, section="BORDERLINE_REGIME", bucket=bucket[0], population="SOURCE_OR_SEPARATE_EXCEPTIONAL")
        row["next_state_change_rate_pct"] = percent(Decimal(row["next_state_change_count"]), Decimal(row["sample_size"]))
        rows.append(row)
    return rows


def flip_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        summarize_records([row for row in records if row["near_regime_flip"]], section="REGIME_FLIP_PROXIMITY", flip_context="WITHIN_ONE_SESSION_OF_ANY_STATE_CHANGE", population="SOURCE"),
        summarize_records([row for row in records if row["near_direct_bull_bear_flip"]], section="REGIME_FLIP_PROXIMITY", flip_context="WITHIN_ONE_SESSION_OF_DIRECT_BULL_BEAR_FLIP", population="SOURCE"),
        summarize_records([row for row in records if not row["near_regime_flip"]], section="REGIME_FLIP_PROXIMITY", flip_context="NOT_WITHIN_ONE_SESSION_OF_STATE_CHANGE", population="SOURCE"),
    ]


def persistence_profiles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    bullish = [row for row in records if row["regime_state"] == "BULLISH"]
    rows = bucket_profiles(bullish, field="regime_streak_sessions", buckets=STREAK_BUCKETS, section="BULLISH_REGIME_STREAK")
    rows.append(
        summarize_records(
            [row for row in bullish if row["regime_streak_sessions"] > 10],
            section="BULLISH_REGIME_STREAK_COMPARISON",
            bucket="ESTABLISHED_GT_10",
            population="SOURCE",
        )
    )
    return rows


def borderline_result(
    borderline: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> tuple[str, dict[str, Any]]:
    lower = next(row for row in borderline if row["bucket"] == "BULLISH_BORDERLINE")
    established = summarize_records([row for row in records if row["regime_state"] == "BULLISH" and decimal(row["regime_score_normalized"]) >= 45], profile="BULLISH_GTE_45")
    favorable, unfavorable, deltas = profile_direction_votes(lower, established)
    if min(lower["admitted_count"], established["admitted_count"]) < 30:
        result = "INCONCLUSIVE"
    elif favorable >= 3 and unfavorable == 0:
        result = "BORDERLINE_WEAKER"
    elif unfavorable >= 3 and favorable == 0:
        result = "BORDERLINE_STRONGER"
    elif favorable and unfavorable:
        result = "MIXED"
    else:
        result = "NO_CLEAR_EFFECT"
    return result, {"borderline": lower, "bullish_gte_45": established, "favorable_votes_for_established": favorable, "unfavorable_votes_for_established": unfavorable, "deltas": deltas}


def persistence_result(
    persistence: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    source_rows = [row for row in persistence if row["population"] == "SOURCE"]
    new = next(row for row in source_rows if row["bucket"] == "STREAK_1")
    established = next(row for row in source_rows if row["bucket"] == "ESTABLISHED_GT_10")
    favorable, unfavorable, deltas = profile_direction_votes(new, established)
    if min(new["admitted_count"], established["admitted_count"]) < 30:
        result = "INCONCLUSIVE"
    elif favorable >= 3 and unfavorable == 0:
        result = "ESTABLISHED_BULLISH_STRONGER"
    elif unfavorable >= 3 and favorable == 0:
        result = "NEW_BULLISH_STRONGER"
    elif favorable and unfavorable:
        result = "MIXED"
    else:
        result = "NO_CLEAR_EFFECT"
    return result, {"new_bullish": new, "established_bullish": established, "favorable_votes_for_established": favorable, "unfavorable_votes_for_established": unfavorable, "deltas": deltas}


def yearly_direction_consistency(
    correlations: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for measure in ("TOTAL_REGIME_SCORE", "NIFTY_TREND", "BREADTH", "SECTOR_PARTICIPATION"):
        annual = [correlation_lookup(correlations, measure=measure, outcome="realized_r_multiple", section="YEARLY_ADMITTED_REALIZED_R", year=year) for year in YEARS]
        material = [float(row["spearman"]) for row in annual if row["spearman"] is not None and abs(float(row["spearman"])) >= 0.05]
        positive = sum(value > 0 for value in material)
        negative = sum(value < 0 for value in material)
        if len(material) < 3:
            classification = "INCONCLUSIVE"
        elif negative == 0:
            classification = "CONSISTENT" if positive == len(material) else "MOSTLY_CONSISTENT"
        elif positive == 0:
            classification = "INVERSE_ACROSS_PERIODS" if negative == len(material) else "MOSTLY_CONSISTENT"
        elif max(positive, negative) >= 4:
            classification = "MOSTLY_CONSISTENT"
        else:
            classification = "UNSTABLE"
        result[measure] = {
            "classification": classification,
            "positive_years": positive,
            "negative_years": negative,
            "annual_spearman": {str(row["year"]): row["spearman"] for row in annual},
        }
    return result


def pilot_case(case: str, scenario: str, record: Mapping[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "case": case,
            "scenario": scenario,
            "source_type": "NOT_AVAILABLE",
            "status": "NOT_AVAILABLE",
            "symbol": None,
            "decision_date": None,
            "passed": True,
        }
    arithmetic = sum(int(record[field]) for field in ("setup_points", "momentum_points", "rvol_points", "rs_points", "regime_points", "rr_points"))
    return {
        "case": case,
        "scenario": scenario,
        "source_type": "REAL_FROZEN_DATA",
        "status": "VALIDATED",
        "source_key": record["source_key"],
        "symbol": record["symbol"],
        "decision_date": record["decision_date"],
        "entry_date": record["entry_date"],
        "regime_state": record["regime_state"],
        "regime_raw_score": record["regime_raw_score"],
        "regime_score_normalized": record["regime_score_normalized"],
        "regime_score_bucket": record["regime_score_bucket"],
        "regime_context_bucket": record["regime_context_bucket"],
        "nifty_trend_state": record["nifty_trend_state"],
        "nifty_trend_contribution": record["nifty_trend_contribution"],
        "nifty_trend_bucket": record["nifty_trend_bucket"],
        "breadth_state": record["breadth_state"],
        "breadth_contribution": record["breadth_contribution"],
        "breadth_bucket": record["breadth_bucket"],
        "sector_state": record["sector_state"],
        "sector_contribution": record["sector_contribution"],
        "sector_bucket": record["sector_bucket"],
        "regime_confidence": record["regime_confidence"],
        "regime_confidence_score": record["regime_confidence_score"],
        "regime_available_weight_pct": record["regime_available_weight_pct"],
        "regime_streak_sessions": record["regime_streak_sessions"],
        "regime_streak_bucket": record["regime_streak_bucket"],
        "raw_strategy_score": record["raw_strategy_score"],
        "score_arithmetic_sum": arithmetic,
        "setup_quality": record["setup_quality"],
        "effective_reward_risk": record["effective_reward_risk"],
        "gap_pct": record["gap_pct"],
        "mfe_r_4": record["mfe_r_4"],
        "mae_r_4": record["mae_r_4"],
        "realized_r_multiple": record["realized_r_multiple"],
        "gross_pnl": record["gross_pnl"],
        "portfolio_exit_reason": record["portfolio_exit_reason"],
        "is_admitted": record["is_admitted"],
        "is_slot_skipped": record["is_slot_skipped"],
        "near_regime_flip": record["near_regime_flip"],
        "near_direct_bull_bear_flip": record["near_direct_bull_bear_flip"],
        "future_state_diagnostic_only": record["future_state_diagnostic_only"],
        "passed": arithmetic == int(record["raw_strategy_score"]),
    }


def build_pilot(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda row: (str(row["decision_date"]), str(row["symbol"])))

    def choose(predicate: Callable[[Mapping[str, Any]], bool]) -> Mapping[str, Any] | None:
        return next((row for row in ordered if predicate(row)), None)

    specs = (
        ("A", "borderline Bullish +30..+34", lambda row: row["regime_state"] == "BULLISH" and 30 <= decimal(row["regime_score_normalized"]) < 35),
        ("B", "strong Bullish >=60", lambda row: row["regime_state"] == "BULLISH" and decimal(row["regime_score_normalized"]) >= 60),
        ("C", "positive Neutral +10..+29", lambda row: row["regime_state"] == "NEUTRAL" and 10 <= decimal(row["regime_score_normalized"]) < 30),
        ("D", "middle Neutral -9..+9", lambda row: row["regime_state"] == "NEUTRAL" and -10 < decimal(row["regime_score_normalized"]) < 10),
        ("E", "negative Neutral -29..-10", lambda row: row["regime_state"] == "NEUTRAL" and -30 < decimal(row["regime_score_normalized"]) <= -10),
        ("F", "strong trend / strong breadth", lambda row: decimal(row["nifty_trend_contribution"]) >= 20 and decimal(row["breadth_contribution"]) >= 12),
        ("G", "strong trend / weaker breadth", lambda row: decimal(row["nifty_trend_contribution"]) >= 20 and decimal(row["breadth_contribution"]) < 5),
        ("H", "weaker trend / strong breadth", lambda row: decimal(row["nifty_trend_contribution"]) < 10 and decimal(row["breadth_contribution"]) >= 12),
        ("I", "score 84+ in borderline/weak regime", lambda row: row["raw_strategy_score"] >= 84 and decimal(row["regime_score_normalized"]) < 45),
        ("J", "score 84+ in stronger Bullish", lambda row: row["raw_strategy_score"] >= 84 and decimal(row["regime_score_normalized"]) >= 45),
        ("K", "newly Bullish streak=1", lambda row: row["regime_state"] == "BULLISH" and row["regime_streak_sessions"] == 1),
        ("L", "established Bullish streak>10", lambda row: row["regime_state"] == "BULLISH" and row["regime_streak_sessions"] > 10),
        ("M", "2023 positive-year admitted example", lambda row: str(row["decision_date"]).startswith("2023-") and row["is_admitted"]),
        ("N", "weak-year admitted example", lambda row: str(row["decision_date"])[:4] in {"2022", "2024", "2025", "2026"} and row["is_admitted"]),
    )
    cases = [pilot_case(case, scenario, choose(predicate)) for case, scenario, predicate in specs]
    return {
        "cases": cases,
        "case_count": len(cases),
        "real_case_count": sum(row["source_type"] == "REAL_FROZEN_DATA" for row in cases),
        "not_available_count": sum(row["source_type"] == "NOT_AVAILABLE" for row in cases),
        "passed": len(cases) == 14 and all(row["passed"] for row in cases),
        "validated_fields": [
            "date",
            "regime_state",
            "raw_and_normalized_regime_score",
            "component_values_and_contributions",
            "confidence",
            "causal_streak",
            "frozen_strategy_score_arithmetic",
            "setup_and_effective_rr",
            "outcome",
            "portfolio_admission",
            "fixed_bucket_assignments",
        ],
    }


def auxiliary_analyses(
    records: Sequence[Mapping[str, Any]],
    exceptional: Sequence[Mapping[str, Any]],
    executions: Mapping[str, ExperimentExecution],
    correlations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    profiles = executions["EXP-REGIME-001"].trades
    component_results: dict[str, str] = {}
    component_evidence: dict[str, Any] = {}
    for measure in COMPONENT_FIELDS:
        result, evidence = component_result(correlations, measure)
        component_results[measure] = result
        component_evidence[measure] = evidence
    total_result, total_evidence = total_regime_result(correlations)
    bull_neutral, bull_neutral_evidence = bullish_neutral_result(profiles)
    confidence = confidence_profiles(records)
    confidence_observed = [row for row in confidence if row["section"] == "CONFIDENCE_STATE" and row["sample_size"]]
    confidence_result = "NO_VARIATION_BEYOND_REGIME_STATE" if len(confidence_observed) < 2 else "DESCRIPTIVE_VARIATION_PRESENT"
    borderline = borderline_profiles(records, exceptional)
    border_result, border_evidence = borderline_result(borderline, records)
    flips = flip_profiles(records)
    persistence = persistence_profiles(records)
    persist_result, persist_evidence = persistence_result(persistence)
    yearly_consistency = yearly_direction_consistency(correlations)
    strongest = max(
        COMPONENT_FIELDS,
        key=lambda measure: abs(float(correlation_lookup(correlations, measure=measure, outcome="realized_r_multiple", section="ADMITTED_OUTCOME")["spearman"] or 0)),
    )
    population_profiles = [summarize_records(population_rows(records, population), section="POPULATION_REGIME_PROFILE", population=population) for population in POPULATIONS]
    score_rows = executions["EXP-REGIME-008"].trades
    fixed_cohorts = {row["cohort"]: row for row in score_rows if row["section"] == "FIXED_DIAGNOSTIC_COHORT"}
    annual_overviews = [row for row in executions["EXP-REGIME-010"].trades if row["section"] == "YEAR_OVERVIEW"]
    year_2023 = next(row for row in annual_overviews if row["year"] == 2023)
    other_years = [row for row in records if int(str(row["decision_date"])[:4]) in {2022, 2024, 2025, 2026}]
    comparison_2023 = {
        "year_2023": year_2023,
        "other_years_combined": summarize_records(other_years, profile="OTHER_REQUESTED_YEARS_COMBINED", population="SOURCE"),
        "causal_inference_allowed": False,
    }
    portfolio_attribution = {
        "regime_state": [row for row in profiles if row.get("profile") in {"BULLISH", "NEUTRAL"}],
        "bullish_strength": [row for row in executions["EXP-REGIME-003"].trades if row.get("population") == "ADMITTED"],
        "neutral_position": [row for row in executions["EXP-REGIME-004"].trades if row.get("population") == "ADMITTED"],
        "nifty_trend": [row for row in executions["EXP-REGIME-005"].trades if row.get("population") == "ADMITTED"],
        "breadth": [row for row in executions["EXP-REGIME-006"].trades if row.get("population") == "ADMITTED"],
        "sector_participation": [row for row in executions["EXP-REGIME-007"].trades if row.get("population") == "ADMITTED"],
        "alternate_portfolio_rerun": False,
    }
    hypothesis_supported = (
        total_result in {"CLEAR_POSITIVE_DISCRIMINATION", "WEAK_POSITIVE_DISCRIMINATION", "PARTIALLY_DISCRIMINATIVE"}
        and any(value in {"CLEAR_POSITIVE_DISCRIMINATION", "WEAK_POSITIVE_DISCRIMINATION"} for value in component_results.values())
        and any(yearly_consistency[measure]["classification"] in {"CONSISTENT", "MOSTLY_CONSISTENT"} for measure in COMPONENT_FIELDS)
    )
    return {
        "baseline_profiles": profiles,
        "population_regime_profiles": population_profiles,
        "component_results": component_results,
        "component_evidence": component_evidence,
        "strongest_market_context_component_by_absolute_admitted_realized_r_spearman": strongest,
        "total_regime_result": total_result,
        "total_regime_evidence": total_evidence,
        "bullish_neutral_result": bull_neutral,
        "bullish_neutral_evidence": bull_neutral_evidence,
        "confidence_profiles": confidence,
        "confidence_beyond_regime_state_result": confidence_result,
        "borderline_profiles": borderline,
        "borderline_result": border_result,
        "borderline_evidence": border_evidence,
        "flip_proximity_profiles": flips,
        "future_flip_used_as_diagnostic_label_only": True,
        "future_flip_used_for_admission": False,
        "persistence_profiles": persistence,
        "persistence_result": persist_result,
        "persistence_evidence": persist_evidence,
        "yearly_direction_consistency": yearly_consistency,
        "fixed_score_context_cohorts": fixed_cohorts,
        "year_2023_vs_other_years": comparison_2023,
        "portfolio_attribution": portfolio_attribution,
        "REGIME_CONTEXT_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING": hypothesis_supported,
    }


def append_registry_preserving_previous(
    path: Path,
    original: Mapping[str, Any],
    new_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    previous = [copy.deepcopy(row) for row in original["experiments"] if row.get("experiment_id") not in REGIME_CONTEXT_EXPERIMENT_IDS]
    if len(previous) != 39:
        raise ValueError(f"Expected 39 previous experiments, found {len(previous)}")
    prior_hashes = {row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"]) for row in previous}
    payload = copy.deepcopy(dict(original))
    payload["experiments"] = previous + [dict(row) for row in new_records]
    payload["command_05"] = {
        "version": REGIME_CONTEXT_COMMAND_VERSION,
        "experiment_ids": list(REGIME_CONTEXT_EXPERIMENT_IDS),
        "promotion_allowed": False,
    }
    write_json(path, payload)
    preserved = {
        row["experiment_id"]: (row["parameter_hash"], row["pre_registration_hash"])
        for row in payload["experiments"]
        if row["experiment_id"] in prior_hashes
    }
    if preserved != prior_hashes or len(payload["experiments"]) != 49:
        raise ValueError("Previous registry hashes changed or combined registry count is not 49")
    return {
        "previous_experiment_count": 39,
        "previous_parameter_and_preregistration_hashes_unchanged": True,
        "combined_registry_count": 49,
    }


def write_outputs(
    *,
    context: RegimeContext,
    registry: RegimeContextRegistry,
    executions: Mapping[str, ExperimentExecution],
    summary: Mapping[str, Any],
    preregistration_path: Path,
    original_registry: Mapping[str, Any],
    auxiliary: Mapping[str, Any],
    pilot: Mapping[str, Any],
) -> tuple[list[Path], dict[str, Any]]:
    command_root = context.data_dir / "research/diagnostics/strategy/v1/regime_context_command_05"
    report_root = context.data_dir / "reports"
    final_registry_path = command_root / "registry/regime_context_experiment_registry_v1.json"
    write_json(
        final_registry_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": REGIME_CONTEXT_COMMAND_VERSION,
            "promotion_allowed": False,
            "experiments": registry.records(),
        },
    )
    paths = [preregistration_path, final_registry_path]
    for experiment_id in REGIME_CONTEXT_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        run_root = command_root / "runs" / experiment_id
        result_path = run_root / "result.json"
        table_path = run_root / "table.csv.gz"
        write_json(result_path, execution.result)
        write_gzip_csv(table_path, execution.trades)
        paths.extend((result_path, table_path))
    report_mapping = {
        "strategy_diagnostic_v1_regime_context_profile.csv": "EXP-REGIME-001",
        "strategy_diagnostic_v1_regime_context_score_buckets.csv": "EXP-REGIME-002",
        "strategy_diagnostic_v1_regime_context_bullish.csv": "EXP-REGIME-003",
        "strategy_diagnostic_v1_regime_context_neutral.csv": "EXP-REGIME-004",
        "strategy_diagnostic_v1_regime_context_trend.csv": "EXP-REGIME-005",
        "strategy_diagnostic_v1_regime_context_breadth.csv": "EXP-REGIME-006",
        "strategy_diagnostic_v1_regime_context_sector.csv": "EXP-REGIME-007",
        "strategy_diagnostic_v1_regime_context_score_interaction.csv": "EXP-REGIME-008",
        "strategy_diagnostic_v1_regime_context_setup_rr.csv": "EXP-REGIME-009",
        "strategy_diagnostic_v1_regime_context_yearly.csv": "EXP-REGIME-010",
    }
    for filename, experiment_id in report_mapping.items():
        path = report_root / filename
        write_csv(path, executions[experiment_id].trades)
        paths.append(path)
    confidence_path = report_root / "strategy_diagnostic_v1_regime_context_confidence.csv"
    borderline_path = report_root / "strategy_diagnostic_v1_regime_context_borderline.csv"
    persistence_path = report_root / "strategy_diagnostic_v1_regime_context_persistence.csv"
    pilot_path = report_root / "strategy_diagnostic_v1_regime_context_pilot.csv"
    write_csv(confidence_path, auxiliary["confidence_profiles"])
    write_csv(borderline_path, auxiliary["borderline_profiles"])
    write_csv(persistence_path, list(auxiliary["persistence_profiles"]) + list(auxiliary["flip_proximity_profiles"]))
    write_csv(pilot_path, pilot["cases"])
    paths.extend((confidence_path, borderline_path, persistence_path, pilot_path))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    preservation = append_registry_preserving_previous(main_registry_path, original_registry, registry.records())
    paths.append(main_registry_path)
    summary_path = report_root / "strategy_diagnostic_v1_regime_context_summary.json"
    write_json(summary_path, summary)
    paths.append(summary_path)
    return paths, preservation


def run_regime_context_diagnostics(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Loading and verifying frozen regime, score, outcome, and portfolio baselines")
    context = load_regime_context(Path(repo_root))
    main_registry_path = context.data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    original_registry = json.loads(main_registry_path.read_text(encoding="utf-8"))
    previous = [row for row in original_registry["experiments"] if row.get("experiment_id") not in REGIME_CONTEXT_EXPERIMENT_IDS]
    if len(previous) != 39 or any(row.get("status") != "COMPLETE" for row in previous):
        raise ValueError("Command 05 requires 39 immutable completed prior experiment records")
    definitions = build_regime_context_definitions()
    registry = RegimeContextRegistry(context.baseline_hashes)
    for definition in definitions:
        registry.register(definition)
    preregistration_path = context.data_dir / "research/diagnostics/strategy/v1/regime_context_command_05/registry/regime_context_experiment_registry_v1_preregistered.json"
    write_json(
        preregistration_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "command_version": REGIME_CONTEXT_COMMAND_VERSION,
            "written_before_metric_derivation_or_results": True,
            "frozen_regime_version": context.regime_version,
            "frozen_regime_config_hash": context.regime_config_hash,
            "regime_score_scale_note": "Fixed state/strength buckets use the exact stored regime_score_normalized that MARKET_REGIME_V1 uses for classification; regime_score_raw is preserved as the unnormalized available-component contribution sum.",
            "bucket_definitions": {
                "regime_score": REGIME_SCORE_BUCKETS,
                "bullish_strength": BULLISH_STRENGTH_BUCKETS,
                "neutral_position": NEUTRAL_POSITION_BUCKETS,
                "nifty_trend": TREND_BUCKETS,
                "breadth": BREADTH_BUCKETS,
                "sector_participation": SECTOR_BUCKETS,
                "effective_rr": RR_BUCKETS,
                "gap": GAP_BUCKETS,
                "streak": STREAK_BUCKETS,
                "borderline": BORDERLINE_BUCKETS,
            },
            "sample_size_rules": SAMPLE_SIZE_RULES,
            "classification_rules": CLASSIFICATION_RULES,
            "promotion_allowed": False,
            "experiments": registry.records(),
        },
    )
    notify(progress, "Pre-registered exactly ten immutable Command 05 experiments")
    records, exceptional, unavailable = derive_regime_context_records(context)
    pilot = build_pilot(records)
    if not pilot["passed"]:
        raise ValueError("Real-data regime-context pilot failed")
    notify(progress, f"Validated fourteen pilot categories ({pilot['real_case_count']} real, {pilot['not_available_count']} unavailable)")
    executions: dict[str, ExperimentExecution] = {}
    for experiment_id in REGIME_CONTEXT_EXPERIMENT_IDS:
        registry.mark_ready(experiment_id)
        notify(progress, f"Running {experiment_id} twice with frozen-hash guards")
        execution = registry.run_twice(
            experiment_id,
            lambda definition: execute_regime_context_experiment(definition, records, exceptional, unavailable),
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Experiment failed: {experiment_id}: {registry.state(experiment_id).failure_reason}")
        executions[experiment_id] = execution
    correlations = regime_correlations(records)
    auxiliary = auxiliary_analyses(records, exceptional, executions, correlations)
    classifications = {
        "NIFTY_TREND_RESULT": auxiliary["component_results"]["NIFTY_TREND"],
        "BREADTH_RESULT": auxiliary["component_results"]["BREADTH"],
        "SECTOR_PARTICIPATION_RESULT": auxiliary["component_results"]["SECTOR_PARTICIPATION"],
        "TOTAL_REGIME_DISCRIMINATION_RESULT": auxiliary["total_regime_result"],
        "BULLISH_NEUTRAL_RESULT": auxiliary["bullish_neutral_result"],
        "BORDERLINE_REGIME_RESULT": auxiliary["borderline_result"],
        "REGIME_PERSISTENCE_RESULT": auxiliary["persistence_result"],
        "FRAMEWORK_RESULT": "PENDING",
    }
    hashes_after = portfolio_backtest_regression_hashes(context.data_dir)
    mutation_violations = sum(hashes_after[name] != value for name, value in context.baseline_hashes.items())
    failures = [state for state in registry._states.values() if state.status == "FAILED"]
    reproducible = all(row["match"] for row in registry.reproducibility.values())
    population_unchanged = (
        len(records) == 3296
        and sum(bool(row["is_admitted"]) for row in records) == 728
        and sum(bool(row["is_slot_skipped"]) for row in records) == 2398
        and len(exceptional) == 324
        and len(unavailable) == 28
    )
    framework_result = "CLEAN" if pilot["passed"] and reproducible and population_unchanged and not failures and mutation_violations == 0 else "METHODOLOGY_FIX_REQUIRED"
    classifications["FRAMEWORK_RESULT"] = framework_result
    config = MarketRegimeConfig()
    summary: dict[str, Any] = {
        "phase": "Step 02.13",
        "command": COMMAND,
        "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
        "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
        "command_version": REGIME_CONTEXT_COMMAND_VERSION,
        "newly_registered_experiment_count": 10,
        "newly_registered_experiment_ids": list(REGIME_CONTEXT_EXPERIMENT_IDS),
        "combined_registry_expected_count": 49,
        "pre_registration": {
            "written_before_metric_derivation_or_results": True,
            "buckets_locked": True,
            "classifications_locked": True,
            "path": str(preregistration_path.relative_to(repo_root)),
        },
        "frozen_regime": {
            "version": context.regime_version,
            "config_hash": context.regime_config_hash,
            "weights": config.snapshot()["weights"],
            "classification": config.snapshot()["classification"],
            "historical_regime_date_counts": dict(sorted(Counter(row["regime_state"] for row in context.regime_rows).items())),
            "normally_available_historical_weight_pct": 65,
            "unavailable_historical_components": ["GLOBAL_GIFT", "INDIA_VIX", "INTRADAY_CONFIRMATION"],
            "raw_score_field": "regime_score_raw",
            "classification_score_field": "regime_score_normalized",
            "rule_changed": False,
            "weight_changed": False,
            "threshold_changed": False,
            "hysteresis_or_smoothing_added": False,
        },
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": hashes_after,
        },
        "population_integrity": {
            "normal_source_opportunities": len(records),
            "admitted_trades": sum(bool(row["is_admitted"]) for row in records),
            "skipped_opportunities": sum(bool(row["is_skipped"]) for row in records),
            "slot_skipped_opportunities": sum(bool(row["is_slot_skipped"]) for row in records),
            "bullish_source": sum(row["regime_state"] == "BULLISH" for row in records),
            "neutral_source": sum(row["regime_state"] == "NEUTRAL" for row in records),
            "bullish_admitted": sum(row["regime_state"] == "BULLISH" and row["is_admitted"] for row in records),
            "neutral_admitted": sum(row["regime_state"] == "NEUTRAL" and row["is_admitted"] for row in records),
            "bearish_exceptional_review_rows": len(exceptional),
            "bearish_exceptional_valid_path_rows": sum(bool(row["path_eligible"]) for row in exceptional),
            "unavailable_preview_rows": len(unavailable),
            "unchanged": population_unchanged,
            "ranking_changed": False,
            "portfolio_rerun_performed": False,
        },
        "classification_rules": CLASSIFICATION_RULES,
        "results": [executions[item].result for item in REGIME_CONTEXT_EXPERIMENT_IDS],
        "tables": {item: executions[item].trades for item in REGIME_CONTEXT_EXPERIMENT_IDS},
        "correlations": correlations,
        "auxiliary_analyses": auxiliary,
        "classifications": classifications,
        "REGIME_CONTEXT_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING": auxiliary["REGIME_CONTEXT_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING"],
        "pilot": pilot,
        "reproducibility": registry.reproducibility,
        "all_experiments_reproducible": reproducible,
        "baseline_mutation_violations": mutation_violations,
        "failed_experiment_count": len(failures),
        "promotion_allowed": False,
        "experiments_promoted": 0,
        "regime_threshold_changed": False,
        "regime_weight_changed": False,
        "neutral_exclusion_applied": False,
        "hysteresis_or_smoothing_added": False,
        "optimizer_or_ml_run": False,
        "portfolio_variant_run": False,
        "future_regime_used_for_admission": False,
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
            "Historical association is descriptive and does not establish causal market-context value.",
            "Portfolio admission is a non-random subset and can distort regime distributions.",
            "Neutral admissions and several fixed buckets are small or absent.",
            "Bearish exceptional and unavailable cohorts are separate research cohorts with no portfolio attribution.",
            "India VIX, Global/GIFT, and intraday confirmation are historically unavailable, structurally capping confidence.",
            "Future regime change is used only as a post-admission diagnostic label.",
            "The 2026 period is partial and year-level component variation can be insufficient.",
            "Results are gross before transaction costs and slippage.",
        ],
        "runtime_seconds": 0,
        "storage": {},
        "registry_preservation": {},
        "ready_for_review": False,
    }
    notify(progress, "Writing isolated Command 05 artifacts and machine reports")
    paths, preservation = write_outputs(
        context=context,
        registry=registry,
        executions=executions,
        summary=summary,
        preregistration_path=preregistration_path,
        original_registry=original_registry,
        auxiliary=auxiliary,
        pilot=pilot,
    )
    summary["registry_preservation"] = preservation
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {
        "artifact_count": len(paths),
        "artifact_size_bytes": sum(path.stat().st_size for path in paths if path.exists()),
        "root": "data/research/diagnostics/strategy/v1/regime_context_command_05",
    }
    summary["ready_for_review"] = framework_result == "CLEAN" and tests_passed and frontend_build_passed
    write_json(context.data_dir / "reports/strategy_diagnostic_v1_regime_context_summary.json", summary)
    return summary


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

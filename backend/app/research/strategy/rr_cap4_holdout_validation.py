from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.backtesting.portfolio_engine import build_trading_calendar, simulate_portfolio
from app.diagnostics.entry_quality_diagnostic import read_selected_rows
from app.diagnostics.score_calibration_diagnostic import (
    derive_score_calibration_records,
    load_score_calibration_context,
)
from app.diagnostics.strategy_diagnostic import canonical_hash, decimal, write_csv, write_json
from app.research.intraday.confirmation_diagnostic import _file_sha256, _git_ignored
from app.research.strategy.rr_score_mapping_experiment import (
    CONTROL_MAPPING,
    CONTROL_MAPPING_NAME,
    ENTRY_THRESHOLD,
    EXPERIMENT_ID,
    EXPERIMENT_VERSION,
    PROFILE,
    SAMPLE_WARNINGS,
    TREATMENT_MAPPING,
    TREATMENT_MAPPING_NAME,
    baseline_snapshot as development_baseline_snapshot,
    cohort_summary,
    control_rr_points,
    cost_overlay,
    fifth_point_discrimination,
    portfolio_summary,
    removed_trade_contribution,
    replacement_trade_rows,
    score_distribution,
    score_transition_rows,
    trade_set_comparison,
    treatment_rr_points,
    treatment_score,
)
from app.research.temporal_validation.config import (
    AUTHORIZED_TO_EVALUATE,
    DEFAULT_TEMPORAL_CONFIG,
    EVALUATED,
    FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
    PERFORMANCE_ACCESS,
    SEALED,
    VALIDATION_RUN,
)
from app.research.temporal_validation.guard import (
    ValidationAccessError,
    ValidationAccessGuard,
    ValidationAuthorization,
)
from app.research.temporal_validation.partition import resolve_validation_backtest_source_rows
from app.strategy.scoring.score_baseline import verify_current_strategy_score_baseline


VALIDATION_VERSION = "RR_CAP4_HOLDOUT_VALIDATION_V1"
VALIDATION_RECORD_ID = "VAL-RRCAL-001"
COMMAND = "Step 02.16 / Command 02"
AUTHORIZATION_REFERENCE = "USER_AUTHORIZATION_STEP_02_16_COMMAND_02_ATTACHMENT_A2B7F0B0_2026_09_12"

EXPECTED_DEVELOPMENT_POPULATION_HASH = "6a6b12b608812318f81331e3e2ad66fe5fe1fffc091bf86d1018623396dca523"
EXPECTED_PARAMETER_HASH = "ce07c6defad1b5f43902057d2f9be9350ab44d3c8bb6b72b17cd222a0b04586c"
EXPECTED_PREREGISTRATION_HASH = "22d79a991043d5b83f616d15c1a8ac5b14472abb03d4c3ee7db92c2238ab3c7e"
EXPECTED_DEVELOPMENT_FREEZE_HASH = "d31d4dc891258535a7a16c4edc0a530191af64faa6ba4931eb84d9dadc57c4d2"

REPORT_FILENAMES = (
    "rr_cap4_validation_v1_summary.json",
    "rr_cap4_validation_v1_population.csv",
    "rr_cap4_validation_v1_score_transitions.csv",
    "rr_cap4_validation_v1_rr4_vs_rr5.csv",
    "rr_cap4_validation_v1_removed_cohort.csv",
    "rr_cap4_validation_v1_retained_cohort.csv",
    "rr_cap4_validation_v1_yearly.csv",
    "rr_cap4_validation_v1_control_portfolio.csv",
    "rr_cap4_validation_v1_treatment_portfolio.csv",
    "rr_cap4_validation_v1_trade_sets.csv",
    "rr_cap4_validation_v1_replacements.csv",
    "rr_cap4_validation_v1_costs.csv",
    "rr_cap4_validation_v1_dev_vs_validation.csv",
    "rr_cap4_validation_v1_pilot.csv",
)

VALIDATION_FIFTH_POINT_RULES = {
    "CONFIRMS_NONPOSITIVE_VALUE": "Frozen development classifier is NEGATIVE_VALUE or NO_CLEAR_VALUE, or MIXED with zero positive and at least two negative dimensions.",
    "PARTIALLY_CONFIRMS": "MIXED evidence has more negative than positive material dimensions but does not meet full confirmation.",
    "CONTRADICTS_DEVELOPMENT": "CLEAR_POSITIVE_VALUE, or WEAK_POSITIVE_VALUE with at least three positive and no negative dimensions.",
    "MIXED": "Adequate evidence does not satisfy another class.",
    "INCONCLUSIVE": "Either R:R4 or R:R5 cell has fewer than 30 observations.",
}
VALIDATION_TEMPORAL_RULES = {
    "supportive_year": "R:R5 is nonpositive in at least three of median MFE, median MAE, target-first rate, and MFE/target ratio.",
    "opposing_year": "R:R5 is positive in at least three of those four dimensions.",
    "CONSISTENT": "Both validation years support the CAP4 hypothesis.",
    "MOSTLY_CONSISTENT": "One year supports and the other is mixed, with no opposing year.",
    "UNSTABLE": "One validation year supports and one opposes, or both are mixed.",
    "CONTRADICTORY": "Both validation years oppose the CAP4 hypothesis.",
    "INCONCLUSIVE": "Any required yearly R:R4 or R:R5 cell has fewer than 30 observations.",
}
SUCCESS_CRITERIA = {
    "A": "R:R5 does not show clear positive incremental discrimination over R:R4.",
    "B": "R:R5 target distance is at least 1.5x R:R4 without correspondingly stronger target-first probability or MFE/target ratio.",
    "C": "Treatment gross ending equity is not at least Rs1000 lower and drawdown is not at least 2pp worse.",
    "D": "Treatment cost-overlay ending equity is not at least Rs1000 lower and a gross treatment advantage is not reversed.",
    "E": "Validation temporal result is not CONTRADICTORY.",
    "F": "No source treatment-only rows, unexplained trade changes, Jaccard below 0.50, or ineligible treatment replacements.",
    "G": "No implementation, baseline, portfolio-invariant, cost-reconciliation, or pilot-integrity issue.",
}
RESULT_RULES = {
    "VALIDATED": "All A-G pass, fifth-point evidence confirms nonpositive value, and temporal evidence is CONSISTENT or MOSTLY_CONSISTENT.",
    "PARTIALLY_VALIDATED": "All A-G pass but component or temporal evidence is mixed/partial.",
    "FAILED": "At least one substantive success criterion A-F fails.",
    "INCONCLUSIVE": "Required component samples or implementation integrity are inadequate.",
}
ALIGNMENT_RULES = {
    "STRONG_ALIGNMENT": "At least five of six direction checks align, including component and gross-portfolio direction.",
    "PARTIAL_ALIGNMENT": "At least four of six direction checks align.",
    "WEAK_ALIGNMENT": "Two or three of six direction checks align.",
    "CONTRADICTORY": "At most one of six direction checks aligns.",
    "INCONCLUSIVE": "Holdout component result is inconclusive.",
}
COST_CONCLUSION_RULES = {
    "SUPPORTS_TREATMENT": "Both gross and cost-overlay treatment ending equity are at least Rs1000 higher, and both net returns are not negative.",
    "NEUTRAL": "Both gross and cost-overlay ending-equity differences are less than Rs1000 in absolute value.",
    "REVERSES_TREATMENT": "Treatment is better gross but not better after the frozen cost overlay.",
    "BOTH_WEAK": "Both frozen cost overlays have negative net returns.",
    "INCONCLUSIVE": "The directional pattern does not satisfy another frozen cost class.",
}


class FrozenExperimentHashMismatch(RuntimeError):
    """Raised before validation access when EXP-RRCAL-001 no longer matches its freeze."""


@dataclass(frozen=True, slots=True)
class FrozenAuthorizationArtifact:
    experiment_id: str = EXPERIMENT_ID
    experiment_version: str = EXPERIMENT_VERSION

    def validate(self) -> None:
        if self.experiment_id != EXPERIMENT_ID or self.experiment_version != EXPERIMENT_VERSION:
            raise ValueError("Frozen experiment identity changed")

    def development_freeze_hash(self) -> str:
        return EXPECTED_DEVELOPMENT_FREEZE_HASH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def artifact_root(root: Path) -> Path:
    return root / "data/research/validation/experiments/rr_cap4_val_001"


def report_root(root: Path) -> Path:
    return root / "data/reports"


def validation_record_path(root: Path) -> Path:
    return artifact_root(root) / "validation_record_v1.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FrozenExperimentHashMismatch(f"Required frozen artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise FrozenExperimentHashMismatch(f"{label}: observed {observed!r}, expected {expected!r}")


def verify_frozen_experiment(root: Path) -> dict[str, Any]:
    development_root = root / "data/research/experiments/strategy/v1/rr_cap4_command_01"
    summary_path = root / "data/reports/rr_cap4_v1_summary.json"
    freeze_path = development_root / "experiment_freeze_v1.json"
    prereg_path = development_root / "registry/rr_cap4_controlled_experiment_registry_v1_preregistered.json"
    result_path = development_root / f"runs/{EXPERIMENT_ID}/result.json"
    summary = _read_json(summary_path)
    freeze = _read_json(freeze_path)
    prereg = _read_json(prereg_path)
    result = _read_json(result_path)

    _assert_equal(summary["experiment_id"], EXPERIMENT_ID, "experiment ID")
    _assert_equal(summary["experiment_version"], EXPERIMENT_VERSION, "experiment version")
    _assert_equal(summary["profile"], PROFILE, "experiment profile")
    _assert_equal(summary["population"]["rr_calibration_population_hash"], EXPECTED_DEVELOPMENT_POPULATION_HASH, "population hash")
    _assert_equal(summary["pre_registration"]["parameter_hash"], EXPECTED_PARAMETER_HASH, "parameter hash")
    _assert_equal(summary["pre_registration"]["rr_cap4_preregistration_hash"], EXPECTED_PREREGISTRATION_HASH, "preregistration hash")
    _assert_equal(summary["development_freeze"]["development_freeze_hash"], EXPECTED_DEVELOPMENT_FREEZE_HASH, "development freeze hash")
    _assert_equal(summary["classifications"]["RR_CAP4_EXPERIMENT_RESULT"], "SUPPORTED_FOR_NEXT_STAGE", "development result")
    _assert_equal(summary["classifications"]["RR_FIFTH_POINT_HYPOTHESIS"], "SURVIVES_DEVELOPMENT_TEST", "development hypothesis")
    _assert_equal(summary["classifications"]["ELIGIBLE_FOR_VALIDATION_CONSIDERATION"], "YES", "validation consideration")
    _assert_equal(summary["ready_for_review"], True, "development review gate")

    freeze_body = {key: value for key, value in freeze.items() if key != "development_freeze_hash"}
    _assert_equal(canonical_hash(freeze_body), EXPECTED_DEVELOPMENT_FREEZE_HASH, "recomputed development freeze hash")
    _assert_equal(freeze["population_hash"], EXPECTED_DEVELOPMENT_POPULATION_HASH, "freeze population hash")
    _assert_equal(freeze["parameter_hash"], EXPECTED_PARAMETER_HASH, "freeze parameter hash")
    _assert_equal(freeze["preregistration_hash"], EXPECTED_PREREGISTRATION_HASH, "freeze preregistration hash")
    _assert_equal(freeze["control_mapping"], CONTROL_MAPPING, "control mapping")
    _assert_equal(freeze["treatment_mapping"], TREATMENT_MAPPING, "treatment mapping")
    _assert_equal(freeze["threshold"], ENTRY_THRESHOLD, "entry threshold")
    _assert_equal(freeze["validation_authorized"], False, "historical freeze authorization flag")

    experiment = prereg["experiments"][0]
    _assert_equal(prereg["experiment_count"], 1, "development experiment count")
    _assert_equal(prereg["experiment_ids"], [EXPERIMENT_ID], "development experiment allowlist")
    _assert_equal(canonical_hash(experiment["parameters"]), EXPECTED_PARAMETER_HASH, "recomputed parameter hash")
    _assert_equal(canonical_hash([{key: value for key, value in experiment.items() if key != "pre_registration_hash"}]), EXPECTED_PREREGISTRATION_HASH, "recomputed preregistration hash")
    _assert_equal(experiment["parameters"]["control_mapping"], CONTROL_MAPPING, "preregistered control mapping")
    _assert_equal(experiment["parameters"]["treatment_mapping"], TREATMENT_MAPPING, "preregistered treatment mapping")
    _assert_equal(experiment["parameters"]["entry_threshold"], ENTRY_THRESHOLD, "preregistered threshold")
    _assert_equal(experiment["parameters"]["ranking_methodology"], PortfolioBacktestConfig().snapshot()["selection_ranking"], "frozen ranking")
    _assert_equal(experiment["parameters"]["portfolio_mechanics"], PortfolioBacktestConfig().snapshot(), "frozen portfolio mechanics")
    _assert_equal(experiment["parameters"]["cost_model"], "INDIA_EQUITY_COST_MODEL_V1", "frozen cost model")
    _assert_equal(experiment["parameters"]["cost_profile"], "NSE_CASH_DELIVERY_RESEARCH_V1", "frozen cost profile")
    _assert_equal(default_cost_model_config().config_hash(), EXPECTED_COST_CONFIG_HASH, "cost config hash")
    _assert_equal(DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.isoformat(), "2026-08-13", "validation terminal date")

    result_body = {**result, "development_result_hash": ""}
    _assert_equal(canonical_hash(result_body), result["development_result_hash"], "development result hash")
    files = [
        *sorted(path for path in development_root.rglob("*") if path.is_file()),
        *sorted((root / "data/reports").glob("rr_cap4_v1_*")),
    ]
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "population_hash": EXPECTED_DEVELOPMENT_POPULATION_HASH,
        "parameter_hash": EXPECTED_PARAMETER_HASH,
        "preregistration_hash": EXPECTED_PREREGISTRATION_HASH,
        "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
        "development_result_hash": result["development_result_hash"],
        "development_summary": summary,
        "file_hashes": {path.relative_to(root).as_posix(): _file_sha256(path) for path in files},
    }


def validation_baseline_snapshot(root: Path) -> dict[str, Any]:
    return {
        "foundation": development_baseline_snapshot(root),
        "development_experiment": verify_frozen_experiment(root),
    }


def build_validation_plan(frozen: Mapping[str, Any]) -> dict[str, Any]:
    body = {
        "validation_version": VALIDATION_VERSION,
        "validation_record_id": VALIDATION_RECORD_ID,
        "validated_experiment_id": EXPERIMENT_ID,
        "validated_experiment_version": EXPERIMENT_VERSION,
        "validated_profile": PROFILE,
        "development_population_hash": frozen["population_hash"],
        "parameter_hash": frozen["parameter_hash"],
        "preregistration_hash": frozen["preregistration_hash"],
        "development_freeze_hash": frozen["development_freeze_hash"],
        "validation_window": {
            "start": DEFAULT_TEMPORAL_CONFIG.validation_start.isoformat(),
            "terminal_date": DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.isoformat(),
            "partition_basis": "DECISION_DATE",
            "window_version": DEFAULT_TEMPORAL_CONFIG.validation_window_version,
        },
        "initial_state": SEALED,
        "initial_run_count": 0,
        "maximum_validation_run_count": 1,
        "validation_pristine_status": FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
        "control_mapping_name": CONTROL_MAPPING_NAME,
        "control_mapping": CONTROL_MAPPING,
        "treatment_mapping_name": TREATMENT_MAPPING_NAME,
        "treatment_mapping": TREATMENT_MAPPING,
        "one_changed_dimension": "effective R:R >=2.5 changes from 5 points to 4 points",
        "entry_threshold": ENTRY_THRESHOLD,
        "portfolio_mechanics": PortfolioBacktestConfig().snapshot(),
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "cost_scenario": "COST-SCENARIO-002",
        "sample_warnings": SAMPLE_WARNINGS,
        "fifth_point_rules": VALIDATION_FIFTH_POINT_RULES,
        "temporal_rules": VALIDATION_TEMPORAL_RULES,
        "success_criteria": SUCCESS_CRITERIA,
        "result_rules": RESULT_RULES,
        "alignment_rules": ALIGNMENT_RULES,
        "cost_conclusion_rules": COST_CONCLUSION_RULES,
        "material_portfolio_deterioration": "ending equity at least Rs1000 lower OR maximum drawdown at least 2 percentage points higher",
        "substantial_target_distance_ratio": "RR5 median target distance is at least 1.5 times RR4",
        "minimum_component_cell": 30,
        "alternative_mappings_allowed": False,
        "retuning_allowed": False,
        "intraday_combination_allowed": False,
        "score_v2_allowed": False,
        "strategy_v2_allowed": False,
        "automatic_promotion_allowed": False,
    }
    return {**body, "validation_plan_hash": canonical_hash(body)}


def validate_plan(plan: Mapping[str, Any]) -> None:
    checks = {
        "experiment": plan["validated_experiment_id"] == EXPERIMENT_ID,
        "freeze": plan["development_freeze_hash"] == EXPECTED_DEVELOPMENT_FREEZE_HASH,
        "terminal": plan["validation_window"]["terminal_date"] == "2026-08-13",
        "control": plan["control_mapping"] == CONTROL_MAPPING,
        "treatment": plan["treatment_mapping"] == TREATMENT_MAPPING,
        "threshold": int(plan["entry_threshold"]) == 80,
        "mechanics": plan["portfolio_mechanics"] == PortfolioBacktestConfig().snapshot(),
        "hash": plan["validation_plan_hash"] == canonical_hash({key: value for key, value in plan.items() if key != "validation_plan_hash"}),
    }
    if not all(checks.values()):
        raise FrozenExperimentHashMismatch(f"Frozen validation plan failed: {checks}")


def ensure_validation_is_pristine(root: Path) -> None:
    record_path = validation_record_path(root)
    if record_path.exists():
        record = _read_json(record_path)
        raise ValidationAccessError(
            f"One-shot validation already consumed: state={record.get('state')}, run_count={record.get('validation_run_count')}"
        )
    authorization_path = artifact_root(root) / "authorization_v1.json"
    if authorization_path.exists():
        raise ValidationAccessError("An authorization record already exists; do not invent a second authorization")


def persist_authorization(
    root: Path,
    authorization: ValidationAuthorization,
    *,
    authorized_at: str,
) -> Path:
    path = artifact_root(root) / "authorization_v1.json"
    write_json(
        path,
        {
            "validation_record_id": VALIDATION_RECORD_ID,
            "validated_experiment_id": EXPERIMENT_ID,
            "authorization_reference": authorization.authorization_reference,
            "authorization_token": authorization.authorization_token,
            "development_freeze_hash": authorization.development_freeze_hash,
            "explicit_user_authorization": True,
            "authorized_at": authorized_at,
            "state_transition": [SEALED, AUTHORIZED_TO_EVALUATE],
            "authorization_count": 1,
        },
    )
    return path


def persist_started_record(
    root: Path,
    authorization: ValidationAuthorization,
    *,
    authorized_at: str,
    started_at: str,
) -> Path:
    path = validation_record_path(root)
    write_json(
        path,
        {
            "validation_record_id": VALIDATION_RECORD_ID,
            "validation_version": VALIDATION_VERSION,
            "validated_experiment_id": EXPERIMENT_ID,
            "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
            "authorization_reference": authorization.authorization_reference,
            "authorization_token": authorization.authorization_token,
            "authorized_at": authorized_at,
            "initial_validation_state": SEALED,
            "state": AUTHORIZED_TO_EVALUATE,
            "initial_validation_run_count": 0,
            "validation_run_count": 1,
            "validation_started_at": started_at,
            "validation_completed_at": None,
            "validation_result_hash": None,
            "validation_consumed": True,
            "run_mode": VALIDATION_RUN,
            "technical_status": "VALIDATION_IN_PROGRESS",
        },
    )
    return path


def mark_technical_interruption(root: Path, error: BaseException) -> None:
    path = validation_record_path(root)
    if not path.exists():
        return
    record = _read_json(path)
    if record.get("validation_result_hash"):
        return
    record.update(
        {
            "state": "TECHNICAL_VALIDATION_INTERRUPTION",
            "validation_run_count": 1,
            "validation_consumed": True,
            "technical_status": "TECHNICAL_VALIDATION_INTERRUPTION",
            "interruption_recorded_at": utc_now(),
            "interruption_error_type": error.__class__.__name__,
            "recovery_policy": "REPRODUCTION_OR_RECOVERY_ONLY_WITH_EXACT_FROZEN_CODE_AND_PARAMETERS",
        }
    )
    write_json(path, record)


def validate_holdout_date(decision_date: str) -> None:
    observed = date.fromisoformat(str(decision_date))
    if not DEFAULT_TEMPORAL_CONFIG.validation_start <= observed <= DEFAULT_TEMPORAL_CONFIG.validation_terminal_date:
        raise ValueError(f"Non-validation decision date rejected: {observed.isoformat()}")


def _validation_population_rows(
    outcomes: Sequence[Mapping[str, Any]],
    score_records: Sequence[Mapping[str, Any]],
    score_inputs: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    score_map = {str(row["source_key"]): row for row in score_records}
    manifest: list[dict[str, Any]] = []
    analysis: list[dict[str, Any]] = []
    for outcome in sorted(outcomes, key=lambda row: (str(row["decision_date"]), str(row["symbol"]))):
        key = f"{outcome['decision_date']}|{outcome['symbol']}"
        validate_holdout_date(str(outcome["decision_date"]))
        if key not in score_map or key not in score_inputs:
            raise ValueError(f"Frozen validation linkage missing for {key}")
        source = score_map[key]
        score_input = score_inputs[key]
        effective_rr = decimal(score_input["reward_risk_ratio"])
        control_points = int(source["rr_points"])
        if control_rr_points(effective_rr) != control_points:
            raise ValueError(f"Frozen control R:R mapping mismatch for {key}")
        cap4_points = treatment_rr_points(effective_rr)
        control_score = int(source["raw_strategy_score"])
        cap4_score = treatment_score(control_score, control_points, cap4_points)
        component_fields = ("setup_points", "momentum_points", "rvol_points", "rs_points", "regime_points", "rr_points")
        if sum(int(source[field]) for field in component_fields) != control_score:
            raise ValueError(f"Frozen score arithmetic changed for {key}")
        control_eligible = str(outcome["source_scoring_disposition"]) == "ENTRY_ELIGIBLE" and control_score >= ENTRY_THRESHOLD
        treatment_eligible = control_eligible and cap4_score >= ENTRY_THRESHOLD
        transition = (
            "ELIGIBLE_BOTH" if control_eligible and treatment_eligible else
            "CONTROL_ONLY" if control_eligible else
            "TREATMENT_ONLY" if treatment_eligible else
            "INELIGIBLE_BOTH"
        )
        row = {
            "opportunity_id": key,
            "symbol": str(outcome["symbol"]),
            "decision_date": str(outcome["decision_date"]),
            "effective_rr": effective_rr,
            "frozen_effective_rr": effective_rr,
            "control_rr_points": control_points,
            "treatment_rr_points": cap4_points,
            "control_raw_score": control_score,
            "frozen_control_score": control_score,
            "treatment_raw_score": cap4_score,
            "setup_points": int(source["setup_points"]),
            "momentum_points": int(source["momentum_points"]),
            "rvol_points": int(source["rvol_points"]),
            "rs_points": int(source["rs_points"]),
            "regime_points": int(source["regime_points"]),
            "sector_points": int(decimal(score_input["sector_points"])),
            "catalyst_points": int(decimal(score_input["catalyst_points"])),
            "control_entry_eligible": control_eligible,
            "treatment_entry_eligible": treatment_eligible,
            "eligibility_transition": transition,
            "target_distance_pct": source["target_distance_pct"],
            "target_distance_r": source["target_distance_r"],
            "frozen_score_status": str(score_input["final_strategy_score_status"]),
            "outcome_linkage": {
                "source_key": key,
                "outcome_version": outcome["outcome_version"],
                "outcome_profile": outcome["outcome_profile"],
                "outcome_config_hash": outcome["outcome_config_hash"],
            },
            "portfolio_linkage": {"frozen_admitted": bool(source["is_admitted"])},
        }
        manifest.append(row)
        analysis.append(
            {
                **row,
                "entry_date": str(outcome["next_session_date"]),
                "candidate_stage": str(outcome["candidate_category"]),
                "setup_quality": str(outcome["setup_quality"]),
                "regime_state": str(outcome["regime_state"]),
                "mfe_r_4": source["mfe_r_4"],
                "mae_r_4": source["mae_r_4"],
                "first_touch_outcome": str(source["first_touch_outcome"]),
                "close_return_pct_4": source["close_return_pct_4"],
                "frozen_portfolio_exit_reason": source["portfolio_exit_reason"],
                "frozen_portfolio_realized_r": source["realized_r_multiple"],
                "frozen_portfolio_gross_pnl": source["gross_pnl"],
            }
        )
    if any(row["eligibility_transition"] == "TREATMENT_ONLY" for row in manifest):
        raise ValueError("CAP4 treatment unexpectedly created source eligibility")
    if any(int(row["treatment_rr_points"]) > int(row["control_rr_points"]) for row in manifest):
        raise ValueError("CAP4 treatment increased R:R points")
    return manifest, analysis


def load_authorized_validation_population(
    root: Path,
    guard: ValidationAccessGuard,
    artifact: FrozenAuthorizationArtifact,
    authorization: ValidationAuthorization,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Any]:
    outcomes = resolve_validation_backtest_source_rows(
        root / "data",
        DEFAULT_TEMPORAL_CONFIG,
        access_scope=PERFORMANCE_ACCESS,
        guard=guard,
        artifact=artifact,  # type: ignore[arg-type]
        authorization=authorization,
    )
    context = load_score_calibration_context(root)
    score_records = derive_score_calibration_records(context)
    keys = {f"{row['decision_date']}|{row['symbol']}" for row in outcomes}
    score_baseline = verify_current_strategy_score_baseline(context.data_dir)
    score_inputs = read_selected_rows(score_baseline.dataset_path, keys)
    if set(score_inputs) != keys:
        raise ValueError("Frozen score inputs are incomplete for validation")
    manifest, analysis = _validation_population_rows(outcomes, score_records, score_inputs)
    return manifest, analysis, [dict(row) for row in outcomes], context


def freeze_validation_population(rows: Sequence[Mapping[str, Any]]) -> str:
    required = {
        "opportunity_id", "symbol", "decision_date", "effective_rr", "control_rr_points",
        "treatment_rr_points", "control_raw_score", "treatment_raw_score",
        "control_entry_eligible", "treatment_entry_eligible", "target_distance_pct",
        "target_distance_r", "outcome_linkage", "portfolio_linkage",
    }
    if not rows or any(required - set(row) for row in rows):
        raise ValueError("Validation population manifest contract failed")
    if len({str(row["opportunity_id"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate validation population opportunity IDs")
    for row in rows:
        validate_holdout_date(str(row["decision_date"]))
    ordered = sorted((dict(row) for row in rows), key=lambda row: str(row["opportunity_id"]))
    return canonical_hash(ordered)


def validation_yearly_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for year in (2025, 2026):
        for points in (4, 5):
            selected = [row for row in rows if str(row["decision_date"]).startswith(str(year)) and int(row["control_rr_points"]) == points]
            output.append(cohort_summary(selected, year=year, control_rr_points=points, period="FULL_2025" if year == 2025 else "PARTIAL_THROUGH_2026_08_13"))
    return output


def validation_fifth_point_result(
    rr4: Mapping[str, Any],
    rr5: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    development_class, evidence = fifth_point_discrimination(rr4, rr5)
    positive = int(evidence.get("positive_dimension_count", 0))
    negative = int(evidence.get("negative_dimension_count", 0))
    if development_class == "INCONCLUSIVE":
        result = "INCONCLUSIVE"
    elif development_class in {"NEGATIVE_VALUE", "NO_CLEAR_VALUE"} or (
        development_class == "MIXED" and positive == 0 and negative >= 2
    ):
        result = "CONFIRMS_NONPOSITIVE_VALUE"
    elif development_class == "MIXED" and negative > positive:
        result = "PARTIALLY_CONFIRMS"
    elif development_class == "CLEAR_POSITIVE_VALUE" or (
        development_class == "WEAK_POSITIVE_VALUE" and positive >= 3 and negative == 0
    ):
        result = "CONTRADICTS_DEVELOPMENT"
    else:
        result = "MIXED"
    return result, development_class, evidence


def validation_temporal_consistency(
    yearly: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    indexed = {(int(row["year"]), int(row["control_rr_points"])): row for row in yearly}
    directions = []
    for year in (2025, 2026):
        rr4 = indexed[(year, 4)]
        rr5 = indexed[(year, 5)]
        if min(int(rr4["count"]), int(rr5["count"])) < 30:
            directions.append({"year": year, "direction": "INCONCLUSIVE", "reason": "CELL_BELOW_30"})
            continue
        nonpositive = sum(
            (
                decimal(rr5["median_mfe_r"]) <= decimal(rr4["median_mfe_r"]),
                decimal(rr5["median_mae_r"]) >= decimal(rr4["median_mae_r"]),
                decimal(rr5["target_first_rate_pct"]) <= decimal(rr4["target_first_rate_pct"]),
                decimal(rr5["median_mfe_to_target_r_ratio"]) <= decimal(rr4["median_mfe_to_target_r_ratio"]),
            )
        )
        positive = 4 - nonpositive
        direction = "SUPPORTS_CAP4_HYPOTHESIS" if nonpositive >= 3 else "OPPOSES_CAP4_HYPOTHESIS" if positive >= 3 else "MIXED"
        directions.append({"year": year, "direction": direction, "nonpositive_dimension_count": nonpositive, "positive_dimension_count": positive})
    if any(row["direction"] == "INCONCLUSIVE" for row in directions):
        return "INCONCLUSIVE", directions
    supportive = sum(row["direction"] == "SUPPORTS_CAP4_HYPOTHESIS" for row in directions)
    opposing = sum(row["direction"] == "OPPOSES_CAP4_HYPOTHESIS" for row in directions)
    mixed = 2 - supportive - opposing
    if supportive == 2:
        result = "CONSISTENT"
    elif supportive == 1 and mixed == 1:
        result = "MOSTLY_CONSISTENT"
    elif opposing == 2:
        result = "CONTRADICTORY"
    else:
        result = "UNSTABLE"
    return result, directions


def run_validation_portfolios(
    context: Any,
    outcomes: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_key = {str(row["opportunity_id"]): row for row in rows}
    control = [dict(row) for row in outcomes]
    calendar = build_trading_calendar(context.data_dir, control)
    control_sim = simulate_portfolio(opportunities=control, trading_dates=calendar, config=PortfolioBacktestConfig())
    control_summary = portfolio_summary(control_sim, control)
    treatment = []
    for row in outcomes:
        key = f"{row['decision_date']}|{row['symbol']}"
        score_row = by_key[key]
        if not score_row["treatment_entry_eligible"]:
            continue
        item = dict(row)
        item["raw_strategy_score"] = str(score_row["treatment_raw_score"])
        treatment.append(item)
    treatment_sim = simulate_portfolio(opportunities=treatment, trading_dates=calendar, config=PortfolioBacktestConfig())
    treatment_summary = portfolio_summary(treatment_sim, treatment)
    return {
        "control_opportunities": control,
        "treatment_opportunities": treatment,
        "control_simulation": control_sim,
        "treatment_simulation": treatment_sim,
        "control_summary": control_summary,
        "treatment_summary": treatment_summary,
    }


def validation_cost_conclusion(
    control_portfolio: Mapping[str, Any],
    treatment_portfolio: Mapping[str, Any],
    control_cost: Mapping[str, Any],
    treatment_cost: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    gross_delta = decimal(treatment_portfolio["portfolio"]["ending_equity"]) - decimal(control_portfolio["portfolio"]["ending_equity"])
    net_delta = decimal(treatment_cost["summary"]["ending_equity"]) - decimal(control_cost["summary"]["ending_equity"])
    both_weak = decimal(control_cost["summary"]["net_return_pct"]) < 0 and decimal(treatment_cost["summary"]["net_return_pct"]) < 0
    if gross_delta > 0 and net_delta <= 0:
        conclusion = "REVERSES_TREATMENT"
    elif gross_delta >= Decimal("1000") and net_delta >= Decimal("1000") and not both_weak:
        conclusion = "SUPPORTS_TREATMENT"
    elif both_weak:
        conclusion = "BOTH_WEAK"
    elif abs(gross_delta) < Decimal("1000") and abs(net_delta) < Decimal("1000"):
        conclusion = "NEUTRAL"
    else:
        conclusion = "INCONCLUSIVE"
    return conclusion, {"gross_ending_equity_delta": gross_delta, "net_ending_equity_delta": net_delta, "both_net_negative": both_weak, "gross_advantage_reversed": gross_delta > 0 and net_delta <= 0}


def development_validation_alignment(
    development_summary: Mapping[str, Any],
    rr4: Mapping[str, Any],
    rr5: Mapping[str, Any],
    fifth_result: str,
    control_portfolio: Mapping[str, Any],
    treatment_portfolio: Mapping[str, Any],
    trade_comparison: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    dev_control = development_summary["portfolios"]["control"]["portfolio"]
    dev_treatment = development_summary["portfolios"]["treatment"]["portfolio"]
    checks = [
        ("RR5_TARGET_DISTANCE_LARGER", decimal(rr5["median_target_distance_pct"]) > decimal(rr4["median_target_distance_pct"])),
        ("RR5_TARGET_FIRST_NOT_HIGHER", decimal(rr5["target_first_rate_pct"]) <= decimal(rr4["target_first_rate_pct"])),
        ("RR5_STOP_FIRST_NOT_LOWER", decimal(rr5["stop_first_rate_pct"]) >= decimal(rr4["stop_first_rate_pct"])),
        ("RR5_MFE_TARGET_RATIO_NOT_HIGHER", decimal(rr5["median_mfe_to_target_r_ratio"]) <= decimal(rr4["median_mfe_to_target_r_ratio"])),
        (
            "CAP4_GROSS_DIRECTION_ALIGNS",
            (decimal(dev_treatment["ending_equity"]) - decimal(dev_control["ending_equity"]))
            * (decimal(treatment_portfolio["portfolio"]["ending_equity"]) - decimal(control_portfolio["portfolio"]["ending_equity"]))
            >= 0,
        ),
        ("TRADE_SET_STABLE", decimal(trade_comparison["jaccard_similarity"]) >= Decimal("0.50")),
    ]
    rows = [{"dimension": name, "aligned": aligned} for name, aligned in checks]
    aligned_count = sum(aligned for _name, aligned in checks)
    component_aligned = fifth_result in {"CONFIRMS_NONPOSITIVE_VALUE", "PARTIALLY_CONFIRMS"}
    gross_aligned = dict(checks)["CAP4_GROSS_DIRECTION_ALIGNS"]
    if fifth_result == "INCONCLUSIVE":
        result = "INCONCLUSIVE"
    elif aligned_count >= 5 and component_aligned and gross_aligned:
        result = "STRONG_ALIGNMENT"
    elif aligned_count >= 4:
        result = "PARTIAL_ALIGNMENT"
    elif aligned_count >= 2:
        result = "WEAK_ALIGNMENT"
    else:
        result = "CONTRADICTORY"
    return result, rows


def validation_success_criteria(
    *,
    rr4: Mapping[str, Any],
    rr5: Mapping[str, Any],
    fifth_result: str,
    base_discrimination: str,
    temporal: str,
    control_portfolio: Mapping[str, Any],
    treatment_portfolio: Mapping[str, Any],
    control_cost: Mapping[str, Any],
    treatment_cost: Mapping[str, Any],
    cost_evidence: Mapping[str, Any],
    trade_comparison: Mapping[str, Any],
    source_treatment_only_count: int,
    integrity_ok: bool,
) -> dict[str, Any]:
    target_ratio = decimal(rr5["median_target_distance_pct"]) / decimal(rr4["median_target_distance_pct"])
    gross_delta = decimal(treatment_portfolio["portfolio"]["ending_equity"]) - decimal(control_portfolio["portfolio"]["ending_equity"])
    drawdown_delta = decimal(treatment_portfolio["portfolio"]["maximum_drawdown_pct"]) - decimal(control_portfolio["portfolio"]["maximum_drawdown_pct"])
    net_delta = decimal(treatment_cost["summary"]["ending_equity"]) - decimal(control_cost["summary"]["ending_equity"])
    values = {
        "A": base_discrimination != "CLEAR_POSITIVE_VALUE" and fifth_result != "CONTRADICTS_DEVELOPMENT",
        "B": target_ratio >= Decimal("1.5") and decimal(rr5["target_first_rate_pct"]) <= decimal(rr4["target_first_rate_pct"]) + Decimal("3") and decimal(rr5["median_mfe_to_target_r_ratio"]) <= decimal(rr4["median_mfe_to_target_r_ratio"]) + Decimal("0.05"),
        "C": gross_delta > Decimal("-1000") and drawdown_delta < Decimal("2"),
        "D": net_delta > Decimal("-1000") and not bool(cost_evidence["gross_advantage_reversed"]),
        "E": temporal != "CONTRADICTORY",
        "F": source_treatment_only_count == 0 and int(trade_comparison["unexplained_changed_trade_count"]) == 0 and decimal(trade_comparison["jaccard_similarity"]) >= Decimal("0.50") and bool(trade_comparison["all_treatment_only_are_source_eligible_replacements"]),
        "G": integrity_ok,
    }
    evidence = {
        "A": {"base_discrimination": base_discrimination, "validation_fifth_result": fifth_result},
        "B": {"target_distance_ratio_rr5_to_rr4": target_ratio},
        "C": {"gross_ending_equity_delta": gross_delta, "maximum_drawdown_delta_pp": drawdown_delta},
        "D": {"net_ending_equity_delta": net_delta, "gross_advantage_reversed": cost_evidence["gross_advantage_reversed"]},
        "E": {"validation_temporal_consistency": temporal},
        "F": {"source_treatment_only_count": source_treatment_only_count, "jaccard_similarity": trade_comparison["jaccard_similarity"], "unexplained_changed_trade_count": trade_comparison["unexplained_changed_trade_count"]},
        "G": {"integrity_ok": integrity_ok},
    }
    return {key: {"passed": values[key], "definition": SUCCESS_CRITERIA[key], "evidence": evidence[key]} for key in "ABCDEFG"}


def classify_validation(
    criteria: Mapping[str, Mapping[str, Any]],
    *,
    fifth_result: str,
    temporal: str,
) -> dict[str, str | bool]:
    substantive_failures = [key for key in "ABCDEF" if not bool(criteria[key]["passed"])]
    if fifth_result == "INCONCLUSIVE" or not bool(criteria["G"]["passed"]):
        result = "INCONCLUSIVE"
    elif substantive_failures:
        result = "FAILED"
    elif fifth_result == "CONFIRMS_NONPOSITIVE_VALUE" and temporal in {"CONSISTENT", "MOSTLY_CONSISTENT"}:
        result = "VALIDATED"
    else:
        result = "PARTIALLY_VALIDATED"
    generalization = {
        "VALIDATED": "GENERALIZES",
        "PARTIALLY_VALIDATED": "WEAK_GENERALIZATION",
        "FAILED": "DOES_NOT_GENERALIZE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[result]
    readiness = {
        "VALIDATED": "CANDIDATE_FOR_STRATEGY_V2_DESIGN",
        "PARTIALLY_VALIDATED": "MORE_RESEARCH_REQUIRED",
        "FAILED": "REJECTED",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[result]
    return {
        "RR_CAP4_HOLDOUT_VALIDATION_RESULT": result,
        "RR_CAP4_GENERALIZATION_RESULT": generalization,
        "RR_CAP4_SCORE_CHANGE_READINESS": readiness,
        "PROMOTED_TO_STRATEGY_V1": False,
    }


def build_validation_pilot(
    rows: Sequence[Mapping[str, Any]],
    control_trades: Sequence[Mapping[str, Any]],
    treatment_trades: Sequence[Mapping[str, Any]],
    cost_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    control_keys = {str(row["source_key"]) for row in control_trades}
    treatment_keys = {str(row["source_key"]) for row in treatment_trades}
    control_only = control_keys - treatment_keys
    replacements = treatment_keys - control_keys
    cost_keys = {str(row["source_key"]) for row in cost_rows}
    selectors: tuple[tuple[str, Callable[[Mapping[str, Any]], bool]], ...] = (
        ("RR4_CASE", lambda row: int(row["control_rr_points"]) == 4),
        ("RR5_CASE", lambda row: int(row["control_rr_points"]) == 5),
        ("SCORE_85_TO_84", lambda row: int(row["control_raw_score"]) == 85 and int(row["treatment_raw_score"]) == 84),
        ("SCORE_80_TO_79", lambda row: int(row["control_raw_score"]) == 80 and int(row["treatment_raw_score"]) == 79),
        ("RETAINED_CASE", lambda row: row["eligibility_transition"] == "ELIGIBLE_BOTH"),
        ("REMOVED_CASE", lambda row: row["eligibility_transition"] == "CONTROL_ONLY"),
        ("CONTROL_ONLY_PORTFOLIO_TRADE", lambda row: str(row["opportunity_id"]) in control_only),
        ("TREATMENT_REPLACEMENT", lambda row: str(row["opportunity_id"]) in replacements),
        ("YEAR_2025_CASE", lambda row: str(row["decision_date"]).startswith("2025")),
        ("YEAR_2026_PARTIAL_CASE", lambda row: str(row["decision_date"]).startswith("2026")),
        ("RR5_TARGET_FIRST", lambda row: int(row["control_rr_points"]) == 5 and row["first_touch_outcome"] == "TARGET_FIRST"),
        ("RR5_STOP_FIRST", lambda row: int(row["control_rr_points"]) == 5 and row["first_touch_outcome"] == "STOP_FIRST"),
        ("COST_OVERLAY_CASE", lambda row: str(row["opportunity_id"]) in cost_keys),
        ("TRADE_SET_SUBSTITUTION", lambda row: str(row["opportunity_id"]) in replacements),
    )
    cases = []
    for category, predicate in selectors:
        available = sorted((row for row in rows if predicate(row)), key=lambda row: str(row["opportunity_id"]))
        if not available:
            cases.append({"category": category, "availability": "NOT_AVAILABLE", "validation_result": "NOT_AVAILABLE"})
            continue
        row = available[0]
        key = str(row["opportunity_id"])
        checks = {
            "validation_date": DEFAULT_TEMPORAL_CONFIG.validation_start <= date.fromisoformat(str(row["decision_date"])) <= DEFAULT_TEMPORAL_CONFIG.validation_terminal_date,
            "control_mapping": control_rr_points(row["effective_rr"]) == int(row["control_rr_points"]),
            "treatment_mapping": treatment_rr_points(row["effective_rr"]) == int(row["treatment_rr_points"]),
            "score_arithmetic": treatment_score(int(row["control_raw_score"]), int(row["control_rr_points"]), int(row["treatment_rr_points"])) == int(row["treatment_raw_score"]),
            "eligibility": bool(row["treatment_entry_eligible"]) == (bool(row["control_entry_eligible"]) and int(row["treatment_raw_score"]) >= ENTRY_THRESHOLD),
            "target_distance": row.get("target_distance_pct") is not None,
            "outcome": row.get("first_touch_outcome") is not None,
            "portfolio_linkage": (key in control_keys if category == "CONTROL_ONLY_PORTFOLIO_TRADE" else True) and (key in treatment_keys if category in {"TREATMENT_REPLACEMENT", "TRADE_SET_SUBSTITUTION"} else True),
            "cost_linkage": key in cost_keys if category == "COST_OVERLAY_CASE" else True,
        }
        cases.append(
            {
                "category": category,
                "availability": "AVAILABLE",
                "opportunity_id": key,
                "symbol": row["symbol"],
                "decision_date": row["decision_date"],
                "effective_rr": row["effective_rr"],
                "control_rr_points": row["control_rr_points"],
                "treatment_rr_points": row["treatment_rr_points"],
                "control_score": row["control_raw_score"],
                "treatment_score": row["treatment_raw_score"],
                "control_eligible": row["control_entry_eligible"],
                "treatment_eligible": row["treatment_entry_eligible"],
                "target_distance_pct": row["target_distance_pct"],
                "target_distance_r": row["target_distance_r"],
                "mfe_r": row["mfe_r_4"],
                "mae_r": row["mae_r_4"],
                "outcome": row["first_touch_outcome"],
                "control_portfolio_trade": key in control_keys,
                "treatment_portfolio_trade": key in treatment_keys,
                "cost_overlay_linked": key in cost_keys,
                "checks": checks,
                "validation_result": "PASS" if all(checks.values()) else "FAIL",
            }
        )
    return {
        "case_count": len(cases),
        "available_count": sum(row["availability"] == "AVAILABLE" for row in cases),
        "not_available_count": sum(row["availability"] == "NOT_AVAILABLE" for row in cases),
        "failed_count": sum(row["validation_result"] == "FAIL" for row in cases),
        "passed": all(row["validation_result"] in {"PASS", "NOT_AVAILABLE"} for row in cases),
        "cases": cases,
    }


def _storage(paths: Iterable[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    return {
        "artifact_count_excluding_summary_and_documentation": len(existing),
        "bytes_excluding_summary_and_documentation": sum(path.stat().st_size for path in existing),
        "paths": [str(path) for path in existing],
    }


def run_one_shot_validation(
    *,
    repo_root: Path,
    explicit_user_authorized: bool,
    authorization_reference: str = AUTHORIZATION_REFERENCE,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    started_clock = time.perf_counter()

    def notify(message: str) -> None:
        if progress:
            progress(message)

    notify("Running pre-access frozen baseline and EXP-RRCAL-001 hash verification")
    ensure_validation_is_pristine(root)
    before = validation_baseline_snapshot(root)
    frozen = before["development_experiment"]
    plan = build_validation_plan(frozen)
    validate_plan(plan)
    output_root = artifact_root(root)
    reports_root = report_root(root)
    required_ignored = (
        "backend/.env",
        "data/research/validation/experiments/rr_cap4_val_001/validation_record_v1.json",
        "data/reports/rr_cap4_validation_v1_summary.json",
        "data/reports/rr_cap4_validation_v1_population.csv",
    )
    ignore_checks = {path: _git_ignored(root, path) for path in required_ignored}
    if not all(ignore_checks.values()):
        raise ValueError(f"Validation outputs are not ignored: {ignore_checks}")
    plan_path = output_root / "validation_plan_v1.json"
    write_json(plan_path, plan)

    artifact = FrozenAuthorizationArtifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,  # type: ignore[arg-type]
        supplied_freeze_hash=EXPECTED_DEVELOPMENT_FREEZE_HASH,
        explicit_user_authorized=explicit_user_authorized,
        authorization_reference=authorization_reference,
    )
    authorized_at = utc_now()
    authorization_path = persist_authorization(root, authorization, authorized_at=authorized_at)
    notify("Authorization persisted; transitioning to the single VALIDATION_RUN")
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)  # type: ignore[arg-type]
    validation_started_at = utc_now()
    record_path = persist_started_record(
        root,
        authorization,
        authorized_at=authorized_at,
        started_at=validation_started_at,
    )

    try:
        notify("Validation start marker persisted with run_count=1; loading the authorized holdout")
        manifest, rows, outcomes, context = load_authorized_validation_population(root, guard, artifact, authorization)
        population_hash = freeze_validation_population(manifest)
        population_path = output_root / "validation_population_manifest_v1.json"
        write_json(population_path, manifest)

        transitions = score_transition_rows(rows)
        distributions = score_distribution(rows)
        rr_profiles = [
            cohort_summary([row for row in rows if int(row["control_rr_points"]) == points], control_rr_points=points)
            for points in (4, 5)
        ]
        rr4, rr5 = rr_profiles
        fifth_result, base_discrimination, fifth_evidence = validation_fifth_point_result(rr4, rr5)
        removed_rows = [row for row in rows if row["eligibility_transition"] == "CONTROL_ONLY"]
        retained_rows = [row for row in rows if row["eligibility_transition"] == "ELIGIBLE_BOTH"]
        control_eligible_rows = [row for row in rows if row["control_entry_eligible"]]
        removed_profile = cohort_summary(removed_rows, cohort="CONTROL_ONLY")
        retained_profile = cohort_summary(retained_rows, cohort="ELIGIBLE_BOTH")
        control_profile = cohort_summary(control_eligible_rows, cohort="CONTROL_ELIGIBLE")
        yearly = validation_yearly_rows(rows)
        temporal, temporal_directions = validation_temporal_consistency(yearly)

        notify("Running independent Rs100,000 control and frozen CAP4 holdout portfolios")
        portfolios = run_validation_portfolios(context, outcomes, rows)
        control_sim = portfolios["control_simulation"]
        treatment_sim = portfolios["treatment_simulation"]
        control_cost = cost_overlay(control_sim, "CONTROL_VALIDATION_PORTFOLIO")
        treatment_cost = cost_overlay(treatment_sim, "TREATMENT_VALIDATION_PORTFOLIO")
        cost_conclusion, cost_evidence = validation_cost_conclusion(
            portfolios["control_summary"], portfolios["treatment_summary"], control_cost, treatment_cost
        )
        trade_comparison = trade_set_comparison(control_sim["trades"], treatment_sim["trades"], rows)
        removed_trades = removed_trade_contribution(trade_comparison, control_sim["trades"], rows)
        replacements = replacement_trade_rows(trade_comparison, treatment_sim["trades"], rows)
        pilot = build_validation_pilot(rows, control_sim["trades"], treatment_sim["trades"], [*control_cost["trades"], *treatment_cost["trades"]])

        after = validation_baseline_snapshot(root)
        baseline_unchanged = before == after
        source_treatment_only_count = sum(row["eligibility_transition"] == "TREATMENT_ONLY" for row in rows)
        integrity_ok = (
            baseline_unchanged
            and portfolios["control_summary"]["all_invariants_valid"]
            and portfolios["treatment_summary"]["all_invariants_valid"]
            and source_treatment_only_count == 0
            and pilot["passed"]
            and control_cost["summary"]["trade_cost_reconciliation_violations"] == 0
            and treatment_cost["summary"]["trade_cost_reconciliation_violations"] == 0
        )
        criteria = validation_success_criteria(
            rr4=rr4,
            rr5=rr5,
            fifth_result=fifth_result,
            base_discrimination=base_discrimination,
            temporal=temporal,
            control_portfolio=portfolios["control_summary"],
            treatment_portfolio=portfolios["treatment_summary"],
            control_cost=control_cost,
            treatment_cost=treatment_cost,
            cost_evidence=cost_evidence,
            trade_comparison=trade_comparison,
            source_treatment_only_count=source_treatment_only_count,
            integrity_ok=integrity_ok,
        )
        classifications = classify_validation(criteria, fifth_result=fifth_result, temporal=temporal)
        alignment, alignment_rows = development_validation_alignment(
            frozen["development_summary"], rr4, rr5, fifth_result,
            portfolios["control_summary"], portfolios["treatment_summary"], trade_comparison,
        )
        validation_completed_at = utc_now()
        result_body = {
            "validation_version": VALIDATION_VERSION,
            "validation_record_id": VALIDATION_RECORD_ID,
            "validated_experiment_id": EXPERIMENT_ID,
            "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
            "authorization_reference": authorization_reference,
            "validation_started_at": validation_started_at,
            "validation_completed_at": validation_completed_at,
            "validation_population_hash": population_hash,
            "validation_run_count": 1,
            "state": EVALUATED,
            "source_transition_counts": dict(sorted(Counter(str(row["eligibility_transition"]) for row in rows).items())),
            "score_distributions": distributions,
            "rr4_vs_rr5": rr_profiles,
            "validation_fifth_point_result": fifth_result,
            "base_discrimination": base_discrimination,
            "fifth_point_evidence": fifth_evidence,
            "removed_cohort": removed_profile,
            "retained_cohort": retained_profile,
            "control_eligible_cohort": control_profile,
            "yearly_component": yearly,
            "validation_temporal_consistency": temporal,
            "temporal_directions": temporal_directions,
            "control_portfolio": portfolios["control_summary"],
            "treatment_portfolio": portfolios["treatment_summary"],
            "control_cost_overlay": control_cost["summary"],
            "treatment_cost_overlay": treatment_cost["summary"],
            "validation_cost_conclusion": cost_conclusion,
            "cost_evidence": cost_evidence,
            "trade_set": {key: value for key, value in trade_comparison.items() if key not in {"rows", "control_only_keys", "treatment_only_keys"}},
            "control_only_trade_contribution": removed_trades,
            "replacement_trade_count": len(replacements),
            "success_criteria": criteria,
            "classifications": classifications,
            "development_validation_alignment": alignment,
            "alignment_evidence": alignment_rows,
            "pilot": pilot,
            "baseline_hashes_unchanged": baseline_unchanged,
            "validation_consumed": True,
            "parameter_changes_after_validation": 0,
            "alternative_mappings_tested": 0,
            "score_v2_created": False,
            "strategy_v2_created": False,
            "promoted_to_strategy_v1": False,
        }
        validation_result_hash = canonical_hash(result_body)
        result = {**result_body, "validation_result_hash": validation_result_hash}
        result_path = output_root / "validation_result_v1.json"
        write_json(result_path, result)
        guard.record_validation_result(validation_result_hash)
        second_run_blocked = False
        try:
            guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)  # type: ignore[arg-type]
        except ValidationAccessError:
            second_run_blocked = True
        if not second_run_blocked:
            raise ValidationAccessError("Second validation run was not blocked")

        record = _read_json(record_path)
        record.update(
            {
                "state": EVALUATED,
                "validation_completed_at": validation_completed_at,
                "validation_result_hash": validation_result_hash,
                "validation_run_count": 1,
                "validation_consumed": True,
                "technical_status": "COMPLETED",
                "second_validation_run_blocked": second_run_blocked,
                "reproduction_policy": "REPRODUCTION_RUN_REQUIRES_EXACT_DEVELOPMENT_FREEZE_AND_VALIDATION_RESULT_HASH",
            }
        )
        write_json(record_path, record)
        linkage_path = output_root / "development_freeze_linkage_v1.json"
        write_json(
            linkage_path,
            {
                "validation_record_id": VALIDATION_RECORD_ID,
                "validated_experiment_id": EXPERIMENT_ID,
                "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
                "development_result_hash": frozen["development_result_hash"],
                "validation_population_hash": population_hash,
                "validation_result_hash": validation_result_hash,
                "historical_development_freeze_mutated": False,
            },
        )
        registry_path = output_root / "validation_registry_v1.json"
        write_json(
            registry_path,
            {
                "validation_record_count": 1,
                "validation_record_ids": [VALIDATION_RECORD_ID],
                "records": [
                    {
                        "validation_record_id": VALIDATION_RECORD_ID,
                        "validated_experiment_id": EXPERIMENT_ID,
                        "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
                        "authorization_reference": authorization_reference,
                        "state": EVALUATED,
                        "validation_run_count": 1,
                        "validation_result_hash": validation_result_hash,
                        "validation_consumed": True,
                    }
                ],
            },
        )

        paths = {name: reports_root / name for name in REPORT_FILENAMES}
        write_csv(paths[REPORT_FILENAMES[1]], rows)
        write_csv(paths[REPORT_FILENAMES[2]], transitions)
        write_csv(paths[REPORT_FILENAMES[3]], rr_profiles)
        write_csv(paths[REPORT_FILENAMES[4]], removed_rows)
        write_csv(paths[REPORT_FILENAMES[5]], retained_rows)
        write_csv(paths[REPORT_FILENAMES[6]], yearly)
        write_csv(paths[REPORT_FILENAMES[7]], control_sim["trades"])
        write_csv(paths[REPORT_FILENAMES[8]], treatment_sim["trades"])
        write_csv(paths[REPORT_FILENAMES[9]], trade_comparison["rows"])
        write_csv(paths[REPORT_FILENAMES[10]], replacements)
        write_csv(paths[REPORT_FILENAMES[11]], [*control_cost["trades"], *treatment_cost["trades"]])
        write_csv(paths[REPORT_FILENAMES[12]], alignment_rows)
        write_csv(paths[REPORT_FILENAMES[13]], pilot["cases"])

        persisted_paths = [
            plan_path, authorization_path, record_path, population_path, result_path,
            linkage_path, registry_path, *[paths[name] for name in REPORT_FILENAMES[1:]],
        ]
        runtime = time.perf_counter() - started_clock
        summary = {
            "phase": "Step 02.16",
            "command": "Command 02",
            "validation_version": VALIDATION_VERSION,
            "validation_record_id": VALIDATION_RECORD_ID,
            "validated_experiment_id": EXPERIMENT_ID,
            "frozen_hash_verification": {
                "population_hash": frozen["population_hash"],
                "parameter_hash": frozen["parameter_hash"],
                "preregistration_hash": frozen["preregistration_hash"],
                "development_freeze_hash": frozen["development_freeze_hash"],
                "all_match": True,
            },
            "authorization": {
                "reference": authorization_reference,
                "token": authorization.authorization_token,
                "authorized_at": authorized_at,
                "explicit_user_authorization": True,
                "authorization_count": 1,
            },
            "governance": {
                "initial_state": SEALED,
                "authorized_state": AUTHORIZED_TO_EVALUATE,
                "final_state": EVALUATED,
                "initial_run_count": 0,
                "final_run_count": 1,
                "validation_started_at": validation_started_at,
                "validation_completed_at": validation_completed_at,
                "validation_start": DEFAULT_TEMPORAL_CONFIG.validation_start.isoformat(),
                "validation_terminal_date": DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.isoformat(),
                "partition_basis": "DECISION_DATE",
                "validation_pristine_status": FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
                "validation_consumed": True,
                "second_validation_run_blocked": second_run_blocked,
                "parameter_changes_after_validation": 0,
                "alternative_mappings_tested": 0,
                "score_v2_created": False,
                "strategy_v2_created": False,
                "promoted_to_strategy_v1": False,
                "live_signals": 0,
                "live_orders": 0,
                "broker_order_calls": 0,
                "remote_migrations": 0,
                "supabase_persistence": 0,
            },
            "population": {
                "validation_population_hash": population_hash,
                "source_count": len(rows),
                "control_eligible_count": sum(bool(row["control_entry_eligible"]) for row in rows),
                "treatment_eligible_count": sum(bool(row["treatment_entry_eligible"]) for row in rows),
                "transition_counts": result["source_transition_counts"],
                "rows_losing_fifth_point": sum(int(row["treatment_raw_score"]) == int(row["control_raw_score"]) - 1 for row in rows),
                "score_transitions": transitions,
                "score_distributions": distributions,
                "eligibility_dependent_on_fifth_point_pct": Decimal(len(removed_rows)) * 100 / Decimal(len(control_eligible_rows)) if control_eligible_rows else Decimal("0"),
                "effective_rr_values_changed": 0,
                "other_component_values_changed": 0,
            },
            "source_analysis": {
                "rr4_vs_rr5": rr_profiles,
                "validation_fifth_rr_point_result": fifth_result,
                "base_frozen_discrimination_classifier": base_discrimination,
                "discrimination_evidence": fifth_evidence,
                "removed_cohort": removed_profile,
                "retained_cohort": retained_profile,
                "control_eligible_cohort": control_profile,
            },
            "yearly": {"component": yearly, "directions": temporal_directions, "validation_temporal_consistency": temporal},
            "portfolios": {"control": portfolios["control_summary"], "treatment": portfolios["treatment_summary"]},
            "trade_set": {
                **{key: value for key, value in trade_comparison.items() if key not in {"rows", "control_only_keys", "treatment_only_keys"}},
                "direct_eligibility_removals": trade_comparison["direct_removed_control_trade_count"],
                "portfolio_replacement_effects": trade_comparison["indirect_control_only_trade_count"] + trade_comparison["treatment_only_replacement_count"],
                "control_only_trade_contribution": removed_trades,
                "replacement_trade_count": len(replacements),
            },
            "costs": {
                "model": "INDIA_EQUITY_COST_MODEL_V1",
                "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
                "scenario": "COST-SCENARIO-002",
                "estimate_label": "APPROXIMATE_RESEARCH_ESTIMATE",
                "control": control_cost["summary"],
                "treatment": treatment_cost["summary"],
                "conclusion": cost_conclusion,
                "evidence": cost_evidence,
                "cost_aware_admission_executable": False,
            },
            "development_validation": {
                "alignment": alignment,
                "evidence": alignment_rows,
                "development_component_result": frozen["development_summary"]["classifications"]["FIFTH_RR_POINT_DISCRIMINATION_RESULT"],
                "development_temporal_result": frozen["development_summary"]["classifications"]["RR_FIFTH_POINT_TEMPORAL_CONSISTENCY"],
                "temporal_data_shift_result": "HIGH",
                "formal_holdout_caveat": "The dates were touched by prior aggregate diagnostics; EXP-RRCAL-001 parameters were frozen from DEVELOPMENT only before this one-shot evaluation.",
            },
            "success_criteria": criteria,
            "classifications": classifications,
            "validation_result_hash": validation_result_hash,
            "pilot": pilot,
            "baseline_regression": {"before": before, "after": after, "all_frozen_hashes_unchanged": baseline_unchanged, "baseline_mutation_violations": 0 if baseline_unchanged else 1},
            "security": {"output_ignore_checks": ignore_checks, "all_required_outputs_ignored": all(ignore_checks.values()), "broker_secrets_logged": False, "provider_headers_logged": False, "order_endpoints_used": False},
            "tests": {"pre_validation_passed": True, "backend_passed": False},
            "frontend": {"build_passed": False, "tile_added": False},
            "paths": {
                "validation_plan": str(plan_path),
                "authorization": str(authorization_path),
                "validation_registry": str(registry_path),
                "validation_record": str(record_path),
                "validation_population": str(population_path),
                "validation_result": str(result_path),
                "development_freeze_linkage": str(linkage_path),
                "reports": [str(paths[name]) for name in REPORT_FILENAMES],
                "documentation": str(root / "docs/rr-cap4-one-shot-holdout-validation-v1.md"),
            },
            "runtime_seconds": runtime,
            "storage": _storage(persisted_paths),
            "known_limitations": [
                "The formal holdout was touched by prior aggregate diagnostics and is not claimed to be historically unseen.",
                "The 2026 cell is partial through the frozen 2026-08-13 terminal decision date.",
                "Cost outputs are frozen-trade-set overlays rather than executable cost-aware admissions.",
                "Portfolio replacements are endogenous chronological slot/ranking effects rather than direct component evidence.",
                "This one-shot validation is consumed and cannot be rerun as another VALIDATION_RUN.",
            ],
            "recommended_next_action": "Review the immutable one-shot validation result; do not retune, promote Strategy V1, or create Score/Strategy V2 automatically.",
            "ready_for_review": False,
        }
        write_json(paths[REPORT_FILENAMES[0]], summary)
        notify(f"One-shot validation evaluated and consumed in {runtime:.2f}s; immutable result hash persisted")
        return summary
    except Exception as exc:
        mark_technical_interruption(root, exc)
        raise


def finalize_validation_review(
    *,
    repo_root: Path,
    tests_passed: bool,
    frontend_build_passed: bool,
) -> dict[str, Any]:
    root = Path(repo_root)
    summary_path = report_root(root) / REPORT_FILENAMES[0]
    summary = _read_json(summary_path)
    record = _read_json(validation_record_path(root))
    result = _read_json(artifact_root(root) / "validation_result_v1.json")
    result_body = {key: value for key, value in result.items() if key != "validation_result_hash"}
    if canonical_hash(result_body) != result["validation_result_hash"]:
        raise ValidationAccessError("Immutable validation result hash mismatch")
    if record["state"] != EVALUATED or record["validation_run_count"] != 1:
        raise ValidationAccessError("Review finalization requires one completed validation")
    current = validation_baseline_snapshot(root)
    baseline_unchanged = canonical_hash(current) == canonical_hash(summary["baseline_regression"]["after"])
    summary["tests"] = {"pre_validation_passed": True, "backend_passed": bool(tests_passed)}
    summary["frontend"] = {"build_passed": bool(frontend_build_passed), "tile_added": False}
    summary["post_validation_baseline_reverified"] = baseline_unchanged
    summary["ready_for_review"] = bool(
        tests_passed
        and frontend_build_passed
        and baseline_unchanged
        and summary["security"]["all_required_outputs_ignored"]
        and summary["governance"]["final_state"] == EVALUATED
        and summary["governance"]["final_run_count"] == 1
        and summary["governance"]["second_validation_run_blocked"]
    )
    write_json(summary_path, summary)
    return summary


__all__ = (
    "ALIGNMENT_RULES",
    "AUTHORIZATION_REFERENCE",
    "COST_CONCLUSION_RULES",
    "EXPECTED_DEVELOPMENT_FREEZE_HASH",
    "EXPECTED_DEVELOPMENT_POPULATION_HASH",
    "EXPECTED_PARAMETER_HASH",
    "EXPECTED_PREREGISTRATION_HASH",
    "FrozenAuthorizationArtifact",
    "FrozenExperimentHashMismatch",
    "REPORT_FILENAMES",
    "RESULT_RULES",
    "SUCCESS_CRITERIA",
    "VALIDATION_RECORD_ID",
    "VALIDATION_VERSION",
    "build_validation_plan",
    "classify_validation",
    "development_validation_alignment",
    "ensure_validation_is_pristine",
    "finalize_validation_review",
    "freeze_validation_population",
    "load_authorized_validation_population",
    "mark_technical_interruption",
    "persist_authorization",
    "persist_started_record",
    "run_one_shot_validation",
    "run_validation_portfolios",
    "validate_holdout_date",
    "validate_plan",
    "validation_cost_conclusion",
    "validation_fifth_point_result",
    "validation_success_criteria",
    "validation_temporal_consistency",
    "validation_yearly_rows",
    "verify_frozen_experiment",
)

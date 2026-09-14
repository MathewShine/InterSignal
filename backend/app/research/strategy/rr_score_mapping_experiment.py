from __future__ import annotations

import json
import subprocess
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.costs.cost_engine import (
    SCENARIO_BASELINE_SLIPPAGE,
    build_costed_daily_ledger,
    calculate_trade_cost,
    registered_cost_scenarios,
    scenario_summary,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    FORCED_DATA_EXIT,
    OTHER_EXIT,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
    build_metrics,
    build_trading_calendar,
    simulate_portfolio,
)
from app.diagnostics.score_calibration_diagnostic import (
    derive_score_calibration_records,
    load_score_calibration_context,
)
from app.diagnostics.entry_quality_diagnostic import read_selected_rows
from app.diagnostics.strategy_diagnostic import (
    canonical_hash,
    decimal,
    mean,
    median,
    percent,
    write_csv,
    write_json,
)
from app.research.intraday.confirmation_diagnostic import _file_sha256, _git_ignored
from app.research.intraday.early_path_recovery_diagnostic import (
    baseline_snapshot as command_03_baseline_snapshot,
    preregistration_dependencies as command_03_preregistration_dependencies,
)
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED
from app.strategy.scoring.score_baseline import verify_current_strategy_score_baseline


EXPERIMENT_VERSION = "RR_SCORE_MAPPING_CONTROLLED_EXPERIMENT_V1"
EXPERIMENT_ID = "EXP-RRCAL-001"
PROFILE = "RR_CAP4_DEVELOPMENT_V1"
EXPERIMENT_TYPE = "DEVELOPMENT_ONLY_CONTROLLED_SCORE_COMPONENT_EXPERIMENT"
COMMAND = "Step 02.16 / Command 01"

CONTROL_MAPPING_NAME = "RR_SCORE_MAPPING_V1"
TREATMENT_MAPPING_NAME = "RR_SCORE_MAPPING_CAP4_V1"
CONTROL_MAPPING = {
    "LT_1_5": 0,
    "GTE_1_5_LT_2": 3,
    "GTE_2_LT_2_5": 4,
    "GTE_2_5": 5,
}
TREATMENT_MAPPING = {
    "LT_1_5": 0,
    "GTE_1_5_LT_2": 3,
    "GTE_2": 4,
}
ENTRY_THRESHOLD = 80
EXPECTED_DEVELOPMENT_SOURCE_COUNT = 2068
EXPECTED_CONTROL_ENDING_EQUITY = Decimal("98326.608925713674")
EXPECTED_CHECKPOINT_COMMIT = "c6315abdd92db3b978ae28c5f5b08013ead4bbb3"
EXPECTED_COMMAND_03_POPULATION_HASH = "49c9243b76a6de6cee38d9f293cb5b510e45ec90f25fb6bfce76ede7fe09c1c8"
EXPECTED_COMMAND_03_PREREGISTRATION_HASH = "912f42ca7a6c58d4b64cfc0f42fb9e886e3b7d13ebf400b42144bc28a50a5fa8"

SAMPLE_WARNINGS = {
    "VERY_SMALL": "<30",
    "SMALL": "30-99",
    "LIMITED": "100-299",
    "ADEQUATE_FOR_DESCRIPTION": ">=300",
}
FIFTH_POINT_CLASSIFICATION_RULES = {
    "material_dimensions": {
        "median_mfe_r": "RR5 minus RR4 >= +0.10R is positive; <= -0.10R is negative",
        "median_mae_r": "RR5 minus RR4 <= -0.10R is positive; >= +0.10R is negative",
        "target_first_rate": "RR5 minus RR4 >= +3pp is positive; <= -3pp is negative",
        "median_mfe_to_target_ratio": "RR5 minus RR4 >= +0.05 is positive; <= -0.05 is negative",
    },
    "CLEAR_POSITIVE_VALUE": "both cells >=100, at least three positive dimensions, and no negative dimension",
    "WEAK_POSITIVE_VALUE": "both cells >=30 and positive dimensions exceed negative dimensions",
    "NEGATIVE_VALUE": "both cells >=30, at least three negative dimensions, and no positive dimension",
    "NO_CLEAR_VALUE": "both cells >=30 and all four dimensions are immaterial",
    "MIXED": "both cells >=30 and material directions conflict or do not satisfy another class",
    "INCONCLUSIVE": "either comparison cell has fewer than 30 observations",
}
TEMPORAL_RULES = {
    "supportive_year": "RR5 is nonpositive in at least three of median MFE, median MAE, target-first rate, and MFE/target ratio",
    "opposing_year": "RR5 is positive in at least three of the same four dimensions",
    "CONSISTENT": "three supportive years",
    "MOSTLY_CONSISTENT": "two supportive years and no opposing year",
    "UNSTABLE": "at least one supportive and one opposing year, or otherwise mixed adequate years",
    "INVERSE": "at least two opposing years and no supportive year",
    "INCONCLUSIVE": "any required R:R4 or R:R5 yearly cell has fewer than 30 observations",
}
FALSIFICATION_CRITERIA = {
    "A": "Fifth-point cohort has CLEAR_POSITIVE_VALUE and at least two yearly opposing directions.",
    "B": "Rows are removed but the retained source set improves fewer than two of median MFE, median MAE, target-first rate, and stop-first rate.",
    "C": "Treatment independently deteriorates by at least 1.0% ending equity or 2.0pp maximum drawdown in at least two of three years.",
    "D": "Source treatment-only rows exist, an unexplained changed trade exists, or trade-set Jaccard is below 0.50.",
    "E": "Treatment is better gross but is not better after the frozen baseline-slippage cost overlay.",
}
SUPPORT_CRITERIA = {
    "nonpositive_fifth_point": "Fifth-point result is NO_CLEAR_VALUE, NEGATIVE_VALUE, or MIXED without positive majority.",
    "distance_without_achievement": "RR5 median target distance is larger without a higher target-first rate and MFE/target ratio.",
    "temporal": "RR_FIFTH_POINT_TEMPORAL_CONSISTENCY is CONSISTENT or MOSTLY_CONSISTENT.",
    "portfolio": "Treatment is not materially worse overall or in two of three independent yearly comparisons.",
    "cost": "Frozen cost overlay does not reverse a structural treatment conclusion.",
    "integrity": "No severe regression, invariant, or data issue.",
}
REPORT_FILENAMES = (
    "rr_cap4_v1_summary.json",
    "rr_cap4_v1_population.csv",
    "rr_cap4_v1_score_transitions.csv",
    "rr_cap4_v1_rr4_vs_rr5.csv",
    "rr_cap4_v1_removed_cohort.csv",
    "rr_cap4_v1_retained_cohort.csv",
    "rr_cap4_v1_yearly_component.csv",
    "rr_cap4_v1_control_portfolio.csv",
    "rr_cap4_v1_treatment_portfolio.csv",
    "rr_cap4_v1_trade_set_comparison.csv",
    "rr_cap4_v1_replacement_trades.csv",
    "rr_cap4_v1_costs.csv",
    "rr_cap4_v1_pilot.csv",
)


def control_rr_points(effective_rr: Any) -> int:
    value = decimal(effective_rr)
    if value < Decimal("1.5"):
        return 0
    if value < 2:
        return 3
    if value < Decimal("2.5"):
        return 4
    return 5


def treatment_rr_points(effective_rr: Any) -> int:
    value = decimal(effective_rr)
    if value < Decimal("1.5"):
        return 0
    if value < 2:
        return 3
    return 4


def treatment_score(control_score: int, control_points: int, treatment_points: int) -> int:
    return int(control_score) - int(control_points) + int(treatment_points)


def eligibility_transition(control_eligible: bool, treatment_eligible: bool) -> str:
    if control_eligible and treatment_eligible:
        return "ELIGIBLE_BOTH"
    if control_eligible:
        return "CONTROL_ONLY"
    if treatment_eligible:
        return "TREATMENT_ONLY"
    return "INELIGIBLE_BOTH"


def validate_development_only(decision_date: str) -> None:
    observed = date.fromisoformat(str(decision_date))
    if not DEFAULT_TEMPORAL_CONFIG.development_start <= observed <= DEFAULT_TEMPORAL_CONFIG.development_end:
        raise ValueError(f"Validation or out-of-window row rejected: {observed.isoformat()}")


def sample_warning(count: int) -> str:
    if count < 30:
        return "VERY_SMALL"
    if count < 100:
        return "SMALL"
    if count < 300:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def _numbers(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return [decimal(row[field]) for row in rows if row.get(field) is not None and str(row.get(field)) != ""]


def _rate(numerator: int, denominator: int) -> Decimal:
    return percent(Decimal(numerator), Decimal(denominator)) if denominator else Decimal("0")


def _first_touch_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    values = Counter(str(row.get("first_touch_outcome") or "") for row in rows)
    return {
        "target_first": values["TARGET_FIRST"],
        "stop_first": values["STOP_FIRST"],
        "neither": values["NEITHER_WITHIN_HORIZON"],
        "ambiguous": sum(count for key, count in values.items() if "AMBIGUOUS" in key),
    }


def cohort_summary(rows: Sequence[Mapping[str, Any]], **labels: Any) -> dict[str, Any]:
    paths = _first_touch_counts(rows)
    ratios = [
        decimal(row["mfe_r_4"]) / decimal(row["target_distance_r"])
        for row in rows
        if row.get("mfe_r_4") is not None
        and row.get("target_distance_r") is not None
        and decimal(row["target_distance_r"]) > 0
    ]
    return {
        **labels,
        "count": len(rows),
        "sample_warning": sample_warning(len(rows)),
        "mean_effective_rr": mean(_numbers(rows, "effective_rr")),
        "median_effective_rr": median(_numbers(rows, "effective_rr")),
        "mean_target_distance_pct": mean(_numbers(rows, "target_distance_pct")),
        "median_target_distance_pct": median(_numbers(rows, "target_distance_pct")),
        "mean_target_distance_r": mean(_numbers(rows, "target_distance_r")),
        "median_target_distance_r": median(_numbers(rows, "target_distance_r")),
        "mean_mfe_r": mean(_numbers(rows, "mfe_r_4")),
        "median_mfe_r": median(_numbers(rows, "mfe_r_4")),
        "mean_mae_r": mean(_numbers(rows, "mae_r_4")),
        "median_mae_r": median(_numbers(rows, "mae_r_4")),
        "mean_mfe_to_target_r_ratio": mean(ratios),
        "median_mfe_to_target_r_ratio": median(ratios),
        "mean_close_return_pct_4": mean(_numbers(rows, "close_return_pct_4")),
        "median_close_return_pct_4": median(_numbers(rows, "close_return_pct_4")),
        "target_first_count": paths["target_first"],
        "target_first_rate_pct": _rate(paths["target_first"], len(rows)),
        "stop_first_count": paths["stop_first"],
        "stop_first_rate_pct": _rate(paths["stop_first"], len(rows)),
        "neither_count": paths["neither"],
        "neither_rate_pct": _rate(paths["neither"], len(rows)),
        "ambiguous_count": paths["ambiguous"],
        "year_distribution": dict(sorted(Counter(str(row["decision_date"])[:4] for row in rows).items())),
        "candidate_stage_distribution": dict(sorted(Counter(str(row["candidate_stage"]) for row in rows).items())),
        "setup_distribution": dict(sorted(Counter(str(row["setup_quality"]) for row in rows).items())),
        "control_score_distribution": dict(sorted(Counter(str(row["frozen_control_score"]) for row in rows).items())),
        "effective_rr_unchanged": all(decimal(row["effective_rr"]) == decimal(row["frozen_effective_rr"]) for row in rows),
    }


def _checkpoint_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _command_03_snapshot(root: Path) -> dict[str, Any]:
    artifact_root = root / "data/research/diagnostics/intraday/v1/early_path_command_03"
    summary_path = root / "data/reports/early_path_recovery_v1_summary.json"
    if not artifact_root.exists() or not summary_path.exists():
        raise FileNotFoundError("Step 02.15 Command 03 frozen artifacts are unavailable")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    observed = {
        "population_hash": summary["population"]["early_path_population_hash"],
        "preregistration_hash": summary["pre_registration"]["early_path_preregistration_hash"],
        "experiment_count": summary["pre_registration"]["experiment_count"],
        "ready_for_review": summary["ready_for_review"],
    }
    expected = {
        "population_hash": EXPECTED_COMMAND_03_POPULATION_HASH,
        "preregistration_hash": EXPECTED_COMMAND_03_PREREGISTRATION_HASH,
        "experiment_count": 10,
        "ready_for_review": True,
    }
    if observed != expected:
        raise ValueError("Step 02.15 Command 03 frozen semantics changed")
    paths = [summary_path, *sorted(path for path in artifact_root.rglob("*") if path.is_file())]
    return {
        **observed,
        "semantic_hash": canonical_hash(observed),
        "file_hashes": {path.relative_to(root).as_posix(): _file_sha256(path) for path in paths},
    }


def baseline_snapshot(root: Path) -> dict[str, Any]:
    snapshot = command_03_baseline_snapshot(root)
    snapshot["command_03"] = _command_03_snapshot(root)
    checkpoint = _checkpoint_commit(root)
    if checkpoint != EXPECTED_CHECKPOINT_COMMIT:
        raise ValueError(f"Frozen checkpoint changed: {checkpoint}")
    snapshot["checkpoint_commit"] = checkpoint
    if default_cost_model_config().config_hash() != EXPECTED_COST_CONFIG_HASH:
        raise ValueError("Frozen cost-model configuration changed")
    return snapshot


def preregistration_dependencies(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    dependencies = command_03_preregistration_dependencies(snapshot)
    dependencies["command_03"] = {
        key: snapshot["command_03"][key]
        for key in (
            "population_hash",
            "preregistration_hash",
            "experiment_count",
            "ready_for_review",
            "semantic_hash",
        )
    }
    dependencies["checkpoint_commit"] = snapshot["checkpoint_commit"]
    return dependencies


def build_population(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Any]:
    context = load_score_calibration_context(root)
    score_records = derive_score_calibration_records(context)
    score_map = {str(row["source_key"]): row for row in score_records}
    outcome_map = {
        f"{row['decision_date']}|{row['symbol']}": row
        for row in context.entry_context.opportunities
    }
    development_outcomes = [
        dict(row)
        for row in context.entry_context.opportunities
        if DEFAULT_TEMPORAL_CONFIG.development_start
        <= date.fromisoformat(str(row["decision_date"]))
        <= DEFAULT_TEMPORAL_CONFIG.development_end
    ]
    development_keys = {
        f"{row['decision_date']}|{row['symbol']}" for row in development_outcomes
    }
    score_baseline = verify_current_strategy_score_baseline(context.data_dir)
    frozen_score_inputs = read_selected_rows(score_baseline.dataset_path, development_keys)
    if set(frozen_score_inputs) != development_keys:
        raise ValueError("Frozen score-input rows are incomplete for the DEVELOPMENT population")
    manifest_rows: list[dict[str, Any]] = []
    analysis_rows: list[dict[str, Any]] = []
    for outcome in sorted(development_outcomes, key=lambda row: (row["decision_date"], row["symbol"])):
        key = f"{outcome['decision_date']}|{outcome['symbol']}"
        source = score_map[key]
        score_input = frozen_score_inputs[key]
        validate_development_only(str(outcome["decision_date"]))
        effective_rr = decimal(score_input["reward_risk_ratio"])
        observed_control_points = int(source["rr_points"])
        if control_rr_points(effective_rr) != observed_control_points:
            raise ValueError(f"Frozen R:R mapping mismatch for {key}")
        cap4_points = treatment_rr_points(effective_rr)
        control_score = int(source["raw_strategy_score"])
        cap4_score = treatment_score(control_score, observed_control_points, cap4_points)
        component_sum = sum(
            int(source[field])
            for field in ("setup_points", "momentum_points", "rvol_points", "rs_points", "regime_points", "rr_points")
        )
        if component_sum != control_score:
            raise ValueError(f"Frozen score arithmetic changed for {key}")
        control_eligible = (
            str(outcome["source_scoring_disposition"]) == "ENTRY_ELIGIBLE"
            and control_score >= ENTRY_THRESHOLD
        )
        cap4_eligible = control_eligible and cap4_score >= ENTRY_THRESHOLD
        transition = eligibility_transition(control_eligible, cap4_eligible)
        frozen = {
            "opportunity_id": key,
            "symbol": str(outcome["symbol"]),
            "decision_date": str(outcome["decision_date"]),
            "frozen_control_score": control_score,
            "setup_points": int(source["setup_points"]),
            "momentum_points": int(source["momentum_points"]),
            "rvol_points": int(source["rvol_points"]),
            "rs_points": int(source["rs_points"]),
            "regime_points": int(source["regime_points"]),
            "sector_points": int(decimal(score_input["sector_points"])),
            "catalyst_points": int(decimal(score_input["catalyst_points"])),
            "control_rr_points": observed_control_points,
            "treatment_rr_points": cap4_points,
            "treatment_raw_score": cap4_score,
            "effective_rr": effective_rr,
            "frozen_effective_rr": effective_rr,
            "target_distance_pct": source["target_distance_pct"],
            "target_distance_r": source["target_distance_r"],
            "frozen_score_status": str(score_input["final_strategy_score_status"]),
            "frozen_scoring_disposition": str(score_input["scoring_disposition"]),
            "frozen_score_coverage_pct": decimal(score_input["score_coverage_pct"]),
            "frozen_entry_eligible": control_eligible,
            "control_entry_eligible": control_eligible,
            "treatment_entry_eligible": cap4_eligible,
            "eligibility_transition": transition,
            "frozen_outcome_linkage": {
                "source_key": key,
                "outcome_version": outcome["outcome_version"],
                "outcome_profile": outcome["outcome_profile"],
                "outcome_config_hash": outcome["outcome_config_hash"],
            },
            "frozen_portfolio_admission_flag": bool(source["is_admitted"]),
        }
        manifest_rows.append(frozen)
        analysis_rows.append(
            {
                **frozen,
                "entry_date": str(outcome["next_session_date"]),
                "candidate_stage": str(outcome["candidate_category"]),
                "candidate_state": str(outcome["candidate_state"]),
                "setup_quality": str(outcome["setup_quality"]),
                "regime_state": str(outcome["regime_state"]),
                "mfe_r_4": source["mfe_r_4"],
                "mae_r_4": source["mae_r_4"],
                "outcome_effective_rr": source["effective_reward_risk"],
                "first_touch_outcome": str(source["first_touch_outcome"]),
                "close_return_pct_4": source["close_return_pct_4"],
                "frozen_portfolio_exit_reason": source["portfolio_exit_reason"],
                "frozen_portfolio_realized_r": source["realized_r_multiple"],
                "frozen_portfolio_gross_pnl": source["gross_pnl"],
            }
        )
    if len(manifest_rows) != EXPECTED_DEVELOPMENT_SOURCE_COUNT:
        raise ValueError(f"Expected {EXPECTED_DEVELOPMENT_SOURCE_COUNT} DEVELOPMENT rows, observed {len(manifest_rows)}")
    if set(score_map) != set(outcome_map):
        raise ValueError("Frozen score/outcome source linkage changed")
    if any(row["eligibility_transition"] == "TREATMENT_ONLY" for row in manifest_rows):
        raise ValueError("CAP4 treatment unexpectedly created source eligibility")
    if any(row["treatment_rr_points"] > row["control_rr_points"] for row in manifest_rows):
        raise ValueError("CAP4 treatment increased R:R points")
    return manifest_rows, analysis_rows, development_outcomes, context


def freeze_population(rows: Sequence[Mapping[str, Any]]) -> str:
    required = {
        "opportunity_id",
        "symbol",
        "decision_date",
        "frozen_control_score",
        "setup_points",
        "momentum_points",
        "rvol_points",
        "rs_points",
        "regime_points",
        "sector_points",
        "catalyst_points",
        "control_rr_points",
        "effective_rr",
        "target_distance_pct",
        "target_distance_r",
        "frozen_score_status",
        "frozen_entry_eligible",
        "frozen_outcome_linkage",
        "frozen_portfolio_admission_flag",
    }
    if len(rows) != EXPECTED_DEVELOPMENT_SOURCE_COUNT or any(required - set(row) for row in rows):
        raise ValueError("R:R calibration population manifest contract failed")
    if len({str(row["opportunity_id"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate population opportunity IDs")
    for row in rows:
        validate_development_only(str(row["decision_date"]))
    return canonical_hash(list(rows))


def build_preregistration(
    population_hash: str,
    dependencies: Mapping[str, Any],
) -> dict[str, Any]:
    parameters = {
        "experiment_version": EXPERIMENT_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "profile": PROFILE,
        "experiment_type": EXPERIMENT_TYPE,
        "development_window": {
            "start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
            "end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
            "partition_key": "decision_date",
        },
        "validation_state": SEALED,
        "validation_run_count": 0,
        "population_hash": population_hash,
        "control_mapping_name": CONTROL_MAPPING_NAME,
        "control_mapping": CONTROL_MAPPING,
        "treatment_mapping_name": TREATMENT_MAPPING_NAME,
        "treatment_mapping": TREATMENT_MAPPING,
        "one_changed_dimension": "effective R:R >=2.5 changes from 5 points to 4 points",
        "architecture_rationale": "R:R >=2 already satisfies preferred reward/risk quality; test whether more score for target distance adds evidence.",
        "entry_threshold": ENTRY_THRESHOLD,
        "raw_score_normalization": False,
        "ranking_methodology": PortfolioBacktestConfig().selection_ranking,
        "portfolio_mechanics": PortfolioBacktestConfig().snapshot(),
        "control_expected_ending_equity": EXPECTED_CONTROL_ENDING_EQUITY,
        "fifth_point_classification_rules": FIFTH_POINT_CLASSIFICATION_RULES,
        "temporal_rules": TEMPORAL_RULES,
        "falsification_criteria": FALSIFICATION_CRITERIA,
        "support_criteria": SUPPORT_CRITERIA,
        "sample_warnings": SAMPLE_WARNINGS,
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
        "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        "alternative_mappings_allowed": False,
        "optimizer_allowed": False,
        "intraday_combination_allowed": False,
        "score_v2_allowed": False,
        "strategy_v2_allowed": False,
        "promotion_allowed": False,
        "validation_authorized": False,
    }
    body = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "hypothesis": "The extra fifth R:R score point for effective R:R >=2.5 lacks sufficient incremental outcome discrimination.",
        "population_hash": population_hash,
        "metrics": (
            "source score transitions",
            "R:R4 versus R:R5 MFE/MAE/first-touch/target distance/MFE-to-target ratio",
            "removed and retained source cohorts",
            "yearly component consistency",
            "independent control and treatment portfolio metrics",
            "trade-set similarity and substitutions",
            "frozen baseline-slippage cost overlays",
        ),
        "baseline_dependencies": dict(dependencies),
        "parameters": parameters,
        "parameter_hash": canonical_hash(parameters),
        "promotion_allowed": False,
        "validation_authorized": False,
        "pre_registered": True,
        "status": "REGISTERED",
    }
    return {
        "experiment_count": 1,
        "experiment_ids": [EXPERIMENT_ID],
        "experiments": [{**body, "pre_registration_hash": canonical_hash(body)}],
        "definitions_frozen_before_results": True,
        "no_post_result_definition_edits": True,
        "promotion_allowed": False,
        "validation_authorized": False,
        "rr_cap4_preregistration_hash": canonical_hash([body]),
    }


def build_development_freeze(
    population_hash: str,
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    experiment = preregistration["experiments"][0]
    body = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "hypothesis": experiment["hypothesis"],
        "one_changed_dimension": experiment["parameters"]["one_changed_dimension"],
        "development_window": experiment["parameters"]["development_window"],
        "population_hash": population_hash,
        "control_mapping": CONTROL_MAPPING,
        "treatment_mapping": TREATMENT_MAPPING,
        "threshold": ENTRY_THRESHOLD,
        "metrics": experiment["metrics"],
        "falsification_criteria": FALSIFICATION_CRITERIA,
        "support_criteria": SUPPORT_CRITERIA,
        "cost_model": {
            "version": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "config_hash": EXPECTED_COST_CONFIG_HASH,
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "mode": "FROZEN_TRADE_SET_OVERLAY_NOT_COST_AWARE_ADMISSION",
        },
        "parameter_hash": experiment["parameter_hash"],
        "preregistration_hash": preregistration["rr_cap4_preregistration_hash"],
        "validation_authorized": False,
    }
    return {**body, "development_freeze_hash": canonical_hash(body)}


def score_transition_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        (
            int(row["frozen_control_score"]),
            int(row["treatment_raw_score"]),
            str(row["eligibility_transition"]),
        )
        for row in rows
    )
    return [
        {
            "control_score": control,
            "treatment_score": treatment,
            "eligibility_transition": transition,
            "count": count,
            "lost_one_rr_point": treatment == control - 1,
        }
        for (control, treatment, transition), count in sorted(counts.items())
    ]


def score_distribution(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    control = Counter(int(row["frozen_control_score"]) for row in rows)
    treatment = Counter(int(row["treatment_raw_score"]) for row in rows)
    return [
        {
            "score": score,
            "control_count": control[score],
            "treatment_count": treatment[score],
            "change": treatment[score] - control[score],
        }
        for score in range(79, 86)
    ]


def score_calibration_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for mapping, field in (
        (CONTROL_MAPPING_NAME, "frozen_control_score"),
        (TREATMENT_MAPPING_NAME, "treatment_raw_score"),
    ):
        for score in range(79, 86):
            selected = [row for row in rows if int(row[field]) == score]
            output.append(cohort_summary(selected, mapping=mapping, score=score))
    return output


def yearly_component_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for year in (2022, 2023, 2024):
        for points in (4, 5):
            selected = [
                row
                for row in rows
                if str(row["decision_date"]).startswith(str(year))
                and int(row["control_rr_points"]) == points
            ]
            output.append(cohort_summary(selected, year=year, control_rr_points=points))
    return output


def _material_direction(delta: Decimal, positive_at: Decimal, negative_at: Decimal) -> int:
    if delta >= positive_at:
        return 1
    if delta <= negative_at:
        return -1
    return 0


def fifth_point_discrimination(
    rr4: Mapping[str, Any],
    rr5: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    if min(int(rr4["count"]), int(rr5["count"])) < 30:
        return "INCONCLUSIVE", {"reason": "COMPARISON_CELL_BELOW_30"}
    deltas = {
        "median_mfe_r": decimal(rr5["median_mfe_r"]) - decimal(rr4["median_mfe_r"]),
        "median_mae_r": decimal(rr5["median_mae_r"]) - decimal(rr4["median_mae_r"]),
        "target_first_rate_pp": decimal(rr5["target_first_rate_pct"]) - decimal(rr4["target_first_rate_pct"]),
        "median_mfe_to_target_ratio": decimal(rr5["median_mfe_to_target_r_ratio"])
        - decimal(rr4["median_mfe_to_target_r_ratio"]),
    }
    directions = {
        "median_mfe_r": _material_direction(deltas["median_mfe_r"], Decimal("0.10"), Decimal("-0.10")),
        "median_mae_r": _material_direction(-deltas["median_mae_r"], Decimal("0.10"), Decimal("-0.10")),
        "target_first_rate": _material_direction(deltas["target_first_rate_pp"], Decimal("3"), Decimal("-3")),
        "median_mfe_to_target_ratio": _material_direction(
            deltas["median_mfe_to_target_ratio"], Decimal("0.05"), Decimal("-0.05")
        ),
    }
    positive = sum(value > 0 for value in directions.values())
    negative = sum(value < 0 for value in directions.values())
    adequate = min(int(rr4["count"]), int(rr5["count"])) >= 100
    if adequate and positive >= 3 and negative == 0:
        result = "CLEAR_POSITIVE_VALUE"
    elif negative >= 3 and positive == 0:
        result = "NEGATIVE_VALUE"
    elif positive > negative:
        result = "WEAK_POSITIVE_VALUE"
    elif positive == 0 and negative == 0:
        result = "NO_CLEAR_VALUE"
    else:
        result = "MIXED"
    return result, {
        "deltas_rr5_minus_rr4": deltas,
        "directions_positive_for_fifth_point": directions,
        "positive_dimension_count": positive,
        "negative_dimension_count": negative,
        "adequate_both_cells": adequate,
    }


def temporal_consistency(
    yearly: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    indexed = {(int(row["year"]), int(row["control_rr_points"])): row for row in yearly}
    directions = []
    for year in (2022, 2023, 2024):
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
                decimal(rr5["median_mfe_to_target_r_ratio"])
                <= decimal(rr4["median_mfe_to_target_r_ratio"]),
            )
        )
        positive = 4 - nonpositive
        direction = "SUPPORTS_CAP4_HYPOTHESIS" if nonpositive >= 3 else "OPPOSES_CAP4_HYPOTHESIS" if positive >= 3 else "MIXED"
        directions.append(
            {
                "year": year,
                "direction": direction,
                "nonpositive_dimension_count": nonpositive,
                "positive_dimension_count": positive,
            }
        )
    if any(row["direction"] == "INCONCLUSIVE" for row in directions):
        return "INCONCLUSIVE", directions
    supportive = sum(row["direction"] == "SUPPORTS_CAP4_HYPOTHESIS" for row in directions)
    opposing = sum(row["direction"] == "OPPOSES_CAP4_HYPOTHESIS" for row in directions)
    if supportive == 3:
        result = "CONSISTENT"
    elif supportive == 2 and opposing == 0:
        result = "MOSTLY_CONSISTENT"
    elif opposing >= 2 and supportive == 0:
        result = "INVERSE"
    else:
        result = "UNSTABLE"
    return result, directions


def portfolio_summary(simulation: Mapping[str, Any], opportunities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics = build_metrics(dict(simulation), list(opportunities), PortfolioBacktestConfig())
    return {
        "portfolio": metrics["portfolio"],
        "trades": metrics["trades"],
        "exits": metrics["exits"],
        "skip_count": len(simulation["skipped"]),
        "skip_reasons": metrics["skip_reasons"],
        "all_invariants_valid": simulation["all_invariants_valid"],
        "invariants": simulation["invariants"],
    }


def run_independent_portfolios(
    context: Any,
    outcomes: Sequence[Mapping[str, Any]],
    analysis_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_key = {str(row["opportunity_id"]): row for row in analysis_rows}
    control = [dict(row) for row in outcomes]
    calendar = build_trading_calendar(context.data_dir, control)
    control_simulation = simulate_portfolio(
        opportunities=control,
        trading_dates=calendar,
        config=PortfolioBacktestConfig(),
    )
    control_summary = portfolio_summary(control_simulation, control)
    observed = decimal(control_summary["portfolio"]["ending_equity"])
    if observed != EXPECTED_CONTROL_ENDING_EQUITY:
        raise ValueError(
            f"Control DEVELOPMENT reproduction failed: {observed} != {EXPECTED_CONTROL_ENDING_EQUITY}"
        )
    treatment = []
    for row in outcomes:
        key = f"{row['decision_date']}|{row['symbol']}"
        score_row = by_key[key]
        if not score_row["treatment_entry_eligible"]:
            continue
        item = dict(row)
        item["raw_strategy_score"] = str(score_row["treatment_raw_score"])
        treatment.append(item)
    treatment_simulation = simulate_portfolio(
        opportunities=treatment,
        trading_dates=calendar,
        config=PortfolioBacktestConfig(),
    )
    treatment_summary = portfolio_summary(treatment_simulation, treatment)
    yearly = []
    for year in (2022, 2023, 2024):
        year_control = [row for row in control if str(row["decision_date"]).startswith(str(year))]
        year_treatment = [row for row in treatment if str(row["decision_date"]).startswith(str(year))]
        year_calendar = build_trading_calendar(context.data_dir, year_control)
        control_year_sim = simulate_portfolio(
            opportunities=year_control,
            trading_dates=year_calendar,
            config=PortfolioBacktestConfig(),
        )
        treatment_year_sim = simulate_portfolio(
            opportunities=year_treatment,
            trading_dates=year_calendar,
            config=PortfolioBacktestConfig(),
        )
        control_year = portfolio_summary(control_year_sim, year_control)
        treatment_year = portfolio_summary(treatment_year_sim, year_treatment)
        yearly.append(
            {
                "year": year,
                "control_ending_equity": control_year["portfolio"]["ending_equity"],
                "treatment_ending_equity": treatment_year["portfolio"]["ending_equity"],
                "ending_equity_delta": decimal(treatment_year["portfolio"]["ending_equity"])
                - decimal(control_year["portfolio"]["ending_equity"]),
                "control_max_drawdown_pct": control_year["portfolio"]["maximum_drawdown_pct"],
                "treatment_max_drawdown_pct": treatment_year["portfolio"]["maximum_drawdown_pct"],
                "max_drawdown_delta_pp": decimal(treatment_year["portfolio"]["maximum_drawdown_pct"])
                - decimal(control_year["portfolio"]["maximum_drawdown_pct"]),
                "control_trade_count": control_year["trades"]["completed_trades"],
                "treatment_trade_count": treatment_year["trades"]["completed_trades"],
                "materially_worse": (
                    decimal(treatment_year["portfolio"]["ending_equity"])
                    <= decimal(control_year["portfolio"]["ending_equity"]) - Decimal("1000")
                    or decimal(treatment_year["portfolio"]["maximum_drawdown_pct"])
                    >= decimal(control_year["portfolio"]["maximum_drawdown_pct"]) + Decimal("2")
                ),
            }
        )
    return {
        "control_opportunities": control,
        "treatment_opportunities": treatment,
        "control_simulation": control_simulation,
        "treatment_simulation": treatment_simulation,
        "control_summary": control_summary,
        "treatment_summary": treatment_summary,
        "yearly": yearly,
    }


def cost_overlay(simulation: Mapping[str, Any], label: str) -> dict[str, Any]:
    config = default_cost_model_config()
    scenario = next(
        item for item in registered_cost_scenarios() if item.scenario_id == SCENARIO_BASELINE_SLIPPAGE
    )
    trades = [
        {**calculate_trade_cost(row, config=config, scenario=scenario), "portfolio": label}
        for row in simulation["trades"]
    ]
    daily, feasibility = build_costed_daily_ledger(
        simulation["daily"],
        trades,
        scenario=scenario,
    )
    summary = scenario_summary(scenario, trades, daily, feasibility)
    return {
        "portfolio": label,
        "trades": trades,
        "daily": daily,
        "summary": summary,
        "cash_feasibility": feasibility,
        "performance_basis": "FROZEN_GENERATED_TRADE_SET_COST_OVERLAY_NOT_COST_AWARE_ADMISSION",
        "cost_aware_admission_executable": False,
    }


def trade_set_comparison(
    control_trades: Sequence[Mapping[str, Any]],
    treatment_trades: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    population = {str(row["opportunity_id"]): row for row in rows}
    control = {str(row["source_key"]): row for row in control_trades}
    treatment = {str(row["source_key"]): row for row in treatment_trades}
    control_keys = set(control)
    treatment_keys = set(treatment)
    union = control_keys | treatment_keys
    intersection = control_keys & treatment_keys
    direct_removed_sources = {
        str(row["opportunity_id"])
        for row in rows
        if row["eligibility_transition"] == "CONTROL_ONLY"
    }
    rows_out = []
    for key in sorted(union):
        state = (
            "TRADED_BOTH"
            if key in intersection
            else "CONTROL_ONLY_TRADE"
            if key in control
            else "TREATMENT_ONLY_REPLACEMENT_TRADE"
        )
        rows_out.append(
            {
                "source_key": key,
                "trade_set_state": state,
                "direct_source_eligibility_removal": key in direct_removed_sources,
                "control_trade_id": control.get(key, {}).get("trade_id", ""),
                "treatment_trade_id": treatment.get(key, {}).get("trade_id", ""),
                "control_score": population[key]["frozen_control_score"],
                "treatment_score": population[key]["treatment_raw_score"],
                "effective_rr": population[key]["effective_rr"],
                "decision_date": population[key]["decision_date"],
                "symbol": population[key]["symbol"],
            }
        )
    control_only = control_keys - treatment_keys
    treatment_only = treatment_keys - control_keys
    unexplained = [
        row
        for row in rows_out
        if row["trade_set_state"] not in {
            "TRADED_BOTH",
            "CONTROL_ONLY_TRADE",
            "TREATMENT_ONLY_REPLACEMENT_TRADE",
        }
    ]
    return {
        "control_trade_count": len(control_keys),
        "treatment_trade_count": len(treatment_keys),
        "intersection_count": len(intersection),
        "control_only_count": len(control_only),
        "treatment_only_replacement_count": len(treatment_only),
        "jaccard_similarity": Decimal(len(intersection)) / Decimal(len(union)) if union else Decimal("1"),
        "direct_removed_control_trade_count": len(control_only & direct_removed_sources),
        "indirect_control_only_trade_count": len(control_only - direct_removed_sources),
        "all_treatment_only_are_source_eligible_replacements": all(
            population[key]["treatment_entry_eligible"] for key in treatment_only
        ),
        "unexplained_changed_trade_count": len(unexplained),
        "rows": rows_out,
        "control_only_keys": sorted(control_only),
        "treatment_only_keys": sorted(treatment_only),
    }


def removed_trade_contribution(
    comparison: Mapping[str, Any],
    control_trades: Sequence[Mapping[str, Any]],
    population_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    control_map = {str(row["source_key"]): row for row in control_trades}
    population = {str(row["opportunity_id"]): row for row in population_rows}
    selected = [control_map[key] for key in comparison["control_only_keys"]]
    realized = [decimal(row["realized_r_multiple"]) for row in selected]
    pnl = [decimal(row["gross_pnl"]) for row in selected]
    return {
        "count": len(selected),
        "gross_pnl": sum(pnl, Decimal("0")),
        "mean_realized_r": mean(realized),
        "median_realized_r": median(realized),
        "exit_distribution": dict(sorted(Counter(str(row["exit_reason"]) for row in selected).items())),
        "year_distribution": dict(sorted(Counter(str(row["decision_date"])[:4] for row in selected).items())),
        "median_effective_rr": median([decimal(population[str(row["source_key"])]["effective_rr"]) for row in selected]),
        "median_target_distance_pct": median(
            [decimal(population[str(row["source_key"])]["target_distance_pct"]) for row in selected]
        ),
        "direct_fifth_point_removal_count": comparison["direct_removed_control_trade_count"],
        "indirect_selection_cascade_count": comparison["indirect_control_only_trade_count"],
    }


def replacement_trade_rows(
    comparison: Mapping[str, Any],
    treatment_trades: Sequence[Mapping[str, Any]],
    population_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    trade_map = {str(row["source_key"]): row for row in treatment_trades}
    population = {str(row["opportunity_id"]): row for row in population_rows}
    output = []
    for key in comparison["treatment_only_keys"]:
        trade = trade_map[key]
        source = population[key]
        output.append(
            {
                "source_key": key,
                "symbol": source["symbol"],
                "decision_date": source["decision_date"],
                "reason_admitted": "DETERMINISTIC_SLOT_OR_RANKING_SUBSTITUTION_AFTER_CAP4_ELIGIBILITY_CHANGE",
                "treatment_score": source["treatment_raw_score"],
                "effective_rr": source["effective_rr"],
                "gross_pnl": trade["gross_pnl"],
                "realized_r_multiple": trade["realized_r_multiple"],
                "exit_reason": trade["exit_reason"],
                "year": str(source["decision_date"])[:4],
                "source_treatment_eligible": source["treatment_entry_eligible"],
            }
        )
    return output


def retained_improvement(
    control_rows: Sequence[Mapping[str, Any]],
    retained_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    control = cohort_summary(control_rows, cohort="CONTROL_ELIGIBLE")
    retained = cohort_summary(retained_rows, cohort="ELIGIBLE_BOTH")
    dimensions = {
        "median_mfe_improved": decimal(retained["median_mfe_r"]) > decimal(control["median_mfe_r"]),
        "median_mae_improved": decimal(retained["median_mae_r"]) < decimal(control["median_mae_r"]),
        "target_first_improved": decimal(retained["target_first_rate_pct"])
        > decimal(control["target_first_rate_pct"]),
        "stop_first_improved": decimal(retained["stop_first_rate_pct"])
        < decimal(control["stop_first_rate_pct"]),
    }
    return {
        "control": control,
        "retained": retained,
        "dimensions": dimensions,
        "improved_dimension_count": sum(dimensions.values()),
    }


def falsification_results(
    *,
    discrimination: str,
    temporal_directions: Sequence[Mapping[str, Any]],
    removed_count: int,
    retained: Mapping[str, Any],
    yearly_portfolios: Sequence[Mapping[str, Any]],
    trade_comparison: Mapping[str, Any],
    source_treatment_only_count: int,
    control_cost: Mapping[str, Any],
    treatment_cost: Mapping[str, Any],
    control_gross_ending: Any,
    treatment_gross_ending: Any,
) -> dict[str, Any]:
    opposing_years = sum(row["direction"] == "OPPOSES_CAP4_HYPOTHESIS" for row in temporal_directions)
    a_triggered = discrimination == "CLEAR_POSITIVE_VALUE" and opposing_years >= 2
    b_triggered = removed_count > 0 and int(retained["improved_dimension_count"]) < 2
    materially_worse_years = sum(bool(row["materially_worse"]) for row in yearly_portfolios)
    c_triggered = materially_worse_years >= 2
    d_triggered = (
        source_treatment_only_count > 0
        or int(trade_comparison["unexplained_changed_trade_count"]) > 0
        or decimal(trade_comparison["jaccard_similarity"]) < Decimal("0.50")
    )
    gross_better = decimal(treatment_gross_ending) > decimal(control_gross_ending)
    net_better = decimal(treatment_cost["summary"]["ending_equity"]) > decimal(
        control_cost["summary"]["ending_equity"]
    )
    e_triggered = gross_better and not net_better
    return {
        "A": {"hypothesis_passed": not a_triggered, "triggered": a_triggered, "opposing_year_count": opposing_years},
        "B": {
            "hypothesis_passed": not b_triggered,
            "triggered": b_triggered,
            "retained_improved_dimension_count": retained["improved_dimension_count"],
        },
        "C": {
            "hypothesis_passed": not c_triggered,
            "triggered": c_triggered,
            "materially_worse_year_count": materially_worse_years,
        },
        "D": {
            "hypothesis_passed": not d_triggered,
            "triggered": d_triggered,
            "source_treatment_only_count": source_treatment_only_count,
            "unexplained_changed_trade_count": trade_comparison["unexplained_changed_trade_count"],
            "jaccard_similarity": trade_comparison["jaccard_similarity"],
        },
        "E": {
            "hypothesis_passed": not e_triggered,
            "triggered": e_triggered,
            "gross_treatment_better": gross_better,
            "net_treatment_better": net_better,
        },
    }


def classify_experiment(
    *,
    discrimination: str,
    rr4: Mapping[str, Any],
    rr5: Mapping[str, Any],
    temporal: str,
    falsification: Mapping[str, Any],
    retained: Mapping[str, Any],
    control_portfolio: Mapping[str, Any],
    treatment_portfolio: Mapping[str, Any],
    control_cost: Mapping[str, Any],
    treatment_cost: Mapping[str, Any],
    integrity_ok: bool,
) -> dict[str, Any]:
    nonpositive = discrimination in {"NO_CLEAR_VALUE", "NEGATIVE_VALUE", "MIXED"}
    distance_without_achievement = (
        decimal(rr5["median_target_distance_pct"]) > decimal(rr4["median_target_distance_pct"])
        and decimal(rr5["target_first_rate_pct"]) <= decimal(rr4["target_first_rate_pct"])
        and decimal(rr5["median_mfe_to_target_r_ratio"])
        <= decimal(rr4["median_mfe_to_target_r_ratio"])
    )
    portfolio_delta = decimal(treatment_portfolio["portfolio"]["ending_equity"]) - decimal(
        control_portfolio["portfolio"]["ending_equity"]
    )
    portfolio_not_materially_worse = portfolio_delta >= Decimal("-1000")
    cost_delta = decimal(treatment_cost["summary"]["ending_equity"]) - decimal(
        control_cost["summary"]["ending_equity"]
    )
    cost_not_reversed = not (portfolio_delta > 0 and cost_delta <= 0)
    supports = {
        "nonpositive_fifth_point": nonpositive,
        "distance_without_achievement": distance_without_achievement,
        "temporal": temporal in {"CONSISTENT", "MOSTLY_CONSISTENT"},
        "retained_source_improves": int(retained["improved_dimension_count"]) >= 2,
        "portfolio_not_materially_worse": portfolio_not_materially_worse,
        "cost_not_reversed": cost_not_reversed,
        "integrity": integrity_ok,
    }
    triggered = [key for key, value in falsification.items() if value["triggered"]]
    adequate = min(int(rr4["count"]), int(rr5["count"])) >= 300
    if not adequate or not integrity_ok:
        experiment = "INCONCLUSIVE"
    elif not triggered and all(supports.values()):
        experiment = "SUPPORTED_FOR_NEXT_STAGE"
    elif "A" in triggered or "C" in triggered or "D" in triggered:
        experiment = "NOT_SUPPORTED"
    elif sum(supports.values()) >= 5 and len(triggered) <= 1:
        experiment = "WEAKLY_SUPPORTED"
    else:
        experiment = "MIXED"
    hypothesis = {
        "SUPPORTED_FOR_NEXT_STAGE": "SURVIVES_DEVELOPMENT_TEST",
        "WEAKLY_SUPPORTED": "WEAKENS",
        "MIXED": "WEAKENS",
        "NOT_SUPPORTED": "REJECTED",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[experiment]
    validation_consideration = (
        experiment == "SUPPORTED_FOR_NEXT_STAGE"
        and adequate
        and discrimination != "CLEAR_POSITIVE_VALUE"
        and temporal in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        and portfolio_not_materially_worse
        and cost_not_reversed
        and integrity_ok
    )
    return {
        "RR_CAP4_EXPERIMENT_RESULT": experiment,
        "RR_FIFTH_POINT_HYPOTHESIS": hypothesis,
        "ELIGIBLE_FOR_VALIDATION_CONSIDERATION": "YES" if validation_consideration else "NO",
        "support_evidence": supports,
        "triggered_falsification_criteria": triggered,
    }


def build_pilot(
    rows: Sequence[Mapping[str, Any]],
    control_trades: Sequence[Mapping[str, Any]],
    treatment_trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    control_trade_keys = {str(row["source_key"]) for row in control_trades}
    treatment_trade_keys = {str(row["source_key"]) for row in treatment_trades}
    control_only_trade_keys = control_trade_keys - treatment_trade_keys
    replacement_keys = treatment_trade_keys - control_trade_keys
    selectors: tuple[tuple[str, Callable[[Mapping[str, Any]], bool], Callable[[Sequence[Mapping[str, Any]]], Mapping[str, Any]] | None], ...] = (
        ("RR_1_5_TO_LT_2_REMAINS_3", lambda row: Decimal("1.5") <= decimal(row["effective_rr"]) < 2, None),
        ("RR_2_TO_LT_2_5_REMAINS_4", lambda row: 2 <= decimal(row["effective_rr"]) < Decimal("2.5"), None),
        ("RR_GE_2_5_CHANGES_5_TO_4", lambda row: decimal(row["effective_rr"]) >= Decimal("2.5"), None),
        ("CONTROL_85_TO_84", lambda row: int(row["frozen_control_score"]) == 85 and int(row["treatment_raw_score"]) == 84, None),
        ("CONTROL_80_TO_79", lambda row: int(row["frozen_control_score"]) == 80 and int(row["treatment_raw_score"]) == 79, None),
        ("CONTROL_84_TO_83", lambda row: int(row["frozen_control_score"]) == 84 and int(row["treatment_raw_score"]) == 83, None),
        ("HIGH_RR_LARGE_TARGET", lambda row: int(row["control_rr_points"]) == 5, lambda values: max(values, key=lambda row: decimal(row["target_distance_pct"]))),
        ("HIGH_RR_LOW_MFE", lambda row: int(row["control_rr_points"]) == 5, lambda values: min(values, key=lambda row: decimal(row["mfe_r_4"]))),
        ("RR4_TARGET_FIRST", lambda row: int(row["control_rr_points"]) == 4 and row["first_touch_outcome"] == "TARGET_FIRST", None),
        ("RR5_TARGET_FIRST", lambda row: int(row["control_rr_points"]) == 5 and row["first_touch_outcome"] == "TARGET_FIRST", None),
        ("REMOVED_SOURCE_OPPORTUNITY", lambda row: row["eligibility_transition"] == "CONTROL_ONLY", None),
        ("RETAINED_OPPORTUNITY", lambda row: row["eligibility_transition"] == "ELIGIBLE_BOTH", None),
        ("CONTROL_ONLY_PORTFOLIO_TRADE", lambda row: str(row["opportunity_id"]) in control_only_trade_keys, None),
        ("REPLACEMENT_TREATMENT_PORTFOLIO_TRADE", lambda row: str(row["opportunity_id"]) in replacement_keys, None),
    )
    cases = []
    for category, predicate, chooser in selectors:
        available = [row for row in rows if predicate(row)]
        if not available:
            cases.append({"category": category, "availability": "NOT_AVAILABLE", "validation_result": "NOT_AVAILABLE"})
            continue
        selected = chooser(available) if chooser else sorted(available, key=lambda row: str(row["opportunity_id"]))[0]
        key = str(selected["opportunity_id"])
        checks = {
            "development_only": DEFAULT_TEMPORAL_CONFIG.development_start
            <= date.fromisoformat(str(selected["decision_date"]))
            <= DEFAULT_TEMPORAL_CONFIG.development_end,
            "control_mapping_reproduced": control_rr_points(selected["effective_rr"])
            == int(selected["control_rr_points"]),
            "treatment_mapping_reproduced": treatment_rr_points(selected["effective_rr"])
            == int(selected["treatment_rr_points"]),
            "score_arithmetic_reproduced": treatment_score(
                int(selected["frozen_control_score"]),
                int(selected["control_rr_points"]),
                int(selected["treatment_rr_points"]),
            )
            == int(selected["treatment_raw_score"]),
            "eligibility_reproduced": bool(selected["treatment_entry_eligible"])
            == (bool(selected["control_entry_eligible"]) and int(selected["treatment_raw_score"]) >= ENTRY_THRESHOLD),
            "target_distance_present": selected.get("target_distance_pct") is not None,
            "outcome_present": selected.get("first_touch_outcome") is not None,
            "year_present": str(selected["decision_date"])[:4] in {"2022", "2023", "2024"},
            "portfolio_linkage_reproduced": (
                (key in control_trade_keys) if category == "CONTROL_ONLY_PORTFOLIO_TRADE" else True
            )
            and ((key in treatment_trade_keys) if category == "REPLACEMENT_TREATMENT_PORTFOLIO_TRADE" else True),
        }
        cases.append(
            {
                "category": category,
                "availability": "AVAILABLE",
                "opportunity_id": key,
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "year": str(selected["decision_date"])[:4],
                "effective_rr": selected["effective_rr"],
                "control_rr_points": selected["control_rr_points"],
                "treatment_rr_points": selected["treatment_rr_points"],
                "control_score": selected["frozen_control_score"],
                "treatment_score": selected["treatment_raw_score"],
                "control_eligible": selected["control_entry_eligible"],
                "treatment_eligible": selected["treatment_entry_eligible"],
                "target_distance_pct": selected["target_distance_pct"],
                "target_distance_r": selected["target_distance_r"],
                "mfe_r": selected["mfe_r_4"],
                "mae_r": selected["mae_r_4"],
                "outcome": selected["first_touch_outcome"],
                "control_portfolio_trade": key in control_trade_keys,
                "treatment_portfolio_trade": key in treatment_trade_keys,
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


def _artifact_root(root: Path) -> Path:
    return root / "data/research/experiments/strategy/v1/rr_cap4_command_01"


def _report_root(root: Path) -> Path:
    return root / "data/reports"


def _storage(paths: Iterable[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    return {
        "artifact_count_excluding_summary_and_documentation": len(existing),
        "bytes_excluding_summary_and_documentation": sum(path.stat().st_size for path in existing),
        "paths": [str(path) for path in existing],
    }


def run_rr_cap4_experiment(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    started = time.perf_counter()

    def notify(message: str) -> None:
        if progress:
            progress(message)

    notify("Verifying frozen checkpoint and all baseline dependencies through Step 02.15 Command 03")
    before = baseline_snapshot(root)
    dependencies = preregistration_dependencies(before)
    notify("Building and freezing the DEVELOPMENT population before outcome analysis")
    population_rows, analysis_rows, outcomes, context = build_population(root)
    population_hash = freeze_population(population_rows)
    artifact_root = _artifact_root(root)
    report_root = _report_root(root)
    population_manifest_path = artifact_root / "population_manifest_v1.json"
    write_json(
        population_manifest_path,
        {
            "experiment_id": EXPERIMENT_ID,
            "experiment_version": EXPERIMENT_VERSION,
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
            "partition_key": "decision_date",
            "source_count": len(population_rows),
            "rr_calibration_population_hash": population_hash,
            "immutable_before_outcome_analysis": True,
            "rows": population_rows,
        },
    )
    preregistration = build_preregistration(population_hash, dependencies)
    prereg_path = artifact_root / "registry/rr_cap4_controlled_experiment_registry_v1_preregistered.json"
    write_json(prereg_path, preregistration)
    development_freeze = build_development_freeze(population_hash, preregistration)
    freeze_path = artifact_root / "experiment_freeze_v1.json"
    write_json(freeze_path, development_freeze)

    notify("Calculating frozen source transitions and R:R4-versus-R:R5 discrimination")
    transitions = score_transition_rows(analysis_rows)
    distributions = score_distribution(analysis_rows)
    calibration = score_calibration_rows(analysis_rows)
    rr_profiles = [
        cohort_summary(
            [row for row in analysis_rows if int(row["control_rr_points"]) == points],
            control_rr_points=points,
        )
        for points in (4, 5)
    ]
    rr4, rr5 = rr_profiles
    discrimination, discrimination_evidence = fifth_point_discrimination(rr4, rr5)
    yearly_component = yearly_component_rows(analysis_rows)
    temporal, temporal_directions = temporal_consistency(yearly_component)
    removed = [row for row in analysis_rows if row["eligibility_transition"] == "CONTROL_ONLY"]
    retained_rows = [row for row in analysis_rows if row["eligibility_transition"] == "ELIGIBLE_BOTH"]
    control_eligible_rows = [row for row in analysis_rows if row["control_entry_eligible"]]
    removed_summary = cohort_summary(removed, cohort="CONTROL_ONLY")
    retained_summary = cohort_summary(retained_rows, cohort="ELIGIBLE_BOTH")
    retained_evidence = retained_improvement(control_eligible_rows, retained_rows)

    notify("Reproducing the independent control portfolio before running the sole CAP4 treatment")
    portfolios = run_independent_portfolios(context, outcomes, analysis_rows)
    control_sim = portfolios["control_simulation"]
    treatment_sim = portfolios["treatment_simulation"]
    notify("Applying the frozen baseline-slippage cost overlay to both generated trade sets")
    control_cost = cost_overlay(control_sim, "CONTROL")
    treatment_cost = cost_overlay(treatment_sim, "TREATMENT")
    trade_comparison = trade_set_comparison(control_sim["trades"], treatment_sim["trades"], analysis_rows)
    removed_trades = removed_trade_contribution(trade_comparison, control_sim["trades"], analysis_rows)
    replacements = replacement_trade_rows(trade_comparison, treatment_sim["trades"], analysis_rows)
    pilot = build_pilot(analysis_rows, control_sim["trades"], treatment_sim["trades"])

    after = baseline_snapshot(root)
    baseline_unchanged = before == after
    source_treatment_only_count = sum(row["eligibility_transition"] == "TREATMENT_ONLY" for row in analysis_rows)
    integrity_ok = (
        baseline_unchanged
        and control_sim["all_invariants_valid"]
        and treatment_sim["all_invariants_valid"]
        and source_treatment_only_count == 0
        and pilot["passed"]
        and control_cost["summary"]["trade_cost_reconciliation_violations"] == 0
        and treatment_cost["summary"]["trade_cost_reconciliation_violations"] == 0
    )
    falsification = falsification_results(
        discrimination=discrimination,
        temporal_directions=temporal_directions,
        removed_count=len(removed),
        retained=retained_evidence,
        yearly_portfolios=portfolios["yearly"],
        trade_comparison=trade_comparison,
        source_treatment_only_count=source_treatment_only_count,
        control_cost=control_cost,
        treatment_cost=treatment_cost,
        control_gross_ending=portfolios["control_summary"]["portfolio"]["ending_equity"],
        treatment_gross_ending=portfolios["treatment_summary"]["portfolio"]["ending_equity"],
    )
    classifications = classify_experiment(
        discrimination=discrimination,
        rr4=rr4,
        rr5=rr5,
        temporal=temporal,
        falsification=falsification,
        retained=retained_evidence,
        control_portfolio=portfolios["control_summary"],
        treatment_portfolio=portfolios["treatment_summary"],
        control_cost=control_cost,
        treatment_cost=treatment_cost,
        integrity_ok=integrity_ok,
    )
    classifications["FIFTH_RR_POINT_DISCRIMINATION_RESULT"] = discrimination
    classifications["RR_FIFTH_POINT_TEMPORAL_CONSISTENCY"] = temporal

    result = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "population_hash": population_hash,
        "parameter_hash": preregistration["experiments"][0]["parameter_hash"],
        "pre_registration_hash": preregistration["rr_cap4_preregistration_hash"],
        "development_freeze_hash": development_freeze["development_freeze_hash"],
        "source_transitions": dict(sorted(Counter(row["eligibility_transition"] for row in analysis_rows).items())),
        "score_distributions": distributions,
        "rr4_vs_rr5": rr_profiles,
        "discrimination_evidence": discrimination_evidence,
        "removed_cohort": removed_summary,
        "retained_cohort": retained_summary,
        "retained_improvement": retained_evidence,
        "yearly_component": yearly_component,
        "temporal_directions": temporal_directions,
        "control_portfolio": portfolios["control_summary"],
        "treatment_portfolio": portfolios["treatment_summary"],
        "yearly_portfolios": portfolios["yearly"],
        "trade_set_comparison": {key: value for key, value in trade_comparison.items() if key not in {"rows", "control_only_keys", "treatment_only_keys"}},
        "removed_trade_contribution": removed_trades,
        "replacement_trade_count": len(replacements),
        "control_cost_overlay": control_cost["summary"],
        "treatment_cost_overlay": treatment_cost["summary"],
        "falsification": falsification,
        "classifications": classifications,
        "pilot": pilot,
        "baseline_hashes_unchanged": baseline_unchanged,
        "baseline_mutation_violations": 0 if baseline_unchanged else 1,
        "development_result_hash": "",
    }
    result["development_result_hash"] = canonical_hash(result)
    result_path = artifact_root / f"runs/{EXPERIMENT_ID}/result.json"
    write_json(result_path, result)
    completed_registry = {
        **preregistration,
        "experiments": [
            {
                **preregistration["experiments"][0],
                "status": "COMPLETE",
                "result_fingerprint": result["development_result_hash"],
                "result_path": str(result_path),
            }
        ],
    }
    registry_path = artifact_root / "registry/rr_cap4_controlled_experiment_registry_v1.json"
    write_json(registry_path, completed_registry)
    run_manifest_path = artifact_root / "run_manifest_v1.json"
    write_json(
        run_manifest_path,
        {
            "experiment_id": EXPERIMENT_ID,
            "population_hash": population_hash,
            "parameter_hash": result["parameter_hash"],
            "pre_registration_hash": result["pre_registration_hash"],
            "development_freeze_hash": result["development_freeze_hash"],
            "development_result_hash": result["development_result_hash"],
            "baseline_hashes_unchanged": baseline_unchanged,
            "validation_state": SEALED,
            "validation_run_count": 0,
            "validation_authorized": False,
        },
    )

    report_paths = {name: report_root / name for name in REPORT_FILENAMES}
    write_csv(report_paths[REPORT_FILENAMES[1]], analysis_rows)
    write_csv(report_paths[REPORT_FILENAMES[2]], transitions)
    write_csv(report_paths[REPORT_FILENAMES[3]], rr_profiles)
    write_csv(report_paths[REPORT_FILENAMES[4]], removed)
    write_csv(report_paths[REPORT_FILENAMES[5]], retained_rows)
    write_csv(report_paths[REPORT_FILENAMES[6]], yearly_component)
    write_csv(report_paths[REPORT_FILENAMES[7]], control_sim["trades"])
    write_csv(report_paths[REPORT_FILENAMES[8]], treatment_sim["trades"])
    write_csv(report_paths[REPORT_FILENAMES[9]], trade_comparison["rows"])
    write_csv(report_paths[REPORT_FILENAMES[10]], replacements)
    write_csv(report_paths[REPORT_FILENAMES[11]], [*control_cost["trades"], *treatment_cost["trades"]])
    write_csv(report_paths[REPORT_FILENAMES[12]], pilot["cases"])

    required_ignored = (
        "backend/.env",
        "data/research/experiments/strategy/v1/rr_cap4_command_01/experiment_freeze_v1.json",
        "data/reports/rr_cap4_v1_summary.json",
        "data/reports/rr_cap4_v1_population.csv",
    )
    output_ignore_checks = {path: _git_ignored(root, path) for path in required_ignored}
    persisted_paths = [
        population_manifest_path,
        prereg_path,
        freeze_path,
        result_path,
        registry_path,
        run_manifest_path,
        *[report_paths[name] for name in REPORT_FILENAMES[1:]],
    ]
    runtime = time.perf_counter() - started
    summary: dict[str, Any] = {
        "phase": "Step 02.16",
        "command": "Command 01",
        "experiment_version": EXPERIMENT_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "profile": PROFILE,
        "experiment_type": EXPERIMENT_TYPE,
        "population": {
            "source_count": len(analysis_rows),
            "control_eligible_count": sum(row["control_entry_eligible"] for row in analysis_rows),
            "treatment_eligible_count": sum(row["treatment_entry_eligible"] for row in analysis_rows),
            "rr_calibration_population_hash": population_hash,
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
        },
        "pre_registration": {
            "experiment_count": 1,
            "experiment_ids": [EXPERIMENT_ID],
            "parameter_hash": result["parameter_hash"],
            "rr_cap4_preregistration_hash": result["pre_registration_hash"],
            "definitions_frozen_before_results": True,
            "path": str(prereg_path),
        },
        "development_freeze": development_freeze,
        "mechanical_effect": {
            "transition_counts": result["source_transitions"],
            "rows_losing_one_point": sum(
                int(row["treatment_raw_score"]) == int(row["frozen_control_score"]) - 1
                for row in analysis_rows
            ),
            "score_transitions": transitions,
            "score_distributions": distributions,
            "control_eligibility_dependent_on_fifth_point_pct": _rate(len(removed), len(control_eligible_rows)),
            "treatment_only_source_rows": source_treatment_only_count,
            "effective_rr_values_changed": 0,
            "other_component_values_changed": 0,
        },
        "source_analysis": {
            "rr4_vs_rr5": rr_profiles,
            "removed_cohort": removed_summary,
            "retained_cohort": retained_summary,
            "retained_improvement": retained_evidence,
            "score_calibration": calibration,
        },
        "yearly_component": yearly_component,
        "temporal_directions": temporal_directions,
        "portfolios": {
            "control": portfolios["control_summary"],
            "treatment": portfolios["treatment_summary"],
            "yearly_independent": portfolios["yearly"],
            "control_reproduction": {
                "expected_ending_equity": EXPECTED_CONTROL_ENDING_EQUITY,
                "observed_ending_equity": portfolios["control_summary"]["portfolio"]["ending_equity"],
                "passed": decimal(portfolios["control_summary"]["portfolio"]["ending_equity"])
                == EXPECTED_CONTROL_ENDING_EQUITY,
            },
        },
        "trade_set": {
            **{key: value for key, value in trade_comparison.items() if key not in {"rows", "control_only_keys", "treatment_only_keys"}},
            "removed_trade_contribution": removed_trades,
            "replacement_trade_count": len(replacements),
            "selection_changes_beyond_direct_removals": trade_comparison["indirect_control_only_trade_count"]
            + len(replacements),
        },
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "control": control_cost["summary"],
            "treatment": treatment_cost["summary"],
            "warning": "Frozen generated-trade-set overlay only; admissions were not rerun with costs and net figures are not executable cost-aware portfolios.",
            "control_cost_aware_admission_executable": False,
            "treatment_cost_aware_admission_executable": False,
        },
        "discrimination_evidence": discrimination_evidence,
        "falsification": falsification,
        "classifications": classifications,
        "pilot": pilot,
        "baseline_regression": {
            "before": before,
            "after": after,
            "all_frozen_hashes_unchanged": baseline_unchanged,
            "baseline_mutation_violations": 0 if baseline_unchanged else 1,
        },
        "governance": {
            "validation_state": SEALED,
            "validation_authorized": False,
            "validation_run_count": 0,
            "validation_rows_accessed": 0,
            "holdout_performance_exposed": False,
            "alternative_rr_mappings_tested": 0,
            "threshold_changed": False,
            "target_changed": False,
            "stop_changed": False,
            "ranking_methodology_changed": False,
            "intraday_rule_combined": False,
            "optimizer_or_ml_used": False,
            "score_v2_created": False,
            "strategy_v2_created": False,
            "strategy_v1_modified": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "security": {
            "output_ignore_checks": output_ignore_checks,
            "all_required_outputs_ignored": all(output_ignore_checks.values()),
            "broker_secrets_logged": False,
            "provider_headers_logged": False,
            "order_endpoints_used": False,
        },
        "tests": {"backend_passed": bool(tests_passed)},
        "frontend": {"build_passed": bool(frontend_build_passed), "tile_added": False},
        "paths": {
            "population_manifest": str(population_manifest_path),
            "registry": str(registry_path),
            "preregistration_registry": str(prereg_path),
            "experiment_freeze": str(freeze_path),
            "result": str(result_path),
            "run_manifest": str(run_manifest_path),
            "reports": [str(report_paths[name]) for name in REPORT_FILENAMES],
            "documentation": str(root / "docs/rr-score-cap4-controlled-experiment-v1.md"),
        },
        "runtime_seconds": runtime,
        "storage": _storage(persisted_paths),
        "known_limitations": [
            "All empirical evidence is DEVELOPMENT-only; validation remains sealed.",
            "Source eligibility starts from the frozen mechanically valid ENTRY_ELIGIBLE population, so INELIGIBLE_BOTH is structurally zero.",
            "Portfolio substitutions are endogenous consequences of chronological slots and ranking, not direct component evidence.",
            "Cost results are frozen trade-set overlays; admissions are not cost-aware and any cash-feasibility warning remains explicit.",
            "Daily OHLC preserves the frozen conservative same-bar ambiguity convention rather than reconstructing intraday execution.",
        ],
        "recommended_next_action": "Review this DEVELOPMENT result only; do not access validation, promote CAP4, or create Score/Strategy V2 automatically.",
        "ready_for_review": False,
    }
    summary["ready_for_review"] = bool(
        integrity_ok
        and summary["portfolios"]["control_reproduction"]["passed"]
        and all(output_ignore_checks.values())
        and tests_passed
        and frontend_build_passed
        and summary["governance"]["validation_run_count"] == 0
        and summary["governance"]["live_signals"] == 0
        and summary["governance"]["live_orders"] == 0
    )
    write_json(report_paths[REPORT_FILENAMES[0]], summary)
    notify(
        f"Completed controlled R:R CAP4 experiment in {runtime:.2f}s; validation stayed sealed and no live path was used"
    )
    return summary


__all__ = (
    "CONTROL_MAPPING",
    "CONTROL_MAPPING_NAME",
    "ENTRY_THRESHOLD",
    "EXPERIMENT_ID",
    "EXPERIMENT_VERSION",
    "FALSIFICATION_CRITERIA",
    "FIFTH_POINT_CLASSIFICATION_RULES",
    "PROFILE",
    "REPORT_FILENAMES",
    "SAMPLE_WARNINGS",
    "TREATMENT_MAPPING",
    "TREATMENT_MAPPING_NAME",
    "TEMPORAL_RULES",
    "build_development_freeze",
    "build_pilot",
    "build_population",
    "build_preregistration",
    "classify_experiment",
    "cohort_summary",
    "control_rr_points",
    "eligibility_transition",
    "fifth_point_discrimination",
    "freeze_population",
    "run_rr_cap4_experiment",
    "sample_warning",
    "score_distribution",
    "score_transition_rows",
    "temporal_consistency",
    "treatment_rr_points",
    "treatment_score",
    "validate_development_only",
)

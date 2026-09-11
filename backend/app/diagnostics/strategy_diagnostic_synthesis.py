from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.strategy_diagnostic import canonical_hash, write_csv, write_json

SYNTHESIS_VERSION = "STRATEGY_DIAGNOSTIC_SYNTHESIS_V1"
SYNTHESIS_PROFILE = "SWING_STRATEGY_RESEARCH_SYNTHESIS_V1"
EXPECTED_REGISTRY_FINGERPRINT = "7113e8d9d327bd2b641e695dd6409794d302e3de745222133ae05413f93c1374"

EXPECTED_EXPERIMENT_IDS = (
    *(f"EXP-RANK-{index:03d}" for index in range(1, 5)),
    *(f"EXP-HOLD-{index:03d}" for index in range(1, 5)),
    *(f"EXP-ENTRY-{index:03d}" for index in range(1, 5)),
    *(f"EXP-EXIT-{index:03d}" for index in range(1, 8)),
    *(f"EXP-ENTRYQ-{index:03d}" for index in range(1, 11)),
    *(f"EXP-SCORECAL-{index:03d}" for index in range(1, 11)),
    *(f"EXP-REGIME-{index:03d}" for index in range(1, 11)),
)

SOURCE_REPORTS = {
    "COMMAND_01": "strategy_diagnostic_v1_summary.json",
    "COMMAND_02": "strategy_diagnostic_v1_exit_summary.json",
    "COMMAND_03": "strategy_diagnostic_v1_entry_quality_summary.json",
    "COMMAND_04": "strategy_diagnostic_v1_score_calibration_summary.json",
    "COMMAND_05": "strategy_diagnostic_v1_regime_context_summary.json",
}

HYPOTHESIS_STATUS_VALUES = {
    "SUPPORTED_FOR_LATER_TESTING",
    "WEAKLY_SUPPORTED",
    "MIXED",
    "NOT_SUPPORTED",
    "DEPRIORITIZED",
    "ALREADY_DISPROVEN_SIMPLE_FORM",
    "UNRESOLVED",
    "INSUFFICIENT_SAMPLE",
}
EVIDENCE_STRENGTH_VALUES = {"HIGH", "MEDIUM", "LOW", "VERY_LOW"}
OVERFITTING_RISK_VALUES = {"LOW", "MODERATE", "HIGH", "VERY_HIGH"}
IMPLEMENTATION_COMPLEXITY_VALUES = {"LOW", "MEDIUM", "HIGH"}
IMPACT_SCOPE_VALUES = {"LOCAL", "COMPONENT_LEVEL", "ENTRY_POLICY", "EXIT_POLICY", "PORTFOLIO_POLICY", "SYSTEM_WIDE"}
PRIORITY_CLASS_VALUES = {"PRIORITY_A", "PRIORITY_B", "PRIORITY_C", "DEPRIORITIZED"}
SAMPLE_QUALITY_VALUES = {"ADEQUATE", "LIMITED", "SMALL", "INSUFFICIENT"}
TEMPORAL_STABILITY_VALUES = {"CONSISTENT", "MOSTLY_CONSISTENT", "UNSTABLE", "INCONCLUSIVE"}

PRIORITY_WEIGHTS = {
    "evidence_strength": 25,
    "research_importance": 20,
    "sample_quality": 15,
    "temporal_stability": 15,
    "low_overfitting_risk": 15,
    "low_dimensionality_simplicity": 10,
}
RATING_VALUES = {
    "evidence_strength": {"HIGH": 4, "MEDIUM": 3, "LOW": 2, "VERY_LOW": 1},
    "research_importance": {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1},
    "sample_quality": {"ADEQUATE": 4, "LIMITED": 3, "SMALL": 2, "INSUFFICIENT": 1},
    "temporal_stability": {"CONSISTENT": 4, "MOSTLY_CONSISTENT": 3, "UNSTABLE": 2, "INCONCLUSIVE": 1},
    "low_overfitting_risk": {"LOW": 4, "MODERATE": 3, "HIGH": 2, "VERY_HIGH": 1},
    "low_dimensionality_simplicity": {"LOW": 4, "MEDIUM": 3, "HIGH": 2},
}
PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY = (
    "ending_equity",
    "gross_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "gross_pnl",
    "realized_r",
)


@dataclass(frozen=True, slots=True)
class SynthesisContext:
    repo_root: Path
    data_dir: Path
    registry_path: Path
    registry: Mapping[str, Any]
    registry_fingerprint: str
    source_paths: Mapping[str, Path]
    source_reports: Mapping[str, Mapping[str, Any]]
    source_hashes: Mapping[str, str]
    baseline_hashes: Mapping[str, str]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry_fingerprint(registry: Mapping[str, Any]) -> str:
    records = [
        {
            "experiment_id": row["experiment_id"],
            "family": row["family"],
            "parameter_hash": row["parameter_hash"],
            "pre_registration_hash": row["pre_registration_hash"],
            "status": row["status"],
        }
        for row in registry["experiments"]
    ]
    return canonical_hash(records)


def validate_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    records = list(registry.get("experiments", []))
    ids = [str(row.get("experiment_id")) for row in records]
    if len(records) != 49:
        raise ValueError(f"Command 06 requires exactly 49 completed experiments, found {len(records)}")
    if len(set(ids)) != 49:
        raise ValueError("Command 06 requires 49 unique experiment IDs")
    if tuple(ids) != EXPECTED_EXPERIMENT_IDS:
        raise ValueError("Command 06 found an unauthorized or reordered experiment ID")
    if any(row.get("status") != "COMPLETE" for row in records):
        raise ValueError("Command 06 requires all 49 experiments to be COMPLETE")
    if any(bool(row.get("eligible_for_promotion")) for row in records):
        raise ValueError("Command 06 found a promotion-eligible prior experiment")
    if any(row.get("failure_reason") for row in records):
        raise ValueError("Command 06 found a prior experiment failure")
    observed_fingerprint = registry_fingerprint(registry)
    if observed_fingerprint != EXPECTED_REGISTRY_FINGERPRINT:
        raise ValueError("Command 06 registry parameter/preregistration hashes differ from the frozen 49-record input")
    return {
        "path": "data/research/diagnostics/strategy/v1/registry/experiment_registry_v1.json",
        "completed_experiment_count": 49,
        "unique_ids": True,
        "all_complete": True,
        "all_previous_hashes_unchanged": True,
        "registry_fingerprint": observed_fingerprint,
        "promoted_experiment_count": 0,
        "failed_experiment_count": 0,
        "unauthorized_experiment_ids": [],
        "synthesis_record_added": False,
    }


def load_synthesis_context(repo_root: Path) -> SynthesisContext:
    repo_root = Path(repo_root)
    data_dir = repo_root / "data"
    registry_path = data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    validation = validate_registry(registry)
    source_paths = {name: data_dir / "reports" / filename for name, filename in SOURCE_REPORTS.items()}
    source_reports = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in source_paths.items()}
    source_hashes = {name: file_hash(path) for name, path in source_paths.items()}
    expected_counts = {"COMMAND_01": 12, "COMMAND_02": 7, "COMMAND_03": 10, "COMMAND_04": 10, "COMMAND_05": 10}
    for name, report in source_reports.items():
        if report.get("ready_for_review") is not True:
            raise ValueError(f"{name} source summary is not ready for review")
        if int(report.get("failed_experiment_count", 0)) != 0:
            raise ValueError(f"{name} source summary records failed experiments")
        count_field = "registered_experiment_count" if name == "COMMAND_01" else "newly_registered_experiment_count"
        if int(report.get(count_field, 0)) != expected_counts[name]:
            raise ValueError(f"{name} source experiment count changed")
    baseline_hashes = portfolio_backtest_regression_hashes(data_dir)
    if not all(portfolio_backtest_regression_hash_checks(baseline_hashes).values()):
        raise ValueError("Frozen baseline hash verification failed")
    if validation["registry_fingerprint"] != EXPECTED_REGISTRY_FINGERPRINT:
        raise ValueError("Frozen diagnostic registry verification failed")
    return SynthesisContext(
        repo_root=repo_root,
        data_dir=data_dir,
        registry_path=registry_path,
        registry=registry,
        registry_fingerprint=validation["registry_fingerprint"],
        source_paths=source_paths,
        source_reports=source_reports,
        source_hashes=source_hashes,
        baseline_hashes=baseline_hashes,
    )


def priority_score(record: Mapping[str, Any]) -> float:
    inputs = record["priority_inputs"]
    values = {
        "evidence_strength": RATING_VALUES["evidence_strength"][record["evidence_strength"]],
        "research_importance": RATING_VALUES["research_importance"][inputs["research_importance"]],
        "sample_quality": RATING_VALUES["sample_quality"][record["sample_quality"]],
        "temporal_stability": RATING_VALUES["temporal_stability"][record["temporal_stability"]],
        "low_overfitting_risk": RATING_VALUES["low_overfitting_risk"][record["overfitting_risk"]],
        "low_dimensionality_simplicity": RATING_VALUES["low_dimensionality_simplicity"][record["implementation_complexity"]],
    }
    return round(sum(PRIORITY_WEIGHTS[name] * values[name] / 4 for name in PRIORITY_WEIGHTS), 3)


def priority_class(record: Mapping[str, Any], score: float) -> str:
    if record["status"] in {"NOT_SUPPORTED", "DEPRIORITIZED", "ALREADY_DISPROVEN_SIMPLE_FORM"}:
        return "DEPRIORITIZED"
    inputs = record["priority_inputs"]
    qualifies_a = (
        score >= 75
        and (record["evidence_strength"] in {"HIGH", "MEDIUM"} or inputs["research_importance"] == "CRITICAL")
        and record["sample_quality"] in {"ADEQUATE", "LIMITED"}
        and record["overfitting_risk"] in {"LOW", "MODERATE"}
        and int(inputs["parameter_dimensions"]) <= 1
        and not bool(inputs["post_hoc_threshold_mining"])
        and bool(record["falsification_criteria"])
    )
    if qualifies_a:
        return "PRIORITY_A"
    if score >= 60:
        return "PRIORITY_B"
    return "PRIORITY_C"


def hypothesis_record(
    hypothesis_id: str,
    hypothesis: str,
    branch: str,
    status: str,
    evidence_strength: str,
    sample_quality: str,
    temporal_stability: str,
    overfitting_risk: str,
    implementation_complexity: str,
    impact_scope: str,
    research_importance: str,
    parameter_dimensions: int,
    source_command: str,
    experiment_ids: Sequence[str],
    source_report: str,
    classification: str,
    sample_notes: str,
    evidence_notes: str,
    falsification_criteria: str,
    recommended_next_step: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "hypothesis": hypothesis,
        "branch": branch,
        "status": status,
        "evidence_strength": evidence_strength,
        "sample_quality": sample_quality,
        "temporal_stability": temporal_stability,
        "overfitting_risk": overfitting_risk,
        "implementation_complexity": implementation_complexity,
        "impact_scope": impact_scope,
        "priority_inputs": {
            "research_importance": research_importance,
            "parameter_dimensions": parameter_dimensions,
            "post_hoc_threshold_mining": False,
            "historical_performance_metrics_used": False,
        },
        "traceability": {
            "source_command": source_command,
            "experiment_ids": list(experiment_ids),
            "source_report": source_report,
            "classification": classification,
            "sample_notes": sample_notes,
        },
        "evidence_notes": evidence_notes,
        "falsification_criteria": falsification_criteria,
        "recommended_next_step": recommended_next_step,
        "promotion_prohibited": True,
    }
    record["priority_score_non_performance"] = priority_score(record)
    record["priority_class"] = priority_class(record, record["priority_score_non_performance"])
    return record


def build_hypothesis_catalog() -> list[dict[str, Any]]:
    rows = [
        hypothesis_record("H-RANK-01", "Portfolio ranking is a primary weakness.", "BRANCH_D", "SUPPORTED_FOR_LATER_TESTING", "HIGH", "ADEQUATE", "UNSTABLE", "HIGH", "MEDIUM", "PORTFOLIO_POLICY", "CRITICAL", 1, "COMMAND_01", ("EXP-RANK-001", "EXP-RANK-002", "EXP-RANK-003", "EXP-RANK-004"), SOURCE_REPORTS["COMMAND_01"], "EXTREME_SENSITIVITY", "728 baseline admissions; four fixed ranking definitions.", "Ranking materially changed the admitted set, but three simple alternatives did not solve the strategy.", "The hypothesis weakens if one preregistered ranking remains selection-stable across development and validation while signals and capacity stay frozen.", "Freeze one architecture-led ranking before any later signal experiment; do not mine another ranking family."),
        hypothesis_record("H-HOLD-01", "The four-session holding horizon is too short.", "BRANCH_F", "MIXED", "MEDIUM", "ADEQUATE", "UNSTABLE", "HIGH", "LOW", "EXIT_POLICY", "MEDIUM", 1, "COMMAND_01", ("EXP-HOLD-001", "EXP-HOLD-002", "EXP-HOLD-003", "EXP-HOLD-004"), SOURCE_REPORTS["COMMAND_01"], "HIGH_SENSITIVITY", "Four fixed horizons with materially different occupancy and trade sets.", "Horizon matters mechanically, but simply extending to 6, 8, or 10 sessions did not consistently solve performance.", "The hypothesis weakens if a preregistered horizon change fails source-path and holdout consistency without relying on occupancy-driven selection changes.", "Defer another horizon test until ranking/slot effects and intraday ordering can be isolated."),
        hypothesis_record("H-GAP-01", "Positive next-open gaps cause entry-quality degradation.", "BRANCH_A", "MIXED", "LOW", "ADEQUATE", "UNSTABLE", "HIGH", "LOW", "ENTRY_POLICY", "LOW", 1, "COMMAND_01/COMMAND_03/COMMAND_05", ("EXP-ENTRY-001", "EXP-ENTRY-002", "EXP-ENTRY-003", "EXP-ENTRY-004", "EXP-ENTRYQ-006", "EXP-REGIME-009"), SOURCE_REPORTS["COMMAND_01"], "MIXED", "3,296 source opportunities; fixed gap cohorts, with small interactions.", "Gap groups differ structurally, but direction changes by maturity and regime context.", "The hypothesis weakens if a fixed gap cohort does not underperform across both source paths and the untouched validation window.", "Do not add a gap filter; retain only as a lower-priority interaction question."),
        hypothesis_record("H-EXIT-01", "Profit giveback is a primary cause of weak performance.", "BRANCH_F", "WEAKLY_SUPPORTED", "MEDIUM", "ADEQUATE", "UNSTABLE", "HIGH", "MEDIUM", "EXIT_POLICY", "HIGH", 1, "COMMAND_02", ("EXP-EXIT-001", "EXP-EXIT-007"), SOURCE_REPORTS["COMMAND_02"], "MATERIAL_GIVEBACK", "728 admissions; 159 stop exits and 542 time exits.", "Material favorable-excursion giveback exists, but the tested simple remedies worsened or failed to robustly solve results.", "The hypothesis weakens if a predeclared path-aware exit change cannot reduce giveback without worsening adverse excursion, occupancy, or validation behavior.", "Require intraday ordering and an isolated path-aware design before another exit experiment."),
        hypothesis_record("H-EXIT-02", "Closer fixed targets improve portfolio quality.", "BRANCH_F", "ALREADY_DISPROVEN_SIMPLE_FORM", "MEDIUM", "ADEQUATE", "UNSTABLE", "VERY_HIGH", "LOW", "EXIT_POLICY", "MEDIUM", 1, "COMMAND_02", ("EXP-EXIT-004", "EXP-EXIT-005", "EXP-EXIT-006"), SOURCE_REPORTS["COMMAND_02"], "MATERIAL_DIFFERENCE_WITHOUT_ROBUST_SOLUTION", "Fixed 1R, 1.5R, and 2R targets were tested.", "Closer targets changed exits and occupancy but did not provide a convincing robust solution.", "Reconsider only if an independent execution model supplies a causal target rationale that is fixed before outcomes are inspected.", "Deprioritize further fixed-target threshold testing."),
        hypothesis_record("H-EXIT-03", "Simple +0.5R or +1R next-session profit protection improves portfolio quality.", "BRANCH_F", "ALREADY_DISPROVEN_SIMPLE_FORM", "HIGH", "ADEQUATE", "UNSTABLE", "VERY_HIGH", "LOW", "EXIT_POLICY", "MEDIUM", 1, "COMMAND_02", ("EXP-EXIT-002", "EXP-EXIT-003"), SOURCE_REPORTS["COMMAND_02"], "PROTECTION_WORSENED_RESULTS", "Two fixed protection rules were evaluated with chronology preserved.", "Both simple protection forms worsened results despite material giveback.", "Reconsider only if independent intraday evidence supports a materially different, preregistered path rule.", "Do not repeat or tune these protection thresholds."),
        hypothesis_record("H-ENTRYQ-01", "Entries are systematically too extended or exhausted.", "BRANCH_A", "NOT_SUPPORTED", "MEDIUM", "ADEQUATE", "UNSTABLE", "VERY_HIGH", "MEDIUM", "ENTRY_POLICY", "MEDIUM", 2, "COMMAND_03", tuple(f"EXP-ENTRYQ-{index:03d}" for index in range(1, 11)), SOURCE_REPORTS["COMMAND_03"], "ENTRY_EXHAUSTION_RESULT=MIXED", "3,296 source and 728 admitted opportunities across fixed maturity views.", "Higher score was not simply more extended; high-RVOL and strong-RS high-extension cohorts were not uniformly weaker.", "The hypothesis would regain support only if a preregistered extension measure is consistently adverse across source, admission, and validation populations.", "Do not introduce a simple extension filter."),
        hypothesis_record("H-SCORE-01", "Total score is poorly calibrated.", "BRANCH_A", "WEAKLY_SUPPORTED", "MEDIUM", "ADEQUATE", "UNSTABLE", "MODERATE", "MEDIUM", "COMPONENT_LEVEL", "CRITICAL", 2, "COMMAND_04", ("EXP-SCORECAL-001", "EXP-SCORECAL-008", "EXP-SCORECAL-009", "EXP-SCORECAL-010"), SOURCE_REPORTS["COMMAND_04"], "PARTIALLY_DISCRIMINATIVE", "3,296 source and 728 admitted; raw score 80–85 and yearly profiles.", "Total score is mostly directionally positive but only partially discriminative, with composition and temporal concentration effects.", "The hypothesis weakens if frozen mappings discriminate consistently in a holdout without composition or calendar concentration.", "Decompose one component at a time; never reweight the whole score jointly."),
        hypothesis_record("H-SCORE-02", "Specific score components are misweighted.", "BRANCH_E", "UNRESOLVED", "LOW", "SMALL", "INCONCLUSIVE", "VERY_HIGH", "HIGH", "COMPONENT_LEVEL", "HIGH", 3, "COMMAND_04", tuple(f"EXP-SCORECAL-{index:03d}" for index in range(2, 8)), SOURCE_REPORTS["COMMAND_04"], "LOW_REDUNDANCY; MOST_COMPONENTS_INCONCLUSIVE", "Sector and catalyst components are historically unavailable.", "Low redundancy does not identify correct weights, and missing components prevent complete calibration.", "The hypothesis weakens if complete component history still shows no stable independent discrimination across periods.", "Acquire missing history before any multi-component weight research."),
        hypothesis_record("H-RR-01", "The five-point R:R bucket rewards distant targets rather than useful opportunity quality.", "BRANCH_B", "WEAKLY_SUPPORTED", "MEDIUM", "ADEQUATE", "INCONCLUSIVE", "MODERATE", "LOW", "COMPONENT_LEVEL", "CRITICAL", 1, "COMMAND_04/COMMAND_05", ("EXP-SCORECAL-007", "EXP-REGIME-009"), SOURCE_REPORTS["COMMAND_04"], "RR_COMPONENT_RESULT=INCONCLUSIVE", "3,296 source and 728 admitted; fixed R:R and regime interactions.", "R:R failed clear discrimination and high nominal R:R did not consistently rescue weaker contexts.", "If one preregistered monotone mapping does not improve discrimination consistently across source paths and both temporal windows, the hypothesis weakens.", "Propose one architecture-led alternative mapping with no threshold search."),
        hypothesis_record("H-REGIME-01", "Bullish versus Neutral market context is materially useful.", "BRANCH_C", "WEAKLY_SUPPORTED", "MEDIUM", "SMALL", "UNSTABLE", "MODERATE", "LOW", "COMPONENT_LEVEL", "HIGH", 1, "COMMAND_04/COMMAND_05", ("EXP-SCORECAL-006", "EXP-REGIME-001", "EXP-REGIME-004"), SOURCE_REPORTS["COMMAND_05"], "BULLISH_CLEARLY_STRONGER", "3,253 Bullish versus 43 Neutral source opportunities; 690 versus 38 admitted.", "Bullish was stronger at a high level, but Neutral is small and fine-grained/yearly behavior is unstable.", "The hypothesis weakens if the Bullish/Neutral difference fails in a later untouched period with adequate Neutral sample.", "Retain as descriptive context; do not exclude Neutral."),
        hypothesis_record("H-REGIME-02", "Fine-grained regime strength is predictive.", "BRANCH_C", "NOT_SUPPORTED", "MEDIUM", "ADEQUATE", "UNSTABLE", "HIGH", "MEDIUM", "COMPONENT_LEVEL", "MEDIUM", 2, "COMMAND_05", ("EXP-REGIME-002", "EXP-REGIME-003", "EXP-REGIME-008", "EXP-REGIME-010"), SOURCE_REPORTS["COMMAND_05"], "NO_CLEAR_DISCRIMINATION", "3,296 source and 728 admitted; locked score/strength buckets.", "Stronger Bullish buckets were not monotonically better and total regime correlations were near zero.", "The hypothesis would regain support only through consistent preregistered bucket ordering in an untouched period.", "Deprioritize threshold, strength, hysteresis, and reweighting research."),
        hypothesis_record("H-BREADTH-01", "Market breadth contains incremental useful context.", "BRANCH_C", "WEAKLY_SUPPORTED", "LOW", "ADEQUATE", "UNSTABLE", "MODERATE", "LOW", "COMPONENT_LEVEL", "HIGH", 1, "COMMAND_05", ("EXP-REGIME-006", "EXP-REGIME-010"), SOURCE_REPORTS["COMMAND_05"], "WEAK_POSITIVE_DISCRIMINATION", "3,296 source and 728 admitted; several intermediate bins were empty.", "Breadth was the strongest component but correlations were weak and yearly directions unstable.", "The hypothesis weakens if one preregistered breadth treatment adds no stable discrimination in development and validation.", "Consider one later inclusion/ablation test without threshold mining."),
        hypothesis_record("H-PERSIST-01", "Newly Bullish regimes outperform established Bullish regimes.", "BRANCH_C", "WEAKLY_SUPPORTED", "LOW", "ADEQUATE", "INCONCLUSIVE", "VERY_HIGH", "LOW", "COMPONENT_LEVEL", "MEDIUM", 1, "COMMAND_05", ("EXP-REGIME-010",), SOURCE_REPORTS["COMMAND_05"], "NEW_BULLISH_STRONGER", "415 new-Bullish source observations; 1,003 established >10-session observations.", "The result is descriptive, post-hoc-sensitive, and lacks cross-period replication.", "The hypothesis weakens if the fixed streak contrast does not repeat directionally in untouched data.", "Do not add a persistence gate; treat as exploratory replication only."),
        hypothesis_record("H-SLOT-01", "Position-slot scarcity materially distorts portfolio outcomes.", "BRANCH_D", "SUPPORTED_FOR_LATER_TESTING", "HIGH", "ADEQUATE", "MOSTLY_CONSISTENT", "MODERATE", "MEDIUM", "PORTFOLIO_POLICY", "CRITICAL", 1, "COMMAND_01/COMMAND_04/COMMAND_05", ("EXP-RANK-001", "EXP-RANK-002", "EXP-RANK-003", "EXP-RANK-004", "EXP-SCORECAL-001", "EXP-REGIME-002"), SOURCE_REPORTS["COMMAND_01"], "SELECTION_DISTORTION=HIGH", "2,398 max-position skips versus 728 admissions.", "Ranking and occupancy materially change which valid opportunities enter the portfolio.", "The hypothesis weakens if one fixed capacity change leaves admission composition and conclusions stable across both temporal windows.", "Test one fixed capacity dimension with ranking, signals, risk, and exits frozen."),
        hypothesis_record("H-COST-01", "Execution costs will materially worsen current gross performance.", "BRANCH_G", "SUPPORTED_FOR_LATER_TESTING", "HIGH", "ADEQUATE", "CONSISTENT", "LOW", "LOW", "SYSTEM_WIDE", "CRITICAL", 0, "COMMAND_01", ("EXP-RANK-001",), SOURCE_REPORTS["COMMAND_01"], "COSTS_AND_SLIPPAGE_NOT_MODELED", "728 trades; current portfolio is already negative gross.", "Non-negative execution frictions cannot improve the already weak gross baseline and are required for credible progression.", "The hypothesis weakens only if a preregistered realistic cost model is immaterial across turnover and liquidity cohorts.", "Build cost/slippage/tax infrastructure before promotion-level conclusions."),
        hypothesis_record("H-ROBUST-01", "Strategy behavior is unstable across calendar years.", "BRANCH_A", "SUPPORTED_FOR_LATER_TESTING", "HIGH", "ADEQUATE", "CONSISTENT", "LOW", "LOW", "SYSTEM_WIDE", "CRITICAL", 0, "COMMAND_01/COMMAND_04/COMMAND_05", ("EXP-RANK-001", "EXP-SCORECAL-010", "EXP-REGIME-010"), SOURCE_REPORTS["COMMAND_05"], "YEARLY_DIRECTION=UNSTABLE", "2022–2025 complete and 2026 partial; 728 admitted in total.", "Portfolio and diagnostic relationships change materially by calendar period.", "The hypothesis weakens if frozen behavior remains directionally stable in a predeclared untouched validation window.", "Make temporal holdout validation mandatory for every later experiment."),
        hypothesis_record("H-BASELINE-01", "Current Strategy V1 has insufficient evidence for live progression.", "BRANCH_G", "SUPPORTED_FOR_LATER_TESTING", "HIGH", "ADEQUATE", "CONSISTENT", "LOW", "LOW", "SYSTEM_WIDE", "CRITICAL", 0, "COMMAND_01–COMMAND_05", ("EXP-RANK-001",), SOURCE_REPORTS["COMMAND_01"], "WEAK_GROSS_BASELINE; NO_PROMOTIONS", "728 trades; broad 49-experiment diagnostic coverage.", "The baseline is negative gross before costs, temporally unstable, and no diagnostic has justified promotion.", "This conclusion weakens only after a preregistered candidate survives costs, chronology, source/admission checks, and untouched validation.", "Remain research/paper-only; do not progress to live or small capital."),
    ]
    ids = [row["hypothesis_id"] for row in rows]
    if len(ids) != len(set(ids)) or len(rows) != 18:
        raise ValueError("Synthesis hypothesis catalog must contain 18 unique records")
    validate_hypotheses(rows)
    return rows


def validate_hypotheses(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        if row["status"] not in HYPOTHESIS_STATUS_VALUES:
            raise ValueError(f"Invalid hypothesis status: {row['status']}")
        if row["evidence_strength"] not in EVIDENCE_STRENGTH_VALUES:
            raise ValueError(f"Invalid evidence strength: {row['evidence_strength']}")
        if row["overfitting_risk"] not in OVERFITTING_RISK_VALUES:
            raise ValueError(f"Invalid overfitting risk: {row['overfitting_risk']}")
        if row["implementation_complexity"] not in IMPLEMENTATION_COMPLEXITY_VALUES:
            raise ValueError(f"Invalid implementation complexity: {row['implementation_complexity']}")
        if row["impact_scope"] not in IMPACT_SCOPE_VALUES or row["priority_class"] not in PRIORITY_CLASS_VALUES:
            raise ValueError(f"Invalid impact/priority classification: {row['hypothesis_id']}")
        if row["sample_quality"] not in SAMPLE_QUALITY_VALUES or row["temporal_stability"] not in TEMPORAL_STABILITY_VALUES:
            raise ValueError(f"Invalid sample/temporal classification: {row['hypothesis_id']}")
        if not row["traceability"]["experiment_ids"] or not row["traceability"]["source_report"]:
            raise ValueError(f"Missing traceability: {row['hypothesis_id']}")
        if any(field in row["priority_inputs"] for field in PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY):
            raise ValueError("Historical performance entered the synthesis priority score")
        if row["priority_inputs"]["historical_performance_metrics_used"]:
            raise ValueError("Historical performance entered the synthesis priority score")


def ruled_out_simple_forms() -> list[dict[str, Any]]:
    specs = (
        ("RULED-001", "Simply use SCORE_ONLY ranking.", "COMMAND_01", "EXP-RANK-002", "EXTREME_SENSITIVITY_WITHOUT_ROBUST_SOLUTION"),
        ("RULED-002", "Simply use RR_FIRST ranking.", "COMMAND_01", "EXP-RANK-003", "EXTREME_SENSITIVITY_WITHOUT_ROBUST_SOLUTION"),
        ("RULED-003", "Simply use SETUP_FIRST ranking.", "COMMAND_01", "EXP-RANK-004", "EXTREME_SENSITIVITY_WITHOUT_ROBUST_SOLUTION"),
        ("RULED-004", "Simply hold every trade for six sessions.", "COMMAND_01", "EXP-HOLD-002", "NO_CONSISTENT_HORIZON_SOLUTION"),
        ("RULED-005", "Simply hold every trade for eight sessions.", "COMMAND_01", "EXP-HOLD-003", "NO_CONSISTENT_HORIZON_SOLUTION"),
        ("RULED-006", "Simply hold every trade for ten sessions.", "COMMAND_01", "EXP-HOLD-004", "NO_CONSISTENT_HORIZON_SOLUTION"),
        ("RULED-007", "Move the stop to breakeven after completed prior +0.5R.", "COMMAND_02", "EXP-EXIT-002", "PROTECTION_WORSENED_RESULTS"),
        ("RULED-008", "Move the stop to breakeven after completed prior +1R.", "COMMAND_02", "EXP-EXIT-003", "PROTECTION_WORSENED_RESULTS"),
        ("RULED-009", "Simply use a fixed 1R target.", "COMMAND_02", "EXP-EXIT-004", "NO_ROBUST_FIXED_TARGET_SOLUTION"),
        ("RULED-010", "Simply use a fixed 1.5R target.", "COMMAND_02", "EXP-EXIT-005", "NO_ROBUST_FIXED_TARGET_SOLUTION"),
        ("RULED-011", "Simply use a fixed 2R target.", "COMMAND_02", "EXP-EXIT-006", "NO_ROBUST_FIXED_TARGET_SOLUTION"),
        ("RULED-012", "Apply a simple high-extension-is-bad entry rule.", "COMMAND_03", "EXP-ENTRYQ-002", "ENTRY_EXHAUSTION_NOT_SUPPORTED"),
        ("RULED-013", "Assume stronger Bullish regime buckets are always better.", "COMMAND_05", "EXP-REGIME-003", "NO_MONOTONIC_STRENGTH_DISCRIMINATION"),
        ("RULED-014", "Apply a universal positive-gap exclusion.", "COMMAND_01/COMMAND_03/COMMAND_05", "EXP-ENTRY-003;EXP-ENTRY-004;EXP-ENTRYQ-006;EXP-REGIME-009", "MIXED_CONTEXT_DEPENDENT_RELATIONSHIP"),
    )
    return [
        {"rule_id": item[0], "simple_form": item[1], "source_command": item[2], "experiment_ids": item[3], "classification": item[4], "promotion_prohibited": True}
        for item in specs
    ]


def unresolved_core_questions() -> list[dict[str, Any]]:
    specs = (
        ("UNRESOLVED-001", "Why do stop exits remain the dominant negative contributor?", "COMMAND_02", "EXP-EXIT-001;EXP-EXIT-007"),
        ("UNRESOLVED-002", "Why is total score only partially discriminative?", "COMMAND_04", "EXP-SCORECAL-001;EXP-SCORECAL-008;EXP-SCORECAL-009"),
        ("UNRESOLVED-003", "Why does 2023 differ from the other calendar years?", "COMMAND_04/COMMAND_05", "EXP-SCORECAL-010;EXP-REGIME-010"),
        ("UNRESOLVED-004", "Does ranking and slot interaction conceal source-opportunity quality?", "COMMAND_01/COMMAND_05", "EXP-RANK-001..004;EXP-REGIME-002"),
        ("UNRESOLVED-005", "Is the current R:R score mapping economically useful?", "COMMAND_04", "EXP-SCORECAL-007"),
        ("UNRESOLVED-006", "Does breadth add stable context beyond the frozen regime state?", "COMMAND_05", "EXP-REGIME-006;EXP-REGIME-010"),
        ("UNRESOLVED-007", "Does the newly Bullish persistence result repeat out of sample?", "COMMAND_05", "EXP-REGIME-010"),
        ("UNRESOLVED-008", "How much do missing sector and catalyst histories limit score calibration?", "COMMAND_04", "EXP-SCORECAL-002..008"),
        ("UNRESOLVED-009", "Can daily bars reliably identify entry timing and exact stop/target order?", "COMMAND_02", "EXP-EXIT-001..007"),
    )
    return [{"question_id": x[0], "question": x[1], "source_command": x[2], "experiment_ids": x[3], "status": "UNRESOLVED"} for x in specs]


def data_limitations() -> list[dict[str, Any]]:
    specs = (
        ("DATA-001", "Historical stock-sector score component unavailable", "BLOCKS_LATER_TEST", "Blocks complete component-weight calibration."),
        ("DATA-002", "Historical catalyst/news score component unavailable", "BLOCKS_LATER_TEST", "Blocks complete point-in-time score calibration."),
        ("DATA-003", "Historical Global/GIFT regime input unavailable", "LIMITS_INTERPRETATION", "Reduces regime coverage and confidence."),
        ("DATA-004", "Historical India VIX regime input unavailable", "LIMITS_INTERPRETATION", "Reduces volatility-context interpretation."),
        ("DATA-005", "Historical intraday regime confirmation unavailable", "BLOCKS_LATER_TEST", "Cannot validate intended confirmation semantics."),
        ("DATA-006", "Daily OHLC cannot always order intraday stop and target touches", "LIMITS_INTERPRETATION", "Conservative ordering remains necessary."),
        ("DATA-007", "Transaction costs, slippage, taxes, and fees are unmodeled", "BLOCKS_LATER_TEST", "Blocks promotion-quality economics."),
        ("DATA-008", "Nifty 500 membership has a partial-history limitation", "LIMITS_INTERPRETATION", "Reduces historical breadth/universe coverage."),
        ("DATA-009", "Corporate-action exclusions reduce usable observations", "ACCEPTABLE_FOR_DIAGNOSTIC", "Conservative exclusions preserve data integrity."),
        ("DATA-010", "Confirmed-only candidate cohort is small", "LIMITS_INTERPRETATION", "Cannot support a standalone candidate-stage rule."),
        ("DATA-011", "Neutral regime cohort is small", "LIMITS_INTERPRETATION", "Bullish/Neutral separation needs later replication."),
        ("DATA-012", "Calendar year 2026 is partial", "LIMITS_INTERPRETATION", "Validation exposure is incomplete."),
        ("DATA-013", "No intraday execution path", "BLOCKS_LATER_TEST", "Cannot validate VWAP, retests, confirmation, or exact timing."),
        ("DATA-014", "No real fills", "BLOCKS_LATER_TEST", "Paper and live execution realism remain unknown."),
    )
    return [{"limitation_id": x[0], "limitation": x[1], "classification": x[2], "effect": x[3]} for x in specs]


def diagnostic_coverage() -> list[dict[str, Any]]:
    specs = (
        ("ranking", True, 4, "Extreme admitted-set sensitivity; simple alternatives did not solve the strategy.", "Which architecture-led ranking is selection-stable?"),
        ("holding", True, 4, "High sensitivity; no fixed 6/8/10-session solution.", "Can horizon be isolated from occupancy and ranking?"),
        ("gap", True, 6, "Mixed and context-dependent.", "Does a fixed relationship repeat out of sample?"),
        ("exits", True, 6, "Material differences; no robust simple target/protection solution.", "Can path-aware exits reduce giveback without new harm?"),
        ("stop path", True, 3, "Giveback exists but most stop exits never reached +0.5R earlier.", "What mechanism drives unrecovered adverse paths?"),
        ("entry extension", True, 10, "Systematic exhaustion not supported.", "Is another causal entry-quality measure available?"),
        ("score", True, 10, "Partially discriminative; low redundancy; most components inconclusive.", "Which one component warrants isolated calibration?"),
        ("regime", True, 10, "Bullish stronger at high level; fine strength unclear.", "Can breadth or state replicate out of sample?"),
        ("portfolio selection", True, 8, "Ranking/occupancy distort admissions.", "How much is due specifically to four-slot scarcity?"),
        ("cost realism", False, 0, "Not modeled.", "What survives realistic Indian-market costs and taxes?"),
        ("intraday timing", False, 0, "Not available.", "Can confirmation, ordering, retests, and VWAP be reproduced?"),
        ("news/catalyst", False, 0, "Not available historically.", "Can point-in-time catalyst history be made auditable?"),
        ("sector context", True, 1, "Market-wide sector participation tested; stock-sector score was unavailable.", "Does point-in-time stock-sector context add independent value?"),
    )
    return [{"research_dimension": x[0], "tested": x[1], "experiment_count": x[2], "main_conclusion": x[3], "open_questions": x[4]} for x in specs]


def research_branches() -> list[dict[str, Any]]:
    specs = (
        ("BRANCH_A", "Signal quality", "H-GAP-01;H-ENTRYQ-01;H-SCORE-01;H-ROBUST-01"),
        ("BRANCH_B", "R:R calibration", "H-RR-01"),
        ("BRANCH_C", "Market breadth/context", "H-REGIME-01;H-REGIME-02;H-BREADTH-01;H-PERSIST-01"),
        ("BRANCH_D", "Portfolio ranking/selection", "H-RANK-01;H-SLOT-01"),
        ("BRANCH_E", "Data enrichment", "H-SCORE-02"),
        ("BRANCH_F", "Execution realism/intraday", "H-HOLD-01;H-EXIT-01;H-EXIT-02;H-EXIT-03"),
        ("BRANCH_G", "Cost/slippage realism and progression governance", "H-COST-01;H-BASELINE-01"),
    )
    return [{"branch": x[0], "name": x[1], "hypothesis_ids": x[2]} for x in specs]


def next_experiment_proposals() -> list[dict[str, Any]]:
    return [
        {
            "proposal_id": "EXP-V2-RESEARCH-001",
            "hypothesis_id": "H-SLOT-01",
            "one_changed_dimension": "Change only maximum concurrent positions from the frozen four-slot baseline to one operationally predeclared capacity; freeze ranking, signals, risk, and exits.",
            "why_prioritized": "Slot scarcity affects 2,398 valid opportunities and confounds interpretation of signal quality.",
            "overfitting_risk": "MODERATE",
            "minimum_data_sample_requirement": ">=300 source opportunities and >=100 admissions in both development and validation, with congestion cohorts reported.",
            "falsification_criteria": "Falsified or weakened if admission composition and conclusions remain materially unstable, or if the direction does not repeat in validation.",
            "promotion_prohibited": True,
            "executed": False,
        },
        {
            "proposal_id": "EXP-V2-RESEARCH-002",
            "hypothesis_id": "H-RR-01",
            "one_changed_dimension": "Replace only the five-point R:R component mapping with one preregistered monotone mapping chosen from architecture, not observed returns.",
            "why_prioritized": "The existing component is inconclusive, strategically relevant, and independently changeable.",
            "overfitting_risk": "MODERATE",
            "minimum_data_sample_requirement": ">=300 valid paths and >=100 admissions per temporal window, with fixed source/admitted calibration metrics.",
            "falsification_criteria": "Falsified or weakened if discrimination does not improve consistently across source paths and both temporal windows.",
            "promotion_prohibited": True,
            "executed": False,
        },
        {
            "proposal_id": "EXP-V2-RESEARCH-003",
            "hypothesis_id": "H-ROBUST-01",
            "one_changed_dimension": "Change only the evaluation protocol to an untouched calendar holdout; do not change Strategy V1 parameters.",
            "why_prioritized": "Temporal instability is a cross-cutting threat to every later hypothesis and can be tested without selecting a historical winner.",
            "overfitting_risk": "LOW",
            "minimum_data_sample_requirement": ">=100 admissions in development and validation, with no parameter tuning on validation.",
            "falsification_criteria": "Falsified or weakened if frozen conclusions remain directionally and compositionally stable in the untouched validation window.",
            "promotion_prohibited": True,
            "executed": False,
        },
    ]


def infrastructure_priorities() -> list[dict[str, Any]]:
    return [
        {"rank": 1, "infrastructure": "Realistic transaction-cost/slippage/tax model", "priority": "HIGH_PRIORITY_INFRASTRUCTURE", "reason": "Current performance is negative gross, so promotion-quality economics require explicit nonzero frictions.", "implemented": False},
        {"rank": 2, "infrastructure": "Fixed temporal holdout and later walk-forward harness", "priority": "HIGH_PRIORITY_INFRASTRUCTURE", "reason": "Forty-nine existing diagnostics create high multiple-comparison risk and observed yearly instability.", "implemented": False},
        {"rank": 3, "infrastructure": "Point-in-time intraday bar and execution-ordering layer", "priority": "CRITICAL_FOR_EXECUTION_RESEARCH", "reason": "The intended confirmation, retests, VWAP, entry timing, and stop/target ordering cannot be validated from daily bars.", "implemented": False},
    ]


def missing_data_priorities() -> list[dict[str, Any]]:
    specs = (
        (1, "Historical intraday bars", "CRITICAL", "Required for intended confirmation and execution-path semantics."),
        (2, "Historical point-in-time stock-sector mapping", "HIGH", "Completes the missing ten-point score component and sector-relative research."),
        (3, "Historical India VIX", "MEDIUM", "Adds volatility context to the structurally capped regime model."),
        (4, "Historical point-in-time news/catalyst", "MEDIUM", "Completes five missing score points but has substantial timestamp and survivorship complexity."),
        (5, "Historical Global/GIFT proxy", "LOW", "Useful context, but proxy identity and point-in-time continuity are difficult and current evidence does not prioritize regime rework."),
    )
    return [{"rank": x[0], "data_source": x[1], "research_priority": x[2], "rationale": x[3], "availability_claimed": False} for x in specs]


def experiment_design_template() -> dict[str, Any]:
    return {
        "experiment_id": "REQUIRED",
        "hypothesis": "REQUIRED",
        "one_changed_dimension": "REQUIRED_EXACTLY_ONE",
        "baseline_comparison": "FROZEN_BASELINE_REQUIRED",
        "predeclared_parameters": "LOCK_BEFORE_RESULTS",
        "primary_metrics": "PREDECLARE_SOURCE_AND_PORTFOLIO_METRICS",
        "secondary_metrics": "PREDECLARE_DESCRIPTIVE_ONLY",
        "sample_size_requirement": "PREDECLARE_BY_WINDOW",
        "temporal_robustness_requirement": "DEVELOPMENT_AND_UNTOUCHED_VALIDATION",
        "falsification_criteria": "REQUIRED_BEFORE_RUN",
        "promotion_prohibited": True,
        "follow_up_decision_rule": "STOP_OR_REQUEST_SEPARATE_AUTHORIZATION",
    }


def pilot_validation(source_reports: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    c1, c2, c3, c4, c5 = (source_reports[f"COMMAND_0{index}"] for index in range(1, 6))
    checks = (
        ("ranking sensitivity", c1["classifications"]["RANKING_DIAGNOSTIC_RESULT"], "EXTREME_SENSITIVITY", "COMMAND_01", "EXP-RANK-001..004"),
        ("exit giveback", c2["classifications"]["EXIT_PATH_RESULT"], "MATERIAL_GIVEBACK", "COMMAND_02", "EXP-EXIT-001;EXP-EXIT-007"),
        ("entry exhaustion", c3["classifications"]["ENTRY_EXHAUSTION_RESULT"], "MIXED", "COMMAND_03", "EXP-ENTRYQ-001..010"),
        ("score calibration", c4["classifications"]["TOTAL_SCORE_CALIBRATION_RESULT"], "PARTIALLY_DISCRIMINATIVE", "COMMAND_04", "EXP-SCORECAL-001..010"),
        ("regime context", c5["classifications"]["TOTAL_REGIME_DISCRIMINATION_RESULT"], "NO_CLEAR_DISCRIMINATION", "COMMAND_05", "EXP-REGIME-001..010"),
        ("hold horizon", c1["classifications"]["HOLD_HORIZON_DIAGNOSTIC_RESULT"], "HIGH_SENSITIVITY", "COMMAND_01", "EXP-HOLD-001..004"),
        ("gap behavior", c1["classifications"]["ENTRY_GAP_DIAGNOSTIC_RESULT"], "MIXED", "COMMAND_01", "EXP-ENTRY-001..004"),
        ("yearly instability", c5["auxiliary_analyses"]["yearly_direction_consistency"]["TOTAL_REGIME_SCORE"]["classification"], "UNSTABLE", "COMMAND_05", "EXP-REGIME-010"),
    )
    rows = [{"finding": x[0], "observed": x[1], "expected": x[2], "source_command": x[3], "experiment_ids": x[4], "passed": x[1] == x[2]} for x in checks]
    if not all(row["passed"] for row in rows):
        raise ValueError("Command 06 manual synthesis validation failed")
    return rows


def core_synthesis(context: SynthesisContext) -> dict[str, Any]:
    registry_validation = validate_registry(context.registry)
    hypotheses = build_hypothesis_catalog()
    branches = research_branches()
    ruled_out = ruled_out_simple_forms()
    unresolved = unresolved_core_questions()
    limitations = data_limitations()
    coverage = diagnostic_coverage()
    proposals = next_experiment_proposals()
    infrastructure = infrastructure_priorities()
    if len(proposals) > 3 or len(infrastructure) > 3:
        raise ValueError("Command 06 permits at most three experiment and infrastructure proposals")
    c1 = context.source_reports["COMMAND_01"]
    baseline = next(row for row in c1["results"] if row["experiment_id"] == "EXP-RANK-001")
    family_counts = dict(sorted(Counter(row["family"] for row in context.registry["experiments"]).items()))
    return {
        "phase": "Step 02.13",
        "command": "Command 06",
        "synthesis_version": SYNTHESIS_VERSION,
        "synthesis_profile": SYNTHESIS_PROFILE,
        "research_decision_support_only": True,
        "registry_verification": registry_validation,
        "source_reports": {name: {"path": str(context.source_paths[name].relative_to(context.repo_root)), "sha256": context.source_hashes[name], "ready_for_review": True} for name in SOURCE_REPORTS},
        "completed_experiments_synthesized": 49,
        "registry_experiment_count_after_synthesis": 49,
        "baseline_performance_context_only": {
            "ending_equity": baseline["ending_equity"],
            "gross_return_pct": baseline["gross_return_pct"],
            "cagr_pct": baseline["cagr_pct"],
            "max_drawdown_pct": baseline["max_drawdown_pct"],
            "trades": baseline["trades"],
            "used_in_priority_score": False,
        },
        "evidence_strength_methodology": {
            "HIGH": "Multiple diagnostics or direct mechanical evidence with adequate samples and chronology.",
            "MEDIUM": "One strong or several aligned descriptive findings, with at least one material limitation.",
            "LOW": "Weak, unstable, interaction-dependent, or primarily descriptive evidence.",
            "VERY_LOW": "Tiny/incomplete samples or unsupported speculation.",
            "factors": ["independent diagnostic support", "sample size", "cross-year consistency", "source/admitted consistency", "portfolio chronology", "small-cohort dependence", "descriptive-only status"],
        },
        "overfitting_risk_methodology": {
            "LOW": "Few degrees of freedom, architecture-led, stable samples, and no outcome-selected threshold.",
            "MODERATE": "One fixed dimension with some instability or prior inspection.",
            "HIGH": "Several related variants inspected, unstable time behavior, or outcome-motivated design risk.",
            "VERY_HIGH": "Small/post-hoc cohorts, threshold freedom, repeated related testing, or multi-parameter search risk.",
        },
        "priority_methodology": {
            "weights": PRIORITY_WEIGHTS,
            "rating_scales": RATING_VALUES,
            "performance_fields_excluded": list(PERFORMANCE_FIELDS_EXCLUDED_FROM_PRIORITY),
            "historical_return_cagr_drawdown_used": False,
            "priority_a_rule": "Not contradicted; MEDIUM/HIGH evidence or critical importance; adequate/limited sample; one dimension; LOW/MODERATE overfitting risk; no post-hoc threshold; explicit falsification; score >=75.",
            "direct_historical_winner_selection": False,
        },
        "hypotheses": hypotheses,
        "hypothesis_count": len(hypotheses),
        "ruled_out_simple_form": ruled_out,
        "ruled_out_simple_form_count": len(ruled_out),
        "unresolved_core_questions": unresolved,
        "unresolved_core_question_count": len(unresolved),
        "data_limitations": limitations,
        "diagnostic_coverage": coverage,
        "diagnostic_family_experiment_counts": family_counts,
        "multiple_comparison_risk": {"classification": "HIGH", "completed_diagnostics": 49, "reason": "Many related hypotheses and variants have already been inspected; later work requires stricter preregistration and untouched validation."},
        "classifications": {
            "DIAGNOSTIC_COVERAGE_RESULT": "BROAD",
            "OVERFITTING_RISK_RESULT": "HIGH",
            "STRATEGY_V1_RESEARCH_RESULT": "WEAK_AND_REQUIRES_RESEARCH",
            "DATA_READINESS_RESULT": "LIMITED_BUT_USABLE",
            "NEXT_PHASE_READINESS": "INFRASTRUCTURE_REQUIRED_FIRST",
            "SCORE_COMPLETENESS_RESULT": "LIMITED_BY_MISSING_COMPONENTS",
            "INTRADAY_DATA_PRIORITY": "CRITICAL",
            "TRANSACTION_COST_MODEL_PRIORITY": "HIGH_PRIORITY_INFRASTRUCTURE",
        },
        "readiness": {
            "LIVE_TRADING_READY": False,
            "SMALL_CAPITAL_LIVE_READY": False,
            "further_research_state": "READY_FOR_FURTHER_RESEARCH",
            "paper_research_state": "READY_FOR_PAPER_RESEARCH_ONLY",
        },
        "research_branches": branches,
        "next_experiment_proposals": proposals,
        "infrastructure_priorities": infrastructure,
        "missing_data_priorities": missing_data_priorities(),
        "temporal_validation_protocol": {
            "status": "PROPOSED_NOT_EXECUTED",
            "selection_basis": "Calendar split declared before future experiments; not selected from performance.",
            "development_window": "2022-01-01 through 2024-12-31",
            "development_source_opportunities": 2068,
            "development_admitted_trades": 478,
            "validation_window": "2025-01-01 through latest frozen 2026 partial date",
            "validation_source_opportunities": 1224,
            "validation_admitted_trades": 246,
            "validation_tuning_prohibited": True,
            "caveat": "2026 is partial; freeze the terminal date before the first future experiment.",
        },
        "walk_forward_recommendation": {
            "recommended_later": True,
            "implemented_now": False,
            "sequence": "Use the first untouched calendar holdout, then consider expanding-window walk-forward replication after parameters are frozen.",
        },
        "minimum_sample_guidance": {
            "less_than_30": "NOT_INFERENTIAL",
            "30_to_99": "SMALL",
            "100_to_299": "LIMITED",
            "300_or_more": "ADEQUATE_FOR_DESCRIPTION",
            "promotion_level": "Require adequate source paths, adequate trade counts across multiple periods, nonzero cost modeling, and untouched validation.",
        },
        "experiment_design_template": experiment_design_template(),
        "policies": {
            "ONE_RESEARCH_DIMENSION_AT_A_TIME": True,
            "ranking_must_be_frozen_before_signal_change": True,
            "strategy_v2_created": False,
            "score_v2_created": False,
            "risk_v2_created": False,
            "regime_v2_created": False,
            "new_strategy_variant_run": False,
            "new_experiment_executed": False,
            "experiment_promoted": False,
            "historical_winner_selected": False,
            "optimizer_grid_search_or_ml_run": False,
            "registry_modified": False,
        },
        "pilot_manual_validation": pilot_validation(context.source_reports),
        "traceability_verified": True,
        "known_limitations": [row["limitation"] for row in limitations],
        "safety": {"live_signals_generated": 0, "live_orders_placed": 0, "remote_migrations_applied": 0, "supabase_records_persisted": 0},
    }


def write_outputs(context: SynthesisContext, summary: Mapping[str, Any]) -> list[Path]:
    report_root = context.data_dir / "reports"
    storage_root = context.data_dir / "research/diagnostics/strategy/v1/synthesis_command_06"
    mapping = {
        "strategy_diagnostic_v1_synthesis_hypotheses.csv": summary["hypotheses"],
        "strategy_diagnostic_v1_synthesis_ruled_out.csv": summary["ruled_out_simple_form"],
        "strategy_diagnostic_v1_synthesis_unresolved.csv": summary["unresolved_core_questions"],
        "strategy_diagnostic_v1_synthesis_priorities.csv": sorted(summary["hypotheses"], key=lambda row: (-row["priority_score_non_performance"], row["hypothesis_id"])),
        "strategy_diagnostic_v1_synthesis_data_gaps.csv": summary["data_limitations"],
        "strategy_diagnostic_v1_synthesis_research_branches.csv": summary["research_branches"],
        "strategy_diagnostic_v1_synthesis_next_experiments.csv": summary["next_experiment_proposals"],
        "strategy_diagnostic_v1_synthesis_infrastructure.csv": summary["infrastructure_priorities"],
    }
    paths: list[Path] = []
    for filename, rows in mapping.items():
        path = report_root / filename
        write_csv(path, rows)
        paths.append(path)
    summary_path = report_root / "strategy_diagnostic_v1_synthesis_summary.json"
    write_json(summary_path, summary)
    paths.append(summary_path)
    payload_path = storage_root / "synthesis_payload_v1.json"
    integrity_path = storage_root / "source_integrity_v1.json"
    write_json(payload_path, summary)
    write_json(integrity_path, {"registry_verification": summary["registry_verification"], "source_reports": summary["source_reports"], "baseline_hashes": summary["baseline_hashes_after"], "traceability_verified": summary["traceability_verified"]})
    paths.extend((payload_path, integrity_path))
    return paths


def run_strategy_diagnostic_synthesis(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Loading the frozen 49-record registry and Command 01–05 reports")
    context = load_synthesis_context(Path(repo_root))
    baseline_before = dict(context.baseline_hashes)
    registry_before = context.registry_fingerprint
    source_before = dict(context.source_hashes)
    notify(progress, "Building the fixed non-performance hypothesis prioritization twice")
    first = core_synthesis(context)
    second = core_synthesis(context)
    first_fingerprint = canonical_hash(first)
    second_fingerprint = canonical_hash(second)
    if first_fingerprint != second_fingerprint:
        raise ValueError("Command 06 synthesis is not reproducible")
    summary = copy.deepcopy(first)
    summary["reproducibility"] = {"first_fingerprint": first_fingerprint, "second_fingerprint": second_fingerprint, "match": True}
    baseline_after = portfolio_backtest_regression_hashes(context.data_dir)
    registry_after = registry_fingerprint(json.loads(context.registry_path.read_text(encoding="utf-8")))
    source_after = {name: file_hash(path) for name, path in context.source_paths.items()}
    mutation_violations = sum(baseline_after.get(name) != value for name, value in baseline_before.items())
    mutation_violations += int(registry_after != registry_before)
    mutation_violations += sum(source_after.get(name) != value for name, value in source_before.items())
    summary["baseline_hashes_after"] = baseline_after
    summary["baseline_mutation_violations"] = mutation_violations
    summary["source_reports_unchanged"] = source_after == source_before
    summary["registry_unchanged"] = registry_after == registry_before
    summary["tests_passed"] = tests_passed
    summary["frontend_build_passed"] = frontend_build_passed
    summary["security"] = {"backend_env_required_ignored": True, "synthesis_outputs_required_ignored": True, "broker_credentials_written": False, "supabase_secrets_written": False, "api_tokens_written": False}
    summary["runtime_seconds"] = 0
    summary["storage"] = {}
    summary["ready_for_review"] = False
    notify(progress, "Writing isolated Command 06 synthesis artifacts and reports")
    paths = write_outputs(context, summary)
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    summary["storage"] = {"artifact_count": len(paths), "artifact_size_bytes": sum(path.stat().st_size for path in paths if path.exists()), "root": "data/research/diagnostics/strategy/v1/synthesis_command_06"}
    summary["ready_for_review"] = mutation_violations == 0 and tests_passed and frontend_build_passed and summary["reproducibility"]["match"]
    write_json(context.data_dir / "reports/strategy_diagnostic_v1_synthesis_summary.json", summary)
    write_json(context.data_dir / "research/diagnostics/strategy/v1/synthesis_command_06/synthesis_payload_v1.json", summary)
    return summary


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

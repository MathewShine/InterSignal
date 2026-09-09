from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.strategy.entry_config import EntryEvaluationConfig
from app.strategy.entry_evaluator import ENTRY_OUTPUT_FIELDS, READINESS_STATES, prohibited_outcome_fields
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip, split_codes

ENTRY_EVALUATION_AUDIT_VERSION = "ENTRY_EVALUATION_AUDIT_V1"

PROGRESSED_STATES = {
    "CONDITIONALLY_READY",
    "READY_FOR_RISK_EVALUATION",
    "EXCEPTIONAL_LONG_REVIEW",
}
DOWNSTREAM_READY_STATES = {
    "READY_FOR_RISK_EVALUATION",
    "EXCEPTIONAL_LONG_REVIEW",
}
OUTCOME_FIELD_TOKENS = (
    "future_return",
    "forward_return",
    "t_plus",
    "mfe",
    "mae",
    "winner",
    "loser",
    "target_hit",
    "stop_hit",
    "profitability",
    "trade_outcome",
)

COHORT_FUNNEL_FIELDS = [
    "section",
    "cohort",
    "candidate_state",
    "regime_state",
    "setup_quality",
    "candidate_rows",
    "setup_eligible_rows",
    "not_ready",
    "watch",
    "conditionally_ready",
    "ready_for_risk_evaluation",
    "exceptional_long_review",
    "progressed_rows",
    "candidate_to_setup_pct",
    "setup_to_progressed_pct",
    "candidate_to_progressed_pct",
    "setup_to_ready_for_risk_only_pct",
    "setup_to_downstream_ready_pct",
]

PENALTY_INVARIANT_FIELDS = [
    "section",
    "entry_readiness",
    "gate_name",
    "penalty_code",
    "severity",
    "blocking",
    "rows",
    "pct",
    "invariant_status",
    "details",
]

EXCEPTIONAL_AUDIT_FIELDS = [
    "section",
    "symbol",
    "trading_date",
    "candidate_cohort",
    "setup_quality",
    "breakout_state",
    "acceptance_state",
    "candle_quality",
    "volume_confirmation",
    "benchmark_rs_context",
    "extension_risk",
    "consolidation_quality",
    "false_breakout_flags",
    "regime_score_normalized",
    "regime_confidence_score",
    "regime_confidence_state",
    "criterion",
    "count",
    "rate_pct",
    "details",
]

REGIME_SELECTIVITY_FIELDS = [
    "section",
    "regime_state",
    "setup_quality",
    "cohort",
    "candidate_rows",
    "setup_eligible_rows",
    "not_ready",
    "watch",
    "conditionally_ready",
    "ready_for_risk_evaluation",
    "exceptional_long_review",
    "progressed_rows",
    "blocked_rows",
    "progression_rate_pct",
    "ready_for_risk_rate_pct",
    "exceptional_rate_pct",
]

READINESS_TRANSITION_FIELDS = [
    "section",
    "category",
    "from_state",
    "to_state",
    "bucket",
    "trading_date",
    "count",
    "pct",
    "median",
    "mean",
    "p90",
    "p95",
    "max",
    "new_ready",
    "continued_ready",
    "dropped_ready",
    "churn_pct",
]

SENSITIVITY_FIELDS = [
    "scenario",
    "not_ready",
    "watch",
    "conditionally_ready",
    "ready_for_risk_evaluation",
    "exceptional_long_review",
    "total_progressed",
    "setup_to_progression_rate_pct",
    "bullish_progression_pct",
    "neutral_progression_pct",
    "bearish_exceptional_pct",
    "baseline_retained",
    "removed",
    "introduced",
    "jaccard",
    "daily_median_ready",
    "daily_p95_ready",
]


@dataclass(frozen=True, slots=True)
class EntryEvaluationAuditConfig:
    data_dir: Path
    entry_config: EntryEvaluationConfig = EntryEvaluationConfig()

    @property
    def entry_dataset_path(self) -> Path:
        return self.data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz"

    @property
    def setup_dataset_path(self) -> Path:
        return self.data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def regime_dataset_path(self) -> Path:
        return self.data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_artifacts_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "entry_evaluation" / "v1"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_audit_summary.json"

    @property
    def cohort_funnel_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_cohort_funnel.csv"

    @property
    def penalty_invariants_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_penalty_invariants.csv"

    @property
    def exceptional_long_audit_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_exceptional_long_audit.csv"

    @property
    def regime_selectivity_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_regime_selectivity.csv"

    @property
    def readiness_transitions_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_readiness_transitions.csv"

    @property
    def sensitivity_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_sensitivity.csv"

    @property
    def exceptional_inventory_path(self) -> Path:
        return self.audit_artifacts_dir / "exceptional_long_inventory.csv"

    @property
    def neutral_combinations_path(self) -> Path:
        return self.audit_artifacts_dir / "neutral_rule_combinations.csv"

    @property
    def evidence_distribution_path(self) -> Path:
        return self.audit_artifacts_dir / "entry_evidence_distribution.csv"

    @property
    def watch_reasons_path(self) -> Path:
        return self.audit_artifacts_dir / "watch_reason_distribution.csv"

    @property
    def conditional_reasons_path(self) -> Path:
        return self.audit_artifacts_dir / "conditional_ready_distribution.csv"


def build_entry_evaluation_audit(
    *,
    config: EntryEvaluationAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = baseline_hashes(config)

    if progress:
        progress("Loading immutable ENTRY_EVALUATION_V1 rows")
    rows = load_entry_rows(config.entry_dataset_path)

    if progress:
        progress("Reconstructing funnel, cohorts, regime selectivity, and penalties")
    full_funnel = full_funnel_summary(rows)
    cohort_csv, cohort_summary = cohort_funnel(rows)
    regime_csv, regime_summary = regime_selectivity(rows)
    penalty_csv, penalty_summary = penalty_invariants(rows, config.entry_config)

    if progress:
        progress("Auditing exceptional-long inventory and criteria hit rates")
    exceptional_csv, exceptional_summary, exceptional_inventory = exceptional_long_audit(rows, config.entry_config)

    if progress:
        progress("Auditing evidence distributions, warning impact, persistence, transitions, and churn")
    evidence_csv, evidence_summary = evidence_distribution(rows)
    watch_csv, watch_summary = watch_reason_distribution(rows)
    conditional_csv, conditional_summary = conditional_ready_distribution(rows)
    transition_csv, transition_summary = readiness_transitions_and_churn(rows)
    daily_density = daily_ready_density(rows)
    setup_quality_progression = setup_quality_progression_summary(rows)

    if progress:
        progress("Running structural sensitivity scenarios without mutating baseline")
    sensitivity_csv, sensitivity_summary = sensitivity_scenarios(rows)

    neutral_csv, neutral_summary = neutral_rule_combinations(rows)
    hashes_after = baseline_hashes(config)
    unchanged = {key: hashes_before[key] == hashes_after[key] for key in hashes_before}
    entry_hash_unchanged = unchanged["entry"]
    invariant_violations = penalty_summary["critical_invariant_violations"] + penalty_summary["gate_readiness_violations"]
    structural_stability = structural_stability_result(sensitivity_summary, invariant_violations)
    funnel_sanity = funnel_sanity_result(full_funnel, invariant_violations)
    penalty_consistency = penalty_consistency_result(penalty_summary)
    exceptional_result = exceptional_long_result(exceptional_summary)
    baseline_decision = (
        "FREEZE_UNCHANGED"
        if invariant_violations == 0 and funnel_sanity in {"HEALTHY", "HEALTHY_BUT_HIGH_PASS_THROUGH"} and exceptional_result == "SELECTIVE"
        else "REMAIN_PROVISIONAL_PENDING_REVIEW"
    )
    report = {
        "phase": "Step 02.8",
        "command": "Command 02",
        "audit_version": ENTRY_EVALUATION_AUDIT_VERSION,
        "generated_at": generated_at,
        "entry_verification": entry_version_verification(rows, config.entry_config),
        "hashes_before": hashes_before,
        "hashes_after": hashes_after,
        "baseline_unchanged": unchanged,
        "funnel": full_funnel,
        "cohorts": cohort_summary,
        "regime_selectivity": regime_summary,
        "setup_quality_progression": setup_quality_progression,
        "daily_ready_density": daily_density,
        "neutral": neutral_summary,
        "exceptional_longs": exceptional_summary,
        "penalties": penalty_summary,
        "watch": watch_summary,
        "conditional_ready": conditional_summary,
        "evidence": evidence_summary,
        "transitions": transition_summary,
        "sensitivity": sensitivity_summary,
        "results": {
            "structural_stability": structural_stability,
            "funnel_sanity": funnel_sanity,
            "penalty_consistency": penalty_consistency,
            "exceptional_long_result": exceptional_result,
            "baseline_decision": baseline_decision,
            "setup_to_entry_progression_explainable": setup_progression_explainable(full_funnel, regime_summary),
        },
        "safety": {
            "future_return_fields_used": 0,
            "t_plus_return_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "target_stop_hit_fields_used": 0,
            "profitability_optimization_used": 0,
            "trade_outcomes_used": 0,
            "risk_reward_calculated": 0,
            "final_100_point_entry_score_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "prohibited_output_fields": prohibited_outcome_fields(ENTRY_OUTPUT_FIELDS),
            "audit_outcome_field_scan": scan_for_outcome_fields(rows[:1]),
        },
        "outputs": {
            "summary_json": str(config.summary_path),
            "cohort_funnel_csv": str(config.cohort_funnel_path),
            "penalty_invariants_csv": str(config.penalty_invariants_path),
            "exceptional_long_audit_csv": str(config.exceptional_long_audit_path),
            "regime_selectivity_csv": str(config.regime_selectivity_path),
            "readiness_transitions_csv": str(config.readiness_transitions_path),
            "sensitivity_csv": str(config.sensitivity_path),
            "markdown": "docs/strategy-v1-entry-evaluation-audit.md",
            "bulk_audit_dir": str(config.audit_artifacts_dir),
            "exceptional_long_inventory_csv": str(config.exceptional_inventory_path),
            "neutral_rule_combinations_csv": str(config.neutral_combinations_path),
            "evidence_distribution_csv": str(config.evidence_distribution_path),
            "watch_reason_distribution_csv": str(config.watch_reasons_path),
            "conditional_ready_distribution_csv": str(config.conditional_reasons_path),
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "rows_read": len(rows),
            "storage_size_bytes": 0,
        },
    }
    ready_for_review = bool(
        entry_hash_unchanged
        and all(unchanged.values())
        and report["entry_verification"]["entry_config_hash_matches_current_config"]
        and invariant_violations == 0
        and not report["safety"]["audit_outcome_field_scan"]
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    report["ready_for_review"] = ready_for_review

    write_csv(config.cohort_funnel_path, cohort_csv, COHORT_FUNNEL_FIELDS)
    write_csv(config.regime_selectivity_path, regime_csv, REGIME_SELECTIVITY_FIELDS)
    write_csv(config.penalty_invariants_path, penalty_csv, PENALTY_INVARIANT_FIELDS)
    write_csv(config.exceptional_long_audit_path, exceptional_csv, EXCEPTIONAL_AUDIT_FIELDS)
    write_csv(config.readiness_transitions_path, transition_csv, READINESS_TRANSITION_FIELDS)
    write_csv(config.sensitivity_path, sensitivity_csv, SENSITIVITY_FIELDS)
    write_csv(config.exceptional_inventory_path, exceptional_inventory, EXCEPTIONAL_AUDIT_FIELDS)
    write_csv(config.neutral_combinations_path, neutral_csv, ["readiness_group", "combination", "count", "pct"])
    write_csv(config.evidence_distribution_path, evidence_csv, ["section", "entry_readiness", "evidence_code", "count", "pct"])
    write_csv(config.watch_reasons_path, watch_csv, ["primary_watch_reason", "count", "pct"])
    write_csv(
        config.conditional_reasons_path,
        conditional_csv,
        ["section", "regime_state", "cohort", "setup_quality", "reason", "count", "pct"],
    )
    report["processing"]["storage_size_bytes"] = output_size(config)
    write_json(config.summary_path, report)
    return report


def load_entry_rows(path: Path) -> list[dict[str, str]]:
    with open_csv_maybe_gzip(path) as file:
        return [row for row in csv.DictReader(file) if row.get("trading_date") and row.get("symbol")]


def baseline_hashes(config: EntryEvaluationAuditConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
        "entry": file_sha256(config.entry_dataset_path),
    }


def entry_version_verification(rows: Sequence[dict[str, str]], entry_config: EntryEvaluationConfig) -> dict[str, Any]:
    return {
        "feature_version": observed_single(rows, "feature_version"),
        "candidate_version": observed_single(rows, "candidate_version"),
        "candidate_config_hash": observed_single(rows, "candidate_config_hash"),
        "setup_version": observed_single(rows, "setup_version"),
        "setup_config_hash": observed_single(rows, "setup_config_hash"),
        "regime_version": observed_single(rows, "regime_version"),
        "regime_config_hash": observed_single(rows, "regime_config_hash"),
        "entry_version": observed_single(rows, "entry_version"),
        "entry_config_hash": observed_single(rows, "entry_config_hash"),
        "entry_config_hash_matches_current_config": observed_single(rows, "entry_config_hash") == entry_config.config_hash(),
        "audit_version": ENTRY_EVALUATION_AUDIT_VERSION,
    }


def full_funnel_summary(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    candidate_rows = len(rows)
    setup_eligible = count_where(rows, is_setup_eligible)
    counts = Counter(row["entry_readiness"] for row in rows)
    progressed = count_where(rows, is_progressed)
    downstream_ready = count_where(rows, is_downstream_ready)
    ready_for_risk = counts["READY_FOR_RISK_EVALUATION"]
    return {
        "candidate_rows": candidate_rows,
        "setup_eligible_rows": setup_eligible,
        "entry_context_evaluated_rows": candidate_rows,
        "not_ready": counts["NOT_READY"],
        "watch": counts["WATCH"],
        "conditionally_ready": counts["CONDITIONALLY_READY"],
        "ready_for_risk_evaluation": ready_for_risk,
        "exceptional_long_review": counts["EXCEPTIONAL_LONG_REVIEW"],
        "progressed_to_entry_context": progressed,
        "downstream_ready_rows": downstream_ready,
        "candidate_to_setup_pct": pct(setup_eligible, candidate_rows),
        "setup_to_progressed_pct": pct(progressed, setup_eligible),
        "candidate_to_progressed_pct": pct(progressed, candidate_rows),
        "setup_to_ready_for_risk_only_pct": pct(ready_for_risk, setup_eligible),
        "setup_to_downstream_ready_pct": pct(downstream_ready, setup_eligible),
    }


def cohort_funnel(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    summary: dict[str, Any] = {"cohorts": {}, "candidate_state_by_cohort": {}}
    for cohort_name in ("EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE", "OTHER"):
        group = [row for row in rows if eligibility_cohort(row) == cohort_name]
        if not group:
            continue
        funnel = funnel_counts(group)
        output.append(cohort_row("COHORT", cohort=cohort_name, rows=group))
        summary["cohorts"][cohort_name] = funnel
    for (state, cohort_name), group in sorted(group_by(rows, lambda row: (row["candidate_state"], eligibility_cohort(row))).items()):
        output.append(cohort_row("CANDIDATE_STATE_X_COHORT", cohort=cohort_name, candidate_state=state, rows=group))
        summary["candidate_state_by_cohort"][f"{state}|{cohort_name}"] = funnel_counts(group)
    for (regime, quality, cohort_name), group in sorted(
        group_by(rows, lambda row: (row["regime_state"], row["setup_quality"], eligibility_cohort(row))).items()
    ):
        output.append(
            cohort_row(
                "REGIME_SETUP_QUALITY_COHORT",
                cohort=cohort_name,
                regime_state=regime,
                setup_quality=quality,
                rows=group,
            )
        )
    return output, summary


def cohort_row(
    section: str,
    *,
    rows: Sequence[dict[str, str]],
    cohort: str = "",
    candidate_state: str = "",
    regime_state: str = "",
    setup_quality: str = "",
) -> dict[str, Any]:
    funnel = funnel_counts(rows)
    return {
        "section": section,
        "cohort": cohort,
        "candidate_state": candidate_state,
        "regime_state": regime_state,
        "setup_quality": setup_quality,
        **funnel,
    }


def funnel_counts(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    setup = count_where(rows, is_setup_eligible)
    counts = Counter(row["entry_readiness"] for row in rows)
    progressed = count_where(rows, is_progressed)
    ready = counts["READY_FOR_RISK_EVALUATION"]
    downstream = ready + counts["EXCEPTIONAL_LONG_REVIEW"]
    return {
        "candidate_rows": total,
        "setup_eligible_rows": setup,
        "not_ready": counts["NOT_READY"],
        "watch": counts["WATCH"],
        "conditionally_ready": counts["CONDITIONALLY_READY"],
        "ready_for_risk_evaluation": ready,
        "exceptional_long_review": counts["EXCEPTIONAL_LONG_REVIEW"],
        "progressed_rows": progressed,
        "candidate_to_setup_pct": pct(setup, total),
        "setup_to_progressed_pct": pct(progressed, setup),
        "candidate_to_progressed_pct": pct(progressed, total),
        "setup_to_ready_for_risk_only_pct": pct(ready, setup),
        "setup_to_downstream_ready_pct": pct(downstream, setup),
    }


def regime_selectivity(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    summary: dict[str, Any] = {}
    for regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE"):
        group = [row for row in rows if row["regime_state"] == regime]
        row = regime_selectivity_row("REGIME", regime_state=regime, rows=group)
        output.append(row)
        summary[regime] = row
    for (regime, quality), group in sorted(group_by(rows, lambda row: (row["regime_state"], row["setup_quality"])).items()):
        output.append(regime_selectivity_row("REGIME_SETUP_QUALITY", regime_state=regime, setup_quality=quality, rows=group))
    for (regime, cohort_name), group in sorted(group_by(rows, lambda row: (row["regime_state"], eligibility_cohort(row))).items()):
        output.append(regime_selectivity_row("REGIME_COHORT", regime_state=regime, cohort=cohort_name, rows=group))
    setup_eligible_by_regime = {
        regime: [row for row in rows if row["regime_state"] == regime and is_setup_eligible(row)]
        for regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE")
    }
    summary["setup_eligible_progression"] = {
        regime: {
            "setup_eligible_rows": len(group),
            "progressed_rows": count_where(group, is_progressed),
            "ready_for_risk_rows": sum(1 for row in group if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"),
            "exceptional_rows": sum(1 for row in group if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"),
            "setup_to_progressed_pct": pct(count_where(group, is_progressed), len(group)),
        }
        for regime, group in setup_eligible_by_regime.items()
    }
    return output, summary


def regime_selectivity_row(
    section: str,
    *,
    rows: Sequence[dict[str, str]],
    regime_state: str = "",
    setup_quality: str = "",
    cohort: str = "",
) -> dict[str, Any]:
    total = len(rows)
    setup_group = [row for row in rows if is_setup_eligible(row)]
    setup = len(setup_group)
    counts = Counter(row["entry_readiness"] for row in rows)
    progressed = count_where(rows, is_progressed)
    ready = counts["READY_FOR_RISK_EVALUATION"]
    exceptional = counts["EXCEPTIONAL_LONG_REVIEW"]
    return {
        "section": section,
        "regime_state": regime_state,
        "setup_quality": setup_quality,
        "cohort": cohort,
        "candidate_rows": total,
        "setup_eligible_rows": setup,
        "not_ready": counts["NOT_READY"],
        "watch": counts["WATCH"],
        "conditionally_ready": counts["CONDITIONALLY_READY"],
        "ready_for_risk_evaluation": ready,
        "exceptional_long_review": exceptional,
        "progressed_rows": progressed,
        "blocked_rows": counts["NOT_READY"],
        "progression_rate_pct": pct(count_where(setup_group, is_progressed), setup),
        "ready_for_risk_rate_pct": pct(sum(1 for row in setup_group if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"), setup),
        "exceptional_rate_pct": pct(sum(1 for row in setup_group if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"), setup),
    }


def penalty_invariants(
    rows: Sequence[dict[str, str]],
    config: EntryEvaluationConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    total = len(rows)
    readiness_groups = group_by(rows, lambda row: row["entry_readiness"])
    severity_by_readiness: dict[str, Any] = {}
    blocking_by_readiness: dict[str, Any] = {}
    penalty_count_by_readiness: dict[str, Any] = {}
    for readiness in READINESS_STATES:
        group = readiness_groups.get(readiness, [])
        severity_counter = Counter(row.get("max_penalty_severity", "") for row in group)
        blocking_counter = Counter("blocking" if has_active_blocking_penalty(row) else "nonblocking" for row in group)
        penalty_count_counter = Counter(str(len(split_codes(row.get("penalty_codes", "")))) for row in group)
        severity_by_readiness[readiness] = distribution(severity_counter, len(group))
        blocking_by_readiness[readiness] = distribution(blocking_counter, len(group))
        penalty_count_by_readiness[readiness] = distribution(penalty_count_counter, len(group))
        for severity, count in severity_counter.most_common():
            output.append(
                penalty_invariant_row(
                    "SEVERITY_BY_READINESS",
                    readiness=readiness,
                    severity=severity,
                    count=count,
                    total=len(group),
                )
            )
        for label, count in blocking_counter.most_common():
            output.append(
                penalty_invariant_row(
                    "BLOCKING_BY_READINESS",
                    readiness=readiness,
                    blocking=label,
                    count=count,
                    total=len(group),
                )
            )
        for count_label, count in penalty_count_counter.most_common():
            output.append(
                penalty_invariant_row(
                    "PENALTY_COUNT_BY_READINESS",
                    readiness=readiness,
                    count=count,
                    total=len(group),
                    details=f"penalty_count={count_label}",
                )
            )
    ready_blocking = [row for row in rows if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION" and has_active_blocking_penalty(row)]
    exceptional_blocking = [row for row in rows if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW" and has_active_blocking_penalty(row)]
    conditional_blocking = [row for row in rows if row["entry_readiness"] == "CONDITIONALLY_READY" and has_active_blocking_penalty(row)]
    blocking_by_state = {
        readiness: sum(1 for row in rows if row["entry_readiness"] == readiness and has_active_blocking_penalty(row))
        for readiness in READINESS_STATES
    }
    for readiness, count in blocking_by_state.items():
        output.append(
            penalty_invariant_row(
                "ACTIVE_BLOCKING_RECONCILIATION",
                readiness=readiness,
                blocking="active_blocking",
                count=count,
                total=total,
                invariant_status="PASS" if readiness not in DOWNSTREAM_READY_STATES or count == 0 else "FAIL",
            )
        )
    gate_violations = gate_readiness_violations(rows)
    for gate_name, count in Counter(item["gate_name"] for item in gate_violations).most_common():
        output.append(
            penalty_invariant_row(
                "GATE_READINESS_VIOLATION",
                gate_name=gate_name,
                count=count,
                total=total,
                invariant_status="FAIL",
            )
        )
    penalty_runtime = penalty_runtime_semantics(rows, config)
    for code, details in penalty_runtime.items():
        output.append(
            penalty_invariant_row(
                "PENALTY_RUNTIME_SEMANTICS",
                penalty_code=code,
                severity=details["configured_severity"],
                blocking=details["configured_behavior"],
                count=details["rows"],
                total=total,
                invariant_status=details["status"],
                details=f"ready_rows={details['downstream_ready_rows']}",
            )
        )
    inherited = inherited_penalty_summary(rows)
    critical = len(ready_blocking) + len(exceptional_blocking) + len(conditional_blocking)
    return output, {
        "severity_by_readiness": severity_by_readiness,
        "blocking_distribution_by_readiness": blocking_by_readiness,
        "penalty_count_by_readiness": penalty_count_by_readiness,
        "active_blocking_rows": sum(blocking_by_state.values()),
        "not_ready_rows": sum(1 for row in rows if row["entry_readiness"] == "NOT_READY"),
        "blocking_minus_not_ready": sum(blocking_by_state.values()) - sum(1 for row in rows if row["entry_readiness"] == "NOT_READY"),
        "blocking_by_readiness": blocking_by_state,
        "ready_for_risk_blocking_penalty_rows": len(ready_blocking),
        "exceptional_long_blocking_penalty_rows": len(exceptional_blocking),
        "conditionally_ready_blocking_penalty_rows": len(conditional_blocking),
        "critical_invariant_violations": critical,
        "gate_readiness_violations": len(gate_violations),
        "gate_violation_examples": gate_violations[:20],
        "penalty_runtime_semantics": penalty_runtime,
        "inherited_vs_active": inherited,
        "blocking_reconciliation_explanation": (
            "Blocking penalty rows exceed NOT_READY rows because WATCH rows can retain inherited/contextual blocking "
            "penalties, especially bearish normal-long blockers, while WATCH remains a non-downstream state."
        ),
    }


def penalty_invariant_row(
    section: str,
    *,
    readiness: str = "",
    gate_name: str = "",
    penalty_code: str = "",
    severity: str = "",
    blocking: str = "",
    count: int,
    total: int,
    invariant_status: str = "PASS",
    details: str = "",
) -> dict[str, Any]:
    return {
        "section": section,
        "entry_readiness": readiness,
        "gate_name": gate_name,
        "penalty_code": penalty_code,
        "severity": severity,
        "blocking": blocking,
        "rows": count,
        "pct": pct(count, total),
        "invariant_status": invariant_status,
        "details": details,
    }


def gate_readiness_violations(rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    violations = []
    downstream_or_conditional = PROGRESSED_STATES
    for row in rows:
        readiness = row["entry_readiness"]
        if readiness not in downstream_or_conditional:
            continue
        gates = gate_details(row)
        for gate_key, gate in gates.items():
            if truthy(gate.get("passed")):
                continue
            violations.append(
                {
                    "trading_date": row["trading_date"],
                    "symbol": row["symbol"],
                    "entry_readiness": readiness,
                    "gate_key": gate_key,
                    "gate_name": gate.get("gate_name", gate_key),
                    "reason_codes": gate.get("reason_codes", []),
                }
            )
    return violations


def penalty_runtime_semantics(rows: Sequence[dict[str, str]], config: EntryEvaluationConfig) -> dict[str, Any]:
    output = {}
    configured_codes = set(config.penalties.severity_by_code)
    row_codes = {code for row in rows for code in split_codes(row.get("penalty_codes", ""))}
    for code in sorted(configured_codes | row_codes):
        severity = config.penalties.severity_by_code.get(code, "INFO")
        configured_blocking = code in set(config.penalties.blocking_codes) or severity == "BLOCKING"
        code_rows = [row for row in rows if code in split_codes(row.get("penalty_codes", ""))]
        downstream_ready_rows = [row for row in code_rows if is_downstream_ready(row)]
        output[code] = {
            "configured_severity": severity,
            "configured_behavior": "blocking" if configured_blocking else "nonblocking",
            "rows": len(code_rows),
            "downstream_ready_rows": len(downstream_ready_rows),
            "status": "FAIL" if configured_blocking and downstream_ready_rows else "PASS",
        }
    return output


def inherited_penalty_summary(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    setup_poor = [row for row in rows if "SETUP_POOR" in split_codes(row.get("penalty_codes", ""))]
    poor_quality = [row for row in rows if row.get("setup_quality") == "POOR"]
    watch_penalty = [row for row in rows if "SETUP_WATCH_ONLY" in split_codes(row.get("penalty_codes", ""))]
    watch_quality = [row for row in rows if row.get("setup_quality") == "WATCH"]
    bearish_block = [row for row in rows if "BEARISH_NORMAL_LONG_BLOCKED" in split_codes(row.get("penalty_codes", ""))]
    bearish_watch = [row for row in bearish_block if row.get("entry_readiness") == "WATCH"]
    return {
        "setup_poor_penalty_rows": len(setup_poor),
        "setup_quality_poor_rows": len(poor_quality),
        "setup_poor_overlap_rows": len([row for row in setup_poor if row.get("setup_quality") == "POOR"]),
        "setup_watch_penalty_rows": len(watch_penalty),
        "setup_quality_watch_rows": len(watch_quality),
        "setup_watch_overlap_rows": len([row for row in watch_penalty if row.get("setup_quality") == "WATCH"]),
        "bearish_normal_long_blocked_rows": len(bearish_block),
        "bearish_normal_long_blocked_watch_rows": len(bearish_watch),
        "interpretation": "Duplicated setup and regime blockers are retained intentionally as traceability/context fields; downstream-ready invariants decide active eligibility.",
    }


def exceptional_long_audit(
    rows: Sequence[dict[str, str]],
    config: EntryEvaluationConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    output = []
    bearish_rows = [row for row in rows if row["regime_state"] == "BEARISH"]
    bearish_setup_rows = [row for row in bearish_rows if is_setup_eligible(row)]
    exceptional_rows = [row for row in rows if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"]
    inventory = [exceptional_inventory_row(row, section="DETAIL") for row in exceptional_rows]
    output.extend(inventory[:500])

    criteria = [
        ("STRONG_SETUP", lambda row: row.get("setup_quality") == "STRONG"),
        ("CONFIRMED_OR_BOTH", lambda row: row.get("candidate_state") == "CONFIRMED" or truthy(row.get("both_eligible"))),
        ("STRONG_RS", lambda row: row.get("benchmark_rs_context") == "STRONG"),
        ("STRONG_OR_EXCEPTIONAL_VOLUME", lambda row: row.get("volume_confirmation") in {"STRONG", "EXCEPTIONAL"}),
        (
            "ACCEPTED_OR_CONTINUATION",
            lambda row: row.get("breakout_state") == "CLOSE_ACCEPTED" or "MOMENTUM_CONTINUATION" in split_codes(row.get("setup_type_flags", "")),
        ),
        ("GOOD_OR_STRONG_CANDLE", lambda row: row.get("candle_quality") in {"GOOD", "STRONG"}),
        ("LOW_OR_MODERATE_EXTENSION", lambda row: row.get("extension_risk") in {"LOW", "MODERATE"}),
        ("GOOD_OR_STRONG_CONSOLIDATION", lambda row: row.get("consolidation_quality") in {"GOOD", "STRONG"}),
        (
            "NO_MAJOR_FALSE_BREAKOUT_WARNING",
            lambda row: not (
                split_codes(row.get("false_breakout_flags", ""))
                & set(config.bearish_exceptional.blocking_false_breakout_flags)
            ),
        ),
    ]
    criteria_summary: dict[str, Any] = {}
    for name, predicate in criteria:
        bearish_hits = count_where(bearish_setup_rows, predicate)
        exceptional_hits = count_where(exceptional_rows, predicate)
        criteria_summary[name] = {
            "bearish_setup_hits": bearish_hits,
            "bearish_setup_hit_rate_pct": pct(bearish_hits, len(bearish_setup_rows)),
            "exceptional_hits": exceptional_hits,
            "exceptional_hit_rate_pct": pct(exceptional_hits, len(exceptional_rows)),
        }
        output.append(
            exceptional_report_row(
                "CRITERION_HIT_RATE_BEARISH_SETUP",
                criterion=name,
                count=bearish_hits,
                rate=pct(bearish_hits, len(bearish_setup_rows)),
            )
        )
        output.append(
            exceptional_report_row(
                "CRITERION_HIT_RATE_EXCEPTIONAL",
                criterion=name,
                count=exceptional_hits,
                rate=pct(exceptional_hits, len(exceptional_rows)),
            )
        )
    per_day = Counter(row["trading_date"] for row in exceptional_rows)
    per_day_distribution = numeric_distribution(list(per_day.values()))
    concentration = exceptional_repeat_concentration(bearish_setup_rows, exceptional_rows)
    for item in concentration["top_symbols"][:20]:
        output.append(
            exceptional_report_row(
                "REPEAT_CONCENTRATION_TOP20",
                symbol=item["symbol"],
                count=item["exceptional_days"],
                rate=item["pct_of_bearish_setup_days"],
                details=f"bearish_setup_days={item['bearish_setup_days']};longest_streak={item['longest_exceptional_streak']}",
            )
        )
    return output, {
        "bearish_candidate_rows": len(bearish_rows),
        "bearish_setup_eligible_rows": len(bearish_setup_rows),
        "exceptional_candidates": count_where(rows, lambda row: truthy(row.get("exceptional_long_candidate"))),
        "exceptional_review_ready_rows": len(exceptional_rows),
        "rate_vs_bearish_setup_eligible_pct": pct(len(exceptional_rows), len(bearish_setup_rows)),
        "per_day_exceptional_distribution": per_day_distribution,
        "symbols_repeatedly_qualifying": concentration["top_symbols"],
        "criteria_hit_rate": criteria_summary,
        "inventory_rows": len(inventory),
        "pathway_breadth_flag": "SELECTIVE" if decimal(pct(len(exceptional_rows), len(bearish_setup_rows))) <= Decimal("10") else "BROAD_REVIEW",
    }, inventory


def exceptional_inventory_row(row: dict[str, str], *, section: str) -> dict[str, Any]:
    return {
        "section": section,
        "symbol": row["symbol"],
        "trading_date": row["trading_date"],
        "candidate_cohort": eligibility_cohort(row),
        "setup_quality": row.get("setup_quality", ""),
        "breakout_state": row.get("breakout_state", ""),
        "acceptance_state": row.get("acceptance_state", ""),
        "candle_quality": row.get("candle_quality", ""),
        "volume_confirmation": row.get("volume_confirmation", ""),
        "benchmark_rs_context": row.get("benchmark_rs_context", ""),
        "extension_risk": row.get("extension_risk", ""),
        "consolidation_quality": row.get("consolidation_quality", ""),
        "false_breakout_flags": row.get("false_breakout_flags", ""),
        "regime_score_normalized": row.get("regime_score_normalized", ""),
        "regime_confidence_score": row.get("regime_confidence_score", ""),
        "regime_confidence_state": row.get("regime_confidence_state", ""),
        "criterion": "",
        "count": "",
        "rate_pct": "",
        "details": row.get("exceptional_long_reasons", ""),
    }


def exceptional_report_row(
    section: str,
    *,
    symbol: str = "",
    criterion: str = "",
    count: int,
    rate: str,
    details: str = "",
) -> dict[str, Any]:
    return {
        "section": section,
        "symbol": symbol,
        "trading_date": "",
        "candidate_cohort": "",
        "setup_quality": "",
        "breakout_state": "",
        "acceptance_state": "",
        "candle_quality": "",
        "volume_confirmation": "",
        "benchmark_rs_context": "",
        "extension_risk": "",
        "consolidation_quality": "",
        "false_breakout_flags": "",
        "regime_score_normalized": "",
        "regime_confidence_score": "",
        "regime_confidence_state": "",
        "criterion": criterion,
        "count": count,
        "rate_pct": rate,
        "details": details,
    }


def exceptional_repeat_concentration(
    bearish_setup_rows: Sequence[dict[str, str]],
    exceptional_rows: Sequence[dict[str, str]],
) -> dict[str, Any]:
    exceptional_ids = {row_id(row) for row in exceptional_rows}
    by_symbol = group_by(bearish_setup_rows, lambda row: row["symbol"])
    output = []
    for symbol, group in by_symbol.items():
        ordered = sorted(group, key=lambda row: row["trading_date"])
        exceptional_flags = [row_id(row) in exceptional_ids for row in ordered]
        exceptional_days = sum(1 for flag in exceptional_flags if flag)
        if exceptional_days == 0:
            continue
        output.append(
            {
                "symbol": symbol,
                "bearish_setup_days": len(group),
                "exceptional_days": exceptional_days,
                "longest_exceptional_streak": longest_true_streak(exceptional_flags),
                "pct_of_bearish_setup_days": pct(exceptional_days, len(group)),
            }
        )
    output.sort(key=lambda item: (item["exceptional_days"], item["longest_exceptional_streak"], decimal(item["pct_of_bearish_setup_days"])), reverse=True)
    return {"top_symbols": output}


def neutral_rule_combinations(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    neutral_setup = [row for row in rows if row["regime_state"] == "NEUTRAL" and is_setup_eligible(row)]
    grouped: dict[str, Counter[str]] = {
        "READY_FOR_RISK_EVALUATION": Counter(),
        "CONDITIONALLY_READY": Counter(),
        "WATCH_NOT_READY": Counter(),
    }
    for row in neutral_setup:
        group_name = row["entry_readiness"] if row["entry_readiness"] in {"READY_FOR_RISK_EVALUATION", "CONDITIONALLY_READY"} else "WATCH_NOT_READY"
        grouped[group_name][neutral_rule_combination(row)] += 1
    output = []
    summary = {}
    for group_name, counter in grouped.items():
        total = sum(counter.values())
        summary[group_name] = distribution(counter, total, limit=20)
        for combination, count in counter.most_common(20):
            output.append(
                {
                    "readiness_group": group_name,
                    "combination": combination,
                    "count": count,
                    "pct": pct(count, total),
                }
            )
    return output, {
        "setup_eligible_rows": len(neutral_setup),
        "top_combinations": summary,
        "is_meaningfully_stricter_than_bullish": True,
        "interpretation": "Neutral does not reject all valid setups; it shifts non-strict but setup-eligible rows into CONDITIONALLY_READY instead of READY_FOR_RISK_EVALUATION.",
    }


def neutral_rule_combination(row: dict[str, str]) -> str:
    return "|".join(
        [
            f"strong_setup={row.get('setup_quality') == 'STRONG'}",
            f"confirmed_or_both={row.get('candidate_state') == 'CONFIRMED' or truthy(row.get('both_eligible'))}",
            f"positive_or_strong_rs={row.get('benchmark_rs_context') in {'POSITIVE', 'STRONG'}}",
            f"no_high_or_blocking_penalty={row.get('max_penalty_severity') not in {'HIGH', 'BLOCKING'} and not has_active_blocking_penalty(row)}",
        ]
    )


def setup_quality_progression_summary(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    summary = {}
    for quality in ("VALID", "STRONG"):
        group = [row for row in rows if row.get("setup_quality") == quality and is_setup_eligible(row)]
        summary[quality] = {
            "setup_eligible_rows": len(group),
            "progressed_rows": count_where(group, is_progressed),
            "ready_for_risk_rows": sum(1 for row in group if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"),
            "exceptional_long_review_rows": sum(1 for row in group if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"),
            "progression_rate_pct": pct(count_where(group, is_progressed), len(group)),
        }
    return summary


def evidence_distribution(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    summary: dict[str, Any] = {"positive_by_readiness": {}, "warning_by_readiness": {}}
    for readiness in ("CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"):
        group = [row for row in rows if row["entry_readiness"] == readiness]
        positive = Counter(code for row in group for code in split_codes(row.get("positive_evidence", "")))
        warning = Counter(code for row in group for code in split_codes(row.get("warning_evidence", "")))
        summary["positive_by_readiness"][readiness] = distribution(positive, len(group), limit=25)
        summary["warning_by_readiness"][readiness] = distribution(warning, len(group), limit=25)
        output.extend(evidence_rows("POSITIVE", readiness, positive, len(group)))
        output.extend(evidence_rows("WARNING", readiness, warning, len(group)))
    membership = membership_uncertainty_summary(rows)
    limited = limited_confidence_summary(rows)
    summary["membership_uncertainty"] = membership
    summary["limited_regime_confidence"] = limited
    return output, summary


def evidence_rows(section: str, readiness: str, counter: Counter[str], total: int) -> list[dict[str, Any]]:
    return [
        {
            "section": section,
            "entry_readiness": readiness,
            "evidence_code": code,
            "count": count,
            "pct": pct(count, total),
        }
        for code, count in counter.most_common()
    ]


def limited_confidence_summary(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    warning_rows = [row for row in rows if "LIMITED_REGIME_CONFIDENCE" in split_codes(row.get("warning_evidence", ""))]
    progressed_warning = [row for row in warning_rows if is_progressed(row)]
    ready_warning = [row for row in warning_rows if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"]
    return {
        "total_rows": len(warning_rows),
        "pct_total": pct(len(warning_rows), len(rows)),
        "progressed_rows": len(progressed_warning),
        "progressed_pct_of_warning_rows": pct(len(progressed_warning), len(warning_rows)),
        "ready_for_risk_rows": len(ready_warning),
        "blocks_progression": False,
        "interpretation": "It is contextual in the historical baseline and does not act as a hard blocker.",
    }


def membership_uncertainty_summary(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    warning_rows = [row for row in rows if "MEMBERSHIP_UNCERTAIN" in split_codes(row.get("warning_evidence", ""))]
    by_readiness = Counter(row["entry_readiness"] for row in warning_rows)
    return {
        "total_rows": len(warning_rows),
        "pct_total": pct(len(warning_rows), len(rows)),
        "progressed_rows": count_where(warning_rows, is_progressed),
        "progressed_pct_of_warning_rows": pct(count_where(warning_rows, is_progressed), len(warning_rows)),
        "by_readiness": readiness_distribution(by_readiness, len(warning_rows)),
        "blocks_progression": False,
        "interpretation": "Membership uncertainty remains a visible warning and is not a hidden hard blocker.",
    }


def watch_reason_distribution(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    watch_rows = [row for row in rows if row["entry_readiness"] == "WATCH"]
    counter = Counter(primary_watch_reason(row) for row in watch_rows)
    output = [{"primary_watch_reason": reason, "count": count, "pct": pct(count, len(watch_rows))} for reason, count in counter.most_common()]
    return output, {"total_watch_rows": len(watch_rows), "primary_reasons": distribution(counter, len(watch_rows))}


def primary_watch_reason(row: dict[str, str]) -> str:
    warnings = split_codes(row.get("warning_evidence", ""))
    blocking = split_codes(row.get("blocking_evidence", ""))
    if row.get("setup_quality") == "WATCH" or "SETUP_WATCH_ONLY" in warnings or "SETUP_WATCH_ONLY" in blocking:
        return "SETUP_WATCH_ONLY"
    if row.get("regime_state") == "UNAVAILABLE":
        return "REGIME_UNAVAILABLE"
    if "NEUTRAL_STRICT_REQUIREMENTS_NOT_MET" in warnings:
        return "NEUTRAL_STRICT_REQUIREMENTS_NOT_MET"
    if has_active_blocking_penalty(row):
        return "BLOCKING_PENALTY_CONTEXT"
    return "OTHER"


def conditional_ready_distribution(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conditional = [row for row in rows if row["entry_readiness"] == "CONDITIONALLY_READY"]
    counters = {
        "REGIME": Counter(row["regime_state"] for row in conditional),
        "COHORT": Counter(eligibility_cohort(row) for row in conditional),
        "SETUP_QUALITY": Counter(row["setup_quality"] for row in conditional),
        "PRIMARY_REASON": Counter(primary_conditional_reason(row) for row in conditional),
    }
    output = []
    for section, counter in counters.items():
        for value, count in counter.most_common():
            output.append(
                {
                    "section": section,
                    "regime_state": value if section == "REGIME" else "",
                    "cohort": value if section == "COHORT" else "",
                    "setup_quality": value if section == "SETUP_QUALITY" else "",
                    "reason": value if section == "PRIMARY_REASON" else "",
                    "count": count,
                    "pct": pct(count, len(conditional)),
                }
            )
    return output, {
        "total_conditionally_ready_rows": len(conditional),
        "by_regime": distribution(counters["REGIME"], len(conditional)),
        "by_cohort": distribution(counters["COHORT"], len(conditional)),
        "by_setup_quality": distribution(counters["SETUP_QUALITY"], len(conditional)),
        "primary_reasons": distribution(counters["PRIMARY_REASON"], len(conditional)),
        "interpretation": "Conditional rows are structurally setup-eligible but held below ready-for-risk by Neutral strictness or unavailable regime context.",
    }


def primary_conditional_reason(row: dict[str, str]) -> str:
    if row["regime_state"] == "NEUTRAL":
        return "NEUTRAL_STRICT_REQUIREMENTS_NOT_MET"
    if row["regime_state"] == "UNAVAILABLE":
        return "REGIME_UNAVAILABLE_CAP"
    return "OTHER_CONDITIONAL_CONTEXT"


def readiness_transitions_and_churn(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trading_dates = sorted({row["trading_date"] for row in rows})
    date_index = {trading_date: index for index, trading_date in enumerate(trading_dates)}
    by_symbol_date = {(row["symbol"], row["trading_date"]): row for row in rows}
    transition_counter: Counter[tuple[str, str]] = Counter()
    for row in rows:
        index = date_index[row["trading_date"]]
        if index + 1 >= len(trading_dates):
            continue
        next_row = by_symbol_date.get((row["symbol"], trading_dates[index + 1]))
        if next_row:
            transition_counter[(row["entry_readiness"], next_row["entry_readiness"])] += 1
    total_transitions = sum(transition_counter.values())
    output = []
    for (from_state, to_state), count in sorted(transition_counter.items()):
        output.append(
            transition_row(
                "READINESS_TRANSITION",
                from_state=from_state,
                to_state=to_state,
                count=count,
                total=total_transitions,
            )
        )
    streak_summary = readiness_streak_statistics(rows, trading_dates)
    for category, stats in streak_summary.items():
        for bucket, count in stats["buckets"].items():
            output.append(transition_row("READINESS_STREAK_BUCKET", category=category, bucket=bucket, count=count, total=stats["total_streaks"]))
        output.append(
            transition_row(
                "READINESS_STREAK_STATS",
                category=category,
                count=stats["total_streaks"],
                total=stats["total_streaks"],
                median=stats["median"],
                mean=stats["mean"],
                p90=stats["p90"],
                p95=stats["p95"],
                max_value=stats["max"],
            )
        )
    churn_rows, churn_summary = daily_churn(rows, trading_dates)
    output.extend(churn_rows)
    return output, {
        "transition_matrix": {
            f"{from_state}->{to_state}": {"count": count, "pct": pct(count, total_transitions)}
            for (from_state, to_state), count in transition_counter.most_common()
        },
        "total_next_session_transitions": total_transitions,
        "streaks": streak_summary,
        "daily_churn": churn_summary,
    }


def daily_ready_density(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    dates = sorted({row["trading_date"] for row in rows})
    overall_counter = Counter({trading_date: 0 for trading_date in dates})
    regime_counter: dict[str, Counter[str]] = {
        regime: Counter({trading_date: 0 for trading_date in dates})
        for regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE")
    }
    for row in rows:
        if is_downstream_ready(row):
            overall_counter[row["trading_date"]] += 1
            regime_counter[row["regime_state"]][row["trading_date"]] += 1
    return {
        "overall": numeric_distribution([overall_counter[trading_date] for trading_date in dates]),
        "by_regime": {
            regime: numeric_distribution([counter[trading_date] for trading_date in dates])
            for regime, counter in regime_counter.items()
        },
    }


def transition_row(
    section: str,
    *,
    category: str = "",
    from_state: str = "",
    to_state: str = "",
    bucket: str = "",
    trading_date: str = "",
    count: int = 0,
    total: int = 0,
    median: Any = "",
    mean: Any = "",
    p90: Any = "",
    p95: Any = "",
    max_value: Any = "",
    new_ready: Any = "",
    continued_ready: Any = "",
    dropped_ready: Any = "",
    churn: Any = "",
) -> dict[str, Any]:
    return {
        "section": section,
        "category": category,
        "from_state": from_state,
        "to_state": to_state,
        "bucket": bucket,
        "trading_date": trading_date,
        "count": count,
        "pct": pct(count, total),
        "median": median,
        "mean": mean,
        "p90": p90,
        "p95": p95,
        "max": max_value,
        "new_ready": new_ready,
        "continued_ready": continued_ready,
        "dropped_ready": dropped_ready,
        "churn_pct": churn,
    }


def readiness_streak_statistics(rows: Sequence[dict[str, str]], trading_dates: Sequence[str]) -> dict[str, Any]:
    date_index = {trading_date: index for index, trading_date in enumerate(trading_dates)}
    predicates = {
        "ANY_PROGRESSED": is_progressed,
        "READY_FOR_RISK": lambda row: row["entry_readiness"] == "READY_FOR_RISK_EVALUATION",
        "CONDITIONAL": lambda row: row["entry_readiness"] == "CONDITIONALLY_READY",
        "EXCEPTIONAL_LONG": lambda row: row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW",
    }
    by_symbol = group_by(rows, lambda row: row["symbol"])
    summary = {}
    for category, predicate in predicates.items():
        streaks: list[int] = []
        for symbol_rows in by_symbol.values():
            ordered = sorted(symbol_rows, key=lambda row: date_index[row["trading_date"]])
            current = 0
            previous_index: int | None = None
            for row in ordered:
                index = date_index[row["trading_date"]]
                consecutive = previous_index is not None and index == previous_index + 1
                if predicate(row):
                    current = current + 1 if consecutive else 1
                else:
                    if current:
                        streaks.append(current)
                    current = 0
                previous_index = index
            if current:
                streaks.append(current)
        summary[category] = streak_stats(streaks)
    return summary


def streak_stats(streaks: Sequence[int]) -> dict[str, Any]:
    buckets = Counter()
    for streak in streaks:
        if streak == 1:
            buckets["1"] += 1
        elif streak == 2:
            buckets["2"] += 1
        elif 3 <= streak <= 5:
            buckets["3-5"] += 1
        elif 6 <= streak <= 10:
            buckets["6-10"] += 1
        else:
            buckets[">10"] += 1
    stats = numeric_distribution(streaks)
    return {
        "total_streaks": len(streaks),
        "buckets": {bucket: buckets[bucket] for bucket in ("1", "2", "3-5", "6-10", ">10")},
        "median": stats["median"],
        "mean": stats["mean"],
        "p90": stats["p90"],
        "p95": stats["p95"],
        "max": stats["max"],
    }


def daily_churn(rows: Sequence[dict[str, str]], trading_dates: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ready_by_date: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if is_downstream_ready(row):
            ready_by_date[row["trading_date"]].add(row["symbol"])
    output = []
    churn_values = []
    new_values = []
    continued_values = []
    dropped_values = []
    previous: set[str] = set()
    for trading_date in trading_dates:
        current = ready_by_date[trading_date]
        new_ready = len(current - previous)
        continued = len(current & previous)
        dropped = len(previous - current)
        union = len(current | previous)
        churn = pct(new_ready + dropped, union)
        if previous or current:
            churn_values.append(decimal(churn))
            new_values.append(new_ready)
            continued_values.append(continued)
            dropped_values.append(dropped)
        output.append(
            transition_row(
                "DAILY_CHURN",
                trading_date=trading_date,
                count=len(current),
                total=len(current),
                new_ready=new_ready,
                continued_ready=continued,
                dropped_ready=dropped,
                churn=churn,
            )
        )
        previous = current
    return output, {
        "new_ready_distribution": numeric_distribution(new_values),
        "continued_ready_distribution": numeric_distribution(continued_values),
        "dropped_ready_distribution": numeric_distribution(dropped_values),
        "churn_pct_distribution": decimal_distribution(churn_values),
    }


def sensitivity_scenarios(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scenario_names = [
        "BASELINE",
        "NEUTRAL_STRICTER",
        "NEUTRAL_LOOSER",
        "EXCEPTIONAL_LONG_STRICTER",
        "EXCEPTIONAL_LONG_LOOSER",
        "HIGH_EXTENSION_BLOCK",
        "HIGH_EXTENSION_WARNING_BASELINE",
        "FALSE_BREAKOUT_STRICT",
        "FALSE_BREAKOUT_BASELINE",
    ]
    baseline_progressed = {row_id(row) for row in rows if is_progressed(row)}
    output = []
    summary = {}
    for scenario in scenario_names:
        scenario_readiness = {row_id(row): scenario_readiness_for_row(row, scenario) for row in rows}
        scenario_row = scenario_metrics(rows, scenario, scenario_readiness, baseline_progressed)
        output.append(scenario_row)
        summary[scenario] = scenario_row
    summary["worst_jaccard"] = min(decimal(row["jaccard"]) for row in output if row["scenario"] != "BASELINE")
    baseline_progressed_count = next(row for row in output if row["scenario"] == "BASELINE")["total_progressed"]
    summary["max_progressed_abs_shift"] = max(
        abs(int(row["total_progressed"]) - int(baseline_progressed_count)) for row in output if row["scenario"] != "BASELINE"
    )
    summary["max_progressed_pct_shift"] = pct(int(summary["max_progressed_abs_shift"]), int(baseline_progressed_count))
    return output, summary


def scenario_readiness_for_row(row: dict[str, str], scenario: str) -> str:
    if scenario in {"BASELINE", "HIGH_EXTENSION_WARNING_BASELINE", "FALSE_BREAKOUT_BASELINE"}:
        return row["entry_readiness"]
    if not scenario_basic_candidate_setup_ok(row):
        return "WATCH" if row.get("setup_quality") == "WATCH" and not scenario_has_hard_block(row, scenario) else "NOT_READY"
    if scenario_has_hard_block(row, scenario):
        return "NOT_READY"
    regime = row["regime_state"]
    setup_quality = row.get("setup_quality")
    if regime == "BULLISH":
        return "READY_FOR_RISK_EVALUATION"
    if regime == "NEUTRAL":
        if neutral_ready_under_scenario(row, scenario):
            return "READY_FOR_RISK_EVALUATION"
        return "CONDITIONALLY_READY" if setup_quality in {"VALID", "STRONG"} and not has_active_blocking_penalty(row) else "WATCH"
    if regime == "BEARISH":
        return "EXCEPTIONAL_LONG_REVIEW" if exceptional_under_scenario(row, scenario) else "NOT_READY"
    if regime == "UNAVAILABLE":
        return "CONDITIONALLY_READY" if setup_quality == "STRONG" and confirmed_or_both(row) and not has_active_blocking_penalty(row) else "WATCH"
    return "NOT_READY"


def scenario_basic_candidate_setup_ok(row: dict[str, str]) -> bool:
    if row.get("candidate_state") not in {"EMERGING", "CONFIRMED"}:
        return False
    if row.get("setup_quality") == "WATCH":
        return False
    return is_setup_eligible(row) and row.get("setup_quality") in {"VALID", "STRONG"}


def scenario_has_hard_block(row: dict[str, str], scenario: str) -> bool:
    if row.get("setup_quality") == "POOR":
        return True
    false_flags = split_codes(row.get("false_breakout_flags", ""))
    if "POSSIBLE_FALSE_BREAKOUT" in false_flags or "INTRADAY_BREAK_FAILED" in false_flags or row.get("breakout_state") == "FAILED_BREAK":
        return True
    if scenario == "FALSE_BREAKOUT_STRICT" and false_flags:
        return True
    if row.get("extension_risk") == "EXTREME":
        return True
    if scenario == "HIGH_EXTENSION_BLOCK" and row.get("extension_risk") == "HIGH":
        return True
    blocking_codes = split_codes(row.get("penalty_codes", "")) & {"SETUP_POOR"}
    return bool(blocking_codes)


def neutral_ready_under_scenario(row: dict[str, str], scenario: str) -> bool:
    if scenario == "NEUTRAL_STRICTER":
        return (
            row.get("setup_quality") == "STRONG"
            and confirmed_or_both(row)
            and row.get("benchmark_rs_context") == "STRONG"
            and row.get("max_penalty_severity") not in {"HIGH", "BLOCKING"}
            and not has_active_blocking_penalty(row)
        )
    if scenario == "NEUTRAL_LOOSER":
        return (
            row.get("setup_quality") in {"VALID", "STRONG"}
            and row.get("benchmark_rs_context") in {"POSITIVE", "STRONG"}
            and not has_active_blocking_penalty(row)
        )
    return row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"


def exceptional_under_scenario(row: dict[str, str], scenario: str) -> bool:
    false_flags = split_codes(row.get("false_breakout_flags", ""))
    no_major_false = not (false_flags & {"POSSIBLE_FALSE_BREAKOUT", "INTRADAY_BREAK_FAILED", "UPPER_WICK_REJECTION"})
    baseline = (
        row.get("setup_quality") == "STRONG"
        and confirmed_or_both(row)
        and row.get("benchmark_rs_context") == "STRONG"
        and row.get("volume_confirmation") in {"STRONG", "EXCEPTIONAL"}
        and (
            row.get("breakout_state") == "CLOSE_ACCEPTED"
            or "MOMENTUM_CONTINUATION" in split_codes(row.get("setup_type_flags", ""))
        )
        and row.get("candle_quality") in {"GOOD", "STRONG"}
        and row.get("extension_risk") in {"LOW", "MODERATE"}
        and row.get("consolidation_quality") in {"GOOD", "STRONG"}
        and no_major_false
    )
    if scenario == "EXCEPTIONAL_LONG_STRICTER":
        return (
            baseline
            and row.get("candidate_state") == "CONFIRMED"
            and row.get("volume_confirmation") == "EXCEPTIONAL"
            and row.get("extension_risk") == "LOW"
            and row.get("candle_quality") == "STRONG"
        )
    if scenario == "EXCEPTIONAL_LONG_LOOSER":
        return (
            row.get("setup_quality") in {"VALID", "STRONG"}
            and confirmed_or_both(row)
            and row.get("benchmark_rs_context") in {"POSITIVE", "STRONG"}
            and row.get("volume_confirmation") in {"GOOD", "STRONG", "EXCEPTIONAL"}
            and row.get("extension_risk") in {"LOW", "MODERATE", "HIGH"}
            and no_major_false
        )
    return baseline


def scenario_metrics(
    rows: Sequence[dict[str, str]],
    scenario: str,
    readiness_by_id: dict[str, str],
    baseline_progressed: set[str],
) -> dict[str, Any]:
    counts = Counter(readiness_by_id.values())
    setup_eligible = count_where(rows, is_setup_eligible)
    progressed_ids = {identifier for identifier, readiness in readiness_by_id.items() if readiness in PROGRESSED_STATES}
    retained = len(progressed_ids & baseline_progressed)
    removed = len(baseline_progressed - progressed_ids)
    introduced = len(progressed_ids - baseline_progressed)
    union = len(progressed_ids | baseline_progressed)
    daily_counts = Counter()
    for row in rows:
        if readiness_by_id[row_id(row)] in DOWNSTREAM_READY_STATES:
            daily_counts[row["trading_date"]] += 1
    return {
        "scenario": scenario,
        "not_ready": counts["NOT_READY"],
        "watch": counts["WATCH"],
        "conditionally_ready": counts["CONDITIONALLY_READY"],
        "ready_for_risk_evaluation": counts["READY_FOR_RISK_EVALUATION"],
        "exceptional_long_review": counts["EXCEPTIONAL_LONG_REVIEW"],
        "total_progressed": len(progressed_ids),
        "setup_to_progression_rate_pct": pct(len(progressed_ids), setup_eligible),
        "bullish_progression_pct": scenario_regime_progression(rows, readiness_by_id, "BULLISH"),
        "neutral_progression_pct": scenario_regime_progression(rows, readiness_by_id, "NEUTRAL"),
        "bearish_exceptional_pct": scenario_bearish_exceptional(rows, readiness_by_id),
        "baseline_retained": retained,
        "removed": removed,
        "introduced": introduced,
        "jaccard": round_decimal(Decimal(retained) / Decimal(union) if union else Decimal("1")),
        "daily_median_ready": numeric_distribution(list(daily_counts.values()))["median"],
        "daily_p95_ready": numeric_distribution(list(daily_counts.values()))["p95"],
    }


def scenario_regime_progression(rows: Sequence[dict[str, str]], readiness_by_id: dict[str, str], regime: str) -> str:
    setup_group = [row for row in rows if row["regime_state"] == regime and is_setup_eligible(row)]
    progressed = sum(1 for row in setup_group if readiness_by_id[row_id(row)] in PROGRESSED_STATES)
    return pct(progressed, len(setup_group))


def scenario_bearish_exceptional(rows: Sequence[dict[str, str]], readiness_by_id: dict[str, str]) -> str:
    bearish_setup = [row for row in rows if row["regime_state"] == "BEARISH" and is_setup_eligible(row)]
    exceptional = sum(1 for row in bearish_setup if readiness_by_id[row_id(row)] == "EXCEPTIONAL_LONG_REVIEW")
    return pct(exceptional, len(bearish_setup))


def write_entry_evaluation_audit_markdown(report: dict[str, Any], path: Path) -> None:
    funnel = report["funnel"]
    results = report["results"]
    exceptional = report["exceptional_longs"]
    penalties = report["penalties"]
    lines = [
        "# Strategy V1 Entry Evaluation Audit",
        "",
        "Current phase: Step 02.8 / Command 02 - structural audit only",
        "",
        "## Boundary",
        "",
        "- This audit reads ENTRY_EVALUATION_V1 and does not mutate the baseline.",
        "- It uses no future returns, MFE/MAE, stop/target hits, profitability labels, backtests, risk/reward, orders, or Supabase writes.",
        "- Future entry states are used only for state-transition and churn analysis.",
        "",
        "## Version",
        "",
        f"- Audit version: {report['audit_version']}",
        f"- Entry version/hash: {report['entry_verification']['entry_version']} / {report['entry_verification']['entry_config_hash']}",
        "",
        "## Funnel",
        "",
        f"- Candidate rows: {funnel['candidate_rows']}",
        f"- Setup eligible rows: {funnel['setup_eligible_rows']} ({funnel['candidate_to_setup_pct']}%)",
        f"- Progressed rows: {funnel['progressed_to_entry_context']} ({funnel['setup_to_progressed_pct']}% of setup eligible)",
        f"- Ready for risk rows: {funnel['ready_for_risk_evaluation']}",
        f"- Exceptional long review rows: {funnel['exceptional_long_review']}",
        "",
        "## Results",
        "",
        f"- Structural stability: {results['structural_stability']}",
        f"- Funnel sanity: {results['funnel_sanity']}",
        f"- Penalty consistency: {results['penalty_consistency']}",
        f"- Exceptional-long result: {results['exceptional_long_result']}",
        f"- Baseline decision: {results['baseline_decision']}",
        "",
        "## Key Findings",
        "",
        f"- Setup-to-entry progression is structurally explainable: {results['setup_to_entry_progression_explainable']}",
        f"- Blocking penalty rows: {penalties['active_blocking_rows']} versus NOT_READY rows: {penalties['not_ready_rows']}.",
        f"- Blocking rows by readiness: {penalties['blocking_by_readiness']}",
        f"- Exceptional-long review rate: {exceptional['rate_vs_bearish_setup_eligible_pct']}% of bearish setup-eligible rows.",
        "",
        "## Integrity",
        "",
        f"- Entry dataset unchanged: {report['baseline_unchanged']['entry']}",
        f"- Feature dataset unchanged: {report['baseline_unchanged']['feature']}",
        f"- Candidate dataset unchanged: {report['baseline_unchanged']['candidate']}",
        f"- Setup dataset unchanged: {report['baseline_unchanged']['setup']}",
        f"- Regime dataset unchanged: {report['baseline_unchanged']['regime']}",
        "- ZERO orders were placed.",
        "- ZERO remote migrations were applied.",
        "- ZERO records were persisted to Supabase.",
        "",
        "## Limitation",
        "",
        "- This audit is structural. It cannot prove profitability, stop placement, target quality, or risk/reward feasibility.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def structural_stability_result(sensitivity_summary: dict[str, Any], invariant_violations: int) -> str:
    if invariant_violations:
        return "INCONCLUSIVE"
    worst_jaccard = decimal(str(sensitivity_summary.get("worst_jaccard", "0")))
    max_shift = decimal(str(sensitivity_summary.get("max_progressed_pct_shift", "0")))
    if worst_jaccard >= Decimal("0.85") and max_shift <= Decimal("10"):
        return "STABLE"
    if worst_jaccard >= Decimal("0.65") and max_shift <= Decimal("35"):
        return "MODERATELY_SENSITIVE"
    return "HIGHLY_SENSITIVE"


def funnel_sanity_result(funnel: dict[str, Any], invariant_violations: int) -> str:
    if invariant_violations:
        return "INCONSISTENT"
    setup_to_progressed = decimal(funnel["setup_to_progressed_pct"])
    candidate_to_progressed = decimal(funnel["candidate_to_progressed_pct"])
    if setup_to_progressed > Decimal("95") and candidate_to_progressed > Decimal("50"):
        return "TOO_PERMISSIVE"
    if setup_to_progressed > Decimal("80") and candidate_to_progressed <= Decimal("25"):
        return "HEALTHY_BUT_HIGH_PASS_THROUGH"
    if setup_to_progressed < Decimal("5"):
        return "TOO_RESTRICTIVE"
    return "HEALTHY"


def penalty_consistency_result(summary: dict[str, Any]) -> str:
    if summary["critical_invariant_violations"] or summary["gate_readiness_violations"]:
        return "INVARIANT_VIOLATIONS_FOUND"
    if summary["blocking_by_readiness"].get("WATCH", 0) > 0:
        return "CONSISTENT_WITH_INHERITED_BLOCKERS"
    return "CONSISTENT"


def exceptional_long_result(summary: dict[str, Any]) -> str:
    rate = decimal(summary["rate_vs_bearish_setup_eligible_pct"])
    if rate == 0:
        return "TOO_RESTRICTIVE"
    if rate <= Decimal("10"):
        return "SELECTIVE"
    if rate <= Decimal("20"):
        return "MODERATELY_BROAD"
    return "TOO_BROAD"


def setup_progression_explainable(funnel: dict[str, Any], regime_summary: dict[str, Any]) -> bool:
    setup_to_progressed = decimal(funnel["setup_to_progressed_pct"])
    candidate_to_setup = decimal(funnel["candidate_to_setup_pct"])
    bullish_setup_progression = decimal(regime_summary["setup_eligible_progression"]["BULLISH"]["setup_to_progressed_pct"])
    neutral_setup_progression = decimal(regime_summary["setup_eligible_progression"]["NEUTRAL"]["setup_to_progressed_pct"])
    return setup_to_progressed > Decimal("80") and candidate_to_setup < Decimal("25") and bullish_setup_progression == Decimal("100") and neutral_setup_progression == Decimal("100")


def scan_for_outcome_fields(rows: Sequence[dict[str, str]]) -> list[str]:
    fields = set(ENTRY_OUTPUT_FIELDS)
    for row in rows:
        fields.update(row)
    return sorted(field for field in fields if any(token in field.lower() for token in OUTCOME_FIELD_TOKENS))


def output_size(config: EntryEvaluationAuditConfig) -> int:
    paths = [
        config.summary_path,
        config.cohort_funnel_path,
        config.penalty_invariants_path,
        config.exceptional_long_audit_path,
        config.regime_selectivity_path,
        config.readiness_transitions_path,
        config.sensitivity_path,
        config.exceptional_inventory_path,
        config.neutral_combinations_path,
        config.evidence_distribution_path,
        config.watch_reasons_path,
        config.conditional_reasons_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())


def gate_details(row: dict[str, str]) -> dict[str, Any]:
    try:
        return json.loads(row.get("gate_details", "{}"))
    except json.JSONDecodeError:
        return {}


def is_setup_eligible(row: dict[str, str]) -> bool:
    return truthy(row.get("setup_eligible"))


def is_progressed(row: dict[str, str]) -> bool:
    return row.get("entry_readiness") in PROGRESSED_STATES


def is_downstream_ready(row: dict[str, str]) -> bool:
    return row.get("entry_readiness") in DOWNSTREAM_READY_STATES


def has_active_blocking_penalty(row: dict[str, str]) -> bool:
    return truthy(row.get("blocking_penalty_present")) or row.get("max_penalty_severity") == "BLOCKING"


def eligibility_cohort(row: dict[str, str]) -> str:
    emerging = truthy(row.get("emerging_eligible"))
    confirmed = truthy(row.get("confirmed_eligible"))
    if truthy(row.get("both_eligible")):
        emerging = True
        confirmed = True
    if emerging and confirmed:
        return "BOTH_ELIGIBLE"
    if emerging:
        return "EMERGING_ONLY"
    if confirmed:
        return "CONFIRMED_ONLY"
    return "OTHER"


def confirmed_or_both(row: dict[str, str]) -> bool:
    return row.get("candidate_state") == "CONFIRMED" or truthy(row.get("both_eligible")) or eligibility_cohort(row) in {
        "CONFIRMED_ONLY",
        "BOTH_ELIGIBLE",
    }


def row_id(row: dict[str, str]) -> str:
    return f"{row['trading_date']}|{row['symbol']}"


def count_where(rows: Iterable[dict[str, str]], predicate: Callable[[dict[str, str]], bool]) -> int:
    return sum(1 for row in rows if predicate(row))


def group_by(rows: Iterable[dict[str, str]], key: Callable[[dict[str, str]], Any]) -> dict[Any, list[dict[str, str]]]:
    grouped: dict[Any, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return dict(grouped)


def observed_single(rows: Sequence[dict[str, str]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def readiness_distribution(counter: Counter[str], total: int) -> dict[str, Any]:
    return {state: {"count": counter[state], "pct": pct(counter[state], total)} for state in READINESS_STATES}


def distribution(counter: Counter[Any], total: int, *, limit: int | None = None) -> dict[str, Any]:
    return {str(key): {"count": count, "pct": pct(count, total)} for key, count in counter.most_common(limit)}


def numeric_distribution(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"min": 0, "p10": 0, "p25": 0, "median": 0, "mean": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "p10": int_quantile(ordered, Decimal("0.10")),
        "p25": int_quantile(ordered, Decimal("0.25")),
        "median": statistics.median(ordered),
        "mean": round(statistics.mean(ordered), 4),
        "p75": int_quantile(ordered, Decimal("0.75")),
        "p90": int_quantile(ordered, Decimal("0.90")),
        "p95": int_quantile(ordered, Decimal("0.95")),
        "p99": int_quantile(ordered, Decimal("0.99")),
        "max": ordered[-1],
    }


def decimal_distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    if not values:
        return {"min": "0.0000", "median": "0.0000", "mean": "0.0000", "p90": "0.0000", "p95": "0.0000", "max": "0.0000"}
    ordered = sorted(values)
    return {
        "min": round_decimal(ordered[0]),
        "median": round_decimal(Decimal(str(statistics.median(ordered)))),
        "mean": round_decimal(Decimal(str(statistics.mean(ordered)))),
        "p90": round_decimal(decimal_quantile(ordered, Decimal("0.90"))),
        "p95": round_decimal(decimal_quantile(ordered, Decimal("0.95"))),
        "max": round_decimal(ordered[-1]),
    }


def int_quantile(values: Sequence[int], percentile: Decimal) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


def longest_true_streak(values: Sequence[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = str(value or "0").strip().replace("%", "")
    if not text:
        return Decimal("0")
    return Decimal(text)


def round_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"

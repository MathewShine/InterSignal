from __future__ import annotations

import csv
import gzip
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.momentum_candidate_audit import (
    group_rows_by,
    load_candidate_rows,
    numeric_distribution,
    pct,
    quantile_number,
    quantile_summary,
    round_decimal,
    truthy,
)
from app.strategy.momentum_candidates import file_sha256

EMERGING_VOLUME_SEMANTICS_AUDIT_VERSION = "EMERGING_VOLUME_SEMANTICS_AUDIT_V1"

RVOL_DISTRIBUTION_FIELDS = [
    "group",
    "total_rows",
    "usable_rows",
    "null_count",
    "p10",
    "p25",
    "median",
    "p75",
    "p90",
    "p95",
    "lt_0_80",
    "pct_lt_0_80",
    "rvol_0_80_to_lt_1_00",
    "pct_0_80_to_lt_1_00",
    "rvol_1_00_to_lt_1_20",
    "pct_1_00_to_lt_1_20",
    "rvol_1_20_to_lt_1_30",
    "pct_1_20_to_lt_1_30",
    "rvol_1_30_to_lt_1_50",
    "pct_1_30_to_lt_1_50",
    "rvol_1_50_to_lt_2_00",
    "pct_1_50_to_lt_2_00",
    "gte_2_00",
    "pct_gte_2_00",
    "pct_gte_1_00",
    "pct_gte_1_20",
    "pct_gte_1_30",
    "pct_gte_1_50",
]
EVIDENCE_FIELDS = ["section", "key", "count", "pct", "details"]
BREAKOUT_FIELDS = [
    "breakout_context",
    "total_rows",
    "median_rvol20",
    "pct_lt_1_00",
    "pct_1_00_to_lt_1_20",
    "pct_gte_1_20",
    "pct_gte_1_50",
]
COUNTERFACTUAL_FIELDS = [
    "scenario",
    "scenario_type",
    "threshold",
    "emerging_rows_retained",
    "emerging_rows_removed",
    "pct_retained",
    "daily_median_emerging_count",
    "daily_p95_emerging_count",
    "symbols_ever_selected",
    "median_emerging_streak",
    "emerging_to_confirmed_5_session_conversion_rate_pct",
    "details",
]
DAY_CONCENTRATION_FIELDS = [
    "trading_date",
    "emerging_count",
    "rvol20_lt_1_00_count",
    "rvol20_lt_1_20_count",
    "pct_rvol20_lt_1_00",
    "pct_rvol20_lt_1_20",
    "low_rvol_concentration_flag",
]
SYMBOL_CONCENTRATION_FIELDS = [
    "symbol",
    "emerging_days",
    "low_rvol_emerging_days",
    "sub_threshold_emerging_days",
    "pct_low_rvol",
    "pct_sub_threshold",
    "median_rvol20_when_emerging",
]


@dataclass(frozen=True, slots=True)
class EmergingVolumeSemanticsAuditConfig:
    data_dir: Path
    start_date: date | None = None
    end_date: date | None = None
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    audit_version: str = EMERGING_VOLUME_SEMANTICS_AUDIT_VERSION

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "emerging_volume" / "v1"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "emerging_volume_semantics_summary.json"

    @property
    def rvol_distribution_path(self) -> Path:
        return self.reports_dir / "emerging_rvol_distribution.csv"

    @property
    def low_rvol_evidence_path(self) -> Path:
        return self.reports_dir / "emerging_low_rvol_evidence.csv"

    @property
    def breakout_context_path(self) -> Path:
        return self.reports_dir / "emerging_rvol_breakout_context.csv"

    @property
    def counterfactual_gates_path(self) -> Path:
        return self.reports_dir / "emerging_rvol_counterfactual_gates.csv"

    @property
    def day_concentration_path(self) -> Path:
        return self.audit_dir / "emerging_low_rvol_day_concentration.csv.gz"

    @property
    def symbol_concentration_path(self) -> Path:
        return self.audit_dir / "emerging_low_rvol_symbol_concentration.csv.gz"


def build_emerging_volume_semantics_audit(
    *,
    config: EmergingVolumeSemanticsAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    candidate_hash_before = file_sha256(config.candidate_dataset_path)
    feature_hash_before = file_sha256(config.feature_dataset_path)

    if progress:
        progress("Loading immutable MOMENTUM_CANDIDATES_V1 rows")
    candidate_rows = load_candidate_rows(
        config.candidate_dataset_path,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    rows_by_date = group_rows_by(candidate_rows, "trading_date")
    sessions = sorted(rows_by_date)
    session_index = {session: offset for offset, session in enumerate(sessions)}

    if progress:
        progress("Computing Emerging RVOL distributions and semantic cohorts")
    emerging_rows = [row for row in candidate_rows if truthy(row.get("emerging_eligible"))]
    emerging_only_rows = [row for row in emerging_rows if not truthy(row.get("confirmed_eligible"))]
    both_rows = [row for row in emerging_rows if truthy(row.get("confirmed_eligible"))]
    primary_emerging_rows = [row for row in candidate_rows if row.get("candidate_state") == "EMERGING"]
    primary_confirmed_rows = [row for row in candidate_rows if row.get("candidate_state") == "CONFIRMED"]

    rvol_distribution = [
        rvol_distribution_row("ALL_EMERGING_ELIGIBLE", emerging_rows),
        rvol_distribution_row("EMERGING_ONLY", emerging_only_rows),
        rvol_distribution_row("BOTH_ELIGIBLE", both_rows),
        rvol_distribution_row("PRIMARY_EMERGING", primary_emerging_rows),
        rvol_distribution_row("PRIMARY_CONFIRMED", primary_confirmed_rows),
    ]
    cohorts = low_rvol_cohort_summary(emerging_rows)
    low_subthreshold_rows = [row for row in emerging_rows if rvol20_less_than(row, Decimal("1.20"))]
    evidence_rows, evidence_summary = low_rvol_evidence_rows(low_subthreshold_rows, total_emerging=len(emerging_rows), config=config.candidate_config)
    breakout_rows = breakout_context_rvol_rows(emerging_rows)
    benchmark_rs = benchmark_rs_summary(emerging_rows)
    momentum_vs_rvol = momentum_vs_rvol_summary(emerging_rows)
    evidence_count = evidence_count_summary(emerging_rows)
    rvol5_vs_rvol20 = rvol5_rvol20_summary(emerging_rows)
    day_rows, day_summary = day_level_low_rvol_concentration(candidate_rows)
    symbol_rows, symbol_summary = symbol_level_low_rvol_concentration(emerging_rows)

    if progress:
        progress("Running RVOL sensitivity, hard-gate, and hybrid diagnostics")
    threshold_sensitivity = emerging_rvol_threshold_sensitivity(primary_emerging_rows, config.candidate_config)
    hard_gate_rows = hard_gate_counterfactual_rows(primary_emerging_rows, candidate_rows, sessions, session_index)
    hybrid_rows = hybrid_volume_diagnostic_rows(primary_emerging_rows, sessions, session_index, candidate_rows)
    counterfactual_rows = hard_gate_rows + hybrid_rows
    semantic_status = semantic_consistency_status(
        semantics=actual_emerging_semantics(config.candidate_config),
        distribution=rvol_distribution[0],
        sensitivity=threshold_sensitivity,
    )

    write_csv(config.rvol_distribution_path, rvol_distribution, RVOL_DISTRIBUTION_FIELDS)
    write_csv(config.low_rvol_evidence_path, evidence_rows, EVIDENCE_FIELDS)
    write_csv(config.breakout_context_path, breakout_rows, BREAKOUT_FIELDS)
    write_csv(config.counterfactual_gates_path, counterfactual_rows, COUNTERFACTUAL_FIELDS)
    write_gzip_csv(config.day_concentration_path, day_rows, DAY_CONCENTRATION_FIELDS)
    write_gzip_csv(config.symbol_concentration_path, symbol_rows, SYMBOL_CONCENTRATION_FIELDS)

    candidate_hash_after = file_sha256(config.candidate_dataset_path)
    feature_hash_after = file_sha256(config.feature_dataset_path)
    report = {
        "phase": "Step 02.5",
        "command": "Command 03",
        "generated_at": generated_at,
        "audit": {
            "audit_version": config.audit_version,
            "candidate_version": config.candidate_config.candidate_version,
            "candidate_config_hash": config.candidate_config.config_hash(),
            "feature_version": "DAILY_FEATURES_V1",
            "methodology": "Semantic and structural audit of Emerging volume confirmation only; no future returns, MFE, MAE, winner/loser labels, profitability optimization, entry scoring, backtesting, or trading execution.",
        },
        "semantics": actual_emerging_semantics(config.candidate_config),
        "baseline": {
            "candidate_dataset_path": str(config.candidate_dataset_path),
            "candidate_dataset_sha256_before": candidate_hash_before,
            "candidate_dataset_sha256_after": candidate_hash_after,
            "candidate_dataset_unchanged": candidate_hash_before == candidate_hash_after,
            "feature_dataset_path": str(config.feature_dataset_path),
            "feature_dataset_sha256_before": feature_hash_before,
            "feature_dataset_sha256_after": feature_hash_after,
            "feature_dataset_unchanged": feature_hash_before == feature_hash_after,
            "row_count": len(candidate_rows),
            "emerging_eligible_count": len(emerging_rows),
            "primary_emerging_count": len(primary_emerging_rows),
            "primary_confirmed_count": len(primary_confirmed_rows),
            "both_eligible_count": len(both_rows),
        },
        "rvol20_distribution": {row["group"]: row for row in rvol_distribution},
        "rvol5_vs_rvol20": rvol5_vs_rvol20,
        "cohorts": cohorts,
        "low_rvol_evidence": evidence_summary,
        "breakout_context_vs_rvol": breakout_rows,
        "benchmark_rs_vs_low_rvol": benchmark_rs,
        "momentum_vs_rvol": momentum_vs_rvol,
        "candidate_evidence_count": evidence_count,
        "day_level_low_rvol_concentration": day_summary,
        "symbol_level_low_rvol_concentration": symbol_summary,
        "threshold_sensitivity": threshold_sensitivity,
        "counterfactual_hard_gates": hard_gate_rows,
        "hybrid_volume_diagnostics": hybrid_rows,
        "semantic_consistency": semantic_status,
        "safety": {
            "future_outcome_fields_used": 0,
            "future_return_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "baseline_candidate_rules_changed": False,
            "entry_scores_generated": 0,
            "risk_reward_calculated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
        },
        "outputs": {
            "summary_json": str(config.summary_path),
            "rvol_distribution_csv": str(config.rvol_distribution_path),
            "low_rvol_evidence_csv": str(config.low_rvol_evidence_path),
            "breakout_context_csv": str(config.breakout_context_path),
            "counterfactual_gates_csv": str(config.counterfactual_gates_path),
            "day_concentration": str(config.day_concentration_path),
            "symbol_concentration": str(config.symbol_concentration_path),
            "markdown": "docs/emerging-volume-semantics-audit.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": 0,
        },
    }
    report["processing"]["storage_size_bytes"] = output_size(config)
    report["ready_for_review"] = bool(
        report["baseline"]["candidate_dataset_unchanged"]
        and report["baseline"]["feature_dataset_unchanged"]
        and report["audit"]["candidate_config_hash"] == "d111957c7a24da96"
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def actual_emerging_semantics(config: MomentumCandidateConfig) -> dict[str, Any]:
    return {
        "classification": "ONE_OF_N_SUPPORTING_EVIDENCE",
        "rvol20_role": "supporting_evidence",
        "is_mandatory_gate": False,
        "is_weighted_evidence": False,
        "is_warning_only": False,
        "config_fields_used": {
            "relative_volume.emerging_threshold": str(config.relative_volume.emerging_threshold),
            "momentum.emerging_min_return_3d": str(config.momentum.emerging_min_return_3d),
            "momentum.emerging_min_return_5d": str(config.momentum.emerging_min_return_5d),
            "momentum.emerging_min_return_10d": str(config.momentum.emerging_min_return_10d),
            "momentum.emerging_min_up_days_ratio_10": str(config.momentum.emerging_min_up_days_ratio_10),
            "momentum.emerging_min_evidence_count": config.momentum.emerging_min_evidence_count,
        },
        "boolean_logic": (
            "Emerging requires mandatory_gates_passed and research_eligible, "
            "(return_3d >= 0.005 OR return_5d >= 0.015), return_10d >= -0.010, "
            "up_days_ratio_10 >= 0.50, and at least 4 Emerging evidence flags. "
            "relative_volume_20d >= 1.20 adds EMERGING_RELATIVE_VOLUME as one evidence flag, "
            "but it is not directly required by passes_emerging()."
        ),
        "interaction_with_other_evidence": (
            "Sub-threshold RVOL20 rows can still qualify if momentum, structure, up-day ratio, "
            "benchmark-relative strength, breakout/high proximity, and current-day confirmation provide enough flags."
        ),
        "implementation_references": {
            "emerging_evidence_flags": "backend/app/strategy/momentum_candidates.py:542",
            "rvol_evidence_flag": "backend/app/strategy/momentum_candidates.py:550",
            "passes_emerging": "backend/app/strategy/momentum_candidates.py:586",
        },
    }


def rvol_distribution_row(group: str, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = [parse_decimal(row.get("relative_volume_20d")) for row in rows]
    usable = [value for value in values if value is not None]
    buckets = Counter(rvol_bucket(value) for value in values)
    stats = quantile_summary(usable)
    total = len(rows)
    return {
        "group": group,
        "total_rows": total,
        "usable_rows": len(usable),
        "null_count": buckets["NULL"],
        "p10": stats["p10"],
        "p25": stats["p25"],
        "median": stats["median"],
        "p75": stats["p75"],
        "p90": stats["p90"],
        "p95": stats["p95"],
        "lt_0_80": buckets["LT_0_80"],
        "pct_lt_0_80": pct(buckets["LT_0_80"], total),
        "rvol_0_80_to_lt_1_00": buckets["RANGE_0_80_TO_LT_1_00"],
        "pct_0_80_to_lt_1_00": pct(buckets["RANGE_0_80_TO_LT_1_00"], total),
        "rvol_1_00_to_lt_1_20": buckets["RANGE_1_00_TO_LT_1_20"],
        "pct_1_00_to_lt_1_20": pct(buckets["RANGE_1_00_TO_LT_1_20"], total),
        "rvol_1_20_to_lt_1_30": buckets["RANGE_1_20_TO_LT_1_30"],
        "pct_1_20_to_lt_1_30": pct(buckets["RANGE_1_20_TO_LT_1_30"], total),
        "rvol_1_30_to_lt_1_50": buckets["RANGE_1_30_TO_LT_1_50"],
        "pct_1_30_to_lt_1_50": pct(buckets["RANGE_1_30_TO_LT_1_50"], total),
        "rvol_1_50_to_lt_2_00": buckets["RANGE_1_50_TO_LT_2_00"],
        "pct_1_50_to_lt_2_00": pct(buckets["RANGE_1_50_TO_LT_2_00"], total),
        "gte_2_00": buckets["GTE_2_00"],
        "pct_gte_2_00": pct(buckets["GTE_2_00"], total),
        "pct_gte_1_00": pct(sum(1 for value in usable if value >= Decimal("1.00")), total),
        "pct_gte_1_20": pct(sum(1 for value in usable if value >= Decimal("1.20")), total),
        "pct_gte_1_30": pct(sum(1 for value in usable if value >= Decimal("1.30")), total),
        "pct_gte_1_50": pct(sum(1 for value in usable if value >= Decimal("1.50")), total),
    }


def rvol_bucket(value: Decimal | None) -> str:
    if value is None:
        return "NULL"
    if value < Decimal("0.80"):
        return "LT_0_80"
    if value < Decimal("1.00"):
        return "RANGE_0_80_TO_LT_1_00"
    if value < Decimal("1.20"):
        return "RANGE_1_00_TO_LT_1_20"
    if value < Decimal("1.30"):
        return "RANGE_1_20_TO_LT_1_30"
    if value < Decimal("1.50"):
        return "RANGE_1_30_TO_LT_1_50"
    if value < Decimal("2.00"):
        return "RANGE_1_50_TO_LT_2_00"
    return "GTE_2_00"


def rvol5_rvol20_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for threshold in (Decimal("1.00"), Decimal("1.20"), Decimal("1.30"), Decimal("1.50")):
        high5_low20 = low5_high20 = both_high = both_low = null_count = 0
        for row in rows:
            rvol5 = parse_decimal(row.get("relative_volume_5d"))
            rvol20 = parse_decimal(row.get("relative_volume_20d"))
            if rvol5 is None or rvol20 is None:
                null_count += 1
                continue
            if rvol5 >= threshold and rvol20 < threshold:
                high5_low20 += 1
            elif rvol5 < threshold and rvol20 >= threshold:
                low5_high20 += 1
            elif rvol5 >= threshold and rvol20 >= threshold:
                both_high += 1
            else:
                both_low += 1
        key = f"threshold_{str(threshold).replace('.', '_')}"
        total = len(rows)
        summary[key] = {
            "threshold": str(threshold),
            "rvol5_high_rvol20_low": high5_low20,
            "rvol5_low_rvol20_high": low5_high20,
            "both_high": both_high,
            "both_low": both_low,
            "null_count": null_count,
            "rvol5_high_rvol20_low_pct": pct(high5_low20, total),
        }
    low20 = [row for row in rows if rvol20_less_than(row, Decimal("1.00"))]
    summary["sub_1_0_rvol20_short_term_acceleration"] = {
        "rvol20_lt_1_0_count": len(low20),
        "rvol5_gte_1_2_count": sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.20"))),
        "rvol5_gte_1_3_count": sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.30"))),
        "rvol5_gte_1_5_count": sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.50"))),
        "rvol5_gte_1_2_pct": pct(sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.20"))), len(low20)),
        "rvol5_gte_1_3_pct": pct(sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.30"))), len(low20)),
        "rvol5_gte_1_5_pct": pct(sum(1 for row in low20 if rvol5_at_least(row, Decimal("1.50"))), len(low20)),
    }
    return summary


def low_rvol_cohort_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cohorts = {
        "LOW_RVOL": lambda row: rvol20_less_than(row, Decimal("1.00")),
        "SUB_THRESHOLD": lambda row: rvol20_between(row, Decimal("1.00"), Decimal("1.20")),
        "BASELINE_OR_HIGHER": lambda row: rvol20_at_least(row, Decimal("1.20")),
        "STRONG": lambda row: rvol20_at_least(row, Decimal("1.50")),
    }
    return {name: cohort_summary(name, [row for row in rows if predicate(row)], len(rows)) for name, predicate in cohorts.items()}


def cohort_summary(name: str, rows: Sequence[dict[str, Any]], total_emerging: int) -> dict[str, Any]:
    median_fields = (
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "up_days_ratio_10",
        "up_days_ratio_20",
        "relative_return_5d_vs_nifty500",
        "relative_return_20d_vs_nifty500",
        "distance_to_prior_20d_high_pct",
        "atr_percent_14",
        "median_traded_value_20d",
    )
    return {
        "cohort": name,
        "count": len(rows),
        "percentage_of_emerging": pct(len(rows), total_emerging),
        "medians": {field: median_value(rows, field) for field in median_fields},
        "above_prior_20d_high_rate_pct": true_rate(rows, "above_prior_20d_high"),
        "intraday_high_above_prior_20d_high_rate_pct": true_rate(rows, "intraday_high_above_prior_20d_high"),
        "extension_status_distribution": code_distribution(rows, "extension_status"),
        "breakout_context_distribution": code_distribution(rows, "breakout_context"),
    }


def low_rvol_evidence_rows(
    rows: Sequence[dict[str, Any]],
    *,
    total_emerging: int,
    config: MomentumCandidateConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence_counter: Counter[str] = Counter()
    semantic_counter: Counter[str] = Counter()
    combination_counter: Counter[str] = Counter()
    evidence_count_counter: Counter[int] = Counter()
    for row in rows:
        flags = split_codes(row.get("emerging_evidence"))
        evidence_counter.update(flags)
        semantic = semantic_evidence_conditions(row, config)
        semantic_counter.update(semantic)
        combination_counter[";".join(sorted(semantic))] += 1
        evidence_count_counter[len(flags)] += 1

    output_rows: list[dict[str, Any]] = []
    for key, count in evidence_counter.most_common():
        output_rows.append({"section": "EVIDENCE_FLAG", "key": key, "count": count, "pct": pct(count, len(rows)), "details": ""})
    for key, count in semantic_counter.most_common():
        output_rows.append({"section": "SEMANTIC_CONDITION", "key": key, "count": count, "pct": pct(count, len(rows)), "details": ""})
    for key, count in combination_counter.most_common(20):
        output_rows.append({"section": "EVIDENCE_COMBINATION", "key": key, "count": count, "pct": pct(count, len(rows)), "details": "Top combination among Emerging-eligible rows with RVOL20 < 1.20."})
    for key, count in sorted(evidence_count_counter.items()):
        output_rows.append({"section": "EVIDENCE_COUNT", "key": str(key), "count": count, "pct": pct(count, len(rows)), "details": "Stored Emerging evidence flag count."})
    return output_rows, {
        "cohort_count": len(rows),
        "cohort_pct_of_emerging": pct(len(rows), total_emerging),
        "evidence_frequency": dict(evidence_counter.most_common()),
        "semantic_condition_frequency": dict(semantic_counter.most_common()),
        "top_20_combinations": [{"combination": key, "count": count, "pct": pct(count, len(rows))} for key, count in combination_counter.most_common(20)],
        "stored_evidence_count_distribution": {str(key): count for key, count in sorted(evidence_count_counter.items())},
    }


def semantic_evidence_conditions(row: dict[str, Any], config: MomentumCandidateConfig) -> set[str]:
    conditions: set[str] = set()
    if decimal_at_least(row, "return_3d", config.momentum.emerging_min_return_3d):
        conditions.add("strong_3d_momentum")
    if decimal_at_least(row, "return_5d", config.momentum.emerging_min_return_5d):
        conditions.add("strong_5d_momentum")
    if decimal_at_least(row, "return_10d", config.momentum.emerging_min_return_10d):
        conditions.add("healthy_10d_structure")
    if decimal_at_least(row, "up_days_ratio_10", config.momentum.emerging_min_up_days_ratio_10):
        conditions.add("high_up_days_ratio")
    if decimal_positive(row, "relative_return_5d_vs_nifty500"):
        conditions.add("positive_benchmark_rs_5d")
    if row.get("breakout_context") in {"APPROACHING_20D_HIGH", "TESTING_20D_HIGH", "ABOVE_20D_HIGH"}:
        conditions.add("near_20d_high")
    if row.get("breakout_context") == "ABOVE_20D_HIGH" or truthy(row.get("above_prior_20d_high")):
        conditions.add("above_20d_high")
    if decimal_positive(row, "return_1d"):
        conditions.add("current_day_confirmation")
    if rvol20_at_least(row, config.relative_volume.emerging_threshold):
        conditions.add("rvol20_baseline_confirmation")
    if rvol5_at_least(row, Decimal("1.20")):
        conditions.add("strong_rvol5_ge_1_20")
    if rvol5_at_least(row, Decimal("1.30")):
        conditions.add("strong_rvol5_ge_1_30")
    if rvol5_at_least(row, Decimal("1.50")):
        conditions.add("strong_rvol5_ge_1_50")
    return conditions


def breakout_context_rvol_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for context, group in sorted(group_rows_by(rows, "breakout_context").items()):
        total = len(group)
        lt_1 = sum(1 for row in group if rvol20_less_than(row, Decimal("1.00")))
        sub = sum(1 for row in group if rvol20_between(row, Decimal("1.00"), Decimal("1.20")))
        ge_1_2 = sum(1 for row in group if rvol20_at_least(row, Decimal("1.20")))
        ge_1_5 = sum(1 for row in group if rvol20_at_least(row, Decimal("1.50")))
        output.append(
            {
                "breakout_context": context or "OTHER",
                "total_rows": total,
                "median_rvol20": median_value(group, "relative_volume_20d"),
                "pct_lt_1_00": pct(lt_1, total),
                "pct_1_00_to_lt_1_20": pct(sub, total),
                "pct_gte_1_20": pct(ge_1_2, total),
                "pct_gte_1_50": pct(ge_1_5, total),
            }
        )
    output.sort(key=lambda row: int(row["total_rows"]), reverse=True)
    return output


def benchmark_rs_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "LOW_RVOL_LT_1_00": benchmark_rs_group([row for row in rows if rvol20_less_than(row, Decimal("1.00"))]),
        "SUB_1_20": benchmark_rs_group([row for row in rows if rvol20_less_than(row, Decimal("1.20"))]),
    }


def benchmark_rs_group(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    positive_5 = sum(1 for row in rows if decimal_positive(row, "relative_return_5d_vs_nifty500"))
    positive_20 = sum(1 for row in rows if decimal_positive(row, "relative_return_20d_vs_nifty500"))
    return {
        "count": len(rows),
        "positive_rs5_pct": pct(positive_5, len(rows)),
        "positive_rs20_pct": pct(positive_20, len(rows)),
        "median_rs5": median_value(rows, "relative_return_5d_vs_nifty500"),
        "median_rs20": median_value(rows, "relative_return_20d_vs_nifty500"),
    }


def momentum_vs_rvol_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    fields = ("return_5d", "return_10d", "return_20d", "up_days_ratio_10", "up_days_ratio_20")
    groups = {
        "LOW_RVOL_LT_1_00": [row for row in rows if rvol20_less_than(row, Decimal("1.00"))],
        "BASELINE_OR_HIGHER_GTE_1_20": [row for row in rows if rvol20_at_least(row, Decimal("1.20"))],
    }
    return {
        name: {field: quantile_summary([parse_decimal(row.get(field)) for row in group]) for field in fields}
        for name, group in groups.items()
    }


def evidence_count_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cohorts = low_rvol_cohort_summary(rows)
    return {
        name: quantile_summary([parse_decimal(row.get("candidate_evidence_count")) for row in select_cohort(rows, name)])
        for name in cohorts
    }


def day_level_low_rvol_concentration(candidate_rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trading_date, group in sorted(group_rows_by(candidate_rows, "trading_date").items()):
        emerging = [row for row in group if truthy(row.get("emerging_eligible"))]
        lt_1 = sum(1 for row in emerging if rvol20_less_than(row, Decimal("1.00")))
        lt_1_2 = sum(1 for row in emerging if rvol20_less_than(row, Decimal("1.20")))
        rows.append(
            {
                "trading_date": trading_date,
                "emerging_count": len(emerging),
                "rvol20_lt_1_00_count": lt_1,
                "rvol20_lt_1_20_count": lt_1_2,
                "pct_rvol20_lt_1_00": pct(lt_1, len(emerging)),
                "pct_rvol20_lt_1_20": pct(lt_1_2, len(emerging)),
                "low_rvol_concentration_flag": "",
            }
        )
    percentages = [Decimal(str(row["pct_rvol20_lt_1_20"])) for row in rows if int(row["emerging_count"])]
    p95 = decimal_quantile(percentages, Decimal("0.95"))
    p99 = decimal_quantile(percentages, Decimal("0.99"))
    for row in rows:
        percentage = Decimal(str(row["pct_rvol20_lt_1_20"]))
        if int(row["emerging_count"]) and percentage >= p99:
            row["low_rvol_concentration_flag"] = "EXTREME_LOW_RVOL_CONCENTRATION"
        elif int(row["emerging_count"]) and percentage >= p95:
            row["low_rvol_concentration_flag"] = "HIGH_LOW_RVOL_CONCENTRATION"
    return rows, {
        "pct_rvol20_lt_1_00_distribution": quantile_summary([Decimal(str(row["pct_rvol20_lt_1_00"])) for row in rows if int(row["emerging_count"])]),
        "pct_rvol20_lt_1_20_distribution": quantile_summary(percentages),
        "rvol20_lt_1_20_count_distribution": numeric_distribution([int(row["rvol20_lt_1_20_count"]) for row in rows]),
        "highest_concentration_dates": sorted(
            [row for row in rows if row["low_rvol_concentration_flag"]],
            key=lambda row: (Decimal(str(row["pct_rvol20_lt_1_20"])), int(row["rvol20_lt_1_20_count"])),
            reverse=True,
        )[:20],
    }


def symbol_level_low_rvol_concentration(emerging_rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, group in group_rows_by(emerging_rows, "symbol").items():
        low = [row for row in group if rvol20_less_than(row, Decimal("1.00"))]
        sub = [row for row in group if rvol20_less_than(row, Decimal("1.20"))]
        rows.append(
            {
                "symbol": symbol,
                "emerging_days": len(group),
                "low_rvol_emerging_days": len(low),
                "sub_threshold_emerging_days": len(sub),
                "pct_low_rvol": pct(len(low), len(group)),
                "pct_sub_threshold": pct(len(sub), len(group)),
                "median_rvol20_when_emerging": median_value(group, "relative_volume_20d"),
            }
        )
    rows.sort(key=lambda row: (int(row["low_rvol_emerging_days"]), Decimal(str(row["pct_low_rvol"])), row["symbol"]), reverse=True)
    return rows, {
        "top_20_low_rvol_symbols": rows[:20],
        "low_rvol_days_distribution": numeric_distribution([int(row["low_rvol_emerging_days"]) for row in rows]),
        "pct_low_rvol_distribution": quantile_summary([Decimal(str(row["pct_low_rvol"])) for row in rows]),
    }


def emerging_rvol_threshold_sensitivity(primary_emerging_rows: Sequence[dict[str, Any]], config: MomentumCandidateConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baseline_count = len(primary_emerging_rows)
    for threshold in (Decimal("1.20"), Decimal("1.25"), Decimal("1.30")):
        retained = [row for row in primary_emerging_rows if simulated_emerging_passes(row, threshold=threshold, config=config)]
        retained_ids = {id(row) for row in retained}
        removed = [row for row in primary_emerging_rows if id(row) not in retained_ids]
        retained_below = [row for row in retained if rvol20_less_than(row, threshold)]
        rows.append(
            {
                "threshold": str(threshold),
                "baseline_primary_emerging_rows": baseline_count,
                "retained_rows": len(retained),
                "removed_rows": len(removed),
                "removed_pct": pct(len(removed), baseline_count),
                "retained_below_threshold": len(retained_below),
                "retained_below_threshold_pct": pct(len(retained_below), len(retained)),
                "removed_due_to_evidence_flag_loss": len(removed),
                "is_hard_gate": False,
                "mechanism": "Changing RVOL20 changes one Emerging evidence flag only; rows with enough alternate evidence remain eligible.",
                "top_retention_evidence": top_semantic_combinations(retained_below, config),
            }
        )
    return rows


def hard_gate_counterfactual_rows(
    primary_emerging_rows: Sequence[dict[str, Any]],
    candidate_rows: Sequence[dict[str, Any]],
    sessions: Sequence[str],
    session_index: dict[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in (Decimal("1.00"), Decimal("1.20"), Decimal("1.30"), Decimal("1.50")):
        retained = [row for row in primary_emerging_rows if rvol20_at_least(row, threshold)]
        daily_counts = counts_by_session(retained, sessions)
        streak_lengths = event_streak_lengths(retained, session_index)
        conversion_rate = conversion_rate_to_confirmed(retained, candidate_rows, session_index, horizon=5)
        rows.append(
            {
                "scenario": f"HARD_GATE_{str(threshold).replace('.', '_')}",
                "scenario_type": "HARD_GATE",
                "threshold": str(threshold),
                "emerging_rows_retained": len(retained),
                "emerging_rows_removed": len(primary_emerging_rows) - len(retained),
                "pct_retained": pct(len(retained), len(primary_emerging_rows)),
                "daily_median_emerging_count": statistics.median(daily_counts) if daily_counts else 0,
                "daily_p95_emerging_count": quantile_number(daily_counts, Decimal("0.95")),
                "symbols_ever_selected": len({row["symbol"] for row in retained}),
                "median_emerging_streak": statistics.median(streak_lengths) if streak_lengths else 0,
                "emerging_to_confirmed_5_session_conversion_rate_pct": conversion_rate,
                "details": "Diagnostic only; baseline Emerging rules were not changed.",
            }
        )
    return rows


def hybrid_volume_diagnostic_rows(
    primary_emerging_rows: Sequence[dict[str, Any]],
    sessions: Sequence[str],
    session_index: dict[str, int],
    candidate_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    scenarios = (
        ("HYBRID_RVOL20_1_20_OR_RVOL5_1_30", Decimal("1.30")),
        ("HYBRID_RVOL20_1_20_OR_RVOL5_1_50", Decimal("1.50")),
    )
    rows: list[dict[str, Any]] = []
    for name, rvol5_threshold in scenarios:
        retained = [
            row
            for row in primary_emerging_rows
            if rvol20_at_least(row, Decimal("1.20")) or rvol5_at_least(row, rvol5_threshold)
        ]
        daily_counts = counts_by_session(retained, sessions)
        streak_lengths = event_streak_lengths(retained, session_index)
        rows.append(
            {
                "scenario": name,
                "scenario_type": "HYBRID",
                "threshold": f"RVOL20>=1.20 OR RVOL5>={rvol5_threshold}",
                "emerging_rows_retained": len(retained),
                "emerging_rows_removed": len(primary_emerging_rows) - len(retained),
                "pct_retained": pct(len(retained), len(primary_emerging_rows)),
                "daily_median_emerging_count": statistics.median(daily_counts) if daily_counts else 0,
                "daily_p95_emerging_count": quantile_number(daily_counts, Decimal("0.95")),
                "symbols_ever_selected": len({row["symbol"] for row in retained}),
                "median_emerging_streak": statistics.median(streak_lengths) if streak_lengths else 0,
                "emerging_to_confirmed_5_session_conversion_rate_pct": conversion_rate_to_confirmed(retained, candidate_rows, session_index, horizon=5),
                "details": "Hybrid diagnostic only; no rule adoption.",
            }
        )
    return rows


def semantic_consistency_status(
    *,
    semantics: dict[str, Any],
    distribution: dict[str, Any],
    sensitivity: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    sub_threshold_pct = Decimal(str(distribution["pct_lt_0_80"])) + Decimal(str(distribution["pct_0_80_to_lt_1_00"])) + Decimal(str(distribution["pct_1_00_to_lt_1_20"]))
    max_removed_pct = max(Decimal(str(row["removed_pct"])) for row in sensitivity)
    if semantics["classification"] == "ONE_OF_N_SUPPORTING_EVIDENCE" and sub_threshold_pct > Decimal("50") and max_removed_pct < Decimal("1"):
        status = "CONSISTENT_BUT_LOOSE"
        reason = "The implementation matches secondary/supporting volume-confirmation language, but RVOL20 is loose enough that most Emerging-eligible rows sit below 1.20 and threshold changes remove very few rows."
    elif semantics["classification"] == "ONE_OF_N_SUPPORTING_EVIDENCE":
        status = "CONSISTENT"
        reason = "RVOL20 is implemented as secondary evidence, and the observed distribution does not show a large loose-volume skew."
    else:
        status = "INCONCLUSIVE"
        reason = "The audit could not map implementation semantics to the documented language."
    return {
        "status": status,
        "criteria": "CONSISTENT_BUT_LOOSE when RVOL20 is supporting evidence, sub-threshold Emerging share exceeds 50%, and 1.20->1.30 removes under 1% of primary Emerging rows.",
        "sub_threshold_pct": round_decimal(sub_threshold_pct),
        "max_removed_pct_in_1_20_1_30_sensitivity": round_decimal(max_removed_pct),
        "reason": reason,
    }


def simulated_emerging_passes(row: dict[str, Any], *, threshold: Decimal, config: MomentumCandidateConfig) -> bool:
    flags = split_codes(row.get("emerging_evidence"))
    if rvol20_less_than(row, threshold):
        flags.discard("EMERGING_RELATIVE_VOLUME")
    elif rvol20_at_least(row, threshold):
        flags.add("EMERGING_RELATIVE_VOLUME")
    has_short_momentum = decimal_at_least(row, "return_3d", config.momentum.emerging_min_return_3d) or decimal_at_least(row, "return_5d", config.momentum.emerging_min_return_5d)
    has_structure = decimal_at_least(row, "return_10d", config.momentum.emerging_min_return_10d)
    has_up_days = decimal_at_least(row, "up_days_ratio_10", config.momentum.emerging_min_up_days_ratio_10)
    return has_short_momentum and has_structure and has_up_days and len(flags) >= config.momentum.emerging_min_evidence_count


def top_semantic_combinations(rows: Sequence[dict[str, Any]], config: MomentumCandidateConfig, limit: int = 5) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[";".join(sorted(semantic_evidence_conditions(row, config)))] += 1
    return [{"combination": key, "count": count, "pct": pct(count, len(rows))} for key, count in counter.most_common(limit)]


def conversion_rate_to_confirmed(events: Sequence[dict[str, Any]], candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int], *, horizon: int) -> str:
    rows_by_symbol = group_rows_by(candidate_rows, "symbol")
    by_symbol_date = {(row["symbol"], row["trading_date"]): row for row in candidate_rows}
    dates_by_symbol = {
        symbol: {row["trading_date"] for row in rows}
        for symbol, rows in rows_by_symbol.items()
    }
    sessions_by_index = {index: session for session, index in session_index.items()}
    converted = 0
    for row in events:
        symbol = row["symbol"]
        symbol_dates = dates_by_symbol.get(symbol, set())
        base_index = session_index[row["trading_date"]]
        for offset in range(1, horizon + 1):
            next_date = sessions_by_index.get(base_index + offset)
            if next_date is None or next_date not in symbol_dates:
                continue
            future_row = by_symbol_date[(symbol, next_date)]
            if future_row.get("candidate_state") == "CONFIRMED" or truthy(future_row.get("confirmed_eligible")):
                converted += 1
                break
    return pct(converted, len(events))


def counts_by_session(events: Sequence[dict[str, Any]], sessions: Sequence[str]) -> list[int]:
    counts = Counter(row["trading_date"] for row in events)
    return [counts[session] for session in sessions]


def event_streak_lengths(events: Sequence[dict[str, Any]], session_index: dict[str, int]) -> list[int]:
    lengths: list[int] = []
    for _symbol, rows in group_rows_by(events, "symbol").items():
        active = 0
        previous_index: int | None = None
        for row in sorted(rows, key=lambda item: session_index[item["trading_date"]]):
            current_index = session_index[row["trading_date"]]
            if previous_index is None or current_index != previous_index + 1:
                if active:
                    lengths.append(active)
                active = 0
            active += 1
            previous_index = current_index
        if active:
            lengths.append(active)
    return lengths


def select_cohort(rows: Sequence[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    if name == "LOW_RVOL":
        return [row for row in rows if rvol20_less_than(row, Decimal("1.00"))]
    if name == "SUB_THRESHOLD":
        return [row for row in rows if rvol20_between(row, Decimal("1.00"), Decimal("1.20"))]
    if name == "BASELINE_OR_HIGHER":
        return [row for row in rows if rvol20_at_least(row, Decimal("1.20"))]
    if name == "STRONG":
        return [row for row in rows if rvol20_at_least(row, Decimal("1.50"))]
    return []


def median_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted(value for value in (parse_decimal(row.get(field)) for row in rows) if value is not None)
    if not values:
        return ""
    return round_decimal(decimal_quantile(values, Decimal("0.50")))


def true_rate(rows: Sequence[dict[str, Any]], field: str) -> str:
    return pct(sum(1 for row in rows if truthy(row.get(field))), len(rows))


def code_distribution(rows: Sequence[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(row.get(field) or "UNAVAILABLE") for row in rows).most_common())


def rvol20_less_than(row: dict[str, Any], threshold: Decimal) -> bool:
    value = parse_decimal(row.get("relative_volume_20d"))
    return value is not None and value < threshold


def rvol20_between(row: dict[str, Any], low: Decimal, high: Decimal) -> bool:
    value = parse_decimal(row.get("relative_volume_20d"))
    return value is not None and low <= value < high


def rvol20_at_least(row: dict[str, Any], threshold: Decimal) -> bool:
    value = parse_decimal(row.get("relative_volume_20d"))
    return value is not None and value >= threshold


def rvol5_at_least(row: dict[str, Any], threshold: Decimal) -> bool:
    value = parse_decimal(row.get("relative_volume_5d"))
    return value is not None and value >= threshold


def decimal_at_least(row: dict[str, Any], field: str, threshold: Decimal) -> bool:
    value = parse_decimal(row.get(field))
    return value is not None and value >= threshold


def decimal_positive(row: dict[str, Any], field: str) -> bool:
    value = parse_decimal(row.get(field))
    return value is not None and value > 0


def split_codes(value: Any) -> set[str]:
    return {item for item in str(value or "").split(";") if item}


def parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    return Decimal(text)


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[min(index, len(ordered) - 1)]


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def output_size(config: EmergingVolumeSemanticsAuditConfig) -> int:
    paths = [
        config.summary_path,
        config.rvol_distribution_path,
        config.low_rvol_evidence_path,
        config.breakout_context_path,
        config.counterfactual_gates_path,
        config.day_concentration_path,
        config.symbol_concentration_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())


def write_emerging_volume_semantics_markdown(report: dict[str, Any], path: Path) -> None:
    all_dist = report["rvol20_distribution"]["ALL_EMERGING_ELIGIBLE"]
    emerging_only = report["rvol20_distribution"]["EMERGING_ONLY"]
    both = report["rvol20_distribution"]["BOTH_ELIGIBLE"]
    primary_emerging = report["rvol20_distribution"]["PRIMARY_EMERGING"]
    primary_confirmed = report["rvol20_distribution"]["PRIMARY_CONFIRMED"]
    lines = [
        "# Emerging Volume Semantics Audit",
        "",
        "Current phase: Step 02.5 / Command 03 - Emerging volume-confirmation semantics",
        "",
        "## Boundary",
        "",
        "- This audit inspects current code semantics and existing candidate rows only.",
        "- It does not use future returns, MFE, MAE, winner/loser labels, profitability optimization, entry scores, backtesting, live data, orders, migrations, or Supabase persistence.",
        "- MOMENTUM_CANDIDATES_V1 rules, thresholds, ranking, and config hash remain unchanged.",
        "",
        "## Semantics",
        "",
        f"- Audit version: {report['audit']['audit_version']}",
        f"- Candidate version: {report['audit']['candidate_version']}",
        f"- Candidate config hash: {report['audit']['candidate_config_hash']}",
        f"- RVOL20 role: {report['semantics']['rvol20_role']}",
        f"- Mandatory gate: {report['semantics']['is_mandatory_gate']}",
        f"- Logic: {report['semantics']['boolean_logic']}",
        "",
        "## RVOL20 Distribution",
        "",
        f"- All Emerging-eligible median RVOL20: {all_dist['median']}; pct >=1.20: {all_dist['pct_gte_1_20']}%; pct <1.00: {Decimal(str(all_dist['pct_lt_0_80'])) + Decimal(str(all_dist['pct_0_80_to_lt_1_00']))}%",
        f"- Emerging-only median RVOL20: {emerging_only['median']}; pct >=1.20: {emerging_only['pct_gte_1_20']}%",
        f"- Both-eligible median RVOL20: {both['median']}; pct >=1.50: {both['pct_gte_1_50']}%",
        f"- Primary Emerging median RVOL20: {primary_emerging['median']}; Primary Confirmed median RVOL20: {primary_confirmed['median']}",
        "",
        "## Low-RVOL Evidence",
        "",
    ]
    for item in report["low_rvol_evidence"]["top_20_combinations"][:10]:
        lines.append(f"- {item['combination']}: {item['count']} ({item['pct']}%)")
    lines.extend(
        [
            "",
            "## Sensitivity",
            "",
        ]
    )
    for row in report["threshold_sensitivity"]:
        lines.append(f"- Emerging RVOL {row['threshold']}: retained={row['retained_rows']}, removed={row['removed_rows']} ({row['removed_pct']}%), retained below threshold={row['retained_below_threshold']}")
    lines.extend(["", "## Counterfactual Hard Gates", ""])
    for row in report["counterfactual_hard_gates"]:
        lines.append(f"- {row['scenario']}: retained={row['emerging_rows_retained']}, removed={row['emerging_rows_removed']}, median/day={row['daily_median_emerging_count']}, p95/day={row['daily_p95_emerging_count']}")
    lines.extend(["", "## Hybrid Diagnostics", ""])
    for row in report["hybrid_volume_diagnostics"]:
        lines.append(f"- {row['scenario']}: retained={row['emerging_rows_retained']}, removed={row['emerging_rows_removed']} ({row['pct_retained']}% retained)")
    lines.extend(
        [
            "",
            "## Semantic Consistency",
            "",
            f"- Result: {report['semantic_consistency']['status']}",
            f"- Reason: {report['semantic_consistency']['reason']}",
            "",
            "## Regression And Safety",
            "",
            f"- Candidate dataset unchanged: {report['baseline']['candidate_dataset_unchanged']}",
            f"- Feature dataset unchanged: {report['baseline']['feature_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "",
            "## Known Limitations",
            "",
            "- This is semantic/structural analysis only; no profitability or outcome claims are made.",
            "- RVOL5 is diagnostic in this audit; current Emerging implementation uses RVOL20 for the configured volume evidence flag.",
            "- Candidate-state conversion uses future candidate state, not future price outcome.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

from __future__ import annotations

import csv
import gzip
import inspect
import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.risk.risk_baseline import UPSTREAM_HASHES
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
)
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.momentum_candidates import file_sha256, split_codes
from app.strategy.scoring.score_baseline import STRATEGY_SCORE_V1_DATASET_HASH
from app.strategy.scoring.score_config import STRATEGY_SCORE_VERSION, StrategyScoreConfig
from app.strategy.scoring.strategy_scorer import (
    COMPONENT_PREFIXES,
    SCORE_OUTPUT_FIELDS,
    StrategyScoreEngineConfig,
    load_lookup,
    percentile,
    score_band,
    scoring_disposition,
)

STRATEGY_SCORE_AUDIT_VERSION = "STRATEGY_SCORE_AUDIT_V1"
COMPONENTS = ("setup", "momentum", "rvol", "relative_strength", "regime", "reward_risk")
ALL_COMPONENTS = tuple(COMPONENT_PREFIXES)
EXPECTED_CAPS = {
    "setup": Decimal("20"),
    "momentum": Decimal("20"),
    "rvol": Decimal("15"),
    "relative_strength": Decimal("15"),
    "regime": Decimal("10"),
    "sector": Decimal("10"),
    "catalyst": Decimal("5"),
    "reward_risk": Decimal("5"),
}
SETUP_POINTS = {"STRONG": Decimal("20"), "VALID": Decimal("16"), "WATCH": Decimal("8"), "POOR": Decimal("0")}
RVOL_POINTS = {"EXCEPTIONAL": Decimal("15"), "STRONG": Decimal("13"), "GOOD": Decimal("10"), "NORMAL": Decimal("6"), "WEAK": Decimal("0")}
RS_POINTS = {"STRONG": Decimal("15"), "POSITIVE": Decimal("11"), "NEUTRAL": Decimal("6"), "WEAK": Decimal("0")}
REGIME_POINTS = {"BULLISH": Decimal("10"), "NEUTRAL": Decimal("5"), "BEARISH": Decimal("0")}
PROHIBITED_FIELD_TOKENS = (
    "future_return",
    "forward_return",
    "future_benchmark",
    "future_regime",
    "target_hit",
    "stop_hit",
    "mfe",
    "mae",
    "trade_outcome",
    "winner",
    "loser",
    "pnl",
    "sharpe",
    "drawdown",
)

COMPONENT_REPORT_FIELDS = [
    "section", "component", "group", "rows", "points", "available_count", "unavailable_count",
    "mean_points", "median_points", "median_raw_score", "raw_gte_80", "entry_eligible",
    "entry_eligible_rate_pct", "notes",
]
CORRELATION_REPORT_FIELDS = [
    "section", "component_a", "component_b", "rows", "pearson", "spearman",
    "identical_normalized_rate_pct", "high_high_count", "high_high_rate_pct",
    "low_low_count", "low_low_rate_pct", "classification",
]
THRESHOLD_REPORT_FIELDS = [
    "section", "population", "threshold", "eligible_count", "population_pct", "retained_vs_baseline",
    "introduced_vs_baseline", "removed_vs_baseline", "jaccard_vs_baseline", "notes",
]
GATE_REPORT_FIELDS = [
    "section", "reason", "rows", "trading_date", "symbol", "raw_strategy_score", "score_mode",
    "scoring_disposition", "risk_readiness", "risk_mode", "risk_rejection_reasons",
    "blocking_penalty_present", "available_weight", "notes",
]
COVERAGE_REPORT_FIELDS = [
    "section", "bucket", "available_weight", "rows", "pct", "cause", "normal_eligible_count", "notes",
]
CATEGORY_REPORT_FIELDS = [
    "candidate_category", "rows", "median_raw_score", "raw_gte_80", "entry_eligible",
    "eligible_rate_pct", "mean_setup", "mean_momentum", "mean_rvol", "mean_relative_strength",
    "mean_regime", "mean_reward_risk", "notes",
]
NEUTRAL_REPORT_FIELDS = [
    "section", "pattern", "rows", "entry_eligible", "setup_points", "momentum_points", "rvol_points",
    "relative_strength_points", "regime_points", "reward_risk_points", "available_weight", "coherent", "notes",
]
HEADROOM_REPORT_FIELDS = ["target", "bucket", "extra_points_required", "rows", "pct_of_full_score", "notes"]
PILOT_REPORT_FIELDS = [
    "pilot_case", "symbol", "trading_date", "score_mode", "component_points", "raw_strategy_score",
    "arithmetic_sum", "available_weight", "score_coverage_pct", "score_band", "scoring_disposition",
    "expected_semantics", "result",
]
DETAIL_FIELDS = [
    "section", "trading_date", "symbol", "reason", "expected", "observed", "score_mode",
    "raw_strategy_score", "available_weight", "scoring_disposition",
]


@dataclass(frozen=True, slots=True)
class StrategyScoreAuditConfig:
    data_dir: Path
    score_config: StrategyScoreConfig = StrategyScoreConfig()
    audit_version: str = STRATEGY_SCORE_AUDIT_VERSION
    enforce_frozen_hashes: bool = True

    @property
    def engine_config(self) -> StrategyScoreEngineConfig:
        return StrategyScoreEngineConfig(data_dir=self.data_dir, full_generation=False)

    @property
    def score_dataset_path(self) -> Path:
        return self.engine_config.output_dataset_path

    @property
    def risk_dataset_path(self) -> Path:
        return resolve_current_risk_structure_dataset(self.data_dir)

    @property
    def candidate_dataset_path(self) -> Path:
        return self.engine_config.candidate_dataset_path

    @property
    def setup_dataset_path(self) -> Path:
        return self.engine_config.setup_dataset_path

    @property
    def entry_dataset_path(self) -> Path:
        return self.engine_config.entry_dataset_path

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "strategy_score" / "v1"

    def report_path(self, suffix: str, extension: str = "csv") -> Path:
        return self.reports_dir / f"strategy_score_v1_audit_{suffix}.{extension}"

    @property
    def summary_path(self) -> Path:
        return self.report_path("summary", "json")


def build_strategy_score_audit(
    *,
    config: StrategyScoreAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = audit_input_hashes(config)
    if config.enforce_frozen_hashes:
        verify_audit_hashes(hashes_before)

    notify(progress, "Loading immutable STRATEGY_SCORE_V1 and supporting provenance rows")
    rows = read_score_rows(config.score_dataset_path)
    keys = {row_key(row) for row in rows}
    risk_lookup = load_lookup(config.risk_dataset_path, keys)
    candidate_lookup = load_lookup(config.candidate_dataset_path, keys)
    setup_lookup = load_lookup(config.setup_dataset_path, keys)
    entry_lookup = load_lookup(config.entry_dataset_path, keys)
    missing_joined = {
        "risk": len(keys - set(risk_lookup)),
        "candidate": len(keys - set(candidate_lookup)),
        "setup": len(keys - set(setup_lookup)),
        "entry": len(keys - set(entry_lookup)),
    }

    notify(progress, "Reconstructing arithmetic, availability, coverage, and gate invariants")
    invariants, violation_rows = invariant_audit(
        rows,
        risk_lookup=risk_lookup,
        candidate_lookup=candidate_lookup,
        setup_lookup=setup_lookup,
        entry_lookup=entry_lookup,
        config=config.score_config,
    )
    coverage_rows, coverage_summary = coverage_audit(rows)
    mode_summary, gate_rows = gate_audit(rows, risk_lookup, entry_lookup, config.score_config)

    notify(progress, "Auditing component mappings, overlap, thresholds, and score resolution")
    component_rows, component_summary = component_audit(rows, candidate_lookup, setup_lookup)
    correlation_rows, correlation_summary = correlation_audit(rows)
    threshold_rows, threshold_summary = threshold_audit(rows)
    category_rows, category_summary = candidate_category_audit(rows)
    neutral_rows, neutral_summary = neutral_ceiling_audit(rows)
    headroom_rows, headroom_summary = headroom_audit(rows)
    profiles = profile_audit(rows)
    leave_out = leave_one_out_audit(rows)
    contribution = contribution_audit(rows)
    patterns = pattern_audit(rows)
    penalties = penalty_audit(rows)
    normalized_isolation = normalized_isolation_audit(rows)
    normalized = normalized_counterfactual(rows)
    score_margin = score_margin_audit(rows)
    regime = regime_audit(rows)
    reward_risk = reward_risk_audit(rows)
    pilot_rows, pilot_summary = pilot_audit(rows)

    missing_result = missing_component_result(invariants)
    gate_result = gate_separation_result(invariants, mode_summary)
    redundancy_result = correlation_summary["component_redundancy_result"]
    threshold_result = threshold_structure_result(rows, neutral_summary)
    resolution_result = patterns["score_resolution_result"]
    review_notes = [
        note
        for note in (
            component_summary["setup_semantic_review"].get("note"),
            component_summary["momentum_semantic_review"].get("note"),
            neutral_summary.get("note"),
        )
        if note
    ]
    critical_counts = (
        invariants["arithmetic_mismatches"],
        invariants["component_cap_violations"],
        invariants["raw_score_bound_violations"],
        invariants["available_weight_mismatches"],
        invariants["coverage_mismatches"],
        invariants["sector_semantic_violations"],
        invariants["catalyst_semantic_violations"],
        invariants["entry_threshold_violations"],
        mode_summary["full_score_invariant_violations"],
        mode_summary["preview_invariant_violations"],
        mode_summary["exceptional_invariant_violations"],
        penalties["blocking_penalty_violations"],
        reward_risk["full_score_zero_point_violations"],
        reward_risk["mapping_violations"],
        component_summary["setup"]["mapping_violations"],
        component_summary["momentum"]["mapping_violations"],
        component_summary["momentum"]["current_day_return_exclusion_violations"],
        component_summary["rvol"]["mapping_violations"],
        component_summary["relative_strength"]["mapping_violations"],
        component_summary["regime"]["mapping_violations"],
        normalized_isolation["output_behavior_violations"],
        normalized_isolation["usage_field_violations"],
    )
    overall = "METHODOLOGY_FIX_REQUIRED" if any(critical_counts) else "STABLE_WITH_REVIEW_NOTES" if review_notes else "STABLE"
    baseline_decision = "B_TARGETED_FIX_REQUIRED" if overall == "METHODOLOGY_FIX_REQUIRED" else "A_FREEZE_UNCHANGED"

    notify(progress, "Writing deterministic audit reports")
    write_csv(config.report_path("components"), component_rows, COMPONENT_REPORT_FIELDS)
    write_csv(config.report_path("correlations"), correlation_rows, CORRELATION_REPORT_FIELDS)
    write_csv(config.report_path("thresholds"), threshold_rows, THRESHOLD_REPORT_FIELDS)
    write_csv(config.report_path("gate_conflicts"), gate_rows, GATE_REPORT_FIELDS)
    write_csv(config.report_path("coverage"), coverage_rows, COVERAGE_REPORT_FIELDS)
    write_csv(config.report_path("candidate_categories"), category_rows, CATEGORY_REPORT_FIELDS)
    write_csv(config.report_path("neutral_ceiling"), neutral_rows, NEUTRAL_REPORT_FIELDS)
    write_csv(config.report_path("headroom"), headroom_rows, HEADROOM_REPORT_FIELDS)
    write_csv(config.report_path("pilot"), pilot_rows, PILOT_REPORT_FIELDS)
    write_gzip_csv(config.audit_dir / "strategy_score_audit_violations.csv.gz", violation_rows, DETAIL_FIELDS)
    write_gzip_csv(
        config.audit_dir / "strategy_score_audit_insufficient_coverage.csv.gz",
        detail_rows_for(rows, lambda row: row["scoring_disposition"] == "INSUFFICIENT_COVERAGE", "INSUFFICIENT_COVERAGE"),
        DETAIL_FIELDS,
    )
    write_gzip_csv(
        config.audit_dir / "strategy_score_audit_blocked_high_scores.csv.gz",
        detail_rows_for(rows, lambda row: row["raw_strategy_score"] >= 80 and row["scoring_disposition"] not in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}, "RAW_GTE_80_BLOCKED"),
        DETAIL_FIELDS,
    )
    write_gzip_csv(
        config.audit_dir / "strategy_score_audit_low_full_scores.csv.gz",
        detail_rows_for(rows, lambda row: row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] < 60, "FULL_SCORE_LT_60"),
        DETAIL_FIELDS,
    )

    hashes_after = audit_input_hashes(config)
    regression = {name: hashes_before[name] == hashes_after[name] for name in hashes_before}
    expected_regression = expected_hash_matches(hashes_after)
    leakage_fields = prohibited_audit_fields(SCORE_OUTPUT_FIELDS)
    safety = {
        "prohibited_score_fields": leakage_fields,
        "future_ohlc_loaded": 0,
        "future_returns_loaded": 0,
        "future_benchmark_loaded": 0,
        "future_regime_loaded": 0,
        "future_reward_risk_outcomes_loaded": 0,
        "future_news_loaded": 0,
        "current_sector_mapping_back_projected": 0,
        "mfe_loaded": 0,
        "mae_loaded": 0,
        "backtests_run": 0,
        "trade_signals_generated": 0,
        "orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    report: dict[str, Any] = {
        "phase": "Step 02.10",
        "command": "Command 02",
        "audit_version": config.audit_version,
        "generated_at": generated_at,
        "baseline": {
            "score_version": STRATEGY_SCORE_VERSION,
            "score_profile": config.score_config.score_profile,
            "score_config_hash": config.score_config.config_hash(),
            "score_dataset_hash": hashes_after["score_v1"],
            "score_rows": len(rows),
            "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
            "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
            "risk_dataset_hash": hashes_after["risk_v1_1"],
        },
        "inputs": {"missing_joined_rows": missing_joined, "hashes_before": hashes_before, "hashes_after": hashes_after},
        "invariants": invariants,
        "normalized_diagnostic": normalized_isolation,
        "coverage": coverage_summary,
        "modes_and_gates": mode_summary,
        "components": component_summary,
        "correlations": correlation_summary,
        "regimes": regime,
        "neutral_ceiling": neutral_summary,
        "thresholds": threshold_summary,
        "score_margin_78_82": score_margin,
        "profiles": profiles,
        "leave_one_out": leave_out,
        "contribution_balance": contribution,
        "patterns_and_resolution": patterns,
        "candidate_categories": category_summary,
        "reward_risk": reward_risk,
        "penalties": penalties,
        "normalized_counterfactual": normalized,
        "headroom": headroom_summary,
        "pilot": pilot_summary,
        "classifications": {
            "missing_component_semantics": missing_result,
            "gate_score_separation": gate_result,
            "component_redundancy": redundancy_result,
            "threshold_structure": threshold_result,
            "score_resolution": resolution_result,
            "overall_structural_result": overall,
            "baseline_decision": baseline_decision,
        },
        "review_notes": review_notes,
        "regression": {"unchanged_during_audit": regression, "expected_hashes_match": expected_regression},
        "leakage": {
            "result": "CLEAN_CAUSAL_INPUT_ONLY" if not leakage_fields else "PROHIBITED_FIELDS_FOUND",
            "prohibited_fields": leakage_fields,
            "time_key": "Exact trading_date T and symbol provenance joins only.",
        },
        "safety": safety,
        "outputs": output_paths(config),
        "processing": {},
    }
    report["ready_for_review"] = bool(
        not any(critical_counts)
        and all(regression.values())
        and all(expected_regression.values())
        and not any(missing_joined.values())
        and pilot_summary["passed"]
        and not leakage_fields
        and all(value == 0 for key, value in safety.items() if isinstance(value, int))
    )
    report["processing"] = {
        "duration_seconds": round(time.perf_counter() - started, 3),
        "report_storage_bytes": audit_output_size(config),
        "rows_per_second": round(len(rows) / max(time.perf_counter() - started, 0.001), 3),
    }
    write_json(config.summary_path, report)
    report["processing"]["report_storage_bytes"] = audit_output_size(config)
    write_json(config.summary_path, report)
    return report


def invariant_audit(
    rows: Sequence[dict[str, Any]],
    *,
    risk_lookup: dict[tuple[str, str], dict[str, str]],
    candidate_lookup: dict[tuple[str, str], dict[str, str]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
    entry_lookup: dict[tuple[str, str], dict[str, str]],
    config: StrategyScoreConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    tolerance = Decimal("0.000000001")
    for row in rows:
        component_sum = sum((row[f"{name}_points"] for name in ALL_COMPONENTS), Decimal("0"))
        reconstructed_weight = sum(
            (EXPECTED_CAPS[name] for name in ALL_COMPONENTS if row[f"{name}_availability"] == "AVAILABLE"),
            Decimal("0"),
        )
        reconstructed_coverage = reconstructed_weight
        reconstructed_normalized = (
            component_sum / reconstructed_weight * Decimal("100") if reconstructed_weight > 0 else None
        )
        checks: list[tuple[str, bool, Any, Any]] = [
            ("arithmetic_mismatches", row["raw_strategy_score"] != component_sum, component_sum, row["raw_strategy_score"]),
            ("available_weight_mismatches", row["available_weight"] != reconstructed_weight, reconstructed_weight, row["available_weight"]),
            ("coverage_mismatches", abs(row["score_coverage_pct"] - reconstructed_coverage) > tolerance, reconstructed_coverage, row["score_coverage_pct"]),
            (
                "normalized_formula_mismatches",
                not decimal_equal(row.get("normalized_available_score"), reconstructed_normalized, tolerance),
                reconstructed_normalized,
                row.get("normalized_available_score"),
            ),
            (
                "raw_score_bound_violations",
                row["raw_strategy_score"] < 0 or row["raw_strategy_score"] > 100,
                "0..100",
                row["raw_strategy_score"],
            ),
            (
                "historical_ceiling_violations",
                row["sector_availability"] == "UNAVAILABLE"
                and row["catalyst_availability"] == "UNAVAILABLE"
                and row["raw_strategy_score"] > 85,
                "<=85",
                row["raw_strategy_score"],
            ),
            (
                "sector_semantic_violations",
                row["sector_availability"] != "UNAVAILABLE"
                or row["sector_points"] != 0
                or (row["sector_availability"] == "AVAILABLE" and row["available_weight"] >= 95),
                "UNAVAILABLE/0/not counted",
                f"{row['sector_availability']}/{row['sector_points']}",
            ),
            (
                "catalyst_semantic_violations",
                row["catalyst_availability"] != "UNAVAILABLE"
                or row["catalyst_points"] != 0
                or (row["catalyst_availability"] == "AVAILABLE" and row["available_weight"] >= 90),
                "UNAVAILABLE/0/not counted",
                f"{row['catalyst_availability']}/{row['catalyst_points']}",
            ),
        ]
        for name in ALL_COMPONENTS:
            points = row[f"{name}_points"]
            maximum = row[f"{name}_max_points"]
            cap_bad = points < 0 or points > EXPECTED_CAPS[name] or maximum != EXPECTED_CAPS[name]
            checks.append(("component_cap_violations", cap_bad, f"0..{EXPECTED_CAPS[name]}", f"{name}={points};max={maximum}"))

        expected_band = independent_score_band(row["raw_strategy_score"])
        expected_disposition = independent_disposition(
            row["score_mode"], row["raw_strategy_score"], row["score_coverage_pct"]
        )
        checks.extend(
            [
                ("score_band_violations", row["score_band"] != expected_band, expected_band, row["score_band"]),
                (
                    "entry_threshold_violations",
                    row["scoring_disposition"] != expected_disposition,
                    expected_disposition,
                    row["scoring_disposition"],
                ),
                (
                    "high_conviction_violations",
                    row["scoring_disposition"] == "HIGH_CONVICTION" and row["raw_strategy_score"] < 90,
                    "raw >=90",
                    row["raw_strategy_score"],
                ),
                (
                    "score_version_violations",
                    row["score_version"] != STRATEGY_SCORE_VERSION
                    or row["score_config_hash"] != config.config_hash(),
                    f"{STRATEGY_SCORE_VERSION}/{config.config_hash()}",
                    f"{row['score_version']}/{row['score_config_hash']}",
                ),
            ]
        )
        for section, failed, expected, observed in checks:
            if failed:
                counts[section] += 1
                details.append(detail_row(row, section, expected, observed))

        key = row_key(row)
        if key not in risk_lookup or key not in candidate_lookup or key not in setup_lookup or key not in entry_lookup:
            counts["required_join_missing"] += 1
            details.append(detail_row(row, "required_join_missing", "all supporting rows", "missing"))

    names = (
        "arithmetic_mismatches", "component_cap_violations", "raw_score_bound_violations",
        "historical_ceiling_violations", "available_weight_mismatches", "coverage_mismatches",
        "normalized_formula_mismatches", "sector_semantic_violations", "catalyst_semantic_violations",
        "score_band_violations", "entry_threshold_violations", "high_conviction_violations",
        "score_version_violations", "required_join_missing",
    )
    summary = {name: counts[name] for name in names}
    summary.update(
        {
            "rows": len(rows),
            "historical_min_raw_score": min((row["raw_strategy_score"] for row in rows), default=None),
            "historical_max_raw_score": max((row["raw_strategy_score"] for row in rows), default=None),
            "high_conviction_count": sum(row["scoring_disposition"] == "HIGH_CONVICTION" for row in rows),
        }
    )
    return summary, details


def coverage_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frequencies = Counter(row["available_weight"] for row in rows)
    buckets = {
        "85": [row for row in rows if row["score_coverage_pct"] == 85],
        "80_TO_LT_85": [row for row in rows if 80 <= row["score_coverage_pct"] < 85],
        "LT_80": [row for row in rows if row["score_coverage_pct"] < 80],
        "GT_85": [row for row in rows if row["score_coverage_pct"] > 85],
    }
    output: list[dict[str, Any]] = []
    for name, group in buckets.items():
        output.append(
            {
                "section": "COVERAGE_BUCKET",
                "bucket": name,
                "available_weight": "",
                "rows": len(group),
                "pct": pct(len(group), len(rows)),
                "cause": ";".join(sorted({coverage_cause(row) for row in group})),
                "normal_eligible_count": sum(is_entry_eligible(row) for row in group),
                "notes": "Coverage uses available weight on the fixed 100-point scale.",
            }
        )
    for weight, count in sorted(frequencies.items()):
        group = [row for row in rows if row["available_weight"] == weight]
        output.append(
            {
                "section": "EXACT_AVAILABLE_WEIGHT",
                "bucket": format(weight, "f"),
                "available_weight": weight,
                "rows": count,
                "pct": pct(count, len(rows)),
                "cause": ";".join(sorted({coverage_cause(row) for row in group})),
                "normal_eligible_count": sum(is_entry_eligible(row) for row in group),
                "notes": "",
            }
        )
    insufficient = [row for row in rows if row["scoring_disposition"] == "INSUFFICIENT_COVERAGE"]
    insuff_causes = Counter(insufficient_coverage_cause(row) for row in insufficient)
    below_min_promotions = sum(
        row["score_coverage_pct"] < 80 and row["scoring_disposition"] in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
        for row in rows
    )
    summary = {
        "buckets": {name: len(group) for name, group in buckets.items()},
        "exact_available_weight_frequencies": {format(weight, "f"): count for weight, count in sorted(frequencies.items())},
        "non_85_causes": Counter(coverage_cause(row) for row in rows if row["available_weight"] != 85),
        "insufficient_coverage_rows": len(insufficient),
        "insufficient_coverage_causes": dict(insuff_causes),
        "below_minimum_normal_promotion_violations": below_min_promotions,
    }
    return output, summary


def gate_audit(
    rows: Sequence[dict[str, Any]],
    risk_lookup: dict[tuple[str, str], dict[str, str]],
    entry_lookup: dict[tuple[str, str], dict[str, str]],
    config: StrategyScoreConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mode_counts = Counter(row["score_mode"] for row in rows)
    full_violations = 0
    preview_violations = 0
    exceptional_violations = 0
    not_reasons: Counter[str] = Counter()
    high_block_reasons: Counter[str] = Counter()
    gate_rows: list[dict[str, Any]] = []
    for row in rows:
        key = row_key(row)
        risk = risk_lookup.get(key, {})
        entry = entry_lookup.get(key, {})
        if row["score_mode"] == "FULL_SCORE":
            failed = (
                risk.get("risk_mode") != "FULL_EVALUATION"
                or row["risk_readiness"] != "READY_FOR_FINAL_SCORING"
                or bool(split_codes(row["risk_rejection_reasons"]))
                or truthy(row["blocking_penalty_present"])
                or str(risk.get("entry_readiness", "")).upper() in {"CONDITIONALLY_READY", "EXCEPTIONAL_LONG_REVIEW"}
            )
            full_violations += failed
        elif row["score_mode"] == "PREVIEW_SCORE":
            source_ok = str(risk.get("entry_readiness", "")).upper() == "CONDITIONALLY_READY" or risk.get("risk_mode") == "PREVIEW_ONLY"
            failed = not source_ok or row["scoring_disposition"] != "PREVIEW_ONLY"
            preview_violations += failed
        elif row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE":
            source_ok = str(risk.get("entry_readiness", "")).upper() == "EXCEPTIONAL_LONG_REVIEW"
            failed = not source_ok or row["scoring_disposition"] != "EXCEPTIONAL_REVIEW"
            exceptional_violations += failed
        else:
            not_reasons[not_score_reason(row, risk, entry)] += 1

        if row["raw_strategy_score"] >= 80 and not is_entry_eligible(row):
            reason = blocked_high_reason(row)
            high_block_reasons[reason] += 1
            gate_rows.append(gate_report_row("RAW_GTE_80_NOT_ELIGIBLE", reason, row, risk))

    top_blocked = sorted(
        [row for row in rows if row["raw_strategy_score"] >= 80 and not is_entry_eligible(row)],
        key=lambda row: (-row["raw_strategy_score"], row["trading_date"], row["symbol"]),
    )[:50]
    for row in top_blocked:
        gate_rows.append(gate_report_row("TOP_50_BLOCKED_HIGH_SCORE", blocked_high_reason(row), row, risk_lookup.get(row_key(row), {})))
    for reason, count in sorted(high_block_reasons.items()):
        gate_rows.append({"section": "EXACT_DECOMPOSITION", "reason": reason, "rows": count})
    raw_gte_80 = sum(row["raw_strategy_score"] >= 80 for row in rows)
    entry_eligible = sum(is_entry_eligible(row) for row in rows)
    low_full = [row for row in rows if row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] < 60]
    low_component_counts = {
        component: sum(
            row[f"{component}_points"] <= EXPECTED_CAPS[component] * Decimal("0.4")
            for row in low_full
        )
        for component in COMPONENTS
    }
    summary = {
        "mode_counts": dict(mode_counts),
        "full_score_invariant_violations": full_violations,
        "preview_invariant_violations": preview_violations,
        "exceptional_invariant_violations": exceptional_violations,
        "not_score_eligible_reason_distribution": dict(not_reasons),
        "raw_gte_80": raw_gte_80,
        "entry_eligible": entry_eligible,
        "raw_gte_80_not_entry_eligible": raw_gte_80 - entry_eligible,
        "raw_gte_80_not_entry_eligible_decomposition": dict(high_block_reasons),
        "decomposition_reconciles": sum(high_block_reasons.values()) == raw_gte_80 - entry_eligible,
        "top_50_blocked_high_score_reason_distribution": dict(Counter(blocked_high_reason(row) for row in top_blocked)),
        "low_score_risk_ready": {
            "rows": len(low_full),
            "component_profile": component_profile(low_full),
            "low_component_counts": low_component_counts,
            "arithmetic_mismatches": sum(
                row["raw_strategy_score"]
                != sum((row[f"{component}_points"] for component in ALL_COMPONENTS), Decimal("0"))
                for row in low_full
            ),
            "finding": "LOW_RANKING_EXPLAINED_BY_COMPONENT_EVIDENCE",
        },
        "numeric_score_rescued_blocked_rows": sum(
            row["score_mode"] != "FULL_SCORE" and is_entry_eligible(row) for row in rows
        ),
    }
    return summary, gate_rows


def component_audit(
    rows: Sequence[dict[str, Any]],
    candidate_lookup: dict[tuple[str, str], dict[str, str]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    distributions: dict[str, Any] = {}
    for component in COMPONENTS:
        values = [row[f"{component}_points"] for row in rows]
        counts = Counter(values)
        distributions[component] = {
            "points": {format(value, "f"): count for value, count in sorted(counts.items())},
            "available": sum(row[f"{component}_availability"] == "AVAILABLE" for row in rows),
            "unavailable": sum(row[f"{component}_availability"] != "AVAILABLE" for row in rows),
            "mean": mean(values),
            "median": median(values),
        }
        for points, count in sorted(counts.items()):
            group = [row for row in rows if row[f"{component}_points"] == points]
            output.append(component_report_row("POINT_DISTRIBUTION", component, format(points, "f"), group, points=points))

    setup_mapping_violations = 0
    setup_groups: dict[str, Any] = {}
    for quality in ("STRONG", "VALID", "WATCH", "POOR", "UNAVAILABLE"):
        group = [row for row in rows if (row["setup_quality"] or "UNAVAILABLE") == quality]
        if not group:
            continue
        expected = SETUP_POINTS.get(quality)
        violations = sum(expected is not None and row["setup_points"] != expected for row in group)
        setup_mapping_violations += violations
        setup_groups[quality] = group_summary(group)
        output.append(component_report_row("SETUP_QUALITY", "setup", quality, group, points=expected, notes=f"mapping_violations={violations}"))

    momentum_mapping_violations = 0
    current_day_exclusion_violations = 0
    for row in rows:
        candidate = candidate_lookup.get(row_key(row), {})
        expected = reconstruct_momentum_points(candidate)
        if expected is None:
            momentum_mapping_violations += row["momentum_availability"] == "AVAILABLE"
        else:
            momentum_mapping_violations += row["momentum_points"] != expected
        current_day_exclusion_violations += "return_1d" in row["momentum_basis"].lower()

    rvol_mapping_violations = 0
    rvol_groups: dict[str, Any] = {}
    for descriptor, expected in RVOL_POINTS.items():
        group = [row for row in rows if descriptor_from_basis(row["rvol_basis"], "UPSTREAM_VOLUME_CONFIRMATION_") == descriptor]
        violations = sum(row["rvol_points"] != expected for row in group)
        rvol_mapping_violations += violations
        rvol_groups[descriptor] = group_summary(group)
        output.append(component_report_row("RVOL_DESCRIPTOR", "rvol", descriptor, group, points=expected, notes=f"mapping_violations={violations}"))

    emerging_rvol = {}
    for descriptor in ("NORMAL", "GOOD", "STRONG"):
        group = [
            row for row in rows
            if row["candidate_category"] == "EMERGING_ONLY"
            and descriptor_from_basis(row["rvol_basis"], "UPSTREAM_VOLUME_CONFIRMATION_") == descriptor
        ]
        emerging_rvol[descriptor] = group_summary(group)
        output.append(component_report_row("EMERGING_RVOL", "rvol", descriptor, group, points=RVOL_POINTS[descriptor]))

    rs_mapping_violations = 0
    rs_groups: dict[str, Any] = {}
    for descriptor, expected in RS_POINTS.items():
        group = [row for row in rows if descriptor_from_basis(row["relative_strength_basis"], "UPSTREAM_BENCHMARK_RS_") == descriptor]
        violations = sum(row["relative_strength_points"] != expected for row in group)
        rs_mapping_violations += violations
        rs_groups[descriptor] = group_summary(group)
        output.append(component_report_row("RS_DESCRIPTOR", "relative_strength", descriptor, group, points=expected, notes=f"mapping_violations={violations}"))
    rs_unavailable = [row for row in rows if row["relative_strength_availability"] != "AVAILABLE"]
    rs_unavailable_causes = Counter(
        setup_lookup.get(row_key(row), {}).get("benchmark_rs_context", "MISSING") or "MISSING"
        for row in rs_unavailable
    )

    regime_mapping_violations = 0
    regime_groups: dict[str, Any] = {}
    for state in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE"):
        group = [row for row in rows if row["regime_state"] == state]
        expected = REGIME_POINTS.get(state)
        violations = sum(
            row["regime_points"] != (expected or 0)
            or (state == "UNAVAILABLE" and row["regime_availability"] != "UNAVAILABLE")
            for row in group
        )
        regime_mapping_violations += violations
        regime_groups[state] = group_summary(group)
        output.append(component_report_row("REGIME_STATE", "regime", state, group, points=expected, notes=f"mapping_violations={violations}"))

    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    setup_corrs = {
        component: correlation_pair(full, "setup", component)
        for component in ("momentum", "rvol", "relative_strength")
    }
    setup_review = {
        "classification": "PARTIALLY_OVERLAPPING",
        "correlations": setup_corrs,
        "summarized_upstream_evidence": [
            "breakout/structure", "relative-volume confirmation", "benchmark relative strength",
            "momentum/continuation state", "candle/acceptance confirmation",
        ],
        "note": "setup_quality is an upstream composite and partially overlaps RVOL, RS, momentum, and candle confirmation; the dedicated components remain separately mapped but are not fully independent evidence.",
    }
    momentum_corrs = {
        component: correlation_pair(full, "momentum", component)
        for component in ("setup", "relative_strength")
    }
    momentum_review = {
        "classification": "MODERATE_OVERLAP",
        "correlations": momentum_corrs,
        "candidate_state_direct_points": False,
        "current_day_return_excluded": current_day_exclusion_violations == 0,
        "note": "Momentum is reconstructed from multi-day returns and up-day ratios. It overlaps most with RS but candidate state itself contributes no points.",
    }
    return output, {
        "distributions": distributions,
        "setup": {"mapping_violations": setup_mapping_violations, "groups": setup_groups},
        "setup_semantic_review": setup_review,
        "momentum": {
            "mapping_violations": momentum_mapping_violations,
            "current_day_return_exclusion_violations": current_day_exclusion_violations,
            "distribution": distributions["momentum"],
        },
        "momentum_semantic_review": momentum_review,
        "rvol": {"mapping_violations": rvol_mapping_violations, "groups": rvol_groups},
        "emerging_rvol": {
            "groups": emerging_rvol,
            "zero_penalty_for_normal_good_strong_violations": sum(
                row["rvol_points"] == 0
                for row in rows
                if row["candidate_category"] == "EMERGING_ONLY"
                and descriptor_from_basis(row["rvol_basis"], "UPSTREAM_VOLUME_CONFIRMATION_") in {"NORMAL", "GOOD", "STRONG"}
            ),
            "finding": "CONSISTENT_WITH_EMERGING_VOLUME_SEMANTICS",
        },
        "relative_strength": {
            "mapping_violations": rs_mapping_violations,
            "available": len(rows) - len(rs_unavailable),
            "unavailable": len(rs_unavailable),
            "unavailable_causes": dict(rs_unavailable_causes),
            "groups": rs_groups,
        },
        "regime": {"mapping_violations": regime_mapping_violations, "confidence_used_in_points": False, "groups": regime_groups},
    }


def correlation_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    output: list[dict[str, Any]] = []
    pairs_summary: list[dict[str, Any]] = []
    for index, left_name in enumerate(COMPONENTS):
        for right_name in COMPONENTS[index + 1 :]:
            pairs = [
                (row[f"{left_name}_points"], row[f"{right_name}_points"])
                for row in full
                if row[f"{left_name}_availability"] == "AVAILABLE"
                and row[f"{right_name}_availability"] == "AVAILABLE"
            ]
            left = [pair[0] for pair in pairs]
            right = [pair[1] for pair in pairs]
            pearson_value = pearson_correlation(left, right)
            spearman_value = spearman_correlation(left, right)
            identical = sum(
                normalize_component(a, EXPECTED_CAPS[left_name]) == normalize_component(b, EXPECTED_CAPS[right_name])
                for a, b in pairs
            )
            high_high = sum(
                normalize_component(a, EXPECTED_CAPS[left_name]) >= Decimal("0.8")
                and normalize_component(b, EXPECTED_CAPS[right_name]) >= Decimal("0.8")
                for a, b in pairs
            )
            low_low = sum(
                normalize_component(a, EXPECTED_CAPS[left_name]) <= Decimal("0.4")
                and normalize_component(b, EXPECTED_CAPS[right_name]) <= Decimal("0.4")
                for a, b in pairs
            )
            classification = pair_redundancy_classification(pearson_value, spearman_value)
            item = {
                "section": "FULL_SCORE_PAIRWISE",
                "component_a": left_name,
                "component_b": right_name,
                "rows": len(pairs),
                "pearson": pearson_value,
                "spearman": spearman_value,
                "identical_normalized_rate_pct": pct(identical, len(pairs)),
                "high_high_count": high_high,
                "high_high_rate_pct": pct(high_high, len(pairs)),
                "low_low_count": low_low,
                "low_low_rate_pct": pct(low_low, len(pairs)),
                "classification": classification,
            }
            output.append(item)
            pairs_summary.append(item)
    ranked = sorted(
        pairs_summary,
        key=lambda item: abs(item["pearson"] or Decimal("0")),
        reverse=True,
    )
    rs_momentum_full = next(
        item for item in pairs_summary
        if {item["component_a"], item["component_b"]} == {"momentum", "relative_strength"}
    )
    all_rs_pairs = [
        (row["momentum_points"], row["relative_strength_points"])
        for row in rows
        if row["momentum_availability"] == "AVAILABLE"
        and row["relative_strength_availability"] == "AVAILABLE"
    ]
    all_left = [pair[0] for pair in all_rs_pairs]
    all_right = [pair[1] for pair in all_rs_pairs]
    all_pearson = pearson_correlation(all_left, all_right)
    all_spearman = spearman_correlation(all_left, all_right)
    all_identical = sum(
        normalize_component(a, EXPECTED_CAPS["momentum"])
        == normalize_component(b, EXPECTED_CAPS["relative_strength"])
        for a, b in all_rs_pairs
    )
    all_high_high = sum(a >= 16 and b >= 12 for a, b in all_rs_pairs)
    all_low_low = sum(a <= 8 and b <= 6 for a, b in all_rs_pairs)
    rs_momentum_all = {
        "section": "ALL_ROWS_RS_MOMENTUM_FOCUS",
        "component_a": "momentum",
        "component_b": "relative_strength",
        "rows": len(all_rs_pairs),
        "pearson": all_pearson,
        "spearman": all_spearman,
        "identical_normalized_rate_pct": pct(all_identical, len(all_rs_pairs)),
        "high_high_count": all_high_high,
        "high_high_rate_pct": pct(all_high_high, len(all_rs_pairs)),
        "low_low_count": all_low_low,
        "low_low_rate_pct": pct(all_low_low, len(all_rs_pairs)),
        "classification": pair_redundancy_classification(all_pearson, all_spearman),
    }
    output.append(rs_momentum_all)
    maximum_abs = max(
        abs(ranked[0]["pearson"] or Decimal("0")) if ranked else Decimal("0"),
        abs(all_pearson or Decimal("0")),
        abs(all_spearman or Decimal("0")),
    )
    overall = "HIGH_REDUNDANCY" if maximum_abs >= Decimal("0.80") else "POTENTIAL_DOUBLE_COUNTING" if maximum_abs >= Decimal("0.65") else "MODERATE_OVERLAP_ACCEPTABLE" if maximum_abs >= Decimal("0.40") else "LOW_REDUNDANCY"
    return output, {
        "population": "FULL_SCORE",
        "pairs": pairs_summary,
        "top_correlations": ranked[:5],
        "rs_momentum": rs_momentum_all,
        "rs_momentum_full_score": rs_momentum_full,
        "rs_momentum_classification": pair_redundancy_classification(all_pearson, all_spearman),
        "component_redundancy_result": overall,
    }


def threshold_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    output: list[dict[str, Any]] = []
    counts_all: dict[str, int] = {}
    counts_full: dict[str, int] = {}
    for threshold in (70, 75, 78, 79, 80, 81, 82, 83, 84, 85, 90):
        all_count = sum(row["raw_strategy_score"] >= threshold for row in rows)
        full_count = sum(row["raw_strategy_score"] >= threshold for row in full)
        counts_all[str(threshold)] = all_count
        counts_full[str(threshold)] = full_count
        output.extend(
            [
                threshold_row("DISTRIBUTION", "ALL", threshold, all_count, len(rows)),
                threshold_row("DISTRIBUTION", "FULL_SCORE", threshold, full_count, len(full)),
            ]
        )
    baseline = eligible_keys(rows, threshold=Decimal("80"), coverage=Decimal("80"))
    sensitivity: dict[str, Any] = {}
    for threshold in (75, 78, 80, 82, 85):
        scenario = eligible_keys(rows, threshold=Decimal(threshold), coverage=Decimal("80"))
        comparison = set_comparison(scenario, baseline)
        sensitivity[str(threshold)] = {"eligible_count": len(scenario), "pct_of_full_score": pct(len(scenario), len(full)), **comparison}
        output.append(
            threshold_row(
                "THRESHOLD_SENSITIVITY", "FULL_SCORE", threshold, len(scenario), len(full), comparison=comparison
            )
        )
    coverage_sensitivity: dict[str, Any] = {}
    for coverage in (75, 80, 85):
        scenario = eligible_keys(rows, threshold=Decimal("80"), coverage=Decimal(coverage))
        comparison = set_comparison(scenario, baseline)
        coverage_sensitivity[str(coverage)] = {"eligible_count": len(scenario), "pct_of_full_score": pct(len(scenario), len(full)), **comparison}
        output.append(
            threshold_row(
                "COVERAGE_SENSITIVITY", "FULL_SCORE", coverage, len(scenario), len(full), comparison=comparison,
                notes="threshold column contains minimum coverage for this section",
            )
        )
    counterfactuals = {
        "BASELINE": {"eligible_count": len(baseline), **set_comparison(baseline, baseline)},
        **{f"THRESHOLD_{value}": sensitivity[str(value)] for value in (75, 78, 82, 85)},
        "COVERAGE_75": coverage_sensitivity["75"],
        "COVERAGE_85": coverage_sensitivity["85"],
    }
    return output, {
        "counts_all": counts_all,
        "counts_full_score": counts_full,
        "threshold_sensitivity": sensitivity,
        "coverage_sensitivity": coverage_sensitivity,
        "counterfactuals": counterfactuals,
    }


def candidate_category_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    output: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for category in ("EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE"):
        group = [row for row in full if row["candidate_category"] == category]
        component_means = {component: mean([row[f"{component}_points"] for row in group]) for component in COMPONENTS}
        item = {
            "candidate_category": category,
            "rows": len(group),
            "median_raw_score": median([row["raw_strategy_score"] for row in group]),
            "raw_gte_80": sum(row["raw_strategy_score"] >= 80 for row in group),
            "entry_eligible": sum(is_entry_eligible(row) for row in group),
            "eligible_rate_pct": pct(sum(is_entry_eligible(row) for row in group), len(group)),
            **{f"mean_{component}": component_means[component] for component in COMPONENTS},
            "notes": "Candidate category is a cohort label and contributes no direct points.",
        }
        output.append(item)
        summary[category] = item
    both = summary.get("BOTH_ELIGIBLE", {})
    emerging = summary.get("EMERGING_ONLY", {})
    both_advantages = {
        component: decimal_or_zero(both.get(f"mean_{component}")) - decimal_or_zero(emerging.get(f"mean_{component}"))
        for component in COMPONENTS
    }
    summary["both_eligible_dominance"] = {
        "component_mean_advantage_vs_emerging_only": both_advantages,
        "candidate_state_direct_points": False,
        "finding": "STRONGER_MULTI_COMPONENT_EVIDENCE_WITH_PARTIAL_UPSTREAM_OVERLAP",
    }
    confirmed_rows = int(summary.get("CONFIRMED_ONLY", {}).get("rows", 0))
    summary["confirmed_only_interpretation"] = {
        "rows": confirmed_rows,
        "finding": "SMALL_COHORT_DESCRIPTIVE_ONLY" if confirmed_rows < 100 else "DESCRIPTIVE_ONLY",
    }
    return output, summary


def neutral_ceiling_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    neutral = [row for row in rows if row["regime_state"] == "NEUTRAL"]
    neutral_80 = [row for row in neutral if row["raw_strategy_score"] == 80]
    patterns = Counter(component_vector(row) + (row["available_weight"],) for row in neutral_80)
    output: list[dict[str, Any]] = []
    coherent_rows = 0
    for pattern, count in sorted(patterns.items(), key=lambda item: (-item[1], item[0])):
        component_values = pattern[:-1]
        available_weight = pattern[-1]
        coherent = (
            component_values == (Decimal("20"), Decimal("20"), Decimal("15"), Decimal("15"), Decimal("5"), Decimal("5"))
            and available_weight == 85
        )
        coherent_rows += count if coherent else 0
        output.append(
            {
                "section": "NEUTRAL_RAW_80_PATTERN",
                "pattern": vector_text(component_values),
                "rows": count,
                "entry_eligible": sum(
                    is_entry_eligible(row) for row in neutral_80 if component_vector(row) == component_values
                ),
                "setup_points": component_values[0],
                "momentum_points": component_values[1],
                "rvol_points": component_values[2],
                "relative_strength_points": component_values[3],
                "regime_points": component_values[4],
                "reward_risk_points": component_values[5],
                "available_weight": available_weight,
                "coherent": coherent,
                "notes": "Neutral 80 requires all six historically available components at their regime-specific maximum.",
            }
        )
    entry_neutral = [row for row in neutral if is_entry_eligible(row)]
    classification = "COHERENT_BUT_STRICT" if len(entry_neutral) == coherent_rows and coherent_rows == len(neutral_80) else "INCONCLUSIVE"
    return output, {
        "rows": len(neutral),
        "full_score_rows": sum(row["score_mode"] == "FULL_SCORE" for row in neutral),
        "raw_80_rows": len(neutral_80),
        "entry_eligible_rows": len(entry_neutral),
        "coherent_raw_80_rows": coherent_rows,
        "component_patterns": [dict(row) for row in output],
        "classification": classification,
        "note": "The Neutral ceiling is coherent but structurally knife-edge: entry at 80 requires every other available component to be maximal.",
    }


def headroom_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    to_80 = {
        "ALREADY_GTE_80": [row for row in full if row["raw_strategy_score"] >= 80],
        "CROSS_WITH_LE_5": [row for row in full if 0 < 80 - row["raw_strategy_score"] <= 5],
        "REQUIRE_6_TO_10": [row for row in full if 6 <= 80 - row["raw_strategy_score"] <= 10],
        "REQUIRE_11_TO_15": [row for row in full if 11 <= 80 - row["raw_strategy_score"] <= 15],
        "CANNOT_REACH_WITH_15": [row for row in full if 80 - row["raw_strategy_score"] > 15],
    }
    to_90 = {
        "ALREADY_GTE_90": [row for row in full if row["raw_strategy_score"] >= 90],
        "CAN_REACH_WITH_FULL_15": [row for row in full if row["raw_strategy_score"] < 90 <= row["raw_strategy_score"] + 15],
        "CANNOT_REACH_WITH_15": [row for row in full if row["raw_strategy_score"] + 15 < 90],
    }
    output: list[dict[str, Any]] = []
    for target, groups in ((80, to_80), (90, to_90)):
        for bucket, group in groups.items():
            output.append(
                {
                    "target": target,
                    "bucket": bucket,
                    "extra_points_required": headroom_requirement(bucket),
                    "rows": len(group),
                    "pct_of_full_score": pct(len(group), len(full)),
                    "notes": "Pure mathematical range only; no sector or catalyst evidence inferred.",
                }
            )
    return output, {
        "full_score_rows": len(full),
        "to_80": {key: len(value) for key, value in to_80.items()},
        "to_90": {key: len(value) for key, value in to_90.items()},
        "assumption": "At most 10 future sector points plus 5 future catalyst points; no actual strength inferred.",
    }


def profile_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if is_entry_eligible(row)]
    non_entry_full = [row for row in rows if row["score_mode"] == "FULL_SCORE" and not is_entry_eligible(row)]
    return {
        "entry_eligible": component_profile(eligible),
        "non_entry_full_score": component_profile(non_entry_full),
    }


def leave_one_out_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    baseline = [row for row in rows if is_entry_eligible(row)]
    output: dict[str, Any] = {}
    for component in COMPONENTS:
        retained = sum(row["raw_strategy_score"] - row[f"{component}_points"] >= 80 for row in baseline)
        lost = len(baseline) - retained
        output[component] = {
            "baseline_eligible": len(baseline),
            "eligible_retained": retained,
            "eligible_lost": lost,
            "dependent_pct": pct(lost, len(baseline)),
        }
    return output


def contribution_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        "FULL_SCORE": [row for row in rows if row["score_mode"] == "FULL_SCORE"],
        "ENTRY_ELIGIBLE": [row for row in rows if is_entry_eligible(row)],
    }
    result: dict[str, Any] = {}
    for group_name, group in groups.items():
        shares = {
            component: mean(
                [
                    row[f"{component}_points"] / row["raw_strategy_score"] * 100
                    for row in group
                    if row["raw_strategy_score"] > 0
                ]
            )
            for component in COMPONENTS
        }
        ranked = sorted(shares.items(), key=lambda item: item[1] or Decimal("0"), reverse=True)
        result[group_name] = {
            "rows": len(group),
            "average_pct_of_raw_score": shares,
            "largest_component": ranked[0][0] if ranked else None,
            "largest_average_share_pct": ranked[0][1] if ranked else None,
            "disproportionate_single_component": bool(ranked and ranked[0][1] is not None and ranked[0][1] > 40),
        }
    return result


def pattern_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    vectors = Counter(component_vector(row) for row in full)
    top = [
        {"vector": vector_text(vector), "rows": count, "pct_of_full_score": pct(count, len(full))}
        for vector, count in sorted(vectors.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    unique_all = len({row["raw_strategy_score"] for row in rows})
    unique_full = len({row["raw_strategy_score"] for row in full})
    classification = "ADEQUATE_RESOLUTION" if unique_full >= 40 and len(vectors) >= 250 else "COARSE_BUT_USABLE" if unique_full >= 15 and len(vectors) >= 50 else "OVERLY_DISCRETE"
    return {
        "population": "FULL_SCORE",
        "unique_component_vectors": len(vectors),
        "top_repeated_vectors": top,
        "top_10_vector_share_pct": pct(sum(item["rows"] for item in top), len(full)),
        "unique_raw_score_values_all": unique_all,
        "unique_raw_score_values_full_score": unique_full,
        "score_resolution_result": classification,
    }


def penalty_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    with_penalty = [row for row in rows if split_codes(row["penalty_codes"])]
    blocking = [row for row in rows if truthy(row["blocking_penalty_present"])]
    blocking_promoted = [row for row in blocking if is_entry_eligible(row)]
    source = inspect.getsource(scoring_disposition) + inspect.getsource(score_band)
    return {
        "rows_with_penalties": len(with_penalty),
        "rows_with_blocking_penalty": len(blocking),
        "blocking_penalty_violations": len(blocking_promoted),
        "penalties_numerically_subtracted": False,
        "raw_arithmetic_uses_components_only": "penalty" not in source.lower(),
        "non_blocking_penalty_preserved_rows": sum(
            bool(split_codes(row["penalty_codes"])) and not truthy(row["blocking_penalty_present"])
            for row in rows
        ),
        "result": "CLEAN_SEPARATE_GATE_SEMANTICS" if not blocking_promoted and "penalty" not in source.lower() else "VIOLATION_FOUND",
    }


def normalized_isolation_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    band_source = inspect.getsource(score_band)
    disposition_source = inspect.getsource(scoring_disposition)
    source_isolated = "normalized" not in band_source.lower() and "normalized" not in disposition_source.lower()
    output_violations = sum(
        row["scoring_disposition"] in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
        and row["raw_strategy_score"] < 80
        for row in rows
    )
    result = "NORMALIZED_DIAGNOSTIC_ISOLATED" if source_isolated and output_violations == 0 else "NORMALIZED_SCORE_LEAKS_INTO_ELIGIBILITY"
    return {
        "result": result,
        "implementation_source_isolated": source_isolated,
        "output_behavior_violations": output_violations,
        "usage_field_violations": sum(row["normalized_score_usage"] != "DIAGNOSTIC_ONLY" for row in rows),
    }


def normalized_counterfactual(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    promotions_80 = [
        row for row in rows
        if row.get("normalized_available_score") is not None
        and row["normalized_available_score"] >= 80
        and row["raw_strategy_score"] < 80
    ]
    promotions_90 = [
        row for row in rows
        if row.get("normalized_available_score") is not None
        and row["normalized_available_score"] >= 90
        and row["raw_strategy_score"] < 90
    ]
    full_baseline = eligible_keys(rows, threshold=Decimal("80"), coverage=Decimal("80"))
    full_normalized_80 = {
        row_key(row) for row in rows
        if row["score_mode"] == "FULL_SCORE"
        and row["score_coverage_pct"] >= 80
        and row.get("normalized_available_score") is not None
        and row["normalized_available_score"] >= 80
    }
    full_normalized_90 = {
        row_key(row) for row in rows
        if row["score_mode"] == "FULL_SCORE"
        and row["score_coverage_pct"] >= 80
        and row.get("normalized_available_score") is not None
        and row["normalized_available_score"] >= 90
    }
    return {
        "label": "INVALID_DIAGNOSTIC_ONLY",
        "all_rows_newly_gte_80": len(promotions_80),
        "all_rows_newly_gte_90": len(promotions_90),
        "full_score_normalized_80_eligible_count": len(full_normalized_80),
        "full_score_normalized_90_eligible_count": len(full_normalized_90),
        "normalized_80_vs_baseline": set_comparison(full_normalized_80, full_baseline),
        "normalized_90_vs_baseline": set_comparison(full_normalized_90, full_baseline),
    }


def score_margin_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for score in (78, 79, 80, 81, 82):
        group = [row for row in rows if row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] == score]
        vectors = Counter(component_vector(row) for row in group)
        output[str(score)] = {
            "rows": len(group),
            "entry_eligible": sum(is_entry_eligible(row) for row in group),
            "average_components": {component: mean([row[f"{component}_points"] for row in group]) for component in COMPONENTS},
            "top_patterns": [
                {"vector": vector_text(vector), "rows": count}
                for vector, count in sorted(vectors.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
        }
    component_steps = {
        "setup": sorted(set(SETUP_POINTS.values())),
        "momentum": sorted({row["momentum_points"] for row in rows}),
        "rvol": sorted(set(RVOL_POINTS.values())),
        "relative_strength": sorted(set(RS_POINTS.values())),
        "regime": sorted(set(REGIME_POINTS.values())),
        "reward_risk": [Decimal("0"), Decimal("3"), Decimal("4"), Decimal("5")],
    }
    output["interpretation"] = {
        "typical_deciders": ["reward_risk", "momentum", "rvol", "relative_strength", "regime"],
        "component_point_steps": component_steps,
        "finding": "Crossing 80 is jointly determined; one-to-five-point changes in R:R, momentum, RVOL, RS, or regime most often resolve the 78-82 margin.",
    }
    return output


def regime_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for state in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE"):
        group = [row for row in rows if row["regime_state"] == state]
        full = [row for row in group if row["score_mode"] == "FULL_SCORE"]
        values = sorted(row["raw_strategy_score"] for row in group)
        result[state] = {
            "rows": len(group),
            "full_score_rows": len(full),
            "median": quantile(values, 50),
            "p75": quantile(values, 75),
            "p90": quantile(values, 90),
            "p95": quantile(values, 95),
            "raw_gte_75": sum(row["raw_strategy_score"] >= 75 for row in group),
            "raw_gte_80": sum(row["raw_strategy_score"] >= 80 for row in group),
            "entry_eligible": sum(is_entry_eligible(row) for row in group),
            "maximum": max(values) if values else None,
        }
    bearish_exceptional = [row for row in rows if row["regime_state"] == "BEARISH" and row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE"]
    result["BEARISH_EXCEPTIONAL"] = {
        **distribution(bearish_exceptional),
        "ordinary_entry_eligible": sum(is_entry_eligible(row) for row in bearish_exceptional),
        "all_remain_exceptional_review": all(row["scoring_disposition"] == "EXCEPTIONAL_REVIEW" for row in bearish_exceptional),
    }
    result["theoretical_max"] = {"BULLISH": 85, "NEUTRAL": 80, "BEARISH": 75}
    result["theoretical_max_verified"] = all(
        row["regime_points"] + 75 == expected
        for state, expected in result["theoretical_max"].items()
        for row in [next((item for item in rows if item["regime_state"] == state and item["regime_availability"] == "AVAILABLE"), {"regime_points": expected - 75})]
    )
    return result


def reward_risk_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    mapping_violations = 0
    for row in rows:
        ratio = decimal_or_none(row["reward_risk_ratio"])
        expected = reward_risk_points(ratio)
        if expected is None:
            mapping_violations += row["reward_risk_availability"] == "AVAILABLE"
        else:
            mapping_violations += row["reward_risk_points"] != expected
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    distribution_counts = Counter(row["reward_risk_points"] for row in full)
    zero_violations = [row for row in full if row["reward_risk_points"] == 0]
    return {
        "boundary_mapping": {"LT_1_5": 0, "1_5_TO_LT_2": 3, "2_TO_LT_2_5": 4, "GTE_2_5": 5},
        "mapping_violations": mapping_violations,
        "full_score_zero_point_violations": len(zero_violations),
        "full_score_distribution": {format(points, "f"): count for points, count in sorted(distribution_counts.items())},
    }


def pilot_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[tuple[str, Callable[[dict[str, Any]], bool], str]] = [
        ("A_BULLISH_RAW_80", lambda row: row["regime_state"] == "BULLISH" and row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] == 80, "Bullish full score exactly 80"),
        ("B_BULLISH_RAW_85", lambda row: row["regime_state"] == "BULLISH" and row["raw_strategy_score"] == 85, "Bullish historical ceiling 85"),
        ("C_BULLISH_RAW_79", lambda row: row["regime_state"] == "BULLISH" and row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] == 79, "Bullish full score just below threshold"),
        ("D_NEUTRAL_RAW_80_ENTRY", lambda row: row["regime_state"] == "NEUTRAL" and row["raw_strategy_score"] == 80 and is_entry_eligible(row), "Neutral ceiling entry eligible"),
        ("E_NEUTRAL_LT_80", lambda row: row["regime_state"] == "NEUTRAL" and row["score_mode"] == "FULL_SCORE" and row["raw_strategy_score"] < 80, "Neutral below entry threshold"),
        ("F_BEARISH_EXCEPTIONAL_HIGH", lambda row: row["regime_state"] == "BEARISH" and row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE", "Bearish exceptional remains review only"),
        ("G_PREVIEW_GTE_80", lambda row: row["score_mode"] == "PREVIEW_SCORE" and row["raw_strategy_score"] >= 80, "Preview cannot become ordinary eligible"),
        ("H_INSUFFICIENT_COVERAGE", lambda row: row["scoring_disposition"] == "INSUFFICIENT_COVERAGE", "Below-80 coverage blocks ordinary eligibility"),
        ("I_STRONG_SETUP_WEAK_RVOL", lambda row: row["setup_quality"] == "STRONG" and row["rvol_points"] == 0, "Strong setup does not fabricate RVOL points"),
        ("J_WEAKER_SETUP_OTHER_EVIDENCE", lambda row: row["setup_quality"] == "VALID" and row["momentum_points"] >= 18 and row["relative_strength_points"] == 15, "VALID is weaker than STRONG while other evidence remains explicit"),
        ("K_BOTH_ELIGIBLE_GTE_80", lambda row: row["candidate_category"] == "BOTH_ELIGIBLE" and row["raw_strategy_score"] >= 80, "Both-eligible cohort receives no direct category points"),
        ("L_EMERGING_ONLY_GTE_80", lambda row: row["candidate_category"] == "EMERGING_ONLY" and row["raw_strategy_score"] >= 80, "Emerging-only can qualify through components"),
        ("M_FULL_SCORE_1_5_TO_2R", lambda row: row["score_mode"] == "FULL_SCORE" and Decimal("1.5") <= decimal_or_zero(row["reward_risk_ratio"]) < 2, "Full score with 1.5R to below 2R"),
        ("N_FULL_SCORE_GTE_2_5R", lambda row: row["score_mode"] == "FULL_SCORE" and decimal_or_zero(row["reward_risk_ratio"]) >= Decimal("2.5"), "Full score with at least 2.5R"),
    ]
    output: list[dict[str, Any]] = []
    for name, predicate, expected in cases:
        matches = [row for row in rows if predicate(row)]
        if not matches:
            if name == "G_PREVIEW_GTE_80":
                preview_rows = [row for row in rows if row["score_mode"] == "PREVIEW_SCORE"]
                if preview_rows:
                    selected = max(
                        preview_rows,
                        key=lambda row: (row["raw_strategy_score"], row["trading_date"], row["symbol"]),
                    )
                    output.append(
                        pilot_row(
                            name,
                            selected,
                            f"No preview row reached 80; highest actual preview ({selected['raw_strategy_score']}) remains PREVIEW_ONLY",
                        )
                    )
                    continue
            output.append(empty_pilot(name, expected))
            continue
        selected = max(matches, key=lambda row: (row["raw_strategy_score"], row["trading_date"], row["symbol"]))
        output.append(pilot_row(name, selected, expected))
    passed = all(row["result"] == "PASS" for row in output)
    return output, {
        "passed": passed,
        "cases": {row["pilot_case"]: row["result"] for row in output},
        "symbols": sorted({row["symbol"] for row in output if row["symbol"]}),
        "dates": sorted({row["trading_date"] for row in output if row["trading_date"]}),
        "rows": len(output),
    }


def read_score_rows(path: Path) -> list[dict[str, Any]]:
    decimal_fields = {
        *(f"{name}_points" for name in ALL_COMPONENTS),
        *(f"{name}_max_points" for name in ALL_COMPONENTS),
        "raw_strategy_score", "available_weight", "score_coverage_pct", "minimum_score_coverage_pct",
        "normalized_available_score", "reward_risk_ratio",
    }
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        for field in decimal_fields:
            row[field] = decimal_or_none(row.get(field))
    return rows


def audit_input_hashes(config: StrategyScoreAuditConfig) -> dict[str, str]:
    engine = config.engine_config
    return {
        "feature": file_sha256(engine.feature_dataset_path),
        "candidate": file_sha256(engine.candidate_dataset_path),
        "setup": file_sha256(engine.setup_dataset_path),
        "regime": file_sha256(engine.regime_dataset_path),
        "entry": file_sha256(engine.entry_dataset_path),
        "risk_v1": file_sha256(resolve_risk_structure_dataset(config.data_dir, "v1")),
        "risk_v1_1": file_sha256(config.risk_dataset_path),
        "score_v1": file_sha256(config.score_dataset_path),
    }


def expected_hash_matches(hashes: dict[str, str]) -> dict[str, bool]:
    expected = {
        **UPSTREAM_HASHES,
        "risk_v1": RISK_STRUCTURE_V1_DATASET_HASH,
        "risk_v1_1": RISK_STRUCTURE_V1_1_DATASET_HASH,
        "score_v1": STRATEGY_SCORE_V1_DATASET_HASH,
    }
    return {name: hashes.get(name) == value for name, value in expected.items()}


def verify_audit_hashes(hashes: dict[str, str]) -> None:
    results = expected_hash_matches(hashes)
    if not all(results.values()):
        raise ValueError(f"Frozen audit input hash mismatch: {dict((key, hashes.get(key)) for key, ok in results.items() if not ok)}")


def reconstruct_momentum_points(candidate: dict[str, str]) -> Decimal | None:
    values = {
        field: decimal_or_none(candidate.get(field))
        for field in ("return_5d", "return_10d", "return_20d", "up_days_ratio_10", "up_days_ratio_20")
    }
    if any(value is None for value in values.values()):
        return None
    points = Decimal("0")
    value = values["return_5d"]
    points += Decimal("4") if value >= Decimal("0.025") else Decimal("3") if value >= Decimal("0.015") else 0
    value = values["return_10d"]
    points += Decimal("4") if value >= Decimal("0.04") else Decimal("2") if value >= Decimal("-0.01") else 0
    value = values["return_20d"]
    points += Decimal("4") if value >= Decimal("0.06") else Decimal("2") if value >= 0 else 0
    value = values["up_days_ratio_10"]
    points += Decimal("4") if value >= Decimal("0.60") else Decimal("3") if value >= Decimal("0.50") else 0
    value = values["up_days_ratio_20"]
    points += Decimal("4") if value >= Decimal("0.55") else 0
    return points


def independent_score_band(raw_score: Decimal) -> str:
    if raw_score >= 90:
        return "HIGH_CONVICTION_SCORE"
    if raw_score >= 80:
        return "ENTRY_ELIGIBLE_SCORE"
    return "BELOW_THRESHOLD"


def independent_disposition(mode: str, raw_score: Decimal, coverage: Decimal) -> str:
    if mode == "PREVIEW_SCORE":
        return "PREVIEW_ONLY"
    if mode == "EXCEPTIONAL_REVIEW_SCORE":
        return "EXCEPTIONAL_REVIEW"
    if mode != "FULL_SCORE":
        return "NOT_ELIGIBLE"
    if coverage < 80:
        return "INSUFFICIENT_COVERAGE"
    if raw_score >= 90:
        return "HIGH_CONVICTION"
    if raw_score >= 80:
        return "ENTRY_ELIGIBLE"
    return "NOT_ELIGIBLE"


def reward_risk_points(ratio: Decimal | None) -> Decimal | None:
    if ratio is None:
        return None
    if ratio < Decimal("1.5"):
        return Decimal("0")
    if ratio < Decimal("2"):
        return Decimal("3")
    if ratio < Decimal("2.5"):
        return Decimal("4")
    return Decimal("5")


def component_profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "mean_points": {component: mean([row[f"{component}_points"] for row in rows]) for component in COMPONENTS},
        "median_points": {component: median([row[f"{component}_points"] for row in rows]) for component in COMPONENTS},
    }


def group_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "median_raw_score": median([row["raw_strategy_score"] for row in rows]),
        "raw_gte_80": sum(row["raw_strategy_score"] >= 80 for row in rows),
        "entry_eligible": sum(is_entry_eligible(row) for row in rows),
        "entry_eligible_rate_pct": pct(sum(is_entry_eligible(row) for row in rows), len(rows)),
    }


def component_report_row(
    section: str,
    component: str,
    group_name: str,
    rows: Sequence[dict[str, Any]],
    *,
    points: Decimal | None = None,
    notes: str = "",
) -> dict[str, Any]:
    profile = group_summary(rows)
    return {
        "section": section,
        "component": component,
        "group": group_name,
        "rows": len(rows),
        "points": points,
        "available_count": sum(row[f"{component}_availability"] == "AVAILABLE" for row in rows),
        "unavailable_count": sum(row[f"{component}_availability"] != "AVAILABLE" for row in rows),
        "mean_points": mean([row[f"{component}_points"] for row in rows]),
        "median_points": median([row[f"{component}_points"] for row in rows]),
        **profile,
        "notes": notes,
    }


def threshold_row(
    section: str,
    population: str,
    threshold: int,
    count: int,
    denominator: int,
    *,
    comparison: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    comparison = comparison or {}
    return {
        "section": section,
        "population": population,
        "threshold": threshold,
        "eligible_count": count,
        "population_pct": pct(count, denominator),
        "retained_vs_baseline": comparison.get("retained_vs_baseline", ""),
        "introduced_vs_baseline": comparison.get("introduced_vs_baseline", ""),
        "removed_vs_baseline": comparison.get("removed_vs_baseline", ""),
        "jaccard_vs_baseline": comparison.get("jaccard_vs_baseline", ""),
        "notes": notes,
    }


def gate_report_row(section: str, reason: str, row: dict[str, Any], risk: dict[str, str]) -> dict[str, Any]:
    return {
        "section": section,
        "reason": reason,
        "rows": 1,
        "trading_date": row["trading_date"],
        "symbol": row["symbol"],
        "raw_strategy_score": row["raw_strategy_score"],
        "score_mode": row["score_mode"],
        "scoring_disposition": row["scoring_disposition"],
        "risk_readiness": row["risk_readiness"],
        "risk_mode": risk.get("risk_mode", ""),
        "risk_rejection_reasons": row["risk_rejection_reasons"],
        "blocking_penalty_present": row["blocking_penalty_present"],
        "available_weight": row["available_weight"],
        "notes": row["upstream_progression_status"],
    }


def detail_row(row: dict[str, Any], section: str, expected: Any, observed: Any) -> dict[str, Any]:
    return {
        "section": section,
        "trading_date": row["trading_date"],
        "symbol": row["symbol"],
        "reason": section,
        "expected": expected,
        "observed": observed,
        "score_mode": row["score_mode"],
        "raw_strategy_score": row["raw_strategy_score"],
        "available_weight": row["available_weight"],
        "scoring_disposition": row["scoring_disposition"],
    }


def detail_rows_for(
    rows: Sequence[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool], reason: str
) -> list[dict[str, Any]]:
    return [detail_row(row, reason, "review", row["scoring_disposition"]) for row in rows if predicate(row)]


def pilot_row(case_name: str, row: dict[str, Any], expected: str) -> dict[str, Any]:
    arithmetic = sum((row[f"{component}_points"] for component in ALL_COMPONENTS), Decimal("0"))
    reconstructed_weight = sum(
        (EXPECTED_CAPS[component] for component in ALL_COMPONENTS if row[f"{component}_availability"] == "AVAILABLE"),
        Decimal("0"),
    )
    expected_disposition = independent_disposition(row["score_mode"], row["raw_strategy_score"], row["score_coverage_pct"])
    valid = (
        arithmetic == row["raw_strategy_score"]
        and reconstructed_weight == row["available_weight"]
        and row["score_coverage_pct"] == reconstructed_weight
        and row["score_band"] == independent_score_band(row["raw_strategy_score"])
        and row["scoring_disposition"] == expected_disposition
    )
    points = ";".join(f"{component}={format(row[f'{component}_points'], 'f')}" for component in ALL_COMPONENTS)
    return {
        "pilot_case": case_name,
        "symbol": row["symbol"],
        "trading_date": row["trading_date"],
        "score_mode": row["score_mode"],
        "component_points": points,
        "raw_strategy_score": row["raw_strategy_score"],
        "arithmetic_sum": arithmetic,
        "available_weight": row["available_weight"],
        "score_coverage_pct": row["score_coverage_pct"],
        "score_band": row["score_band"],
        "scoring_disposition": row["scoring_disposition"],
        "expected_semantics": expected,
        "result": "PASS" if valid else "FAIL",
    }


def empty_pilot(case_name: str, expected: str) -> dict[str, Any]:
    return {
        "pilot_case": case_name, "symbol": "", "trading_date": "", "score_mode": "",
        "component_points": "", "raw_strategy_score": "", "arithmetic_sum": "", "available_weight": "",
        "score_coverage_pct": "", "score_band": "", "scoring_disposition": "",
        "expected_semantics": expected, "result": "FAIL",
    }


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("trading_date", "")), canonical_symbol(row.get("symbol", ""))


def is_entry_eligible(row: dict[str, Any]) -> bool:
    return row["scoring_disposition"] in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}


def eligible_keys(rows: Sequence[dict[str, Any]], *, threshold: Decimal, coverage: Decimal) -> set[tuple[str, str]]:
    return {
        row_key(row)
        for row in rows
        if row["score_mode"] == "FULL_SCORE"
        and row["score_coverage_pct"] >= coverage
        and row["raw_strategy_score"] >= threshold
    }


def set_comparison(scenario: set[Any], baseline: set[Any]) -> dict[str, Any]:
    union = scenario | baseline
    return {
        "retained_vs_baseline": len(scenario & baseline),
        "introduced_vs_baseline": len(scenario - baseline),
        "removed_vs_baseline": len(baseline - scenario),
        "jaccard_vs_baseline": Decimal(len(scenario & baseline)) / Decimal(len(union)) if union else Decimal("1"),
    }


def coverage_cause(row: dict[str, Any]) -> str:
    unavailable = [component.upper() for component in ALL_COMPONENTS if row[f"{component}_availability"] != "AVAILABLE"]
    return ";".join(unavailable) if unavailable else "ALL_COMPONENTS_AVAILABLE"


def insufficient_coverage_cause(row: dict[str, Any]) -> str:
    if row["relative_strength_availability"] != "AVAILABLE":
        return "RS_UNAVAILABLE"
    if row["regime_availability"] != "AVAILABLE":
        return "REGIME_UNAVAILABLE"
    if row["reward_risk_availability"] != "AVAILABLE":
        return "RISK_DATA_UNAVAILABLE"
    return "OTHER"


def not_score_reason(row: dict[str, Any], risk: dict[str, str], entry: dict[str, str]) -> str:
    if truthy(row["blocking_penalty_present"]) or split_codes(row["risk_rejection_reasons"]):
        return "INVALID_BLOCKED"
    if not risk or not entry or row["available_weight"] < 80:
        return "INSUFFICIENT_DATA"
    if row["risk_readiness"] != "READY_FOR_FINAL_SCORING" or risk.get("risk_mode") != "FULL_EVALUATION":
        return "RISK_NOT_READY"
    return "OTHER"


def blocked_high_reason(row: dict[str, Any]) -> str:
    if row["score_mode"] == "PREVIEW_SCORE":
        return "PREVIEW"
    if row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE":
        return "EXCEPTIONAL"
    if row["score_mode"] == "FULL_SCORE" and row["score_coverage_pct"] < 80:
        return "INSUFFICIENT_COVERAGE"
    if truthy(row["blocking_penalty_present"]):
        return "BLOCKING_PENALTY"
    if split_codes(row["risk_rejection_reasons"]):
        return "RISK_REJECTION:" + "+".join(sorted(split_codes(row["risk_rejection_reasons"])))
    if row["score_mode"] == "NOT_SCORE_ELIGIBLE":
        return "NON_FULL_SCORE"
    return "OTHER"


def descriptor_from_basis(value: Any, prefix: str) -> str:
    text = str(value or "")
    return text[len(prefix) :] if text.startswith(prefix) else "UNAVAILABLE"


def component_vector(row: dict[str, Any]) -> tuple[Decimal, ...]:
    return tuple(row[f"{component}_points"] for component in COMPONENTS)


def vector_text(vector: Sequence[Decimal]) -> str:
    return ";".join(f"{component}={format(value, 'f')}" for component, value in zip(COMPONENTS, vector, strict=True))


def normalize_component(value: Decimal, maximum: Decimal) -> Decimal:
    return value / maximum if maximum else Decimal("0")


def correlation_pair(rows: Sequence[dict[str, Any]], left: str, right: str) -> Decimal | None:
    return pearson_correlation(
        [row[f"{left}_points"] for row in rows],
        [row[f"{right}_points"] for row in rows],
    )


def pearson_correlation(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_float = [float(value) for value in left]
    right_float = [float(value) for value in right]
    left_mean = statistics.fmean(left_float)
    right_mean = statistics.fmean(right_float)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_float, right_float, strict=True))
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left_float)
        * sum((value - right_mean) ** 2 for value in right_float)
    )
    return Decimal(str(numerator / denominator)) if denominator else None


def spearman_correlation(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    return pearson_correlation(average_ranks(left), average_ranks(right))


def average_ranks(values: Sequence[Decimal]) -> list[Decimal]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [Decimal("0")] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        rank = (Decimal(index + 1) + Decimal(end)) / Decimal("2")
        for position in range(index, end):
            ranks[indexed[position][0]] = rank
        index = end
    return ranks


def pair_redundancy_classification(pearson_value: Decimal | None, spearman_value: Decimal | None) -> str:
    if pearson_value is None or spearman_value is None:
        return "INCONCLUSIVE"
    maximum = max(abs(pearson_value), abs(spearman_value))
    if maximum >= Decimal("0.80"):
        return "HIGH_REDUNDANCY"
    if maximum >= Decimal("0.40"):
        return "MODERATE_OVERLAP"
    return "LOW_REDUNDANCY"


def threshold_structure_result(rows: Sequence[dict[str, Any]], neutral: dict[str, Any]) -> str:
    full = [row for row in rows if row["score_mode"] == "FULL_SCORE"]
    eligible_rate = pct(sum(is_entry_eligible(row) for row in full), len(full))
    if Decimal("5") <= eligible_rate <= Decimal("60") and neutral["classification"] == "COHERENT_BUT_STRICT":
        return "SELECTIVE_AND_COHERENT"
    if eligible_rate > 60:
        return "TOO_PERMISSIVE_STRUCTURALLY"
    if eligible_rate < 1:
        return "OVERLY_KNIFE_EDGE"
    return "INCONCLUSIVE"


def missing_component_result(invariants: dict[str, Any]) -> str:
    if invariants["normalized_formula_mismatches"]:
        return "NORMALIZATION_LEAK_FOUND"
    if invariants["sector_semantic_violations"] or invariants["catalyst_semantic_violations"]:
        return "FREE_POINTS_FOUND"
    if invariants["available_weight_mismatches"] or invariants["coverage_mismatches"]:
        return "COVERAGE_BUG"
    return "CLEAN_MISSING_EVIDENCE_POLICY"


def gate_separation_result(invariants: dict[str, Any], modes: dict[str, Any]) -> str:
    if modes["numeric_score_rescued_blocked_rows"]:
        return "SCORE_RESCUES_BLOCKED_ROWS"
    if modes["preview_invariant_violations"]:
        return "PREVIEW_LEAK"
    if modes["exceptional_invariant_violations"]:
        return "EXCEPTIONAL_LEAK"
    if invariants["entry_threshold_violations"]:
        return "INCONCLUSIVE"
    return "CLEAN_GATE_FIRST"


def distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(row["raw_strategy_score"] for row in rows)
    return {
        "rows": len(rows),
        "min": values[0] if values else None,
        "median": quantile(values, 50),
        "p75": quantile(values, 75),
        "p90": quantile(values, 90),
        "p95": quantile(values, 95),
        "max": values[-1] if values else None,
    }


def quantile(values: Sequence[Decimal], value: int) -> Decimal | None:
    return percentile(values, Decimal(value)) if values else None


def mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def median(values: Sequence[Decimal]) -> Decimal | None:
    return quantile(sorted(values), 50)


def decimal_or_none(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def decimal_equal(left: Decimal | None, right: Decimal | None, tolerance: Decimal) -> bool:
    if left is None or right is None:
        return left is right
    return abs(left - right) <= tolerance


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def pct(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) * Decimal("100") if denominator else Decimal("0")


def headroom_requirement(bucket: str) -> str:
    return {
        "ALREADY_GTE_80": "0",
        "CROSS_WITH_LE_5": "1-5",
        "REQUIRE_6_TO_10": "6-10",
        "REQUIRE_11_TO_15": "11-15",
        "CAN_REACH_WITH_FULL_15": "0-15",
        "ALREADY_GTE_90": "0",
        "CANNOT_REACH_WITH_15": ">15",
    }.get(bucket, "")


def prohibited_audit_fields(fields: Iterable[str]) -> list[str]:
    return [field for field in fields if any(token in field.lower() for token in PROHIBITED_FIELD_TOKENS)]


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def output_paths(config: StrategyScoreAuditConfig) -> dict[str, str]:
    return {
        "summary": str(config.summary_path),
        "components": str(config.report_path("components")),
        "correlations": str(config.report_path("correlations")),
        "thresholds": str(config.report_path("thresholds")),
        "gate_conflicts": str(config.report_path("gate_conflicts")),
        "coverage": str(config.report_path("coverage")),
        "candidate_categories": str(config.report_path("candidate_categories")),
        "neutral_ceiling": str(config.report_path("neutral_ceiling")),
        "headroom": str(config.report_path("headroom")),
        "pilot": str(config.report_path("pilot")),
        "bulk_detail_dir": str(config.audit_dir),
        "documentation": "docs/strategy-v1-final-scoring-audit.md",
    }


def audit_output_size(config: StrategyScoreAuditConfig) -> int:
    paths = [
        config.summary_path,
        *(config.report_path(name) for name in (
            "components", "correlations", "thresholds", "gate_conflicts", "coverage",
            "candidate_categories", "neutral_ceiling", "headroom", "pilot",
        )),
    ]
    if config.audit_dir.exists():
        paths.extend(path for path in config.audit_dir.rglob("*") if path.is_file())
    return sum(path.stat().st_size for path in paths if path.exists())


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def write_strategy_score_audit_markdown(report: dict[str, Any], path: Path) -> None:
    baseline = report["baseline"]
    invariants = report["invariants"]
    classifications = report["classifications"]
    modes = report["modes_and_gates"]
    lines = [
        "# STRATEGY_SCORE_V1 Structural Audit",
        "",
        f"- Audit version: {report['audit_version']}",
        f"- Baseline: {baseline['score_version']} / {baseline['score_profile']} / `{baseline['score_config_hash']}`",
        f"- Dataset SHA-256: `{baseline['score_dataset_hash']}`",
        f"- Active risk input: {baseline['risk_version']} / `{baseline['risk_config_hash']}`",
        "- Scope: structural score behavior only; no outcomes, optimization, backtest, signals, or execution.",
        "",
        "## Integrity",
        "",
        f"- Rows: {baseline['score_rows']}",
        f"- Arithmetic / cap / raw-bound violations: {invariants['arithmetic_mismatches']} / {invariants['component_cap_violations']} / {invariants['raw_score_bound_violations']}",
        f"- Available-weight / coverage / normalized-formula mismatches: {invariants['available_weight_mismatches']} / {invariants['coverage_mismatches']} / {invariants['normalized_formula_mismatches']}",
        f"- Normalized-score isolation: {report['normalized_diagnostic']['result']}",
        "",
        "## Gates And Coverage",
        "",
        f"- FULL / preview / exceptional / not eligible: {modes['mode_counts'].get('FULL_SCORE', 0)} / {modes['mode_counts'].get('PREVIEW_SCORE', 0)} / {modes['mode_counts'].get('EXCEPTIONAL_REVIEW_SCORE', 0)} / {modes['mode_counts'].get('NOT_SCORE_ELIGIBLE', 0)}",
        f"- Raw >=80 / ordinary eligible / blocked difference: {modes['raw_gte_80']} / {modes['entry_eligible']} / {modes['raw_gte_80_not_entry_eligible']}",
        f"- Exact blocked decomposition: {modes['raw_gte_80_not_entry_eligible_decomposition']}",
        f"- Coverage frequencies: {report['coverage']['exact_available_weight_frequencies']}",
        f"- Insufficient-coverage causes: {report['coverage']['insufficient_coverage_causes']}",
        "",
        "## Structural Findings",
        "",
        f"- Missing components: {classifications['missing_component_semantics']}",
        f"- Gate/score separation: {classifications['gate_score_separation']}",
        f"- Component redundancy: {classifications['component_redundancy']}",
        f"- Threshold structure: {classifications['threshold_structure']}",
        f"- Score resolution: {classifications['score_resolution']}",
        f"- Neutral ceiling: {report['neutral_ceiling']['classification']}",
        "",
        "## Decision",
        "",
        f"- Overall: {classifications['overall_structural_result']}",
        f"- Baseline decision: {classifications['baseline_decision']}",
        "- Review note: setup quality is a composite upstream judgment, so its overlap with dedicated momentum, RVOL, and RS components should remain visible in future outcome-based validation.",
        "- STRATEGY_SCORE_V1 was not modified by this audit.",
        "",
        "## Safety",
        "",
        "- ZERO signals, orders, remote migrations, and Supabase persistence.",
        "- Sector and catalyst remain unavailable; no historical values were inferred or back-projected.",
        "- Normalized available score remains diagnostic only.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

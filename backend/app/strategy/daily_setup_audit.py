from __future__ import annotations

import csv
import gzip
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.strategy.breakout_quality import (
    classify_52w_context,
    classify_acceptance_state,
    classify_benchmark_rs_context,
    classify_breakout_state,
    classify_candle_quality,
    classify_consolidation,
    classify_extension_risk,
    classify_overhead_resistance,
    classify_volume_confirmation,
    derive_setup_decision,
    false_breakout_flags,
    setup_type_flags,
)
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.daily_setup_evaluator import (
    DailySetupEvaluationConfig,
    max_decimal,
    pct,
    truthy,
)
from app.strategy.momentum_candidate_audit import decimal_quantile, quantile_number, round_decimal
from app.strategy.momentum_candidates import (
    distribution,
    file_sha256,
    open_csv_maybe_gzip,
    parse_bool,
    parse_decimal,
    split_codes,
)

DAILY_SETUP_AUDIT_VERSION = "DAILY_SETUP_AUDIT_V1"

CANDLE_QUALITY_FIELDS = ["section", "group", "state", "sub_state", "count", "pct", "details"]
REJECTION_OVERLAP_FIELDS = ["section", "group", "state", "sub_state", "count", "pct", "details"]
TRANSITION_MATRIX_FIELDS = ["section", "from_state", "to_state", "candidate_state", "count", "from_total", "pct"]
SENSITIVITY_FIELDS = [
    "scenario",
    "candidate_rows_evaluated",
    "setup_eligible",
    "pass_rate_pct",
    "strong_count",
    "valid_count",
    "watch_count",
    "poor_count",
    "emerging_pass_rate_pct",
    "confirmed_pass_rate_pct",
    "daily_median",
    "daily_mean",
    "daily_p90",
    "daily_p95",
    "daily_max",
    "symbols_ever_setup_eligible",
    "baseline_retained_rows",
    "removed_rows",
    "introduced_rows",
    "jaccard_similarity",
    "median_setup_streak",
]
STREAK_SUMMARY_FIELDS = [
    "streak_type",
    "streak_count",
    "one_session",
    "two_sessions",
    "three_to_five",
    "six_to_ten",
    "over_ten",
    "median",
    "mean",
    "p90",
    "p95",
    "max",
]
DAILY_CHURN_FIELDS = [
    "trading_date",
    "setup_eligible",
    "new_setup_eligible_today",
    "continued_setup_eligible",
    "dropped_setup_eligible",
    "churn_rate_pct",
]
DAILY_DENSITY_FIELDS = ["trading_date", "setup_eligible", "density_flag"]

NUMERIC_CANDLE_FIELDS = [
    "close_location_value",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
    "daily_range_pct",
    "gap_open_pct",
]

SCENARIO_NAMES = [
    "CANDLE_LOOSER",
    "BASELINE",
    "CANDLE_TIGHTER",
    "ACCEPTANCE_LOOSER",
    "ACCEPTANCE_TIGHTER",
    "CONSOLIDATION_LOOSER",
    "CONSOLIDATION_TIGHTER",
    "FALSE_BREAKOUT_WARNING_ONLY",
    "FALSE_BREAKOUT_STRICT",
    "EXTENSION_LOOSER",
    "EXTENSION_TIGHTER",
    "SETUP_CONSERVATIVE_COMBINED",
    "SETUP_LOOSER_COMBINED",
]


@dataclass(frozen=True, slots=True)
class DailySetupAuditConfig:
    data_dir: Path
    start_date: date | None = None
    end_date: date | None = None
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    audit_version: str = DAILY_SETUP_AUDIT_VERSION

    @property
    def setup_dataset_path(self) -> Path:
        return self.data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def calendar_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "calendar" / "nse_cash_trading_calendar.csv"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "daily_setups" / "v1"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "daily_setup_audit_summary.json"

    @property
    def candle_quality_path(self) -> Path:
        return self.reports_dir / "daily_setup_candle_quality.csv"

    @property
    def rejection_overlap_path(self) -> Path:
        return self.reports_dir / "daily_setup_rejection_overlap.csv"

    @property
    def transition_matrix_path(self) -> Path:
        return self.reports_dir / "daily_setup_transition_matrix.csv"

    @property
    def sensitivity_path(self) -> Path:
        return self.reports_dir / "daily_setup_sensitivity.csv"

    @property
    def streak_summary_path(self) -> Path:
        return self.reports_dir / "daily_setup_streak_summary.csv"

    @property
    def daily_churn_path(self) -> Path:
        return self.audit_dir / "daily_setup_churn.csv.gz"

    @property
    def daily_density_path(self) -> Path:
        return self.audit_dir / "daily_setup_density.csv.gz"


def build_daily_setup_audit(*, config: DailySetupAuditConfig, progress: Any | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    setup_before = file_sha256(config.setup_dataset_path)
    candidate_before = file_sha256(config.candidate_dataset_path)
    feature_before = file_sha256(config.feature_dataset_path)

    if progress:
        progress("Loading DAILY_SETUP_EVALUATION_V1 baseline")
    setup_rows = load_setup_rows(config.setup_dataset_path, config.start_date, config.end_date)
    trading_sessions = load_trading_sessions(config.calendar_path, setup_rows)

    if progress:
        progress("Analyzing funnel and candle semantics")
    funnel = funnel_summary(setup_rows)
    candle_rows, candle_summary = candle_quality_audit_rows(setup_rows, config.setup_config)
    rejection_rows, rejection_summary = rejection_overlap_audit_rows(setup_rows)
    false_breakout = false_breakout_summary(setup_rows)
    reclaim = daily_reclaim_summary(setup_rows)
    component_analyses = {
        "approaching_testing": component_group_summary(
            [row for row in setup_rows if row["breakout_state"] in {"APPROACHING", "TESTING"}],
            label="APPROACHING_OR_TESTING",
        ),
        "close_above_accepted": component_group_summary(
            [row for row in setup_rows if row["breakout_state"] in {"CLOSE_ABOVE", "CLOSE_ACCEPTED"}],
            label="CLOSE_ABOVE_OR_ACCEPTED",
        ),
        "emerging_vs_confirmed": state_comparison_summary(setup_rows),
        "consolidation": grouped_component_summary(setup_rows, "consolidation_state"),
        "consolidation_quality": grouped_component_summary(setup_rows, "consolidation_quality"),
        "volume_confirmation": grouped_component_summary(setup_rows, "volume_confirmation"),
        "extension_risk": grouped_component_summary(setup_rows, "extension_risk"),
        "overhead_resistance": grouped_component_summary(setup_rows, "overhead_resistance"),
    }

    if progress:
        progress("Analyzing setup persistence and transitions")
    streak_rows, streak_summary = setup_streak_summary_rows(setup_rows, trading_sessions)
    transition_rows, transition_summary = transition_matrix_rows(setup_rows, trading_sessions)
    churn_rows, churn_summary = daily_churn_rows(setup_rows, trading_sessions)
    density_rows, density_summary = daily_density_rows(setup_rows)

    if progress:
        progress("Running structural sensitivity scenarios")
    sensitivity_rows, sensitivity_summary = sensitivity_audit_rows(setup_rows, config.setup_config, trading_sessions)

    write_csv(config.candle_quality_path, candle_rows, CANDLE_QUALITY_FIELDS)
    write_csv(config.rejection_overlap_path, rejection_rows, REJECTION_OVERLAP_FIELDS)
    write_csv(config.transition_matrix_path, transition_rows, TRANSITION_MATRIX_FIELDS)
    write_csv(config.sensitivity_path, sensitivity_rows, SENSITIVITY_FIELDS)
    write_csv(config.streak_summary_path, streak_rows, STREAK_SUMMARY_FIELDS)
    write_gzip_csv(config.daily_churn_path, churn_rows, DAILY_CHURN_FIELDS)
    write_gzip_csv(config.daily_density_path, density_rows, DAILY_DENSITY_FIELDS)

    setup_after = file_sha256(config.setup_dataset_path)
    candidate_after = file_sha256(config.candidate_dataset_path)
    feature_after = file_sha256(config.feature_dataset_path)
    structural_stability = structural_stability_result(sensitivity_rows)
    funnel_sanity = funnel_sanity_result(funnel, candle_summary, sensitivity_summary)

    report = {
        "phase": "Step 02.6",
        "command": "Command 02",
        "generated_at": generated_at,
        "audit": {
            "audit_version": config.audit_version,
            "setup_version": "DAILY_SETUP_EVALUATION_V1",
            "setup_config_hash": observed_single_value(setup_rows, "setup_config_hash"),
            "expected_setup_config_hash": config.setup_config.config_hash(),
            "candidate_version": observed_single_value(setup_rows, "candidate_version"),
            "candidate_config_hash": observed_single_value(setup_rows, "candidate_config_hash"),
            "expected_candidate_config_hash": config.candidate_config.config_hash(),
            "feature_version": observed_single_value(setup_rows, "feature_version"),
            "methodology": "Structural audit of setup funnel behavior only; no future returns, MFE, MAE, winner/loser labels, profitability, target/stop outcomes, backtesting, entry scoring, or trading execution.",
        },
        "inputs": {
            "setup_dataset": str(config.setup_dataset_path),
            "setup_hash_before": setup_before,
            "setup_hash_after": setup_after,
            "candidate_dataset": str(config.candidate_dataset_path),
            "candidate_hash_before": candidate_before,
            "candidate_hash_after": candidate_after,
            "feature_dataset": str(config.feature_dataset_path),
            "feature_hash_before": feature_before,
            "feature_hash_after": feature_after,
        },
        "funnel": funnel,
        "candle_quality": candle_summary,
        "rejection_overlap": rejection_summary,
        "primary_rejection_driver": primary_rejection_driver_summary(setup_rows),
        "false_breakout": false_breakout,
        "daily_reclaim": reclaim,
        "component_analyses": component_analyses,
        "streaks": streak_summary,
        "transitions": transition_summary,
        "churn": churn_summary,
        "daily_density": density_summary,
        "sensitivity": sensitivity_summary,
        "structural_stability": structural_stability,
        "funnel_sanity": funnel_sanity,
        "regression": {
            "setup_dataset_unchanged": setup_before == setup_after,
            "candidate_dataset_unchanged": candidate_before == candidate_after,
            "feature_dataset_unchanged": feature_before == feature_after,
            "setup_config_hash_unchanged": observed_single_value(setup_rows, "setup_config_hash")
            == config.setup_config.config_hash(),
            "candidate_config_hash_unchanged": observed_single_value(setup_rows, "candidate_config_hash")
            == config.candidate_config.config_hash(),
        },
        "safety": {
            "future_outcome_fields_used": 0,
            "future_return_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "profitability_optimization_used": 0,
            "baseline_setup_config_changed": False,
            "entry_scores_generated": 0,
            "market_regime_scores_generated": 0,
            "risk_reward_calculated": 0,
            "stops_generated": 0,
            "targets_generated": 0,
            "position_sizes_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
        },
        "outputs": {
            "summary_json": str(config.summary_path),
            "candle_quality_csv": str(config.candle_quality_path),
            "rejection_overlap_csv": str(config.rejection_overlap_path),
            "transition_matrix_csv": str(config.transition_matrix_path),
            "sensitivity_csv": str(config.sensitivity_path),
            "streak_summary_csv": str(config.streak_summary_path),
            "daily_churn_bulk": str(config.daily_churn_path),
            "daily_density_bulk": str(config.daily_density_path),
            "markdown": "docs/daily-setup-audit.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": sum(
                file_size(path)
                for path in [
                    config.summary_path,
                    config.candle_quality_path,
                    config.rejection_overlap_path,
                    config.transition_matrix_path,
                    config.sensitivity_path,
                    config.streak_summary_path,
                    config.daily_churn_path,
                    config.daily_density_path,
                ]
            ),
        },
        "ready_for_review": bool(
            setup_before == setup_after
            and candidate_before == candidate_after
            and feature_before == feature_after
            and observed_single_value(setup_rows, "setup_config_hash") == config.setup_config.config_hash()
            and observed_single_value(setup_rows, "candidate_config_hash") == config.candidate_config.config_hash()
            and structural_stability["status"] in {"STABLE", "MODERATELY_SENSITIVE"}
            and funnel_sanity["status"] in {"HEALTHY", "HEALTHY_BUT_CANDLE_STRICT"}
        ),
    }
    write_json(config.summary_path, report)
    return report


def load_setup_rows(path: Path, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            parsed = parse_date_value(row.get("trading_date"))
            if parsed is None:
                continue
            if start_date is not None and parsed < start_date:
                continue
            if end_date is not None and parsed > end_date:
                continue
            row["_key"] = setup_key(row)
            rows.append(row)
    return rows


def load_trading_sessions(calendar_path: Path, setup_rows: Sequence[dict[str, Any]]) -> list[str]:
    if calendar_path.exists():
        sessions: list[str] = []
        with calendar_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if str(row.get("source_available", "")).lower() == "true":
                    sessions.append(str(row.get("trading_date", "")))
        if sessions:
            setup_dates = {str(row.get("trading_date", "")) for row in setup_rows}
            start = min(setup_dates) if setup_dates else sessions[0]
            end = max(setup_dates) if setup_dates else sessions[-1]
            return [item for item in sessions if start <= item <= end]
    return sorted({str(row.get("trading_date", "")) for row in setup_rows})


def funnel_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    eligible = [row for row in rows if truthy(row.get("setup_eligible"))]
    emerging = [row for row in rows if row.get("candidate_state") == "EMERGING"]
    confirmed = [row for row in rows if row.get("candidate_state") == "CONFIRMED"]
    both = [row for row in rows if truthy(row.get("both_eligible"))]
    quality_counts = Counter(str(row.get("setup_quality", "")) for row in rows)
    all_dates = sorted({str(row.get("trading_date", "")) for row in rows})
    daily_counts = Counter(str(row.get("trading_date", "")) for row in eligible)
    return {
        "candidate_rows": total,
        "setup_eligible": len(eligible),
        "setup_rejected": total - len(eligible),
        "overall_pass_rate_pct": pct(len(eligible), total),
        "emerging_pass_rate_pct": pct(sum(1 for row in emerging if truthy(row.get("setup_eligible"))), len(emerging)),
        "confirmed_pass_rate_pct": pct(sum(1 for row in confirmed if truthy(row.get("setup_eligible"))), len(confirmed)),
        "both_eligible_pass_rate_pct": pct(sum(1 for row in both if truthy(row.get("setup_eligible"))), len(both)),
        "quality_counts": dict(quality_counts),
        "quality_percentages": {quality: pct(count, total) for quality, count in quality_counts.items()},
        "daily_setup_eligible_distribution": numeric_distribution([daily_counts[trading_date] for trading_date in all_dates], include_p10=True),
    }


def candle_quality_audit_rows(
    rows: Sequence[dict[str, Any]],
    setup_config: DailySetupEvaluationConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    groups = {
        "ALL": list(rows),
        "EMERGING_PRIMARY": [row for row in rows if row.get("candidate_state") == "EMERGING"],
        "CONFIRMED_PRIMARY": [row for row in rows if row.get("candidate_state") == "CONFIRMED"],
        "BOTH_ELIGIBLE": [row for row in rows if truthy(row.get("both_eligible"))],
        "SETUP_ELIGIBLE": [row for row in rows if truthy(row.get("setup_eligible"))],
        "SETUP_REJECTED": [row for row in rows if not truthy(row.get("setup_eligible"))],
    }
    distribution_by_group: dict[str, Any] = {}
    for group, group_rows in groups.items():
        counter = Counter(str(row.get("candle_quality", "")) or "UNAVAILABLE" for row in group_rows)
        distribution_by_group[group] = {
            quality: {"count": counter[quality], "pct": pct(counter[quality], len(group_rows))}
            for quality in ["POOR", "FAIR", "GOOD", "STRONG", "UNAVAILABLE"]
        }
        for quality, payload in distribution_by_group[group].items():
            output.append(
                {
                    "section": "CANDLE_QUALITY_DISTRIBUTION",
                    "group": group,
                    "state": quality,
                    "sub_state": "",
                    "count": payload["count"],
                    "pct": payload["pct"],
                    "details": "",
                }
            )

    poor_rows = [row for row in rows if row.get("candle_quality") == "POOR"]
    weakness_counter: Counter[str] = Counter()
    combination_counter: Counter[str] = Counter()
    overlap_counter: Counter[str] = Counter()
    for row in poor_rows:
        weaknesses = candle_weaknesses(row, setup_config)
        for weakness in weaknesses:
            weakness_counter[weakness] += 1
        if len(weaknesses) == 1:
            overlap_counter["exactly_1"] += 1
        elif len(weaknesses) == 2:
            overlap_counter["exactly_2"] += 1
        else:
            overlap_counter["exactly_3_plus"] += 1
        combination_counter[";".join(weaknesses)] += 1

    for reason, count in weakness_counter.most_common():
        output.append(
            {
                "section": "POOR_CANDLE_REASON",
                "group": "POOR",
                "state": reason,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(poor_rows)),
                "details": "",
            }
        )
    for bucket, count in overlap_counter.items():
        output.append(
            {
                "section": "POOR_CANDLE_WEAKNESS_COUNT",
                "group": "POOR",
                "state": bucket,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(poor_rows)),
                "details": "",
            }
        )
    for combination, count in combination_counter.most_common(20):
        output.append(
            {
                "section": "POOR_CANDLE_COMBINATION",
                "group": "POOR",
                "state": combination,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(poor_rows)),
                "details": "Top 20 weakness combinations among POOR candle rows.",
            }
        )

    for breakout_state, breakout_rows in group_rows_by(rows, "breakout_state").items():
        counter = Counter(str(row.get("candle_quality", "")) or "UNAVAILABLE" for row in breakout_rows)
        for quality in ["POOR", "FAIR", "GOOD", "STRONG", "UNAVAILABLE"]:
            output.append(
                {
                    "section": "BREAKOUT_X_CANDLE",
                    "group": breakout_state,
                    "state": quality,
                    "sub_state": "",
                    "count": counter[quality],
                    "pct": pct(counter[quality], len(breakout_rows)),
                    "details": "",
                }
            )

    poor_numeric = {
        field: decimal_distribution([parse_decimal(row.get(field)) for row in poor_rows])
        for field in NUMERIC_CANDLE_FIELDS
    }
    summary = {
        "distribution_by_group": distribution_by_group,
        "poor_count": len(poor_rows),
        "poor_pct": pct(len(poor_rows), len(rows)),
        "poor_semantics": {
            "source": "backend/app/strategy/breakout_quality.py::classify_candle_quality",
            "conditions": [
                "UNAVAILABLE when close_location_value is missing.",
                "POOR when close_location_value < 0.350.",
                "POOR when upper_wick_pct >= 0.025 and close_location_value < 0.600.",
                "STRONG requires close_location_value >= 0.750, upper_wick_pct <= 0.012, and body_pct >= 0.004.",
                "GOOD requires close_location_value >= 0.600 and upper_wick_pct <= 0.025.",
                "FAIR requires close_location_value >= 0.450.",
                "The final fallback below FAIR is POOR.",
            ],
            "thresholds": asdict(setup_config.candle),
        },
        "poor_reason_decomposition": {
            reason: {"count": count, "pct": pct(count, len(poor_rows))}
            for reason, count in weakness_counter.most_common()
        },
        "poor_weakness_count": dict(overlap_counter),
        "top_poor_weakness_combinations": [
            {"combination": combo, "count": count, "pct": pct(count, len(poor_rows))}
            for combo, count in combination_counter.most_common(20)
        ],
        "poor_numeric_distributions": poor_numeric,
        "breakout_x_candle": breakout_x_candle_summary(rows),
    }
    return output, summary


def candle_weaknesses(row: dict[str, Any], config: DailySetupEvaluationConfig) -> list[str]:
    weaknesses: list[str] = []
    close_location = parse_decimal(row.get("close_location_value"))
    body = parse_decimal(row.get("body_pct"))
    upper_wick = parse_decimal(row.get("upper_wick_pct"))
    gap_open = parse_decimal(row.get("gap_open_pct"))
    if close_location is None or close_location < config.candle.fair_close_location:
        weaknesses.append("WEAK_CLOSE_LOCATION")
    if body is None or body < config.candle.meaningful_body_pct:
        weaknesses.append("SMALL_BODY")
    if upper_wick is not None and upper_wick >= config.candle.large_upper_wick_pct:
        weaknesses.append("LARGE_UPPER_WICK")
    if (
        "GAP_FADE" in split_codes(row.get("false_breakout_flags", ""))
        or (
            gap_open is not None
            and gap_open >= config.extension.gap_fade_threshold
            and close_location is not None
            and close_location < config.acceptance.weak_close_location
        )
    ):
        weaknesses.append("GAP_FADE")
    if len(weaknesses) >= 2:
        weaknesses.append("MULTIPLE_CANDLE_WEAKNESSES")
    if not weaknesses:
        weaknesses.append("OTHER")
    return sorted(weaknesses)


def breakout_x_candle_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for breakout_state, group in group_rows_by(rows, "breakout_state").items():
        counter = Counter(str(row.get("candle_quality", "")) or "UNAVAILABLE" for row in group)
        summary[breakout_state] = {
            quality: {"count": counter[quality], "pct": pct(counter[quality], len(group))}
            for quality in ["POOR", "FAIR", "GOOD", "STRONG", "UNAVAILABLE"]
        }
    return summary


def rejection_overlap_audit_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    rejected = [row for row in rows if not truthy(row.get("setup_eligible"))]
    count_buckets: Counter[str] = Counter()
    combination_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    pair_counter: Counter[str] = Counter()
    for row in rejected:
        reasons = sorted(split_codes(row.get("setup_rejection_reasons", "")))
        if len(reasons) == 1:
            count_buckets["exactly_1"] += 1
        elif len(reasons) == 2:
            count_buckets["exactly_2"] += 1
        else:
            count_buckets["exactly_3_plus"] += 1
        combo = ";".join(reasons) if reasons else "NO_REASON"
        combination_counter[combo] += 1
        for reason in reasons:
            reason_counter[reason] += 1
        for first_index, first in enumerate(reasons):
            for second in reasons[first_index + 1 :]:
                pair_counter[f"{first}+{second}"] += 1

    for bucket, count in count_buckets.items():
        output.append(
            {
                "section": "REJECTION_REASON_COUNT",
                "group": "REJECTED",
                "state": bucket,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(rejected)),
                "details": "",
            }
        )
    for reason, count in reason_counter.most_common():
        output.append(
            {
                "section": "REJECTION_REASON_RAW",
                "group": "REJECTED",
                "state": reason,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(rejected)),
                "details": "Reasons overlap; counts are not unique rows.",
            }
        )
    for combo, count in combination_counter.most_common(20):
        output.append(
            {
                "section": "REJECTION_COMBINATION",
                "group": "REJECTED",
                "state": combo,
                "sub_state": "",
                "count": count,
                "pct": pct(count, len(rejected)),
                "details": "Top 20 rejection reason combinations.",
            }
        )
    for pair, count in pair_counter.most_common(30):
        first, second = pair.split("+", 1)
        output.append(
            {
                "section": "REJECTION_PAIR",
                "group": "REJECTED",
                "state": first,
                "sub_state": second,
                "count": count,
                "pct": pct(count, len(rejected)),
                "details": "",
            }
        )

    summary = {
        "rejected_rows": len(rejected),
        "reason_count_distribution": dict(count_buckets),
        "raw_reason_counts": {
            reason: {"count": count, "pct": pct(count, len(rejected))}
            for reason, count in reason_counter.most_common()
        },
        "top_reason_combinations": [
            {"combination": combo, "count": count, "pct": pct(count, len(rejected))}
            for combo, count in combination_counter.most_common(20)
        ],
        "top_reason_pairs": [
            {"pair": pair, "count": count, "pct": pct(count, len(rejected))}
            for pair, count in pair_counter.most_common(20)
        ],
    }
    return output, summary


def primary_rejection_driver_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rejected = [row for row in rows if not truthy(row.get("setup_eligible"))]
    counter = Counter(primary_rejection_driver(row) for row in rejected)
    return {
        "distribution": {
            driver: {"count": count, "pct": pct(count, len(rejected))}
            for driver, count in counter.most_common()
        },
        "priority": [
            "RESEARCH_BLOCK",
            "NO_SETUP_CONTEXT",
            "CANDLE_FAILURE",
            "FALSE_BREAKOUT_RISK",
            "CONFIRMATION_WEAKNESS",
            "EXTENSION",
            "OTHER",
        ],
    }


def primary_rejection_driver(row: dict[str, Any]) -> str:
    reasons = split_codes(row.get("setup_rejection_reasons", ""))
    if "RESEARCH_BLOCKED" in reasons or "RESEARCH_UNAVAILABLE" in reasons:
        return "RESEARCH_BLOCK"
    if "NO_CLEAR_BREAKOUT_OR_CONTINUATION" in reasons:
        return "NO_SETUP_CONTEXT"
    if "POOR_CANDLE_QUALITY" in reasons:
        return "CANDLE_FAILURE"
    if "POSSIBLE_FALSE_BREAKOUT" in reasons:
        return "FALSE_BREAKOUT_RISK"
    if "INSUFFICIENT_SETUP_CONFIRMATION" in reasons or "CONFIRMED_REQUIRES_CLOSE_OR_CONTINUATION" in reasons:
        return "CONFIRMATION_WEAKNESS"
    if "EXTREME_EXTENSION" in reasons:
        return "EXTENSION"
    return "OTHER"


def false_breakout_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    flagged = [row for row in rows if split_codes(row.get("false_breakout_flags", ""))]
    flag_counter: Counter[str] = Counter()
    combo_counter: Counter[str] = Counter()
    for row in flagged:
        flags = sorted(split_codes(row.get("false_breakout_flags", "")))
        combo_counter[";".join(flags)] += 1
        for flag in flags:
            flag_counter[flag] += 1
    return {
        "rows_with_any_flag": len(flagged),
        "rows_with_any_flag_pct": pct(len(flagged), len(rows)),
        "flag_counts": {flag: {"count": count, "pct": pct(count, len(rows))} for flag, count in flag_counter.most_common()},
        "top_flag_combinations": [
            {"combination": combo, "count": count, "pct": pct(count, len(flagged))}
            for combo, count in combo_counter.most_common(20)
        ],
        "setup_pass_rate_pct": pct(sum(1 for row in flagged if truthy(row.get("setup_eligible"))), len(flagged)),
        "candle_quality": distribution_for_field(flagged, "candle_quality"),
        "breakout_state": distribution_for_field(flagged, "breakout_state"),
    }


def daily_reclaim_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    reclaim_rows = [row for row in rows if truthy(row.get("daily_level_reclaim"))]
    return {
        "count": len(reclaim_rows),
        "pct": pct(len(reclaim_rows), len(rows)),
        "candidate_state": distribution_for_field(reclaim_rows, "candidate_state"),
        "reclaim_depth_status": distribution_for_field(reclaim_rows, "reclaim_depth_status"),
        "candle_quality": distribution_for_field(reclaim_rows, "candle_quality"),
        "setup_quality": distribution_for_field(reclaim_rows, "setup_quality"),
        "setup_pass_rate_pct": pct(sum(1 for row in reclaim_rows if truthy(row.get("setup_eligible"))), len(reclaim_rows)),
        "volume_confirmation": distribution_for_field(reclaim_rows, "volume_confirmation"),
        "benchmark_rs_context": distribution_for_field(reclaim_rows, "benchmark_rs_context"),
    }


def component_group_summary(rows: Sequence[dict[str, Any]], *, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "count": len(rows),
        "setup_pass_rate_pct": pct(sum(1 for row in rows if truthy(row.get("setup_eligible"))), len(rows)),
        "setup_quality": distribution_for_field(rows, "setup_quality"),
        "candle_quality": distribution_for_field(rows, "candle_quality"),
        "acceptance_state": distribution_for_field(rows, "acceptance_state"),
        "volume_confirmation": distribution_for_field(rows, "volume_confirmation"),
        "benchmark_rs_context": distribution_for_field(rows, "benchmark_rs_context"),
        "consolidation_quality": distribution_for_field(rows, "consolidation_quality"),
        "extension_risk": distribution_for_field(rows, "extension_risk"),
        "false_breakout_flags": false_breakout_flag_distribution(rows),
    }


def state_comparison_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        state: component_group_summary(
            [row for row in rows if row.get("candidate_state") == state],
            label=state,
        )
        for state in ["EMERGING", "CONFIRMED"]
    }


def grouped_component_summary(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for state, group in group_rows_by(rows, field).items():
        output[state] = {
            "count": len(group),
            "setup_pass_rate_pct": pct(sum(1 for row in group if truthy(row.get("setup_eligible"))), len(group)),
            "candidate_state": distribution_for_field(group, "candidate_state"),
            "setup_quality": distribution_for_field(group, "setup_quality"),
            "breakout_state": distribution_for_field(group, "breakout_state"),
        }
    return output


def setup_streak_summary_rows(
    rows: Sequence[dict[str, Any]],
    trading_sessions: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    streak_sets = {
        "ANY_SETUP_ELIGIBLE": lambda row: truthy(row.get("setup_eligible")),
        "STRONG_SETUP": lambda row: row.get("setup_quality") == "STRONG",
        "VALID_SETUP": lambda row: row.get("setup_quality") == "VALID",
        "WATCH_SETUP": lambda row: row.get("setup_quality") == "WATCH",
    }
    setup_dates_by_symbol = setup_dates_index(rows)
    session_index = {session: offset for offset, session in enumerate(trading_sessions)}
    output_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for streak_type, predicate in streak_sets.items():
        lengths: list[int] = []
        for _symbol, date_map in setup_dates_by_symbol.items():
            active_dates = sorted(date for date, row in date_map.items() if predicate(row))
            lengths.extend(streak_lengths(active_dates, session_index))
        output = streak_distribution_row(streak_type, lengths)
        output_rows.append(output)
        summary[streak_type] = output
    return output_rows, summary


def transition_matrix_rows(
    rows: Sequence[dict[str, Any]],
    trading_sessions: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    next_session = next_session_map(trading_sessions)
    row_by_key = {(str(row.get("trading_date")), str(row.get("symbol"))): row for row in rows}
    quality_counter: Counter[tuple[str, str, str]] = Counter()
    eligible_counter: Counter[tuple[str, str]] = Counter()
    eligible_by_state: Counter[tuple[str, str]] = Counter()
    for row in rows:
        current_date = str(row.get("trading_date", ""))
        next_date = next_session.get(current_date)
        if not next_date:
            continue
        next_row = row_by_key.get((next_date, str(row.get("symbol"))))
        from_quality = str(row.get("setup_quality", "UNAVAILABLE")) or "UNAVAILABLE"
        to_quality = str(next_row.get("setup_quality", "UNAVAILABLE")) if next_row else "UNAVAILABLE"
        candidate_state = str(row.get("candidate_state", "UNKNOWN"))
        quality_counter[(from_quality, to_quality, candidate_state)] += 1
        if truthy(row.get("setup_eligible")):
            if next_row is None:
                next_bucket = "UNAVAILABLE"
            elif truthy(next_row.get("setup_eligible")):
                next_bucket = "REMAINS_SETUP_ELIGIBLE"
            elif next_row.get("setup_quality") == "WATCH":
                next_bucket = "BECOMES_WATCH"
            elif next_row.get("setup_quality") == "POOR":
                next_bucket = "BECOMES_POOR"
            else:
                next_bucket = str(next_row.get("setup_quality", "UNAVAILABLE"))
            eligible_counter[(next_bucket, "ALL")] += 1
            eligible_by_state[(next_bucket, candidate_state)] += 1

    output: list[dict[str, Any]] = []
    from_totals: Counter[tuple[str, str]] = Counter()
    for from_quality, _to_quality, candidate_state in quality_counter:
        from_totals[(from_quality, candidate_state)] += quality_counter[(from_quality, _to_quality, candidate_state)]
    for (from_quality, to_quality, candidate_state), count in sorted(quality_counter.items()):
        total = from_totals[(from_quality, candidate_state)]
        output.append(
            {
                "section": "SETUP_STATE_TRANSITION",
                "from_state": from_quality,
                "to_state": to_quality,
                "candidate_state": candidate_state,
                "count": count,
                "from_total": total,
                "pct": pct(count, total),
            }
        )
    for (to_bucket, candidate_state), count in sorted(eligible_by_state.items()):
        total = sum(value for (bucket, state), value in eligible_by_state.items() if state == candidate_state)
        output.append(
            {
                "section": "SETUP_ELIGIBLE_NEXT_SESSION",
                "from_state": "SETUP_ELIGIBLE",
                "to_state": to_bucket,
                "candidate_state": candidate_state,
                "count": count,
                "from_total": total,
                "pct": pct(count, total),
            }
        )

    top_transitions = [
        {
            "from_state": from_state,
            "to_state": to_state,
            "candidate_state": candidate_state,
            "count": count,
        }
        for (from_state, to_state, candidate_state), count in quality_counter.most_common(20)
    ]
    summary = {
        "top_setup_state_transitions": top_transitions,
        "setup_eligible_next_session": {
            candidate_state: {
                bucket: {"count": count, "pct": pct(count, sum(v for (b, s), v in eligible_by_state.items() if s == candidate_state))}
                for (bucket, state), count in eligible_by_state.items()
                if state == candidate_state
            }
            for candidate_state in sorted({state for _bucket, state in eligible_by_state})
        },
    }
    return output, summary


def daily_churn_rows(
    rows: Sequence[dict[str, Any]],
    trading_sessions: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible_by_date: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if truthy(row.get("setup_eligible")):
            eligible_by_date[str(row.get("trading_date", ""))].add(str(row.get("symbol", "")))
    output: list[dict[str, Any]] = []
    previous: set[str] = set()
    for trading_date in trading_sessions:
        current = eligible_by_date.get(trading_date, set())
        new = current - previous
        continued = current & previous
        dropped = previous - current
        denominator = len(new | continued | dropped)
        output.append(
            {
                "trading_date": trading_date,
                "setup_eligible": len(current),
                "new_setup_eligible_today": len(new),
                "continued_setup_eligible": len(continued),
                "dropped_setup_eligible": len(dropped),
                "churn_rate_pct": pct(len(new) + len(dropped), denominator),
            }
        )
        previous = current
    churn_rates = [parse_decimal(row["churn_rate_pct"]) or Decimal("0") for row in output]
    summary = {
        "new_setup_distribution": numeric_distribution([int(row["new_setup_eligible_today"]) for row in output]),
        "continued_setup_distribution": numeric_distribution([int(row["continued_setup_eligible"]) for row in output]),
        "dropped_setup_distribution": numeric_distribution([int(row["dropped_setup_eligible"]) for row in output]),
        "churn_rate_pct_distribution": decimal_distribution(churn_rates),
    }
    return output, summary


def daily_density_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_dates = sorted({str(row.get("trading_date", "")) for row in rows})
    eligible_counter = Counter(str(row.get("trading_date", "")) for row in rows if truthy(row.get("setup_eligible")))
    counts = [eligible_counter[trading_date] for trading_date in all_dates]
    p95 = quantile_number(counts, Decimal("0.95"))
    p99 = quantile_number(counts, Decimal("0.99"))
    output = []
    for trading_date in all_dates:
        count = eligible_counter[trading_date]
        flag = ""
        if count >= p99:
            flag = "EXTREME_SETUP_DENSITY"
        elif count >= p95:
            flag = "HIGH_SETUP_DENSITY"
        output.append({"trading_date": trading_date, "setup_eligible": count, "density_flag": flag})
    top_dates = sorted(output, key=lambda row: int(row["setup_eligible"]), reverse=True)[:20]
    return output, {
        "thresholds": {"p95": p95, "p99": p99},
        "top_20_dates": top_dates,
        "distribution": numeric_distribution(counts, include_p10=True),
    }


def sensitivity_audit_rows(
    rows: Sequence[dict[str, Any]],
    baseline_config: DailySetupEvaluationConfig,
    trading_sessions: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_keys = {setup_key(row) for row in rows if truthy(row.get("setup_eligible"))}
    scenario_results: dict[str, list[dict[str, Any]]] = {}
    output: list[dict[str, Any]] = []
    for name in SCENARIO_NAMES:
        scenario_rows = rows if name == "BASELINE" else [scenario_setup_row(row, scenario_config(name, baseline_config), name) for row in rows]
        scenario_results[name] = scenario_rows
        metrics = sensitivity_metrics(name, scenario_rows, baseline_keys, trading_sessions)
        output.append(metrics)
    summary = {
        "scenarios": {row["scenario"]: row for row in output},
        "most_sensitive_by_removed_rows": max(output, key=lambda row: int(row["removed_rows"])),
        "most_sensitive_by_introduced_rows": max(output, key=lambda row: int(row["introduced_rows"])),
    }
    return output, summary


def scenario_config(name: str, baseline: DailySetupEvaluationConfig) -> DailySetupEvaluationConfig:
    if name in {"CANDLE_LOOSER", "SETUP_LOOSER_COMBINED"}:
        candle = replace(
            baseline.candle,
            poor_close_location=Decimal("0.300"),
            fair_close_location=Decimal("0.400"),
            good_close_location=Decimal("0.550"),
            strong_close_location=Decimal("0.700"),
            large_upper_wick_pct=Decimal("0.035"),
            contained_upper_wick_pct=Decimal("0.015"),
            meaningful_body_pct=Decimal("0.003"),
        )
        acceptance = baseline.acceptance
        if name == "SETUP_LOOSER_COMBINED":
            acceptance = replace(
                baseline.acceptance,
                moderate_close_location=Decimal("0.550"),
                strong_close_location=Decimal("0.700"),
                meaningful_body_pct=Decimal("0.003"),
                large_upper_wick_pct=Decimal("0.030"),
            )
            breakout = replace(baseline.breakout, close_acceptance_distance=Decimal("0.001"))
            return replace(baseline, candle=candle, acceptance=acceptance, breakout=breakout)
        return replace(baseline, candle=candle)
    if name == "CANDLE_TIGHTER":
        return replace(
            baseline,
            candle=replace(
                baseline.candle,
                poor_close_location=Decimal("0.400"),
                fair_close_location=Decimal("0.500"),
                good_close_location=Decimal("0.650"),
                strong_close_location=Decimal("0.800"),
                large_upper_wick_pct=Decimal("0.020"),
                contained_upper_wick_pct=Decimal("0.010"),
                meaningful_body_pct=Decimal("0.005"),
            ),
        )
    if name == "ACCEPTANCE_LOOSER":
        return replace(
            baseline,
            breakout=replace(baseline.breakout, close_acceptance_distance=Decimal("0.001")),
            acceptance=replace(
                baseline.acceptance,
                moderate_close_location=Decimal("0.550"),
                strong_close_location=Decimal("0.700"),
                meaningful_body_pct=Decimal("0.003"),
                large_upper_wick_pct=Decimal("0.030"),
            ),
        )
    if name == "ACCEPTANCE_TIGHTER":
        return replace(
            baseline,
            breakout=replace(baseline.breakout, close_acceptance_distance=Decimal("0.005")),
            acceptance=replace(
                baseline.acceptance,
                moderate_close_location=Decimal("0.650"),
                strong_close_location=Decimal("0.800"),
                meaningful_body_pct=Decimal("0.005"),
                large_upper_wick_pct=Decimal("0.020"),
            ),
        )
    if name == "CONSOLIDATION_LOOSER":
        return replace(
            baseline,
            consolidation=replace(
                baseline.consolidation,
                very_tight_range_20d=Decimal("0.090"),
                tight_range_20d=Decimal("0.140"),
                moderate_range_20d=Decimal("0.200"),
                loose_range_20d=Decimal("0.280"),
                strong_atr_contraction=Decimal("0.800"),
                moderate_atr_contraction=Decimal("0.980"),
                price_near_high_tolerance=Decimal("-0.050"),
            ),
        )
    if name in {"CONSOLIDATION_TIGHTER", "SETUP_CONSERVATIVE_COMBINED"}:
        consolidation = replace(
            baseline.consolidation,
            very_tight_range_20d=Decimal("0.070"),
            tight_range_20d=Decimal("0.100"),
            moderate_range_20d=Decimal("0.160"),
            loose_range_20d=Decimal("0.220"),
            strong_atr_contraction=Decimal("0.700"),
            moderate_atr_contraction=Decimal("0.900"),
            price_near_high_tolerance=Decimal("-0.030"),
        )
        if name == "SETUP_CONSERVATIVE_COMBINED":
            candle = scenario_config("CANDLE_TIGHTER", baseline).candle
            acceptance_config = scenario_config("ACCEPTANCE_TIGHTER", baseline)
            return replace(
                baseline,
                candle=candle,
                acceptance=acceptance_config.acceptance,
                breakout=acceptance_config.breakout,
                consolidation=consolidation,
            )
        return replace(baseline, consolidation=consolidation)
    if name == "EXTENSION_LOOSER":
        return replace(
            baseline,
            extension=replace(
                baseline.extension,
                extreme_return_1d_atr_multiple=Decimal("3.30"),
                extreme_return_5d_atr_multiple=Decimal("8.80"),
                extreme_sma20_distance=Decimal("0.200"),
            ),
        )
    if name == "EXTENSION_TIGHTER":
        return replace(
            baseline,
            extension=replace(
                baseline.extension,
                extreme_return_1d_atr_multiple=Decimal("2.70"),
                extreme_return_5d_atr_multiple=Decimal("7.20"),
                extreme_sma20_distance=Decimal("0.160"),
            ),
        )
    if name == "FALSE_BREAKOUT_WARNING_ONLY":
        return replace(baseline, eligibility=replace(baseline.eligibility, block_possible_false_breakout=False))
    return baseline


def scenario_setup_row(
    baseline_row: dict[str, Any],
    config: DailySetupEvaluationConfig,
    scenario_name: str,
) -> dict[str, Any]:
    values = scenario_values(baseline_row)
    breakout_state = classify_breakout_state(values, config)
    consolidation_state, consolidation_quality, _consolidation_evidence = classify_consolidation(values, config)
    volume_confirmation = classify_volume_confirmation(values, config)
    benchmark_rs_context = classify_benchmark_rs_context(values, config)
    candle_quality = classify_candle_quality(values, config)
    extension_risk = classify_extension_risk(values, config)
    false_flags = false_breakout_flags(values, breakout_state, volume_confirmation, config)
    if scenario_name == "FALSE_BREAKOUT_STRICT" and false_flags:
        false_flags.add("POSSIBLE_FALSE_BREAKOUT")
    high_52w_context = classify_52w_context(values, config)
    acceptance_state, _acceptance_evidence = classify_acceptance_state(
        values,
        breakout_state,
        volume_confirmation,
        benchmark_rs_context,
        config,
    )
    setup_flags = setup_type_flags(
        values,
        candidate_state=str(baseline_row.get("candidate_state", "")),
        breakout_state=breakout_state,
        consolidation_quality=consolidation_quality,
        benchmark_rs_context=benchmark_rs_context,
        candle_quality=candle_quality,
        extension_risk=extension_risk,
        high_52w_context=high_52w_context,
    )
    setup_eligible, setup_quality, rejection_reasons, _supporting, _warnings = derive_setup_decision(
        candidate_state=str(baseline_row.get("candidate_state", "")),
        research_status=str(baseline_row.get("setup_status", "")),
        setup_type_flags_value=setup_flags,
        breakout_state=breakout_state,
        level_quality=str(baseline_row.get("level_quality", "")),
        consolidation_quality=consolidation_quality,
        acceptance_state=acceptance_state,
        candle_quality=candle_quality,
        volume_confirmation=volume_confirmation,
        benchmark_rs_context=benchmark_rs_context,
        extension_risk=extension_risk,
        high_52w_context=high_52w_context,
        daily_level_reclaim=truthy(baseline_row.get("daily_level_reclaim")),
        false_breakout_flags_value=false_flags,
        config=config,
    )
    return {
        "trading_date": baseline_row.get("trading_date", ""),
        "symbol": baseline_row.get("symbol", ""),
        "candidate_state": baseline_row.get("candidate_state", ""),
        "both_eligible": baseline_row.get("both_eligible", ""),
        "setup_eligible": setup_eligible,
        "setup_quality": setup_quality,
        "setup_rejection_reasons": ";".join(sorted(rejection_reasons)),
        "breakout_state": breakout_state,
    }


def scenario_values(row: dict[str, Any]) -> dict[str, Any]:
    prior_high = parse_decimal(row.get("prior_high_20d"))
    high = parse_decimal(row.get("adjusted_high"))
    close = parse_decimal(row.get("adjusted_close")) or parse_decimal(row.get("price"))
    distance_20d = parse_decimal(row.get("distance_to_prior_20d_high_pct"))
    return {
        "prior_high_20d": prior_high,
        "prior_high_52w": parse_decimal(row.get("prior_high_52w")),
        "distance_to_prior_20d_high_pct": distance_20d,
        "distance_to_prior_52w_high_pct": parse_decimal(row.get("distance_to_prior_52w_high_pct")),
        "relative_volume_20d": parse_decimal(row.get("relative_volume_20d")),
        "relative_volume_5d": parse_decimal(row.get("relative_volume_5d")),
        "relative_return_5d_vs_nifty500": parse_decimal(row.get("relative_return_5d_vs_nifty500")),
        "relative_return_20d_vs_nifty500": parse_decimal(row.get("relative_return_20d_vs_nifty500")),
        "return_1d": parse_decimal(row.get("return_1d")),
        "return_5d": parse_decimal(row.get("return_5d")),
        "return_10d": parse_decimal(row.get("return_10d")),
        "atr_percent_14": parse_decimal(row.get("atr_percent_14")),
        "close_location_value": parse_decimal(row.get("close_location_value")),
        "upper_wick_pct": parse_decimal(row.get("upper_wick_pct")),
        "body_pct": parse_decimal(row.get("body_pct")),
        "range_width_5d_pct": parse_decimal(row.get("range_width_5d_pct")),
        "range_width_10d_pct": parse_decimal(row.get("range_width_10d_pct")),
        "range_width_20d_pct": parse_decimal(row.get("range_width_20d_pct")),
        "atr_contraction_ratio": parse_decimal(row.get("atr_contraction_ratio")),
        "gap_open_pct": parse_decimal(row.get("gap_open_pct")),
        "distance_from_sma_20_pct": parse_decimal(row.get("distance_from_sma_20_pct")),
        "open": parse_decimal(row.get("adjusted_open")),
        "high": high,
        "low": parse_decimal(row.get("adjusted_low")),
        "close": close,
        "price": close,
        "above_prior_20d_high": distance_20d is not None and distance_20d > 0,
        "intraday_high_above_prior_20d_high": prior_high is not None and high is not None and high > prior_high,
        "above_prior_52w_high": parse_decimal(row.get("distance_to_prior_52w_high_pct")) is not None
        and parse_decimal(row.get("distance_to_prior_52w_high_pct")) > 0,
        "candidate_extension_status": extension_status_from_risk(row.get("extension_risk")),
    }


def sensitivity_metrics(
    scenario: str,
    rows: Sequence[dict[str, Any]],
    baseline_keys: set[tuple[str, str]],
    trading_sessions: Sequence[str],
) -> dict[str, Any]:
    total = len(rows)
    eligible = [row for row in rows if truthy(row.get("setup_eligible"))]
    eligible_keys = {setup_key(row) for row in eligible}
    quality_counts = Counter(str(row.get("setup_quality", "")) for row in rows)
    emerging = [row for row in rows if row.get("candidate_state") == "EMERGING"]
    confirmed = [row for row in rows if row.get("candidate_state") == "CONFIRMED"]
    daily_counts = Counter(str(row.get("trading_date", "")) for row in eligible)
    daily_distribution = numeric_distribution(list(daily_counts.values()))
    streak_lengths_any = scenario_streak_lengths(eligible, trading_sessions)
    intersection = baseline_keys & eligible_keys
    union = baseline_keys | eligible_keys
    return {
        "scenario": scenario,
        "candidate_rows_evaluated": total,
        "setup_eligible": len(eligible),
        "pass_rate_pct": pct(len(eligible), total),
        "strong_count": quality_counts["STRONG"],
        "valid_count": quality_counts["VALID"],
        "watch_count": quality_counts["WATCH"],
        "poor_count": quality_counts["POOR"],
        "emerging_pass_rate_pct": pct(sum(1 for row in emerging if truthy(row.get("setup_eligible"))), len(emerging)),
        "confirmed_pass_rate_pct": pct(sum(1 for row in confirmed if truthy(row.get("setup_eligible"))), len(confirmed)),
        "daily_median": daily_distribution["median"],
        "daily_mean": daily_distribution["mean"],
        "daily_p90": daily_distribution["p90"],
        "daily_p95": daily_distribution["p95"],
        "daily_max": daily_distribution["max"],
        "symbols_ever_setup_eligible": len({str(row.get("symbol", "")) for row in eligible}),
        "baseline_retained_rows": len(intersection),
        "removed_rows": len(baseline_keys - eligible_keys),
        "introduced_rows": len(eligible_keys - baseline_keys),
        "jaccard_similarity": round_decimal(Decimal(len(intersection)) / Decimal(len(union)) if union else Decimal("1")),
        "median_setup_streak": statistics.median(streak_lengths_any) if streak_lengths_any else 0,
    }


def structural_stability_result(sensitivity_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    baseline = next(row for row in sensitivity_rows if row["scenario"] == "BASELINE")
    baseline_eligible = int(baseline["setup_eligible"])
    non_baseline = [row for row in sensitivity_rows if row["scenario"] != "BASELINE"]
    max_shift_pct = max(
        abs(Decimal(int(row["setup_eligible"]) - baseline_eligible)) / Decimal(baseline_eligible) * Decimal("100")
        for row in non_baseline
    )
    min_jaccard = min(Decimal(str(row["jaccard_similarity"])) for row in non_baseline)
    if max_shift_pct <= Decimal("10") and min_jaccard >= Decimal("0.85"):
        status = "STABLE"
    elif max_shift_pct <= Decimal("30") and min_jaccard >= Decimal("0.65"):
        status = "MODERATELY_SENSITIVE"
    else:
        status = "HIGHLY_SENSITIVE"
    return {
        "status": status,
        "max_setup_count_shift_pct": round_decimal(max_shift_pct),
        "min_jaccard_similarity": round_decimal(min_jaccard),
        "criteria": "STABLE <=10% max setup-count shift and Jaccard >=0.85; MODERATELY_SENSITIVE <=30% and Jaccard >=0.65; otherwise HIGHLY_SENSITIVE.",
    }


def funnel_sanity_result(funnel: dict[str, Any], candle_summary: dict[str, Any], sensitivity_summary: dict[str, Any]) -> dict[str, Any]:
    pass_rate = Decimal(str(funnel["overall_pass_rate_pct"]))
    poor_pct = Decimal(str(candle_summary["poor_pct"]))
    candle_looser = sensitivity_summary["scenarios"]["CANDLE_LOOSER"]
    baseline = sensitivity_summary["scenarios"]["BASELINE"]
    looser_shift = Decimal(int(candle_looser["setup_eligible"]) - int(baseline["setup_eligible"])) / Decimal(int(baseline["setup_eligible"])) * Decimal("100")
    if Decimal("15") <= pass_rate <= Decimal("30") and poor_pct > Decimal("55") and looser_shift <= Decimal("25"):
        status = "HEALTHY_BUT_CANDLE_STRICT"
        reason = "The pass rate is structurally selective and candle quality is strict, but loosening candle thresholds does not radically reshape the setup population."
    elif Decimal("15") <= pass_rate <= Decimal("30"):
        status = "HEALTHY"
        reason = "The candidate-to-setup pass rate is selective without obvious population explosion or collapse."
    elif pass_rate < Decimal("10"):
        status = "TOO_STRICT"
        reason = "The setup pass rate is below the audit sanity band."
    elif pass_rate > Decimal("45"):
        status = "TOO_LOOSE"
        reason = "The setup pass rate is above the audit sanity band."
    else:
        status = "INCONCLUSIVE"
        reason = "The pass rate is outside the preferred range but not extreme."
    return {
        "status": status,
        "candidate_to_setup_pass_rate_reasonable": status in {"HEALTHY", "HEALTHY_BUT_CANDLE_STRICT"},
        "poor_candle_over_restrictive": status == "HEALTHY_BUT_CANDLE_STRICT",
        "reason": reason,
        "candle_looser_setup_count_shift_pct": round_decimal(looser_shift),
    }


def write_daily_setup_audit_markdown(report: dict[str, Any], path: Path) -> None:
    funnel = report["funnel"]
    stability = report["structural_stability"]
    sanity = report["funnel_sanity"]
    dist = funnel["daily_setup_eligible_distribution"]
    lines = [
        "# Daily Setup Audit",
        "",
        "Current phase: Step 02.6 / Command 02 - setup funnel, candle semantics, persistence, and threshold sensitivity",
        "",
        "## Boundary",
        "",
        "- This is a structural audit of DAILY_SETUP_EVALUATION_V1 only.",
        "- No future returns, MFE, MAE, winner/loser labels, profitability, target-hit, stop-hit, backtesting, entry scoring, market-regime scoring, risk/reward, orders, migrations, or Supabase writes are used.",
        "- The baseline setup, candidate, and feature datasets remain unchanged.",
        "",
        "## Version",
        "",
        f"- Audit version: {report['audit']['audit_version']}",
        f"- Setup version/config hash: {report['audit']['setup_version']} / {report['audit']['setup_config_hash']}",
        f"- Candidate version/config hash: {report['audit']['candidate_version']} / {report['audit']['candidate_config_hash']}",
        f"- Feature version: {report['audit']['feature_version']}",
        "",
        "## Funnel",
        "",
        f"- Candidate rows: {funnel['candidate_rows']}",
        f"- Setup eligible: {funnel['setup_eligible']} ({funnel['overall_pass_rate_pct']}%)",
        f"- Setup rejected: {funnel['setup_rejected']}",
        f"- Quality counts: {funnel['quality_counts']}",
        f"- Emerging pass rate: {funnel['emerging_pass_rate_pct']}%",
        f"- Confirmed pass rate: {funnel['confirmed_pass_rate_pct']}%",
        f"- Per-day setup eligible: min={dist['min']}, p10={dist.get('p10')}, p25={dist.get('p25')}, median={dist['median']}, mean={dist['mean']}, p75={dist.get('p75')}, p90={dist['p90']}, p95={dist['p95']}, p99={dist.get('p99')}, max={dist['max']}",
        "",
        "## Candle Quality",
        "",
        f"- POOR candle rows: {report['candle_quality']['poor_count']} ({report['candle_quality']['poor_pct']}%)",
        f"- Top weaknesses: {report['candle_quality']['poor_reason_decomposition']}",
        f"- Top combinations: {report['candle_quality']['top_poor_weakness_combinations'][:5]}",
        "",
        "## Persistence And Sensitivity",
        "",
        f"- Structural stability: {stability['status']} ({stability['criteria']})",
        f"- Funnel sanity: {sanity['status']}. {sanity['reason']}",
        f"- Highest-density dates are in {report['outputs']['daily_density_bulk']}",
        f"- Sensitivity scenarios are in {report['outputs']['sensitivity_csv']}",
        "",
        "## Integrity And Safety",
        "",
        f"- DAILY_SETUP_EVALUATION_V1 unchanged: {report['regression']['setup_dataset_unchanged']}",
        f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['regression']['candidate_dataset_unchanged']}",
        f"- DAILY_FEATURES_V1 unchanged: {report['regression']['feature_dataset_unchanged']}",
        "- ZERO orders were placed.",
        "- ZERO remote migrations were applied.",
        "- ZERO bulk records were persisted to Supabase.",
        "",
        "## Known Limitations",
        "",
        "- Persistence and transitions describe setup-state evolution only, not price outcomes.",
        "- Sensitivity scenarios are small structural perturbations, not optimized parameters.",
        "- Daily reclaim and false-breakout warnings remain daily-EOD diagnostics, not intraday proof.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def scenario_streak_lengths(rows: Sequence[dict[str, Any]], trading_sessions: Sequence[str]) -> list[int]:
    dates_by_symbol: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        dates_by_symbol[str(row.get("symbol", ""))].append(str(row.get("trading_date", "")))
    session_index = {session: offset for offset, session in enumerate(trading_sessions)}
    lengths: list[int] = []
    for dates in dates_by_symbol.values():
        lengths.extend(streak_lengths(sorted(set(dates)), session_index))
    return lengths


def setup_dates_index(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        output[str(row.get("symbol", ""))][str(row.get("trading_date", ""))] = row
    return output


def streak_lengths(active_dates: Sequence[str], session_index: dict[str, int]) -> list[int]:
    if not active_dates:
        return []
    lengths: list[int] = []
    current = 1
    previous = active_dates[0]
    for trading_date in active_dates[1:]:
        if trading_date in session_index and previous in session_index and session_index[trading_date] == session_index[previous] + 1:
            current += 1
        else:
            lengths.append(current)
            current = 1
        previous = trading_date
    lengths.append(current)
    return lengths


def streak_distribution_row(streak_type: str, lengths: Sequence[int]) -> dict[str, Any]:
    counter = Counter()
    for length in lengths:
        if length == 1:
            counter["one_session"] += 1
        elif length == 2:
            counter["two_sessions"] += 1
        elif 3 <= length <= 5:
            counter["three_to_five"] += 1
        elif 6 <= length <= 10:
            counter["six_to_ten"] += 1
        else:
            counter["over_ten"] += 1
    return {
        "streak_type": streak_type,
        "streak_count": len(lengths),
        "one_session": counter["one_session"],
        "two_sessions": counter["two_sessions"],
        "three_to_five": counter["three_to_five"],
        "six_to_ten": counter["six_to_ten"],
        "over_ten": counter["over_ten"],
        "median": statistics.median(lengths) if lengths else 0,
        "mean": round(statistics.mean(lengths), 4) if lengths else 0,
        "p90": quantile_number(list(lengths), Decimal("0.90")) if lengths else 0,
        "p95": quantile_number(list(lengths), Decimal("0.95")) if lengths else 0,
        "max": max(lengths) if lengths else 0,
    }


def next_session_map(trading_sessions: Sequence[str]) -> dict[str, str]:
    return {trading_sessions[index]: trading_sessions[index + 1] for index in range(len(trading_sessions) - 1)}


def distribution_for_field(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    counter = Counter(str(row.get(field, "")) or "UNAVAILABLE" for row in rows)
    total = len(rows)
    return {state: {"count": count, "pct": pct(count, total)} for state, count in counter.most_common()}


def false_breakout_flag_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for row in rows:
        flags = split_codes(row.get("false_breakout_flags", ""))
        if not flags:
            counter["NO_FALSE_BREAKOUT_FLAG"] += 1
        for flag in flags:
            counter[flag] += 1
    return {flag: {"count": count, "pct": pct(count, len(rows))} for flag, count in counter.most_common()}


def decimal_distribution(values: Sequence[Decimal | None]) -> dict[str, Any]:
    clean = [value for value in values if value is not None]
    if not clean:
        return {"usable_rows": 0, "p10": "", "p25": "", "median": "", "p75": "", "p90": "", "p95": ""}
    ordered = sorted(clean)
    return {
        "usable_rows": len(clean),
        "p10": round_decimal(decimal_quantile(ordered, Decimal("0.10"))),
        "p25": round_decimal(decimal_quantile(ordered, Decimal("0.25"))),
        "median": round_decimal(decimal_quantile(ordered, Decimal("0.50"))),
        "p75": round_decimal(decimal_quantile(ordered, Decimal("0.75"))),
        "p90": round_decimal(decimal_quantile(ordered, Decimal("0.90"))),
        "p95": round_decimal(decimal_quantile(ordered, Decimal("0.95"))),
    }


def numeric_distribution(values: Sequence[int], *, include_p10: bool = False) -> dict[str, Any]:
    if not values:
        output = {"min": 0, "p25": 0, "median": 0, "mean": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
        if include_p10:
            output["p10"] = 0
        return output
    ordered = sorted(values)
    output = distribution(values) | {
        "p25": quantile_number(ordered, Decimal("0.25")),
        "p75": quantile_number(ordered, Decimal("0.75")),
        "p99": quantile_number(ordered, Decimal("0.99")),
    }
    if include_p10:
        output["p10"] = quantile_number(ordered, Decimal("0.10"))
    return output


def group_rows_by(rows: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, "")) or "UNAVAILABLE"].append(row)
    return dict(grouped)


def setup_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("trading_date", "")), str(row.get("symbol", "")))


def observed_single_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def parse_date_value(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def extension_status_from_risk(value: Any) -> str:
    return {
        "LOW": "NORMAL",
        "MODERATE": "ELEVATED",
        "HIGH": "EXTENDED",
        "EXTREME": "EXTREME",
    }.get(str(value or "").upper(), "")


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0

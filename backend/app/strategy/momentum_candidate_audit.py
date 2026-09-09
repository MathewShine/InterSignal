from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.services.daily_feature_engine import json_safe, parse_date, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.candidate_config import (
    BreakoutContextRules,
    LiquidityRules,
    MomentumCandidateConfig,
    MomentumEvidenceRules,
    RelativeVolumeRules,
)
from app.strategy.momentum_candidates import (
    evaluate_candidate_row,
    file_sha256,
    open_csv_maybe_gzip,
)

MOMENTUM_CANDIDATE_AUDIT_VERSION = "MOMENTUM_CANDIDATE_AUDIT_V1"
STATES = ("EMERGING", "CONFIRMED", "REJECTED", "UNAVAILABLE")
CANDIDATE_STATES = {"EMERGING", "CONFIRMED"}
SENSITIVITY_FIELDS = [
    "scenario",
    "scenario_type",
    "audit_version",
    "candidate_version",
    "candidate_config_hash",
    "evaluated_rows",
    "evaluable_rows",
    "emerging_count",
    "confirmed_count",
    "both_eligible_count",
    "total_candidate_count",
    "candidate_rate_pct",
    "daily_candidate_median",
    "daily_candidate_mean",
    "daily_candidate_p90",
    "daily_candidate_p95",
    "daily_candidate_max",
    "symbols_ever_selected",
    "median_candidate_streak_length",
    "p95_candidate_streak_length",
    "emerging_to_confirmed_5_session_conversion_rate_pct",
    "baseline_candidate_rows_retained",
    "baseline_rows_removed",
    "new_rows_introduced",
    "jaccard_similarity",
    "emerging_overlap",
    "confirmed_overlap",
    "stability_status",
    "config_changes",
]
DAILY_DISTRIBUTION_FIELDS = [
    "trading_date",
    "universe_count",
    "evaluable_count",
    "unavailable_count",
    "rejected_count",
    "emerging_primary_count",
    "confirmed_primary_count",
    "emerging_eligible_count",
    "confirmed_eligible_count",
    "both_eligible_count",
    "total_candidate_count",
    "candidate_rate_pct",
    "emerging_rate_pct",
    "confirmed_rate_pct",
    "rolling_5_candidate_avg",
    "rolling_20_candidate_avg",
    "candidate_density_flag",
    "candidate_density_band",
]
STREAK_FIELDS = [
    "streak_type",
    "symbol",
    "start_date",
    "end_date",
    "trading_sessions",
    "initial_state",
    "final_state",
    "max_state_strength",
]
TRANSITION_FIELDS = [
    "symbol",
    "from_date",
    "to_date",
    "from_state",
    "to_state",
    "from_emerging_eligible",
    "from_confirmed_eligible",
    "to_emerging_eligible",
    "to_confirmed_eligible",
]
SYMBOL_FREQUENCY_FIELDS = [
    "symbol",
    "total_rows",
    "eligible_historical_days",
    "total_candidate_days",
    "emerging_days",
    "confirmed_days",
    "both_eligible_days",
    "candidate_streaks",
    "longest_streak",
    "candidate_pct_of_eligible_days",
]
STATE_AGE_FIELDS = [
    "trading_date",
    "symbol",
    "candidate_state",
    "any_candidate_state_age",
    "emerging_state_age",
    "confirmed_state_age",
]
CHURN_FIELDS = [
    "trading_date",
    "new_candidates_today",
    "continued_candidates",
    "dropped_candidates",
    "candidate_churn_rate_pct",
    "new_emerging_today",
    "continued_emerging",
    "dropped_emerging",
    "emerging_churn_rate_pct",
    "new_confirmed_today",
    "continued_confirmed",
    "dropped_confirmed",
    "confirmed_churn_rate_pct",
]
TRANSITION_MATRIX_FIELDS = ["from_state", "to_state", "count", "from_state_total", "percent"]
STREAK_SUMMARY_FIELDS = [
    "streak_type",
    "streak_count",
    "one_session",
    "two_sessions",
    "three_to_five_sessions",
    "six_to_ten_sessions",
    "eleven_to_twenty_sessions",
    "over_twenty_sessions",
    "median",
    "mean",
    "p90",
    "p95",
    "max",
]
PERIOD_SUMMARY_FIELDS = [
    "period_type",
    "period",
    "sessions",
    "total_candidate_days",
    "avg_candidate_count",
    "median_candidate_count",
    "p95_candidate_count",
    "max_candidate_count",
    "avg_candidate_rate_pct",
    "density_band",
]


@dataclass(frozen=True, slots=True)
class MomentumCandidateAuditConfig:
    data_dir: Path
    start_date: date | None = None
    end_date: date | None = None
    baseline_config: MomentumCandidateConfig = MomentumCandidateConfig()
    audit_version: str = MOMENTUM_CANDIDATE_AUDIT_VERSION

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "momentum_candidates" / "v1"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def daily_distribution_path(self) -> Path:
        return self.audit_dir / "candidate_daily_distribution.csv.gz"

    @property
    def streaks_path(self) -> Path:
        return self.audit_dir / "candidate_streaks.csv.gz"

    @property
    def transitions_path(self) -> Path:
        return self.audit_dir / "candidate_transitions.csv.gz"

    @property
    def symbol_frequency_path(self) -> Path:
        return self.audit_dir / "candidate_symbol_frequency.csv.gz"

    @property
    def sensitivity_scenarios_path(self) -> Path:
        return self.audit_dir / "candidate_sensitivity_scenarios.csv.gz"

    @property
    def state_age_path(self) -> Path:
        return self.audit_dir / "candidate_state_age.csv.gz"

    @property
    def churn_path(self) -> Path:
        return self.audit_dir / "candidate_churn.csv.gz"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_audit_summary.json"

    @property
    def sensitivity_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_sensitivity.csv"

    @property
    def transition_matrix_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_transition_matrix.csv"

    @property
    def streak_summary_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_streak_summary.csv"

    @property
    def period_summary_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_period_summary.csv"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    scenario_type: str
    config: MomentumCandidateConfig
    config_changes: str


def build_momentum_candidate_audit(
    *,
    config: MomentumCandidateAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    baseline_candidate_hash_before = file_sha256(config.candidate_dataset_path)
    feature_hash_before = file_sha256(config.feature_dataset_path)

    if progress:
        progress("Loading MOMENTUM_CANDIDATES_V1 baseline rows")
    candidate_rows = load_candidate_rows(config.candidate_dataset_path, start_date=config.start_date, end_date=config.end_date)
    rows_by_date = group_rows_by(candidate_rows, "trading_date")
    sessions = sorted(rows_by_date)
    session_index = {session: offset for offset, session in enumerate(sessions)}

    if progress:
        progress("Building baseline distribution, streak, transition, and churn audits")
    daily_distribution = daily_distribution_rows(rows_by_date)
    attach_density_flags(daily_distribution)
    streak_rows = candidate_streak_rows(candidate_rows, session_index)
    state_age_rows = candidate_state_age_rows(candidate_rows, session_index)
    transition_rows = candidate_transition_rows(candidate_rows, session_index)
    transition_matrix = transition_matrix_rows(transition_rows)
    streak_summary = streak_summary_rows(streak_rows)
    symbol_frequency = symbol_frequency_rows(candidate_rows, streak_rows)
    churn_rows = candidate_churn_rows(rows_by_date)
    period_summary = period_summary_rows(daily_distribution)
    progression = emerging_to_confirmed_progression(candidate_rows, session_index)
    confirmed_persistence = confirmed_persistence_summary(candidate_rows, session_index)
    evidence = evidence_distribution_summary(candidate_rows)
    composition = composition_summary(candidate_rows)
    distribution_summary = baseline_distribution_summary(daily_distribution)
    concentration = concentration_summary(symbol_frequency, daily_distribution)
    churn_summary = churn_distribution_summary(churn_rows)
    sanity = funnel_sanity_status(
        daily_distribution=daily_distribution,
        composition=composition,
        streak_summary=streak_summary,
        churn_summary=churn_summary,
    )

    if progress:
        progress("Loading DAILY_FEATURES_V1 rows for sensitivity scenarios")
    feature_records = load_feature_records(
        feature_dataset_path=config.feature_dataset_path,
        baseline_candidate_rows=candidate_rows,
        start_date=config.start_date,
        end_date=config.end_date,
    )

    if progress:
        progress("Running controlled threshold sensitivity scenarios")
    scenarios = sensitivity_scenarios(config.baseline_config)
    sensitivity_rows = run_sensitivity_scenarios(
        feature_records=feature_records,
        scenarios=scenarios,
        sessions=sessions,
        session_index=session_index,
        baseline_rows=candidate_rows,
        audit_version=config.audit_version,
        progress=progress,
    )
    stability = parameter_stability_assessment(sensitivity_rows)

    write_gzip_csv(config.daily_distribution_path, daily_distribution, DAILY_DISTRIBUTION_FIELDS)
    write_gzip_csv(config.streaks_path, streak_rows, STREAK_FIELDS)
    write_gzip_csv(config.transitions_path, transition_rows, TRANSITION_FIELDS)
    write_gzip_csv(config.symbol_frequency_path, symbol_frequency, SYMBOL_FREQUENCY_FIELDS)
    write_gzip_csv(config.sensitivity_scenarios_path, sensitivity_rows, SENSITIVITY_FIELDS)
    write_gzip_csv(config.state_age_path, state_age_rows, STATE_AGE_FIELDS)
    write_gzip_csv(config.churn_path, churn_rows, CHURN_FIELDS)
    write_csv(config.sensitivity_path, sensitivity_rows, SENSITIVITY_FIELDS)
    write_csv(config.transition_matrix_path, transition_matrix, TRANSITION_MATRIX_FIELDS)
    write_csv(config.streak_summary_path, streak_summary, STREAK_SUMMARY_FIELDS)
    write_csv(config.period_summary_path, period_summary, PERIOD_SUMMARY_FIELDS)

    baseline_candidate_hash_after = file_sha256(config.candidate_dataset_path)
    feature_hash_after = file_sha256(config.feature_dataset_path)
    report = {
        "phase": "Step 02.5",
        "command": "Command 02",
        "generated_at": generated_at,
        "audit": {
            "audit_version": config.audit_version,
            "candidate_version": config.baseline_config.candidate_version,
            "candidate_config_hash": config.baseline_config.config_hash(),
            "feature_version": "DAILY_FEATURES_V1",
            "methodology": "Structural candidate-funnel audit only; no future returns, MFE, MAE, hit labels, profitability optimization, backtesting, or entry/exit logic.",
        },
        "baseline": {
            "candidate_dataset_path": str(config.candidate_dataset_path),
            "candidate_dataset_sha256_before": baseline_candidate_hash_before,
            "candidate_dataset_sha256_after": baseline_candidate_hash_after,
            "candidate_dataset_unchanged": baseline_candidate_hash_before == baseline_candidate_hash_after,
            "feature_dataset_path": str(config.feature_dataset_path),
            "feature_dataset_sha256_before": feature_hash_before,
            "feature_dataset_sha256_after": feature_hash_after,
            "feature_dataset_unchanged": feature_hash_before == feature_hash_after,
            "row_count": len(candidate_rows),
            "date_count": len(sessions),
            "first_date": sessions[0] if sessions else "",
            "last_date": sessions[-1] if sessions else "",
            "distribution": distribution_summary,
            "composition": composition,
        },
        "candidate_explosion": candidate_explosion_summary(daily_distribution),
        "streaks": {
            "summary": {row["streak_type"]: row for row in streak_summary},
            "top_streaks": sorted(streak_rows, key=lambda row: int(row["trading_sessions"]), reverse=True)[:20],
        },
        "concentration": concentration,
        "transitions": {
            "matrix": transition_matrix,
            "summary": transition_summary(transition_matrix),
        },
        "emerging_to_confirmed_progression": progression,
        "confirmed_persistence": confirmed_persistence,
        "period_concentration": {
            "summary": period_summary,
            "highest_density_periods": sorted(
                period_summary,
                key=lambda row: (Decimal(str(row["avg_candidate_count"])), Decimal(str(row["max_candidate_count"]))),
                reverse=True,
            )[:20],
        },
        "churn": churn_summary,
        "evidence_distributions": evidence,
        "sensitivity": {
            "scenarios": sensitivity_rows,
            "parameter_stability_assessment": stability,
            "emerging_rvol_1_20_vs_1_30": scenario_comparison(
                sensitivity_rows,
                baseline_name="BASELINE",
                scenario_name="RVOL_EMERGING_1_30",
                count_field="emerging_count",
            ),
            "liquidity_5_10_20cr": {
                "LIQUIDITY_5CR": find_scenario(sensitivity_rows, "LIQUIDITY_5CR"),
                "BASELINE_10CR": find_scenario(sensitivity_rows, "BASELINE"),
                "LIQUIDITY_20CR": find_scenario(sensitivity_rows, "LIQUIDITY_20CR"),
            },
        },
        "funnel_sanity": sanity,
        "safety": {
            "future_outcome_fields_used": 0,
            "future_return_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "entry_scores_generated": 0,
            "risk_reward_calculated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "baseline_thresholds_changed": False,
        },
        "outputs": {
            "daily_distribution": str(config.daily_distribution_path),
            "streaks": str(config.streaks_path),
            "transitions": str(config.transitions_path),
            "symbol_frequency": str(config.symbol_frequency_path),
            "sensitivity_scenarios": str(config.sensitivity_scenarios_path),
            "state_age": str(config.state_age_path),
            "churn": str(config.churn_path),
            "summary_json": str(config.summary_path),
            "sensitivity_csv": str(config.sensitivity_path),
            "transition_matrix_csv": str(config.transition_matrix_path),
            "streak_summary_csv": str(config.streak_summary_path),
            "period_summary_csv": str(config.period_summary_path),
            "markdown": "docs/momentum-candidate-audit.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        report["baseline"]["candidate_dataset_unchanged"]
        and report["baseline"]["feature_dataset_unchanged"]
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def load_candidate_rows(path: Path, *, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            row_date = parse_date(row.get("trading_date", ""))
            if row_date is None:
                continue
            if start_date is not None and row_date < start_date:
                continue
            if end_date is not None and row_date > end_date:
                continue
            row["symbol"] = canonical_symbol(row.get("symbol", ""))
            rows.append(row)
    return rows


def load_feature_records(
    *,
    feature_dataset_path: Path,
    baseline_candidate_rows: Sequence[dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    price_by_key = {
        (row["trading_date"], row["symbol"]): parse_decimal(row.get("price"))
        for row in baseline_candidate_rows
    }
    records: list[dict[str, Any]] = []
    with open_csv_maybe_gzip(feature_dataset_path) as file:
        for row in csv.DictReader(file):
            row_date = parse_date(row.get("trading_date", ""))
            if row_date is None:
                continue
            if start_date is not None and row_date < start_date:
                continue
            if end_date is not None and row_date > end_date:
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            compact = {field: row.get(field, "") for field in feature_fields_for_classification()}
            compact["symbol"] = symbol
            compact["trading_date"] = row.get("trading_date", "")
            compact["_price"] = price_by_key.get((compact["trading_date"], symbol))
            records.append(compact)
    return records


def feature_fields_for_classification() -> tuple[str, ...]:
    return (
        "trading_date",
        "symbol",
        "isin",
        "universe_name",
        "universe_membership_status",
        "universe_membership_confidence",
        "universe_version",
        "feature_version",
        "benchmark_context_version",
        "sector_context_version",
        "adjustment_methodology",
        "exclusion_policy",
        "availability_time",
        "decision_input_time",
        "timeframe",
        "series",
        "feature_status",
        "feature_null_reasons",
        "return_1d",
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "relative_volume_5d",
        "relative_volume_20d",
        "up_days_ratio_10",
        "up_days_ratio_20",
        "median_traded_value_20d",
        "atr_percent_14",
        "relative_return_5d_vs_nifty500",
        "relative_return_20d_vs_nifty500",
        "prior_high_20d",
        "distance_to_prior_20d_high_pct",
        "distance_from_sma_20_pct",
        "above_prior_20d_high",
        "above_prior_52w_high",
        "intraday_high_above_prior_20d_high",
        "sector_mapping_status",
    )


def daily_distribution_rows(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rolling_counts: list[int] = []
    for trading_date in sorted(rows_by_date):
        group = rows_by_date[trading_date]
        universe_count = len(group)
        evaluable_count = sum(1 for row in group if truthy(row.get("mandatory_gates_passed")))
        unavailable_count = sum(1 for row in group if row.get("candidate_state") == "UNAVAILABLE")
        rejected_count = sum(1 for row in group if row.get("candidate_state") == "REJECTED")
        emerging_primary_count = sum(1 for row in group if row.get("candidate_state") == "EMERGING")
        confirmed_primary_count = sum(1 for row in group if row.get("candidate_state") == "CONFIRMED")
        emerging_eligible_count = sum(1 for row in group if truthy(row.get("emerging_eligible")))
        confirmed_eligible_count = sum(1 for row in group if truthy(row.get("confirmed_eligible")))
        both_eligible_count = sum(1 for row in group if truthy(row.get("both_eligible")))
        total_candidate_count = emerging_primary_count + confirmed_primary_count
        rolling_counts.append(total_candidate_count)
        rows.append(
            {
                "trading_date": trading_date,
                "universe_count": universe_count,
                "evaluable_count": evaluable_count,
                "unavailable_count": unavailable_count,
                "rejected_count": rejected_count,
                "emerging_primary_count": emerging_primary_count,
                "confirmed_primary_count": confirmed_primary_count,
                "emerging_eligible_count": emerging_eligible_count,
                "confirmed_eligible_count": confirmed_eligible_count,
                "both_eligible_count": both_eligible_count,
                "total_candidate_count": total_candidate_count,
                "candidate_rate_pct": pct(total_candidate_count, universe_count),
                "emerging_rate_pct": pct(emerging_primary_count, universe_count),
                "confirmed_rate_pct": pct(confirmed_primary_count, universe_count),
                "rolling_5_candidate_avg": round(statistics.mean(rolling_counts[-5:]), 4),
                "rolling_20_candidate_avg": round(statistics.mean(rolling_counts[-20:]), 4),
                "candidate_density_flag": "",
                "candidate_density_band": "",
            }
        )
    return rows


def attach_density_flags(rows: list[dict[str, Any]]) -> None:
    counts = [int(row["total_candidate_count"]) for row in rows]
    p10 = quantile_number(counts, Decimal("0.10"))
    p75 = quantile_number(counts, Decimal("0.75"))
    p95 = quantile_number(counts, Decimal("0.95"))
    p99 = quantile_number(counts, Decimal("0.99"))
    for row in rows:
        count = int(row["total_candidate_count"])
        if count > p99:
            row["candidate_density_flag"] = "EXTREME_CANDIDATE_DENSITY"
        elif count > p95:
            row["candidate_density_flag"] = "HIGH_CANDIDATE_DENSITY"
        if count <= p10:
            row["candidate_density_band"] = "SPARSE"
        elif count <= p75:
            row["candidate_density_band"] = "NORMAL"
        elif count <= p95:
            row["candidate_density_band"] = "DENSE"
        else:
            row["candidate_density_band"] = "EXTREME"


def candidate_streak_rows(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows_by_symbol = group_rows_by(candidate_rows, "symbol")
    specs: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
        ("ANY_CANDIDATE_STREAK", lambda row: row.get("candidate_state") in CANDIDATE_STATES),
        ("EMERGING_STREAK", lambda row: row.get("candidate_state") == "EMERGING"),
        ("CONFIRMED_STREAK", lambda row: row.get("candidate_state") == "CONFIRMED"),
    )
    for streak_type, predicate in specs:
        for symbol, symbol_rows in rows_by_symbol.items():
            active: list[dict[str, Any]] = []
            previous_index: int | None = None
            for row in sorted(symbol_rows, key=lambda item: session_index[item["trading_date"]]):
                current_index = session_index[row["trading_date"]]
                consecutive = previous_index is not None and current_index == previous_index + 1
                if not consecutive or not predicate(row):
                    if active:
                        rows.append(streak_output_row(streak_type, symbol, active))
                        active = []
                if predicate(row):
                    active.append(row)
                previous_index = current_index
            if active:
                rows.append(streak_output_row(streak_type, symbol, active))
    return rows


def streak_output_row(streak_type: str, symbol: str, active: Sequence[dict[str, Any]]) -> dict[str, Any]:
    max_state_strength = "CONFIRMED" if any(row.get("candidate_state") == "CONFIRMED" for row in active) else "EMERGING"
    return {
        "streak_type": streak_type,
        "symbol": symbol,
        "start_date": active[0]["trading_date"],
        "end_date": active[-1]["trading_date"],
        "trading_sessions": len(active),
        "initial_state": active[0]["candidate_state"],
        "final_state": active[-1]["candidate_state"],
        "max_state_strength": max_state_strength,
    }


def candidate_state_age_rows(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _symbol, symbol_rows in group_rows_by(candidate_rows, "symbol").items():
        any_age = emerging_age = confirmed_age = 0
        previous_index: int | None = None
        for row in sorted(symbol_rows, key=lambda item: session_index[item["trading_date"]]):
            current_index = session_index[row["trading_date"]]
            if previous_index is None or current_index != previous_index + 1:
                any_age = emerging_age = confirmed_age = 0
            state = row.get("candidate_state")
            any_age = any_age + 1 if state in CANDIDATE_STATES else 0
            emerging_age = emerging_age + 1 if state == "EMERGING" else 0
            confirmed_age = confirmed_age + 1 if state == "CONFIRMED" else 0
            if state in CANDIDATE_STATES:
                rows.append(
                    {
                        "trading_date": row["trading_date"],
                        "symbol": row["symbol"],
                        "candidate_state": state,
                        "any_candidate_state_age": any_age,
                        "emerging_state_age": emerging_age,
                        "confirmed_state_age": confirmed_age,
                    }
                )
            previous_index = current_index
    return rows


def candidate_transition_rows(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _symbol, symbol_rows in group_rows_by(candidate_rows, "symbol").items():
        ordered = sorted(symbol_rows, key=lambda item: session_index[item["trading_date"]])
        for previous, current in zip(ordered, ordered[1:]):
            if session_index[current["trading_date"]] != session_index[previous["trading_date"]] + 1:
                continue
            rows.append(
                {
                    "symbol": current["symbol"],
                    "from_date": previous["trading_date"],
                    "to_date": current["trading_date"],
                    "from_state": previous["candidate_state"],
                    "to_state": current["candidate_state"],
                    "from_emerging_eligible": truthy(previous.get("emerging_eligible")),
                    "from_confirmed_eligible": truthy(previous.get("confirmed_eligible")),
                    "to_emerging_eligible": truthy(current.get("emerging_eligible")),
                    "to_confirmed_eligible": truthy(current.get("confirmed_eligible")),
                }
            )
    return rows


def transition_matrix_rows(transition_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((row["from_state"], row["to_state"]) for row in transition_rows)
    totals = Counter(row["from_state"] for row in transition_rows)
    rows: list[dict[str, Any]] = []
    for from_state in STATES:
        for to_state in STATES:
            count = counts[(from_state, to_state)]
            rows.append(
                {
                    "from_state": from_state,
                    "to_state": to_state,
                    "count": count,
                    "from_state_total": totals[from_state],
                    "percent": pct(count, totals[from_state]),
                }
            )
    return rows


def streak_summary_rows(streak_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for streak_type in ("ANY_CANDIDATE_STREAK", "EMERGING_STREAK", "CONFIRMED_STREAK"):
        lengths = [int(row["trading_sessions"]) for row in streak_rows if row["streak_type"] == streak_type]
        rows.append(
            {
                "streak_type": streak_type,
                "streak_count": len(lengths),
                "one_session": sum(1 for value in lengths if value == 1),
                "two_sessions": sum(1 for value in lengths if value == 2),
                "three_to_five_sessions": sum(1 for value in lengths if 3 <= value <= 5),
                "six_to_ten_sessions": sum(1 for value in lengths if 6 <= value <= 10),
                "eleven_to_twenty_sessions": sum(1 for value in lengths if 11 <= value <= 20),
                "over_twenty_sessions": sum(1 for value in lengths if value > 20),
                **numeric_distribution(lengths, include_quartiles=False),
            }
        )
    return rows


def symbol_frequency_rows(candidate_rows: Sequence[dict[str, Any]], streak_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    longest_by_symbol: Counter[str] = Counter()
    streak_count_by_symbol: Counter[str] = Counter()
    for row in streak_rows:
        if row["streak_type"] != "ANY_CANDIDATE_STREAK":
            continue
        symbol = row["symbol"]
        streak_count_by_symbol[symbol] += 1
        longest_by_symbol[symbol] = max(longest_by_symbol[symbol], int(row["trading_sessions"]))

    rows: list[dict[str, Any]] = []
    for symbol, symbol_rows in group_rows_by(candidate_rows, "symbol").items():
        total_rows = len(symbol_rows)
        eligible_days = sum(1 for row in symbol_rows if row.get("candidate_state") != "UNAVAILABLE")
        candidate_days = sum(1 for row in symbol_rows if row.get("candidate_state") in CANDIDATE_STATES)
        rows.append(
            {
                "symbol": symbol,
                "total_rows": total_rows,
                "eligible_historical_days": eligible_days,
                "total_candidate_days": candidate_days,
                "emerging_days": sum(1 for row in symbol_rows if row.get("candidate_state") == "EMERGING"),
                "confirmed_days": sum(1 for row in symbol_rows if row.get("candidate_state") == "CONFIRMED"),
                "both_eligible_days": sum(1 for row in symbol_rows if truthy(row.get("both_eligible"))),
                "candidate_streaks": streak_count_by_symbol[symbol],
                "longest_streak": longest_by_symbol[symbol],
                "candidate_pct_of_eligible_days": pct(candidate_days, eligible_days),
            }
        )
    rows.sort(key=lambda row: (int(row["total_candidate_days"]), int(row["longest_streak"]), row["symbol"]), reverse=True)
    return rows


def candidate_churn_rows(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_any: set[str] = set()
    previous_emerging: set[str] = set()
    previous_confirmed: set[str] = set()
    for trading_date in sorted(rows_by_date):
        group = rows_by_date[trading_date]
        current_any = {row["symbol"] for row in group if row.get("candidate_state") in CANDIDATE_STATES}
        current_emerging = {row["symbol"] for row in group if row.get("candidate_state") == "EMERGING"}
        current_confirmed = {row["symbol"] for row in group if row.get("candidate_state") == "CONFIRMED"}
        any_stats = churn_counts(current_any, previous_any)
        emerging_stats = churn_counts(current_emerging, previous_emerging)
        confirmed_stats = churn_counts(current_confirmed, previous_confirmed)
        rows.append(
            {
                "trading_date": trading_date,
                "new_candidates_today": any_stats["new"],
                "continued_candidates": any_stats["continued"],
                "dropped_candidates": any_stats["dropped"],
                "candidate_churn_rate_pct": any_stats["churn_rate_pct"],
                "new_emerging_today": emerging_stats["new"],
                "continued_emerging": emerging_stats["continued"],
                "dropped_emerging": emerging_stats["dropped"],
                "emerging_churn_rate_pct": emerging_stats["churn_rate_pct"],
                "new_confirmed_today": confirmed_stats["new"],
                "continued_confirmed": confirmed_stats["continued"],
                "dropped_confirmed": confirmed_stats["dropped"],
                "confirmed_churn_rate_pct": confirmed_stats["churn_rate_pct"],
            }
        )
        previous_any = current_any
        previous_emerging = current_emerging
        previous_confirmed = current_confirmed
    return rows


def churn_counts(current: set[str], previous: set[str]) -> dict[str, Any]:
    new_count = len(current - previous)
    continued = len(current & previous)
    dropped = len(previous - current)
    relevant_pool = len(current | previous)
    return {
        "new": new_count,
        "continued": continued,
        "dropped": dropped,
        "churn_rate_pct": pct(new_count + dropped, relevant_pool),
    }


def emerging_to_confirmed_progression(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> dict[str, Any]:
    horizons = (1, 2, 3, 5, 10)
    events = [row for row in candidate_rows if truthy(row.get("emerging_eligible"))]
    already_both = [row for row in events if truthy(row.get("both_eligible"))]
    pool = [row for row in events if not truthy(row.get("both_eligible"))]
    rows_by_symbol = group_rows_by(candidate_rows, "symbol")
    by_symbol_date = {(row["symbol"], row["trading_date"]): row for row in candidate_rows}
    dates_by_symbol = {
        symbol: {row["trading_date"] for row in rows}
        for symbol, rows in rows_by_symbol.items()
    }
    sessions_by_index = {index: session for session, index in session_index.items()}
    conversions = {}
    for horizon in horizons:
        converted = 0
        for row in pool:
            symbol = row["symbol"]
            base_index = session_index[row["trading_date"]]
            symbol_dates = dates_by_symbol[symbol]
            found = False
            for offset in range(1, horizon + 1):
                next_date = sessions_by_index.get(base_index + offset)
                if next_date is None or next_date not in symbol_dates:
                    continue
                future_row = by_symbol_date[(symbol, next_date)]
                if truthy(future_row.get("confirmed_eligible")) or future_row.get("candidate_state") == "CONFIRMED":
                    found = True
                    break
            if found:
                converted += 1
        conversions[f"within_{horizon}_sessions"] = {
            "converted": converted,
            "pool": len(pool),
            "rate_pct": pct(converted, len(pool)),
        }
    return {
        "emerging_eligible_events": len(events),
        "already_both_eligible_events": len(already_both),
        "later_conversion_pool": len(pool),
        "conversions": conversions,
    }


def confirmed_persistence_summary(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> dict[str, Any]:
    rows_by_symbol = group_rows_by(candidate_rows, "symbol")
    next_state_counts: Counter[str] = Counter()
    confirmed_events = 0
    no_next = 0
    for _symbol, symbol_rows in rows_by_symbol.items():
        ordered = sorted(symbol_rows, key=lambda row: session_index[row["trading_date"]])
        for previous, current in zip(ordered, ordered[1:]):
            if previous.get("candidate_state") != "CONFIRMED":
                continue
            confirmed_events += 1
            if session_index[current["trading_date"]] == session_index[previous["trading_date"]] + 1:
                next_state_counts[current["candidate_state"]] += 1
            else:
                no_next += 1
        if ordered and ordered[-1].get("candidate_state") == "CONFIRMED":
            confirmed_events += 1
            no_next += 1
    total_with_next = sum(next_state_counts.values())
    return {
        "confirmed_events": confirmed_events,
        "events_with_next_session": total_with_next,
        "no_next_or_nonconsecutive": no_next,
        "remains_confirmed_next_session": next_state_counts["CONFIRMED"],
        "drops_to_emerging_next_session": next_state_counts["EMERGING"],
        "becomes_rejected_next_session": next_state_counts["REJECTED"],
        "becomes_unavailable_next_session": next_state_counts["UNAVAILABLE"],
        "remains_confirmed_pct": pct(next_state_counts["CONFIRMED"], total_with_next),
        "drops_to_emerging_pct": pct(next_state_counts["EMERGING"], total_with_next),
        "becomes_rejected_pct": pct(next_state_counts["REJECTED"], total_with_next),
        "becomes_unavailable_pct": pct(next_state_counts["UNAVAILABLE"], total_with_next),
    }


def evidence_distribution_summary(candidate_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "relative_volume_20d",
        "relative_return_5d_vs_nifty500",
        "relative_return_20d_vs_nifty500",
        "distance_to_prior_20d_high_pct",
        "up_days_ratio_10",
        "up_days_ratio_20",
        "atr_percent_14",
        "median_traded_value_20d",
    )
    summary: dict[str, Any] = {}
    for state in ("EMERGING", "CONFIRMED"):
        state_rows = [row for row in candidate_rows if row.get("candidate_state") == state]
        summary[state] = {
            field: quantile_summary([parse_decimal(row.get(field)) for row in state_rows])
            for field in fields
        }
    return summary


def composition_summary(candidate_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(candidate_rows)
    primary_emerging = sum(1 for row in candidate_rows if row.get("candidate_state") == "EMERGING")
    primary_confirmed = sum(1 for row in candidate_rows if row.get("candidate_state") == "CONFIRMED")
    emerging_eligible = sum(1 for row in candidate_rows if truthy(row.get("emerging_eligible")))
    confirmed_eligible = sum(1 for row in candidate_rows if truthy(row.get("confirmed_eligible")))
    both = sum(1 for row in candidate_rows if truthy(row.get("both_eligible")))
    total_candidates = primary_emerging + primary_confirmed
    return {
        "total_rows": total,
        "total_candidates": total_candidates,
        "emerging_only_rows": emerging_eligible - both,
        "confirmed_only_rows": confirmed_eligible - both,
        "both_eligible_rows": both,
        "primary_emerging_rows": primary_emerging,
        "primary_confirmed_rows": primary_confirmed,
        "emerging_only_pct_of_candidates": pct(emerging_eligible - both, total_candidates),
        "confirmed_only_pct_of_candidates": pct(confirmed_eligible - both, total_candidates),
        "both_eligible_pct_of_candidates": pct(both, total_candidates),
        "primary_emerging_pct_of_candidates": pct(primary_emerging, total_candidates),
        "primary_confirmed_pct_of_candidates": pct(primary_confirmed, total_candidates),
        "confirmed_selectivity_ratio_vs_emerging_primary": round(primary_emerging / primary_confirmed, 4) if primary_confirmed else None,
        "interpretation": composition_interpretation(primary_emerging, primary_confirmed, both, total_candidates),
    }


def composition_interpretation(primary_emerging: int, primary_confirmed: int, both: int, total_candidates: int) -> dict[str, Any]:
    confirmed_selective = primary_confirmed < primary_emerging * Decimal("0.50")
    both_dominates = total_candidates > 0 and both / total_candidates > 0.50
    emerging_overwhelms = total_candidates > 0 and primary_emerging / total_candidates > 0.85
    return {
        "confirmed_meaningfully_more_selective": bool(confirmed_selective),
        "both_eligible_dominates_unexpectedly": both_dominates,
        "emerging_overwhelms_funnel": emerging_overwhelms,
    }


def baseline_distribution_summary(daily_distribution: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        "all_candidates": "total_candidate_count",
        "emerging": "emerging_primary_count",
        "confirmed": "confirmed_primary_count",
        "both_eligible": "both_eligible_count",
    }
    return {
        label: numeric_distribution([int(row[field]) for row in daily_distribution])
        for label, field in metrics.items()
    }


def concentration_summary(symbol_frequency: Sequence[dict[str, Any]], daily_distribution: Sequence[dict[str, Any]]) -> dict[str, Any]:
    candidate_days = [int(row["total_candidate_days"]) for row in symbol_frequency]
    high_density_dates = [
        {
            "trading_date": row["trading_date"],
            "total_candidate_count": row["total_candidate_count"],
            "candidate_rate_pct": row["candidate_rate_pct"],
            "candidate_density_flag": row["candidate_density_flag"],
            "candidate_density_band": row["candidate_density_band"],
        }
        for row in daily_distribution
        if row["candidate_density_flag"]
    ]
    return {
        "top_20_symbols": list(symbol_frequency[:20]),
        "candidate_frequency_distribution": numeric_distribution(candidate_days),
        "high_density_dates": high_density_dates,
    }


def candidate_explosion_summary(daily_distribution: Sequence[dict[str, Any]]) -> dict[str, Any]:
    flags = Counter(row["candidate_density_flag"] for row in daily_distribution if row["candidate_density_flag"])
    return {
        "flag_counts": dict(flags),
        "dates": [
            {
                "trading_date": row["trading_date"],
                "total_candidate_count": row["total_candidate_count"],
                "candidate_rate_pct": row["candidate_rate_pct"],
                "flag": row["candidate_density_flag"],
            }
            for row in daily_distribution
            if row["candidate_density_flag"]
        ],
    }


def transition_summary(matrix_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(row["from_state"], row["to_state"]): row for row in matrix_rows}
    return {
        "emerging_to_emerging": lookup[("EMERGING", "EMERGING")],
        "emerging_to_confirmed": lookup[("EMERGING", "CONFIRMED")],
        "emerging_to_rejected": lookup[("EMERGING", "REJECTED")],
        "confirmed_to_confirmed": lookup[("CONFIRMED", "CONFIRMED")],
        "confirmed_to_emerging": lookup[("CONFIRMED", "EMERGING")],
        "confirmed_to_rejected": lookup[("CONFIRMED", "REJECTED")],
        "rejected_to_emerging": lookup[("REJECTED", "EMERGING")],
        "rejected_to_confirmed": lookup[("REJECTED", "CONFIRMED")],
    }


def period_summary_rows(daily_distribution: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period_type, key_func in (
        ("YEAR", lambda value: value[:4]),
        ("QUARTER", lambda value: f"{value[:4]}-Q{((int(value[5:7]) - 1) // 3) + 1}"),
        ("MONTH", lambda value: value[:7]),
    ):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in daily_distribution:
            grouped[key_func(row["trading_date"])].append(row)
        for period, period_rows in sorted(grouped.items()):
            counts = [int(row["total_candidate_count"]) for row in period_rows]
            rates = [Decimal(str(row["candidate_rate_pct"])) for row in period_rows]
            bands = Counter(row["candidate_density_band"] for row in period_rows)
            rows.append(
                {
                    "period_type": period_type,
                    "period": period,
                    "sessions": len(period_rows),
                    "total_candidate_days": sum(counts),
                    "avg_candidate_count": round(statistics.mean(counts), 4) if counts else 0,
                    "median_candidate_count": statistics.median(counts) if counts else 0,
                    "p95_candidate_count": quantile_number(counts, Decimal("0.95")),
                    "max_candidate_count": max(counts) if counts else 0,
                    "avg_candidate_rate_pct": round_decimal(sum(rates, Decimal("0")) / Decimal(len(rates))) if rates else "0",
                    "density_band": bands.most_common(1)[0][0] if bands else "",
                }
            )
    return rows


def churn_distribution_summary(churn_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_churn_rate_pct": quantile_summary([Decimal(str(row["candidate_churn_rate_pct"])) for row in churn_rows]),
        "new_candidates_today": numeric_distribution([int(row["new_candidates_today"]) for row in churn_rows]),
        "continued_candidates": numeric_distribution([int(row["continued_candidates"]) for row in churn_rows]),
        "dropped_candidates": numeric_distribution([int(row["dropped_candidates"]) for row in churn_rows]),
        "emerging_churn_rate_pct": quantile_summary([Decimal(str(row["emerging_churn_rate_pct"])) for row in churn_rows]),
        "confirmed_churn_rate_pct": quantile_summary([Decimal(str(row["confirmed_churn_rate_pct"])) for row in churn_rows]),
    }


def funnel_sanity_status(
    *,
    daily_distribution: Sequence[dict[str, Any]],
    composition: dict[str, Any],
    streak_summary: Sequence[dict[str, Any]],
    churn_summary: dict[str, Any],
) -> dict[str, Any]:
    candidate_rates = [Decimal(str(row["candidate_rate_pct"])) for row in daily_distribution]
    median_rate = decimal_quantile(candidate_rates, Decimal("0.50"))
    p95_rate = decimal_quantile(candidate_rates, Decimal("0.95"))
    confirmed_pct = Decimal(str(composition["primary_confirmed_pct_of_candidates"]))
    churn_median = Decimal(str(churn_summary["candidate_churn_rate_pct"]["median"]))
    any_streak = next(row for row in streak_summary if row["streak_type"] == "ANY_CANDIDATE_STREAK")

    status = "HEALTHY"
    reasons: list[str] = []
    if median_rate > Decimal("35") or p95_rate > Decimal("55"):
        status = "HEALTHY_WITH_HIGH_BREADTH"
        reasons.append("Candidate breadth is high in dense periods but not structurally explosive.")
    if median_rate > Decimal("45"):
        status = "TOO_BROAD"
        reasons.append("Median candidate rate is above the broadness guardrail.")
    if median_rate < Decimal("3") and confirmed_pct < Decimal("5"):
        status = "TOO_SPARSE"
        reasons.append("Median candidate rate and confirmed share are both very low.")
    if churn_median > Decimal("85"):
        status = "UNSTABLE"
        reasons.append("Median daily churn is very high.")
    if not reasons:
        reasons.append("Median breadth, confirmed selectivity, streak profile, and churn are within structural audit guardrails.")
    return {
        "status": status,
        "criteria": {
            "median_candidate_rate_pct": round_decimal(median_rate),
            "p95_candidate_rate_pct": round_decimal(p95_rate),
            "confirmed_pct_of_candidates": composition["primary_confirmed_pct_of_candidates"],
            "median_churn_rate_pct": churn_summary["candidate_churn_rate_pct"]["median"],
            "any_candidate_median_streak": any_streak["median"],
            "guardrails": "TOO_BROAD if median rate > 45%; TOO_SPARSE if median rate < 3% and confirmed share < 5%; UNSTABLE if median churn > 85%.",
        },
        "reasons": reasons,
    }


def sensitivity_scenarios(baseline: MomentumCandidateConfig) -> list[Scenario]:
    return [
        Scenario("BASELINE", "BASELINE", baseline, "No threshold changes."),
        Scenario(
            "RVOL_EMERGING_1_25",
            "RELATIVE_VOLUME",
            replace(baseline, relative_volume=replace(baseline.relative_volume, emerging_threshold=Decimal("1.25"))),
            "Emerging relative volume 1.20 -> 1.25.",
        ),
        Scenario(
            "RVOL_EMERGING_1_30",
            "RELATIVE_VOLUME",
            replace(baseline, relative_volume=replace(baseline.relative_volume, emerging_threshold=Decimal("1.30"))),
            "Emerging relative volume 1.20 -> 1.30.",
        ),
        Scenario(
            "RVOL_CONFIRMED_1_40",
            "RELATIVE_VOLUME",
            replace(baseline, relative_volume=replace(baseline.relative_volume, confirmed_threshold=Decimal("1.40"))),
            "Confirmed relative volume 1.50 -> 1.40.",
        ),
        Scenario(
            "RVOL_CONFIRMED_1_60",
            "RELATIVE_VOLUME",
            replace(baseline, relative_volume=replace(baseline.relative_volume, confirmed_threshold=Decimal("1.60"))),
            "Confirmed relative volume 1.50 -> 1.60.",
        ),
        Scenario(
            "LIQUIDITY_5CR",
            "LIQUIDITY",
            replace(
                baseline,
                liquidity=LiquidityRules(
                    median_traded_value_20d_min=Decimal("50000000"),
                    description="20-day median traded value must be at least INR 5 crore per day.",
                ),
            ),
            "Liquidity threshold 10 crore -> 5 crore.",
        ),
        Scenario(
            "LIQUIDITY_20CR",
            "LIQUIDITY",
            replace(
                baseline,
                liquidity=LiquidityRules(
                    median_traded_value_20d_min=Decimal("200000000"),
                    description="20-day median traded value must be at least INR 20 crore per day.",
                ),
            ),
            "Liquidity threshold 10 crore -> 20 crore.",
        ),
        Scenario("MOMENTUM_LOOSER", "MOMENTUM", replace(baseline, momentum=looser_momentum(baseline.momentum)), "Small looser perturbation of baseline momentum thresholds."),
        Scenario("MOMENTUM_STRICTER", "MOMENTUM", replace(baseline, momentum=stricter_momentum(baseline.momentum)), "Small stricter perturbation of baseline momentum thresholds."),
        Scenario(
            "HIGH_PROXIMITY_LOOSER",
            "HIGH_PROXIMITY",
            replace(baseline, breakout=BreakoutContextRules(testing_20d_high_distance=Decimal("-0.015"), approaching_20d_high_distance=Decimal("-0.060"))),
            "20d-high proximity looser: testing -1.5%, approaching -6.0%.",
        ),
        Scenario(
            "HIGH_PROXIMITY_TIGHTER",
            "HIGH_PROXIMITY",
            replace(baseline, breakout=BreakoutContextRules(testing_20d_high_distance=Decimal("-0.005"), approaching_20d_high_distance=Decimal("-0.030"))),
            "20d-high proximity tighter: testing -0.5%, approaching -3.0%.",
        ),
        Scenario(
            "CONSERVATIVE_COMBINED",
            "COMBINED",
            replace(
                baseline,
                relative_volume=RelativeVolumeRules(emerging_threshold=Decimal("1.30"), confirmed_threshold=Decimal("1.60")),
                momentum=stricter_momentum(baseline.momentum),
                breakout=BreakoutContextRules(testing_20d_high_distance=Decimal("-0.005"), approaching_20d_high_distance=Decimal("-0.030")),
            ),
            "Emerging RVOL 1.30, Confirmed RVOL 1.60, stricter momentum, tighter high proximity; liquidity remains 10 crore.",
        ),
    ]


def looser_momentum(momentum: MomentumEvidenceRules) -> MomentumEvidenceRules:
    return replace(
        momentum,
        emerging_min_return_3d=Decimal("0.003"),
        emerging_min_return_5d=Decimal("0.012"),
        emerging_min_return_10d=Decimal("-0.015"),
        emerging_min_up_days_ratio_10=Decimal("0.45"),
        confirmed_min_return_5d=Decimal("0.020"),
        confirmed_min_return_10d=Decimal("0.035"),
        confirmed_min_return_20d=Decimal("0.050"),
        confirmed_min_up_days_ratio_10=Decimal("0.55"),
        confirmed_min_up_days_ratio_20=Decimal("0.50"),
    )


def stricter_momentum(momentum: MomentumEvidenceRules) -> MomentumEvidenceRules:
    return replace(
        momentum,
        emerging_min_return_3d=Decimal("0.007"),
        emerging_min_return_5d=Decimal("0.020"),
        emerging_min_return_10d=Decimal("0.000"),
        emerging_min_up_days_ratio_10=Decimal("0.55"),
        confirmed_min_return_5d=Decimal("0.030"),
        confirmed_min_return_10d=Decimal("0.050"),
        confirmed_min_return_20d=Decimal("0.070"),
        confirmed_min_up_days_ratio_10=Decimal("0.65"),
        confirmed_min_up_days_ratio_20=Decimal("0.60"),
    )


def run_sensitivity_scenarios(
    *,
    feature_records: Sequence[dict[str, Any]],
    scenarios: Sequence[Scenario],
    sessions: Sequence[str],
    session_index: dict[str, int],
    baseline_rows: Sequence[dict[str, Any]],
    audit_version: str,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    baseline_candidate_keys = row_key_set(baseline_rows, candidate_only=True)
    baseline_emerging_keys = row_key_set(baseline_rows, state="EMERGING")
    baseline_confirmed_keys = row_key_set(baseline_rows, state="CONFIRMED")
    baseline_rows_by_date = group_rows_by(baseline_rows, "trading_date")
    baseline_daily_counts = [
        sum(1 for row in baseline_rows_by_date.get(session, []) if row.get("candidate_state") in CANDIDATE_STATES)
        for session in sessions
    ]
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        if progress:
            progress(f"Sensitivity scenario {scenario.name}")
        state_rows: list[dict[str, Any]] = []
        daily_counts_by_date: Counter[str] = Counter()
        evaluated = 0
        evaluable = 0
        state_counts: Counter[str] = Counter()
        both_eligible_count = 0
        candidate_keys: set[tuple[str, str]] = set()
        emerging_keys: set[tuple[str, str]] = set()
        confirmed_keys: set[tuple[str, str]] = set()
        for record in feature_records:
            row = evaluate_candidate_row(record, config=scenario.config, price=record.get("_price"))
            evaluated += 1
            state = row["candidate_state"]
            symbol = row["symbol"]
            trading_date = row["trading_date"]
            state_counts[state] += 1
            if row.get("mandatory_gates_passed"):
                evaluable += 1
            if row.get("both_eligible"):
                both_eligible_count += 1
            if state in CANDIDATE_STATES:
                candidate_keys.add((trading_date, symbol))
                daily_counts_by_date[trading_date] += 1
            if state == "EMERGING":
                emerging_keys.add((trading_date, symbol))
            if state == "CONFIRMED":
                confirmed_keys.add((trading_date, symbol))
            state_rows.append(
                {
                    "trading_date": trading_date,
                    "symbol": symbol,
                    "candidate_state": state,
                    "emerging_eligible": row["emerging_eligible"],
                    "confirmed_eligible": row["confirmed_eligible"],
                    "both_eligible": row["both_eligible"],
                    "mandatory_gates_passed": row["mandatory_gates_passed"],
                }
            )
        daily_counts = [daily_counts_by_date[session] for session in sessions]
        any_lengths = any_candidate_streak_lengths(state_rows, session_index)
        progression = emerging_to_confirmed_progression(state_rows, session_index)
        total_candidates = len(candidate_keys)
        overlap = len(candidate_keys & baseline_candidate_keys)
        union_count = len(candidate_keys | baseline_candidate_keys)
        scenario_row = {
            "scenario": scenario.name,
            "scenario_type": scenario.scenario_type,
            "audit_version": audit_version,
            "candidate_version": scenario.config.candidate_version,
            "candidate_config_hash": scenario.config.config_hash(),
            "evaluated_rows": evaluated,
            "evaluable_rows": evaluable,
            "emerging_count": state_counts["EMERGING"],
            "confirmed_count": state_counts["CONFIRMED"],
            "both_eligible_count": both_eligible_count,
            "total_candidate_count": total_candidates,
            "candidate_rate_pct": pct(total_candidates, evaluated),
            "daily_candidate_median": statistics.median(daily_counts) if daily_counts else 0,
            "daily_candidate_mean": round(statistics.mean(daily_counts), 4) if daily_counts else 0,
            "daily_candidate_p90": quantile_number(daily_counts, Decimal("0.90")),
            "daily_candidate_p95": quantile_number(daily_counts, Decimal("0.95")),
            "daily_candidate_max": max(daily_counts) if daily_counts else 0,
            "symbols_ever_selected": len({symbol for _trading_date, symbol in candidate_keys}),
            "median_candidate_streak_length": statistics.median(any_lengths) if any_lengths else 0,
            "p95_candidate_streak_length": quantile_number(any_lengths, Decimal("0.95")),
            "emerging_to_confirmed_5_session_conversion_rate_pct": progression["conversions"]["within_5_sessions"]["rate_pct"],
            "baseline_candidate_rows_retained": overlap,
            "baseline_rows_removed": len(baseline_candidate_keys - candidate_keys),
            "new_rows_introduced": len(candidate_keys - baseline_candidate_keys),
            "jaccard_similarity": round_decimal(Decimal(overlap) / Decimal(union_count)) if union_count else "0",
            "emerging_overlap": len(emerging_keys & baseline_emerging_keys),
            "confirmed_overlap": len(confirmed_keys & baseline_confirmed_keys),
            "stability_status": scenario_stability_status(
                baseline_count=len(baseline_candidate_keys),
                scenario_count=total_candidates,
                jaccard=Decimal(overlap) / Decimal(union_count) if union_count else Decimal("0"),
                baseline_daily_counts=baseline_daily_counts,
                scenario_daily_counts=daily_counts,
            ),
            "config_changes": scenario.config_changes,
        }
        rows.append(scenario_row)
    return rows


def any_candidate_streak_lengths(candidate_rows: Sequence[dict[str, Any]], session_index: dict[str, int]) -> list[int]:
    lengths: list[int] = []
    for _symbol, symbol_rows in group_rows_by(candidate_rows, "symbol").items():
        active_length = 0
        previous_index: int | None = None
        for row in sorted(symbol_rows, key=lambda item: session_index[item["trading_date"]]):
            current_index = session_index[row["trading_date"]]
            if previous_index is None or current_index != previous_index + 1 or row.get("candidate_state") not in CANDIDATE_STATES:
                if active_length:
                    lengths.append(active_length)
                active_length = 0
            if row.get("candidate_state") in CANDIDATE_STATES:
                active_length += 1
            previous_index = current_index
        if active_length:
            lengths.append(active_length)
    return lengths


def parameter_stability_assessment(sensitivity_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    non_baseline = [row for row in sensitivity_rows if row["scenario"] != "BASELINE"]
    status_counts = Counter(row["stability_status"] for row in non_baseline)
    if status_counts["HIGHLY_SENSITIVE"]:
        status = "HIGHLY_SENSITIVE"
    elif status_counts["MODERATELY_SENSITIVE"]:
        status = "MODERATELY_SENSITIVE"
    else:
        status = "STABLE"
    return {
        "status": status,
        "criteria": "Stable if count shift <=10%, Jaccard >=0.85, and p95 daily count shift <=10%; moderate if count shift <=25% and Jaccard >=0.70; otherwise highly sensitive.",
        "scenario_status_counts": dict(status_counts),
    }


def scenario_stability_status(
    *,
    baseline_count: int,
    scenario_count: int,
    jaccard: Decimal,
    baseline_daily_counts: Sequence[int],
    scenario_daily_counts: Sequence[int],
) -> str:
    count_shift = abs(Decimal(scenario_count - baseline_count) / Decimal(baseline_count)) if baseline_count else Decimal("0")
    baseline_p95 = Decimal(quantile_number(baseline_daily_counts, Decimal("0.95")))
    scenario_p95 = Decimal(quantile_number(scenario_daily_counts, Decimal("0.95")))
    p95_shift = abs((scenario_p95 - baseline_p95) / baseline_p95) if baseline_p95 else Decimal("0")
    if count_shift <= Decimal("0.10") and jaccard >= Decimal("0.85") and p95_shift <= Decimal("0.10"):
        return "STABLE"
    if count_shift <= Decimal("0.25") and jaccard >= Decimal("0.70"):
        return "MODERATELY_SENSITIVE"
    return "HIGHLY_SENSITIVE"


def scenario_comparison(
    rows: Sequence[dict[str, Any]],
    *,
    baseline_name: str,
    scenario_name: str,
    count_field: str,
) -> dict[str, Any]:
    baseline = find_scenario(rows, baseline_name)
    scenario = find_scenario(rows, scenario_name)
    baseline_count = Decimal(str(baseline[count_field]))
    scenario_count = Decimal(str(scenario[count_field]))
    reduction = baseline_count - scenario_count
    return {
        "baseline": baseline_name,
        "scenario": scenario_name,
        "absolute_change": int(scenario_count - baseline_count),
        "absolute_reduction": int(reduction),
        "percentage_reduction": round_decimal(reduction / baseline_count * Decimal("100")) if baseline_count else "0",
        "confirmed_impact": int(scenario["confirmed_count"]) - int(baseline["confirmed_count"]),
        "median_candidates_per_day_change": Decimal(str(scenario["daily_candidate_median"])) - Decimal(str(baseline["daily_candidate_median"])),
        "p95_candidates_per_day_change": int(scenario["daily_candidate_p95"]) - int(baseline["daily_candidate_p95"]),
        "jaccard_similarity": scenario["jaccard_similarity"],
        "median_streak_change": Decimal(str(scenario["median_candidate_streak_length"])) - Decimal(str(baseline["median_candidate_streak_length"])),
        "emerging_to_confirmed_5_session_conversion_rate_change_pct": Decimal(str(scenario["emerging_to_confirmed_5_session_conversion_rate_pct"])) - Decimal(str(baseline["emerging_to_confirmed_5_session_conversion_rate_pct"])),
    }


def find_scenario(rows: Sequence[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(row for row in rows if row["scenario"] == name)


def row_key_set(rows: Sequence[dict[str, Any]], *, candidate_only: bool = False, state: str | None = None) -> set[tuple[str, str]]:
    selected: set[tuple[str, str]] = set()
    for row in rows:
        if candidate_only and row.get("candidate_state") not in CANDIDATE_STATES:
            continue
        if state is not None and row.get("candidate_state") != state:
            continue
        selected.add((row["trading_date"], row["symbol"]))
    return selected


def numeric_distribution(values: Sequence[int], *, include_quartiles: bool = True) -> dict[str, Any]:
    if not values:
        base = {"min": 0, "median": 0, "mean": 0, "p90": 0, "p95": 0, "max": 0}
        if include_quartiles:
            return {"min": 0, "p10": 0, "p25": 0, "median": 0, "mean": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
        return base
    ordered = sorted(values)
    result = {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "mean": round(statistics.mean(ordered), 4),
        "p90": quantile_number(ordered, Decimal("0.90")),
        "p95": quantile_number(ordered, Decimal("0.95")),
        "max": ordered[-1],
    }
    if include_quartiles:
        result = {
            "min": ordered[0],
            "p10": quantile_number(ordered, Decimal("0.10")),
            "p25": quantile_number(ordered, Decimal("0.25")),
            "median": result["median"],
            "mean": result["mean"],
            "p75": quantile_number(ordered, Decimal("0.75")),
            "p90": result["p90"],
            "p95": result["p95"],
            "p99": quantile_number(ordered, Decimal("0.99")),
            "max": ordered[-1],
        }
    return result


def quantile_summary(values: Sequence[Decimal | None]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"p10": "", "p25": "", "median": "", "p75": "", "p90": "", "p95": "", "usable_rows": 0}
    return {
        "p10": round_decimal(decimal_quantile(clean, Decimal("0.10"))),
        "p25": round_decimal(decimal_quantile(clean, Decimal("0.25"))),
        "median": round_decimal(decimal_quantile(clean, Decimal("0.50"))),
        "p75": round_decimal(decimal_quantile(clean, Decimal("0.75"))),
        "p90": round_decimal(decimal_quantile(clean, Decimal("0.90"))),
        "p95": round_decimal(decimal_quantile(clean, Decimal("0.95"))),
        "usable_rows": len(clean),
    }


def quantile_number(values: Sequence[int], percentile: Decimal) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[min(index, len(ordered) - 1)]


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return ordered[min(index, len(ordered) - 1)]


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def round_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() == "true" if not isinstance(value, bool) else value


def group_rows_by(rows: Sequence[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key, ""))].append(row)
    return dict(grouped)


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def output_size(config: MomentumCandidateAuditConfig) -> int:
    paths = [
        config.daily_distribution_path,
        config.streaks_path,
        config.transitions_path,
        config.symbol_frequency_path,
        config.sensitivity_scenarios_path,
        config.state_age_path,
        config.churn_path,
        config.summary_path,
        config.sensitivity_path,
        config.transition_matrix_path,
        config.streak_summary_path,
        config.period_summary_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())


def write_momentum_candidate_audit_markdown(report: dict[str, Any], path: Path) -> None:
    baseline = report["baseline"]
    composition = baseline["composition"]
    distribution = baseline["distribution"]
    progression = report["emerging_to_confirmed_progression"]["conversions"]
    confirmed = report["confirmed_persistence"]
    sensitivity = report["sensitivity"]["scenarios"]
    top_symbols = report["concentration"]["top_20_symbols"][:10]
    lines = [
        "# Momentum Candidate Audit",
        "",
        "Current phase: Step 02.5 / Command 02 - structural candidate funnel audit",
        "",
        "## Boundary",
        "",
        "- This audit uses candidate states and same-day features only.",
        "- It does not use future returns, MFE, MAE, winner/loser labels, target hits, stop hits, profitability optimization, entry scores, risk/reward, position sizing, backtesting, live feeds, orders, migrations, or Supabase persistence.",
        "- MOMENTUM_CANDIDATES_V1 thresholds remain unchanged.",
        "",
        "## Version",
        "",
        f"- Audit methodology: {report['audit']['audit_version']}",
        f"- Candidate methodology: {report['audit']['candidate_version']}",
        f"- Candidate config hash: {report['audit']['candidate_config_hash']}",
        f"- Baseline candidate hash unchanged: {baseline['candidate_dataset_unchanged']}",
        f"- Feature hash unchanged: {baseline['feature_dataset_unchanged']}",
        "",
        "## Baseline Distribution",
        "",
    ]
    for label, stats in distribution.items():
        lines.append(f"- {label}: min={stats['min']}, p10={stats['p10']}, p25={stats['p25']}, median={stats['median']}, mean={stats['mean']}, p75={stats['p75']}, p90={stats['p90']}, p95={stats['p95']}, p99={stats['p99']}, max={stats['max']}")
    lines.extend(
        [
            "",
            "## Composition",
            "",
            f"- Emerging-only rows: {composition['emerging_only_rows']} ({composition['emerging_only_pct_of_candidates']}% of candidates)",
            f"- Confirmed-only rows: {composition['confirmed_only_rows']} ({composition['confirmed_only_pct_of_candidates']}% of candidates)",
            f"- Both-eligible rows: {composition['both_eligible_rows']} ({composition['both_eligible_pct_of_candidates']}% of candidates)",
            f"- Primary Emerging rows: {composition['primary_emerging_rows']} ({composition['primary_emerging_pct_of_candidates']}% of candidates)",
            f"- Primary Confirmed rows: {composition['primary_confirmed_rows']} ({composition['primary_confirmed_pct_of_candidates']}% of candidates)",
            "",
            "## Persistence",
            "",
        ]
    )
    for _kind, summary in report["streaks"]["summary"].items():
        lines.append(f"- {summary['streak_type']}: count={summary['streak_count']}, median={summary['median']}, mean={summary['mean']}, p90={summary['p90']}, p95={summary['p95']}, max={summary['max']}")
    lines.extend(["", "## Transitions", ""])
    for name, row in report["transitions"]["summary"].items():
        lines.append(f"- {name}: {row['count']} ({row['percent']}%)")
    lines.extend(
        [
            "",
            "## Emerging To Confirmed",
            "",
            f"- Emerging eligible events: {report['emerging_to_confirmed_progression']['emerging_eligible_events']}",
            f"- Already both-eligible events: {report['emerging_to_confirmed_progression']['already_both_eligible_events']}",
            f"- Later-conversion pool: {report['emerging_to_confirmed_progression']['later_conversion_pool']}",
        ]
    )
    for horizon, row in progression.items():
        lines.append(f"- {horizon}: {row['converted']} / {row['pool']} ({row['rate_pct']}%)")
    lines.extend(
        [
            "",
            "## Confirmed Persistence",
            "",
            f"- Remains Confirmed next session: {confirmed['remains_confirmed_next_session']} ({confirmed['remains_confirmed_pct']}%)",
            f"- Drops to Emerging next session: {confirmed['drops_to_emerging_next_session']} ({confirmed['drops_to_emerging_pct']}%)",
            f"- Becomes Rejected next session: {confirmed['becomes_rejected_next_session']} ({confirmed['becomes_rejected_pct']}%)",
            f"- Becomes Unavailable next session: {confirmed['becomes_unavailable_next_session']} ({confirmed['becomes_unavailable_pct']}%)",
            "",
            "## Concentration",
            "",
        ]
    )
    for row in top_symbols:
        lines.append(f"- {row['symbol']}: {row['total_candidate_days']} candidate days, longest streak {row['longest_streak']}, {row['candidate_pct_of_eligible_days']}% of eligible days")
    lines.extend(["", "## Churn", ""])
    churn = report["churn"]
    lines.append(f"- Candidate churn rate median={churn['candidate_churn_rate_pct']['median']}%, p90={churn['candidate_churn_rate_pct']['p90']}%, p95={churn['candidate_churn_rate_pct']['p95']}%.")
    lines.extend(["", "## Evidence Distributions", ""])
    for state, fields in report["evidence_distributions"].items():
        lines.append(f"- {state}: return_5d median={fields['return_5d']['median']}, return_20d median={fields['return_20d']['median']}, relative_volume_20d median={fields['relative_volume_20d']['median']}, distance_to_prior_20d_high_pct median={fields['distance_to_prior_20d_high_pct']['median']}.")
    lines.extend(["", "## Sensitivity", ""])
    for row in sensitivity:
        lines.append(f"- {row['scenario']}: candidates={row['total_candidate_count']}, emerging={row['emerging_count']}, confirmed={row['confirmed_count']}, median/day={row['daily_candidate_median']}, p95/day={row['daily_candidate_p95']}, Jaccard={row['jaccard_similarity']}, stability={row['stability_status']}")
    lines.extend(
        [
            "",
            "## Funnel Sanity",
            "",
            f"- Final structural status: {report['funnel_sanity']['status']}",
        ]
    )
    for reason in report["funnel_sanity"]["reasons"]:
        lines.append(f"- {reason}")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Summary JSON: {report['outputs']['summary_json']}",
            f"- Sensitivity CSV: {report['outputs']['sensitivity_csv']}",
            f"- Transition matrix CSV: {report['outputs']['transition_matrix_csv']}",
            f"- Streak summary CSV: {report['outputs']['streak_summary_csv']}",
            f"- Period summary CSV: {report['outputs']['period_summary_csv']}",
            f"- Bulk audit directory: {Path(report['outputs']['streaks']).parent}",
            "",
            "## Known Limitations",
            "",
            "- Membership remains partial-history/uncertain metadata inherited from upstream features.",
            "- Sector context remains metadata only because historical sector-relative features were not point-in-time verified upstream.",
            "- Conversion analysis is candidate-state progression only, not financial outcome analysis.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

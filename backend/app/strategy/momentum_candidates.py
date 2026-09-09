from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.services.corporate_actions import fingerprint_directory
from app.services.daily_feature_engine import (
    adjusted_daily_files,
    date_from_adjusted_path,
    json_safe,
    parse_date,
    read_csv_iter,
    write_csv,
    write_json,
)
from app.services.nifty500_membership import canonical_symbol
from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig

CANDIDATE_OUTPUT_FIELDS = [
    "trading_date",
    "symbol",
    "isin",
    "universe_name",
    "membership_status",
    "membership_confidence",
    "universe_version",
    "feature_version",
    "candidate_version",
    "candidate_config_hash",
    "benchmark_context_version",
    "sector_context_version",
    "adjustment_methodology",
    "exclusion_policy",
    "availability_time",
    "decision_input_time",
    "timeframe",
    "research_eligible",
    "eligibility_status",
    "mandatory_gates_passed",
    "rejection_reasons",
    "candidate_state",
    "emerging_eligible",
    "confirmed_eligible",
    "both_eligible",
    "emerging_rank",
    "emerging_percentile",
    "confirmed_rank",
    "confirmed_percentile",
    "candidate_rank_metric",
    "candidate_rank_components",
    "price",
    "price_range_status",
    "cash_equity_status",
    "median_traded_value_20d",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "relative_volume_5d",
    "relative_volume_20d",
    "up_days_ratio_10",
    "up_days_ratio_20",
    "relative_return_5d_vs_nifty500",
    "relative_return_20d_vs_nifty500",
    "prior_high_20d",
    "distance_to_prior_20d_high_pct",
    "above_prior_20d_high",
    "intraday_high_above_prior_20d_high",
    "atr_percent_14",
    "extension_status",
    "breakout_context",
    "volatility_context",
    "sector_context_status",
    "candidate_evidence_count",
    "candidate_strength_descriptor",
    "emerging_evidence",
    "confirmed_evidence",
    "warning_flags",
]

DAILY_COUNT_FIELDS = [
    "trading_date",
    "universe_count",
    "evaluable_count",
    "rejected_count",
    "emerging_count",
    "confirmed_count",
    "both_eligible_count",
    "unavailable_count",
    "median_candidate_return_5d",
    "median_relative_volume_20d",
    "median_benchmark_relative_strength",
]

REJECTION_SUMMARY_FIELDS = ["reason_code", "count"]
PILOT_VALIDATION_FIELDS = [
    "symbol",
    "trading_date",
    "candidate_state",
    "check_name",
    "observed",
    "threshold_or_rule",
    "result",
    "explanation",
]

RESEARCH_UNAVAILABLE_REASONS = {
    "CORPORATE_ACTION_BLOCKED",
    "INSUFFICIENT_HISTORY",
    "MISSING_REQUIRED_FEATURE",
    "MISSING_LIQUIDITY_HISTORY",
    "MISSING_PRICE",
    "NON_STANDARD_SERIES",
    "NOT_IN_POINT_IN_TIME_UNIVERSE",
}


@dataclass(frozen=True, slots=True)
class MomentumCandidateEngineConfig:
    data_dir: Path
    start_date: date
    end_date: date
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    full_generation: bool = True

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.data_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def raw_daily_dir(self) -> Path:
        return self.data_dir / "raw" / "nse" / "daily"

    @property
    def candidates_dir(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1"

    @property
    def candidate_dataset_path(self) -> Path:
        return self.candidates_dir / "momentum_candidates_v1.csv.gz"

    @property
    def pilot_dataset_path(self) -> Path:
        return self.candidates_dir / "momentum_candidates_v1_pilot.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_summary.json"

    @property
    def daily_counts_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_daily_counts.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_pilot_validation.csv"

    @property
    def rejection_summary_path(self) -> Path:
        return self.reports_dir / "momentum_candidate_rejection_summary.csv"


def build_momentum_candidate_engine(
    *,
    config: MomentumCandidateEngineConfig,
    progress: Any | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    raw_before = fingerprint_directory(config.raw_daily_dir)
    adjusted_before = fingerprint_directory(config.adjusted_daily_dir)
    feature_before = file_sha256(config.feature_dataset_path)

    if progress:
        progress("Loading adjusted close price lookup")
    price_lookup = load_adjusted_close_lookup(
        adjusted_daily_dir=config.adjusted_daily_dir,
        start_date=config.start_date,
        end_date=config.end_date,
    )

    if progress:
        progress("Evaluating DAILY_FEATURES_V1 rows")
    rows_by_date, input_summary = evaluate_feature_dataset(config=config, price_lookup=price_lookup)

    if progress:
        progress("Assigning same-date cross-sectional ranks")
    rank_candidate_rows_by_date(rows_by_date)
    all_rows = flatten_by_date(rows_by_date)

    daily_counts = daily_count_rows(rows_by_date)
    write_csv(config.daily_counts_path, daily_counts, DAILY_COUNT_FIELDS)
    rejection_summary = rejection_summary_rows(all_rows)
    write_csv(config.rejection_summary_path, rejection_summary, REJECTION_SUMMARY_FIELDS)

    pilot_rows = select_pilot_rows(all_rows)
    write_candidate_rows(config.pilot_dataset_path, pilot_rows)
    pilot_validation = validate_pilot_rows(pilot_rows, config.candidate_config)
    write_csv(config.pilot_validation_path, pilot_validation["rows"], PILOT_VALIDATION_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_validation["passed"]:
        if progress:
            progress("Writing full historical candidate dataset")
        write_candidate_rows(config.candidate_dataset_path, all_rows)
        full_generation_completed = True

    feature_after = file_sha256(config.feature_dataset_path)
    raw_after = fingerprint_directory(config.raw_daily_dir)
    adjusted_after = fingerprint_directory(config.adjusted_daily_dir)
    generation = generation_summary(all_rows, daily_counts)
    report = {
        "phase": "Step 02.5",
        "command": "Command 01",
        "generated_at": generated_at,
        "candidate_engine": {
            "candidate_version": config.candidate_config.candidate_version,
            "candidate_config_hash": config.candidate_config.config_hash(),
            "input_feature_version": "DAILY_FEATURES_V1",
            "output_format": "compressed CSV",
            "dataset_path": str(config.candidate_dataset_path),
            "pilot_dataset_path": str(config.pilot_dataset_path),
        },
        "config_snapshot": config.candidate_config.snapshot(),
        "methodology": {
            "boundary": "Research candidates only; not buy/sell entries.",
            "candidate_states": ["EMERGING", "CONFIRMED", "REJECTED", "UNAVAILABLE"],
            "primary_benchmark": config.candidate_config.primary_benchmark_id,
            "ranking": "Same-date cross-sectional component percentiles; separate Emerging and Confirmed ranks.",
            "sector_policy": "Sector context is metadata only unless point-in-time verified by upstream features.",
        },
        "pilot": {
            "row_count": len(pilot_rows),
            "validation_passed": pilot_validation["passed"],
            "validation_rows": len(pilot_validation["rows"]),
            "symbols": sorted({row["symbol"] for row in pilot_rows}),
            "dates": sorted({row["trading_date"] for row in pilot_rows}),
            "classifications": [
                {
                    "trading_date": row["trading_date"],
                    "symbol": row["symbol"],
                    "candidate_state": row["candidate_state"],
                    "emerging_eligible": row["emerging_eligible"],
                    "confirmed_eligible": row["confirmed_eligible"],
                    "rejection_reasons": row["rejection_reasons"],
                    "emerging_evidence": row["emerging_evidence"],
                    "confirmed_evidence": row["confirmed_evidence"],
                }
                for row in pilot_rows
            ],
        },
        "generation": generation
        | {
            "full_generation_completed": full_generation_completed,
            "input_feature_rows": input_summary["feature_rows_read"],
        },
        "input_load": input_summary | {"price_lookup_rows": len(price_lookup)},
        "integrity": {
            "daily_features_v1_unchanged": feature_before == feature_after,
            "daily_features_v1_hash_before": feature_before,
            "daily_features_v1_hash_after": feature_after,
            "raw_nse_unchanged": raw_before == raw_after,
            "adjusted_dataset_unchanged": adjusted_before == adjusted_after,
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "future_outcome_fields_generated": 0,
            "entry_scores_generated": 0,
            "risk_reward_calculated": 0,
        },
        "outputs": {
            "candidate_dataset": str(config.candidate_dataset_path),
            "pilot_dataset": str(config.pilot_dataset_path),
            "summary_json": str(config.summary_path),
            "daily_counts_csv": str(config.daily_counts_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "rejection_summary_csv": str(config.rejection_summary_path),
            "markdown": "docs/momentum-candidate-engine.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": file_size(config.candidate_dataset_path) + file_size(config.pilot_dataset_path),
        },
        "ready_for_review": bool(
            full_generation_completed
            and pilot_validation["passed"]
            and feature_before == feature_after
            and raw_before == raw_after
            and adjusted_before == adjusted_after
        ),
    }
    write_json(config.summary_path, report)
    return report


def evaluate_feature_dataset(
    *,
    config: MomentumCandidateEngineConfig,
    price_lookup: dict[tuple[str, str], Decimal],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    rows_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    summary = Counter()
    with open_csv_maybe_gzip(config.feature_dataset_path) as file:
        for feature_row in csv.DictReader(file):
            trading_date = feature_row.get("trading_date", "")
            parsed_date = parse_date(trading_date)
            if parsed_date is None or parsed_date < config.start_date or parsed_date > config.end_date:
                continue
            summary["feature_rows_read"] += 1
            candidate_row = evaluate_candidate_row(
                feature_row,
                config=config.candidate_config,
                price=price_lookup.get((trading_date, canonical_symbol(feature_row.get("symbol", "")))),
            )
            rows_by_date[trading_date].append(candidate_row)
    return dict(rows_by_date), dict(summary)


def evaluate_candidate_row(
    feature_row: dict[str, Any],
    *,
    config: MomentumCandidateConfig,
    price: Decimal | None,
) -> dict[str, Any]:
    values = parsed_feature_values(feature_row)
    warnings: set[str] = set()
    rejection_reasons: set[str] = set()
    eligibility_status = "RESEARCH_ELIGIBLE"
    research_eligible = True
    mandatory_gates_passed = True

    series = str(feature_row.get("series", "EQ")).upper()
    if series not in config.allowed_series:
        rejection_reasons.add("NON_STANDARD_SERIES")
        eligibility_status = "OTHER"
        research_eligible = False
        mandatory_gates_passed = False

    if feature_row.get("universe_name") != "NIFTY_500":
        rejection_reasons.add("NOT_IN_POINT_IN_TIME_UNIVERSE")
        eligibility_status = "OTHER"
        research_eligible = False
        mandatory_gates_passed = False

    if feature_row.get("universe_membership_status") != "SURVIVORSHIP_SAFE":
        warnings.add("MEMBERSHIP_UNCERTAIN")

    null_reasons = str(feature_row.get("feature_null_reasons", ""))
    if "CORPORATE_ACTION_LOOKBACK_BLOCKED" in null_reasons or str(feature_row.get("feature_status")) == "CORPORATE_ACTION_LOOKBACK_BLOCKED":
        rejection_reasons.add("CORPORATE_ACTION_BLOCKED")
        eligibility_status = "CORPORATE_ACTION_BLOCKED"
        research_eligible = False
        mandatory_gates_passed = False

    if price is None:
        rejection_reasons.add("MISSING_PRICE")
        eligibility_status = "MISSING_REQUIRED_FEATURE"
        mandatory_gates_passed = False
    elif price < config.price.minimum_price:
        rejection_reasons.add("PRICE_BELOW_MINIMUM")
        eligibility_status = "PRICE_BELOW_MINIMUM"
        mandatory_gates_passed = False
    elif price > config.price.hard_max_price:
        rejection_reasons.add("PRICE_ABOVE_HARD_LIMIT")
        eligibility_status = "PRICE_ABOVE_HARD_LIMIT"
        mandatory_gates_passed = False
    elif price > config.price.preferred_max_price:
        warnings.add("ABOVE_PREFERRED_PRICE_RANGE")

    if values["median_traded_value_20d"] is None:
        rejection_reasons.add("MISSING_LIQUIDITY_HISTORY")
        eligibility_status = "MISSING_REQUIRED_FEATURE"
        mandatory_gates_passed = False
    elif values["median_traded_value_20d"] < config.liquidity.median_traded_value_20d_min:
        rejection_reasons.add("LOW_LIQUIDITY")
        eligibility_status = "LOW_LIQUIDITY"
        mandatory_gates_passed = False

    missing_required = [
        field
        for field in config.required_feature_fields
        if values.get(field) is None and field != "median_traded_value_20d"
    ]
    if missing_required:
        if "INSUFFICIENT_HISTORY" in null_reasons or str(feature_row.get("feature_status")) == "INSUFFICIENT_HISTORY":
            rejection_reasons.add("INSUFFICIENT_HISTORY")
            eligibility_status = "INSUFFICIENT_HISTORY"
        else:
            rejection_reasons.add("MISSING_REQUIRED_FEATURE")
            eligibility_status = "MISSING_REQUIRED_FEATURE"
        mandatory_gates_passed = False

    if values["relative_return_5d_vs_nifty500"] is None or values["relative_return_20d_vs_nifty500"] is None:
        warnings.add("BENCHMARK_CONTEXT_UNAVAILABLE")
    if values["above_prior_52w_high"] is None:
        warnings.add("INSUFFICIENT_52W_HISTORY")

    breakout_context = classify_breakout_context(values, config)
    extension_status = classify_extension(values, config)
    volatility_context = classify_volatility(values, config)
    sector_context_status = classify_sector_context(feature_row)
    if extension_status == "EXTREME":
        warnings.add("EXTREME_EXTENSION")

    emerging_evidence = emerging_evidence_flags(values, breakout_context, config)
    confirmed_evidence = confirmed_evidence_flags(values, breakout_context, config)
    emerging_eligible = False
    confirmed_eligible = False
    if mandatory_gates_passed and research_eligible:
        emerging_eligible = passes_emerging(values, emerging_evidence, config)
        confirmed_eligible = passes_confirmed(values, confirmed_evidence, config)
        if not emerging_eligible and not confirmed_eligible:
            add_behavioral_rejection_reasons(rejection_reasons, values, breakout_context, volatility_context, config)

    if not research_eligible or any(reason in RESEARCH_UNAVAILABLE_REASONS for reason in rejection_reasons):
        candidate_state = "UNAVAILABLE"
    elif confirmed_eligible:
        candidate_state = "CONFIRMED"
    elif emerging_eligible:
        candidate_state = "EMERGING"
    else:
        candidate_state = "REJECTED"

    evidence_count = max(len(emerging_evidence), len(confirmed_evidence))
    output = {
        "trading_date": feature_row.get("trading_date", ""),
        "symbol": canonical_symbol(feature_row.get("symbol", "")),
        "isin": feature_row.get("isin", ""),
        "universe_name": feature_row.get("universe_name", ""),
        "membership_status": feature_row.get("universe_membership_status", ""),
        "membership_confidence": feature_row.get("universe_membership_confidence", ""),
        "universe_version": feature_row.get("universe_version", ""),
        "feature_version": feature_row.get("feature_version", ""),
        "candidate_version": config.candidate_version,
        "candidate_config_hash": config.config_hash(),
        "benchmark_context_version": feature_row.get("benchmark_context_version", ""),
        "sector_context_version": feature_row.get("sector_context_version", ""),
        "adjustment_methodology": feature_row.get("adjustment_methodology", ""),
        "exclusion_policy": feature_row.get("exclusion_policy", ""),
        "availability_time": feature_row.get("availability_time", ""),
        "decision_input_time": feature_row.get("decision_input_time", ""),
        "timeframe": feature_row.get("timeframe", ""),
        "research_eligible": research_eligible,
        "eligibility_status": eligibility_status,
        "mandatory_gates_passed": mandatory_gates_passed,
        "rejection_reasons": join_codes(rejection_reasons),
        "candidate_state": candidate_state,
        "emerging_eligible": emerging_eligible,
        "confirmed_eligible": confirmed_eligible,
        "both_eligible": emerging_eligible and confirmed_eligible,
        "emerging_rank": None,
        "emerging_percentile": None,
        "confirmed_rank": None,
        "confirmed_percentile": None,
        "candidate_rank_metric": None,
        "candidate_rank_components": "",
        "price": price,
        "price_range_status": classify_price(price, config),
        "cash_equity_status": "EQ" if series in config.allowed_series else "NON_STANDARD_SERIES",
        "median_traded_value_20d": values["median_traded_value_20d"],
        "return_1d": values["return_1d"],
        "return_3d": values["return_3d"],
        "return_5d": values["return_5d"],
        "return_10d": values["return_10d"],
        "return_20d": values["return_20d"],
        "relative_volume_5d": values["relative_volume_5d"],
        "relative_volume_20d": values["relative_volume_20d"],
        "up_days_ratio_10": values["up_days_ratio_10"],
        "up_days_ratio_20": values["up_days_ratio_20"],
        "relative_return_5d_vs_nifty500": values["relative_return_5d_vs_nifty500"],
        "relative_return_20d_vs_nifty500": values["relative_return_20d_vs_nifty500"],
        "prior_high_20d": values["prior_high_20d"],
        "distance_to_prior_20d_high_pct": values["distance_to_prior_20d_high_pct"],
        "above_prior_20d_high": values["above_prior_20d_high"],
        "intraday_high_above_prior_20d_high": values["intraday_high_above_prior_20d_high"],
        "atr_percent_14": values["atr_percent_14"],
        "extension_status": extension_status,
        "breakout_context": breakout_context,
        "volatility_context": volatility_context,
        "sector_context_status": sector_context_status,
        "candidate_evidence_count": evidence_count,
        "candidate_strength_descriptor": strength_descriptor(candidate_state, evidence_count),
        "emerging_evidence": join_codes(emerging_evidence),
        "confirmed_evidence": join_codes(confirmed_evidence),
        "warning_flags": join_codes(warnings),
        "_rank_momentum": momentum_component(values),
        "_rank_relative_volume": values["relative_volume_20d"],
        "_rank_benchmark_relative_strength": values["relative_return_20d_vs_nifty500"] or values["relative_return_5d_vs_nifty500"],
        "_rank_breakout_context": breakout_rank_component(values, breakout_context),
    }
    return output


def parsed_feature_values(feature_row: dict[str, Any]) -> dict[str, Any]:
    decimal_fields = [
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
        "upper_wick_pct",
        "gap_open_pct",
    ]
    values = {field: parse_decimal(feature_row.get(field)) for field in decimal_fields}
    values["above_prior_20d_high"] = parse_bool(feature_row.get("above_prior_20d_high"))
    values["intraday_high_above_prior_20d_high"] = parse_bool(feature_row.get("intraday_high_above_prior_20d_high"))
    values["above_prior_52w_high"] = parse_bool(feature_row.get("above_prior_52w_high"))
    return values


def emerging_evidence_flags(values: dict[str, Any], breakout_context: str, config: MomentumCandidateConfig) -> set[str]:
    evidence: set[str] = set()
    if at_least(values["return_3d"], config.momentum.emerging_min_return_3d):
        evidence.add("POSITIVE_3D_MOMENTUM")
    if at_least(values["return_5d"], config.momentum.emerging_min_return_5d):
        evidence.add("POSITIVE_5D_MOMENTUM")
    if at_least(values["return_10d"], config.momentum.emerging_min_return_10d):
        evidence.add("IMPROVING_10D_STRUCTURE")
    if at_least(values["relative_volume_20d"], config.relative_volume.emerging_threshold):
        evidence.add("EMERGING_RELATIVE_VOLUME")
    if at_least(values["up_days_ratio_10"], config.momentum.emerging_min_up_days_ratio_10):
        evidence.add("HEALTHY_UP_DAY_RATIO")
    if positive(values["relative_return_5d_vs_nifty500"]):
        evidence.add("POSITIVE_5D_BENCHMARK_RELATIVE_STRENGTH")
    if breakout_context in {"APPROACHING_20D_HIGH", "TESTING_20D_HIGH", "ABOVE_20D_HIGH"}:
        evidence.add(breakout_context)
    if positive(values["return_1d"]):
        evidence.add("CURRENT_DAY_CONFIRMATION")
    return evidence


def confirmed_evidence_flags(values: dict[str, Any], breakout_context: str, config: MomentumCandidateConfig) -> set[str]:
    evidence: set[str] = set()
    if at_least(values["return_5d"], config.momentum.confirmed_min_return_5d):
        evidence.add("STRONG_5D_MOMENTUM")
    if at_least(values["return_10d"], config.momentum.confirmed_min_return_10d):
        evidence.add("STRONG_10D_MOMENTUM")
    if at_least(values["return_20d"], config.momentum.confirmed_min_return_20d):
        evidence.add("STRONG_20D_MOMENTUM")
    if at_least(values["relative_volume_20d"], config.relative_volume.confirmed_threshold):
        evidence.add("CONFIRMED_RELATIVE_VOLUME")
    if at_least(values["up_days_ratio_10"], config.momentum.confirmed_min_up_days_ratio_10):
        evidence.add("REPEATED_POSITIVE_10D_SESSIONS")
    if at_least(values["up_days_ratio_20"], config.momentum.confirmed_min_up_days_ratio_20):
        evidence.add("REPEATED_POSITIVE_20D_SESSIONS")
    if positive(values["relative_return_20d_vs_nifty500"]):
        evidence.add("POSITIVE_20D_BENCHMARK_RELATIVE_STRENGTH")
    if breakout_context in {"TESTING_20D_HIGH", "ABOVE_20D_HIGH"}:
        evidence.add(breakout_context)
    if at_least(values["return_1d"], Decimal("0.005")):
        evidence.add("CURRENT_DAY_STRONG")
    return evidence


def passes_emerging(values: dict[str, Any], evidence: set[str], config: MomentumCandidateConfig) -> bool:
    has_short_momentum = (
        at_least(values["return_3d"], config.momentum.emerging_min_return_3d)
        or at_least(values["return_5d"], config.momentum.emerging_min_return_5d)
    )
    has_structure = at_least(values["return_10d"], config.momentum.emerging_min_return_10d)
    has_up_days = at_least(values["up_days_ratio_10"], config.momentum.emerging_min_up_days_ratio_10)
    return bool(has_short_momentum and has_structure and has_up_days and len(evidence) >= config.momentum.emerging_min_evidence_count)


def passes_confirmed(values: dict[str, Any], evidence: set[str], config: MomentumCandidateConfig) -> bool:
    momentum_checks = [
        at_least(values["return_5d"], config.momentum.confirmed_min_return_5d),
        at_least(values["return_10d"], config.momentum.confirmed_min_return_10d),
        at_least(values["return_20d"], config.momentum.confirmed_min_return_20d),
    ]
    has_momentum_depth = sum(1 for item in momentum_checks if item) >= 2
    has_up_days = (
        at_least(values["up_days_ratio_10"], config.momentum.confirmed_min_up_days_ratio_10)
        or at_least(values["up_days_ratio_20"], config.momentum.confirmed_min_up_days_ratio_20)
    )
    has_volume = at_least(values["relative_volume_20d"], config.relative_volume.confirmed_threshold)
    return bool(has_momentum_depth and has_up_days and has_volume and len(evidence) >= config.momentum.confirmed_min_evidence_count)


def add_behavioral_rejection_reasons(
    rejection_reasons: set[str],
    values: dict[str, Any],
    breakout_context: str,
    volatility_context: str,
    config: MomentumCandidateConfig,
) -> None:
    if not (
        at_least(values["return_3d"], config.momentum.emerging_min_return_3d)
        or at_least(values["return_5d"], config.momentum.emerging_min_return_5d)
        or positive(values["return_20d"])
    ):
        rejection_reasons.add("LOW_MULTI_DAY_MOMENTUM")
    if values["relative_volume_20d"] is None or values["relative_volume_20d"] < config.relative_volume.emerging_threshold:
        rejection_reasons.add("LOW_RELATIVE_VOLUME")
    if breakout_context == "FAR_FROM_20D_HIGH":
        rejection_reasons.add("FAR_FROM_RELEVANT_HIGH")
    if volatility_context == "LOW":
        rejection_reasons.add("LOW_ACTIVITY")
    if (
        values["relative_return_5d_vs_nifty500"] is not None
        and values["relative_return_20d_vs_nifty500"] is not None
        and values["relative_return_5d_vs_nifty500"] <= 0
        and values["relative_return_20d_vs_nifty500"] <= 0
    ):
        rejection_reasons.add("WEAK_BENCHMARK_RELATIVE_STRENGTH")


def rank_candidate_rows_by_date(rows_by_date: dict[str, list[dict[str, Any]]]) -> None:
    component_fields = {
        "momentum": "_rank_momentum",
        "relative_volume": "_rank_relative_volume",
        "benchmark_relative_strength": "_rank_benchmark_relative_strength",
        "breakout_context": "_rank_breakout_context",
    }
    for rows in rows_by_date.values():
        component_percentiles: dict[str, dict[int, Decimal]] = {}
        for name, field in component_fields.items():
            component_percentiles[name] = percentile_map(rows, field)
        for offset, row in enumerate(rows):
            values = [component_percentiles[name][offset] for name in component_fields if offset in component_percentiles[name]]
            if values and row["mandatory_gates_passed"]:
                metric = sum(values, Decimal("0")) / Decimal(len(values))
                row["candidate_rank_metric"] = metric
                row["candidate_rank_components"] = ";".join(f"{name}={format_decimal(component_percentiles[name][offset])}" for name in component_fields if offset in component_percentiles[name])
        assign_category_ranks(rows, category="emerging")
        assign_category_ranks(rows, category="confirmed")
        for row in rows:
            for key in list(row):
                if key.startswith("_rank_"):
                    del row[key]


def percentile_map(rows: Sequence[dict[str, Any]], field: str) -> dict[int, Decimal]:
    values = [
        (offset, row[field])
        for offset, row in enumerate(rows)
        if row.get("mandatory_gates_passed") and isinstance(row.get(field), Decimal)
    ]
    if not values:
        return {}
    ordered = sorted(values, key=lambda item: item[1])
    if len(ordered) == 1:
        return {ordered[0][0]: Decimal("100")}
    percentiles: dict[int, Decimal] = {}
    for rank, (offset, _value) in enumerate(ordered, start=1):
        percentiles[offset] = (Decimal(rank - 1) / Decimal(len(ordered) - 1) * Decimal("100"))
    return percentiles


def assign_category_ranks(rows: list[dict[str, Any]], *, category: str) -> None:
    eligible_field = f"{category}_eligible"
    rank_field = f"{category}_rank"
    percentile_field = f"{category}_percentile"
    candidates = [row for row in rows if row.get(eligible_field) and isinstance(row.get("candidate_rank_metric"), Decimal)]
    candidates.sort(key=lambda row: (row["candidate_rank_metric"], row["candidate_evidence_count"], row["symbol"]), reverse=True)
    total = len(candidates)
    for rank, row in enumerate(candidates, start=1):
        row[rank_field] = rank
        row[percentile_field] = Decimal(total - rank + 1) / Decimal(total) * Decimal("100")


def daily_count_rows(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trading_date in sorted(rows_by_date):
        group = rows_by_date[trading_date]
        candidates = [row for row in group if row["candidate_state"] in {"EMERGING", "CONFIRMED"}]
        rows.append(
            {
                "trading_date": trading_date,
                "universe_count": len(group),
                "evaluable_count": sum(1 for row in group if row["mandatory_gates_passed"]),
                "rejected_count": sum(1 for row in group if row["candidate_state"] == "REJECTED"),
                "emerging_count": sum(1 for row in group if row["candidate_state"] == "EMERGING"),
                "confirmed_count": sum(1 for row in group if row["candidate_state"] == "CONFIRMED"),
                "both_eligible_count": sum(1 for row in group if row["both_eligible"]),
                "unavailable_count": sum(1 for row in group if row["candidate_state"] == "UNAVAILABLE"),
                "median_candidate_return_5d": median_decimal([row["return_5d"] for row in candidates]),
                "median_relative_volume_20d": median_decimal([row["relative_volume_20d"] for row in candidates]),
                "median_benchmark_relative_strength": median_decimal([row["relative_return_20d_vs_nifty500"] for row in candidates]),
            }
        )
    return rows


def generation_summary(candidate_rows: Sequence[dict[str, Any]], daily_counts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    state_counts = Counter(row["candidate_state"] for row in candidate_rows)
    candidate_counts_by_date = [int(row["emerging_count"]) + int(row["confirmed_count"]) for row in daily_counts]
    return {
        "total_evaluated_rows": len(candidate_rows),
        "emerging_count": state_counts["EMERGING"],
        "confirmed_count": state_counts["CONFIRMED"],
        "rejected_count": state_counts["REJECTED"],
        "unavailable_count": state_counts["UNAVAILABLE"],
        "both_eligible_count": sum(1 for row in candidate_rows if row["both_eligible"]),
        "state_counts": dict(state_counts),
        "candidate_count_distribution": distribution(candidate_counts_by_date),
        "major_rejection_reasons": {row["reason_code"]: row["count"] for row in rejection_summary_rows(candidate_rows)[:20]},
    }


def distribution(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"min": 0, "median": 0, "mean": 0, "p90": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "mean": round(statistics.mean(ordered), 4),
        "p90": percentile_value(ordered, Decimal("0.90")),
        "p95": percentile_value(ordered, Decimal("0.95")),
        "max": ordered[-1],
    }


def percentile_value(sorted_values: Sequence[int], percentile: Decimal) -> int:
    if not sorted_values:
        return 0
    index = int((Decimal(len(sorted_values) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP"))
    return sorted_values[min(index, len(sorted_values) - 1)]


def rejection_summary_rows(candidate_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in candidate_rows:
        for reason in split_codes(row.get("rejection_reasons", "")):
            counter[reason] += 1
    return [{"reason_code": reason, "count": count} for reason, count in counter.most_common()]


def select_pilot_rows(candidate_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    requested_symbols = {"RELIANCE", "TCS", "HDFCBANK", "INFY", "SUNPHARMA", "INFIBEAM"}
    for symbol in sorted(requested_symbols):
        row = latest_row_for_symbol(candidate_rows, symbol)
        add_pilot_row(selected, seen, row)

    for state in ("EMERGING", "CONFIRMED", "REJECTED", "UNAVAILABLE"):
        add_pilot_row(selected, seen, first_row(candidate_rows, lambda row, state=state: row["candidate_state"] == state))

    add_pilot_row(selected, seen, first_row(candidate_rows, lambda row: "LOW_LIQUIDITY" in split_codes(row["rejection_reasons"])))
    add_pilot_row(selected, seen, first_row(candidate_rows, lambda row: "LOW_MULTI_DAY_MOMENTUM" in split_codes(row["rejection_reasons"])))
    add_pilot_row(selected, seen, first_row(candidate_rows, lambda row: row["confirmed_eligible"]))
    add_pilot_row(selected, seen, first_row(candidate_rows, lambda row: row["emerging_eligible"] and not row["confirmed_eligible"]))
    add_pilot_row(selected, seen, first_row(candidate_rows, lambda row: "CORPORATE_ACTION_BLOCKED" in split_codes(row["rejection_reasons"])))
    return selected


def add_pilot_row(selected: list[dict[str, Any]], seen: set[tuple[str, str, str]], row: dict[str, Any] | None) -> None:
    if row is None:
        return
    key = (row["trading_date"], row["symbol"], row["candidate_state"])
    if key in seen:
        return
    selected.append(row)
    seen.add(key)


def latest_row_for_symbol(candidate_rows: Sequence[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    normalized = canonical_symbol(symbol)
    matches = [row for row in candidate_rows if row["symbol"] == normalized]
    return max(matches, key=lambda row: row["trading_date"]) if matches else None


def first_row(candidate_rows: Sequence[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    return next((row for row in candidate_rows if predicate(row)), None)


def validate_pilot_rows(pilot_rows: Sequence[dict[str, Any]], config: MomentumCandidateConfig) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    states = {row["candidate_state"] for row in pilot_rows}
    for expected_state in ("EMERGING", "CONFIRMED", "REJECTED", "UNAVAILABLE"):
        rows.append(
            validation_row(
                {},
                check_name=f"state_coverage_{expected_state.lower()}",
                observed=expected_state in states,
                rule="Pilot must include this state when present in historical data.",
                passed=expected_state in states,
                explanation=f"Pilot includes {expected_state}: {expected_state in states}.",
            )
        )

    for row in pilot_rows:
        price = parse_decimal(row.get("price"))
        liquidity_value = parse_decimal(row.get("median_traded_value_20d"))
        rows.append(
            validation_row(
                row,
                check_name="price_gate",
                observed=price,
                rule=f"{config.price.minimum_price} <= price <= {config.price.hard_max_price}",
                passed=price is not None and config.price.minimum_price <= price <= config.price.hard_max_price
                or "PRICE_" in str(row.get("rejection_reasons")),
                explanation=f"Price status is {row.get('price_range_status')}.",
            )
        )
        rows.append(
            validation_row(
                row,
                check_name="liquidity_gate",
                observed=liquidity_value,
                rule=f"median_traded_value_20d >= {config.liquidity.median_traded_value_20d_min}",
                passed=(
                    liquidity_value is not None
                    and liquidity_value >= config.liquidity.median_traded_value_20d_min
                )
                or "LOW_LIQUIDITY" in split_codes(row.get("rejection_reasons", ""))
                or "MISSING_LIQUIDITY_HISTORY" in split_codes(row.get("rejection_reasons", "")),
                explanation=f"Eligibility status is {row.get('eligibility_status')}.",
            )
        )
        if row["candidate_state"] in {"EMERGING", "CONFIRMED"}:
            rows.append(
                validation_row(
                    row,
                    check_name="candidate_classification",
                    observed=row["candidate_state"],
                    rule="Candidate requires mandatory gates and model-specific evidence.",
                    passed=bool(row["mandatory_gates_passed"] and (row["emerging_eligible"] or row["confirmed_eligible"])),
                    explanation=classification_explanation(row),
                )
            )
        else:
            rows.append(
                validation_row(
                    row,
                    check_name="rejection_or_unavailable_reason",
                    observed=row.get("rejection_reasons", ""),
                    rule="Rejected/unavailable rows must retain reason codes.",
                    passed=bool(row.get("rejection_reasons")),
                    explanation=classification_explanation(row),
                )
            )
    return {"passed": all(row["result"] == "PASS" for row in rows), "rows": rows}


def validation_row(
    row: dict[str, Any],
    *,
    check_name: str,
    observed: Any,
    rule: str,
    passed: bool,
    explanation: str,
) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol", ""),
        "trading_date": row.get("trading_date", ""),
        "candidate_state": row.get("candidate_state", ""),
        "check_name": check_name,
        "observed": observed,
        "threshold_or_rule": rule,
        "result": "PASS" if passed else "FAIL",
        "explanation": explanation,
    }


def classification_explanation(row: dict[str, Any]) -> str:
    if row["candidate_state"] == "CONFIRMED":
        return f"Confirmed evidence: {row['confirmed_evidence']}; emerging preserved as {row['emerging_eligible']}."
    if row["candidate_state"] == "EMERGING":
        return f"Emerging evidence: {row['emerging_evidence']}; confirmed evidence was not sufficient."
    return f"Reasons: {row['rejection_reasons']}; warnings: {row['warning_flags']}."


def load_adjusted_close_lookup(
    *,
    adjusted_daily_dir: Path,
    start_date: date,
    end_date: date,
) -> dict[tuple[str, str], Decimal]:
    lookup: dict[tuple[str, str], Decimal] = {}
    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None or trading_date < start_date or trading_date > end_date:
            continue
        for row in read_csv_iter(path):
            if row.get("series", "EQ") != "EQ":
                continue
            close_value = parse_decimal(row.get("adjusted_close"))
            symbol = canonical_symbol(row.get("symbol", ""))
            if close_value is not None and symbol:
                lookup[(trading_date.isoformat(), symbol)] = close_value
    return lookup


def write_candidate_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CANDIDATE_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def write_momentum_candidate_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    distribution_row = generation["candidate_count_distribution"]
    lines = [
        "# Momentum Candidate Engine",
        "",
        "Current phase: Step 02.5 / Command 01 - Emerging and Confirmed Momentum research candidates",
        "",
        "## Boundary",
        "",
        "- Candidate Engine is not an Entry Engine.",
        "- Output means worth further Strategy V1 evaluation, not buy/sell advice.",
        "- No final 0-100 entry score, risk/reward, stops, position sizing, backtesting, future labels, live feeds, or orders are implemented.",
        "",
        "## Version",
        "",
        f"- Candidate methodology: {report['candidate_engine']['candidate_version']}",
        f"- Config hash: {report['candidate_engine']['candidate_config_hash']}",
        "- Input features: DAILY_FEATURES_V1 with BENCHMARK_CONTEXT_V1 and SECTOR_CONTEXT_V1.",
        "",
        "## Mandatory Gates",
        "",
        "- Point-in-time NIFTY_500 universe row from the feature dataset.",
        "- Cash-equity/EQ source policy, with non-standard series rejected if present.",
        "- Corporate-action-safe required feature windows.",
        "- Price between INR 100 and INR 7,000.",
        "- 20-day median traded value at least INR 100,000,000.",
        "- Required momentum, liquidity, volatility, and breakout-context features must be present.",
        "",
        "## Emerging Momentum",
        "",
        "- Earlier-stage acceleration using positive 3d/5d momentum, improving 10d structure, healthy up-day ratio, emerging relative volume, 20d-high proximity, current-day confirmation, and benchmark-relative support where available.",
        "- Default relative-volume reference: 1.20x.",
        "- Requires mandatory gates plus at least 4 emerging evidence flags.",
        "",
        "## Confirmed Momentum",
        "",
        "- Stronger established momentum using 5d/10d/20d return depth, 1.50x relative volume, repeated positive sessions, 20d-high test/clearance, current-day strength, and 20d benchmark-relative support.",
        "- Requires mandatory gates plus at least 5 confirmed evidence flags.",
        "- If both Emerging and Confirmed pass, primary state is CONFIRMED while both booleans are preserved.",
        "",
        "## Ranking",
        "",
        "- Same-date cross-sectional percentiles are built from momentum, relative volume, benchmark-relative strength, and breakout-context components.",
        "- Emerging and Confirmed ranks are assigned separately on each trading date.",
        "- Later dates and future outcomes are not used.",
        "",
        "## Context Handling",
        "",
        "- NIFTY 500 benchmark relative strength supports candidacy but missing isolated benchmark context is not a mandatory rejection by itself.",
        "- Historical sector-relative strength is not fabricated from current-only mapping. Sector context is metadata in this command.",
        "- Extension and volatility are descriptive diagnostics, not final entry penalties.",
        "",
        "## Pilot",
        "",
        f"- Pilot rows: {report['pilot']['row_count']}",
        f"- Pilot validation rows: {report['pilot']['validation_rows']}",
        f"- Pilot validation passed: {report['pilot']['validation_passed']}",
        f"- Pilot symbols: {', '.join(report['pilot']['symbols'])}",
        f"- Pilot dates: {', '.join(report['pilot']['dates'])}",
        "",
        "## Full Historical Generation",
        "",
        f"- Full generation completed: {generation['full_generation_completed']}",
        f"- Total evaluated rows: {generation['total_evaluated_rows']}",
        f"- Emerging rows: {generation['emerging_count']}",
        f"- Confirmed rows: {generation['confirmed_count']}",
        f"- Rejected rows: {generation['rejected_count']}",
        f"- Unavailable rows: {generation['unavailable_count']}",
        f"- Both-eligible rows: {generation['both_eligible_count']}",
        f"- Candidate count distribution: min={distribution_row['min']}, median={distribution_row['median']}, mean={distribution_row['mean']}, p90={distribution_row['p90']}, p95={distribution_row['p95']}, max={distribution_row['max']}",
        f"- Candidate dataset: {report['outputs']['candidate_dataset']}",
        f"- Processing seconds: {report['processing']['duration_seconds']}",
        f"- Storage bytes: {report['processing']['storage_size_bytes']}",
        "",
        "## Major Rejection Reasons",
        "",
    ]
    for reason, count in list(generation["major_rejection_reasons"].items())[:20]:
        lines.append(f"- {reason}: {count}")
    lines.extend(
        [
            "",
            "## Integrity And Safety",
            "",
            f"- DAILY_FEATURES_V1 unchanged: {report['integrity']['daily_features_v1_unchanged']}",
            f"- Raw NSE unchanged: {report['integrity']['raw_nse_unchanged']}",
            f"- Adjusted dataset unchanged: {report['integrity']['adjusted_dataset_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "",
            "## Known Limitations",
            "",
            "- Membership remains PARTIAL_HISTORY and is carried as metadata/warning.",
            "- Sector context remains unavailable for historical relative strength because upstream mapping is current-only or unavailable.",
            "- Thresholds are baseline research defaults, not optimized parameters.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def flatten_by_date(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row for trading_date in sorted(rows_by_date) for row in sorted(rows_by_date[trading_date], key=lambda item: item["symbol"])]


def classify_price(price: Decimal | None, config: MomentumCandidateConfig) -> str:
    if price is None:
        return "UNAVAILABLE"
    if price < config.price.minimum_price:
        return "BELOW_MINIMUM"
    if price > config.price.hard_max_price:
        return "ABOVE_HARD_LIMIT"
    if price > config.price.preferred_max_price:
        return "ABOVE_PREFERRED_PRICE_RANGE"
    return "NORMAL_ELIGIBLE_RANGE"


def classify_breakout_context(values: dict[str, Any], config: MomentumCandidateConfig) -> str:
    if values["above_prior_20d_high"] is True:
        return "ABOVE_20D_HIGH"
    distance = values["distance_to_prior_20d_high_pct"]
    if distance is None:
        return "UNAVAILABLE"
    if distance >= config.breakout.testing_20d_high_distance:
        return "TESTING_20D_HIGH"
    if distance >= config.breakout.approaching_20d_high_distance:
        return "APPROACHING_20D_HIGH"
    return "FAR_FROM_20D_HIGH"


def classify_extension(values: dict[str, Any], config: MomentumCandidateConfig) -> str:
    atr = values["atr_percent_14"]
    return_1d = abs(values["return_1d"]) if values["return_1d"] is not None else None
    return_5d = abs(values["return_5d"]) if values["return_5d"] is not None else None
    sma_distance = abs(values["distance_from_sma_20_pct"]) if values.get("distance_from_sma_20_pct") is not None else None
    if atr is None or atr <= 0:
        return "UNAVAILABLE"
    return_1d_multiple = return_1d / atr if return_1d is not None else Decimal("0")
    return_5d_multiple = return_5d / atr if return_5d is not None else Decimal("0")
    if (
        return_1d_multiple >= config.extension.extreme_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.extreme_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.extreme_distance_from_sma20)
    ):
        return "EXTREME"
    if (
        return_1d_multiple >= config.extension.extended_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.extended_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.extended_distance_from_sma20)
    ):
        return "EXTENDED"
    if (
        return_1d_multiple >= config.extension.elevated_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.elevated_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.elevated_distance_from_sma20)
    ):
        return "ELEVATED"
    return "NORMAL"


def classify_volatility(values: dict[str, Any], config: MomentumCandidateConfig) -> str:
    atr = values["atr_percent_14"]
    if atr is None:
        return "UNAVAILABLE"
    if atr < config.volatility.low_atr_percent:
        return "LOW"
    if atr >= config.volatility.extreme_atr_percent:
        return "EXTREME"
    if atr >= config.volatility.high_atr_percent:
        return "HIGH"
    return "NORMAL"


def classify_sector_context(feature_row: dict[str, Any]) -> str:
    status = feature_row.get("sector_mapping_status", "")
    if status in {"POINT_IN_TIME_VERIFIED", "INFERRED_WITH_EVIDENCE"}:
        return "VERIFIED"
    if status == "CURRENT_ONLY":
        return "CURRENT_ONLY"
    return "UNAVAILABLE"


def momentum_component(values: dict[str, Any]) -> Decimal | None:
    parts = [values["return_5d"], values["return_10d"], values["return_20d"]]
    clean = [value for value in parts if value is not None]
    return sum(clean, Decimal("0")) / Decimal(len(clean)) if clean else None


def breakout_rank_component(values: dict[str, Any], breakout_context: str) -> Decimal | None:
    distance = values["distance_to_prior_20d_high_pct"]
    if distance is None:
        return None
    if breakout_context == "ABOVE_20D_HIGH":
        return Decimal("1") + distance
    return distance


def strength_descriptor(candidate_state: str, evidence_count: int) -> str:
    if candidate_state == "CONFIRMED":
        return "STRONG" if evidence_count >= 7 else "MODERATE"
    if candidate_state == "EMERGING":
        return "DEVELOPING" if evidence_count < 6 else "STRONG_DEVELOPING"
    if candidate_state == "REJECTED":
        return "LOW"
    return "UNAVAILABLE"


def median_decimal(values: Iterable[Any]) -> Decimal | None:
    clean = [value for value in values if isinstance(value, Decimal)]
    if not clean:
        return None
    ordered = sorted(clean)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def at_least(value: Decimal | None, threshold: Decimal) -> bool:
    return value is not None and value >= threshold


def positive(value: Decimal | None) -> bool:
    return value is not None and value > 0


def join_codes(values: Iterable[Any]) -> str:
    return ";".join(str(value) for value in sorted(values) if value not in {"", None})


def split_codes(value: Any) -> set[str]:
    return {item for item in str(value or "").split(";") if item}


def parse_bool(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def format_decimal(value: Decimal) -> str:
    text = format(value.quantize(Decimal("0.0001")), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def open_csv_maybe_gzip(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

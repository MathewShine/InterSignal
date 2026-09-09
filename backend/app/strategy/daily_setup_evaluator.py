from __future__ import annotations

import csv
import gzip
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.services.corporate_actions import fingerprint_directory
from app.services.daily_feature_engine import (
    adjusted_daily_files,
    date_from_adjusted_path,
    json_safe,
    read_csv_iter,
    write_csv,
    write_json,
)
from app.services.nifty500_membership import canonical_symbol
from app.strategy.breakout_quality import (
    AdjustedDailyOhlc,
    classify_52w_context,
    classify_acceptance_state,
    classify_benchmark_rs_context,
    classify_breakout_state,
    classify_candle_quality,
    classify_consolidation,
    classify_extension_risk,
    classify_level_quality,
    classify_overhead_resistance,
    classify_volume_confirmation,
    daily_reclaim_context,
    derive_setup_decision,
    false_breakout_flags,
    join_flags,
    setup_type_flags,
)
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.momentum_candidates import (
    distribution,
    file_sha256,
    format_decimal,
    join_codes,
    open_csv_maybe_gzip,
    parse_bool,
    parse_decimal,
    split_codes,
)
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig

SETUP_OUTPUT_FIELDS = [
    "trading_date",
    "symbol",
    "isin",
    "candidate_state",
    "emerging_eligible",
    "confirmed_eligible",
    "both_eligible",
    "candidate_rank",
    "candidate_percentile",
    "feature_version",
    "candidate_version",
    "candidate_config_hash",
    "setup_version",
    "setup_config_hash",
    "benchmark_context_version",
    "adjustment_methodology",
    "exclusion_policy",
    "research_status",
    "setup_status",
    "setup_availability",
    "decision_input_time",
    "setup_eligible",
    "setup_rejection_reasons",
    "setup_type_flags",
    "breakout_state",
    "level_quality",
    "level_quality_metadata",
    "consolidation_state",
    "consolidation_quality",
    "acceptance_state",
    "candle_quality",
    "volume_confirmation",
    "benchmark_rs_context",
    "sector_context_status",
    "extension_risk",
    "overhead_resistance",
    "high_52w_context",
    "daily_level_reclaim",
    "reclaim_depth_pct",
    "reclaim_depth_status",
    "false_breakout_flags",
    "prior_high_20d",
    "prior_high_52w",
    "distance_to_prior_20d_high_pct",
    "distance_to_prior_52w_high_pct",
    "relative_volume_20d",
    "relative_volume_5d",
    "relative_return_5d_vs_nifty500",
    "relative_return_20d_vs_nifty500",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "atr_percent_14",
    "close_location_value",
    "upper_wick_pct",
    "lower_wick_pct",
    "body_pct",
    "daily_range_pct",
    "range_width_5d_pct",
    "range_width_10d_pct",
    "range_width_20d_pct",
    "atr_contraction_ratio",
    "gap_open_pct",
    "distance_from_sma_20_pct",
    "price",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
    "setup_quality",
    "setup_rank",
    "setup_percentile",
    "supporting_evidence",
    "warning_flags",
]

DAILY_COUNT_FIELDS = [
    "trading_date",
    "candidate_rows_evaluated",
    "setup_eligible",
    "setup_rejected",
    "strong_count",
    "valid_count",
    "watch_count",
    "poor_count",
    "emerging_rows",
    "emerging_setup_eligible",
    "confirmed_rows",
    "confirmed_setup_eligible",
    "candidate_setup_pass_rate_pct",
    "emerging_setup_pass_rate_pct",
    "confirmed_setup_pass_rate_pct",
    "pathology_flag",
]

PILOT_VALIDATION_FIELDS = [
    "example_type",
    "symbol",
    "trading_date",
    "candidate_state",
    "setup_quality",
    "setup_eligible",
    "check_name",
    "observed",
    "threshold_or_rule",
    "result",
    "explanation",
]

REJECTION_SUMMARY_FIELDS = ["reason_code", "count", "pct"]
COMPONENT_DISTRIBUTION_FIELDS = ["component", "state", "count", "pct"]

DECIMAL_FIELDS = [
    "prior_high_20d",
    "prior_high_52w",
    "distance_to_prior_20d_high_pct",
    "distance_to_prior_52w_high_pct",
    "relative_volume_20d",
    "relative_volume_5d",
    "relative_return_5d_vs_nifty500",
    "relative_return_20d_vs_nifty500",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "up_days_ratio_10",
    "up_days_ratio_20",
    "atr_percent_14",
    "close_location_value",
    "upper_wick_pct",
    "lower_wick_pct",
    "body_pct",
    "daily_range_pct",
    "range_width_5d_pct",
    "range_width_10d_pct",
    "range_width_20d_pct",
    "atr_contraction_ratio",
    "gap_open_pct",
    "distance_from_sma_20_pct",
    "price",
]

BOOL_FIELDS = [
    "above_prior_20d_high",
    "intraday_high_above_prior_20d_high",
    "above_prior_52w_high",
]


@dataclass(frozen=True, slots=True)
class DailySetupEvaluationEngineConfig:
    data_dir: Path
    start_date: date
    end_date: date
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    full_generation: bool = True

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.data_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def setups_dir(self) -> Path:
        return self.data_dir / "research" / "setups" / "daily" / "v1"

    @property
    def setup_dataset_path(self) -> Path:
        return self.setups_dir / "daily_setup_evaluations_v1.csv.gz"

    @property
    def pilot_dataset_path(self) -> Path:
        return self.setups_dir / "daily_setup_evaluations_v1_pilot.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "daily_setup_summary.json"

    @property
    def daily_counts_path(self) -> Path:
        return self.reports_dir / "daily_setup_daily_counts.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "daily_setup_pilot_validation.csv"

    @property
    def rejection_summary_path(self) -> Path:
        return self.reports_dir / "daily_setup_rejection_summary.csv"

    @property
    def component_distribution_path(self) -> Path:
        return self.reports_dir / "daily_setup_component_distribution.csv"


def build_daily_setup_evaluations(
    *,
    config: DailySetupEvaluationEngineConfig,
    progress: Any | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    candidate_before = file_sha256(config.candidate_dataset_path)
    feature_before = file_sha256(config.feature_dataset_path)
    adjusted_before = fingerprint_directory(config.adjusted_daily_dir)

    if progress:
        progress("Loading Momentum Candidate rows")
    all_candidate_rows = load_candidate_rows(config.candidate_dataset_path, config.start_date, config.end_date)
    evaluation_candidates = [row for row in all_candidate_rows if is_setup_scope_candidate(row)]
    pilot_extra_candidates = select_pilot_extra_candidates(all_candidate_rows, evaluation_candidates)
    lookup_keys = {
        (row.get("trading_date", ""), canonical_symbol(row.get("symbol", "")))
        for row in evaluation_candidates + pilot_extra_candidates
    }
    symbols = {symbol for _trading_date, symbol in lookup_keys if symbol}

    if progress:
        progress("Joining DAILY_FEATURES_V1 rows")
    feature_lookup = load_feature_lookup(config.feature_dataset_path, lookup_keys)

    if progress:
        progress("Loading adjusted daily OHLC for evaluated symbols")
    ohlc_history = load_adjusted_ohlc_history(
        adjusted_daily_dir=config.adjusted_daily_dir,
        symbols=symbols,
        start_date=config.start_date,
        end_date=config.end_date,
    )

    if progress:
        progress("Evaluating daily setup components")
    setup_rows_by_date = evaluate_candidate_rows_by_date(
        evaluation_candidates,
        feature_lookup=feature_lookup,
        ohlc_history=ohlc_history,
        config=config.setup_config,
    )
    rank_setup_rows_by_date(setup_rows_by_date)
    setup_rows = flatten_by_date(setup_rows_by_date)

    pilot_extra_rows = evaluate_candidate_rows(
        pilot_extra_candidates,
        feature_lookup=feature_lookup,
        ohlc_history=ohlc_history,
        config=config.setup_config,
    )
    pilot_rows, pilot_examples = select_pilot_rows(setup_rows, pilot_extra_rows)
    write_setup_rows(config.pilot_dataset_path, pilot_rows)
    pilot_validation = validate_pilot_rows(pilot_rows, pilot_examples, config.setup_config)
    write_csv(config.pilot_validation_path, pilot_validation["rows"], PILOT_VALIDATION_FIELDS)

    daily_counts = daily_count_rows(setup_rows_by_date)
    write_csv(config.daily_counts_path, daily_counts, DAILY_COUNT_FIELDS)
    rejection_summary = rejection_summary_rows(setup_rows)
    write_csv(config.rejection_summary_path, rejection_summary, REJECTION_SUMMARY_FIELDS)
    component_distributions = component_distribution_rows(setup_rows)
    write_csv(config.component_distribution_path, component_distributions, COMPONENT_DISTRIBUTION_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_validation["passed"]:
        if progress:
            progress("Writing full DAILY_SETUP_EVALUATION_V1 dataset")
        write_setup_rows(config.setup_dataset_path, setup_rows)
        full_generation_completed = True

    candidate_after = file_sha256(config.candidate_dataset_path)
    feature_after = file_sha256(config.feature_dataset_path)
    adjusted_after = fingerprint_directory(config.adjusted_daily_dir)

    generation = generation_summary(setup_rows, daily_counts)
    report = {
        "phase": "Step 02.6",
        "command": "Command 01",
        "generated_at": generated_at,
        "setup_evaluator": {
            "setup_version": config.setup_config.setup_version,
            "setup_config_hash": config.setup_config.config_hash(),
            "setup_availability": config.setup_config.setup_availability,
            "decision_input_time": config.setup_config.decision_input_time,
            "output_format": "compressed CSV",
            "dataset_path": str(config.setup_dataset_path),
            "pilot_dataset_path": str(config.pilot_dataset_path),
        },
        "inputs": {
            "candidate_dataset": str(config.candidate_dataset_path),
            "candidate_dataset_hash_before": candidate_before,
            "candidate_dataset_hash_after": candidate_after,
            "candidate_version": "MOMENTUM_CANDIDATES_V1",
            "candidate_config_hash": observed_candidate_config_hash(evaluation_candidates),
            "expected_candidate_config_hash": config.candidate_config.config_hash(),
            "feature_dataset": str(config.feature_dataset_path),
            "feature_dataset_hash_before": feature_before,
            "feature_dataset_hash_after": feature_after,
            "feature_version": "DAILY_FEATURES_V1",
        },
        "config_snapshot": config.setup_config.snapshot(),
        "methodology": methodology_summary(),
        "pilot": {
            "row_count": len(pilot_rows),
            "validation_passed": pilot_validation["passed"],
            "validation_rows": len(pilot_validation["rows"]),
            "examples": pilot_examples,
        },
        "generation": generation
        | {
            "full_generation_completed": full_generation_completed,
            "input_candidate_rows_read": len(all_candidate_rows),
            "candidate_rows_in_setup_scope": len(evaluation_candidates),
            "pilot_extra_rows": len(pilot_extra_candidates),
        },
        "component_distributions": compact_component_distributions(component_distributions),
        "integrity": {
            "daily_features_v1_unchanged": feature_before == feature_after,
            "daily_features_v1_hash_before": feature_before,
            "daily_features_v1_hash_after": feature_after,
            "momentum_candidates_v1_unchanged": candidate_before == candidate_after,
            "momentum_candidates_v1_hash_before": candidate_before,
            "momentum_candidates_v1_hash_after": candidate_after,
            "candidate_config_hash_unchanged": observed_candidate_config_hash(evaluation_candidates)
            == config.candidate_config.config_hash(),
            "adjusted_dataset_unchanged": adjusted_before == adjusted_after,
            "adjusted_dataset_before": asdict(adjusted_before),
            "adjusted_dataset_after": asdict(adjusted_after),
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "future_outcome_fields_generated": 0,
            "entry_scores_generated": 0,
            "risk_reward_calculated": 0,
            "stops_generated": 0,
            "targets_generated": 0,
            "position_sizes_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
        },
        "outputs": {
            "setup_dataset": str(config.setup_dataset_path),
            "pilot_dataset": str(config.pilot_dataset_path),
            "summary_json": str(config.summary_path),
            "daily_counts_csv": str(config.daily_counts_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "rejection_summary_csv": str(config.rejection_summary_path),
            "component_distribution_csv": str(config.component_distribution_path),
            "markdown": "docs/daily-breakout-setup-evaluation.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": file_size(config.setup_dataset_path) + file_size(config.pilot_dataset_path),
        },
        "ready_for_review": bool(
            full_generation_completed
            and pilot_validation["passed"]
            and feature_before == feature_after
            and candidate_before == candidate_after
            and adjusted_before == adjusted_after
            and observed_candidate_config_hash(evaluation_candidates) == config.candidate_config.config_hash()
        ),
    }
    write_json(config.summary_path, report)
    return report


def load_candidate_rows(path: Path, start_date: date, end_date: date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            parsed = parse_iso_date(row.get("trading_date"))
            if parsed is None or parsed < start_date or parsed > end_date:
                continue
            rows.append(row)
    return rows


def is_setup_scope_candidate(row: dict[str, Any]) -> bool:
    return str(row.get("candidate_state", "")).upper() in {"EMERGING", "CONFIRMED"} or truthy(row.get("emerging_eligible")) or truthy(row.get("confirmed_eligible"))


def select_pilot_extra_candidates(
    all_rows: Sequence[dict[str, str]],
    evaluation_candidates: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    evaluated_keys = {(row.get("trading_date", ""), canonical_symbol(row.get("symbol", ""))) for row in evaluation_candidates}
    selected: list[dict[str, str]] = []
    for predicate in (
        lambda row: canonical_symbol(row.get("symbol", "")) == "INFIBEAM",
        lambda row: "CORPORATE_ACTION_BLOCKED" in split_codes(row.get("rejection_reasons", "")),
    ):
        row = first_candidate_row(all_rows, predicate, exclude_keys=evaluated_keys)
        if row is not None and row not in selected:
            selected.append(row)
    return selected


def load_feature_lookup(path: Path, lookup_keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            key = (row.get("trading_date", ""), canonical_symbol(row.get("symbol", "")))
            if key in lookup_keys:
                lookup[key] = row
    return lookup


def load_adjusted_ohlc_history(
    *,
    adjusted_daily_dir: Path,
    symbols: set[str],
    start_date: date,
    end_date: date,
) -> dict[str, list[AdjustedDailyOhlc]]:
    history: dict[str, list[AdjustedDailyOhlc]] = defaultdict(list)
    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None or trading_date < start_date or trading_date > end_date:
            continue
        for row in read_csv_iter(path):
            symbol = canonical_symbol(row.get("symbol", ""))
            if symbol not in symbols or row.get("series", "EQ") != "EQ":
                continue
            history[symbol].append(
                AdjustedDailyOhlc(
                    trading_date=trading_date.isoformat(),
                    symbol=symbol,
                    open=parse_decimal(row.get("adjusted_open")),
                    high=parse_decimal(row.get("adjusted_high")),
                    low=parse_decimal(row.get("adjusted_low")),
                    close=parse_decimal(row.get("adjusted_close")),
                )
            )
    return {symbol: sorted(rows, key=lambda item: item.trading_date) for symbol, rows in history.items()}


def evaluate_candidate_rows_by_date(
    rows: Sequence[dict[str, str]],
    *,
    feature_lookup: dict[tuple[str, str], dict[str, str]],
    ohlc_history: dict[str, list[AdjustedDailyOhlc]],
    config: DailySetupEvaluationConfig,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evaluate_candidate_rows(
        rows,
        feature_lookup=feature_lookup,
        ohlc_history=ohlc_history,
        config=config,
    ):
        rows_by_date[row["trading_date"]].append(row)
    return dict(rows_by_date)


def evaluate_candidate_rows(
    rows: Sequence[dict[str, str]],
    *,
    feature_lookup: dict[tuple[str, str], dict[str, str]],
    ohlc_history: dict[str, list[AdjustedDailyOhlc]],
    config: DailySetupEvaluationConfig,
) -> list[dict[str, Any]]:
    index = ohlc_index(ohlc_history)
    evaluated: list[dict[str, Any]] = []
    for candidate_row in rows:
        trading_date = candidate_row.get("trading_date", "")
        symbol = canonical_symbol(candidate_row.get("symbol", ""))
        feature_row = feature_lookup.get((trading_date, symbol), {})
        bars = ohlc_history.get(symbol, [])
        bar_index = index.get((trading_date, symbol))
        current_ohlc = bars[bar_index] if bar_index is not None else None
        prior_bars = bars[max(0, bar_index - 260) : bar_index] if bar_index is not None else []
        evaluated.append(
            evaluate_setup_candidate(
                candidate_row,
                feature_row=feature_row,
                current_ohlc=current_ohlc,
                prior_bars=prior_bars,
                config=config,
            )
        )
    return evaluated


def evaluate_setup_candidate(
    candidate_row: dict[str, Any],
    *,
    feature_row: dict[str, Any] | None = None,
    current_ohlc: AdjustedDailyOhlc | None = None,
    prior_bars: list[AdjustedDailyOhlc] | None = None,
    config: DailySetupEvaluationConfig = DailySetupEvaluationConfig(),
) -> dict[str, Any]:
    feature_row = feature_row or {}
    prior_bars = prior_bars or []
    candidate_state = str(candidate_row.get("candidate_state", "")).upper()
    values = setup_values(candidate_row, feature_row, current_ohlc)
    research_status = classify_research_status(candidate_row, feature_row)
    setup_status = classify_setup_status(research_status, values, feature_row)

    breakout_state = classify_breakout_state(values, config)
    level_quality, level_metadata = classify_level_quality(values, prior_bars, config)
    consolidation_state, consolidation_quality, consolidation_evidence = classify_consolidation(values, config)
    volume_confirmation = classify_volume_confirmation(values, config)
    benchmark_rs_context = classify_benchmark_rs_context(values, config)
    candle_quality = classify_candle_quality(values, config)
    extension_risk = classify_extension_risk(values, config)
    false_flags = false_breakout_flags(values, breakout_state, volume_confirmation, config)
    daily_level_reclaim, reclaim_depth, reclaim_depth_status = daily_reclaim_context(values, config)
    overhead_resistance = classify_overhead_resistance(values, config)
    high_52w_context = classify_52w_context(values, config)
    acceptance_state, acceptance_evidence = classify_acceptance_state(
        values,
        breakout_state,
        volume_confirmation,
        benchmark_rs_context,
        config,
    )
    setup_flags = setup_type_flags(
        values,
        candidate_state=candidate_state,
        breakout_state=breakout_state,
        consolidation_quality=consolidation_quality,
        benchmark_rs_context=benchmark_rs_context,
        candle_quality=candle_quality,
        extension_risk=extension_risk,
        high_52w_context=high_52w_context,
    )
    setup_eligible, setup_quality, rejection_reasons, supporting_evidence, warnings = derive_setup_decision(
        candidate_state=candidate_state,
        research_status=setup_status if setup_status in {"BLOCKED", "UNAVAILABLE"} else research_status,
        setup_type_flags_value=setup_flags,
        breakout_state=breakout_state,
        level_quality=level_quality,
        consolidation_quality=consolidation_quality,
        acceptance_state=acceptance_state,
        candle_quality=candle_quality,
        volume_confirmation=volume_confirmation,
        benchmark_rs_context=benchmark_rs_context,
        extension_risk=extension_risk,
        high_52w_context=high_52w_context,
        daily_level_reclaim=daily_level_reclaim,
        false_breakout_flags_value=false_flags,
        config=config,
    )
    if setup_status == "PARTIAL":
        warnings.add("SETUP_PARTIAL_COMPONENTS")
    supporting_evidence |= consolidation_evidence | acceptance_evidence

    output = {
        "trading_date": candidate_row.get("trading_date", ""),
        "symbol": canonical_symbol(candidate_row.get("symbol", "")),
        "isin": candidate_row.get("isin", feature_row.get("isin", "")),
        "candidate_state": candidate_state,
        "emerging_eligible": truthy(candidate_row.get("emerging_eligible")),
        "confirmed_eligible": truthy(candidate_row.get("confirmed_eligible")),
        "both_eligible": truthy(candidate_row.get("both_eligible")),
        "candidate_rank": candidate_rank(candidate_row),
        "candidate_percentile": candidate_percentile(candidate_row),
        "feature_version": first_present(feature_row.get("feature_version"), candidate_row.get("feature_version")),
        "candidate_version": candidate_row.get("candidate_version", ""),
        "candidate_config_hash": candidate_row.get("candidate_config_hash", ""),
        "setup_version": config.setup_version,
        "setup_config_hash": config.config_hash(),
        "benchmark_context_version": first_present(
            feature_row.get("benchmark_context_version"),
            candidate_row.get("benchmark_context_version"),
        ),
        "adjustment_methodology": first_present(
            feature_row.get("adjustment_methodology"),
            candidate_row.get("adjustment_methodology"),
        ),
        "exclusion_policy": first_present(feature_row.get("exclusion_policy"), candidate_row.get("exclusion_policy")),
        "research_status": research_status,
        "setup_status": setup_status,
        "setup_availability": config.setup_availability,
        "decision_input_time": config.decision_input_time,
        "setup_eligible": setup_eligible,
        "setup_rejection_reasons": join_codes(rejection_reasons),
        "setup_type_flags": join_flags(setup_flags),
        "breakout_state": breakout_state,
        "level_quality": level_quality,
        "level_quality_metadata": metadata_string(level_metadata),
        "consolidation_state": consolidation_state,
        "consolidation_quality": consolidation_quality,
        "acceptance_state": acceptance_state,
        "candle_quality": candle_quality,
        "volume_confirmation": volume_confirmation,
        "benchmark_rs_context": benchmark_rs_context,
        "sector_context_status": sector_context_status(candidate_row, feature_row),
        "extension_risk": extension_risk,
        "overhead_resistance": overhead_resistance,
        "high_52w_context": high_52w_context,
        "daily_level_reclaim": daily_level_reclaim,
        "reclaim_depth_pct": reclaim_depth,
        "reclaim_depth_status": reclaim_depth_status,
        "false_breakout_flags": join_flags(false_flags),
        "prior_high_20d": values.get("prior_high_20d"),
        "prior_high_52w": values.get("prior_high_52w"),
        "distance_to_prior_20d_high_pct": values.get("distance_to_prior_20d_high_pct"),
        "distance_to_prior_52w_high_pct": values.get("distance_to_prior_52w_high_pct"),
        "relative_volume_20d": values.get("relative_volume_20d"),
        "relative_volume_5d": values.get("relative_volume_5d"),
        "relative_return_5d_vs_nifty500": values.get("relative_return_5d_vs_nifty500"),
        "relative_return_20d_vs_nifty500": values.get("relative_return_20d_vs_nifty500"),
        "return_1d": values.get("return_1d"),
        "return_3d": values.get("return_3d"),
        "return_5d": values.get("return_5d"),
        "return_10d": values.get("return_10d"),
        "return_20d": values.get("return_20d"),
        "atr_percent_14": values.get("atr_percent_14"),
        "close_location_value": values.get("close_location_value"),
        "upper_wick_pct": values.get("upper_wick_pct"),
        "lower_wick_pct": values.get("lower_wick_pct"),
        "body_pct": values.get("body_pct"),
        "daily_range_pct": values.get("daily_range_pct"),
        "range_width_5d_pct": values.get("range_width_5d_pct"),
        "range_width_10d_pct": values.get("range_width_10d_pct"),
        "range_width_20d_pct": values.get("range_width_20d_pct"),
        "atr_contraction_ratio": values.get("atr_contraction_ratio"),
        "gap_open_pct": values.get("gap_open_pct"),
        "distance_from_sma_20_pct": values.get("distance_from_sma_20_pct"),
        "price": values.get("close"),
        "adjusted_open": values.get("open"),
        "adjusted_high": values.get("high"),
        "adjusted_low": values.get("low"),
        "adjusted_close": values.get("close"),
        "setup_quality": setup_quality,
        "setup_rank": "",
        "setup_percentile": "",
        "supporting_evidence": join_flags(supporting_evidence),
        "warning_flags": join_codes(set(split_codes(candidate_row.get("warning_flags", ""))) | warnings),
        "_rank_tuple": setup_rank_tuple(
            setup_quality=setup_quality,
            supporting_evidence_count=len(supporting_evidence),
            acceptance_state=acceptance_state,
            volume_confirmation=volume_confirmation,
            benchmark_rs_context=benchmark_rs_context,
            candidate_percentile_value=parse_decimal(candidate_percentile(candidate_row)),
        ),
    }
    return output


def setup_values(
    candidate_row: dict[str, Any],
    feature_row: dict[str, Any],
    current_ohlc: AdjustedDailyOhlc | None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in DECIMAL_FIELDS:
        values[field] = parse_decimal(first_present(feature_row.get(field), candidate_row.get(field)))
    for field in BOOL_FIELDS:
        values[field] = parse_bool(first_present(feature_row.get(field), candidate_row.get(field)))
    if current_ohlc is not None:
        values["open"] = current_ohlc.open
        values["high"] = current_ohlc.high
        values["low"] = current_ohlc.low
        values["close"] = current_ohlc.close
    else:
        values["open"] = None
        values["high"] = None
        values["low"] = None
        values["close"] = values["price"]
    values["candidate_extension_status"] = candidate_row.get("extension_status", "")
    if values["price"] is None:
        values["price"] = values["close"]
    return values


def classify_research_status(candidate_row: dict[str, Any], feature_row: dict[str, Any]) -> str:
    candidate_reasons = split_codes(candidate_row.get("rejection_reasons", ""))
    feature_null_reasons = str(feature_row.get("feature_null_reasons", ""))
    feature_status = str(feature_row.get("feature_status", ""))
    if "CORPORATE_ACTION_BLOCKED" in candidate_reasons or "CORPORATE_ACTION_LOOKBACK_BLOCKED" in feature_null_reasons or feature_status == "CORPORATE_ACTION_LOOKBACK_BLOCKED":
        return "BLOCKED"
    if not feature_row:
        return "PARTIAL"
    if not is_setup_scope_candidate(candidate_row):
        return "UNAVAILABLE"
    return "READY"


def classify_setup_status(research_status: str, values: dict[str, Any], feature_row: dict[str, Any]) -> str:
    if research_status in {"BLOCKED", "UNAVAILABLE"}:
        return research_status
    required_fields = [
        "prior_high_20d",
        "distance_to_prior_20d_high_pct",
        "relative_volume_20d",
        "relative_volume_5d",
        "return_5d",
        "return_10d",
        "atr_percent_14",
        "close_location_value",
        "range_width_20d_pct",
    ]
    if any(values.get(field) is None for field in required_fields):
        return "PARTIAL"
    if not feature_row:
        return "PARTIAL"
    return "READY"


def sector_context_status(candidate_row: dict[str, Any], feature_row: dict[str, Any]) -> str:
    status = str(first_present(candidate_row.get("sector_context_status"), feature_row.get("sector_mapping_status"), ""))
    if status == "CURRENT_ONLY":
        return "CURRENT_ONLY_NOT_USED"
    return status or "UNAVAILABLE"


def rank_setup_rows_by_date(rows_by_date: dict[str, list[dict[str, Any]]]) -> None:
    for rows in rows_by_date.values():
        eligible = [row for row in rows if row.get("setup_eligible")]
        eligible.sort(key=lambda row: (row.get("_rank_tuple", ()), row["symbol"]), reverse=True)
        total = len(eligible)
        for rank, row in enumerate(eligible, start=1):
            row["setup_rank"] = rank
            row["setup_percentile"] = Decimal(total - rank + 1) / Decimal(total) * Decimal("100")
        for row in rows:
            row.pop("_rank_tuple", None)


def setup_rank_tuple(
    *,
    setup_quality: str,
    supporting_evidence_count: int,
    acceptance_state: str,
    volume_confirmation: str,
    benchmark_rs_context: str,
    candidate_percentile_value: Decimal | None,
) -> tuple[int, int, int, int, int, Decimal]:
    return (
        quality_ordinal(setup_quality),
        supporting_evidence_count,
        acceptance_ordinal(acceptance_state),
        volume_ordinal(volume_confirmation),
        benchmark_ordinal(benchmark_rs_context),
        candidate_percentile_value or Decimal("0"),
    )


def quality_ordinal(value: str) -> int:
    return {"POOR": 0, "WATCH": 1, "VALID": 2, "STRONG": 3}.get(value, 0)


def acceptance_ordinal(value: str) -> int:
    return {"NONE": 0, "WEAK": 1, "MODERATE": 2, "STRONG": 3}.get(value, 0)


def volume_ordinal(value: str) -> int:
    return {"UNKNOWN": 0, "WEAK": 1, "NORMAL": 2, "GOOD": 3, "STRONG": 4, "EXCEPTIONAL": 5}.get(value, 0)


def benchmark_ordinal(value: str) -> int:
    return {"UNKNOWN": 0, "WEAK": 1, "NEUTRAL": 2, "POSITIVE": 3, "STRONG": 4}.get(value, 0)


def daily_count_rows(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trading_date in sorted(rows_by_date):
        group = rows_by_date[trading_date]
        eligible = [row for row in group if row["setup_eligible"]]
        emerging = [row for row in group if row["candidate_state"] == "EMERGING"]
        confirmed = [row for row in group if row["candidate_state"] == "CONFIRMED"]
        rows.append(
            {
                "trading_date": trading_date,
                "candidate_rows_evaluated": len(group),
                "setup_eligible": len(eligible),
                "setup_rejected": len(group) - len(eligible),
                "strong_count": count_quality(group, "STRONG"),
                "valid_count": count_quality(group, "VALID"),
                "watch_count": count_quality(group, "WATCH"),
                "poor_count": count_quality(group, "POOR"),
                "emerging_rows": len(emerging),
                "emerging_setup_eligible": sum(1 for row in emerging if row["setup_eligible"]),
                "confirmed_rows": len(confirmed),
                "confirmed_setup_eligible": sum(1 for row in confirmed if row["setup_eligible"]),
                "candidate_setup_pass_rate_pct": pct(len(eligible), len(group)),
                "emerging_setup_pass_rate_pct": pct(sum(1 for row in emerging if row["setup_eligible"]), len(emerging)),
                "confirmed_setup_pass_rate_pct": pct(sum(1 for row in confirmed if row["setup_eligible"]), len(confirmed)),
                "pathology_flag": "SETUP_EXPLOSION" if len(eligible) >= 250 else "",
            }
        )
    return rows


def generation_summary(setup_rows: Sequence[dict[str, Any]], daily_counts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    quality_counts = Counter(row["setup_quality"] for row in setup_rows)
    setup_status_counts = Counter(row["setup_status"] for row in setup_rows)
    eligible_count = sum(1 for row in setup_rows if row["setup_eligible"])
    emerging = [row for row in setup_rows if row["candidate_state"] == "EMERGING"]
    confirmed = [row for row in setup_rows if row["candidate_state"] == "CONFIRMED"]
    per_day_eligible = [int(row["setup_eligible"]) for row in daily_counts]
    return {
        "candidate_rows_evaluated": len(setup_rows),
        "setup_eligible_count": eligible_count,
        "setup_rejected_count": len(setup_rows) - eligible_count,
        "quality_counts": dict(quality_counts),
        "setup_status_counts": dict(setup_status_counts),
        "strong_count": quality_counts["STRONG"],
        "valid_count": quality_counts["VALID"],
        "watch_count": quality_counts["WATCH"],
        "poor_count": quality_counts["POOR"],
        "emerging_rows": len(emerging),
        "emerging_setup_eligible": sum(1 for row in emerging if row["setup_eligible"]),
        "confirmed_rows": len(confirmed),
        "confirmed_setup_eligible": sum(1 for row in confirmed if row["setup_eligible"]),
        "candidate_setup_pass_rate_pct": pct(eligible_count, len(setup_rows)),
        "emerging_setup_pass_rate_pct": pct(sum(1 for row in emerging if row["setup_eligible"]), len(emerging)),
        "confirmed_setup_pass_rate_pct": pct(sum(1 for row in confirmed if row["setup_eligible"]), len(confirmed)),
        "per_day_setup_eligible_distribution": distribution(per_day_eligible),
        "pathological_setup_explosions": sum(1 for row in daily_counts if row["pathology_flag"]),
        "major_rejection_reasons": {
            row["reason_code"]: row["count"] for row in rejection_summary_rows(setup_rows)[:20]
        },
    }


def rejection_summary_rows(setup_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in setup_rows:
        if row.get("setup_eligible"):
            continue
        for reason in split_codes(row.get("setup_rejection_reasons", "")):
            counter[reason] += 1
    rejected = sum(1 for row in setup_rows if not row.get("setup_eligible"))
    return [{"reason_code": reason, "count": count, "pct": pct(count, rejected)} for reason, count in counter.most_common()]


def component_distribution_rows(setup_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    components = [
        "breakout_state",
        "level_quality",
        "consolidation_state",
        "consolidation_quality",
        "acceptance_state",
        "candle_quality",
        "volume_confirmation",
        "benchmark_rs_context",
        "sector_context_status",
        "extension_risk",
        "overhead_resistance",
        "high_52w_context",
        "reclaim_depth_status",
        "setup_quality",
        "setup_status",
    ]
    rows: list[dict[str, Any]] = []
    total = len(setup_rows)
    for component in components:
        counter = Counter(str(row.get(component, "")) for row in setup_rows)
        rows.extend(
            {"component": component, "state": state, "count": count, "pct": pct(count, total)}
            for state, count in counter.most_common()
        )
    return rows


def compact_component_distributions(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    compact: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        compact[row["component"]][row["state"]] = {"count": row["count"], "pct": row["pct"]}
    return dict(compact)


def select_pilot_rows(
    setup_rows: Sequence[dict[str, Any]],
    extra_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    criteria = [
        ("clean_20d_breakout", lambda row: row["breakout_state"] == "CLOSE_ACCEPTED" and not split_codes(row["false_breakout_flags"])),
        ("approaching_breakout", lambda row: row["breakout_state"] == "APPROACHING"),
        ("strong_continuation", lambda row: "MOMENTUM_CONTINUATION" in split_codes(row["setup_type_flags"]) and row["setup_quality"] == "STRONG"),
        ("failed_intraday_breakout", lambda row: "INTRADAY_BREAK_FAILED" in split_codes(row["false_breakout_flags"]) or row["breakout_state"] == "FAILED_BREAK"),
        ("large_upper_wick", lambda row: "UPPER_WICK_REJECTION" in split_codes(row["false_breakout_flags"]) or parse_decimal(row.get("upper_wick_pct")) is not None and parse_decimal(row.get("upper_wick_pct")) >= Decimal("0.025")),
        ("tight_consolidation_breakout", lambda row: "CONSOLIDATION_BREAKOUT" in split_codes(row["setup_type_flags"]) and row["consolidation_state"] in {"TIGHT", "VERY_TIGHT"}),
        ("loose_or_noisy_consolidation", lambda row: row["consolidation_state"] in {"LOOSE", "NONE"}),
        ("emerging_low_rvol_candidate", lambda row: row["candidate_state"] == "EMERGING" and decimal_lt(row.get("relative_volume_20d"), Decimal("1.20"))),
        ("confirmed_strong_rvol_candidate", lambda row: row["candidate_state"] == "CONFIRMED" and row["volume_confirmation"] in {"STRONG", "EXCEPTIONAL"}),
    ]
    for example_type, predicate in criteria:
        row = first_setup_row(setup_rows, predicate)
        add_pilot_setup_row(selected, examples, seen, row, example_type)

    add_pilot_setup_row(
        selected,
        examples,
        seen,
        first_setup_row(extra_rows, lambda row: row["research_status"] == "BLOCKED"),
        "corporate_action_blocked_candidate",
        optional=True,
    )
    add_pilot_setup_row(
        selected,
        examples,
        seen,
        first_setup_row(list(setup_rows) + list(extra_rows), lambda row: row["symbol"] == "INFIBEAM"),
        "infibeam_or_excluded_case",
        optional=True,
    )
    return selected, examples


def validate_pilot_rows(
    pilot_rows: Sequence[dict[str, Any]],
    examples: Sequence[dict[str, Any]],
    config: DailySetupEvaluationConfig,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    example_types = {item["example_type"] for item in examples if item["found"]}
    required_examples = {
        "clean_20d_breakout",
        "approaching_breakout",
        "strong_continuation",
        "failed_intraday_breakout",
        "large_upper_wick",
        "tight_consolidation_breakout",
        "loose_or_noisy_consolidation",
        "emerging_low_rvol_candidate",
        "confirmed_strong_rvol_candidate",
    }
    for example_type in sorted(required_examples):
        rows.append(
            pilot_validation_row(
                {},
                example_type=example_type,
                check_name="example_coverage",
                observed=example_type in example_types,
                rule="Pilot must include this actual historical example type.",
                passed=example_type in example_types,
                explanation=f"Example found: {example_type in example_types}.",
            )
        )

    for row in pilot_rows:
        rows.extend(manual_validation_rows(row, config))

    return {"passed": all(row["result"] != "FAIL" for row in rows), "rows": rows}


def manual_validation_rows(row: dict[str, Any], config: DailySetupEvaluationConfig) -> list[dict[str, Any]]:
    unavailable_allowed = row.get("setup_status") in {"BLOCKED", "UNAVAILABLE"}
    reclaim_depth = parse_decimal(row.get("reclaim_depth_pct"))
    low = parse_decimal(row.get("adjusted_low"))
    close = parse_decimal(row.get("adjusted_close"))
    prior_high = parse_decimal(row.get("prior_high_20d"))
    expected_reclaim = bool(prior_high is not None and low is not None and close is not None and low < prior_high < close)
    volume = max_decimal(parse_decimal(row.get("relative_volume_20d")), parse_decimal(row.get("relative_volume_5d")))
    return [
        pilot_validation_row(row, check_name="prior_high_present", observed=row.get("prior_high_20d"), rule="prior_high_20d must be explicit and prior-window based when research is available.", passed=bool(row.get("prior_high_20d")) or unavailable_allowed, explanation="Breakout state is anchored to prior_high_20d when the row is not blocked/unavailable."),
        pilot_validation_row(row, check_name="breakout_state", observed=row.get("breakout_state"), rule="Breakout state must be one DAILY_EOD state or unavailable when research is blocked.", passed=row.get("breakout_state") not in {""} and (row.get("breakout_state") != "UNAVAILABLE" or unavailable_allowed), explanation="State uses close/high versus prior 20d high only."),
        pilot_validation_row(row, check_name="daily_reclaim_formula", observed=row.get("daily_level_reclaim"), rule="low_T < prior_high_20d and close_T > prior_high_20d.", passed=truthy(row.get("daily_level_reclaim")) == expected_reclaim, explanation="No intraday retest is reconstructed."),
        pilot_validation_row(row, check_name="candle_quality_inputs", observed=f"CLV={row.get('close_location_value')};upper={row.get('upper_wick_pct')};body={row.get('body_pct')}", rule="Candle quality uses body, upper wick, and close location when available.", passed=row.get("candle_quality") not in {""} and (row.get("candle_quality") != "UNAVAILABLE" or unavailable_allowed), explanation=f"Candle quality is {row.get('candle_quality')}."),
        pilot_validation_row(row, check_name="volume_bucket", observed=volume, rule=f"Volume bands use {config.volume.normal_threshold}/{config.volume.good_threshold}/{config.volume.strong_threshold}/{config.volume.exceptional_threshold} when available.", passed=row.get("volume_confirmation") not in {""} and (row.get("volume_confirmation") != "UNKNOWN" or unavailable_allowed), explanation=f"Volume confirmation is {row.get('volume_confirmation')}."),
        pilot_validation_row(row, check_name="extension_context", observed=row.get("extension_risk"), rule="Extension uses ATR multiples, SMA distance, and candidate extension metadata.", passed=row.get("extension_risk") not in {""}, explanation=f"Extension risk is {row.get('extension_risk')}."),
        pilot_validation_row(row, check_name="consolidation_classification", observed=f"{row.get('consolidation_state')}/{row.get('consolidation_quality')}", rule="Consolidation uses range width, ATR contraction, and high proximity.", passed=row.get("consolidation_state") not in {""}, explanation="No optimized thresholds are used."),
        pilot_validation_row(row, check_name="setup_quality_descriptor", observed=row.get("setup_quality"), rule="Descriptor must be POOR, WATCH, VALID, or STRONG.", passed=row.get("setup_quality") in {"POOR", "WATCH", "VALID", "STRONG"}, explanation="This is not an entry score."),
        pilot_validation_row(row, check_name="setup_eligibility_boolean", observed=row.get("setup_eligible"), rule="Eligibility must remain a technical setup handoff flag only.", passed=isinstance(row.get("setup_eligible"), bool), explanation=f"Rejection reasons: {row.get('setup_rejection_reasons') or 'none'}."),
        pilot_validation_row(row, check_name="reclaim_depth_status", observed=f"{row.get('reclaim_depth_status')};depth={reclaim_depth}", rule="Reclaim depth is shallow/moderate/deep only when daily reclaim is true.", passed=(not expected_reclaim and row.get("reclaim_depth_status") in {"NONE", "UNAVAILABLE"}) or (expected_reclaim and row.get("reclaim_depth_status") in {"SHALLOW", "MODERATE", "DEEP"}), explanation="Daily OHLC only; no 5m/10m retest claim."),
    ]


def pilot_validation_row(
    row: dict[str, Any],
    *,
    check_name: str,
    observed: Any,
    rule: str,
    passed: bool,
    explanation: str,
    example_type: str | None = None,
) -> dict[str, Any]:
    return {
        "example_type": example_type or row.get("example_type", ""),
        "symbol": row.get("symbol", ""),
        "trading_date": row.get("trading_date", ""),
        "candidate_state": row.get("candidate_state", ""),
        "setup_quality": row.get("setup_quality", ""),
        "setup_eligible": row.get("setup_eligible", ""),
        "check_name": check_name,
        "observed": observed,
        "threshold_or_rule": rule,
        "result": "PASS" if passed else "FAIL",
        "explanation": explanation,
    }


def methodology_summary() -> dict[str, Any]:
    return {
        "boundary": "Daily EOD setup quality only; not final entry scoring and not a trade signal.",
        "timing": "For date T, data through close of T is allowed and output is NEXT_SESSION_DECISION_INPUT.",
        "candidate_vs_setup_vs_entry": {
            "candidate": "Which stocks deserve further attention.",
            "setup": "Whether the current technical breakout or continuation structure is credible.",
            "entry": "A later layer may decide whether to enter; not implemented here.",
        },
        "breakout_states": [
            "APPROACHING",
            "TESTING",
            "INTRADAY_BREAK_ONLY",
            "CLOSE_ABOVE",
            "CLOSE_ACCEPTED",
            "FAILED_BREAK",
            "NOT_NEAR_LEVEL",
            "UNAVAILABLE",
        ],
        "setup_quality": "POOR/WATCH/VALID/STRONG deterministic descriptor from transparent components.",
        "sector_policy": "Historical sector RS is preserved as status metadata and is not mandatory.",
        "daily_reclaim_limitation": "Daily low below prior high and close above prior high is only coarse daily reclaim context.",
    }


def write_daily_setup_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    dist = generation["per_day_setup_eligible_distribution"]
    examples = report["pilot"]["examples"]
    lines = [
        "# Daily Breakout Setup Evaluation",
        "",
        "Current phase: Step 02.6 / Command 01 - breakout-quality and daily entry-setup evaluation foundation",
        "",
        "## Boundary",
        "",
        "- Setup Evaluation is not the final Entry Engine.",
        "- It creates setup state, quality descriptors, evidence, and warnings only.",
        "- No final 0-100 entry score, Entry Eligible band, High Conviction band, stop loss, target, risk/reward, position sizing, future outcome labels, backtesting, paper trading, live feeds, orders, migrations, or Supabase persistence are implemented.",
        "",
        "## Version",
        "",
        f"- Setup methodology: {report['setup_evaluator']['setup_version']}",
        f"- Setup config hash: {report['setup_evaluator']['setup_config_hash']}",
        f"- Candidate input: {report['inputs']['candidate_version']} / {report['inputs']['candidate_config_hash']}",
        f"- Feature input: {report['inputs']['feature_version']}",
        "",
        "## Architecture",
        "",
        "- Momentum Candidate Snapshot + DAILY_FEATURES_V1 + adjusted daily OHLC feed deterministic setup components.",
        "- Output availability is EOD and intended for NEXT_SESSION_DECISION_INPUT.",
        "- Candidate, setup, and future entry layers remain separate.",
        "",
        "## Methodology",
        "",
        "- Breakout states: APPROACHING, TESTING, INTRADAY_BREAK_ONLY, CLOSE_ABOVE, CLOSE_ACCEPTED, FAILED_BREAK, NOT_NEAR_LEVEL.",
        "- Level quality uses prior 20-session touch count, days since prior high, proximity to level, and range compression.",
        "- Consolidation uses 5d/10d/20d range width, ATR contraction, and price proximity to highs.",
        "- Acceptance uses close above prior high, close distance, close location, body, upper wick, volume support, and benchmark RS support.",
        "- Candle quality uses close location value, body size, and upper-wick size.",
        "- Volume confirmation is descriptive: WEAK, NORMAL, GOOD, STRONG, EXCEPTIONAL.",
        "- Benchmark RS is WEAK, NEUTRAL, POSITIVE, STRONG, or UNKNOWN if unavailable.",
        "- Sector context is preserved as metadata and not used as mandatory evidence.",
        "- Extension risk uses ATR multiples, SMA20 distance, and candidate-layer extension diagnostics.",
        "- False-breakout warnings are same-day technical flags only.",
        "- Daily reclaim is coarse daily context only: low_T below prior high and close_T above prior high.",
        "- Overhead resistance and 52w context use prior/current daily levels only.",
        "- Momentum continuation is allowed where structure, momentum, candle, RS, and extension still support continuation.",
        "- Setup quality is a descriptor only: POOR, WATCH, VALID, STRONG.",
        "",
        "## Full Generation",
        "",
        f"- Full generation completed: {generation['full_generation_completed']}",
        f"- Candidate rows evaluated: {generation['candidate_rows_evaluated']}",
        f"- Setup eligible: {generation['setup_eligible_count']}",
        f"- Setup rejected: {generation['setup_rejected_count']}",
        f"- STRONG: {generation['strong_count']}",
        f"- VALID: {generation['valid_count']}",
        f"- WATCH: {generation['watch_count']}",
        f"- POOR: {generation['poor_count']}",
        f"- Emerging pass rate: {generation['emerging_setup_pass_rate_pct']}%",
        f"- Confirmed pass rate: {generation['confirmed_setup_pass_rate_pct']}%",
        f"- Per-day setup eligible: min={dist['min']}, median={dist['median']}, mean={dist['mean']}, p90={dist['p90']}, p95={dist['p95']}, max={dist['max']}",
        f"- Setup dataset: {report['outputs']['setup_dataset']}",
        "",
        "## Pilot Examples",
        "",
    ]
    for example in examples:
        status = "found" if example["found"] else "not found"
        lines.append(
            f"- {example['example_type']}: {status}; {example.get('symbol', '')} {example.get('trading_date', '')} {example.get('setup_quality', '')} {example.get('breakout_state', '')}".rstrip()
        )
    lines.extend(
        [
            "",
            "## Major Rejection Reasons",
            "",
        ]
    )
    for reason, count in list(generation["major_rejection_reasons"].items())[:20]:
        lines.append(f"- {reason}: {count}")
    lines.extend(
        [
            "",
            "## Integrity And Safety",
            "",
            f"- DAILY_FEATURES_V1 unchanged: {report['integrity']['daily_features_v1_unchanged']}",
            f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['integrity']['momentum_candidates_v1_unchanged']}",
            f"- Candidate config hash unchanged: {report['integrity']['candidate_config_hash_unchanged']}",
            "- ZERO orders were placed.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "",
            "## Known Limitations",
            "",
            "- No intraday opening-range breakout or precise intraday retest/reclaim detection is attempted.",
            "- No future price outcome, target, stop, MFE, MAE, or winner/loser labels are generated.",
            "- Historical sector-relative strength remains metadata-only when sector mapping is current-only.",
            "- Thresholds are baseline research defaults, not optimized parameters.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_setup_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SETUP_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def ohlc_index(history: dict[str, list[AdjustedDailyOhlc]]) -> dict[tuple[str, str], int]:
    return {
        (bar.trading_date, symbol): index
        for symbol, bars in history.items()
        for index, bar in enumerate(bars)
    }


def flatten_by_date(rows_by_date: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row for trading_date in sorted(rows_by_date) for row in sorted(rows_by_date[trading_date], key=lambda item: item["symbol"])]


def add_pilot_setup_row(
    selected: list[dict[str, Any]],
    examples: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    row: dict[str, Any] | None,
    example_type: str,
    *,
    optional: bool = False,
) -> None:
    if row is None:
        examples.append({"example_type": example_type, "found": False, "optional": optional})
        return
    key = (row["trading_date"], row["symbol"])
    enriched = dict(row)
    enriched["example_type"] = example_type
    if key not in seen:
        selected.append(enriched)
        seen.add(key)
    examples.append(
        {
            "example_type": example_type,
            "found": True,
            "optional": optional,
            "symbol": row["symbol"],
            "trading_date": row["trading_date"],
            "candidate_state": row["candidate_state"],
            "setup_quality": row["setup_quality"],
            "setup_eligible": row["setup_eligible"],
            "breakout_state": row["breakout_state"],
            "volume_confirmation": row["volume_confirmation"],
            "rejection_reasons": row["setup_rejection_reasons"],
        }
    )


def first_setup_row(rows: Sequence[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    return next((row for row in rows if predicate(row)), None)


def first_candidate_row(
    rows: Sequence[dict[str, str]],
    predicate: Any,
    *,
    exclude_keys: set[tuple[str, str]],
) -> dict[str, str] | None:
    return next(
        (
            row
            for row in rows
            if predicate(row)
            and (row.get("trading_date", ""), canonical_symbol(row.get("symbol", ""))) not in exclude_keys
        ),
        None,
    )


def count_quality(rows: Sequence[dict[str, Any]], quality: str) -> int:
    return sum(1 for row in rows if row["setup_quality"] == quality)


def observed_candidate_config_hash(rows: Sequence[dict[str, Any]]) -> str:
    values = sorted({str(row.get("candidate_config_hash", "")) for row in rows if row.get("candidate_config_hash")})
    return values[0] if len(values) == 1 else ";".join(values)


def candidate_rank(row: dict[str, Any]) -> str:
    if str(row.get("candidate_state", "")).upper() == "CONFIRMED":
        return str(row.get("confirmed_rank", ""))
    return str(row.get("emerging_rank", ""))


def candidate_percentile(row: dict[str, Any]) -> str:
    if str(row.get("candidate_state", "")).upper() == "CONFIRMED":
        return str(row.get("confirmed_percentile", ""))
    return str(row.get("emerging_percentile", ""))


def metadata_string(values: dict[str, Any]) -> str:
    return ";".join(f"{key}={format_metadata_value(value)}" for key, value in sorted(values.items()))


def format_metadata_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format_decimal(value)
    return str(value)


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0"
    return format((Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(Decimal("0.0001")), "f")


def decimal_lt(value: Any, threshold: Decimal) -> bool:
    parsed = parse_decimal(value)
    return parsed is not None and parsed < threshold


def max_decimal(*values: Decimal | None) -> Decimal | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in {None, ""}:
            return value
    return ""


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0

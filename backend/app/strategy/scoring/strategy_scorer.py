from __future__ import annotations

import csv
import gzip
import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.risk.risk_baseline import UPSTREAM_HASHES
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    RISK_STRUCTURE_VERSION,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
)
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.momentum_candidates import file_sha256, split_codes
from app.strategy.scoring.score_baseline import resolve_strategy_score_dataset
from app.strategy.scoring.catalyst_score import score_catalyst
from app.strategy.scoring.component_models import ComponentScore, decimal_value
from app.strategy.scoring.momentum_score import score_momentum
from app.strategy.scoring.regime_score import score_regime
from app.strategy.scoring.relative_strength_score import score_relative_strength
from app.strategy.scoring.reward_risk_score import score_reward_risk
from app.strategy.scoring.score_config import (
    STRATEGY_SCORE_VERSION,
    SWING_DAILY_EOD_PROFILE,
    StrategyScoreConfig,
)
from app.strategy.scoring.sector_score import score_sector
from app.strategy.scoring.setup_score import score_setup
from app.strategy.scoring.volume_score import score_relative_volume

COMPONENT_PREFIXES = (
    "setup",
    "momentum",
    "rvol",
    "relative_strength",
    "regime",
    "sector",
    "catalyst",
    "reward_risk",
)
SCORE_MODES = ("FULL_SCORE", "PREVIEW_SCORE", "EXCEPTIONAL_REVIEW_SCORE", "NOT_SCORE_ELIGIBLE")
SCORING_DISPOSITIONS = (
    "NOT_ELIGIBLE",
    "INSUFFICIENT_COVERAGE",
    "PREVIEW_ONLY",
    "EXCEPTIONAL_REVIEW",
    "ENTRY_ELIGIBLE",
    "HIGH_CONVICTION",
)

SCORE_OUTPUT_FIELDS = [
    "trading_date",
    "symbol",
    "isin",
    "score_version",
    "score_config_hash",
    "score_profile",
    "trading_profile",
    "score_availability",
    "decision_use",
    "feature_version",
    "candidate_version",
    "setup_version",
    "regime_version",
    "entry_version",
    "risk_version",
    "risk_config_hash",
    "score_mode",
    "upstream_progression_status",
    "risk_readiness",
    "exceptional_long_status",
]
for _prefix in COMPONENT_PREFIXES:
    SCORE_OUTPUT_FIELDS.extend(
        [
            f"{_prefix}_points",
            f"{_prefix}_max_points",
            f"{_prefix}_availability",
            f"{_prefix}_basis",
        ]
    )
SCORE_OUTPUT_FIELDS.extend(
    [
        "raw_strategy_score",
        "available_weight",
        "score_coverage_pct",
        "minimum_score_coverage_pct",
        "normalized_available_score",
        "normalized_score_usage",
        "score_band",
        "scoring_disposition",
        "setup_quality",
        "candidate_state",
        "candidate_category",
        "regime_state",
        "regime_confidence",
        "reward_risk_ratio",
        "selected_stop_basis",
        "warning_flags",
        "penalty_codes",
        "max_penalty_severity",
        "blocking_penalty_present",
        "risk_rejection_reasons",
        "final_strategy_score_status",
        "trade_signal_status",
        "execution_status",
    ]
)

DAILY_REPORT_FIELDS = [
    "trading_date",
    "total_rows",
    "full_score",
    "preview_score",
    "exceptional_review_score",
    "not_score_eligible",
    "risk_ready_rows",
    "raw_gte_80",
    "raw_gte_90",
    "entry_eligible",
    "high_conviction",
    "exceptional_review",
    "insufficient_coverage",
    "median_raw_score",
    "mean_raw_score",
]
COMPONENT_REPORT_FIELDS = [
    "component",
    "component_max_points",
    "available_count",
    "unavailable_count",
    "average_points",
    "median_points",
    "average_pct_of_max",
    "zero_frequency",
    "full_score_frequency",
]
REGIME_REPORT_FIELDS = [
    "regime_state",
    "rows",
    "median_raw_score",
    "p90_raw_score",
    "raw_gte_80",
    "raw_gte_90",
    "entry_eligible",
    "high_conviction",
    "exceptional_review",
]
CATEGORY_REPORT_FIELDS = [
    "candidate_category",
    "rows",
    "median_raw_score",
    "raw_gte_80",
    "entry_eligible",
]
SETUP_REPORT_FIELDS = [
    "setup_quality",
    "rows",
    "median_raw_score",
    "raw_gte_80",
    "entry_eligible",
]
COVERAGE_REPORT_FIELDS = ["score_coverage_pct", "rows", "pct"]
THRESHOLD_REPORT_FIELDS = ["raw_score_threshold", "rows", "pct", "entry_eligible", "high_conviction"]
PILOT_REPORT_FIELDS = [
    "pilot_case",
    "symbol",
    "trading_date",
    "score_mode",
    "component_points",
    "raw_strategy_score",
    "arithmetic_sum",
    "available_weight",
    "score_coverage_pct",
    "normalized_available_score",
    "score_band",
    "scoring_disposition",
    "expected_semantics",
    "result",
]
REDUNDANCY_REPORT_FIELDS = [
    "component_a",
    "component_b",
    "rows",
    "pearson_correlation",
    "identical_normalized_value_rate_pct",
    "obvious_double_counting_risk",
]
PROHIBITED_SCORE_FIELD_TOKENS = (
    "future_return",
    "forward_return",
    "target_hit",
    "stop_hit",
    "mfe",
    "mae",
    "winner",
    "loser",
    "pnl",
    "sharpe",
    "drawdown",
    "profit_factor",
    "expectancy",
    "trade_outcome",
)


@dataclass(frozen=True, slots=True)
class StrategyScoreEngineConfig:
    data_dir: Path
    score_config: StrategyScoreConfig = StrategyScoreConfig()
    full_generation: bool = True
    enforce_frozen_hashes: bool = True

    @property
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def candidate_dataset_path(self) -> Path:
        return self.data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"

    @property
    def setup_dataset_path(self) -> Path:
        return self.data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz"

    @property
    def regime_dataset_path(self) -> Path:
        return self.data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz"

    @property
    def entry_dataset_path(self) -> Path:
        return self.data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz"

    @property
    def risk_v1_dataset_path(self) -> Path:
        return resolve_risk_structure_dataset(self.data_dir, RISK_STRUCTURE_VERSION)

    @property
    def current_risk_dataset_path(self) -> Path:
        return resolve_current_risk_structure_dataset(self.data_dir)

    @property
    def output_dataset_path(self) -> Path:
        return resolve_strategy_score_dataset(
            self.data_dir,
            profile=self.score_config.score_profile,
            version=self.score_config.score_version,
        )

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_summary.json"

    @property
    def daily_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_daily_distribution.csv"

    @property
    def components_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_components.csv"

    @property
    def regimes_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_regimes.csv"

    @property
    def candidate_categories_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_candidate_categories.csv"

    @property
    def setup_quality_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_setup_quality.csv"

    @property
    def coverage_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_coverage.csv"

    @property
    def thresholds_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_thresholds.csv"

    @property
    def pilot_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_pilot_validation.csv"

    @property
    def redundancy_path(self) -> Path:
        return self.reports_dir / "strategy_score_v1_redundancy.csv"


def build_strategy_scores(
    *,
    config: StrategyScoreEngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    if config.score_config.weights.total() != Decimal("100"):
        raise ValueError("Strategy score component weights must sum to 100")

    hashes_before = input_hashes(config)
    if config.enforce_frozen_hashes:
        verify_frozen_hashes(hashes_before)
    notify(progress, "Loading current risk baseline through the central resolver")
    risk_rows = read_gzip_rows(config.current_risk_dataset_path)
    observed_risk_versions = {row.get("risk_version", "") for row in risk_rows}
    observed_risk_hashes = {row.get("risk_config_hash", "") for row in risk_rows}
    if observed_risk_versions != {CURRENT_RISK_STRUCTURE_VERSION}:
        raise ValueError(f"Current risk version mismatch: {sorted(observed_risk_versions)}")
    if observed_risk_hashes != {CURRENT_RISK_STRUCTURE_CONFIG_HASH}:
        raise ValueError(f"Current risk config hash mismatch: {sorted(observed_risk_hashes)}")

    keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in risk_rows}
    notify(progress, "Joining frozen candidate, setup, and entry evidence")
    candidate_lookup = load_lookup(config.candidate_dataset_path, keys)
    setup_lookup = load_lookup(config.setup_dataset_path, keys)
    entry_lookup = load_lookup(config.entry_dataset_path, keys)
    missing_inputs = {
        "candidate": len(keys - set(candidate_lookup)),
        "setup": len(keys - set(setup_lookup)),
        "entry": len(keys - set(entry_lookup)),
    }
    if any(missing_inputs.values()):
        raise ValueError(f"Missing frozen scoring inputs: {missing_inputs}")

    notify(progress, "Calculating deterministic component and total scores")
    score_rows = evaluate_score_rows(
        risk_rows=risk_rows,
        candidate_lookup=candidate_lookup,
        setup_lookup=setup_lookup,
        entry_lookup=entry_lookup,
        config=config.score_config,
    )
    pilot_rows, pilot_summary = build_pilot_validation(score_rows)
    daily_rows = daily_distribution(score_rows)
    component_rows = component_distribution(score_rows)
    regime_rows = regime_distribution(score_rows)
    candidate_rows = candidate_category_distribution(score_rows)
    setup_rows = setup_quality_distribution(score_rows)
    coverage_rows = coverage_distribution(score_rows)
    threshold_rows = threshold_distribution(score_rows, config.score_config)
    redundancy_rows = redundancy_report(score_rows)
    rr_bands = grouped_score_summary(score_rows, "reward_risk_band")
    score_stats = score_distribution(score_rows)
    mode_stats = {
        mode: score_distribution([row for row in score_rows if row["score_mode"] == mode])
        for mode in SCORE_MODES
    }
    funnel = score_funnel(score_rows)

    write_csv(config.daily_path, daily_rows, DAILY_REPORT_FIELDS)
    write_csv(config.components_path, component_rows, COMPONENT_REPORT_FIELDS)
    write_csv(config.regimes_path, regime_rows, REGIME_REPORT_FIELDS)
    write_csv(config.candidate_categories_path, candidate_rows, CATEGORY_REPORT_FIELDS)
    write_csv(config.setup_quality_path, setup_rows, SETUP_REPORT_FIELDS)
    write_csv(config.coverage_path, coverage_rows, COVERAGE_REPORT_FIELDS)
    write_csv(config.thresholds_path, threshold_rows, THRESHOLD_REPORT_FIELDS)
    write_csv(config.pilot_path, pilot_rows, PILOT_REPORT_FIELDS)
    write_csv(config.redundancy_path, redundancy_rows, REDUNDANCY_REPORT_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_summary["passed"]:
        notify(progress, "Writing full STRATEGY_SCORE_V1 dataset")
        write_score_rows(config.output_dataset_path, score_rows)
        full_generation_completed = True

    hashes_after = input_hashes(config)
    regression = {name: hashes_before[name] == hashes_after[name] for name in hashes_before}
    prohibited_fields = prohibited_outcome_fields(SCORE_OUTPUT_FIELDS)
    invariant_violations = scoring_invariant_violations(score_rows, config.score_config)
    promotion = {
        "current_risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "current_risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "resolved_dataset": str(config.current_risk_dataset_path),
        "dataset_hash": hashes_after["risk_v1_1"],
    }
    report = {
        "phase": "Step 02.10",
        "command": "Command 01",
        "generated_at": generated_at,
        "score": {
            "score_version": config.score_config.score_version,
            "score_config_hash": config.score_config.config_hash(),
            "score_profile": config.score_config.score_profile,
            "trading_profile": SWING_DAILY_EOD_PROFILE,
            "weights": config.score_config.snapshot()["weights"],
            "weight_total": format(config.score_config.weights.total(), "f"),
            "minimum_score_coverage_pct": format(config.score_config.thresholds.minimum_score_coverage_pct, "f"),
            "entry_threshold": format(config.score_config.thresholds.entry_eligible, "f"),
            "high_conviction_threshold": format(config.score_config.thresholds.high_conviction, "f"),
        },
        "risk_input": promotion,
        "config_snapshot": config.score_config.snapshot(),
        "inputs": {
            "rows": len(risk_rows),
            "missing_joined_rows": missing_inputs,
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
        },
        "methodology": {
            "principle": "GATES_FIRST_SCORE_SECOND",
            "raw_score": "Sum of available component points on the fixed 0-100 scale; unavailable evidence contributes zero without free points.",
            "available_weight": "Sum of weights whose component availability is AVAILABLE.",
            "coverage": "available_weight / 100 * 100.",
            "normalized_score": "raw_strategy_score / available_weight * 100; DIAGNOSTIC_ONLY and never used for score band or disposition.",
            "penalties": "Preserved separately from score; no numeric subtraction.",
        },
        "pilot": pilot_summary,
        "generation": {
            "pilot_only": not config.full_generation,
            "full_generation_completed": full_generation_completed,
            "output_rows": len(score_rows) if full_generation_completed else 0,
            "dataset_hash": file_sha256(config.output_dataset_path) if full_generation_completed else "",
        },
        "funnel": funnel,
        "score_distribution": score_stats,
        "score_distribution_by_mode": mode_stats,
        "component_distribution": {row["component"]: row for row in component_rows},
        "regime_distribution": {row["regime_state"]: row for row in regime_rows},
        "candidate_category_distribution": {row["candidate_category"]: row for row in candidate_rows},
        "setup_quality_distribution": {row["setup_quality"]: row for row in setup_rows},
        "reward_risk_band_distribution": rr_bands,
        "coverage": coverage_summary(score_rows),
        "threshold_sanity": {
            format(row["raw_score_threshold"], "f"): row for row in threshold_rows
        },
        "max_reachability": {
            "historical_typical_available_weight": "85",
            "bullish_theoretical_max": "85",
            "neutral_theoretical_max": "80",
            "bearish_theoretical_max": "75",
            "high_conviction_reachability": "HIGH_CONVICTION_NOT_REACHABLE_WITH_CURRENT_HISTORICAL_COMPONENT_COVERAGE",
        },
        "redundancy": {
            "pairs": redundancy_rows,
            "obvious_double_counting_risks": [
                row for row in redundancy_rows if row["obvious_double_counting_risk"] == "YES"
            ],
        },
        "leakage": {
            "future_ohlc_loaded": 0,
            "future_rvol_context_loaded": 0,
            "future_benchmark_context_loaded": 0,
            "future_regime_loaded": 0,
            "future_risk_or_outcome_loaded": 0,
            "historical_news_consumed": 0,
            "current_sector_mapping_back_projected": 0,
            "time_key": "Exact trading_date T and symbol joins only.",
        },
        "invariants": invariant_violations,
        "regression": regression,
        "safety": {
            "prohibited_output_fields": prohibited_fields,
            "trade_signals_generated": 0,
            "orders_placed": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "outputs": {
            "dataset": str(config.output_dataset_path),
            "summary": str(config.summary_path),
            "daily_distribution": str(config.daily_path),
            "components": str(config.components_path),
            "regimes": str(config.regimes_path),
            "candidate_categories": str(config.candidate_categories_path),
            "setup_quality": str(config.setup_quality_path),
            "coverage": str(config.coverage_path),
            "thresholds": str(config.thresholds_path),
            "pilot_validation": str(config.pilot_path),
            "redundancy": str(config.redundancy_path),
            "documentation": "docs/strategy-v1-final-scoring.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        pilot_summary["passed"]
        and (full_generation_completed or not config.full_generation)
        and all(regression.values())
        and not prohibited_fields
        and not any(invariant_violations.values())
        and report["safety"]["trade_signals_generated"] == 0
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def evaluate_score_rows(
    *,
    risk_rows: Sequence[dict[str, Any]],
    candidate_lookup: dict[tuple[str, str], dict[str, Any]],
    setup_lookup: dict[tuple[str, str], dict[str, Any]],
    entry_lookup: dict[tuple[str, str], dict[str, Any]],
    config: StrategyScoreConfig,
) -> list[dict[str, Any]]:
    rows = []
    for risk_row in risk_rows:
        key = (str(risk_row.get("trading_date", "")), canonical_symbol(risk_row.get("symbol", "")))
        rows.append(
            score_joined_row(
                risk_row=risk_row,
                candidate_row=candidate_lookup.get(key, {}),
                setup_row=setup_lookup.get(key, {}),
                entry_row=entry_lookup.get(key, {}),
                config=config,
            )
        )
    return rows


def score_joined_row(
    *,
    risk_row: dict[str, Any],
    candidate_row: dict[str, Any],
    setup_row: dict[str, Any],
    entry_row: dict[str, Any],
    config: StrategyScoreConfig = StrategyScoreConfig(),
) -> dict[str, Any]:
    components = {
        "setup": score_setup(setup_row, config),
        "momentum": score_momentum(candidate_row, config),
        "rvol": score_relative_volume(setup_row, config),
        "relative_strength": score_relative_strength(setup_row, config),
        "regime": score_regime(risk_row, entry_row, config),
        "sector": score_sector(config),
        "catalyst": score_catalyst(config),
        "reward_risk": score_reward_risk(risk_row, config),
    }
    raw_score = sum((component.component_points for component in components.values()), Decimal("0"))
    available_weight = sum((component.available_weight for component in components.values()), Decimal("0"))
    coverage = available_weight
    normalized = raw_score / available_weight * Decimal("100") if available_weight > 0 else None
    mode = score_mode(risk_row, entry_row, candidate_row, setup_row)
    band = score_band(raw_score, config)
    disposition = scoring_disposition(
        mode=mode,
        raw_score=raw_score,
        coverage=coverage,
        config=config,
    )
    row: dict[str, Any] = {
        "trading_date": risk_row.get("trading_date", ""),
        "symbol": canonical_symbol(risk_row.get("symbol", "")),
        "isin": risk_row.get("isin", ""),
        "score_version": config.score_version,
        "score_config_hash": config.config_hash(),
        "score_profile": config.score_profile,
        "trading_profile": SWING_DAILY_EOD_PROFILE,
        "score_availability": config.availability,
        "decision_use": config.decision_use,
        "feature_version": risk_row.get("feature_version", ""),
        "candidate_version": risk_row.get("candidate_version", ""),
        "setup_version": risk_row.get("setup_version", ""),
        "regime_version": risk_row.get("regime_version", ""),
        "entry_version": risk_row.get("entry_version", ""),
        "risk_version": risk_row.get("risk_version", ""),
        "risk_config_hash": risk_row.get("risk_config_hash", ""),
        "score_mode": mode,
        "upstream_progression_status": upstream_progression_status(mode, risk_row),
        "risk_readiness": risk_row.get("risk_readiness", ""),
        "exceptional_long_status": entry_row.get("exceptional_long_status", "NOT_EXCEPTIONAL"),
    }
    for prefix, component in components.items():
        row.update(component.output_fields(prefix))
    warning_flags = sorted(
        set(split_codes(risk_row.get("warning_flags", "")))
        | set(split_codes(entry_row.get("warning_evidence", "")))
    )
    row.update(
        {
            "raw_strategy_score": raw_score,
            "available_weight": available_weight,
            "score_coverage_pct": coverage,
            "minimum_score_coverage_pct": config.thresholds.minimum_score_coverage_pct,
            "normalized_available_score": normalized,
            "normalized_score_usage": config.normalized_score_usage,
            "score_band": band,
            "scoring_disposition": disposition,
            "setup_quality": setup_row.get("setup_quality", risk_row.get("setup_quality", "")),
            "candidate_state": candidate_row.get("candidate_state", risk_row.get("candidate_state", "")),
            "candidate_category": candidate_category(candidate_row, entry_row),
            "regime_state": risk_row.get("regime_state", "UNAVAILABLE"),
            "regime_confidence": entry_row.get("regime_confidence_state", "UNAVAILABLE"),
            "reward_risk_ratio": risk_row.get("reward_risk_ratio", ""),
            "selected_stop_basis": risk_row.get("invalidation_basis", ""),
            "warning_flags": ";".join(warning_flags),
            "penalty_codes": entry_row.get("penalty_codes", ""),
            "max_penalty_severity": entry_row.get("max_penalty_severity", ""),
            "blocking_penalty_present": entry_row.get("blocking_penalty_present", ""),
            "risk_rejection_reasons": risk_row.get("rejection_reasons", ""),
            "final_strategy_score_status": "CALCULATED_RESEARCH_ONLY",
            "trade_signal_status": config.trade_signal_status,
            "execution_status": config.execution_status,
            "reward_risk_band": reward_risk_band(risk_row.get("reward_risk_ratio")),
        }
    )
    return row


def score_mode(
    risk_row: dict[str, Any],
    entry_row: dict[str, Any],
    candidate_row: dict[str, Any],
    setup_row: dict[str, Any],
) -> str:
    readiness = str(risk_row.get("entry_readiness", "")).upper()
    if readiness == "CONDITIONALLY_READY" or risk_row.get("risk_mode") == "PREVIEW_ONLY":
        return "PREVIEW_SCORE"
    if readiness == "EXCEPTIONAL_LONG_REVIEW":
        return "EXCEPTIONAL_REVIEW_SCORE"
    upstream_present = bool(candidate_row and setup_row and entry_row)
    no_blocking_penalty = not truthy(entry_row.get("blocking_penalty_present"))
    no_risk_rejection = not split_codes(risk_row.get("rejection_reasons", ""))
    if (
        upstream_present
        and risk_row.get("risk_mode") == "FULL_EVALUATION"
        and risk_row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"
        and no_blocking_penalty
        and no_risk_rejection
    ):
        return "FULL_SCORE"
    return "NOT_SCORE_ELIGIBLE"


def scoring_disposition(
    *,
    mode: str,
    raw_score: Decimal,
    coverage: Decimal,
    config: StrategyScoreConfig,
) -> str:
    if mode == "PREVIEW_SCORE":
        return "PREVIEW_ONLY"
    if mode == "EXCEPTIONAL_REVIEW_SCORE":
        return "EXCEPTIONAL_REVIEW"
    if mode != "FULL_SCORE":
        return "NOT_ELIGIBLE"
    if coverage < config.thresholds.minimum_score_coverage_pct:
        return "INSUFFICIENT_COVERAGE"
    if raw_score >= config.thresholds.high_conviction:
        return "HIGH_CONVICTION"
    if raw_score >= config.thresholds.entry_eligible:
        return "ENTRY_ELIGIBLE"
    return "NOT_ELIGIBLE"


def score_band(raw_score: Decimal, config: StrategyScoreConfig) -> str:
    if raw_score >= config.thresholds.high_conviction:
        return "HIGH_CONVICTION_SCORE"
    if raw_score >= config.thresholds.entry_eligible:
        return "ENTRY_ELIGIBLE_SCORE"
    return "BELOW_THRESHOLD"


def upstream_progression_status(mode: str, risk_row: dict[str, Any]) -> str:
    if mode == "FULL_SCORE":
        return "PASSED_ALL_MANDATORY_GATES"
    if mode == "PREVIEW_SCORE":
        return "UPSTREAM_CONDITIONAL_PREVIEW"
    if mode == "EXCEPTIONAL_REVIEW_SCORE":
        return "UPSTREAM_EXCEPTIONAL_LONG_REVIEW"
    return f"BLOCKED_{risk_row.get('risk_readiness', 'UNKNOWN')}"


def candidate_category(candidate_row: dict[str, Any], entry_row: dict[str, Any]) -> str:
    group = str(entry_row.get("candidate_group", "")).upper()
    if group in {"EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE"}:
        return group
    if truthy(candidate_row.get("both_eligible")):
        return "BOTH_ELIGIBLE"
    state = str(candidate_row.get("candidate_state", "")).upper()
    if state == "EMERGING":
        return "EMERGING_ONLY"
    if state == "CONFIRMED":
        return "CONFIRMED_ONLY"
    return "UNAVAILABLE"


def reward_risk_band(value: Any) -> str:
    ratio = decimal_value(value)
    if ratio is None:
        return "UNAVAILABLE"
    if ratio < Decimal("1.50"):
        return "BELOW_1_5"
    if ratio < Decimal("2.00"):
        return "1_5_TO_2"
    if ratio < Decimal("2.50"):
        return "2_TO_2_5"
    return "GTE_2_5"


def build_pilot_validation(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[tuple[str, Callable[[dict[str, Any]], bool], str, str]] = [
        ("A_BULLISH_RISK_READY_STRONG", lambda row: row["regime_state"] == "BULLISH" and row["score_mode"] == "FULL_SCORE" and row["setup_quality"] == "STRONG", "highest", "Bullish, risk-ready, strong setup"),
        ("B_BULLISH_NEAR_80", lambda row: row["regime_state"] == "BULLISH" and row["score_mode"] == "FULL_SCORE", "near80", "Bullish full-score row nearest raw 80"),
        ("C_BULLISH_BELOW_THRESHOLD", lambda row: row["regime_state"] == "BULLISH" and row["raw_strategy_score"] < Decimal("75"), "lowest", "Bullish row clearly below entry threshold"),
        ("D_NEUTRAL_RISK_READY", lambda row: row["regime_state"] == "NEUTRAL" and row["score_mode"] == "FULL_SCORE", "highest", "Neutral risk-ready opportunity"),
        ("E_BEARISH_EXCEPTIONAL_LONG", lambda row: row["regime_state"] == "BEARISH" and row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE", "highest", "Bearish exceptional-long review remains exceptional"),
        ("F_CONDITIONAL_PREVIEW", lambda row: row["score_mode"] == "PREVIEW_SCORE", "highest", "Conditional row remains preview-only"),
        ("G_STRONG_REWARD_RISK", lambda row: row["reward_risk_band"] == "GTE_2_5", "highest", "Reward:risk at or above 2.5R"),
        ("H_MINIMUM_REWARD_RISK", lambda row: row["reward_risk_band"] == "1_5_TO_2", "highest", "Reward:risk from 1.5R to below 2R"),
        ("I_STRONG_VOLUME", lambda row: row["rvol_points"] >= Decimal("13"), "highest", "Strong or exceptional upstream volume"),
        ("J_WEAKER_VOLUME_VALID", lambda row: row["score_mode"] == "FULL_SCORE" and row["rvol_points"] <= Decimal("10"), "highest", "Weaker volume with otherwise risk-ready structure"),
        ("K_STRONG_RELATIVE_STRENGTH", lambda row: row["relative_strength_points"] == Decimal("15"), "highest", "Strong upstream benchmark-relative strength"),
        ("L_BOTH_ELIGIBLE", lambda row: row["candidate_category"] == "BOTH_ELIGIBLE", "highest", "Candidate qualifies for both upstream categories"),
        ("M_EMERGING_ONLY_RISK_READY", lambda row: row["candidate_category"] == "EMERGING_ONLY" and row["score_mode"] == "FULL_SCORE", "highest", "Emerging-only risk-ready row"),
        ("N_MISSING_SECTOR_CATALYST", lambda row: row["sector_availability"] == "UNAVAILABLE" and row["catalyst_availability"] == "UNAVAILABLE", "highest", "Historical sector and catalyst evidence unavailable"),
    ]
    output = []
    for case_name, predicate, selection, expected in cases:
        matches = [row for row in rows if predicate(row)]
        if not matches:
            output.append(empty_pilot_row(case_name, expected))
            continue
        if selection == "near80":
            selected = min(matches, key=lambda row: (abs(row["raw_strategy_score"] - Decimal("80")), row["trading_date"], row["symbol"]))
        elif selection == "lowest":
            selected = min(matches, key=lambda row: (row["raw_strategy_score"], row["trading_date"], row["symbol"]))
        else:
            selected = max(matches, key=lambda row: (row["raw_strategy_score"], row["trading_date"], row["symbol"]))
        output.append(pilot_validation_row(case_name, selected, expected))
    passed = all(row["result"] == "PASS" for row in output)
    return output, {
        "passed": passed,
        "cases": {row["pilot_case"]: row["result"] for row in output},
        "symbols": sorted({row["symbol"] for row in output if row["symbol"]}),
        "dates": sorted({row["trading_date"] for row in output if row["trading_date"]}),
        "rows": len(output),
    }


def pilot_validation_row(case_name: str, row: dict[str, Any], expected: str) -> dict[str, Any]:
    points = {prefix: row[f"{prefix}_points"] for prefix in COMPONENT_PREFIXES}
    arithmetic_sum = sum(points.values(), Decimal("0"))
    available_sum = sum(
        row[f"{prefix}_max_points"]
        for prefix in COMPONENT_PREFIXES
        if row[f"{prefix}_availability"] == "AVAILABLE"
    )
    normalized = (
        row["raw_strategy_score"] / row["available_weight"] * Decimal("100")
        if row["available_weight"] > 0
        else None
    )
    valid = (
        arithmetic_sum == row["raw_strategy_score"]
        and available_sum == row["available_weight"]
        and row["score_coverage_pct"] == row["available_weight"]
        and normalized == row["normalized_available_score"]
        and row["normalized_score_usage"] == "DIAGNOSTIC_ONLY"
        and not (
            row["score_mode"] == "PREVIEW_SCORE"
            and row["scoring_disposition"] in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
        )
        and not (
            row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE"
            and row["scoring_disposition"] != "EXCEPTIONAL_REVIEW"
        )
    )
    return {
        "pilot_case": case_name,
        "symbol": row["symbol"],
        "trading_date": row["trading_date"],
        "score_mode": row["score_mode"],
        "component_points": ";".join(f"{key}={format(value, 'f')}" for key, value in points.items()),
        "raw_strategy_score": row["raw_strategy_score"],
        "arithmetic_sum": arithmetic_sum,
        "available_weight": row["available_weight"],
        "score_coverage_pct": row["score_coverage_pct"],
        "normalized_available_score": row["normalized_available_score"],
        "score_band": row["score_band"],
        "scoring_disposition": row["scoring_disposition"],
        "expected_semantics": expected,
        "result": "PASS" if valid else "FAIL",
    }


def empty_pilot_row(case_name: str, expected: str) -> dict[str, Any]:
    return {
        "pilot_case": case_name,
        "symbol": "",
        "trading_date": "",
        "score_mode": "",
        "component_points": "",
        "raw_strategy_score": "",
        "arithmetic_sum": "",
        "available_weight": "",
        "score_coverage_pct": "",
        "normalized_available_score": "",
        "score_band": "",
        "scoring_disposition": "",
        "expected_semantics": expected,
        "result": "FAIL",
    }


def score_funnel(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    modes = Counter(row["score_mode"] for row in rows)
    dispositions = Counter(row["scoring_disposition"] for row in rows)
    return {
        "total_rows": len(rows),
        "full_score": modes["FULL_SCORE"],
        "preview_score": modes["PREVIEW_SCORE"],
        "exceptional_review_score": modes["EXCEPTIONAL_REVIEW_SCORE"],
        "not_score_eligible": modes["NOT_SCORE_ELIGIBLE"],
        "risk_ready_rows": sum(row["risk_readiness"] == "READY_FOR_FINAL_SCORING" for row in rows),
        "raw_gte_80": sum(row["raw_strategy_score"] >= Decimal("80") for row in rows),
        "raw_gte_90": sum(row["raw_strategy_score"] >= Decimal("90") for row in rows),
        "entry_eligible": dispositions["ENTRY_ELIGIBLE"],
        "high_conviction": dispositions["HIGH_CONVICTION"],
        "exceptional_review": dispositions["EXCEPTIONAL_REVIEW"],
        "insufficient_coverage": dispositions["INSUFFICIENT_COVERAGE"],
    }


def score_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(row["raw_strategy_score"] for row in rows)
    if not values:
        return {name: None for name in ("min", "p10", "p25", "median", "mean", "p75", "p90", "p95", "max")}
    return {
        "min": values[0],
        "p10": percentile(values, Decimal("10")),
        "p25": percentile(values, Decimal("25")),
        "median": percentile(values, Decimal("50")),
        "mean": sum(values, Decimal("0")) / Decimal(len(values)),
        "p75": percentile(values, Decimal("75")),
        "p90": percentile(values, Decimal("90")),
        "p95": percentile(values, Decimal("95")),
        "max": values[-1],
    }


def daily_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["trading_date"]].append(row)
    output = []
    for trading_date, group in sorted(groups.items()):
        funnel = score_funnel(group)
        output.append(
            {
                "trading_date": trading_date,
                "total_rows": len(group),
                **{key: funnel[key] for key in DAILY_REPORT_FIELDS if key in funnel},
                "median_raw_score": score_distribution(group)["median"],
                "mean_raw_score": score_distribution(group)["mean"],
            }
        )
    return output


def component_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for prefix in COMPONENT_PREFIXES:
        values = [row[f"{prefix}_points"] for row in rows]
        maximum = rows[0][f"{prefix}_max_points"] if rows else Decimal("0")
        available = sum(row[f"{prefix}_availability"] == "AVAILABLE" for row in rows)
        output.append(
            {
                "component": prefix,
                "component_max_points": maximum,
                "available_count": available,
                "unavailable_count": len(rows) - available,
                "average_points": sum(values, Decimal("0")) / Decimal(len(values)) if values else None,
                "median_points": percentile(sorted(values), Decimal("50")) if values else None,
                "average_pct_of_max": (
                    sum(values, Decimal("0")) / Decimal(len(values)) / maximum * Decimal("100")
                    if values and maximum > 0
                    else Decimal("0")
                ),
                "zero_frequency": sum(value == 0 for value in values),
                "full_score_frequency": sum(value == maximum for value in values),
            }
        )
    return output


def regime_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for state in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE"):
        group = [row for row in rows if row["regime_state"] == state]
        distribution = score_distribution(group)
        output.append(
            {
                "regime_state": state,
                "rows": len(group),
                "median_raw_score": distribution["median"],
                "p90_raw_score": distribution["p90"],
                "raw_gte_80": sum(row["raw_strategy_score"] >= Decimal("80") for row in group),
                "raw_gte_90": sum(row["raw_strategy_score"] >= Decimal("90") for row in group),
                "entry_eligible": sum(row["scoring_disposition"] == "ENTRY_ELIGIBLE" for row in group),
                "high_conviction": sum(row["scoring_disposition"] == "HIGH_CONVICTION" for row in group),
                "exceptional_review": sum(row["scoring_disposition"] == "EXCEPTIONAL_REVIEW" for row in group),
            }
        )
    return output


def candidate_category_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for category in ("EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE", "UNAVAILABLE"):
        group = [row for row in rows if row["candidate_category"] == category]
        output.append(
            {
                "candidate_category": category,
                "rows": len(group),
                "median_raw_score": score_distribution(group)["median"],
                "raw_gte_80": sum(row["raw_strategy_score"] >= Decimal("80") for row in group),
                "entry_eligible": sum(row["scoring_disposition"] == "ENTRY_ELIGIBLE" for row in group),
            }
        )
    return output


def setup_quality_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for quality in ("STRONG", "VALID", "WATCH", "POOR", "UNAVAILABLE"):
        group = [row for row in rows if str(row["setup_quality"] or "UNAVAILABLE").upper() == quality]
        output.append(
            {
                "setup_quality": quality,
                "rows": len(group),
                "median_raw_score": score_distribution(group)["median"],
                "raw_gte_80": sum(row["raw_strategy_score"] >= Decimal("80") for row in group),
                "entry_eligible": sum(row["scoring_disposition"] == "ENTRY_ELIGIBLE" for row in group),
            }
        )
    return output


def grouped_score_summary(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    output = {}
    for value in sorted({str(row.get(field, "")) for row in rows}):
        group = [row for row in rows if str(row.get(field, "")) == value]
        output[value] = {
            "rows": len(group),
            "median_raw_score": score_distribution(group)["median"],
            "raw_gte_80": sum(row["raw_strategy_score"] >= Decimal("80") for row in group),
            "entry_eligible": sum(row["scoring_disposition"] == "ENTRY_ELIGIBLE" for row in group),
        }
    return output


def coverage_distribution(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["score_coverage_pct"] for row in rows)
    return [
        {
            "score_coverage_pct": coverage,
            "rows": count,
            "pct": pct(count, len(rows)),
        }
        for coverage, count in sorted(counts.items())
    ]


def coverage_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "at_85_pct": sum(row["score_coverage_pct"] == Decimal("85") for row in rows),
        "below_85_pct": sum(row["score_coverage_pct"] < Decimal("85") for row in rows),
        "above_85_pct": sum(row["score_coverage_pct"] > Decimal("85") for row in rows),
        "sector_available": sum(row["sector_availability"] == "AVAILABLE" for row in rows),
        "catalyst_available": sum(row["catalyst_availability"] == "AVAILABLE" for row in rows),
    }


def threshold_distribution(rows: Sequence[dict[str, Any]], config: StrategyScoreConfig) -> list[dict[str, Any]]:
    output = []
    for threshold in config.thresholds.diagnostic_thresholds:
        selected = [row for row in rows if row["raw_strategy_score"] >= threshold]
        output.append(
            {
                "raw_score_threshold": threshold,
                "rows": len(selected),
                "pct": pct(len(selected), len(rows)),
                "entry_eligible": sum(row["scoring_disposition"] == "ENTRY_ELIGIBLE" for row in selected),
                "high_conviction": sum(row["scoring_disposition"] == "HIGH_CONVICTION" for row in selected),
            }
        )
    return output


def redundancy_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    prefixes = ("setup", "momentum", "rvol", "relative_strength")
    output = []
    for index, first in enumerate(prefixes):
        for second in prefixes[index + 1 :]:
            pairs = [
                (row[f"{first}_points"], row[f"{second}_points"], row[f"{first}_max_points"], row[f"{second}_max_points"])
                for row in rows
                if row[f"{first}_availability"] == "AVAILABLE" and row[f"{second}_availability"] == "AVAILABLE"
            ]
            correlation = pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
            identical = sum(
                pair[0] / pair[2] == pair[1] / pair[3]
                for pair in pairs
                if pair[2] and pair[3]
            )
            identical_rate = Decimal(identical) / Decimal(len(pairs)) * Decimal("100") if pairs else Decimal("0")
            obvious = (
                correlation is not None
                and abs(correlation) >= Decimal("0.95")
            ) or identical_rate >= Decimal("90")
            output.append(
                {
                    "component_a": first,
                    "component_b": second,
                    "rows": len(pairs),
                    "pearson_correlation": correlation,
                    "identical_normalized_value_rate_pct": identical_rate,
                    "obvious_double_counting_risk": "YES" if obvious else "NO",
                }
            )
    return output


def pearson(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    left_mean = statistics.fmean(left_values)
    right_mean = statistics.fmean(right_values)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left_values, right_values, strict=True))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left_values)
        * sum((y - right_mean) ** 2 for y in right_values)
    )
    if denominator == 0:
        return None
    return Decimal(str(numerator / denominator)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def scoring_invariant_violations(rows: Sequence[dict[str, Any]], config: StrategyScoreConfig) -> dict[str, int]:
    return {
        "raw_score_out_of_bounds": sum(
            row["raw_strategy_score"] < 0 or row["raw_strategy_score"] > Decimal("100") for row in rows
        ),
        "component_cap_violations": sum(
            row[f"{prefix}_points"] < 0 or row[f"{prefix}_points"] > row[f"{prefix}_max_points"]
            for row in rows
            for prefix in COMPONENT_PREFIXES
        ),
        "arithmetic_violations": sum(
            row["raw_strategy_score"]
            != sum((row[f"{prefix}_points"] for prefix in COMPONENT_PREFIXES), Decimal("0"))
            for row in rows
        ),
        "coverage_violations": sum(
            row["score_coverage_pct"] != row["available_weight"] for row in rows
        ),
        "normalized_eligibility_violations": sum(
            row["raw_strategy_score"] < config.thresholds.entry_eligible
            and row["scoring_disposition"] in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
            for row in rows
        ),
        "preview_promotion_violations": sum(
            row["score_mode"] == "PREVIEW_SCORE"
            and row["scoring_disposition"] not in {"PREVIEW_ONLY"}
            for row in rows
        ),
        "exceptional_promotion_violations": sum(
            row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE"
            and row["scoring_disposition"] != "EXCEPTIONAL_REVIEW"
            for row in rows
        ),
        "failed_gate_promotion_violations": sum(
            row["score_mode"] == "NOT_SCORE_ELIGIBLE"
            and row["scoring_disposition"] != "NOT_ELIGIBLE"
            for row in rows
        ),
        "coverage_gate_violations": sum(
            row["score_mode"] == "FULL_SCORE"
            and row["score_coverage_pct"] < config.thresholds.minimum_score_coverage_pct
            and row["scoring_disposition"] != "INSUFFICIENT_COVERAGE"
            for row in rows
        ),
        "signal_status_violations": sum(row["trade_signal_status"] != "NOT_GENERATED" for row in rows),
        "execution_status_violations": sum(row["execution_status"] != "NOT_IMPLEMENTED" for row in rows),
        "sector_fabrication_violations": sum(
            row["sector_availability"] != "UNAVAILABLE" or row["sector_points"] != 0 for row in rows
        ),
        "catalyst_fabrication_violations": sum(
            row["catalyst_availability"] != "UNAVAILABLE" or row["catalyst_points"] != 0 for row in rows
        ),
    }


def input_hashes(config: StrategyScoreEngineConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
        "entry": file_sha256(config.entry_dataset_path),
        "risk_v1": file_sha256(config.risk_v1_dataset_path),
        "risk_v1_1": file_sha256(config.current_risk_dataset_path),
    }


def verify_frozen_hashes(hashes: dict[str, str]) -> None:
    expected = {
        **UPSTREAM_HASHES,
        "risk_v1": RISK_STRUCTURE_V1_DATASET_HASH,
        "risk_v1_1": RISK_STRUCTURE_V1_1_DATASET_HASH,
    }
    mismatches = {
        name: {"expected": expected_hash, "observed": hashes.get(name)}
        for name, expected_hash in expected.items()
        if hashes.get(name) != expected_hash
    }
    if mismatches:
        raise ValueError(f"Frozen input hash mismatch: {mismatches}")


def load_lookup(path: Path, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    output = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            key = (str(row.get("trading_date", "")), canonical_symbol(row.get("symbol", "")))
            if key in keys:
                output[key] = row
    return output


def read_gzip_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_score_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SCORE_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def prohibited_outcome_fields(fields: Iterable[str]) -> list[str]:
    return [
        field
        for field in fields
        if any(token in field.lower() for token in PROHIBITED_SCORE_FIELD_TOKENS)
    ]


def percentile(values: Sequence[Decimal], percentile_value: Decimal) -> Decimal:
    if not values:
        raise ValueError("Cannot calculate a percentile without values")
    if len(values) == 1:
        return values[0]
    position = percentile_value / Decimal("100") * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - Decimal(lower)
    return values[lower] + (values[upper] - values[lower]) * fraction


def pct(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) * Decimal("100") if denominator else Decimal("0")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def output_size(config: StrategyScoreEngineConfig) -> int:
    paths = (
        config.output_dataset_path,
        config.summary_path,
        config.daily_path,
        config.components_path,
        config.regimes_path,
        config.candidate_categories_path,
        config.setup_quality_path,
        config.coverage_path,
        config.thresholds_path,
        config.pilot_path,
        config.redundancy_path,
    )
    return sum(path.stat().st_size for path in paths if path.exists())


def write_strategy_score_markdown(report: dict[str, Any], path: Path) -> None:
    score = report["score"]
    funnel = report["funnel"]
    distribution = report["score_distribution"]
    coverage = report["coverage"]
    lines = [
        "# Strategy V1 Final Scoring",
        "",
        "Current phase: Step 02.10 / Command 01 - deterministic swing daily-EOD scoring foundation",
        "",
        "## Boundary",
        "",
        "- The score ranks available evidence; it is not a predicted probability, trade signal, or order instruction.",
        "- Mandatory candidate, setup, regime, entry, and risk gates run before score. A numerical score cannot rescue a failed gate.",
        "- No outcome labels, future data, backtest, profitability optimization, paper trade, broker action, migration, or Supabase write is used.",
        "",
        "## Version",
        "",
        f"- Score: {score['score_version']} / {score['score_config_hash']}",
        f"- Profile: {score['score_profile']}",
        f"- Active risk input: {report['risk_input']['current_risk_version']} / {report['risk_input']['current_risk_config_hash']}",
        "",
        "## Weights",
        "",
        "- Setup 20; multi-day momentum 20; relative volume 15; benchmark relative strength 15.",
        "- Market regime 10; sector 10; catalyst/news 5; reward:risk 5.",
        "- Sector and catalyst are unavailable historically and contribute zero points and zero available weight.",
        "",
        "## Component Mappings",
        "",
        "- Setup quality: STRONG 20, VALID 16, WATCH 8, POOR 0.",
        "- Multi-day momentum: candidate V1 5d, 10d, 20d, up-day-ratio-10, and up-day-ratio-20 thresholds contribute up to 4 points each; return_1d is excluded.",
        "- Relative volume: EXCEPTIONAL 15, STRONG 13, GOOD 10, NORMAL 6, WEAK 0.",
        "- Benchmark relative strength: STRONG 15, POSITIVE 11, NEUTRAL 6, WEAK 0.",
        "- Regime: BULLISH 10, NEUTRAL 5, BEARISH 0; UNAVAILABLE contributes zero and removes 10 points from available weight.",
        "- Sector: UNAVAILABLE / 0 because point-in-time stock-to-sector mapping does not exist.",
        "- Catalyst/news: UNAVAILABLE / 0 because no historical point-in-time catalyst layer exists.",
        "- Reward:risk: below 1.5R 0, 1.5R to below 2R 3, 2R to below 2.5R 4, at least 2.5R 5.",
        "",
        "## Score Semantics",
        "",
        "- Raw score is the unscaled sum on the locked 0-100 scale.",
        "- Available weight counts only AVAILABLE components; historical coverage is normally 85%.",
        "- Normalized available score is DIAGNOSTIC_ONLY and never controls bands or eligibility.",
        f"- Minimum coverage: {score['minimum_score_coverage_pct']}%; entry threshold: {score['entry_threshold']}; high-conviction threshold: {score['high_conviction_threshold']}.",
        "- Preview rows remain PREVIEW_ONLY. Bearish exceptional longs remain EXCEPTIONAL_REVIEW.",
        "- Penalties remain separate and retain their upstream severity and blocking status.",
        "",
        "## Current Reachability",
        "",
        "- Bullish theoretical maximum: 85; Neutral: 80; Bearish: 75.",
        "- HIGH_CONVICTION_NOT_REACHABLE_WITH_CURRENT_HISTORICAL_COMPONENT_COVERAGE.",
        "",
        "## Generation",
        "",
        f"- Full generation completed: {report['generation']['full_generation_completed']}",
        f"- Rows: {funnel['total_rows']}; full / preview / exceptional / not eligible: {funnel['full_score']} / {funnel['preview_score']} / {funnel['exceptional_review_score']} / {funnel['not_score_eligible']}",
        f"- Entry eligible: {funnel['entry_eligible']}; high conviction: {funnel['high_conviction']}; exceptional review: {funnel['exceptional_review']}",
        f"- Raw score min / median / mean / max: {distribution['min']} / {distribution['median']} / {distribution['mean']} / {distribution['max']}",
        f"- Coverage at 85% / below / above: {coverage['at_85_pct']} / {coverage['below_85_pct']} / {coverage['above_85_pct']}",
        "",
        "## Future Integration",
        "",
        "- Add sector points only after point-in-time stock-to-sector history exists.",
        "- Add catalyst points only through a separately approved point-in-time news research layer.",
        "- Intraday scoring remains a separate future INTRADAY_SCORE_V1 profile.",
        "",
        "## Audit And Status",
        "",
        "- STATUS: ACTIVE_FORWARD_BASELINE.",
        "- Step 02.10 - Strategy V1 Final Scoring Foundation: COMPLETE.",
        "- STRATEGY_SCORE_AUDIT_V1 concluded STABLE_WITH_REVIEW_NOTES and recommended freezing STRATEGY_SCORE_V1 unchanged.",
        "- Structural audit: docs/strategy-v1-final-scoring-audit.md.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(str(line) for line in lines), encoding="utf-8")

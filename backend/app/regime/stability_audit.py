from __future__ import annotations

import csv
import gzip
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Sequence

from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip
from app.strategy.setup_config import DailySetupEvaluationConfig

MARKET_REGIME_AUDIT_VERSION = "MARKET_REGIME_AUDIT_V1"

CLASSIFIED_STATES = ("BULLISH", "NEUTRAL", "BEARISH")
ALL_STATES = ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE")
DIRECT_FLIP_STATES = (("BULLISH", "BEARISH"), ("BEARISH", "BULLISH"))
SCORE_STATES = ("STRONGLY_BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "STRONGLY_BULLISH")
STATE_LEVEL = {
    "STRONGLY_BEARISH": -2,
    "BEARISH": -1,
    "RISK_OFF": -1,
    "STRONGLY_RISK_OFF": -2,
    "NEUTRAL": 0,
    "BULLISH": 1,
    "RISK_ON": 1,
    "STRONGLY_BULLISH": 2,
    "STRONGLY_RISK_ON": 2,
}
COMPONENTS = (
    ("NIFTY_TREND", "nifty_trend", Decimal("30")),
    ("NIFTY500_BREADTH", "breadth", Decimal("20")),
    ("SECTOR_PARTICIPATION", "sector", Decimal("15")),
    ("INDIA_VIX", "vix", Decimal("10")),
    ("GLOBAL_GIFT", "global_gift", Decimal("15")),
    ("INTRADAY_CONFIRMATION", "intraday", Decimal("10")),
)
AVAILABLE_COMPONENTS = ("NIFTY_TREND", "NIFTY500_BREADTH", "SECTOR_PARTICIPATION")
PROHIBITED_OUTCOME_FIELD_TOKENS = (
    "future_",
    "forward_",
    "mfe",
    "mae",
    "winner",
    "loser",
    "profit",
    "target_hit",
    "stop_hit",
    "backtest",
    "sharpe",
    "drawdown",
    "trade_outcome",
)

DIRECT_FLIP_FIELDS = [
    "flip_id",
    "date_t",
    "state_t",
    "normalized_score_t",
    "raw_score_t",
    "available_weight_t",
    "confidence_t",
    "confidence_score_t",
    "date_t1",
    "state_t1",
    "normalized_score_t1",
    "raw_score_t1",
    "available_weight_t1",
    "confidence_t1",
    "confidence_score_t1",
    "absolute_score_change",
    "signed_score_change",
    "nifty_trend_status_t",
    "nifty_trend_state_t",
    "nifty_trend_contribution_t",
    "nifty_trend_status_t1",
    "nifty_trend_state_t1",
    "nifty_trend_contribution_t1",
    "breadth_status_t",
    "breadth_state_t",
    "breadth_contribution_t",
    "breadth_status_t1",
    "breadth_state_t1",
    "breadth_contribution_t1",
    "sector_status_t",
    "sector_state_t",
    "sector_contribution_t",
    "sector_status_t1",
    "sector_state_t1",
    "sector_contribution_t1",
    "vix_status_t",
    "vix_state_t",
    "vix_contribution_t",
    "vix_status_t1",
    "vix_state_t1",
    "vix_contribution_t1",
    "global_gift_status_t",
    "global_gift_state_t",
    "global_gift_contribution_t",
    "global_gift_status_t1",
    "global_gift_state_t1",
    "global_gift_contribution_t1",
    "intraday_status_t",
    "intraday_state_t",
    "intraday_contribution_t",
    "intraday_status_t1",
    "intraday_state_t1",
    "intraday_contribution_t1",
]
FLIP_DRIVER_FIELDS = [
    "flip_id",
    "date_t",
    "date_t1",
    "transition",
    "trend_contribution_change",
    "breadth_contribution_change",
    "sector_contribution_change",
    "vix_status",
    "global_gift_status",
    "intraday_status",
    "raw_score_change",
    "normalized_score_change",
    "available_weight_change",
    "dominant_driver",
    "structural_classification",
    "classification_reason",
    "raw_equivalent_direct_flip",
    "normalization_material_boundary_crossing",
]
SCORE_CHANGE_FIELDS = [
    "date_t",
    "date_t1",
    "state_t",
    "state_t1",
    "normalized_score_t",
    "normalized_score_t1",
    "raw_score_t",
    "raw_score_t1",
    "available_weight_t",
    "available_weight_t1",
    "absolute_score_change",
    "signed_score_change",
    "change_band",
    "direct_bullish_bearish_flip",
    "sign_reversal_type",
    "trend_contribution_change",
    "breadth_contribution_change",
    "sector_contribution_change",
    "one_component_changed_discretely",
    "multiple_components_moved_coherently",
    "suspicious_jump",
]
COMPONENT_TRANSITION_FIELDS = [
    "section",
    "component_name",
    "from_state",
    "to_state",
    "count",
    "from_total",
    "pct",
    "daily_bucket_changes",
    "one_level_jumps",
    "two_level_jumps",
    "extreme_state_jumps",
    "median_abs_contribution_change",
    "p90_abs_contribution_change",
    "p95_abs_contribution_change",
    "max_abs_contribution_change",
    "threshold_boundaries",
    "contribution_step_sizes",
]
CONFIDENCE_AUDIT_FIELDS = [
    "section",
    "regime_state",
    "confidence_state",
    "score_magnitude_bucket",
    "agreement_class",
    "available_weight_bucket",
    "count",
    "pct",
    "median_confidence",
    "median_score_magnitude",
    "persistence_rate_next_session_pct",
]
SENSITIVITY_FIELDS = [
    "scenario",
    "scenario_type",
    "bullish_count",
    "neutral_count",
    "bearish_count",
    "unavailable_count",
    "direct_bullish_bearish_flips",
    "one_day_bullish_states",
    "one_day_bearish_states",
    "median_bullish_streak",
    "median_bearish_streak",
    "overall_state_agreement_pct",
    "regime_state_jaccard",
    "average_transition_delay",
    "delayed_transitions",
]
SCENARIO_STATE_FIELDS = ["scenario", "trading_date", "baseline_state", "scenario_state", "normalized_score", "available_weight_pct"]
BOUNDARY_ROW_FIELDS = ["band", "trading_date", "regime_state", "next_regime_state", "normalized_score", "next_score_change"]
COMPONENT_DAILY_CHANGE_FIELDS = [
    "component_name",
    "date_t",
    "date_t1",
    "state_t",
    "state_t1",
    "contribution_t",
    "contribution_t1",
    "absolute_contribution_change",
    "bucket_level_change",
]


@dataclass(frozen=True, slots=True)
class MarketRegimeStabilityAuditConfig:
    data_dir: Path
    regime_config: MarketRegimeConfig = MarketRegimeConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    audit_version: str = MARKET_REGIME_AUDIT_VERSION

    @property
    def regime_dataset_path(self) -> Path:
        return self.data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz"

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
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "market_regime" / "v1"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "market_regime_audit_summary.json"

    @property
    def direct_flips_path(self) -> Path:
        return self.reports_dir / "market_regime_direct_flips.csv"

    @property
    def flip_drivers_path(self) -> Path:
        return self.reports_dir / "market_regime_flip_drivers.csv"

    @property
    def score_changes_path(self) -> Path:
        return self.reports_dir / "market_regime_score_changes.csv"

    @property
    def component_transitions_path(self) -> Path:
        return self.reports_dir / "market_regime_component_transitions.csv"

    @property
    def confidence_audit_path(self) -> Path:
        return self.reports_dir / "market_regime_confidence_audit.csv"

    @property
    def sensitivity_path(self) -> Path:
        return self.reports_dir / "market_regime_sensitivity.csv"

    @property
    def direct_flips_bulk_path(self) -> Path:
        return self.audit_dir / "market_regime_direct_flips.csv.gz"

    @property
    def top_score_jumps_bulk_path(self) -> Path:
        return self.audit_dir / "market_regime_top_score_jumps.csv.gz"

    @property
    def scenario_state_series_path(self) -> Path:
        return self.audit_dir / "market_regime_scenario_state_series.csv.gz"

    @property
    def boundary_rows_path(self) -> Path:
        return self.audit_dir / "market_regime_boundary_rows.csv.gz"

    @property
    def component_daily_changes_path(self) -> Path:
        return self.audit_dir / "market_regime_component_daily_changes.csv.gz"


def build_market_regime_stability_audit(
    *,
    config: MarketRegimeStabilityAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = baseline_hashes(config)

    if progress:
        progress("Loading immutable MARKET_REGIME_V1 baseline rows")
    rows = load_regime_rows(config.regime_dataset_path)
    observed_regime_config_hash = observed_single_value(rows, "config_hash")

    if progress:
        progress("Extracting direct Bullish/Bearish flips and driver decomposition")
    direct_flips = direct_flip_rows(rows)
    flip_driver_rows, flip_driver_summary = flip_driver_analysis(direct_flips, config.regime_config)

    if progress:
        progress("Auditing score boundaries, score jumps, and component discretization")
    score_changes, score_change_summary = score_change_analysis(rows)
    boundary_summary, boundary_rows = boundary_zone_analysis(rows)
    borderline_summary = borderline_state_analysis(rows)
    component_transition_rows, component_summary, component_daily_changes = component_transition_analysis(rows, config.regime_config)

    if progress:
        progress("Auditing normalization, available weight, confidence, and agreement semantics")
    normalization = normalization_audit(rows, direct_flips, config.regime_config)
    available_weight = available_weight_analysis(rows, direct_flips)
    confidence_rows, confidence_summary = confidence_audit_rows(rows, config.regime_config)
    agreement = component_agreement_audit(rows)
    flip_paths = flip_path_analysis(rows)
    sign_reversals = sign_reversal_analysis(score_changes)
    streaks = streak_statistics(rows)
    one_day = one_day_state_summary(rows)

    if progress:
        progress("Running audit-only structural scenario simulations")
    scenario_rows, scenario_summary, scenario_state_rows = scenario_analysis(rows, config.regime_config)

    top_jumps = sorted(score_changes, key=lambda row: decimal_or_zero(row["absolute_score_change"]), reverse=True)[:50]
    stability_result = regime_stability_result(score_change_summary, flip_driver_summary, streaks)
    confidence_result_value = confidence_result(confidence_summary, config.regime_config)
    flip_quality = flip_quality_result(flip_driver_summary, score_change_summary)
    baseline_decision = baseline_decision_result(
        stability_result=stability_result,
        flip_quality=flip_quality,
        confidence_result_value=confidence_result_value,
    )

    write_csv(config.direct_flips_path, direct_flips, DIRECT_FLIP_FIELDS)
    write_csv(config.flip_drivers_path, flip_driver_rows, FLIP_DRIVER_FIELDS)
    write_csv(config.score_changes_path, score_changes, SCORE_CHANGE_FIELDS)
    write_csv(config.component_transitions_path, component_transition_rows, COMPONENT_TRANSITION_FIELDS)
    write_csv(config.confidence_audit_path, confidence_rows, CONFIDENCE_AUDIT_FIELDS)
    write_csv(config.sensitivity_path, scenario_rows, SENSITIVITY_FIELDS)
    write_gzip_csv(config.direct_flips_bulk_path, direct_flips, DIRECT_FLIP_FIELDS)
    write_gzip_csv(config.top_score_jumps_bulk_path, top_jumps, SCORE_CHANGE_FIELDS)
    write_gzip_csv(config.scenario_state_series_path, scenario_state_rows, SCENARIO_STATE_FIELDS)
    write_gzip_csv(config.boundary_rows_path, boundary_rows, BOUNDARY_ROW_FIELDS)
    write_gzip_csv(config.component_daily_changes_path, component_daily_changes, COMPONENT_DAILY_CHANGE_FIELDS)

    hashes_after = baseline_hashes(config)
    baseline_unchanged = {key: hashes_before[key] == hashes_after[key] for key in hashes_before}
    source_field_safety = prohibited_outcome_fields(load_header(config.regime_dataset_path))
    report = {
        "phase": "Step 02.7",
        "command": "Command 02",
        "generated_at": generated_at,
        "audit": {
            "audit_version": config.audit_version,
            "methodology": "Structural market-regime stability audit only; no future outcomes, profitability, candidate/setup outcomes, MFE, MAE, stops, targets, backtesting, entry scoring, trading execution, migrations, or Supabase writes.",
            "regime_version": MARKET_REGIME_VERSION,
            "regime_config_hash": config.regime_config.config_hash(),
            "observed_regime_config_hash": observed_regime_config_hash,
            "source_versions": {
                "benchmark": "BENCHMARK_CONTEXT_V1",
                "breadth": "DAILY_FEATURES_V1_PLUS_POINT_IN_TIME_MEMBERSHIP",
                "sector": "SECTOR_CONTEXT_V1_OFFICIAL_INDEX_HISTORY",
                "india_vix": "UNAVAILABLE_NOT_IMPUTED",
                "global_gift": "UNAVAILABLE_NOT_IMPUTED",
                "intraday": "UNAVAILABLE_FOR_DAILY_EOD_COMMAND",
            },
            "criteria": audit_criteria(config.regime_config),
        },
        "inputs": {
            "regime_dataset": str(config.regime_dataset_path),
            "feature_dataset": str(config.feature_dataset_path),
            "candidate_dataset": str(config.candidate_dataset_path),
            "setup_dataset": str(config.setup_dataset_path),
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
        },
        "baseline": {
            "row_count": len(rows),
            "date_start": rows[0]["trading_date"] if rows else "",
            "date_end": rows[-1]["trading_date"] if rows else "",
            "state_counts": state_counts(rows),
            "confidence_counts": state_counts(rows, field="confidence_state"),
            "regime_config_hash_matches": observed_regime_config_hash == config.regime_config.config_hash(),
        },
        "direct_flips": {
            "expected_count": 34,
            "observed_count": len(direct_flips),
            "matches_expected_count": len(direct_flips) == 34,
            "dominant_driver_distribution": flip_driver_summary["dominant_driver_distribution"],
            "structural_classification_distribution": flip_driver_summary["structural_classification_distribution"],
            "strongest_multi_component_reversals": flip_driver_summary["strongest_multi_component_reversals"],
            "borderline_threshold_flips": flip_driver_summary["borderline_threshold_flips"],
            "quality_result": flip_quality,
        },
        "boundary_analysis": {
            "threshold_bands": boundary_summary,
            "borderline_vs_core": borderline_summary,
        },
        "score_changes": {
            "distribution": score_change_summary["distribution"],
            "change_band_thresholds": score_change_summary["band_thresholds"],
            "change_band_distribution": score_change_summary["band_distribution"],
            "top_extreme_jumps": top_jumps[:10],
            "suspicious_jump_count": sum(1 for row in score_changes if truthy(row["suspicious_jump"])),
            "sign_reversals": sign_reversals,
        },
        "component_discretization": component_summary["discretization"],
        "component_transitions": component_summary["transitions"],
        "component_contribution_volatility": component_summary["contribution_volatility"],
        "normalization": normalization,
        "available_weight": available_weight,
        "missing_components": {
            "permanently_unavailable": ["INDIA_VIX", "GLOBAL_GIFT", "INTRADAY_CONFIRMATION"],
            "missing_target_weight": "35",
            "directional_certainty_unavailable_pct": "35",
            "policy": "Missing components are unavailable evidence, not neutral evidence; no synthetic VIX, Global/GIFT, or intraday values are introduced.",
        },
        "confidence": confidence_summary | {"result": confidence_result_value},
        "component_agreement": agreement,
        "flip_paths": flip_paths,
        "streaks": streaks,
        "one_day_states": one_day,
        "sensitivity": {
            "scenarios": scenario_summary,
            "stability_result": stability_result,
            "baseline_retention_note": "Scenario changes are structural diagnostics only; no scenario is preferred solely because it reduces flips.",
        },
        "regression": {
            "market_regime_dataset_unchanged": baseline_unchanged["regime"],
            "market_regime_config_hash_unchanged": observed_regime_config_hash == config.regime_config.config_hash(),
            "daily_features_v1_unchanged": baseline_unchanged["feature"],
            "momentum_candidates_v1_unchanged": baseline_unchanged["candidate"],
            "daily_setup_evaluation_v1_unchanged": baseline_unchanged["setup"],
            "candidate_config_hash_unchanged": config.candidate_config.config_hash() == "d111957c7a24da96",
            "setup_config_hash_unchanged": config.setup_config.config_hash() == "1dcc8d7790116e56",
        },
        "safety": {
            "future_outcome_fields_used": 0,
            "future_return_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "profitability_optimization_used": 0,
            "entry_scores_generated": 0,
            "risk_reward_calculated": 0,
            "stops_generated": 0,
            "targets_generated": 0,
            "position_sizes_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "baseline_thresholds_changed": False,
            "baseline_weights_changed": False,
            "prohibited_outcome_fields_in_regime_input": source_field_safety,
        },
        "decision": {
            "flip_quality_result": flip_quality,
            "confidence_result": confidence_result_value,
            "regime_stability_result": stability_result,
            "baseline_decision": baseline_decision,
        },
        "outputs": {
            "summary_json": str(config.summary_path),
            "direct_flips_csv": str(config.direct_flips_path),
            "flip_drivers_csv": str(config.flip_drivers_path),
            "score_changes_csv": str(config.score_changes_path),
            "component_transitions_csv": str(config.component_transitions_path),
            "confidence_audit_csv": str(config.confidence_audit_path),
            "sensitivity_csv": str(config.sensitivity_path),
            "bulk_audit_dir": str(config.audit_dir),
            "direct_flips_bulk": str(config.direct_flips_bulk_path),
            "top_score_jumps_bulk": str(config.top_score_jumps_bulk_path),
            "scenario_state_series_bulk": str(config.scenario_state_series_path),
            "boundary_rows_bulk": str(config.boundary_rows_path),
            "component_daily_changes_bulk": str(config.component_daily_changes_path),
            "markdown": "docs/market-regime-stability-audit.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        report["baseline"]["regime_config_hash_matches"]
        and all(baseline_unchanged.values())
        and not source_field_safety
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def direct_flip_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(rows, rows[1:]), start=1):
        if (state(left), state(right)) not in DIRECT_FLIP_STATES:
            continue
        left_score = parse_decimal(left.get("regime_score_normalized"))
        right_score = parse_decimal(right.get("regime_score_normalized"))
        flip = {
            "flip_id": f"FLIP_{len(output) + 1:04d}",
            "date_t": left["trading_date"],
            "state_t": state(left),
            "normalized_score_t": round_decimal(left_score),
            "raw_score_t": round_decimal(parse_decimal(left.get("regime_score_raw"))),
            "available_weight_t": round_decimal(parse_decimal(left.get("available_weight_pct"))),
            "confidence_t": left.get("confidence_state", ""),
            "confidence_score_t": round_decimal(parse_decimal(left.get("confidence_score"))),
            "date_t1": right["trading_date"],
            "state_t1": state(right),
            "normalized_score_t1": round_decimal(right_score),
            "raw_score_t1": round_decimal(parse_decimal(right.get("regime_score_raw"))),
            "available_weight_t1": round_decimal(parse_decimal(right.get("available_weight_pct"))),
            "confidence_t1": right.get("confidence_state", ""),
            "confidence_score_t1": round_decimal(parse_decimal(right.get("confidence_score"))),
            "absolute_score_change": round_decimal(abs(right_score - left_score) if left_score is not None and right_score is not None else None),
            "signed_score_change": round_decimal(right_score - left_score if left_score is not None and right_score is not None else None),
        }
        flip.update(component_pair_fields(left, right))
        output.append(flip)
    return output


def flip_driver_analysis(
    direct_flips: Sequence[dict[str, Any]],
    config: MarketRegimeConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for flip in direct_flips:
        driver = dominant_flip_driver(flip, config)
        rows.append(driver)
    dominant_distribution = distribution_dict(Counter(row["dominant_driver"] for row in rows), len(rows))
    structural_distribution = distribution_dict(Counter(row["structural_classification"] for row in rows), len(rows))
    strongest = [
        row
        for row in sorted(rows, key=lambda item: decimal_or_zero(item["normalized_score_change"]).copy_abs(), reverse=True)
        if row["structural_classification"] in {"STRONG_MULTI_COMPONENT_REVERSAL", "MODERATE_MULTI_COMPONENT_REVERSAL"}
    ][:5]
    borderline = [
        row
        for row in sorted(rows, key=lambda item: decimal_or_zero(item["normalized_score_change"]).copy_abs())
        if row["structural_classification"] == "BORDERLINE_THRESHOLD_FLIP"
    ][:5]
    return rows, {
        "dominant_driver_distribution": dominant_distribution,
        "structural_classification_distribution": structural_distribution,
        "strongest_multi_component_reversals": strongest,
        "borderline_threshold_flips": borderline,
    }


def dominant_flip_driver(flip: dict[str, Any], config: MarketRegimeConfig) -> dict[str, Any]:
    deltas = {
        "NIFTY_TREND": contribution_delta(flip, "nifty_trend"),
        "NIFTY500_BREADTH": contribution_delta(flip, "breadth"),
        "SECTOR_PARTICIPATION": contribution_delta(flip, "sector"),
    }
    abs_deltas = {key: abs(value) for key, value in deltas.items() if value is not None}
    total_abs = sum(abs_deltas.values(), Decimal("0"))
    available_weight_change = decimal_or_zero(flip["available_weight_t1"]) - decimal_or_zero(flip["available_weight_t"])
    raw_direct = raw_equivalent_direct_flip(flip, config)
    normalization_material = not raw_direct
    coverage_change = available_weight_change.copy_abs() > Decimal("0.0001")
    if coverage_change:
        dominant = "COVERAGE_CHANGE"
    elif normalization_material:
        dominant = "NORMALIZATION_EFFECT"
    elif not abs_deltas:
        dominant = "OTHER"
    else:
        top_component, top_abs = max(abs_deltas.items(), key=lambda item: item[1])
        significant_components = [name for name, value in abs_deltas.items() if value >= Decimal("9")]
        if top_abs >= total_abs * Decimal("0.65") and top_abs >= Decimal("12"):
            dominant = {
                "NIFTY_TREND": "TREND_DOMINANT",
                "NIFTY500_BREADTH": "BREADTH_DOMINANT",
                "SECTOR_PARTICIPATION": "SECTOR_DOMINANT",
            }[top_component]
        elif len(significant_components) >= 2:
            dominant = "MULTI_COMPONENT"
        else:
            dominant = "OTHER"
    structural_classification, reason = structural_flip_classification(
        flip=flip,
        deltas=deltas,
        dominant_driver=dominant,
        coverage_change=coverage_change,
        normalization_material=normalization_material,
    )
    return {
        "flip_id": flip["flip_id"],
        "date_t": flip["date_t"],
        "date_t1": flip["date_t1"],
        "transition": f"{flip['state_t']}->{flip['state_t1']}",
        "trend_contribution_change": round_decimal(deltas["NIFTY_TREND"]),
        "breadth_contribution_change": round_decimal(deltas["NIFTY500_BREADTH"]),
        "sector_contribution_change": round_decimal(deltas["SECTOR_PARTICIPATION"]),
        "vix_status": f"{flip['vix_status_t']}->{flip['vix_status_t1']}",
        "global_gift_status": f"{flip['global_gift_status_t']}->{flip['global_gift_status_t1']}",
        "intraday_status": f"{flip['intraday_status_t']}->{flip['intraday_status_t1']}",
        "raw_score_change": round_decimal(decimal_or_zero(flip["raw_score_t1"]) - decimal_or_zero(flip["raw_score_t"])),
        "normalized_score_change": round_decimal(decimal_or_zero(flip["normalized_score_t1"]) - decimal_or_zero(flip["normalized_score_t"])),
        "available_weight_change": round_decimal(available_weight_change),
        "dominant_driver": dominant,
        "structural_classification": structural_classification,
        "classification_reason": reason,
        "raw_equivalent_direct_flip": raw_direct,
        "normalization_material_boundary_crossing": normalization_material,
    }


def structural_flip_classification(
    *,
    flip: dict[str, Any],
    deltas: dict[str, Decimal | None],
    dominant_driver: str,
    coverage_change: bool,
    normalization_material: bool,
) -> tuple[str, str]:
    if coverage_change or normalization_material:
        return "COVERAGE/NORMALIZATION_ARTIFACT", "Available weight or raw/normalized equivalence changed across the flip."
    reversed_components = []
    changed_components = []
    for _component_name, prefix, _weight in COMPONENTS[:3]:
        left_direction = component_direction(flip.get(f"{prefix}_contribution_t"))
        right_direction = component_direction(flip.get(f"{prefix}_contribution_t1"))
        left_level = STATE_LEVEL.get(str(flip.get(f"{prefix}_state_t", "")))
        right_level = STATE_LEVEL.get(str(flip.get(f"{prefix}_state_t1", "")))
        if left_level is not None and right_level is not None and left_level != right_level:
            changed_components.append(prefix)
        if left_direction and right_direction and left_direction != right_direction:
            reversed_components.append(prefix)
    score_t = decimal_or_zero(flip["normalized_score_t"])
    score_t1 = decimal_or_zero(flip["normalized_score_t1"])
    absolute_change = decimal_or_zero(flip["absolute_score_change"])
    if len(reversed_components) >= 2 and min(abs(score_t), abs(score_t1)) >= Decimal("50") and absolute_change >= Decimal("80"):
        return "STRONG_MULTI_COMPONENT_REVERSAL", "At least two available components reversed direction with large absolute regime scores."
    if len(reversed_components) >= 2:
        return "MODERATE_MULTI_COMPONENT_REVERSAL", "At least two available components reversed direction, but one side was less extreme."
    if near_boundary(score_t) or near_boundary(score_t1):
        return "BORDERLINE_THRESHOLD_FLIP", "At least one side of the flip was within 10 normalized points of a classification boundary."
    if len(changed_components) == 1 or dominant_driver in {"TREND_DOMINANT", "BREADTH_DOMINANT", "SECTOR_DOMINANT"}:
        return "SINGLE_COMPONENT_BUCKET_JUMP", "One component bucket/contribution change dominated the regime reversal."
    return "INCONCLUSIVE", "Same-day component evidence did not cleanly identify one structural cause."


def boundary_zone_analysis(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bands = [
        ("PLUS_25_TO_35", Decimal("25"), Decimal("35")),
        ("PLUS_20_TO_40", Decimal("20"), Decimal("40")),
        ("MINUS_35_TO_25", Decimal("-35"), Decimal("-25")),
        ("MINUS_40_TO_20", Decimal("-40"), Decimal("-20")),
    ]
    summaries = []
    details = []
    for band_name, lower, upper in bands:
        selected = []
        next_transitions: Counter[str] = Counter()
        changes = []
        direct_flips = 0
        for left, right in with_next(rows):
            score_value = parse_decimal(left.get("regime_score_normalized"))
            if score_value is None or score_value < lower or score_value > upper:
                continue
            selected.append(left)
            transition = f"{state(left)}->{state(right)}"
            next_transitions[transition] += 1
            if (state(left), state(right)) in DIRECT_FLIP_STATES:
                direct_flips += 1
            right_score = parse_decimal(right.get("regime_score_normalized"))
            if right_score is not None:
                changes.append(abs(right_score - score_value))
            details.append(
                {
                    "band": band_name,
                    "trading_date": left["trading_date"],
                    "regime_state": state(left),
                    "next_regime_state": state(right),
                    "normalized_score": round_decimal(score_value),
                    "next_score_change": round_decimal(abs(right_score - score_value) if right_score is not None else None),
                }
            )
        summaries.append(
            {
                "band": band_name,
                "range": f"{round_decimal(lower)} to {round_decimal(upper)}",
                "row_count": len(selected),
                "state_distribution": distribution_dict(Counter(state(row) for row in selected), len(selected)),
                "next_transition_distribution": distribution_dict(next_transitions, sum(next_transitions.values())),
                "median_abs_next_score_change": round_decimal(median_decimal(changes)),
                "direct_flip_count": direct_flips,
                "direct_flip_frequency_pct": pct(direct_flips, len(selected)),
            }
        )
    return summaries, details


def borderline_state_analysis(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[tuple[dict[str, Any], dict[str, Any] | None]]] = defaultdict(list)
    for index, row in enumerate(rows):
        bucket = score_bucket_for_borderline(row)
        if bucket:
            buckets[bucket].append((row, rows[index + 1] if index + 1 < len(rows) else None))
    summary = {}
    for bucket in ("BORDERLINE_BULLISH", "BORDERLINE_BEARISH", "CORE_BULLISH", "CORE_BEARISH"):
        pairs = buckets.get(bucket, [])
        next_pairs = [(left, right) for left, right in pairs if right is not None]
        persistent = sum(1 for left, right in next_pairs if state(left) == state(right))
        neutral = sum(1 for _left, right in next_pairs if right is not None and state(right) == "NEUTRAL")
        opposite = sum(1 for left, right in next_pairs if right is not None and (state(left), state(right)) in DIRECT_FLIP_STATES)
        summary[bucket] = {
            "row_count": len(pairs),
            "persistence_rate_next_session_pct": pct(persistent, len(next_pairs)),
            "transition_to_neutral_count": neutral,
            "transition_to_neutral_pct": pct(neutral, len(next_pairs)),
            "direct_opposite_transition_count": opposite,
            "direct_opposite_transition_pct": pct(opposite, len(next_pairs)),
            "median_confidence": round_decimal(median_decimal([parse_decimal(left.get("confidence_score")) for left, _right in pairs])),
        }
    return summary


def score_change_analysis(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_changes: list[Decimal] = []
    pairs = []
    for left, right in with_next(rows):
        left_score = parse_decimal(left.get("regime_score_normalized"))
        right_score = parse_decimal(right.get("regime_score_normalized"))
        if left_score is None or right_score is None:
            continue
        abs_change = abs(right_score - left_score)
        raw_changes.append(abs_change)
        pairs.append((left, right, abs_change, right_score - left_score))
    thresholds = change_band_thresholds(raw_changes)
    output = []
    for left, right, abs_change, signed_change in pairs:
        component_changes = {
            "trend": contribution_delta_from_rows(left, right, "nifty_trend"),
            "breadth": contribution_delta_from_rows(left, right, "breadth"),
            "sector": contribution_delta_from_rows(left, right, "sector"),
        }
        one_component = exactly_one_component_changed_discretely(left, right)
        coherent = multiple_components_moved_coherently(left, right)
        direct_flip = (state(left), state(right)) in DIRECT_FLIP_STATES
        suspicious = direct_flip and (one_component or near_boundary(parse_decimal(left.get("regime_score_normalized"))) or near_boundary(parse_decimal(right.get("regime_score_normalized"))))
        output.append(
            {
                "date_t": left["trading_date"],
                "date_t1": right["trading_date"],
                "state_t": state(left),
                "state_t1": state(right),
                "normalized_score_t": round_decimal(parse_decimal(left.get("regime_score_normalized"))),
                "normalized_score_t1": round_decimal(parse_decimal(right.get("regime_score_normalized"))),
                "raw_score_t": round_decimal(parse_decimal(left.get("regime_score_raw"))),
                "raw_score_t1": round_decimal(parse_decimal(right.get("regime_score_raw"))),
                "available_weight_t": round_decimal(parse_decimal(left.get("available_weight_pct"))),
                "available_weight_t1": round_decimal(parse_decimal(right.get("available_weight_pct"))),
                "absolute_score_change": round_decimal(abs_change),
                "signed_score_change": round_decimal(signed_change),
                "change_band": change_band(abs_change, thresholds),
                "direct_bullish_bearish_flip": direct_flip,
                "sign_reversal_type": sign_reversal_type(left, right),
                "trend_contribution_change": round_decimal(component_changes["trend"]),
                "breadth_contribution_change": round_decimal(component_changes["breadth"]),
                "sector_contribution_change": round_decimal(component_changes["sector"]),
                "one_component_changed_discretely": one_component,
                "multiple_components_moved_coherently": coherent,
                "suspicious_jump": suspicious,
            }
        )
    return output, {
        "distribution": decimal_distribution(raw_changes),
        "band_thresholds": {key: round_decimal(value) for key, value in thresholds.items()},
        "band_distribution": distribution_dict(Counter(row["change_band"] for row in output), len(output)),
        "direct_flip_count": sum(1 for row in output if truthy(row["direct_bullish_bearish_flip"])),
    }


def component_transition_analysis(
    rows: Sequence[dict[str, Any]],
    config: MarketRegimeConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    output = []
    daily_changes = []
    discretization = {}
    transition_summary = {}
    volatility = {}
    for component_name, prefix, target_weight in COMPONENTS[:3]:
        transitions: Counter[tuple[str, str]] = Counter()
        from_counts: Counter[str] = Counter()
        level_jumps = Counter()
        contribution_changes: list[Decimal] = []
        for left, right in with_next(rows):
            left_state = str(left.get(f"{prefix}_state", "") or "UNAVAILABLE")
            right_state = str(right.get(f"{prefix}_state", "") or "UNAVAILABLE")
            transitions[(left_state, right_state)] += 1
            from_counts[left_state] += 1
            level_delta = bucket_level_delta(left_state, right_state)
            if level_delta > 0 and left_state != "UNAVAILABLE" and right_state != "UNAVAILABLE":
                level_jumps["daily_bucket_changes"] += 1
                if level_delta == 1:
                    level_jumps["one_level_jumps"] += 1
                elif level_delta == 2:
                    level_jumps["two_level_jumps"] += 1
                elif level_delta >= 3:
                    level_jumps["extreme_state_jumps"] += 1
            contribution_delta_value = contribution_delta_from_rows(left, right, prefix)
            if contribution_delta_value is not None:
                abs_delta = abs(contribution_delta_value)
                contribution_changes.append(abs_delta)
                daily_changes.append(
                    {
                        "component_name": component_name,
                        "date_t": left["trading_date"],
                        "date_t1": right["trading_date"],
                        "state_t": left_state,
                        "state_t1": right_state,
                        "contribution_t": round_decimal(parse_decimal(left.get(f"{prefix}_contribution"))),
                        "contribution_t1": round_decimal(parse_decimal(right.get(f"{prefix}_contribution"))),
                        "absolute_contribution_change": round_decimal(abs_delta),
                        "bucket_level_change": level_delta,
                    }
                )
        thresholds = component_threshold_description(component_name, config)
        steps = contribution_step_sizes(target_weight)
        transition_rows = []
        for from_state in sorted(from_counts):
            for to_state in sorted({right for left, right in transitions if left == from_state}):
                count = transitions[(from_state, to_state)]
                row = {
                    "section": "TRANSITION_MATRIX",
                    "component_name": component_name,
                    "from_state": from_state,
                    "to_state": to_state,
                    "count": count,
                    "from_total": from_counts[from_state],
                    "pct": pct(count, from_counts[from_state]),
                    "daily_bucket_changes": level_jumps["daily_bucket_changes"],
                    "one_level_jumps": level_jumps["one_level_jumps"],
                    "two_level_jumps": level_jumps["two_level_jumps"],
                    "extreme_state_jumps": level_jumps["extreme_state_jumps"],
                    "median_abs_contribution_change": round_decimal(median_decimal(contribution_changes)),
                    "p90_abs_contribution_change": round_decimal(decimal_quantile(contribution_changes, Decimal("0.90"))),
                    "p95_abs_contribution_change": round_decimal(decimal_quantile(contribution_changes, Decimal("0.95"))),
                    "max_abs_contribution_change": round_decimal(max(contribution_changes) if contribution_changes else None),
                    "threshold_boundaries": thresholds,
                    "contribution_step_sizes": steps,
                }
                output.append(row)
                transition_rows.append(row)
        discretization[component_name] = {
            "threshold_boundaries": thresholds,
            "contribution_step_sizes": steps,
            "daily_bucket_changes": level_jumps["daily_bucket_changes"],
            "one_level_jumps": level_jumps["one_level_jumps"],
            "two_level_jumps": level_jumps["two_level_jumps"],
            "extreme_state_jumps": level_jumps["extreme_state_jumps"],
            "small_metric_change_can_cross_bucket": True,
        }
        transition_summary[component_name] = {
            "top_transitions": sorted(
                (
                    {
                        "from_state": row["from_state"],
                        "to_state": row["to_state"],
                        "count": row["count"],
                        "pct": row["pct"],
                    }
                    for row in transition_rows
                ),
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:10]
        }
        volatility[component_name] = decimal_distribution(contribution_changes)
    volatility["rank_most_jumpy"] = [
        item[0]
        for item in sorted(
            ((name, decimal_or_zero(stats.get("p95")), decimal_or_zero(stats.get("max"))) for name, stats in volatility.items() if isinstance(stats, dict)),
            key=lambda item: (item[1], item[2]),
            reverse=True,
        )
    ]
    return output, {"discretization": discretization, "transitions": transition_summary, "contribution_volatility": volatility}, daily_changes


def normalization_audit(
    rows: Sequence[dict[str, Any]],
    direct_flips: Sequence[dict[str, Any]],
    config: MarketRegimeConfig,
) -> dict[str, Any]:
    multipliers = []
    mismatch_rows = []
    for row in rows:
        available_weight = parse_decimal(row.get("available_weight_pct"))
        if available_weight is not None and available_weight > 0:
            multipliers.append(Decimal("100") / available_weight)
        normalized_state = state(row)
        raw_state = classify_raw_equivalent_row(row, config)
        if normalized_state != raw_state:
            mismatch_rows.append({"trading_date": row["trading_date"], "normalized_state": normalized_state, "raw_equivalent_state": raw_state})
    direct_flip_rows_with_equivalence = []
    material_count = 0
    for flip in direct_flips:
        raw_direct = raw_equivalent_direct_flip(flip, config)
        if not raw_direct:
            material_count += 1
        direct_flip_rows_with_equivalence.append(
            {
                "flip_id": flip["flip_id"],
                "date_t": flip["date_t"],
                "date_t1": flip["date_t1"],
                "raw_score_transition": f"{flip['raw_score_t']}->{flip['raw_score_t1']}",
                "normalized_score_transition": f"{flip['normalized_score_t']}->{flip['normalized_score_t1']}",
                "raw_equivalent_direct_flip": raw_direct,
                "normalization_material_boundary_crossing": not raw_direct,
            }
        )
    return {
        "formula": "normalized_score = raw_available_score / available_weight_pct * 100",
        "multiplier_distribution": decimal_distribution(multipliers),
        "typical_65pct_multiplier": round_decimal(Decimal("100") / Decimal("65")),
        "raw_vs_normalized_mismatch_count": len(mismatch_rows),
        "raw_vs_normalized_mismatches": mismatch_rows[:20],
        "normalization_material_direct_flip_count": material_count,
        "classification_artifact_result": "NO_CLASSIFICATION_ARTIFACTS" if not mismatch_rows and not material_count else "POSSIBLE_CLASSIFICATION_ARTIFACTS",
        "direct_flip_raw_equivalence": direct_flip_rows_with_equivalence,
        "interpretation": "Raw proportional boundaries are mathematically equivalent to normalized boundaries; normalization magnifies presentation but does not add classification changes when implemented consistently.",
    }


def available_weight_analysis(rows: Sequence[dict[str, Any]], direct_flips: Sequence[dict[str, Any]]) -> dict[str, Any]:
    weights = [parse_decimal(row.get("available_weight_pct")) for row in rows]
    weights = [value for value in weights if value is not None]
    bucket_counts = Counter(weight_bucket(value) for value in weights)
    non_65_dates = [
        {"trading_date": row["trading_date"], "available_weight_pct": round_decimal(parse_decimal(row.get("available_weight_pct")))}
        for row in rows
        if parse_decimal(row.get("available_weight_pct")) != Decimal("65")
    ]
    flip_weight_changes = [
        flip
        for flip in direct_flips
        if decimal_or_zero(flip["available_weight_t"]) != decimal_or_zero(flip["available_weight_t1"])
    ]
    return {
        "distribution": decimal_distribution(weights),
        "bucket_counts": distribution_dict(bucket_counts, len(weights)),
        "dates_where_available_weight_differs_from_65": non_65_dates[:50],
        "dates_where_available_weight_differs_from_65_count": len(non_65_dates),
        "direct_flips_with_available_weight_change": len(flip_weight_changes),
        "direct_flips_cluster_around_coverage_changes": len(flip_weight_changes) > 0,
    }


def confidence_audit_rows(
    rows: Sequence[dict[str, Any]],
    config: MarketRegimeConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    confidence_scores = [parse_decimal(row.get("confidence_score")) for row in rows]
    confidence_scores = [value for value in confidence_scores if value is not None]
    confidence_counts = Counter(str(row.get("confidence_state", "")) for row in rows)
    cross_tab: Counter[tuple[str, str]] = Counter((state(row), str(row.get("confidence_state", ""))) for row in rows)
    total = len(rows)
    for (regime_state, confidence_state), count in sorted(cross_tab.items()):
        group = [row for row in rows if state(row) == regime_state and str(row.get("confidence_state", "")) == confidence_state]
        output.append(confidence_output_row("REGIME_VS_CONFIDENCE", group, regime_state, confidence_state, "", "", total))
    score_bucket_rows = defaultdict(list)
    for row in rows:
        score_bucket_rows[score_magnitude_bucket(row)].append(row)
    for bucket, group in sorted(score_bucket_rows.items()):
        output.append(confidence_output_row("SCORE_MAGNITUDE_BUCKET", group, "", "", bucket, "", total))
    agreement_rows = defaultdict(list)
    for row in rows:
        agreement_rows[agreement_class_for_row(row)].append(row)
    for agreement_class, group in sorted(agreement_rows.items()):
        output.append(confidence_output_row("AGREEMENT_CLASS", group, "", "", "", agreement_class, total))
    available_weight_rows = defaultdict(list)
    for row in rows:
        available_weight_rows[weight_bucket(parse_decimal(row.get("available_weight_pct")) or Decimal("0"))].append(row)
    for bucket, group in sorted(available_weight_rows.items()):
        output.append(
            confidence_output_row(
                "AVAILABLE_WEIGHT_BUCKET",
                group,
                "",
                "",
                "",
                "",
                total,
                available_weight_bucket=bucket,
            )
        )
    theoretical = theoretical_confidence_ceiling(rows, config)
    return output, {
        "formula": {
            "text": "confidence_score = available_weight_pct*0.45 + component_agreement_pct*0.30 + weighted_component_coverage_pct*0.25 - partial_membership_penalty; capped to 0..100.",
            "availability_weight": round_decimal(config.confidence.availability_weight),
            "agreement_weight": round_decimal(config.confidence.agreement_weight),
            "coverage_weight": round_decimal(config.confidence.coverage_weight),
            "partial_membership_penalty": round_decimal(config.confidence.partial_membership_penalty),
            "medium_threshold": round_decimal(config.confidence.medium_threshold),
            "high_threshold": round_decimal(config.confidence.high_threshold),
        },
        "theoretical_ceiling": theoretical,
        "observed_distribution": decimal_distribution(confidence_scores),
        "confidence_state_distribution": distribution_dict(confidence_counts, total),
        "regime_vs_confidence": {
            f"{regime_state}/{confidence_state}": {"count": count, "pct": pct(count, total)}
            for (regime_state, confidence_state), count in sorted(cross_tab.items())
        },
        "high_confidence_absence_reason": high_confidence_absence_reason(theoretical, confidence_counts, config),
        "direction_and_confidence_are_separate": True,
    }


def confidence_output_row(
    section: str,
    rows: Sequence[dict[str, Any]],
    regime_state: str,
    confidence_state: str,
    score_bucket: str,
    agreement_class: str,
    total: int,
    *,
    available_weight_bucket: str = "",
) -> dict[str, Any]:
    return {
        "section": section,
        "regime_state": regime_state,
        "confidence_state": confidence_state,
        "score_magnitude_bucket": score_bucket,
        "agreement_class": agreement_class,
        "available_weight_bucket": available_weight_bucket,
        "count": len(rows),
        "pct": pct(len(rows), total),
        "median_confidence": round_decimal(median_decimal([parse_decimal(row.get("confidence_score")) for row in rows])),
        "median_score_magnitude": round_decimal(median_decimal([abs(parse_decimal(row.get("regime_score_normalized")) or Decimal("0")) for row in rows])),
        "persistence_rate_next_session_pct": "",
    }


def component_agreement_audit(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    agreement_classes = Counter()
    direct_flip_prior_current = Counter()
    by_state_confidence: Counter[tuple[str, str, str]] = Counter()
    persistence_counts: Counter[str] = Counter()
    persistence_totals: Counter[str] = Counter()
    for index, row in enumerate(rows):
        agreement_class = agreement_class_for_row(row)
        agreement_classes[agreement_class] += 1
        by_state_confidence[(agreement_class, state(row), str(row.get("confidence_state", "")))] += 1
        if index + 1 < len(rows):
            persistence_totals[agreement_class] += 1
            if state(row) == state(rows[index + 1]):
                persistence_counts[agreement_class] += 1
            if (state(row), state(rows[index + 1])) in DIRECT_FLIP_STATES:
                direct_flip_prior_current[agreement_class] += 1
                direct_flip_prior_current[agreement_class_for_row(rows[index + 1])] += 1
    return {
        "distribution": distribution_dict(agreement_classes, len(rows)),
        "by_state_confidence": {
            f"{agreement}/{regime_state}/{confidence}": count
            for (agreement, regime_state, confidence), count in sorted(by_state_confidence.items())
        },
        "persistence_by_agreement": {
            agreement: {
                "same_state_next_count": persistence_counts[agreement],
                "eligible_rows": persistence_totals[agreement],
                "same_state_next_pct": pct(persistence_counts[agreement], persistence_totals[agreement]),
            }
            for agreement in sorted(persistence_totals)
        },
        "direct_flip_prior_or_current_agreement_distribution": distribution_dict(
            direct_flip_prior_current,
            sum(direct_flip_prior_current.values()),
        ),
    }


def flip_path_analysis(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    direct_changes = []
    buffered_changes = []
    for left, right in with_next(rows):
        if (state(left), state(right)) in DIRECT_FLIP_STATES:
            direct_changes.append(abs(decimal_or_zero(right.get("regime_score_normalized")) - decimal_or_zero(left.get("regime_score_normalized"))))
    for first, second, third in zip(rows, rows[1:], rows[2:]):
        if state(second) == "NEUTRAL" and (state(first), state(third)) in DIRECT_FLIP_STATES:
            buffered_changes.append(abs(decimal_or_zero(third.get("regime_score_normalized")) - decimal_or_zero(first.get("regime_score_normalized"))))
    direct_count = len(direct_changes)
    buffered_count = len(buffered_changes)
    total = direct_count + buffered_count
    return {
        "direct_count": direct_count,
        "direct_pct": pct(direct_count, total),
        "buffered_count": buffered_count,
        "buffered_pct": pct(buffered_count, total),
        "direct_median_abs_score_change": round_decimal(median_decimal(direct_changes)),
        "buffered_median_abs_score_change": round_decimal(median_decimal(buffered_changes)),
    }


def sign_reversal_analysis(score_changes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(row["sign_reversal_type"] for row in score_changes if row["sign_reversal_type"] != "NO_SIGN_REVERSAL")
    return distribution_dict(counter, sum(counter.values()))


def streak_statistics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    lengths_by_state = {regime_state: [] for regime_state in CLASSIFIED_STATES}
    current_state = ""
    current_length = 0
    for row in rows:
        row_state = state(row)
        if row_state not in CLASSIFIED_STATES:
            if current_state in CLASSIFIED_STATES and current_length:
                lengths_by_state[current_state].append(current_length)
            current_state = ""
            current_length = 0
            continue
        if row_state == current_state:
            current_length += 1
        else:
            if current_state in CLASSIFIED_STATES and current_length:
                lengths_by_state[current_state].append(current_length)
            current_state = row_state
            current_length = 1
    if current_state in CLASSIFIED_STATES and current_length:
        lengths_by_state[current_state].append(current_length)
    return {regime_state: streak_distribution(lengths) for regime_state, lengths in lengths_by_state.items()}


def one_day_state_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    streaks = state_streaks([state(row) for row in rows])
    summary = {}
    for target_state in ("BULLISH", "BEARISH"):
        isolated = [
            streak
            for streak in streaks
            if streak["state"] == target_state and streak["length"] == 1 and streak["start_index"] > 0 and streak["end_index"] < len(rows) - 1
        ]
        summary[target_state] = {
            "isolated_one_day_count": len(isolated),
            "dates": [rows[streak["start_index"]]["trading_date"] for streak in isolated[:50]],
        }
    return summary


def scenario_analysis(
    rows: Sequence[dict[str, Any]],
    config: MarketRegimeConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    baseline_states = [state(row) for row in rows]
    scenarios: list[tuple[str, str, list[str], dict[str, Any]]] = [
        ("BASELINE", "BASELINE", baseline_states, {"delays": []}),
        ("DEADBAND_35", "DEAD_BAND", classify_rows_by_threshold(rows, Decimal("35"), Decimal("-35"), config), {"delays": []}),
        ("DEADBAND_40", "DEAD_BAND", classify_rows_by_threshold(rows, Decimal("40"), Decimal("-40"), config), {"delays": []}),
    ]
    scenarios.append(("HYSTERESIS_30_20", "HYSTERESIS", simulate_hysteresis(rows, Decimal("30"), Decimal("-30"), Decimal("20"), Decimal("-20"), config), {"delays": []}))
    scenarios.append(("HYSTERESIS_35_20", "HYSTERESIS", simulate_hysteresis(rows, Decimal("35"), Decimal("-35"), Decimal("20"), Decimal("-20"), config), {"delays": []}))
    persistence_2, delays_2 = simulate_minimum_persistence(rows, 2)
    persistence_3, delays_3 = simulate_minimum_persistence(rows, 3)
    scenarios.append(("PERSISTENCE_2", "MINIMUM_PERSISTENCE", persistence_2, {"delays": delays_2}))
    scenarios.append(("PERSISTENCE_3", "MINIMUM_PERSISTENCE", persistence_3, {"delays": delays_3}))
    scenarios.append(("SCORE_MEAN_2", "TRAILING_SCORE_MEAN", simulate_score_smoothing(rows, 2, config), {"delays": []}))
    scenarios.append(("SCORE_MEAN_3", "TRAILING_SCORE_MEAN", simulate_score_smoothing(rows, 3, config), {"delays": []}))

    metrics = []
    state_rows = []
    for scenario_name, scenario_type, scenario_states, metadata in scenarios:
        metrics.append(scenario_metrics(scenario_name, scenario_type, scenario_states, baseline_states, metadata))
        for row, scenario_state, baseline_state in zip(rows, scenario_states, baseline_states):
            state_rows.append(
                {
                    "scenario": scenario_name,
                    "trading_date": row["trading_date"],
                    "baseline_state": baseline_state,
                    "scenario_state": scenario_state,
                    "normalized_score": round_decimal(parse_decimal(row.get("regime_score_normalized"))),
                    "available_weight_pct": round_decimal(parse_decimal(row.get("available_weight_pct"))),
                }
            )
    return metrics, {row["scenario"]: row for row in metrics}, state_rows


def scenario_metrics(
    scenario_name: str,
    scenario_type: str,
    scenario_states: Sequence[str],
    baseline_states: Sequence[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(scenario_states)
    streaks = {regime_state: streak_distribution(state_streak_lengths(scenario_states, regime_state)) for regime_state in CLASSIFIED_STATES}
    same = sum(1 for left, right in zip(scenario_states, baseline_states) if left == right)
    delays = metadata.get("delays", [])
    return {
        "scenario": scenario_name,
        "scenario_type": scenario_type,
        "bullish_count": counts["BULLISH"],
        "neutral_count": counts["NEUTRAL"],
        "bearish_count": counts["BEARISH"],
        "unavailable_count": counts["UNAVAILABLE"],
        "direct_bullish_bearish_flips": direct_flip_count_for_states(scenario_states),
        "one_day_bullish_states": len(state_streak_lengths(scenario_states, "BULLISH", only_one_day=True)),
        "one_day_bearish_states": len(state_streak_lengths(scenario_states, "BEARISH", only_one_day=True)),
        "median_bullish_streak": streaks["BULLISH"]["median"],
        "median_bearish_streak": streaks["BEARISH"]["median"],
        "overall_state_agreement_pct": pct(same, len(scenario_states)),
        "regime_state_jaccard": round_decimal(state_jaccard(scenario_states, baseline_states)),
        "average_transition_delay": round_decimal(sum(delays) / Decimal(len(delays)) if delays else Decimal("0")),
        "delayed_transitions": len(delays),
    }


def classify_rows_by_threshold(
    rows: Sequence[dict[str, Any]],
    bullish_min: Decimal,
    bearish_max: Decimal,
    config: MarketRegimeConfig,
) -> list[str]:
    return [
        classify_score(
            parse_decimal(row.get("regime_score_normalized")),
            parse_decimal(row.get("available_weight_pct")) or Decimal("0"),
            bullish_min=bullish_min,
            bearish_max=bearish_max,
            min_available=config.classification.minimum_available_weight_pct,
        )
        for row in rows
    ]


def simulate_hysteresis(
    rows: Sequence[dict[str, Any]],
    enter_bullish: Decimal,
    enter_bearish: Decimal,
    exit_bullish: Decimal,
    exit_bearish: Decimal,
    config: MarketRegimeConfig,
) -> list[str]:
    output: list[str] = []
    previous_state = "NEUTRAL"
    for row in rows:
        score_value = parse_decimal(row.get("regime_score_normalized"))
        available_weight = parse_decimal(row.get("available_weight_pct")) or Decimal("0")
        if score_value is None or available_weight < config.classification.minimum_available_weight_pct:
            current = "UNAVAILABLE"
        elif previous_state == "BULLISH":
            if score_value >= exit_bullish:
                current = "BULLISH"
            elif score_value <= enter_bearish:
                current = "BEARISH"
            else:
                current = "NEUTRAL"
        elif previous_state == "BEARISH":
            if score_value <= exit_bearish:
                current = "BEARISH"
            elif score_value >= enter_bullish:
                current = "BULLISH"
            else:
                current = "NEUTRAL"
        else:
            current = classify_score(
                score_value,
                available_weight,
                bullish_min=enter_bullish,
                bearish_max=enter_bearish,
                min_available=config.classification.minimum_available_weight_pct,
            )
        output.append(current)
        if current != "UNAVAILABLE":
            previous_state = current
    return output


def simulate_minimum_persistence(rows: Sequence[dict[str, Any]], required_sessions: int) -> tuple[list[str], list[Decimal]]:
    baseline = [state(row) for row in rows]
    output: list[str] = []
    active_state = "UNAVAILABLE"
    pending_opposite = ""
    pending_count = 0
    delays: list[Decimal] = []
    for proposed in baseline:
        if proposed == "UNAVAILABLE":
            output.append("UNAVAILABLE")
            active_state = "UNAVAILABLE"
            pending_opposite = ""
            pending_count = 0
            continue
        if (active_state, proposed) in DIRECT_FLIP_STATES:
            if pending_opposite == proposed:
                pending_count += 1
            else:
                pending_opposite = proposed
                pending_count = 1
            if pending_count >= required_sessions:
                active_state = proposed
                output.append(proposed)
                delays.append(Decimal(required_sessions - 1))
                pending_opposite = ""
                pending_count = 0
            else:
                output.append("NEUTRAL")
            continue
        active_state = proposed
        pending_opposite = ""
        pending_count = 0
        output.append(proposed)
    return output, delays


def simulate_score_smoothing(rows: Sequence[dict[str, Any]], window: int, config: MarketRegimeConfig) -> list[str]:
    scores: list[Decimal | None] = []
    output = []
    for row in rows:
        score_value = parse_decimal(row.get("regime_score_normalized"))
        available_weight = parse_decimal(row.get("available_weight_pct")) or Decimal("0")
        scores.append(score_value)
        trailing = [value for value in scores[-window:] if value is not None]
        smoothed = sum(trailing) / Decimal(len(trailing)) if trailing else None
        output.append(
            classify_score(
                smoothed,
                available_weight,
                bullish_min=config.classification.bullish_min,
                bearish_max=config.classification.bearish_max,
                min_available=config.classification.minimum_available_weight_pct,
            )
        )
    return output


def write_market_regime_stability_audit_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Market Regime Stability Audit",
        "",
        "Current phase: Step 02.7 / Command 02 - audit historical regime stability",
        "",
        "## Boundary",
        "",
        "- This is MARKET_REGIME_AUDIT_V1, a structural audit of MARKET_REGIME_V1.",
        "- MARKET_REGIME_V1 is not changed by this audit.",
        "- No future outcomes, future returns, candidate/setup outcomes, MFE, MAE, winners/losers, stops, targets, backtesting, entry scoring, trading execution, migrations, or Supabase writes are used.",
        "",
        "## Version",
        "",
        f"- Audit version: {report['audit']['audit_version']}",
        f"- Regime version/config hash: {report['audit']['regime_version']} / {report['audit']['regime_config_hash']}",
        f"- Baseline hash unchanged: {report['regression']['market_regime_dataset_unchanged']}",
        "",
        "## Direct Flips",
        "",
        f"- Direct Bullish/Bearish flips: {report['direct_flips']['observed_count']}",
        f"- Dominant drivers: {report['direct_flips']['dominant_driver_distribution']}",
        f"- Structural classes: {report['direct_flips']['structural_classification_distribution']}",
        f"- Flip quality result: {report['decision']['flip_quality_result']}",
        "",
        "## Stability",
        "",
        f"- Score-change distribution: {report['score_changes']['distribution']}",
        f"- Boundary analysis: {report['boundary_analysis']['threshold_bands']}",
        f"- One-day states: {report['one_day_states']}",
        f"- Stability result: {report['decision']['regime_stability_result']}",
        "",
        "## Normalization And Confidence",
        "",
        f"- Normalization result: {report['normalization']['classification_artifact_result']}",
        f"- Multiplier distribution: {report['normalization']['multiplier_distribution']}",
        f"- Confidence ceiling: {report['confidence']['theoretical_ceiling']}",
        f"- Confidence result: {report['decision']['confidence_result']}",
        "",
        "## Scenarios",
        "",
    ]
    for name, row in report["sensitivity"]["scenarios"].items():
        lines.append(
            f"- {name}: direct flips={row['direct_bullish_bearish_flips']}, one-day Bullish={row['one_day_bullish_states']}, one-day Bearish={row['one_day_bearish_states']}, agreement={row['overall_state_agreement_pct']}%"
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Summary JSON: {report['outputs']['summary_json']}",
            f"- Direct flips CSV: {report['outputs']['direct_flips_csv']}",
            f"- Flip drivers CSV: {report['outputs']['flip_drivers_csv']}",
            f"- Score changes CSV: {report['outputs']['score_changes_csv']}",
            f"- Component transitions CSV: {report['outputs']['component_transitions_csv']}",
            f"- Confidence audit CSV: {report['outputs']['confidence_audit_csv']}",
            f"- Sensitivity CSV: {report['outputs']['sensitivity_csv']}",
            f"- Bulk audit directory: {report['outputs']['bulk_audit_dir']}",
            "",
            "## Decision",
            "",
            f"- Baseline decision: {report['decision']['baseline_decision']}",
            "- Any methodology change would require a separate command.",
            "",
            "## Known Limitations",
            "",
            "- India VIX, Global/GIFT, and intraday confirmation remain unavailable in the historical baseline.",
            "- Nifty 500 breadth inherits partial-history membership reconstruction.",
            "- Counterfactual scenarios are structural diagnostics only, not adopted methodology.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def load_regime_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            if row.get("trading_date"):
                rows.append(row)
    return rows


def load_header(path: Path) -> list[str]:
    with open_csv_maybe_gzip(path) as file:
        return list(csv.DictReader(file).fieldnames or [])


def baseline_hashes(config: MarketRegimeStabilityAuditConfig) -> dict[str, str]:
    return {
        "regime": file_sha256(config.regime_dataset_path),
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
    }


def component_pair_fields(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for _component_name, prefix, _weight in COMPONENTS:
        output[f"{prefix}_status_t"] = left.get(f"{prefix}_status", "")
        output[f"{prefix}_state_t"] = left.get(f"{prefix}_state", "")
        output[f"{prefix}_contribution_t"] = round_decimal(parse_decimal(left.get(f"{prefix}_contribution")))
        output[f"{prefix}_status_t1"] = right.get(f"{prefix}_status", "")
        output[f"{prefix}_state_t1"] = right.get(f"{prefix}_state", "")
        output[f"{prefix}_contribution_t1"] = round_decimal(parse_decimal(right.get(f"{prefix}_contribution")))
    return output


def contribution_delta(flip: dict[str, Any], prefix: str) -> Decimal | None:
    left = parse_decimal(flip.get(f"{prefix}_contribution_t"))
    right = parse_decimal(flip.get(f"{prefix}_contribution_t1"))
    if left is None or right is None:
        return None
    return right - left


def contribution_delta_from_rows(left: dict[str, Any], right: dict[str, Any], prefix: str) -> Decimal | None:
    left_value = parse_decimal(left.get(f"{prefix}_contribution"))
    right_value = parse_decimal(right.get(f"{prefix}_contribution"))
    if left_value is None or right_value is None:
        return None
    return right_value - left_value


def raw_equivalent_direct_flip(flip: dict[str, Any], config: MarketRegimeConfig) -> bool:
    left_state = classify_raw_values(
        parse_decimal(flip.get("raw_score_t")),
        parse_decimal(flip.get("available_weight_t")) or Decimal("0"),
        config,
    )
    right_state = classify_raw_values(
        parse_decimal(flip.get("raw_score_t1")),
        parse_decimal(flip.get("available_weight_t1")) or Decimal("0"),
        config,
    )
    return (left_state, right_state) in DIRECT_FLIP_STATES


def classify_raw_equivalent_row(row: dict[str, Any], config: MarketRegimeConfig) -> str:
    return classify_raw_values(
        parse_decimal(row.get("regime_score_raw")),
        parse_decimal(row.get("available_weight_pct")) or Decimal("0"),
        config,
    )


def classify_raw_values(raw_score: Decimal | None, available_weight_pct: Decimal, config: MarketRegimeConfig) -> str:
    if raw_score is None or available_weight_pct < config.classification.minimum_available_weight_pct:
        return "UNAVAILABLE"
    bullish_raw = config.classification.bullish_min * available_weight_pct / Decimal("100")
    bearish_raw = config.classification.bearish_max * available_weight_pct / Decimal("100")
    if raw_score >= bullish_raw:
        return "BULLISH"
    if raw_score <= bearish_raw:
        return "BEARISH"
    return "NEUTRAL"


def classify_score(
    score_value: Decimal | None,
    available_weight: Decimal,
    *,
    bullish_min: Decimal,
    bearish_max: Decimal,
    min_available: Decimal,
) -> str:
    if score_value is None or available_weight < min_available:
        return "UNAVAILABLE"
    if score_value >= bullish_min:
        return "BULLISH"
    if score_value <= bearish_max:
        return "BEARISH"
    return "NEUTRAL"


def theoretical_confidence_ceiling(rows: Sequence[dict[str, Any]], config: MarketRegimeConfig) -> dict[str, Any]:
    available_weights = [parse_decimal(row.get("available_weight_pct")) for row in rows]
    coverage_scores = [row_weighted_coverage_pct(row) for row in rows]
    penalties = [partial_membership_penalty(row, config) for row in rows]
    max_available = max((value for value in available_weights if value is not None), default=Decimal("0"))
    max_coverage = max((value for value in coverage_scores if value is not None), default=Decimal("0"))
    min_penalty = min(penalties, default=Decimal("0"))
    possible_scores = []
    for row in rows:
        available_weight = parse_decimal(row.get("available_weight_pct")) or Decimal("0")
        possible_scores.append(
            available_weight * config.confidence.availability_weight
            + Decimal("100") * config.confidence.agreement_weight
            + row_weighted_coverage_pct(row) * config.confidence.coverage_weight
            - partial_membership_penalty(row, config)
        )
    theoretical_max = max(possible_scores, default=Decimal("0"))
    theoretical_max = max(Decimal("0"), min(Decimal("100"), theoretical_max))
    observed_scores = [parse_decimal(row.get("confidence_score")) for row in rows]
    observed_scores = [value for value in observed_scores if value is not None]
    return {
        "theoretical_max": round_decimal(theoretical_max),
        "max_available_weight_observed": round_decimal(max_available),
        "max_weighted_component_coverage_observed": round_decimal(max_coverage),
        "minimum_partial_membership_penalty_observed": round_decimal(min_penalty),
        "observed_p50": round_decimal(decimal_quantile(observed_scores, Decimal("0.50"))),
        "observed_p90": round_decimal(decimal_quantile(observed_scores, Decimal("0.90"))),
        "observed_p95": round_decimal(decimal_quantile(observed_scores, Decimal("0.95"))),
        "observed_max": round_decimal(max(observed_scores) if observed_scores else None),
        "high_mathematically_unreachable": theoretical_max < config.confidence.high_threshold,
    }


def row_weighted_coverage_pct(row: dict[str, Any]) -> Decimal:
    trend_checks = [
        "nifty50_return_5d",
        "nifty50_return_20d",
        "nifty50_distance_sma20_pct",
        "nifty50_distance_sma50_pct",
        "nifty50_distance_sma200_pct",
        "nifty50_sma20_slope_10d_pct",
    ]
    trend_coverage = Decimal(sum(1 for field in trend_checks if parse_decimal(row.get(field)) is not None)) / Decimal(len(trend_checks)) * Decimal("100")
    breadth_coverage = parse_decimal(row.get("breadth_coverage_pct")) or Decimal("0")
    sector_coverage = parse_decimal(row.get("sector_coverage_pct")) or Decimal("0")
    weighted = (
        Decimal("30") * min(trend_coverage, Decimal("100")) / Decimal("100")
        + Decimal("20") * min(breadth_coverage, Decimal("100")) / Decimal("100")
        + Decimal("15") * min(sector_coverage, Decimal("100")) / Decimal("100")
    )
    return weighted


def partial_membership_penalty(row: dict[str, Any], config: MarketRegimeConfig) -> Decimal:
    warnings = str(row.get("warnings", ""))
    if "NIFTY500_MEMBERSHIP_PARTIAL_HISTORY" in warnings:
        return config.confidence.partial_membership_penalty
    return Decimal("0")


def high_confidence_absence_reason(theoretical: dict[str, Any], confidence_counts: Counter[str], config: MarketRegimeConfig) -> str:
    if confidence_counts["HIGH"]:
        return "HIGH confidence is present."
    if truthy(theoretical["high_mathematically_unreachable"]):
        return "HIGH confidence is mathematically unreachable because max available historical weight is capped near 65%, 35% target weight is unavailable, and partial membership penalties apply."
    if decimal_or_zero(theoretical["observed_max"]) < config.confidence.high_threshold:
        return "HIGH confidence is absent because observed agreement/coverage never reaches the high threshold."
    return "HIGH confidence absence is inconclusive."


def state_counts(rows: Sequence[dict[str, Any]], *, field: str = "regime_state") -> dict[str, Any]:
    counter = Counter(str(row.get(field, "")) for row in rows)
    return distribution_dict(counter, len(rows))


def audit_criteria(config: MarketRegimeConfig) -> dict[str, Any]:
    return {
        "direct_flip_structural_classes": {
            "STRONG_MULTI_COMPONENT_REVERSAL": "At least two available components reverse and both sides have absolute normalized score >=50 with >=80 point move.",
            "MODERATE_MULTI_COMPONENT_REVERSAL": "At least two available components reverse without meeting strong magnitude criteria.",
            "SINGLE_COMPONENT_BUCKET_JUMP": "One available component bucket or contribution change dominates.",
            "BORDERLINE_THRESHOLD_FLIP": "At least one side is within 10 normalized points of +/-30.",
            "COVERAGE/NORMALIZATION_ARTIFACT": "Available weight changed or raw/normalized equivalence fails.",
            "INCONCLUSIVE": "No single structural criterion dominates.",
        },
        "score_change_bands": "LOW <= median absolute change; MODERATE <= p90; HIGH <= p95; EXTREME > p95.",
        "deadband_scenarios": ["DEADBAND_35", "DEADBAND_40"],
        "hysteresis_scenarios": ["HYSTERESIS_30_20", "HYSTERESIS_35_20"],
        "minimum_persistence_scenarios": ["PERSISTENCE_2", "PERSISTENCE_3"],
        "score_smoothing_scenarios": ["SCORE_MEAN_2", "SCORE_MEAN_3"],
        "baseline_thresholds": {
            "bullish_min": round_decimal(config.classification.bullish_min),
            "bearish_max": round_decimal(config.classification.bearish_max),
            "minimum_available_weight_pct": round_decimal(config.classification.minimum_available_weight_pct),
        },
    }


def component_threshold_description(component_name: str, config: MarketRegimeConfig) -> str:
    if component_name == "NIFTY_TREND":
        trend = config.trend
        return (
            "score_ratio strong<=-0.67/-0.25/0.25/0.67; "
            f"5d return thresholds {trend.strong_negative_return_5d},{trend.negative_return_5d},{trend.positive_return_5d},{trend.strong_positive_return_5d}; "
            f"20d return thresholds {trend.strong_negative_return_20d},{trend.negative_return_20d},{trend.positive_return_20d},{trend.strong_positive_return_20d}; "
            f"sma20 slope thresholds {trend.sma_slope_negative},{trend.sma_slope_positive}"
        )
    if component_name == "NIFTY500_BREADTH":
        breadth = config.breadth
        return f"percent thresholds <= {breadth.strongly_bearish_pct}, <= {breadth.bearish_pct}, >= {breadth.bullish_pct}, >= {breadth.strongly_bullish_pct}"
    sector = config.sector
    return f"percent thresholds <= {sector.strongly_bearish_pct}, <= {sector.bearish_pct}, >= {sector.bullish_pct}, >= {sector.strongly_bullish_pct}; median 5d sector return sign contributes one point"


def contribution_step_sizes(target_weight: Decimal) -> str:
    strong = target_weight
    normal = target_weight * Decimal("0.60")
    return f"STRONGLY_BEARISH {-strong}, BEARISH {-normal}, NEUTRAL 0, BULLISH {normal}, STRONGLY_BULLISH {strong}"


def prohibited_outcome_fields(fields: Sequence[str]) -> list[str]:
    flagged = []
    for field in fields:
        lower = field.lower()
        if any(token in lower for token in PROHIBITED_OUTCOME_FIELD_TOKENS):
            flagged.append(field)
    return flagged


def component_direction(value: Any) -> str:
    parsed = parse_decimal(value)
    if parsed is None or parsed == 0:
        return ""
    return "POSITIVE" if parsed > 0 else "NEGATIVE"


def agreement_class_for_row(row: dict[str, Any]) -> str:
    directions = []
    for _component_name, prefix, _weight in COMPONENTS[:3]:
        contribution = parse_decimal(row.get(f"{prefix}_contribution"))
        if contribution is None:
            continue
        if contribution > 0:
            directions.append("POSITIVE")
        elif contribution < 0:
            directions.append("NEGATIVE")
        else:
            directions.append("NEUTRAL")
    if not directions:
        return "MIXED"
    counts = Counter(directions)
    non_neutral = {direction for direction in directions if direction != "NEUTRAL"}
    if len(non_neutral) == 1 and counts["NEUTRAL"] == 0:
        return "FULL_AVAILABLE_AGREEMENT"
    if counts["POSITIVE"] and counts["NEGATIVE"] and counts["POSITIVE"] == counts["NEGATIVE"]:
        return "CONFLICTING"
    if counts["POSITIVE"] >= 2 or counts["NEGATIVE"] >= 2:
        return "MAJORITY_AGREEMENT"
    if counts["POSITIVE"] and counts["NEGATIVE"]:
        return "CONFLICTING"
    return "MIXED"


def score_magnitude_bucket(row: dict[str, Any]) -> str:
    score_value = parse_decimal(row.get("regime_score_normalized"))
    if score_value is None:
        return "UNAVAILABLE"
    magnitude = abs(score_value)
    if magnitude < Decimal("30"):
        return "0-30"
    if magnitude < Decimal("50"):
        return "30-50"
    if magnitude < Decimal("70"):
        return "50-70"
    return "70-100"


def score_bucket_for_borderline(row: dict[str, Any]) -> str:
    score_value = parse_decimal(row.get("regime_score_normalized"))
    if score_value is None:
        return ""
    if Decimal("30") <= score_value <= Decimal("40"):
        return "BORDERLINE_BULLISH"
    if Decimal("-40") <= score_value <= Decimal("-30"):
        return "BORDERLINE_BEARISH"
    if score_value > Decimal("40"):
        return "CORE_BULLISH"
    if score_value < Decimal("-40"):
        return "CORE_BEARISH"
    return ""


def sign_reversal_type(left: dict[str, Any], right: dict[str, Any]) -> str:
    left_score = parse_decimal(left.get("regime_score_normalized"))
    right_score = parse_decimal(right.get("regime_score_normalized"))
    if left_score is None or right_score is None or left_score == 0 or right_score == 0 or (left_score > 0) == (right_score > 0):
        return "NO_SIGN_REVERSAL"
    if (state(left), state(right)) in DIRECT_FLIP_STATES:
        return "DIRECT_OPPOSITE_REGIME"
    if (state(left) in {"BULLISH", "BEARISH"} and state(right) == "NEUTRAL") or (
        state(left) == "NEUTRAL" and state(right) in {"BULLISH", "BEARISH"}
    ):
        return "CROSSED_ONE_REGIME_BOUNDARY"
    if state(left) == "NEUTRAL" and state(right) == "NEUTRAL":
        return "REMAINED_NEUTRAL"
    return "CROSSED_SIGN_ONLY"


def exactly_one_component_changed_discretely(left: dict[str, Any], right: dict[str, Any]) -> bool:
    changed = 0
    for _component_name, prefix, _weight in COMPONENTS[:3]:
        if bucket_level_delta(str(left.get(f"{prefix}_state", "")), str(right.get(f"{prefix}_state", ""))) > 0:
            changed += 1
    return changed == 1


def multiple_components_moved_coherently(left: dict[str, Any], right: dict[str, Any]) -> bool:
    deltas = [
        contribution_delta_from_rows(left, right, prefix)
        for _component_name, prefix, _weight in COMPONENTS[:3]
    ]
    directions = [1 if delta and delta > 0 else -1 if delta and delta < 0 else 0 for delta in deltas]
    return directions.count(1) >= 2 or directions.count(-1) >= 2


def change_band_thresholds(changes: Sequence[Decimal]) -> dict[str, Decimal]:
    return {
        "low_max": decimal_quantile(changes, Decimal("0.50")),
        "moderate_max": decimal_quantile(changes, Decimal("0.90")),
        "high_max": decimal_quantile(changes, Decimal("0.95")),
    }


def change_band(change: Decimal, thresholds: dict[str, Decimal]) -> str:
    if change <= thresholds["low_max"]:
        return "LOW_CHANGE"
    if change <= thresholds["moderate_max"]:
        return "MODERATE_CHANGE"
    if change <= thresholds["high_max"]:
        return "HIGH_CHANGE"
    return "EXTREME_CHANGE"


def direct_flip_count_for_states(states: Sequence[str]) -> int:
    return sum(1 for left, right in zip(states, states[1:]) if (left, right) in DIRECT_FLIP_STATES)


def state_streak_lengths(states: Sequence[str], target_state: str, *, only_one_day: bool = False) -> list[int]:
    lengths = [streak["length"] for streak in state_streaks(states) if streak["state"] == target_state]
    if only_one_day:
        return [length for length in lengths if length == 1]
    return lengths


def state_streaks(states: Sequence[str]) -> list[dict[str, Any]]:
    output = []
    if not states:
        return output
    start = 0
    current = states[0]
    for index, item in enumerate(states[1:], start=1):
        if item != current:
            output.append({"state": current, "start_index": start, "end_index": index - 1, "length": index - start})
            start = index
            current = item
    output.append({"state": current, "start_index": start, "end_index": len(states) - 1, "length": len(states) - start})
    return output


def state_jaccard(left_states: Sequence[str], right_states: Sequence[str]) -> Decimal:
    left = {(index, state_value) for index, state_value in enumerate(left_states) if state_value in CLASSIFIED_STATES}
    right = {(index, state_value) for index, state_value in enumerate(right_states) if state_value in CLASSIFIED_STATES}
    union = left | right
    if not union:
        return Decimal("1")
    return Decimal(len(left & right)) / Decimal(len(union))


def streak_distribution(lengths: Sequence[int]) -> dict[str, Any]:
    if not lengths:
        return {
            "streak_count": 0,
            "one_session": 0,
            "one_session_pct": "0.0000",
            "median": 0,
            "mean": 0,
            "p90": 0,
            "p95": 0,
            "max": 0,
        }
    ordered = sorted(lengths)
    one_session = sum(1 for value in ordered if value == 1)
    return {
        "streak_count": len(ordered),
        "one_session": one_session,
        "one_session_pct": pct(one_session, len(ordered)),
        "median": statistics.median(ordered),
        "mean": round(statistics.mean(ordered), 4),
        "p90": int_quantile(ordered, Decimal("0.90")),
        "p95": int_quantile(ordered, Decimal("0.95")),
        "max": ordered[-1],
    }


def regime_stability_result(
    score_change_summary: dict[str, Any],
    flip_driver_summary: dict[str, Any],
    streaks: dict[str, Any],
) -> str:
    direct_flips = score_change_summary["direct_flip_count"]
    structural = flip_driver_summary["structural_classification_distribution"]
    artifact_count = structural.get("COVERAGE/NORMALIZATION_ARTIFACT", {}).get("count", 0)
    excessive_borderline = structural.get("BORDERLINE_THRESHOLD_FLIP", {}).get("count", 0) + structural.get("SINGLE_COMPONENT_BUCKET_JUMP", {}).get("count", 0)
    bullish_median = Decimal(str(streaks["BULLISH"]["median"]))
    bearish_median = Decimal(str(streaks["BEARISH"]["median"]))
    if artifact_count:
        return "MODERATELY_UNSTABLE"
    if direct_flips > 75 or excessive_borderline > direct_flips * Decimal("0.60"):
        return "UNSTABLE"
    if direct_flips > 40:
        return "MODERATELY_UNSTABLE"
    if direct_flips > 0 and min(bullish_median, bearish_median) >= Decimal("2"):
        return "STABLE_WITH_SOME_FAST_FLIPS"
    if direct_flips == 0:
        return "STABLE"
    return "INCONCLUSIVE"


def confidence_result(confidence_summary: dict[str, Any], config: MarketRegimeConfig) -> str:
    theoretical_max = decimal_or_zero(confidence_summary["theoretical_ceiling"]["theoretical_max"])
    observed_max = decimal_or_zero(confidence_summary["theoretical_ceiling"]["observed_max"])
    if theoretical_max < config.confidence.high_threshold and observed_max >= config.confidence.medium_threshold:
        return "CONSISTENT_BUT_CAPPED_BY_DATA_AVAILABILITY"
    if observed_max < config.confidence.medium_threshold:
        return "TOO_LOW"
    return "CONSISTENT"


def flip_quality_result(flip_driver_summary: dict[str, Any], score_change_summary: dict[str, Any]) -> str:
    structural = flip_driver_summary["structural_classification_distribution"]
    total = sum(int(row["count"]) for row in structural.values())
    if not total:
        return "EXPECTED_MARKET_REVERSALS"
    if structural.get("COVERAGE/NORMALIZATION_ARTIFACT", {}).get("count", 0):
        return "NORMALIZATION_ARTIFACT"
    borderline_like = structural.get("BORDERLINE_THRESHOLD_FLIP", {}).get("count", 0) + structural.get("SINGLE_COMPONENT_BUCKET_JUMP", {}).get("count", 0)
    if Decimal(borderline_like) / Decimal(total) > Decimal("0.55"):
        return "EXCESSIVE_THRESHOLD_WHIPSAW"
    strong_or_moderate = structural.get("STRONG_MULTI_COMPONENT_REVERSAL", {}).get("count", 0) + structural.get("MODERATE_MULTI_COMPONENT_REVERSAL", {}).get("count", 0)
    if strong_or_moderate:
        return "MOSTLY_REASONABLE_WITH_SOME_BORDERLINE_FLIPS"
    return "INCONCLUSIVE"


def baseline_decision_result(
    *,
    stability_result: str,
    flip_quality: str,
    confidence_result_value: str,
) -> str:
    if stability_result in {"STABLE", "STABLE_WITH_SOME_FAST_FLIPS"} and flip_quality != "NORMALIZATION_ARTIFACT":
        return "frozen unchanged"
    if confidence_result_value == "CONSISTENT_BUT_CAPPED_BY_DATA_AVAILABILITY":
        return "remain provisional"
    return "receive a separate change command"


def near_boundary(score_value: Decimal | None) -> bool:
    if score_value is None:
        return False
    return Decimal("30") <= abs(score_value) <= Decimal("40")


def bucket_level_delta(left_state: str, right_state: str) -> int:
    left = STATE_LEVEL.get(left_state)
    right = STATE_LEVEL.get(right_state)
    if left is None or right is None:
        return 0
    return abs(right - left)


def weight_bucket(weight: Decimal) -> str:
    if weight == Decimal("65"):
        return "65"
    if weight == Decimal("50"):
        return "50"
    if weight == Decimal("35"):
        return "35"
    return "OTHER"


def with_next(rows: Sequence[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return list(zip(rows, rows[1:]))


def state(row: dict[str, Any]) -> str:
    return str(row.get("regime_state", "") or "UNAVAILABLE")


def distribution_dict(counter: Counter[str] | Counter[tuple[str, str]], total: int) -> dict[str, Any]:
    if total <= 0:
        return {}
    return {
        str(key): {"count": count, "pct": pct(count, total)}
        for key, count in counter.most_common()
    }


def decimal_distribution(values: Sequence[Decimal | None]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {
            "usable_rows": 0,
            "min": "",
            "p10": "",
            "p25": "",
            "median": "",
            "mean": "",
            "p75": "",
            "p90": "",
            "p95": "",
            "p99": "",
            "max": "",
        }
    return {
        "usable_rows": len(clean),
        "min": round_decimal(clean[0]),
        "p10": round_decimal(decimal_quantile(clean, Decimal("0.10"))),
        "p25": round_decimal(decimal_quantile(clean, Decimal("0.25"))),
        "median": round_decimal(decimal_quantile(clean, Decimal("0.50"))),
        "mean": round_decimal(sum(clean) / Decimal(len(clean))),
        "p75": round_decimal(decimal_quantile(clean, Decimal("0.75"))),
        "p90": round_decimal(decimal_quantile(clean, Decimal("0.90"))),
        "p95": round_decimal(decimal_quantile(clean, Decimal("0.95"))),
        "p99": round_decimal(decimal_quantile(clean, Decimal("0.99"))),
        "max": round_decimal(clean[-1]),
    }


def decimal_quantile(values: Sequence[Decimal | None], percentile: Decimal) -> Decimal:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return Decimal("0")
    index = int((Decimal(len(clean) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return clean[min(index, len(clean) - 1)]


def int_quantile(values: Sequence[int], percentile: Decimal) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


def median_decimal(values: Sequence[Decimal | None]) -> Decimal | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    return Decimal(str(statistics.median(clean)))


def decimal_or_zero(value: Any) -> Decimal:
    return parse_decimal(value) or Decimal("0")


def parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text or text == "None":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def round_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.0001")), "f")


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def observed_single_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def output_size(config: MarketRegimeStabilityAuditConfig) -> int:
    paths = [
        config.summary_path,
        config.direct_flips_path,
        config.flip_drivers_path,
        config.score_changes_path,
        config.component_transitions_path,
        config.confidence_audit_path,
        config.sensitivity_path,
        config.direct_flips_bulk_path,
        config.top_score_jumps_bulk_path,
        config.scenario_state_series_path,
        config.boundary_rows_path,
        config.component_daily_changes_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())

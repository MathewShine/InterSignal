from __future__ import annotations

import csv
import gzip
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.risk.position_sizing import calculate_position_size
from app.risk.reward_risk import calculate_reward_risk
from app.risk.risk_config import RISK_STRUCTURE_VERSION, EntryReferenceRules, RiskStructureConfig, StopPlacementRules
from app.risk.risk_structurer import (
    RISK_OUTPUT_FIELDS,
    RiskStructureEngineConfig,
    atr_14_value,
    entry_reference_price,
    evaluate_risk_rows,
    load_adjusted_history,
    load_entry_rows,
    load_lookup,
    load_regime_lookup,
    output_size,
    patch_history_from_context,
    price_band,
    risk_status,
)
from app.risk.stop_placement import (
    StopCandidate,
    build_ohlc_index,
    priority_for_setup,
    stop_candidates,
    stop_distance_band,
    stop_quality,
)
from app.risk.target_planning import build_target_plan, structural_target
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip, split_codes

RISK_STRUCTURE_AUDIT_VERSION = "RISK_STRUCTURE_AUDIT_V1"

STOP_CANDIDATE_FIELDS = [
    "section",
    "basis",
    "rows",
    "pct",
    "available_rows",
    "eligible_rows",
    "valid_rows",
    "selected_rows",
    "selected_when_available_pct",
    "median_candidate_stop_distance_pct",
    "median_candidate_stop_distance_atr",
]
STOP_BASIS_AUDIT_FIELDS = [
    "section",
    "group_name",
    "basis",
    "rows",
    "pct",
    "valid_stop_rate_pct",
    "median_stop_distance_pct",
    "median_stop_distance_atr",
    "median_reward_risk",
    "ready_for_final_scoring_rate_pct",
]
TARGET_SEMANTICS_FIELDS = [
    "section",
    "group_name",
    "basis_or_status",
    "rows",
    "pct",
    "structural_available_rows",
    "structural_selected_rows",
    "fallback_selected_rows",
    "violations",
    "median_structural_reward_risk",
]
RR_FAILURE_CAUSE_FIELDS = ["cause", "rows", "pct", "median_stop_distance_pct", "median_structural_reward_risk"]
CAPITAL_AUDIT_FIELDS = ["section", "bucket_or_driver", "rows", "pct", "median_price", "median_stop_distance_pct", "median_quantity", "median_capital_utilization_pct", "ready_rate_pct"]
SENSITIVITY_FIELDS = [
    "scenario_group",
    "scenario",
    "valid_stop",
    "median_stop_pct",
    "median_stop_atr",
    "structural_target_selected",
    "fallback_target_selected",
    "rr_gte_1_5",
    "rr_gte_2_0",
    "final_ready",
    "median_quantity",
    "median_capital_utilization_pct",
    "median_planned_risk",
    "baseline_retained",
    "baseline_removed",
    "introduced",
    "jaccard_vs_baseline",
    "notes",
]
RISK_TOO_LARGE_FIELDS = ["trading_date", "symbol", "entry", "stop", "risk_per_share", "assumed_entry_price", "quantity_by_risk", "quantity_by_cash", "rejection_reasons"]
SINGLE_SHARE_FIELDS = ["trading_date", "symbol", "assumed_entry_price", "risk_per_share", "planned_rupee_risk", "reward_risk_ratio", "risk_readiness", "warning_flags"]
STOP_CANDIDATE_DETAIL_FIELDS = [
    "trading_date",
    "symbol",
    "setup_type",
    "selected_basis",
    "candidate_basis",
    "level",
    "eligible",
    "candidate_stop_price",
    "candidate_stop_distance_pct",
    "candidate_stop_distance_atr",
    "candidate_stop_band",
    "candidate_stop_quality",
    "selected",
]
STOP_SELECTION_DETAIL_FIELDS = [
    "trading_date",
    "symbol",
    "setup_type",
    "selected_basis",
    "candidate_count",
    "valid_candidate_count",
    "selected_rank_by_tightness",
    "selected_position",
    "tightest_basis",
    "widest_basis",
    "selected_stop_distance_pct",
    "tightest_stop_distance_pct",
    "widest_stop_distance_pct",
    "median_alternative_stop_distance_pct",
]
PROHIBITED_AUDIT_FIELD_TOKENS = (
    "future_return",
    "forward_return",
    "mfe",
    "mae",
    "winner",
    "loser",
    "profitability",
    "target_hit",
    "stop_hit",
    "trade_outcome",
    "backtest",
    "sharpe",
    "drawdown",
)


@dataclass(frozen=True, slots=True)
class RiskStructureAuditConfig:
    data_dir: Path
    risk_config: RiskStructureConfig = RiskStructureConfig()
    audit_version: str = RISK_STRUCTURE_AUDIT_VERSION

    @property
    def engine_config(self) -> RiskStructureEngineConfig:
        return RiskStructureEngineConfig(data_dir=self.data_dir, risk_config=self.risk_config)

    @property
    def risk_dataset_path(self) -> Path:
        return self.engine_config.output_dataset_path

    @property
    def entry_dataset_path(self) -> Path:
        return self.engine_config.entry_dataset_path

    @property
    def setup_dataset_path(self) -> Path:
        return self.engine_config.setup_dataset_path

    @property
    def feature_dataset_path(self) -> Path:
        return self.engine_config.feature_dataset_path

    @property
    def candidate_dataset_path(self) -> Path:
        return self.engine_config.candidate_dataset_path

    @property
    def regime_dataset_path(self) -> Path:
        return self.engine_config.regime_dataset_path

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.engine_config.adjusted_daily_dir

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "research" / "audits" / "risk_structure" / "v1"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "risk_structure_audit_summary.json"

    @property
    def stop_candidates_path(self) -> Path:
        return self.reports_dir / "risk_structure_stop_candidates.csv"

    @property
    def stop_basis_audit_path(self) -> Path:
        return self.reports_dir / "risk_structure_stop_basis_audit.csv"

    @property
    def target_semantics_path(self) -> Path:
        return self.reports_dir / "risk_structure_target_semantics.csv"

    @property
    def rr_failure_causes_path(self) -> Path:
        return self.reports_dir / "risk_structure_rr_failure_causes.csv"

    @property
    def capital_audit_path(self) -> Path:
        return self.reports_dir / "risk_structure_capital_audit.csv"

    @property
    def sensitivity_path(self) -> Path:
        return self.reports_dir / "risk_structure_sensitivity.csv"

    @property
    def risk_too_large_cases_path(self) -> Path:
        return self.reports_dir / "risk_structure_risk_too_large_cases.csv"

    @property
    def single_share_cases_path(self) -> Path:
        return self.reports_dir / "risk_structure_single_share_cases.csv"

    @property
    def stop_candidate_detail_path(self) -> Path:
        return self.audit_dir / "risk_structure_stop_candidate_inventory.csv.gz"

    @property
    def stop_selection_detail_path(self) -> Path:
        return self.audit_dir / "risk_structure_stop_selection_detail.csv.gz"

    @property
    def scenario_membership_path(self) -> Path:
        return self.audit_dir / "risk_structure_scenario_membership.csv.gz"


def build_risk_structure_audit(
    *,
    config: RiskStructureAuditConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = upstream_hashes(config)

    if progress:
        progress("Loading baseline RISK_STRUCTURE_V1 rows")
    risk_rows = load_risk_rows(config.risk_dataset_path)
    keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in risk_rows}
    dates = {date for date, _ in keys}
    symbols = {symbol for _, symbol in keys}

    if progress:
        progress("Loading immutable entry/setup/feature/regime context")
    entry_lookup = load_lookup(config.entry_dataset_path, keys)
    setup_lookup = load_lookup(config.setup_dataset_path, keys)
    feature_lookup = load_lookup(config.feature_dataset_path, keys)
    regime_lookup = load_regime_lookup(config.regime_dataset_path, dates)
    risk_rows = enrich_risk_rows(risk_rows, setup_lookup)

    if progress:
        progress("Reconstructing causal OHLC history and stop candidates")
    history = load_adjusted_history(
        adjusted_daily_dir=config.adjusted_daily_dir,
        symbols=symbols,
        through_date=max(dates) if dates else "",
    )
    patch_history_from_context(history=history, keys=keys, setup_lookup=setup_lookup, feature_lookup=feature_lookup)
    history_index = build_ohlc_index(history)
    candidate_audit_rows, selection_detail_rows = reconstruct_stop_candidate_inventory(
        risk_rows=risk_rows,
        entry_lookup=entry_lookup,
        setup_lookup=setup_lookup,
        feature_lookup=feature_lookup,
        history=history,
        history_index=history_index,
        config=config.risk_config,
    )

    if progress:
        progress("Auditing stop, target, reward:risk, and capital behavior")
    stop_candidate_summary = stop_candidate_availability(candidate_audit_rows, risk_rows)
    stop_basis_rows = stop_basis_audit(risk_rows)
    stop_basis_rows.extend(stop_basis_by_setup_type(risk_rows))
    stop_basis_rows.extend(stop_quality_audit(risk_rows))
    stop_basis_rows.extend(stop_distance_bucket_audit(risk_rows))
    stop_basis_rows.extend(stop_distance_atr_bucket_audit(risk_rows))
    stop_basis_rows.extend(stop_band_audit(risk_rows))

    target_rows, target_summary = target_semantics_audit(risk_rows)
    rr_failure_rows, rr_failure_summary = rr_failure_cause_audit(risk_rows)
    capital_rows, capital_summary = capital_audit(risk_rows)
    risk_too_large_cases = risk_too_large_rows(risk_rows)
    single_share_case_rows = single_share_rows(risk_rows)
    warning_summary = warning_distribution(risk_rows)
    rejection_summary = rejection_overlap(risk_rows)
    low_comparison = swing_low_comparison(candidate_audit_rows)
    multiple_stop_summary = multiple_stop_availability(selection_detail_rows, candidate_audit_rows)
    selected_vs_alternative_summary = selected_vs_alternative(selection_detail_rows)
    atr_buffer_summary = atr_buffer_contribution(risk_rows)

    if progress:
        progress("Running audit-only sensitivity and counterfactual scenarios")
    scenario_context = ScenarioContext(
        risk_rows=risk_rows,
        entry_lookup=entry_lookup,
        setup_lookup=setup_lookup,
        feature_lookup=feature_lookup,
        regime_lookup=regime_lookup,
        history=history,
        history_index=history_index,
        candidate_detail_rows=candidate_audit_rows,
    )
    sensitivity_rows, scenario_summary, scenario_membership = scenario_audit(config.risk_config, scenario_context)

    write_csv(config.stop_candidates_path, stop_candidate_summary["rows"], STOP_CANDIDATE_FIELDS)
    write_csv(config.stop_basis_audit_path, stop_basis_rows, STOP_BASIS_AUDIT_FIELDS)
    write_csv(config.target_semantics_path, target_rows, TARGET_SEMANTICS_FIELDS)
    write_csv(config.rr_failure_causes_path, rr_failure_rows, RR_FAILURE_CAUSE_FIELDS)
    write_csv(config.capital_audit_path, capital_rows, CAPITAL_AUDIT_FIELDS)
    write_csv(config.sensitivity_path, sensitivity_rows, SENSITIVITY_FIELDS)
    write_csv(config.risk_too_large_cases_path, risk_too_large_cases, RISK_TOO_LARGE_FIELDS)
    write_csv(config.single_share_cases_path, single_share_case_rows, SINGLE_SHARE_FIELDS)
    write_gzip_csv(config.stop_candidate_detail_path, candidate_audit_rows, STOP_CANDIDATE_DETAIL_FIELDS)
    write_gzip_csv(config.stop_selection_detail_path, selection_detail_rows, STOP_SELECTION_DETAIL_FIELDS)
    write_gzip_csv(config.scenario_membership_path, scenario_membership, ["scenario", "trading_date", "symbol", "risk_readiness"])

    hashes_after = upstream_hashes(config)
    risk_hash_unchanged = hashes_before["risk"] == hashes_after["risk"]
    risk_config_hash_unchanged = observed_single_value(risk_rows, "risk_config_hash") == config.risk_config.config_hash()
    prohibited_fields = prohibited_audit_fields()
    final_ready_violations = final_ready_invariant_violations(risk_rows)
    capital_violations = capital_risk_violations(risk_rows, config.risk_config)
    preview_violations = conditional_preview_violations(risk_rows)
    semantic_results = audit_results(
        stop_candidate_summary=stop_candidate_summary,
        scenario_summary=scenario_summary,
        target_summary=target_summary,
        capital_summary=capital_summary,
        final_ready_violations=final_ready_violations,
        capital_violations=capital_violations,
    )
    report = {
        "phase": "Step 02.9",
        "command": "Command 02",
        "audit_version": config.audit_version,
        "generated_at": generated_at,
        "risk": {
            "risk_version": observed_single_value(risk_rows, "risk_version"),
            "risk_config_hash": observed_single_value(risk_rows, "risk_config_hash"),
            "expected_risk_version": RISK_STRUCTURE_VERSION,
            "expected_risk_config_hash": config.risk_config.config_hash(),
            "risk_config_hash_unchanged": risk_config_hash_unchanged,
        },
        "inputs": {
            "versions": observed_versions(risk_rows, config),
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
        },
        "stop_implementation": {
            "candidate_structures_generated": [
                "BREAKOUT_STRUCTURE",
                "DAILY_RECLAIM_LOW",
                "CONSOLIDATION_LOW",
                "RECENT_SWING_LOW_3",
                "RECENT_SWING_LOW_5",
                "RECENT_SWING_LOW_10",
                "CANDLE_LOW",
                "SMA20_SUPPORT",
            ],
            "priority_order_source": "app.risk.stop_placement.priority_for_setup",
            "momentum_continuation_priority": list(priority_for_setup({"setup_type_flags": "MOMENTUM_CONTINUATION"}, config.risk_config)),
            "consolidation_priority": list(priority_for_setup({"setup_type_flags": "CONSOLIDATION_BREAKOUT"}, config.risk_config)),
            "reclaim_priority": list(priority_for_setup({"daily_level_reclaim": "True"}, config.risk_config)),
            "breakout_priority": list(priority_for_setup({"setup_type_flags": "BREAKOUT_20D"}, config.risk_config)),
            "eligibility_tests": "candidate level > 0, level < assumed_entry_price; selected stop then requires stop_price > 0 and stop_price < assumed entry; practical band and stop quality decide final validity.",
            "tie_breaking": "first valid basis in deterministic priority order; duplicate bases keep first generated candidate.",
            "fallback_behavior": "fallbacks are candle low and SMA20 support after setup-priority references.",
            "why_recent_swing_low_5_wins": stop_candidate_summary["why_recent_swing_low_5_wins"],
        },
        "stop_audit": {
            "baseline_distribution": selected_basis_distribution(risk_rows),
            "candidate_availability": stop_candidate_summary,
            "multiple_stop_availability": multiple_stop_summary,
            "selected_vs_alternative": selected_vs_alternative_summary,
            "swing_low_comparison": low_comparison,
            "atr_buffer_contribution": atr_buffer_summary,
            "breakout": setup_section_summary(risk_rows, "BREAKOUT_20D"),
            "consolidation": setup_section_summary(risk_rows, "CONSOLIDATION_BREAKOUT"),
            "reclaim": setup_section_summary(risk_rows, "DAILY_RECLAIM"),
            "continuation": setup_section_summary(risk_rows, "MOMENTUM_CONTINUATION"),
        },
        "target_audit": target_summary,
        "rr_failure_causes": rr_failure_summary,
        "capital_audit": capital_summary,
        "warnings": warning_summary,
        "rejections": rejection_summary,
        "sensitivity": scenario_summary,
        "leakage_safety": {
            "future_low_high_used": 0,
            "future_pivot_confirmation_used": 0,
            "future_resistance_used": 0,
            "future_stop_target_hit_used": 0,
            "future_returns_used": 0,
            "mfe_mae_used": 0,
            "notes": "Causal history reconstruction indexes only the row trading_date and prior bars; no future outcome columns are read.",
        },
        "regression": {
            "daily_features_v1_unchanged": hashes_before["feature"] == hashes_after["feature"],
            "momentum_candidates_v1_unchanged": hashes_before["candidate"] == hashes_after["candidate"],
            "daily_setup_evaluation_v1_unchanged": hashes_before["setup"] == hashes_after["setup"],
            "market_regime_v1_unchanged": hashes_before["regime"] == hashes_after["regime"],
            "entry_evaluation_v1_unchanged": hashes_before["entry"] == hashes_after["entry"],
            "risk_structure_v1_unchanged": risk_hash_unchanged,
        },
        "safety": {
            "future_return_fields_used": 0,
            "future_outcome_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "profitability_optimization_used": 0,
            "final_100_point_strategy_score_generated": 0,
            "buy_sell_signals_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "orders_placed": 0,
            "shorts_created": 0,
            "leverage_or_margin_used": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "prohibited_audit_fields": prohibited_fields,
        },
        "invariants": {
            "capital_risk_violations": capital_violations,
            "conditional_preview_violations": preview_violations,
            "final_ready_violations": final_ready_violations,
            "target_fallback_violations": target_summary["fallback_semantic_violations"],
            "artificial_2r_replacements": target_summary["artificial_2r_replacements"],
        },
        "decision": {
            "structural_stability": semantic_results["structural_stability"],
            "stop_semantics": semantic_results["stop_semantics"],
            "target_semantics": semantic_results["target_semantics"],
            "capital_risk": semantic_results["capital_risk"],
            "baseline_decision": semantic_results["baseline_decision"],
            "recommended_next_action": semantic_results["recommended_next_action"],
        },
        "outputs": {
            "summary_json": str(config.summary_path),
            "stop_candidates_csv": str(config.stop_candidates_path),
            "stop_basis_audit_csv": str(config.stop_basis_audit_path),
            "target_semantics_csv": str(config.target_semantics_path),
            "rr_failure_causes_csv": str(config.rr_failure_causes_path),
            "capital_audit_csv": str(config.capital_audit_path),
            "sensitivity_csv": str(config.sensitivity_path),
            "risk_too_large_cases_csv": str(config.risk_too_large_cases_path),
            "single_share_cases_csv": str(config.single_share_cases_path),
            "bulk_audit_dir": str(config.audit_dir),
            "markdown": "docs/strategy-v1-risk-structure-audit.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "risk_rows": len(risk_rows),
            "storage_size_bytes": audit_output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        risk_hash_unchanged
        and risk_config_hash_unchanged
        and all(report["regression"].values())
        and not prohibited_fields
        and not final_ready_violations
        and not capital_violations
        and not preview_violations
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    if not all(report["regression"].values()):
        raise RuntimeError("Baseline mutation detected during risk-structure audit.")
    return report


@dataclass(frozen=True, slots=True)
class ScenarioContext:
    risk_rows: Sequence[dict[str, Any]]
    entry_lookup: dict[tuple[str, str], dict[str, str]]
    setup_lookup: dict[tuple[str, str], dict[str, str]]
    feature_lookup: dict[tuple[str, str], dict[str, str]]
    regime_lookup: dict[str, dict[str, str]]
    history: dict[str, Sequence[Any]]
    history_index: dict[tuple[str, str], int]
    candidate_detail_rows: Sequence[dict[str, Any]]


def reconstruct_stop_candidate_inventory(
    *,
    risk_rows: Sequence[dict[str, Any]],
    entry_lookup: dict[tuple[str, str], dict[str, str]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
    feature_lookup: dict[tuple[str, str], dict[str, str]],
    history: dict[str, Sequence[Any]],
    history_index: dict[tuple[str, str], int],
    config: RiskStructureConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    for risk_row in risk_rows:
        key = (risk_row["trading_date"], canonical_symbol(risk_row["symbol"]))
        symbol = key[1]
        setup_row = setup_lookup.get(key, {})
        feature_row = feature_lookup.get(key, {})
        entry_row = entry_lookup.get(key, risk_row)
        bars = history.get(symbol, ())
        bar_index = history_index.get(key)
        assumed_entry = parse_decimal(risk_row.get("assumed_entry_price"))
        atr_14 = parse_decimal(risk_row.get("atr_14"))
        if assumed_entry is None or atr_14 is None or bar_index is None:
            continue
        candidates = stop_candidates(
            entry_row=entry_row,
            setup_row=setup_row,
            feature_row=feature_row,
            bars=bars,
            bar_index=bar_index,
            config=config,
        )
        candidate_distances: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_row = candidate_stop_detail(
                risk_row=risk_row,
                setup_row=setup_row,
                candidate=candidate,
                assumed_entry=assumed_entry,
                atr_14=atr_14,
                config=config,
            )
            detail_rows.append(candidate_row)
            if truthy(candidate_row["eligible"]):
                candidate_distances.append(candidate_row)
        valid_candidates = [row for row in candidate_distances if row["candidate_stop_quality"] in {"ACCEPTABLE", "GOOD"}]
        selected_basis = str(risk_row.get("invalidation_basis", ""))
        selected = next((row for row in candidate_distances if row["candidate_basis"] == selected_basis), None)
        selected_rank = ""
        selected_position = ""
        if selected is not None and candidate_distances:
            ordered = sorted(candidate_distances, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]))
            selected_rank = 1 + next(index for index, row in enumerate(ordered) if row["candidate_basis"] == selected_basis)
            if selected_rank == 1:
                selected_position = "TIGHTEST"
            elif selected_rank == len(ordered):
                selected_position = "WIDEST"
            else:
                selected_position = "MIDDLE"
        tightest = min(candidate_distances, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]), default={})
        widest = max(candidate_distances, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]), default={})
        alternatives = [
            parse_decimal(row["candidate_stop_distance_pct"])
            for row in candidate_distances
            if row["candidate_basis"] != selected_basis
        ]
        selection_rows.append(
            {
                "trading_date": key[0],
                "symbol": symbol,
                "setup_type": setup_type_label(setup_row or risk_row),
                "selected_basis": selected_basis,
                "candidate_count": len(candidate_distances),
                "valid_candidate_count": len(valid_candidates),
                "selected_rank_by_tightness": selected_rank,
                "selected_position": selected_position,
                "tightest_basis": tightest.get("candidate_basis", ""),
                "widest_basis": widest.get("candidate_basis", ""),
                "selected_stop_distance_pct": risk_row.get("stop_distance_pct", ""),
                "tightest_stop_distance_pct": tightest.get("candidate_stop_distance_pct", ""),
                "widest_stop_distance_pct": widest.get("candidate_stop_distance_pct", ""),
                "median_alternative_stop_distance_pct": median_decimal(alternatives),
            }
        )
    return detail_rows, selection_rows


def candidate_stop_detail(
    *,
    risk_row: dict[str, Any],
    setup_row: dict[str, Any],
    candidate: StopCandidate,
    assumed_entry: Decimal,
    atr_14: Decimal,
    config: RiskStructureConfig,
) -> dict[str, Any]:
    eligible = candidate.level > 0 and candidate.level < assumed_entry
    stop_price: Decimal | None = None
    distance_pct: Decimal | None = None
    distance_atr: Decimal | None = None
    band = "INVALID"
    quality = "INVALID"
    if eligible:
        stop_price = candidate.level - (atr_14 * config.stop.atr_buffer_multiple)
        eligible = stop_price > 0 and stop_price < assumed_entry
    if eligible and stop_price is not None:
        distance = assumed_entry - stop_price
        distance_pct = distance / assumed_entry * Decimal("100")
        distance_atr = distance / atr_14
        band = stop_distance_band(distance_pct=distance_pct, distance_atr=distance_atr, config=config)
        quality = stop_quality(basis=candidate.basis, band=band, config=config)
    return {
        "trading_date": risk_row["trading_date"],
        "symbol": canonical_symbol(risk_row["symbol"]),
        "setup_type": setup_type_label(setup_row or risk_row),
        "selected_basis": risk_row.get("invalidation_basis", ""),
        "candidate_basis": candidate.basis,
        "level": candidate.level,
        "eligible": eligible,
        "candidate_stop_price": stop_price,
        "candidate_stop_distance_pct": distance_pct,
        "candidate_stop_distance_atr": distance_atr,
        "candidate_stop_band": band,
        "candidate_stop_quality": quality,
        "selected": candidate.basis == risk_row.get("invalidation_basis", ""),
    }


def stop_candidate_availability(candidate_rows: Sequence[dict[str, Any]], risk_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(risk_rows)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        by_key[(row["trading_date"], row["symbol"])].append(row)
    all_bases = (
        "BREAKOUT_STRUCTURE",
        "CONSOLIDATION_LOW",
        "DAILY_RECLAIM_LOW",
        "RECENT_SWING_LOW_3",
        "RECENT_SWING_LOW_5",
        "RECENT_SWING_LOW_10",
        "CANDLE_LOW",
        "SMA20_SUPPORT",
        "UNAVAILABLE",
    )
    summary_rows = []
    for basis in all_bases:
        basis_rows = [row for row in candidate_rows if row["candidate_basis"] == basis]
        available_rows = len({(row["trading_date"], row["symbol"]) for row in basis_rows})
        eligible_rows = len({(row["trading_date"], row["symbol"]) for row in basis_rows if truthy(row["eligible"])})
        valid_rows = len({(row["trading_date"], row["symbol"]) for row in basis_rows if row["candidate_stop_quality"] in {"ACCEPTABLE", "GOOD"}})
        selected_rows = sum(1 for risk_row in risk_rows if risk_row.get("invalidation_basis") == basis)
        summary_rows.append(
            {
                "section": "candidate_availability",
                "basis": basis,
                "rows": available_rows,
                "pct": pct(available_rows, total),
                "available_rows": available_rows,
                "eligible_rows": eligible_rows,
                "valid_rows": valid_rows,
                "selected_rows": selected_rows,
                "selected_when_available_pct": pct(selected_rows, available_rows),
                "median_candidate_stop_distance_pct": median_decimal(parse_decimal(row.get("candidate_stop_distance_pct")) for row in basis_rows),
                "median_candidate_stop_distance_atr": median_decimal(parse_decimal(row.get("candidate_stop_distance_atr")) for row in basis_rows),
            }
        )
    five_available = sum(1 for rows in by_key.values() if any(row["candidate_basis"] == "RECENT_SWING_LOW_5" and truthy(row["eligible"]) for row in rows))
    setup_specific_available = sum(1 for rows in by_key.values() if any(row["candidate_basis"] in {"BREAKOUT_STRUCTURE", "CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW"} and truthy(row["eligible"]) for row in rows))
    multi_flag_momentum = sum(
        1
        for row in risk_rows
        if "MOMENTUM_CONTINUATION" in split_codes(row.get("setup_type_flags", ""))
        and any(flag in split_codes(row.get("setup_type_flags", "")) for flag in {"BREAKOUT_20D", "CONSOLIDATION_BREAKOUT"})
    )
    return {
        "rows": summary_rows,
        "five_day_swing_low_eligible_rows": five_available,
        "setup_specific_eligible_rows": setup_specific_available,
        "multi_flag_momentum_rows": multi_flag_momentum,
        "why_recent_swing_low_5_wins": (
            "RECENT_SWING_LOW_5 is generated for nearly every row because causal 5-session lows are almost always available. "
            "Rows carrying MOMENTUM_CONTINUATION enter that priority branch first, and that branch checks RECENT_SWING_LOW_5 "
            "before consolidation, reclaim, or breakout references. The selector stops at the first eligible basis."
        ),
    }


def multiple_stop_availability(selection_rows: Sequence[dict[str, Any]], candidate_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(selection_rows)
    count_distribution = Counter()
    valid_distribution = Counter()
    winner_by_multi = Counter()
    all_setup_specific_unavailable = 0
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        by_key[(row["trading_date"], row["symbol"])].append(row)
    for row in selection_rows:
        count = int(row["candidate_count"] or 0)
        valid_count = int(row["valid_candidate_count"] or 0)
        count_distribution[count_label(count)] += 1
        valid_distribution[count_label(valid_count)] += 1
        if count > 1:
            winner_by_multi[row["selected_basis"]] += 1
        candidates = by_key.get((row["trading_date"], row["symbol"]), [])
        if not any(item["candidate_basis"] in {"BREAKOUT_STRUCTURE", "CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "SMA20_SUPPORT"} and truthy(item["eligible"]) for item in candidates):
            all_setup_specific_unavailable += 1
    return {
        "candidate_count_distribution": distribution(count_distribution, total),
        "valid_candidate_count_distribution": distribution(valid_distribution, total),
        "multiple_candidate_winners": distribution(winner_by_multi, sum(winner_by_multi.values())),
        "all_setup_specific_structures_unavailable": all_setup_specific_unavailable,
        "all_setup_specific_structures_unavailable_pct": pct(all_setup_specific_unavailable, total),
    }


def selected_vs_alternative(selection_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    multi = [row for row in selection_rows if int(row["candidate_count"] or 0) > 1 and row["selected_position"]]
    return {
        "rows_with_multiple_candidates": len(multi),
        "selected_position_distribution": distribution(Counter(row["selected_position"] for row in multi), len(multi)),
        "median_selected_stop_distance_pct": median_decimal(parse_decimal(row.get("selected_stop_distance_pct")) for row in multi),
        "median_tightest_stop_distance_pct": median_decimal(parse_decimal(row.get("tightest_stop_distance_pct")) for row in multi),
        "median_widest_stop_distance_pct": median_decimal(parse_decimal(row.get("widest_stop_distance_pct")) for row in multi),
        "median_alternative_stop_distance_pct": median_decimal(parse_decimal(row.get("median_alternative_stop_distance_pct")) for row in multi),
    }


def swing_low_comparison(candidate_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in candidate_rows:
        by_key[(row["trading_date"], row["symbol"])][row["candidate_basis"]] = row
    rows = [
        values
        for values in by_key.values()
        if {"RECENT_SWING_LOW_3", "RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10"} <= set(values)
    ]
    distances_3 = [parse_decimal(row["RECENT_SWING_LOW_3"].get("candidate_stop_distance_pct")) for row in rows]
    distances_5 = [parse_decimal(row["RECENT_SWING_LOW_5"].get("candidate_stop_distance_pct")) for row in rows]
    distances_10 = [parse_decimal(row["RECENT_SWING_LOW_10"].get("candidate_stop_distance_pct")) for row in rows]
    identical = sum(1 for row in rows if row["RECENT_SWING_LOW_3"]["level"] == row["RECENT_SWING_LOW_5"]["level"] == row["RECENT_SWING_LOW_10"]["level"])
    equal_5_3 = sum(1 for row in rows if row["RECENT_SWING_LOW_5"]["level"] == row["RECENT_SWING_LOW_3"]["level"])
    equal_5_10 = sum(1 for row in rows if row["RECENT_SWING_LOW_5"]["level"] == row["RECENT_SWING_LOW_10"]["level"])
    return {
        "rows_with_all_three": len(rows),
        "median_3d_stop_distance_pct": median_decimal(distances_3),
        "median_5d_stop_distance_pct": median_decimal(distances_5),
        "median_10d_stop_distance_pct": median_decimal(distances_10),
        "all_three_identical_count": identical,
        "all_three_identical_pct": pct(identical, len(rows)),
        "five_equals_three_count": equal_5_3,
        "five_equals_three_pct": pct(equal_5_3, len(rows)),
        "five_equals_ten_count": equal_5_10,
        "five_equals_ten_pct": pct(equal_5_10, len(rows)),
    }


def stop_basis_audit(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        stop_basis_metric_row("selected_stop_basis", basis, basis, group, len(rows))
        for basis, group in sorted(group_rows(rows, "invalidation_basis").items())
    ]


def stop_basis_by_setup_type(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for setup_type in ("BREAKOUT_20D", "CONSOLIDATION_BREAKOUT", "MOMENTUM_CONTINUATION", "DAILY_RECLAIM", "OTHER"):
        group = setup_type_rows(rows, setup_type)
        for basis, basis_group in sorted(group_rows(group, "invalidation_basis").items()):
            output.append(stop_basis_metric_row("basis_by_setup_type", setup_type, basis, basis_group, len(group)))
    return output


def stop_quality_audit(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for quality, group in sorted(group_rows(rows, "stop_quality").items()):
        for basis, basis_group in sorted(group_rows(group, "invalidation_basis").items()):
            output.append(stop_basis_metric_row("stop_quality", quality, basis, basis_group, len(group)))
    return output


def stop_distance_bucket_audit(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[stop_distance_pct_bucket(parse_decimal(row.get("stop_distance_pct")))].append(row)
    return [stop_basis_metric_row("stop_distance_pct_bucket", bucket, "ALL", group, len(rows)) for bucket, group in sorted(grouped.items())]


def stop_distance_atr_bucket_audit(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[stop_distance_atr_bucket(parse_decimal(row.get("stop_distance_atr_multiple")))].append(row)
    return [stop_basis_metric_row("stop_distance_atr_bucket", bucket, "ALL", group, len(rows)) for bucket, group in sorted(grouped.items())]


def stop_band_audit(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        stop_basis_metric_row("stop_distance_band", band, "ALL", group, len(rows))
        for band, group in sorted(group_rows(rows, "stop_distance_band").items())
    ]


def stop_basis_metric_row(section: str, group_name: str, basis: str, group: Sequence[dict[str, Any]], total: int) -> dict[str, Any]:
    ready = sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING")
    return {
        "section": section,
        "group_name": group_name,
        "basis": basis,
        "rows": len(group),
        "pct": pct(len(group), total),
        "valid_stop_rate_pct": pct(sum(1 for row in group if truthy(row.get("stop_valid"))), len(group)),
        "median_stop_distance_pct": median_decimal(parse_decimal(row.get("stop_distance_pct")) for row in group),
        "median_stop_distance_atr": median_decimal(parse_decimal(row.get("stop_distance_atr_multiple")) for row in group),
        "median_reward_risk": median_decimal(parse_decimal(row.get("reward_risk_ratio")) for row in group),
        "ready_for_final_scoring_rate_pct": pct(ready, len(group)),
    }


def target_semantics_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = len(rows)
    structural_available = [row for row in rows if row.get("structural_target_status") == "AVAILABLE"]
    structural_selected = [row for row in rows if str(row.get("selected_target_basis", "")).startswith("PRIOR_")]
    fallback_selected = [row for row in rows if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"]
    violations = [
        row for row in rows
        if row.get("structural_target_status") == "AVAILABLE"
        and row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"
    ]
    structural_rr_rows = [
        row | {"structural_reward_risk": structural_reward_risk(row)}
        for row in structural_available
    ]
    below_min = [
        row for row in structural_rr_rows
        if parse_decimal(row.get("structural_reward_risk")) is not None
        and parse_decimal(row.get("structural_reward_risk")) < Decimal("1.50")
    ]
    below_min_not_rejected = [
        row for row in below_min
        if row.get("risk_mode") == "FULL_EVALUATION"
        if row.get("risk_readiness") != "RR_BELOW_MINIMUM"
        and row.get("reward_risk_status") != "BELOW_MINIMUM"
    ]
    rows_out = [
        target_metric_row("overall", "ALL", "STRUCTURAL_AVAILABLE", structural_available, total),
        target_metric_row("overall", "ALL", "STRUCTURAL_UNAVAILABLE", [row for row in rows if row.get("structural_target_status") != "AVAILABLE"], total),
        target_metric_row("overall", "ALL", "STRUCTURAL_SELECTED", structural_selected, total),
        target_metric_row("overall", "ALL", "FALLBACK_2R_SELECTED", fallback_selected, total),
        target_metric_row("overall", "ALL", "FALLBACK_WITH_STRUCTURAL_AVAILABLE_VIOLATION", violations, total),
    ]
    for setup_type in ("BREAKOUT_20D", "CONSOLIDATION_BREAKOUT", "MOMENTUM_CONTINUATION", "DAILY_RECLAIM", "OTHER"):
        group = setup_type_rows(rows, setup_type)
        rows_out.append(target_metric_row("by_setup_type", setup_type, "STRUCTURAL_AVAILABLE", [row for row in group if row.get("structural_target_status") == "AVAILABLE"], len(group)))
        rows_out.append(target_metric_row("by_setup_type", setup_type, "FALLBACK_2R_SELECTED", [row for row in group if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"], len(group)))
    for regime, group in sorted(group_rows(rows, "regime_state").items()):
        rows_out.append(target_metric_row("by_regime", regime, "STRUCTURAL_AVAILABLE", [row for row in group if row.get("structural_target_status") == "AVAILABLE"], len(group)))
        rows_out.append(target_metric_row("by_regime", regime, "FALLBACK_2R_SELECTED", [row for row in group if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"], len(group)))
    for basis, group in sorted(group_rows(rows, "invalidation_basis").items()):
        rows_out.append(target_metric_row("by_stop_basis", basis, "STRUCTURAL_AVAILABLE", [row for row in group if row.get("structural_target_status") == "AVAILABLE"], len(group)))
        rows_out.append(target_metric_row("by_stop_basis", basis, "FALLBACK_2R_SELECTED", [row for row in group if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"], len(group)))
    rr_bucket_counter = Counter(structural_rr_bucket(parse_decimal(row.get("structural_reward_risk"))) for row in structural_rr_rows)
    summary = {
        "structural_target_available_count": len(structural_available),
        "structural_target_available_pct": pct(len(structural_available), total),
        "structural_target_unavailable_count": total - len(structural_available),
        "selected_structural_target_count": len(structural_selected),
        "fallback_2r_count": len(fallback_selected),
        "fallback_semantic_violations": len(violations),
        "artificial_2r_replacements": len(violations),
        "structural_target_below_minimum_count": len(below_min),
        "structural_target_below_minimum_not_rejected": len(below_min_not_rejected),
        "structural_reward_risk_distribution": distribution(rr_bucket_counter, len(structural_rr_rows)),
        "median_structural_target_distance_pct": median_decimal(structural_target_distance_pct(row) for row in structural_available),
        "target_selection_semantics": (
            "build_target_plan selects structural_target when structural_target() returns a valid 52w or 20d resistance above the minimum distance. "
            "Fallback 2R is used only in the else branch when structural_price is None."
        ),
    }
    return rows_out, summary


def target_metric_row(section: str, group_name: str, basis_or_status: str, rows: Sequence[dict[str, Any]], denominator: int) -> dict[str, Any]:
    return {
        "section": section,
        "group_name": group_name,
        "basis_or_status": basis_or_status,
        "rows": len(rows),
        "pct": pct(len(rows), denominator),
        "structural_available_rows": sum(1 for row in rows if row.get("structural_target_status") == "AVAILABLE"),
        "structural_selected_rows": sum(1 for row in rows if str(row.get("selected_target_basis", "")).startswith("PRIOR_")),
        "fallback_selected_rows": sum(1 for row in rows if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"),
        "violations": sum(1 for row in rows if row.get("structural_target_status") == "AVAILABLE" and row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"),
        "median_structural_reward_risk": median_decimal(structural_reward_risk(row) for row in rows if row.get("structural_target_status") == "AVAILABLE"),
    }


def rr_failure_cause_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures = [
        row for row in rows
        if parse_decimal(row.get("reward_risk_ratio")) is not None
        and parse_decimal(row.get("reward_risk_ratio")) < Decimal("1.50")
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in failures:
        grouped[rr_failure_cause(row)].append(row)
    report_rows = [
        {
            "cause": cause,
            "rows": len(group),
            "pct": pct(len(group), len(failures)),
            "median_stop_distance_pct": median_decimal(parse_decimal(row.get("stop_distance_pct")) for row in group),
            "median_structural_reward_risk": median_decimal(structural_reward_risk(row) for row in group),
        }
        for cause, group in sorted(grouped.items())
    ]
    return report_rows, {
        "rr_below_minimum_rows": len(failures),
        "primary_causes": distribution(Counter(rr_failure_cause(row) for row in failures), len(failures)),
    }


def rr_failure_cause(row: dict[str, Any]) -> str:
    wide_stop = row.get("stop_distance_band") in {"WIDE", "TOO_WIDE"} or decimal_or_zero(row.get("stop_distance_pct")) >= Decimal("8")
    structural_rr = structural_reward_risk(row)
    near_target = structural_rr is not None and structural_rr < Decimal("1.50")
    invalid_target = not row.get("selected_target_price") or decimal_or_zero(row.get("selected_target_price")) <= decimal_or_zero(row.get("assumed_entry_price"))
    if wide_stop and near_target:
        return "BOTH_WIDE_STOP_AND_NEAR_TARGET"
    if wide_stop:
        return "WIDE_STOP"
    if near_target:
        return "NEAR_STRUCTURAL_RESISTANCE"
    if invalid_target:
        return "INVALID_TARGET"
    return "OTHER"


def capital_audit(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total = len(rows)
    output = []
    driver_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        driver_groups[quantity_driver(row)].append(row)
    for driver, group in sorted(driver_groups.items()):
        output.append(capital_metric_row("quantity_driver", driver, group, total))

    utilization_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        utilization_groups[capital_utilization_bucket(parse_decimal(row.get("capital_utilization_pct")))].append(row)
    for bucket, group in sorted(utilization_groups.items()):
        output.append(capital_metric_row("capital_utilization_bucket", bucket, group, total))

    price_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        price_groups[price_band(parse_decimal(row.get("assumed_entry_price")))].append(row)
    for bucket, group in sorted(price_groups.items()):
        output.append(capital_metric_row("price_band", bucket, group, total))

    ready_rows = [row for row in rows if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"]
    notionals = [parse_decimal(row.get("position_notional")) for row in ready_rows]
    concurrency = {
        "median_position_notional": median_decimal(notionals),
        "p75_position_notional": decimal_quantile(clean_decimals(notionals), Decimal("0.75")),
        "p90_position_notional": decimal_quantile(clean_decimals(notionals), Decimal("0.90")),
        "pct_position_notional_gt_25k": pct(sum(1 for value in clean_decimals(notionals) if value > Decimal("25000")), len(ready_rows)),
        "pct_position_notional_gt_33_3k": pct(sum(1 for value in clean_decimals(notionals) if value > Decimal("33333.33")), len(ready_rows)),
        "pct_position_notional_gt_50k": pct(sum(1 for value in clean_decimals(notionals) if value > Decimal("50000")), len(ready_rows)),
    }
    summary = {
        "quantity_driver_distribution": distribution(Counter(quantity_driver(row) for row in rows), total),
        "capital_utilization_distribution": distribution(Counter(capital_utilization_bucket(parse_decimal(row.get("capital_utilization_pct"))) for row in rows), total),
        "median_capital_utilization_pct": median_decimal(parse_decimal(row.get("capital_utilization_pct")) for row in rows),
        "low_capital_utilization_causes": low_capital_utilization_causes(rows),
        "position_concurrency_feasibility": concurrency,
        "planned_risk_cap_violations": sum(1 for row in rows if decimal_or_zero(row.get("planned_risk_pct")) > Decimal("1.00")),
        "single_share_count": sum(1 for row in rows if "SINGLE_SHARE_ONLY" in split_codes(row.get("warning_flags", ""))),
        "risk_too_large_count": sum(1 for row in rows if "RISK_TOO_LARGE_FOR_CAPITAL" in split_codes(row.get("rejection_reasons", ""))),
        "affordability_failures": sum(1 for row in rows if "AFFORDABILITY_FAIL" in split_codes(row.get("rejection_reasons", ""))),
    }
    return output, summary


def capital_metric_row(section: str, bucket: str, group: Sequence[dict[str, Any]], total: int) -> dict[str, Any]:
    ready = sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING")
    return {
        "section": section,
        "bucket_or_driver": bucket,
        "rows": len(group),
        "pct": pct(len(group), total),
        "median_price": median_decimal(parse_decimal(row.get("assumed_entry_price")) for row in group),
        "median_stop_distance_pct": median_decimal(parse_decimal(row.get("stop_distance_pct")) for row in group),
        "median_quantity": median_decimal(parse_decimal(row.get("structured_quantity")) for row in group),
        "median_capital_utilization_pct": median_decimal(parse_decimal(row.get("capital_utilization_pct")) for row in group),
        "ready_rate_pct": pct(ready, len(group)),
    }


def scenario_audit(config: RiskStructureConfig, context: ScenarioContext) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    baseline_ready = ready_set(context.risk_rows)
    rows: list[dict[str, Any]] = []
    membership: list[dict[str, Any]] = []
    scenario_outputs: dict[str, list[dict[str, Any]]] = {"BASELINE": list(context.risk_rows)}

    config_scenarios = {
        "ATR_BUFFER_0_10": replace(config, stop=replace(config.stop, atr_buffer_multiple=Decimal("0.10"))),
        "ATR_BUFFER_0_25": replace(config, stop=replace(config.stop, atr_buffer_multiple=Decimal("0.25"))),
        "ATR_BUFFER_0_30": replace(config, stop=replace(config.stop, atr_buffer_multiple=Decimal("0.30"))),
        "ENTRY_BUFFER_0_00": replace(config, entry=replace(config.entry, long_entry_buffer_pct=Decimal("0.00"))),
        "ENTRY_BUFFER_0_20": replace(config, entry=replace(config.entry, long_entry_buffer_pct=Decimal("0.20"))),
        "ENTRY_BUFFER_0_30": replace(config, entry=replace(config.entry, long_entry_buffer_pct=Decimal("0.30"))),
        "STOP_TIGHTER": replace(
            config,
            stop=replace(
                config.stop,
                minimum_stop_distance_pct=Decimal("0.60"),
                minimum_stop_distance_atr=Decimal("0.50"),
                wide_stop_distance_pct=Decimal("7.00"),
                maximum_stop_distance_pct=Decimal("12.00"),
            ),
        ),
        "STOP_LOOSER": replace(
            config,
            stop=replace(
                config.stop,
                minimum_stop_distance_pct=Decimal("0.25"),
                minimum_stop_distance_atr=Decimal("0.25"),
                wide_stop_distance_pct=Decimal("10.00"),
                maximum_stop_distance_pct=Decimal("16.00"),
            ),
        ),
    }
    for name, scenario_config in config_scenarios.items():
        scenario_outputs[name] = evaluate_scenario_rows(scenario_config, context)

    for name in ("BASELINE_PRIORITY", "SETUP_SPECIFIC_FIRST", "TIGHTEST_VALID_STOP", "WIDEST_VALID_STOP"):
        scenario_outputs[name] = counterfactual_stop_rows(config, context, name)

    scenario_outputs["STRUCTURAL_STRICT_BASELINE"] = list(context.risk_rows)
    scenario_outputs["NO_STRUCTURAL_TARGET_FORCE_2R"] = target_counterfactual_rows(config, context, "NO_STRUCTURAL_TARGET_FORCE_2R")
    scenario_outputs["ALWAYS_2R_REFERENCE"] = target_counterfactual_rows(config, context, "ALWAYS_2R_REFERENCE")

    for name, scenario_rows in scenario_outputs.items():
        group = scenario_group(name)
        rows.append(scenario_metric_row(group, name, scenario_rows, baseline_ready, notes_for_scenario(name)))
        for row in scenario_rows:
            if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING":
                membership.append({"scenario": name, "trading_date": row["trading_date"], "symbol": row["symbol"], "risk_readiness": row["risk_readiness"]})
    summary = {
        "scenarios": {row["scenario"]: row for row in rows},
        "baseline_ready_count": len(baseline_ready),
        "always_2r_inflation_count": rows_by_scenario(rows, "ALWAYS_2R_REFERENCE")["final_ready"] - rows_by_scenario(rows, "STRUCTURAL_STRICT_BASELINE")["final_ready"],
        "no_structural_target_force_2r_matches_baseline": rows_by_scenario(rows, "NO_STRUCTURAL_TARGET_FORCE_2R")["jaccard_vs_baseline"] == "1.0000",
    }
    return rows, summary, membership


def evaluate_scenario_rows(config: RiskStructureConfig, context: ScenarioContext) -> list[dict[str, Any]]:
    return evaluate_risk_rows(
        entry_rows=[context.entry_lookup[(row["trading_date"], row["symbol"])] for row in context.risk_rows],
        setup_lookup=context.setup_lookup,
        feature_lookup=context.feature_lookup,
        regime_lookup=context.regime_lookup,
        history=context.history,
        history_index=context.history_index,
        config=config,
    )


def counterfactual_stop_rows(config: RiskStructureConfig, context: ScenarioContext, name: str) -> list[dict[str, Any]]:
    if name == "BASELINE_PRIORITY":
        return list(context.risk_rows)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in context.candidate_detail_rows:
        if row["candidate_stop_quality"] in {"ACCEPTABLE", "GOOD"}:
            by_key[(row["trading_date"], row["symbol"])].append(row)
    output = []
    for risk_row in context.risk_rows:
        key = (risk_row["trading_date"], risk_row["symbol"])
        setup_row = context.setup_lookup.get(key, {})
        feature_row = context.feature_lookup.get(key, {})
        candidates = by_key.get(key, [])
        selected = select_counterfactual_candidate(name=name, candidates=candidates, setup_row=setup_row)
        output.append(row_with_candidate_stop(risk_row, selected, config, setup_row=setup_row, feature_row=feature_row))
    return output


def select_counterfactual_candidate(name: str, candidates: Sequence[dict[str, Any]], setup_row: dict[str, Any]) -> dict[str, Any] | None:
    if not candidates:
        return None
    if name == "TIGHTEST_VALID_STOP":
        return min(candidates, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]))
    if name == "WIDEST_VALID_STOP":
        return max(candidates, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]))
    if name == "SETUP_SPECIFIC_FIRST":
        by_basis = {row["candidate_basis"]: row for row in candidates}
        for basis in setup_specific_first_priority(setup_row):
            if basis in by_basis:
                return by_basis[basis]
        return min(candidates, key=lambda row: decimal_or_zero(row["candidate_stop_distance_pct"]))
    return None


def setup_specific_first_priority(setup_row: dict[str, Any]) -> tuple[str, ...]:
    flags = split_codes(setup_row.get("setup_type_flags", ""))
    if "CONSOLIDATION_BREAKOUT" in flags:
        return ("CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE", "RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3", "CANDLE_LOW", "SMA20_SUPPORT")
    if truthy(setup_row.get("daily_level_reclaim")):
        return ("DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE", "RECENT_SWING_LOW_5", "CONSOLIDATION_LOW", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3", "CANDLE_LOW", "SMA20_SUPPORT")
    if "BREAKOUT_20D" in flags:
        return ("BREAKOUT_STRUCTURE", "DAILY_RECLAIM_LOW", "CONSOLIDATION_LOW", "RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3", "CANDLE_LOW", "SMA20_SUPPORT")
    if "MOMENTUM_CONTINUATION" in flags:
        return ("RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3", "SMA20_SUPPORT", "CONSOLIDATION_LOW", "CANDLE_LOW", "BREAKOUT_STRUCTURE")
    return ("RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "CONSOLIDATION_LOW", "BREAKOUT_STRUCTURE", "CANDLE_LOW", "SMA20_SUPPORT")


def row_with_candidate_stop(
    risk_row: dict[str, Any],
    selected: dict[str, Any] | None,
    config: RiskStructureConfig,
    *,
    setup_row: dict[str, Any],
    feature_row: dict[str, Any],
) -> dict[str, Any]:
    row = dict(risk_row)
    if selected is None:
        row.update(
            {
                "invalidation_basis": "UNAVAILABLE",
                "technical_invalidation_level": "",
                "stop_price": "",
                "stop_distance_abs": "",
                "stop_distance_pct": "",
                "stop_distance_atr_multiple": "",
                "stop_distance_band": "INVALID",
                "stop_quality": "INVALID",
                "stop_valid": False,
                "risk_readiness": "INVALID_STRUCTURE" if row.get("risk_mode") == "FULL_EVALUATION" else "NOT_EVALUATED",
            }
        )
        return row
    assumed_entry = decimal_or_zero(row.get("assumed_entry_price"))
    stop_price = decimal_or_zero(selected.get("candidate_stop_price"))
    risk_per_share = assumed_entry - stop_price
    target = build_target_plan(setup_row=setup_row, feature_row=feature_row, assumed_entry_price=assumed_entry, risk_per_share=risk_per_share, config=config)
    rr = calculate_reward_risk(assumed_entry_price=assumed_entry, stop_price=stop_price, selected_target_price=target["selected_target_price"], config=config)
    sizing = calculate_position_size(assumed_entry_price=assumed_entry, risk_per_share=rr["risk_per_share"], config=config)
    structure_status, readiness = risk_status(
        risk_mode=row.get("risk_mode", ""),
        stop_valid=True,
        rr_valid=bool(rr["rr_valid"]),
        capital_valid=bool(sizing["capital_valid"]),
        missing_setup=False,
        missing_price=False,
    )
    row.update(
        {
            "technical_invalidation_level": selected["level"],
            "invalidation_basis": selected["candidate_basis"],
            "stop_price": stop_price,
            "stop_distance_abs": risk_per_share,
            "stop_distance_pct": selected["candidate_stop_distance_pct"],
            "stop_distance_atr_multiple": selected["candidate_stop_distance_atr"],
            "stop_distance_band": selected["candidate_stop_band"],
            "stop_quality": selected["candidate_stop_quality"],
            "stop_valid": True,
        }
        | target
        | rr
        | sizing
        | {"risk_structure_status": structure_status, "risk_readiness": readiness}
    )
    return row


def target_counterfactual_rows(config: RiskStructureConfig, context: ScenarioContext, name: str) -> list[dict[str, Any]]:
    output = []
    for risk_row in context.risk_rows:
        row = dict(risk_row)
        assumed_entry = parse_decimal(row.get("assumed_entry_price"))
        risk_per_share = parse_decimal(row.get("risk_per_share"))
        if assumed_entry is None or risk_per_share is None or risk_per_share <= 0:
            output.append(row)
            continue
        if name == "NO_STRUCTURAL_TARGET_FORCE_2R":
            target = build_target_plan(setup_row=context.setup_lookup.get((row["trading_date"], row["symbol"]), row), feature_row=context.feature_lookup.get((row["trading_date"], row["symbol"]), row), assumed_entry_price=assumed_entry, risk_per_share=risk_per_share, config=config)
        else:
            target = build_target_plan(setup_row={}, feature_row={}, assumed_entry_price=assumed_entry, risk_per_share=risk_per_share, config=config)
            target["selected_target_price"] = assumed_entry + risk_per_share * Decimal("2")
            target["selected_target_basis"] = "ALWAYS_2R_REFERENCE_INVALID_FOR_BASELINE_STRATEGY_RESEARCH_DIAGNOSTIC_ONLY"
            target["structural_target_status"] = "IGNORED_FOR_DIAGNOSTIC_ONLY"
        rr = calculate_reward_risk(assumed_entry_price=assumed_entry, stop_price=parse_decimal(row.get("stop_price")), selected_target_price=target["selected_target_price"], config=config)
        sizing = calculate_position_size(assumed_entry_price=assumed_entry, risk_per_share=rr["risk_per_share"], config=config)
        structure_status, readiness = risk_status(
            risk_mode=row.get("risk_mode", ""),
            stop_valid=truthy(row.get("stop_valid")),
            rr_valid=bool(rr["rr_valid"]),
            capital_valid=bool(sizing["capital_valid"]),
            missing_setup=False,
            missing_price=False,
        )
        row.update(target | rr | sizing | {"risk_structure_status": structure_status, "risk_readiness": readiness})
        output.append(row)
    return output


def scenario_metric_row(group: str, name: str, rows: Sequence[dict[str, Any]], baseline_ready: set[tuple[str, str]], notes: str) -> dict[str, Any]:
    scenario_ready = ready_set(rows)
    intersection = baseline_ready & scenario_ready
    union = baseline_ready | scenario_ready
    return {
        "scenario_group": group,
        "scenario": name,
        "valid_stop": sum(1 for row in rows if truthy(row.get("stop_valid"))),
        "median_stop_pct": median_decimal(parse_decimal(row.get("stop_distance_pct")) for row in rows),
        "median_stop_atr": median_decimal(parse_decimal(row.get("stop_distance_atr_multiple")) for row in rows),
        "structural_target_selected": sum(1 for row in rows if str(row.get("selected_target_basis", "")).startswith("PRIOR_")),
        "fallback_target_selected": sum(1 for row in rows if row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE"),
        "rr_gte_1_5": sum(1 for row in rows if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("1.50")),
        "rr_gte_2_0": sum(1 for row in rows if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("2.00")),
        "final_ready": len(scenario_ready),
        "median_quantity": median_decimal(parse_decimal(row.get("structured_quantity")) for row in rows),
        "median_capital_utilization_pct": median_decimal(parse_decimal(row.get("capital_utilization_pct")) for row in rows),
        "median_planned_risk": median_decimal(parse_decimal(row.get("planned_rupee_risk")) for row in rows),
        "baseline_retained": len(intersection),
        "baseline_removed": len(baseline_ready - scenario_ready),
        "introduced": len(scenario_ready - baseline_ready),
        "jaccard_vs_baseline": round_decimal(Decimal(len(intersection)) / Decimal(len(union)) if union else Decimal("1")),
        "notes": notes,
    }


def selected_basis_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return distribution(Counter(row.get("invalidation_basis", "UNAVAILABLE") for row in rows), len(rows))


def setup_section_summary(rows: Sequence[dict[str, Any]], setup_type: str) -> dict[str, Any]:
    group = setup_type_rows(rows, setup_type)
    return {
        "rows": len(group),
        "selected_stop_basis": selected_basis_distribution(group),
        "valid_stop_rate_pct": pct(sum(1 for row in group if truthy(row.get("stop_valid"))), len(group)),
        "median_stop_distance_pct": median_decimal(parse_decimal(row.get("stop_distance_pct")) for row in group),
        "median_stop_distance_atr": median_decimal(parse_decimal(row.get("stop_distance_atr_multiple")) for row in group),
        "structural_target_available_pct": pct(sum(1 for row in group if row.get("structural_target_status") == "AVAILABLE"), len(group)),
        "median_reward_risk": median_decimal(parse_decimal(row.get("reward_risk_ratio")) for row in group),
        "rr_gte_1_5_pct": pct(sum(1 for row in group if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("1.50")), len(group)),
        "rr_gte_2_0_pct": pct(sum(1 for row in group if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("2.00")), len(group)),
        "ready_for_final_scoring": sum(1 for row in group if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"),
        "ready_for_final_scoring_pct": pct(sum(1 for row in group if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"), len(group)),
    }


def warning_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total_counter: Counter[str] = Counter()
    ready_counter: Counter[str] = Counter()
    rejected_counter: Counter[str] = Counter()
    for row in rows:
        for code in split_codes(row.get("warning_flags", "")):
            total_counter[code] += 1
            if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING":
                ready_counter[code] += 1
            elif row.get("risk_readiness") in {"INVALID_STRUCTURE", "RR_BELOW_MINIMUM", "CAPITAL_CONSTRAINED"}:
                rejected_counter[code] += 1
    return {
        "overall": distribution(total_counter, len(rows), limit=20),
        "final_ready": distribution(ready_counter, sum(ready_counter.values()), limit=20),
        "rejected": distribution(rejected_counter, sum(rejected_counter.values()), limit=20),
    }


def rejection_overlap(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rejected = [row for row in rows if row.get("risk_readiness") in {"INVALID_STRUCTURE", "RR_BELOW_MINIMUM", "CAPITAL_CONSTRAINED"}]
    size_counter: Counter[str] = Counter()
    combo_counter: Counter[str] = Counter()
    for row in rejected:
        reasons = sorted(split_codes(row.get("rejection_reasons", "")))
        size_counter[reason_size_label(len(reasons))] += 1
        combo_counter["+".join(reasons) if reasons else "NONE"] += 1
    return {
        "reason_count_distribution": distribution(size_counter, len(rejected)),
        "top_combinations": distribution(combo_counter, len(rejected), limit=20),
    }


def low_capital_utilization_causes(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    low_rows = [row for row in rows if decimal_or_zero(row.get("capital_utilization_pct")) < Decimal("10") and decimal_or_zero(row.get("structured_quantity")) > 0]
    counter: Counter[str] = Counter()
    for row in low_rows:
        if row.get("stop_distance_band") in {"WIDE", "TOO_WIDE"} or decimal_or_zero(row.get("stop_distance_pct")) >= Decimal("8"):
            counter["WIDE_STOP_RISK_LIMITED"] += 1
        elif decimal_or_zero(row.get("assumed_entry_price")) > Decimal("5000"):
            counter["EXPENSIVE_STOCK"] += 1
        elif decimal_or_zero(row.get("structured_quantity")) <= Decimal("3"):
            counter["LOW_QUANTITY"] += 1
        else:
            counter["OTHER"] += 1
    return distribution(counter, len(low_rows))


def final_ready_invariant_violations(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    violations = []
    for row in rows:
        if row.get("risk_readiness") != "READY_FOR_FINAL_SCORING":
            continue
        reasons = []
        if row.get("risk_mode") != "FULL_EVALUATION":
            reasons.append("NOT_FULL_EVALUATION")
        if row.get("stop_quality") not in {"ACCEPTABLE", "GOOD"}:
            reasons.append("STOP_NOT_VALID_GOOD")
        if decimal_or_zero(row.get("stop_price")) >= decimal_or_zero(row.get("assumed_entry_price")):
            reasons.append("STOP_NOT_BELOW_ENTRY")
        if decimal_or_zero(row.get("reward_risk_ratio")) < Decimal("1.50"):
            reasons.append("RR_BELOW_MINIMUM")
        if decimal_or_zero(row.get("structured_quantity")) < Decimal("1"):
            reasons.append("QUANTITY_LT_1")
        if decimal_or_zero(row.get("planned_risk_pct")) > Decimal("1.00"):
            reasons.append("PLANNED_RISK_GT_1")
        if row.get("rejection_reasons"):
            reasons.append("HAS_REJECTION_REASON")
        if row.get("final_strategy_score_status") != "NOT_IMPLEMENTED":
            reasons.append("FINAL_SCORE_PRESENT")
        if row.get("trade_signal_status") != "NOT_GENERATED":
            reasons.append("TRADE_SIGNAL_PRESENT")
        if reasons:
            violations.append({"trading_date": row["trading_date"], "symbol": row["symbol"], "reasons": reasons})
    return violations


def capital_risk_violations(rows: Sequence[dict[str, Any]], config: RiskStructureConfig) -> list[dict[str, Any]]:
    cap = config.capital.max_risk_per_trade_pct
    return [
        {"trading_date": row["trading_date"], "symbol": row["symbol"], "planned_risk_pct": row.get("planned_risk_pct")}
        for row in rows
        if row.get("risk_mode") == "FULL_EVALUATION" and decimal_or_zero(row.get("planned_risk_pct")) > cap
    ]


def conditional_preview_violations(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"trading_date": row["trading_date"], "symbol": row["symbol"], "risk_mode": row.get("risk_mode"), "risk_readiness": row.get("risk_readiness")}
        for row in rows
        if row.get("entry_readiness") == "CONDITIONALLY_READY"
        and (row.get("risk_mode") != "PREVIEW_ONLY" or row.get("risk_readiness") == "READY_FOR_FINAL_SCORING")
    ]


def audit_results(
    *,
    stop_candidate_summary: dict[str, Any],
    scenario_summary: dict[str, Any],
    target_summary: dict[str, Any],
    capital_summary: dict[str, Any],
    final_ready_violations: Sequence[dict[str, Any]],
    capital_violations: Sequence[dict[str, Any]],
) -> dict[str, str]:
    baseline = scenario_summary["scenarios"]["BASELINE"]
    setup_specific = scenario_summary["scenarios"]["SETUP_SPECIFIC_FIRST"]
    jaccard = parse_decimal(setup_specific["jaccard_vs_baseline"]) or Decimal("0")
    if final_ready_violations or target_summary["fallback_semantic_violations"]:
        structural = "HIGHLY_SENSITIVE"
    elif jaccard < Decimal("0.75") or abs(int(setup_specific["final_ready"]) - int(baseline["final_ready"])) > int(baseline["final_ready"]) * Decimal("0.20"):
        structural = "MODERATELY_SENSITIVE"
    else:
        structural = "STABLE"

    recent_5_selected = int(next((row["selected_rows"] for row in stop_candidate_summary["rows"] if row["basis"] == "RECENT_SWING_LOW_5"), 0))
    total_rows = sum(int(row["selected_rows"]) for row in stop_candidate_summary["rows"])
    recent_5_pct = Decimal(recent_5_selected) / Decimal(total_rows) * Decimal("100") if total_rows else Decimal("0")
    stop_semantics = "CONSISTENT_BUT_OVERCONCENTRATED" if recent_5_pct >= Decimal("90") else "CONSISTENT"
    if int(setup_specific["introduced"]) + int(setup_specific["baseline_removed"]) > 0:
        stop_semantics = "SETUP_SPECIFIC_STOPS_UNDERUSED"

    if target_summary["fallback_semantic_violations"]:
        target_semantics = "SEMANTIC_MISMATCH"
    elif int(scenario_summary["always_2r_inflation_count"]) > 0:
        target_semantics = "CONSISTENT_STRUCTURAL_FIRST"
    else:
        target_semantics = "CONSISTENT_BUT_FALLBACK_HEAVY"

    if capital_violations:
        capital = "RISK_LIMIT_VIOLATIONS"
    elif parse_decimal(capital_summary["median_capital_utilization_pct"]) and parse_decimal(capital_summary["median_capital_utilization_pct"]) < Decimal("20"):
        capital = "HEALTHY_BUT_LOW_UTILIZATION"
    else:
        capital = "HEALTHY"

    baseline_decision = (
        "B. remain provisional pending a specific semantic fix"
        if stop_semantics == "SETUP_SPECIFIC_STOPS_UNDERUSED"
        else "A. freeze unchanged"
    )
    return {
        "structural_stability": structural,
        "stop_semantics": stop_semantics,
        "target_semantics": target_semantics,
        "capital_risk": capital,
        "baseline_decision": baseline_decision,
        "recommended_next_action": (
            "Create a separate methodology-change command to decide whether multi-flag rows should prioritize setup-specific invalidation before momentum-continuation swing lows."
            if baseline_decision.startswith("B.")
            else "Freeze RISK_STRUCTURE_V1 and proceed to the next approved layer only after review."
        ),
    }


def risk_too_large_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if "RISK_TOO_LARGE_FOR_CAPITAL" not in split_codes(row.get("rejection_reasons", "")):
            continue
        output.append(
            {
                "trading_date": row["trading_date"],
                "symbol": row["symbol"],
                "entry": row.get("assumed_entry_price", ""),
                "stop": row.get("stop_price", ""),
                "risk_per_share": row.get("risk_per_share", ""),
                "assumed_entry_price": row.get("assumed_entry_price", ""),
                "quantity_by_risk": row.get("quantity_by_risk", ""),
                "quantity_by_cash": row.get("quantity_by_cash", ""),
                "rejection_reasons": row.get("rejection_reasons", ""),
            }
        )
    return output


def single_share_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if "SINGLE_SHARE_ONLY" not in split_codes(row.get("warning_flags", "")):
            continue
        output.append(
            {
                "trading_date": row["trading_date"],
                "symbol": row["symbol"],
                "assumed_entry_price": row.get("assumed_entry_price", ""),
                "risk_per_share": row.get("risk_per_share", ""),
                "planned_rupee_risk": row.get("planned_rupee_risk", ""),
                "reward_risk_ratio": row.get("reward_risk_ratio", ""),
                "risk_readiness": row.get("risk_readiness", ""),
                "warning_flags": row.get("warning_flags", ""),
            }
        )
    return output


def write_strategy_v1_risk_structure_audit_markdown(report: dict[str, Any], path: Path) -> None:
    decision = report["decision"]
    stop = report["stop_audit"]
    target = report["target_audit"]
    capital = report["capital_audit"]
    lines = [
        "# Strategy V1 Risk Structure Audit",
        "",
        "Current phase: Step 02.9 / Command 02 - RISK_STRUCTURE_V1 structural audit",
        "",
        "## Boundary",
        "",
        "- This is a structural audit only.",
        "- RISK_STRUCTURE_V1 was not modified.",
        "- No future returns, future highs/lows, stop-hit labels, target-hit labels, MFE/MAE, profitability optimization, final score, signal, paper trade, live order, leverage, or Supabase write is used.",
        "",
        "## Version",
        "",
        f"- Audit version: {report['audit_version']}",
        f"- Risk version/config hash: {report['risk']['risk_version']} / {report['risk']['risk_config_hash']}",
        "",
        "## Stop Semantics",
        "",
        f"- Baseline selected stop distribution: {report['stop_audit']['baseline_distribution']}",
        f"- Stop semantics result: {decision['stop_semantics']}",
        f"- Why 5d swing low dominates: {report['stop_implementation']['why_recent_swing_low_5_wins']}",
        f"- Multiple-stop availability: {stop['multiple_stop_availability']}",
        f"- Selected vs alternative: {stop['selected_vs_alternative']}",
        "",
        "## Target Semantics",
        "",
        f"- Target semantics result: {decision['target_semantics']}",
        f"- Structural available rows: {target['structural_target_available_count']}",
        f"- 2R fallback rows: {target['fallback_2r_count']}",
        f"- Fallback semantic violations: {target['fallback_semantic_violations']}",
        "",
        "## Capital Risk",
        "",
        f"- Capital risk result: {decision['capital_risk']}",
        f"- Planned-risk violations: {capital['planned_risk_cap_violations']}",
        f"- Quantity drivers: {capital['quantity_driver_distribution']}",
        f"- Concurrency feasibility: {capital['position_concurrency_feasibility']}",
        "",
        "## Decision",
        "",
        f"- Structural stability: {decision['structural_stability']}",
        f"- Baseline decision: {decision['baseline_decision']}",
        f"- Recommended next action: {decision['recommended_next_action']}",
        "",
        "## Regression",
        "",
        f"- DAILY_FEATURES_V1 unchanged: {report['regression']['daily_features_v1_unchanged']}",
        f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['regression']['momentum_candidates_v1_unchanged']}",
        f"- DAILY_SETUP_EVALUATION_V1 unchanged: {report['regression']['daily_setup_evaluation_v1_unchanged']}",
        f"- MARKET_REGIME_V1 unchanged: {report['regression']['market_regime_v1_unchanged']}",
        f"- ENTRY_EVALUATION_V1 unchanged: {report['regression']['entry_evaluation_v1_unchanged']}",
        f"- RISK_STRUCTURE_V1 unchanged: {report['regression']['risk_structure_v1_unchanged']}",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def load_risk_rows(path: Path) -> list[dict[str, str]]:
    with open_csv_maybe_gzip(path) as file:
        return list(csv.DictReader(file))


def enrich_risk_rows(
    rows: Sequence[dict[str, Any]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, Any]]:
    enriched = []
    for row in rows:
        key = (row["trading_date"], canonical_symbol(row["symbol"]))
        setup_row = setup_lookup.get(key, {})
        enriched.append(
            dict(row)
            | {
                "daily_level_reclaim": setup_row.get("daily_level_reclaim", ""),
                "breakout_state": setup_row.get("breakout_state", ""),
                "consolidation_quality": setup_row.get("consolidation_quality", ""),
                "consolidation_state": setup_row.get("consolidation_state", ""),
            }
        )
    return enriched


def upstream_hashes(config: RiskStructureAuditConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
        "entry": file_sha256(config.entry_dataset_path),
        "risk": file_sha256(config.risk_dataset_path),
    }


def observed_versions(rows: Sequence[dict[str, Any]], config: RiskStructureAuditConfig) -> dict[str, str]:
    return {
        "feature_version": observed_single_value(rows, "feature_version"),
        "candidate_version": observed_single_value(rows, "candidate_version"),
        "candidate_config_hash": observed_single_value(rows, "candidate_config_hash"),
        "setup_version": observed_single_value(rows, "setup_version"),
        "setup_config_hash": observed_single_value(rows, "setup_config_hash"),
        "regime_version": observed_single_value(rows, "regime_version"),
        "regime_config_hash": observed_single_value(rows, "regime_config_hash"),
        "entry_version": observed_single_value(rows, "entry_version"),
        "entry_config_hash": observed_single_value(rows, "entry_config_hash"),
        "risk_version": observed_single_value(rows, "risk_version"),
        "risk_config_hash": observed_single_value(rows, "risk_config_hash"),
        "audit_version": config.audit_version,
    }


def setup_type_rows(rows: Sequence[dict[str, Any]], setup_type: str) -> list[dict[str, Any]]:
    if setup_type == "OTHER":
        return [
            row for row in rows
            if not split_codes(row.get("setup_type_flags", "")) & {"BREAKOUT_20D", "CONSOLIDATION_BREAKOUT", "MOMENTUM_CONTINUATION"}
            and not truthy(row.get("daily_level_reclaim"))
        ]
    if setup_type == "DAILY_RECLAIM":
        return [row for row in rows if truthy(row.get("daily_level_reclaim")) or row.get("invalidation_basis") == "DAILY_RECLAIM_LOW"]
    return [row for row in rows if setup_type in split_codes(row.get("setup_type_flags", ""))]


def setup_type_label(row: dict[str, Any]) -> str:
    flags = split_codes(row.get("setup_type_flags", ""))
    labels = [flag for flag in ("BREAKOUT_20D", "CONSOLIDATION_BREAKOUT", "MOMENTUM_CONTINUATION") if flag in flags]
    if truthy(row.get("daily_level_reclaim")):
        labels.append("DAILY_RECLAIM")
    return ";".join(labels) if labels else "OTHER"


def structural_reward_risk(row: dict[str, Any]) -> Decimal | None:
    target = parse_decimal(row.get("structural_target_price"))
    entry = parse_decimal(row.get("assumed_entry_price"))
    risk = parse_decimal(row.get("risk_per_share"))
    if target is None or entry is None or risk is None or risk <= 0:
        return None
    return (target - entry) / risk


def structural_target_distance_pct(row: dict[str, Any]) -> Decimal | None:
    target = parse_decimal(row.get("structural_target_price"))
    entry = parse_decimal(row.get("assumed_entry_price"))
    if target is None or entry is None or entry <= 0:
        return None
    return (target - entry) / entry * Decimal("100")


def stop_distance_pct_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value < Decimal("1"):
        return "LT_1"
    if value < Decimal("2"):
        return "1_TO_2"
    if value < Decimal("3"):
        return "2_TO_3"
    if value < Decimal("5"):
        return "3_TO_5"
    if value < Decimal("7.5"):
        return "5_TO_7_5"
    if value < Decimal("10"):
        return "7_5_TO_10"
    if value <= Decimal("15"):
        return "10_TO_15"
    return "GT_15"


def stop_distance_atr_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value < Decimal("0.5"):
        return "LT_0_5_ATR"
    if value < Decimal("1"):
        return "0_5_TO_1_ATR"
    if value < Decimal("1.5"):
        return "1_TO_1_5_ATR"
    if value < Decimal("2"):
        return "1_5_TO_2_ATR"
    if value < Decimal("3"):
        return "2_TO_3_ATR"
    if value < Decimal("4"):
        return "3_TO_4_ATR"
    return "GT_4_ATR"


def structural_rr_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 0:
        return "LE_0"
    if value < Decimal("0.5"):
        return "0_TO_0_5"
    if value < Decimal("1.0"):
        return "0_5_TO_1_0"
    if value < Decimal("1.5"):
        return "1_0_TO_1_5"
    if value < Decimal("2.0"):
        return "1_5_TO_2_0"
    if value < Decimal("2.5"):
        return "2_0_TO_2_5"
    return "GE_2_5"


def capital_utilization_bucket(value: Decimal | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value < Decimal("5"):
        return "LT_5"
    if value < Decimal("10"):
        return "5_TO_10"
    if value < Decimal("20"):
        return "10_TO_20"
    if value < Decimal("30"):
        return "20_TO_30"
    if value < Decimal("50"):
        return "30_TO_50"
    if value < Decimal("75"):
        return "50_TO_75"
    return "75_TO_100"


def quantity_driver(row: dict[str, Any]) -> str:
    risk_qty = int(decimal_or_zero(row.get("quantity_by_risk")))
    cash_qty = int(decimal_or_zero(row.get("quantity_by_cash")))
    if risk_qty < cash_qty:
        return "RISK_LIMITED"
    if cash_qty < risk_qty:
        return "CASH_LIMITED"
    return "EQUAL_LIMIT"


def ready_set(rows: Sequence[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(row["trading_date"], row["symbol"]) for row in rows if row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"}


def scenario_group(name: str) -> str:
    if name.startswith("ATR_"):
        return "ATR_BUFFER"
    if name.startswith("ENTRY_"):
        return "ENTRY_BUFFER"
    if name.startswith("STOP_"):
        return "STOP_DISTANCE_RULES"
    if name in {"BASELINE_PRIORITY", "SETUP_SPECIFIC_FIRST", "TIGHTEST_VALID_STOP", "WIDEST_VALID_STOP"}:
        return "STOP_SELECTION_COUNTERFACTUAL"
    if name in {"STRUCTURAL_STRICT_BASELINE", "NO_STRUCTURAL_TARGET_FORCE_2R", "ALWAYS_2R_REFERENCE"}:
        return "TARGET_COUNTERFACTUAL"
    return "BASELINE"


def notes_for_scenario(name: str) -> str:
    if name == "ALWAYS_2R_REFERENCE":
        return "INVALID_FOR_BASELINE_STRATEGY_RESEARCH_DIAGNOSTIC_ONLY"
    if name == "NO_STRUCTURAL_TARGET_FORCE_2R":
        return "Expected to match baseline if fallback semantics are correct."
    if name == "SETUP_SPECIFIC_FIRST":
        return "Audit-only transparent setup-specific priority; baseline not modified."
    return "Audit-only scenario; baseline retained."


def rows_by_scenario(rows: Sequence[dict[str, Any]], scenario: str) -> dict[str, Any]:
    return next(row for row in rows if row["scenario"] == scenario)


def count_label(count: int) -> str:
    if count >= 4:
        return "4_PLUS"
    return str(count)


def reason_size_label(count: int) -> str:
    if count >= 3:
        return "3_PLUS"
    return str(count)


def group_rows(rows: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, ""))].append(row)
    return dict(grouped)


def distribution(counter: Counter[str], total: int, *, limit: int | None = None) -> dict[str, Any]:
    return {
        key: {"count": count, "pct": pct(count, total)}
        for key, count in counter.most_common(limit)
    }


def atr_buffer_contribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = [
        decimal_or_zero(row.get("atr_buffer_value")) / decimal_or_zero(row.get("stop_distance_abs")) * Decimal("100")
        for row in rows
        if decimal_or_zero(row.get("stop_distance_abs")) > 0
    ]
    return {
        "p25": decimal_quantile(values, Decimal("0.25")),
        "median": median_decimal(values),
        "p75": decimal_quantile(values, Decimal("0.75")),
        "p90": decimal_quantile(values, Decimal("0.90")),
    }


def clean_decimals(values: Iterable[Decimal | None]) -> list[Decimal]:
    return sorted(value for value in values if value is not None)


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal | str:
    if not values:
        return ""
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


def median_decimal(values: Iterable[Decimal | None]) -> Decimal | str:
    clean = clean_decimals(values)
    if not clean:
        return ""
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / Decimal("2")


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


def decimal_or_zero(value: Any) -> Decimal:
    return parse_decimal(value) or Decimal("0")


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def round_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.0001")), "f")


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def observed_single_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def prohibited_audit_fields() -> list[str]:
    fields = (
        STOP_CANDIDATE_FIELDS
        + STOP_BASIS_AUDIT_FIELDS
        + TARGET_SEMANTICS_FIELDS
        + RR_FAILURE_CAUSE_FIELDS
        + CAPITAL_AUDIT_FIELDS
        + SENSITIVITY_FIELDS
        + RISK_TOO_LARGE_FIELDS
        + SINGLE_SHARE_FIELDS
        + STOP_CANDIDATE_DETAIL_FIELDS
        + STOP_SELECTION_DETAIL_FIELDS
        + RISK_OUTPUT_FIELDS
    )
    flagged = []
    for field in fields:
        lower = field.lower()
        if any(token in lower for token in PROHIBITED_AUDIT_FIELD_TOKENS):
            flagged.append(field)
    return sorted(set(flagged))


def write_gzip_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def audit_output_size(config: RiskStructureAuditConfig) -> int:
    paths = [
        config.summary_path,
        config.stop_candidates_path,
        config.stop_basis_audit_path,
        config.target_semantics_path,
        config.rr_failure_causes_path,
        config.capital_audit_path,
        config.sensitivity_path,
        config.risk_too_large_cases_path,
        config.single_share_cases_path,
        config.stop_candidate_detail_path,
        config.stop_selection_detail_path,
        config.scenario_membership_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())

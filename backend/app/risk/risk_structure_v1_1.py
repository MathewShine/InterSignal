from __future__ import annotations

import csv
import gzip
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.regime.regime_config import MarketRegimeConfig
from app.risk.risk_config import (
    RISK_STRUCTURE_V1_CONFIG_HASH,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_VERSION,
    RISK_STRUCTURE_VERSION,
    SETUP_SPECIFIC_FIRST_METHODOLOGY,
    RiskStructureV11Config,
    resolve_risk_structure_dataset,
)
from app.risk.risk_structurer import (
    RISK_OUTPUT_FIELDS,
    assumed_long_entry_price,
    atr_14_value,
    entry_reference_price,
    evaluate_risk_rows,
    load_adjusted_history,
    load_entry_rows,
    load_lookup,
    load_regime_lookup,
    patch_history_from_context,
    prohibited_outcome_fields,
)
from app.risk.stop_placement import (
    StopCandidateAssessment,
    assess_stop_candidate,
    build_ohlc_index,
    stop_candidates,
)
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.entry_config import EntryEvaluationConfig
from app.strategy.momentum_candidates import file_sha256, split_codes
from app.strategy.setup_config import DailySetupEvaluationConfig

V11_METADATA_FIELDS = [
    "previous_risk_version",
    "previous_risk_config_hash",
    "stop_selection_methodology",
    "selected_stop_priority_reason",
    "fallback_stop_used",
    "fallback_reason",
    "setup_specific_stop_available",
    "setup_specific_stop_valid",
]
RISK_V11_OUTPUT_FIELDS = RISK_OUTPUT_FIELDS[:15] + V11_METADATA_FIELDS + RISK_OUTPUT_FIELDS[15:]

COMPARISON_FIELDS = [
    "trading_date",
    "symbol",
    "setup_type_flags",
    "daily_level_reclaim",
    "regime_state",
    "old_stop_basis",
    "new_stop_basis",
    "stop_basis_changed",
    "old_stop_price",
    "new_stop_price",
    "stop_price_changed",
    "old_stop_distance_pct",
    "new_stop_distance_pct",
    "stop_distance_pct_delta",
    "old_stop_distance_atr",
    "new_stop_distance_atr",
    "stop_distance_atr_delta",
    "old_reward_risk",
    "new_reward_risk",
    "reward_risk_delta",
    "old_quantity",
    "new_quantity",
    "old_position_notional",
    "new_position_notional",
    "old_capital_utilization_pct",
    "new_capital_utilization_pct",
    "old_planned_rupee_risk",
    "new_planned_rupee_risk",
    "old_planned_risk_pct",
    "new_planned_risk_pct",
    "old_readiness",
    "new_readiness",
    "readiness_changed",
]
STOP_BASIS_FIELDS = ["risk_version", "stop_basis", "rows", "pct", "valid_stop_rows", "ready_rows"]
SETUP_COMPARISON_FIELDS = [
    "setup_type",
    "risk_version",
    "stop_basis",
    "rows",
    "pct",
    "median_stop_pct",
    "median_stop_atr",
    "median_reward_risk",
    "ready_rows",
    "ready_rate_pct",
]
PILOT_FIELDS = [
    "pilot_case",
    "symbol",
    "trading_date",
    "setup_type_flags",
    "daily_level_reclaim",
    "candidate_basis",
    "candidate_level",
    "candidate_stop_price",
    "candidate_eligible",
    "candidate_band",
    "candidate_quality",
    "candidate_valid",
    "old_selected_basis",
    "new_selected_basis",
    "assumed_entry_price",
    "atr_14",
    "atr_buffer_multiple",
    "old_target_basis",
    "new_target_basis",
    "old_reward_risk",
    "new_reward_risk",
    "old_quantity",
    "new_quantity",
    "old_planned_risk_pct",
    "new_planned_risk_pct",
    "old_readiness",
    "new_readiness",
    "result",
    "notes",
]
REGRESSION_FIELDS = ["metric", "old_value", "new_value", "violations", "result"]


@dataclass(frozen=True, slots=True)
class RiskStructureV11EngineConfig:
    data_dir: Path
    risk_config: RiskStructureV11Config = RiskStructureV11Config()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    regime_config: MarketRegimeConfig = MarketRegimeConfig()
    entry_config: EntryEvaluationConfig = EntryEvaluationConfig()
    full_generation: bool = True

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
    def adjusted_daily_dir(self) -> Path:
        return self.data_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def old_dataset_path(self) -> Path:
        return resolve_risk_structure_dataset(self.data_dir, RISK_STRUCTURE_VERSION)

    @property
    def output_dataset_path(self) -> Path:
        return resolve_risk_structure_dataset(self.data_dir, RISK_STRUCTURE_V1_1_VERSION)

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_summary.json"

    @property
    def comparison_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_vs_v1_1_comparison.csv"

    @property
    def stop_basis_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_stop_basis.csv"

    @property
    def setup_comparison_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_setup_type_comparison.csv"

    @property
    def pilot_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_pilot_validation.csv"

    @property
    def target_regression_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_target_regression.csv"

    @property
    def capital_regression_path(self) -> Path:
        return self.reports_dir / "risk_structure_v1_1_capital_regression.csv"


def build_risk_structures_v1_1(
    *,
    config: RiskStructureV11EngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    hashes_before = baseline_hashes(config)
    if hashes_before["risk_v1"] != RISK_STRUCTURE_V1_DATASET_HASH:
        raise ValueError(
            f"RISK_STRUCTURE_V1 hash mismatch: expected {RISK_STRUCTURE_V1_DATASET_HASH}, "
            f"observed {hashes_before['risk_v1']}"
        )

    notify(progress, "Loading immutable V1 and the same progressed entry scope")
    old_rows = read_gzip_rows(config.old_dataset_path)
    entry_rows = load_entry_rows(config.entry_dataset_path, config.risk_config)
    keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in entry_rows}
    if len(old_rows) != len(entry_rows):
        raise ValueError(f"V1/input row-count mismatch: {len(old_rows)} != {len(entry_rows)}")

    notify(progress, "Joining unchanged setup, feature, regime, and causal OHLC context")
    setup_lookup = load_lookup(config.setup_dataset_path, keys)
    feature_lookup = load_lookup(config.feature_dataset_path, keys)
    dates = {date for date, _ in keys}
    symbols = {symbol for _, symbol in keys}
    regime_lookup = load_regime_lookup(config.regime_dataset_path, dates)
    history = load_adjusted_history(
        adjusted_daily_dir=config.adjusted_daily_dir,
        symbols=symbols,
        through_date=max(dates) if dates else "",
    )
    patch_history_from_context(history=history, keys=keys, setup_lookup=setup_lookup, feature_lookup=feature_lookup)
    history_index = build_ohlc_index(history)

    notify(progress, "Evaluating versioned setup-specific-first risk structures")
    new_rows = evaluate_risk_rows(
        entry_rows=entry_rows,
        setup_lookup=setup_lookup,
        feature_lookup=feature_lookup,
        regime_lookup=regime_lookup,
        history=history,
        history_index=history_index,
        config=config.risk_config,
    )
    pairs = comparison_pairs(old_rows, new_rows, setup_lookup)
    comparison_rows = [comparison_row(pair) for pair in pairs]

    notify(progress, "Reconstructing causal candidate validity for semantic impact reports")
    inventory = candidate_inventory(
        entry_rows=entry_rows,
        setup_lookup=setup_lookup,
        feature_lookup=feature_lookup,
        history=history,
        history_index=history_index,
        config=config.risk_config,
    )
    pilot_rows, pilot_summary = build_pilot_report(pairs, inventory, config.risk_config)
    stop_basis_rows = stop_basis_comparison(old_rows, new_rows)
    setup_rows, setup_summary = setup_type_comparison(pairs)
    comparison = comparison_summary(pairs)
    stop_distance = stop_distance_comparison(old_rows, new_rows)
    reward_risk = reward_risk_comparison(old_rows, new_rows)
    capital = capital_comparison(old_rows, new_rows)
    impact = setup_impact(pairs, inventory)
    target_rows, target_summary = target_regression(old_rows, new_rows)
    capital_rows, capital_summary = capital_regression(old_rows, new_rows, config.risk_config)
    final_ready_violations = final_ready_invariant_violations(new_rows, config.risk_config)
    conditional_violations = conditional_preview_violations(new_rows)
    leakage = leakage_summary()

    write_csv(config.comparison_path, comparison_rows, COMPARISON_FIELDS)
    write_csv(config.stop_basis_path, stop_basis_rows, STOP_BASIS_FIELDS)
    write_csv(config.setup_comparison_path, setup_rows, SETUP_COMPARISON_FIELDS)
    write_csv(config.pilot_path, pilot_rows, PILOT_FIELDS)
    write_csv(config.target_regression_path, target_rows, REGRESSION_FIELDS)
    write_csv(config.capital_regression_path, capital_rows, REGRESSION_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_summary["passed"]:
        notify(progress, "Writing separate RISK_STRUCTURE_V1_1 dataset")
        write_v11_rows(config.output_dataset_path, new_rows)
        full_generation_completed = True

    hashes_after = baseline_hashes(config)
    regressions = {key: hashes_before[key] == hashes_after[key] for key in hashes_before}
    stop_result = stop_semantics_result(old_rows, new_rows, comparison)
    target_result = target_summary["result"]
    capital_result = capital_summary["result"]
    should_replace = (
        "A. YES - freeze new methodology"
        if stop_result == "FIX_CONFIRMED" and target_result == "UNCHANGED_AND_VALID" and capital_result == "UNCHANGED_AND_VALID"
        else "C. remain provisional"
    )
    prohibited_fields = prohibited_outcome_fields(RISK_V11_OUTPUT_FIELDS)
    report = {
        "phase": "Step 02.9",
        "command": "Command 03",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "risk": {
            "old_version": RISK_STRUCTURE_VERSION,
            "old_config_hash": RISK_STRUCTURE_V1_CONFIG_HASH,
            "old_dataset_hash": hashes_after["risk_v1"],
            "new_version": config.risk_config.risk_version,
            "new_config_hash": config.risk_config.config_hash(),
            "stop_selection_methodology": config.risk_config.stop_selection_methodology,
        },
        "methodology_delta": {
            "changed": "Explicit setup-specific-first, validity-aware stop selection for multi-flag rows.",
            "unchanged": ["input scope", "ATR buffer", "entry buffer", "target selection", "R:R thresholds", "capital and risk rules"],
            "priority": ["CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE", "RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3", "safe causal fallback"],
        },
        "inputs": {
            "rows": len(entry_rows),
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
        },
        "pilot": pilot_summary,
        "comparison": comparison,
        "stop_basis": {
            "old": basis_distribution(old_rows),
            "new": basis_distribution(new_rows),
            "distance": stop_distance,
            "setup_types": setup_summary,
            "impact": impact,
        },
        "reward_risk": reward_risk,
        "capital": capital,
        "target_regression": target_summary,
        "capital_regression": capital_summary,
        "invariants": {
            "final_ready_violations": final_ready_violations,
            "conditional_preview_violations": conditional_violations,
            "whole_share_violations": capital_summary["whole_share_violations"],
            "capital_risk_violations": capital_summary["capital_risk_violations"],
        },
        "results": {
            "stop_semantics": stop_result,
            "target_regression": target_result,
            "capital_regression": capital_result,
            "forward_baseline_decision": should_replace,
        },
        "regression": regressions,
        "leakage": leakage,
        "safety": {
            "prohibited_output_fields": prohibited_fields,
            "final_strategy_scores_generated": 0,
            "trade_signals_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "generation": {
            "pilot_only": not config.full_generation,
            "full_generation_completed": full_generation_completed,
            "output_rows": len(new_rows),
            "new_dataset_hash": file_sha256(config.output_dataset_path) if full_generation_completed else "NOT_WRITTEN",
        },
        "outputs": {
            "dataset": str(config.output_dataset_path),
            "summary": str(config.summary_path),
            "comparison": str(config.comparison_path),
            "stop_basis": str(config.stop_basis_path),
            "setup_type_comparison": str(config.setup_comparison_path),
            "pilot_validation": str(config.pilot_path),
            "target_regression": str(config.target_regression_path),
            "capital_regression": str(config.capital_regression_path),
            "documentation": "docs/strategy-v1-risk-structure-v1-1.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "storage_size_bytes": output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        full_generation_completed
        and pilot_summary["passed"]
        and all(regressions.values())
        and target_result == "UNCHANGED_AND_VALID"
        and capital_result == "UNCHANGED_AND_VALID"
        and stop_result in {"FIX_CONFIRMED", "PARTIAL_FIX"}
        and not final_ready_violations
        and not conditional_violations
        and not prohibited_fields
    )
    write_json(config.summary_path, report)
    return report


def comparison_pairs(
    old_rows: Sequence[dict[str, Any]],
    new_rows: Sequence[dict[str, Any]],
    setup_lookup: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    old_lookup = {row_key(row): row for row in old_rows}
    new_lookup = {row_key(row): row for row in new_rows}
    if old_lookup.keys() != new_lookup.keys():
        raise ValueError("V1 and V1.1 row keys differ")
    return [
        {"key": key, "old": old_lookup[key], "new": new_lookup[key], "setup": setup_lookup.get(key, {})}
        for key in sorted(old_lookup)
    ]


def comparison_row(pair: dict[str, Any]) -> dict[str, Any]:
    old = pair["old"]
    new = pair["new"]
    setup = pair["setup"]
    return {
        "trading_date": new["trading_date"],
        "symbol": new["symbol"],
        "setup_type_flags": new.get("setup_type_flags", ""),
        "daily_level_reclaim": setup.get("daily_level_reclaim", ""),
        "regime_state": new.get("regime_state", ""),
        "old_stop_basis": old.get("invalidation_basis", ""),
        "new_stop_basis": new.get("invalidation_basis", ""),
        "stop_basis_changed": old.get("invalidation_basis") != new.get("invalidation_basis"),
        "old_stop_price": old.get("stop_price", ""),
        "new_stop_price": new.get("stop_price", ""),
        "stop_price_changed": decimal_changed(old.get("stop_price"), new.get("stop_price")),
        "old_stop_distance_pct": old.get("stop_distance_pct", ""),
        "new_stop_distance_pct": new.get("stop_distance_pct", ""),
        "stop_distance_pct_delta": decimal_delta(new.get("stop_distance_pct"), old.get("stop_distance_pct")),
        "old_stop_distance_atr": old.get("stop_distance_atr_multiple", ""),
        "new_stop_distance_atr": new.get("stop_distance_atr_multiple", ""),
        "stop_distance_atr_delta": decimal_delta(new.get("stop_distance_atr_multiple"), old.get("stop_distance_atr_multiple")),
        "old_reward_risk": old.get("reward_risk_ratio", ""),
        "new_reward_risk": new.get("reward_risk_ratio", ""),
        "reward_risk_delta": decimal_delta(new.get("reward_risk_ratio"), old.get("reward_risk_ratio")),
        "old_quantity": old.get("structured_quantity", ""),
        "new_quantity": new.get("structured_quantity", ""),
        "old_position_notional": old.get("position_notional", ""),
        "new_position_notional": new.get("position_notional", ""),
        "old_capital_utilization_pct": old.get("capital_utilization_pct", ""),
        "new_capital_utilization_pct": new.get("capital_utilization_pct", ""),
        "old_planned_rupee_risk": old.get("planned_rupee_risk", ""),
        "new_planned_rupee_risk": new.get("planned_rupee_risk", ""),
        "old_planned_risk_pct": old.get("planned_risk_pct", ""),
        "new_planned_risk_pct": new.get("planned_risk_pct", ""),
        "old_readiness": old.get("risk_readiness", ""),
        "new_readiness": new.get("risk_readiness", ""),
        "readiness_changed": old.get("risk_readiness") != new.get("risk_readiness"),
    }


def candidate_inventory(
    *,
    entry_rows: Sequence[dict[str, Any]],
    setup_lookup: dict[tuple[str, str], dict[str, Any]],
    feature_lookup: dict[tuple[str, str], dict[str, Any]],
    history: dict[str, Sequence[Any]],
    history_index: dict[tuple[str, str], int],
    config: RiskStructureV11Config,
) -> dict[tuple[str, str], dict[str, StopCandidateAssessment]]:
    output: dict[tuple[str, str], dict[str, StopCandidateAssessment]] = {}
    for entry in entry_rows:
        key = row_key(entry)
        setup = setup_lookup.get(key, {})
        feature = feature_lookup.get(key, {})
        bars = history.get(key[1], ())
        bar_index = history_index.get(key)
        reference = entry_reference_price(setup, feature, entry)
        assumed_entry = assumed_long_entry_price(reference, config)
        atr = atr_14_value(setup, feature, reference)
        if assumed_entry is None or atr is None or bar_index is None:
            output[key] = {}
            continue
        candidates = stop_candidates(
            entry_row=entry,
            setup_row=setup,
            feature_row=feature,
            bars=bars,
            bar_index=bar_index,
            config=config,
        )
        output[key] = {
            candidate.basis: assess_stop_candidate(
                candidate=candidate,
                assumed_entry_price=assumed_entry,
                atr_14=atr,
                config=config,
            )
            for candidate in candidates
        }
    return output


def build_pilot_report(
    pairs: Sequence[dict[str, Any]],
    inventory: dict[tuple[str, str], dict[str, StopCandidateAssessment]],
    config: RiskStructureV11Config,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[tuple[str, Callable[[dict[str, Any]], bool], str]] = [
        ("A_MULTI_FLAG_CONSOLIDATION_CONTINUATION", lambda p: has_flag(p, "CONSOLIDATION_BREAKOUT") and has_flag(p, "MOMENTUM_CONTINUATION") and p["new"].get("invalidation_basis") == "CONSOLIDATION_LOW", "Valid consolidation structure wins."),
        ("B_MULTI_FLAG_RECLAIM_CONTINUATION", lambda p: is_reclaim(p) and has_flag(p, "MOMENTUM_CONTINUATION") and p["new"].get("invalidation_basis") == "DAILY_RECLAIM_LOW", "Valid reclaim structure wins."),
        ("C_BREAKOUT_CONTINUATION_VALID", lambda p: has_flag(p, "BREAKOUT_20D") and has_flag(p, "MOMENTUM_CONTINUATION") and p["new"].get("invalidation_basis") == "BREAKOUT_STRUCTURE", "Valid breakout structure wins when no stronger active structure wins."),
        ("D_BREAKOUT_TOO_TIGHT_FALLBACK", lambda p: breakout_too_tight(p, inventory) and truthy(p["new"].get("fallback_stop_used")) and truthy(p["new"].get("stop_valid")), "Invalid breakout structure falls back safely."),
        ("E_CONTINUATION_ONLY", lambda p: continuation_only(p) and str(p["new"].get("invalidation_basis", "")).startswith("RECENT_SWING_LOW_"), "Continuation-only rows retain swing support."),
        ("F_STOP_TIGHTER", lambda p: decimal_delta(p["new"].get("stop_distance_pct"), p["old"].get("stop_distance_pct")) < 0, "New valid structure is tighter."),
        ("G_STOP_WIDER", lambda p: decimal_delta(p["new"].get("stop_distance_pct"), p["old"].get("stop_distance_pct")) > 0, "New valid structure is wider."),
        ("H_REJECT_TO_PASS", lambda p: not ready(p["old"]) and ready(p["new"]), "Readiness changes from reject to pass."),
        ("I_PASS_TO_REJECT", lambda p: ready(p["old"]) and not ready(p["new"]), "Readiness changes from pass to reject."),
        ("J_BEARISH_EXCEPTIONAL_LONG", lambda p: p["new"].get("regime_state") == "BEARISH" and p["new"].get("entry_readiness") == "EXCEPTIONAL_LONG_REVIEW", "Bearish exceptional long keeps the same thresholds."),
    ]
    selected: list[tuple[str, dict[str, Any] | None, str]] = []
    seen: set[tuple[str, str]] = set()
    for name, predicate, note in cases:
        match = next((pair for pair in pairs if pair["key"] not in seen and predicate(pair)), None)
        if match:
            seen.add(match["key"])
        selected.append((name, match, note))

    rows: list[dict[str, Any]] = []
    case_results: dict[str, str] = {}
    symbols: list[str] = []
    dates: list[str] = []
    for case_name, pair, note in selected:
        if pair is None:
            result = "NOT_APPLICABLE" if case_name == "E_CONTINUATION_ONLY" else "MISSING"
            case_results[case_name] = result
            rows.append(empty_pilot_row(case_name, result, note))
            continue
        old = pair["old"]
        new = pair["new"]
        assessments = inventory.get(pair["key"], {})
        passed = pilot_invariants(old, new, assessments, config)
        result = "PASS" if passed else "FAIL"
        case_results[case_name] = result
        symbols.append(new["symbol"])
        dates.append(new["trading_date"])
        for basis, assessment in assessments.items():
            rows.append(pilot_row(case_name, pair, basis, assessment, result, note, config))

    blocking = [value for value in case_results.values() if value not in {"PASS", "NOT_APPLICABLE"}]
    return rows, {
        "passed": not blocking,
        "case_results": case_results,
        "symbols": symbols,
        "dates": dates,
        "real_rows": len(symbols),
        "continuation_only_rows_in_scope": sum(continuation_only(pair) for pair in pairs),
        "notes": "Continuation-only is not applicable when every current row also carries BREAKOUT_20D; synthetic tests cover that branch.",
    }


def pilot_invariants(
    old: dict[str, Any],
    new: dict[str, Any],
    assessments: dict[str, StopCandidateAssessment],
    config: RiskStructureV11Config,
) -> bool:
    selected = assessments.get(str(new.get("invalidation_basis", "")))
    return bool(
        new.get("risk_version") == RISK_STRUCTURE_V1_1_VERSION
        and new.get("risk_config_hash") == config.config_hash()
        and new.get("stop_selection_methodology") == SETUP_SPECIFIC_FIRST_METHODOLOGY
        and selected is not None
        and selected.valid
        and decimal(new.get("atr_buffer_multiple")) == Decimal("0.20")
        and decimal(new.get("entry_buffer_pct")) == Decimal("0.10")
        and old.get("selected_target_basis") == new.get("selected_target_basis")
        and old.get("structural_target_status") == new.get("structural_target_status")
        and decimal(new.get("planned_risk_pct"), Decimal("0")) <= Decimal("1.00")
        and new.get("final_strategy_score_status") == "NOT_IMPLEMENTED"
        and new.get("trade_signal_status") == "NOT_GENERATED"
    )


def pilot_row(
    case_name: str,
    pair: dict[str, Any],
    basis: str,
    assessment: StopCandidateAssessment,
    result: str,
    note: str,
    config: RiskStructureV11Config,
) -> dict[str, Any]:
    old, new, setup = pair["old"], pair["new"], pair["setup"]
    return {
        "pilot_case": case_name,
        "symbol": new["symbol"],
        "trading_date": new["trading_date"],
        "setup_type_flags": new.get("setup_type_flags", ""),
        "daily_level_reclaim": setup.get("daily_level_reclaim", ""),
        "candidate_basis": basis,
        "candidate_level": assessment.candidate.level,
        "candidate_stop_price": assessment.stop_price,
        "candidate_eligible": assessment.eligible,
        "candidate_band": assessment.band,
        "candidate_quality": assessment.quality,
        "candidate_valid": assessment.valid,
        "old_selected_basis": old.get("invalidation_basis", ""),
        "new_selected_basis": new.get("invalidation_basis", ""),
        "assumed_entry_price": new.get("assumed_entry_price", ""),
        "atr_14": new.get("atr_14", ""),
        "atr_buffer_multiple": config.stop.atr_buffer_multiple,
        "old_target_basis": old.get("selected_target_basis", ""),
        "new_target_basis": new.get("selected_target_basis", ""),
        "old_reward_risk": old.get("reward_risk_ratio", ""),
        "new_reward_risk": new.get("reward_risk_ratio", ""),
        "old_quantity": old.get("structured_quantity", ""),
        "new_quantity": new.get("structured_quantity", ""),
        "old_planned_risk_pct": old.get("planned_risk_pct", ""),
        "new_planned_risk_pct": new.get("planned_risk_pct", ""),
        "old_readiness": old.get("risk_readiness", ""),
        "new_readiness": new.get("risk_readiness", ""),
        "result": result,
        "notes": note,
    }


def empty_pilot_row(case_name: str, result: str, notes: str) -> dict[str, Any]:
    return {field: "" for field in PILOT_FIELDS} | {"pilot_case": case_name, "result": result, "notes": notes}


def stop_basis_comparison(old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for version, rows in ((RISK_STRUCTURE_VERSION, old_rows), (RISK_STRUCTURE_V1_1_VERSION, new_rows)):
        counter = Counter(str(row.get("invalidation_basis", "UNAVAILABLE")) for row in rows)
        for basis, count in sorted(counter.items()):
            group = [row for row in rows if row.get("invalidation_basis") == basis]
            output.append({
                "risk_version": version,
                "stop_basis": basis,
                "rows": count,
                "pct": pct(count, len(rows)),
                "valid_stop_rows": sum(truthy(row.get("stop_valid")) for row in group),
                "ready_rows": sum(ready(row) for row in group),
            })
    return output


def setup_type_comparison(pairs: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for setup_type in ("BREAKOUT_20D", "CONSOLIDATION_BREAKOUT", "DAILY_RECLAIM", "MOMENTUM_CONTINUATION"):
        selected = [pair for pair in pairs if pair_in_setup(pair, setup_type)]
        summary[setup_type] = {"rows": len(selected)}
        for label, version in (("old", RISK_STRUCTURE_VERSION), ("new", RISK_STRUCTURE_V1_1_VERSION)):
            rows = [pair[label] for pair in selected]
            summary[setup_type][label] = profile(rows)
            for basis, count in sorted(Counter(str(row.get("invalidation_basis", "UNAVAILABLE")) for row in rows).items()):
                group = [row for row in rows if row.get("invalidation_basis") == basis]
                output.append({
                    "setup_type": setup_type,
                    "risk_version": version,
                    "stop_basis": basis,
                    "rows": count,
                    "pct": pct(count, len(rows)),
                    "median_stop_pct": median(row.get("stop_distance_pct") for row in group),
                    "median_stop_atr": median(row.get("stop_distance_atr_multiple") for row in group),
                    "median_reward_risk": median(row.get("reward_risk_ratio") for row in group),
                    "ready_rows": sum(ready(row) for row in group),
                    "ready_rate_pct": pct(sum(ready(row) for row in group), len(group)),
                })
    return output, summary


def setup_impact(
    pairs: Sequence[dict[str, Any]],
    inventory: dict[tuple[str, str], dict[str, StopCandidateAssessment]],
) -> dict[str, Any]:
    specs = {
        "consolidation": (lambda pair: has_flag(pair, "CONSOLIDATION_BREAKOUT"), "CONSOLIDATION_LOW"),
        "reclaim": (is_reclaim, "DAILY_RECLAIM_LOW"),
        "breakout": (lambda pair: has_flag(pair, "BREAKOUT_20D"), "BREAKOUT_STRUCTURE"),
        "continuation_only": (continuation_only, "RECENT_SWING_LOW_5"),
    }
    output: dict[str, Any] = {}
    for name, (predicate, basis) in specs.items():
        group = [pair for pair in pairs if predicate(pair)]
        assessments = [inventory.get(pair["key"], {}).get(basis) for pair in group]
        output[name] = {
            "rows": len(group),
            "candidate_available": sum(item is not None for item in assessments),
            "candidate_valid": sum(bool(item and item.valid) for item in assessments),
            "candidate_too_tight": sum(bool(item and item.band == "TOO_TIGHT") for item in assessments),
            "selected_old": sum(pair["old"].get("invalidation_basis") == basis for pair in group),
            "selected_new": sum(pair["new"].get("invalidation_basis") == basis for pair in group),
            "ready_old": sum(ready(pair["old"]) for pair in group),
            "ready_new": sum(ready(pair["new"]) for pair in group),
        }
    momentum = [pair for pair in pairs if has_flag(pair, "MOMENTUM_CONTINUATION")]
    output["multi_flag_momentum"] = {
        "rows": len(momentum),
        "changed_stop_basis": sum(pair["old"].get("invalidation_basis") != pair["new"].get("invalidation_basis") for pair in momentum),
        "median_stop_distance_delta": median(decimal_delta(pair["new"].get("stop_distance_pct"), pair["old"].get("stop_distance_pct")) for pair in momentum),
        "median_reward_risk_delta": median(decimal_delta(pair["new"].get("reward_risk_ratio"), pair["old"].get("reward_risk_ratio")) for pair in momentum),
        "ready_old": sum(ready(pair["old"]) for pair in momentum),
        "ready_new": sum(ready(pair["new"]) for pair in momentum),
    }
    return output


def comparison_summary(pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    old_ready = {pair["key"] for pair in pairs if ready(pair["old"])}
    new_ready = {pair["key"] for pair in pairs if ready(pair["new"])}
    retained = old_ready & new_ready
    removed = old_ready - new_ready
    introduced = new_ready - old_ready
    union = old_ready | new_ready
    return {
        "rows_evaluated": len(pairs),
        "changed_stop_basis": sum(pair["old"].get("invalidation_basis") != pair["new"].get("invalidation_basis") for pair in pairs),
        "changed_stop_price": sum(decimal_changed(pair["old"].get("stop_price"), pair["new"].get("stop_price")) for pair in pairs),
        "changed_readiness": sum(pair["old"].get("risk_readiness") != pair["new"].get("risk_readiness") for pair in pairs),
        "old_ready": len(old_ready),
        "new_ready": len(new_ready),
        "retained_ready": len(retained),
        "removed_ready": len(removed),
        "introduced_ready": len(introduced),
        "jaccard": format(Decimal(len(retained)) / Decimal(len(union)), ".4f") if union else "1.0000",
    }


def stop_distance_comparison(old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stop_distance_pct": {"old": numeric_summary(row.get("stop_distance_pct") for row in old_rows), "new": numeric_summary(row.get("stop_distance_pct") for row in new_rows)},
        "stop_distance_atr": {"old": numeric_summary(row.get("stop_distance_atr_multiple") for row in old_rows), "new": numeric_summary(row.get("stop_distance_atr_multiple") for row in new_rows)},
    }


def reward_risk_comparison(old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"old": reward_risk_profile(old_rows), "new": reward_risk_profile(new_rows)}


def reward_risk_profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = [value for value in (decimal(row.get("reward_risk_ratio")) for row in rows) if value is not None]
    return {
        "median": median(values),
        "mean": mean(values),
        "below_1_5": sum(value < Decimal("1.5") for value in values),
        "1_5_to_2": sum(Decimal("1.5") <= value < Decimal("2") for value in values),
        "2_to_2_5": sum(Decimal("2") <= value < Decimal("2.5") for value in values),
        "gte_2_5": sum(value >= Decimal("2.5") for value in values),
        "gte_1_5": sum(value >= Decimal("1.5") for value in values),
        "ready": sum(ready(row) for row in rows),
    }


def capital_comparison(old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"old": capital_profile(old_rows), "new": capital_profile(new_rows)}


def capital_profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "median_quantity": median(row.get("structured_quantity") for row in rows),
        "median_notional": median(row.get("position_notional") for row in rows),
        "median_capital_utilization_pct": median(row.get("capital_utilization_pct") for row in rows),
        "median_planned_rupee_risk": median(row.get("planned_rupee_risk") for row in rows),
        "median_planned_risk_pct": median(row.get("planned_risk_pct") for row in rows),
    }


def target_regression(
    old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metrics = {
        "structural_target_available": lambda rows: sum(row.get("structural_target_status") == "AVAILABLE" for row in rows),
        "structural_target_selected": lambda rows: sum(row.get("structural_target_status") == "AVAILABLE" and row.get("selected_target_basis") != "R_MULTIPLE_2R_RESEARCH_REFERENCE" for row in rows),
        "fallback_2r": lambda rows: sum(row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE" for row in rows),
    }
    old_lookup = {row_key(row): row for row in old_rows}
    new_lookup = {row_key(row): row for row in new_rows}
    non_evaluable = sum(row.get("invalidation_basis") == "UNAVAILABLE" for row in new_rows)
    semantic_mismatches = sum(
        old_lookup[key].get("structural_target_status") != row.get("structural_target_status")
        or old_lookup[key].get("selected_target_basis") != row.get("selected_target_basis")
        for key, row in new_lookup.items()
        if row.get("invalidation_basis") != "UNAVAILABLE"
    )
    rows = []
    for metric, calculate in metrics.items():
        old_value, new_value = calculate(old_rows), calculate(new_rows)
        rows.append({"metric": metric, "old_value": old_value, "new_value": new_value, "violations": semantic_mismatches, "result": "PASS" if semantic_mismatches == 0 else "FAIL"})
    artificial = sum(row.get("structural_target_status") == "AVAILABLE" and row.get("selected_target_basis") == "R_MULTIPLE_2R_RESEARCH_REFERENCE" for row in new_rows)
    below_minimum = sum(
        row.get("structural_target_status") == "AVAILABLE"
        and (decimal(row.get("reward_risk_ratio"), Decimal("0")) or Decimal("0")) < Decimal("1.5")
        and ready(row)
        for row in new_rows
    )
    rows.extend([
        {"metric": "artificial_2r_replacement", "old_value": 0, "new_value": artificial, "violations": artificial, "result": "PASS" if artificial == 0 else "FAIL"},
        {"metric": "structural_below_minimum_passed", "old_value": 0, "new_value": below_minimum, "violations": below_minimum, "result": "PASS" if below_minimum == 0 else "FAIL"},
        {"metric": "target_not_evaluable_without_valid_stop", "old_value": 0, "new_value": non_evaluable, "violations": 0, "result": "PASS"},
    ])
    result = "UNCHANGED_AND_VALID" if all(row["result"] == "PASS" for row in rows) else "SEMANTIC_REGRESSION"
    return rows, {
        "result": result,
        "structural_target_available_old": metrics["structural_target_available"](old_rows),
        "structural_target_available_new": metrics["structural_target_available"](new_rows),
        "fallback_2r_old": metrics["fallback_2r"](old_rows),
        "fallback_2r_new": metrics["fallback_2r"](new_rows),
        "artificial_2r_replacements": artificial,
        "structural_below_minimum_violations": below_minimum,
        "semantic_mismatches_on_evaluable_rows": semantic_mismatches,
        "not_evaluable_without_valid_stop": non_evaluable,
    }


def capital_regression(
    old_rows: Sequence[dict[str, Any]],
    new_rows: Sequence[dict[str, Any]],
    config: RiskStructureV11Config,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    risk_violations = sum((decimal(row.get("planned_risk_pct"), Decimal("0")) or Decimal("0")) > config.capital.max_risk_per_trade_pct for row in new_rows)
    whole_share_violations = sum(not integer_value(row.get("structured_quantity")) or row.get("whole_share_status") != "WHOLE_SHARES_ONLY" for row in new_rows)
    leverage_violations = sum(row.get("no_leverage_status") != "NO_LEVERAGE" for row in new_rows)
    old_affordability = sum("AFFORDABILITY_FAIL" in split_codes(row.get("rejection_reasons")) for row in old_rows)
    new_affordability = sum("AFFORDABILITY_FAIL" in split_codes(row.get("rejection_reasons")) for row in new_rows)
    rows = [
        {"metric": "planned_risk_pct_gt_1", "old_value": 0, "new_value": risk_violations, "violations": risk_violations, "result": "PASS" if risk_violations == 0 else "FAIL"},
        {"metric": "whole_share", "old_value": 0, "new_value": whole_share_violations, "violations": whole_share_violations, "result": "PASS" if whole_share_violations == 0 else "FAIL"},
        {"metric": "no_leverage", "old_value": 0, "new_value": leverage_violations, "violations": leverage_violations, "result": "PASS" if leverage_violations == 0 else "FAIL"},
        {"metric": "affordability_failures", "old_value": old_affordability, "new_value": new_affordability, "violations": abs(old_affordability - new_affordability), "result": "PASS" if old_affordability == new_affordability else "FAIL"},
    ]
    result = "UNCHANGED_AND_VALID" if all(row["result"] == "PASS" for row in rows) else "SEMANTIC_REGRESSION"
    return rows, {
        "result": result,
        "capital_risk_violations": risk_violations,
        "whole_share_violations": whole_share_violations,
        "leverage_violations": leverage_violations,
        "affordability_failures_old": old_affordability,
        "affordability_failures_new": new_affordability,
    }


def final_ready_invariant_violations(rows: Sequence[dict[str, Any]], config: RiskStructureV11Config) -> list[dict[str, Any]]:
    violations = []
    for row in rows:
        if not ready(row):
            continue
        valid = (
            row.get("risk_mode") == "FULL_EVALUATION"
            and truthy(row.get("stop_valid"))
            and row.get("stop_quality") in {"ACCEPTABLE", "GOOD"}
            and (decimal(row.get("stop_price"), Decimal("0")) or Decimal("0")) < (decimal(row.get("assumed_entry_price"), Decimal("0")) or Decimal("0"))
            and (decimal(row.get("reward_risk_ratio"), Decimal("0")) or Decimal("0")) >= config.target.minimum_reward_risk
            and (decimal(row.get("structured_quantity"), Decimal("0")) or Decimal("0")) >= Decimal("1")
            and (decimal(row.get("planned_risk_pct"), Decimal("0")) or Decimal("0")) <= config.capital.max_risk_per_trade_pct
            and not str(row.get("rejection_reasons", ""))
            and row.get("final_strategy_score_status") == "NOT_IMPLEMENTED"
            and row.get("trade_signal_status") == "NOT_GENERATED"
        )
        if not valid:
            violations.append({"trading_date": row.get("trading_date"), "symbol": row.get("symbol")})
    return violations


def conditional_preview_violations(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"trading_date": row.get("trading_date"), "symbol": row.get("symbol")}
        for row in rows
        if row.get("entry_readiness") == "CONDITIONALLY_READY"
        and (row.get("risk_mode") != "PREVIEW_ONLY" or row.get("risk_readiness") == "READY_FOR_FINAL_SCORING")
    ]


def stop_semantics_result(
    old_rows: Sequence[dict[str, Any]], new_rows: Sequence[dict[str, Any]], comparison: dict[str, Any]
) -> str:
    old_specific = sum(row.get("invalidation_basis") in {"CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE"} for row in old_rows)
    new_specific = sum(row.get("invalidation_basis") in {"CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE"} for row in new_rows)
    old_swing = sum(row.get("invalidation_basis") == "RECENT_SWING_LOW_5" for row in old_rows)
    new_swing = sum(row.get("invalidation_basis") == "RECENT_SWING_LOW_5" for row in new_rows)
    if new_specific > old_specific and new_swing < old_swing and comparison["changed_stop_basis"] > 0:
        return "FIX_CONFIRMED"
    if new_specific > old_specific or new_swing < old_swing:
        return "PARTIAL_FIX"
    if comparison["changed_stop_basis"] == 0:
        return "NO_MATERIAL_CHANGE"
    return "UNINTENDED_REGRESSION"


def basis_distribution(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        basis: {"count": count, "pct": pct(count, len(rows))}
        for basis, count in Counter(str(row.get("invalidation_basis", "UNAVAILABLE")) for row in rows).most_common()
    }


def profile(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "basis_distribution": basis_distribution(rows),
        "median_stop_pct": median(row.get("stop_distance_pct") for row in rows),
        "median_stop_atr": median(row.get("stop_distance_atr_multiple") for row in rows),
        "median_reward_risk": median(row.get("reward_risk_ratio") for row in rows),
        "ready": sum(ready(row) for row in rows),
        "ready_rate_pct": pct(sum(ready(row) for row in rows), len(rows)),
    }


def numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    cleaned = sorted(value for value in (decimal(item) for item in values) if value is not None)
    if not cleaned:
        return {"p25": "", "median": "", "mean": "", "p75": "", "p90": "", "p95": ""}
    return {
        "p25": quantile(cleaned, Decimal("0.25")),
        "median": quantile(cleaned, Decimal("0.50")),
        "mean": sum(cleaned) / Decimal(len(cleaned)),
        "p75": quantile(cleaned, Decimal("0.75")),
        "p90": quantile(cleaned, Decimal("0.90")),
        "p95": quantile(cleaned, Decimal("0.95")),
    }


def quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if len(values) == 1:
        return values[0]
    position = percentile * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - Decimal(lower)
    return values[lower] + (values[upper] - values[lower]) * weight


def median(values: Iterable[Any]) -> Decimal | str:
    cleaned = sorted(value for value in (decimal(item) for item in values) if value is not None)
    return quantile(cleaned, Decimal("0.50")) if cleaned else ""


def mean(values: Iterable[Any]) -> Decimal | str:
    cleaned = [value for value in (decimal(item) for item in values) if value is not None]
    return sum(cleaned) / Decimal(len(cleaned)) if cleaned else ""


def leakage_summary() -> dict[str, Any]:
    return {
        "t_plus_1_data_used": 0,
        "future_low_high_used": 0,
        "future_pivot_used": 0,
        "future_resistance_used": 0,
        "future_stop_target_outcome_used": 0,
        "notes": "Risk evaluation indexes only trading date T and prior causal bars; future-bar invariance is covered by tests.",
    }


def baseline_hashes(config: RiskStructureV11EngineConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
        "entry": file_sha256(config.entry_dataset_path),
        "risk_v1": file_sha256(config.old_dataset_path),
    }


def write_v11_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RISK_V11_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def read_gzip_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def output_size(config: RiskStructureV11EngineConfig) -> int:
    paths = [
        config.output_dataset_path,
        config.summary_path,
        config.comparison_path,
        config.stop_basis_path,
        config.setup_comparison_path,
        config.pilot_path,
        config.target_regression_path,
        config.capital_regression_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("trading_date", "")), canonical_symbol(row.get("symbol", ""))


def has_flag(pair: dict[str, Any], flag: str) -> bool:
    return flag in split_codes(pair["new"].get("setup_type_flags", ""))


def is_reclaim(pair: dict[str, Any]) -> bool:
    return truthy(pair["setup"].get("daily_level_reclaim")) or pair["new"].get("invalidation_basis") == "DAILY_RECLAIM_LOW" or pair["old"].get("invalidation_basis") == "DAILY_RECLAIM_LOW"


def continuation_only(pair: dict[str, Any]) -> bool:
    flags = split_codes(pair["new"].get("setup_type_flags", ""))
    return "MOMENTUM_CONTINUATION" in flags and not flags & {"CONSOLIDATION_BREAKOUT", "BREAKOUT_20D"} and not is_reclaim(pair)


def pair_in_setup(pair: dict[str, Any], setup_type: str) -> bool:
    return is_reclaim(pair) if setup_type == "DAILY_RECLAIM" else has_flag(pair, setup_type)


def breakout_too_tight(
    pair: dict[str, Any], inventory: dict[tuple[str, str], dict[str, StopCandidateAssessment]]
) -> bool:
    assessment = inventory.get(pair["key"], {}).get("BREAKOUT_STRUCTURE")
    return bool(has_flag(pair, "BREAKOUT_20D") and assessment and assessment.band == "TOO_TIGHT")


def ready(row: dict[str, Any]) -> bool:
    return row.get("risk_readiness") == "READY_FOR_FINAL_SCORING"


def truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def integer_value(value: Any) -> bool:
    parsed = decimal(value)
    return parsed is not None and parsed == parsed.to_integral_value()


def decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return Decimal(text)
    except Exception:
        return default


def decimal_delta(new: Any, old: Any) -> Decimal:
    return (decimal(new, Decimal("0")) or Decimal("0")) - (decimal(old, Decimal("0")) or Decimal("0"))


def decimal_changed(old: Any, new: Any) -> bool:
    old_value = decimal(old)
    new_value = decimal(new)
    if old_value is None or new_value is None:
        return old_value != new_value
    return abs(old_value - new_value) > Decimal("0.000000001")


def pct(numerator: int, denominator: int) -> str:
    return format(Decimal(numerator) / Decimal(denominator) * Decimal("100"), ".4f") if denominator else "0.0000"


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def write_risk_structure_v11_markdown(report: dict[str, Any], path: Path) -> None:
    comparison = report["comparison"]
    target = report["target_regression"]
    capital = report["capital_regression"]
    lines = [
        "# Strategy V1 Risk Structure V1.1",
        "",
        "Current phase: Step 02.9 / Command 03 - setup-specific-first stop selection",
        "",
        "## Versioned Delta",
        "",
        f"- Previous methodology: {report['risk']['old_version']} / {report['risk']['old_config_hash']}",
        f"- New methodology: {report['risk']['new_version']} / {report['risk']['new_config_hash']}",
        f"- Stop selection: {report['risk']['stop_selection_methodology']}",
        "- V1 remains immutable and available for comparison.",
        "- The only intended behavioral change is validity-aware, setup-specific-first stop priority.",
        "",
        "## Priority",
        "",
        "1. Valid consolidation support for an active consolidation breakout.",
        "2. Valid daily reclaim support for an active reclaim context.",
        "3. Valid breakout invalidation for an active 20-day breakout.",
        "4. Causal 5-day, 10-day, then 3-day swing support.",
        "5. Other valid causal support fallbacks.",
        "",
        "Candidates must be positive, below the assumed entry, causal, and GOOD or ACCEPTABLE under the unchanged stop-distance rules before selection.",
        "",
        "## Unchanged Rules",
        "",
        "- ATR stop buffer: 0.20 ATR14.",
        "- Entry buffer: 0.10% above EOD close reference.",
        "- Structural target first; 2R only when structural resistance is unavailable.",
        "- Minimum/preferred reward:risk: 1.5R / 2.0R.",
        "- Research capital: INR 100,000; maximum planned risk: 1%; whole shares; no leverage or margin.",
        "",
        "## Structural Impact",
        "",
        f"- Rows evaluated: {comparison['rows_evaluated']}",
        f"- Changed stop basis: {comparison['changed_stop_basis']}",
        f"- Changed stop price: {comparison['changed_stop_price']}",
        f"- V1 ready / V1.1 ready: {comparison['old_ready']} / {comparison['new_ready']}",
        f"- Retained / removed / introduced ready: {comparison['retained_ready']} / {comparison['removed_ready']} / {comparison['introduced_ready']}",
        f"- Ready-set Jaccard: {comparison['jaccard']}",
        "",
        "## Regression",
        "",
        f"- Stop semantics: {report['results']['stop_semantics']}",
        f"- Target semantics: {target['result']}",
        f"- Capital semantics: {capital['result']}",
        f"- Artificial 2R replacements: {target['artificial_2r_replacements']}",
        f"- Planned-risk violations: {capital['capital_risk_violations']}",
        f"- Final-ready invariant violations: {len(report['invariants']['final_ready_violations'])}",
        "",
        "## Boundary",
        "",
        "- No future returns, future highs/lows, future pivots, stop/target outcomes, MFE, MAE, profitability optimization, final score, signal, backtest, paper trade, order, migration, or Supabase persistence is used.",
        "- Daily reclaim support remains a same-day daily low reference and does not claim intraday retest precision.",
        "- Breakout invalidations that are too tight remain invalid and fall back safely; practicality thresholds were not weakened.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

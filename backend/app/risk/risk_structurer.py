from __future__ import annotations

import csv
import gzip
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.regime.regime_config import MarketRegimeConfig
from app.risk.position_sizing import calculate_position_size
from app.risk.reward_risk import calculate_reward_risk
from app.risk.risk_config import RISK_STRUCTURE_VERSION, RiskStructureConfig, RiskStructureV11Config, resolve_risk_structure_dataset
from app.risk.stop_placement import RiskDailyBar, build_ohlc_index, calculate_stop_structure
from app.risk.target_planning import build_target_plan
from app.services.daily_feature_engine import adjusted_daily_files, date_from_adjusted_path, json_safe, read_csv_iter, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.entry_config import EntryEvaluationConfig
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip, split_codes
from app.strategy.setup_config import DailySetupEvaluationConfig

RISK_OUTPUT_FIELDS = [
    "trading_date",
    "symbol",
    "isin",
    "feature_version",
    "candidate_version",
    "candidate_config_hash",
    "setup_version",
    "setup_config_hash",
    "regime_version",
    "regime_config_hash",
    "entry_version",
    "entry_config_hash",
    "risk_version",
    "risk_config_hash",
    "risk_availability",
    "decision_use",
    "strategy_direction",
    "candidate_state",
    "setup_quality",
    "setup_type_flags",
    "entry_readiness",
    "risk_mode",
    "regime_state",
    "entry_price_basis",
    "execution_price_status",
    "entry_reference_price",
    "entry_buffer_pct",
    "assumed_entry_price",
    "technical_invalidation_level",
    "invalidation_basis",
    "invalidation_details",
    "atr_14",
    "atr_buffer_multiple",
    "atr_buffer_value",
    "stop_price",
    "stop_distance_abs",
    "stop_distance_pct",
    "stop_distance_atr_multiple",
    "stop_distance_band",
    "stop_quality",
    "stop_valid",
    "target_1_5r",
    "target_2r",
    "target_2_5r",
    "structural_target_price",
    "structural_target_basis",
    "structural_target_status",
    "selected_target_price",
    "selected_target_basis",
    "risk_per_share",
    "reward_per_share",
    "reward_risk_ratio",
    "reward_risk_status",
    "min_reward_risk",
    "preferred_reward_risk",
    "rr_valid",
    "research_capital",
    "max_risk_per_trade_pct",
    "risk_budget_rupees",
    "quantity_by_risk",
    "quantity_by_cash",
    "structured_quantity",
    "whole_share_status",
    "no_leverage_status",
    "position_notional",
    "capital_utilization_pct",
    "planned_rupee_risk",
    "planned_risk_pct",
    "capital_status",
    "capital_valid",
    "risk_structure_status",
    "risk_readiness",
    "rejection_reasons",
    "warning_flags",
    "final_strategy_score_status",
    "trade_signal_status",
]

DAILY_FUNNEL_FIELDS = [
    "trading_date",
    "entry_rows",
    "risk_evaluated_rows",
    "preview_rows",
    "valid_stop_rows",
    "rr_minimum_rows",
    "rr_preferred_rows",
    "capital_valid_rows",
    "ready_for_final_scoring_rows",
    "risk_rejected_rows",
]
STOP_BASIS_FIELDS = ["invalidation_basis", "rows", "pct", "valid_stop_rows", "ready_for_final_scoring_rows"]
REWARD_RISK_FIELDS = ["reward_risk_bucket", "rows", "pct", "ready_for_final_scoring_rows"]
CAPITAL_CONSTRAINT_FIELDS = ["constraint_or_warning", "rows", "pct"]
PRICE_BAND_FIELDS = ["price_band", "rows", "ready_for_final_scoring_rows", "ready_rate_pct", "median_structured_quantity"]
PILOT_VALIDATION_FIELDS = [
    "pilot_case",
    "symbol",
    "trading_date",
    "entry_readiness",
    "risk_mode",
    "check_name",
    "observed",
    "expected",
    "result",
    "explanation",
]
RISK_READINESS_STATES = (
    "NOT_EVALUATED",
    "INVALID_STRUCTURE",
    "RR_BELOW_MINIMUM",
    "CAPITAL_CONSTRAINED",
    "READY_FOR_FINAL_SCORING",
)
PROHIBITED_OUTCOME_FIELD_TOKENS = (
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
class RiskStructureEngineConfig:
    data_dir: Path
    risk_config: RiskStructureConfig
    entry_config: EntryEvaluationConfig = EntryEvaluationConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    regime_config: MarketRegimeConfig = MarketRegimeConfig()
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
    def output_dir(self) -> Path:
        return self.output_dataset_path.parent

    @property
    def output_dataset_path(self) -> Path:
        return resolve_risk_structure_dataset(self.data_dir, self.risk_config.risk_version)

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "risk_structure_summary.json"

    @property
    def daily_funnel_path(self) -> Path:
        return self.reports_dir / "risk_structure_daily_funnel.csv"

    @property
    def stop_basis_path(self) -> Path:
        return self.reports_dir / "risk_structure_stop_basis.csv"

    @property
    def reward_risk_path(self) -> Path:
        return self.reports_dir / "risk_structure_reward_risk.csv"

    @property
    def capital_constraints_path(self) -> Path:
        return self.reports_dir / "risk_structure_capital_constraints.csv"

    @property
    def price_bands_path(self) -> Path:
        return self.reports_dir / "risk_structure_price_bands.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "risk_structure_pilot_validation.csv"


def build_risk_structures(
    *,
    config: RiskStructureEngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if config.risk_config.risk_version != RISK_STRUCTURE_VERSION:
        raise ValueError("The legacy builder reproduces RISK_STRUCTURE_V1 only; use the current V1.1 builder for forward generation.")
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = upstream_hashes(config)

    if progress:
        progress("Loading progressed ENTRY_EVALUATION_V1 rows")
    entry_rows = load_entry_rows(config.entry_dataset_path, config.risk_config)
    keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in entry_rows}
    symbols = {symbol for _, symbol in keys}
    dates = sorted({date for date, _ in keys})

    if progress:
        progress("Joining setup, feature, and regime context")
    setup_lookup = load_lookup(config.setup_dataset_path, keys)
    feature_lookup = load_lookup(config.feature_dataset_path, keys)
    regime_lookup = load_regime_lookup(config.regime_dataset_path, set(dates))

    if progress:
        progress("Loading adjusted daily OHLC history for causal stop references")
    history = load_adjusted_history(
        adjusted_daily_dir=config.adjusted_daily_dir,
        symbols=symbols,
        through_date=max(dates) if dates else "",
    )
    patch_history_from_context(history=history, keys=keys, setup_lookup=setup_lookup, feature_lookup=feature_lookup)
    history_index = build_ohlc_index(history)

    if progress:
        progress("Evaluating stops, targets, reward:risk, and cash-only position risk")
    risk_rows = evaluate_risk_rows(
        entry_rows=entry_rows,
        setup_lookup=setup_lookup,
        feature_lookup=feature_lookup,
        regime_lookup=regime_lookup,
        history=history,
        history_index=history_index,
        config=config.risk_config,
    )

    daily_rows = daily_funnel(risk_rows)
    stop_basis_rows = stop_basis_report(risk_rows)
    reward_risk_rows = reward_risk_report(risk_rows)
    capital_rows = capital_constraints_report(risk_rows)
    price_rows = price_band_report(risk_rows)
    pilot_rows = select_pilot_rows(risk_rows)
    pilot_validation = validate_pilot_rows(pilot_rows, config.risk_config)

    write_csv(config.daily_funnel_path, daily_rows, DAILY_FUNNEL_FIELDS)
    write_csv(config.stop_basis_path, stop_basis_rows, STOP_BASIS_FIELDS)
    write_csv(config.reward_risk_path, reward_risk_rows, REWARD_RISK_FIELDS)
    write_csv(config.capital_constraints_path, capital_rows, CAPITAL_CONSTRAINT_FIELDS)
    write_csv(config.price_bands_path, price_rows, PRICE_BAND_FIELDS)
    write_csv(config.pilot_validation_path, pilot_validation["rows"], PILOT_VALIDATION_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_validation["passed"]:
        if progress:
            progress(f"Writing full {config.risk_config.risk_version} dataset")
        write_risk_rows(config.output_dataset_path, risk_rows)
        full_generation_completed = True

    hashes_after = upstream_hashes(config)
    baseline_unchanged = {key: hashes_before[key] == hashes_after[key] for key in hashes_before}
    input_versions = observed_versions(risk_rows, config)
    generation = generation_summary(risk_rows, full_generation_completed=full_generation_completed)
    prohibited_fields = prohibited_outcome_fields(RISK_OUTPUT_FIELDS)
    report = {
        "phase": "Step 02.9",
        "command": "Command 01",
        "generated_at": generated_at,
        "risk": {
            "risk_version": config.risk_config.risk_version,
            "risk_config_hash": config.risk_config.config_hash(),
            "risk_availability": config.risk_config.risk_availability,
            "decision_use": config.risk_config.decision_use,
            "strategy_direction": config.risk_config.strategy_direction,
            "instrument_type": config.risk_config.instrument_type,
        },
        "config_snapshot": config.risk_config.snapshot(),
        "inputs": {
            "versions": input_versions,
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
        },
        "methodology": {
            "boundary": "Risk structure only; no final score, signal, backtest, paper trade, live execution, orders, leverage, shorts, or Supabase writes.",
            "time_semantics": "DAILY_EOD rows use only information available through close T and produce NEXT_SESSION_RISK_CONTEXT.",
            "entry_reference": "EOD close reference plus deterministic long buffer; execution price remains unknown.",
            "stop": "Technical structure first, ATR-supported second. Causal lows use T and prior rows only.",
            "target": "Structural target when defensible, otherwise configurable R-multiple research reference.",
            "capital": "INR 100,000 research capital, 1.00% max risk per trade, whole shares, no leverage.",
        },
        "pilot": {
            "row_count": len(pilot_rows),
            "validation_passed": pilot_validation["passed"],
            "validation_rows": len(pilot_validation["rows"]),
            "symbols": sorted({row["symbol"] for row in pilot_rows}),
            "dates": sorted({row["trading_date"] for row in pilot_rows}),
        },
        "generation": generation,
        "reports": {
            "daily_funnel": daily_rows,
            "stop_basis": stop_basis_rows,
            "reward_risk": reward_risk_rows,
            "capital_constraints": capital_rows,
            "price_bands": price_rows,
        },
        "regression": {
            "daily_features_v1_unchanged": baseline_unchanged["feature"],
            "momentum_candidates_v1_unchanged": baseline_unchanged["candidate"],
            "daily_setup_evaluation_v1_unchanged": baseline_unchanged["setup"],
            "market_regime_v1_unchanged": baseline_unchanged["regime"],
            "entry_evaluation_v1_unchanged": baseline_unchanged["entry"],
            "candidate_config_hash_unchanged": input_versions["candidate_config_hash"] == config.candidate_config.config_hash(),
            "setup_config_hash_unchanged": input_versions["setup_config_hash"] == config.setup_config.config_hash(),
            "regime_config_hash_unchanged": input_versions["regime_config_hash"] == config.regime_config.config_hash(),
            "entry_config_hash_unchanged": input_versions["entry_config_hash"] == config.entry_config.config_hash(),
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
            "prohibited_output_fields": prohibited_fields,
        },
        "outputs": {
            "dataset": str(config.output_dataset_path),
            "summary_json": str(config.summary_path),
            "daily_funnel_csv": str(config.daily_funnel_path),
            "stop_basis_csv": str(config.stop_basis_path),
            "reward_risk_csv": str(config.reward_risk_path),
            "capital_constraints_csv": str(config.capital_constraints_path),
            "price_bands_csv": str(config.price_bands_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "markdown": "docs/strategy-v1-risk-structure.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "output_rows": len(risk_rows),
            "storage_size_bytes": output_size(config),
        },
    }
    report["ready_for_review"] = bool(
        full_generation_completed
        and pilot_validation["passed"]
        and all(baseline_unchanged.values())
        and report["regression"]["candidate_config_hash_unchanged"]
        and report["regression"]["setup_config_hash_unchanged"]
        and report["regression"]["regime_config_hash_unchanged"]
        and report["regression"]["entry_config_hash_unchanged"]
        and not prohibited_fields
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def evaluate_risk_rows(
    *,
    entry_rows: Sequence[dict[str, Any]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
    feature_lookup: dict[tuple[str, str], dict[str, str]],
    regime_lookup: dict[str, dict[str, str]],
    history: dict[str, Sequence[RiskDailyBar]],
    history_index: dict[tuple[str, str], int],
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> list[dict[str, Any]]:
    rows = []
    for entry_row in entry_rows:
        key = (str(entry_row.get("trading_date", "")), canonical_symbol(entry_row.get("symbol", "")))
        symbol = key[1]
        rows.append(
            evaluate_risk_row(
                entry_row=entry_row,
                setup_row=setup_lookup.get(key),
                feature_row=feature_lookup.get(key),
                regime_row=regime_lookup.get(key[0]),
                history=history.get(symbol, ()),
                history_index=history_index,
                config=config,
            )
        )
    return rows


def evaluate_risk_row(
    *,
    entry_row: dict[str, Any],
    setup_row: dict[str, Any] | None,
    feature_row: dict[str, Any] | None,
    regime_row: dict[str, Any] | None = None,
    history: Sequence[RiskDailyBar] = (),
    history_index: dict[tuple[str, str], int] | None = None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> dict[str, Any]:
    trading_date = str(entry_row.get("trading_date", ""))
    symbol = canonical_symbol(entry_row.get("symbol", ""))
    history_index = history_index or {(bar.trading_date, bar.symbol): index for index, bar in enumerate(history)}
    bar_index = history_index.get((trading_date, symbol))
    setup = setup_row or {}
    feature = feature_row or {}
    warnings: list[str] = []
    rejections: list[str] = []

    entry_readiness = str(entry_row.get("entry_readiness", "")).upper()
    if entry_readiness in config.full_evaluation_entry_readiness:
        risk_mode = "FULL_EVALUATION"
    elif entry_readiness in config.preview_entry_readiness:
        risk_mode = "PREVIEW_ONLY"
        warnings.append("RISK_PREVIEW_ONLY")
    else:
        risk_mode = "NOT_EVALUATED"
        rejections.append("ENTRY_READINESS_NOT_IN_SCOPE")

    entry_reference = entry_reference_price(setup, feature, entry_row)
    assumed_entry = assumed_long_entry_price(entry_reference, config)
    atr_14 = atr_14_value(setup, feature, entry_reference)
    stop = calculate_stop_structure(
        entry_row=entry_row,
        setup_row=setup,
        feature_row=feature,
        bars=history,
        bar_index=bar_index,
        assumed_entry_price=assumed_entry,
        atr_14=atr_14,
        config=config,
    )
    target = build_target_plan(
        setup_row=setup,
        feature_row=feature,
        assumed_entry_price=assumed_entry,
        risk_per_share=stop["stop_distance_abs"],
        config=config,
    )
    rr = calculate_reward_risk(
        assumed_entry_price=assumed_entry,
        stop_price=stop["stop_price"],
        selected_target_price=target["selected_target_price"],
        config=config,
    )
    sizing = calculate_position_size(
        assumed_entry_price=assumed_entry,
        risk_per_share=rr["risk_per_share"],
        config=config,
    )

    rejections.extend(stop["stop_rejection_reasons"])
    rejections.extend(target["target_rejection_reasons"])
    rejections.extend(rr["reward_risk_rejection_reasons"])
    rejections.extend(sizing["capital_rejection_reasons"])
    warnings.extend(stop["stop_warning_flags"])
    warnings.extend(target["target_warning_flags"])
    warnings.extend(rr["reward_risk_warning_flags"])
    warnings.extend(sizing["capital_warning_flags"])

    risk_structure_status, risk_readiness = risk_status(
        risk_mode=risk_mode,
        stop_valid=bool(stop["stop_valid"]),
        rr_valid=bool(rr["rr_valid"]),
        capital_valid=bool(sizing["capital_valid"]),
        missing_setup=setup_row is None,
        missing_price=entry_reference is None,
    )
    if risk_readiness == "INVALID_STRUCTURE" and not rejections:
        rejections.append("INVALID_STRUCTURE")
    elif risk_readiness == "RR_BELOW_MINIMUM" and not rejections:
        rejections.append("RR_BELOW_MINIMUM")
    elif risk_readiness == "CAPITAL_CONSTRAINED" and not rejections:
        rejections.append("CAPITAL_CONSTRAINED")

    row = {
        "trading_date": trading_date,
        "symbol": symbol,
        "isin": entry_row.get("isin", setup.get("isin", feature.get("isin", ""))),
        "feature_version": entry_row.get("feature_version", setup.get("feature_version", feature.get("feature_version", ""))),
        "candidate_version": entry_row.get("candidate_version", setup.get("candidate_version", "")),
        "candidate_config_hash": entry_row.get("candidate_config_hash", setup.get("candidate_config_hash", "")),
        "setup_version": entry_row.get("setup_version", setup.get("setup_version", "")),
        "setup_config_hash": entry_row.get("setup_config_hash", setup.get("setup_config_hash", "")),
        "regime_version": entry_row.get("regime_version", (regime_row or {}).get("regime_version", "")),
        "regime_config_hash": entry_row.get("regime_config_hash", (regime_row or {}).get("config_hash", "")),
        "entry_version": entry_row.get("entry_version", ""),
        "entry_config_hash": entry_row.get("entry_config_hash", ""),
        "risk_version": config.risk_version,
        "risk_config_hash": config.config_hash(),
        "risk_availability": config.risk_availability,
        "decision_use": config.decision_use,
        "strategy_direction": config.strategy_direction,
        "candidate_state": entry_row.get("candidate_state", setup.get("candidate_state", "")),
        "setup_quality": entry_row.get("setup_quality", setup.get("setup_quality", "")),
        "setup_type_flags": entry_row.get("setup_type_flags", setup.get("setup_type_flags", "")),
        "entry_readiness": entry_readiness,
        "risk_mode": risk_mode,
        "regime_state": entry_row.get("regime_state", (regime_row or {}).get("regime_state", "UNAVAILABLE")),
        "entry_price_basis": config.entry.entry_price_basis,
        "execution_price_status": config.entry.execution_price_status,
        "entry_reference_price": entry_reference,
        "entry_buffer_pct": config.entry.long_entry_buffer_pct,
        "assumed_entry_price": assumed_entry,
        "technical_invalidation_level": stop["technical_invalidation_level"],
        "invalidation_basis": stop["invalidation_basis"],
        "invalidation_details": stop["invalidation_details"],
        "atr_14": atr_14,
        "atr_buffer_multiple": config.stop.atr_buffer_multiple,
        "atr_buffer_value": stop["atr_buffer_value"],
        "stop_price": stop["stop_price"],
        "stop_distance_abs": stop["stop_distance_abs"],
        "stop_distance_pct": stop["stop_distance_pct"],
        "stop_distance_atr_multiple": stop["stop_distance_atr_multiple"],
        "stop_distance_band": stop["stop_distance_band"],
        "stop_quality": stop["stop_quality"],
        "stop_valid": stop["stop_valid"],
        "target_1_5r": target["target_1_5r"],
        "target_2r": target["target_2r"],
        "target_2_5r": target["target_2_5r"],
        "structural_target_price": target["structural_target_price"],
        "structural_target_basis": target["structural_target_basis"],
        "structural_target_status": target["structural_target_status"],
        "selected_target_price": target["selected_target_price"],
        "selected_target_basis": target["selected_target_basis"],
        "risk_per_share": rr["risk_per_share"],
        "reward_per_share": rr["reward_per_share"],
        "reward_risk_ratio": rr["reward_risk_ratio"],
        "reward_risk_status": rr["reward_risk_status"],
        "min_reward_risk": config.target.minimum_reward_risk,
        "preferred_reward_risk": config.target.preferred_reward_risk,
        "rr_valid": rr["rr_valid"],
        "research_capital": sizing["research_capital"],
        "max_risk_per_trade_pct": sizing["max_risk_per_trade_pct"],
        "risk_budget_rupees": sizing["risk_budget_rupees"],
        "quantity_by_risk": sizing["quantity_by_risk"],
        "quantity_by_cash": sizing["quantity_by_cash"],
        "structured_quantity": sizing["structured_quantity"],
        "whole_share_status": sizing["whole_share_status"],
        "no_leverage_status": sizing["no_leverage_status"],
        "position_notional": sizing["position_notional"],
        "capital_utilization_pct": sizing["capital_utilization_pct"],
        "planned_rupee_risk": sizing["planned_rupee_risk"],
        "planned_risk_pct": sizing["planned_risk_pct"],
        "capital_status": sizing["capital_status"],
        "capital_valid": sizing["capital_valid"],
        "risk_structure_status": risk_structure_status,
        "risk_readiness": risk_readiness,
        "rejection_reasons": join_codes(rejections),
        "warning_flags": join_codes(warnings),
        "final_strategy_score_status": config.final_strategy_score_status,
        "trade_signal_status": config.trade_signal_status,
    }
    stop_selection_methodology = getattr(config, "stop_selection_methodology", "")
    if stop_selection_methodology:
        row.update(
            {
                "previous_risk_version": getattr(config, "previous_risk_version", ""),
                "previous_risk_config_hash": getattr(config, "previous_risk_config_hash", ""),
                "stop_selection_methodology": stop_selection_methodology,
                "selected_stop_priority_reason": stop["selected_stop_priority_reason"],
                "fallback_stop_used": stop["fallback_stop_used"],
                "fallback_reason": stop["fallback_reason"],
                "setup_specific_stop_available": stop["setup_specific_stop_available"],
                "setup_specific_stop_valid": stop["setup_specific_stop_valid"],
            }
        )
    return row


def risk_status(
    *,
    risk_mode: str,
    stop_valid: bool,
    rr_valid: bool,
    capital_valid: bool,
    missing_setup: bool,
    missing_price: bool,
) -> tuple[str, str]:
    if risk_mode != "FULL_EVALUATION":
        return ("PARTIAL" if risk_mode == "PREVIEW_ONLY" else "UNAVAILABLE", "NOT_EVALUATED")
    if missing_setup or missing_price:
        return "UNAVAILABLE", "INVALID_STRUCTURE"
    if not stop_valid:
        return "BLOCKED", "INVALID_STRUCTURE"
    if not rr_valid:
        return "BLOCKED", "RR_BELOW_MINIMUM"
    if not capital_valid:
        return "BLOCKED", "CAPITAL_CONSTRAINED"
    return "READY", "READY_FOR_FINAL_SCORING"


def load_entry_rows(path: Path, config: RiskStructureConfig) -> list[dict[str, str]]:
    allowed = set(config.full_evaluation_entry_readiness) | set(config.preview_entry_readiness)
    with open_csv_maybe_gzip(path) as file:
        return [
            row
            for row in csv.DictReader(file)
            if str(row.get("entry_readiness", "")).upper() in allowed
        ]


def load_lookup(path: Path, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            key = (str(row.get("trading_date", "")), canonical_symbol(row.get("symbol", "")))
            if key in keys:
                lookup[key] = row
    return lookup


def load_regime_lookup(path: Path, dates: set[str]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            trading_date = str(row.get("trading_date", ""))
            if trading_date in dates:
                lookup[trading_date] = row
    return lookup


def load_adjusted_history(
    *,
    adjusted_daily_dir: Path,
    symbols: set[str],
    through_date: str,
) -> dict[str, list[RiskDailyBar]]:
    history: dict[str, list[RiskDailyBar]] = defaultdict(list)
    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None:
            continue
        date_text = trading_date.isoformat()
        if through_date and date_text > through_date:
            continue
        for row in read_csv_iter(path):
            if row.get("series", "EQ") != "EQ":
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            if symbol not in symbols:
                continue
            bar = risk_bar_from_row(row)
            if bar is not None:
                history[symbol].append(bar)
    for symbol in history:
        history[symbol] = sorted(history[symbol], key=lambda bar: bar.trading_date)
    return dict(history)


def patch_history_from_context(
    *,
    history: dict[str, list[RiskDailyBar]],
    keys: set[tuple[str, str]],
    setup_lookup: dict[tuple[str, str], dict[str, str]],
    feature_lookup: dict[tuple[str, str], dict[str, str]],
) -> None:
    for key in keys:
        trading_date, symbol = key
        if any(bar.trading_date == trading_date for bar in history.get(symbol, [])):
            continue
        row = setup_lookup.get(key) or feature_lookup.get(key)
        bar = risk_bar_from_row(row or {})
        if bar is not None:
            history.setdefault(symbol, []).append(bar)
    for symbol in history:
        history[symbol] = sorted(history[symbol], key=lambda bar: bar.trading_date)


def risk_bar_from_row(row: dict[str, Any]) -> RiskDailyBar | None:
    trading_date = str(row.get("trading_date", ""))
    symbol = canonical_symbol(row.get("symbol", ""))
    open_value = parse_decimal(row.get("adjusted_open") or row.get("open") or row.get("raw_open"))
    high_value = parse_decimal(row.get("adjusted_high") or row.get("high") or row.get("raw_high"))
    low_value = parse_decimal(row.get("adjusted_low") or row.get("low") or row.get("raw_low"))
    close_value = parse_decimal(row.get("adjusted_close") or row.get("close") or row.get("price") or row.get("raw_close"))
    if not trading_date or not symbol or None in {open_value, high_value, low_value, close_value}:
        return None
    return RiskDailyBar(trading_date, symbol, open_value, high_value, low_value, close_value)


def entry_reference_price(*rows: dict[str, Any]) -> Decimal | None:
    for row in rows:
        value = parse_decimal(row.get("adjusted_close") or row.get("price") or row.get("close"))
        if value is not None and value > 0:
            return value
    return None


def assumed_long_entry_price(entry_reference: Decimal | None, config: RiskStructureConfig) -> Decimal | None:
    if entry_reference is None or entry_reference <= 0:
        return None
    return entry_reference * (Decimal("1") + config.entry.long_entry_buffer_pct / Decimal("100"))


def atr_14_value(setup_row: dict[str, Any], feature_row: dict[str, Any], entry_reference: Decimal | None) -> Decimal | None:
    direct = parse_decimal(feature_row.get("atr_14") or setup_row.get("atr_14"))
    if direct is not None and direct > 0:
        return direct
    pct = parse_decimal(setup_row.get("atr_percent_14") or feature_row.get("atr_percent_14"))
    if pct is not None and pct > 0 and entry_reference is not None:
        return entry_reference * pct
    return None


def daily_funnel(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for trading_date, group in group_rows(rows, "trading_date").items():
        total = len(group)
        output.append(
            {
                "trading_date": trading_date,
                "entry_rows": total,
                "risk_evaluated_rows": sum(1 for row in group if row["risk_mode"] == "FULL_EVALUATION"),
                "preview_rows": sum(1 for row in group if row["risk_mode"] == "PREVIEW_ONLY"),
                "valid_stop_rows": sum(1 for row in group if truthy(row["stop_valid"])),
                "rr_minimum_rows": sum(1 for row in group if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("1.50")),
                "rr_preferred_rows": sum(1 for row in group if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("2.00")),
                "capital_valid_rows": sum(1 for row in group if truthy(row["capital_valid"])),
                "ready_for_final_scoring_rows": sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING"),
                "risk_rejected_rows": sum(1 for row in group if row["risk_readiness"] in {"INVALID_STRUCTURE", "RR_BELOW_MINIMUM", "CAPITAL_CONSTRAINED"}),
            }
        )
    return sorted(output, key=lambda row: row["trading_date"])


def stop_basis_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(rows)
    output = []
    for basis, group in sorted(group_rows(rows, "invalidation_basis").items()):
        output.append(
            {
                "invalidation_basis": basis,
                "rows": len(group),
                "pct": pct(len(group), total),
                "valid_stop_rows": sum(1 for row in group if truthy(row["stop_valid"])),
                "ready_for_final_scoring_rows": sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING"),
            }
        )
    return output


def reward_risk_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = group_rows(rows, "reward_risk_status")
    total = len(rows)
    return [
        {
            "reward_risk_bucket": bucket,
            "rows": len(group),
            "pct": pct(len(group), total),
            "ready_for_final_scoring_rows": sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING"),
        }
        for bucket, group in sorted(buckets.items())
    ]


def capital_constraints_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for code in split_codes(row.get("rejection_reasons", "")) | split_codes(row.get("warning_flags", "")):
            if code in {
                "LOW_CAPITAL_UTILIZATION",
                "SINGLE_SHARE_ONLY",
                "AFFORDABILITY_LIMITED",
                "RISK_LIMITED_QUANTITY",
                "AFFORDABILITY_FAIL",
                "RISK_TOO_LARGE_FOR_CAPITAL",
                "STRUCTURED_QUANTITY_ZERO",
                "PLANNED_RISK_EXCEEDS_BUDGET",
            }:
                counter[code] += 1
    return [
        {"constraint_or_warning": code, "rows": count, "pct": pct(count, len(rows))}
        for code, count in counter.most_common()
    ]


def price_band_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[price_band(parse_decimal(row.get("assumed_entry_price")))].append(row)
    output = []
    for band, group in sorted(grouped.items()):
        ready = sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING")
        output.append(
            {
                "price_band": band,
                "rows": len(group),
                "ready_for_final_scoring_rows": ready,
                "ready_rate_pct": pct(ready, len(group)),
                "median_structured_quantity": median_decimal(parse_decimal(row.get("structured_quantity")) for row in group),
            }
        )
    return output


def select_pilot_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    requested_symbols = {"RELIANCE", "TCS", "HDFCBANK", "INFY", "SUNPHARMA", "ABB", "BLUEDART"}
    for symbol in sorted(requested_symbols):
        add_pilot_row(selected, seen, latest_row_for_symbol(rows, symbol))
    for state in RISK_READINESS_STATES:
        add_pilot_row(selected, seen, first_row(rows, lambda row, state=state: row["risk_readiness"] == state))
    for code in ("STRUCTURAL_TARGET_UNAVAILABLE", "RR_BELOW_MINIMUM", "AFFORDABILITY_FAIL", "LOW_CAPITAL_UTILIZATION"):
        add_pilot_row(selected, seen, first_row(rows, lambda row, code=code: code in split_codes(row.get("rejection_reasons", "")) or code in split_codes(row.get("warning_flags", ""))))
    return selected[:25]


def add_pilot_row(selected: list[dict[str, Any]], seen: set[tuple[str, str]], row: dict[str, Any] | None) -> None:
    if row is None:
        return
    key = (row["trading_date"], row["symbol"])
    if key in seen:
        return
    selected.append(row | {"pilot_case": f"{row['symbol']}_{row['trading_date']}"})
    seen.add(key)


def latest_row_for_symbol(rows: Sequence[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    normalized = canonical_symbol(symbol)
    matches = [row for row in rows if row["symbol"] == normalized]
    return max(matches, key=lambda row: row["trading_date"]) if matches else None


def first_row(rows: Sequence[dict[str, Any]], predicate: Any) -> dict[str, Any] | None:
    return next((row for row in rows if predicate(row)), None)


def validate_pilot_rows(pilot_rows: Sequence[dict[str, Any]], config: RiskStructureConfig) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    states = {row["risk_readiness"] for row in pilot_rows}
    if not pilot_rows:
        rows.append(pilot_validation_row({}, check_name="pilot_rows_present", observed=0, expected=">=1", passed=False, explanation="Pilot must include at least one risk row."))
    for expected in ("READY_FOR_FINAL_SCORING", "INVALID_STRUCTURE"):
        rows.append(pilot_validation_row({}, check_name=f"state_coverage_{expected.lower()}", observed=expected in states, expected=True, passed=expected in states or not pilot_rows, explanation="Pilot includes representative readiness coverage when present."))
    for row in pilot_rows:
        stop_valid = truthy(row["stop_valid"])
        if stop_valid:
            rows.append(pilot_validation_row(row, check_name="stop_below_entry", observed=f"{row['stop_price']} < {row['assumed_entry_price']}", expected=True, passed=decimal_or_zero(row["stop_price"]) < decimal_or_zero(row["assumed_entry_price"]), explanation="Long-only stop must sit below assumed entry."))
        rows.append(pilot_validation_row(row, check_name="target_references_present", observed=f"{row['target_1_5r']}/{row['target_2r']}/{row['target_2_5r']}", expected="1.5R/2R/2.5R", passed=all(str(row.get(field, "")) for field in ("target_1_5r", "target_2r", "target_2_5r")) or not stop_valid, explanation="Reference R-multiple targets are deterministic research references."))
        if row["risk_readiness"] == "READY_FOR_FINAL_SCORING":
            rows.append(pilot_validation_row(row, check_name="minimum_reward_risk", observed=row["reward_risk_ratio"], expected=f">={config.target.minimum_reward_risk}", passed=decimal_or_zero(row["reward_risk_ratio"]) >= config.target.minimum_reward_risk, explanation="Ready rows meet minimum reward:risk."))
            rows.append(pilot_validation_row(row, check_name="planned_risk_cap", observed=row["planned_risk_pct"], expected=f"<={config.capital.max_risk_per_trade_pct}", passed=decimal_or_zero(row["planned_risk_pct"]) <= config.capital.max_risk_per_trade_pct, explanation="Position sizing respects the per-trade risk cap after whole-share rounding."))
        if row["risk_mode"] == "PREVIEW_ONLY":
            rows.append(pilot_validation_row(row, check_name="preview_not_ready", observed=row["risk_readiness"], expected="NOT_EVALUATED", passed=row["risk_readiness"] == "NOT_EVALUATED", explanation="Conditional inputs are previewed without promotion to final scoring."))
        rows.append(pilot_validation_row(row, check_name="future_status_placeholders", observed=f"{row['final_strategy_score_status']}/{row['trade_signal_status']}", expected="NOT_IMPLEMENTED/NOT_GENERATED", passed=row["final_strategy_score_status"] == "NOT_IMPLEMENTED" and row["trade_signal_status"] == "NOT_GENERATED", explanation="Risk foundation does not create a final score or trade signal."))
        rows.append(pilot_validation_row(row, check_name="no_leverage", observed=row["no_leverage_status"], expected="NO_LEVERAGE", passed=row["no_leverage_status"] == "NO_LEVERAGE", explanation="Cash affordability caps quantity; leverage is not used."))
    return {"passed": all(row["result"] == "PASS" for row in rows), "rows": rows}


def pilot_validation_row(
    row: dict[str, Any],
    *,
    check_name: str,
    observed: Any,
    expected: Any,
    passed: bool,
    explanation: str,
) -> dict[str, Any]:
    return {
        "pilot_case": row.get("pilot_case", ""),
        "symbol": row.get("symbol", ""),
        "trading_date": row.get("trading_date", ""),
        "entry_readiness": row.get("entry_readiness", ""),
        "risk_mode": row.get("risk_mode", ""),
        "check_name": check_name,
        "observed": observed,
        "expected": expected,
        "result": "PASS" if passed else "FAIL",
        "explanation": explanation,
    }


def generation_summary(rows: Sequence[dict[str, Any]], *, full_generation_completed: bool) -> dict[str, Any]:
    total = len(rows)
    valid_stop = sum(1 for row in rows if truthy(row["stop_valid"]))
    rr_15 = sum(1 for row in rows if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("1.50"))
    rr_20 = sum(1 for row in rows if decimal_or_zero(row.get("reward_risk_ratio")) >= Decimal("2.00"))
    capital_valid = sum(1 for row in rows if truthy(row["capital_valid"]))
    ready = sum(1 for row in rows if row["risk_readiness"] == "READY_FOR_FINAL_SCORING")
    rejected = sum(1 for row in rows if row["risk_readiness"] in {"INVALID_STRUCTURE", "RR_BELOW_MINIMUM", "CAPITAL_CONSTRAINED"})
    rr_values = [decimal for row in rows if (decimal := parse_decimal(row.get("reward_risk_ratio"))) is not None]
    return {
        "full_generation_completed": full_generation_completed,
        "total_rows_risk_evaluated": total,
        "risk_mode_counts": distribution(Counter(row["risk_mode"] for row in rows), total),
        "risk_structure_status_counts": distribution(Counter(row["risk_structure_status"] for row in rows), total),
        "risk_readiness_counts": readiness_distribution(Counter(row["risk_readiness"] for row in rows), total),
        "valid_stop_count": valid_stop,
        "valid_stop_rate_pct": pct(valid_stop, total),
        "rr_1_5_count": rr_15,
        "rr_1_5_rate_pct": pct(rr_15, total),
        "rr_2_0_count": rr_20,
        "rr_2_0_rate_pct": pct(rr_20, total),
        "capital_valid_count": capital_valid,
        "capital_valid_rate_pct": pct(capital_valid, total),
        "ready_for_final_scoring_count": ready,
        "ready_for_final_scoring_rate_pct": pct(ready, total),
        "risk_rejected_count": rejected,
        "stop_basis_distribution": distribution(Counter(row["invalidation_basis"] for row in rows), total),
        "stop_distance_pct_distribution": numeric_distribution([decimal for row in rows if (decimal := parse_decimal(row.get("stop_distance_pct"))) is not None]),
        "stop_distance_atr_distribution": numeric_distribution([decimal for row in rows if (decimal := parse_decimal(row.get("stop_distance_atr_multiple"))) is not None]),
        "reward_risk_distribution": distribution(Counter(row["reward_risk_status"] for row in rows), total),
        "reward_risk_numeric_distribution": numeric_distribution(rr_values),
        "median_reward_risk": median_decimal(rr_values),
        "mean_reward_risk": mean_decimal(rr_values),
        "median_structured_quantity": median_decimal(parse_decimal(row.get("structured_quantity")) for row in rows),
        "median_position_notional": median_decimal(parse_decimal(row.get("position_notional")) for row in rows),
        "median_capital_utilization_pct": median_decimal(parse_decimal(row.get("capital_utilization_pct")) for row in rows),
        "median_planned_rupee_risk": median_decimal(parse_decimal(row.get("planned_rupee_risk")) for row in rows),
        "median_planned_risk_pct": median_decimal(parse_decimal(row.get("planned_risk_pct")) for row in rows),
        "single_share_count": sum(1 for row in rows if "SINGLE_SHARE_ONLY" in split_codes(row.get("warning_flags", ""))),
        "affordability_failures": sum(1 for row in rows if "AFFORDABILITY_FAIL" in split_codes(row.get("rejection_reasons", ""))),
        "risk_too_large_failures": sum(1 for row in rows if "RISK_TOO_LARGE_FOR_CAPITAL" in split_codes(row.get("rejection_reasons", ""))),
        "regime_readiness": regime_readiness(rows),
        "most_common_rejection_reasons": top_reason_codes(rows, "rejection_reasons"),
        "most_common_warnings": top_reason_codes(rows, "warning_flags"),
    }


def write_strategy_v1_risk_structure_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    lines = [
        "# Strategy V1 Risk Structure",
        "",
        "Current phase: Step 02.9 / Command 01 - Stop, target, reward:risk, and position-risk foundation",
        "",
        "## Boundary",
        "",
        "- RISK_STRUCTURE_V1 evaluates only deterministic structure for rows handed off by ENTRY_EVALUATION_V1.",
        "- The layer is DAILY_EOD and produces NEXT_SESSION_RISK_CONTEXT.",
        "- Entry execution price remains unknown; the engine uses EOD close plus a deterministic long buffer.",
        "- No final score, buy/sell signal, backtest, paper trade, live order, short, leverage, margin, remote migration, or Supabase write is implemented.",
        "",
        "## Version",
        "",
        f"- Risk methodology/config hash: {report['risk']['risk_version']} / {report['risk']['risk_config_hash']}",
        f"- Entry: {report['inputs']['versions']['entry_version']} / {report['inputs']['versions']['entry_config_hash']}",
        f"- Setup: {report['inputs']['versions']['setup_version']} / {report['inputs']['versions']['setup_config_hash']}",
        f"- Regime: {report['inputs']['versions']['regime_version']} / {report['inputs']['versions']['regime_config_hash']}",
        "",
        "## Methodology",
        "",
        "- Capital baseline is INR 100,000 with maximum 1.00% risk per trade.",
        "- Stops are selected from technical invalidation levels first, then buffered by 0.20 ATR.",
        "- Causal swing lows use current session T and prior sessions only; no future pivot confirmation is used.",
        "- Structural targets are used only when available. Otherwise the default research reference is 2R.",
        "- Minimum reward:risk is 1.5R and preferred reward:risk is 2.0R.",
        "- Quantity is the lower of risk-budget quantity and cash-affordability quantity, whole shares only.",
        "",
        "## Results",
        "",
        f"- Full generation completed: {generation['full_generation_completed']}",
        f"- Total rows risk evaluated: {generation['total_rows_risk_evaluated']}",
        f"- Valid stops: {generation['valid_stop_count']} ({generation['valid_stop_rate_pct']}%)",
        f"- R:R >= 1.5: {generation['rr_1_5_count']} ({generation['rr_1_5_rate_pct']}%)",
        f"- R:R >= 2.0: {generation['rr_2_0_count']} ({generation['rr_2_0_rate_pct']}%)",
        f"- Capital valid: {generation['capital_valid_count']} ({generation['capital_valid_rate_pct']}%)",
        f"- Ready for final scoring: {generation['ready_for_final_scoring_count']} ({generation['ready_for_final_scoring_rate_pct']}%)",
        f"- Rejected by risk layer: {generation['risk_rejected_count']}",
        "",
        "## Integrity",
        "",
        f"- DAILY_FEATURES_V1 unchanged: {report['regression']['daily_features_v1_unchanged']}",
        f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['regression']['momentum_candidates_v1_unchanged']}",
        f"- DAILY_SETUP_EVALUATION_V1 unchanged: {report['regression']['daily_setup_evaluation_v1_unchanged']}",
        f"- MARKET_REGIME_V1 unchanged: {report['regression']['market_regime_v1_unchanged']}",
        f"- ENTRY_EVALUATION_V1 unchanged: {report['regression']['entry_evaluation_v1_unchanged']}",
        "- ZERO orders were placed.",
        "- ZERO remote migrations were applied.",
        "- ZERO records were persisted to Supabase.",
        "",
        "## Known Limitations",
        "",
        "- Structural resistance is limited to upstream same-day historical level references.",
        "- Target, stop, and position values are research references, not executable order instructions.",
        "- No portfolio allocator is implemented despite a preferred maximum concurrent position count.",
        "- No slippage, brokerage, gap-open, or intraday fill model is implemented.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def upstream_hashes(config: RiskStructureEngineConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
        "entry": file_sha256(config.entry_dataset_path),
    }


def observed_versions(rows: Sequence[dict[str, Any]], config: RiskStructureEngineConfig) -> dict[str, str]:
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
        "risk_version": config.risk_config.risk_version,
        "risk_config_hash": config.risk_config.config_hash(),
    }


def write_risk_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RISK_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def prohibited_outcome_fields(fields: Sequence[str]) -> list[str]:
    flagged = []
    for field in fields:
        lower = field.lower()
        if any(token in lower for token in PROHIBITED_OUTCOME_FIELD_TOKENS):
            flagged.append(field)
    return flagged


def group_rows(rows: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, ""))].append(row)
    return dict(grouped)


def regime_readiness(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped = group_rows(rows, "regime_state")
    return {
        state or "UNAVAILABLE": {
            "rows": len(group),
            "ready_for_final_scoring": sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING"),
            "ready_rate_pct": pct(sum(1 for row in group if row["risk_readiness"] == "READY_FOR_FINAL_SCORING"), len(group)),
        }
        for state, group in sorted(grouped.items())
    }


def readiness_distribution(counter: Counter[str], total: int) -> dict[str, Any]:
    return {state: {"count": counter[state], "pct": pct(counter[state], total)} for state in RISK_READINESS_STATES}


def distribution(counter: Counter[str], total: int, *, limit: int | None = None) -> dict[str, Any]:
    pairs = counter.most_common(limit)
    return {key: {"count": count, "pct": pct(count, total)} for key, count in pairs}


def numeric_distribution(values: Iterable[Decimal | None]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"min": "", "p10": "", "p25": "", "median": "", "mean": "", "p75": "", "p90": "", "p95": "", "p99": "", "max": ""}
    return {
        "min": clean[0],
        "p10": decimal_quantile(clean, Decimal("0.10")),
        "p25": decimal_quantile(clean, Decimal("0.25")),
        "median": median_decimal(clean),
        "mean": mean_decimal(clean),
        "p75": decimal_quantile(clean, Decimal("0.75")),
        "p90": decimal_quantile(clean, Decimal("0.90")),
        "p95": decimal_quantile(clean, Decimal("0.95")),
        "p99": decimal_quantile(clean, Decimal("0.99")),
        "max": clean[-1],
    }


def decimal_quantile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


def median_decimal(values: Iterable[Decimal | None]) -> Decimal | str:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return ""
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / Decimal("2")


def mean_decimal(values: Iterable[Decimal | None]) -> Decimal | str:
    clean = [value for value in values if value is not None]
    if not clean:
        return ""
    return Decimal(str(statistics.mean(clean)))


def top_reason_codes(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for row in rows:
        for code in split_codes(row.get(field, "")):
            counter[code] += 1
    return distribution(counter, len(rows), limit=20)


def price_band(price: Decimal | None) -> str:
    if price is None:
        return "UNAVAILABLE"
    if price < Decimal("250"):
        return "LT_250"
    if price < Decimal("500"):
        return "250_TO_500"
    if price < Decimal("1000"):
        return "500_TO_1000"
    if price < Decimal("2500"):
        return "1000_TO_2500"
    if price < Decimal("5000"):
        return "2500_TO_5000"
    if price < Decimal("7000"):
        return "5000_TO_7000"
    return "GE_7000"


def decimal_or_zero(value: Any) -> Decimal:
    return parse_decimal(value) or Decimal("0")


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


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def round_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.0001")), "f")


def join_codes(values: Sequence[str]) -> str:
    output = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return ";".join(output)


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def observed_single_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def output_size(config: RiskStructureEngineConfig) -> int:
    paths = [
        config.output_dataset_path,
        config.summary_path,
        config.daily_funnel_path,
        config.stop_basis_path,
        config.reward_risk_path,
        config.capital_constraints_path,
        config.price_bands_path,
        config.pilot_validation_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())

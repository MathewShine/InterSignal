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
from typing import Any, Callable, Sequence

from app.regime.regime_config import MarketRegimeConfig
from app.services.daily_feature_engine import json_safe, write_csv, write_json
from app.services.nifty500_membership import canonical_symbol
from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.entry_config import ENTRY_EVALUATION_VERSION, EntryEvaluationConfig
from app.strategy.entry_gates import evaluate_entry_gates, neutral_strict_requirements_met, regime_permission
from app.strategy.entry_penalties import (
    blocking_penalty_present,
    build_entry_penalties,
    max_penalty_severity,
    penalty_codes,
)
from app.strategy.momentum_candidates import file_sha256, open_csv_maybe_gzip, split_codes
from app.strategy.setup_config import DailySetupEvaluationConfig

ENTRY_OUTPUT_FIELDS = [
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
    "entry_availability",
    "decision_use",
    "candidate_state",
    "emerging_eligible",
    "confirmed_eligible",
    "both_eligible",
    "candidate_group",
    "setup_status",
    "setup_eligible",
    "setup_quality",
    "setup_type_flags",
    "breakout_state",
    "acceptance_state",
    "candle_quality",
    "volume_confirmation",
    "extension_risk",
    "benchmark_rs_context",
    "consolidation_state",
    "consolidation_quality",
    "false_breakout_flags",
    "overhead_resistance",
    "daily_level_reclaim",
    "regime_state",
    "regime_score_normalized",
    "regime_confidence_score",
    "regime_confidence_state",
    "regime_available_weight_pct",
    "regime_permission",
    "research_gate_passed",
    "candidate_gate_passed",
    "setup_gate_passed",
    "regime_gate_passed",
    "extension_gate_passed",
    "technical_rejection_gate_passed",
    "gate_details",
    "entry_evaluation_status",
    "entry_readiness",
    "exceptional_long_candidate",
    "exceptional_long_status",
    "exceptional_long_reasons",
    "entry_evidence_strength",
    "entry_context_rank",
    "entry_context_percentile",
    "positive_evidence",
    "neutral_evidence",
    "warning_evidence",
    "blocking_evidence",
    "penalty_codes",
    "max_penalty_severity",
    "blocking_penalty_present",
    "candidate_strength_context",
    "setup_strength_context",
    "breakout_context",
    "volume_context",
    "benchmark_rs_entry_context",
    "regime_context",
    "extension_context",
    "candle_context",
    "consolidation_context",
    "false_breakout_context",
    "reclaim_context",
    "overhead_resistance_context",
    "stock_sector_rs_status",
    "catalyst_context_status",
    "risk_reward_status",
    "score_architecture_status",
]

DAILY_FUNNEL_FIELDS = [
    "trading_date",
    "candidate_rows",
    "setup_eligible_rows",
    "entry_evaluated_rows",
    "not_ready",
    "watch",
    "conditionally_ready",
    "ready_for_risk_evaluation",
    "exceptional_long_review",
    "candidate_to_setup_conversion_pct",
    "setup_to_ready_or_conditional_pct",
    "candidate_to_ready_or_conditional_pct",
]

REGIME_FUNNEL_FIELDS = [
    "regime_state",
    "evaluated_rows",
    "setup_eligible_rows",
    "not_ready",
    "watch",
    "conditionally_ready",
    "ready_for_risk_evaluation",
    "exceptional_long_review",
    "ready_or_conditional_pct",
    "blocked_or_not_ready_pct",
]

PENALTY_REPORT_FIELDS = ["section", "penalty_code", "severity", "blocking", "count", "pct", "details"]
PILOT_VALIDATION_FIELDS = [
    "pilot_case",
    "symbol",
    "trading_date",
    "regime_state",
    "candidate_state",
    "setup_quality",
    "entry_readiness",
    "check_name",
    "observed",
    "expected",
    "result",
    "explanation",
]
EXCEPTIONAL_LONG_FIELDS = [
    "section",
    "trading_date",
    "symbol",
    "regime_state",
    "candidate_state",
    "setup_quality",
    "exceptional_long_status",
    "entry_readiness",
    "reason_codes",
    "count",
    "rate_pct",
]

READINESS_STATES = (
    "NOT_READY",
    "WATCH",
    "CONDITIONALLY_READY",
    "READY_FOR_RISK_EVALUATION",
    "EXCEPTIONAL_LONG_REVIEW",
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
class EntryEvaluationEngineConfig:
    data_dir: Path
    entry_config: EntryEvaluationConfig = EntryEvaluationConfig()
    candidate_config: MomentumCandidateConfig = MomentumCandidateConfig()
    setup_config: DailySetupEvaluationConfig = DailySetupEvaluationConfig()
    regime_config: MarketRegimeConfig = MarketRegimeConfig()
    full_generation: bool = True

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
    def feature_dataset_path(self) -> Path:
        return self.data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "research" / "entry_evaluations" / "daily" / "v1"

    @property
    def output_dataset_path(self) -> Path:
        return self.output_dir / "entry_evaluations_v1.csv.gz"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def summary_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_summary.json"

    @property
    def daily_funnel_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_daily_funnel.csv"

    @property
    def regime_funnel_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_regime_funnel.csv"

    @property
    def penalties_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_penalties.csv"

    @property
    def pilot_validation_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_pilot_validation.csv"

    @property
    def exceptional_longs_path(self) -> Path:
        return self.reports_dir / "entry_evaluation_exceptional_longs.csv"


def build_entry_evaluations(
    *,
    config: EntryEvaluationEngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    hashes_before = upstream_hashes(config)

    if progress:
        progress("Loading DAILY_SETUP_EVALUATION_V1 scope rows")
    setup_rows = load_setup_rows(config.setup_dataset_path)
    setup_keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in setup_rows}

    if progress:
        progress("Joining same-day Momentum Candidate and Market Regime rows")
    candidate_lookup = load_candidate_lookup(config.candidate_dataset_path, setup_keys)
    regime_lookup = load_regime_lookup(config.regime_dataset_path)

    if progress:
        progress("Evaluating entry gates, evidence, penalties, and regime-aware readiness")
    entry_rows = evaluate_entry_rows(
        setup_rows=setup_rows,
        candidate_lookup=candidate_lookup,
        regime_lookup=regime_lookup,
        config=config.entry_config,
    )

    if progress:
        progress("Running real-row pilot validation")
    pilot_examples, pilot_rows = select_pilot_rows(entry_rows)
    pilot_validation = validate_pilot_rows(pilot_examples, pilot_rows)
    write_csv(config.pilot_validation_path, pilot_validation["rows"], PILOT_VALIDATION_FIELDS)

    full_generation_completed = False
    if config.full_generation and pilot_validation["passed"]:
        if progress:
            progress("Writing full ENTRY_EVALUATION_V1 dataset")
        write_entry_rows(config.output_dataset_path, entry_rows)
        full_generation_completed = True

    daily_funnel_rows, daily_funnel_summary = daily_funnel(entry_rows)
    regime_funnel_rows, regime_funnel_summary = regime_funnel(entry_rows)
    penalty_rows, penalty_summary = penalty_report(entry_rows)
    exceptional_rows, exceptional_summary = exceptional_long_report(entry_rows)

    write_csv(config.daily_funnel_path, daily_funnel_rows, DAILY_FUNNEL_FIELDS)
    write_csv(config.regime_funnel_path, regime_funnel_rows, REGIME_FUNNEL_FIELDS)
    write_csv(config.penalties_path, penalty_rows, PENALTY_REPORT_FIELDS)
    write_csv(config.exceptional_longs_path, exceptional_rows, EXCEPTIONAL_LONG_FIELDS)

    hashes_after = upstream_hashes(config)
    baseline_unchanged = {name: hashes_before[name] == hashes_after[name] for name in hashes_before}
    input_versions = observed_versions(entry_rows, config)
    prohibited_output_fields = prohibited_outcome_fields(ENTRY_OUTPUT_FIELDS)
    report = {
        "phase": "Step 02.8",
        "command": "Command 01",
        "generated_at": generated_at,
        "entry": {
            "entry_version": config.entry_config.entry_version,
            "entry_config_hash": config.entry_config.config_hash(),
            "entry_availability": config.entry_config.entry_availability,
            "decision_use": config.entry_config.decision_use,
            "strategy_direction": config.entry_config.strategy_direction,
            "methodology": "Deterministic Strategy V1 entry-evaluation foundation that combines same-day candidate, setup, and regime context. It does not calculate final score, stops, targets, R:R, position sizing, backtests, paper trades, live signals, or orders.",
            "config_snapshot": config.entry_config.snapshot(),
        },
        "inputs": {
            "feature_dataset": str(config.feature_dataset_path),
            "candidate_dataset": str(config.candidate_dataset_path),
            "setup_dataset": str(config.setup_dataset_path),
            "regime_dataset": str(config.regime_dataset_path),
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
            "versions": input_versions,
        },
        "architecture": {
            "candidate_engine": "Which stocks deserve attention.",
            "setup_engine": "Whether the technical structure is credible.",
            "market_regime_engine": "What the broad market environment is.",
            "entry_evaluation_engine": "Whether the combined context may proceed to later risk evaluation.",
            "later_risk_engine": "Not implemented here; will decide stop/target/R:R feasibility later.",
            "later_signal_engine": "Not implemented here; no trade signal is emitted.",
        },
        "pilot": {
            "examples": pilot_examples,
            "validation_passed": pilot_validation["passed"],
            "validation_rows": len(pilot_validation["rows"]),
            "failed_checks": sum(1 for row in pilot_validation["rows"] if row["result"] == "FAIL"),
        },
        "generation": generation_summary(
            entry_rows=entry_rows,
            full_generation_completed=full_generation_completed,
            daily_funnel_summary=daily_funnel_summary,
            regime_funnel_summary=regime_funnel_summary,
            penalty_summary=penalty_summary,
            exceptional_summary=exceptional_summary,
        ),
        "reports": {
            "daily_funnel": daily_funnel_summary,
            "regime_funnel": regime_funnel_summary,
            "penalties": penalty_summary,
            "exceptional_longs": exceptional_summary,
        },
        "regression": {
            "daily_features_v1_unchanged": baseline_unchanged["feature"],
            "momentum_candidates_v1_unchanged": baseline_unchanged["candidate"],
            "daily_setup_evaluation_v1_unchanged": baseline_unchanged["setup"],
            "market_regime_v1_unchanged": baseline_unchanged["regime"],
            "candidate_config_hash_unchanged": input_versions["candidate_config_hash"] == config.candidate_config.config_hash(),
            "setup_config_hash_unchanged": input_versions["setup_config_hash"] == config.setup_config.config_hash(),
            "regime_config_hash_unchanged": input_versions["regime_config_hash"] == config.regime_config.config_hash(),
        },
        "safety": {
            "future_return_fields_used": 0,
            "future_outcome_fields_used": 0,
            "mfe_mae_fields_used": 0,
            "winner_loser_labels_used": 0,
            "profitability_optimization_used": 0,
            "final_100_point_entry_score_generated": 0,
            "risk_reward_calculated": 0,
            "stops_generated": 0,
            "targets_generated": 0,
            "position_sizes_generated": 0,
            "backtests_run": 0,
            "paper_trades_generated": 0,
            "buy_sell_signals_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "prohibited_output_fields": prohibited_output_fields,
        },
        "outputs": {
            "dataset": str(config.output_dataset_path),
            "summary_json": str(config.summary_path),
            "daily_funnel_csv": str(config.daily_funnel_path),
            "regime_funnel_csv": str(config.regime_funnel_path),
            "penalties_csv": str(config.penalties_path),
            "pilot_validation_csv": str(config.pilot_validation_path),
            "exceptional_longs_csv": str(config.exceptional_longs_path),
            "markdown": "docs/strategy-v1-entry-evaluation.md",
        },
        "processing": {
            "duration_seconds": round(time.perf_counter() - started, 3),
            "output_rows": len(entry_rows),
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
        and not prohibited_output_fields
        and report["safety"]["orders_placed"] == 0
        and report["safety"]["remote_migrations_applied"] == 0
        and report["safety"]["supabase_bulk_records_persisted"] == 0
    )
    write_json(config.summary_path, report)
    return report


def evaluate_entry_rows(
    *,
    setup_rows: Sequence[dict[str, Any]],
    candidate_lookup: dict[tuple[str, str], dict[str, Any]],
    regime_lookup: dict[str, dict[str, Any]],
    config: EntryEvaluationConfig = EntryEvaluationConfig(),
) -> list[dict[str, Any]]:
    output = []
    for setup_row in setup_rows:
        key = (str(setup_row.get("trading_date", "")), canonical_symbol(setup_row.get("symbol", "")))
        output.append(
            evaluate_entry_row(
                candidate_row=candidate_lookup.get(key),
                setup_row=setup_row,
                regime_row=regime_lookup.get(str(setup_row.get("trading_date", ""))),
                config=config,
            )
        )
    rank_entry_rows_by_date(output, config)
    return output


def evaluate_entry_row(
    *,
    candidate_row: dict[str, Any] | None,
    setup_row: dict[str, Any],
    regime_row: dict[str, Any] | None,
    config: EntryEvaluationConfig = EntryEvaluationConfig(),
) -> dict[str, Any]:
    exceptional_candidate, exceptional_reasons = exceptional_long_candidate(setup_row, config)
    penalties = build_entry_penalties(
        setup_row=setup_row,
        regime_row=regime_row,
        config=config,
        exceptional_long_candidate=exceptional_candidate,
    )
    gates = evaluate_entry_gates(
        candidate_row=candidate_row,
        setup_row=setup_row,
        regime_row=regime_row,
        penalties=penalties,
        exceptional_long_candidate=exceptional_candidate,
        config=config,
    )
    permission = regime_permission(regime_state=regime_state(regime_row), config=config)
    readiness = derive_entry_readiness(
        setup_row=setup_row,
        regime_row=regime_row,
        gates=gates,
        penalties=penalties,
        exceptional_candidate=exceptional_candidate,
        config=config,
    )
    exceptional_status = exceptional_long_status(
        regime_row=regime_row,
        readiness=readiness,
        exceptional_candidate=exceptional_candidate,
    )
    positive, neutral, warning, blocking = evidence_sets(
        setup_row=setup_row,
        regime_row=regime_row,
        gates=gates,
        penalties=penalties,
        exceptional_status=exceptional_status,
        config=config,
    )
    max_severity = max_penalty_severity(penalties, config)
    blocking_present = blocking_penalty_present(penalties)
    row = {
        "trading_date": setup_row.get("trading_date", ""),
        "symbol": canonical_symbol(setup_row.get("symbol", "")),
        "isin": setup_row.get("isin", ""),
        "feature_version": setup_row.get("feature_version", ""),
        "candidate_version": setup_row.get("candidate_version", (candidate_row or {}).get("candidate_version", "")),
        "candidate_config_hash": setup_row.get("candidate_config_hash", (candidate_row or {}).get("candidate_config_hash", "")),
        "setup_version": setup_row.get("setup_version", ""),
        "setup_config_hash": setup_row.get("setup_config_hash", ""),
        "regime_version": (regime_row or {}).get("regime_version", ""),
        "regime_config_hash": (regime_row or {}).get("config_hash", ""),
        "entry_version": ENTRY_EVALUATION_VERSION,
        "entry_config_hash": config.config_hash(),
        "entry_availability": config.entry_availability,
        "decision_use": config.decision_use,
        "candidate_state": setup_row.get("candidate_state", ""),
        "emerging_eligible": truthy(setup_row.get("emerging_eligible")),
        "confirmed_eligible": truthy(setup_row.get("confirmed_eligible")),
        "both_eligible": truthy(setup_row.get("both_eligible")),
        "candidate_group": candidate_group(setup_row),
        "setup_status": setup_row.get("setup_status", ""),
        "setup_eligible": truthy(setup_row.get("setup_eligible")),
        "setup_quality": setup_row.get("setup_quality", ""),
        "setup_type_flags": setup_row.get("setup_type_flags", ""),
        "breakout_state": setup_row.get("breakout_state", ""),
        "acceptance_state": setup_row.get("acceptance_state", ""),
        "candle_quality": setup_row.get("candle_quality", ""),
        "volume_confirmation": setup_row.get("volume_confirmation", ""),
        "extension_risk": setup_row.get("extension_risk", ""),
        "benchmark_rs_context": setup_row.get("benchmark_rs_context", ""),
        "consolidation_state": setup_row.get("consolidation_state", ""),
        "consolidation_quality": setup_row.get("consolidation_quality", ""),
        "false_breakout_flags": setup_row.get("false_breakout_flags", ""),
        "overhead_resistance": setup_row.get("overhead_resistance", ""),
        "daily_level_reclaim": truthy(setup_row.get("daily_level_reclaim")),
        "regime_state": regime_state(regime_row),
        "regime_score_normalized": (regime_row or {}).get("regime_score_normalized", ""),
        "regime_confidence_score": (regime_row or {}).get("confidence_score", ""),
        "regime_confidence_state": (regime_row or {}).get("confidence_state", ""),
        "regime_available_weight_pct": (regime_row or {}).get("available_weight_pct", ""),
        "regime_permission": permission,
        "research_gate_passed": gates["research"]["passed"],
        "candidate_gate_passed": gates["candidate"]["passed"],
        "setup_gate_passed": gates["setup"]["passed"],
        "regime_gate_passed": gates["regime"]["passed"],
        "extension_gate_passed": gates["extension"]["passed"],
        "technical_rejection_gate_passed": gates["technical_rejection"]["passed"],
        "gate_details": json_blob(gates),
        "entry_evaluation_status": entry_evaluation_status(readiness, gates),
        "entry_readiness": readiness,
        "exceptional_long_candidate": exceptional_candidate,
        "exceptional_long_status": exceptional_status,
        "exceptional_long_reasons": join_codes(exceptional_reasons),
        "entry_evidence_strength": evidence_strength(setup_row, readiness, penalties),
        "entry_context_rank": "",
        "entry_context_percentile": "",
        "positive_evidence": join_codes(positive),
        "neutral_evidence": join_codes(neutral),
        "warning_evidence": join_codes(warning),
        "blocking_evidence": join_codes(blocking),
        "penalty_codes": join_codes(penalty_codes(penalties)),
        "max_penalty_severity": max_severity,
        "blocking_penalty_present": blocking_present,
        "candidate_strength_context": candidate_group(setup_row),
        "setup_strength_context": setup_row.get("setup_quality", ""),
        "breakout_context": setup_row.get("breakout_state", ""),
        "volume_context": setup_row.get("volume_confirmation", ""),
        "benchmark_rs_entry_context": setup_row.get("benchmark_rs_context", ""),
        "regime_context": regime_state(regime_row),
        "extension_context": setup_row.get("extension_risk", ""),
        "candle_context": setup_row.get("candle_quality", ""),
        "consolidation_context": setup_row.get("consolidation_quality", ""),
        "false_breakout_context": setup_row.get("false_breakout_flags", "") or "NONE",
        "reclaim_context": "DAILY_RECLAIM" if truthy(setup_row.get("daily_level_reclaim")) else "NONE",
        "overhead_resistance_context": setup_row.get("overhead_resistance", ""),
        "stock_sector_rs_status": config.stock_sector_rs_status,
        "catalyst_context_status": config.catalyst_context_status,
        "risk_reward_status": config.risk_reward_status,
        "score_architecture_status": config.final_score_status,
    }
    row["_entry_rank_metric"] = entry_rank_metric(row, penalties)
    return row


def derive_entry_readiness(
    *,
    setup_row: dict[str, Any],
    regime_row: dict[str, Any] | None,
    gates: dict[str, dict[str, Any]],
    penalties: Sequence[dict[str, Any]],
    exceptional_candidate: bool,
    config: EntryEvaluationConfig,
) -> str:
    if not gates["research"]["passed"]:
        return "NOT_READY"
    if not gates["candidate"]["passed"]:
        return "NOT_READY"
    if not gates["extension"]["passed"] or not gates["technical_rejection"]["passed"]:
        return "NOT_READY"
    setup_quality = str(setup_row.get("setup_quality", "")).upper()
    if setup_quality == "WATCH":
        return "WATCH"
    if not gates["setup"]["passed"]:
        return "NOT_READY"
    if blocking_penalty_present(penalties) and regime_state(regime_row) != "BEARISH":
        return "NOT_READY"
    row_regime = regime_state(regime_row)
    if row_regime == "BULLISH":
        return "READY_FOR_RISK_EVALUATION"
    if row_regime == "NEUTRAL":
        if neutral_strict_requirements_met(setup_row, penalties, config):
            return "READY_FOR_RISK_EVALUATION"
        if setup_quality in {"VALID", "STRONG"} and not blocking_penalty_present(penalties):
            return "CONDITIONALLY_READY"
        return "WATCH"
    if row_regime == "BEARISH":
        if exceptional_candidate and gates["regime"]["passed"] and not blocking_penalty_present(penalties):
            return "EXCEPTIONAL_LONG_REVIEW"
        return "NOT_READY"
    if row_regime == "UNAVAILABLE":
        if setup_quality == "STRONG" and (candidate_confirmed(setup_row) or truthy(setup_row.get("both_eligible"))) and not blocking_penalty_present(penalties):
            return "CONDITIONALLY_READY"
        return "WATCH"
    return "NOT_READY"


def exceptional_long_candidate(setup_row: dict[str, Any], config: EntryEvaluationConfig) -> tuple[bool, list[str]]:
    rules = config.bearish_exceptional
    reasons: list[str] = []
    false_flags = split_codes(setup_row.get("false_breakout_flags", ""))
    setup_flags = split_codes(setup_row.get("setup_type_flags", ""))
    if str(setup_row.get("setup_quality", "")).upper() == rules.required_setup_quality:
        reasons.append("STRONG_SETUP")
    if str(setup_row.get("candidate_state", "")).upper() in set(rules.required_candidate_states) or (
        rules.allow_both_eligible and truthy(setup_row.get("both_eligible"))
    ):
        reasons.append("CONFIRMED_OR_BOTH_ELIGIBLE")
    if str(setup_row.get("benchmark_rs_context", "")).upper() in set(rules.required_benchmark_rs):
        reasons.append("STRONG_BENCHMARK_RS")
    if str(setup_row.get("volume_confirmation", "")).upper() in set(rules.required_volume):
        reasons.append("STRONG_OR_EXCEPTIONAL_VOLUME")
    if str(setup_row.get("breakout_state", "")).upper() in set(rules.required_breakout_states) or setup_flags & set(
        rules.allowed_setup_type_flags
    ):
        reasons.append("CLOSE_ACCEPTED_OR_CONTINUATION")
    if str(setup_row.get("candle_quality", "")).upper() in set(rules.required_candle_quality):
        reasons.append("GOOD_OR_STRONG_CANDLE")
    if str(setup_row.get("extension_risk", "")).upper() in set(rules.allowed_extension_risk):
        reasons.append("LOW_OR_MODERATE_EXTENSION")
    if str(setup_row.get("consolidation_quality", "")).upper() in set(rules.required_consolidation_quality):
        reasons.append("GOOD_OR_STRONG_CONSOLIDATION")
    if not (false_flags & set(rules.blocking_false_breakout_flags)):
        reasons.append("NO_MAJOR_FALSE_BREAKOUT_WARNING")
    required_count = 9
    return len(reasons) == required_count, reasons


def exceptional_long_status(
    *,
    regime_row: dict[str, Any] | None,
    readiness: str,
    exceptional_candidate: bool,
) -> str:
    if readiness == "EXCEPTIONAL_LONG_REVIEW":
        return "EXCEPTIONAL_REVIEW_READY"
    if exceptional_candidate:
        return "EXCEPTIONAL_CANDIDATE"
    return "NOT_EXCEPTIONAL"


def evidence_sets(
    *,
    setup_row: dict[str, Any],
    regime_row: dict[str, Any] | None,
    gates: dict[str, dict[str, Any]],
    penalties: Sequence[dict[str, Any]],
    exceptional_status: str,
    config: EntryEvaluationConfig,
) -> tuple[list[str], list[str], list[str], list[str]]:
    positive: list[str] = []
    neutral: list[str] = []
    warning: list[str] = []
    blocking: list[str] = []
    setup_quality = str(setup_row.get("setup_quality", "")).upper()
    candidate_state_value = str(setup_row.get("candidate_state", "")).upper()
    volume = str(setup_row.get("volume_confirmation", "")).upper()
    benchmark_rs = str(setup_row.get("benchmark_rs_context", "")).upper()
    regime = regime_state(regime_row)
    if setup_quality == "STRONG":
        positive.append("STRONG_SETUP")
    elif setup_quality == "VALID":
        positive.append("VALID_SETUP")
    elif setup_quality == "WATCH":
        warning.append("SETUP_WATCH_ONLY")
    if candidate_state_value == "CONFIRMED":
        positive.append("CONFIRMED_MOMENTUM")
    elif candidate_state_value == "EMERGING":
        positive.append("EMERGING_MOMENTUM")
    if truthy(setup_row.get("both_eligible")):
        positive.append("BOTH_ELIGIBLE")
    if setup_row.get("breakout_state") == "CLOSE_ACCEPTED":
        positive.append("CLOSE_ACCEPTED")
    elif setup_row.get("breakout_state") == "CLOSE_ABOVE":
        positive.append("CLOSE_ABOVE_PRIOR_HIGH")
    if "MOMENTUM_CONTINUATION" in split_codes(setup_row.get("setup_type_flags", "")):
        positive.append("MOMENTUM_CONTINUATION")
    if volume == "EXCEPTIONAL":
        positive.append("EXCEPTIONAL_VOLUME")
    elif volume == "STRONG":
        positive.append("STRONG_VOLUME")
    elif volume == "GOOD":
        positive.append("GOOD_VOLUME")
    if benchmark_rs == "STRONG":
        positive.append("STRONG_BENCHMARK_RS")
    elif benchmark_rs == "POSITIVE":
        positive.append("POSITIVE_BENCHMARK_RS")
    if str(setup_row.get("consolidation_quality", "")).upper() in {"GOOD", "STRONG"}:
        positive.append("TIGHT_OR_GOOD_CONSOLIDATION")
    if truthy(setup_row.get("daily_level_reclaim")):
        positive.append("DAILY_RECLAIM")
    if regime == "BULLISH":
        positive.append("BULLISH_REGIME")
    elif regime == "NEUTRAL":
        warning.append("NEUTRAL_REGIME")
    elif regime == "BEARISH":
        warning.append("BEARISH_REGIME")
    else:
        warning.append("REGIME_UNAVAILABLE")
    if exceptional_status == "EXCEPTIONAL_REVIEW_READY":
        positive.append("EXCEPTIONAL_LONG_EVIDENCE")

    neutral.extend(
        [
            "STOCK_SECTOR_RS_UNAVAILABLE",
            "CATALYST_CONTEXT_UNAVAILABLE",
            "RISK_REWARD_NOT_EVALUATED",
            "FINAL_ENTRY_SCORE_NOT_IMPLEMENTED",
        ]
    )
    for penalty in penalties:
        code = str(penalty["penalty_code"])
        if truthy(penalty.get("blocking")):
            blocking.append(code)
        else:
            warning.append(code)
    for gate_info in gates.values():
        if not truthy(gate_info.get("passed")):
            blocking.extend(gate_info.get("reason_codes", []))
        elif gate_info.get("gate_status") == "PARTIAL":
            warning.extend(gate_info.get("reason_codes", []))
    warning.extend(split_codes(setup_row.get("warning_flags", "")))
    return dedupe(positive), dedupe(neutral), dedupe(warning), dedupe(blocking)


def entry_evaluation_status(readiness: str, gates: dict[str, dict[str, Any]]) -> str:
    if not gates["research"]["passed"]:
        return "UNAVAILABLE"
    if readiness in {"READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}:
        return "READY"
    if readiness in {"WATCH", "CONDITIONALLY_READY"}:
        return "PARTIAL"
    return "BLOCKED"


def evidence_strength(setup_row: dict[str, Any], readiness: str, penalties: Sequence[dict[str, Any]]) -> str:
    if readiness == "EXCEPTIONAL_LONG_REVIEW":
        return "EXCEPTIONAL"
    if (
        str(setup_row.get("setup_quality", "")).upper() == "STRONG"
        and (candidate_confirmed(setup_row) or truthy(setup_row.get("both_eligible")))
        and str(setup_row.get("volume_confirmation", "")).upper() in {"STRONG", "EXCEPTIONAL"}
        and str(setup_row.get("benchmark_rs_context", "")).upper() == "STRONG"
        and not blocking_penalty_present(penalties)
    ):
        return "STRONG"
    if readiness in {"CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION"}:
        return "MODERATE"
    return "WEAK"


def entry_rank_metric(row: dict[str, Any], penalties: Sequence[dict[str, Any]]) -> tuple[Any, ...]:
    return (
        readiness_ordinal(row["entry_readiness"]),
        strength_ordinal(row["entry_evidence_strength"]),
        setup_quality_ordinal(row["setup_quality"]),
        candidate_ordinal(row),
        volume_ordinal(row["volume_confirmation"]),
        benchmark_ordinal(row["benchmark_rs_context"]),
        regime_ordinal(row["regime_state"]),
        -severity_ordinal(row["max_penalty_severity"]),
        -len(penalties),
        decimal_or_zero(row.get("regime_score_normalized")),
    )


def rank_entry_rows_by_date(rows: Sequence[dict[str, Any]], config: EntryEvaluationConfig) -> None:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    eligible_states = set(config.ranking.eligible_readiness_states)
    for row in rows:
        if row["entry_readiness"] in eligible_states:
            by_date[str(row["trading_date"])].append(row)
    for same_date_rows in by_date.values():
        ordered = sorted(same_date_rows, key=lambda row: row["_entry_rank_metric"], reverse=True)
        total = len(ordered)
        for index, row in enumerate(ordered, start=1):
            row["entry_context_rank"] = index
            row["entry_context_percentile"] = round_decimal(Decimal(total - index + 1) / Decimal(total) * Decimal("100"))


def load_setup_rows(path: Path) -> list[dict[str, str]]:
    with open_csv_maybe_gzip(path) as file:
        return [row for row in csv.DictReader(file) if row.get("trading_date") and row.get("symbol")]


def load_candidate_lookup(path: Path, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    lookup = {}
    with open_csv_maybe_gzip(path) as file:
        for row in csv.DictReader(file):
            key = (str(row.get("trading_date", "")), canonical_symbol(row.get("symbol", "")))
            if key in keys:
                lookup[key] = row
    return lookup


def load_regime_lookup(path: Path) -> dict[str, dict[str, str]]:
    with open_csv_maybe_gzip(path) as file:
        return {row["trading_date"]: row for row in csv.DictReader(file) if row.get("trading_date")}


def daily_funnel(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    by_date = group_rows(rows, "trading_date")
    ready_states = {"CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}
    ready_for_risk_states = {"READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}
    ready_counts = []
    for trading_date in sorted(by_date):
        group = by_date[trading_date]
        counts = Counter(row["entry_readiness"] for row in group)
        setup_eligible = sum(1 for row in group if truthy(row["setup_eligible"]))
        ready_or_conditional = sum(1 for row in group if row["entry_readiness"] in ready_states)
        ready_for_risk = sum(1 for row in group if row["entry_readiness"] in ready_for_risk_states)
        ready_counts.append(ready_for_risk)
        output.append(
            {
                "trading_date": trading_date,
                "candidate_rows": len(group),
                "setup_eligible_rows": setup_eligible,
                "entry_evaluated_rows": len(group),
                "not_ready": counts["NOT_READY"],
                "watch": counts["WATCH"],
                "conditionally_ready": counts["CONDITIONALLY_READY"],
                "ready_for_risk_evaluation": counts["READY_FOR_RISK_EVALUATION"],
                "exceptional_long_review": counts["EXCEPTIONAL_LONG_REVIEW"],
                "candidate_to_setup_conversion_pct": pct(setup_eligible, len(group)),
                "setup_to_ready_or_conditional_pct": pct(ready_or_conditional, setup_eligible),
                "candidate_to_ready_or_conditional_pct": pct(ready_or_conditional, len(group)),
            }
        )
    return output, {"daily_ready_for_risk_distribution": numeric_distribution(ready_counts)}


def regime_funnel(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output = []
    summary = {}
    ready_states = {"CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}
    for regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNAVAILABLE"):
        group = [row for row in rows if row["regime_state"] == regime]
        counts = Counter(row["entry_readiness"] for row in group)
        ready_or_conditional = sum(1 for row in group if row["entry_readiness"] in ready_states)
        row = {
            "regime_state": regime,
            "evaluated_rows": len(group),
            "setup_eligible_rows": sum(1 for row in group if truthy(row["setup_eligible"])),
            "not_ready": counts["NOT_READY"],
            "watch": counts["WATCH"],
            "conditionally_ready": counts["CONDITIONALLY_READY"],
            "ready_for_risk_evaluation": counts["READY_FOR_RISK_EVALUATION"],
            "exceptional_long_review": counts["EXCEPTIONAL_LONG_REVIEW"],
            "ready_or_conditional_pct": pct(ready_or_conditional, len(group)),
            "blocked_or_not_ready_pct": pct(counts["NOT_READY"], len(group)),
        }
        output.append(row)
        summary[regime] = row
    return output, summary


def penalty_report(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    code_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    blocking_counter: Counter[str] = Counter()
    combo_counter: Counter[str] = Counter()
    for row in rows:
        codes = split_codes(row.get("penalty_codes", ""))
        if not codes:
            combo_counter["NO_PENALTY"] += 1
        else:
            combo_counter[";".join(sorted(codes))] += 1
        for code in codes:
            code_counter[code] += 1
        severity_counter[str(row.get("max_penalty_severity", ""))] += 1
        blocking_counter["blocking"] += 1 if truthy(row.get("blocking_penalty_present")) else 0
        blocking_counter["nonblocking"] += 0 if truthy(row.get("blocking_penalty_present")) else 1
    output = []
    total = len(rows)
    for code, count in code_counter.most_common():
        output.append(
            {
                "section": "PENALTY_FREQUENCY",
                "penalty_code": code,
                "severity": "",
                "blocking": "",
                "count": count,
                "pct": pct(count, total),
                "details": "",
            }
        )
    for severity, count in severity_counter.most_common():
        output.append(
            {
                "section": "MAX_SEVERITY",
                "penalty_code": "",
                "severity": severity,
                "blocking": "",
                "count": count,
                "pct": pct(count, total),
                "details": "",
            }
        )
    for label, count in blocking_counter.items():
        output.append(
            {
                "section": "BLOCKING_VS_NONBLOCKING",
                "penalty_code": "",
                "severity": "",
                "blocking": label,
                "count": count,
                "pct": pct(count, total),
                "details": "",
            }
        )
    for combo, count in combo_counter.most_common(20):
        output.append(
            {
                "section": "TOP_COMBINATIONS",
                "penalty_code": "",
                "severity": "",
                "blocking": "",
                "count": count,
                "pct": pct(count, total),
                "details": combo,
            }
        )
    return output, {
        "penalty_frequency": distribution(code_counter, total),
        "max_severity_distribution": distribution(severity_counter, total),
        "blocking_vs_nonblocking": distribution(blocking_counter, total),
        "top_combinations": distribution(combo_counter, total, limit=10),
    }


def exceptional_long_report(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bearish = [row for row in rows if row["regime_state"] == "BEARISH"]
    bearish_setup = [row for row in bearish if truthy(row["setup_eligible"])]
    candidates = [row for row in bearish if truthy(row["exceptional_long_candidate"])]
    review_ready = [row for row in rows if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"]
    rate = pct(len(review_ready), len(bearish_setup))
    output = [
        {
            "section": "SUMMARY",
            "trading_date": "",
            "symbol": "",
            "regime_state": "BEARISH",
            "candidate_state": "",
            "setup_quality": "",
            "exceptional_long_status": "",
            "entry_readiness": "",
            "reason_codes": "",
            "count": len(bearish),
            "rate_pct": "",
        },
        {
            "section": "BEARISH_SETUP_ELIGIBLE",
            "trading_date": "",
            "symbol": "",
            "regime_state": "BEARISH",
            "candidate_state": "",
            "setup_quality": "",
            "exceptional_long_status": "",
            "entry_readiness": "",
            "reason_codes": "",
            "count": len(bearish_setup),
            "rate_pct": "",
        },
        {
            "section": "EXCEPTIONAL_REVIEW_READY",
            "trading_date": "",
            "symbol": "",
            "regime_state": "BEARISH",
            "candidate_state": "",
            "setup_quality": "",
            "exceptional_long_status": "",
            "entry_readiness": "",
            "reason_codes": "",
            "count": len(review_ready),
            "rate_pct": rate,
        },
    ]
    for row in review_ready[:200]:
        output.append(
            {
                "section": "DETAIL",
                "trading_date": row["trading_date"],
                "symbol": row["symbol"],
                "regime_state": row["regime_state"],
                "candidate_state": row["candidate_state"],
                "setup_quality": row["setup_quality"],
                "exceptional_long_status": row["exceptional_long_status"],
                "entry_readiness": row["entry_readiness"],
                "reason_codes": row["exceptional_long_reasons"],
                "count": "",
                "rate_pct": "",
            }
        )
    return output, {
        "total_bearish_candidate_rows": len(bearish),
        "bearish_setup_eligible_rows": len(bearish_setup),
        "exceptional_long_candidates": len(candidates),
        "exceptional_long_review_ready_rows": len(review_ready),
        "exceptional_pct_of_bearish_setup_rows": rate,
        "population_flag": "SELECTIVE" if Decimal(rate or "0") <= Decimal("20") else "LARGE_EXCEPTIONAL_LONG_POPULATION",
    }


def select_pilot_rows(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[tuple[str, Any, bool]] = [
        (
            "BULLISH_CONFIRMED_STRONG_SETUP",
            lambda row: row["regime_state"] == "BULLISH" and row["candidate_state"] == "CONFIRMED" and row["setup_quality"] == "STRONG",
            False,
        ),
        (
            "BULLISH_EMERGING_VALID_SETUP",
            lambda row: row["regime_state"] == "BULLISH" and row["candidate_state"] == "EMERGING" and row["setup_quality"] == "VALID",
            False,
        ),
        (
            "NEUTRAL_STRONG_QUALIFIES",
            lambda row: row["regime_state"] == "NEUTRAL" and row["entry_readiness"] == "READY_FOR_RISK_EVALUATION",
            False,
        ),
        (
            "NEUTRAL_WEAK_DOES_NOT_QUALIFY",
            lambda row: row["regime_state"] == "NEUTRAL" and row["entry_readiness"] in {"WATCH", "NOT_READY"},
            False,
        ),
        (
            "BEARISH_NORMAL_LONG_BLOCKED",
            lambda row: row["regime_state"] == "BEARISH" and truthy(row["setup_eligible"]) and row["entry_readiness"] == "NOT_READY",
            False,
        ),
        (
            "BEARISH_EXCEPTIONAL_LONG_CANDIDATE",
            lambda row: row["regime_state"] == "BEARISH" and row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW",
            False,
        ),
        ("HIGH_EXTENSION", lambda row: row["extension_risk"] == "HIGH", False),
        ("FALSE_BREAKOUT_WARNING", lambda row: bool(split_codes(row["false_breakout_flags"])), False),
        ("REGIME_UNAVAILABLE", lambda row: row["regime_state"] == "UNAVAILABLE", False),
        (
            "CA_OR_RESEARCH_BLOCKED_IF_PRESENT",
            lambda row: "RESEARCH_DATA_BLOCKED" in row["blocking_evidence"] or "CORPORATE_ACTION_EXCLUSION" in row["blocking_evidence"],
            True,
        ),
    ]
    examples = []
    pilot_rows = []
    seen: set[tuple[str, str]] = set()
    for case, predicate, optional in cases:
        match = next((row for row in rows if predicate(row)), None)
        if match is None:
            examples.append({"pilot_case": case, "found": False, "optional": optional})
            continue
        key = (match["trading_date"], match["symbol"])
        if key not in seen:
            pilot_rows.append(match)
            seen.add(key)
        examples.append(
            {
                "pilot_case": case,
                "found": True,
                "optional": optional,
                "symbol": match["symbol"],
                "trading_date": match["trading_date"],
                "regime_state": match["regime_state"],
                "candidate_state": match["candidate_state"],
                "setup_quality": match["setup_quality"],
                "entry_readiness": match["entry_readiness"],
            }
        )
    return examples, pilot_rows


def validate_pilot_rows(
    examples: Sequence[dict[str, Any]],
    pilot_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for example in examples:
        required_found = example.get("found") or example.get("optional")
        rows.append(
            pilot_validation_row(
                example,
                check_name="pilot_case_coverage",
                observed=example.get("found"),
                expected="FOUND_OR_OPTIONAL",
                passed=bool(required_found),
                explanation="Pilot examples are discovered from actual historical rows where available.",
            )
        )
    for row in pilot_rows:
        rows.extend(manual_validation_rows(row))
    return {"passed": all(row["result"] == "PASS" for row in rows), "rows": rows}


def manual_validation_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    gate_details = json.loads(row["gate_details"])
    valid_readiness = row["entry_readiness"] in READINESS_STATES
    version_fields = all(row.get(field) for field in ("feature_version", "candidate_version", "candidate_config_hash", "setup_version", "setup_config_hash", "regime_version", "regime_config_hash", "entry_version", "entry_config_hash"))
    rows = [
        pilot_validation_row(row, check_name="same_day_time_semantics", observed=f"{row['entry_availability']}/{row['decision_use']}", expected="EOD/NEXT_SESSION_ENTRY_RESEARCH", passed=row["entry_availability"] == "EOD" and row["decision_use"] == "NEXT_SESSION_ENTRY_RESEARCH", explanation="Entry context uses Candidate(T)+Setup(T)+Regime(T) for next-session research."),
        pilot_validation_row(row, check_name="version_fields_preserved", observed=version_fields, expected=True, passed=version_fields, explanation="Output row preserves upstream and entry methodology versions/hashes."),
        pilot_validation_row(row, check_name="gate_details_complete", observed=sorted(gate_details), expected="research/candidate/setup/regime/extension/technical_rejection", passed=set(gate_details) == {"research", "candidate", "setup", "regime", "extension", "technical_rejection"}, explanation="Every mandatory gate stores explicit status, pass flag, reasons, and evidence."),
        pilot_validation_row(row, check_name="readiness_state_valid", observed=row["entry_readiness"], expected="ENTRY_READINESS_ENUM", passed=valid_readiness, explanation="Readiness is an entry-evaluation handoff descriptor only."),
        pilot_validation_row(row, check_name="penalty_fields_visible", observed=f"{row['penalty_codes']} / {row['max_penalty_severity']}", expected="VISIBLE_PENALTY_ARCHITECTURE", passed=bool(row["max_penalty_severity"]), explanation="Penalties remain separate from positive evidence and no score deduction is applied."),
        pilot_validation_row(row, check_name="future_components_not_fabricated", observed=f"{row['stock_sector_rs_status']}/{row['catalyst_context_status']}/{row['risk_reward_status']}/{row['score_architecture_status']}", expected="UNAVAILABLE/UNAVAILABLE/NOT_EVALUATED/NOT_IMPLEMENTED", passed=row["stock_sector_rs_status"] == "UNAVAILABLE" and row["catalyst_context_status"] == "UNAVAILABLE" and row["risk_reward_status"] == "NOT_EVALUATED" and row["score_architecture_status"] == "NOT_IMPLEMENTED", explanation="Sector stock RS, catalyst/news, risk/reward, and final score are only placeholders."),
    ]
    if row["regime_state"] == "BEARISH" and truthy(row["setup_eligible"]) and row["entry_readiness"] != "EXCEPTIONAL_LONG_REVIEW":
        rows.append(pilot_validation_row(row, check_name="bearish_normal_long_block", observed=row["blocking_evidence"], expected="BEARISH_NORMAL_LONG_BLOCKED", passed="BEARISH_NORMAL_LONG_BLOCKED" in row["blocking_evidence"], explanation="Normal swing longs are blocked in bearish regimes."))
    if row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW":
        rows.append(pilot_validation_row(row, check_name="exceptional_long_review_ready", observed=row["exceptional_long_status"], expected="EXCEPTIONAL_REVIEW_READY", passed=row["exceptional_long_status"] == "EXCEPTIONAL_REVIEW_READY", explanation="Bearish exceptional long remains a review handoff, not a trade approval."))
    if row["regime_state"] == "UNAVAILABLE":
        rows.append(pilot_validation_row(row, check_name="regime_unavailable_conservative", observed=row["entry_readiness"], expected="NOT_READY_OR_WATCH_OR_CONDITIONALLY_READY", passed=row["entry_readiness"] != "READY_FOR_RISK_EVALUATION", explanation="Unavailable regime is not silently treated as neutral."))
    if row["extension_risk"] == "HIGH":
        rows.append(pilot_validation_row(row, check_name="high_extension_penalty", observed=row["penalty_codes"], expected="HIGH_EXTENSION", passed="HIGH_EXTENSION" in row["penalty_codes"], explanation="High extension is visible as a nonblocking penalty unless other gates block."))
    if split_codes(row["false_breakout_flags"]):
        rows.append(pilot_validation_row(row, check_name="false_breakout_penalty", observed=row["penalty_codes"], expected="FALSE_BREAKOUT_WARNING", passed="FALSE_BREAKOUT_WARNING" in row["penalty_codes"], explanation="Same-day false-breakout warnings remain visible and may block when severe."))
    return rows


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
        "regime_state": row.get("regime_state", ""),
        "candidate_state": row.get("candidate_state", ""),
        "setup_quality": row.get("setup_quality", ""),
        "entry_readiness": row.get("entry_readiness", ""),
        "check_name": check_name,
        "observed": observed,
        "expected": expected,
        "result": "PASS" if passed else "FAIL",
        "explanation": explanation,
    }


def generation_summary(
    *,
    entry_rows: Sequence[dict[str, Any]],
    full_generation_completed: bool,
    daily_funnel_summary: dict[str, Any],
    regime_funnel_summary: dict[str, Any],
    penalty_summary: dict[str, Any],
    exceptional_summary: dict[str, Any],
) -> dict[str, Any]:
    readiness_counts = Counter(row["entry_readiness"] for row in entry_rows)
    status_counts = Counter(row["entry_evaluation_status"] for row in entry_rows)
    setup_eligible = sum(1 for row in entry_rows if truthy(row["setup_eligible"]))
    ready_or_conditional = sum(
        1
        for row in entry_rows
        if row["entry_readiness"] in {"CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}
    )
    ready_for_risk = sum(1 for row in entry_rows if row["entry_readiness"] in {"READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"})
    return {
        "full_generation_completed": full_generation_completed,
        "total_rows_evaluated": len(entry_rows),
        "entry_evaluation_status_counts": distribution(status_counts, len(entry_rows)),
        "entry_readiness_counts": readiness_distribution(readiness_counts, len(entry_rows)),
        "candidate_to_setup_conversion_pct": pct(setup_eligible, len(entry_rows)),
        "setup_to_entry_readiness_conversion_pct": pct(ready_or_conditional, setup_eligible),
        "candidate_to_entry_readiness_conversion_pct": pct(ready_or_conditional, len(entry_rows)),
        "ready_for_risk_or_exceptional_rows": ready_for_risk,
        "daily_ready_for_risk_distribution": daily_funnel_summary["daily_ready_for_risk_distribution"],
        "candidate_group_readiness": candidate_group_readiness(entry_rows),
        "regime_funnel": regime_funnel_summary,
        "most_common_warnings": top_reason_codes(entry_rows, "warning_evidence"),
        "most_common_blocking_reasons": top_reason_codes(entry_rows, "blocking_evidence"),
        "penalty_summary": penalty_summary,
        "exceptional_long_sanity": exceptional_summary,
    }


def candidate_group_readiness(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary = {}
    ready_states = {"CONDITIONALLY_READY", "READY_FOR_RISK_EVALUATION", "EXCEPTIONAL_LONG_REVIEW"}
    for group_name in ("EMERGING_ONLY", "CONFIRMED_ONLY", "BOTH_ELIGIBLE"):
        group = [row for row in rows if row["candidate_group"] == group_name]
        ready = sum(1 for row in group if row["entry_readiness"] in ready_states)
        summary[group_name] = {
            "rows": len(group),
            "ready_or_conditional": ready,
            "ready_rate_pct": pct(ready, len(group)),
        }
    return summary


def write_strategy_v1_entry_evaluation_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    readiness = generation["entry_readiness_counts"]
    exceptional = generation["exceptional_long_sanity"]
    lines = [
        "# Strategy V1 Entry Evaluation",
        "",
        "Current phase: Step 02.8 / Command 01 - Strategy V1 entry-evaluation foundation",
        "",
        "## Boundary",
        "",
        "- ENTRY_EVALUATION_V1 combines same-day Momentum Candidate, Daily Setup Evaluation, and Market Regime rows.",
        "- The output is NEXT_SESSION_ENTRY_RESEARCH and remains DAILY_EOD only.",
        "- READY_FOR_RISK_EVALUATION does not mean trade.",
        "- EXCEPTIONAL_LONG_REVIEW does not mean high conviction or trade approval.",
        "- No final 0-100 entry score, stop, target, risk/reward, position sizing, BUY/SELL signal, backtest, paper trade, order, migration, or Supabase write is implemented.",
        "",
        "## Version",
        "",
        f"- Entry methodology/config hash: {report['entry']['entry_version']} / {report['entry']['entry_config_hash']}",
        f"- Candidate: {report['inputs']['versions']['candidate_version']} / {report['inputs']['versions']['candidate_config_hash']}",
        f"- Setup: {report['inputs']['versions']['setup_version']} / {report['inputs']['versions']['setup_config_hash']}",
        f"- Regime: {report['inputs']['versions']['regime_version']} / {report['inputs']['versions']['regime_config_hash']}",
        "",
        "## Architecture",
        "",
        "- Candidate Engine: which stocks deserve attention.",
        "- Setup Engine: whether the technical structure is credible.",
        "- Market Regime Engine: broad market environment.",
        "- Entry Evaluation Engine: whether current context may proceed to later risk evaluation.",
        "- Later Risk and Signal Engines are explicitly not implemented here.",
        "",
        "## Gates",
        "",
        "- Data/research safety preserves row availability, corporate-action/research blocking, and membership uncertainty metadata.",
        "- Candidate eligibility allows only EMERGING or CONFIRMED rows.",
        "- Setup eligibility requires setup_eligible plus VALID or STRONG for normal readiness; WATCH stays watch-only and POOR blocks.",
        "- Bullish regime permits normal long evaluation.",
        "- Neutral regime applies stricter confirmation.",
        "- Bearish regime blocks normal swing longs except rare exceptional-long review rows.",
        "- Regime unavailable is conservative and never treated as Neutral.",
        "",
        "## Results",
        "",
        f"- Full generation completed: {generation['full_generation_completed']}",
        f"- Total evaluated rows: {generation['total_rows_evaluated']}",
        f"- Readiness counts: {readiness}",
        f"- Candidate to setup conversion: {generation['candidate_to_setup_conversion_pct']}%",
        f"- Setup to ready/conditional conversion: {generation['setup_to_entry_readiness_conversion_pct']}%",
        f"- Candidate to ready/conditional conversion: {generation['candidate_to_entry_readiness_conversion_pct']}%",
        f"- Daily ready-for-risk distribution: {generation['daily_ready_for_risk_distribution']}",
        "",
        "## Exceptional Longs",
        "",
        f"- Bearish candidate rows: {exceptional['total_bearish_candidate_rows']}",
        f"- Bearish setup-eligible rows: {exceptional['bearish_setup_eligible_rows']}",
        f"- Exceptional-long candidates: {exceptional['exceptional_long_candidates']}",
        f"- Exceptional-long review-ready rows: {exceptional['exceptional_long_review_ready_rows']} ({exceptional['exceptional_pct_of_bearish_setup_rows']}% of bearish setup rows)",
        "",
        "## Integrity",
        "",
        f"- DAILY_FEATURES_V1 unchanged: {report['regression']['daily_features_v1_unchanged']}",
        f"- MOMENTUM_CANDIDATES_V1 unchanged: {report['regression']['momentum_candidates_v1_unchanged']}",
        f"- DAILY_SETUP_EVALUATION_V1 unchanged: {report['regression']['daily_setup_evaluation_v1_unchanged']}",
        f"- MARKET_REGIME_V1 unchanged: {report['regression']['market_regime_v1_unchanged']}",
        "- ZERO orders were placed.",
        "- ZERO remote migrations were applied.",
        "- ZERO records were persisted to Supabase.",
        "",
        "## Known Limitations",
        "",
        "- Stock-specific historical sector RS is unavailable and not used.",
        "- Catalyst/news is unavailable and not fabricated.",
        "- Risk/reward is not evaluated, so no trade can be approved from this layer.",
        "- The rank is a same-day structural context ordering, not the final Strategy V1 0-100 score.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def upstream_hashes(config: EntryEvaluationEngineConfig) -> dict[str, str]:
    return {
        "feature": file_sha256(config.feature_dataset_path),
        "candidate": file_sha256(config.candidate_dataset_path),
        "setup": file_sha256(config.setup_dataset_path),
        "regime": file_sha256(config.regime_dataset_path),
    }


def observed_versions(rows: Sequence[dict[str, Any]], config: EntryEvaluationEngineConfig) -> dict[str, str]:
    return {
        "feature_version": observed_single_value(rows, "feature_version"),
        "candidate_version": observed_single_value(rows, "candidate_version"),
        "candidate_config_hash": observed_single_value(rows, "candidate_config_hash"),
        "setup_version": observed_single_value(rows, "setup_version"),
        "setup_config_hash": observed_single_value(rows, "setup_config_hash"),
        "regime_version": observed_single_value(rows, "regime_version"),
        "regime_config_hash": observed_single_value(rows, "regime_config_hash"),
        "entry_version": config.entry_config.entry_version,
        "entry_config_hash": config.entry_config.config_hash(),
    }


def write_entry_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ENTRY_OUTPUT_FIELDS, extrasaction="ignore")
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


def top_reason_codes(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for row in rows:
        for code in split_codes(row.get(field, "")):
            counter[code] += 1
    return distribution(counter, len(rows), limit=20)


def readiness_distribution(counter: Counter[str], total: int) -> dict[str, Any]:
    return {state: {"count": counter[state], "pct": pct(counter[state], total)} for state in READINESS_STATES}


def distribution(counter: Counter[str], total: int, *, limit: int | None = None) -> dict[str, Any]:
    pairs = counter.most_common(limit)
    return {key: {"count": count, "pct": pct(count, total)} for key, count in pairs}


def numeric_distribution(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"min": 0, "p10": 0, "p25": 0, "median": 0, "mean": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "p10": int_quantile(ordered, Decimal("0.10")),
        "p25": int_quantile(ordered, Decimal("0.25")),
        "median": statistics.median(ordered),
        "mean": round(statistics.mean(ordered), 4),
        "p75": int_quantile(ordered, Decimal("0.75")),
        "p90": int_quantile(ordered, Decimal("0.90")),
        "p95": int_quantile(ordered, Decimal("0.95")),
        "p99": int_quantile(ordered, Decimal("0.99")),
        "max": ordered[-1],
    }


def int_quantile(values: Sequence[int], percentile: Decimal) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * percentile).to_integral_value(rounding=ROUND_HALF_UP))
    return ordered[min(index, len(ordered) - 1)]


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


def round_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.0001")), "f")


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0000"
    return round_decimal(Decimal(numerator) / Decimal(denominator) * Decimal("100"))


def join_codes(values: Sequence[str]) -> str:
    return ";".join(dedupe(values))


def dedupe(values: Sequence[str]) -> list[str]:
    output = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def json_blob(value: Any) -> str:
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"))


def group_rows(rows: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, ""))].append(row)
    return dict(grouped)


def regime_state(regime_row: dict[str, Any] | None) -> str:
    return str((regime_row or {}).get("regime_state", "") or "UNAVAILABLE").upper()


def candidate_group(row: dict[str, Any]) -> str:
    if truthy(row.get("both_eligible")):
        return "BOTH_ELIGIBLE"
    if str(row.get("candidate_state", "")).upper() == "CONFIRMED":
        return "CONFIRMED_ONLY"
    if str(row.get("candidate_state", "")).upper() == "EMERGING":
        return "EMERGING_ONLY"
    return "OTHER"


def candidate_confirmed(row: dict[str, Any]) -> bool:
    return str(row.get("candidate_state", "")).upper() == "CONFIRMED" or truthy(row.get("confirmed_eligible"))


def readiness_ordinal(value: str) -> int:
    return {
        "NOT_READY": 0,
        "WATCH": 1,
        "CONDITIONALLY_READY": 2,
        "READY_FOR_RISK_EVALUATION": 3,
        "EXCEPTIONAL_LONG_REVIEW": 4,
    }.get(str(value).upper(), 0)


def strength_ordinal(value: str) -> int:
    return {"WEAK": 0, "MODERATE": 1, "STRONG": 2, "EXCEPTIONAL": 3}.get(str(value).upper(), 0)


def setup_quality_ordinal(value: str) -> int:
    return {"POOR": 0, "WATCH": 1, "VALID": 2, "STRONG": 3}.get(str(value).upper(), 0)


def candidate_ordinal(row: dict[str, Any]) -> int:
    if truthy(row.get("both_eligible")):
        return 3
    if str(row.get("candidate_state", "")).upper() == "CONFIRMED":
        return 2
    if str(row.get("candidate_state", "")).upper() == "EMERGING":
        return 1
    return 0


def volume_ordinal(value: str) -> int:
    return {"WEAK": 0, "UNKNOWN": 0, "NORMAL": 1, "GOOD": 2, "STRONG": 3, "EXCEPTIONAL": 4}.get(str(value).upper(), 0)


def benchmark_ordinal(value: str) -> int:
    return {"WEAK": 0, "UNKNOWN": 0, "NEUTRAL": 1, "POSITIVE": 2, "STRONG": 3}.get(str(value).upper(), 0)


def regime_ordinal(value: str) -> int:
    return {"UNAVAILABLE": 0, "BEARISH": 1, "NEUTRAL": 2, "BULLISH": 3}.get(str(value).upper(), 0)


def severity_ordinal(value: str) -> int:
    return {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "BLOCKING": 4}.get(str(value).upper(), 0)


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def observed_single_value(rows: Sequence[dict[str, Any]], field: str) -> str:
    values = sorted({str(row.get(field, "")) for row in rows if row.get(field)})
    return values[0] if len(values) == 1 else ";".join(values)


def output_size(config: EntryEvaluationEngineConfig) -> int:
    paths = [
        config.output_dataset_path,
        config.summary_path,
        config.daily_funnel_path,
        config.regime_funnel_path,
        config.penalties_path,
        config.pilot_validation_path,
        config.exceptional_longs_path,
    ]
    return sum(path.stat().st_size for path in paths if path.exists())

from __future__ import annotations

import csv
import gzip
import io
import statistics
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.risk.position_sizing import calculate_position_size
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    RiskStructureV11Config,
    resolve_current_risk_structure_dataset,
)
from app.risk.risk_structurer import load_lookup
from app.services.daily_feature_engine import (
    adjusted_daily_files,
    date_from_adjusted_path,
    json_safe,
    read_csv_iter,
    write_csv,
    write_json,
)
from app.services.nifty500_membership import canonical_symbol
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import resolve_strategy_outcome_dataset
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
    baseline_hash_checks,
    baseline_input_hashes,
    resolve_current_strategy_score_dataset,
    verify_current_strategy_score_baseline,
)
from app.strategy.outcomes.outcome_config import StrategyOutcomeConfig

ENTRY_VALID = "ENTRY_VALID"
ENTRY_INVALID_GAP = "ENTRY_INVALID_GAP"
ENTRY_INVALID_RR = "ENTRY_INVALID_RR"
ENTRY_INVALID_STOP_RELATION = "ENTRY_INVALID_STOP_RELATION"
ENTRY_INVALID_CAPITAL = "ENTRY_INVALID_CAPITAL"
NO_NEXT_SESSION_DATA = "NO_NEXT_SESSION_DATA"
OTHER_INVALID = "OTHER_INVALID"

TARGET_FIRST = "TARGET_FIRST"
STOP_FIRST = "STOP_FIRST"
NEITHER_WITHIN_HORIZON = "NEITHER_WITHIN_HORIZON"
AMBIGUOUS = "AMBIGUOUS"
INVALID_ENTRY = "INVALID_ENTRY"
INSUFFICIENT_FORWARD_DATA = "INSUFFICIENT_FORWARD_DATA"

PRIMARY_COHORT = "HISTORICAL_ELIGIBLE_OPPORTUNITY"
COUNTERFACTUAL_COHORT = "COUNTERFACTUAL_RESEARCH_COHORT"
EXCEPTIONAL_COHORT = "EXCEPTIONAL_REVIEW_RESEARCH"
PREVIEW_COHORT = "PREVIEW_RESEARCH_ONLY"

COMPONENTS = (
    "setup",
    "momentum",
    "rvol",
    "relative_strength",
    "regime",
    "reward_risk",
)
SAFE_BAR_STATUSES = {"", "ADJUSTED_READY", "RESEARCH_READY"}
BLOCKING_ELIGIBILITY_STATUSES = {
    "EXCLUDE_CORPORATE_ACTION_WINDOW",
    "EXCLUDE_SECURITY_RANGE",
    "MANUAL_REVIEW_REQUIRED",
}


@dataclass(frozen=True, slots=True)
class OutcomeBar:
    trading_date: date
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    research_usability_status: str = "ADJUSTED_READY"


@dataclass(frozen=True, slots=True)
class ForwardExclusion:
    start_date: date
    end_date: date
    reason_code: str
    source_event_id: str


@dataclass(frozen=True, slots=True)
class StrategyOutcomeEngineConfig:
    data_dir: Path
    outcome_config: StrategyOutcomeConfig = StrategyOutcomeConfig()
    full_generation: bool = True

    @property
    def adjusted_daily_dir(self) -> Path:
        return self.data_dir / "research" / "adjusted" / "daily" / "nse"

    @property
    def eligibility_path(self) -> Path:
        return self.data_dir / "reference" / "nse" / "corporate_actions" / "research_eligibility.csv"

    @property
    def score_dataset_path(self) -> Path:
        return resolve_current_strategy_score_dataset(self.data_dir)

    @property
    def risk_dataset_path(self) -> Path:
        return resolve_current_risk_structure_dataset(self.data_dir)

    @property
    def output_dataset_path(self) -> Path:
        return resolve_strategy_outcome_dataset(
            self.data_dir,
            profile=self.outcome_config.outcome_profile,
            version=self.outcome_config.outcome_version,
        )

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def report_path(self, suffix: str) -> Path:
        return self.reports_dir / f"strategy_outcome_v1_{suffix}"


OUTCOME_OUTPUT_FIELDS = [
    "decision_date",
    "symbol",
    "isin",
    "score_version",
    "score_profile",
    "score_config_hash",
    "raw_strategy_score",
    "scoring_disposition",
    "source_score_mode",
    "source_scoring_disposition",
    "source_raw_strategy_score",
    "source_score_band",
    "risk_version",
    "risk_config_hash",
    "outcome_version",
    "outcome_profile",
    "outcome_config_hash",
    "outcome_cohort",
    "source_trade_permission_status",
    "primary_evaluation_eligible",
    "setup_quality",
    "candidate_state",
    "candidate_category",
    "regime_state",
    "regime_confidence",
]
for _component in COMPONENTS:
    OUTCOME_OUTPUT_FIELDS.append(f"{_component}_points")
OUTCOME_OUTPUT_FIELDS.extend(
    [
        "next_session_date",
        "entry_model",
        "reference_entry_price",
        "t_close_reference_price",
        "hypothetical_entry_price",
        "gap_pct",
        "gap_from_t_close_pct",
        "gap_category",
        "entry_recheck_status",
        "entry_valid",
        "entry_rejection_reasons",
        "original_stop_price",
        "stop_price",
        "selected_target_price",
        "target_price",
        "selected_target_basis",
        "target_basis",
        "effective_risk_per_share",
        "effective_reward_per_share",
        "effective_reward_risk",
        "risk_budget_rupees",
        "quantity_by_risk",
        "quantity_by_cash",
        "hypothetical_quantity",
        "position_notional",
        "planned_rupee_risk",
        "planned_risk_pct",
        "no_leverage_status",
    ]
)
for _session in range(1, 5):
    OUTCOME_OUTPUT_FIELDS.extend(
        [
            f"session_date_{_session}",
            f"open_{_session}",
            f"high_{_session}",
            f"low_{_session}",
            f"close_{_session}",
            f"horizon_available_{_session}",
            f"close_return_pct_{_session}",
            f"close_return_r_{_session}",
            f"mfe_pct_{_session}",
            f"mae_pct_{_session}",
            f"mfe_r_{_session}",
            f"mae_r_{_session}",
            f"stop_touched_{_session}",
            f"target_touched_{_session}",
        ]
    )
OUTCOME_OUTPUT_FIELDS.extend(
    [
        "first_stop_session",
        "first_target_session",
        "same_bar_ambiguous",
        "stop_target_same_bar_ambiguous",
        "first_touch_outcome",
        "forward_sessions_available",
        "right_censored",
        "forward_data_safe",
        "forward_data_status",
        "forward_data_reasons",
        "transaction_cost_status",
        "slippage_status",
        "historical_execution_status",
        "trade_signal_status",
    ]
)


def build_strategy_outcomes(
    *,
    config: StrategyOutcomeEngineConfig,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Verifying frozen score and risk baselines")
    score_baseline = verify_current_strategy_score_baseline(config.data_dir)
    if file_sha256(config.risk_dataset_path) != RISK_STRUCTURE_V1_1_DATASET_HASH:
        raise ValueError("Current RISK_STRUCTURE_V1_1 dataset hash mismatch")
    if RiskStructureV11Config().config_hash() != CURRENT_RISK_STRUCTURE_CONFIG_HASH:
        raise ValueError("Current RISK_STRUCTURE_V1_1 config hash mismatch")
    hashes_before = baseline_input_hashes(config.data_dir)
    if not all(baseline_hash_checks(hashes_before).values()):
        raise ValueError("One or more frozen upstream dataset hashes do not match")

    notify(progress, "Loading selected score cohorts and frozen risk structures")
    score_rows = load_selected_score_rows(config.score_dataset_path)
    keys = {(row["trading_date"], canonical_symbol(row["symbol"])) for row in score_rows}
    risk_lookup = load_lookup(config.risk_dataset_path, keys)
    missing_risk = sorted(keys - set(risk_lookup))
    if missing_risk:
        raise ValueError(f"Missing frozen risk rows for {len(missing_risk)} selected scores")
    validate_input_identities(score_rows, risk_lookup.values())

    notify(progress, "Loading adjusted next-session market history")
    symbols = {canonical_symbol(row["symbol"]) for row in score_rows}
    sessions, bars = load_adjusted_market_history(config.adjusted_daily_dir, symbols)
    exclusions = load_forward_exclusions(config.eligibility_path)

    notify(progress, f"Calculating {len(score_rows)} future-separated outcome rows")
    rows = [
        build_outcome_row(
            score_row=score_row,
            risk_row=risk_lookup[(score_row["trading_date"], canonical_symbol(score_row["symbol"]))],
            sessions=sessions,
            bars=bars,
            exclusions=exclusions,
            config=config.outcome_config,
        )
        for score_row in score_rows
    ]

    notify(progress, "Running reproducible real-row pilot validation")
    pilot = run_pilot_validation(rows, config.outcome_config)
    if not pilot["passed"]:
        raise ValueError("Outcome pilot validation failed; full generation was not written")

    if config.full_generation:
        notify(progress, "Writing deterministic STRATEGY_OUTCOME_V1 dataset")
        write_outcome_rows(config.output_dataset_path, rows)

    hashes_after = baseline_input_hashes(config.data_dir)
    if hashes_after != hashes_before:
        raise ValueError("Frozen upstream dataset changed while generating outcomes")

    tables = build_report_tables(rows, pilot)
    dataset_hash = file_sha256(config.output_dataset_path) if config.full_generation else "NOT_WRITTEN_PILOT_ONLY"
    report = build_summary_report(
        engine_config=config,
        rows=rows,
        pilot=pilot,
        tables=tables,
        score_baseline=score_baseline,
        hashes_before=hashes_before,
        hashes_after=hashes_after,
        dataset_hash=dataset_hash,
        runtime_seconds=time.perf_counter() - started,
    )
    write_outcome_reports(config, report, tables)
    return report


def load_selected_score_rows(path: Path) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if outcome_cohort(row) is not None:
                selected.append(row)
    return selected


def outcome_cohort(score_row: dict[str, Any]) -> str | None:
    disposition = str(score_row.get("scoring_disposition", ""))
    mode = str(score_row.get("score_mode", ""))
    if disposition in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}:
        return PRIMARY_COHORT
    if mode == "FULL_SCORE":
        return COUNTERFACTUAL_COHORT
    if disposition == "EXCEPTIONAL_REVIEW" or mode == "EXCEPTIONAL_REVIEW_SCORE":
        return EXCEPTIONAL_COHORT
    if disposition == "PREVIEW_ONLY" or mode == "PREVIEW_SCORE":
        return PREVIEW_COHORT
    return None


def validate_input_identities(
    score_rows: Sequence[dict[str, Any]],
    risk_rows: Iterable[dict[str, Any]],
) -> None:
    if {row.get("score_version") for row in score_rows} != {CURRENT_STRATEGY_SCORE_VERSION}:
        raise ValueError("Selected score rows do not match current score version")
    if {row.get("score_profile") for row in score_rows} != {CURRENT_STRATEGY_SCORE_PROFILE}:
        raise ValueError("Selected score rows do not match current score profile")
    if {row.get("score_config_hash") for row in score_rows} != {CURRENT_STRATEGY_SCORE_CONFIG_HASH}:
        raise ValueError("Selected score rows do not match current score config")
    risk_rows = list(risk_rows)
    if {row.get("risk_version") for row in risk_rows} != {CURRENT_RISK_STRUCTURE_VERSION}:
        raise ValueError("Frozen risk rows do not match current risk version")
    if {row.get("risk_config_hash") for row in risk_rows} != {CURRENT_RISK_STRUCTURE_CONFIG_HASH}:
        raise ValueError("Frozen risk rows do not match current risk config")


def load_adjusted_market_history(
    adjusted_daily_dir: Path,
    symbols: set[str],
) -> tuple[list[date], dict[tuple[str, str], OutcomeBar]]:
    sessions: list[date] = []
    bars: dict[tuple[str, str], OutcomeBar] = {}
    for path in adjusted_daily_files(adjusted_daily_dir):
        trading_date = date_from_adjusted_path(path)
        if trading_date is None:
            continue
        sessions.append(trading_date)
        date_text = trading_date.isoformat()
        for row in read_csv_iter(path):
            if row.get("series", "EQ") != "EQ":
                continue
            symbol = canonical_symbol(row.get("symbol", ""))
            if symbol not in symbols:
                continue
            bar = parse_outcome_bar(row, trading_date)
            if bar is not None:
                bars[(date_text, symbol)] = bar
    return sorted(set(sessions)), bars


def parse_outcome_bar(row: dict[str, Any], trading_date: date | None = None) -> OutcomeBar | None:
    try:
        parsed_date = trading_date or date.fromisoformat(str(row.get("trading_date", "")))
    except ValueError:
        return None
    values = [decimal_or_none(row.get(name)) for name in ("adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close")]
    if any(value is None for value in values):
        values = [decimal_or_none(row.get(name)) for name in ("open", "high", "low", "close")]
    if any(value is None for value in values):
        return None
    open_value, high_value, low_value, close_value = values
    assert open_value is not None and high_value is not None and low_value is not None and close_value is not None
    if open_value <= 0 or high_value < low_value:
        return None
    return OutcomeBar(
        trading_date=parsed_date,
        symbol=canonical_symbol(row.get("symbol", "")),
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        research_usability_status=str(row.get("research_usability_status", "")),
    )


def load_forward_exclusions(path: Path) -> dict[str, list[ForwardExclusion]]:
    grouped: dict[str, list[ForwardExclusion]] = defaultdict(list)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("eligibility_status") not in BLOCKING_ELIGIBILITY_STATUSES:
                continue
            try:
                start = date.fromisoformat(str(row.get("start_date", "")))
                end = date.fromisoformat(str(row.get("end_date", "")))
            except ValueError:
                continue
            grouped[canonical_symbol(row.get("symbol", ""))].append(
                ForwardExclusion(start, end, row.get("reason_code", ""), row.get("source_event_id", ""))
            )
    return dict(grouped)


def resolve_next_sessions(decision_date: date, sessions: Sequence[date], maximum: int = 4) -> list[date]:
    start = bisect_right(sessions, decision_date)
    return list(sessions[start : start + maximum])


def classify_gap(gap_pct: Decimal | None, config: StrategyOutcomeConfig) -> str:
    if gap_pct is None:
        return "UNAVAILABLE"
    thresholds = config.gap_thresholds
    if gap_pct < -thresholds.flat_absolute_pct:
        return "GAP_DOWN"
    if abs(gap_pct) <= thresholds.flat_absolute_pct:
        return "FLAT"
    if gap_pct < thresholds.material_gap_up_pct:
        return "SMALL_GAP_UP"
    if gap_pct < thresholds.extreme_gap_up_pct:
        return "MATERIAL_GAP_UP"
    return "EXTREME_GAP_UP"


def forward_safety(
    *,
    symbol: str,
    session_dates: Sequence[date],
    session_bars: Sequence[OutcomeBar | None],
    exclusions: dict[str, list[ForwardExclusion]],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for exclusion in exclusions.get(symbol, []):
        if any(exclusion.start_date <= session <= exclusion.end_date for session in session_dates):
            reasons.append(f"CORPORATE_ACTION_EXCLUSION:{exclusion.reason_code or exclusion.source_event_id}")
    for bar in session_bars:
        if bar is not None and bar.research_usability_status not in SAFE_BAR_STATUSES:
            reasons.append(f"BAR_RESEARCH_STATUS:{bar.research_usability_status}")
    return not reasons, dedupe(reasons)


def build_outcome_row(
    *,
    score_row: dict[str, Any],
    risk_row: dict[str, Any],
    sessions: Sequence[date],
    bars: dict[tuple[str, str], OutcomeBar],
    exclusions: dict[str, list[ForwardExclusion]],
    config: StrategyOutcomeConfig = StrategyOutcomeConfig(),
) -> dict[str, Any]:
    decision = date.fromisoformat(str(score_row["trading_date"]))
    symbol = canonical_symbol(score_row.get("symbol", ""))
    session_dates = resolve_next_sessions(decision, sessions, config.max_hold_sessions)
    session_bars = [bars.get((session.isoformat(), symbol)) for session in session_dates]
    contiguous_bars: list[OutcomeBar] = []
    for bar in session_bars:
        if bar is None:
            break
        contiguous_bars.append(bar)
    right_censored = len(session_dates) < config.max_hold_sessions
    data_safe, safety_reasons = forward_safety(
        symbol=symbol,
        session_dates=session_dates,
        session_bars=session_bars,
        exclusions=exclusions,
    )

    cohort = outcome_cohort(score_row)
    if cohort is None:
        raise ValueError("Score row is outside configured outcome cohorts")
    reference_entry = decimal_or_none(risk_row.get("assumed_entry_price"))
    t_close_reference = decimal_or_none(risk_row.get("entry_reference_price"))
    stop = decimal_or_none(risk_row.get("stop_price"))
    target = decimal_or_none(risk_row.get("selected_target_price"))
    entry = contiguous_bars[0].open if contiguous_bars else None
    gap_pct = percent_change(entry, reference_entry)
    gap_from_t_close_pct = percent_change(entry, t_close_reference)
    effective_risk = entry - stop if entry is not None and stop is not None else None
    effective_reward = target - entry if entry is not None and target is not None else None
    effective_rr = (
        effective_reward / effective_risk
        if effective_reward is not None and effective_risk is not None and effective_risk > 0
        else None
    )
    position = calculate_position_size(
        assumed_entry_price=entry,
        risk_per_share=effective_risk,
        config=position_sizing_config(config),
    )

    rejection_reasons: list[str] = []
    if not session_dates or entry is None:
        entry_status = NO_NEXT_SESSION_DATA
        rejection_reasons.append("NEXT_VALID_SESSION_BAR_UNAVAILABLE")
    elif not data_safe:
        entry_status = OTHER_INVALID
        rejection_reasons.extend(safety_reasons)
    elif stop is None or target is None or reference_entry is None:
        entry_status = OTHER_INVALID
        rejection_reasons.append("FROZEN_RISK_REFERENCE_UNAVAILABLE")
    elif effective_risk is None or effective_risk <= 0:
        entry_status = ENTRY_INVALID_STOP_RELATION
        rejection_reasons.append("NEXT_SESSION_OPEN_NOT_ABOVE_FROZEN_STOP")
    elif effective_rr is None or effective_rr < config.minimum_effective_reward_risk:
        if gap_pct is not None and gap_pct > config.gap_thresholds.flat_absolute_pct:
            entry_status = ENTRY_INVALID_GAP
            rejection_reasons.append("GAP_UP_REDUCED_RR_BELOW_MINIMUM")
        else:
            entry_status = ENTRY_INVALID_RR
            rejection_reasons.append("EFFECTIVE_RR_BELOW_MINIMUM")
    elif not position["capital_valid"] or position["structured_quantity"] < 1:
        entry_status = ENTRY_INVALID_CAPITAL
        rejection_reasons.extend(position["capital_rejection_reasons"])
    else:
        entry_status = ENTRY_VALID

    source_permission = (
        PRIMARY_COHORT if cohort == PRIMARY_COHORT else cohort
    )
    row: dict[str, Any] = {
        "decision_date": decision.isoformat(),
        "symbol": symbol,
        "isin": score_row.get("isin", "") or risk_row.get("isin", ""),
        "score_version": score_row.get("score_version", ""),
        "score_profile": score_row.get("score_profile", ""),
        "score_config_hash": score_row.get("score_config_hash", ""),
        "raw_strategy_score": score_row.get("raw_strategy_score", ""),
        "scoring_disposition": score_row.get("scoring_disposition", ""),
        "source_score_mode": score_row.get("score_mode", ""),
        "source_scoring_disposition": score_row.get("scoring_disposition", ""),
        "source_raw_strategy_score": score_row.get("raw_strategy_score", ""),
        "source_score_band": score_row.get("score_band", ""),
        "risk_version": risk_row.get("risk_version", ""),
        "risk_config_hash": risk_row.get("risk_config_hash", ""),
        "outcome_version": config.outcome_version,
        "outcome_profile": config.outcome_profile,
        "outcome_config_hash": config.config_hash(),
        "outcome_cohort": cohort,
        "source_trade_permission_status": source_permission,
        "primary_evaluation_eligible": cohort == PRIMARY_COHORT and entry_status == ENTRY_VALID,
        "setup_quality": score_row.get("setup_quality", ""),
        "candidate_state": score_row.get("candidate_state", ""),
        "candidate_category": score_row.get("candidate_category", ""),
        "regime_state": score_row.get("regime_state", ""),
        "regime_confidence": score_row.get("regime_confidence", ""),
        "next_session_date": session_dates[0].isoformat() if session_dates else "",
        "entry_model": config.entry_model,
        "reference_entry_price": reference_entry,
        "t_close_reference_price": t_close_reference,
        "hypothetical_entry_price": entry,
        "gap_pct": gap_pct,
        "gap_from_t_close_pct": gap_from_t_close_pct,
        "gap_category": classify_gap(gap_pct, config),
        "entry_recheck_status": entry_status,
        "entry_valid": entry_status == ENTRY_VALID,
        "entry_rejection_reasons": ";".join(dedupe(rejection_reasons)),
        "original_stop_price": stop,
        "stop_price": stop,
        "selected_target_price": target,
        "target_price": target,
        "selected_target_basis": risk_row.get("selected_target_basis", ""),
        "target_basis": risk_row.get("selected_target_basis", ""),
        "effective_risk_per_share": effective_risk,
        "effective_reward_per_share": effective_reward,
        "effective_reward_risk": effective_rr,
        "risk_budget_rupees": position["risk_budget_rupees"],
        "quantity_by_risk": position["quantity_by_risk"],
        "quantity_by_cash": position["quantity_by_cash"],
        "hypothetical_quantity": position["structured_quantity"],
        "position_notional": position["position_notional"],
        "planned_rupee_risk": position["planned_rupee_risk"],
        "planned_risk_pct": position["planned_risk_pct"],
        "no_leverage_status": position["no_leverage_status"],
        "first_stop_session": "",
        "first_target_session": "",
        "same_bar_ambiguous": False,
        "stop_target_same_bar_ambiguous": False,
        "first_touch_outcome": INVALID_ENTRY,
        "forward_sessions_available": len(contiguous_bars),
        "right_censored": right_censored,
        "forward_data_safe": data_safe,
        "forward_data_status": forward_data_status(
            session_dates=session_dates,
            session_bars=session_bars,
            contiguous_count=len(contiguous_bars),
            right_censored=right_censored,
            data_safe=data_safe,
        ),
        "forward_data_reasons": ";".join(safety_reasons),
        "transaction_cost_status": config.transaction_cost_status,
        "slippage_status": config.slippage_status,
        "historical_execution_status": config.historical_execution_status,
        "trade_signal_status": config.trade_signal_status,
    }
    for component in COMPONENTS:
        row[f"{component}_points"] = score_row.get(f"{component}_points", "")
    for session_number in range(1, config.max_hold_sessions + 1):
        bar = session_bars[session_number - 1] if session_number <= len(session_bars) else None
        row.update(session_fields(session_number, bar))
    if entry_status == ENTRY_VALID:
        row.update(calculate_path_metrics(contiguous_bars, entry, stop, target, config.max_hold_sessions, right_censored))
    return row


def forward_data_status(
    *,
    session_dates: Sequence[date],
    session_bars: Sequence[OutcomeBar | None],
    contiguous_count: int,
    right_censored: bool,
    data_safe: bool,
) -> str:
    if not data_safe:
        return "FORWARD_DATA_UNSAFE"
    if not session_dates:
        return "RIGHT_CENSORED_NO_NEXT_SESSION"
    if not session_bars or session_bars[0] is None:
        return "NO_NEXT_SESSION_DATA"
    if contiguous_count < len(session_bars):
        return "MISSING_FORWARD_DATA"
    if right_censored:
        return "RIGHT_CENSORED"
    return "COMPLETE"


def position_sizing_config(config: StrategyOutcomeConfig) -> RiskStructureV11Config:
    risk_config = RiskStructureV11Config()
    return replace(
        risk_config,
        capital=replace(
            risk_config.capital,
            research_capital_rupees=config.research_capital_rupees,
            max_risk_per_trade_pct=config.max_risk_per_trade_pct,
        ),
    )


def session_fields(number: int, bar: OutcomeBar | None) -> dict[str, Any]:
    return {
        f"session_date_{number}": bar.trading_date.isoformat() if bar else "",
        f"open_{number}": bar.open if bar else "",
        f"high_{number}": bar.high if bar else "",
        f"low_{number}": bar.low if bar else "",
        f"close_{number}": bar.close if bar else "",
        f"horizon_available_{number}": False,
        f"close_return_pct_{number}": "",
        f"close_return_r_{number}": "",
        f"mfe_pct_{number}": "",
        f"mae_pct_{number}": "",
        f"mfe_r_{number}": "",
        f"mae_r_{number}": "",
        f"stop_touched_{number}": False,
        f"target_touched_{number}": False,
    }


def calculate_path_metrics(
    bars: Sequence[OutcomeBar],
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    max_hold_sessions: int,
    right_censored: bool,
) -> dict[str, Any]:
    risk = entry - stop
    output: dict[str, Any] = {}
    running_high = entry
    running_low = entry
    stop_seen = False
    target_seen = False
    first_stop: int | None = None
    first_target: int | None = None
    for number in range(1, max_hold_sessions + 1):
        if number > len(bars):
            continue
        bar = bars[number - 1]
        running_high = max(running_high, bar.high)
        running_low = min(running_low, bar.low)
        stop_now = bar.low <= stop
        target_now = bar.high >= target
        stop_seen = stop_seen or stop_now
        target_seen = target_seen or target_now
        if stop_now and first_stop is None:
            first_stop = number
        if target_now and first_target is None:
            first_target = number
        output.update(
            {
                f"horizon_available_{number}": True,
                f"close_return_pct_{number}": (bar.close - entry) / entry * Decimal("100"),
                f"close_return_r_{number}": (bar.close - entry) / risk,
                f"mfe_pct_{number}": max(Decimal("0"), (running_high - entry) / entry * Decimal("100")),
                f"mae_pct_{number}": max(Decimal("0"), (entry - running_low) / entry * Decimal("100")),
                f"mfe_r_{number}": max(Decimal("0"), (running_high - entry) / risk),
                f"mae_r_{number}": max(Decimal("0"), (entry - running_low) / risk),
                f"stop_touched_{number}": stop_seen,
                f"target_touched_{number}": target_seen,
            }
        )
    same_bar = first_stop is not None and first_stop == first_target
    if same_bar:
        first_touch = AMBIGUOUS
    elif first_target is not None and (first_stop is None or first_target < first_stop):
        first_touch = TARGET_FIRST
    elif first_stop is not None and (first_target is None or first_stop < first_target):
        first_touch = STOP_FIRST
    elif len(bars) < max_hold_sessions or right_censored:
        first_touch = INSUFFICIENT_FORWARD_DATA
    else:
        first_touch = NEITHER_WITHIN_HORIZON
    output.update(
        {
            "first_stop_session": first_stop or "",
            "first_target_session": first_target or "",
            "same_bar_ambiguous": same_bar,
            "stop_target_same_bar_ambiguous": same_bar,
            "first_touch_outcome": first_touch,
        }
    )
    return output


def run_pilot_validation(rows: Sequence[dict[str, Any]], config: StrategyOutcomeConfig) -> dict[str, Any]:
    cases: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
        ("A", "valid next-session primary entry", lambda row: is_primary(row) and row["entry_valid"]),
        ("B", "gap-up but still valid", lambda row: is_primary(row) and row["entry_valid"] and decimal_or_zero(row.get("gap_pct")) > config.gap_thresholds.flat_absolute_pct),
        ("C", "gap-up causing R:R below 1.5", lambda row: is_primary(row) and row["entry_recheck_status"] == ENTRY_INVALID_GAP),
        ("D", "open at or below frozen stop", lambda row: is_primary(row) and row["entry_recheck_status"] == ENTRY_INVALID_STOP_RELATION),
        ("E", "target touched before stop", lambda row: is_primary(row) and row["first_touch_outcome"] == TARGET_FIRST),
        ("F", "stop touched before target", lambda row: is_primary(row) and row["first_touch_outcome"] == STOP_FIRST),
        ("G", "same-bar stop and target ambiguity", lambda row: is_primary(row) and row["first_touch_outcome"] == AMBIGUOUS),
        ("H", "neither touched within four sessions", lambda row: is_primary(row) and row["first_touch_outcome"] == NEITHER_WITHIN_HORIZON),
        ("I", "right-censored near data end", lambda row: bool(row["right_censored"])),
        ("J", "positive MFE before stop-first", lambda row: is_primary(row) and row["first_touch_outcome"] == STOP_FIRST and decimal_or_zero(row.get("mfe_r_4")) > 0),
        ("K", "target-first with weak four-session close", lambda row: is_primary(row) and row["first_touch_outcome"] == TARGET_FIRST and decimal_or_zero(row.get("close_return_pct_4")) < 0),
        ("L", "neutral eligible", lambda row: is_primary(row) and row["entry_valid"] and row.get("regime_state") == "NEUTRAL"),
        ("M", "both-eligible candidate", lambda row: is_primary(row) and row["entry_valid"] and row.get("candidate_category") == "BOTH_ELIGIBLE"),
        ("N", "emerging-only candidate", lambda row: is_primary(row) and row["entry_valid"] and row.get("candidate_category") == "EMERGING_ONLY"),
    ]
    output_rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for code, description, predicate in cases:
        found = next((row for row in rows if predicate(row)), None)
        if found is None:
            output_rows.append(
                {
                    "pilot_case": code,
                    "scenario": description,
                    "result": "NOT_AVAILABLE_IN_POPULATION",
                    "validation_notes": "Exhaustive selected-cohort scan found no real row matching this optional scenario.",
                }
            )
            continue
        passed, checks = validate_outcome_row(found, config)
        output_rows.append(
            {
                "pilot_case": code,
                "scenario": description,
                "symbol": found["symbol"],
                "decision_date": found["decision_date"],
                "next_session_date": found["next_session_date"],
                "source_raw_strategy_score": found["source_raw_strategy_score"],
                "outcome_cohort": found["outcome_cohort"],
                "entry_recheck_status": found["entry_recheck_status"],
                "gap_pct": found["gap_pct"],
                "stop_price": found["stop_price"],
                "target_price": found["target_price"],
                "hypothetical_entry_price": found["hypothetical_entry_price"],
                "effective_reward_risk": found["effective_reward_risk"],
                "hypothetical_quantity": found["hypothetical_quantity"],
                "forward_ohlc_sequence": serialize_ohlc(found, config.max_hold_sessions),
                "mfe_r_4": found.get("mfe_r_4", ""),
                "mae_r_4": found.get("mae_r_4", ""),
                "first_stop_session": found["first_stop_session"],
                "first_target_session": found["first_target_session"],
                "same_bar_ambiguous": found["same_bar_ambiguous"],
                "first_touch_outcome": found["first_touch_outcome"],
                "result": "PASS" if passed else "FAIL",
                "validation_notes": ";".join(checks),
            }
        )
        selected.append({"case": code, "symbol": found["symbol"], "decision_date": found["decision_date"]})
    return {
        "passed": not any(row["result"] == "FAIL" for row in output_rows),
        "rows": output_rows,
        "selected_symbols_dates": selected,
        "unavailable_cases": [row["pilot_case"] for row in output_rows if row["result"] == "NOT_AVAILABLE_IN_POPULATION"],
    }


def validate_outcome_row(row: dict[str, Any], config: StrategyOutcomeConfig) -> tuple[bool, list[str]]:
    checks: list[tuple[str, bool]] = []
    decision = date.fromisoformat(str(row["decision_date"]))
    if row.get("next_session_date"):
        checks.append(("next_session_after_decision", date.fromisoformat(str(row["next_session_date"])) > decision))
    if row.get("hypothetical_entry_price") not in {"", None}:
        checks.append(("entry_equals_session_1_open", decimal_or_none(row["hypothetical_entry_price"]) == decimal_or_none(row["open_1"])))
    if row["entry_recheck_status"] == ENTRY_VALID:
        entry = decimal_or_zero(row["hypothetical_entry_price"])
        stop = decimal_or_zero(row["stop_price"])
        target = decimal_or_zero(row["target_price"])
        risk = entry - stop
        checks.extend(
            [
                ("risk_recalculated", decimal_or_none(row["effective_risk_per_share"]) == risk),
                ("rr_recalculated", close_decimal(decimal_or_none(row["effective_reward_risk"]), (target - entry) / risk)),
                ("rr_minimum", decimal_or_zero(row["effective_reward_risk"]) >= config.minimum_effective_reward_risk),
                ("quantity_positive", int(row["hypothetical_quantity"]) >= 1),
                ("no_leverage", row["no_leverage_status"] == "NO_LEVERAGE"),
                ("mfe_monotonic", monotonic_horizons(row, "mfe_pct")),
                ("mae_monotonic", monotonic_horizons(row, "mae_pct")),
                ("touch_temporal", touch_temporal_valid(row)),
                ("ambiguity_consistent", ambiguity_valid(row)),
            ]
        )
    elif row["entry_recheck_status"] == ENTRY_INVALID_GAP:
        checks.extend(
            [
                ("gap_is_up", decimal_or_zero(row.get("gap_pct")) > config.gap_thresholds.flat_absolute_pct),
                ("rr_below_minimum", decimal_or_zero(row.get("effective_reward_risk")) < config.minimum_effective_reward_risk),
            ]
        )
    elif row["entry_recheck_status"] == ENTRY_INVALID_RR:
        checks.append(("rr_below_minimum", decimal_or_zero(row.get("effective_reward_risk")) < config.minimum_effective_reward_risk))
    elif row["entry_recheck_status"] == ENTRY_INVALID_STOP_RELATION:
        checks.append(
            (
                "open_not_above_stop",
                decimal_or_zero(row.get("hypothetical_entry_price")) <= decimal_or_zero(row.get("stop_price")),
            )
        )
    elif row["entry_recheck_status"] == ENTRY_INVALID_CAPITAL:
        checks.append(("quantity_zero", int(row.get("hypothetical_quantity") or 0) < 1))
    elif row["entry_recheck_status"] == NO_NEXT_SESSION_DATA:
        checks.append(("next_session_bar_unavailable", row.get("hypothetical_entry_price") in {"", None}))
    elif row["entry_recheck_status"] == OTHER_INVALID and not row.get("forward_data_safe"):
        checks.append(("forward_data_unsafe", row.get("forward_data_status") == "FORWARD_DATA_UNSAFE"))
    failed = [name for name, passed in checks if not passed]
    return not failed, [f"{name}={'PASS' if passed else 'FAIL'}" for name, passed in checks]


def build_report_tables(rows: Sequence[dict[str, Any]], pilot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    primary = [row for row in rows if is_primary(row)]
    primary_valid = [row for row in primary if row["entry_valid"]]
    return {
        "entry_revalidation": entry_revalidation_rows(primary),
        "gap_analysis": gap_analysis_rows(primary),
        "horizons": horizon_report_rows(primary_valid),
        "first_touch": first_touch_report_rows(primary_valid),
        "scores": score_report_rows(rows),
        "regimes": grouped_report_rows(rows, "regime_state", include_exceptional=True),
        "candidate_categories": grouped_report_rows(primary_valid, "candidate_category"),
        "setup_quality": grouped_report_rows(primary_valid, "setup_quality"),
        "rr_bands": rr_report_rows(primary_valid),
        "pilot_validation": pilot["rows"],
    }


def entry_revalidation_rows(primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(primary)
    next_data = [row for row in primary if row.get("hypothetical_entry_price") not in {"", None}]
    safe = [row for row in next_data if row["forward_data_safe"]]
    stop_valid = [row for row in safe if decimal_or_zero(row.get("hypothetical_entry_price")) > decimal_or_zero(row.get("stop_price"))]
    rr_valid = [row for row in stop_valid if decimal_or_zero(row.get("effective_reward_risk")) >= Decimal("1.5")]
    quantity_valid = [row for row in rr_valid if int(row.get("hypothetical_quantity") or 0) >= 1]
    valid = [row for row in primary if row["entry_valid"]]
    stages = [
        ("ENTRY_ELIGIBLE_AT_T", primary),
        ("NEXT_SESSION_DATA_AVAILABLE", next_data),
        ("FORWARD_DATA_SAFE", safe),
        ("STOP_RELATION_VALID", stop_valid),
        ("EFFECTIVE_RR_GTE_1_5", rr_valid),
        ("QUANTITY_GTE_1", quantity_valid),
        ("VALID_HYPOTHETICAL_ENTRY", valid),
    ]
    return [
        {"sequence": index, "funnel_stage": name, "count": len(stage_rows), "rate_of_t_level_eligible_pct": rate(len(stage_rows), total)}
        for index, (name, stage_rows) in enumerate(stages, start=1)
    ]


def gap_analysis_rows(primary: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for category, grouped in sorted(group_by(primary, "gap_category").items()):
        output.append({"section": "GAP_CATEGORY", "category": category, **describe_rows(grouped)})
    for status, grouped in sorted(group_by(primary, "entry_recheck_status").items()):
        output.append({"section": "ENTRY_RECHECK_STATUS", "category": status, **describe_rows(grouped)})
    return output


def horizon_report_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for horizon in range(1, 5):
        available = [row for row in rows if truthy(row.get(f"horizon_available_{horizon}"))]
        ambiguous = [row for row in available if first_event_within(row, horizon) == AMBIGUOUS]
        neither = [row for row in available if first_event_within(row, horizon) == NEITHER_WITHIN_HORIZON]
        output.append(
            {
                "horizon_sessions": horizon,
                "available_rows": len(available),
                "mean_close_return_pct": mean_value(row.get(f"close_return_pct_{horizon}") for row in available),
                "median_close_return_pct": median_value(row.get(f"close_return_pct_{horizon}") for row in available),
                "median_mfe_pct": median_value(row.get(f"mfe_pct_{horizon}") for row in available),
                "median_mae_pct": median_value(row.get(f"mae_pct_{horizon}") for row in available),
                "target_touched_count": sum(truthy(row.get(f"target_touched_{horizon}")) for row in available),
                "target_touched_rate_pct": rate(sum(truthy(row.get(f"target_touched_{horizon}")) for row in available), len(available)),
                "stop_touched_count": sum(truthy(row.get(f"stop_touched_{horizon}")) for row in available),
                "stop_touched_rate_pct": rate(sum(truthy(row.get(f"stop_touched_{horizon}")) for row in available), len(available)),
                "ambiguous_count": len(ambiguous),
                "ambiguous_rate_pct": rate(len(ambiguous), len(available)),
                "neither_count": len(neither),
                "neither_rate_pct": rate(len(neither), len(available)),
            }
        )
    return output


def first_touch_report_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row["first_touch_outcome"]) for row in rows)
    states = (TARGET_FIRST, STOP_FIRST, AMBIGUOUS, NEITHER_WITHIN_HORIZON, INSUFFICIENT_FORWARD_DATA)
    return [{"first_touch_outcome": state, "count": counts[state], "rate_pct": rate(counts[state], len(rows))} for state in states]


def score_report_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    cohort_rows = {
        "ENTRY_ELIGIBLE": [row for row in rows if is_primary(row)],
        "FULL_SCORE_BELOW_THRESHOLD": [row for row in rows if row["outcome_cohort"] == COUNTERFACTUAL_COHORT],
    }
    for cohort_name, selected in cohort_rows.items():
        by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in selected:
            by_band[research_score_band(decimal_or_zero(row.get("source_raw_strategy_score")))].append(row)
        for band, grouped in sorted(by_band.items()):
            output.append({"section": "SCORE_BAND", "cohort": cohort_name, "dimension": "raw_score_band", "value": band, **describe_rows(grouped)})
        for exact in range(80, 86):
            grouped = [row for row in selected if decimal_or_zero(row.get("source_raw_strategy_score")) == Decimal(exact)]
            output.append({"section": "EXACT_SCORE", "cohort": cohort_name, "dimension": "raw_score", "value": exact, **describe_rows(grouped)})
    primary = cohort_rows["ENTRY_ELIGIBLE"]
    for component in COMPONENTS:
        grouped_values = group_by(primary, f"{component}_points")
        for points, grouped in sorted(grouped_values.items(), key=lambda item: decimal_or_zero(item[0])):
            output.append({"section": "SCORE_COMPONENT", "cohort": "ENTRY_ELIGIBLE", "dimension": component, "value": points, **describe_rows(grouped)})
    return output


def grouped_report_rows(
    rows: Sequence[dict[str, Any]],
    field: str,
    *,
    include_exceptional: bool = False,
) -> list[dict[str, Any]]:
    selected = [row for row in rows if row["entry_valid"] and (is_primary(row) or (include_exceptional and row["outcome_cohort"] == EXCEPTIONAL_COHORT))]
    output: list[dict[str, Any]] = []
    for (cohort, value), grouped in sorted(group_by_pair(selected, "outcome_cohort", field).items()):
        output.append({"outcome_cohort": cohort, "dimension": field, "value": value, **describe_rows(grouped)})
    return output


def rr_report_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[reward_risk_band(decimal_or_zero(row.get("effective_reward_risk")))].append(row)
    return [{"rr_band": band, **describe_rows(grouped_rows)} for band, grouped_rows in sorted(grouped.items())]


def describe_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("entry_valid")]
    denominator = len(valid)
    counts = Counter(str(row.get("first_touch_outcome", "")) for row in valid)
    return {
        "source_rows": len(rows),
        "valid_entry_rows": denominator,
        "median_gap_pct": median_value(row.get("gap_pct") for row in valid),
        "median_effective_rr": median_value(row.get("effective_reward_risk") for row in valid),
        "median_mfe_pct_4": median_value(row.get("mfe_pct_4") for row in valid),
        "median_mae_pct_4": median_value(row.get("mae_pct_4") for row in valid),
        "median_close_return_pct_4": median_value(row.get("close_return_pct_4") for row in valid),
        "target_first_count": counts[TARGET_FIRST],
        "target_first_rate_pct": rate(counts[TARGET_FIRST], denominator),
        "stop_first_count": counts[STOP_FIRST],
        "stop_first_rate_pct": rate(counts[STOP_FIRST], denominator),
        "ambiguous_count": counts[AMBIGUOUS],
        "ambiguous_rate_pct": rate(counts[AMBIGUOUS], denominator),
        "neither_count": counts[NEITHER_WITHIN_HORIZON],
        "neither_rate_pct": rate(counts[NEITHER_WITHIN_HORIZON], denominator),
    }


def build_summary_report(
    *,
    engine_config: StrategyOutcomeEngineConfig,
    rows: Sequence[dict[str, Any]],
    pilot: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
    score_baseline: Any,
    hashes_before: dict[str, str],
    hashes_after: dict[str, str],
    dataset_hash: str,
    runtime_seconds: float,
) -> dict[str, Any]:
    primary = [row for row in rows if is_primary(row)]
    valid = [row for row in primary if row["entry_valid"]]
    invalid = [row for row in primary if not row["entry_valid"]]
    outcome_counts = Counter(str(row["first_touch_outcome"]) for row in valid)
    sanity = sanity_summary(rows)
    statuses = Counter(str(row["entry_recheck_status"]) for row in primary)
    report_paths = report_paths_for(engine_config)
    return {
        "phase": "Step 02.11",
        "command": "Command 01",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outcome": {
            "version": engine_config.outcome_config.outcome_version,
            "profile": engine_config.outcome_config.outcome_profile,
            "config_hash": engine_config.outcome_config.config_hash(),
            "status": "PROVISIONAL_RESEARCH_EVALUATION_BASELINE",
        },
        "frozen_score": {
            "version": score_baseline.version,
            "profile": score_baseline.profile,
            "config_hash": score_baseline.config_hash,
            "dataset_hash_expected": STRATEGY_SCORE_V1_DATASET_HASH,
            "dataset_hash_observed": file_sha256(engine_config.score_dataset_path),
            "verified": True,
        },
        "active_risk": {
            "version": CURRENT_RISK_STRUCTURE_VERSION,
            "config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
            "dataset_hash_expected": RISK_STRUCTURE_V1_1_DATASET_HASH,
            "dataset_hash_observed": file_sha256(engine_config.risk_dataset_path),
            "verified": True,
        },
        "methodology": engine_config.outcome_config.snapshot(),
        "cohorts": dict(Counter(str(row["outcome_cohort"]) for row in rows)),
        "generation": {
            "full_generation_completed": engine_config.full_generation,
            "total_outcome_rows": len(rows),
            "entry_eligible_source_rows": len(primary),
            "next_session_data_available_count": sum(row.get("hypothetical_entry_price") not in {"", None} for row in primary),
            "valid_hypothetical_entry_count": len(valid),
            "invalid_hypothetical_entry_count": len(invalid),
            "invalid_open_at_or_below_stop": statuses[ENTRY_INVALID_STOP_RELATION],
            "invalid_effective_rr_below_1_5": statuses[ENTRY_INVALID_RR] + statuses[ENTRY_INVALID_GAP],
            "invalid_quantity_zero": statuses[ENTRY_INVALID_CAPITAL],
            "invalid_forward_data_unsafe": sum(not row["forward_data_safe"] for row in primary),
            "other_invalid_count": sum(
                row["entry_recheck_status"] == OTHER_INVALID and row["forward_data_safe"]
                for row in primary
            ),
            "no_next_session_data_count": statuses[NO_NEXT_SESSION_DATA],
            "gap_up_invalidation_count": statuses[ENTRY_INVALID_GAP],
            "median_gap_pct": median_value(row.get("gap_pct") for row in primary),
            "p90_gap_pct": percentile_value((row.get("gap_pct") for row in primary), Decimal("0.90")),
            "median_effective_reward_risk": median_value(row.get("effective_reward_risk") for row in valid),
            "median_hypothetical_quantity": median_value(row.get("hypothetical_quantity") for row in valid),
            "median_planned_risk_pct": median_value(row.get("planned_risk_pct") for row in valid),
            "right_censored_count": sum(bool(row["right_censored"]) for row in primary),
            "first_touch_counts": dict(outcome_counts),
            "first_touch_rates_pct": {state: rate(outcome_counts[state], len(valid)) for state in (TARGET_FIRST, STOP_FIRST, AMBIGUOUS, NEITHER_WITHIN_HORIZON, INSUFFICIENT_FORWARD_DATA)},
        },
        "horizons": tables["horizons"],
        "descriptive_profiles": {
            "bullish_eligible": describe_rows([row for row in valid if row["regime_state"] == "BULLISH"]),
            "neutral_eligible": describe_rows([row for row in valid if row["regime_state"] == "NEUTRAL"]),
            "bearish_exceptional": describe_rows([row for row in rows if row["outcome_cohort"] == EXCEPTIONAL_COHORT and row["entry_valid"]]),
            "emerging_only": describe_rows([row for row in valid if row["candidate_category"] == "EMERGING_ONLY"]),
            "confirmed_only": describe_rows([row for row in valid if row["candidate_category"] == "CONFIRMED_ONLY"]),
            "both_eligible": describe_rows([row for row in valid if row["candidate_category"] == "BOTH_ELIGIBLE"]),
            "strong_setup": describe_rows([row for row in valid if row["setup_quality"] == "STRONG"]),
            "valid_setup": describe_rows([row for row in valid if row["setup_quality"] == "VALID"]),
        },
        "pilot": pilot,
        "sanity": sanity,
        "regression": {
            "hashes_before": hashes_before,
            "hashes_after": hashes_after,
            "checks": {name: hashes_before[name] == hashes_after[name] for name in hashes_before},
            "all_frozen_datasets_unchanged": hashes_before == hashes_after,
        },
        "separation": {
            "future_data_used_only_in_outcome_layer": True,
            "outcomes_are_signal_inputs": False,
            "membership_change_terminates_holding": False,
            "counterfactual_cohort_separate": True,
            "exceptional_cohort_separate": True,
            "preview_cohort_separate": True,
        },
        "safety": {
            "signals_generated": 0,
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
            "broker_api_calls": 0,
        },
        "artifacts": {
            "dataset_path": str(engine_config.output_dataset_path),
            "dataset_sha256": dataset_hash,
            "dataset_size_bytes": engine_config.output_dataset_path.stat().st_size if engine_config.output_dataset_path.exists() else 0,
            "report_paths": report_paths,
        },
        "runtime_seconds": round(runtime_seconds, 3),
        "known_limitations": [
            "Daily bars cannot resolve intraday stop/target order when both first occur in one candle.",
            "Brokerage, taxes, fees, slippage, and exact fill behavior are not modeled.",
            "The four-session window is descriptive and does not implement an exit or P&L engine.",
            "Comparison cohorts are counterfactual research populations, not eligible Strategy V1 trades.",
            "Rows at the dataset boundary retain partial horizons and are right-censored.",
        ],
        "ready_for_review": pilot["passed"] and hashes_before == hashes_after and not any(sanity.values()),
    }


def sanity_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    valid = [row for row in rows if row["entry_valid"]]
    return {
        "mfe_monotonicity_violations": sum(not monotonic_horizons(row, "mfe_pct") for row in valid),
        "mae_monotonicity_violations": sum(not monotonic_horizons(row, "mae_pct") for row in valid),
        "stop_target_temporal_violations": sum(not touch_temporal_valid(row) for row in valid),
        "same_bar_ambiguity_violations": sum(not ambiguity_valid(row) for row in valid),
        "negative_mfe_violations": sum(any(decimal_or_zero(row.get(f"mfe_pct_{h}")) < 0 for h in range(1, 5) if truthy(row.get(f"horizon_available_{h}"))) for row in valid),
        "negative_mae_magnitude_violations": sum(any(decimal_or_zero(row.get(f"mae_pct_{h}")) < 0 for h in range(1, 5) if truthy(row.get(f"horizon_available_{h}"))) for row in valid),
    }


def write_outcome_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=OUTCOME_OUTPUT_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow(json_safe(row))


def write_outcome_reports(
    config: StrategyOutcomeEngineConfig,
    report: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
) -> None:
    write_json(config.report_path("summary.json"), report)
    for name, rows in tables.items():
        path = config.report_path(f"{name}.csv")
        write_csv(path, rows, union_fieldnames(rows))


def write_outcome_markdown(report: dict[str, Any], path: Path) -> None:
    generation = report["generation"]
    lines = [
        "# Strategy V1 Historical Outcomes",
        "",
        "STATUS: ACTIVE_HISTORICAL_OUTCOME_BASELINE",
        "",
        "Step 02.11 - Historical Outcome Labeling: COMPLETE",
        "",
        "## Boundary",
        "",
        "- STRATEGY_OUTCOME_V1 intentionally uses future adjusted daily prices for evaluation only.",
        "- Outcome fields are separated from features, candidates, setups, regime, entry, risk, and score generation.",
        "- Rows are historical opportunities or explicitly marked comparison cohorts; they are not executed trades.",
        "- No signal, broker action, order, remote migration, or Supabase persistence is performed.",
        "",
        "## Entry and Risk",
        "",
        "- Decision date T is the frozen daily EOD score date; the earliest hypothetical entry is the next valid NSE session.",
        "- The baseline entry model uses the T+1 adjusted open, never the T close as a post-score fill.",
        "- The RISK_STRUCTURE_V1_1 stop and selected target remain frozen.",
        "- Per-share risk, reward:risk, affordability, whole-share quantity, notional, and planned risk are recalculated at T+1 open.",
        "- A valid entry requires open above stop, effective R:R of at least 1.5, quantity of at least one, and no leverage.",
        "",
        "## Forward Window",
        "",
        "- Session 1 is the entry session; sessions 2-4 are the next three valid NSE sessions.",
        "- Close return is measured from entry open to each horizon close.",
        "- MFE is cumulative maximum high above entry, stored as percent and initial-risk multiples.",
        "- MAE is cumulative adverse magnitude from entry to minimum low, stored as non-negative percent and initial-risk multiples.",
        "- Frozen stop and target touches are cumulative by horizon.",
        "- If stop and target first appear in the same daily candle, the result is AMBIGUOUS; no intraday path is invented.",
        "- Partial forward histories are retained. Dataset-end cases are RIGHT_CENSORED, not failures.",
        "- Forward windows crossing CORPORATE_ACTION_EXCLUSIONS_V1 are marked FORWARD_DATA_UNSAFE.",
        "- Constituent membership changes after entry do not terminate the mechanical observation window.",
        "",
        "## Current Output",
        "",
        f"- Outcome version/profile: {report['outcome']['version']} / {report['outcome']['profile']}",
        f"- Outcome config hash: {report['outcome']['config_hash']}",
        f"- Dataset hash: {report['artifacts']['dataset_sha256']}",
        f"- Total outcome rows: {generation['total_outcome_rows']}",
        f"- ENTRY_ELIGIBLE source rows: {generation['entry_eligible_source_rows']}",
        f"- Valid hypothetical entries: {generation['valid_hypothetical_entry_count']}",
        f"- Invalid at next-session recheck: {generation['invalid_hypothetical_entry_count']}",
        "- Structural audit: STRATEGY_OUTCOME_AUDIT_V1 / STABLE_WITH_REVIEW_NOTES.",
        "- Baseline decision: A_FREEZE_UNCHANGED.",
        "- Audit document: docs/strategy-v1-historical-outcomes-audit.md.",
        "- The four-session horizon remains frozen; LIKELY_TOO_SHORT is a research note, not a baseline defect.",
        "- The descriptive pattern is WEAK and is not a live-performance or profitability claim.",
        "",
        "## Deliberate Omissions",
        "",
        "- Transaction costs: NOT_MODELED.",
        "- Slippage: NOT_MODELED.",
        "- No trailing stop, break-even move, partial exit, dynamic target, forced P&L, backtest, or optimization is implemented.",
        "- Descriptive cohort reports must not be used to change frozen Strategy V1 rules in this command.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def report_paths_for(config: StrategyOutcomeEngineConfig) -> list[str]:
    return [
        str(config.report_path("summary.json")),
        *[
            str(config.report_path(f"{name}.csv"))
            for name in (
                "entry_revalidation",
                "gap_analysis",
                "horizons",
                "first_touch",
                "scores",
                "regimes",
                "candidate_categories",
                "setup_quality",
                "rr_bands",
                "pilot_validation",
            )
        ],
    ]


def first_event_within(row: dict[str, Any], horizon: int) -> str:
    first_stop = int(row.get("first_stop_session") or 0)
    first_target = int(row.get("first_target_session") or 0)
    stop = first_stop if 0 < first_stop <= horizon else 0
    target = first_target if 0 < first_target <= horizon else 0
    if stop and target and stop == target:
        return AMBIGUOUS
    if target and (not stop or target < stop):
        return TARGET_FIRST
    if stop and (not target or stop < target):
        return STOP_FIRST
    return NEITHER_WITHIN_HORIZON


def monotonic_horizons(row: dict[str, Any], prefix: str) -> bool:
    values = [
        decimal_or_none(row.get(f"{prefix}_{horizon}"))
        for horizon in range(1, 5)
        if truthy(row.get(f"horizon_available_{horizon}"))
    ]
    return all(left is not None and right is not None and left <= right for left, right in zip(values, values[1:]))


def touch_temporal_valid(row: dict[str, Any]) -> bool:
    for touch, first_field in (("stop", "first_stop_session"), ("target", "first_target_session")):
        first = int(row.get(first_field) or 0)
        for horizon in range(1, 5):
            observed = truthy(row.get(f"{touch}_touched_{horizon}"))
            expected = bool(first and horizon >= first and truthy(row.get(f"horizon_available_{horizon}")))
            if observed != expected:
                return False
    return True


def ambiguity_valid(row: dict[str, Any]) -> bool:
    first_stop = int(row.get("first_stop_session") or 0)
    first_target = int(row.get("first_target_session") or 0)
    same_bar = bool(first_stop and first_stop == first_target)
    return (
        truthy(row.get("same_bar_ambiguous")) == same_bar
        and truthy(row.get("stop_target_same_bar_ambiguous")) == same_bar
        and ((row.get("first_touch_outcome") == AMBIGUOUS) if same_bar else (row.get("first_touch_outcome") != AMBIGUOUS))
    )


def serialize_ohlc(row: dict[str, Any], maximum: int) -> str:
    return "|".join(
        f"{row.get(f'session_date_{h}', '')}:{row.get(f'open_{h}', '')}/{row.get(f'high_{h}', '')}/{row.get(f'low_{h}', '')}/{row.get(f'close_{h}', '')}"
        for h in range(1, maximum + 1)
        if row.get(f"session_date_{h}")
    )


def research_score_band(score: Decimal) -> str:
    if score < 70:
        return "<70"
    if score < 75:
        return "70-74"
    if score < 80:
        return "75-79"
    if score < 83:
        return "80-82"
    if score <= 85:
        return "83-85"
    return ">85"


def reward_risk_band(value: Decimal) -> str:
    if value < Decimal("1.5"):
        return "<1.5"
    if value < Decimal("2"):
        return "1.5-2"
    if value < Decimal("2.5"):
        return "2-2.5"
    return ">=2.5"


def group_by(rows: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field, ""))].append(row)
    return dict(grouped)


def group_by_pair(rows: Sequence[dict[str, Any]], first: str, second: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get(first, "")), str(row.get(second, "")))].append(row)
    return dict(grouped)


def union_fieldnames(rows: Sequence[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    return fields or ["status"]


def is_primary(row: dict[str, Any]) -> bool:
    return row.get("outcome_cohort") == PRIMARY_COHORT


def percent_change(value: Decimal | None, reference: Decimal | None) -> Decimal | None:
    if value is None or reference is None or reference <= 0:
        return None
    return (value / reference - Decimal("1")) * Decimal("100")


def decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return decimal_or_none(value) or Decimal("0")


def close_decimal(left: Decimal | None, right: Decimal | None, tolerance: Decimal = Decimal("0.000000001")) -> bool:
    return left is not None and right is not None and abs(left - right) <= tolerance


def truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def median_value(values: Iterable[Any]) -> Decimal | None:
    parsed = [item for value in values if (item := decimal_or_none(value)) is not None]
    return Decimal(str(statistics.median(parsed))) if parsed else None


def mean_value(values: Iterable[Any]) -> Decimal | None:
    parsed = [item for value in values if (item := decimal_or_none(value)) is not None]
    return sum(parsed, Decimal("0")) / Decimal(len(parsed)) if parsed else None


def percentile_value(values: Iterable[Any], percentile: Decimal) -> Decimal | None:
    parsed = sorted(item for value in values if (item := decimal_or_none(value)) is not None)
    if not parsed:
        return None
    index = int((Decimal(len(parsed) - 1) * percentile).to_integral_value())
    return parsed[index]


def rate(numerator: int, denominator: int) -> Decimal:
    return Decimal("0") if denominator <= 0 else Decimal(numerator) / Decimal(denominator) * Decimal("100")


def dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)

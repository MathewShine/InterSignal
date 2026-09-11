from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.portfolio_baseline import (
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
    CURRENT_PORTFOLIO_BACKTEST_PROFILE,
    CURRENT_PORTFOLIO_BACKTEST_VERSION,
    EXPECTED_METRICS,
    get_current_portfolio_backtest_baseline,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig, json_ready
from app.backtesting.portfolio_engine import (
    AMBIGUOUS_SAME_BAR_EXIT,
    SKIP_INSUFFICIENT_CASH,
    SKIP_MAX_POSITIONS,
    SKIP_OTHER,
    SKIP_PORTFOLIO_RISK_LIMIT,
    SKIP_SAME_SYMBOL_ALREADY_OPEN,
    SKIP_ZERO_QUANTITY,
    STOP_EXIT,
    TARGET_EXIT,
    TIME_EXIT,
    calculate_portfolio_quantity,
    load_frozen_opportunities,
)
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset
from app.strategy.outcomes.outcome_engine import (
    OutcomeBar,
    StrategyOutcomeEngineConfig,
    forward_safety,
    load_adjusted_market_history,
    load_forward_exclusions,
    resolve_next_sessions,
)

STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION = "STRATEGY_DIAGNOSTIC_FRAMEWORK_V1"
STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE = "SWING_STRATEGY_DIAGNOSTICS_V1"
PROMOTION_ALLOWED = False
PERFORMANCE_SCOPE = "HISTORICAL_RESEARCH_ONLY"
COST_STATUS = "NOT_MODELED"
SLIPPAGE_STATUS = "NOT_MODELED"

EXPERIMENT_FAMILIES = (
    "RANKING_DIAGNOSTIC",
    "ENTRY_TIMING_DIAGNOSTIC",
    "EXIT_DIAGNOSTIC",
    "HOLD_HORIZON_DIAGNOSTIC",
    "TARGET_DIAGNOSTIC",
    "STOP_DIAGNOSTIC",
    "SCORE_CALIBRATION_DIAGNOSTIC",
    "REGIME_DIAGNOSTIC",
    "PORTFOLIO_CAPACITY_DIAGNOSTIC",
    "COST_SENSITIVITY_DIAGNOSTIC",
)
EXPERIMENT_STATUSES = (
    "REGISTERED",
    "READY",
    "RUNNING",
    "COMPLETE",
    "REJECTED",
    "INVALID",
    "FAILED",
)
RESEARCH_HYPOTHESES = {
    "H1": "The four-position limit plus crowded days may make selection order a major determinant of portfolio performance.",
    "H2": "Next-open entry may lose edge after strong EOD momentum and positive gaps.",
    "H3": "Many positions time-exit after useful favorable movement; frozen targets may be too distant for a four-session window.",
    "H4": "Four sessions may be too short for some momentum setups.",
    "H5": "Stop losses dominate negative P&L; some stop-outs may have had earlier favorable excursion.",
    "H6": "Raw scores 80–85 may not be monotonic with portfolio returns.",
    "H7": "Neutral-regime behavior may be weaker than Bullish-regime behavior.",
    "H8": "Max-position pressure may materially distort which mechanically valid opportunities enter.",
    "H9": "Weak gross edge may be materially reduced by realistic transaction costs.",
}
AUTHORIZED_EXPERIMENT_IDS = (
    "EXP-RANK-001",
    "EXP-RANK-002",
    "EXP-RANK-003",
    "EXP-RANK-004",
    "EXP-HOLD-001",
    "EXP-HOLD-002",
    "EXP-HOLD-003",
    "EXP-HOLD-004",
    "EXP-ENTRY-001",
    "EXP-ENTRY-002",
    "EXP-ENTRY-003",
    "EXP-ENTRY-004",
)
PORTFOLIO_EXPERIMENT_IDS = AUTHORIZED_EXPERIMENT_IDS[:8]
RANKING_EXPERIMENT_IDS = AUTHORIZED_EXPERIMENT_IDS[:4]
HOLD_EXPERIMENT_IDS = AUTHORIZED_EXPERIMENT_IDS[4:8]
ENTRY_EXPERIMENT_IDS = AUTHORIZED_EXPERIMENT_IDS[8:]

BASELINE_DEPENDENCY = (
    CURRENT_PORTFOLIO_BACKTEST_VERSION,
    CURRENT_PORTFOLIO_BACKTEST_PROFILE,
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
)
METRIC_DEFINITIONS = {
    "portfolio": (
        "trades, admission rate, ending equity, gross return, CAGR, maximum drawdown, "
        "realized-R distribution, exit rates, turnover, yearly returns"
    ),
    "comparison": (
        "trade-count/equity/return/CAGR/drawdown/mean-R deltas, trade-set Jaccard, "
        "entry-source overlap, skip-profile delta"
    ),
    "gap_cohort": (
        "source and admitted counts, admission rate, effective R:R, four-session MFE/MAE, "
        "gross P&L, realized R, and exit distribution"
    ),
    "ranking_sensitivity_thresholds": (
        "EXTREME if minimum baseline Jaccard <0.50 or absolute return/drawdown delta >15pp; "
        "HIGH if <0.70 or >8pp; MODERATE if <0.90 or >3pp; otherwise LOW"
    ),
    "hold_sensitivity_thresholds": (
        "HIGH if minimum baseline Jaccard <0.50 or absolute return/drawdown delta >15pp; "
        "MATERIAL if <0.80 or >5pp; otherwise STABLE"
    ),
    "gap_classification_thresholds": (
        "MATERIAL_DIFFERENCE if cohort mean-realized-R range >=0.25; MIXED if >=0.10; "
        "otherwise NO_CLEAR_RELATIONSHIP; any cohort under 20 is INCONCLUSIVE"
    ),
}


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    experiment_id: str
    family: str
    name: str
    description: str
    hypothesis: str
    parameters: tuple[tuple[str, Any], ...]
    outcome_fields_used_for_evaluation: tuple[str, ...]
    changes_strategy_semantics: bool
    changes_portfolio_mechanics: bool
    registered_at: str
    status: str = "REGISTERED"
    parameters_locked_before_run: bool = True
    diagnostic_only: bool = True
    eligible_for_promotion: bool = False
    pre_registered: bool = True

    @property
    def parameter_map(self) -> dict[str, Any]:
        return dict(self.parameters)

    @property
    def parameter_hash(self) -> str:
        return canonical_hash(self.parameter_map)

    def pre_registration_hash(self, baseline_hashes: Mapping[str, str]) -> str:
        return calculate_pre_registration_hash(self, baseline_hashes)

    def record(self, baseline_hashes: Mapping[str, str], *, status: str | None = None) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "family": self.family,
            "name": self.name,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "baseline_dependency": {
                "backtest_version": BASELINE_DEPENDENCY[0],
                "backtest_profile": BASELINE_DEPENDENCY[1],
                "backtest_config_hash": BASELINE_DEPENDENCY[2],
                "hashes": dict(baseline_hashes),
            },
            "parameters": self.parameter_map,
            "parameter_hash": self.parameter_hash,
            "parameters_locked_before_run": self.parameters_locked_before_run,
            "outcome_fields_used_for_evaluation": list(self.outcome_fields_used_for_evaluation),
            "changes_strategy_semantics": self.changes_strategy_semantics,
            "changes_portfolio_mechanics": self.changes_portfolio_mechanics,
            "diagnostic_only": self.diagnostic_only,
            "eligible_for_promotion": self.eligible_for_promotion,
            "pre_registered": self.pre_registered,
            "pre_registration_hash": self.pre_registration_hash(baseline_hashes),
            "registered_at": self.registered_at,
            "status": status or self.status,
        }


@dataclass(slots=True)
class ExperimentState:
    definition: ExperimentDefinition
    status: str = "REGISTERED"
    result_fingerprint: str | None = None
    failure_reason: str | None = None


@dataclass(slots=True)
class ExperimentExecution:
    result: dict[str, Any]
    trades: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    daily: list[dict[str, Any]] = field(default_factory=list)

    def canonical_fingerprint(self) -> str:
        return canonical_hash(self.result)


class ExperimentRegistry:
    def __init__(self, baseline_hashes: Mapping[str, str]) -> None:
        self.baseline_hashes = dict(baseline_hashes)
        self._states: dict[str, ExperimentState] = {}

    def register(self, definition: ExperimentDefinition) -> None:
        if definition.experiment_id not in AUTHORIZED_EXPERIMENT_IDS:
            raise ValueError(f"Unauthorized Command 01 experiment: {definition.experiment_id}")
        if definition.family not in EXPERIMENT_FAMILIES:
            raise ValueError(f"Unknown experiment family: {definition.family}")
        if definition.experiment_id in self._states:
            existing = self._states[definition.experiment_id]
            if existing.status == "COMPLETE":
                raise ValueError(
                    f"Completed experiment {definition.experiment_id} is immutable; create a new experiment ID"
                )
            raise ValueError(f"Experiment ID already registered: {definition.experiment_id}")
        if definition.eligible_for_promotion or not definition.diagnostic_only:
            raise ValueError("Command 01 experiments must be diagnostic-only and not promotion-eligible")
        self._states[definition.experiment_id] = ExperimentState(definition=definition)

    def mark_ready(self, experiment_id: str) -> None:
        state = self.state(experiment_id)
        if state.status != "REGISTERED":
            raise ValueError(f"Experiment {experiment_id} cannot move from {state.status} to READY")
        state.status = "READY"

    def run(
        self,
        experiment_id: str,
        runner: Callable[[ExperimentDefinition], ExperimentExecution],
        *,
        hash_reader: Callable[[], Mapping[str, str]],
    ) -> ExperimentExecution | None:
        state = self.state(experiment_id)
        if state.status != "READY":
            raise ValueError(f"Experiment {experiment_id} is not READY")
        state.status = "RUNNING"
        before = dict(hash_reader())
        try:
            execution = runner(state.definition)
            after = dict(hash_reader())
            if before != self.baseline_hashes or after != before:
                raise ValueError("Frozen baseline hash mutation detected")
            execution.result["baseline_hashes"] = after
            execution.result["baseline_hashes_before"] = before
            execution.result["baseline_hashes_after"] = after
            execution.result["baseline_hashes_unchanged"] = after == before
            execution.result["baseline_mutation_violations"] = 0
            execution.result["run_status"] = "COMPLETE"
            state.result_fingerprint = execution.canonical_fingerprint()
            state.status = "COMPLETE"
            return execution
        except Exception as exc:
            state.status = "FAILED"
            state.failure_reason = f"{exc.__class__.__name__}: {exc}"
            return None

    def state(self, experiment_id: str) -> ExperimentState:
        try:
            return self._states[experiment_id]
        except KeyError as exc:
            raise ValueError(f"Experiment is not registered: {experiment_id}") from exc

    def records(self) -> list[dict[str, Any]]:
        return [
            {
                **self._states[experiment_id].definition.record(
                    self.baseline_hashes,
                    status=self._states[experiment_id].status,
                ),
                "result_fingerprint": self._states[experiment_id].result_fingerprint,
                "failure_reason": self._states[experiment_id].failure_reason,
            }
            for experiment_id in AUTHORIZED_EXPERIMENT_IDS
            if experiment_id in self._states
        ]


@dataclass(slots=True)
class DiagnosticContext:
    repo_root: Path
    data_dir: Path
    opportunities: list[dict[str, str]]
    baseline_trades: list[dict[str, str]]
    sessions: list[date]
    bars: dict[tuple[str, str], OutcomeBar]
    exclusions: dict[str, list[Any]]
    baseline_hashes: dict[str, str]
    baseline_summary: dict[str, Any]
    horizon_cache: dict[int, tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]] = field(
        default_factory=dict
    )


def build_experiment_definitions(registered_at: str | None = None) -> tuple[ExperimentDefinition, ...]:
    timestamp = registered_at or datetime.now(timezone.utc).isoformat()
    common_portfolio_fields = (
        "exit_date",
        "exit_price",
        "exit_reason",
        "gross_pnl",
        "realized_r_multiple",
        "daily_portfolio_equity",
    )
    gap_fields = (
        "gap_from_t_close_pct",
        "effective_reward_risk",
        "mfe_r_4",
        "mae_r_4",
        "gross_pnl",
        "realized_r_multiple",
        "exit_reason",
    )
    definitions = (
        _definition(timestamp, "EXP-RANK-001", "RANKING_DIAGNOSTIC", "BASELINE_RANK_REPRODUCTION", "Reproduce the frozen ranking exactly.", "H1 — Portfolio results should exactly reproduce under the frozen ranking.", {"ranking": "BASELINE_RANK", "max_hold_sessions": 4}, common_portfolio_fields, False, False),
        _definition(timestamp, "EXP-RANK-002", "RANKING_DIAGNOSTIC", "SCORE_ONLY_RANK", "Replace only the admission ordering adapter with score then symbol.", "H1 — Crowded-day admission may be materially sensitive to selection order.", {"ranking": "SCORE_ONLY", "max_hold_sessions": 4}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-RANK-003", "RANKING_DIAGNOSTIC", "RR_FIRST_RANK", "Replace only the admission ordering adapter with R:R, score, then symbol.", "H1 — Crowded-day admission may be materially sensitive to selection order.", {"ranking": "RR_FIRST", "max_hold_sessions": 4}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-RANK-004", "RANKING_DIAGNOSTIC", "SETUP_FIRST_RANK", "Replace only the admission ordering adapter with setup, score, R:R, then symbol.", "H1 — Crowded-day admission may be materially sensitive to selection order.", {"ranking": "SETUP_FIRST", "max_hold_sessions": 4}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-HOLD-001", "HOLD_HORIZON_DIAGNOSTIC", "BASELINE_4_SESSION", "Reproduce the frozen four-session horizon.", "H4 — The frozen four-session horizon provides the comparison anchor.", {"ranking": "BASELINE_RANK", "max_hold_sessions": 4}, common_portfolio_fields, False, False),
        _definition(timestamp, "EXP-HOLD-002", "HOLD_HORIZON_DIAGNOSTIC", "6_SESSION_DIAGNOSTIC", "Chronologically simulate a six-session time-exit horizon.", "H4 — Some momentum setups may require more than four sessions.", {"ranking": "BASELINE_RANK", "max_hold_sessions": 6}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-HOLD-003", "HOLD_HORIZON_DIAGNOSTIC", "8_SESSION_DIAGNOSTIC", "Chronologically simulate an eight-session time-exit horizon.", "H4 — Some momentum setups may require more than four sessions.", {"ranking": "BASELINE_RANK", "max_hold_sessions": 8}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-HOLD-004", "HOLD_HORIZON_DIAGNOSTIC", "10_SESSION_DIAGNOSTIC", "Chronologically simulate a ten-session time-exit horizon.", "H4 — Some momentum setups may require more than four sessions.", {"ranking": "BASELINE_RANK", "max_hold_sessions": 10}, common_portfolio_fields, False, True),
        _definition(timestamp, "EXP-ENTRY-001", "ENTRY_TIMING_DIAGNOSTIC", "NEXT_OPEN_BASELINE", "Describe all frozen next-open opportunities and admitted trades.", "H2 — Next-open entry is the descriptive cohort anchor.", {"gap_group": "ALL_NEXT_OPEN"}, gap_fields, False, False),
        _definition(timestamp, "EXP-ENTRY-002", "ENTRY_TIMING_DIAGNOSTIC", "GAP_NON_POSITIVE_COHORT_DIAGNOSTIC", "Describe opportunities with next-open gap at or below zero.", "H2 — Entry outcomes may differ when the next-open gap is non-positive.", {"gap_group": "GAP_LE_ZERO", "lower_exclusive_pct": None, "upper_inclusive_pct": 0}, gap_fields, False, False),
        _definition(timestamp, "EXP-ENTRY-003", "ENTRY_TIMING_DIAGNOSTIC", "GAP_0_TO_0_5_COHORT_DIAGNOSTIC", "Describe opportunities with next-open gap above zero and at or below 0.5%.", "H2 — Entry outcomes may differ for small positive next-open gaps.", {"gap_group": "GAP_GT_ZERO_LE_0_5", "lower_exclusive_pct": 0, "upper_inclusive_pct": "0.5"}, gap_fields, False, False),
        _definition(timestamp, "EXP-ENTRY-004", "ENTRY_TIMING_DIAGNOSTIC", "GAP_GT_0_5_COHORT_DIAGNOSTIC", "Describe opportunities with next-open gap above 0.5%.", "H2 — Entry outcomes may differ after larger positive next-open gaps.", {"gap_group": "GAP_GT_0_5", "lower_exclusive_pct": "0.5", "upper_inclusive_pct": None}, gap_fields, False, False),
    )
    if tuple(item.experiment_id for item in definitions) != AUTHORIZED_EXPERIMENT_IDS:
        raise ValueError("Command 01 experiment suite differs from the explicit allowlist")
    return definitions


def _definition(
    registered_at: str,
    experiment_id: str,
    family: str,
    name: str,
    description: str,
    hypothesis: str,
    parameters: Mapping[str, Any],
    fields: tuple[str, ...],
    changes_strategy_semantics: bool,
    changes_portfolio_mechanics: bool,
) -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=experiment_id,
        family=family,
        name=name,
        description=description,
        hypothesis=hypothesis,
        parameters=tuple(parameters.items()),
        outcome_fields_used_for_evaluation=fields,
        changes_strategy_semantics=changes_strategy_semantics,
        changes_portfolio_mechanics=changes_portfolio_mechanics,
        registered_at=registered_at,
    )


def calculate_pre_registration_hash(
    definition: ExperimentDefinition, baseline_hashes: Mapping[str, str]
) -> str:
    return canonical_hash(
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "experiment_id": definition.experiment_id,
            "family": definition.family,
            "name": definition.name,
            "description": definition.description,
            "hypothesis": definition.hypothesis,
            "parameters": definition.parameter_map,
            "baseline_dependency": BASELINE_DEPENDENCY,
            "baseline_hashes": dict(sorted(baseline_hashes.items())),
            "metric_definitions": METRIC_DEFINITIONS,
            "outcome_fields_used_for_evaluation": definition.outcome_fields_used_for_evaluation,
            "changes_strategy_semantics": definition.changes_strategy_semantics,
            "changes_portfolio_mechanics": definition.changes_portfolio_mechanics,
            "diagnostic_only": definition.diagnostic_only,
            "eligible_for_promotion": definition.eligible_for_promotion,
        }
    )


def load_diagnostic_context(repo_root: Path) -> DiagnosticContext:
    data_dir = Path(repo_root) / "data"
    verify_current_portfolio_backtest_baseline(data_dir)
    baseline_hashes = portfolio_backtest_regression_hashes(data_dir)
    if not all(portfolio_backtest_regression_hash_checks(baseline_hashes).values()):
        raise ValueError("Frozen baseline-chain hash verification failed")
    opportunities, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    baseline = get_current_portfolio_backtest_baseline(data_dir)
    baseline_trades = read_gzip_csv(baseline.trades_dataset_path)
    outcome_config = StrategyOutcomeEngineConfig(data_dir)
    sessions, bars = load_adjusted_market_history(
        outcome_config.adjusted_daily_dir,
        {row["symbol"] for row in opportunities},
    )
    exclusions = load_forward_exclusions(outcome_config.eligibility_path)
    summary = json.loads(
        (data_dir / "reports/portfolio_backtest_v1_summary.json").read_text(encoding="utf-8")
    )
    return DiagnosticContext(
        repo_root=Path(repo_root),
        data_dir=data_dir,
        opportunities=opportunities,
        baseline_trades=baseline_trades,
        sessions=sessions,
        bars=bars,
        exclusions=exclusions,
        baseline_hashes=baseline_hashes,
        baseline_summary=summary,
    )


def ranking_key(row: Mapping[str, Any], ranking: str) -> tuple[Any, ...]:
    setup = {"STRONG": 2, "VALID": 1}.get(str(row.get("setup_quality", "")), 0)
    score = decimal(row.get("raw_strategy_score"))
    rr = decimal(row.get("effective_reward_risk"))
    symbol = str(row.get("symbol", ""))
    if ranking == "BASELINE_RANK":
        return (
            -score,
            -rr,
            -setup,
            -decimal(row.get("momentum_points")),
            -decimal(row.get("rvol_points")),
            -decimal(row.get("relative_strength_points")),
            decimal(row.get("position_notional")),
            symbol,
        )
    if ranking == "SCORE_ONLY":
        return (-score, symbol)
    if ranking == "RR_FIRST":
        return (-rr, -score, symbol)
    if ranking == "SETUP_FIRST":
        return (-setup, -score, -rr, symbol)
    raise ValueError(f"Unauthorized ranking adapter: {ranking}")


def rank_diagnostic_opportunities(
    rows: Sequence[Mapping[str, Any]], ranking: str
) -> list[dict[str, Any]]:
    ranked = [dict(row) for row in sorted(rows, key=lambda item: ranking_key(item, ranking))]
    for index, row in enumerate(ranked, start=1):
        row["_diagnostic_selection_rank"] = index
    return ranked


def gap_group(row: Mapping[str, Any]) -> str:
    value = decimal(row.get("gap_from_t_close_pct"))
    if value <= 0:
        return "GAP_LE_ZERO"
    if value <= Decimal("0.5"):
        return "GAP_GT_ZERO_LE_0_5"
    return "GAP_GT_0_5"


def prepare_horizon(
    context: DiagnosticContext, horizon: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if horizon in context.horizon_cache:
        return context.horizon_cache[horizon]
    if horizon not in {4, 6, 8, 10}:
        raise ValueError(f"Unauthorized hold horizon: {horizon}")
    if horizon == 4:
        available = []
        all_dates: set[str] = set()
        for source in context.opportunities:
            row = dict(source)
            row["_diagnostic_bars"] = {
                str(source[f"session_date_{index}"]): {
                    "index": index,
                    "date": str(source[f"session_date_{index}"]),
                    "open": decimal(source[f"open_{index}"]),
                    "high": decimal(source[f"high_{index}"]),
                    "low": decimal(source[f"low_{index}"]),
                    "close": decimal(source[f"close_{index}"]),
                }
                for index in range(1, 5)
            }
            row["_diagnostic_horizon"] = horizon
            available.append(row)
            all_dates.update(row["_diagnostic_bars"])
        minimum_entry = min(row["next_session_date"] for row in context.opportunities)
        maximum_date = max(all_dates)
        calendar = [
            session.isoformat()
            for session in context.sessions
            if minimum_entry <= session.isoformat() <= maximum_date
        ]
        context.horizon_cache[horizon] = (available, [], calendar)
        return context.horizon_cache[horizon]
    available: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    all_dates: set[str] = set()
    for source in context.opportunities:
        decision = date.fromisoformat(source["decision_date"])
        session_dates = resolve_next_sessions(decision, context.sessions, horizon)
        selected_bars = [
            context.bars.get((session.isoformat(), source["symbol"])) for session in session_dates
        ]
        safe, reasons = forward_safety(
            symbol=source["symbol"],
            session_dates=session_dates,
            session_bars=selected_bars,
            exclusions=context.exclusions,
        )
        right_censored = len(session_dates) < horizon
        missing_bar = len(selected_bars) != horizon or any(bar is None for bar in selected_bars)
        if right_censored or missing_bar or not safe:
            reason_codes = list(reasons)
            if right_censored:
                reason_codes.append("RIGHT_CENSORED_END_OF_HISTORY")
            if missing_bar and not right_censored:
                reason_codes.append("MISSING_ADJUSTED_BAR")
            unavailable.append(
                {
                    "source_key": source_key(source),
                    "symbol": source["symbol"],
                    "decision_date": source["decision_date"],
                    "horizon": horizon,
                    "right_censored": right_censored,
                    "unavailable_reasons": sorted(set(reason_codes)),
                }
            )
            continue
        row = dict(source)
        row["_diagnostic_bars"] = {
            session.isoformat(): {
                "index": index,
                "date": session.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
            for index, (session, bar) in enumerate(zip(session_dates, selected_bars), start=1)
            if bar is not None
        }
        row["_diagnostic_horizon"] = horizon
        available.append(row)
        all_dates.update(item.isoformat() for item in session_dates)
    minimum_entry = min(row["next_session_date"] for row in context.opportunities)
    maximum_date = max(all_dates)
    calendar = [
        session.isoformat()
        for session in context.sessions
        if minimum_entry <= session.isoformat() <= maximum_date
    ]
    context.horizon_cache[horizon] = (available, unavailable, calendar)
    return context.horizon_cache[horizon]


def simulate_diagnostic_portfolio(
    *, opportunities: Sequence[dict[str, Any]], trading_dates: Sequence[str], ranking: str, horizon: int
) -> dict[str, Any]:
    config = PortfolioBacktestConfig()
    by_entry_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        by_entry_date[row["next_session_date"]].append(row)
    cash = config.initial_capital_rupees
    positions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    invariants: Counter[str] = Counter()
    trade_number = 0

    for trading_date in trading_dates:
        opening_cash = cash
        opening_positions = len(positions)
        opening_market_value = Decimal("0")
        for position in positions:
            bar = position["source"]["_diagnostic_bars"].get(trading_date)
            opening_mark = bar["open"] if bar else position["last_mark"]
            opening_market_value += opening_mark * position["trade"]["quantity"]
        opening_equity = cash + opening_market_value
        ranked = rank_diagnostic_opportunities(by_entry_date.get(trading_date, []), ranking)
        entries = 0
        for row in ranked:
            open_risk = sum(item["trade"]["planned_risk"] for item in positions)
            sizing = calculate_portfolio_quantity(
                entry_price=decimal(row["hypothetical_entry_price"]),
                stop_price=decimal(row["stop_price"]),
                portfolio_equity=opening_equity,
                available_cash=cash,
                config=config,
            )
            reason = ""
            if any(item["trade"]["symbol"] == row["symbol"] for item in positions):
                reason = SKIP_SAME_SYMBOL_ALREADY_OPEN
            elif len(positions) >= config.max_concurrent_positions:
                reason = SKIP_MAX_POSITIONS
            elif sizing["risk_per_share"] <= 0 or decimal(row["hypothetical_entry_price"]) <= 0:
                reason = SKIP_OTHER
            elif sizing["quantity_by_risk"] < 1:
                reason = SKIP_ZERO_QUANTITY
            elif sizing["quantity_by_cash"] < 1:
                reason = SKIP_INSUFFICIENT_CASH
            elif open_risk + sizing["planned_risk"] > (
                opening_equity * config.max_total_open_risk_pct / Decimal("100")
                + Decimal("0.000001")
            ):
                reason = SKIP_PORTFOLIO_RISK_LIMIT
            if reason:
                skipped.append({"source_key": source_key(row), "skip_reason": reason})
                continue
            trade_number += 1
            entry_price = decimal(row["hypothetical_entry_price"])
            trade = {
                "trade_id": f"DIAG-{trade_number:06d}",
                "source_key": source_key(row),
                "symbol": row["symbol"],
                "entry_date": trading_date,
                "entry_price": entry_price,
                "quantity": sizing["quantity"],
                "entry_notional": sizing["entry_notional"],
                "stop_price": decimal(row["stop_price"]),
                "target_price": decimal(row["target_price"]),
                "risk_per_share": sizing["risk_per_share"],
                "planned_risk": sizing["planned_risk"],
                "selection_rank": row["_diagnostic_selection_rank"],
            }
            cash -= sizing["entry_notional"]
            positions.append(
                {"trade": trade, "source": row, "last_mark": entry_price, "sessions_seen": 0}
            )
            entries += 1

        exits = 0
        realized_pnl = Decimal("0")
        survivors: list[dict[str, Any]] = []
        for position in positions:
            bar = position["source"]["_diagnostic_bars"].get(trading_date)
            if bar is None:
                survivors.append(position)
                continue
            position["sessions_seen"] += 1
            position["last_mark"] = bar["close"]
            trade = position["trade"]
            stop_touched = bar["low"] <= trade["stop_price"]
            target_touched = bar["high"] >= trade["target_price"]
            if stop_touched and target_touched:
                exit_reason, exit_price = AMBIGUOUS_SAME_BAR_EXIT, trade["stop_price"]
            elif target_touched:
                exit_reason, exit_price = TARGET_EXIT, trade["target_price"]
            elif stop_touched:
                exit_reason, exit_price = STOP_EXIT, trade["stop_price"]
            elif position["sessions_seen"] == horizon:
                exit_reason, exit_price = TIME_EXIT, bar["close"]
            else:
                survivors.append(position)
                continue
            pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
            trade.update(
                {
                    "exit_date": trading_date,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "holding_sessions": position["sessions_seen"],
                    "gross_pnl": pnl,
                    "realized_r_multiple": (
                        (exit_price - trade["entry_price"]) / trade["risk_per_share"]
                    ),
                }
            )
            cash += exit_price * trade["quantity"]
            realized_pnl += pnl
            trades.append(trade)
            exits += 1
        positions = survivors
        market_value = sum(item["last_mark"] * item["trade"]["quantity"] for item in positions)
        equity = cash + market_value
        daily.append(
            {
                "date": trading_date,
                "opening_cash": opening_cash,
                "closing_cash": cash,
                "opening_portfolio_equity": opening_equity,
                "open_positions_start": opening_positions,
                "candidates": len(ranked),
                "new_entries": entries,
                "exits": exits,
                "open_positions_end": len(positions),
                "portfolio_equity": equity,
                "realized_pnl_day": realized_pnl,
            }
        )
        invariants["negative_cash"] += cash < Decimal("-0.000001")
        invariants["max_positions"] += len(positions) > config.max_concurrent_positions
        invariants["duplicate_symbols"] += len({item["trade"]["symbol"] for item in positions}) != len(
            positions
        )
    invariants["unresolved_positions"] = len(positions)
    return {
        "trades": trades,
        "skipped": skipped,
        "daily": daily,
        "invariants": dict(invariants),
        "all_invariants_valid": not any(invariants.values()),
    }


def portfolio_execution(
    definition: ExperimentDefinition, context: DiagnosticContext
) -> ExperimentExecution:
    parameters = definition.parameter_map
    horizon = int(parameters["max_hold_sessions"])
    ranking = str(parameters["ranking"])
    opportunities, unavailable, calendar = prepare_horizon(context, horizon)
    simulation = simulate_diagnostic_portfolio(
        opportunities=opportunities,
        trading_dates=calendar,
        ranking=ranking,
        horizon=horizon,
    )
    if not simulation["all_invariants_valid"]:
        raise ValueError(f"Diagnostic simulation invariants failed: {simulation['invariants']}")
    result = portfolio_result(
        definition,
        simulation,
        source_opportunity_count=len(context.opportunities),
        available_opportunity_count=len(opportunities),
        unavailable=unavailable,
    )
    return ExperimentExecution(
        result=result,
        trades=simulation["trades"],
        skipped=simulation["skipped"],
        daily=simulation["daily"],
    )


def portfolio_result(
    definition: ExperimentDefinition,
    simulation: Mapping[str, Any],
    *,
    source_opportunity_count: int,
    available_opportunity_count: int,
    unavailable: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    trades = list(simulation["trades"])
    skipped = list(simulation["skipped"])
    daily = list(simulation["daily"])
    starting = Decimal("100000")
    ending = decimal(daily[-1]["portfolio_equity"])
    returns = percent(ending - starting, starting)
    cagr = calculate_cagr(starting, ending, daily[0]["date"], daily[-1]["date"])
    drawdown = maximum_drawdown(daily)
    realized_r = [decimal(trade["realized_r_multiple"]) for trade in trades]
    pnl = [decimal(trade["gross_pnl"]) for trade in trades]
    holds = [int(trade["holding_sessions"]) for trade in trades]
    exits = Counter(str(trade["exit_reason"]) for trade in trades)
    yearly = yearly_summary(daily)
    skip_profile = Counter(str(row["skip_reason"]) for row in skipped)
    censored = sum(bool(row.get("right_censored")) for row in unavailable)
    unavailable_non_censored = len(unavailable) - censored
    unavailable_reasons = Counter(
        reason
        for row in unavailable
        for reason in row.get("unavailable_reasons", [])
    )
    return {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "pre_registration_hash": "PENDING_REGISTRY_INJECTION",
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "run_status": "RUNNING",
        "sample_size": {
            "source_opportunities": source_opportunity_count,
            "available_opportunities": available_opportunity_count,
            "admitted_trades": len(trades),
            "censored_rows": censored,
            "unavailable_rows": unavailable_non_censored,
            "sample_size_flag": sample_size_flag(len(trades)),
        },
        "unavailable_reason_counts": dict(sorted(unavailable_reasons.items())),
        "trades": len(trades),
        "opportunities_skipped": len(skipped),
        "admission_rate_pct": percent(Decimal(len(trades)), Decimal(source_opportunity_count)),
        "ending_equity": ending,
        "gross_return_pct": returns,
        "cagr_pct": cagr,
        "max_drawdown_pct": drawdown,
        "mean_realized_r": mean(realized_r),
        "median_realized_r": median(realized_r),
        "positive_gross_pnl_rate_pct": percent(
            Decimal(sum(value > 0 for value in pnl)), Decimal(len(pnl))
        ),
        "target_exit_rate_pct": percent(Decimal(exits[TARGET_EXIT]), Decimal(len(trades))),
        "stop_exit_rate_pct": percent(Decimal(exits[STOP_EXIT]), Decimal(len(trades))),
        "time_exit_rate_pct": percent(Decimal(exits[TIME_EXIT]), Decimal(len(trades))),
        "target_exits": exits[TARGET_EXIT],
        "stop_exits": exits[STOP_EXIT],
        "time_exits": exits[TIME_EXIT],
        "ambiguous_exits": exits[AMBIGUOUS_SAME_BAR_EXIT],
        "turnover": sum(
            (trade["entry_notional"] + trade["exit_price"] * trade["quantity"] for trade in trades),
            Decimal("0"),
        ),
        "average_hold_sessions": mean([Decimal(value) for value in holds]),
        "median_hold_sessions": median([Decimal(value) for value in holds]),
        "yearly_results": yearly,
        "robustness": robustness_summary(yearly),
        "trade_source_keys_fingerprint": canonical_hash(
            sorted(str(trade["source_key"]) for trade in trades)
        ),
        "daily_equity_fingerprint": canonical_hash(
            [(row["date"], row["portfolio_equity"]) for row in daily]
        ),
        "skip_profile": dict(sorted(skip_profile.items())),
        "comparison_to_baseline": None,
        "performance_scope": PERFORMANCE_SCOPE,
        "gross_before_costs": True,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "diagnostic_only": True,
        "eligible_for_promotion": False,
        "notes": [
            "No baseline artifact was overwritten.",
            "Longer horizons were simulated chronologically, so slot occupancy changed later admissions.",
            "Unavailable or right-censored forward paths were reported before simulation.",
        ],
    }


def gap_execution(
    definition: ExperimentDefinition,
    context: DiagnosticContext,
    baseline_execution: ExperimentExecution,
) -> ExperimentExecution:
    group = str(definition.parameter_map["gap_group"])
    selected = (
        list(context.opportunities)
        if group == "ALL_NEXT_OPEN"
        else [row for row in context.opportunities if gap_group(row) == group]
    )
    selected_keys = {source_key(row) for row in selected}
    admitted = [row for row in context.baseline_trades if row["source_key"] in selected_keys]
    exit_counts = Counter(row["exit_reason"] for row in admitted)
    source_rr = [decimal(row["effective_reward_risk"]) for row in selected]
    source_mfe = [decimal(row["mfe_r_4"]) for row in selected]
    source_mae = [decimal(row["mae_r_4"]) for row in selected]
    realized = [decimal(row["realized_r_multiple"]) for row in admitted]
    pnl = [decimal(row["gross_pnl"]) for row in admitted]
    baseline_result = baseline_execution.result
    is_anchor = group == "ALL_NEXT_OPEN"
    result = {
        "experiment_id": definition.experiment_id,
        "family": definition.family,
        "pre_registration_hash": "PENDING_REGISTRY_INJECTION",
        "parameter_hash": definition.parameter_hash,
        "parameters": definition.parameter_map,
        "run_status": "RUNNING",
        "sample_size": {
            "source_opportunities": len(selected),
            "available_opportunities": len(selected),
            "admitted_trades": len(admitted),
            "censored_rows": 0,
            "unavailable_rows": 0,
            "sample_size_flag": sample_size_flag(len(admitted)),
        },
        "trades": len(admitted),
        "opportunities_skipped": len(selected) - len(admitted),
        "admission_rate_pct": percent(Decimal(len(admitted)), Decimal(len(selected))),
        "ending_equity": baseline_result["ending_equity"] if is_anchor else None,
        "gross_return_pct": baseline_result["gross_return_pct"] if is_anchor else None,
        "cagr_pct": baseline_result["cagr_pct"] if is_anchor else None,
        "max_drawdown_pct": baseline_result["max_drawdown_pct"] if is_anchor else None,
        "mean_realized_r": mean(realized),
        "median_realized_r": median(realized),
        "positive_gross_pnl_rate_pct": percent(
            Decimal(sum(value > 0 for value in pnl)), Decimal(len(pnl))
        ),
        "target_exit_rate_pct": percent(Decimal(exit_counts[TARGET_EXIT]), Decimal(len(admitted))),
        "stop_exit_rate_pct": percent(Decimal(exit_counts[STOP_EXIT]), Decimal(len(admitted))),
        "time_exit_rate_pct": percent(Decimal(exit_counts[TIME_EXIT]), Decimal(len(admitted))),
        "target_exits": exit_counts[TARGET_EXIT],
        "stop_exits": exit_counts[STOP_EXIT],
        "time_exits": exit_counts[TIME_EXIT],
        "turnover": None,
        "source_mean_effective_reward_risk": mean(source_rr),
        "source_mean_mfe_r_4": mean(source_mfe),
        "source_mean_mae_r_4": mean(source_mae),
        "aggregate_gross_pnl": sum(pnl, Decimal("0")),
        "yearly_results": baseline_result["yearly_results"] if is_anchor else None,
        "robustness": baseline_result["robustness"] if is_anchor else None,
        "trade_source_keys_fingerprint": canonical_hash(sorted(row["source_key"] for row in admitted)),
        "skip_profile": None,
        "comparison_to_baseline": None,
        "performance_scope": PERFORMANCE_SCOPE,
        "gross_before_costs": True,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "diagnostic_only": True,
        "descriptive_segmentation_only": True,
        "eligible_for_promotion": False,
        "notes": [
            "This is descriptive segmentation of frozen opportunities and baseline admissions.",
            "No entry filter or strategy rule was changed.",
        ],
    }
    trades = [
        {
            "source_key": row["source_key"],
            "gross_pnl": decimal(row["gross_pnl"]),
            "realized_r_multiple": decimal(row["realized_r_multiple"]),
            "exit_reason": row["exit_reason"],
        }
        for row in admitted
    ]
    return ExperimentExecution(result=result, trades=trades)


def run_strategy_diagnostic_framework(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    notify(progress, "Verifying and loading the frozen baseline chain")
    context = load_diagnostic_context(repo_root)
    definitions = build_experiment_definitions()
    registry = ExperimentRegistry(context.baseline_hashes)
    for definition in definitions:
        registry.register(definition)
    storage_root = context.data_dir / "research/diagnostics/strategy/v1"
    preregistration_path = storage_root / "registry/experiment_registry_v1_preregistered.json"
    write_json(
        preregistration_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "promotion_allowed": PROMOTION_ALLOWED,
            "research_hypotheses": RESEARCH_HYPOTHESES,
            "experiments": registry.records(),
        },
    )
    for experiment_id in AUTHORIZED_EXPERIMENT_IDS:
        registry.mark_ready(experiment_id)

    executions: dict[str, ExperimentExecution] = {}

    def execute(definition: ExperimentDefinition) -> ExperimentExecution:
        if definition.experiment_id in PORTFOLIO_EXPERIMENT_IDS:
            output = portfolio_execution(definition, context)
        else:
            baseline_execution = executions.get("EXP-RANK-001")
            if baseline_execution is None:
                raise ValueError("Baseline reproduction must complete before gap diagnostics")
            output = gap_execution(definition, context, baseline_execution)
        output.result["pre_registration_hash"] = definition.pre_registration_hash(
            context.baseline_hashes
        )
        return output

    notify(progress, "Running pre-declared pilot experiments")
    for experiment_id in ("EXP-RANK-001", "EXP-RANK-002", "EXP-HOLD-002", "EXP-ENTRY-002"):
        execution = registry.run(
            experiment_id,
            execute,
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Pilot experiment failed: {experiment_id}")
        executions[experiment_id] = execution
    reproduction = baseline_reproduction_check(executions["EXP-RANK-001"].result)
    pilot = {
        "baseline_reproduction": reproduction["passed"],
        "ranking_experiment": executions["EXP-RANK-002"].result["run_status"] == "COMPLETE",
        "extended_horizon_experiment": executions["EXP-HOLD-002"].result["run_status"] == "COMPLETE",
        "gap_cohort_experiment": executions["EXP-ENTRY-002"].result["run_status"] == "COMPLETE",
    }
    pilot["passed"] = all(pilot.values())
    if not pilot["passed"]:
        raise ValueError(f"Strategy diagnostic pilot failed: {pilot}")

    notify(progress, "Running the remaining experiments in the exact finite Command 01 registry")
    for experiment_id in AUTHORIZED_EXPERIMENT_IDS:
        if experiment_id in executions:
            continue
        execution = registry.run(
            experiment_id,
            execute,
            hash_reader=lambda: portfolio_backtest_regression_hashes(context.data_dir),
        )
        if execution is None:
            raise ValueError(f"Registered experiment failed: {experiment_id}")
        executions[experiment_id] = execution

    baseline_execution = executions["EXP-RANK-001"]
    for experiment_id, execution in executions.items():
        execution.result["comparison_to_baseline"] = compare_to_baseline(
            execution,
            baseline_execution,
        )
        registry.state(experiment_id).result_fingerprint = execution.canonical_fingerprint()

    notify(progress, "Checking canonical reproducibility without changing the registry")
    hashes_before_repeat = portfolio_backtest_regression_hashes(context.data_dir)
    repeated = portfolio_execution(registry.state("EXP-RANK-001").definition, context)
    repeated.result["pre_registration_hash"] = registry.state(
        "EXP-RANK-001"
    ).definition.pre_registration_hash(context.baseline_hashes)
    repeated.result["baseline_hashes"] = context.baseline_hashes
    repeated.result["baseline_hashes_before"] = context.baseline_hashes
    repeated.result["baseline_hashes_after"] = context.baseline_hashes
    repeated.result["baseline_hashes_unchanged"] = True
    repeated.result["baseline_mutation_violations"] = 0
    repeated.result["run_status"] = "COMPLETE"
    repeated.result["comparison_to_baseline"] = compare_to_baseline(repeated, repeated)
    hashes_after_repeat = portfolio_backtest_regression_hashes(context.data_dir)
    reproducible = (
        repeated.canonical_fingerprint() == baseline_execution.canonical_fingerprint()
        and hashes_before_repeat == hashes_after_repeat == context.baseline_hashes
    )
    if not reproducible:
        raise ValueError("Baseline diagnostic reproduction fingerprint mismatch")

    ranking_jaccard = pairwise_jaccard(
        {experiment_id: executions[experiment_id] for experiment_id in RANKING_EXPERIMENT_IDS}
    )
    hold_jaccard = pairwise_jaccard(
        {experiment_id: executions[experiment_id] for experiment_id in HOLD_EXPERIMENT_IDS}
    )
    ranking_classification = classify_ranking(executions)
    hold_classification = classify_holds(executions)
    gap_classification = classify_gaps(executions)
    failures = [state for state in registry._states.values() if state.status == "FAILED"]
    hashes_after = portfolio_backtest_regression_hashes(context.data_dir)
    mutation_violations = sum(hashes_after[name] != value for name, value in context.baseline_hashes.items())
    framework_result = (
        "CLEAN"
        if pilot["passed"]
        and not failures
        and not mutation_violations
        and reproducible
        and all(state.status == "COMPLETE" for state in registry._states.values())
        else "METHODOLOGY_FIX_REQUIRED"
    )
    results = [executions[experiment_id].result for experiment_id in AUTHORIZED_EXPERIMENT_IDS]
    summary = {
        "phase": "Step 02.13",
        "command": "Command 01",
        "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
        "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
        "baseline_dependency": {
            "backtest_version": BASELINE_DEPENDENCY[0],
            "backtest_profile": BASELINE_DEPENDENCY[1],
            "backtest_config_hash": BASELINE_DEPENDENCY[2],
            "hashes": hashes_after,
        },
        "registered_experiment_count": len(definitions),
        "registered_experiment_ids": list(AUTHORIZED_EXPERIMENT_IDS),
        "registered_hypotheses": RESEARCH_HYPOTHESES,
        "pilot": pilot,
        "baseline_reproduction": reproduction,
        "results": results,
        "ranking_jaccard_matrix": ranking_jaccard,
        "hold_horizon_jaccard_matrix": hold_jaccard,
        "classifications": {
            "FRAMEWORK_RESULT": framework_result,
            "RANKING_DIAGNOSTIC_RESULT": ranking_classification,
            "HOLD_HORIZON_DIAGNOSTIC_RESULT": hold_classification,
            "ENTRY_GAP_DIAGNOSTIC_RESULT": gap_classification,
        },
        "reproducibility": {
            "same_registered_experiment_canonical_outputs_match": reproducible,
            "generated_timestamps_excluded_from_fingerprint": True,
        },
        "baseline_mutation_violations": mutation_violations,
        "failed_experiment_count": len(failures),
        "promotion_allowed": PROMOTION_ALLOWED,
        "experiments_promoted": 0,
        "winner_selected": False,
        "optimizer_or_parameter_search_run": False,
        "performance_scope": PERFORMANCE_SCOPE,
        "transaction_cost_status": COST_STATUS,
        "slippage_status": SLIPPAGE_STATUS,
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "storage": {},
        "ready_for_review": framework_result == "CLEAN" and tests_passed and frontend_build_passed,
    }
    notify(progress, "Writing isolated diagnostic results and machine reports")
    artifact_paths = write_framework_outputs(
        context=context,
        registry=registry,
        executions=executions,
        summary=summary,
        preregistration_path=preregistration_path,
    )
    summary["storage"] = {
        "artifact_count": len(artifact_paths),
        "artifact_size_bytes_excluding_summary": sum(
            path.stat().st_size for path in artifact_paths if path.exists()
        ),
    }
    summary_path = context.data_dir / "reports/strategy_diagnostic_v1_summary.json"
    write_json(summary_path, summary)
    return summary


def baseline_reproduction_check(result: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "trades": result["trades"] == 728,
        "skips": result["opportunities_skipped"] == 2568,
        "ending_equity": decimal(result["ending_equity"]) == Decimal(EXPECTED_METRICS["ending_equity"]),
        "gross_return_pct": decimal(result["gross_return_pct"]) == Decimal(EXPECTED_METRICS["gross_return_pct"]),
        "max_drawdown_pct": decimal(result["max_drawdown_pct"]) == Decimal(EXPECTED_METRICS["max_drawdown_pct"]),
    }
    return {"checks": checks, "passed": all(checks.values())}


def compare_to_baseline(
    execution: ExperimentExecution, baseline: ExperimentExecution
) -> dict[str, Any]:
    result = execution.result
    base = baseline.result
    current_keys = {str(row["source_key"]) for row in execution.trades}
    baseline_keys = {str(row["source_key"]) for row in baseline.trades}
    portfolio_metrics_available = result.get("ending_equity") is not None
    return {
        "delta_trade_count": int(result["trades"]) - int(base["trades"]),
        "delta_ending_equity": (
            decimal(result["ending_equity"]) - decimal(base["ending_equity"])
            if portfolio_metrics_available
            else None
        ),
        "delta_return_pct": (
            decimal(result["gross_return_pct"]) - decimal(base["gross_return_pct"])
            if portfolio_metrics_available
            else None
        ),
        "delta_cagr_pct": (
            decimal(result["cagr_pct"]) - decimal(base["cagr_pct"])
            if portfolio_metrics_available
            else None
        ),
        "delta_max_drawdown_pct": (
            decimal(result["max_drawdown_pct"]) - decimal(base["max_drawdown_pct"])
            if portfolio_metrics_available
            else None
        ),
        "delta_mean_realized_r": decimal(result["mean_realized_r"]) - decimal(base["mean_realized_r"]),
        "trade_set_jaccard": jaccard(current_keys, baseline_keys),
        "entry_source_overlap_count": len(current_keys & baseline_keys),
        "entry_source_overlap_pct_of_baseline": percent(
            Decimal(len(current_keys & baseline_keys)), Decimal(len(baseline_keys))
        ),
        "skip_profile_delta": skip_profile_delta(result.get("skip_profile"), base.get("skip_profile")),
    }


def pairwise_jaccard(executions: Mapping[str, ExperimentExecution]) -> dict[str, dict[str, Decimal]]:
    key_sets = {
        experiment_id: {str(row["source_key"]) for row in execution.trades}
        for experiment_id, execution in executions.items()
    }
    return {
        left: {right: jaccard(key_sets[left], key_sets[right]) for right in key_sets}
        for left in key_sets
    }


def classify_ranking(executions: Mapping[str, ExperimentExecution]) -> str:
    rows = [executions[item].result for item in RANKING_EXPERIMENT_IDS[1:]]
    minimum_jaccard = min(decimal(row["comparison_to_baseline"]["trade_set_jaccard"]) for row in rows)
    max_return = max(abs(decimal(row["comparison_to_baseline"]["delta_return_pct"])) for row in rows)
    max_drawdown = max(
        abs(decimal(row["comparison_to_baseline"]["delta_max_drawdown_pct"])) for row in rows
    )
    if minimum_jaccard < Decimal("0.50") or max(max_return, max_drawdown) > 15:
        return "EXTREME_SENSITIVITY"
    if minimum_jaccard < Decimal("0.70") or max(max_return, max_drawdown) > 8:
        return "HIGH_SENSITIVITY"
    if minimum_jaccard < Decimal("0.90") or max(max_return, max_drawdown) > 3:
        return "MODERATE_SENSITIVITY"
    return "LOW_SENSITIVITY"


def classify_holds(executions: Mapping[str, ExperimentExecution]) -> str:
    rows = [executions[item].result for item in HOLD_EXPERIMENT_IDS[1:]]
    minimum_jaccard = min(decimal(row["comparison_to_baseline"]["trade_set_jaccard"]) for row in rows)
    maximum_delta = max(
        max(
            abs(decimal(row["comparison_to_baseline"]["delta_return_pct"])),
            abs(decimal(row["comparison_to_baseline"]["delta_max_drawdown_pct"])),
        )
        for row in rows
    )
    if minimum_jaccard < Decimal("0.50") or maximum_delta > 15:
        return "HIGH_SENSITIVITY"
    if minimum_jaccard < Decimal("0.80") or maximum_delta > 5:
        return "MATERIAL_SENSITIVITY"
    return "STABLE"


def classify_gaps(executions: Mapping[str, ExperimentExecution]) -> str:
    rows = [executions[item].result for item in ENTRY_EXPERIMENT_IDS[1:]]
    if any(int(row["sample_size"]["admitted_trades"]) < 20 for row in rows):
        return "INCONCLUSIVE"
    values = [decimal(row["mean_realized_r"]) for row in rows]
    spread = max(values) - min(values)
    if spread >= Decimal("0.25"):
        return "MATERIAL_DIFFERENCE"
    if spread >= Decimal("0.10"):
        return "MIXED"
    return "NO_CLEAR_RELATIONSHIP"


def write_framework_outputs(
    *,
    context: DiagnosticContext,
    registry: ExperimentRegistry,
    executions: Mapping[str, ExperimentExecution],
    summary: Mapping[str, Any],
    preregistration_path: Path,
) -> list[Path]:
    storage_root = context.data_dir / "research/diagnostics/strategy/v1"
    report_root = context.data_dir / "reports"
    registry_path = storage_root / "registry/experiment_registry_v1.json"
    results_path = storage_root / "summaries/experiment_results_v1.csv"
    write_json(
        registry_path,
        {
            "framework_version": STRATEGY_DIAGNOSTIC_FRAMEWORK_VERSION,
            "framework_profile": STRATEGY_DIAGNOSTIC_FRAMEWORK_PROFILE,
            "promotion_allowed": PROMOTION_ALLOWED,
            "research_hypotheses": RESEARCH_HYPOTHESES,
            "experiments": registry.records(),
        },
    )
    write_csv(results_path, [execution.result for execution in executions.values()])
    paths = [preregistration_path, registry_path, results_path]
    for experiment_id in AUTHORIZED_EXPERIMENT_IDS:
        execution = executions[experiment_id]
        result_path = storage_root / f"runs/{experiment_id}/result.json"
        write_json(result_path, execution.result)
        paths.append(result_path)
        if execution.daily:
            daily_path = storage_root / f"runs/{experiment_id}/daily_equity.csv.gz"
            write_gzip_csv(daily_path, execution.daily)
            paths.append(daily_path)
    registry_report = report_root / "strategy_diagnostic_v1_registry.csv"
    ranking_report = report_root / "strategy_diagnostic_v1_ranking.csv"
    hold_report = report_root / "strategy_diagnostic_v1_hold_horizon.csv"
    gap_report = report_root / "strategy_diagnostic_v1_gap_cohorts.csv"
    reproduction_report = report_root / "strategy_diagnostic_v1_baseline_reproduction.csv"
    write_csv(registry_report, registry.records())
    write_csv(
        ranking_report,
        [executions[item].result for item in RANKING_EXPERIMENT_IDS],
    )
    write_csv(
        hold_report,
        [executions[item].result for item in HOLD_EXPERIMENT_IDS],
    )
    write_csv(
        gap_report,
        [executions[item].result for item in ENTRY_EXPERIMENT_IDS],
    )
    reproduction = summary["baseline_reproduction"]
    write_csv(
        reproduction_report,
        [{"experiment_id": "EXP-RANK-001", **reproduction["checks"], "passed": reproduction["passed"]}],
    )
    paths.extend(
        [registry_report, ranking_report, hold_report, gap_report, reproduction_report]
    )
    return paths


def yearly_summary(daily: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in daily:
        grouped[int(str(row["date"])[:4])].append(row)
    results = []
    period_start = decimal(daily[0]["opening_portfolio_equity"])
    for year in sorted(grouped):
        rows = grouped[year]
        starting = period_start
        ending = decimal(rows[-1]["portfolio_equity"])
        results.append(
            {
                "year": year,
                "period_status": "PARTIAL" if year == 2026 else "COMPLETE",
                "starting_equity": starting,
                "ending_equity": ending,
                "gross_pnl": ending - starting,
                "gross_return_pct": percent(ending - starting, starting),
            }
        )
        period_start = ending
    return results


def robustness_summary(yearly: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    positive = [row for row in yearly if decimal(row["gross_return_pct"]) > 0]
    negative = [row for row in yearly if decimal(row["gross_return_pct"]) < 0]
    best = max(yearly, key=lambda row: decimal(row["gross_return_pct"]))
    worst = min(yearly, key=lambda row: decimal(row["gross_return_pct"]))
    absolute_pnl = sum((abs(decimal(row["gross_pnl"])) for row in yearly), Decimal("0"))
    maximum_share = (
        max(abs(decimal(row["gross_pnl"])) for row in yearly) / absolute_pnl
        if absolute_pnl
        else Decimal("0")
    )
    return {
        "positive_years": len(positive),
        "negative_years": len(negative),
        "flat_years": len(yearly) - len(positive) - len(negative),
        "best_year": best["year"],
        "best_year_return_pct": best["gross_return_pct"],
        "worst_year": worst["year"],
        "worst_year_return_pct": worst["gross_return_pct"],
        "one_year_concentration_warning": maximum_share > Decimal("0.60"),
        "largest_absolute_year_pnl_share": maximum_share,
    }


def maximum_drawdown(daily: Sequence[Mapping[str, Any]]) -> Decimal:
    peak = Decimal("0")
    maximum = Decimal("0")
    for row in daily:
        equity = decimal(row["portfolio_equity"])
        peak = max(peak, equity)
        maximum = max(maximum, percent(peak - equity, peak))
    return maximum


def calculate_cagr(starting: Decimal, ending: Decimal, start: str, end: str) -> Decimal:
    span_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    years = Decimal(span_days) / Decimal("365.25")
    return Decimal(str(((float(ending / starting) ** (1 / float(years))) - 1) * 100))


def jaccard(left: set[str], right: set[str]) -> Decimal:
    union = left | right
    return Decimal(len(left & right)) / Decimal(len(union)) if union else Decimal("1")


def skip_profile_delta(
    current: Mapping[str, Any] | None, baseline: Mapping[str, Any] | None
) -> dict[str, int] | None:
    if current is None or baseline is None:
        return None
    keys = set(current) | set(baseline)
    return {key: int(current.get(key, 0)) - int(baseline.get(key, 0)) for key in sorted(keys)}


def source_key(row: Mapping[str, Any]) -> str:
    return f"{row.get('decision_date', '')}|{row.get('symbol', '')}"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def decimal(value: Any) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    return Decimal(str(value))


def percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator * Decimal("100") if denominator else Decimal("0")


def mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def median(values: Sequence[Decimal]) -> Decimal:
    return Decimal(str(statistics.median(values))) if values else Decimal("0")


def sample_size_flag(count: int) -> str:
    if count < 20:
        return "VERY_SMALL"
    if count < 50:
        return "SMALL"
    if count < 200:
        return "LIMITED"
    return "ADEQUATE_FOR_DESCRIPTION"


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    prepared = [flatten_row(row) for row in rows]
    fields = union_fields(prepared)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(prepared)


def write_gzip_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    prepared = [flatten_row(row) for row in rows]
    fields = union_fields(prepared)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(prepared)


def flatten_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list, tuple))
            else json_ready(value)
        )
        for key, value in row.items()
    }


def union_fields(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields or ["status"]


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)

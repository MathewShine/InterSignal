from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

PORTFOLIO_BACKTEST_VERSION = "PORTFOLIO_BACKTEST_V1"
SWING_PORTFOLIO_BACKTEST_PROFILE = "SWING_PORTFOLIO_BACKTEST_V1"
FUTURE_INTRADAY_BACKTEST_PROFILE = "INTRADAY_PORTFOLIO_BACKTEST_V1"

SELECTION_RANKING = (
    "RAW_STRATEGY_SCORE_DESC",
    "EFFECTIVE_REWARD_RISK_DESC",
    "SETUP_QUALITY_DESC",
    "MOMENTUM_POINTS_DESC",
    "RVOL_POINTS_DESC",
    "RELATIVE_STRENGTH_POINTS_DESC",
    "POSITION_NOTIONAL_ASC",
    "SYMBOL_ASC",
)


@dataclass(frozen=True, slots=True)
class PortfolioBacktestConfig:
    backtest_version: str = PORTFOLIO_BACKTEST_VERSION
    backtest_profile: str = SWING_PORTFOLIO_BACKTEST_PROFILE
    initial_capital_rupees: Decimal = Decimal("100000")
    max_concurrent_positions: int = 4
    max_risk_per_trade_pct: Decimal = Decimal("1.00")
    max_total_open_risk_pct: Decimal = Decimal("4.00")
    entry_model: str = "NEXT_SESSION_OPEN"
    selection_ranking: tuple[str, ...] = SELECTION_RANKING
    same_symbol_policy: str = "ONE_OPEN_POSITION_PER_SYMBOL"
    max_hold_sessions: int = 4
    target_exit_policy: str = "FROZEN_TARGET"
    stop_exit_policy: str = "FROZEN_STOP"
    time_exit_policy: str = "SESSION_4_CLOSE"
    ambiguity_policy: str = "CONSERVATIVE_STOP_FIRST"
    session_ordering_policy: str = "OPEN_ENTRIES_BEFORE_INTRADAY_EXITS_NO_SAME_DAY_CASH_REUSE"
    equity_marking_policy: str = "END_OF_DAY_CLOSE"
    entry_equity_basis: str = "OPENING_CASH_PLUS_OPEN_POSITION_OPEN_MARKS"
    transaction_cost_status: str = "NOT_MODELED"
    slippage_status: str = "NOT_MODELED"
    performance_basis: str = "GROSS_BEFORE_COSTS_RESEARCH_ONLY"
    exceptional_review_policy: str = "EXCEPTIONAL_NOT_INCLUDED_BASELINE"
    leverage_policy: str = "NO_LEVERAGE_NO_MARGIN_NO_BORROWING"
    position_direction: str = "LONG_CASH_EQUITY_ONLY"

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value

"""Deterministic historical portfolio simulation for frozen Strategy V1 research."""

from app.backtesting.portfolio_config import (
    PORTFOLIO_BACKTEST_VERSION,
    SWING_PORTFOLIO_BACKTEST_PROFILE,
    PortfolioBacktestConfig,
)
from app.backtesting.portfolio_baseline import (
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
    CURRENT_PORTFOLIO_BACKTEST_PROFILE,
    CURRENT_PORTFOLIO_BACKTEST_VERSION,
    PORTFOLIO_BACKTEST_BASELINE_STATUS,
    CurrentPortfolioBacktestBaseline,
    get_current_portfolio_backtest_baseline,
    resolve_current_portfolio_backtest_daily_dataset,
    resolve_current_portfolio_backtest_skipped_dataset,
    resolve_current_portfolio_backtest_trades_dataset,
)
from app.backtesting.portfolio_audit import (
    PORTFOLIO_BACKTEST_AUDIT_VERSION,
    PortfolioBacktestAuditConfig,
    build_portfolio_backtest_audit,
)
from app.backtesting.portfolio_engine import (
    PortfolioBacktestEngineConfig,
    build_portfolio_backtest,
    simulate_portfolio,
)

__all__ = [
    "PORTFOLIO_BACKTEST_VERSION",
    "SWING_PORTFOLIO_BACKTEST_PROFILE",
    "PortfolioBacktestConfig",
    "CURRENT_PORTFOLIO_BACKTEST_VERSION",
    "CURRENT_PORTFOLIO_BACKTEST_PROFILE",
    "CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH",
    "PORTFOLIO_BACKTEST_BASELINE_STATUS",
    "CurrentPortfolioBacktestBaseline",
    "get_current_portfolio_backtest_baseline",
    "resolve_current_portfolio_backtest_trades_dataset",
    "resolve_current_portfolio_backtest_daily_dataset",
    "resolve_current_portfolio_backtest_skipped_dataset",
    "PORTFOLIO_BACKTEST_AUDIT_VERSION",
    "PortfolioBacktestAuditConfig",
    "PortfolioBacktestEngineConfig",
    "build_portfolio_backtest",
    "build_portfolio_backtest_audit",
    "simulate_portfolio",
]

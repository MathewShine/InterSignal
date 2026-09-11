from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.portfolio_baseline import (
    CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
    CURRENT_PORTFOLIO_BACKTEST_PROFILE,
    CURRENT_PORTFOLIO_BACKTEST_VERSION,
    PORTFOLIO_BACKTEST_BASELINE_STATUS,
    PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH,
    PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH,
    PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH,
    audit_portfolio_backtest_references,
    build_portfolio_backtest_baseline_promotion_report,
    get_current_portfolio_backtest_baseline,
    get_current_portfolio_backtest_config,
    get_current_portfolio_backtest_config_hash,
    get_current_portfolio_backtest_profile,
    get_current_portfolio_backtest_version,
    get_portfolio_backtest_baseline,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    resolve_current_portfolio_backtest_daily_dataset,
    resolve_current_portfolio_backtest_skipped_dataset,
    resolve_current_portfolio_backtest_trades_dataset,
    verify_current_portfolio_backtest_baseline,
    write_portfolio_backtest_baseline_promotion_markdown,
    write_portfolio_backtest_baseline_promotion_report,
)
from app.backtesting.portfolio_config import (
    FUTURE_INTRADAY_BACKTEST_PROFILE,
    SELECTION_RANKING,
    PortfolioBacktestConfig,
)
from app.backtesting.portfolio_engine import PortfolioBacktestEngineConfig
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import (
    CURRENT_STRATEGY_OUTCOME_VERSION,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_current_backtest_identity_and_config_hash_are_authoritative() -> None:
    assert get_current_portfolio_backtest_version() == CURRENT_PORTFOLIO_BACKTEST_VERSION
    assert get_current_portfolio_backtest_profile() == CURRENT_PORTFOLIO_BACKTEST_PROFILE
    assert get_current_portfolio_backtest_config_hash() == CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH
    assert get_current_portfolio_backtest_config().config_hash() == CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH


def test_current_dataset_resolvers_and_contract_use_canonical_v1_ledgers() -> None:
    expected_root = DATA_DIR / "research/backtests/swing/portfolio/v1"
    assert resolve_current_portfolio_backtest_trades_dataset(DATA_DIR) == (
        expected_root / "portfolio_trades_v1.csv.gz"
    )
    assert resolve_current_portfolio_backtest_daily_dataset(DATA_DIR) == (
        expected_root / "portfolio_daily_v1.csv.gz"
    )
    assert resolve_current_portfolio_backtest_skipped_dataset(DATA_DIR) == (
        expected_root / "portfolio_skipped_opportunities_v1.csv.gz"
    )
    baseline = get_current_portfolio_backtest_baseline(DATA_DIR)
    assert baseline.status == PORTFOLIO_BACKTEST_BASELINE_STATUS
    assert baseline.trades_dataset_path == resolve_current_portfolio_backtest_trades_dataset(DATA_DIR)
    assert baseline.daily_dataset_path == resolve_current_portfolio_backtest_daily_dataset(DATA_DIR)
    assert baseline.skipped_dataset_path == resolve_current_portfolio_backtest_skipped_dataset(DATA_DIR)


def test_exact_dataset_hashes_and_immutability() -> None:
    baseline = verify_current_portfolio_backtest_baseline(DATA_DIR)
    before = {
        "trades": file_sha256(baseline.trades_dataset_path),
        "daily": file_sha256(baseline.daily_dataset_path),
        "skipped": file_sha256(baseline.skipped_dataset_path),
    }
    assert before == {
        "trades": PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH,
        "daily": PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH,
        "skipped": PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH,
    }
    assert before == {
        "trades": file_sha256(baseline.trades_dataset_path),
        "daily": file_sha256(baseline.daily_dataset_path),
        "skipped": file_sha256(baseline.skipped_dataset_path),
    }


def test_future_profile_and_version_are_explicitly_isolated() -> None:
    with pytest.raises(ValueError, match="No current portfolio-backtest baseline"):
        get_current_portfolio_backtest_version(FUTURE_INTRADAY_BACKTEST_PROFILE)
    with pytest.raises(ValueError, match="Unsupported portfolio-backtest baseline"):
        get_portfolio_backtest_baseline(
            DATA_DIR,
            profile=CURRENT_PORTFOLIO_BACKTEST_PROFILE,
            version="PORTFOLIO_BACKTEST_V2",
        )


def test_generic_engine_and_build_default_resolve_central_baseline() -> None:
    engine = PortfolioBacktestEngineConfig(data_dir=DATA_DIR)
    baseline = get_current_portfolio_backtest_baseline(DATA_DIR)
    assert engine.trades_path == baseline.trades_dataset_path
    assert engine.daily_path == baseline.daily_dataset_path
    assert engine.skipped_path == baseline.skipped_dataset_path
    source = (REPO_ROOT / "backend/scripts/build_portfolio_backtest.py").read_text(encoding="utf-8")
    assert "get_current_portfolio_backtest_profile" in source
    assert "get_current_portfolio_backtest_version" in source
    assert "get_portfolio_backtest_config" in source
    assert "CURRENT_PORTFOLIO_BASELINE_RESOLUTION_MISMATCH" in source


def test_frozen_dependencies_and_all_regression_hashes_match() -> None:
    summary = json.loads(
        (DATA_DIR / "reports/portfolio_backtest_v1_summary.json").read_text(encoding="utf-8")
    )
    source = summary["source_contract"]
    hashes = portfolio_backtest_regression_hashes(DATA_DIR)
    assert source["outcome_version"] == CURRENT_STRATEGY_OUTCOME_VERSION
    assert hashes["outcome_v1"] == STRATEGY_OUTCOME_V1_DATASET_HASH
    assert source["score_version"] == CURRENT_STRATEGY_SCORE_VERSION
    assert hashes["score_v1"] == STRATEGY_SCORE_V1_DATASET_HASH
    assert source["risk_version"] == CURRENT_RISK_STRUCTURE_VERSION
    assert hashes["risk_v1_1"] == RISK_STRUCTURE_V1_1_DATASET_HASH
    assert all(portfolio_backtest_regression_hash_checks(hashes).values())


def test_baseline_metrics_and_audit_invariants_remain_unchanged() -> None:
    summary = json.loads(
        (DATA_DIR / "reports/portfolio_backtest_v1_summary.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (DATA_DIR / "reports/portfolio_backtest_v1_audit_summary.json").read_text(encoding="utf-8")
    )
    assert summary["opportunity_pool"] == {
        "mechanically_valid_opportunities_considered": 3296,
        "actual_portfolio_trades_entered": 728,
        "opportunities_skipped": 2568,
        "admission_rate_pct": "22.08737864077669902912621359",
        "excluded_source_rows": {"non_primary_cohort": 9983, "entry_invalid": 972},
        "exceptional_review_policy": "EXCEPTIONAL_NOT_INCLUDED_BASELINE",
    }
    assert audit["constraints"]["same_symbol"] == {"audited": 153, "incorrect": 0}
    assert audit["constraints"]["max_positions"] == {"audited": 2398, "incorrect": 0}
    assert audit["constraints"]["cash"] == {"audited": 15, "incorrect": 0}
    assert audit["constraints"]["portfolio_risk_skips"] == {"audited": 2, "incorrect": 0}
    assert audit["chronology"]["daily_processing_order_violations"] == 0
    assert audit["accounting"]["cash"]["mismatch_count"] == 0
    assert audit["accounting"]["equity"]["mismatch_count"] == 0
    assert audit["ranking"]["reconstruction_mismatches"] == 0
    assert audit["accounting"]["trade_linkage"]["violation_count"] == 0
    assert audit["ranking"]["lookahead"]["future_fields_consumed"] == []


def test_ranking_positions_risk_exits_ambiguity_and_costs_remain_locked() -> None:
    config = PortfolioBacktestConfig()
    assert config.selection_ranking == SELECTION_RANKING
    assert config.max_concurrent_positions == 4
    assert config.max_risk_per_trade_pct == Decimal("1.00")
    assert config.max_total_open_risk_pct == Decimal("4.00")
    assert config.same_symbol_policy == "ONE_OPEN_POSITION_PER_SYMBOL"
    assert config.target_exit_policy == "FROZEN_TARGET"
    assert config.stop_exit_policy == "FROZEN_STOP"
    assert config.time_exit_policy == "SESSION_4_CLOSE"
    assert config.max_hold_sessions == 4
    assert config.ambiguity_policy == "CONSERVATIVE_STOP_FIRST"
    assert config.transaction_cost_status == "NOT_MODELED"
    assert config.slippage_status == "NOT_MODELED"
    assert config.performance_basis == "GROSS_BEFORE_COSTS_RESEARCH_ONLY"


def test_reference_audit_has_no_unintended_forward_backtest_paths() -> None:
    audit = audit_portfolio_backtest_references(REPO_ROOT)
    assert audit["total_references"] > 0
    assert audit["classification_counts"]["FORWARD_CURRENT"] > 0
    assert audit["classification_counts"]["AUDIT_ALLOWED"] > 0
    assert audit["classification_counts"]["TEST_FIXTURE_ALLOWED"] > 0
    assert audit["classification_counts"]["DOCUMENTATION_ALLOWED"] > 0
    assert audit["unintended_forward_references"] == []


def test_promotion_report_generation_and_baseline_immutability(tmp_path: Path) -> None:
    baseline = get_current_portfolio_backtest_baseline(DATA_DIR)
    before = portfolio_backtest_regression_hashes(DATA_DIR)
    report = build_portfolio_backtest_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=True,
        frontend_build_passed=True,
    )
    report_path = tmp_path / "portfolio_backtest_baseline_promotion.json"
    document_path = tmp_path / "portfolio-backtest-baseline-promotion.md"
    write_portfolio_backtest_baseline_promotion_report(report_path, report)
    write_portfolio_backtest_baseline_promotion_markdown(document_path, report)
    assert report["promotion_status"] == PORTFOLIO_BACKTEST_BASELINE_STATUS
    assert report["step_status"] == "COMPLETE"
    assert report["ready_for_review"] is True
    assert report["baseline_metrics_match"] is True
    assert report["input_hash_checks"] and all(report["input_hash_checks"].values())
    assert all(report["unchanged_during_promotion"].values())
    assert portfolio_backtest_regression_hashes(DATA_DIR) == before
    assert file_sha256(baseline.trades_dataset_path) == PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH
    assert report_path.exists()
    assert document_path.exists()

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.costs.brokerage import brokerage_raw
from app.backtesting.costs.cost_config import (
    DEFAULT_COST_CONFIG_HASH,
    EXPECTED_COST_CONFIG_HASH,
    default_cost_model_config,
)
from app.backtesting.costs.cost_engine import (
    EXPECTED_SCENARIO_HASHES,
    EXPECTED_SCENARIO_IDS,
    REPORT_NAMES,
    SCENARIO_BASELINE_SLIPPAGE,
    SCENARIO_ZERO_COST,
    calculate_trade_cost,
    registered_cost_scenarios,
)
from app.backtesting.costs.cost_models import (
    BROKERAGE_FLAT_PER_ORDER,
    BROKERAGE_PERCENTAGE,
    BROKERAGE_ZERO_DELIVERY,
    COSTED_BACKTEST_VERSION,
    COST_MODEL_VERSION,
    COST_PROFILE,
    FIXED_BPS,
    LIQUIDITY_AWARE_FUTURE_PLACEHOLDER,
    SLIPPAGE_MODEL_VERSION,
    TURNOVER_TIERED,
    ZERO_SLIPPAGE,
    BrokerageConfig,
)
from app.backtesting.costs.slippage import slippage_raw
from app.backtesting.costs.statutory_costs import round_rupees, side_fee_components
from app.backtesting.portfolio_baseline import (
    EXPECTED_METRICS,
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
)
from app.diagnostics.strategy_diagnostic_synthesis import (
    EXPECTED_REGISTRY_FINGERPRINT,
    registry_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SUMMARY_PATH = DATA_DIR / "reports/transaction_cost_v1_summary.json"
TRADES_PATH = (
    DATA_DIR
    / "research/backtests/swing/portfolio/v1_costed/portfolio_trades_costed_v1.csv.gz"
)
DAILY_PATH = (
    DATA_DIR
    / "research/backtests/swing/portfolio/v1_costed/portfolio_daily_costed_v1.csv.gz"
)


def load_summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def sample_trade(*, gross_pnl: str = "10") -> dict[str, str]:
    return {
        "trade_id": "TEST-001",
        "symbol": "TEST",
        "entry_date": "2025-01-02",
        "exit_date": "2025-01-06",
        "entry_price": "100",
        "exit_price": str(Decimal("100") + Decimal(gross_pnl) / Decimal("10")),
        "quantity": "10",
        "initial_planned_risk": "100",
        "gross_pnl": gross_pnl,
        "realized_r_multiple": str(Decimal(gross_pnl) / Decimal("100")),
        "selection_rank": "1",
        "raw_strategy_score": "80",
        "exit_reason": "TIME_EXIT",
        "holding_sessions": "4",
    }


def scenario(scenario_id: str):
    return next(row for row in registered_cost_scenarios() if row.scenario_id == scenario_id)


def test_cost_model_identity_and_config_hash_are_frozen() -> None:
    config = default_cost_model_config()
    assert config.version == COST_MODEL_VERSION == "INDIA_EQUITY_COST_MODEL_V1"
    assert config.profile == COST_PROFILE == "NSE_CASH_DELIVERY_RESEARCH_V1"
    assert COSTED_BACKTEST_VERSION == "PORTFOLIO_BACKTEST_V1_COSTED_RESEARCH"
    assert SLIPPAGE_MODEL_VERSION == "SLIPPAGE_MODEL_V1"
    assert config.config_hash() == DEFAULT_COST_CONFIG_HASH == EXPECTED_COST_CONFIG_HASH


def test_effective_date_exchange_schedules() -> None:
    config = default_cost_model_config()
    assert config.schedule_for("EXCHANGE_TRANSACTION_CHARGE", "BUY", date(2022, 6, 1)).rate == Decimal("0.0000345")
    assert config.schedule_for("EXCHANGE_TRANSACTION_CHARGE", "SELL", date(2023, 6, 1)).rate == Decimal("0.0000325")
    assert config.schedule_for("EXCHANGE_TRANSACTION_CHARGE", "BUY", date(2025, 6, 1)).rate == Decimal("0.0000297")


def test_buy_sell_applicability_is_asymmetric() -> None:
    config = default_cost_model_config()
    buy = side_fee_components(config=config, side="BUY", value_date=date(2025, 1, 2), executed_turnover=Decimal("100000"), include_costs=True)
    sell = side_fee_components(config=config, side="SELL", value_date=date(2025, 1, 2), executed_turnover=Decimal("100000"), include_costs=True)
    assert buy["STAMP_DUTY"]["rounded"] == Decimal("15.00")
    assert sell["STAMP_DUTY"]["rounded"] == Decimal("0")
    assert buy["DP_CHARGE"]["rounded"] == Decimal("0")
    assert sell["DP_CHARGE"]["rounded"] == Decimal("13.50")


@pytest.mark.parametrize(
    ("model", "percentage", "flat", "expected"),
    (
        (BROKERAGE_ZERO_DELIVERY, "0", "0", "0"),
        (BROKERAGE_PERCENTAGE, "0.001", "0", "100.000"),
        (BROKERAGE_FLAT_PER_ORDER, "0", "20", "20"),
    ),
)
def test_brokerage_models(model: str, percentage: str, flat: str, expected: str) -> None:
    config = BrokerageConfig(
        model=model,
        percentage_rate=Decimal(percentage),
        flat_per_order_rupees=Decimal(flat),
    )
    assert brokerage_raw(Decimal("100000"), config) == Decimal(expected)


def test_statutory_components_and_gst_basis() -> None:
    fees = side_fee_components(
        config=default_cost_model_config(),
        side="SELL",
        value_date=date(2025, 1, 2),
        executed_turnover=Decimal("100000"),
        include_costs=True,
    )
    assert fees["STT"]["rounded"] == Decimal("100.00")
    assert fees["EXCHANGE_TRANSACTION_CHARGE"]["rounded"] == Decimal("2.97")
    assert fees["SEBI_CHARGE"]["rounded"] == Decimal("0.10")
    assert fees["DP_CHARGE"]["rounded"] == Decimal("13.50")
    assert fees["GST_TAXABLE_BASE"]["raw"] == Decimal("16.5700000")
    assert fees["GST"]["rounded"] == Decimal("2.98")


def test_zero_cost_disables_every_charge() -> None:
    fees = side_fee_components(
        config=default_cost_model_config(),
        side="BUY",
        value_date=date(2025, 1, 2),
        executed_turnover=Decimal("100000"),
        include_costs=False,
    )
    assert all(row["rounded"] == 0 for row in fees.values())


def test_rounding_policy_is_half_up_to_paise() -> None:
    config = default_cost_model_config()
    assert round_rupees(Decimal("1.004"), config) == Decimal("1.00")
    assert round_rupees(Decimal("1.005"), config) == Decimal("1.01")


@pytest.mark.parametrize(
    ("model", "bps", "expected"),
    (
        (ZERO_SLIPPAGE, "0", "0"),
        (FIXED_BPS, "5", "50"),
    ),
)
def test_supported_slippage_models(model: str, bps: str, expected: str) -> None:
    assert slippage_raw(Decimal("100000"), model, Decimal(bps)) == Decimal(expected)


def test_turnover_tiered_slippage_uses_predeclared_tier() -> None:
    tiers = ((Decimal("50000"), Decimal("4")), (None, Decimal("8")))
    assert slippage_raw(
        Decimal("100000"), TURNOVER_TIERED, Decimal("0"), turnover_tiers=tiers
    ) == Decimal("80")
    with pytest.raises(ValueError, match="predeclared tiers"):
        slippage_raw(Decimal("100000"), TURNOVER_TIERED, Decimal("0"))


def test_liquidity_aware_slippage_is_only_a_placeholder() -> None:
    with pytest.raises(NotImplementedError):
        slippage_raw(Decimal("100000"), LIQUIDITY_AWARE_FUTURE_PLACEHOLDER, Decimal("5"))


def test_long_slippage_direction_and_trade_reconciliation() -> None:
    row = calculate_trade_cost(
        sample_trade(),
        config=default_cost_model_config(),
        scenario=scenario(SCENARIO_BASELINE_SLIPPAGE),
    )
    assert row["effective_entry_price"] > Decimal("100")
    assert row["effective_exit_price"] < Decimal("101")
    assert row["buy_gst_taxable_base_raw"] >= 0
    assert row["sell_gst_taxable_base_raw"] >= 0
    assert row["gross_pnl"] - row["total_transaction_cost"] == row["net_pnl"]
    assert row["net_realized_r"] == row["net_pnl"] / Decimal("100")


def test_small_gross_win_can_flip_net_negative() -> None:
    row = calculate_trade_cost(
        sample_trade(gross_pnl="1"),
        config=default_cost_model_config(),
        scenario=scenario(SCENARIO_BASELINE_SLIPPAGE),
    )
    assert row["gross_pnl"] > 0
    assert row["net_pnl"] < 0


def test_exactly_four_scenarios_are_preregistered_with_frozen_hashes() -> None:
    scenarios = registered_cost_scenarios()
    config_hash = default_cost_model_config().config_hash()
    assert tuple(row.scenario_id for row in scenarios) == EXPECTED_SCENARIO_IDS
    assert {row.scenario_id: row.scenario_hash(config_hash) for row in scenarios} == EXPECTED_SCENARIO_HASHES
    assert all(row.preregistered and row.optimization_prohibited for row in scenarios)


def test_config_and_scenarios_are_immutable() -> None:
    config = default_cost_model_config()
    with pytest.raises(FrozenInstanceError):
        config.rounding_quantum = Decimal("1")  # type: ignore[misc]
    frozen_scenario = registered_cost_scenarios()[0]
    with pytest.raises(FrozenInstanceError):
        frozen_scenario.slippage_bps_per_side = Decimal("99")  # type: ignore[misc]


def test_summary_has_clean_reconciliations_and_no_negative_costs() -> None:
    summary = load_summary()
    assert summary["reconciliation"] == {
        "trade_cost_violation_count": 0,
        "daily_cash_violation_count": 0,
        "daily_cash_max_mismatch": "0",
        "negative_cost_violations": 0,
    }


def test_zero_cost_reference_exactly_reproduces_baseline() -> None:
    summary = load_summary()
    zero = next(row for row in summary["scenarios"] if row["scenario_id"] == SCENARIO_ZERO_COST)
    assert zero["trade_count"] == 728
    assert zero["ending_equity"] == EXPECTED_METRICS["ending_equity"]
    assert zero["net_return_pct"] == EXPECTED_METRICS["gross_return_pct"]
    assert zero["cagr_pct"] == EXPECTED_METRICS["cagr_pct"]
    assert zero["max_drawdown_pct"] == EXPECTED_METRICS["max_drawdown_pct"]
    assert summary["zero_cost_reproduction"]["passed"] is True


def test_trade_set_and_quantities_are_preserved() -> None:
    preserved = load_summary()["frozen_trade_set_preservation"]
    assert preserved["baseline_trade_count"] == 728
    assert set(preserved["costed_trade_count_per_scenario"].values()) == {728}
    assert preserved["trade_ids_quantities_entry_exit_prices_unchanged"] is True
    assert preserved["admission_decisions_rerun"] is False
    assert preserved["quantities_recalculated"] is False


def test_costed_datasets_contain_all_scenarios() -> None:
    with gzip.open(TRADES_PATH, "rt", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 728 * 4
    assert {row["scenario_id"] for row in rows} == set(EXPECTED_SCENARIO_IDS)
    assert all(row["costed_backtest_version"] == COSTED_BACKTEST_VERSION for row in rows)
    with gzip.open(DAILY_PATH, "rt", encoding="utf-8", newline="") as file:
        daily = list(csv.DictReader(file))
    assert {row["scenario_id"] for row in daily} == set(EXPECTED_SCENARIO_IDS)
    assert all(Decimal(row["cash_reconciliation_mismatch"]) == 0 for row in daily)


def test_year_score_exit_holding_and_turnover_reports_are_complete() -> None:
    reports = DATA_DIR / "reports"
    for name in (
        "transaction_cost_v1_yearly.csv",
        "transaction_cost_v1_scores.csv",
        "transaction_cost_v1_exit_types.csv",
        "transaction_cost_v1_holding_period.csv",
        "transaction_cost_v1_turnover.csv",
        "transaction_cost_v1_small_wins.csv",
    ):
        with (reports / name).open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        assert rows
        assert {row["scenario_id"] for row in rows} == set(EXPECTED_SCENARIO_IDS)


def test_pilot_covers_all_required_cases() -> None:
    summary = load_summary()
    assert summary["pilot"] == {
        "required_case_count": 14,
        "passed_case_count": 14,
        "passed": True,
    }
    with (DATA_DIR / "reports/transaction_cost_v1_pilot.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 14
    assert all(row["passed"] == "True" for row in rows)


def test_rate_sources_and_approximation_warning_are_explicit() -> None:
    summary = load_summary()
    assert summary["historical_rate_precision"] == "APPROXIMATE_RESEARCH_ASSUMPTION"
    assert summary["net_estimate_warning"] == "NET_RESULTS_ARE_APPROXIMATE_RESEARCH_ESTIMATES"
    assert all(row["source_status"] in {"AUTHORITATIVE", "BROKER_PUBLISHED", "REGULATORY_PUBLISHED", "RESEARCH_ASSUMPTION", "HISTORICAL_APPROXIMATION"} for row in summary["rate_source_metadata"])
    assert any(row["research_assumption"] for row in summary["rate_source_metadata"])


def test_cost_materiality_and_live_readiness() -> None:
    summary = load_summary()
    assert summary["classifications"] == {
        "COST_MODEL_RESULT": "CLEAN_WITH_APPROXIMATE_HISTORICAL_RATES",
        "COST_MATERIALITY_RESULT": "VERY_HIGH",
    }
    assert summary["readiness"]["LIVE_TRADING_READY"] is False
    assert summary["readiness"]["SMALL_CAPITAL_LIVE_READY"] is False


def test_frozen_baseline_and_diagnostic_registry_are_unchanged() -> None:
    summary = load_summary()
    hashes = portfolio_backtest_regression_hashes(DATA_DIR)
    assert all(portfolio_backtest_regression_hash_checks(hashes).values())
    assert summary["frozen_hashes_before"] == summary["frozen_hashes_after"] == hashes
    registry_path = DATA_DIR / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry_fingerprint(registry) == EXPECTED_REGISTRY_FINGERPRINT
    assert summary["diagnostic_registry_regression"]["unchanged"] is True
    assert summary["baseline_mutation_violations"] == 0


def test_all_machine_reports_and_registry_outputs_exist() -> None:
    assert all((DATA_DIR / "reports" / name).exists() for name in REPORT_NAMES)
    registry = DATA_DIR / "research/costs/v1/registry"
    assert (registry / "cost_model_config_v1.json").exists()
    assert (registry / "cost_scenarios_v1_preregistered.json").exists()
    assert (registry / "cost_scenarios_v1.json").exists()


def test_source_has_no_network_order_or_supabase_actions() -> None:
    root = REPO_ROOT / "backend/app/backtesting/costs"
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))
    assert "requests." not in source
    assert "httpx." not in source
    assert "urlopen(" not in source
    assert "place_order" not in source
    assert "supabase." not in source


def test_no_strategy_or_admission_mutation_policy() -> None:
    policies = load_summary()["policies"]
    assert policies["strategy_v1_modified"] is False
    assert policies["backtest_v1_modified"] is False
    assert policies["trade_selection_modified"] is False
    assert policies["quantity_modified"] is False
    assert policies["strategy_v2_created"] is False
    assert policies["parameters_optimized"] is False
    assert policies["cost_assumptions_optimized"] is False


def test_reproducibility_and_scenario_preregistration() -> None:
    summary = load_summary()
    assert summary["reproducibility"]["match"] is True
    assert summary["reproducibility"]["scenario_parameters_unchanged"] is True
    assert summary["scenario_registry"]["registered_before_computation"] is True
    assert summary["scenario_registry"]["scenario_count"] == 4
    assert summary["scenario_registry"]["no_post_result_rate_change"] is True


def test_final_summary_gate_is_ready_after_validation() -> None:
    summary = load_summary()
    assert summary["tests_passed"] is True
    assert summary["frontend_build_passed"] is True
    assert summary["ready_for_review"] is True

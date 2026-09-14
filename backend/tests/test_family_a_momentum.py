from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.costs.cost_models import DP_CHARGE, STAMP_DUTY
from app.research.strategy.family_a_momentum import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPERIMENT_IDS,
    FAMILY_CODE,
    FAMILY_VERSION,
    LOOKBACK_SESSIONS,
    MembershipIndex,
    MembershipPeriod,
    PRICE_FLOOR,
    REPORT_NAMES,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    build_rebalance_calendar,
    compounded_return,
    equal_weight_targets,
    estimate_order_cost,
    experiment_registry,
    family_config,
    frozen_project_snapshot,
    integer_share_targets,
    plan_rebalance,
    select_top_decile,
    verify_registry,
    write_csv,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def trading_dates(count: int, start: date = date(2022, 1, 3)) -> list[date]:
    return [start + timedelta(days=index) for index in range(count)]


def eligible_rows(count: int, *, equal_signal: bool = False) -> list[dict[str, object]]:
    return [
        {
            "symbol": f"S{index:03d}",
            "eligible": True,
            "6m_return": Decimal("1") if equal_signal else Decimal(index),
        }
        for index in range(count)
    ]


def test_exact_family_identity_and_protocol() -> None:
    assert FAMILY_VERSION == "STRATEGY_FAMILY_A_MOMENTUM_V1"
    assert RESEARCH_PROFILE == "MEDIUM_TERM_CROSS_SECTIONAL_MOMENTUM_V1"
    assert FAMILY_CODE == "FAMILY_A"
    assert RESEARCH_PROTOCOL == "FAMILY_A_RESEARCH_PROTOCOL_V1"
    assert DEVELOPMENT_START == date(2022, 1, 1)
    assert DEVELOPMENT_END == date(2024, 12, 31)


def test_registry_has_exactly_three_authorized_preregistrations() -> None:
    config = family_config()
    registry = experiment_registry(config)
    verify_registry(registry, config)
    assert EXPERIMENT_IDS == ("MOM-A-001", "MOM-A-002", "MOM-A-003")
    assert registry["experiment_count"] == 3
    assert registry["experiment_ids"] == list(EXPERIMENT_IDS)
    assert all(row["status"] == "PREREGISTERED" for row in registry["experiments"])
    assert all(row["promotion_allowed"] is False for row in registry["experiments"])
    assert [row["parameters"]["signal"] for row in registry["experiments"]] == [
        "6M",
        "6M",
        "12M_EX_LAST_1M",
    ]
    assert [row["parameters"]["rebalance_frequency"] for row in registry["experiments"]] == [
        "MONTHLY",
        "QUARTERLY",
        "MONTHLY",
    ]


def test_generic_calculators_do_not_create_extra_experiments() -> None:
    assert LOOKBACK_SESSIONS == {
        "3M": 63,
        "6M": 126,
        "9M": 189,
        "12M": 252,
        "12M_EX_LAST_1M": 252,
    }
    registry = experiment_registry(family_config())
    assert {row["parameters"]["signal"] for row in registry["experiments"]} == {
        "6M",
        "12M_EX_LAST_1M",
    }


def test_point_in_time_membership_never_uses_future_members() -> None:
    index = MembershipIndex(
        [
            MembershipPeriod("OLD", "I1", date(2022, 1, 1), date(2022, 6, 30), "TEST", "HIGH", "fixture"),
            MembershipPeriod("NEW", "I2", date(2022, 7, 1), None, "TEST", "HIGH", "fixture"),
        ]
    )
    assert set(index.members_for(date(2022, 6, 30))) == {"OLD"}
    assert set(index.members_for(date(2022, 7, 1))) == {"NEW"}


def test_price_and_liquidity_gates_are_frozen() -> None:
    config = family_config()
    assert PRICE_FLOOR == Decimal("100")
    assert config["universe"]["minimum_price_inr"] == Decimal("100")
    assert config["universe"]["liquidity_window_sessions"] == 20
    assert config["universe"]["minimum_median_traded_value_inr"] == Decimal("100000000")


def test_six_month_compounded_return_uses_exact_126_session_endpoint() -> None:
    sessions = trading_dates(253)
    closes = {sessions[0]: Decimal("100"), sessions[126]: Decimal("125")}
    result = compounded_return(closes, sessions, sessions[126], "6M")
    assert result["start_date"] == sessions[0]
    assert result["end_date"] == sessions[126]
    assert result["value"] == Decimal("0.25")


def test_twelve_minus_one_excludes_exactly_21_sessions() -> None:
    sessions = trading_dates(253)
    closes = {
        sessions[0]: Decimal("80"),
        sessions[231]: Decimal("120"),
        sessions[252]: Decimal("999"),
    }
    result = compounded_return(closes, sessions, sessions[252], "12M_EX_LAST_1M")
    assert result["start_date"] == sessions[0]
    assert result["end_date"] == sessions[231]
    assert result["value"] == Decimal("0.5")


def test_missing_exact_endpoint_is_unavailable_and_not_backfilled() -> None:
    sessions = trading_dates(127)
    closes = {sessions[0]: Decimal("100"), sessions[125]: Decimal("130")}
    result = compounded_return(closes, sessions, sessions[126], "6M")
    assert result["value"] is None
    assert result["reason"] == "MISSING_EXACT_ENDPOINT_PRICE"


def test_monthly_and_quarterly_calendars_use_next_open_without_lookahead() -> None:
    sessions = [
        date(2022, 1, 28),
        date(2022, 1, 31),
        date(2022, 2, 1),
        date(2022, 2, 28),
        date(2022, 3, 1),
        date(2022, 3, 31),
        date(2022, 4, 1),
    ]
    rows = build_rebalance_calendar(
        sessions,
        development_start=date(2022, 1, 1),
        development_end=date(2022, 4, 1),
    )
    monthly = [row for row in rows if row["schedule"] == "MONTHLY"]
    quarterly = [row for row in rows if row["schedule"] == "QUARTERLY"]
    assert [(row["formation_date"], row["execution_date"]) for row in monthly] == [
        ("2022-01-31", "2022-02-01"),
        ("2022-02-28", "2022-03-01"),
        ("2022-03-31", "2022-04-01"),
    ]
    assert [(row["formation_date"], row["execution_date"]) for row in quarterly] == [
        ("2022-03-31", "2022-04-01")
    ]
    assert all(row["formation_date"] < row["execution_date"] for row in rows)
    assert all(row["same_close_execution"] is False for row in rows)


def test_top_decile_selection_is_single_breadth_and_not_v1_max_four() -> None:
    result = select_top_decile(eligible_rows(200), signal_field="6m_return")
    assert result["selected_count"] == 20
    assert result["sufficient_universe"] is True
    assert len(result["selected"]) == 20
    assert len(result["selected"]) > 4


def test_top_decile_tie_breaks_by_symbol() -> None:
    result = select_top_decile(eligible_rows(200, equal_signal=True), signal_field="6m_return")
    assert [row["symbol"] for row in result["selected"]] == [f"S{index:03d}" for index in range(20)]


def test_top_decile_does_not_loosen_minimum_portfolio_size() -> None:
    result = select_top_decile(eligible_rows(190), signal_field="6m_return")
    assert result["selected_count"] == 19
    assert result["sufficient_universe"] is False
    assert result["selected"] == []


def test_equal_weights_are_exact_and_deterministic() -> None:
    weights = equal_weight_targets(["C", "A", "B"])
    assert list(weights) == ["A", "B", "C"]
    assert set(weights.values()) == {Decimal("1") / Decimal("3")}
    assert abs(sum(weights.values()) - Decimal("1")) < Decimal("1e-27")


def test_family_is_long_only_unlevered_and_has_no_stop_or_target() -> None:
    portfolio = family_config()["portfolio"]
    assert portfolio["direction"] == "LONG_ONLY"
    assert portfolio["leverage_allowed"] is False
    assert portfolio["shorting_allowed"] is False
    assert portfolio["stop_loss"] is None
    assert portfolio["profit_target"] is None
    assert portfolio["max_position_count"] == "DERIVED_FROM_TOP_DECILE_NOT_V1_MAX_4"


def test_integer_share_feasibility_reports_unaffordable_names_and_cash() -> None:
    result = integer_share_targets(
        ["CHEAP", "EXPENSIVE"],
        {"CHEAP": Decimal("1000"), "EXPENSIVE": Decimal("60000")},
    )
    rows = {row["symbol"]: row for row in result["targets"]}
    assert rows["CHEAP"]["target_shares"] == 50
    assert rows["EXPENSIVE"]["target_shares"] == 0
    assert rows["EXPENSIVE"]["skipped_due_to_affordability"] is True
    assert result["cash_residual"] == Decimal("50000")


def test_rebalance_retention_turnover_and_cost_integration() -> None:
    result = plan_rebalance(
        {"A": 10, "B": 10},
        {"B": 8, "C": 5},
        {"A": Decimal("100"), "B": Decimal("200"), "C": Decimal("300")},
        value_date=date(2024, 1, 2),
        portfolio_value=Decimal("10000"),
    )
    assert result["names_retained"] == ["B"]
    assert result["names_added"] == ["C"]
    assert result["names_removed"] == ["A"]
    assert result["turnover_by_component"] == {
        "EXITS": Decimal("1000"),
        "ENTRIES": Decimal("1500"),
        "WEIGHT_ADJUSTMENTS": Decimal("400"),
    }
    assert result["one_way_turnover"] == Decimal("0.29")
    assert result["round_trip_equivalent_turnover"] == Decimal("0.145")
    assert result["total_transaction_cost"] > 0


def test_cost_engine_has_5bps_buy_stamp_and_sell_dp_semantics() -> None:
    buy = estimate_order_cost("BUY", date(2024, 1, 2), Decimal("10000"))
    sell = estimate_order_cost("SELL", date(2024, 1, 2), Decimal("10000"))
    assert buy["cost_config_hash"] == EXPECTED_COST_CONFIG_HASH
    assert buy["scenario_id"] == "COST-SCENARIO-002"
    assert buy["slippage"] == Decimal("5.00")
    assert buy["components"][STAMP_DUTY] > 0
    assert buy["components"][DP_CHARGE] == 0
    assert sell["components"][DP_CHARGE] > 0
    assert sell["components"][STAMP_DUTY] == 0


def test_command_one_has_no_performance_winner_validation_access_or_strategy_v2() -> None:
    config = family_config()
    registry = experiment_registry(config)
    assert config["performance_policy"] == {
        "final_comparison_allowed": False,
        "winner_selection_allowed": False,
        "performance_results_generated": False,
        "strategy_v2_creation_allowed": False,
    }
    assert config["temporal_governance"]["family_a_validation_authorized"] is False
    assert config["temporal_governance"]["family_a_validation_accessed"] is False
    assert registry["performance_evaluated"] is False
    assert registry["winner"] is None


def test_frozen_cost_and_project_baseline_are_immutable_during_preregistration() -> None:
    before = frozen_project_snapshot(REPO_ROOT)
    config = family_config()
    verify_registry(experiment_registry(config), config)
    after = frozen_project_snapshot(REPO_ROOT)
    assert default_cost_model_config().config_hash() == EXPECTED_COST_CONFIG_HASH
    assert before == after


def test_report_contract_and_writers(tmp_path: Path) -> None:
    assert REPORT_NAMES == (
        "family_a_v1_summary.json",
        "family_a_v1_data_readiness.csv",
        "family_a_v1_signal_pilot.csv",
        "family_a_v1_rebalance_calendar.csv",
        "family_a_v1_universe_coverage.csv",
        "family_a_v1_capital_feasibility.csv",
        "family_a_v1_registry.csv",
    )
    write_json(tmp_path / REPORT_NAMES[0], {"family_version": FAMILY_VERSION})
    for name in REPORT_NAMES[1:]:
        write_csv(tmp_path / name, [{"status": "GENERATED"}])
    assert all((tmp_path / name).stat().st_size > 0 for name in REPORT_NAMES)

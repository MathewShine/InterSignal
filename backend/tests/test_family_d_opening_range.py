from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_c_research_closure import EXPECTED_FAMILY_C_CLOSURE_HASH
from app.research.strategy.family_d_opening_range import (
    ACTIVITY_THRESHOLD,
    BOUNDED_RESEARCH_LABEL,
    CONTROL_ID,
    CONTROL_NAME,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_D001_PARAMETER_HASH,
    EXPECTED_D001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CONFIG_HASH,
    EXPECTED_INTRADAY_SCOPE_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_COUNT,
    FAMILY_D_ARCHITECTURE_RESULT_VALUES,
    FAMILY_D_DATA_READINESS_VALUES,
    FAMILY_CODE,
    FAMILY_VERSION,
    FUTURE_OUTCOME_FIELDS,
    GOVERNANCE_CHECKLIST,
    MAX_CONCURRENT_POSITIONS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    RISK_PER_TRADE,
    SIGNAL_FIELDS,
    TIME_EXIT,
    TREATMENT_ID,
    TREATMENT_NAME,
    control_document,
    d001_parameter_document,
    first_breakout,
    opening_activity_ratio,
    opening_range_15m,
    preregistration_document,
    rank_capacity,
    risk_position_size,
    stop_exit,
    success_criteria_document,
    time_exit_bar,
    verify_preregistration_hashes,
    verify_scope_hash,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data/research/strategy_families/family_d/v1"
REPORT_ROOT = REPO_ROOT / "data/reports"
IST = ZoneInfo("Asia/Kolkata")


def _summary() -> dict:
    return json.loads((REPORT_ROOT / "family_d_v1_summary.json").read_text(encoding="utf-8"))


def _bar(hh: int, mm: int, *, open_: str = "100", high: str = "101", low: str = "99", close: str = "100", volume: int = 100, sequence: int = 1):
    start = datetime(2024, 1, 2, hh, mm, tzinfo=IST)
    return SimpleNamespace(
        symbol="TEST",
        trading_date=date(2024, 1, 2),
        bar_start=start,
        bar_end=start + timedelta(minutes=5),
        session_sequence=sequence,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


def test_exact_ids_profile_protocol_and_one_treatment() -> None:
    assert FAMILY_VERSION == "STRATEGY_FAMILY_D_OPENING_RANGE_V1"
    assert RESEARCH_PROFILE == "INTRADAY_OPENING_RANGE_STOCKS_IN_PLAY_V1"
    assert FAMILY_CODE == "FAMILY_D"
    assert RESEARCH_PROTOCOL == "FAMILY_D_RESEARCH_PROTOCOL_V1"
    assert BOUNDED_RESEARCH_LABEL == "BOUNDED_100_SYMBOL_INTRADAY_DEVELOPMENT_RESEARCH"
    assert (CONTROL_ID, CONTROL_NAME) == ("CONTROL-D-000", "ORB15_PLAIN_V1")
    assert (TREATMENT_ID, TREATMENT_NAME, EXPERIMENT_COUNT) == ("ORB-D-001", "ORB15_WITH_OPENING_ACTIVITY_V1", 1)


def test_preregistration_hashes_and_family_c_closure_are_frozen() -> None:
    assert all(verify_preregistration_hashes().values())
    assert verify_scope_hash(REPO_ROOT)
    summary = _summary()
    assert summary["hashes"] == {
        "family_d_config_hash": EXPECTED_FAMILY_D_CONFIG_HASH,
        "intraday_scope_hash": EXPECTED_INTRADAY_SCOPE_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "d001_parameter_hash": EXPECTED_D001_PARAMETER_HASH,
        "d001_preregistration_hash": EXPECTED_D001_PREREGISTRATION_HASH,
        "family_d_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
    }
    assert summary["freeze_gate"]["checks"]["family_c_closure_hash"] is True
    family_c = json.loads((REPORT_ROOT / "family_c_closure_v1_summary.json").read_text(encoding="utf-8"))
    assert family_c["family_c_closure_hash"] == EXPECTED_FAMILY_C_CLOSURE_HASH


def test_opening_range_uses_exact_first_three_bars() -> None:
    result = opening_range_15m([
        _bar(9, 15, high="102", low="99", volume=10),
        _bar(9, 20, high="103", low="98", volume=20),
        _bar(9, 25, high="101", low="97", volume=30),
        _bar(9, 30, high="999", low="1", volume=999),
    ])
    assert result["available"] is True
    assert result["high"] == Decimal("103")
    assert result["low"] == Decimal("97")
    assert result["volume"] == Decimal("60")


def test_breakout_is_strict_in_window_and_entry_is_next_open() -> None:
    bars = [
        _bar(9, 30, close="101", sequence=4),
        _bar(9, 35, open_="102", close="101", sequence=5),
    ]
    assert first_breakout(bars, Decimal("101"))["signal_bar"] is None
    bars[0].close = Decimal("101.01")
    result = first_breakout(bars, Decimal("101"))
    assert result["signal_bar"] is bars[0]
    assert result["entry_bar"] is bars[1]
    assert result["entry_bar"].open == Decimal("102")
    assert first_breakout([_bar(11, 35, close="102")], Decimal("101"))["signal_bar"] is None


def test_stop_no_target_time_exit_and_one_trade_policy() -> None:
    control = control_document()["rules"]
    assert control["stop"] == "ORL"
    assert control["profit_target"] is None
    assert control["time_exit"] == "FIRST_VALID_OPEN_AT_OR_AFTER_15:20"
    assert TIME_EXIT.isoformat(timespec="minutes") == "15:20"
    exit_bar = _bar(15, 20, open_="105")
    assert time_exit_bar([exit_bar]) is exit_bar
    config = _summary()["family"]
    assert config["mechanics"]["one_position_per_symbol_session"] is True
    assert config["mechanics"]["reentry_allowed"] is False
    assert tuple(FUTURE_OUTCOME_FIELDS) and "net_pnl" in FUTURE_OUTCOME_FIELDS


def test_activity_ratio_exact_threshold_and_prior20_requirement() -> None:
    equal = opening_activity_ratio(150, [100] * 20)
    assert equal == {"available": True, "median": Decimal("100"), "ratio": Decimal("1.5"), "pass": True}
    assert opening_activity_ratio(149, [100] * 20)["pass"] is False
    assert opening_activity_ratio(200, [100] * 19)["available"] is False
    assert ACTIVITY_THRESHOLD == Decimal("1.50")
    params = d001_parameter_document()
    assert params["gap_filter"] is None
    assert params["vwap_filter"] is None
    assert params["news_filter"] is None


def test_risk_size_cash_constraint_no_leverage_and_capacity() -> None:
    result = risk_position_size(equity=Decimal("500000"), available_cash=Decimal("500000"), entry_price=Decimal("100"), stop_price=Decimal("95"))
    assert RISK_PER_TRADE == Decimal("0.005")
    assert result["shares"] == 500
    assert result["planned_risk"] == Decimal("2500")
    assert result["notional"] <= Decimal("500000")
    constrained = risk_position_size(equity=Decimal("500000"), available_cash=Decimal("1000"), entry_price=Decimal("100"), stop_price=Decimal("95"))
    assert constrained["shares"] == 10 and constrained["cash_constrained"] is True
    assert MAX_CONCURRENT_POSITIONS == 5


def test_capacity_rankings_and_ties_are_exact() -> None:
    rows = [
        {"symbol": "B", "breakout_excess_pct": "0.03", "opening_activity_ratio": "1.6"},
        {"symbol": "A", "breakout_excess_pct": "0.03", "opening_activity_ratio": "1.7"},
        {"symbol": "C", "breakout_excess_pct": "0.04", "opening_activity_ratio": "1.5"},
    ]
    assert [row["symbol"] for row in rank_capacity(rows, treatment=False)] == ["C", "A", "B"]
    assert [row["symbol"] for row in rank_capacity(rows, treatment=True)] == ["A", "B", "C"]


def test_stop_touch_and_intraday_gap_through_are_deterministic() -> None:
    entry = _bar(9, 35, open_="105", low="102")
    touch = _bar(9, 40, open_="102", low="99")
    result = stop_exit([entry, touch], entry_timestamp=entry.bar_start, stop_price=Decimal("100"))
    assert result["exit_reason"] == "STOP_FIRST" and result["reference_price"] == Decimal("100")
    gap = _bar(9, 40, open_="98", low="97")
    result = stop_exit([entry, gap], entry_timestamp=entry.bar_start, stop_price=Decimal("100"))
    assert result["exit_reason"] == "GAP_THROUGH_STOP" and result["reference_price"] == Decimal("98")


def test_exact_success_criteria_and_governance_14_of_14() -> None:
    criteria = success_criteria_document()
    assert criteria["family_d_success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH
    assert len(criteria["control_viability_all_required"]) == 7
    assert len(criteria["treatment_standard_criteria"]) == 7
    assert len(criteria["quality_dimensions"]) == 4
    assert criteria["high_win_rate_flag"] == "YES_IF_WIN_RATE_GTE_60_PERCENT_DESCRIPTIVE_ONLY"
    assert criteria["drawdown_fatal"] == "GT_20_PERCENT_RELATIVE_WORSENING"
    assert len(GOVERNANCE_CHECKLIST) == 14
    assert _summary()["governance_v2"] == {"passed": 14, "total": 14, "all_pass": True}


def test_scope_counts_structural_block_and_no_outcomes() -> None:
    summary = _summary()
    assert summary["scope"] == {"symbol_count": 100, "symbol_session_count": 4821, "strict_session_count": 4812}
    assert summary["structural_counts"]["d001_subset_violations"] == 0
    assert summary["activity_distribution"]["observation_count"] == 0
    assert summary["FAMILY_D_DATA_READINESS"] == "BLOCKED"
    assert summary["FAMILY_D_ARCHITECTURE_RESULT"] == "DATA_BLOCKED"
    assert set(FAMILY_D_DATA_READINESS_VALUES) == {"READY_FOR_BOUNDED_RESEARCH", "READY_WITH_LIMITATIONS", "BLOCKED", "INCONCLUSIVE"}
    assert set(FAMILY_D_ARCHITECTURE_RESULT_VALUES) == {"READY_FOR_DEVELOPMENT_BACKTEST", "METHODOLOGY_FIX_REQUIRED", "DATA_BLOCKED", "INCONCLUSIVE"}
    assert all(value is False for value in summary["no_performance_policy"].values())
    assert set(SIGNAL_FIELDS) == set((OUTPUT_ROOT / "signals/family_d_structural_signals_v1.csv").read_text(encoding="utf-8").splitlines()[0].split(","))


def test_no_validation_no_strategy_v2_and_security_guards() -> None:
    summary = _summary()
    assert summary["governance"] == {
        "validation_accessed": False,
        "strategy_v2_created": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_order_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "previous_family_baseline_unchanged": True,
    }
    assert preregistration_document()["performance_evaluated"] is False
    assert preregistration_document()["validation_accessed"] is False


def test_reports_storage_documentation_roadmap_and_pilots() -> None:
    expected_reports = {
        "family_d_v1_summary.json", "family_d_v1_registry.csv", "family_d_v1_data_readiness.csv",
        "family_d_v1_signal_counts.csv", "family_d_v1_activity_distribution.csv", "family_d_v1_time_distribution.csv",
        "family_d_v1_pilots.csv", "family_d_v1_scope.csv", "family_d_v1_governance.csv",
    }
    assert all((REPORT_ROOT / name).is_file() for name in expected_reports)
    assert all((OUTPUT_ROOT / directory).is_dir() for directory in ("registry", "signals", "pilots", "manifests", "governance", "scope", "activity"))
    assert (REPO_ROOT / "docs/strategy-family-d-opening-range-stocks-in-play-v1.md").is_file()
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert "| Family D | Opening Range / Stocks-in-Play | ACTIVE_PREREGISTRATION |" in roadmap
    for family in "EFG":
        assert f"| Family {family} |" in roadmap and "PLANNED_NOT_STARTED" in next(line for line in roadmap.splitlines() if line.startswith(f"| Family {family} |"))
    assert _summary()["pilots"] == {"passed": 23, "total": 23, "all_pass": True}


def test_artifact_manifest_hashes_recompute() -> None:
    path = OUTPUT_ROOT / "manifests/family_d_artifact_manifest_v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_d_artifact_manifest_hash"
    }
    assert canonical_hash(body) == manifest["family_d_artifact_manifest_hash"]
    assert manifest["family_d_config_hash"] == EXPECTED_FAMILY_D_CONFIG_HASH
    assert manifest["intraday_scope_hash"] == EXPECTED_INTRADAY_SCOPE_HASH
    assert all(
        (REPO_ROOT / relative).is_file()
        and file_sha256(REPO_ROOT / relative) == expected
        for relative, expected in manifest["artifact_hashes"].items()
    )

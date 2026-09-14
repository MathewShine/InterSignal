from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_e_pullback_reclaim import (
    CONTROL_ID,
    CONTROL_NAME,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_E001_PARAMETER_HASH,
    EXPECTED_E001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CLOSURE_HASH,
    EXPECTED_FAMILY_E_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPERIMENT_COUNT,
    FAMILY_CODE,
    FAMILY_VERSION,
    GOVERNANCE_CHECKLIST,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    REPORT_NAMES,
    RISK_PER_TRADE,
    STARTING_CAPITAL,
    TREATMENT_ID,
    TREATMENT_NAME,
    compounded_return_20d,
    daily_stop_execution,
    e001_parameter_document,
    entry_exit_chronology,
    high_win_rate_flag,
    previous_research_snapshot,
    pullback_structure,
    rank_capacity_signals,
    reclaim_requirement,
    risk_position_size,
    simple_moving_average,
    structural_stop,
    success_criteria_document,
    trend_requirement,
    verify_family_d_closure,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_ROOT = REPO_ROOT / "data/research/strategy_families/family_e/v1"
SUMMARY_PATH = REPO_ROOT / "data/reports/family_e_v1_summary.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_family_d_closure_hash_is_verified_before_family_e() -> None:
    result = verify_family_d_closure(REPO_ROOT)
    assert result["status"] == "VERIFIED"
    assert all(result["checks"].values())
    assert result["family_d_closure_hash"] == EXPECTED_FAMILY_D_CLOSURE_HASH
    assert EXPECTED_FAMILY_D_CLOSURE_HASH == (
        "1628774e5a6032487ac6e15e9beba21cbf52c96389b83aca7d4e87a46e577414"
    )


def test_exact_family_identity_registry_and_hashes() -> None:
    summary = _summary()
    assert FAMILY_VERSION == "STRATEGY_FAMILY_E_PULLBACK_RECLAIM_V1"
    assert RESEARCH_PROFILE == "DAILY_PULLBACK_RECLAIM_CONTINUATION_V1"
    assert FAMILY_CODE == "FAMILY_E"
    assert RESEARCH_PROTOCOL == "FAMILY_E_RESEARCH_PROTOCOL_V1"
    assert CONTROL_ID == "CONTROL-E-000"
    assert CONTROL_NAME == "TREND_PULLBACK_RECLAIM_V1"
    assert TREATMENT_ID == "PBR-E-001"
    assert TREATMENT_NAME == "TREND_PULLBACK_RECLAIM_WITH_50DMA_STRUCTURE_V1"
    assert EXPERIMENT_COUNT == 1 == summary["experiment_count"]
    assert summary["family_e_config_hash"] == EXPECTED_FAMILY_E_CONFIG_HASH
    assert summary["control"]["reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    assert summary["experiment"]["parameter_hash"] == EXPECTED_E001_PARAMETER_HASH
    assert summary["experiment"]["preregistration_hash"] == EXPECTED_E001_PREREGISTRATION_HASH
    assert summary["family_e_success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH


def test_all_frozen_document_hashes_are_canonical() -> None:
    config = _json(FAMILY_ROOT / "registry/family_e_config_v1.json")
    control = _json(FAMILY_ROOT / "registry/control_e_000_reference_v1.json")
    treatment = _json(FAMILY_ROOT / "registry/pbr_e_001_preregistration_v1.json")
    criteria = _json(FAMILY_ROOT / "governance/success_criteria_v1.json")
    assert canonical_hash({key: value for key, value in config.items() if key != "family_e_config_hash"}) == config["family_e_config_hash"] == EXPECTED_FAMILY_E_CONFIG_HASH
    assert canonical_hash({key: value for key, value in control.items() if key != "control_e_000_reference_hash"}) == control["control_e_000_reference_hash"] == EXPECTED_CONTROL_REFERENCE_HASH
    assert canonical_hash(treatment["parameters"]) == treatment["pbr_e_001_parameter_hash"] == EXPECTED_E001_PARAMETER_HASH
    assert canonical_hash({key: value for key, value in treatment.items() if key != "pbr_e_001_preregistration_hash"}) == treatment["pbr_e_001_preregistration_hash"] == EXPECTED_E001_PREREGISTRATION_HASH
    assert canonical_hash({key: value for key, value in criteria.items() if key != "family_e_success_criteria_hash"}) == criteria["family_e_success_criteria_hash"] == EXPECTED_SUCCESS_CRITERIA_HASH


def test_sma20_sma50_and_20d_return_are_exact_and_causal() -> None:
    values20 = [Decimal(index) for index in range(1, 21)]
    values50 = [Decimal(index) for index in range(1, 51)]
    assert simple_moving_average(values20, 20) == Decimal("10.5")
    assert simple_moving_average(values50, 50) == Decimal("25.5")
    assert simple_moving_average(values20[:-1], 20) is None
    closes = [Decimal("100")] + [Decimal("101")] * 19 + [Decimal("110")]
    assert compounded_return_20d(closes) == Decimal("0.10")
    assert compounded_return_20d(closes[:-1]) is None


def test_trend_strict_inequalities_and_positive_return() -> None:
    assert trend_requirement(Decimal("110"), Decimal("105"), Decimal("100"), Decimal("0.01"))
    assert not trend_requirement(Decimal("100"), Decimal("105"), Decimal("100"), Decimal("0.01"))
    assert not trend_requirement(Decimal("110"), Decimal("100"), Decimal("100"), Decimal("0.01"))
    assert not trend_requirement(Decimal("110"), Decimal("105"), Decimal("100"), Decimal("0"))


def test_exact_five_session_pullback_touch_and_equality_semantics() -> None:
    result = pullback_structure(
        [106, 104, 103, 102, 104],
        [101, 101, 100, 102, 103],
        [105, 105, 104, 104, 104],
        [100, 100, 100, 100, 100],
    )
    assert result["available"] is True
    assert result["touch_count"] == 4
    assert result["minimum_low"] == Decimal("102")
    assert result["minimum_close_minus_sma50"] == Decimal("0")
    assert result["e001_structure_pass"] is True
    below = pullback_structure([99] * 5, [101, 101, 99, 101, 101], [100] * 5, [100] * 5)
    assert below["e001_structure_pass"] is False
    assert pullback_structure([99] * 4, [101] * 4, [100] * 4, [100] * 4)["available"] is False


def test_reclaim_is_strictly_above_previous_high_and_sma20() -> None:
    assert reclaim_requirement(Decimal("106"), Decimal("105"), Decimal("104"))["pass"]
    assert not reclaim_requirement(Decimal("105"), Decimal("105"), Decimal("104"))["pass"]
    assert not reclaim_requirement(Decimal("104"), Decimal("103"), Decimal("104"))["pass"]


def test_treatment_only_change_is_five_session_sma50_preservation() -> None:
    parameters = e001_parameter_document()
    assert parameters["base_control"] == CONTROL_ID
    assert parameters["base_rules_unchanged"] is True
    assert parameters["pullback_window_sessions"] == 5
    assert parameters["comparison_operator"] == ">="
    assert parameters["equality_passes"] is True
    assert parameters["volume_filter"] is None
    assert parameters["alternate_ranking"] is None


def test_next_open_entry_and_exact_ten_session_hold() -> None:
    sessions = [date(2024, 1, day) for day in range(1, 14)]
    result = entry_exit_chronology(sessions, sessions[0])
    assert result["entry_date"] == sessions[1]
    assert result["holding_sessions"] == HOLDING_SESSIONS == 10
    assert result["holding_dates"] == tuple(sessions[1:11])
    assert result["exit_date"] == sessions[11]


def test_structural_stop_has_no_buffer_and_gap_through_uses_open() -> None:
    assert structural_stop([99, 98, 97, 96, 95, 94]) == Decimal("94")
    assert structural_stop([99, 98, 97, 96, 95]) is None
    gap = daily_stop_execution(session_open=Decimal("93"), session_low=Decimal("92"), stop_price=Decimal("94"))
    touch = daily_stop_execution(session_open=Decimal("95"), session_low=Decimal("94"), stop_price=Decimal("94"))
    assert gap == {"exit_reason": "GAP_THROUGH_STOP", "reference_price": Decimal("93")}
    assert touch == {"exit_reason": "STOP_EXIT", "reference_price": Decimal("94")}


def test_half_percent_risk_whole_shares_cash_limit_and_no_leverage() -> None:
    assert STARTING_CAPITAL == Decimal("500000")
    assert RISK_PER_TRADE == Decimal("0.005")
    result = risk_position_size(equity=STARTING_CAPITAL, available_cash=STARTING_CAPITAL, entry_price=Decimal("100"), stop_price=Decimal("95"))
    assert result["allowed_risk"] == Decimal("2500")
    assert result["shares"] == 500
    assert result["planned_risk"] == Decimal("2500")
    constrained = risk_position_size(equity=STARTING_CAPITAL, available_cash=Decimal("10000"), entry_price=Decimal("100"), stop_price=Decimal("95"))
    assert constrained["shares"] == 100
    assert constrained["notional"] <= Decimal("10000")
    assert constrained["cash_constrained"] is True


def test_capacity_ranking_is_shared_return20_desc_then_symbol() -> None:
    rows = [
        {"symbol": "B", "return_20d": Decimal("0.20")},
        {"symbol": "A", "return_20d": Decimal("0.20")},
        *(
            {"symbol": f"Z{index:02d}", "return_20d": Decimal("0.19") - Decimal(index) / Decimal("1000")}
            for index in range(10)
        ),
    ]
    result = rank_capacity_signals(rows, MAX_CONCURRENT_POSITIONS)
    assert MAX_CONCURRENT_POSITIONS == 10
    assert [row["symbol"] for row in result["ranked"][:2]] == ["A", "B"]
    assert len(result["selected"]) == 10
    assert len(result["rejected"]) == 2


def test_success_criteria_are_exactly_frozen_before_performance() -> None:
    criteria = success_criteria_document()
    control = criteria["control_viability"]
    fatal = criteria["control_fatal_conditions"]
    treatment = criteria["treatment_standard_criteria"]
    quality = criteria["quality_dimensions"]
    assert control["A_NET_EXPECTANCY"]["operator"] == ">"
    assert control["B_NET_PROFIT_FACTOR"]["threshold"] == Decimal("1.05")
    assert control["C_NET_CAGR"]["operator"] == ">"
    assert control["D_MAX_DRAWDOWN_MAGNITUDE"]["threshold"] == Decimal("0.30")
    assert control["E_NONNEGATIVE_DEVELOPMENT_YEARS"]["threshold"] == 2
    assert control["F_CLOSED_POSITIONS"]["threshold"] == 150
    assert fatal["net_profit_factor"]["threshold"] == Decimal("0.90")
    assert fatal["net_expectancy"]["threshold"] == Decimal("-0.001")
    assert fatal["net_cagr"]["threshold"] == Decimal("-0.05")
    assert fatal["max_drawdown_magnitude"]["threshold"] == Decimal("0.40")
    assert fatal["closed_positions"]["threshold"] == 75
    assert treatment["A_RETURN_PRESERVATION"]["positive_control_cagr_ratio_threshold"] == Decimal("0.85")
    assert treatment["B_PROFITABILITY"]["net_profit_factor_threshold"] == Decimal("1.10")
    assert treatment["C_DRAWDOWN_NON_DEGRADATION"]["maximum_relative_worsening"] == Decimal("0.10")
    assert treatment["C_DRAWDOWN_NON_DEGRADATION"]["fatal_relative_worsening"] == Decimal("0.20")
    assert treatment["D_TEMPORAL_SUPPORT"]["maximum_yearly_underperformance_percentage_points"] == Decimal("10")
    assert treatment["E_COST_EFFICIENCY"]["maximum_normalized_cost_drag_multiple"] == Decimal("1.25")
    assert treatment["F_SAMPLE_ADEQUACY"] == {"pass_minimum_closed_positions": 100, "limited_sample_minimum": 60, "limited_sample_maximum": 99, "fatal_sample_failure_below": 60}
    assert quality["H_WIN_RATE_IMPROVEMENT"]["percentage_points"] == Decimal("5")
    assert quality["I_PROFIT_FACTOR_IMPROVEMENT"]["absolute_increment"] == Decimal("0.05")
    assert quality["J_EXPECTANCY_IMPROVEMENT"]["positive_control_multiple"] == Decimal("1.10")
    assert high_win_rate_flag(Decimal("0.60")) == "YES"
    assert high_win_rate_flag(Decimal("0.5999")) == "NO"
    assert criteria["performance_evaluated"] is False


def test_structural_counts_years_subset_and_filter_impact() -> None:
    structural = _summary()["structural_counts"]
    assert structural["eligible_universe_rows"] == 199915
    assert structural["trend_pass_rows"] == 84980
    assert structural["pullback_touch_rows"] == 39150
    assert structural["control_signals"] == 10754
    assert structural["e001_signals"] == 8343
    assert structural["e001_subset_violations"] == 0
    impact = structural["filter_impact"][0]
    assert impact["removed_by_sma50_structure"] == 2411
    assert str(impact["removal_pct_of_control"]).startswith("22.4195648130")
    counts = {row["metric"]: row for row in structural["yearly"]}
    assert (counts["CONTROL_E_000_SIGNALS"]["2022"], counts["CONTROL_E_000_SIGNALS"]["2023"], counts["CONTROL_E_000_SIGNALS"]["2024"]) == (2301, 3687, 4766)
    assert (counts["PBR_E_001_SIGNALS"]["2022"], counts["PBR_E_001_SIGNALS"]["2023"], counts["PBR_E_001_SIGNALS"]["2024"]) == (1706, 2988, 3649)
    assert all(row["outcomes_inspected"] is False for row in structural["yearly"])


def test_all_structural_pilots_and_governance_v2_pass() -> None:
    pilots = read_csv(REPO_ROOT / "data/reports/family_e_v1_pilots.csv")
    governance = read_csv(REPO_ROOT / "data/reports/family_e_v1_governance.csv")
    assert len(pilots) == 20
    assert all(row["passed"] == "True" for row in pilots)
    assert {row["category"] for row in pilots} == {"CONTROL", "E001", "HOLDING", "STOP", "GAP_THROUGH", "RISK_SIZING", "CAPACITY", "ACCOUNTING"}
    assert len(GOVERNANCE_CHECKLIST) == len(governance) == 14
    assert all(row["status"] == "PASS" for row in governance)
    assert all(row["governance_policy"] == "RESEARCH_EXPERIMENT_GOVERNANCE_V2" for row in governance)


def test_data_readiness_architecture_and_development_partition() -> None:
    summary = _summary()
    assert summary["classifications"]["FAMILY_E_DATA_READINESS"] == "READY_WITH_LIMITATIONS"
    assert summary["classifications"]["FAMILY_E_ARCHITECTURE_RESULT"] == "READY_FOR_DEVELOPMENT_BACKTEST"
    assert DEVELOPMENT_START == date(2022, 1, 1)
    assert DEVELOPMENT_END == date(2024, 12, 31)
    assert summary["development_window"]["prehistory_version"] == "DAILY_HISTORY_PREHISTORY_V2"
    assert summary["data"]["post_2024_loaded"] is False
    readiness = {row["check"]: row for row in read_csv(REPO_ROOT / "data/reports/family_e_v1_data_readiness.csv")}
    assert {"SMA20", "SMA50", "RETURN_20D", "FIVE_SESSION_PULLBACK_HISTORY", "PREVIOUS_DAY_HIGH", "NEXT_OPEN_AVAILABILITY", "TEN_SESSION_FUTURE_DEVELOPMENT_PATH", "CORPORATE_ACTION_SAFETY", "LIQUIDITY_HISTORY", "POINT_IN_TIME_MEMBERSHIP"} <= set(readiness)


def test_no_performance_validation_mutations_or_strategy_v2() -> None:
    governance = _summary()["governance"]
    assert governance["development_performance_run"] is False
    assert governance["validation_accessed"] is False
    assert governance["alternate_ma_tested"] is False
    assert governance["alternate_pullback_tested"] is False
    assert governance["alternate_reclaim_tested"] is False
    assert governance["volume_filter_added"] is False
    assert governance["target_added"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["family_f_started"] is False
    source = (REPO_ROOT / "backend/app/research/strategy/family_e_pullback_reclaim.py").read_text(encoding="utf-8")
    assert "simulate_strategy(" not in source
    assert "final_development_performance_allowed_in_command_01\": True" not in source


def test_previous_families_and_daily_history_are_immutable() -> None:
    summary = _summary()
    snapshot = previous_research_snapshot(REPO_ROOT)
    assert summary["immutability"]["previous_families_unchanged"] is True
    assert summary["immutability"]["baseline_snapshot_before"] == snapshot["snapshot_hash"]
    assert summary["immutability"]["baseline_snapshot_after"] == snapshot["snapshot_hash"]
    for field in ("strategy_v1_unchanged", "cap4_unchanged", "family_a_unchanged", "family_b_unchanged", "family_c_unchanged", "family_d_unchanged", "daily_history_prehistory_v2_unchanged"):
        assert summary["immutability"][field] is True


def test_manifest_artifacts_reports_and_documentation() -> None:
    manifest = _json(FAMILY_ROOT / "manifests/family_e_architecture_manifest_v1.json")
    body = {key: value for key, value in manifest.items() if key != "family_e_architecture_manifest_hash"}
    assert canonical_hash(body) == manifest["family_e_architecture_manifest_hash"]
    assert manifest["family_d_closure_hash"] == EXPECTED_FAMILY_D_CLOSURE_HASH
    assert all((REPO_ROOT / relative).is_file() and file_sha256(REPO_ROOT / relative) == expected for relative, expected in manifest["artifact_hashes"].items())
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    assert (REPO_ROOT / "docs/strategy-family-e-pullback-reclaim-continuation-v1.md").is_file()
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[1])) == 2
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[4])) == 4
    assert len(read_csv(REPO_ROOT / "data/reports" / REPORT_NAMES[7])) == 2


def test_roadmap_marks_family_e_active_and_family_f_not_started() -> None:
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap
    assert "| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |" in roadmap
    assert "| Family E | Pullback / Reclaim | ACTIVE_PREREGISTRATION |" in roadmap
    assert "| Family F | Catalyst Momentum | PLANNED_NOT_STARTED |" in roadmap
    assert "| Family G | Regime / Volatility | PLANNED_NOT_STARTED |" in roadmap


def test_security_counters_are_zero() -> None:
    security = _summary()["security"]
    for field in ("live_signals", "live_orders", "broker_calls", "remote_migrations", "supabase_persistence", "external_writes", "secrets_added"):
        assert security[field] == 0

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_c_breakout_continuation import (
    COMPRESSION_THRESHOLD,
    DEVELOPMENT_END,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    FamilyCBar,
)
from app.research.strategy.family_c_c001_attribution_audit import (
    COHORT_LABEL,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_C001_RESULT_HASH,
    EXPECTED_C002_RESULT_HASH,
    EXPECTED_CONTROL_RESULT_HASH,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    NORMALIZED_EVENT_NOTIONAL,
    REPLAY_LABEL,
    REPORT_NAMES,
    build_event_cohort,
    capacity_ranking_rows,
    classify_capacity_materiality,
    classify_capacity_selection,
    classify_development_advantage,
    classify_ranking,
    classify_signal_quality,
    classify_temporal_consistency,
    cohort_metrics,
    compression_bucket_rows,
    compression_distribution_rows,
    holding_path_rows,
    next_stage,
    normalized_event_outcome,
    occupancy_metrics,
    same_day_matched_rows,
    verify_frozen_inputs,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    REPO_ROOT
    / "data/research/strategy_families/family_c/v1/c001_attribution_audit"
)


def _bar(trading_date: date, symbol: str, price: Decimal) -> FamilyCBar:
    return FamilyCBar(
        trading_date=trading_date,
        symbol=symbol,
        isin=f"TEST-{symbol}",
        open_price=price,
        high_price=price * Decimal("1.02"),
        low_price=price * Decimal("0.98"),
        close_price=price * Decimal("1.01"),
        volume=Decimal("100000"),
        usability_status="ADJUSTED_READY",
        methodology_version="TEST",
    )


def _synthetic_cohort_inputs():
    sessions = [date(2022, 1, 1) + timedelta(days=index) for index in range(20)]
    bars = {
        session: {
            "PASS": _bar(session, "PASS", Decimal("100") + index),
            "FAIL": _bar(session, "FAIL", Decimal("90") + index),
        }
        for index, session in enumerate(sessions)
    }
    rows = [
        {
            "decision_date": sessions[0],
            "symbol": "PASS",
            "isin": "TEST-PASS",
            "close": Decimal("100"),
            "breakout_strength_pct": Decimal("0.02"),
            "compression_range_pct": Decimal("0.08"),
            "formation_volume_ratio": Decimal("1.2"),
            "control_signal": True,
            "c001_signal": True,
        },
        {
            "decision_date": sessions[0],
            "symbol": "FAIL",
            "isin": "TEST-FAIL",
            "close": Decimal("90"),
            "breakout_strength_pct": Decimal("0.01"),
            "compression_range_pct": Decimal("0.081"),
            "formation_volume_ratio": Decimal("1.1"),
            "control_signal": True,
            "c001_signal": False,
        },
        {
            "decision_date": sessions[15],
            "symbol": "PASS",
            "isin": "TEST-PASS",
            "close": Decimal("115"),
            "breakout_strength_pct": Decimal("0.03"),
            "compression_range_pct": Decimal("0.07"),
            "formation_volume_ratio": Decimal("1.3"),
            "control_signal": True,
            "c001_signal": True,
        },
    ]
    return sessions, bars, rows


def _metric_record(**overrides):
    value = {
        "event_count": 100,
        "win_rate": Decimal("0.55"),
        "median_return": Decimal("0.005"),
        "net_expectancy": Decimal("0.006"),
        "net_profit_factor": Decimal("1.20"),
    }
    value.update(overrides)
    return value


def _admission_row(
    formation_date: str,
    symbol: str,
    rank: int,
    count: int,
    status: str,
    outcome: str,
    open_before: int = 19,
):
    return {
        "event_key": f"{formation_date}|{symbol}",
        "formation_date": formation_date,
        "entry_date": formation_date,
        "symbol": symbol,
        "breakout_strength_pct": Decimal("0.10") - Decimal(rank) / Decimal("100"),
        "admission_status": status,
        "explanation": "TEST",
        "open_positions_before_entry": open_before,
        "same_day_rank": rank,
        "same_day_ranked_candidates": count,
        "gross_10session_return": Decimal(outcome) + Decimal("0.004"),
        "estimated_normalized_net_return": Decimal(outcome),
        "MFE_pct": Decimal("0.03"),
        "MAE_pct": Decimal("-0.02"),
        "year": 2022,
    }


def test_exact_command_identity_and_frozen_input_hashes() -> None:
    assert COMMAND_VERSION == "FAMILY_C_C001_ATTRIBUTION_AUDIT_V1"
    assert COMMAND_PROFILE == "COMPRESSION_BREAKOUT_CAPACITY_ATTRIBUTION_V1"
    assert REPLAY_LABEL == "ATTRIBUTION_REPLAY_NOT_STRATEGY_EXPERIMENT"
    assert COHORT_LABEL == "SIGNAL_QUALITY_COHORT_ONLY"
    assert EXPECTED_CONTROL_RESULT_HASH == "efdf9ccdf70f4c58d1ce40e2f1e1ccb7e7fa8ad83c5fb3832ce0994d323b991f"
    assert EXPECTED_C001_RESULT_HASH == "8adc1aec00041256748a8fa086b4dae562a6841b844875fc39b3dd19b61680e4"
    assert EXPECTED_C002_RESULT_HASH == "49afe8ee5d766afa9a0e01195fa49041605c71483df0de9ac4c354b469a9a240"
    assert EXPECTED_DEVELOPMENT_REGISTRY_HASH == "529322157a13058f0e2f73e88d471b5f15e006b8eae1c1050a0110b77d6345bc"
    gate = verify_frozen_inputs(REPO_ROOT)
    assert gate["status"] == "VERIFIED"
    assert all(gate["checks"].values())


def test_normalized_event_cost_is_frozen_round_trip_and_cash_independent() -> None:
    result = normalized_event_outcome(
        date(2022, 1, 3),
        date(2022, 1, 17),
        Decimal("100"),
        Decimal("110"),
    )
    assert NORMALIZED_EVENT_NOTIONAL == Decimal("25000.00")
    assert result["gross_10session_return"] == Decimal("0.1")
    assert result["normalized_buy_cost"] > 0
    assert result["normalized_sell_cost"] > 0
    assert result["estimated_normalized_net_return"] < result["gross_10session_return"]


def test_event_cohort_requires_complete_development_path_and_exact_8_percent_rule() -> None:
    sessions, bars, rows = _synthetic_cohort_inputs()
    events = build_event_cohort(rows, sessions, bars)
    assert len(events) == 2
    assert {row["symbol"] for row in events} == {"PASS", "FAIL"}
    assert all(row["terminal_path_status"] == "COMPLETE_WITHIN_DEVELOPMENT" for row in events)
    passed = next(row for row in events if row["symbol"] == "PASS")
    assert passed["compression_range_pct"] == COMPRESSION_THRESHOLD
    assert passed["compression_pass"] is True
    assert passed["c001_signal"] is True
    assert date.fromisoformat(passed["exit_date"]) <= DEVELOPMENT_END
    assert HOLDING_SESSIONS == 10


def test_event_cohort_rejects_c001_rule_mismatch() -> None:
    sessions, bars, rows = _synthetic_cohort_inputs()
    rows[0]["c001_signal"] = False
    try:
        build_event_cohort(rows, sessions, bars)
    except ValueError as error:
        assert "exact <=8% rule" in str(error)
    else:
        raise AssertionError("Expected exact-threshold mismatch")


def test_cohort_metrics_pf_expectancy_win_rate_mfe_mae() -> None:
    rows = [
        {
            "estimated_normalized_net_return": Decimal("0.10"),
            "gross_10session_return": Decimal("0.11"),
            "MFE_pct": Decimal("0.15"),
            "MAE_pct": Decimal("-0.02"),
        },
        {
            "estimated_normalized_net_return": Decimal("-0.05"),
            "gross_10session_return": Decimal("-0.04"),
            "MFE_pct": Decimal("0.02"),
            "MAE_pct": Decimal("-0.08"),
        },
    ]
    metrics = cohort_metrics(rows)
    assert metrics["event_count"] == 2
    assert metrics["win_rate"] == Decimal("0.5")
    assert metrics["net_expectancy"] == Decimal("0.025")
    assert metrics["net_profit_factor"] == Decimal("2")
    assert metrics["median_MFE"] == Decimal("0.085")
    assert metrics["median_MAE"] == Decimal("-0.05")


def test_signal_quality_classification_clear_modest_negative_and_mixed() -> None:
    failed = _metric_record(
        win_rate=Decimal("0.50"),
        median_return=Decimal("0"),
        net_expectancy=Decimal("0.001"),
        net_profit_factor=Decimal("1.0"),
    )
    clear = _metric_record(
        win_rate=Decimal("0.54"),
        median_return=Decimal("0.005"),
        net_expectancy=Decimal("0.006"),
        net_profit_factor=Decimal("1.2"),
    )
    assert classify_signal_quality(clear, failed) == "CLEAR_POSITIVE"
    modest = {**clear, "win_rate": Decimal("0.51"), "net_profit_factor": Decimal("1.05")}
    assert classify_signal_quality(modest, failed) == "MODEST_POSITIVE"
    assert classify_signal_quality(failed, clear) == "NEGATIVE"
    mixed = {
        **clear,
        "win_rate": Decimal("0.49"),
        "median_return": Decimal("-0.001"),
    }
    assert classify_signal_quality(mixed, failed) == "MIXED"


def test_temporal_consistency_uses_all_three_frozen_years() -> None:
    rows = []
    for year, pass_value, fail_value in (
        (2022, "0.01", "0"),
        (2023, "0.02", "0.01"),
        (2024, "0.03", "0.01"),
    ):
        rows.extend(
            [
                {"year": year, "cohort": "COMPRESSION_PASS", "net_expectancy": Decimal(pass_value)},
                {"year": year, "cohort": "COMPRESSION_FAIL", "net_expectancy": Decimal(fail_value)},
            ]
        )
    assert classify_temporal_consistency(rows) == "CONSISTENT"
    rows[2]["net_expectancy"] = Decimal("-0.01")
    assert classify_temporal_consistency(rows) == "MOSTLY_CONSISTENT"


def test_capacity_selection_classification() -> None:
    rejected = _metric_record(
        win_rate=Decimal("0.50"),
        median_return=Decimal("0"),
        net_expectancy=Decimal("0.001"),
        net_profit_factor=Decimal("1.0"),
    )
    better = _metric_record()
    assert classify_capacity_selection(better, rejected) == "SELECTED_BETTER"
    assert classify_capacity_selection(rejected, better) == "SELECTED_WORSE"


def test_same_day_ranking_order_quartiles_and_matched_comparison() -> None:
    rows = [
        _admission_row("2022-01-03", f"S{rank}", rank, 8, "ADMITTED" if rank <= 2 else "CAPACITY_REJECTED", "0.02" if rank <= 4 else "-0.01")
        for rank in range(1, 9)
    ]
    detail, aggregate = capacity_ranking_rows(rows)
    assert [row["same_day_rank"] for row in detail] == list(range(1, 9))
    assert [row["rank_quartile"] for row in detail[:2]] == ["TOP_QUARTILE", "TOP_QUARTILE"]
    assert len(aggregate) == 4
    assert classify_ranking(aggregate) in {
        "POSITIVE_DISCRIMINATION",
        "WEAK_POSITIVE",
        "MIXED",
    }
    matched, overall = same_day_matched_rows(detail)
    assert len(matched) == 1
    assert overall["matched_day_count"] == 1
    assert overall["admitted"]["event_count"] == 2
    assert overall["capacity_rejected"]["event_count"] == 6


def test_occupancy_and_capacity_materiality() -> None:
    rows = [
        _admission_row("2022-01-03", "A", 1, 2, "ADMITTED", "0.01", 18),
        _admission_row("2022-01-04", "B", 1, 2, "ADMITTED", "0.01", 20),
    ]
    occupancy = occupancy_metrics(rows)
    assert occupancy["average_open_positions_before_entry"] == 19.0
    assert occupancy["fraction_entry_days_at_least_18_open"] == Decimal("1")
    assert occupancy["fraction_entry_days_exactly_20_open"] == Decimal("0.5")
    assert classify_capacity_materiality(Decimal("0.60"), occupancy, "SELECTED_WORSE") == "DOMINANT"
    assert MAX_CONCURRENT_POSITIONS == 20


def test_holding_breakout_gap_and_distribution_diagnostics_do_not_optimize() -> None:
    sessions, bars, rows = _synthetic_cohort_inputs()
    events = build_event_cohort(rows, sessions, bars)
    holding = holding_path_rows(events)
    assert {row["completed_sessions"] for row in holding} == {1, 3, 5, 10}
    assert all(row["diagnostic_only"] and not row["exit_rule_changed"] for row in holding)
    breakout = compression_bucket_rows(events, "BREAKOUT_STRENGTH")
    gap = compression_bucket_rows(events, "ENTRY_GAP")
    assert all(not row["threshold_optimized"] for row in breakout + gap)
    admissions = [
        {"event_key": events[0]["event_key"], "admission_status": "ADMITTED"}
    ]
    distribution = compression_distribution_rows(events, admissions)
    assert all(not row["alternate_cutoff_tested"] for row in distribution)


def test_attribution_and_next_stage_mapping() -> None:
    assert classify_development_advantage("CLEAR_POSITIVE", "SELECTED_WORSE", "MATERIAL") == "PRIMARILY_COMPRESSION_SIGNAL"
    assert classify_development_advantage("MODEST_POSITIVE", "SELECTED_BETTER", "MATERIAL") == "MIXED_SIGNAL_AND_CAPACITY"
    assert next_stage("CLEAR_POSITIVE", "MOSTLY_CONSISTENT", "SELECTED_WORSE", "MATERIAL") == "PREREGISTER_NEW_C001_IMPLEMENTATION_HYPOTHESIS"
    assert next_stage("MODEST_POSITIVE", "CONSISTENT", "SELECTED_SIMILAR", "MATERIAL") == "FREEZE_C001_FOR_VALIDATION_DESIGN"
    assert next_stage("MIXED", "UNSTABLE", "MIXED", "MATERIAL") == "PAUSE_FAMILY_C"


def test_generated_audit_reconciles_frozen_admission_counts() -> None:
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_c001_attribution_v1_summary.json").read_text(encoding="utf-8")
    )
    reconciliation = summary["capacity"]["reconciliation"]
    assert reconciliation["frozen_primary_counts_match"] is True
    assert reconciliation["all_signals_classified"] is True
    assert reconciliation["admitted_keys_match"] is True
    assert reconciliation["classification_counts"]["ADMITTED"] == 1170
    assert reconciliation["classification_counts"]["CAPACITY_REJECTED"] == 2624


def test_generated_result_hash_reports_and_governance() -> None:
    assert len(REPORT_NAMES) == 12
    for name in REPORT_NAMES:
        assert (REPO_ROOT / "data/reports" / name).is_file()
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_c001_attribution_v1_summary.json").read_text(encoding="utf-8")
    )
    field = "family_c_c001_attribution_hash"
    result = json.loads(
        (OUTPUT_ROOT / "manifests/family_c_c001_attribution_result_v1.json").read_text(encoding="utf-8")
    )
    assert canonical_hash({key: value for key, value in result.items() if key != field}) == result[field]
    assert summary[field] == result[field]
    assert summary["signal_cohort"]["c001_subset_violations"] == 0
    assert summary["governance"]["new_strategy_created"] is False
    assert summary["governance"]["compression_threshold_changed"] is False
    assert summary["governance"]["alternate_compression_threshold_tested"] is False
    assert summary["governance"]["capacity_changed"] is False
    assert summary["governance"]["alternate_capacity_tested"] is False
    assert summary["governance"]["holding_period_changed"] is False
    assert summary["governance"]["stop_added"] is False
    assert summary["governance"]["target_added"] is False
    assert summary["governance"]["c002_reevaluated"] is False
    assert summary["governance"]["validation_accessed"] is False
    assert summary["governance"]["strategy_v2_created"] is False
    assert summary["security"]["live_orders"] == 0


def test_required_storage_and_documentation_exist() -> None:
    for directory in (
        "event_cohort",
        "capacity",
        "ranking",
        "matched_days",
        "diagnostics",
        "manifests",
    ):
        assert (OUTPUT_ROOT / directory).is_dir()
    assert (REPO_ROOT / "docs/strategy-family-c-c001-attribution-audit-v1.md").is_file()

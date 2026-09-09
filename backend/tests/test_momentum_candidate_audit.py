from __future__ import annotations

import csv
import gzip
import json
from datetime import date
from decimal import Decimal

from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.momentum_candidate_audit import (
    MOMENTUM_CANDIDATE_AUDIT_VERSION,
    MomentumCandidateAuditConfig,
    build_momentum_candidate_audit,
    candidate_churn_rows,
    candidate_state_age_rows,
    candidate_streak_rows,
    candidate_transition_rows,
    daily_distribution_rows,
    emerging_to_confirmed_progression,
    row_key_set,
    scenario_stability_status,
    sensitivity_scenarios,
    symbol_frequency_rows,
    transition_matrix_rows,
    write_momentum_candidate_audit_markdown,
)


def test_trading_session_streak_and_weekend_gap_handling():
    rows = [
        candidate_row("AAA", "2024-01-05", "EMERGING"),
        candidate_row("AAA", "2024-01-08", "CONFIRMED"),
        candidate_row("AAA", "2024-01-09", "REJECTED"),
        candidate_row("AAA", "2024-01-10", "EMERGING"),
    ]
    session_index = {"2024-01-05": 0, "2024-01-08": 1, "2024-01-09": 2, "2024-01-10": 3}

    streaks = candidate_streak_rows(rows, session_index)
    any_streaks = [row for row in streaks if row["streak_type"] == "ANY_CANDIDATE_STREAK"]

    assert any_streaks[0]["trading_sessions"] == 2
    assert any_streaks[0]["start_date"] == "2024-01-05"
    assert any_streaks[0]["end_date"] == "2024-01-08"
    assert any_streaks[1]["trading_sessions"] == 1


def test_candidate_state_transitions_and_matrix():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING"),
        candidate_row("AAA", "2024-01-02", "CONFIRMED"),
        candidate_row("AAA", "2024-01-03", "REJECTED"),
        candidate_row("BBB", "2024-01-01", "REJECTED"),
        candidate_row("BBB", "2024-01-02", "EMERGING"),
    ]
    session_index = {"2024-01-01": 0, "2024-01-02": 1, "2024-01-03": 2}

    transitions = candidate_transition_rows(rows, session_index)
    matrix = transition_matrix_rows(transitions)

    assert any(row["from_state"] == "EMERGING" and row["to_state"] == "CONFIRMED" and row["count"] == 1 for row in matrix)
    assert any(row["from_state"] == "CONFIRMED" and row["to_state"] == "REJECTED" and row["count"] == 1 for row in matrix)
    assert any(row["from_state"] == "REJECTED" and row["to_state"] == "EMERGING" and row["count"] == 1 for row in matrix)


def test_emerging_to_confirmed_conversion_and_both_eligible_handling():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", emerging=True),
        candidate_row("AAA", "2024-01-02", "REJECTED"),
        candidate_row("AAA", "2024-01-03", "CONFIRMED", confirmed=True),
        candidate_row("BBB", "2024-01-01", "CONFIRMED", emerging=True, confirmed=True, both=True),
        candidate_row("BBB", "2024-01-02", "CONFIRMED", confirmed=True),
    ]
    session_index = {"2024-01-01": 0, "2024-01-02": 1, "2024-01-03": 2}

    progression = emerging_to_confirmed_progression(rows, session_index)

    assert progression["already_both_eligible_events"] == 1
    assert progression["later_conversion_pool"] == 1
    assert progression["conversions"]["within_1_sessions"]["converted"] == 0
    assert progression["conversions"]["within_2_sessions"]["converted"] == 1


def test_frequency_churn_daily_distribution_and_state_age():
    rows_by_date = {
        "2024-01-01": [candidate_row("AAA", "2024-01-01", "EMERGING"), candidate_row("BBB", "2024-01-01", "REJECTED")],
        "2024-01-02": [candidate_row("AAA", "2024-01-02", "CONFIRMED"), candidate_row("BBB", "2024-01-02", "EMERGING")],
        "2024-01-03": [candidate_row("AAA", "2024-01-03", "REJECTED"), candidate_row("BBB", "2024-01-03", "EMERGING")],
    }
    rows = [row for group in rows_by_date.values() for row in group]
    session_index = {"2024-01-01": 0, "2024-01-02": 1, "2024-01-03": 2}
    streaks = candidate_streak_rows(rows, session_index)

    daily = daily_distribution_rows(rows_by_date)
    frequency = symbol_frequency_rows(rows, streaks)
    churn = candidate_churn_rows(rows_by_date)
    ages = candidate_state_age_rows(rows, session_index)

    assert daily[0]["total_candidate_count"] == 1
    assert daily[1]["emerging_primary_count"] == 1
    assert frequency[0]["symbol"] == "BBB"
    assert churn[1]["new_candidates_today"] == 1
    assert any(row["symbol"] == "AAA" and row["any_candidate_state_age"] == 2 for row in ages)


def test_sensitivity_config_isolation_and_thresholds():
    baseline = MomentumCandidateConfig()
    scenarios = {scenario.name: scenario for scenario in sensitivity_scenarios(baseline)}

    assert scenarios["RVOL_EMERGING_1_30"].config.relative_volume.emerging_threshold == Decimal("1.30")
    assert baseline.relative_volume.emerging_threshold == Decimal("1.20")
    assert scenarios["LIQUIDITY_5CR"].config.liquidity.median_traded_value_20d_min == Decimal("50000000")
    assert scenarios["HIGH_PROXIMITY_TIGHTER"].config.breakout.approaching_20d_high_distance == Decimal("-0.030")


def test_overlap_jaccard_and_stability_status():
    baseline_rows = [candidate_row("AAA", "2024-01-01", "EMERGING"), candidate_row("BBB", "2024-01-01", "CONFIRMED")]
    changed_rows = [candidate_row("AAA", "2024-01-01", "EMERGING"), candidate_row("CCC", "2024-01-01", "EMERGING")]

    baseline_keys = row_key_set(baseline_rows, candidate_only=True)
    changed_keys = row_key_set(changed_rows, candidate_only=True)

    assert len(baseline_keys & changed_keys) == 1
    assert len(baseline_keys | changed_keys) == 3
    assert scenario_stability_status(
        baseline_count=100,
        scenario_count=92,
        jaccard=Decimal("0.90"),
        baseline_daily_counts=[10, 12, 14],
        scenario_daily_counts=[9, 11, 13],
    ) == "STABLE"
    assert scenario_stability_status(
        baseline_count=100,
        scenario_count=50,
        jaccard=Decimal("0.40"),
        baseline_daily_counts=[10, 12, 14],
        scenario_daily_counts=[2, 4, 6],
    ) == "HIGHLY_SENSITIVE"


def test_full_audit_generation_no_future_outcomes_and_no_baseline_mutation(tmp_path):
    data_dir = tmp_path / "data"
    candidate_rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", return_5d="0.03", relative_volume_20d="1.25"),
        candidate_row("AAA", "2024-01-02", "CONFIRMED", return_5d="0.05", relative_volume_20d="1.70", confirmed=True, both=True),
        candidate_row("AAA", "2024-01-03", "REJECTED", return_5d="-0.01", relative_volume_20d="0.80", emerging=False),
        candidate_row("BBB", "2024-01-01", "REJECTED", return_5d="-0.02", relative_volume_20d="0.70", emerging=False),
        candidate_row("BBB", "2024-01-02", "EMERGING", return_5d="0.04", relative_volume_20d="1.30"),
        candidate_row("BBB", "2024-01-03", "UNAVAILABLE", return_5d="", relative_volume_20d="", emerging=False, mandatory=False),
    ]
    feature_rows = [feature_row_from_candidate(row) for row in candidate_rows]
    write_candidate_dataset(data_dir, candidate_rows)
    write_feature_dataset(data_dir, feature_rows)
    baseline_hash = (data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz").read_bytes()

    report = build_momentum_candidate_audit(
        config=MomentumCandidateAuditConfig(data_dir=data_dir, start_date=date(2024, 1, 1), end_date=date(2024, 1, 3))
    )
    write_momentum_candidate_audit_markdown(report, tmp_path / "docs" / "momentum-candidate-audit.md")

    assert report["audit"]["audit_version"] == MOMENTUM_CANDIDATE_AUDIT_VERSION
    assert report["baseline"]["candidate_dataset_unchanged"] is True
    assert report["baseline"]["feature_dataset_unchanged"] is True
    assert report["safety"]["future_outcome_fields_used"] == 0
    assert report["safety"]["orders_placed"] == 0
    assert (data_dir / "reports" / "momentum_candidate_audit_summary.json").exists()
    assert (data_dir / "research" / "audits" / "momentum_candidates" / "v1" / "candidate_streaks.csv.gz").exists()
    assert (data_dir / "research" / "audits" / "momentum_candidates" / "v1" / "candidate_sensitivity_scenarios.csv.gz").exists()
    assert (data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz").read_bytes() == baseline_hash
    assert json.loads((data_dir / "reports" / "momentum_candidate_audit_summary.json").read_text(encoding="utf-8"))["ready_for_review"] is True


def candidate_row(
    symbol,
    trading_date,
    state,
    *,
    emerging=None,
    confirmed=None,
    both=False,
    mandatory=True,
    return_5d="0.03",
    relative_volume_20d="1.35",
):
    if emerging is None:
        emerging = state == "EMERGING" or both
    if confirmed is None:
        confirmed = state == "CONFIRMED"
    return {
        "trading_date": trading_date,
        "symbol": symbol,
        "isin": f"INE{symbol}",
        "universe_name": "NIFTY_500",
        "membership_status": "PARTIAL_HISTORY",
        "membership_confidence": "OFFICIAL_EVENTS_PARTIAL",
        "universe_version": "fixture",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "candidate_config_hash": "fixture-hash",
        "benchmark_context_version": "BENCHMARK_CONTEXT_V1",
        "sector_context_version": "SECTOR_CONTEXT_V1",
        "adjustment_methodology": "PRICE_ADJUSTED_STRUCTURAL_V1",
        "exclusion_policy": "CORPORATE_ACTION_EXCLUSIONS_V1",
        "availability_time": "EOD",
        "decision_input_time": "NEXT_SESSION_DECISION_INPUT",
        "timeframe": "DAILY_EOD",
        "research_eligible": str(mandatory),
        "eligibility_status": "RESEARCH_ELIGIBLE" if mandatory else "INSUFFICIENT_HISTORY",
        "mandatory_gates_passed": str(mandatory),
        "rejection_reasons": "" if state in {"EMERGING", "CONFIRMED"} else "LOW_MULTI_DAY_MOMENTUM",
        "candidate_state": state,
        "emerging_eligible": str(emerging),
        "confirmed_eligible": str(confirmed),
        "both_eligible": str(both),
        "price": "250",
        "price_range_status": "NORMAL_ELIGIBLE_RANGE",
        "cash_equity_status": "EQ",
        "median_traded_value_20d": "150000000",
        "return_1d": "0.01",
        "return_3d": "0.02",
        "return_5d": return_5d,
        "return_10d": "0.04",
        "return_20d": "0.06",
        "relative_volume_5d": "1.30",
        "relative_volume_20d": relative_volume_20d,
        "up_days_ratio_10": "0.60",
        "up_days_ratio_20": "0.55",
        "relative_return_5d_vs_nifty500": "0.01",
        "relative_return_20d_vs_nifty500": "0.02",
        "prior_high_20d": "255",
        "distance_to_prior_20d_high_pct": "-0.005",
        "above_prior_20d_high": "False",
        "intraday_high_above_prior_20d_high": "True",
        "atr_percent_14": "0.02",
        "extension_status": "NORMAL",
        "breakout_context": "TESTING_20D_HIGH",
        "volatility_context": "NORMAL",
        "sector_context_status": "UNAVAILABLE",
        "candidate_evidence_count": "5",
        "candidate_strength_descriptor": "DEVELOPING",
        "emerging_evidence": "POSITIVE_3D_MOMENTUM",
        "confirmed_evidence": "",
        "warning_flags": "",
    }


def feature_row_from_candidate(row):
    feature = {
        "trading_date": row["trading_date"],
        "symbol": row["symbol"],
        "isin": row["isin"],
        "universe_name": row["universe_name"],
        "universe_membership_status": row["membership_status"],
        "universe_membership_confidence": row["membership_confidence"],
        "universe_version": row["universe_version"],
        "feature_version": row["feature_version"],
        "benchmark_context_version": row["benchmark_context_version"],
        "sector_context_version": row["sector_context_version"],
        "adjustment_methodology": row["adjustment_methodology"],
        "exclusion_policy": row["exclusion_policy"],
        "availability_time": row["availability_time"],
        "decision_input_time": row["decision_input_time"],
        "timeframe": row["timeframe"],
        "series": "EQ",
        "feature_status": "READY" if row["candidate_state"] != "UNAVAILABLE" else "INSUFFICIENT_HISTORY",
        "feature_null_reasons": "" if row["candidate_state"] != "UNAVAILABLE" else "return_5d:INSUFFICIENT_HISTORY:fixture",
        "distance_from_sma_20_pct": "0.03",
        "above_prior_52w_high": "",
        "sector_mapping_status": "UNAVAILABLE",
    }
    for key in (
        "return_1d",
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "relative_volume_5d",
        "relative_volume_20d",
        "up_days_ratio_10",
        "up_days_ratio_20",
        "median_traded_value_20d",
        "atr_percent_14",
        "relative_return_5d_vs_nifty500",
        "relative_return_20d_vs_nifty500",
        "prior_high_20d",
        "distance_to_prior_20d_high_pct",
        "above_prior_20d_high",
        "intraday_high_above_prior_20d_high",
    ):
        feature[key] = row[key]
    return feature


def write_candidate_dataset(data_dir, rows):
    path = data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_feature_dataset(data_dir, rows):
    path = data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

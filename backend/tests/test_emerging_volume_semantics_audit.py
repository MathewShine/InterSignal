from __future__ import annotations

import csv
import gzip
import json
from datetime import date
from decimal import Decimal

from app.strategy.candidate_config import MomentumCandidateConfig
from app.strategy.emerging_volume_semantics_audit import (
    EMERGING_VOLUME_SEMANTICS_AUDIT_VERSION,
    EmergingVolumeSemanticsAuditConfig,
    actual_emerging_semantics,
    breakout_context_rvol_rows,
    build_emerging_volume_semantics_audit,
    hard_gate_counterfactual_rows,
    hybrid_volume_diagnostic_rows,
    low_rvol_cohort_summary,
    low_rvol_evidence_rows,
    rvol5_rvol20_summary,
    rvol_bucket,
    rvol_distribution_row,
    semantic_consistency_status,
    simulated_emerging_passes,
    write_emerging_volume_semantics_markdown,
)


def test_rvol_bucket_classification():
    assert rvol_bucket(None) == "NULL"
    assert rvol_bucket(Decimal("0.79")) == "LT_0_80"
    assert rvol_bucket(Decimal("0.80")) == "RANGE_0_80_TO_LT_1_00"
    assert rvol_bucket(Decimal("1.00")) == "RANGE_1_00_TO_LT_1_20"
    assert rvol_bucket(Decimal("1.20")) == "RANGE_1_20_TO_LT_1_30"
    assert rvol_bucket(Decimal("1.30")) == "RANGE_1_30_TO_LT_1_50"
    assert rvol_bucket(Decimal("1.50")) == "RANGE_1_50_TO_LT_2_00"
    assert rvol_bucket(Decimal("2.00")) == "GTE_2_00"


def test_emerging_only_vs_both_split_distribution():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", rvol20="0.90", emerging=True, confirmed=False),
        candidate_row("BBB", "2024-01-01", "CONFIRMED", rvol20="1.80", emerging=True, confirmed=True, both=True),
    ]

    emerging_only = rvol_distribution_row("EMERGING_ONLY", [row for row in rows if row["emerging_eligible"] == "True" and row["confirmed_eligible"] == "False"])
    both = rvol_distribution_row("BOTH_ELIGIBLE", [row for row in rows if row["both_eligible"] == "True"])

    assert emerging_only["rvol_0_80_to_lt_1_00"] == 1
    assert both["rvol_1_50_to_lt_2_00"] == 1


def test_rvol5_rvol20_joint_classification():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", rvol5="1.40", rvol20="0.90"),
        candidate_row("BBB", "2024-01-01", "EMERGING", rvol5="0.90", rvol20="1.40"),
        candidate_row("CCC", "2024-01-01", "EMERGING", rvol5="1.40", rvol20="1.40"),
        candidate_row("DDD", "2024-01-01", "EMERGING", rvol5="0.90", rvol20="0.90"),
    ]

    summary = rvol5_rvol20_summary(rows)["threshold_1_20"]

    assert summary["rvol5_high_rvol20_low"] == 1
    assert summary["rvol5_low_rvol20_high"] == 1
    assert summary["both_high"] == 1
    assert summary["both_low"] == 1


def test_low_rvol_cohort_aggregation_and_evidence_combinations():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", rvol20="0.90", evidence="CURRENT_DAY_CONFIRMATION;HEALTHY_UP_DAY_RATIO;IMPROVING_10D_STRUCTURE;POSITIVE_3D_MOMENTUM"),
        candidate_row("BBB", "2024-01-01", "EMERGING", rvol20="1.10", evidence="CURRENT_DAY_CONFIRMATION;HEALTHY_UP_DAY_RATIO;IMPROVING_10D_STRUCTURE;POSITIVE_5D_MOMENTUM"),
        candidate_row("CCC", "2024-01-01", "EMERGING", rvol20="1.30", evidence="EMERGING_RELATIVE_VOLUME;HEALTHY_UP_DAY_RATIO;IMPROVING_10D_STRUCTURE;POSITIVE_5D_MOMENTUM"),
    ]

    cohorts = low_rvol_cohort_summary(rows)
    evidence_rows, summary = low_rvol_evidence_rows(rows[:2], total_emerging=len(rows), config=MomentumCandidateConfig())

    assert cohorts["LOW_RVOL"]["count"] == 1
    assert cohorts["SUB_THRESHOLD"]["count"] == 1
    assert any(row["section"] == "EVIDENCE_COMBINATION" for row in evidence_rows)
    assert summary["stored_evidence_count_distribution"]["4"] == 2


def test_breakout_grouping_hard_gate_and_hybrid_diagnostics():
    rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", rvol20="0.90", breakout="APPROACHING_20D_HIGH"),
        candidate_row("AAA", "2024-01-02", "CONFIRMED", rvol20="1.70", confirmed=True, both=True),
        candidate_row("BBB", "2024-01-01", "EMERGING", rvol5="1.40", rvol20="0.90", breakout="TESTING_20D_HIGH"),
        candidate_row("CCC", "2024-01-01", "EMERGING", rvol5="0.80", rvol20="1.30", breakout="ABOVE_20D_HIGH"),
    ]
    primary_emerging = [row for row in rows if row["candidate_state"] == "EMERGING"]
    sessions = ["2024-01-01", "2024-01-02"]
    session_index = {"2024-01-01": 0, "2024-01-02": 1}

    breakout = breakout_context_rvol_rows(primary_emerging)
    hard_gate = hard_gate_counterfactual_rows(primary_emerging, rows, sessions, session_index)
    hybrid = hybrid_volume_diagnostic_rows(primary_emerging, sessions, session_index, rows)

    assert any(row["breakout_context"] == "APPROACHING_20D_HIGH" for row in breakout)
    assert next(row for row in hard_gate if row["threshold"] == "1.20")["emerging_rows_retained"] == 1
    assert next(row for row in hybrid if row["scenario"] == "HYBRID_RVOL20_1_20_OR_RVOL5_1_30")["emerging_rows_retained"] == 2


def test_semantic_status_threshold_simulation_and_hash_stability():
    config = MomentumCandidateConfig()
    row = candidate_row(
        "AAA",
        "2024-01-01",
        "EMERGING",
        rvol20="1.22",
        evidence="CURRENT_DAY_CONFIRMATION;EMERGING_RELATIVE_VOLUME;HEALTHY_UP_DAY_RATIO;IMPROVING_10D_STRUCTURE",
    )
    distribution = rvol_distribution_row("ALL_EMERGING_ELIGIBLE", [candidate_row("BBB", "2024-01-01", "EMERGING", rvol20="0.90") for _ in range(2)] + [row])

    assert actual_emerging_semantics(config)["classification"] == "ONE_OF_N_SUPPORTING_EVIDENCE"
    assert simulated_emerging_passes(row, threshold=Decimal("1.30"), config=config) is False
    assert config.config_hash() == "d111957c7a24da96"
    status = semantic_consistency_status(
        semantics=actual_emerging_semantics(config),
        distribution=distribution,
        sensitivity=[{"removed_pct": "0.1"}, {"removed_pct": "0.2"}],
    )
    assert status["status"] == "CONSISTENT_BUT_LOOSE"


def test_full_report_generation_no_outcomes_and_no_baseline_mutation(tmp_path):
    data_dir = tmp_path / "data"
    candidate_rows = [
        candidate_row("AAA", "2024-01-01", "EMERGING", rvol20="0.90"),
        candidate_row("AAA", "2024-01-02", "CONFIRMED", rvol20="1.80", confirmed=True, both=True),
        candidate_row("BBB", "2024-01-01", "EMERGING", rvol5="1.50", rvol20="0.95"),
        candidate_row("BBB", "2024-01-02", "REJECTED", emerging=False, rvol20="0.70"),
        candidate_row("CCC", "2024-01-01", "EMERGING", rvol20="1.30"),
        candidate_row("CCC", "2024-01-02", "UNAVAILABLE", emerging=False, mandatory=False, rvol20=""),
    ]
    write_candidate_dataset(data_dir, candidate_rows)
    write_feature_dataset(data_dir, [{"trading_date": row["trading_date"], "symbol": row["symbol"]} for row in candidate_rows])
    baseline_bytes = (data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz").read_bytes()

    report = build_emerging_volume_semantics_audit(
        config=EmergingVolumeSemanticsAuditConfig(data_dir=data_dir, start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))
    )
    write_emerging_volume_semantics_markdown(report, tmp_path / "docs" / "emerging-volume-semantics-audit.md")

    assert report["audit"]["audit_version"] == EMERGING_VOLUME_SEMANTICS_AUDIT_VERSION
    assert report["baseline"]["candidate_dataset_unchanged"] is True
    assert report["baseline"]["feature_dataset_unchanged"] is True
    assert report["safety"]["future_outcome_fields_used"] == 0
    assert report["safety"]["orders_placed"] == 0
    assert report["ready_for_review"] is True
    assert (data_dir / "reports" / "emerging_volume_semantics_summary.json").exists()
    assert (data_dir / "reports" / "emerging_rvol_counterfactual_gates.csv").exists()
    assert (data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz").read_bytes() == baseline_bytes
    assert json.loads((data_dir / "reports" / "emerging_volume_semantics_summary.json").read_text(encoding="utf-8"))["ready_for_review"] is True


def candidate_row(
    symbol,
    trading_date,
    state,
    *,
    emerging=True,
    confirmed=False,
    both=False,
    mandatory=True,
    rvol5="1.10",
    rvol20="0.95",
    return_5d="0.03",
    breakout="TESTING_20D_HIGH",
    evidence="CURRENT_DAY_CONFIRMATION;HEALTHY_UP_DAY_RATIO;IMPROVING_10D_STRUCTURE;POSITIVE_3D_MOMENTUM;POSITIVE_5D_BENCHMARK_RELATIVE_STRENGTH",
):
    if state == "CONFIRMED":
        confirmed = True
    return {
        "trading_date": trading_date,
        "symbol": symbol,
        "candidate_state": state,
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "candidate_config_hash": "d111957c7a24da96",
        "feature_version": "DAILY_FEATURES_V1",
        "mandatory_gates_passed": str(mandatory),
        "emerging_eligible": str(emerging),
        "confirmed_eligible": str(confirmed),
        "both_eligible": str(both),
        "relative_volume_5d": rvol5,
        "relative_volume_20d": rvol20,
        "return_1d": "0.01",
        "return_3d": "0.02",
        "return_5d": return_5d,
        "return_10d": "0.04",
        "return_20d": "0.06",
        "up_days_ratio_10": "0.60",
        "up_days_ratio_20": "0.55",
        "relative_return_5d_vs_nifty500": "0.01",
        "relative_return_20d_vs_nifty500": "0.02",
        "distance_to_prior_20d_high_pct": "-0.005",
        "above_prior_20d_high": "False",
        "intraday_high_above_prior_20d_high": "True",
        "atr_percent_14": "0.02",
        "median_traded_value_20d": "150000000",
        "extension_status": "NORMAL",
        "breakout_context": breakout,
        "candidate_evidence_count": str(len([item for item in evidence.split(";") if item])),
        "emerging_evidence": evidence,
        "confirmed_evidence": "CONFIRMED_RELATIVE_VOLUME" if confirmed else "",
    }


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

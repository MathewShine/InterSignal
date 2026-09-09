from __future__ import annotations

import csv
import gzip
from pathlib import Path

from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig
from app.strategy.entry_evaluation_audit import (
    ENTRY_EVALUATION_AUDIT_VERSION,
    EntryEvaluationAuditConfig,
    build_entry_evaluation_audit,
    cohort_funnel,
    conditional_ready_distribution,
    daily_ready_density,
    exceptional_long_audit,
    funnel_sanity_result,
    full_funnel_summary,
    neutral_rule_combinations,
    penalty_consistency_result,
    penalty_invariants,
    readiness_transitions_and_churn,
    regime_selectivity,
    sensitivity_scenarios,
    watch_reason_distribution,
    write_entry_evaluation_audit_markdown,
)
from app.strategy.entry_evaluator import ENTRY_OUTPUT_FIELDS, evaluate_entry_rows
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig

CANDIDATE_HASH = MomentumCandidateConfig().config_hash()
SETUP_HASH = DailySetupEvaluationConfig().config_hash()
REGIME_HASH = MarketRegimeConfig().config_hash()


def test_cohort_denominators_and_candidate_state_cross_tab() -> None:
    rows = audit_rows()
    _, summary = cohort_funnel(rows)

    assert summary["cohorts"]["EMERGING_ONLY"]["candidate_rows"] >= 2
    assert summary["cohorts"]["CONFIRMED_ONLY"]["candidate_rows"] >= 2
    assert summary["cohorts"]["BOTH_ELIGIBLE"]["candidate_rows"] >= 1
    assert summary["candidate_state_by_cohort"]["CONFIRMED|BOTH_ELIGIBLE"]["candidate_rows"] >= 1
    assert summary["candidate_state_by_cohort"]["EMERGING|EMERGING_ONLY"]["candidate_rows"] >= 1


def test_funnel_regime_selectivity_and_neutral_stricter_semantics() -> None:
    rows = audit_rows()
    funnel = full_funnel_summary(rows)
    _, regime = regime_selectivity(rows)
    _, neutral = neutral_rule_combinations(rows)

    assert funnel["candidate_rows"] == len(rows)
    assert funnel["setup_eligible_rows"] < funnel["candidate_rows"]
    assert funnel["progressed_to_entry_context"] >= 1
    assert regime["setup_eligible_progression"]["BULLISH"]["setup_to_progressed_pct"] != "0.0000"
    assert regime["setup_eligible_progression"]["BEARISH"]["ready_for_risk_rows"] == 0
    assert regime["setup_eligible_progression"]["BEARISH"]["exceptional_rows"] == 1
    assert neutral["is_meaningfully_stricter_than_bullish"] is True
    assert neutral["top_combinations"]["CONDITIONALLY_READY"]


def test_exceptional_long_selectivity_and_criteria_profile() -> None:
    rows = audit_rows()
    csv_rows, summary, inventory = exceptional_long_audit(rows, EntryEvaluationAuditConfig(data_dir=Path("unused")).entry_config)

    assert summary["exceptional_review_ready_rows"] == 1
    assert summary["rate_vs_bearish_setup_eligible_pct"] != "100.0000"
    assert summary["criteria_hit_rate"]["STRONG_SETUP"]["exceptional_hit_rate_pct"] == "100.0000"
    assert summary["pathway_breadth_flag"] == "SELECTIVE"
    assert len(inventory) == 1
    assert any(row["section"] == "CRITERION_HIT_RATE_EXCEPTIONAL" for row in csv_rows)


def test_penalty_gate_invariants_and_inherited_blockers() -> None:
    rows = audit_rows()
    _, summary = penalty_invariants(rows, EntryEvaluationAuditConfig(data_dir=Path("unused")).entry_config)

    assert summary["ready_for_risk_blocking_penalty_rows"] == 0
    assert summary["exceptional_long_blocking_penalty_rows"] == 0
    assert summary["conditionally_ready_blocking_penalty_rows"] == 0
    assert summary["blocking_by_readiness"]["WATCH"] >= 1
    assert summary["gate_readiness_violations"] == 0
    assert penalty_consistency_result(summary) == "CONSISTENT_WITH_INHERITED_BLOCKERS"


def test_watch_conditional_ready_for_risk_evidence_and_density() -> None:
    rows = audit_rows()
    _, watch = watch_reason_distribution(rows)
    _, conditional = conditional_ready_distribution(rows)
    density = daily_ready_density(rows)

    ready_rows = [row for row in rows if row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"]
    assert watch["primary_reasons"]["SETUP_WATCH_ONLY"]["count"] >= 1
    assert conditional["primary_reasons"]["NEUTRAL_STRICT_REQUIREMENTS_NOT_MET"]["count"] >= 1
    assert all(row["setup_eligible"] is True for row in ready_rows)
    assert all(row["risk_reward_status"] == "NOT_EVALUATED" for row in ready_rows)
    assert density["overall"]["max"] >= 1


def test_readiness_streaks_transitions_churn_and_sensitivity() -> None:
    rows = audit_rows()
    _, transition_summary = readiness_transitions_and_churn(rows)
    sensitivity_rows, sensitivity = sensitivity_scenarios(rows)

    assert transition_summary["streaks"]["READY_FOR_RISK"]["max"] >= 2
    assert transition_summary["total_next_session_transitions"] >= 1
    assert transition_summary["daily_churn"]["churn_pct_distribution"]["max"] != "0.0000"
    assert {row["scenario"] for row in sensitivity_rows} >= {
        "BASELINE",
        "NEUTRAL_STRICTER",
        "EXCEPTIONAL_LONG_LOOSER",
        "HIGH_EXTENSION_BLOCK",
        "FALSE_BREAKOUT_STRICT",
    }
    assert sensitivity["BASELINE"]["jaccard"] == "1.0000"


def test_report_generation_baseline_immutability_and_no_outcomes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    rows = audit_rows()
    write_entry_rows(data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz", rows)
    write_gzip_rows(data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz", [{"trading_date": "2024-01-01", "symbol": "AAA"}])
    write_gzip_rows(data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz", [{"trading_date": "2024-01-01", "symbol": "AAA"}])
    write_gzip_rows(data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz", [{"trading_date": "2024-01-01", "symbol": "AAA"}])
    write_gzip_rows(data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz", [{"trading_date": "2024-01-01", "regime_state": "BULLISH"}])

    report = build_entry_evaluation_audit(config=EntryEvaluationAuditConfig(data_dir=data_dir))
    markdown_path = tmp_path / "docs" / "strategy-v1-entry-evaluation-audit.md"
    write_entry_evaluation_audit_markdown(report, markdown_path)

    assert report["audit_version"] == ENTRY_EVALUATION_AUDIT_VERSION
    assert report["ready_for_review"] is True
    assert all(report["baseline_unchanged"].values())
    assert report["safety"]["future_return_fields_used"] == 0
    assert report["safety"]["audit_outcome_field_scan"] == []
    assert report["safety"]["orders_placed"] == 0
    assert funnel_sanity_result(report["funnel"], 0) in {"HEALTHY", "HEALTHY_BUT_HIGH_PASS_THROUGH", "TOO_RESTRICTIVE"}
    assert (data_dir / "reports" / "entry_evaluation_audit_summary.json").exists()
    assert (data_dir / "reports" / "entry_evaluation_cohort_funnel.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_penalty_invariants.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_exceptional_long_audit.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_regime_selectivity.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_readiness_transitions.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_sensitivity.csv").exists()
    assert (data_dir / "research" / "audits" / "entry_evaluation" / "v1" / "exceptional_long_inventory.csv").exists()
    assert markdown_path.exists()


def audit_rows() -> list[dict[str, object]]:
    setup_rows = [
        base_setup(symbol="AAA", trading_date="2024-01-01"),
        base_setup(
            symbol="BBB",
            trading_date="2024-01-01",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="VALID",
            volume_confirmation="GOOD",
            benchmark_rs_context="POSITIVE",
            consolidation_quality="GOOD",
        ),
        base_setup(symbol="AAA", trading_date="2024-01-02"),
        base_setup(symbol="CCC", trading_date="2024-01-02"),
        base_setup(
            symbol="DDD",
            trading_date="2024-01-02",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="VALID",
            volume_confirmation="GOOD",
            benchmark_rs_context="NEUTRAL",
            consolidation_quality="GOOD",
        ),
        base_setup(
            symbol="EEE",
            trading_date="2024-01-03",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="VALID",
            volume_confirmation="GOOD",
            benchmark_rs_context="POSITIVE",
            consolidation_quality="GOOD",
        ),
        *[
            base_setup(
                symbol=f"BR{i}",
                trading_date="2024-01-03",
                candidate_state="EMERGING",
                emerging_eligible="True",
                confirmed_eligible="False",
                both_eligible="False",
                setup_quality="VALID",
                volume_confirmation="GOOD",
                benchmark_rs_context="POSITIVE",
                consolidation_quality="GOOD",
            )
            for i in range(9)
        ],
        base_setup(
            symbol="FFF",
            trading_date="2024-01-03",
            emerging_eligible="True",
            confirmed_eligible="True",
            both_eligible="True",
        ),
        base_setup(symbol="GGG", trading_date="2024-01-05"),
        base_setup(
            symbol="HHH",
            trading_date="2024-01-03",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="WATCH",
            setup_eligible="False",
            setup_rejection_reasons="SETUP_WATCH_ONLY",
            volume_confirmation="NORMAL",
            benchmark_rs_context="NEUTRAL",
        ),
        base_setup(symbol="III", trading_date="2024-01-04", extension_risk="HIGH"),
        base_setup(symbol="JJJ", trading_date="2024-01-04", false_breakout_flags="POSSIBLE_FALSE_BREAKOUT"),
    ]
    candidate_lookup = {(str(row["trading_date"]), str(row["symbol"])): base_candidate_from_setup(row) for row in setup_rows}
    regime_lookup = {
        "2024-01-01": base_regime("2024-01-01", "BULLISH"),
        "2024-01-02": base_regime("2024-01-02", "NEUTRAL"),
        "2024-01-03": base_regime("2024-01-03", "BEARISH"),
        "2024-01-04": base_regime("2024-01-04", "BULLISH", confidence_state="LOW", available_weight_pct="50"),
        "2024-01-05": base_regime("2024-01-05", "UNAVAILABLE", confidence_state="LOW", available_weight_pct="40"),
    }
    rows = evaluate_entry_rows(
        setup_rows=setup_rows,
        candidate_lookup=candidate_lookup,
        regime_lookup=regime_lookup,
    )
    for row in rows:
        row.pop("_entry_rank_metric", None)
    return rows


def base_setup(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-01",
        "symbol": "AAA",
        "isin": "INE000000001",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "setup_version": DAILY_SETUP_EVALUATION_VERSION,
        "setup_config_hash": SETUP_HASH,
        "research_status": "READY",
        "setup_status": "SETUP_ELIGIBLE",
        "setup_availability": "EOD",
        "decision_input_time": "NEXT_SESSION_DECISION_INPUT",
        "setup_eligible": "True",
        "setup_rejection_reasons": "",
        "candidate_state": "CONFIRMED",
        "emerging_eligible": "False",
        "confirmed_eligible": "True",
        "both_eligible": "False",
        "candidate_rank": "1",
        "candidate_percentile": "99.0",
        "setup_quality": "STRONG",
        "setup_type_flags": "BREAKOUT_20D;MOMENTUM_CONTINUATION",
        "breakout_state": "CLOSE_ACCEPTED",
        "consolidation_state": "TIGHT",
        "consolidation_quality": "STRONG",
        "acceptance_state": "CLOSE_ACCEPTED",
        "candle_quality": "STRONG",
        "volume_confirmation": "STRONG",
        "benchmark_rs_context": "STRONG",
        "extension_risk": "LOW",
        "overhead_resistance": "LOW",
        "false_breakout_flags": "",
        "daily_level_reclaim": "True",
        "warning_flags": "MEMBERSHIP_UNCERTAIN",
    }
    row.update(overrides)
    return row


def base_candidate_from_setup(setup_row: dict[str, object]) -> dict[str, object]:
    return {
        "trading_date": setup_row["trading_date"],
        "symbol": setup_row["symbol"],
        "isin": setup_row["isin"],
        "membership_status": "ACTIVE",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "research_eligible": "True",
        "mandatory_gates_passed": "True",
        "rejection_reasons": "",
        "candidate_state": setup_row["candidate_state"],
        "emerging_eligible": setup_row["emerging_eligible"],
        "confirmed_eligible": setup_row["confirmed_eligible"],
        "both_eligible": setup_row["both_eligible"],
        "candidate_strength_descriptor": "STRONG",
        "warning_flags": setup_row.get("warning_flags", ""),
    }


def base_regime(trading_date: str, state: str, **overrides: object) -> dict[str, object]:
    score_by_state = {"BULLISH": "40", "NEUTRAL": "0", "BEARISH": "-40", "UNAVAILABLE": ""}
    row: dict[str, object] = {
        "trading_date": trading_date,
        "regime_version": MARKET_REGIME_VERSION,
        "config_hash": REGIME_HASH,
        "regime_state": state,
        "regime_score_normalized": score_by_state[state],
        "confidence_score": "80",
        "confidence_state": "HIGH",
        "available_weight_pct": "90",
    }
    row.update(overrides)
    return row


def write_entry_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ENTRY_OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

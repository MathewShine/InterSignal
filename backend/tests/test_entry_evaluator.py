from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig
from app.strategy.entry_config import ENTRY_EVALUATION_VERSION, EntryEvaluationConfig
from app.strategy.entry_evaluator import (
    ENTRY_OUTPUT_FIELDS,
    EntryEvaluationEngineConfig,
    build_entry_evaluations,
    evaluate_entry_row,
    evaluate_entry_rows,
    exceptional_long_candidate,
    prohibited_outcome_fields,
    write_strategy_v1_entry_evaluation_markdown,
)
from app.strategy.entry_gates import neutral_strict_requirements_met, regime_permission
from app.strategy.entry_penalties import build_entry_penalties
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig

CANDIDATE_HASH = MomentumCandidateConfig().config_hash()
SETUP_HASH = DailySetupEvaluationConfig().config_hash()
REGIME_HASH = MarketRegimeConfig().config_hash()


def test_entry_row_preserves_versions_hashes_gates_and_placeholders() -> None:
    config = EntryEvaluationConfig()
    row = evaluate_entry_row(
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        regime_row=base_regime("2024-01-02", "BULLISH"),
        config=config,
    )

    assert row["feature_version"] == "DAILY_FEATURES_V1"
    assert row["candidate_version"] == MOMENTUM_CANDIDATES_VERSION
    assert row["candidate_config_hash"] == CANDIDATE_HASH
    assert row["setup_version"] == DAILY_SETUP_EVALUATION_VERSION
    assert row["setup_config_hash"] == SETUP_HASH
    assert row["regime_version"] == MARKET_REGIME_VERSION
    assert row["regime_config_hash"] == REGIME_HASH
    assert row["entry_version"] == ENTRY_EVALUATION_VERSION
    assert row["entry_config_hash"] == config.config_hash()
    assert row["entry_availability"] == "EOD"
    assert row["decision_use"] == "NEXT_SESSION_ENTRY_RESEARCH"
    assert row["regime_permission"] == "NORMAL_LONG_ALLOWED"
    assert row["entry_evaluation_status"] == "READY"
    assert row["entry_readiness"] == "READY_FOR_RISK_EVALUATION"
    assert row["stock_sector_rs_status"] == "UNAVAILABLE"
    assert row["catalyst_context_status"] == "UNAVAILABLE"
    assert row["risk_reward_status"] == "NOT_EVALUATED"
    assert row["score_architecture_status"] == "NOT_IMPLEMENTED"
    assert prohibited_outcome_fields(ENTRY_OUTPUT_FIELDS) == []

    gate_details = json.loads(row["gate_details"])
    assert set(gate_details) == {"research", "candidate", "setup", "regime", "extension", "technical_rejection"}
    for gate in gate_details.values():
        assert {"gate_name", "gate_status", "passed", "reason_codes", "evidence"} <= set(gate)


def test_regime_permission_and_readiness_paths_are_deterministic() -> None:
    config = EntryEvaluationConfig()

    bullish = evaluate_entry_row(
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        regime_row=base_regime("2024-01-02", "BULLISH"),
        config=config,
    )
    assert bullish["regime_permission"] == "NORMAL_LONG_ALLOWED"
    assert bullish["entry_readiness"] == "READY_FOR_RISK_EVALUATION"

    neutral_ready = evaluate_entry_row(
        candidate_row=base_candidate(symbol="NEUTRALOK", trading_date="2024-01-03"),
        setup_row=base_setup(symbol="NEUTRALOK", trading_date="2024-01-03"),
        regime_row=base_regime("2024-01-03", "NEUTRAL"),
        config=config,
    )
    assert neutral_ready["regime_permission"] == "STRICT_LONG_ONLY"
    assert neutral_ready["entry_readiness"] == "READY_FOR_RISK_EVALUATION"

    neutral_strict_miss = base_setup(
        symbol="NEUTRALWEAK",
        trading_date="2024-01-03",
        candidate_state="EMERGING",
        emerging_eligible="True",
        confirmed_eligible="False",
        benchmark_rs_context="NEUTRAL",
        setup_quality="VALID",
        volume_confirmation="GOOD",
    )
    neutral_penalties = build_entry_penalties(
        setup_row=neutral_strict_miss,
        regime_row=base_regime("2024-01-03", "NEUTRAL"),
        config=config,
    )
    assert neutral_strict_requirements_met(neutral_strict_miss, neutral_penalties, config) is False
    neutral_conditional = evaluate_entry_row(
        candidate_row=base_candidate_from_setup(neutral_strict_miss),
        setup_row=neutral_strict_miss,
        regime_row=base_regime("2024-01-03", "NEUTRAL"),
        config=config,
    )
    assert neutral_conditional["entry_readiness"] == "CONDITIONALLY_READY"
    assert "NEUTRAL_STRICT_REQUIREMENTS_NOT_MET" in neutral_conditional["warning_evidence"]

    bearish_normal = base_setup(
        symbol="BEARNORMAL",
        trading_date="2024-01-04",
        candidate_state="EMERGING",
        emerging_eligible="True",
        confirmed_eligible="False",
        both_eligible="False",
        setup_quality="VALID",
        volume_confirmation="GOOD",
        benchmark_rs_context="POSITIVE",
    )
    bearish = evaluate_entry_row(
        candidate_row=base_candidate_from_setup(bearish_normal),
        setup_row=bearish_normal,
        regime_row=base_regime("2024-01-04", "BEARISH"),
        config=config,
    )
    assert bearish["regime_permission"] == "EXCEPTIONAL_LONG_ONLY"
    assert bearish["entry_readiness"] == "NOT_READY"
    assert "BEARISH_NORMAL_LONG_BLOCKED" in bearish["blocking_evidence"]

    unavailable = evaluate_entry_row(
        candidate_row=base_candidate(symbol="REGNA", trading_date="2024-01-05"),
        setup_row=base_setup(symbol="REGNA", trading_date="2024-01-05"),
        regime_row=base_regime("2024-01-05", "UNAVAILABLE", confidence_state="LOW", available_weight_pct="40"),
        config=config,
    )
    assert unavailable["regime_permission"] == "INSUFFICIENT_REGIME_CONTEXT"
    assert unavailable["entry_readiness"] == "CONDITIONALLY_READY"
    assert unavailable["entry_readiness"] != "READY_FOR_RISK_EVALUATION"
    assert "REGIME_UNAVAILABLE" in unavailable["warning_evidence"]
    assert regime_permission(regime_state="BULLISH", config=config) == "NORMAL_LONG_ALLOWED"


def test_exceptional_long_extension_false_breakout_and_confidence_penalties() -> None:
    config = EntryEvaluationConfig()
    bearish_setup = base_setup(symbol="EXCEPT", trading_date="2024-01-04")
    is_exceptional, reasons = exceptional_long_candidate(bearish_setup, config)
    assert is_exceptional is True
    assert {
        "STRONG_SETUP",
        "CONFIRMED_OR_BOTH_ELIGIBLE",
        "STRONG_BENCHMARK_RS",
        "STRONG_OR_EXCEPTIONAL_VOLUME",
        "LOW_OR_MODERATE_EXTENSION",
    } <= set(reasons)

    exceptional = evaluate_entry_row(
        candidate_row=base_candidate_from_setup(bearish_setup),
        setup_row=bearish_setup,
        regime_row=base_regime("2024-01-04", "BEARISH"),
        config=config,
    )
    assert exceptional["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW"
    assert exceptional["exceptional_long_status"] == "EXCEPTIONAL_REVIEW_READY"
    assert "BEARISH_NORMAL_LONG_BLOCKED" not in exceptional["blocking_evidence"]

    high_extension = evaluate_entry_row(
        candidate_row=base_candidate(symbol="HIGHX"),
        setup_row=base_setup(symbol="HIGHX", extension_risk="HIGH"),
        regime_row=base_regime("2024-01-02", "BULLISH"),
        config=config,
    )
    assert high_extension["entry_readiness"] == "READY_FOR_RISK_EVALUATION"
    assert "HIGH_EXTENSION" in high_extension["penalty_codes"]
    assert high_extension["extension_gate_passed"] is True

    extreme_extension = evaluate_entry_row(
        candidate_row=base_candidate(symbol="EXTREMEX"),
        setup_row=base_setup(symbol="EXTREMEX", extension_risk="EXTREME"),
        regime_row=base_regime("2024-01-02", "BULLISH"),
        config=config,
    )
    assert extreme_extension["entry_readiness"] == "NOT_READY"
    assert extreme_extension["extension_gate_passed"] is False
    assert "EXTREME_EXTENSION" in extreme_extension["blocking_evidence"]

    false_break = evaluate_entry_row(
        candidate_row=base_candidate(symbol="FALSEBRK"),
        setup_row=base_setup(symbol="FALSEBRK", false_breakout_flags="POSSIBLE_FALSE_BREAKOUT"),
        regime_row=base_regime("2024-01-02", "BULLISH"),
        config=config,
    )
    assert false_break["entry_readiness"] == "NOT_READY"
    assert false_break["technical_rejection_gate_passed"] is False
    assert "FALSE_BREAKOUT_WARNING" in false_break["penalty_codes"]

    low_confidence = evaluate_entry_row(
        candidate_row=base_candidate(symbol="LOWCONF"),
        setup_row=base_setup(symbol="LOWCONF"),
        regime_row=base_regime("2024-01-02", "BULLISH", confidence_state="LOW", available_weight_pct="55"),
        config=config,
    )
    assert "LIMITED_REGIME_CONFIDENCE" in low_confidence["warning_evidence"]


def test_no_t_plus_one_usage_for_candidate_setup_regime_and_outcome_columns() -> None:
    config = EntryEvaluationConfig()
    t_setup = base_setup(symbol="AAA", trading_date="2024-01-02", future_return_5d="999")
    future_setup = base_setup(
        symbol="AAA",
        trading_date="2024-01-03",
        setup_quality="STRONG",
        volume_confirmation="EXCEPTIONAL",
        regime_score_normalized="999",
        forward_return_10d="999",
    )
    setup_rows = [t_setup, future_setup]
    candidate_lookup = {
        ("2024-01-02", "AAA"): base_candidate_from_setup(t_setup, future_return_5d="999"),
        ("2024-01-03", "AAA"): base_candidate_from_setup(future_setup, candidate_state="CONFIRMED"),
    }
    regime_lookup = {
        "2024-01-02": base_regime("2024-01-02", "BULLISH"),
        "2024-01-03": base_regime("2024-01-03", "BULLISH", regime_score_normalized="99"),
    }
    baseline_t = first_for_date(evaluate_entry_rows(setup_rows=setup_rows, candidate_lookup=candidate_lookup, regime_lookup=regime_lookup, config=config), "2024-01-02")

    candidate_lookup[("2024-01-03", "AAA")] = base_candidate_from_setup(future_setup, candidate_state="REJECTED")
    future_setup["setup_quality"] = "POOR"
    future_setup["setup_eligible"] = "False"
    regime_lookup["2024-01-03"] = base_regime("2024-01-03", "BEARISH", regime_score_normalized="-99")
    mutated_t = first_for_date(evaluate_entry_rows(setup_rows=setup_rows, candidate_lookup=candidate_lookup, regime_lookup=regime_lookup, config=config), "2024-01-02")

    compared_fields = [
        "entry_readiness",
        "entry_evaluation_status",
        "entry_context_rank",
        "entry_context_percentile",
        "regime_state",
        "regime_permission",
        "penalty_codes",
        "positive_evidence",
        "warning_evidence",
        "blocking_evidence",
    ]
    assert {field: baseline_t[field] for field in compared_fields} == {field: mutated_t[field] for field in compared_fields}
    assert not any("future" in field.lower() or "forward" in field.lower() for field in mutated_t)


def test_same_date_entry_ranking_is_unaffected_by_future_dates() -> None:
    config = EntryEvaluationConfig()
    strong = base_setup(symbol="AAA", trading_date="2024-01-02")
    moderate = base_setup(
        symbol="BBB",
        trading_date="2024-01-02",
        candidate_state="EMERGING",
        emerging_eligible="True",
        confirmed_eligible="False",
        both_eligible="False",
        setup_quality="VALID",
        volume_confirmation="GOOD",
        benchmark_rs_context="POSITIVE",
        consolidation_quality="GOOD",
    )
    future = base_setup(symbol="ZZZ", trading_date="2024-01-03", volume_confirmation="EXCEPTIONAL")
    baseline = evaluate_entry_rows(
        setup_rows=[strong, moderate],
        candidate_lookup={("2024-01-02", "AAA"): base_candidate_from_setup(strong), ("2024-01-02", "BBB"): base_candidate_from_setup(moderate)},
        regime_lookup={"2024-01-02": base_regime("2024-01-02", "BULLISH")},
        config=config,
    )
    with_future = evaluate_entry_rows(
        setup_rows=[strong, moderate, future],
        candidate_lookup={
            ("2024-01-02", "AAA"): base_candidate_from_setup(strong),
            ("2024-01-02", "BBB"): base_candidate_from_setup(moderate),
            ("2024-01-03", "ZZZ"): base_candidate_from_setup(future),
        },
        regime_lookup={
            "2024-01-02": base_regime("2024-01-02", "BULLISH"),
            "2024-01-03": base_regime("2024-01-03", "BULLISH", regime_score_normalized="99"),
        },
        config=config,
    )
    baseline_ranks = {row["symbol"]: (row["entry_context_rank"], row["entry_context_percentile"]) for row in baseline}
    future_ranks = {row["symbol"]: (row["entry_context_rank"], row["entry_context_percentile"]) for row in with_future if row["trading_date"] == "2024-01-02"}
    assert baseline_ranks == future_ranks


def test_full_fixture_report_generation_rejected_retention_and_regressions(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    setup_rows = full_fixture_setup_rows()
    candidate_rows = [base_candidate_from_setup(row) for row in setup_rows]
    regime_rows = [
        base_regime("2024-01-02", "BULLISH"),
        base_regime("2024-01-03", "NEUTRAL"),
        base_regime("2024-01-04", "BEARISH"),
        base_regime("2024-01-05", "BULLISH"),
        base_regime("2024-01-06", "UNAVAILABLE", confidence_state="LOW", available_weight_pct="40"),
    ]
    write_gzip_rows(data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz", [feature_from_setup(row) for row in setup_rows])
    write_gzip_rows(data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz", candidate_rows)
    write_gzip_rows(data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz", setup_rows)
    write_gzip_rows(data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz", regime_rows)

    report = build_entry_evaluations(config=EntryEvaluationEngineConfig(data_dir=data_dir))
    markdown_path = tmp_path / "docs" / "strategy-v1-entry-evaluation.md"
    write_strategy_v1_entry_evaluation_markdown(report, markdown_path)

    assert report["ready_for_review"] is True
    assert report["generation"]["full_generation_completed"] is True
    assert report["generation"]["total_rows_evaluated"] == len(setup_rows)
    assert report["pilot"]["validation_passed"] is True
    assert report["regression"]["daily_features_v1_unchanged"] is True
    assert report["regression"]["momentum_candidates_v1_unchanged"] is True
    assert report["regression"]["daily_setup_evaluation_v1_unchanged"] is True
    assert report["regression"]["market_regime_v1_unchanged"] is True
    assert report["safety"]["orders_placed"] == 0
    assert report["safety"]["remote_migrations_applied"] == 0
    assert report["safety"]["supabase_bulk_records_persisted"] == 0
    assert report["safety"]["final_100_point_entry_score_generated"] == 0
    assert report["safety"]["prohibited_output_fields"] == []
    assert (data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz").exists()
    assert (data_dir / "reports" / "entry_evaluation_summary.json").exists()
    assert (data_dir / "reports" / "entry_evaluation_daily_funnel.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_regime_funnel.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_penalties.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_pilot_validation.csv").exists()
    assert (data_dir / "reports" / "entry_evaluation_exceptional_longs.csv").exists()
    assert markdown_path.exists()

    output_rows = read_gzip_rows(data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz")
    assert len(output_rows) == len(setup_rows)
    assert any(row["entry_readiness"] == "NOT_READY" for row in output_rows)
    assert any(row["entry_readiness"] == "EXCEPTIONAL_LONG_REVIEW" for row in output_rows)
    assert all(row["risk_reward_status"] == "NOT_EVALUATED" for row in output_rows)


def full_fixture_setup_rows() -> list[dict[str, object]]:
    return [
        base_setup(symbol="AAA", trading_date="2024-01-02"),
        base_setup(
            symbol="BBB",
            trading_date="2024-01-02",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="VALID",
            volume_confirmation="GOOD",
            benchmark_rs_context="POSITIVE",
            consolidation_quality="GOOD",
        ),
        base_setup(symbol="CCC", trading_date="2024-01-03"),
        base_setup(
            symbol="DDD",
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
        base_setup(
            symbol="EEE",
            trading_date="2024-01-04",
            candidate_state="EMERGING",
            emerging_eligible="True",
            confirmed_eligible="False",
            both_eligible="False",
            setup_quality="VALID",
            volume_confirmation="GOOD",
            benchmark_rs_context="POSITIVE",
            consolidation_quality="GOOD",
        ),
        base_setup(symbol="FFF", trading_date="2024-01-04"),
        base_setup(symbol="GGG", trading_date="2024-01-05", extension_risk="HIGH"),
        base_setup(symbol="HHH", trading_date="2024-01-05", false_breakout_flags="UPPER_WICK_REJECTION"),
        base_setup(symbol="III", trading_date="2024-01-06"),
    ]


def base_setup(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
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
        "setup_rank": "1",
        "setup_percentile": "99.0",
        "setup_type_flags": "BREAKOUT_20D;MOMENTUM_CONTINUATION",
        "breakout_state": "CLOSE_ACCEPTED",
        "level_quality": "GOOD",
        "consolidation_state": "TIGHT",
        "consolidation_quality": "STRONG",
        "acceptance_state": "CLOSE_ACCEPTED",
        "candle_quality": "STRONG",
        "volume_confirmation": "STRONG",
        "benchmark_rs_context": "STRONG",
        "sector_context_status": "CURRENT_ONLY",
        "extension_risk": "LOW",
        "overhead_resistance": "LOW",
        "false_breakout_flags": "",
        "daily_level_reclaim": "True",
        "supporting_evidence": "SYNTHETIC_TEST_FIXTURE",
        "warning_flags": "",
    }
    row.update(overrides)
    return row


def base_candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
        "symbol": "AAA",
        "isin": "INE000000001",
        "membership_status": "ACTIVE",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "research_eligible": "True",
        "mandatory_gates_passed": "True",
        "rejection_reasons": "",
        "candidate_state": "CONFIRMED",
        "emerging_eligible": "False",
        "confirmed_eligible": "True",
        "both_eligible": "False",
        "confirmed_rank": "1",
        "confirmed_percentile": "99.0",
        "extension_status": "NORMAL",
        "candidate_strength_descriptor": "STRONG",
        "warning_flags": "",
    }
    row.update(overrides)
    return row


def base_candidate_from_setup(setup_row: dict[str, object], **overrides: object) -> dict[str, object]:
    row = base_candidate(
        trading_date=setup_row["trading_date"],
        symbol=setup_row["symbol"],
        isin=setup_row["isin"],
        candidate_state=setup_row["candidate_state"],
        emerging_eligible=setup_row["emerging_eligible"],
        confirmed_eligible=setup_row["confirmed_eligible"],
        both_eligible=setup_row["both_eligible"],
    )
    row.update(overrides)
    return row


def base_regime(trading_date: str, state: str, **overrides: object) -> dict[str, object]:
    score_by_state = {"BULLISH": "40", "NEUTRAL": "0", "BEARISH": "-40", "UNAVAILABLE": ""}
    row: dict[str, object] = {
        "trading_date": trading_date,
        "regime_version": MARKET_REGIME_VERSION,
        "config_hash": REGIME_HASH,
        "regime_state": state,
        "classification_status": "CLASSIFIED" if state != "UNAVAILABLE" else "INSUFFICIENT_COMPONENT_COVERAGE",
        "regime_score_normalized": score_by_state[state],
        "confidence_score": "85" if state != "UNAVAILABLE" else "40",
        "confidence_state": "HIGH" if state != "UNAVAILABLE" else "LOW",
        "available_weight_pct": "90" if state != "UNAVAILABLE" else "40",
    }
    row.update(overrides)
    return row


def feature_from_setup(setup_row: dict[str, object]) -> dict[str, object]:
    return {
        "trading_date": setup_row["trading_date"],
        "symbol": setup_row["symbol"],
        "isin": setup_row["isin"],
        "feature_version": "DAILY_FEATURES_V1",
    }


def first_for_date(rows: list[dict[str, object]], trading_date: str) -> dict[str, object]:
    return next(row for row in rows if row["trading_date"] == trading_date)


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_gzip_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))

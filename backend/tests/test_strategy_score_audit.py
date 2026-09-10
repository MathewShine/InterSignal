from __future__ import annotations

import csv
import gzip
import json
from decimal import Decimal
from pathlib import Path

from app.strategy.momentum_candidates import file_sha256
from app.strategy.scoring.score_audit import (
    STRATEGY_SCORE_AUDIT_VERSION,
    StrategyScoreAuditConfig,
    build_strategy_score_audit,
    correlation_audit,
    coverage_audit,
    headroom_audit,
    independent_disposition,
    invariant_audit,
    leave_one_out_audit,
    normalized_counterfactual,
    normalized_isolation_audit,
    penalty_audit,
    pilot_audit,
    prohibited_audit_fields,
    reconstruct_momentum_points,
    reward_risk_audit,
    threshold_audit,
    verify_audit_hashes,
    write_strategy_score_audit_markdown,
)
from app.strategy.scoring.score_config import StrategyScoreConfig
from app.strategy.scoring.strategy_scorer import SCORE_OUTPUT_FIELDS, score_joined_row, scoring_disposition


def test_independent_score_arithmetic_caps_weight_coverage_and_bounds() -> None:
    row = scored_row()
    summary, details = invariant_audit(
        [row], risk_lookup={key(row): base_risk()}, candidate_lookup={key(row): base_candidate()},
        setup_lookup={key(row): base_setup()}, entry_lookup={key(row): base_entry()},
        config=StrategyScoreConfig(),
    )
    assert summary["arithmetic_mismatches"] == 0
    assert summary["component_cap_violations"] == 0
    assert summary["raw_score_bound_violations"] == 0
    assert summary["available_weight_mismatches"] == 0
    assert summary["coverage_mismatches"] == 0
    assert summary["normalized_formula_mismatches"] == 0
    assert details == []


def test_independent_invariants_detect_corruption() -> None:
    row = scored_row()
    row["raw_strategy_score"] = Decimal("101")
    row["setup_points"] = Decimal("21")
    row["available_weight"] = Decimal("100")
    row["score_coverage_pct"] = Decimal("100")
    summary, _ = invariant_audit(
        [row], risk_lookup={key(row): base_risk()}, candidate_lookup={key(row): base_candidate()},
        setup_lookup={key(row): base_setup()}, entry_lookup={key(row): base_entry()},
        config=StrategyScoreConfig(),
    )
    assert summary["arithmetic_mismatches"] == 1
    assert summary["component_cap_violations"] == 1
    assert summary["raw_score_bound_violations"] == 1
    assert summary["available_weight_mismatches"] == 1


def test_normalized_score_is_diagnostic_only_in_source_and_output() -> None:
    row = scored_row(setup_quality="VALID", reward_risk_ratio="1.50")
    row["normalized_available_score"] = Decimal("99")
    row["raw_strategy_score"] = Decimal("79")
    row["score_band"] = "BELOW_THRESHOLD"
    row["scoring_disposition"] = "NOT_ELIGIBLE"
    result = normalized_isolation_audit([row])
    assert result["result"] == "NORMALIZED_DIAGNOSTIC_ISOLATED"
    assert result["implementation_source_isolated"] is True


def test_sector_and_catalyst_are_missing_without_free_weight() -> None:
    row = scored_row()
    assert row["sector_availability"] == "UNAVAILABLE"
    assert row["sector_points"] == 0
    assert row["catalyst_availability"] == "UNAVAILABLE"
    assert row["catalyst_points"] == 0
    assert row["available_weight"] == 85


def test_coverage_distribution_and_insufficient_coverage_block() -> None:
    full = scored_row()
    unavailable = scored_row(symbol="LOWCOV")
    unavailable["relative_strength_availability"] = "UNAVAILABLE"
    unavailable["relative_strength_points"] = Decimal("0")
    unavailable["available_weight"] = Decimal("70")
    unavailable["score_coverage_pct"] = Decimal("70")
    unavailable["raw_strategy_score"] = Decimal("70")
    unavailable["normalized_available_score"] = Decimal("100")
    unavailable["score_band"] = "BELOW_THRESHOLD"
    unavailable["scoring_disposition"] = "INSUFFICIENT_COVERAGE"
    _, summary = coverage_audit([full, unavailable])
    assert summary["exact_available_weight_frequencies"] == {"70": 1, "85": 1}
    assert summary["insufficient_coverage_causes"] == {"RS_UNAVAILABLE": 1}
    assert summary["below_minimum_normal_promotion_violations"] == 0


def test_full_preview_and_exceptional_threshold_boundaries() -> None:
    config = StrategyScoreConfig()
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("79.99"), coverage=Decimal("100"), config=config) == "NOT_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("80"), coverage=Decimal("100"), config=config) == "ENTRY_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("89.99"), coverage=Decimal("100"), config=config) == "ENTRY_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("90"), coverage=Decimal("100"), config=config) == "HIGH_CONVICTION"
    assert independent_disposition("PREVIEW_SCORE", Decimal("100"), Decimal("100")) == "PREVIEW_ONLY"
    assert independent_disposition("EXCEPTIONAL_REVIEW_SCORE", Decimal("100"), Decimal("100")) == "EXCEPTIONAL_REVIEW"


def test_momentum_reconstruction_excludes_current_day_return() -> None:
    first = reconstruct_momentum_points(base_candidate(return_1d="-0.99"))
    second = reconstruct_momentum_points(base_candidate(return_1d="99"))
    assert first == second == Decimal("20")


def test_candidate_state_does_not_change_score_when_evidence_is_unchanged() -> None:
    confirmed = scored_row(candidate_state="CONFIRMED")
    emerging = scored_row(candidate_state="EMERGING", both_eligible="False", candidate_group="EMERGING_ONLY")
    assert confirmed["raw_strategy_score"] == emerging["raw_strategy_score"]


def test_risk_reward_boundaries_and_full_score_zero_invariant() -> None:
    rows = [
        scored_row(symbol="A", reward_risk_ratio="1.50"),
        scored_row(symbol="B", reward_risk_ratio="1.99"),
        scored_row(symbol="C", reward_risk_ratio="2.00"),
        scored_row(symbol="D", reward_risk_ratio="2.49"),
        scored_row(symbol="E", reward_risk_ratio="2.50"),
    ]
    result = reward_risk_audit(rows)
    assert result["mapping_violations"] == 0
    assert result["full_score_zero_point_violations"] == 0
    assert result["full_score_distribution"] == {"3": 2, "4": 2, "5": 1}


def test_penalties_are_separate_and_blocking_rows_cannot_promote() -> None:
    non_blocking = scored_row(penalty_codes="LOW_VOLUME_CONFIRMATION", max_penalty_severity="MEDIUM")
    blocked = scored_row(symbol="BLOCKED", blocking_penalty_present="True", risk_readiness="BLOCKED")
    assert non_blocking["raw_strategy_score"] == scored_row()["raw_strategy_score"]
    assert blocked["score_mode"] == "NOT_SCORE_ELIGIBLE"
    result = penalty_audit([non_blocking, blocked])
    assert result["blocking_penalty_violations"] == 0
    assert result["penalties_numerically_subtracted"] is False


def test_threshold_leave_out_and_coverage_counterfactuals() -> None:
    rows = [
        scored_row(symbol="A"),
        scored_row(symbol="B", setup_quality="VALID", reward_risk_ratio="1.50"),
    ]
    threshold_rows, result = threshold_audit(rows)
    assert threshold_rows
    assert result["threshold_sensitivity"]["80"]["eligible_count"] == 1
    assert result["coverage_sensitivity"]["80"]["eligible_count"] == 1
    leave_out = leave_one_out_audit(rows)
    assert leave_out["setup"]["eligible_lost"] == 1


def test_normalized_invalid_counterfactual_is_explicit() -> None:
    row = scored_row(setup_quality="VALID")
    result = normalized_counterfactual([row])
    assert result["label"] == "INVALID_DIAGNOSTIC_ONLY"
    assert result["all_rows_newly_gte_90"] >= 1


def test_component_correlations_and_headroom_are_structural_only() -> None:
    rows = [
        scored_row(symbol="A"),
        scored_row(symbol="B", setup_quality="VALID", volume_confirmation="GOOD", benchmark_rs_context="POSITIVE"),
        scored_row(symbol="C", setup_quality="VALID", volume_confirmation="NORMAL", benchmark_rs_context="NEUTRAL"),
    ]
    correlations, summary = correlation_audit(rows)
    assert correlations
    assert summary["population"] == "FULL_SCORE"
    headroom_rows, headroom = headroom_audit(rows)
    assert headroom_rows
    assert sum(headroom["to_80"].values()) == len(rows)


def test_pilot_audit_requires_all_a_to_n_cases() -> None:
    rows = [scored_row()]
    pilot_rows, result = pilot_audit(rows)
    assert len(pilot_rows) == 14
    assert result["passed"] is False


def test_hash_mismatch_stops_audit() -> None:
    try:
        verify_audit_hashes({})
    except ValueError as exc:
        assert "Frozen audit input hash mismatch" in str(exc)
    else:
        raise AssertionError("Expected frozen hash mismatch")


def test_no_outcome_or_execution_fields_are_consumed() -> None:
    assert prohibited_audit_fields(SCORE_OUTPUT_FIELDS) == []


def test_report_generation_preserves_all_input_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    config = StrategyScoreAuditConfig(data_dir=data_dir, enforce_frozen_hashes=False)
    score = scored_row()
    candidate = base_candidate()
    setup = base_setup()
    entry = base_entry()
    risk = base_risk()
    files = {
        config.engine_config.feature_dataset_path: [{"trading_date": "2024-01-02", "symbol": "ABC"}],
        config.candidate_dataset_path: [candidate],
        config.setup_dataset_path: [setup],
        config.engine_config.regime_dataset_path: [{"trading_date": "2024-01-02", "regime_state": "BULLISH"}],
        config.entry_dataset_path: [entry],
        config.engine_config.risk_v1_dataset_path: [{**risk, "risk_version": "RISK_STRUCTURE_V1"}],
        config.risk_dataset_path: [risk],
        config.score_dataset_path: [score],
    }
    for path, rows in files.items():
        write_gzip_rows(path, rows)
    before = {path: file_sha256(path) for path in files}

    report = build_strategy_score_audit(config=config)
    markdown = tmp_path / "docs" / "strategy-v1-final-scoring-audit.md"
    write_strategy_score_audit_markdown(report, markdown)

    assert report["audit_version"] == STRATEGY_SCORE_AUDIT_VERSION
    assert config.summary_path.exists()
    assert config.report_path("components").exists()
    assert config.report_path("correlations").exists()
    assert config.report_path("thresholds").exists()
    assert config.report_path("gate_conflicts").exists()
    assert config.report_path("coverage").exists()
    assert config.report_path("candidate_categories").exists()
    assert config.report_path("neutral_ceiling").exists()
    assert config.report_path("headroom").exists()
    assert config.report_path("pilot").exists()
    assert (config.audit_dir / "strategy_score_audit_violations.csv.gz").exists()
    assert markdown.exists()
    assert before == {path: file_sha256(path) for path in files}
    assert all(report["regression"]["unchanged_during_audit"].values())
    assert json.loads(config.summary_path.read_text(encoding="utf-8"))["audit_version"] == STRATEGY_SCORE_AUDIT_VERSION
    assert report["safety"]["orders_placed"] == 0


def scored_row(**overrides: object) -> dict[str, object]:
    candidate_fields = {name: overrides[name] for name in list(overrides) if name in base_candidate()}
    setup_fields = {name: overrides[name] for name in list(overrides) if name in base_setup()}
    entry_fields = {name: overrides[name] for name in list(overrides) if name in base_entry()}
    risk_fields = {name: overrides[name] for name in list(overrides) if name in base_risk()}
    symbol = str(overrides.get("symbol", "ABC"))
    for fields in (candidate_fields, setup_fields, entry_fields, risk_fields):
        fields["symbol"] = symbol
    return score_joined_row(
        risk_row=base_risk(**risk_fields),
        candidate_row=base_candidate(**candidate_fields),
        setup_row=base_setup(**setup_fields),
        entry_row=base_entry(**entry_fields),
    )


def key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["trading_date"]), str(row["symbol"])


def base_candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02", "symbol": "ABC", "candidate_state": "CONFIRMED",
        "both_eligible": "True", "return_1d": "0.01", "return_5d": "0.03", "return_10d": "0.05",
        "return_20d": "0.07", "up_days_ratio_10": "0.70", "up_days_ratio_20": "0.60",
    }
    row.update(overrides)
    return row


def base_setup(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02", "symbol": "ABC", "setup_quality": "STRONG",
        "volume_confirmation": "EXCEPTIONAL", "benchmark_rs_context": "STRONG",
    }
    row.update(overrides)
    return row


def base_entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02", "symbol": "ABC", "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "candidate_group": "BOTH_ELIGIBLE", "exceptional_long_status": "NOT_EXCEPTIONAL",
        "regime_confidence_state": "HIGH", "penalty_codes": "", "max_penalty_severity": "NONE",
        "blocking_penalty_present": "False", "warning_evidence": "",
    }
    row.update(overrides)
    return row


def base_risk(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02", "symbol": "ABC", "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1", "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "setup_version": "DAILY_SETUP_EVALUATION_V1", "regime_version": "MARKET_REGIME_V1",
        "entry_version": "ENTRY_EVALUATION_V1", "risk_version": "RISK_STRUCTURE_V1_1",
        "risk_config_hash": "f66fbdf2fc5aecd0", "risk_mode": "FULL_EVALUATION",
        "risk_readiness": "READY_FOR_FINAL_SCORING", "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "regime_state": "BULLISH", "reward_risk_ratio": "2.50", "invalidation_basis": "BREAKOUT_STRUCTURE",
        "warning_flags": "", "rejection_reasons": "",
    }
    row.update(overrides)
    return row


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({name for row in rows for name in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

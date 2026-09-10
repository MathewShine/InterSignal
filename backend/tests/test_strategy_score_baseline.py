from __future__ import annotations

from pathlib import Path

import pytest

from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_BASELINE_STATUS,
    STRATEGY_SCORE_V1_DATASET_HASH,
    audit_score_references,
    baseline_hash_checks,
    baseline_input_hashes,
    build_score_baseline_promotion_report,
    get_current_scoring_baseline,
    get_current_strategy_score_config_hash,
    get_current_strategy_score_profile,
    get_current_strategy_score_version,
    resolve_current_strategy_score_dataset,
    resolve_strategy_score_dataset,
    validate_score_baseline_rows,
    verify_current_strategy_score_baseline,
    write_score_baseline_promotion_markdown,
    write_score_baseline_promotion_report,
)
from app.strategy.scoring.score_config import (
    FUTURE_INTRADAY_SCORE_PROFILE,
    STRATEGY_SCORE_VERSION,
    SWING_DAILY_EOD_PROFILE,
    StrategyScoreConfig,
)
from app.strategy.scoring.strategy_scorer import StrategyScoreEngineConfig, score_joined_row

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_current_swing_version_profile_and_config_hash_are_authoritative() -> None:
    assert get_current_strategy_score_version() == CURRENT_STRATEGY_SCORE_VERSION == STRATEGY_SCORE_VERSION
    assert get_current_strategy_score_profile() == CURRENT_STRATEGY_SCORE_PROFILE == SWING_DAILY_EOD_PROFILE
    assert get_current_strategy_score_config_hash() == CURRENT_STRATEGY_SCORE_CONFIG_HASH
    assert StrategyScoreConfig().config_hash() == CURRENT_STRATEGY_SCORE_CONFIG_HASH


def test_current_dataset_resolver_uses_canonical_swing_v1_path() -> None:
    expected = DATA_DIR / "research" / "strategy_scores" / "swing" / "daily" / "v1" / "strategy_scores_v1.csv.gz"
    assert resolve_current_strategy_score_dataset(DATA_DIR) == expected
    assert resolve_strategy_score_dataset(
        DATA_DIR, profile=SWING_DAILY_EOD_PROFILE, version=STRATEGY_SCORE_VERSION
    ) == expected


def test_current_baseline_contract_is_profile_aware() -> None:
    baseline = get_current_scoring_baseline(DATA_DIR)
    assert baseline.version == STRATEGY_SCORE_VERSION
    assert baseline.profile == SWING_DAILY_EOD_PROFILE
    assert baseline.config_hash == CURRENT_STRATEGY_SCORE_CONFIG_HASH
    assert baseline.status == STRATEGY_SCORE_BASELINE_STATUS
    with pytest.raises(ValueError, match="No current scoring baseline"):
        get_current_strategy_score_version(FUTURE_INTRADAY_SCORE_PROFILE)


def test_generic_score_engine_resolves_through_current_registry() -> None:
    engine = StrategyScoreEngineConfig(data_dir=DATA_DIR)
    baseline = get_current_scoring_baseline(DATA_DIR)
    assert engine.output_dataset_path == baseline.dataset_path
    build_script = (REPO_ROOT / "backend" / "scripts" / "build_strategy_scores.py").read_text(encoding="utf-8")
    assert "get_current_scoring_baseline" in build_script
    assert "CURRENT_SCORE_BASELINE_RESOLUTION_MISMATCH" in build_script


def test_frozen_dataset_hash_and_active_risk_dependency() -> None:
    baseline = verify_current_strategy_score_baseline(DATA_DIR)
    assert file_sha256(baseline.dataset_path) == STRATEGY_SCORE_V1_DATASET_HASH
    validation = validate_score_baseline_rows(baseline.dataset_path)
    assert validation["identity"]["risk_versions"] == [CURRENT_RISK_STRUCTURE_VERSION]
    assert validation["identity"]["risk_config_hashes"] == [CURRENT_RISK_STRUCTURE_CONFIG_HASH]
    assert baseline_input_hashes(DATA_DIR)["risk_v1_1"] == RISK_STRUCTURE_V1_1_DATASET_HASH


def test_frozen_score_counts_and_lightweight_invariants() -> None:
    validation = validate_score_baseline_rows(resolve_current_strategy_score_dataset(DATA_DIR))
    assert validation["counts"] == validation["expected_counts"]
    assert validation["counts"] == {
        "total_rows": 26130,
        "full_score": 10791,
        "preview_score": 3136,
        "exceptional_review_score": 324,
        "not_score_eligible": 11879,
        "entry_eligible": 4268,
        "high_conviction": 0,
    }
    assert validation["all_valid"] is True
    assert not any(validation["invariants"].values())


def test_weights_thresholds_coverage_and_missing_evidence_remain_locked() -> None:
    config = StrategyScoreConfig()
    assert config.weights.total() == 100
    assert config.snapshot()["weights"] == {
        "setup": "20", "momentum": "20", "rvol": "15", "relative_strength": "15",
        "regime": "10", "sector": "10", "catalyst": "5", "reward_risk": "5",
    }
    assert config.thresholds.entry_eligible == 80
    assert config.thresholds.high_conviction == 90
    assert config.thresholds.minimum_score_coverage_pct == 80
    assert config.normalized_score_usage == "DIAGNOSTIC_ONLY"
    assert config.sector_history_status == "UNAVAILABLE_POINT_IN_TIME_MAPPING"
    assert config.catalyst_history_status == "UNAVAILABLE_HISTORICAL_CATALYST_LAYER"


def test_normalized_preview_exceptional_and_gate_semantics_remain_locked() -> None:
    normal = score_joined_row(
        risk_row=base_risk(), candidate_row=base_candidate(), setup_row=base_setup(), entry_row=base_entry()
    )
    preview = score_joined_row(
        risk_row=base_risk(entry_readiness="CONDITIONALLY_READY", risk_mode="PREVIEW_ONLY", risk_readiness="NOT_EVALUATED"),
        candidate_row=base_candidate(), setup_row=base_setup(), entry_row=base_entry(entry_readiness="CONDITIONALLY_READY"),
    )
    exceptional = score_joined_row(
        risk_row=base_risk(entry_readiness="EXCEPTIONAL_LONG_REVIEW", regime_state="BEARISH"),
        candidate_row=base_candidate(), setup_row=base_setup(),
        entry_row=base_entry(entry_readiness="EXCEPTIONAL_LONG_REVIEW", exceptional_long_status="EXCEPTIONAL_REVIEW_READY"),
    )
    assert normal["raw_strategy_score"] == 85
    assert normal["normalized_available_score"] == 100
    assert normal["scoring_disposition"] == "ENTRY_ELIGIBLE"
    assert preview["scoring_disposition"] == "PREVIEW_ONLY"
    assert exceptional["scoring_disposition"] == "EXCEPTIONAL_REVIEW"
    assert normal["sector_availability"] == normal["catalyst_availability"] == "UNAVAILABLE"


def test_reference_audit_has_no_unintended_forward_score_paths() -> None:
    audit = audit_score_references(REPO_ROOT)
    assert audit["total_references"] > 0
    assert audit["unintended_forward_references"] == []


def test_all_frozen_input_hashes_match() -> None:
    assert all(baseline_hash_checks(baseline_input_hashes(DATA_DIR)).values())


def test_promotion_report_generation_and_score_immutability(tmp_path: Path) -> None:
    dataset = resolve_current_strategy_score_dataset(DATA_DIR)
    before = file_sha256(dataset)
    report = build_score_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=True,
        frontend_build_passed=True,
    )
    report_path = tmp_path / "strategy_score_baseline_promotion.json"
    document_path = tmp_path / "strategy-score-baseline-promotion.md"
    write_score_baseline_promotion_report(report_path, report)
    write_score_baseline_promotion_markdown(document_path, report)
    assert report["promotion_status"] == "ACTIVE_FORWARD_BASELINE"
    assert report["step_status"] == "COMPLETE"
    assert report["ready_for_review"] is True
    assert report["score_dataset_unchanged_during_promotion"] is True
    assert file_sha256(dataset) == before
    assert report_path.exists()
    assert document_path.exists()


def base_candidate() -> dict[str, object]:
    return {
        "trading_date": "2024-01-02", "symbol": "ABC", "candidate_state": "CONFIRMED",
        "both_eligible": "True", "return_5d": "0.03", "return_10d": "0.05", "return_20d": "0.07",
        "up_days_ratio_10": "0.70", "up_days_ratio_20": "0.60",
    }


def base_setup() -> dict[str, object]:
    return {
        "trading_date": "2024-01-02", "symbol": "ABC", "setup_quality": "STRONG",
        "volume_confirmation": "EXCEPTIONAL", "benchmark_rs_context": "STRONG",
    }


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
        "entry_version": "ENTRY_EVALUATION_V1", "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH, "risk_mode": "FULL_EVALUATION",
        "risk_readiness": "READY_FOR_FINAL_SCORING", "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "regime_state": "BULLISH", "reward_risk_ratio": "2.50", "invalidation_basis": "BREAKOUT_STRUCTURE",
        "warning_flags": "", "rejection_reasons": "",
    }
    row.update(overrides)
    return row


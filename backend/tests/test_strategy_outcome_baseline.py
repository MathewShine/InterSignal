from __future__ import annotations

from pathlib import Path

import pytest

from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import (
    APPROVED_BASELINE_DECISION,
    APPROVED_ENTRY_REVALIDATION_RESULT,
    APPROVED_FORWARD_SAFETY_RESULT,
    APPROVED_FOUR_SESSION_HORIZON_RESULT,
    APPROVED_OUTCOME_LABEL_RESULT,
    CURRENT_STRATEGY_OUTCOME_CONFIG_HASH,
    CURRENT_STRATEGY_OUTCOME_PROFILE,
    CURRENT_STRATEGY_OUTCOME_VERSION,
    STRATEGY_OUTCOME_BASELINE_STATUS,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    audit_outcome_references,
    build_outcome_baseline_promotion_report,
    get_current_strategy_outcome_baseline,
    get_current_strategy_outcome_config_hash,
    get_current_strategy_outcome_profile,
    get_current_strategy_outcome_version,
    outcome_input_hash_checks,
    outcome_input_hashes,
    resolve_current_strategy_outcome_dataset,
    resolve_strategy_outcome_dataset,
    validate_outcome_baseline_rows,
    verify_current_strategy_outcome_baseline,
    verify_future_data_separation,
    write_outcome_baseline_promotion_markdown,
    write_outcome_baseline_promotion_report,
)
from app.strategy.outcomes.outcome_config import (
    FUTURE_INTRADAY_OUTCOME_PROFILE,
    STRATEGY_OUTCOME_VERSION,
    SWING_DAILY_OUTCOME_PROFILE,
    StrategyOutcomeConfig,
)
from app.strategy.outcomes.outcome_engine import StrategyOutcomeEngineConfig
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_current_outcome_identity_and_config_hash_are_authoritative() -> None:
    assert get_current_strategy_outcome_version() == CURRENT_STRATEGY_OUTCOME_VERSION == STRATEGY_OUTCOME_VERSION
    assert get_current_strategy_outcome_profile() == CURRENT_STRATEGY_OUTCOME_PROFILE == SWING_DAILY_OUTCOME_PROFILE
    assert get_current_strategy_outcome_config_hash() == CURRENT_STRATEGY_OUTCOME_CONFIG_HASH
    assert StrategyOutcomeConfig().config_hash() == CURRENT_STRATEGY_OUTCOME_CONFIG_HASH


def test_current_dataset_resolver_uses_canonical_profile_aware_path() -> None:
    expected = DATA_DIR / "research/outcomes/swing/daily/v1/strategy_outcomes_v1.csv.gz"
    assert resolve_current_strategy_outcome_dataset(DATA_DIR) == expected
    assert resolve_strategy_outcome_dataset(
        DATA_DIR,
        profile=SWING_DAILY_OUTCOME_PROFILE,
        version=STRATEGY_OUTCOME_VERSION,
    ) == expected


def test_current_baseline_contract_is_profile_aware_and_isolates_future_intraday() -> None:
    baseline = get_current_strategy_outcome_baseline(DATA_DIR)
    assert baseline.version == STRATEGY_OUTCOME_VERSION
    assert baseline.profile == SWING_DAILY_OUTCOME_PROFILE
    assert baseline.config_hash == CURRENT_STRATEGY_OUTCOME_CONFIG_HASH
    assert baseline.status == STRATEGY_OUTCOME_BASELINE_STATUS
    with pytest.raises(ValueError, match="No current outcome baseline"):
        get_current_strategy_outcome_version(FUTURE_INTRADAY_OUTCOME_PROFILE)


def test_generic_outcome_build_resolves_through_current_registry() -> None:
    engine = StrategyOutcomeEngineConfig(data_dir=DATA_DIR)
    baseline = get_current_strategy_outcome_baseline(DATA_DIR)
    assert engine.output_dataset_path == baseline.dataset_path
    build_script = (REPO_ROOT / "backend/scripts/build_strategy_outcomes.py").read_text(encoding="utf-8")
    assert "get_current_strategy_outcome_baseline" in build_script
    assert "CURRENT_OUTCOME_BASELINE_RESOLUTION_MISMATCH" in build_script
    assert "--outcome-version" in build_script
    assert "--outcome-profile" in build_script


def test_frozen_dataset_hash_and_dependencies() -> None:
    baseline = verify_current_strategy_outcome_baseline(DATA_DIR)
    assert file_sha256(baseline.dataset_path) == STRATEGY_OUTCOME_V1_DATASET_HASH
    validation = validate_outcome_baseline_rows(baseline.dataset_path)
    assert validation["identity"]["score_versions"] == [CURRENT_STRATEGY_SCORE_VERSION]
    assert validation["identity"]["score_profiles"] == [CURRENT_STRATEGY_SCORE_PROFILE]
    assert validation["identity"]["score_config_hashes"] == [CURRENT_STRATEGY_SCORE_CONFIG_HASH]
    assert validation["identity"]["risk_versions"] == [CURRENT_RISK_STRUCTURE_VERSION]
    assert validation["identity"]["risk_config_hashes"] == [CURRENT_RISK_STRUCTURE_CONFIG_HASH]
    hashes = outcome_input_hashes(DATA_DIR)
    assert hashes["score_v1"] == STRATEGY_SCORE_V1_DATASET_HASH
    assert hashes["risk_v1_1"] == RISK_STRUCTURE_V1_1_DATASET_HASH


def test_primary_counts_and_first_touch_counts_remain_frozen() -> None:
    validation = validate_outcome_baseline_rows(resolve_current_strategy_outcome_dataset(DATA_DIR))
    assert validation["counts"] == validation["expected_counts"] == {
        "total_rows": 14251,
        "primary_source_count": 4268,
        "valid_entry_count": 3296,
        "invalid_entry_count": 972,
        "unsafe_count": 700,
        "rr_invalid_count": 260,
        "open_below_stop_count": 12,
        "quantity_zero_count": 0,
        "target_first_count": 115,
        "stop_first_count": 724,
        "ambiguous_count": 1,
        "neither_count": 2456,
    }
    assert validation["all_valid"] is True
    assert not any(validation["invariants"].values())


def test_methodology_ambiguity_and_right_censoring_remain_locked() -> None:
    config = StrategyOutcomeConfig()
    assert config.entry_model == "NEXT_SESSION_OPEN"
    assert config.max_hold_sessions == 4
    assert str(config.minimum_effective_reward_risk) == "1.50"
    assert config.same_bar_ambiguity_policy == "AMBIGUOUS_EXCLUDE_FROM_DETERMINISTIC_CLASSIFICATION"
    assert config.transaction_cost_status == "NOT_MODELED"
    assert config.slippage_status == "NOT_MODELED"
    invariants = validate_outcome_baseline_rows(resolve_current_strategy_outcome_dataset(DATA_DIR))["invariants"]
    assert invariants["same_bar_ambiguity_violations"] == 0
    assert invariants["right_censoring_separation_violations"] == 0
    assert invariants["frozen_stop_violations"] == 0
    assert invariants["frozen_target_violations"] == 0


def test_future_data_boundary_excludes_all_frozen_upstream_consumers() -> None:
    separation = verify_future_data_separation(REPO_ROOT)
    assert separation["verified"] is True
    assert separation["violations"] == []
    assert all(separation["checks"].values())


def test_reference_audit_has_no_unintended_forward_outcome_paths() -> None:
    audit = audit_outcome_references(REPO_ROOT)
    assert audit["total_references"] > 0
    assert audit["unintended_forward_references"] == []
    assert audit["classification_counts"]["FORWARD_CURRENT"] > 0
    assert audit["classification_counts"]["AUDIT_ALLOWED"] > 0
    assert audit["classification_counts"]["TEST_FIXTURE_ALLOWED"] > 0
    assert audit["classification_counts"]["DOCUMENTATION_ALLOWED"] > 0


def test_all_frozen_input_hashes_match() -> None:
    hashes = outcome_input_hashes(DATA_DIR)
    assert all(outcome_input_hash_checks(hashes).values())
    assert hashes["outcome_v1"] == STRATEGY_OUTCOME_V1_DATASET_HASH


def test_promotion_report_generation_and_outcome_immutability(tmp_path: Path) -> None:
    dataset = resolve_current_strategy_outcome_dataset(DATA_DIR)
    before = file_sha256(dataset)
    report = build_outcome_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=True,
        frontend_build_passed=True,
    )
    report_path = tmp_path / "strategy_outcome_baseline_promotion.json"
    document_path = tmp_path / "strategy-outcome-baseline-promotion.md"
    write_outcome_baseline_promotion_report(report_path, report)
    write_outcome_baseline_promotion_markdown(document_path, report)
    assert report["promotion_status"] == STRATEGY_OUTCOME_BASELINE_STATUS
    assert report["step_status"] == "COMPLETE"
    assert report["ready_for_review"] is True
    assert report["baseline_decision"] == APPROVED_BASELINE_DECISION
    assert report["forward_safety_result"] == APPROVED_FORWARD_SAFETY_RESULT
    assert report["entry_revalidation_result"] == APPROVED_ENTRY_REVALIDATION_RESULT
    assert report["outcome_label_result"] == APPROVED_OUTCOME_LABEL_RESULT
    assert report["four_session_horizon_result"] == APPROVED_FOUR_SESSION_HORIZON_RESULT
    assert report["lightweight_invariants_clean"] is True
    assert report["outcome_dataset_unchanged_during_promotion"] is True
    assert file_sha256(dataset) == before
    assert report_path.exists()
    assert document_path.exists()

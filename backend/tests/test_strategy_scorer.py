from __future__ import annotations

import csv
import gzip
from decimal import Decimal
from pathlib import Path

from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    resolve_current_risk_structure_dataset,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.scoring.catalyst_score import score_catalyst
from app.strategy.scoring.momentum_score import score_momentum
from app.strategy.scoring.regime_score import score_regime
from app.strategy.scoring.relative_strength_score import score_relative_strength
from app.strategy.scoring.reward_risk_score import score_reward_risk
from app.strategy.scoring.score_config import (
    STRATEGY_SCORE_VERSION,
    SWING_DAILY_EOD_PROFILE,
    StrategyScoreConfig,
)
from app.strategy.scoring.sector_score import score_sector
from app.strategy.scoring.setup_score import score_setup
from app.strategy.scoring.strategy_scorer import (
    COMPONENT_PREFIXES,
    SCORE_OUTPUT_FIELDS,
    StrategyScoreEngineConfig,
    build_strategy_scores,
    evaluate_score_rows,
    prohibited_outcome_fields,
    score_joined_row,
    scoring_disposition,
)
from app.strategy.scoring.volume_score import score_relative_volume

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_score_profile_weights_and_config_hash_are_reproducible() -> None:
    first = StrategyScoreConfig()
    second = StrategyScoreConfig()
    assert first.score_version == STRATEGY_SCORE_VERSION
    assert first.score_profile == SWING_DAILY_EOD_PROFILE
    assert first.weights.total() == Decimal("100")
    assert first.config_hash() == second.config_hash()


def test_setup_score_mapping() -> None:
    config = StrategyScoreConfig()
    expected = {"STRONG": "20", "VALID": "16", "WATCH": "8", "POOR": "0"}
    for quality, points in expected.items():
        result = score_setup({"setup_quality": quality}, config)
        assert result.availability_status == "AVAILABLE"
        assert result.component_points == Decimal(points)


def test_momentum_score_uses_candidate_v1_multiday_thresholds() -> None:
    result = score_momentum(base_candidate(), StrategyScoreConfig())
    assert result.availability_status == "AVAILABLE"
    assert result.component_points == Decimal("20")

    current_day_mutation = base_candidate(return_1d="-0.99")
    assert score_momentum(current_day_mutation, StrategyScoreConfig()).component_points == result.component_points


def test_momentum_missing_input_is_unavailable_not_free_points() -> None:
    result = score_momentum(base_candidate(return_20d=""), StrategyScoreConfig())
    assert result.availability_status == "UNAVAILABLE"
    assert result.available_weight == 0
    assert result.component_points == 0


def test_relative_volume_mapping_and_cap() -> None:
    config = StrategyScoreConfig()
    expected = {"EXCEPTIONAL": "15", "STRONG": "13", "GOOD": "10", "NORMAL": "6", "WEAK": "0"}
    for descriptor, points in expected.items():
        result = score_relative_volume(base_setup(volume_confirmation=descriptor), config)
        assert result.component_points == Decimal(points)
        assert result.component_points <= config.weights.rvol


def test_relative_strength_mapping() -> None:
    config = StrategyScoreConfig()
    expected = {"STRONG": "15", "POSITIVE": "11", "NEUTRAL": "6", "WEAK": "0"}
    for descriptor, points in expected.items():
        result = score_relative_strength(base_setup(benchmark_rs_context=descriptor), config)
        assert result.component_points == Decimal(points)


def test_regime_mapping_and_unavailable_context() -> None:
    config = StrategyScoreConfig()
    assert score_regime(base_risk(regime_state="BULLISH"), base_entry(), config).component_points == 10
    assert score_regime(base_risk(regime_state="NEUTRAL"), base_entry(), config).component_points == 5
    assert score_regime(base_risk(regime_state="BEARISH"), base_entry(), config).component_points == 0
    unavailable = score_regime(base_risk(regime_state="UNAVAILABLE"), base_entry(), config)
    assert unavailable.component_points == 0
    assert unavailable.availability_status == "UNAVAILABLE"


def test_sector_and_catalyst_are_explicitly_unavailable() -> None:
    config = StrategyScoreConfig()
    sector = score_sector(config)
    catalyst = score_catalyst(config)
    assert sector.availability_status == "UNAVAILABLE"
    assert sector.component_points == 0
    assert sector.available_weight == 0
    assert catalyst.availability_status == "UNAVAILABLE"
    assert catalyst.component_points == 0
    assert catalyst.available_weight == 0


def test_reward_risk_boundaries() -> None:
    config = StrategyScoreConfig()
    expected = {
        "1.49": "0",
        "1.50": "3",
        "1.99": "3",
        "2.00": "4",
        "2.49": "4",
        "2.50": "5",
        "9.00": "5",
    }
    for ratio, points in expected.items():
        result = score_reward_risk(base_risk(reward_risk_ratio=ratio), config)
        assert result.component_points == Decimal(points)
        assert result.component_points <= config.weights.reward_risk


def test_raw_score_arithmetic_coverage_and_historical_ceiling() -> None:
    row = score_joined_row(
        risk_row=base_risk(),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(),
    )
    component_sum = sum((row[f"{prefix}_points"] for prefix in COMPONENT_PREFIXES), Decimal("0"))
    assert row["raw_strategy_score"] == component_sum == Decimal("85")
    assert row["available_weight"] == Decimal("85")
    assert row["score_coverage_pct"] == Decimal("85")
    assert row["normalized_available_score"] == Decimal("100")
    assert row["normalized_score_usage"] == "DIAGNOSTIC_ONLY"
    assert row["score_band"] == "ENTRY_ELIGIBLE_SCORE"
    assert row["scoring_disposition"] == "ENTRY_ELIGIBLE"


def test_normalization_never_manufactures_high_conviction() -> None:
    row = score_joined_row(
        risk_row=base_risk(),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(),
    )
    assert row["normalized_available_score"] == 100
    assert row["raw_strategy_score"] == 85
    assert row["scoring_disposition"] != "HIGH_CONVICTION"


def test_entry_and_high_conviction_boundaries_use_raw_score() -> None:
    config = StrategyScoreConfig()
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("79.99"), coverage=Decimal("100"), config=config) == "NOT_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("80"), coverage=Decimal("100"), config=config) == "ENTRY_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("89.99"), coverage=Decimal("100"), config=config) == "ENTRY_ELIGIBLE"
    assert scoring_disposition(mode="FULL_SCORE", raw_score=Decimal("90"), coverage=Decimal("100"), config=config) == "HIGH_CONVICTION"


def test_insufficient_coverage_blocks_ordinary_eligibility() -> None:
    result = scoring_disposition(
        mode="FULL_SCORE",
        raw_score=Decimal("95"),
        coverage=Decimal("75"),
        config=StrategyScoreConfig(),
    )
    assert result == "INSUFFICIENT_COVERAGE"


def test_conditional_preview_is_never_promoted() -> None:
    row = score_joined_row(
        risk_row=base_risk(entry_readiness="CONDITIONALLY_READY", risk_mode="PREVIEW_ONLY", risk_readiness="NOT_EVALUATED"),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(entry_readiness="CONDITIONALLY_READY"),
    )
    assert row["raw_strategy_score"] == 85
    assert row["score_mode"] == "PREVIEW_SCORE"
    assert row["scoring_disposition"] == "PREVIEW_ONLY"


def test_bearish_exceptional_long_remains_exceptional_review() -> None:
    row = score_joined_row(
        risk_row=base_risk(entry_readiness="EXCEPTIONAL_LONG_REVIEW", regime_state="BEARISH"),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(
            entry_readiness="EXCEPTIONAL_LONG_REVIEW",
            exceptional_long_status="EXCEPTIONAL_REVIEW_READY",
        ),
    )
    assert row["score_mode"] == "EXCEPTIONAL_REVIEW_SCORE"
    assert row["scoring_disposition"] == "EXCEPTIONAL_REVIEW"


def test_failed_risk_gate_cannot_be_rescued_by_high_components() -> None:
    row = score_joined_row(
        risk_row=base_risk(risk_readiness="RR_BELOW_MINIMUM", rejection_reasons="RR_BELOW_MINIMUM"),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(),
    )
    assert row["score_mode"] == "NOT_SCORE_ELIGIBLE"
    assert row["scoring_disposition"] == "NOT_ELIGIBLE"


def test_penalties_remain_separate_from_score() -> None:
    baseline = score_joined_row(
        risk_row=base_risk(),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(),
    )
    penalized = score_joined_row(
        risk_row=base_risk(),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(penalty_codes="LOW_VOLUME_CONFIRMATION", max_penalty_severity="MEDIUM"),
    )
    assert penalized["raw_strategy_score"] == baseline["raw_strategy_score"]
    assert penalized["penalty_codes"] == "LOW_VOLUME_CONFIRMATION"
    assert penalized["max_penalty_severity"] == "MEDIUM"


def test_no_signal_execution_or_outcome_fields() -> None:
    row = score_joined_row(
        risk_row=base_risk(),
        candidate_row=base_candidate(),
        setup_row=base_setup(),
        entry_row=base_entry(),
    )
    assert row["trade_signal_status"] == "NOT_GENERATED"
    assert row["execution_status"] == "NOT_IMPLEMENTED"
    assert prohibited_outcome_fields(SCORE_OUTPUT_FIELDS) == []
    assert not any("order" in field.lower() for field in SCORE_OUTPUT_FIELDS)


def test_current_risk_resolver_is_the_scoring_input() -> None:
    data_dir = REPO_ROOT / "data"
    path = resolve_current_risk_structure_dataset(data_dir)
    config = StrategyScoreEngineConfig(data_dir=data_dir)
    assert config.current_risk_dataset_path == path
    assert file_sha256(path) == RISK_STRUCTURE_V1_1_DATASET_HASH


def test_future_context_mutations_do_not_change_t_score() -> None:
    config = StrategyScoreConfig()
    risk = base_risk()
    key = (risk["trading_date"], risk["symbol"])
    future_key = ("2024-01-03", risk["symbol"])
    candidate_lookup = {key: base_candidate()}
    setup_lookup = {key: base_setup()}
    entry_lookup = {key: base_entry()}
    baseline = evaluate_score_rows(
        risk_rows=[risk],
        candidate_lookup=candidate_lookup,
        setup_lookup=setup_lookup,
        entry_lookup=entry_lookup,
        config=config,
    )[0]

    candidate_lookup[future_key] = base_candidate(
        trading_date=future_key[0],
        relative_volume_20d="999",
        relative_return_20d_vs_nifty500="999",
    )
    setup_lookup[future_key] = base_setup(
        trading_date=future_key[0],
        adjusted_high="999999",
        adjusted_low="0.01",
        volume_confirmation="WEAK",
        benchmark_rs_context="WEAK",
    )
    entry_lookup[future_key] = base_entry(
        trading_date=future_key[0],
        regime_state="BEARISH",
    )
    risk["future_target_hit"] = "True"
    risk["future_return"] = "999"
    mutated = evaluate_score_rows(
        risk_rows=[risk],
        candidate_lookup=candidate_lookup,
        setup_lookup=setup_lookup,
        entry_lookup=entry_lookup,
        config=config,
    )[0]
    assert mutated["raw_strategy_score"] == baseline["raw_strategy_score"]
    assert mutated["scoring_disposition"] == baseline["scoring_disposition"]
    assert mutated["sector_availability"] == "UNAVAILABLE"
    assert mutated["catalyst_availability"] == "UNAVAILABLE"


def test_report_generation_and_upstream_immutability(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    config = StrategyScoreEngineConfig(
        data_dir=data_dir,
        full_generation=False,
        enforce_frozen_hashes=False,
    )
    datasets = {
        config.feature_dataset_path: [{"trading_date": "2024-01-02", "symbol": "ABC"}],
        config.candidate_dataset_path: [base_candidate()],
        config.setup_dataset_path: [base_setup()],
        config.regime_dataset_path: [{"trading_date": "2024-01-02", "regime_state": "BULLISH"}],
        config.entry_dataset_path: [base_entry()],
        config.risk_v1_dataset_path: [base_risk(risk_version="RISK_STRUCTURE_V1")],
        config.current_risk_dataset_path: [base_risk()],
    }
    for path, rows in datasets.items():
        write_gzip_rows(path, rows)
    hashes_before = {path: file_sha256(path) for path in datasets}

    report = build_strategy_scores(config=config)

    assert config.summary_path.exists()
    assert config.components_path.exists()
    assert config.pilot_path.exists()
    assert report["score"]["weight_total"] == "100"
    assert report["safety"]["orders_placed"] == 0
    assert all(file_sha256(path) == before for path, before in hashes_before.items())
    assert all(report["regression"].values())


def base_candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "candidate_state": "CONFIRMED",
        "both_eligible": "True",
        "return_1d": "0.01",
        "return_5d": "0.03",
        "return_10d": "0.05",
        "return_20d": "0.07",
        "up_days_ratio_10": "0.70",
        "up_days_ratio_20": "0.60",
    }
    row.update(overrides)
    return row


def base_setup(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "setup_quality": "STRONG",
        "volume_confirmation": "EXCEPTIONAL",
        "relative_volume_20d": "2.10",
        "relative_volume_5d": "2.20",
        "benchmark_rs_context": "STRONG",
        "relative_return_5d_vs_nifty500": "0.03",
        "relative_return_20d_vs_nifty500": "0.04",
    }
    row.update(overrides)
    return row


def base_entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "candidate_group": "BOTH_ELIGIBLE",
        "exceptional_long_status": "NOT_EXCEPTIONAL",
        "regime_state": "BULLISH",
        "regime_confidence_state": "HIGH",
        "regime_confidence_score": "80",
        "penalty_codes": "",
        "max_penalty_severity": "NONE",
        "blocking_penalty_present": "False",
        "warning_evidence": "",
    }
    row.update(overrides)
    return row


def base_risk(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2024-01-02",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "setup_version": "DAILY_SETUP_EVALUATION_V1",
        "regime_version": "MARKET_REGIME_V1",
        "entry_version": "ENTRY_EVALUATION_V1",
        "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "risk_mode": "FULL_EVALUATION",
        "risk_readiness": "READY_FOR_FINAL_SCORING",
        "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "regime_state": "BULLISH",
        "reward_risk_ratio": "2.50",
        "invalidation_basis": "BREAKOUT_STRUCTURE",
        "warning_flags": "",
        "rejection_reasons": "",
    }
    row.update(overrides)
    return row


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

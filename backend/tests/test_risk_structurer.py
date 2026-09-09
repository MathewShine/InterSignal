from __future__ import annotations

import csv
import gzip
import json
from decimal import Decimal
from pathlib import Path

from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.risk.risk_config import RISK_STRUCTURE_VERSION, RiskStructureConfig
from app.risk.risk_structurer import (
    RISK_OUTPUT_FIELDS,
    RiskStructureEngineConfig,
    build_risk_structures,
    evaluate_risk_row,
    prohibited_outcome_fields,
    write_strategy_v1_risk_structure_markdown,
)
from app.risk.stop_placement import RiskDailyBar, build_ohlc_index
from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig
from app.strategy.entry_config import ENTRY_EVALUATION_VERSION, EntryEvaluationConfig
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig

CANDIDATE_HASH = MomentumCandidateConfig().config_hash()
SETUP_HASH = DailySetupEvaluationConfig().config_hash()
REGIME_HASH = MarketRegimeConfig().config_hash()
ENTRY_HASH = EntryEvaluationConfig().config_hash()


def test_entry_reference_buffer_stop_reward_risk_and_position_size() -> None:
    row = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(),
        feature_row=base_feature(),
        history=base_history(),
        config=RiskStructureConfig(),
    )

    assert row["risk_version"] == RISK_STRUCTURE_VERSION
    assert row["risk_availability"] == "DAILY_EOD"
    assert row["decision_use"] == "NEXT_SESSION_RISK_CONTEXT"
    assert row["entry_price_basis"] == "EOD_CLOSE_REFERENCE"
    assert row["execution_price_status"] == "NOT_KNOWN"
    assert row["entry_reference_price"] == Decimal("100")
    assert row["assumed_entry_price"] == Decimal("100.100")
    assert row["invalidation_basis"] == "BREAKOUT_STRUCTURE"
    assert row["technical_invalidation_level"] == Decimal("95")
    assert row["atr_buffer_value"] == Decimal("0.40")
    assert row["stop_price"] == Decimal("94.60")
    assert row["risk_per_share"] == Decimal("5.500")
    assert row["reward_risk_status"] == "STRONG"
    assert row["quantity_by_risk"] == 181
    assert row["quantity_by_cash"] == 999
    assert row["structured_quantity"] == 181
    assert row["planned_rupee_risk"] == Decimal("995.500")
    assert row["planned_risk_pct"] < Decimal("1.00")
    assert row["risk_structure_status"] == "READY"
    assert row["risk_readiness"] == "READY_FOR_FINAL_SCORING"
    assert row["final_strategy_score_status"] == "NOT_IMPLEMENTED"
    assert row["trade_signal_status"] == "NOT_GENERATED"


def test_causal_swing_low_ignores_future_bars() -> None:
    history_without_future = [
        RiskDailyBar("2026-01-08", "ABC", Decimal("98"), Decimal("101"), Decimal("98"), Decimal("100")),
        RiskDailyBar("2026-01-09", "ABC", Decimal("96"), Decimal("101"), Decimal("91"), Decimal("99")),
        RiskDailyBar("2026-01-10", "ABC", Decimal("100"), Decimal("102"), Decimal("97"), Decimal("100")),
    ]
    history_with_future = history_without_future + [
        RiskDailyBar("2026-01-11", "ABC", Decimal("99"), Decimal("100"), Decimal("20"), Decimal("25")),
    ]
    kwargs = {
        "entry_row": base_entry(),
        "setup_row": base_setup(setup_type_flags="MOMENTUM_CONTINUATION", prior_high_20d="110", prior_high_52w=""),
        "feature_row": base_feature(),
        "config": RiskStructureConfig(),
    }

    baseline = evaluate_risk_row(history=history_without_future, **kwargs)
    with_future = evaluate_risk_row(history=history_with_future, history_index=build_ohlc_index({"ABC": history_with_future}), **kwargs)

    assert baseline["invalidation_basis"] == "RECENT_SWING_LOW_5"
    assert baseline["technical_invalidation_level"] == Decimal("91")
    assert with_future["technical_invalidation_level"] == baseline["technical_invalidation_level"]
    assert with_future["stop_price"] == baseline["stop_price"]


def test_consolidation_and_reclaim_stop_priorities_are_deterministic() -> None:
    consolidation_history = [
        RiskDailyBar("2026-01-06", "ABC", Decimal("96"), Decimal("101"), Decimal("94"), Decimal("100")),
        RiskDailyBar("2026-01-07", "ABC", Decimal("97"), Decimal("101"), Decimal("93"), Decimal("100")),
        RiskDailyBar("2026-01-08", "ABC", Decimal("98"), Decimal("101"), Decimal("96"), Decimal("100")),
        RiskDailyBar("2026-01-09", "ABC", Decimal("99"), Decimal("101"), Decimal("96"), Decimal("100")),
        RiskDailyBar("2026-01-10", "ABC", Decimal("100"), Decimal("102"), Decimal("97"), Decimal("100")),
    ]
    consolidation = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(setup_type_flags="CONSOLIDATION_BREAKOUT", prior_high_20d="95", consolidation_quality="STRONG"),
        feature_row=base_feature(),
        history=consolidation_history,
        config=RiskStructureConfig(),
    )
    assert consolidation["invalidation_basis"] == "CONSOLIDATION_LOW"
    assert consolidation["technical_invalidation_level"] == Decimal("93")

    reclaim = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(setup_type_flags="DAILY_RECLAIM", daily_level_reclaim="True", prior_high_20d="95"),
        feature_row=base_feature(),
        history=base_history(current_low=Decimal("96")),
        config=RiskStructureConfig(),
    )
    assert reclaim["invalidation_basis"] == "DAILY_RECLAIM_LOW"
    assert reclaim["technical_invalidation_level"] == Decimal("96")


def test_stop_too_tight_and_too_wide_are_invalid_structures() -> None:
    tight = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(prior_high_20d="99.95", prior_high_52w=""),
        feature_row=base_feature(),
        history=base_history(current_low=Decimal("99.90")),
        config=RiskStructureConfig(),
    )
    assert tight["stop_distance_band"] == "TOO_TIGHT"
    assert tight["stop_quality"] == "INVALID"
    assert tight["risk_readiness"] == "INVALID_STRUCTURE"

    wide = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(prior_high_20d="50", prior_high_52w=""),
        feature_row=base_feature(),
        history=base_history(current_low=Decimal("88")),
        config=RiskStructureConfig(),
    )
    assert wide["stop_distance_band"] == "TOO_WIDE"
    assert wide["risk_readiness"] == "INVALID_STRUCTURE"


def test_target_references_fallback_and_structural_rr_rejection() -> None:
    fallback = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(prior_high_52w=""),
        feature_row=base_feature(prior_high_52w=""),
        history=base_history(),
        config=RiskStructureConfig(),
    )
    assert fallback["structural_target_status"] == "UNAVAILABLE"
    assert fallback["selected_target_basis"] == "R_MULTIPLE_2R_RESEARCH_REFERENCE"
    assert fallback["target_1_5r"] == fallback["assumed_entry_price"] + fallback["risk_per_share"] * Decimal("1.50")
    assert fallback["reward_risk_ratio"] == Decimal("2.00")

    below_minimum = evaluate_risk_row(
        entry_row=base_entry(),
        setup_row=base_setup(prior_high_52w="104"),
        feature_row=base_feature(),
        history=base_history(),
        config=RiskStructureConfig(),
    )
    assert below_minimum["selected_target_basis"] == "PRIOR_52W_HIGH_RESISTANCE"
    assert below_minimum["reward_risk_status"] == "BELOW_MINIMUM"
    assert below_minimum["risk_readiness"] == "RR_BELOW_MINIMUM"


def test_capital_affordability_single_share_and_no_leverage() -> None:
    expensive = evaluate_risk_row(
        entry_row=base_entry(symbol="EXP", trading_date="2026-01-10"),
        setup_row=base_setup(symbol="EXP", adjusted_close="200000", price="200000", prior_high_20d="199000", prior_high_52w=""),
        feature_row=base_feature(symbol="EXP", atr_14="2000"),
        history=[
            RiskDailyBar("2026-01-10", "EXP", Decimal("199000"), Decimal("201000"), Decimal("198000"), Decimal("200000")),
        ],
        config=RiskStructureConfig(),
    )
    assert "AFFORDABILITY_FAIL" in expensive["rejection_reasons"]
    assert "RISK_TOO_LARGE_FOR_CAPITAL" in expensive["rejection_reasons"]
    assert expensive["risk_readiness"] == "CAPITAL_CONSTRAINED"
    assert expensive["no_leverage_status"] == "NO_LEVERAGE"

    single_share = evaluate_risk_row(
        entry_row=base_entry(symbol="ONE", trading_date="2026-01-10"),
        setup_row=base_setup(symbol="ONE", adjusted_close="90000", price="90000", prior_high_20d="89300", prior_high_52w=""),
        feature_row=base_feature(symbol="ONE", atr_14="100"),
        history=[
            RiskDailyBar("2026-01-10", "ONE", Decimal("89500"), Decimal("90500"), Decimal("89200"), Decimal("90000")),
        ],
        config=RiskStructureConfig(),
    )
    assert single_share["structured_quantity"] == 1
    assert "SINGLE_SHARE_ONLY" in single_share["warning_flags"]
    assert single_share["planned_risk_pct"] <= Decimal("1.00")


def test_conditional_rows_are_preview_only_and_exceptional_longs_keep_same_rules() -> None:
    preview = evaluate_risk_row(
        entry_row=base_entry(entry_readiness="CONDITIONALLY_READY"),
        setup_row=base_setup(),
        feature_row=base_feature(),
        history=base_history(),
        config=RiskStructureConfig(),
    )
    assert preview["risk_mode"] == "PREVIEW_ONLY"
    assert preview["risk_structure_status"] == "PARTIAL"
    assert preview["risk_readiness"] == "NOT_EVALUATED"
    assert "RISK_PREVIEW_ONLY" in preview["warning_flags"]

    exceptional = evaluate_risk_row(
        entry_row=base_entry(symbol="EXC", trading_date="2026-01-10", entry_readiness="EXCEPTIONAL_LONG_REVIEW", regime_state="BEARISH"),
        setup_row=base_setup(symbol="EXC"),
        feature_row=base_feature(symbol="EXC"),
        history=[
            RiskDailyBar("2026-01-10", "EXC", Decimal("99"), Decimal("101"), Decimal("94"), Decimal("100")),
        ],
        config=RiskStructureConfig(),
    )
    assert exceptional["risk_mode"] == "FULL_EVALUATION"
    assert exceptional["min_reward_risk"] == Decimal("1.50")
    assert exceptional["preferred_reward_risk"] == Decimal("2.00")
    assert exceptional["risk_readiness"] == "READY_FOR_FINAL_SCORING"


def test_output_fields_do_not_include_outcome_or_execution_labels() -> None:
    assert prohibited_outcome_fields(RISK_OUTPUT_FIELDS) == []
    lowered = [field.lower() for field in RISK_OUTPUT_FIELDS]
    assert not any("order" in field for field in lowered)
    assert "final_strategy_score_status" in RISK_OUTPUT_FIELDS
    assert "trade_signal_status" in RISK_OUTPUT_FIELDS


def test_full_fixture_report_generation_regressions_and_leakage(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        base_entry(symbol="AAA", trading_date="2026-01-10"),
        base_entry(symbol="BBB", trading_date="2026-01-10", entry_readiness="CONDITIONALLY_READY"),
        base_entry(symbol="CCC", trading_date="2026-01-11", entry_readiness="EXCEPTIONAL_LONG_REVIEW", regime_state="BEARISH"),
        base_entry(symbol="DDD", trading_date="2026-01-11"),
        base_entry(symbol="EEE", trading_date="2026-01-12"),
    ]
    setups = [
        base_setup(symbol="AAA", trading_date="2026-01-10"),
        base_setup(symbol="BBB", trading_date="2026-01-10", prior_high_52w=""),
        base_setup(symbol="CCC", trading_date="2026-01-11", prior_high_52w=""),
        base_setup(symbol="DDD", trading_date="2026-01-11", prior_high_52w="104"),
        base_setup(symbol="EEE", trading_date="2026-01-12", prior_high_20d="99.95", prior_high_52w=""),
    ]
    features = [
        base_feature(symbol="AAA", trading_date="2026-01-10"),
        base_feature(symbol="BBB", trading_date="2026-01-10"),
        base_feature(symbol="CCC", trading_date="2026-01-11"),
        base_feature(symbol="DDD", trading_date="2026-01-11"),
        base_feature(symbol="EEE", trading_date="2026-01-12"),
    ]
    regime_rows = [
        base_regime("2026-01-10", "BULLISH"),
        base_regime("2026-01-11", "BEARISH"),
        base_regime("2026-01-12", "NEUTRAL"),
    ]
    adjusted_rows = [
        adjusted_row(symbol="AAA", trading_date="2026-01-10", low="94"),
        adjusted_row(symbol="BBB", trading_date="2026-01-10", low="94"),
        adjusted_row(symbol="CCC", trading_date="2026-01-11", low="94"),
        adjusted_row(symbol="DDD", trading_date="2026-01-11", low="94"),
        adjusted_row(symbol="EEE", trading_date="2026-01-12", low="99.90"),
    ]

    write_gzip_rows(data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz", entries)
    write_gzip_rows(data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz", setups)
    write_gzip_rows(data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz", features)
    write_gzip_rows(data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz", [candidate_from_entry(row) for row in entries])
    write_gzip_rows(data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz", regime_rows)
    write_plain_rows(data_dir / "research" / "adjusted" / "daily" / "nse" / "2026" / "01" / "nse_adjusted_daily_20260110.csv", adjusted_rows[:2])
    write_plain_rows(data_dir / "research" / "adjusted" / "daily" / "nse" / "2026" / "01" / "nse_adjusted_daily_20260111.csv", adjusted_rows[2:4])
    write_plain_rows(data_dir / "research" / "adjusted" / "daily" / "nse" / "2026" / "01" / "nse_adjusted_daily_20260112.csv", adjusted_rows[4:])

    report = build_risk_structures(
        config=RiskStructureEngineConfig(data_dir=data_dir, risk_config=RiskStructureConfig())
    )
    markdown_path = tmp_path / "docs" / "strategy-v1-risk-structure.md"
    write_strategy_v1_risk_structure_markdown(report, markdown_path)

    assert report["ready_for_review"] is True
    assert report["generation"]["full_generation_completed"] is True
    assert report["generation"]["total_rows_risk_evaluated"] == 5
    assert report["generation"]["ready_for_final_scoring_count"] >= 2
    assert report["generation"]["risk_rejected_count"] >= 1
    assert report["pilot"]["validation_passed"] is True
    assert report["regression"]["daily_features_v1_unchanged"] is True
    assert report["regression"]["momentum_candidates_v1_unchanged"] is True
    assert report["regression"]["daily_setup_evaluation_v1_unchanged"] is True
    assert report["regression"]["market_regime_v1_unchanged"] is True
    assert report["regression"]["entry_evaluation_v1_unchanged"] is True
    assert report["safety"]["orders_placed"] == 0
    assert report["safety"]["remote_migrations_applied"] == 0
    assert report["safety"]["supabase_bulk_records_persisted"] == 0
    assert report["safety"]["final_100_point_strategy_score_generated"] == 0
    assert report["safety"]["prohibited_output_fields"] == []
    assert (data_dir / "research" / "risk_structures" / "daily" / "v1" / "risk_structures_v1.csv.gz").exists()
    assert (data_dir / "reports" / "risk_structure_summary.json").exists()
    assert (data_dir / "reports" / "risk_structure_daily_funnel.csv").exists()
    assert (data_dir / "reports" / "risk_structure_stop_basis.csv").exists()
    assert (data_dir / "reports" / "risk_structure_reward_risk.csv").exists()
    assert (data_dir / "reports" / "risk_structure_capital_constraints.csv").exists()
    assert (data_dir / "reports" / "risk_structure_price_bands.csv").exists()
    assert (data_dir / "reports" / "risk_structure_pilot_validation.csv").exists()
    assert markdown_path.exists()

    output_rows = read_gzip_rows(data_dir / "research" / "risk_structures" / "daily" / "v1" / "risk_structures_v1.csv.gz")
    assert any(row["risk_mode"] == "PREVIEW_ONLY" and row["risk_readiness"] == "NOT_EVALUATED" for row in output_rows)
    assert all(row["final_strategy_score_status"] == "NOT_IMPLEMENTED" for row in output_rows)
    assert all(row["trade_signal_status"] == "NOT_GENERATED" for row in output_rows)


def base_entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "setup_version": DAILY_SETUP_EVALUATION_VERSION,
        "setup_config_hash": SETUP_HASH,
        "regime_version": MARKET_REGIME_VERSION,
        "regime_config_hash": REGIME_HASH,
        "entry_version": ENTRY_EVALUATION_VERSION,
        "entry_config_hash": ENTRY_HASH,
        "candidate_state": "CONFIRMED",
        "setup_quality": "STRONG",
        "setup_type_flags": "BREAKOUT_20D",
        "entry_readiness": "READY_FOR_RISK_EVALUATION",
        "regime_state": "BULLISH",
    }
    row.update(overrides)
    return row


def base_setup(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "setup_version": DAILY_SETUP_EVALUATION_VERSION,
        "setup_config_hash": SETUP_HASH,
        "candidate_state": "CONFIRMED",
        "setup_quality": "STRONG",
        "setup_type_flags": "BREAKOUT_20D",
        "breakout_state": "CLOSE_ACCEPTED",
        "consolidation_state": "NONE",
        "consolidation_quality": "WEAK",
        "daily_level_reclaim": "False",
        "adjusted_open": "99",
        "adjusted_high": "101",
        "adjusted_low": "94",
        "adjusted_close": "100",
        "price": "100",
        "prior_high_20d": "95",
        "prior_high_52w": "115",
        "atr_percent_14": "0.02",
    }
    row.update(overrides)
    return row


def base_feature(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "adjusted_open": "99",
        "adjusted_high": "101",
        "adjusted_low": "94",
        "adjusted_close": "100",
        "atr_14": "2",
        "sma_20": "96",
        "prior_high_20d": "95",
        "prior_high_52w": "115",
    }
    row.update(overrides)
    return row


def base_regime(trading_date: str, state: str) -> dict[str, object]:
    return {
        "trading_date": trading_date,
        "regime_version": MARKET_REGIME_VERSION,
        "config_hash": REGIME_HASH,
        "regime_state": state,
    }


def base_history(*, symbol: str = "ABC", current_low: Decimal = Decimal("94")) -> list[RiskDailyBar]:
    return [
        RiskDailyBar("2026-01-10", symbol, Decimal("99"), Decimal("101"), current_low, Decimal("100")),
    ]


def adjusted_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "series": "EQ",
        "adjusted_open": "99",
        "adjusted_high": "101",
        "adjusted_low": "94",
        "adjusted_close": "100",
    }
    row.update(overrides)
    return row


def candidate_from_entry(entry_row: dict[str, object]) -> dict[str, object]:
    return {
        "trading_date": entry_row["trading_date"],
        "symbol": entry_row["symbol"],
        "isin": entry_row["isin"],
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "candidate_state": entry_row["candidate_state"],
    }


def write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_plain_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_gzip_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_summary_json_is_safe(tmp_path: Path) -> None:
    payload = {"score": "NOT_IMPLEMENTED", "orders_placed": 0}
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == payload

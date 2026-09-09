from __future__ import annotations

import csv
import gzip
import json
from decimal import Decimal
from pathlib import Path

from app.regime.regime_config import MARKET_REGIME_VERSION, MarketRegimeConfig
from app.risk.risk_config import RISK_STRUCTURE_VERSION, RiskStructureConfig
from app.risk.risk_structure_audit import (
    RISK_STRUCTURE_AUDIT_VERSION,
    RiskStructureAuditConfig,
    build_risk_structure_audit,
    prohibited_audit_fields,
    setup_specific_first_priority,
    swing_low_comparison,
    target_semantics_audit,
    write_strategy_v1_risk_structure_audit_markdown,
)
from app.risk.risk_structurer import evaluate_risk_row
from app.risk.stop_placement import RiskDailyBar
from app.strategy.candidate_config import MOMENTUM_CANDIDATES_VERSION, MomentumCandidateConfig
from app.strategy.entry_config import ENTRY_EVALUATION_VERSION, EntryEvaluationConfig
from app.strategy.momentum_candidates import file_sha256
from app.strategy.setup_config import DAILY_SETUP_EVALUATION_VERSION, DailySetupEvaluationConfig

CANDIDATE_HASH = MomentumCandidateConfig().config_hash()
SETUP_HASH = DailySetupEvaluationConfig().config_hash()
REGIME_HASH = MarketRegimeConfig().config_hash()
ENTRY_HASH = EntryEvaluationConfig().config_hash()


def test_setup_specific_first_priority_prefers_specific_structures() -> None:
    assert setup_specific_first_priority({"setup_type_flags": "CONSOLIDATION_BREAKOUT"})[0] == "CONSOLIDATION_LOW"
    assert setup_specific_first_priority({"daily_level_reclaim": "True"})[0] == "DAILY_RECLAIM_LOW"
    assert setup_specific_first_priority({"setup_type_flags": "BREAKOUT_20D"})[0] == "BREAKOUT_STRUCTURE"
    assert setup_specific_first_priority({"setup_type_flags": "MOMENTUM_CONTINUATION"})[0] == "RECENT_SWING_LOW_5"


def test_target_semantics_detects_no_2r_replacement_with_structural_target() -> None:
    rows = [
        risk_row("AAA", structural_status="AVAILABLE", selected_basis="PRIOR_52W_HIGH_RESISTANCE", rr="0.8", readiness="RR_BELOW_MINIMUM"),
        risk_row("BBB", structural_status="UNAVAILABLE", selected_basis="R_MULTIPLE_2R_RESEARCH_REFERENCE", rr="2.0", readiness="READY_FOR_FINAL_SCORING"),
    ]
    _, summary = target_semantics_audit(rows)
    assert summary["structural_target_available_count"] == 1
    assert summary["fallback_2r_count"] == 1
    assert summary["fallback_semantic_violations"] == 0
    assert summary["structural_target_below_minimum_count"] == 1
    assert summary["structural_target_below_minimum_not_rejected"] == 0


def test_swing_low_comparison_counts_equalities() -> None:
    rows = [
        candidate_detail("AAA", "RECENT_SWING_LOW_3", "95", "5"),
        candidate_detail("AAA", "RECENT_SWING_LOW_5", "95", "5"),
        candidate_detail("AAA", "RECENT_SWING_LOW_10", "90", "10"),
        candidate_detail("BBB", "RECENT_SWING_LOW_3", "92", "8"),
        candidate_detail("BBB", "RECENT_SWING_LOW_5", "92", "8"),
        candidate_detail("BBB", "RECENT_SWING_LOW_10", "92", "8"),
    ]
    summary = swing_low_comparison(rows)
    assert summary["rows_with_all_three"] == 2
    assert summary["five_equals_three_count"] == 2
    assert summary["five_equals_ten_count"] == 1
    assert summary["all_three_identical_count"] == 1


def test_build_risk_structure_audit_reports_and_preserves_baselines(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries, setups, features, regimes, risk_rows = fixture_rows()
    write_gzip_rows(data_dir / "research" / "entry_evaluations" / "daily" / "v1" / "entry_evaluations_v1.csv.gz", entries)
    write_gzip_rows(data_dir / "research" / "setups" / "daily" / "v1" / "daily_setup_evaluations_v1.csv.gz", setups)
    write_gzip_rows(data_dir / "research" / "features" / "daily" / "v1" / "daily_features_v1.csv.gz", features)
    write_gzip_rows(data_dir / "research" / "candidates" / "daily" / "v1" / "momentum_candidates_v1.csv.gz", [candidate_from_entry(row) for row in entries])
    write_gzip_rows(data_dir / "research" / "regime" / "daily" / "v1" / "market_regime_daily_v1.csv.gz", regimes)
    write_gzip_rows(data_dir / "research" / "risk_structures" / "daily" / "v1" / "risk_structures_v1.csv.gz", risk_rows)
    write_plain_rows(
        data_dir / "research" / "adjusted" / "daily" / "nse" / "2026" / "01" / "nse_adjusted_daily_20260110.csv",
        [adjusted_row(symbol=row["symbol"], trading_date=row["trading_date"], low=row["adjusted_low"]) for row in setups],
    )
    before_hash = file_sha256(data_dir / "research" / "risk_structures" / "daily" / "v1" / "risk_structures_v1.csv.gz")

    report = build_risk_structure_audit(config=RiskStructureAuditConfig(data_dir=data_dir))
    markdown_path = tmp_path / "docs" / "strategy-v1-risk-structure-audit.md"
    write_strategy_v1_risk_structure_audit_markdown(report, markdown_path)
    after_hash = file_sha256(data_dir / "research" / "risk_structures" / "daily" / "v1" / "risk_structures_v1.csv.gz")

    assert report["audit_version"] == RISK_STRUCTURE_AUDIT_VERSION
    assert report["risk"]["risk_version"] == RISK_STRUCTURE_VERSION
    assert report["ready_for_review"] is True
    assert report["regression"]["risk_structure_v1_unchanged"] is True
    assert before_hash == after_hash
    assert report["target_audit"]["fallback_semantic_violations"] == 0
    assert report["invariants"]["capital_risk_violations"] == []
    assert report["invariants"]["conditional_preview_violations"] == []
    assert "SETUP_SPECIFIC_FIRST" in report["sensitivity"]["scenarios"]
    assert "ALWAYS_2R_REFERENCE" in report["sensitivity"]["scenarios"]
    assert (data_dir / "reports" / "risk_structure_audit_summary.json").exists()
    assert (data_dir / "reports" / "risk_structure_stop_candidates.csv").exists()
    assert (data_dir / "reports" / "risk_structure_stop_basis_audit.csv").exists()
    assert (data_dir / "reports" / "risk_structure_target_semantics.csv").exists()
    assert (data_dir / "reports" / "risk_structure_rr_failure_causes.csv").exists()
    assert (data_dir / "reports" / "risk_structure_capital_audit.csv").exists()
    assert (data_dir / "reports" / "risk_structure_sensitivity.csv").exists()
    assert (data_dir / "reports" / "risk_structure_risk_too_large_cases.csv").exists()
    assert (data_dir / "reports" / "risk_structure_single_share_cases.csv").exists()
    assert (data_dir / "research" / "audits" / "risk_structure" / "v1" / "risk_structure_stop_candidate_inventory.csv.gz").exists()
    assert markdown_path.exists()
    assert prohibited_audit_fields() == []
    assert json.loads((data_dir / "reports" / "risk_structure_audit_summary.json").read_text(encoding="utf-8"))["audit_version"] == RISK_STRUCTURE_AUDIT_VERSION


def fixture_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    entries = [
        base_entry(symbol="AAA"),
        base_entry(symbol="BBB", entry_readiness="CONDITIONALLY_READY"),
        base_entry(symbol="CCC"),
        base_entry(symbol="DDD", regime_state="BEARISH", entry_readiness="EXCEPTIONAL_LONG_REVIEW"),
    ]
    setups = [
        base_setup(symbol="AAA", setup_type_flags="BREAKOUT_20D;MOMENTUM_CONTINUATION", prior_high_20d="95", adjusted_low="94"),
        base_setup(symbol="BBB", setup_type_flags="CONSOLIDATION_BREAKOUT", consolidation_quality="STRONG", prior_high_20d="96", prior_high_52w="", adjusted_low="93"),
        base_setup(symbol="CCC", setup_type_flags="BREAKOUT_20D", prior_high_20d="95", prior_high_52w="104", adjusted_low="94"),
        base_setup(symbol="DDD", setup_type_flags="DAILY_RECLAIM", daily_level_reclaim="True", prior_high_20d="95", prior_high_52w="", adjusted_low="96"),
    ]
    features = [base_feature(symbol=row["symbol"], prior_high_20d=row["prior_high_20d"], prior_high_52w=row["prior_high_52w"]) for row in setups]
    regimes = [base_regime("2026-01-10", "BULLISH")]
    histories = {
        row["symbol"]: [
            RiskDailyBar("2026-01-06", str(row["symbol"]), Decimal("97"), Decimal("101"), Decimal("93"), Decimal("99")),
            RiskDailyBar("2026-01-07", str(row["symbol"]), Decimal("98"), Decimal("101"), Decimal("94"), Decimal("99")),
            RiskDailyBar("2026-01-08", str(row["symbol"]), Decimal("99"), Decimal("101"), Decimal("95"), Decimal("100")),
            RiskDailyBar("2026-01-09", str(row["symbol"]), Decimal("99"), Decimal("101"), Decimal("96"), Decimal("100")),
            RiskDailyBar("2026-01-10", str(row["symbol"]), Decimal("99"), Decimal("101"), Decimal(str(row["adjusted_low"])), Decimal("100")),
        ]
        for row in setups
    }
    risk_rows = [
        evaluate_risk_row(
            entry_row=entry,
            setup_row=setup,
            feature_row=feature,
            history=histories[str(entry["symbol"])],
            config=RiskStructureConfig(),
        )
        for entry, setup, feature in zip(entries, setups, features, strict=True)
    ]
    return entries, setups, features, regimes, risk_rows


def base_entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "AAA",
        "isin": "INEAAA",
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
        "symbol": "AAA",
        "isin": "INEAAA",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": MOMENTUM_CANDIDATES_VERSION,
        "candidate_config_hash": CANDIDATE_HASH,
        "setup_version": DAILY_SETUP_EVALUATION_VERSION,
        "setup_config_hash": SETUP_HASH,
        "candidate_state": "CONFIRMED",
        "setup_quality": "STRONG",
        "setup_type_flags": "BREAKOUT_20D",
        "breakout_state": "CLOSE_ACCEPTED",
        "consolidation_state": "TIGHT",
        "consolidation_quality": "GOOD",
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
        "symbol": "AAA",
        "isin": "INEAAA",
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


def risk_row(symbol: str, *, structural_status: str, selected_basis: str, rr: str, readiness: str) -> dict[str, object]:
    return {
        "trading_date": "2026-01-10",
        "symbol": symbol,
        "structural_target_status": structural_status,
        "selected_target_basis": selected_basis,
        "structural_target_price": "104",
        "assumed_entry_price": "100",
        "risk_per_share": "5",
        "reward_risk_ratio": rr,
        "reward_risk_status": "BELOW_MINIMUM" if Decimal(rr) < Decimal("1.5") else "GOOD",
        "risk_readiness": readiness,
        "risk_mode": "FULL_EVALUATION",
    }


def candidate_detail(symbol: str, basis: str, level: str, distance: str) -> dict[str, object]:
    return {
        "trading_date": "2026-01-10",
        "symbol": symbol,
        "candidate_basis": basis,
        "level": Decimal(level),
        "candidate_stop_distance_pct": distance,
        "candidate_stop_distance_atr": distance,
    }


def adjusted_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "AAA",
        "isin": "INEAAA",
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

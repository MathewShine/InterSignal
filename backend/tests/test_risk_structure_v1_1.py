from __future__ import annotations

import csv
import gzip
from decimal import Decimal

from app.risk.risk_config import (
    RISK_STRUCTURE_V1_CONFIG_HASH,
    RISK_STRUCTURE_V1_1_VERSION,
    RISK_STRUCTURE_VERSION,
    SETUP_SPECIFIC_FIRST_METHODOLOGY,
    RiskStructureConfig,
    RiskStructureV11Config,
)
from app.risk.risk_structure_v1_1 import (
    RISK_V11_OUTPUT_FIELDS,
    capital_regression,
    comparison_pairs,
    comparison_summary,
    final_ready_invariant_violations,
    prohibited_outcome_fields,
    target_regression,
    write_v11_rows,
)
from app.risk.risk_structurer import evaluate_risk_row
from app.risk.stop_placement import RiskDailyBar, build_ohlc_index, priority_for_setup


def test_version_is_explicit_and_v1_hash_is_unchanged() -> None:
    old = RiskStructureConfig()
    new = RiskStructureV11Config()

    assert old.risk_version == RISK_STRUCTURE_VERSION
    assert old.config_hash() == RISK_STRUCTURE_V1_CONFIG_HASH
    assert new.risk_version == RISK_STRUCTURE_V1_1_VERSION
    assert new.config_hash() != old.config_hash()
    assert new.previous_risk_version == RISK_STRUCTURE_VERSION
    assert new.previous_risk_config_hash == RISK_STRUCTURE_V1_CONFIG_HASH


def test_explicit_multi_flag_priority_is_setup_specific_first() -> None:
    setup = base_setup(
        setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION",
        daily_level_reclaim="True",
    )

    assert priority_for_setup(setup, RiskStructureV11Config())[:6] == (
        "CONSOLIDATION_LOW",
        "DAILY_RECLAIM_LOW",
        "BREAKOUT_STRUCTURE",
        "RECENT_SWING_LOW_5",
        "RECENT_SWING_LOW_10",
        "RECENT_SWING_LOW_3",
    )


def test_consolidation_beats_momentum_when_valid() -> None:
    old = evaluate(setup=base_setup(setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION"), config=RiskStructureConfig())
    new = evaluate(setup=base_setup(setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION"))

    assert old["invalidation_basis"] == "RECENT_SWING_LOW_5"
    assert new["invalidation_basis"] == "CONSOLIDATION_LOW"
    assert new["selected_stop_priority_reason"] == "CONSOLIDATION_BREAKOUT_VALID"
    assert new["setup_specific_stop_valid"] is True


def test_reclaim_beats_momentum_when_valid() -> None:
    row = evaluate(
        setup=base_setup(
            setup_type_flags="BREAKOUT_20D;MOMENTUM_CONTINUATION",
            daily_level_reclaim="True",
            consolidation_quality="WEAK",
            consolidation_state="NONE",
        ),
        history=base_history(current_low=Decimal("96")),
    )

    assert row["invalidation_basis"] == "DAILY_RECLAIM_LOW"
    assert row["selected_stop_priority_reason"] == "DAILY_RECLAIM_VALID"


def test_breakout_beats_momentum_when_valid() -> None:
    row = evaluate(
        setup=base_setup(
            setup_type_flags="BREAKOUT_20D;MOMENTUM_CONTINUATION",
            consolidation_quality="WEAK",
            consolidation_state="NONE",
            prior_high_20d="95",
        )
    )

    assert row["invalidation_basis"] == "BREAKOUT_STRUCTURE"
    assert row["selected_stop_priority_reason"] == "BREAKOUT_STRUCTURE_VALID"


def test_invalid_breakout_falls_back_to_valid_swing_support() -> None:
    row = evaluate(
        setup=base_setup(
            setup_type_flags="BREAKOUT_20D;MOMENTUM_CONTINUATION",
            consolidation_quality="WEAK",
            consolidation_state="NONE",
            prior_high_20d="99.95",
        )
    )

    assert row["invalidation_basis"] == "RECENT_SWING_LOW_5"
    assert row["fallback_stop_used"] is True
    assert row["fallback_reason"] == "SETUP_SPECIFIC_STRUCTURE_INVALID"
    assert row["stop_valid"] is True


def test_continuation_only_keeps_swing_fallback() -> None:
    row = evaluate(
        setup=base_setup(
            setup_type_flags="MOMENTUM_CONTINUATION",
            prior_high_20d="",
            consolidation_quality="WEAK",
            consolidation_state="NONE",
        )
    )

    assert row["invalidation_basis"] == "RECENT_SWING_LOW_5"
    assert row["selected_stop_priority_reason"] == "MOMENTUM_CONTINUATION_SWING_SUPPORT"
    assert row["fallback_stop_used"] is False


def test_buffers_targets_rr_and_capital_rules_are_unchanged() -> None:
    config = RiskStructureV11Config()
    below_minimum = evaluate(setup=base_setup(prior_high_52w="103"), config=config)
    fallback = evaluate(setup=base_setup(prior_high_52w=""), feature=base_feature(prior_high_52w=""), config=config)

    assert config.stop.atr_buffer_multiple == Decimal("0.20")
    assert config.entry.long_entry_buffer_pct == Decimal("0.10")
    assert config.target.minimum_reward_risk == Decimal("1.50")
    assert config.target.preferred_reward_risk == Decimal("2.00")
    assert config.capital.research_capital_rupees == Decimal("100000")
    assert config.capital.max_risk_per_trade_pct == Decimal("1.00")
    assert below_minimum["selected_target_basis"] == "PRIOR_52W_HIGH_RESISTANCE"
    assert below_minimum["risk_readiness"] == "RR_BELOW_MINIMUM"
    assert fallback["selected_target_basis"] == "R_MULTIPLE_2R_RESEARCH_REFERENCE"
    assert fallback["planned_risk_pct"] <= Decimal("1.00")
    assert fallback["whole_share_status"] == "WHOLE_SHARES_ONLY"
    assert fallback["no_leverage_status"] == "NO_LEVERAGE"


def test_conditional_preview_and_exceptional_long_invariants() -> None:
    preview = evaluate(entry=base_entry(entry_readiness="CONDITIONALLY_READY"))
    exceptional = evaluate(entry=base_entry(entry_readiness="EXCEPTIONAL_LONG_REVIEW", regime_state="BEARISH"))

    assert preview["risk_mode"] == "PREVIEW_ONLY"
    assert preview["risk_readiness"] == "NOT_EVALUATED"
    assert exceptional["risk_mode"] == "FULL_EVALUATION"
    assert exceptional["min_reward_risk"] == Decimal("1.50")
    assert exceptional["max_risk_per_trade_pct"] == Decimal("1.00")


def test_future_bar_does_not_change_current_risk_structure() -> None:
    history = base_history()
    future = history + [RiskDailyBar("2026-01-11", "ABC", Decimal("20"), Decimal("21"), Decimal("1"), Decimal("2"))]
    kwargs = {
        "entry_row": base_entry(),
        "setup_row": base_setup(setup_type_flags="MOMENTUM_CONTINUATION", prior_high_20d=""),
        "feature_row": base_feature(prior_high_20d=""),
        "config": RiskStructureV11Config(),
    }

    baseline = evaluate_risk_row(history=history, **kwargs)
    changed_future = evaluate_risk_row(history=future, history_index=build_ohlc_index({"ABC": future}), **kwargs)

    assert changed_future["stop_price"] == baseline["stop_price"]
    assert changed_future["selected_target_price"] == baseline["selected_target_price"]
    assert changed_future["structured_quantity"] == baseline["structured_quantity"]


def test_comparison_regressions_and_v11_report_dataset_generation(tmp_path) -> None:
    old = evaluate(config=RiskStructureConfig(), setup=base_setup(setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION"))
    new = evaluate(setup=base_setup(setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION"))
    setup_lookup = {(new["trading_date"], new["symbol"]): base_setup(setup_type_flags="BREAKOUT_20D;CONSOLIDATION_BREAKOUT;MOMENTUM_CONTINUATION")}
    pairs = comparison_pairs([old], [new], setup_lookup)
    target_rows, target = target_regression([old], [new])
    capital_rows, capital = capital_regression([old], [new], RiskStructureV11Config())

    old_path = tmp_path / "risk_v1.csv.gz"
    with gzip.open(old_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(old))
        writer.writeheader()
        writer.writerow(old)
    old_bytes = old_path.read_bytes()
    new_path = tmp_path / "risk_v1_1.csv.gz"
    write_v11_rows(new_path, [new])

    assert comparison_summary(pairs)["changed_stop_basis"] == 1
    assert target["result"] == "UNCHANGED_AND_VALID"
    assert capital["result"] == "UNCHANGED_AND_VALID"
    assert all(row["result"] == "PASS" for row in target_rows + capital_rows)
    assert final_ready_invariant_violations([new], RiskStructureV11Config()) == []
    assert old_path.read_bytes() == old_bytes
    assert new_path.exists()
    with gzip.open(new_path, "rt", encoding="utf-8", newline="") as handle:
        written = next(csv.DictReader(handle))
    assert written["risk_version"] == RISK_STRUCTURE_V1_1_VERSION
    assert written["stop_selection_methodology"] == SETUP_SPECIFIC_FIRST_METHODOLOGY


def test_v11_fields_contain_no_outcome_or_execution_data() -> None:
    assert prohibited_outcome_fields(RISK_V11_OUTPUT_FIELDS) == []
    assert not any("order" in field.lower() for field in RISK_V11_OUTPUT_FIELDS)


def evaluate(
    *,
    entry: dict[str, object] | None = None,
    setup: dict[str, object] | None = None,
    feature: dict[str, object] | None = None,
    history: list[RiskDailyBar] | None = None,
    config: RiskStructureConfig | None = None,
) -> dict[str, object]:
    return evaluate_risk_row(
        entry_row=entry or base_entry(),
        setup_row=setup or base_setup(),
        feature_row=feature or base_feature(),
        history=history or base_history(),
        config=config or RiskStructureV11Config(),
    )


def base_entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "isin": "INEABC",
        "feature_version": "DAILY_FEATURES_V1",
        "candidate_version": "MOMENTUM_CANDIDATES_V1",
        "candidate_config_hash": "candidate-hash",
        "setup_version": "DAILY_SETUP_EVALUATION_V1",
        "setup_config_hash": "setup-hash",
        "regime_version": "MARKET_REGIME_V1",
        "regime_config_hash": "regime-hash",
        "entry_version": "ENTRY_EVALUATION_V1",
        "entry_config_hash": "entry-hash",
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
        "setup_type_flags": "BREAKOUT_20D",
        "setup_quality": "STRONG",
        "consolidation_state": "TIGHT",
        "consolidation_quality": "GOOD",
        "daily_level_reclaim": "False",
        "adjusted_open": "99",
        "adjusted_high": "101",
        "adjusted_low": "97",
        "adjusted_close": "100",
        "price": "100",
        "prior_high_20d": "95",
        "prior_high_52w": "115",
    }
    row.update(overrides)
    return row


def base_feature(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trading_date": "2026-01-10",
        "symbol": "ABC",
        "adjusted_open": "99",
        "adjusted_high": "101",
        "adjusted_low": "97",
        "adjusted_close": "100",
        "atr_14": "2",
        "sma_20": "96",
        "prior_high_20d": "95",
        "prior_high_52w": "115",
    }
    row.update(overrides)
    return row


def base_history(*, current_low: Decimal = Decimal("97")) -> list[RiskDailyBar]:
    return [
        RiskDailyBar("2026-01-06", "ABC", Decimal("98"), Decimal("101"), Decimal("93"), Decimal("99")),
        RiskDailyBar("2026-01-07", "ABC", Decimal("98"), Decimal("101"), Decimal("94"), Decimal("99")),
        RiskDailyBar("2026-01-08", "ABC", Decimal("99"), Decimal("101"), Decimal("95"), Decimal("100")),
        RiskDailyBar("2026-01-09", "ABC", Decimal("99"), Decimal("101"), Decimal("96"), Decimal("100")),
        RiskDailyBar("2026-01-10", "ABC", Decimal("100"), Decimal("102"), current_low, Decimal("100")),
    ]

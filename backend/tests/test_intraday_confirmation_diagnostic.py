from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.confirmation_diagnostic import (
    CLASSIFICATION_RULES,
    DIAGNOSTIC_VERSION,
    EXPERIMENT_IDS,
    FAMILY,
    PRICE_DRIFT_BUCKETS,
    PROFILE,
    REPORT_FILENAMES,
    RR_BUCKETS,
    WINDOWS,
    _path_metrics,
    _price_basis_scale,
    _prereg_baseline_dependency,
    _scale_bars,
    _write_csv,
    _write_json,
    build_preregistration,
    confirmation_feasibility,
    confirmation_reference,
    confirmation_rr,
    early_path_classification,
    freeze_population,
    opening_range_classification,
    preconfirmation_touch_state,
    price_drift_bucket,
    rr_bucket,
    sample_safety,
    validate_development_only,
    vwap_classification,
    window_profile,
)
from app.research.intraday.models import CanonicalIntradayBar
from app.research.temporal_validation.config import SEALED, canonical_hash, json_ready
from app.research.temporal_validation.guard import ValidationAccessError


IST = timezone(timedelta(hours=5, minutes=30))


def bar(
    sequence: int,
    *,
    interval: str = "5m",
    minutes: int = 5,
    open_: str = "100",
    high: str = "101",
    low: str = "99",
    close: str = "100.5",
    volume: int = 100,
    source_count: int = 1,
) -> CanonicalIntradayBar:
    start = datetime(2024, 1, 2, 9, 15, tzinfo=IST) + timedelta(
        minutes=(sequence - 1) * minutes
    )
    return CanonicalIntradayBar(
        instrument_id="1",
        symbol="TEST",
        isin="INE000000001",
        exchange="NSE",
        trading_date=date(2024, 1, 2),
        interval=interval,
        bar_start=start,
        bar_end=start + timedelta(minutes=minutes),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        source_provider=("GROWW_OFFICIAL_API" if interval == "5m" else "DERIVED_FROM_NORMALIZED_5M"),
        source_interval="5m",
        source_timestamp=start,
        ingested_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
        normalization_version="NSE_CASH_INTRADAY_5M_V1",
        session_id="NSE:2024-01-02",
        session_sequence=sequence,
        source_bar_count=source_count,
    )


def population_row(opportunity_id: str = "2024-01-01|TEST") -> dict[str, object]:
    return {
        "opportunity_id": opportunity_id,
        "symbol": "TEST",
        "decision_date": opportunity_id.split("|")[0],
        "entry_date": "2024-01-02",
        "score": 84,
        "candidate_stage": "BOTH_ELIGIBLE",
        "setup_quality": "STRONG",
        "regime_state": "BULLISH",
        "frozen_next_open": Decimal("100"),
        "frozen_stop": Decimal("95"),
        "frozen_target": Decimal("110"),
        "frozen_effective_rr": Decimal("2"),
        "intraday_quality": "USABLE_STRICT_FULL_PATH",
        "CA_safety": "SAFE",
        "population_group": "SOURCE_COVERED_STRICT_ONLY",
        "is_admitted": False,
    }


def test_contract_identity_and_exact_experiment_set() -> None:
    assert DIAGNOSTIC_VERSION == "INTRADAY_CONFIRMATION_DIAGNOSTIC_V1"
    assert PROFILE == "DEVELOPMENT_INTRADAY_CONFIRMATION_V1"
    assert FAMILY == "INTRADAY_CONFIRMATION_DIAGNOSTIC"
    assert WINDOWS == (5, 10, 15)
    assert EXPERIMENT_IDS == tuple(f"EXP-INTRACONF-{index:03d}" for index in range(1, 11))


def test_development_only_scope_accepts_development() -> None:
    result = validate_development_only((date(2022, 1, 3), date(2024, 12, 31)))
    assert result["validation_state"] == SEALED
    assert result["performance_accessed"] is False


@pytest.mark.parametrize("value", [date(2025, 1, 1), date(2026, 1, 2), date(2021, 12, 31)])
def test_development_only_scope_rejects_every_outside_date(value: date) -> None:
    with pytest.raises(ValidationAccessError, match="development-window only"):
        validate_development_only((value,))


def test_population_freeze_is_order_independent_and_deterministic() -> None:
    first = population_row("2024-01-01|TEST")
    second = {**population_row("2023-01-01|OTHER"), "symbol": "OTHER"}
    assert freeze_population((first, second)) == freeze_population((second, first))
    assert freeze_population((first, second)) == canonical_hash([second, first])


def test_population_freeze_rejects_duplicates() -> None:
    source = population_row()
    with pytest.raises(ValueError, match="duplicate"):
        freeze_population((source, source))


def test_population_freeze_rejects_validation_rows() -> None:
    with pytest.raises(ValidationAccessError):
        freeze_population((population_row("2025-01-01|TEST"),))


def test_preregistration_locks_exactly_ten_non_promotable_experiments() -> None:
    prereg = build_preregistration("population-hash", {"feature": "frozen"})
    assert prereg["experiment_count"] == 10
    assert [row["experiment_id"] for row in prereg["experiments"]] == list(EXPERIMENT_IDS)
    assert prereg["written_before_result_computation"] is True
    assert all(row["promotion_allowed"] is False for row in prereg["experiments"])
    assert all(row["eligible_for_promotion"] is False for row in prereg["experiments"])
    assert all(row["parameter_hash"] == canonical_hash(row["parameters"]) for row in prereg["experiments"])
    assert prereg["intraday_confirmation_prereg_hash"] == canonical_hash(prereg["experiments"])


def test_preregistration_contains_no_unregistered_wait_window() -> None:
    prereg = build_preregistration("population-hash", {})
    assert all(tuple(row["parameters"]["registered_windows_minutes"]) == WINDOWS for row in prereg["experiments"])
    payload = json.dumps(json_ready(prereg))
    assert "7m" not in payload
    assert "12m" not in payload
    assert "20m" not in payload


def test_preregistration_dependency_excludes_mutable_whole_file_guards() -> None:
    stable = {
        "baseline_chain_hashes": {"feature": "frozen"},
        "diagnostic_registry_experiment_count": 1,
        "diagnostic_registry_experiment_hashes": {
            "EXP-TEST-001": {
                "parameter_hash": "parameter",
                "pre_registration_hash": "preregistration",
            }
        },
        "diagnostic_registry_semantic_hash": "semantic",
        "cost_model_config_sha256": "cost",
        "temporal_harness_config_hash": "temporal",
        "scope_hash": "scope",
        "request_plan_hash": "plan",
        "command_05b_dataset_hashes": {"normalized_5m_dataset_hash": "bars"},
    }
    first = {**stable, "diagnostic_registry_sha256": "first", "guard_file_hashes": {"a": "first"}}
    second = {**stable, "diagnostic_registry_sha256": "second", "guard_file_hashes": {"a": "second"}}
    assert _prereg_baseline_dependency(first) == _prereg_baseline_dependency(second)
    assert build_preregistration("population", _prereg_baseline_dependency(first)) == build_preregistration(
        "population", _prereg_baseline_dependency(second)
    )


def test_real_intraday_prices_are_rebased_to_frozen_t1_open_without_mutation() -> None:
    raw = bar(1, open_="500", high="510", low="490", close="505")
    factor = _price_basis_scale(Decimal("100"), (raw,))
    aligned = _scale_bars((raw,), factor)[0]
    assert factor == Decimal("0.2")
    assert (aligned.open, aligned.high, aligned.low, aligned.close) == (
        Decimal("100"),
        Decimal("102"),
        Decimal("98"),
        Decimal("101"),
    )
    assert raw.open == Decimal("500")
    assert raw.close == Decimal("505")


@pytest.mark.parametrize("window", WINDOWS)
def test_confirmation_reference_uses_completed_registered_bar(window: int) -> None:
    closes = ("100.5", "101", "102")
    five = [bar(index + 1, close=closes[index]) for index in range(3)]
    if window == 5:
        derived = [five[0]]
    else:
        count = window // 5
        derived = [
            replace(
                five[0],
                interval=f"{window}m",
                bar_end=five[count - 1].bar_end,
                close=five[count - 1].close,
                source_provider="DERIVED_FROM_NORMALIZED_5M",
                source_bar_count=count,
            )
        ]
    price, timestamp, causal = confirmation_reference(five, derived, window)
    assert price == five[window // 5 - 1].close
    assert timestamp == five[window // 5 - 1].bar_end
    assert all(item.bar_end <= timestamp for item in causal)


def test_confirmation_reference_rejects_partial_derived_bar() -> None:
    five = [bar(1), bar(2, close="101")]
    derived = replace(
        five[0],
        interval="10m",
        bar_end=five[1].bar_end,
        close=five[1].close,
        source_provider="DERIVED_FROM_NORMALIZED_5M",
        source_bar_count=2,
        is_partial_bar=True,
    )
    with pytest.raises(ValueError, match="complete"):
        confirmation_reference(five, (derived,), 10)


def test_confirmation_reference_rejects_future_bar_leakage() -> None:
    five = [bar(1), replace(bar(2), bar_end=datetime(2024, 1, 2, 9, 30, tzinfo=IST))]
    derived = replace(
        five[0],
        interval="10m",
        bar_end=datetime(2024, 1, 2, 9, 25, tzinfo=IST),
        source_provider="DERIVED_FROM_NORMALIZED_5M",
        source_bar_count=2,
    )
    with pytest.raises(ValueError, match="leakage"):
        confirmation_reference(five, (derived,), 10)


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        ("-1", PRICE_DRIFT_BUCKETS[0]),
        ("-0.75", PRICE_DRIFT_BUCKETS[1]),
        ("0", PRICE_DRIFT_BUCKETS[2]),
        ("0.25", PRICE_DRIFT_BUCKETS[3]),
        ("0.75", PRICE_DRIFT_BUCKETS[4]),
        ("1.5", PRICE_DRIFT_BUCKETS[5]),
        ("2.1", PRICE_DRIFT_BUCKETS[6]),
    ],
)
def test_price_drift_buckets_are_frozen(price: str, expected: str) -> None:
    assert price_drift_bucket(Decimal(price)) == expected


def test_confirmation_rr_recomputes_without_moving_stop_or_target() -> None:
    rr, risk, reward = confirmation_rr(Decimal("102"), Decimal("95"), Decimal("110"))
    assert risk == 7
    assert reward == 8
    assert rr == Decimal("8") / Decimal("7")


@pytest.mark.parametrize(("price", "stop", "target"), [("95", "95", "110"), ("110", "95", "110")])
def test_confirmation_rr_flags_invalid_structure(price: str, stop: str, target: str) -> None:
    rr, _risk, _reward = confirmation_rr(Decimal(price), Decimal(stop), Decimal(target))
    assert rr is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1.49", RR_BUCKETS[0]), ("1.5", RR_BUCKETS[1]), ("2", RR_BUCKETS[2]), ("2.5", RR_BUCKETS[3])],
)
def test_rr_viability_buckets(value: str, expected: str) -> None:
    assert rr_bucket(Decimal(value)) == expected


def test_stop_before_confirmation_is_detected() -> None:
    result = preconfirmation_touch_state((bar(1, low="94"),), Decimal("95"), Decimal("110"))
    assert result["stop_touched"] is True
    assert result["first_touch"] == "STOP_FIRST"
    assert confirmation_feasibility(result, Decimal("1")) == "STOP_INVALIDATED_BEFORE_CONFIRMATION"


def test_target_before_confirmation_is_detected() -> None:
    result = preconfirmation_touch_state((bar(1, high="111"),), Decimal("95"), Decimal("110"))
    assert result["target_touched"] is True
    assert result["first_touch"] == "TARGET_FIRST"
    assert confirmation_feasibility(result, Decimal("1")) == "TARGET_REACHED_BEFORE_CONFIRMATION"


def test_same_bar_preconfirmation_ambiguity_is_preserved() -> None:
    result = preconfirmation_touch_state(
        (bar(1, high="111", low="94"),), Decimal("95"), Decimal("110")
    )
    assert result["ambiguous"] is True
    assert result["first_touch"] == "INTRABAR_SEQUENCE_AMBIGUOUS"
    assert confirmation_feasibility(result, Decimal("1")) == "INTRABAR_AMBIGUOUS"


def test_structure_invalid_feasibility_is_separate() -> None:
    untouched = preconfirmation_touch_state((bar(1),), Decimal("95"), Decimal("110"))
    assert confirmation_feasibility(untouched, None) == "STRUCTURE_INVALID_AT_CONFIRMATION"
    assert confirmation_feasibility(untouched, Decimal("2")) == "FEASIBLE"


def test_post_confirmation_path_starts_after_completed_confirmation_bar() -> None:
    completed_confirmation = bar(1, high="120", low="90")
    next_bar = bar(2, high="104", low="98", close="101")
    result = _path_metrics(
        confirmation_price=Decimal("100"),
        confirmation_timestamp=completed_confirmation.bar_end,
        stop=Decimal("95"),
        target=Decimal("110"),
        risk=Decimal("5"),
        all_bars=(completed_confirmation, next_bar),
        max_holding_date=date(2024, 1, 2),
    )
    assert result["post_confirmation_bar_count"] == 1
    assert result["post_first_touch"] == "NEITHER"
    assert result["mfe_confirm_r"] == Decimal("0.8")
    assert result["mae_confirm_r"] == Decimal("0.4")


@pytest.mark.parametrize(
    ("price", "open_", "expected"),
    [("101", "100", "EARLY_STRENGTH"), ("99", "100", "EARLY_WEAKNESS"), ("100", "100", "FLAT")],
)
def test_early_path_definition_uses_sign_only(price: str, open_: str, expected: str) -> None:
    assert early_path_classification(Decimal(price), Decimal(open_)) == expected


def test_vwap_context_uses_fixed_precision_tolerance() -> None:
    assert vwap_classification(Decimal("100.004"), Decimal("100")) == "AT_VWAP"
    assert vwap_classification(Decimal("100.006"), Decimal("100")) == "ABOVE_VWAP"
    assert vwap_classification(Decimal("99.99"), Decimal("100")) == "BELOW_VWAP"
    assert CLASSIFICATION_RULES["vwap_at_tolerance_rupees"] == "0.005"


@pytest.mark.parametrize(
    ("price", "expected"),
    [("111", "ABOVE_OR_HIGH"), ("110", "ON_OR_HIGH"), ("105", "INSIDE_OR"), ("100", "ON_OR_LOW"), ("99", "BELOW_OR_LOW")],
)
def test_opening_range_context_preserves_boundaries(price: str, expected: str) -> None:
    assert opening_range_classification(Decimal(price), Decimal("110"), Decimal("100")) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "VERY_SMALL"), (29, "VERY_SMALL"), (30, "SMALL"), (99, "SMALL"), (100, "LIMITED"), (299, "LIMITED"), (300, "ADEQUATE_FOR_DESCRIPTION")],
)
def test_sample_safety_thresholds(count: int, expected: str) -> None:
    assert sample_safety(count) == expected


def test_source_and_admitted_denominators_remain_separate() -> None:
    common = {
        "window_minutes": 5,
        "data_available": True,
        "confirmation_feasibility": "FEASIBLE",
        "stop_touched_before_confirmation": False,
        "target_touched_before_confirmation": False,
        "price_change_from_open_pct": Decimal("0.1"),
        "confirmation_effective_rr": Decimal("2"),
        "frozen_effective_rr": Decimal("2"),
        "rr_delta": Decimal("0"),
        "remaining_target_distance_pct": Decimal("5"),
        "remaining_stop_distance_pct": Decimal("5"),
        "mfe_from_confirmation_pct": Decimal("2"),
        "mae_from_confirmation_pct": Decimal("1"),
        "mfe_confirm_r": Decimal("0.4"),
        "mae_confirm_r": Decimal("0.2"),
        "post_path_quality_group": "NEITHER_WITH_POSITIVE_MFE",
    }
    rows = [{**common, "is_admitted": True}, {**common, "is_admitted": False}]
    assert window_profile(rows, "ALL_STRICT_COVERED")["source_opportunity_count"] == 2
    assert window_profile(rows, "ADMITTED_STRICT_COVERED")["source_opportunity_count"] == 1


def test_report_contract_contains_all_required_machine_outputs() -> None:
    assert REPORT_FILENAMES == (
        "intraday_confirmation_v1_summary.json",
        "intraday_confirmation_v1_population.csv",
        "intraday_confirmation_v1_5m.csv",
        "intraday_confirmation_v1_10m.csv",
        "intraday_confirmation_v1_15m.csv",
        "intraday_confirmation_v1_price_drift.csv",
        "intraday_confirmation_v1_rr_headroom.csv",
        "intraday_confirmation_v1_vwap.csv",
        "intraday_confirmation_v1_opening_range.csv",
        "intraday_confirmation_v1_false_start.csv",
        "intraday_confirmation_v1_contexts.csv",
        "intraday_confirmation_v1_yearly.csv",
        "intraday_confirmation_v1_pilot.csv",
    )


def test_machine_report_writers_are_offline_and_deterministic() -> None:
    output_root = Path("tmp/intraday_confirmation_writer_test")
    json_path = output_root / "report.json"
    csv_path = output_root / "report.csv"
    payload = [{"value": Decimal("1.25"), "tags": ["A", "B"]}]
    _write_json(json_path, payload)
    _write_csv(csv_path, payload)
    try:
        assert json.loads(json_path.read_text(encoding="utf-8"))[0]["value"] == "1.25"
        assert "1.25" in csv_path.read_text(encoding="utf-8")
    finally:
        json_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        output_root.rmdir()


def test_diagnostic_contract_prohibits_promotion_and_performance_winner() -> None:
    prereg = build_preregistration("population-hash", {})
    assert all(row["diagnostic_only"] for row in prereg["experiments"])
    assert all(not row["promotion_allowed"] for row in prereg["experiments"])
    payload = json.dumps(json_ready(prereg)).lower()
    assert "best" not in payload
    assert "winner" not in payload

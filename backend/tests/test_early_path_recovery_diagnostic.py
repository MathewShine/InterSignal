from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.confirmation_diagnostic import _path_metrics, _write_csv, _write_json
from app.research.intraday.early_path_recovery_diagnostic import (
    CLOSE_LOCATION_BUCKETS,
    DIAGNOSTIC_VERSION,
    EXPERIMENT_IDS,
    EXPERIMENTS,
    FAMILY,
    FIRST5_STATES,
    HIGHER_LOW_STATES,
    PRIMARY_PATH_STATES,
    PROFILE,
    RECOVERY10_STATES,
    RECOVERY15_STATES,
    RECLAIM_TIME_DEFINITIONS,
    RECLAIM_TIME_BUCKETS,
    REPORT_FILENAMES,
    STATE_DEFINITIONS,
    _post15_path,
    _yearly,
    build_preregistration,
    classifications,
    close_location,
    close_location_bucket,
    favorable_control_path,
    failure_control_path,
    first5_state,
    freeze_population,
    higher_low_state,
    open_reclaim_state,
    primary_path_state,
    reclaim_time_bucket,
    recovery10_state,
    recovery15_state,
    recovery_value,
    state_profile,
    temporal_consistency,
)
from app.research.intraday.models import CanonicalIntradayBar, FirstTouch
from app.research.temporal_validation.config import SEALED, canonical_hash, json_ready


IST = timezone(timedelta(hours=5, minutes=30))


def population_row(opportunity_id: str = "2024-01-01|TEST") -> dict[str, object]:
    start = datetime(2024, 1, 2, 9, 15, tzinfo=IST)
    bars = [
        {
            "bar_number": index,
            "bar_start": start + timedelta(minutes=(index - 1) * 5),
            "bar_end": start + timedelta(minutes=index * 5),
            "open": Decimal("100"),
            "high": Decimal("101"),
            "low": Decimal("99"),
            "close": Decimal("100"),
            "volume": 100,
        }
        for index in (1, 2, 3)
    ]
    return {
        "opportunity_id": opportunity_id,
        "symbol": opportunity_id.split("|")[1],
        "decision_date": opportunity_id.split("|")[0],
        "entry_date": "2024-01-02",
        "score": 84,
        "setup_quality": "STRONG",
        "candidate_stage": "BOTH_ELIGIBLE",
        "regime_state": "BULLISH",
        "open_0": Decimal("100"),
        "frozen_stop": Decimal("95"),
        "frozen_target": Decimal("110"),
        "frozen_rr": Decimal("2"),
        "first_15m_bars": bars,
        "c1": Decimal("99"),
        "c2": Decimal("100"),
        "c3": Decimal("101"),
        "h1": Decimal("101"),
        "h2": Decimal("102"),
        "h3": Decimal("103"),
        "l1": Decimal("98"),
        "l2": Decimal("99"),
        "l3": Decimal("100"),
        "first_15m_completed_at": start + timedelta(minutes=15),
        "intraday_quality": "USABLE_STRICT_FULL_PATH",
        "CA_safety": "SAFE",
        "frozen_admitted_flag": False,
        "price_basis_scale_factor": Decimal("1"),
        "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
        "causal_source_bar_count": 3,
    }


def record(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        **population_row(),
        "first5_state": "FIRST5_WEAK",
        "recovery10_state": "RECOVER_BY_10",
        "recovery15_state": "NOT_APPLICABLE",
        "open_reclaim_state": "DIP_AND_RECLAIM_BY_10",
        "reclaim_time_bucket": "10M",
        "higher_low_state": "TWO_STEP_HIGHER_LOW",
        "early15_close_location_bucket": "HIGH_QUARTER",
        "primary_path_state": "RECOVERY_STRENGTH_15",
        "control_path": "TARGET_FIRST",
        "control_stop_first": False,
        "control_target_first": True,
        "control_mfe_r": Decimal("2"),
        "control_mae_r": Decimal("0.4"),
        "favorable_control_path": True,
        "post15_path": "TARGET_FIRST",
        "mfe_post15_r": Decimal("1.5"),
        "mae_post15_r": Decimal("0.3"),
        "price_extension_15m_pct": Decimal("1"),
        "hypothetical_rr_at_15m": Decimal("1.5"),
        "pre15_stop_touched": False,
        "pre15_target_touched": False,
        "vwap_15m_context": "ABOVE_VWAP",
    }
    row.update(updates)
    return row


def bar(sequence: int, *, high: str = "101", low: str = "99") -> CanonicalIntradayBar:
    start = datetime(2024, 1, 2, 9, 15, tzinfo=IST) + timedelta(minutes=(sequence - 1) * 5)
    return CanonicalIntradayBar(
        instrument_id="1",
        symbol="TEST",
        isin="INE000000001",
        exchange="NSE",
        trading_date=date(2024, 1, 2),
        interval="5m",
        bar_start=start,
        bar_end=start + timedelta(minutes=5),
        open=Decimal("100"),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal("100"),
        volume=100,
        source_provider="GROWW_OFFICIAL_API",
        source_interval="5m",
        source_timestamp=start,
        ingested_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
        normalization_version="NSE_CASH_INTRADAY_5M_V1",
        session_id="NSE:2024-01-02",
        session_sequence=sequence,
        source_bar_count=1,
    )


def test_contract_identity_and_exact_experiment_allowlist() -> None:
    assert DIAGNOSTIC_VERSION == "EARLY_PATH_RECOVERY_DIAGNOSTIC_V1"
    assert PROFILE == "DEVELOPMENT_EARLY_PATH_RECOVERY_V1"
    assert FAMILY == "EARLY_PATH_QUALITY_DIAGNOSTIC"
    assert EXPERIMENT_IDS == tuple(f"EXP-EARLYPATH-{index:03d}" for index in range(1, 11))
    assert tuple(name for _experiment_id, name in EXPERIMENTS)[-1] == "EARLY_PATH_CONTEXT_INTERACTIONS"


@pytest.mark.parametrize(
    ("close", "expected"),
    [("101", "FIRST5_STRONG"), ("99", "FIRST5_WEAK"), ("100", "FIRST5_FLAT")],
)
def test_first5_states_use_exact_canonical_precision(close: str, expected: str) -> None:
    assert first5_state(Decimal(close), Decimal("100")) == expected
    assert expected in FIRST5_STATES


@pytest.mark.parametrize(
    ("c1", "c2", "expected"),
    [
        ("99", "100", "RECOVER_BY_10"),
        ("99", "99.5", "PARTIAL_RECOVERY_BY_10"),
        ("99", "99", "PERSISTENT_WEAK_TO_10"),
        ("99", "98", "PERSISTENT_WEAK_TO_10"),
        ("100", "101", "NOT_APPLICABLE"),
    ],
)
def test_five_to_ten_recovery_states(c1: str, c2: str, expected: str) -> None:
    assert recovery10_state(Decimal(c1), Decimal(c2), Decimal("100")) == expected


@pytest.mark.parametrize(
    ("c2", "c3", "expected"),
    [
        ("99", "100", "RECOVER_BY_15"),
        ("99", "99.5", "PARTIAL_RECOVERY_BY_15"),
        ("99", "99", "PERSISTENT_WEAK_TO_15"),
        ("99", "98", "PERSISTENT_WEAK_TO_15"),
        ("100", "101", "NOT_APPLICABLE"),
    ],
)
def test_ten_to_fifteen_recovery_states(c2: str, c3: str, expected: str) -> None:
    assert recovery15_state(Decimal(c2), Decimal(c3), Decimal("100")) == expected


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (("100", "101", "102"), "NEVER_BELOW_OPEN_FIRST15"),
        (("99", "100", "101"), "DIP_AND_RECLAIM_BY_10"),
        (("99", "99.5", "100"), "DIP_AND_RECLAIM_BY_15"),
        (("99", "99.5", "99.9"), "BELOW_OPEN_AT_15"),
        (("101", "99", "100"), "MIXED_OPEN_RECLAIM"),
    ],
)
def test_open_reclaim_states_are_deterministic(closes: tuple[str, str, str], expected: str) -> None:
    assert open_reclaim_state(*(Decimal(value) for value in closes), Decimal("100")) == expected


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (("100", "99", "101"), "5M"),
        (("99", "100", "101"), "10M"),
        (("99", "99", "100"), "15M"),
        (("99", "99", "99"), "NONE"),
    ],
)
def test_reclaim_time_buckets(closes: tuple[str, str, str], expected: str) -> None:
    assert reclaim_time_bucket(*(Decimal(value) for value in closes), Decimal("100")) == expected
    assert expected in RECLAIM_TIME_BUCKETS


def test_reclaim_time_semantics_are_preregistered() -> None:
    assert tuple(RECLAIM_TIME_DEFINITIONS) == RECLAIM_TIME_BUCKETS
    assert "no prior completed 5m close exists" in RECLAIM_TIME_DEFINITIONS["5M"]
    assert "literal completed-close reclaim" in RECLAIM_TIME_DEFINITIONS["10M"]


@pytest.mark.parametrize(
    ("lows", "expected"),
    [
        (("98", "99", "100"), "TWO_STEP_HIGHER_LOW"),
        (("98", "99", "98"), "ONE_STEP_HIGHER_LOW"),
        (("99", "98", "99"), "ONE_STEP_HIGHER_LOW"),
        (("100", "99", "98"), "NO_HIGHER_LOW"),
        (("99", "99", "99"), "NO_HIGHER_LOW"),
    ],
)
def test_higher_low_definitions(lows: tuple[str, str, str], expected: str) -> None:
    assert higher_low_state(*(Decimal(value) for value in lows)) == expected
    assert expected in HIGHER_LOW_STATES


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "LOW_QUARTER"),
        ("0.249999", "LOW_QUARTER"),
        ("0.25", "LOW_MID"),
        ("0.5", "HIGH_MID"),
        ("0.75", "HIGH_QUARTER"),
        ("1", "HIGH_QUARTER"),
    ],
)
def test_close_location_quartile_boundaries_are_frozen(value: str, expected: str) -> None:
    assert close_location_bucket(Decimal(value)) == expected


def test_close_location_and_zero_range() -> None:
    assert close_location(Decimal("101"), Decimal("104"), Decimal("100")) == Decimal("0.25")
    assert close_location(Decimal("100"), Decimal("100"), Decimal("100")) is None
    assert close_location_bucket(None) == "ZERO_RANGE"


def test_close_location_rejects_invalid_ohlc() -> None:
    with pytest.raises(ValueError, match="low <= close <= high"):
        close_location(Decimal("105"), Decimal("104"), Decimal("100"))


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (("100", "101", "102"), "PERSISTENT_STRENGTH_15"),
        (("99", "99", "100"), "RECOVERY_STRENGTH_15"),
        (("101", "99", "100"), "RECOVERY_STRENGTH_15"),
        (("99", "99", "99"), "PERSISTENT_WEAKNESS_15"),
        (("101", "101", "99"), "MIXED_EARLY_PATH"),
    ],
)
def test_primary_state_hierarchy_is_non_overlapping(closes: tuple[str, str, str], expected: str) -> None:
    assert primary_path_state(*(Decimal(value) for value in closes), Decimal("100")) == expected
    assert expected in PRIMARY_PATH_STATES


@pytest.mark.parametrize(
    ("path", "mfe", "expected"),
    [("TARGET_FIRST", "0", True), ("NEITHER", "1.5", True), ("STOP_FIRST", "1.49", False)],
)
def test_favorable_path_definition_matches_command02(path: str, mfe: str, expected: bool) -> None:
    assert favorable_control_path(path, Decimal(mfe)) is expected


def test_failure_path_is_only_control_stop_first() -> None:
    assert failure_control_path("STOP_FIRST") is True
    assert all(not failure_control_path(value) for value in ("TARGET_FIRST", "AMBIGUOUS", "NEITHER"))


def test_population_hash_is_order_independent_and_deterministic() -> None:
    first = population_row("2024-01-01|TEST")
    second = {**population_row("2023-01-01|OTHER"), "entry_date": "2023-01-02"}
    assert freeze_population((first, second)) == freeze_population((second, first))
    assert freeze_population((first, second)) == canonical_hash([second, first])


def test_population_freeze_rejects_duplicates() -> None:
    row = population_row()
    with pytest.raises(ValueError, match="duplicate"):
        freeze_population((row, row))


@pytest.mark.parametrize("decision", ["2021-12-31", "2025-01-01"])
def test_population_freeze_rejects_non_development_rows(decision: str) -> None:
    with pytest.raises(ValueError, match="non-DEVELOPMENT"):
        freeze_population(({**population_row(), "decision_date": decision},))


def test_population_freeze_requires_three_real_bars() -> None:
    row = population_row()
    row["first_15m_bars"] = row["first_15m_bars"][:2]
    with pytest.raises(ValueError, match="three canonical"):
        freeze_population((row,))


def test_population_freeze_rejects_non_strict_or_ca_unsafe() -> None:
    with pytest.raises(ValueError, match="unsafe or non-strict"):
        freeze_population(({**population_row(), "CA_safety": "UNSAFE"},))
    with pytest.raises(ValueError, match="unsafe or non-strict"):
        freeze_population(({**population_row(), "intraday_quality": "PARTIAL"},))


def test_preregistration_freezes_exactly_ten_diagnostic_records() -> None:
    prereg = build_preregistration("population", {"feature": "frozen"})
    assert prereg["experiment_count"] == 10
    assert tuple(prereg["experiment_ids"]) == EXPERIMENT_IDS
    assert [row["experiment_id"] for row in prereg["experiments"]] == list(EXPERIMENT_IDS)
    assert prereg["definitions_frozen_before_results"] is True
    assert all(row["diagnostic_only"] for row in prereg["experiments"])
    assert all(not row["promotion_allowed"] for row in prereg["experiments"])
    assert all(not row["validation_authorized"] for row in prereg["experiments"])


def test_preregistration_hashes_and_definitions_are_deterministic() -> None:
    prereg = build_preregistration("population", {"feature": "frozen"})
    assert prereg == build_preregistration("population", {"feature": "frozen"})
    assert prereg["early_path_preregistration_hash"] == canonical_hash(prereg["experiments"])
    assert all(row["parameter_hash"] == canonical_hash(row["parameters"]) for row in prereg["experiments"])
    assert prereg["experiments"][0]["parameters"]["state_definitions"] == STATE_DEFINITIONS


def test_preregistration_does_not_mutate_dependencies() -> None:
    dependencies = {"nested": {"hash": "frozen"}}
    before = deepcopy(dependencies)
    build_preregistration("population", dependencies)
    assert dependencies == before


def test_preregistration_prohibits_rule_optimization_portfolio_validation_and_v2() -> None:
    parameters = build_preregistration("population", {})["experiments"][0]["parameters"]
    assert parameters["no_hypothetical_entry"] is True
    assert parameters["no_rule_creation"] is True
    assert parameters["threshold_optimization_allowed"] is False
    assert parameters["vwap_rule_allowed"] is False
    assert parameters["opening_range_rule_allowed"] is False
    assert parameters["portfolio_rerun_allowed"] is False
    assert parameters["strategy_v2_allowed"] is False
    assert parameters["validation_state"] == SEALED
    assert parameters["validation_run_count"] == 0


def test_state_profile_keeps_source_and_admitted_separate() -> None:
    rows = [record(), record(frozen_admitted_flag=True)]
    source = state_profile(rows, field="primary_path_state", states=PRIMARY_PATH_STATES, population="SOURCE_OPPORTUNITIES")
    admitted = state_profile(rows, field="primary_path_state", states=PRIMARY_PATH_STATES, population="FROZEN_ADMITTED_SUBSET")
    assert next(row for row in source if row["state"] == "RECOVERY_STRENGTH_15")["count"] == 2
    assert next(row for row in admitted if row["state"] == "RECOVERY_STRENGTH_15")["count"] == 1


def test_state_profile_calculates_failure_favorable_post15_and_extension() -> None:
    rows = [
        record(),
        record(control_path="STOP_FIRST", control_stop_first=True, control_target_first=False, favorable_control_path=False, post15_path="STOP_FIRST", mfe_post15_r=Decimal("0.5"), mae_post15_r=Decimal("1"), price_extension_15m_pct=Decimal("-1")),
    ]
    profile = next(row for row in state_profile(rows, field="primary_path_state", states=PRIMARY_PATH_STATES, population="SOURCE_OPPORTUNITIES") if row["state"] == "RECOVERY_STRENGTH_15")
    assert profile["count"] == 2
    assert profile["control_stop_first_rate_pct"] == 50
    assert profile["favorable_rate_pct"] == 50
    assert profile["post15_stop_first_rate_pct"] == 50
    assert profile["median_price_extension_15m_pct"] == 0


def test_recovery_value_metrics_are_directionally_explicit() -> None:
    rows = [
        record(recovery10_state="RECOVER_BY_10"),
        record(recovery10_state="RECOVER_BY_10", control_path="STOP_FIRST", control_stop_first=True, control_target_first=False, favorable_control_path=False),
        record(recovery10_state="PERSISTENT_WEAK_TO_10", control_path="STOP_FIRST", control_stop_first=True, control_target_first=False, favorable_control_path=False),
        record(recovery10_state="PERSISTENT_WEAK_TO_10", control_path="STOP_FIRST", control_stop_first=True, control_target_first=False, favorable_control_path=False),
    ]
    result = recovery_value(rows)
    assert result["recover_by_10_failure_rate_pct"] == 50
    assert result["persistent_weak_to_10_failure_rate_pct"] == 100
    assert result["persistent_minus_recovered_failure_rate_pp"] == 50
    assert result["recovered_minus_persistent_favorable_rate_pp"] == 50


def test_post15_path_begins_after_0930_and_preserves_first_touch() -> None:
    first_three = (bar(1, high="120", low="90"), bar(2, high="120", low="90"), bar(3, high="120", low="90"))
    after = bar(4, high="111", low="99")
    result = _path_metrics(
        confirmation_price=Decimal("100"),
        confirmation_timestamp=first_three[2].bar_end,
        stop=Decimal("95"),
        target=Decimal("110"),
        risk=Decimal("5"),
        all_bars=(*first_three, after),
        max_holding_date=date(2024, 1, 2),
    )
    assert result["post_confirmation_bar_count"] == 1
    assert _post15_path(result["post_first_touch"]) == "TARGET_FIRST"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (FirstTouch.GAP_THROUGH_STOP, "STOP_FIRST"),
        (FirstTouch.GAP_THROUGH_TARGET, "TARGET_FIRST"),
        (FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS, "AMBIGUOUS"),
        (FirstTouch.NEITHER, "NEITHER"),
    ],
)
def test_post15_path_normalization(value: FirstTouch, expected: str) -> None:
    assert _post15_path(value) == expected


def test_yearly_partition_reports_all_primary_states() -> None:
    rows = [
        record(opportunity_id=f"{year}-01-01|TEST", decision_date=f"{year}-01-01")
        for year in (2022, 2023, 2024)
    ]
    yearly = _yearly(rows)
    assert len(yearly) == 12
    assert {row["year"] for row in yearly} == {2022, 2023, 2024}
    assert {row["state"] for row in yearly} == set(PRIMARY_PATH_STATES)


def test_temporal_consistency_requires_two_adequate_supportive_years() -> None:
    yearly = []
    for year, supportive in ((2022, True), (2023, True), (2024, False)):
        yearly.extend(
            [
                {"year": year, "state": "RECOVERY_STRENGTH_15", "count": 40, "control_stop_first_rate_pct": Decimal("10") if supportive else Decimal("30"), "favorable_rate_pct": Decimal("30") if supportive else Decimal("10")},
                {"year": year, "state": "PERSISTENT_WEAKNESS_15", "count": 40, "control_stop_first_rate_pct": Decimal("30") if supportive else Decimal("10"), "favorable_rate_pct": Decimal("10") if supportive else Decimal("30")},
            ]
        )
    assert temporal_consistency(yearly) == "MOSTLY_CONSISTENT"


def test_temporal_consistency_is_inconclusive_for_small_cells() -> None:
    yearly = [
        {"year": year, "state": state, "count": 29, "control_stop_first_rate_pct": Decimal("10"), "favorable_rate_pct": Decimal("20")}
        for year in (2022, 2023, 2024)
        for state in ("RECOVERY_STRENGTH_15", "PERSISTENT_WEAKNESS_15")
    ]
    assert temporal_consistency(yearly) == "INCONCLUSIVE"


def test_classifications_are_diagnostic_and_mechanical() -> None:
    rows = []
    for year in (2022, 2023, 2024):
        for index in range(100):
            is_recovery = index < 50
            within_state_index = index if is_recovery else index - 50
            is_failure = within_state_index < (5 if is_recovery else 15)
            is_favorable = (5 if is_recovery else 15) <= within_state_index < (20 if is_recovery else 20)
            rows.append(
                record(
                    opportunity_id=f"{year}-01-01|TEST{index:03d}",
                    decision_date=f"{year}-01-01",
                    setup_quality="STRONG" if index % 2 else "VALID",
                    candidate_stage="BOTH_ELIGIBLE" if index % 3 else "PRIMARY_ONLY",
                    regime_state="BULLISH" if index % 2 else "NEUTRAL",
                    primary_path_state="RECOVERY_STRENGTH_15" if is_recovery else "PERSISTENT_WEAKNESS_15",
                    control_stop_first=is_failure,
                    control_target_first=is_favorable,
                    control_path="STOP_FIRST" if is_failure else ("TARGET_FIRST" if is_favorable else "NEITHER"),
                    favorable_control_path=is_favorable,
                )
            )
    state_rows = []
    templates = {
        "PERSISTENT_STRENGTH_15": (300, 15, 20),
        "RECOVERY_STRENGTH_15": (300, 10, 30),
        "PERSISTENT_WEAKNESS_15": (300, 30, 10),
        "MIXED_EARLY_PATH": (200, 20, 20),
    }
    for state, (count, failure, favorable) in templates.items():
        state_rows.append({"population": "SOURCE_OPPORTUNITIES", "state": state, "count": count, "control_stop_first_rate_pct": Decimal(failure), "favorable_rate_pct": Decimal(favorable)})
    higher = [
        {"population": "SOURCE_OPPORTUNITIES", "state": "TWO_STEP_HIGHER_LOW", "count": 200, "control_stop_first_rate_pct": Decimal("10"), "favorable_rate_pct": Decimal("30")},
        {"population": "SOURCE_OPPORTUNITIES", "state": "ONE_STEP_HIGHER_LOW", "count": 200, "control_stop_first_rate_pct": Decimal("20"), "favorable_rate_pct": Decimal("20")},
        {"population": "SOURCE_OPPORTUNITIES", "state": "NO_HIGHER_LOW", "count": 200, "control_stop_first_rate_pct": Decimal("20"), "favorable_rate_pct": Decimal("20")},
    ]
    close_rows = [
        {"population": "SOURCE_OPPORTUNITIES", "state": state, "count": 200, "control_stop_first_rate_pct": Decimal("10") if state == "HIGH_QUARTER" else Decimal("20"), "favorable_rate_pct": Decimal("30") if state == "HIGH_QUARTER" else Decimal("20")}
        for state in CLOSE_LOCATION_BUCKETS
    ]
    yearly = [
        {"year": year, "state": state, "count": 40, "control_stop_first_rate_pct": Decimal("30") if state == "PERSISTENT_WEAKNESS_15" else Decimal("10"), "favorable_rate_pct": Decimal("10") if state == "PERSISTENT_WEAKNESS_15" else Decimal("30")}
        for year in (2022, 2023, 2024)
        for state in PRIMARY_PATH_STATES
    ]
    result, evidence = classifications(rows, state_rows, higher, close_rows, yearly, "CONSISTENT")
    assert result["RECOVERY_STATE_RESULT"] == "PROMISING_FOR_CONTROLLED_TEST"
    assert result["HIGHER_LOW_RESULT"] == "PROMISING_FOR_CONTROLLED_TEST"
    assert result["EARLY_CLOSE_LOCATION_RESULT"] == "PROMISING_FOR_CONTROLLED_TEST"
    assert result["EARLY_PATH_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING"] == "YES"
    assert evidence["later_gate"]["concepts"]["recovery"]["supportive_year_count"] == 3
    assert evidence["later_gate"]["concepts"]["recovery"]["not_entirely_driven_by_one_subgroup"] is True
    assert evidence["later_gate"]["threshold_optimization_performed"] is False


def test_report_contract_contains_exactly_twelve_files() -> None:
    assert REPORT_FILENAMES == (
        "early_path_recovery_v1_summary.json",
        "early_path_recovery_v1_population.csv",
        "early_path_recovery_v1_first5.csv",
        "early_path_recovery_v1_recovery10.csv",
        "early_path_recovery_v1_recovery15.csv",
        "early_path_recovery_v1_reclaim.csv",
        "early_path_recovery_v1_higher_low.csv",
        "early_path_recovery_v1_close_location.csv",
        "early_path_recovery_v1_states.csv",
        "early_path_recovery_v1_contexts.csv",
        "early_path_recovery_v1_yearly.csv",
        "early_path_recovery_v1_pilot.csv",
    )


def test_machine_report_writers_are_offline_and_decimal_safe() -> None:
    output_root = Path("tmp/early_path_recovery_writer_test")
    json_path = output_root / "report.json"
    csv_path = output_root / "report.csv"
    payload = [{"value": Decimal("1.25"), "nested": {"diagnostic_only": True}}]
    _write_json(json_path, payload)
    _write_csv(csv_path, payload)
    try:
        assert json.loads(json_path.read_text(encoding="utf-8"))[0]["value"] == "1.25"
        assert "1.25" in csv_path.read_text(encoding="utf-8")
        assert json_ready(payload)[0]["nested"]["diagnostic_only"] is True
    finally:
        json_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        output_root.rmdir()

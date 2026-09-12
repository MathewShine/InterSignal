from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.intraday.confirmation_diagnostic import _path_metrics, _write_csv, _write_json
from app.research.intraday.confirmation_rule_experiment import (
    COMPARATOR,
    EXPERIMENT_ID,
    EXPERIMENT_TYPE,
    EXPERIMENT_VERSION,
    PROFILE,
    REPORT_FILENAMES,
    TREATMENT_STATUSES,
    WINDOW_MINUTES,
    _classifications,
    _cost_reference,
    _pilot,
    _yearly,
    build_experiment_freeze,
    build_preregistration,
    exact_ten_minute_rule,
    falsification_results,
    favorable_control_opportunity,
    freeze_population,
    mae_band,
    mfe_band,
    population_metrics,
    temporal_consistency,
    treatment_status,
)
from app.research.intraday.models import CanonicalIntradayBar
from app.research.temporal_validation.config import SEALED, canonical_hash, json_ready


IST = timezone(timedelta(hours=5, minutes=30))


def population_row(opportunity_id: str = "2024-01-01|TEST") -> dict[str, object]:
    return {
        "opportunity_id": opportunity_id,
        "symbol": opportunity_id.split("|")[1],
        "decision_date": opportunity_id.split("|")[0],
        "entry_date": "2024-01-02",
        "score": 84,
        "setup_quality": "STRONG",
        "candidate_stage": "BOTH_ELIGIBLE",
        "regime_state": "BULLISH",
        "t1_open": Decimal("100"),
        "first_10m_close": Decimal("101"),
        "first_10m_timestamp": "2024-01-02T09:25:00+05:30",
        "causal_source_bar_count": 2,
        "causal_cutoff_verified": True,
        "stop": Decimal("95"),
        "target": Decimal("110"),
        "frozen_rr": Decimal("2"),
        "intraday_quality": "USABLE_STRICT_FULL_PATH",
        "corporate_action_safe": True,
        "frozen_admitted_flag": False,
        "price_basis_scale_factor": Decimal("1"),
        "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
    }


def status_record(
    *,
    available: bool = True,
    feasibility: str = "FEASIBLE",
    close: str = "101",
) -> dict[str, object]:
    return {
        "data_available": available,
        "confirmation_feasibility": feasibility,
        "confirmation_price": Decimal(close),
        "frozen_next_open": Decimal("100"),
    }


def matched_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        **population_row(),
        "treatment_status": "CONFIRMED",
        "control_path_outcome": "STOP_FIRST",
        "treatment_path_outcome": "NEITHER",
        "control_favorable": False,
        "control_mfe_r": Decimal("0.4"),
        "treatment_mfe_r": Decimal("0.5"),
        "control_mae_r": Decimal("1.0"),
        "treatment_mae_r": Decimal("0.8"),
        "price_drift_pct": Decimal("0.5"),
        "control_rr": Decimal("2"),
        "treatment_rr": Decimal("1.8"),
        "rr_delta": Decimal("-0.2"),
        "control_cost_r": Decimal("0.10"),
        "treatment_cost_r": Decimal("0.12"),
        "cost_r_delta": Decimal("0.02"),
        "rejected_control_mfe_band": None,
        "rejected_control_mae_band": None,
        "pre_confirmation_stop_touched": False,
        "pre_confirmation_target_touched": False,
        "pre_confirmation_ambiguous": False,
        "treatment_entry_reference": Decimal("101"),
        "stop": Decimal("95"),
        "target": Decimal("110"),
        "treatment_rr": Decimal("1.8"),
        "treatment_cost": {"cost_r": Decimal("0.12")},
        "control_cost": {"cost_r": Decimal("0.10")},
    }
    row.update(updates)
    return row


def yearly_row(*, support: bool = True, confirmed: int = 50) -> dict[str, object]:
    return {
        "confirmed_count": confirmed,
        "filter_separation_pp": Decimal("10") if support else Decimal("-1"),
        "control_stop_first_rate_pct": Decimal("30"),
        "treatment_stop_first_rate_pct": Decimal("20") if support else Decimal("30"),
    }


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


def test_contract_identity_is_exact() -> None:
    assert EXPERIMENT_VERSION == "INTRADAY_CONFIRMATION_RULE_EXPERIMENT_V1"
    assert EXPERIMENT_ID == "EXP-INTRARULE-001"
    assert PROFILE == "TEN_MINUTE_OPEN_CONFIRMATION_V1"
    assert EXPERIMENT_TYPE == "DEVELOPMENT_ONLY_CONTROLLED_RULE_EXPERIMENT"
    assert WINDOW_MINUTES == 10
    assert COMPARATOR == ">="


@pytest.mark.parametrize(
    ("close", "open_", "expected"),
    [("101", "100", True), ("100", "100", True), ("99.999999", "100", False)],
)
def test_exact_ten_minute_rule_has_no_tolerance(close: str, open_: str, expected: bool) -> None:
    assert exact_ten_minute_rule(Decimal(close), Decimal(open_)) is expected


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (status_record(available=False), "DATA_UNAVAILABLE"),
        (status_record(feasibility="INTRABAR_AMBIGUOUS"), "PRE_CONFIRMATION_AMBIGUOUS"),
        (status_record(feasibility="STOP_INVALIDATED_BEFORE_CONFIRMATION"), "PRE_CONFIRMATION_STOP_INVALIDATED"),
        (status_record(feasibility="TARGET_REACHED_BEFORE_CONFIRMATION"), "PRE_CONFIRMATION_TARGET_REACHED"),
        (status_record(feasibility="STRUCTURE_INVALID_AT_CONFIRMATION"), "TREATMENT_STRUCTURE_INVALID"),
        (status_record(close="101"), "CONFIRMED"),
        (status_record(close="100"), "CONFIRMED"),
        (status_record(close="99"), "REJECTED"),
    ],
)
def test_treatment_statuses_are_mutually_exclusive(record: dict[str, object], expected: str) -> None:
    assert treatment_status(record) == expected
    assert expected in TREATMENT_STATUSES


@pytest.mark.parametrize(
    ("path", "mfe", "expected"),
    [("TARGET_FIRST", "0", True), ("NEITHER", "1.5", True), ("STOP_FIRST", "1.49", False)],
)
def test_favorable_control_definition_is_frozen(path: str, mfe: str, expected: bool) -> None:
    assert favorable_control_opportunity(
        {"control_path_outcome": path, "control_mfe_r": Decimal(mfe)}
    ) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.49", "MFE_LT_0_5"), ("0.5", "MFE_0_5_TO_LT_1"), ("1", "MFE_1_TO_LT_1_5"), ("1.5", "MFE_GE_1_5")],
)
def test_rejection_mfe_bands(value: str, expected: str) -> None:
    assert mfe_band(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.49", "MAE_LT_0_5"), ("0.5", "MAE_0_5_TO_LT_1"), ("1", "MAE_GE_1")],
)
def test_rejection_mae_bands(value: str, expected: str) -> None:
    assert mae_band(Decimal(value)) == expected


def test_population_hash_is_order_independent_and_deterministic() -> None:
    first = population_row("2024-01-01|TEST")
    second = {**population_row("2023-01-01|OTHER"), "entry_date": "2023-01-02"}
    assert freeze_population((first, second)) == freeze_population((second, first))
    assert freeze_population((first, second)) == canonical_hash([second, first])


def test_population_freeze_rejects_duplicate_ids() -> None:
    row = population_row()
    with pytest.raises(ValueError, match="duplicate"):
        freeze_population((row, row))


@pytest.mark.parametrize("decision_date", ["2021-12-31", "2025-01-01"])
def test_population_freeze_rejects_validation_or_predevelopment_access(decision_date: str) -> None:
    with pytest.raises(ValueError, match="non-DEVELOPMENT"):
        freeze_population(({**population_row(), "decision_date": decision_date},))


def test_population_freeze_rejects_missing_required_fields() -> None:
    row = population_row()
    del row["first_10m_close"]
    with pytest.raises(ValueError, match="required frozen field"):
        freeze_population((row,))


def test_population_freeze_rejects_corporate_action_unsafe_rows() -> None:
    with pytest.raises(ValueError, match="corporate-action-unsafe"):
        freeze_population(({**population_row(), "corporate_action_safe": False},))


def test_population_freeze_rejects_non_strict_rows() -> None:
    with pytest.raises(ValueError, match="non-strict"):
        freeze_population(({**population_row(), "intraday_quality": "PARTIAL"},))


def test_preregistration_freezes_one_rule_before_results() -> None:
    prereg = build_preregistration("population-hash", {"feature": "frozen"})
    assert prereg["experiment_id"] == EXPERIMENT_ID
    assert prereg["population_hash"] == "population-hash"
    assert prereg["rule"] == "CONFIRMED iff first_10m_close >= T1_session_open"
    assert prereg["written_before_outcome_computation"] is True
    assert prereg["promotion_allowed"] is False
    assert prereg["validation_authorized"] is False


def test_preregistration_hashes_are_deterministic_and_linked() -> None:
    prereg = build_preregistration("population-hash", {"feature": "frozen"})
    repeated = build_preregistration("population-hash", {"feature": "frozen"})
    assert prereg == repeated
    assert prereg["parameter_hash"] == canonical_hash(prereg["parameters"])
    body = {key: value for key, value in prereg.items() if key not in {"experiment_preregistration_hash", "status"}}
    assert prereg["experiment_preregistration_hash"] == canonical_hash(body)


def test_preregistration_changes_when_population_changes() -> None:
    first = build_preregistration("population-a", {})
    second = build_preregistration("population-b", {})
    assert first["parameter_hash"] != second["parameter_hash"]
    assert first["experiment_preregistration_hash"] != second["experiment_preregistration_hash"]


def test_preregistration_does_not_mutate_baseline_dependencies() -> None:
    dependencies = {"nested": {"hash": "frozen"}}
    before = deepcopy(dependencies)
    build_preregistration("population", dependencies)
    assert dependencies == before


def test_only_preregistered_ten_minute_treatment_is_enabled() -> None:
    parameters = build_preregistration("population", {})["parameters"]
    assert tuple(parameters["treatment_windows_run"]) == (10,)
    assert parameters["window_minutes"] == 10
    assert parameters["confirmation_comparator"] == ">="
    assert parameters["optimization_allowed"] is False


def test_no_vwap_opening_range_portfolio_validation_or_strategy_v2_rule() -> None:
    parameters = build_preregistration("population", {})["parameters"]
    assert parameters["vwap_filter_used"] is False
    assert parameters["opening_range_filter_used"] is False
    assert parameters["portfolio_rerun_allowed"] is False
    assert parameters["strategy_v2_allowed"] is False
    assert parameters["validation_state"] == SEALED
    assert parameters["validation_run_count"] == 0


def test_freeze_artifact_uses_same_parameter_hash_and_stays_sealed() -> None:
    prereg = build_preregistration("population", {"feature": "frozen"})
    artifact = build_experiment_freeze(prereg, "a" * 64)
    snapshot = artifact.snapshot()
    assert snapshot["parameter_hash"] == prereg["parameter_hash"]
    assert len(snapshot["development_freeze_hash"]) == 64
    assert snapshot["validation_authorized"] is False
    assert snapshot["development_result_hash"] == "a" * 64


def test_freeze_hash_changes_when_development_result_changes() -> None:
    prereg = build_preregistration("population", {})
    first = build_experiment_freeze(prereg, "a" * 64)
    second = build_experiment_freeze(prereg, "b" * 64)
    assert first.development_freeze_hash() != second.development_freeze_hash()


def test_matched_population_metrics_keep_source_and_admitted_separate() -> None:
    rows = [matched_row(), matched_row(frozen_admitted_flag=True)]
    assert population_metrics(rows, "SOURCE_OPPORTUNITIES")["source_count"] == 2
    assert population_metrics(rows, "FROZEN_ADMITTED_SUBSET")["source_count"] == 1


def test_failure_rejection_good_rejection_and_filter_separation() -> None:
    rows = [
        matched_row(),
        matched_row(treatment_status="REJECTED", rejected_control_mfe_band="MFE_LT_0_5", rejected_control_mae_band="MAE_GE_1"),
        matched_row(control_path_outcome="TARGET_FIRST", treatment_path_outcome="TARGET_FIRST", control_favorable=True),
        matched_row(control_path_outcome="NEITHER", treatment_status="REJECTED", control_favorable=True, control_mfe_r=Decimal("1.5"), rejected_control_mfe_band="MFE_GE_1_5", rejected_control_mae_band="MAE_LT_0_5"),
    ]
    metrics = population_metrics(rows, "SOURCE_OPPORTUNITIES")
    assert metrics["control_failure_rejection_rate_pct"] == 50
    assert metrics["good_opportunity_rejection_rate_pct"] == 50
    assert metrics["filter_separation_pp"] == 0
    assert metrics["rejected_cohort"]["control_paths"] == {"NEITHER": 1, "STOP_FIRST": 1}


def test_matched_path_mfe_mae_rr_and_cost_metrics() -> None:
    metrics = population_metrics(
        [matched_row(), matched_row(control_path_outcome="TARGET_FIRST", treatment_path_outcome="TARGET_FIRST", control_favorable=True)],
        "SOURCE_OPPORTUNITIES",
    )
    assert metrics["matched_control_paths"]["STOP_FIRST"]["count"] == 1
    assert metrics["matched_treatment_paths"]["TARGET_FIRST"]["count"] == 1
    assert metrics["median_mfe_delta_r"] == Decimal("0.1")
    assert metrics["median_mae_delta_r"] == Decimal("-0.2")
    assert metrics["rr"]["median_delta"] == Decimal("-0.2")
    assert metrics["costs"]["median_cost_r_delta"] == Decimal("0.02")


@pytest.mark.parametrize(
    ("years", "expected"),
    [
        ((True, True, True), "CONSISTENT"),
        ((True, True, False), "MOSTLY_CONSISTENT"),
        ((False, False, True), "INVERSE"),
    ],
)
def test_temporal_consistency_classifications(years: tuple[bool, bool, bool], expected: str) -> None:
    assert temporal_consistency([yearly_row(support=value) for value in years]) == expected


def test_temporal_consistency_preserves_unstable_and_inconclusive() -> None:
    unstable = [yearly_row(support=True), {**yearly_row(support=False), "filter_separation_pp": Decimal("1")}, yearly_row(support=False)]
    assert temporal_consistency(unstable) == "UNSTABLE"
    assert temporal_consistency([yearly_row(), yearly_row(), yearly_row(confirmed=29)]) == "INCONCLUSIVE"


def test_yearly_sample_safety_uses_confirmed_treatment_count() -> None:
    rows = [
        matched_row(
            opportunity_id=f"{year}-01-{index + 1:02d}|TEST",
            decision_date=f"{year}-01-{index + 1:02d}",
        )
        for year in (2022, 2023, 2024)
        for index in range(30)
    ]
    assert [row["sample_safety"] for row in _yearly(rows)] == ["SMALL", "SMALL", "SMALL"]


def test_falsification_criteria_and_classification_are_mechanical() -> None:
    metrics = population_metrics(
        [matched_row(), matched_row(control_path_outcome="TARGET_FIRST", treatment_path_outcome="TARGET_FIRST", control_favorable=True)],
        "SOURCE_OPPORTUNITIES",
    )
    metrics["control_failure_rejection_rate_pct"] = Decimal("30")
    metrics["good_opportunity_rejection_rate_pct"] = Decimal("10")
    metrics["filter_separation_pp"] = Decimal("20")
    metrics["matched_control_paths"]["STOP_FIRST"]["rate_pct"] = Decimal("30")
    metrics["matched_treatment_paths"]["STOP_FIRST"]["rate_pct"] = Decimal("20")
    metrics["confirmed_count"] = 300
    criteria = falsification_results(metrics, [yearly_row()] * 3, "CONSISTENT")
    assert criteria["A"]["passed"] is True
    assert criteria["B"]["passed"] is True
    assert criteria["E"]["passed"] is True
    classifications = _classifications(metrics, criteria, "CONSISTENT")
    assert classifications["TEN_MINUTE_CONFIRMATION_RULE_RESULT"] == "SUPPORTED_FOR_NEXT_STAGE"
    assert classifications["ELIGIBLE_FOR_VALIDATION_CONSIDERATION"] == "YES"


def test_post_confirmation_path_excludes_confirmation_interval() -> None:
    confirmation_bar = bar(1, high="120", low="90")
    next_bar = bar(2, high="104", low="98")
    result = _path_metrics(
        confirmation_price=Decimal("100"),
        confirmation_timestamp=confirmation_bar.bar_end,
        stop=Decimal("95"),
        target=Decimal("110"),
        risk=Decimal("5"),
        all_bars=(confirmation_bar, next_bar),
        max_holding_date=date(2024, 1, 2),
    )
    assert result["post_confirmation_bar_count"] == 1
    assert result["post_first_touch"] == "NEITHER"
    assert result["mfe_confirm_r"] == Decimal("0.8")
    assert result["mae_confirm_r"] == Decimal("0.4")


def test_trade_level_cost_metadata_uses_frozen_quantity_and_baseline_slippage() -> None:
    row = matched_row(control_path_outcome="TARGET_FIRST", treatment_path_outcome="TARGET_FIRST")
    source = {
        "hypothetical_quantity": "10",
        "first_target_session": "1",
        "session_date_1": "2024-01-02",
        "session_date_4": "2024-01-05",
        "close_4": "102",
    }
    result = _cost_reference(row=row, source=source, entry=Decimal("100"), treatment=False)
    assert result["quantity_basis"] == "FROZEN_STRATEGY_V1_HYPOTHETICAL_QUANTITY"
    assert result["cost_model"] == "INDIA_EQUITY_COST_MODEL_V1"
    assert result["cost_scenario"] == "COST-SCENARIO-002"
    assert result["slippage_bps_per_side"] == 5
    assert result["estimated_round_trip_cost"] > 0


def test_pilot_contract_has_fourteen_real_case_slots_and_allows_na() -> None:
    pilot = _pilot([matched_row(symbol="TEST", decision_date="2024-01-01")])
    assert pilot["case_count"] == 14
    assert pilot["available_count"] + pilot["not_available_count"] == 14
    assert pilot["passed"] is True
    assert all(case["availability"] in {"AVAILABLE", "NOT_AVAILABLE"} for case in pilot["cases"])


def test_report_contract_contains_exactly_all_eleven_machine_reports() -> None:
    assert REPORT_FILENAMES == (
        "intraday_confirmation_rule_v1_summary.json",
        "intraday_confirmation_rule_v1_population.csv",
        "intraday_confirmation_rule_v1_matched.csv",
        "intraday_confirmation_rule_v1_confirmed.csv",
        "intraday_confirmation_rule_v1_rejected.csv",
        "intraday_confirmation_rule_v1_outcomes.csv",
        "intraday_confirmation_rule_v1_yearly.csv",
        "intraday_confirmation_rule_v1_rr.csv",
        "intraday_confirmation_rule_v1_costs.csv",
        "intraday_confirmation_rule_v1_contexts.csv",
        "intraday_confirmation_rule_v1_pilot.csv",
    )


def test_machine_report_writers_are_offline_and_decimal_safe() -> None:
    output_root = Path("tmp/intraday_confirmation_rule_writer_test")
    json_path = output_root / "report.json"
    csv_path = output_root / "report.csv"
    payload = [{"value": Decimal("1.25"), "nested": {"sealed": True}}]
    _write_json(json_path, payload)
    _write_csv(csv_path, payload)
    try:
        assert json.loads(json_path.read_text(encoding="utf-8"))[0]["value"] == "1.25"
        assert "1.25" in csv_path.read_text(encoding="utf-8")
        assert json_ready(payload)[0]["nested"]["sealed"] is True
    finally:
        json_path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        output_root.rmdir()

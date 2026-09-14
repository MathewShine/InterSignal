from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.diagnostics.strategy_diagnostic import canonical_hash, write_csv, write_json
from app.research.strategy.rr_cap4_holdout_validation import (
    ALIGNMENT_RULES,
    AUTHORIZATION_REFERENCE,
    EXPECTED_DEVELOPMENT_FREEZE_HASH,
    EXPECTED_DEVELOPMENT_POPULATION_HASH,
    EXPECTED_PARAMETER_HASH,
    EXPECTED_PREREGISTRATION_HASH,
    FrozenAuthorizationArtifact,
    REPORT_FILENAMES,
    SUCCESS_CRITERIA,
    VALIDATION_RECORD_ID,
    VALIDATION_VERSION,
    _validation_population_rows,
    artifact_root,
    build_validation_plan,
    classify_validation,
    development_validation_alignment,
    ensure_validation_is_pristine,
    freeze_validation_population,
    persist_authorization,
    persist_started_record,
    run_validation_portfolios,
    validate_holdout_date,
    validate_plan,
    validation_cost_conclusion,
    validation_fifth_point_result,
    validation_success_criteria,
    validation_temporal_consistency,
    verify_frozen_experiment,
)
from app.research.strategy.rr_score_mapping_experiment import CONTROL_MAPPING, TREATMENT_MAPPING
from app.research.temporal_validation.config import (
    AUTHORIZED_TO_EVALUATE,
    EVALUATED,
    SEALED,
    VALIDATION_RUN,
)
from app.research.temporal_validation.guard import ValidationAccessError, ValidationAccessGuard


REPO_ROOT = Path(__file__).resolve().parents[2]


def profile(
    *,
    count: int = 100,
    mfe: str = "0.5",
    mae: str = "0.5",
    target: str = "10",
    stop: str = "20",
    ratio: str = "0.25",
    distance: str = "10",
) -> dict[str, object]:
    return {
        "count": count,
        "median_mfe_r": Decimal(mfe),
        "median_mae_r": Decimal(mae),
        "target_first_rate_pct": Decimal(target),
        "stop_first_rate_pct": Decimal(stop),
        "median_mfe_to_target_r_ratio": Decimal(ratio),
        "median_target_distance_pct": Decimal(distance),
    }


def yearly(directions: tuple[str, str], *, count: int = 100) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for year, direction in zip((2025, 2026), directions, strict=True):
        rr4 = profile(count=count)
        if direction == "support":
            rr5 = profile(count=count, mfe="0.4", mae="0.6", target="7", ratio="0.2")
        elif direction == "oppose":
            rr5 = profile(count=count, mfe="0.6", mae="0.4", target="13", ratio="0.3")
        else:
            rr5 = profile(count=count, mfe="0.6", mae="0.6", target="7", ratio="0.3")
        rows.extend(({**rr4, "year": year, "control_rr_points": 4}, {**rr5, "year": year, "control_rr_points": 5}))
    return rows


def validation_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "opportunity_id": "2025-01-01|TEST",
        "symbol": "TEST",
        "decision_date": "2025-01-01",
        "effective_rr": Decimal("2.5"),
        "frozen_effective_rr": Decimal("2.5"),
        "control_rr_points": 5,
        "treatment_rr_points": 4,
        "control_raw_score": 80,
        "frozen_control_score": 80,
        "treatment_raw_score": 79,
        "control_entry_eligible": True,
        "treatment_entry_eligible": False,
        "eligibility_transition": "CONTROL_ONLY",
        "target_distance_pct": Decimal("20"),
        "target_distance_r": Decimal("2.5"),
        "outcome_linkage": {"source_key": "2025-01-01|TEST"},
        "portfolio_linkage": {"frozen_admitted": False},
        "mfe_r_4": Decimal("0.5"),
        "mae_r_4": Decimal("0.5"),
        "first_touch_outcome": "NEITHER_WITHIN_HORIZON",
        "close_return_pct_4": Decimal("0"),
        "candidate_stage": "BOTH_ELIGIBLE",
        "setup_quality": "STRONG",
    }
    row.update(updates)
    return row


def test_validation_identity_and_frozen_hash_contract() -> None:
    assert VALIDATION_VERSION == "RR_CAP4_HOLDOUT_VALIDATION_V1"
    assert VALIDATION_RECORD_ID == "VAL-RRCAL-001"
    assert EXPECTED_DEVELOPMENT_POPULATION_HASH == "6a6b12b608812318f81331e3e2ad66fe5fe1fffc091bf86d1018623396dca523"
    assert EXPECTED_PARAMETER_HASH == "ce07c6defad1b5f43902057d2f9be9350ab44d3c8bb6b72b17cd222a0b04586c"
    assert EXPECTED_PREREGISTRATION_HASH == "22d79a991043d5b83f616d15c1a8ac5b14472abb03d4c3ee7db92c2238ab3c7e"
    assert EXPECTED_DEVELOPMENT_FREEZE_HASH == "d31d4dc891258535a7a16c4edc0a530191af64faa6ba4931eb84d9dadc57c4d2"


def test_current_frozen_experiment_verifies_without_validation_access() -> None:
    frozen = verify_frozen_experiment(REPO_ROOT)
    assert frozen["experiment_id"] == "EXP-RRCAL-001"
    assert frozen["population_hash"] == EXPECTED_DEVELOPMENT_POPULATION_HASH
    assert frozen["parameter_hash"] == EXPECTED_PARAMETER_HASH
    assert frozen["preregistration_hash"] == EXPECTED_PREREGISTRATION_HASH
    assert frozen["development_freeze_hash"] == EXPECTED_DEVELOPMENT_FREEZE_HASH


def test_validation_plan_freezes_one_mapping_threshold_window_and_rules() -> None:
    plan = build_validation_plan(
        {
            "population_hash": EXPECTED_DEVELOPMENT_POPULATION_HASH,
            "parameter_hash": EXPECTED_PARAMETER_HASH,
            "preregistration_hash": EXPECTED_PREREGISTRATION_HASH,
            "development_freeze_hash": EXPECTED_DEVELOPMENT_FREEZE_HASH,
        }
    )
    validate_plan(plan)
    assert plan["validated_experiment_id"] == "EXP-RRCAL-001"
    assert plan["control_mapping"] == CONTROL_MAPPING
    assert plan["treatment_mapping"] == TREATMENT_MAPPING
    assert plan["entry_threshold"] == 80
    assert plan["validation_window"]["start"] == "2025-01-01"
    assert plan["validation_window"]["terminal_date"] == "2026-08-13"
    assert plan["validation_window"]["partition_basis"] == "DECISION_DATE"
    assert plan["portfolio_mechanics"] == PortfolioBacktestConfig().snapshot()
    assert plan["alternative_mappings_allowed"] is False
    assert plan["retuning_allowed"] is False
    assert plan["intraday_combination_allowed"] is False
    assert plan["score_v2_allowed"] is False
    assert plan["strategy_v2_allowed"] is False
    assert plan["automatic_promotion_allowed"] is False
    assert plan["validation_plan_hash"] == canonical_hash({key: value for key, value in plan.items() if key != "validation_plan_hash"})


def test_explicit_authorization_and_state_transitions_are_enforced() -> None:
    artifact = FrozenAuthorizationArtifact()
    guard = ValidationAccessGuard()
    with pytest.raises(ValidationAccessError, match="Explicit"):
        guard.authorize_validation(
            artifact,
            supplied_freeze_hash=EXPECTED_DEVELOPMENT_FREEZE_HASH,
            explicit_user_authorized=False,
            authorization_reference=AUTHORIZATION_REFERENCE,
        )
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=EXPECTED_DEVELOPMENT_FREEZE_HASH,
        explicit_user_authorized=True,
        authorization_reference=AUTHORIZATION_REFERENCE,
    )
    assert guard.state == AUTHORIZED_TO_EVALUATE
    assert guard.validation_run_count == 0
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    assert guard.validation_run_count == 1
    guard.record_validation_result("a" * 64)
    assert guard.state == EVALUATED
    with pytest.raises(ValidationAccessError):
        guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)


def test_wrong_frozen_hash_is_rejected_before_authorization() -> None:
    with pytest.raises(ValidationAccessError, match="hash mismatch"):
        ValidationAccessGuard().authorize_validation(
            FrozenAuthorizationArtifact(),
            supplied_freeze_hash="f" * 64,
            explicit_user_authorized=True,
            authorization_reference=AUTHORIZATION_REFERENCE,
        )


def test_authorization_and_start_markers_persist_run_count_one(tmp_path: Path) -> None:
    artifact = FrozenAuthorizationArtifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=EXPECTED_DEVELOPMENT_FREEZE_HASH,
        explicit_user_authorized=True,
        authorization_reference=AUTHORIZATION_REFERENCE,
    )
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    auth_path = persist_authorization(tmp_path, authorization, authorized_at="2026-09-12T00:00:00Z")
    record_path = persist_started_record(
        tmp_path,
        authorization,
        authorized_at="2026-09-12T00:00:00Z",
        started_at="2026-09-12T00:00:01Z",
    )
    assert json.loads(auth_path.read_text(encoding="utf-8"))["authorization_count"] == 1
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["state"] == AUTHORIZED_TO_EVALUATE
    assert record["initial_validation_run_count"] == 0
    assert record["validation_run_count"] == 1
    assert record["validation_consumed"] is True
    with pytest.raises(ValidationAccessError, match="already consumed"):
        ensure_validation_is_pristine(tmp_path)


@pytest.mark.parametrize("decision", ["2025-01-01", "2026-08-13"])
def test_exact_validation_window_accepts_boundaries(decision: str) -> None:
    validate_holdout_date(decision)


@pytest.mark.parametrize("decision", ["2024-12-31", "2026-08-14", "2027-01-01"])
def test_validation_partition_rejects_development_and_terminal_extension(decision: str) -> None:
    with pytest.raises(ValueError, match="Non-validation"):
        validate_holdout_date(decision)


@pytest.mark.parametrize(
    ("rr", "control", "treatment", "control_score", "treatment_score"),
    [("1.4", 0, 0, 80, 80), ("1.5", 3, 3, 83, 83), ("2", 4, 4, 84, 84), ("2.5", 5, 4, 80, 79), ("10", 5, 4, 85, 84)],
)
def test_synthetic_population_applies_only_frozen_cap4(
    rr: str, control: int, treatment: int, control_score: int, treatment_score: int
) -> None:
    key = "2025-01-02|TEST"
    outcome = {
        "decision_date": "2025-01-02", "symbol": "TEST", "source_scoring_disposition": "ENTRY_ELIGIBLE",
        "outcome_version": "STRATEGY_OUTCOME_V1", "outcome_profile": "SWING_DAILY_OUTCOME_V1",
        "outcome_config_hash": "hash", "next_session_date": "2025-01-03", "candidate_category": "BOTH_ELIGIBLE",
        "setup_quality": "STRONG", "regime_state": "BULLISH",
    }
    non_rr = control_score - control
    source = {
        "source_key": key, "rr_points": control, "raw_strategy_score": control_score,
        "setup_points": non_rr, "momentum_points": 0, "rvol_points": 0, "rs_points": 0, "regime_points": 0,
        "target_distance_pct": "20", "target_distance_r": rr, "is_admitted": False,
        "mfe_r_4": "0.5", "mae_r_4": "0.5", "first_touch_outcome": "NEITHER_WITHIN_HORIZON",
        "close_return_pct_4": "0", "portfolio_exit_reason": "", "realized_r_multiple": "", "gross_pnl": "",
    }
    score_input = {
        "reward_risk_ratio": rr, "sector_points": "0", "catalyst_points": "0",
        "final_strategy_score_status": "COMPLETE",
    }
    manifest, analysis = _validation_population_rows([outcome], [source], {key: score_input})
    assert len(manifest) == len(analysis) == 1
    assert manifest[0]["control_rr_points"] == control
    assert manifest[0]["treatment_rr_points"] == treatment
    assert manifest[0]["control_raw_score"] == control_score
    assert manifest[0]["treatment_raw_score"] == treatment_score
    assert sum(int(manifest[0][field]) for field in ("setup_points", "momentum_points", "rvol_points", "rs_points", "regime_points", "sector_points", "catalyst_points")) == non_rr
    assert manifest[0]["effective_rr"] == Decimal(rr)


def test_validation_population_hash_is_order_independent_and_rejects_bad_rows() -> None:
    first = validation_row()
    second = validation_row(opportunity_id="2026-08-13|OTHER", symbol="OTHER", decision_date="2026-08-13")
    assert freeze_validation_population([first, second]) == freeze_validation_population([second, first])
    with pytest.raises(ValueError, match="Duplicate"):
        freeze_validation_population([first, first])
    with pytest.raises(ValueError, match="Non-validation"):
        freeze_validation_population([{**first, "decision_date": "2024-01-01"}])


@pytest.mark.parametrize(
    ("rr5", "expected"),
    [
        (profile(mfe="0.35", mae="0.65", target="6", ratio="0.19", distance="25"), "CONFIRMS_NONPOSITIVE_VALUE"),
        (profile(mfe="0.50", mae="0.65", target="10", ratio="0.19", distance="25"), "CONFIRMS_NONPOSITIVE_VALUE"),
        (profile(mfe="0.65", mae="0.65", target="10", ratio="0.19", distance="25"), "PARTIALLY_CONFIRMS"),
        (profile(mfe="0.65", mae="0.35", target="14", ratio="0.31", distance="25"), "CONTRADICTS_DEVELOPMENT"),
        (profile(mfe="0.65", mae="0.65", target="14", ratio="0.19", distance="25"), "MIXED"),
        (profile(count=29, distance="25"), "INCONCLUSIVE"),
    ],
)
def test_holdout_fifth_point_result_classes(rr5: dict[str, object], expected: str) -> None:
    rr4 = profile(count=int(rr5["count"]))
    assert validation_fifth_point_result(rr4, rr5)[0] == expected


@pytest.mark.parametrize(
    ("directions", "expected"),
    [
        (("support", "support"), "CONSISTENT"),
        (("support", "mixed"), "MOSTLY_CONSISTENT"),
        (("support", "oppose"), "UNSTABLE"),
        (("oppose", "oppose"), "CONTRADICTORY"),
        (("mixed", "mixed"), "UNSTABLE"),
    ],
)
def test_validation_temporal_result_classes(directions: tuple[str, str], expected: str) -> None:
    assert validation_temporal_consistency(yearly(directions))[0] == expected


def test_validation_temporal_result_is_inconclusive_for_small_cell() -> None:
    assert validation_temporal_consistency(yearly(("support", "support"), count=29))[0] == "INCONCLUSIVE"


def test_validation_portfolios_start_independently_and_treatment_only_changes_score(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[dict[str, object]]] = []

    def fake_simulate(*, opportunities: list[dict[str, object]], trading_dates: list[date], config: PortfolioBacktestConfig) -> dict[str, object]:
        calls.append(opportunities)
        return {"trades": [], "skipped": [], "daily": [], "all_invariants_valid": True, "invariants": {}}

    def fake_summary(_simulation: dict[str, object], opportunities: list[dict[str, object]]) -> dict[str, object]:
        return {"portfolio": {"starting_equity": Decimal("100000"), "ending_equity": Decimal("100000"), "maximum_drawdown_pct": Decimal("0")}, "trades": {"completed_trades": 0}, "skip_count": 0, "all_invariants_valid": True}

    monkeypatch.setattr("app.research.strategy.rr_cap4_holdout_validation.build_trading_calendar", lambda _data, _rows: [date(2025, 1, 2)])
    monkeypatch.setattr("app.research.strategy.rr_cap4_holdout_validation.simulate_portfolio", fake_simulate)
    monkeypatch.setattr("app.research.strategy.rr_cap4_holdout_validation.portfolio_summary", fake_summary)
    context = type("Context", (), {"data_dir": Path("unused")})()
    outcomes = [{"decision_date": "2025-01-01", "symbol": "TEST", "raw_strategy_score": "80"}]
    rows = [validation_row()]
    result = run_validation_portfolios(context, outcomes, rows)
    assert result["control_summary"]["portfolio"]["starting_equity"] == 100000
    assert result["treatment_summary"]["portfolio"]["starting_equity"] == 100000
    assert len(calls[0]) == 1
    assert calls[1] == []


@pytest.mark.parametrize(
    ("gross_control", "gross_treatment", "net_control", "net_treatment", "expected"),
    [
        ("100000", "102000", "100000", "102000", "SUPPORTS_TREATMENT"),
        ("100", "110", "90", "80", "REVERSES_TREATMENT"),
        ("100", "110", "-10", "-5", "BOTH_WEAK"),
        ("100", "100", "100", "100.5", "NEUTRAL"),
    ],
)
def test_validation_cost_conclusions(
    gross_control: str, gross_treatment: str, net_control: str, net_treatment: str, expected: str
) -> None:
    control_port = {"portfolio": {"ending_equity": Decimal(gross_control)}}
    treatment_port = {"portfolio": {"ending_equity": Decimal(gross_treatment)}}
    control_cost = {"summary": {"ending_equity": Decimal(net_control), "net_return_pct": Decimal(net_control)}}
    treatment_cost = {"summary": {"ending_equity": Decimal(net_treatment), "net_return_pct": Decimal(net_treatment)}}
    assert validation_cost_conclusion(control_port, treatment_port, control_cost, treatment_cost)[0] == expected


def passing_criteria() -> dict[str, dict[str, object]]:
    return {key: {"passed": True} for key in "ABCDEFG"}


@pytest.mark.parametrize(
    ("fifth", "temporal", "failed", "expected"),
    [
        ("CONFIRMS_NONPOSITIVE_VALUE", "CONSISTENT", "", "VALIDATED"),
        ("MIXED", "UNSTABLE", "", "PARTIALLY_VALIDATED"),
        ("CONFIRMS_NONPOSITIVE_VALUE", "CONSISTENT", "C", "FAILED"),
        ("INCONCLUSIVE", "INCONCLUSIVE", "", "INCONCLUSIVE"),
        ("CONFIRMS_NONPOSITIVE_VALUE", "CONSISTENT", "G", "INCONCLUSIVE"),
    ],
)
def test_validation_result_classification(fifth: str, temporal: str, failed: str, expected: str) -> None:
    criteria = passing_criteria()
    if failed:
        criteria[failed]["passed"] = False
    result = classify_validation(criteria, fifth_result=fifth, temporal=temporal)
    assert result["RR_CAP4_HOLDOUT_VALIDATION_RESULT"] == expected
    assert result["PROMOTED_TO_STRATEGY_V1"] is False
    assert result["RR_CAP4_SCORE_CHANGE_READINESS"] in {"CANDIDATE_FOR_STRATEGY_V2_DESIGN", "MORE_RESEARCH_REQUIRED", "REJECTED", "INCONCLUSIVE"}


def test_each_predeclared_success_criterion_is_evaluated() -> None:
    rr4 = profile(distance="10")
    rr5 = profile(mfe="0.4", mae="0.6", target="7", stop="25", ratio="0.2", distance="25")
    control_port = {"portfolio": {"ending_equity": Decimal("100000"), "maximum_drawdown_pct": Decimal("10")}}
    treatment_port = {"portfolio": {"ending_equity": Decimal("101000"), "maximum_drawdown_pct": Decimal("11")}}
    control_cost = {"summary": {"ending_equity": Decimal("60000")}}
    treatment_cost = {"summary": {"ending_equity": Decimal("61000")}}
    result = validation_success_criteria(
        rr4=rr4, rr5=rr5, fifth_result="CONFIRMS_NONPOSITIVE_VALUE", base_discrimination="NEGATIVE_VALUE",
        temporal="CONSISTENT", control_portfolio=control_port, treatment_portfolio=treatment_port,
        control_cost=control_cost, treatment_cost=treatment_cost,
        cost_evidence={"gross_advantage_reversed": False},
        trade_comparison={"unexplained_changed_trade_count": 0, "jaccard_similarity": Decimal("0.8"), "all_treatment_only_are_source_eligible_replacements": True},
        source_treatment_only_count=0, integrity_ok=True,
    )
    assert set(result) == set("ABCDEFG") == set(SUCCESS_CRITERIA)
    assert all(item["passed"] for item in result.values())


def test_development_validation_alignment_is_rule_driven() -> None:
    development = {"portfolios": {"control": {"portfolio": {"ending_equity": "100"}}, "treatment": {"portfolio": {"ending_equity": "110"}}}}
    rr4 = profile(distance="10")
    rr5 = profile(mfe="0.4", mae="0.6", target="7", stop="25", ratio="0.2", distance="25")
    control = {"portfolio": {"ending_equity": Decimal("100")}}
    treatment = {"portfolio": {"ending_equity": Decimal("105")}}
    result, evidence = development_validation_alignment(
        development, rr4, rr5, "CONFIRMS_NONPOSITIVE_VALUE", control, treatment,
        {"jaccard_similarity": Decimal("0.8")},
    )
    assert result == "STRONG_ALIGNMENT"
    assert len(evidence) == 6
    assert set(ALIGNMENT_RULES) == {"STRONG_ALIGNMENT", "PARTIAL_ALIGNMENT", "WEAK_ALIGNMENT", "CONTRADICTORY", "INCONCLUSIVE"}


def test_validation_result_hash_is_immutable_in_guard() -> None:
    artifact = FrozenAuthorizationArtifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=EXPECTED_DEVELOPMENT_FREEZE_HASH,
        explicit_user_authorized=True,
        authorization_reference=AUTHORIZATION_REFERENCE,
    )
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    payload = {"validation_record_id": VALIDATION_RECORD_ID, "result": "fixture"}
    result_hash = canonical_hash(payload)
    guard.record_validation_result(result_hash)
    assert guard.immutable_result_hash == result_hash
    with pytest.raises(ValidationAccessError):
        guard.record_validation_result(canonical_hash({"changed": True}))


def test_exact_fourteen_report_contract() -> None:
    assert REPORT_FILENAMES == (
        "rr_cap4_validation_v1_summary.json", "rr_cap4_validation_v1_population.csv",
        "rr_cap4_validation_v1_score_transitions.csv", "rr_cap4_validation_v1_rr4_vs_rr5.csv",
        "rr_cap4_validation_v1_removed_cohort.csv", "rr_cap4_validation_v1_retained_cohort.csv",
        "rr_cap4_validation_v1_yearly.csv", "rr_cap4_validation_v1_control_portfolio.csv",
        "rr_cap4_validation_v1_treatment_portfolio.csv", "rr_cap4_validation_v1_trade_sets.csv",
        "rr_cap4_validation_v1_replacements.csv", "rr_cap4_validation_v1_costs.csv",
        "rr_cap4_validation_v1_dev_vs_validation.csv", "rr_cap4_validation_v1_pilot.csv",
    )


def test_machine_report_writers_are_offline_and_decimal_safe(tmp_path: Path) -> None:
    payload = [{"value": Decimal("1.25"), "state": EVALUATED}]
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    write_json(json_path, payload)
    write_csv(csv_path, payload)
    assert '"1.25"' in json_path.read_text(encoding="utf-8")
    assert "1.25" in csv_path.read_text(encoding="utf-8")


def test_output_root_is_isolated_from_development_artifacts() -> None:
    root = artifact_root(REPO_ROOT)
    assert root.as_posix().endswith("data/research/validation/experiments/rr_cap4_val_001")
    assert "rr_cap4_command_01" not in root.as_posix()
    assert date(2025, 1, 1) <= date(2026, 8, 13)

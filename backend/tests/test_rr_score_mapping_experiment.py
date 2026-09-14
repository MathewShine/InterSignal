from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.diagnostics.strategy_diagnostic import canonical_hash, write_csv, write_json
from app.research.strategy.rr_score_mapping_experiment import (
    CONTROL_MAPPING,
    CONTROL_MAPPING_NAME,
    ENTRY_THRESHOLD,
    EXPECTED_CONTROL_ENDING_EQUITY,
    EXPECTED_DEVELOPMENT_SOURCE_COUNT,
    EXPERIMENT_ID,
    EXPERIMENT_TYPE,
    EXPERIMENT_VERSION,
    FALSIFICATION_CRITERIA,
    PROFILE,
    REPORT_FILENAMES,
    TREATMENT_MAPPING,
    TREATMENT_MAPPING_NAME,
    baseline_snapshot,
    build_development_freeze,
    build_pilot,
    build_population,
    build_preregistration,
    classify_experiment,
    cohort_summary,
    control_rr_points,
    cost_overlay,
    eligibility_transition,
    falsification_results,
    fifth_point_discrimination,
    freeze_population,
    preregistration_dependencies,
    replacement_trade_rows,
    retained_improvement,
    run_independent_portfolios,
    sample_warning,
    score_calibration_rows,
    score_distribution,
    score_transition_rows,
    temporal_consistency,
    trade_set_comparison,
    treatment_rr_points,
    treatment_score,
    validate_development_only,
    yearly_component_rows,
)
from app.research.temporal_validation.config import SEALED


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_POPULATION_HASH = "6a6b12b608812318f81331e3e2ad66fe5fe1fffc091bf86d1018623396dca523"
EXPECTED_PARAMETER_HASH = "ce07c6defad1b5f43902057d2f9be9350ab44d3c8bb6b72b17cd222a0b04586c"
EXPECTED_PREREGISTRATION_HASH = "22d79a991043d5b83f616d15c1a8ac5b14472abb03d4c3ee7db92c2238ab3c7e"
EXPECTED_FREEZE_HASH = "d31d4dc891258535a7a16c4edc0a530191af64faa6ba4931eb84d9dadc57c4d2"


@pytest.fixture(scope="session")
def population_bundle() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object]:
    return build_population(REPO_ROOT)


@pytest.fixture(scope="session")
def portfolio_bundle(population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object]) -> dict[str, object]:
    _manifest, analysis, outcomes, context = population_bundle
    return run_independent_portfolios(context, outcomes, analysis)


@pytest.fixture(scope="session")
def trade_comparison(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
    portfolio_bundle: dict[str, object],
) -> dict[str, object]:
    _manifest, analysis, _outcomes, _context = population_bundle
    return trade_set_comparison(
        portfolio_bundle["control_simulation"]["trades"],
        portfolio_bundle["treatment_simulation"]["trades"],
        analysis,
    )


@pytest.fixture(scope="session")
def cost_overlays(portfolio_bundle: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    return (
        cost_overlay(portfolio_bundle["control_simulation"], "CONTROL"),
        cost_overlay(portfolio_bundle["treatment_simulation"], "TREATMENT"),
    )


def metric_profile(
    *,
    count: int = 300,
    mfe: str = "0.50",
    mae: str = "0.50",
    target_rate: str = "10",
    ratio: str = "0.25",
    target_distance: str = "10",
) -> dict[str, object]:
    return {
        "count": count,
        "median_mfe_r": Decimal(mfe),
        "median_mae_r": Decimal(mae),
        "target_first_rate_pct": Decimal(target_rate),
        "median_mfe_to_target_r_ratio": Decimal(ratio),
        "median_target_distance_pct": Decimal(target_distance),
    }


def cohort_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "opportunity_id": "2024-01-01|TEST",
        "symbol": "TEST",
        "decision_date": "2024-01-01",
        "effective_rr": Decimal("2.5"),
        "frozen_effective_rr": Decimal("2.5"),
        "target_distance_pct": Decimal("20"),
        "target_distance_r": Decimal("2.5"),
        "mfe_r_4": Decimal("0.5"),
        "mae_r_4": Decimal("0.4"),
        "first_touch_outcome": "NEITHER_WITHIN_HORIZON",
        "close_return_pct_4": Decimal("0.1"),
        "candidate_stage": "BOTH_ELIGIBLE",
        "setup_quality": "STRONG",
        "frozen_control_score": 80,
        "treatment_raw_score": 79,
        "control_rr_points": 5,
        "treatment_rr_points": 4,
        "control_entry_eligible": True,
        "treatment_entry_eligible": False,
        "eligibility_transition": "CONTROL_ONLY",
    }
    row.update(updates)
    return row


def temporal_rows(directions: tuple[str, str, str], *, count: int = 100) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for year, direction in zip((2022, 2023, 2024), directions, strict=True):
        rr4 = metric_profile(count=count)
        if direction == "support":
            rr5 = metric_profile(count=count, mfe="0.40", mae="0.60", target_rate="7", ratio="0.20")
        elif direction == "oppose":
            rr5 = metric_profile(count=count, mfe="0.60", mae="0.40", target_rate="13", ratio="0.30")
        else:
            rr5 = metric_profile(count=count, mfe="0.60", mae="0.60", target_rate="7", ratio="0.30")
        rows.extend(
            (
                {**rr4, "year": year, "control_rr_points": 4},
                {**rr5, "year": year, "control_rr_points": 5},
            )
        )
    return rows


def test_contract_identity_and_exact_single_mapping_change() -> None:
    assert EXPERIMENT_VERSION == "RR_SCORE_MAPPING_CONTROLLED_EXPERIMENT_V1"
    assert EXPERIMENT_ID == "EXP-RRCAL-001"
    assert PROFILE == "RR_CAP4_DEVELOPMENT_V1"
    assert EXPERIMENT_TYPE == "DEVELOPMENT_ONLY_CONTROLLED_SCORE_COMPONENT_EXPERIMENT"
    assert ENTRY_THRESHOLD == 80
    assert CONTROL_MAPPING_NAME == "RR_SCORE_MAPPING_V1"
    assert TREATMENT_MAPPING_NAME == "RR_SCORE_MAPPING_CAP4_V1"
    assert CONTROL_MAPPING == {"LT_1_5": 0, "GTE_1_5_LT_2": 3, "GTE_2_LT_2_5": 4, "GTE_2_5": 5}
    assert TREATMENT_MAPPING == {"LT_1_5": 0, "GTE_1_5_LT_2": 3, "GTE_2": 4}


@pytest.mark.parametrize(
    ("rr", "control", "treatment"),
    [
        ("0", 0, 0),
        ("1.499999", 0, 0),
        ("1.5", 3, 3),
        ("1.999999", 3, 3),
        ("2", 4, 4),
        ("2.499999", 4, 4),
        ("2.5", 5, 4),
        ("20", 5, 4),
    ],
)
def test_exact_control_and_cap4_mapping_boundaries(rr: str, control: int, treatment: int) -> None:
    assert control_rr_points(rr) == control
    assert treatment_rr_points(rr) == treatment


@pytest.mark.parametrize(
    ("control_eligible", "treatment_eligible", "expected"),
    [
        (True, True, "ELIGIBLE_BOTH"),
        (True, False, "CONTROL_ONLY"),
        (False, True, "TREATMENT_ONLY"),
        (False, False, "INELIGIBLE_BOTH"),
    ],
)
def test_eligibility_transition_labels(control_eligible: bool, treatment_eligible: bool, expected: str) -> None:
    assert eligibility_transition(control_eligible, treatment_eligible) == expected


def test_score_arithmetic_changes_only_the_fifth_point() -> None:
    assert treatment_score(80, 5, 4) == 79
    assert treatment_score(85, 5, 4) == 84
    assert treatment_score(84, 4, 4) == 84


@pytest.mark.parametrize("decision", ["2022-01-01", "2024-12-31"])
def test_development_window_accepts_boundaries(decision: str) -> None:
    validate_development_only(decision)


@pytest.mark.parametrize("decision", ["2021-12-31", "2025-01-01", "2026-08-13"])
def test_development_window_rejects_validation_and_out_of_window_dates(decision: str) -> None:
    with pytest.raises(ValueError, match="rejected"):
        validate_development_only(decision)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "VERY_SMALL"), (29, "VERY_SMALL"), (30, "SMALL"), (99, "SMALL"), (100, "LIMITED"), (299, "LIMITED"), (300, "ADEQUATE_FOR_DESCRIPTION")],
)
def test_sample_warning_boundaries(count: int, expected: str) -> None:
    assert sample_warning(count) == expected


def test_preregistration_freezes_exactly_one_controlled_experiment() -> None:
    dependencies = {"score_v1": {"hash": "frozen"}}
    before = deepcopy(dependencies)
    prereg = build_preregistration("population", dependencies)
    experiment = prereg["experiments"][0]
    parameters = experiment["parameters"]
    assert dependencies == before
    assert prereg["experiment_count"] == 1
    assert prereg["experiment_ids"] == [EXPERIMENT_ID]
    assert experiment["experiment_id"] == EXPERIMENT_ID
    assert experiment["pre_registered"] is True
    assert parameters["control_mapping"] == CONTROL_MAPPING
    assert parameters["treatment_mapping"] == TREATMENT_MAPPING
    assert parameters["entry_threshold"] == 80
    assert parameters["validation_state"] == SEALED
    assert parameters["validation_run_count"] == 0
    assert parameters["alternative_mappings_allowed"] is False
    assert parameters["optimizer_allowed"] is False
    assert parameters["intraday_combination_allowed"] is False
    assert parameters["score_v2_allowed"] is False
    assert parameters["strategy_v2_allowed"] is False
    assert parameters["promotion_allowed"] is False
    assert parameters["validation_authorized"] is False


def test_preregistration_parameter_and_registry_hashes_are_deterministic() -> None:
    prereg = build_preregistration("population", {"dependency": "frozen"})
    experiment = prereg["experiments"][0]
    assert experiment["parameter_hash"] == canonical_hash(experiment["parameters"])
    body = {key: value for key, value in experiment.items() if key != "pre_registration_hash"}
    assert experiment["pre_registration_hash"] == canonical_hash(body)
    assert prereg["rr_cap4_preregistration_hash"] == canonical_hash([body])
    assert prereg == build_preregistration("population", {"dependency": "frozen"})


def test_development_freeze_carries_governed_fields_and_hash() -> None:
    prereg = build_preregistration("population", {"dependency": "frozen"})
    freeze = build_development_freeze("population", prereg)
    body = {key: value for key, value in freeze.items() if key != "development_freeze_hash"}
    assert freeze["experiment_id"] == EXPERIMENT_ID
    assert freeze["control_mapping"] == CONTROL_MAPPING
    assert freeze["treatment_mapping"] == TREATMENT_MAPPING
    assert freeze["threshold"] == 80
    assert freeze["validation_authorized"] is False
    assert freeze["falsification_criteria"] == FALSIFICATION_CRITERIA
    assert freeze["cost_model"]["mode"] == "FROZEN_TRADE_SET_OVERLAY_NOT_COST_AWARE_ADMISSION"
    assert freeze["development_freeze_hash"] == canonical_hash(body)


def test_real_population_is_development_only_complete_and_frozen(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    manifest, analysis, outcomes, _context = population_bundle
    assert len(manifest) == len(analysis) == len(outcomes) == EXPECTED_DEVELOPMENT_SOURCE_COUNT
    assert freeze_population(manifest) == EXPECTED_POPULATION_HASH
    assert all(date(2022, 1, 1) <= date.fromisoformat(str(row["decision_date"])) <= date(2024, 12, 31) for row in analysis)
    assert not any(str(row["decision_date"]) >= "2025-01-01" for row in analysis)


def test_real_population_preserves_every_non_rr_component_and_continuous_rr(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    components = ("setup_points", "momentum_points", "rvol_points", "rs_points", "regime_points", "sector_points", "catalyst_points")
    assert all(row["effective_rr"] == row["frozen_effective_rr"] for row in analysis)
    assert all(
        int(row["treatment_raw_score"])
        == sum(int(row[field]) for field in components) + int(row["treatment_rr_points"])
        for row in analysis
    )
    assert all(int(row["treatment_rr_points"]) <= int(row["control_rr_points"]) for row in analysis)
    assert not any(row["eligibility_transition"] == "TREATMENT_ONLY" for row in analysis)


def test_real_score_transitions_and_distributions_match_the_frozen_mechanical_effect(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    transitions = {(row["control_score"], row["treatment_score"]): row["count"] for row in score_transition_rows(analysis)}
    assert transitions == {
        (80, 79): 82,
        (80, 80): 541,
        (81, 80): 144,
        (81, 81): 61,
        (82, 81): 10,
        (82, 82): 294,
        (83, 82): 89,
        (83, 83): 119,
        (84, 83): 18,
        (84, 84): 569,
        (85, 84): 141,
    }
    distributions = {row["score"]: (row["control_count"], row["treatment_count"]) for row in score_distribution(analysis)}
    assert distributions == {79: (0, 82), 80: (623, 685), 81: (205, 71), 82: (304, 383), 83: (208, 137), 84: (587, 710), 85: (141, 0)}
    assert sum(int(row["treatment_raw_score"]) == int(row["frozen_control_score"]) - 1 for row in analysis) == 484


def test_removed_and_retained_cohorts_are_separate_and_interpretable(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    control = [row for row in analysis if row["control_entry_eligible"]]
    removed = [row for row in analysis if row["eligibility_transition"] == "CONTROL_ONLY"]
    retained = [row for row in analysis if row["eligibility_transition"] == "ELIGIBLE_BOTH"]
    removed_profile = cohort_summary(removed, cohort="CONTROL_ONLY")
    improvement = retained_improvement(control, retained)
    assert removed_profile["count"] == 82
    assert removed_profile["sample_warning"] == "SMALL"
    assert removed_profile["median_effective_rr"] == Decimal("4.978459256366")
    assert removed_profile["target_first_count"] == 1
    assert removed_profile["stop_first_count"] == 29
    assert improvement["retained"]["count"] == 1986
    assert improvement["improved_dimension_count"] == 3


@pytest.mark.parametrize(
    ("rr5", "expected"),
    [
        (metric_profile(mfe="0.65", mae="0.35", target_rate="14", ratio="0.31"), "CLEAR_POSITIVE_VALUE"),
        (metric_profile(count=99, mfe="0.65", mae="0.50", target_rate="10", ratio="0.25"), "WEAK_POSITIVE_VALUE"),
        (metric_profile(mfe="0.50", mae="0.50", target_rate="10", ratio="0.25"), "NO_CLEAR_VALUE"),
        (metric_profile(mfe="0.35", mae="0.65", target_rate="6", ratio="0.19"), "NEGATIVE_VALUE"),
        (metric_profile(mfe="0.65", mae="0.65", target_rate="6", ratio="0.19"), "MIXED"),
        (metric_profile(count=29), "INCONCLUSIVE"),
    ],
)
def test_fifth_point_discrimination_classification(rr5: dict[str, object], expected: str) -> None:
    rr4 = metric_profile(count=min(300, int(rr5["count"])))
    assert fifth_point_discrimination(rr4, rr5)[0] == expected


def test_real_rr4_vs_rr5_discrimination_and_target_distance_findings(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    profiles = {row["control_rr_points"]: row for row in (cohort_summary([item for item in analysis if item["control_rr_points"] == points], control_rr_points=points) for points in (4, 5))}
    result, evidence = fifth_point_discrimination(profiles[4], profiles[5])
    assert profiles[4]["count"] == 1541
    assert profiles[5]["count"] == 484
    assert profiles[5]["median_target_distance_pct"] > profiles[4]["median_target_distance_pct"]
    assert profiles[5]["target_first_rate_pct"] < profiles[4]["target_first_rate_pct"]
    assert profiles[5]["median_mfe_to_target_r_ratio"] < profiles[4]["median_mfe_to_target_r_ratio"]
    assert result == "MIXED"
    assert evidence["positive_dimension_count"] == 0
    assert evidence["negative_dimension_count"] == 2


@pytest.mark.parametrize(
    ("directions", "expected"),
    [
        (("support", "support", "support"), "CONSISTENT"),
        (("support", "support", "mixed"), "MOSTLY_CONSISTENT"),
        (("support", "oppose", "mixed"), "UNSTABLE"),
        (("oppose", "oppose", "mixed"), "INVERSE"),
    ],
)
def test_temporal_consistency_classifications(directions: tuple[str, str, str], expected: str) -> None:
    assert temporal_consistency(temporal_rows(directions))[0] == expected


def test_temporal_consistency_is_inconclusive_for_small_yearly_cell() -> None:
    assert temporal_consistency(temporal_rows(("support", "support", "support"), count=29))[0] == "INCONCLUSIVE"


def test_real_yearly_component_analysis_supports_cap4_in_all_three_years(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    yearly = yearly_component_rows(analysis)
    result, directions = temporal_consistency(yearly)
    assert len(yearly) == 6
    assert {(row["year"], row["control_rr_points"]) for row in yearly} == {(year, points) for year in (2022, 2023, 2024) for points in (4, 5)}
    assert result == "CONSISTENT"
    assert all(row["direction"] == "SUPPORTS_CAP4_HYPOTHESIS" for row in directions)


def test_score_calibration_reports_both_mappings_at_all_required_levels() -> None:
    rows = [cohort_row(), cohort_row(opportunity_id="2024-01-02|OTHER", frozen_control_score=84, treatment_raw_score=83)]
    calibration = score_calibration_rows(rows)
    assert len(calibration) == 14
    assert {row["mapping"] for row in calibration} == {CONTROL_MAPPING_NAME, TREATMENT_MAPPING_NAME}
    assert {row["score"] for row in calibration} == set(range(79, 86))


def test_control_reproduction_and_treatment_portfolio_are_independent_and_valid(portfolio_bundle: dict[str, object]) -> None:
    control = portfolio_bundle["control_summary"]
    treatment = portfolio_bundle["treatment_summary"]
    assert control["portfolio"]["starting_equity"] == PortfolioBacktestConfig().initial_capital_rupees
    assert treatment["portfolio"]["starting_equity"] == PortfolioBacktestConfig().initial_capital_rupees
    assert control["portfolio"]["ending_equity"] == EXPECTED_CONTROL_ENDING_EQUITY
    assert treatment["portfolio"]["ending_equity"] == Decimal("101263.422565713715")
    assert control["trades"]["completed_trades"] == 481
    assert treatment["trades"]["completed_trades"] == 470
    assert control["skip_count"] == 1587
    assert treatment["skip_count"] == 1516
    assert control["all_invariants_valid"] is True
    assert treatment["all_invariants_valid"] is True
    assert sum(bool(row["materially_worse"]) for row in portfolio_bundle["yearly"]) == 1


def test_trade_set_comparison_distinguishes_source_eligibility_from_replacements(trade_comparison: dict[str, object]) -> None:
    assert trade_comparison["control_trade_count"] == 481
    assert trade_comparison["treatment_trade_count"] == 470
    assert trade_comparison["intersection_count"] == 442
    assert trade_comparison["control_only_count"] == 39
    assert trade_comparison["treatment_only_replacement_count"] == 28
    assert trade_comparison["jaccard_similarity"] == Decimal("0.8683693516699410609037328094")
    assert trade_comparison["direct_removed_control_trade_count"] == 18
    assert trade_comparison["indirect_control_only_trade_count"] == 21
    assert trade_comparison["all_treatment_only_are_source_eligible_replacements"] is True
    assert trade_comparison["unexplained_changed_trade_count"] == 0


def test_replacement_trade_identification_is_endogenous_and_source_eligible(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
    portfolio_bundle: dict[str, object],
    trade_comparison: dict[str, object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    replacements = replacement_trade_rows(trade_comparison, portfolio_bundle["treatment_simulation"]["trades"], analysis)
    assert len(replacements) == 28
    assert all(row["source_treatment_eligible"] for row in replacements)
    assert all(row["reason_admitted"] == "DETERMINISTIC_SLOT_OR_RANKING_SUBSTITUTION_AFTER_CAP4_ELIGIBILITY_CHANGE" for row in replacements)


def test_frozen_cost_overlay_reconciles_and_is_not_cost_aware_admission(
    cost_overlays: tuple[dict[str, object], dict[str, object]],
) -> None:
    control, treatment = cost_overlays
    assert control["summary"]["trade_count"] == 481
    assert treatment["summary"]["trade_count"] == 470
    assert control["summary"]["total_transaction_cost"] == Decimal("37254.00")
    assert treatment["summary"]["total_transaction_cost"] == Decimal("35515.52")
    assert control["summary"]["ending_equity"] == Decimal("61072.608925713674")
    assert treatment["summary"]["ending_equity"] == Decimal("65747.902565713715")
    assert control["summary"]["trade_cost_reconciliation_violations"] == 0
    assert treatment["summary"]["trade_cost_reconciliation_violations"] == 0
    assert control["cash_feasibility"]["violation_count"] == 126
    assert treatment["cash_feasibility"]["violation_count"] == 120
    assert control["cost_aware_admission_executable"] is False
    assert treatment["cost_aware_admission_executable"] is False


def test_each_falsification_criterion_can_trigger_independently() -> None:
    base = {
        "discrimination": "MIXED",
        "temporal_directions": [{"direction": "SUPPORTS_CAP4_HYPOTHESIS"}] * 3,
        "removed_count": 1,
        "retained": {"improved_dimension_count": 3},
        "yearly_portfolios": [{"materially_worse": False}] * 3,
        "trade_comparison": {"unexplained_changed_trade_count": 0, "jaccard_similarity": Decimal("0.9")},
        "source_treatment_only_count": 0,
        "control_cost": {"summary": {"ending_equity": Decimal("90")}},
        "treatment_cost": {"summary": {"ending_equity": Decimal("100")}},
        "control_gross_ending": Decimal("90"),
        "treatment_gross_ending": Decimal("100"),
    }
    assert not any(row["triggered"] for row in falsification_results(**base).values())
    cases = {
        "A": {"discrimination": "CLEAR_POSITIVE_VALUE", "temporal_directions": [{"direction": "OPPOSES_CAP4_HYPOTHESIS"}] * 2},
        "B": {"retained": {"improved_dimension_count": 1}},
        "C": {"yearly_portfolios": [{"materially_worse": True}] * 2},
        "D": {"source_treatment_only_count": 1},
        "E": {"treatment_cost": {"summary": {"ending_equity": Decimal("80")}}},
    }
    for criterion, updates in cases.items():
        args = {**base, **updates}
        assert falsification_results(**args)[criterion]["triggered"] is True


def test_supported_classification_does_not_authorize_validation() -> None:
    rr4 = metric_profile(target_distance="10")
    rr5 = metric_profile(mfe="0.40", mae="0.60", target_rate="7", ratio="0.20", target_distance="30")
    falsification = {key: {"triggered": False} for key in "ABCDE"}
    result = classify_experiment(
        discrimination="NEGATIVE_VALUE",
        rr4=rr4,
        rr5=rr5,
        temporal="CONSISTENT",
        falsification=falsification,
        retained={"improved_dimension_count": 3},
        control_portfolio={"portfolio": {"ending_equity": Decimal("100000")}},
        treatment_portfolio={"portfolio": {"ending_equity": Decimal("101000")}},
        control_cost={"summary": {"ending_equity": Decimal("60000")}},
        treatment_cost={"summary": {"ending_equity": Decimal("61000")}},
        integrity_ok=True,
    )
    assert result["RR_CAP4_EXPERIMENT_RESULT"] == "SUPPORTED_FOR_NEXT_STAGE"
    assert result["RR_FIFTH_POINT_HYPOTHESIS"] == "SURVIVES_DEVELOPMENT_TEST"
    assert result["ELIGIBLE_FOR_VALIDATION_CONSIDERATION"] == "YES"
    assert "validation_authorized" not in result


def test_real_pilot_covers_all_fourteen_requested_cases(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
    portfolio_bundle: dict[str, object],
) -> None:
    _manifest, analysis, _outcomes, _context = population_bundle
    pilot = build_pilot(analysis, portfolio_bundle["control_simulation"]["trades"], portfolio_bundle["treatment_simulation"]["trades"])
    assert pilot["case_count"] == 14
    assert pilot["available_count"] == 14
    assert pilot["failed_count"] == 0
    assert pilot["passed"] is True
    assert all(row["validation_result"] == "PASS" for row in pilot["cases"])


def test_baseline_dependencies_and_checkpoint_are_immutable() -> None:
    before = baseline_snapshot(REPO_ROOT)
    dependencies = preregistration_dependencies(before)
    after = baseline_snapshot(REPO_ROOT)
    assert before == after
    assert dependencies["checkpoint_commit"] == "c6315abdd92db3b978ae28c5f5b08013ead4bbb3"
    assert dependencies["command_03"]["population_hash"] == "49c9243b76a6de6cee38d9f293cb5b510e45ec90f25fb6bfce76ede7fe09c1c8"


def test_real_governance_hashes_match_the_pre_result_freeze(
    population_bundle: tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], object],
) -> None:
    manifest, _analysis, _outcomes, _context = population_bundle
    snapshot = baseline_snapshot(REPO_ROOT)
    prereg = build_preregistration(freeze_population(manifest), preregistration_dependencies(snapshot))
    freeze = build_development_freeze(freeze_population(manifest), prereg)
    assert prereg["experiments"][0]["parameter_hash"] == EXPECTED_PARAMETER_HASH
    assert prereg["rr_cap4_preregistration_hash"] == EXPECTED_PREREGISTRATION_HASH
    assert freeze["development_freeze_hash"] == EXPECTED_FREEZE_HASH


def test_report_contract_contains_exactly_thirteen_required_files() -> None:
    assert REPORT_FILENAMES == (
        "rr_cap4_v1_summary.json",
        "rr_cap4_v1_population.csv",
        "rr_cap4_v1_score_transitions.csv",
        "rr_cap4_v1_rr4_vs_rr5.csv",
        "rr_cap4_v1_removed_cohort.csv",
        "rr_cap4_v1_retained_cohort.csv",
        "rr_cap4_v1_yearly_component.csv",
        "rr_cap4_v1_control_portfolio.csv",
        "rr_cap4_v1_treatment_portfolio.csv",
        "rr_cap4_v1_trade_set_comparison.csv",
        "rr_cap4_v1_replacement_trades.csv",
        "rr_cap4_v1_costs.csv",
        "rr_cap4_v1_pilot.csv",
    )


def test_machine_report_generation_is_offline_and_decimal_safe(tmp_path: Path) -> None:
    payload = [{"value": Decimal("1.25"), "validation_state": SEALED}]
    json_path = tmp_path / "summary.json"
    csv_path = tmp_path / "rows.csv"
    write_json(json_path, payload)
    write_csv(csv_path, payload)
    assert '"1.25"' in json_path.read_text(encoding="utf-8")
    assert "1.25" in csv_path.read_text(encoding="utf-8")

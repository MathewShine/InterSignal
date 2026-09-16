from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.strategy import family_a_one_shot_validation as validation
from app.research.temporal_validation.config import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "data/research/validation/family_a/v1/evaluation"
SUMMARY = json.loads(
    (ROOT / "data/reports/family_a_validation_v1_summary.json").read_text(
        encoding="utf-8"
    )
)
RESULT = json.loads(
    (EVALUATION / "results/validation_result_v1.json").read_text(encoding="utf-8")
)
MANIFEST = json.loads(
    (
        EVALUATION
        / "manifests/family_a_one_shot_validation_manifest_v1.json"
    ).read_text(encoding="utf-8")
)

FROZEN_COMPUTATION_HASHES = {
    "build_validation_schedules": "1efe3d28dd0b044599d095c1519c57912af3f5393c9acd7bb3f7cb944bde3dc6",
    "simulate_validation_executable": "95ec474da47b8cca6d0193945e531ab6ee52ea5e8f557d53a9b22d70eb44d52a",
    "calculate_validation_metrics": "ce58079afa0eaf1b3ea40887f259e3afd8cbe1ad12244864bf86a2b997b4422c",
    "evaluate_criteria": "85405fb352d3def4d727345616804554087397ccbcdca2c6da0e4b20181a44db",
}


def _serializer_fixture() -> dict[str, object]:
    return {
        "periods": [
            {
                "period_start": "2025-01-01",
                "period_end": "2025-04-01",
                "gross_period_return_pct": Decimal("10"),
                "net_period_return_pct": Decimal("9"),
                "gross_period_pnl": Decimal("100"),
                "net_period_pnl": Decimal("90"),
                "positive_net_period": True,
                "final_partial_period": False,
            }
        ],
        "rebalances": [
            {
                "formation_date": "2024-12-31",
                "execution_date": "2025-01-01",
                "eligible_count": 200,
                "selected_count": 20,
                "actual_holdings": 1,
                "cash": Decimal("10"),
                "post_rebalance_gross_equity": Decimal("1000"),
                "post_rebalance_net_equity": Decimal("1000"),
                "rebalance_cost": Decimal("5"),
                "one_way_turnover": Decimal("0.99"),
            }
        ],
        "holdings": [
            {
                "execution_date": "2025-01-01",
                "symbol": "FIXTURE",
                "quantity": 10,
                "actual_weight_pct": Decimal("99"),
            }
        ],
    }


def test_serializer_fixture_uses_actual_period_schema() -> None:
    period = _serializer_fixture()["periods"][0]
    assert "end_gross_equity" not in period
    assert "end_net_equity" not in period
    assert "gross_period_pnl" in period
    assert "net_period_pnl" in period


def test_serializer_fix_reconstructs_end_equity_without_recalculation() -> None:
    row = validation.build_interval_ledger(_serializer_fixture())[0]
    assert row["exit_or_rebalance_gross_equity_inr"] == Decimal("1100")
    assert row["exit_or_rebalance_net_equity_inr"] == Decimal("1090")
    assert row["gross_interval_return_pct"] == Decimal("10")
    assert row["net_interval_return_pct"] == Decimal("9")


def test_serializer_schema_assertion_is_deterministic() -> None:
    fixture = _serializer_fixture()
    del fixture["periods"][0]["gross_period_pnl"]
    with pytest.raises(ValueError, match="gross_period_pnl"):
        validation.build_interval_ledger(fixture)


def test_performance_computation_functions_are_unchanged() -> None:
    observed = {
        name: hashlib.sha256(inspect.getsource(getattr(validation, name)).encode()).hexdigest()
        for name in FROZEN_COMPUTATION_HASHES
    }
    assert observed == FROZEN_COMPUTATION_HASHES


def test_invalidation_record_is_immutable_and_exact() -> None:
    path = EVALUATION / "authorization/attempt_1_invalidation_record_v1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    observed = canonical_hash(
        {
            key: value
            for key, value in record.items()
            if key != "family_a_validation_attempt_invalidation_hash"
        }
    )
    assert observed == validation.ATTEMPT_INVALIDATION_HASH
    assert record["status"] == "INVALIDATED_IMPLEMENTATION_DEFECT"
    assert record["performance_persistence"] is False
    assert record["result_sealing"] is False


def test_frozen_input_snapshot_is_reused_exactly() -> None:
    snapshot = validation._existing_input_snapshot(ROOT)
    assert (
        snapshot["family_a_validation_input_snapshot_hash"]
        == validation.FAILED_ATTEMPT_INPUT_SNAPSHOT_HASH
    )
    assert snapshot["post_holdout_files_loaded"] == 0
    assert snapshot["last_loaded_date"] == "2026-08-13"


def test_repository_contains_original_checkpoint_and_candidate_hashes_remain_exact() -> None:
    ancestry = subprocess.run(
        (
            "git",
            "merge-base",
            "--is-ancestor",
            validation.REQUIRED_CHECKPOINT,
            "HEAD",
        ),
        cwd=ROOT,
        check=False,
    )
    assert ancestry.returncode == 0
    candidate = validation.build_candidate_configuration()
    assert candidate["frozen_hashes"]["candidate_identity_hash"] == (
        "0e8ef3cc26d4146258f25fdd4c269867a383d2f098d9df0e367d4b0ff86beacc"
    )


def test_original_and_replacement_authorizations_are_exact() -> None:
    original = json.loads(
        (EVALUATION / "authorization/authorization_record_v1.json").read_text(
            encoding="utf-8"
        )
    )
    replacement = json.loads(
        (EVALUATION / "authorization/replacement_authorization_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert original["family_a_validation_authorization_hash"] == (
        validation.ORIGINAL_AUTHORIZATION_HASH
    )
    assert replacement["attempt_number"] == 2
    assert replacement["replacement_valid_run_number"] == 1
    assert replacement["invalidation_hash"] == validation.ATTEMPT_INVALIDATION_HASH
    assert canonical_hash(
        {
            key: value
            for key, value in replacement.items()
            if key != "family_a_validation_replacement_authorization_hash"
        }
    ) == replacement["family_a_validation_replacement_authorization_hash"]


def test_exact_window_schedule_and_terminal_exclusion() -> None:
    assert RESULT["validation_window"] == {
        "start": "2025-01-01",
        "end": "2026-08-13",
    }
    assert RESULT["primary_interval_end"] == "2026-07-01"
    assert RESULT["terminal_interval_excluded_from_primary"] is True
    observed = [
        (row["formation_date"], row["execution_date"])
        for row in SUMMARY["rebalance_schedule"]["schedule"]
    ]
    assert observed == [
        (formation.isoformat(), execution.isoformat())
        for formation, execution in validation.SEALED_SCHEDULE
    ]
    assert SUMMARY["data_quality"]["post_holdout_files_loaded"] == 0
    assert SUMMARY["terminal_mark_to_market_diagnostic"][
        "included_in_primary_classification"
    ] is False


def test_candidate_architecture_has_no_overlay_or_mutation() -> None:
    candidate = SUMMARY["candidate"]
    assert candidate["momentum_lookback"] == "6M"
    assert candidate["selection"] == "TOP_DECILE"
    assert candidate["weighting"] == "EQUAL_WEIGHT"
    assert candidate["share_semantics"] == "WHOLE_SHARES"
    assert candidate["starting_capital_inr"] == "500000"
    assert candidate["prohibited_overlays_present"] == []
    assert candidate["candidate_parameter_changed"] is False
    assert RESULT["criteria_changed"] is False


def test_selection_counts_are_exact_top_decile() -> None:
    for row in SUMMARY["rebalance_schedule"]["schedule"]:
        assert row["selected_count"] == row["intended_count"]
        assert row["selected_count"] == (
            0 if row["eligible_count"] == 0 else __import__("math").ceil(row["eligible_count"] * 0.1)
        )


def test_holdings_are_whole_share_and_unlevered() -> None:
    import csv

    with (EVALUATION / "holdings/validation_holdings_v1.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        holdings = list(csv.DictReader(file))
    with (EVALUATION / "ledgers/portfolio_daily_ledger_v1.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        daily = list(csv.DictReader(file))
    assert holdings
    assert all(Decimal(row["quantity"]) == int(Decimal(row["quantity"])) for row in holdings)
    assert all(Decimal(row["cash"]) >= 0 for row in daily)


def test_frozen_cost_semantics_and_accounting() -> None:
    import csv

    with (EVALUATION / "ledgers/cost_ledger_v1.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        costs = list(csv.DictReader(file))
    assert costs
    assert {row["cost_config_hash"] for row in costs} == {
        "9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48"
    }
    assert {row["cost_scenario"] for row in costs} == {"COST-SCENARIO-002"}
    assert SUMMARY["metrics"]["cash_reconciliation_violations"] == 0
    assert SUMMARY["metrics"]["equity_reconciliation_violations"] == 0


def test_interval_accounting_and_completed_count() -> None:
    intervals = RESULT["completed_intervals"]
    assert len(intervals) == 6
    for row in intervals:
        start = Decimal(row["entry_net_equity_inr"])
        end = Decimal(row["exit_or_rebalance_net_equity_inr"])
        observed_return = (end / start - Decimal("1")) * Decimal("100")
        assert observed_return == Decimal(row["net_interval_return_pct"])


def test_cagr_is_reproducible() -> None:
    ending = float(SUMMARY["metrics"]["net_ending_equity_inr"])
    elapsed_days = 546
    expected = ((ending / 500000) ** (365.25 / elapsed_days) - 1) * 100
    assert float(SUMMARY["metrics"]["net_cagr_pct"]) == pytest.approx(expected)


def test_drawdown_is_reproducible_from_primary_ledger() -> None:
    import csv

    with (EVALUATION / "ledgers/portfolio_daily_ledger_v1.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        primary = [
            row for row in csv.DictReader(file) if row["date"] < "2026-07-01"
        ]
    values = [Decimal(row["net_equity"]) for row in primary]
    values.append(Decimal(SUMMARY["metrics"]["net_ending_equity_inr"]))
    peak = Decimal("500000")
    maximum = Decimal("0")
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, Decimal("1") - value / peak)
    assert maximum * 100 == Decimal(
        SUMMARY["metrics"]["max_drawdown_magnitude_pct"]
    )


def test_core_criteria_A_to_G_are_sealed_results() -> None:
    observed = {
        key: row["passed"] for key, row in SUMMARY["criteria"]["core_criteria"].items()
    }
    assert observed == {
        "A": True,
        "B": False,
        "C": True,
        "D": False,
        "E": True,
        "F": False,
        "G": True,
    }


def test_quality_H_to_K_are_sealed_results() -> None:
    observed = {
        key: row["passed"]
        for key, row in SUMMARY["criteria"]["quality_dimensions"].items()
    }
    assert observed == {"H": True, "I": False, "J": True, "K": False}


def test_fatal_and_final_mappings_are_exact() -> None:
    criteria = SUMMARY["criteria"]
    assert criteria["fatal_condition_triggered"] is True
    assert criteria["fatal_detail"] == ["F"]
    assert criteria["VALIDATION_RESULT"] == "INCONCLUSIVE"
    assert criteria["FAMILY_A_GENERALIZATION_RESULT"] == "INCONCLUSIVE"
    assert criteria["STRATEGY_V2_ADVANCEMENT_STATUS"] == "NO_DECISION"


def test_attempt_counts_and_lifecycle_are_truthful() -> None:
    state = json.loads(
        (EVALUATION / "results/evaluated_lifecycle_state_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["lifecycle_after"] == "EVALUATED"
    assert state["attempt_count"] == 2
    assert state["invalidated_attempt_count"] == 1
    assert state["completed_valid_formal_runs_after"] == 1
    assert state["validation_run_count_after"] == 1
    assert state["remaining_formal_runs"] == 0
    assert state["SECOND_FORMAL_VALIDATION_RUN_ALLOWED"] == "NO"


def test_no_third_attempt_is_structurally_allowed() -> None:
    with pytest.raises(validation.FamilyASecondFormalRunProhibited):
        validation._ensure_fresh_replacement(ROOT)


def test_result_criteria_and_manifest_hashes_recompute() -> None:
    assert canonical_hash(
        {
            key: value
            for key, value in RESULT.items()
            if key != "family_a_validation_result_hash"
        }
    ) == RESULT["family_a_validation_result_hash"]
    criteria = RESULT["criteria"]
    assert canonical_hash(
        {
            key: value
            for key, value in criteria.items()
            if key != "family_a_validation_criteria_result_hash"
        }
    ) == criteria["family_a_validation_criteria_result_hash"]
    assert canonical_hash(
        {
            key: value
            for key, value in MANIFEST.items()
            if key != "family_a_one_shot_validation_manifest_hash"
        }
    ) == MANIFEST["family_a_one_shot_validation_manifest_hash"]


def test_ledger_hashes_recompute_from_persisted_artifacts() -> None:
    import csv

    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    holdings = rows(EVALUATION / "holdings/validation_holdings_v1.csv")
    for row in holdings:
        row["quantity"] = int(row["quantity"])
        for key in ("price", "market_value", "actual_weight_pct", "cash_weight_pct"):
            row[key] = Decimal(row[key])

    costs = rows(EVALUATION / "ledgers/cost_ledger_v1.csv")
    cost_text = {
        "experiment_id",
        "mode",
        "execution_date",
        "symbol",
        "side",
        "cost_methodology",
        "cost_model",
        "cost_profile",
        "cost_config_hash",
        "cost_scenario",
    }
    for row in costs:
        for key in set(row) - cost_text:
            row[key] = Decimal(row[key])

    daily = rows(EVALUATION / "ledgers/portfolio_daily_ledger_v1.csv")
    daily_text = {"experiment_id", "mode", "date", "scope", "valuation_point"}
    daily_int = {"holding_count", "missing_close_valuation_count"}
    for row in daily:
        for key in daily_int:
            row[key] = int(row[key])
        for key in set(row) - daily_text - daily_int:
            row[key] = Decimal(row[key])
    endpoint = json.loads(
        (EVALUATION / "ledgers/primary_endpoint_v1.json").read_text(encoding="utf-8")
    )

    hashes = RESULT["result_hashes"]
    assert canonical_hash(holdings) == hashes["family_a_validation_holdings_hash"]
    assert canonical_hash(costs) == hashes["family_a_validation_cost_ledger_hash"]
    assert canonical_hash({"daily": daily, "primary_endpoint": endpoint}) == hashes[
        "family_a_validation_portfolio_ledger_hash"
    ]


def test_manifest_contains_full_governance_history() -> None:
    assert MANIFEST["attempt_history"][0]["status"] == (
        "INVALIDATED_IMPLEMENTATION_DEFECT"
    )
    assert MANIFEST["attempt_history"][1]["status"] == (
        "VALID_FORMAL_REPLACEMENT_RUN"
    )
    assert MANIFEST["attempt_invalidation_hash"] == validation.ATTEMPT_INVALIDATION_HASH
    assert MANIFEST["replacement_authorization_hash"] == SUMMARY[
        "replacement_authorization"
    ]["family_a_validation_replacement_authorization_hash"]


def test_reports_and_atomic_seal_are_complete() -> None:
    assert all((ROOT / "data/reports" / name).is_file() for name in validation.REPORT_NAMES)
    assert not (EVALUATION / ".replacement_staging_v1").exists()
    assert (EVALUATION / "manifests/family_a_one_shot_validation_manifest_v1.json").is_file()
    assert (EVALUATION / "results/evaluated_lifecycle_state_v1.json").is_file()


def test_no_strategy_v2_or_family_h_was_created() -> None:
    assert RESULT["strategy_v2_created"] is False
    assert RESULT["family_h_created"] is False
    assert MANIFEST["strategy_v2_created"] is False
    assert MANIFEST["family_h_created"] is False


def test_security_counters_are_zero() -> None:
    assert all(value == 0 for value in MANIFEST["security"].values())


def test_review_verification_is_separate_and_ready() -> None:
    path = EVALUATION / "diagnostics/verification_record_v1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["verification"]["ready_for_review"] is True
    assert record["verification"]["immutable_manifest_unchanged"] is True
    assert canonical_hash(
        {
            key: value
            for key, value in record.items()
            if key != "family_a_validation_verification_hash"
        }
    ) == record["family_a_validation_verification_hash"]

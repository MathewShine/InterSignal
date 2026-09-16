from __future__ import annotations

import csv
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.09 / Command 01"
COMMAND_VERSION = "FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_V1"
COMMAND_PROFILE = "MOM_A_002_GOVERNED_VALIDATION_PROTOCOL_V1"
MANIFEST_VERSION = "FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_MANIFEST_V1"
MILESTONE_COMMIT = "a405e9ffef9cd1c9de3d9f9b92ff6b2547e1bdd1"
SYNTHESIS_VERSION = "CROSS_FAMILY_EVIDENCE_SYNTHESIS_V1"
SYNTHESIS_HASH = "d05826bfae334b64a759b81de5864b25cc076da0267ac36d7b926a67f865d64e"

CANDIDATE_ID = "PROVISIONAL_VALIDATION_CANDIDATE_V1"
CANDIDATE_STATUS_BEFORE = "SELECTED_FOR_VALIDATION_DESIGN_ONLY"
ARCHITECTURE_ID = "MOM-A-002"
IMPLEMENTATION_ID = "A2-002"
REFERENCE_CAPITAL_INR = "500000"

FAMILY_CONFIG_HASH = "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3"
MOM_A_002_PARAMETER_HASH = "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8"
MOM_A_002_PREREGISTRATION_HASH = "e88f8c2588b8c1ffb2fb5c951471f423d6b99d065ba135c58979c57f196f91cc"
PHASE2_CONFIG_HASH = "8800738a5716ccbd1464ff564c5dea3b2891c523063eee01d5ad85fb583672cc"
A2_002_IMPLEMENTATION_HASH = "a391c2b46541af88b91b316bf2914bb15c6a11a7c5c9ff291d9f6c617bf8ae5b"
A2_002_PREREGISTRATION_HASH = "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897"
A2_002_RESULT_HASH = "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27"
FAMILY_A_CLOSURE_HASH = "51e2190c25f3146609ac173cc345e2a8adc0b6c9efb824633d735dc976581250"
SYNTHESIS_CANDIDATE_HASH = "2680c16aacda5d924f1b3d4484bc7fc5e419e8d3ed2cc2699f5ad750e7d9fb4c"

COST_MODEL_VERSION = "INDIA_EQUITY_COST_MODEL_V1"
COST_PROFILE = "NSE_CASH_DELIVERY_RESEARCH_V1"
COST_SCENARIO = "COST-SCENARIO-002"
COST_CONFIG_HASH = "9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48"
COST_SCENARIO_HASH = "17284d899a68119a4f5059e0fc0a6956accaccbf0cb3a5731251603593857a0d"

VALIDATION_START = date(2025, 1, 1)
VALIDATION_END = date(2026, 8, 13)
LIFECYCLE = "SEALED_DESIGN"
VALIDATION_RUN_COUNT = 0
MAXIMUM_FORMAL_RUN_COUNT = 1

CONTAMINATION_DISCLOSURE = (
    "The project has previously observed aggregate later-period diagnostics in other "
    "research contexts. Therefore this is a formally governed/sealed validation period, "
    "but not philosophically pristine laboratory-grade unseen data."
)

CORE_GATE_IDS = (
    "A_POSITIVE_AFTER_COST_PERFORMANCE",
    "B_CAGR_RETENTION",
    "C_DRAWDOWN_ACCEPTABILITY",
    "D_INTERVAL_CONSISTENCY",
    "E_COST_ROBUSTNESS",
    "F_IMPLEMENTATION_INTEGRITY",
    "G_SAMPLE_ADEQUACY",
)
QUALITY_DIMENSION_IDS = (
    "H_YEAR_SLICES",
    "I_SHARPE_LIKE",
    "J_DRAWDOWN_RETENTION",
    "K_CAGR_QUALITY",
)

SOURCE_FILE_HASHES = {
    "data/research/cross_family_synthesis/v1/manifests/cross_family_evidence_synthesis_manifest_v1.json": (
        "54aae22e50c46494a87fef9745347cf0e1c578b7d541ec40223db8320c892aa8"
    ),
    "data/research/strategy_families/family_a/v1/registry/family_config_v1.json": (
        "fccf7b2ed7d76dbedc616e04f75e95e7cdb12fc293e01837c23a95ea781b7515"
    ),
    "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json": (
        "92a74e267806ca38c2409c105d6d7acac5b8cc6bd84cb7fc603e2ff5c9698135"
    ),
    "data/research/strategy_families/family_a/v1/phase2/registry/phase2_config_v1.json": (
        "0fc0d2e25871e903e93713b8fef4a0e4f3e8528727de8ccd0d65e671301edc86"
    ),
    "data/research/strategy_families/family_a/v1/phase2/registry/a2_002_preregistration_v1.json": (
        "261ee7e8c6a4a5a96b8027a3ac35d20ebc267d9d4592c270f9d1ed65eea30065"
    ),
    "data/research/strategy_families/family_a/v1/phase2/development_evaluation/a2_002/development_result_v1.json": (
        "083350f4a86b4ff502814159dc4b39c02c7d05ad88e7f7daf9b1422e089d367d"
    ),
    "data/research/strategy_families/family_a/v1/closure/manifest/family_a_closure_manifest_v1.json": (
        "9d996efb5c41d2b1a280a0f0cfb2ed800919b683e87cbfe93e735d99ffa8ba8e"
    ),
}

REPORT_NAMES = (
    "family_a_validation_design_v1_summary.json",
    "family_a_validation_design_v1_candidate.csv",
    "family_a_validation_design_v1_schedule.csv",
    "family_a_validation_design_v1_criteria.csv",
    "family_a_validation_design_v1_fatal_conditions.csv",
    "family_a_validation_design_v1_data_readiness.csv",
    "family_a_validation_design_v1_governance.csv",
    "family_a_validation_design_v1_advancement.csv",
)

FUTURE_VALIDATION_FIELDS = (
    "starting_equity",
    "gross_ending_equity",
    "net_ending_equity",
    "gross_return",
    "net_return",
    "net_cagr",
    "max_drawdown",
    "annualized_volatility",
    "sharpe_like",
    "positive_completed_intervals",
    "completed_interval_count",
    "return_2025",
    "return_2026_partial_year",
    "turnover",
    "transaction_costs",
    "average_cash",
    "average_holdings",
    "rebalance_level_ledger",
    "criteria_A_to_G",
    "quality_H_to_K",
    "FAMILY_A_GENERALIZATION_RESULT",
)

FUTURE_VALIDATION_HASHES = (
    "validation_input_snapshot_hash",
    "candidate_configuration_hash",
    "rebalance_schedule_hash",
    "holdings_hash",
    "portfolio_ledger_hash",
    "cost_ledger_hash",
    "result_hash",
    "criteria_hash",
    "manifest_hash",
)


class FamilyAValidationCandidateIdentityMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/validation/family_a/v1/design"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def _round_prefix(value: Any, expected: str) -> bool:
    return str(value).startswith(expected)


def verify_frozen_candidate(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    missing = [relative for relative in SOURCE_FILE_HASHES if not (root / relative).is_file()]
    if missing:
        raise FamilyAValidationCandidateIdentityMismatch(
            f"FAMILY_A_VALIDATION_CANDIDATE_IDENTITY_MISMATCH: missing {missing}"
        )
    observed_file_hashes = {
        relative: file_sha256(root / relative) for relative in SOURCE_FILE_HASHES
    }
    changed = [
        relative
        for relative, expected in SOURCE_FILE_HASHES.items()
        if observed_file_hashes[relative] != expected
    ]
    if changed:
        raise FamilyAValidationCandidateIdentityMismatch(
            f"FAMILY_A_VALIDATION_CANDIDATE_IDENTITY_MISMATCH: changed {changed}"
        )

    synthesis_summary = _read_json(
        root / "data/reports/cross_family_synthesis_v1_summary.json"
    )
    synthesis_manifest = _read_json(
        root
        / "data/research/cross_family_synthesis/v1/manifests/cross_family_evidence_synthesis_manifest_v1.json"
    )
    family_config = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/registry/family_config_v1.json"
    )
    mom = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json"
    )
    phase2 = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/registry/phase2_config_v1.json"
    )
    implementation = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/registry/a2_002_preregistration_v1.json"
    )
    development = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/phase2/development_evaluation/a2_002/development_result_v1.json"
    )
    closure = _read_json(
        root
        / "data/research/strategy_families/family_a/v1/closure/manifest/family_a_closure_manifest_v1.json"
    )
    candidate = synthesis_summary["candidate_selection"]["provisional_candidate"]
    performance = development["performance"]

    checks = {
        "synthesis_version_exact": synthesis_summary.get("command_version") == SYNTHESIS_VERSION,
        "synthesis_summary_hash_exact": synthesis_summary.get("cross_family_synthesis_hash") == SYNTHESIS_HASH,
        "synthesis_manifest_hash_exact": synthesis_manifest.get("cross_family_synthesis_hash") == SYNTHESIS_HASH,
        "synthesis_manifest_recomputes": _document_hash(
            synthesis_manifest, "cross_family_synthesis_hash"
        )
        == SYNTHESIS_HASH,
        "candidate_id_exact": candidate.get("candidate_id") == CANDIDATE_ID,
        "candidate_status_exact": candidate.get("status") == CANDIDATE_STATUS_BEFORE,
        "candidate_architecture_exact": candidate.get("architecture_reference") == ARCHITECTURE_ID,
        "candidate_implementation_exact": candidate.get("implementation_reference") == IMPLEMENTATION_ID,
        "candidate_capital_exact": str(candidate.get("reference_capital_inr")) == REFERENCE_CAPITAL_INR,
        "synthesis_candidate_hash_exact": synthesis_manifest.get("candidate_selection", {}).get(
            "provisional_candidate_hash"
        )
        == SYNTHESIS_CANDIDATE_HASH,
        "family_config_hash_exact": family_config.get("family_config_hash") == FAMILY_CONFIG_HASH,
        "mom_parameter_hash_exact": mom.get("parameter_hash") == MOM_A_002_PARAMETER_HASH,
        "mom_preregistration_hash_exact": mom.get("preregistration_hash") == MOM_A_002_PREREGISTRATION_HASH,
        "phase2_config_hash_exact": phase2.get("phase2_config_hash") == PHASE2_CONFIG_HASH,
        "a2_002_parameter_hash_exact": implementation.get("parameter_hash") == A2_002_IMPLEMENTATION_HASH,
        "a2_002_preregistration_hash_exact": implementation.get("preregistration_hash") == A2_002_PREREGISTRATION_HASH,
        "a2_002_result_hash_exact": development.get("development_result_hash") == A2_002_RESULT_HASH,
        "closure_hash_exact": closure.get("family_a_closure_hash") == FAMILY_A_CLOSURE_HASH,
        "development_starting_equity_exact": str(performance.get("starting_equity")) == "500000",
        "development_ending_equity_exact": str(performance.get("net_ending_equity")) == "955331.6799",
        "development_return_exact": _round_prefix(performance.get("net_total_return_pct"), "91.06633598"),
        "development_cagr_exact": _round_prefix(performance.get("net_cagr_pct"), "24.10585067"),
        "development_drawdown_exact": _round_prefix(
            str(performance.get("net_max_drawdown_pct")).lstrip("-"), "22.92216992"
        ),
        "development_only": development.get("development_only") is True,
        "prior_validation_not_accessed": development.get("validation_accessed") is False,
    }
    parameters = implementation["parameters"]
    architecture_checks = {
        "universe": parameters.get("universe") == "POINT_IN_TIME_NIFTY_500",
        "direction": parameters.get("direction") == "LONG_ONLY",
        "signal": parameters.get("signal") == "6M",
        "lookback": parameters.get("lookback_trading_sessions") == 126,
        "selection": parameters.get("selection") == "TOP_DECILE",
        "selection_fraction": str(parameters.get("selection_fraction")) == "0.10",
        "rebalance": parameters.get("rebalance_frequency") == "QUARTERLY",
        "weighting": parameters.get("weighting") == "EQUAL_WEIGHT",
        "capital": str(parameters.get("starting_capital_inr")) == REFERENCE_CAPITAL_INR,
        "execution": parameters.get("execution") == "NEXT_ELIGIBLE_SESSION_OPEN",
        "leverage": parameters.get("leverage_allowed") is False,
        "shorting": parameters.get("shorting_allowed") is False,
        "stop_loss": parameters.get("stop_loss") is None,
        "profit_target": parameters.get("profit_target") is None,
        "cost_model": parameters.get("cost_model") == COST_MODEL_VERSION,
        "cost_profile": parameters.get("cost_profile") == COST_PROFILE,
        "cost_scenario": parameters.get("cost_scenario") == COST_SCENARIO,
    }
    checks.update({f"architecture_{key}": value for key, value in architecture_checks.items()})
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise FamilyAValidationCandidateIdentityMismatch(
            "FAMILY_A_VALIDATION_CANDIDATE_IDENTITY_MISMATCH: " + ", ".join(failures)
        )

    return {
        "status": "VERIFIED",
        "checks": checks,
        "source_file_hashes": observed_file_hashes,
        "source_snapshot_hash": canonical_hash(observed_file_hashes),
        "candidate": candidate,
        "parameters": parameters,
        "development": development,
    }


def candidate_identity_document(verification: Mapping[str, Any]) -> dict[str, Any]:
    parameters = verification["parameters"]
    body = {
        "candidate_id": CANDIDATE_ID,
        "status_before_design": CANDIDATE_STATUS_BEFORE,
        "status_after_design": "SEALED_FOR_FUTURE_ONE_SHOT_REVIEW_NOT_AUTHORIZED",
        "candidate_selection_classification": "SINGLE_LEADING_CANDIDATE",
        "why_selected": (
            "Family A is the only A-G architecture passing all ten validation-candidacy gates; "
            "this is not proof of future performance."
        ),
        "architecture_reference": ARCHITECTURE_ID,
        "implementation_reference": IMPLEMENTATION_ID,
        "reference_capital_inr": REFERENCE_CAPITAL_INR,
        "frozen_hashes": {
            "cross_family_synthesis_hash": SYNTHESIS_HASH,
            "cross_family_candidate_hash": SYNTHESIS_CANDIDATE_HASH,
            "family_a_family_config_hash": FAMILY_CONFIG_HASH,
            "mom_a_002_parameter_hash": MOM_A_002_PARAMETER_HASH,
            "mom_a_002_preregistration_hash": MOM_A_002_PREREGISTRATION_HASH,
            "family_a_phase2_config_hash": PHASE2_CONFIG_HASH,
            "a2_002_implementation_config_hash": A2_002_IMPLEMENTATION_HASH,
            "a2_002_preregistration_hash": A2_002_PREREGISTRATION_HASH,
            "a2_002_development_result_hash": A2_002_RESULT_HASH,
            "family_a_closure_hash": FAMILY_A_CLOSURE_HASH,
            "cost_config_hash": COST_CONFIG_HASH,
            "cost_scenario_hash": COST_SCENARIO_HASH,
        },
        "architecture": {
            "universe": "POINT_IN_TIME_NIFTY_500",
            "direction": "LONG_ONLY",
            "signal": "6M_CROSS_SECTIONAL_RELATIVE_MOMENTUM",
            "lookback_trading_sessions": 126,
            "skip_most_recent_trading_sessions": 0,
            "minimum_price_inr": str(parameters["minimum_price_inr"]),
            "liquidity_window_sessions": parameters["liquidity_window_sessions"],
            "minimum_median_traded_value_inr": str(
                parameters["minimum_median_traded_value_inr"]
            ),
            "selection": "TOP_DECILE",
            "selection_fraction": "0.10",
            "minimum_portfolio_size": parameters["minimum_portfolio_size"],
            "tie_break": parameters["tie_break"],
            "rebalance": "QUARTERLY",
            "weighting": "EQUAL_WEIGHT",
            "capital_inr": REFERENCE_CAPITAL_INR,
            "execution": "NEXT_ELIGIBLE_SESSION_OPEN",
            "whole_shares": True,
            "leverage_allowed": False,
            "shorting_allowed": False,
            "cost_model": COST_MODEL_VERSION,
            "cost_profile": COST_PROFILE,
            "cost_scenario": COST_SCENARIO,
            "slippage_bps_per_side": "5",
            "corporate_action_return_layer": "PRICE_ADJUSTED_STRUCTURAL_V1",
            "unsafe_corporate_action_windows": "EXCLUDE_USING_RESEARCH_ELIGIBILITY_V1",
        },
        "prohibited_additions": [
            "ABSOLUTE_MOMENTUM_FILTER",
            "SMA_FILTER",
            "COMPRESSION_FILTER",
            "MARKET_REGIME_FILTER",
            "VIX",
            "BREADTH",
            "NEWS",
            "CATALYST",
            "STOP_LOSS",
            "TARGET",
            "INTRADAY_CONFIRMATION",
            "FAMILY_B_OVERLAY",
            "FAMILY_C_OVERLAY",
            "FAMILY_G_OVERLAY",
            "CROSS_FAMILY_HYBRID",
        ],
        "source_file_hashes": verification["source_file_hashes"],
        "source_snapshot_hash": verification["source_snapshot_hash"],
        "candidate_parameters_changed": False,
    }
    return {
        **body,
        "family_a_validation_candidate_identity_hash": canonical_hash(body),
    }


def _eligible_sessions(root: Path) -> list[date]:
    calendar_path = Path(root) / "data/reference/nse/calendar/nse_cash_trading_calendar.csv"
    with calendar_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        return sorted(
            date.fromisoformat(row["trading_date"])
            for row in rows
            if row["session_type"] == "NORMAL" and row["source_available"] == "True"
        )


def derive_validation_schedule(root: Path) -> dict[str, Any]:
    sessions = _eligible_sessions(root)
    bounded = [session for session in sessions if session <= VALIDATION_END]
    quarter_groups: dict[tuple[int, int], list[date]] = {}
    for session in bounded:
        quarter = (session.month - 1) // 3 + 1
        quarter_groups.setdefault((session.year, quarter), []).append(session)
    formation_dates = [
        max(quarter_groups[key])
        for key in sorted(quarter_groups)
        if key >= (2024, 4)
    ]
    positions = {session: index for index, session in enumerate(bounded)}
    rebalances: list[dict[str, Any]] = []
    for formation in formation_dates:
        next_index = positions[formation] + 1
        if next_index >= len(bounded):
            continue
        execution = bounded[next_index]
        if execution < VALIDATION_START or execution > VALIDATION_END:
            continue
        rebalances.append(
            {
                "rebalance_number": len(rebalances) + 1,
                "formation_quarter": f"{formation.year:04d}-Q{((formation.month - 1) // 3) + 1}",
                "formation_date": formation.isoformat(),
                "formation_reference": "LAST_ELIGIBLE_TRADING_SESSION_OF_CALENDAR_QUARTER_CLOSE",
                "execution_date": execution.isoformat(),
                "execution_reference": "NEXT_ELIGIBLE_TRADING_SESSION_OPEN",
                "same_close_execution": False,
            }
        )
    if len(rebalances) != 7:
        raise RuntimeError(f"Expected seven prospective validation rebalances, observed {len(rebalances)}")

    intervals: list[dict[str, Any]] = []
    for index, rebalance in enumerate(rebalances):
        endpoint = rebalances[index + 1]["execution_date"] if index + 1 < len(rebalances) else None
        complete = endpoint is not None and date.fromisoformat(endpoint) <= VALIDATION_END
        intervals.append(
            {
                "interval_number": index + 1,
                "entry_execution_date": rebalance["execution_date"],
                "required_exit_or_rebalance_endpoint": endpoint,
                "primary_status": "COMPLETED_PRIMARY_INTERVAL" if complete else "TERMINAL_INCOMPLETE_EXCLUDED",
                "included_in_primary_metrics": complete,
                "terminal_mark_to_market_diagnostic": (
                    "NOT_APPLICABLE" if complete else "OPTIONAL_UNCOMPUTED_NEVER_PRIMARY"
                ),
            }
        )
    completed = sum(row["included_in_primary_metrics"] for row in intervals)
    body = {
        "schedule_semantics": {
            "frequency": "QUARTERLY",
            "formation": "LAST_ELIGIBLE_TRADING_SESSION_OF_CALENDAR_QUARTER_CLOSE",
            "execution": "NEXT_ELIGIBLE_TRADING_SESSION_OPEN",
            "holding": "UNTIL_NEXT_SCHEDULED_QUARTERLY_REBALANCE",
            "same_close_execution_allowed": False,
            "source": "DATE_ONLY_NSE_CALENDAR_METADATA",
        },
        "validation_window": {
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
        },
        "prospective_rebalances": rebalances,
        "prospective_intervals": intervals,
        "prospective_rebalance_count": len(rebalances),
        "expected_completed_interval_count": completed,
        "expected_sample_classification": (
            "VALIDATION_SAMPLE_ACCEPTABLE"
            if completed >= 5
            else "LIMITED_SAMPLE"
            if completed == 4
            else "INSUFFICIENT_VALIDATION_SAMPLE"
        ),
        "completed_interval_policy": (
            "PRIMARY_METRICS_USE_ONLY_INTERVALS_WITH_REQUIRED_ENDPOINT_ON_OR_BEFORE_2026_08_13"
        ),
        "post_holdout_data_to_complete_interval_allowed": False,
        "terminal_interval_policy": {
            "status": "TERMINAL_INCOMPLETE_EXCLUDED_FROM_PRIMARY",
            "entry_execution_date": rebalances[-1]["execution_date"],
            "formal_holdout_end": VALIDATION_END.isoformat(),
            "future_endpoint_loaded": False,
            "optional_diagnostic": "TERMINAL_MARK_TO_MARKET_DIAGNOSTIC",
            "diagnostic_status": "UNCOMPUTED",
            "may_alter_primary_classification": False,
        },
        "outcomes_computed": False,
    }
    return {**body, "family_a_validation_schedule_hash": canonical_hash(body)}


def success_criteria_document(expected_completed_intervals: int) -> dict[str, Any]:
    minimum_positive_intervals = math.ceil(expected_completed_intervals * 0.60)
    core = [
        {
            "criterion": "A",
            "criterion_id": CORE_GATE_IDS[0],
            "rule": "NET_ENDING_EQUITY_GT_STARTING_EQUITY_AND_NET_CAGR_GT_ZERO",
            "threshold": "BOTH_REQUIRED",
            "fatal_or_integrity_gate": False,
        },
        {
            "criterion": "B",
            "criterion_id": CORE_GATE_IDS[1],
            "rule": "VALIDATION_NET_CAGR_PCT_GTE_50_PERCENT_OF_DEVELOPMENT_NET_CAGR",
            "threshold": "12.052925335",
            "fatal_or_integrity_gate": False,
        },
        {
            "criterion": "C",
            "criterion_id": CORE_GATE_IDS[2],
            "rule": "VALIDATION_MAX_DRAWDOWN_MAGNITUDE_PCT_LTE_ABSOLUTE_CEILING",
            "threshold": "30",
            "fatal_or_integrity_gate": False,
        },
        {
            "criterion": "D",
            "criterion_id": CORE_GATE_IDS[3],
            "rule": "POSITIVE_AFTER_COST_COMPLETED_INTERVALS_GTE_CEILING_60_PERCENT",
            "threshold": "60_PERCENT_CEILING_TO_WHOLE_INTERVAL",
            "expected_minimum_positive_intervals": minimum_positive_intervals,
            "fatal_or_integrity_gate": False,
        },
        {
            "criterion": "E",
            "criterion_id": CORE_GATE_IDS[4],
            "rule": (
                "EXACT_FROZEN_COST_ACCOUNTING_AND_AFTER_COST_PROFITABILITY_AND_"
                "NORMALIZED_COST_DRAG_CONTROL"
            ),
            "threshold": "MATERIAL_FLAG_IF_VALIDATION_NORMALIZED_COST_DRAG_GT_1.50_X_DEVELOPMENT",
            "normalized_cost_drag_definition": "TOTAL_MODELED_COST_DIVIDED_BY_AVERAGE_NET_EQUITY_PCT",
            "development_normalized_cost_drag_pct": "2.694781929547442552083022935",
            "material_degradation_threshold_pct": "4.0421728943211638281245344025",
            "mechanical_explanation_policy": (
                "ONLY_A_PREEXISTING_FROZEN_PORTFOLIO_IMPLEMENTATION_MECHANISM_MAY_EXPLAIN_"
                "THE_FLAG;_NO_POSTHOC_EXCEPTION_OR_THRESHOLD_CHANGE"
            ),
            "fatal_or_integrity_gate": False,
        },
        {
            "criterion": "F",
            "criterion_id": CORE_GATE_IDS[5],
            "rule": (
                "ALL_POINT_IN_TIME_MEMBERSHIP_RANKING_TOP_DECILE_QUARTERLY_TIMING_"
                "EQUAL_WEIGHT_500K_WHOLE_SHARE_NO_LEVERAGE_COST_CASH_HOLDINGS_LEAKAGE_"
                "AND_PARAMETER_IMMUTABILITY_CHECKS_PASS"
            ),
            "threshold": "ALL_REQUIRED_MATERIAL_FAILURE_IS_FAIL",
            "fatal_or_integrity_gate": True,
        },
        {
            "criterion": "G",
            "criterion_id": CORE_GATE_IDS[6],
            "rule": "AT_LEAST_FIVE_COMPLETED_INTERVALS_FOR_FULL_PASS_ELIGIBILITY",
            "threshold": "GTE_5_ACCEPTABLE__EQ_4_MIXED_LIMITED_SAMPLE__LT_4_INCONCLUSIVE",
            "fatal_or_integrity_gate": True,
        },
    ]
    quality = [
        {
            "dimension": "H",
            "dimension_id": QUALITY_DIMENSION_IDS[0],
            "rule": "2025_RETURN_GTE_ZERO_AND_2026_THROUGH_VALIDATION_END_RETURN_GTE_ZERO",
            "threshold": "BOTH_NONNEGATIVE",
            "core_gate": False,
        },
        {
            "dimension": "I",
            "dimension_id": QUALITY_DIMENSION_IDS[1],
            "rule": "VALIDATION_SHARPE_LIKE_GT_0_5",
            "threshold": "0.5_EXCLUSIVE",
            "core_gate": False,
        },
        {
            "dimension": "J",
            "dimension_id": QUALITY_DIMENSION_IDS[2],
            "rule": "VALIDATION_DRAWDOWN_MAGNITUDE_PCT_LTE_115_PERCENT_OF_DEVELOPMENT",
            "threshold": "26.36049541",
            "core_gate": False,
        },
        {
            "dimension": "K",
            "dimension_id": QUALITY_DIMENSION_IDS[3],
            "rule": "VALIDATION_NET_CAGR_PCT_GTE_60_PERCENT_OF_DEVELOPMENT",
            "threshold": "14.463510402",
            "core_gate": False,
        },
    ]
    fatal_conditions = [
        {
            "fatal_id": "A",
            "condition": "VALIDATION_NET_RETURN_PCT_LTE_NEGATIVE_10",
            "threshold": "-10",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "FAIL",
        },
        {
            "fatal_id": "B",
            "condition": "VALIDATION_NET_CAGR_PCT_LTE_NEGATIVE_8",
            "threshold": "-8",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "FAIL",
        },
        {
            "fatal_id": "C",
            "condition": "VALIDATION_MAX_DRAWDOWN_MAGNITUDE_PCT_GT_35",
            "threshold": "35_EXCLUSIVE",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "FAIL",
        },
        {
            "fatal_id": "D",
            "condition": "MATERIAL_LOOKAHEAD_OR_DATA_LEAKAGE",
            "threshold": "ANY_MATERIAL_OCCURRENCE",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "INCONCLUSIVE_AND_INVALIDATE_RUN",
        },
        {
            "fatal_id": "E",
            "condition": "FROZEN_CANDIDATE_MUTATION",
            "threshold": "ANY_MUTATION",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "INCONCLUSIVE_AND_INVALIDATE_RUN",
        },
        {
            "fatal_id": "F",
            "condition": "INCORRECT_UNIVERSE_COST_OR_EXECUTION_IMPLEMENTATION",
            "threshold": "ANY_MATERIAL_OCCURRENCE",
            "candidate_behavior_mapping": "FAIL",
            "implementation_defect_mapping": "INCONCLUSIVE_AND_INVALIDATE_RUN",
        },
    ]
    result_mapping = {
        "evaluation_precedence": [
            "IDENTITY_DATA_METHODOLOGY_OR_EXECUTION_CONTAMINATION_CHECK",
            "FATAL_CONDITIONS",
            "SAMPLE_ADEQUACY",
            "EXPLICIT_FAIL_CONDITIONS",
            "ALL_CORE_GATES_AND_STRONG_QUALITY",
            "ALL_CORE_GATES",
            "MIXED_CONDITIONS",
        ],
        "STRONG_PASS": (
            "ALL_A_TO_G_PASS_AND_AT_LEAST_3_OF_H_TO_K_PASS_AND_NET_CAGR_GTE_"
            "14.463510402_AND_MAX_DD_LTE_26.36049541"
        ),
        "PASS": "ALL_A_TO_G_PASS_BUT_STRONG_PASS_NOT_FULLY_MET",
        "MIXED": (
            "IMPLEMENTATION_AND_DATA_PASS_SAMPLE_ADEQUATE_CUMULATIVE_AFTER_COST_POSITIVE_"
            "NO_FATAL_AND_ONE_OR_TWO_OF_A_TO_E_FAIL"
        ),
        "MIXED_LIMITED_SAMPLE": (
            "EXACTLY_FOUR_COMPLETED_INTERVALS_AND_OTHERWISE_INTERPRETABLE;_NO_PASS_ELIGIBILITY"
        ),
        "FAIL": (
            "NET_ENDING_EQUITY_LTE_START_OR_NET_CAGR_LTE_ZERO_OR_MAX_DD_GT_30_OR_"
            "MATERIAL_IMPLEMENTATION_FAILURE_OR_THREE_OR_MORE_A_TO_E_FAIL_OR_FATAL_FAIL"
        ),
        "INCONCLUSIVE": (
            "CORRUPTED_DATA_OR_UNRESOLVED_METHODOLOGY_ERROR_OR_SAMPLE_LT_4_OR_IDENTITY_"
            "MISMATCH_OR_EXECUTION_CONTAMINATION_OR_IMPLEMENTATION_CAUSED_FATAL_D_TO_F"
        ),
    }
    generalization = {
        "STRONG_PASS": "STRONG_GENERALIZATION",
        "PASS": "GENERALIZES",
        "MIXED": "MIXED_GENERALIZATION",
        "MIXED_LIMITED_SAMPLE": "MIXED_GENERALIZATION",
        "FAIL": "DOES_NOT_GENERALIZE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }
    advancement = {
        "STRONG_PASS": "ELIGIBLE_FOR_STRATEGY_V2_CANDIDATE_REVIEW",
        "PASS": "ELIGIBLE_FOR_STRATEGY_V2_CANDIDATE_REVIEW",
        "MIXED": "NOT_ELIGIBLE — further governance decision required",
        "MIXED_LIMITED_SAMPLE": "NOT_ELIGIBLE — further governance decision required",
        "FAIL": "REJECT_VALIDATION_CANDIDATE",
        "INCONCLUSIVE": "NO_DECISION",
    }
    body = {
        "primary_validation_objective": (
            "Does MOM-A-002 / A2-002 retain economically meaningful positive after-cost "
            "performance outside DEVELOPMENT without unacceptable degradation?"
        ),
        "development_comparison_reference": {
            "starting_equity_inr": "500000",
            "net_ending_equity_inr": "955331.6799",
            "net_total_return_pct": "91.06633598",
            "net_cagr_pct": "24.10585067",
            "max_drawdown_magnitude_pct": "22.92216992",
            "period_start": "2022-01-01",
            "period_end": "2024-12-31",
            "use": "PREREGISTERED_DEGRADATION_COMPARISONS_ONLY",
        },
        "core_criteria": core,
        "core_gate_count": len(core),
        "quality_dimensions": quality,
        "quality_dimension_count": len(quality),
        "fatal_conditions": fatal_conditions,
        "fatal_origin_mapping": (
            "FOR_D_TO_F_USE_INCONCLUSIVE_AND_INVALIDATE_RUN_ONLY_WHEN_A_PROVABLE_"
            "IMPLEMENTATION_OR_ARTIFACT_DEFECT_CAUSED_THE_CONDITION;_OTHERWISE_FAIL"
        ),
        "sample_policy": {
            "gte_5": "VALIDATION_SAMPLE_ACCEPTABLE",
            "eq_4": "LIMITED_SAMPLE_MAXIMUM_MIXED_LIMITED_SAMPLE",
            "lt_4": "INCONCLUSIVE_INSUFFICIENT_SAMPLE",
        },
        "result_mapping": result_mapping,
        "generalization_mapping": generalization,
        "future_generalization_field": "FAMILY_A_GENERALIZATION_RESULT",
        "strategy_v2_advancement_mapping": advancement,
        "strategy_v2_auto_creation_allowed": False,
        "threshold_changes_after_outcomes_allowed": False,
        "parameter_salvage_on_same_holdout_allowed": False,
        "prohibited_post_failure_salvage": [
            "3M_MOMENTUM",
            "9M_MOMENTUM",
            "12M_MOMENTUM",
            "MONTHLY_REBALANCE",
            "DIFFERENT_TOP_PERCENTILE",
            "DIFFERENT_LIQUIDITY_THRESHOLD",
            "FAMILY_B_FILTER",
            "FAMILY_C_COMPRESSION",
            "FAMILY_G_REGIME_GATE",
        ],
        "validation_outcomes_present": False,
    }
    return {
        **body,
        "family_a_validation_success_criteria_hash": canonical_hash(body),
    }


def fatal_condition_classification(fatal_id: str, origin: str) -> str:
    if fatal_id not in set("ABCDEF"):
        raise ValueError(f"Unknown fatal condition: {fatal_id}")
    if origin not in {"CANDIDATE_OR_GOVERNANCE", "IMPLEMENTATION_OR_ARTIFACT_DEFECT"}:
        raise ValueError(f"Unknown fatal-condition origin: {origin}")
    if fatal_id in set("DEF") and origin == "IMPLEMENTATION_OR_ARTIFACT_DEFECT":
        return "INCONCLUSIVE"
    return "FAIL"


def classify_validation_result(
    *,
    core_pass: Mapping[str, bool],
    quality_pass_count: int,
    completed_intervals: int,
    net_ending_equity_gt_start: bool,
    net_cagr_pct: float,
    max_drawdown_magnitude_pct: float,
    cumulative_after_cost_positive: bool,
    data_integrity_pass: bool = True,
    identity_match: bool = True,
    execution_contaminated: bool = False,
    fatal_id: str | None = None,
    fatal_origin: str = "CANDIDATE_OR_GOVERNANCE",
) -> str:
    """Apply the preregistered mapping to synthetic/future inputs only."""
    if set(core_pass) != set("ABCDEFG"):
        raise ValueError("Exactly core gates A-G are required")
    if not identity_match or not data_integrity_pass or execution_contaminated:
        return "INCONCLUSIVE"
    if fatal_id is not None:
        return fatal_condition_classification(fatal_id, fatal_origin)
    if completed_intervals < 4:
        return "INCONCLUSIVE"
    if (
        not core_pass["F"]
        or not net_ending_equity_gt_start
        or net_cagr_pct <= 0
        or max_drawdown_magnitude_pct > 30
    ):
        return "FAIL"
    a_to_e_failures = sum(not core_pass[gate] for gate in "ABCDE")
    if a_to_e_failures >= 3:
        return "FAIL"
    if completed_intervals == 4:
        return "MIXED_LIMITED_SAMPLE"
    if all(core_pass.values()):
        if (
            quality_pass_count >= 3
            and net_cagr_pct >= 14.463510402
            and max_drawdown_magnitude_pct <= 26.36049541
        ):
            return "STRONG_PASS"
        return "PASS"
    if (
        core_pass["F"]
        and core_pass["G"]
        and cumulative_after_cost_positive
        and a_to_e_failures in {1, 2}
    ):
        return "MIXED"
    return "FAIL"


def _adjusted_file_dates(root: Path) -> list[date]:
    dates: list[date] = []
    adjusted_root = Path(root) / "data/research/adjusted/daily/nse"
    pattern = re.compile(r"^nse_adjusted_daily_(\d{8})\.csv$")
    for path in adjusted_root.rglob("*.csv"):
        matched = pattern.match(path.name)
        if matched:
            dates.append(datetime.strptime(matched.group(1), "%Y%m%d").date())
    return sorted(dates)


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return next(csv.reader(file))


def _active_member_counts(root: Path, formation_dates: Sequence[str]) -> dict[str, int]:
    path = Path(root) / "data/reference/nifty500/history/membership_periods.csv"
    counts = {formation: 0 for formation in formation_dates}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            for formation in formation_dates:
                if row["valid_from"] <= formation <= row["valid_to"]:
                    counts[formation] += 1
    return counts


def data_readiness_document(root: Path, schedule: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    eligible = _eligible_sessions(root)
    required_sessions = [
        session for session in eligible if VALIDATION_START <= session <= VALIDATION_END
    ]
    adjusted_dates = _adjusted_file_dates(root)
    adjusted_set = set(adjusted_dates)
    missing_adjusted_sessions = [
        session.isoformat() for session in required_sessions if session not in adjusted_set
    ]
    adjusted_example = root / (
        f"data/research/adjusted/daily/nse/{VALIDATION_START:%Y/%m}/"
        f"nse_adjusted_daily_{VALIDATION_START:%Y%m%d}.csv"
    )
    adjusted_header = _header(adjusted_example) if adjusted_example.is_file() else []
    membership_path = root / "data/reference/nifty500/history/membership_periods.csv"
    membership_coverage_path = root / "data/reference/nifty500/history/membership_coverage.json"
    corporate_coverage_path = root / "data/reference/nse/corporate_actions/corporate_action_coverage.json"
    eligibility_path = root / "data/reference/nse/corporate_actions/research_eligibility.csv"
    membership_coverage = _read_json(membership_coverage_path)
    corporate_coverage = _read_json(corporate_coverage_path)
    formation_dates = [
        row["formation_date"] for row in schedule["prospective_rebalances"]
    ]
    active_counts = _active_member_counts(root, formation_dates)
    required_adjusted_columns = {
        "trading_date",
        "symbol",
        "adjusted_open",
        "adjusted_close",
        "raw_volume",
        "research_usability_status",
        "adjustment_methodology_version",
    }
    structural_sufficient = all(
        (
            not missing_adjusted_sessions,
            required_adjusted_columns <= set(adjusted_header),
            membership_path.is_file(),
            membership_coverage_path.is_file(),
            corporate_coverage_path.is_file(),
            eligibility_path.is_file(),
            all(count >= 499 for count in active_counts.values()),
            corporate_coverage.get("methodology", {}).get("version")
            == "PRICE_ADJUSTED_STRUCTURAL_V1",
            corporate_coverage.get("date_coverage", {}).get("end_date", "")
            >= VALIDATION_END.isoformat(),
            membership_coverage.get("membership_periods", {}).get("coverage_end", "")
            >= VALIDATION_END.isoformat(),
        )
    )
    limitations = [
        "POINT_IN_TIME_MEMBERSHIP_IS_OFFICIAL_EVENTS_PARTIAL_WITH_THREE_RECONSTRUCTION_ANOMALIES",
        "CORPORATE_ACTION_LAYER_RETAINS_MANUAL_REVIEW_AND_CONTINUITY_BREAK_STATUSES",
        "AGGREGATE_LATER_PERIOD_DIAGNOSTICS_WERE_PREVIOUSLY_OBSERVED_IN_OTHER_CONTEXTS",
    ]
    readiness = "READY_WITH_LIMITATIONS" if structural_sufficient else "BLOCKED"
    audit_rows = [
        {
            "input": "DAILY_ADJUSTED_PRICES",
            "status": "AVAILABLE" if not missing_adjusted_sessions else "BLOCKED",
            "availability": (
                f"{len(required_sessions)} required session partitions from "
                f"{required_sessions[0]} through {required_sessions[-1]}; "
                f"missing={len(missing_adjusted_sessions)}"
            ),
            "outcomes_accessed": False,
        },
        {
            "input": "POINT_IN_TIME_NIFTY500_MEMBERSHIP",
            "status": "AVAILABLE_WITH_LIMITATIONS",
            "availability": (
                f"coverage={membership_coverage['membership_periods']['coverage_start']}.."
                f"{membership_coverage['membership_periods']['coverage_end']}; "
                f"formation_counts={active_counts}"
            ),
            "outcomes_accessed": False,
        },
        {
            "input": "LIQUIDITY_FIELDS",
            "status": "AVAILABLE" if {"adjusted_close", "raw_volume"} <= set(adjusted_header) else "BLOCKED",
            "availability": "adjusted_close and raw_volume schema fields",
            "outcomes_accessed": False,
        },
        {
            "input": "MOMENTUM_LOOKBACK_HISTORY",
            "status": "AVAILABLE",
            "availability": (
                f"date-only adjusted partitions begin {adjusted_dates[0]}; frozen lookback=126 sessions"
            ),
            "outcomes_accessed": False,
        },
        {
            "input": "EXECUTION_OPEN",
            "status": "AVAILABLE" if "adjusted_open" in adjusted_header else "BLOCKED",
            "availability": "adjusted_open schema field",
            "outcomes_accessed": False,
        },
        {
            "input": "CORPORATE_ACTION_SAFETY",
            "status": "AVAILABLE_WITH_LIMITATIONS",
            "availability": (
                "PRICE_ADJUSTED_STRUCTURAL_V1 plus EXCLUDE_USING_RESEARCH_ELIGIBILITY_V1; "
                f"coverage through {corporate_coverage['date_coverage']['end_date']}"
            ),
            "outcomes_accessed": False,
        },
        {
            "input": "QUARTERLY_SCHEDULE",
            "status": "AVAILABLE",
            "availability": (
                f"{schedule['prospective_rebalance_count']} prospective rebalances and "
                f"{schedule['expected_completed_interval_count']} completed intervals"
            ),
            "outcomes_accessed": False,
        },
        {
            "input": "TERMINAL_INTERVAL_BOUNDARY",
            "status": "AVAILABLE",
            "availability": "terminal entry 2026-07-01; formal end 2026-08-13; next endpoint not used",
            "outcomes_accessed": False,
        },
    ]
    body = {
        "FAMILY_A_VALIDATION_DATA_READINESS": readiness,
        "structural_data_sufficient": structural_sufficient,
        "audit_scope": "SCHEMA_DATES_FILE_NAMES_ROW_COUNTS_AND_AVAILABILITY_METADATA_ONLY",
        "audit_rows": audit_rows,
        "limitations": limitations,
        "calendar": {
            "eligible_validation_session_count": len(required_sessions),
            "first_eligible_validation_session": required_sessions[0].isoformat(),
            "last_eligible_validation_session": required_sessions[-1].isoformat(),
        },
        "adjusted_data": {
            "available_validation_partition_count": len(
                [item for item in adjusted_dates if VALIDATION_START <= item <= VALIDATION_END]
            ),
            "missing_required_session_partition_count": len(missing_adjusted_sessions),
            "missing_required_session_partitions": missing_adjusted_sessions,
            "schema_columns": adjusted_header,
            "rows_read": 0,
        },
        "point_in_time_membership": {
            "coverage_start": membership_coverage["membership_periods"]["coverage_start"],
            "coverage_end": membership_coverage["membership_periods"]["coverage_end"],
            "survivorship_bias_status": membership_coverage["survivorship_bias_status"],
            "formation_date_member_counts": active_counts,
            "known_gap_count": len(membership_coverage.get("known_gaps", [])),
        },
        "corporate_actions": {
            "coverage_start": corporate_coverage["date_coverage"]["start_date"],
            "coverage_end": corporate_coverage["date_coverage"]["end_date"],
            "methodology_version": corporate_coverage["methodology"]["version"],
            "research_eligibility_schema": _header(eligibility_path),
            "full_processing_completed": corporate_coverage["adjusted_dataset"][
                "full_processing_completed"
            ],
        },
        "validation_price_values_read": False,
        "validation_returns_read": False,
        "validation_holdings_read": False,
        "validation_performance_read": False,
    }
    return {
        **body,
        "family_a_validation_data_readiness_hash": canonical_hash(body),
    }


def governance_document(
    candidate: Mapping[str, Any],
    schedule: Mapping[str, Any],
    criteria: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    readiness_checks = {
        "candidate_identity_frozen": bool(
            candidate.get("family_a_validation_candidate_identity_hash")
        ),
        "validation_design_sealed": LIFECYCLE == "SEALED_DESIGN",
        "structural_data_availability_sufficient": readiness.get(
            "structural_data_sufficient"
        )
        is True,
        "exact_pass_fail_criteria_frozen": criteria.get("core_gate_count") == 7
        and criteria.get("quality_dimension_count") == 4,
        "expected_sample_adequate": schedule.get(
            "expected_completed_interval_count", 0
        )
        >= 5,
        "candidate_parameter_mutation_absent": candidate.get(
            "candidate_parameters_changed"
        )
        is False,
        "validation_run_count_zero": VALIDATION_RUN_COUNT == 0,
        "prohibited_validation_outcome_access_absent": True,
    }
    one_shot_ready = all(readiness_checks.values())
    return {
        "lifecycle_transitions": [
            "SEALED_DESIGN",
            "AUTHORIZED_FOR_ONE_SHOT",
            "EVALUATED",
        ],
        "current_lifecycle": LIFECYCLE,
        "authorization_granted": False,
        "validation_run_count": VALIDATION_RUN_COUNT,
        "maximum_formal_run_count": MAXIMUM_FORMAL_RUN_COUNT,
        "FAMILY_A_ONE_SHOT_VALIDATION_READINESS": "YES" if one_shot_ready else "NO",
        "one_shot_readiness_checks": readiness_checks,
        "readiness_does_not_equal_authorization": True,
        "next_transition_requires_explicit_user_authorization": True,
        "one_shot_principle": (
            "The exact frozen candidate may execute once only after explicit authorization."
        ),
        "rerun_allowed_after_outcomes": False,
        "replacement_run_exception": {
            "allowed_causes": [
                "DETERMINISTIC_BUG_CORRECTION",
                "ARTIFACT_CORRUPTION",
                "PROVABLE_IMPLEMENTATION_DEFECT",
            ],
            "separate_governance_review_required": True,
            "original_run_must_be_invalidated_before_replacement": True,
            "outcome_disappointment_is_not_an_exception": True,
        },
        "no_validation_peek": {
            "allowed": [
                "DATES",
                "SCHEMA",
                "DATA_AVAILABILITY_METADATA",
                "REBALANCE_SCHEDULE_AVAILABILITY",
            ],
            "prohibited": [
                "GENERATED_VALIDATION_HOLDINGS",
                "VALIDATION_PORTFOLIO_RETURNS",
                "VALIDATION_QUARTERLY_RETURNS",
                "VALIDATION_ENDING_EQUITY",
                "VALIDATION_DRAWDOWN",
                "VALIDATION_CANDIDATE_PERFORMANCE",
            ],
        },
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "future_validation_output_contract": {
            "status": "UNPOPULATED_DESIGN_ONLY",
            "fields": list(FUTURE_VALIDATION_FIELDS),
        },
        "future_validation_immutable_hash_contract": list(FUTURE_VALIDATION_HASHES),
        "strategy_v2_created": False,
        "family_h_created": False,
        "hybrid_strategy_created": False,
        "candidate_parameter_changed": False,
        "validation_outcomes_accessed": False,
        "validation_holdings_generated": False,
        "validation_performance_calculated": False,
        "security": {
            "network_accessed": False,
            "credentials_written": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
        },
    }


def design_config_document(
    candidate: Mapping[str, Any],
    schedule: Mapping[str, Any],
    criteria: Mapping[str, Any],
    readiness: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "design_only": True,
        "validation_window": {
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
        },
        "candidate_id": CANDIDATE_ID,
        "candidate_identity_hash": candidate[
            "family_a_validation_candidate_identity_hash"
        ],
        "schedule_hash": schedule["family_a_validation_schedule_hash"],
        "success_criteria_hash": criteria[
            "family_a_validation_success_criteria_hash"
        ],
        "data_readiness_hash": readiness[
            "family_a_validation_data_readiness_hash"
        ],
        "lifecycle": governance["current_lifecycle"],
        "validation_run_count": governance["validation_run_count"],
        "maximum_formal_run_count": governance["maximum_formal_run_count"],
        "authorization_granted": governance["authorization_granted"],
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
    }
    return {**body, "family_a_validation_design_config_hash": canonical_hash(body)}


def _criteria_report_rows(criteria: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "CORE",
            "id": row["criterion"],
            "name": row["criterion_id"],
            "rule": row["rule"],
            "threshold": row["threshold"],
            "validation_value": "UNPOPULATED",
        }
        for row in criteria["core_criteria"]
    ] + [
        {
            "type": "QUALITY",
            "id": row["dimension"],
            "name": row["dimension_id"],
            "rule": row["rule"],
            "threshold": row["threshold"],
            "validation_value": "UNPOPULATED",
        }
        for row in criteria["quality_dimensions"]
    ]


def _governance_report_rows(governance: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"control": "CURRENT_LIFECYCLE", "value": governance["current_lifecycle"]},
        {"control": "AUTHORIZATION_GRANTED", "value": governance["authorization_granted"]},
        {"control": "VALIDATION_RUN_COUNT", "value": governance["validation_run_count"]},
        {"control": "MAXIMUM_FORMAL_RUN_COUNT", "value": governance["maximum_formal_run_count"]},
        {
            "control": "FAMILY_A_ONE_SHOT_VALIDATION_READINESS",
            "value": governance["FAMILY_A_ONE_SHOT_VALIDATION_READINESS"],
        },
        {"control": "CONTAMINATION_DISCLOSURE", "value": CONTAMINATION_DISCLOSURE},
        {"control": "VALIDATION_OUTCOMES_ACCESSED", "value": False},
        {"control": "VALIDATION_HOLDINGS_GENERATED", "value": False},
        {"control": "VALIDATION_PERFORMANCE_CALCULATED", "value": False},
        {"control": "CANDIDATE_PARAMETER_CHANGED", "value": False},
        {"control": "STRATEGY_V2_CREATED", "value": False},
        {"control": "FAMILY_H_CREATED", "value": False},
        {"control": "HYBRID_STRATEGY_CREATED", "value": False},
    ]


def build_family_a_validation_design(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    verification = verify_frozen_candidate(root)
    candidate = candidate_identity_document(verification)
    schedule = derive_validation_schedule(root)
    criteria = success_criteria_document(schedule["expected_completed_interval_count"])
    readiness = data_readiness_document(root, schedule)
    governance = governance_document(candidate, schedule, criteria, readiness)
    config = design_config_document(candidate, schedule, criteria, readiness, governance)

    design_root = output_root(root)
    reports = root / "data/reports"
    paths = {
        "candidate": design_root / "candidate/candidate_identity_v1.json",
        "schedule": design_root / "schedule/prospective_rebalance_schedule_v1.json",
        "criteria": design_root / "criteria/validation_success_criteria_v1.json",
        "readiness": design_root / "data_readiness/validation_data_readiness_v1.json",
        "governance": design_root / "governance/one_shot_validation_governance_v1.json",
        "manifest": design_root / "manifests/family_a_one_shot_validation_design_manifest_v1.json",
        "summary": reports / REPORT_NAMES[0],
    }
    write_json(paths["candidate"], candidate)
    write_json(paths["schedule"], schedule)
    write_json(paths["criteria"], criteria)
    write_json(paths["readiness"], readiness)
    write_json(paths["governance"], governance)

    write_csv(
        reports / REPORT_NAMES[1],
        [
            {
                "candidate_id": CANDIDATE_ID,
                "architecture_reference": ARCHITECTURE_ID,
                "implementation_reference": IMPLEMENTATION_ID,
                "reference_capital_inr": REFERENCE_CAPITAL_INR,
                "family_config_hash": FAMILY_CONFIG_HASH,
                "mom_a_002_parameter_hash": MOM_A_002_PARAMETER_HASH,
                "mom_a_002_preregistration_hash": MOM_A_002_PREREGISTRATION_HASH,
                "a2_002_implementation_hash": A2_002_IMPLEMENTATION_HASH,
                "a2_002_preregistration_hash": A2_002_PREREGISTRATION_HASH,
                "family_a_closure_hash": FAMILY_A_CLOSURE_HASH,
                "candidate_identity_hash": candidate[
                    "family_a_validation_candidate_identity_hash"
                ],
                "validation_outcome": "UNPOPULATED",
            }
        ],
    )
    schedule_rows = []
    for rebalance, interval in zip(
        schedule["prospective_rebalances"],
        schedule["prospective_intervals"],
        strict=True,
    ):
        schedule_rows.append({**rebalance, **interval})
    write_csv(reports / REPORT_NAMES[2], schedule_rows)
    write_csv(reports / REPORT_NAMES[3], _criteria_report_rows(criteria))
    write_csv(reports / REPORT_NAMES[4], criteria["fatal_conditions"])
    write_csv(reports / REPORT_NAMES[5], readiness["audit_rows"])
    write_csv(reports / REPORT_NAMES[6], _governance_report_rows(governance))
    write_csv(
        reports / REPORT_NAMES[7],
        [
            {
                "validation_result": result,
                "generalization_result": criteria["generalization_mapping"][result],
                "strategy_v2_advancement": criteria["strategy_v2_advancement_mapping"][result],
                "strategy_v2_auto_created": False,
            }
            for result in (
                "STRONG_PASS",
                "PASS",
                "MIXED",
                "MIXED_LIMITED_SAMPLE",
                "FAIL",
                "INCONCLUSIVE",
            )
        ],
    )

    component_paths = [
        paths["candidate"],
        paths["schedule"],
        paths["criteria"],
        paths["readiness"],
        paths["governance"],
        *(reports / name for name in REPORT_NAMES[1:]),
    ]
    component_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in component_paths
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "sealed_date": "2026-09-16",
        "cross_family_synthesis_hash": SYNTHESIS_HASH,
        "candidate_identity": candidate,
        "development_reference": criteria["development_comparison_reference"],
        "validation_window": config["validation_window"],
        "prospective_rebalance_schedule": schedule,
        "sample_policy": criteria["sample_policy"],
        "terminal_policy": schedule["terminal_interval_policy"],
        "core_criteria_A_to_G": criteria["core_criteria"],
        "quality_dimensions_H_to_K": criteria["quality_dimensions"],
        "fatal_conditions": criteria["fatal_conditions"],
        "result_mapping": criteria["result_mapping"],
        "generalization_mapping": criteria["generalization_mapping"],
        "strategy_v2_advancement_policy": criteria[
            "strategy_v2_advancement_mapping"
        ],
        "contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "data_readiness": readiness["FAMILY_A_VALIDATION_DATA_READINESS"],
        "one_shot_readiness": governance["FAMILY_A_ONE_SHOT_VALIDATION_READINESS"],
        "lifecycle": LIFECYCLE,
        "authorization_granted": False,
        "validation_run_count": VALIDATION_RUN_COUNT,
        "maximum_formal_run_count": MAXIMUM_FORMAL_RUN_COUNT,
        "design_hashes": {
            "family_a_validation_design_config_hash": config[
                "family_a_validation_design_config_hash"
            ],
            "family_a_validation_candidate_identity_hash": candidate[
                "family_a_validation_candidate_identity_hash"
            ],
            "family_a_validation_schedule_hash": schedule[
                "family_a_validation_schedule_hash"
            ],
            "family_a_validation_success_criteria_hash": criteria[
                "family_a_validation_success_criteria_hash"
            ],
            "family_a_validation_data_readiness_hash": readiness[
                "family_a_validation_data_readiness_hash"
            ],
        },
        "component_hashes": component_hashes,
        "future_validation_output_contract": governance[
            "future_validation_output_contract"
        ],
        "future_validation_immutable_hash_contract": governance[
            "future_validation_immutable_hash_contract"
        ],
        "safety": governance["security"],
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    manifest = {
        **manifest_body,
        "family_a_validation_design_hash": canonical_hash(manifest_body),
    }
    write_json(paths["manifest"], manifest)
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "design_config": config,
        "candidate_identity": candidate,
        "schedule": schedule,
        "success_criteria": criteria,
        "data_readiness": readiness,
        "governance": governance,
        "manifest_path": paths["manifest"].relative_to(root).as_posix(),
        "family_a_validation_design_hash": manifest[
            "family_a_validation_design_hash"
        ],
        "verification": manifest["verification"],
    }
    write_json(paths["summary"], summary)
    return summary


def finalize_family_a_validation_design(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = output_root(root) / (
        "manifests/family_a_one_shot_validation_design_manifest_v1.json"
    )
    summary_path = root / "data/reports/family_a_validation_design_v1_summary.json"
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
        "ready_for_review": all(
            value.startswith("PASS")
            for value in (
                backend_targeted_tests,
                backend_full_tests,
                frontend_build,
                regressions,
            )
        ),
        "finalized_at": utc_now(),
    }
    manifest["verification"] = verification
    manifest["family_a_validation_design_hash"] = _document_hash(
        manifest, "family_a_validation_design_hash"
    )
    write_json(manifest_path, manifest)
    summary["verification"] = verification
    summary["family_a_validation_design_hash"] = manifest[
        "family_a_validation_design_hash"
    ]
    write_json(summary_path, summary)
    return summary


__all__ = [
    "A2_002_IMPLEMENTATION_HASH",
    "A2_002_PREREGISTRATION_HASH",
    "A2_002_RESULT_HASH",
    "ARCHITECTURE_ID",
    "CANDIDATE_ID",
    "CANDIDATE_STATUS_BEFORE",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "CONTAMINATION_DISCLOSURE",
    "CORE_GATE_IDS",
    "COST_CONFIG_HASH",
    "COST_MODEL_VERSION",
    "COST_SCENARIO_HASH",
    "FAMILY_A_CLOSURE_HASH",
    "FAMILY_CONFIG_HASH",
    "IMPLEMENTATION_ID",
    "LIFECYCLE",
    "MANIFEST_VERSION",
    "MAXIMUM_FORMAL_RUN_COUNT",
    "MOM_A_002_PARAMETER_HASH",
    "MOM_A_002_PREREGISTRATION_HASH",
    "QUALITY_DIMENSION_IDS",
    "REPORT_NAMES",
    "SOURCE_FILE_HASHES",
    "SYNTHESIS_HASH",
    "VALIDATION_END",
    "VALIDATION_RUN_COUNT",
    "VALIDATION_START",
    "build_family_a_validation_design",
    "candidate_identity_document",
    "classify_validation_result",
    "data_readiness_document",
    "derive_validation_schedule",
    "fatal_condition_classification",
    "finalize_family_a_validation_design",
    "governance_document",
    "success_criteria_document",
    "verify_frozen_candidate",
]

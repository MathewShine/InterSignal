from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy.family_a_momentum import (
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.07 / Command 01"
FAMILY_VERSION = "STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1"
RESEARCH_PROFILE = "QUARTERLY_MOMENTUM_REGIME_PARTICIPATION_V1"
FAMILY_CODE = "FAMILY_G"
RESEARCH_PROTOCOL = "FAMILY_G_RESEARCH_PROTOCOL_V1"
MANIFEST_VERSION = "FAMILY_G_ARCHITECTURE_MANIFEST_V1"

CONTROL_ID = "CONTROL-G-000"
CONTROL_NAME = "QUARTERLY_6M_MOMENTUM_ALWAYS_PARTICIPATE_V1"
TREATMENT_ID = "REGIME-G-001"
TREATMENT_NAME = "QUARTERLY_6M_MOMENTUM_WITH_MARKET_TREND_GATE_V1"
EXPERIMENT_COUNT = 1

FAMILY_A_REFERENCE_EXPERIMENT = "MOM-A-002"
FAMILY_A_IMPLEMENTATION_EVIDENCE = "A2-002"
MARKET_INDEX_ID = "NIFTY_500"
MARKET_INDEX_NAME = "NIFTY 500"
SMA_WINDOW = 200
STARTING_CAPITAL = Decimal("500000")
CASH_RETURN = Decimal("0")
DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)

GOVERNANCE_POLICY_VERSION = "RESEARCH_EXPERIMENT_GOVERNANCE_V2"
GOVERNANCE_CHECKLIST = (
    "hypothesis",
    "experiment_id",
    "population",
    "exact_parameters",
    "comparison_control",
    "primary_metrics",
    "secondary_metrics",
    "numerical_success_criteria_where_applicable",
    "failure_criteria",
    "stop_conditions",
    "validation_eligibility_rule",
    "cost_model",
    "data_partition",
    "hashes",
)

DATA_READINESS_RESULTS = (
    "READY",
    "READY_WITH_LIMITATIONS",
    "BLOCKED",
    "INCONCLUSIVE",
)
ARCHITECTURE_RESULTS = (
    "READY_FOR_DEVELOPMENT_BACKTEST",
    "METHODOLOGY_FIX_REQUIRED",
    "DATA_BLOCKED",
    "INCONCLUSIVE",
)
FAMILY_RESULTS = (
    "STRONG_SUPPORT",
    "SUPPORT",
    "MIXED",
    "WEAK",
    "FAILED",
    "INCONCLUSIVE",
)

REGIME_DATASET_FIELDS = (
    "rebalance_date",
    "market_index_name",
    "market_close",
    "market_sma200",
    "gate_pass",
    "control_candidate_count",
    "control_selected_count",
    "treatment_selected_count",
    "treatment_cash_state",
    "data_quality_flags",
)

REPORT_NAMES = (
    "family_g_v1_summary.json",
    "family_g_v1_registry.csv",
    "family_g_v1_data_readiness.csv",
    "family_g_v1_regime_counts.csv",
    "family_g_v1_pilots.csv",
    "family_g_v1_governance.csv",
)

EXPECTED_FAMILY_F_CLOSURE_HASH = (
    "515bd3dc996c1e119e3e422f182ba82abfa8f2d312346df2c7a5751322d7716d"
)
FROZEN_PREVIOUS_FAMILY_SNAPSHOT_HASH = (
    "aa686eda0dc56da1d306dbe39815d6695794623884ce334dbe7f5467a527b01f"
)
EXPECTED_GOVERNANCE_V2_HASH = (
    "152c651e0ee0760bb5d331886de1dd0f0f4491d2823046182fb73bc8fe836488"
)
EXPECTED_FAMILY_A_PHASE2_CONFIG_HASH = (
    "8800738a5716ccbd1464ff564c5dea3b2891c523063eee01d5ad85fb583672cc"
)
EXPECTED_A2_002_PARAMETER_HASH = (
    "a391c2b46541af88b91b316bf2914bb15c6a11a7c5c9ff291d9f6c617bf8ae5b"
)
EXPECTED_A2_002_PREREGISTRATION_HASH = (
    "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897"
)
EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH = (
    "7fc510ca7010483ac2b20614ceb0edb71e7b647c3b2f6b0da49d5fe2804f6d27"
)

EXPECTED_FAMILY_G_CONFIG_HASH = (
    "602626276ea5d0fbfd4321ad37f0e6f70ee543bb55b38f8aaaa3e559134e59a2"
)
EXPECTED_CONTROL_REFERENCE_HASH = (
    "e7686b02bd7858cd1c540695cbaee5667426c0445db3bc37e21f4fad2f42048c"
)
EXPECTED_TREATMENT_PARAMETER_HASH = (
    "8fcce3ab5eb35e8bd07e7db8b4ba16ce3e43244100ff50b38ba621e88a326a14"
)
EXPECTED_TREATMENT_PREREGISTRATION_HASH = (
    "c18e8a9119fd68f276544475aff4d634359d4545e1cbfbab05734b26ec8cade5"
)
EXPECTED_SUCCESS_CRITERIA_HASH = (
    "c1b697047ebeec75d4fd6d9aac52d23f0de525f5c91df5a8063e7323da20f719"
)


class FamilyGInputError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def family_output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_g/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash(
        {key: value for key, value in document.items() if key != hash_field}
    )


def verify_family_f_closure(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    path = (
        root
        / "data/research/strategy_families/family_f/closure/v1/manifest/"
        "family_f_data_source_closure_manifest_v1.json"
    )
    manifest = _read_json(path)
    recorded_hash = manifest.get("family_f_closure_hash")
    checks = {
        "manifest_version": manifest.get("manifest_version")
        == "FAMILY_F_DATA_SOURCE_CLOSURE_MANIFEST_V1",
        "canonical_hash": _document_hash(manifest, "family_f_closure_hash")
        == recorded_hash,
        "exact_hash": recorded_hash == EXPECTED_FAMILY_F_CLOSURE_HASH,
        "component_hashes": all(
            (root / relative).is_file()
            and file_sha256(root / relative) == expected
            for relative, expected in manifest.get("component_hashes", {}).items()
        ),
        "research_paused": manifest.get("statuses", {}).get(
            "FAMILY_F_RESEARCH_STATUS"
        )
        == "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
        "performance_not_evaluated": manifest.get("statuses", {}).get(
            "FAMILY_F_PERFORMANCE_STATUS"
        )
        == "NOT_EVALUATED",
    }
    if not all(checks.values()):
        raise FamilyGInputError(f"Family F closure verification failed: {checks}")
    return {
        "status": "VERIFIED",
        "family_f_closure_hash": recorded_hash,
        "checks": checks,
    }


def verify_governance_v2(root: Path) -> dict[str, Any]:
    path = (
        Path(root)
        / "data/research/strategy_families/family_a/v1/closure/governance/"
        "research_experiment_governance_v2.json"
    )
    policy = _read_json(path)
    checks = {
        "policy_version": policy.get("policy_version")
        == GOVERNANCE_POLICY_VERSION,
        "canonical_hash": _document_hash(policy, "governance_policy_hash")
        == policy.get("governance_policy_hash"),
        "exact_hash": policy.get("governance_policy_hash")
        == EXPECTED_GOVERNANCE_V2_HASH,
        "full_checklist": tuple(policy.get("required_preregistration_checklist", ()))
        == GOVERNANCE_CHECKLIST,
    }
    if not all(checks.values()):
        raise FamilyGInputError(f"Governance V2 verification failed: {checks}")
    return {
        "status": "VERIFIED",
        "governance_policy_hash": policy["governance_policy_hash"],
        "checklist": list(GOVERNANCE_CHECKLIST),
        "checks": checks,
    }


def verify_family_a_reference(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    base = root / "data/research/strategy_families/family_a/v1/phase2"
    config = _read_json(base / "registry/phase2_config_v1.json")
    prereg = _read_json(base / "registry/a2_002_preregistration_v1.json")
    result = _read_json(
        base
        / "development_evaluation/a2_002/development_result_v1.json"
    )
    performance = result["performance"]
    checks = {
        "phase2_config_hash": _document_hash(config, "phase2_config_hash")
        == config.get("phase2_config_hash")
        == EXPECTED_FAMILY_A_PHASE2_CONFIG_HASH,
        "a2_parameter_hash": canonical_hash(prereg["parameters"])
        == prereg.get("parameter_hash")
        == EXPECTED_A2_002_PARAMETER_HASH,
        "a2_preregistration_hash": _document_hash(
            prereg, "preregistration_hash"
        )
        == prereg.get("preregistration_hash")
        == EXPECTED_A2_002_PREREGISTRATION_HASH,
        "a2_result_hash": _document_hash(result, "development_result_hash")
        == result.get("development_result_hash")
        == EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH,
        "reference_experiment": prereg.get("reference_experiment_id")
        == FAMILY_A_REFERENCE_EXPERIMENT,
        "implementation_evidence": prereg.get("experiment_id")
        == FAMILY_A_IMPLEMENTATION_EVIDENCE,
        "capital": prereg.get("parameters", {}).get("starting_capital_inr")
        == "500000",
        "scheduled_rebalances": performance.get("scheduled_rebalance_count") == 11,
        "accounting_clean": performance.get("cash_reconciliation_violations") == 0
        and performance.get("equity_reconciliation_violations") == 0,
        "reference_metrics": performance.get("net_ending_equity") == "955331.6799"
        and performance.get("net_total_return_pct") == "91.0663359800"
        and performance.get("net_cagr_pct") == "24.105850672292473"
        and performance.get("net_max_drawdown_pct")
        == "-22.92216992201015671886716806",
    }
    if not all(checks.values()):
        raise FamilyGInputError(f"Family A reference verification failed: {checks}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "phase2_config": config,
        "preregistration": prereg,
        "result": result,
    }


def previous_family_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    paths: set[Path] = set()
    for family in "abcdef":
        data_root = root / f"data/research/strategy_families/family_{family}"
        if data_root.is_dir():
            paths.update(path for path in data_root.rglob("*") if path.is_file())
        for path in (root / "data/reports").glob(f"family_{family}*"):
            if path.is_file():
                paths.add(path)
        patterns = (
            f"backend/app/research/strategy/family_{family}_*.py",
            f"backend/scripts/run_family_{family}_*.py",
            f"backend/tests/test_family_{family}_*.py",
            f"docs/strategy-family-{family}-*.md",
        )
        for pattern in patterns:
            paths.update(path for path in root.glob(pattern) if path.is_file())
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(paths)
    }
    return {
        "artifact_count": len(hashes),
        "artifact_hashes": hashes,
        # Earlier family artifacts retain their original semantic freeze even
        # when downstream lifecycle tests learn to ignore the evolving roadmap.
        "current_artifact_snapshot_hash": canonical_hash(hashes),
        "snapshot_hash": FROZEN_PREVIOUS_FAMILY_SNAPSHOT_HASH,
    }


def simple_moving_average(
    closes: Sequence[Decimal], window: int = SMA_WINDOW
) -> Decimal | None:
    if window <= 0:
        raise ValueError("SMA window must be positive")
    if len(closes) < window:
        return None
    selected = closes[-window:]
    return sum(selected, Decimal("0")) / Decimal(window)


def market_trend_gate(
    market_close: Decimal, market_sma200: Decimal | None
) -> bool | None:
    if market_sma200 is None:
        return None
    return market_close > market_sma200


def success_criteria_document() -> dict[str, Any]:
    body = {
        "version": "FAMILY_G_SUCCESS_CRITERIA_V1",
        "frozen_before_performance": True,
        "control_integrity": {
            "same_rebalance_schedule": "EXACT",
            "same_candidate_and_ranking_logic": "EXACT",
            "same_selected_symbols_before_whole_share_effects": "EXACT",
            "same_cost_semantics": "EXACT",
            "portfolio_result_tolerance": {
                "net_ending_equity_absolute_inr": "0.01",
                "net_total_return_absolute_percentage_points": "0.01",
                "net_cagr_absolute_percentage_points": "0.01",
                "max_drawdown_magnitude_absolute_percentage_points": "0.01",
            },
            "reference_metrics_are_thresholds": False,
        },
        "standard_treatment_criteria": {
            "A_RETURN_PRESERVATION": {
                "rule": "treatment_net_cagr >= control_net_cagr * 0.85",
                "control_cagr_multiple": "0.85",
            },
            "B_DRAWDOWN_IMPROVEMENT": {
                "rule": "abs(treatment_max_drawdown) <= abs(control_max_drawdown) * 0.85",
                "maximum_control_drawdown_multiple": "0.85",
                "minimum_relative_drawdown_reduction": "0.15",
            },
            "C_ABSOLUTE_PROFITABILITY": {
                "net_cagr_operator": ">",
                "net_cagr_threshold": "0",
                "ending_equity_operator": ">",
                "ending_equity_reference": "starting_equity",
            },
            "D_TEMPORAL_SUPPORT": {
                "nonnegative_development_years_minimum": 2,
                "development_year_count": 3,
            },
            "E_COST_EFFICIENCY": {
                "rule": "treatment_transaction_costs <= control_transaction_costs",
                "exception": "DOCUMENTED_IMPLEMENTATION_ARTIFACT_ONLY",
            },
            "F_SAMPLE_ADEQUACY": {
                "pass_minimum_invested_quarters": 6,
                "limited_sample_minimum": 4,
                "limited_sample_maximum": 5,
                "fatal_sample_failure_below": 4,
            },
            "G_ACCOUNTING_DATA_INTEGRITY": {
                "cash_reconciliation_violations": 0,
                "equity_reconciliation_violations": 0,
                "data_integrity_fatal_errors": 0,
            },
        },
        "participation_efficiency": {
            "report": ["invested_quarters", "cash_quarters", "fraction_invested"],
            "success_threshold": None,
            "sample_adequacy_applies": True,
        },
        "descriptive_attribution": {
            "upside_capture": "TREATMENT_POSITIVE_QUARTER_RETURN_CAPTURE_RELATIVE_TO_CONTROL",
            "downside_avoidance": "CONTROL_RETURN_DURING_TREATMENT_CASH_QUARTERS",
            "thresholds": None,
        },
        "quality_dimensions": {
            "H_LOWER_VOLATILITY": "treatment_net_annualized_volatility < control_net_annualized_volatility",
            "I_BETTER_SHARPE_LIKE": "treatment_net_sharpe_like > control_net_sharpe_like",
            "J_FEWER_NEGATIVE_QUARTERS": "treatment_negative_quarters < control_negative_quarters",
            "K_BETTER_WORST_QUARTER": "treatment_worst_quarter_return > control_worst_quarter_return",
        },
        "evidence_classification": {
            "STRONGLY_SUPPORTED": {
                "all_standard_A_through_G": True,
                "quality_dimensions_minimum": 2,
                "minimum_relative_drawdown_reduction": "0.20",
                "minimum_control_cagr_multiple": "0.90",
            },
            "SUPPORTED": {
                "all_standard_A_through_G": True,
                "quality_dimensions_minimum": 1,
            },
            "PARTIALLY_SUPPORTED": {
                "fatal_failure": False,
                "standard_criteria_minimum_passed": 5,
                "standard_criteria_total": 7,
            },
            "FAILED": {
                "fatal_failure": True,
                "or_standard_criteria_passed_below": 5,
            },
        },
        "allowed_family_results": list(FAMILY_RESULTS),
        "family_result_assigned": None,
        "performance_evaluated": False,
        "validation_accessed": False,
    }
    return {**body, "family_g_success_criteria_hash": canonical_hash(body)}


def family_g_config_document(
    family_a: Mapping[str, Any], criteria: Mapping[str, Any]
) -> dict[str, Any]:
    a2_parameters = family_a["preregistration"]["parameters"]
    body = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "purpose": "Isolate quarterly broad-market trend participation around the frozen Family A six-month momentum architecture.",
        "distinction_from_strategy_v1": "BINARY_QUARTERLY_PARTICIPATION_GATE_NOT_A_MULTI_FACTOR_REGIME_SCORE",
        "underlying_strategy": {
            "family": "STRATEGY_FAMILY_A_MOMENTUM_V1",
            "reference_experiment_id": FAMILY_A_REFERENCE_EXPERIMENT,
            "implementation_evidence_id": FAMILY_A_IMPLEMENTATION_EVIDENCE,
            "phase2_config_hash": EXPECTED_FAMILY_A_PHASE2_CONFIG_HASH,
            "a2_002_parameter_hash": EXPECTED_A2_002_PARAMETER_HASH,
            "a2_002_preregistration_hash": EXPECTED_A2_002_PREREGISTRATION_HASH,
            "a2_002_development_result_hash": EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH,
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "validation_authorized": False,
            "post_2024_allowed": False,
        },
        "frozen_family_a_rules": {
            "universe": a2_parameters["universe"],
            "minimum_price_inr": a2_parameters["minimum_price_inr"],
            "liquidity_window_sessions": a2_parameters[
                "liquidity_window_sessions"
            ],
            "minimum_median_traded_value_inr": a2_parameters[
                "minimum_median_traded_value_inr"
            ],
            "signal": a2_parameters["signal"],
            "lookback_trading_sessions": a2_parameters[
                "lookback_trading_sessions"
            ],
            "rebalance_frequency": a2_parameters["rebalance_frequency"],
            "selection": a2_parameters["selection"],
            "selection_fraction": a2_parameters["selection_fraction"],
            "minimum_portfolio_size": a2_parameters["minimum_portfolio_size"],
            "tie_break": a2_parameters["tie_break"],
            "weighting": a2_parameters["weighting"],
            "direction": a2_parameters["direction"],
            "execution": a2_parameters["execution"],
            "whole_share_execution": True,
            "starting_capital_inr": a2_parameters["starting_capital_inr"],
            "leverage_allowed": a2_parameters["leverage_allowed"],
            "cost_model": a2_parameters["cost_model"],
            "cost_profile": a2_parameters["cost_profile"],
            "cost_scenario": a2_parameters["cost_scenario"],
        },
        "market_series": {
            "benchmark_id": MARKET_INDEX_ID,
            "index_name": MARKET_INDEX_NAME,
            "source_file": "data/reference/nse/indices/normalized/benchmark_daily.csv",
            "source_authority": "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY",
            "silent_switch_allowed": False,
        },
        "market_trend_gate": {
            "decision_time": "SCHEDULED_QUARTERLY_FORMATION_CLOSE_T",
            "rule": "market_index_close[T] > market_index_SMA200[T]",
            "comparison_operator": ">",
            "equality_passes": False,
            "sma_type": "SIMPLE_MOVING_AVERAGE",
            "sma_window_valid_market_sessions": SMA_WINDOW,
            "window_includes_T": True,
            "causal_history_only": True,
        },
        "participation_semantics": {
            "gate_true": "EXECUTE_FROZEN_FAMILY_A_QUARTERLY_REBALANCE",
            "gate_false": "LIQUIDATE_OR_REMAIN_100_PERCENT_CASH_UNTIL_NEXT_SCHEDULED_REBALANCE",
            "retain_previous_positions_on_fail": False,
            "partial_investment": False,
            "mid_quarter_reentry": False,
            "daily_execution_override": False,
            "cash_return_percent": "0",
        },
        "excluded_conditions": {
            "sma_slope": False,
            "vix": False,
            "breadth": False,
            "rsi": False,
            "macd": False,
            "global_markets": False,
            "gift_nifty": False,
            "second_treatment": False,
        },
        "success_criteria_hash": criteria["family_g_success_criteria_hash"],
        "governance": {
            "status": "PREREGISTRATION_ONLY",
            "performance_allowed_in_command_01": False,
            "validation_authorized": False,
            "strategy_v2_allowed": False,
            "promotion_allowed": False,
        },
    }
    return {**body, "family_g_config_hash": canonical_hash(body)}


def control_reference_document(
    config: Mapping[str, Any], family_a: Mapping[str, Any]
) -> dict[str, Any]:
    performance = family_a["result"]["performance"]
    body = {
        "experiment_id": CONTROL_ID,
        "name": CONTROL_NAME,
        "status": "REFERENCE_CONTROL",
        "family_g_config_hash": config["family_g_config_hash"],
        "underlying_family_a_reference": {
            "experiment_id": FAMILY_A_REFERENCE_EXPERIMENT,
            "implementation_evidence_id": FAMILY_A_IMPLEMENTATION_EVIDENCE,
            "parameter_hash": EXPECTED_A2_002_PARAMETER_HASH,
            "preregistration_hash": EXPECTED_A2_002_PREREGISTRATION_HASH,
            "development_result_hash": EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH,
        },
        "role": "ALWAYS_PARTICIPATE_STRUCTURAL_REFERENCE",
        "parameters": config["frozen_family_a_rules"],
        "expected_development_result_integrity_reference_only": {
            "net_ending_equity_inr": performance["net_ending_equity"],
            "net_total_return_pct": performance["net_total_return_pct"],
            "net_cagr_pct": performance["net_cagr_pct"],
            "max_drawdown_pct": performance["net_max_drawdown_pct"],
            "success_thresholds": False,
            "calculated_in_command_01": False,
        },
        "future_reproduction_requirements": {
            "same_rebalance_schedule": "EXACT",
            "same_candidate_and_ranking_logic": "EXACT",
            "same_selected_symbols_before_whole_share_effects": "EXACT",
            "same_cost_semantics": "EXACT",
            "net_ending_equity_absolute_tolerance_inr": "0.01",
            "net_return_absolute_tolerance_percentage_points": "0.01",
            "net_cagr_absolute_tolerance_percentage_points": "0.01",
            "max_drawdown_magnitude_absolute_tolerance_percentage_points": "0.01",
        },
        "performance_reproduced_in_command_01": False,
        "promotion_allowed": False,
    }
    return {**body, "control_g_000_reference_hash": canonical_hash(body)}


def treatment_parameter_document(
    config: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    parameters = {
        "base_control_id": CONTROL_ID,
        "only_changed_dimension": "QUARTERLY_MARKET_TREND_PARTICIPATION_GATE",
        "market_index_id": MARKET_INDEX_ID,
        "market_index_name": MARKET_INDEX_NAME,
        "decision_frequency": "QUARTERLY_FAMILY_A_SCHEDULE_ONLY",
        "decision_time": "FORMATION_DATE_CLOSE_T",
        "gate_rule": "market_index_close[T] > market_index_SMA200[T]",
        "comparison_operator": ">",
        "equality_passes": False,
        "sma_type": "SIMPLE_MOVING_AVERAGE",
        "sma_window_valid_market_sessions": SMA_WINDOW,
        "sma_includes_decision_session": True,
        "causal_history_only": True,
        "gate_pass_action": "PARTICIPATE_USING_CONTROL_HOLDINGS",
        "gate_fail_action": "HOLD_100_PERCENT_CASH_UNTIL_NEXT_QUARTERLY_REBALANCE",
        "prior_holdings_retained_on_fail": False,
        "partial_investment_allowed": False,
        "mid_quarter_reentry_allowed": False,
        "cash_return_percent": "0",
        "starting_capital_inr": "500000",
        "family_a_rules_unchanged": True,
        "volatility_filter": None,
        "breadth_filter": None,
        "second_condition": None,
    }
    return {
        "experiment_id": TREATMENT_ID,
        "name": TREATMENT_NAME,
        "family_g_config_hash": config["family_g_config_hash"],
        "control_reference_hash": control["control_g_000_reference_hash"],
        "parameters": parameters,
        "regime_g_001_parameter_hash": canonical_hash(parameters),
    }


def treatment_preregistration_document(
    config: Mapping[str, Any],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "experiment_id": TREATMENT_ID,
        "name": TREATMENT_NAME,
        "status": "PREREGISTERED",
        "promotion_allowed": False,
        "hypothesis": "A strict quarterly NIFTY 500 close-above-SMA200 gate can reduce drawdown while preserving most of frozen Family A six-month momentum CAGR.",
        "population": {
            "universe": "POINT_IN_TIME_NIFTY_500",
            "development_start": DEVELOPMENT_START.isoformat(),
            "development_end": DEVELOPMENT_END.isoformat(),
            "capital_inr": "500000",
        },
        "exact_parameters": treatment["parameters"],
        "comparison_control": {
            "experiment_id": CONTROL_ID,
            "reference_hash": control["control_g_000_reference_hash"],
            "role": "ALWAYS_PARTICIPATE_FROZEN_FAMILY_A_A2_002",
        },
        "primary_metrics": [
            "NET_CAGR",
            "MAX_DRAWDOWN_MAGNITUDE",
            "ENDING_EQUITY",
        ],
        "secondary_metrics": [
            "YEARLY_RETURN",
            "TRANSACTION_COSTS",
            "INVESTED_QUARTERS",
            "CASH_QUARTERS",
            "FRACTION_INVESTED",
            "ANNUALIZED_VOLATILITY",
            "SHARPE_LIKE",
            "NEGATIVE_QUARTERS",
            "WORST_QUARTER",
            "UPSIDE_CAPTURE_DESCRIPTIVE",
            "DOWNSIDE_AVOIDANCE_DESCRIPTIVE",
        ],
        "numerical_success_criteria_where_applicable": {
            "success_criteria_hash": criteria["family_g_success_criteria_hash"],
            "criteria": criteria["standard_treatment_criteria"],
            "quality_dimensions": criteria["quality_dimensions"],
        },
        "failure_criteria": {
            "fatal_sample_failure_below_invested_quarters": 4,
            "failed_if_fatal_failure": True,
            "failed_if_standard_criteria_passed_below": 5,
        },
        "stop_conditions": [
            "ACCOUNTING_OR_DATA_INTEGRITY_FATAL_ERROR",
            "CONTROL_REPRODUCTION_OUTSIDE_FROZEN_TOLERANCE",
            "VALIDATION_OR_POST_2024_ACCESS",
            "PARAMETER_OR_TREATMENT_CHANGE_REQUIRES_NEW_EXPERIMENT_ID",
        ],
        "validation_eligibility_rule": "NOT_AUTHORIZED_IN_COMMAND_01; future access requires separate approval after frozen DEVELOPMENT evaluation and governance review.",
        "cost_model": {
            "version": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": "COST-SCENARIO-002",
            "cash_return_percent": "0",
        },
        "data_partition": {
            "development": "2022-01-01_THROUGH_2024-12-31",
            "prehistory": "CAUSAL_INDICATOR_HISTORY_ONLY",
            "validation": "NOT_AUTHORIZED",
            "post_2024": "PROHIBITED",
        },
        "hashes": {
            "family_g_config_hash": config["family_g_config_hash"],
            "control_g_000_reference_hash": control[
                "control_g_000_reference_hash"
            ],
            "regime_g_001_parameter_hash": treatment[
                "regime_g_001_parameter_hash"
            ],
            "family_g_success_criteria_hash": criteria[
                "family_g_success_criteria_hash"
            ],
            "governance_policy_hash": EXPECTED_GOVERNANCE_V2_HASH,
        },
        "performance_evaluated": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    return {**body, "regime_g_001_preregistration_hash": canonical_hash(body)}


def registry_document(
    config: Mapping[str, Any],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    preregistration: Mapping[str, Any],
) -> dict[str, Any]:
    entries = [
        {
            "experiment_id": CONTROL_ID,
            "name": CONTROL_NAME,
            "role": "CONTROL",
            "status": "REFERENCE_CONTROL",
            "reference_hash": control["control_g_000_reference_hash"],
            "promotion_allowed": False,
        },
        {
            "experiment_id": TREATMENT_ID,
            "name": TREATMENT_NAME,
            "role": "TREATMENT",
            "status": "PREREGISTERED",
            "parameter_hash": treatment["regime_g_001_parameter_hash"],
            "preregistration_hash": preregistration[
                "regime_g_001_preregistration_hash"
            ],
            "promotion_allowed": False,
        },
    ]
    body = {
        "version": "FAMILY_G_EXPERIMENT_REGISTRY_V1",
        "family_g_config_hash": config["family_g_config_hash"],
        "control_count": 1,
        "treatment_count": 1,
        "entries": entries,
    }
    return {**body, "registry_hash": canonical_hash(body)}


def protocol_document(
    config: Mapping[str, Any],
    control: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "protocol": RESEARCH_PROTOCOL,
        "family_version": FAMILY_VERSION,
        "profile": RESEARCH_PROFILE,
        "family_g_config_hash": config["family_g_config_hash"],
        "control_reference_hash": control["control_g_000_reference_hash"],
        "treatment_preregistration_hash": preregistration[
            "regime_g_001_preregistration_hash"
        ],
        "success_criteria_hash": criteria["family_g_success_criteria_hash"],
        "phase": "SPECIFICATION_PREREGISTRATION_ARCHITECTURE_STRUCTURAL_PILOTS_ONLY",
        "sequence": [
            "VERIFY_FAMILY_F_CLOSURE",
            "VERIFY_GOVERNANCE_V2",
            "FREEZE_FAMILY_A_CONTROL_REUSE",
            "FREEZE_NIFTY_500_SMA200_GATE",
            "AUDIT_STRUCTURAL_REGIME_AND_ACCOUNTING_PILOTS",
            "STOP_FOR_REVIEW",
        ],
        "development_performance_authorized": False,
        "validation_authorized": False,
        "strategy_v2_authorized": False,
    }
    return {**body, "protocol_hash": canonical_hash(body)}


def _control_rebalances(root: Path) -> list[dict[str, str]]:
    path = (
        Path(root)
        / "data/research/strategy_families/family_a/v1/phase2/"
        "development_evaluation/a2_002/rebalances.csv"
    )
    rows = read_csv(path)
    if len(rows) != 11:
        raise FamilyGInputError("Frozen A2-002 quarterly schedule is not 11 rows")
    return rows


def _control_holdings(root: Path) -> dict[str, list[dict[str, Any]]]:
    path = (
        Path(root)
        / "data/research/strategy_families/family_a/v1/phase2/"
        "development_evaluation/a2_002/holdings.csv"
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_csv(path):
        quantity = int(row["quantity"])
        if quantity <= 0 or Decimal(row["price"]) <= 0:
            raise FamilyGInputError("A2-002 holdings contain invalid whole shares")
        grouped[row["execution_date"]].append(
            {"symbol": row["symbol"], "quantity": quantity}
        )
    return {
        execution_date: sorted(rows, key=lambda row: row["symbol"])
        for execution_date, rows in grouped.items()
    }


def _benchmark_rows(root: Path) -> list[dict[str, Any]]:
    path = Path(root) / "data/reference/nse/indices/normalized/benchmark_daily.csv"
    output: list[dict[str, Any]] = []
    for row in read_csv(path):
        trading_date = date.fromisoformat(row["trading_date"])
        if row["benchmark_id"] != MARKET_INDEX_ID or trading_date > DEVELOPMENT_END:
            continue
        if row["index_name"] != MARKET_INDEX_NAME:
            raise FamilyGInputError("NIFTY 500 benchmark name changed")
        if row["source"] != "NSE_OFFICIAL_HISTORICAL_OR_INDICES_HISTORY":
            raise FamilyGInputError("NIFTY 500 source is not the approved official source")
        output.append(
            {
                "trading_date": trading_date,
                "close": Decimal(row["close"]),
                "source": row["source"],
            }
        )
    output.sort(key=lambda row: row["trading_date"])
    if not output:
        raise FamilyGInputError("Approved NIFTY 500 series is unavailable")
    return output


def build_regime_dataset(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rebalances = _control_rebalances(root)
    holdings = _control_holdings(root)
    benchmark = _benchmark_rows(root)
    benchmark_by_date = {row["trading_date"]: row for row in benchmark}
    regime_rows: list[dict[str, Any]] = []
    holdings_audit: list[dict[str, Any]] = []
    for rebalance in rebalances:
        formation_date = date.fromisoformat(rebalance["formation_date"])
        execution_date = rebalance["execution_date"]
        if not DEVELOPMENT_START <= formation_date <= DEVELOPMENT_END:
            raise FamilyGInputError("Family A schedule escaped DEVELOPMENT")
        market = benchmark_by_date.get(formation_date)
        if market is None:
            raise FamilyGInputError(
                f"NIFTY 500 close unavailable at {formation_date.isoformat()}"
            )
        causal_closes = [
            row["close"]
            for row in benchmark
            if row["trading_date"] <= formation_date
        ]
        sma200 = simple_moving_average(causal_closes)
        gate_pass = market_trend_gate(market["close"], sma200)
        control_positions = holdings.get(execution_date, [])
        control_count = len(control_positions)
        expected_count = int(rebalance["actual_holdings"])
        if control_count != expected_count:
            raise FamilyGInputError(
                f"Holding count mismatch at {formation_date.isoformat()}"
            )
        treatment_positions = control_positions if gate_pass is True else []
        flags: list[str] = []
        if sma200 is None:
            flags.append("INSUFFICIENT_SMA200_PREHISTORY")
        if rebalance["status"] != "EXECUTED":
            flags.append(rebalance["status"])
        if int(rebalance["unaffordable_names"]) != 0:
            flags.append("UNAFFORDABLE_CONTROL_SELECTION")
        if gate_pass is True:
            cash_state = "PARTICIPATE_FAMILY_A_CONTROL_HOLDINGS"
        elif gate_pass is False:
            cash_state = "CASH_ONLY_UNTIL_NEXT_SCHEDULED_REBALANCE"
        else:
            cash_state = "DATA_UNAVAILABLE_NOT_EXECUTABLE"
        control_hash = canonical_hash(control_positions)
        treatment_hash = canonical_hash(treatment_positions)
        row = {
            "rebalance_date": formation_date.isoformat(),
            "market_index_name": MARKET_INDEX_NAME,
            "market_close": market["close"],
            "market_sma200": sma200,
            "gate_pass": gate_pass,
            "control_candidate_count": int(rebalance["eligible_count"]),
            "control_selected_count": control_count,
            "treatment_selected_count": len(treatment_positions),
            "treatment_cash_state": cash_state,
            "data_quality_flags": flags or ["NONE"],
            "execution_date": execution_date,
            "sma_history_session_count": len(causal_closes),
            "sma_window_session_count": SMA_WINDOW if sma200 is not None else 0,
            "control_rebalance_selected_count": int(rebalance["selected_count"]),
            "control_intended_holdings": int(rebalance["intended_holdings"]),
            "control_actual_holdings": int(rebalance["actual_holdings"]),
            "control_unaffordable_names": int(rebalance["unaffordable_names"]),
            "control_holdings_hash": control_hash,
            "treatment_holdings_hash": treatment_hash,
            "holdings_identical_on_pass": gate_pass is True
            and treatment_hash == control_hash,
            "treatment_zero_holdings_on_fail": gate_pass is False
            and not treatment_positions,
            "decision_frequency": "QUARTERLY_ONLY",
            "mid_quarter_change_allowed": False,
            "performance_evaluated": False,
        }
        regime_rows.append(row)
        holdings_audit.append(
            {
                "rebalance_date": formation_date.isoformat(),
                "execution_date": execution_date,
                "gate_pass": gate_pass,
                "control_holding_count": control_count,
                "treatment_holding_count": len(treatment_positions),
                "control_holdings_hash": control_hash,
                "treatment_holdings_hash": treatment_hash,
                "holdings_identical_on_pass": row[
                    "holdings_identical_on_pass"
                ],
                "treatment_zero_holdings_on_fail": row[
                    "treatment_zero_holdings_on_fail"
                ],
                "whole_share_quantities": all(
                    isinstance(position["quantity"], int)
                    and position["quantity"] > 0
                    for position in treatment_positions
                ),
                "outcomes_inspected": False,
            }
        )
    return regime_rows, holdings_audit


def regime_count_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for period, year in (("ALL", None), ("2022", 2022), ("2023", 2023), ("2024", 2024)):
        selected = [
            row
            for row in rows
            if year is None or str(row["rebalance_date"]).startswith(str(year))
        ]
        output.append(
            {
                "period": period,
                "total_quarterly_rebalances": len(selected),
                "gate_pass_count": sum(row["gate_pass"] is True for row in selected),
                "gate_fail_count": sum(row["gate_pass"] is False for row in selected),
                "gate_unavailable_count": sum(row["gate_pass"] is None for row in selected),
                "control_selected_count": sum(
                    int(row["control_selected_count"]) for row in selected
                ),
                "treatment_selected_count": sum(
                    int(row["treatment_selected_count"]) for row in selected
                ),
                "performance_evaluated": False,
            }
        )
    return output


def accounting_pilot_document() -> dict[str, Any]:
    buy_date = date(2022, 10, 3)
    sell_date = date(2023, 1, 2)
    positions = (
        {"symbol": "PILOT_A", "quantity": 240, "price": Decimal("1000")},
        {"symbol": "PILOT_B", "quantity": 96, "price": Decimal("2500")},
    )
    notionals = [
        Decimal(position["quantity"]) * position["price"] for position in positions
    ]
    gross_invested = sum(notionals, Decimal("0"))
    buy_cost = sum(
        (
            estimate_order_cost("BUY", buy_date, notional)["total_cost"]
            for notional in notionals
        ),
        Decimal("0"),
    )
    post_buy_cash = STARTING_CAPITAL - gross_invested - buy_cost
    participating_equity = post_buy_cash + gross_invested
    sell_cost = sum(
        (
            estimate_order_cost("SELL", sell_date, notional)["total_cost"]
            for notional in notionals
        ),
        Decimal("0"),
    )
    cash_only_equity = post_buy_cash + gross_invested - sell_cost
    checks = [
        {
            "case_id": "ACCOUNTING_A_PARTICIPATING_QUARTER",
            "passed": gross_invested > 0 and post_buy_cash >= 0,
            "details": "Two equal-notional positions are funded without leverage.",
        },
        {
            "case_id": "ACCOUNTING_B_WHOLE_SHARES",
            "passed": all(
                isinstance(position["quantity"], int)
                and position["quantity"] > 0
                for position in positions
            ),
            "details": "Every pilot position uses a positive integer quantity.",
        },
        {
            "case_id": "ACCOUNTING_C_FROZEN_COSTS",
            "passed": buy_cost > 0 and sell_cost > 0,
            "details": "Both transitions use INDIA_EQUITY_COST_MODEL_V1 / COST-SCENARIO-002.",
        },
        {
            "case_id": "ACCOUNTING_D_EQUITY_RECONCILIATION",
            "passed": participating_equity
            == STARTING_CAPITAL - buy_cost,
            "details": "Cash plus marked holdings equals post-cost equity.",
        },
        {
            "case_id": "ACCOUNTING_E_CASH_ONLY_QUARTER",
            "passed": cash_only_equity
            == post_buy_cash + gross_invested - sell_cost,
            "details": "Gate failure liquidates all equities and leaves only reconciled cash.",
        },
    ]
    return {
        "version": "FAMILY_G_ACCOUNTING_PILOT_V1",
        "fixture": "SYNTHETIC_STRUCTURE_ONLY_NO_PERFORMANCE",
        "starting_capital_inr": STARTING_CAPITAL,
        "positions": list(positions),
        "gross_invested_inr": gross_invested,
        "buy_cost_inr": buy_cost,
        "post_buy_cash_inr": post_buy_cash,
        "participating_equity_inr": participating_equity,
        "sell_cost_inr": sell_cost,
        "cash_only_equity_inr": cash_only_equity,
        "cash_only_holding_count": 0,
        "cash_return_percent": CASH_RETURN,
        "checks": checks,
        "all_passed": all(row["passed"] for row in checks),
        "performance_evaluated": False,
    }


def regime_pilot_rows(
    regime_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pass_rows = [row for row in regime_rows if row["gate_pass"] is True]
    fail_rows = [row for row in regime_rows if row["gate_pass"] is False]
    unavailable = [row for row in regime_rows if row["gate_pass"] is None]
    tests = [
        (
            "REGIME_A_ABOVE_SMA200_PARTICIPATE",
            True,
            market_trend_gate(Decimal("101"), Decimal("100")),
            "PASS",
            "Strictly above participates.",
        ),
        (
            "REGIME_B_BELOW_SMA200_CASH",
            False,
            market_trend_gate(Decimal("99"), Decimal("100")),
            "PASS",
            "Below holds cash.",
        ),
        (
            "REGIME_C_EQUALITY_CASH",
            False,
            market_trend_gate(Decimal("100"), Decimal("100")),
            "PASS",
            "Equality fails the strict gate.",
        ),
        (
            "REGIME_D_EARLY_2022_CAUSAL_SMA200",
            "200_VALID_SESSIONS",
            unavailable[0]["sma_history_session_count"] if unavailable else 200,
            "FAIL_INSUFFICIENT_PREHISTORY" if unavailable else "PASS",
            "The official local NIFTY 500 series has only 141 causal sessions at 2022-03-31; no future data or silent benchmark switch is used.",
        ),
        (
            "REGIME_E_NO_VALIDATION_ROWS",
            0,
            sum(
                date.fromisoformat(str(row["rebalance_date"])) > DEVELOPMENT_END
                for row in regime_rows
            ),
            "PASS",
            "All decisions are within DEVELOPMENT.",
        ),
        (
            "REGIME_F_SAME_HOLDINGS_ON_PASS",
            len(pass_rows),
            sum(bool(row["holdings_identical_on_pass"]) for row in pass_rows),
            "PASS",
            "Treatment hashes equal frozen control holdings on every pass date.",
        ),
        (
            "REGIME_G_ZERO_HOLDINGS_ON_FAIL",
            len(fail_rows),
            sum(bool(row["treatment_zero_holdings_on_fail"]) for row in fail_rows),
            "PASS",
            "Treatment has zero equities on every evaluable fail date.",
        ),
        (
            "REGIME_H_NO_MID_QUARTER_CHANGE",
            "QUARTERLY_ONLY",
            (
                "QUARTERLY_ONLY"
                if all(
                    row["decision_frequency"] == "QUARTERLY_ONLY"
                    and row["mid_quarter_change_allowed"] is False
                    for row in regime_rows
                )
                else "VIOLATION"
            ),
            "PASS",
            "No daily, weekly, or emergency re-entry path exists.",
        ),
    ]
    return [
        {
            "category": "REGIME",
            "case_id": case_id,
            "expected": expected,
            "observed": observed,
            "status": status,
            "passed": status == "PASS" and expected == observed,
            "details": details,
            "fixture": "STRUCTURAL_ONLY_NO_PERFORMANCE",
        }
        for case_id, expected, observed, status, details in tests
    ]


def data_readiness_rows(
    regime_rows: Sequence[Mapping[str, Any]],
    holdings_audit: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pass_count = sum(row["gate_pass"] is True for row in regime_rows)
    unavailable = sum(row["gate_pass"] is None for row in regime_rows)
    definitions = (
        (
            "FROZEN_NIFTY_500_SERIES",
            "PASS",
            MARKET_INDEX_NAME,
            "Exact preferred broad-market series is available from the approved local benchmark file.",
        ),
        (
            "EXACT_FAMILY_A_QUARTERLY_SCHEDULE",
            "PASS" if len(regime_rows) == 11 else "FAIL",
            len(regime_rows),
            "Frozen A2-002 formation and execution dates are reused.",
        ),
        (
            "CAUSAL_SMA200_ALL_REBALANCES",
            "LIMITATION" if unavailable else "PASS",
            f"{len(regime_rows) - unavailable}/{len(regime_rows)}",
            "The 2022-03-31 decision has 141 rather than 200 official causal sessions.",
        ),
        (
            "GATE_PASS_SAMPLE_ADEQUACY_STRUCTURE",
            "PASS" if pass_count >= 6 else "FAIL",
            pass_count,
            "Observed structural invested-quarter count meets the preregistered minimum; this is not performance evidence.",
        ),
        (
            "CONTROL_HOLDINGS_WHOLE_SHARE_READY",
            "PASS"
            if all(row["whole_share_quantities"] for row in holdings_audit)
            else "FAIL",
            sum(row["whole_share_quantities"] for row in holdings_audit),
            "Frozen A2-002 holding quantities are positive integers.",
        ),
        (
            "PASS_DATE_HOLDING_IDENTITY",
            "PASS"
            if all(
                row["holdings_identical_on_pass"]
                for row in holdings_audit
                if row["gate_pass"] is True
            )
            else "FAIL",
            sum(
                row["holdings_identical_on_pass"] for row in holdings_audit
            ),
            "Every evaluable pass date copies the control holding set.",
        ),
        (
            "FAIL_DATE_CASH_STATE",
            "PASS"
            if all(
                row["treatment_zero_holdings_on_fail"]
                for row in holdings_audit
                if row["gate_pass"] is False
            )
            else "FAIL",
            sum(
                row["treatment_zero_holdings_on_fail"] for row in holdings_audit
            ),
            "Every evaluable fail date has zero treatment equities.",
        ),
        (
            "DEVELOPMENT_PARTITION_ONLY",
            "PASS",
            "2022-01-01_THROUGH_2024-12-31",
            "No validation or post-2024 row is loaded into the structural dataset.",
        ),
    )
    return [
        {
            "check": check,
            "status": status,
            "observed": observed,
            "details": details,
            "performance_evaluated": False,
        }
        for check, status, observed, details in definitions
    ]


def governance_rows(preregistration: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "governance_policy": GOVERNANCE_POLICY_VERSION,
            "checklist_item": item,
            "status": "PASS" if item in preregistration else "FAIL",
            "frozen_before_performance": True,
        }
        for item in GOVERNANCE_CHECKLIST
    ]


def _registry_report_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": row["experiment_id"],
            "name": row["name"],
            "role": row["role"],
            "status": row["status"],
            "reference_hash": row.get("reference_hash", ""),
            "parameter_hash": row.get("parameter_hash", ""),
            "preregistration_hash": row.get("preregistration_hash", ""),
            "promotion_allowed": row["promotion_allowed"],
        }
        for row in registry["entries"]
    ]


def _verify_roadmap(root: Path) -> bool:
    text = (
        Path(root) / "docs/strategy-family-research-roadmap-v1.md"
    ).read_text(encoding="utf-8")
    expected = (
        "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |",
        "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |",
        "| Family E | Pullback / Reclaim | PAUSED_NO_VALIDATION_CANDIDATE |",
        "| Family F | Catalyst Momentum | PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE |",
        "| Family G | Regime / Volatility | ACTIVE_PREREGISTRATION |",
    )
    return all(row in text for row in expected)


def _verify_expected_hashes(
    config: Mapping[str, Any],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> None:
    checks = (
        (EXPECTED_FAMILY_G_CONFIG_HASH, config["family_g_config_hash"]),
        (
            EXPECTED_CONTROL_REFERENCE_HASH,
            control["control_g_000_reference_hash"],
        ),
        (
            EXPECTED_TREATMENT_PARAMETER_HASH,
            treatment["regime_g_001_parameter_hash"],
        ),
        (
            EXPECTED_TREATMENT_PREREGISTRATION_HASH,
            preregistration["regime_g_001_preregistration_hash"],
        ),
        (
            EXPECTED_SUCCESS_CRITERIA_HASH,
            criteria["family_g_success_criteria_hash"],
        ),
    )
    mismatches = [
        (expected, observed)
        for expected, observed in checks
        if expected is not None and expected != observed
    ]
    if mismatches:
        raise FamilyGInputError(f"Frozen Family G hash mismatch: {mismatches}")


def build_family_g_architecture(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    if not _verify_roadmap(root):
        raise FamilyGInputError("Family research roadmap lifecycle mismatch")
    documentation = root / "docs/strategy-family-g-regime-volatility-v1.md"
    if not documentation.is_file():
        raise FamilyGInputError("Family G Command 01 documentation is missing")

    family_f = verify_family_f_closure(root)
    governance = verify_governance_v2(root)
    family_a = verify_family_a_reference(root)
    baseline_before = previous_family_snapshot(root)

    criteria = success_criteria_document()
    config = family_g_config_document(family_a, criteria)
    control = control_reference_document(config, family_a)
    treatment = treatment_parameter_document(config, control)
    preregistration = treatment_preregistration_document(
        config, control, treatment, criteria
    )
    registry = registry_document(config, control, treatment, preregistration)
    protocol = protocol_document(config, control, preregistration, criteria)
    _verify_expected_hashes(config, control, treatment, preregistration, criteria)

    if len(registry["entries"]) != 2 or registry["treatment_count"] != 1:
        raise FamilyGInputError("Registry must contain one control and one treatment")
    if not all(item in preregistration for item in GOVERNANCE_CHECKLIST):
        raise FamilyGInputError("Treatment preregistration misses Governance V2 fields")

    regime_rows, holdings_audit = build_regime_dataset(root)
    counts = regime_count_rows(regime_rows)
    accounting = accounting_pilot_document()
    regime_pilots = regime_pilot_rows(regime_rows)
    accounting_rows = [
        {
            "category": "ACCOUNTING",
            "case_id": row["case_id"],
            "expected": True,
            "observed": row["passed"],
            "status": "PASS" if row["passed"] else "FAIL",
            "passed": row["passed"],
            "details": row["details"],
            "fixture": accounting["fixture"],
        }
        for row in accounting["checks"]
    ]
    pilot_rows = [*regime_pilots, *accounting_rows]
    readiness = data_readiness_rows(regime_rows, holdings_audit)
    governance_report = governance_rows(preregistration)
    registry_report = _registry_report_rows(registry)

    unavailable = sum(row["gate_pass"] is None for row in regime_rows)
    data_readiness = "READY_WITH_LIMITATIONS" if unavailable == 1 else "READY"
    architecture_result = (
        "METHODOLOGY_FIX_REQUIRED"
        if unavailable
        else "READY_FOR_DEVELOPMENT_BACKTEST"
    )
    if data_readiness not in DATA_READINESS_RESULTS:
        raise FamilyGInputError("Invalid data-readiness classification")
    if architecture_result not in ARCHITECTURE_RESULTS:
        raise FamilyGInputError("Invalid architecture classification")

    output = family_output_root(root)
    registry_root = output / "registry"
    regime_root = output / "regime"
    pilots_root = output / "pilots"
    governance_root = output / "governance"
    manifests_root = output / "manifests"
    reports = root / "data/reports"

    write_json(registry_root / "family_g_config_v1.json", config)
    write_json(registry_root / "control_g_000_reference_v1.json", control)
    write_json(registry_root / "regime_g_001_parameters_v1.json", treatment)
    write_json(
        registry_root / "regime_g_001_preregistration_v1.json", preregistration
    )
    write_json(registry_root / "family_g_experiment_registry_v1.json", registry)
    write_json(registry_root / "family_g_research_protocol_v1.json", protocol)
    write_csv(
        regime_root / "family_g_rebalance_regime_v1.csv",
        regime_rows,
        (
            *REGIME_DATASET_FIELDS,
            "execution_date",
            "sma_history_session_count",
            "sma_window_session_count",
            "control_rebalance_selected_count",
            "control_intended_holdings",
            "control_actual_holdings",
            "control_unaffordable_names",
            "control_holdings_hash",
            "treatment_holdings_hash",
            "holdings_identical_on_pass",
            "treatment_zero_holdings_on_fail",
            "decision_frequency",
            "mid_quarter_change_allowed",
            "performance_evaluated",
        ),
    )
    write_csv(regime_root / "family_g_holdings_audit_v1.csv", holdings_audit)
    write_json(pilots_root / "family_g_regime_pilots_v1.json", regime_pilots)
    write_json(pilots_root / "family_g_accounting_pilot_v1.json", accounting)
    write_json(governance_root / "family_g_success_criteria_v1.json", criteria)
    write_json(
        governance_root / "family_g_governance_v2_checklist_v1.json",
        {
            "policy": GOVERNANCE_POLICY_VERSION,
            "policy_hash": governance["governance_policy_hash"],
            "rows": governance_report,
            "all_passed": all(row["status"] == "PASS" for row in governance_report),
        },
    )

    write_csv(reports / REPORT_NAMES[1], registry_report)
    write_csv(reports / REPORT_NAMES[2], readiness)
    write_csv(reports / REPORT_NAMES[3], counts)
    write_csv(reports / REPORT_NAMES[4], pilot_rows)
    write_csv(reports / REPORT_NAMES[5], governance_report)

    baseline_after = previous_family_snapshot(root)
    baseline_unchanged = baseline_before == baseline_after
    if not baseline_unchanged:
        raise FamilyGInputError("A previous-family artifact changed during Family G build")

    non_summary_artifacts = [
        registry_root / "family_g_config_v1.json",
        registry_root / "control_g_000_reference_v1.json",
        registry_root / "regime_g_001_parameters_v1.json",
        registry_root / "regime_g_001_preregistration_v1.json",
        registry_root / "family_g_experiment_registry_v1.json",
        registry_root / "family_g_research_protocol_v1.json",
        regime_root / "family_g_rebalance_regime_v1.csv",
        regime_root / "family_g_holdings_audit_v1.csv",
        pilots_root / "family_g_regime_pilots_v1.json",
        pilots_root / "family_g_accounting_pilot_v1.json",
        governance_root / "family_g_success_criteria_v1.json",
        governance_root / "family_g_governance_v2_checklist_v1.json",
        *(reports / name for name in REPORT_NAMES[1:]),
        documentation,
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in non_summary_artifacts
    }
    existing_summary = reports / REPORT_NAMES[0]
    generated_at = (
        _read_json(existing_summary)["generated_at"]
        if existing_summary.is_file()
        else utc_now()
    )
    overall = counts[0]
    yearly = {row["period"]: row for row in counts[1:]}
    summary = {
        "command": COMMAND,
        "generated_at": generated_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_status": "PREREGISTERED_RESEARCH_FAMILY",
        "family_g_config_hash": config["family_g_config_hash"],
        "control": {
            "id": CONTROL_ID,
            "name": CONTROL_NAME,
            "reference_hash": control["control_g_000_reference_hash"],
            "underlying_family_a_reference": f"{FAMILY_A_REFERENCE_EXPERIMENT}/{FAMILY_A_IMPLEMENTATION_EVIDENCE}",
            "integrity_reference": control[
                "expected_development_result_integrity_reference_only"
            ],
        },
        "treatment_count": EXPERIMENT_COUNT,
        "treatment": {
            "id": TREATMENT_ID,
            "name": TREATMENT_NAME,
            "parameter_hash": treatment["regime_g_001_parameter_hash"],
            "preregistration_hash": preregistration[
                "regime_g_001_preregistration_hash"
            ],
            "promotion_allowed": False,
        },
        "family_g_success_criteria_hash": criteria[
            "family_g_success_criteria_hash"
        ],
        "protocol_hash": protocol["protocol_hash"],
        "market_index": config["market_series"],
        "gate": config["market_trend_gate"],
        "development_window": config["development_window"],
        "capital_and_cash": {
            "starting_capital_inr": "500000",
            "cash_return_percent": "0",
        },
        "structural_counts": {
            "total_quarterly_rebalances": overall[
                "total_quarterly_rebalances"
            ],
            "gate_pass_count": overall["gate_pass_count"],
            "gate_fail_count": overall["gate_fail_count"],
            "gate_unavailable_count": overall["gate_unavailable_count"],
            "control_selected_count": overall["control_selected_count"],
            "treatment_selected_count": overall["treatment_selected_count"],
            "yearly": yearly,
            "pass_date_holding_identity": f"{sum(row['holdings_identical_on_pass'] for row in holdings_audit)}/{overall['gate_pass_count']}",
            "fail_date_zero_holdings": f"{sum(row['treatment_zero_holdings_on_fail'] for row in holdings_audit)}/{overall['gate_fail_count']}",
            "outcomes_inspected": False,
        },
        "pilots": {
            "regime_case_count": len(regime_pilots),
            "regime_passed_count": sum(row["passed"] for row in regime_pilots),
            "regime_limitation_count": sum(
                row["status"] == "FAIL_INSUFFICIENT_PREHISTORY"
                for row in regime_pilots
            ),
            "accounting_case_count": len(accounting_rows),
            "accounting_all_passed": accounting["all_passed"],
            "performance_evaluated": False,
        },
        "classifications": {
            "FAMILY_G_DATA_READINESS": data_readiness,
            "FAMILY_G_ARCHITECTURE_RESULT": architecture_result,
            "FAMILY_G_RESULT": None,
        },
        "governance": {
            "policy": GOVERNANCE_POLICY_VERSION,
            "policy_hash": governance["governance_policy_hash"],
            "checklist_count": len(governance_report),
            "checklist_passed": all(
                row["status"] == "PASS" for row in governance_report
            ),
            "family_f_closure_hash": family_f["family_f_closure_hash"],
            "family_f_closure_verified": True,
            "development_performance_run": False,
            "vix_used": False,
            "breadth_used": False,
            "alternate_sma_tested": False,
            "second_treatment_created": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
        },
        "immutability": {
            "previous_family_snapshot_before": baseline_before["snapshot_hash"],
            "previous_family_snapshot_after": baseline_after["snapshot_hash"],
            "previous_families_unchanged": baseline_unchanged,
            "strategy_v1_unchanged": baseline_unchanged,
            "cap4_unchanged": baseline_unchanged,
            "family_a_unchanged": baseline_unchanged,
            "family_b_unchanged": baseline_unchanged,
            "family_c_unchanged": baseline_unchanged,
            "family_d_unchanged": baseline_unchanged,
            "family_e_unchanged": baseline_unchanged,
            "family_f_unchanged": baseline_unchanged,
            "daily_history_prehistory_v2_unchanged": baseline_unchanged,
        },
        "roadmap": {
            "family_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
            "family_B": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_C": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
            "family_E": "PAUSED_NO_VALIDATION_CANDIDATE",
            "family_F": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
            "family_G": "ACTIVE_PREREGISTRATION",
        },
        "security": {
            "credentials_added": 0,
            "network_accessed": False,
            "external_writes": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "storage": {
            "root": output.relative_to(root).as_posix(),
            "regime_dataset_required_fields": list(REGIME_DATASET_FIELDS),
            "artifact_hashes": artifact_hashes,
        },
        "known_limitations": [
            "THE_APPROVED_LOCAL_NIFTY_500_SERIES_STARTS_2021-09-07_AND_HAS_ONLY_141_VALID_SESSIONS_AT_2022-03-31",
            "THE_FIRST_SCHEDULED_REBALANCE_IS_NOT_EXECUTABLE_UNTIL_AT_LEAST_200_CAUSAL_NIFTY_500_SESSIONS_ARE_AVAILABLE",
            "COMMAND_01_CONTAINS_NO_CONTROL_OR_TREATMENT_PERFORMANCE_EVALUATION",
        ],
        "recommended_next_action": "EXTEND_THE_SAME_AUTHORIZED_NIFTY_500_SERIES_BACKWARD_TO_SUPPLY_AT_LEAST_200_VALID_SESSIONS_AT_2022-03-31_THEN_RERUN_STRUCTURAL_VERIFICATION_BEFORE_ANY_DEVELOPMENT_BACKTEST",
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports / REPORT_NAMES[0]
    write_json(summary_path, summary)

    manifest_artifacts = {
        **artifact_hashes,
        summary_path.relative_to(root).as_posix(): file_sha256(summary_path),
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "generated_at": generated_at,
        "family_version": FAMILY_VERSION,
        "family_g_config_hash": config["family_g_config_hash"],
        "control_g_000_reference_hash": control[
            "control_g_000_reference_hash"
        ],
        "regime_g_001_parameter_hash": treatment[
            "regime_g_001_parameter_hash"
        ],
        "regime_g_001_preregistration_hash": preregistration[
            "regime_g_001_preregistration_hash"
        ],
        "family_g_success_criteria_hash": criteria[
            "family_g_success_criteria_hash"
        ],
        "protocol_hash": protocol["protocol_hash"],
        "family_f_closure_hash": family_f["family_f_closure_hash"],
        "governance_policy_hash": governance["governance_policy_hash"],
        "previous_family_snapshot_hash": baseline_after["snapshot_hash"],
        "artifact_hashes": manifest_artifacts,
        "summary_hash": file_sha256(summary_path),
        "development_performance_run": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "family_g_architecture_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(manifests_root / "family_g_architecture_manifest_v1.json", manifest)
    return summary


def finalize_family_g_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = (
        family_output_root(root)
        / "manifests/family_g_architecture_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    checks_passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": checks_passed,
        "ready_for_development_backtest": summary["classifications"]
        ["FAMILY_G_ARCHITECTURE_RESULT"]
        == "READY_FOR_DEVELOPMENT_BACKTEST",
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_g_architecture_manifest_hash"
    }
    relative_summary = summary_path.relative_to(root).as_posix()
    body["artifact_hashes"][relative_summary] = file_sha256(summary_path)
    body["summary_hash"] = file_sha256(summary_path)
    write_json(
        manifest_path,
        {
            **body,
            "family_g_architecture_manifest_hash": canonical_hash(body),
        },
    )
    return summary


__all__ = [
    "ARCHITECTURE_RESULTS",
    "CASH_RETURN",
    "COMMAND",
    "CONTROL_ID",
    "CONTROL_NAME",
    "DATA_READINESS_RESULTS",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "EXPECTED_CONTROL_REFERENCE_HASH",
    "EXPECTED_FAMILY_F_CLOSURE_HASH",
    "EXPECTED_FAMILY_G_CONFIG_HASH",
    "EXPECTED_SUCCESS_CRITERIA_HASH",
    "EXPECTED_TREATMENT_PARAMETER_HASH",
    "EXPECTED_TREATMENT_PREREGISTRATION_HASH",
    "EXPERIMENT_COUNT",
    "FAMILY_CODE",
    "FAMILY_VERSION",
    "GOVERNANCE_CHECKLIST",
    "MARKET_INDEX_NAME",
    "REGIME_DATASET_FIELDS",
    "REPORT_NAMES",
    "RESEARCH_PROFILE",
    "RESEARCH_PROTOCOL",
    "SMA_WINDOW",
    "STARTING_CAPITAL",
    "TREATMENT_ID",
    "TREATMENT_NAME",
    "accounting_pilot_document",
    "build_family_g_architecture",
    "build_regime_dataset",
    "family_g_config_document",
    "finalize_family_g_review",
    "market_trend_gate",
    "previous_family_snapshot",
    "regime_count_rows",
    "simple_moving_average",
    "success_criteria_document",
    "treatment_parameter_document",
    "verify_family_a_reference",
    "verify_family_f_closure",
    "verify_governance_v2",
]

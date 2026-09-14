from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_c_breakout_continuation import (
    BREAKOUT_WINDOW,
    COMPRESSION_THRESHOLD,
    COMPRESSION_WINDOW,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
)
from app.research.strategy.family_c_c001_implementation_research import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPERIMENT_ID,
    EXPERIMENT_NAME,
    EXPECTED_ATTRIBUTION_HASH,
    GOVERNANCE_ITEMS,
    ORIGINAL_RANKING,
    REFERENCE_EXPERIMENT_ID,
    REPORT_NAMES,
    ROADMAP_STATUS,
    TREATMENT_RANKING,
    governance_rows,
    implementation_parameters,
    implementation_research_config,
    implementation_success_criteria,
    preregistration,
    rank_compression_priority,
    real_date_structural_pilots,
    synthetic_ranking_pilot,
    verify_frozen_inputs,
    verify_signal_set_identity,
)
from app.research.strategy.family_a_momentum import file_sha256


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data/research/strategy_families/family_c/v1/implementation_research"


def _criteria_inputs():
    portfolio = {
        "net_CAGR": Decimal("0.03173069861574107"),
        "max_drawdown": Decimal("0.2208443281999234540844616697"),
        "normalized_cost_drag": Decimal("0.21831072"),
        "yearly_returns": {
            "2022": Decimal("-0.1005287184"),
            "2023": Decimal("0.054643012629120498203574886"),
            "2024": Decimal("0.157727308250891659323241228"),
        },
    }
    admitted = {
        "net_expectancy": Decimal("0.002132077445397085395329098845"),
        "net_profit_factor": Decimal("1.089795625568447941013450018"),
        "win_rate": Decimal("0.4982905982905982905982905983"),
    }
    return portfolio, admitted


def test_command_identity_and_attribution_hash_gate() -> None:
    assert COMMAND_VERSION == "FAMILY_C_C001_IMPLEMENTATION_RESEARCH_V1"
    assert COMMAND_PROFILE == "C001_COMPRESSION_PRIORITY_PREREGISTRATION_V1"
    assert EXPECTED_ATTRIBUTION_HASH == "26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b"
    gate = verify_frozen_inputs(REPO_ROOT)
    assert gate["status"] == "VERIFIED"
    assert all(gate["checks"].values())


def test_exactly_one_experiment_and_reference_control() -> None:
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json").read_text(encoding="utf-8")
    )
    assert EXPERIMENT_ID == "C1-IMP-001"
    assert EXPERIMENT_NAME == "C001_COMPRESSION_PRIORITY_CAPACITY_RANKING_V1"
    assert REFERENCE_EXPERIMENT_ID == "BRK-C-001"
    assert summary["registry"]["experiment_count"] == 1
    assert len(summary["registry"]["experiments"]) == 1
    experiment = summary["registry"]["experiments"][0]
    assert experiment["experiment_id"] == EXPERIMENT_ID
    assert experiment["status"] == "PREREGISTERED"
    assert experiment["promotion_allowed"] is False


def test_compression_priority_ranking_is_exact_lexicographic_order() -> None:
    rows = [
        {"symbol": "Z", "compression_range_pct": "0.06", "breakout_strength_pct": "0.09"},
        {"symbol": "C", "compression_range_pct": "0.05", "breakout_strength_pct": "0.02"},
        {"symbol": "A", "compression_range_pct": "0.05", "breakout_strength_pct": "0.02"},
        {"symbol": "B", "compression_range_pct": "0.05", "breakout_strength_pct": "0.03"},
        {"symbol": "D", "compression_range_pct": "0.04", "breakout_strength_pct": "0.01"},
    ]
    result = rank_compression_priority(rows, 3)
    assert [row["symbol"] for row in result["ranked"]] == ["D", "B", "A", "C", "Z"]
    assert [row["symbol"] for row in result["selected"]] == ["D", "B", "A"]
    assert TREATMENT_RANKING == (
        "COMPRESSION_RANGE_PCT_ASCENDING",
        "BREAKOUT_STRENGTH_PCT_DESCENDING",
        "SYMBOL_ASCENDING",
    )
    assert ORIGINAL_RANKING == (
        "BREAKOUT_STRENGTH_PCT_DESCENDING",
        "SYMBOL_ASCENDING",
    )


def test_frozen_signal_and_portfolio_parameters_are_unchanged() -> None:
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json").read_text(encoding="utf-8")
    )
    parameters = summary["parameters"]
    assert BREAKOUT_WINDOW == parameters["breakout"]["lookback_sessions"] == 20
    assert COMPRESSION_WINDOW == parameters["compression"]["window_sessions"] == 10
    assert Decimal(parameters["compression"]["threshold"]) == COMPRESSION_THRESHOLD == Decimal("0.08")
    assert HOLDING_SESSIONS == parameters["holding_completed_sessions"] == 10
    assert MAX_CONCURRENT_POSITIONS == parameters["max_concurrent_positions"] == 20
    assert Decimal(parameters["starting_capital"]) == STARTING_CAPITAL == Decimal("500000")
    assert Decimal(parameters["target_notional_fraction_of_current_equity"]) == TARGET_NOTIONAL_FRACTION == Decimal("0.05")
    assert parameters["stop"] is None
    assert parameters["target"] is None
    assert parameters["capacity_ranking"] == list(TREATMENT_RANKING)
    assert summary["configuration"]["only_experimental_change"] == "SAME_DAY_CAPACITY_RANKING"


def test_signal_set_hash_and_identity_are_exact() -> None:
    record = json.loads(
        (OUTPUT_ROOT / "ranking/c001_signal_set_v1.json").read_text(encoding="utf-8")
    )
    field = "c001_signal_set_hash"
    body = {key: value for key, value in record.items() if key != field}
    assert len(record["events"]) == record["event_count"] == 4247
    assert canonical_hash(body) == record[field]
    identity = verify_signal_set_identity(REPO_ROOT, record["events"])
    assert identity["equal"] is True
    assert identity["frozen_count"] == identity["treatment_count"] == 4247
    assert identity[field] == record[field]


def test_synthetic_ranking_pilot_covers_all_three_sort_keys() -> None:
    rows = synthetic_ranking_pilot()
    assert [row["symbol"] for row in rows] == ["DELTA", "BRAVO", "ALPHA", "CHARLIE", "ECHO"]
    assert all(row["ordering_verified"] for row in rows)
    assert all(row["performance_calculated"] is False for row in rows)
    assert sum(row["selected_with_three_slots"] for row in rows) == 3


def test_real_date_pilots_are_structural_only() -> None:
    signal_set = json.loads(
        (OUTPUT_ROOT / "ranking/c001_signal_set_v1.json").read_text(encoding="utf-8")
    )["events"]
    rows, findings = real_date_structural_pilots(REPO_ROOT, signal_set)
    assert findings["real_date_pilot_count"] == 5
    assert findings["selection_changed_rows"] > 0
    assert findings["old_admitted_new_rejected"] == findings["old_rejected_new_selected"]
    assert all(row["performance_calculated"] is False for row in rows)
    assert all(row["validation_accessed"] is False for row in rows)
    forbidden = {"ending_equity", "CAGR", "drawdown", "strategy_return", "net_return"}
    assert all(not forbidden.intersection(row) for row in rows)


def test_success_criteria_freeze_exact_thresholds() -> None:
    portfolio, admitted = _criteria_inputs()
    criteria = implementation_success_criteria(portfolio, admitted)
    dimensions = criteria["admitted_quality_dimensions"]
    assert dimensions["EXPECTANCY"]["multiplier"] == "1.15"
    assert dimensions["PROFIT_FACTOR"]["absolute_increment"] == "0.05"
    assert dimensions["WIN_RATE"]["percentage_point_increment"] == "0.03"
    standard = criteria["standard_criteria_A_H"]
    assert len(standard) == 8
    assert "NET_PF_GTE_1_10" in standard["B_PORTFOLIO_PROFITABILITY"]
    assert "TIMES_0_90" in standard["C_RETURN_NON_DEGRADATION"]
    assert "LTE_0_10" in standard["D_DRAWDOWN_NON_DEGRADATION"]
    assert "TIMES_1_20" in standard["F_COST_NON_DEGRADATION"]
    assert "GTE_500" in standard["G_SAMPLE_ADEQUACY"]
    field = "implementation_success_criteria_hash"
    assert canonical_hash({key: value for key, value in criteria.items() if key != field}) == criteria[field]


def test_parameter_preregistration_and_config_hashes_recompute() -> None:
    config = implementation_research_config()
    parameters = implementation_parameters("signal-hash")
    portfolio, admitted = _criteria_inputs()
    criteria = implementation_success_criteria(portfolio, admitted)
    prereg = preregistration(config, parameters, criteria, "signal-hash")
    for document, field in (
        (config, "implementation_research_config_hash"),
        (parameters, "parameter_hash"),
        (criteria, "implementation_success_criteria_hash"),
        (prereg, "preregistration_hash"),
    ):
        body = {key: value for key, value in document.items() if key != field}
        assert canonical_hash(body) == document[field]
    assert prereg["performance_run"] is False
    assert prereg["validation_accessed"] is False


def test_governance_v2_is_14_of_14() -> None:
    config = implementation_research_config()
    parameters = implementation_parameters("signal-hash")
    portfolio, admitted = _criteria_inputs()
    criteria = implementation_success_criteria(portfolio, admitted)
    prereg = preregistration(config, parameters, criteria, "signal-hash")
    rows = governance_rows(config, parameters, criteria, prereg)
    assert len(rows) == len(GOVERNANCE_ITEMS) == 14
    assert [row["check"] for row in rows] == list(GOVERNANCE_ITEMS)
    assert all(row["status"] == "PASS" for row in rows)


def test_no_performance_validation_or_second_ranking() -> None:
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json").read_text(encoding="utf-8")
    )
    assert summary["performance"] == {
        "performance_run": False,
        "calculated_metrics": [],
        "C1_IMP_001_FUTURE_RESULT": None,
    }
    prohibited = summary["governance_prohibitions"]
    for key in (
        "second_ranking_tested",
        "compression_threshold_changed",
        "capacity_changed",
        "holding_period_changed",
        "stop_added",
        "target_added",
        "validation_accessed",
        "strategy_v2_created",
    ):
        assert prohibited[key] is False


def test_generated_registry_criteria_and_manifest_hashes() -> None:
    registry = json.loads(
        (OUTPUT_ROOT / "registry/implementation_research_registry_v1.json").read_text(encoding="utf-8")
    )
    criteria = json.loads(
        (OUTPUT_ROOT / "governance/implementation_success_criteria_v1.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (OUTPUT_ROOT / "manifests/implementation_research_manifest_v1.json").read_text(encoding="utf-8")
    )
    for document, field in (
        (registry, "implementation_research_registry_hash"),
        (criteria, "implementation_success_criteria_hash"),
        (manifest, "implementation_research_manifest_hash"),
    ):
        body = {key: value for key, value in document.items() if key != field}
        assert canonical_hash(body) == document[field]
    assert registry["experiment_count"] == 1
    assert manifest["performance_run"] is False
    assert manifest["validation_accessed"] is False
    manifest_relative_path = (
        "data/research/strategy_families/family_c/v1/implementation_research/"
        "manifests/implementation_research_manifest_v1.json"
    )
    assert manifest_relative_path not in manifest["artifact_hashes"]
    for relative_path, expected_hash in manifest["artifact_hashes"].items():
        assert file_sha256(REPO_ROOT / relative_path) == expected_hash
    assert (
        file_sha256(REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json")
        == manifest["summary_hash"]
    )


def test_reports_readiness_documentation_and_roadmap() -> None:
    assert len(REPORT_NAMES) == 6
    assert all((REPO_ROOT / "data/reports" / name).is_file() for name in REPORT_NAMES)
    for directory in ("registry", "pilots", "manifests", "governance", "ranking"):
        assert (OUTPUT_ROOT / directory).is_dir()
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json").read_text(encoding="utf-8")
    )
    assert summary["classifications"]["C1_IMP_001_ARCHITECTURE_RESULT"] == "READY_FOR_CONTROLLED_DEVELOPMENT_TEST"
    assert summary["governance"]["status"] == "PASS"
    assert summary["governance"]["passed"] == summary["governance"]["required"] == 14
    assert (REPO_ROOT / "docs/strategy-family-c-c001-implementation-research-v1.md").is_file()
    roadmap = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(encoding="utf-8")
    assert any(
        status in roadmap
        for status in (
            f"| Family C | Breakout Continuation | {ROADMAP_STATUS} |",
            "| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |",
        )
    )
    assert "| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |" in roadmap
    assert "| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |" in roadmap


def test_security_is_zero_and_family_d_not_started() -> None:
    summary = json.loads(
        (REPO_ROOT / "data/reports/family_c_imp001_v1_summary.json").read_text(encoding="utf-8")
    )
    assert all(value == 0 for value in summary["security"].values())
    assert summary["governance_prohibitions"]["family_d_started"] is False

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_g_research_closure import (
    CAPITAL_PATH_EFFECT,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    CONTROL_G_000_FINAL_STATUS,
    DEVELOPMENT_RESULT_HASHES,
    DIRECT_GATE_EFFECT,
    FAMILY_G_EVIDENCE_STATUS,
    FAMILY_G_FROZEN_HASHES,
    FAMILY_G_FUTURE_RESEARCH_POLICY,
    FAMILY_G_RESEARCH_LESSON_VERSION,
    FAMILY_G_RESEARCH_STATUS,
    FAMILY_G_STRATEGY_V2_STATUS,
    FAMILY_G_VALIDATION_STATUS,
    MANIFEST_VERSION,
    NEGATIVE_EVIDENCE_ID,
    NEGATIVE_EVIDENCE_STATUS,
    NEXT_PLANNED_PHASE,
    PREHISTORY_HASHES,
    PREHISTORY_INFRASTRUCTURE,
    REGIME_G_001_FINAL_STATUS,
    REPORT_NAMES,
    ROADMAP_STATUSES,
    STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS,
    prior_artifact_snapshot,
    verify_closure_inputs,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = REPO_ROOT / "data/research/strategy_families/family_g/v1/closure"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = (
    CLOSURE_ROOT / "manifest/family_g_research_closure_manifest_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _manifest() -> dict:
    return _json(MANIFEST_PATH)


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_command_and_all_frozen_inputs_are_verified_exactly() -> None:
    assert COMMAND_VERSION == "FAMILY_G_RESEARCH_CLOSURE_V1"
    assert COMMAND_PROFILE == "REGIME_PARTICIPATION_CLOSURE_V1"
    assert MANIFEST_VERSION == "FAMILY_G_RESEARCH_CLOSURE_MANIFEST_V1"
    verification = verify_closure_inputs(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert all(verification["checks"].values())
    assert verification["family_g_frozen_hashes"] == FAMILY_G_FROZEN_HASHES
    assert verification["prehistory_hashes"] == PREHISTORY_HASHES
    assert verification["development_result_hashes"] == DEVELOPMENT_RESULT_HASHES


def test_all_required_hash_values_are_frozen() -> None:
    assert FAMILY_G_FROZEN_HASHES == {
        "family_g_config_hash": "602626276ea5d0fbfd4321ad37f0e6f70ee543bb55b38f8aaaa3e559134e59a2",
        "control_g_000_reference_hash": "e7686b02bd7858cd1c540695cbaee5667426c0445db3bc37e21f4fad2f42048c",
        "regime_g_001_parameter_hash": "8fcce3ab5eb35e8bd07e7db8b4ba16ce3e43244100ff50b38ba621e88a326a14",
        "regime_g_001_preregistration_hash": "c18e8a9119fd68f276544475aff4d634359d4545e1cbfbab05734b26ec8cade5",
        "family_g_success_criteria_hash": "c1b697047ebeec75d4fd6d9aac52d23f0de525f5c91df5a8063e7323da20f719",
        "governance_policy_hash": "152c651e0ee0760bb5d331886de1dd0f0f4491d2823046182fb73bc8fe836488",
    }
    assert PREHISTORY_HASHES == {
        "family_g_prehistory_remediation_config_hash": "9491b33f9d1882bba5aade35cce73a21cd8b8366fa985607147cdd0c377f45cf",
        "nifty500_prehistory_raw_hash": "2c5d507f7af8c0f93c82e297d49f490d97bcf47f1c4250d53a4900c6f1b9af07",
        "nifty500_prehistory_normalized_hash": "9275d17c96eff3f701194759e524229847af4673245d127a1dac57c71f107e96",
        "nifty500_overlap_reconciliation_hash": "b943ac884033d7b9f3073c75ec119a6e3557faced003da39f3c86405176ced4c",
        "family_g_regime_matrix_hash": "291e295b19945dee9e9e648d3bf2162801982da73757a767c0178ccbc64b21d6",
        "family_g_post_remediation_readiness_hash": "e16d8d345ba950b2ea275d95fc9fc824b2aa774f7bbfa5d391c046a903664c93",
        "family_g_benchmark_prehistory_manifest_hash": "bb60b53448b8148ff8c14422c25dcf24e4acac2919013cd3d22402952c932a96",
    }
    assert DEVELOPMENT_RESULT_HASHES == {
        "control_g_000_result_hash": "f953062ce28fe0a439fd8cbd00bc79b426625f7533f3fa414c632fa75243fd7b",
        "regime_g_001_result_hash": "5c1738f4e8a4f0ddb6c7bd45f83a0e191361ad530780cdae85f172a350166198",
        "family_g_development_registry_hash": "c44850f520942effb2b8e42ab4596cd036242675aee4fcf6b0c6ff344df32d2f",
        "family_g_development_evaluation_manifest_hash": "5fb0643f3f2a2c8b9795a664435b908166345467df0c8ae005f7f88db6f2723c",
    }


def test_control_treatment_and_family_statuses_are_final() -> None:
    statuses = _summary()["statuses"]
    assert statuses == {
        "CONTROL_G_000_FINAL_STATUS": CONTROL_G_000_FINAL_STATUS,
        "REGIME_G_001_FINAL_STATUS": REGIME_G_001_FINAL_STATUS,
        "FAMILY_G_RESEARCH_STATUS": FAMILY_G_RESEARCH_STATUS,
        "FAMILY_G_EVIDENCE_STATUS": FAMILY_G_EVIDENCE_STATUS,
        "FAMILY_G_VALIDATION_STATUS": FAMILY_G_VALIDATION_STATUS,
        "FAMILY_G_STRATEGY_V2_STATUS": FAMILY_G_STRATEGY_V2_STATUS,
    }
    assert CONTROL_G_000_FINAL_STATUS == "PRESERVED_STRONG_REFERENCE_CONTROL"
    assert REGIME_G_001_FINAL_STATUS == "CLOSED_PARTIALLY_SUPPORTED_NOT_ADVANCED"
    assert FAMILY_G_RESEARCH_STATUS == "PAUSED_NO_VALIDATION_CANDIDATE"
    assert FAMILY_G_VALIDATION_STATUS == "NOT_ACCESSED"
    assert FAMILY_G_STRATEGY_V2_STATUS == "NOT_CREATED"


def test_frozen_control_and_treatment_reference_metrics_are_exact() -> None:
    evidence = _summary()["evidence"]
    assert evidence["control"] == {
        "experiment_id": "CONTROL-G-000",
        "final_status": CONTROL_G_000_FINAL_STATUS,
        "reference_experiment_id": "MOM-A-002",
        "implementation_reference": "A2-002",
        "starting_capital_rupees": "500000",
        "net_ending_equity_rupees": "955331.6799",
        "net_return_pct": "91.0663359800",
        "net_cagr_pct": "24.105850672292473",
        "max_drawdown_magnitude_pct": "22.92216992201015671886716806",
        "annualized_volatility_pct": "21.225518024865917",
        "sharpe_like": "1.1423662151622573",
        "evidence_scope": "DEVELOPMENT_ONLY_NOT_VALIDATED",
    }
    treatment = evidence["treatment"]
    assert treatment["net_ending_equity_rupees"] == "701280.9627"
    assert treatment["net_return_pct"] == "40.2561925400"
    assert treatment["net_cagr_pct"] == "11.945736746483359"
    assert treatment["max_drawdown_magnitude_pct"] == (
        "30.72712578084777096151980811"
    )
    assert treatment["annualized_volatility_pct"] == "20.2948146190893"
    assert treatment["sharpe_like"] == "0.6681925214711923"
    assert treatment["return_preservation"] == "FAILED"
    assert treatment["drawdown_objective"] == "FAILED"
    assert treatment["advanced"] is False


def test_negative_evidence_and_two_missed_gain_intervals_are_preserved() -> None:
    negative = _summary()["negative_evidence"]
    assert negative["evidence_id"] == NEGATIVE_EVIDENCE_ID
    assert negative["status"] == NEGATIVE_EVIDENCE_STATUS
    assert negative["tested_design"] == {
        "decision_frequency": "QUARTERLY",
        "market_index": "NIFTY_500",
        "gate": "CLOSE_ABOVE_SMA200",
        "participation": "ALL_IN_OR_ALL_CASH",
        "treatment_count": 1,
    }
    assert negative["missed_gain_intervals"] == [
        {
            "rebalance_date": "2022-06-30",
            "execution_date": "2022-07-01",
            "interval_end": "2022-10-03",
            "control_return_pct": "13.77159596075032505853906660",
            "treatment_return_pct": "0",
            "classification": "MISSED_GAIN",
        },
        {
            "rebalance_date": "2023-03-31",
            "execution_date": "2023-04-03",
            "interval_end": "2023-07-03",
            "control_return_pct": "19.97507308961838985613335600",
            "treatment_return_pct": "0",
            "classification": "MISSED_GAIN",
        },
    ]
    assert negative["generalization_prohibited"] == [
        "SMA200_NEVER_WORKS",
        "MARKET_REGIME_FILTERS_NEVER_WORK",
    ]


def test_direct_and_capital_path_effects_are_frozen() -> None:
    negative = _summary()["negative_evidence"]
    assert negative["DIRECT_GATE_EFFECT"] == DIRECT_GATE_EFFECT == "NEGATIVE"
    assert negative["direct_gate_effect_rupees"] == (
        "-262351.7854122956219083635528"
    )
    assert negative["direct_gate_effect_reason"] == (
        "BOTH_EXCLUDED_CONTROL_INTERVALS_WERE_PROFITABLE"
    )
    assert negative["CAPITAL_PATH_EFFECT"] == (
        CAPITAL_PATH_EFFECT
    ) == "PARTIAL_OFFSET_ONLY"
    assert negative["capital_path_effect_rupees"] == (
        "8301.0682122956219083635528"
    )
    assert negative["final_treatment_minus_control_rupees"] == "-254050.7172"


def test_primary_drawdown_cost_and_volatility_lessons_are_frozen() -> None:
    lessons = _summary()["lessons"]
    assert lessons["version"] == FAMILY_G_RESEARCH_LESSON_VERSION
    assert "two excluded quarters were profitable" in lessons["primary_lesson"]
    drawdown = lessons["drawdown_lesson"]
    assert drawdown["control_max_drawdown_magnitude_pct"] == (
        "22.92216992201015671886716806"
    )
    assert drawdown["treatment_max_drawdown_magnitude_pct"] == (
        "30.72712578084777096151980811"
    )
    assert drawdown["relative_change_pct"] == "34.04981241040010426169685913"
    assert drawdown["result"] == "WORSENED"
    costs = lessons["cost_lesson"]
    assert costs["treatment_cost_reduction_rupees"] == "3659.37"
    assert costs["treatment_cost_reduction_pct"] == (
        "20.75661234607116319434596906"
    )
    volatility = lessons["volatility_lesson"]
    assert volatility["control_annualized_volatility_pct"] == "21.225518024865917"
    assert volatility["treatment_annualized_volatility_pct"] == "20.2948146190893"
    assert volatility["control_sharpe_like"] == "1.1423662151622573"
    assert volatility["treatment_sharpe_like"] == "0.6681925214711923"


def test_family_a_and_prehistory_infrastructure_are_preserved() -> None:
    summary = _summary()
    preservation = summary["evidence"]["family_a_preservation"]
    assert "does not weaken" in preservation["finding"]
    assert "INR 500,000" in preservation["independent_reproduction"]
    assert preservation["family_a_evidence_upgraded_to_validated"] is False
    assert summary["lessons"]["shared_infrastructure_preserved"] == (
        PREHISTORY_INFRASTRUCTURE
    )
    assert summary["lessons"]["attribution_artifacts_preserved"] == [
        "QUARTERLY_LEDGER",
        "CASH_QUARTER_ATTRIBUTION",
        "PATH_EFFECT_ANALYSIS",
        "DRAWDOWN_ATTRIBUTION",
        "COST_TURNOVER_ANALYSIS",
        "NORMALIZED_QUARTER_DIAGNOSTIC",
    ]


def test_future_policy_requires_new_architecture_and_preregistration() -> None:
    governance = _summary()["governance"]
    assert governance["FAMILY_G_FUTURE_RESEARCH_POLICY"] == (
        FAMILY_G_FUTURE_RESEARCH_POLICY
    ) == "REQUIRES_GENUINELY_NEW_REGIME_ARCHITECTURE"
    assert "new preregistration" in governance["resume_rule"]
    assert governance["incremental_variants_not_authorized"] == [
        "SMA150",
        "SMA250",
        "NIFTY50_INSTEAD_OF_NIFTY500",
        "MONTHLY_INSTEAD_OF_QUARTERLY",
        "VIX_THRESHOLD",
        "BREADTH_THRESHOLD",
        "MULTIPLE_REGIME_SCORE",
        "PARTIAL_EXPOSURE_PERCENTAGES",
    ]


def test_no_performance_rerun_new_treatment_validation_v2_or_synthesis() -> None:
    summary = _summary()
    governance = summary["governance"]
    safety = summary["safety"]
    for field in (
        "performance_rerun",
        "new_treatment_created",
        "parameters_changed",
        "validation_accessed",
        "strategy_v2_created",
        "cross_family_synthesis_performed",
        "new_family_started",
    ):
        assert governance[field] is False
        assert safety[field] is False
    source = (
        REPO_ROOT / "backend/app/research/strategy/family_g_research_closure.py"
    ).read_text(encoding="utf-8")
    assert "build_family_g_development_evaluation" not in source
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("backtest" in module for module in imports)
    assert not any(name in module for module in imports for name in ("requests", "httpx"))
    assert not re.search(r"REGIME-G-00[2-9]", source)


def test_roadmap_has_exact_current_states_and_cycle_handoff() -> None:
    summary = _summary()
    assert summary["roadmap"] == ROADMAP_STATUSES
    roadmap = (
        REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md"
    ).read_text(encoding="utf-8")
    directions = {
        "family_A": ("Family A", "Medium-Term Momentum"),
        "family_B": ("Family B", "Relative + Absolute Momentum"),
        "family_C": ("Family C", "Breakout Continuation"),
        "family_D": ("Family D", "Opening Range / Stocks-in-Play"),
        "family_E": ("Family E", "Pullback / Reclaim"),
        "family_F": ("Family F", "Catalyst Momentum"),
        "family_G": ("Family G", "Regime / Volatility"),
    }
    for key, status in ROADMAP_STATUSES.items():
        family, direction = directions[key]
        assert f"| {family} | {direction} | {status} |" in roadmap
    assert (
        "STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS = "
        "COMPLETE_FOR_CURRENT_RESEARCH_CYCLE"
    ) in roadmap
    assert "NEXT_PLANNED_PHASE = CROSS_FAMILY_EVIDENCE_SYNTHESIS" in roadmap


def test_cycle_completion_and_synthesis_handoff_are_planning_only() -> None:
    handoff = _summary()["handoff"]
    assert handoff["STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS"] == (
        STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS
    ) == "COMPLETE_FOR_CURRENT_RESEARCH_CYCLE"
    assert handoff["production_strategy_selected"] is False
    assert handoff["NEXT_PLANNED_PHASE"] == (
        NEXT_PLANNED_PHASE
    ) == "CROSS_FAMILY_EVIDENCE_SYNTHESIS"
    assert handoff["status"] == "PLANNING_NOTE_ONLY"
    assert len(handoff["purpose"]) == 5
    assert handoff["cross_family_synthesis_performed"] is False
    assert handoff["validation_design_created"] is False
    assert handoff["new_family_started"] is False


def test_closure_manifest_hash_components_and_prior_artifacts_are_immutable() -> None:
    manifest = _manifest()
    body = {key: value for key, value in manifest.items() if key != "family_g_closure_hash"}
    assert manifest["family_g_closure_hash"] == canonical_hash(body)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["closure_timestamp"].endswith("Z")
    for relative, expected in manifest["component_hashes"].items():
        assert file_sha256(REPO_ROOT / relative) == expected
    assert manifest["prior_command_artifact_snapshot"] == prior_artifact_snapshot(
        REPO_ROOT
    )


def test_reports_documentation_and_storage_layout_exist() -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert (REPO_ROOT / "docs/strategy-family-g-closure-v1.md").is_file()
    for directory in ("manifest", "evidence", "lessons", "governance", "handoff"):
        assert (CLOSURE_ROOT / directory).is_dir()
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[1])) == 2
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[2])) == 1
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[3])) == 6
    assert len(_csv(REPORT_ROOT / REPORT_NAMES[4])) == 1


def test_security_and_zero_external_effects_are_explicit() -> None:
    safety = _summary()["safety"]
    assert safety["network_accessed"] is False
    assert safety["credentials_written"] is False
    assert safety["external_writes"] == 0
    assert safety["live_signals"] == 0
    assert safety["live_orders"] == 0
    assert safety["broker_calls"] == 0
    assert safety["database_writes"] == 0
    assert safety["remote_migrations"] == 0
    assert safety["supabase_persistence"] == 0

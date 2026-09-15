from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.research.strategy.family_a_momentum import file_sha256, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.07 / Command 04"
COMMAND_VERSION = "FAMILY_G_RESEARCH_CLOSURE_V1"
COMMAND_PROFILE = "REGIME_PARTICIPATION_CLOSURE_V1"
MANIFEST_VERSION = "FAMILY_G_RESEARCH_CLOSURE_MANIFEST_V1"
FAMILY_VERSION = "STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1"
FAMILY_PROFILE = "QUARTERLY_MOMENTUM_REGIME_PARTICIPATION_V1"

CONTROL_G_000_FINAL_STATUS = "PRESERVED_STRONG_REFERENCE_CONTROL"
REGIME_G_001_FINAL_STATUS = "CLOSED_PARTIALLY_SUPPORTED_NOT_ADVANCED"
FAMILY_G_RESEARCH_STATUS = "PAUSED_NO_VALIDATION_CANDIDATE"
FAMILY_G_EVIDENCE_STATUS = (
    "SIMPLE_QUARTERLY_SMA200_PARTICIPATION_GATE_NOT_SUPPORTED_FOR_ADVANCEMENT"
)
FAMILY_G_VALIDATION_STATUS = "NOT_ACCESSED"
FAMILY_G_STRATEGY_V2_STATUS = "NOT_CREATED"
FAMILY_G_FUTURE_RESEARCH_POLICY = "REQUIRES_GENUINELY_NEW_REGIME_ARCHITECTURE"
FAMILY_G_RESEARCH_LESSON_VERSION = "FAMILY_G_RESEARCH_LESSON_V1"
NEGATIVE_EVIDENCE_ID = "EDGE-NEGATIVE-G-SMA200-GATE-001"
NEGATIVE_EVIDENCE_STATUS = "RESEARCH_EVIDENCE_NOT_VALIDATED"
DIRECT_GATE_EFFECT = "NEGATIVE"
CAPITAL_PATH_EFFECT = "PARTIAL_OFFSET_ONLY"
PREHISTORY_INFRASTRUCTURE = "NIFTY500_BENCHMARK_PREHISTORY_V1"
STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS = "COMPLETE_FOR_CURRENT_RESEARCH_CYCLE"
NEXT_PLANNED_PHASE = "CROSS_FAMILY_EVIDENCE_SYNTHESIS"

FAMILY_G_FROZEN_HASHES = {
    "family_g_config_hash": (
        "602626276ea5d0fbfd4321ad37f0e6f70ee543bb55b38f8aaaa3e559134e59a2"
    ),
    "control_g_000_reference_hash": (
        "e7686b02bd7858cd1c540695cbaee5667426c0445db3bc37e21f4fad2f42048c"
    ),
    "regime_g_001_parameter_hash": (
        "8fcce3ab5eb35e8bd07e7db8b4ba16ce3e43244100ff50b38ba621e88a326a14"
    ),
    "regime_g_001_preregistration_hash": (
        "c18e8a9119fd68f276544475aff4d634359d4545e1cbfbab05734b26ec8cade5"
    ),
    "family_g_success_criteria_hash": (
        "c1b697047ebeec75d4fd6d9aac52d23f0de525f5c91df5a8063e7323da20f719"
    ),
    "governance_policy_hash": (
        "152c651e0ee0760bb5d331886de1dd0f0f4491d2823046182fb73bc8fe836488"
    ),
}

PREHISTORY_HASHES = {
    "family_g_prehistory_remediation_config_hash": (
        "9491b33f9d1882bba5aade35cce73a21cd8b8366fa985607147cdd0c377f45cf"
    ),
    "nifty500_prehistory_raw_hash": (
        "2c5d507f7af8c0f93c82e297d49f490d97bcf47f1c4250d53a4900c6f1b9af07"
    ),
    "nifty500_prehistory_normalized_hash": (
        "9275d17c96eff3f701194759e524229847af4673245d127a1dac57c71f107e96"
    ),
    "nifty500_overlap_reconciliation_hash": (
        "b943ac884033d7b9f3073c75ec119a6e3557faced003da39f3c86405176ced4c"
    ),
    "family_g_regime_matrix_hash": (
        "291e295b19945dee9e9e648d3bf2162801982da73757a767c0178ccbc64b21d6"
    ),
    "family_g_post_remediation_readiness_hash": (
        "e16d8d345ba950b2ea275d95fc9fc824b2aa774f7bbfa5d391c046a903664c93"
    ),
    "family_g_benchmark_prehistory_manifest_hash": (
        "bb60b53448b8148ff8c14422c25dcf24e4acac2919013cd3d22402952c932a96"
    ),
}

DEVELOPMENT_RESULT_HASHES = {
    "control_g_000_result_hash": (
        "f953062ce28fe0a439fd8cbd00bc79b426625f7533f3fa414c632fa75243fd7b"
    ),
    "regime_g_001_result_hash": (
        "5c1738f4e8a4f0ddb6c7bd45f83a0e191361ad530780cdae85f172a350166198"
    ),
    "family_g_development_registry_hash": (
        "c44850f520942effb2b8e42ab4596cd036242675aee4fcf6b0c6ff344df32d2f"
    ),
    "family_g_development_evaluation_manifest_hash": (
        "5fb0643f3f2a2c8b9795a664435b908166345467df0c8ae005f7f88db6f2723c"
    ),
}

ROADMAP_STATUSES = {
    "family_A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
    "family_B": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_C": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
    "family_E": "PAUSED_NO_VALIDATION_CANDIDATE",
    "family_F": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE",
    "family_G": FAMILY_G_RESEARCH_STATUS,
}

REPORT_NAMES = (
    "family_g_closure_v1_summary.json",
    "family_g_closure_v1_evidence.csv",
    "family_g_closure_v1_negative_evidence.csv",
    "family_g_closure_v1_lessons.csv",
    "family_g_closure_v1_handoff.csv",
)


class FamilyGClosureInputMismatch(RuntimeError):
    pass


class FamilyGClosureImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_g/v1/closure"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash(
        {key: value for key, value in document.items() if key != hash_field}
    )


def _input_mismatch(reason: str) -> None:
    raise FamilyGClosureInputMismatch(f"FAMILY_G_CLOSURE_INPUT_MISMATCH: {reason}")


def _input_paths(root: Path) -> dict[str, Path]:
    family = Path(root) / "data/research/strategy_families/family_g/v1"
    development = family / "development_evaluation"
    prehistory = family / "benchmark_prehistory"
    return {
        "family_config": family / "registry/family_g_config_v1.json",
        "control_reference": family / "registry/control_g_000_reference_v1.json",
        "treatment_parameter": family / "registry/regime_g_001_parameters_v1.json",
        "treatment_preregistration": (
            family / "registry/regime_g_001_preregistration_v1.json"
        ),
        "success_criteria": family / "governance/family_g_success_criteria_v1.json",
        "governance": (
            Path(root)
            / "data/research/strategy_families/family_a/v1/closure/governance/"
            "research_experiment_governance_v2.json"
        ),
        "architecture_manifest": family / "manifests/family_g_architecture_manifest_v1.json",
        "remediation_config": (
            prehistory / "manifests/family_g_prehistory_remediation_config_v1.json"
        ),
        "raw_registry": (
            prehistory / "raw_extension/nifty500_prehistory_raw_registry_v1.json"
        ),
        "normalized_registry": (
            prehistory
            / "normalized_extension/nifty500_benchmark_prehistory_registry_v1.json"
        ),
        "overlap": (
            prehistory / "reconciliation/nifty500_overlap_reconciliation_v1.json"
        ),
        "regime_matrix": (
            prehistory / "regime_matrix/family_g_regime_matrix_v1.json"
        ),
        "readiness": (
            prehistory / "manifests/family_g_post_remediation_readiness_v1.json"
        ),
        "prehistory_manifest": (
            prehistory / "manifests/family_g_benchmark_prehistory_manifest_v1.json"
        ),
        "control_result": development / "control/control_g_000_result_v1.json",
        "treatment_result": (
            development / "regime_g_001/regime_g_001_result_v1.json"
        ),
        "development_registry": (
            development / "manifests/family_g_development_registry_v1.json"
        ),
        "development_manifest": (
            development
            / "manifests/family_g_development_evaluation_manifest_v1.json"
        ),
        "development_summary": Path(root) / "data/reports/family_g_dev_v1_summary.json",
    }


def _verify_manifest_artifacts(root: Path, manifest: Mapping[str, Any]) -> bool:
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    return all(
        (Path(root) / relative).is_file()
        and file_sha256(Path(root) / relative) == expected
        for relative, expected in hashes.items()
    )


def verify_closure_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    paths = _input_paths(root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        _input_mismatch(f"missing inputs: {missing}")
    documents = {name: _read_json(path) for name, path in paths.items()}

    semantic_specs = {
        "family_config": ("family_g_config_hash", FAMILY_G_FROZEN_HASHES["family_g_config_hash"]),
        "control_reference": (
            "control_g_000_reference_hash",
            FAMILY_G_FROZEN_HASHES["control_g_000_reference_hash"],
        ),
        "treatment_preregistration": (
            "regime_g_001_preregistration_hash",
            FAMILY_G_FROZEN_HASHES["regime_g_001_preregistration_hash"],
        ),
        "success_criteria": (
            "family_g_success_criteria_hash",
            FAMILY_G_FROZEN_HASHES["family_g_success_criteria_hash"],
        ),
        "governance": (
            "governance_policy_hash",
            FAMILY_G_FROZEN_HASHES["governance_policy_hash"],
        ),
        "remediation_config": (
            "family_g_prehistory_remediation_config_hash",
            PREHISTORY_HASHES["family_g_prehistory_remediation_config_hash"],
        ),
        "raw_registry": (
            "nifty500_prehistory_raw_hash",
            PREHISTORY_HASHES["nifty500_prehistory_raw_hash"],
        ),
        "normalized_registry": (
            "nifty500_prehistory_normalized_hash",
            PREHISTORY_HASHES["nifty500_prehistory_normalized_hash"],
        ),
        "overlap": (
            "nifty500_overlap_reconciliation_hash",
            PREHISTORY_HASHES["nifty500_overlap_reconciliation_hash"],
        ),
        "regime_matrix": (
            "family_g_regime_matrix_hash",
            PREHISTORY_HASHES["family_g_regime_matrix_hash"],
        ),
        "readiness": (
            "family_g_post_remediation_readiness_hash",
            PREHISTORY_HASHES["family_g_post_remediation_readiness_hash"],
        ),
        "prehistory_manifest": (
            "family_g_benchmark_prehistory_manifest_hash",
            PREHISTORY_HASHES["family_g_benchmark_prehistory_manifest_hash"],
        ),
        "control_result": (
            "control_g_000_result_hash",
            DEVELOPMENT_RESULT_HASHES["control_g_000_result_hash"],
        ),
        "treatment_result": (
            "regime_g_001_result_hash",
            DEVELOPMENT_RESULT_HASHES["regime_g_001_result_hash"],
        ),
        "development_registry": (
            "family_g_development_registry_hash",
            DEVELOPMENT_RESULT_HASHES["family_g_development_registry_hash"],
        ),
        "development_manifest": (
            "family_g_development_evaluation_manifest_hash",
            DEVELOPMENT_RESULT_HASHES[
                "family_g_development_evaluation_manifest_hash"
            ],
        ),
    }
    checks: dict[str, bool] = {}
    for name, (field, expected) in semantic_specs.items():
        document = documents[name]
        checks[f"{name}_stored_hash_exact"] = document.get(field) == expected
        checks[f"{name}_canonical_hash_exact"] = (
            _document_hash(document, field) == expected
        )

    architecture = documents["architecture_manifest"]
    prehistory_manifest = documents["prehistory_manifest"]
    development_manifest = documents["development_manifest"]
    summary = documents["development_summary"]
    control = documents["control_result"]
    treatment = documents["treatment_result"]
    checks.update(
        {
            "treatment_parameter_stored_hash_exact": (
                documents["treatment_parameter"].get(
                    "regime_g_001_parameter_hash"
                )
                == FAMILY_G_FROZEN_HASHES["regime_g_001_parameter_hash"]
            ),
            "treatment_parameter_canonical_hash_exact": (
                canonical_hash(documents["treatment_parameter"].get("parameters"))
                == FAMILY_G_FROZEN_HASHES["regime_g_001_parameter_hash"]
            ),
            "architecture_frozen_hashes_exact": all(
                architecture.get(key) == value
                for key, value in FAMILY_G_FROZEN_HASHES.items()
            ),
            "architecture_artifacts_unchanged": _verify_manifest_artifacts(
                root, architecture
            ),
            "prehistory_frozen_hashes_exact": (
                prehistory_manifest.get("family_g_frozen_hashes")
                == {
                    key: value
                    for key, value in FAMILY_G_FROZEN_HASHES.items()
                    if key != "governance_policy_hash"
                }
            ),
            "prehistory_generated_hashes_exact": (
                prehistory_manifest.get("generated_hashes")
                == {
                    key: value
                    for key, value in PREHISTORY_HASHES.items()
                    if key != "family_g_benchmark_prehistory_manifest_hash"
                }
            ),
            "prehistory_artifacts_unchanged": _verify_manifest_artifacts(
                root, prehistory_manifest
            ),
            "development_frozen_hashes_exact": (
                development_manifest.get("family_g_frozen_hashes")
                == {
                    key: value
                    for key, value in FAMILY_G_FROZEN_HASHES.items()
                    if key != "governance_policy_hash"
                }
            ),
            "development_prehistory_hashes_exact": (
                development_manifest.get("prehistory_hashes")
                == {
                    key: value
                    for key, value in PREHISTORY_HASHES.items()
                    if key != "family_g_benchmark_prehistory_manifest_hash"
                }
            ),
            "development_result_hashes_exact": (
                development_manifest.get("result_hashes")
                == {
                    key: value
                    for key, value in DEVELOPMENT_RESULT_HASHES.items()
                    if key != "family_g_development_evaluation_manifest_hash"
                }
            ),
            "development_artifacts_unchanged": _verify_manifest_artifacts(
                root, development_manifest
            ),
            "development_result_mixed": (
                summary.get("classifications", {}).get("FAMILY_G_DEVELOPMENT_RESULT")
                == "MIXED"
            ),
            "treatment_partially_supported": (
                treatment.get("development_result") == "PARTIALLY_SUPPORTED"
                and summary.get("classifications", {}).get(
                    "REGIME_G_001_DEVELOPMENT_RESULT"
                )
                == "PARTIALLY_SUPPORTED"
            ),
            "next_stage_pause": (
                summary.get("classifications", {}).get(
                    "FAMILY_G_NEXT_RESEARCH_STAGE"
                )
                == "PAUSE_FAMILY_G"
            ),
            "control_reproduction_passed": (
                control.get("reproduction", {}).get("status") == "PASS"
            ),
            "validation_not_accessed": (
                control.get("validation_accessed") is False
                and treatment.get("validation_accessed") is False
                and development_manifest.get("validation_accessed") is False
            ),
            "strategy_v2_not_created": (
                development_manifest.get("strategy_v2_created") is False
            ),
            "command_03_final_verification_ready": (
                development_manifest.get("verification", {}).get("ready_for_review")
                is True
            ),
        }
    )
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        _input_mismatch(f"failed checks: {failed}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "family_g_frozen_hashes": FAMILY_G_FROZEN_HASHES,
        "prehistory_hashes": PREHISTORY_HASHES,
        "development_result_hashes": DEVELOPMENT_RESULT_HASHES,
    }


def _prior_artifact_paths(root: Path) -> list[Path]:
    root = Path(root).resolve()
    paths = _input_paths(root)
    prior: set[Path] = set(paths.values())
    for manifest_name in (
        "architecture_manifest",
        "prehistory_manifest",
        "development_manifest",
    ):
        manifest = _read_json(paths[manifest_name])
        prior.update(root / relative for relative in manifest["artifact_hashes"])
    prior.update(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_g_regime_volatility.py",
            "backend/app/research/strategy/family_g_benchmark_prehistory.py",
            "backend/app/research/strategy/family_g_development_evaluation.py",
            "backend/scripts/run_family_g_regime_volatility.py",
            "backend/scripts/run_family_g_benchmark_prehistory.py",
            "backend/scripts/run_family_g_development_evaluation.py",
            "backend/tests/test_family_g_regime_volatility.py",
            "backend/tests/test_family_g_benchmark_prehistory.py",
            "backend/tests/test_family_g_development_evaluation.py",
        )
    )
    return sorted(path.resolve() for path in prior if path.is_file())


def prior_artifact_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in _prior_artifact_paths(root)
    }
    return {
        "artifact_count": len(hashes),
        "artifact_hashes": hashes,
        "snapshot_hash": canonical_hash(hashes),
    }


def _assert_exact_metrics(
    control: Mapping[str, Any], treatment: Mapping[str, Any], summary: Mapping[str, Any]
) -> None:
    expected_control = {
        "net_ending_equity": "955331.6799",
        "net_total_return_pct": "91.0663359800",
        "net_cagr_pct": "24.105850672292473",
        "net_max_drawdown_pct": "-22.92216992201015671886716806",
        "net_annualized_volatility_pct": "21.225518024865917",
        "net_sharpe_like": "1.1423662151622573",
        "total_cost": "17629.90",
    }
    expected_treatment = {
        "net_ending_equity": "701280.9627",
        "net_total_return_pct": "40.2561925400",
        "net_cagr_pct": "11.945736746483359",
        "net_max_drawdown_pct": "-30.72712578084777096151980811",
        "net_annualized_volatility_pct": "20.2948146190893",
        "net_sharpe_like": "0.6681925214711923",
        "total_cost": "13970.53",
    }
    if any(control.get(key) != value for key, value in expected_control.items()):
        _input_mismatch("CONTROL-G-000 frozen metrics changed")
    if any(treatment.get(key) != value for key, value in expected_treatment.items()):
        _input_mismatch("REGIME-G-001 frozen metrics changed")
    attribution = summary.get("attribution", {})
    expected_cash_quarters = [
        ("2022-06-30", "13.77159596075032505853906660", "MISSED_GAIN"),
        ("2023-03-31", "19.97507308961838985613335600", "MISSED_GAIN"),
    ]
    observed = [
        (row.get("rebalance_date"), row.get("control_return_pct"), row.get("classification"))
        for row in attribution.get("cash_quarters", [])
    ]
    if observed != expected_cash_quarters:
        _input_mismatch("missed-gain evidence changed")
    path_effect = attribution.get("path_effect", {})
    expected_path = {
        "direct_gate_effect_rupees": "-262351.7854122956219083635528",
        "capital_path_effect_rupees": "8301.0682122956219083635528",
        "actual_treatment_minus_control_rupees": "-254050.7172",
    }
    if any(path_effect.get(key) != value for key, value in expected_path.items()):
        _input_mismatch("direct or capital-path attribution changed")
    expected_other = {
        "relative_drawdown_improvement_pct": "-34.04981241040010426169685913",
        "cost_reduction_rupees": "3659.37",
        "cost_reduction_pct": "20.75661234607116319434596906",
    }
    observed_other = {
        "relative_drawdown_improvement_pct": summary.get("criteria", {}).get(
            "relative_drawdown_improvement_pct"
        ),
        "cost_reduction_rupees": attribution.get("cost_reduction_rupees"),
        "cost_reduction_pct": attribution.get("cost_reduction_pct"),
    }
    if observed_other != expected_other:
        _input_mismatch("drawdown or cost attribution changed")


def evidence_document(summary: Mapping[str, Any]) -> dict[str, Any]:
    control = summary["control"]["metrics"]
    treatment = summary["treatment"]["metrics"]
    _assert_exact_metrics(control, treatment, summary)
    return {
        "version": "FAMILY_G_CLOSURE_EVIDENCE_V1",
        "family_version": FAMILY_VERSION,
        "development_result": "MIXED",
        "control": {
            "experiment_id": "CONTROL-G-000",
            "final_status": CONTROL_G_000_FINAL_STATUS,
            "reference_experiment_id": "MOM-A-002",
            "implementation_reference": "A2-002",
            "starting_capital_rupees": "500000",
            "net_ending_equity_rupees": control["net_ending_equity"],
            "net_return_pct": control["net_total_return_pct"],
            "net_cagr_pct": control["net_cagr_pct"],
            "max_drawdown_magnitude_pct": control["net_max_drawdown_pct"].lstrip("-"),
            "annualized_volatility_pct": control["net_annualized_volatility_pct"],
            "sharpe_like": control["net_sharpe_like"],
            "evidence_scope": "DEVELOPMENT_ONLY_NOT_VALIDATED",
        },
        "treatment": {
            "experiment_id": "REGIME-G-001",
            "final_status": REGIME_G_001_FINAL_STATUS,
            "development_result": "PARTIALLY_SUPPORTED",
            "gate_pass_count": summary["treatment"]["gate_pass_count"],
            "gate_fail_count": summary["treatment"]["gate_fail_count"],
            "net_ending_equity_rupees": treatment["net_ending_equity"],
            "net_return_pct": treatment["net_total_return_pct"],
            "net_cagr_pct": treatment["net_cagr_pct"],
            "max_drawdown_magnitude_pct": treatment["net_max_drawdown_pct"].lstrip("-"),
            "annualized_volatility_pct": treatment["net_annualized_volatility_pct"],
            "sharpe_like": treatment["net_sharpe_like"],
            "return_preservation": "FAILED",
            "drawdown_objective": "FAILED",
            "profitability": "PASSED",
            "temporal_support": "PASSED",
            "costs": "PASSED",
            "sample": "PASSED",
            "accounting": "PASSED",
            "lower_volatility_quality_dimension": "PASSED",
            "advanced": False,
        },
        "family_a_preservation": {
            "finding": (
                "Family G failure does not weaken the previously observed Family A "
                "DEVELOPMENT evidence."
            ),
            "independent_reproduction": (
                "CONTROL-G-000 reproduced the Family A INR 500,000 quarterly "
                "momentum architecture."
            ),
            "family_a_evidence_upgraded_to_validated": False,
        },
    }


def negative_evidence_document(summary: Mapping[str, Any]) -> dict[str, Any]:
    _assert_exact_metrics(
        summary["control"]["metrics"], summary["treatment"]["metrics"], summary
    )
    path_effect = summary["attribution"]["path_effect"]
    return {
        "version": "FAMILY_G_NEGATIVE_EVIDENCE_V1",
        "evidence_id": NEGATIVE_EVIDENCE_ID,
        "status": NEGATIVE_EVIDENCE_STATUS,
        "finding": (
            "A quarterly NIFTY 500 close>SMA200 gate applied to the frozen Family A "
            "6M momentum strategy failed to preserve return and failed to improve "
            "drawdown."
        ),
        "tested_design": {
            "decision_frequency": "QUARTERLY",
            "market_index": "NIFTY_500",
            "gate": "CLOSE_ABOVE_SMA200",
            "participation": "ALL_IN_OR_ALL_CASH",
            "treatment_count": 1,
        },
        "missed_gain_intervals": summary["attribution"]["cash_quarters"],
        "DIRECT_GATE_EFFECT": DIRECT_GATE_EFFECT,
        "direct_gate_effect_rupees": path_effect["direct_gate_effect_rupees"],
        "direct_gate_effect_reason": "BOTH_EXCLUDED_CONTROL_INTERVALS_WERE_PROFITABLE",
        "CAPITAL_PATH_EFFECT": CAPITAL_PATH_EFFECT,
        "capital_path_effect_rupees": path_effect["capital_path_effect_rupees"],
        "final_treatment_minus_control_rupees": path_effect[
            "actual_treatment_minus_control_rupees"
        ],
        "generalization_prohibited": [
            "SMA200_NEVER_WORKS",
            "MARKET_REGIME_FILTERS_NEVER_WORK",
        ],
        "scope": (
            "Only the frozen quarterly NIFTY 500 close>SMA200 all-in/all-cash "
            "participation design was evaluated."
        ),
    }


def lesson_document(summary: Mapping[str, Any]) -> dict[str, Any]:
    control = summary["control"]["metrics"]
    treatment = summary["treatment"]["metrics"]
    _assert_exact_metrics(control, treatment, summary)
    path_effect = summary["attribution"]["path_effect"]
    return {
        "version": FAMILY_G_RESEARCH_LESSON_VERSION,
        "primary_lesson": (
            "The tested quarterly NIFTY 500 close-above-SMA200 participation gate "
            "reduced exposure but did not improve the Family A momentum strategy. "
            "It materially reduced return and worsened max drawdown because the two "
            "excluded quarters were profitable control intervals. Conclusions apply "
            "only to the frozen quarterly SMA200 participation design."
        ),
        "direct_gate_lesson": {
            "status": DIRECT_GATE_EFFECT,
            "normalized_effect_rupees": path_effect["direct_gate_effect_rupees"],
            "reason": "BOTH_EXCLUDED_CONTROL_INTERVALS_WERE_PROFITABLE",
        },
        "capital_path_lesson": {
            "status": CAPITAL_PATH_EFFECT,
            "offset_rupees": path_effect["capital_path_effect_rupees"],
            "final_ending_equity_gap_rupees": path_effect[
                "actual_treatment_minus_control_rupees"
            ],
        },
        "drawdown_lesson": {
            "control_max_drawdown_magnitude_pct": control[
                "net_max_drawdown_pct"
            ].lstrip("-"),
            "treatment_max_drawdown_magnitude_pct": treatment[
                "net_max_drawdown_pct"
            ].lstrip("-"),
            "relative_change_pct": "34.04981241040010426169685913",
            "result": "WORSENED",
            "conclusion": (
                "This specific gate did not function as a successful drawdown-control overlay."
            ),
        },
        "cost_lesson": {
            "treatment_cost_reduction_rupees": summary["attribution"][
                "cost_reduction_rupees"
            ],
            "treatment_cost_reduction_pct": summary["attribution"][
                "cost_reduction_pct"
            ],
            "conclusion": (
                "Lower costs did not compensate for missed profitable exposure."
            ),
        },
        "volatility_lesson": {
            "control_annualized_volatility_pct": control[
                "net_annualized_volatility_pct"
            ],
            "treatment_annualized_volatility_pct": treatment[
                "net_annualized_volatility_pct"
            ],
            "control_sharpe_like": control["net_sharpe_like"],
            "treatment_sharpe_like": treatment["net_sharpe_like"],
            "conclusion": (
                "Reduced volatility alone is insufficient evidence of improved "
                "risk-adjusted performance."
            ),
        },
        "shared_infrastructure_preserved": PREHISTORY_INFRASTRUCTURE,
        "attribution_artifacts_preserved": [
            "QUARTERLY_LEDGER",
            "CASH_QUARTER_ATTRIBUTION",
            "PATH_EFFECT_ANALYSIS",
            "DRAWDOWN_ATTRIBUTION",
            "COST_TURNOVER_ANALYSIS",
            "NORMALIZED_QUARTER_DIAGNOSTIC",
        ],
    }


def governance_document() -> dict[str, Any]:
    prohibited_incremental_variants = [
        "SMA150",
        "SMA250",
        "NIFTY50_INSTEAD_OF_NIFTY500",
        "MONTHLY_INSTEAD_OF_QUARTERLY",
        "VIX_THRESHOLD",
        "BREADTH_THRESHOLD",
        "MULTIPLE_REGIME_SCORE",
        "PARTIAL_EXPOSURE_PERCENTAGES",
    ]
    return {
        "version": "FAMILY_G_CLOSURE_GOVERNANCE_V1",
        "statuses": {
            "CONTROL_G_000_FINAL_STATUS": CONTROL_G_000_FINAL_STATUS,
            "REGIME_G_001_FINAL_STATUS": REGIME_G_001_FINAL_STATUS,
            "FAMILY_G_RESEARCH_STATUS": FAMILY_G_RESEARCH_STATUS,
            "FAMILY_G_EVIDENCE_STATUS": FAMILY_G_EVIDENCE_STATUS,
            "FAMILY_G_VALIDATION_STATUS": FAMILY_G_VALIDATION_STATUS,
            "FAMILY_G_STRATEGY_V2_STATUS": FAMILY_G_STRATEGY_V2_STATUS,
        },
        "FAMILY_G_FUTURE_RESEARCH_POLICY": FAMILY_G_FUTURE_RESEARCH_POLICY,
        "resume_rule": (
            "A future Family G study requires a genuinely new, independently "
            "justified regime architecture and a new preregistration."
        ),
        "incremental_variants_not_authorized": prohibited_incremental_variants,
        "performance_rerun": False,
        "new_treatment_created": False,
        "parameters_changed": False,
        "benchmark_changed": False,
        "sma_changed": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "cross_family_synthesis_performed": False,
        "new_family_started": False,
    }


def handoff_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_G_CROSS_FAMILY_HANDOFF_V1",
        "STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS": (
            STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS
        ),
        "cycle_meaning": "PLANNED_A_TO_G_DISCOVERY_PASS_COMPLETE",
        "production_strategy_selected": False,
        "NEXT_PLANNED_PHASE": NEXT_PLANNED_PHASE,
        "status": "PLANNING_NOTE_ONLY",
        "purpose": [
            "COMPARE_FAMILIES_A_TO_G",
            "IDENTIFY_STRONGEST_REUSABLE_EVIDENCE",
            "SEPARATE_POSITIVE_NEGATIVE_AND_DATA_BLOCKED_FINDINGS",
            "DECIDE_WHETHER_ANY_CANDIDATE_MERITS_VALIDATION_DESIGN",
            "DETERMINE_WHETHER_A_GENUINELY_NEW_FAMILY_IS_JUSTIFIED",
        ],
        "cross_family_synthesis_performed": False,
        "validation_design_created": False,
        "new_family_started": False,
    }


def _component_paths(root: Path) -> dict[str, Path]:
    base = output_root(root)
    reports = Path(root) / "data/reports"
    return {
        "evidence": base / "evidence/family_g_closure_evidence_v1.json",
        "negative_evidence": (
            base / "evidence/family_g_negative_evidence_v1.json"
        ),
        "lesson": base / "lessons/family_g_research_lesson_v1.json",
        "governance": base / "governance/family_g_closure_governance_v1.json",
        "handoff": (
            base / "handoff/family_g_cross_family_synthesis_handoff_v1.json"
        ),
        "evidence_report": reports / REPORT_NAMES[1],
        "negative_evidence_report": reports / REPORT_NAMES[2],
        "lessons_report": reports / REPORT_NAMES[3],
        "handoff_report": reports / REPORT_NAMES[4],
        "documentation": Path(root) / "docs/strategy-family-g-closure-v1.md",
        "roadmap": Path(root) / "docs/strategy-family-research-roadmap-v1.md",
    }


def _verify_roadmap(root: Path) -> None:
    roadmap = (Path(root) / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    directions = {
        "family_A": ("Family A", "Medium-Term Momentum"),
        "family_B": ("Family B", "Relative + Absolute Momentum"),
        "family_C": ("Family C", "Breakout Continuation"),
        "family_D": ("Family D", "Opening Range / Stocks-in-Play"),
        "family_E": ("Family E", "Pullback / Reclaim"),
        "family_F": ("Family F", "Catalyst Momentum"),
        "family_G": ("Family G", "Regime / Volatility"),
    }
    missing = []
    for key, status in ROADMAP_STATUSES.items():
        family, direction = directions[key]
        row = f"| {family} | {direction} | {status} |"
        if row not in roadmap:
            missing.append(row)
    for marker in (
        f"STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS = {STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS}",
        f"NEXT_PLANNED_PHASE = {NEXT_PLANNED_PHASE}",
    ):
        if marker not in roadmap:
            missing.append(marker)
    if missing:
        _input_mismatch(f"roadmap closure state missing: {missing}")


def _write_immutable_manifest(path: Path, document: Mapping[str, Any]) -> None:
    if path.is_file():
        if _read_json(path) != document:
            raise FamilyGClosureImmutabilityError(
                f"Refusing to overwrite immutable Family G closure manifest: {path}"
            )
        return
    write_json(path, document)


def build_family_g_research_closure(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    input_verification = verify_closure_inputs(root)
    _verify_roadmap(root)
    prior_before = prior_artifact_snapshot(root)
    inputs = _input_paths(root)
    development_summary = _read_json(inputs["development_summary"])
    evidence = evidence_document(development_summary)
    negative = negative_evidence_document(development_summary)
    lesson = lesson_document(development_summary)
    governance = governance_document()
    handoff = handoff_document()
    paths = _component_paths(root)

    for key, document in (
        ("evidence", evidence),
        ("negative_evidence", negative),
        ("lesson", lesson),
        ("governance", governance),
        ("handoff", handoff),
    ):
        write_json(paths[key], document)

    reports = root / "data/reports"
    write_csv(
        paths["evidence_report"],
        [
            {
                "evidence_id": "CONTROL-G-000",
                "evidence_type": "STRONG_REFERENCE_CONTROL",
                "final_status": CONTROL_G_000_FINAL_STATUS,
                "development_result": "REFERENCE_REPRODUCED",
                "net_return_pct": evidence["control"]["net_return_pct"],
                "net_cagr_pct": evidence["control"]["net_cagr_pct"],
                "max_drawdown_magnitude_pct": evidence["control"][
                    "max_drawdown_magnitude_pct"
                ],
                "advanced": False,
                "validation_status": FAMILY_G_VALIDATION_STATUS,
            },
            {
                "evidence_id": "REGIME-G-001",
                "evidence_type": "FROZEN_TREATMENT",
                "final_status": REGIME_G_001_FINAL_STATUS,
                "development_result": "PARTIALLY_SUPPORTED",
                "net_return_pct": evidence["treatment"]["net_return_pct"],
                "net_cagr_pct": evidence["treatment"]["net_cagr_pct"],
                "max_drawdown_magnitude_pct": evidence["treatment"][
                    "max_drawdown_magnitude_pct"
                ],
                "advanced": False,
                "validation_status": FAMILY_G_VALIDATION_STATUS,
            },
        ],
    )
    write_csv(
        paths["negative_evidence_report"],
        [
            {
                "evidence_id": NEGATIVE_EVIDENCE_ID,
                "status": NEGATIVE_EVIDENCE_STATUS,
                "finding": negative["finding"],
                "DIRECT_GATE_EFFECT": DIRECT_GATE_EFFECT,
                "direct_gate_effect_rupees": negative[
                    "direct_gate_effect_rupees"
                ],
                "CAPITAL_PATH_EFFECT": CAPITAL_PATH_EFFECT,
                "capital_path_effect_rupees": negative[
                    "capital_path_effect_rupees"
                ],
                "final_treatment_minus_control_rupees": negative[
                    "final_treatment_minus_control_rupees"
                ],
                "missed_gain_interval_count": len(
                    negative["missed_gain_intervals"]
                ),
                "validation_status": FAMILY_G_VALIDATION_STATUS,
            }
        ],
    )
    write_csv(
        paths["lessons_report"],
        [
            {
                "lesson_id": "PRIMARY",
                "status": FAMILY_G_EVIDENCE_STATUS,
                "finding": lesson["primary_lesson"],
            },
            {
                "lesson_id": "DIRECT_GATE_EFFECT",
                "status": DIRECT_GATE_EFFECT,
                "finding": lesson["direct_gate_lesson"]["reason"],
            },
            {
                "lesson_id": "CAPITAL_PATH_EFFECT",
                "status": CAPITAL_PATH_EFFECT,
                "finding": "OFFSET_DID_NOT_CLOSE_FINAL_EQUITY_GAP",
            },
            {
                "lesson_id": "DRAWDOWN",
                "status": lesson["drawdown_lesson"]["result"],
                "finding": lesson["drawdown_lesson"]["conclusion"],
            },
            {
                "lesson_id": "COST",
                "status": "LOWER_NOT_DECISIVE",
                "finding": lesson["cost_lesson"]["conclusion"],
            },
            {
                "lesson_id": "VOLATILITY",
                "status": "LOWER_WITH_WORSE_SHARPE_LIKE",
                "finding": lesson["volatility_lesson"]["conclusion"],
            },
        ],
    )
    write_csv(
        paths["handoff_report"],
        [
            {
                "cycle_status": STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS,
                "next_planned_phase": NEXT_PLANNED_PHASE,
                "status": handoff["status"],
                "production_strategy_selected": False,
                "synthesis_performed": False,
                "validation_design_created": False,
                "new_family_started": False,
            }
        ],
    )

    prior_after = prior_artifact_snapshot(root)
    if prior_after != prior_before:
        raise FamilyGClosureImmutabilityError(
            "Prior Family G Command 01-03 artifacts changed during closure"
        )
    component_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in paths.values()
    }
    timestamp = utc_now()
    statuses = governance["statuses"]
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "family_profile": FAMILY_PROFILE,
        "closure_timestamp": timestamp,
        "input_verification": input_verification,
        "family_g_frozen_hashes": FAMILY_G_FROZEN_HASHES,
        "prehistory_hashes": PREHISTORY_HASHES,
        "development_result_hashes": DEVELOPMENT_RESULT_HASHES,
        "statuses": statuses,
        "negative_evidence": negative,
        "lessons": lesson,
        "future_research_policy": FAMILY_G_FUTURE_RESEARCH_POLICY,
        "shared_infrastructure_preserved": PREHISTORY_INFRASTRUCTURE,
        "roadmap": ROADMAP_STATUSES,
        "strategy_discovery_cycle_status": (
            STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS
        ),
        "handoff": handoff,
        "prior_command_artifact_snapshot": prior_after,
        "component_hashes": component_hashes,
        "safety": {
            "network_accessed": False,
            "performance_rerun": False,
            "new_treatment_created": False,
            "parameters_changed": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "cross_family_synthesis_performed": False,
            "new_family_started": False,
            "credentials_written": False,
            "external_writes": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "database_writes": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    manifest = {
        **manifest_body,
        "family_g_closure_hash": canonical_hash(manifest_body),
    }
    manifest_path = (
        output_root(root)
        / "manifest/family_g_research_closure_manifest_v1.json"
    )
    _write_immutable_manifest(manifest_path, manifest)

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": timestamp,
        "family_version": FAMILY_VERSION,
        "family_profile": FAMILY_PROFILE,
        "input_verification": input_verification,
        "statuses": statuses,
        "evidence": evidence,
        "negative_evidence": negative,
        "lessons": lesson,
        "governance": governance,
        "roadmap": ROADMAP_STATUSES,
        "handoff": handoff,
        "safety": manifest["safety"],
        "manifest": manifest_path.relative_to(root).as_posix(),
        "family_g_closure_hash": manifest["family_g_closure_hash"],
        "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        "documentation": "docs/strategy-family-g-closure-v1.md",
        "verification": manifest["verification"],
    }
    write_json(reports / REPORT_NAMES[0], summary)
    return summary


def finalize_family_g_research_closure(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = (
        output_root(root)
        / "manifest/family_g_research_closure_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    manifest = _read_json(manifest_path)
    values = (backend_targeted_tests, backend_full_tests, frontend_build)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": all(value.startswith("PASS") for value in values),
        "finalized_at": utc_now(),
    }
    manifest["verification"] = verification
    manifest["family_g_closure_hash"] = _document_hash(
        manifest, "family_g_closure_hash"
    )
    write_json(manifest_path, manifest)
    summary["verification"] = verification
    summary["family_g_closure_hash"] = manifest["family_g_closure_hash"]
    write_json(summary_path, summary)
    return summary


__all__ = [
    "COMMAND",
    "COMMAND_VERSION",
    "COMMAND_PROFILE",
    "MANIFEST_VERSION",
    "FAMILY_VERSION",
    "FAMILY_PROFILE",
    "CONTROL_G_000_FINAL_STATUS",
    "REGIME_G_001_FINAL_STATUS",
    "FAMILY_G_RESEARCH_STATUS",
    "FAMILY_G_EVIDENCE_STATUS",
    "FAMILY_G_VALIDATION_STATUS",
    "FAMILY_G_STRATEGY_V2_STATUS",
    "FAMILY_G_FUTURE_RESEARCH_POLICY",
    "FAMILY_G_RESEARCH_LESSON_VERSION",
    "NEGATIVE_EVIDENCE_ID",
    "NEGATIVE_EVIDENCE_STATUS",
    "DIRECT_GATE_EFFECT",
    "CAPITAL_PATH_EFFECT",
    "PREHISTORY_INFRASTRUCTURE",
    "STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS",
    "NEXT_PLANNED_PHASE",
    "FAMILY_G_FROZEN_HASHES",
    "PREHISTORY_HASHES",
    "DEVELOPMENT_RESULT_HASHES",
    "ROADMAP_STATUSES",
    "REPORT_NAMES",
    "verify_closure_inputs",
    "prior_artifact_snapshot",
    "evidence_document",
    "negative_evidence_document",
    "lesson_document",
    "governance_document",
    "handoff_document",
    "build_family_g_research_closure",
    "finalize_family_g_research_closure",
]

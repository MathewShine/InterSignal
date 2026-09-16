from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.research.strategy import family_a_one_shot_validation as validation
from app.research.strategy.family_a_momentum import (
    _load_aliases,
    _load_membership,
    file_sha256,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_validation_design import CONTAMINATION_DISCLOSURE
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.10 / Command 03"
COMMAND_VERSION = "FAMILY_A_POST_OUTCOME_REMEDIATED_VALIDATION_V1"
COMMAND_PROFILE = "MOM_A_002_CA_REMEDIATED_EVALUATION_V1"
AUTHORIZATION_VERSION = "FAMILY_A_POST_OUTCOME_REMEDIATED_AUTHORIZATION_V1"
MANIFEST_VERSION = "FAMILY_A_POST_OUTCOME_REMEDIATED_VALIDATION_MANIFEST_V1"
EVIDENCE_CLASS = "POST_OUTCOME_REMEDIATED_VALIDATION"

REQUIRED_CHECKPOINT = "a01023be642f1f3f5728bbc60b949e876cb9d1c3"
FORMAL_MANIFEST_HASH = "e3d2629077ac0de042e5599cbae8bc86279127e8556c85fed789600cc3f796c8"
FORMAL_RESULT_HASH = "be17598d2be97fc3c77f1e6e2efc2240a24451ddaa56037575c5a610221996e9"
ROOT_CAUSE_AUDIT_HASH = "a1892e805c7baf49c42534abe3c4800da721ec25bbc1de80e62fc1fc7bee6793"
CA_REMEDIATION_HASH = "ecdacd4dc4c348fe9002928fe37f78381e8833d2c5fb3cfa611e62237161db00"

PERMANENT_DISCLOSURE = (
    "This evaluation was performed after the original validation outcomes were "
    "observed and after a proven implementation defect was remediated. It is "
    "therefore post-outcome remediated evidence and must not be represented as "
    "pristine one-shot holdout validation."
)

EXPECTED_CANDIDATE_HASHES = {
    "family_a_family_config_hash": "becf703d7b21dee110165b469b2e1a3abd1cd64d4211ae41c6172554953be2e3",
    "mom_a_002_parameter_hash": "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8",
    "mom_a_002_preregistration_hash": "e88f8c2588b8c1ffb2fb5c951471f423d6b99d065ba135c58979c57f196f91cc",
    "a2_002_implementation_config_hash": "a391c2b46541af88b91b316bf2914bb15c6a11a7c5c9ff291d9f6c617bf8ae5b",
    "a2_002_preregistration_hash": "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897",
    "cost_config_hash": "9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48",
    "family_a_closure_hash": "51e2190c25f3146609ac173cc345e2a8adc0b6c9efb824633d735dc976581250",
    "candidate_identity_hash": "0e8ef3cc26d4146258f25fdd4c269867a383d2f098d9df0e367d4b0ff86beacc",
}

EXPECTED_DESIGN_HASHES = {
    "validation_design_hash": "8effd2ca6233c581d88aab46d16ff48b1aa04c0ce7648be11889c094d401a494",
    "validation_design_config_hash": "3c4c54f7a4c3e136d8f7e3a5dd395f81dd9aa768324056e4746db6a02dbcad43",
    "validation_schedule_hash": "42650a34a30d51f9817454cba938518ae9fbb84d180cdeff4e0fdf9d9bf771a7",
    "validation_success_criteria_hash": "89bec4f0b213c0b7a9bf8d1f67e0cf5c853fb3775e1ce9120bbb7933d1bc1ad4",
}

EXPECTED_STRUCTURAL_COUNTS = {
    "2024-12-31": (487, 13),
    "2025-03-28": (493, 7),
    "2025-06-30": (486, 14),
    "2025-09-30": (481, 19),
}

REPORT_NAMES = (
    "family_a_post_outcome_v1_summary.json",
    "family_a_post_outcome_v1_metrics.csv",
    "family_a_post_outcome_v1_intervals.csv",
    "family_a_post_outcome_v1_holdings.csv",
    "family_a_post_outcome_v1_costs.csv",
    "family_a_post_outcome_v1_criteria.csv",
    "family_a_post_outcome_v1_data_quality.csv",
    "family_a_post_outcome_v1_formal_comparison.csv",
    "family_a_post_outcome_v1_development_comparison.csv",
    "family_a_post_outcome_v1_review_status.csv",
)

RELEVANT_CHECKPOINT_PATHS = (
    "backend/app/research/strategy/family_a_momentum.py",
    "backend/app/research/strategy/family_a_development_backtest.py",
    "backend/app/research/strategy/family_a_validation_design.py",
    "backend/app/research/strategy/family_a_one_shot_validation.py",
    "backend/app/research/strategy/family_a_ca_lookback_remediation.py",
    "data/research/validation/family_a/v1/design",
    "data/research/validation/family_a/v1/evaluation",
    "data/research/validation/family_a/v1/post_validation_ca_audit",
    "data/research/validation/family_a/v1/ca_remediation",
)


class PostOutcomeRepositoryMismatch(RuntimeError):
    pass


class PostOutcomeGovernanceMismatch(RuntimeError):
    pass


class PostOutcomeSecondRunProhibited(RuntimeError):
    pass


def artifact_root(root: Path) -> Path:
    return Path(root) / "data/research/validation/family_a/v1/post_outcome_remediated"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def _verify_hashed_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _read_json(path)
    if document.get(field) != expected or _document_hash(document, field) != expected:
        raise PostOutcomeGovernanceMismatch(f"Governance artifact mismatch: {path}")
    return document


def verify_repository_checkpoint(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ancestry = _git(root, "merge-base", "--is-ancestor", REQUIRED_CHECKPOINT, "HEAD")
    relevant_committed = _git(
        root, "diff", "--quiet", REQUIRED_CHECKPOINT, "HEAD", "--", *RELEVANT_CHECKPOINT_PATHS
    )
    relevant_worktree = _git(root, "diff", "--quiet", "--", *RELEVANT_CHECKPOINT_PATHS)
    relevant_index = _git(root, "diff", "--cached", "--quiet", "--", *RELEVANT_CHECKPOINT_PATHS)
    checkpoint = {
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "head": head.stdout.strip(),
        "branch": branch.stdout.strip(),
        "upstream": upstream.stdout.strip(),
        "checkpoint_is_ancestor": ancestry.returncode == 0,
        "relevant_committed_changes_after_checkpoint": relevant_committed.returncode != 0,
        "relevant_worktree_changes": relevant_worktree.returncode != 0,
        "relevant_index_changes": relevant_index.returncode != 0,
        "status": "VERIFIED",
    }
    if (
        head.returncode
        or branch.returncode
        or upstream.returncode
        or not checkpoint["checkpoint_is_ancestor"]
        or checkpoint["branch"] != "main"
        or checkpoint["upstream"] != "origin/main"
        or checkpoint["relevant_committed_changes_after_checkpoint"]
        or checkpoint["relevant_worktree_changes"]
        or checkpoint["relevant_index_changes"]
    ):
        raise PostOutcomeRepositoryMismatch(
            f"POST_OUTCOME_REMEDIATED_VALIDATION_REPOSITORY_MISMATCH: {checkpoint}"
        )
    return checkpoint


def verify_governance_dependencies(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    formal_manifest = _verify_hashed_document(
        root
        / "data/research/validation/family_a/v1/evaluation/manifests/"
        "family_a_one_shot_validation_manifest_v1.json",
        "family_a_one_shot_validation_manifest_hash",
        FORMAL_MANIFEST_HASH,
    )
    formal_result = _verify_hashed_document(
        root
        / "data/research/validation/family_a/v1/evaluation/results/"
        "validation_result_v1.json",
        "family_a_validation_result_hash",
        FORMAL_RESULT_HASH,
    )
    audit = _verify_hashed_document(
        root
        / "data/research/validation/family_a/v1/post_validation_ca_audit/manifests/"
        "family_a_post_validation_ca_audit_manifest_v1.json",
        "family_a_post_validation_ca_audit_manifest_hash",
        ROOT_CAUSE_AUDIT_HASH,
    )
    remediation = _verify_hashed_document(
        root
        / "data/research/validation/family_a/v1/ca_remediation/manifests/"
        "family_a_ca_lookback_remediation_manifest_v1.json",
        "family_a_ca_lookback_remediation_manifest_hash",
        CA_REMEDIATION_HASH,
    )
    design = _read_json(root / "data/reports/family_a_validation_design_v1_summary.json")
    first_three = formal_result.get("completed_intervals", [])[:3]
    if not (
        formal_result.get("VALIDATION_RESULT") == "INCONCLUSIVE"
        and formal_result.get("FAMILY_A_GENERALIZATION_RESULT") == "INCONCLUSIVE"
        and formal_result.get("STRATEGY_V2_ADVANCEMENT_STATUS") == "NO_DECISION"
        and formal_result.get("completed_valid_formal_runs") == 1
        and formal_result.get("remaining_formal_runs") == 0
        and audit.get("root_cause") == "IMPLEMENTATION_LOGIC_DEFECT"
        and audit.get("severity") == "FATAL_TO_VALIDATION_INTEGRITY"
        and audit.get("fixability") == "CODE_FIX_ONLY"
        and formal_manifest.get("validation_design_hash")
        == EXPECTED_DESIGN_HASHES["validation_design_hash"]
        and formal_manifest.get("validation_design_config_hash")
        == EXPECTED_DESIGN_HASHES["validation_design_config_hash"]
        and design.get("schedule", {}).get("family_a_validation_schedule_hash")
        == EXPECTED_DESIGN_HASHES["validation_schedule_hash"]
        and design.get("success_criteria", {}).get(
            "family_a_validation_success_criteria_hash"
        )
        == EXPECTED_DESIGN_HASHES["validation_success_criteria_hash"]
        and formal_manifest.get("candidate_hashes") == EXPECTED_CANDIDATE_HASHES
        and len(first_three) == 3
        and all(row.get("candidate_count") == 0 for row in first_three)
        and remediation.get("technical_readiness", {}).get(
            "FAMILY_A_CA_REMEDIATION_RESULT"
        )
        == "FIX_VERIFIED_STRUCTURALLY"
        and remediation.get("technical_readiness", {}).get(
            "POST_OUTCOME_REMEDIATED_VALIDATION_TECHNICAL_READINESS"
        )
        == "YES"
    ):
        raise PostOutcomeGovernanceMismatch("Required governance state is not satisfied")
    return {
        "formal_manifest": formal_manifest,
        "formal_result": formal_result,
        "root_cause_audit": audit,
        "remediation": remediation,
    }


def verify_structural_remediation(remediation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = list(remediation["formation_date_structural_results"])
    by_date = {str(row["formation_date"]): row for row in rows}
    for formation, (eligible, excluded) in EXPECTED_STRUCTURAL_COUNTS.items():
        row = by_date.get(formation, {})
        if (
            row.get("ca_eligible_count") != eligible
            or row.get("ca_excluded_count") != excluded
            or row.get("lookback_session_count") != 126
            or row.get("no_lookback_start_count") != 0
        ):
            raise PostOutcomeGovernanceMismatch(
                f"POST_OUTCOME_REMEDIATED_VALIDATION_STRUCTURAL_MISMATCH: {formation}"
            )
    if any(
        row.get("lookback_session_count") != 126
        or row.get("no_lookback_start_count") != 0
        for row in rows
    ):
        raise PostOutcomeGovernanceMismatch(
            "POST_OUTCOME_REMEDIATED_VALIDATION_STRUCTURAL_MISMATCH"
        )
    return rows


def _formal_artifact_hashes(root: Path) -> dict[str, str]:
    root = Path(root).resolve()
    paths = list(
        (root / "data/research/validation/family_a/v1/evaluation").rglob("*")
    )
    paths.extend(
        root / "data/reports" / name for name in validation.REPORT_NAMES
    )
    files = sorted({path for path in paths if path.is_file()})
    if not files:
        raise PostOutcomeGovernanceMismatch("Original formal artifacts are missing")
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in files
    }


def _ensure_fresh_namespace(root: Path) -> None:
    destination = artifact_root(root)
    staging = destination.parent / ".post_outcome_remediated_staging_v1"
    reports = [Path(root) / "data/reports" / name for name in REPORT_NAMES]
    existing = [path for path in (destination, staging, *reports) if path.exists()]
    if existing:
        raise PostOutcomeSecondRunProhibited(
            "POST_OUTCOME_REMEDIATED_VALIDATION_ALREADY_EXISTS: "
            + ", ".join(str(path) for path in existing)
        )


def _verify_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = validation.build_candidate_configuration()
    if not (
        candidate.get("candidate_id") == "PROVISIONAL_VALIDATION_CANDIDATE_V1"
        and candidate.get("implementation_id") == "A2-002"
        and str(candidate.get("starting_capital_inr")) == "500000"
        and candidate.get("frozen_hashes") == EXPECTED_CANDIDATE_HASHES
        and candidate.get("candidate_parameter_changed") is False
    ):
        raise PostOutcomeGovernanceMismatch("Frozen candidate identity mismatch")
    body = {
        "evidence_class": EVIDENCE_CLASS,
        "source_candidate": candidate,
        "research_candidate_id": "MOM-A-002",
        "implementation_id": "A2-002",
        "candidate_identity_hash": EXPECTED_CANDIDATE_HASHES["candidate_identity_hash"],
        "candidate_parameter_changed": False,
    }
    return candidate, {
        **body,
        "family_a_post_outcome_candidate_hash": canonical_hash(body),
    }


def _build_input_snapshot(root: Path, original: Mapping[str, Any]) -> dict[str, Any]:
    source_paths = (
        "backend/app/research/strategy/family_a_momentum.py",
        "backend/app/research/strategy/family_a_development_backtest.py",
        "backend/app/research/strategy/family_a_validation_design.py",
        "backend/app/research/strategy/family_a_one_shot_validation.py",
        "backend/app/research/strategy/family_a_ca_lookback_remediation.py",
        "backend/app/research/strategy/family_a_post_outcome_remediated_validation.py",
    )
    body = {
        "evidence_class": EVIDENCE_CLASS,
        "performance_window": {
            "start": validation.VALIDATION_START.isoformat(),
            "end": validation.VALIDATION_END.isoformat(),
        },
        "causal_history_start": "2021-09-07",
        "causal_history_end": validation.VALIDATION_END.isoformat(),
        "last_loaded_date": original["last_loaded_date"],
        "post_holdout_files_loaded": original["post_holdout_files_loaded"],
        "adjusted_partition_count": original["adjusted_partition_count"],
        "static_file_count": original["static_file_count"],
        "frozen_data_file_hashes": original["file_hashes"],
        "execution_source_hashes": {
            path: file_sha256(root / path) for path in source_paths
        },
        "original_formal_input_snapshot_hash": original[
            "family_a_validation_input_snapshot_hash"
        ],
        "candidate_identity_hash": EXPECTED_CANDIDATE_HASHES["candidate_identity_hash"],
        "validation_design_hash": EXPECTED_DESIGN_HASHES["validation_design_hash"],
        "causal_prehistory_permitted_for_features_only": True,
        "performance_outside_window_permitted": False,
    }
    return {
        **body,
        "family_a_post_outcome_input_snapshot_hash": canonical_hash(body),
    }


def _build_authorization(
    checkpoint: Mapping[str, Any], candidate_hash: str, created_at: str
) -> dict[str, Any]:
    body = {
        "authorization_version": AUTHORIZATION_VERSION,
        "command": COMMAND,
        "authorized_at": created_at,
        "reason": "PROVEN_IMPLEMENTATION_DEFECT_REMOVED",
        "evidence_class": EVIDENCE_CLASS,
        "PRISTINE_HOLDOUT_EVIDENCE": "NO",
        "FORMAL_ONE_SHOT_REPLACEMENT": "NO",
        "prior_outcomes_known": "YES",
        "strategy_changed": "NO",
        "criteria_changed": "NO",
        "CA_rules_changed": "NO",
        "performance_window_changed": "NO",
        "root_cause_audit_hash": ROOT_CAUSE_AUDIT_HASH,
        "CA_remediation_hash": CA_REMEDIATION_HASH,
        "candidate_identity_hash": EXPECTED_CANDIDATE_HASHES["candidate_identity_hash"],
        "post_outcome_candidate_hash": candidate_hash,
        "validation_design_hash": EXPECTED_DESIGN_HASHES["validation_design_hash"],
        "formal_validation_manifest_hash": FORMAL_MANIFEST_HASH,
        "authorized_post_outcome_runs": 1,
        "post_outcome_run_number": 1,
        "repository_checkpoint": dict(checkpoint),
        "permanent_disclosure": PERMANENT_DISCLOSURE,
    }
    return {
        **body,
        "family_a_post_outcome_remediated_authorization_hash": canonical_hash(body),
    }


def _post_outcome_criteria(sealed: Mapping[str, Any]) -> dict[str, Any]:
    classification = str(sealed["VALIDATION_RESULT"])
    generalization = {
        "STRONG_PASS": "STRONGLY_SUPPORTIVE",
        "PASS": "SUPPORTIVE",
        "MIXED": "MIXED",
        "MIXED_LIMITED_SAMPLE": "MIXED",
        "FAIL": "UNSUPPORTIVE",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[classification]
    review = {
        "STRONG_PASS": "SUPPORTS_CANDIDATE_REVIEW",
        "PASS": "SUPPORTS_CANDIDATE_REVIEW",
        "MIXED": "FURTHER_GOVERNANCE_REQUIRED",
        "MIXED_LIMITED_SAMPLE": "FURTHER_GOVERNANCE_REQUIRED",
        "FAIL": "DOES_NOT_SUPPORT_CANDIDATE_REVIEW",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[classification]
    body = {
        "criteria_version": "FAMILY_A_POST_OUTCOME_REMEDIATED_CRITERIA_RESULT_V1",
        "evidence_class": EVIDENCE_CLASS,
        "sealed_design_hashes": EXPECTED_DESIGN_HASHES,
        "core_criteria_A_to_G": sealed["core_criteria"],
        "quality_dimensions_H_to_K": sealed["quality_dimensions"],
        "quality_pass_count": sealed["quality_pass_count"],
        "fatal_checks": sealed["fatal_checks"],
        "fatal_condition_triggered": sealed["fatal_condition_triggered"],
        "fatal_detail": sealed["fatal_detail"],
        "POST_OUTCOME_REMEDIATED_RESULT": classification,
        "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION": generalization,
        "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS": review,
        "criteria_changed": False,
        "candidate_parameter_changed": False,
        "strategy_v2_created": False,
        "source_sealed_classifier_output_hash": sealed[
            "family_a_validation_criteria_result_hash"
        ],
    }
    return {
        **body,
        "family_a_post_outcome_criteria_hash": canonical_hash(body),
    }


def _enhance_intervals(
    rows: Sequence[Mapping[str, Any]], formal_result: Mapping[str, Any]
) -> list[dict[str, Any]]:
    formal = {
        int(row["interval_number"]): row
        for row in formal_result["completed_intervals"]
    }
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        number = int(item["interval_number"])
        original = formal.get(number, {})
        symbols = sorted(dict(item.get("whole_share_quantities", {})))
        item["original_formal_candidate_count"] = original.get("candidate_count")
        item["newly_active_holdings"] = symbols if number <= 3 else []
        item["newly_active_holding_count"] = len(symbols) if number <= 3 else 0
        item["holding_change_context"] = (
            "ORIGINAL_FORMAL_UNIVERSE_STRUCTURALLY_DISABLED"
            if number <= 3
            else "NOT_APPLICABLE"
        )
        result.append(item)
    return result


def _formal_comparison_rows(
    formal_result: Mapping[str, Any], metrics: Mapping[str, Any], classification: str
) -> list[dict[str, Any]]:
    formal_metrics = formal_result["metrics"]
    rows = [
        {
            "metric": "classification",
            "original_formal": formal_result["VALIDATION_RESULT"],
            "post_outcome_remediated": classification,
            "interpretation": "SEPARATE_EVIDENCE_CLASSES_NO_REPLACEMENT",
        }
    ]
    for key in (
        "net_return_pct",
        "net_cagr_pct",
        "max_drawdown_magnitude_pct",
        "sharpe_like",
        "positive_completed_interval_count",
        "transaction_costs_inr",
        "average_holdings",
    ):
        rows.append(
            {
                "metric": key,
                "original_formal": formal_metrics[key],
                "post_outcome_remediated": metrics[key],
                "interpretation": (
                    "FIRST_THREE_FORMAL_INTERVALS_STRUCTURALLY_DISABLED; "
                    "REMEDIATED_RESULT_IS_NOT_INDEPENDENT_EVIDENCE"
                ),
            }
        )
    return rows


def _data_quality_rows(
    formation_rows: Sequence[Mapping[str, Any]], data_quality: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            **dict(row),
            "identity_mapping_unresolved_count": 0,
            "cash_reconciliation_violations": data_quality[
                "cash_reconciliation_violations"
            ],
            "equity_reconciliation_violations": data_quality[
                "equity_reconciliation_violations"
            ],
            "membership_caveat": data_quality["membership_reconstruction_caveat"],
        }
        for row in formation_rows
    ]


def _write_outputs(
    root: Path,
    *,
    authorization: Mapping[str, Any],
    input_snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any],
    schedule: Mapping[str, Any],
    selection_rows: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
    intervals: Sequence[Mapping[str, Any]],
    criteria: Mapping[str, Any],
    data_quality: Mapping[str, Any],
    result: Mapping[str, Any],
    manifest: Mapping[str, Any],
    formal_comparison: Sequence[Mapping[str, Any]],
    development_comparison: Sequence[Mapping[str, Any]],
    data_quality_rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    final = artifact_root(root)
    staging = final.parent / ".post_outcome_remediated_staging_v1"
    report_staging = staging / "_reports"
    write_json(staging / "authorization/authorization_record_v1.json", authorization)
    write_json(staging / "inputs/input_snapshot_v1.json", input_snapshot)
    write_json(staging / "inputs/candidate_configuration_v1.json", candidate)
    write_json(staging / "inputs/rebalance_schedule_v1.json", schedule)
    write_csv(staging / "inputs/candidate_selections_v1.csv", selection_rows)
    write_csv(staging / "holdings/post_outcome_holdings_v1.csv", simulation["holdings"])
    write_csv(staging / "ledgers/portfolio_daily_ledger_v1.csv", simulation["daily"])
    write_json(staging / "ledgers/primary_endpoint_v1.json", simulation["primary_endpoint"])
    write_csv(staging / "ledgers/rebalance_ledger_v1.csv", simulation["rebalances"])
    write_csv(staging / "ledgers/cost_ledger_v1.csv", simulation["costs"])
    write_csv(staging / "ledgers/interval_ledger_v1.csv", intervals)
    write_json(staging / "criteria/criteria_results_v1.json", criteria)
    write_json(staging / "results/post_outcome_result_v1.json", result)
    write_json(
        staging / "results/terminal_mark_to_market_diagnostic_v1.json",
        result["terminal_mark_to_market_diagnostic"],
    )
    write_json(staging / "results/data_quality_v1.json", data_quality)
    write_json(staging / "comparison/formal_comparison_v1.json", list(formal_comparison))
    write_csv(staging / "comparison/formal_comparison_v1.csv", formal_comparison)
    write_json(
        staging / "comparison/development_comparison_v1.json",
        list(development_comparison),
    )
    write_csv(staging / "comparison/development_comparison_v1.csv", development_comparison)
    write_json(
        staging / "manifests/family_a_post_outcome_remediated_validation_manifest_v1.json",
        manifest,
    )

    write_json(report_staging / REPORT_NAMES[0], summary)
    write_csv(report_staging / REPORT_NAMES[1], validation._metric_report_rows(result["metrics"]))
    write_csv(report_staging / REPORT_NAMES[2], intervals)
    write_csv(report_staging / REPORT_NAMES[3], simulation["holdings"])
    write_csv(report_staging / REPORT_NAMES[4], simulation["costs"])
    write_csv(
        report_staging / REPORT_NAMES[5],
        [
            {"criterion": key, **value}
            for key, value in criteria["core_criteria_A_to_G"].items()
        ]
        + [
            {"criterion": key, **value}
            for key, value in criteria["quality_dimensions_H_to_K"].items()
        ],
    )
    write_csv(report_staging / REPORT_NAMES[6], data_quality_rows)
    write_csv(report_staging / REPORT_NAMES[7], formal_comparison)
    write_csv(report_staging / REPORT_NAMES[8], development_comparison)
    write_csv(
        report_staging / REPORT_NAMES[9],
        [
            {
                "EVIDENCE_CLASS": EVIDENCE_CLASS,
                "PRISTINE_HOLDOUT_EVIDENCE": "NO",
                "FORMAL_ONE_SHOT_REPLACEMENT": "NO",
                "POST_OUTCOME_REMEDIATED_RESULT": criteria[
                    "POST_OUTCOME_REMEDIATED_RESULT"
                ],
                "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION": criteria[
                    "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"
                ],
                "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS": criteria[
                    "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"
                ],
                "strategy_v2_created": False,
            }
        ],
    )

    staging.replace(final)
    for source in list((final / "_reports").iterdir()):
        destination = root / "data/reports" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    (final / "_reports").rmdir()


def execute_post_outcome_remediated_validation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _ensure_fresh_namespace(root)
    checkpoint = verify_repository_checkpoint(root)
    dependencies = verify_governance_dependencies(root)
    structural_rows = verify_structural_remediation(dependencies["remediation"])
    formal_before = _formal_artifact_hashes(root)
    base_candidate, candidate = _verify_candidate()
    started_at = validation.utc_now()
    authorization = _build_authorization(
        checkpoint, candidate["family_a_post_outcome_candidate_hash"], started_at
    )
    original_input = validation._existing_input_snapshot(root)
    input_snapshot = _build_input_snapshot(root, original_input)

    causal_sessions, performance_sessions = validation.prepare_validation_session_windows(root)
    membership = _load_membership(root)
    aliases = _load_aliases(root)
    bars = validation._load_bounded_bars(root, set(membership.grouped), aliases)
    schedules, selection_rows, quality_rows = validation.build_validation_schedules(
        root, causal_sessions, bars
    )
    simulation = validation.simulate_validation_executable(
        schedules, performance_sessions, bars
    )
    analysis = validation.calculate_validation_metrics(simulation)
    sealed_criteria = validation.evaluate_criteria(
        analysis["metrics"], simulation, schedules, selection_rows, input_snapshot
    )
    criteria = _post_outcome_criteria(sealed_criteria)
    schedule = validation.build_rebalance_schedule_document(schedules)
    intervals = _enhance_intervals(
        validation.build_interval_ledger(simulation), dependencies["formal_result"]
    )
    sealed_data_quality = validation.build_data_quality(
        quality_rows, simulation, input_snapshot
    )
    data_quality_body = {
        **{
            key: value
            for key, value in sealed_data_quality.items()
            if key != "family_a_validation_data_quality_hash"
        },
        "evidence_class": EVIDENCE_CLASS,
        "source_sealed_data_quality_hash": sealed_data_quality[
            "family_a_validation_data_quality_hash"
        ],
        "identity_mapping_unresolved_count": 0,
        "structural_remediation_verified": True,
        "post_remediation_failure_scope": "NORMAL_SYMBOL_LEVEL_ELIGIBILITY",
    }
    data_quality = {
        **data_quality_body,
        "family_a_post_outcome_data_quality_hash": canonical_hash(data_quality_body),
    }

    if len(intervals[:6]) != 6 or any(
        row["scope"] != "PRIMARY" for row in intervals[:6]
    ):
        raise PostOutcomeGovernanceMismatch("Six completed primary intervals required")
    if not intervals[6]["scope"] == "TERMINAL_DIAGNOSTIC":
        raise PostOutcomeGovernanceMismatch("Terminal interval handling mismatch")

    formal_after = _formal_artifact_hashes(root)
    if formal_before != formal_after:
        raise PostOutcomeGovernanceMismatch("Original formal artifacts changed")

    metrics = analysis["metrics"]
    classification = criteria["POST_OUTCOME_REMEDIATED_RESULT"]
    formal_comparison = _formal_comparison_rows(
        dependencies["formal_result"], metrics, classification
    )
    development_comparison = validation._development_comparison_rows(metrics)
    quality_report_rows = _data_quality_rows(quality_rows, data_quality)
    portfolio_payload = {
        "daily": simulation["daily"],
        "primary_endpoint": simulation["primary_endpoint"],
    }
    result_hashes = {
        "family_a_post_outcome_authorization_hash": authorization[
            "family_a_post_outcome_remediated_authorization_hash"
        ],
        "family_a_post_outcome_input_snapshot_hash": input_snapshot[
            "family_a_post_outcome_input_snapshot_hash"
        ],
        "family_a_post_outcome_candidate_hash": candidate[
            "family_a_post_outcome_candidate_hash"
        ],
        "family_a_post_outcome_holdings_hash": canonical_hash(simulation["holdings"]),
        "family_a_post_outcome_portfolio_ledger_hash": canonical_hash(portfolio_payload),
        "family_a_post_outcome_cost_ledger_hash": canonical_hash(simulation["costs"]),
        "family_a_post_outcome_criteria_hash": criteria[
            "family_a_post_outcome_criteria_hash"
        ],
    }
    result_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "evaluated_at": started_at,
        "EVIDENCE_CLASS": EVIDENCE_CLASS,
        "PRISTINE_HOLDOUT_EVIDENCE": "NO",
        "FORMAL_ONE_SHOT_REPLACEMENT": "NO",
        "validation_window": {
            "start": validation.VALIDATION_START.isoformat(),
            "end": validation.VALIDATION_END.isoformat(),
        },
        "causal_history_window": {
            "start": causal_sessions[0].isoformat(),
            "end": causal_sessions[-1].isoformat(),
            "use": "CA_LOOKBACK_PERMITTED_FEATURE_HISTORY_AND_IDENTITY_CONTEXT_ONLY",
        },
        "primary_interval_end": validation.PRIMARY_END.isoformat(),
        "primary_completed_interval_count": 6,
        "terminal_interval_excluded_from_primary": True,
        "metrics": metrics,
        "completed_intervals": intervals[:6],
        "terminal_mark_to_market_diagnostic": analysis["terminal_diagnostic"],
        "data_quality": data_quality,
        "criteria": criteria,
        "POST_OUTCOME_REMEDIATED_RESULT": classification,
        "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION": criteria[
            "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"
        ],
        "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS": criteria[
            "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"
        ],
        "original_formal_record": {
            "manifest_hash": FORMAL_MANIFEST_HASH,
            "result_hash": FORMAL_RESULT_HASH,
            "VALIDATION_RESULT": "INCONCLUSIVE",
            "FAMILY_A_GENERALIZATION_RESULT": "INCONCLUSIVE",
            "STRATEGY_V2_ADVANCEMENT_STATUS": "NO_DECISION",
            "completed_formal_runs": 1,
            "remaining_formal_runs": 0,
            "overwritten_or_reinterpreted": False,
        },
        "formal_comparison": formal_comparison,
        "development_comparison": development_comparison,
        "permanent_post_outcome_disclosure": PERMANENT_DISCLOSURE,
        "original_contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "original_formal_artifacts_unchanged": True,
        "candidate_changed": False,
        "criteria_changed": False,
        "CA_rules_changed": False,
        "performance_window_changed": False,
        "strategy_v2_created": False,
        "post_outcome_run_number": 1,
        "additional_post_outcome_runs_authorized": 0,
        "result_hashes": result_hashes,
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
        },
    }
    result = {
        **result_body,
        "family_a_post_outcome_result_hash": canonical_hash(result_body),
    }
    result_hashes = {
        **result_hashes,
        "family_a_post_outcome_result_hash": result[
            "family_a_post_outcome_result_hash"
        ],
    }

    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": started_at,
        "EVIDENCE_CLASS": EVIDENCE_CLASS,
        "PRISTINE_HOLDOUT_EVIDENCE": "NO",
        "FORMAL_ONE_SHOT_REPLACEMENT": "NO",
        "original_formal_manifest_hash": FORMAL_MANIFEST_HASH,
        "original_formal_result_hash": FORMAL_RESULT_HASH,
        "root_cause_audit_hash": ROOT_CAUSE_AUDIT_HASH,
        "CA_remediation_hash": CA_REMEDIATION_HASH,
        "authorization_hash": authorization[
            "family_a_post_outcome_remediated_authorization_hash"
        ],
        "candidate_identity_hash": EXPECTED_CANDIDATE_HASHES["candidate_identity_hash"],
        "candidate_hashes": EXPECTED_CANDIDATE_HASHES,
        "design_criteria_hashes": EXPECTED_DESIGN_HASHES,
        "validation_window": result["validation_window"],
        "schedule": schedule["schedule"],
        "structural_eligibility": structural_rows,
        "performance_metrics": metrics,
        "core_criteria_A_to_G": criteria["core_criteria_A_to_G"],
        "quality_dimensions_H_to_K": criteria["quality_dimensions_H_to_K"],
        "POST_OUTCOME_REMEDIATED_RESULT": classification,
        "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION": criteria[
            "POST_OUTCOME_REMEDIATED_GENERALIZATION_INDICATION"
        ],
        "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS": criteria[
            "POST_OUTCOME_STRATEGY_V2_REVIEW_STATUS"
        ],
        "permanent_post_outcome_disclosure": PERMANENT_DISCLOSURE,
        "original_contamination_disclosure": CONTAMINATION_DISCLOSURE,
        "proof_original_formal_artifacts_unchanged": {
            "unchanged": True,
            "file_hashes_before": formal_before,
            "file_hashes_after": formal_after,
        },
        "result_hashes": result_hashes,
        "post_outcome_run_number": 1,
        "additional_post_outcome_runs_authorized": 0,
        "candidate_changed": False,
        "criteria_changed": False,
        "strategy_v2_created": False,
        "reports": list(REPORT_NAMES),
        "security": result["security"],
    }
    manifest = {
        **manifest_body,
        "family_a_post_outcome_remediated_validation_manifest_hash": canonical_hash(
            manifest_body
        ),
    }
    summary = {
        **result,
        "authorization": authorization,
        "input_snapshot": input_snapshot,
        "candidate": candidate,
        "source_candidate": base_candidate,
        "rebalance_schedule": schedule,
        "manifest_path": (
            artifact_root(root)
            / "manifests/family_a_post_outcome_remediated_validation_manifest_v1.json"
        ).relative_to(root).as_posix(),
        "manifest_hash": manifest[
            "family_a_post_outcome_remediated_validation_manifest_hash"
        ],
        "reports": list(REPORT_NAMES),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    _write_outputs(
        root,
        authorization=authorization,
        input_snapshot=input_snapshot,
        candidate=candidate,
        schedule=schedule,
        selection_rows=selection_rows,
        simulation=simulation,
        intervals=intervals,
        criteria=criteria,
        data_quality=data_quality,
        result=result,
        manifest=manifest,
        formal_comparison=formal_comparison,
        development_comparison=development_comparison,
        data_quality_rows=quality_report_rows,
        summary=summary,
    )
    return summary


def finalize_post_outcome_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    out = artifact_root(root)
    manifest = _read_json(
        out / "manifests/family_a_post_outcome_remediated_validation_manifest_v1.json"
    )
    result = _read_json(out / "results/post_outcome_result_v1.json")
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    if _document_hash(
        manifest, "family_a_post_outcome_remediated_validation_manifest_hash"
    ) != manifest.get("family_a_post_outcome_remediated_validation_manifest_hash"):
        raise PostOutcomeGovernanceMismatch("Immutable post-outcome manifest mismatch")
    if _document_hash(result, "family_a_post_outcome_result_hash") != result.get(
        "family_a_post_outcome_result_hash"
    ):
        raise PostOutcomeGovernanceMismatch("Immutable post-outcome result mismatch")
    current_formal = _formal_artifact_hashes(root)
    expected_formal = manifest["proof_original_formal_artifacts_unchanged"][
        "file_hashes_after"
    ]
    if current_formal != expected_formal:
        raise PostOutcomeGovernanceMismatch("Original formal artifacts changed")
    values = (
        backend_targeted_tests,
        backend_full_tests,
        frontend_build,
        regressions,
    )
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
        "ready_for_review": all(value.startswith("PASS") for value in values),
        "finalized_at": validation.utc_now(),
        "immutable_manifest_unchanged": True,
        "immutable_result_unchanged": True,
        "original_formal_artifacts_unchanged": True,
    }
    record_body = {
        "verification": verification,
        "manifest_hash": manifest[
            "family_a_post_outcome_remediated_validation_manifest_hash"
        ],
        "result_hash": result["family_a_post_outcome_result_hash"],
    }
    record = {
        **record_body,
        "family_a_post_outcome_verification_hash": canonical_hash(record_body),
    }
    verification_path = out / "results/verification_record_v1.json"
    if verification_path.exists():
        raise PostOutcomeSecondRunProhibited("Post-outcome verification already finalized")
    write_json(verification_path, record)
    summary["verification"] = verification
    write_json(summary_path, summary)
    return summary


__all__ = (
    "AUTHORIZATION_VERSION",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EVIDENCE_CLASS",
    "MANIFEST_VERSION",
    "PERMANENT_DISCLOSURE",
    "REPORT_NAMES",
    "PostOutcomeGovernanceMismatch",
    "PostOutcomeRepositoryMismatch",
    "PostOutcomeSecondRunProhibited",
    "artifact_root",
    "execute_post_outcome_remediated_validation",
    "finalize_post_outcome_review",
    "verify_governance_dependencies",
    "verify_repository_checkpoint",
    "verify_structural_remediation",
)

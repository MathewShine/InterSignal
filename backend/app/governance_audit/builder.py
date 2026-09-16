from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.platform.hashing import HASH_VERSION, canonical_hash, file_sha256, normalize_for_hash
from app.platform.repositories import JsonFilePlatformRepository
from app.portfolio_os.builder import PRIOR_ARTIFACT_PATHS as PRE_PORTFOLIO_PATHS
from app.portfolio_os.repositories import JsonFilePortfolioOSRepository
from app.governance_audit.models import (
    GovernanceIntegritySummary,
    GovernanceSnapshot,
    GovernanceViolation,
    IntegrityStatus,
    ReadinessType,
)
from app.governance_audit.repositories import JsonFileGovernanceRepository
from app.governance_audit.seeding import seed_current_governance_state
from app.governance_audit.service import GovernanceService


COMMAND = "Step 04.04 / Command 01"
COMMAND_VERSION = "INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_V1"
COMMAND_PROFILE = "POLICY_AUTHORIZATION_READINESS_AUDIT_V1"
MANIFEST_VERSION = "INTERSIGNAL_GOVERNANCE_AUDIT_FOUNDATION_MANIFEST_V1"
INTEGRITY_VERSION = "INTERSIGNAL_GOVERNANCE_AUDIT_INTEGRITY_V1"
REQUIRED_CHECKPOINT = "0f7936bd482b05758546b2ce58915a93aeab7e02"
PLATFORM_FOUNDATION_HASH = (
    "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
)
RESEARCH_WORKBENCH_HASH = (
    "c0c1ba634f584b4532e99e4f015be83e7e0c069eafb3cd5ca6a1fc7cfaf8f52b"
)
PORTFOLIO_OS_HASH = (
    "6941ae2713b707908106ffb8d50be113d181e9339fd3e030338b2da637f026de"
)

PORTFOLIO_SOURCE_PATHS = (
    "backend/app/portfolio_os/__init__.py",
    "backend/app/portfolio_os/accounting.py",
    "backend/app/portfolio_os/builder.py",
    "backend/app/portfolio_os/errors.py",
    "backend/app/portfolio_os/models.py",
    "backend/app/portfolio_os/repositories.py",
    "backend/app/portfolio_os/service.py",
    "backend/scripts/build_portfolio_os_foundation.py",
    "backend/tests/test_portfolio_os_foundation.py",
    "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json",
    "docs/portfolio-os-accounting-v1.md",
    "docs/portfolio-os-domain-model-v1.md",
    "docs/portfolio-os-risk-analytics-v1.md",
    "data/reports/portfolio_os_foundation_v1_summary.json",
    "data/reports/portfolio_os_foundation_v1_portfolios.csv",
    "data/reports/portfolio_os_foundation_v1_holdings.csv",
    "data/reports/portfolio_os_foundation_v1_transactions.csv",
    "data/reports/portfolio_os_foundation_v1_integrity.csv",
)

REPORT_NAMES = (
    "governance_audit_v1_summary.json",
    "governance_audit_v1_authorizations.csv",
    "governance_audit_v1_readiness.csv",
    "governance_audit_v1_policies.csv",
    "governance_audit_v1_violations.csv",
    "governance_audit_v1_timeline.csv",
    "governance_audit_v1_integrity.csv",
)
DOCUMENTATION_PATHS = (
    "docs/governance-audit-domain-v1.md",
    "docs/governance-policy-engine-v1.md",
    "docs/governance-authorization-readiness-v1.md",
)


class GovernanceAuditInputMismatch(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any] | object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            normalize_for_hash(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _portfolio_artifact_paths(root: Path) -> tuple[str, ...]:
    manifest = _read_json(
        root / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json"
    )
    return tuple(sorted(manifest["artifact_file_hashes"]))


def prior_artifact_paths(root: Path) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (*PRE_PORTFOLIO_PATHS, *PORTFOLIO_SOURCE_PATHS, *_portfolio_artifact_paths(root))
        )
    )


def _file_hashes(root: Path, paths: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise GovernanceAuditInputMismatch(f"Missing prior artifact: {relative}")
        values[relative] = file_sha256(path)
    return values


def verify_governance_audit_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git_head(root)
    if head != REQUIRED_CHECKPOINT:
        raise GovernanceAuditInputMismatch(
            f"Expected checkpoint {REQUIRED_CHECKPOINT}, found {head}"
        )
    platform = _read_json(
        root / "data/platform/manifests/intersignal_platform_foundation_manifest_v1.json"
    )
    if (
        platform.get("platform_foundation_hash") != PLATFORM_FOUNDATION_HASH
        or _document_hash(platform, "platform_foundation_hash") != PLATFORM_FOUNDATION_HASH
    ):
        raise GovernanceAuditInputMismatch("Step 04.01 hash mismatch")
    workbench = _read_json(
        root
        / "data/platform/manifests/intersignal_research_workbench_backend_manifest_v1.json"
    )
    if (
        workbench.get("research_workbench_backend_hash") != RESEARCH_WORKBENCH_HASH
        or _document_hash(workbench, "research_workbench_backend_hash")
        != RESEARCH_WORKBENCH_HASH
    ):
        raise GovernanceAuditInputMismatch("Step 04.02 hash mismatch")
    portfolio = _read_json(
        root / "data/platform/manifests/intersignal_portfolio_os_foundation_manifest_v1.json"
    )
    if (
        portfolio.get("portfolio_os_foundation_hash") != PORTFOLIO_OS_HASH
        or _document_hash(portfolio, "portfolio_os_foundation_hash") != PORTFOLIO_OS_HASH
    ):
        raise GovernanceAuditInputMismatch("Step 04.03 hash mismatch")
    research_state = _read_json(
        root / "data/platform/registry/current_research_snapshot_v1.json"
    )
    expected = {
        "strategy_research_programme": "PAUSED",
        "a_to_g": "COMPLETE_NO_VALIDATED_STRATEGY",
        "strategy_v2": "NOT_CREATED",
        "family_h": "NOT_PLANNED",
        "paper": "NOT_READY",
        "live": "NOT_READY",
        "production_candidate_count": 0,
        "validated_production_strategy_count": 0,
    }
    for key, value in expected.items():
        if research_state.get(key) != value:
            raise GovernanceAuditInputMismatch(
                f"Unexpected current research state for {key}: {research_state.get(key)}"
            )
    return {
        "head": head,
        "platform": platform,
        "workbench": workbench,
        "portfolio": portfolio,
        "research_state": research_state,
        "workbench_snapshot": _read_json(
            root / "data/platform/workbench/research_workbench_snapshot_v1.json"
        ),
    }


def _governance_artifact_hashes(root: Path) -> dict[str, str]:
    artifact_root = root / "data/platform/governance"
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(artifact_root.rglob("*"))
        if path.is_file()
    }


def _rows(models: Sequence[object], *, empty_fields: Sequence[str] = ()) -> tuple[tuple[str, ...], list[dict]]:
    output: list[dict] = []
    for model in models:
        row = model.model_dump(mode="json")
        for key, value in tuple(row.items()):
            if isinstance(value, (dict, list, tuple)):
                row[key] = _csv_value(value)
        output.append(row)
    if output:
        return tuple(output[0]), output
    return tuple(empty_fields), []


def _write_reports(
    root: Path,
    snapshot: GovernanceSnapshot,
    summary: dict[str, Any],
) -> None:
    reports = root / "data/reports"
    _write_json(reports / REPORT_NAMES[0], summary)
    groups = (
        (REPORT_NAMES[1], snapshot.authorizations, tuple()),
        (REPORT_NAMES[2], snapshot.readiness, tuple()),
        (REPORT_NAMES[3], snapshot.policies, tuple()),
        (
            REPORT_NAMES[4],
            snapshot.violations,
            tuple(GovernanceViolation.model_fields),
        ),
        (REPORT_NAMES[5], snapshot.audit_timeline, tuple()),
    )
    for name, models, empty_fields in groups:
        fields, rows = _rows(models, empty_fields=empty_fields)
        _write_csv(reports / name, fields, rows)
    integrity = snapshot.integrity.model_dump(mode="json")
    integrity["metadata"] = _csv_value(integrity["metadata"])
    _write_csv(reports / REPORT_NAMES[6], tuple(integrity), [integrity])


def build_governance_audit_foundation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    inputs = verify_governance_audit_inputs(root)
    protected = prior_artifact_paths(root)
    before = _file_hashes(root, protected)
    governance_root = root / "data/platform/governance"
    if governance_root.exists() and any(governance_root.rglob("*.jsonl")):
        raise GovernanceAuditInputMismatch(
            "Governance JSONL seed already exists; refusing duplicate append"
        )
    platform_repository = JsonFilePlatformRepository(root / "data/platform")
    portfolio_repository = JsonFilePortfolioOSRepository(
        root / "data/platform/portfolio_os"
    )
    portfolio_events = tuple(
        event
        for portfolio in portfolio_repository.list_portfolios()
        for event in portfolio_repository.list_portfolio_events(portfolio.portfolio_id)
    )
    repository = JsonFileGovernanceRepository(governance_root)
    service = GovernanceService.from_repository(
        repository,
        registry_events=tuple(platform_repository.list_events()),
        portfolio_events=portfolio_events,
        valid_artifact_ids={row.artifact_id for row in platform_repository.list_artifacts()},
        valid_evidence_ids={row.evidence_id for row in platform_repository.list_evidence()},
        valid_lineage_node_ids={row.node_id for row in platform_repository.list_lineage_nodes()},
    )
    seed_current_governance_state(
        service,
        platform_repository=platform_repository,
        portfolio_repository=portfolio_repository,
        workbench_snapshot=inputs["workbench_snapshot"],
        platform_foundation_hash=PLATFORM_FOUNDATION_HASH,
        research_workbench_hash=RESEARCH_WORKBENCH_HASH,
        portfolio_os_hash=PORTFOLIO_OS_HASH,
    )
    integrity = service.require_integrity()
    snapshot = service.export_governance_snapshot()
    _write_json(
        governance_root / "governance_snapshot_v1.json",
        snapshot.model_dump(mode="python"),
    )
    integrity_payload: dict[str, Any] = {
        "integrity_version": INTEGRITY_VERSION,
        "generated_at": snapshot.generated_at,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
        "portfolio_os_foundation_hash": PORTFOLIO_OS_HASH,
        "integrity": integrity.model_dump(mode="json"),
    }
    integrity_payload["integrity_hash"] = canonical_hash(integrity_payload)
    _write_json(
        governance_root / "governance_integrity_v1.json", integrity_payload
    )
    after = _file_hashes(root, protected)
    if before != after:
        raise GovernanceAuditInputMismatch(
            "Existing platform artifacts changed during governance build"
        )
    artifacts = _governance_artifact_hashes(root)
    summary_state = snapshot.summary
    counts = {
        "subjects": len(snapshot.subjects),
        "authorizations": len(snapshot.authorizations),
        "readiness_assessments": len(snapshot.readiness),
        "policies": len(snapshot.policies),
        "policy_evaluations": len(snapshot.policy_evaluations),
        "violations": len(snapshot.violations),
        "manual_overrides": len(snapshot.manual_overrides),
        "timeline_events": len(snapshot.audit_timeline),
        "registry_events_projected": len(platform_repository.list_events()),
        "portfolio_events_projected": len(portfolio_events),
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
    }
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
        "portfolio_os_foundation_hash": PORTFOLIO_OS_HASH,
        "hashing_method": HASH_VERSION,
        "created_at": snapshot.generated_at,
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "integrity": integrity.model_dump(mode="json"),
        "component_hashes": {
            "subjects_hash": canonical_hash(snapshot.subjects),
            "authorizations_hash": canonical_hash(snapshot.authorizations),
            "readiness_hash": canonical_hash(snapshot.readiness),
            "policies_hash": canonical_hash(snapshot.policies),
            "evaluations_hash": canonical_hash(snapshot.policy_evaluations),
            "violations_hash": canonical_hash(snapshot.violations),
            "audit_timeline_hash": canonical_hash(snapshot.audit_timeline),
            "module_state_hash": canonical_hash(snapshot.module_state),
        },
        "artifact_file_hashes": artifacts,
        "counts": counts,
        "current_state": {
            "research": "PAUSED",
            "a_to_g": "COMPLETE_NO_VALIDATED_STRATEGY",
            "strategy_v2": "NOT_CREATED",
            "family_h": "NOT_PLANNED",
            "paper_readiness": summary_state.paper_readiness.value,
            "live_readiness": summary_state.live_readiness.value,
            "production_readiness": summary_state.production_readiness.value,
            "broker_readiness": snapshot.summary.readiness_by_type[
                ReadinessType.BROKER_READINESS
            ].value,
            "broker_connection": "NOT_CONNECTED",
        },
        "existing_platform_artifacts_unchanged": {
            "unchanged": before == after,
            "file_hashes_before": before,
            "file_hashes_after": after,
        },
        "documentation": list(DOCUMENTATION_PATHS),
        "reports": list(REPORT_NAMES),
        "security": {
            "network_required": False,
            "credentials_written": 0,
            "external_writes": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "migrations": 0,
            "supabase_writes": 0,
        },
        "ui_implemented": False,
        "broker_connected": False,
        "real_time_feed_added": False,
        "shadow_mode_started": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "strategy_v2_created": False,
        "family_h_created": False,
        "research_rerun": False,
        "direct_domain_mutations": 0,
    }
    manifest["governance_audit_foundation_hash"] = canonical_hash(manifest)
    manifest_path = (
        root
        / "data/platform/manifests/intersignal_governance_audit_foundation_manifest_v1.json"
    )
    _write_json(manifest_path, manifest)
    summary: dict[str, Any] = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "research_workbench_backend_hash": RESEARCH_WORKBENCH_HASH,
        "portfolio_os_foundation_hash": PORTFOLIO_OS_HASH,
        "governance_audit_foundation_hash": manifest[
            "governance_audit_foundation_hash"
        ],
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "integrity": integrity.model_dump(mode="json"),
        "counts": counts,
        "current_state": manifest["current_state"],
        "existing_platform_artifacts_unchanged": manifest[
            "existing_platform_artifacts_unchanged"
        ],
        "reports": list(REPORT_NAMES),
        "documentation": list(DOCUMENTATION_PATHS),
        "verification": {
            "backend_targeted_tests": "PENDING",
            "backend_full_tests": "PENDING",
            "frontend_build": "PENDING",
            "regressions": "PENDING",
            "ready_for_review": False,
        },
    }
    _write_reports(root, snapshot, summary)
    return summary


def finalize_governance_audit_foundation(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = (
        root
        / "data/platform/manifests/intersignal_governance_audit_foundation_manifest_v1.json"
    )
    manifest = _read_json(manifest_path)
    if manifest["governance_audit_foundation_hash"] != _document_hash(
        manifest, "governance_audit_foundation_hash"
    ):
        raise GovernanceAuditInputMismatch("Governance manifest hash mismatch")
    if _file_hashes(root, prior_artifact_paths(root)) != manifest[
        "existing_platform_artifacts_unchanged"
    ]["file_hashes_after"]:
        raise GovernanceAuditInputMismatch("Existing platform artifacts changed")
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
    }
    verification["ready_for_review"] = all(
        value.startswith("PASS") for value in verification.values()
    )
    summary["verification"] = verification
    _write_json(summary_path, summary)
    return verification


__all__ = (
    "COMMAND",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "GovernanceAuditInputMismatch",
    "MANIFEST_VERSION",
    "PLATFORM_FOUNDATION_HASH",
    "PORTFOLIO_OS_HASH",
    "REQUIRED_CHECKPOINT",
    "RESEARCH_WORKBENCH_HASH",
    "build_governance_audit_foundation",
    "finalize_governance_audit_foundation",
    "prior_artifact_paths",
    "verify_governance_audit_inputs",
)

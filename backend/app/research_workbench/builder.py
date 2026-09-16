from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.platform.hashing import (
    HASH_VERSION,
    canonical_hash,
    file_sha256,
    normalize_for_hash,
)
from app.platform.repositories import JsonFilePlatformRepository
from app.research_workbench.errors import WorkbenchIntegrityError
from app.research_workbench.models import ResearchWorkbenchSnapshot
from app.research_workbench.service import ResearchWorkbenchService


COMMAND = "Step 04.02 / Command 01"
COMMAND_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_V1"
COMMAND_PROFILE = "RESEARCH_QUERY_AND_VIEW_MODEL_FOUNDATION_V1"
MANIFEST_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_MANIFEST_V1"
INTEGRITY_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_INTEGRITY_V1"

REQUIRED_CHECKPOINT = "1ccb93afabad936a79eb1c1131194652f80ec3c1"
PLATFORM_FOUNDATION_HASH = (
    "ec270dcb640116fe56709c784b4ca915bd794b0a96847e11fb561460dfed877f"
)
PLATFORM_CHARTER_HASH = (
    "3bdf3224c6ca21c06c261bf673b76e164e6d0788b204b2875122dad878d9263b"
)

FOUNDATION_PATHS = (
    "data/platform/artifacts/artifacts.jsonl",
    "data/platform/lineage/edges.jsonl",
    "data/platform/lineage/nodes.jsonl",
    "data/platform/manifests/intersignal_platform_foundation_manifest_v1.json",
    "data/platform/registry/current_research_snapshot_v1.json",
    "data/platform/registry/events.jsonl",
    "data/platform/registry/evidence.jsonl",
    "data/platform/registry/platform_foundation_verification_v1.json",
    "data/platform/registry/strategies.jsonl",
)

REPORT_NAMES = (
    "research_workbench_backend_v1_summary.json",
    "research_workbench_backend_v1_families.csv",
    "research_workbench_backend_v1_evidence.csv",
    "research_workbench_backend_v1_blocked.csv",
    "research_workbench_backend_v1_integrity.csv",
)

DOCUMENTATION_PATHS = (
    "docs/research-workbench-backend-v1.md",
    "docs/research-workbench-view-models-v1.md",
)


class ResearchWorkbenchInputMismatch(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
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


def _foundation_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in FOUNDATION_PATHS:
        path = root / relative
        if not path.is_file():
            raise ResearchWorkbenchInputMismatch(
                f"Missing platform foundation artifact: {relative}"
            )
        hashes[relative] = file_sha256(path)
    return hashes


def verify_research_workbench_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git_head(root)
    if head != REQUIRED_CHECKPOINT:
        raise ResearchWorkbenchInputMismatch(
            f"Expected checkpoint {REQUIRED_CHECKPOINT}, found {head}"
        )
    foundation = _read_json(
        root
        / "data/platform/manifests/intersignal_platform_foundation_manifest_v1.json"
    )
    recorded_foundation_hash = foundation["platform_foundation_hash"]
    if (
        recorded_foundation_hash != PLATFORM_FOUNDATION_HASH
        or _document_hash(foundation, "platform_foundation_hash")
        != PLATFORM_FOUNDATION_HASH
    ):
        raise ResearchWorkbenchInputMismatch("Platform foundation hash mismatch")
    charter = _read_json(
        root
        / "data/product/platform_charter/v1/manifests/"
        "intersignal_product_platform_charter_manifest_v1.json"
    )
    recorded_charter_hash = charter["product_platform_charter_hash"]
    if (
        recorded_charter_hash != PLATFORM_CHARTER_HASH
        or _document_hash(charter, "product_platform_charter_hash")
        != PLATFORM_CHARTER_HASH
    ):
        raise ResearchWorkbenchInputMismatch("Platform charter hash mismatch")
    snapshot = foundation["current_research_snapshot"]
    expected = {
        "strategy_research_programme": "PAUSED",
        "a_to_g": "COMPLETE_NO_VALIDATED_STRATEGY",
        "strategy_v2": "NOT_CREATED",
        "family_h": "NOT_PLANNED",
        "paper": "NOT_READY",
        "live": "NOT_READY",
    }
    for field, value in expected.items():
        if snapshot[field] != value:
            raise ResearchWorkbenchInputMismatch(
                f"Unexpected foundation state for {field}: {snapshot[field]}"
            )
    governance = charter["governance_status"]
    return {
        "foundation": foundation,
        "charter": charter,
        "programme_state": {
            "strategy_research_status": snapshot[
                "strategy_research_programme"
            ],
            "a_to_g_cycle_status": snapshot["a_to_g"],
            "strategy_v2_status": snapshot["strategy_v2"],
            "family_h_status": snapshot["family_h"],
            "paper_readiness": snapshot["paper"],
            "live_readiness": snapshot["live"],
            "primary_programme": governance["PRIMARY_PROGRAMME"],
            "secondary_programme": governance["SECONDARY_PROGRAMME"],
        },
    }


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


def _write_reports(root: Path, snapshot: ResearchWorkbenchSnapshot, summary: dict) -> None:
    reports = root / "data/reports"
    _write_json(reports / REPORT_NAMES[0], summary)
    family_rows: list[dict] = []
    for family in snapshot.families:
        row = family.model_dump(mode="json")
        row["evidence_summary"] = _csv_value(row["evidence_summary"])
        row["metadata"] = _csv_value(row["metadata"])
        family_rows.append(row)
    _write_csv(
        reports / REPORT_NAMES[1],
        tuple(family_rows[0]) if family_rows else (),
        family_rows,
    )
    evidence_rows: list[dict] = []
    repository = JsonFilePlatformRepository(root / "data/platform")
    service = ResearchWorkbenchService.from_repository(
        repository,
        programme_state=snapshot.programme_summary.model_dump(mode="json"),
    )
    for evidence in service.list_evidence():
        row = evidence.model_dump(mode="json")
        for field in ("artifact_linkage", "lineage_linkage", "limitations", "metadata"):
            row[field] = _csv_value(row[field])
        evidence_rows.append(row)
    _write_csv(
        reports / REPORT_NAMES[2],
        tuple(evidence_rows[0]) if evidence_rows else (),
        evidence_rows,
    )
    blocked_rows = []
    for blocked in snapshot.blocked_studies:
        row = blocked.model_dump(mode="json")
        for field in (
            "resume_requirements",
            "related_evidence",
            "related_artifacts",
        ):
            row[field] = _csv_value(row[field])
        blocked_rows.append(row)
    _write_csv(
        reports / REPORT_NAMES[3],
        tuple(blocked_rows[0]) if blocked_rows else (),
        blocked_rows,
    )
    integrity_row = snapshot.integrity_summary.model_dump(mode="json")
    integrity_row["metadata"] = _csv_value(integrity_row["metadata"])
    _write_csv(
        reports / REPORT_NAMES[4],
        tuple(integrity_row),
        [integrity_row],
    )


def build_research_workbench_backend(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    inputs = verify_research_workbench_inputs(root)
    foundation_before = _foundation_hashes(root)
    repository = JsonFilePlatformRepository(root / "data/platform")
    service = ResearchWorkbenchService.from_repository(
        repository,
        programme_state=inputs["programme_state"],
    )
    integrity = service.require_integrity()
    snapshot = service.export_research_workbench_snapshot()
    workbench_root = root / "data/platform/workbench"
    snapshot_path = workbench_root / "research_workbench_snapshot_v1.json"
    _write_json(snapshot_path, snapshot.model_dump(mode="json"))

    integrity_payload: dict[str, Any] = {
        "integrity_version": INTEGRITY_VERSION,
        "generated_at": snapshot.generated_at,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "integrity": integrity.model_dump(mode="json"),
    }
    integrity_payload["integrity_hash"] = canonical_hash(integrity_payload)
    integrity_path = workbench_root / "research_workbench_integrity_v1.json"
    _write_json(integrity_path, integrity_payload)

    programme = snapshot.programme_summary
    foundation_after = _foundation_hashes(root)
    if foundation_after != foundation_before:
        raise ResearchWorkbenchInputMismatch(
            "Platform foundation artifacts changed during Workbench export"
        )
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_foundation_hash": PLATFORM_FOUNDATION_HASH,
        "platform_charter_hash": PLATFORM_CHARTER_HASH,
        "hashing_method": HASH_VERSION,
        "created_at": snapshot.generated_at,
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "component_hashes": {
            "families_hash": canonical_hash(snapshot.families),
            "strategy_summaries_hash": canonical_hash(snapshot.strategy_summaries),
            "evidence_summary_hash": canonical_hash(snapshot.evidence_summary),
            "blocked_studies_hash": canonical_hash(snapshot.blocked_studies),
            "latest_events_hash": canonical_hash(snapshot.latest_events),
        },
        "counts": {
            "families": len(snapshot.families),
            "strategies": len(snapshot.strategy_summaries),
            "evidence": snapshot.evidence_summary.total_count,
            "blocked_studies": len(snapshot.blocked_studies),
            "latest_events": len(snapshot.latest_events),
            "production_candidate_count": programme.production_candidate_count,
            "validated_production_strategy_count": programme.validated_strategy_count,
        },
        "programme_state": programme.model_dump(mode="json"),
        "integrity": integrity.model_dump(mode="json"),
        "foundation_artifacts_unchanged": {
            "unchanged": foundation_before == foundation_after,
            "file_hashes_before": foundation_before,
            "file_hashes_after": foundation_after,
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
        "portfolio_os_started": False,
        "real_time_feed_added": False,
        "strategy_v2_created": False,
        "family_h_created": False,
        "strategy_research_run": False,
        "paper_trading_started": False,
        "live_trading_started": False,
    }
    manifest["research_workbench_backend_hash"] = canonical_hash(manifest)
    manifest_path = (
        root
        / "data/platform/manifests/"
        "intersignal_research_workbench_backend_manifest_v1.json"
    )
    _write_json(manifest_path, manifest)

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "research_workbench_backend_hash": manifest[
            "research_workbench_backend_hash"
        ],
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_hash": integrity_payload["integrity_hash"],
        "counts": manifest["counts"],
        "programme_state": manifest["programme_state"],
        "integrity": manifest["integrity"],
        "foundation_artifacts_unchanged": manifest[
            "foundation_artifacts_unchanged"
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


def finalize_research_workbench_backend(
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
        / "data/platform/manifests/"
        "intersignal_research_workbench_backend_manifest_v1.json"
    )
    manifest = _read_json(manifest_path)
    recorded_hash = manifest["research_workbench_backend_hash"]
    if (
        recorded_hash
        != _document_hash(manifest, "research_workbench_backend_hash")
    ):
        raise ResearchWorkbenchInputMismatch("Workbench manifest hash mismatch")
    if _foundation_hashes(root) != manifest["foundation_artifacts_unchanged"][
        "file_hashes_after"
    ]:
        raise ResearchWorkbenchInputMismatch("Platform foundation artifacts changed")
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
    "FOUNDATION_PATHS",
    "MANIFEST_VERSION",
    "PLATFORM_CHARTER_HASH",
    "PLATFORM_FOUNDATION_HASH",
    "REQUIRED_CHECKPOINT",
    "ResearchWorkbenchInputMismatch",
    "build_research_workbench_backend",
    "finalize_research_workbench_backend",
    "verify_research_workbench_inputs",
)

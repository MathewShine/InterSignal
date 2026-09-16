from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.platform.hashing import HASH_VERSION, canonical_hash, canonical_json, file_sha256
from app.platform.models import (
    ArtifactRecord,
    ArtifactType,
    EvidenceClassification,
    EvidenceLevel,
    EvidenceRecord,
    EvidenceStatus,
    LineageRelationship,
    LineageStage,
    StrategyLifecycle,
    StrategyRecord,
    build_artifact_record,
    build_lineage_edge,
    build_lineage_node,
    evidence_content_hash,
)
from app.platform.repositories import JsonFilePlatformRepository
from app.platform.services import PlatformRegistryService


COMMAND = "Step 04.01 / Command 01"
COMMAND_VERSION = "INTERSIGNAL_PLATFORM_FOUNDATION_V1"
COMMAND_PROFILE = "DATA_LINEAGE_STRATEGY_EVIDENCE_REGISTRY_V1"
MANIFEST_VERSION = "INTERSIGNAL_PLATFORM_FOUNDATION_MANIFEST_V1"

REQUIRED_CHECKPOINT = "ee7a9bfca356015483aa0380f26985b88301f75e"
PLATFORM_CHARTER_HASH = "3bdf3224c6ca21c06c261bf673b76e164e6d0788b204b2875122dad878d9263b"
PROGRAM_REVIEW_HASH = "a152b0e489005ecb506887082c99bee35a8e3c77e199f4c0ada2d7e0089a18cc"
FAMILY_A_CLOSURE_HASH = "ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad"

REPORT_NAMES = (
    "platform_foundation_v1_summary.json",
    "platform_foundation_v1_strategy_seed.csv",
    "platform_foundation_v1_evidence_seed.csv",
    "platform_foundation_v1_lineage_seed.csv",
    "platform_foundation_v1_registry_events.csv",
)

DOCUMENTATION_PATHS = (
    "docs/platform-data-lineage-v1.md",
    "docs/platform-strategy-evidence-registry-v1.md",
    "docs/platform-registry-domain-model-v1.md",
)

ACTOR = "seed_platform_registry_from_research"
SEED_REASON = "Reference frozen research metadata without mutating source artifacts"


class PlatformFoundationInputMismatch(RuntimeError):
    pass


class PlatformFoundationImmutabilityError(RuntimeError):
    pass


def output_root(root: Path) -> Path:
    return Path(root) / "data/platform"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != field})


def _verified_document(path: Path, field: str, expected: str) -> dict[str, Any]:
    document = _read_json(path)
    actual = document[field] if field in document else None
    if actual != expected or _document_hash(document, field) != expected:
        raise PlatformFoundationInputMismatch(f"Immutable foundation input mismatch: {path}")
    return document


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def verify_platform_foundation_inputs(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    head = _git_head(root)
    if head != REQUIRED_CHECKPOINT:
        raise PlatformFoundationInputMismatch(
            f"Expected checkpoint {REQUIRED_CHECKPOINT}, found {head}"
        )
    charter = _verified_document(
        root
        / "data/product/platform_charter/v1/manifests/"
        "intersignal_product_platform_charter_manifest_v1.json",
        "product_platform_charter_hash",
        PLATFORM_CHARTER_HASH,
    )
    program_review = _verified_document(
        root
        / "data/research/program_review/v1/manifests/"
        "post_research_strategy_program_review_manifest_v1.json",
        "post_research_program_review_hash",
        PROGRAM_REVIEW_HASH,
    )
    closure = _verified_document(
        root
        / "data/research/validation/family_a/v1/post_validation_closure/manifests/"
        "family_a_post_validation_closure_manifest_v1.json",
        "family_a_post_validation_closure_hash",
        FAMILY_A_CLOSURE_HASH,
    )
    checks = {
        "checkpoint_exact": head == REQUIRED_CHECKPOINT,
        "platform_charter_exact": charter["product_platform_charter_hash"]
        == PLATFORM_CHARTER_HASH,
        "product_platform_primary": charter["governance_status"][
            "PRIMARY_PROGRAMME"
        ]
        == "PRODUCT_PLATFORM_PROGRAM",
        "strategy_research_paused": charter["governance_status"][
            "STRATEGY_RESEARCH"
        ]
        == "PAUSED",
        "strategy_v2_not_created": charter["strategy_v2_created"] is False,
        "paper_not_ready": charter["governance_status"]["PAPER"] == "NOT_READY",
        "live_not_ready": charter["governance_status"]["LIVE"] == "NOT_READY",
        "a_to_g_complete": program_review["a_to_g_final_status"]
        == "COMPLETE_NO_VALIDATED_STRATEGY",
        "family_a_closed": closure["candidate_final_status"]
        == "CLOSED_NOT_ADVANCED",
    }
    if not all(checks.values()):
        raise PlatformFoundationInputMismatch(
            f"PLATFORM_FOUNDATION_INPUT_MISMATCH: {checks}"
        )
    return {
        "checks": checks,
        "head": head,
        "charter": charter,
        "program_review": program_review,
        "closure": closure,
    }


def _artifact_specs() -> tuple[dict[str, Any], ...]:
    return (
        {"path": "data/product/platform_charter/v1/manifests/intersignal_product_platform_charter_manifest_v1.json", "type": ArtifactType.MANIFEST, "name": "InterSignal Product Platform Charter Manifest"},
        {"path": "data/research/program_review/v1/manifests/post_research_strategy_program_review_manifest_v1.json", "type": ArtifactType.MANIFEST, "name": "Post-Research Strategy Program Review Manifest"},
        {"path": "data/research/validation/family_a/v1/post_validation_closure/manifests/family_a_post_validation_closure_manifest_v1.json", "type": ArtifactType.MANIFEST, "name": "Family A Post-Validation Closure Manifest"},
        {"path": "data/research/validation/family_a/v1/post_validation_closure/evidence/final_evidence_registry_v1.json", "type": ArtifactType.RESEARCH_ARTIFACT, "name": "A-G Final Governance Evidence Registry"},
        {"path": "data/research/validation/family_a/v1/evaluation/results/validation_result_v1.json", "type": ArtifactType.VALIDATION_ARTIFACT, "name": "Family A Formal Validation Result"},
        {"path": "data/research/validation/family_a/v1/post_outcome_remediated/results/post_outcome_result_v1.json", "type": ArtifactType.VALIDATION_ARTIFACT, "name": "Family A Post-Outcome Remediated Result"},
        {"path": "data/research/cross_family_synthesis/v1/positive_evidence/positive_evidence_registry_v1.json", "type": ArtifactType.RESEARCH_ARTIFACT, "name": "Cross-Family Positive Evidence Registry"},
        {"path": "data/research/cross_family_synthesis/v1/negative_evidence/negative_evidence_registry_v1.json", "type": ArtifactType.RESEARCH_ARTIFACT, "name": "Cross-Family Negative Evidence Registry"},
        {"path": "data/research/cross_family_synthesis/v1/blocked_research/blocked_research_registry_v1.json", "type": ArtifactType.RESEARCH_ARTIFACT, "name": "Cross-Family Blocked Research Registry"},
        {"path": "data/research/cross_family_synthesis/v1/family_matrix/family_matrix_v1.json", "type": ArtifactType.RESEARCH_ARTIFACT, "name": "Cross-Family Matrix"},
        {"path": "data/research/strategy_families/family_a/v1/registry/family_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family A Configuration"},
        {"path": "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family A Preregistration"},
        {"path": "data/research/strategy_families/family_b/v1/registry/family_b_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family B Configuration"},
        {"path": "data/research/strategy_families/family_b/v1/registry/mom_b_002_preregistration_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family B Preregistration"},
        {"path": "data/research/strategy_families/family_c/v1/registry/family_c_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family C Configuration"},
        {"path": "data/research/strategy_families/family_c/v1/registry/brk_c_001_preregistration_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family C Preregistration"},
        {"path": "data/research/strategy_families/family_d/v1/registry/family_d_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family D Configuration and Preregistration"},
        {"path": "data/research/strategy_families/family_e/v1/registry/family_e_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family E Configuration"},
        {"path": "data/research/strategy_families/family_e/v1/registry/pbr_e_001_preregistration_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family E Preregistration"},
        {"path": "data/research/strategy_families/family_f/closure/v1/manifest/family_f_data_source_closure_manifest_v1.json", "type": ArtifactType.MANIFEST, "name": "Family F Data-Source Closure Manifest"},
        {"path": "data/research/strategy_families/family_g/v1/registry/family_g_config_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family G Configuration"},
        {"path": "data/research/strategy_families/family_g/v1/registry/regime_g_001_preregistration_v1.json", "type": ArtifactType.MODEL_CONFIG, "name": "Family G Preregistration"},
    )


def _protected_hashes(root: Path) -> dict[str, str]:
    return {
        spec["path"]: file_sha256(root / spec["path"])
        for spec in _artifact_specs()
    }


def _strategy_specs() -> tuple[dict[str, Any], ...]:
    return (
        {"strategy_id": "FAMILY_A", "family": "A", "name": "Medium-Term Cross-Sectional Momentum", "status": StrategyLifecycle.REJECTED, "validation": "INCONCLUSIVE", "source_status": "CLOSED_NOT_ADVANCED", "config": "data/research/strategy_families/family_a/v1/registry/family_config_v1.json", "prereg": "data/research/strategy_families/family_a/v1/registry/mom_a_002_v1.json", "description": "Historically strong development evidence that did not generalize after the post-outcome remediation."},
        {"strategy_id": "FAMILY_B", "family": "B", "name": "Relative Plus Absolute Momentum", "status": StrategyLifecycle.REJECTED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_NO_VALIDATION_CANDIDATE", "config": "data/research/strategy_families/family_b/v1/registry/family_b_config_v1.json", "prereg": "data/research/strategy_families/family_b/v1/registry/mom_b_002_preregistration_v1.json", "description": "No clear incremental edge over relative momentum."},
        {"strategy_id": "FAMILY_C", "family": "C", "name": "Breakout Continuation", "status": StrategyLifecycle.PAUSED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_NO_VALIDATION_CANDIDATE", "config": "data/research/strategy_families/family_c/v1/registry/family_c_config_v1.json", "prereg": "data/research/strategy_families/family_c/v1/registry/brk_c_001_preregistration_v1.json", "description": "Reusable compression signal evidence only; no portfolio-ready candidate."},
        {"strategy_id": "FAMILY_D", "family": "D", "name": "Opening-Range Stocks in Play", "status": StrategyLifecycle.DATA_BLOCKED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE", "config": "data/research/strategy_families/family_d/v1/registry/family_d_config_v1.json", "prereg": "data/research/strategy_families/family_d/v1/registry/family_d_config_v1.json", "description": "Performance not evaluated because intraday continuity failed the frozen readiness gate."},
        {"strategy_id": "FAMILY_E", "family": "E", "name": "Pullback Reclaim Continuation", "status": StrategyLifecycle.REJECTED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_NO_VALIDATION_CANDIDATE", "config": "data/research/strategy_families/family_e/v1/registry/family_e_config_v1.json", "prereg": "data/research/strategy_families/family_e/v1/registry/pbr_e_001_preregistration_v1.json", "description": "The tested control and SMA50 treatment were not supported for advancement."},
        {"strategy_id": "FAMILY_F", "family": "F", "name": "Catalyst Momentum", "status": StrategyLifecycle.SOURCE_BLOCKED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE", "config": "data/research/strategy_families/family_f/closure/v1/manifest/family_f_data_source_closure_manifest_v1.json", "prereg": None, "description": "Source feasibility was demonstrated, but historical acquisition remains authorization-blocked."},
        {"strategy_id": "FAMILY_G", "family": "G", "name": "Quarterly Regime Volatility Participation", "status": StrategyLifecycle.REJECTED, "validation": "NOT_ACCESSED", "source_status": "PAUSED_NO_VALIDATION_CANDIDATE", "config": "data/research/strategy_families/family_g/v1/registry/family_g_config_v1.json", "prereg": "data/research/strategy_families/family_g/v1/registry/regime_g_001_preregistration_v1.json", "description": "The exact SMA200 gate was not supported for advancement."},
    )


def _evidence_specs() -> tuple[dict[str, Any], ...]:
    final_registry = "data/research/validation/family_a/v1/post_validation_closure/evidence/final_evidence_registry_v1.json"
    positive = "data/research/cross_family_synthesis/v1/positive_evidence/positive_evidence_registry_v1.json"
    negative = "data/research/cross_family_synthesis/v1/negative_evidence/negative_evidence_registry_v1.json"
    blocked = "data/research/cross_family_synthesis/v1/blocked_research/blocked_research_registry_v1.json"
    return (
        {"id": "EDGE-POSITIVE-A-DEVELOPMENT-001", "title": "Family A development evidence", "description": "Strong 2022-2024 after-cost development performance was historically observed but did not generalize.", "classification": EvidenceClassification.POSITIVE_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_A", "source": final_registry, "period": "2022-01-01/2024-12-31", "limitations": ("DEVELOPMENT_EVIDENCE_NOT_PRODUCTION_APPROVAL",), "metadata": {"source_status": "HISTORICALLY_STRONG_DEVELOPMENT_EVIDENCE_NOT_GENERALIZED"}},
        {"id": "EVIDENCE-A-FORMAL-VALIDATION-001", "title": "Family A formal validation evidence", "description": "The formal one-shot validation remains INCONCLUSIVE because of an implementation defect.", "classification": EvidenceClassification.VALIDATION_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_A", "source": "data/research/validation/family_a/v1/evaluation/results/validation_result_v1.json", "period": "2025-01-01/2026-08-13", "limitations": ("FORMAL_RESULT_REMAINS_INCONCLUSIVE",), "metadata": {"formal_validation_status": "INCONCLUSIVE", "formal_one_shot_replaced": False}},
        {"id": "EDGE-NEGATIVE-A-LATER-PERIOD-GENERALIZATION-001", "title": "Family A post-outcome remediated evidence", "description": "The exact frozen architecture produced UNSUPPORTIVE later-period results under corrected CA eligibility semantics.", "classification": EvidenceClassification.POST_OUTCOME_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_A", "source": "data/research/validation/family_a/v1/post_outcome_remediated/results/post_outcome_result_v1.json", "period": "2025-01-01/2026-08-13", "limitations": ("POST_OUTCOME_NOT_PRISTINE_HOLDOUT", "DOES_NOT_REPLACE_FORMAL_ONE_SHOT"), "metadata": {"generalization_indication": "UNSUPPORTIVE", "pristine_holdout_evidence": False}},
        {"id": "EVIDENCE-B-NEGATIVE-DEVELOPMENT-001", "title": "Family B negative development evidence", "description": "Family B produced no clear incremental edge over relative momentum.", "classification": EvidenceClassification.NEGATIVE_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_B", "source": negative, "period": "DEVELOPMENT", "limitations": ("DOES_NOT_REJECT_ALL_TREND_FILTERS",), "metadata": {}},
        {"id": "EVIDENCE-C-COMPRESSION-001", "title": "Family C preserved compression evidence", "description": "Compression remains reusable signal evidence only and is not portfolio-ready.", "classification": EvidenceClassification.POSITIVE_EVIDENCE, "level": EvidenceLevel.SIGNAL_LEVEL, "status": EvidenceStatus.RESEARCH_ONLY, "strategy": "FAMILY_C", "source": final_registry, "period": "DEVELOPMENT", "limitations": ("SIGNAL_ONLY_NOT_PORTFOLIO_READY",), "metadata": {"canonical_alias": "EDGE-EVIDENCE-C-COMPRESSION-001"}},
        {"id": "EDGE-EVIDENCE-C-COMPRESSION-001", "title": "Family C compression signal evidence", "description": "Pre-breakout compression no greater than 8% improved event-level signal quality in DEVELOPMENT.", "classification": EvidenceClassification.POSITIVE_EVIDENCE, "level": EvidenceLevel.SIGNAL_LEVEL, "status": EvidenceStatus.RESEARCH_ONLY, "strategy": "FAMILY_C", "source": positive, "period": "DEVELOPMENT", "limitations": ("RESEARCH_EVIDENCE_NOT_VALIDATED", "NO_STRATEGY_CREATED"), "metadata": {"source_registry_id": "EVIDENCE-C-COMPRESSION-001"}},
        {"id": "EVIDENCE-D-DATA-BLOCKED-001", "title": "Family D intraday continuity blocker", "description": "Exact prior-20 continuity was below the frozen 95% readiness threshold.", "classification": EvidenceClassification.BLOCKED_RESEARCH, "level": EvidenceLevel.DATA_INFRASTRUCTURE_LEVEL, "status": EvidenceStatus.BLOCKED, "strategy": "FAMILY_D", "source": blocked, "period": "DEVELOPMENT_DATA_ASSESSMENT", "limitations": ("STRATEGY_NOT_PERFORMANCE_EVALUATED",), "metadata": {"blocker": "CONTINUOUS_INTRADAY_DATA"}},
        {"id": "EVIDENCE-E-NEGATIVE-DEVELOPMENT-001", "title": "Family E negative development evidence", "description": "Pullback/reclaim development evidence was negative and not supported for advancement.", "classification": EvidenceClassification.NEGATIVE_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_E", "source": negative, "period": "DEVELOPMENT", "limitations": ("DOES_NOT_REJECT_ALL_PULLBACK_STRATEGIES",), "metadata": {}},
        {"id": "EVIDENCE-F-SOURCE-BLOCKED-001", "title": "Family F authorized-source blocker", "description": "Catalyst history remains blocked by source authorization and licensing.", "classification": EvidenceClassification.BLOCKED_RESEARCH, "level": EvidenceLevel.DATA_INFRASTRUCTURE_LEVEL, "status": EvidenceStatus.BLOCKED, "strategy": "FAMILY_F", "source": blocked, "period": "SOURCE_ASSESSMENT", "limitations": ("STRATEGY_NOT_PERFORMANCE_EVALUATED",), "metadata": {"blocker": "CATALYST_SOURCE_AUTHORIZATION"}},
        {"id": "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001", "title": "Family F NSE timestamp feasibility", "description": "The bounded NSE pilot demonstrated timestamp, linkage, identity, and reproducibility feasibility.", "classification": EvidenceClassification.DATA_INFRASTRUCTURE_EVIDENCE, "level": EvidenceLevel.DATA_INFRASTRUCTURE_LEVEL, "status": EvidenceStatus.BLOCKED, "strategy": "FAMILY_F", "source": positive, "period": "BOUNDED_SOURCE_PILOT", "limitations": ("HISTORICAL_ACQUISITION_AUTHORIZATION_UNRESOLVED",), "metadata": {"trusted_timestamp_quality_percent": 95.24, "canonical_linkage_percent": 100.0}},
        {"id": "EDGE-NEGATIVE-G-SMA200-GATE-001", "title": "Family G SMA200 gate evidence", "description": "The exact quarterly SMA200 participation gate reduced returns and worsened drawdown.", "classification": EvidenceClassification.NEGATIVE_EVIDENCE, "level": EvidenceLevel.STRATEGY_LEVEL, "status": EvidenceStatus.HISTORICAL, "strategy": "FAMILY_G", "source": negative, "period": "DEVELOPMENT", "limitations": ("DOES_NOT_REJECT_ALL_REGIME_FILTERS",), "metadata": {"source_status": "PARTIALLY_SUPPORTED_NOT_ADVANCED"}},
    )


def seed_research_registry(
    root: Path, repository: JsonFilePlatformRepository | Any, created_at: datetime
) -> dict[str, Any]:
    root = Path(root).resolve()
    service = PlatformRegistryService.from_repository(repository)
    artifact_by_path: dict[str, ArtifactRecord] = {}
    source_node_by_path: dict[str, Any] = {}

    for spec in _artifact_specs():
        relative = spec["path"]
        source = root / relative
        if not source.is_file():
            raise PlatformFoundationInputMismatch(f"Missing seed source artifact: {relative}")
        content_hash = file_sha256(source)
        node = build_lineage_node(
            stage=LineageStage.SOURCE,
            entity_type="FROZEN_RESEARCH_ARTIFACT",
            entity_key=relative,
            version="V1",
            content_hash=content_hash,
            created_at=created_at,
            source_system="INTERSIGNAL_RESEARCH_CORPUS",
            metadata={"reference_only": True, "source_mutated": False},
        )
        service.register_lineage_node(node, actor=ACTOR, reason=SEED_REASON)
        artifact = build_artifact_record(
            artifact_type=spec["type"],
            name=spec["name"],
            version="V1",
            path_or_reference=relative,
            content_hash=content_hash,
            created_at=created_at,
            lineage_node_id=node.node_id,
            metadata={"reference_only": True, "copied": False},
        )
        service.register_artifact(artifact, actor=ACTOR, reason=SEED_REASON)
        artifact_by_path[relative] = artifact
        source_node_by_path[relative] = node

    for spec in _strategy_specs():
        config_artifact = artifact_by_path[spec["config"]]
        prereg_artifact = (
            artifact_by_path[spec["prereg"]] if spec["prereg"] else None
        )
        source_artifact_ids = [config_artifact.artifact_id]
        if prereg_artifact and prereg_artifact.artifact_id not in source_artifact_ids:
            source_artifact_ids.append(prereg_artifact.artifact_id)
        record = StrategyRecord(
            strategy_id=spec["strategy_id"],
            strategy_family=spec["family"],
            name=spec["name"],
            version="V1",
            description=spec["description"],
            lifecycle_status=spec["status"],
            config_hash=config_artifact.content_hash,
            preregistration_hash=(
                prereg_artifact.content_hash if prereg_artifact else None
            ),
            implementation_hash=None,
            created_at=created_at,
            updated_at=created_at,
            promotion_allowed=False,
            validation_status=spec["validation"],
            production_status="NOT_READY",
            metadata={
                "source_governance_status": spec["source_status"],
                "source_artifact_ids": source_artifact_ids,
                "seed_is_reference_only": True,
            },
        )
        service.register_strategy(record, actor=ACTOR, reason=SEED_REASON)

    for spec in _evidence_specs():
        source_artifact = artifact_by_path[spec["source"]]
        source_node = source_node_by_path[spec["source"]]
        record = EvidenceRecord(
            evidence_id=spec["id"],
            title=spec["title"],
            description=spec["description"],
            classification=spec["classification"],
            evidence_level=spec["level"],
            status=spec["status"],
            strategy_id=spec["strategy"],
            source_artifact_ids=(source_artifact.artifact_id,),
            lineage_node_ids=(source_node.node_id,),
            created_at=created_at,
            effective_period=spec["period"],
            confidence=None,
            limitations=spec["limitations"],
            metadata=spec["metadata"],
        )
        service.register_evidence(record, actor=ACTOR, reason=SEED_REASON)
        evidence_node = build_lineage_node(
            stage=LineageStage.EVIDENCE,
            entity_type="EVIDENCE_RECORD",
            entity_key=record.evidence_id,
            version="V1",
            content_hash=evidence_content_hash(record),
            created_at=created_at,
            source_system="INTERSIGNAL_PLATFORM_REGISTRY",
            metadata={"strategy_id": record.strategy_id},
        )
        service.register_lineage_node(
            evidence_node, actor=ACTOR, reason="Create evidence lineage reference"
        )
        relationship = {
            EvidenceClassification.POSITIVE_EVIDENCE: LineageRelationship.SUPPORTED_BY,
            EvidenceClassification.NEGATIVE_EVIDENCE: LineageRelationship.CONTRADICTED_BY,
            EvidenceClassification.VALIDATION_EVIDENCE: LineageRelationship.VALIDATED_BY,
            EvidenceClassification.POST_OUTCOME_EVIDENCE: LineageRelationship.CONTRADICTED_BY,
            EvidenceClassification.BLOCKED_RESEARCH: LineageRelationship.GENERATED_BY,
            EvidenceClassification.DATA_INFRASTRUCTURE_EVIDENCE: LineageRelationship.SUPPORTED_BY,
        }[record.classification]
        edge = build_lineage_edge(
            parent_node_id=source_node.node_id,
            child_node_id=evidence_node.node_id,
            relationship_type=relationship,
            created_at=created_at,
            metadata={"evidence_id": record.evidence_id},
        )
        service.register_lineage_edge(
            edge, actor=ACTOR, reason="Link evidence to immutable source artifact"
        )

    strategies = service.list_strategies()
    evidence = service.list_evidence()
    production_candidates = sum(
        row.lifecycle_status == StrategyLifecycle.PRODUCTION_CANDIDATE
        for row in strategies
    )
    validated_production = sum(
        row.lifecycle_status == StrategyLifecycle.PRODUCTION_CANDIDATE
        and row.validation_status == "VALIDATED"
        and row.production_status == "PRODUCTION_READY"
        for row in strategies
    )
    if production_candidates or validated_production:
        raise PlatformFoundationInputMismatch(
            "Seed unexpectedly created a production strategy"
        )
    return {
        "service": service,
        "strategies": strategies,
        "evidence": evidence,
        "artifacts": service.list_artifacts(),
        "nodes": repository.list_lineage_nodes(),
        "edges": repository.list_lineage_edges(),
        "events": repository.list_events(),
        "production_candidate_count": production_candidates,
        "validated_production_strategy_count": validated_production,
    }


def _ensure_fresh(root: Path) -> None:
    destination = output_root(root)
    staging = root / "data/.platform_foundation_staging_v1"
    reports = [root / "data/reports" / name for name in REPORT_NAMES]
    existing = [path for path in (destination, staging, *reports) if path.exists()]
    if existing:
        raise PlatformFoundationImmutabilityError(
            "INTERSIGNAL_PLATFORM_FOUNDATION_ALREADY_EXISTS: "
            + ", ".join(str(path) for path in existing)
        )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: canonical_json(value)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def _model_rows(models: Sequence[Any]) -> list[dict[str, Any]]:
    return [model.model_dump(mode="json") for model in models]


def _lineage_report_rows(seed: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "record_type": "NODE",
            "record_id": node.node_id,
            "stage": node.stage.value,
            "entity_type": node.entity_type,
            "entity_key": node.entity_key,
            "parent_node_id": "",
            "child_node_id": "",
            "relationship_type": "",
            "content_hash": node.content_hash,
        }
        for node in seed["nodes"]
    ]
    rows.extend(
        {
            "record_type": "EDGE",
            "record_id": edge.edge_id,
            "stage": "",
            "entity_type": "",
            "entity_key": "",
            "parent_node_id": edge.parent_node_id,
            "child_node_id": edge.child_node_id,
            "relationship_type": edge.relationship_type.value,
            "content_hash": "",
        }
        for edge in seed["edges"]
    )
    return rows


def _event_report_rows(events: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row.event_id,
            "entity_type": row.entity_type.value,
            "entity_id": row.entity_id,
            "event_type": row.event_type.value,
            "actor": row.actor,
            "reason": row.reason,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
            "previous_state": canonical_json(row.previous_state),
            "new_state": canonical_json(row.new_state),
            "related_artifact_ids": canonical_json(row.related_artifact_ids),
        }
        for row in events
    ]


def build_platform_foundation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    _ensure_fresh(root)
    inputs = verify_platform_foundation_inputs(root)
    protected_before = _protected_hashes(root)
    created_at = datetime.fromisoformat(
        inputs["charter"]["created_at"].replace("Z", "+00:00")
    )
    staging = root / "data/.platform_foundation_staging_v1"
    repository = JsonFilePlatformRepository(staging)
    seed = seed_research_registry(root, repository, created_at)

    snapshot = {
        "snapshot_version": "INTERSIGNAL_CURRENT_RESEARCH_SNAPSHOT_V1",
        "strategy_research_programme": "PAUSED",
        "a_to_g": "COMPLETE_NO_VALIDATED_STRATEGY",
        "strategy_v2": "NOT_CREATED",
        "family_h": "NOT_PLANNED",
        "paper": "NOT_READY",
        "live": "NOT_READY",
        "strategy_count": len(seed["strategies"]),
        "evidence_count": len(seed["evidence"]),
        "production_candidate_count": seed["production_candidate_count"],
        "validated_production_strategy_count": seed[
            "validated_production_strategy_count"
        ],
    }
    snapshot["current_research_snapshot_hash"] = canonical_hash(snapshot)
    _write_json(staging / "registry/current_research_snapshot_v1.json", snapshot)

    protected_after = _protected_hashes(root)
    if protected_before != protected_after:
        raise PlatformFoundationInputMismatch(
            "Existing research artifacts changed during registry seeding"
        )

    strategy_rows = _model_rows(seed["strategies"])
    evidence_rows = _model_rows(seed["evidence"])
    lineage_rows = _lineage_report_rows(seed)
    artifact_rows = _model_rows(seed["artifacts"])
    event_rows = _event_report_rows(seed["events"])
    component_hashes = {
        "strategy_seed_hash": canonical_hash(strategy_rows),
        "evidence_seed_hash": canonical_hash(evidence_rows),
        "lineage_seed_hash": canonical_hash(lineage_rows),
        "artifact_seed_hash": canonical_hash(artifact_rows),
        "registry_events_hash": canonical_hash(event_rows),
        "current_research_snapshot_hash": snapshot[
            "current_research_snapshot_hash"
        ],
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "required_checkpoint": REQUIRED_CHECKPOINT,
        "platform_charter_hash": PLATFORM_CHARTER_HASH,
        "hashing_method": HASH_VERSION,
        "component_hashes": component_hashes,
        "counts": {
            "strategies": len(strategy_rows),
            "evidence": len(evidence_rows),
            "artifacts": len(artifact_rows),
            "lineage_nodes": len(seed["nodes"]),
            "lineage_edges": len(seed["edges"]),
            "registry_events": len(event_rows),
            "production_candidate_count": seed["production_candidate_count"],
            "validated_production_strategy_count": seed[
                "validated_production_strategy_count"
            ],
        },
        "current_research_snapshot": snapshot,
        "proof_existing_research_unchanged": {
            "unchanged": True,
            "file_hashes_before": protected_before,
            "file_hashes_after": protected_after,
        },
        "strategy_v2_created": False,
        "family_h_created": False,
        "paper_trading_started": False,
        "live_trading_started": False,
        "shadow_observation_started": False,
        "portfolio_os_implemented": False,
        "ui_implemented": False,
        "broker_connected": False,
        "real_time_feed_added": False,
        "strategy_research_run": False,
        "reports": list(REPORT_NAMES),
        "documentation": list(DOCUMENTATION_PATHS),
        "security": {
            "network_required": False,
            "external_writes": 0,
            "credentials_written": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "migrations": 0,
            "supabase_writes": 0,
        },
    }
    manifest = {
        **manifest_body,
        "platform_foundation_hash": canonical_hash(manifest_body),
    }
    _write_json(
        staging / "manifests/intersignal_platform_foundation_manifest_v1.json",
        manifest,
    )

    summary = {
        **manifest,
        "inputs_verified": inputs["checks"],
        "strategy_seed": strategy_rows,
        "evidence_seed": evidence_rows,
        "artifact_seed": artifact_rows,
        "lineage_seed": lineage_rows,
        "registry_events": event_rows,
        "manifest_path": "data/platform/manifests/intersignal_platform_foundation_manifest_v1.json",
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "regressions": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    reports = staging / "_reports"
    _write_json(reports / REPORT_NAMES[0], summary)
    _write_csv(reports / REPORT_NAMES[1], strategy_rows)
    _write_csv(reports / REPORT_NAMES[2], evidence_rows)
    _write_csv(reports / REPORT_NAMES[3], lineage_rows)
    _write_csv(reports / REPORT_NAMES[4], event_rows)

    destination = output_root(root)
    staging.replace(destination)
    for source in list((destination / "_reports").iterdir()):
        source.replace(root / "data/reports" / source.name)
    (destination / "_reports").rmdir()
    return summary


def finalize_platform_foundation(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
    regressions: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = (
        output_root(root)
        / "manifests/intersignal_platform_foundation_manifest_v1.json"
    )
    manifest = _read_json(manifest_path)
    recorded_hash = manifest["platform_foundation_hash"]
    if _document_hash(manifest, "platform_foundation_hash") != recorded_hash:
        raise PlatformFoundationInputMismatch("Platform foundation manifest mismatch")
    if _protected_hashes(root) != manifest["proof_existing_research_unchanged"][
        "file_hashes_after"
    ]:
        raise PlatformFoundationInputMismatch("Existing research artifacts changed")
    values = (backend_targeted_tests, backend_full_tests, frontend_build, regressions)
    verification = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "regressions": regressions,
        "ready_for_review": all(value.startswith("PASS") for value in values),
        "manifest_unchanged": True,
        "research_artifacts_unchanged": True,
    }
    record = {
        "verification_version": "INTERSIGNAL_PLATFORM_FOUNDATION_VERIFICATION_V1",
        "platform_foundation_hash": manifest["platform_foundation_hash"],
        "verification": verification,
    }
    record["platform_foundation_verification_hash"] = canonical_hash(record)
    target = output_root(root) / "registry/platform_foundation_verification_v1.json"
    if target.exists():
        raise PlatformFoundationImmutabilityError(
            "Platform foundation has already been finalized"
        )
    _write_json(target, record)
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    summary = _read_json(summary_path)
    summary["verification"] = verification
    _write_json(summary_path, summary)
    return summary


__all__ = (
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "DOCUMENTATION_PATHS",
    "MANIFEST_VERSION",
    "PLATFORM_CHARTER_HASH",
    "REPORT_NAMES",
    "REQUIRED_CHECKPOINT",
    "build_platform_foundation",
    "finalize_platform_foundation",
    "output_root",
    "seed_research_registry",
    "verify_platform_foundation_inputs",
)

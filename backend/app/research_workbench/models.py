from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from app.platform.models import (
    EvidenceClassification,
    EvidenceLevel,
    EvidenceStatus,
    ImmutableDomainModel,
    LineageEdge,
    LineageNode,
    StrategyLifecycle,
    StrategyRecord,
)


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class WorkbenchModel(ImmutableDomainModel):
    @field_validator(
        "timestamp",
        "latest_activity_at",
        "generated_at",
        "start_at",
        "end_at",
        check_fields=False,
    )
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Workbench timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class ResearchConclusionClassification(StrEnum):
    STRONG_DEVELOPMENT_NOT_GENERALIZED = "STRONG_DEVELOPMENT_NOT_GENERALIZED"
    NO_INCREMENTAL_EDGE = "NO_INCREMENTAL_EDGE"
    REUSABLE_SIGNAL_ONLY = "REUSABLE_SIGNAL_ONLY"
    DATA_BLOCKED = "DATA_BLOCKED"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    NEGATIVE_DEVELOPMENT = "NEGATIVE_DEVELOPMENT"
    NEGATIVE_OVERLAY = "NEGATIVE_OVERLAY"
    CLOSED_NOT_ADVANCED = "CLOSED_NOT_ADVANCED"


class FamilySortField(StrEnum):
    NAME = "name"
    LATEST_ACTIVITY = "latest_activity"
    STATUS = "status"
    FAMILY_CODE = "family_code"


class WorkbenchIntegrityStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ERROR = "ERROR"


class EvidenceSummary(WorkbenchModel):
    positive_evidence_count: int = Field(ge=0)
    negative_evidence_count: int = Field(ge=0)
    blocked_research_count: int = Field(ge=0)
    validation_evidence_count: int = Field(ge=0)
    post_outcome_evidence_count: int = Field(ge=0)
    data_infrastructure_evidence_count: int = Field(ge=0)
    total_count: int = Field(ge=0)


class ResearchEvidenceDetail(WorkbenchModel):
    evidence_id: str = Field(min_length=1)
    classification: EvidenceClassification
    level: EvidenceLevel
    status: EvidenceStatus
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    strategy_linkage: str = Field(min_length=1)
    artifact_linkage: tuple[str, ...]
    lineage_linkage: tuple[str, ...]
    effective_period: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchTimelineEvent(WorkbenchModel):
    event_id: str = Field(min_length=1)
    timestamp: datetime
    family_id: str | None = None
    strategy_id: str | None = None
    event_type: str = Field(min_length=1)
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any]
    reason: str = Field(min_length=1)
    related_artifacts: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationSummary(WorkbenchModel):
    validation_status: str = Field(min_length=1)
    formal_result: str | None = None
    generalization_result: str | None = None
    post_outcome_result: str | None = None
    advancement_status: str = Field(min_length=1)
    run_count: int = Field(ge=0)
    remaining_runs: int = Field(ge=0)
    pristine_holdout: bool | None = None
    limitations: tuple[str, ...] = ()
    related_artifacts: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class BlockedResearchSummary(WorkbenchModel):
    family_id: str = Field(min_length=1)
    block_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    resume_requirements: tuple[str, ...]
    data_or_source: str = Field(min_length=1)
    status: str = Field(min_length=1)
    related_evidence: tuple[str, ...]
    related_artifacts: tuple[str, ...]


class ResearchArtifactSummary(WorkbenchModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str
    reference: str = Field(min_length=1)
    immutability_status: str = Field(min_length=1)
    lineage_node_id: str = Field(min_length=1)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("content_hash must be a lowercase SHA-256 hex digest")
        return value


class ResearchLineageSummary(WorkbenchModel):
    node_id: str = Field(min_length=1)
    upstream_count: int = Field(ge=0)
    downstream_count: int = Field(ge=0)
    root_sources: tuple[str, ...]
    terminal_evidence: tuple[str, ...]
    path_summary: tuple[str, ...]
    integrity_status: WorkbenchIntegrityStatus


class ResearchLineageTrace(WorkbenchModel):
    summary: ResearchLineageSummary
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    max_nodes: int = Field(gt=0)
    max_depth: int = Field(gt=0)


class ResearchConclusion(WorkbenchModel):
    classification: ResearchConclusionClassification
    summary: str = Field(min_length=1)
    basis: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    advancement_allowed: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchFamilySummary(WorkbenchModel):
    family_id: str = Field(min_length=1)
    family_name: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    lifecycle_status: StrategyLifecycle
    evidence_summary: EvidenceSummary
    validation_status: str = Field(min_length=1)
    block_reason: str | None = None
    strategy_count: int = Field(ge=0)
    experiment_count: int = Field(ge=0)
    positive_evidence_count: int = Field(ge=0)
    negative_evidence_count: int = Field(ge=0)
    blocked_evidence_count: int = Field(ge=0)
    latest_activity_at: datetime
    production_candidate: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchStrategySummary(WorkbenchModel):
    strategy_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    lifecycle_status: StrategyLifecycle
    validation_state: str = Field(min_length=1)
    production_state: str = Field(min_length=1)
    evidence_summary: EvidenceSummary
    conclusion: ResearchConclusion
    latest_activity_at: datetime


class ResearchStrategyDetail(WorkbenchModel):
    strategy_record: StrategyRecord
    lifecycle_history: tuple[StrategyRecord, ...]
    config_hashes: tuple[str, ...]
    preregistration_hashes: tuple[str, ...]
    implementation_hash: str | None = None
    validation_state: str = Field(min_length=1)
    production_state: str = Field(min_length=1)
    evidence_by_classification: dict[
        EvidenceClassification, tuple[ResearchEvidenceDetail, ...]
    ]
    artifacts: tuple[ResearchArtifactSummary, ...]
    lineage: tuple[ResearchLineageSummary, ...]
    limitations: tuple[str, ...]
    current_conclusion: ResearchConclusion


class ResearchFamilyDetail(WorkbenchModel):
    family_id: str = Field(min_length=1)
    family_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    current_lifecycle: StrategyLifecycle
    strategies: tuple[StrategyRecord, ...]
    evidence: tuple[ResearchEvidenceDetail, ...]
    events: tuple[ResearchTimelineEvent, ...]
    artifacts: tuple[ResearchArtifactSummary, ...]
    validation_summary: ValidationSummary
    blocked_reason: str | None = None
    known_limitations: tuple[str, ...]
    research_conclusion: ResearchConclusion
    lineage_references: tuple[str, ...]


class ResearchProgrammeSummary(WorkbenchModel):
    strategy_research_status: str = Field(min_length=1)
    a_to_g_cycle_status: str = Field(min_length=1)
    validated_strategy_count: int = Field(ge=0)
    production_candidate_count: int = Field(ge=0)
    strategy_v2_status: str = Field(min_length=1)
    family_h_status: str = Field(min_length=1)
    paper_readiness: str = Field(min_length=1)
    live_readiness: str = Field(min_length=1)
    primary_programme: str = Field(min_length=1)
    secondary_programme: str = Field(min_length=1)


class ResearchFamilyQuery(WorkbenchModel):
    family_status: tuple[str, ...] = ()
    lifecycle: tuple[StrategyLifecycle, ...] = ()
    evidence_classification: tuple[EvidenceClassification, ...] = ()
    evidence_level: tuple[EvidenceLevel, ...] = ()
    blocked_state: bool | None = None
    validation_state: tuple[str, ...] = ()
    start_at: datetime | None = None
    end_at: datetime | None = None
    sort_by: FamilySortField = FamilySortField.FAMILY_CODE
    descending: bool = False
    limit: int = 50
    offset: int = 0


class ResearchFamilyPage(WorkbenchModel):
    items: tuple[ResearchFamilySummary, ...]
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)
    total_count: int = Field(ge=0)


class ResearchWorkbenchIntegritySummary(WorkbenchModel):
    broken_strategy_refs: int = Field(ge=0)
    broken_evidence_refs: int = Field(ge=0)
    broken_artifact_refs: int = Field(ge=0)
    broken_lineage_refs: int = Field(ge=0)
    cycle_count: int = Field(ge=0)
    duplicate_ids: int = Field(ge=0)
    hash_mismatches: int = Field(ge=0)
    status: WorkbenchIntegrityStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchWorkbenchSnapshot(WorkbenchModel):
    snapshot_version: str = Field(min_length=1)
    generated_at: datetime
    programme_summary: ResearchProgrammeSummary
    families: tuple[ResearchFamilySummary, ...]
    strategy_summaries: tuple[ResearchStrategySummary, ...]
    evidence_summary: EvidenceSummary
    blocked_studies: tuple[BlockedResearchSummary, ...]
    latest_events: tuple[ResearchTimelineEvent, ...]
    integrity_summary: ResearchWorkbenchIntegritySummary
    snapshot_hash: str

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if not HASH_PATTERN.fullmatch(value):
            raise ValueError("snapshot_hash must be a lowercase SHA-256 hex digest")
        return value


__all__ = (
    "BlockedResearchSummary",
    "EvidenceSummary",
    "FamilySortField",
    "ResearchArtifactSummary",
    "ResearchConclusion",
    "ResearchConclusionClassification",
    "ResearchEvidenceDetail",
    "ResearchFamilyDetail",
    "ResearchFamilyPage",
    "ResearchFamilyQuery",
    "ResearchFamilySummary",
    "ResearchLineageSummary",
    "ResearchLineageTrace",
    "ResearchProgrammeSummary",
    "ResearchStrategyDetail",
    "ResearchStrategySummary",
    "ResearchTimelineEvent",
    "ResearchWorkbenchIntegritySummary",
    "ResearchWorkbenchSnapshot",
    "ValidationSummary",
    "WorkbenchIntegrityStatus",
)

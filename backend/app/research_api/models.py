from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_RESEARCH_WORKBENCH_V1 = "INTERSIGNAL_RESEARCH_WORKBENCH_V1"


class ResearchApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("generated_at", "updated_at", "occurred_at", "created_at", check_fields=False)
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Research API timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class ResearchAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ResearchMeta(ResearchApiModel):
    read_only: bool = True
    auth_enforcement: str = "NOT_IMPLEMENTED"
    broker_integration: str = "NOT_IMPLEMENTED"
    market_integration: str = "NOT_CONFIGURED"
    source_contracts: tuple[str, ...] = (
        "INTERSIGNAL_RESEARCH_WORKBENCH_SNAPSHOT_V1",
        "INTERSIGNAL_PLATFORM_REGISTRY_V1",
    )
    internal_paths_exposed: bool = False
    unavailable_sections: tuple[str, ...] = ()


class ProgrammeView(ResearchApiModel):
    status: str
    cycle_status: str
    validated_strategy_count: int = Field(ge=0)
    production_candidate_count: int = Field(ge=0)
    strategy_v2_status: str
    family_h_status: str
    paper_readiness: str
    live_readiness: str
    primary_programme: str
    secondary_programme: str


class EvidenceCountsView(ResearchApiModel):
    positive: int = Field(ge=0)
    negative: int = Field(ge=0)
    blocked: int = Field(ge=0)
    validation: int = Field(ge=0)
    post_outcome: int = Field(ge=0)
    data_infrastructure: int = Field(ge=0)
    total: int = Field(ge=0)


class FamilyView(ResearchApiModel):
    family_id: str
    name: str
    setup: str
    description: str
    stage: str
    current_status: str
    current_status_label: str
    decision_status: str
    decision_label: str
    evidence_state: str
    validation_state: str
    validation_label: str
    blocker: str | None = None
    evidence_counts: EvidenceCountsView
    latest_activity_at: datetime
    production_candidate: bool = False
    key_findings: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    action_path: str


class ArtifactView(ResearchApiModel):
    artifact_id: str
    name: str
    artifact_type: str
    version: str
    integrity: str
    created_at: datetime
    lineage_node_id: str


class LineageNodeView(ResearchApiModel):
    node_id: str
    stage: str
    source_system: str
    entity_type: str
    status: str


class LineageEdgeView(ResearchApiModel):
    parent_node_id: str
    child_node_id: str
    relationship: str


class LineageView(ResearchApiModel):
    nodes: tuple[LineageNodeView, ...] = ()
    edges: tuple[LineageEdgeView, ...] = ()
    integrity: str = "HEALTHY"


class EvidenceView(ResearchApiModel):
    evidence_id: str
    family_id: str
    title: str
    summary: str
    classification: str
    evidence_type: str
    status: str
    production_relevance: str
    source: str
    updated_at: datetime
    artifact_ids: tuple[str, ...] = ()
    lineage_node_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    action_path: str


class EvidenceDetailView(EvidenceView):
    research_context: str
    current_disposition: str
    effective_period: str | None = None
    confidence: float | None = None
    supporting_artifacts: tuple[ArtifactView, ...] = ()
    lineage: LineageView


class ValidationRecordView(ResearchApiModel):
    record_id: str
    family_id: str
    validation_type: str
    period: str
    outcome: str
    interpretation: str
    integrity: str
    pristine_intent: bool | None = None
    notes: str
    artifact_ids: tuple[str, ...] = ()
    action_path: str


class BlockedResearchView(ResearchApiModel):
    family_id: str
    blocker_type: str
    blocker_label: str
    reason: str
    impact: str
    required_resolution: str
    status: str
    current_state: str
    related_evidence: tuple[str, ...] = ()
    related_artifacts: tuple[str, ...] = ()
    action_path: str


class TimelineEventView(ResearchApiModel):
    event_id: str
    occurred_at: datetime
    family_id: str | None = None
    event: str
    category: str
    result: str
    related_artifacts: tuple[str, ...] = ()
    related_evidence: str | None = None


class NarrativeSectionView(ResearchApiModel):
    section_id: str
    title: str
    summary: str
    tone: str = "NEUTRAL"


class ResearchOverviewResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    reason: str | None = None
    programme: ProgrammeView | None = None
    family_count: int = Field(ge=0)
    reusable_evidence_count: int = Field(ge=0)
    blocked_study_count: int = Field(ge=0)
    production_ready_count: int = Field(ge=0)
    families: tuple[FamilyView, ...] = ()
    retained_evidence: tuple[EvidenceView, ...] = ()
    blocked: tuple[BlockedResearchView, ...] = ()
    recent_activity: tuple[TimelineEventView, ...] = ()
    meta: ResearchMeta


class ResearchFamiliesResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    items: tuple[FamilyView, ...] = ()
    total_count: int = Field(ge=0)
    meta: ResearchMeta


class ResearchFamilyDetailResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    family: FamilyView
    hypothesis: str
    sections: tuple[NarrativeSectionView, ...]
    evidence: tuple[EvidenceView, ...]
    validation: tuple[ValidationRecordView, ...]
    timeline: tuple[TimelineEventView, ...]
    artifacts: tuple[ArtifactView, ...]
    lineage: LineageView
    limitations: tuple[str, ...]
    meta: ResearchMeta


class ResearchEvidenceResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    items: tuple[EvidenceView, ...] = ()
    total_count: int = Field(ge=0)
    meta: ResearchMeta


class ResearchEvidenceDetailResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    evidence: EvidenceDetailView
    meta: ResearchMeta


class ResearchValidationResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    items: tuple[ValidationRecordView, ...] = ()
    total_count: int = Field(ge=0)
    meta: ResearchMeta


class ResearchBlockedResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    items: tuple[BlockedResearchView, ...] = ()
    total_count: int = Field(ge=0)
    meta: ResearchMeta


class ResearchTimelineResponse(ResearchApiModel):
    version: str = INTERSIGNAL_RESEARCH_WORKBENCH_V1
    generated_at: datetime
    status: ResearchAvailability
    items: tuple[TimelineEventView, ...] = ()
    total_count: int = Field(ge=0)
    meta: ResearchMeta


__all__ = tuple(name for name in globals() if name.endswith(("View", "Response"))) + (
    "INTERSIGNAL_RESEARCH_WORKBENCH_V1",
    "ResearchAvailability",
    "ResearchMeta",
)

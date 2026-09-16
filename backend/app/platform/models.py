from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.hashing import canonical_hash, deterministic_id


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ImmutableDomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("created_at", "updated_at", "retrieved_at", "effective_at", "published_at", check_fields=False)
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class LineageStage(StrEnum):
    SOURCE = "SOURCE"
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    DERIVED = "DERIVED"
    FEATURE = "FEATURE"
    CANDIDATE = "CANDIDATE"
    SIGNAL = "SIGNAL"
    POSITION = "POSITION"
    TRADE = "TRADE"
    OUTCOME = "OUTCOME"
    EVIDENCE = "EVIDENCE"


class LineageRelationship(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    NORMALIZED_FROM = "NORMALIZED_FROM"
    COMPUTED_FROM = "COMPUTED_FROM"
    GENERATED_BY = "GENERATED_BY"
    VALIDATED_BY = "VALIDATED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    SUPERSEDES = "SUPERSEDES"


class RecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    SUPERSEDED = "SUPERSEDED"


class ArtifactType(StrEnum):
    RESEARCH_ARTIFACT = "RESEARCH_ARTIFACT"
    REPORT = "REPORT"
    MANIFEST = "MANIFEST"
    MODEL_CONFIG = "MODEL_CONFIG"
    VALIDATION_ARTIFACT = "VALIDATION_ARTIFACT"
    DATA_SNAPSHOT = "DATA_SNAPSHOT"


class ArtifactImmutabilityStatus(StrEnum):
    IMMUTABLE = "IMMUTABLE"
    DEPRECATED = "DEPRECATED"
    SUPERSEDED = "SUPERSEDED"


class StrategyLifecycle(StrEnum):
    IDEA = "IDEA"
    PREREGISTERED = "PREREGISTERED"
    DEVELOPMENT_EVALUATED = "DEVELOPMENT_EVALUATED"
    VALIDATION_CANDIDATE = "VALIDATION_CANDIDATE"
    VALIDATION_EVALUATED = "VALIDATION_EVALUATED"
    PAUSED = "PAUSED"
    REJECTED = "REJECTED"
    DATA_BLOCKED = "DATA_BLOCKED"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"


class EvidenceClassification(StrEnum):
    POSITIVE_EVIDENCE = "POSITIVE_EVIDENCE"
    NEGATIVE_EVIDENCE = "NEGATIVE_EVIDENCE"
    BLOCKED_RESEARCH = "BLOCKED_RESEARCH"
    VALIDATION_EVIDENCE = "VALIDATION_EVIDENCE"
    POST_OUTCOME_EVIDENCE = "POST_OUTCOME_EVIDENCE"
    DATA_INFRASTRUCTURE_EVIDENCE = "DATA_INFRASTRUCTURE_EVIDENCE"


class EvidenceLevel(StrEnum):
    STRATEGY_LEVEL = "STRATEGY_LEVEL"
    SIGNAL_LEVEL = "SIGNAL_LEVEL"
    DATA_INFRASTRUCTURE_LEVEL = "DATA_INFRASTRUCTURE_LEVEL"
    IMPLEMENTATION_LEVEL = "IMPLEMENTATION_LEVEL"
    GOVERNANCE_LEVEL = "GOVERNANCE_LEVEL"


class EvidenceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    HISTORICAL = "HISTORICAL"
    SUPERSEDED = "SUPERSEDED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    NOT_VALIDATED = "NOT_VALIDATED"
    BLOCKED = "BLOCKED"


class RegistryEntityType(StrEnum):
    LINEAGE_NODE = "LINEAGE_NODE"
    LINEAGE_EDGE = "LINEAGE_EDGE"
    STRATEGY = "STRATEGY"
    EVIDENCE = "EVIDENCE"
    ARTIFACT = "ARTIFACT"


class RegistryEventType(StrEnum):
    REGISTERED = "REGISTERED"
    TRANSITIONED = "TRANSITIONED"
    DEPRECATED = "DEPRECATED"
    SUPERSEDED = "SUPERSEDED"


def _validate_hash(value: str | None, field_name: str) -> str | None:
    if value is not None and not HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


class LineageNode(ImmutableDomainModel):
    node_id: str = Field(min_length=1)
    stage: LineageStage
    entity_type: str = Field(min_length=1)
    entity_key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str
    created_at: datetime
    source_system: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: RecordStatus = RecordStatus.ACTIVE

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_hash(value, "content_hash") or ""


class LineageEdge(ImmutableDomainModel):
    edge_id: str = Field(min_length=1)
    parent_node_id: str = Field(min_length=1)
    child_node_id: str = Field(min_length=1)
    relationship_type: LineageRelationship
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_self_cycle(self) -> "LineageEdge":
        if self.parent_node_id == self.child_node_id:
            raise ValueError("lineage edge cannot reference the same parent and child")
        return self


class ProvenanceRecord(ImmutableDomainModel):
    source_name: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    retrieved_at: datetime
    effective_at: datetime | None = None
    published_at: datetime | None = None
    market: str | None = None
    instrument_id: str | None = None
    license_classification: str = Field(min_length=1)
    raw_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("raw_hash")
    @classmethod
    def validate_raw_hash(cls, value: str) -> str:
        return _validate_hash(value, "raw_hash") or ""


class ArtifactRecord(ImmutableDomainModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: ArtifactType
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    path_or_reference: str = Field(min_length=1)
    content_hash: str
    created_at: datetime
    lineage_node_id: str = Field(min_length=1)
    immutability_status: ArtifactImmutabilityStatus = (
        ArtifactImmutabilityStatus.IMMUTABLE
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_hash(value, "content_hash") or ""


class StrategyRecord(ImmutableDomainModel):
    strategy_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    lifecycle_status: StrategyLifecycle
    config_hash: str
    preregistration_hash: str | None = None
    implementation_hash: str | None = None
    created_at: datetime
    updated_at: datetime
    promotion_allowed: bool = False
    validation_status: str = Field(min_length=1)
    production_status: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config_hash", "preregistration_hash", "implementation_hash")
    @classmethod
    def validate_hashes(cls, value: str | None, info: Any) -> str | None:
        return _validate_hash(value, info.field_name)

    @model_validator(mode="after")
    def validate_dates_and_promotion(self) -> "StrategyRecord":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if (
            self.lifecycle_status == StrategyLifecycle.PRODUCTION_CANDIDATE
            and not self.promotion_allowed
        ):
            raise ValueError("production candidates require promotion_allowed=true")
        return self


class EvidenceRecord(ImmutableDomainModel):
    evidence_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    classification: EvidenceClassification
    evidence_level: EvidenceLevel
    status: EvidenceStatus
    strategy_id: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    lineage_node_ids: tuple[str, ...] = Field(min_length=1)
    created_at: datetime
    effective_period: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistryEvent(ImmutableDomainModel):
    event_id: str = Field(min_length=1)
    entity_type: RegistryEntityType
    entity_id: str = Field(min_length=1)
    event_type: RegistryEventType
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime
    related_artifact_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_lineage_node(
    *,
    stage: LineageStage,
    entity_type: str,
    entity_key: str,
    version: str,
    content_hash: str,
    created_at: datetime,
    source_system: str,
    metadata: dict[str, Any] | None = None,
    status: RecordStatus = RecordStatus.ACTIVE,
) -> LineageNode:
    node_id = deterministic_id(
        "LIN-NODE",
        stage,
        entity_type,
        entity_key,
        version,
        content_hash,
        source_system,
    )
    return LineageNode(
        node_id=node_id,
        stage=stage,
        entity_type=entity_type,
        entity_key=entity_key,
        version=version,
        content_hash=content_hash,
        created_at=created_at,
        source_system=source_system,
        metadata=metadata or {},
        status=status,
    )


def build_lineage_edge(
    *,
    parent_node_id: str,
    child_node_id: str,
    relationship_type: LineageRelationship,
    created_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> LineageEdge:
    edge_id = deterministic_id(
        "LIN-EDGE", parent_node_id, child_node_id, relationship_type
    )
    return LineageEdge(
        edge_id=edge_id,
        parent_node_id=parent_node_id,
        child_node_id=child_node_id,
        relationship_type=relationship_type,
        created_at=created_at,
        metadata=metadata or {},
    )


def build_artifact_record(
    *,
    artifact_type: ArtifactType,
    name: str,
    version: str,
    path_or_reference: str,
    content_hash: str,
    created_at: datetime,
    lineage_node_id: str,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRecord:
    artifact_id = deterministic_id(
        "ART", artifact_type, name, version, path_or_reference, content_hash
    )
    return ArtifactRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version=version,
        path_or_reference=path_or_reference,
        content_hash=content_hash,
        created_at=created_at,
        lineage_node_id=lineage_node_id,
        metadata=metadata or {},
    )


def evidence_content_hash(record: EvidenceRecord) -> str:
    return canonical_hash(record)


__all__ = (
    "ArtifactImmutabilityStatus",
    "ArtifactRecord",
    "ArtifactType",
    "EvidenceClassification",
    "EvidenceLevel",
    "EvidenceRecord",
    "EvidenceStatus",
    "ImmutableDomainModel",
    "LineageEdge",
    "LineageNode",
    "LineageRelationship",
    "LineageStage",
    "ProvenanceRecord",
    "RecordStatus",
    "RegistryEntityType",
    "RegistryEvent",
    "RegistryEventType",
    "StrategyLifecycle",
    "StrategyRecord",
    "build_artifact_record",
    "build_lineage_edge",
    "build_lineage_node",
    "evidence_content_hash",
)

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


INTERSIGNAL_DATA_HEALTH_V1 = "INTERSIGNAL_DATA_HEALTH_V1"


class DataApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("generated_at", "updated_at", "created_at", check_fields=False)
    @classmethod
    def aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Data API timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class DataAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class DataMeta(DataApiModel):
    read_only: bool = True
    source_contract: str = "INTERSIGNAL_PLATFORM_FOUNDATION_V1"
    internal_paths_exposed: bool = False
    runtime_fixtures: bool = False
    unavailable_sections: tuple[str, ...] = ()


class DataSourceView(DataApiModel):
    source_id: str
    name: str
    domain: str
    status: str
    research_use: str
    summary: str
    freshness: str
    coverage_pct: Decimal | None = None
    gap_count: int | None = Field(default=None, ge=0)
    limitations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class LineageNodeView(DataApiModel):
    node_id: str
    stage: str
    entity_type: str
    label: str
    version: str
    source_system: str
    status: str
    created_at: datetime
    parent_count: int = Field(ge=0)
    child_count: int = Field(ge=0)


class LineageSummaryView(DataApiModel):
    integrity_status: str
    broken_reference_count: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    nodes: tuple[LineageNodeView, ...] = ()


class DataLimitationView(DataApiModel):
    limitation_id: str
    title: str
    status: str
    severity: str
    summary: str
    impact: str
    resolution: str
    related_source_id: str


class DataResponse(DataApiModel):
    version: str = INTERSIGNAL_DATA_HEALTH_V1
    generated_at: datetime
    status: DataAvailability
    reason: str | None = None
    meta: DataMeta = Field(default_factory=DataMeta)


class DataOverviewResponse(DataResponse):
    sources: tuple[DataSourceView, ...] = ()
    lineage: LineageSummaryView | None = None
    limitations: tuple[DataLimitationView, ...] = ()


class DataSourcesResponse(DataResponse):
    items: tuple[DataSourceView, ...] = ()
    total_count: int = Field(ge=0)


class DataLineageResponse(DataResponse):
    lineage: LineageSummaryView | None = None


class DataLimitationsResponse(DataResponse):
    items: tuple[DataLimitationView, ...] = ()
    total_count: int = Field(ge=0)


__all__ = (
    "INTERSIGNAL_DATA_HEALTH_V1",
    "DataAvailability",
    "DataLimitationsResponse",
    "DataLineageResponse",
    "DataOverviewResponse",
    "DataSourcesResponse",
)

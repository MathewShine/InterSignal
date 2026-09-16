from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.platform.hashing import canonical_hash
from app.platform.models import (
    ArtifactRecord,
    EvidenceClassification,
    EvidenceLevel,
    EvidenceRecord,
    LineageEdge,
    LineageNode,
    LineageStage,
    RegistryEntityType,
    RegistryEvent,
    StrategyLifecycle,
    StrategyRecord,
)
from app.platform.repositories import (
    ArtifactRegistryRepository,
    EvidenceRegistryRepository,
    LineageRepository,
    RegistryEventRepository,
    StrategyRegistryRepository,
)
from app.research_workbench.errors import (
    ArtifactNotFound,
    EvidenceNotFound,
    InvalidWorkbenchQuery,
    LineageNodeNotFound,
    ResearchFamilyNotFound,
    StrategyNotFound,
    WorkbenchIntegrityError,
)
from app.research_workbench.models import (
    BlockedResearchSummary,
    EvidenceSummary,
    FamilySortField,
    ResearchArtifactSummary,
    ResearchConclusion,
    ResearchConclusionClassification,
    ResearchEvidenceDetail,
    ResearchFamilyDetail,
    ResearchFamilyPage,
    ResearchFamilyQuery,
    ResearchFamilySummary,
    ResearchLineageSummary,
    ResearchLineageTrace,
    ResearchProgrammeSummary,
    ResearchStrategyDetail,
    ResearchStrategySummary,
    ResearchTimelineEvent,
    ResearchWorkbenchIntegritySummary,
    ResearchWorkbenchSnapshot,
    ValidationSummary,
    WorkbenchIntegrityStatus,
)


SNAPSHOT_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_SNAPSHOT_V1"

DEFAULT_PROGRAMME_STATE: dict[str, str] = {
    "strategy_research_status": "PAUSED",
    "a_to_g_cycle_status": "COMPLETE_NO_VALIDATED_STRATEGY",
    "strategy_v2_status": "NOT_CREATED",
    "family_h_status": "NOT_PLANNED",
    "paper_readiness": "NOT_READY",
    "live_readiness": "NOT_READY",
    "primary_programme": "PRODUCT_PLATFORM_PROGRAM",
    "secondary_programme": "FORWARD_DATA_PROGRAM",
}

_CONCLUSIONS: dict[str, tuple[ResearchConclusionClassification, str]] = {
    "A": (
        ResearchConclusionClassification.CLOSED_NOT_ADVANCED,
        "Strong historical development evidence did not generalize; the family is closed for the current cycle.",
    ),
    "B": (
        ResearchConclusionClassification.NO_INCREMENTAL_EDGE,
        "The tested construction showed no incremental edge over relative momentum.",
    ),
    "C": (
        ResearchConclusionClassification.REUSABLE_SIGNAL_ONLY,
        "Compression remains reusable signal evidence, not a portfolio-ready strategy.",
    ),
    "D": (
        ResearchConclusionClassification.DATA_BLOCKED,
        "Evaluation is blocked by intraday data continuity and is not a strategy failure.",
    ),
    "E": (
        ResearchConclusionClassification.NEGATIVE_DEVELOPMENT,
        "The tested development treatment was not supported for advancement.",
    ),
    "F": (
        ResearchConclusionClassification.SOURCE_BLOCKED,
        "Evaluation is blocked by authorized historical source availability and is not a strategy failure.",
    ),
    "G": (
        ResearchConclusionClassification.NEGATIVE_OVERLAY,
        "The exact SMA200 overlay was not supported for advancement.",
    ),
}

_BLOCKS: dict[str, dict[str, Any]] = {
    "D": {
        "block_type": "DATA_BLOCKED",
        "reason": "intraday continuity below frozen threshold",
        "resume_requirements": (
            "Provide an intraday source meeting the frozen continuity threshold",
        ),
        "data_or_source": "DATA",
    },
    "F": {
        "block_type": "SOURCE_BLOCKED",
        "reason": "authorized catalyst historical source unavailable",
        "resume_requirements": (
            "Authorize a reproducible historical catalyst source",
        ),
        "data_or_source": "SOURCE",
    },
}


def _family_code(value: str) -> str:
    normalized = value.strip().upper()
    if normalized.startswith("FAMILY_"):
        normalized = normalized.removeprefix("FAMILY_")
    return normalized


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


class ResearchWorkbenchService:
    """Read-only projections over immutable platform registry interfaces."""

    def __init__(
        self,
        *,
        lineage: LineageRepository,
        strategies: StrategyRegistryRepository,
        evidence: EvidenceRegistryRepository,
        artifacts: ArtifactRegistryRepository,
        events: RegistryEventRepository,
        programme_state: Mapping[str, str] | None = None,
    ) -> None:
        self._lineage = lineage
        self._strategies = strategies
        self._evidence = evidence
        self._artifacts = artifacts
        self._events = events
        self._programme_state = {
            **DEFAULT_PROGRAMME_STATE,
            **dict(programme_state or {}),
        }

    @classmethod
    def from_repository(
        cls,
        repository: object,
        *,
        programme_state: Mapping[str, str] | None = None,
    ) -> "ResearchWorkbenchService":
        required = (
            LineageRepository,
            StrategyRegistryRepository,
            EvidenceRegistryRepository,
            ArtifactRegistryRepository,
            RegistryEventRepository,
        )
        if not all(isinstance(repository, interface) for interface in required):
            raise TypeError("Repository does not implement all platform interfaces")
        return cls(
            lineage=repository,
            strategies=repository,
            evidence=repository,
            artifacts=repository,
            events=repository,
            programme_state=programme_state,
        )

    def _all_strategies(self) -> list[StrategyRecord]:
        return sorted(
            self._strategies.list_strategies(),
            key=lambda row: (row.strategy_family, row.strategy_id),
        )

    def _family_strategies(self, family_id: str) -> list[StrategyRecord]:
        family = _family_code(family_id)
        rows = [
            row for row in self._all_strategies() if row.strategy_family == family
        ]
        if not rows:
            raise ResearchFamilyNotFound(f"Research family not found: {family_id}")
        return rows

    def _strategy(self, strategy_id: str) -> StrategyRecord:
        record = self._strategies.get_strategy(strategy_id)
        if record is None:
            raise StrategyNotFound(f"Strategy not found: {strategy_id}")
        return record

    def _evidence_record(self, evidence_id: str) -> EvidenceRecord:
        record = self._evidence.get_evidence(evidence_id)
        if record is None:
            raise EvidenceNotFound(f"Evidence not found: {evidence_id}")
        return record

    def _artifact(self, artifact_id: str) -> ArtifactRecord:
        record = self._artifacts.get_artifact(artifact_id)
        if record is None:
            raise ArtifactNotFound(f"Artifact not found: {artifact_id}")
        return record

    def _family_evidence(self, family_id: str) -> list[EvidenceRecord]:
        strategy_ids = {
            row.strategy_id for row in self._family_strategies(family_id)
        }
        return [
            row
            for row in self._evidence.list_evidence()
            if row.strategy_id in strategy_ids
        ]

    @staticmethod
    def _evidence_summary(records: Sequence[EvidenceRecord]) -> EvidenceSummary:
        counts = Counter(row.classification for row in records)
        return EvidenceSummary(
            positive_evidence_count=counts[
                EvidenceClassification.POSITIVE_EVIDENCE
            ],
            negative_evidence_count=counts[
                EvidenceClassification.NEGATIVE_EVIDENCE
            ],
            blocked_research_count=counts[
                EvidenceClassification.BLOCKED_RESEARCH
            ],
            validation_evidence_count=counts[
                EvidenceClassification.VALIDATION_EVIDENCE
            ],
            post_outcome_evidence_count=counts[
                EvidenceClassification.POST_OUTCOME_EVIDENCE
            ],
            data_infrastructure_evidence_count=counts[
                EvidenceClassification.DATA_INFRASTRUCTURE_EVIDENCE
            ],
            total_count=len(records),
        )

    @staticmethod
    def _evidence_detail(record: EvidenceRecord) -> ResearchEvidenceDetail:
        return ResearchEvidenceDetail(
            evidence_id=record.evidence_id,
            classification=record.classification,
            level=record.evidence_level,
            status=record.status,
            title=record.title,
            description=record.description,
            strategy_linkage=record.strategy_id,
            artifact_linkage=tuple(sorted(record.source_artifact_ids)),
            lineage_linkage=tuple(sorted(record.lineage_node_ids)),
            effective_period=record.effective_period,
            confidence=record.confidence,
            limitations=tuple(record.limitations),
            metadata=dict(record.metadata),
        )

    def get_evidence_detail(self, evidence_id: str) -> ResearchEvidenceDetail:
        return self._evidence_detail(self._evidence_record(evidence_id))

    def list_evidence(
        self,
        *,
        family_id: str | None = None,
        classification: EvidenceClassification | str | None = None,
        level: EvidenceLevel | str | None = None,
    ) -> tuple[ResearchEvidenceDetail, ...]:
        records = (
            self._family_evidence(family_id)
            if family_id is not None
            else self._evidence.list_evidence()
        )
        try:
            classification_value = (
                EvidenceClassification(classification)
                if classification is not None
                else None
            )
            level_value = EvidenceLevel(level) if level is not None else None
        except ValueError as error:
            raise InvalidWorkbenchQuery(str(error)) from error
        if classification_value is not None:
            records = [
                row for row in records if row.classification == classification_value
            ]
        if level_value is not None:
            records = [row for row in records if row.evidence_level == level_value]
        return tuple(
            self._evidence_detail(row)
            for row in sorted(records, key=lambda item: item.evidence_id)
        )

    @staticmethod
    def _artifact_summary(record: ArtifactRecord) -> ResearchArtifactSummary:
        return ResearchArtifactSummary(
            artifact_id=record.artifact_id,
            artifact_type=record.artifact_type.value,
            name=record.name,
            version=record.version,
            content_hash=record.content_hash,
            reference=record.path_or_reference,
            immutability_status=record.immutability_status.value,
            lineage_node_id=record.lineage_node_id,
            created_at=record.created_at,
            metadata=dict(record.metadata),
        )

    def get_artifact_summary(self, artifact_id: str) -> ResearchArtifactSummary:
        return self._artifact_summary(self._artifact(artifact_id))

    def list_evidence_artifacts(
        self, evidence_id: str
    ) -> tuple[ResearchArtifactSummary, ...]:
        record = self._evidence_record(evidence_id)
        return tuple(
            self._artifact_summary(self._artifact(artifact_id))
            for artifact_id in sorted(record.source_artifact_ids)
        )

    def _strategy_artifact_ids(self, strategy_id: str) -> tuple[str, ...]:
        strategy = self._strategy(strategy_id)
        artifact_ids = list(strategy.metadata.get("source_artifact_ids", ()))
        for record in self._evidence.get_evidence_for_strategy(strategy_id):
            artifact_ids.extend(record.source_artifact_ids)
        return _unique(artifact_ids)

    def list_strategy_artifacts(
        self, strategy_id: str
    ) -> tuple[ResearchArtifactSummary, ...]:
        return tuple(
            self._artifact_summary(self._artifact(artifact_id))
            for artifact_id in self._strategy_artifact_ids(strategy_id)
        )

    def list_family_artifacts(
        self, family_id: str
    ) -> tuple[ResearchArtifactSummary, ...]:
        artifact_ids: list[str] = []
        for strategy in self._family_strategies(family_id):
            artifact_ids.extend(self._strategy_artifact_ids(strategy.strategy_id))
        return tuple(
            self._artifact_summary(self._artifact(artifact_id))
            for artifact_id in _unique(artifact_ids)
        )

    def _conclusion(self, family_id: str) -> ResearchConclusion:
        family = _family_code(family_id)
        self._family_strategies(family)
        try:
            classification, summary = _CONCLUSIONS[family]
        except KeyError as error:
            raise ResearchFamilyNotFound(
                f"No conclusion projection for family: {family_id}"
            ) from error
        evidence = self._family_evidence(family)
        limitations = _unique(
            [item for row in evidence for item in row.limitations]
        )
        metadata: dict[str, Any] = {"family_id": family}
        if family == "A":
            metadata["historical_development_classification"] = (
                ResearchConclusionClassification.STRONG_DEVELOPMENT_NOT_GENERALIZED
            )
        return ResearchConclusion(
            classification=classification,
            summary=summary,
            basis=tuple(sorted(row.evidence_id for row in evidence)),
            limitations=limitations,
            advancement_allowed=False,
            metadata=metadata,
        )

    def get_research_conclusion(self, family_id: str) -> ResearchConclusion:
        return self._conclusion(family_id)

    def get_validation_summary(self, family_id: str) -> ValidationSummary:
        strategy = self._family_strategies(family_id)[0]
        evidence = self._family_evidence(family_id)
        formal = [
            row
            for row in evidence
            if row.classification == EvidenceClassification.VALIDATION_EVIDENCE
        ]
        post = [
            row
            for row in evidence
            if row.classification == EvidenceClassification.POST_OUTCOME_EVIDENCE
        ]
        formal_result = None
        if formal:
            formal_result = str(
                formal[0].metadata.get(
                    "formal_validation_status", strategy.validation_status
                )
            )
        post_result = None
        pristine_holdout = None
        if post:
            post_result = str(
                post[0].metadata.get("generalization_indication", "UNSPECIFIED")
            )
            pristine_holdout = bool(
                post[0].metadata.get("pristine_holdout_evidence", False)
            )
        related = formal + post
        return ValidationSummary(
            validation_status=strategy.validation_status,
            formal_result=formal_result,
            generalization_result=post_result,
            post_outcome_result=post_result,
            advancement_status=str(
                strategy.metadata.get(
                    "source_governance_status",
                    self._conclusion(family_id).classification.value,
                )
            ),
            run_count=len(related),
            remaining_runs=0,
            pristine_holdout=pristine_holdout,
            limitations=_unique(
                [item for row in related for item in row.limitations]
            ),
            related_artifacts=_unique(
                [item for row in related for item in row.source_artifact_ids]
            ),
            metadata={
                "formal_evidence_ids": tuple(row.evidence_id for row in formal),
                "post_outcome_evidence_ids": tuple(row.evidence_id for row in post),
            },
        )

    def get_blocked_research(
        self, family_id: str
    ) -> BlockedResearchSummary | None:
        family = _family_code(family_id)
        self._family_strategies(family)
        if family not in _BLOCKS:
            return None
        values = _BLOCKS[family]
        evidence = [
            row
            for row in self._family_evidence(family)
            if row.classification
            in {
                EvidenceClassification.BLOCKED_RESEARCH,
                EvidenceClassification.DATA_INFRASTRUCTURE_EVIDENCE,
            }
        ]
        return BlockedResearchSummary(
            family_id=family,
            block_type=values["block_type"],
            reason=values["reason"],
            resume_requirements=values["resume_requirements"],
            data_or_source=values["data_or_source"],
            status="BLOCKED",
            related_evidence=tuple(sorted(row.evidence_id for row in evidence)),
            related_artifacts=_unique(
                [item for row in evidence for item in row.source_artifact_ids]
            ),
        )

    def list_blocked_research(self) -> tuple[BlockedResearchSummary, ...]:
        rows = [self.get_blocked_research(family) for family in sorted(_BLOCKS)]
        return tuple(row for row in rows if row is not None)

    def _relevant_entity_ids(self, strategy_id: str) -> set[str]:
        evidence = self._evidence.get_evidence_for_strategy(strategy_id)
        evidence_ids = {row.evidence_id for row in evidence}
        artifact_ids = set(self._strategy_artifact_ids(strategy_id))
        nodes = self._lineage.list_lineage_nodes()
        lineage_ids = {
            row.lineage_node_id
            for row in self._artifacts.list_artifacts()
            if row.artifact_id in artifact_ids
        }
        lineage_ids.update(
            item for row in evidence for item in row.lineage_node_ids
        )
        lineage_ids.update(
            row.node_id
            for row in nodes
            if row.entity_type == "EVIDENCE_RECORD"
            and row.entity_key in evidence_ids
        )
        edge_ids = {
            edge.edge_id
            for edge in self._lineage.list_lineage_edges()
            if edge.parent_node_id in lineage_ids or edge.child_node_id in lineage_ids
        }
        return {
            strategy_id,
            *evidence_ids,
            *artifact_ids,
            *lineage_ids,
            *edge_ids,
        }

    @staticmethod
    def _timeline_event(
        event: RegistryEvent,
        *,
        family_id: str | None,
        strategy_id: str | None,
    ) -> ResearchTimelineEvent:
        return ResearchTimelineEvent(
            event_id=event.event_id,
            timestamp=event.created_at,
            family_id=family_id,
            strategy_id=strategy_id,
            event_type=event.event_type.value,
            previous_state=(
                dict(event.previous_state) if event.previous_state is not None else None
            ),
            new_state=dict(event.new_state),
            reason=event.reason,
            related_artifacts=tuple(event.related_artifact_ids),
            metadata={
                **dict(event.metadata),
                "registry_entity_type": event.entity_type.value,
                "registry_entity_id": event.entity_id,
                "actor": event.actor,
            },
        )

    def get_strategy_timeline(
        self, strategy_id: str
    ) -> tuple[ResearchTimelineEvent, ...]:
        strategy = self._strategy(strategy_id)
        entity_ids = self._relevant_entity_ids(strategy_id)
        events = [
            event
            for event in self._events.list_events()
            if event.entity_id in entity_ids
        ]
        return tuple(
            self._timeline_event(
                event,
                family_id=strategy.strategy_family,
                strategy_id=strategy_id,
            )
            for event in sorted(events, key=lambda row: (row.created_at, row.event_id))
        )

    def get_family_timeline(
        self, family_id: str
    ) -> tuple[ResearchTimelineEvent, ...]:
        family = _family_code(family_id)
        projected: dict[str, ResearchTimelineEvent] = {}
        for strategy in self._family_strategies(family):
            for event in self.get_strategy_timeline(strategy.strategy_id):
                projected[event.event_id] = event
        return tuple(
            sorted(projected.values(), key=lambda row: (row.timestamp, row.event_id))
        )

    def _lineage_graph(
        self,
    ) -> tuple[dict[str, LineageNode], tuple[LineageEdge, ...]]:
        nodes = {row.node_id: row for row in self._lineage.list_lineage_nodes()}
        edges = tuple(self._lineage.list_lineage_edges())
        return nodes, edges

    @staticmethod
    def _cycle_count(
        nodes: Mapping[str, LineageNode], edges: Sequence[LineageEdge]
    ) -> int:
        children: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.parent_node_id in nodes and edge.child_node_id in nodes:
                children[edge.parent_node_id].append(edge.child_node_id)
        state: dict[str, int] = {}
        cycles = 0

        def visit(node_id: str) -> None:
            nonlocal cycles
            state[node_id] = 1
            for child in sorted(children[node_id]):
                if state.get(child, 0) == 0:
                    visit(child)
                elif state.get(child) == 1:
                    cycles += 1
            state[node_id] = 2

        for node_id in sorted(nodes):
            if state.get(node_id, 0) == 0:
                visit(node_id)
        return cycles

    def trace_research_lineage(
        self,
        node_id: str,
        *,
        max_nodes: int = 256,
        max_depth: int = 32,
    ) -> ResearchLineageTrace:
        if max_nodes <= 0 or max_depth <= 0:
            raise InvalidWorkbenchQuery("max_nodes and max_depth must be positive")
        nodes, edges = self._lineage_graph()
        if node_id not in nodes:
            raise LineageNodeNotFound(f"Lineage node not found: {node_id}")
        broken = [
            edge.edge_id
            for edge in edges
            if edge.parent_node_id not in nodes or edge.child_node_id not in nodes
        ]
        if broken:
            raise WorkbenchIntegrityError(
                f"Lineage graph contains missing references: {', '.join(sorted(broken))}"
            )
        if self._cycle_count(nodes, edges):
            raise WorkbenchIntegrityError("Lineage graph contains a cycle")
        parents: dict[str, list[tuple[str, LineageEdge]]] = defaultdict(list)
        children: dict[str, list[tuple[str, LineageEdge]]] = defaultdict(list)
        for edge in edges:
            parents[edge.child_node_id].append((edge.parent_node_id, edge))
            children[edge.parent_node_id].append((edge.child_node_id, edge))

        def walk(
            adjacency: Mapping[str, list[tuple[str, LineageEdge]]]
        ) -> tuple[set[str], set[str]]:
            found = {node_id}
            edge_ids: set[str] = set()
            pending: deque[tuple[str, int]] = deque([(node_id, 0)])
            while pending:
                current, depth = pending.popleft()
                neighbours = sorted(
                    adjacency.get(current, ()), key=lambda item: item[1].edge_id
                )
                if neighbours and depth >= max_depth:
                    raise WorkbenchIntegrityError(
                        f"Lineage traversal exceeded max_depth={max_depth}"
                    )
                for neighbour, edge in neighbours:
                    edge_ids.add(edge.edge_id)
                    if neighbour in found:
                        continue
                    if len(found) >= max_nodes:
                        raise WorkbenchIntegrityError(
                            f"Lineage traversal exceeded max_nodes={max_nodes}"
                        )
                    found.add(neighbour)
                    pending.append((neighbour, depth + 1))
            return found, edge_ids

        upstream, upstream_edges = walk(parents)
        downstream, downstream_edges = walk(children)
        selected_ids = upstream | downstream
        selected_edge_ids = upstream_edges | downstream_edges
        selected_edges = tuple(
            sorted(
                (edge for edge in edges if edge.edge_id in selected_edge_ids),
                key=lambda row: row.edge_id,
            )
        )
        roots = tuple(
            sorted(
                item
                for item in upstream
                if nodes[item].stage == LineageStage.SOURCE and not parents[item]
            )
        )
        terminals = tuple(
            sorted(
                item
                for item in downstream
                if nodes[item].stage == LineageStage.EVIDENCE and not children[item]
            )
        )
        summary = ResearchLineageSummary(
            node_id=node_id,
            upstream_count=len(upstream - {node_id}),
            downstream_count=len(downstream - {node_id}),
            root_sources=roots,
            terminal_evidence=terminals,
            path_summary=tuple(
                f"{edge.parent_node_id}-[{edge.relationship_type.value}]->{edge.child_node_id}"
                for edge in selected_edges
            ),
            integrity_status=WorkbenchIntegrityStatus.HEALTHY,
        )
        return ResearchLineageTrace(
            summary=summary,
            nodes=tuple(nodes[item] for item in sorted(selected_ids)),
            edges=selected_edges,
            max_nodes=max_nodes,
            max_depth=max_depth,
        )

    def get_strategy_detail(self, strategy_id: str) -> ResearchStrategyDetail:
        strategy = self._strategy(strategy_id)
        history = tuple(self._strategies.get_strategy_history(strategy_id))
        evidence = self._evidence.get_evidence_for_strategy(strategy_id)
        grouped: dict[
            EvidenceClassification, tuple[ResearchEvidenceDetail, ...]
        ] = {}
        for classification in EvidenceClassification:
            rows = [row for row in evidence if row.classification == classification]
            grouped[classification] = tuple(
                self._evidence_detail(row)
                for row in sorted(rows, key=lambda item: item.evidence_id)
            )
        artifacts = self.list_strategy_artifacts(strategy_id)
        lineage_ids = _unique(
            [row.lineage_node_id for row in artifacts]
            + [item for row in evidence for item in row.lineage_node_ids]
        )
        return ResearchStrategyDetail(
            strategy_record=strategy,
            lifecycle_history=history,
            config_hashes=_unique([row.config_hash for row in history]),
            preregistration_hashes=_unique(
                [row.preregistration_hash or "" for row in history]
            ),
            implementation_hash=strategy.implementation_hash,
            validation_state=strategy.validation_status,
            production_state=strategy.production_status,
            evidence_by_classification=grouped,
            artifacts=artifacts,
            lineage=tuple(
                self.trace_research_lineage(item).summary for item in lineage_ids
            ),
            limitations=_unique(
                [item for row in evidence for item in row.limitations]
            ),
            current_conclusion=self._conclusion(strategy.strategy_family),
        )

    def _family_summary(self, family_id: str) -> ResearchFamilySummary:
        family = _family_code(family_id)
        strategies = self._family_strategies(family)
        evidence = self._family_evidence(family)
        evidence_summary = self._evidence_summary(evidence)
        timeline = self.get_family_timeline(family)
        latest = max(
            (row.timestamp for row in timeline),
            default=max(row.updated_at for row in strategies),
        )
        conclusion = self._conclusion(family)
        blocked = self.get_blocked_research(family)
        return ResearchFamilySummary(
            family_id=family,
            family_name=strategies[0].name,
            current_status=conclusion.classification.value,
            lifecycle_status=strategies[0].lifecycle_status,
            evidence_summary=evidence_summary,
            validation_status=strategies[0].validation_status,
            block_reason=blocked.reason if blocked else None,
            strategy_count=len(strategies),
            experiment_count=sum(
                len(self._strategies.get_strategy_history(row.strategy_id))
                for row in strategies
            ),
            positive_evidence_count=evidence_summary.positive_evidence_count,
            negative_evidence_count=evidence_summary.negative_evidence_count,
            blocked_evidence_count=evidence_summary.blocked_research_count,
            latest_activity_at=latest,
            production_candidate=any(
                row.lifecycle_status == StrategyLifecycle.PRODUCTION_CANDIDATE
                for row in strategies
            ),
            metadata={
                "strategy_ids": tuple(row.strategy_id for row in strategies),
                "source_governance_status": strategies[0].metadata.get(
                    "source_governance_status"
                ),
            },
        )

    @staticmethod
    def _validate_query(query: ResearchFamilyQuery) -> None:
        if query.limit <= 0 or query.limit > 500:
            raise InvalidWorkbenchQuery("limit must be between 1 and 500")
        if query.offset < 0:
            raise InvalidWorkbenchQuery("offset cannot be negative")
        if query.start_at and query.end_at and query.start_at > query.end_at:
            raise InvalidWorkbenchQuery("start_at cannot be after end_at")

    def _filtered_families(
        self, query: ResearchFamilyQuery
    ) -> list[ResearchFamilySummary]:
        self._validate_query(query)
        rows = [
            self._family_summary(family)
            for family in sorted({row.strategy_family for row in self._all_strategies()})
        ]
        if query.family_status:
            statuses = {item.upper() for item in query.family_status}
            rows = [row for row in rows if row.current_status.upper() in statuses]
        if query.lifecycle:
            lifecycle = set(query.lifecycle)
            rows = [row for row in rows if row.lifecycle_status in lifecycle]
        if query.evidence_classification:
            classifications = set(query.evidence_classification)
            rows = [
                row
                for row in rows
                if any(
                    item.classification in classifications
                    for item in self._family_evidence(row.family_id)
                )
            ]
        if query.evidence_level:
            levels = set(query.evidence_level)
            rows = [
                row
                for row in rows
                if any(
                    item.evidence_level in levels
                    for item in self._family_evidence(row.family_id)
                )
            ]
        if query.blocked_state is not None:
            rows = [
                row
                for row in rows
                if (self.get_blocked_research(row.family_id) is not None)
                == query.blocked_state
            ]
        if query.validation_state:
            validation = {item.upper() for item in query.validation_state}
            rows = [
                row for row in rows if row.validation_status.upper() in validation
            ]
        if query.start_at:
            rows = [
                row for row in rows if row.latest_activity_at >= query.start_at
            ]
        if query.end_at:
            rows = [row for row in rows if row.latest_activity_at <= query.end_at]
        key = {
            FamilySortField.NAME: lambda row: (row.family_name.casefold(), row.family_id),
            FamilySortField.LATEST_ACTIVITY: lambda row: (
                row.latest_activity_at,
                row.family_id,
            ),
            FamilySortField.STATUS: lambda row: (
                row.current_status,
                row.family_id,
            ),
            FamilySortField.FAMILY_CODE: lambda row: (row.family_id,),
        }[query.sort_by]
        return sorted(rows, key=key, reverse=query.descending)

    def list_research_families(
        self,
        *,
        family_status: str | None = None,
        lifecycle: StrategyLifecycle | str | None = None,
        evidence_classification: EvidenceClassification | str | None = None,
        evidence_level: EvidenceLevel | str | None = None,
        blocked_state: bool | None = None,
        validation_state: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        sort_by: FamilySortField | str = FamilySortField.FAMILY_CODE,
        descending: bool = False,
    ) -> tuple[ResearchFamilySummary, ...]:
        try:
            query = ResearchFamilyQuery(
                family_status=(family_status,) if family_status else (),
                lifecycle=(StrategyLifecycle(lifecycle),) if lifecycle else (),
                evidence_classification=(
                    (EvidenceClassification(evidence_classification),)
                    if evidence_classification
                    else ()
                ),
                evidence_level=(EvidenceLevel(evidence_level),) if evidence_level else (),
                blocked_state=blocked_state,
                validation_state=(validation_state,) if validation_state else (),
                start_at=start_at,
                end_at=end_at,
                sort_by=FamilySortField(sort_by),
                descending=descending,
            )
        except (ValueError, TypeError) as error:
            raise InvalidWorkbenchQuery(str(error)) from error
        return tuple(self._filtered_families(query))

    def query_research_families(
        self, query: ResearchFamilyQuery
    ) -> ResearchFamilyPage:
        rows = self._filtered_families(query)
        return ResearchFamilyPage(
            items=tuple(rows[query.offset : query.offset + query.limit]),
            limit=query.limit,
            offset=query.offset,
            total_count=len(rows),
        )

    def get_family_detail(self, family_id: str) -> ResearchFamilyDetail:
        family = _family_code(family_id)
        strategies = self._family_strategies(family)
        evidence_records = self._family_evidence(family)
        evidence = tuple(
            self._evidence_detail(row)
            for row in sorted(evidence_records, key=lambda item: item.evidence_id)
        )
        artifacts = self.list_family_artifacts(family)
        blocked = self.get_blocked_research(family)
        return ResearchFamilyDetail(
            family_id=family,
            family_name=strategies[0].name,
            description=strategies[0].description,
            current_lifecycle=strategies[0].lifecycle_status,
            strategies=tuple(strategies),
            evidence=evidence,
            events=self.get_family_timeline(family),
            artifacts=artifacts,
            validation_summary=self.get_validation_summary(family),
            blocked_reason=blocked.reason if blocked else None,
            known_limitations=_unique(
                [item for row in evidence_records for item in row.limitations]
            ),
            research_conclusion=self._conclusion(family),
            lineage_references=_unique(
                [row.lineage_node_id for row in artifacts]
                + [item for row in evidence_records for item in row.lineage_node_ids]
            ),
        )

    def get_programme_summary(self) -> ResearchProgrammeSummary:
        strategies = self._all_strategies()
        return ResearchProgrammeSummary(
            strategy_research_status=self._programme_state[
                "strategy_research_status"
            ],
            a_to_g_cycle_status=self._programme_state["a_to_g_cycle_status"],
            validated_strategy_count=sum(
                row.validation_status == "VALIDATED" for row in strategies
            ),
            production_candidate_count=sum(
                row.lifecycle_status == StrategyLifecycle.PRODUCTION_CANDIDATE
                for row in strategies
            ),
            strategy_v2_status=self._programme_state["strategy_v2_status"],
            family_h_status=self._programme_state["family_h_status"],
            paper_readiness=self._programme_state["paper_readiness"],
            live_readiness=self._programme_state["live_readiness"],
            primary_programme=self._programme_state["primary_programme"],
            secondary_programme=self._programme_state["secondary_programme"],
        )

    def get_integrity_summary(self) -> ResearchWorkbenchIntegritySummary:
        strategies = self._all_strategies()
        evidence = self._evidence.list_evidence()
        artifacts = self._artifacts.list_artifacts()
        nodes, edges = self._lineage_graph()
        strategy_ids = {row.strategy_id for row in strategies}
        artifact_by_id = {row.artifact_id: row for row in artifacts}
        details: dict[str, list[str]] = defaultdict(list)

        for strategy in strategies:
            for artifact_id in strategy.metadata.get("source_artifact_ids", ()):
                if artifact_id not in artifact_by_id:
                    details["broken_strategy_refs"].append(
                        f"{strategy.strategy_id}:{artifact_id}"
                    )
        for record in evidence:
            if record.strategy_id not in strategy_ids:
                details["broken_evidence_refs"].append(
                    f"{record.evidence_id}:{record.strategy_id}"
                )
            for artifact_id in record.source_artifact_ids:
                if artifact_id not in artifact_by_id:
                    details["broken_artifact_refs"].append(
                        f"{record.evidence_id}:{artifact_id}"
                    )
            for lineage_id in record.lineage_node_ids:
                if lineage_id not in nodes:
                    details["broken_lineage_refs"].append(
                        f"{record.evidence_id}:{lineage_id}"
                    )
        for artifact in artifacts:
            node = nodes.get(artifact.lineage_node_id)
            if node is None:
                details["broken_artifact_refs"].append(
                    f"{artifact.artifact_id}:{artifact.lineage_node_id}"
                )
            elif node.content_hash != artifact.content_hash:
                details["hash_mismatches"].append(artifact.artifact_id)
        for edge in edges:
            if edge.parent_node_id not in nodes or edge.child_node_id not in nodes:
                details["broken_lineage_refs"].append(edge.edge_id)
        evidence_by_id = {row.evidence_id: row for row in evidence}
        evidence_nodes = {
            row.entity_key: row
            for row in nodes.values()
            if row.entity_type == "EVIDENCE_RECORD"
        }
        for evidence_id, record in evidence_by_id.items():
            node = evidence_nodes.get(evidence_id)
            if node is None:
                details["broken_lineage_refs"].append(
                    f"{evidence_id}:EVIDENCE_NODE"
                )
            elif node.content_hash != canonical_hash(record):
                details["hash_mismatches"].append(evidence_id)
        artifact_hashes = {row.content_hash for row in artifacts}
        for strategy in strategies:
            for label, value in (
                ("config", strategy.config_hash),
                ("preregistration", strategy.preregistration_hash),
                ("implementation", strategy.implementation_hash),
            ):
                if value and value not in artifact_hashes:
                    details["hash_mismatches"].append(
                        f"{strategy.strategy_id}:{label}"
                    )

        collections = (
            [row.strategy_id for row in strategies],
            [row.evidence_id for row in evidence],
            [row.artifact_id for row in artifacts],
            list(nodes),
            [row.edge_id for row in edges],
            [row.event_id for row in self._events.list_events()],
        )
        duplicate_ids = sum(len(items) - len(set(items)) for items in collections)
        cycle_count = self._cycle_count(nodes, edges)
        counts = {
            "broken_strategy_refs": len(details["broken_strategy_refs"]),
            "broken_evidence_refs": len(details["broken_evidence_refs"]),
            "broken_artifact_refs": len(details["broken_artifact_refs"]),
            "broken_lineage_refs": len(details["broken_lineage_refs"]),
            "cycle_count": cycle_count,
            "duplicate_ids": duplicate_ids,
            "hash_mismatches": len(details["hash_mismatches"]),
        }
        status = (
            WorkbenchIntegrityStatus.HEALTHY
            if all(value == 0 for value in counts.values())
            else WorkbenchIntegrityStatus.ERROR
        )
        return ResearchWorkbenchIntegritySummary(
            **counts,
            status=status,
            metadata={
                key: tuple(sorted(values)) for key, values in sorted(details.items())
            },
        )

    def require_integrity(self) -> ResearchWorkbenchIntegritySummary:
        summary = self.get_integrity_summary()
        if summary.status != WorkbenchIntegrityStatus.HEALTHY:
            raise WorkbenchIntegrityError(
                f"Research Workbench integrity status is {summary.status.value}"
            )
        return summary

    def _strategy_summary(self, strategy: StrategyRecord) -> ResearchStrategySummary:
        timeline = self.get_strategy_timeline(strategy.strategy_id)
        latest = max(
            (row.timestamp for row in timeline), default=strategy.updated_at
        )
        evidence = self._evidence.get_evidence_for_strategy(strategy.strategy_id)
        return ResearchStrategySummary(
            strategy_id=strategy.strategy_id,
            family_id=strategy.strategy_family,
            name=strategy.name,
            lifecycle_status=strategy.lifecycle_status,
            validation_state=strategy.validation_status,
            production_state=strategy.production_status,
            evidence_summary=self._evidence_summary(evidence),
            conclusion=self._conclusion(strategy.strategy_family),
            latest_activity_at=latest,
        )

    def export_research_workbench_snapshot(
        self, *, latest_event_limit: int = 25
    ) -> ResearchWorkbenchSnapshot:
        if latest_event_limit <= 0 or latest_event_limit > 500:
            raise InvalidWorkbenchQuery(
                "latest_event_limit must be between 1 and 500"
            )
        integrity = self.require_integrity()
        strategies = self._all_strategies()
        families = self.list_research_families()
        all_projected: dict[str, ResearchTimelineEvent] = {}
        for family in families:
            for event in self.get_family_timeline(family.family_id):
                all_projected.setdefault(event.event_id, event)
        latest_events = tuple(
            sorted(
                all_projected.values(),
                key=lambda row: (row.timestamp, row.event_id),
                reverse=True,
            )[:latest_event_limit]
        )
        registry_events = self._events.list_events()
        generated_at = max(
            (row.created_at for row in registry_events),
            default=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
        payload = {
            "snapshot_version": SNAPSHOT_VERSION,
            "generated_at": generated_at,
            "programme_summary": self.get_programme_summary(),
            "families": families,
            "strategy_summaries": tuple(
                self._strategy_summary(row) for row in strategies
            ),
            "evidence_summary": self._evidence_summary(
                self._evidence.list_evidence()
            ),
            "blocked_studies": self.list_blocked_research(),
            "latest_events": latest_events,
            "integrity_summary": integrity,
        }
        return ResearchWorkbenchSnapshot(
            **payload,
            snapshot_hash=canonical_hash(payload),
        )


__all__ = ("DEFAULT_PROGRAMME_STATE", "ResearchWorkbenchService", "SNAPSHOT_VERSION")

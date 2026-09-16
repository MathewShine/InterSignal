from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.platform.hashing import deterministic_id
from app.platform.models import (
    ArtifactRecord,
    EvidenceRecord,
    LineageEdge,
    LineageNode,
    RegistryEntityType,
    RegistryEvent,
    RegistryEventType,
    StrategyLifecycle,
    StrategyRecord,
)
from app.platform.policies import validate_transition
from app.platform.repositories import (
    ArtifactRegistryRepository,
    EvidenceRegistryRepository,
    LineageRepository,
    MissingReferenceError,
    RegistryEventRepository,
    StrategyRegistryRepository,
)


class PlatformRegistryService:
    def __init__(
        self,
        *,
        lineage: LineageRepository,
        strategies: StrategyRegistryRepository,
        evidence: EvidenceRegistryRepository,
        artifacts: ArtifactRegistryRepository,
        events: RegistryEventRepository,
    ) -> None:
        self.lineage = lineage
        self.strategies = strategies
        self.evidence = evidence
        self.artifacts = artifacts
        self.events = events

    @classmethod
    def from_repository(cls, repository: object) -> "PlatformRegistryService":
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
        )

    def _event(
        self,
        *,
        entity_type: RegistryEntityType,
        entity_id: str,
        event_type: RegistryEventType,
        previous_state: dict | None,
        new_state: dict,
        actor: str,
        reason: str,
        created_at: datetime,
        related_artifact_ids: tuple[str, ...] = (),
    ) -> RegistryEvent:
        event_id = deterministic_id(
            "REG-EVT",
            entity_type,
            entity_id,
            event_type,
            previous_state,
            new_state,
            created_at,
        )
        return RegistryEvent(
            event_id=event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
            actor=actor,
            reason=reason,
            created_at=created_at,
            related_artifact_ids=related_artifact_ids,
        )

    def _record_registration(
        self,
        *,
        entity_type: RegistryEntityType,
        entity_id: str,
        state: dict,
        actor: str,
        reason: str,
        created_at: datetime,
        related_artifact_ids: tuple[str, ...] = (),
    ) -> None:
        self.events.append_event(
            self._event(
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=RegistryEventType.REGISTERED,
                previous_state=None,
                new_state=state,
                actor=actor,
                reason=reason,
                created_at=created_at,
                related_artifact_ids=related_artifact_ids,
            )
        )

    def register_lineage_node(
        self, node: LineageNode, *, actor: str, reason: str
    ) -> LineageNode:
        self.lineage.add_lineage_node(node)
        self._record_registration(
            entity_type=RegistryEntityType.LINEAGE_NODE,
            entity_id=node.node_id,
            state=node.model_dump(mode="json"),
            actor=actor,
            reason=reason,
            created_at=node.created_at,
        )
        return node

    def register_lineage_edge(
        self, edge: LineageEdge, *, actor: str, reason: str
    ) -> LineageEdge:
        self.lineage.add_lineage_edge(edge)
        self._record_registration(
            entity_type=RegistryEntityType.LINEAGE_EDGE,
            entity_id=edge.edge_id,
            state=edge.model_dump(mode="json"),
            actor=actor,
            reason=reason,
            created_at=edge.created_at,
        )
        return edge

    def register_artifact(
        self, record: ArtifactRecord, *, actor: str, reason: str
    ) -> ArtifactRecord:
        if self.lineage.get_lineage_node(record.lineage_node_id) is None:
            raise MissingReferenceError(
                f"Artifact references missing lineage node: {record.lineage_node_id}"
            )
        self.artifacts.add_artifact(record)
        self._record_registration(
            entity_type=RegistryEntityType.ARTIFACT,
            entity_id=record.artifact_id,
            state=record.model_dump(mode="json"),
            actor=actor,
            reason=reason,
            created_at=record.created_at,
        )
        return record

    def register_strategy(
        self, record: StrategyRecord, *, actor: str, reason: str
    ) -> StrategyRecord:
        if self.strategies.get_strategy(record.strategy_id) is not None:
            raise ValueError(f"Strategy already registered: {record.strategy_id}")
        artifact_ids = tuple(record.metadata.get("source_artifact_ids", ()))
        for artifact_id in artifact_ids:
            if self.artifacts.get_artifact(artifact_id) is None:
                raise MissingReferenceError(
                    f"Strategy references missing artifact: {artifact_id}"
                )
        self.strategies.append_strategy(record)
        self._record_registration(
            entity_type=RegistryEntityType.STRATEGY,
            entity_id=record.strategy_id,
            state=record.model_dump(mode="json"),
            actor=actor,
            reason=reason,
            created_at=record.updated_at,
            related_artifact_ids=artifact_ids,
        )
        return record

    def record_strategy_transition(
        self,
        strategy_id: str,
        new_status: StrategyLifecycle,
        *,
        actor: str,
        reason: str,
        created_at: datetime,
        validation_status: str | None = None,
        production_status: str | None = None,
    ) -> StrategyRecord:
        previous = self.get_strategy(strategy_id)
        validate_transition(previous.lifecycle_status, new_status)
        if new_status == StrategyLifecycle.PRODUCTION_CANDIDATE and (
            not previous.promotion_allowed
            or (validation_status or previous.validation_status) != "VALIDATED"
        ):
            raise ValueError(
                "Production candidate transition requires explicit promotion allowance "
                "and VALIDATED status"
            )
        updated = previous.model_copy(
            update={
                "lifecycle_status": new_status,
                "updated_at": created_at,
                "validation_status": validation_status
                or previous.validation_status,
                "production_status": production_status
                or previous.production_status,
            }
        )
        updated = StrategyRecord.model_validate(updated.model_dump())
        self.strategies.append_strategy(updated)
        artifact_ids = tuple(updated.metadata.get("source_artifact_ids", ()))
        self.events.append_event(
            self._event(
                entity_type=RegistryEntityType.STRATEGY,
                entity_id=strategy_id,
                event_type=RegistryEventType.TRANSITIONED,
                previous_state={"lifecycle_status": previous.lifecycle_status.value},
                new_state={"lifecycle_status": new_status.value},
                actor=actor,
                reason=reason,
                created_at=created_at,
                related_artifact_ids=artifact_ids,
            )
        )
        return updated

    def register_evidence(
        self, record: EvidenceRecord, *, actor: str, reason: str
    ) -> EvidenceRecord:
        if self.strategies.get_strategy(record.strategy_id) is None:
            raise MissingReferenceError(
                f"Evidence references missing strategy: {record.strategy_id}"
            )
        for artifact_id in record.source_artifact_ids:
            if self.artifacts.get_artifact(artifact_id) is None:
                raise MissingReferenceError(
                    f"Evidence references missing artifact: {artifact_id}"
                )
        for node_id in record.lineage_node_ids:
            if self.lineage.get_lineage_node(node_id) is None:
                raise MissingReferenceError(
                    f"Evidence references missing lineage node: {node_id}"
                )
        self.evidence.add_evidence(record)
        self._record_registration(
            entity_type=RegistryEntityType.EVIDENCE,
            entity_id=record.evidence_id,
            state=record.model_dump(mode="json"),
            actor=actor,
            reason=reason,
            created_at=record.created_at,
            related_artifact_ids=record.source_artifact_ids,
        )
        return record

    def get_strategy(self, strategy_id: str) -> StrategyRecord:
        record = self.strategies.get_strategy(strategy_id)
        if record is None:
            raise KeyError(strategy_id)
        return record

    def list_strategies(self) -> list[StrategyRecord]:
        return self.strategies.list_strategies()

    def get_strategy_history(self, strategy_id: str) -> list[StrategyRecord]:
        return self.strategies.get_strategy_history(strategy_id)

    def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        record = self.evidence.get_evidence(evidence_id)
        if record is None:
            raise KeyError(evidence_id)
        return record

    def list_evidence(self) -> list[EvidenceRecord]:
        return self.evidence.list_evidence()

    def get_evidence_for_strategy(self, strategy_id: str) -> list[EvidenceRecord]:
        return self.evidence.get_evidence_for_strategy(strategy_id)

    def get_lineage_node(self, node_id: str) -> LineageNode:
        record = self.lineage.get_lineage_node(node_id)
        if record is None:
            raise KeyError(node_id)
        return record

    def get_lineage_parents(self, node_id: str) -> list[LineageNode]:
        self.get_lineage_node(node_id)
        return self.lineage.get_lineage_parents(node_id)

    def get_lineage_children(self, node_id: str) -> list[LineageNode]:
        self.get_lineage_node(node_id)
        return self.lineage.get_lineage_children(node_id)

    def trace_lineage(
        self,
        node_id: str,
        *,
        direction: Literal["parents", "children"] = "parents",
    ) -> list[LineageNode]:
        self.get_lineage_node(node_id)
        visit = (
            self.lineage.get_lineage_parents
            if direction == "parents"
            else self.lineage.get_lineage_children
        )
        pending = list(visit(node_id))
        found: dict[str, LineageNode] = {}
        while pending:
            current = pending.pop(0)
            if current.node_id in found:
                continue
            found[current.node_id] = current
            pending.extend(visit(current.node_id))
        return [found[item] for item in sorted(found)]

    def list_artifacts(self) -> list[ArtifactRecord]:
        return self.artifacts.list_artifacts()


__all__ = ("PlatformRegistryService",)

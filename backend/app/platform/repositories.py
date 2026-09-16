from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.platform.hashing import canonical_hash
from app.platform.models import (
    ArtifactRecord,
    EvidenceRecord,
    LineageEdge,
    LineageNode,
    RegistryEvent,
    StrategyRecord,
)


class DuplicateIdentityError(ValueError):
    pass


class MissingReferenceError(ValueError):
    pass


class LineageCycleError(ValueError):
    pass


class AppendOnlyViolation(ValueError):
    pass


@runtime_checkable
class LineageRepository(Protocol):
    def add_lineage_node(self, node: LineageNode) -> None: ...

    def add_lineage_edge(self, edge: LineageEdge) -> None: ...

    def get_lineage_node(self, node_id: str) -> LineageNode | None: ...

    def list_lineage_nodes(self) -> list[LineageNode]: ...

    def get_lineage_parents(self, node_id: str) -> list[LineageNode]: ...

    def get_lineage_children(self, node_id: str) -> list[LineageNode]: ...

    def list_lineage_edges(self) -> list[LineageEdge]: ...


@runtime_checkable
class StrategyRegistryRepository(Protocol):
    def append_strategy(self, record: StrategyRecord) -> None: ...

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None: ...

    def list_strategies(self) -> list[StrategyRecord]: ...

    def get_strategy_history(self, strategy_id: str) -> list[StrategyRecord]: ...


@runtime_checkable
class EvidenceRegistryRepository(Protocol):
    def add_evidence(self, record: EvidenceRecord) -> None: ...

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...

    def list_evidence(self) -> list[EvidenceRecord]: ...

    def get_evidence_for_strategy(self, strategy_id: str) -> list[EvidenceRecord]: ...


@runtime_checkable
class ArtifactRegistryRepository(Protocol):
    def add_artifact(self, record: ArtifactRecord) -> None: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def list_artifacts(self) -> list[ArtifactRecord]: ...


@runtime_checkable
class RegistryEventRepository(Protocol):
    def append_event(self, event: RegistryEvent) -> None: ...

    def list_events(self) -> list[RegistryEvent]: ...


class InMemoryPlatformRepository:
    """Append-only in-memory implementation of all platform repositories."""

    def __init__(self) -> None:
        self._nodes: dict[str, LineageNode] = {}
        self._edges: dict[str, LineageEdge] = {}
        self._strategy_history: dict[str, list[StrategyRecord]] = defaultdict(list)
        self._evidence: dict[str, EvidenceRecord] = {}
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._events: list[RegistryEvent] = []
        self._event_ids: set[str] = set()

    def add_lineage_node(self, node: LineageNode) -> None:
        if node.node_id in self._nodes:
            raise DuplicateIdentityError(f"Duplicate lineage node: {node.node_id}")
        self._nodes[node.node_id] = node

    def _has_path(self, start: str, target: str) -> bool:
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in self._edges.values():
            adjacency[edge.parent_node_id].append(edge.child_node_id)
        pending = [start]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current])
        return False

    def add_lineage_edge(self, edge: LineageEdge) -> None:
        if edge.edge_id in self._edges:
            raise DuplicateIdentityError(f"Duplicate lineage edge: {edge.edge_id}")
        if edge.parent_node_id not in self._nodes:
            raise MissingReferenceError(
                f"Missing parent lineage node: {edge.parent_node_id}"
            )
        if edge.child_node_id not in self._nodes:
            raise MissingReferenceError(
                f"Missing child lineage node: {edge.child_node_id}"
            )
        if self._has_path(edge.child_node_id, edge.parent_node_id):
            raise LineageCycleError(
                f"Lineage edge would create a cycle: {edge.parent_node_id} -> "
                f"{edge.child_node_id}"
            )
        self._edges[edge.edge_id] = edge

    def get_lineage_node(self, node_id: str) -> LineageNode | None:
        return self._nodes.get(node_id)

    def list_lineage_nodes(self) -> list[LineageNode]:
        return sorted(self._nodes.values(), key=lambda row: row.node_id)

    def get_lineage_parents(self, node_id: str) -> list[LineageNode]:
        parent_ids = {
            edge.parent_node_id
            for edge in self._edges.values()
            if edge.child_node_id == node_id
        }
        return [self._nodes[item] for item in sorted(parent_ids)]

    def get_lineage_children(self, node_id: str) -> list[LineageNode]:
        child_ids = {
            edge.child_node_id
            for edge in self._edges.values()
            if edge.parent_node_id == node_id
        }
        return [self._nodes[item] for item in sorted(child_ids)]

    def list_lineage_edges(self) -> list[LineageEdge]:
        return sorted(self._edges.values(), key=lambda row: row.edge_id)

    def append_strategy(self, record: StrategyRecord) -> None:
        history = self._strategy_history[record.strategy_id]
        if history:
            previous = history[-1]
            if canonical_hash(previous) == canonical_hash(record):
                raise DuplicateIdentityError(
                    f"Duplicate strategy state: {record.strategy_id}"
                )
            if record.updated_at <= previous.updated_at:
                raise AppendOnlyViolation(
                    "New strategy state must have a later updated_at timestamp"
                )
            if record.created_at != previous.created_at:
                raise AppendOnlyViolation(
                    "Strategy created_at cannot change across append-only history"
                )
        history.append(record)

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        history = self._strategy_history.get(strategy_id, [])
        return history[-1] if history else None

    def list_strategies(self) -> list[StrategyRecord]:
        return [
            self._strategy_history[item][-1]
            for item in sorted(self._strategy_history)
        ]

    def get_strategy_history(self, strategy_id: str) -> list[StrategyRecord]:
        return list(self._strategy_history.get(strategy_id, []))

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._evidence:
            raise DuplicateIdentityError(f"Duplicate evidence: {record.evidence_id}")
        self._evidence[record.evidence_id] = record

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)

    def list_evidence(self) -> list[EvidenceRecord]:
        return sorted(self._evidence.values(), key=lambda row: row.evidence_id)

    def get_evidence_for_strategy(self, strategy_id: str) -> list[EvidenceRecord]:
        return [
            row for row in self.list_evidence() if row.strategy_id == strategy_id
        ]

    def add_artifact(self, record: ArtifactRecord) -> None:
        if record.artifact_id in self._artifacts:
            raise DuplicateIdentityError(f"Duplicate artifact: {record.artifact_id}")
        self._artifacts[record.artifact_id] = record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self._artifacts.get(artifact_id)

    def list_artifacts(self) -> list[ArtifactRecord]:
        return sorted(self._artifacts.values(), key=lambda row: row.artifact_id)

    def append_event(self, event: RegistryEvent) -> None:
        if event.event_id in self._event_ids:
            raise DuplicateIdentityError(f"Duplicate registry event: {event.event_id}")
        self._events.append(event)
        self._event_ids.add(event.event_id)

    def list_events(self) -> list[RegistryEvent]:
        return list(self._events)


class JsonFilePlatformRepository(InMemoryPlatformRepository):
    """Append-only JSONL repository rooted in a caller-controlled directory."""

    _FILES = {
        "nodes": Path("lineage/nodes.jsonl"),
        "edges": Path("lineage/edges.jsonl"),
        "strategies": Path("registry/strategies.jsonl"),
        "evidence": Path("registry/evidence.jsonl"),
        "artifacts": Path("artifacts/artifacts.jsonl"),
        "events": Path("registry/events.jsonl"),
    }

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        super().__init__()
        self._load()

    def _path(self, kind: str) -> Path:
        return self.root / self._FILES[kind]

    def _read_jsonl(self, kind: str) -> list[dict]:
        path = self._path(kind)
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSONL in {path} at line {line_number}"
                    ) from error
        return rows

    def _load(self) -> None:
        for value in self._read_jsonl("nodes"):
            super().add_lineage_node(LineageNode.model_validate(value))
        for value in self._read_jsonl("edges"):
            super().add_lineage_edge(LineageEdge.model_validate(value))
        for value in self._read_jsonl("strategies"):
            super().append_strategy(StrategyRecord.model_validate(value))
        for value in self._read_jsonl("evidence"):
            super().add_evidence(EvidenceRecord.model_validate(value))
        for value in self._read_jsonl("artifacts"):
            super().add_artifact(ArtifactRecord.model_validate(value))
        for value in self._read_jsonl("events"):
            super().append_event(RegistryEvent.model_validate(value))

    def _append_jsonl(self, kind: str, model: object) -> None:
        path = self._path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(model, (LineageNode, LineageEdge, StrategyRecord, EvidenceRecord, ArtifactRecord, RegistryEvent)):
            raise TypeError(f"Unsupported registry model: {type(model)!r}")
        payload = json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def add_lineage_node(self, node: LineageNode) -> None:
        super().add_lineage_node(node)
        self._append_jsonl("nodes", node)

    def add_lineage_edge(self, edge: LineageEdge) -> None:
        super().add_lineage_edge(edge)
        self._append_jsonl("edges", edge)

    def append_strategy(self, record: StrategyRecord) -> None:
        super().append_strategy(record)
        self._append_jsonl("strategies", record)

    def add_evidence(self, record: EvidenceRecord) -> None:
        super().add_evidence(record)
        self._append_jsonl("evidence", record)

    def add_artifact(self, record: ArtifactRecord) -> None:
        super().add_artifact(record)
        self._append_jsonl("artifacts", record)

    def append_event(self, event: RegistryEvent) -> None:
        super().append_event(event)
        self._append_jsonl("events", event)


__all__ = (
    "AppendOnlyViolation",
    "ArtifactRegistryRepository",
    "DuplicateIdentityError",
    "EvidenceRegistryRepository",
    "InMemoryPlatformRepository",
    "JsonFilePlatformRepository",
    "LineageCycleError",
    "LineageRepository",
    "MissingReferenceError",
    "RegistryEventRepository",
    "StrategyRegistryRepository",
)

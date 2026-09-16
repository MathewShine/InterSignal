# Platform Registry Domain Model V1

## Scope

The platform registry is the first implementation slice authorized by the Product Platform Charter. Its package is `backend/app/platform/` and contains domain models, hashing, lifecycle policy, repository contracts, local repositories, services, and the research seed adapter.

The package is independent of Groww, Zerodha, NSE endpoints, Supabase, React, and any one filesystem layout. Only the seed adapter knows the current project paths; core domain models store neutral references.

## Identity and hashing

`INTERSIGNAL_CANONICAL_SHA256_V1` serializes canonical JSON with sorted keys, compact separators, normalized UTC timestamps, stable enum values, exact Decimal strings, and rejection of NaN/infinity. Callers may explicitly exclude named top-level volatile fields when computing a content identity.

Deterministic IDs combine the hash version and stable identity parts, then use a semantic prefix plus 24 hexadecimal digest characters. Current prefixes are `LIN-NODE`, `LIN-EDGE`, `ART`, and `REG-EVT`. Immutable content retains the same identity across processes; random UUIDs are not used when source identity exists.

## Domain objects

| Object | Role |
|---|---|
| `LineageNode` | Versioned object in one canonical lineage stage |
| `LineageEdge` | Directed, typed, acyclic parent/child relationship |
| `ProvenanceRecord` | Source, licensing, timing, market, and raw-hash metadata |
| `ArtifactRecord` | Immutable reference to research, report, manifest, config, validation, or snapshot content |
| `StrategyRecord` | Versioned strategy/family lifecycle and governance state |
| `EvidenceRecord` | Classified and levelled evidence tied to strategy, artifacts, and lineage |
| `RegistryEvent` | Append-only audit record for every mutation |

Pydantic models are frozen and reject unknown fields. Required identifiers must be non-empty; hashes must be lowercase SHA-256; timestamps must be timezone-aware; and confidence, when present, is constrained to 0–1.

## Repository interfaces

Five runtime-checkable protocols define persistence boundaries:

- `LineageRepository`
- `StrategyRegistryRepository`
- `EvidenceRegistryRepository`
- `ArtifactRegistryRepository`
- `RegistryEventRepository`

The interfaces expose append and read methods only. They contain no Supabase, provider, HTTP, frontend, or delete dependency.

`InMemoryPlatformRepository` implements all five protocols for tests and future dependency injection. `JsonFilePlatformRepository` supplies the first local implementation using append-only JSONL files:

- `data/platform/lineage/nodes.jsonl`
- `data/platform/lineage/edges.jsonl`
- `data/platform/registry/strategies.jsonl`
- `data/platform/registry/evidence.jsonl`
- `data/platform/registry/events.jsonl`
- `data/platform/artifacts/artifacts.jsonl`

The repository reconstructs state by replaying the files. Strategy history preserves every version. Duplicate immutable IDs, missing lineage endpoints, out-of-order strategy versions, and graph cycles are rejected.

## Service layer

Read operations are `get_strategy`, `list_strategies`, `get_strategy_history`, `get_evidence`, `list_evidence`, `get_evidence_for_strategy`, `get_lineage_node`, `get_lineage_parents`, `get_lineage_children`, `trace_lineage`, and `list_artifacts`.

Guarded writes are `register_strategy`, `record_strategy_transition`, `register_evidence`, `register_artifact`, `register_lineage_node`, and `register_lineage_edge`. References are validated before registration. Each successful mutation appends a deterministic audit event.

No destructive delete exists. Deprecation and supersession are modeled as explicit status/event semantics for later governed workflows.

## Local seed and boundaries

`backend/scripts/seed_platform_registry_from_research.py` reads and hashes selected frozen A–G artifacts, then records path/hash references under `data/platform/`. It does not copy raw research data and proves all source hashes remained unchanged.

The current snapshot remains `PAUSED`, `COMPLETE_NO_VALIDATED_STRATEGY`, Strategy V2 `NOT_CREATED`, Family H `NOT_PLANNED`, paper `NOT_READY`, and live `NOT_READY`. There are no production candidates, broker calls, live signals, live orders, migrations, Supabase writes, external writes, or network requirements.

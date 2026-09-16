# Platform Data Lineage V1

`INTERSIGNAL_PLATFORM_FOUNDATION_V1` introduces the first implementation of InterSignal's immutable lineage model. It is a backend/domain foundation only: it contains no UI, broker, live-feed, indicator, pattern, portfolio, shadow-mode, or execution behavior.

## Canonical stages

`LineageStage` is a stable string enum with the exact path:

`SOURCE → RAW → NORMALIZED → DERIVED → FEATURE → CANDIDATE → SIGNAL → POSITION → TRADE → OUTCOME → EVIDENCE`

The enum deliberately describes possible platform lineage beyond the current seed. The initial registry creates only `SOURCE` nodes for frozen research artifacts and `EVIDENCE` nodes for seeded evidence. It does not manufacture intermediate transformations that did not occur.

## Nodes

An immutable `LineageNode` contains:

- `node_id`: deterministic identity derived from stable business fields;
- `stage`: one canonical `LineageStage`;
- `entity_type` and `entity_key`: stable semantic identity;
- `version` and `content_hash`;
- timezone-aware `created_at`;
- provider-neutral `source_system`;
- metadata and an `ACTIVE`, `DEPRECATED`, or `SUPERSEDED` status.

Node IDs use `LIN-NODE-` plus the first 24 hexadecimal characters of a versioned canonical SHA-256 identity. Time of registration is not part of the ID, so the same immutable object receives the same ID when imported again.

## Edges and graph integrity

An immutable `LineageEdge` contains `edge_id`, parent and child node IDs, relationship, timezone-aware creation time, and metadata. Supported relationships are `DERIVED_FROM`, `NORMALIZED_FROM`, `COMPUTED_FROM`, `GENERATED_BY`, `VALIDATED_BY`, `SUPPORTED_BY`, `CONTRADICTED_BY`, and `SUPERSEDES`.

Edge identity depends only on parent, child, and relationship. Re-registering an identical relationship is rejected as a duplicate. Both endpoint nodes must already exist. Self-cycles are rejected by schema validation, and a graph traversal rejects any edge that would create an indirect cycle.

The service supports direct parent/child reads and recursive ancestor or descendant tracing. Traversal is read-only and uses visited-node guards.

## Provenance

`ProvenanceRecord` represents external or internal source identity independently of storage. It records source name/type/reference/version, retrieved/effective/published timestamps, market and instrument where applicable, licensing classification, raw SHA-256 hash, and metadata.

Timestamps must be timezone-aware and are normalized to UTC for hashing. Source hashes must be lowercase 64-character SHA-256 values. Provider-specific clients and filesystem layouts do not appear in the core lineage abstractions.

## Repository contract

`LineageRepository` defines append operations for nodes and edges and read operations for nodes, edges, parents, and children. There is no delete operation. `InMemoryPlatformRepository` supplies deterministic test behavior; `JsonFilePlatformRepository` writes newline-delimited JSON under `data/platform/lineage/`.

The JSONL store is append-only. Deprecation or supersession must be represented by a later governed record and registry event, not destructive removal.

## Initial seed

`seed_platform_registry_from_research` hashes selected frozen research manifests, configurations, validation artifacts, and evidence registries in place. It registers references without copying or rewriting the source artifacts. Each referenced artifact becomes a `SOURCE` node; each imported evidence record becomes an `EVIDENCE` node linked to its immutable source.

The foundation manifest stores before/after hashes for every referenced source. Any difference aborts generation.

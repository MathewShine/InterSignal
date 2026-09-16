# Research Workbench Backend V1

## Scope

`INTERSIGNAL_RESEARCH_WORKBENCH_BACKEND_V1` is the read-only backend and
domain foundation for the InterSignal Research Workbench. Its profile is
`RESEARCH_QUERY_AND_VIEW_MODEL_FOUNDATION_V1`.

The Workbench projects the immutable platform registries into research-facing
views. The strategy, evidence, artifact, lineage, and registry-event stores
remain the sources of truth. The Workbench neither changes those stores nor
recomputes research metrics from market data.

This command adds no HTTP routes, React components, broker connections,
real-time feeds, Portfolio OS behavior, database migrations, Strategy V2, or
Family H.

## Service queries

`ResearchWorkbenchService` exposes read operations for:

- the A-G family matrix and family details;
- strategy history and strategy details;
- evidence details and classification/level filters;
- family and strategy timelines derived from `RegistryEvent`;
- validation and blocked-research summaries;
- family, strategy, and evidence artifact traversal;
- bounded upstream/downstream lineage traces;
- the current research-programme projection;
- deterministic pagination, sorting, and snapshot export;
- registry and lineage integrity reporting.

The service accepts repository interfaces rather than concrete storage. The
current runner uses the local JSONL platform repository, while future API or
database adapters can implement the same interfaces.

## Read-only guarantee

The public Workbench service surface has no registration, transition, update,
delete, append, or write operation. Mutations remain the responsibility of the
platform registry service. Projection models are frozen and reject unexpected
fields.

## Snapshot export

`export_research_workbench_snapshot()` returns an immutable serializable view
containing programme state, family summaries, strategy summaries, evidence
counts, blocked studies, latest events, and integrity. The snapshot timestamp
comes from the latest registry event, not wall-clock time. Its SHA-256 is
computed with `INTERSIGNAL_CANONICAL_SHA256_V1`.

The generated platform-owned files are:

- `data/platform/workbench/research_workbench_snapshot_v1.json`
- `data/platform/workbench/research_workbench_integrity_v1.json`
- `data/platform/manifests/intersignal_research_workbench_backend_manifest_v1.json`

## Integrity semantics

Integrity checks cover strategy-to-artifact references, evidence-to-strategy,
artifact, and lineage references, artifact-to-lineage references, edge
endpoints, graph cycles, duplicate identifiers, artifact/node hashes,
evidence-node hashes, and strategy configuration hashes. The current seed must
produce `HEALTHY` with every error count equal to zero.

Lineage traversal is deterministic and bounded by node and depth limits. A
cycle, missing reference, or exceeded bound produces a stable Workbench domain
error rather than a partial or fabricated graph.

## Storage boundary

Artifact views expose stable references and hashes. They do not assume a user
interface reads the local filesystem, and they never fabricate artifact
content. The JSONL repository is suitable for this offline foundation; it is
not a transactional or multi-process production database.

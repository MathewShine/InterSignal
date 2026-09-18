export const DATA_CONTRACT_VERSION = "INTERSIGNAL_DATA_HEALTH_V1";

const number = (value) => value === null || value === undefined ? null : Number(value);
const meta = (value = {}) => ({
  readOnly: value.read_only !== false,
  sourceContract: value.source_contract,
  unavailableSections: value.unavailable_sections ?? [],
});
const base = (payload) => ({
  version: payload.version,
  generatedAt: payload.generated_at,
  status: payload.status,
  reason: payload.reason,
  meta: meta(payload.meta),
});
export const normalizeSource = (value) => ({
  id: value.source_id,
  name: value.name,
  domain: value.domain,
  status: value.status,
  researchUse: value.research_use,
  summary: value.summary,
  freshness: value.freshness,
  coveragePercent: number(value.coverage_pct),
  gapCount: value.gap_count,
  limitations: value.limitations ?? [],
  evidenceRefs: value.evidence_refs ?? [],
});
export const normalizeLineage = (value) => value ? ({
  integrityStatus: value.integrity_status,
  brokenReferenceCount: value.broken_reference_count,
  nodeCount: value.node_count,
  edgeCount: value.edge_count,
  artifactCount: value.artifact_count,
  stageCounts: value.stage_counts ?? {},
  nodes: (value.nodes ?? []).map((row) => ({
    id: row.node_id, stage: row.stage, entityType: row.entity_type, label: row.label,
    version: row.version, sourceSystem: row.source_system, status: row.status,
    createdAt: row.created_at, parentCount: row.parent_count, childCount: row.child_count,
  })),
}) : null;
export const normalizeLimitation = (value) => ({
  id: value.limitation_id,
  title: value.title,
  status: value.status,
  severity: value.severity,
  summary: value.summary,
  impact: value.impact,
  resolution: value.resolution,
  sourceId: value.related_source_id,
});
export const normalizeDataOverview = (payload) => ({
  ...base(payload),
  sources: (payload.sources ?? []).map(normalizeSource),
  lineage: normalizeLineage(payload.lineage),
  limitations: (payload.limitations ?? []).map(normalizeLimitation),
});
export const normalizeDataSources = (payload) => ({ ...base(payload), items: (payload.items ?? []).map(normalizeSource), totalCount: payload.total_count });
export const normalizeDataLineage = (payload) => ({ ...base(payload), lineage: normalizeLineage(payload.lineage) });
export const normalizeDataLimitations = (payload) => ({ ...base(payload), items: (payload.items ?? []).map(normalizeLimitation), totalCount: payload.total_count });

export const displayStatus = (value) => ({
  AVAILABLE: "Available",
  AVAILABLE_WITH_CAVEATS: "Available with caveats",
  BLOCKED_FOR_RESEARCH_USE: "Research blocked",
  SOURCE_BLOCKED: "Source blocked",
  HEALTHY: "Healthy",
  NOT_READY: "Not ready",
  REQUESTED: "Pending",
  PASS: "Pass",
  OPEN: "Open",
  DOCUMENTED: "Documented",
}[value] ?? String(value ?? "Unavailable").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()));

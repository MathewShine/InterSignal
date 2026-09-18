export const RESEARCH_CONTRACT_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_V1";

export const statusLabel = (value) => {
  const labels = {
    INCONCLUSIVE: "Inconclusive",
    FAIL: "Fail",
    PAUSED: "Paused",
    BLOCKED: "Blocked",
    CLOSED_NOT_ADVANCED: "Closed",
    REJECTED_FOR_CURRENT_CYCLE: "Not advanced this cycle",
    PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE: "Blocked by data",
    PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE: "Blocked by source",
    PAUSED_NO_VALIDATION_CANDIDATE: "Paused · no validation candidate",
    REUSABLE_SIGNAL_ONLY: "Reusable evidence only",
    DATA_BLOCKED: "Blocked by data",
    SOURCE_BLOCKED: "Blocked by source",
    NEGATIVE_DEVELOPMENT: "Negative evidence",
    NEGATIVE_OVERLAY: "Negative overlay evidence",
    NOT_ACCESSED: "Not accessed",
    NOT_CREATED: "Not created",
    NOT_PLANNED: "Not planned",
    NOT_READY: "Not ready",
    UNSUPPORTIVE: "Unsupportive",
    NON_PRISTINE: "Non-pristine",
    IMPLEMENTATION_DEFECT: "Implementation defect",
  };
  if (!value) return "—";
  return labels[value] ?? String(value).toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
};

export const statusTone = (value = "") => {
  const normalized = String(value).toUpperCase();
  if (normalized.includes("REUSABLE") || normalized.includes("POSITIVE")) return "positive";
  if (normalized.includes("BLOCK") || normalized.includes("PENDING") || normalized.includes("INCONCLUSIVE")) return "caution";
  if (normalized.includes("FAIL") || normalized.includes("NEGATIVE") || normalized.includes("UNSUPPORTIVE")) return "negative";
  return "neutral";
};

const copy = (value) => JSON.parse(JSON.stringify(value));

export const normalizeFamily = (family) => ({
  id: family.family_id,
  name: family.name,
  setup: family.setup,
  description: family.description,
  stage: family.stage,
  currentStatus: family.current_status,
  currentStatusLabel: family.current_status_label,
  decisionStatus: family.decision_status,
  decisionLabel: family.decision_label,
  evidenceState: family.evidence_state,
  validationState: family.validation_state,
  validationLabel: family.validation_label,
  blocker: family.blocker,
  evidenceCounts: copy(family.evidence_counts ?? {}),
  latestActivityAt: family.latest_activity_at,
  productionCandidate: Boolean(family.production_candidate),
  keyFindings: family.key_findings ?? [],
  searchTerms: family.search_terms ?? [],
  actionPath: family.action_path,
});

export const normalizeEvidence = (item) => ({
  id: item.evidence_id,
  familyId: item.family_id,
  title: item.title,
  summary: item.summary,
  classification: item.classification,
  type: item.evidence_type,
  status: item.status,
  productionRelevance: item.production_relevance,
  source: item.source,
  updatedAt: item.updated_at,
  artifactIds: item.artifact_ids ?? [],
  lineageNodeIds: item.lineage_node_ids ?? [],
  limitations: item.limitations ?? [],
  actionPath: item.action_path,
  researchContext: item.research_context,
  currentDisposition: item.current_disposition,
  effectivePeriod: item.effective_period,
  confidence: item.confidence,
  supportingArtifacts: item.supporting_artifacts ?? [],
  lineage: item.lineage ?? { nodes: [], edges: [], integrity: "HEALTHY" },
});

export const normalizeValidation = (item) => ({
  id: item.record_id,
  familyId: item.family_id,
  type: item.validation_type,
  period: item.period,
  outcome: item.outcome,
  interpretation: item.interpretation,
  integrity: item.integrity,
  pristineIntent: item.pristine_intent,
  notes: item.notes,
  artifactIds: item.artifact_ids ?? [],
  actionPath: item.action_path,
});

export const normalizeBlocked = (item) => ({
  familyId: item.family_id,
  type: item.blocker_type,
  label: item.blocker_label,
  reason: item.reason,
  impact: item.impact,
  requiredResolution: item.required_resolution,
  status: item.status,
  currentState: item.current_state,
  relatedEvidence: item.related_evidence ?? [],
  relatedArtifacts: item.related_artifacts ?? [],
  actionPath: item.action_path,
});

export const normalizeTimeline = (item) => ({
  id: item.event_id,
  occurredAt: item.occurred_at,
  familyId: item.family_id,
  event: item.event,
  category: item.category,
  result: item.result,
  relatedArtifacts: item.related_artifacts ?? [],
  relatedEvidence: item.related_evidence,
});

export function normalizeOverview(payload) {
  return {
    version: payload.version,
    generatedAt: payload.generated_at,
    status: payload.status,
    reason: payload.reason,
    programme: payload.programme ? {
      status: payload.programme.status,
      cycleStatus: payload.programme.cycle_status,
      validatedStrategyCount: payload.programme.validated_strategy_count,
      productionCandidateCount: payload.programme.production_candidate_count,
      strategyV2Status: payload.programme.strategy_v2_status,
      familyHStatus: payload.programme.family_h_status,
      paperReadiness: payload.programme.paper_readiness,
      liveReadiness: payload.programme.live_readiness,
      primaryProgramme: payload.programme.primary_programme,
      secondaryProgramme: payload.programme.secondary_programme,
    } : null,
    metrics: {
      families: payload.family_count,
      reusableEvidence: payload.reusable_evidence_count,
      blockedStudies: payload.blocked_study_count,
      productionReady: payload.production_ready_count,
    },
    families: (payload.families ?? []).map(normalizeFamily),
    retainedEvidence: (payload.retained_evidence ?? []).map(normalizeEvidence),
    blocked: (payload.blocked ?? []).map(normalizeBlocked),
    recentActivity: (payload.recent_activity ?? []).map(normalizeTimeline),
    meta: copy(payload.meta ?? {}),
  };
}

export const normalizeFamilies = (payload) => ({
  status: payload.status,
  items: (payload.items ?? []).map(normalizeFamily),
  totalCount: payload.total_count,
  meta: copy(payload.meta ?? {}),
});

export const normalizeFamilyDetail = (payload) => ({
  status: payload.status,
  family: normalizeFamily(payload.family),
  hypothesis: payload.hypothesis,
  sections: (payload.sections ?? []).map((item) => ({
    id: item.section_id,
    title: item.title,
    summary: item.summary,
    tone: item.tone,
  })),
  evidence: (payload.evidence ?? []).map(normalizeEvidence),
  validation: (payload.validation ?? []).map(normalizeValidation),
  timeline: (payload.timeline ?? []).map(normalizeTimeline),
  artifacts: payload.artifacts ?? [],
  lineage: payload.lineage ?? { nodes: [], edges: [], integrity: "HEALTHY" },
  limitations: payload.limitations ?? [],
  meta: copy(payload.meta ?? {}),
});

export const normalizeEvidenceList = (payload) => ({
  status: payload.status,
  items: (payload.items ?? []).map(normalizeEvidence),
  totalCount: payload.total_count,
  meta: copy(payload.meta ?? {}),
});

export const normalizeEvidenceDetail = (payload) => ({
  status: payload.status,
  evidence: normalizeEvidence(payload.evidence),
  meta: copy(payload.meta ?? {}),
});

export const normalizeValidationList = (payload) => ({
  status: payload.status,
  items: (payload.items ?? []).map(normalizeValidation),
  totalCount: payload.total_count,
  meta: copy(payload.meta ?? {}),
});

export const normalizeBlockedList = (payload) => ({
  status: payload.status,
  items: (payload.items ?? []).map(normalizeBlocked),
  totalCount: payload.total_count,
  meta: copy(payload.meta ?? {}),
});

export const normalizeTimelineList = (payload) => ({
  status: payload.status,
  items: (payload.items ?? []).map(normalizeTimeline),
  totalCount: payload.total_count,
  meta: copy(payload.meta ?? {}),
});

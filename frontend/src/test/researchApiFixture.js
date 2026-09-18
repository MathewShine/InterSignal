export const RESEARCH_VERSION = "INTERSIGNAL_RESEARCH_WORKBENCH_V1";
export const timestamp = "2026-09-16T17:54:02Z";

export const meta = {
  read_only: true,
  auth_enforcement: "NOT_IMPLEMENTED",
  broker_integration: "NOT_IMPLEMENTED",
  market_integration: "NOT_CONFIGURED",
  source_contracts: ["INTERSIGNAL_RESEARCH_WORKBENCH_SNAPSHOT_V1"],
  internal_paths_exposed: false,
  unavailable_sections: [],
};

const familyFacts = {
  A: ["Medium-Term Cross-Sectional Momentum", "Medium-term cross-sectional momentum", "Closed", "CLOSED_NOT_ADVANCED", "Closed", "REJECTED_FOR_CURRENT_CYCLE", "Not advanced this cycle", "Historical positive evidence; later-period evidence unsupportive", "Formal: Inconclusive · Post-remediation: Fail", null],
  B: ["Relative Plus Absolute Momentum", "Relative + absolute momentum filters", "Closed", "NO_INCREMENTAL_EDGE", "Closed", "PAUSED_NO_VALIDATION_CANDIDATE", "No validation candidate", "Negative development evidence", "Not accessed", null],
  C: ["Breakout Continuation", "Breakout continuation", "Paused", "REUSABLE_SIGNAL_ONLY", "Reusable evidence only", "PAUSED_NO_VALIDATION_CANDIDATE", "No portfolio-ready candidate", "Reusable signal-level evidence retained", "Not accessed", null],
  D: ["Opening-Range Stocks in Play", "Opening range / stocks-in-play", "Blocked", "DATA_BLOCKED", "Blocked by data quality", "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE", "Awaiting better intraday source", "Data blocker", "Not accessed", "intraday continuity below frozen threshold"],
  E: ["Pullback Reclaim Continuation", "Pullback / reclaim", "Paused", "NEGATIVE_DEVELOPMENT", "Paused", "PAUSED_NO_VALIDATION_CANDIDATE", "No validation candidate", "Negative evidence", "Not accessed", null],
  F: ["Catalyst Momentum", "Catalyst momentum feasibility", "Blocked", "SOURCE_BLOCKED", "Blocked pending authorized source", "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE", "Awaiting source authorization", "Source blocker; technical feasibility retained", "Not accessed", "authorized catalyst historical source unavailable"],
  G: ["Quarterly Regime Volatility Participation", "Quarterly 6M momentum + Nifty 500 SMA200 gate", "Closed", "NEGATIVE_OVERLAY", "Closed", "PAUSED_NO_VALIDATION_CANDIDATE", "No validation candidate", "Negative overlay evidence", "Not accessed", null],
};

export function family(id) {
  const [name, setup, stage, current, currentLabel, decision, decisionLabel, evidenceState, validationLabel, blocker] = familyFacts[id];
  const findings = {
    A: ["Formal validation remains INCONCLUSIVE because an implementation logic defect invalidated the pristine one-shot evaluation.", "The separate post-remediation evaluation returned FAIL with an UNSUPPORTIVE interpretation.", "The 2025–26 holdout is contaminated."],
    B: ["B001 was redundant.", "B002 initial strength was a history-availability artifact.", "Incremental evidence was sparse and weak."],
    C: ["Compression <=8% improved event-level quality.", "Capacity and ranking implementation failed.", "Retained evidence, not production strategy."],
    D: ["Continuity reached only 77.826%.", "217 defects remain unresolved.", "Not a strategy failure."],
    E: ["Control was negative.", "Treatment was worse."],
    F: ["Timestamp feasibility was promising.", "Authorization remains unresolved.", "No performance conclusion."],
    G: ["Control CAGR 24.11% versus treatment 11.95%.", "Drawdown 22.92% to 30.73%.", "Missed two large positive quarters."],
  }[id];
  return {
    family_id: id,
    name,
    setup,
    description: setup,
    stage,
    current_status: current,
    current_status_label: currentLabel,
    decision_status: decision,
    decision_label: decisionLabel,
    evidence_state: evidenceState,
    validation_state: id === "A" ? "INCONCLUSIVE" : "NOT_ACCESSED",
    validation_label: validationLabel,
    blocker,
    evidence_counts: { positive: id === "C" ? 2 : 0, negative: ["B", "E", "G"].includes(id) ? 1 : 0, blocked: ["D", "F"].includes(id) ? 1 : 0, validation: id === "A" ? 1 : 0, post_outcome: id === "A" ? 1 : 0, data_infrastructure: id === "F" ? 1 : 0, total: id === "A" ? 3 : id === "C" || id === "F" ? 2 : 1 },
    latest_activity_at: timestamp,
    production_candidate: false,
    key_findings: findings,
    search_terms: [`ART-${id}`, `Family ${id} source artifact`],
    action_path: `/app/research/families/${id}`,
  };
}

export function evidence(overrides = {}) {
  return {
    evidence_id: "EDGE-EVIDENCE-C-COMPRESSION-001",
    family_id: "C",
    title: "Family C compression signal evidence",
    summary: "Pre-breakout compression no greater than 8% improved event-level signal quality in DEVELOPMENT.",
    classification: "POSITIVE_EVIDENCE",
    evidence_type: "SIGNAL_LEVEL",
    status: "RESEARCH_ONLY",
    production_relevance: "Reusable signal evidence · not production strategy",
    source: "Cross-Family Positive Evidence Registry",
    updated_at: timestamp,
    artifact_ids: ["ART-C"],
    lineage_node_ids: ["LIN-C"],
    limitations: ["NO_STRATEGY_CREATED"],
    action_path: "/app/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001",
    ...overrides,
  };
}

export const blocked = [
  {
    family_id: "D", blocker_type: "DATA_BLOCKED", blocker_label: "Data blocker", reason: "Intraday continuity is below the required threshold (77.826%; 217 unresolved defects).", impact: "Cannot perform a trustworthy formal evaluation.", required_resolution: "A better intraday source meeting the frozen continuity threshold.", status: "BLOCKED", current_state: "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE", related_evidence: ["EVIDENCE-D"], related_artifacts: ["ART-D"], action_path: "/app/research/families/D",
  },
  {
    family_id: "F", blocker_type: "SOURCE_BLOCKED", blocker_label: "Source authorization blocker", reason: "Historical catalyst source authorization and licensing are unresolved.", impact: "Cannot execute a robust historical catalyst study.", required_resolution: "An authorized historical announcement source.", status: "BLOCKED", current_state: "PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE", related_evidence: ["EVIDENCE-F"], related_artifacts: ["ART-F"], action_path: "/app/research/families/F",
  },
];

export const validation = [
  { record_id: "A-FORMAL", family_id: "A", validation_type: "Formal one-shot", period: "2025-01-01/2026-08-13", outcome: "INCONCLUSIVE", interpretation: "Inconclusive", integrity: "IMPLEMENTATION_DEFECT", pristine_intent: true, notes: "Implementation logic defect invalidated the pristine one-shot evaluation; this is not a formal fail.", artifact_ids: ["ART-A-FORMAL"], action_path: "/app/research/families/A#validation" },
  { record_id: "A-POST", family_id: "A", validation_type: "Post-remediation evaluation", period: "2025-01-01/2026-08-13", outcome: "FAIL", interpretation: "UNSUPPORTIVE", integrity: "NON_PRISTINE", pristine_intent: false, notes: "Separate post-outcome evidence; contaminated holdout does not replace formal validation.", artifact_ids: ["ART-A-POST"], action_path: "/app/research/families/A#validation" },
];

export function makeOverviewPayload(overrides = {}) {
  return {
    version: RESEARCH_VERSION,
    generated_at: timestamp,
    status: "AVAILABLE",
    reason: null,
    programme: { status: "PAUSED", cycle_status: "COMPLETE_NO_VALIDATED_STRATEGY", validated_strategy_count: 0, production_candidate_count: 0, strategy_v2_status: "NOT_CREATED", family_h_status: "NOT_PLANNED", paper_readiness: "NOT_READY", live_readiness: "NOT_READY", primary_programme: "PRODUCT_PLATFORM_PROGRAM", secondary_programme: "FORWARD_DATA_PROGRAM" },
    family_count: 7,
    reusable_evidence_count: 1,
    blocked_study_count: 2,
    production_ready_count: 0,
    families: "ABCDEFG".split("").map(family),
    retained_evidence: [evidence()],
    blocked,
    recent_activity: [{ event_id: "EVT-1", occurred_at: timestamp, family_id: "C", event: "Reference frozen research metadata", category: "Evidence Record", result: "Registered", related_artifacts: ["ART-C"], related_evidence: "EDGE-EVIDENCE-C-COMPRESSION-001" }],
    meta,
    ...overrides,
  };
}

export function makeFamilyDetailPayload(id = "A") {
  return {
    version: RESEARCH_VERSION,
    generated_at: timestamp,
    status: "AVAILABLE",
    family: family(id),
    hypothesis: "A frozen research hypothesis.",
    sections: id === "A" ? [
      { section_id: "formal-validation", title: "Formal validation", summary: "INCONCLUSIVE — an implementation logic defect invalidated the pristine one-shot evaluation. The formal result remains Inconclusive.", tone: "CAUTION" },
      { section_id: "post-remediation", title: "Post-remediation evaluation", summary: "FAIL / UNSUPPORTIVE — separate non-pristine post-outcome evidence.", tone: "NEGATIVE" },
      { section_id: "future-model-selection", title: "Future-model-selection note", summary: "2025–26 holdout contaminated. Do not present it as fresh validation evidence.", tone: "CAUTION" },
    ] : [],
    evidence: id === "C" ? [evidence()] : [],
    validation: id === "A" ? validation : [],
    timeline: [],
    artifacts: [{ artifact_id: "ART-A", name: "Family A Formal Validation Result", artifact_type: "VALIDATION_ARTIFACT", version: "V1", integrity: "IMMUTABLE", created_at: timestamp, lineage_node_id: "LIN-A" }],
    lineage: { nodes: [{ node_id: "LIN-A", stage: "SOURCE", source_system: "INTERSIGNAL_RESEARCH_CORPUS", entity_type: "FROZEN_RESEARCH_ARTIFACT", status: "ACTIVE" }], edges: [], integrity: "HEALTHY" },
    limitations: [],
    meta,
  };
}

export const listPayload = (items) => ({ version: RESEARCH_VERSION, generated_at: timestamp, status: "AVAILABLE", items, total_count: items.length, meta });

export function makeEvidenceDetailPayload() {
  return {
    version: RESEARCH_VERSION,
    generated_at: timestamp,
    status: "AVAILABLE",
    evidence: {
      ...evidence(),
      research_context: "Breakout continuation",
      current_disposition: "No portfolio-ready candidate",
      effective_period: "DEVELOPMENT",
      confidence: null,
      supporting_artifacts: [{ artifact_id: "ART-C", name: "Cross-Family Positive Evidence Registry", artifact_type: "RESEARCH_ARTIFACT", version: "V1", integrity: "IMMUTABLE", created_at: timestamp, lineage_node_id: "LIN-C" }],
      lineage: { nodes: [{ node_id: "LIN-C", stage: "SOURCE", source_system: "INTERSIGNAL_RESEARCH_CORPUS", entity_type: "FROZEN_RESEARCH_ARTIFACT", status: "ACTIVE" }], edges: [], integrity: "HEALTHY" },
    },
    meta,
  };
}

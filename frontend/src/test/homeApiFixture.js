const BASE_HOME_API_PAYLOAD = {
  version: "INTERSIGNAL_HOME_SNAPSHOT_V1",
  generated_at: "2026-09-18T09:00:00Z",
  mode: "BACKEND_READ_ONLY_PROTOTYPE",
  availability: {
    market: { status: "UNAVAILABLE", reason: "LIVE_MARKET_SERVICE_NOT_CONFIGURED" },
    portfolio: { status: "AVAILABLE", reason: null },
    research: { status: "AVAILABLE", reason: null },
    data_health: { status: "PARTIAL", reason: null },
    governance: { status: "AVAILABLE", reason: null },
    activity: { status: "AVAILABLE", reason: null },
  },
  market: {
    status: "UNAVAILABLE",
    reason: "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
    source: "NOT_CONFIGURED",
  },
  portfolio: {
    status: "AVAILABLE",
    reason: null,
    has_portfolio: true,
    portfolio_count: 2,
    portfolio_id: "PORT-MANUAL-INVESTMENT-SYNTHETIC-001",
    name: "Synthetic Manual Investment Portfolio",
    source_type: "SYNTHETIC",
    currency: "INR",
    valuation: "52393",
    cash: "42393",
    invested_value: "10000",
    invested_pct: "19.0865191915",
    period_change: "4.786",
    benchmark_delta: "2.786",
    concentration: "19.0865191915",
    sector_exposure: { Diversified: "19.0865191915" },
    holding_count: 1,
    valuation_timestamp: "2026-09-16T20:31:00Z",
  },
  research: {
    status: "AVAILABLE",
    reason: null,
    programme_status: "PAUSED",
    family_count: 7,
    production_candidate_count: 0,
    validated_production_strategy_count: 0,
    strategy_v2_status: "NOT_CREATED",
    reusable_evidence: [{
      id: "EDGE-EVIDENCE-C-COMPRESSION-001",
      title: "Family C compression signal evidence",
      summary: "Pre-breakout compression improved event-level signal quality in development research.",
      family: "C",
      status: "RESEARCH_ONLY",
      production_strategy: false,
    }],
    blocked_research: [
      {
        family: "D",
        reason_code: "DATA_BLOCKED",
        reason: "intraday continuity below frozen threshold",
        source_ref: "EVIDENCE-D-DATA-BLOCKED-001",
      },
      {
        family: "F",
        reason_code: "SOURCE_BLOCKED",
        reason: "authorized catalyst historical source unavailable",
        source_ref: "DATA-EVIDENCE-F-NSE-ANNOUNCEMENTS-001",
      },
    ],
    latest_research_state: "COMPLETE_NO_VALIDATED_STRATEGY",
  },
  data_health: {
    status: "PARTIAL",
    reason: null,
    lineage_integrity: "HEALTHY",
    broken_reference_count: 0,
    daily_history_status: "AVAILABLE",
    corporate_actions_status: "AVAILABLE_WITH_CAVEATS",
    intraday_status: "BLOCKED_FOR_RESEARCH_USE",
    catalyst_status: "SOURCE_BLOCKED",
    freshness_summary: "STATIC_SEEDED_PLATFORM_STATE",
    data_limitations: [
      "CORPORATE_ACTIONS_AVAILABLE_WITH_DOCUMENTED_CAVEATS",
      "FAMILY_D_INTRADAY_CONTINUITY_DATA_BLOCKED",
      "FAMILY_F_CATALYST_AUTHORIZED_SOURCE_REQUIRED",
    ],
  },
  governance: {
    status: "AVAILABLE",
    reason: null,
    paper_readiness: "NOT_READY",
    live_readiness: "NOT_READY",
    broker_readiness: "NOT_READY",
    production_readiness: "NOT_READY",
    blocking_violation_count: 0,
    pending_authorization_count: 1,
    policy_summary: { NO_LIVE_WITHOUT_VALIDATED_STRATEGY: "PASS" },
  },
  attention: [{
    id: "research-family-d-blocked",
    category: "Research data",
    title: "Family D research remains blocked.",
    summary: "intraday continuity below frozen threshold",
    severity: "WARNING",
    source_domain: "RESEARCH",
    source_ref: "EVIDENCE-D-DATA-BLOCKED-001",
    portfolio_context: null,
    research_context: "DATA_BLOCKED",
    action_target: "/app/research",
    metadata: { family: "D", investment_recommendation: false },
  }],
  recent_activity: [{
    id: "AUDIT-001",
    title: "Authorization requested",
    summary: "Record unresolved authorization gate",
    source_domain: "DATA",
    source_ref: "GOVERNANCE:DATA-SOURCE-CATALYST-HISTORY",
    occurred_at: "2026-09-16T22:35:00Z",
  }],
  meta: {
    read_only: true,
    auth_enforcement: "NOT_IMPLEMENTED",
    market_integration: "NOT_CONFIGURED",
    broker_integration: "NOT_IMPLEMENTED",
    data_scope: "SEEDED_LOCAL_PLATFORM_STATE",
    partial_response: true,
    source_contracts: [
      "INTERSIGNAL_RESEARCH_WORKBENCH_SNAPSHOT_V1",
      "INTERSIGNAL_PORTFOLIO_OS_SNAPSHOT_V1",
      "INTERSIGNAL_GOVERNANCE_AUDIT_SNAPSHOT_V1",
    ],
  },
};

export function makeHomeApiPayload(overrides = {}) {
  const payload = JSON.parse(JSON.stringify(BASE_HOME_API_PAYLOAD));
  for (const [key, value] of Object.entries(overrides)) {
    if (
      value
      && typeof value === "object"
      && !Array.isArray(value)
      && typeof payload[key] === "object"
      && !Array.isArray(payload[key])
    ) {
      payload[key] = { ...payload[key], ...value };
    } else {
      payload[key] = value;
    }
  }
  return payload;
}

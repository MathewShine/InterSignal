import { homeDemoData } from "./homeDemoData.js";

export const HOME_SNAPSHOT_CONTRACT_VERSION =
  "INTERSIGNAL_HOME_SNAPSHOT_V1";

const clone = (value) => JSON.parse(JSON.stringify(value));

const EXPLORE_NEXT = Object.freeze([
  { id: "market", label: "Market context", path: "/app/market" },
  { id: "portfolio", label: "Portfolio exposure", path: "/app/portfolio" },
  { id: "research", label: "Research evidence", path: "/app/research" },
  { id: "data", label: "Data health", path: "/app/data" },
]);

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCurrency(value, currency = "INR") {
  const parsed = toNumber(value);
  if (parsed === null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(parsed);
}

function formatPercentage(value, { signed = false } = {}) {
  const parsed = toNumber(value);
  if (parsed === null) return "—";
  const prefix = signed && parsed > 0 ? "+" : "";
  return `${prefix}${parsed.toFixed(2)}%`;
}

function displayStatus(value) {
  if (!value) return "Unavailable";
  const text = value.toLowerCase().replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function displayDataHealthStatus(id, value) {
  if (id === "daily" && value === "AVAILABLE") return "Ready";
  if (id === "actions" && value?.startsWith("AVAILABLE")) return "Available";
  if (id === "intraday" && (value?.includes("BLOCKED") || value?.includes("LIMITED"))) return "Limited";
  if (id === "catalyst" && value?.includes("BLOCKED")) return "Pending";
  if (id === "lineage" && value === "HEALTHY") return "Healthy";
  return displayStatus(value);
}

function slug(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

function normalizeAvailability(availability = {}) {
  const names = [
    "market",
    "portfolio",
    "research",
    "data_health",
    "governance",
    "activity",
  ];
  return Object.fromEntries(
    names.map((name) => [
      name === "data_health" ? "dataHealth" : name,
      {
        status: availability[name]?.status ?? "UNAVAILABLE",
        reason: availability[name]?.reason ?? null,
      },
    ]),
  );
}

function normalizeMarket(market = {}) {
  return {
    ...clone(homeDemoData.market),
    status: "illustrative",
    availability: market.status ?? "UNAVAILABLE",
    reason: market.reason ?? "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
    source: market.source ?? "NOT_CONFIGURED",
    visualizationMode: "ILLUSTRATIVE",
    label: "Sample market data",
  };
}

function portfolioSourceStatus(portfolio) {
  if (portfolio.status === "UNAVAILABLE") return "UNAVAILABLE";
  if (!portfolio.has_portfolio) return "EMPTY";
  return portfolio.source_type === "SYNTHETIC" ? "SYNTHETIC" : "REAL";
}

function normalizePortfolio(portfolio = {}) {
  const sourceStatus = portfolioSourceStatus(portfolio);
  if (sourceStatus === "UNAVAILABLE") {
    return {
      status: "unavailable",
      availability: "UNAVAILABLE",
      reason: portfolio.reason ?? "PORTFOLIO_SOURCE_UNAVAILABLE",
      sourceStatus,
    };
  }
  if (sourceStatus === "EMPTY") {
    return {
      status: "empty",
      availability: portfolio.status ?? "AVAILABLE",
      reason: portfolio.reason ?? "NO_PORTFOLIO_CONFIGURED",
      sourceStatus,
      hasPortfolio: false,
    };
  }

  const investedPercent = toNumber(portfolio.invested_pct) ?? 0;
  const allocations = Object.entries(portfolio.sector_exposure ?? {}).map(
    ([label, percent]) => ({
      id: slug(label),
      label,
      percent: Number(toNumber(percent)?.toFixed(2) ?? 0),
      context: "portfolio",
    }),
  );
  const cashPercent = Math.max(0, 100 - investedPercent);
  if (cashPercent > 0) {
    allocations.push({
      id: "cash",
      label: "Cash",
      percent: Number(cashPercent.toFixed(2)),
      context: "portfolio",
    });
  }

  return {
    status: "available",
    availability: portfolio.status ?? "AVAILABLE",
    sourceStatus,
    hasPortfolio: true,
    portfolioId: portfolio.portfolio_id,
    portfolioCount: portfolio.portfolio_count,
    name: portfolio.name,
    label: sourceStatus === "SYNTHETIC" ? "Demo portfolio" : "Portfolio",
    currency: portfolio.currency,
    value: formatCurrency(portfolio.valuation, portfolio.currency),
    cash: formatCurrency(portfolio.cash, portfolio.currency),
    investedValue: formatCurrency(portfolio.invested_value, portfolio.currency),
    investedPercent: formatPercentage(portfolio.invested_pct),
    invested: `${formatCurrency(portfolio.invested_value, portfolio.currency)} · ${formatPercentage(portfolio.invested_pct)}`,
    periodChange: formatPercentage(portfolio.period_change, { signed: true }),
    benchmarkDelta: formatPercentage(portfolio.benchmark_delta, { signed: true }),
    concentration: formatPercentage(portfolio.concentration),
    allocations,
    holdingCount: portfolio.holding_count,
    valuationTimestamp: portfolio.valuation_timestamp,
  };
}

function normalizeResearch(research = {}) {
  if (research.status === "UNAVAILABLE") {
    return {
      status: "unavailable",
      availability: "UNAVAILABLE",
      reason: research.reason ?? "RESEARCH_SOURCE_UNAVAILABLE",
      blocked: [],
      blockedItems: [],
    };
  }

  const evidence = research.reusable_evidence?.[0];
  const blockedItems = (research.blocked_research ?? []).map((item) => ({
    family: item.family,
    label: `Family ${item.family}`,
    reasonCode: item.reason_code,
    reason: item.reason,
    sourceRef: item.source_ref,
  }));
  return {
    status: research.status?.toLowerCase() ?? "available",
    availability: research.status ?? "AVAILABLE",
    programmeState: research.programme_status,
    programmeLabel: displayStatus(research.programme_status),
    families: research.family_count,
    productionCandidates: research.production_candidate_count,
    validatedStrategies: research.validated_production_strategy_count,
    strategyV2: research.strategy_v2_status,
    reusableEvidence: evidence?.title ?? "No reusable evidence",
    reusableEvidenceItems: (research.reusable_evidence ?? []).map((item) => ({
      id: item.id,
      title: item.title,
      summary: item.summary,
      family: item.family,
      status: item.status,
      productionStrategy: item.production_strategy,
    })),
    blocked: blockedItems.map((item) => item.label),
    blockedItems,
    latestResearchState: research.latest_research_state,
    evidence: evidence?.summary ?? "No reusable evidence is currently available.",
    evidenceLabel: "Research evidence",
    evidenceQualification: evidence?.production_strategy
      ? "Production strategy"
      : "Not production strategy",
  };
}

function dataTone(value) {
  if (["HEALTHY", "AVAILABLE"].includes(value)) return "healthy";
  if (value?.includes("BLOCKED")) return "blocked";
  return "caution";
}

function normalizeDataHealth(dataHealth = {}) {
  if (dataHealth.status === "UNAVAILABLE") {
    return {
      status: "unavailable",
      availability: "UNAVAILABLE",
      reason: dataHealth.reason ?? "DATA_HEALTH_SOURCE_UNAVAILABLE",
      rows: [],
      limitations: [],
    };
  }
  const values = [
    ["daily", "Daily history", dataHealth.daily_history_status],
    ["actions", "Corporate actions", dataHealth.corporate_actions_status],
    ["intraday", "Intraday research", dataHealth.intraday_status],
    ["catalyst", "Catalyst feed", dataHealth.catalyst_status],
    ["lineage", "Lineage integrity", dataHealth.lineage_integrity],
    ["refs", "Broken refs", String(dataHealth.broken_reference_count ?? 0)],
  ];
  return {
    status: dataHealth.status?.toLowerCase() ?? "partial",
    availability: dataHealth.status ?? "PARTIAL",
    lineageIntegrity: dataHealth.lineage_integrity,
    brokenReferenceCount: dataHealth.broken_reference_count,
    freshnessSummary: dataHealth.freshness_summary,
    limitations: dataHealth.data_limitations ?? [],
    rows: values.map(([id, label, value]) => ({
      id,
      label,
      value: id === "refs" ? value : displayStatus(value),
      displayValue: id === "refs" ? value : displayDataHealthStatus(id, value),
      rawValue: value,
      tone: id === "refs" ? "healthy" : dataTone(value),
    })),
  };
}

function normalizeGovernance(governance = {}) {
  if (governance.status === "UNAVAILABLE") {
    return {
      status: "unavailable",
      availability: "UNAVAILABLE",
      reason: governance.reason ?? "GOVERNANCE_SOURCE_UNAVAILABLE",
    };
  }
  return {
    status: governance.status?.toLowerCase() ?? "available",
    availability: governance.status ?? "AVAILABLE",
    paperState: governance.paper_readiness,
    liveState: governance.live_readiness,
    brokerState: governance.broker_readiness,
    productionState: governance.production_readiness,
    paper: displayStatus(governance.paper_readiness),
    live: displayStatus(governance.live_readiness),
    broker: displayStatus(governance.broker_readiness),
    brokerDisplay: governance.broker_readiness === "NOT_READY"
      ? "Not connected"
      : displayStatus(governance.broker_readiness),
    production: displayStatus(governance.production_readiness),
    blockingViolations: governance.blocking_violation_count,
    pendingAuthorizations: governance.pending_authorization_count,
    policySummary: governance.policy_summary ?? {},
  };
}

function actionLabel(path) {
  if (path?.endsWith("/research")) return "Open Research";
  if (path?.endsWith("/portfolio")) return "Open Portfolio";
  if (path?.endsWith("/governance")) return "Open Governance";
  if (path?.endsWith("/data")) return "Open Data";
  return "Open context";
}

function focusTarget(sourceDomain) {
  return {
    DATA: "dataHealth",
    GOVERNANCE: "governance",
    PORTFOLIO: "portfolio",
    RESEARCH: "research",
  }[sourceDomain] ?? null;
}

function normalizePlatformAttention(items = []) {
  return items.map((item) => ({
    id: item.id,
    category: item.category,
    title: item.title,
    summary: item.summary,
    severity: item.severity,
    sourceDomain: item.source_domain,
    sourceRef: item.source_ref,
    portfolioContext: item.portfolio_context ?? "—",
    researchContext: item.research_context ?? "—",
    timestampLabel: item.source_ref,
    actions: [
      {
        label: actionLabel(item.action_target),
        path: item.action_target,
      },
    ],
    metadata: {
      ...(item.metadata ?? {}),
      focusTarget: focusTarget(item.source_domain),
    },
    provenance: "PLATFORM",
    provenanceLabel: "Platform attention",
  }));
}

function illustrativeAttention() {
  return homeDemoData.attentionItems.slice(0, 2).map((item) => ({
    ...clone(item),
    portfolioContext: "No backend portfolio implication.",
    researchContext: "Illustrative only; no validated strategy implication.",
    sourceDomain: "MARKET",
    sourceRef: "LOCAL_MARKET_ILLUSTRATION",
    provenance: "ILLUSTRATIVE_MARKET",
    provenanceLabel: "Illustrative market context",
    metadata: {
      ...item.metadata,
      exposureIds: [],
      focusTarget: "market",
    },
  }));
}

function normalizeRecentActivity(items = []) {
  return items.map((item) => ({
    id: item.id,
    label: item.title,
    summary: item.summary,
    context: item.source_domain,
    sourceDomain: item.source_domain,
    sourceRef: item.source_ref,
    occurredAt: item.occurred_at,
  }));
}

function searchItems(research, portfolio) {
  return [
    ...(research.reusableEvidenceItems ?? []).map((item) => ({
      id: item.id,
      group: "Research",
      label: item.title,
      path: "/app/research",
    })),
    ...(research.blockedItems ?? []).map((item) => ({
      id: `family-${item.family.toLowerCase()}`,
      group: "Research",
      label: `${item.label} ${item.reason.toLowerCase()}`,
      path: "/app/research",
    })),
    ...(portfolio.sourceStatus === "SYNTHETIC"
      ? [{
        id: "portfolio-synthetic",
        group: "Portfolio",
        label: "Demo portfolio",
        path: "/app/portfolio",
      }]
      : []),
    {
      id: "market-illustrative",
      group: "Market",
      label: "Sample market context",
      path: "/app/market",
    },
    {
      id: "lineage",
      group: "Data",
      label: "Lineage integrity",
      path: "/app/data",
    },
  ];
}

export function normalizeHomeSnapshot(payload) {
  const availability = normalizeAvailability(payload.availability);
  const research = normalizeResearch(payload.research);
  const portfolio = normalizePortfolio(payload.portfolio);
  const dataHealth = normalizeDataHealth(payload.data_health);
  const governance = normalizeGovernance(payload.governance);
  const platformAttention = normalizePlatformAttention(payload.attention);
  const marketAttention = illustrativeAttention();
  const partial = Boolean(payload.meta?.partial_response);

  return {
    version: payload.version,
    backendContractVersion: payload.version,
    generatedAt: payload.generated_at,
    mode: payload.mode,
    profile: "ATTENTION_CONTEXT_PORTFOLIO_RESEARCH_HOME_V1",
    demoMode: false,
    connectionState: partial ? "PARTIAL" : "CONNECTED",
    environmentLabel: partial ? "CONNECTED · PARTIAL DATA" : "BACKEND CONNECTED",
    snapshotLabel: "Backend Home snapshot",
    availability,
    market: normalizeMarket(payload.market),
    portfolio,
    research,
    dataHealth,
    governance,
    attentionItems: [...platformAttention, ...marketAttention],
    recentActivity: normalizeRecentActivity(payload.recent_activity),
    exploreNext: clone(EXPLORE_NEXT),
    searchItems: searchItems(research, portfolio),
    projectState: {
      strategyResearch: research.programmeState,
      productionCandidates: research.productionCandidates,
      validatedProductionStrategies: research.validatedStrategies,
      strategyV2: research.strategyV2,
      paper: governance.paperState,
      live: governance.liveState,
      broker: governance.brokerState,
    },
    meta: {
      readOnly: payload.meta?.read_only === true,
      authEnforcement: payload.meta?.auth_enforcement,
      brokerIntegration: payload.meta?.broker_integration,
      marketIntegration: payload.meta?.market_integration,
      dataScope: payload.meta?.data_scope,
      partialResponse: partial,
      sourceContracts: payload.meta?.source_contracts ?? [],
    },
  };
}

export function createUnavailableHomeSnapshot({
  connectionState = "DISCONNECTED",
  reason = "HOME_API_UNAVAILABLE",
} = {}) {
  const unavailable = { status: "UNAVAILABLE", reason };
  const research = normalizeResearch({ status: "UNAVAILABLE", reason });
  const portfolio = normalizePortfolio({ status: "UNAVAILABLE", reason });
  return {
    version: HOME_SNAPSHOT_CONTRACT_VERSION,
    backendContractVersion: null,
    generatedAt: null,
    mode: "BACKEND_UNAVAILABLE",
    profile: "ATTENTION_CONTEXT_PORTFOLIO_RESEARCH_HOME_V1",
    demoMode: false,
    connectionState,
    environmentLabel: "BACKEND UNAVAILABLE",
    snapshotLabel: "Backend connection unavailable",
    availability: {
      market: {
        status: "UNAVAILABLE",
        reason: "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
      },
      portfolio: unavailable,
      research: unavailable,
      dataHealth: unavailable,
      governance: unavailable,
      activity: unavailable,
    },
    market: normalizeMarket(),
    portfolio,
    research,
    dataHealth: normalizeDataHealth({ status: "UNAVAILABLE", reason }),
    governance: normalizeGovernance({ status: "UNAVAILABLE", reason }),
    attentionItems: illustrativeAttention(),
    recentActivity: [],
    exploreNext: clone(EXPLORE_NEXT),
    searchItems: [
      {
        id: "market-illustrative",
        group: "Market",
        label: "Illustrative market context",
        path: "/app/market",
      },
    ],
    projectState: {},
    meta: {
      readOnly: true,
      authEnforcement: "NOT_IMPLEMENTED",
      brokerIntegration: "NOT_IMPLEMENTED",
      marketIntegration: "NOT_CONFIGURED",
      partialResponse: true,
      failureReason: reason,
    },
  };
}

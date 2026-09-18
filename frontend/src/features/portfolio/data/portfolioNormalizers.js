export const PORTFOLIO_CONTRACT_VERSION = "INTERSIGNAL_PORTFOLIO_OS_V1";

const number = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const meta = (value = {}) => ({
  readOnly: value.read_only !== false,
  sourceContract: value.source_contract,
  unavailableSections: value.unavailable_sections ?? [],
});

const option = (value) => ({
  id: value.portfolio_id,
  name: value.name,
  type: value.portfolio_type,
  sourceType: value.source_type,
  sourceLabel: value.source_type === "SYNTHETIC" ? "Demo portfolio" : "Portfolio",
});

const portfolio = (value) => value ? ({
  ...option(value),
  currency: value.currency,
  status: value.status,
}) : null;

export const normalizeLot = (value) => ({
  id: value.lot_id,
  acquisitionDate: value.acquisition_date,
  quantity: number(value.quantity),
  entryPrice: number(value.entry_price),
  costBasis: number(value.cost_basis),
  remainingQuantity: number(value.remaining_quantity),
  realizedStatus: value.realized_status,
});

export const normalizeHolding = (value) => ({
  id: value.holding_id,
  securityId: value.security_id,
  symbol: value.symbol,
  name: value.name,
  instrumentType: value.instrument_type,
  quantity: number(value.quantity),
  averageCost: number(value.average_cost),
  currentPrice: number(value.current_price),
  marketValue: number(value.market_value),
  costBasis: number(value.cost_basis),
  weight: number(value.weight),
  unrealizedPnl: number(value.unrealized_pnl),
  unrealizedPnlPercent: number(value.unrealized_pnl_pct),
  sector: value.sector,
  industry: value.industry,
  currency: value.currency,
  asOf: value.as_of,
  lots: (value.lots ?? []).map(normalizeLot),
});

export const normalizeBenchmark = (value) => value ? ({
  id: value.benchmark_id,
  name: value.name,
  portfolioReturn: number(value.portfolio_return),
  benchmarkReturn: number(value.benchmark_return),
  difference: number(value.difference),
  periodStart: value.period_start,
  periodEnd: value.period_end,
}) : null;

export const normalizePerformance = (value) => value ? ({
  realizedPnl: number(value.realized_pnl),
  unrealizedPnl: number(value.unrealized_pnl),
  totalPnl: number(value.total_pnl),
  benchmark: normalizeBenchmark(value.benchmark),
  points: (value.points ?? []).map((point) => ({
    date: point.date,
    equity: number(point.equity),
    cash: number(point.cash),
    investedValue: number(point.invested_value),
    dailyReturn: number(point.daily_return),
    cumulativeReturn: number(point.cumulative_return),
    benchmarkValue: number(point.benchmark_value),
  })),
  chartAvailable: Boolean(value.chart_available),
}) : null;

export const normalizeActivity = (value) => ({
  id: value.activity_id,
  occurredAt: value.occurred_at,
  type: value.activity_type,
  security: value.security,
  quantity: number(value.quantity),
  amount: number(value.amount),
  currency: value.currency,
  reference: value.reference,
  description: value.description,
});

const base = (payload) => ({
  version: payload.version,
  generatedAt: payload.generated_at,
  status: payload.status,
  reason: payload.reason,
  hasPortfolio: Boolean(payload.has_portfolio),
  portfolio: portfolio(payload.portfolio),
  portfolios: (payload.portfolios ?? []).map(option),
  meta: meta(payload.meta),
});

export function normalizeOverview(payload) {
  return {
    ...base(payload),
    summary: payload.summary ? {
      portfolioValue: number(payload.summary.portfolio_value),
      invested: number(payload.summary.invested),
      cash: number(payload.summary.cash),
      investedPercent: number(payload.summary.invested_pct),
      cashPercent: number(payload.summary.cash_pct),
      costBasis: number(payload.summary.cost_basis),
      realizedPnl: number(payload.summary.realized_pnl),
      unrealizedPnl: number(payload.summary.unrealized_pnl),
      totalPnl: number(payload.summary.total_pnl),
      valuationTimestamp: payload.summary.valuation_timestamp,
    } : null,
    holdings: (payload.holdings ?? []).map(normalizeHolding),
    allocation: payload.allocation ? {
      investedPercent: number(payload.allocation.invested_pct),
      cashPercent: number(payload.allocation.cash_pct),
      grossExposure: number(payload.allocation.gross_exposure),
      netExposure: number(payload.allocation.net_exposure),
      sectors: (payload.allocation.sectors ?? []).map((item) => ({ label: item.label, weight: number(item.weight) })),
    } : null,
    concentration: payload.concentration ? {
      holdingCount: payload.concentration.holding_count,
      topHoldingWeight: number(payload.concentration.top_holding_weight),
      topSectorWeight: number(payload.concentration.top_sector_weight),
      topFiveWeight: number(payload.concentration.top_five_weight),
      riskFlags: payload.concentration.risk_flags ?? [],
    } : null,
    benchmark: normalizeBenchmark(payload.benchmark),
    performance: normalizePerformance(payload.performance),
    recentActivity: (payload.recent_activity ?? []).map(normalizeActivity),
  };
}

export const normalizeHoldings = (payload) => ({
  ...base(payload),
  items: (payload.items ?? []).map(normalizeHolding),
  totalCount: payload.total_count,
});

export const normalizeActivityList = (payload) => ({
  ...base(payload),
  items: (payload.items ?? []).map(normalizeActivity),
  totalCount: payload.total_count,
});

export const normalizePerformanceResponse = (payload) => ({
  ...base(payload),
  performance: normalizePerformance(payload.performance),
});

export const statusLabel = (value) => ({
  AVAILABLE: "Available",
  PARTIAL: "Partial",
  UNAVAILABLE: "Unavailable",
  SYNTHETIC: "Demo portfolio",
  FULLY_REALIZED: "Fully realised",
  PARTIALLY_REALIZED: "Partly realised",
  OPEN: "Open",
}[value] ?? String(value ?? "—").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()));

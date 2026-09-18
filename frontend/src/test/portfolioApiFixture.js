export const holding = {
  holding_id: "HLD-1",
  security_id: "SEC-1",
  symbol: "SYN-MF-001",
  name: "Synthetic Mutual Fund One",
  instrument_type: "MUTUAL_FUND",
  quantity: "80",
  average_cost: "100.05",
  current_price: "125",
  market_value: "10000",
  cost_basis: "8004",
  weight: "0.1908651919",
  unrealized_pnl: "1996",
  unrealized_pnl_pct: "0.249375",
  sector: "Diversified",
  industry: "Mutual Fund",
  currency: "INR",
  as_of: "2026-09-16T20:27:00Z",
  lots: [{ lot_id: "LOT-1", acquisition_date: "2026-09-15", quantity: "100", entry_price: "100.05", cost_basis: "8004", remaining_quantity: "80", realized_status: "PARTIALLY_REALIZED" }],
};

const common = {
  version: "INTERSIGNAL_PORTFOLIO_OS_V1",
  generated_at: "2026-09-18T12:00:00Z",
  status: "AVAILABLE",
  reason: null,
  has_portfolio: true,
  portfolio: { portfolio_id: "PORT-1", name: "Synthetic Manual Investment Portfolio", portfolio_type: "MANUAL", source_type: "SYNTHETIC", currency: "INR", status: "ACTIVE" },
  portfolios: [
    { portfolio_id: "PORT-1", name: "Synthetic Manual Investment Portfolio", portfolio_type: "MANUAL", source_type: "SYNTHETIC" },
    { portfolio_id: "PORT-2", name: "Synthetic Research Portfolio", portfolio_type: "RESEARCH", source_type: "SYNTHETIC" },
  ],
  meta: { read_only: true, source_contract: "INTERSIGNAL_PORTFOLIO_OS_SNAPSHOT_V1", auth_enforcement: "NOT_IMPLEMENTED", broker_integration: "NOT_IMPLEMENTED", live_market_integration: "NOT_CONFIGURED", internal_paths_exposed: false, unavailable_sections: [] },
};

export function makePortfolioOverview(overrides = {}) {
  return {
    ...common,
    summary: { portfolio_value: "52393", invested: "10000", cash: "42393", invested_pct: "0.1908651919", cash_pct: "0.8091348081", cost_basis: "8004", realized_pnl: "397", unrealized_pnl: "1996", total_pnl: "2393", valuation_timestamp: "2026-09-16T20:31:00Z" },
    holdings: [holding],
    allocation: { invested_pct: "0.1908651919", cash_pct: "0.8091348081", gross_exposure: "0.1908651919", net_exposure: "0.1908651919", sectors: [{ label: "Diversified", weight: "0.1908651919" }] },
    concentration: { holding_count: 1, top_holding_weight: "0.1908651919", top_sector_weight: "0.1908651919", top_five_weight: "0.1908651919", risk_flags: [] },
    benchmark: { benchmark_id: "BMK-1", name: "Synthetic Manual Investment Index", portfolio_return: "0.04786", benchmark_return: "0.02", difference: "0.02786", period_start: "2026-09-14", period_end: "2026-09-16" },
    performance: { realized_pnl: "397", unrealized_pnl: "1996", total_pnl: "2393", benchmark: { benchmark_id: "BMK-1", name: "Synthetic Manual Investment Index", portfolio_return: "0.04786", benchmark_return: "0.02", difference: "0.02786", period_start: "2026-09-14", period_end: "2026-09-16" }, points: [{ date: "2026-09-14", equity: "0", cash: "50000", invested_value: "0", daily_return: "0", cumulative_return: "0", benchmark_value: null }, { date: "2026-09-16", equity: "10000", cash: "42393", invested_value: "8004", daily_return: "0.04786", cumulative_return: "0.04786", benchmark_value: "51000" }], chart_available: false },
    recent_activity: [{ activity_id: "TXN-SELL", occurred_at: "2026-09-16", activity_type: "SELL", security: "SYN-MF-001", quantity: "20", amount: "2398", currency: "INR", reference: "TXN-SELL", description: null }],
    ...overrides,
  };
}

export function makeHoldingsPayload(overrides = {}) {
  return { ...common, items: [holding], total_count: 1, ...overrides };
}

export function makeActivityPayload(overrides = {}) {
  return { ...common, items: makePortfolioOverview().recent_activity, total_count: 1, ...overrides };
}

export function makePerformancePayload(overrides = {}) {
  return { ...common, performance: makePortfolioOverview().performance, ...overrides };
}

export function makeEmptyPortfolio() {
  return { ...makePortfolioOverview(), has_portfolio: false, portfolio: null, portfolios: [], reason: "NO_PORTFOLIO_CONFIGURED", summary: null, holdings: [], allocation: null, concentration: null, benchmark: null, performance: null, recent_activity: [] };
}

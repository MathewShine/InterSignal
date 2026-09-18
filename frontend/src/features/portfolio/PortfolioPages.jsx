import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { portfolioDataService } from "./data/apiPortfolioAdapter.js";
import {
  ActivityList,
  AllocationPanel,
  HoldingDrawer,
  HoldingsTable,
  PartialNotice,
  PerformancePanel,
  PortfolioEmpty,
  PortfolioError,
  PortfolioLayout,
  PortfolioLoading,
  PortfolioPageHeader,
  PortfolioSummary,
  SectionHeading,
  SourceLabel,
  formatCurrency,
  formatDate,
  formatPercent,
  usePortfolioResource,
  useSelectedPortfolioId,
} from "./components/PortfolioLayout.jsx";

function LoadedPortfolioPage({ state, children }) {
  if (state.status === "loading") return <PortfolioLoading />;
  if (state.status === "error") return <PortfolioError error={state.error} onRetry={state.retry} />;
  if (!state.data.hasPortfolio) return <PortfolioEmpty portfolio={state.data.portfolio} portfolios={state.data.portfolios} />;
  return children(state.data);
}

function pageActions(data) {
  return <><SourceLabel sourceType={data.portfolio.sourceType} /><span className="portfolio-read-only">Read-only</span></>;
}

export function PortfolioOverviewPage({ dataService = portfolioDataService }) {
  const portfolioId = useSelectedPortfolioId();
  const loader = useCallback((options) => dataService.getOverview({ ...options, portfolioId }), [dataService, portfolioId]);
  const state = usePortfolioResource(loader, [portfolioId]);
  const [selectedHolding, setSelectedHolding] = useState(null);
  return (
    <LoadedPortfolioPage state={state}>{(data) => (
      <PortfolioLayout connectionState={data.status === "PARTIAL" ? "PARTIAL" : "CONNECTED"} portfolio={data.portfolio} portfolios={data.portfolios}>
        <PortfolioPageHeader actions={pageActions(data)} />
        <PartialNotice unavailable={data.meta.unavailableSections} />
        <PortfolioSummary benchmark={data.benchmark} portfolio={data.portfolio} summary={data.summary} />
        <section className="portfolio-overview-grid">
          <article className="portfolio-surface holdings-overview">
            <SectionHeading eyebrow="OWNERSHIP" title="Holdings" action={<Link to="/app/portfolio/holdings">All holdings →</Link>} />
            <HoldingsTable compact items={data.holdings} onSelect={setSelectedHolding} />
          </article>
          <AllocationPanel allocation={data.allocation} concentration={data.concentration} />
        </section>
        <section className="portfolio-lower-grid">
          <PerformancePanel compact currency={data.portfolio.currency} performance={data.performance} />
          <article className="portfolio-surface recent-activity-panel"><SectionHeading eyebrow="LEDGER" title="Recent portfolio activity" action={<Link to="/app/portfolio/activity">View activity →</Link>} /><ActivityList currency={data.portfolio.currency} items={data.recentActivity} limit={4} /></article>
        </section>
        <HoldingDrawer holding={selectedHolding} onClose={() => setSelectedHolding(null)} />
      </PortfolioLayout>
    )}</LoadedPortfolioPage>
  );
}

export function PortfolioHoldingsPage({ dataService = portfolioDataService }) {
  const portfolioId = useSelectedPortfolioId();
  const loader = useCallback((options) => dataService.getHoldings({ ...options, portfolioId }), [dataService, portfolioId]);
  const state = usePortfolioResource(loader, [portfolioId]);
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");
  const [sort, setSort] = useState({ key: "marketValue", direction: "desc" });
  const [selectedHolding, setSelectedHolding] = useState(null);
  const changeSort = (key) => setSort((current) => ({ key, direction: current.key === key ? (current.direction === "desc" ? "asc" : "desc") : "asc" }));

  return (
    <LoadedPortfolioPage state={state}>{(data) => {
      const sectors = [...new Set(data.items.map((item) => item.sector).filter(Boolean))].sort();
      const filtered = data.items.filter((item) => {
        const match = `${item.name} ${item.symbol} ${item.sector ?? ""} ${item.industry ?? ""}`.toLowerCase();
        return (!query || match.includes(query.toLowerCase())) && (!sector || item.sector === sector);
      }).sort((left, right) => {
        const a = left[sort.key];
        const b = right[sort.key];
        const result = typeof a === "string" ? a.localeCompare(b) : (a ?? -Infinity) - (b ?? -Infinity);
        return sort.direction === "asc" ? result : -result;
      });
      return (
        <PortfolioLayout portfolio={data.portfolio} portfolios={data.portfolios}>
          <PortfolioPageHeader actions={pageActions(data)} description="Search, sort and inspect the positions recorded by Portfolio OS." eyebrow="OWNERSHIP" title="Holdings" />
          <div className="portfolio-filters">
            <label><span>Search</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Security, symbol or sector" type="search" value={query} /></label>
            <label><span>Sector</span><select onChange={(event) => setSector(event.target.value)} value={sector}><option value="">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}</select></label>
            <p aria-live="polite">{filtered.length} of {data.totalCount} holdings · sorted by {sort.key.replace(/([A-Z])/g, " $1").toLowerCase()} {sort.direction === "asc" ? "ascending" : "descending"}</p>
          </div>
          <section className="portfolio-surface holdings-page-table"><HoldingsTable items={filtered} onSelect={setSelectedHolding} onSort={changeSort} sort={sort} /></section>
          <HoldingDrawer holding={selectedHolding} onClose={() => setSelectedHolding(null)} />
        </PortfolioLayout>
      );
    }}</LoadedPortfolioPage>
  );
}

export function PortfolioActivityPage({ dataService = portfolioDataService }) {
  const portfolioId = useSelectedPortfolioId();
  const loader = useCallback((options) => dataService.getActivity({ ...options, portfolioId }), [dataService, portfolioId]);
  const state = usePortfolioResource(loader, [portfolioId]);
  return (
    <LoadedPortfolioPage state={state}>{(data) => (
      <PortfolioLayout portfolio={data.portfolio} portfolios={data.portfolios}>
        <PortfolioPageHeader actions={pageActions(data)} description="Transactions and operational records from the Portfolio OS ledger." eyebrow="LEDGER" title="Portfolio activity" />
        <section className="portfolio-surface activity-page-list"><SectionHeading eyebrow={`${data.totalCount} RECORDS`} title="Recorded activity" /><ActivityList currency={data.portfolio.currency} items={data.items} /></section>
      </PortfolioLayout>
    )}</LoadedPortfolioPage>
  );
}

export function PortfolioPerformancePage({ dataService = portfolioDataService }) {
  const portfolioId = useSelectedPortfolioId();
  const loader = useCallback((options) => dataService.getPerformance({ ...options, portfolioId }), [dataService, portfolioId]);
  const state = usePortfolioResource(loader, [portfolioId]);
  return (
    <LoadedPortfolioPage state={state}>{(data) => (
      <PortfolioLayout portfolio={data.portfolio} portfolios={data.portfolios}>
        <PortfolioPageHeader actions={pageActions(data)} description="Recorded returns, P&L and benchmark context from Portfolio OS." eyebrow="PERFORMANCE" title="Performance" />
        <PerformancePanel currency={data.portfolio.currency} performance={data.performance} />
        {data.performance ? (
          <section className="portfolio-surface performance-records"><SectionHeading eyebrow="SOURCE VALUES" title="Valuation history" /><div className="performance-point-table"><table><caption className="sr-only">Recorded Portfolio OS performance points</caption><thead><tr><th>Date</th><th>Equity</th><th>Cash</th><th>Invested capital</th><th>Daily return</th><th>Cumulative return</th><th>Benchmark value</th></tr></thead><tbody>{data.performance.points.map((point) => <tr key={point.date}><th scope="row">{formatDate(point.date)}</th><td>{formatCurrency(point.equity, data.portfolio.currency)}</td><td>{formatCurrency(point.cash, data.portfolio.currency)}</td><td>{formatCurrency(point.investedValue, data.portfolio.currency)}</td><td>{formatPercent(point.dailyReturn, { signed: true })}</td><td>{formatPercent(point.cumulativeReturn, { signed: true })}</td><td>{formatCurrency(point.benchmarkValue, data.portfolio.currency)}</td></tr>)}</tbody></table></div></section>
        ) : null}
      </PortfolioLayout>
    )}</LoadedPortfolioPage>
  );
}

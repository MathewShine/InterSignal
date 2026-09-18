import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AuthenticatedShell } from "../../home/components/AuthenticatedShell.jsx";
import { statusLabel } from "../data/portfolioNormalizers.js";

export const portfolioSearchItems = [
  { id: "portfolio-overview", group: "Portfolio", label: "Portfolio", path: "/app/portfolio" },
  { id: "portfolio-holdings", group: "Portfolio", label: "Holdings", path: "/app/portfolio/holdings" },
  { id: "portfolio-activity", group: "Portfolio", label: "Portfolio activity", path: "/app/portfolio/activity" },
  { id: "portfolio-performance", group: "Portfolio", label: "Performance", path: "/app/portfolio/performance" },
];

const navigation = [
  ["Overview", "/app/portfolio"],
  ["Holdings", "/app/portfolio/holdings"],
  ["Performance", "/app/portfolio/performance"],
  ["Activity", "/app/portfolio/activity"],
];

export function PortfolioLayout({ children, connectionState = "CONNECTED", portfolio, portfolios = [] }) {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    document.body.classList.add("app-route-active");
    return () => document.body.classList.remove("app-route-active");
  }, []);

  const selectPortfolio = (event) => {
    const value = event.target.value;
    const query = value ? `?portfolio_id=${encodeURIComponent(value)}` : "";
    navigate(`${location.pathname}${query}`);
  };

  return (
    <AuthenticatedShell area="Portfolio" connectionState={connectionState} marketMode="PORTFOLIO" searchItems={portfolioSearchItems}>
      <div className="portfolio-workspace">
        <div className="portfolio-subnav-row">
          <nav aria-label="Portfolio sections" className="portfolio-subnav">
            {navigation.map(([label, path]) => (
              <NavLink className={({ isActive }) => isActive ? "is-active" : undefined} end={path === "/app/portfolio"} key={path} to={path}>{label}</NavLink>
            ))}
          </nav>
          {portfolios.length > 1 ? (
            <label className="portfolio-selector">
              <span>Portfolio</span>
              <select aria-label="Select portfolio" onChange={selectPortfolio} value={portfolio?.id ?? ""}>
                {portfolios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
          ) : null}
        </div>
        {children}
      </div>
    </AuthenticatedShell>
  );
}

export function useSelectedPortfolioId() {
  const [params] = useSearchParams();
  return params.get("portfolio_id") || undefined;
}

export function usePortfolioResource(loader, dependencies = []) {
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    loader({ signal: controller.signal })
      .then((data) => { if (current) setState({ status: "ready", data, error: null }); })
      .catch((error) => {
        if (current && error?.code !== "PORTFOLIO_API_CANCELLED") setState({ status: "error", data: null, error });
      });
    return () => { current = false; controller.abort(); };
  }, [loader, reloadKey, ...dependencies]);
  const retry = useCallback(() => setReloadKey((key) => key + 1), []);
  return { ...state, retry };
}

export function PortfolioPageHeader({ title = "Portfolio", description = "Holdings, allocation, performance and exposure in one view.", eyebrow = "PORTFOLIO OS", actions }) {
  return (
    <header className="portfolio-page-header">
      <div><span className="technical-label">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {actions ? <div className="portfolio-page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function PortfolioLoading() {
  return (
    <PortfolioLayout connectionState="CONNECTING">
      <div aria-label="Loading Portfolio" className="portfolio-loading" role="status">
        <div className="portfolio-skeleton portfolio-skeleton--title" />
        <div className="portfolio-skeleton portfolio-skeleton--summary" />
        <div className="portfolio-loading__grid">
          <div>{Array.from({ length: 5 }, (_, index) => <div className="portfolio-skeleton portfolio-skeleton--row" key={index} />)}</div>
          <div><div className="portfolio-skeleton portfolio-skeleton--band" /><div className="portfolio-skeleton portfolio-skeleton--panel" /></div>
        </div>
        <span className="sr-only">Loading Portfolio data…</span>
      </div>
    </PortfolioLayout>
  );
}

export function PortfolioError({ error, onRetry }) {
  return (
    <PortfolioLayout connectionState="DISCONNECTED">
      <section className="portfolio-error" role="alert">
        <span className="technical-label">PORTFOLIO UNAVAILABLE</span>
        <h1>Portfolio data couldn’t be loaded.</h1>
        <p>{error?.code === "PORTFOLIO_API_INCOMPATIBLE" ? "This Portfolio data version isn’t supported." : "No demo holdings have been substituted."}</p>
        <button className="button button--primary" onClick={onRetry} type="button">Retry</button>
      </section>
    </PortfolioLayout>
  );
}

export function PortfolioEmpty({ portfolio, portfolios }) {
  return (
    <PortfolioLayout portfolio={portfolio} portfolios={portfolios}>
      <PortfolioPageHeader />
      <section className="portfolio-empty-state">
        <span className="technical-label">READ-ONLY PORTFOLIO</span>
        <h2>No portfolio yet.</h2>
        <p>Add holdings manually.</p>
        <div><button disabled type="button">Add holdings manually</button><button disabled type="button">Connect broker <small>Coming later</small></button></div>
      </section>
    </PortfolioLayout>
  );
}

export function PartialNotice({ unavailable = [] }) {
  if (!unavailable.length) return null;
  return <div className="portfolio-inline-notice" role="status">Some Portfolio sections are temporarily unavailable: {unavailable.join(", ")}.</div>;
}

export function SourceLabel({ sourceType }) {
  return (
    <span className="portfolio-source-label" title="This portfolio is generated from the platform’s seeded Portfolio OS data.">
      {sourceType === "SYNTHETIC" ? "Demo portfolio" : "Portfolio"}
    </span>
  );
}

export function formatCurrency(value, currency = "INR", maximumFractionDigits = 2) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits }).format(value);
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(value);
}

export function formatPercent(value, { signed = false } = {}) {
  if (value === null || value === undefined) return "Unavailable";
  const formatted = new Intl.NumberFormat("en-IN", { style: "percent", maximumFractionDigits: 2, signDisplay: signed ? "exceptZero" : "auto" }).format(value);
  return formatted;
}

export function formatDate(value, includeTime = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", includeTime ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" } : { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(parsed);
}

export function PortfolioSummary({ portfolio, summary, benchmark }) {
  if (!summary) return <SectionUnavailable title="Portfolio summary" />;
  const returnValue = benchmark?.portfolioReturn;
  return (
    <section aria-label="Portfolio summary" className="portfolio-summary-surface">
      <div className="portfolio-summary-primary">
        <div><span>Portfolio value</span><strong>{formatCurrency(summary.portfolioValue, portfolio.currency, 0)}</strong></div>
        <div className="portfolio-summary-meta"><SourceLabel sourceType={portfolio.sourceType} /><time dateTime={summary.valuationTimestamp}>Valued {formatDate(summary.valuationTimestamp, true)} UTC</time></div>
      </div>
      <div className="portfolio-summary-metric"><span>Invested</span><strong>{formatCurrency(summary.invested, portfolio.currency, 0)}</strong><small>{formatPercent(summary.investedPercent)} allocated</small></div>
      <div className="portfolio-summary-metric"><span>Cash</span><strong>{formatCurrency(summary.cash, portfolio.currency, 0)}</strong><small>{formatPercent(summary.cashPercent)} available</small></div>
      <div className="portfolio-summary-metric"><span>Period change</span><strong className={returnValue >= 0 ? "is-positive" : "is-negative"}>{formatPercent(returnValue, { signed: true })}</strong><small>{benchmark ? `${formatDate(benchmark.periodStart)}–${formatDate(benchmark.periodEnd)}` : "Unavailable"}</small></div>
      <div className="portfolio-summary-metric"><span>vs benchmark</span><strong className={benchmark?.difference >= 0 ? "is-positive" : "is-negative"}>{formatPercent(benchmark?.difference, { signed: true })}</strong><small>{benchmark?.name ?? "Benchmark unavailable"}</small></div>
    </section>
  );
}

export function SectionHeading({ eyebrow, title, action }) {
  return <div className="portfolio-section-heading"><div><span className="technical-label">{eyebrow}</span><h2>{title}</h2></div>{action}</div>;
}

export function SectionUnavailable({ title }) {
  return <div className="portfolio-section-unavailable"><strong>{title}</strong><span>{title} data unavailable.</span></div>;
}

export function AllocationPanel({ allocation, concentration }) {
  if (!allocation) return <article className="portfolio-surface"><SectionHeading eyebrow="ALLOCATION" title="Allocation & exposure" /><SectionUnavailable title="Allocation" /></article>;
  const invested = Math.max(0, Math.min(1, allocation.investedPercent ?? 0));
  const cash = Math.max(0, Math.min(1, allocation.cashPercent ?? 0));
  return (
    <article className="portfolio-surface portfolio-allocation-panel">
      <SectionHeading eyebrow="CAPITAL" title="Allocation & exposure" />
      <div className="allocation-content">
        <div aria-label={`Invested ${formatPercent(invested)}; cash ${formatPercent(cash)}`} className="allocation-band" role="img">
          <span className="allocation-band__invested" style={{ width: `${invested * 100}%` }} /><span className="allocation-band__cash" style={{ width: `${cash * 100}%` }} />
        </div>
        <div className="allocation-legend"><span><i data-tone="invested" />Invested <b>{formatPercent(invested)}</b></span><span><i data-tone="cash" />Cash <b>{formatPercent(cash)}</b></span></div>
        <div className="exposure-list"><h3>Sector exposure</h3>{allocation.sectors.length ? allocation.sectors.map((item) => <div key={item.label}><span>{item.label}</span><div><i style={{ width: `${Math.min(item.weight * 100, 100)}%` }} /></div><strong>{formatPercent(item.weight)}</strong></div>) : <p>Sector exposure unavailable.</p>}</div>
        {concentration ? <div className="concentration-grid"><div><span>Top holding</span><strong>{formatPercent(concentration.topHoldingWeight)}</strong></div><div><span>Top sector</span><strong>{formatPercent(concentration.topSectorWeight)}</strong></div><div><span>Holdings</span><strong>{concentration.holdingCount}</strong></div></div> : <SectionUnavailable title="Concentration" />}
      </div>
    </article>
  );
}

export function HoldingsTable({ items, compact = false, onSelect, sort, onSort }) {
  if (!items.length) return <div className="portfolio-list-empty">No holdings in this portfolio.</div>;
  const heading = (key, label) => (
    onSort ? <button aria-label={`Sort by ${label}`} onClick={() => onSort(key)} type="button">{label}{sort?.key === key ? <span aria-hidden="true"> {sort.direction === "asc" ? "↑" : "↓"}</span> : null}</button> : label
  );
  return (
    <>
      <div className={`portfolio-table-wrap${compact ? " is-compact" : ""}`}>
        <table><caption className="sr-only">Portfolio holdings</caption><thead><tr>
          <th aria-sort={sort?.key === "name" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} scope="col">{heading("name", "Security")}</th>
          <th aria-sort={sort?.key === "quantity" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} scope="col">{heading("quantity", "Quantity")}</th>
          <th scope="col">Average cost</th><th scope="col">Valuation price</th>
          <th aria-sort={sort?.key === "marketValue" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} scope="col">{heading("marketValue", "Market value")}</th>
          <th aria-sort={sort?.key === "weight" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} scope="col">{heading("weight", "Weight")}</th>
          <th aria-sort={sort?.key === "unrealizedPnl" ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} scope="col">{heading("unrealizedPnl", "Unrealised P&L")}</th>
          <th scope="col">Sector</th><th scope="col"><span className="sr-only">Detail</span></th>
        </tr></thead><tbody>{items.map((item) => <tr key={item.id}>
          <th scope="row"><strong>{item.name}</strong><span>{item.symbol} · {statusLabel(item.instrumentType)}</span></th>
          <td className="numeric">{formatNumber(item.quantity, 4)}</td><td className="numeric">{formatCurrency(item.averageCost, item.currency)}</td><td className="numeric">{formatCurrency(item.currentPrice, item.currency)}</td>
          <td className="numeric"><strong>{formatCurrency(item.marketValue, item.currency)}</strong></td><td className="numeric">{formatPercent(item.weight)}</td>
          <td className={`numeric ${item.unrealizedPnl >= 0 ? "is-positive" : "is-negative"}`}><strong>{formatCurrency(item.unrealizedPnl, item.currency)}</strong><span>{formatPercent(item.unrealizedPnlPercent, { signed: true })}</span></td>
          <td>{item.sector ?? "—"}</td><td><button className="portfolio-row-action" onClick={() => onSelect?.(item)} type="button">View</button></td>
        </tr>)}</tbody></table>
      </div>
      <div className="holding-card-list">{items.map((item) => <button className="holding-card" key={item.id} onClick={() => onSelect?.(item)} type="button"><span><strong>{item.name}</strong><small>{item.symbol} · {item.sector ?? "Sector unavailable"}</small></span><span><strong>{formatCurrency(item.marketValue, item.currency)}</strong><small>{formatPercent(item.weight)} weight</small></span><span className={item.unrealizedPnl >= 0 ? "is-positive" : "is-negative"}>{formatCurrency(item.unrealizedPnl, item.currency)} <small>{formatPercent(item.unrealizedPnlPercent, { signed: true })}</small></span><b aria-hidden="true">→</b></button>)}</div>
    </>
  );
}

export function HoldingDrawer({ holding, onClose }) {
  const closeRef = useRef(null);
  useEffect(() => {
    if (!holding) return undefined;
    closeRef.current?.focus();
    const onKeyDown = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [holding, onClose]);
  if (!holding) return null;
  return (
    <div className="holding-drawer-backdrop" onMouseDown={onClose}>
      <aside aria-label={`${holding.name} holding detail`} aria-modal="true" className="holding-drawer" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <header><div><span className="technical-label">READ-ONLY HOLDING</span><h2>{holding.name}</h2><p>{holding.symbol} · {statusLabel(holding.instrumentType)}</p></div><button aria-label="Close holding detail" onClick={onClose} ref={closeRef} type="button">×</button></header>
        <dl className="holding-detail-grid"><div><dt>Quantity</dt><dd>{formatNumber(holding.quantity, 4)}</dd></div><div><dt>Cost basis</dt><dd>{formatCurrency(holding.costBasis, holding.currency)}</dd></div><div><dt>Market value</dt><dd>{formatCurrency(holding.marketValue, holding.currency)}</dd></div><div><dt>Weight</dt><dd>{formatPercent(holding.weight)}</dd></div><div><dt>Sector</dt><dd>{holding.sector ?? "Unavailable"}</dd></div><div><dt>Unrealised P&L</dt><dd className={holding.unrealizedPnl >= 0 ? "is-positive" : "is-negative"}>{formatCurrency(holding.unrealizedPnl, holding.currency)}</dd></div></dl>
        <section><h3>FIFO lots</h3>{holding.lots.length ? <div className="lot-list">{holding.lots.map((lot) => <article key={lot.id}><div><strong>{formatDate(lot.acquisitionDate)}</strong><span>{statusLabel(lot.realizedStatus)}</span></div><dl><div><dt>Original quantity</dt><dd>{formatNumber(lot.quantity, 4)}</dd></div><div><dt>Remaining</dt><dd>{formatNumber(lot.remainingQuantity, 4)}</dd></div><div><dt>Entry price</dt><dd>{formatCurrency(lot.entryPrice, holding.currency)}</dd></div><div><dt>Cost basis</dt><dd>{formatCurrency(lot.costBasis, holding.currency)}</dd></div></dl></article>)}</div> : <p className="portfolio-list-empty">No lot detail is available.</p>}</section>
      </aside>
    </div>
  );
}

export function PerformancePanel({ performance, currency, compact = false }) {
  if (!performance) return <article className="portfolio-surface"><SectionHeading eyebrow="PERFORMANCE" title="Performance" /><SectionUnavailable title="Performance" /></article>;
  const benchmark = performance.benchmark;
  return (
    <article className={`portfolio-surface performance-panel${compact ? " is-compact" : ""}`}>
      <SectionHeading eyebrow="RECORDED HISTORY" title="Performance" action={<Link to="/app/portfolio/performance">View performance →</Link>} />
      <div className="performance-summary-grid"><div><span>Period return</span><strong className={benchmark?.portfolioReturn >= 0 ? "is-positive" : "is-negative"}>{formatPercent(benchmark?.portfolioReturn, { signed: true })}</strong></div><div><span>Benchmark</span><strong>{formatPercent(benchmark?.benchmarkReturn, { signed: true })}</strong></div><div><span>Difference</span><strong className={benchmark?.difference >= 0 ? "is-positive" : "is-negative"}>{formatPercent(benchmark?.difference, { signed: true })}</strong></div><div><span>Realised P&L</span><strong className={performance.realizedPnl >= 0 ? "is-positive" : "is-negative"}>{formatCurrency(performance.realizedPnl, currency)}</strong></div><div><span>Unrealised P&L</span><strong className={performance.unrealizedPnl >= 0 ? "is-positive" : "is-negative"}>{formatCurrency(performance.unrealizedPnl, currency)}</strong></div></div>
      <PerformanceVisual performance={performance} currency={currency} />
    </article>
  );
}

function PerformanceVisual({ performance, currency }) {
  if (!performance.chartAvailable) return <div className="performance-history-note"><span>Recorded history</span><strong>{performance.points.length} valuation dates</strong><p>A chart needs at least three recorded points. No time series has been inferred.</p></div>;
  const values = performance.points.map((point) => point.equity + point.cash);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${42 - ((value - minimum) / range) * 36}`).join(" ");
  return <div className="performance-chart"><svg aria-label={`Portfolio value from ${formatCurrency(values[0], currency)} to ${formatCurrency(values.at(-1), currency)}`} preserveAspectRatio="none" role="img" viewBox="0 0 100 46"><polyline fill="none" points={points} stroke="currentColor" strokeWidth="2" /></svg><span>{formatDate(performance.points[0].date)}</span><span>{formatDate(performance.points.at(-1).date)}</span></div>;
}

export function ActivityList({ items, currency, limit }) {
  const visible = typeof limit === "number" ? items.slice(0, limit) : items;
  if (!visible.length) return <div className="portfolio-list-empty">No portfolio activity is recorded.</div>;
  return <ol className="portfolio-activity-list">{visible.map((item) => <li key={item.id}><time dateTime={item.occurredAt}>{formatDate(item.occurredAt)}</time><span className="activity-type">{statusLabel(item.type)}</span><div><strong>{item.security ?? item.description ?? "Portfolio record"}</strong><small>{item.quantity !== null ? `${formatNumber(item.quantity, 4)} units` : item.description ?? "Recorded by Portfolio OS"}</small></div><span className="numeric">{item.amount !== null ? formatCurrency(item.amount, item.currency ?? currency) : "—"}</span><code>{item.reference}</code></li>)}</ol>;
}

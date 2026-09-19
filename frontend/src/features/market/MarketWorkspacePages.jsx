import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MarketWorkspaceHeader, MarketWorkspaceLayout } from "./components/MarketWorkspaceLayout.jsx";
import { marketStreamUrl, marketWorkspaceApi } from "./data/marketWorkspaceApi.js";

const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const ranges = ["1D", "5D", "1M", "3M", "6M", "1Y"];

const number = (value) => value === null || value === undefined ? null : Number(value);
const formatNumber = (value) => Number.isFinite(number(value)) ? decimal.format(number(value)) : "Unavailable";
const formatWhole = (value) => Number.isFinite(number(value)) ? whole.format(number(value)) : "Unavailable";
const formatPercent = (value) => Number.isFinite(number(value)) ? `${number(value) >= 0 ? "+" : ""}${number(value).toFixed(2)}%` : "Unavailable";
const tone = (value) => number(value) > 0 ? "positive" : number(value) < 0 ? "negative" : "neutral";

function useMarketResource(loader, dependencies = []) {
  const [reload, setReload] = useState(0);
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    loader({ signal: controller.signal })
      .then((data) => { if (current) setState({ status: "ready", data, error: null }); })
      .catch((error) => { if (current && error?.code !== "MARKET_WORKSPACE_CANCELLED") setState({ status: "error", data: null, error }); });
    return () => { current = false; controller.abort(); };
  }, [loader, reload, ...dependencies]);
  return { ...state, retry: () => setReload((value) => value + 1) };
}

async function loadCandlesSafely(symbol, range, options) {
  try {
    return await marketWorkspaceApi.getCandles(symbol, range, options);
  } catch (error) {
    if (error?.code === "MARKET_WORKSPACE_CANCELLED") throw error;
    return { status: "UNAVAILABLE", range, candles: [] };
  }
}

function WorkspaceLoading({ label = "Market workspace" }) {
  return <MarketWorkspaceLayout connectionState="CONNECTING"><section aria-label={`Loading ${label}`} className="market-workspace-state" role="status"><span className="technical-label">LOADING</span><h1>{label}</h1><div className="market-workspace-skeleton" /><div className="market-workspace-skeleton is-short" /></section></MarketWorkspaceLayout>;
}

function WorkspaceError({ onRetry }) {
  return <MarketWorkspaceLayout connectionState="DISCONNECTED"><section className="market-workspace-state" role="alert"><span className="technical-label">PARTIAL MARKET SERVICE</span><h1>This market surface is unavailable.</h1><p>Other Market pages remain accessible. No substitute values have been invented.</p><button className="button button--primary" onClick={onRetry} type="button">Retry</button></section></MarketWorkspaceLayout>;
}

function StatusTag({ children, tone: tagTone = "neutral" }) {
  return <span className="market-status-tag" data-tone={tagTone}>{children}</span>;
}

export function applyMarketTick(quote, payload) {
  if (!quote || payload?.event !== "INSTRUMENT_UPDATE") return quote;
  const current = quote.instrument?.symbol?.toUpperCase();
  if (![payload.symbol, payload.instrument_id].filter(Boolean).map((value) => value.toUpperCase()).includes(current)) return quote;
  return {
    ...quote,
    timestamp: payload.timestamp ?? quote.timestamp,
    ltp: payload.ltp ?? quote.ltp,
    change: payload.change ?? quote.change,
    change_pct: payload.change_pct ?? quote.change_pct,
    open: payload.open ?? quote.open,
    high: payload.high ?? quote.high,
    low: payload.low ?? quote.low,
    close: payload.close ?? quote.close,
    volume: payload.volume ?? quote.volume,
    bid: payload.bid ?? quote.bid,
    ask: payload.ask ?? quote.ask,
    source: payload.source ?? quote.source,
    freshness: payload.freshness ?? quote.freshness,
  };
}

function useInstrumentStream(symbol, enabled, onTick) {
  useEffect(() => {
    if (!enabled || !symbol || typeof WebSocket !== "function") return undefined;
    const socket = new WebSocket(marketStreamUrl());
    socket.addEventListener("open", () => socket.send(JSON.stringify({ action: "subscribe", instruments: [symbol] })));
    socket.addEventListener("message", (event) => {
      try { onTick(JSON.parse(event.data)); } catch { /* Ignore malformed external events. */ }
    });
    return () => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: "unsubscribe", instruments: [symbol] }));
      socket.close();
    };
  }, [enabled, onTick, symbol]);
}

function MarketChart({ candles = [], chartType, onChartTypeChange }) {
  const width = 900;
  const height = 290;
  const padding = 24;
  const values = candles.flatMap((item) => [number(item.high), number(item.low)]).filter(Number.isFinite);
  if (!candles.length || !values.length) return <div className="market-chart-empty">Historical candles are unavailable for this range.</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (index) => padding + index * ((width - padding * 2) / Math.max(candles.length - 1, 1));
  const y = (value) => height - padding - ((number(value) - min) / span) * (height - padding * 2);
  const path = candles.map((item, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(item.close).toFixed(2)}`).join(" ");
  const candleWidth = Math.max(2, Math.min(9, (width - padding * 2) / Math.max(candles.length, 1) * .55));
  return (
    <div className="market-chart-shell">
      <div className="market-chart-toolbar"><span>{candles.length} recorded candles</span><div aria-label="Chart type"><button aria-pressed={chartType === "line"} onClick={() => onChartTypeChange("line")} type="button">Line</button><button aria-pressed={chartType === "candlestick"} onClick={() => onChartTypeChange("candlestick")} type="button">Candlestick</button></div></div>
      <svg aria-label={`${chartType === "line" ? "Line" : "Candlestick"} chart from recorded OHLC data`} className="market-financial-chart" preserveAspectRatio="none" role="img" viewBox={`0 0 ${width} ${height}`}>
        {[0, 1, 2, 3, 4].map((row) => <line className="market-chart-grid" key={row} x1={padding} x2={width - padding} y1={padding + row * ((height - padding * 2) / 4)} y2={padding + row * ((height - padding * 2) / 4)} />)}
        {chartType === "line" ? <path className="market-chart-line" d={path} /> : candles.map((item, index) => {
          const openY = y(item.open);
          const closeY = y(item.close);
          const positive = number(item.close) >= number(item.open);
          return <g className={positive ? "is-up" : "is-down"} key={item.timestamp}><line className="market-candle-wick" x1={x(index)} x2={x(index)} y1={y(item.high)} y2={y(item.low)} /><rect className="market-candle-body" height={Math.max(1, Math.abs(closeY - openY))} width={candleWidth} x={x(index) - candleWidth / 2} y={Math.min(openY, closeY)} /></g>;
        })}
      </svg>
      <div className="market-chart-axis"><span>{new Date(candles[0].timestamp).toLocaleDateString("en-GB")}</span><strong>{formatNumber(candles.at(-1)?.close)}</strong><span>{new Date(candles.at(-1).timestamp).toLocaleDateString("en-GB")}</span></div>
    </div>
  );
}

function RangeControl({ range, onChange }) {
  return <div aria-label="Chart range" className="market-range-control">{ranges.map((value) => <button aria-pressed={range === value} key={value} onClick={() => onChange(value)} type="button">{value}</button>)}</div>;
}

export function MarketIndicesPage() {
  const loader = useCallback((options) => marketWorkspaceApi.getIndices(options), []);
  const state = useMarketResource(loader);
  if (state.status === "loading") return <WorkspaceLoading label="Indices" />;
  if (state.status === "error") return <WorkspaceError onRetry={state.retry} />;
  return (
    <MarketWorkspaceLayout>
      <MarketWorkspaceHeader description="Recorded or live provider-normalized index snapshots." title="Indices" />
      <section className="market-workspace-surface">
        <div className="market-section-heading"><div><span className="technical-label">SUPPORTED BY PROVIDER</span><h2>Index board</h2></div><StatusTag>{state.data.provider}</StatusTag></div>
        {state.data.items?.length ? <div className="market-table-wrap"><table><thead><tr><th>Index</th><th>LTP</th><th>Change</th><th>Change %</th><th>Open</th><th>High</th><th>Low</th><th>Status</th></tr></thead><tbody>{state.data.items.map((item) => <tr key={item.symbol}><th><Link to={`/app/market/indices/${item.symbol}`}>{item.name}<small>{item.symbol}</small></Link></th><td>{formatNumber(item.value)}</td><td data-tone={tone(item.change)}>{formatNumber(item.change)}</td><td data-tone={tone(item.change_pct)}>{formatPercent(item.change_pct)}</td><td>{formatNumber(item.open)}</td><td>{formatNumber(item.high)}</td><td>{formatNumber(item.low)}</td><td><StatusTag>{item.status}</StatusTag></td></tr>)}</tbody></table></div> : <div className="market-empty-copy">Index data is unavailable from the selected provider.</div>}
      </section>
    </MarketWorkspaceLayout>
  );
}

export function MarketIndexDetailPage() {
  const { symbol = "" } = useParams();
  const [range, setRange] = useState("1M");
  const [chartType, setChartType] = useState("line");
  const loader = useCallback((options) => Promise.all([marketWorkspaceApi.getIndex(symbol, options), loadCandlesSafely(symbol, range, options)]), [range, symbol]);
  const state = useMarketResource(loader, [range, symbol]);
  if (state.status === "loading") return <WorkspaceLoading label="Index detail" />;
  if (state.status === "error") return <WorkspaceError onRetry={state.retry} />;
  const [detail, candles] = state.data;
  return <MarketWorkspaceLayout><MarketWorkspaceHeader actions={<Link className="market-text-link" to="/app/market/indices">All indices</Link>} description="Quote, recorded history, breadth and coverage where supported." title={detail.item?.name ?? symbol} />
    <section className="market-detail-metrics">{[["LTP", detail.item?.value], ["Change", detail.item?.change], ["Change %", detail.item?.change_pct, true], ["Previous close", detail.item?.previous_close]].map(([label, value, percent]) => <div key={label}><span>{label}</span><strong data-tone={tone(value)}>{percent ? formatPercent(value) : formatNumber(value)}</strong></div>)}</section>
    <section className="market-workspace-surface market-chart-panel"><div className="market-section-heading"><div><span className="technical-label">RECORDED OHLC</span><h2>Historical chart</h2></div><RangeControl onChange={setRange} range={range} /></div><MarketChart candles={candles.candles} chartType={chartType} onChartTypeChange={setChartType} /><p className="market-source-note">{candles.status === "AVAILABLE" ? `${candles.source} · ${candles.interval} · Last recorded candle ${new Date(candles.last_recorded_candle_at).toLocaleString("en-GB")}` : "Historical candles unavailable."}</p></section>
    <section className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">PARTICIPATION</span><h2>Breadth & coverage</h2></div></div>{detail.breadth ? <div className="market-detail-metrics is-contained"><div><span>Advancers</span><strong>{detail.breadth.advancers}</strong></div><div><span>Decliners</span><strong>{detail.breadth.decliners}</strong></div><div><span>Unchanged</span><strong>{detail.breadth.unchanged}</strong></div><div><span>Coverage</span><strong>{detail.coverage.coverage_count}/{detail.coverage.expected_count}</strong></div></div> : <div className="market-empty-copy">Breadth is not derivable for this index.</div>}</section>
  </MarketWorkspaceLayout>;
}

export function MarketStocksPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState({ status: "idle", items: [] });
  useEffect(() => {
    if (query.trim().length < 2) { setResult({ status: "idle", items: [] }); return undefined; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setResult((current) => ({ ...current, status: "loading" }));
      marketWorkspaceApi.search(query, { signal: controller.signal })
        .then((payload) => setResult({ status: "ready", items: payload.items ?? [], refreshedAt: payload.instrument_master_refreshed_at }))
        .catch((error) => { if (error.code !== "MARKET_WORKSPACE_CANCELLED") setResult({ status: "error", items: [] }); });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);
  return <MarketWorkspaceLayout><MarketWorkspaceHeader description="Search-first access to the provider-normalized instrument master." title="Stocks" />
    <section className="market-stock-search market-workspace-surface"><label><span className="technical-label">INSTRUMENT SEARCH</span><input autoComplete="off" onChange={(event) => setQuery(event.target.value)} placeholder="Search RELIANCE, TCS, HDFCBANK…" type="search" value={query} /></label><p>Search by symbol, company, index or underlying. Results remain available while the market is closed.</p></section>
    <section aria-live="polite" className="market-search-results market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">INSTRUMENT MASTER</span><h2>{query.trim().length < 2 ? "Start with a symbol or company" : `${result.items.length} matches`}</h2></div>{result.refreshedAt ? <time dateTime={result.refreshedAt}>Cache {new Date(result.refreshedAt).toLocaleDateString("en-GB")}</time> : null}</div>{result.status === "loading" ? <div className="market-empty-copy">Searching instruments…</div> : result.items.length ? <div className="market-result-list">{result.items.map((item) => <Link key={item.instrument_id} to={item.instrument_type === "INDEX" ? `/app/market/indices/${item.symbol}` : `/app/market/instruments/${item.symbol}`}><span><strong>{item.display_name}</strong><small>{item.exchange} · {item.instrument_type} · {item.segment}</small></span><b>{item.symbol}</b></Link>)}</div> : <div className="market-empty-copy">{result.status === "error" ? "Instrument search is temporarily unavailable." : query.trim().length >= 2 ? "No matching instruments." : "Try RELIANCE, TCS, HDFCBANK, NIFTY or BANKNIFTY."}</div>}</section>
  </MarketWorkspaceLayout>;
}

function QuoteFacts({ quote }) {
  const facts = [["LTP", quote.ltp], ["Open", quote.open], ["High", quote.high], ["Low", quote.low], ["Previous close", quote.previous_close], ["Volume", quote.volume, "whole"], ["Bid", quote.bid], ["Ask", quote.ask]];
  return <div className="market-quote-facts">{facts.map(([label, value, kind]) => <div key={label}><span>{label}</span><strong>{kind === "whole" ? formatWhole(value) : formatNumber(value)}</strong></div>)}</div>;
}

function DepthPanel({ quote, supported }) {
  const count = Math.max(quote.buy_depth?.length ?? 0, quote.sell_depth?.length ?? 0);
  if (!supported || !count) return <div className="market-empty-copy">Market depth unavailable.</div>;
  return <div className="market-depth"><div className="market-depth__head"><span>Bid price</span><span>Bid quantity</span><span>Ask price</span><span>Ask quantity</span></div>{Array.from({ length: count }, (_, index) => { const bid = quote.buy_depth?.[index]; const ask = quote.sell_depth?.[index]; return <div className="market-depth__row" key={index}><span className="is-positive">{formatNumber(bid?.price)}</span><span>{formatWhole(bid?.quantity)}</span><span className="is-negative">{formatNumber(ask?.price)}</span><span>{formatWhole(ask?.quantity)}</span></div>; })}</div>;
}

export function MarketInstrumentPage() {
  const { symbol = "" } = useParams();
  const [activeTab, setActiveTab] = useState("Overview");
  const [range, setRange] = useState("1M");
  const [chartType, setChartType] = useState("line");
  const [portfolio, setPortfolio] = useState(undefined);
  const loader = useCallback((options) => Promise.all([marketWorkspaceApi.getQuote(symbol, options), loadCandlesSafely(symbol, range, options)]), [range, symbol]);
  const state = useMarketResource(loader, [range, symbol]);
  const [liveQuote, setLiveQuote] = useState(null);
  useEffect(() => { setLiveQuote(state.data?.[0]?.quote ?? null); }, [state.data]);
  const onTick = useCallback((event) => setLiveQuote((quote) => applyMarketTick(quote, event)), []);
  useInstrumentStream(symbol, state.data?.[0]?.provider_mode === "LIVE", onTick);
  useEffect(() => {
    if (activeTab !== "Portfolio") return undefined;
    const controller = new AbortController();
    marketWorkspaceApi.getPortfolioContext(symbol, { signal: controller.signal }).then(setPortfolio).catch(() => setPortfolio(null));
    return () => controller.abort();
  }, [activeTab, symbol]);
  if (state.status === "loading") return <WorkspaceLoading label="Instrument detail" />;
  if (state.status === "error") return <WorkspaceError onRetry={state.retry} />;
  const [quoteResponse, candles] = state.data;
  const quote = liveQuote;
  if (!quote) return <MarketWorkspaceLayout><MarketWorkspaceHeader description="The selected provider has no quote for this instrument." title={symbol} /><section className="market-workspace-state"><h2>Instrument quote unavailable.</h2><p>Instrument search and other Market pages remain accessible.</p><Link className="market-text-link" to="/app/market/stocks">Back to Stocks</Link></section></MarketWorkspaceLayout>;
  const capabilities = quoteResponse.capabilities ?? [];
  return <MarketWorkspaceLayout><header className="market-instrument-header"><div><span className="technical-label">{quote.instrument.exchange} · {quote.instrument.segment} · READ-ONLY</span><h1>{quote.instrument.display_name}</h1><p>{quote.instrument.symbol} · {quote.instrument.instrument_type}</p></div><div className="market-instrument-price"><strong>{formatNumber(quote.ltp)}</strong><span data-tone={tone(quote.change_pct)}>{formatNumber(quote.change)} · {formatPercent(quote.change_pct)}</span><small>{quote.market_session === "CLOSED" ? "Market closed" : quote.market_session} · {quote.freshness} · {quote.source}</small></div></header>
    <nav aria-label="Instrument sections" className="market-detail-tabs">{["Overview", "Chart", "Depth", "Research", "Portfolio"].map((tab) => <button aria-selected={activeTab === tab} key={tab} onClick={() => setActiveTab(tab)} role="tab" type="button">{tab}</button>)}</nav>
    {activeTab === "Overview" ? <section className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">NORMALIZED QUOTE</span><h2>Session overview</h2></div><StatusTag>{quote.market_session === "CLOSED" ? "Market closed" : quote.market_session}</StatusTag></div><QuoteFacts quote={quote} /><p className="market-source-note">Last known quote {new Date(quote.timestamp).toLocaleString("en-GB")}. No execution actions are available.</p></section> : null}
    {activeTab === "Chart" ? <section className="market-workspace-surface market-chart-panel"><div className="market-section-heading"><div><span className="technical-label">OHLC + VOLUME</span><h2>Historical chart</h2></div><RangeControl onChange={setRange} range={range} /></div><MarketChart candles={candles.candles} chartType={chartType} onChartTypeChange={setChartType} /><p className="market-source-note">{candles.status === "AVAILABLE" ? `${candles.interval} · Last recorded candle ${new Date(candles.last_recorded_candle_at).toLocaleString("en-GB")}` : "Historical candles unavailable; the current quote remains usable."}</p></section> : null}
    {activeTab === "Depth" ? <section className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">READ-ONLY ORDER BOOK</span><h2>Market depth</h2></div></div><DepthPanel quote={quote} supported={capabilities.includes("MARKET_DEPTH")} /></section> : null}
    {activeTab === "Research" ? <section className="market-workspace-surface market-context-panel"><span className="technical-label">RESEARCH CONTEXT</span><h2>No instrument-specific research linked.</h2><p>InterSignal does not infer a security relationship from family-level evidence.</p><Link className="market-text-link" to="/app/research">Open Research</Link></section> : null}
    {activeTab === "Portfolio" ? <section className="market-workspace-surface market-context-panel"><span className="technical-label">PORTFOLIO OS · READ-ONLY</span>{portfolio === undefined ? <h2>Checking current portfolio…</h2> : portfolio ? <><h2>Portfolio exposure</h2><div className="market-detail-metrics is-contained"><div><span>Quantity</span><strong>{formatNumber(portfolio.quantity)}</strong></div><div><span>Portfolio weight</span><strong>{formatPercent(number(portfolio.weight) * 100)}</strong></div><div><span>Unrealised P&amp;L</span><strong data-tone={tone(portfolio.unrealized_pnl)}>{formatNumber(portfolio.unrealized_pnl)}</strong></div></div></> : <><h2>Not currently held</h2><p>No matching Portfolio OS holding was found.</p></>}</section> : null}
  </MarketWorkspaceLayout>;
}

export function MarketSectorsPage() {
  const loader = useCallback((options) => marketWorkspaceApi.getSectors(options), []);
  const state = useMarketResource(loader);
  if (state.status === "loading") return <WorkspaceLoading label="Sectors" />;
  if (state.status === "error") return <WorkspaceError onRetry={state.retry} />;
  return <MarketWorkspaceLayout><MarketWorkspaceHeader description="Relative performance, participation, volume and coverage without recommendations." title="Sectors" /><section className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">PROVIDER-NORMALIZED</span><h2>Sector board</h2></div><StatusTag>{state.data.provider}</StatusTag></div>{state.data.items?.length ? <div className="market-table-wrap"><table><thead><tr><th>Sector</th><th>Index value</th><th>Change</th><th>Breadth</th><th>Relative volume</th><th>Coverage</th></tr></thead><tbody>{state.data.items.map((item) => <tr key={item.sector_id}><th><Link to={`/app/market/sectors/${item.sector_id}`}>{item.name}</Link></th><td>{formatNumber(item.index_value)}</td><td data-tone={tone(item.change_pct)}>{formatPercent(item.change_pct)}</td><td>{formatPercent(item.breadth_pct)}</td><td>{Number.isFinite(number(item.relative_volume)) ? `${number(item.relative_volume).toFixed(2)}×` : "Unavailable"}</td><td>{item.coverage_count}/{item.expected_count}</td></tr>)}</tbody></table></div> : <div className="market-empty-copy">Sector context is unavailable from this provider.</div>}</section></MarketWorkspaceLayout>;
}

export function MarketSectorDetailPage() {
  const { sectorId = "" } = useParams();
  const [range, setRange] = useState("3M");
  const [chartType, setChartType] = useState("line");
  const loader = useCallback((options) => Promise.all([marketWorkspaceApi.getSector(sectorId, options), loadCandlesSafely(sectorId, range, options)]), [range, sectorId]);
  const state = useMarketResource(loader, [range, sectorId]);
  if (state.status === "loading") return <WorkspaceLoading label="Sector detail" />;
  if (state.status === "error") return <WorkspaceError onRetry={state.retry} />;
  const [detail, candles] = state.data;
  const item = detail.item;
  return <MarketWorkspaceLayout><MarketWorkspaceHeader actions={<Link className="market-text-link" to="/app/market/sectors">All sectors</Link>} description="Recorded sector performance, participation and constituent context." title={item?.name ?? sectorId.replaceAll("_", " ")} />
    {item ? <section className="market-detail-metrics">{[["Index value", item.index_value], ["Change", item.change_pct, true], ["Breadth", item.breadth_pct, true], ["Relative volume", item.relative_volume]].map(([label, value, percent]) => <div key={label}><span>{label}</span><strong data-tone={label === "Change" ? tone(value) : "neutral"}>{percent ? formatPercent(value) : label === "Relative volume" && Number.isFinite(number(value)) ? `${number(value).toFixed(2)}×` : formatNumber(value)}</strong></div>)}</section> : null}
    <section className="market-workspace-surface market-chart-panel"><div className="market-section-heading"><div><span className="technical-label">SECTOR INDEX</span><h2>Historical chart</h2></div><RangeControl onChange={setRange} range={range} /></div><MarketChart candles={candles.candles} chartType={chartType} onChartTypeChange={setChartType} /></section>
    <section className="market-sector-detail-grid"><article className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">MAPPED MEMBERS</span><h2>Constituents</h2></div><span>{detail.constituents.length}</span></div><div className="market-result-list is-compact">{detail.constituents.slice(0, 24).map((instrument) => <Link key={instrument.instrument_id} to={`/app/market/instruments/${instrument.symbol}`}><span><strong>{instrument.display_name}</strong><small>{instrument.exchange} · {instrument.symbol}</small></span></Link>)}</div>{!detail.constituents.length ? <div className="market-empty-copy">No constituent mapping is available.</div> : null}</article><article className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">SESSION CONTEXT</span><h2>Leaders & laggards</h2></div></div><div className="market-leader-grid"><div><span>Leaders</span>{detail.leaders.map((row) => <Link key={row.instrument_id} to={`/app/market/instruments/${row.symbol}`}>{row.symbol}</Link>)}</div><div><span>Laggards</span>{detail.laggards.map((row) => <Link key={row.instrument_id} to={`/app/market/instruments/${row.symbol}`}>{row.symbol}</Link>)}</div></div>{!detail.leaders.length ? <div className="market-empty-copy">Leader/laggard ranking is unavailable.</div> : null}</article></section>
  </MarketWorkspaceLayout>;
}

export function MarketDerivativesPage() {
  return <MarketWorkspaceLayout><MarketWorkspaceHeader description="A future read-only surface for expiries, contracts and option-chain context." eyebrow="FUTURE CAPABILITY" title="Derivatives" /><section className="market-workspace-state"><StatusTag>Not yet enabled</StatusTag><h2>Provider boundary ready; workspace pending.</h2><p>Expiries, contracts and option-chain APIs are normalized behind the backend. No derivatives execution or order entry is available.</p></section></MarketWorkspaceLayout>;
}

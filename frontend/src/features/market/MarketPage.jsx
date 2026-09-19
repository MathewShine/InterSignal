import { useCallback, useMemo, useState } from "react";
import { useOperationalResource } from "../operations/OperationalLayout.jsx";
import { MarketWorkspaceLayout } from "./components/MarketWorkspaceLayout.jsx";
import { MarketSessionOverviewCard } from "./MarketSessionPage.jsx";
import { marketDataService } from "./data/apiMarketAdapter.js";
import {
  breadthSummary,
  selectPrimaryIndex,
  selectReferenceIndex,
  selectSectorLaggards,
  selectSectorLeaders,
  sortSectors,
} from "./data/marketSelectors.js";

const decimal = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

function formatDate(value) {
  if (!value) return "Unavailable";
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${date.getUTCDate()} ${months[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function formatPercent(value, digits = 2) {
  if (value === null || !Number.isFinite(value)) return "Unavailable";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatPlainPercent(value, digits = 1) {
  return value === null || !Number.isFinite(value) ? "Unavailable" : `${value.toFixed(digits)}%`;
}

function tone(value) {
  return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
}

function providerLabel(mode, sessionStatus) {
  if (mode === "SEEDED") return "Recorded market data";
  if (mode === "DELAYED") return "Delayed market data";
  if (mode === "LIVE") return sessionStatus === "OPEN" ? "Live market data" : "Groww market data";
  return "Market source unavailable";
}

function providerModeLabel(mode) {
  return mode ? mode.toLowerCase().replace(/^./, (letter) => letter.toUpperCase()) : "Unavailable";
}

function freshnessLabel(status) {
  return status === "STALE" ? "Historical snapshot" : status === "FRESH" ? "Fresh snapshot" : status === "AGING" ? "Aging snapshot" : "Freshness unavailable";
}

function MarketLayout({ children, connectionState = "CONNECTED" }) {
  return <MarketWorkspaceLayout connectionState={connectionState}>{children}</MarketWorkspaceLayout>;
}

function MarketLoading() {
  return (
    <MarketLayout connectionState="CONNECTING">
      <div aria-label="Loading Market" className="market-loading" role="status">
        <div className="market-skeleton market-skeleton--header" />
        <div className="market-skeleton market-skeleton--hero" />
        <div className="market-loading-grid">
          <div className="market-skeleton market-skeleton--panel" />
          <div className="market-skeleton market-skeleton--panel" />
          <div className="market-skeleton market-skeleton--panel" />
        </div>
        <span className="sr-only">Loading recorded market data…</span>
      </div>
    </MarketLayout>
  );
}

function MarketError({ error, onRetry }) {
  return (
    <MarketLayout connectionState="DISCONNECTED">
      <section className="market-state-panel" role="alert">
        <span className="technical-label">MARKET UNAVAILABLE</span>
        <h1>Market data is unavailable.</h1>
        <p>{error?.code === "MARKET_API_INCOMPATIBLE" ? "This Market Snapshot contract version is not supported." : "Research and Portfolio remain accessible. No sample market records have been substituted."}</p>
        <button className="button button--primary" onClick={onRetry} type="button">Retry</button>
      </section>
    </MarketLayout>
  );
}

function MarketUnavailable({ snapshot }) {
  return (
    <MarketLayout connectionState="DISCONNECTED">
      <header className="market-page-header">
        <div><span className="technical-label">INDIA · NSE</span><h1>Market Intelligence</h1><p>Read-only market structure and participation context.</p></div>
      </header>
      <section className="market-state-panel" role="status">
        <span className="technical-label">RECORDED SOURCE UNAVAILABLE</span>
        <h2>Market data is unavailable.</h2>
        <p>Research and Portfolio remain accessible. No sample market records have been substituted.</p>
        {snapshot.limitations[0] ? <small>{snapshot.limitations[0].summary}</small> : null}
      </section>
    </MarketLayout>
  );
}

function IndexChange({ index, compact = false }) {
  if (!index) return <p className="market-unavailable-copy">Index observation unavailable.</p>;
  return (
    <div className={compact ? "market-index-quote market-index-quote--compact" : "market-index-quote"}>
      <strong>{decimal.format(index.value)}</strong>
      <span data-tone={tone(index.changePercent)}>{index.change === null ? "Change unavailable" : `${index.change >= 0 ? "+" : ""}${decimal.format(index.change)} · ${formatPercent(index.changePercent)}`}</span>
    </div>
  );
}

function PrimaryIndexPanel({ index, universe }) {
  return (
    <section aria-labelledby="primary-index-title" className="market-primary-panel">
      <header>
        <div><span className="technical-label">PRIMARY MARKET CANVAS</span><h2 id="primary-index-title">{index?.name ?? "NIFTY 500"}</h2></div>
        <span className="market-chip">Recorded close</span>
      </header>
      <IndexChange index={index} />
      <div aria-label={index ? `${index.name} changed ${formatPercent(index.changePercent)} in the recorded session` : "Index change unavailable"} className="market-change-axis" role="img">
        <span className="market-change-axis__zero" />
        {index?.changePercent !== null && index?.changePercent !== undefined ? <i className={`market-change-axis__mark is-${tone(index.changePercent)}`} style={{ "--change-position": `${Math.max(4, Math.min(96, 50 + index.changePercent * 12))}%` }} /> : null}
      </div>
      <footer>
        <div><span>Previous close</span><strong>{index?.previousClose === null || index?.previousClose === undefined ? "Unavailable" : decimal.format(index.previousClose)}</strong></div>
        <div><span>Universe</span><strong>{universe ? `${whole.format(universe.memberCount)} members` : "Unavailable"}</strong></div>
        <div><span>Observation</span><strong>End of day</strong></div>
      </footer>
    </section>
  );
}

function ReferencePanel({ index, snapshot }) {
  const quality = snapshot.breadth?.quality ?? snapshot.volume?.quality;
  return (
    <aside className="market-reference-panel">
      <div>
        <span className="technical-label">REFERENCE INDEX</span>
        <h2>{index?.name ?? "NIFTY 50"}</h2>
        <IndexChange compact index={index} />
      </div>
      <dl>
        <div><dt>Source</dt><dd title={`Provider mode: ${providerModeLabel(snapshot.provider.mode)}`}>{providerLabel(snapshot.provider.mode, snapshot.session?.status)}</dd></div>
        <div><dt>Freshness</dt><dd>{freshnessLabel(snapshot.freshness.status)}</dd></div>
        <div><dt>Coverage</dt><dd>{quality?.coveragePercent === null || quality?.coveragePercent === undefined ? "Unavailable" : `${quality.coverageCount}/${quality.expectedCount} · ${quality.coveragePercent.toFixed(4)}%`}</dd></div>
        <div><dt>Missing</dt><dd>{quality ? whole.format(quality.missingCount) : "Unavailable"}</dd></div>
      </dl>
    </aside>
  );
}

function SectionUnavailable({ children }) {
  return <div className="market-section-unavailable" role="status">{children}</div>;
}

function BreadthPanel({ snapshot }) {
  const breadth = snapshot.breadth;
  if (!breadth || snapshot.availability.breadth?.status === "UNAVAILABLE") {
    return <section className="market-panel" id="breadth"><SectionTitle eyebrow="PARTICIPATION" title="Market breadth" /><SectionUnavailable>Breadth is unavailable for this snapshot.</SectionUnavailable></section>;
  }
  const total = breadth.advancers + breadth.decliners + breadth.unchanged;
  return (
    <section aria-labelledby="breadth-title" className="market-panel" id="breadth">
      <SectionTitle eyebrow="PARTICIPATION" title="Market breadth" titleId="breadth-title" />
      <p className="market-panel__summary">{breadthSummary(breadth)}</p>
      <div aria-label={`${breadth.advancers} advancers, ${breadth.decliners} decliners and ${breadth.unchanged} unchanged`} className="breadth-bar" role="img">
        <i className="is-positive" style={{ width: `${total ? breadth.advancers / total * 100 : 0}%` }} />
        <i className="is-neutral" style={{ width: `${total ? breadth.unchanged / total * 100 : 0}%` }} />
        <i className="is-negative" style={{ width: `${total ? breadth.decliners / total * 100 : 0}%` }} />
      </div>
      <div className="breadth-counts">
        <div><span>Advancers</span><strong className="is-positive">{whole.format(breadth.advancers)}</strong><small>{formatPlainPercent(breadth.positivePercent)}</small></div>
        <div><span>Decliners</span><strong className="is-negative">{whole.format(breadth.decliners)}</strong><small>{formatPlainPercent(breadth.negativePercent)}</small></div>
        <div><span>Unchanged</span><strong>{whole.format(breadth.unchanged)}</strong><small>{total ? formatPlainPercent(breadth.unchanged / total * 100) : "Unavailable"}</small></div>
      </div>
      <dl className="market-inline-facts">
        <div><dt>Above prior close</dt><dd>{formatPlainPercent(breadth.abovePriorClosePercent, 4)}</dd></div>
        <div><dt>Above VWAP</dt><dd>{breadth.aboveVwapPercent === null ? "Unavailable" : formatPlainPercent(breadth.aboveVwapPercent, 4)}</dd></div>
      </dl>
    </section>
  );
}

function SectorPulse({ snapshot }) {
  if (!snapshot.sectors.length || snapshot.availability.sectors?.status === "UNAVAILABLE") {
    return <section className="market-panel"><SectionTitle eyebrow="RECORDED RELATIVE PERFORMANCE" title="Sector leadership" /><SectionUnavailable>Sector context is unavailable for this snapshot.</SectionUnavailable></section>;
  }
  const leaders = selectSectorLeaders(snapshot);
  const laggards = selectSectorLaggards(snapshot);
  return (
    <section aria-labelledby="sector-pulse-title" className="market-panel market-sector-pulse">
      <SectionTitle eyebrow="RECORDED RELATIVE PERFORMANCE" title="Sector leadership" titleId="sector-pulse-title" trailing={`${snapshot.sectors.length} sectors`} />
      <div className="sector-pulse-columns">
        <div><span>Leading</span>{leaders.map((sector) => <SectorPulseRow key={sector.name} sector={sector} />)}</div>
        <div><span>Lagging</span>{laggards.map((sector) => <SectorPulseRow key={sector.name} sector={sector} />)}</div>
      </div>
      <p className="market-context-note">Recorded one-session performance relative to NIFTY 500; this is descriptive context, not a strategy output.</p>
    </section>
  );
}

function SectorPulseRow({ sector }) {
  return <div className="sector-pulse-row"><strong>{sector.name}</strong><span data-tone={tone(sector.returnPercent)}>{formatPercent(sector.returnPercent)}</span></div>;
}

function VolumePanel({ snapshot }) {
  const volume = snapshot.volume;
  if (!volume || snapshot.availability.volume?.status === "UNAVAILABLE") {
    return <section className="market-panel" id="volume"><SectionTitle eyebrow="RECORDED SESSION" title="Volume context" /><SectionUnavailable>Volume context is unavailable for this snapshot.</SectionUnavailable></section>;
  }
  return (
    <section aria-labelledby="volume-title" className="market-panel" id="volume">
      <SectionTitle eyebrow="RECORDED SESSION" title="Volume context" titleId="volume-title" />
      <div className="volume-primary"><strong>{decimal.format(volume.aggregateTradedValue)}</strong><span>{volume.tradedValueUnit.replace("_", " ").toLowerCase()}</span></div>
      <div className="volume-baseline">
        <div><span>Median relative volume</span><strong>{volume.medianRelativeVolume === null ? "Unavailable" : `${volume.medianRelativeVolume.toFixed(4)}×`}</strong></div>
        <div aria-label={`${formatPlainPercent(volume.aboveBaselinePercent, 4)} of covered members above their 20-session baseline`} className="volume-baseline__bar" role="img"><i style={{ width: `${Math.max(0, Math.min(100, volume.aboveBaselinePercent ?? 0))}%` }} /></div>
        <p><strong>{whole.format(volume.aboveBaselineCount)}</strong> members above 20-session baseline · {formatPlainPercent(volume.aboveBaselinePercent, 4)}</p>
      </div>
    </section>
  );
}

function SectionTitle({ eyebrow, title, titleId, trailing }) {
  return <header className="market-section-title"><div><span className="technical-label">{eyebrow}</span><h2 id={titleId}>{title}</h2></div>{trailing ? <span>{trailing}</span> : null}</header>;
}

function SectorTable({ snapshot }) {
  const [sortKey, setSortKey] = useState("performance");
  const sectors = useMemo(() => sortSectors(snapshot.sectors, sortKey), [snapshot.sectors, sortKey]);
  if (!sectors.length || snapshot.availability.sectors?.status === "UNAVAILABLE") return null;
  const maxMove = Math.max(...sectors.map((sector) => Math.abs(sector.returnPercent ?? 0)), 1);
  return (
    <section aria-labelledby="sectors-title" className="market-sector-section" id="sectors">
      <header className="market-sector-section__header">
        <div><span className="technical-label">ALL RECORDED SECTORS</span><h2 id="sectors-title">Sector context</h2><p>Official sector-index return, relative strength and available member participation.</p></div>
        <label>Sort sectors<select aria-label="Sort sectors" onChange={(event) => setSortKey(event.target.value)} value={sortKey}><option value="performance">Performance</option><option value="breadth">Breadth</option><option value="name">Name</option></select></label>
      </header>
      <div className="market-sector-table-wrap">
        <table aria-label="Sector performance">
          <thead><tr><th scope="col">Sector</th><th scope="col">Recorded return</th><th scope="col">Relative strength</th><th scope="col">Breadth</th><th scope="col">Volume context</th><th scope="col">Coverage</th></tr></thead>
          <tbody>{sectors.map((sector) => (
            <tr key={sector.name}>
              <th scope="row">{sector.name}</th>
              <td><div className="sector-return"><span data-tone={tone(sector.returnPercent)}>{formatPercent(sector.returnPercent)}</span><i aria-hidden="true" className={`is-${tone(sector.returnPercent)}`} style={{ "--sector-size": `${Math.abs(sector.returnPercent ?? 0) / maxMove * 48}%` }} /></div></td>
              <td>{formatPercent(sector.relativeStrength)}</td>
              <td>{sector.breadthPercent === null ? "Unavailable" : `${formatPlainPercent(sector.breadthPercent)} · ${sector.advancers}/${sector.decliners}/${sector.unchanged}`}</td>
              <td>{sector.volumeContext === null ? "Unavailable" : `${sector.volumeContext.toFixed(4)}×`}</td>
              <td>{sector.quality.coveragePercent === null ? "Not mapped" : `${sector.quality.coverageCount}/${sector.quality.expectedCount}`}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

function QualityAndLimitations({ snapshot }) {
  const quality = snapshot.breadth?.quality ?? snapshot.volume?.quality;
  return (
    <section aria-labelledby="quality-title" className="market-quality-section" id="quality">
      <div className="market-quality-summary">
        <SectionTitle eyebrow="SNAPSHOT QUALITY" title="Coverage & freshness" titleId="quality-title" />
        <dl>
          <div><dt>Source</dt><dd>{snapshot.provider.mode === "SEEDED" ? "Recorded NSE data" : providerLabel(snapshot.provider.mode, snapshot.session?.status)}</dd></div>
          <div><dt>Mode</dt><dd>{snapshot.provider.mode === "SEEDED" ? "Recorded / Seeded" : providerModeLabel(snapshot.provider.mode)}</dd></div>
          <div><dt>Session</dt><dd>{snapshot.session?.status === "CLOSED" ? "Closed" : snapshot.session?.status ?? "Unavailable"}</dd></div>
          <div><dt>Freshness</dt><dd>{freshnessLabel(snapshot.freshness.status)}</dd></div>
          <div><dt>Overall availability</dt><dd>{snapshot.status === "PARTIAL" ? "Partial" : snapshot.status === "AVAILABLE" ? "Available" : "Unavailable"}</dd></div>
          <div><dt>Covered members</dt><dd>{quality ? `${quality.coverageCount} of ${quality.expectedCount}` : "Unavailable"}</dd></div>
          <div><dt>Coverage rate</dt><dd>{quality?.coveragePercent === null || quality?.coveragePercent === undefined ? "Unavailable" : `${quality.coveragePercent.toFixed(4)}%`}</dd></div>
          <div><dt>Recorded on</dt><dd>{formatDate(snapshot.session?.marketDate ?? snapshot.freshness.sourceTimestamp)}</dd></div>
          <div><dt>Membership</dt><dd>{snapshot.meta.currentMembershipOnly ? "Current effective only" : "Unavailable"}</dd></div>
          <div><dt>Broker connection</dt><dd>{snapshot.meta.brokerIntegration === "NOT_CONNECTED" ? "Not connected" : snapshot.meta.brokerIntegration}</dd></div>
        </dl>
      </div>
      <div className="market-limitations">
        <SectionTitle eyebrow="KNOWN LIMITATIONS" title="What this snapshot cannot establish" trailing={`${snapshot.limitations.length} recorded`} />
        <ul>{snapshot.limitations.map((item) => <li key={item.id}><span>{item.section}</span><p>{item.summary}</p></li>)}</ul>
      </div>
    </section>
  );
}

export function MarketPage({ dataService = marketDataService }) {
  const load = useCallback(({ signal }) => dataService.getSnapshot({ signal }), [dataService]);
  const resource = useOperationalResource(load, "MARKET_API_CANCELLED");
  if (resource.status === "loading") return <MarketLoading />;
  if (resource.status === "error") return <MarketError error={resource.error} onRetry={resource.retry} />;
  const snapshot = resource.data;
  if (snapshot.status === "UNAVAILABLE" || snapshot.provider.mode === "UNAVAILABLE") return <MarketUnavailable snapshot={snapshot} />;
  const primaryIndex = selectPrimaryIndex(snapshot);
  const referenceIndex = selectReferenceIndex(snapshot);
  const connectionState = snapshot.status === "PARTIAL" ? "PARTIAL" : "CONNECTED";
  return (
    <MarketLayout connectionState={connectionState}>
      <header className="market-page-header">
        <div><span className="technical-label">INDIA · NSE · READ-ONLY</span><h1>Market Intelligence</h1><p>Breadth, sector leadership and participation across the recorded NSE session.</p></div>
        <div className="market-page-meta"><span title={`Provider mode: ${providerModeLabel(snapshot.provider.mode)}`}>{providerLabel(snapshot.provider.mode, snapshot.session?.status)}</span><strong>{snapshot.session?.status === "CLOSED" ? "Closed" : snapshot.session?.status ?? "Session unavailable"}</strong><time dateTime={snapshot.session?.marketDate}>Recorded {formatDate(snapshot.session?.marketDate)}</time></div>
      </header>
      <MarketSessionOverviewCard />
      <div className="market-overview-grid">
        <PrimaryIndexPanel index={primaryIndex} universe={snapshot.universe} />
        <ReferencePanel index={referenceIndex} snapshot={snapshot} />
      </div>
      <div className="market-context-grid">
        <BreadthPanel snapshot={snapshot} />
        <SectorPulse snapshot={snapshot} />
        <VolumePanel snapshot={snapshot} />
      </div>
      <SectorTable snapshot={snapshot} />
      <QualityAndLimitations snapshot={snapshot} />
    </MarketLayout>
  );
}

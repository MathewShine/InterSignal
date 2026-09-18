import { useCallback } from "react";
import { Link } from "react-router-dom";
import { dataHealthService } from "./data/apiDataAdapter.js";
import { displayStatus } from "./data/dataNormalizers.js";
import {
  OperationalError,
  OperationalLayout,
  OperationalLoading,
  OperationalPageHeader,
  PartialNotice,
  StatusBadge,
  label,
  useOperationalResource,
} from "../operations/OperationalLayout.jsx";

export const dataNavigation = [["Overview", "/app/data"], ["Sources", "/app/data/sources"], ["Lineage", "/app/data/lineage"], ["Limitations", "/app/data/limitations"]];
export const dataSearchItems = [
  { id: "data-sources", group: "Data", label: "Data sources", path: "/app/data/sources" },
  { id: "data-lineage", group: "Data", label: "Lineage", path: "/app/data/lineage" },
  { id: "data-limitations", group: "Data", label: "Data limitations", path: "/app/data/limitations" },
];

function DataPage({ children, dataService, description, eyebrow, loaderName, title }) {
  const loader = useCallback((options) => dataService[loaderName](options), [dataService, loaderName]);
  const state = useOperationalResource(loader, "DATA_API_CANCELLED");
  if (state.status === "loading") return <OperationalLoading area="Data" navigation={dataNavigation} searchItems={dataSearchItems} />;
  if (state.status === "error") return <OperationalError area="Data" error={state.error} navigation={dataNavigation} onRetry={state.retry} searchItems={dataSearchItems} />;
  return <OperationalLayout area="Data" connectionState={state.data.status === "PARTIAL" ? "PARTIAL" : "CONNECTED"} navigation={dataNavigation} searchItems={dataSearchItems}><OperationalPageHeader description={description} eyebrow={eyebrow} generatedAt={state.data.generatedAt} title={title} /><PartialNotice sections={state.data.meta.unavailableSections} />{children(state.data)}</OperationalLayout>;
}

function SourceCard({ source }) {
  return <article className="ops-surface data-source-card"><header><div><span className="technical-label">{label(source.domain)}</span><h2>{source.name}</h2></div><StatusBadge value={source.status} /></header><p>{source.summary}</p>{source.coveragePercent !== null ? <div className="data-continuity"><strong>{source.coveragePercent.toFixed(3)}%</strong><span>exact prior-20 continuity</span><i><b style={{ width: `${source.coveragePercent}%` }} /></i></div> : null}<dl><div><dt>Research use</dt><dd>{displayStatus(source.researchUse)}</dd></div>{source.gapCount !== null && source.gapCount !== undefined ? <div><dt>Unresolved gaps</dt><dd>{source.gapCount}</dd></div> : null}<div><dt>Freshness</dt><dd>{displayStatus(source.freshness)}</dd></div></dl>{source.limitations.map((item) => <p className="ops-caveat" key={item}>{item}</p>)}</article>;
}

function LineageSummary({ lineage, compact = false }) {
  if (!lineage) return <div className="ops-empty"><h2>Lineage unavailable</h2><p>The rest of Data Health remains visible.</p></div>;
  return <article className="ops-surface lineage-summary"><header className="ops-section-heading"><div><span className="technical-label">PROVENANCE</span><h2>Lineage integrity</h2></div><StatusBadge value={lineage.integrityStatus} /></header><div className="ops-metric-strip"><div><span>Broken refs</span><strong>{lineage.brokenReferenceCount}</strong></div><div><span>Nodes</span><strong>{lineage.nodeCount}</strong></div><div><span>Edges</span><strong>{lineage.edgeCount}</strong></div><div><span>Artifacts</span><strong>{lineage.artifactCount}</strong></div></div>{!compact ? <><div className="stage-grid">{Object.entries(lineage.stageCounts).map(([stage, count]) => <div key={stage}><span>{label(stage)}</span><strong>{count}</strong></div>)}</div><LineageTable nodes={lineage.nodes} /></> : <Link className="ops-card-link" to="/app/data/lineage">Inspect lineage →</Link>}</article>;
}

function LineageTable({ nodes }) {
  if (!nodes.length) return <div className="ops-empty"><h2>No lineage nodes</h2><p>No provenance records are available.</p></div>;
  return <div className="ops-table-wrap"><table><caption className="sr-only">Recent lineage records</caption><thead><tr><th>Record</th><th>Stage</th><th>Source system</th><th>Links</th><th>Status</th></tr></thead><tbody>{nodes.map((node) => <tr key={node.id}><th scope="row"><strong>{node.label}</strong><span>{node.id}</span></th><td>{label(node.stage)}</td><td>{label(node.sourceSystem)}</td><td>{node.parentCount} in · {node.childCount} out</td><td><StatusBadge value={node.status} /></td></tr>)}</tbody></table></div>;
}

const affectedArea = (sourceId) => ({
  "intraday-continuity": "Family D research",
  "catalyst-history": "Family F research",
  "corporate-actions": "Adjusted-history consumers",
}[sourceId] ?? "Platform research");

function LimitationsList({ items, compact = false }) {
  if (!items.length) return <div className="ops-empty"><h2>No recorded limitations</h2><p>No limitations are present in the platform state.</p></div>;
  return <div className="limitation-list">{items.slice(0, compact ? 3 : undefined).map((item) => <article className="ops-surface limitation-card" key={item.id}><header><div><span className="technical-label">{label(item.severity)}</span><h2>{item.title}</h2></div><StatusBadge value={item.status} /></header><p>{item.summary}</p><dl><div><dt>Impact</dt><dd>{item.impact}</dd></div><div><dt>Affected research</dt><dd>{affectedArea(item.sourceId)}</dd></div><div><dt>Resolution</dt><dd>{item.resolution}</dd></div></dl><Link to={`/app/data/sources#${item.sourceId}`}>View source →</Link></article>)}</div>;
}

export function DataOverviewPage({ dataService = dataHealthService }) {
  return <DataPage dataService={dataService} description="Availability, research fitness and provenance across the platform’s recorded inputs." eyebrow="DATA HEALTH" loaderName="getOverview" title="Data">{(data) => <main className="data-overview"><section aria-label="Data sources" className="source-grid">{data.sources.map((source) => <SourceCard key={source.id} source={source} />)}</section><div className="data-lower-grid"><LineageSummary compact lineage={data.lineage} /><section><div className="ops-section-title"><div><span className="technical-label">KNOWN CONSTRAINTS</span><h2>Limitations</h2></div><Link to="/app/data/limitations">View all →</Link></div><LimitationsList compact items={data.limitations} /></section></div></main>}</DataPage>;
}
export function DataSourcesPage({ dataService = dataHealthService }) { return <DataPage dataService={dataService} description="Recorded availability and research-use status for each material input class." eyebrow="SOURCE REGISTER" loaderName="getSources" title="Data sources">{(data) => <section className="source-grid source-grid--page">{data.items.length ? data.items.map((source) => <div id={source.id} key={source.id}><SourceCard source={source} /></div>) : <div className="ops-empty"><h2>No data sources</h2><p>No source records are available.</p></div>}</section>}</DataPage>; }
export function DataLineagePage({ dataService = dataHealthService }) { return <DataPage dataService={dataService} description="A safe, read-only projection of platform provenance and reference integrity." eyebrow="PROVENANCE" loaderName="getLineage" title="Lineage">{(data) => <LineageSummary lineage={data.lineage} />}</DataPage>; }
export function DataLimitationsPage({ dataService = dataHealthService }) { return <DataPage dataService={dataService} description="Known constraints are surfaced without weakening or reinterpreting research gates." eyebrow="DISCLOSED CONSTRAINTS" loaderName="getLimitations" title="Data limitations">{(data) => <LimitationsList items={data.items} />}</DataPage>; }

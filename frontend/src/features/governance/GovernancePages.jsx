import { useCallback } from "react";
import { Link } from "react-router-dom";
import { governanceDataService } from "./data/apiGovernanceAdapter.js";
import {
  OperationalError,
  OperationalLayout,
  OperationalLoading,
  OperationalPageHeader,
  PartialNotice,
  StatusBadge,
  formatDate,
  label,
  useOperationalResource,
} from "../operations/OperationalLayout.jsx";

export const governanceNavigation = [["Overview", "/app/governance"], ["Readiness", "/app/governance/readiness"], ["Policies", "/app/governance/policies"], ["Authorizations", "/app/governance/authorizations"], ["Audit", "/app/governance/audit"]];
export const governanceSearchItems = [
  { id: "governance-readiness", group: "Governance", label: "Readiness", path: "/app/governance/readiness" },
  { id: "governance-policies", group: "Governance", label: "Policies", path: "/app/governance/policies" },
  { id: "governance-authorizations", group: "Governance", label: "Authorizations", path: "/app/governance/authorizations" },
  { id: "governance-audit", group: "Governance", label: "Audit", path: "/app/governance/audit" },
];

function GovernancePage({ children, dataService, description, eyebrow, loaderName, title }) {
  const loader = useCallback((options) => dataService[loaderName](options), [dataService, loaderName]);
  const state = useOperationalResource(loader, "GOVERNANCE_API_CANCELLED");
  if (state.status === "loading") return <OperationalLoading area="Governance" navigation={governanceNavigation} searchItems={governanceSearchItems} />;
  if (state.status === "error") return <OperationalError area="Governance" error={state.error} navigation={governanceNavigation} onRetry={state.retry} searchItems={governanceSearchItems} />;
  return <OperationalLayout area="Governance" connectionState={state.data.status === "PARTIAL" ? "PARTIAL" : "CONNECTED"} navigation={governanceNavigation} searchItems={governanceSearchItems}><OperationalPageHeader description={description} eyebrow={eyebrow} generatedAt={state.data.generatedAt} title={title} /><PartialNotice sections={state.data.meta.unavailableSections} />{children(state.data)}</OperationalLayout>;
}

function ReadinessGrid({ items }) {
  if (!items.length) return <div className="ops-empty"><h2>No readiness assessments</h2><p>No readiness records are available.</p></div>;
  return <div className="readiness-grid">{items.map((item) => <article className="ops-surface readiness-card" key={item.id}><header><span className="technical-label">{item.label}</span><StatusBadge value={item.status} /></header><strong>{item.passedCriteria}/{item.totalCriteria}</strong><p>required conditions currently satisfied</p>{item.connectionState ? <span className="readiness-connection">Connection: {label(item.connectionState)}</span> : null}<h3>Blocking conditions</h3>{item.failedCriteria.length ? <ul>{item.failedCriteria.map((criterion) => <li key={criterion}>{label(criterion)}</li>)}</ul> : <p className="readiness-clear">No blocking conditions recorded.</p>}<time dateTime={item.assessedAt}>Assessed {formatDate(item.assessedAt, true)}</time></article>)}</div>;
}
function PolicyList({ items }) {
  if (!items.length) return <div className="ops-empty"><h2>No governance policies</h2><p>No policy records are available.</p></div>;
  return <div className="policy-list">{items.map((item) => <article className="ops-surface policy-card" key={item.id}><header><div><span className="technical-label">{item.domain} · {item.severity}</span><h2>{item.name}</h2></div><StatusBadge value={item.status} /></header><p>{item.description}</p><footer><code>{item.id}</code><span>{item.passedChecks.length} checks passed</span></footer></article>)}</div>;
}
function AuthorizationList({ items }) {
  if (!items.length) return <div className="ops-empty"><h2>No authorization requests</h2><p>No authorization records are present.</p></div>;
  return <div className="authorization-list">{items.map((item) => <article className="ops-surface authorization-card" key={item.id}><header><div><span className="technical-label">{label(item.type)}</span><h2>{label(item.subjectId)}</h2></div><StatusBadge value={item.status} /></header><p>{item.reason}</p><dl><div><dt>Domain</dt><dd>{label(item.type)}</dd></div><div><dt>Scope</dt><dd>{label(item.subjectType)}</dd></div><div><dt>Requested</dt><dd>{formatDate(item.requestedAt, true)}</dd></div><div><dt>Requester</dt><dd>{label(item.requestedBy)}</dd></div></dl><h3>Conditions</h3><ul>{item.conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></article>)}</div>;
}
function AuditList({ items, compact = false }) {
  const rows = compact ? items.slice(0, 6) : items;
  if (!rows.length) return <div className="ops-empty"><h2>No audit events</h2><p>No audit history is recorded.</p></div>;
  return <ol className="audit-list">{rows.map((item) => <li className="ops-surface" key={`${item.source}-${item.id}`}><time dateTime={item.occurredAt}>{formatDate(item.occurredAt, true)}</time><StatusBadge value={item.result} /><div><strong>{label(item.eventType)}</strong><p>{item.reason}</p><small>{label(item.domain)} · {label(item.subjectId)}</small></div><code>{item.id}</code></li>)}</ol>;
}

export function GovernanceOverviewPage({ dataService = governanceDataService }) {
  return <GovernancePage dataService={dataService} description="Readiness, policy controls, authorizations and the immutable operational record." eyebrow="CONTROL PLANE" loaderName="getOverview" title="Governance">{(data) => <>{data.summary ? <section className="governance-summary ops-surface"><div><span>Paper</span><StatusBadge value={data.summary.paperReadiness} /></div><div><span>Live</span><StatusBadge value={data.summary.liveReadiness} /></div><div><span>Broker</span><StatusBadge value={data.summary.brokerReadiness} /><small>{label(data.summary.brokerConnectionState)}</small></div><div><span>Production</span><StatusBadge value={data.summary.productionReadiness} /></div><div><span>Blocking violations</span><strong>{data.summary.blockingViolationCount}</strong></div><div><span>Pending authorizations</span><strong>{data.summary.pendingAuthorizationCount}</strong></div></section> : null}<div className="governance-callout"><strong>{data.summary?.passingPolicyCount}/{data.summary?.totalPolicyCount} policy evaluations pass.</strong><span>Passing controls confirm current restrictions are being respected; they do not imply trading readiness.</span></div><ReadinessGrid items={data.readiness.filter((item) => ["PAPER_TRADING_READINESS", "LIVE_TRADING_READINESS", "BROKER_READINESS", "PRODUCTION_READINESS"].includes(item.type))} /><div className="governance-lower-grid"><section><div className="ops-section-title"><div><span className="technical-label">AUTHORIZATION QUEUE</span><h2>Pending decisions</h2></div><Link to="/app/governance/authorizations">View all →</Link></div><AuthorizationList items={data.authorizations.filter((item) => item.status === "REQUESTED")} /></section><section><div className="ops-section-title"><div><span className="technical-label">RECENT RECORD</span><h2>Audit trail</h2></div><Link to="/app/governance/audit">View audit →</Link></div><AuditList compact items={data.recentAudit} /></section></div></>}</GovernancePage>;
}
export function GovernanceReadinessPage({ dataService = governanceDataService }) { return <GovernancePage dataService={dataService} description="Recorded operational gates remain explicit and independent of policy compliance." eyebrow="READINESS GATES" loaderName="getReadiness" title="Readiness">{(data) => <ReadinessGrid items={data.items} />}</GovernancePage>; }
export function GovernancePoliciesPage({ dataService = governanceDataService }) { return <GovernancePage dataService={dataService} description="Declarative safeguards and their latest deterministic evaluations." eyebrow="POLICY REGISTER" loaderName="getPolicies" title="Policies">{(data) => <><div className="governance-callout"><strong>{data.passingCount}/{data.totalCount} evaluations pass.</strong><span>This records control compliance only; readiness is assessed separately.</span></div><PolicyList items={data.items} /></>}</GovernancePage>; }
export function GovernanceAuthorizationsPage({ dataService = governanceDataService }) { return <GovernancePage dataService={dataService} description="Requested and decided permissions. This surface cannot approve or mutate them." eyebrow="AUTHORIZATION REGISTER" loaderName="getAuthorizations" title="Authorizations">{(data) => <><div className="ops-count-line">{data.pendingCount} pending of {data.totalCount} recorded authorizations</div><AuthorizationList items={data.items} /></>}</GovernancePage>; }
export function GovernanceAuditPage({ dataService = governanceDataService }) { return <GovernancePage dataService={dataService} description="Real registry, Portfolio OS and governance events in reverse chronological order." eyebrow="AUDIT TRAIL" loaderName="getAudit" title="Audit">{(data) => <><section className="override-panel ops-surface"><span className="technical-label">MANUAL OVERRIDES</span><h2>{data.manualOverrides.length ? `${data.manualOverrides.length} recorded` : "No manual overrides recorded"}</h2><p>{data.manualOverrides.length ? "Approved overrides are included below." : "The empty state is sourced from the governance repository."}</p></section><AuditList items={data.items} /></>}</GovernancePage>; }

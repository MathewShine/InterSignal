import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { AuthenticatedShell } from "../../home/components/AuthenticatedShell.jsx";
import { statusLabel, statusTone } from "../data/researchNormalizers.js";

export const researchSearchItems = [
  { id: "research-overview", group: "Research", label: "Go to Research", path: "/app/research" },
  ..."ABCDEFG".split("").map((family) => ({
    id: `research-family-${family.toLowerCase()}`,
    group: "Research families",
    label: `Family ${family}`,
    path: `/app/research/families/${family}`,
  })),
  { id: "research-evidence", group: "Research", label: "Evidence", path: "/app/research/evidence" },
  { id: "research-validation", group: "Research", label: "Validation", path: "/app/research/validation" },
  { id: "research-blocked", group: "Research", label: "Blocked Research", path: "/app/research/blocked" },
  { id: "research-timeline", group: "Research", label: "Research timeline", path: "/app/research/timeline" },
];

const navigation = [
  ["Overview", "/app/research"],
  ["Families", "/app/research/families"],
  ["Evidence", "/app/research/evidence"],
  ["Validation", "/app/research/validation"],
  ["Blocked", "/app/research/blocked"],
  ["Timeline", "/app/research/timeline"],
];

export function ResearchLayout({ children, connectionState = "CONNECTED" }) {
  useEffect(() => {
    document.body.classList.add("app-route-active");
    return () => document.body.classList.remove("app-route-active");
  }, []);

  return (
    <AuthenticatedShell
      area="Research"
      connectionState={connectionState}
      marketMode="RESEARCH"
      searchItems={researchSearchItems}
    >
      <div className="research-workbench">
        <nav aria-label="Research sections" className="research-subnav">
          {navigation.map(([label, path]) => (
            <NavLink
              className={({ isActive }) => isActive ? "is-active" : undefined}
              end={path === "/app/research"}
              key={path}
              to={path}
            >
              {label}
            </NavLink>
          ))}
        </nav>
        {children}
      </div>
    </AuthenticatedShell>
  );
}

export function useResearchResource(loader, dependencies = []) {
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    loader({ signal: controller.signal })
      .then((data) => {
        if (current) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (current && error?.code !== "RESEARCH_API_CANCELLED") {
          setState({ status: "error", data: null, error });
        }
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [loader, reloadKey, ...dependencies]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);
  return { ...state, retry };
}

export function PageHeader({ eyebrow = "RESEARCH WORKBENCH", title, description, actions }) {
  return (
    <header className="research-page-header">
      <div>
        <span className="technical-label">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="research-page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function StatusPill({ children, value = "" }) {
  return <span className="research-status" data-tone={statusTone(`${value} ${children}`)}>{children}</span>;
}

export function ResearchLoading({ type = "table" }) {
  return (
    <ResearchLayout connectionState="CONNECTING">
      <div aria-label="Loading Research" className="research-loading" role="status">
        <div className="research-skeleton research-skeleton--title" />
        <div className="research-loading__metrics">
          {Array.from({ length: 5 }, (_, index) => <div className="research-skeleton research-skeleton--metric" key={index} />)}
        </div>
        <div className={`research-loading__${type}`}>
          {Array.from({ length: 7 }, (_, index) => <div className="research-skeleton research-skeleton--row" key={index} />)}
        </div>
        <span className="sr-only">Loading Research data…</span>
      </div>
    </ResearchLayout>
  );
}

export function ResearchError({ error, onRetry }) {
  return (
    <ResearchLayout connectionState="DISCONNECTED">
      <section className="research-error" role="alert">
        <span className="technical-label">RESEARCH UNAVAILABLE</span>
        <h1>Research data couldn’t be loaded.</h1>
        <p>{error?.code === "RESEARCH_API_INCOMPATIBLE" ? "This Research data version isn’t supported." : "The workbench remains read-only and no demo data has been substituted."}</p>
        <button className="button button--primary" onClick={onRetry} type="button">Retry</button>
      </section>
    </ResearchLayout>
  );
}

export function EmptyState({ title, message }) {
  return (
    <div className="research-empty">
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
}

export function PartialNotice({ unavailable = [] }) {
  if (!unavailable.length) return null;
  return (
    <div className="research-inline-notice" role="status">
      Some Research sections are temporarily unavailable: {unavailable.join(", ")}.
    </div>
  );
}

export function FamilyMatrix({ families, compact = false }) {
  if (!families.length) return <EmptyState title="No families match" message="Try clearing the current filters." />;
  return (
    <>
      <div className={`research-table-wrap family-matrix${compact ? " is-compact" : ""}`}>
        <table>
          <caption className="sr-only">Research families A through G</caption>
          <thead>
            <tr>
              <th scope="col">Family</th>
              <th scope="col">Hypothesis / setup</th>
              <th scope="col">Stage</th>
              <th scope="col">Current status</th>
              <th scope="col">Evidence</th>
              <th scope="col">Validation</th>
              <th scope="col">Blocker</th>
              <th scope="col">Last activity</th>
              <th scope="col"><span className="sr-only">Action</span></th>
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family.id}>
                <th scope="row"><Link className="family-code" to={family.actionPath}>{family.id}</Link></th>
                <td><strong>{family.name}</strong><span>{family.setup}</span></td>
                <td>{family.stage}</td>
                <td><StatusPill value={family.currentStatus}>{family.currentStatusLabel}</StatusPill><span>{family.decisionLabel}</span></td>
                <td>{family.evidenceState}</td>
                <td>{family.validationLabel}</td>
                <td>{family.blocker ?? "—"}</td>
                <td><time dateTime={family.latestActivityAt}>{formatDate(family.latestActivityAt)}</time></td>
                <td><Link aria-label={`Open Family ${family.id}`} className="research-row-action" to={family.actionPath}>Open</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="family-mobile-list">
        {families.map((family) => (
          <Link className="family-mobile-card" key={family.id} to={family.actionPath}>
            <span className="family-code">{family.id}</span>
            <span><strong>Family {family.id} · {family.name}</strong><small>{family.setup}</small></span>
            <span><StatusPill value={family.currentStatus}>{family.currentStatusLabel}</StatusPill><small>{family.evidenceState}</small></span>
            <b aria-hidden="true">→</b>
          </Link>
        ))}
      </div>
    </>
  );
}

export function FilterBar({ children, query, onQueryChange, placeholder = "Search Research" }) {
  return (
    <div className="research-filters">
      <label className="research-search">
        <span>Search</span>
        <input onChange={(event) => onQueryChange(event.target.value)} placeholder={placeholder} type="search" value={query} />
      </label>
      {children}
    </div>
  );
}

export function SelectFilter({ label, value, onChange, options }) {
  return (
    <label className="research-select">
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="">All</option>
        {options.map((option) => <option key={option} value={option}>{statusLabel(option)}</option>)}
      </select>
    </label>
  );
}

export function EvidenceTable({ items }) {
  if (!items.length) return <EmptyState title="No evidence found" message="No evidence records match the selected filters." />;
  return (
    <div className="research-table-wrap evidence-table">
      <table>
        <caption className="sr-only">Research evidence registry</caption>
        <thead><tr><th scope="col">Evidence ID</th><th scope="col">Family</th><th scope="col">Type</th><th scope="col">Summary</th><th scope="col">Status</th><th scope="col">Production relevance</th><th scope="col">Source</th><th scope="col">Updated</th></tr></thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <th scope="row"><Link to={item.actionPath}>{item.id}</Link></th>
              <td><Link to={`/app/research/families/${item.familyId}`}>{item.familyId}</Link></td>
              <td>{statusLabel(item.type)}</td>
              <td><strong>{item.title}</strong><span>{item.summary}</span></td>
              <td><StatusPill value={`${item.status} ${item.classification}`}>{statusLabel(item.status)}</StatusPill></td>
              <td>{item.productionRelevance}</td>
              <td>{item.source}</td>
              <td>{formatDate(item.updatedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TimelineList({ items, limit }) {
  const visible = typeof limit === "number" ? items.slice(0, limit) : items;
  if (!visible.length) return <EmptyState title="No activity" message="No Research events are available for this view." />;
  return (
    <ol className="research-timeline-list">
      {visible.map((item) => (
        <li key={item.id}>
          <time dateTime={item.occurredAt}>{formatDate(item.occurredAt)}</time>
          <span>{item.familyId ? `Family ${item.familyId}` : "Programme"}</span>
          <div><strong>{item.event}</strong><small>{item.category} · {item.result}</small></div>
          {item.relatedEvidence ? <Link to={`/app/research/evidence/${item.relatedEvidence}`}>Evidence</Link> : <span>{item.relatedArtifacts.length ? `${item.relatedArtifacts.length} artifact${item.relatedArtifacts.length === 1 ? "" : "s"}` : "Recorded"}</span>}
        </li>
      ))}
    </ol>
  );
}

export function LineageDisclosure({ lineage }) {
  return (
    <details className="lineage-disclosure">
      <summary>View lineage <span>{lineage.nodes.length} nodes · {lineage.integrity.toLowerCase()}</span></summary>
      {lineage.nodes.length ? (
        <div className="lineage-stages">
          {lineage.nodes.map((node) => (
            <div key={node.node_id}>
              <StatusPill value={node.stage}>{statusLabel(node.stage)}</StatusPill>
              <strong>{node.entity_type.replaceAll("_", " ")}</strong>
              <span>{node.source_system.replaceAll("_", " ")}</span>
              <code>{node.node_id}</code>
            </div>
          ))}
        </div>
      ) : <EmptyState title="No lineage nodes" message="This record has no linked lineage nodes." />}
    </details>
  );
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

export function useStableLoader(callback, dependencies = []) {
  return useMemo(() => callback, dependencies);
}

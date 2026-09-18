import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { AuthenticatedShell } from "../home/components/AuthenticatedShell.jsx";

export function OperationalLayout({ area, children, connectionState = "CONNECTED", navigation, searchItems }) {
  useEffect(() => {
    document.body.classList.add("app-route-active");
    return () => document.body.classList.remove("app-route-active");
  }, []);
  return (
    <AuthenticatedShell area={area} connectionState={connectionState} marketMode={area.toUpperCase()} searchItems={searchItems}>
      <div className="ops-workspace">
        <nav aria-label={`${area} sections`} className="ops-subnav">
          {navigation.map(([label, path]) => <NavLink className={({ isActive }) => isActive ? "is-active" : undefined} end={path === navigation[0][1]} key={path} to={path}>{label}</NavLink>)}
        </nav>
        {children}
      </div>
    </AuthenticatedShell>
  );
}

export function useOperationalResource(loader, cancellationCode) {
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    loader({ signal: controller.signal })
      .then((data) => { if (current) setState({ status: "ready", data, error: null }); })
      .catch((error) => { if (current && error?.code !== cancellationCode) setState({ status: "error", data: null, error }); });
    return () => { current = false; controller.abort(); };
  }, [loader, reloadKey, cancellationCode]);
  const retry = useCallback(() => setReloadKey((value) => value + 1), []);
  return { ...state, retry };
}

export function OperationalPageHeader({ eyebrow, title, description, generatedAt }) {
  return <header className="ops-page-header"><div><span className="technical-label">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div><div className="ops-page-meta"><span>Read-only</span>{generatedAt ? <time dateTime={generatedAt}>Updated {formatDate(generatedAt, true)}</time> : null}</div></header>;
}

export function OperationalLoading({ area, navigation, searchItems }) {
  return <OperationalLayout area={area} connectionState="CONNECTING" navigation={navigation} searchItems={searchItems}><div aria-label={`Loading ${area}`} className="ops-loading" role="status"><div className="ops-skeleton ops-skeleton--title" /><div className="ops-skeleton ops-skeleton--metrics" /><div className="ops-loading-grid"><div className="ops-skeleton ops-skeleton--panel" /><div className="ops-skeleton ops-skeleton--panel" /></div><span className="sr-only">Loading {area} data…</span></div></OperationalLayout>;
}

export function OperationalError({ area, error, navigation, onRetry, searchItems }) {
  return <OperationalLayout area={area} connectionState="DISCONNECTED" navigation={navigation} searchItems={searchItems}><section className="ops-error ops-surface" role="alert"><span className="technical-label">{area.toUpperCase()} UNAVAILABLE</span><h1>{area === "Data" ? "Data health couldn’t be loaded." : "Governance data couldn’t be loaded."}</h1><p>{error?.code?.endsWith("INCOMPATIBLE") ? `This ${area} contract version isn’t supported.` : "Available sections will return when the connection is restored. No demo records have been substituted."}</p><button className="button button--primary" onClick={onRetry} type="button">Retry</button></section></OperationalLayout>;
}

export function PartialNotice({ sections = [] }) {
  if (!sections.length) return null;
  return <div className="ops-partial-notice" role="status">Some sections are temporarily unavailable: {sections.join(", ")}.</div>;
}

export function StatusBadge({ value }) {
  const tone = ["AVAILABLE", "HEALTHY", "PASS", "READY"].includes(value) ? "good" : ["OPEN", "BLOCKING", "SOURCE_BLOCKED", "BLOCKED_FOR_RESEARCH_USE", "NOT_READY", "REQUESTED", "NOT_CONNECTED"].includes(value) ? "blocked" : "neutral";
  return <span className="ops-status" data-tone={tone}>{label(value)}</span>;
}

export const label = (value) => String(value ?? "Unavailable").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
export function formatDate(value, includeTime = false) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", includeTime ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" } : { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

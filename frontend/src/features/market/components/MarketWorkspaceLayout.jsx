import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { AuthenticatedShell } from "../../home/components/AuthenticatedShell.jsx";
import { marketWorkspaceApi } from "../data/marketWorkspaceApi.js";

export const marketSearchItems = [
  { id: "market-overview", group: "Market", label: "Market overview", path: "/app/market" },
  { id: "market-indices", group: "Market", label: "Indices", path: "/app/market/indices" },
  { id: "market-stocks", group: "Market", label: "Stocks", path: "/app/market/stocks" },
  { id: "market-sectors", group: "Market", label: "Sectors", path: "/app/market/sectors" },
  { id: "market-session", group: "Market", label: "Market session evidence", path: "/app/market/session" },
  { id: "market-breadth", group: "Market", label: "Market breadth", path: "/app/market#breadth" },
  { id: "sector-context", group: "Market", label: "Sector context", path: "/app/market#sectors" },
];

const navigation = [
  ["Overview", "/app/market"],
  ["Indices", "/app/market/indices"],
  ["Stocks", "/app/market/stocks"],
  ["Sectors", "/app/market/sectors"],
  ["Derivatives", "/app/market/derivatives"],
  ["Session", "/app/market/session"],
];

export function marketIndicator(status) {
  if (!status || status.mode === "UNAVAILABLE") return { label: "Market unavailable", mode: "UNAVAILABLE", connection: "DISCONNECTED" };
  if (status.mode === "SEEDED") return { label: "Recorded market data", mode: "RECORDED", connection: "CONNECTED" };
  const streamActive = status.stream_state === "CONNECTED";
  if (status.connected && streamActive && status.market_session === "OPEN") return { label: "Live", mode: "LIVE", connection: "CONNECTED" };
  if (status.configured && status.market_session === "CLOSED") return { label: "Market closed", mode: "CLOSED", connection: "CONNECTED" };
  return { label: status.configured ? "Provider ready" : "Market unavailable", mode: status.configured ? "READY" : "UNAVAILABLE", connection: status.configured ? "PARTIAL" : "DISCONNECTED" };
}

export function MarketWorkspaceLayout({ children, connectionState, providerStatus }) {
  const [resolvedStatus, setResolvedStatus] = useState(providerStatus ?? null);
  useEffect(() => {
    document.body.classList.add("app-route-active");
    const controller = new AbortController();
    if (!providerStatus) marketWorkspaceApi.getProviderStatus({ signal: controller.signal }).then(setResolvedStatus).catch(() => setResolvedStatus(null));
    return () => { document.body.classList.remove("app-route-active"); controller.abort(); };
  }, [providerStatus]);
  const indicator = marketIndicator(resolvedStatus);
  return (
    <AuthenticatedShell area="Market" connectionState={connectionState ?? indicator.connection} marketMode={indicator.mode} searchItems={marketSearchItems}>
      <div className="market-workspace">
        <div className="market-subnav-row">
          <nav aria-label="Market sections" className="market-subnav">
            {navigation.map(([label, path]) => (
              <NavLink className={({ isActive }) => isActive ? "is-active" : undefined} end={path === "/app/market"} key={path} to={path}>{label}</NavLink>
            ))}
          </nav>
          <span className="market-live-indicator" data-mode={indicator.mode}><i />{indicator.label}</span>
        </div>
        {children}
      </div>
    </AuthenticatedShell>
  );
}

export function MarketWorkspaceHeader({ eyebrow = "INDIA · NSE · READ-ONLY", title, description, actions }) {
  return <header className="market-workspace-header"><div><span className="technical-label">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{actions ? <div className="market-workspace-header__actions">{actions}</div> : null}</header>;
}

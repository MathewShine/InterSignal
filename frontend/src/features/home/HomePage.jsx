import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AttentionStream } from "./components/AttentionStream.jsx";
import { AuthenticatedShell } from "./components/AuthenticatedShell.jsx";
import { ContextDrawer } from "./components/ContextDrawer.jsx";
import { DataHealthPulse } from "./components/DataHealthPulse.jsx";
import { ExploreNext } from "./components/ExploreNext.jsx";
import { GovernancePulse } from "./components/GovernancePulse.jsx";
import { HomeConnectionNotice, HomeLoadingState } from "./components/HomeStates.jsx";
import { HomeGreeting } from "./components/HomeGreeting.jsx";
import { MarketContextCanvas } from "./components/MarketContextCanvas.jsx";
import { PortfolioContextStrip } from "./components/PortfolioContextStrip.jsx";
import { RecentActivity } from "./components/RecentActivity.jsx";
import { ResearchPulse } from "./components/ResearchPulse.jsx";
import { createHomeDataService } from "./data/homeDataService.js";
import { createUnavailableHomeSnapshot } from "./data/homeSnapshotNormalizer.js";
import {
  selectActiveExposureIds,
  selectAttentionById,
  selectDefaultAttention,
  selectDrawerSummary,
  selectFocusTarget,
  selectMarketHighlightId,
  selectSearchItems,
} from "./data/homeSelectors.js";

export function HomePage({ dataService, reducedMotionOverride }) {
  const [searchParams] = useSearchParams();
  const scenario = searchParams.get("fixture") ?? "healthy";
  const requestedMode = searchParams.get("dataMode") === "demo" ? "demo" : undefined;
  const service = useMemo(
    () => dataService ?? createHomeDataService({ mode: requestedMode, scenario }),
    [dataService, requestedMode, scenario],
  );
  const [loadKey, setLoadKey] = useState(0);
  const [state, setState] = useState({ status: "loading", snapshot: null });
  const [activeAttentionId, setActiveAttentionId] = useState(null);

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState({ status: "loading", snapshot: null });
    service.getHomeSnapshot({ signal: controller.signal })
      .then((snapshot) => {
        if (!current) return;
        setState({ status: "ready", snapshot });
        setActiveAttentionId(selectDefaultAttention(snapshot)?.id ?? null);
      })
      .catch((error) => {
        if (!current || error?.code === "HOME_API_CANCELLED") return;
        const connectionState = error?.code === "HOME_API_UNAVAILABLE"
          ? "DISCONNECTED"
          : "ERROR";
        const snapshot = createUnavailableHomeSnapshot({
          connectionState,
          reason: error?.code ?? "HOME_API_UNAVAILABLE",
        });
        setState({ status: "ready", error, snapshot });
        setActiveAttentionId(selectDefaultAttention(snapshot)?.id ?? null);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [loadKey, service]);

  useEffect(() => {
    document.body.classList.add("app-route-active");
    return () => document.body.classList.remove("app-route-active");
  }, []);

  const retry = useCallback(() => setLoadKey((key) => key + 1), []);

  if (state.status === "loading") {
    return <AuthenticatedShell connectionState="CONNECTING" marketMode="ILLUSTRATIVE" reducedMotionOverride={reducedMotionOverride}><HomeLoadingState /></AuthenticatedShell>;
  }

  const snapshot = state.snapshot;
  const activeAttention = selectAttentionById(snapshot, activeAttentionId);
  const activeContext = selectMarketHighlightId(activeAttention);
  const activeExposureIds = selectActiveExposureIds(activeAttention);
  const focusTarget = selectFocusTarget(activeAttention);
  const drawerSummary = selectDrawerSummary(snapshot);

  return (
    <AuthenticatedShell
      contextDrawer={({ open, onClose, onOpen }) => (
        <ContextDrawer
          dataHealth={snapshot.dataHealth}
          governance={snapshot.governance}
          onClose={onClose}
          onOpen={onOpen}
          open={open}
          research={snapshot.research}
          selectedItem={activeAttention}
          summary={drawerSummary}
        />
      )}
      connectionState={snapshot.connectionState}
      marketMode={snapshot.market.visualizationMode}
      reducedMotionOverride={reducedMotionOverride}
      searchItems={selectSearchItems(snapshot)}
    >
      <div className="intelligence-home" data-connection-state={snapshot.connectionState} data-demo-mode={snapshot.demoMode ? "true" : "false"} data-home-version={snapshot.version}>
        <HomeGreeting />
        {state.error ? <HomeConnectionNotice connectionState={snapshot.connectionState} onRetry={retry} /> : null}
        <div className="home-intelligence-grid">
          <MarketContextCanvas activeContext={activeContext} market={snapshot.market} />
          <PortfolioContextStrip activeExposureIds={activeExposureIds} focused={focusTarget === "portfolio"} portfolio={snapshot.portfolio} />
          <AttentionStream activeId={activeAttention?.id} items={snapshot.attentionItems} onSelect={setActiveAttentionId} />
          <ResearchPulse focused={focusTarget === "research"} research={snapshot.research} />
        </div>
        <div className="home-support-grid">
          <RecentActivity items={snapshot.recentActivity} />
          <DataHealthPulse dataHealth={snapshot.dataHealth} focused={focusTarget === "dataHealth"} />
          <GovernancePulse focused={focusTarget === "governance"} governance={snapshot.governance} />
        </div>
        <ExploreNext items={snapshot.exploreNext} />
      </div>
    </AuthenticatedShell>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AttentionStream } from "./components/AttentionStream.jsx";
import { AuthenticatedShell } from "./components/AuthenticatedShell.jsx";
import { ContextDrawer } from "./components/ContextDrawer.jsx";
import { DataHealthPulse } from "./components/DataHealthPulse.jsx";
import { ExploreNext } from "./components/ExploreNext.jsx";
import { GovernancePulse } from "./components/GovernancePulse.jsx";
import { HomeErrorState, HomeLoadingState } from "./components/HomeStates.jsx";
import { HomeGreeting } from "./components/HomeGreeting.jsx";
import { MarketContextCanvas } from "./components/MarketContextCanvas.jsx";
import { PortfolioContextStrip } from "./components/PortfolioContextStrip.jsx";
import { RecentActivity } from "./components/RecentActivity.jsx";
import { ResearchPulse } from "./components/ResearchPulse.jsx";
import { createHomeDataService } from "./data/homeDataService.js";
import { selectActiveExposureIds, selectAttentionById, selectDefaultAttention, selectDrawerSummary, selectSearchItems } from "./data/homeSelectors.js";

export function HomePage({ dataService, reducedMotionOverride }) {
  const [searchParams] = useSearchParams();
  const scenario = searchParams.get("fixture") ?? "healthy";
  const service = useMemo(() => dataService ?? createHomeDataService({ scenario }), [dataService, scenario]);
  const [loadKey, setLoadKey] = useState(0);
  const [state, setState] = useState({ status: "loading", snapshot: null });
  const [activeAttentionId, setActiveAttentionId] = useState(null);

  useEffect(() => {
    let current = true;
    setState({ status: "loading", snapshot: null });
    service.getHomeSnapshot()
      .then((snapshot) => {
        if (!current) return;
        setState({ status: "ready", snapshot });
        setActiveAttentionId(selectDefaultAttention(snapshot)?.id ?? null);
      })
      .catch((error) => {
        if (current) setState({ status: "error", error, snapshot: null });
      });
    return () => { current = false; };
  }, [loadKey, service]);

  useEffect(() => {
    document.body.classList.add("app-route-active");
    return () => document.body.classList.remove("app-route-active");
  }, []);

  const retry = useCallback(() => setLoadKey((key) => key + 1), []);

  if (state.status === "loading") {
    return <AuthenticatedShell reducedMotionOverride={reducedMotionOverride}><HomeLoadingState /></AuthenticatedShell>;
  }
  if (state.status === "error") {
    return <AuthenticatedShell reducedMotionOverride={reducedMotionOverride}><HomeErrorState onRetry={retry} /></AuthenticatedShell>;
  }

  const snapshot = state.snapshot;
  const activeAttention = selectAttentionById(snapshot, activeAttentionId);
  const activeContext = activeAttention?.metadata?.highlightId ?? "breadth";
  const activeExposureIds = selectActiveExposureIds(activeAttention);
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
      reducedMotionOverride={reducedMotionOverride}
      searchItems={selectSearchItems(snapshot)}
    >
      <div className="intelligence-home" data-demo-mode={snapshot.demoMode ? "true" : "false"} data-home-version={snapshot.version}>
        <HomeGreeting environmentLabel={snapshot.environmentLabel} />
        <div className="home-intelligence-grid">
          <MarketContextCanvas activeContext={activeContext} market={snapshot.market} />
          <PortfolioContextStrip activeExposureIds={activeExposureIds} portfolio={snapshot.portfolio} />
          <AttentionStream activeId={activeAttention?.id} items={snapshot.attentionItems} onSelect={setActiveAttentionId} />
          <ResearchPulse research={snapshot.research} />
        </div>
        <div className="home-support-grid">
          <DataHealthPulse dataHealth={snapshot.dataHealth} />
          <RecentActivity items={snapshot.recentActivity} />
          <GovernancePulse governance={snapshot.governance} />
        </div>
        <ExploreNext items={snapshot.exploreNext} />
      </div>
    </AuthenticatedShell>
  );
}

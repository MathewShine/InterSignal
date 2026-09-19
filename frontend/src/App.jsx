import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "./pages/AuthPage.jsx";
import { LandingPage } from "./pages/LandingPage.jsx";
import { AppSectionPlaceholder } from "./features/home/AppSectionPlaceholder.jsx";
import { HomePage } from "./features/home/HomePage.jsx";
import { MarketPage } from "./features/market/MarketPage.jsx";
import { MarketSessionPage } from "./features/market/MarketSessionPage.jsx";
import {
  MarketDerivativesPage,
  MarketIndexDetailPage,
  MarketIndicesPage,
  MarketInstrumentPage,
  MarketSectorDetailPage,
  MarketSectorsPage,
  MarketStocksPage,
} from "./features/market/MarketWorkspacePages.jsx";
import {
  DataLimitationsPage,
  DataLineagePage,
  DataOverviewPage,
  DataSourcesPage,
} from "./features/data/DataPages.jsx";
import {
  GovernanceAuditPage,
  GovernanceAuthorizationsPage,
  GovernanceOverviewPage,
  GovernancePoliciesPage,
  GovernanceReadinessPage,
} from "./features/governance/GovernancePages.jsx";
import {
  PortfolioActivityPage,
  PortfolioHoldingsPage,
  PortfolioOverviewPage,
  PortfolioPerformancePage,
} from "./features/portfolio/PortfolioPages.jsx";
import {
  ResearchBlockedPage,
  ResearchEvidenceDetailPage,
  ResearchEvidencePage,
  ResearchFamiliesPage,
  ResearchFamilyDetailPage,
  ResearchOverviewPage,
  ResearchTimelinePage,
  ResearchValidationPage,
} from "./features/research/ResearchPages.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<LandingPage />} path="/" />
        <Route element={<AuthPage />} path="/auth" />
        <Route element={<HomePage />} path="/app" />
        <Route element={<ResearchOverviewPage />} path="/app/research" />
        <Route element={<ResearchFamiliesPage />} path="/app/research/families" />
        <Route element={<ResearchFamilyDetailPage />} path="/app/research/families/:familyId" />
        <Route element={<ResearchEvidencePage />} path="/app/research/evidence" />
        <Route element={<ResearchEvidenceDetailPage />} path="/app/research/evidence/:evidenceId" />
        <Route element={<ResearchValidationPage />} path="/app/research/validation" />
        <Route element={<ResearchBlockedPage />} path="/app/research/blocked" />
        <Route element={<ResearchTimelinePage />} path="/app/research/timeline" />
        <Route element={<PortfolioOverviewPage />} path="/app/portfolio" />
        <Route element={<PortfolioHoldingsPage />} path="/app/portfolio/holdings" />
        <Route element={<PortfolioActivityPage />} path="/app/portfolio/activity" />
        <Route element={<PortfolioPerformancePage />} path="/app/portfolio/performance" />
        <Route element={<MarketPage />} path="/app/market" />
        <Route element={<MarketIndicesPage />} path="/app/market/indices" />
        <Route element={<MarketIndexDetailPage />} path="/app/market/indices/:symbol" />
        <Route element={<MarketStocksPage />} path="/app/market/stocks" />
        <Route element={<MarketInstrumentPage />} path="/app/market/instruments/:symbol" />
        <Route element={<MarketSectorsPage />} path="/app/market/sectors" />
        <Route element={<MarketSectorDetailPage />} path="/app/market/sectors/:sectorId" />
        <Route element={<MarketDerivativesPage />} path="/app/market/derivatives" />
        <Route element={<MarketSessionPage />} path="/app/market/session" />
        <Route element={<DataOverviewPage />} path="/app/data" />
        <Route element={<DataSourcesPage />} path="/app/data/sources" />
        <Route element={<DataLineagePage />} path="/app/data/lineage" />
        <Route element={<DataLimitationsPage />} path="/app/data/limitations" />
        <Route element={<GovernanceOverviewPage />} path="/app/governance" />
        <Route element={<GovernanceReadinessPage />} path="/app/governance/readiness" />
        <Route element={<GovernancePoliciesPage />} path="/app/governance/policies" />
        <Route element={<GovernanceAuthorizationsPage />} path="/app/governance/authorizations" />
        <Route element={<GovernanceAuditPage />} path="/app/governance/audit" />
        <Route element={<AppSectionPlaceholder area="Alerts" />} path="/app/alerts" />
        <Route element={<AppSectionPlaceholder area="Settings" />} path="/app/settings" />
        <Route element={<AppSectionPlaceholder area="Profile" />} path="/app/profile" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  );
}

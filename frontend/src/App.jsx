import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "./pages/AuthPage.jsx";
import { LandingPage } from "./pages/LandingPage.jsx";
import { AppSectionPlaceholder } from "./features/home/AppSectionPlaceholder.jsx";
import { HomePage } from "./features/home/HomePage.jsx";
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
        <Route element={<AppSectionPlaceholder area="Market" />} path="/app/market" />
        <Route element={<AppSectionPlaceholder area="Data" />} path="/app/data" />
        <Route element={<AppSectionPlaceholder area="Governance" />} path="/app/governance" />
        <Route element={<AppSectionPlaceholder area="Alerts" />} path="/app/alerts" />
        <Route element={<AppSectionPlaceholder area="Settings" />} path="/app/settings" />
        <Route element={<AppSectionPlaceholder area="Profile" />} path="/app/profile" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  );
}

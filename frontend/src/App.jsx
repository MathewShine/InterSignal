import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "./pages/AuthPage.jsx";
import { LandingPage } from "./pages/LandingPage.jsx";
import { AppSectionPlaceholder } from "./features/home/AppSectionPlaceholder.jsx";
import { HomePage } from "./features/home/HomePage.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<LandingPage />} path="/" />
        <Route element={<AuthPage />} path="/auth" />
        <Route element={<HomePage />} path="/app" />
        <Route element={<AppSectionPlaceholder area="Research" />} path="/app/research" />
        <Route element={<AppSectionPlaceholder area="Portfolio" />} path="/app/portfolio" />
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

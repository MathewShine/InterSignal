import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppPlaceholderPage } from "./pages/AppPlaceholderPage.jsx";
import { AuthPage } from "./pages/AuthPage.jsx";
import { LandingPage } from "./pages/LandingPage.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<LandingPage />} path="/" />
        <Route element={<AuthPage />} path="/auth" />
        <Route element={<AppPlaceholderPage />} path="/app" />
        <Route element={<Navigate replace to="/" />} path="*" />
      </Routes>
    </BrowserRouter>
  );
}

import { appConfig } from "../config/appConfig.js";

export function AppShell({ children }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">{appConfig.appStatus}</p>
          <h1>{appConfig.appName}</h1>
        </div>
        <span className="environment-pill">{appConfig.environment}</span>
      </header>
      <main>{children}</main>
    </div>
  );
}


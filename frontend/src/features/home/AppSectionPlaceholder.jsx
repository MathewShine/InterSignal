import { Link } from "react-router-dom";
import { AuthenticatedShell } from "./components/AuthenticatedShell.jsx";

export function AppSectionPlaceholder({ area }) {
  return (
    <AuthenticatedShell area={area}>
      <section className="app-section-placeholder">
        <span className="technical-label">COMING NEXT</span>
        <h1>{area}</h1>
        <p>This application area is reserved for a later implementation command. The shared authenticated shell is ready.</p>
        <Link to="/app">Return to Home →</Link>
      </section>
    </AuthenticatedShell>
  );
}

import { Link } from "react-router-dom";

export function GovernancePulse({ governance }) {
  return (
    <section aria-labelledby="governance-title" className="governance-pulse">
      <div><span className="technical-label">GOVERNANCE</span><h2 id="governance-title">Operational readiness</h2></div>
      <dl><div><dt>Paper</dt><dd>{governance.paper}</dd></div><div><dt>Live</dt><dd>{governance.live}</dd></div><div><dt>Blocking violations</dt><dd className="metric-value">{governance.blockingViolations}</dd></div><div><dt>Pending authorizations</dt><dd className="metric-value">{governance.pendingAuthorizations}</dd></div></dl>
      <Link to="/app/governance">Open Governance →</Link>
    </section>
  );
}

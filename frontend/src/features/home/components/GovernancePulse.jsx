import { Link } from "react-router-dom";

export function GovernancePulse({ focused = false, governance }) {
  if (!governance || governance.status === "unavailable") {
    return <section aria-labelledby="governance-title" className={`governance-pulse home-pulse--empty${focused ? " is-context-focused" : ""}`}><h2 id="governance-title">Readiness</h2><p>Readiness information is unavailable.</p></section>;
  }
  return (
    <section aria-labelledby="governance-title" className={`governance-pulse${focused ? " is-context-focused" : ""}`}>
      <div><h2 id="governance-title">Readiness</h2><p>Operational controls</p></div>
      <dl><div><dt>Paper</dt><dd>{governance.paper}</dd></div><div><dt>Live</dt><dd>{governance.live}</dd></div><div><dt>Broker</dt><dd>{governance.brokerDisplay ?? governance.broker ?? "Not connected"}</dd></div></dl>
      <Link to="/app/governance">View governance →</Link>
    </section>
  );
}

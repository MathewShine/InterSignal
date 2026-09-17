import { Link } from "react-router-dom";

export function DataHealthPulse({ dataHealth }) {
  return (
    <section aria-labelledby="data-health-title" className="home-pulse data-health-pulse">
      <header><div><span className="technical-label">DATA HEALTH</span><h2 id="data-health-title">Data health</h2></div><span className="state-tag state-tag--quiet">{dataHealth.status}</span></header>
      <div className="data-health-list">{dataHealth.rows.map((row) => <div key={row.id}><span><i className={`health-dot health-dot--${row.tone}`} />{row.label}</span><strong>{row.value}</strong></div>)}</div>
      <Link to="/app/data">Open Data →</Link>
    </section>
  );
}

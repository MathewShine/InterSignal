import { Link } from "react-router-dom";

export function DataHealthPulse({ dataHealth, focused = false }) {
  if (!dataHealth || dataHealth.status === "unavailable") {
    return <section aria-labelledby="data-health-title" className={`home-pulse home-pulse--empty${focused ? " is-context-focused" : ""}`}><h2 id="data-health-title">Data health</h2><p>Data information is unavailable right now.</p></section>;
  }
  const hasBlocker = dataHealth.rows.some((row) => row.tone === "blocked");
  return (
    <section aria-labelledby="data-health-title" className={`home-pulse data-health-pulse${focused ? " is-context-focused" : ""}`}>
      <header><div><h2 id="data-health-title">Data health</h2><p>Research inputs</p></div></header>
      <div className="data-health-list">{dataHealth.rows.filter((row) => row.id !== "refs").map((row) => <div key={row.id}><span><i className={`health-dot health-dot--${row.tone}`} />{row.shortLabel ?? row.label}</span><strong>{row.displayValue ?? row.value}</strong></div>)}</div>
      <footer><Link to="/app/data">View data health →</Link>{hasBlocker ? <Link to="/app/data/limitations">Review limitations →</Link> : null}</footer>
    </section>
  );
}

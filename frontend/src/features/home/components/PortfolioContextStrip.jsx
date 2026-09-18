import { Link } from "react-router-dom";

export function PortfolioContextStrip({ activeExposureIds = [], focused = false, portfolio }) {
  if (!portfolio || portfolio.status === "unavailable") {
    return (
      <section aria-labelledby="portfolio-title" className={`portfolio-strip portfolio-strip--empty${focused ? " is-context-focused" : ""}`} data-source-status="UNAVAILABLE">
        <div><h2 id="portfolio-title">Portfolio</h2><p>Portfolio information is unavailable right now.</p></div>
      </section>
    );
  }
  if (!portfolio || portfolio.status === "empty") {
    return (
      <section aria-labelledby="portfolio-title" className={`portfolio-strip portfolio-strip--empty${focused ? " is-context-focused" : ""}`} data-source-status="EMPTY">
        <div><h2 id="portfolio-title">No portfolio yet</h2><p>Add holdings manually when you’re ready.</p></div>
        <div className="portfolio-empty-actions"><button type="button">Add manually</button><button disabled type="button">Connect broker <small>Coming later</small></button></div>
      </section>
    );
  }

  return (
    <section aria-labelledby="portfolio-title" className={`portfolio-strip${focused ? " is-context-focused" : ""}`} data-source-status={portfolio.sourceStatus}>
      <header><div><h2 id="portfolio-title">Portfolio</h2><span className="source-tag" title="Portfolio data is generated from the platform’s seeded Portfolio OS state.">Demo portfolio</span></div><div className="portfolio-strip__value"><span>Portfolio value</span><strong className="metric-value">{portfolio.value}</strong></div></header>
      <div className="portfolio-strip__metrics">
        <div><span>Invested</span><strong className="metric-value">{portfolio.invested}</strong></div>
        <div><span>Cash</span><strong className="metric-value">{portfolio.cash}</strong></div>
        <div><span>Period change</span><strong className="metric-value is-positive">{portfolio.periodChange}</strong></div>
      </div>
      <div aria-label="Portfolio allocation" className="portfolio-allocation">
        {portfolio.allocations.map((allocation) => (
          <span
            className={activeExposureIds.includes(allocation.id) ? "is-active" : ""}
            key={allocation.id}
            style={{ "--allocation": allocation.percent }}
            title={`${allocation.label} ${allocation.percent}%`}
          ><b>{allocation.label}</b><small>{allocation.percent}%</small></span>
        ))}
      </div>
      <footer><span>{portfolio.holdingCount ?? "Sample"} holding · {portfolio.concentration} concentration</span><Link to="/app/portfolio">View portfolio →</Link></footer>
    </section>
  );
}

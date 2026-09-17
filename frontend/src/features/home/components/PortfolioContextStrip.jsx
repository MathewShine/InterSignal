export function PortfolioContextStrip({ activeExposureIds = [], portfolio }) {
  if (!portfolio || portfolio.status === "empty") {
    return (
      <section aria-labelledby="portfolio-title" className="portfolio-strip portfolio-strip--empty">
        <div><span className="technical-label">PORTFOLIO CONTEXT</span><h2 id="portfolio-title">No portfolio connected yet.</h2><p>Add holdings manually when you’re ready. Broker connection is intentionally unavailable.</p></div>
        <div className="portfolio-empty-actions"><button type="button">Add manually</button><button disabled type="button">Connect broker <small>Coming later</small></button></div>
      </section>
    );
  }

  return (
    <section aria-labelledby="portfolio-title" className="portfolio-strip">
      <header><div><span className="technical-label">PORTFOLIO CONTEXT</span><h2 id="portfolio-title">{portfolio.label}</h2></div><strong className="metric-value">{portfolio.value}</strong></header>
      <div className="portfolio-strip__metrics">
        <div><span>Cash</span><strong className="metric-value">{portfolio.cash}</strong></div>
        <div><span>Invested</span><strong className="metric-value">{portfolio.invested}</strong></div>
        <div><span>Today</span><strong className="metric-value is-positive">{portfolio.periodChange}</strong></div>
        <div><span>vs benchmark</span><strong className="metric-value is-positive">{portfolio.benchmarkDelta}</strong></div>
        <div><span>Concentration</span><strong>{portfolio.concentration}</strong></div>
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
    </section>
  );
}

import { motion } from "motion/react";
import { useState } from "react";

function trajectoryPath(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
}

export function MarketContextCanvas({ activeContext = "breadth", market }) {
  const [horizon, setHorizon] = useState(market?.selectedHorizon ?? "Today");

  if (!market || (market.status === "unavailable" && market.visualizationMode !== "ILLUSTRATIVE")) {
    return (
      <section aria-labelledby="market-title" className="market-canvas market-canvas--empty">
        <div><h2 id="market-title">Market overview</h2><p>Market information is unavailable right now.</p></div>
      </section>
    );
  }

  const marker = market.contextMarkers[activeContext] ?? market.contextMarkers.breadth;
  return (
    <motion.section
      animate={{ opacity: 1, y: 0 }}
      aria-labelledby="market-title"
      className="market-canvas"
      data-active-context={activeContext}
      data-market-availability={market.availability ?? "AVAILABLE"}
      data-visualization-mode={market.visualizationMode ?? "DEMO"}
      initial={{ opacity: 0, y: 8 }}
      transition={{ delay: .22, duration: .3 }}
    >
      <header className="market-canvas__header">
        <div className="market-canvas__title"><div><h2 id="market-title">Market overview</h2><p>{market.index} context</p></div><span className="source-tag" title="Live market connection has not been enabled yet.">Sample market data</span></div>
        <div className="market-canvas__quote"><strong className="metric-value">{market.value}</strong><span className="metric-value is-positive">{market.dayChange}</span></div>
      </header>
      <div aria-label="Market horizon" className="market-horizons">
        {market.horizons.map((item) => <button aria-pressed={item === horizon} key={item} onClick={() => setHorizon(item)} type="button">{item}</button>)}
      </div>
      <div className="market-canvas__plot">
        <svg aria-label={market.textualSummary} preserveAspectRatio="none" role="img" viewBox="0 0 100 90">
          <defs>
            <linearGradient id="marketArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#c9eaff" stopOpacity=".48" /><stop offset="1" stopColor="#c9eaff" stopOpacity="0" /></linearGradient>
          </defs>
          {[18, 36, 54, 72].map((y) => <line className="market-grid-line" key={y} x1="0" x2="100" y1={y} y2={y} />)}
          {market.participation.map((height, index) => <rect className="market-participation" height={height * .22} key={index} width="4.5" x={index * 8.6} y={88 - height * .22} />)}
          <path className="market-area" d={`${trajectoryPath(market.trajectory)} L 100 90 L 0 90 Z`} />
          <motion.path animate={{ pathLength: 1 }} className="market-trajectory" d={trajectoryPath(market.trajectory)} initial={{ pathLength: 0 }} transition={{ delay: .32, duration: .7 }} />
          <motion.circle animate={{ cx: marker.x, cy: marker.y, r: 2.2 }} className="market-marker-halo" transition={{ duration: .28 }} />
          <motion.circle animate={{ cx: marker.x, cy: marker.y }} className="market-marker" r="1.15" transition={{ duration: .28 }}><title>{marker.label}</title></motion.circle>
        </svg>
      </div>
      <footer className="market-canvas__footer">
        <div><span>Breadth</span><strong className="metric-value">{market.breadth.label}</strong></div>
        <div><span>Volume</span><strong>{market.volume}</strong></div>
        <div><span>Leadership</span><strong>{market.leadership.join(" / ")}</strong></div>
        <div className="market-sector-row">{market.sectors.map((sector) => <span className={activeContext === sector.context ? "is-contextual" : ""} key={sector.id}>{sector.label} <b>{sector.change}</b></span>)}</div>
      </footer>
    </motion.section>
  );
}

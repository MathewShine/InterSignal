import { AnimatedNumber } from "../motion/AnimatedNumber.jsx";
import { DemoBadge } from "../ui/DataDisplay.jsx";

function SurfaceChrome({ title, meta, children, tone = "light" }) {
  return (
    <article className={`product-surface product-surface--${tone}`} aria-label={title}>
      <header className="product-surface__chrome">
        <span className="product-surface__mark" aria-hidden="true" />
        <strong>{title}</strong>
        <span>{meta}</span>
      </header>
      {children}
    </article>
  );
}

function MarketSurface({ compact = false }) {
  return (
    <SurfaceChrome meta="Illustrative view" title="Market intelligence" tone="market">
      <div className={`surface-market ${compact ? "is-compact" : ""}`}>
        <div className="surface-market__headline">
          <div>
            <span className="technical-label">NIFTY 500 · DEMO</span>
            <strong className="surface-number">22,842</strong>
          </div>
          <span className="surface-chip">Context updated</span>
        </div>
        <svg aria-label="Illustrative NIFTY 500 line" className="surface-chart" role="img" viewBox="0 0 620 210">
          <defs>
            <linearGradient id="surface-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#dfff32" stopOpacity="0.32" />
              <stop offset="1" stopColor="#dfff32" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path className="surface-chart__grid" d="M0 45H620 M0 105H620 M0 165H620" />
          <path className="surface-chart__area" d="M0 168 C58 152 72 176 126 142 C176 111 202 148 254 111 C304 76 338 118 386 83 C442 43 496 92 620 36 V210 H0Z" />
          <path className="surface-chart__line" d="M0 168 C58 152 72 176 126 142 C176 111 202 148 254 111 C304 76 338 118 386 83 C442 43 496 92 620 36" />
          <circle cx="386" cy="83" r="5" />
          <circle cx="620" cy="36" r="5" />
        </svg>
        <div className="surface-market__metrics">
          <div><span>Breadth</span><strong><AnimatedNumber value={61} format={(value) => `${Math.round(value)}%`} /></strong></div>
          <div><span>Volume rhythm</span><strong>1.08×</strong></div>
          <div><span>Portfolio exposure</span><strong>24%</strong></div>
          <div><span>Research context</span><strong>Broadening</strong></div>
        </div>
      </div>
    </SurfaceChrome>
  );
}

function ResearchSurface() {
  return (
    <SurfaceChrome meta="Evidence view" title="Research" tone="research">
      <div className="surface-research">
        <span className="technical-label">Open question</span>
        <h3>Is participation expanding beyond the leaders?</h3>
        <div className="surface-research__thread">
          <span><i />Evidence captured <b>04</b></span>
          <span><i />Context changes <b>03</b></span>
          <span><i />Review window <b>12w</b></span>
        </div>
        <p>Frame → observe → revisit</p>
      </div>
    </SurfaceChrome>
  );
}

function PortfolioSurface({ detailed = false }) {
  return (
    <SurfaceChrome meta="Example data" title="Portfolio" tone="portfolio">
      <div className={`surface-portfolio ${detailed ? "is-detailed" : ""}`}>
        <div className="surface-portfolio__topline">
          <div>
            <span className="technical-label">Illustrative value</span>
            <strong className="surface-number"><AnimatedNumber value={48200} format={(value) => Math.round(value).toLocaleString("en-GB")} /></strong>
          </div>
          <DemoBadge>Demo portfolio</DemoBadge>
        </div>
        <div className="surface-allocation" aria-label="Demo portfolio allocation">
          <span style={{ "--share": "44%" }}><b>44%</b> Global equity</span>
          <span style={{ "--share": "27%" }}><b>27%</b> Quality leaders</span>
          <span style={{ "--share": "17%" }}><b>17%</b> Short duration</span>
          <span style={{ "--share": "12%" }}><b>12%</b> Cash</span>
        </div>
        <div className="surface-portfolio__facts">
          <span><small>Benchmark</small><b>Global blended</b></span>
          <span><small>Equity exposure</small><b>71%</b></span>
          <span><small>Cash</small><b>12%</b></span>
        </div>
        {detailed ? (
          <div className="surface-holdings">
            <span className="technical-label">Top holdings · illustrative</span>
            <div><b>Global equity fund</b><span>18%</span></div>
            <div><b>Quality leaders</b><span>14%</span></div>
            <div><b>Broad market</b><span>11%</span></div>
          </div>
        ) : null}
        <p className="surface-disclaimer">Demo data. No recommendation.</p>
      </div>
    </SurfaceChrome>
  );
}

function MarketLensSurface() {
  return (
    <SurfaceChrome meta="Illustrative" title="Market" tone="market-lens">
      <div className="surface-lens">
        <span className="technical-label">NIFTY 500</span>
        <strong>Momentum<br />broadening</strong>
        <svg aria-hidden="true" viewBox="0 0 240 110">
          <path d="M4 88 C44 76 57 91 91 62 S144 58 173 34 S210 37 236 14" />
          <circle cx="236" cy="14" r="4" />
        </svg>
        <div><span>Breadth</span><b>61%</b></div>
      </div>
    </SurfaceChrome>
  );
}

function PortfolioLensSurface() {
  return (
    <SurfaceChrome meta="Demo" title="Portfolio context" tone="portfolio-lens">
      <div className="surface-lens surface-lens--portfolio">
        <DemoBadge>Demo portfolio</DemoBadge>
        <strong>Exposure<br />in context</strong>
        <div className="surface-lens__ring" aria-hidden="true"><span /></div>
        <div><span>Market exposure</span><b>24%</b></div>
        <div><span>Cash</span><b>12%</b></div>
      </div>
    </SurfaceChrome>
  );
}

export function ProductSurface({ variant = "market", detailed = false, compact = false }) {
  if (variant === "research") return <ResearchSurface />;
  if (variant === "portfolio") return <PortfolioSurface detailed={detailed} />;
  if (variant === "portfolio-lens") return <PortfolioLensSurface />;
  if (variant === "market-lens") return <MarketLensSurface />;
  return <MarketSurface compact={compact} />;
}

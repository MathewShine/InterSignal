import { motion, useReducedMotion } from "motion/react";
import { PerspectiveSurface } from "./PerspectiveSurface.jsx";
import { ProductSurface } from "./ProductSurface.jsx";
import { SignalCurve } from "./SignalCurve.jsx";

export function PortfolioContextScene() {
  const reducedMotion = useReducedMotion();

  return (
    <section
      className="visual-scene portfolio-stage"
      data-header-surface="sky"
      data-header-theme="light"
      data-nav-label="Invest"
      data-scene="portfolio-context"
      id="invest"
    >
      <div className="portfolio-stage__radial" aria-hidden="true">
        <span /><span /><span />
      </div>
      <SignalCurve
        className="portfolio-stage__carry"
        path="M8 36 C118 12 172 90 278 84 C390 78 434 166 552 134 C642 110 706 132 770 182"
        staticPath
        viewBox="0 0 780 210"
      />

      <div className="page-frame portfolio-stage__inner">
        <header className="portfolio-stage__headline">
          <p className="technical-label">Portfolio context</p>
          <h2>Your portfolio, with the market around it.</h2>
          <p>See allocation, exposure and market setting together—without reducing the whole picture to one score.</p>
        </header>

        <motion.div
          className="portfolio-stage__device"
          data-qa="portfolio-surface"
          initial={reducedMotion ? false : { opacity: 0.64, scale: 0.98, x: 64 }}
          transition={{ duration: reducedMotion ? 0 : 0.64, ease: [0.22, 1, 0.36, 1] }}
          viewport={{ amount: 0.4, once: true }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
        >
          <PerspectiveSurface cursorLabel="Open" delay={0} intensity="main">
            <ProductSurface detailed variant="portfolio" />
          </PerspectiveSurface>
        </motion.div>

        <p className="portfolio-stage__note technical-label">Illustrative interface · Demo data · No recommendation</p>
      </div>
    </section>
  );
}

export const PortfolioStage = PortfolioContextScene;

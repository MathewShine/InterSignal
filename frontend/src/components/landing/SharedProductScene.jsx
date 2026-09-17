import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { ProductSurface } from "./ProductSurface.jsx";
import { SignalCurve } from "./SignalCurve.jsx";

export function PerspectiveSeparationScene() {
  const ref = useRef(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const progress = useSpring(scrollYProgress, { stiffness: 96, damping: 26, mass: 0.8 });

  const researchX = useTransform(progress, [0.28, 0.44], [-40, 0]);
  const researchOpacity = useTransform(progress, [0.28, 0.44], [0, 1]);
  const portfolioY = useTransform(progress, [0.56, 0.72], [40, 0]);
  const portfolioOpacity = useTransform(progress, [0.56, 0.72], [0, 1]);
  const marketX = useTransform(progress, [0.82, 0.94], [42, 0]);
  const marketOpacity = useTransform(progress, [0.82, 0.94], [0, 1]);
  const curveProgress = useTransform(progress, [0.94, 0.975], [0, 1]);
  const curveOpacity = useTransform(progress, [0.94, 0.95], [0, 1]);
  const curveArrow = useTransform(progress, [0.965, 0.985], [0, 1]);
  const connectorOpacity = useTransform(progress, [0.94, 0.975], [0, 1]);

  return (
    <section
      className="visual-scene separation-scene"
      data-header-theme="light"
      data-nav-label="Research"
      data-scene="decompose"
      id="product"
      ref={ref}
    >
      <div className="page-frame separation-scene__inner">
        <span className="scene-anchor" id="research" />
        <header className="separation-scene__intro">
          <p className="technical-label">One system · three working views</p>
          <h2>Three perspectives.<br />One connected view.</h2>
        </header>

        <div className="separation-stage" data-qa="separation-stage">
          <SignalCurve
            className="separation-stage__carry"
            dataQa="separation-connector"
            opacity={reducedMotion ? undefined : curveOpacity}
            arrowOpacity={reducedMotion ? undefined : curveArrow}
            path="M12 150 C112 48 174 186 286 108 C390 36 470 154 598 76 C652 43 696 48 748 24"
            pathLength={reducedMotion ? undefined : curveProgress}
            staticPath={reducedMotion}
            viewBox="0 0 760 210"
          />

          <motion.article
            className="decomposition-surface decomposition-surface--research"
            data-qa="research-surface"
            style={reducedMotion ? undefined : { opacity: researchOpacity, x: researchX }}
          >
            <div className="decomposition-surface__label">
              <span>Research</span>
              <small>Evidence before conclusion</small>
            </div>
            <ProductSurface variant="research" />
          </motion.article>

          <motion.article
            className="decomposition-surface decomposition-surface--portfolio"
            data-qa="separation-portfolio-surface"
            style={reducedMotion ? undefined : { opacity: portfolioOpacity, y: portfolioY }}
          >
            <div className="decomposition-surface__label">
              <span>Portfolio</span>
              <small>Exposure in context</small>
            </div>
            <ProductSurface variant="portfolio" />
          </motion.article>

          <motion.article
            className="decomposition-surface decomposition-surface--market"
            data-qa="market-surface"
            style={reducedMotion ? undefined : { opacity: marketOpacity, x: marketX }}
          >
            <div className="decomposition-surface__label">
              <span>Market</span>
              <small>What changed</small>
            </div>
            <ProductSurface variant="market-lens" />
          </motion.article>

          <motion.a
            className="trade-connector"
            href="#trade"
            style={reducedMotion ? undefined : { opacity: connectorOpacity }}
          >
            <span>Trade</span>
            <small>Coming next</small>
            <b aria-hidden="true">→</b>
          </motion.a>
        </div>
      </div>
    </section>
  );
}

export const SharedProductScene = PerspectiveSeparationScene;

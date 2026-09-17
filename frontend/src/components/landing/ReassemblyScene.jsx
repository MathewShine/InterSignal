import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { ProductSurface } from "./ProductSurface.jsx";
import { SignalCurve } from "./SignalCurve.jsx";

export function ReassemblyScene() {
  const ref = useRef(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const progress = useSpring(scrollYProgress, { stiffness: 98, damping: 27, mass: 0.8 });

  const researchX = useTransform(progress, [0.3, 0.46, 0.84, 0.94], [-680, -318, -318, -276]);
  const researchOpacity = useTransform(progress, [0.3, 0.42], [0, 1]);
  const researchScale = useTransform(progress, [0.3, 0.46, 0.84, 0.94], [0.88, 0.82, 0.82, 0.76]);

  const portfolioOpacity = useTransform(progress, [0, 0.12], [0, 1]);
  const portfolioScale = useTransform(progress, [0, 0.18, 0.84, 0.94], [0.96, 0.9, 0.9, 0.82]);

  const marketX = useTransform(progress, [0.58, 0.74, 0.84, 0.94], [680, 318, 318, 276]);
  const marketOpacity = useTransform(progress, [0.58, 0.7], [0, 1]);
  const marketScale = useTransform(progress, [0.58, 0.74, 0.84, 0.94], [0.88, 0.82, 0.82, 0.76]);

  const curveProgress = useTransform(progress, [0.84, 0.93], [0, 1]);
  const curveOpacity = useTransform(progress, [0.84, 0.86], [0, 1]);
  const curveArrow = useTransform(progress, [0.91, 0.94], [0, 1]);
  const brandOpacity = useTransform(progress, [0.94, 0.95], [0, 1]);
  const brandY = useTransform(progress, [0.94, 0.95], [12, 0]);

  const flowTransition = reducedMotion
    ? { duration: 0 }
    : { duration: 0.62, ease: [0.22, 1, 0.36, 1] };
  const flowViewport = { amount: 0.75, once: true };

  return (
    <section
      className="reassembly-scene"
      data-header-theme="light"
      data-nav-label="Trade"
      data-scene="reassemble"
      id="trade"
      ref={ref}
    >
      <div className="reassembly-scene__sticky">
        <div className="reassembly-stage" data-qa="reassembly-stage">
          <motion.div
            className="reassembly-piece reassembly-piece--research"
            data-qa="reassembly-research"
            style={reducedMotion ? undefined : { opacity: researchOpacity, scale: researchScale, x: researchX }}
          >
            <ProductSurface variant="research" />
          </motion.div>

          <motion.div
            className="reassembly-piece reassembly-piece--portfolio"
            data-qa="reassembly-portfolio"
            style={reducedMotion ? undefined : { opacity: portfolioOpacity, scale: portfolioScale }}
          >
            <ProductSurface variant="portfolio" />
          </motion.div>

          <motion.div
            className="reassembly-piece reassembly-piece--market"
            data-qa="reassembly-market"
            style={reducedMotion ? undefined : { opacity: marketOpacity, scale: marketScale, x: marketX }}
          >
            <ProductSurface variant="market-lens" />
          </motion.div>

          <SignalCurve
            arrowOpacity={reducedMotion ? undefined : curveArrow}
            className="reassembly-stage__curve"
            dataQa="reassembly-connector"
            opacity={reducedMotion ? undefined : curveOpacity}
            path="M16 126 C120 18 166 214 282 114 C372 35 429 188 520 96 C578 38 632 66 706 42"
            pathLength={reducedMotion ? undefined : curveProgress}
            staticPath={reducedMotion}
            viewBox="0 0 720 220"
          />

          <motion.div
            className="reassembly-brand"
            data-reveal-threshold="0.94"
            data-qa="reassembly-wordmark"
            style={reducedMotion ? undefined : { opacity: brandOpacity, y: brandY }}
          >
            <strong>INTERSIGNAL</strong>
            <span>Research → Market context → Portfolio</span>
          </motion.div>
        </div>
      </div>

      <div className="reassembly-flow" data-qa="reassembly-flow">
        <motion.article
          className="reassembly-flow__piece reassembly-flow__piece--portfolio"
          data-qa="reassembly-flow-portfolio"
          initial={reducedMotion ? false : { opacity: 0, y: 28 }}
          transition={flowTransition}
          viewport={flowViewport}
          whileInView={{ opacity: 1, y: 0 }}
        >
          <span className="technical-label">Portfolio</span>
          <ProductSurface variant="portfolio" />
        </motion.article>

        <motion.article
          className="reassembly-flow__piece reassembly-flow__piece--research"
          data-qa="reassembly-flow-research"
          initial={reducedMotion ? false : { opacity: 0, x: -36 }}
          transition={flowTransition}
          viewport={flowViewport}
          whileInView={{ opacity: 1, x: 0 }}
        >
          <span className="technical-label">Research</span>
          <ProductSurface variant="research" />
        </motion.article>

        <motion.article
          className="reassembly-flow__piece reassembly-flow__piece--market"
          data-qa="reassembly-flow-market"
          initial={reducedMotion ? false : { opacity: 0, x: 36 }}
          transition={flowTransition}
          viewport={flowViewport}
          whileInView={{ opacity: 1, x: 0 }}
        >
          <span className="technical-label">Market</span>
          <ProductSurface variant="market-lens" />
        </motion.article>

        <motion.div
          className="reassembly-flow__brand"
          data-qa="reassembly-flow-wordmark"
          initial={reducedMotion ? false : { opacity: 0, y: 12 }}
          transition={flowTransition}
          viewport={{ amount: 0.9, margin: "0px 0px -40% 0px", once: true }}
          whileInView={{ opacity: 1, y: 0 }}
        >
          <strong>INTERSIGNAL</strong>
          <span>Research → Market context → Portfolio</span>
        </motion.div>
      </div>
    </section>
  );
}

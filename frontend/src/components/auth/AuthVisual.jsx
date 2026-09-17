import { motion } from "motion/react";
import { Link } from "react-router-dom";
import { BrandMark } from "../brand/BrandMark.jsx";
import { useMotionPreference } from "../motion/index.js";

export function AuthVisual() {
  const { reducedMotion } = useMotionPreference();

  return (
    <section aria-label="InterSignal context" className="auth-visual">
      <Link aria-label="Back to InterSignal home" className="auth-visual__brand" to="/">
        <BrandMark />
      </Link>

      <div className="auth-visual__body">
        <p className="technical-label">INTERSIGNAL WORKSPACE</p>
        <h2>Context before action.</h2>
        <p className="auth-visual__copy">
          Research the market, understand your portfolio, and carry context into every decision.
        </p>
        <p className="auth-visual__modes">Research <i /> Invest <i /> Trade</p>
      </div>

      <div aria-hidden="true" className="auth-visual__scene">
        <motion.svg className="auth-visual__curve" preserveAspectRatio="none" viewBox="0 0 680 220">
          <motion.path
            animate={{ opacity: 1, pathLength: 1 }}
            d="M10 180 C108 144 126 70 224 112 S384 170 474 82 S574 58 660 24"
            fill="none"
            initial={reducedMotion ? { opacity: 1, pathLength: 1 } : { opacity: 0.28, pathLength: 0 }}
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="2"
            transition={{ duration: reducedMotion ? 0 : 1.1, delay: reducedMotion ? 0 : 0.18, ease: [0.22, 1, 0.36, 1] }}
            vectorEffect="non-scaling-stroke"
          />
          <motion.path
            animate={{ opacity: 1 }}
            d="m642 20 18 4-8 17"
            fill="none"
            initial={{ opacity: reducedMotion ? 1 : 0 }}
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            transition={{ duration: reducedMotion ? 0 : 0.22, delay: reducedMotion ? 0 : 1.16 }}
          />
        </motion.svg>

        <motion.article
          animate={reducedMotion ? undefined : { y: [0, -3, 0] }}
          className="auth-context-surface"
          transition={{ duration: 5.6, ease: "easeInOut", repeat: Infinity }}
        >
          <header><span /><strong>Market context</strong><small>Illustrative</small></header>
          <div className="auth-context-surface__body">
            <span className="technical-label">TODAY'S VIEW</span>
            <strong>Signal, with context.</strong>
            <svg viewBox="0 0 260 72">
              <path d="M2 58 C48 53 61 20 103 38 S171 55 205 22 S238 18 258 6" />
              <circle cx="258" cy="6" r="3" />
            </svg>
          </div>
        </motion.article>

        <motion.div
          animate={{ opacity: 1, y: 0 }}
          className="auth-context-datum"
          initial={reducedMotion ? false : { opacity: 0, y: 6 }}
          transition={{ duration: reducedMotion ? 0 : 0.3, delay: reducedMotion ? 0 : 0.86 }}
        >
          <span>Research note</span>
          <strong>Context carried forward</strong>
        </motion.div>
      </div>
    </section>
  );
}

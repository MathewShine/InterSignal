import { motion, useReducedMotion } from "motion/react";
import { BrandMark } from "../brand/BrandMark.jsx";
import { PrimaryAction, SecondaryAction } from "../ui/Actions.jsx";

export function PublicFooter() {
  const reducedMotion = useReducedMotion();

  return (
    <section
      className="final-statement"
      data-header-theme="dark"
      data-nav-label="Trade"
      data-scene="resolve"
      id="company"
    >
      <div className="final-statement__signal" aria-hidden="true">
        <svg viewBox="0 0 240 110">
          <motion.path
            d="M8 80 C54 76 55 38 101 58 S160 78 220 18"
            initial={reducedMotion ? false : { pathLength: 0, opacity: 0.35 }}
            transition={{ duration: reducedMotion ? 0 : 1.55, ease: [0.22, 1, 0.36, 1] }}
            viewport={{ amount: 0.6, once: true }}
            whileInView={{ pathLength: 1, opacity: 1 }}
          />
          <motion.path
            d="M205 14 L220 18 L214 33"
            initial={reducedMotion ? false : { opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.25, delay: reducedMotion ? 0 : 1.35 }}
            viewport={{ amount: 0.6, once: true }}
            whileInView={{ opacity: 1 }}
          />
        </svg>
      </div>
      <div className="page-frame final-statement__inner">
        <p className="technical-label">The clearer view</p>
        <h2>SEE MORE.<br /><span>DECIDE WITH CONTEXT.</span></h2>
        <div className="final-statement__actions" data-qa="final-cta">
          <PrimaryAction className="button--signal" href="#product">Explore InterSignal</PrimaryAction>
          <SecondaryAction href="/auth?mode=signin">Sign in</SecondaryAction>
        </div>
      </div>
      <footer className="page-frame public-footer">
        <BrandMark />
        <nav aria-label="Footer navigation">
          <a href="#product">Product</a>
          <a href="#research">Research</a>
          <a href="#invest">Invest</a>
          <a href="#trade">Trade</a>
        </nav>
        <p>Information and analytical context, not investment advice.</p>
        <span>© InterSignal</span>
      </footer>
    </section>
  );
}

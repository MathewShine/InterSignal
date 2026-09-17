import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import { PrimaryAction } from "../ui/Actions.jsx";
import { AnimatedNumber } from "../motion/AnimatedNumber.jsx";
import { FloatingDatum } from "./FloatingDatum.jsx";
import { KineticHeadline } from "./KineticHeadline.jsx";
import { MobileProductPrototype } from "./MobileProductPrototype.jsx";
import { PerspectiveSurface } from "./PerspectiveSurface.jsx";
import { SignalCurve } from "./SignalCurve.jsx";
import { SignalField } from "./SignalField.jsx";

export function SignalHero() {
  const ref = useRef(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const exitProgress = useSpring(scrollYProgress, { stiffness: 100, damping: 26, mass: 0.8 });
  const prototypeY = useTransform(exitProgress, [0, 0.32, 1], [0, 0, -58]);
  const trajectoryX = useTransform(exitProgress, [0, 0.3, 1], [0, 0, 54]);
  const fieldScale = useTransform(exitProgress, [0, 0.35, 1], [1, 1, 0.975]);
  const fieldOpacity = useTransform(exitProgress, [0, 0.35, 1], [1, 1, 0.78]);

  return (
    <section
      className="signal-hero"
      data-header-theme="light"
      data-nav-label="Product"
      data-scene="signal"
      id="top"
      ref={ref}
    >
      <SignalField />
      <div className="signal-hero__grain" aria-hidden="true" />

      <div className="signal-hero__content page-frame">
        <div className="signal-hero__headline-zone" data-qa="hero-headline-zone">
          <div className="signal-hero__eyebrow technical-label">
            <span>Research</span><i /> <span>Portfolio</span><i /> <span>Market intelligence</span>
          </div>
          <KineticHeadline />
        </div>

        <motion.div
          className="signal-hero__theatre"
          data-overlap-max="0"
          data-qa="hero-product-theatre"
          style={reducedMotion ? undefined : { opacity: fieldOpacity, scale: fieldScale }}
        >
          <div className="signal-hero__safe-seam" aria-hidden="true" />
          <motion.div
            className="signal-hero__market-field"
            style={reducedMotion ? undefined : { x: trajectoryX }}
          >
            <span className="signal-hero__market-radial" aria-hidden="true"><i /></span>
            <span className="signal-hero__market-texture" aria-hidden="true" />
            <SignalCurve delay={0.85} />
            <span className="signal-hero__marker signal-hero__marker--one" aria-hidden="true" />
            <span className="signal-hero__marker signal-hero__marker--two" aria-hidden="true" />
          </motion.div>

          <motion.div className="signal-hero__mobile" style={reducedMotion ? undefined : { y: prototypeY }}>
            <PerspectiveSurface cursorLabel="Explore" delay={1.15} duration={0.42} intensity="main">
              <MobileProductPrototype />
            </PerspectiveSurface>
          </motion.div>

          <FloatingDatum
            className="floating-datum--breadth"
            delay={1.9}
            detail="illustrative"
            label="Breadth"
            parallax
            value={<AnimatedNumber value={61} format={(value) => `${Math.round(value)}%`} />}
          />
          <FloatingDatum
            className="floating-datum--exposure"
            delay={2.05}
            detail="demo portfolio"
            label="Market exposure"
            parallax
            value="24%"
          />

        </motion.div>

        <div className="signal-hero__support" data-qa="hero-cta-cluster">
          <p>Research, portfolio intelligence and market context—held in one coherent view.</p>
          <motion.div
            animate={{ opacity: 1, scale: 1 }}
            className="signal-hero__cta-emphasis"
            initial={reducedMotion ? false : { opacity: 0.42, scale: 0.985 }}
            transition={{ duration: reducedMotion ? 0 : 0.42, delay: reducedMotion ? 0 : 1.78, ease: [0.22, 1, 0.36, 1] }}
          >
            <PrimaryAction className="button--signal" href="#product">Explore InterSignal</PrimaryAction>
          </motion.div>
        </div>

        <p className="signal-hero__note">Illustrative product data. Information and context only.</p>
      </div>
    </section>
  );
}

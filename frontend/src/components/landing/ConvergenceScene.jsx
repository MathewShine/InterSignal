import { useRef, useState } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";

const sources = [
  { label: "Price", className: "convergence-label--price", path: "M22 88 C248 78 286 262 536 300", range: [0, 0.25] },
  { label: "Volume", className: "convergence-label--volume", path: "M56 236 C262 218 328 326 536 300", range: [0.04, 0.25] },
  { label: "Momentum", className: "convergence-label--momentum", path: "M104 500 C274 464 368 344 536 300", range: [0.25, 0.45] },
  { label: "Sector", className: "convergence-label--sector", path: "M1078 78 C826 86 806 268 564 300", range: [0.28, 0.45] },
  { label: "Breadth", className: "convergence-label--breadth", path: "M1070 290 C828 284 772 330 564 300", range: [0.45, 0.62] },
  { label: "Events", className: "convergence-label--events", path: "M1012 520 C812 450 748 344 564 300", range: [0.48, 0.62] },
];

function ConvergencePath({ source, progress, reducedMotion, activeSource }) {
  const pathLength = useTransform(progress, source.range, [0, 1]);
  const dimmed = activeSource && activeSource !== source.label;

  return (
    <motion.path
      className={dimmed ? "is-dimmed" : activeSource === source.label ? "is-active" : ""}
      data-source={source.label.toLowerCase()}
      d={source.path}
      style={reducedMotion ? { pathLength: 1 } : { pathLength }}
    />
  );
}

export function ConvergenceFocusScene() {
  const ref = useRef(null);
  const [activeSource, setActiveSource] = useState(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const progress = useSpring(scrollYProgress, { stiffness: 96, damping: 27, mass: 0.8 });
  const eyebrowOpacity = useTransform(progress, [0.68, 0.74], [0, 1]);
  const eyebrowY = useTransform(progress, [0.68, 0.74], [12, 0]);
  const lineOneOpacity = useTransform(progress, [0.72, 0.76], [0, 1]);
  const lineTwoOpacity = useTransform(progress, [0.75, 0.8], [0, 1]);
  const lineThreeOpacity = useTransform(progress, [0.79, 0.84], [0, 1]);
  const noteOpacity = useTransform(progress, [0.82, 0.86], [0, 1]);

  return (
    <section
      className="visual-scene convergence-scene"
      data-header-theme="dark"
      data-nav-label="Research"
      data-scene="focus"
      id="how-it-works"
      ref={ref}
    >
      <div className="convergence-scene__sticky">
        <div className="page-frame convergence-scene__inner">
          <header className="convergence-scene__headline">
            <p className="technical-label">Focus</p>
            <h2>MARKET NOISE,<br /><span>BROUGHT INTO FOCUS.</span></h2>
          </header>

          <div className="convergence-field" data-qa="convergence-field">
            <svg aria-hidden="true" className="convergence-field__paths" viewBox="0 0 1100 600">
              {sources.map((source) => (
                <ConvergencePath
                  activeSource={activeSource}
                  key={source.label}
                  progress={progress}
                  reducedMotion={reducedMotion}
                  source={source}
                />
              ))}
            </svg>

            {sources.map((source) => (
              <button
                className={`convergence-label ${source.className}`}
                key={source.label}
                onBlur={() => setActiveSource(null)}
                onFocus={() => setActiveSource(source.label)}
                onMouseEnter={() => setActiveSource(source.label)}
                onMouseLeave={() => setActiveSource(null)}
                type="button"
              >
                {source.label}
              </button>
            ))}

            <div className="convergence-output-anchor">
              <div className="convergence-output">
                <motion.span
                  className="technical-label"
                  style={reducedMotion ? undefined : { opacity: eyebrowOpacity, y: eyebrowY }}
                >Why it matters</motion.span>
                <p data-qa="convergence-copy">
                  <motion.span style={reducedMotion ? undefined : { opacity: lineOneOpacity }}>When price, participation</motion.span>
                  <motion.span style={reducedMotion ? undefined : { opacity: lineTwoOpacity }}>and events move together,</motion.span>
                  <motion.span style={reducedMotion ? undefined : { opacity: lineThreeOpacity }}>the change becomes easier to inspect.</motion.span>
                </p>
                <motion.small style={reducedMotion ? undefined : { opacity: noteOpacity }}>Context—not a recommendation.</motion.small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export const ConvergenceScene = ConvergenceFocusScene;

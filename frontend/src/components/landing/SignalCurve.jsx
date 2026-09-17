import { motion, useReducedMotion } from "motion/react";

const heroPath = "M18 194 C126 88 214 194 324 128 S516 86 704 58";

export function SignalCurve({
  arrowOpacity,
  className = "",
  dataQa,
  delay = 0.48,
  opacity,
  path = heroPath,
  pathLength,
  staticPath = false,
  viewBox = "0 0 720 260",
}) {
  const reducedMotion = useReducedMotion();
  const controlled = pathLength !== undefined;
  const immediate = reducedMotion || staticPath;

  return (
    <motion.svg
      aria-hidden="true"
      className={`signal-curve ${className}`.trim()}
      data-qa={dataQa}
      style={opacity === undefined ? undefined : { opacity }}
      viewBox={viewBox}
    >
      <motion.path
        animate={controlled ? undefined : { opacity: 1, pathLength: 1 }}
        d={path}
        fill="none"
        initial={controlled ? false : immediate ? { opacity: 1, pathLength: 1 } : { opacity: 0.25, pathLength: 0 }}
        style={controlled ? { opacity: 1, pathLength } : undefined}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        transition={{ duration: immediate ? 0 : 0.82, delay: immediate ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
        vectorEffect="non-scaling-stroke"
      />
      <motion.path
        animate={controlled ? undefined : { opacity: 1 }}
        className="signal-curve__arrow"
        d="M688 54 L706 64 L691 77"
        fill="none"
        initial={controlled ? false : { opacity: immediate ? 1 : 0 }}
        style={controlled ? { opacity: arrowOpacity ?? pathLength } : undefined}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        transition={{ duration: immediate ? 0 : 0.2, delay: immediate ? 0 : delay + 0.74 }}
        vectorEffect="non-scaling-stroke"
      />
    </motion.svg>
  );
}

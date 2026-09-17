import { motion, useReducedMotion } from "motion/react";

const defaultLines = ["SEE THE MARKET.", "UNDERSTAND", "THE SIGNAL."];
const compactLines = ["SEE THE MARKET.", "UNDERSTAND THE SIGNAL."];

function AnimatedLines({ lines, reducedMotion, variant }) {
  return (
    <span className={`kinetic-headline__variant kinetic-headline__variant--${variant}`}>
      {lines.map((line, index) => (
        <span aria-hidden="true" className="kinetic-headline__mask" key={`${variant}-${line}`}>
          <motion.span
            animate={{ y: "0%" }}
            className={index === lines.length - 1 ? "kinetic-headline__line kinetic-headline__line--signal" : "kinetic-headline__line"}
            initial={reducedMotion ? { y: "0%" } : { y: "112%" }}
            transition={{ duration: reducedMotion ? 0 : 0.72, delay: reducedMotion ? 0 : 0.42 + index * 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            {line}
          </motion.span>
        </span>
      ))}
    </span>
  );
}

export function KineticHeadline({ lines = defaultLines, className = "" }) {
  const reducedMotion = useReducedMotion();
  const label = lines.join(" ");

  return (
    <h1 aria-label={label} className={`kinetic-headline display-type ${className}`.trim()}>
      <AnimatedLines lines={lines} reducedMotion={reducedMotion} variant="wide" />
      <AnimatedLines lines={compactLines} reducedMotion={reducedMotion} variant="compact" />
      <AnimatedLines lines={lines} reducedMotion={reducedMotion} variant="stacked" />
    </h1>
  );
}

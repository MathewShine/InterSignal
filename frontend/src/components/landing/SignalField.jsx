import { motion, useReducedMotion } from "motion/react";

export function SignalField() {
  const reducedMotion = useReducedMotion();

  return (
    <motion.div
      animate={{ clipPath: "polygon(0 0, 100% 0, 100% 44%, 92% 67%, 92% 100%, 0 100%)" }}
      aria-hidden="true"
      className="signal-field"
      initial={reducedMotion ? false : { clipPath: "polygon(0 0, 0 0, 0 44%, 0 67%, 0 100%, 0 100%)" }}
      transition={{ duration: reducedMotion ? 0 : 0.82, delay: reducedMotion ? 0 : 0.12, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="signal-field__disc" />
      <span className="signal-field__ticks" />
    </motion.div>
  );
}

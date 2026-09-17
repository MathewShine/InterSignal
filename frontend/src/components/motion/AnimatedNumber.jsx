import { useEffect } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";

export function AnimatedNumber({ value, format = (number) => Math.round(number).toString(), className = "" }) {
  const reducedMotion = useReducedMotion();
  const source = useMotionValue(reducedMotion ? value : 0);
  const spring = useSpring(source, { stiffness: 110, damping: 24, mass: 0.5 });
  const display = useTransform(spring, (latest) => format(latest));

  useEffect(() => {
    source.set(value);
  }, [source, value]);

  return (
    <span aria-label={format(value)} className={className}>
      <motion.span aria-hidden="true">{reducedMotion ? format(value) : display}</motion.span>
    </span>
  );
}

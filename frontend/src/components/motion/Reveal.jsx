import { motion } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function Reveal({ children, delay = 0, distance = 10, className = "", as = "div", once = true }) {
  const { reducedMotion } = useMotionPreference();
  const Component = motion[as] ?? motion.div;
  return (
    <Component
      className={`motion-reveal ${className}`.trim()}
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: distance }}
      transition={{ duration: reducedMotion ? 0.12 : 0.52, delay, ease: [0.22, 1, 0.36, 1] }}
      viewport={{ once, amount: 0.22 }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      {children}
    </Component>
  );
}

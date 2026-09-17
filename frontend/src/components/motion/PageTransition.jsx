import { motion } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function PageTransition({ children, className = "" }) {
  const { reducedMotion } = useMotionPreference();
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={className}
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 10 }}
      transition={{ duration: reducedMotion ? 0.12 : 0.48, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

import { useRef } from "react";
import { motion, useScroll, useSpring, useTransform } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function ParallaxLayer({ children, className = "", distance = 18 }) {
  const ref = useRef(null);
  const { reducedMotion } = useMotionPreference();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const rawY = useTransform(scrollYProgress, [0, 1], [-distance, distance]);
  const y = useSpring(rawY, { stiffness: 120, damping: 28, mass: 0.4 });

  return (
    <motion.div
      className={`parallax-layer ${className}`.trim()}
      ref={ref}
      style={reducedMotion ? undefined : { y }}
    >
      {children}
    </motion.div>
  );
}

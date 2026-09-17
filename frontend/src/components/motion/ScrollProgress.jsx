import { motion, useScroll, useSpring } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function ScrollProgress() {
  const { reducedMotion } = useMotionPreference();
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 150, damping: 32, mass: 0.32 });
  if (reducedMotion) return null;
  return <motion.div aria-hidden="true" className="scroll-progress" style={{ scaleX }} />;
}

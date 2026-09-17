import { motion } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function Stagger({ children, className = "", as = "div" }) {
  const { reducedMotion } = useMotionPreference();
  const Component = motion[as] ?? motion.div;
  return (
    <Component
      className={className}
      initial="hidden"
      variants={{
        hidden: {},
        visible: {
          transition: { staggerChildren: reducedMotion ? 0 : 0.075 },
        },
      }}
      viewport={{ once: true, amount: 0.18 }}
      whileInView="visible"
    >
      {children}
    </Component>
  );
}

export function StaggerItem({ children, className = "" }) {
  const { reducedMotion } = useMotionPreference();
  return (
    <motion.div
      className={className}
      variants={{
        hidden: reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 },
        visible: {
          opacity: 1,
          y: 0,
          transition: { duration: reducedMotion ? 0.1 : 0.4, ease: [0.22, 1, 0.36, 1] },
        },
      }}
    >
      {children}
    </motion.div>
  );
}

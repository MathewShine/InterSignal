import { motion } from "motion/react";
import { useMotionPreference } from "./MotionProvider.jsx";

export function SharedSurface({ layoutId, children, className = "", as = "div", ...props }) {
  const { reducedMotion } = useMotionPreference();
  const Component = motion[as] ?? motion.div;
  return (
    <Component
      className={className}
      layout={reducedMotion ? false : true}
      layoutId={reducedMotion ? undefined : layoutId}
      transition={{ layout: { type: "spring", stiffness: 360, damping: 38 } }}
      {...props}
    >
      {children}
    </Component>
  );
}

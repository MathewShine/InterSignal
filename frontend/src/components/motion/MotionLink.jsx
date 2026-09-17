import { motion, useReducedMotion } from "motion/react";
import { ArrowRightIcon } from "../icons/Icons.jsx";

export function MotionLink({ children, href, className = "", ...props }) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.a
      className={`motion-link ${className}`.trim()}
      href={href}
      transition={{ duration: 0.16 }}
      whileTap={reducedMotion ? undefined : { y: 1 }}
      {...props}
    >
      <span>{children}</span>
      <ArrowRightIcon className="motion-link__arrow" size={14} />
    </motion.a>
  );
}

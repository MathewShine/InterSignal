import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";

export function MagneticAction({ children, className = "" }) {
  const reducedMotion = useReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 280, damping: 28, mass: 0.45 });
  const springY = useSpring(y, { stiffness: 280, damping: 28, mass: 0.45 });

  function handlePointerMove(event) {
    if (reducedMotion || !window.matchMedia("(pointer: fine)").matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    x.set(((event.clientX - bounds.left) / bounds.width - 0.5) * 6);
    y.set(((event.clientY - bounds.top) / bounds.height - 0.5) * 6);
  }

  function reset() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.div
      className={`magnetic-action ${className}`.trim()}
      onPointerLeave={reset}
      onPointerMove={handlePointerMove}
      style={reducedMotion ? undefined : { x: springX, y: springY }}
    >
      {children}
    </motion.div>
  );
}

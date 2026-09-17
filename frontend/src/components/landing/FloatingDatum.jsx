import { useEffect, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";

export function FloatingDatum({ label, value, detail, className = "", delay = 0.84, parallax = false }) {
  const reducedMotion = useReducedMotion();
  const [pointerEnabled, setPointerEnabled] = useState(false);
  const xValue = useMotionValue(0);
  const yValue = useMotionValue(0);
  const x = useSpring(xValue, { stiffness: 115, damping: 24, mass: 0.72 });
  const y = useSpring(yValue, { stiffness: 115, damping: 24, mass: 0.72 });

  useEffect(() => {
    const query = window.matchMedia("(pointer: fine) and (min-width: 1024px)");
    const update = () => setPointerEnabled(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  function move(event) {
    if (!parallax || reducedMotion || !pointerEnabled) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    xValue.set((((event.clientX - bounds.left) / bounds.width) - 0.5) * 6);
    yValue.set((((event.clientY - bounds.top) / bounds.height) - 0.5) * 6);
  }

  function reset() {
    xValue.set(0);
    yValue.set(0);
  }

  const interactive = parallax && pointerEnabled && !reducedMotion;

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className={`floating-datum ${className}`.trim()}
      data-datum={label.toLowerCase().replaceAll(" ", "-")}
      initial={reducedMotion ? false : { opacity: 0 }}
      onPointerLeave={interactive ? reset : undefined}
      onPointerMove={interactive ? move : undefined}
      style={interactive ? { x, y } : undefined}
      transition={{ duration: reducedMotion ? 0 : 0.36, delay: reducedMotion ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="datum-label">{label}</span>
      <strong className="datum-value">{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </motion.div>
  );
}

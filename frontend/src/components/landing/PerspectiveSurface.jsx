import { useEffect, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import { ContextCursor } from "./ContextCursor.jsx";

const intensityMap = {
  main: { translate: 6, rotate: 0.8 },
  supporting: { translate: 8, rotate: 1.1 },
};

export function PerspectiveSurface({
  children,
  className = "",
  cursorLabel = "Inspect",
  delay = 0.42,
  duration = 0.72,
  intensity = "main",
}) {
  const reducedMotion = useReducedMotion();
  const [pointerEnabled, setPointerEnabled] = useState(false);
  const xValue = useMotionValue(0);
  const yValue = useMotionValue(0);
  const rotateXValue = useMotionValue(0);
  const rotateYValue = useMotionValue(0);
  const x = useSpring(xValue, { stiffness: 110, damping: 25, mass: 0.8 });
  const y = useSpring(yValue, { stiffness: 110, damping: 25, mass: 0.8 });
  const rotateX = useSpring(rotateXValue, { stiffness: 105, damping: 25, mass: 0.8 });
  const rotateY = useSpring(rotateYValue, { stiffness: 105, damping: 25, mass: 0.8 });
  const limits = intensityMap[intensity] ?? intensityMap.main;

  useEffect(() => {
    const query = window.matchMedia("(pointer: fine) and (min-width: 1024px)");
    const update = () => setPointerEnabled(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  function onPointerMove(event) {
    if (reducedMotion || !pointerEnabled) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const horizontal = (event.clientX - bounds.left) / bounds.width - 0.5;
    const vertical = (event.clientY - bounds.top) / bounds.height - 0.5;
    xValue.set(horizontal * limits.translate * 2);
    yValue.set(vertical * limits.translate * 2);
    rotateYValue.set(horizontal * limits.rotate * 2);
    rotateXValue.set(vertical * limits.rotate * -2);
  }

  function reset() {
    xValue.set(0);
    yValue.set(0);
    rotateXValue.set(0);
    rotateYValue.set(0);
  }

  const interactive = pointerEnabled && !reducedMotion;

  return (
    <ContextCursor className={`perspective-surface ${className}`.trim()} label={cursorLabel}>
      <motion.div
        animate={{ opacity: 1, x: 0, y: 0 }}
        className="perspective-surface__entry"
        initial={reducedMotion ? false : { opacity: 0, x: 34, y: 46 }}
        transition={{ duration: reducedMotion ? 0 : duration, delay: reducedMotion ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      >
        <motion.div
          className="perspective-surface__responsive"
          onPointerLeave={interactive ? reset : undefined}
          onPointerMove={interactive ? onPointerMove : undefined}
          style={interactive ? { rotateX, rotateY, x, y } : undefined}
        >
          <div className="perspective-surface__base">{children}</div>
        </motion.div>
      </motion.div>
    </ContextCursor>
  );
}

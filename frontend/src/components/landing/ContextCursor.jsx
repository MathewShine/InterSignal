import { useEffect, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";

export function ContextCursor({ children, label = "Inspect", className = "" }) {
  const reducedMotion = useReducedMotion();
  const [finePointer, setFinePointer] = useState(false);
  const [visible, setVisible] = useState(false);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const x = useSpring(pointerX, { stiffness: 720, damping: 48, mass: 0.24 });
  const y = useSpring(pointerY, { stiffness: 720, damping: 48, mass: 0.24 });

  useEffect(() => {
    const query = window.matchMedia("(pointer: fine) and (min-width: 1024px)");
    const update = () => setFinePointer(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  function move(event) {
    if (reducedMotion || !finePointer) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    pointerX.set(event.clientX - bounds.left + 14);
    pointerY.set(event.clientY - bounds.top + 14);
  }

  const enabled = finePointer && !reducedMotion;

  return (
    <div
      className={`context-cursor-zone ${className}`.trim()}
      onPointerEnter={() => enabled && setVisible(true)}
      onPointerLeave={() => setVisible(false)}
      onPointerMove={move}
    >
      {children}
      {enabled ? (
        <motion.span
          animate={{ opacity: visible ? 1 : 0 }}
          aria-hidden="true"
          className="context-cursor"
          style={{ x, y }}
          transition={{ duration: 0.08 }}
        >
          {label}
        </motion.span>
      ) : null}
    </div>
  );
}

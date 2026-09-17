import { createContext, useContext, useMemo } from "react";
import { MotionConfig, useReducedMotion } from "motion/react";

const MotionPreferenceContext = createContext({ reducedMotion: false });

export function MotionProvider({ children, reducedMotionOverride }) {
  const systemReducedMotion = useReducedMotion();
  const reducedMotion = reducedMotionOverride ?? Boolean(systemReducedMotion);
  const value = useMemo(() => ({ reducedMotion }), [reducedMotion]);

  return (
    <MotionPreferenceContext.Provider value={value}>
      <MotionConfig reducedMotion={reducedMotion ? "always" : "never"}>
        <div data-reduced-motion={reducedMotion ? "true" : "false"}>{children}</div>
      </MotionConfig>
    </MotionPreferenceContext.Provider>
  );
}

export function useMotionPreference() {
  return useContext(MotionPreferenceContext);
}

import { useEffect, useState } from "react";

const DEFAULT_STATE = { navLabel: "Product", scene: "signal", surface: "light", theme: "light" };

function area(entry) {
  if (entry.intersectionRect) {
    return entry.intersectionRect.width * entry.intersectionRect.height;
  }
  return entry.intersectionRatio ?? (entry.isIntersecting ? 1 : 0);
}

export function useHeaderThemeController() {
  const [headerState, setHeaderState] = useState(DEFAULT_STATE);

  useEffect(() => {
    if (!("IntersectionObserver" in window)) return undefined;

    const entriesByElement = new Map();
    const observed = new Set();
    let frame = 0;

    function publish() {
      frame = 0;
      const visible = [...entriesByElement.values()]
        .filter((entry) => entry.isIntersecting && area(entry) > 0)
        .sort((left, right) => area(right) - area(left))[0];

      if (!visible) return;
      const target = visible.target;
      setHeaderState((current) => {
        const next = {
          navLabel: target.dataset.navLabel || current.navLabel,
          scene: target.dataset.scene || target.dataset.transition || "unknown",
          surface: target.dataset.headerSurface || target.dataset.headerTheme || "light",
          theme: target.dataset.headerTheme || "light",
        };
        return current.theme === next.theme
          && current.scene === next.scene
          && current.surface === next.surface
          && current.navLabel === next.navLabel
          ? current
          : next;
      });
    }

    function schedulePublish() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(publish);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => entriesByElement.set(entry.target, entry));
        schedulePublish();
      },
      {
        rootMargin: "0px 0px -88% 0px",
        threshold: [0, 0.001, 0.01, 0.025, 0.05, 0.1],
      },
    );

    function observeScenes() {
      document.querySelectorAll("[data-header-theme]").forEach((element) => {
        if (observed.has(element)) return;
        observed.add(element);
        observer.observe(element);
      });
    }

    observeScenes();
    const mutationObserver = new MutationObserver(observeScenes);
    mutationObserver.observe(document.body, { childList: true, subtree: true });

    return () => {
      cancelAnimationFrame(frame);
      mutationObserver.disconnect();
      observer.disconnect();
    };
  }, []);

  return headerState;
}

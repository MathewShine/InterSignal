import { LayoutGroup, motion, useReducedMotion } from "motion/react";

export function Tabs({ items, value, onChange, label }) {
  const reducedMotion = useReducedMotion();

  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? items.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    onChange(items[nextIndex].value);
    event.currentTarget.parentElement
      ?.querySelectorAll('[role="tab"]')
      [nextIndex]?.focus();
  }

  return (
    <LayoutGroup id={`tabs-${label.replace(/\s+/g, "-").toLowerCase()}`}>
      <div aria-label={label} className="tabs" role="tablist">
        {items.map((item, index) => {
          const active = item.value === value;
          return (
            <button
              aria-selected={active}
              className={`tab ${active ? "is-active" : ""}`}
              key={item.value}
              onClick={() => onChange(item.value)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              role="tab"
              tabIndex={active ? 0 : -1}
              type="button"
            >
              <span>{item.label}</span>
              {active ? (
                <motion.span
                  className="tab__indicator"
                  layoutId="tab-indicator"
                  transition={reducedMotion ? { duration: 0.08 } : { type: "spring", stiffness: 420, damping: 38 }}
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}

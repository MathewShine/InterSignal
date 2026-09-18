import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { BrandMark } from "../../../components/brand/BrandMark.jsx";
import { useMotionPreference } from "../../../components/motion/index.js";
import { AppIcon } from "./AppIcon.jsx";
import { primaryNavigation, secondaryNavigation, utilityNavigation } from "./appNavigation.js";

function RailLink({ item, expanded }) {
  return (
    <NavLink
      aria-label={item.label}
      className={({ isActive }) => `app-rail__link${isActive ? " is-active" : ""}`}
      end={item.path === "/app"}
      to={item.path}
    >
      <span className="app-rail__active-mark" />
      <AppIcon name={item.icon} />
      <motion.span
        animate={{ opacity: expanded ? 1 : 0, x: expanded ? 0 : -5 }}
        aria-hidden={!expanded}
        className="app-rail__label"
        transition={{ duration: 0.18 }}
      >
        {item.label}
      </motion.span>
    </NavLink>
  );
}

export function AppRail({ onExpandedChange }) {
  const { reducedMotion } = useMotionPreference();
  const [expanded, setExpanded] = useState(false);
  const collapseTimer = useRef(null);

  const cancelCollapse = () => {
    if (collapseTimer.current) window.clearTimeout(collapseTimer.current);
    collapseTimer.current = null;
  };

  const openRail = () => {
    cancelCollapse();
    setExpanded(true);
  };

  const scheduleCollapse = () => {
    cancelCollapse();
    collapseTimer.current = window.setTimeout(() => setExpanded(false), reducedMotion ? 0 : 190);
  };

  useEffect(() => {
    onExpandedChange?.(expanded);
  }, [expanded, onExpandedChange]);

  useEffect(() => () => cancelCollapse(), []);

  return (
    <aside
      aria-label="Application navigation"
      className="app-rail"
      data-expanded={expanded ? "true" : "false"}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) scheduleCollapse();
      }}
      onFocus={openRail}
      onMouseEnter={openRail}
      onMouseLeave={scheduleCollapse}
    >
      <NavLink aria-label="InterSignal Home" className="app-rail__brand" to="/app">
        <BrandMark compact />
        <motion.span animate={{ opacity: expanded ? 1 : 0 }} className="app-rail__brand-word">InterSignal</motion.span>
      </NavLink>
      <nav aria-label="Primary app" className="app-rail__nav">
        {primaryNavigation.map((item) => <RailLink expanded={expanded} item={item} key={item.id} />)}
      </nav>
      <div className="app-rail__divider" />
      <nav aria-label="Secondary app" className="app-rail__nav app-rail__nav--secondary">
        {secondaryNavigation.map((item) => <RailLink expanded={expanded} item={item} key={item.id} />)}
      </nav>
      <nav aria-label="Account" className="app-rail__nav app-rail__nav--utility">
        {utilityNavigation.map((item) => <RailLink expanded={expanded} item={item} key={item.id} />)}
      </nav>
    </aside>
  );
}

export function MobileAppNav() {
  const mobileItems = [...primaryNavigation.slice(0, 4), { id: "more", label: "More", path: "/app/alerts", icon: "more" }];
  return (
    <nav aria-label="Mobile app" className="mobile-app-nav">
      {mobileItems.map((item) => (
        <NavLink
          aria-label={item.label}
          className={({ isActive }) => `mobile-app-nav__link${isActive ? " is-active" : ""}`}
          end={item.path === "/app"}
          key={item.id}
          to={item.path}
        >
          <AppIcon name={item.icon} size={19} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

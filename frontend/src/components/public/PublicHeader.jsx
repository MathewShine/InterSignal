import { useEffect, useState } from "react";
import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";
import { BrandMark } from "../brand/BrandMark.jsx";
import { CloseIcon, MenuIcon } from "../icons/Icons.jsx";
import { IconButton, PrimaryAction } from "../ui/Actions.jsx";
import { useHeaderThemeController } from "./HeaderThemeController.jsx";

const primaryNavigation = [
  ["Product", "#product"],
  ["Research", "#research"],
  ["Invest", "#invest"],
  ["Trade", "#trade"],
];

const secondaryNavigation = [
  ["Invest", "#invest"],
  ["Trade", "#trade"],
  ["Company", "#company"],
];

export function PublicHeader() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [materialized, setMaterialized] = useState(false);
  const [hoveredItem, setHoveredItem] = useState(null);
  const { navLabel: activeItem, scene: activeScene, surface, theme } = useHeaderThemeController();
  const reducedMotion = useReducedMotion();
  const { scrollY } = useScroll();

  useMotionValueEvent(scrollY, "change", (value) => {
    const next = value > 72;
    setMaterialized((current) => (current === next ? current : next));
  });

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        setMoreOpen(false);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  const underlinedItem = hoveredItem ?? activeItem;

  return (
    <header
      className={`public-header ${materialized ? "is-materialized" : ""} theme-${surface}`}
      data-active-scene={activeScene}
      data-materialized={materialized ? "true" : "false"}
      data-surface={surface}
      data-theme={theme}
    >
      <motion.div className="public-header__material" layout={!reducedMotion}>
        <div className="public-header__inner">
          <a aria-label="InterSignal home" className="public-header__brand" href="#top">
            <BrandMark />
          </a>

          <nav
            aria-label="Primary navigation"
            className="public-header__nav"
            onMouseLeave={() => setHoveredItem(null)}
          >
            {primaryNavigation.map(([label, href]) => (
              <a
                aria-current={activeItem === label ? "location" : undefined}
                data-nav-item={label.toLowerCase()}
                href={href}
                key={label}
                onBlur={() => setHoveredItem(null)}
                onFocus={() => setHoveredItem(label)}
                onMouseEnter={() => setHoveredItem(label)}
              >
                {label}
                {underlinedItem === label ? (
                  <motion.span className="public-header__underline" layoutId="public-nav-underline" />
                ) : null}
              </a>
            ))}
            <button
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              className="public-header__more"
              onClick={() => setMoreOpen((open) => !open)}
              type="button"
            >
              More <span aria-hidden="true">+</span>
            </button>
          </nav>

          <div className="public-header__actions">
            <a className="sign-in-link" href="/auth?mode=signin">Sign in</a>
            <PrimaryAction href="#product">Explore InterSignal</PrimaryAction>
          </div>

          <a className="public-header__mobile-explore" href="#product">Explore</a>
          <IconButton
            aria-controls="mobile-navigation"
            aria-expanded={menuOpen}
            className="public-header__menu-button"
            label={menuOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </IconButton>
        </div>
      </motion.div>

      <AnimatePresence>
        {moreOpen ? (
          <motion.nav
            animate={{ opacity: 1, y: 0 }}
            aria-label="More navigation"
            className="more-navigation"
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -6 }}
            transition={{ duration: reducedMotion ? 0 : 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            {secondaryNavigation.map(([label, href]) => (
              <a href={href} key={label} onClick={() => setMoreOpen(false)}>{label}</a>
            ))}
          </motion.nav>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {menuOpen ? (
          <motion.nav
            animate={{ opacity: 1, y: 0 }}
            aria-label="Mobile navigation"
            className="mobile-navigation"
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
            id="mobile-navigation"
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, y: -8 }}
            transition={{ duration: reducedMotion ? 0 : 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            {[...primaryNavigation, ["Company", "#company"]].map(([label, href]) => (
              <a href={href} key={label} onClick={() => setMenuOpen(false)}>{label}</a>
            ))}
            <a href="/auth?mode=signin" onClick={() => setMenuOpen(false)}>Sign in</a>
          </motion.nav>
        ) : null}
      </AnimatePresence>
    </header>
  );
}

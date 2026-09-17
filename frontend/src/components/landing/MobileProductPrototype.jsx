import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BrandMark } from "../brand/BrandMark.jsx";
import { useMotionPreference } from "../motion/MotionProvider.jsx";
import { DemoBadge } from "../ui/DataDisplay.jsx";

const SCREEN_ORDER = ["market", "portfolio", "research"];
const NAVIGATION_ITEMS = [
  { label: "Home", screen: null },
  { label: "Market", screen: "market" },
  { label: "Portfolio", screen: "portfolio" },
  { label: "Research", screen: "research" },
];

const DESKTOP_DWELL_MS = 3200;
const MOBILE_DWELL_MS = 3500;
const ENTRANCE_SEQUENCE_MS = 2200;
const MANUAL_PAUSE_MS = 8000;

function MarketScreen() {
  return (
    <div className="mobile-screen mobile-screen--market">
      <div className="mobile-prototype__context">
        <span className="technical-label">Market intelligence</span>
        <strong>NIFTY 500</strong>
      </div>

      <section className="mobile-prototype__insight" aria-label="Illustrative market insight">
        <span>Primary insight</span>
        <strong className="mobile-prototype__insight-title">Momentum<br />broadening</strong>
        <div><span>Breadth</span><b>61%</b></div>
      </section>

      <svg aria-label="Illustrative market trajectory" className="mobile-prototype__chart" role="img" viewBox="0 0 260 118">
        <path className="mobile-prototype__grid" d="M0 32H260 M0 72H260 M0 112H260" />
        <path className="mobile-prototype__area" d="M0 101 C38 94 46 104 78 80 S127 78 154 53 S202 59 260 17 V118 H0Z" />
        <path className="mobile-prototype__line" d="M0 101 C38 94 46 104 78 80 S127 78 154 53 S202 59 260 17" />
        <circle cx="260" cy="17" r="4" />
      </svg>

      <div className="mobile-prototype__signals">
        <div><span>Portfolio context</span><b>Exposure 24%</b></div>
        <div><span>Research context</span><b>Evidence available</b></div>
      </div>
    </div>
  );
}

function PortfolioScreen() {
  return (
    <div className="mobile-screen mobile-screen--portfolio">
      <div className="mobile-screen__heading">
        <span className="technical-label">Portfolio</span>
        <DemoBadge>Demo portfolio</DemoBadge>
      </div>
      <div className="mobile-portfolio__value">
        <span>Illustrative value</span>
        <strong>₹4,82,000</strong>
      </div>
      <div className="mobile-portfolio__allocation" aria-label="Illustrative allocation">
        <span className="mobile-portfolio__equity" />
        <span className="mobile-portfolio__cash" />
        <span className="mobile-portfolio__other" />
      </div>
      <dl className="mobile-screen__metrics">
        <div><dt>Equity exposure</dt><dd>71%</dd></div>
        <div><dt>Cash</dt><dd>12%</dd></div>
        <div><dt>Portfolio context</dt><dd>Balanced</dd></div>
      </dl>
      <p className="mobile-screen__disclaimer">Illustrative data. No recommendation.</p>
    </div>
  );
}

function ResearchScreen() {
  return (
    <div className="mobile-screen mobile-screen--research">
      <span className="technical-label">Research</span>
      <div className="mobile-research__question">
        <span>Current question</span>
        <strong>Is participation<br />broadening?</strong>
      </div>
      <dl className="mobile-screen__metrics">
        <div><dt>Evidence</dt><dd>Captured</dd></div>
        <div><dt>Context</dt><dd>Changing</dd></div>
        <div><dt>Review</dt><dd>Open</dd></div>
      </dl>
      <div aria-label="Evidence timeline" className="mobile-research__timeline">
        <span className="is-complete"><i />Observe</span>
        <span className="is-complete"><i />Compare</span>
        <span><i />Review</span>
      </div>
    </div>
  );
}

const screenComponents = {
  market: MarketScreen,
  portfolio: PortfolioScreen,
  research: ResearchScreen,
};

function enterState(screen, reducedMotion) {
  if (reducedMotion) return { opacity: 0 };
  if (screen === "portfolio") return { opacity: 0, x: 26 };
  if (screen === "research") return { opacity: 0, y: 22 };
  return { opacity: 0, x: 18, y: 10 };
}

function exitState(screen, reducedMotion) {
  if (reducedMotion) return { opacity: 0 };
  if (screen === "market") return { opacity: 0, scale: 0.985, x: -20 };
  if (screen === "portfolio") return { opacity: 0, y: -18 };
  return { opacity: 0, scale: 0.98 };
}

export function MobileProductPrototype() {
  const articleRef = useRef(null);
  const entranceComplete = useRef(false);
  const { reducedMotion } = useMotionPreference();
  const [activeScreen, setActiveScreen] = useState("market");
  const [visible, setVisible] = useState(false);
  const [documentVisible, setDocumentVisible] = useState(() => !document.hidden);
  const [mobileMode, setMobileMode] = useState(false);
  const [manualPauseUntil, setManualPauseUntil] = useState(0);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 47.9375rem)");
    const update = () => setMobileMode(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  useEffect(() => {
    const onVisibilityChange = () => setDocumentVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    const element = articleRef.current;
    if (!element) return undefined;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return undefined;
    }

    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting && entry.intersectionRatio >= (mobileMode ? 0.7 : 0.5)),
      { threshold: [0, 0.5, 0.7, 1] },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [mobileMode]);

  useEffect(() => {
    if (reducedMotion || !visible || !documentVisible) return undefined;

    const now = Date.now();
    const dwell = mobileMode ? MOBILE_DWELL_MS : DESKTOP_DWELL_MS;
    const manualWait = Math.max(0, manualPauseUntil - now);
    const entranceWait = entranceComplete.current ? 0 : ENTRANCE_SEQUENCE_MS;
    const timer = window.setTimeout(() => {
      entranceComplete.current = true;
      setActiveScreen((current) => SCREEN_ORDER[(SCREEN_ORDER.indexOf(current) + 1) % SCREEN_ORDER.length]);
    }, Math.max(manualWait, entranceWait) + dwell);

    return () => window.clearTimeout(timer);
  }, [activeScreen, documentVisible, manualPauseUntil, mobileMode, reducedMotion, visible]);

  function selectScreen(screen) {
    if (!screen || screen === activeScreen) return;
    entranceComplete.current = true;
    setActiveScreen(screen);
    setManualPauseUntil(Date.now() + MANUAL_PAUSE_MS);
  }

  const ActiveScreen = screenComponents[activeScreen];
  const transitionDuration = reducedMotion ? 0.12 : mobileMode ? 0.5 : 0.7;

  return (
    <article
      aria-label="InterSignal mobile market intelligence prototype"
      className="mobile-prototype"
      data-active-screen={activeScreen}
      data-qa="hero-mobile-prototype"
      ref={articleRef}
    >
      <header className="mobile-prototype__header">
        <BrandMark />
        <DemoBadge>Prototype</DemoBadge>
      </header>

      <div aria-live="polite" className="mobile-prototype__deck">
        <AnimatePresence initial={false} mode="sync">
          <motion.div
            animate={{ opacity: 1, scale: 1, x: 0, y: 0 }}
            aria-labelledby={`prototype-tab-${activeScreen}`}
            className="mobile-prototype__panel"
            data-qa={`mobile-screen-${activeScreen}`}
            exit={exitState(activeScreen, reducedMotion)}
            initial={enterState(activeScreen, reducedMotion)}
            key={activeScreen}
            role="tabpanel"
            transition={{ duration: transitionDuration, ease: [0.22, 1, 0.36, 1] }}
          >
            <ActiveScreen />
          </motion.div>
        </AnimatePresence>
      </div>

      <nav aria-label="Prototype navigation" className="mobile-prototype__nav" role="tablist">
        {NAVIGATION_ITEMS.map((item) => {
          const selected = item.screen === activeScreen;
          return (
            <button
              aria-disabled={item.screen ? undefined : "true"}
              aria-selected={selected}
              className={selected ? "is-active" : ""}
              id={item.screen ? `prototype-tab-${item.screen}` : undefined}
              key={item.label}
              onClick={() => selectScreen(item.screen)}
              role="tab"
              tabIndex={item.screen ? 0 : -1}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </nav>
    </article>
  );
}

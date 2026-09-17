import { BrandMark } from "../../../components/brand/BrandMark.jsx";
import { AppIcon } from "./AppIcon.jsx";

export function HomeContextBar({ area, onOpenCommand, onOpenDrawer }) {
  return (
    <header className="app-context-bar">
      <div className="app-context-bar__mobile-brand"><BrandMark /></div>
      <div className="app-context-bar__area">
        <span className="technical-label">Current area</span>
        <strong>{area}</strong>
      </div>
      <button aria-label="Open command palette" className="app-search-trigger" onClick={onOpenCommand} type="button">
        <AppIcon name="search" size={17} />
        <span>Search research, portfolios, evidence…</span>
        <kbd><span className="app-search-trigger__mac">⌘ K</span><span className="app-search-trigger__windows">Ctrl K</span></kbd>
      </button>
      <div className="app-context-bar__status">
        <div><span>Market context</span><strong>Illustrative</strong></div>
        <div><span>Data freshness</span><strong>Local snapshot</strong></div>
      </div>
      <button aria-label="Open contextual drawer" className="app-icon-button" onClick={onOpenDrawer} type="button">
        <AppIcon name="alerts" size={19} />
        <span className="app-icon-button__indicator" />
      </button>
      <div aria-label="Prototype profile" className="app-profile-mark">IS</div>
    </header>
  );
}

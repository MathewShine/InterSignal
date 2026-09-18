import { BrandMark } from "../../../components/brand/BrandMark.jsx";
import { AppIcon } from "./AppIcon.jsx";

const quietStateLabels = {
  CONNECTING: "Refreshing information",
  DISCONNECTED: "Some information is unavailable",
  ERROR: "Some information is unavailable",
  PARTIAL: "Some information is partially available",
};

export function HomeContextBar({ area, connectionState, onOpenCommand, onOpenDrawer }) {
  const quietState = quietStateLabels[connectionState];
  return (
    <header className="app-context-bar">
      <div className="app-context-bar__mobile-brand"><BrandMark /></div>
      <strong className="app-context-bar__area">{area}</strong>
      <button aria-label="Open command palette" className="app-search-trigger" onClick={onOpenCommand} type="button">
        <AppIcon name="search" size={17} />
        <span>Search InterSignal</span>
        <kbd><span className="app-search-trigger__mac">⌘ K</span><span className="app-search-trigger__windows">Ctrl K</span></kbd>
      </button>
      {quietState ? <span aria-live="polite" className="app-context-bar__system-state" data-state={connectionState} title={quietState}><i /><span className="sr-only">{quietState}</span></span> : null}
      <button aria-label="Open contextual drawer" className="app-icon-button" onClick={onOpenDrawer} type="button">
        <AppIcon name="alerts" size={19} />
        <span className="app-icon-button__indicator" />
      </button>
      <div aria-label="Shine profile" className="app-profile"><span className="app-profile-mark">S</span><span>Shine</span></div>
    </header>
  );
}

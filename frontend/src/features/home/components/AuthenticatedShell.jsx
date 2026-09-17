import { useCallback, useState } from "react";
import { MotionProvider } from "../../../components/motion/index.js";
import { AppRail, MobileAppNav } from "./AppRail.jsx";
import { CommandPalette } from "./CommandPalette.jsx";
import { HomeContextBar } from "./HomeContextBar.jsx";

export function AuthenticatedShell({ area = "Home", children, contextDrawer, reducedMotionOverride, searchItems = [] }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  return (
    <MotionProvider reducedMotionOverride={reducedMotionOverride}>
      <div className="authenticated-shell">
        <a className="skip-link" href="#app-content">Skip to intelligence home</a>
        <AppRail />
        <HomeContextBar area={area} onOpenCommand={openPalette} onOpenDrawer={() => setDrawerOpen(true)} />
        <main className="authenticated-shell__content" id="app-content">{children}</main>
        <MobileAppNav />
        {contextDrawer ? contextDrawer({ open: drawerOpen, onClose: () => setDrawerOpen(false), onOpen: () => setDrawerOpen(true) }) : null}
        <CommandPalette onClose={closePalette} onOpen={openPalette} open={paletteOpen} searchItems={searchItems} />
      </div>
    </MotionProvider>
  );
}

import { lazy, Suspense } from "react";
import { MotionProvider, PageTransition } from "../components/motion/index.js";
import { PublicHeader } from "../components/public/PublicHeader.jsx";
import { SignalHero } from "../components/landing/SignalHero.jsx";

const LandingScenes = lazy(() => import("../components/landing/LandingScenes.jsx"));

function LandingFallback() {
  return (
    <div aria-hidden="true" className="landing-fallback page-frame">
      <span /><span />
    </div>
  );
}

export function LandingPage({ reducedMotionOverride }) {
  return (
    <MotionProvider reducedMotionOverride={reducedMotionOverride}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <PublicHeader />
      <PageTransition>
        <main className="kinetic-site" id="main-content">
          <SignalHero />
          <Suspense fallback={<LandingFallback />}>
            <LandingScenes />
          </Suspense>
        </main>
      </PageTransition>
    </MotionProvider>
  );
}

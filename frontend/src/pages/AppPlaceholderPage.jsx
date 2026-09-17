import { BrandMark } from "../components/brand/BrandMark.jsx";
import { MotionProvider, PageTransition } from "../components/motion/index.js";

export function AppPlaceholderPage() {
  return (
    <MotionProvider>
      <PageTransition className="app-placeholder-page">
        <main className="app-placeholder" data-authentication-backend="NOT_IMPLEMENTED">
          <a aria-label="InterSignal home" className="app-placeholder__brand" href="/">
            <BrandMark />
          </a>
          <div className="app-placeholder__content">
            <p className="technical-label">PROTOTYPE ROUTE</p>
            <h1>Authenticated prototype entry</h1>
            <p>Home / Intelligence Canvas will be implemented in Step 04.05C.</p>
            <p className="app-placeholder__notice">AUTHENTICATION_BACKEND = NOT_IMPLEMENTED</p>
            <a className="auth-button auth-button--primary" href="/">Return to landing</a>
          </div>
        </main>
      </PageTransition>
    </MotionProvider>
  );
}

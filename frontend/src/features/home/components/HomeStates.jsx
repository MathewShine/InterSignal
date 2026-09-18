export function HomeLoadingState() {
  return <div aria-live="polite" className="home-state home-state--loading"><span className="sr-only">Loading your overview…</span><div className="home-state__header" /><div className="home-state__market" /><div className="home-state__portfolio" /><div className="home-state__attention" /><div className="home-state__research" /></div>;
}

export function HomeErrorState({ onRetry }) {
  return <section className="home-state home-state--error" role="alert"><span className="technical-label">HOME CONTEXT</span><h1>Intelligence Home is temporarily unavailable.</h1><p>Your underlying research and portfolio state has not been changed.</p><button onClick={onRetry} type="button">Try again</button></section>;
}

export function HomeConnectionNotice({ connectionState, onRetry }) {
  return (
    <section aria-live="polite" className="home-connection-notice" role="status">
      <div><strong>Some data couldn’t be refreshed.</strong><span>Available information remains visible.</span></div>
      <button onClick={onRetry} type="button">Retry</button>
    </section>
  );
}

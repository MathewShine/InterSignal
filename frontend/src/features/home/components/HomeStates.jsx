export function HomeLoadingState() {
  return <div aria-live="polite" className="home-state home-state--loading"><span className="home-state__line" /><span className="home-state__line" /><span className="home-state__surface" /><p>Assembling market, portfolio and research context…</p></div>;
}

export function HomeErrorState({ onRetry }) {
  return <section className="home-state home-state--error" role="alert"><span className="technical-label">HOME CONTEXT</span><h1>Intelligence Home is temporarily unavailable.</h1><p>Your underlying research and portfolio state has not been changed.</p><button onClick={onRetry} type="button">Try again</button></section>;
}

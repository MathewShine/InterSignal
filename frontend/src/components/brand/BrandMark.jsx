export function BrandMark({ compact = false }) {
  return (
    <span className="brand-mark" aria-label="InterSignal">
      <svg aria-hidden="true" className="brand-mark__glyph" viewBox="0 0 28 28">
        <path d="M4 19.4 9.3 14l3.8 3.8L24 6.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
        <circle cx="4" cy="19.4" fill="currentColor" r="1.75" />
        <circle cx="13.1" cy="17.8" fill="currentColor" r="1.75" />
        <circle cx="24" cy="6.8" fill="currentColor" r="1.75" />
      </svg>
      {compact ? null : <span className="brand-mark__word">InterSignal</span>}
    </span>
  );
}

export function ArrowRightIcon({ size = 16, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 16 16"
      width={size}
    >
      <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MenuIcon({ size = 20 }) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 20 20" width={size}>
      <path d="M3 6.25h14M3 13.75h14" stroke="currentColor" strokeLinecap="round" />
    </svg>
  );
}

export function CloseIcon({ size = 20 }) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 20 20" width={size}>
      <path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeLinecap="round" />
    </svg>
  );
}

export function PlusIcon({ size = 16 }) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 16 16" width={size}>
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeLinecap="round" />
    </svg>
  );
}

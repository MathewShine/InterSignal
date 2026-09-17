const paths = {
  home: <><path d="M3.5 9.4 10 4l6.5 5.4" /><path d="M5.5 8.5v7h9v-7M8 15.5v-4h4v4" /></>,
  research: <><path d="M5 3.5h7.2a2.3 2.3 0 0 1 2.3 2.3v10.7H7.2A2.7 2.7 0 0 1 4.5 13.8V4" /><path d="M7 7h5M7 10h4" /></>,
  portfolio: <><rect x="3.5" y="6" width="13" height="10" rx="2" /><path d="M7 6V4.5h6V6M3.5 10h13" /></>,
  market: <><path d="M3 15.5h14M4.5 13l3.2-3.4 2.7 2.1 5-6" /><circle cx="15.4" cy="5.7" r="1" /></>,
  data: <><ellipse cx="10" cy="5" rx="6" ry="2.5" /><path d="M4 5v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V5M4 10v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-5" /></>,
  governance: <><path d="M10 2.8 16 5v4.2c0 4-2.5 6.7-6 8-3.5-1.3-6-4-6-8V5l6-2.2Z" /><path d="m7.3 9.8 1.8 1.8 3.7-4" /></>,
  alerts: <><path d="M5.2 8.5a4.8 4.8 0 1 1 9.6 0c0 5 2 5.2 2 6.2H3.2c0-1 2-1.2 2-6.2Z" /><path d="M8.2 16.5h3.6" /></>,
  settings: <><circle cx="10" cy="10" r="2.5" /><path d="M10 2.8v2M10 15.2v2M2.8 10h2M15.2 10h2M4.9 4.9l1.4 1.4M13.7 13.7l1.4 1.4M15.1 4.9l-1.4 1.4M6.3 13.7l-1.4 1.4" /></>,
  profile: <><circle cx="10" cy="7" r="3" /><path d="M4.2 17c.6-3 2.5-4.5 5.8-4.5s5.2 1.5 5.8 4.5" /></>,
  search: <><circle cx="8.5" cy="8.5" r="5" /><path d="m12.2 12.2 4.1 4.1" /></>,
  close: <path d="m5 5 10 10M15 5 5 15" />,
  chevron: <path d="m7 4 6 6-6 6" />,
  more: <><circle cx="4" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none" /></>,
};

export function AppIcon({ name, size = 20, className = "" }) {
  return (
    <svg aria-hidden="true" className={className} fill="none" height={size} viewBox="0 0 20 20" width={size}>
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.45">{paths[name]}</g>
    </svg>
  );
}

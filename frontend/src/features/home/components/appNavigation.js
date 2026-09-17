export const primaryNavigation = [
  { id: "home", label: "Home", path: "/app", icon: "home" },
  { id: "research", label: "Research", path: "/app/research", icon: "research" },
  { id: "portfolio", label: "Portfolio", path: "/app/portfolio", icon: "portfolio" },
  { id: "market", label: "Market", path: "/app/market", icon: "market" },
  { id: "data", label: "Data", path: "/app/data", icon: "data" },
];

export const secondaryNavigation = [
  { id: "governance", label: "Governance", path: "/app/governance", icon: "governance" },
  { id: "alerts", label: "Alerts", path: "/app/alerts", icon: "alerts" },
];

export const utilityNavigation = [
  { id: "settings", label: "Settings", path: "/app/settings", icon: "settings" },
  { id: "profile", label: "Profile", path: "/app/profile", icon: "profile" },
];

export const commandNavigation = [...primaryNavigation, ...secondaryNavigation];

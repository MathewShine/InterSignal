const statusLabels = {
  ok: "Online",
  available: "Available",
  checking: "Checking",
  pilot: "Pilot",
  partial: "Partial",
  limited: "Limited",
  current_only: "Current-only",
  partial_history: "Partial History",
  verified_history: "Verified History",
  not_configured: "Not configured",
  placeholder: "Pending",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

export function formatStatusLabel(status) {
  return statusLabels[status] || statusLabels.unknown;
}

export function getStatusClassName(status) {
  if (status === "ok" || status === "available") {
    return "status-ok";
  }

  if (status === "checking" || status === "placeholder" || status === "partial" || status === "partial_history" || status === "limited" || status === "pilot") {
    return "status-pending";
  }

  if (status === "verified_history") {
    return "status-ok";
  }

  if (status === "not_configured" || status === "current_only") {
    return "status-muted";
  }

  return "status-error";
}

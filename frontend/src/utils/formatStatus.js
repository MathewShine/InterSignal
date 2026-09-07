const statusLabels = {
  ok: "Online",
  checking: "Checking",
  not_configured: "Not configured",
  placeholder: "Pending",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

export function formatStatusLabel(status) {
  return statusLabels[status] || statusLabels.unknown;
}

export function getStatusClassName(status) {
  if (status === "ok") {
    return "status-ok";
  }

  if (status === "checking" || status === "placeholder") {
    return "status-pending";
  }

  if (status === "not_configured") {
    return "status-muted";
  }

  return "status-error";
}


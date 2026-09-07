import { formatStatusLabel, getStatusClassName } from "../utils/formatStatus.js";

export function StatusBadge({ status }) {
  return (
    <span className={`status-badge ${getStatusClassName(status)}`}>
      {formatStatusLabel(status)}
    </span>
  );
}


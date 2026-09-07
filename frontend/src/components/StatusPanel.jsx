import { StatusBadge } from "./StatusBadge.jsx";

export function StatusPanel({ label, status, detail }) {
  return (
    <section className="status-panel" aria-label={label}>
      <div>
        <p className="status-label">{label}</p>
        {detail ? <p className="status-detail">{detail}</p> : null}
      </div>
      <StatusBadge status={status} />
    </section>
  );
}


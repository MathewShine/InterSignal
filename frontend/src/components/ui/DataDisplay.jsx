export function StatusDot({ tone = "petrol", label }) {
  return (
    <span className="status-dot-wrap">
      <span aria-hidden="true" className={`status-dot status-dot--${tone}`} />
      {label ? <span>{label}</span> : null}
    </span>
  );
}

export function Metric({ label, value, detail, className = "" }) {
  return (
    <div className={`metric ${className}`.trim()}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {detail ? <span className="metric-detail">{detail}</span> : null}
    </div>
  );
}

export function ContextMetric({ label, value, context }) {
  return (
    <div className="context-metric">
      <div>
        <span className="context-metric__label">{label}</span>
        <strong className="context-metric__value">{value}</strong>
      </div>
      <span className="context-metric__context">{context}</span>
    </div>
  );
}

export function DemoBadge({ children = "Demo" }) {
  return <span className="demo-badge">{children}</span>;
}

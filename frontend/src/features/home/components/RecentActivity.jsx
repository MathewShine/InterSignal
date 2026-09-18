import { Link } from "react-router-dom";

function activityTime(value) {
  if (!value) return "Recent";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recent";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function RecentActivity({ items }) {
  return (
    <section aria-labelledby="activity-title" className="recent-activity">
      <header><div><h2 id="activity-title">Recent activity</h2><p>Latest platform changes</p></div><Link to="/app/alerts">View activity →</Link></header>
      <div>{items.length ? items.slice(0, 5).map((item) => <p key={item.id}><time dateTime={item.occurredAt ?? undefined}>{activityTime(item.occurredAt)}</time><span>{item.label}</span><small>{item.context}</small></p>) : <p className="recent-activity__empty">Activity is unavailable right now.</p>}</div>
    </section>
  );
}

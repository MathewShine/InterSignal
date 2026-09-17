export function RecentActivity({ items }) {
  return (
    <section aria-labelledby="activity-title" className="recent-activity">
      <header><span className="technical-label">RECENT ACTIVITY</span><h2 id="activity-title">Recent activity</h2></header>
      <div>{items.map((item) => <p key={item.id}><i /><span>{item.label}</span><small>{item.context}</small></p>)}</div>
    </section>
  );
}

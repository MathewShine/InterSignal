import { Link } from "react-router-dom";

export function ExploreNext({ items }) {
  return (
    <nav aria-label="Explore next" className="explore-next">
      <span className="technical-label">EXPLORE NEXT</span>
      <div>{items.map((item) => <Link key={item.id} to={item.path}>{item.label}<span>→</span></Link>)}</div>
    </nav>
  );
}

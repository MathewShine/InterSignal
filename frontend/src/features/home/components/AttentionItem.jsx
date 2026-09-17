import { Link } from "react-router-dom";

export function AttentionItem({ active, item, onSelect }) {
  return (
    <article className={`attention-item${active ? " is-active" : ""}`}>
      <button aria-pressed={active} className="attention-item__select" onClick={() => onSelect(item.id)} type="button">
        <span className="attention-item__meta"><span>{item.category}</span><span className={`attention-severity attention-severity--${item.severity.toLowerCase()}`}><i />{item.severity}</span></span>
        <h3>{item.title}</h3>
        <p>{item.summary}</p>
      </button>
      <div className="attention-item__detail">
        <dl><div><dt>Portfolio</dt><dd>{item.portfolioContext}</dd></div><div><dt>Research</dt><dd>{item.researchContext}</dd></div></dl>
        <footer><span>{item.timestampLabel}</span><Link to={item.actions[0].path}>{item.actions[0].label} →</Link></footer>
      </div>
    </article>
  );
}

import { Link } from "react-router-dom";

export function AttentionItem({ active, item, onSelect }) {
  return (
    <article className={`attention-item${active ? " is-active" : ""}`}>
      <button aria-pressed={active} className="attention-item__select" onClick={() => onSelect(item.id)} type="button">
        <span className={`attention-severity attention-severity--${item.severity.toLowerCase()}`}><i /><span className="sr-only">{item.severity}</span></span>
        <span className="attention-item__copy"><strong>{item.title}</strong><span>{item.summary}</span></span>
        <span className="attention-item__source">{item.category}</span>
      </button>
      <Link aria-label={`${item.actions[0].label}: ${item.title}`} to={item.actions[0].path}>View →</Link>
    </article>
  );
}

import { motion } from "motion/react";
import { AttentionItem } from "./AttentionItem.jsx";

export function AttentionStream({ activeId, items, onSelect }) {
  const platformItems = items.filter((item) => item.provenance === "PLATFORM");
  const ungroupedItems = items.filter((item) => !item.provenance);
  const visibleItems = [...platformItems, ...ungroupedItems].slice(0, 4);
  return (
    <motion.section animate={{ opacity: 1, y: 0 }} aria-labelledby="attention-title" className="attention-stream" initial={{ opacity: 0, y: 8 }} transition={{ delay: .35, duration: .28 }}>
      <header><div><h2 id="attention-title">Important today</h2><p>Operational changes that may need a decision.</p></div><span>{visibleItems.length} items</span></header>
      <div className="attention-stream__items">
        {visibleItems.map((item) => <AttentionItem active={item.id === activeId} item={item} key={item.id} onSelect={onSelect} />)}
        {!visibleItems.length ? <p className="attention-stream__empty">No new items need attention.</p> : null}
      </div>
    </motion.section>
  );
}

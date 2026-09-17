import { motion } from "motion/react";
import { AttentionItem } from "./AttentionItem.jsx";

export function AttentionStream({ activeId, items, onSelect }) {
  return (
    <motion.section animate={{ opacity: 1, y: 0 }} aria-labelledby="attention-title" className="attention-stream" initial={{ opacity: 0, y: 8 }} transition={{ delay: .35, duration: .28 }}>
      <header><div><span className="technical-label">ATTENTION STREAM</span><h2 id="attention-title">What deserves attention</h2></div><span>{items.length} contexts</span></header>
      <div className="attention-stream__items">{items.map((item) => <AttentionItem active={item.id === activeId} item={item} key={item.id} onSelect={onSelect} />)}</div>
    </motion.section>
  );
}

import { AnimatePresence, motion } from "motion/react";
import { Link } from "react-router-dom";
import { AppIcon } from "./AppIcon.jsx";

export function ContextDrawer({ open, onClose, onOpen, selectedItem, summary, research, dataHealth, governance }) {
  return (
    <>
      <button
        aria-label="Open contextual drawer"
        className="context-edge-trigger"
        onClick={() => open ? onClose() : onOpen()}
        type="button"
      >
        <span>{summary.researchBlockers} research blockers</span>
        <span>{summary.dataLimitations} data limitations</span>
      </button>
      <AnimatePresence>
        {open ? (
          <motion.div animate={{ opacity: 1 }} className="context-drawer__backdrop" exit={{ opacity: 0 }} initial={{ opacity: 0 }} onMouseDown={onClose}>
            <motion.aside
              animate={{ x: 0 }}
              aria-label="Context drawer"
              aria-modal="true"
              className="context-drawer"
              exit={{ x: "100%" }}
              initial={{ x: "100%" }}
              onMouseDown={(event) => event.stopPropagation()}
              role="dialog"
              transition={{ duration: .24, ease: [0.22, 1, 0.36, 1] }}
            >
              <header><div><span className="technical-label">CURRENT CONTEXT</span><h2>{selectedItem?.title ?? "Home context"}</h2></div><button aria-label="Close contextual drawer" className="app-icon-button" onClick={onClose} type="button"><AppIcon name="close" /></button></header>
              <section><span className="context-drawer__section-label">Research</span><p>{selectedItem?.researchContext ?? research?.evidenceQualification}</p><Link to="/app/research">Open Research →</Link></section>
              <section><span className="context-drawer__section-label">Data</span><p>{dataHealth?.rows?.find((row) => row.tone === "blocked")?.value ?? "No blocking data state."}</p><Link to="/app/data">Open Data →</Link></section>
              <section><span className="context-drawer__section-label">Governance</span><dl><div><dt>Paper</dt><dd>{governance?.paper}</dd></div><div><dt>Live</dt><dd>{governance?.live}</dd></div><div><dt>Pending authorizations</dt><dd>{governance?.pendingAuthorizations}</dd></div></dl><Link to="/app/governance">Open Governance →</Link></section>
              <section><span className="context-drawer__section-label">Alerts</span><p>{summary.researchBlockers} research blockers and {summary.dataLimitations} data limitations remain visible in context.</p><Link to="/app/alerts">Open Alerts →</Link></section>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}

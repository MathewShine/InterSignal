import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppIcon } from "./AppIcon.jsx";
import { commandNavigation } from "./appNavigation.js";
import { searchMarketInstruments } from "../../market/data/marketWorkspaceApi.js";

export function CommandPalette({ open, onClose, onOpen, searchItems = [] }) {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [marketItems, setMarketItems] = useState([]);

  const items = useMemo(() => {
    const routes = commandNavigation.map((item) => ({ ...item, group: "Go to" }));
    const all = [...routes, ...searchItems, ...marketItems];
    const normalized = query.trim().toLowerCase();
    return normalized ? all.filter((item) => `${item.group} ${item.label}`.toLowerCase().includes(normalized)) : all;
  }, [marketItems, query, searchItems]);

  useEffect(() => {
    const normalized = query.trim();
    if (!open || normalized.length < 2) { setMarketItems([]); return undefined; }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchMarketInstruments(normalized, { signal: controller.signal }).then(setMarketItems).catch(() => setMarketItems([]));
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [open, query]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
      if (event.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, onOpen, open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const choose = (item) => {
    if (!item) return;
    onClose();
    navigate(item.path);
  };

  const handleKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % Math.max(items.length, 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + Math.max(items.length, 1)) % Math.max(items.length, 1));
    }
    if (event.key === "Enter") {
      event.preventDefault();
      choose(items[activeIndex]);
    }
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div animate={{ opacity: 1 }} className="command-palette__backdrop" exit={{ opacity: 0 }} initial={{ opacity: 0 }} onMouseDown={onClose}>
          <motion.section
            animate={{ opacity: 1, scale: 1, y: 0 }}
            aria-label="Command palette"
            aria-modal="true"
            className="command-palette"
            exit={{ opacity: 0, scale: .98, y: -8 }}
            initial={{ opacity: 0, scale: .98, y: -8 }}
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            transition={{ duration: .18 }}
          >
            <div className="command-palette__input-row">
              <AppIcon name="search" size={19} />
              <input
                aria-label="Search commands"
                onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
                onKeyDown={handleKeyDown}
                placeholder="Search markets, research, portfolios, evidence…"
                ref={inputRef}
                value={query}
              />
              <kbd>Esc</kbd>
            </div>
            <div aria-label="Command results" className="command-palette__results" role="listbox">
              {items.map((item, index) => (
                <button
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "is-active" : ""}
                  key={`${item.group}-${item.id}`}
                  onClick={() => choose(item)}
                  onMouseEnter={() => setActiveIndex(index)}
                  role="option"
                  type="button"
                >
                  <span><small>{item.group}</small>{item.label}</span>
                  <AppIcon name="chevron" size={16} />
                </button>
              ))}
              {items.length === 0 ? <p className="command-palette__empty">No prototype result matches that search.</p> : null}
            </div>
            <footer><span>↑↓ Navigate</span><span>↵ Open</span><span>Market instrument master + product navigation</span></footer>
          </motion.section>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

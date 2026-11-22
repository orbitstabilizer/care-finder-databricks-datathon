import { useEffect, useRef, useState } from "react";
import { useStore } from "../App.jsx";
import { Chev } from "../icons.jsx";

/** Searchable, grouped service combobox. */
export default function ServicePicker() {
  const { services, service, svcByLabel, chooseService } = useStore();
  const current = svcByLabel(service)?.name || "";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(null);     // null = show all
  const [active, setActive] = useState(-1);
  const inputRef = useRef(null), listRef = useRef(null);

  const f = (query || "").toLowerCase().trim();
  // match the visible name, the service id and its aliases (config.SERVICE_ALIASES), e.g. "lscs" -> C-section
  const fn = f.replace(/[-_]/g, " ");
  const visible = services.filter((s) => !f || s.entry.toLowerCase().includes(f)
    || [s.label, ...(s.aliases || [])].some((a) => { const x = a.toLowerCase(); return x.includes(f) || x.replace(/[-_]/g, " ").includes(fn); }));
  useEffect(() => { listRef.current?.querySelector(".opt.active")?.scrollIntoView({ block: "nearest" }); }, [active]);

  const close = () => { setOpen(false); setQuery(null); setActive(-1); };
  const pick = (s) => { if (s) chooseService(s.label); close(); inputRef.current?.blur(); };
  const note = svcByLabel(service)?.coverage_note;

  let group = null;
  return (
    <div className="field combo">
      <label htmlFor="svc-input">Service</label>
      <div className="select-wrap">
        <input id="svc-input" ref={inputRef} type="text" role="combobox" aria-expanded={open} aria-controls="svc-list"
          autoComplete="off" placeholder="Type to search services"
          value={open && query !== null ? query : current}
          onFocus={(e) => { e.target.select(); setOpen(true); setQuery(null); setActive(-1); }}
          onChange={(e) => { setQuery(e.target.value); setActive(-1); setOpen(true); }}
          onBlur={() => setTimeout(close, 120)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(0, Math.min(visible.length - 1, a + (e.key === "ArrowDown" ? 1 : -1))));
            } else if (e.key === "Enter") { e.preventDefault(); pick(visible[active >= 0 ? active : 0]); }
            else if (e.key === "Escape") { close(); inputRef.current?.blur(); }
          }} />
        <Chev />
      </div>
      {open && (
        <ul id="svc-list" className="combo-list" role="listbox" ref={listRef}>
          {visible.length ? visible.map((s, i) => {
            const head = s.group !== group ? (group = s.group) : null;
            return [
              head && <li key={`g-${head}`} className="grp" role="presentation">{head}</li>,
              <li key={s.label} className={`opt${i === active ? " active" : ""}`} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); pick(s); }}>{s.name}</li>,
            ];
          }) : <li className="grp">No matching service</li>}
        </ul>
      )}
      {note && <div className="note">{note}</div>}
    </div>
  );
}

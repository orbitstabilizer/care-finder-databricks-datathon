import { useStore } from "../App.jsx";
import { Warn } from "../icons.jsx";

export function Distance({ r, drawer }) {
  if (!r.exact_location) return <span className="dist unk">{drawer ? `in ${r.city || "this area"}, exact location unknown` : "exact location unknown"}</span>;
  if (r.location_uncertain) return <span className="dist uncertain">about {Math.round(r.distance_km)} km, location uncertain</span>;
  return <span className="dist num">{drawer ? `${r.distance_km.toFixed(2)} km away` : `${r.distance_km.toFixed(1)} km`}</span>;
}

/** Record-level sources: domains sharing the facility's name, then directory listings. Others are never shown. */
export function Sources({ list }) {
  const own = list.filter((d) => !d.listing);
  const link = (d) => <a href={`https://${d.domain}`} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()}>{d.domain}</a>;
  return (
    <div className="sources">
      <span className="sources-k">{own.length ? "Sources for this record (not for each sentence):" : "Sources: listings only"}</span>{" "}
      {list.map((d, i) => <span key={d.domain}>{i > 0 && " · "}{link(d)}{d.listing && <span className="listing-tag">listing</span>}</span>)}
    </div>
  );
}

export default function ResultCard({ r }) {
  const { selectedId, hoveredId, setHoveredId, openDetails } = useStore();
  const q = r.evidence[0];
  const w = r.warnings;
  const city = r.exact_location ? [r.city, r.state].filter(Boolean).join(", ") : `in ${r.city || "this area"}${r.state ? `, ${r.state}` : ""}`;
  const cls = ["card", r.tier, selectedId === r.id && "sel", hoveredId === r.id && "hl"].filter(Boolean).join(" ");
  return (
    <div className={cls} data-id={r.id} tabIndex={0} role="button" aria-label={`${r.name}, ${r.tier}`}
      onClick={() => openDetails(r.id)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetails(r.id); } }}
      onMouseEnter={() => setHoveredId(r.id)} onMouseLeave={() => setHoveredId((h) => (h === r.id ? null : h))}>
      <div className="card-top">
        <div><div className="card-name">{r.name}</div><div className="card-city">{city}</div>
          {r.position && <div className="card-pos">{r.position}</div>}</div>
        <Distance r={r} />
      </div>
      {q ? <div className="quote"><q>{q.sentence}</q> <span className="src">{q.source_column}</span></div> : <div className="noev">No quoted evidence.</div>}
      {r.sources && <Sources list={r.sources} />}
      {w.length > 0 && (
        <div className="warns">
          <span className="wchip" title={w.join("\n")}><Warn /><span>{w[0]}</span></span>
          {w.length > 1 && <span className="wchip" title={w.slice(1).join("\n")}>+{w.length - 1} more</span>}
        </div>
      )}
    </div>
  );
}

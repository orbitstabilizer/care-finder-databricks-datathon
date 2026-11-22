import { useEffect, useRef } from "react";
import { useStore } from "../App.jsx";
import { Back, Nav, Phone, Warn, Web } from "../icons.jsx";
import { Distance, Sources } from "./ResultCard.jsx";

const WHY_WARN = /([1-9]\d*% of its sentences were flagged|mostly|rarely|approximate|unknown|suspect|unverified|disagree|only weak|could not|not exact|no statement|centre)/i;

/** Slides over the result list; keeps the last facility rendered while it slides out. */
export default function DetailsDrawer() {
  const { selectedId, byId, closeDetails } = useStore();
  const last = useRef(null);
  const backRef = useRef(null), boxRef = useRef(null);
  const r = (selectedId && byId[selectedId]) || null;
  if (r) last.current = r;
  const show = last.current;
  const open = !!r;

  useEffect(() => {
    if (open) { boxRef.current.scrollTop = 0; backRef.current?.focus({ preventScroll: true }); }
    else if (last.current) document.querySelector(`.card[data-id="${CSS.escape(last.current.id)}"]`)?.focus({ preventScroll: true });
  }, [open, selectedId]);

  let body = null;
  if (show) {
    const d = show.details;
    const tel = d.phone ? d.phone.replace(/[^\d+]/g, "") : "";
    const rows = [
      ["Address", d.address],
      ["Phone", d.phone && <a href={`tel:${tel}`}>{d.phone}</a>],
      ["Website", d.website && <a href={d.website} target="_blank" rel="noopener">{d.domain}</a>],
      ["Type", d.type],
      ["Departments", d.departments],
      ["Location", d.location_confidence],
    ].filter(([, v]) => v);
    body = (<>
      <div className="drawer-head">
        <button className="back" id="back" ref={backRef} type="button" onClick={closeDetails}><Back /> Back to results</button>
        <h2>{show.name}</h2>
        {show.position && <div className="card-pos">{show.position}</div>}
        <div className="drawer-meta">
          <span className={`badge ${show.tier}`}><span className={`dot ${show.tier}`} />{show.tier}</span>
          <Distance r={show} drawer />
          <span>{[show.city, show.state].filter(Boolean).join(", ")}</span>
        </div>
      </div>
      <div className="drawer-body">
        <div className="actions">
          {d.phone && <a className="action" href={`tel:${tel}`}><Phone />Call<small>{d.phone}</small></a>}
          <a className="action primary" href={d.directions_url} target="_blank" rel="noopener"><Nav />Directions{d.directions_approximate && <small>approximate: city or postcode centre</small>}</a>
          {d.website && <a className="action" href={d.website} target="_blank" rel="noopener"><Web />Website<small>{d.domain}</small></a>}
        </div>
        {show.warnings.length > 0 && (
          <div className="sect"><h4>Warnings</h4>
            <ul className="wlist">{show.warnings.map((w) => <li key={w}><Warn /><span>{w}</span></li>)}</ul></div>
        )}
        <div className="sect"><h4>Evidence <span className="sub-h">· quoted from the facility's own text</span></h4>
          {show.evidence.length ? show.evidence.map((e, i) => (
            <blockquote key={i} className="ev">“{e.sentence}”<br /><span className="src">source column: {e.source_column}</span></blockquote>
          )) : <p className="noev">No quoted evidence.</p>}
          {show.sources && <Sources list={show.sources} />}
        </div>
        <div className="sect"><h4>Why this result</h4>
          <ul className="check">{show.why.map((w) => {
            const bad = WHY_WARN.test(w);
            return <li key={w}><span className={`ic ${bad ? "wa" : "ok"}`} aria-label={bad ? "caution" : "ok"}>{bad ? "!" : "✓"}</span><span>{w}</span></li>;
          })}</ul>
        </div>
        <div className="sect"><h4>Details</h4>
          <dl className="dl">{rows.map(([k, v]) => [<dt key={`t${k}`}>{k}</dt>, <dd key={`d${k}`}>{v}</dd>])}</dl>
        </div>
      </div>
    </>);
  }
  return <div ref={boxRef} className={`drawer${open ? " open" : ""}`} aria-hidden={!open}>{body}</div>;
}

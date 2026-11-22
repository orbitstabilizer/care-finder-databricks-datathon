import { useState } from "react";
import { useStore } from "../App.jsx";
import { EXAMPLES } from "../api.js";
import { Pin, Warn } from "../icons.jsx";
import TierChips from "./TierChips.jsx";
import DistrictStrip from "./DistrictStrip.jsx";
import TierSection from "./TierSection.jsx";

function EmptyState({ title, text, examples }) {
  const { setService, setPinText, setPlaceText, resolve } = useStore();
  const [busy, setBusy] = useState(null);
  return (
    <div className="empty-state">
      <div className="ill"><Pin /></div>
      <h3>{title}</h3>
      <p>{text}</p>
      {examples && (
        <div className="examples">
          {EXAMPLES.map((x, i) => (
            <button key={x.q} type="button" className={`pill${busy === i ? " busy" : ""}`} onClick={async () => {
              setBusy(i);
              setService(x.label);
              if (x.kind === "pin") { setPinText(x.where); setPlaceText(""); } else { setPlaceText(x.where); setPinText(""); }
              await resolve(x.q);
              setBusy(null);
            }}>{x.name} <span className="sep">·</span> {x.where}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function Skeleton() {
  const card = (k) => (<div key={k} className="sk-card"><div className="sk sk-line mid" /><div className="sk sk-line short" /><div className="sk sk-quote" /></div>);
  return (<>
    <div className="sk sk-line short" style={{ height: 16, marginTop: 14 }} />
    <div className="sk-chips"><div className="sk" /><div className="sk" /><div className="sk" /><div className="sk" /></div>
    {[0, 1, 2].map(card)}
  </>);
}

function Credible() {
  const { data: d, openDetails } = useStore();
  const c = d.closest_credible;
  if (!c && !d.far_confirmed_note) return null;
  return (
    <div className="credible">
      {c && (
        <button type="button" className="credible-row" onClick={() => openDetails(c.id)}>
          <span className="credible-k">Closest credible option</span>
          <span className="credible-name">{c.name}{c.city ? `, ${c.city}` : ""} · <span className="num">{c.distance_km} km</span></span>
          <span className="credible-tag"><span className="dot Likely" />Likely — call to confirm{c.confirmed_km ? ` (nearest Confirmed is ${Math.round(c.confirmed_km)} km)` : ""}</span>
        </button>
      )}
      {d.far_confirmed_note && <p className="credible-note">Few facilities state this in detail. Call the Likely ones first.</p>}
    </div>
  );
}

/** District hint: a suggestion to call nearby hospitals offering related care. Separate from the
 *  tiers; it never changes tier or order. The server decides when it shows (main._district_hint). */
function DistrictHint() {
  const { district: c } = useStore();
  const h = c?.hint;
  if (!h || !h.facilities?.length) return null;
  return (
    <div className="dhint">
      <p className="dhint-head">{h.headline}</p>
      <p className="dhint-text">{h.text}</p>
      <ul className="dhint-list">
        {h.facilities.map((f) => (
          <li key={f.id}>
            <div className="dhint-row">
              <span className="dhint-name">{f.name}{f.city ? `, ${f.city}` : ""} · <span className="num">{f.where}</span></span>
              <span className="dhint-tag"><span className={`dot ${f.tier}`} />{f.tier} for {f.service_name.toLowerCase()}</span>
              {f.sentence && <q className="dhint-quote">{f.sentence}</q>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Results({ scrollRef }) {
  const { point, data, loading, searchError, emergency } = useStore();
  let body;
  if (!point) body = <EmptyState title="Choose a location" text="Enter a PIN code or place, or click the map. Or try one of these:" examples />;
  else if (loading) body = <Skeleton />;
  else if (searchError) body = <EmptyState title="Search did not finish" text="Something went wrong reaching the data. Try again in a moment." />;
  else if (!data) body = null;
  else {
    const d = data;
    body = (<>
      {d.is_sample && <div className="banner sample">SAMPLE DATA: not real recommendations. Real facilities and quoted sentences, placeholder tiers.</div>}
      {emergency && <div className="emergency" style={{ margin: "8px 0 4px" }}><Warn /> <span>If this is an emergency, call <a href="tel:108">108</a> for an ambulance, or <a href="tel:112">112</a>.</span></div>}
      <div className="res-head"><h2>{d.service_name}</h2>{d.n ? <span className="count num">{d.n} {d.n === 1 ? "facility" : "facilities"}</span> : null}</div>
      {!d.n ? <EmptyState title={`No facility has evidence for ${d.service_name}.`} text="Try a related service or another location." /> : (<>
        <Credible />
        <DistrictHint />
        <TierChips scrollRef={scrollRef} />
        <DistrictStrip />
        <p className="meta">Within each tier, facilities with an exact location come first, then by distance. Column-shifted records and facilities with no usable position are left out. Query {d.query_s}s.</p>
        {d.tiers.filter((t) => t.count).map((t) => <TierSection key={t.tier} t={t} />)}
      </>)}
    </>);
  }
  return <section id="results" className="results" aria-live="polite">{body}</section>;
}

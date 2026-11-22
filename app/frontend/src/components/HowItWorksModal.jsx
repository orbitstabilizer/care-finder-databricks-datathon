import { useEffect, useRef, useState } from "react";
import { useStore } from "../App.jsx";
import { api } from "../api.js";
import { Close } from "../icons.jsx";

const FUNNEL = [
  ["facilities", "Facilities in the dataset"],
  ["sentences_read", "Sentences read about them"],
  ["distinct_sentences", "Distinct sentences"],
  ["distinct_sentences_tagged", "Distinct sentences classified so far"],
  ["service_claim_sentences", "Distinct sentences that say a facility offers a service"],
  ["facilities_audited", "Records checked for text from other hospitals"],
  ["records_mixed", "Records that appear mixed with another hospital's text (flagged sentences never quoted)"],
];
let cache = null;

export default function HowItWorksModal() {
  const { setModalOpen } = useStore();
  const [s, setS] = useState(cache);
  const [err, setErr] = useState(null);
  const closeRef = useRef(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  useEffect(() => {
    if (cache) return;
    api("/api/stats").then((x) => { cache = x; setS(x); }).catch((e) => setErr(e.message));
  }, []);
  const fmt = (v) => (v == null ? "?" : Number(v).toLocaleString("en-IN"));
  const known = new Set(FUNNEL.map(([k]) => k));
  const rows = s ? [...FUNNEL, ...Object.keys(s.funnel).filter((k) => !known.has(k)).map((k) => [k, k.replace(/_/g, " ")])].filter(([k]) => k in s.funnel) : [];
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" onClick={(e) => { if (e.target === e.currentTarget) setModalOpen(false); }}>
      <div className="modal-box">
        <button className="icon-btn close" ref={closeRef} aria-label="Close" onClick={() => setModalOpen(false)}><Close /></button>
        <h2 id="modal-title">How this works</h2>
        {err ? <div>{err}</div> : !s ? (<><div className="sk sk-line" /><div className="sk sk-line" /><div className="sk sk-line short" /></>) : (<>
          <p>Every result is traced to sentences in the facility's own record. Each sentence was classified for which service it describes and how strongly. Records that mix in another hospital's text were audited, and their flagged sentences are never quoted.</p>
          <ul className="funnel">{rows.map(([k, l]) => <li key={k}><span>{l}</span><b>{fmt(s.funnel[k])}</b></li>)}</ul>
          <dl className="rules">
            <dt><span className="badge Confirmed"><span className="dot Confirmed" />Confirmed</span></dt><dd>A detailed statement (numbers, units, beds) plus a matching department, a second statement, or a usual fit for the facility type.</dd>
            <dt><span className="badge Likely"><span className="dot Likely" />Likely</span></dt><dd>At least one detailed or plain statement.</dd>
            <dt><span className="badge Possible"><span className="dot Possible" />Possible</span></dt><dd>No statement, but the matching department plus a related service.</dd>
            <dt><span className="badge Unverified"><span className="dot Unverified" />Unverified</span></dt><dd>Only weak mentions, mostly another hospital's text, or a facility type that rarely offers the service.</dd>
          </dl>
          <p>Within each tier, facilities with an exact location come first, then by distance. Facilities placed only at a city or postcode centre show no distance.</p>
          {s.build_ts && <p className="fine">Numbers as of {s.build_ts.slice(0, 16).replace("T", " ")} UTC.</p>}
        </>)}
      </div>
    </div>
  );
}

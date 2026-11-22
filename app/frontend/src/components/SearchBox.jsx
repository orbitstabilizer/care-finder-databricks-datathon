import { useState } from "react";
import { useStore } from "../App.jsx";
import { api } from "../api.js";
import { Search, Warn } from "../icons.jsx";

/** Free-text matcher. Auto-searches only for a named service with high confidence; otherwise offers options. */
export default function SearchBox() {
  const { svcByLabel, chooseService, service, setEmergency, toast } = useStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);       // {pending} | match response
  const [picked, setPicked] = useState(null);

  async function submit(e) {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setBusy(true); setRes({ pending: true }); setPicked(null);
    try {
      const m = await api("/api/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: t }) });
      setEmergency(!!m.emergency);
      setRes(m);
      if (m.matched && svcByLabel(m.matched)) chooseService(m.matched);
    } catch (err) {
      setRes(null); toast(err.message);
    } finally { setBusy(false); }
  }

  const usable = (l) => !!svcByLabel(l.label);
  const matched = res && !res.pending && res.matched && svcByLabel(res.matched) ? res.matched : null;
  const alts = res && !res.pending ? (res.alternatives || []).filter(usable) : [];
  // "Best guess" first; the rest keep the server's least-invasive order (no surgery above a non-surgical option).
  const opts0 = res && !res.pending ? (res.options || []).filter(usable) : [];
  const opts = [...opts0.filter((o) => o.fit === "best"), ...opts0.filter((o) => o.fit !== "best")];

  return (
    <form className="hero" onSubmit={submit}>
      <label htmlFor="need" className="hero-label">What care do you need?</label>
      <div className="hero-box">
        <Search />
        <input id="need" type="text" placeholder="e.g. my father needs a kidney machine" autoComplete="off"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className={`btn primary${busy ? " busy" : ""}`} disabled={busy}>Find</button>
      </div>
      {res && (
        <div className="match" aria-live="polite">
          {res.pending ? <div className="muted-line">Matching your words to a service…</div> : (<>
            {res.emergency && <div className="emergency"><Warn /> <span>If this is an emergency, call <a href="tel:108">108</a> for an ambulance, or <a href="tel:112">112</a>.</span></div>}
            {matched ? (
              <div className="pills">
                <span className="pill-label">Matched</span>
                {[{ label: matched }, ...alts].map((a, i) => (
                  <span key={a.label} style={{ display: "contents" }}>
                    {i === 1 && <span className="pill-label">or</span>}
                    <button type="button" className={`pill${service === a.label ? " on" : ""}`}
                      onClick={() => { if (a.label !== service) chooseService(a.label); }}>
                      {svcByLabel(a.label).name}{service === a.label ? " ✓" : ""}
                    </button>
                  </span>
                ))}
              </div>
            ) : opts.length ? (<>
              <div className="opt-q">Which of these fits?</div>
              <div className="opts">
                {opts.map((o) => (
                  <button key={o.label} type="button" className={`opt-card${picked === o.label ? " on" : ""}`}
                    onClick={() => { setPicked(o.label); chooseService(o.label); }}>
                    <span className="opt-top"><b>{svcByLabel(o.label).name}</b>
                      <span className={`opt-tag${o.fit === "best" ? " best" : ""}`}>{o.fit === "best" ? "Best guess" : "Possible"}</span></span>
                    {o.reason && <span className="opt-reason">{o.reason}</span>}
                  </button>
                ))}
              </div>
            </>) : res.kind === "unclear" ? (
              <div className="muted-line">Please describe the care you need, for example “dialysis” or “my child has a high fever”.</div>
            ) : res.error ? (
              <div className="muted-line">Could not match right now ({res.error}). Pick a service from the list.</div>
            ) : <div className="muted-line">Pick a service from the list.</div>}
            <p className="fine">This only matches words to a service; it is not medical advice.</p>
          </>)}
        </div>
      )}
    </form>
  );
}

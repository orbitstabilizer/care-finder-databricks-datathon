import { useState } from "react";
import { useStore } from "../App.jsx";
import { Cursor } from "../icons.jsx";

export default function LocationInputs() {
  const { resolve, point, clearPoint, pickPlace, pinText, setPinText, placeText, setPlaceText } = useStore();
  const [busy, setBusy] = useState(null);
  const go = async (e, kind) => {
    e.preventDefault();
    const v = (kind === "pin" ? pinText : placeText).trim();
    if (!v) return;
    setBusy(kind);
    await resolve(`${kind}=${encodeURIComponent(v)}`);
    setBusy(null);
  };
  return (<>
    <div className="field">
      <span className="field-label">Location</span>
      <div className="loc-row">
        <form className="inline-form" onSubmit={(e) => go(e, "pin")}>
          <input inputMode="numeric" maxLength={10} placeholder="PIN code, e.g. 411001" aria-label="PIN code"
            value={pinText} onChange={(e) => setPinText(e.target.value)} />
          <button className={`btn ghost${busy === "pin" ? " busy" : ""}`} type="submit" disabled={busy === "pin"}>Use</button>
        </form>
        <form className="inline-form" onSubmit={(e) => go(e, "place")}>
          <input placeholder="Place, e.g. Udaipur" aria-label="Place name"
            value={placeText} onChange={(e) => setPlaceText(e.target.value)} />
          <button className={`btn ghost${busy === "place" ? " busy" : ""}`} type="submit" disabled={busy === "place"}>Use</button>
        </form>
      </div>
      <p className="hint"><Cursor />Or click anywhere on the map to use that point.</p>
    </div>
    {point && (
      <div className="point">
        <div className="point-top">
          <span className="point-dot" aria-hidden="true" />
          <span className="point-text"><b>{point.origin}</b> <span className="num">{point.lat.toFixed(4)}, {point.lon.toFixed(4)}</span></span>
          <button className="text-btn" id="clear-pt" type="button" onClick={clearPoint}>Clear</button>
        </div>
        {point.matched && !point.matched.exact && (
          <div className="matched-line">Showing results near <b>{point.matched.name}</b> (matched “{point.matched.query}”)</div>
        )}
        {point.alternatives?.length > 0 && (
          <div className="pills alt-places"><span className="pill-label">Did you mean</span>
            {point.alternatives.map((a) => (
              <button key={`${a.name}-${a.lat}`} type="button" className="pill" onClick={() => pickPlace(a)}>{a.name}</button>
            ))}
          </div>
        )}
        {point.notes.map((n) => <div key={n} className="note">{n}</div>)}
      </div>
    )}
  </>);
}

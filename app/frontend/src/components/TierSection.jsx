import { useStore } from "../App.jsx";
import { FIRST, STEP } from "../api.js";
import ResultCard from "./ResultCard.jsx";

export default function TierSection({ t }) {
  const { shown, setShown, openUnverified, setOpenUnverified } = useStore();
  const open = t.tier !== "Unverified" || openUnverified;
  const n = shown[t.tier] || FIRST;
  return (
    <section className="tier" id={`tier-${t.tier}`}>
      <div className="tier-head">
        <span className={`dot ${t.tier}`} /><h3>{t.tier}</h3>
        <span className="tcount num">{t.count}{t.capped ? "+" : ""}</span>
        {t.tier === "Unverified" && (
          <button className="btn ghost small" onClick={() => setOpenUnverified((o) => !o)}>{open ? "Hide unverified" : "Show unverified"}</button>
        )}
      </div>
      <p className="tier-meaning">{t.meaning}</p>
      {open && (<>
        {t.results.slice(0, n).map((r) => <ResultCard key={r.id} r={r} />)}
        {t.count > n ? (
          <div className="more-row"><button className="btn ghost small" onClick={() => setShown((s) => ({ ...s, [t.tier]: n + STEP }))}>Show {Math.min(STEP, t.count - n)} more</button></div>
        ) : t.capped ? <p className="meta">Showing the nearest {t.results.length}.</p> : null}
        {t.city_block?.length > 0 && (
          <div className="city-block">
            <div className="city-block-head">In this city, exact address unknown <span className="tcount num">{t.city_block.length}</span></div>
            <p className="tier-meaning">Placed at a city or PIN centre within 25 km of your point, so no distance is shown.</p>
            {t.city_block.map((r) => <ResultCard key={r.id} r={r} />)}
          </div>
        )}
      </>)}
    </section>
  );
}

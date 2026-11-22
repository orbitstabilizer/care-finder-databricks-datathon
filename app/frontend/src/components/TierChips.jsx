import { useStore } from "../App.jsx";
import { TIERS, where } from "../api.js";

/** One chip per tier: nearest facility with a high/good location, plus a note if an uncertain one is closer. */
export default function TierChips({ scrollRef }) {
  const { data, openUnverified, setOpenUnverified } = useStore();
  const byTier = Object.fromEntries(data.summary.map((x) => [x.tier, x]));
  const jump = (t) => {
    if (t === "Unverified" && !openUnverified) setOpenUnverified(true);
    requestAnimationFrame(() => {
      const sec = document.getElementById(`tier-${t}`);
      if (sec && scrollRef.current) scrollRef.current.scrollTo({ top: sec.offsetTop - 4 });
    });
  };
  return (
    <div className="summary">
      {TIERS.map((t) => {
        const x = byTier[t];
        if (!x) return (<div key={t} className="tchip none"><span className="tname"><span className={`dot ${t}`} />{t}</span><span className="tdist unk">none nearby</span></div>);
        return (
          <button key={t} type="button" className="tchip" title={x.name ? `Nearest ${t}: ${x.name}` : undefined} onClick={() => jump(t)}>
            <span className="tname"><span className={`dot ${t}`} />{t}</span>
            {x.trusted ? <span className="tdist num">nearest {where(x)}</span> : <span className="tdist unk">no facility with a reliable location</span>}
            {x.closer_uncertain_km != null && <span className="tsub">A closer one at about {x.closer_uncertain_km} km has an uncertain location</span>}
          </button>
        );
      })}
    </div>
  );
}

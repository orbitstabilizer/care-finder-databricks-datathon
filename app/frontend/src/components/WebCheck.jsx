import { useStore } from "../App.jsx";

/** Blind web check for the searched service (hand-checked on each facility's own website,
 *  without seeing our tier). Shown only for services that were checked. Context only. */
export default function WebCheck() {
  const { data: d } = useStore();
  const w = d?.web_check;
  if (!w || !w.by_tier?.length) return null;
  const c = w.by_tier.find((t) => t.tier === "Confirmed");
  const head = c
    ? `Blind web check of Confirmed results: ${c.yes} of ${c.checked} checked offer it` +
      (c.cannot_tell ? `; ${c.cannot_tell} could not be checked.` : ".")
    : "Blind web check: no Confirmed results were sampled.";
  return (
    <div className="webcheck">
      <p className="wc-line">{head}{w.tuned && <span className="wc-tuned"> Rules were adjusted after this check.</span>}</p>
      <details className="wc-more">
        <summary>By tier</summary>
        <table className="wc-table">
          <thead><tr><th>Tier</th><th>Offer it</th><th>Could not be checked</th></tr></thead>
          <tbody>
            {w.by_tier.map((t) => (
              <tr key={t.tier}>
                <td><span className={`dot ${t.tier}`} />{t.tier}</td>
                <td className="num">{t.checked ? `${t.yes} of ${t.checked}` : "none checked"}</td>
                <td className="num">{t.cannot_tell}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="wc-foot">
          A sample of facilities was looked up on their own websites by someone who did not see our tier.
          "Checked" means the site clearly said yes or no; "could not be checked" means it did not say.
          {w.tuned ? " Tier as it was when sampled. Two dialysis rules were tuned on this check, so it is not an independent test." : " Tier from the current build. No rule was tuned on this check."}
        </p>
      </details>
    </div>
  );
}

import { useStore } from "../App.jsx";
import { fmtKm, ordinal, titleCase } from "../api.js";

/** NFHS-5 district context. Context only: never changes tier or order. Hidden until data arrives. */
export default function DistrictStrip() {
  const { district: c, data: d } = useStore();
  if (!c || !d) return <div id="district-strip" className="district" hidden />;
  const svc = /^[A-Z][^a-z]/.test(d.service_name) ? d.service_name : d.service_name.charAt(0).toLowerCase() + d.service_name.slice(1);
  const name = titleCase(c.district) + (c.state ? `, ${titleCase(c.state)}` : "");
  const inds = (c.indicators || []).filter((i) => i && i.value != null);
  const nC = c.n_confirmed_in_district || 0, nLP = (c.n_likely_in_district || 0) + (c.n_possible_in_district || 0);
  const nF = c.n_facilities_in_district || 0;
  const ex = c.nearest_confirmed_exact, any = c.nearest_confirmed_any;
  return (
    <div id="district-strip" className="district">
      <div className="ds-head">
        <span className="ds-kicker">District context</span><b>{name}</b>
        {c.district_method === "nearest_pin_centre" && <span className="ds-note">approximate: nearest PIN centre</span>}
        {c.alias_note && <span className="ds-note">matched via alias{c.nfhs_district ? ` (NFHS: ${c.nfhs_district})` : ""}</span>}
      </div>
      {inds.length ? (
        <ul className="ds-ind">
          {inds.map((i) => (
            <li key={i.indicator_column || i.label}>
              <span>{i.label}</span>
              <span><b className="num">{i.value}{i.unit === "%" ? "%" : i.unit ? ` ${i.unit}` : ""}</b>
                {i.rank_of_706 ? <span className="ds-rank">{ordinal(i.rank_of_706)} {i.direction === "lower_is_worse" ? "lowest" : "highest"} of 706 districts</span> : null}</span>
            </li>
          ))}
        </ul>
      ) : c.no_indicator_reason ? <p className="ds-note">{c.no_indicator_reason}</p> : null}
      <ul className="ds-lines">
        <li>{nF.toLocaleString("en-IN")} {nF === 1 ? "facility" : "facilities"} in this district in our data</li>
        <li>{nC ? `${nC} Confirmed for ${svc} in this district in our data` : `No Confirmed ${svc} in this district in our data`}</li>
        {!nC && nLP > 0 && <li>{nLP} {nLP === 1 ? "facility" : "facilities"} here may offer this service, call to confirm</li>}
        {/* nearest = nearest Confirmed with a high/good location (same rule as the tier chips) */}
        <li>{ex ? <>Nearest Confirmed: {ex.name}, <span className="num">{fmtKm(ex.km)}</span></> : `No Confirmed ${svc} with a reliable location found nearby in our data`}</li>
        {any && (!ex || (any.unique_id !== ex.unique_id && any.km < ex.km)) && (
          <li><span className="ds-sub">A closer one at about {Math.round(any.km)} km has an uncertain location</span></li>
        )}
      </ul>
      <p className="ds-foot">NFHS-5 (2019–21) district survey. Context only; it does not change the ranking.</p>
    </div>
  );
}

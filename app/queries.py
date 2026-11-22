"""Every read the app makes. One backend: Databricks SQL."""
import json

from config import (
    T_PIN_POINT, T_PINCODE, T_CITY_POINT, T_FAC_LOC, F_HAVERSINE,
    T_FAC_CLEAN, T_SERVICE, T_SERVICE_SAMPLE, WEAK_LOCATION, HIDDEN_SERVICES,
    SERVICE_GROUPS, COMMON_SEARCHES, N_DISTINCT_SENTENCES, service_name,
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, T_BUILD_STATS, TGT,
)

FALLBACK_SOURCES = ("city_point", "pin_point")   # facility point is a centroid, not an address
CITY_BLOCK_KM = 25   # centre-placed facilities this close get their own block per tier

PIN_SQL = f"""
SELECT pin, lat, lon, n_offices, spread_km
FROM {T_PIN_POINT} WHERE pin = ?
"""

# PINs missing from pin_point: median of the PIN's post-office coordinates.
PIN_MEDIAN_SQL = f"""
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY lat) AS lat,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY lon) AS lon,
       count(*) AS n_offices
FROM (SELECT try_cast(latitude AS DOUBLE) AS lat, try_cast(longitude AS DOUBLE) AS lon
      FROM {T_PINCODE} WHERE CAST(pincode AS STRING) = ?)
WHERE lat BETWEEN {LAT_MIN} AND {LAT_MAX} AND lon BETWEEN {LON_MIN} AND {LON_MAX}
"""

CITY_SQL = f"""
SELECT city_key, lat, lon, n_facilities
FROM {T_CITY_POINT} WHERE city_key = lower(trim(?))
"""

# Place index for fuzzy place search: cities (city_point), districts (centre of their primary,
# trusted PIN points), NFHS district aliases, and post-office names (exact match only).
PLACE_INDEX_SQL = f"""
WITH d AS (
  SELECT pd.district, pd.state,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY pp.lat) AS lat,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY pp.lon) AS lon, count(*) AS n
  FROM {TGT}.pin_district pd JOIN {T_PIN_POINT} pp ON pp.pin = pd.pin
  WHERE pd.is_primary AND coalesce(pp.trusted, true) AND pd.district IS NOT NULL
  GROUP BY pd.district, pd.state)
SELECT 'city' AS kind, city_key AS name, CAST(NULL AS STRING) AS district, CAST(NULL AS STRING) AS state,
       lat, lon, n_facilities AS n, 0 AS office_rank FROM {T_CITY_POINT}
UNION ALL
SELECT 'district', district, district, state, lat, lon, n, 0 FROM d
UNION ALL
SELECT DISTINCT 'alias', a.nfhs_district, d.district, d.state, d.lat, d.lon, d.n, 0
FROM {TGT}.district_alias a JOIN d ON lower(d.district) = lower(a.pin_district_name)
                                   AND lower(d.state) = lower(a.pin_state)
WHERE a.nfhs_district IS NOT NULL
UNION ALL
SELECT 'office', name, district, state, lat, lon, n, office_rank FROM (
  SELECT lower(trim(officename)) AS name,   -- office-type suffix (B.O, S.O, H.O) stripped in places.py
         district, statename AS state,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY try_cast(latitude AS DOUBLE)) AS lat,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY try_cast(longitude AS DOUBLE)) AS lon, count(*) AS n,
         min(CASE upper(officetype) WHEN 'HO' THEN 0 WHEN 'SO' THEN 1 ELSE 2 END) AS office_rank
  FROM {T_PINCODE}
  WHERE try_cast(latitude AS DOUBLE) BETWEEN {LAT_MIN} AND {LAT_MAX}
    AND try_cast(longitude AS DOUBLE) BETWEEN {LON_MIN} AND {LON_MAX}
  GROUP BY 1, 2, 3)
"""


def place_index(cn) -> list[dict]:
    return _rows(cn, PLACE_INDEX_SQL)


# Within a tier, facilities with real coordinates come before those placed only at a
# city or PIN centroid; then distance. Up to {per_tier} rows per tier.
SERVICE_SQL = """
SELECT * FROM (
  SELECT fs.unique_id, c.name, c.city, c.state, c.postcode, l.address,
         c.official_domain, c.official_phone, c.specialties, c.source_domains,
         l.final_lat, l.final_lon,
         {hav}(?, ?, l.final_lat, l.final_lon) AS distance_km,
         l.location_source, l.location_confidence, l.location_note,
         fs.tier, fs.n_explicit, fs.n_stated, fs.n_weak,
         fs.department_backing, fs.type_fit, fs.audit_verdict,
         {extra}
         to_json(fs.evidence) AS evidence_json,
         to_json(fs.warnings) AS warnings_json,
         row_number() OVER (
           PARTITION BY fs.tier
           ORDER BY CASE WHEN l.location_source IN ('city_point', 'pin_point') THEN 1 ELSE 0 END,
                    {hav}(?, ?, l.final_lat, l.final_lon), c.name) AS tier_rank
  FROM {tbl} fs
  JOIN {fc} c ON c.unique_id = fs.unique_id
  JOIN {loc} l ON l.facility_id = fs.unique_id
  WHERE fs.service = ?
    AND NOT coalesce(c.is_shifted, false)
    AND l.final_lat IS NOT NULL AND l.final_lon IS NOT NULL
    AND coalesce(l.location_confidence, 'none') <> 'none')
WHERE tier_rank <= ?
   -- city/PIN-centre facilities near the user are never cut by the per-tier cap
   OR (location_source IN ('city_point', 'pin_point') AND distance_km <= {city_km})
ORDER BY CASE tier WHEN 'Confirmed' THEN 0 WHEN 'Likely' THEN 1
                   WHEN 'Possible' THEN 2 WHEN 'Unverified' THEN 3 ELSE 4 END, tier_rank
"""

STATS_SQL = f"SELECT metric, value, build_ts FROM {T_BUILD_STATS}"


def _rows(cn, sql, params=None):
    with cn.cursor() as c:
        c.execute(sql, params or [])
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in c.fetchall()]


def is_fallback(location_source: str) -> bool:
    return location_source in FALLBACK_SOURCES


def location_text(r: dict) -> str:
    """Distance for a facility with real coordinates; for a centroid, no km at all."""
    if is_fallback(r["location_source"]):
        return f"in {r['city'] or 'this area'}, exact location unknown"
    return f"{r['distance_km']:.2f} km"


def pin_lookup(cn, pin: str) -> dict | None:
    """Point for a 6-digit PIN: pin_point (median of post offices), else the median
    computed from the PIN directory. Never rejected for spread; spread_km may be None."""
    pin = "".join(ch for ch in str(pin) if ch.isdigit())[:6]
    if len(pin) != 6:
        return None
    r = _rows(cn, PIN_SQL, [pin])
    if r:
        return r[0]
    try:
        m = _rows(cn, PIN_MEDIAN_SQL, [pin])
    except Exception:
        return None
    if m and m[0]["n_offices"] and m[0]["lat"] is not None:
        return {"pin": pin, "lat": m[0]["lat"], "lon": m[0]["lon"],
                "n_offices": m[0]["n_offices"], "spread_km": None}
    return None


def city_lookup(cn, name: str) -> dict | None:
    """Point for a city name, with n_facilities behind it. None if unknown."""
    if not name or not name.strip():
        return None
    r = _rows(cn, CITY_SQL, [name])
    return r[0] if r else None


# ------------------------------------------------------- service search ---
def service_sources(cn) -> dict[str, tuple[str, bool]]:
    """{service: (table, is_sample)} for every service label in the real contract
    table (except HIDDEN_SERVICES), plus sample-only services that have no real
    rows yet (marked is_sample, shown with the SAMPLE DATA banner)."""
    real = {r["service"] for r in _rows(
        cn, f"SELECT DISTINCT service FROM {T_SERVICE} WHERE service IS NOT NULL")}
    sample = {r["service"] for r in _rows(
        cn, f"SELECT DISTINCT service FROM {T_SERVICE_SAMPLE}")}
    out = {s: (T_SERVICE, False) for s in sorted(real - HIDDEN_SERVICES)}
    for s in sorted(sample - real - HIDDEN_SERVICES):
        out[s] = (T_SERVICE_SAMPLE, True)
    return out


def dropdown(sources: dict) -> list[tuple[str, str]]:
    """[(entry text "<Group> / <Service>", service label)]. The headline services
    appear only under "Common searches" (first); every other service under its
    group in config order; labels missing from config go to "Other specialties"."""
    out, seen = [], set()
    for s in COMMON_SEARCHES:
        if s in sources:
            out.append((f"Common searches / {service_name(s)}", s))
            seen.add(s)
    for grp, items in SERVICE_GROUPS.items():
        for s, _ in items:
            if s in sources and s not in seen:
                out.append((f"{grp} / {service_name(s)}", s))
                seen.add(s)
    for s in sorted(set(sources) - seen):
        out.append((f"Other specialties / {service_name(s)}", s))
    return out


def tag_coverage(cn) -> dict:
    """Tagging coverage stamped by the last verdict build:
    tagged = non-failed tags, attempted = distinct sentences tagged or failed."""
    r = _rows(cn, f"""SELECT max(n_sentences_tagged_at_build) AS tagged,
        max(n_sentences_attempted_at_build) AS attempted, max(build_ts) AS build_ts
        FROM {T_SERVICE}""")[0]
    tagged, attempted = r["tagged"] or 0, r["attempted"] or 0
    return {"pct": 100.0 * tagged / N_DISTINCT_SENTENCES,
            "complete": attempted >= N_DISTINCT_SENTENCES, "build_ts": r["build_ts"],
            "tagged": tagged, "attempted": attempted}


def confirmed_counts(cn) -> list[dict]:
    """Rows per service and tier in the real table (for the startup probe)."""
    return _rows(cn, f"""SELECT service, count_if(tier = 'Confirmed') AS confirmed,
        count(*) AS n FROM {T_SERVICE} GROUP BY service ORDER BY service""")


def build_stats(cn) -> dict:
    """{metric: value} plus '_build_ts' from workspace.vf.build_stats (written by each build)."""
    try:
        rows = _rows(cn, STATS_SQL)
    except Exception:
        return {}
    out = {r["metric"]: r["value"] for r in rows}
    out["_build_ts"] = rows[0]["build_ts"] if rows else None
    return out


def service_search(cn, table: str, service: str, user_lat: float,
                   user_lon: float, per_tier: int = 20) -> list[dict]:
    """Facilities with a verdict for `service`, up to `per_tier` per tier: best tier
    first; within a tier real coordinates before centroid-placed facilities, then
    nearest. tier_rank 1 is the tier's nearest. Location warnings are appended when
    the facility's point is weak."""
    extra = ("fs.facility_type, fs.flagged_share," if table == T_SERVICE
             else "CAST(NULL AS STRING) AS facility_type, CAST(NULL AS DOUBLE) AS flagged_share,")
    sql = SERVICE_SQL.format(hav=F_HAVERSINE, tbl=table, fc=T_FAC_CLEAN, loc=T_FAC_LOC,
                             extra=extra, city_km=CITY_BLOCK_KM)
    rows = _rows(cn, sql, [float(user_lat), float(user_lon), float(user_lat), float(user_lon),
                           service, int(per_tier)])
    for r in rows:
        r["evidence"] = json.loads(r.pop("evidence_json") or "[]")
        warns = json.loads(r.pop("warnings_json") or "[]")
        if r["location_confidence"] in WEAK_LOCATION and not is_fallback(r["location_source"]):
            warns.append(f"Location {r['location_confidence']}: "
                         f"{r['location_note'] or 'position not verified'}")
        r["warnings"] = warns
        r["specialties"] = list(r["specialties"]) if r["specialties"] is not None else []
        r["source_domains"] = list(r["source_domains"]) if r.get("source_domains") is not None else []
    return rows


# Blind web check (hand-checked against each facility's own website, without seeing our tier).
# Dialysis: tier at sampling time; two dialysis rules were tuned on this check, so it is not
# independent. Wave 3 (C-section, cardiac surgery): tier after the current build, untuned.
WEB_CHECK_SQL = f"""
SELECT service, tier, count_if(verdict IN ('yes', 'no')) AS checked,
       count_if(verdict = 'yes') AS yes, count_if(verdict = 'no') AS no,
       count_if(verdict = 'cannot tell') AS cannot_tell
FROM (SELECT 'dialysis' AS service, tier_at_sample AS tier, verdict FROM {TGT}.validation_dialysis
      UNION ALL
      SELECT service, tier_now AS tier, verdict FROM {TGT}.validation_wave3)
GROUP BY service, tier
"""
WEB_CHECK_TUNED = {"dialysis"}


def web_check(cn) -> dict:
    """{service: {"tuned": bool, "by_tier": {tier: {checked, yes, no, cannot_tell}}}}."""
    out = {}
    for r in _rows(cn, WEB_CHECK_SQL):
        s = out.setdefault(r["service"], {"tuned": r["service"] in WEB_CHECK_TUNED, "by_tier": {}})
        s["by_tier"][r["tier"]] = {k: int(r[k] or 0) for k in ("checked", "yes", "no", "cannot_tell")}
    return out

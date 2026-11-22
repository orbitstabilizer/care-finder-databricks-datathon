"""Care finder: FastAPI backend + static single-page front end.

All SQL lives in queries.py, names in config.py, the LLM matcher in matcher.py.
This file turns their rows into JSON the page can render directly."""
import os
import re
import threading
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import matcher
from places import PlaceIndex
from district_context import district_context
import queries as q
from conn import connect
from config import (PIN_TIGHT_KM, MIN_CITY_FACILITIES, TIER_ORDER, APP_SERVICES,
                    DEFAULT_SERVICE, TGT, service_name, facility_type_name,
                    HINT_SUPPLY_INDICATOR, HINT_RADIUS_KM, HINT_MAX, HINT_RELATED_FALLBACK,
                    HINT_RELATED_ALLOWED, HINT_TEXT, SERVICE_ALIASES)

HERE = os.path.dirname(os.path.abspath(__file__))
PER_TIER = 20
T_VALIDATION = f"{TGT}.validation_dialysis"

app = FastAPI(title="Care finder")

# ------------------------------------------------------------ connection ---
_local = threading.local()


def rows(fn, *a):
    """Run fn(cn, *a) on this thread's connection; reconnect once on failure."""
    for attempt in (0, 1):
        cn = getattr(_local, "cn", None)
        if cn is None:
            cn = _local.cn = connect()
        try:
            return fn(cn, *a)
        except Exception:
            _local.cn = None
            try:
                cn.close()
            except Exception:
                pass
            if attempt:
                raise


_cache: dict = {}
_places = {"idx": None}
_places_lock = threading.Lock()


def place_index():
    """Fuzzy place index, built once per process (~150k names, ~5 s)."""
    with _places_lock:
        if _places["idx"] is None:
            _places["idx"] = PlaceIndex(rows(q.place_index))
        return _places["idx"]


def cached(key, ttl, fn, *a):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = rows(fn, *a)
    _cache[key] = (time.time(), v)
    return v


def sources():
    return cached("sources", 300, q.service_sources)


# --------------------------------------------------------------- wording ---
TIER_MEANING = {
    "Confirmed": "Detailed evidence that this facility offers the service, backed by its "
                 "departments or more than one statement.",
    "Likely": "The facility's own text says it offers the service, but with less detail "
              "or backing.",
    "Possible": "No statement names the service, but the facility lists the matching "
                "department and offers a closely related service.",
    "Unverified": "The service is mentioned, but only weakly, in text that may belong to "
                  "another hospital, or at a kind of facility that rarely offers it.",
}
FIT_WORDS = {"expected": "is usual for", "plausible": "is possible at",
             "unexpected": "is unusual for"}
VERDICT_WORDS = {"consistent": "no sign of text from other hospitals",
                 "partly_foreign": "some text that may describe other organisations",
                 "mostly_foreign": "mostly text that appears to describe other organisations"}
LOCATION_WORDS = {
    "high": "Map position is exact and agrees with its postcode and city.",
    "good": "Map position is exact and agrees with its postcode or city.",
    "approximate": "Map position is approximate.",
    "suspect": "Map position may be wrong.",
    "unverified": "Map position could not be checked against its postcode or city.",
}


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def website(domain):
    if not domain:
        return None
    return domain if re.match(r"^https?://", domain) else f"https://{domain}"


def departments(specs, limit=10):
    words = list(dict.fromkeys(re.sub(r"(?<!^)([A-Z])", r" \1", s).lower() for s in specs))
    if not words:
        return None
    more = len(words) - limit
    return ", ".join(words[:limit]) + (f" and {more} more" if more > 0 else "")


def location_words(r):
    if q.is_fallback(r["location_source"]):
        area = "city" if r["location_source"] == "city_point" else "postcode area"
        return f"Exact location unknown; shown at the centre of its {area}."
    base = LOCATION_WORDS.get(r["location_confidence"], "Map position not checked.")
    if r["location_confidence"] in ("approximate", "suspect", "unverified") and r["location_note"]:
        base += f" ({r['location_note']})"
    return base


def why_lines(r, svc):
    name = service_name(svc)
    out = []
    if r["tier"] == "Possible":
        out.append(f"No statement names {name} directly; it is inferred from a related "
                   f"service the facility states (quoted).")
    else:
        out.append(f"{plural(r['n_explicit'] or 0, 'detailed statement')} and "
                   f"{plural(r['n_stated'] or 0, 'plain statement')} support {name}"
                   + (f"; {plural(r['n_weak'], 'weak mention')}." if r["n_weak"] else "."))
    out.append("The matching department is listed." if r["department_backing"] == "true"
               else "No matching department is listed.")
    ft = r.get("facility_type")
    if r.get("type_fit") in FIT_WORDS and (ft or "unknown") != "unknown":
        out.append(f"{name} {FIT_WORDS[r['type_fit']]} {facility_type_name(ft)}.")
    else:
        out.append("The kind of facility is not known, so fit was not checked.")
    if r.get("audit_verdict") is None:
        out.append("This record has not been checked for text from other hospitals.")
    else:
        share = r.get("flagged_share")
        pct = f"{share * 100:.0f}% of its sentences were flagged; " if share is not None else ""
        out.append(f"Check for text from other hospitals: {pct}"
                   f"{VERDICT_WORDS.get(r['audit_verdict'], r['audit_verdict'])}.")
    out.append(location_words(r))
    return out


def address(r):
    addr = r.get("address") or ", ".join(
        x for x in [r.get("city"), r.get("state"), r.get("postcode")] if x)
    parts, seen = [], set()
    for p in (addr or "").split(","):
        if p.strip() and p.strip().lower() not in seen:
            seen.add(p.strip().lower())
            parts.append(p.strip())
    return ", ".join(parts) or None


TRUSTED_LOCATION = ("high", "good")   # one rule for "nearest" everywhere

# Directory, social, insurance and map sites: listed after the facility's own and other sources.
AGGREGATORS = ("facebook.", "justdial.", "practo.", "mappls.", "medindia.", "onefivenine.", "proptiger.",
               "linkedin.", "policyx.", "lybrate.", "indiamart.", "docindia.", "hexahealth.", "medicineindia.",
               "scribd.", "latlong.", "instagram.", "bajajfinservhealth.", "healthfrog.", "chotu.", "drlogy.",
               "sulekha.", "clinicspots.", "cardiologistindia.", "grotal.", "bdir.", "healthinsuranceindia.",
               "policybazaar.", "zoominfo.", "myupchar.", "iffcotokio.", "insurancedekho.", "whatclinic.",
               "mapcarta.", "diagnosticcentres.", "myhospitalnow.", "youtube.", "twitter.", "x.com",
               "google.", "credihealth.", "quickerala.", "zoylo.", "docprime.", "1mg.", "medifee.",
               "hospitalsindia.", "joonsquare.", "asklaila.", "yellowpages.", "tripadvisor.")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


GENERIC_NAME_TOKENS = {
    "hospital", "hospitals", "clinic", "clinics", "centre", "center", "research", "medical", "institute",
    "multispeciality", "multispecialty", "multi", "speciality", "specialty", "super", "care", "health",
    "healthcare", "nursing", "home", "sciences", "science", "memorial", "trust", "foundation", "general",
    "city", "district", "government", "govt", "private", "limited", "diagnostic", "diagnostics", "dental",
    "maternity", "children", "child", "women", "mother", "life", "polyclinic", "laboratory", "labs",
    "heart", "kidney", "cancer", "superspeciality", "superspecialty", "and", "the", "with", "international",
    "national", "global", "family", "society", "mission", "charitable", "community", "primary", "rural",
    "urban", "civil", "eye", "surgical", "surgery", "orthopaedic", "orthopedic", "neuro", "speciality",
    "knee", "ortho",
}


LISTING_SITES = ("practo.", "justdial.", "lybrate.", "medindia.", "hexahealth.", "credihealth.", "mappls.",
                 "maps.google.", "google.com/maps", "sulekha.", "docindia.", "clinicspots.", "bajajfinservhealth.",
                 "drlogy.", "healthfrog.", "myupchar.", "whatclinic.", "quickerala.", "zoylo.", "medifee.",
                 "myhospitalnow.", "onefivenine.", "grotal.", "asklaila.")


def _own_tokens(r) -> list[str]:
    """Distinctive name tokens (>= 4 chars, not generic, not the city). If there are none, a 3-letter
    first word (e.g. "Raj") is allowed."""
    city = set(re.split(r"[^a-z0-9]+", str(r.get("city") or "").lower()))
    toks = [t for t in re.split(r"[^a-z0-9]+", str(r.get("name") or "").lower()) if t]
    out = [t for t in toks if len(t) >= 4 and t not in GENERIC_NAME_TOKENS and t not in city]
    if not out and toks and len(toks[0]) == 3 and toks[0] not in GENERIC_NAME_TOKENS and toks[0] not in city:
        out = [toks[0]]
    return out


def _acronym(r) -> str:
    """Initials of the name's words (city and generic words count; of/and/the do not)."""
    words = [w for w in re.split(r"[^a-z0-9]+", str(r.get("name") or "").lower()) if w and w not in ("of", "and", "the")]
    return "".join(w[0] for w in words)


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _is_own(d: str, toks: list[str], acro: str) -> bool:
    """Domain belongs to the facility: contains a name token; or its first label shares a >= 5-letter
    prefix with a >= 5-letter token covering all but at most its last letter ("anupama" ~ "anupamhospital");
    or the first label starts with the name's initials (>= 3 letters, "ccl" ~ "ccllab")."""
    host = d.split("/")[0]
    labels = [x for x in host.split(".") if x != "www"]
    first = labels[0] if labels else ""
    if any(t in host.rsplit(".", 1)[0] for t in toks):
        return True
    for t in toks:
        if len(t) >= 5:
            p = _common_prefix(t, first)
            if p >= 5 and p >= len(t) - 1:
                return True
    return len(acro) >= 3 and first.startswith(acro)


def source_list(r) -> list[dict]:
    """Up to 3 source domains we can stand behind: domains matching the facility's name (official domain
    first), then well-known directory listings. Any other domain is never shown: it may belong to a
    different hospital merged into this record. [] means listings only or nothing."""
    official = (r.get("official_domain") or "").lower() or None
    doms = list(dict.fromkeys(d.lower() for d in ([official] + (r.get("source_domains") or [])) if d))
    toks, acro = _own_tokens(r), _acronym(r)
    own = [d for d in doms if _is_own(d, toks, acro)]
    own.sort(key=lambda d: d != official)
    listing = [d for d in doms if d not in own and any(a in d for a in LISTING_SITES)]
    return ([{"domain": d, "listing": False} for d in own] + [{"domain": d, "listing": True} for d in listing])[:3]


def position_line(tier, i, r, nearest) -> str:
    """One line on why the card sits where it does in its tier."""
    if q.is_fallback(r["location_source"]):
        return f"{tier} · exact address unknown, listed after facilities with a map position"
    if nearest is not None and r["unique_id"] == nearest["unique_id"]:
        return f"{tier} · nearest {tier} with an exact location"
    d = r["distance_km"]
    if r.get("location_confidence") not in TRUSTED_LOCATION:
        return f"Ranked {_ordinal(i)} in {tier}: about {round(d)} km, location uncertain"
    return f"Ranked {_ordinal(i)} in {tier}: {d:.1f} km"


def card(r, svc):
    fb = q.is_fallback(r["location_source"])
    tn = facility_type_name(r.get("facility_type"), with_article=False)
    uncertain = not fb and r.get("location_confidence") not in TRUSTED_LOCATION
    loc_text = (f"about {round(r['distance_km'])} km, location uncertain" if uncertain
                else q.location_text(r))
    return {
        "id": r["unique_id"], "name": r["name"], "city": r["city"], "state": r["state"],
        "tier": r["tier"], "lat": r["final_lat"], "lon": r["final_lon"],
        "distance_km": None if fb else round(r["distance_km"], 2),
        "exact_location": not fb,
        "location_trusted": r.get("location_confidence") in TRUSTED_LOCATION,
        "location_uncertain": uncertain,
        "location_text": loc_text,
        "evidence": [{"sentence": e.get("sentence"), "source_column": e.get("source_column")}
                     for e in r["evidence"]],
        "warnings": r["warnings"],
        "sources": source_list(r),
        "why": why_lines(r, svc),
        "details": {
            "address": address(r), "phone": r.get("official_phone"),
            "website": website(r.get("official_domain")), "domain": r.get("official_domain"),
            "type": tn[:1].upper() + tn[1:],
            "departments": departments(r.get("specialties") or []),
            "location_confidence": location_words(r),
            "directions_url": ("https://www.google.com/maps/dir/?api=1&destination="
                               f"{r['final_lat']},{r['final_lon']}"),
            "directions_approximate": fb,
        },
    }


# ------------------------------------------------------------- endpoints ---
@app.get("/api/services")
def api_services():
    src = sources()
    cov = cached("coverage", 300, q.tag_coverage)
    out = []
    for entry, s in q.dropdown(src):
        group, _, name = entry.partition(" / ")
        _, is_sample = src[s]
        note = None
        if is_sample:
            note = "Sample data only: placeholder tiers, not real recommendations."
        elif s not in APP_SERVICES and not cov["complete"]:
            note = f"Results still loading, coverage {cov['pct']:.0f}%."
        out.append({"label": s, "entry": entry, "group": group, "name": name,
                    "is_sample": is_sample, "coverage_note": note,
                    "aliases": [s.replace("_", " ")] + SERVICE_ALIASES.get(s, [])})
    return {"services": out, "default": DEFAULT_SERVICE}


class MatchIn(BaseModel):
    text: str


@app.post("/api/match")
def api_match(body: MatchIn):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    key = ("match", text.lower())
    hit = _cache.get(key)
    if hit:
        res = hit[1]
    else:
        res = matcher.match(text)
        if not res.get("error"):
            _cache[key] = (time.time(), res)
    svcs = res["services"]
    # auto-search only when the text names a service and the match is confident
    auto = res.get("kind") == "service" and res["confidence"] == "high" and bool(svcs)
    return {**res, "matched": svcs[0] if auto else None,
            "alternatives": [{"label": s, "name": service_name(s)}
                             for s in (svcs[1:] if auto else svcs)],
            "labels": [{"label": s, "name": service_name(s)} for s in svcs],
            "options": [{**o, "label": o["service"], "name": service_name(o["service"])}
                        for o in res.get("options", [])]}


@app.get("/api/resolve")
def api_resolve(pin: str | None = None, place: str | None = None):
    if pin:
        rec = rows(q.pin_lookup, pin)
        if rec is None:
            raise HTTPException(404, "No point known for that PIN code.")
        spread = rec.get("spread_km")
        notes = []
        if spread is None or spread > PIN_TIGHT_KM:
            notes.append("PIN covers a wide area, distances are approximate.")
        return {"lat": rec["lat"], "lon": rec["lon"],
                "origin": f"PIN {rec['pin']}, middle of its {rec['n_offices']} post offices",
                "notes": notes}
    if place:
        idx = place_index()
        hit = idx.resolve(place)
        if hit is None:
            raise HTTPException(404, "No place by that name in our data. Try a city, district or "
                                     "PIN code, or click the map.")
        r = hit["place"]
        label = idx.label(r)
        n = r.get("n") or 0
        note = {
            "city": f"Approximate: the centre of {n} facilities in this place.",
            "district": f"Approximate: the middle of the district's {n} PIN codes.",
            "alias": f"Approximate: the middle of the district's {n} PIN codes "
                     f"(district also known as {str(r['name']).title()}).",
            "office": "Approximate: the post office's location.",
        }[r["kind"]]
        return {"lat": r["lat"], "lon": r["lon"], "origin": label, "notes": [note],
                "matched": {"query": place.strip(), "name": label, "kind": r["kind"],
                            "exact": hit["exact"], "score": hit["score"]},
                "alternatives": hit["alternatives"]}
    raise HTTPException(400, "Give pin or place.")


@app.get("/api/search")
def api_search(service: str, lat: float = Query(...), lon: float = Query(...)):
    src = sources()
    if service not in src:
        raise HTTPException(404, f"Unknown service {service}")
    tbl, is_sample = src[service]
    t0 = time.time()
    key = ("search", service, round(lat, 5), round(lon, 5))
    rs = cached(key, 600, q.service_search, tbl, service, lat, lon, PER_TIER)
    tiers, summary, nearest = [], [], {}
    for t in TIER_ORDER:
        trs = [r for r in rs if r["tier"] == t]
        # centre-placed facilities within CITY_BLOCK_KM get their own block (never cut by the cap)
        near_fb = [r for r in trs if q.is_fallback(r["location_source"])
                   and r["distance_km"] is not None and r["distance_km"] <= q.CITY_BLOCK_KM]
        near_ids = {r["unique_id"] for r in near_fb}
        main_rs = [r for r in trs if r["unique_id"] not in near_ids]
        ok = [r for r in trs if r.get("location_confidence") in TRUSTED_LOCATION]
        n = min(ok, key=lambda r: r["distance_km"]) if ok else None
        nearest[t] = n
        items = []
        for i, r in enumerate(main_rs, 1):
            c = card(r, service)
            c["position"] = position_line(t, i, r, n)
            items.append(c)
        city_items = []
        for r in near_fb:
            c = card(r, service)
            c["position"] = f"{t} · in this city, exact address unknown"
            city_items.append(c)
        if trs:
            # nearest = nearest facility with a high/good location; note a closer uncertain one
            weak = [r["distance_km"] for r in trs
                    if r.get("location_confidence") not in TRUSTED_LOCATION
                    and r.get("distance_km") is not None
                    and (n is None or r["distance_km"] < n["distance_km"])]
            summary.append({"tier": t, "name": n["name"] if n else None,
                            "city": n["city"] if n else None,
                            "distance_km": round(n["distance_km"], 2) if n else None,
                            "exact_location": n is not None, "trusted": n is not None,
                            "closer_uncertain_km": round(min(weak)) if weak else None})
        capped = sum(1 for r in trs if r.get("tier_rank", 0) <= PER_TIER) == PER_TIER
        tiers.append({"tier": t, "meaning": TIER_MEANING[t], "count": len(items) + len(city_items),
                      "capped": capped, "results": items, "city_block": city_items})
    # "Closest credible option": a trusted Likely at under half the distance of the nearest trusted
    # Confirmed (or no trusted Confirmed at all). Context line only; tiers and order are unchanged.
    nc, nl = nearest.get("Confirmed"), nearest.get("Likely")
    credible = None
    if nl and (nc is None or nl["distance_km"] < 0.5 * nc["distance_km"]):
        credible = {"id": nl["unique_id"], "name": nl["name"], "city": nl["city"],
                    "distance_km": round(nl["distance_km"], 1),
                    "confirmed_km": round(nc["distance_km"], 1) if nc else None}
    # "Call the Likely ones first" only when a trusted Likely is nearer than the nearest trusted Confirmed.
    far_note = nl is not None and (nc is None or nl["distance_km"] < nc["distance_km"])
    for t in tiers:   # the nearest Confirmed card says how many trusted Likely are closer
        if t["tier"] == "Confirmed" and nc:
            closer = sum(1 for r in rs if r["tier"] == "Likely"
                         and r.get("location_confidence") in TRUSTED_LOCATION
                         and r["distance_km"] < nc["distance_km"])
            for c in t["results"]:
                if c["id"] == nc["unique_id"] and closer:
                    c["position"] += f"; {closer} Likely {'option is' if closer == 1 else 'options are'} closer, see below"
    return {"service": service, "service_name": service_name(service),
            "is_sample": is_sample, "point": {"lat": lat, "lon": lon},
            "summary": summary, "tiers": tiers, "n": len(rs),
            "closest_credible": credible, "far_confirmed_note": far_note,
            "web_check": _web_check(service),
            "query_s": round(time.time() - t0, 2)}


def _web_check(service):
    """Blind web-check counts for this service, or None if it was never checked."""
    try:
        wc = cached("web_check", 300, q.web_check)
    except Exception:
        return None
    w = wc.get(service)
    if not w:
        return None
    return {"tuned": w["tuned"],
            "by_tier": [{"tier": t, **w["by_tier"][t]} for t in TIER_ORDER if t in w["by_tier"]]}


def _validation(cn):
    return q._rows(cn, f"""SELECT tier_at_sample AS tier, verdict, count(*) AS n
        FROM {T_VALIDATION} GROUP BY ALL""")


@app.get("/api/district_context")
def api_district_context(service: str, lat: float | None = None, lon: float | None = None,
                         pin: str | None = None):
    """NFHS-5 district context for the search point. Context only: never touches tier or order."""
    if lat is None and not pin:
        raise HTTPException(400, "Give lat/lon or pin.")
    pin = (pin or "").strip() or None
    key = ("district", service, None if lat is None else round(lat, 4),
           None if lon is None else round(lon, 4), pin)
    ctx = cached(key, 600, lambda cn: district_context(lat, lon, pin, service, conn=cn))
    try:
        hint = cached(("hint",) + key[1:], 600, lambda cn: _district_hint(cn, service, ctx))
    except Exception as e:   # the hint is optional; context still returns
        print(f"HINT failed: {type(e).__name__}: {e}", flush=True)
        hint = None
    return {**ctx, "hint": hint}


def _district_hint(cn, service, ctx):
    """Suggestion block, separate from tiers (never changes tier or order). Shown when:
    - the service has a SUPPLY-signal NFHS indicator (config.HINT_SUPPLY_INDICATOR; need indicators
      such as blood sugar are never used),
    - the district's value is "high" = at or above the median of all 706 NFHS-5 districts (top half),
    - no facility is Confirmed for the service within HINT_RADIUS_KM (30 km) of the search point,
    - at least one facility within 30 km is Confirmed or Likely for a related maternity service
      (service_department_map link_type 'implied_by_service', limited to HINT_RELATED_ALLOWED).
    Lists up to HINT_MAX nearest such facilities with their related tier and one quoted sentence."""
    col = HINT_SUPPLY_INDICATOR.get(service)
    lat, lon, nk = ctx.get("point_lat"), ctx.get("point_lon"), ctx.get("nfhs_key")
    if not col or lat is None or not nk:
        return None
    d = q.hint_district(cn, service, col, nk, lat, lon, HINT_RADIUS_KM)
    if not d or d["value"] is None or d["median"] is None:
        return None
    if d["value"] < d["median"] or d["n_confirmed_near"]:
        return None
    related = [s for s in (q.related_services(cn, service) or HINT_RELATED_FALLBACK.get(service, []))
               if s in HINT_RELATED_ALLOWED and s != service]
    if not related:
        return None
    facs = q.hint_facilities(cn, related, lat, lon, HINT_RADIUS_KM, HINT_MAX)
    if not facs:
        return None
    head, follow = HINT_TEXT[service]
    items = []
    for f in facs:
        fb = q.is_fallback(f["location_source"])
        km = f["distance_km"]
        where = (f"in {f['city'] or 'this area'}, exact address unknown" if fb
                 else f"about {round(km)} km" if f.get("location_confidence") not in TRUSTED_LOCATION
                 else f"{km:.1f} km")
        items.append({"id": f["unique_id"], "name": f["name"], "city": f["city"],
                      "distance_km": round(km, 1), "where": where,
                      "service": f["service"], "service_name": service_name(f["service"]),
                      "tier": f["tier"], "sentence": f["sentence"]})
    return {"headline": head.format(v=round(float(d["value"]))), "text": follow,
            "indicator": col, "value": float(d["value"]), "median_706": float(d["median"]),
            "radius_km": HINT_RADIUS_KM, "facilities": items}


@app.get("/api/stats")
def api_stats():
    stats = cached("stats", 300, q.build_stats)
    ts = stats.get("_build_ts")
    funnel = {k: v for k, v in stats.items() if not k.startswith("_")}
    try:
        vrows = cached("validation", 300, _validation)
    except Exception:
        vrows = []
    v = {}
    for r in vrows:
        v.setdefault(r["tier"], {})[r["verdict"]] = r["n"]
    line = None
    if v:
        total = sum(sum(d.values()) for d in v.values())

        def frac(t):
            d = v.get(t, {})
            return d.get("yes", 0), d.get("yes", 0) + d.get("no", 0)
        top = [frac(t) for t in ("Confirmed", "Likely", "Possible")]
        all_yes = all(y == n for y, n in top)
        uy, un = frac("Unverified")
        line = (f"Spot check: of {total} dialysis facilities checked blind against their own "
                f"websites, " +
                ("every Confirmed, Likely and Possible facility that could be checked offers "
                 "dialysis" if all_yes else
                 "Confirmed, Likely and Possible facilities that could be checked offer dialysis")
                + f" ({', '.join(f'{y}/{n}' for y, n in top)}); among Unverified, "
                f"{uy} of {un} did.")
    return {"funnel": funnel, "build_ts": ts.isoformat() if ts else None,
            "validation": {"line": line, "by_tier": v}}


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/india.geojson")
def india():
    return FileResponse(os.path.join(HERE, "india.geojson"), media_type="application/geo+json")


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.on_event("startup")
def _warm_places():
    """Build the place index in the background so the first place search is fast."""
    def run():
        try:
            place_index()
        except Exception as e:  # place search falls back to building it on demand
            print(f"PLACES warm failed: {type(e).__name__}: {e}", flush=True)
    threading.Thread(target=run, daemon=True).start()

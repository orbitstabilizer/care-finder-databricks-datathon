"""Find facilities offering a service near a point in India, with quoted
evidence and a confidence tier."""
import html
import json
import os
import re
import time

import folium
import streamlit as st
from streamlit_folium import st_folium

import matcher
import queries as q
from conn import connect
from config import (PIN_TIGHT_KM, MIN_CITY_FACILITIES, TIER_ORDER, APP_SERVICES,
                    DEFAULT_SERVICE, service_name, facility_type_name)

st.set_page_config(page_title="Care finder", layout="wide")

INDIA_CENTRE = (22.5, 82.5)
INDIA_BOUNDS = (6.0, 68.0, 37.5, 98.0)   # min lat, min lon, max lat, max lon (pan limit)
# Simplified India outline (Natural Earth admin-0 1:110m, bundled; no runtime download).
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "india.geojson")) as _f:
    INDIA_RING = [(lon, lat) for lon, lat in json.load(_f)["geometry"]["coordinates"][0]]


def in_india(lat, lon):
    """Ray-casting point-in-polygon against the bundled India outline."""
    inside, n = False, len(INDIA_RING)
    for i in range(n):
        x1, y1 = INDIA_RING[i]
        x2, y2 = INDIA_RING[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside
PER_TIER = 20      # rows fetched per tier
FIRST_SHOWN = 5    # rows shown per tier before "Show more"
STEP = 5


@st.cache_resource
def conn():
    return connect()


@st.cache_data(ttl=300, show_spinner=False)
def _service_sources():
    return q.service_sources(conn())


@st.cache_data(ttl=300, show_spinner=False)
def _tag_coverage():
    return q.tag_coverage(conn())


@st.cache_data(ttl=300, show_spinner=False)
def _build_stats():
    return q.build_stats(conn())


@st.cache_data(ttl=600, show_spinner=False)
def _service_search(table, service, lat, lon):
    t0 = time.time()
    return q.service_search(conn(), table, service, lat, lon, PER_TIER), time.time() - t0


TIER_BADGE = {"Confirmed": "🟢 Confirmed", "Likely": "🟡 Likely",
              "Possible": "🔵 Possible", "Unverified": "⚪ Unverified"}
TIER_COLOUR = {"Confirmed": "green", "Likely": "orange", "Possible": "blue",
               "Unverified": "gray"}
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


# ------------------------------------------------------------- helpers ---
def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def type_words(ft):
    return (ft or "unknown").replace("_", " ")


def article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def website(domain):
    if not domain:
        return None
    return domain if re.match(r"^https?://", domain) else f"https://{domain}"


def directions(r):
    return (f"https://www.google.com/maps/dir/?api=1&destination="
            f"{r['final_lat']},{r['final_lon']}")


def departments(specs, limit=10):
    words = [re.sub(r"(?<!^)([A-Z])", r" \1", s).lower() for s in specs]
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
                   f"service the facility states (quoted above).")
    else:
        out.append(f"{plural(r['n_explicit'] or 0, 'detailed statement')} and "
                   f"{plural(r['n_stated'] or 0, 'plain statement')} support {name}"
                   + (f"; {plural(r['n_weak'], 'weak mention')}." if r["n_weak"] else "."))
    out.append("The matching department is listed." if r["department_backing"] == "true"
               else "No matching department is listed.")
    tw = type_words(r.get("facility_type"))
    if r.get("type_fit") in FIT_WORDS and tw != "unknown":
        out.append(f"{name} {FIT_WORDS[r['type_fit']]} {facility_type_name(r.get('facility_type'))}.")
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


def details_lines(r):
    out = []
    addr = r.get("address") or ", ".join(
        x for x in [r.get("city"), r.get("state"), r.get("postcode")] if x)
    parts, seen = [], set()
    for p_ in (addr or "").split(","):          # drop repeated comma-separated parts
        if p_.strip() and p_.strip().lower() not in seen:
            seen.add(p_.strip().lower())
            parts.append(p_.strip())
    addr = ", ".join(parts)
    if addr:
        out.append(f"**Address:** {addr}")
    if r.get("official_phone"):
        out.append(f"**Phone:** {r['official_phone']}")
    url = website(r.get("official_domain"))
    if url:
        out.append(f"**Website:** [{r['official_domain']}]({url})")
    tn = facility_type_name(r.get("facility_type"), with_article=False)
    out.append(f"**Type:** {tn[:1].upper() + tn[1:]}")
    deps = departments(r.get("specialties") or [])
    if deps:
        out.append(f"**Departments listed:** {deps}")
    out.append(f"**Location:** {location_words(r)}")
    label = ("Directions (approximate: city or postcode centre)"
             if q.is_fallback(r["location_source"]) else "Directions")
    out.append(f"[{label}]({directions(r)})")
    return out


def popup_html(r):
    e = html.escape
    parts = [f"<b>{e(r['name'])}</b>", f"{e(r['tier'])} · {e(q.location_text(r))}"]
    if r.get("official_phone"):
        parts.append(f"Phone: {e(r['official_phone'])}")
    url = website(r.get("official_domain"))
    if url:
        parts.append(f'<a href="{e(url)}" target="_blank">Website</a>')
    parts.append(f'<a href="{e(directions(r))}" target="_blank">Directions'
                 f'{" (approximate)" if q.is_fallback(r["location_source"]) else ""}</a>')
    return "<br>".join(parts)


def nearest_summary(by_tier):
    bits = []
    for t in TIER_ORDER:
        if by_tier.get(t):
            r = by_tier[t][0]
            where = (f"in {r['city'] or 'its area'}" if q.is_fallback(r["location_source"])
                     else f"{r['distance_km']:.0f} km" if r["distance_km"] >= 10
                     else f"{r['distance_km']:.1f} km")
            bits.append(f"nearest {t} {where}")
    text = ", ".join(bits)
    return text[:1].upper() + text[1:]


def how_it_works(stats):
    def n(k):
        v = stats.get(k)
        return f"{v:,}" if v is not None else "?"
    return (
        f"We read {n('sentences_read')} sentences about {n('facilities')} facilities "
        f"({n('distinct_sentences')} distinct; {n('distinct_sentences_tagged')} classified so far). "
        f"{n('service_claim_sentences')} distinct sentences say a facility offers a service. "
        f"{n('records_mixed')} of {n('facilities_audited')} checked records appear mixed with "
        f"another hospital's text; their flagged sentences are never quoted.\n\n"
        "- **Confirmed:** a detailed statement (numbers, units, beds) plus a matching department, "
        "a second statement, or a usual fit for the facility type.\n"
        "- **Likely:** at least one detailed or plain statement.\n"
        "- **Possible:** no statement, but the matching department plus a related service.\n"
        "- **Unverified:** only weak mentions, mostly another hospital's text, or a facility "
        "type that rarely offers the service.\n\n"
        "Within each tier, exact locations come first, then distance."
        + (f"\n\nNumbers as of {stats['_build_ts']:%Y-%m-%d %H:%M} UTC."
           if stats.get("_build_ts") else ""))


# ------------------------------------------------------------------ page ---
st.title("Care finder")
st.caption("Find the nearest facilities that offer a medical service, with the quoted "
           "evidence behind each one and how confident we are.")
SVC_SOURCES = _service_sources()
banner = st.empty()
with st.expander("How this works"):
    st.markdown(how_it_works(_build_stats()))

ss = st.session_state
ss.setdefault("point", None)      # (lat, lon)
ss.setdefault("origin", None)     # how the point was set
ss.setdefault("pin_note", None)   # wide-PIN caveat
ss.setdefault("shown", {})        # tier -> rows shown
ss.setdefault("search_key", None)

# ---------------------------------------------------------------- inputs ---
side, main = st.columns([1, 2.4])

with side:
    entries = q.dropdown(SVC_SOURCES)
    labels = [e for e, _ in entries]
    entry_of = {}
    for e, s_ in entries:
        entry_of.setdefault(s_, e)
    default = next((e for e, s_ in entries if s_ == DEFAULT_SERVICE), labels[0])
    if ss.get("svc_choice") not in labels:
        ss["svc_choice"] = default

    # free-text need -> service labels (one LLM call per distinct text, cached in session)
    with st.form("need_form", clear_on_submit=False, border=False):
        need = st.text_input("Describe what you need",
                             placeholder="e.g. my father needs a kidney machine")
        asked = st.form_submit_button("Find the service", use_container_width=True)
    if asked and need.strip():
        cache = ss.setdefault("match_cache", {})
        key_ = need.strip().lower()
        if key_ not in cache:
            with st.spinner("Matching your words to a service…"):
                cache[key_] = matcher.match(need.strip())
        res = cache[key_]
        ss["match"] = res
        svcs = [s_ for s_ in res["services"] if s_ in entry_of]
        if res["confidence"] in ("high", "medium") and svcs:
            ss["svc_choice"] = entry_of[svcs[0]]
    res = ss.get("match")
    if res:
        svcs = [s_ for s_ in res["services"] if s_ in entry_of]
        auto = res["confidence"] in ("high", "medium") and svcs
        if auto:
            st.success(f"Matched: {service_name(svcs[0])}")
            alts = svcs[1:]
        else:
            alts = svcs
            st.info("Pick a service from the list."
                    + (" Suggestions below." if svcs else ""))
        for s_ in alts:
            if st.button(f"Or: {service_name(s_)}", key=f"alt_{s_}", use_container_width=True):
                ss["svc_choice"] = entry_of[s_]
                st.rerun()
        st.caption("This only matches words to a service; it is not medical advice.")

    choice = st.selectbox("Service (type to search)", labels, key="svc_choice")
    service = dict(entries).get(choice)
    SVC_TABLE, IS_SAMPLE = SVC_SOURCES.get(service, (None, False))
    if IS_SAMPLE:
        banner.error("**SAMPLE DATA — not real recommendations.** The verdict "
                     "table `facility_service` has no rows for this service yet, "
                     "so results come from marked sample rows (real facilities "
                     "and real quoted sentences, but placeholder tiers).")
    cov = _tag_coverage()
    if service and service not in APP_SERVICES and not cov["complete"]:
        st.caption(f"Results still loading, coverage {cov['pct']:.0f}%")

    st.markdown("**PIN code**")
    pin_in = st.text_input("PIN code", max_chars=10, label_visibility="collapsed",
                           placeholder="411001")
    if st.button("Use this PIN", use_container_width=True):
        rec = q.pin_lookup(conn(), pin_in)
        if rec is None:
            st.error("No point known for that PIN code.")
        else:
            ss.point = (rec["lat"], rec["lon"])
            spread = rec.get("spread_km")
            ss.origin = f"PIN {rec['pin']} — middle of its {rec['n_offices']} post offices"
            ss.pin_note = (None if spread is not None and spread <= PIN_TIGHT_KM
                           else "PIN covers a wide area, distances are approximate")

    st.markdown("**Place name**")
    city_in = st.text_input("Place name", label_visibility="collapsed",
                            placeholder="Udaipur")
    if st.button("Use this place", use_container_width=True):
        rec = q.city_lookup(conn(), city_in)
        if rec is None:
            st.error(f"No point known for that place. A place needs at least "
                     f"{MIN_CITY_FACILITIES} facilities with good coordinates "
                     f"to get one.")
        else:
            ss.point = (rec["lat"], rec["lon"])
            ss.origin = (f"{rec['city_key'].title()} — approximate, the centre of "
                         f"{rec['n_facilities']} facilities in this place")
            ss.pin_note = None

    if ss.point:
        if st.button("Clear point", use_container_width=True):
            ss.point, ss.origin, ss.pin_note = None, None, None

# ---------------------------------------------------------------- search ---
rows, elapsed = ([], None)
if ss.point and service and SVC_TABLE:
    rows, elapsed = _service_search(SVC_TABLE, service, ss.point[0], ss.point[1])
key = (service, ss.point)
if ss.search_key != key:          # new search: reset "show more"
    ss.search_key, ss.shown = key, {}
by_tier = {t: [r for r in rows if r["tier"] == t] for t in TIER_ORDER}
shown_rows = [r for t in TIER_ORDER for r in by_tier[t][:ss.shown.get(t, FIRST_SHOWN)]]

# ------------------------------------------------------------------- map ---
with main:
    centre = ss.point or INDIA_CENTRE
    lat0, lon0, lat1, lon1 = INDIA_BOUNDS
    m = folium.Map(location=list(centre), zoom_start=11 if ss.point else 5, min_zoom=4,
                   max_bounds=True, min_lat=lat0, max_lat=lat1, min_lon=lon0, max_lon=lon1)
    # gray mask over the world with India cut out; not interactive, so clicks reach the map
    folium.Polygon(
        locations=[[[-89, -179], [-89, 179], [89, 179], [89, -179]],
                   [[lat, lon] for lon, lat in INDIA_RING]],
        color=None, weight=0, fill=True, fill_color="#808080", fill_opacity=0.45,
        interactive=False).add_to(m)
    if ss.point:
        folium.Marker(list(ss.point), tooltip="Your point",
                      icon=folium.Icon(color="black", icon="screenshot")).add_to(m)
    for r in shown_rows:
        folium.Marker(
            [r["final_lat"], r["final_lon"]],
            tooltip=f"{r['name']} — {r['tier']} — {q.location_text(r)}",
            popup=folium.Popup(popup_html(r), max_width=300),
            icon=folium.Icon(color=TIER_COLOUR.get(r["tier"], "gray")),
        ).add_to(m)
    if ss.point and shown_rows:
        # fit the view to the search point plus every shown facility
        pts = [list(ss.point)] + [[r["final_lat"], r["final_lon"]] for r in shown_rows]
        m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)],
                      [max(p[0] for p in pts), max(p[1] for p in pts)]],
                     padding=(30, 30), max_zoom=14)

    out = st_folium(m, height=520, use_container_width=True, key="map")
    click = (out or {}).get("last_clicked")
    if click and not in_india(click["lat"], click["lng"]):
        st.warning("Please choose a point in India.")
    elif click and (ss.origin != "map" or ss.point != (click["lat"], click["lng"])):
        if ss.point != (click["lat"], click["lng"]):
            ss.point = (click["lat"], click["lng"])
            ss.origin, ss.pin_note = "map", None
            st.rerun()


# --------------------------------------------------------------- results ---
def card(r, svc):
    with st.container(border=True):
        st.markdown(f"**{r['name']}** — {r['city'] or ''}"
                    f"{', ' + r['state'] if r['state'] else ''}  \n"
                    f"{q.location_text(r)}"
                    f"{'' if q.is_fallback(r['location_source']) else ' away'} · "
                    f"{TIER_BADGE.get(r['tier'], r['tier'])}")
        for e in r["evidence"][:3]:
            st.markdown(f"> “{e['sentence']}”  \n"
                        f"> <small>source column: `{e['source_column']}`</small>",
                        unsafe_allow_html=True)
        if not r["evidence"]:
            st.caption("No quoted evidence.")
        for w in r["warnings"]:
            st.markdown(f":orange[⚠ {w}]")
        with st.expander("Why this result · Details"):
            st.markdown("**Why this result**")
            st.markdown("\n".join(f"- {line}" for line in why_lines(r, svc)))
            st.markdown("**Details**")
            st.markdown("  \n".join(details_lines(r)))


def section(t, svc):
    items = by_tier[t]
    n = ss.shown.get(t, FIRST_SHOWN)
    st.caption(TIER_MEANING[t])
    for r in items[:n]:
        card(r, svc)
    if len(items) > n:
        more = min(STEP, len(items) - n)
        if st.button(f"Show {more} more {t}", key=f"more_{t}"):
            ss.shown[t] = n + STEP
            st.rerun()
    elif len(items) == PER_TIER:
        st.caption(f"Showing the nearest {PER_TIER}.")


if not ss.point:
    st.info("No point chosen yet. Click the map, or enter a PIN code or place name.")
else:
    lat, lon = ss.point
    note = "exact point you clicked" if ss.origin == "map" else ss.origin
    st.success(f"**{lat:.5f}, {lon:.5f}** — {note}")
    if ss.pin_note:
        st.warning(ss.pin_note)
    if (ss.get("match") or {}).get("emergency"):
        st.error("If this is an emergency, call 112.")
    summary = nearest_summary(by_tier)
    if summary:
        st.markdown(f"**{summary}**")
    st.caption(f"Query took {elapsed or 0:.2f} s. Within each tier, facilities with an exact "
               "location come first, then by distance. Column-shifted records and facilities "
               "with no usable position are left out.")
    if not rows:
        st.info("No facility has evidence for this service.")
    for t in TIER_ORDER:
        if not by_tier[t]:
            continue
        label = f"{TIER_BADGE[t]} ({len(by_tier[t])}{'+' if len(by_tier[t]) == PER_TIER else ''})"
        if t == "Unverified":
            # a toggle, not an expander: cards contain expanders, which cannot be nested
            st.subheader(label)
            if st.toggle("Show Unverified results", value=False, key="show_unverified"):
                section(t, service)
        else:
            st.subheader(label)
            section(t, service)

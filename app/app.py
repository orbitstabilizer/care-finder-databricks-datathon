"""Find the nearest facilities to a point in India, and say how much to trust
each facility's position."""
import time

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import queries as q
from conn import connect
from config import NEAR_KM, PIN_TIGHT_KM, MIN_CITY_FACILITIES

st.set_page_config(page_title="Facility finder", layout="wide")

INDIA_CENTRE = (22.0, 79.0)
COLOUR = {"high": "green", "good": "blue", "approximate": "orange",
          "suspect": "red", "none": "lightgray"}
BADGE = {"high": "🟢 high", "good": "🔵 good", "approximate": "🟠 approximate",
         "suspect": "🔴 suspect", "none": "⚪ none"}


@st.cache_resource
def conn():
    return connect()


@st.cache_data(ttl=600, show_spinner=False)
def _nearest(lat, lon, limit):
    t0 = time.time()
    return q.nearest(conn(), lat, lon, limit), time.time() - t0


@st.cache_data(ttl=3600, show_spinner=False)
def _unlocated():
    return q.unlocated(conn())


st.title("Facility finder")
st.caption("Click the map to choose a point, or use a PIN code or place name. "
           f"Positions are cross-checked against the postcode and city; a check "
           f"passes when the two agree to within {NEAR_KM:.0f} km.")

ss = st.session_state
ss.setdefault("point", None)      # (lat, lon)
ss.setdefault("origin", None)     # how the point was set

# ---------------------------------------------------------------- inputs ---
side, main = st.columns([1, 2.4])

with side:
    limit = st.slider("How many facilities", 1, 50, 10)

    st.markdown("**PIN code**")
    pin_in = st.text_input("PIN code", max_chars=10, label_visibility="collapsed",
                           placeholder="411001")
    if st.button("Use this PIN", use_container_width=True):
        rec = q.pin_lookup(conn(), pin_in)
        if rec is None:
            st.error("No point known for that PIN code.")
        elif not rec["trusted"]:
            st.error(f"PIN {rec['pin']} covers an area about "
                     f"{rec['spread_km']:.0f} km across, too spread out to use "
                     f"as a point (limit {PIN_TIGHT_KM:.0f} km).")
        else:
            ss.point = (rec["lat"], rec["lon"])
            ss.origin = (f"PIN {rec['pin']} — approximate, post offices in this "
                         f"PIN lie within {rec['spread_km']:.1f} km of this point")

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

    if ss.point:
        if st.button("Clear point", use_container_width=True):
            ss.point, ss.origin = None, None

# ---------------------------------------------------------------- search ---
rows, elapsed = ([], None)
if ss.point:
    rows, elapsed = _nearest(ss.point[0], ss.point[1], limit)

# ------------------------------------------------------------------- map ---
with main:
    centre = ss.point or INDIA_CENTRE
    m = folium.Map(location=list(centre), zoom_start=11 if ss.point else 4)
    if ss.point:
        folium.Marker(list(ss.point), tooltip="Your point",
                      icon=folium.Icon(color="black", icon="screenshot")).add_to(m)
        folium.Circle(list(ss.point), radius=NEAR_KM * 1000, color="#888",
                      weight=1, fill=False).add_to(m)
    for i, r in enumerate(rows, 1):
        folium.Marker(
            [r["final_lat"], r["final_lon"]],
            tooltip=(f"{i}. {r['name']} — "
                     f"{q.distance_text(r['distance_km'], r['location_source'])}"),
            popup=folium.Popup(
                f"<b>{r['name']}</b><br>{r['city'] or ''} {r['state'] or ''}"
                f"<br>{q.distance_text(r['distance_km'], r['location_source'])}"
                f" to the {q.point_label(r['location_source'])}"
                f"<br><i>{r['location_confidence']}</i> — {r['location_note']}",
                max_width=320),
            icon=folium.Icon(color=COLOUR.get(r["location_confidence"], "gray")),
        ).add_to(m)

    out = st_folium(m, height=520, use_container_width=True, key="map")
    click = (out or {}).get("last_clicked")
    if click and (ss.origin != "map" or ss.point != (click["lat"], click["lng"])):
        if ss.point != (click["lat"], click["lng"]):
            ss.point = (click["lat"], click["lng"])
            ss.origin = "map"
            st.rerun()

# --------------------------------------------------------------- results ---
if not ss.point:
    st.info("No point chosen yet. Click the map, or enter a PIN code or place name.")
else:
    lat, lon = ss.point
    note = "exact point you clicked" if ss.origin == "map" else ss.origin
    st.success(f"**{lat:.5f}, {lon:.5f}** — {note}")
    st.caption(f"{len(rows)} facilities, query took {elapsed:.2f} s")

    df = pd.DataFrame(rows)
    if not df.empty:
        show = pd.DataFrame({
            "#": range(1, len(df) + 1),
            "Distance": [q.distance_text(d, s_)
                         for d, s_ in zip(df["distance_km"], df["location_source"])],
            "Measured to": df["location_source"].map(q.point_label),
            "Facility": df["name"],
            "City": df["city"].fillna(""),
            "State": df["state"].fillna(""),
            "Position": df["location_confidence"].map(BADGE),
            "Why": [n if c in ("approximate", "suspect") else ""
                    for c, n in zip(df["location_confidence"], df["location_note"])],
        })
        st.dataframe(show, hide_index=True, use_container_width=True)

        weak = df[df["location_confidence"].isin(["approximate", "suspect"])]
        if len(weak):
            st.warning(f"{len(weak)} of these {len(df)} positions are approximate "
                       f"or suspect. The 'Why' column says what is wrong with each.")

# ------------------------------------------------------------- unlocated ---
un = _unlocated()
with st.expander(f"Facilities that cannot be placed on the map ({len(un)})"):
    st.caption("These have no usable coordinates, no usable postcode and no "
               "usable city, so they never appear in a nearest-facility result.")
    st.dataframe(pd.DataFrame(un), hide_index=True, use_container_width=True)

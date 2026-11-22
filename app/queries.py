"""Every read the app makes. One backend: Databricks SQL."""
from config import (
    T_FAC_LOC, T_PIN_POINT, T_CITY_POINT, F_HAVERSINE,
    NEAR_KM, PIN_TIGHT_KM, MIN_CITY_FACILITIES,
)

NEAREST_SQL = f"""
SELECT facility_id, name, city, state,
       final_lat, final_lon,
       {F_HAVERSINE}(?, ?, final_lat, final_lon) AS distance_km,
       location_source, location_confidence, location_note
FROM {T_FAC_LOC}
WHERE final_lat IS NOT NULL
-- at equal distance an exact coordinate outranks a centroid
ORDER BY distance_km, CASE WHEN location_source = 'coordinates' THEN 0 ELSE 1 END, name
LIMIT ?
"""

UNLOCATED_SQL = f"""
SELECT facility_id, name, city, state, postcode, location_note
FROM {T_FAC_LOC}
WHERE location_confidence = 'none'
ORDER BY name
"""

PIN_SQL = f"""
SELECT pin, lat, lon, n_offices, spread_km, trusted
FROM {T_PIN_POINT} WHERE pin = ?
"""

CITY_SQL = f"""
SELECT city_key, lat, lon, n_facilities
FROM {T_CITY_POINT} WHERE city_key = lower(trim(?))
"""


POINT_LABEL = {
    "coordinates": "exact location",
    "city_point": "city centre",
    "pin_point": "postcode area",
    "none": "not placed",
}


def point_label(location_source: str) -> str:
    """What the shown point actually is, in the user's words."""
    return POINT_LABEL.get(location_source, location_source)


def distance_text(distance_km: float, location_source: str) -> str:
    """A centroid is not a real address, so its distance is never shown to the
    nearest 10 m. Only coordinates get decimals."""
    if location_source in ("city_point", "pin_point"):
        n = round(distance_km)
        return "under 1 km" if n < 1 else f"about {n:.0f} km"
    return f"{distance_km:.2f} km"


def _rows(cn, sql, params=None):
    with cn.cursor() as c:
        c.execute(sql, params or [])
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in c.fetchall()]


def nearest(cn, user_lat: float, user_lon: float, limit: int = 10) -> list[dict]:
    """Facilities closest to a point, nearest first. facility_id is the join key
    a capability filter can later be added on."""
    return _rows(cn, NEAREST_SQL, [float(user_lat), float(user_lon), int(limit)])


def unlocated(cn) -> list[dict]:
    """Facilities that could not be placed on the map at all."""
    return _rows(cn, UNLOCATED_SQL)


def pin_lookup(cn, pin: str) -> dict | None:
    """Point for a 6-digit PIN, with its spread_km. None if unknown."""
    pin = "".join(ch for ch in str(pin) if ch.isdigit())[:6]
    if len(pin) != 6:
        return None
    r = _rows(cn, PIN_SQL, [pin])
    return r[0] if r else None


def city_lookup(cn, name: str) -> dict | None:
    """Point for a city name, with n_facilities behind it. None if unknown."""
    if not name or not name.strip():
        return None
    r = _rows(cn, CITY_SQL, [name])
    return r[0] if r else None

"""district_context(lat, lon, pin=None, service=...) -> dict, via scripts/district_context.sql.

District = the PIN's primary district when a PIN is given and known ('from_pin'), otherwise the primary
district of the nearest trusted PIN centre to (lat, lon) ('nearest_pin_centre', approximate).
Returns: district/state, NFHS match (exact/alias/None, alias_note for parent-mapped new districts),
mapped indicators (value, unit, rank_of_706, quartile, direction, reason) or no_indicator_reason,
raw "in our data" counts for the district (facilities, Confirmed/Likely/Possible for the service), and
the nearest Confirmed facility for the service from the search point: nearest_confirmed_exact
(exact coordinates, high/good confidence) and nearest_confirmed_any (any location source).
Distances are straight-line km. NFHS is context, never evidence about a facility.

Usage:  district_context(None, None, pin="835207", service="dialysis")
        district_context(10.787, 79.138, service="dialysis")
Pass `conn` (a databricks.sql connection) to reuse one; otherwise a CLI-profile token is used.
"""
import json
import os
import subprocess

SQL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "district_context.sql")


def _connect():
    from databricks import sql
    tok = json.loads(subprocess.check_output(["databricks", "auth", "token", "-p", "datathon"]))["access_token"]
    return sql.connect(server_hostname="dbc-70851148-db1d.cloud.databricks.com",
                       http_path="/sql/1.0/warehouses/8ea2282aca435351", access_token=tok)


def _plain(v):
    if hasattr(v, "asDict"):
        return {k: _plain(x) for k, x in v.asDict().items()}
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)) or type(v).__name__ == "ndarray":
        return [_plain(x) for x in v]
    if type(v).__name__ == "Decimal":
        return float(v)
    return v


def district_context(lat, lon, pin=None, service="dialysis", conn=None):
    with open(SQL_PATH) as f:
        query = f.read()
    own = conn is None
    conn = conn or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(query, {"lat": None if lat is None else float(lat),
                                "lon": None if lon is None else float(lon),
                                "pin": None if pin is None else str(pin).strip(),
                                "service": service})
            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
    finally:
        if own:
            conn.close()
    out = {c: _plain(v) for c, v in zip(cols, row)}
    for k in ("nearest_confirmed_exact", "nearest_confirmed_any"):
        if isinstance(out.get(k), str):
            out[k] = json.loads(out[k])
    if isinstance(out.get("indicators"), str):
        out["indicators"] = json.loads(out["indicators"])
    return out


if __name__ == "__main__":
    import sys
    import pprint
    pin = sys.argv[1] if len(sys.argv) > 1 else "835207"
    svc = sys.argv[2] if len(sys.argv) > 2 else "dialysis"
    pprint.pprint(district_context(None, None, pin=pin, service=svc), width=120)

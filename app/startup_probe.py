"""Smoke test run at app start; output lands in `databricks apps logs`."""
import sys, time
from conn import connect
import queries as q

TEST_POINTS = [("Pune", 18.520, 73.856), ("Udaipur", 24.585, 73.712)]

try:
    t0 = time.time()
    cn = connect()
    print(f"PROBE connect_s={time.time()-t0:.2f}", flush=True)
    for label, la, lo in TEST_POINTS:
        for trial in range(3):
            t1 = time.time()
            rows = q.nearest(cn, la, lo, 5)
            el = time.time() - t1
            print(f"PROBE nearest {label} trial={trial} secs={el:.3f} n={len(rows)}", flush=True)
        for i, r in enumerate(rows, 1):
            print(f"PROBE   {label} {i} {r['distance_km']:.2f}km "
                  f"{r['name']} | {r['city']} | {r['location_confidence']} | {r['location_source']}",
                  flush=True)
    t2 = time.time()
    print(f"PROBE unlocated n={len(q.unlocated(cn))} secs={time.time()-t2:.2f}", flush=True)
except Exception as e:
    print(f"PROBE FAILED {type(e).__name__}: {e}", flush=True)
    sys.exit(0)

"""Smoke test run at app start; output lands in `databricks apps logs`."""
import sys, time
from conn import connect
import queries as q
from config import COMMON_SEARCHES

try:
    t0 = time.time()
    cn = connect()
    print(f"PROBE connect_s={time.time()-t0:.2f}", flush=True)
    src = q.service_sources(cn)
    entries = q.dropdown(src)
    n_sample = sum(1 for _, s in src.values() if s)
    print(f"PROBE dropdown entries={len(entries)} services={len(src)} sample_services={n_sample} "
          f"first={entries[0][0] if entries else '-'}", flush=True)
    cov = q.tag_coverage(cn)
    print(f"PROBE coverage pct={cov['pct']:.1f} tagged={cov['tagged']} attempted={cov['attempted']} "
          f"complete={cov['complete']} build_ts={cov['build_ts']}", flush=True)
    print("PROBE confirmed " + " ".join(f"{r['service']}={r['confirmed']}"
                                        for r in q.confirmed_counts(cn)), flush=True)
    stats = q.build_stats(cn)
    print("PROBE build_stats " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())), flush=True)
    for pin_code in ("500001", "835207"):
        pin = q.pin_lookup(cn, pin_code)
        print(f"PROBE pin {pin_code} -> {pin}", flush=True)
        if not pin:
            continue
        tbl, _ = src["dialysis"]
        rows = q.service_search(cn, tbl, "dialysis", pin["lat"], pin["lon"], 20)
        per = {}
        for r in rows:
            per.setdefault(r["tier"], []).append(r)
        print(f"PROBE pin{pin_code} dialysis n={len(rows)} " +
              " ".join(f"{t}={len(v)}" for t, v in per.items()), flush=True)
        for t, v in per.items():
            r = v[0]
            print(f"PROBE   nearest {t}: {r['name']} | {q.location_text(r)} | "
                  f"{r['location_source']} | phone={r['official_phone']} | web={r['official_domain']}",
                  flush=True)
    import matcher
    t4 = time.time()
    m = matcher.match("kidney machine")
    print(f"PROBE matcher 'kidney machine' -> {m} secs={time.time()-t4:.2f}", flush=True)
    for svc in COMMON_SEARCHES:
        tbl, is_sample = src.get(svc, (None, None))
        if not tbl:
            print(f"PROBE service {svc} missing", flush=True)
            continue
        t3 = time.time()
        rows = q.service_search(cn, tbl, svc, 18.520, 73.856, 3)[:3]
        print(f"PROBE service {svc} source={tbl} is_sample={is_sample} "
              f"secs={time.time()-t3:.3f} n={len(rows)} "
              f"top={rows[0]['tier'] + ' ' + rows[0]['name'] if rows else '-'}", flush=True)
except Exception as e:
    print(f"PROBE FAILED {type(e).__name__}: {e}", flush=True)
    sys.exit(0)

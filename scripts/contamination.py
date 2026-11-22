"""Size record-level contamination (merged/foreign sentences) in the facilities table.

Stages (run in order):  python scripts/contamination.py base|sample|llm|signals|report
Writes only to workspace.vf.contam_*.
"""

import json
import re
import subprocess
import sys

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
SRC = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities"
PIN = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.india_post_pincode_directory"
VF = "workspace.vf"
SEED = "contam2026"
N_SAMPLE = 300
MIN_SENT = 20
AGG_MIN_RECORDS = 50  # aggregator = domain in > 50 distinct records

# ---- signal c: state inference ----------------------------------------------------
# canonical state key = lowercase letters only, the word "and" removed
STATES = {
    "andhrapradesh": "andhrapradesh", "arunachalpradesh": "arunachalpradesh", "assam": "assam",
    "bihar": "bihar", "chhattisgarh": "chhattisgarh", "chattisgarh": "chhattisgarh", "goa": "goa",
    "gujarat": "gujarat", "haryana": "haryana", "himachalpradesh": "himachalpradesh",
    "himachal": "himachalpradesh", "jharkhand": "jharkhand", "karnataka": "karnataka",
    "kerala": "kerala", "madhyapradesh": "madhyapradesh", "maharashtra": "maharashtra",
    "manipur": "manipur", "meghalaya": "meghalaya", "mizoram": "mizoram", "nagaland": "nagaland",
    "odisha": "odisha", "orissa": "odisha", "punjab": "punjab", "rajasthan": "rajasthan",
    "sikkim": "sikkim", "tamilnadu": "tamilnadu", "telangana": "telangana", "tripura": "tripura",
    "uttarpradesh": "uttarpradesh", "uttarakhand": "uttarakhand", "uttaranchal": "uttarakhand",
    "westbengal": "westbengal", "delhi": "delhi", "chandigarh": "chandigarh",
    "puducherry": "puducherry", "pondicherry": "puducherry", "jammukashmir": "jammukashmir",
    "ladakh": "ladakh", "lakshadweep": "lakshadweep", "andamannicobarislands": "andamannicobarislands",
    "andaman": "andamannicobarislands",
    "thedadranagarhavelidamandiu": "dnhdd",
}
# 2-letter codes: only accepted as a whole host label
STATE_CODES = {
    "ap": "andhrapradesh", "ar": "arunachalpradesh", "br": "bihar", "cg": "chhattisgarh",
    "gj": "gujarat", "hr": "haryana", "hp": "himachalpradesh", "jh": "jharkhand",
    "ka": "karnataka", "kar": "karnataka", "kl": "kerala", "mp": "madhyapradesh",
    "mh": "maharashtra", "mn": "manipur", "ml": "meghalaya", "mz": "mizoram", "nl": "nagaland",
    "od": "odisha", "pb": "punjab", "rj": "rajasthan", "sk": "sikkim", "tn": "tamilnadu",
    "ts": "telangana", "tg": "telangana", "tr": "tripura", "up": "uttarpradesh",
    "uk": "uttarakhand", "wb": "westbengal", "dl": "delhi", "py": "puducherry",
    "jk": "jammukashmir", "ga": "goa", "dnh": "dnhdd", "hry": "haryana",
}
CITY_STATE = {  # well-known city labels in gov hosts
    "mumbai": "maharashtra", "mcgm": "maharashtra", "pune": "maharashtra", "nagpur": "maharashtra",
    "thane": "maharashtra", "chennai": "tamilnadu", "kolkata": "westbengal",
    "hyderabad": "telangana", "ghmc": "telangana", "bangalore": "karnataka",
    "bengaluru": "karnataka", "bbmp": "karnataka", "ahmedabad": "gujarat", "surat": "gujarat",
    "lucknow": "uttarpradesh", "jaipur": "rajasthan", "bhopal": "madhyapradesh",
    "indore": "madhyapradesh", "patna": "bihar", "ranchi": "jharkhand", "guwahati": "assam",
    "bhubaneswar": "odisha", "raipur": "chhattisgarh", "dehradun": "uttarakhand",
    "shimla": "himachalpradesh", "srinagar": "jammukashmir", "jammu": "jammukashmir",
    "thiruvananthapuram": "kerala", "trivandrum": "kerala", "ernakulam": "kerala",
    "kochi": "kerala", "visakhapatnam": "andhrapradesh", "vijayawada": "andhrapradesh",
    "ludhiana": "punjab", "amritsar": "punjab", "gurugram": "haryana", "gurgaon": "haryana",
    "faridabad": "haryana", "noida": "uttarpradesh", "mcd": "delhi", "ndmc": "delhi",
}
NATIONAL_GOV = {"mohfw", "nhm", "india", "nhp", "pmjay", "abdm", "cghs", "esic", "nha",
                "icmr", "data", "mygov", "dghs", "main", "nhsrcindia", "aiims"}


def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def conn():
    return sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token())


def run(c, q, fetch=False):
    with c.cursor() as cur:
        cur.execute(q)
        if fetch:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    return None


def lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def arr(xs) -> str:
    return "array(" + ",".join(lit(x) for x in xs) + ")"


# ----------------------------------------------------------------------------------
def stage_base(c):
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_base AS
WITH d AS (
  SELECT * FROM (SELECT f.*, row_number() OVER (PARTITION BY unique_id ORDER BY name) rn
                 FROM {SRC} f) WHERE rn = 1
), p AS (
  SELECT unique_id, name, address_city, address_stateOrRegion, description, latitude, longitude,
    organization_type, officialWebsite, coalesce(organization_type = 'facility', false) AS valid,
    coalesce(from_json(procedure,'array<string>'), cast(array() AS array<string>)) pr,
    coalesce(from_json(capability,'array<string>'), cast(array() AS array<string>)) cap,
    coalesce(from_json(equipment,'array<string>'), cast(array() AS array<string>)) eq,
    coalesce(from_json(source_urls,'array<string>'), cast(array() AS array<string>)) su
  FROM d)
SELECT *, size(pr) n_pr, size(cap) n_cap, size(eq) n_eq,
  filter(transform(concat(pr, cap, eq), x -> trim(x)), x -> x IS NOT NULL AND x <> '') sentences
FROM p""")
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_fac_domain AS
SELECT DISTINCT unique_id,
  regexp_extract(lower(trim(u)), '^(?:[a-z]+://)?(?:www\\\\.)?([^/:?#]+)', 1) AS domain
FROM {VF}.contam_base LATERAL VIEW explode(su) t AS u
WHERE u IS NOT NULL AND trim(u) <> ''""")
    run(c, f"DELETE FROM {VF}.contam_fac_domain WHERE domain IS NULL OR domain = ''")
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_domain_stats AS
SELECT domain, count(DISTINCT unique_id) n_records,
       count(DISTINCT unique_id) > {AGG_MIN_RECORDS} AS is_agg
FROM {VF}.contam_fac_domain GROUP BY domain""")
    print(run(c, f"""SELECT (SELECT count(*) FROM {VF}.contam_base) n_base,
      (SELECT count(*) FROM {VF}.contam_domain_stats) n_domains,
      (SELECT count(*) FROM {VF}.contam_domain_stats WHERE is_agg) n_agg,
      (SELECT count(*) FROM {VF}.contam_base WHERE size(sentences) >= {MIN_SENT}) n_eligible""",
              True))


PROMPT_HEAD = """You audit ONE record from a scraped database of Indian healthcare facilities.
Records were built by merging web snippets, and some records absorbed sentences that actually describe a DIFFERENT organisation (another hospital, clinic or government facility, often in another city).

RECORD
Name: """
PROMPT_TAIL = """

TASK
Judge every numbered sentence against the record's OWN name and city.
- A sentence is foreign if it names, or clearly describes, a different organisation or a different location.
- A branch, unit or parent of the same hospital group counts as the same organisation (consistent).
- A generic sentence that names no organisation and could fit this facility counts as consistent.
verdict: "consistent" if (almost) no sentences are foreign; "partly_foreign" if some but not most are foreign; "mostly_foreign" if more than half are foreign.

Return ONLY a JSON object, no other text:
{"verdict": "consistent" | "partly_foreign" | "mostly_foreign",
 "foreign_share": <number from 0 to 1: rough share of sentences that describe a different organisation>,
 "other_names": [<up to 5 OTHER facility names found in the sentences; [] if none>],
 "reason": "<at most 15 words>"}"""


def stage_sample(c):
    prompt_sql = f"""concat({lit(PROMPT_HEAD)}, coalesce(name,'(none)'),
  '\\nCity: ', coalesce(address_city,'(none)'),
  '\\nState: ', coalesce(address_stateOrRegion,'(none)'),
  '\\nDescription: ', coalesce(substr(description,1,1200),'(none)'),
  '\\n\\nNUMBERED SENTENCES (from the record\\'s procedure, capability and equipment fields)\\n',
  array_join(transform(sentences, (x, i) -> concat(cast(i + 1 AS string), '. ', x)), '\\n'),
  {lit(PROMPT_TAIL)})"""
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_pilot AS
SELECT unique_id, name, address_city, address_stateOrRegion, latitude, longitude,
       size(sentences) n_sent, n_pr, n_cap, n_eq, sentences, {prompt_sql} AS prompt
FROM {VF}.contam_base
WHERE size(sentences) >= {MIN_SENT} AND valid
ORDER BY md5(concat('{SEED}', unique_id))
LIMIT {N_SAMPLE}""")
    print(run(c, f"SELECT count(*) n, avg(length(prompt)) avg_len, max(length(prompt)) max_len "
                 f"FROM {VF}.contam_pilot", True))


# ----------------------------------------------------------------------------------
ALLOWED = {"consistent", "partly_foreign", "mostly_foreign"}


def parse(raw):
    if raw is None:
        return None, "null response"
    try:
        o = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception as e:  # noqa: BLE001
        return None, f"unparseable: {e}"
    v = o.get("verdict")
    if v not in ALLOWED:
        return None, f"bad verdict {v!r}"
    fs = o.get("foreign_share")
    if isinstance(fs, str):
        try:
            fs = float(fs)
        except ValueError:
            return None, "foreign_share not number"
    if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not 0 <= fs <= 1:
        return None, f"bad foreign_share {fs!r}"
    on = o.get("other_names")
    if not isinstance(on, list) or len(on) > 5 or not all(isinstance(x, str) for x in on):
        return None, f"bad other_names {on!r}"
    r = o.get("reason")
    if not isinstance(r, str):
        return None, "bad reason"
    return {"verdict": v, "foreign_share": float(fs), "other_names": on, "reason": r,
            "reason_words": len(r.split())}, None


def stage_llm(c):
    results, errs, attempts_used = {}, {}, {}
    ids = [r["unique_id"] for r in run(c, f"SELECT unique_id FROM {VF}.contam_pilot", True)]
    pending = ids
    for attempt in (1, 2, 3):
        if not pending:
            break
        temp = 0.0 if attempt == 1 else 0.3
        extra = "" if attempt == 1 else (
            "\\n\\nIMPORTANT: reply with ONE valid JSON object exactly matching the schema; "
            "other_names must be a list of at most 5 strings.")
        inlist = ",".join(lit(i) for i in pending)
        tbl = f"{VF}.contam_llm_a{attempt}"
        print(f"attempt {attempt}: {len(pending)} rows", flush=True)
        run(c, f"""
CREATE OR REPLACE TABLE {tbl} AS
SELECT unique_id, r.result AS raw, r.errorMessage AS err FROM (
  SELECT unique_id, ai_query('{MODEL}', concat(prompt, '{extra}'),
      modelParameters => named_struct('max_tokens', 400, 'temperature', {temp}),
      failOnError => false) AS r
  FROM {VF}.contam_pilot WHERE unique_id IN ({inlist}))""")
        rows = run(c, f"SELECT * FROM {tbl}", True)
        nxt = []
        for r in rows:
            uid = r["unique_id"]
            attempts_used[uid] = attempt
            res, e = parse(r["raw"]) if not r["err"] else (None, f"endpoint error: {r['err'][:120]}")
            if res:
                results[uid] = res
                errs.pop(uid, None)
            else:
                errs[uid] = e
                nxt.append(uid)
        pending = nxt
        print(f"  ok so far {len(results)}, malformed this attempt {len(nxt)}", flush=True)
    # write parsed results
    vals = []
    for uid in ids:
        r = results.get(uid)
        if r:
            vals.append(f"({lit(uid)},{attempts_used[uid]},{lit(r['verdict'])},{r['foreign_share']},"
                        f"{lit(json.dumps(r['other_names'], ensure_ascii=False))},{lit(r['reason'])},"
                        f"{r['reason_words']},NULL)")
        else:
            vals.append(f"({lit(uid)},{attempts_used.get(uid, 0)},NULL,NULL,NULL,NULL,NULL,"
                        f"{lit(errs.get(uid, 'missing'))})")
    run(c, f"""CREATE OR REPLACE TABLE {VF}.contam_llm (unique_id STRING, attempts INT,
      verdict STRING, foreign_share DOUBLE, other_names STRING, reason STRING,
      reason_words INT, error STRING)""")
    run(c, f"INSERT INTO {VF}.contam_llm VALUES " + ",".join(vals))
    print("errors:", errs)


# ----------------------------------------------------------------------------------
# Signal a / e rule as revised by the user (column-inventory rule) ------------------
A_MIN_LEN = 4
A_GENERIC = """hospital hospitals clinic clinics eye dental dentist care centre center multispeciality
multispecialty multi speciality specialty super health healthcare medical nursing home institute
research diagnostic diagnostics the and of for dr doctor doctors children women maternity memorial
general city life new sri shri shree lab labs path pathology polyclinic trust foundation private
limited ltd pvt india indian unit road nagar""".split()
HOST_RE = '^(?:[a-z]+://)?(?:www\\\\.)?([^/:?#]+)'
SUFFIX_RE = '(\\\\.(org\\\\.in|co\\\\.in|ac\\\\.in|nic\\\\.in|com|in|org|net|co|gov|edu|info))+$'


def host_norm(expr):
    return f"regexp_replace(regexp_extract(lower(trim({expr})), '{HOST_RE}', 1), '{SUFFIX_RE}', '')"


def signals_ae_sql():
    """Signals a and e for every valid facility (organization_type = 'facility')."""
    return f"""
WITH city AS (SELECT collect_set(lower(trim(address_city))) cities FROM {VF}.contam_base
              WHERE address_city IS NOT NULL),
t AS (
  SELECT b.unique_id, b.name, b.officialWebsite, b.su,
    array_distinct(filter(split(lower(coalesce(b.name,'')), '[^a-z0-9]+'),
      x -> length(x) >= {A_MIN_LEN} AND NOT array_contains({arr(A_GENERIC)}, x)
           AND NOT array_contains(city.cities, x))) toks
  FROM {VF}.contam_base b CROSS JOIN city WHERE b.valid
), dom AS (
  SELECT fd.unique_id, fd.domain,
    regexp_replace(fd.domain, '{SUFFIX_RE}', '') AS h
  FROM {VF}.contam_fac_domain fd JOIN {VF}.contam_domain_stats ds USING (domain)
  WHERE NOT ds.is_agg
), m AS (
  SELECT t.unique_id, d.domain, exists(t.toks, x -> instr(d.h, x) > 0) hit
  FROM t JOIN dom d USING (unique_id)
), a AS (
  SELECT t.unique_id, max(coalesce(m.hit, false)) hit,
    array_sort(collect_set(CASE WHEN m.hit THEN m.domain END)) own_domains,
    count(DISTINCT m.domain) n_nonagg_domains
  FROM t LEFT JOIN m USING (unique_id) GROUP BY t.unique_id
), e AS (
  SELECT t.unique_id,
    CASE WHEN t.officialWebsite IS NULL OR trim(t.officialWebsite) IN ('', 'null')
              OR instr(t.officialWebsite, '.') = 0 THEN NULL
         ELSE {host_norm('t.officialWebsite')} END AS off_host,
    filter(transform(t.su, u -> {host_norm('u')}), x -> x IS NOT NULL AND x <> '') url_hosts
  FROM t
)
SELECT t.unique_id, t.name, t.toks AS name_tokens, t.officialWebsite,
  CASE WHEN size(t.toks) = 0 THEN 'no_tokens' WHEN a.hit THEN 'true' ELSE 'false' END own_domain,
  a.own_domains, a.n_nonagg_domains,
  e.off_host, e.off_host IS NULL AS official_missing,
  size(e.url_hosts) AS n_urls,
  CASE WHEN e.off_host IS NULL OR size(e.url_hosts) = 0 THEN NULL
       ELSE size(filter(e.url_hosts, x -> x = e.off_host)) / size(e.url_hosts) END official_site_share,
  CASE WHEN e.off_host IS NULL THEN NULL
       ELSE NOT exists(t.toks, x -> instr(e.off_host, x) > 0) END official_not_name
FROM t JOIN a USING (unique_id) JOIN e USING (unique_id)"""


def state_key_sql(expr):
    return f"regexp_replace(regexp_replace(lower({expr}), '\\\\band\\\\b', ''), '[^a-z]', '')"


def stage_signals(c):
    # facility state: majority statename among the 5 nearest geocoded post offices within 0.3 deg;
    # fallback: address_stateOrRegion if it normalises to a known state name; else unknown.
    states_map = ",".join(f"{lit(k)},{lit(v)}" for k, v in STATES.items())
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_fac_state AS
WITH po AS (
  SELECT DISTINCT round(cast(latitude AS double), 3) la, round(cast(longitude AS double), 3) lo,
         element_at(map({states_map}), {state_key_sql('statename')}) st
  FROM {PIN}
  WHERE try_cast(latitude AS double) BETWEEN 6 AND 37.5
    AND try_cast(longitude AS double) BETWEEN 68 AND 97.5 AND statename <> 'NA'
), near AS (
  SELECT p.unique_id, po.st,
    row_number() OVER (PARTITION BY p.unique_id ORDER BY
      pow(po.la - p.latitude, 2) + pow((po.lo - p.longitude) * cos(radians(p.latitude)), 2)) rk
  FROM {VF}.contam_pilot p JOIN po
    ON po.la BETWEEN p.latitude - 0.3 AND p.latitude + 0.3
   AND po.lo BETWEEN p.longitude - 0.3 AND p.longitude + 0.3
  WHERE po.st IS NOT NULL
), vote AS (
  SELECT unique_id, st, count(*) n,
    row_number() OVER (PARTITION BY unique_id ORDER BY count(*) DESC, min(rk)) r
  FROM near WHERE rk <= 5 GROUP BY unique_id, st
)
SELECT p.unique_id,
  coalesce(v.st, element_at(map({states_map}), {state_key_sql('p.address_stateOrRegion')})) fac_state,
  CASE WHEN v.st IS NOT NULL THEN 'coords_nearest5_postoffice'
       WHEN element_at(map({states_map}), {state_key_sql('p.address_stateOrRegion')}) IS NOT NULL
       THEN 'address_field' ELSE 'unknown' END state_source
FROM {VF}.contam_pilot p LEFT JOIN (SELECT * FROM vote WHERE r = 1) v USING (unique_id)""")

    # district names (from post directory) that map to exactly one state, >=5 chars
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_district_state AS
SELECT d, first(st) st FROM (
  SELECT DISTINCT regexp_replace(lower(district), '[^a-z]', '') d,
         element_at(map({states_map}), {state_key_sql('statename')}) st
  FROM {PIN} WHERE statename <> 'NA')
WHERE st IS NOT NULL AND length(d) >= 5
GROUP BY d HAVING count(DISTINCT st) = 1""")

    codes = ",".join(f"{lit(k)},{lit(v)}" for k, v in STATE_CODES.items())
    cities = ",".join(f"{lit(k)},{lit(v)}" for k, v in CITY_STATE.items())
    full = ",".join(f"{lit(k)},{lit(v)}" for k, v in STATES.items() if len(k) >= 5)
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_gov_domain AS
WITH g AS (
  SELECT DISTINCT fd.unique_id, fd.domain,
    filter(split(regexp_replace(fd.domain, '\\\\.gov\\\\.in$', ''), '[.\\\\-]'), l -> l <> '') labels
  FROM {VF}.contam_fac_domain fd
  WHERE fd.unique_id IN (SELECT unique_id FROM {VF}.contam_pilot)
    AND (fd.domain LIKE '%.gov.in' OR fd.domain = 'gov.in')
), s AS (
  SELECT g.*,
    array_distinct(filter(concat(
      transform(labels, l -> element_at(map({codes}), l)),
      flatten(transform(labels, l -> transform(filter(map_keys(map({cities})), k -> length(k) >= 5 AND instr(l, k) > 0),
                                               k -> element_at(map({cities}), k)))),
      flatten(transform(labels, l -> transform(filter(map_keys(map({full})), k -> instr(l, k) > 0),
                                               k -> element_at(map({full}), k))))
    ), x -> x IS NOT NULL)) direct_states
  FROM g
)
SELECT s.unique_id, s.domain, s.labels,
  CASE WHEN size(s.direct_states) = 1 THEN s.direct_states[0]
       WHEN size(s.direct_states) > 1 THEN NULL
       WHEN size(ds.sts) = 1 THEN ds.sts[0] END AS dom_state,
  CASE WHEN size(s.direct_states) = 1 THEN 'state_or_city_token'
       WHEN size(s.direct_states) > 1 THEN 'ambiguous'
       WHEN size(ds.sts) = 1 THEN 'district_label'
       WHEN exists(s.labels, l -> array_contains({arr(sorted(NATIONAL_GOV))}, l)) THEN 'national'
       ELSE 'unknown' END AS dom_state_source
FROM s LEFT JOIN (
  SELECT s2.unique_id, s2.domain, array_distinct(collect_list(dd.st)) sts
  FROM (SELECT unique_id, domain, explode(labels) AS l FROM s) s2
  JOIN {VF}.contam_district_state dd ON dd.d = s2.l
  GROUP BY s2.unique_id, s2.domain) ds ON ds.unique_id = s.unique_id AND ds.domain = s.domain""")

    run(c, f"CREATE OR REPLACE TABLE {VF}.contam_sig_ae_all AS " + signals_ae_sql())

    run(c, f"""
CREATE OR REPLACE TABLE {VF}.contam_signals AS
SELECT p.unique_id, p.name, p.address_city, p.address_stateOrRegion, p.n_sent,
  o.own_domain, o.own_domains, o.name_tokens, o.n_nonagg_domains,
  o.official_site_share, o.official_missing, o.official_not_name, o.off_host, o.n_urls,
  coalesce(gv.n_gov, 0) n_gov_in, fs.fac_state, fs.state_source,
  CASE WHEN coalesce(gv.n_gov, 0) = 0 THEN 'no_gov_in'
       WHEN fs.fac_state IS NULL THEN 'unknown'
       WHEN gv.n_other > 0 THEN 'true'
       WHEN gv.n_known > 0 THEN 'false'
       ELSE 'unknown' END AS gov_other_state,
  gv.other_state_domains,
  (p.n_pr >= 50 AND p.n_cap >= 50 AND p.n_eq >= 50) all_three_capped
FROM {VF}.contam_pilot p
JOIN {VF}.contam_sig_ae_all o USING (unique_id)
JOIN {VF}.contam_fac_state fs USING (unique_id)
LEFT JOIN (
  SELECT g.unique_id, count(*) n_gov,
    sum(CASE WHEN g.dom_state IS NOT NULL THEN 1 ELSE 0 END) n_known,
    sum(CASE WHEN g.dom_state IS NOT NULL AND g.dom_state <> f.fac_state THEN 1 ELSE 0 END) n_other,
    slice(collect_list(CASE WHEN g.dom_state <> f.fac_state THEN concat(g.domain, ':', g.dom_state) END), 1, 4)
      other_state_domains
  FROM {VF}.contam_gov_domain g JOIN {VF}.contam_fac_state f USING (unique_id)
  GROUP BY g.unique_id) gv USING (unique_id)""")
    print(run(c, f"SELECT own_domain, count(*) n FROM {VF}.contam_signals GROUP BY 1", True))


def stage_report(c):
    import pandas as pd
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    df = pd.DataFrame(run(c, f"""
SELECT s.*, l.verdict, l.foreign_share, l.other_names, l.reason, l.reason_words, l.attempts
FROM {VF}.contam_signals s JOIN {VF}.contam_llm l USING (unique_id)""", True))
    df.to_parquet("data/contam_pilot_results.parquet")
    order = ["consistent", "partly_foreign", "mostly_foreign"]
    print("attempts:", df.attempts.value_counts().to_dict(), " reason>15 words:",
          int((df.reason_words > 15).sum()))
    print("\n== verdict counts ==")
    print(df.verdict.value_counts().reindex(order).to_string())
    print("\n== foreign_share by verdict ==")
    print(df.groupby("verdict").foreign_share.describe().reindex(order).round(2).to_string())

    def xt(col, bins=None, labels=None):
        x = df[col]
        if bins is not None:
            x = pd.cut(x, bins=bins, labels=labels, right=True)
        t = pd.crosstab(x, df.verdict).reindex(columns=order).fillna(0).astype(int)
        pct = (t / t.sum() * 100).round(0).astype(int).astype(str) + "%"
        print(f"\n== {col} x verdict (count / column %) ==")
        print((t.astype(str) + " / " + pct).to_string())

    df["own_domain"] = df.own_domain.astype(str)
    xt("own_domain")
    xt("n_nonagg_domains", [-1, 0, 1, 2, 5, 10, 1000], ["0", "1", "2", "3-5", "6-10", "11+"])
    print(df.groupby("verdict").n_nonagg_domains.median().reindex(order).to_string())
    xt("n_gov_in", [-1, 0, 1, 3, 1000], ["0", "1", "2-3", "4+"])
    xt("gov_other_state")
    xt("all_three_capped")

    def ebucket(r):
        if r.official_missing:
            return "5 official missing"
        v = r.official_site_share
        if v is None or pd.isna(v):
            return "6 no urls"
        v = float(v)
        return "1 0" if v == 0 else "2 (0,.25]" if v <= .25 else "3 (.25,.5]" if v <= .5 else "4 >.5"
    df["official_site_share_bucket"] = df.apply(ebucket, axis=1)
    xt("official_site_share_bucket")
    df["official_not_name"] = df.official_not_name.map(lambda x: "n/a (missing)" if x is None else str(x))
    xt("official_not_name")
    xt("n_sent", [19, 49, 99, 149, 150], ["20-49", "50-99", "100-149", "150"])
    df["fac_state"].value_counts().head(5)

    show = ["name", "address_city", "verdict", "foreign_share", "reason", "other_names",
            "own_domain", "n_nonagg_domains", "official_site_share", "official_missing",
            "official_not_name", "n_gov_in", "gov_other_state", "all_three_capped",
            "unique_id"]
    mf = df[df.verdict == "mostly_foreign"][show]
    pf = df[df.verdict == "partly_foreign"].sample(n=min(15, (df.verdict == "partly_foreign").sum()),
                                                   random_state=2026)[show]
    mf.to_json("data/contam_show_mf.json", orient="records", indent=1)
    pf.to_json("data/contam_show_pf.json", orient="records", indent=1)
    print(f"\nmostly_foreign: {len(mf)}  partly_foreign shown: {len(pf)}")


if __name__ == "__main__":
    stage = sys.argv[1]
    with conn() as c:
        {"base": stage_base, "sample": stage_sample, "llm": stage_llm,
         "signals": stage_signals, "report": stage_report}[stage](c)

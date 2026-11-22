"""Pilot B: record audit with sentence-level output (prompt version pb_v1).

Usage:  python scripts/pilot_b_audit.py select|stage0|stage1|report
Reads only workspace.vf.facilities_clean, workspace.vf.facility_sentences (usable sentences) and the
earlier contam_llm table. Writes only workspace.vf.pb_* tables.
Every SQL statement's start/end time is logged to data/pb_timings.jsonl and to workspace.vf.pb_timings.
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
VF = "workspace.vf"
FC = f"{VF}.facilities_clean"
FS = f"{VF}.facility_sentences"
SEED = "pb2026"
PROMPT_VERSION = "pb_v1"
MAX_TOKENS = 800  # earlier audit used 400; raised because foreign_sentences adds output
TIMING_LOG = "data/pb_timings.jsonl"
ARAVIND = "b8a5401f-42f1-422a-8cd9-686a15b4cb76"

# ---- reviewer marks from the contamination pilot review (rows 1-25 = contam_show_mf.json order,
# rows 26-40 = contam_show_pf.json order). target = verdict the reviewer said it should be.
MARKS = {  # review row -> (mark, target_verdict or None, reviewer note)
    5: ("W", "consistent", "own-chain branches; should be consistent"),
    6: ("D", None, "eye content dominant; partly"),
    12: ("W", "partly_foreign", "eye ~25%; partly"),
    13: ("W", "consistent", "same hospital has ophthalmology"),
    18: ("W", "partly_foreign", "dental core is Jodhpur; ~25% foreign"),
    22: ("D", None, "generic services unattributable"),
    23: ("D", None, "much is JJ group itself"),
    26: ("W", "consistent", "branches; consistent"),
    28: ("W", "consistent", "Bijapur = Vijayapura"),
    29: ("W", "consistent", "Puthur is in Palakkad"),
    30: ("W", "consistent", "same trust; same taluk"),
    32: ("D", None, "parent campus/branches"),
    33: ("W", "mostly_foreign", "UNDER-called: mostly_foreign"),
    34: ("W", "consistent", "Brahmapur = Berhampur"),
    35: ("W", "consistent", "Kopaganj is in Mau district"),
    36: ("W", "consistent", "affiliations, not foreign content"),
    37: ("W", "consistent", "all Gurgaon sectors"),
    38: ("W", "consistent", "own branch"),
    40: ("D", None, "same group"),
}

PROMPT_HEAD = """You audit ONE record from a scraped database of Indian healthcare facilities.
Records were built by merging web snippets, and some records absorbed sentences that actually describe a DIFFERENT organisation (another hospital, clinic or government facility, often in another city).

RECORD
Name: """
PROMPT_TAIL = """

TASK
Judge every numbered sentence against the record's OWN name and city.
- A sentence is foreign if it names, or clearly describes, a different organisation or a different location.
- A branch, unit, parent or sister unit of the same group counts as the same organisation (consistent).
- Old and new names of one city are the same place (e.g. Bijapur and Vijayapura, Berhampur and Brahmapur), and a locality, taluk or district that contains the record's city is the same place.
- A different hospital with a similar or identical name in another city is foreign.
- A generic sentence that names no organisation and could fit this facility counts as consistent.
verdict: "consistent" if (almost) no sentences are foreign; "partly_foreign" if some but not most are foreign; "mostly_foreign" if more than half are foreign.

Return ONLY a JSON object, no other text:
{"verdict": "consistent" | "partly_foreign" | "mostly_foreign",
 "foreign_share": <number from 0 to 1: rough share of sentences that describe a different organisation>,
 "foreign_sentences": [<numbers of the sentences that describe a different organisation; integers, or ranges as strings like "12-19"; [] if none>],
 "other_names": [<up to 5 OTHER facility names found in the sentences; [] if none>],
 "reason": "<at most 15 words>"}"""
SENT_HEADER = "\\n\\nNUMBERED SENTENCES (from the record\\'s procedure, capability and equipment fields)\\n"


# ---------------------------------------------------------------------------------- infra
def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def conn():
    return sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token())


TIMINGS = []


def run(c, q, fetch=False, label=None):
    t0 = time.time()
    s0 = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with c.cursor() as cur:
            cur.execute(q)
            out = None
            if fetch:
                cols = [d[0] for d in cur.description]
                out = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        t1 = time.time()
        rec = {"label": label or q.strip().split("\n")[0][:80], "start": s0,
               "end": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "seconds": round(t1 - t0, 2)}
        TIMINGS.append(rec)
        with open(TIMING_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{rec['start']} -> {rec['end']}] {rec['seconds']:7.1f}s  {rec['label']}", flush=True)
    return out


def lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def flush_timings(c):
    if not TIMINGS:
        return
    vals = ",".join(f"({lit(t['label'])},{lit(t['start'])},{lit(t['end'])},{t['seconds']})"
                    for t in TIMINGS)
    TIMINGS.clear()
    with c.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {VF}.pb_timings (label STRING, start_utc STRING, "
                    f"end_utc STRING, seconds DOUBLE)")
        cur.execute(f"INSERT INTO {VF}.pb_timings VALUES {vals}")


def full_prompt_text():
    return (PROMPT_HEAD + "{name}\nCity: {city}\nState: {state}\nDescription: {description[:1200]}"
            "\n\nNUMBERED SENTENCES (from the record's procedure, capability and equipment fields)\n"
            "1. {sentence 1}\n2. {sentence 2}\n..." + PROMPT_TAIL)


# ---------------------------------------------------------------------------------- select
def stage_select(c):
    mf = json.load(open("data/contam_show_mf.json"))
    pf = json.load(open("data/contam_show_pf.json"))
    rows = []
    for i, r in enumerate(mf + pf, start=1):
        mark, target, note = MARKS.get(i, ("", None, ""))
        rows.append((r["unique_id"], "reviewed_mf" if i <= 25 else "reviewed_pf", i, mark, target, note))
    reviewed = [r[0] for r in rows]
    # 20 random earlier-consistent records (fixed seed), not reviewed, not Aravind, non-shifted
    rnd = run(c, f"""
SELECT l.unique_id FROM {VF}.contam_llm l JOIN {FC} f USING (unique_id)
WHERE l.verdict = 'consistent' AND NOT f.is_shifted
  AND l.unique_id NOT IN ({",".join(lit(x) for x in reviewed + [ARAVIND])})
ORDER BY md5(concat('{SEED}', l.unique_id)) LIMIT 20""", True, "select random consistent")
    for r in rnd:
        rows.append((r["unique_id"], "random_consistent", None, "", None, ""))
    rows.append((ARAVIND, "aravind", None, "", None, "known positive"))
    assert len(rows) == 61 and len({r[0] for r in rows}) == 61

    # stage 0: Aravind + 2 mostly_foreign + 1 partly_foreign + 1 consistent, first by seeded order
    def seeded(ids):
        import hashlib
        return sorted(ids, key=lambda x: hashlib.md5((SEED + x).encode()).hexdigest())
    s0 = {ARAVIND}
    s0 |= set(seeded([r[0] for r in rows if r[1] == "reviewed_mf"])[:2])
    s0 |= set(seeded([r[0] for r in rows if r[1] == "reviewed_pf"])[:1])
    s0 |= set(seeded([r[0] for r in rows if r[1] == "random_consistent"])[:1])

    vals = ",".join(
        f"({lit(u)},{lit(g)},{'NULL' if i is None else i},{lit(m)},"
        f"{'NULL' if t is None else lit(t)},{lit(n)},{0 if u in s0 else 1})"
        for u, g, i, m, t, n in rows)
    run(c, f"""CREATE OR REPLACE TABLE {VF}.pb_records_in (unique_id STRING, grp STRING,
      review_row INT, mark STRING, target_verdict STRING, review_note STRING, stage INT)""",
        label="create pb_records_in")
    run(c, f"INSERT INTO {VF}.pb_records_in VALUES {vals}", label="insert pb_records_in")

    # numbered usable sentences
    run(c, f"""
CREATE OR REPLACE TABLE {VF}.pb_sentences AS
SELECT s.unique_id, s.source_column, s.position, s.sentence,
  row_number() OVER (PARTITION BY s.unique_id ORDER BY
    CASE s.source_column WHEN 'procedure' THEN 1 WHEN 'capability' THEN 2 ELSE 3 END, s.position) AS sentence_no
FROM {FS} s JOIN {VF}.pb_records_in r USING (unique_id)
WHERE s.is_placeholder = false AND s.is_repeat = false""", label="create pb_sentences")

    run(c, f"""
CREATE OR REPLACE TABLE {VF}.pb_records AS
WITH agg AS (
  SELECT unique_id, count(*) n_usable,
    array_join(transform(array_sort(collect_list(struct(sentence_no, sentence))),
                         x -> concat(cast(x.sentence_no AS string), '. ', x.sentence)), '\\n') numbered
  FROM {VF}.pb_sentences GROUP BY unique_id)
SELECT r.*, f.name, f.city, f.state, f.is_shifted, l.verdict AS prev_verdict,
  l.foreign_share AS prev_foreign_share, coalesce(a.n_usable, 0) n_usable,
  concat({lit(PROMPT_HEAD)}, coalesce(f.name,'(none)'),
    '\\nCity: ', coalesce(f.city,'(none)'),
    '\\nState: ', coalesce(f.state,'(none)'),
    '\\nDescription: ', coalesce(substr(f.description,1,1200),'(none)'),
    '{SENT_HEADER}', coalesce(a.numbered, ''),
    {lit(PROMPT_TAIL)}) AS prompt
FROM {VF}.pb_records_in r JOIN {FC} f USING (unique_id)
LEFT JOIN {VF}.contam_llm l USING (unique_id)
LEFT JOIN agg a USING (unique_id)""", label="create pb_records")

    run(c, f"""CREATE OR REPLACE TABLE {VF}.pb_prompt AS SELECT '{PROMPT_VERSION}' AS version,
      {lit(MODEL)} AS model, 0.0 AS temperature, {MAX_TOKENS} AS max_tokens,
      {lit(full_prompt_text())} AS prompt_template""", label="create pb_prompt")
    print(run(c, f"""SELECT stage, grp, count(*) n, sum(CASE WHEN is_shifted THEN 1 ELSE 0 END) shifted,
      min(n_usable) min_n, max(n_usable) max_n, max(length(prompt)) max_len
      FROM {VF}.pb_records GROUP BY 1,2 ORDER BY 1,2""", True, "summary pb_records"))
    flush_timings(c)


# ---------------------------------------------------------------------------------- validate
ALLOWED = {"consistent", "partly_foreign", "mostly_foreign"}
RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


# fix (a), user decision after stage-0 run 1: quote bare a-b tokens before json parsing
BARE_RANGE_RE = re.compile(r'([\[,]\s*)(\d+)\s*-\s*(\d+)(\s*)(?=[,\]])')
DIGITS_RE = re.compile(r"^\s*(\d+)\s*$")


def normalise(raw):
    return BARE_RANGE_RE.sub(r'\1"\2-\3"\4', raw)


def parse(raw, n):
    if raw is None:
        return None, "null response"
    try:
        o = json.loads(normalise(raw[raw.index("{"): raw.rindex("}") + 1]))
    except Exception as e:  # noqa: BLE001
        return None, f"unparseable: {str(e)[:60]}"
    if not isinstance(o, dict):
        return None, "not an object"
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
        return None, "bad other_names"
    fl = o.get("foreign_sentences")
    if not isinstance(fl, list):
        return None, "foreign_sentences not a list"
    nums = set()
    for x in fl:
        if isinstance(x, int) and not isinstance(x, bool):
            if not 1 <= x <= n:
                return None, "foreign_sentences out of range"
            nums.add(x)
        elif isinstance(x, str) and DIGITS_RE.match(x):  # lenient: "7" -> 7
            k = int(x)
            if not 1 <= k <= n:
                return None, "foreign_sentences out of range"
            nums.add(k)
        elif isinstance(x, str) and RANGE_RE.match(x):
            a, b = map(int, RANGE_RE.match(x).groups())
            if not (1 <= a <= b <= n):
                return None, "foreign_sentences out of range"
            nums.update(range(a, b + 1))
        else:
            return None, "foreign_sentences bad item"
    r = o.get("reason")
    if not isinstance(r, str):
        return None, "bad reason"
    return {"verdict": v, "foreign_share": float(fs), "other_names": on, "reason": r,
            "foreign_sentences_raw": fl, "flagged": sorted(nums)}, None


def stage_run(c, stage, tag=""):
    recs = run(c, f"SELECT unique_id, n_usable FROM {VF}.pb_records WHERE stage = {stage}", True,
               f"stage{stage} list")
    n_of = {r["unique_id"]: r["n_usable"] for r in recs}
    results, errs, attempts = {}, {}, {}
    pending = list(n_of)
    wall = {}
    for attempt in (1, 2):  # attempt 2 = the single retry of malformed rows
        if not pending:
            break
        temp = 0.0 if attempt == 1 else 0.3
        tbl = f"{VF}.pb_raw_s{stage}{tag}_a{attempt}"
        inlist = ",".join(lit(i) for i in pending)
        t0 = time.time()
        run(c, f"""
CREATE OR REPLACE TABLE {tbl} AS
SELECT unique_id, r.result AS raw, r.errorMessage AS err FROM (
  SELECT unique_id, ai_query('{MODEL}', prompt,
      modelParameters => named_struct('max_tokens', {MAX_TOKENS}, 'temperature', {temp}),
      failOnError => false) AS r
  FROM {VF}.pb_records WHERE unique_id IN ({inlist}))""",
            label=f"stage{stage}{tag} ai_query attempt{attempt} ({len(pending)} rows)")
        wall[attempt] = round(time.time() - t0, 2)
        rows = run(c, f"SELECT * FROM {tbl}", True, f"stage{stage} read attempt{attempt}")
        nxt = []
        for r in rows:
            uid = r["unique_id"]
            attempts[uid] = attempt
            res, e = parse(r["raw"], n_of[uid]) if not r["err"] else (None, f"endpoint error: {r['err'][:100]}")
            if res:
                results[uid] = res
                errs.pop(uid, None)
            else:
                errs[uid] = e
                nxt.append(uid)
        pending = nxt
        print(f"attempt {attempt}: valid so far {len(results)}, malformed {len(nxt)}", flush=True)

    vals = []
    for uid, n in n_of.items():
        r = results.get(uid)
        if r:
            share = len(r["flagged"]) / n if n else None
            vals.append(
                f"({lit(uid)},{stage},{attempts[uid]},{lit(r['verdict'])},{r['foreign_share']},"
                f"{lit(json.dumps(r['foreign_sentences_raw']))},{lit(json.dumps(r['flagged']))},"
                f"{len(r['flagged'])},{n},{'NULL' if share is None else share},"
                f"{lit(json.dumps(r['other_names'], ensure_ascii=False))},{lit(r['reason'])},NULL)")
        else:
            vals.append(f"({lit(uid)},{stage},{attempts.get(uid, 0)},NULL,NULL,NULL,NULL,NULL,{n},NULL,"
                        f"NULL,NULL,{lit(errs.get(uid, 'missing'))})")
    run(c, f"""CREATE TABLE IF NOT EXISTS {VF}.pb_audit (unique_id STRING, stage INT, attempts INT,
      verdict STRING, foreign_share DOUBLE, foreign_sentences STRING, flagged_numbers STRING,
      n_flagged INT, n_usable INT, flagged_share DOUBLE, other_names STRING, reason STRING,
      error STRING)""", label="create pb_audit")
    run(c, f"DELETE FROM {VF}.pb_audit WHERE stage = {stage}", label=f"stage{stage} clear pb_audit")
    run(c, f"INSERT INTO {VF}.pb_audit VALUES " + ",".join(vals), label=f"stage{stage} insert pb_audit")

    # per-sentence flags
    run(c, f"""CREATE TABLE IF NOT EXISTS {VF}.pb_sentence_flags (unique_id STRING, sentence_no INT,
      source_column STRING, position INT, sentence STRING, is_foreign BOOLEAN)""",
        label="create pb_sentence_flags")
    run(c, f"""DELETE FROM {VF}.pb_sentence_flags WHERE unique_id IN
      (SELECT unique_id FROM {VF}.pb_records WHERE stage = {stage})""", label=f"stage{stage} clear flags")
    run(c, f"""
INSERT INTO {VF}.pb_sentence_flags
SELECT s.unique_id, cast(s.sentence_no AS INT), s.source_column, s.position, s.sentence,
  array_contains(from_json(a.flagged_numbers, 'array<int>'), cast(s.sentence_no AS INT)) AS is_foreign
FROM {VF}.pb_sentences s JOIN {VF}.pb_audit a USING (unique_id)
WHERE a.stage = {stage} AND a.verdict IS NOT NULL""", label=f"stage{stage} insert flags")

    json.dump({"stage": stage, "wall_ai_query": wall, "n_records": len(n_of),
               "valid": len(results), "failed": errs, "attempts": attempts},
              open(f"data/pb_stage{stage}{tag}_run.json", "w"), indent=1)
    reasons = {}
    for e in errs.values():
        k = e.split(":")[0]
        reasons[k] = reasons.get(k, 0) + 1
    print(f"STAGE {stage}: valid {len(results)}/{len(n_of)}, failed {len(errs)} {reasons}, "
          f"ai_query wall {wall}")
    if ARAVIND in n_of:
        r = results.get(ARAVIND)
        print("Aravind:", (len(r["flagged"]) if r else None), "/", n_of[ARAVIND],
              r["verdict"] if r else errs.get(ARAVIND))
    flush_timings(c)


# ---------------------------------------------------------------------------------- report
# token rule = contamination signal a (scripts/contamination.py): name tokens >= 4 chars, not generic,
# not any city name in the data
A_MIN_LEN = 4
A_GENERIC = set("""hospital hospitals clinic clinics eye dental dentist care centre center multispeciality
multispecialty multi speciality specialty super health healthcare medical nursing home institute
research diagnostic diagnostics the and of for dr doctor doctors children women maternity memorial
general city life new sri shri shree lab labs path pathology polyclinic trust foundation private
limited ltd pvt india indian unit road nagar""".split())
ORG_RE = re.compile(r"\b(?:[A-Z][\w.'&-]*\s+){1,6}(?:Hospitals?|Clinic|Centre|Center|Institute|College|"
                    r"Nursing Home)\b")


def classify_sentence(sent, toks, city):
    low = sent.lower()
    words = set(re.split(r"[^a-z0-9]+", low))
    if any(t in words for t in toks) or (city and city.lower() in low):
        return "own"
    if ORG_RE.search(sent):
        return "other"
    return "nobody"


def stage_report(c):
    import numpy as np
    import pandas as pd
    df = pd.DataFrame(run(c, f"""
SELECT r.unique_id, r.grp, r.review_row, r.mark, r.target_verdict, r.review_note, r.stage, r.name,
  r.city, r.prev_verdict, r.prev_foreign_share, a.attempts, a.verdict, a.foreign_share,
  a.foreign_sentences, a.n_flagged, a.n_usable, a.flagged_share, a.other_names, a.reason, a.error
FROM {VF}.pb_records r LEFT JOIN {VF}.pb_audit a USING (unique_id)""", True, "report fetch"))
    nproj = run(c, f"""
SELECT count(*) n FROM (SELECT s.unique_id FROM {FS} s JOIN {FC} f USING (unique_id)
  WHERE NOT f.is_shifted AND s.is_placeholder = false AND s.is_repeat = false
  GROUP BY s.unique_id HAVING count(*) >= 5)""", True, "count projection base")[0]["n"]
    cities = {r["c"] for r in run(c, f"SELECT DISTINCT lower(trim(city)) c FROM {FC} WHERE city IS NOT NULL",
                                  True, "fetch city list")}
    mfids = df[df.verdict == "mostly_foreign"].unique_id.tolist()
    sents = pd.DataFrame(run(c, f"""SELECT unique_id, sentence_no, sentence, is_foreign
      FROM {VF}.pb_sentence_flags WHERE unique_id IN ({",".join(lit(x) for x in mfids)})""", True,
                             "fetch mf sentence flags")) if mfids else pd.DataFrame()
    flush_timings(c)
    df.to_parquet("data/pb_results.parquet")

    order = ["consistent", "partly_foreign", "mostly_foreign"]
    L = []
    w = L.append
    # timings
    r1 = json.load(open("data/pb_stage0_run1.json"))
    r2 = json.load(open("data/pb_stage0r2_run.json"))
    s1 = json.load(open("data/pb_stage1_run.json"))
    w("# Pilot B: record audit with sentence-level output (prompt pb_v1)\n")
    w(f"Model `{MODEL}`, temperature 0 (retry 0.3), max_tokens {MAX_TOKENS}, one record per ai_query row, "
      "on the shared 2X-Small warehouse 8ea2282aca435351. Script `scripts/pilot_b_audit.py`. Tables "
      "`workspace.vf.pb_records, pb_sentences, pb_prompt, pb_raw_*, pb_audit, pb_sentence_flags, pb_timings`.\n")
    w("## Runs\n")
    w(f"- Stage 0 run 1 (strict parser): valid {r1['valid']}/5, failed {len(r1['failed'])} (unparseable JSON: "
      f"unquoted ranges like `35-38`); ai_query wall {r1['wall_ai_query']} s (attempt: seconds). "
      "Tables `pb_raw_s0_a1`, `pb_raw_s0_a2`.")
    w(f"- Fix (a) applied (user decision): pre-parse normalisation quotes bare `a-b` tokens inside lists "
      "(regex `([\\[,]\\s*)(\\d+)\\s*-\\s*(\\d+)(\\s*)(?=[,\\]])`), and digit strings like `\"7\"` are accepted "
      "as integers. No prompt change.")
    w(f"- Stage 0 run 2 (same 5 records, new calls): valid {r2['valid']}/5, failed {len(r2['failed'])}; "
      f"ai_query wall {r2['wall_ai_query']} s. Table `pb_raw_s0r2_a1`.")
    w(f"- Stage 1 (56 records, one statement): valid {s1['valid']}/56, failed {len(s1['failed'])}; "
      f"ai_query wall {s1['wall_ai_query']} s. Retries needed: "
      f"{sum(1 for v in s1['attempts'].values() if v > 1)}.")
    w("- Note: temperature 0 is not deterministic here. Aravind flagged 63/149 in run 1 and "
      f"{int(df[df.unique_id == ARAVIND].n_flagged.iloc[0])}/149 in run 2.\n")
    w("### Statement timings (UTC)\n")
    w("| statement | start | end | s |\n|---|---|---|---|")
    for line in open(TIMING_LOG):
        t = json.loads(line)
        w(f"| {t['label']} | {t['start']} | {t['end']} | {t['seconds']} |")
    w("")
    # speed
    tot_rec = 61
    sec_best = (r2["wall_ai_query"]["1"] + s1["wall_ai_query"]["1"]) / tot_rec
    sec_worst = r1["wall_ai_query"]["1"] / 5
    w("## Speed\n")
    w(f"- Final runs: {r2['wall_ai_query']['1'] + s1['wall_ai_query']['1']:.1f} s ai_query wall for 61 records = "
      f"{sec_best:.2f} s/record. Stage 1 alone: {s1['wall_ai_query']['1'] / 56:.2f} s/record.")
    w(f"- Worst observed: stage 0 run 1, {sec_worst:.2f} s/record (5 rows, first call of the session).")
    w(f"- Projection base: {nproj} non-shifted facilities with >= 5 usable sentences. "
      f"Projected {nproj * sec_best / 60:.0f} min at {sec_best:.2f} s/rec; {nproj * sec_worst / 60:.0f} min at "
      f"the worst observed {sec_worst:.2f} s/rec. Shared warehouse; batches of 56 may not scale linearly.\n")
    # tables
    w("## Verdict now vs before\n")
    xt = pd.crosstab(df.prev_verdict, df.verdict).reindex(index=order, columns=order).fillna(0).astype(int)
    w("| before \\ now | " + " | ".join(order) + " |\n|---|---|---|---|")
    for v in order:
        w(f"| {v} | " + " | ".join(str(xt.loc[v, k]) for k in order) + " |")
    w("\n(Aravind had no earlier verdict: " + str(df[df.unique_id == ARAVIND].verdict.iloc[0]) + ".)\n")
    rv = df[df.grp.isin(["reviewed_mf", "reviewed_pf"])].copy()
    rv["markc"] = rv.mark.replace("", "agree")
    xm = pd.crosstab(rv.markc, rv.verdict).reindex(index=["W", "D", "agree"], columns=order).fillna(0).astype(int)
    w("## Verdict now vs earlier reviewer marks (40 reviewed)\n")
    w("| mark \\ now | " + " | ".join(order) + " |\n|---|---|---|---|")
    for m in ["W", "D", "agree"]:
        w(f"| {m} | " + " | ".join(str(xm.loc[m, k]) for k in order) + " |")
    agree = rv[rv.markc == "agree"]
    w(f"\nAgree-marked rows keeping their earlier verdict: {(agree.verdict == agree.prev_verdict).sum()}/{len(agree)}.\n")
    W = rv[rv.mark == "W"].copy()
    W["right"] = W.verdict == W.target_verdict
    w(f"## W records ({W.right.sum()}/{len(W)} now right; right = verdict equals reviewer target)\n")
    w("| row | name | city | before | target | now | flagged/N | right | reviewer note |\n|---|---|---|---|---|---|---|---|---|")
    for _, r in W.sort_values("review_row").iterrows():
        w(f"| {int(r.review_row)} | {r["name"][:40]} | {r.city} | {r.prev_verdict} | {r.target_verdict} | {r.verdict} | "
          f"{r.n_flagged}/{r.n_usable} | {'yes' if r.right else 'no'} | {r.review_note} |")
    w("\nMapping note: the brief says 13 over/under-called cases; the review lists 14 W rows, all with a stated "
      "target (4 mostly_foreign W rows, 9 over-called partly_foreign, 1 under-called). Row 36 (Rani Durgavati, "
      "'affiliations, not foreign content') is mapped to consistent. Row 12 and 18 targets are partly_foreign "
      "('~25% foreign'). Targets come from the review table in the session transcript; the JSON files hold no marks.\n")
    D = rv[rv.mark == "D"]
    w("D rows (no target): " + "; ".join(f"{r['name'][:30]} {r.prev_verdict}->{r.verdict} ({r.review_note})"
                                         for _, r in D.iterrows()) + "\n")
    # shares
    ok = df[df.verdict.notna()].copy()
    w("## Flagged share vs model foreign_share\n")
    w("| verdict now | n | mean flagged share | mean foreign_share |\n|---|---|---|---|")
    for v in order:
        g = ok[ok.verdict == v]
        if len(g):
            w(f"| {v} | {len(g)} | {g.flagged_share.mean():.3f} | {g.foreign_share.mean():.3f} |")
    pr = np.corrcoef(ok.flagged_share, ok.foreign_share)[0, 1]
    sp = ok.flagged_share.rank().corr(ok.foreign_share.rank())
    mad = (ok.flagged_share - ok.foreign_share).abs().mean()
    def band(x):
        return "consistent" if x < 0.05 else ("mostly_foreign" if x > 0.5 else "partly_foreign")
    bandagree = (ok.flagged_share.map(band) == ok.verdict).mean()
    w(f"\nPearson r = {pr:.3f}, Spearman = {sp:.3f}, mean |flagged share - foreign_share| = {mad:.3f}. "
      f"Verdict implied by flagged share (<0.05 consistent, >0.5 mostly, else partly) matches the model verdict "
      f"in {bandagree:.0%} of {len(ok)} records.")
    mfo = ok[ok.verdict == "mostly_foreign"]
    w(f"mostly_foreign records whose flagged list covers > 50% of sentences: {(mfo.flagged_share > 0.5).sum()}/{len(mfo)}; "
      f"partly_foreign records with 0 flagged: {((ok.verdict == 'partly_foreign') & (ok.n_flagged == 0)).sum()}.\n")
    # names-own
    w("## mostly_foreign: what the UNFLAGGED sentences name\n")
    w("Rule (mechanical, applied in order): **own** = sentence contains a distinctive name token of the record "
      "(record name lowercased, split on non-alphanumerics, tokens >= 4 chars, not in the generic list of "
      "contamination signal a, not any city name in facilities_clean; whole-word match) or the record's city string "
      "(case-insensitive substring). Else **other org** = matches regex "
      f"`{ORG_RE.pattern}` (1-6 capitalised words ending in Hospital(s)/Clinic/Centre/Center/Institute/College/"
      "Nursing Home). Else **nobody**. A sentence naming both own and another org counts as own.\n")
    w("| name | city | N | flagged | unflagged | own | nobody | other org |\n|---|---|---|---|---|---|---|---|")
    mf_rows = []
    for _, r in ok[ok.verdict == "mostly_foreign"].iterrows():
        toks = {t for t in re.split(r"[^a-z0-9]+", (r["name"] or "").lower())
                if len(t) >= A_MIN_LEN and t not in A_GENERIC and t not in cities}
        u = sents[(sents.unique_id == r.unique_id) & (~sents.is_foreign)]
        cl = u.sentence.map(lambda x: classify_sentence(x, toks, r.city)).value_counts()
        row = (r["name"][:40], r.city, r.n_usable, r.n_flagged, len(u), int(cl.get("own", 0)),
               int(cl.get("nobody", 0)), int(cl.get("other", 0)), sorted(toks))
        mf_rows.append(row)
        w("| " + " | ".join(str(x) for x in row[:8]) + " |")
    if mf_rows:
        tt = [sum(x[i] for x in mf_rows) for i in range(2, 8)]
        w(f"| **total** | | {tt[0]} | {tt[1]} | {tt[2]} | {tt[3]} | {tt[4]} | {tt[5]} |")
    w("\nName tokens used: " + "; ".join(f"{x[0][:25]}: {x[8]}" for x in mf_rows) + "\n")
    # per record
    w("## Per-record table (all 61)\n")
    w("| grp | row | mark | name | city | before | now | fshare | flagged/N | att | foreign_sentences | other_names | reason |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in df.sort_values(["grp", "review_row", "name"]).iterrows():
        w(f"| {r.grp} | {'' if pd.isna(r.review_row) else int(r.review_row)} | {r.mark} | {r['name'][:40]} | {r.city} | "
          f"{r.prev_verdict} | {r.verdict} | {r.foreign_share} | {r.n_flagged}/{r.n_usable} | {r.attempts} | "
          f"`{r.foreign_sentences}` | {(r.other_names or '').replace('|', '/')[:120]} | {(r.reason or '').replace('|', '/')} |")
    w("\n## Exact prompt (pb_v1)\n")
    w("Record fields and numbered usable sentences (procedure, capability, equipment, then position; "
      "is_placeholder = false AND is_repeat = false) are substituted where shown.\n")
    w("```\n" + full_prompt_text() + "\n```\n")
    w("Changes vs the contamination prompt: added the foreign_sentences output field; the branch line now reads "
      "'branch, unit, parent or sister unit of the same group'; added the city-alias/locality line; added the "
      "similar-name-other-city line. Retry (only stage 0 run 1 needed it): same prompt, temperature 0.3.")
    open("reports/pilot_b_audit.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L[:200]))


if __name__ == "__main__":
    st = sys.argv[1]
    with conn() as c:
        if st == "select":
            stage_select(c)
        elif st == "stage0":
            stage_run(c, 0)
        elif st == "stage0r2":  # rerun after parser fix (a), new ai_query calls
            stage_run(c, 0, "r2")
        elif st == "stage1":
            stage_run(c, 1)
        elif st == "report":
            stage_report(c)

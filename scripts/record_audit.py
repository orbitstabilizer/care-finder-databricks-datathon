"""Full record audit (prompt pb_v1 + parser fix (a)), reusing Pilot B's prompt and parser.

Usage:  python scripts/record_audit.py prepare | stage0 | stage1 | retry | comments | summary
Reads only workspace.vf.facilities_clean (non-shifted) and workspace.vf.facility_sentences (usable =
is_placeholder false AND is_repeat false); reads sentence_tags only to compute the tagging failed-row rate.
Writes workspace.vf.record_audit, workspace.vf.sentence_foreign_flag and helper tables workspace.vf.ra_*.
One statement at a time; a fresh connection (and token) per statement.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilot_b_audit as pb  # noqa: E402  (prompt text, parser with fix (a), lit, conn)

VF = "workspace.vf"
FC, FS = f"{VF}.facilities_clean", f"{VF}.facility_sentences"
MODEL, MAX_TOKENS, PROMPT_VERSION = pb.MODEL, pb.MAX_TOKENS, pb.PROMPT_VERSION
SEED = "ra2026"
ARAVIND = pb.ARAVIND
N_STAGE1_CHUNKS = 7  # ~9,477 / 7 = ~1,354 records per chunk
RETRY_TEMP = 0.3     # same as Pilot B's single retry
RATE_LIMIT = 0.03
LOG = "data/ra_timings.jsonl"
lit = pb.lit

# Credits/quota standing rule (CLAUDE.md): stop at once, do not store those rows as failed, report.
import re  # noqa: E402
CREDIT_RE = re.compile(r"quota|credit|billing|limit exceeded|limit_exceeded|resource_exhausted|payment|insufficient|"
                       r"warehouse.{0,40}(start|stopped|not running)", re.I)
CREDIT_SQL = ("lower(coalesce(fail_reason,'')) RLIKE 'quota|credit|billing|limit exceeded|limit_exceeded|"
              "resource_exhausted|payment|insufficient'")
BULK_SHARE = 0.30


class CreditsExhausted(Exception):
    pass


def run(q, fetch=False, label=None):
    t0 = time.time()
    s0 = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with pb.conn() as c, c.cursor() as cur:
            cur.execute(q)
            out = None
            if fetch:
                cols = [d[0] for d in cur.description]
                out = [dict(zip(cols, r)) for r in cur.fetchall()]
    except CreditsExhausted:
        raise
    except Exception as e:  # noqa: BLE001
        if CREDIT_RE.search(str(e)):
            raise CreditsExhausted(f"statement error ({label}): {str(e)[:500]}") from e
        raise
    finally:
        rec = {"label": label or q.strip().split("\n")[0][:80], "start": s0,
               "end": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "seconds": round(time.time() - t0, 2)}
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{rec['start']} -> {rec['end']}] {rec['seconds']:8.1f}s  {rec['label']}", flush=True)
    return out


# ------------------------------------------------------------------------------------ prepare
def prepare():
    run(f"""
CREATE OR REPLACE TABLE {VF}.ra_sentences AS
WITH u AS (
  SELECT s.unique_id, s.source_column, s.position, s.sentence
  FROM {FS} s JOIN {FC} f USING (unique_id)
  WHERE NOT f.is_shifted AND s.is_placeholder = false AND s.is_repeat = false),
pop AS (SELECT unique_id FROM u GROUP BY unique_id HAVING count(*) >= 5)
SELECT u.unique_id, u.source_column, u.position, u.sentence,
  CAST(row_number() OVER (PARTITION BY u.unique_id ORDER BY
    CASE u.source_column WHEN 'procedure' THEN 1 WHEN 'capability' THEN 2 ELSE 3 END, u.position) AS INT)
    AS sentence_no
FROM u JOIN pop USING (unique_id)""", label="create ra_sentences")

    # stage 0 = Aravind + 99 seeded-random others; stage 1 = the rest in 7 seeded chunks
    run(f"""
CREATE OR REPLACE TABLE {VF}.ra_inputs AS
WITH agg AS (
  SELECT unique_id, count(*) n_usable,
    array_join(transform(array_sort(collect_list(struct(sentence_no, sentence))),
                         x -> concat(cast(x.sentence_no AS string), '. ', x.sentence)), '\\n') numbered
  FROM {VF}.ra_sentences GROUP BY unique_id),
ord AS (
  SELECT unique_id, row_number() OVER (ORDER BY CASE WHEN unique_id = '{ARAVIND}' THEN 0 ELSE 1 END,
                                        md5(concat('{SEED}', unique_id))) rn
  FROM agg),
ch AS (
  SELECT unique_id, rn,
    CASE WHEN rn <= 100 THEN 's0'
         ELSE concat('s1_c', lpad(cast(ntile({N_STAGE1_CHUNKS}) OVER (ORDER BY rn) AS string), 2, '0')) END tmp
  FROM ord)
SELECT a.unique_id, CAST(a.n_usable AS INT) n_usable,
  CASE WHEN ch.rn <= 100 THEN 's0' ELSE ch.tmp END AS chunk_id,
  concat({lit(pb.PROMPT_HEAD)}, coalesce(f.name,'(none)'),
    '\\nCity: ', coalesce(f.city,'(none)'),
    '\\nState: ', coalesce(f.state,'(none)'),
    '\\nDescription: ', coalesce(substr(f.description,1,1200),'(none)'),
    '{pb.SENT_HEADER}', a.numbered,
    {lit(pb.PROMPT_TAIL)}) AS prompt
FROM agg a JOIN ch USING (unique_id) JOIN {FC} f USING (unique_id)""", label="create ra_inputs")
    # ntile above runs over all rows incl. stage 0; recompute stage-1 chunks over stage-1 rows only
    run(f"""
CREATE OR REPLACE TABLE {VF}.ra_inputs AS
WITH o AS (SELECT *, row_number() OVER (ORDER BY CASE WHEN unique_id = '{ARAVIND}' THEN 0 ELSE 1 END,
                                        md5(concat('{SEED}', unique_id))) rn FROM {VF}.ra_inputs),
s1 AS (SELECT unique_id, ntile({N_STAGE1_CHUNKS}) OVER (ORDER BY rn) k FROM o WHERE rn > 100)
SELECT o.unique_id, o.n_usable,
  CASE WHEN o.rn <= 100 THEN 's0' ELSE concat('s1_c', lpad(cast(s1.k AS string), 2, '0')) END chunk_id,
  o.prompt
FROM o LEFT JOIN s1 USING (unique_id)""", label="rechunk ra_inputs")
    print(run(f"""SELECT chunk_id, count(*) n, min(n_usable) mn, max(n_usable) mx, max(length(prompt)) maxlen,
      sum(CASE WHEN unique_id = '{ARAVIND}' THEN 1 ELSE 0 END) aravind
      FROM {VF}.ra_inputs GROUP BY 1 ORDER BY 1""", True, "summary ra_inputs"))
    # prompt identity check vs Pilot B's stored prompt for the same records
    print(run(f"""SELECT count(*) n_common, sum(CASE WHEN i.prompt = p.prompt THEN 1 ELSE 0 END) n_identical
      FROM {VF}.ra_inputs i JOIN {VF}.pb_records p USING (unique_id)""", True, "prompt identity vs pb_records"))

    run(f"""CREATE TABLE IF NOT EXISTS {VF}.ra_raw (unique_id STRING, chunk_id STRING, attempt INT,
      temperature DOUBLE, raw STRING, err STRING, called_at TIMESTAMP)""", label="create ra_raw")
    run(f"""CREATE TABLE IF NOT EXISTS {VF}.ra_parsed (unique_id STRING, attempt INT,
      foreign_sentences STRING, flagged ARRAY<INT>)""", label="create ra_parsed")
    run(f"""CREATE TABLE IF NOT EXISTS {VF}.record_audit (unique_id STRING, verdict STRING,
      foreign_share DOUBLE, other_names ARRAY<STRING>, reason STRING, n_usable INT, n_flagged INT,
      flagged_share DOUBLE, failed BOOLEAN, fail_reason STRING, attempts INT, chunk_id STRING,
      prompt_version STRING, audited_at TIMESTAMP)""", label="create record_audit")
    run(f"""CREATE TABLE IF NOT EXISTS {VF}.sentence_foreign_flag (unique_id STRING, sentence_no INT,
      source_column STRING, position INT, is_foreign BOOLEAN)""", label="create sentence_foreign_flag")


# ------------------------------------------------------------------------------------ core
def call(where, chunk_label, attempt, temp, n):
    t0 = time.time()
    run(f"""
INSERT INTO {VF}.ra_raw
SELECT unique_id, '{chunk_label}', {attempt}, {temp}, r.result, r.errorMessage, current_timestamp() FROM (
  SELECT unique_id, ai_query('{MODEL}', prompt,
      modelParameters => named_struct('max_tokens', {MAX_TOKENS}, 'temperature', {temp}),
      failOnError => false) AS r
  FROM {VF}.ra_inputs i WHERE {where})""", label=f"{chunk_label} ai_query attempt{attempt} ({n} rows)")
    return round(time.time() - t0, 2)


def screen_credit(rows, chunk, attempt):
    """Return error text if the rows show credit/quota exhaustion; also drop those raw rows so a resume recalls them."""
    errs = [r["err"] for r in rows if r["err"]]
    bad = {e for e in errs if CREDIT_RE.search(e)}
    if errs:
        top, cnt = max(((e, errs.count(e)) for e in set(errs)), key=lambda x: x[1])
        if rows and cnt / len(rows) > BULK_SHARE:
            bad.add(top)
    if not bad:
        return None
    ids = ",".join(lit(r["unique_id"]) for r in rows if r["err"] in bad)
    run(f"DELETE FROM {VF}.ra_raw WHERE attempt = {attempt} AND unique_id IN ({ids})", label="drop credit-error raw rows")
    rows[:] = [r for r in rows if r["err"] not in bad]
    return sorted(bad)[0]


def store(rows, attempt):
    """rows: dicts with unique_id, chunk_id, n_usable, raw, err. Parse, then write audit + flags."""
    audit, parsed, reasons = [], [], {}
    for r in rows:
        uid, n = r["unique_id"], r["n_usable"]
        res, e = pb.parse(r["raw"], n) if not r["err"] else (None, f"endpoint error: {r['err'][:100]}")
        if res:
            k = len(res["flagged"])
            names = "array(" + ",".join(lit(x) for x in res["other_names"]) + ")" if res["other_names"] \
                else "CAST(array() AS ARRAY<STRING>)"
            audit.append(f"({lit(uid)},{lit(res['verdict'])},{res['foreign_share']},{names},{lit(res['reason'])},"
                         f"{n},{k},{k / n},false,NULL,{attempt},{lit(r['chunk_id'])})")
            parsed.append(f"({lit(uid)},{attempt},{lit(json.dumps(res['foreign_sentences_raw']))},"
                          f"array({','.join(map(str, res['flagged']))}))" if res["flagged"] else
                          f"({lit(uid)},{attempt},{lit(json.dumps(res['foreign_sentences_raw']))},"
                          f"CAST(array() AS ARRAY<INT>))")
        else:
            reasons[e.split(":")[0]] = reasons.get(e.split(":")[0], 0) + 1
            audit.append(f"({lit(uid)},NULL,NULL,NULL,NULL,{n},NULL,NULL,true,{lit(e)},{attempt},"
                         f"{lit(r['chunk_id'])})")
    if not audit:
        return 0, reasons
    ids = ",".join(lit(r["unique_id"]) for r in rows)
    if parsed:
        run(f"DELETE FROM {VF}.ra_parsed WHERE attempt = {attempt} AND unique_id IN ({ids})", label="clear ra_parsed")
        run(f"INSERT INTO {VF}.ra_parsed VALUES " + ",".join(parsed), label=f"insert ra_parsed ({len(parsed)})")
    run(f"DELETE FROM {VF}.sentence_foreign_flag WHERE unique_id IN ({ids})", label="clear flags")
    run(f"DELETE FROM {VF}.record_audit WHERE unique_id IN ({ids})", label="clear record_audit")
    run(f"INSERT INTO {VF}.record_audit SELECT *, '{PROMPT_VERSION}', current_timestamp() FROM VALUES "
        + ",".join(audit), label=f"insert record_audit ({len(audit)})")
    run(f"""
INSERT INTO {VF}.sentence_foreign_flag
SELECT s.unique_id, s.sentence_no, s.source_column, s.position,
  CASE WHEN a.failed THEN NULL ELSE array_contains(p.flagged, s.sentence_no) END
FROM {VF}.ra_sentences s JOIN {VF}.record_audit a USING (unique_id)
LEFT JOIN {VF}.ra_parsed p ON p.unique_id = s.unique_id AND p.attempt = a.attempts
WHERE s.unique_id IN ({ids})""", label="insert sentence_foreign_flag")
    return len(parsed), reasons


def run_chunk(chunk):
    pend = f"i.chunk_id = '{chunk}' AND i.unique_id NOT IN (SELECT unique_id FROM {VF}.record_audit)"
    n = run(f"""SELECT count(*) n, sum(CASE WHEN EXISTS (SELECT 1 FROM {VF}.ra_raw r WHERE r.unique_id = i.unique_id
      AND r.attempt = 1) THEN 1 ELSE 0 END) have FROM {VF}.ra_inputs i WHERE {pend}""", True, f"{chunk} pending")[0]
    wall = None
    todo = n["n"] - (n["have"] or 0)
    if todo:  # resume: only call the model for rows with no stored attempt-1 response
        wall = call(pend + f" AND i.unique_id NOT IN (SELECT unique_id FROM {VF}.ra_raw WHERE attempt = 1)",
                    chunk, 1, 0.0, todo)
    rows = run(f"""SELECT i.unique_id, i.chunk_id, i.n_usable, r.raw, r.err FROM {VF}.ra_inputs i
      JOIN (SELECT * FROM {VF}.ra_raw WHERE attempt = 1 QUALIFY row_number() OVER
            (PARTITION BY unique_id ORDER BY called_at DESC) = 1) r USING (unique_id) WHERE {pend}""",
               True, f"{chunk} read raw")
    credit_err = screen_credit(rows, chunk, 1)
    valid, reasons = store(rows, 1)  # non-credit rows of this chunk are kept
    if credit_err:
        raise CreditsExhausted(f"ai_query errorMessage in chunk {chunk}: {credit_err}")
    rec = {"chunk": chunk, "rows": len(rows), "called": todo, "ai_query_seconds": wall, "valid": valid,
           "failed": len(rows) - valid, "reasons": reasons,
           "s_per_record": round(wall / todo, 3) if wall and todo else None}
    with open("data/ra_chunks.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("CHUNK", rec, flush=True)
    return rec


def rates():
    a = run(f"""SELECT count(*) n, sum(CASE WHEN failed THEN 1 ELSE 0 END) f FROM {VF}.record_audit
      WHERE NOT (failed AND {CREDIT_SQL})""", True, "audit failed rate")[0]
    t = run(f"""SELECT count(*) n, sum(CASE WHEN failed THEN 1 ELSE 0 END) f FROM {VF}.sentence_tags
      WHERE prompt_version = 'pa_single_v1' AND NOT (failed AND {CREDIT_SQL})
        AND NOT (failed AND coalesce(fail_reason, '') IN ('claim_without_label', 'unknown_label'))""",
            True, "tagging failed rate (content failures excluded)")[0]
    ar = (a["f"] or 0) / a["n"] if a["n"] else 0.0
    tr = (t["f"] or 0) / t["n"] if t["n"] else 0.0
    return ar, a, tr, t


def stage0():
    t0 = time.time()
    rec = run_chunk("s0")
    secs = round(time.time() - t0, 1)
    vc = run(f"SELECT verdict, count(*) n FROM {VF}.record_audit WHERE chunk_id = 's0' GROUP BY 1", True, "s0 verdicts")
    av = run(f"SELECT verdict, n_flagged, n_usable, failed, fail_reason FROM {VF}.record_audit "
             f"WHERE unique_id = '{ARAVIND}'", True, "aravind")
    ar, a, tr, t = rates()
    print(json.dumps({"stage0": rec, "seconds_total": secs, "verdicts": vc, "aravind": av,
                      "tagging_failed": t, "tagging_rate": tr}, default=str, indent=1))


def stage1():
    chunks = [r["chunk_id"] for r in run(f"""SELECT DISTINCT chunk_id FROM {VF}.ra_inputs
      WHERE chunk_id LIKE 's1_%' ORDER BY 1""", True, "list chunks")]
    t0 = time.time()
    for ch in chunks:
        ar, a, tr, t = rates()
        print(f"before {ch}: audit failed {a['f']}/{a['n']} = {ar:.4f}; tagging failed {t['f']}/{t['n']} = {tr:.4f}",
              flush=True)
        if ar > RATE_LIMIT or tr > RATE_LIMIT:
            print(f"PAUSE before {ch}: audit rate {ar:.4f}, tagging rate {tr:.4f}", flush=True)
            return
        run_chunk(ch)
    print(f"STAGE1 DONE in {time.time() - t0:.0f}s", flush=True)


def retry():
    rows = run(f"SELECT count(*) n FROM {VF}.record_audit WHERE failed AND attempts = 1", True, "retry count")[0]["n"]
    if rows:
        wall = call(f"i.unique_id IN (SELECT unique_id FROM {VF}.record_audit WHERE failed AND attempts = 1)",
                    "retry", 2, RETRY_TEMP, rows)
        got = run(f"""SELECT i.unique_id, a.chunk_id, i.n_usable, r.raw, r.err FROM {VF}.ra_inputs i
          JOIN {VF}.record_audit a USING (unique_id)
          JOIN (SELECT * FROM {VF}.ra_raw WHERE attempt = 2 QUALIFY row_number() OVER
                (PARTITION BY unique_id ORDER BY called_at DESC) = 1) r USING (unique_id)
          WHERE a.failed AND a.attempts = 1""", True, "retry read raw")
        credit_err = screen_credit(got, "retry", 2)
        valid, reasons = store(got, 2)
        if credit_err:
            raise CreditsExhausted(f"ai_query errorMessage in retry pass: {credit_err}")
        rec = {"chunk": "retry", "rows": len(got), "ai_query_seconds": wall, "valid": valid,
               "failed": len(got) - valid, "reasons": reasons}
        with open("data/ra_chunks.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print("RETRY", rec, flush=True)


def comments():
    C = {
        "record_audit": ("One row per audited facility (non-shifted, >= 5 usable sentences). LLM judgement of whether the "
                         "record's usable sentences describe a different organisation (record merging). Prompt pb_v1 "
                         "(text in workspace.vf.pb_prompt), model databricks-meta-llama-3-3-70b-instruct, temperature 0, "
                         "one retry at 0.3. Script scripts/record_audit.py.", {
            "unique_id": "Facility key; joins facilities_clean.unique_id.",
            "verdict": "consistent | partly_foreign | mostly_foreign; NULL if failed.",
            "foreign_share": "Model's own rough share (0-1) of sentences describing another organisation.",
            "other_names": "Up to 5 other facility names the model found in the sentences.",
            "reason": "Model's short reason (<= 15 words).",
            "n_usable": "Usable sentences sent (is_placeholder false AND is_repeat false), numbered 1..n_usable.",
            "n_flagged": "Number of sentences listed as foreign (ranges expanded).",
            "flagged_share": "n_flagged / n_usable; computed, not model-stated.",
            "failed": "True if the response failed validation on all attempts.",
            "fail_reason": "Validation or endpoint error of the last attempt.",
            "attempts": "1 = first call, 2 = after the single retry.",
            "chunk_id": "s0 (stage 0, 100 records) or s1_cNN (stage 1 chunk).",
            "prompt_version": "Prompt version (pb_v1).",
            "audited_at": "Time the row was written."}),
        "sentence_foreign_flag": ("One row per usable sentence of each audited facility; joins facility_sentences on "
                                  "unique_id + source_column + position. is_foreign from record_audit's sentence list.", {
            "unique_id": "Facility key.",
            "sentence_no": "Number shown to the model (order: procedure, capability, equipment, then position).",
            "source_column": "procedure | capability | equipment.",
            "position": "Position within the source column (facility_sentences.position).",
            "is_foreign": "True if the model listed the sentence as describing another organisation; NULL if the audit failed."}),
    }
    for t, (tc, cols) in C.items():
        run(f"COMMENT ON TABLE {VF}.{t} IS {lit(tc)}", label=f"comment {t}")
        for col, cc in cols.items():
            run(f"ALTER TABLE {VF}.{t} ALTER COLUMN {col} COMMENT {lit(cc)}", label=f"comment {t}.{col}")


def summary():
    q = lambda s, l: run(s, True, l)  # noqa: E731
    print(q(f"""SELECT count(*) n, sum(CASE WHEN failed THEN 1 ELSE 0 END) failed,
      sum(CASE WHEN attempts = 2 THEN 1 ELSE 0 END) retried FROM {VF}.record_audit""", "totals"))
    print(q(f"""SELECT verdict, count(*) n, round(count(*) / sum(count(*)) OVER (), 4) share,
      round(avg(flagged_share), 4) mean_flagged_share, round(avg(foreign_share), 4) mean_foreign_share
      FROM {VF}.record_audit GROUP BY 1 ORDER BY 1""", "verdicts"))
    print(q(f"SELECT fail_reason, count(*) n FROM {VF}.record_audit WHERE failed GROUP BY 1", "fail reasons"))
    print(q(f"""SELECT sum(CASE WHEN n_flagged > 0 THEN 1 ELSE 0 END) fac_with_flag, sum(n_flagged) flagged_total
      FROM {VF}.record_audit""", "flag totals"))
    print(q(f"""SELECT count(*) rows, sum(CASE WHEN is_foreign THEN 1 ELSE 0 END) foreign_rows,
      sum(CASE WHEN is_foreign IS NULL THEN 1 ELSE 0 END) null_rows, count(DISTINCT unique_id) fac
      FROM {VF}.sentence_foreign_flag""", "flag table"))
    print(q(f"SELECT * FROM {VF}.record_audit WHERE unique_id = '{ARAVIND}'", "aravind"))


def progress():
    d = run(f"SELECT count(*) n FROM {VF}.record_audit", True, "progress")[0]["n"]
    t = run(f"SELECT count(*) n FROM {VF}.ra_inputs", True, "population")[0]["n"]
    return d, t - d


if __name__ == "__main__":
    try:
        {"prepare": prepare, "stage0": stage0, "stage1": stage1, "retry": retry, "comments": comments,
         "summary": summary}[sys.argv[1]]()
    except CreditsExhausted as e:
        done, left = progress()
        print(f"CREDITS EXHAUSTED, TOP UP NEEDED\n{e}\njob: record_audit {sys.argv[1]}; rows done {done}, "
              f"rows left {left}", flush=True)
        sys.exit(3)

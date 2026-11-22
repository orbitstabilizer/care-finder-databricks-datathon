"""Full sentence service tagging on workspace.vf.distinct_sentences.

Usage:
  python scripts/tag_sentences.py step1    # SQL only: type sets, dental-only rule rows, queue
  python scripts/tag_sentences.py step2    # throughput test: 2,000 in one statement, 2,000 as 4x500
  python scripts/tag_sentences.py step3 [--mode single|conc4] [--chunks N] [--prompt V]
                                           # chunks of ~10,000 from the priority queue
  python scripts/tag_sentences.py step3 --until-tier 1  # stop when the keyword tier is done
  python scripts/tag_sentences.py resume [--mode ...]   # all remaining tiers, then final_retry
                                           # (failed rows, one statement) and comments (skips tagged ids,
                                           # finishes any half-done chunk first)
  python scripts/tag_sentences.py comment  # table + column comments on sentence_tags

Prompt pa_single_v1 (read from workspace.vf.pa_prompt), model
databricks-meta-llama-3-3-70b-instruct, temperature 0, one sentence per ai_query call,
failOnError => false, sentence_id carried in SQL.

Tables (all workspace.vf):
  sentence_tags      result, append only, key sentence_id
  sentence_tags_raw  raw ai_query responses (sentence_id, chunk_id, attempt)
  st_type_sets       per sentence_id: set of facility_types it appears in
  st_queue           untagged-by-rule sentences with priority (1 keyword, 2 hospital, 3 rest)
  st_chunk_members   chunk_id, sentence_id, part (which concurrent statement)
Local log: reports/sentence_tagging/ (statement timings, chunk stats, retry log).
"""

import concurrent.futures as cf
import datetime as dt
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from databricks import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pilot_a_tagger import ALLOWED, PROMPT_SINGLE, PROMPT_SINGLE_VERSION, STRENGTHS  # noqa: E402

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
VF = "workspace.vf"
ROOT = Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "reports" / "sentence_tagging"
CHUNK = 10_000
WRITE_BATCH = 2_000

KEYWORDS = {
    "dialysis": ["dialysis", "haemodialysis", "hemodialysis", "renal replacement", "nephrolog"],
    "caesarean_delivery": ["caesarean", "cesarean", "c-section", "lscs", "delivery", "labour",
                           "labor room", "obstetric", "maternity"],
    "nicu": ["nicu", "neonatal", "newborn", "neonat"],
    "cardiac_surgery": ["cardiac surgery", "cardiothoracic", "bypass", "cabg", "valve",
                        "open heart"],
    "mri": ["mri", "magnetic resonance"],
    "burn_care": ["burn"],
    "icu_emergency": ["icu", "intensive care", "critical care", "emergency", "casualty",
                      "trauma", "ventilator"],
}
# Match on sentence_key (already lowercase) with a leading word boundary only, so prefixes
# like "nephrolog"/"neonat"/"burn" still match "nephrology"/"neonates"/"burns" but "icu"
# does not match "particular".
KEYWORD_REGEX = r"\b(" + "|".join(
    k.replace("-", r"\-") for ks in KEYWORDS.values() for k in ks) + ")"
HOSPITAL_TYPES = ["multispecialty_hospital", "general_hospital_or_nursing_home",
                  "medical_college_teaching_hospital", "government_health_centre",
                  "maternity_women_children", "pediatric", "cardiac", "cancer",
                  "orthopedic_spine", "neuro", "gastro_liver", "kidney_urology"]


def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def log(kind: str, rec: dict):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now(), **rec}
    with open(LOGDIR / f"{kind}.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(kind, json.dumps(rec), flush=True)


# ---------------------------------------------------------------- credit guard
# Standing rule (CLAUDE.md "Credits and quota"): quota/credit exhaustion is a pause, not a
# failure. Stop at once, write nothing for the affected chunk, exit cleanly.
CREDIT_RE = re.compile(r"quota|credit|billing|limit exceeded|REQUEST_LIMIT_EXCEEDED|"
                       r"RESOURCE_EXHAUSTED|PAYMENT|insufficient", re.I)
BULK_SHARE = 0.30


class CreditsExhausted(Exception):
    pass


def credit_check(where: str, errs: list):
    """errs: errorMessage per raw row (None when ok). Raise CreditsExhausted on (a) or (b)."""
    msgs = [e for e in errs if e]
    hit = next((e for e in msgs if CREDIT_RE.search(e)), None)
    if hit:
        raise CreditsExhausted(f"{where}: errorMessage matches credit pattern: {hit}")
    if errs and msgs:
        top, n = Counter(msgs).most_common(1)[0]
        if n > BULK_SHARE * len(errs):
            raise CreditsExhausted(f"{where}: {n}/{len(errs)} rows share errorMessage: {top}")


def run(label: str, query: str, params=None, fetch=True):
    """One statement on a fresh connection (fresh token every statement)."""
    t0 = time.time()
    try:
        with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token()) as c:
            with c.cursor() as cur:
                cur.execute(query, params) if params is not None else cur.execute(query)
                rows = cur.fetchall() if fetch else None
    except Exception as e:  # noqa: BLE001  (c) warehouse/statement errors with credit text
        if CREDIT_RE.search(str(e)):
            raise CreditsExhausted(f"statement {label}: {e}") from e
        raise
    log("statements", {"label": label, "seconds": round(time.time() - t0, 2)})
    return rows


# ---------------------------------------------------------------- tables

def ensure_tables():
    run("create_sentence_tags", f"""
        CREATE TABLE IF NOT EXISTS {VF}.sentence_tags (
          sentence_id STRING, is_claim BOOLEAN, services ARRAY<STRING>, strength STRING,
          suggested_name STRING, prompt_version STRING, chunk_id STRING, failed BOOLEAN,
          fail_reason STRING, tagged_at TIMESTAMP)""", fetch=False)
    run("create_sentence_tags_raw", f"""
        CREATE TABLE IF NOT EXISTS {VF}.sentence_tags_raw (
          sentence_id STRING, chunk_id STRING, attempt INT, part INT,
          resp STRUCT<result: STRING, errorMessage: STRING>, created_at TIMESTAMP)""",
        fetch=False)
    run("create_st_chunk_members", f"""
        CREATE TABLE IF NOT EXISTS {VF}.st_chunk_members (
          chunk_id STRING, sentence_id STRING, part INT, created_at TIMESTAMP)""", fetch=False)


PROMPT_VERSION = PROMPT_SINGLE_VERSION  # set by --prompt (pa_single_v1 | pa_compact_v1)


def load_prompt() -> str:
    rows = run("read_prompt", f"SELECT prompt, model FROM {VF}.pa_prompt "
               f"WHERE prompt_version = '{PROMPT_VERSION}'")
    prompt, model = rows[0]
    assert model == MODEL
    if PROMPT_VERSION == PROMPT_SINGLE_VERSION:
        assert prompt == PROMPT_SINGLE, "pa_prompt differs from pilot_a_tagger"
    return prompt


# ---------------------------------------------------------------- step 1

def step1():
    ensure_tables()
    run("create_st_type_sets", f"""
        CREATE OR REPLACE TABLE {VF}.st_type_sets AS
        WITH occ AS (
          SELECT DISTINCT fs.sentence_key, coalesce(ft.facility_type, '(no_type_row)') AS ftype
          FROM {VF}.facility_sentences fs
          LEFT JOIN {VF}.facility_type ft USING (unique_id)
          WHERE NOT fs.is_placeholder)
        SELECT d.sentence_id, d.sentence_key, array_sort(collect_set(o.ftype)) AS types
        FROM {VF}.distinct_sentences d JOIN occ o USING (sentence_key)
        GROUP BY d.sentence_id, d.sentence_key""", fetch=False)
    tot = run("count_type_sets", f"""
        SELECT count(*), (SELECT count(*) FROM {VF}.distinct_sentences)
        FROM {VF}.st_type_sets""")[0]
    single = run("single_type_counts", f"""
        SELECT types[0], count(*) FROM {VF}.st_type_sets WHERE size(types) = 1
        GROUP BY 1 ORDER BY 2 DESC""")
    multi = run("multi_type_count",
                f"SELECT count(*) FROM {VF}.st_type_sets WHERE size(types) >= 2")[0][0]
    log("step1", {"type_sets_rows": tot[0], "distinct_sentences": tot[1],
                  "single_type": {t: n for t, n in single}, "two_plus_types": multi})

    run("insert_dental_rule", f"""
        INSERT INTO {VF}.sentence_tags
        SELECT s.sentence_id, CAST(NULL AS BOOLEAN), array('dental'), CAST(NULL AS STRING),
               CAST(NULL AS STRING), 'rule_dental_only', 'rule_dental_only', false,
               CAST(NULL AS STRING), current_timestamp()
        FROM {VF}.st_type_sets s
        WHERE s.types = array('dental')
          AND NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = s.sentence_id)
    """, fetch=False)

    hosp = ", ".join(f"'{t}'" for t in HOSPITAL_TYPES)
    run("create_st_queue", f"""
        CREATE OR REPLACE TABLE {VF}.st_queue AS
        SELECT d.sentence_id, d.example_sentence, d.n_facilities,
               CASE WHEN d.sentence_key RLIKE ? THEN 1
                    WHEN arrays_overlap(s.types, array({hosp})) THEN 2
                    ELSE 3 END AS priority,
               row_number() OVER (ORDER BY
                 CASE WHEN d.sentence_key RLIKE ? THEN 1
                      WHEN arrays_overlap(s.types, array({hosp})) THEN 2 ELSE 3 END,
                 d.n_facilities DESC, d.sentence_id) AS ord
        FROM {VF}.distinct_sentences d
        LEFT JOIN {VF}.st_type_sets s USING (sentence_id)
        WHERE s.types IS NULL OR s.types != array('dental')""",
        [KEYWORD_REGEX, KEYWORD_REGEX], fetch=False)
    q = run("queue_counts", f"""
        SELECT priority, count(*) FROM {VF}.st_queue GROUP BY 1 ORDER BY 1""")
    dental = run("dental_rows", f"SELECT count(*) FROM {VF}.sentence_tags "
                 "WHERE prompt_version = 'rule_dental_only'")[0][0]
    remaining = remaining_count()
    log("step1", {"dental_rule_rows": dental, "queue_by_priority": {p: n for p, n in q},
                  "remaining_to_tag": remaining, "keyword_regex": KEYWORD_REGEX})


def next_tier():
    """Lowest priority tier that still has untagged rows not yet assigned to a chunk."""
    return run("next_tier", f"""
        SELECT min(priority) FROM {VF}.st_queue q
        WHERE NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = q.sentence_id)
          AND NOT EXISTS (SELECT 1 FROM {VF}.st_chunk_members m WHERE m.sentence_id = q.sentence_id)
    """)[0][0]


def remaining_count() -> int:
    return run("remaining", f"""
        SELECT count(*) FROM {VF}.st_queue q
        WHERE NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = q.sentence_id)
    """)[0][0]


# ---------------------------------------------------------------- tagging core

def validate(res, err):
    """Return (obj, fail_reason, over_length)."""
    if err or res is None:
        return None, "ai_query_error", False
    try:
        o = json.loads(res[res.index("{"): res.rindex("}") + 1])
    except Exception:  # noqa: BLE001
        return None, "unparseable", False
    if not isinstance(o, dict):
        return None, "unparseable", False
    claim, svc, st = o.get("is_claim"), o.get("services"), o.get("strength")
    if not isinstance(claim, bool):
        return None, "is_claim_not_bool", False
    if not isinstance(svc, list):
        return None, "services_not_list", False
    if any(s not in ALLOWED for s in svc):
        return None, "unknown_label", False
    if st not in STRENGTHS:
        return None, "bad_strength", False
    if claim is False and (svc or st != "na"):
        return None, "inconsistent_false", False
    if claim is True and not svc:
        # Not a failure (user rule): unlabelled claim -> other_clinical, flagged.
        o["services"], o["_unlabelled"] = ["other_clinical"], True
        return o, None, False
    name = o.get("suggested_name")
    if "other_clinical" in svc:
        if not isinstance(name, str) or not name.strip():
            return None, "missing_suggested_name", False
        return o, None, len(name.split()) > 4
    return o, None, False


def create_chunk(chunk_id: str, n: int, parts: int):
    """Members = next n untagged queue rows in priority order, not already in a chunk."""
    existing = run("chunk_exists", f"SELECT count(*) FROM {VF}.st_chunk_members "
                   "WHERE chunk_id = ?", [chunk_id])[0][0]
    if existing:
        return existing
    tier = next_tier()
    run(f"{chunk_id}_members", f"""
        INSERT INTO {VF}.st_chunk_members
        SELECT ?, sentence_id, CAST(pmod(rn - 1, {parts}) AS INT), current_timestamp()
        FROM (
          SELECT q.sentence_id, row_number() OVER (ORDER BY q.ord) AS rn
          FROM {VF}.st_queue q
          WHERE NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = q.sentence_id)
            AND NOT EXISTS (SELECT 1 FROM {VF}.st_chunk_members m WHERE m.sentence_id = q.sentence_id)
            AND q.priority = {tier}
          ORDER BY q.ord LIMIT {n})""", [chunk_id], fetch=False)
    return run("chunk_count", f"SELECT count(*) FROM {VF}.st_chunk_members "
               "WHERE chunk_id = ?", [chunk_id])[0][0]


def ai_query_part(prompt: str, chunk_id: str, attempt: int, part, ids_filter: str):
    """One INSERT ... ai_query statement. part=None covers all parts."""
    part_sql = "" if part is None else f"AND m.part = {int(part)}"
    label = f"{chunk_id}_a{attempt}" + ("" if part is None else f"_p{part}")
    t0 = time.time()
    run(label, f"""
        INSERT INTO {VF}.sentence_tags_raw
        SELECT m.sentence_id, m.chunk_id, {attempt}, m.part,
               ai_query('{MODEL}', concat(?, q.example_sentence),
                        modelParameters => named_struct('max_tokens', 300, 'temperature', 0.0),
                        failOnError => false),
               current_timestamp()
        FROM {VF}.st_chunk_members m JOIN {VF}.st_queue q USING (sentence_id)
        WHERE m.chunk_id = ? {part_sql}
          AND NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = m.sentence_id)
          {ids_filter}""", [prompt, chunk_id], fetch=False)
    return time.time() - t0


def read_raw(chunk_id: str, attempt: int):
    rows = run(f"{chunk_id}_read_a{attempt}", f"""
        SELECT r.sentence_id, r.resp.result, r.resp.errorMessage
        FROM {VF}.sentence_tags_raw r
        WHERE r.chunk_id = ? AND r.attempt = {attempt}
          AND NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t WHERE t.sentence_id = r.sentence_id)
    """, [chunk_id])
    return {sid: (res, err) for sid, res, err in rows}


def write_tags(chunk_id: str, rows: list[dict]):
    for i in range(0, len(rows), WRITE_BATCH):
        payload = json.dumps(rows[i: i + WRITE_BATCH], ensure_ascii=False)
        run(f"{chunk_id}_write", f"""
            INSERT INTO {VF}.sentence_tags
            (sentence_id, is_claim, services, strength, suggested_name, prompt_version,
             chunk_id, failed, fail_reason, tagged_at, unlabelled_claim)
            SELECT sentence_id, is_claim, services, strength, suggested_name, prompt_version,
                   chunk_id, failed, fail_reason, current_timestamp(), unlabelled_claim
            FROM (SELECT inline(from_json(?, 'array<struct<sentence_id:string,
                  is_claim:boolean,services:array<string>,strength:string,
                  suggested_name:string,prompt_version:string,chunk_id:string,
                  failed:boolean,fail_reason:string,unlabelled_claim:boolean>>')))""",
                [payload], fetch=False)


def to_row(sid, chunk_id, o, fail):
    ok = fail is None
    svc = o.get("services") if ok else None
    return {"sentence_id": sid, "chunk_id": chunk_id, "prompt_version": PROMPT_VERSION,
            "is_claim": o.get("is_claim") if ok else None, "services": svc,
            "strength": o.get("strength") if ok else None,
            "suggested_name": (o.get("suggested_name") if ok and "other_clinical" in svc
                               and isinstance(o.get("suggested_name"), str) else None),
            "unlabelled_claim": bool(ok and o.get("_unlabelled")),
            "failed": not ok, "fail_reason": fail}


def run_chunk(prompt: str, chunk_id: str, n: int, mode: str, retry: bool = True):
    parts = 4 if mode == "conc4" else 1
    members = create_chunk(chunk_id, n, parts)
    t0 = time.time()
    # No self-read of sentence_tags_raw inside the INSERT (concurrent appends would conflict);
    # resumability: skip parts whose attempt-1 rows already exist (each INSERT is atomic).
    # A part counts as done only if it has error-free raw rows for all its members; otherwise
    # (e.g. after a credit stop) its raw rows are deleted and the part is queried again.
    stat = run("raw_parts", f"""
        SELECT m.part, count(*) AS n_mem,
               count(r.sentence_id) AS n_raw, count(r.resp.errorMessage) AS n_err
        FROM {VF}.st_chunk_members m
        LEFT JOIN {VF}.sentence_tags_raw r
          ON r.sentence_id = m.sentence_id AND r.chunk_id = m.chunk_id AND r.attempt = 1
        WHERE m.chunk_id = ? GROUP BY m.part""", [chunk_id])
    todo = []
    for p, n_mem, n_raw, n_err in stat:
        if n_raw and n_raw == n_mem and n_err == 0:
            continue
        if n_raw:
            run("raw_part_reset", f"DELETE FROM {VF}.sentence_tags_raw WHERE chunk_id = ? "
                f"AND attempt = 1 AND part = {int(p)}", [chunk_id], fetch=False)
        todo.append(p)
    if parts == 1:
        q_secs = ai_query_part(prompt, chunk_id, 1, None, "") if todo else 0.0
    else:
        with cf.ThreadPoolExecutor(parts) as ex:
            list(ex.map(lambda p: ai_query_part(prompt, chunk_id, 1, p, ""), todo))
        q_secs = time.time() - t0

    raw1 = read_raw(chunk_id, 1)
    credit_check(chunk_id, [e for _, e in raw1.values()])  # before any row is written
    first = {sid: validate(res, err) for sid, (res, err) in raw1.items()}
    failed1 = [sid for sid, (_, f, _) in first.items() if f]
    reasons1 = Counter(f for _, f, _ in first.values() if f)

    retry_secs, reasons2, final = 0.0, Counter(), dict(first)
    if failed1 and retry:
        ids = ", ".join(f"'{s}'" for s in failed1)
        retry_secs = ai_query_part(prompt, chunk_id, 2, None, f"AND m.sentence_id IN ({ids})")
        raw2 = read_raw(chunk_id, 2)
        for sid in failed1:
            if sid in raw2:
                final[sid] = validate(*raw2[sid])
        reasons2 = Counter(final[s][1] for s in failed1 if final[s][1])
    rows = [to_row(sid, chunk_id, o, f) for sid, (o, f, _) in final.items()]
    write_tags(chunk_id, rows)
    total = time.time() - t0
    n_rows = len(rows)
    stats = {
        "chunk_id": chunk_id, "mode": mode, "members": members, "rows_written": n_rows,
        "ai_query_seconds": round(q_secs, 1),
        "sentences_per_s": round(len(raw1) / q_secs, 2) if q_secs else None,
        "retry_rows": len(failed1), "retry_seconds": round(retry_secs, 1),
        "fail_first": dict(reasons1), "fail_after_retry": dict(reasons2),
        "failed_rows": sum(r["failed"] for r in rows),
        "over_length_names": sum(1 for o, f, ol in final.values() if ol and f is None),
        "chunk_total_seconds": round(total, 1),
    }
    log("chunks", stats)
    return stats


def step2():
    ensure_tables()
    prompt = load_prompt()
    a = run_chunk(prompt, "tp_single", 2000, "single")
    b = run_chunk(prompt, "tp_conc4", 2000, "conc4")
    rem = remaining_count()
    for s in (a, b):
        rate = s["rows_written"] / s["ai_query_seconds"]
        log("step2", {"chunk_id": s["chunk_id"], "rate": round(rate, 2),
                      "remaining": rem, "projected_hours": round(rem / rate / 3600, 2)})


def step3(mode: str, max_chunks, until_tier=None):
    ensure_tables()
    prompt = load_prompt()
    done = run("chunk_ids", f"SELECT DISTINCT chunk_id FROM {VF}.st_chunk_members "
               "WHERE chunk_id LIKE 'c%'")
    nums = sorted(int(c[0][1:]) for c in done)
    # finish any half-done chunk first
    for k in nums:
        cid = f"c{k:03d}"
        left = run("chunk_left", f"""
            SELECT count(*) FROM {VF}.st_chunk_members m WHERE m.chunk_id = ?
              AND NOT EXISTS (SELECT 1 FROM {VF}.sentence_tags t
                              WHERE t.sentence_id = m.sentence_id)""", [cid])[0][0]
        if left:
            run_chunk(prompt, cid, CHUNK, mode, retry=False)
    k = (nums[-1] + 1) if nums else 1
    ran = 0
    while (max_chunks is None or ran < max_chunks):
        tier = next_tier()
        if tier is None or (until_tier is not None and tier > until_tier):
            break
        t0 = time.time()
        s = run_chunk(prompt, f"c{k:03d}", CHUNK, mode, retry=False)
        rem = remaining_count()
        rate = s["rows_written"] / (time.time() - t0)
        log("progress", {"chunk_id": s["chunk_id"], "tier": tier, "remaining": rem,
                         "end_to_end_rate": round(rate, 2),
                         "projected_hours_left": round(rem / rate / 3600, 2)})
        k += 1
        ran += 1


def final_retry():
    """All failed pa_single_v1 rows rerun once in ONE statement; replace their rows."""
    prompt = load_prompt()
    n = run("final_members", f"SELECT count(*) FROM {VF}.st_chunk_members "
            "WHERE chunk_id = 'final_retry'")[0][0]
    if not n:
        run("final_members_insert", f"""
            INSERT INTO {VF}.st_chunk_members
            SELECT 'final_retry', sentence_id, 0, current_timestamp()
            FROM {VF}.sentence_tags WHERE failed AND prompt_version = '{PROMPT_SINGLE_VERSION}'
        """, fetch=False)
    have, n_err = run("final_raw", f"SELECT count(*), count(resp.errorMessage) FROM "
                      f"{VF}.sentence_tags_raw WHERE chunk_id = 'final_retry'")[0]
    if have and n_err:  # e.g. an earlier credit stop: query again
        run("final_raw_reset", f"DELETE FROM {VF}.sentence_tags_raw "
            "WHERE chunk_id = 'final_retry'", fetch=False)
        have = 0
    t0 = time.time()
    if not have:
        run("final_retry_ai_query", f"""
            INSERT INTO {VF}.sentence_tags_raw
            SELECT m.sentence_id, 'final_retry', 2, 0,
                   ai_query('{MODEL}', concat(?, q.example_sentence),
                            modelParameters => named_struct('max_tokens', 300, 'temperature', 0.0),
                            failOnError => false),
                   current_timestamp()
            FROM {VF}.st_chunk_members m JOIN {VF}.st_queue q USING (sentence_id)
            WHERE m.chunk_id = 'final_retry'""", [prompt], fetch=False)
    secs = time.time() - t0
    raw = run("final_read", f"""SELECT sentence_id, resp.result, resp.errorMessage
        FROM {VF}.sentence_tags_raw WHERE chunk_id = 'final_retry'""")
    credit_check("final_retry", [e for _, _, e in raw])  # before any row is written
    res = {sid: validate(r, e) for sid, r, e in raw}
    # only replace rows that are still failed (idempotent if rerun)
    still = {sid for (sid,) in run("final_still", f"""SELECT t.sentence_id FROM {VF}.sentence_tags t
        JOIN {VF}.st_chunk_members m ON m.sentence_id = t.sentence_id AND m.chunk_id = 'final_retry'
        WHERE t.failed AND t.chunk_id != 'final_retry'""")}
    rows = [to_row(sid, "final_retry", o, f) for sid, (o, f, _) in res.items() if sid in still]
    if rows:
        run("final_delete_failed", f"""DELETE FROM {VF}.sentence_tags WHERE failed
            AND chunk_id != 'final_retry' AND sentence_id IN
            (SELECT sentence_id FROM {VF}.st_chunk_members WHERE chunk_id = 'final_retry')""",
            fetch=False)
        write_tags("final_retry", rows)
    log("chunks", {"chunk_id": "final_retry", "rows": len(res), "ai_query_seconds": round(secs, 1),
                   "replaced": len(rows), "still_failed": sum(r["failed"] for r in rows),
                   "fail_reasons": dict(Counter(f for _, f, _ in res.values() if f))})


def comment():
    tc = ("Service tags for every sentence in workspace.vf.distinct_sentences (key sentence_id). "
          "LLM rows: prompt_version pa_single_v1 (exact text in workspace.vf.pa_prompt), model "
          "databricks-meta-llama-3-3-70b-instruct, temperature 0, one sentence per ai_query "
          "call; raw responses in workspace.vf.sentence_tags_raw. Rule rows: prompt_version "
          "rule_dental_only = sentences that appear only in facilities typed dental in "
          "workspace.vf.facility_type; services = [dental], is_claim/strength NULL (not judged). "
          "unlabelled_claim = true marks is_claim true with no label (stored as other_clinical, "
          "not a failure). From chunk c007 ai_query uses max_tokens 300. "
          "failed = true when the response failed validation on the first call and on one retry "
          "(per chunk for tp_*, one final statement chunk_id final_retry for the rest). "
          "Rows are appended per chunk; failed rows are replaced by the final_retry pass. Resume with: python scripts/tag_sentences.py resume (skips sentence_ids "
          "already present, finishes half-done chunks from workspace.vf.st_chunk_members).")
    cols = {
        "sentence_id": "Key; joins to workspace.vf.distinct_sentences.sentence_id.",
        "is_claim": "Model: does the sentence assert this facility offers a service. NULL for "
                    "rule rows and failed rows.",
        "services": "Model labels from the 49-label list in pa_single_v1 ([] when is_claim false). "
                    "Rule rows: [dental]. NULL when failed.",
        "strength": "Model: explicit | stated | weak | na. NULL for rule rows and failed rows.",
        "suggested_name": "Model's short name when services contains other_clinical (asked for "
                          "<= 4 words, not enforced). NULL otherwise.",
        "prompt_version": "pa_single_v1 (LLM) or rule_dental_only (rule).",
        "chunk_id": "Run chunk: rule_dental_only, tp_single, tp_conc4 (throughput test), c001... (step 3, one tier per chunk), final_retry.",
        "failed": "true if the response failed validation on the first call and the one retry "
                  "(final_retry pass).",
        "fail_reason": "Validation failure of the final attempt (unparseable, unknown_label, "
                       "claim_without_label, ...). NULL when not failed.",
        "tagged_at": "Insert timestamp.",
        "unlabelled_claim": "true when the model said is_claim true but returned no label; stored "
                            "as services [other_clinical], strength as returned, failed false "
                            "(user rule, applied from chunk c007 and converted in place for "
                            "earlier rows). false for all other rows.",
    }
    run("table_comment", f"COMMENT ON TABLE {VF}.sentence_tags IS ?", [tc], fetch=False)
    for c, txt in cols.items():
        run(f"col_{c}", f"ALTER TABLE {VF}.sentence_tags ALTER COLUMN {c} COMMENT ?", [txt],
            fetch=False)


def credits_stop(err: Exception):
    try:
        done = run("credit_done", f"SELECT count(*) FROM {VF}.sentence_tags "
                   f"WHERE prompt_version = '{PROMPT_SINGLE_VERSION}'")[0][0]
        left = remaining_count()
    except Exception as e:  # noqa: BLE001
        done = left = f"unknown ({type(e).__name__})"
    msg = (f"CREDITS EXHAUSTED {now()}\nerror: {err}\nLLM rows done: {done}\n"
           f"sentences left: {left}\nNothing was written for the affected chunk. "
           "Resume after top-up: python scripts/tag_sentences.py resume --mode conc4\n")
    print(msg, flush=True)
    (LOGDIR / "CREDITS_EXHAUSTED.txt").write_text(msg)
    sys.exit(0)


def main():
    try:
        _main()
    except CreditsExhausted as e:
        credits_stop(e)


def _main():
    cmd = sys.argv[1]
    mode = "conc4"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    max_chunks = None
    if "--chunks" in sys.argv:
        max_chunks = int(sys.argv[sys.argv.index("--chunks") + 1])
    global PROMPT_VERSION
    if "--prompt" in sys.argv:
        PROMPT_VERSION = sys.argv[sys.argv.index("--prompt") + 1]
    if cmd == "step1":
        step1()
    elif cmd == "step2":
        step2()
    elif cmd == "step3":
        until = int(sys.argv[sys.argv.index("--until-tier") + 1]) if "--until-tier" in sys.argv else None
        step3(mode, max_chunks, until)
    elif cmd == "resume":
        step3(mode, max_chunks)
        if next_tier() is None:
            final_retry()
            comment()
            log("progress", {"done": True, "remaining": remaining_count()})
    elif cmd == "final_retry":
        final_retry()
    elif cmd == "comment":
        comment()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

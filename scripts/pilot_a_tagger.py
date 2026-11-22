"""Pilot A: sentence service tagger on workspace.vf.distinct_sentences.

Usage:
  python scripts/pilot_a_tagger.py stage0   # build pa_sample (500), tag first 50 at 25/call
  python scripts/pilot_a_tagger.py stage1   # tag remaining 450 at 25/call, then 250 at 50/call

Writes: workspace.vf.pa_sample, pa_prompt, pa_results, pa_statements.
Local logs: reports/pilot_a/ (raw responses, statement timings).
"""

import datetime as dt
import json
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
PROMPT_VERSION = "pa_v1"
SEED = "pa_seed_1"
VF = "workspace.vf"
LOGDIR = Path(__file__).resolve().parent.parent / "reports" / "pilot_a"

SERVICES = [
    "dialysis", "caesarean_section", "normal_delivery", "high_risk_obstetrics",
    "nicu", "picu", "icu_critical_care", "ventilator_support",
    "cardiac_surgery", "interventional_cardiology", "stroke_care",
    "mri", "ct_scan", "xray", "ultrasound", "mammography", "nuclear_imaging",
    "burn_care", "trauma_emergency", "ambulance",
    "chemotherapy", "radiotherapy", "cancer_surgery",
    "orthopedic_surgery", "joint_replacement", "neurosurgery", "spine_surgery",
    "general_surgery", "gi_endoscopy", "pulmonology_respiratory", "transplant",
    "blood_bank", "laboratory_pathology", "dental", "eye_surgery",
    "physiotherapy_rehab", "mental_health", "outpatient_opd",
    "infertility_ivf", "dermatology", "ent", "ophthalmology_medical",
    "pediatrics", "obstetrics_maternity", "cosmetic_aesthetic",
    "prosthetics_orthotics", "nephrology_renal", "gastroenterology",
    "other_clinical",
]
ALLOWED = set(SERVICES)
STRENGTHS = {"explicit", "stated", "weak", "na"}

# Copied from scripts/classify_eval.py PROMPT with exactly two changes:
#  (1) the education/training paragraph now says is_claim false;
#  (2) other_clinical objects must carry "suggested_name" (<= 4 words).
PROMPT = textwrap.dedent(f"""\
    You label snippets scraped from Indian hospital websites.

    For EACH numbered snippet decide which clinical service the snippet is
    EVIDENCE THAT THE FACILITY OFFERS.

    Allowed labels: {", ".join(SERVICES)}

    Set "is_claim": false when the snippet does not assert that this facility
    offers a service. Research findings, statistics, doctor biographies, fees,
    founding dates, buildings, accommodation and awards all get is_claim false,
    even when they mention clinical words. When is_claim is false, "services"
    MUST be [] and "strength" MUST be "na".

    Use "other_clinical" when it IS a service claim but no allowed label fits.
    Whenever "services" contains "other_clinical", the object MUST also contain
    "suggested_name": a short service name of at most 4 words. Other objects
    may omit "suggested_name" or set it to null.

    Note: lung function tests, spirometry, bronchoscopy, ventilation and sleep
    studies are all "pulmonology_respiratory". A general emergency department or
    casualty ward is "trauma_emergency", NOT any obstetric label.

    Also return "strength":
      "explicit" - names the service with concrete detail (beds, machines, units)
      "stated"   - names the service plainly
      "weak"     - only implies it

    A snippet may evidence SEVERAL services - return all of them.
    "imaging including USG, CT and MRI" -> ["ultrasound","ct_scan","mri"].

    Education, training, fellowship and degree programmes get is_claim false
    (services [] and strength "na"), even in a clinical subject.

    Cosmetic and aesthetic procedures are "cosmetic_aesthetic", never cancer_surgery.
    Breast implants, cupping, body contouring and hair removal are cosmetic_aesthetic.

    Orthodontics, aligners, braces and anything about teeth is "dental",
    NEVER orthopedic_surgery. Orthodontic and orthopaedic are different words.

    Use ONLY labels from the allowed list. Never invent a label.

    Strength calibration:
    - A bare list of department names is "weak" for each department, not "explicit".
    - "Has N specialists on staff" is "weak" - staffing is not a service claim detail.
    - "explicit" needs concrete capacity: beds, machines, units, theatres, counts.

    Rules:
    - Return EXACTLY one object per snippet, same order, nothing omitted.
    - Echo the first three words of the snippet in "echo" so alignment is checkable.
    - Reply with ONLY a JSON array of
      {{"i":<index>,"echo":"<first three words>","is_claim":<true|false>,
       "services":[<labels>],"strength":"explicit"|"stated"|"weak"|"na",
       "suggested_name":"<only when other_clinical>"}}
    - When is_claim is true, "services" must contain at least one allowed label.

    Snippets:
    """)

CALL_SQL = ("SELECT ai_query(?, ?, modelParameters => named_struct('temperature', 0.0)) AS out")


def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


class Runner:
    def __init__(self, stage: str):
        self.conn = sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token())
        self.stage = stage
        self.stmts: list[dict] = []
        LOGDIR.mkdir(parents=True, exist_ok=True)
        self.rawlog = open(LOGDIR / f"raw_{stage}.jsonl", "a")
        self.stmtlog = open(LOGDIR / f"statements_{stage}.jsonl", "a")

    def run(self, label: str, query: str, params=None, fetch=True):
        start, t0 = now(), time.time()
        with self.conn.cursor() as cur:
            cur.execute(query, params) if params is not None else cur.execute(query)
            rows = cur.fetchall() if fetch else None
        rec = {"stage": self.stage, "label": label, "start": start, "end": now(),
               "seconds": round(time.time() - t0, 3)}
        self.stmts.append(rec)
        self.stmtlog.write(json.dumps(rec) + "\n")
        self.stmtlog.flush()
        return rows


def first_word(s) -> str:
    m = re.search(r"[A-Za-z0-9]+", str(s or ""))
    return m.group(0).lower() if m else ""


def parse_batch(raw: str, n: int):
    """Return (list, None) if accepted else (None, reason)."""
    try:
        out = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
    except Exception:  # noqa: BLE001
        return None, "unparseable"
    if not isinstance(out, list) or not all(isinstance(o, dict) for o in out):
        return None, "unparseable"
    if len(out) != n:
        return None, f"count {len(out)}!={n}"
    if [o.get("i") for o in out] != list(range(n)):
        return None, "indices_out_of_order"
    return out, None


def validate_row(o: dict):
    claim, svc, st = o.get("is_claim"), o.get("services"), o.get("strength")
    if not isinstance(claim, bool):
        return "is_claim_not_bool"
    if not isinstance(svc, list):
        return "services_not_list"
    if any(s not in ALLOWED for s in svc):
        return "unknown_label"
    if st not in STRENGTHS:
        return "bad_strength"
    if claim is False and (svc or st != "na"):
        return "inconsistent_false"
    if claim is True and not svc:
        return "claim_without_label"
    return None


def call(r: Runner, sents: list[dict], label: str):
    numbered = json.dumps([f"{i}. {s['example_sentence']}" for i, s in enumerate(sents)],
                          ensure_ascii=False)
    raw = r.run(label, CALL_SQL, [MODEL, PROMPT + numbered])[0][0]
    r.rawlog.write(json.dumps({"label": label, "ids": [s["sentence_id"] for s in sents],
                               "raw": raw}) + "\n")
    r.rawlog.flush()
    return raw


def tag(r: Runner, sents: list[dict], run_name: str, batch_size: int, retry_log: list):
    """Tag sentences in batches. Returns result rows and batch stats."""
    results, stats = [], {"batches": 0, "failed_first": 0, "failed_retry": 0}
    for b0 in range(0, len(sents), batch_size):
        batch = sents[b0: b0 + batch_size]
        bid = f"{run_name}_b{b0 // batch_size:03d}"
        stats["batches"] += 1
        out, why = parse_batch(call(r, batch, bid), len(batch))
        mode = "batch"
        if out is None:
            stats["failed_first"] += 1
            retry_log.append({"batch": bid, "attempt": 1, "reason": why})
            out, why = parse_batch(call(r, batch, bid + "_retry"), len(batch))
            mode = "retry"
            if out is None:
                stats["failed_retry"] += 1
                retry_log.append({"batch": bid, "attempt": 2, "reason": why,
                                  "action": "single"})
                out, mode = [], "single"
                for j, s in enumerate(batch):
                    o, why1 = parse_batch(call(r, [s], f"{bid}_s{j:02d}"), 1)
                    out.append(o[0] if o else {"_fail": f"single_{why1}"})
        for s, o in zip(batch, out):
            fail = o.get("_fail") or validate_row(o)
            echo = o.get("echo")
            results.append({
                "sentence_id": s["sentence_id"], "run": run_name, "batch_id": bid,
                "batch_size": batch_size, "mode": mode,
                "is_claim": o.get("is_claim") if not fail else None,
                "services": o.get("services") if not fail else None,
                "strength": o.get("strength") if not fail else None,
                "suggested_name": o.get("suggested_name"),
                "echo": None if echo is None else str(echo),
                "echo_first_word_match": first_word(echo) == first_word(s["example_sentence"]),
                "valid": fail is None, "fail_reason": fail,
                "prompt_version": PROMPT_VERSION,
            })
    return results, stats


def ensure_tables(r: Runner):
    r.run("create_pa_prompt",
          f"CREATE TABLE IF NOT EXISTS {VF}.pa_prompt (prompt_version STRING, model STRING, "
          "temperature DOUBLE, prompt STRING, created_at TIMESTAMP)", fetch=False)
    r.run("upsert_pa_prompt",
          f"MERGE INTO {VF}.pa_prompt t USING (SELECT ? v, ? m, 0.0 tmp, ? p) s "
          "ON t.prompt_version = s.v WHEN NOT MATCHED THEN INSERT "
          "(prompt_version, model, temperature, prompt, created_at) "
          "VALUES (s.v, s.m, s.tmp, s.p, current_timestamp())",
          [PROMPT_VERSION, MODEL, PROMPT], fetch=False)
    r.run("create_pa_results",
          f"CREATE TABLE IF NOT EXISTS {VF}.pa_results (sentence_id STRING, run STRING, "
          "batch_id STRING, batch_size INT, mode STRING, is_claim BOOLEAN, "
          "services ARRAY<STRING>, strength STRING, suggested_name STRING, echo STRING, "
          "echo_first_word_match BOOLEAN, valid BOOLEAN, fail_reason STRING, "
          "prompt_version STRING, created_at TIMESTAMP)", fetch=False)
    r.run("create_pa_statements",
          f"CREATE TABLE IF NOT EXISTS {VF}.pa_statements (stage STRING, label STRING, "
          "start_ts STRING, end_ts STRING, seconds DOUBLE)", fetch=False)


def write_results(r: Runner, rows: list[dict]):
    payload = json.dumps(rows, ensure_ascii=False)
    r.run("insert_pa_results", f"""
        INSERT INTO {VF}.pa_results
        SELECT sentence_id, run, batch_id, batch_size, mode, is_claim, services, strength,
               suggested_name, echo, echo_first_word_match, valid, fail_reason,
               prompt_version, current_timestamp()
        FROM (SELECT inline(from_json(?, 'array<struct<sentence_id:string,run:string,
              batch_id:string,batch_size:int,mode:string,is_claim:boolean,
              services:array<string>,strength:string,suggested_name:string,echo:string,
              echo_first_word_match:boolean,valid:boolean,fail_reason:string,
              prompt_version:string>>')))""", [payload], fetch=False)


def write_statements(r: Runner):
    stmts = list(r.stmts)
    r.run("insert_pa_statements", f"""
        INSERT INTO {VF}.pa_statements
        SELECT stage, label, start, `end`, seconds FROM (SELECT inline(from_json(?,
          'array<struct<stage:string,label:string,start:string,end:string,seconds:double>>')))""",
          [json.dumps(stmts)], fetch=False)


def load_sample(r: Runner):
    rows = r.run("read_pa_sample",
                 f"SELECT ord, sentence_id, example_sentence FROM {VF}.pa_sample ORDER BY ord")
    return [{"ord": x[0], "sentence_id": x[1], "example_sentence": x[2]} for x in rows]


def summarize(name, rows, stats, seconds):
    from collections import Counter
    v = sum(x["valid"] for x in rows)
    fr = Counter(x["fail_reason"] for x in rows if not x["valid"])
    em = sum(not x["echo_first_word_match"] for x in rows)
    print(f"[{name}] rows={len(rows)} valid={v} failed={len(rows) - v} reasons={dict(fr)} "
          f"echo_mismatch={em} batches={stats['batches']} failed_first={stats['failed_first']} "
          f"failed_retry={stats['failed_retry']} call_seconds={seconds:.1f}")


def main():
    stage = sys.argv[1]
    r = Runner(stage)
    retry_log: list = []
    ensure_tables(r)
    if stage == "stage0":
        r.run("create_pa_sample", f"""
            CREATE TABLE IF NOT EXISTS {VF}.pa_sample AS
            SELECT row_number() OVER (ORDER BY md5(concat('{SEED}', sentence_id))) - 1 AS ord,
                   sentence_id, example_sentence
            FROM {VF}.distinct_sentences
            ORDER BY md5(concat('{SEED}', sentence_id)) LIMIT 500""", fetch=False)
        sample = load_sample(r)
        plan = [("s0_bs25", sample[:50], 25)]
    elif stage == "stage1":
        sample = load_sample(r)
        plan = [("s1_bs25", sample[50:500], 25), ("s1_bs50", sample[:250], 50)]
    else:
        sys.exit("stage0 | stage1")

    for name, sents, bs in plan:
        n0 = len(r.stmts)
        rows, stats = tag(r, sents, name, bs, retry_log)
        secs = sum(s["seconds"] for s in r.stmts[n0:] if s["label"].startswith(name))
        write_results(r, rows)
        summarize(name, rows, stats, secs)
    with open(LOGDIR / f"retry_{stage}.json", "w") as f:
        json.dump(retry_log, f, indent=1)
    write_statements(r)
    print("retry_log:", retry_log)


if __name__ == "__main__":
    main()

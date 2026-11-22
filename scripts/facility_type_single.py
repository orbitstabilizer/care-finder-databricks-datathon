"""Facility type, one facility per ai_query call (prompt version ft_single_v1).

Usage (py13 env):
    python scripts/facility_type_single.py pilot    # the 200 old pilot facilities (minus shifted)
    python scripts/facility_type_single.py review   # print 30 random pilot rows for manual review
    python scripts/facility_type_single.py probe    # 100 random non-pilot facilities, timed (gate 3b)
    python scripts/facility_type_single.py full     # all remaining non-shifted facilities,
                                                    # then build workspace.vf.facility_type
    python scripts/facility_type_single.py stats    # summary counts of workspace.vf.facility_type

Design:
  - input: workspace.vf.facilities_clean, is_shifted = false; name, description[:400],
    specialties (already distinct).
  - one SQL statement per (phase, attempt): ai_query over one row per facility, temperature 0,
    failOnError => false. unique_id is a column of the row, never sent through the model.
    Raw output -> workspace.vf.facility_type_single_raw.
  - Python validates each response (JSON object parses, every field in its allowed set).
    Failed rows get exactly one retry (one more statement over just those rows). Rows still
    failing -> facility_type 'unknown', failed = true.
  - Per-row outcome -> workspace.vf.facility_type_single_status; the output table re-parses
    exactly the accepted raw response in SQL.
  - Prompt text is stored in workspace.vf.facility_type_single_prompts.
  Old tables (facility_type_raw/_batches/_input/_accepted/_pilot) are read only (pilot ids).
"""

import json
import subprocess
import sys
import time

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
S = "workspace.vf"
SRC = f"{S}.facilities_clean"
PROMPT_VERSION = "ft_single_v1"
PROBE_N = 100

TYPES = [
    "multispecialty_hospital", "general_hospital_or_nursing_home",
    "medical_college_teaching_hospital", "government_health_centre",
    "maternity_women_children", "pediatric", "eye", "dental", "ent_hearing_speech",
    "skin_hair_cosmetic", "ivf_fertility", "kidney_urology", "cardiac", "cancer",
    "orthopedic_spine", "neuro", "gastro_liver", "diagnostic_imaging_lab",
    "physiotherapy_rehab", "mental_health_deaddiction", "ayush_alternative",
    "home_care_or_ambulance", "general_clinic_polyclinic", "other_single_specialty",
    "not_a_care_facility", "unknown",
]
OWNERSHIP = ["public", "private", "charitable_trust", "unknown"]
CONFIDENCE = ["high", "medium", "low"]

# ft_v3 text (as stored in facility_type_raw) with only these changes: one facility instead
# of a numbered list, no "n"/"echo" fields, a single JSON object instead of an array.
# The facility JSON is appended directly after "Facility:\n".
PROMPT = """You classify records of Indian healthcare facilities by FACILITY TYPE.

The facility below is given as JSON with "name",
"description" (first 400 characters) and "specialties" (a list of tags).

How to weigh the evidence:
- The NAME and the DESCRIPTION lead. Decide from them first.
- "specialties" is over-assigned and unreliable: generic tags such as
  internalMedicine and familyMedicine appear even on dental clinics and hearing
  clinics. Use specialties ONLY to break a tie when the name and description
  do not decide.

facility_type - exactly one of:
  multispecialty_hospital - hospital with many specialties ("multi speciality", "super speciality")
  general_hospital_or_nursing_home - general hospital or nursing home without one specialty focus
  medical_college_teaching_hospital - medical college, institute of medical sciences, teaching hospital
  government_health_centre - PHC, CHC, sub-centre, district/taluk/civil/government hospital, ESI dispensary
  maternity_women_children - maternity home, women's hospital, mother and child, obstetrics/gynaecology
  pediatric - children's hospital or child clinic
  eye
  dental
  ent_hearing_speech - ENT, hearing aids, audiology, speech therapy
  skin_hair_cosmetic - dermatology, hair, cosmetic or aesthetic clinic
  ivf_fertility
  kidney_urology - nephrology, dialysis centre, urology
  cardiac
  cancer
  orthopedic_spine
  neuro - neurology, neurosurgery
  gastro_liver
  diagnostic_imaging_lab - diagnostic centre, scan centre, imaging, pathology lab
  physiotherapy_rehab
  mental_health_deaddiction
  ayush_alternative - ayurveda, homeopathy, unani, siddha, naturopathy, yoga
  home_care_or_ambulance
  general_clinic_polyclinic - doctor's clinic or polyclinic without one specialty focus
  other_single_specialty - a single specialty not listed above
  not_a_care_facility - pharmacy, supplier, company, NGO office, school, veterinary, other non-provider
  unknown - not enough information to decide

is_single_specialty - true if the facility focuses on one specialty or service line,
  false for hospitals, colleges, government centres and general clinics.
ownership - public (government, municipal, ESI, railway, armed forces),
  private, charitable_trust (trust, society, mission, NGO, religious charity),
  or unknown when nothing indicates it.
confidence - high (stated plainly), medium (inferred), low (guess or conflicting evidence).
reason - at most 12 words, quoting the words in the name or description that decided it.

Output rules:
- Reply with ONLY a single JSON object for this facility, nothing added.
- Use ONLY the allowed values above. Never invent a value.
- The object: {"facility_type":"<value>",
  "is_single_specialty":true|false,"ownership":"<value>","confidence":"<value>",
  "reason":"<at most 12 words>"}

Facility:
"""


# --------------------------------------------------------------------------- db
def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def run(stmt: str, params=None, fetch=False):
    with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token()) as c:
        with c.cursor() as cur:
            cur.execute(stmt, params or [])
            return cur.fetchall() if fetch else None


def q(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


# --------------------------------------------------------------------------- validation
def parse(raw):
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])


def validate(raw, err):
    if err:
        return False, f"endpoint_error: {str(err)[:150]}"
    if not raw:
        return False, "empty_response"
    try:
        o = parse(raw)
    except Exception as e:  # noqa: BLE001
        return False, f"unparseable: {type(e).__name__}"
    if not isinstance(o, dict):
        return False, "not an object"
    if o.get("facility_type") not in TYPES:
        return False, f"facility_type {o.get('facility_type')!r}"
    if not isinstance(o.get("is_single_specialty"), bool):
        return False, f"is_single_specialty {o.get('is_single_specialty')!r}"
    if o.get("ownership") not in OWNERSHIP:
        return False, f"ownership {o.get('ownership')!r}"
    if o.get("confidence") not in CONFIDENCE:
        return False, f"confidence {o.get('confidence')!r}"
    if not isinstance(o.get("reason"), str):
        return False, f"reason {o.get('reason')!r}"
    return True, ""


# --------------------------------------------------------------------------- setup
def setup():
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_single_prompts (
        prompt_version STRING, model STRING, prompt STRING, created_ts TIMESTAMP)""")
    run(f"DELETE FROM {S}.facility_type_single_prompts WHERE prompt_version = ?", [PROMPT_VERSION])
    run(f"INSERT INTO {S}.facility_type_single_prompts VALUES (?, ?, ?, current_timestamp())",
        [PROMPT_VERSION, MODEL, PROMPT])
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_single_raw (
        unique_id STRING, phase STRING, attempt INT, response STRING, error STRING,
        prompt_version STRING, ts TIMESTAMP)""")
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_single_runs (
        phase STRING, unique_id STRING)""")
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_single_status (
        unique_id STRING, phase STRING, accepted_attempt INT, failed BOOLEAN,
        problems STRING, prompt_version STRING)""")


def assign(phase: str):
    for t in ("facility_type_single_runs", "facility_type_single_status"):
        run(f"DELETE FROM {S}.{t} WHERE phase = ?", [phase])
    run(f"DELETE FROM {S}.facility_type_single_raw WHERE phase = ? AND prompt_version = ?",
        [phase, PROMPT_VERSION])
    if phase == "pilot":
        sel = f"""SELECT b.unique_id FROM {S}.facility_type_batches b
                  JOIN {SRC} c USING (unique_id)
                  WHERE b.phase = 'pilot' AND NOT c.is_shifted"""
    else:
        others = f"SELECT unique_id FROM {S}.facility_type_single_runs WHERE phase != '{phase}'"
        limit = f"ORDER BY md5(concat('probe', unique_id)) LIMIT {PROBE_N}" if phase == "probe" else ""
        sel = f"""SELECT unique_id FROM {SRC}
                  WHERE NOT is_shifted AND unique_id NOT IN ({others}) {limit}"""
    run(f"INSERT INTO {S}.facility_type_single_runs SELECT '{phase}', unique_id FROM ({sel})")
    return run(f"SELECT count(*) FROM {S}.facility_type_single_runs WHERE phase = ?",
               [phase], fetch=True)[0][0]


# --------------------------------------------------------------------------- calling
def call(phase: str, attempt: int, only_failed_of=None) -> float:
    """One SQL statement: ai_query over every facility of the phase (attempt 1) or over the
    given failed unique_ids (attempt 2). Returns wall-clock seconds."""
    where = ""
    if only_failed_of is not None:
        where = "AND c.unique_id IN (" + ",".join(q(u) for u in only_failed_of) + ")"
    stmt = f"""
    INSERT INTO {S}.facility_type_single_raw
    WITH inp AS (
      SELECT c.unique_id,
             concat(?, to_json(named_struct(
               'name', coalesce(trim(c.name), ''),
               'description', coalesce(substr(c.description, 1, 400), ''),
               'specialties', coalesce(c.specialties, array())))) AS prompt
      FROM {SRC} c JOIN {S}.facility_type_single_runs r
        ON r.unique_id = c.unique_id AND r.phase = ?
      WHERE NOT c.is_shifted {where}
    ), called AS (
      SELECT unique_id,
             ai_query('{MODEL}', prompt,
                      modelParameters => named_struct('temperature', 0.0, 'max_tokens', 400),
                      failOnError => false) AS r
      FROM inp
    )
    SELECT unique_id, ?, {attempt}, r.result, r.errorMessage, ?, current_timestamp()
    FROM called"""
    t = time.time()
    run(stmt, [PROMPT, phase, phase, PROMPT_VERSION])
    return round(time.time() - t, 1)


def check(phase: str, attempt: int):
    rows = run(f"""SELECT unique_id, response, error FROM {S}.facility_type_single_raw
                   WHERE phase = ? AND attempt = ? AND prompt_version = ?""",
               [phase, attempt, PROMPT_VERSION], fetch=True)
    ok, bad = [], {}
    for u, r, e in rows:
        good, prob = validate(r, e)
        (ok.append(u) if good else bad.__setitem__(u, prob))
    return ok, bad


def write_status(phase, ok1, bad1, ok2, bad2):
    vals = [f"({q(u)},'{phase}',1,false,'',{q(PROMPT_VERSION)})" for u in ok1]
    vals += [f"({q(u)},'{phase}',2,false,{q('a1: ' + bad1[u])},{q(PROMPT_VERSION)})" for u in ok2]
    vals += [f"({q(u)},'{phase}',NULL,true,{q('a1: ' + bad1[u] + ' | a2: ' + bad2.get(u, 'missing'))},"
             f"{q(PROMPT_VERSION)})" for u in bad1 if u not in ok2]
    for i in range(0, len(vals), 1000):
        run(f"INSERT INTO {S}.facility_type_single_status VALUES " + ",".join(vals[i:i + 1000]))


def run_phase(phase: str, retry=True):
    setup()
    n = assign(phase)
    out = {"phase": phase, "rows": n}
    out["a1_seconds"] = call(phase, 1)
    ok1, bad1 = check(phase, 1)
    out["a1_valid"], out["a1_failed"] = len(ok1), len(bad1)
    out["a1_missing"] = n - len(ok1) - len(bad1)
    out["a1_problems"] = bad1
    print(json.dumps({k: v for k, v in out.items() if k != "a1_problems"}), flush=True)
    ok2, bad2 = [], {}
    if retry and bad1:
        out["a2_seconds"] = call(phase, 2, list(bad1))
        ok2, bad2 = check(phase, 2)
        out["a2_valid"], out["a2_failed"] = len(ok2), len(bad2)
    write_status(phase, ok1, bad1, ok2, bad2)
    out["failed_after_retry"] = len([u for u in bad1 if u not in ok2])
    print(json.dumps(out, indent=1), flush=True)
    return out


# --------------------------------------------------------------------------- output
PARSED = f"""
    SELECT s.unique_id, s.phase, s.failed, s.accepted_attempt,
           from_json(regexp_extract(r.response, '(?s)(\\\\{{.*\\\\}})', 1),
             'struct<facility_type:string,is_single_specialty:boolean,ownership:string,
                     confidence:string,reason:string>') AS o, r.ts
    FROM {S}.facility_type_single_status s
    LEFT JOIN {S}.facility_type_single_raw r
      ON r.unique_id = s.unique_id AND r.phase = s.phase AND r.attempt = s.accepted_attempt
     AND r.prompt_version = s.prompt_version
    WHERE s.prompt_version = '{PROMPT_VERSION}'"""


def review(n=30):
    rows = run(f"""
    WITH p AS ({PARSED})
    SELECT p.unique_id, c.name, substr(c.description, 1, 400), p.o.facility_type,
           p.o.is_single_specialty, p.o.ownership, p.o.confidence, p.o.reason, p.failed
    FROM p JOIN {SRC} c USING (unique_id) WHERE p.phase = 'pilot'
    ORDER BY md5(concat('review', p.unique_id)) LIMIT {n}""", fetch=True)
    for i, r in enumerate(rows, 1):
        print(json.dumps({"i": i, "id": r[0], "name": r[1], "desc": r[2], "type": r[3],
                          "single": r[4], "own": r[5], "conf": r[6], "reason": r[7],
                          "failed": r[8]}, ensure_ascii=False))


def build_output():
    run(f"""
    CREATE OR REPLACE TABLE {S}.facility_type AS
    WITH p AS ({PARSED})
    SELECT c.unique_id, c.name,
           CASE WHEN p.failed THEN 'unknown' ELSE p.o.facility_type END AS facility_type,
           CASE WHEN p.failed THEN NULL ELSE p.o.is_single_specialty END AS is_single_specialty,
           CASE WHEN p.failed THEN 'unknown' ELSE p.o.ownership END AS ownership,
           CASE WHEN p.failed THEN 'low' ELSE p.o.confidence END AS confidence,
           CASE WHEN p.failed THEN NULL ELSE p.o.reason END AS reason,
           coalesce(p.failed, true) AS failed,
           '{PROMPT_VERSION}' AS prompt_version,
           p.ts AS run_ts
    FROM {SRC} c LEFT JOIN p USING (unique_id)
    WHERE NOT c.is_shifted""")
    comments = {
        "unique_id": "Facility key; joins to workspace.vf.facilities_clean.unique_id.",
        "name": "Facility name from facilities_clean (not model output).",
        "facility_type": "One of 26 labels from prompt ft_single_v1, decided from name + first 400 chars of description (specialties only as tiebreaker). 'unknown' when the model said so or the row failed validation.",
        "is_single_specialty": "Model output: true if the facility focuses on one specialty or service line. NULL when failed.",
        "ownership": "Model output: public, private, charitable_trust or unknown ('unknown' when failed).",
        "confidence": "Model self-reported confidence: high (stated plainly), medium (inferred), low (guess or conflicting). Set to low when failed.",
        "reason": "Model output, meant to be at most 12 words quoting the deciding words of name/description. Not enforced; can exceed 12 words. NULL when failed.",
        "failed": "true if both the first call and the one retry returned a response that did not parse or had a value outside the allowed sets.",
        "prompt_version": "Prompt version; exact text in workspace.vf.facility_type_single_prompts.",
        "run_ts": "Timestamp of the accepted ai_query response (NULL when failed).",
    }
    run(f"""COMMENT ON TABLE {S}.facility_type IS {q(
        "Facility type per non-shifted facility in workspace.vf.facilities_clean (one row per unique_id). "
        "Classified by ai_query (" + MODEL + ", temperature 0), one facility per call, prompt ft_single_v1; "
        "inputs: name, description truncated to 400 chars, distinct specialties. Labels are model claims, "
        "not verified facts: use confidence and failed. Raw responses: facility_type_single_raw; per-row "
        "validation: facility_type_single_status. Built by scripts/facility_type_single.py; report "
        "reports/facility_type_single.md.")}""")
    for col, txt in comments.items():
        run(f"ALTER TABLE {S}.facility_type ALTER COLUMN {col} COMMENT {q(txt)}")


def stats():
    for stmt in [
        f"SELECT count(*), count(DISTINCT unique_id), sum(cast(failed AS INT)) FROM {S}.facility_type",
        f"SELECT facility_type, count(*) n FROM {S}.facility_type GROUP BY 1 ORDER BY n DESC",
        f"SELECT confidence, count(*) n FROM {S}.facility_type GROUP BY 1 ORDER BY n DESC",
        f"SELECT ownership, count(*) n FROM {S}.facility_type GROUP BY 1 ORDER BY n DESC",
        f"SELECT is_single_specialty, count(*) n FROM {S}.facility_type GROUP BY 1 ORDER BY n DESC",
        f"SELECT count_if(size(split(trim(reason), '\\\\s+')) > 12) FROM {S}.facility_type",
        f"""SELECT name, facility_type, reason FROM {S}.facility_type WHERE confidence = 'low'
            AND NOT failed ORDER BY md5(concat('low', unique_id)) LIMIT 10""",
    ]:
        print("--", stmt.split("FROM")[0].strip()[:80])
        for r in run(stmt, fetch=True):
            print("  ", tuple(r))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    if cmd == "pilot":
        run_phase("pilot")
    elif cmd == "review":
        review()
    elif cmd == "probe":
        run_phase("probe")   # attempt-1 seconds/validity is the gate measurement; retry after
    elif cmd == "full":
        t0 = time.time()
        run_phase("full")
        build_output()
        print("full total seconds", round(time.time() - t0, 1))
        stats()
    elif cmd == "build":
        build_output()
    elif cmd == "stats":
        stats()

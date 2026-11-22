"""Classify every facility into one facility type with ai_query (batched).

Usage (py13 env):
    python scripts/facility_type.py pilot     # 200 random facilities -> workspace.vf.facility_type_pilot
    python scripts/facility_type.py full      # all facilities        -> workspace.vf.facility_type

Flow per phase:
  1. workspace.vf.facility_type_input   deduplicated input (one row per unique_id)
  2. workspace.vf.facility_type_batches (phase, batch_id, pos, unique_id), 20 per batch
  3. one SQL statement per attempt: ai_query over every pending batch -> appended to
     workspace.vf.facility_type_raw (prompt, raw response, error)
  4. Python validates each response (count, order, echo, allowed values); failures are
     retried, max 3 attempts per batch
  5. accepted (batch_id, attempt) pairs -> workspace.vf.facility_type_accepted; the
     output table is built in SQL by re-parsing exactly those raw responses.
"""

import json
import re
import subprocess
import sys
import textwrap
import time

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
SRC = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities"
S = "workspace.vf"
PROMPT_VERSION = "ft_v4"
# ft_v3: more echo examples; 285/600 item echoes wrong. ft_v1-v3 failed 30/30 calls each.
# ft_v4: each line carries key="<first three words of name>" (computed in SQL) and
#        the model must copy it into echo; the check is still per-item alignment.
# ft_v2: echo example added; still 259/600 item echoes wrong (176 two-word echoes)
# ft_v1: echo instruction without example; model echoed 2 words in 10/10 pilot batches
BATCH = 20
MAX_ATTEMPTS = 3
PILOT_N = 200

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
NONAME = "NONAME"

PROMPT = textwrap.dedent("""\
    You classify records of Indian healthcare facilities by FACILITY TYPE.

    Each numbered line below is one facility, given as JSON with "name",
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
    - Reply with ONLY a JSON array: exactly one object per facility, in the same order,
      nothing omitted, nothing added.
    - "n" is the facility's line number.
    - "echo" is the key="..." shown at the start of that facility's line (the first
      three words of its name). Copy it exactly, character for character.
    - Use ONLY the allowed values above. Never invent a value.
    - Each object: {"n":<number>,"echo":"<key of that line>","facility_type":"<value>",
      "is_single_specialty":true|false,"ownership":"<value>","confidence":"<value>",
      "reason":"<at most 12 words>"}

    Facilities:
    """)


# --------------------------------------------------------------------------- db
def token() -> str:
    raw = subprocess.run(["databricks", "auth", "token", "-p", PROFILE],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)["access_token"]


def run(stmt: str, params=None, fetch=False):
    # fresh connection per statement: OAuth tokens are short-lived and the full run is long
    with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token()) as c:
        with c.cursor() as cur:
            cur.execute(stmt, params or [])
            return cur.fetchall() if fetch else None


# --------------------------------------------------------------------------- validation
def _words(s) -> list[str]:
    """Whitespace tokens, lower-cased, curly quotes folded, leading/trailing punctuation
    stripped; tokens with no letter/digit (e.g. '&', '-') are not words."""
    s = str(s).lower().replace("\u2019", "'").replace("\u2018", "'")
    toks = [re.sub(r"^[\W_]+|[\W_]+$", "", t) for t in s.split()]
    return [t for t in toks if t]


def _norm_words(s) -> str:
    return " ".join(_words(s))


def expected_echo(key) -> str:
    """key = echo_key column (first three space-separated words of prompt_name, or NONAME)."""
    return _norm_words(key)


def extract_array(raw: str):
    return json.loads(raw[raw.index("["): raw.rindex("]") + 1])


def validate(raw, err, expected):
    """expected: list of names in pos order. Returns (ok, problem)."""
    if err:
        return False, f"endpoint_error: {str(err)[:120]}"
    if not raw:
        return False, "empty_response"
    try:
        arr = extract_array(raw)
    except Exception as e:  # noqa: BLE001
        return False, f"unparseable: {type(e).__name__}"
    if not isinstance(arr, list) or len(arr) != len(expected):
        return False, f"count {len(arr) if isinstance(arr, list) else 'n/a'} != {len(expected)}"
    for k, (o, name) in enumerate(zip(arr, expected), start=1):
        if not isinstance(o, dict):
            return False, f"item {k} not an object"
        if o.get("n") != k:
            return False, f"item {k} n={o.get('n')!r}"
        if _norm_words(o.get("echo", "")) != expected_echo(name):
            return False, f"item {k} echo {o.get('echo')!r} != {expected_echo(name)!r}"
        if o.get("facility_type") not in TYPES:
            return False, f"item {k} facility_type {o.get('facility_type')!r}"
        if not isinstance(o.get("is_single_specialty"), bool):
            return False, f"item {k} is_single_specialty {o.get('is_single_specialty')!r}"
        if o.get("ownership") not in OWNERSHIP:
            return False, f"item {k} ownership {o.get('ownership')!r}"
        if o.get("confidence") not in CONFIDENCE:
            return False, f"item {k} confidence {o.get('confidence')!r}"
        if not isinstance(o.get("reason"), str):
            return False, f"item {k} reason {o.get('reason')!r}"
    return True, ""


# --------------------------------------------------------------------------- setup
def build_input():
    run(f"""
    CREATE OR REPLACE TABLE {S}.facility_type_input AS
    WITH d AS (
      SELECT *, row_number() OVER (PARTITION BY unique_id ORDER BY name) AS rn FROM {SRC}
    )
    SELECT unique_id, name,
           -- name as shown to the model: literal 'null'/'none', and names that are a JSON
           -- array (column-shifted records), become ''; control characters become spaces
           CASE WHEN name IS NULL OR lower(trim(name)) IN ('null', 'none', '')
                  OR trim(name) LIKE '[%' THEN ''
                ELSE trim(regexp_replace(name, '[\\u0000-\\u001f]', ' ')) END AS prompt_name,
           substr(description, 1, 400) AS description400,
           array_distinct(from_json(specialties, 'array<string>')) AS specialties
    FROM d WHERE rn = 1""")
    run(f"""CREATE OR REPLACE TABLE {S}.facility_type_input AS
    SELECT *, CASE WHEN prompt_name = '' THEN '{NONAME}'
                   ELSE array_join(slice(filter(split(prompt_name, ' '), x -> x != ''), 1, 3), ' ')
              END AS echo_key
    FROM {S}.facility_type_input""")
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_raw (
        phase STRING, batch_id INT, attempt INT, prompt_version STRING, model STRING,
        prompt STRING, response STRING, error STRING, call_ts TIMESTAMP)""")
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_accepted (
        phase STRING, batch_id INT, attempt INT)""")
    run(f"""CREATE TABLE IF NOT EXISTS {S}.facility_type_batches (
        phase STRING, batch_id INT, pos INT, unique_id STRING)""")


def build_batches(phase: str):
    # raw responses of earlier prompt versions are kept for audit
    run(f"DELETE FROM {S}.facility_type_raw WHERE phase = ? AND prompt_version = ?",
        [phase, PROMPT_VERSION])
    for t in ("facility_type_accepted", "facility_type_batches"):
        run(f"DELETE FROM {S}.{t} WHERE phase = ?", [phase])
    limit = f"LIMIT {PILOT_N}" if phase == "pilot" else ""
    run(f"""
    INSERT INTO {S}.facility_type_batches
    SELECT ?, CAST(floor((rn - 1) / {BATCH}) AS INT), CAST((rn - 1) % {BATCH} + 1 AS INT), unique_id
    FROM (
      SELECT unique_id, row_number() OVER (ORDER BY md5(concat('{phase}', unique_id))) AS rn
      FROM (SELECT unique_id FROM {S}.facility_type_input
            ORDER BY md5(concat('{phase}', unique_id)) {limit})
    )""", [phase])


def expected_by_batch(phase: str):
    rows = run(f"""SELECT b.batch_id, b.pos, i.echo_key FROM {S}.facility_type_batches b
                   JOIN {S}.facility_type_input i USING (unique_id)
                   WHERE b.phase = ? ORDER BY b.batch_id, b.pos""", [phase], fetch=True)
    exp: dict[int, list] = {}
    for bid, pos, name in rows:
        exp.setdefault(bid, []).append(name)
        assert len(exp[bid]) == pos
    return exp


# --------------------------------------------------------------------------- calling
def call_attempt(phase: str, attempt: int, batch_ids: list[int]):
    temp = 0.0 if attempt == 1 else 0.3
    ids = ",".join(str(b) for b in batch_ids)
    run(f"""
    INSERT INTO {S}.facility_type_raw
    WITH lines AS (
      SELECT b.batch_id, b.pos,
             concat(b.pos, '. key="', i.echo_key, '" ', to_json(named_struct(
               'name', i.prompt_name, 'description', coalesce(i.description400, ''),
               'specialties', coalesce(i.specialties, array())))) AS line
      FROM {S}.facility_type_batches b JOIN {S}.facility_type_input i USING (unique_id)
      WHERE b.phase = ? AND b.batch_id IN ({ids})
    ), prompts AS (
      SELECT batch_id,
             concat(?, array_join(transform(array_sort(collect_list(struct(pos, line))),
                                            x -> x.line), '\\n')) AS prompt
      FROM lines GROUP BY batch_id
    ), called AS (
      SELECT batch_id, prompt,
             ai_query('{MODEL}', prompt,
                      modelParameters => named_struct('temperature', {temp}, 'max_tokens', 4000),
                      failOnError => false) AS r
      FROM prompts
    )
    SELECT ?, batch_id, {attempt}, ?, '{MODEL}', prompt, r.result, r.errorMessage, current_timestamp()
    FROM called""", [phase, PROMPT, phase, PROMPT_VERSION])


def run_phase(phase: str):
    t0 = time.time()
    build_input()
    build_batches(phase)
    exp = expected_by_batch(phase)
    pending = sorted(exp)
    stats = {"calls": 0, "bad_calls": 0, "batches": len(pending), "problems": []}
    accepted: list[tuple[int, int]] = []
    retried: set[int] = set()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not pending:
            break
        ts = time.time()
        call_attempt(phase, attempt, pending)
        rows = run(f"""SELECT batch_id, response, error FROM {S}.facility_type_raw
                       WHERE phase = ? AND attempt = ? AND prompt_version = ?""",
                   [phase, attempt, PROMPT_VERSION], fetch=True)
        got = {b: (r, e) for b, r, e in rows}
        nxt = []
        for b in pending:
            stats["calls"] += 1
            ok, prob = validate(*got.get(b, (None, "missing_row")), exp[b])
            if ok:
                accepted.append((b, attempt))
            else:
                stats["bad_calls"] += 1
                stats["problems"].append((b, attempt, prob))
                retried.add(b)
                nxt.append(b)
        print(f"attempt {attempt}: {len(pending)} calls, {len(pending) - len(nxt)} ok, "
              f"{len(nxt)} bad, {time.time() - ts:.1f}s", flush=True)
        pending = nxt
    if accepted:
        vals = ",".join(f"('{phase}',{b},{a})" for b, a in accepted)
        run(f"INSERT INTO {S}.facility_type_accepted VALUES {vals}")
    out = "facility_type_pilot" if phase == "pilot" else "facility_type"
    run(f"""
    CREATE OR REPLACE TABLE {S}.{out} AS
    WITH acc AS (
      SELECT r.batch_id, r.response FROM {S}.facility_type_raw r
      JOIN {S}.facility_type_accepted a
        ON a.phase = r.phase AND a.batch_id = r.batch_id AND a.attempt = r.attempt
      WHERE r.phase = '{phase}' AND r.prompt_version = '{PROMPT_VERSION}'
    ), items AS (
      SELECT batch_id, p.pos + 1 AS pos, p.col AS o
      FROM acc LATERAL VIEW posexplode(from_json(
        regexp_extract(response, '(?s)(\\\\[.*\\\\])', 1),
        'array<struct<n:int,echo:string,facility_type:string,is_single_specialty:boolean,
                      ownership:string,confidence:string,reason:string>>')) p AS pos, col
    )
    SELECT b.unique_id, i.name, o.facility_type, o.is_single_specialty, o.ownership,
           o.confidence, o.reason, '{PROMPT_VERSION}' AS prompt_version,
           current_timestamp() AS run_ts
    FROM {S}.facility_type_batches b
    JOIN {S}.facility_type_input i USING (unique_id)
    LEFT JOIN items it ON it.batch_id = b.batch_id AND it.pos = b.pos
    WHERE b.phase = '{phase}'""")
    stats["failed_batches"] = len(pending)
    stats["retried_batches"] = len(retried)
    stats["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(stats, indent=1))
    return stats


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    assert phase in ("pilot", "full")
    run_phase(phase)

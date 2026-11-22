"""Build the verdict table workspace.vf.facility_service with SQL only (no LLM calls).

Rerunnable: INSERT OVERWRITE into the existing contract table, so it can be run again as
sentence tagging (sentence_tags) and the record audit (record_audit, sentence_foreign_flag)
progress. Coverage at build time is stamped on every row.

Inputs (clean base / derived tables only):
  facility_sentences -> distinct_sentences -> sentence_tags      (claims per sentence)
  facilities_clean (specialties, name, city, is_shifted), facility_type
  service_department_map, service_type_fit                       (hand-written lookups)
  record_audit, sentence_foreign_flag                            (optional; used if present)

Run: /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_facility_service.py
"""
import json
import subprocess
import time

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
VF = "workspace.vf"
ROOT = "/Users/yusufakin/CMU/datathon"
OUT = f"{VF}.facility_service"

# Possible tier: hospital-type facilities only.
HOSPITAL_TYPES = ["multispecialty_hospital", "general_hospital_or_nursing_home",
                  "medical_college_teaching_hospital", "government_health_centre",
                  "maternity_women_children", "pediatric", "cardiac", "cancer",
                  "orthopedic_spine", "neuro", "gastro_liver", "kidney_urology"]

# Operating-theatre sentence (caesarean_section Possible gate b). Spark rlike (Java regex) on the
# original sentence (not sentence_key). Phrases case-insensitive; bare "OT" only as a whole word
# in capitals (case-sensitive), so it never matches "physiotherapy" or "other".
OT_PATTERN = (r"(?i:operation theatre|operating theatre|operation theater|operating theater"
              r"|surgical theatre|modular ot)|(?<![A-Za-z])OT(?![A-Za-z])")

# Demote-to-weak patterns (Spark rlike / Java regex, case-insensitive, on the ORIGINAL sentence).
# A sentence that is hedged/future, extractor commentary, about another place, or negated near the
# service term counts as weak for that service whatever its tag says, and is never quoted as
# evidence for Confirmed or Likely (it may still be quoted for Unverified).
HEDGE_RE = (r"(?i)\b(planned|proposed|upcoming|will be|to be (started|commissioned|set up)"
            r"|under construction|coming soon)\b")
COMMENT_RE = (r"(?i)\([^)]*\b(not explicit|not listed|not mentioned|explicit|explicitly|mentioned"
              r"|listed|stated|specified|implied|unclear|inferred)\b")
ELSEWHERE_RE = (r"(?i)\b(oversees|supervises|across \d+ districts|at hub hospitals"
                r"|in other districts|network of|partner hospitals)\b")
# Negation within 4 words of the service term, either side: NEG_PRE + term + NEG_PRE_END and
# NEG_POST + term + NEG_POST_END. "No." (number) is not a negation; a bare "not available"
# elsewhere in the sentence does not demote.
NEG_PRE = r"(?i)\b(?:not|unavailable|no)\b(?!\.)(?:\W+\w+){0,4}?\W+(?:"
NEG_PRE_END = r")\b"
NEG_POST = r"(?i)\b(?:"
NEG_POST_END = r")(?:\W+\w+){0,4}?\W+(?:not|unavailable|no)\b(?!\.)"
SERVICE_TERMS = {   # service term regex; services not listed use the label with spaces
    "dialysis": r"dialysis|haemodialysis|hemodialysis|capd",
    "caesarean_section": r"caesarean|cesarean|c-section|lscs",
    "nicu": r"nicu|neonatal|newborn",
    "picu": r"picu|paediatric icu|pediatric icu|paediatric intensive|pediatric intensive",
    "icu_critical_care": r"icu|iccu|intensive care|critical care",
    "cardiac_surgery": r"cardiac surgery|heart surgery|cabg|bypass|cardiothoracic",
    "interventional_cardiology": r"angioplasty|angiography|cath lab|cathlab|ptca|stent",
    "mri": r"mri|magnetic resonance",
    "ct_scan": r"ct|cat scan|computed tomography",
    "xray": r"x-ray|xray|radiograph",
    "ultrasound": r"ultrasound|usg|sonography",
    "mammography": r"mammogra\w*",
    "nuclear_imaging": r"pet|spect|nuclear|gamma camera",
    "burn_care": r"burns?",
    "trauma_emergency": r"trauma|emergency|casualty|accident",
    "ambulance": r"ambulances?",
    "blood_bank": r"blood bank|blood storage",
    "ventilator_support": r"ventilators?|ventilation",
    "transplant": r"transplant\w*",
    # pa_single_v2 labels
    "urology": r"urolog\w*|kidney stones?|stones?|prostate|lithotripsy|turp|pcnl",
    "diabetes_endocrinology": r"diabet\w*|thyroid|endocrin\w*",
    "health_checkup_vaccination": r"check-?ups?|vaccin\w*|immuni[sz]ation",
    "cardiac_diagnostics": r"echo\w*|tmt|treadmill|stress test|holter|eecp|doppler",
    "neurology": r"neurolog\w*|eeg|emg|epilepsy|migraine|headache",
    "ayush_traditional_medicine": r"ayurved\w*|homo?eopath\w*|panchakarma|unani|siddha|naturopathy|yoga",
    "gynecology": r"gyn\w*colog\w*|hysteroscop\w*|colposcop\w*|hysterectomy",
    "proctology": r"piles|fistula|fissure|ha?emorrhoids?|proctolog\w*",
    "pain_management": r"pain",
    "vascular_surgery": r"vascular|varicose|veins?|fistula",
    "cardiology_medical": r"cardiolog\w*|heart|cardiac",
}

# Wave 1 (proposal 2): "explicit" counts only when a number sits next to a unit word, after
# stripping time and marketing numbers. Spark rlike (Java regex), case-insensitive.
STRIP_RE = (r"(?i)24\s*[/x×*]\s*7|24\s*(hours?|hrs?)|round[\s-]the[\s-]clock"
            r"|\b\d+\s*\+?\s*(years?|yrs?)\b|\b\d+\s*\+\s*[a-z]+"
            r"|\b\d+\s*(services|specialt(y|ies)|specialit(y|ies)|doctors|specialists|departments"
            r"|consultants|surgeons|staff|nurses|patients|cities|centres|centers|hospitals|branches)\b"
            r"|\b(19|20)\d\d\b")
UNIT_RE = (r"(?i)\b\d+(\.\d+)?\s*(-\s*)?([a-z]+[\s-]+){0,2}?"
           r"(beds?|bedded|machines?|units?|stations?|theat(re|er)s?|ots|scanners?|tesla|t|slices?"
           r"|sessions?|treatments|ventilators?|cots?|incubators?|warmers?|chairs?)\b")
# Department-name or generic line (wave 1, proposal 1): a sentence with no term match that names a
# department / speciality or an operating theatre. Evidence made only of these -> Possible.
DEPT_RE = (r"(?i)\b(department|departments|dept|division|specialit(y|ies)|specialt(y|ies)"
           r"|(?!techno)[a-z]+olog(y|ies|ist|ists)|[a-z]*iatrics?|orthop(a)?edics|obstetrics|medicine)\b")
# Generic dedicated-facility test (services without a DEDICATED list): term match + facility noun.
FACILITY_NOUN_RE = (r"(?i)\b(units?|cent(re|er)s?|wards?|labs?|laborator(y|ies)|machines?|scanners?"
                    r"|theat(re|er)s?)\b")
DEPT_WARNING = "Only a department or an operating theatre is listed for this service"


def term_values() -> str:
    """VALUES rows (service, term regex, gate) from scripts/build_lookups.py TERMS."""
    import sys
    sys.path.insert(0, f"{ROOT}/scripts")
    import build_lookups as bl
    rows = []
    for sv in bl.SERVICES:
        rx = bl.term_regex(sv)
        gate = bool(rx) and sv not in bl.TERM_GATE_OFF
        drx = bl.dedicated_regex(sv)
        rows.append(f"({lit(sv)}, {lit(rx) if rx else 'CAST(NULL AS STRING)'}, {'true' if gate else 'false'}, "
                    f"{lit(drx) if drx else 'CAST(NULL AS STRING)'})")
    return ", ".join(rows)


# Name-token rule, identical to scripts/contamination.py signal a (A_MIN_LEN, A_GENERIC,
# and tokens equal to any city name are dropped).
A_MIN_LEN = 4
A_GENERIC = """hospital hospitals clinic clinics eye dental dentist care centre center multispeciality
multispecialty multi speciality specialty super health healthcare medical nursing home institute
research diagnostic diagnostics the and of for dr doctor doctors children women maternity memorial
general city life new sri shri shree lab labs path pathology polyclinic trust foundation private
limited ltd pvt india indian unit road nagar""".split()


def lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def arr(xs) -> str:
    return "array(" + ",".join(lit(x) for x in xs) + ")"


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


def svc_label(x: str) -> str:
    """SQL expression: human label for a service code, capitalised."""
    return (f"CASE {x} WHEN 'mri' THEN 'MRI' WHEN 'nicu' THEN 'NICU' WHEN 'picu' THEN 'PICU' "
            f"WHEN 'icu_critical_care' THEN 'ICU / critical care' WHEN 'ct_scan' THEN 'CT scan' "
            f"ELSE concat(upper(substr(replace({x}, '_', ' '), 1, 1)), "
            f"substr(replace({x}, '_', ' '), 2)) END")


def svc_label_lc(x: str) -> str:
    """SQL expression: human label for a service code, mid-sentence."""
    return (f"CASE {x} WHEN 'mri' THEN 'MRI' WHEN 'nicu' THEN 'NICU' WHEN 'picu' THEN 'PICU' "
            f"WHEN 'icu_critical_care' THEN 'ICU / critical care' WHEN 'ct_scan' THEN 'CT scan' "
            f"ELSE replace({x}, '_', ' ') END")


def _readable_names() -> dict:
    """Readable service names from the app's config (single source), mid-sentence case."""
    import runpy
    names = runpy.run_path(f"{ROOT}/app/config.py").get("SERVICE_NAME", {})
    # labels added with pa_single_v2 that app/config.py does not have yet (app/config.py wins)
    extra = runpy.run_path(f"{ROOT}/scripts/service_names_extra.py").get("NEW_SERVICE_NAME", {})
    names = {**extra, **names}
    return {k: (v if v[:2].isupper() else v[:1].lower() + v[1:]) for k, v in names.items()}


def readable_lc(x: str) -> str:
    """SQL expression: readable service name for label x (falls back to label with spaces)."""
    whens = " ".join(f"WHEN {lit(k)} THEN {lit(v)}" for k, v in _readable_names().items())
    return f"CASE {x} {whens} ELSE replace({x}, '_', ' ') END"


def type_readable(x: str) -> str:
    """SQL expression: readable facility type with article, from app/config.py FACILITY_TYPE_NAME."""
    import runpy
    names = runpy.run_path(f"{ROOT}/app/config.py").get("FACILITY_TYPE_NAME", {})
    whens = " ".join(f"WHEN {lit(k)} THEN {lit(v)}" for k, v in names.items())
    return (f"CASE {x} {whens} ELSE concat('a ', replace({x}, '_', ' '), ' facility') END")


def build_sql(has_audit: bool, has_flag: bool) -> str:
    foreign_anti = (f"LEFT ANTI JOIN (SELECT DISTINCT unique_id, source_column, position "
                    f"FROM {VF}.sentence_foreign_flag WHERE is_foreign) ff "
                    f"USING (unique_id, source_column, position)") if has_flag else ""
    audit_cte = (f"""audit AS (
  SELECT unique_id, verdict,
         CASE WHEN n_usable > 0 THEN n_flagged / n_usable END flagged_share
  FROM {VF}.record_audit WHERE NOT coalesce(failed, false)
  QUALIFY row_number() OVER (PARTITION BY unique_id ORDER BY audited_at DESC) = 1)"""
                 if has_audit else
                 "audit AS (SELECT CAST(NULL AS STRING) unique_id, CAST(NULL AS STRING) verdict, "
                 "CAST(NULL AS DOUBLE) flagged_share "
                 "WHERE false)")
    n_audited = (f"(SELECT count(DISTINCT unique_id) FROM {VF}.record_audit "
                 f"WHERE NOT coalesce(failed, false))") if has_audit else "CAST(NULL AS BIGINT)"
    terms_values = ", ".join(f"({lit(k)}, {lit(v)})" for k, v in SERVICE_TERMS.items())
    return f"""
INSERT OVERWRITE {OUT}
WITH
cities AS (SELECT collect_set(lower(trim(city))) cities FROM {VF}.facilities_clean
           WHERE city IS NOT NULL),
fac AS (
  SELECT c.unique_id, lower(trim(c.city)) city_l, c.specialties,
         coalesce(ft.facility_type, 'unknown') facility_type,
         array_distinct(filter(split(lower(coalesce(c.name, '')), '[^a-z0-9]+'),
           x -> length(x) >= {A_MIN_LEN} AND NOT array_contains({arr(A_GENERIC)}, x)
                AND NOT array_contains(cities.cities, x))) toks
  FROM {VF}.facilities_clean c CROSS JOIN cities
  LEFT JOIN {VF}.facility_type ft USING (unique_id)
  WHERE NOT coalesce(c.is_shifted, false)),
tags AS (
  SELECT d.sentence_key,
         CASE WHEN t.prompt_version = 'rule_dental_only' THEN true ELSE t.is_claim END is_claim,
         CASE WHEN t.prompt_version = 'rule_dental_only' THEN 'stated' ELSE t.strength END strength,
         CASE WHEN t.prompt_version = 'rule_dental_only' THEN filter(t.services, x -> x = 'dental')
              ELSE t.services END services
  FROM {VF}.sentence_tags t JOIN {VF}.distinct_sentences d USING (sentence_id)
  WHERE NOT coalesce(t.failed, false)
  QUALIFY row_number() OVER (PARTITION BY t.sentence_id ORDER BY t.tagged_at DESC) = 1),
sent AS (
  SELECT s.unique_id, s.source_column, s.position, s.sentence, s.sentence_key
  FROM {VF}.facility_sentences s
  JOIN fac USING (unique_id)
  {foreign_anti}
  WHERE NOT s.is_placeholder AND NOT s.is_repeat),
terms AS (SELECT * FROM VALUES {terms_values} AS v(service, term)),
svc_terms AS (SELECT * FROM VALUES {term_values()} AS v(service, rx, gate, drx)),
claim0 AS (
  SELECT s.unique_id, svc AS service, s.sentence_key, s.sentence, s.source_column, s.position,
         t.strength tag_strength,
         CASE WHEN exists(f.toks, x -> instr(lower(s.sentence), x) > 0)
                OR (f.city_l IS NOT NULL AND instr(lower(s.sentence), f.city_l) > 0)
              THEN 0 ELSE 1 END nrank
  FROM sent s JOIN tags t USING (sentence_key) JOIN fac f USING (unique_id)
  LATERAL VIEW explode(t.services) e AS svc
  WHERE t.is_claim AND t.strength IN ('explicit', 'stated', 'weak')
  QUALIFY row_number() OVER (PARTITION BY s.unique_id, svc, s.sentence_key
                             ORDER BY s.source_column, s.position) = 1),
claim AS (
  SELECT c.*,
    CASE WHEN demoted OR tag_strength = 'weak' THEN 2
         -- explicit needs a number next to a unit word, after stripping time/marketing numbers
         -- explicit = a number next to a unit word (after stripping time/marketing numbers), or a
         -- dedicated unit/machine/facility for the service (DEDICATED list, else term + facility noun)
         WHEN tag_strength = 'explicit'
              AND (regexp_replace(sentence, {lit(STRIP_RE)}, ' ') RLIKE {lit(UNIT_RE)} OR dedicated) THEN 0
         ELSE 1 END srank,
    -- term-list match first in the evidence order
    CASE WHEN tmatch THEN 0 ELSE 1 END tmiss,
    -- evidence order after strength: sentences with a digit first, then longer first
    CASE WHEN sentence RLIKE '[0-9]' THEN 0 ELSE 1 END nodigit,
    -length(sentence) neg_len,
    -- near-duplicate key: lowercase, punctuation (incl. thousands separators) removed
    trim(regexp_replace(regexp_replace(lower(sentence), '[^a-z0-9 ]', ''), ' +', ' ')) norm
  FROM (
    SELECT c0.*,
      coalesce(c0.sentence RLIKE st.rx, false) tmatch, coalesce(st.gate, false) gate,
      coalesce(CASE WHEN st.drx IS NOT NULL THEN c0.sentence RLIKE st.drx
                    ELSE c0.sentence RLIKE st.rx AND c0.sentence RLIKE {lit(FACILITY_NOUN_RE)} END, false) dedicated,
      (NOT coalesce(c0.sentence RLIKE st.rx, false)
       AND (c0.sentence RLIKE {lit(OT_PATTERN)} OR c0.sentence RLIKE {lit(DEPT_RE)})) dept_ot,
      (c0.sentence RLIKE {lit(HEDGE_RE)} OR c0.sentence RLIKE {lit(COMMENT_RE)}
       OR c0.sentence RLIKE {lit(ELSEWHERE_RE)}
       OR c0.sentence RLIKE concat({lit(NEG_PRE)}, coalesce(tm.term, replace(c0.service, '_', ' ')),
                                   {lit(NEG_PRE_END)})
       OR c0.sentence RLIKE concat({lit(NEG_POST)}, coalesce(tm.term, replace(c0.service, '_', ' ')),
                                   {lit(NEG_POST_END)})) demoted
    FROM claim0 c0 LEFT JOIN terms tm ON tm.service = c0.service
    LEFT JOIN svc_terms st ON st.service = c0.service) c),
direct AS (
  SELECT unique_id, service,
    count(DISTINCT CASE WHEN srank = 0 THEN sentence_key END) n_explicit,
    count(DISTINCT CASE WHEN srank = 1 THEN sentence_key END) n_stated,
    count(DISTINCT CASE WHEN srank = 2 THEN sentence_key END) n_weak,
    count(DISTINCT CASE WHEN srank <= 1 AND tmatch THEN sentence_key END) n_term,
    count(DISTINCT CASE WHEN srank <= 1 AND NOT dept_ot THEN sentence_key END) n_nondept,
    max(gate) gate,
    array_sort(collect_list(struct(tmiss, srank, nodigit, neg_len, source_column, position, sentence,
            demoted, norm))) ev_all
  FROM claim GROUP BY unique_id, service),
backing AS (
  SELECT f.unique_id, m.service, array_sort(collect_set(m.value)) specs
  FROM (SELECT unique_id, explode(specialties) sp FROM fac) f
  JOIN {VF}.service_department_map m
    ON m.link_type = 'specialty' AND m.strength = 'strong' AND m.value = sp
  GROUP BY f.unique_id, m.service),
possible AS (
  SELECT b.unique_id, m.service,
    array_sort(collect_set(c.service)) related,
    array_distinct(array_sort(collect_list(struct(c.tmiss, c.srank, c.nodigit, c.neg_len, c.source_column,
            c.position, c.sentence, c.demoted, c.norm)))) ev_all
  FROM backing b
  JOIN fac f ON f.unique_id = b.unique_id
              AND array_contains({arr(HOSPITAL_TYPES)}, f.facility_type)
  JOIN {VF}.service_department_map m
    ON m.link_type = 'implied_by_service' AND m.strength = 'strong' AND m.service = b.service
  JOIN claim c ON c.unique_id = b.unique_id AND c.service = m.value AND c.srank <= 1
  LEFT ANTI JOIN direct d ON d.unique_id = b.unique_id AND d.service = m.service
  WHERE m.service <> 'caesarean_section'
     OR (b.unique_id IN (SELECT unique_id FROM claim
                         WHERE service IN ('normal_delivery', 'high_risk_obstetrics'))
         AND (b.unique_id IN (SELECT unique_id FROM claim WHERE service = 'general_surgery')
              OR b.unique_id IN (SELECT unique_id FROM sent WHERE sentence RLIKE {lit(OT_PATTERN)})))
  GROUP BY b.unique_id, m.service),
base AS (
  SELECT unique_id, service, n_explicit, n_stated, n_weak, ev_all,
         CAST(NULL AS ARRAY<STRING>) related, true has_claim, n_term, n_nondept, gate FROM direct
  UNION ALL
  SELECT unique_id, service, 0, 0, 0, ev_all, related, false, 0, 0, false FROM possible),
{audit_cte},
j AS (
  SELECT b.*, f.facility_type, coalesce(bk.specs, array()) specs,
         size(coalesce(bk.specs, array())) > 0 backed,
         tf.fit type_fit, a.verdict audit_verdict, a.flagged_share,
         -- mixed record: mostly_foreign, or partly_foreign with >= 50% of usable sentences flagged
         (a.verdict = 'mostly_foreign'
          OR (a.verdict = 'partly_foreign' AND a.flagged_share >= 0.5)) mixed_unverified,
         -- warn when mostly_foreign or >= 25% flagged; unaudited facilities get no warning
         coalesce(a.verdict = 'mostly_foreign' OR a.flagged_share >= 0.25, false) mixed_warn
  FROM base b JOIN fac f USING (unique_id)
  LEFT JOIN backing bk ON bk.unique_id = b.unique_id AND bk.service = b.service
  LEFT JOIN {VF}.service_type_fit tf
    ON tf.service = b.service AND tf.facility_type = f.facility_type
  LEFT JOIN audit a ON a.unique_id = b.unique_id),
t AS (
  SELECT j.*,
    CASE WHEN coalesce(mixed_unverified, false) OR type_fit = 'unexpected'
              OR (has_claim AND n_explicit + n_stated = 0) THEN 'Unverified'
         -- term gate: evidence made only of department names / operating-theatre lines
         WHEN gate AND has_claim AND n_nondept = 0 THEN 'Possible'
         WHEN n_explicit >= 1 AND (NOT gate OR n_term >= 1) AND (backed OR n_explicit + n_stated >= 2
              OR type_fit = 'expected') THEN 'Confirmed'
         WHEN n_explicit + n_stated >= 1 THEN 'Likely'
         ELSE 'Possible' END tier,
    replace(facility_type, '_', ' ') type_l
  FROM j),
t2 AS (
  SELECT t.*, (gate AND has_claim AND tier = 'Possible') dept_only,
         CASE WHEN tier IN ('Confirmed', 'Likely') OR (has_claim AND tier = 'Possible')
              THEN filter(ev_all, x -> NOT x.demoted)
                   ELSE ev_all END ev_f
  FROM t),
stamp AS (
  SELECT (SELECT count(*) FROM {VF}.sentence_tags WHERE NOT coalesce(failed, false)) n_tagged,
         (SELECT count(DISTINCT sentence_id) FROM {VF}.sentence_tags) n_attempted,
         {n_audited} n_audited)
SELECT unique_id, service, tier,
  CAST(n_explicit AS INT), CAST(n_stated AS INT), CAST(n_weak AS INT),
  CAST(backed AS STRING) department_backing, type_fit, audit_verdict,
  -- demoted (hedged / commentary / elsewhere / negated) sentences are never quoted for Confirmed
  -- or Likely; near-duplicates (same norm) are quoted once, keeping the first in evidence order
  slice(transform(aggregate(ev_f, filter(ev_f, x -> false),
                            (acc, x) -> CASE WHEN exists(acc, y -> y.norm = x.norm) THEN acc
                                             ELSE concat(acc, array(x)) END),
                  x -> named_struct('sentence', x.sentence, 'source_column', x.source_column)),
        1, 3) evidence,
  array_compact(array(
    CASE WHEN mixed_warn
         THEN 'Parts of this record may describe a different hospital. Call to confirm.' END,
    CASE WHEN type_fit = 'unexpected'
         THEN concat(upper(substr({readable_lc('service')}, 1, 1)), substr({readable_lc('service')}, 2),
                     ' is unexpected for ', {type_readable('facility_type')}) END,
    CASE WHEN has_claim AND n_explicit + n_stated = 0 THEN 'Only weak evidence' END,
    CASE WHEN dept_only THEN {lit(DEPT_WARNING)} END,
    CASE WHEN NOT has_claim
         THEN concat('No direct claim; inferred from the ',
                     array_join(transform(specs, s -> lower(regexp_replace(s, '([A-Z])', ' $1'))), ', '),
                     CASE WHEN size(specs) > 1 THEN ' departments and ' ELSE ' department and ' END,
                     CASE WHEN size(related) > 1 THEN '' ELSE 'a ' END,
                     array_join(transform(related, r -> {readable_lc('r')}), ', '),
                     CASE WHEN size(related) > 1 THEN ' claims' ELSE ' claim' END) END
  )) warnings,
  current_timestamp() build_ts,
  stamp.n_tagged n_sentences_tagged_at_build,
  stamp.n_audited n_records_audited_at_build,
  stamp.n_attempted n_sentences_attempted_at_build,
  facility_type, flagged_share, CAST(n_term AS INT) n_term_sentences
FROM t2 CROSS JOIN stamp
"""


TABLE_COMMENT = (
    "Verdict per (unique_id, service), built by scripts/build_facility_service.py with SQL only "
    "(no LLM calls); rerun as tagging and the audit progress (INSERT OVERWRITE). Rows exist only "
    "for pairs with >= 1 claim sentence, or that qualify for Possible. Claims = sentence_tags rows "
    "with is_claim true (failed rows ignored) on usable sentences (not placeholder, not repeat, "
    "facility not shifted), minus sentences flagged foreign in sentence_foreign_flag (joined on "
    "unique_id, source_column, position) when that table has rows. Rows tagged by prompt_version "
    "'rule_dental_only' (is_claim NULL, services [dental], strength NULL) are treated as is_claim "
    "true with strength 'stated', for the dental service only. An explicit-tagged sentence counts as explicit "
    "only when a number sits next to a unit word (UNIT_RE: beds, machines, units, stations, theatres, scanners, Tesla, "
    "slice, sessions, ventilators, cots, incubators...) after stripping time and marketing numbers (STRIP_RE: 24/7, "
    "N years, N+ services, years); otherwise it counts as stated. And a sentence that is hedged/future, extractor commentary, "
    "about another place, or negated within 4 words of the service term counts as weak (patterns in the "
    "script) and is never quoted for Confirmed or Likely; both applied before the tier rules, "
    "sentence_tags unchanged. "
    "Tier, first match wins: "
    "Unverified if audit mostly_foreign (or partly_foreign with flagged_share = n_flagged/n_usable >= 0.5), type_fit unexpected, or only weak sentences; "
    "term gate (services with applied = true in workspace.vf.service_term_gate; term lists in workspace.vf.service_terms): "
    "Possible with warning 'Only a department or an operating theatre is listed for this service' if every explicit/stated "
    "sentence lacks a term match and is a department-name (DEPT_RE) or operating-theatre (OT_PATTERN) line; Confirmed if "
    ">= 1 explicit, >= 1 explicit/stated sentence matching the term list (gated services only) and (department_backing, or >= 2 explicit+stated, or type_fit expected); Likely "
    "if >= 1 explicit or stated; Possible if no claim sentence for the service but department_backing "
    "and an explicit/stated claim for a related service that implies it (service_department_map "
    "implied_by_service, STRONG links only), hospital facility types only; evidence quotes only the "
    "triggering related-service sentences. caesarean_section Possible additionally needs a claim for "
    "normal_delivery or high_risk_obstetrics AND (a general_surgery claim OR a usable non-foreign "
    "sentence matching the operating-theatre pattern OT_PATTERN in the script). Coverage at build time is in "
    "build_ts, n_sentences_tagged_at_build, n_records_audited_at_build: tiers change as coverage "
    "grows. Read by the vf-locator Databricks App.")

COL_COMMENTS = {
    "unique_id": "Facility key; joins to workspace.vf.facilities_clean.unique_id",
    "service": "Service label (one of the 60 labels in scripts/build_lookups.py SERVICES: 49 from pa_single_v1 + 11 from pa_single_v2; readable names in app/config.py and scripts/service_names_extra.py), e.g. dialysis, caesarean_section, nicu",
    "tier": "Confirmed | Likely | Possible | Unverified (rules in the table comment). Possible = no direct claim, inferred from department + related-service claim",
    "n_explicit": "Distinct sentences (distinct sentence_key per facility) tagged explicit for this service in which a number sits next to a unit word after stripping time/marketing numbers (UNIT_RE, STRIP_RE in the script); 0 for inferred Possible",
    "n_term_sentences": "Distinct non-demoted explicit/stated sentences for this service that match its term list (workspace.vf.service_terms, whole word/phrase); Confirmed needs >= 1 for gated services; 0 for inferred Possible",
    "n_stated": "Distinct sentences tagged stated for this service, plus explicit-tagged sentences without a number next to a unit word (rule_dental_only rows count here for dental); 0 for Possible",
    "n_weak": "Distinct sentences tagged weak for this service; 0 for Possible",
    "department_backing": "'true' if facilities_clean.specialties contains a specialty linked to the service with strength STRONG in service_department_map (supporting links are not used); 'false' otherwise, including services with no strong specialty link",
    "type_fit": "service_type_fit.fit for the facility's facility_type (expected / plausible / unexpected); NULL if no fit row",
    "audit_verdict": "record_audit.verdict (latest non-failed); NULL if not audited, audit failed, or record_audit absent at build",
    "evidence": "Up to 3 verbatim sentences with source_column: term-list matches first, then explicit before stated before weak, then sentences with a digit, then longer first; near-duplicates (same text after lowercasing and removing punctuation/thousands separators) quoted once. For Possible: only explicit/stated sentences of the related service(s) whose strong implied_by_service link triggered the row",
    "facility_type": "Added by build_facility_service.py: workspace.vf.facility_type label used for type_fit ('unknown' if none)",
    "flagged_share": "Added by build_facility_service.py: record_audit n_flagged / n_usable (share of the record's usable sentences flagged as describing another organisation); NULL if not audited",
    "warnings": "Plain-text reasons a row is Unverified or Possible. Mixed-record warning 'Parts of this record may describe a different hospital. Call to confirm.' only when audit is mostly_foreign or record_audit n_flagged/n_usable >= 0.25 (none for unaudited). Location caveats are added by the app",
    "build_ts": "Added by build_facility_service.py: when this build ran",
    "n_sentences_tagged_at_build": "Added by build_facility_service.py: non-failed rows in sentence_tags (LLM + rule_dental_only) at build time; compare to 271,262 distinct sentences",
    "n_sentences_attempted_at_build": "Added by build_facility_service.py: distinct sentence_id in sentence_tags (tagged or failed) at build time; tagging is complete when this reaches 271,262",
    "n_records_audited_at_build": "Added by build_facility_service.py: distinct unique_id with a non-failed record_audit row at build time; NULL if record_audit absent",
}


STATS = f"{VF}.build_stats"


def build_stats(c, has_audit):
    """Funnel numbers for the app's "How this works" panel, as of this build."""
    run(c, f"""CREATE TABLE IF NOT EXISTS {STATS} (metric STRING, value BIGINT, build_ts TIMESTAMP)
        COMMENT 'Funnel numbers for the vf-locator How this works panel, rewritten by scripts/build_facility_service.py on every rebuild of facility_service. build_ts = facility_service.build_ts.'""")
    audited = (f"(SELECT count(*) FROM {VF}.record_audit WHERE NOT coalesce(failed, false))"
               if has_audit else "CAST(NULL AS BIGINT)")
    mixed = (f"""(SELECT count(*) FROM {VF}.record_audit WHERE NOT coalesce(failed, false)
                 AND (verdict = 'mostly_foreign' OR (n_usable > 0 AND n_flagged / n_usable >= 0.25)))"""
             if has_audit else "CAST(NULL AS BIGINT)")
    metrics = [
        ("facilities", f"SELECT count(*) FROM {VF}.facilities_clean WHERE NOT coalesce(is_shifted, false)"),
        ("sentences_read", f"""SELECT count(*) FROM {VF}.facility_sentences s JOIN {VF}.facilities_clean f
            USING (unique_id) WHERE NOT coalesce(f.is_shifted, false)
            AND NOT s.is_placeholder AND NOT s.is_repeat"""),
        ("distinct_sentences", f"SELECT count(*) FROM {VF}.distinct_sentences"),
        ("distinct_sentences_tagged", f"""SELECT count(DISTINCT sentence_id) FROM {VF}.sentence_tags
            WHERE NOT coalesce(failed, false)"""),
        ("service_claim_sentences", f"""SELECT count(DISTINCT sentence_id) FROM {VF}.sentence_tags
            WHERE NOT coalesce(failed, false) AND (is_claim OR prompt_version = 'rule_dental_only')"""),
        ("facilities_audited", f"SELECT {audited}"),
        ("records_mixed", f"SELECT {mixed}"),
        ("rows_confirmed", f"SELECT count_if(tier = 'Confirmed') FROM {OUT}"),
        ("rows_likely", f"SELECT count_if(tier = 'Likely') FROM {OUT}"),
        ("rows_possible", f"SELECT count_if(tier = 'Possible') FROM {OUT}"),
        ("rows_unverified", f"SELECT count_if(tier = 'Unverified') FROM {OUT}"),
    ]
    union = "\nUNION ALL ".join(f"SELECT {lit(m)} AS metric, CAST(({q}) AS BIGINT) AS value"
                                 for m, q in metrics)
    run(c, f"""INSERT OVERWRITE {STATS}
SELECT metric, value, (SELECT max(build_ts) FROM {OUT}) FROM ({union})""")
    print("build_stats:", run(c, f"SELECT metric, value FROM {STATS} ORDER BY metric", True))


def main():
    c = conn()
    present = {r["table_name"] for r in run(c, f"""SELECT table_name FROM workspace.information_schema.tables
        WHERE table_schema = 'vf' AND table_name IN ('record_audit', 'sentence_foreign_flag',
        'service_department_map', 'service_type_fit', 'facility_type', 'sentence_tags')""", True)}
    for req in ("service_department_map", "service_type_fit", "facility_type", "sentence_tags"):
        if req not in present:
            raise SystemExit(f"required table workspace.vf.{req} missing")
    has_audit = "record_audit" in present
    has_flag = "sentence_foreign_flag" in present
    print(f"record_audit present={has_audit} sentence_foreign_flag present={has_flag}")

    cols = {r["col_name"] for r in run(c, f"DESCRIBE TABLE {OUT}", True)}
    add = [(n, t) for n, t in [("build_ts", "TIMESTAMP"), ("n_sentences_tagged_at_build", "BIGINT"),
                               ("n_records_audited_at_build", "BIGINT"),
                               ("n_sentences_attempted_at_build", "BIGINT"),
                               ("facility_type", "STRING"), ("flagged_share", "DOUBLE"),
                               ("n_term_sentences", "INT")]
           if n not in cols]
    if add:
        run(c, f"ALTER TABLE {OUT} ADD COLUMNS (" + ", ".join(f"{n} {t}" for n, t in add) + ")")
        print("added columns:", [n for n, _ in add])

    t0 = time.time()
    q = build_sql(has_audit, has_flag)
    run(c, q)
    print(f"build secs={time.time() - t0:.1f}")
    # how many (facility, sentence, service) claim pairs the demote-to-weak patterns hit
    ctes = q[q.index("WITH"):q.index(",\ndirect AS (")]
    print("demoted pairs:", run(c, ctes + """
SELECT count(*) n_pairs, count_if(demoted AND tag_strength <> 'weak') n_demoted_from_explicit_or_stated,
       count_if(demoted) n_demoted, count_if(demoted AND tag_strength <> 'weak' AND service = 'dialysis') n_dialysis
FROM claim""", True))

    build_stats(c, has_audit)
    run(c, f"COMMENT ON TABLE {OUT} IS {lit(TABLE_COMMENT)}")
    for col, cm in COL_COMMENTS.items():
        run(c, f"ALTER TABLE {OUT} ALTER COLUMN {col} COMMENT {lit(cm)}")

    for r in run(c, f"""SELECT tier, count(*) n FROM {OUT} GROUP BY tier ORDER BY tier""", True):
        print(r)
    print(run(c, f"""SELECT max(n_sentences_tagged_at_build) tagged, max(n_records_audited_at_build) audited,
        max(build_ts) ts, count(*) n_rows FROM {OUT}""", True))


if __name__ == "__main__":
    main()

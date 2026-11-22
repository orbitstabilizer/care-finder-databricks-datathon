"""Build the three clean base tables in workspace.vf (mechanical cleaning only, no LLM).

  workspace.vf.facilities_clean     one row per facility (unique_id)
  workspace.vf.facility_sentences   one row per non-empty item of procedure/capability/equipment
  workspace.vf.distinct_sentences   one row per sentence_key (non-placeholder, non-shifted)

Source (read-only Delta Sharing):
  databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities

Usage:
  /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_clean_base.py          # build + report
  /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_clean_base.py report   # report only
  /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_clean_base.py add_phone  # add/refresh official_phone only
"""

import json
import subprocess
import sys

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"

SRC = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities"
FC = "workspace.vf.facilities_clean"
FS = "workspace.vf.facility_sentences"
DS = "workspace.vf.distinct_sentences"

# --------------------------------------------------------------------------------------
# Reusable SQL expressions
# --------------------------------------------------------------------------------------

def missing_to_null(col: str) -> str:
    """Trim; '', 'null', 'none' (any case) -> NULL."""
    return f"CASE WHEN lower(trim({col})) IN ('', 'null', 'none') THEN NULL ELSE trim({col}) END"


def domain(col: str) -> str:
    """Host only: lowercase, strip scheme, strip leading www., stop at / : ? # whitespace.
    Result must look like a hostname (labels of [a-z0-9-] joined by dots), else NULL."""
    host = (
        f"regexp_extract(lower(trim({col})), "
        r"r'^(?:[a-z][a-z0-9+.\-]*://)?(?:www\.)?([^/:?#\s]+)', 1)"
    )
    return (
        f"CASE WHEN {col} IS NULL OR lower(trim({col})) IN ('', 'null', 'none') THEN NULL "
        rf"WHEN {host} RLIKE r'^[a-z0-9\-]+(\.[a-z0-9\-]+)+$' THEN {host} ELSE NULL END"
    )


def int_or_null(col: str) -> str:
    return f"try_cast(trim({col}) AS INT)"


def is_empty_scalar(col: str) -> str:
    return f"({col} IS NULL OR lower(trim({col})) IN ('', 'null', 'none'))"


UUID_RE = r"r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'"

# --------------------------------------------------------------------------------------
# Placeholder rules (applied to sentence_key: lowercase, collapsed whitespace,
# trailing [whitespace . , ; : ! ? …] removed). Rule-based, conservative.
# --------------------------------------------------------------------------------------

P1_EXACT = [
    "none", "nil", "n/a", "na", "null", "nan", "unknown", "-", "--", "tbd",
    "not specified", "not available", "not applicable", "not mentioned", "not listed",
    "not provided", "not stated", "none listed", "none mentioned", "none specified",
    "none found", "not specified in content", "not specified in listing",
]

# P2: refers to the scraped source ("provided content", "on the page", ...) AND states absence.
# Evaluated on the key with parenthesised segments removed, so a real claim followed by
# "(not specified in content)" is NOT flagged.
P2_META = (
    r"r'\b(provided|supplied|given|source|input|scraped|available)( [a-z0-9&\x27.\-]+){0,4} "
    r"(content|text|page|pages|data|information|material|document|snippet|entry)\b"
    r"|\b(in|from|on) (the |this )?(content|text|input|listing|page|hospital page)\b"
    r"|\b(the|provided) content (does|did) not\b'"
)
P2_NEG = (
    r"r'\b(no|not|none|nor|unknown|without|omitted|unavailable|unspecified)\b|n\x27t\b'"
)

# P3: extractor note marking an item as absent: "liver transplant (not listed)",
# "neurophysiology? (not listed) — skip", "... -- exclude".
P3 = (
    r"r'\((not|no) (explicitly )?(listed|mentioned|specified|stated|found)\)\s*"
    r"((—|--|-)\s*(skip|exclude))?$|(—|--)\s*(skip|exclude)$'"
)

# P4: generic absence statement without a source reference:
# starts with "no"/"none" (optionally "there are/has/offers/the hospital has"), names a
# clinical-content noun AND a listing verb. Length-capped.
P4_START = r"r'^(there (are|is) |has |offers |the (hospital|facility) has )?(no|none) '"
P4_NOUN = (
    r"r'\b(procedures?|equipment|devices?|treatments?|surger(y|ies)|services?|"
    r"capabilit(y|ies)|details|information|interventions)\b'"
)
P4_VERB = (
    r"r'\b(listed|mentioned|specified|provided|described|documented|stated|detailed|"
    r"enumerated|identified)\b'"
)


def sql_list(items):
    return ", ".join("'" + i.replace("'", "''") + "'" for i in items)


def placeholder_rule(k: str) -> str:
    """Returns the first matching rule name ('P1'..'P4') or NULL."""
    # strip parenthesised segments, unless the whole key is one parenthesis
    k_noparen = (f"CASE WHEN {k} RLIKE r'^\\(.*\\)$' THEN {k} "
                 f"ELSE regexp_replace({k}, r'\\([^)]*\\)', '') END")
    return f"""CASE
      WHEN {k} IN ({sql_list(P1_EXACT)}) THEN 'P1_exact'
      WHEN {k_noparen} RLIKE {P2_META} AND {k_noparen} RLIKE {P2_NEG} THEN 'P2_source_absent'
      WHEN {k} RLIKE {P3} THEN 'P3_not_listed_note'
      WHEN length({k}) <= 150 AND {k} RLIKE {P4_START} AND {k} RLIKE {P4_NOUN}
           AND {k} RLIKE {P4_VERB} THEN 'P4_generic_absence'
      ELSE NULL END"""


# --------------------------------------------------------------------------------------
# Build statements
# --------------------------------------------------------------------------------------

BUILD = [
    # ---------------------------------------------------------------- facilities_clean
    f"""
CREATE OR REPLACE TABLE {FC} AS
WITH d AS (SELECT DISTINCT * FROM {SRC})
SELECT
  unique_id,
  {missing_to_null('name')}                       AS name,
  description,
  {missing_to_null('address_city')}               AS city,
  {missing_to_null('address_stateOrRegion')}      AS state,
  nullif(regexp_replace({missing_to_null('address_zipOrPostcode')}, r'\\s', ''), '') AS postcode,
  coalesce(regexp_replace({missing_to_null('address_zipOrPostcode')}, r'\\s', '')
           RLIKE r'^[1-9][0-9]{{5}}$', false)     AS postcode_valid,
  latitude,
  longitude,
  {int_or_null('numberDoctors')}                  AS numberDoctors,
  {int_or_null('capacity')}                       AS capacity,
  {int_or_null('yearEstablished')}                AS yearEstablished,
  array_sort(array_distinct(filter(
      transform(from_json(specialties, 'array<string>'), x -> trim(x)),
      x -> x IS NOT NULL AND x <> '')))           AS specialties,
  {domain('officialWebsite')}                     AS official_domain,
  {missing_to_null('officialPhone')}              AS official_phone,
  array_sort(array_distinct(filter(
      transform(from_json(source_urls, 'array<string>'), u -> {domain('u')}),
      x -> x IS NOT NULL)))                       AS source_domains,
  facilityTypeId,
  operatorTypeId,
  affiliationTypeIds,
  coalesce(organization_type, '') <> 'facility'   AS is_shifted,
  (latitude IS NULL OR longitude IS NULL)         AS coords_missing,
  coalesce(latitude NOT BETWEEN 6 AND 38 OR longitude NOT BETWEEN 68 AND 98, false)
                                                  AS coords_outside_india,
  coalesce(trim(address_country), '') <> 'India'  AS country_not_india,
  NOT coalesce(unique_id RLIKE {UUID_RE}, false)  AS id_not_uuid
FROM d
""",
    # ---------------------------------------------------------------- facility_sentences
    f"""
CREATE OR REPLACE TABLE {FS} AS
WITH d AS (SELECT DISTINCT unique_id, procedure, capability, equipment FROM {SRC}),
items AS (
  SELECT unique_id, 'procedure' AS source_column, 1 AS col_order, pos AS position, item
  FROM d LATERAL VIEW posexplode(from_json(procedure, 'array<string>')) e AS pos, item
  UNION ALL
  SELECT unique_id, 'capability', 2, pos, item
  FROM d LATERAL VIEW posexplode(from_json(capability, 'array<string>')) e AS pos, item
  UNION ALL
  SELECT unique_id, 'equipment', 3, pos, item
  FROM d LATERAL VIEW posexplode(from_json(equipment, 'array<string>')) e AS pos, item
),
keyed AS (
  SELECT unique_id, source_column, col_order, position,
         trim(item) AS sentence,
         regexp_replace(lower(regexp_replace(trim(item), r'\\s+', ' ')),
                        r'[\\s.,;:!?…]+$', '') AS sentence_key
  FROM items
  WHERE item IS NOT NULL AND trim(item) <> ''
),
flagged AS (
  SELECT *, {placeholder_rule('sentence_key')} AS placeholder_rule
  FROM keyed
  WHERE sentence_key <> ''
)
SELECT unique_id, source_column, position, sentence, sentence_key,
       placeholder_rule IS NOT NULL AS is_placeholder,
       placeholder_rule,
       row_number() OVER (PARTITION BY unique_id, sentence_key
                          ORDER BY col_order, position) > 1 AS is_repeat
FROM flagged
""",
    # ---------------------------------------------------------------- distinct_sentences
    f"""
CREATE OR REPLACE TABLE {DS} AS
WITH s AS (
  SELECT s.unique_id, s.sentence, s.sentence_key
  FROM {FS} s JOIN {FC} f USING (unique_id)
  WHERE NOT s.is_placeholder AND NOT f.is_shifted
),
forms AS (
  SELECT sentence_key, sentence, count(*) AS n,
         row_number() OVER (PARTITION BY sentence_key ORDER BY count(*) DESC, sentence) AS rk
  FROM s GROUP BY sentence_key, sentence
),
agg AS (
  SELECT sentence_key, count(DISTINCT unique_id) AS n_facilities, count(*) AS n_occurrences
  FROM s GROUP BY sentence_key
)
SELECT substr(sha2(a.sentence_key, 256), 1, 16) AS sentence_id,
       a.sentence_key,
       f.sentence AS example_sentence,
       a.n_facilities,
       a.n_occurrences
FROM agg a JOIN forms f ON f.sentence_key = a.sentence_key AND f.rk = 1
""",
]

# --------------------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------------------

TABLE_COMMENTS = {
    FC: (
        "One row per facility (unique_id), mechanically cleaned from the read-only share "
        f"{SRC}. Built by scripts/build_clean_base.py: SELECT DISTINCT * removes the 11 exact "
        "duplicate rows (10,088 -> 10,077); name/city/state/postcode trimmed with '', 'null', "
        "'none' -> NULL; postcode spaces stripped; numberDoctors/capacity/yearEstablished "
        "try_cast to INT (NULL if unparseable, no range check); specialties parsed to a sorted "
        "distinct array; official_domain and source_domains are lowercase hosts without "
        "scheme/www. No content judgement, no LLM. Flags: is_shifted (organization_type <> "
        "'facility', NULL fails; the canonical column-shift test), coords_missing, "
        "coords_outside_india, country_not_india, id_not_uuid, postcode_valid. Filter "
        "downstream with NOT is_shifted."
    ),
    FS: (
        "One row per non-empty item of the procedure, capability and equipment JSON arrays, "
        f"from the deduplicated facilities (one row per unique_id, shifted rows included; "
        f"filter via {FC}.is_shifted). Built by scripts/build_clean_base.py. Items that are "
        "NULL, blank after trim, or whose sentence_key is empty are dropped. Flags: "
        "is_placeholder (rule-based, see placeholder_rule: P1_exact list, P2_source_absent = "
        "mentions the provided content/page AND states absence, P3_not_listed_note = "
        "'(not listed)'/'-- skip' extractor notes, P4_generic_absence = 'no ... procedures/"
        "equipment ... listed/mentioned'); is_repeat (same sentence_key already seen for the "
        "same unique_id, ordered procedure, capability, equipment then position; first "
        "occurrence unflagged)."
    ),
    DS: (
        "One row per distinct sentence_key over workspace.vf.facility_sentences, EXCLUDING "
        "placeholders (is_placeholder) and EXCLUDING sentences of shifted facilities "
        f"({FC}.is_shifted). Repeats within a facility are included in n_occurrences. "
        "sentence_id = first 16 hex chars of sha2(sentence_key, 256) (deterministic, stable "
        "across rebuilds). example_sentence = most frequent original (trimmed) form, ties "
        "broken alphabetically. Built by scripts/build_clean_base.py."
    ),
}

COLUMN_COMMENTS = {
    FC: {
        "unique_id": "Facility id from the source (unique in this table). Not always a UUID; see id_not_uuid.",
        "name": "Source name, trimmed; '', 'null', 'none' -> NULL.",
        "description": "Source description, unchanged.",
        "city": "Source address_city, trimmed; '', 'null', 'none' -> NULL. Unreliable; prefer coordinates.",
        "state": "Source address_stateOrRegion, trimmed; '', 'null', 'none' -> NULL. 254 raw spellings; prefer coordinates.",
        "postcode": "Source address_zipOrPostcode, trimmed, all whitespace removed; '', 'null', 'none' -> NULL.",
        "postcode_valid": "TRUE when postcode is 6 digits with first digit 1-9 (Indian PIN format). FALSE otherwise, including NULL.",
        "latitude": "Source latitude (DOUBLE), unchanged. See coords_missing / coords_outside_india.",
        "longitude": "Source longitude (DOUBLE), unchanged. See coords_missing / coords_outside_india.",
        "numberDoctors": "try_cast(trim(numberDoctors) AS INT); NULL when missing or unparseable. Not range-checked.",
        "capacity": "try_cast(trim(capacity) AS INT); NULL when missing or unparseable. Not range-checked.",
        "yearEstablished": "try_cast(trim(yearEstablished) AS INT); NULL when missing or unparseable. Not range-checked.",
        "specialties": "Source specialties JSON parsed to array<string>, items trimmed, blanks removed, distinct, sorted.",
        "official_domain": "Host of officialWebsite: lowercase, scheme and leading www. stripped, cut at / : ? #. NULL if missing ('', 'null', 'none') or not hostname-shaped.",
        "official_phone": "Source officialPhone, trimmed; '', 'null', 'none' (any case) -> NULL; otherwise the raw value (not parsed or validated; may hold several numbers).",
        "source_domains": "Distinct sorted hosts of the source_urls JSON array, same normalisation as official_domain.",
        "facilityTypeId": "Source facilityTypeId, unchanged.",
        "operatorTypeId": "Source operatorTypeId, unchanged.",
        "affiliationTypeIds": "Source affiliationTypeIds, unchanged.",
        "is_shifted": "Canonical column-shift flag: organization_type <> 'facility' (NULL counts as shifted). Exclude these rows downstream.",
        "coords_missing": "TRUE when latitude or longitude is NULL.",
        "coords_outside_india": "TRUE when coordinates are present but latitude not in [6,38] or longitude not in [68,98].",
        "country_not_india": "TRUE when trimmed address_country is not exactly 'India' (NULL counts as not India).",
        "id_not_uuid": "TRUE when unique_id is not a canonical 8-4-4-4-12 hex UUID.",
    },
    FS: {
        "unique_id": "Facility id; joins to workspace.vf.facilities_clean.unique_id.",
        "source_column": "Source array the item came from: procedure, capability or equipment.",
        "position": "0-based index of the item in its source JSON array (gaps where empty items were dropped).",
        "sentence": "The item text, trimmed (otherwise verbatim).",
        "sentence_key": "Normalised key: lowercase, whitespace runs collapsed to one space, trailing whitespace and . , ; : ! ? … removed.",
        "is_placeholder": "TRUE when the item is a 'nothing listed' placeholder per placeholder_rule. Not a facility claim.",
        "placeholder_rule": "First placeholder rule matched (P1_exact, P2_source_absent, P3_not_listed_note, P4_generic_absence) or NULL. Rules in scripts/build_clean_base.py.",
        "is_repeat": "TRUE when the same sentence_key already occurred for this unique_id earlier (order: procedure, capability, equipment, then position). First occurrence is FALSE.",
    },
    DS: {
        "sentence_id": "Stable id: first 16 hex chars of sha2(sentence_key, 256).",
        "sentence_key": "Normalised sentence key (see workspace.vf.facility_sentences.sentence_key). Unique in this table.",
        "example_sentence": "Most frequent original (trimmed) form of this key; ties broken alphabetically.",
        "n_facilities": "Number of distinct non-shifted facilities with at least one non-placeholder occurrence.",
        "n_occurrences": "Number of non-placeholder rows in facility_sentences for non-shifted facilities with this key (repeats included).",
    },
}


def comment_statements():
    out = []
    for t, c in TABLE_COMMENTS.items():
        out.append(f"COMMENT ON TABLE {t} IS '{c.replace(chr(39), chr(39) * 2)}'")
    for t, cols in COLUMN_COMMENTS.items():
        for col, c in cols.items():
            out.append(f"ALTER TABLE {t} ALTER COLUMN {col} COMMENT '{c.replace(chr(39), chr(39) * 2)}'")
    return out


# --------------------------------------------------------------------------------------
# Report queries
# --------------------------------------------------------------------------------------

REPORT = {
    "row_counts": f"""
SELECT (SELECT count(*) FROM {SRC}) AS src_rows,
       (SELECT count(*) FROM {FC}) AS facilities_clean_rows,
       (SELECT count(DISTINCT unique_id) FROM {FC}) AS facilities_clean_distinct_ids,
       (SELECT count(*) FROM {FS}) AS facility_sentences_rows,
       (SELECT count(*) FROM {DS}) AS distinct_sentences_rows,
       (SELECT count(DISTINCT sentence_id) FROM {DS}) AS distinct_sentence_ids""",
    "shift_tests": f"""
SELECT 'is_shifted' t, count_if(is_shifted) n, count_if(is_shifted) overlap, 0 missed_by_is_shifted FROM {FC}
UNION ALL SELECT 'coords_missing', count_if(coords_missing), count_if(coords_missing AND is_shifted), count_if(coords_missing AND NOT is_shifted) FROM {FC}
UNION ALL SELECT 'coords_outside_india', count_if(coords_outside_india), count_if(coords_outside_india AND is_shifted), count_if(coords_outside_india AND NOT is_shifted) FROM {FC}
UNION ALL SELECT 'country_not_india', count_if(country_not_india), count_if(country_not_india AND is_shifted), count_if(country_not_india AND NOT is_shifted) FROM {FC}
UNION ALL SELECT 'id_not_uuid', count_if(id_not_uuid), count_if(id_not_uuid AND is_shifted), count_if(id_not_uuid AND NOT is_shifted) FROM {FC}
UNION ALL SELECT 'any_extra_test', count_if(coords_missing OR coords_outside_india OR country_not_india OR id_not_uuid),
  count_if((coords_missing OR coords_outside_india OR country_not_india OR id_not_uuid) AND is_shifted),
  count_if((coords_missing OR coords_outside_india OR country_not_india OR id_not_uuid) AND NOT is_shifted) FROM {FC}""",
    "shift_missed_examples": f"""
SELECT f.unique_id, f.name, f.city, s.address_country, f.latitude, f.longitude, s.organization_type,
       f.coords_missing, f.coords_outside_india, f.country_not_india, f.id_not_uuid
FROM {FC} f JOIN (SELECT DISTINCT unique_id, address_country, organization_type FROM {SRC}) s USING (unique_id)
WHERE NOT f.is_shifted AND (f.coords_missing OR f.coords_outside_india OR f.country_not_india OR f.id_not_uuid)
ORDER BY f.coords_outside_india DESC, f.country_not_india DESC, f.id_not_uuid DESC, f.unique_id LIMIT 20""",
    "numeric_parse": f"""
WITH d AS (SELECT DISTINCT * FROM {SRC})
SELECT 'numberDoctors' f, count_if(NOT {is_empty_scalar('numberDoctors')}) non_empty,
       count_if(NOT {is_empty_scalar('numberDoctors')} AND {int_or_null('numberDoctors')} IS NULL) failed,
       count_if(lower(trim(numberDoctors)) = 'null') literal_null,
       min({int_or_null('numberDoctors')}) mn, max({int_or_null('numberDoctors')}) mx, count({int_or_null('numberDoctors')}) parsed FROM d
UNION ALL
SELECT 'capacity', count_if(NOT {is_empty_scalar('capacity')}),
       count_if(NOT {is_empty_scalar('capacity')} AND {int_or_null('capacity')} IS NULL),
       count_if(lower(trim(capacity)) = 'null'),
       min({int_or_null('capacity')}), max({int_or_null('capacity')}), count({int_or_null('capacity')}) FROM d
UNION ALL
SELECT 'yearEstablished', count_if(NOT {is_empty_scalar('yearEstablished')}),
       count_if(NOT {is_empty_scalar('yearEstablished')} AND {int_or_null('yearEstablished')} IS NULL),
       count_if(lower(trim(yearEstablished)) = 'null'),
       min({int_or_null('yearEstablished')}), max({int_or_null('yearEstablished')}), count({int_or_null('yearEstablished')}) FROM d""",
    "numeric_fail_by_shift": f"""
WITH d AS (SELECT DISTINCT * FROM {SRC})
SELECT coalesce(organization_type,'') <> 'facility' shifted,
  count_if(NOT {is_empty_scalar('numberDoctors')} AND {int_or_null('numberDoctors')} IS NULL) nd_fail,
  count_if(NOT {is_empty_scalar('capacity')} AND {int_or_null('capacity')} IS NULL) cap_fail,
  count_if(NOT {is_empty_scalar('yearEstablished')} AND {int_or_null('yearEstablished')} IS NULL) yr_fail
FROM d GROUP BY 1""",
    "field_stats": f"""
SELECT count_if(postcode_valid) postcode_valid, count_if(postcode IS NOT NULL AND NOT postcode_valid) postcode_invalid,
       count_if(postcode IS NULL) postcode_null,
       count_if(official_domain IS NOT NULL) has_official_domain,
       count_if(size(source_domains) > 0) has_source_domains,
       count_if(specialties IS NOT NULL AND size(specialties) > 0) has_specialties,
       count_if(name IS NULL) name_null, count_if(city IS NULL) city_null, count_if(state IS NULL) state_null
FROM {FC}""",
    "website_not_hostname": f"""
WITH d AS (SELECT DISTINCT * FROM {SRC})
SELECT count_if(NOT {is_empty_scalar('officialWebsite')}) website_non_empty,
       count_if(NOT {is_empty_scalar('officialWebsite')} AND {domain('officialWebsite')} IS NULL) website_unparsed
FROM d""",
    "items_total": f"""
WITH d AS (SELECT DISTINCT unique_id, procedure, capability, equipment FROM {SRC}),
a AS (SELECT 'procedure' c, from_json(procedure,'array<string>') a FROM d UNION ALL
      SELECT 'capability', from_json(capability,'array<string>') FROM d UNION ALL
      SELECT 'equipment', from_json(equipment,'array<string>') FROM d),
i AS (SELECT c, item FROM a LATERAL VIEW explode(a) e AS item)
SELECT c, count(*) total_items,
       count_if(item IS NULL OR trim(item) = '') dropped_blank,
       count_if(item IS NOT NULL AND trim(item) <> '' AND
                regexp_replace(lower(regexp_replace(trim(item), r'\\s+', ' ')), r'[\\s.,;:!?…]+$', '') = '') dropped_punct_only
FROM i GROUP BY ROLLUP(c) ORDER BY c""",
    "sentence_flags": f"""
SELECT coalesce(source_column,'ALL') source_column, count(*) rows_kept, count_if(is_placeholder) placeholder,
       count_if(is_repeat) repeat, count_if(is_placeholder AND is_repeat) both,
       count_if(f.is_shifted) from_shifted,
       count_if(NOT is_placeholder AND NOT is_repeat AND NOT f.is_shifted) usable
FROM {FS} s JOIN {FC} f USING (unique_id) GROUP BY ROLLUP(source_column) ORDER BY 1""",
    "placeholder_by_rule": f"""
SELECT placeholder_rule, count(*) n, count(DISTINCT sentence_key) distinct_keys
FROM {FS} WHERE is_placeholder GROUP BY 1 ORDER BY 1""",
    "top20_placeholders": f"""
SELECT sentence_key, placeholder_rule, count(*) n FROM {FS} WHERE is_placeholder
GROUP BY 1, 2 ORDER BY n DESC, sentence_key LIMIT 20""",
    "top30_sentences": f"""
SELECT example_sentence, n_facilities, n_occurrences FROM {DS}
ORDER BY n_facilities DESC, n_occurrences DESC, sentence_key LIMIT 30""",
    "zero_usable": f"""
SELECT count_if(NOT f.is_shifted) non_shifted_facilities,
       count_if(NOT f.is_shifted AND coalesce(u.n, 0) = 0) zero_usable_non_shifted,
       count_if(NOT f.is_shifted AND coalesce(a.n, 0) = 0) zero_items_at_all_non_shifted
FROM {FC} f
LEFT JOIN (SELECT unique_id, count(*) n FROM {FS} WHERE NOT is_placeholder AND NOT is_repeat GROUP BY 1) u USING (unique_id)
LEFT JOIN (SELECT unique_id, count(*) n FROM {FS} GROUP BY 1) a USING (unique_id)""",
    "check_occurrences": f"""
SELECT (SELECT sum(n_occurrences) FROM {DS}) sum_occurrences,
       (SELECT count(*) FROM {FS} s JOIN {FC} f USING (unique_id) WHERE NOT s.is_placeholder AND NOT f.is_shifted) expected""",
}


def token() -> str:
    raw = subprocess.check_output(["databricks", "auth", "token", "-p", PROFILE])
    return json.loads(raw)["access_token"]


OFFICIAL_PHONE_COMMENT = "Source officialPhone, trimmed; '', 'null', 'none' (any case) -> NULL; otherwise the raw value (not parsed or validated; may hold several numbers)."


def add_phone(cur):
    """Add official_phone to the existing facilities_clean in place (no recreate; other
    columns and flags untouched): ADD COLUMN if missing, then MERGE from the source share."""
    cur.execute(f"DESCRIBE TABLE {FC}")
    if "official_phone" not in {r[0] for r in cur.fetchall()}:
        cur.execute(f"ALTER TABLE {FC} ADD COLUMN official_phone STRING")
    # the 11 duplicated ids are exact duplicate rows, so max() picks their single value
    cur.execute(f"""MERGE INTO {FC} t
USING (SELECT unique_id, max({missing_to_null('officialPhone')}) AS official_phone
       FROM {SRC} GROUP BY unique_id) s
ON t.unique_id = s.unique_id
WHEN MATCHED THEN UPDATE SET t.official_phone = s.official_phone""")
    cur.execute(f"ALTER TABLE {FC} ALTER COLUMN official_phone COMMENT '{OFFICIAL_PHONE_COMMENT.replace(chr(39), chr(92) + chr(39))}'")
    cur.execute(f"SELECT count(*), count(official_phone) FROM {FC}")
    print("facilities_clean rows, with official_phone:", cur.fetchall(), flush=True)


def main():
    report_only = len(sys.argv) > 1 and sys.argv[1] == "report"
    with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token()) as conn:
        cur = conn.cursor()
        if len(sys.argv) > 1 and sys.argv[1] == "add_phone":
            add_phone(cur)
            return
        if not report_only:
            for stmt in BUILD:
                print("RUN:", stmt.strip().splitlines()[0], flush=True)
                cur.execute(stmt)
            for stmt in comment_statements():
                cur.execute(stmt)
            print("comments applied", flush=True)
        for name, q in REPORT.items():
            cur.execute(q)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            print(f"\n== {name}")
            print(" | ".join(cols))
            for r in rows:
                print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()

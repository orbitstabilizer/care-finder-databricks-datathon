"""Build the NFHS-5 district context tables in workspace.vf (no LLM calls).

  workspace.vf.nfhs_district          one row per NFHS-5 district: 58 clean DOUBLE indicators,
                                      rank (1..706) and quartile for every indicator in the strip
  workspace.vf.district_alias         hand-written PIN-directory district -> NFHS district (renames,
                                      spelling, and districts created after the survey -> parent)
  workspace.vf.pin_district           pin x district with pin_share and the NFHS key
  workspace.vf.facility_district      non-shifted facility -> district via its postcode (majority district)
  workspace.vf.service_indicator_map  six headline services -> 0-3 NFHS indicators

Reads the NFHS and PIN tables from the read-only dataset share; facilities from facilities_clean.
Run:  /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/build_nfhs.py
Method notes: reports/nfhs_proposal.md sections 3-5.
"""
import json
import subprocess

from databricks import sql

SHARE = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset"
NFHS = f"{SHARE}.nfhs_5_district_health_indicators"
PIN = f"{SHARE}.india_post_pincode_directory"

# Normalisation, identical on both sides: lowercase, '&' -> 'and', drop non-letters.
def norm_sql(col):
    return f"regexp_replace(replace(lower(trim({col})), '&', 'and'), '[^a-z]', '')"

# State fixes (normalised form -> canonical normalised form)
STATE_FIX = {
    "maharastra": "maharashtra",
    "nctofdelhi": "delhi",
    "thedadraandnagarhavelianddamananddiu": "dadraandnagarhavelianddamananddiu",
}

def state_sql(col):
    expr = norm_sql(col)
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in STATE_FIX.items())
    return f"(CASE {expr} {cases} ELSE {expr} END)"

# ---------------------------------------------------------------------------------------------
# Alias table: (state, pin-directory district, NFHS district, note), all as normalised keys.
# 'rename' = same territory, new/other spelling. 'new' = carved out after NFHS-5 (2019 boundaries),
# mapped to the parent district that held most of it; the parent's value is shown, and must be
# labelled as such. Ordered roughly by number of facilities we hold in the PIN district.
ALIASES = [
    ("karnataka", "bengaluruurban", "bangalore", "rename"),
    ("haryana", "gurugram", "gurgaon", "rename"),
    ("westbengal", "paraganasnorth", "northtwentyfourpargana", "rename"),
    ("andhrapradesh", "ntr", "krishna", "new 2022, carved from Krishna (Vijayawada)"),
    ("uttarpradesh", "prayagraj", "allahabad", "rename"),
    ("maharashtra", "raigad", "raigarh", "spelling (NFHS lists Maharashtra's Raigad as Raigarh)"),
    ("andhrapradesh", "visakhapatanam", "visakhapatnam", "spelling"),
    ("assam", "kamrupmetro", "kamrupmetropolitan", "spelling"),
    ("westbengal", "darjeeling", "darjiling", "spelling"),
    ("punjab", "sasnagar", "sahibzadaajitsinghnagar", "abbreviation (SAS Nagar / Mohali)"),
    ("tamilnadu", "chengalpattu", "kancheepuram", "new 2019, carved from Kancheepuram"),
    ("westbengal", "howrah", "haora", "spelling"),
    ("westbengal", "paschimbardhaman", "paschimbarddhaman", "spelling"),
    ("jharkhand", "eastsinghbum", "purbisinghbhum", "rename (East Singhbhum = Purbi Singhbhum)"),
    ("karnataka", "belagavi", "belgaum", "rename"),
    ("maharashtra", "ahmednagar", "ahmadnagar", "spelling"),
    ("westbengal", "hooghly", "hugli", "spelling"),
    ("uttarakhand", "haridwar", "hardwar", "spelling"),
    ("karnataka", "mysuru", "mysore", "rename"),
    ("karnataka", "shivamogga", "shimoga", "rename"),
    ("telangana", "hanumakonda", "warangalurban", "rename 2021 (Warangal Urban -> Hanumakonda)"),
    ("westbengal", "paraganassouth", "southtwentyfourpargana", "rename"),
    ("karnataka", "tumakuru", "tumkur", "rename"),
    ("westbengal", "medinipurwest", "paschimmedinipur", "rename"),
    ("puducherry", "pondicherry", "puducherry", "rename"),
    ("andhrapradesh", "spsrnellore", "sripottisriramulunello", "abbreviation (SPSR Nellore)"),
    ("uttarakhand", "udamsinghnagar", "udhamsinghnagar", "spelling"),
    ("karnataka", "davangere", "davanagere", "spelling"),
    ("karnataka", "ballari", "bellary", "rename"),
    ("karnataka", "bengalururural", "bangalorerural", "rename"),
    ("bihar", "purbichamparan", "purbachamparan", "spelling"),
    ("tamilnadu", "tuticorin", "thoothukkudi", "rename"),
    ("andhrapradesh", "tirupati", "chittoor", "new 2022, carved from Chittoor"),
    ("rajasthan", "jhunjhunu", "jhunjhunun", "spelling"),
    ("punjab", "srimuktsarsahib", "muktsar", "rename"),
    ("tamilnadu", "tenkasi", "tirunelveli", "new 2019, carved from Tirunelveli"),
    ("uttarpradesh", "ayodhya", "faizabad", "rename"),
    ("maharashtra", "buldhana", "buldana", "spelling"),
    ("karnataka", "kalaburagi", "gulbarga", "rename"),
    ("maharashtra", "beed", "bid", "spelling"),
    ("andhrapradesh", "eluru", "westgodavari", "new 2022, carved from West Godavari"),
    ("gujarat", "arvalli", "aravali", "spelling"),
    ("tamilnadu", "villupuram", "viluppuram", "spelling"),
    ("punjab", "malerkotla", "sangrur", "new 2021, carved from Sangrur"),
    ("westbengal", "medinipureast", "purbamedinipur", "rename"),
    ("andhrapradesh", "annamayya", "ysr", "new 2022, carved mainly from YSR Kadapa"),
    ("karnataka", "chikkamagaluru", "chikmagalur", "rename"),
    ("tamilnadu", "ranipet", "vellore", "new 2019, carved from Vellore"),
    ("punjab", "firozepur", "firozpur", "spelling"),
    ("westbengal", "coochbehar", "kochbihar", "spelling"),
    ("andhrapradesh", "bapatla", "guntur", "new 2022, carved mainly from Guntur"),
    ("tamilnadu", "kanchipuram", "kancheepuram", "spelling"),
    ("westbengal", "purulia", "puruliya", "spelling"),
    ("andhrapradesh", "palnadu", "guntur", "new 2022, carved from Guntur"),
    ("haryana", "charkidadri", "charkhidadri", "spelling"),
    ("andhrapradesh", "kakinada", "eastgodavari", "new 2022, carved from East Godavari"),
    ("jammuandkashmir", "budgam", "badgam", "spelling"),
    ("uttarpradesh", "bhadohi", "santravidasnagarbhadohi", "rename"),
    ("rajasthan", "jalore", "jalor", "spelling"),
    ("madhyapradesh", "khargone", "khargonewestnimar", "rename"),
    ("maharashtra", "gondia", "gondiya", "spelling"),
    ("tamilnadu", "kallakurichi", "viluppuram", "new 2019, carved from Viluppuram"),
    ("andhrapradesh", "srisathyasai", "anantapur", "new 2022, carved from Anantapur"),
    ("karnataka", "vijayapura", "bijapur", "rename"),
    ("andhrapradesh", "nandyal", "kurnool", "new 2022, carved from Kurnool"),
    ("madhyapradesh", "eastnimar", "khandwaeastnimar", "rename"),
    ("westbengal", "dinajpuruttar", "uttardinajpur", "rename"),
    ("tamilnadu", "tirupathur", "vellore", "new 2019, carved from Vellore"),
    ("andhrapradesh", "anakapalli", "visakhapatnam", "new 2022, carved from Visakhapatnam"),
    ("uttarpradesh", "kasganj", "kanshiramnagar", "rename"),
    ("andamanandnicobarislands", "southandamans", "southandaman", "spelling"),
    ("jammuandkashmir", "baramulla", "baramula", "spelling"),
    ("chhattisgarh", "kabirdham", "kabeerdham", "spelling"),
    ("uttarpradesh", "amroha", "jyotibaphulenagar", "rename"),
    ("rajasthan", "chittorgarh", "chittaurgarh", "spelling"),
    ("uttarpradesh", "maharajganj", "mahrajganj", "spelling"),
    ("tamilnadu", "mayiladuthurai", "nagapattinam", "new 2020, carved from Nagapattinam"),
    ("andhrapradesh", "konaseema", "eastgodavari", "new 2022, carved from East Godavari"),
    ("jharkhand", "koderma", "kodarma", "spelling"),
    ("karnataka", "vijaynagar", "bellary", "new 2020 (Vijayanagara), carved from Bellary"),
    ("odisha", "nabarangpur", "nabarangapur", "spelling"),
    ("gujarat", "chhotaudepur", "chhotaudaipur", "spelling"),
    ("uttarpradesh", "santkabeernagar", "santkabirnagar", "spelling"),
    ("westbengal", "kalimpong", "darjiling", "new 2017, carved from Darjiling"),
    ("chhattisgarh", "korea", "koriya", "spelling"),
    ("andhrapradesh", "parvathipurammanyam", "vizianagaram", "new 2022, carved mainly from Vizianagaram"),
    ("assam", "marigaon", "morigaon", "spelling"),
    ("madhyapradesh", "narsinghpur", "narsimhapur", "spelling"),
    ("uttarpradesh", "hathras", "mahamayanagar", "rename"),
    ("karnataka", "chamarajanagara", "chamarajanagar", "spelling"),
    # NFHS districts with no facility today but a PIN-side spelling difference
    ("haryana", "nuh", "mewat", "rename"),
    ("jammuandkashmir", "poonch", "punch", "spelling"),
    ("jammuandkashmir", "shopian", "shupiyan", "spelling"),
    ("jammuandkashmir", "bandipora", "bandipore", "spelling"),
    ("jharkhand", "sahebganj", "sahibganj", "spelling"),
    ("jharkhand", "westsinghbhum", "pashchimisinghbhum", "rename"),
    ("gujarat", "dangs", "thedangs", "spelling"),
    ("chhattisgarh", "kondagaon", "kodagaon", "spelling"),
    ("chhattisgarh", "kanker", "uttarbastarkanker", "rename"),
    ("odisha", "boudh", "baudh", "spelling"),
    ("odisha", "deogarh", "debagarh", "spelling"),
    ("odisha", "sonepur", "subarnapur", "rename"),
    ("rajasthan", "dholpur", "dhaulpur", "spelling"),
    ("telangana", "kumurambheemasifabad", "komarambheemasifabad", "spelling"),
    ("telangana", "warangal", "warangalrural", "rename 2021 (Warangal Rural -> Warangal)"),
    ("uttarakhand", "paurigarhwal", "garhwal", "rename"),
    ("uttarpradesh", "shravasti", "shrawasti", "spelling"),
    ("westbengal", "dinajpurdakshin", "dakshindinajpur", "rename"),
    ("westbengal", "alipurduar", "jalpaiguri", "new 2014, carved from Jalpaiguri"),
    ("westbengal", "jhargram", "paschimmedinipur", "new 2017, carved from Paschim Medinipur"),
    ("meghalaya", "eastjaintiahills", "eastjantiahills", "spelling"),
]
# Not aliased: West Bengal 'Purba Bardhaman' (absent from this 706-row NFHS table), and
# Mizoram 'Chandel' (a duplicate Manipur row in the NFHS table).

# ---------------------------------------------------------------------------------------------
# Service -> indicator map. direction: 'higher_is_worse' (rank 1 = highest value) or
# 'lower_is_worse' (rank 1 = lowest value). indicator_column NULL = deliberately no indicator.
SERVICE_MAP = [
    ("dialysis", "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
     "Men 15+ with high blood sugar or on medication for it", "higher_is_worse",
     "Diabetes is the leading cause of kidney failure; a risk factor years upstream, not dialysis demand."),
    ("dialysis", "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
     "Women 15+ with high blood sugar or on medication for it", "higher_is_worse",
     "Same diabetes risk factor for women; risk factor for kidney disease, not a patient count."),
    ("dialysis", "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
     "Men 15+ with high blood pressure or on medication for it", "higher_is_worse",
     "Hypertension is the second main cause of kidney failure; risk factor only."),
    ("caesarean_section", "births_delivered_by_csection_5y_pct",
     "Births delivered by caesarean section (last 5 years)", "lower_is_worse",
     "Direct measure of C-section use; very low (<5%) suggests unmet need, very high suggests over-use, so show the number without a good/bad label. Rank 1 = lowest rate."),
    ("caesarean_section", "institutional_birth_5y_pct",
     "Births in a health facility (last 5 years)", "lower_is_worse",
     "A C-section needs a facility birth; a low share means many births happen where surgery is not available."),
    ("nicu", "institutional_birth_5y_pct",
     "Births in a health facility (last 5 years)", "lower_is_worse",
     "Newborns born at home cannot reach neonatal care quickly; risk context, not NICU demand."),
    ("nicu", "births_attended_by_skilled_hp_5y_10_pct",
     "Births attended by a skilled health worker (last 5 years)", "lower_is_worse",
     "Unattended births raise the risk of newborn complications going unrecognised; risk context only."),
    ("nicu", "all_w15_49_who_are_anaemic_pct",
     "Women 15-49 who are anaemic", "higher_is_worse",
     "Maternal anaemia is linked to preterm birth and low birth weight, the main reasons for NICU care; risk factor only."),
    ("cardiac_surgery", "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
     "Men 15+ with high blood pressure or on medication for it", "higher_is_worse",
     "Hypertension is a major risk factor for heart disease; years upstream of surgery."),
    ("cardiac_surgery", "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
     "Men 15+ with high blood sugar or on medication for it", "higher_is_worse",
     "Diabetes is a major risk factor for coronary artery disease; risk factor only."),
    ("cardiac_surgery", "m15_plus_who_use_any_kind_of_tobacco_pct",
     "Men 15+ who use any kind of tobacco", "higher_is_worse",
     "Tobacco use is a major risk factor for coronary artery disease; risk factor only."),
    ("mri", None, None, None,
     "No defensible population indicator: MRI need is not measured by NFHS-5. Show no district context."),
    ("burn_care", None, None, None,
     "No defensible population indicator. Unclean cooking fuel is a plausible burn-risk proxy, but too indirect to show; show no district context."),
]

UNITS = {}  # every mapped indicator is a percentage; set in SQL as '%'


def connect():
    tok = json.loads(subprocess.check_output(["databricks", "auth", "token", "-p", "datathon"]))["access_token"]
    return sql.connect(server_hostname="dbc-70851148-db1d.cloud.databricks.com",
                       http_path="/sql/1.0/warehouses/8ea2282aca435351", access_token=tok)


def q(cur, stmt):
    cur.execute(stmt)
    try:
        return cur.fetchall()
    except Exception:
        return None


def esc(s):
    return "NULL" if s is None else "'" + s.replace("'", "''") + "'"


def main():
    con = connect()
    cur = con.cursor()

    # ---- nfhs_district --------------------------------------------------------------------
    cols = q(cur, f"""SELECT column_name, data_type FROM {SHARE.split('.')[0]}.information_schema.columns
                     WHERE table_schema='{SHARE.split('.')[1]}' AND table_name='nfhs_5_district_health_indicators'
                     ORDER BY ordinal_position""")
    dbl = [c for c, t in cols if t == "DOUBLE"]
    assert len(dbl) == 58, len(dbl)
    mapped = sorted({(r[1], r[3]) for r in SERVICE_MAP if r[1]})
    for c, _ in mapped:
        assert c in dbl, c
    rank_cols = []
    for c, d in mapped:
        order = "DESC" if d == "higher_is_worse" else "ASC"
        rank_cols.append(f"CAST(rank() OVER (ORDER BY {c} {order}) AS INT) AS rank_{c}")
        rank_cols.append(f"CAST(ntile(4) OVER (ORDER BY {c} {order}) AS INT) AS quartile_{c}")
    q(cur, f"""CREATE OR REPLACE TABLE workspace.vf.nfhs_district AS
      SELECT concat({state_sql('state_ut')}, '|', {norm_sql('district_name')}) AS nfhs_key,
             trim(district_name) AS district, trim(state_ut) AS state,
             {', '.join(dbl)},
             {', '.join(rank_cols)}
      FROM {NFHS}""")

    # ---- district_alias -------------------------------------------------------------------
    vals = ",\n".join(f"({esc(s)},{esc(p)},{esc(n)},{esc(note)})" for s, p, n, note in ALIASES)
    q(cur, f"""CREATE OR REPLACE TEMPORARY VIEW alias_raw AS
      SELECT * FROM VALUES {vals} AS t(state_key, pin_key, nfhs_district_key, note)""")
    # resolve keys to display names; refuse aliases whose keys do not exist on both sides
    q(cur, f"""CREATE OR REPLACE TEMPORARY VIEW pin_names AS
      SELECT {state_sql('statename')} AS state_key, {norm_sql('district')} AS pin_key,
             max(trim(district)) AS pin_district_name, max(trim(statename)) AS pin_state
      FROM {PIN} GROUP BY 1, 2""")
    bad = q(cur, """SELECT a.state_key, a.pin_key, a.nfhs_district_key,
                          p.pin_key IS NULL AS pin_missing, n.nfhs_key IS NULL AS nfhs_missing,
                          e.nfhs_key IS NOT NULL AS pin_already_exact
                   FROM alias_raw a
                   LEFT JOIN pin_names p USING (state_key, pin_key)
                   LEFT JOIN workspace.vf.nfhs_district n ON n.nfhs_key = a.state_key || '|' || a.nfhs_district_key
                   LEFT JOIN workspace.vf.nfhs_district e ON e.nfhs_key = a.state_key || '|' || a.pin_key
                   WHERE p.pin_key IS NULL OR n.nfhs_key IS NULL OR e.nfhs_key IS NOT NULL""")
    for b in bad:
        print("alias dropped:", b)
    q(cur, """CREATE OR REPLACE TABLE workspace.vf.district_alias AS
      SELECT p.pin_district_name, p.pin_state, n.district AS nfhs_district, n.state AS nfhs_state,
             n.nfhs_key, a.state_key || '|' || a.pin_key AS pin_key, a.note
      FROM alias_raw a
      JOIN pin_names p USING (state_key, pin_key)
      JOIN workspace.vf.nfhs_district n ON n.nfhs_key = a.state_key || '|' || a.nfhs_district_key
      LEFT JOIN workspace.vf.nfhs_district e ON e.nfhs_key = a.state_key || '|' || a.pin_key
      WHERE e.nfhs_key IS NULL""")

    # ---- pin_district ---------------------------------------------------------------------
    q(cur, f"""CREATE OR REPLACE TABLE workspace.vf.pin_district AS
      WITH po AS (
        SELECT lpad(CAST(pincode AS STRING), 6, '0') AS pin, trim(district) AS district, trim(statename) AS state,
               concat({state_sql('statename')}, '|', {norm_sql('district')}) AS pin_key
        FROM {PIN} WHERE upper(trim(statename)) <> 'NA' AND pincode IS NOT NULL),
      g AS (
        SELECT pin, pin_key, max(district) AS district, max(state) AS state, count(*) AS n_offices
        FROM po GROUP BY pin, pin_key),
      s AS (
        SELECT *, n_offices / sum(n_offices) OVER (PARTITION BY pin) AS pin_share,
               row_number() OVER (PARTITION BY pin ORDER BY n_offices DESC, pin_key) AS share_rank
        FROM g)
      SELECT s.pin, s.district, s.state, s.pin_key, CAST(s.n_offices AS INT) AS n_offices,
             ROUND(s.pin_share, 4) AS pin_share, s.share_rank = 1 AS is_primary,
             coalesce(e.nfhs_key, a.nfhs_key) AS nfhs_key,
             CASE WHEN e.nfhs_key IS NOT NULL THEN 'exact' WHEN a.nfhs_key IS NOT NULL THEN 'alias' END AS match_method
      FROM s
      LEFT JOIN workspace.vf.nfhs_district e ON e.nfhs_key = s.pin_key
      LEFT JOIN workspace.vf.district_alias a ON a.pin_key = s.pin_key""")

    # ---- facility_district ----------------------------------------------------------------
    q(cur, """CREATE OR REPLACE TABLE workspace.vf.facility_district AS
      SELECT f.unique_id, f.postcode AS pin, p.district, p.state, p.pin_key, p.pin_share,
             p.nfhs_key, p.match_method
      FROM workspace.vf.facilities_clean f
      LEFT JOIN workspace.vf.pin_district p ON p.pin = f.postcode AND p.is_primary AND f.postcode_valid
      WHERE NOT f.is_shifted""")

    # ---- service_indicator_map ------------------------------------------------------------
    vals = ",\n".join(
        f"({esc(s)},{esc(c)},{esc(l)},{esc(d)},{esc(r)},{esc('%' if c else None)})"
        for s, c, l, d, r in SERVICE_MAP)
    q(cur, f"""CREATE OR REPLACE TABLE workspace.vf.service_indicator_map AS
      SELECT * FROM VALUES {vals} AS t(service, indicator_column, label_for_users, direction, reason, unit)""")

    comments(cur, dbl, mapped)
    report(cur)


def comments(cur, dbl, mapped):
    c = lambda t, s: q(cur, f"COMMENT ON TABLE workspace.vf.{t} IS {esc(s)}")
    col = lambda t, k, s: q(cur, f"ALTER TABLE workspace.vf.{t} ALTER COLUMN {k} COMMENT {esc(s)}")
    c("nfhs_district", "NFHS-5 (2019-21) district indicators, one row per NFHS row (706). The 58 DOUBLE columns of the "
      "share table copied as-is (no suppressed values). rank_<col>: 1..706, 1 = highest burden (ties share a rank); "
      "quartile_<col>: 1 = highest-burden quarter. Direction per indicator is in service_indicator_map.direction: "
      "higher_is_worse ranks the highest value 1; lower_is_worse ranks the lowest value 1. Context about population "
      "need only; never use for facility tier or ranking. Built by scripts/build_nfhs.py.")
    col("nfhs_district", "nfhs_key", "state|district, both lowercased, & -> and, non-letters dropped; state spellings fixed (Maharastra, NCT of Delhi). Key is never district alone (8 names occur in two states).")
    col("nfhs_district", "district", "NFHS district name, trimmed")
    col("nfhs_district", "state", "NFHS state/UT name as in the source (incl. its spelling 'Maharastra')")
    for k, d in mapped:
        w = "highest value" if d == "higher_is_worse" else "lowest value"
        col("nfhs_district", f"rank_{k}", f"Rank of {k} out of 706, 1 = {w} ({d}). Ties share a rank.")
        col("nfhs_district", f"quartile_{k}", f"Quartile of {k}, 1 = quarter with the {w} ({d}).")
    c("district_alias", "Hand-written aliases from India Post PIN-directory district names to NFHS-5 districts: renames, "
      "spellings, and districts created after the survey mapped to their parent (note says 'new YYYY, carved from X'; "
      "show the parent's value and say so). Only for PIN districts with no exact NFHS match. Built by scripts/build_nfhs.py.")
    col("district_alias", "pin_district_name", "District name as in the PIN directory")
    col("district_alias", "pin_state", "State name as in the PIN directory")
    col("district_alias", "nfhs_district", "NFHS district it maps to")
    col("district_alias", "nfhs_state", "NFHS state")
    col("district_alias", "nfhs_key", "Join key to nfhs_district")
    col("district_alias", "pin_key", "Normalised state|district of the PIN-directory name (join key to pin_district.pin_key)")
    col("district_alias", "note", "rename / spelling / new district with its parent")
    c("pin_district", "One row per (PIN, district) from the India Post directory (grain there is post office). pin_share = "
      "share of the PIN's post offices in that district; is_primary marks the majority district per PIN. nfhs_key via "
      "exact normalised name or district_alias. Built by scripts/build_nfhs.py.")
    col("pin_district", "pin", "6-digit PIN code as string")
    col("pin_district", "district", "PIN-directory district name")
    col("pin_district", "state", "PIN-directory state name")
    col("pin_district", "pin_key", "Normalised state|district")
    col("pin_district", "n_offices", "Post offices of this PIN in this district")
    col("pin_district", "pin_share", "n_offices / all post offices of the PIN")
    col("pin_district", "is_primary", "True for the district with most of the PIN's post offices (one per PIN)")
    col("pin_district", "nfhs_key", "Join key to nfhs_district; NULL if no exact or alias match")
    col("pin_district", "match_method", "'exact' | 'alias' | NULL")
    c("facility_district", "Non-shifted facilities (facilities_clean) -> district of their postcode (primary district of "
      "the PIN). NULL district when the postcode is invalid or not in the PIN directory. Built by scripts/build_nfhs.py.")
    col("facility_district", "unique_id", "Joins facilities_clean")
    col("facility_district", "pin", "facilities_clean.postcode")
    col("facility_district", "pin_share", "Share of the PIN's post offices in this district (below 1 = PIN spans districts)")
    col("facility_district", "nfhs_key", "Join key to nfhs_district; NULL if not linked")
    col("facility_district", "match_method", "'exact' | 'alias' | NULL")
    c("service_indicator_map", "Hand mapping of six headline services to 0-3 clean NFHS-5 indicators with a reason. A row "
      "with NULL indicator_column means deliberately no indicator (show no district context). Indicators are risk or "
      "use context, never service demand. Built by scripts/build_nfhs.py.")
    col("service_indicator_map", "indicator_column", "Column in nfhs_district (rank_/quartile_ prefixed columns hold its rank)")
    col("service_indicator_map", "direction", "higher_is_worse (rank 1 = highest value) or lower_is_worse (rank 1 = lowest value)")
    col("service_indicator_map", "unit", "Unit of the value")


def report(cur):
    for t in ["nfhs_district", "district_alias", "pin_district", "facility_district", "service_indicator_map"]:
        print(t, q(cur, f"SELECT count(*) FROM workspace.vf.{t}")[0][0])
    print(q(cur, """SELECT count(*) n, count(district) with_district, count(nfhs_key) linked,
                         count_if(match_method='exact') exact, count_if(match_method='alias') alias,
                         count(DISTINCT nfhs_key) nfhs_districts
                  FROM workspace.vf.facility_district"""))
    print("top unlinked:", q(cur, """SELECT state, district, count(*) n FROM workspace.vf.facility_district
                  WHERE district IS NOT NULL AND nfhs_key IS NULL GROUP BY 1,2 ORDER BY n DESC LIMIT 10"""))


if __name__ == "__main__":
    main()

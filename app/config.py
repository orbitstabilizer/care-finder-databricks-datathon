"""Single source of truth for schema, table and constant names."""
import os

# --- where the data lives -------------------------------------------------
SHARE_CATALOG  = os.getenv("VF_SHARE_CATALOG",  "databricks_virtue_foundation_dataset_dais_2026")
SHARE_SCHEMA   = os.getenv("VF_SHARE_SCHEMA",   "virtue_foundation_dataset")
TARGET_CATALOG = os.getenv("VF_TARGET_CATALOG", "workspace")
TARGET_SCHEMA  = os.getenv("VF_TARGET_SCHEMA",  "vf")

SRC = f"{SHARE_CATALOG}.{SHARE_SCHEMA}"
TGT = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"

T_FACILITIES = f"{SRC}.facilities"
T_PINCODE    = f"{SRC}.india_post_pincode_directory"
T_PIN_POINT  = f"{TGT}.pin_point"
T_CITY_POINT = f"{TGT}.city_point"
T_FAC_LOC    = f"{TGT}.facility_location"
F_HAVERSINE  = f"{TGT}.haversine_km"

# --- constants ------------------------------------------------------------
NEAR_KM             = 50.0
PIN_TIGHT_KM        = 25.0
PREFIX_OUTLIER_KM   = 100.0
MIN_CITY_FACILITIES = 5
LAT_MIN, LAT_MAX    = 6.0, 38.0
LON_MIN, LON_MAX    = 68.0, 98.0

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "8ea2282aca435351")

def subs() -> dict:
    """Values available to sql/*.sql as {placeholders}."""
    return {k: v for k, v in globals().items() if k.isupper()}

# --- service search (contract table filled later by the verdict job) -------
T_FAC_CLEAN      = f"{TGT}.facilities_clean"
T_SERVICE        = f"{TGT}.facility_service"         # real verdicts; empty until filled
T_SERVICE_SAMPLE = f"{TGT}.facility_service_sample"  # 200 marked sample rows
T_BUILD_STATS    = f"{TGT}.build_stats"              # funnel numbers, rewritten each build
TIER_ORDER       = ["Confirmed", "Likely", "Possible", "Unverified"]
# The 8 services whose tiers were checked first (keyword-tier services). Other
# services show a "results still loading" note while tagging is incomplete.
APP_SERVICES     = ["dialysis", "caesarean_section", "nicu", "cardiac_surgery", "mri",
                    "burn_care", "icu_critical_care", "trauma_emergency"]
N_DISTINCT_SENTENCES = 271_262   # workspace.vf.distinct_sentences rows (coverage denominator)
HIDDEN_SERVICES  = {"other_clinical"}
WEAK_LOCATION    = ("suspect", "approximate", "unverified")
# Shown first in the dropdown, ONLY under "Common searches" (not repeated in their group).
COMMON_SEARCHES  = ["dialysis", "caesarean_section", "nicu", "cardiac_surgery", "mri", "burn_care"]
DEFAULT_SERVICE  = "dialysis"

# Dropdown: group -> [(service label, readable name)], in display order.
# Every label in facility_service except HIDDEN_SERVICES is offered as "<Group> / <Name>";
# a label missing here falls into "Other specialties" under a generated name.
SERVICE_GROUPS = {
    "Emergency and critical care": [
        ("trauma_emergency", "Emergency and trauma"),
        ("icu_critical_care", "ICU / critical care"),
        ("ventilator_support", "Ventilator support"),
        ("burn_care", "Burn care"),
        ("stroke_care", "Stroke care"),
        ("ambulance", "Ambulance"),
        ("blood_bank", "Blood bank"),
    ],
    "Maternity and newborn": [
        ("caesarean_section", "C-section"),
        ("normal_delivery", "Normal delivery"),
        ("obstetrics_maternity", "Maternity / obstetrics"),
        ("high_risk_obstetrics", "High-risk pregnancy care"),
        ("nicu", "NICU (newborn intensive care)"),
        ("picu", "PICU (children's intensive care)"),
        ("pediatrics", "Paediatrics"),
        ("infertility_ivf", "Infertility / IVF"),
        ("gynecology", "Gynaecology (non-pregnancy)"),
    ],
    "Surgery": [
        ("general_surgery", "General surgery"),
        ("cardiac_surgery", "Cardiac surgery"),
        ("interventional_cardiology", "Interventional cardiology (angioplasty)"),
        ("neurosurgery", "Neurosurgery"),
        ("orthopedic_surgery", "Orthopaedic surgery"),
        ("joint_replacement", "Joint replacement"),
        ("spine_surgery", "Spine surgery"),
        ("eye_surgery", "Eye surgery"),
        ("transplant", "Organ transplant"),
        ("cosmetic_aesthetic", "Cosmetic / aesthetic surgery"),
        ("proctology", "Piles, fistula and fissure treatment"),
        ("vascular_surgery", "Vascular surgery and varicose veins"),
    ],
    "Imaging and diagnostics": [
        ("mri", "MRI scan"),
        ("ct_scan", "CT scan"),
        ("xray", "X-ray"),
        ("ultrasound", "Ultrasound"),
        ("mammography", "Mammography"),
        ("nuclear_imaging", "Nuclear imaging"),
        ("gi_endoscopy", "GI endoscopy"),
        ("laboratory_pathology", "Laboratory / pathology"),
        ("cardiac_diagnostics", "Heart tests (echo, ECG, TMT)"),
    ],
    "Cancer": [
        ("cancer_surgery", "Cancer surgery"),
        ("chemotherapy", "Chemotherapy"),
        ("radiotherapy", "Radiotherapy"),
    ],
    "Other specialties": [
        ("dialysis", "Dialysis"),
        ("nephrology_renal", "Nephrology (kidney care)"),
        ("dental", "Dental"),
        ("ent", "ENT (ear, nose, throat)"),
        ("ophthalmology_medical", "Eye care (medical)"),
        ("dermatology", "Dermatology"),
        ("gastroenterology", "Gastroenterology"),
        ("pulmonology_respiratory", "Pulmonology / respiratory"),
        ("mental_health", "Mental health"),
        ("physiotherapy_rehab", "Physiotherapy / rehabilitation"),
        ("prosthetics_orthotics", "Prosthetics / orthotics"),
        ("outpatient_opd", "Outpatient (OPD)"),
        ("urology", "Urology and kidney stone treatment"),
        ("diabetes_endocrinology", "Diabetes, thyroid and hormone care"),
        ("health_checkup_vaccination", "Health check-ups and vaccination"),
        ("neurology", "Neurology (non-surgical brain and nerve care)"),
        ("pain_management", "Pain management"),
        ("cardiology_medical", "Cardiology (heart care, no surgery)"),
    ],
    "Traditional medicine (AYUSH)": [
        ("ayush_traditional_medicine", "Ayurveda, homeopathy and other traditional medicine"),
    ],
}
# Readable facility types, with article, for sentences ("... is unusual for a dental clinic").
FACILITY_TYPE_NAME = {
    "multispecialty_hospital": "a multispecialty hospital",
    "dental": "a dental clinic",
    "general_hospital_or_nursing_home": "a general hospital or nursing home",
    "diagnostic_imaging_lab": "a diagnostic or imaging centre",
    "eye": "an eye hospital",
    "ayush_alternative": "an AYUSH (traditional medicine) centre",
    "maternity_women_children": "a maternity and children's hospital",
    "general_clinic_polyclinic": "a general clinic or polyclinic",
    "medical_college_teaching_hospital": "a medical college hospital",
    "other_single_specialty": "a single-specialty clinic",
    "ivf_fertility": "a fertility (IVF) clinic",
    "orthopedic_spine": "an orthopaedic and spine hospital",
    "skin_hair_cosmetic": "a skin, hair or cosmetic clinic",
    "ent_hearing_speech": "an ENT, hearing or speech clinic",
    "pediatric": "a children's hospital",
    "government_health_centre": "a government health centre",
    "cardiac": "a heart hospital",
    "cancer": "a cancer hospital",
    "kidney_urology": "a kidney and urology hospital",
    "mental_health_deaddiction": "a mental health or de-addiction centre",
    "physiotherapy_rehab": "a physiotherapy or rehabilitation centre",
    "neuro": "a neurology and neurosurgery hospital",
    "gastro_liver": "a gastro and liver hospital",
    "not_a_care_facility": "an organisation that is not a care facility",
    "home_care_or_ambulance": "a home-care or ambulance service",
    "unknown": "a facility of unknown type",
}


def facility_type_name(ft, with_article=True):
    n = FACILITY_TYPE_NAME.get(ft or "unknown", f"a {(ft or 'unknown').replace('_', ' ')} facility")
    return n if with_article else n.split(" ", 1)[1]


SERVICE_NAME  = {s: n for g in SERVICE_GROUPS.values() for s, n in g}
SERVICE_GROUP = {s: grp for grp, g in SERVICE_GROUPS.items() for s, _ in g}


def service_name(label: str) -> str:
    return SERVICE_NAME.get(label, label.replace("_", " ").capitalize())


# --- district hint (suggestion block only; never changes tiers or order) ----
# Supply-signal NFHS-5 indicator per service: a high value means the service is commonly
# delivered in the district. NFHS need indicators (blood sugar, BP, anaemia...) are NOT used.
HINT_SUPPLY_INDICATOR = {
    "caesarean_section":    "births_delivered_by_csection_5y_pct",
    "normal_delivery":      "institutional_birth_5y_pct",
    "obstetrics_maternity": "institutional_birth_5y_pct",
}
HINT_RADIUS_KM = 30.0   # hint shows only if no Confirmed for the service within this distance
HINT_MAX = 3            # nearby related facilities listed under the hint
# Related services come from service_department_map (link_type 'implied_by_service');
# this dict is the fallback if the map has none, and HINT_RELATED_ALLOWED keeps the list to
# maternity care (the map also links caesarean_section -> nicu, which is newborn care).
HINT_RELATED_FALLBACK = {
    "caesarean_section":    ["obstetrics_maternity", "high_risk_obstetrics", "normal_delivery"],
    "normal_delivery":      ["obstetrics_maternity", "caesarean_section", "high_risk_obstetrics"],
    "obstetrics_maternity": ["normal_delivery", "caesarean_section", "high_risk_obstetrics"],
}
HINT_RELATED_ALLOWED = {"obstetrics_maternity", "high_risk_obstetrics", "normal_delivery", "caesarean_section"}
# (headline with {v} = rounded %, follow-up line). Plain words for a health worker.
HINT_TEXT = {
    "caesarean_section": ("C-sections are common in this district ({v}% of births, NFHS-5).",
                          "These nearby hospitals offer maternity care and may do C-sections. Call to check."),
    "normal_delivery": ("Most births in this district happen in a health facility ({v}%, NFHS-5).",
                        "These nearby hospitals offer maternity care and may handle deliveries. Call to check."),
    "obstetrics_maternity": ("Most births in this district happen in a health facility ({v}%, NFHS-5).",
                             "These nearby hospitals offer related care and may offer maternity care. Call to check."),
}

# --- service picker aliases (typed words that should find a service) -------
SERVICE_ALIASES = {
    "caesarean_section": ["c-section", "c section", "csection", "caesarean", "cesarean", "caesar", "lscs", "c-sec"],
    "normal_delivery": ["delivery", "childbirth", "birth", "labour", "labor"],
    "obstetrics_maternity": ["pregnancy", "maternity", "obstetrics", "antenatal", "prenatal", "ob gyn", "obgyn"],
    "high_risk_obstetrics": ["high risk pregnancy", "complicated pregnancy"],
    "nicu": ["newborn", "neonatal", "neonate", "baby icu", "premature", "preterm", "sncu"],
    "picu": ["child icu", "paediatric icu", "pediatric icu"],
    "pediatrics": ["pediatrics", "paediatrics", "child", "children", "kids"],
    "dialysis": ["kidney", "renal", "haemodialysis", "hemodialysis", "kidney machine"],
    "nephrology_renal": ["kidney", "renal"],
    "mri": ["mri", "magnetic resonance", "scan"],
    "ct_scan": ["ct", "cat scan", "scan"],
    "xray": ["x-ray", "x ray", "radiograph"],
    "ultrasound": ["usg", "sonography", "scan"],
    "cardiac_surgery": ["heart surgery", "bypass", "cabg", "open heart", "valve"],
    "interventional_cardiology": ["angioplasty", "stent", "angiography", "cath lab"],
    "burn_care": ["burns", "burn unit"],
    "trauma_emergency": ["emergency", "accident", "casualty", "trauma", "er"],
    "icu_critical_care": ["icu", "intensive care", "critical care"],
    "ventilator_support": ["ventilator", "oxygen"],
    "chemotherapy": ["cancer", "chemo", "oncology"],
    "radiotherapy": ["cancer", "radiation", "oncology"],
    "cancer_surgery": ["cancer", "oncology", "tumour", "tumor"],
    "eye_surgery": ["cataract", "lasik", "eye"],
    "infertility_ivf": ["ivf", "fertility", "test tube"],
    "dental": ["teeth", "tooth", "dentist"],
    "mental_health": ["psychiatry", "depression", "de-addiction"],
    "joint_replacement": ["knee replacement", "hip replacement"],
    "stroke_care": ["stroke", "paralysis"],
    "blood_bank": ["blood"],
    "ambulance": ["108"],
}

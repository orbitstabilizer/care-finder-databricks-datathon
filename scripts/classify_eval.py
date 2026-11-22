"""Iterate on the snippet classification prompt against a fixed hard sample.

Runs on the Databricks warehouse via ai_query; prints a side-by-side table so the
labels can be eyeballed. Usage: python scripts/classify_eval.py
"""

import json
import subprocess
import sys
import textwrap

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
MODEL = "databricks-meta-llama-3-3-70b-instruct"

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

# Deliberately hard: real service claims, research prose, institutional trivia,
# equipment-only lines, and the three that failed the first attempt.
SAMPLE = [
    "Dialysis treatment is provided via a 20-bed Dialysis Unit with 10 machines",
    "Complex surgeries - for skull base lesions, Aneuryms, AVMs",
    "Conducts lung function tests including lung volume studies, diffusion capacity measurements",
    "In a cohort of ten intracranial VMAT patients, nine cases show agreement within 8.6%",
    "10-bed Neonatal Intensive Care Unit (NICU)",
    "Dr B. Niranjan Naik is a General Surgeon with 28 years of experience",
    "Has a 3 Tesla MRI scanner",
    "Hemodialysis is performed in three units as a regular service",
    "Established in 2001",
    "24x7 Emergency Services with a 50-bed emergency ward",
    "Premashraya is a residential facility for outstation patients and relatives",
    "Total knee replacement using computer navigation and robotic assistance",
    "Offers bronchoscopy with endobronchial ultrasound (EBUS).",
    "Regional Blood Bank Centre with facilities for fractionated blood components",
    "Consultation fee at Fortis Memorial Research Institute is Rs 2,000 at clinic.",
    "Fully equipped minor operation theatre in burn ward",
]

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

    Note: lung function tests, spirometry, bronchoscopy, ventilation and sleep
    studies are all "pulmonology_respiratory". A general emergency department or
    casualty ward is "trauma_emergency", NOT any obstetric label.

    Also return "strength":
      "explicit" - names the service with concrete detail (beds, machines, units)
      "stated"   - names the service plainly
      "weak"     - only implies it

    A snippet may evidence SEVERAL services - return all of them.
    "imaging including USG, CT and MRI" -> ["ultrasound","ct_scan","mri"].

    Education, training, fellowship and degree programmes are
    "not_a_service_claim", even in a clinical subject.

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
       "services":[<labels>],"strength":"explicit"|"stated"|"weak"|"na"}}
    - When is_claim is true, "services" must contain at least one allowed label.

    Snippets:
    """)


def token() -> str:
    raw = subprocess.run(
        ["databricks", "auth", "token", "-p", PROFILE],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(raw)["access_token"]


SAMPLE_SQL = """
WITH ev AS (
  SELECT explode(from_json(procedure,'array<string>')) AS s
  FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities
  UNION ALL
  SELECT explode(from_json(capability,'array<string>'))
  FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities
  UNION ALL
  SELECT explode(from_json(equipment,'array<string>'))
  FROM databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities
)
SELECT DISTINCT trim(s) AS s FROM ev
WHERE s IS NOT NULL AND length(trim(s)) BETWEEN 15 AND 250
ORDER BY md5(trim(s))
LIMIT {n}
"""


def random_sample(conn, n: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(SAMPLE_SQL.format(n=n))
        return [r[0] for r in cur.fetchall()]


def main() -> None:
    numbered = json.dumps([f"{i}. {s}" for i, s in enumerate(SAMPLE)], ensure_ascii=False)
    full = PROMPT + numbered

    sample = SAMPLE
    with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=token()) as conn:
        if len(sys.argv) > 1 and sys.argv[1] == "--random":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
            sample = random_sample(conn, n)
            full = PROMPT + json.dumps(
                [f"{i}. {s}" for i, s in enumerate(sample)], ensure_ascii=False
            )
        with conn.cursor() as cur:
            cur.execute("SELECT ai_query(?, ?) AS out", [MODEL, full])
            raw = cur.fetchone()[0]

    try:
        out = json.loads(raw[raw.index("[") : raw.rindex("]") + 1])
    except Exception as exc:  # noqa: BLE001
        print("UNPARSEABLE:", exc)
        print(raw)
        return

    invalid: list[str] = []
    print(f"in={len(sample)}  out={len(out)}  "
          f"{'OK' if len(out) == len(sample) else '*** COUNT MISMATCH ***'}\n")

    for i, snip in enumerate(sample):
        rec = next((o for o in out if o.get("i") == i), None)
        if rec is None:
            print(f"{i:>2}  !! MISSING            | {snip[:70]}")
            continue
        echo_ok = snip.lower().startswith(str(rec.get("echo", "")).lower()[:12])
        flag = " " if echo_ok else "!"
        svc = rec.get("services") or []
        bad = [s for s in svc if s not in ALLOWED]
        claim = rec.get("is_claim")
        if bad or (claim and not svc) or (claim is False and svc):
            flag = "X"
            invalid.extend(bad)
        shown = ",".join(svc) if svc else ("-- not a claim --" if claim is False else "?? EMPTY")
        print(f"{i:>2}{flag} {shown:<34} {rec.get('strength','?'):<9} | {snip[:52]}")

    print()
    print(f"invalid labels: {sorted(set(invalid)) if invalid else 'none'}")


ALLOWED = set(SERVICES)


if __name__ == "__main__":
    main()

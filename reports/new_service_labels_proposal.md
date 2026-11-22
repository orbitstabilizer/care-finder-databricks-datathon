# Proposal: 8 new service labels

Status: proposal only. Nothing was built, no table was written, no model was called.
All numbers come from read-only SQL on `workspace.vf` run on 2026-11-21.

## What was measured

- Starting pool: sentences in `workspace.vf.sentence_tags` that are claims, not failed,
  and tagged `other_clinical`. That is **29,950 distinct sentences** on
  **6,714 non-shifted facilities**. 4,442 of them are "unlabelled claims" with no
  suggested name (4,037 distinct sentences reach a non-shifted facility).
- Facility link: `sentence_tags.sentence_id` -> `distinct_sentences` -> `facility_sentences`
  (`is_placeholder = false`) -> `facilities_clean` (`is_shifted = false`).
- A sentence belongs to a group when the model's `suggested_name` matches the group's
  keyword pattern. When the suggested name is empty, the sentence text is matched instead.
  A facility counts once if at least one of its sentences is in the group.
- These are keyword groupings of the model's free-text names, not a re-tagging. The counts
  are a good size estimate, not a final label count. A sentence can sit in two groups
  (for example "Ayurvedic treatment for piles").

The 8 proposed labels together cover **11,344 sentences (38% of the pool)** on
**3,815 facilities (57% of facilities that have any `other_clinical` claim)**.

## How generic sentences are treated

These are not services a patient searches for, so they are kept out of every proposed label
and should stay `other_clinical` (or better, become `is_claim = false` in a later prompt fix):

| Kind | Examples (verbatim) | Size |
|---|---|---|
| Facility type, beds, pharmacy, operation theatre, "inpatient services" | "Multispeciality hospital", "On-site pharmacy", "Has 20 beds", "Operation Theatre" | 2,584 sentences on 2,821 facilities |
| ECG mentioned alone | "ECG machine", "ECG", "Electrocardiography (ECG)", "Performs ECG" | 74 sentences on 516 facilities |

The ECG case matters: counting bare ECG mentions would lift the cardiac label from 740 to
about 1,080 facilities, but almost every clinic owns an ECG machine, so it says nothing about
a cardiac service. ECG only counts when it appears with another cardiac test
("Provides 2D Echo & ECG diagnostic capabilities"). The same rule is applied to bare
"EEG equipment" / "EMG" lines in neurology.

Techniques are also not services: "robotic surgery", "laser treatment", "minimally invasive"
describe how, not what (see rejects).

## Proposed labels

| # | Label | Readable name | Facilities | Sentences |
|---|---|---|---|---|
| 1 | `urology` | Urology and kidney stone treatment | 1,450 | 2,182 |
| 2 | `diabetes_endocrinology` | Diabetes, thyroid and hormone care | 847 | 1,517 |
| 3 | `health_checkup_vaccination` | Health check-ups and vaccination | 760 | 1,166 |
| 4 | `cardiac_diagnostics` | Heart tests and non-invasive cardiology | 740 | 1,053 |
| 5 | `neurology` | Neurology (non-surgical brain and nerve care) | 709 | 914 |
| 6 | `ayush_traditional_medicine` | Ayurveda, homeopathy and other traditional medicine | 697 | 3,646 |
| 7 | `gynecology` | Gynaecology (non-pregnancy women's health) | 647 | 564 |
| 8 | `proctology` | Piles, fistula and fissure treatment | 418 | 451 |

### 1. `urology` — Urology and kidney stone treatment

- Covers: urology departments and consultations; kidney/urinary stone treatment
  (lithotripsy, PCNL, URS, RIRS); prostate treatment (TURP, HoLEP); cystoscopy, urodynamics,
  uroflowmetry; circumcision; andrology and erectile dysfunction; paediatric urology.
- Excludes: dialysis and kidney medicine; kidney transplant; cancer chemotherapy; Ayurvedic
  or homeopathic "kidney stone cures".
- Must not overlap with: `nephrology_renal`, `dialysis`, `transplant`, `infertility_ivf`
  (male infertility stays there), `cancer_surgery`, `general_surgery`.
- Examples:
  - Health City Vistaar: "Endoscopic urology surgeries including PCNL, URS, TURP, TUR bladder tumor, VIU Endopylotomy are performed at Health City Hospital."
  - Soni Hospital: "Lithotripsy machine installed in Rajasthan at Soni Hospital in 1988."
- Note: the keyword must be anchored at a word start. An unanchored "urolog" also matches
  "neurology"; the first draft count was 1,616 for that reason.

### 2. `diabetes_endocrinology` — Diabetes, thyroid and hormone care

- Covers: diabetes clinics and management programmes, insulin pump and glucose monitoring,
  diabetic foot care, thyroid treatment, endocrinology departments.
- Excludes: diabetic eye disease; bariatric surgery; Ayurvedic or homeopathic diabetes
  treatment; a bare "blood sugar test" in a lab list.
- Must not overlap with: `ophthalmology_medical`, `eye_surgery`, `laboratory_pathology`,
  `outpatient_opd`, `nephrology_renal`.
- Examples:
  - Neelu Medical Centre and Diabetes Foundation: "15-bed hospital specializing in diabetes care, family medicine, and podiatric surgery"
  - Diacare Diabetes Specialities Center: "Provides diabetes diagnosis and screening for Type 1, Type 2, and gestational diabetes"

### 3. `health_checkup_vaccination` — Health check-ups and vaccination

- Covers: full-body / master / executive health check packages, vaccination and immunisation
  (child, adult, travel, COVID-19), cancer screening programmes, visa and employment medical
  examinations.
- Excludes: a single lab test; dental or eye check-ups; antenatal check-ups; prenatal or
  newborn screening tests.
- Must not overlap with: `laboratory_pathology`, `outpatient_opd`, `pediatrics`,
  `obstetrics_maternity`, `mammography`.
- Examples:
  - Medcis Pathlabs India: "Offers Aarogyam X 1+1 health checkup with 139 tests"
  - Swarup Medical Centre: "GAMCA Approved Medical Examination Centre in Kolkata"
- Risk: many sentences are diagnostic-lab package adverts. Useful for a "full body checkup
  near me" search, weak evidence of a hospital-grade service.

### 4. `cardiac_diagnostics` — Heart tests and non-invasive cardiology

- Covers: echocardiography / 2D echo, treadmill or stress test (TMT), Holter and ambulatory
  blood-pressure monitoring, EECP therapy, cardiology consultation and departments.
- Excludes: bare ECG mentions (see above); angiography, angioplasty, stents, pacemakers,
  cath lab; bypass and valve surgery.
- Must not overlap with: `interventional_cardiology`, `cardiac_surgery`, `icu_critical_care`,
  `ultrasound` (echo is a heart test here, not general ultrasound).
- Examples:
  - Tender Palm Super Specialty Hospital: "Treadmill testing equipment is available at Tender Palm Super Specialty Hospital"
  - Randhawa Hospital: "Operates an EECP Centre within Randhawa Hospital"
- Count with bare ECG sentences included would be about 1,080; 740 is the count without them.

### 5. `neurology` — Neurology (non-surgical brain and nerve care)

- Covers: neurology departments and consultations; epilepsy, headache and migraine, vertigo,
  Parkinson's, dementia and neuropathy clinics; EEG, EMG and nerve-conduction testing when
  stated as a service.
- Excludes: brain and spine operations; acute stroke units and thrombolysis; psychiatric
  care; bare "EEG equipment" lines.
- Must not overlap with: `neurosurgery`, `spine_surgery`, `stroke_care`, `mental_health`,
  `physiotherapy_rehab`.
- Examples:
  - Jaslok Hospital: "Headache and Migraine Clinics at Jaslok Hospital are led by Dr Ravishankar, Consultant in-charge"
  - Athani Hospital: "Electroencephalogram (EEG) testing is offered at Athani Hospital"

### 6. `ayush_traditional_medicine` — Ayurveda, homeopathy and other traditional medicine

- Covers: Ayurveda (including Panchakarma, Shirodhara, Kshar Sutra), homeopathy, naturopathy,
  Unani, Siddha, yoga therapy.
- Excludes: modern physiotherapy; spa and beauty treatments; acupuncture, cupping, ozone,
  PRP and stem-cell therapy (kept out, see rejects).
- Must not overlap with: `physiotherapy_rehab`, `cosmetic_aesthetic`, `dermatology`,
  `outpatient_opd`. An Ayurvedic treatment for a condition gets this label only, not the
  modern-medicine label for that condition.
- Examples:
  - Praanadha Ayurveda Hospital: "Offers Panchakarma detoxification programme (28 days) including detox diet, Vamana, Virechana, Nasyam, Vasthi, Rakhta moksha and Yoga sessions"
  - Rao Tula Ram Memorial Hospital: "Rao Tula Ram Memorial Hospital is listed as a government hospital in Delhi where homoeopathic treatment is available."
- Why include it: it is the largest sentence group in the pool, and without the label these
  facilities can surface for unrelated modern-medicine searches or not at all. The label also
  lets the app keep them out of emergency-style results.

### 7. `gynecology` — Gynaecology (non-pregnancy women's health)

- Covers: hysteroscopy, colposcopy, Pap smear and cervical screening, PCOS/PCOD,
  endometriosis and fibroid treatment, hysterectomy, menopause clinics, contraception,
  tubectomy, MTP.
- Excludes: pregnancy, delivery and antenatal care; IVF and fertility treatment;
  gynaecological cancer surgery; breast imaging.
- Must not overlap with: `obstetrics_maternity`, `normal_delivery`, `caesarean_section`,
  `high_risk_obstetrics`, `infertility_ivf`, `cancer_surgery`, `mammography`.
- Examples:
  - Lakhotia Medical Center: "Colposcopy Examination is offered at Lakhotia Medical Center"
  - Zoi Hospitals - Attapur: "Tubectomy/Tubal ligation offered at Zoi Hospitals Attapur"
- Note: 179 facilities carry the single bare word "Hysteroscopy".

### 8. `proctology` — Piles, fistula and fissure treatment

- Covers: piles/haemorrhoids, anal fistula, fissure, pilonidal sinus, laser proctology,
  anorectal surgery.
- Excludes: AV fistula for dialysis, bladder and obstetric fistula; colonoscopy; colorectal
  cancer; Ayurvedic Kshar Sutra (goes to `ayush_traditional_medicine`).
- Must not overlap with: `general_surgery`, `gi_endoscopy`, `gastroenterology`,
  `cancer_surgery`, `dialysis`.
- Examples:
  - Harsh Hospital & Maternity Home: "Offers anorectal laser surgeries using German-made Diode Laser 1470nm 15W"
  - Jaslok Hospital and Research Center: "Piles treatment (Non Surgical) provided at Jaslok Hospital and Research Centre"

## Rejected candidates

| Candidate | Facilities | Sentences | Reason |
|---|---|---|---|
| Generic facility descriptions (multispeciality, pharmacy, beds, OT) | 2,821 | 2,584 | Not a service. |
| ECG alone | 516 | 74 | Equipment nearly every clinic has; not a searchable service. |
| General / internal medicine, fever and infection treatment | 1,003 | 770 | Largest reject. Mostly "Treats viral fever" and "General Medicine"; same meaning as `outpatient_opd`, so it would not separate facilities. |
| Robotic, laser, laparoscopic, "minimally invasive" | 915 | 1,353 | A technique, not a service. The organ decides the label. |
| Pain management | 434 | 699 | Passes the 300 bar; ninth in line. Vague ("back pain", "joint pain") and overlaps `physiotherapy_rehab` and orthopaedics. First to add if a slot opens. |
| Vascular surgery and varicose veins | 321 | 377 | Passes the bar narrowly; tenth in line. Real service, smallest qualifying group. |
| Acupuncture, cupping, ozone, PRP, stem cell, hyperbaric | 281 | 529 | Below 300 and a mix of unrelated therapies. |
| Audiology and speech therapy | 256 | 560 | Below 300. Could be folded into `ent` by a prompt note. |
| Bariatric surgery and weight loss | 251 | 290 | Below 300. |
| Allergy and immunology | 245 | 233 | Below 300. |
| Rheumatology and arthritis | 241 | 220 | Below 300. |
| Palliative, geriatric and home care | 234 | 368 | Below 300. |
| Bone density (DEXA) | 202 | 216 | Below 300; equipment-style lines. |
| De-addiction | 128 | 236 | Below 300; belongs under `mental_health`. |

Reject counts use the first, broader keyword pass; pain management and vascular use the
refined pass.

## Caveats

- Groups are built from the model's suggested names by keyword. Real counts after a proper
  re-tag will differ somewhat in both directions.
- Unlabelled sentences that list several departments ("Provides tertiary care in over 40
  specialties including cardiology, neurology...") enter a group through text matching.
  These are weak evidence and should be tagged `weak`.
- Record merging is visible in these rows too: "Hysteroscopy equipment is available at Rana
  Hospital Pvt. Ltd." is attached to Raj Eye Hospital, Gorakhpur. The attribution filter
  still has to run on any new label.
- The queries and patterns used are in the session scratchpad only; they would need to be
  copied into `scripts/` if this proposal is accepted.

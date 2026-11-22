# Facility type, one facility per call (ft_single_v1)

Script: `scripts/facility_type_single.py`. Run date 2026-11-21. Model `databricks-meta-llama-3-3-70b-instruct`, temperature 0, max_tokens 400, `failOnError => false`. Warehouse 8ea2282aca435351 (2X-Small).

## Results

| step | rows | attempt-1 valid | attempt-1 failed | statement seconds (attempt 1) | retry seconds | failed after retry |
|---|---|---|---|---|---|---|
| pilot (old pilot ids, 2 shifted dropped) | 198 | 198 | 0 | 11.5 | – | 0 |
| probe 3b (100 random non-pilot) | 100 | 100 | 0 | 7.7 | – | 0 |
| full (all remaining non-shifted) | 9,691 | 9,690 | 1 | 244.7 | 2.9 | 1 |

- Gate 3 (30-row review of pilot): 0 W, 7 D (facility_type judged). Passed.
- Gate 3b: 100/100 valid; projection 7.7 s / 100 x 9,691 = 746 s (12.4 min) < 60 min. Passed.
- Full run wall-clock (script, incl. validation, retry, table build, comments): 291.9 s. ai_query statement alone 244.7 s (~40 rows/s).
- Output `workspace.vf.facility_type`: 9,989 rows = 9,989 distinct unique_id = all non-shifted rows of facilities_clean. 1 failed.
- Failed row: `43f8b198-6b94-4458-b3fb-155945c904d5` "Danth Care". Both attempts returned identical malformed JSON (`"reason":"smile","}`). Stored as facility_type unknown, confidence low, failed true.
- Reasons longer than 12 words: 0.

### Counts

facility_type: multispecialty_hospital 3081, dental 1802, general_hospital_or_nursing_home 754, diagnostic_imaging_lab 655, eye 628, ayush_alternative 387, maternity_women_children 311, general_clinic_polyclinic 252, medical_college_teaching_hospital 245, other_single_specialty 239, ivf_fertility 235, orthopedic_spine 207, skin_hair_cosmetic 195, ent_hearing_speech 179, pediatric 163, government_health_centre 144, cardiac 120, cancer 97, kidney_urology 92, mental_health_deaddiction 50, physiotherapy_rehab 50, neuro 35, gastro_liver 32, not_a_care_facility 21, home_care_or_ambulance 14, unknown 1.

confidence: high 7551, medium 2394, low 44 (43 model + 1 failed row).
ownership: private 8534, unknown 801, public 432, charitable_trust 222.
is_single_specialty: false 5058, true 4930, NULL 1.
multispecialty_hospital by confidence: high 2024, medium 1056, low 1.

### Caveats seen in review

- Bare-name hospitals with no specialty evidence ("Ishan Hospital", "Mangal Prabhu Hospital") are often labelled multispecialty_hospital at medium confidence, while similar rows elsewhere get general_hospital_or_nursing_home. The 1,056 medium-confidence multispecialty rows should be treated as "hospital, breadth unknown".
- Ownership "private" is given even where nothing in name/description indicates it (prompt says unknown in that case). 2,150 rows are private + medium confidence. Treat ownership as weak.
- Conflicting text is not always downgraded to low confidence (e.g. "Getwell Eye Hospital" with a pediatric description: eye, medium).

## Method

1. Input: `workspace.vf.facilities_clean`, `NOT is_shifted`; JSON `{"name": trim(name) or '', "description": first 400 chars or '', "specialties": specialties (already distinct) or []}` appended after the prompt.
2. One SQL statement per (phase, attempt): `INSERT INTO facility_type_single_raw ... ai_query(...)` over one row per facility. unique_id is a SQL column, never sent through the model.
3. Python validation per row: extract first `{` to last `}`, `json.loads`, facility_type/ownership/confidence in allowed sets, is_single_specialty a JSON boolean, reason a string. No word-count rejection.
4. Failed rows retried once (one statement over just those ids, same prompt, temperature 0). Still failing -> failed = true.
5. Per-row outcome in `facility_type_single_status` (phase, accepted_attempt, failed, problems). `facility_type` re-parses exactly the accepted raw response in SQL (`from_json`).
6. Phases: pilot = `facility_type_batches.phase='pilot'` minus 2 shifted (198); probe = 100 non-shifted non-pilot, `ORDER BY md5('probe'||unique_id)`; full = the rest (9,691). The pilot and probe rows are reused in the final table.

Tables written (all new; old facility_type_* tables untouched): `facility_type_single_prompts`, `facility_type_single_raw`, `facility_type_single_runs`, `facility_type_single_status`, `facility_type` (with table + column comments).

## Prompt ft_single_v1 (exact text; the facility JSON follows "Facility:\n")

Derived from the stored ft_v3 text by: "Each numbered line below is one facility" -> "The facility below is"; array/order rule -> single JSON object rule; removed the "n" and "echo" rules; object template without n/echo; "Facilities:" -> "Facility:". Nothing else changed. Also stored in `workspace.vf.facility_type_single_prompts`.

```
You classify records of Indian healthcare facilities by FACILITY TYPE.

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
```

## 30-row review (pilot run, rows ordered by md5('review'||unique_id))

Judged on facility_type from name + description. W = wrong, D = debatable, blank = agree.

| # | name | type | conf | mark | note |
|---|---|---|---|---|---|

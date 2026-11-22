# Pilot A: sentence service tagger

All speed numbers are **worst case**: the single 2X-Small warehouse was shared with Pilot B (pb_*); the facility-type job had finished. See the contention note in the one-per-call section for the overlaps visible in query history. Calls were sequential on one connection; concurrent calls were not tested.

Source: `workspace.vf.distinct_sentences`. Sample: `workspace.vf.pa_sample` (500 rows, ordered by md5('pa_seed_1'||sentence_id), column `ord`). Results: `workspace.vf.pa_results` (key sentence_id + run). Prompt: `workspace.vf.pa_prompt` (pa_v1). Statement log: `workspace.vf.pa_statements` and `reports/pilot_a/statements_*.jsonl`. Raw model responses: `reports/pilot_a/raw_*.jsonl`. Script: `scripts/pilot_a_tagger.py`.

Model `databricks-meta-llama-3-3-70b-instruct`, temperature 0 (`modelParameters => named_struct('temperature', 0.0)`).

## Results summary

**Speed (worst case: the warehouse was shared with two other jobs; calls were sequential on one connection).**

| batch size | sentences | call seconds | sentences/s | projected hours for 271,262 |
|---|---|---|---|---|
| 25, all of stage 0 + stage 1 (includes the retry and 25 single calls) | 500 | 462.6 | 1.08 | 69.8 |
| 25, stage 1 only | 450 | 383.1 | 1.17 | 64.1 |
| 25, median first-attempt call (14.0 s) | 25 | 14.0 | 1.78 | 42.2 |
| 50, stage 1 (ran before the order to skip it arrived) | 250 | 140.2 | 1.78 | 42.3 |

The first call of each run was slow: 29.5 s and 50.0 s in stage 0, 82.8 s for the first stage 1 call. After that, calls of 25 took 10.8 to 20.1 s and calls of 50 took 24.3 to 31.7 s. Per sentence, 50 per call matched a steady call of 25. Single-sentence calls took about 1.6 s each.

**Quality**
- Failed batches: 1 of 20 at 25 per call (5%), unparseable on both the first try and the retry; 0 of 5 at 50 per call.
- Failed rows: 9 of 500 at 25 (1.8%) and 7 of 250 at 50 (2.8%), all `unknown_label`.
- First-word echo mismatch: 1 of 500 at 25 (0.2%; "An I.T." vs "I.T. Recognized…") and 0 of 250 at 50.
- Agreement on the 250 rows run at both sizes (239 valid at both): 234 have the same is_claim and 213 the same label set.
- Shares at 25 per call (491 valid rows): is_claim false 155 (31.6%); other_clinical 49 (10.0%), all with a suggested_name. At 50 per call, 1 of 27 other_clinical rows had no name.
- The 15 most common suggested names, out of 49: migraine treatment 2, pain management 2, ayurveda 2, then 1 each for obesity management, microvascular surgery, pediatric urology, lanso meter, uroflowmetry testing, siddha treatment, imaging services, cancer treatment, thrombolysis treatment, health check, fever treatment, endoscopy.

**Count per label at 25 per call (491 valid rows):** other_clinical 49, dental 39, eye_surgery 30, laboratory_pathology 29, general_surgery 28, obstetrics_maternity 25, outpatient_opd 24, pediatrics 18, cardiac_surgery 15, orthopedic_surgery 13, ent 12, ultrasound 11, ct_scan 11, cosmetic_aesthetic 10, interventional_cardiology 9, infertility_ivf 9, gastroenterology 8, xray 8, neurosurgery 7, icu_critical_care 7, ophthalmology_medical 7, physiotherapy_rehab 7, mri 7, trauma_emergency 7, pulmonology_respiratory 4, spine_surgery 3, mental_health 3, radiotherapy 3, dialysis 3, nephrology_renal 2, gi_endoscopy 2, ambulance 2, nuclear_imaging 2, normal_delivery 2, nicu 2, cancer_surgery 2, high_risk_obstetrics 2, and 1 each for ventilator_support, joint_replacement, burn_care, chemotherapy, dermatology, transplant. Zero: caesarean_section, picu, stroke_care, mammography, blood_bank, prosthetics_orthotics. Strength: stated 245, na 155, explicit 64, weak 27.

**Label counts at 50 per call (243 valid rows):** other_clinical 27, dental 23, obstetrics_maternity 15, eye_surgery 14, laboratory_pathology 13, general_surgery 13, outpatient_opd 13, ent 9, pediatrics 9, orthopedic_surgery 8, cardiac_surgery 7, others 6 or fewer.

## Exact prompt (pa_v1)

The numbered sentences are appended as a JSON list of `"<i>. <sentence>"` strings.

```
You label snippets scraped from Indian hospital websites.

For EACH numbered snippet decide which clinical service the snippet is
EVIDENCE THAT THE FACILITY OFFERS.

Allowed labels: dialysis, caesarean_section, normal_delivery, high_risk_obstetrics, nicu, picu, icu_critical_care, ventilator_support, cardiac_surgery, interventional_cardiology, stroke_care, mri, ct_scan, xray, ultrasound, mammography, nuclear_imaging, burn_care, trauma_emergency, ambulance, chemotherapy, radiotherapy, cancer_surgery, orthopedic_surgery, joint_replacement, neurosurgery, spine_surgery, general_surgery, gi_endoscopy, pulmonology_respiratory, transplant, blood_bank, laboratory_pathology, dental, eye_surgery, physiotherapy_rehab, mental_health, outpatient_opd, infertility_ivf, dermatology, ent, ophthalmology_medical, pediatrics, obstetrics_maternity, cosmetic_aesthetic, prosthetics_orthotics, nephrology_renal, gastroenterology, other_clinical

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
  {"i":<index>,"echo":"<first three words>","is_claim":<true|false>,
   "services":[<labels>],"strength":"explicit"|"stated"|"weak"|"na",
   "suggested_name":"<only when other_clinical>"}
- When is_claim is true, "services" must contain at least one allowed label.

Snippets:
```

## Retry log

- retry_stage0.json: `[]`
- retry_stage1.json: `[  {   "batch": "s1_bs25_b010",   "attempt": 1,   "reason": "unparseable"  },  {   "batch": "s1_bs25_b010",   "attempt": 2,   "reason": "unparseable",   "action": "single"  } ]`

Batch s1_bs25_b010 failed to parse twice with the identical response: at i=11 the model wrote `"services": ["endocrinology" -> changed to "other_clinical"]` (invalid JSON). Its 25 sentences were then sent one per call; all 25 parsed.

Invalid labels returned (raw, across all runs): urology 5, general_medicine 3, 'urologic surgery is not allowed, so: other_clinical' 2, internal medicine 1, dentistry 1, anesthesia 1, emergency_&_critical_care 1, pet_ct 1, imaging 1, emergency 1.

## Per-statement timings (UTC)

| stage | label | start | end | seconds |
|---|---|---|---|---|
| stage0 | create_pa_prompt | 01:10:42.300 | 01:10:43.858 | 1.557 |
| stage0 | upsert_pa_prompt | 01:10:43.858 | 01:10:45.359 | 1.501 |
| stage0 | create_pa_results | 01:10:45.359 | 01:10:46.746 | 1.387 |
| stage0 | create_pa_statements | 01:10:46.746 | 01:10:48.161 | 1.415 |
| stage0 | create_pa_sample | 01:10:48.161 | 01:10:50.574 | 2.413 |
| stage0 | read_pa_sample | 01:10:50.575 | 01:10:50.968 | 0.394 |
| stage0 | s0_bs25_b000 | 01:10:50.969 | 01:11:20.491 | 29.522 |
| stage0 | s0_bs25_b001 | 01:11:20.494 | 01:12:10.469 | 49.975 |
| stage0 | insert_pa_results | 01:12:10.469 | 01:12:11.916 | 1.446 |
| stage0 | insert_pa_statements | 01:12:11.920 | 01:12:13.152 | 1.232 |
| stage1 | create_pa_prompt | 01:12:44.565 | 01:12:44.805 | 0.241 |
| stage1 | upsert_pa_prompt | 01:12:44.806 | 01:12:45.824 | 1.019 |
| stage1 | create_pa_results | 01:12:45.825 | 01:12:46.013 | 0.189 |
| stage1 | create_pa_statements | 01:12:46.014 | 01:12:46.479 | 0.466 |
| stage1 | read_pa_sample | 01:12:46.480 | 01:12:46.729 | 0.249 |
| stage1 | s1_bs25_b000 | 01:12:46.730 | 01:14:09.506 | 82.777 |
| stage1 | s1_bs25_b001 | 01:14:09.508 | 01:14:22.346 | 12.838 |
| stage1 | s1_bs25_b002 | 01:14:22.347 | 01:14:37.273 | 14.925 |
| stage1 | s1_bs25_b003 | 01:14:37.274 | 01:14:48.056 | 10.782 |
| stage1 | s1_bs25_b004 | 01:14:48.057 | 01:15:05.270 | 17.214 |
| stage1 | s1_bs25_b005 | 01:15:05.272 | 01:15:16.870 | 11.598 |
| stage1 | s1_bs25_b006 | 01:15:16.872 | 01:15:32.519 | 15.647 |
| stage1 | s1_bs25_b007 | 01:15:32.519 | 01:15:43.456 | 10.937 |
| stage1 | s1_bs25_b008 | 01:15:43.458 | 01:15:55.226 | 11.768 |
| stage1 | s1_bs25_b009 | 01:15:55.227 | 01:16:09.743 | 14.515 |
| stage1 | s1_bs25_b010 | 01:16:09.744 | 01:16:24.749 | 15.006 |
| stage1 | s1_bs25_b010_retry | 01:16:24.750 | 01:16:39.195 | 14.444 |
| stage1 | s1_bs25_b010_s00 | 01:16:39.196 | 01:16:40.720 | 1.524 |
| stage1 | s1_bs25_b010_s01 | 01:16:40.720 | 01:16:42.580 | 1.86 |
| stage1 | s1_bs25_b010_s02 | 01:16:42.580 | 01:16:44.502 | 1.922 |
| stage1 | s1_bs25_b010_s03 | 01:16:44.502 | 01:16:46.317 | 1.815 |
| stage1 | s1_bs25_b010_s04 | 01:16:46.317 | 01:16:47.924 | 1.607 |
| stage1 | s1_bs25_b010_s05 | 01:16:47.924 | 01:16:49.488 | 1.564 |
| stage1 | s1_bs25_b010_s06 | 01:16:49.488 | 01:16:51.036 | 1.548 |
| stage1 | s1_bs25_b010_s07 | 01:16:51.036 | 01:16:52.630 | 1.594 |
| stage1 | s1_bs25_b010_s08 | 01:16:52.631 | 01:16:54.114 | 1.483 |
| stage1 | s1_bs25_b010_s09 | 01:16:54.114 | 01:17:02.198 | 8.084 |
| stage1 | s1_bs25_b010_s10 | 01:17:02.200 | 01:17:04.076 | 1.876 |
| stage1 | s1_bs25_b010_s11 | 01:17:04.076 | 01:17:05.896 | 1.82 |
| stage1 | s1_bs25_b010_s12 | 01:17:05.896 | 01:17:07.465 | 1.569 |
| stage1 | s1_bs25_b010_s13 | 01:17:07.466 | 01:17:08.860 | 1.394 |
| stage1 | s1_bs25_b010_s14 | 01:17:08.860 | 01:17:10.367 | 1.507 |
| stage1 | s1_bs25_b010_s15 | 01:17:10.367 | 01:17:12.013 | 1.646 |
| stage1 | s1_bs25_b010_s16 | 01:17:12.013 | 01:17:14.035 | 2.022 |
| stage1 | s1_bs25_b010_s17 | 01:17:14.035 | 01:17:15.609 | 1.573 |
| stage1 | s1_bs25_b010_s18 | 01:17:15.609 | 01:17:16.820 | 1.211 |
| stage1 | s1_bs25_b010_s19 | 01:17:16.821 | 01:17:18.383 | 1.561 |
| stage1 | s1_bs25_b010_s20 | 01:17:18.383 | 01:17:19.805 | 1.422 |
| stage1 | s1_bs25_b010_s21 | 01:17:19.805 | 01:17:21.101 | 1.296 |
| stage1 | s1_bs25_b010_s22 | 01:17:21.101 | 01:17:22.690 | 1.589 |
| stage1 | s1_bs25_b010_s23 | 01:17:22.691 | 01:17:24.232 | 1.541 |
| stage1 | s1_bs25_b010_s24 | 01:17:24.232 | 01:17:25.569 | 1.338 |
| stage1 | s1_bs25_b011 | 01:17:25.570 | 01:17:39.616 | 14.046 |
| stage1 | s1_bs25_b012 | 01:17:39.617 | 01:17:52.311 | 12.694 |
| stage1 | s1_bs25_b013 | 01:17:52.312 | 01:18:12.437 | 20.125 |
| stage1 | s1_bs25_b014 | 01:18:12.438 | 01:18:29.722 | 17.284 |
| stage1 | s1_bs25_b015 | 01:18:29.722 | 01:18:42.445 | 12.723 |
| stage1 | s1_bs25_b016 | 01:18:42.446 | 01:18:56.400 | 13.954 |
| stage1 | s1_bs25_b017 | 01:18:56.401 | 01:19:09.902 | 13.501 |
| stage1 | insert_pa_results | 01:19:09.905 | 01:19:11.368 | 1.464 |
| stage1 | s1_bs50_b000 | 01:19:11.369 | 01:19:39.784 | 28.415 |
| stage1 | s1_bs50_b001 | 01:19:39.786 | 01:20:04.040 | 24.254 |
| stage1 | s1_bs50_b002 | 01:20:04.042 | 01:20:35.706 | 31.664 |
| stage1 | s1_bs50_b003 | 01:20:35.708 | 01:21:03.467 | 27.759 |
| stage1 | s1_bs50_b004 | 01:21:03.469 | 01:21:31.579 | 28.11 |
| stage1 | insert_pa_results | 01:21:31.581 | 01:21:33.167 | 1.586 |
| stage1 | insert_pa_statements | 01:21:33.170 | 01:21:34.153 | 0.983 |

## Review of 60 random rows (batch-size-25 results, random.seed(60)) — marks are my judgement

W = wrong, D = debatable, F = failed row, blank = OK.

| # | sentence_id | sentence | is_claim | services | strength | suggested_name | mark | note |
|---|---|---|---|---|---|---|---|---|
| R00 | 9b1496e94266f600 | Initial doctor consultation to assess pain and tailor a personalized treatment plan. | True | outpatient_opd | weak |  |  |  |
| R01 | 320084d98c8cf37e | Offers oral surgery and oral oncology | True | dental | stated |  | D | oral oncology could also be cancer_surgery |
| R02 | d9afabd87c358197 | Offers 195+ treatment options | True | other_clinical | weak | Treatment Options | W | no specific service named; should be is_claim false |
| R03 | 95cd7fafb97ce4d8 | Budget-friendly services | False |  | na |  |  |  |
| R04 | 26ae7a3e22000ed6 | Retina care program including fundus imaging and fundus autofluorescence | True | eye_surgery, ophthalmology_medical | stated |  | D | fundus imaging is diagnostic; eye_surgery questionable |
| R05 | 5aa208f439c86601 | Offers pet clinic services | False |  | na |  |  |  |
| R06 | c4c70dada52aeb47 | Focuses on total healthcare as directed by the WHO | False |  | na |  |  |  |
| R07 | 36ab125f3ea35f53 | Operates a School of Nursing for nurse training | False |  | na |  |  |  |
| R08 | 6216dffac58f711b | Periodontal Flap Surgery offered | True | dental | stated |  |  |  |
| R09 | 8a54c82b08542cad | Pediatric hospital in Orderly Bazaar, Varanasi | True | pediatrics | stated |  |  |  |
| R10 | 2a0fba4c8dae7d7b | Has on-site reproductive genetic testing laboratory | True | laboratory_pathology | stated |  |  |  |
| R11 | 99cf66a7edba1c09 | Operating theatre equipped with overhead surgical lights, anesthesia machine, and patient monitoring equipment. | True | general_surgery | explicit |  | D | OT equipment, general_surgery is an inference |
| R12 | 9179f71f3e3e0c2f | Cost-effective MMII pipeline using free/open-source tools for multimodal imaging integration and trajectory planning | False |  | na |  |  |  |
| R13 | 2553ccc6fce1a5ff | Lanso meter | True | other_clinical | explicit | Lanso Meter | W | 'Lanso meter' is a device name with no service; 'explicit' is wrong |
| R14 | d986021af6b2190c | Provides obstetrics, IVF and pediatric care | True | obstetrics_maternity, infertility_ivf, pediatrics | stated |  |  |  |
| R15 | f5853c5cd478bd5a | Professional affiliations include Indian Menopause Society (IMS), Federation of Obstetrics and Gynecology Societies of India (FOGSI), and Indian Medical Association (IMA) | False |  | na |  |  |  |
| R16 | e76680d81cd6b91c | Diabetes and endocrinology treatments are provided | True | other_clinical | stated | Diabetes Care |  |  |
| R17 | be48d8c5c1ead748 | Laparoscopy Diagnostic with chromopertubation and or adhesiolysis and drilling | True | general_surgery | stated |  | D | diagnostic laparoscopy with chromopertubation is an infertility workup; infertility_ivf missing |
| R18 | 26717411a78ee3af | Has four branches in Chennai, Tamil Nadu: Valasaravakkam, West Tambaram, Washermenpet, and Virugambakkam | False |  | na |  |  |  |
| R19 | b15fb63b326b3d20 | Dr. Ankush Sayal holds MBBS, DNB - ENT, MS - ENT | False |  | na |  |  |  |
| R20 | bf03dea9a1d10e5b | Has all private patient rooms | False |  | na |  |  |  |
| R21 | 7f1fd6a56c776502 | Offers Nutrition services | True | other_clinical | stated | Nutrition Services |  |  |
| R22 | 3e6ec5051dcc25ea | ENT specialized care (otolaryngology) | True | ent | stated |  |  |  |
| R23 | bfbbbdb792238891 | Offers cardiac surgery as part of the Hi-Tech Heart program | True | cardiac_surgery | stated |  |  |  |
| R24 | 17210c9a72ad4789 | Dialysis treatment (hemodialysis) is provided at the hospital | True | dialysis | explicit |  | D | no capacity given, so 'stated' not 'explicit' |
| R25 | e10d5467a9b701be | Samsung 4D ultrasound machine used for fetal imaging | True | ultrasound | explicit |  |  |  |
| R26 | e04c2a7b3d6bf7ee | Adate Hospital is listed as a hospital in Narhe, Pune on Practo. | False |  | na |  |  |  |
| R27 | 782adcdc4d06f712 | Has 75 beds | False |  | na |  |  |  |
| R28 | 2140e0a0cc225595 | Located in Dilsukhnagar, Hyderabad according to the Oasis Fertility hospital listing on Practo ( oasis-fertility-dilsukhnagar ) | False |  | na |  |  |  |
| R29 | a376f42db552c755 | LASIK laser machines used for spectacle removal | True | eye_surgery | explicit |  |  |  |
| R30 | cb4968f2352b3f21 | X-ray monitor visible in operating room photos | True | xray | weak |  |  |  |
| R31 | 2e4130eb44388fb7 | Conducts Complete Diabetic Check-Up including HbA1c, RBS, and Lipid Profile | True | laboratory_pathology | stated |  |  |  |
| R32 | e0022a2b3288f4f1 | Vatech Digital X-Ray System | True | xray | explicit |  |  |  |
| R33 | f1cd64cf0c091802 | Columbia Asia Hospital, Kolkata has a Department of Pediatrics. | True | pediatrics | weak |  |  |  |
| R34 | 056324c14b2dee58 | Tamil Nadu Medical Council registration 37241 for Dr. S R Subrammaniyan (1983) | False |  | na |  |  |  |
| R35 | 1336709dd917e01e | Provides RT-PCR testing for COVID-19 onsite | True | laboratory_pathology | explicit |  |  |  |
| R36 | 8d3b036e8d8b0a69 | CT scan facility run in PPP mode | True | ct_scan | stated |  |  |  |
| R37 | 9283939be48e8730 | CMRI School of Nursing | False |  | na |  |  |  |
| R38 | 6a647ad41bbffa7b | PKHRF serves as the R&D wing of the Pankajakasthuri Group of Enterprises | False |  | na |  |  |  |
| R39 | d96421f910521714 | Performs laparoscopic and hysteroscopic gynecologic surgeries, including vaginal and abdominal hysterectomies | True | obstetrics_maternity, general_surgery | stated |  | D | gynae surgery has no label; obstetrics_maternity + general_surgery is a stretch |
| R40 | 9da6a91908ef9813 | Affiliations of Dr. Pooja Mehta: Indian Orthodontic Society, Indian Dental Association, World Federation of Orthodontics, Indian Board Of Orthodontics (Phase 2) | False |  | na |  |  |  |
| R41 | f8b8e3f4e295b6b5 | ISO-Aligned Quality Management with regular medical audits and CMEs | False |  | na |  |  |  |
| R42 | 2f034965ee8a5fb3 | High-risk pregnancy management (approximately 20 pregnancies annually) | True | high_risk_obstetrics | explicit |  |  |  |
| R43 | f0e364771697a5e8 | Provides comprehensive cardiac services | True | cardiac_surgery, interventional_cardiology | stated |  | D | 'comprehensive cardiac services' does not establish cardiac surgery |
| R44 | ddda272356572d72 | Cardiothoracic & Vascular Surgery program | True | cardiac_surgery | stated |  |  |  |
| R45 | 383ae4ecd711ab1d | Care 24 Medical Centre And Hospital is a hospital located in Erode, Tamil Nadu, India | False |  | na |  |  |  |
| R46 | 3296ad7085848c1a | Leading multi-speciality hospital providing comprehensive care across all medical fields | True | other_clinical | weak | Multi-speciality Care | W | generic multi-speciality claim; other_clinical adds nothing |
| R47 | 71b0226acd4423d8 | In-office mouth guard fabrication capability | True | dental | explicit |  |  |  |
| R48 | ce8333da7e6f806d | Outpatient care with multiple specialty clinics | True | outpatient_opd | stated |  |  |  |
| R49 | 4b8fec3911e445ac | SCHWIND AMARIS Laser system | True | eye_surgery | explicit |  |  |  |
| R50 | ee2bb505e1cc4f83 | Is the only clinic in Bardoli with a Dental Operating Microscope | True | dental | explicit |  |  |  |
| R51 | 6f6595d54e28b33d | Critical & Intensive Care | True | icu_critical_care | stated |  |  |  |
| R52 | 723560e379eaab71 | Dental clinic in Ghaziabad listed under Dentists on Joonsquare: 32 Diamonds Dental Clinic | True | dental | stated |  |  |  |
| R53 | cb828dd36016e074 | Provides MBBS (undergraduate) and postgraduate medical education | False |  | na |  |  |  |
| R54 | 6c8d7bbdd1eb129c | Provides Crown & Bridges services | True | dental | stated |  |  |  |
| R55 | 1fe82c989a77031c | Has a dedicated Burn Care Unit (Pune Burns Unit) at Siddharth Hospital. | True | burn_care | explicit |  |  |  |
| R56 | 9d4107756a794fd9 | Five-Day Glucose Sensor device for diabetes testing | True | other_clinical | stated | Diabetes Testing |  |  |
| R57 | 3d72a8b7522a8882 | Provides lingual orthodontics | True | dental | stated |  |  |  |
| R58 | 3d8a3e4c9e0b37ae | Offers internal medicine & critical care; orthopedic & joint replacement surgery; pulmonology; pediatrics; dermatology; interventional radiology; cardiology; cardiac surgery; anesthesia & critical care; nephrology; urology; gastroenterology; oncology & oncosurgery; hematology; gynecology; neurosurgery; neurology; plastic & reconstructive surgery; ENT; ophthalmology; endocrinology; pain physician; dentistry; interventional neurology; hand surgery; arthroscopy | None |  | None |  | F | row failed validation (invalid labels 'internal medicine', 'dentistry'), not reviewed |
| R59 | f8ca1aae9bd9dbd8 | The Eye Clinic offers laser vision correction | True | eye_surgery | stated |  |  |  |

Counts: W 3, D 7, F 1, OK 49.


## One-per-call arm (pa_single_v1)

One ai_query call per sentence, all rows in one SQL statement (`INSERT INTO workspace.vf.pa_single_raw SELECT ... ai_query(..., failOnError => false) FROM pa_sample`); sentence_id carried in SQL. Temperature 0, no retries. Results in `workspace.vf.pa_results` (runs `single_s0`, `single_full`, mode `single_sql`); raw responses in `workspace.vf.pa_single_raw`.

| run | rows | valid | failures | ai_query statement seconds | sentences/s | projected hours for 271,262 |
|---|---|---|---|---|---|---|
| single_s0 (ord 0-49) | 50 | 50 | none | 9.54 | 5.24 | 14.4 |
| single_full (ord 0-499) | 500 | 489 | claim_without_label 10, unparseable 1 | 58.92 | 8.49 | 8.9 |

Failures: 10 rows came back with is_claim true, services [] (bed counts, 'multi-specialty hospital', pharmacy/optical, equipment); 1 unparseable ('Penile Implants Surgery': the model wrote `["urology" is not allowed, using "other_clinical"]` inside the JSON).

Contention: system.query.history (latest entry 01:18:12 UTC when queried at 01:25) shows Pilot B (`pb_raw_s0_a1`, 01:12:36-01:13:20) overlapping our first stage 1 call (01:12:46-01:14:09, 82.8 s, the slowest call), plus read-only queries on `facility_type` 01:14:04-01:14:13. History did not yet cover the one-per-call run (01:23:43-01:24:52), so overlap there is unknown. Treat all speeds as worst case.

Prompt changes from pa_v1 (only): 'For EACH numbered snippet decide' became 'For the snippet decide'; the Rules block asks for a single JSON object without "i"/"echo" (array, count and echo rules dropped); 'Snippets:' became 'Snippet:'. The sentence is appended raw.

```
You label snippets scraped from Indian hospital websites.

For the snippet decide which clinical service the snippet is
EVIDENCE THAT THE FACILITY OFFERS.

Allowed labels: dialysis, caesarean_section, normal_delivery, high_risk_obstetrics, nicu, picu, icu_critical_care, ventilator_support, cardiac_surgery, interventional_cardiology, stroke_care, mri, ct_scan, xray, ultrasound, mammography, nuclear_imaging, burn_care, trauma_emergency, ambulance, chemotherapy, radiotherapy, cancer_surgery, orthopedic_surgery, joint_replacement, neurosurgery, spine_surgery, general_surgery, gi_endoscopy, pulmonology_respiratory, transplant, blood_bank, laboratory_pathology, dental, eye_surgery, physiotherapy_rehab, mental_health, outpatient_opd, infertility_ivf, dermatology, ent, ophthalmology_medical, pediatrics, obstetrics_maternity, cosmetic_aesthetic, prosthetics_orthotics, nephrology_renal, gastroenterology, other_clinical

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
- Reply with ONLY a JSON object
  {"is_claim":<true|false>,
   "services":[<labels>],"strength":"explicit"|"stated"|"weak"|"na",
   "suggested_name":"<only when other_clinical>"}
- When is_claim is true, "services" must contain at least one allowed label.

Snippet:
```

### Label differences, one-per-call vs 25-per-call

Of the 482 sentences valid in both: 92 differ in is_claim or services set (25 differ in is_claim).

| sentence_id | sentence | 25/call is_claim | 25/call services | 1/call is_claim | 1/call services |
|---|---|---|---|---|---|
| a0cbc7a74d4cf3e4 | Laminar-flow and modular operating theatres in Nagpur, Maharashtra, India | True | general_surgery | True | general_surgery, orthopedic_surgery, neurosurgery, cardiac_surgery |
| 734dec319528e512 | Clinical specialization in Cardiology, Neurology, Gastroenterology, Internal Medicine, Nephrology, Pulmonology, Pain Medicine, Clinical Psychology, Neuro Psychiatry, Orthopaedics | True | cardiac_surgery, neurosurgery, gastroenterology, nephrology_renal, pulmonology_respiratory, orthopedic_surgery | False |  |
| b916056ffc2ff10a | Pediatric urology services | True | pediatrics, other_clinical | True | other_clinical |
| 2553ccc6fce1a5ff | Lanso meter | True | other_clinical | False |  |
| 50b60bf507e32fbd | Ultrasound equipment for obstetric and gynecological imaging | True | ultrasound | True | ultrasound, obstetrics_maternity |
| 72acbf402a4fb658 | Operates Eye Bank for corneal transplants | True | eye_surgery | True | eye_surgery, transplant |
| 3e2b644d4e8a6179 | CBCT/OPG | True | dental | True | xray |
| 725eb2d6f4814dc9 | Dr. Mandeep Singh is the dentist at Deep Dental Clinic. | False |  | True | dental |
| be48d8c5c1ead748 | Laparoscopy Diagnostic with chromopertubation and or adhesiolysis and drilling | True | general_surgery | True | gi_endoscopy, other_clinical |
| 07acf10eaaf58642 | Diagnostic center offering laboratory and imaging services in Amritsar, Punjab | True | laboratory_pathology, other_clinical | True | laboratory_pathology, mri, ct_scan, ultrasound, xray |
| 86ccea3749ea6e43 | Venus Legancy RF | False |  | True | cosmetic_aesthetic |
| 767ee9655f87fe90 | Thrombolysis | True | other_clinical | True | stroke_care |
| 26d37bf26e1679eb | Cardiac care program includes diagnosis, medication and rehabilitation | True | cardiac_surgery, interventional_cardiology | True | cardiac_surgery, icu_critical_care |
| 34ebe46bff510ed9 | Offers advanced orthopedic care including diagnosis and treatment of musculoskeletal disorders, joint replacements, and trauma care | True | orthopedic_surgery, joint_replacement | True | orthopedic_surgery, joint_replacement, trauma_emergency |
| b43bcd85741dc4d6 | Offers outpatient fetal medicine clinic | True | outpatient_opd, obstetrics_maternity | True | obstetrics_maternity |
| 2e4130eb44388fb7 | Conducts Complete Diabetic Check-Up including HbA1c, RBS, and Lipid Profile | True | laboratory_pathology | True | other_clinical |
| 10f7dd951fc1492b | Provides Laser Teeth Whitening | True | dental, cosmetic_aesthetic | True | dental |
| 16e2af7790d1808f | Radiology services available | True | laboratory_pathology, xray, ct_scan, mri, ultrasound | True | xray, ultrasound, ct_scan, mri |
| 83f27f8ce0b2d779 | Provides dental and skin outpatient services | True | dental, outpatient_opd | True | dental, dermatology |
| 163e42f288c12c2f | Focuses on reducing risk and complications of chronic diseases such as asthma, diabetes and heart disease. | False |  | True | pulmonology_respiratory, nephrology_renal, cardiac_surgery |
| 33a2d5bd8f6dc470 | Dermatology staff practicing at Om Multispeciality Hospital, including Dr. Aman Khurana (Dermatologist) | False |  | True | dermatology |
| ac0501ca8f61ef72 | Gynae OPD | True | obstetrics_maternity, outpatient_opd | True | obstetrics_maternity |
| 5aa208f439c86601 | Offers pet clinic services | False |  | True | other_clinical |
| c72b05684f59cc09 | Has a dedicated team of ophthalmic surgeons and support staff | True | eye_surgery, ophthalmology_medical | True | eye_surgery |
| 2db51150f3f4f904 | Audiological evaluation service | True | ent | True | other_clinical |
| 1ef44a0c7aea002b | Offers 122+ treatment options | False |  | True | other_clinical |
| 5251eb7fdae8acbf | Offers orthopaedics and trauma surgery | True | orthopedic_surgery | True | orthopedic_surgery, trauma_emergency |
| 5e160711dc76e7b1 | Performs endoscopic cystogastrostomy for pancreatic pseudocyst. | True | gi_endoscopy, other_clinical | True | gi_endoscopy |
| 26ae7a3e22000ed6 | Retina care program including fundus imaging and fundus autofluorescence | True | eye_surgery, ophthalmology_medical | True | eye_surgery, ultrasound |
| 4cadcd0a33ac30e9 | Thyroid Function Tests | True | other_clinical | True | laboratory_pathology |
| 5bc4788227aebbb4 | Offers health check packages including Master Health Checkup, Well Women Checkup, Cardiac Health Checkup, and Diabetic Health Checkup | True | outpatient_opd, other_clinical | True | outpatient_opd |
| 45faa0fb50b16145 | On-campus Ayurvedic pharmacy that prepares medicines using traditional methods and fresh raw materials | False |  | True | other_clinical |
| 0c36f51a9a234c8c | Power drill and power instruments | False |  | True | orthopedic_surgery |
| dd0e25ac075e6ada | Samples are transported to the Microbiology Department at KIMS in a cold box. | False |  | True | laboratory_pathology |
| 98b27702ebc2637c | Performs uvulopalatopharyngoplasty (UPPP) for sleep apnea. | True | ent | True | other_clinical |
| 9b1496e94266f600 | Initial doctor consultation to assess pain and tailor a personalized treatment plan. | True | outpatient_opd | True | other_clinical |
| 8bb81a700cfb3af1 | Offers sex therapy | True | other_clinical | True | mental_health |
| 01a0fb35e2abf920 | Recurring pregnancy loss clinic | True | obstetrics_maternity | True | obstetrics_maternity, infertility_ivf |
| 2a0fba4c8dae7d7b | Has on-site reproductive genetic testing laboratory | True | laboratory_pathology | True | infertility_ivf, laboratory_pathology |
| 9ba5b720e07f38b0 | Lions Hospital employs a pediatrician named Dr. V N Wasule | False |  | True | pediatrics |
| 6f5a6e2e12d43021 | Believers Regional Institute of Gastroenterology, Hepatology, Transplantation provides Gastrointestinal & Hepatobiliary Surgery and Medical Gastroenterology & Hepatology | True | gastroenterology | True | gastroenterology, general_surgery |
| 451fad5f7d23f211 | Family planning operations | True | obstetrics_maternity, other_clinical | True | obstetrics_maternity |
| d87646ad75c786ad | Branch of Maxivision Super Speciality Eye Hospitals located in Bhimavaram, West Godavari, Andhra Pradesh | True | eye_surgery, ophthalmology_medical | True | eye_surgery |
| c86c8a74337be749 | General Medicine department is available | True | general_surgery | True | other_clinical |
| 59faf09e37543635 | Specializes in facial trauma and pathology of the head and neck region | True | ent | True | ent, trauma_emergency |
| 07e622f485c8860a | Vitreoretinal treatments | True | other_clinical | True | eye_surgery |
| 9c92ed1ddae6e40e | Treats Paralysis | True | other_clinical | True | neurosurgery, physiotherapy_rehab |
| 4263474be82867e0 | Hysterosalpingography (HSG) is available in Radiology Services | True | other_clinical | True | xray |
| e1b48a44198e1dab | Cath lab Philips Intuits | True | interventional_cardiology | True | cardiac_surgery, interventional_cardiology |
| 6216dffac58f711b | Periodontal Flap Surgery offered | True | dental | True | other_clinical |
| d2e28f078428a302 | Multi-specialty healthcare center offering General Surgery, ENT, Gynecology, Orthopedics, Urology, and Diabetology | True | general_surgery, ent, orthopedic_surgery, gastroenterology | True | general_surgery, ent, obstetrics_maternity, orthopedic_surgery |
| 50164efe0add10be | Modular OT and Anaesthesia Facility | True | general_surgery | True | general_surgery, orthopedic_surgery, neurosurgery, cardiac_surgery |
| 6cd3aeb91e63c477 | Described as Best Psychiatric Hospital in Ahmedabad | False |  | True | mental_health |
| 6ca52c4947e61a92 | Dental clinic providing outpatient dental services | True | dental | True | dental, outpatient_opd |
| d55b05031448a2ee | Angiography system for coronary angiography | True | interventional_cardiology | True | ct_scan |
| d96421f910521714 | Performs laparoscopic and hysteroscopic gynecologic surgeries, including vaginal and abdominal hysterectomies | True | obstetrics_maternity, general_surgery | True | general_surgery |
| 98a0a49c0ed413b9 | Listed as a top General Surgery Hospital in Gurgaon Sector 28 | False |  | True | general_surgery |
| fffb80d88cddf90f | Lions Club Of Ghatkopar Charity Fund A/c Medical Centre is a CG Eye Foundation Charitable Eye Clinic – Mehta Eye Clinic centre | False |  | True | eye_surgery |
| bdc796db6c3ac354 | ECG, Chest X-Ray, and 2D Echo services | True | other_clinical | True | xray, ultrasound |
| 1cfff3ed64b482d2 | Manages ovarian tumors | True | gastroenterology | True | cancer_surgery |
| c95c908ce8547b94 | Ayushman Bharat affiliated offering free treatment up to ₹5 lakhs (for eligible beneficiaries) | True | outpatient_opd, trauma_emergency | False |  |
| 403b0ac0c25c1d5f | Offers diagnostic centres in multiple Indian cities including Delhi, Hyderabad, Mumbai, Chennai, Bangalore, Pune, Kolkata, Jaipur, Ahmedabad, Gurgaon, Noida, Lucknow, Madurai, Guwahati, and Amritsar | True | laboratory_pathology, ct_scan, mri, ultrasound, xray | True | laboratory_pathology |
| 0b0898cdff36b101 | Specialties: Muscular Dystrophy | True | other_clinical | False |  |
| 0a359e40573393c5 | Radiology offers Diagnostic & Interventional imaging under Tesla Diagnostic and Imaging | True | mri, ct_scan, ultrasound, interventional_cardiology | True | mri, ct_scan, ultrasound |
| a60745f6757b33d1 | Pediatric SST services | True | pediatrics, other_clinical | True | pediatrics |
| cbae382ea2587eaa | Ayurvedic Panchkarma hospital in Surat | False |  | True | other_clinical |
| 118de5ff688998cd | Steel operating theatres (OTs) | True | general_surgery | True | general_surgery, orthopedic_surgery, cardiac_surgery, neurosurgery, obstetrics_maternity |
| f20cb8c298adfeb6 | Receives 60+ serious pediatric cases annually | False |  | True | pediatrics |
| 0da518024cf67514 | Deshmukh Hospital is a Beed-based hospital where Dr. Ganesh Deshmukh, an orthopedist, practices. | False |  | True | orthopedic_surgery |
| 9f452296ccbecd84 | Ponmalligai Hospital is listed as a top ENT clinic in Madipakkam. | False |  | True | ent |
| 8b0c1bfa23d3d124 | W & H Physiodispenser for Implant and surgical procedures with Implant Kits | True | other_clinical | True | orthopedic_surgery |
| d0364235eaa3376e | 21 ophthalmology specialties | True | eye_surgery | True | ophthalmology_medical |
| 82636c5db8b5f036 | General Ophthalmology services with departments including Cataract, Glaucoma, Cornea, Retina, and Pediatric & Squint | True | eye_surgery | True | eye_surgery, ophthalmology_medical |
| bf7ebc5a4239bd24 | Three modular Class-100 Operating Theatres | True | general_surgery | True | orthopedic_surgery, general_surgery, cardiac_surgery, neurosurgery, obstetrics_maternity |
| 304854c455b166e0 | Provides neurological rehabilitation as part of physiotherapy. | True | physiotherapy_rehab | True | physiotherapy_rehab, neurosurgery |
| ae21d369bd0dbc83 | GE Advanced Cath Lab | True | interventional_cardiology | True | cardiac_surgery, interventional_cardiology |
| f2b6f40b6b240765 | Obstetric and neonatal care services for childbirth and related procedures | True | obstetrics_maternity | True | obstetrics_maternity, nicu |
| b8382e1c78b76450 | 3D imaging of the jaw used for diagnostics | True | other_clinical | True | ct_scan |
| af5e9ca5e0869ebb | Post Delivery Rehabilitation | True | physiotherapy_rehab | True | physiotherapy_rehab, obstetrics_maternity |
| ac35df6358858bb5 | Listed as a diagnostic center in Amritsar (Uppal Neuro Hospital) | True | laboratory_pathology | True | other_clinical |
| 12faedd4e8d69e67 | Offers mental health rehabilitation program (Mental Health Rehab Program) | True | mental_health | True | mental_health, physiotherapy_rehab |
| 023dc00a0fb92ba9 | Day care centre with operating theatre | True | outpatient_opd | True | general_surgery |
| 3d67f896f4f17fb9 | Cosmetic dermatology clinic | True | cosmetic_aesthetic | True | dermatology, cosmetic_aesthetic |
| 432d2489bfcd4c43 | Offers home sampling service | True | outpatient_opd | True | laboratory_pathology |
| a4211371593d630e | Olympus endoscopic instruments | False |  | True | gi_endoscopy |
| d81d64fa6b37ed50 | Self-described as the best ophthalmology hospital in Kerala | True | eye_surgery | True | ophthalmology_medical |
| 831de41e999dfdac | Dedicated oxygen plant | True | icu_critical_care | True | icu_critical_care, ventilator_support |
| c3f5e590f4038982 | Sabouraud's dextrose agar plates | False |  | True | laboratory_pathology |
| 5ac9bbcf0c9c9cb2 | Performs Colour 2D Echocardiography | True | cardiac_surgery, ultrasound | True | ultrasound |
| 4594ec1b65eb2e13 | Laser piles treatment offered | True | general_surgery | True | other_clinical |
| 9f7cdcb54913262c | Specializes in ENT, Anesthesiology, Cardiology, General Surgery, Neurology, Pathology, Physiotherapy, Pulmonology, Radiology and Orthopedics | True | ent, general_surgery, orthopedic_surgery, pulmonology_respiratory | False |  |
| 36e36cc5e0791b89 | Empire Advance Dental Clinic & Implant Centre is listed as a top clinic in Kandivali, Mumbai on Practo | False |  | True | dental |

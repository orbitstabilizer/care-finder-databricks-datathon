# Sentence tagging: details

Script: `scripts/tag_sentences.py` (step1, step2, step3, resume, comment). Compact-prompt side test: `scripts/tag_compact_test.py`. Step-2 summary: `reports/sentence_tagging_step2.md`. Machine logs: `reports/sentence_tagging/{statements,chunks,progress,step1,step2,compact_test}.jsonl`.

Tables (workspace.vf): `sentence_tags` (result, key sentence_id, append only), `sentence_tags_raw` (raw ai_query responses: sentence_id, chunk_id, attempt 1/2, part), `st_type_sets` (facility_types per sentence), `st_queue` (sentences to tag, priority + ord), `st_chunk_members` (chunk_id, sentence_id, part), `tag_compact_test` + `tag_compact_sample` (side test only).

## Step 1

Usable rows: facility_sentences with is_placeholder false, left-joined to facility_type on unique_id (no type row -> '(no_type_row)'; none occurred). 271,262 sentence_ids have a type set.

Sentences appearing in only one facility_type: multispecialty_hospital 96,398; dental 32,147; eye 17,622; diagnostic_imaging_lab 15,449; general_hospital_or_nursing_home 12,491; medical_college_teaching_hospital 11,629; ayush_alternative 8,759; ivf_fertility 7,029; maternity_women_children 6,899; other_single_specialty 5,516; general_clinic_polyclinic 5,329; skin_hair_cosmetic 5,068; ent_hearing_speech 4,587; orthopedic_spine 4,334; cancer 3,652; pediatric 3,359; government_health_centre 3,354; cardiac 3,234; kidney_urology 2,549; mental_health_deaddiction 1,273; physiotherapy_rehab 974; neuro 817; gastro_liver 728; home_care_or_ambulance 368; not_a_care_facility 258; unknown 11. In 2+ types: 17,428.

Dental-only: 32,147 rows written with services ['dental'], prompt_version and chunk_id 'rule_dental_only'. Remaining to tag: 239,115.

## Priority order (st_queue.ord)

Tier 1, keyword (22,236): `sentence_key RLIKE` the regex below (leading word boundary only, so prefixes match, "icu" does not match "particular"):

```
\b(dialysis|haemodialysis|hemodialysis|renal replacement|nephrolog|caesarean|cesarean|c\-section|lscs|delivery|labour|labor room|obstetric|maternity|nicu|neonatal|newborn|neonat|cardiac surgery|cardiothoracic|bypass|cabg|valve|open heart|mri|magnetic resonance|burn|icu|intensive care|critical care|emergency|casualty|trauma|ventilator)
```

Groups: dialysis (dialysis, haemodialysis, hemodialysis, renal replacement, nephrolog); caesarean/delivery (caesarean, cesarean, c-section, lscs, delivery, labour, labor room, obstetric, maternity); NICU (nicu, neonatal, newborn, neonat); cardiac surgery (cardiac surgery, cardiothoracic, bypass, cabg, valve, open heart); MRI (mri, magnetic resonance); burn (burn); ICU/emergency (icu, intensive care, critical care, emergency, casualty, trauma, ventilator).

Tier 2, hospital (145,537): appears in at least one facility typed multispecialty_hospital, general_hospital_or_nursing_home, medical_college_teaching_hospital, government_health_centre, maternity_women_children, pediatric, cardiac, cancer, orthopedic_spine, neuro, gastro_liver, kidney_urology.

Tier 3, rest (71,342). Within a tier: n_facilities desc, then sentence_id. Chunks take the lowest ord first, so tiers are processed strictly in order.

## Validation

As Pilot A (JSON parses; is_claim bool; services list of allowed labels; strength in explicit/stated/weak/na; is_claim false => [] and na; is_claim true => >= 1 label) plus: other_clinical requires a non-empty suggested_name (fail reason missing_suggested_name); names over 4 words are counted, not failed. suggested_name is stored only when services contains other_clinical. Failed rows of a chunk get one retry statement (attempt 2); still-failing rows are stored with failed = true and the attempt-2 fail_reason.

## Step 2 retry log

- tp_single: attempt 1 fails 5 (unparseable 3, unknown_label 2); after retry 4 failed (unparseable 3, unknown_label 1).
- tp_conc4: attempt 1 fails 38 (unparseable 22, unknown_label 13, claim_without_label 3); after retry 25 failed (unparseable 14, unknown_label 9, claim_without_label 2). Typical cause: long department lists where the model writes "radiology" or prose inside the JSON array.
- tp_conc4 first attempt: 3 of 4 parts failed with DELTA_CONCURRENT_APPEND.ROW_LEVEL_CHANGES (the INSERT read sentence_tags_raw for resumability). Fix: removed the self-read; resumability now checks per part in Python. The tp_conc4 raw rows and members were deleted and the arm rerun.

## Per-chunk timings

| chunk | mode | prompt | members | ai_query s | sent/s | retry rows | retry s | failed | chunk total s |
|---|---|---|---|---|---|---|---|---|---|
| tp_single | 1 x 2000 | pa_single_v1 | 2000 | 106.9 | 18.71 | 5 | 7.0 | 4 | 117.9 |
| tp_conc4 | 4 x 500 | pa_single_v1 | 2000 | 71.4 | 28.01 | 38 | 12.6 | 25 | 88.1 |
| x_c001_compact_discarded | 4 x 2500 | pa_compact_v1 | 10000 | 185.2 | 53.99 | 304 | 137.4 | 235 | 334.0 |
| c001 | 4 x 2500 | pa_single_v1 | 10000 | 192.0 | 52.08 | (no per-chunk retry) | - | 180 pending | 202.0 |
| c002 | 4 x 2059 | pa_single_v1 | 8236 | 131.8 | 62.49 | (no per-chunk retry) | - | 138 pending | 141.7 |

Later chunks: see reports/sentence_tagging/chunks.jsonl (written by the detached `resume` process; log reports/sentence_tagging/resume.log).

## Step 3 changes (user instructions mid-run)

- First c001 ran with pa_compact_v1 (chosen by the step-2 rule). The user then required pa_single_v1 for all tiers: its 10,000 rows (235 failed) were deleted from sentence_tags, raw rows renamed to chunk_id x_c001_compact_discarded, members removed; the same 10,000 (front of tier 1) were re-tagged as c001 with pa_single_v1.
- Per-chunk retry removed for step 3. Failed rows are stored with failed = true at chunk time and rerun once at the end in ONE statement (chunk_id final_retry, which also covers the 29 failed tp_* rows); their old rows are deleted and replaced by the final result.
- Chunks are restricted to one tier each, so tiers are processed strictly in order (c002 = last 8,236 of tier 1).
- Keyword tier (22,236) complete at 01:51 UTC: 4,000 in tp_single/tp_conc4 (206.0 s incl. retries) + 18,236 in c001-c002 (343.7 s). 347 failed rows pending the final retry. Background `resume` (tiers 2, 3, final_retry, comments) started 01:51 UTC; a record-audit job shares the warehouse from then on, so later speeds are worst case.

## Credit guard and restart (01:54-01:58 UTC)

- Guard added to tag_sentences.py (CLAUDE.md credits rule): after each chunk's ai_query and before writing, and likewise in final_retry, it stops if (a) any errorMessage matches /quota|credit|billing|limit exceeded|REQUEST_LIMIT_EXCEEDED|RESOURCE_EXHAUSTED|PAYMENT|insufficient/i, (b) more than 30% of rows share one non-empty errorMessage, or (c) any statement exception (including the warehouse failing to start) matches that pattern. On a stop it writes nothing for the chunk, prints "CREDITS EXHAUSTED" + error + done/left to resume.log and reports/sentence_tagging/CREDITS_EXHAUSTED.txt, and exits 0. On resume, a part is reused only if its raw rows cover all members with no errorMessage; otherwise those raw rows are deleted and the part is queried again.
- Old PID 91959 got SIGTERM after c003 was written (tier 2). It had already launched c004's 4 ai_query statements, which kept running on the server. I did not cancel them (that cancel was blocked); they finished at 01:57 with 10,000 error-free raw rows. New PID 94618 (resume.log appended) reused those rows for c004, so c004's logged ai_query_seconds (0.8 s) is not a real timing. c004 took about 160 s of warehouse time (statements launched about 01:54:44, finished by 01:57:29).

## Failure analysis at 02:00 UTC (1,004 failed of 42,236 pa_single_v1 rows)

| chunk | rows | failed | rate | invalid JSON | claim no label | label outside list | truncated | endpoint error | audit overlapping |
|---|---|---|---|---|---|---|---|---|---|
| tp_single | 2000 | 4 | 0.20% | 3 | 0 | 1 | 0 | 0 | no |
| tp_conc4 | 2000 | 25 | 1.25% | 13 | 2 | 9 | 1 | 0 | no |
| c001 | 10000 | 180 | 1.80% | 74 | 19 | 79 | 8 | 0 | no |
| c002 | 8236 | 138 | 1.68% | 75 | 7 | 49 | 7 | 0 | no |
| c003 (tier 2) | 10000 | 295 | 2.95% | 47 | 235 | 13 | 0 | 0 | no (ended 01:54:27; audit began 01:54:54) |
| c004 (tier 2) | 10000 | 362 | 3.62% | 66 | 274 | 22 | 0 | 0 | yes (audit s0 ai_query 01:55:41-01:56:29) |

"Truncated" = unparseable and missing closing brackets: all 16 are runaway prose inside the services array (e.g. `"anesthesiology" is not allowed, use "other_clinical" instead, ...`), up to 29,630 chars, not a short output cut by a token cap. ai_query sets no max_tokens (endpoint default). Not changed: a higher cap would not fix these. Rates: all 2.38%; without claim_no_label 1.11%; without both content reasons 0.70%. The jump in c003/c004 is claim_no_label in tier 2 (hospital boilerplate) and began before the audit, so it is content, not load. Concurrency kept at 4.

## Unlabelled claims (user rule, from c007; 1,041 earlier rows converted in place 02:04 UTC)

is_claim true + services [] is stored as services ['other_clinical'], unlabelled_claim = true, failed = false, strength as returned. Strength of the 1,041: {'weak': 534, 'stated': 63, 'explicit': 265, 'na': 179}. max_tokens 300 set on ai_query from c007 and in final_retry. Failed rate after conversion: 686/62236. Old PID 94618 stopped after c006 was written (02:04:25, before c007 members); new PID 97730.

Top 20 unlabelled-claim sentences (each distinct sentence is one row, so the count is n_facilities it appears in):

| n_facilities | sentence |
|---|---|
| 346 | Multispeciality hospital |
| 270 | Multi-speciality hospital |
| 210 | ECG machine |
| 191 | Multi-specialty hospital |
| 180 | On-site pharmacy |
| 135 | Multi-speciality clinic |
| 99 | ECG |
| 68 | Electrocardiography (ECG) |
| 68 | Operation Theatre |
| 59 | EEG equipment |
| 58 | Operates as a multispeciality hospital |
| 50 | ECG equipment |
| 50 | Radiology department |
| 45 | Is a multispeciality hospital |
| 40 | Has 20 beds |
| 40 | Operation theatres |
| 36 | Performs electrocardiography (ECG) |
| 34 | Is a multi-speciality hospital |
| 34 | Is a multi-specialty hospital |
| 31 | ECG machines |

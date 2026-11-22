# facility_service build (verdict table)

Script: `scripts/build_facility_service.py` (SQL only, no LLM calls; INSERT OVERWRITE, rerunnable).
Built 2026-11-22 01:57:52 UTC; statement took 8.0 s on the 2X-Small warehouse.

## Coverage at build time
- sentence_tags non-failed rows: 67,609 (LLM pa_single_v1 + rule_dental_only) of 271,262 distinct sentences (24.9%).
- record_audit: 100 facilities audited (non-failed) of 9,989 non-shifted. sentence_foreign_flag present.
- Lookup tables service_department_map and service_type_fit present.

## Table changes
- Added columns build_ts, n_sentences_tagged_at_build, n_records_audited_at_build.
- department_backing kept as STRING ('true'/'false') to match the contract type.
- Table and all column comments updated (rules, dental-rule treatment, strong-only backing).

## Choices
- department_backing uses STRONG specialty links only.
- Possible uses implied_by_service links of any strength (strong and supporting).
- Evidence order: explicit, stated, weak; then sentences naming the facility (contamination signal a tokens or city).
- rule_dental_only tags count as is_claim true, strength stated, for dental only.

## Rows: 74,162 total (Confirmed 12,635, Likely 38,316, Possible 10,968, Unverified 12,243)

| service | Confirmed | Likely | Possible | Unverified |
|---|---|---|---|---|
| dialysis | 531 | 406 | 668 | 132 |
| caesarean_section | 33 | 380 | 1,852 | 119 |
| nicu | 485 | 543 | 30 | 97 |
| cardiac_surgery | 449 | 828 | 15 | 566 |
| mri | 732 | 375 | 0 | 207 |
| burn_care | 24 | 128 | 38 | 38 |
| icu_critical_care | 1,164 | 997 | 366 | 239 |
| trauma_emergency | 328 | 2,711 | 61 | 1,032 |

## Test cases (dialysis)
- Aravind Eye Hospital, Hyderabad: Unverified; explicit 4, stated 1, weak 0; backing false; fit unexpected; audit mostly_foreign.
  Warnings: "Record text appears to belong to other organisations (audit: mostly foreign)", "Dialysis is unexpected for an eye facility".
- Kims Icon Hospital, Visakhapatnam (46ed4e88-...): Possible; 0/0/0; backing true (nephrology); fit expected; not audited.
  Warning: "No direct claim; inferred from nephrology department and ICU / critical care, nephrology renal, transplant claim".
  Related sentences are tagged ("Kidney transplantation", "Nephrology", ICU lines).

## Manual review (my judgement), dialysis, 10 random Confirmed + 10 random Likely
- Confirmed: W 0, D 2. Likely: W 0, D 1.
- D: Silchar Medical College, Confirmed on a bare "Dialysis Unit" (a department label, arguably weak).
- D: Gandhi Lincoln Hospital, Confirmed on "Dialysis equipment" + "Dialysis" only.
- D: Vaatsalya Hospitals, Likely on "Dialysis performed at hub hospitals" (network-level, may not be this site).

## App
- vf-locator reads facility_service per service for the 8 APP_SERVICES; sample only for a service with no real rows
  (banner shown then). All 8 have real rows, so no sample rows are shown now. Tier order Confirmed, Likely, Possible, Unverified, then distance.
- Deployed; startup probe in app logs shows real_rows counts and `source=workspace.vf.facility_service is_sample=False` for all 8.
- No new table created, so no new grant; the app SP reads facility_service via existing schema-level SELECT (probe confirms).

---
# Rebuild 2 (2026-11-22 02:05:16 UTC) — user rule changes

Changes in `scripts/build_facility_service.py`:
1. Possible uses STRONG implied_by_service links only. caesarean_section Possible also needs (a) a claim
   (any strength, not foreign) for normal_delivery or high_risk_obstetrics AND (b) a general_surgery claim
   OR a usable non-foreign sentence of the facility matching OT_PATTERN, applied to the original sentence:
   `(?i:operation theatre|operating theatre|operation theater|operating theater|surgical theatre|modular ot)|(?<![A-Za-z])OT(?![A-Za-z])`
   (phrases case-insensitive; bare OT case-sensitive, whole word). Checked: matches "2 OT complex",
   "Modular ot", "Operation Theatre"; does not match "Physiotherapy", "other services", "ot room", "OTs".
2. Possible evidence = only explicit/stated sentences of the triggering related service(s), deduplicated.
3. Explicit sentence with no digit and < 5 words counts as stated (sentence_tags untouched).
Also fixed: partly-foreign warning lost its apostrophe ("record's"); duplicate evidence sentences (0 now).

Coverage: before = 67,609 tags / 100 audited (stamps of build 1; at rebuild time live tables had
83,010 / 2,805). After = 93,697 tags / 4,157 audited.

| service | before C/L/P/U | after C/L/P/U |
|---|---|---|
| dialysis | 531/406/668/132 | 341/574/249/123 |
| caesarean_section | 33/380/1852/119 | 32/376/335/61 |
| nicu | 485/543/30/97 | 432/581/0/114 |
| cardiac_surgery | 449/828/15/566 | 387/1026/0/597 |
| mri | 732/375/0/207 | 489/683/0/259 |
| burn_care | 24/128/38/38 | 21/124/0/40 |
| icu_critical_care | 1164/997/366/239 | 1049/1102/121/288 |
| trauma_emergency | 328/2711/61/1032 | 317/2638/0/1099 |

Kims Icon dialysis: Possible, evidence "Nephrology", "Renal Sciences institute" (kidney transplantation not
quoted: transplant -> dialysis is a supporting link, so it no longer triggers). Aravind: Unverified, unchanged.
caesarean_section Possible review (10 random, my judgement): W 1 (Aashirwad Ortho & Dental Care Centre,
OBGYN/NICU text likely from another org), D 1 (Rajindra Hospital, Patiala: quotes "provided by Amar Hospital").

---
# Rebuild 3 (2026-11-22 02:17:37 UTC) + app changes

Demote-to-weak (constants in scripts/build_facility_service.py; Java regex, case-insensitive, original sentence):
- HEDGE_RE `\b(planned|proposed|upcoming|will be|to be (started|commissioned|set up)|under construction|coming soon)\b`
- COMMENT_RE `\([^)]*\b(not explicit|not listed|not mentioned|explicit|explicitly|mentioned|listed|stated|specified|implied|unclear|inferred)\b`
- ELSEWHERE_RE `\b(oversees|supervises|across \d+ districts|at hub hospitals|in other districts|network of|partner hospitals)\b`
- Negation within 4 words of the service term: `\b(?:not|unavailable|no)\b(?!\.)(?:\W+\w+){0,4}?\W+(?:TERM)\b`
  or `\b(?:TERM)(?:\W+\w+){0,4}?\W+(?:not|unavailable|no)\b(?!\.)`; TERM from SERVICE_TERMS (else label with spaces).
Demoted sentences are never quoted for Confirmed/Likely. 139 claim pairs demoted (126 from explicit/stated; dialysis 10).
Mixed record: Unverified if mostly_foreign or (partly_foreign and n_flagged/n_usable >= 0.5); warning
"Parts of this record may describe a different hospital. Call to confirm." if mostly_foreign or share >= 0.25.
Flagged-share bands (9,575 audited): 0: 5,877 | >0-0.1: 2,023 | >0.1-<0.25: 965 | 0.25-<0.5: 509 | >=0.5: 201.
Warning on 5,586 rows / 731 facilities. Dialysis C/L/P/U: 331/544/259/157 (was 341/574/249/123 at 93,697 tags).
Added column n_sentences_attempted_at_build. Watcher: scripts/rebuild_watcher.py, log reports/rebuild_watcher.log.

---
# Rebuild 4 (2026-11-22 02:27:59 UTC) + app round 3
- Evidence order: explicit > stated > weak, then has-digit, then longer; near-duplicates (lowercase, punctuation and
  thousands separators removed, spaces collapsed) quoted once. Demoted sentences still excluded for Confirmed/Likely.
- facility_service: added facility_type, flagged_share. New table workspace.vf.build_stats (metric, value, build_ts),
  rewritten each build; app SP granted SELECT.
- facilities_clean: added official_phone in place (ALTER + MERGE from share; 9,513 of 10,077 non-null).
- App: per-tier sections (5 shown, +5 to 20; Unverified collapsed), nearest-per-tier summary, "Why this result · Details"
  expander, marker popups, "How this works" from build_stats, free-text matcher (one LLM call per distinct text,
  databricks-meta-llama-3-3-70b-instruct, app resource llm-endpoint CAN_QUERY).
- Rebuild 5 (02:35:00 UTC): Possible warnings use readable names from app/config.py SERVICE_NAME
  ("inferred from the nephrology department and a nephrology (kidney care) claim").
- App map: India view (centre 22.5, 82.5, zoom 5, min_zoom 4, pan limited to 6-37.5 N, 68-98 E), gray mask outside
  app/india.geojson (Natural Earth 1:110m India, buffered 0.15 deg, simplified 0.02 deg; no Andaman/Lakshadweep),
  clicks outside the outline -> "Please choose a point in India". Unverified section is a toggle (no nested expanders).

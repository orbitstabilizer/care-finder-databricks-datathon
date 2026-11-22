# Clean base tables — build report (2026-11-21)

Built by a sub-agent, verified by the orchestrator (row counts, flag counts, checks, comments).
Script: `scripts/build_clean_base.py` (re-run to rebuild; `report` argument prints the report only).

## Row counts
| table | rows |
|---|---|
| source facilities | 10,088 |
| workspace.vf.facilities_clean | 10,077 (one per unique_id) |
| workspace.vf.facility_sentences | 451,110 |
| workspace.vf.distinct_sentences | 271,262 (sentence_id unique) |

## facilities_clean
- 11 exact duplicate rows removed.
- Shifted-row tests (10,077 rows): is_shifted 88; coords_missing 118 (30 not shifted); coords_outside_india 6 (all not shifted);
  country_not_india 88 (same as is_shifted); id_not_uuid 88 (same as is_shifted). is_shifted catches every column-shifted row;
  the 36 extra rows are ordinary records with missing or scrambled coordinates.
- Out-of-India examples: Krishna Hospital Multispeciality, Lucknow (-81.71, 26.95); Cura Imaging & Gastro Clinic, Nagpur (2.95, 41.39);
  Cardia Health Care, Noida (7.71, 109.69); The Family Tree Hospital, Tirupati (32.96, 7.48); Hazaribagh (46.07, 106.17); Chengannur (59.95, -38.26).
- name/city/state/postcode trimmed; '', 'null', 'none' -> NULL (name NULL 65, city 64, state 63).
- postcode: whitespace stripped; postcode_valid (^[1-9][0-9]{5}$) 9,909; invalid 102; NULL 66.
- Integers (try_cast): numberDoctors 3,628 parsed (3 fail; range 0–15,000); capacity 2,511 (3 fail; 0–200,000);
  yearEstablished 4,781 (16 fail; 0–2025). All failures are in shifted rows. Implausible values (0, 200,000) are kept as parsed.
- specialties: sorted array of distinct values (9,959 rows non-empty).
- official_domain: 8,381 rows (32 non-hostname values set NULL). source_domains: 9,959 rows.
- Kept: unique_id, description, facilityTypeId, operatorTypeId, affiliationTypeIds, latitude, longitude.

## facility_sentences
- One row per item of procedure/capability/equipment of deduplicated facilities. position = 0-based array index.
- 459,647 parsed items; 8,537 empty dropped. Shifted facilities contribute 0 sentences (their list columns are not JSON).
| column | kept | placeholder | repeat | usable |
|---|---|---|---|---|
| procedure | 163,647 | 544 | 10,169 | 152,935 |
| capability | 231,465 | 23 | 11,695 | 219,748 |
| equipment | 55,998 | 433 | 4,558 | 51,023 |
| all | 451,110 | 1,000 | 26,422 | 423,706 |
- Placeholder rules (first match stored in placeholder_rule): P1_exact (none, n/a, nil, "-", not specified...), P2_source_absent
  ("no ... in the provided content"), P3_not_listed_note ("(not listed) — skip"), P4_generic_absence ("no procedures listed").
  Reviewed by eye; real claims like "no-cost EMI", "not-for-profit hospital" are not flagged.
- Repeat = same sentence_key within a facility; first occurrence (procedure, capability, equipment, then position) unflagged.
- Top placeholders: "no explicit clinical procedures listed in the provided content" (12), "-" (8),
  "no specific clinical procedures listed in provided content" (7), "no specific medical equipment listed in provided content" (6), "n/a" (4), "nil" (4).

## distinct_sentences
- One row per sentence_key; placeholders and shifted facilities excluded. sentence_id = first 16 hex of sha2(sentence_key, 256).
- example_sentence = most frequent original form. n_occurrences includes repeats.
- Top: Dental implants (574 facilities), Outpatient dental clinic (534), CT scanner (525), Operates 24/7 (508),
  Provides 24/7 emergency care (489), Wheelchair accessible entrance and exit (487), Root canal treatment (484), NABH accredited (463).

## Facilities with zero usable sentences
60 of 9,989 non-shifted facilities (all had no items at all), plus the 88 shifted ones.

## Checks (all PASS, re-verified by orchestrator)
- facilities_clean: 10,077 rows = 10,077 distinct unique_id.
- facility_sentences 451,110 + 8,537 dropped empty = 459,647 parsed items.
- sum(distinct_sentences.n_occurrences) 450,110 = non-placeholder sentences from non-shifted facilities.
- Table comments on all three tables; every column commented (23 / 8 / 5).

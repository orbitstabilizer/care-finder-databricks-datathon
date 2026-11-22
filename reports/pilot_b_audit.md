# Pilot B: record audit with sentence-level output (prompt pb_v1)

Model `databricks-meta-llama-3-3-70b-instruct`, temperature 0 (retry 0.3), max_tokens 800, one record per ai_query row, on the shared 2X-Small warehouse 8ea2282aca435351. Script `scripts/pilot_b_audit.py`. Tables `workspace.vf.pb_records, pb_sentences, pb_prompt, pb_raw_*, pb_audit, pb_sentence_flags, pb_timings`.

## Runs

- Stage 0 run 1 (strict parser): valid 3/5, failed 2 (unparseable JSON: unquoted ranges like `35-38`); ai_query wall {'1': 44.92, '2': 8.9} s (attempt: seconds). Tables `pb_raw_s0_a1`, `pb_raw_s0_a2`.
- Fix (a) applied (user decision): pre-parse normalisation quotes bare `a-b` tokens inside lists (regex `([\[,]\s*)(\d+)\s*-\s*(\d+)(\s*)(?=[,\]])`), and digit strings like `"7"` are accepted as integers. No prompt change.
- Stage 0 run 2 (same 5 records, new calls): valid 5/5, failed 0; ai_query wall {'1': 6.17} s. Table `pb_raw_s0r2_a1`.
- Stage 1 (56 records, one statement): valid 56/56, failed 0; ai_query wall {'1': 10.69} s. Retries needed: 0.
- Note: temperature 0 is not deterministic here. Aravind flagged 63/149 in run 1 and 79/149 in run 2.

### Statement timings (UTC)

| statement | start | end | s |
|---|---|---|---|
| select random consistent | 2026-11-22T01:12:11+00:00 | 2026-11-22T01:12:11+00:00 | 0.49 |
| create pb_records_in | 2026-11-22T01:12:11+00:00 | 2026-11-22T01:12:13+00:00 | 1.54 |
| insert pb_records_in | 2026-11-22T01:12:13+00:00 | 2026-11-22T01:12:14+00:00 | 1.2 |
| create pb_sentences | 2026-11-22T01:12:14+00:00 | 2026-11-22T01:12:16+00:00 | 2.49 |
| create pb_records | 2026-11-22T01:12:16+00:00 | 2026-11-22T01:12:19+00:00 | 2.54 |
| create pb_prompt | 2026-11-22T01:12:19+00:00 | 2026-11-22T01:12:21+00:00 | 2.37 |
| summary pb_records | 2026-11-22T01:12:21+00:00 | 2026-11-22T01:12:22+00:00 | 0.39 |
| inspect prompt | 2026-11-22T01:12:30+00:00 | 2026-11-22T01:12:30+00:00 | 0.31 |
| stage0 list | 2026-11-22T01:12:35+00:00 | 2026-11-22T01:12:36+00:00 | 0.33 |
| stage0 ai_query attempt1 (5 rows) | 2026-11-22T01:12:36+00:00 | 2026-11-22T01:13:21+00:00 | 44.92 |
| stage0 read attempt1 | 2026-11-22T01:13:21+00:00 | 2026-11-22T01:13:21+00:00 | 0.79 |
| stage0 ai_query attempt2 (2 rows) | 2026-11-22T01:13:21+00:00 | 2026-11-22T01:13:30+00:00 | 8.9 |
| stage0 read attempt2 | 2026-11-22T01:13:30+00:00 | 2026-11-22T01:13:31+00:00 | 0.4 |
| create pb_audit | 2026-11-22T01:13:31+00:00 | 2026-11-22T01:13:32+00:00 | 1.35 |
| stage0 clear pb_audit | 2026-11-22T01:13:32+00:00 | 2026-11-22T01:13:33+00:00 | 0.73 |
| stage0 insert pb_audit | 2026-11-22T01:13:33+00:00 | 2026-11-22T01:13:34+00:00 | 1.18 |
| create pb_sentence_flags | 2026-11-22T01:13:34+00:00 | 2026-11-22T01:13:35+00:00 | 1.4 |
| stage0 clear flags | 2026-11-22T01:13:35+00:00 | 2026-11-22T01:13:36+00:00 | 0.76 |
| stage0 insert flags | 2026-11-22T01:13:36+00:00 | 2026-11-22T01:13:37+00:00 | 1.31 |
| inspect raw | 2026-11-22T01:13:45+00:00 | 2026-11-22T01:13:45+00:00 | 0.51 |
| inspect raw | 2026-11-22T01:13:45+00:00 | 2026-11-22T01:13:46+00:00 | 0.34 |
| stage0 list | 2026-11-22T01:21:28+00:00 | 2026-11-22T01:21:28+00:00 | 0.31 |
| stage0r2 ai_query attempt1 (5 rows) | 2026-11-22T01:21:28+00:00 | 2026-11-22T01:21:34+00:00 | 6.17 |
| stage0 read attempt1 | 2026-11-22T01:21:34+00:00 | 2026-11-22T01:21:35+00:00 | 0.43 |
| create pb_audit | 2026-11-22T01:21:35+00:00 | 2026-11-22T01:21:35+00:00 | 0.18 |
| stage0 clear pb_audit | 2026-11-22T01:21:35+00:00 | 2026-11-22T01:21:36+00:00 | 0.87 |
| stage0 insert pb_audit | 2026-11-22T01:21:36+00:00 | 2026-11-22T01:21:37+00:00 | 0.82 |
| create pb_sentence_flags | 2026-11-22T01:21:37+00:00 | 2026-11-22T01:21:37+00:00 | 0.19 |
| stage0 clear flags | 2026-11-22T01:21:37+00:00 | 2026-11-22T01:21:38+00:00 | 1.01 |
| stage0 insert flags | 2026-11-22T01:21:38+00:00 | 2026-11-22T01:21:39+00:00 | 1.02 |
| stage1 list | 2026-11-22T01:21:45+00:00 | 2026-11-22T01:21:45+00:00 | 0.31 |
| stage1 ai_query attempt1 (56 rows) | 2026-11-22T01:21:45+00:00 | 2026-11-22T01:21:56+00:00 | 10.69 |
| stage1 read attempt1 | 2026-11-22T01:21:56+00:00 | 2026-11-22T01:21:57+00:00 | 0.37 |
| create pb_audit | 2026-11-22T01:21:57+00:00 | 2026-11-22T01:21:57+00:00 | 0.19 |
| stage1 clear pb_audit | 2026-11-22T01:21:57+00:00 | 2026-11-22T01:21:57+00:00 | 0.58 |
| stage1 insert pb_audit | 2026-11-22T01:21:57+00:00 | 2026-11-22T01:21:58+00:00 | 0.98 |
| create pb_sentence_flags | 2026-11-22T01:21:58+00:00 | 2026-11-22T01:21:58+00:00 | 0.19 |
| stage1 clear flags | 2026-11-22T01:21:58+00:00 | 2026-11-22T01:21:59+00:00 | 0.7 |
| stage1 insert flags | 2026-11-22T01:21:59+00:00 | 2026-11-22T01:22:00+00:00 | 1.18 |
| report fetch | 2026-11-22T01:22:53+00:00 | 2026-11-22T01:22:53+00:00 | 0.51 |
| count projection base | 2026-11-22T01:22:53+00:00 | 2026-11-22T01:22:54+00:00 | 0.47 |
| fetch city list | 2026-11-22T01:22:54+00:00 | 2026-11-22T01:22:54+00:00 | 0.32 |
| fetch mf sentence flags | 2026-11-22T01:22:54+00:00 | 2026-11-22T01:22:54+00:00 | 0.41 |
| report fetch | 2026-11-22T01:23:06+00:00 | 2026-11-22T01:23:06+00:00 | 0.21 |
| count projection base | 2026-11-22T01:23:06+00:00 | 2026-11-22T01:23:06+00:00 | 0.16 |
| fetch city list | 2026-11-22T01:23:06+00:00 | 2026-11-22T01:23:06+00:00 | 0.17 |
| fetch mf sentence flags | 2026-11-22T01:23:06+00:00 | 2026-11-22T01:23:06+00:00 | 0.19 |
| report fetch | 2026-11-22T01:23:15+00:00 | 2026-11-22T01:23:15+00:00 | 0.23 |
| count projection base | 2026-11-22T01:23:15+00:00 | 2026-11-22T01:23:15+00:00 | 0.17 |
| fetch city list | 2026-11-22T01:23:15+00:00 | 2026-11-22T01:23:15+00:00 | 0.16 |
| fetch mf sentence flags | 2026-11-22T01:23:15+00:00 | 2026-11-22T01:23:16+00:00 | 0.19 |
| report fetch | 2026-11-22T01:23:26+00:00 | 2026-11-22T01:23:26+00:00 | 0.58 |
| count projection base | 2026-11-22T01:23:26+00:00 | 2026-11-22T01:23:27+00:00 | 0.17 |
| fetch city list | 2026-11-22T01:23:27+00:00 | 2026-11-22T01:23:27+00:00 | 0.16 |
| fetch mf sentence flags | 2026-11-22T01:23:27+00:00 | 2026-11-22T01:23:27+00:00 | 0.18 |

## Speed

- Final runs: 16.9 s ai_query wall for 61 records = 0.28 s/record. Stage 1 alone: 0.19 s/record.
- Worst observed: stage 0 run 1, 8.98 s/record (5 rows, first call of the session).
- Projection base: 9577 non-shifted facilities with >= 5 usable sentences. Projected 44 min at 0.28 s/rec; 1434 min at the worst observed 8.98 s/rec. Shared warehouse; batches of 56 may not scale linearly.

## Verdict now vs before

| before \ now | consistent | partly_foreign | mostly_foreign |
|---|---|---|---|
| consistent | 20 | 0 | 0 |
| partly_foreign | 1 | 14 | 0 |
| mostly_foreign | 0 | 9 | 16 |

(Aravind had no earlier verdict: mostly_foreign.)

## Verdict now vs earlier reviewer marks (40 reviewed)

| mark \ now | consistent | partly_foreign | mostly_foreign |
|---|---|---|---|
| W | 1 | 11 | 2 |
| D | 0 | 4 | 1 |
| agree | 0 | 8 | 13 |

Agree-marked rows keeping their earlier verdict: 16/21.

## W records (2/14 now right; right = verdict equals reviewer target)

| row | name | city | before | target | now | flagged/N | right | reviewer note |
|---|---|---|---|---|---|---|---|---|
| 5 | Homeocare International | Belgaum | mostly_foreign | consistent | mostly_foreign | 23/40 | no | own-chain branches; should be consistent |
| 12 | Sood Dental Care And Implant Centre | Jalandhar | mostly_foreign | partly_foreign | partly_foreign | 15/64 | yes | eye ~25%; partly |
| 13 | Shri Komal Hospital and Dr Saxena Nursin | Kanmajra | mostly_foreign | consistent | partly_foreign | 11/54 | no | same hospital has ophthalmology |
| 18 | Shivam Hospital | Jodhpur | mostly_foreign | partly_foreign | mostly_foreign | 6/28 | no | dental core is Jodhpur; ~25% foreign |
| 26 | Dr Sumesh's Homoeopathic Speciality Cent | Kozhikode | partly_foreign | consistent | partly_foreign | 6/19 | no | branches; consistent |
| 28 | Shri B.M.Patil Medical College, Hospital | Vijayapura | partly_foreign | consistent | partly_foreign | 3/72 | no | Bijapur = Vijayapura |
| 29 | Athani Hospital | Puthur | partly_foreign | consistent | partly_foreign | 4/27 | no | Puthur is in Palakkad |
| 30 | Ruckmoni Memorial Devi Hospital | Neyyattinkara | partly_foreign | consistent | partly_foreign | 2/30 | no | same trust; same taluk |
| 33 | Aum Eye Hospital | Jamnagar | partly_foreign | mostly_foreign | partly_foreign | 29/69 | no | UNDER-called: mostly_foreign |
| 34 | Surya Dental Clinic | Berhampur | partly_foreign | consistent | consistent | 0/35 | yes | Brahmapur = Berhampur |
| 35 | Bapu Ayurvedic Medical College & Hospita | Kopaganj | partly_foreign | consistent | partly_foreign | 3/42 | no | Kopaganj is in Mau district |
| 36 | Rani Durgavati Medical College, Banda | Banda | partly_foreign | consistent | partly_foreign | 11/28 | no | affiliations, not foreign content |
| 37 | Safe Hands Hospital | Gurugram | partly_foreign | consistent | partly_foreign | 9/67 | no | all Gurgaon sectors |
| 38 | Dental Expressions | Thane West | partly_foreign | consistent | partly_foreign | 1/24 | no | own branch |

Mapping note: the brief says 13 over/under-called cases; the review lists 14 W rows, all with a stated target (4 mostly_foreign W rows, 9 over-called partly_foreign, 1 under-called). Row 36 (Rani Durgavati, 'affiliations, not foreign content') is mapped to consistent. Row 12 and 18 targets are partly_foreign ('~25% foreign'). Targets come from the review table in the session transcript; the JSON files hold no marks.

D rows (no target): J J Eye Hospital mostly_foreign->partly_foreign (much is JJ group itself); Ahalia Foundation Eye Hospital partly_foreign->partly_foreign (parent campus/branches); Fortis Hospital partly_foreign->partly_foreign (same group); Sai Baba Eye Hospital, Raipur, mostly_foreign->mostly_foreign (eye content dominant; partly); Sadguru Hospitals mostly_foreign->partly_foreign (generic services unattributable)

## Flagged share vs model foreign_share

| verdict now | n | mean flagged share | mean foreign_share |
|---|---|---|---|
| consistent | 21 | 0.000 | 0.000 |
| partly_foreign | 23 | 0.159 | 0.322 |
| mostly_foreign | 17 | 0.385 | 0.715 |

Pearson r = 0.840, Spearman = 0.924, mean |flagged share - foreign_share| = 0.158. Verdict implied by flagged share (<0.05 consistent, >0.5 mostly, else partly) matches the model verdict in 77% of 61 records.
mostly_foreign records whose flagged list covers > 50% of sentences: 6/17; partly_foreign records with 0 flagged: 0.

## mostly_foreign: what the UNFLAGGED sentences name

Rule (mechanical, applied in order): **own** = sentence contains a distinctive name token of the record (record name lowercased, split on non-alphanumerics, tokens >= 4 chars, not in the generic list of contamination signal a, not any city name in facilities_clean; whole-word match) or the record's city string (case-insensitive substring). Else **other org** = matches regex `\b(?:[A-Z][\w.'&-]*\s+){1,6}(?:Hospitals?|Clinic|Centre|Center|Institute|College|Nursing Home)\b` (1-6 capitalised words ending in Hospital(s)/Clinic/Centre/Center/Institute/College/Nursing Home). Else **nobody**. A sentence naming both own and another org counts as own.

| name | city | N | flagged | unflagged | own | nobody | other org |
|---|---|---|---|---|---|---|---|
| Bansal Hospital | Barwala | 55 | 16 | 39 | 6 | 32 | 1 |
| Ashirwad Hospital | Bhiwandi | 76 | 14 | 62 | 13 | 44 | 5 |
| Lakshmi Hospital | Ambasamudram | 86 | 28 | 58 | 9 | 48 | 1 |
| Narayanam Hospital | Katni | 21 | 9 | 12 | 1 | 10 | 1 |
| Ojas Hospital | Pune | 124 | 27 | 97 | 2 | 95 | 0 |
| Shivam Hospital | Jodhpur | 28 | 6 | 22 | 2 | 20 | 0 |
| Sai Baba Eye Hospital, Raipur, Chhattisg | Raipur | 99 | 7 | 92 | 8 | 84 | 0 |
| Sadhana Diabetes & Hormone’s Clinic , Da | Mumbai | 134 | 79 | 55 | 1 | 54 | 0 |
| Homeocare International | Belgaum | 40 | 23 | 17 | 4 | 13 | 0 |
| Kalptaru Hospital | Nanded | 37 | 5 | 32 | 0 | 29 | 3 |
| Shree Hospital | Valsad | 69 | 44 | 25 | 0 | 25 | 0 |
| Sakar Hospital | Ahmedabad | 101 | 43 | 58 | 7 | 47 | 4 |
| Pratham Hospital | Dahegam | 31 | 11 | 20 | 2 | 17 | 1 |
| Employees' State Insurance Corporation D | Sirhind | 74 | 43 | 31 | 4 | 27 | 0 |
| Aravind Eye Hospital | Hyderabad | 149 | 79 | 70 | 2 | 65 | 3 |
| Gajanan Hospital | Satara | 21 | 11 | 10 | 3 | 7 | 0 |
| Government Ayurvedic Hospital | Makhiyala | 24 | 11 | 13 | 6 | 7 | 0 |
| **total** | | 1169 | 456 | 713 | 70 | 624 | 19 |

Name tokens used: Bansal Hospital: ['bansal']; Ashirwad Hospital: ['ashirwad']; Lakshmi Hospital: ['lakshmi']; Narayanam Hospital: ['narayanam']; Ojas Hospital: ['ojas']; Shivam Hospital: ['shivam']; Sai Baba Eye Hospital, Ra: ['baba', 'chhattisgarh']; Sadhana Diabetes & Hormon: ['diabetes', 'hormone', 'sadhana', 'west']; Homeocare International: ['homeocare', 'international']; Kalptaru Hospital: ['kalptaru']; Shree Hospital: []; Sakar Hospital: ['sakar']; Pratham Hospital: ['pratham']; Employees' State Insuranc: ['behla', 'corporation', 'dispensary', 'employees', 'insurance', 'mohalla', 'state']; Aravind Eye Hospital: ['aravind']; Gajanan Hospital: ['gajanan']; Government Ayurvedic Hosp: ['ayurvedic', 'government']

## Per-record table (all 61)

| grp | row | mark | name | city | before | now | fshare | flagged/N | att | foreign_sentences | other_names | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| aravind |  |  | Aravind Eye Hospital | Hyderabad | None | mostly_foreign | 0.7 | 79/149 | 1 | `["54-57", "73-93", "95-99", "101-149"]` | ["Madras Medical Mission", "Janakpuri Super Speciality Hospital", "Lok Nayak Hospital"] | Multiple hospital names |
| random_consistent |  |  | Ace Dental Clinic and Implant Centre | Nerul West | consistent | consistent | 0.0 | 0/27 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Advanced E.N.T. and Multispeciality Hosp | Aurangabad | consistent | consistent | 0.0 | 0/37 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | All India Institute of Ayurveda, New Del | New Delhi | consistent | consistent | 0.0 | 0/80 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Amrit Clinic | New Rajender Nagar | consistent | consistent | 0.0 | 0/31 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Archana Multispeciality Hospital | Tirupati | consistent | consistent | 0.0 | 0/21 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Balaji Hospital | Ludhiana | consistent | consistent | 0.0 | 0/35 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Bangalore Institute Of Gastroenterology  | Bangalore | consistent | consistent | 0.0 | 0/97 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Care AKPS Hospital | Virudhunagar | consistent | consistent | 0.0 | 0/43 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Chella Suriya Orthopaedic Hospital | Tirunelveli | consistent | consistent | 0.0 | 0/41 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Clear Vision Eye Centre | Mumbai | consistent | consistent | 0.0 | 0/31 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Dhami Eye Care Hospital | Ludhiana | consistent | consistent | 0.0 | 0/44 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Dr. Prashant Bakshi | Pune | consistent | consistent | 0.0 | 0/25 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Gargi Hospital | Ghaziabad | consistent | consistent | 0.0 | 0/71 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Kabeer Clinic | Chennai | consistent | consistent | 0.0 | 0/35 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Kanyakumari Government Medical College | Asaripallam | consistent | consistent | 0.0 | 0/84 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Piles Care Point | Dehradun | consistent | consistent | 0.0 | 0/22 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Pills Hospital | Coimbatore | consistent | consistent | 0.0 | 0/66 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Shiv Orthopaedic Hospital | Surat | consistent | consistent | 0.0 | 0/26 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Smiles Unlimited Dental Care | Pune | consistent | consistent | 0.0 | 0/33 | 1 | `[]` | [] | No foreign sentences found |
| random_consistent |  |  | Vijay Multi-Speciality Dental Hospital - | Kondapur | consistent | consistent | 0.0 | 0/76 | 1 | `[]` | [] | No foreign sentences found |
| reviewed_mf | 1 |  | Pratham Hospital | Dahegam | mostly_foreign | mostly_foreign | 0.7 | 11/31 | 1 | `["1-3", "8", "11", "13", "15", "17", "18", "21", "23"]` | ["Aman Dental Care", "Prathna Hospital", "Pratha Hospital"] | Multiple locations |
| reviewed_mf | 2 |  | Lakshmi Hospital | Ambasamudram | mostly_foreign | mostly_foreign | 0.7 | 28/86 | 1 | `["30-40", "42", "46", "52-55", "57-63", "71-74"]` | ["Laksmi Hospital", "Lakshmi Fertility Centre", "Lakshmi Institute of Fertillity and Endoscopy"] | Multiple locations |
| reviewed_mf | 3 |  | Kalptaru Hospital | Nanded | mostly_foreign | mostly_foreign | 0.8 | 5/37 | 1 | `["4", "16", "21", "25", "28"]` | [] | Multiple locations mentioned |
| reviewed_mf | 4 |  | Employees' State Insurance Corporation D | Sirhind | mostly_foreign | mostly_foreign | 0.7 | 43/74 | 1 | `["1-4", "7-9", "20-24", "28-33", "49-64", "66-74"]` | ["Civil Hospital, Abohar", "Rural Hospital, Kup Kalan", "Civil Hospital, Wraich Road, Samana", "Malhotra Dental Clinic", | Multiple facilities described |
| reviewed_mf | 5 | W | Homeocare International | Belgaum | mostly_foreign | mostly_foreign | 0.8 | 23/40 | 1 | `["7", "9-14", "21-23", "26-38"]` | [] | Multiple locations described |
| reviewed_mf | 6 | D | Sai Baba Eye Hospital, Raipur, Chhattisg | Raipur | mostly_foreign | mostly_foreign | 0.7 | 7/99 | 1 | `["55", "61-63", "90-91", "99"]` | ["Om hospital", "Om Netra Kendra"] | Multiple foreign hospitals described |
| reviewed_mf | 7 |  | Apollo Gleneagles Hospitals | Kolkata | mostly_foreign | partly_foreign | 0.27 | 7/143 | 1 | `[27, 53, 56, 57, 58, 71, 72]` | ["AMRI Hospitals", "Columbia Asia Hospital"] | Multiple hospital names |
| reviewed_mf | 8 |  | Om Hospital | Nashik | mostly_foreign | partly_foreign | 0.43 | 30/142 | 1 | `["52-62", "76", "77", "78", "79-84", "88-91", "92-97"]` | [] | Multiple locations described |
| reviewed_mf | 9 |  | Ojas Hospital | Pune | mostly_foreign | mostly_foreign | 0.7 | 27/124 | 1 | `["8-9", "40-44", "52-55", "58", "63-72", "78-82"]` | ["ORAS Hospital"] | Multiple locations mentioned |
| reviewed_mf | 10 |  | Narayanam Hospital | Katni | mostly_foreign | mostly_foreign | 0.7 | 9/21 | 1 | `[6, 8, "10-15", 16]` | ["Narayana Hospital", "Dharamshila Narayana Superspeciality Hospital", "Nh Mmi Narayana Multispeciality Hospital", "Brah | Different hospital names |
| reviewed_mf | 11 |  | Gajanan Hospital | Satara | mostly_foreign | mostly_foreign | 0.85 | 11/21 | 1 | `["1-2", "5-8", "12", "14", "17", "19", "21"]` | [] | Multiple locations mentioned |
| reviewed_mf | 12 | W | Sood Dental Care And Implant Centre | Jalandhar | mostly_foreign | partly_foreign | 0.4 | 15/64 | 1 | `["5-12", 28, 30, "44-45", 48, 57, 64]` | ["Sood Eye Care Centre"] | Ophthalmology services |
| reviewed_mf | 13 | W | Shri Komal Hospital and Dr Saxena Nursin | Kanmajra | mostly_foreign | partly_foreign | 0.5 | 11/54 | 1 | `["41-51"]` | [] | Mixed hospital descriptions |
| reviewed_mf | 14 |  | Bansal Hospital | Barwala | mostly_foreign | mostly_foreign | 0.7 | 16/55 | 1 | `["4", "6", "7", "8", "20", "22", "26", "27", "36", "38", "39", "40", "43", "48", "51", "52"]` | ["Kansal Hospital"] | Multiple locations |
| reviewed_mf | 15 |  | Medical College Hospital | Thiruvananthapuram | mostly_foreign | partly_foreign | 0.4 | 6/32 | 1 | `[11, 13, 32, "12-14", 31]` | ["Government Medical College, Thrissur"] | Multiple locations mentioned |
| reviewed_mf | 16 |  | Government Ayurvedic Hospital | Makhiyala | mostly_foreign | mostly_foreign | 0.7 | 11/24 | 1 | `["4", "6", "11", "12", "14", "16", "17", "18", "19", "23", "24"]` | ["Government Ayurvedic Hospital, Amreli", "Government Ayurved Hospital, Amreli", "Government Ayurvedic Hospital - Bhuj"] | Multiple locations mentioned |
| reviewed_mf | 17 |  | Ashirwad Hospital | Bhiwandi | mostly_foreign | mostly_foreign | 0.7 | 14/76 | 1 | `["29", "30", "33", "35", "38", "40-43", "45", "47", "55", "57", "60"]` | ["Ashirvad Eye Hospital", "Mediplus Pathology Laboratory"] | Multiple locations described |
| reviewed_mf | 18 | W | Shivam Hospital | Jodhpur | mostly_foreign | mostly_foreign | 0.6 | 6/28 | 1 | `[16, 21, 22, 24, 26, 27]` | ["SHIVAM EYE HOSPITAL", "Aarogyam Heart Care"] | Multiple locations and names |
| reviewed_mf | 19 |  | Sakar Hospital | Ahmedabad | mostly_foreign | mostly_foreign | 0.7 | 43/101 | 1 | `["1-5", "40", "44-53", "60-74", "76-87"]` | ["Navkar Hospital", "Aakar Hospital", "Mavatar Hospital", "Sagar Hospital", "Aman Hospital"] | Multiple hospitals mentioned |
| reviewed_mf | 20 |  | Malkangiri District Headquarters Hospita | Malkangiri | mostly_foreign | partly_foreign | 0.35 | 16/100 | 1 | `[3, "9-13", "20-25", 33, 52, 58, 95]` | ["District Headquarters Hospital Angul", "DHH Koraput", "Keonjhar District Hospital", "Sunrise Hospital", "District Head | Multiple hospitals mentioned |
| reviewed_mf | 21 |  | Sadhana Diabetes & Hormone’s Clinic , Da | Mumbai | mostly_foreign | mostly_foreign | 0.7 | 79/134 | 1 | `["1-39", "45-50", "55-83", "86-90"]` | ["Patwardhan Homoeopathy Clinic", "Sabka Dentist", "Center for Cosmetic & Implant Dentistry"] | Multiple foreign clinics described |
| reviewed_mf | 22 | D | Sadguru Hospitals | Ghansoli | mostly_foreign | partly_foreign | 0.43 | 11/64 | 1 | `[18, 24, 25, 26, 31, 34, 36, 37, 43, 44, 51]` | ["Dr. Lodha's Nashik Clinic"] | Mixed locations |
| reviewed_mf | 23 | D | J J Eye Hospital | Mumbai | mostly_foreign | partly_foreign | 0.4 | 15/95 | 1 | `[1, 7, 31, "35-38", "44-48", "51-53"]` | ["Smt. B. C. J. General Hospital", "J K Hospital", "J.P Hospital"] | Multiple hospital names |
| reviewed_mf | 24 |  | Shree Hospital | Valsad | mostly_foreign | mostly_foreign | 0.7 | 44/69 | 1 | `["20-31", "36-54", "55", "58-69"]` | ["Shrey Hospital", "Honey Ent Clinic", "Shreya Hospital"] | Multiple hospitals described |
| reviewed_mf | 25 |  | MNP Nursing Home | Perundurai | mostly_foreign | partly_foreign | 0.5 | 7/31 | 1 | `["1", "14-17", "19", "24"]` | ["ANP Nursing Home"] | Multiple names and cities |
| reviewed_pf | 26 | W | Dr Sumesh's Homoeopathic Speciality Cent | Kozhikode | partly_foreign | partly_foreign | 0.4 | 6/19 | 1 | `[7, 8, 12, 17, 18, 19]` | ["Dr Sumesh's Homeopathic Speciality Center - Trivandrum", "Thrissur branch"] | Multiple branches mentioned |
| reviewed_pf | 27 |  | Santhosh Hospital | Tirupattur | partly_foreign | partly_foreign | 0.3 | 3/22 | 1 | `[8, 16, 19]` | [] | Multiple locations mentioned |
| reviewed_pf | 28 | W | Shri B.M.Patil Medical College, Hospital | Vijayapura | partly_foreign | partly_foreign | 0.2 | 3/72 | 1 | `[13, 32, 64]` | [] | Some sentences mention Bijapur |
| reviewed_pf | 29 | W | Athani Hospital | Puthur | partly_foreign | partly_foreign | 0.48 | 4/27 | 1 | `[9, 10, 11, 23]` | [] | Mentions Palakkad |
| reviewed_pf | 30 | W | Ruckmoni Memorial Devi Hospital | Neyyattinkara | partly_foreign | partly_foreign | 0.2 | 2/30 | 1 | `[5, 9]` | ["Southern Institute Of Medical Sciences"] | Mentions other organization |
| reviewed_pf | 31 |  | Lakshmi Hospital | Palakkad | partly_foreign | partly_foreign | 0.2 | 9/93 | 1 | `[38, 39, 47, 49, 50, 77, 78, 81, 82]` | [] | Multiple locations mentioned |
| reviewed_pf | 32 | D | Ahalia Foundation Eye Hospital, Mukkom | Calicut | partly_foreign | partly_foreign | 0.2 | 7/122 | 1 | `[47, 57, 65, 66, 67, 68, 69]` | [] | Multiple locations mentioned |
| reviewed_pf | 33 | W | Aum Eye Hospital | Jamnagar | partly_foreign | partly_foreign | 0.5 | 29/69 | 1 | `["1-8", 10, 14, 17, 20, 23, 24, 27, 37, 38, 41, 42, 45, 48, 49, 50, 51, 52, 53, 54, 55, 57]` | ["AUM Hospital"] | Mentions AUM Hospital |
| reviewed_pf | 34 | W | Surya Dental Clinic | Berhampur | partly_foreign | consistent | 0.0 | 0/35 | 1 | `[]` | [] | No foreign sentences found |
| reviewed_pf | 35 | W | Bapu Ayurvedic Medical College & Hospita | Kopaganj | partly_foreign | partly_foreign | 0.2 | 3/42 | 1 | `[9, 21, 23]` | [] | Inconsistent city and year |
| reviewed_pf | 36 | W | Rani Durgavati Medical College, Banda | Banda | partly_foreign | partly_foreign | 0.24 | 11/28 | 1 | `[17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28]` | ["Atal Bihari Vajpayee Medical University"] | Affiliation mismatch |
| reviewed_pf | 37 | W | Safe Hands Hospital | Gurugram | partly_foreign | partly_foreign | 0.3 | 9/67 | 1 | `[17, 20, 25, 34, 36, 37, 44, 46, 55]` | [] | Multiple locations mentioned |
| reviewed_pf | 38 | W | Dental Expressions | Thane West | partly_foreign | partly_foreign | 0.1 | 1/24 | 1 | `[20]` | [] | Majiwade branch |
| reviewed_pf | 39 |  | Guru Nanak Hospital & Divine India IVF C | Karnal | partly_foreign | partly_foreign | 0.2 | 6/109 | 1 | `["91", "62", "74", "92-94"]` | [] | Mentions Palwal |
| reviewed_pf | 40 | D | Fortis Hospital | Chennai | partly_foreign | partly_foreign | 0.2 | 2/23 | 1 | `[18, 19]` | ["Fortis Malar Hospital", "Fortis Hospital, Vasant Kunj"] | Similar names in other cities |

## Exact prompt (pb_v1)

Record fields and numbered usable sentences (procedure, capability, equipment, then position; is_placeholder = false AND is_repeat = false) are substituted where shown.

```
You audit ONE record from a scraped database of Indian healthcare facilities.
Records were built by merging web snippets, and some records absorbed sentences that actually describe a DIFFERENT organisation (another hospital, clinic or government facility, often in another city).

RECORD
Name: {name}
City: {city}
State: {state}
Description: {description[:1200]}

NUMBERED SENTENCES (from the record's procedure, capability and equipment fields)
1. {sentence 1}
2. {sentence 2}
...

TASK
Judge every numbered sentence against the record's OWN name and city.
- A sentence is foreign if it names, or clearly describes, a different organisation or a different location.
- A branch, unit, parent or sister unit of the same group counts as the same organisation (consistent).
- Old and new names of one city are the same place (e.g. Bijapur and Vijayapura, Berhampur and Brahmapur), and a locality, taluk or district that contains the record's city is the same place.
- A different hospital with a similar or identical name in another city is foreign.
- A generic sentence that names no organisation and could fit this facility counts as consistent.
verdict: "consistent" if (almost) no sentences are foreign; "partly_foreign" if some but not most are foreign; "mostly_foreign" if more than half are foreign.

Return ONLY a JSON object, no other text:
{"verdict": "consistent" | "partly_foreign" | "mostly_foreign",
 "foreign_share": <number from 0 to 1: rough share of sentences that describe a different organisation>,
 "foreign_sentences": [<numbers of the sentences that describe a different organisation; integers, or ranges as strings like "12-19"; [] if none>],
 "other_names": [<up to 5 OTHER facility names found in the sentences; [] if none>],
 "reason": "<at most 15 words>"}
```

Changes vs the contamination prompt: added the foreign_sentences output field; the branch line now reads 'branch, unit, parent or sister unit of the same group'; added the city-alias/locality line; added the similar-name-other-city line. Retry (only stage 0 run 1 needed it): same prompt, temperature 0.3.

# Full record audit (prompt pb_v1)

Script `scripts/record_audit.py` (prepare / stage0 / stage1 / retry / comments / summary). It reuses Pilot B's prompt text
and parser from `scripts/pilot_b_audit.py`, including parser fix (a): unquoted ranges like `35-38` in the list are quoted
before JSON parsing, and numbers given as strings are accepted.

- Model `databricks-meta-llama-3-3-70b-instruct`, max_tokens 800, one record per ai_query row, `failOnError => false`.
- Temperature 0 on attempt 1. The single retry of failed rows used **temperature 0.3**, copied from Pilot B's code
  (coordinator-confirmed: a temperature-0 retry would likely reproduce the same broken output).
- Prompt version `pb_v1` (exact text in `workspace.vf.pb_prompt`). The prompts built for the 61 Pilot B records are
  identical to Pilot B's stored prompts (61/61).
- Input: name, city, state, description (first 1,200 chars), usable sentences (is_placeholder false AND is_repeat false)
  numbered 1..N in the order procedure, capability, equipment, then position. All usable sentences are kept (max 150).
- Population: non-shifted facilities with >= 5 usable sentences = **9,577**. Stage 0 = Aravind + 99 seeded-random
  facilities (seed `ra2026`, md5 order). Stage 1 = 7 seeded chunks of 1,353-1,354 records.
- Shared 2X-Small warehouse 8ea2282aca435351. The tagging job (PID 91959) was running throughout, so speeds are worst case.
- Helper tables: `workspace.vf.ra_sentences` (numbered input), `ra_inputs` (prompt + chunk), `ra_raw` (raw responses,
  every attempt), `ra_parsed` (parsed foreign_sentences + expanded list). Statement log: `data/ra_timings.jsonl`;
  per-chunk results: `data/ra_chunks.jsonl`.

## Timings (UTC, 2026-11-22)

| chunk | rows | ai_query s | s/record | valid | failed | reasons |
|---|---|---|---|---|---|---|
| s0 | 100 | 47.6 | 0.475 | 100 | 0 | |
| s1_c01 | 1,354 | 139.5 | 0.103 | 1,353 | 1 | unparseable 1 |
| s1_c02 | 1,354 | 122.5 | 0.091 | 1,352 | 2 | unparseable 1, foreign_sentences bad item 1 |
| s1_c03 | 1,354 | 129.3 | 0.095 | 1,352 | 2 | unparseable 1, foreign_sentences bad item 1 |
| s1_c04 | 1,354 | 117.2 | 0.087 | 1,353 | 1 | unparseable 1 |
| s1_c05 | 1,354 | 115.6 | 0.085 | 1,354 | 0 | |
| s1_c06 | 1,354 | 107.6 | 0.079 | 1,353 | 1 | foreign_sentences out of range 1 |
| s1_c07 | 1,353 | 145.9 | 0.108 | 1,352 | 1 | unparseable 1 |
| retry (attempt 2, temp 0.3) | 8 | 24.2 | | 6 | 2 | unparseable 2 |

- ai_query total 949 s. Wall clock from the first statement (prepare, 01:54:54) to the end of comments (02:14:43):
  19 min 49 s. Stage 1 loop: 971 s.
- Final failed rows: 2, both `unparseable: Expecting ',' delimiter` (char 147 and char 81).

## Gates checked before each stage-1 chunk

| before | audit failed | tagging failed (pa_single_v1) |
|---|---|---|
| s1_c01 | 0/100 | 642/32,236 = 1.99% |
| s1_c02 | 1/1,454 | 1,004/42,236 = 2.38% |
| s1_c03 | 3/2,808 | 1,373/52,236 = 2.63% |
| s1_c04 | 5/4,162 | 1,727/62,236 = 2.77% |
| s1_c05 | 6/5,516 | 686/62,236 = 1.10% |
| s1_c06 | 6/6,870 | 780/72,236 = 1.08% |
| s1_c07 | 7/8,224 | 893/82,236 = 1.09% |

Neither rate crossed 3%. The running process used the first tagging rule throughout (credit-related failures
excluded). The drop at s1_c05 comes from the tagging table, not from this script. The script now also excludes
tagging's `claim_without_label` and `unknown_label` content failures (user rule received mid-run). That version was not
used for these checks. No credit or quota errors occurred, so the credits stop rule never fired.

## Results

| verdict | n | share | mean flagged share | mean foreign_share |
|---|---|---|---|---|
| consistent | 5,857 | 61.2% | 0.0001 | 0.0002 |
| partly_foreign | 3,228 | 33.7% | 0.109 | 0.237 |
| mostly_foreign | 490 | 5.1% | 0.427 | 0.726 |
| failed | 2 | 0.02% | | |

- Facilities with >= 1 flagged sentence: 3,698. Flagged sentences in total: 26,332 of 422,686 rows in
  `sentence_foreign_flag` (153 rows NULL = the 2 failed facilities).
- Aravind Eye Hospital, Hyderabad (b8a5401f-42f1-422a-8cd9-686a15b4cb76): mostly_foreign, 79/149 flagged,
  foreign_share 0.7, other_names Madras Medical Mission, Janakpuri Super Speciality Hospital, Lok Nayak Hospital.
- For mostly_foreign, the mean flagged share (0.43) is well below the model's own foreign_share (0.73). The model's
  sentence lists under-cover its own share estimate, as in Pilot B. Use `is_foreign` for sentence-level filtering and
  `verdict` for record-level tiers.
- Temperature 0 is not deterministic on this endpoint (Pilot B: Aravind 63/149 vs 79/149 across runs).

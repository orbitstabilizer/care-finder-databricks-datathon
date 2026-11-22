# Sentence tagging, step 2 (throughput and prompt test)

Warehouse 8ea2282aca435351 (2X-Small), model databricks-meta-llama-3-3-70b-instruct, temp 0, one sentence per ai_query call, failOnError => false. Script: scripts/tag_sentences.py, scripts/tag_compact_test.py. Raw log: reports/sentence_tagging/*.jsonl.

- Step 1: 32,147 dental-only sentences rule-labelled; 239,115 left to tag. Tiers: 1 keyword 22,236 / 2 hospital 145,537 / 3 rest 71,342.
- (a) 1 statement x 2,000 (pa_single_v1): 106.9 s, 18.7 sent/s, projected 3.5 h for the 235,115 remaining. First-pass fails 5, after one retry 4 failed.
- (b) 4 concurrent x 500 (pa_single_v1): 71.4 s wall, 28.0 sent/s, projected 2.3 h. First-pass fails 38 (unparseable 22, unknown_label 13, claim_without_label 3), after retry 25 failed. Different sentences from (a), so the failure gap is not attributable to concurrency.
- Rate limits: 0 errorMessage values in all 4,043 + 1,000 calls; no 429 / REQUEST_LIMIT_EXCEEDED. First concurrent attempt hit a Delta DELTA_CONCURRENT_APPEND conflict (self-read of the raw table inside the INSERT); fixed by removing that read; the arm was reset and rerun from scratch.
- Compact prompt pa_compact_v1 (in workspace.vf.pa_prompt): 140 words / 1,516 chars vs 370 words / 3,105 chars for pa_single_v1 (38% of words, 49% of chars). Same 49 labels, same output fields.
- On the first 500 sentences of (a): compact 41.1 s (12.2 sent/s, one statement), 0 failed; differs from full in 23/500 (4.6%; is_claim differs 4). Full re-run 58.5 s (8.5 sent/s), 0 failed; differs from (a) in 8/500 (1.6%; is_claim 1) = noise floor. Results only in workspace.vf.tag_compact_test.
- Chat endpoints (not tested): databricks-gpt-oss-120b, gpt-oss-20b, qwen3-next-80b-a3b-instruct, qwen35-122b-a10b, gemma-3-12b, meta-llama-3-1-8b-instruct, meta-llama-3-3-70b-instruct, llama-4-maverick. No AI Gateway rate_limits configured on any endpoint (field null); no per-endpoint limit visible.
- Decision: compact differs 4.6% (< 10% and < noise 1.6 + 10) -> pa_compact_v1 with 4 concurrent statements per chunk. Compact x conc4 was not measured together; estimate 28.0 x (58.5/41.1) = ~40 sent/s -> ~1.6 h (unmeasured estimate). Gate removed by user; step 3 started.

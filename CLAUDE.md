# CMU Datathon — Fall 2026 — Virtue Foundation

## Status — read this first

**We are still brainstorming the method. Nothing final has been built.**
Feasibility has been measured and a classification prompt has been validated on a small
sample, but the pipeline, the scoring and the app are not designed in detail and not
agreed. Do not start pipeline or build steps until the user has agreed the plan.

Last updated: 2026-11-21.

## How this project is run

- **The user decides the method.** They want short answers and to be kept in the loop.
- **The main Claude Code session is an orchestrator.** It brainstorms with the user, runs
  only short Databricks queries to look at things, and delegates real tasks to subagents
  (Opus 5.5, medium effort).
- **If you are a subagent with a task:** do exactly the task in your brief, on Databricks,
  and stop there. Do not extend it into building the pipeline. Report measured results,
  say what you did not verify, and never state an inference as a finding.
- **A separate conversation agent** may be brainstorming with the user in a chat that has
  no access to code or data. `CONVERSATION_BRIEF.md` is written for that agent. Coding
  agents should ignore that file; this file is the source of truth.

## Credits and quota — standing rule (every agent)

The workspace can hit its credit or quota limit. Yusuf can reset or top it up, so this is a **pause, not a failure**.

1. **Recognise it:** errors mentioning quota, credit, billing or limit exceeded; the warehouse refusing to start;
   or ai_query calls failing in bulk with the same error.
2. **Stop sending calls at once.** No retry loops, no prompt or design changes to work around it.
3. **Keep everything written so far.** Long jobs (tagging, audit) must stay resumable from the last saved chunk.
   Do not write rows that failed because of credits as ordinary failed rows.
4. **Report immediately.** First line: `CREDITS EXHAUSTED, TOP UP NEEDED`. Then the exact error text, which jobs
   stopped, and rows done vs rows left for each.
5. **After Yusuf confirms the top-up, resume** from where each job stopped. Never restart from zero.
6. **These failures do not count** toward any failed-row gate (e.g. the 3% gate).

## Clean base tables, use these

**Rule: every job reads from these three tables, not from the raw `facilities` table.**
Filter out `is_shifted` facilities and `is_placeholder` sentences unless your brief states a reason not to.
Every result table you write must carry `unique_id` so it joins to `facilities_clean`.
(The contamination and facility-type jobs ran on the raw table before this rule; their tables carry unique_id.)

| table | key | rows | flags |
|---|---|---|---|
| `workspace.vf.facilities_clean` | `unique_id` | 10,077 | `is_shifted` (88 column-shifted rows), `coords_missing` (118), `coords_outside_india` (6), `country_not_india`, `id_not_uuid`, `postcode_valid` (9,909) |
| `workspace.vf.facility_sentences` | `unique_id, source_column, position` | 451,110 | `is_placeholder` (1,000; rule in `placeholder_rule`), `is_repeat` (26,422) |
| `workspace.vf.distinct_sentences` | `sentence_id` (also `sentence_key`) | 271,262 | none — already excludes placeholders and shifted facilities |
| `workspace.vf.facility_location` | `facility_id` (= unique_id) | 10,077 | `location_confidence` (high 5,551, good 3,221, suspect 666, approximate 476, unverified 73, none 90), `location_source` (coordinates / city_point / pin_point / none). Use `final_lat`, `final_lon`. |
| `workspace.vf.record_audit` | `unique_id` | 9,577 | LLM record-merging audit per facility (non-shifted, >= 5 usable sentences): `verdict` consistent / partly_foreign / mostly_foreign, `foreign_share`, `other_names`, `n_flagged`/`flagged_share`, `failed` (2). Prompt pb_v1; `scripts/record_audit.py`, `reports/record_audit.md`. |
| `workspace.vf.sentence_foreign_flag` | `unique_id, source_column, position` | 422,686 | `is_foreign` per usable sentence of each audited facility (26,332 true; NULL for the 2 failed audits); joins `facility_sentences`. |
| `workspace.vf.nfhs_district` | `nfhs_key` (state\|district normalised) | 706 | NFHS-5 58 clean DOUBLE indicators + `rank_<col>` (1..706, 1 = worst per `service_indicator_map.direction`) and `quartile_<col>` for the 8 mapped indicators. Context only, never tier/rank input. `scripts/build_nfhs.py` |
| `workspace.vf.pin_district` | `pin, pin_key` | 20,824 | PIN x district with `pin_share`, `is_primary` (majority district), `nfhs_key`, `match_method` exact/alias/NULL |
| `workspace.vf.district_alias` | `pin_key` | 110 | hand-written PIN-directory district -> NFHS district (renames, spellings, post-2019 districts -> parent; see `note`) |
| `workspace.vf.facility_district` | `unique_id` | 9,989 | non-shifted facility -> postcode's primary district; `nfhs_key` linked for 9,689 (8,242 exact, 1,447 alias) |
| `workspace.vf.service_indicator_map` | `service, indicator_column` | 13 | 6 headline services -> 0-3 NFHS indicators with label, direction, reason; NULL indicator = deliberately none (mri, burn_care). Query: `scripts/district_context.sql` / `.py` |

- `facilities_clean` columns: unique_id, name, city, state, postcode, postcode_valid, latitude, longitude, description,
  specialties (distinct array), numberDoctors / capacity / yearEstablished (INT, NULL if unparseable), facilityTypeId,
  operatorTypeId, affiliationTypeIds, official_domain, source_domains, official_phone (raw officialPhone, trimmed,
  ''/'null'/'none' -> NULL; added in place by `build_clean_base.py add_phone`), plus the flags.
- `facility_sentences`: sentence (trimmed) and sentence_key (lowercase, whitespace collapsed, trailing punctuation removed).
  Join to `distinct_sentences` on sentence_key. Usable sentence = not placeholder and not repeat.
- Shifted facilities have 0 sentences. 60 non-shifted facilities also have 0 sentences.
- Coordinates are not cleaned: 6 rows have scrambled lat/lon (`coords_outside_india`).
- Full build report: `reports/clean_base_build.md`. Rebuild with `scripts/build_clean_base.py`.
- Location: `facility_location` was built by a separate location workstream; its SQL is in `sql/` (00_schema to
  03_facility_location). It has no Unity Catalog comments. Its key column is named `facility_id` and joins 1:1 to `facilities_clean.unique_id`
  (10,077 matched, none unmatched). It still contains the 88 shifted rows (87 with no point, 1 with a PIN point) —
  filter them with `facilities_clean.is_shifted`. Helpers: `workspace.vf.pin_point` (key `pin`, 18,966 rows),
  `workspace.vf.city_point` (key `city_key`, 272 rows). Distance: SQL function
  `workspace.vf.haversine_km(lat1, lon1, lat2, lon2)` returns km.

Lookup tables (hand-written; source and rebuild in `scripts/build_lookups.py`, sample rows in `reports/lookup_tables.md`):
- `workspace.vf.service_department_map` — key `service, link_type, value`, 442 rows: per service label (49), the specialty terms
  (in >= 20 facilities) and other service labels that back it, each `strong` / `supporting`; other_clinical has one NULL row.
- `workspace.vf.service_type_fit` — key `service, facility_type`, 1,274 rows (49 x 26): `expected` / `plausible` / `unexpected`
  for a service at a facility type, with the deciding rule in `note`.

Superseded drafts, do not use: `workspace.vf.silver_evidence`, `workspace.vf.facility_type_pilot` (unvalidated labels;
the facility-type job was stopped after every pilot batch failed its echo check).

## App — extend this one, do not build another

- Name `vf-locator`, URL https://vf-locator-7474654371578222.aws.databricksapps.com
- Workspace source `/Workspace/Users/yakin@andrew.cmu.edu/vf/locator`; local source `app/` (deploy steps in `app/README.md`).
- **FastAPI + React single page**: `app/main.py` serves `app/static/` (Vite build output). Front-end source is
  `app/frontend/` (React + Leaflet). **Rebuild before deploying: `cd app/frontend && npm ci && npm run build`**,
  then sync with `--exclude-from app/.syncignore` (keeps `frontend/` out of the workspace). Older UIs (Streamlit, vanilla JS) were removed 2026-11-22; recover from git history if needed.
  `app.yaml` runs `startup_probe.py` then `uvicorn main:app` on `$DATABRICKS_APP_PORT` (default 8000).
  SQL stays in `queries.py`, names in `config.py`, LLM matcher in `matcher.py`.
- Endpoints: `GET /api/services` (grouped entries + coverage note), `POST /api/match {text}`,
  `GET /api/resolve?pin=|place=`, `GET /api/search?service=&lat=&lon=` (summary + per-tier lists, 20 each, with
  quotes, warnings, why, details), `GET /api/stats` (build_stats funnel + validation line from
  `workspace.vf.validation_dialysis`). Reserved: `#district-strip` under the summary for a future `/api/district_context`.
- Local run: `DATABRICKS_CONFIG_PROFILE=datathon uvicorn main:app --port 8765` from `app/` (needs fastapi + uvicorn).
- `workspace.vf.facility_service` is the contract table the verdict job fills (one row per unique_id, service).
- **Rule: do not build another app; extend this one.**
- Auto-rebuild: `scripts/rebuild_watcher.py` (nohup, log `reports/rebuild_watcher.log`) reruns `scripts/build_facility_service.py` every 3 new lines in `reports/sentence_tagging/chunks.jsonl` and once after the tagging PID exits, then stops. Data changes need no app redeploy.

## Demo cases (keep these working)

The presentation uses these stories, written out in `reports/executive_summary.md` ("Demo stories"); every feature is walked through in `reports/demo_script.md`:
Rayagada NICU (PIN 765019: nearest Confirmed NICU 143 km, Christian Hospital Bissamcuttack Likely ~8 km), Gumla dialysis
(PIN 835207), Aravind Eye Hospital, Hyderabad (unique_id b8a5401f-42f1-422a-8cd9-686a15b4cb76, should stay Unverified for
dialysis; it shows at PIN 605602 Villupuram, 1.1 km, below a Possible at 31 km, because its coordinates are there), and Thanjavur dialysis (PIN 613001) as the example of a Confirmed result nearby (Sudar Hospital, <1 km).
After any rebuild or app change, check these still behave as described and refresh the numbers if they moved.

## The challenge

Build something that takes **a service** (dialysis, emergency C-section, NICU, cardiac
surgery, MRI, burn care…) and **a location** (city, district, PIN code, or coordinates),
and returns the **best facility option(s) with an evidence-based explanation**.

Every recommendation must answer two questions:

1. **WHY this facility?** What evidence says it exists, offers this service, and is the
   best choice for this location?
2. **HOW did you decide?** What logic, scoring or rules turned ~10,000 records into
   this answer? What was weighed and traded off?

> If your build can't explain itself, it doesn't meet the challenge requirements,
> however good it looks.

Hard requirements: runs on Databricks Free Edition; uses the provided facility dataset;
supports a non-technical user workflow; cites the underlying facility text for any
important claim; communicates uncertainty instead of presenting weak evidence as fact.

The users the brief has in mind: a community health worker, an NGO coordinator, a
district planner. Full brief in `task.md`. Supplemental dataset notes in `dais-2026.md`.
Original scratch notes in `intro.md`.

## Databricks access

| | |
|---|---|
| CLI profile | `datathon` |
| Workspace | `https://dbc-70851148-db1d.cloud.databricks.com` (AWS, Free Edition) |
| Warehouse | `Serverless Starter Warehouse` (`8ea2282aca435351`), 2X-Small |
| Dataset catalog | `databricks_virtue_foundation_dataset_dais_2026` (read-only) |
| Dataset schema | `virtue_foundation_dataset` |
| Our schema | `workspace.vf` (writable) |

Always pass `--profile datathon` (each Bash call is a separate shell, so `export` does
not persist across calls).

**MCP servers** (user scope, already authorized):

- `databricks-sql` → `execute_sql`, `poll_sql_result`
- `databricks-genie` → `genie_ask`, `view_ask`, …

Without MCP, run SQL with
`databricks experimental aitools tools query "<SQL>" --profile datathon`.

### Verified capabilities

All confirmed working on this workspace — do not re-probe:

- `ai_classify`, `ai_query` ✅ (tested with `databricks-meta-llama-3-3-70b-instruct`)
- 11 foundation-model endpoints, incl. embeddings (`databricks-gte-large-en`,
  `databricks-bge-large-en`, `databricks-qwen3-embedding-0-6b`) ✅
- Databricks Apps — an app was created and its compute came up ✅ (no app deployed yet)
- Vector Search — endpoint creation works ✅ (`probe-vs-check` exists, 0 indexes; no
  compute is billed until an index is created)
- Serverless jobs run notebooks, and `ai_classify` works there ✅
- Credits can be topped up on request (the Databricks team is on site) — cost is not a
  design constraint.
- The account is in the `admins` group, so workspace preview toggles are self-service.

Note: the legacy `/api/2.0/mcp/*` managed MCP servers are **disabled**; the working
route is Unity Gateway at `/ai-gateway/mcp-services/...`.

### Free Edition limits (measured, not guessed)

These are **feature gates, not credit limits** — topping up credits does not lift them.
Only a workspace that is not Free Edition would.

- `databricks warehouses edit` → *"Editing warehouse is not available to free users."*
- Warehouse size is capped: *"Only sizes smaller than or equal to '2X-Small' are
  allowed."*
- The **number** of warehouses is capped too: creating a second one fails with
  *"You've hit the limit for warehouses for free usage."* There is exactly one
  2X-Small warehouse and that is the entire SQL compute budget.
- Measured LLM throughput:

  | setup | rate |
  |---|---|
  | 2X-Small warehouse, `ai_classify`, 1 snippet/call | 4.3/sec |
  | serverless job, `ai_classify`, 1 snippet/call | 5.1/sec |
  | 2X-Small warehouse, `ai_query`, 25 snippets/call | **16.6/sec** |

  The bottleneck is **per-call round-trip latency to the model endpoint**, not compute.
  Serverless compute is not a speed lever. Batching is the only lever found: at 25
  snippets per call a 65k-snippet pass takes about 65 minutes. The 16.6/sec figure was
  measured with an early, simpler prompt; the validated prompt is longer and returns
  more per snippet, so its throughput is **not yet measured**.

Benchmark notebook: `notebooks/99_bench_ai.py`.

## The data

Three tables in `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset`.
The whole dataset is about 20 MB on disk — small enough that nothing needs distributed
processing. The only expensive step is LLM calls.

| table | rows | cols | on disk |
|---|---|---|---|
| `facilities` | 10,088 | 51 | 16.3 MB |
| `india_post_pincode_directory` | 165,627 | 11 | 3.1 MB |
| `nfhs_5_district_health_indicators` | 706 | 109 | 0.2 MB |

**Where the data comes from.** `facilities` is not raw. It is the output of the
provider's own pipeline ("FDR"), which scraped websites, extracted facts with GenAI,
resolved entities and consolidated sources into one row per facility. Errors in it are
that pipeline's errors, baked in.

### `facilities`

- **Every column is `STRING`** except `latitude` / `longitude` (`DOUBLE`). List-valued
  fields (`specialties`, `procedure`, `equipment`, `capability`, `phone_numbers`,
  `source_urls`) are **JSON-encoded strings** — parse with
  `from_json(col, 'array<string>')`.
- 10,088 rows but **10,077 distinct `unique_id`**: 11 ids appear twice as exact duplicate
  rows. Deduplicate before any join, or rows fan out.
- 9,512 distinct names after lower/trim; 10,014 distinct name+city pairs. Most repeated
  names are chain branches in different cities.
- **99% geocoded** (9,970 rows have coordinates).
- **`address_stateOrRegion` has 254 distinct values** where India has 37. Place names are
  unreliable — resolve locations via coordinates, not name matching.
- Coverage of scale fields is thin: `yearEstablished` 47.8%, `numberDoctors` 36.4%,
  `capacity` 25.2% (figures from the brief). They can only be tiebreakers.
- `description`: 10,008 rows non-null, average 179 characters, max 6,557.

**The evidence text.** What a facility "offers" lives in three columns, each a JSON array
of free-text sentences:

| column | sentences | 
|---|---|
| `capability` | 232,564 |
| `procedure` | 167,430 |
| `equipment` | 60,138 |

- About 451,600 non-empty sentences ("snippets") in total, about 276,000–286,000
  distinct (depending on case-folding). 37% are repeats.
- Snippets are short: average 43 characters, 99.4% under 200.
- **Arrays are capped at 50 entries.** 1,125 records sit at exactly 50 procedures, so the
  largest records are truncated. `source_urls` is capped at 50 too.
- **148 facilities have no snippets at all** in these three columns. They would be
  invisible to an evidence-based recommender unless `description` is used.
- A keyword filter for clinical terms keeps 65,172 of 285,968 distinct snippets. It was
  written quickly and its recall is unmeasured.

**Sources.** `source_urls` is a list per record (average 17, every record has at least
two). **There is no per-snippet URL.** A snippet cannot be tied to the page it came
from using the columns we have. A citation is therefore the verbatim snippet plus the
record's list of URLs. Whether a tighter link can be recovered is untested.

### Two findings that drive the design

**1. `specialties` is already a controlled vocabulary.** Clean camelCase terms
(`neonatologyPerinatalMedicine`, `burnAndTraumaPlasticSurgery`, `nephrology`). Values
repeat within a row — deduplicate. Facilities per specialty (top and relevant):

| specialty | facilities | | specialty | facilities |
|---|---|---|---|---|
| internalMedicine | 6,836 | | nephrology | 2,153 |
| familyMedicine | 5,175 | | emergencyMedicine | 2,079 |
| gynecologyAndObstetrics | 4,489 | | criticalCareMedicine | 1,673 |
| dentistry | 4,190 | | neonatologyPerinatalMedicine | 1,252 |
| orthopedicSurgery | 3,519 | | medicalOncology | 1,435 |
| pediatrics | 3,429 | | cardiacSurgery | 587 |
| cardiology | 3,003 | | radiology | 2,993 |

But **specialty ≠ service**. `nephrology` is a department; `dialysis` is the service.
Services appear only in the snippets, e.g. *"20-bed Dialysis Unit with 10 machines"*.

**2. Records mix sentences from different hospitals.** Example: the row named
*Aravind Eye Hospital*, Hyderabad (`unique_id` `b8a5401f-42f1-422a-8cd9-686a15b4cb76`)
carries *"Dialysis treatment is provided via a 20-bed Dialysis Unit with 10 machines…"*,
a neurosurgery department and an Ayurvedic clinic — text from other hospitals. The row
named *Wockhardt Hospital Nagpur* carries procedures *"offered at S L Raheja Fortis
Hospital, Mumbai"*. So `WHERE procedure LIKE '%dialysis%'` returns an eye hospital as a
dialysis provider.

How common is it? **The overall rate has not been measured.** What has been measured,
for dialysis only:

- 1,036 facilities mention dialysis in their snippets.
- 831 (80%) also list the `nephrology` specialty, which is consistent.
- 205 do not. That is a soft warning sign, not proof of contamination.
- 33 have names matching eye / dental / skin / clinic / diagnostic — a crude proxy
  (a real dialysis clinic would match "clinic").

An earlier version of this file called the problem "severe, all three rows sampled".
That was an over-reading of three rows. The honest position: it is real, it produces
dangerous wrong answers, it seems concentrated in the large records (the ones at the
50-entry cap, which would also score highest on any evidence count), and its true rate
is unknown.

Idea for mitigation, untested: many snippets name their own facility
(*"Hip replacement surgery is offered at Fortis Hospital, Anandapur"*). Work at
**snippet level**, extract the facility a snippet names, and drop or flag snippets that
name a different facility than their record. How many snippets name a facility at all
is unmeasured.

### `india_post_pincode_directory`

165,627 rows; 19,586 distinct PIN codes; 750 districts; 37 states. One row per **post
office**, not per PIN, so a join on `pincode` fans out — aggregate first. `latitude` and
`longitude` are **strings** here and 12,007 rows have no usable coordinates.

### `nfhs_5_district_health_indicators`

706 rows, 698 distinct district names, 36 states, 109 columns of district health
indicators (2019–21). Columns that contain suppressed (`*`) or low-confidence
(parenthesised) values are typed `STRING`; clean ones are `DOUBLE`. Not used so far.

`dais-2026.md` is wrong on three points: column names in both tables are already
snake_case; it says about 12,600 pincode rows lack coordinates (measured: 12,007); and
it does not mention the string-typed coordinate columns.

## Design state

### Decided by the user

- **Format: a Databricks App.** Service and location in, ranked result cards out, each
  showing the verbatim evidence and how confident we are.
- **Matching: LLM extraction into a table, then exact matching.** An LLM pass turns
  snippets into structured service claims once; queries then run against that table.
- **Work on Databricks**, not on a local copy of the data.
- **No building until the plan is agreed.**

### Working assumptions (proposed by Claude, not objected to, not confirmed)

- A **fixed service taxonomy** (48 labels plus `other_clinical`, listed in
  `scripts/classify_eval.py`). The user's free-text request is mapped onto it at query
  time with one LLM call ("kidney machine" → `dialysis`).
- **Snippet-level evidence**: one row per (facility, snippet, source column).
- **Locations resolve to coordinates.** A PIN code becomes a point through the pincode
  table; distance is computed from coordinates. How a typed city or district name
  becomes a point is not designed.
- Classify only distinct snippets that pass a clinical keyword filter, in batches of
  25–50 per call.
- Read the dataset from the share; write only derived tables to `workspace.vf`.
- Vector Search is not in the first version. Its possible role: finding evidence for a
  request that maps to no taxonomy label, and catching what the keyword filter dropped.

### Proposed, waiting for a decision

- **Scoring: tier first, then distance.** Put each candidate in a tier — *Confirmed*
  (explicit evidence, attribution clean, specialty agrees), *Likely* (stated evidence, or
  explicit with one warning flag), *Unverified* (weak evidence only, or attribution
  mismatch) — and sort by distance inside a tier. The alternative is one continuous
  score, evidence × trust × distance decay. The argument for tiers: the rule can be
  shown to a judge, and a nearby weak candidate cannot outrank a confirmed one further
  away. The cost: no fine ordering inside a tier (source count could break ties).
- **Extract the named facility in the same LLM call** as the service labels, instead of
  a separate regex or second pass.

### Open questions

- **Dentistry.** 4,190 of 10,077 facilities list `dentistry`. Keep or exclude, given the
  brief's emergency-care framing?
- **The 148 facilities with no snippets**, and whether `description` should be used as
  evidence text.
- **Citations** without a per-snippet URL: is "snippet + the record's URLs" enough?
- **How we know the recommender is right.** There is no ground truth. No evaluation
  method has been discussed.
- **Requests outside the taxonomy.**
- Whether NFHS district data has any role.
- The `strength` label (explicit / stated / weak) would feed the tiers but has only been
  eyeballed on 40 snippets.
- Extraction quality and speed across thousands of batches are unmeasured.

## Classification prompt — validated on a small sample

The prompt lives in `scripts/classify_eval.py`. Run
`python scripts/classify_eval.py --random 40` to re-validate after any change; it prints
a side-by-side table and flags invalid labels and misalignment. It uses
`databricks-meta-llama-3-3-70b-instruct` through `ai_query`.

Output, one object per snippet — **three separate axes**:

```json
{"i":0,"echo":"first three words","is_claim":true,
 "services":["dialysis"],"strength":"explicit"}
```

- `is_claim` false → `services: []` and `strength: "na"`. Research findings, doctor
  bios, fees, founding dates, buildings, accreditations and listings are not claims.
- `services` is an **array** — "imaging including USG, CT and MRI" is three services.
- `strength`: `explicit` (beds, machines, units, counts) | `stated` | `weak`.
- `echo` exists so batch alignment can be checked instead of assumed.

Result: on 40 random real snippets, 40 objects back, no invalid labels, no misalignment,
no clear errors on manual reading. One batch only.

Lessons that each cost an iteration — do not regress them:

1. **"Not a service claim" is a state, never a label.** As a label it collided with the
   strength axis. (One leftover line in the prompt still uses the phrase
   `"not_a_service_claim"` for education programmes; it works but should be reworded to
   `is_claim` false.)
2. **Single-label loses evidence.** Must be multi-label.
3. **Validate every returned label against the allowed set** — the model invented
   `pediatrics` when it was not listed.
4. Education and fellowship programmes are not services. Cosmetic work is not oncology.
   Orthodontic (teeth) is not orthopaedic (bones) — the model conflates them.
5. A bare department list is `weak` evidence for each department, not `explicit`.
6. Without the `echo` field and a count check, a batch can silently drop one item and
   shift every later label onto the wrong snippet. This happened in the first attempt
   (25 in, 24 out).

## What exists

**In the Databricks workspace**

- `workspace.vf.silver_evidence` — a **draft** table, built before the plan was agreed.
  The user chose to leave it. 452,502 rows, one per (facility, snippet, source column),
  with facility name, city, state, PIN, coordinates, `snippet_hash`, `source_urls`,
  `specialties`. **Known flaw:** the 11 duplicated ids fan out (about 1,400 excess
  rows). Rebuild from deduplicated facilities before relying on it.
- Notebooks `/Users/yakin@andrew.cmu.edu/vf/01_explore` (imported, never run) and
  `/Users/yakin@andrew.cmu.edu/vf/99_bench_ai` (throughput benchmark, ran once).
- `probe-vs-check` — empty Vector Search endpoint left from a capability test.
- No apps, no jobs, no extraction output.

**In this folder**

| file | what it is |
|---|---|
| `task.md`, `dais-2026.md`, `intro.md` | the brief and dataset notes |
| `scripts/classify_eval.py` | the validated prompt and its test harness |
| `notebooks/99_bench_ai.py` | source of the workspace benchmark notebook (01_explore.py removed from the repo; its workspace copy remains) |
| `explore.ipynb`, `download_data.py`, `data/*.parquet` | local copies for the user to inspect — not the working copy |
| `CONVERSATION_BRIEF.md` | briefing for the conversation agent — coding agents ignore it |
| `.venv/` | leftover, ignore |

## Where work happens — Databricks first

**Do the work on the platform, not locally.** Notebooks, pipelines and the app live in
the workspace; local files are for inspection and version control.

- The dataset catalog is a **Delta Sharing catalog — read-only**. Never try to write
  into it.
- Write everything derived to **`workspace.vf`**. Don't use `workspace.default`.

Notebook sources are kept in `notebooks/` and pushed to the workspace with:

```
databricks workspace import /Users/yakin@andrew.cmu.edu/vf/<name> \
  --file notebooks/<name>.py --format SOURCE --language PYTHON --overwrite \
  --profile datathon
```

`spark` and `display` are injected by the Databricks runtime, so local linters flag them
as undefined in `notebooks/*.py`. That is expected.

## Local environment

Use the **`py13` conda env**, not the local `.venv` — it carries the user's own
JupyterLab setup, including the `jupyterlab-vim` extension:

```
/opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python
/opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/jupyter lab
```

It has pandas, numpy, matplotlib, plotly, pyarrow, geopandas, shapely and
`databricks-sql-connector`.

## Working conventions

- Treat every field as **a claim to verify, not ground truth**.
- Any ranking, score or recommendation must be traceable to a verbatim snippet.
- **Measure before asserting.** The data is cheap to query. Do not extrapolate from a
  handful of rows, and say plainly when a number is a proxy.
- Don't normalize names in catalog/schema/table identifiers — use them literally.
- Keep answers short: lead with the point, at most a paragraph while brainstorming.
- Genie (`genie_ask` / `view_ask`) can answer ad-hoc data questions and finds tables
  unaided — useful, optional. It is stateless Q&A: it cannot be assigned work, write
  tables or run on a schedule.

## Version control

This folder is a git repo (no remote). Commit at each milestone (after a rebuild, a re-tag, an app deploy) with a short
message, so any change can be rolled back. `data/`, `.venv/` and `node_modules/` are ignored. Never delete work that is
not committed.

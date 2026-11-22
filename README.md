# Care Finder — CMU Datathon 2026 (Virtue Foundation)

Type a need in plain words ("my father needs a kidney machine") and a place (PIN code, place name or a map click). Care Finder returns the nearest facilities that offer the service, ranked by how strong the evidence is. Each result quotes the facility's own text and says honestly how sure we are.

- **Live app:** Databricks App `vf-locator`, https://vf-locator-7474654371578222.aws.databricksapps.com (Databricks sign-in required)
- **Submission notebook:** [`notebooks/vf_care_finder.ipynb`](notebooks/vf_care_finder.ipynb) — the whole pipeline, step by step, with saved outputs
- **Method in plain words:** [`reports/executive_summary.md`](reports/executive_summary.md)
- **Decisions and judge Q&A:** [`reports/presenter_brief.md`](reports/presenter_brief.md)
- **Demo video script:** [`reports/demo_script.md`](reports/demo_script.md)

## The challenge

CMU Datathon, Fall 2026, with the Virtue Foundation: *find the right care.* A community health worker needs dialysis for a patient; an NGO coordinator needs a hospital for a high-risk delivery; a district planner needs somewhere to send trauma cases. Build something that takes **a service** (dialysis, emergency C-section, NICU, cardiac surgery, MRI, burn care…) and **a location** (city, district, PIN code or coordinates), and returns the best facility options with an evidence-based explanation. The format is free: app, dashboard, Genie space, notebook or agent.

The dataset lists about 10,000 Indian facilities with 51 attributes each, mostly extracted from web text. Every field is a claim to verify, not ground truth. Some records merge two hospitals or contradict themselves, and coverage is uneven: description 100%, capability 99.7%, procedure 92.5%, equipment 77%, year established 47.8%, number of doctors 36.4%, capacity 25.2%.

**The one rule: show your reasoning.** For every recommendation, answer *WHY this facility?* (what evidence says it exists, offers the service, and is the best choice here) and *HOW did you decide?* (what logic turned 10,000 records into this answer, and what was traded off).

| Requirement | How Care Finder meets it |
|---|---|
| Runs on Databricks Free Edition | One 2X-Small warehouse, `ai_query`, a Databricks App |
| Uses the provided dataset | Facilities, PIN directory and NFHS-5 district indicators |
| Clear non-technical workflow | Plain-words search, PIN / place / map click, call and directions buttons, emergency warning |
| Cites facility text for every important claim | Every result, and every hospital the district hint suggests, quotes the facility's own sentences |
| Communicates uncertainty | Four tiers, warnings, "about" distances, "call to check" |

## How it works, in one paragraph

The dataset (10,077 Indian facilities, scraped and merged by an LLM) hides services in 451,000 short sentences, and some records mix text from several hospitals. We clean the records, place every facility on the map with a confidence level, and give each one a facility type. An LLM tags every distinct sentence once, with the services it claims and how strong the claim is. A second LLM pass checks that each record's sentences belong to that facility. Rules then combine the evidence, department backing and facility type into four tiers: Confirmed, Likely, Possible and Unverified. Searches rank by tier, then distance. District health survey data (NFHS-5) adds context, and suggests nearby hospitals to call when no website mentions the service. It never changes a tier. Blind web checks: every Confirmed facility we could verify offered the service (30 of 30).

## Repository

| Path | What |
|---|---|
| `scripts/` | Pipeline (clean base, facility type, sentence tagging, ownership audit, lookups, verdicts, NFHS, validation), plus `deploy.sh` / `run_sql.py` and `download_data.py` |
| `sql/` | Location workstream: PIN and city centres, facility location with confidence |
| `app/` | The Databricks App: FastAPI backend (`main.py`, `queries.py`, `matcher.py`) and React + Leaflet front end (`frontend/`, built into `static/`). Deploy steps in [`app/README.md`](app/README.md) |
| `reports/` | Build reports, validation results, method write-ups |
| `notebooks/` | **`vf_care_finder.ipynb`, the submission**; the LLM throughput benchmark; `explore.ipynb` for local inspection |
| `dais-2026.md` | Dataset notes from the organisers |

## Running it

Everything runs on **Databricks Free Edition**: one 2X-Small SQL warehouse, `ai_query` with Llama 3.3 70B, and a Databricks App. Source data is the read-only share `databricks_virtue_foundation_dataset_dais_2026`. All derived tables are in `workspace.vf`.

- **Read the pipeline:** open the submission notebook. By default (`REBUILD = False`, `RUN_LLM = False`) it only reads existing tables.
- **Rebuild:** set the flags in the notebook, or run the scripts in `scripts/` in the notebook's order. The LLM passes are the only expensive step.
- **App:** see `app/README.md`. Short version: `cd app/frontend && npm ci && npm run build`, then `databricks sync` and `databricks apps deploy vf-locator`.

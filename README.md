# Care Finder — CMU Datathon 2026 (Virtue Foundation)

Type a need in plain words ("my father needs a kidney machine") and a place (PIN code, place name or a map click). Care Finder returns the nearest facilities that offer the service, ranked by how strong the evidence is. Each result quotes the facility's own text and says honestly how sure we are.

- **Live app:** Databricks App `vf-locator`, https://vf-locator-7474654371578222.aws.databricksapps.com (Databricks sign-in required)
- **Submission notebook:** [`submission/vf_care_finder.ipynb`](submission/vf_care_finder.ipynb) — the whole pipeline, step by step, with saved outputs
- **Method in plain words:** [`reports/executive_summary.md`](reports/executive_summary.md)
- **Decisions and judge Q&A:** [`reports/presenter_brief.md`](reports/presenter_brief.md)
- **Demo video script:** [`reports/demo_script.md`](reports/demo_script.md)

## How it works, in one paragraph

The dataset (10,077 Indian facilities, scraped and merged by an LLM) hides services in 451,000 short sentences, and some records mix text from several hospitals. We clean the records, place every facility on the map with a confidence level, and give each one a facility type. An LLM tags every distinct sentence once, with the services it claims and how strong the claim is. A second LLM pass checks that each record's sentences belong to that facility. Rules then combine the evidence, department backing and facility type into four tiers: Confirmed, Likely, Possible and Unverified. Searches rank by tier, then distance. District health survey data (NFHS-5) adds context, and suggests nearby hospitals to call when no website mentions the service. It never changes a tier. Blind web checks: every Confirmed facility we could verify offered the service (30 of 30).

## Repository

| Path | What |
|---|---|
| `scripts/` | Pipeline: clean base, facility type, sentence tagging, ownership audit, lookups, verdicts, NFHS, validation |
| `sql/` | Location workstream: PIN and city centres, facility location with confidence |
| `app/` | The Databricks App: FastAPI backend (`main.py`, `queries.py`, `matcher.py`) and React + Leaflet front end (`frontend/`, built into `static/`). Deploy steps in [`app/README.md`](app/README.md) |
| `submission/` | The single-notebook submission |
| `reports/` | Build reports, validation results, method write-ups |
| `notebooks/` | The LLM throughput benchmark |
| `deploy/` | Deploy and SQL helper scripts |
| `task.md`, `dais-2026.md` | The challenge brief and dataset notes |

## Running it

Everything runs on **Databricks Free Edition**: one 2X-Small SQL warehouse, `ai_query` with Llama 3.3 70B, and a Databricks App. Source data is the read-only share `databricks_virtue_foundation_dataset_dais_2026`. All derived tables are in `workspace.vf`.

- **Read the pipeline:** open the submission notebook. By default (`REBUILD = False`, `RUN_LLM = False`) it only reads existing tables.
- **Rebuild:** set the flags in the notebook, or run the scripts in `scripts/` in the notebook's order. The LLM passes are the only expensive step.
- **App:** see `app/README.md`. Short version: `cd app/frontend && npm ci && npm run build`, then `databricks sync` and `databricks apps deploy vf-locator`.

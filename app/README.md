# vf-locator (Care finder)

Streamlit + folium Databricks App, one screen: **find a service**. One searchable dropdown
("<Group> / <Service>", every label in `workspace.vf.facility_service` except other_clinical;
the six headline services appear only under "Common searches"; default Dialysis), a point from
map click, PIN (`pin_point` median of post offices, or the directory median; wide PINs accepted
with a note) or place name (`city_point`). Results: tier (Confirmed, Likely, Possible,
Unverified), then facilities with exact coordinates before city/PIN-centroid ones (shown as
"in <city>, exact location unknown", no km), then distance. Map fits to the point plus results.
Services outside the 8 keyword-tier services show "Results still loading, coverage X%" until
tagging completes. A service with no real rows falls back to the sample table with a SAMPLE
DATA banner.

Files: `app.py` (UI), `queries.py` (all SQL), `config.py` (table names), `conn.py`
(warehouse connection via SDK `Config()`), `startup_probe.py` (smoke test incl. PIN 500001 dialysis; output in app logs).

## Deploy

```
databricks sync app /Users/yakin@andrew.cmu.edu/vf/locator --full \
  --exclude-from app/.syncignore --profile datathon
databricks apps deploy vf-locator \
  --source-code-path /Workspace/Users/yakin@andrew.cmu.edu/vf/locator --profile datathon
databricks apps logs vf-locator --profile datathon | grep PROBE   # verify
```

(`deploy/deploy.sh --app-only` does the same plus grants.) The app service principal has
`USE CATALOG workspace`, `USE SCHEMA, SELECT, EXECUTE` on `workspace.vf`, and `CAN_USE` on
warehouse `8ea2282aca435351` (app resource `sql-warehouse`).

Run locally: `DATABRICKS_CONFIG_PROFILE=datathon uvicorn main:app --port 8765` (py13 env + fastapi, uvicorn).

**Now FastAPI + static page** (`main.py`, `static/`); the Streamlit description above is the legacy UI in `streamlit_legacy/`.

## Front end (React + Vite)

Source is `frontend/` (React 18 + Leaflet, plain JSX, one store in `src/App.jsx`; components in
`src/components/`). It builds into `static/` (`index.html` + `static/assets/*`), which FastAPI serves;
the deployed app needs no Node. Rebuild after any front-end change, before syncing:

```
cd app/frontend && npm ci && npm run build      # node from /opt/homebrew/bin
```

`app/.syncignore` keeps `frontend/` (and its `node_modules/`) out of the workspace; pass it to
`databricks sync` with `--exclude-from` as above. Local dev with hot reload: run uvicorn on 8765, then
`npm run dev` in `frontend/` (Vite proxies `/api` and `/india.geojson`). The pre-React vanilla files are
in `static_vanilla/` for rollback: copy them into `static/` and redeploy.

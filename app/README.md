# vf-locator (Care finder)

FastAPI + React Databricks App. `main.py` serves the API and the built front end in `static/`; SQL lives in `queries.py`, table names in `config.py`, the plain-words matcher in `matcher.py`, place search in `places.py`, the warehouse connection in `conn.py`, and `startup_probe.py` runs a smoke test at start-up (output in the app logs).

## Deploy

```
databricks sync app /Users/yakin@andrew.cmu.edu/vf/locator --full \
  --exclude-from app/.syncignore --profile datathon
databricks apps deploy vf-locator \
  --source-code-path /Workspace/Users/yakin@andrew.cmu.edu/vf/locator --profile datathon
databricks apps logs vf-locator --profile datathon | grep PROBE   # verify
```

(`scripts/deploy.sh --app-only` does the same plus grants.) The app service principal has
`USE CATALOG workspace`, `USE SCHEMA, SELECT, EXECUTE` on `workspace.vf`, and `CAN_USE` on
warehouse `8ea2282aca435351` (app resource `sql-warehouse`).

Run locally: `DATABRICKS_CONFIG_PROFILE=datathon uvicorn main:app --port 8765` (py13 env + fastapi, uvicorn).

## Front end (React + Vite)

Source is `frontend/` (React 18 + Leaflet, plain JSX, one store in `src/App.jsx`; components in
`src/components/`). It builds into `static/` (`index.html` + `static/assets/*`), which FastAPI serves;
the deployed app needs no Node. Rebuild after any front-end change, before syncing:

```
cd app/frontend && npm ci && npm run build      # node from /opt/homebrew/bin
```

`app/.syncignore` keeps `frontend/` (and its `node_modules/`) out of the workspace; pass it to
`databricks sync` with `--exclude-from` as above. Local dev with hot reload: run uvicorn on 8765, then
`npm run dev` in `frontend/` (Vite proxies `/api` and `/india.geojson`).

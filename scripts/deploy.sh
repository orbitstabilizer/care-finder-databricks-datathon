#!/usr/bin/env bash
# Build the tables, then deploy the app. One script, both halves.
#   usage: scripts/deploy.sh [--sql-only | --app-only]
set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-datathon}"
APP_NAME="${VF_APP_NAME:-vf-locator}"
WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-8ea2282aca435351}"
WS_PATH="${VF_WS_PATH:-/Users/yakin@andrew.cmu.edu/vf/locator}"
PYTHON="${VF_PYTHON:-/opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="${1:-all}"

q() { databricks experimental aitools tools query "$1" --profile "$PROFILE" >/dev/null; }

if [[ "$MODE" != "--app-only" ]]; then
  echo "== building tables"
  DATABRICKS_CONFIG_PROFILE="$PROFILE" DATABRICKS_WAREHOUSE_ID="$WAREHOUSE_ID" \
    "$PYTHON" "$ROOT/scripts/run_sql.py"
fi

if [[ "$MODE" == "--sql-only" ]]; then exit 0; fi

echo "== app $APP_NAME"
if ! databricks apps get "$APP_NAME" --profile "$PROFILE" >/dev/null 2>&1; then
  databricks apps create --profile "$PROFILE" --json "$(cat <<JSON
{"name":"$APP_NAME","description":"Facility finder",
 "resources":[{"name":"sql-warehouse","description":"SQL warehouse",
   "sql_warehouse":{"id":"$WAREHOUSE_ID","permission":"CAN_USE"}}]}
JSON
)" >/dev/null
fi

SP=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json \
     | python3 -c 'import json,sys;print(json.load(sys.stdin)["service_principal_client_id"])')
echo "== granting app service principal $SP"
q "GRANT USE CATALOG ON CATALOG databricks_virtue_foundation_dataset_dais_2026 TO \`$SP\`"
q "GRANT USE SCHEMA, SELECT ON SCHEMA databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset TO \`$SP\`"
q "GRANT USE CATALOG ON CATALOG workspace TO \`$SP\`"
q "GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.vf TO \`$SP\`"

echo "== uploading source"
databricks sync "$ROOT/app" "$WS_PATH" --full --profile "$PROFILE" >/dev/null

echo "== deploying"
databricks apps deploy "$APP_NAME" \
  --source-code-path "/Workspace${WS_PATH}" --profile "$PROFILE" -o json \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])'

databricks apps get "$APP_NAME" --profile "$PROFILE" -o json \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["url"])'

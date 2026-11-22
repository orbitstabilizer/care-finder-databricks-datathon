"""Download the Virtue Foundation datathon tables from Databricks to local Parquet.

Usage:  .venv/bin/python download_data.py
Re-run any time; it overwrites data/*.parquet.
"""

import json
import pathlib
import subprocess

from databricks import sql

PROFILE = "datathon"
HOST = "dbc-70851148-db1d.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/8ea2282aca435351"
CATALOG = "databricks_virtue_foundation_dataset_dais_2026"
SCHEMA = "virtue_foundation_dataset"
TABLES = [
    "facilities",
    "india_post_pincode_directory",
    "nfhs_5_district_health_indicators",
]

OUT = pathlib.Path(__file__).parent / "data"


def access_token() -> str:
    """Short-lived OAuth token from the already-configured CLI profile."""
    raw = subprocess.run(
        ["databricks", "auth", "token", "-p", PROFILE],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(raw)["access_token"]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sql.connect(
        server_hostname=HOST,
        http_path=HTTP_PATH,
        access_token=access_token(),
    ) as conn:
        for table in TABLES:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {CATALOG}.{SCHEMA}.{table}")
                df = cur.fetchall_arrow().to_pandas()
            path = OUT / f"{table}.parquet"
            df.to_parquet(path, index=False)
            print(f"{table:38s} {len(df):>7,} rows x {df.shape[1]:>3} cols  -> {path.name}")


if __name__ == "__main__":
    main()

"""Connection to the SQL warehouse.

This is the ONLY place the laptop run and the deployed run differ, and even
here the difference is handled by the SDK: Config() picks up
DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET when running as a Databricks
App, and DATABRICKS_CONFIG_PROFILE / ~/.databrickscfg on a laptop.
"""
import os
from databricks import sql
from databricks.sdk.core import Config
from config import WAREHOUSE_ID


def connect():
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        credentials_provider=lambda: cfg.authenticate,
    )

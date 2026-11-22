"""Single source of truth for schema, table and constant names."""
import os

# --- where the data lives -------------------------------------------------
SHARE_CATALOG  = os.getenv("VF_SHARE_CATALOG",  "databricks_virtue_foundation_dataset_dais_2026")
SHARE_SCHEMA   = os.getenv("VF_SHARE_SCHEMA",   "virtue_foundation_dataset")
TARGET_CATALOG = os.getenv("VF_TARGET_CATALOG", "workspace")
TARGET_SCHEMA  = os.getenv("VF_TARGET_SCHEMA",  "vf")

SRC = f"{SHARE_CATALOG}.{SHARE_SCHEMA}"
TGT = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"

T_FACILITIES = f"{SRC}.facilities"
T_PINCODE    = f"{SRC}.india_post_pincode_directory"
T_PIN_POINT  = f"{TGT}.pin_point"
T_CITY_POINT = f"{TGT}.city_point"
T_FAC_LOC    = f"{TGT}.facility_location"
F_HAVERSINE  = f"{TGT}.haversine_km"

# --- constants ------------------------------------------------------------
NEAR_KM             = 50.0
PIN_TIGHT_KM        = 25.0
PREFIX_OUTLIER_KM   = 100.0
MIN_CITY_FACILITIES = 5
LAT_MIN, LAT_MAX    = 6.0, 38.0
LON_MIN, LON_MAX    = 68.0, 98.0

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "8ea2282aca435351")

def subs() -> dict:
    """Values available to sql/*.sql as {placeholders}."""
    return {k: v for k, v in globals().items() if k.isupper()}

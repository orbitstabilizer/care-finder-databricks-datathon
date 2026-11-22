# Databricks notebook source
# MAGIC %md
# MAGIC # Virtue Foundation — exploration
# MAGIC
# MAGIC Reads `facilities` straight from the Delta Sharing catalog (read-only).
# MAGIC Anything we write goes to `workspace.vf`.
# MAGIC
# MAGIC See `CLAUDE.md` in the repo for the brief, data gotchas and the agreed plan.

# COMMAND ----------

CATALOG = "databricks_virtue_foundation_dataset_dais_2026"
SCHEMA = "virtue_foundation_dataset"

fac = spark.table(f"{CATALOG}.{SCHEMA}.facilities")
pin = spark.table(f"{CATALOG}.{SCHEMA}.india_post_pincode_directory")
nfhs = spark.table(f"{CATALOG}.{SCHEMA}.nfhs_5_district_health_indicators")

for name, df in [("facilities", fac), ("pincode", pin), ("nfhs5", nfhs)]:
    print(f"{name:12s} {df.count():>7,} rows x {len(df.columns):>3} cols")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parsing the JSON list columns
# MAGIC
# MAGIC Every column in `facilities` is a `STRING` except `latitude` / `longitude`.
# MAGIC These six hold JSON-encoded arrays.

# COMMAND ----------

from pyspark.sql import functions as F

LIST_COLS = ["specialties", "procedure", "equipment", "capability", "phone_numbers", "source_urls"]

fac_parsed = fac
for col in LIST_COLS:
    fac_parsed = fac_parsed.withColumn(
        f"{col}_arr",
        F.filter(
            F.coalesce(F.from_json(F.col(col), "array<string>"), F.array()),
            lambda x: x.isNotNull() & (F.trim(x) != ""),
        ),
    )

fac_parsed = fac_parsed.cache()

display(
    fac_parsed.select(
        *[F.size(f"{c}_arr").alias(c) for c in LIST_COLS]
    ).summary("mean", "50%", "max")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## The evidence frame
# MAGIC
# MAGIC One row per `(facility, snippet, source_field)` — ~460k rows.
# MAGIC This is the grain everything downstream should work at, because
# MAGIC **claims belong to sentences, not to records** (see next section).

# COMMAND ----------

from functools import reduce

EVIDENCE_FIELDS = ["procedure", "capability", "equipment"]

evidence = reduce(
    lambda a, b: a.unionByName(b),
    [
        fac_parsed.select(
            "unique_id",
            "name",
            "address_city",
            "address_stateOrRegion",
            F.explode(f"{field}_arr").alias("snippet"),
            F.lit(field).alias("source_field"),
        )
        for field in EVIDENCE_FIELDS
    ],
).cache()

print(f"{evidence.count():,} snippets")
display(evidence.groupBy("source_field").count().orderBy(F.desc("count")))

# COMMAND ----------

# MAGIC %md
# MAGIC ## The core problem: snippets don't belong to their record
# MAGIC
# MAGIC Records merge several hospitals. A naive `LIKE '%dialysis%'` on the record
# MAGIC returns facilities that do not offer dialysis at all.

# COMMAND ----------

# Aravind Eye Hospital, Hyderabad -- an EYE hospital with a 20-bed dialysis unit?
display(
    evidence.filter(F.lower("snippet").contains("dialysis"))
    .filter(F.lower("name").contains("aravind eye"))
    .select("name", "address_city", "source_field", "snippet")
    .limit(5)
)

# COMMAND ----------

# Snippets that name a DIFFERENT facility than the record they sit in.
# Crude proxy: the snippet says "at <X> Hospital" and <X>'s first word is absent
# from the record name.
NAMED = r"\bat ([A-Z][A-Za-z.'&\- ]{3,40}(?:Hospital|Institute|Centre|Center|Clinic))"

attributed = evidence.withColumn("named_facility", F.regexp_extract("snippet", NAMED, 1)).filter(
    F.col("named_facility") != ""
)

mismatch = attributed.filter(
    ~F.lower("name").contains(F.lower(F.split("named_facility", " ")[0]))
).cache()

print(f"{mismatch.count():,} snippets name a facility that doesn't match their record")
print(f"across {mismatch.select('unique_id').distinct().count():,} facilities")
display(mismatch.select("name", "named_facility", "snippet").limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Specialties — the inherited taxonomy
# MAGIC
# MAGIC Already a clean controlled vocabulary. Note these are **departments**, not
# MAGIC services: `nephrology` is not `dialysis`.

# COMMAND ----------

spec = (
    fac_parsed.select("unique_id", F.explode("specialties_arr").alias("specialty"))
    .distinct()  # values repeat within a row
)

print(f"{spec.select('specialty').distinct().count()} distinct specialties")
display(spec.groupBy("specialty").count().orderBy(F.desc("count")).limit(40))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Geography
# MAGIC
# MAGIC Coordinates are trustworthy (99% present). Place names are not —
# MAGIC `address_stateOrRegion` has far more distinct values than India has states.

# COMMAND ----------

display(
    fac.select(
        F.sum(F.col("latitude").isNotNull().cast("int")).alias("geocoded"),
        F.count("*").alias("total"),
        F.countDistinct("address_stateOrRegion").alias("distinct_states_should_be_37"),
        F.countDistinct("address_city").alias("distinct_cities"),
    )
)

# COMMAND ----------

# PIN -> coordinates lookup, deduplicated (source grain is post office, not PIN)
pin_geo = (
    pin.withColumn("lat", F.col("latitude").cast("double"))
    .withColumn("lon", F.col("longitude").cast("double"))
    .filter(F.col("lat").isNotNull() & F.col("lon").isNotNull())
    .groupBy("pincode")
    .agg(
        F.expr("percentile_approx(lat, 0.5)").alias("lat"),
        F.expr("percentile_approx(lon, 0.5)").alias("lon"),
        F.first("district").alias("district"),
        F.first("statename").alias("state"),
    )
)

print(f"PIN lookup rows: {pin_geo.count():,}")
display(pin_geo.limit(10))

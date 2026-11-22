# Databricks notebook source
# MAGIC %md
# MAGIC # Benchmark: ai_classify on serverless compute
# MAGIC Measures throughput vs the 2X-Small SQL warehouse (~4 snippets/sec).

# COMMAND ----------

import time

CAT = "databricks_virtue_foundation_dataset_dais_2026"
SCH = "virtue_foundation_dataset"
LABELS = ("dialysis","maternity_childbirth","neonatal_icu","cardiac","imaging",
          "trauma_emergency","oncology","orthopedic","other")
LBL_SQL = ",".join(f"'{l}'" for l in LABELS)

for N in (200, 1000):
    sql = f"""
    WITH ev AS (
      SELECT explode(from_json(procedure,'array<string>')) AS s
      FROM {CAT}.{SCH}.facilities
    ),
    c AS (
      SELECT DISTINCT trim(s) AS s FROM ev
      WHERE s IS NOT NULL AND length(trim(s)) BETWEEN 10 AND 300
      LIMIT {N}
    )
    SELECT COUNT(*) AS n, COUNT(DISTINCT lbl) AS labels
    FROM (SELECT ai_classify(s, ARRAY({LBL_SQL})) AS lbl FROM c)
    """
    t0 = time.time()
    row = spark.sql(sql).collect()[0]
    dt = time.time() - t0
    print(f"N={N:>5}  {dt:7.1f}s  {row['n']/dt:6.1f} snippets/sec  labels={row['labels']}")

---
title: "Snowpark to Dynamic Table"
subtitle: "How Python features become SQL Dynamic Tables"
---

## Overview

A common question when evaluating Snowflake Feature Store is: *"How does Python feature logic actually run inside a Dynamic Table?"* This appendix explains the end-to-end path from Snowpark DataFrame to Dynamic Table, the limitations that arise from that translation, and optimisation strategies for production pipelines.

Examples that need a database and schema use the same **canonical names** as the rest of this guide: database `FEATURE_STORE_DEMO`, Feature Store schema `FEATURE_STORE`, source schema `CLICKSTREAM_DATA`, warehouse `FS_DEV_WH`, and Feature View versions in **`V01`** format (dynamic table suffix `$V01`).

## 1. The Translation Path

When you define feature transformations in Python using Snowpark DataFrames, **no Python code ships to the Dynamic Table**. The pipeline works as follows:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│               SNOWPARK DATAFRAME → DYNAMIC TABLE PATH                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DEVELOPMENT TIME                                                            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────────┐  │
│  │  Snowpark Python │───▶│  SQL Query Plan  │───▶│  Feature View Object   │  │
│  │  DataFrame ops   │    │  (lazy, logical) │    │  (name, entity, freq)  │  │
│  └──────────────────┘    └──────────────────┘    └───────────┬────────────┘  │
│                                                              │               │
│  REGISTRATION TIME                                           ▼               │
│                                                  ┌────────────────────────┐  │
│                                                  │  CREATE DYNAMIC TABLE  │  │
│                                                  │  ... AS <generated SQL>│  │
│                                                  └───────────┬────────────┘  │
│                                                              │               │
│  RUNTIME (refresh cycles)                                    ▼               │
│                                                  ┌────────────────────────┐  │
│                                                  │  Pure SQL execution    │  │
│                                                  │  (no Python involved)  │  │
│                                                  └────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Step 1 -- Snowpark DataFrame (Lazy Evaluation)

Snowpark DataFrames are *lazily evaluated*. Each operation (`filter`, `select`, `join`, `group_by`, `agg`, etc.) appends to a logical query plan but does not execute immediately. The Python syntax is a thin wrapper around SQL semantics.

```python
from snowflake.ml.feature_store import FeatureView, Entity
import snowflake.snowpark.functions as F

user_purchase_df = (
    session.table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS")
    .group_by("USER_ID")
    .agg(
        F.count_distinct("ORDER_ID").alias("ORDER_CNT"),
        F.sum("AMOUNT").alias("TOTAL_SPEND"),
        F.avg("AMOUNT").alias("AVG_ORDER_AMT"),
        F.max("ORDER_TS").alias("LAST_ORDER_TS"),
    )
)
```

### Step 2 -- Query Pushdown (Python-to-SQL Translation)

When the DataFrame is consumed -- either by an action like `collect()` or by passing it to a Feature View -- Snowpark translates the entire chain of operations into a single optimised SQL statement. You can inspect the generated SQL at any time:

```python
print(user_purchase_df.queries)
```

This produces the equivalent:

```sql
SELECT USER_ID,
       COUNT(DISTINCT ORDER_ID) AS ORDER_CNT,
       SUM(AMOUNT)              AS TOTAL_SPEND,
       AVG(AMOUNT)              AS AVG_ORDER_AMT,
       MAX(ORDER_TS)            AS LAST_ORDER_TS
FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS
GROUP BY USER_ID
```

The translation is direct and deterministic: `F.sum()` becomes `SUM()`, `F.col("X") / F.col("Y")` becomes `X / Y`, `.filter()` becomes `WHERE`, `.join()` becomes `JOIN`, and so on. You can also write SQL directly via `session.sql("SELECT ...")` -- the end result is identical.

### Step 3 -- Feature View Registration Creates a Dynamic Table

When you register a Feature View with a `refresh_freq`, the Feature Store API issues a `CREATE DYNAMIC TABLE ... AS <generated-SQL>`. From that point forward, the Dynamic Table is a **pure SQL object** -- no Python interpreter is involved in the refresh cycle.

```python
user_purchase_fv = FeatureView(
    name="USER_PURCHASE_STATS",
    entities=[user_entity],
    feature_df=user_purchase_df,
    timestamp_col="LAST_ORDER_TS",
    refresh_freq="15 minutes",
    desc="User purchase statistics"
)

fs.register_feature_view(feature_view=user_purchase_fv, version="V01")
```

Users who prefer to express feature-engineering logic directly in SQL can do so by wrapping a raw SQL SELECT statement in `session.sql()` and passing the resulting DataFrame as the `feature_df`. The outcome is identical -- the SQL text is used as-is for the Dynamic Table definition:

```python
user_purchase_df = session.sql("""
    SELECT USER_ID,
           COUNT(DISTINCT ORDER_ID) AS ORDER_CNT,
           SUM(AMOUNT)              AS TOTAL_SPEND,
           AVG(AMOUNT)              AS AVG_ORDER_AMT,
           MAX(ORDER_TS)            AS LAST_ORDER_TS
    FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS
    GROUP BY USER_ID
""")

user_purchase_fv = FeatureView(
    name="USER_PURCHASE_STATS",
    entities=[user_entity],
    feature_df=user_purchase_df,
    timestamp_col="LAST_ORDER_TS",
    refresh_freq="15 minutes",
    desc="User purchase statistics"
)
```

This is often preferable when teams already have well-tested SQL transformations, or when the SQL is complex enough that the Snowpark DataFrame API machine generated SQL adds verbosity without added clarity.

> **Key takeaway:** Python is a development-time convenience. At runtime, the Dynamic Table refreshes by re-executing the generated SQL with no Python involvement. Whether you author with Snowpark DataFrames or raw SQL via `session.sql()`, the end result is the same.

---

## 2. Limitations: What Can and Cannot Be Expressed

Because the Dynamic Table is ultimately a SQL object, the constraints come from what Dynamic Tables support in their query definition.

### 2.1 Incremental vs Full Refresh

Dynamic Tables support three refresh modes:

- **Incremental** -- analyses the query to determine what changed since the last refresh and merges only those changes into the table.
- **Full** -- re-executes the entire query from scratch and replaces the previously materialised results.
- **AUTO** -- Snowflake evaluates the query at creation time and selects whichever mode it expects to be more cost- and time-effective.

Full refresh does not always imply slower or more expensive. The relative cost depends on several factors:

- **Incrementalisation overhead.** Incremental refresh must track changes, compute deltas, and merge them -- this bookkeeping has its own cost. For simple queries over small-to-moderate tables, a straightforward full recomputation can be faster than the incremental machinery.
- **Volume of changed data.** When a large proportion of rows change between refreshes (e.g., more than 5% of grouping keys), incremental refresh can end up doing *more* work than a full refresh because it recomputes each affected group individually.
- **Data locality.** Operators like `GROUP BY`, `DISTINCT`, `JOIN`, and window functions are sensitive to how well the source data is clustered by the relevant keys. Poor locality degrades incremental performance disproportionately.
- **Query complexity.** Highly complex queries with many joins, subqueries, or nested CTEs may produce incremental plans that are harder for the optimizer to execute efficiently.

When using **AUTO** mode, Snowflake takes these trade-offs into account at table creation time. If you are explicitly choosing a mode, consider benchmarking both to see which performs better for your specific workload.

Several SQL constructs **fall back to full refresh** or are unsupported entirely:

| Construct | Incremental | Full | Notes |
|-----------|:-----------:|:----:|-------|
| `SELECT`, `WHERE`, `FROM` | Supported | Supported | Performs consistently well |
| `GROUP BY` | Supported | Supported | Performance depends on data locality |
| `INNER JOIN`, `OUTER JOIN` | Supported | Supported | Best when one side is small or changes infrequently |
| `UNION ALL` | Supported | Supported | |
| `DISTINCT` | Supported | Supported | Locality-sensitive; prefer `QUALIFY` (see below) |
| Window functions (`ROW_NUMBER`, `RANK`, etc.) | Supported | Supported | Must include `PARTITION BY`; cluster source by partition keys |
| `LATERAL FLATTEN` | Supported | Supported | |
| Cortex AI/LLM functions | Supported (SELECT clause) | Supported | |
| Immutable UDFs (Python/Java/Scala) | Supported | Supported | Must not be marked `VOLATILE` |
| UDTFs (Python/Java/Scala) | Supported | Supported | SQL UDTFs not supported; must explicitly name output columns (no `SELECT *`) |
| `PIVOT` / `UNPIVOT` | **Not supported** | **Not supported** | |
| `SAMPLE` / `TABLESAMPLE` | **Not supported** | **Not supported** | |
| External functions | **Not supported** | **Not supported** | |
| Sequences (`SEQ1`, `SEQ2`) | Not supported | Supported | |
| Set operators (`MINUS`, `EXCEPT`, `INTERSECT`) | Not supported | Supported | `UNION` supported incrementally |
| Subqueries outside `FROM` | Not supported | Supported | |
| `WITH RECURSIVE` | Not supported | Supported | |
| `VOLATILE` UDFs | Not supported | Supported | |

> **Reference:** [Supported queries for dynamic tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-supported-queries)

### 2.2 Python UDFs and UDTFs in Dynamic Tables

UDFs and UDTFs provide a way to embed custom logic -- including Python with third-party libraries -- inside a Dynamic Table's SQL definition. They are **row-level transformations**: they operate on input columns from a single row and produce output for that row. They do not aggregate across rows or join between tables.

**UDF (scalar function):** Takes one or more input columns from a single row and returns a **single output column**. The output can be a scalar type (`FLOAT`, `STRING`, `INT`, etc.) or a compound type (`VARIANT`, `OBJECT`, `ARRAY`) when multiple values need to be packed into one column. Typical feature-engineering uses include:

- Applying a pre-trained scoring model (n feature columns in, one score out)
- Encoding or decoding a field using proprietary logic
- Computing a derived value from multiple columns that cannot be expressed with native SQL functions
- Parsing semi-structured data into a typed value

**UDTF (table function):** Takes one or more input columns from a single row and returns **multiple output columns** (or multiple output rows) per input row. Useful for exploding a `VARIANT` into structured columns or reshaping row data.

**Vectorised execution.** UDFs and UDTFs can be declared as vectorised, which means Snowflake sends batches of rows as Pandas DataFrames to the Python runtime rather than invoking the function row by row. This is an **execution-level optimisation** -- the logical contract is still row-in, value(s)-out, but throughput improves substantially because batch processing avoids per-row Python overhead.

If existing Python logic *cannot* be expressed as Snowpark DataFrame operations (e.g., proprietary libraries, complex numerical algorithms), you can:

1. Register a Python UDF (or UDTF) in Snowflake.
2. Call it from within the Dynamic Table's SQL definition.

According to the Snowflake documentation, both UDFs and UDTFs **are supported for incremental refresh** (the docs list them as separate entries in the support matrix). The DT refresh process applies them only to changed rows, just as it would any other expression in the SELECT clause. Neither inherently forces a full refresh.

**UDF caveats:**

- The UDF must be declared **`IMMUTABLE`** (not `VOLATILE`). `VOLATILE` UDFs are not supported for incremental refresh.
- **Replacing** an `IMMUTABLE` UDF while it is in use by an incremental-refresh DT will cause refresh failures. The DT must be recreated after replacing the UDF.
- UDFs that **import from an external stage** are not supported.
- SQL UDFs that **contain subqueries** are not supported for incremental refresh.
- **Vectorised UDFs** (processing Pandas DataFrames in batches) perform significantly better than scalar UDFs for large datasets.

**UDTF caveats:**

- **SQL UDTFs** are not supported in Dynamic Tables (only Python, Java, and Scala UDTFs).
- SELECT blocks that read from a UDTF must **explicitly specify columns** -- `SELECT *` from a UDTF is not allowed.
- As with UDFs, vectorised UDTFs are recommended for throughput.

```python
from snowflake.snowpark.types import PandasSeries, FloatType
from snowflake.snowpark.functions import udf, call_udf
import numpy as np

@udf(name="compute_custom_feature", is_permanent=True,
     packages=["pandas", "numpy"], replace=True)
def compute_custom_feature(amount: PandasSeries[float],
                           quantity: PandasSeries[int]) -> PandasSeries[float]:
    return amount * np.log1p(quantity)

feature_df = session.table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS").select(
    F.col("USER_ID"),
    call_udf("compute_custom_feature",
             F.col("AMOUNT"), F.col("QTY")).alias("CUSTOM_FEATURE"),
)
```

> **Bottom line:** Existing Python logic can run via `IMMUTABLE` UDFs within a Dynamic Table and still benefit from incremental refresh. Prefer vectorised UDFs for performance, and avoid replacing a UDF definition while a DT depends on it.

### 2.2.1 Common Pattern: UDF for Incremental Batch Inference

A particularly effective use of UDFs in Dynamic Tables is placing a model-scoring UDF at the **end** of a Feature View pipeline. Upstream DTs prepare and aggregate the features incrementally; a final DT calls a vectorised UDF that runs batch inference over those features. Because the UDF is `IMMUTABLE` and the DT supports incremental refresh, only the rows whose upstream features changed are scored -- giving you **incremental batch inference** without any external orchestration.

```python
# Upstream Feature View: features are incrementally maintained
user_features_fv = FeatureView(
    name="USER_FEATURES",
    entities=[user_entity],
    feature_df=user_features_df,
    refresh_freq="DOWNSTREAM",
)

# Final Feature View: scores new/changed rows via UDF
scored_df = (
    session.table("FEATURE_STORE_DEMO.FEATURE_STORE.USER_FEATURES$V01")
    .select(
        F.col("USER_ID"),
        F.col("TOTAL_SPEND"),
        F.col("ORDER_CNT"),
        call_udf("predict_churn_score",
                 F.col("TOTAL_SPEND"),
                 F.col("ORDER_CNT")).alias("CHURN_SCORE"),
    )
)

churn_score_fv = FeatureView(
    name="USER_CHURN_SCORES",
    entities=[user_entity],
    feature_df=scored_df,
    refresh_freq="1 hour",
    desc="Churn propensity scores - incremental batch inference"
)
```

This pattern is well-suited to use cases like propensity scoring, risk rating, or recommendation ranking where predictions need to stay fresh as features update, but a full re-score of the entire population each cycle would be wasteful.

### 2.3 Constructs That Prevent Incremental Refresh Entirely

The following patterns force every refresh to be a full recomputation:

- **Non-deterministic functions in SELECT** (e.g., `RANDOM()`, `CURRENT_TIMESTAMP()` outside WHERE/HAVING/QUALIFY)
- **Self-referential queries** (a DT reading its own previous state)
- **`VOLATILE` UDFs** -- even if the logic is deterministic, the `VOLATILE` marker tells the optimizer it cannot be trusted
- **Downstream incremental DTs cannot sit below upstream full-refresh DTs** -- an incremental DT is incompatible with the complete row changes that occur during each refresh of an upstream full-refresh table

---

## 3. View-Based Feature Views: The On-Demand Alternative

Not every Feature View needs a Dynamic Table. When you omit `refresh_freq`, the Feature Store creates a **view** instead. The transformation SQL is stored as a view definition and executed on-the-fly each time data is retrieved.

```python
product_attributes_fv = FeatureView(
    name="PRODUCT_ATTRIBUTES",
    entities=[product_entity],
    feature_df=product_df,
    timestamp_col="UPDATED_TS",
    # No refresh_freq → View-based Feature View
    desc="Product attributes - computed on query"
)
```

### When View-Based Feature Views Make Sense

- **Prototyping and development.** During early iteration you want to change feature definitions rapidly without waiting for DT materialisation or paying continuous refresh costs. A view lets you test transformations immediately.
- **Rarely accessed Feature Views.** If a Feature View is only consumed during periodic training runs (e.g., weekly or monthly), the cost of computing features on-the-fly at query time may be significantly lower than continuously maintaining a Dynamic Table.
- **Slowly changing or static dimensions.** Reference data (product catalogues, region mappings) that changes infrequently often does not justify a DT.

### Spine Filter Push-Down

A key advantage of view-based Feature Views during dataset generation is **spine filter push-down**. When the Feature Store performs an ASOF join against a view-based Feature View, the filters from the spine (entity keys and timestamps) are pushed down into the view query. This means the view **does not need to materialise its entire result set** -- only the rows relevant to the spine are computed. This can dramatically reduce compute cost for large source tables when the spine is selective.

### Escaping Dynamic Table Constraints with External Pipelines

If a transformation pipeline is too complex or time-consuming to be processed efficiently in Dynamic Tables -- for example, pipelines that involve unsupported constructs, extensive Python library dependencies, or orchestration logic that exceeds what a single SQL query can express -- the transformations can be expressed in **any external tool** (DBT, Airflow, Dagster, custom scripts, etc.). The resulting output table is then registered as a **view-based Feature View** that simply references the externally maintained table:

```python
# DBT (or any external tool) maintains the output table
# Register it as a view-based Feature View for FS integration
dbt_features_df = session.table("FEATURE_STORE_DEMO.FEATURE_STORE.USER_STATS")

dbt_fv = FeatureView(
    name="USER_STATS_DBT",
    entities=[user_entity],
    feature_df=dbt_features_df,
    timestamp_col="_DBT_UPDATED_TS",
    # No refresh_freq → View wrapping the externally managed table
    desc="User statistics - maintained by DBT pipeline"
)

fs.register_feature_view(feature_view=dbt_fv, version="V01")
```

This gives you the full Feature Store benefits -- point-in-time-correct dataset generation, entity-based retrieval, Model Registry lineage -- while keeping the transformation logic in the tool best suited for it. The external tool owns the refresh schedule; the Feature Store owns the feature contract.

---

## 4. Optimisation Strategies

### 4.1 Break Complex Pipelines into Chained Dynamic Tables

Long, complex Snowpark pipelines translate to long, complex SQL, which can degrade incremental refresh performance. The recommended pattern is to **decompose** into multiple Feature Views (each backed by its own Dynamic Table) chained together:

```python
# Stage 1: Cleaning and parsing
clean_df = session.table("RAW_EVENTS").select(
    F.col("USER_ID"),
    F.to_timestamp("EVENT_TS").alias("EVENT_TS"),
    F.col("AMOUNT").cast("FLOAT").alias("AMOUNT"),
)

clean_fv = FeatureView(
    name="EVENTS_CLEAN",
    entities=[user_entity],
    feature_df=clean_df,
    refresh_freq="DOWNSTREAM",
)
fs.register_feature_view(feature_view=clean_fv, version="V01")

# Stage 2: Aggregation (reads from Stage 1's DT)
agg_df = (
    session.table("FEATURE_STORE_DEMO.FEATURE_STORE.EVENTS_CLEAN$V01")
    .group_by("USER_ID")
    .agg(F.sum("AMOUNT").alias("TOTAL_SPEND"))
)

agg_fv = FeatureView(
    name="USER_SPEND_AGGREGATES",
    entities=[user_entity],
    feature_df=agg_df,
    refresh_freq="15 minutes",
)
fs.register_feature_view(feature_view=agg_fv, version="V01")
```

Benefits:

- **Better incremental refresh** -- simpler SQL per DT means the optimizer can reason about changes more effectively.
- **Independent monitoring** -- each stage has its own refresh history and health metrics.
- **Mixed refresh strategies** -- fast refresh for one stage, slower for another.
- **Full-refresh propagation awareness** -- any DT using full refresh forces all downstream DTs to also use full refresh (see Section 2.3). Design your chain so that stages using full-refresh constructs sit at the *end* of the pipeline, not the beginning. If this is unavoidable, consider whether the full-refresh stages should instead be handled by an external pipeline and wrapped as a view-based Feature View (see Section 3).

### 4.2 Optimise for Incremental Refresh

The Snowflake documentation provides specific guidance on operator-level optimisation:

**Cluster source tables by grouping/join/partition keys.** Data locality is the single biggest factor for incremental refresh performance. When changes affect a small portion of grouping keys, the DT only recomputes those groups.

**Keep changes to fewer than 5% of grouping keys per refresh.** When more than 5% of keys change, incremental refresh may be slower than full refresh.

**Use `QUALIFY ROW_NUMBER() ... = 1` instead of `DISTINCT` for deduplication.** The `QUALIFY` pattern has an optimised incremental path that performs consistently faster than `DISTINCT`, which is equivalent to `GROUP BY ALL`.

SQL:

```sql
-- Prefer this (optimised incremental path)
SELECT customer_id, customer_name, email, event_time
FROM customer_events
QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY event_time DESC) = 1

-- Over this (locality-sensitive, potentially slow)
SELECT DISTINCT customer_id, customer_name, email
FROM customer_events
```

Snowpark equivalent:

```python
from snowflake.snowpark.functions import row_number
from snowflake.snowpark import Window

# Prefer this (optimised incremental path)
window = Window.partition_by("CUSTOMER_ID").order_by(F.col("EVENT_TIME").desc())

deduped_df = (
    session.table("CUSTOMER_EVENTS")
    .select("CUSTOMER_ID", "CUSTOMER_NAME", "EMAIL", "EVENT_TIME")
    .with_column("RN", row_number().over(window))
    .filter(F.col("RN") == 1)
    .drop("RN")
)

# Over this (locality-sensitive, potentially slow)
distinct_df = (
    session.table("CUSTOMER_EVENTS")
    .select("CUSTOMER_ID", "CUSTOMER_NAME", "EMAIL")
    .distinct()
)
```

**Avoid compound expressions in `GROUP BY`.** Materialise computed columns in an upstream DT first, then group on the simple column reference in a downstream DT.

SQL:

```sql
-- Upstream DT: materialise the expression
CREATE DYNAMIC TABLE transactions_with_minute ...
AS SELECT DATE_TRUNC('minute', ts) AS ts_minute, amount
   FROM transactions;

-- Downstream DT: group on simple column
CREATE DYNAMIC TABLE minute_sums ...
AS SELECT ts_minute, SUM(amount)
   FROM transactions_with_minute
   GROUP BY 1;
```

Snowpark equivalent (as two chained Feature Views):

```python
# Upstream Feature View: materialise the expression
stage1_df = session.table("TRANSACTIONS").select(
    F.date_trunc("minute", F.col("TS")).alias("TS_MINUTE"),
    F.col("AMOUNT"),
)

stage1_fv = FeatureView(
    name="TRANSACTIONS_WITH_MINUTE",
    entities=[txn_entity],
    feature_df=stage1_df,
    refresh_freq="DOWNSTREAM",
)
fs.register_feature_view(feature_view=stage1_fv, version="V01")

# Downstream Feature View: group on simple column
stage2_df = (
    session.table("FEATURE_STORE_DEMO.FEATURE_STORE.TRANSACTIONS_WITH_MINUTE$V01")
    .group_by("TS_MINUTE")
    .agg(F.sum("AMOUNT").alias("TOTAL_AMOUNT"))
)

stage2_fv = FeatureView(
    name="MINUTE_SUMS",
    entities=[txn_entity],
    feature_df=stage2_df,
    refresh_freq="15 minutes",
)
fs.register_feature_view(feature_view=stage2_fv, version="V01")
```

**For joins, cluster the dimension table** (the side that changes less often) by the join key. For `OUTER JOIN`s, put the table that changes more frequently on the `LEFT` side. Clustering is configured at the table level via SQL (`ALTER TABLE ... CLUSTER BY ...`) and applies regardless of whether you author the Feature View in Snowpark or SQL.

**Always include `PARTITION BY` in window functions.** Window functions without `PARTITION BY` result in full recomputation of the entire result set on every refresh.

```python
# Good: partition_by included
window = Window.partition_by("REGION").order_by(F.col("AMOUNT").desc())
ranked_df = sales_df.with_column("SALES_RANK", F.rank().over(window))

# Bad: no partition_by -- forces full recomputation every refresh
window_all = Window.order_by(F.col("AMOUNT").desc())
ranked_df = sales_df.with_column("GLOBAL_RANK", F.rank().over(window_all))
```

### 4.3 Reduce Refresh Cost with Immutability Constraints

Dynamic Tables with large historical datasets can incur significant compute costs during refresh -- especially when dimension table changes force recomputation of the entire result set, or when queries that cannot incrementalise well (e.g., multiple LEFT OUTER JOINs) fall back to full refresh.

The [`IMMUTABLE WHERE`](https://docs.snowflake.com/en/user-guide/dynamic-tables-performance-optimize-immutability) clause lets you declare that rows matching a condition will **never change**, so Snowflake skips them entirely during refresh. Only the mutable region is reprocessed.

```sql
CREATE DYNAMIC TABLE USER_EVENT_FEATURES
  TARGET_LAG = '1 hour'
  WAREHOUSE = FS_DEV_WH
  IMMUTABLE WHERE (LAST_EVENT_TS < CURRENT_TIMESTAMP() - INTERVAL '7 days')
  AS
    SELECT USER_ID,
           COUNT(EVENT_ID)  AS EVENT_CNT,
           MAX(EVENT_TS)    AS LAST_EVENT_TS
    FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.EVENTS
    GROUP BY USER_ID;
```

With this definition, events older than 7 days are locked. If an upstream dimension table changes, only the last 7 days of aggregates are recomputed rather than the full history.

**Key use cases for Feature Store pipelines:**

| Scenario | How IMMUTABLE WHERE helps |
|----------|--------------------------|
| **Dimension table updates** | Changes to a dimension (e.g., product category rename) don't trigger recomputation of historical fact aggregates |
| **Expensive UDF scoring** | Model inference or LLM calls on historical rows are preserved; only new rows are scored |
| **Full-refresh DTs** | Queries that cannot incrementalise (multiple OUTER JOINs, UDTFs) only reprocess the mutable window instead of the entire table |
| **Source data retention** | Delete old source data to save storage while retaining historical aggregates in the DT |
| **Downstream incremental refresh** | A downstream DT can use incremental refresh even if its upstream DT uses full refresh, provided both declare `IMMUTABLE WHERE` |

**Backfill from existing data.** `IMMUTABLE WHERE` pairs with `BACKFILL FROM` to copy historical data from an existing table (or a clone of a prior DT version) into a new DT without recomputing it. This is particularly valuable for [schema evolution](../../04_feature_views/index.qmd#sec-schema-evolution) -- adding new feature columns to a large Feature View without paying the cost of a full historical recompute. See Chapter 04 for the detailed workflow.

You can check whether a row is immutable via the `METADATA$IS_IMMUTABLE` pseudo-column:

```sql
SELECT *, METADATA$IS_IMMUTABLE FROM USER_EVENT_FEATURES LIMIT 10;
```

> **Note:** `IMMUTABLE WHERE` and `BACKFILL FROM` are Dynamic Table SQL features and are not currently exposed through the Feature Store Python API. Other SQL-only DT features -- `INITIALIZATION_WAREHOUSE`, `ROW_TIMESTAMP`, `DATA_RETENTION_TIME_IN_DAYS`, and `MAX_DATA_EXTENSION_TIME_IN_DAYS` -- are also valuable for Feature Store pipelines; see [Chapter 11: Dynamic Table SQL Features Beyond the API](../../11_operations/index.qmd#sec-dt-sql-features) for details. To use any of these with Feature Store, create the DT via SQL and wrap it as a view-based Feature View, or use `ALTER DYNAMIC TABLE` after the API creates the DT. Check the [Feature Store release notes](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store) for future API integration.

> **Reference:** [Use immutability constraints](https://docs.snowflake.com/en/user-guide/dynamic-tables-performance-optimize-immutability) | [Introducing Immutability for Dynamic Tables (engineering blog)](https://www.snowflake.com/en/engineering-blog/dynamic-tables-immutability/)

### 4.4 Choose an Appropriate Target Lag

Dynamic Tables do **not** blindly re-execute on every refresh cycle. The scheduler checks for upstream changes and only triggers warehouse compute when there is new data to process. This change-detection check is near-zero cost, so a short target lag on a source that updates infrequently does not waste significant compute -- the DT simply checks more often and finds nothing to do.

That said, target lag is still worth considering:

- **Shorter target lag** means the DT is ready to process changes sooner, giving lower latency from source change to feature availability. The compute cost is driven by the volume and frequency of actual data changes, not the target lag itself.
- **Longer target lag** allows Snowflake to batch multiple small changes into fewer, larger refresh operations, which can be more efficient for high-frequency sources where micro-batching would otherwise create overhead.

Choose your target lag based on how quickly downstream consumers need to see updated features, rather than trying to match it exactly to the source update cadence.

| Use Case | Suggested Target Lag | Rationale |
|----------|---------------------|-----------|
| Real-time fraud / personalisation | `1 minute` | Features must reflect latest activity promptly |
| Operational ML features | `5-15 minutes` | Balance of freshness and batching efficiency |
| Standard reporting / training features | `1 hour` | Consumers tolerate moderate lag |
| Slowly changing dimensions | `1 day` or greater | Source changes are infrequent |

---

## 5. Summary

| Question | Answer |
|----------|--------|
| How does Python become a Dynamic Table? | Snowpark translates DataFrame operations to SQL at registration time. The DT is a pure SQL object -- no Python runs during refresh. |
| Can we use existing Python code? | Yes, via `IMMUTABLE` UDFs called within the DT definition. Immutable UDFs are supported for incremental refresh. Prefer vectorised UDFs for performance, and avoid replacing a UDF while a DT depends on it. |
| What are the limitations? | Certain SQL constructs don't support incremental refresh (`PIVOT`, external functions, `VOLATILE` UDFs, set operators other than `UNION`/`UNION ALL`). See the [supported queries documentation](https://docs.snowflake.com/en/user-guide/dynamic-tables-supported-queries) for the full matrix. |
| What about view-based Feature Views? | Omit `refresh_freq` to create a view instead of a DT. The query runs on-the-fly at retrieval time with spine filter push-down. Ideal for prototyping, rarely accessed features, or wrapping externally managed tables (DBT, Airflow, etc.). |
| How do we optimise? | Break long pipelines into chained DTs, cluster source data by grouping/join keys, use `QUALIFY` over `DISTINCT`, choose target lag based on consumer freshness needs, and use `IMMUTABLE WHERE` to skip recomputation of historical rows. |

## References

- [Snowpark DataFrames](https://docs.snowflake.com/en/developer-guide/snowpark/python/working-with-dataframes) -- how lazy evaluation and query pushdown work
- [Dynamic Tables overview](https://docs.snowflake.com/en/user-guide/dynamic-tables-about) -- architecture and refresh mechanics
- [Supported queries for Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-supported-queries) -- full incremental/full support matrix
- [Optimise queries for incremental refresh](https://docs.snowflake.com/en/user-guide/dynamic-tables-performance-optimize-query) -- operator-level tuning guidance
- [Use immutability constraints](https://docs.snowflake.com/en/user-guide/dynamic-tables-performance-optimize-immutability) -- IMMUTABLE WHERE and BACKFILL FROM
- [Chapter 04: Feature Views](../../04_feature_views/index.qmd) -- DT vs View Feature View types
- [Chapter 05: Feature Pipelines](../../05_feature_pipelines/index.qmd) -- pipeline architecture patterns

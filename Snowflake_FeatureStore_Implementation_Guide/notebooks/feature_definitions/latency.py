"""
Latency measurement framework for the Feature Store pipeline.

Measures freshness and propagation delay at every pipeline stage:
  Source tables -> DT Feature Views (tier 1) -> chained DTs (tier 2) -> OFTs

Uses METADATA$ROW_LAST_COMMIT_TIME (ROW_TIMESTAMP) for DTs and standard tables,
and propagated timestamps for OFTs (which may not support ROW_TIMESTAMP natively).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .config import get_config


# ---------------------------------------------------------------------------
# Per-table freshness
# ---------------------------------------------------------------------------

SOURCE_TABLES = ["SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"]

TIER1_DTS = [
    "SESSION_BEHAVIOR_FEATURES$V01",
    "USER_RECENCY_RAW$V01",
    "USER_PURCHASE_AGGREGATES$V03",
    "USER_SESSION_ENGAGEMENT$V01",
    "USER_ENGAGEMENT_REALTIME$V01",
    "USER_TREND_FEATURES$V01",
]

TIER2_DTS: list[str] = []

WIDE_DTS = [
    "USER_PERMUTATION_FEATURES_WIDE$V01",
    "PRODUCT_EMBEDDINGS$V01",
]


def get_table_freshness(session, env: str = "DEV",
                        schema_key: str = "source_schema",
                        tables: list[str] | None = None) -> list[dict]:
    """Query MAX(METADATA$ROW_LAST_COMMIT_TIME) for a list of tables.

    Returns a list of dicts with table name, last commit time, and age in seconds.
    """
    cfg = get_config(env)
    db = cfg["database"]
    schema = cfg[schema_key]
    tables = tables or SOURCE_TABLES
    results = []

    for table in tables:
        try:
            row = session.sql(f"""
                SELECT
                    MAX(METADATA$ROW_LAST_COMMIT_TIME) AS LAST_COMMIT_TIME,
                    TIMESTAMPDIFF('SECOND',
                        MAX(METADATA$ROW_LAST_COMMIT_TIME),
                        CURRENT_TIMESTAMP()) AS AGE_SECONDS
                FROM {db}.{schema}.{table}
            """).collect()[0]
            results.append({
                "TABLE": table,
                "SCHEMA": schema,
                "LAST_COMMIT_TIME": row["LAST_COMMIT_TIME"],
                "AGE_SECONDS": row["AGE_SECONDS"],
            })
        except Exception as e:
            results.append({
                "TABLE": table,
                "SCHEMA": schema,
                "LAST_COMMIT_TIME": None,
                "AGE_SECONDS": None,
                "ERROR": str(e),
            })
    return results


def get_source_freshness(session, env: str = "DEV") -> list[dict]:
    return get_table_freshness(session, env, "source_schema", SOURCE_TABLES)


def get_dt_freshness(session, env: str = "DEV",
                     dt_names: list[str] | None = None) -> list[dict]:
    """Query ROW_TIMESTAMP freshness for DT-backed Feature Views."""
    cfg = get_config(env)
    all_dts = dt_names or (TIER1_DTS + TIER2_DTS + WIDE_DTS)
    return get_table_freshness(session, env, "fs_schema", all_dts)


# ---------------------------------------------------------------------------
# Cross-stage latency
# ---------------------------------------------------------------------------

def measure_stage_latency(session, env: str = "DEV") -> list[dict]:
    """Measure latency between each pipeline stage.

    Queries each table independently and computes the delta.
    Per the Snowflake docs, ROW_TIMESTAMPs are only reliably ordered
    within the same table, so cross-table comparisons are approximate.

    Returns a list of dicts:
      stage, from_table, to_table, from_commit, to_commit, latency_seconds
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    fs = cfg["fs_schema"]

    def _max_commit(fqn: str):
        try:
            row = session.sql(f"""
                SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS TS
                FROM {fqn}
            """).collect()[0]
            return row["TS"]
        except Exception:
            return None

    results = []
    stage_pairs = [
        ("source->tier1_dt", f"{db}.{src}.SESSIONS",
         f'{db}.{fs}."SESSION_BEHAVIOR_FEATURES$V01"'),
        ("source->tier1_dt", f"{db}.{src}.ORDERS",
         f'{db}.{fs}."USER_RECENCY_RAW$V01"'),
        ("source->tier1_dt", f"{db}.{src}.ORDERS",
         f'{db}.{fs}."USER_PURCHASE_AGGREGATES$V03"'),
        ("source->tier1_dt", f"{db}.{src}.EVENTS",
         f'{db}.{fs}."USER_SESSION_ENGAGEMENT$V01"'),
        ("source->tier1_dt", f"{db}.{src}.EVENTS",
         f'{db}.{fs}."USER_ENGAGEMENT_REALTIME$V01"'),
    ]

    for stage, from_tbl, to_tbl in stage_pairs:
        from_ts = _max_commit(from_tbl)
        to_ts = _max_commit(to_tbl)

        lat = None
        if from_ts and to_ts:
            lat = int((to_ts - from_ts).total_seconds())

        results.append({
            "STAGE": stage,
            "FROM_TABLE": from_tbl.split(".")[-1].strip('"'),
            "TO_TABLE": to_tbl.split(".")[-1].strip('"'),
            "FROM_COMMIT": from_ts,
            "TO_COMMIT": to_ts,
            "LATENCY_SECONDS": lat,
        })

    return results


# ---------------------------------------------------------------------------
# Batch-level latency from GENERATION_LOG
# ---------------------------------------------------------------------------

def get_batch_latency(session, env: str = "DEV",
                      last_n: int = 10) -> list[dict]:
    """Return per-batch stats from GENERATION_LOG, with source freshness.

    If ROW_TIMESTAMP is enabled, also includes ingestion latency computed
    from METADATA$ROW_LAST_COMMIT_TIME.
    """
    cfg = get_config(env)
    db = cfg["database"]
    admin = cfg["admin_schema"]
    src = cfg["source_schema"]

    # Try the full query with ROW_TIMESTAMP; fall back to log-only
    try:
        rows = session.sql(f"""
            WITH batches AS (
                SELECT LOG_ID, BATCH_TS, SESSIONS_GENERATED, EVENTS_GENERATED,
                       ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS
                FROM {db}.{admin}.GENERATION_LOG
                WHERE STATUS = 'SUCCESS'
                ORDER BY LOG_ID DESC
                LIMIT {last_n}
            ),
            src_fresh AS (
                SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS LATEST_SOURCE_COMMIT
                FROM {db}.{src}.SESSIONS
            )
            SELECT b.*, s.LATEST_SOURCE_COMMIT,
                   TIMESTAMPDIFF('SECOND', b.BATCH_TS, s.LATEST_SOURCE_COMMIT)
                       AS INGEST_LATENCY_SECONDS
            FROM batches b, src_fresh s
            ORDER BY b.LOG_ID DESC
        """).collect()
    except Exception:
        rows = session.sql(f"""
            SELECT LOG_ID, BATCH_TS, SESSIONS_GENERATED, EVENTS_GENERATED,
                   ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS
            FROM {db}.{admin}.GENERATION_LOG
            WHERE STATUS = 'SUCCESS'
            ORDER BY LOG_ID DESC
            LIMIT {last_n}
        """).collect()

    return [r.as_dict() for r in rows]


# ---------------------------------------------------------------------------
# OFT freshness
# ---------------------------------------------------------------------------

OFT_FEATURE_VIEWS = [
    {
        "name": "SESSION_BEHAVIOR_FEATURES",
        "version": "V01",
        "entity_key": "SESSION_ID",
        "strategy": "max_key",
    },
    {
        "name": "USER_RECENCY_RAW",
        "version": "V01",
        "entity_key": "USER_ID",
        "strategy": "max_key",
    },
]


def get_oft_freshness(session, env: str = "DEV",
                      oft_fvs: list[dict] | None = None,
                      fs=None) -> list[dict]:
    """Measure freshness of Online Feature Tables.

    Two strategies depending on the Feature View:

    * **timestamp** – The DT includes an ``UPDATED_TS = CURRENT_TIMESTAMP()``
      column that propagates into the OFT.  We compare it with the DT's
      ``METADATA$ROW_LAST_COMMIT_TIME`` to derive sync lag.
    * **max_key** – The DT is INCREMENTAL and has no embedded refresh
      timestamp.  We read ``MAX(entity_key)`` from the DT and check
      whether that key has reached the OFT yet.

    Both strategies also report the DT's ROW_TIMESTAMP as the
    authoritative "last refresh" indicator.

    Args:
        fs: A FeatureStore object.  If None, one will be created.
    """
    from datetime import timezone

    cfg = get_config(env)
    db = cfg["database"]
    fs_schema = cfg["fs_schema"]
    oft_fvs = oft_fvs or OFT_FEATURE_VIEWS

    if fs is None:
        from snowflake.ml.feature_store import FeatureStore, CreationMode
        fs = FeatureStore(
            session=session, database=db, name=fs_schema,
            default_warehouse=cfg["warehouse"],
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        )

    results = []
    for fv_spec in oft_fvs:
        fv_name = fv_spec["name"]
        version = fv_spec["version"]
        entity_key = fv_spec["entity_key"]
        strategy = fv_spec.get("strategy", "timestamp")

        entry = {"FEATURE_VIEW": fv_name, "MEASURED_AT": datetime.now(timezone.utc)}

        fqn = f'{db}.{fs_schema}."{fv_name}${version}"'

        # DT ROW_TIMESTAMP — authoritative last-refresh indicator
        try:
            dt_row = session.sql(f"""
                SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS DT_LAST_COMMIT
                FROM {fqn}
            """).collect()[0]
            entry["DT_LAST_COMMIT"] = dt_row["DT_LAST_COMMIT"]
        except Exception as e:
            entry["DT_LAST_COMMIT"] = None
            entry["DT_ERROR"] = str(e)

        if strategy == "max_key":
            # Get latest key from DT, then check OFT
            try:
                mk_row = session.sql(f"""
                    SELECT MAX({entity_key}) AS MAX_KEY FROM {fqn}
                """).collect()[0]
                dt_max_key = mk_row["MAX_KEY"]
                entry["DT_MAX_KEY"] = dt_max_key
            except Exception as e:
                dt_max_key = None
                entry["DT_MAX_KEY_ERROR"] = str(e)

            if dt_max_key:
                try:
                    fv_obj = fs.get_feature_view(fv_name, version)
                    oft_result = fs.read_feature_view(
                        fv_obj, keys=[[dt_max_key]], store_type="online",
                    ).collect()
                    entry["OFT_SYNCED"] = bool(oft_result and len(oft_result) > 0)
                except Exception as e:
                    entry["OFT_SYNCED"] = False
                    entry["OFT_ERROR"] = str(e)

        elif strategy == "timestamp":
            ts_col = fv_spec["ts_col"]
            sample_keys = fv_spec.get("sample_keys", [["usr_00000001"]])
            try:
                fv_obj = fs.get_feature_view(fv_name, version)
                oft_result = fs.read_feature_view(
                    fv_obj, keys=sample_keys, store_type="online",
                ).collect()
                if oft_result:
                    oft_ts = oft_result[0].as_dict().get(ts_col)
                    entry["OFT_UPDATED_TS"] = oft_ts
                    now = datetime.now(timezone.utc)
                    if oft_ts:
                        oft_utc = (oft_ts.astimezone(timezone.utc)
                                   if hasattr(oft_ts, "astimezone") else oft_ts)
                        entry["OFT_DATA_AGE_SECONDS"] = round(
                            (now - oft_utc).total_seconds(), 1
                        )
                    if entry.get("DT_LAST_COMMIT") and oft_ts:
                        dt_utc = entry["DT_LAST_COMMIT"]
                        if hasattr(dt_utc, "astimezone"):
                            dt_utc = dt_utc.astimezone(timezone.utc)
                        entry["DT_TO_OFT_DELTA_SECONDS"] = round(
                            (dt_utc - oft_utc).total_seconds(), 1
                        )
                    entry["OFT_SYNCED"] = True
                else:
                    entry["OFT_UPDATED_TS"] = None
                    entry["OFT_SYNCED"] = False
            except Exception as e:
                entry["OFT_ERROR"] = str(e)

        results.append(entry)

    return results


def measure_end_to_end(session, env: str = "DEV",
                       fs=None,
                       poll_interval: int = 5,
                       max_wait_dt: int = 120,
                       max_wait_oft: int = 120) -> dict:
    """Run one full end-to-end latency measurement cycle.

    Sequence:
      1. Snapshot current OFT state (UPDATED_TS for recency, max key for session)
      2. Generate one batch of incremental data
      3. Record source table ROW_TIMESTAMP
      4. Trigger DT refresh and poll ROW_TIMESTAMP until committed
      5. Poll OFTs until they reflect the new data
      6. Return per-stage latencies

    Both ``SESSION_BEHAVIOR_FEATURES`` and ``USER_RECENCY_RAW`` are
    INCREMENTAL DTs (no ``CURRENT_TIMESTAMP()``).  OFT sync is detected
    by checking whether the newest entity key from the DT appears in
    the OFT.

    Returns a dict with T0-T3 timestamps and per-stage durations.
    """
    import time
    from datetime import timezone
    from .generator import generate_batch

    cfg = get_config(env)
    db = cfg["database"]
    fs_schema = cfg["fs_schema"]
    src = cfg["source_schema"]

    if fs is None:
        from snowflake.ml.feature_store import FeatureStore, CreationMode
        fs = FeatureStore(
            session=session, database=db, name=fs_schema,
            default_warehouse=cfg["warehouse"],
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        )

    fv_urf = fs.get_feature_view("USER_RECENCY_RAW", "V01")
    fv_sbf = fs.get_feature_view("SESSION_BEHAVIOR_FEATURES", "V01")

    # T0: Generate batch
    t0 = datetime.now(timezone.utc)
    batch = generate_batch(session, env)

    # T1: Source commit
    t1_row = session.sql(f"""
        SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS TS
        FROM {db}.{src}.SESSIONS
    """).collect()[0]
    t1 = t1_row["TS"]
    if hasattr(t1, "astimezone"):
        t1 = t1.astimezone(timezone.utc)

    # T2: Trigger DT refresh and poll ROW_TIMESTAMP
    current_role = session.get_current_role().strip('"')
    sbf_max_key = None
    urf_max_key = None
    try:
        from .config import ROLES
        session.sql(f"USE ROLE {ROLES['dev']}").collect()
        session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

        for dt_name in ["USER_RECENCY_RAW$V01", "SESSION_BEHAVIOR_FEATURES$V01"]:
            session.sql(
                f'ALTER DYNAMIC TABLE {db}.{fs_schema}."{dt_name}" REFRESH'
            ).collect()

        t2 = None
        for _ in range(max_wait_dt // poll_interval):
            time.sleep(poll_interval)
            row = session.sql(f"""
                SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS TS
                FROM {db}.{fs_schema}."USER_RECENCY_RAW$V01"
            """).collect()[0]
            ts = row["TS"]
            if ts:
                ts_utc = ts.astimezone(timezone.utc) if hasattr(ts, "astimezone") else ts
                if ts_utc > t0:
                    t2 = ts_utc
                    break

        # Grab the max keys from the refreshed DTs
        sbf_max_key = session.sql(f"""
            SELECT MAX(SESSION_ID) AS MK
            FROM {db}.{fs_schema}."SESSION_BEHAVIOR_FEATURES$V01"
        """).collect()[0]["MK"]

        urf_max_key = session.sql(f"""
            SELECT MAX(USER_ID) AS MK
            FROM {db}.{fs_schema}."USER_RECENCY_RAW$V01"
        """).collect()[0]["MK"]
    finally:
        session.sql(f"USE ROLE {current_role}").collect()
        session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

    # T3a: Poll OFT for USER_RECENCY_RAW (latest key presence)
    t3 = None
    if urf_max_key:
        for _ in range(max_wait_oft // poll_interval):
            time.sleep(poll_interval)
            try:
                rows = fs.read_feature_view(
                    fv_urf, keys=[[urf_max_key]], store_type="online",
                ).collect()
                if rows and len(rows) > 0:
                    t3 = datetime.now(timezone.utc)
                    break
            except Exception:
                pass

    # T3b: Poll OFT for SESSION_BEHAVIOR_FEATURES (latest key presence)
    t3_sbf = None
    if sbf_max_key:
        for _ in range(max_wait_oft // poll_interval):
            time.sleep(poll_interval)
            try:
                rows = fs.read_feature_view(
                    fv_sbf, keys=[[sbf_max_key]], store_type="online",
                ).collect()
                if rows and len(rows) > 0:
                    t3_sbf = datetime.now(timezone.utc)
                    break
            except Exception:
                pass

    result = {
        "batch": batch,
        "T0_generate": t0,
        "T1_source_commit": t1,
        "T2_dt_commit": t2,
        "T3_oft_visible_urf": t3,
        "T3_oft_visible_sbf": t3_sbf,
        "sbf_max_key": sbf_max_key,
    }

    if t1:
        result["ingest_seconds"] = round((t1 - t0).total_seconds(), 1)
    if t2 and t1:
        result["dt_refresh_seconds"] = round((t2 - t1).total_seconds(), 1)
    if t3 and t2:
        result["oft_sync_urf_seconds"] = round((t3 - t2).total_seconds(), 1)
    if t3_sbf and t2:
        result["oft_sync_sbf_seconds"] = round((t3_sbf - t2).total_seconds(), 1)
    if t3 and t0:
        result["total_e2e_urf_seconds"] = round((t3 - t0).total_seconds(), 1)
    if t3_sbf and t0:
        result["total_e2e_sbf_seconds"] = round((t3_sbf - t0).total_seconds(), 1)

    return result


# ---------------------------------------------------------------------------
# DT refresh history (from INFORMATION_SCHEMA)
# ---------------------------------------------------------------------------

def get_dt_refresh_history(
    session, env: str = "DEV",
    last_n_minutes: int = 10,
    dt_names: list[str] | None = None,
) -> list[dict]:
    """Return recent DT refresh records with timing breakdown.

    Queries INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY()
    for each DT, returning refresh times, duration, row stats,
    and the queued/compilation/execution time split from
    the STATISTICS column.
    """
    import json as _json

    cfg = get_config(env)
    db = cfg["database"]
    fs = cfg["fs_schema"]
    all_dts = dt_names or (TIER1_DTS + TIER2_DTS + WIDE_DTS)

    results: list[dict] = []
    for dt in all_dts:
        fqn = f"{db}.{fs}.{dt}"
        try:
            rows = session.sql(f"""
                SELECT
                    NAME,
                    STATE,
                    REFRESH_ACTION,
                    REFRESH_TRIGGER,
                    REFRESH_START_TIME,
                    REFRESH_END_TIME,
                    DATA_TIMESTAMP,
                    TARGET_LAG_SEC,
                    STATISTICS
                FROM TABLE(
                    INFORMATION_SCHEMA
                    .DYNAMIC_TABLE_REFRESH_HISTORY(
                        NAME => '{fqn}',
                        DATA_TIMESTAMP_START
                            => DATEADD(
                                'MINUTE',
                                -{last_n_minutes},
                                CURRENT_TIMESTAMP()
                            )
                    )
                )
                WHERE STATE = 'SUCCEEDED'
                ORDER BY REFRESH_END_TIME DESC
            """).collect()
        except Exception as e:
            results.append({
                "DT": dt, "ERROR": str(e),
            })
            continue

        for r in rows:
            d = r.as_dict()
            stats_raw = d.get("STATISTICS")
            stats = {}
            if stats_raw:
                if isinstance(stats_raw, str):
                    try:
                        stats = _json.loads(stats_raw)
                    except Exception:
                        stats = {}
                elif isinstance(stats_raw, dict):
                    stats = stats_raw

            start = d.get("REFRESH_START_TIME")
            end = d.get("REFRESH_END_TIME")
            dur_s = None
            if start and end:
                dur_s = round(
                    (end - start).total_seconds(), 2
                )

            results.append({
                "DT": dt,
                "STATE": d.get("STATE"),
                "REFRESH_ACTION": d.get("REFRESH_ACTION"),
                "REFRESH_TRIGGER": d.get("REFRESH_TRIGGER"),
                "REFRESH_START_TIME": start,
                "REFRESH_END_TIME": end,
                "DURATION_SECONDS": dur_s,
                "TARGET_LAG_SEC": d.get("TARGET_LAG_SEC"),
                "DATA_TIMESTAMP": d.get("DATA_TIMESTAMP"),
                "ROWS_INSERTED": stats.get(
                    "numInsertedRows"),
                "ROWS_DELETED": stats.get(
                    "numDeletedRows"),
                "ROWS_COPIED": stats.get(
                    "numCopiedRows"),
                "QUEUED_MS": stats.get("queuedTimeMs"),
                "COMPILATION_MS": stats.get(
                    "compilationTimeMs"),
                "EXECUTION_MS": stats.get(
                    "executionTimeMs"),
            })

    return results


# ---------------------------------------------------------------------------
# Row counts
# ---------------------------------------------------------------------------

def get_row_counts(
    session, env: str = "DEV",
) -> dict:
    """Return row counts for source tables and DT Feature Views.

    Returns::

        {
            "source": {"SESSIONS": 2600, "EVENTS": 21989, ...},
            "dt": {"SESSION_BEHAVIOR_FEATURES$V01": 1535, ...},
        }
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    fs = cfg["fs_schema"]

    source_counts: dict[str, int | None] = {}
    for t in SOURCE_TABLES:
        try:
            r = session.sql(
                f"SELECT COUNT(*) AS C FROM {db}.{src}.{t}"
            ).collect()[0]
            source_counts[t] = r["C"]
        except Exception:
            source_counts[t] = None

    dt_counts: dict[str, int | None] = {}
    for dt in TIER1_DTS + TIER2_DTS + WIDE_DTS:
        try:
            r = session.sql(
                f'SELECT COUNT(*) AS C '
                f'FROM {db}.{fs}."{dt}"'
            ).collect()[0]
            dt_counts[dt] = r["C"]
        except Exception:
            dt_counts[dt] = None

    return {"source": source_counts, "dt": dt_counts}


# ---------------------------------------------------------------------------
# End-to-end summary
# ---------------------------------------------------------------------------

def pipeline_summary(
    session, env: str = "DEV",
    refresh_history_minutes: int = 10,
    batch_history_count: int = 10,
) -> dict:
    """Produce a combined summary of pipeline health,
    latency, DT refresh history, batch stats, and row counts."""
    source = get_source_freshness(session, env)
    dts = get_dt_freshness(session, env)
    stages = measure_stage_latency(session, env)

    try:
        dt_refreshes = get_dt_refresh_history(
            session, env,
            last_n_minutes=refresh_history_minutes,
        )
    except Exception:
        dt_refreshes = []

    try:
        batches = get_batch_latency(
            session, env, last_n=batch_history_count,
        )
    except Exception:
        batches = []

    try:
        row_counts = get_row_counts(session, env)
    except Exception:
        row_counts = {"source": {}, "dt": {}}

    return {
        "measured_at": datetime.now().isoformat(),
        "source_freshness": source,
        "dt_freshness": dts,
        "stage_latency": stages,
        "dt_refresh_history": dt_refreshes,
        "batch_stats": batches,
        "row_counts": row_counts,
    }


# ---------------------------------------------------------------------------
# ROW_TIMESTAMP enablement
# ---------------------------------------------------------------------------

def enable_row_timestamp_on_sources(session, env: str = "DEV") -> list[str]:
    """Enable ROW_TIMESTAMP on the 4 source tables used in the pipeline.

    Uses ALTER TABLE ... SET ROW_TIMESTAMP = TRUE.
    Rows inserted before enablement will have NULL commit timestamps.
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    results = []
    for table in SOURCE_TABLES:
        try:
            session.sql(
                f"ALTER TABLE {db}.{src}.{table} SET ROW_TIMESTAMP = TRUE"
            ).collect()
            results.append(f"{table}: ROW_TIMESTAMP enabled")
        except Exception as e:
            if "already set" in str(e).lower() or "already enabled" in str(e).lower():
                results.append(f"{table}: ROW_TIMESTAMP already enabled")
            else:
                results.append(f"{table}: {e}")
    return results


def enable_row_timestamp_on_dts(session, env: str = "DEV") -> list[str]:
    """Enable ROW_TIMESTAMP on all DT-backed Feature Views.

    Uses ALTER DYNAMIC TABLE ... SET ROW_TIMESTAMP = TRUE.
    """
    cfg = get_config(env)
    db = cfg["database"]
    fs = cfg["fs_schema"]
    all_dts = TIER1_DTS + TIER2_DTS + WIDE_DTS
    results = []
    for dt in all_dts:
        try:
            session.sql(
                f'ALTER DYNAMIC TABLE {db}.{fs}."{dt}" SET ROW_TIMESTAMP = TRUE'
            ).collect()
            results.append(f"{dt}: ROW_TIMESTAMP enabled")
        except Exception as e:
            if "already set" in str(e).lower() or "already enabled" in str(e).lower():
                results.append(f"{dt}: ROW_TIMESTAMP already enabled")
            else:
                results.append(f"{dt}: {e}")

    # Verify by querying METADATA$ROW_LAST_COMMIT_TIME
    for dt in all_dts:
        try:
            row = session.sql(f"""
                SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS TS
                FROM {db}.{fs}."{dt}"
            """).collect()[0]
            results.append(f"{dt}: verified (latest={row['TS']})")
        except Exception as e:
            results.append(f"{dt}: verify failed - {e}")
    return results

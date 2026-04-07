"""
Test script for the incremental pipeline & end-to-end latency measurement.

Run from the notebooks/ directory:
    python _test_pipeline.py

Sequence:
  1. Deploy admin tables (GENERATION_CONFIG/STATE/LOG)
  2. Seed state from existing bulk data
  3. Enable ROW_TIMESTAMP on source tables
  4. Verify ROW_TIMESTAMP on DT Feature Views
  5. Deploy stored procedure and task (SUSPENDED)
  6. Run 3 batches manually via local generate_batch()
  7. Vary scale live, run 2 more batches
  8. Expand OFTs to DT-backed FVs
  9. Measure latency at every stage
 10. Suspend task, report summary
"""

import sys
import time

sys.path.insert(0, ".")

from feature_definitions.config import get_config, get_session, ROLES

# ── 1. Connect ──────────────────────────────────────────────────────────
session = get_session(role=ROLES["admin"])
cfg = get_config("DEV")
print(f"Connected: role={session.get_current_role()}, db={cfg['database']}")
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
session.sql(f"USE DATABASE {cfg['database']}").collect()

# ── 2. Deploy admin tables ──────────────────────────────────────────────
print("\n=== Deploying admin tables ===")
from feature_definitions.generator import (
    create_admin_tables,
    seed_state_from_existing_data,
    generate_batch,
    deploy_stored_procedure,
    deploy_task,
    set_scale,
)

create_admin_tables(session, "DEV")
print("  GENERATION_CONFIG, GENERATION_STATE, GENERATION_LOG created")

# ── 3. Seed state from existing bulk load ───────────────────────────────
print("\n=== Seeding state from existing data ===")
counters = seed_state_from_existing_data(session, "DEV")
for k, v in counters.items():
    print(f"  {k}: {v}")

# ── 4. Enable ROW_TIMESTAMP on source tables (needs ACCOUNTADMIN) ───────
print("\n=== Enabling ROW_TIMESTAMP on source tables ===")
from feature_definitions.latency import (
    enable_row_timestamp_on_sources,
    enable_row_timestamp_on_dts,
    get_source_freshness,
    get_dt_freshness,
    measure_stage_latency,
    get_oft_freshness,
    get_batch_latency,
    pipeline_summary,
)

session.sql("USE ROLE ACCOUNTADMIN").collect()
results = enable_row_timestamp_on_sources(session, "DEV")
for r in results:
    print(f"  {r}")

# ── 5. Enable ROW_TIMESTAMP on DT Feature Views ────────────────────────
# DTs are owned by FS_DEV_ROLE (which created them), so switch role
print("\n=== Enabling ROW_TIMESTAMP on DT Feature Views ===")
session.sql(f"USE ROLE {ROLES['dev']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
dt_results = enable_row_timestamp_on_dts(session, "DEV")
for r in dt_results:
    print(f"  {r}")

# Switch back to admin for the rest
session.sql(f"USE ROLE {ROLES['admin']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

# ── 6. Check source freshness before generating ────────────────────────
print("\n=== Source freshness (before new data) ===")
freshness = get_source_freshness(session, "DEV")
for f in freshness:
    if "ERROR" in f:
        print(f"  {f['TABLE']}: ERROR - {f['ERROR']}")
    else:
        print(f"  {f['TABLE']}: last_commit={f['LAST_COMMIT_TIME']}, age={f['AGE_SECONDS']}s")

# ── 7. Run 3 batches with default scale ────────────────────────────────
print("\n=== Running 3 batches (default scale: 50 sessions, 5 orders) ===")
for i in range(3):
    result = generate_batch(session, "DEV")
    print(f"  Batch {i+1}: {result}")
    if i < 2:
        time.sleep(2)

# ── 8. Check freshness after 3 batches ─────────────────────────────────
print("\n=== Source freshness (after 3 batches) ===")
freshness = get_source_freshness(session, "DEV")
for f in freshness:
    if "ERROR" in f:
        print(f"  {f['TABLE']}: ERROR - {f['ERROR']}")
    else:
        print(f"  {f['TABLE']}: last_commit={f['LAST_COMMIT_TIME']}, age={f['AGE_SECONDS']}s")

# ── 9. Vary scale live and run 2 more batches ──────────────────────────
print("\n=== Adjusting scale: 200 sessions, 20 orders ===")
set_scale(session, "DEV", sessions_per_batch=200, orders_per_batch=20)

# Verify config change
row = session.sql(f"""
    SELECT SESSIONS_PER_BATCH, ORDERS_PER_BATCH
    FROM {cfg['database']}.{cfg['admin_schema']}.GENERATION_CONFIG
    WHERE ID = 1
""").collect()[0]
print(f"  Config now: sessions={row['SESSIONS_PER_BATCH']}, orders={row['ORDERS_PER_BATCH']}")

print("\n=== Running 2 batches at increased scale ===")
for i in range(2):
    result = generate_batch(session, "DEV")
    print(f"  Batch {i+4}: {result}")
    if i < 1:
        time.sleep(2)

# Reset scale back to default
set_scale(session, "DEV", sessions_per_batch=50, orders_per_batch=5)
print("  Scale reset to default (50/5)")

# ── 10. Trigger DT refreshes and wait ───────────────────────────────────
print("\n=== Triggering manual DT refresh ===")
from feature_definitions.latency import TIER1_DTS, TIER2_DTS, WIDE_DTS

session.sql(f"USE ROLE {ROLES['dev']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
for dt in TIER1_DTS + TIER2_DTS:
    try:
        session.sql(
            f'ALTER DYNAMIC TABLE {cfg["database"]}.{cfg["fs_schema"]}."{dt}" REFRESH'
        ).collect()
        print(f"  Refreshed: {dt}")
    except Exception as e:
        print(f"  Refresh failed {dt}: {e}")

session.sql(f"USE ROLE {ROLES['admin']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

print("  Waiting 60s for refreshes to complete...")
time.sleep(60)

print("\n=== DT Feature View freshness ===")
# Read DTs using dev role since that owns them
session.sql(f"USE ROLE {ROLES['dev']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
dt_fresh = get_dt_freshness(session, "DEV")
for f in dt_fresh:
    if "ERROR" in f:
        print(f"  {f['TABLE']}: ERROR - {f.get('ERROR', 'unknown')}")
    elif f['LAST_COMMIT_TIME'] is None:
        print(f"  {f['TABLE']}: no ROW_TIMESTAMP data yet (pre-existing rows are NULL)")
    else:
        print(f"  {f['TABLE']}: last_commit={f['LAST_COMMIT_TIME']}, age={f['AGE_SECONDS']}s")

session.sql(f"USE ROLE {ROLES['admin']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

# ── 11. Measure stage latency ──────────────────────────────────────────
print("\n=== Stage latency ===")
stages = measure_stage_latency(session, "DEV")
for s in stages:
    if "ERROR" in s:
        print(f"  {s['STAGE']}: {s['FROM_TABLE']} -> {s['TO_TABLE']}: ERROR - {s['ERROR']}")
    elif s.get('LATENCY_SECONDS') is None:
        print(f"  {s['STAGE']}: {s['FROM_TABLE']} -> {s['TO_TABLE']}: "
              f"from={s.get('FROM_COMMIT')}, to={s.get('TO_COMMIT')} (waiting for DT refresh)")
    else:
        print(f"  {s['STAGE']}: {s['FROM_TABLE']} -> {s['TO_TABLE']}: {s['LATENCY_SECONDS']}s")

# ── 12. Batch-level latency ────────────────────────────────────────────
print("\n=== Batch-level latency (last 10) ===")
batch_lat = get_batch_latency(session, "DEV")
for b in batch_lat:
    print(f"  Batch {b.get('LOG_ID', '?')}: "
          f"duration={b.get('DURATION_MS', '?')}ms, "
          f"ingest_latency={b.get('INGEST_LATENCY_SECONDS', '?')}s")

# ── 13. Expand OFTs to DT-backed FVs ───────────────────────────────────
print("\n=== Creating OFTs for DT-backed Feature Views ===")
from snowflake.ml.feature_store import FeatureStore, CreationMode
from snowflake.ml.feature_store.feature_view import OnlineConfig

dev_fs = FeatureStore(
    session=session,
    database=cfg["database"],
    name=cfg["fs_schema"],
    default_warehouse=cfg["warehouse"],
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)

for fv_name in ["SESSION_BEHAVIOR_FEATURES", "USER_RECENCY_RAW"]:
    try:
        fv = dev_fs.update_feature_view(
            fv_name, "V01",
            online_config=OnlineConfig(enable=True),
        )
        print(f"  OFT enabled: {fv_name} (online={fv.online})")
    except Exception as e:
        if "already" in str(e).lower():
            print(f"  OFT already enabled: {fv_name}")
        else:
            print(f"  OFT creation failed for {fv_name}: {e}")

# ── 14. Test OFT reads ─────────────────────────────────────────────────
print("\n=== Testing OFT reads (waiting 30s for OFT sync) ===")
time.sleep(30)
for fv_name, key_vals in [
    ("SESSION_BEHAVIOR_FEATURES",
     [["sess_00000001"], ["sess_00000010"]]),
    ("USER_RECENCY_RAW",
     [["usr_00000001"], ["usr_00000010"]]),
]:
    try:
        fv = dev_fs.get_feature_view(fv_name, "V01")
        result = dev_fs.read_feature_view(fv, keys=key_vals, store_type="online")
        print(f"\n  {fv_name} OFT read:")
        result.show()
    except Exception as e:
        print(f"  {fv_name} OFT read failed: {e}")
        print("  (OFT may still be initialising — try again in a few minutes)")

# ── 15. OFT freshness measurement ──────────────────────────────────────
print("\n=== OFT freshness ===")
session.sql(f"USE ROLE {ROLES['dev']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
oft_fresh = get_oft_freshness(session, "DEV", fs=dev_fs)
for f in oft_fresh:
    fv = f["FEATURE_VIEW"]
    dt_commit = f.get("DT_LAST_COMMIT")
    synced = f.get("OFT_SYNCED", "?")
    extra = ""
    if f.get("DT_MAX_KEY"):
        extra = f", max_key={f['DT_MAX_KEY']}"
    if f.get("OFT_UPDATED_TS"):
        extra = f", OFT_UPDATED_TS={f['OFT_UPDATED_TS']}"
    if f.get("OFT_ERROR"):
        extra += f", ERROR={f['OFT_ERROR']}"
    print(f"  {fv}: DT_LAST_COMMIT={dt_commit}, synced={synced}{extra}")
session.sql(f"USE ROLE {ROLES['admin']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

# ── 16. OFT Serving Benchmark (concurrent query workload) ──────────────
# Run a short 30s burst of concurrent OFT queries on the dedicated serving
# warehouse whilst the ingestion pipeline state is still warm.
print("\n=== OFT Serving Benchmark ===")
from feature_definitions.benchmark import (
    create_serving_warehouse,
    run_benchmark,
    BenchmarkConfig,
    drop_serving_warehouse,
)

# Create (or ensure) the serving warehouse as ACCOUNTADMIN
session.sql("USE ROLE ACCOUNTADMIN").collect()
create_serving_warehouse(session, "DEV", max_clusters=1)
session.sql(f"USE ROLE {ROLES['admin']}").collect()
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

bench_cfg = BenchmarkConfig(
    duration_seconds=30,
    threads_per_cluster=8,
    max_clusters=1,
)
bench_result = run_benchmark(session, "DEV", bench_cfg)
bench_result.print_summary()

# ── 17. Deploy stored procedure and task ────────────────────────────────
print("\n=== Deploying stored procedure ===")
deploy_stored_procedure(session, "DEV")
print("  GENERATE_INCREMENTAL_BATCH procedure created")

print("\n=== Deploying task (SUSPENDED) ===")
deploy_task(session, "DEV")
print("  INCREMENTAL_DATA_TASK created (suspended)")

# ── 18. Pipeline summary ───────────────────────────────────────────────
print("\n=== Pipeline Summary ===")
summary = pipeline_summary(session, "DEV")
print(f"  Measured at: {summary['measured_at']}")
print(f"  Source tables: {len(summary['source_freshness'])}")
print(f"  DT Feature Views: {len(summary['dt_freshness'])}")
print(f"  Stage latencies: {len(summary['stage_latency'])}")

# ── 19. Verify generation log ──────────────────────────────────────────
print("\n=== Generation Log ===")
rows = session.sql(f"""
    SELECT LOG_ID, BATCH_TS, SESSIONS_GENERATED, EVENTS_GENERATED,
           ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS
    FROM {cfg['database']}.{cfg['admin_schema']}.GENERATION_LOG
    ORDER BY LOG_ID
""").collect()
for r in rows:
    d = r.as_dict()
    print(f"  Batch {d['LOG_ID']}: {d['STATUS']} - "
          f"sessions={d['SESSIONS_GENERATED']}, events={d['EVENTS_GENERATED']}, "
          f"orders={d['ORDERS_GENERATED']}, items={d['ORDER_ITEMS_GENERATED']}, "
          f"duration={d['DURATION_MS']}ms")

print("\n=== All pipeline tests complete ===")

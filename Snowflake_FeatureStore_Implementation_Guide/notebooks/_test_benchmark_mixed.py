"""
Mixed-workload benchmark runner — extended E2E test with ML workloads.

Adds dataset generation, batch inference, and a continuous inference DT
alongside the existing ingestion + OFT serving benchmark.

Two modes:
  --validate   Quick 4x5min run to confirm everything works (default)
  --team       Full 4x30min run for the SnowCAT team session (~2 hours)

Prerequisites:
  - Run _test_nb00_setup.py (with FS_DATA_SCALE=1.0 for team run)
  - Run _test_nb01_features.py (register FVs, enable OFTs)
  - Run _test_nb02_ml.py (train + register CONVERSION_PREDICTION model)
  - Create FS_ML_WH adaptive warehouse:
      CREATE WAREHOUSE IF NOT EXISTS FS_ML_WH
        WAREHOUSE_TYPE = 'ADAPTIVE'
        MAX_QUERY_PERFORMANCE_LEVEL = 'XSMALL'
        QUERY_THROUGHPUT_MULTIPLIER = 10
        COMMENT = 'ML workloads — dataset gen, batch inference, inference DT';

Usage:
    python _test_benchmark_mixed.py              # validate mode (20 min)
    python _test_benchmark_mixed.py --validate   # same as above
    python _test_benchmark_mixed.py --team       # full team run (2 hours)
"""

import sys
import argparse

sys.path.insert(0, ".")

from feature_definitions.config import get_session
from feature_definitions.orchestrator import (
    ScaleStep,
    run_e2e_test,
)


# ---------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------

VALIDATE_STEPS = [
    ScaleStep(
        name="baseline",
        duration_minutes=5,
        sessions_per_batch=50,
        orders_per_batch=5,
        serving_clusters=1,
        threads_per_cluster=8,
        refresh_clusters=1,
        dt_target_lag="1 minute",
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=3,
        enable_batch_inference=True,
        batch_inference_interval_minutes=3,
        enable_inference_dt=True,
    ),
    ScaleStep(
        name="2x_ingest",
        duration_minutes=5,
        sessions_per_batch=200,
        orders_per_batch=20,
        serving_clusters=1,
        threads_per_cluster=8,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=3,
        enable_batch_inference=True,
        batch_inference_interval_minutes=3,
    ),
    ScaleStep(
        name="scale_serving",
        duration_minutes=5,
        sessions_per_batch=200,
        orders_per_batch=20,
        serving_clusters=2,
        threads_per_cluster=8,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=3,
        enable_batch_inference=True,
        batch_inference_interval_minutes=3,
    ),
    ScaleStep(
        name="peak",
        duration_minutes=5,
        sessions_per_batch=500,
        orders_per_batch=50,
        serving_clusters=4,
        threads_per_cluster=8,
        refresh_clusters=4,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=2,
        enable_batch_inference=True,
        batch_inference_interval_minutes=2,
    ),
]

TEAM_STEPS = [
    ScaleStep(
        name="baseline",
        duration_minutes=30,
        sessions_per_batch=200,
        orders_per_batch=20,
        serving_clusters=1,
        threads_per_cluster=8,
        refresh_clusters=1,
        dt_target_lag="1 minute",
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=5,
        enable_batch_inference=True,
        batch_inference_interval_minutes=5,
        enable_inference_dt=True,
    ),
    ScaleStep(
        name="ramp_ingest",
        duration_minutes=30,
        sessions_per_batch=500,
        orders_per_batch=50,
        serving_clusters=1,
        threads_per_cluster=8,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=5,
        enable_batch_inference=True,
        batch_inference_interval_minutes=5,
    ),
    ScaleStep(
        name="scale_serving",
        duration_minutes=30,
        sessions_per_batch=500,
        orders_per_batch=50,
        serving_clusters=2,
        threads_per_cluster=8,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=5,
        enable_batch_inference=True,
        batch_inference_interval_minutes=5,
    ),
    ScaleStep(
        name="peak",
        duration_minutes=30,
        sessions_per_batch=1000,
        orders_per_batch=100,
        serving_clusters=4,
        threads_per_cluster=8,
        refresh_clusters=4,
        enable_dataset_gen=True,
        dataset_gen_interval_minutes=3,
        enable_batch_inference=True,
        batch_inference_interval_minutes=3,
    ),
]


# ---------------------------------------------------------------
# Warehouse setup
# ---------------------------------------------------------------

WAREHOUSE_SETUP_SQL = """
CREATE WAREHOUSE IF NOT EXISTS FS_ML_WH
    WAREHOUSE_TYPE = 'ADAPTIVE'
    MAX_QUERY_PERFORMANCE_LEVEL = 'XSMALL'
    QUERY_THROUGHPUT_MULTIPLIER = 10
    COMMENT = 'ML workloads — dataset gen, batch inference, inference DT';
"""

INFERENCE_TABLE_SETUP_SQL = """
CREATE TABLE IF NOT EXISTS {db}.{inf}.BENCHMARK_CHURN_SCORES (
    USER_ID VARCHAR,
    CHURN_PROB FLOAT,
    SCORED_AT VARCHAR,
    CYCLE INTEGER
);
"""


def setup_prerequisites(session, env="DEV"):
    """Ensure FS_ML_WH and inference tables exist."""
    from feature_definitions.config import get_config

    print("Setting up prerequisites...")

    try:
        session.sql(WAREHOUSE_SETUP_SQL).collect()
        print("  FS_ML_WH: OK")
    except Exception as e:
        print(f"  FS_ML_WH: {e} (may already exist)")

    cfg = get_config(env)
    db = cfg["database"]
    inf = cfg["inference_schema"]

    session.sql(
        f"CREATE SCHEMA IF NOT EXISTS {db}.{inf}"
    ).collect()

    session.sql(
        INFERENCE_TABLE_SETUP_SQL.format(db=db, inf=inf)
    ).collect()
    print("  Inference tables: OK")

    try:
        session.sql(
            "GRANT USAGE ON WAREHOUSE FS_ML_WH "
            "TO ROLE FS_DEV_ROLE"
        ).collect()
        session.sql(
            "GRANT OPERATE ON WAREHOUSE FS_ML_WH "
            "TO ROLE FS_DEV_ROLE"
        ).collect()
        print("  FS_ML_WH grants: OK")
    except Exception as e:
        print(f"  FS_ML_WH grants: {e}")


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mixed-workload benchmark"
    )
    parser.add_argument(
        "--team", action="store_true",
        help="Full 2-hour team run (4x30 min)",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Quick validation run (4x5 min, default)",
    )
    args = parser.parse_args()

    mode = "team" if args.team else "validate"
    steps = TEAM_STEPS if mode == "team" else VALIDATE_STEPS

    total_min = sum(s.duration_minutes for s in steps)
    print(f"\nMode: {mode}")
    print(f"Steps: {len(steps)}")
    print(f"Planned duration: {total_min} minutes\n")

    session = get_session(role="ACCOUNTADMIN")
    print(
        f"Connected as {session.get_current_user()} "
        f"/ {session.get_current_role()}"
    )

    setup_prerequisites(session)

    results = run_e2e_test(
        session,
        steps,
        env="DEV",
        warmup_seconds=10,
    )

    print(
        f"\nCompleted {results['overall']['steps_completed']}"
        f" steps, "
        f"{results['overall']['total_queries']:,} queries"
    )

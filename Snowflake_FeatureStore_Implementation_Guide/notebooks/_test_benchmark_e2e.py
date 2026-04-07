"""
End-to-end benchmark orchestrator runner.

Run from the notebooks/ directory:
    python _test_benchmark_e2e.py

Requires ACCOUNTADMIN (for warehouse ALTERs and task control).
The ingestion task, DTs, and OFTs must already exist (run
_test_nb00_setup.py through _test_nb04_pipeline.py first).
"""

import sys
sys.path.insert(0, ".")

from feature_definitions.config import get_session
from feature_definitions.orchestrator import (
    ScaleStep,
    run_e2e_test,
)

# ---------------------------------------------------------------
# Connect
# ---------------------------------------------------------------
session = get_session(role="ACCOUNTADMIN")
print(
    f"Connected as {session.get_current_user()} "
    f"/ {session.get_current_role()}"
)

# ---------------------------------------------------------------
# Define scale steps
# ---------------------------------------------------------------
STEPS = [
    ScaleStep(
        name="baseline",
        duration_minutes=5,
        sessions_per_batch=50,
        orders_per_batch=5,
        serving_clusters=1,
        threads_per_cluster=8,
        refresh_clusters=1,
        dt_target_lag="1 minute",
    ),
    ScaleStep(
        name="2x_ingest",
        duration_minutes=5,
        sessions_per_batch=200,
        orders_per_batch=20,
        serving_clusters=1,
        threads_per_cluster=8,
    ),
    ScaleStep(
        name="scale_serving",
        duration_minutes=5,
        sessions_per_batch=200,
        orders_per_batch=20,
        serving_clusters=2,
        threads_per_cluster=8,
    ),
    ScaleStep(
        name="peak",
        duration_minutes=5,
        sessions_per_batch=500,
        orders_per_batch=50,
        serving_clusters=4,
        threads_per_cluster=8,
        refresh_clusters=4,
    ),
]

# ---------------------------------------------------------------
# Run
# ---------------------------------------------------------------
if __name__ == "__main__":
    results = run_e2e_test(
        session,
        STEPS,
        env="DEV",
        warmup_seconds=10,
    )
    print(
        f"\nCompleted {results['overall']['steps_completed']}"
        f" steps, "
        f"{results['overall']['total_queries']:,} queries"
    )

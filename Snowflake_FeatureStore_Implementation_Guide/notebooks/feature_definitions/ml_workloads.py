"""
ML workloads for mixed-workload benchmarking.

Three workloads that run alongside the existing ingestion + OFT serving
benchmark to simulate a realistic production Feature Store environment:

  A. **Dataset Generation** — periodic ``fs.generate_dataset()`` calls that
     materialise versioned training datasets.
  B. **Batch Inference** — periodic feature assembly + model scoring for all
     active users, writing results to an inference table.
  C. **Inference DT** — a continuously-refreshing Dynamic Table that joins
     multiple feature views to produce near-real-time churn risk scores.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .config import get_config


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class WorkloadCycleResult:
    """One execution cycle of a periodic workload."""
    workload: str
    cycle: int
    started_at: str
    duration_seconds: float
    rows: int = 0
    version: str = ""
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class WorkloadSummary:
    """Aggregated results for a workload across an entire step."""
    workload: str
    cycles_completed: int = 0
    cycles_failed: int = 0
    total_rows: int = 0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    versions_created: list[str] = field(default_factory=list)
    cycle_results: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# A. Dataset Generation
# ---------------------------------------------------------------------------

def run_dataset_generation(
    session,
    env: str = "DEV",
    *,
    dataset_name: str = "BENCHMARK_TRAINING",
    version_prefix: str = "",
    cycle: int = 1,
) -> WorkloadCycleResult:
    """Generate a versioned training dataset via feature assembly + materialisation.

    Uses ``generate_training_set()`` to assemble features (avoiding the
    multi-session UDF conflict in ``generate_dataset()``), then writes the
    result to a versioned table to simulate the full dataset-creation workload.
    """
    from snowflake.ml.feature_store import FeatureStore

    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    inf = cfg["inference_schema"]
    ml_wh = cfg.get("ml_warehouse", "FS_ML_WH")

    ts = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    ts_tag = datetime.now(timezone.utc).strftime(
        "%H%M%S"
    )
    pfx = version_prefix or f"R{ts_tag}"
    version = f"{pfx}_{cycle:03d}"

    try:
        session.sql(f"USE WAREHOUSE {ml_wh}").collect()

        spine_df = session.sql(f"""
            SELECT SESSION_ID, USER_ID,
                   SESSION_START_TS AS LABEL_TS,
                   IS_CONVERTED
            FROM {db}.{src}.SESSIONS
                TABLESAMPLE BERNOULLI (50)
            WHERE USER_ID IS NOT NULL
        """)

        fs = FeatureStore(
            session=session,
            database=cfg["database"],
            name=cfg["fs_schema"],
            default_warehouse=ml_wh,
        )

        fv_session = fs.get_feature_view("SESSION_BEHAVIOR_FEATURES", "V01")
        fv_profile = fs.get_feature_view("USER_PROFILE_FEATURES", "V01")
        fv_purchase = fs.get_feature_view("USER_PURCHASE_AGGREGATES", "V03")

        training_df = fs.generate_training_set(
            spine_df=spine_df,
            features=[fv_session, fv_profile, fv_purchase],
            spine_timestamp_col="LABEL_TS",
            join_method="cte",
        )

        table_name = (
            f"{db}.{inf}.{dataset_name}_{version}"
        )
        training_df.write.mode("overwrite").save_as_table(
            table_name
        )
        row_count = session.table(table_name).count()

        dur = time.time() - t0

        return WorkloadCycleResult(
            workload="dataset_generation",
            cycle=cycle,
            started_at=ts,
            duration_seconds=round(dur, 2),
            rows=row_count,
            version=version,
        )

    except Exception as e:
        return WorkloadCycleResult(
            workload="dataset_generation",
            cycle=cycle,
            started_at=ts,
            duration_seconds=round(time.time() - t0, 2),
            error=str(e),
        )


# ---------------------------------------------------------------------------
# B. Batch Inference
# ---------------------------------------------------------------------------

def run_batch_inference(
    session,
    env: str = "DEV",
    *,
    cycle: int = 1,
) -> WorkloadCycleResult:
    """Score recent sessions with the CONVERSION_PREDICTION model.

    Builds a session-level spine, assembles features from the same
    FVs the model was trained on, scores server-side via
    ``mv.run()``, and writes results to an inference table.
    """
    from snowflake.ml.feature_store import FeatureStore
    from snowflake.ml.registry import Registry

    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    inf = cfg["inference_schema"]
    ml_wh = cfg.get("ml_warehouse", "FS_ML_WH")

    ts = datetime.now(timezone.utc).isoformat()
    t0 = time.time()

    try:
        session.sql(f"USE WAREHOUSE {ml_wh}").collect()

        session.sql(f"""
            CREATE OR REPLACE TABLE
                {db}.{inf}.BENCHMARK_INF_SPINE AS
            SELECT
                SESSION_ID,
                USER_ID,
                SESSION_START_TS AS LABEL_TS
            FROM {db}.{src}.SESSIONS
                TABLESAMPLE BERNOULLI (50)
            WHERE USER_ID IS NOT NULL
        """).collect()

        spine_df = session.table(
            f"{db}.{inf}.BENCHMARK_INF_SPINE"
        )

        fs = FeatureStore(
            session=session,
            database=cfg["database"],
            name=cfg["fs_schema"],
            default_warehouse=ml_wh,
        )

        fv_session = fs.get_feature_view(
            "SESSION_BEHAVIOR_FEATURES", "V01"
        )
        fv_profile = fs.get_feature_view(
            "USER_PROFILE_FEATURES", "V01"
        )
        fv_purchase = fs.get_feature_view(
            "USER_PURCHASE_AGGREGATES", "V03"
        )
        fv_engage = fs.get_feature_view(
            "USER_SESSION_ENGAGEMENT", "V01"
        )

        inference_df = fs.generate_training_set(
            spine_df=spine_df,
            features=[
                fv_session, fv_profile,
                fv_purchase, fv_engage,
            ],
            spine_timestamp_col="LABEL_TS",
            join_method="cte",
        )

        registry = Registry(
            session=session,
            database_name=cfg["database"],
            schema_name=cfg["ml_datasets_schema"],
        )
        mv = registry.get_model(
            "CONVERSION_PREDICTION"
        ).version("V01")

        inference_df = inference_df.na.drop()

        scored_df = mv.run(
            inference_df,
            function_name="predict_proba",
        )

        from snowflake.snowpark import functions as F
        output_df = scored_df.select(
            F.col("USER_ID"),
            F.col('"output_feature_1"').alias(
                "CONVERSION_PROB"
            ),
            F.lit(ts).alias("SCORED_AT"),
            F.lit(cycle).alias("CYCLE"),
        )

        target = (
            f"{db}.{inf}.BENCHMARK_CHURN_SCORES"
        )
        output_df.write.mode("append").save_as_table(
            target
        )
        row_count = output_df.count()

        dur = time.time() - t0
        return WorkloadCycleResult(
            workload="batch_inference",
            cycle=cycle,
            started_at=ts,
            duration_seconds=round(dur, 2),
            rows=row_count,
            extra={
                "model": "CONVERSION_PREDICTION/V01"
            },
        )

    except Exception as e:
        return WorkloadCycleResult(
            workload="batch_inference",
            cycle=cycle,
            started_at=ts,
            duration_seconds=round(
                time.time() - t0, 2
            ),
            error=str(e),
        )


# ---------------------------------------------------------------------------
# C. Inference DT (setup only — runs on Snowflake side)
# ---------------------------------------------------------------------------

def ensure_inference_dt(
    session,
    env: str = "DEV",
) -> str:
    """Create or replace a Dynamic Table for churn risk scoring.

    Sources directly from USERS, SESSIONS, and ORDERS tables
    (not from DT-backed FVs) to avoid lag-dependency constraints.
    Computes per-user recency + activity metrics and a rule-based
    churn risk score. Refreshes on a 5-minute lag on FS_ML_WH.

    Returns the fully-qualified DT name.
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    inf = cfg["inference_schema"]
    ml_wh = cfg.get("ml_warehouse", "FS_ML_WH")

    dt_name = f"{db}.{inf}.CHURN_RISK_SCORES_DT"

    session.sql(
        f"CREATE SCHEMA IF NOT EXISTS {db}.{inf}"
    ).collect()

    session.sql(f"""
        CREATE OR REPLACE DYNAMIC TABLE {dt_name}
            TARGET_LAG = '5 minutes'
            WAREHOUSE = {ml_wh}
        AS
        WITH user_orders AS (
            SELECT
                USER_ID,
                COUNT(*) AS ORDER_CNT_90D,
                SUM(TOTAL_AMT) AS REVENUE_90D,
                MAX(ORDER_TS) AS LAST_ORDER_TS
            FROM {db}.{src}.ORDERS
            WHERE ORDER_TS >= DATEADD('day', -90,
                CURRENT_TIMESTAMP())
            GROUP BY USER_ID
        ),
        user_sessions AS (
            SELECT
                USER_ID,
                COUNT(*) AS SESSION_CNT_30D,
                MAX(SESSION_START_TS) AS LAST_SESSION
            FROM {db}.{src}.SESSIONS
            WHERE SESSION_START_TS >= DATEADD(
                'day', -30, CURRENT_TIMESTAMP())
              AND USER_ID IS NOT NULL
            GROUP BY USER_ID
        )
        SELECT
            u.USER_ID,
            u.LOYALTY_POINTS,
            u.IS_ACTIVE,
            COALESCE(o.ORDER_CNT_90D, 0)
                AS ORDER_CNT_90D,
            COALESCE(o.REVENUE_90D, 0)
                AS REVENUE_90D,
            COALESCE(s.SESSION_CNT_30D, 0)
                AS SESSION_CNT_30D,
            DATEDIFF('day',
                o.LAST_ORDER_TS,
                CURRENT_TIMESTAMP()
            ) AS DAYS_SINCE_ORDER,
            DATEDIFF('day',
                s.LAST_SESSION,
                CURRENT_TIMESTAMP()
            ) AS DAYS_SINCE_SESSION,
            CASE
                WHEN o.ORDER_CNT_90D IS NULL
                 AND COALESCE(
                     s.SESSION_CNT_30D, 0) < 3
                    THEN 0.9
                WHEN COALESCE(
                     o.ORDER_CNT_90D, 0) <= 1
                 AND COALESCE(
                     s.SESSION_CNT_30D, 0) < 10
                    THEN 0.6
                WHEN o.ORDER_CNT_90D >= 3
                 AND s.SESSION_CNT_30D >= 20
                    THEN 0.1
                ELSE 0.3
            END AS CHURN_RISK_SCORE,
            CURRENT_TIMESTAMP() AS SCORED_AT
        FROM {db}.{src}.USERS u
        LEFT JOIN user_orders o
            ON u.USER_ID = o.USER_ID
        LEFT JOIN user_sessions s
            ON u.USER_ID = s.USER_ID
    """).collect()

    print(f"  Inference DT created: {dt_name} "
          f"(TARGET_LAG=5 min, warehouse={ml_wh})")
    return dt_name


def drop_inference_dt(session, env: str = "DEV") -> None:
    """Drop the benchmark inference DT to clean up."""
    cfg = get_config(env)
    db = cfg["database"]
    inf = cfg["inference_schema"]
    dt_name = f"{db}.{inf}.CHURN_RISK_SCORES_DT"
    try:
        session.sql(
            f"DROP DYNAMIC TABLE IF EXISTS {dt_name}"
        ).collect()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background thread runner
# ---------------------------------------------------------------------------

def _workload_loop(
    workload_fn,
    session_factory,
    env: str,
    interval_seconds: float,
    deadline: float,
    results_queue: list,
    workload_name: str,
    stop_event: threading.Event,
):
    """Run a workload function in a loop until deadline or stop_event.

    Uses a single persistent session for the entire loop to avoid
    connection-pool invalidation when closing sessions concurrently
    with other threads sharing the same key-pair auth.
    """
    sess = None
    try:
        sess = session_factory()
    except Exception as e:
        results_queue.append(WorkloadCycleResult(
            workload=workload_name,
            cycle=0,
            started_at=datetime.now(
                timezone.utc
            ).isoformat(),
            duration_seconds=0,
            error=f"session creation failed: {e}",
        ))
        print(f"    [{workload_name}] "
              f"session creation failed: {e}")
        return

    cycle = 0
    while (time.time() < deadline
           and not stop_event.is_set()):
        cycle += 1
        try:
            result = workload_fn(
                sess, env, cycle=cycle
            )
            results_queue.append(result)
            status = (
                "ok" if result.error is None
                else f"ERR: {result.error}"
            )
            print(
                f"    [{workload_name}] "
                f"cycle {cycle}: "
                f"{result.duration_seconds:.1f}s, "
                f"{result.rows} rows — {status}"
            )
        except Exception as e:
            results_queue.append(
                WorkloadCycleResult(
                    workload=workload_name,
                    cycle=cycle,
                    started_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                    duration_seconds=0,
                    error=str(e),
                )
            )
            print(
                f"    [{workload_name}] "
                f"cycle {cycle}: ERROR {e}"
            )

        remaining = deadline - time.time()
        if remaining <= 0 or stop_event.is_set():
            break
        stop_event.wait(
            min(interval_seconds, remaining)
        )


def run_background_workloads(
    session_factory,
    env: str,
    duration_seconds: float,
    *,
    enable_dataset_gen: bool = False,
    dataset_gen_interval: float = 300,
    enable_batch_inference: bool = False,
    batch_inference_interval: float = 300,
) -> dict[str, WorkloadSummary]:
    """Start ML workloads as background threads, run for ``duration_seconds``.

    Returns a dict of workload name -> WorkloadSummary after all threads
    join.  Each thread gets its own Snowpark session via ``session_factory``.
    """
    deadline = time.time() + duration_seconds
    stop_event = threading.Event()
    all_results: dict[str, list[WorkloadCycleResult]] = {}

    workloads = []
    if enable_dataset_gen:
        results_list: list[WorkloadCycleResult] = []
        all_results["dataset_generation"] = results_list
        t = threading.Thread(
            target=_workload_loop,
            kwargs=dict(
                workload_fn=run_dataset_generation,
                session_factory=session_factory,
                env=env,
                interval_seconds=dataset_gen_interval,
                deadline=deadline,
                results_queue=results_list,
                workload_name="dataset_generation",
                stop_event=stop_event,
            ),
            daemon=True,
        )
        workloads.append(("dataset_generation", t))

    if enable_batch_inference:
        results_list = []
        all_results["batch_inference"] = results_list
        t = threading.Thread(
            target=_workload_loop,
            kwargs=dict(
                workload_fn=run_batch_inference,
                session_factory=session_factory,
                env=env,
                interval_seconds=batch_inference_interval,
                deadline=deadline,
                results_queue=results_list,
                workload_name="batch_inference",
                stop_event=stop_event,
            ),
            daemon=True,
        )
        workloads.append(("batch_inference", t))

    if not workloads:
        return {}

    for name, t in workloads:
        t.start()

    return _BackgroundHandle(
        threads=[(name, t) for name, t in workloads],
        all_results=all_results,
        stop_event=stop_event,
    )


class _BackgroundHandle:
    """Returned by ``run_background_workloads``; call ``.join()`` to collect."""

    def __init__(self, threads, all_results, stop_event):
        self._threads = threads
        self._all_results = all_results
        self._stop_event = stop_event

    def join(self, timeout: float = 30) -> dict[str, WorkloadSummary]:
        self._stop_event.set()
        for name, t in self._threads:
            t.join(timeout=timeout)

        summaries: dict[str, WorkloadSummary] = {}
        for name, results_list in self._all_results.items():
            ok = [r for r in results_list if r.error is None]
            failed = [r for r in results_list if r.error is not None]
            total_dur = sum(r.duration_seconds for r in ok)
            summaries[name] = WorkloadSummary(
                workload=name,
                cycles_completed=len(ok),
                cycles_failed=len(failed),
                total_rows=sum(r.rows for r in ok),
                total_duration_seconds=round(total_dur, 2),
                avg_duration_seconds=(
                    round(total_dur / len(ok), 2) if ok else 0
                ),
                versions_created=[r.version for r in ok if r.version],
                cycle_results=[
                    {
                        "cycle": r.cycle,
                        "started_at": r.started_at,
                        "duration_seconds": r.duration_seconds,
                        "rows": r.rows,
                        "version": r.version,
                        "error": r.error,
                    }
                    for r in results_list
                ],
            )
        return summaries

"""
OFT feature-serving benchmark — concurrent query workload with latency percentiles.

Emulates application-server traffic by running multiple concurrent threads,
each with its own Snowpark session, issuing point-lookups against Online
Feature Tables.

Architecture:
  * A dedicated XS multi-cluster warehouse isolates serving load from
    ingestion/transformation.
  * 8 threads per cluster (configurable) — scale up by increasing
    ``max_clusters`` on the warehouse.
  * Each thread loops for ``duration_seconds``, picking random entity keys
    and calling ``fs.read_feature_view(..., store_type="online")``.
  * Per-query wall-clock latency is recorded and aggregated into QPM and
    p50/p90/p95/p99 percentiles — both per-minute windows and overall.

Key ranges are auto-discovered from the backing Dynamic Tables at the start
of each run, so the benchmark always queries the full key space.

An optional ``target_qpm`` rate limiter paces queries to a specific throughput
rather than saturating the warehouse.

Usage::

    from feature_definitions.benchmark import (
        create_serving_warehouse, run_benchmark, BenchmarkConfig,
    )
    create_serving_warehouse(session, "DEV", max_clusters=2)
    cfg = BenchmarkConfig(duration_seconds=300, threads_per_cluster=8, max_clusters=2)
    result = run_benchmark(session, "DEV", cfg)
    result.print_summary()
"""

from __future__ import annotations

import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .config import get_config, ROLES, is_workspace

SERVING_WAREHOUSE = "FS_SERVING_WH"


# ---------------------------------------------------------------------------
# Warehouse management
# ---------------------------------------------------------------------------

def create_serving_warehouse(
    session,
    env: str = "DEV",
    *,
    min_clusters: int = 1,
    max_clusters: int = 1,
    warehouse_name: str = SERVING_WAREHOUSE,
) -> str:
    """Create (or alter) the dedicated serving warehouse.

    Multi-cluster auto-scale is configured via ``min_clusters`` /
    ``max_clusters``.  The warehouse is XS to match the "minimal footprint"
    policy used across this guide.
    """
    session.sql(f"""
        CREATE WAREHOUSE IF NOT EXISTS {warehouse_name}
            WAREHOUSE_SIZE      = 'X-SMALL'
            MIN_CLUSTER_COUNT   = {min_clusters}
            MAX_CLUSTER_COUNT   = {max_clusters}
            SCALING_POLICY      = 'STANDARD'
            AUTO_SUSPEND        = 60
            AUTO_RESUME         = TRUE
            INITIALLY_SUSPENDED = TRUE
            COMMENT = 'Feature Store serving benchmark — isolated from ingestion'
    """).collect()

    if max_clusters > 1:
        session.sql(f"""
            ALTER WAREHOUSE {warehouse_name} SET
                MIN_CLUSTER_COUNT = {min_clusters}
                MAX_CLUSTER_COUNT = {max_clusters}
        """).collect()

    for role_key in ("consumer", "dev", "admin"):
        try:
            session.sql(
                f"GRANT USAGE ON WAREHOUSE {warehouse_name} TO ROLE {ROLES[role_key]}"
            ).collect()
        except Exception:
            pass

    return warehouse_name


def drop_serving_warehouse(
    session,
    warehouse_name: str = SERVING_WAREHOUSE,
) -> None:
    """Drop the serving warehouse (cleanup)."""
    session.sql(f"DROP WAREHOUSE IF EXISTS {warehouse_name}").collect()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_OFT_TARGETS = [
    {
        "name": "SESSION_BEHAVIOR_FEATURES",
        "version": "V01",
        "entity_key": "SESSION_ID",
        "key_prefix": "sess_",
        "key_range": (1, 2000),
    },
    {
        "name": "USER_RECENCY_RAW",
        "version": "V01",
        "entity_key": "USER_ID",
        "key_prefix": "usr_",
        "key_range": (1, 50),
    },
]


@dataclass
class BenchmarkConfig:
    """Parameters for a benchmark run."""
    duration_seconds: int = 60
    threads_per_cluster: int = 8
    max_clusters: int = 1
    warehouse_name: str = SERVING_WAREHOUSE
    target_qpm: Optional[float] = None
    oft_targets: list[dict] = field(default_factory=lambda: [
        dict(t) for t in _DEFAULT_OFT_TARGETS
    ])

    @property
    def total_threads(self) -> int:
        return self.threads_per_cluster * self.max_clusters


# ---------------------------------------------------------------------------
# Auto-discover key ranges
# ---------------------------------------------------------------------------

def discover_key_ranges(session, env: str = "DEV",
                        targets: list[dict] | None = None) -> list[dict]:
    """Query MAX(entity_key) from each backing DT and update key_range.

    Returns a new list of target dicts with ``key_range`` set to ``(1, max_id)``.
    If the query fails or returns None, the original range is preserved.
    """
    cfg = get_config(env)
    db = cfg["database"]
    fs = cfg["fs_schema"]
    targets = targets or [dict(t) for t in _DEFAULT_OFT_TARGETS]
    updated = []

    for target in targets:
        t = dict(target)
        fqn = f'{db}.{fs}."{t["name"]}${t["version"]}"'
        prefix = t["key_prefix"]
        try:
            row = session.sql(f"""
                SELECT MAX(REPLACE({t["entity_key"]}, '{prefix}', '')::INT) AS MAX_ID
                FROM {fqn}
            """).collect()[0]
            max_id = row["MAX_ID"]
            if max_id and max_id > 0:
                t["key_range"] = (1, int(max_id))
        except Exception:
            pass
        updated.append(t)

    return updated


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class WindowStats:
    """Statistics for a single 1-minute window."""
    minute: int
    window_start: datetime
    window_end: datetime
    query_count: int
    error_count: int
    qpm: float
    percentiles: dict[str, float]
    per_fv: dict[str, dict[str, float]]


@dataclass
class BenchmarkResult:
    """Aggregated results from a benchmark run."""
    config: BenchmarkConfig
    started_at: datetime
    ended_at: datetime
    total_queries: int
    total_errors: int
    latencies_ms: list[float]
    per_fv: dict[str, list[float]]
    raw_records: list[tuple[str, float, float, Optional[str]]]
    key_ranges_used: dict[str, tuple[int, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def qpm(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return self.total_queries / self.duration_seconds * 60.0

    @staticmethod
    def _percentiles(arr: np.ndarray) -> dict[str, float]:
        if len(arr) == 0:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0,
                    "min": 0, "max": 0, "mean": 0}
        return {
            "p50": float(np.percentile(arr, 50)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
        }

    def percentiles(self, data: list[float] | None = None) -> dict[str, float]:
        arr = np.array(data if data is not None else self.latencies_ms)
        return self._percentiles(arr)

    def windows(self, window_seconds: int = 60) -> list[WindowStats]:
        """Bucket raw records into fixed-width time windows.

        Args:
            window_seconds: Window width (default 60 = 1 minute).

        Returns:
            List of WindowStats, one per window that contains data.
        """
        if not self.raw_records:
            return []

        epoch_start = self.started_at.timestamp()
        result = []
        max_ts = max(r[1] for r in self.raw_records)
        n_windows = int(math.ceil((max_ts - epoch_start) / window_seconds))

        for w in range(max(n_windows, 1)):
            w_start = epoch_start + w * window_seconds
            w_end = w_start + window_seconds

            window_recs = [
                r for r in self.raw_records
                if w_start <= r[1] < w_end
            ]
            if not window_recs:
                continue

            lats = np.array([r[2] for r in window_recs if r[3] is None])
            errs = [r for r in window_recs if r[3] is not None]
            ok_count = len(window_recs) - len(errs)

            fv_lats: dict[str, list[float]] = {}
            for fv_name, _, lat, err in window_recs:
                if err is None:
                    fv_lats.setdefault(fv_name, []).append(lat)

            per_fv_pcts = {
                fv: self._percentiles(np.array(v))
                for fv, v in fv_lats.items()
            }

            actual_span = min(w_end, max_ts) - w_start
            qpm = ok_count / actual_span * 60.0 if actual_span > 0 else 0

            result.append(WindowStats(
                minute=w + 1,
                window_start=datetime.fromtimestamp(w_start, tz=timezone.utc),
                window_end=datetime.fromtimestamp(w_end, tz=timezone.utc),
                query_count=len(window_recs),
                error_count=len(errs),
                qpm=qpm,
                percentiles=self._percentiles(lats),
                per_fv=per_fv_pcts,
            ))

        return result

    def print_summary(self) -> None:
        dur = self.duration_seconds
        pcts = self.percentiles()
        fv_names = list(self.per_fv.keys())

        print(f"\n{'='*80}")
        print(f"  OFT Serving Benchmark Results")
        print(f"{'='*80}")
        print(f"  Duration:    {dur:.1f}s")
        print(f"  Threads:     {self.config.total_threads} "
              f"({self.config.threads_per_cluster}/cluster × "
              f"{self.config.max_clusters} cluster(s))")
        print(f"  Warehouse:   {self.config.warehouse_name}")
        if self.config.target_qpm:
            print(f"  Target QPM:  {self.config.target_qpm:,.0f}")
        print(f"  Queries:     {self.total_queries}  "
              f"(errors: {self.total_errors})")
        print(f"  QPM:         {self.qpm:,.0f}")

        if self.key_ranges_used:
            print(f"\n  Key ranges (auto-discovered from DTs):")
            for fv, (lo, hi) in self.key_ranges_used.items():
                print(f"    {fv}: {lo:,}–{hi:,}")

        # --- Per-minute windows ---
        wins = self.windows()
        if len(wins) > 1:
            print(f"\n  {'─'*76}")
            print(f"  Per-Minute Windows")
            print(f"  {'─'*76}")
            hdr = f"  {'Min':>3s} {'Queries':>8s} {'Errors':>7s} {'QPM':>8s}"
            hdr += f" {'p50':>8s} {'p90':>8s} {'p95':>8s} {'p99':>8s} {'mean':>8s}"
            print(hdr)
            print(f"  {'─'*3} {'─'*8} {'─'*7} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
            for w in wins:
                p = w.percentiles
                print(f"  {w.minute:3d} {w.query_count:8d} {w.error_count:7d} "
                      f"{w.qpm:8,.0f} "
                      f"{p['p50']:7.1f}ms {p['p90']:7.1f}ms "
                      f"{p['p95']:7.1f}ms {p['p99']:7.1f}ms "
                      f"{p['mean']:7.1f}ms")

        # --- Overall ---
        print(f"\n  {'─'*76}")
        print(f"  Overall Latency")
        print(f"  {'─'*76}")
        col_hdr = f"  {'Metric':<12s} {'Overall':>10s}"
        for fv in fv_names:
            col_hdr += f" {fv[:22]:>24s}"
        print(col_hdr)
        sep = f"  {'─'*12} {'─'*10}"
        for _ in fv_names:
            sep += f" {'─'*24}"
        print(sep)
        for label in ("p50", "p90", "p95", "p99", "min", "max", "mean"):
            line = f"  {label:<12s} {pcts[label]:>9.1f}ms"
            for fv in fv_names:
                fv_pcts = self.percentiles(self.per_fv[fv])
                line += f" {fv_pcts[label]:>23.1f}ms"
            print(line)
        print(f"{'='*80}\n")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _random_key(prefix: str, lo: int, hi: int) -> str:
    n = random.randint(lo, hi)
    return f"{prefix}{n:08d}"


def _worker(
    worker_id: int,
    session_factory,
    env: str,
    config: BenchmarkConfig,
    deadline: float,
    epoch_start: float,
    query_interval: float | None,
) -> list[tuple[str, float, float, Optional[str]]]:
    """Single worker thread — creates its own session and queries OFTs.

    Returns a list of (fv_name, wall_clock_ts, latency_ms, error_or_None).
    ``wall_clock_ts`` is ``time.time()`` at query start (epoch seconds, UTC).
    """
    from snowflake.ml.feature_store import FeatureStore, CreationMode

    cfg = get_config(env)
    sess = session_factory()
    sess.sql(f"USE WAREHOUSE {config.warehouse_name}").collect()

    fs = FeatureStore(
        session=sess,
        database=cfg["database"],
        name=cfg["fs_schema"],
        default_warehouse=config.warehouse_name,
        creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
    )

    fv_cache = {}
    for t in config.oft_targets:
        fv_cache[t["name"]] = fs.get_feature_view(t["name"], t["version"])

    results: list[tuple[str, float, float, Optional[str]]] = []
    targets = config.oft_targets

    while time.monotonic() < deadline:
        target = random.choice(targets)
        fv_name = target["name"]
        key = _random_key(target["key_prefix"], *target["key_range"])

        wall_ts = time.time()
        t0 = time.monotonic()
        err = None
        try:
            fs.read_feature_view(
                fv_cache[fv_name],
                keys=[[key]],
                store_type="online",
            ).collect()
        except Exception as e:
            if time.monotonic() >= deadline:
                break
            err = str(e)[:200]
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        results.append((fv_name, wall_ts, elapsed_ms, err))

        if query_interval and time.monotonic() < deadline:
            sleep_for = query_interval - (elapsed_ms / 1000.0)
            if sleep_for > 0:
                time.sleep(sleep_for)

    try:
        sess.close()
    except Exception:
        pass

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_benchmark(
    session,
    env: str = "DEV",
    config: BenchmarkConfig | None = None,
    *,
    session_factory=None,
    auto_discover_keys: bool = True,
) -> BenchmarkResult:
    """Run the OFT serving benchmark.

    Args:
        session: An existing session (used for key-range discovery).
        env: Environment key.
        config: Benchmark parameters.  Defaults to 60s, 8 threads, 1 cluster.
        session_factory: Callable returning a new Snowpark Session.
            Each worker thread gets its own session.  If None, uses
            ``config.get_session(role=ROLES["dev"])``.
        auto_discover_keys: If True (default), query MAX(entity_key) from
            each backing DT and use the actual cardinality as the key range.

    Returns:
        BenchmarkResult with per-minute windows and overall QPM/percentiles.
    """
    config = config or BenchmarkConfig()

    if session_factory is None:
        if is_workspace():
            from .config import workspace_session_factory
            cfg = get_config(env)
            session_factory = workspace_session_factory(
                role=ROLES["dev"],
                warehouse=config.warehouse_name,
                database=cfg["database"],
                schema=cfg["fs_schema"],
            )
            print("Workspace detected: using SPCS "
                  "OAuth token for worker sessions")
        else:
            from .config import get_session as _gs
            def session_factory():
                return _gs(role=ROLES["dev"])

    # Auto-discover key ranges from DTs
    key_ranges_used: dict[str, tuple[int, int]] = {}
    if auto_discover_keys:
        print("Discovering key ranges from DTs...")
        config.oft_targets = discover_key_ranges(session, env, config.oft_targets)
        for t in config.oft_targets:
            key_ranges_used[t["name"]] = tuple(t["key_range"])
            print(f"  {t['name']}: {t['key_prefix']}{t['key_range'][0]:08d} – "
                  f"{t['key_prefix']}{t['key_range'][1]:08d} "
                  f"({t['key_range'][1]:,} keys)")

    # Rate limiter: per-thread query interval
    query_interval: float | None = None
    if config.target_qpm and config.target_qpm > 0:
        total_threads = config.total_threads
        per_thread_qps = (config.target_qpm / 60.0) / total_threads
        query_interval = 1.0 / per_thread_qps if per_thread_qps > 0 else None
        print(f"Rate limit: {config.target_qpm:,.0f} QPM → "
              f"{per_thread_qps:.1f} QPS/thread "
              f"(interval={query_interval:.3f}s)")

    total_threads = config.total_threads
    deadline = time.monotonic() + config.duration_seconds
    epoch_start = time.time()

    print(f"Starting benchmark: {total_threads} threads, "
          f"{config.duration_seconds}s, warehouse={config.warehouse_name} "
          f"(clusters: 1–{config.max_clusters})"
          f"{f', target={config.target_qpm:,.0f} QPM' if config.target_qpm else ', unlimited'}")

    started_at = datetime.now(timezone.utc)

    all_results: list[tuple[str, float, float, Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=total_threads) as pool:
        futures = [
            pool.submit(
                _worker, i, session_factory, env, config,
                deadline, epoch_start, query_interval,
            )
            for i in range(total_threads)
        ]
        for fut in as_completed(futures):
            all_results.extend(fut.result())

    ended_at = datetime.now(timezone.utc)

    latencies = [r[2] for r in all_results if r[3] is None]
    errors = [r[3] for r in all_results if r[3] is not None]

    per_fv: dict[str, list[float]] = {}
    for fv_name, _, lat, err in all_results:
        if err is None:
            per_fv.setdefault(fv_name, []).append(lat)

    return BenchmarkResult(
        config=config,
        started_at=started_at,
        ended_at=ended_at,
        total_queries=len(all_results),
        total_errors=len(errors),
        latencies_ms=latencies,
        per_fv=per_fv,
        raw_records=all_results,
        key_ranges_used=key_ranges_used,
        errors=errors[:20],
    )

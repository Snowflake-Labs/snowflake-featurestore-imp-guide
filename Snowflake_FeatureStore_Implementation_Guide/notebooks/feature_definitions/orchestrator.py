"""
End-to-end benchmark orchestrator — multi-step scaled test with reporting.

Drives a sequence of ``ScaleStep`` configurations, each specifying ingestion
volume, serving warehouse concurrency, refresh warehouse sizing, DT target lag,
and OFT query rate.  Produces three artefacts:

  * **Console output** — live per-step summaries during the run
  * **JSON file** — machine-readable results (written incrementally)
  * **Markdown report** — human-readable summary with cross-step comparison

Usage::

    from feature_definitions.orchestrator import ScaleStep, run_e2e_test

    steps = [
        ScaleStep("baseline", duration_minutes=2),
        ScaleStep("2x_ingest", duration_minutes=3,
                  sessions_per_batch=200, orders_per_batch=20,
                  serving_clusters=2),
        ScaleStep("peak", duration_minutes=3,
                  sessions_per_batch=500, orders_per_batch=50,
                  serving_clusters=4, refresh_clusters=4),
    ]
    results = run_e2e_test(session, steps)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import get_config


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------

@dataclass
class ScaleStep:
    """Configuration for one phase of a benchmark run."""
    name: str
    duration_minutes: int = 2
    # Ingestion
    sessions_per_batch: int = 50
    orders_per_batch: int = 5
    # Serving
    serving_clusters: int = 1
    target_qpm: Optional[float] = None
    threads_per_cluster: int = 8
    # DT refresh
    refresh_clusters: Optional[int] = None
    dt_target_lag: Optional[str] = None


# ---------------------------------------------------------------------------
# Config adjustment helpers
# ---------------------------------------------------------------------------

def _adjust_ingestion(session, env: str, step: ScaleStep) -> None:
    from .generator import set_scale
    set_scale(
        session, env,
        sessions_per_batch=step.sessions_per_batch,
        orders_per_batch=step.orders_per_batch,
    )


def _adjust_serving_warehouse(session, step: ScaleStep) -> None:
    cfg = get_config("DEV")
    wh = cfg.get("serving_warehouse", "FS_SERVING_WH")
    session.sql(f"""
        ALTER WAREHOUSE {wh} SET
            MAX_CLUSTER_COUNT = {step.serving_clusters}
    """).collect()


def _adjust_refresh_warehouse(session, clusters: int) -> None:
    cfg = get_config("DEV")
    wh = cfg.get("refresh_warehouse", "FS_REFRESH_WH")
    session.sql(f"""
        ALTER WAREHOUSE {wh} SET
            MAX_CLUSTER_COUNT = {clusters}
    """).collect()


def _adjust_dt_lag(session, env: str, lag: str) -> None:
    """ALTER TARGET_LAG on all INCREMENTAL DTs."""
    cfg = get_config(env)
    db = cfg["database"]
    fs = cfg["fs_schema"]

    rows = session.sql(f"SHOW DYNAMIC TABLES IN SCHEMA {db}.{fs}").collect()
    for r in rows:
        d = r.as_dict()
        if d.get("refresh_mode") == "INCREMENTAL":
            fqn = f'{db}.{fs}."{d["name"]}"'
            session.sql(f"ALTER DYNAMIC TABLE {fqn} SET TARGET_LAG = '{lag}'").collect()


def _apply_step(
    session, env: str, step: ScaleStep, prev: ScaleStep | None,
) -> list[str]:
    """Apply config changes for a step.

    Returns a list of change descriptions.
    """
    changes: list[str] = []

    ingest_changed = (
        prev is None
        or step.sessions_per_batch != prev.sessions_per_batch
        or step.orders_per_batch != prev.orders_per_batch
    )
    if ingest_changed:
        _adjust_ingestion(session, env, step)
        changes.append(
            f"ingestion: {step.sessions_per_batch} sessions, "
            f"{step.orders_per_batch} orders/batch"
        )

    serving_changed = (
        prev is None
        or step.serving_clusters != prev.serving_clusters
    )
    if serving_changed:
        _adjust_serving_warehouse(session, step)
        changes.append(
            f"serving warehouse: "
            f"max_clusters={step.serving_clusters}"
        )

    refresh_changed = (
        step.refresh_clusters is not None
        and (prev is None
             or step.refresh_clusters != prev.refresh_clusters)
    )
    if refresh_changed:
        _adjust_refresh_warehouse(session, step.refresh_clusters)
        changes.append(
            f"refresh warehouse: "
            f"max_clusters={step.refresh_clusters}"
        )

    lag_changed = (
        step.dt_target_lag is not None
        and (prev is None
             or step.dt_target_lag != prev.dt_target_lag)
    )
    if lag_changed:
        _adjust_dt_lag(session, env, step.dt_target_lag)
        changes.append(
            f"DT target_lag: {step.dt_target_lag} "
            f"(INCREMENTAL only)"
        )

    return changes


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _benchmark_result_to_dict(result) -> dict[str, Any]:
    """Convert a BenchmarkResult to a JSON-serialisable dict."""
    pcts = result.percentiles()
    per_fv = {}
    for fv_name, lats in result.per_fv.items():
        per_fv[fv_name] = result.percentiles(lats)

    windows = []
    for w in result.windows():
        windows.append({
            "minute": w.minute,
            "query_count": w.query_count,
            "error_count": w.error_count,
            "qpm": round(w.qpm, 1),
            "percentiles": {k: round(v, 2) for k, v in w.percentiles.items()},
            "per_fv": {
                fv: {k: round(v, 2) for k, v in p.items()}
                for fv, p in w.per_fv.items()
            },
        })

    return {
        "qpm": round(result.qpm, 1),
        "total_queries": result.total_queries,
        "total_errors": result.total_errors,
        "duration_seconds": round(result.duration_seconds, 1),
        "overall_percentiles": {k: round(v, 2) for k, v in pcts.items()},
        "per_fv": {
            fv: {k: round(v, 2) for k, v in p.items()}
            for fv, p in per_fv.items()
        },
        "windows": windows,
        "key_ranges": {
            fv: list(rng) for fv, rng in result.key_ranges_used.items()
        },
    }


def _serialise_pipeline_snapshot(snapshot: dict) -> dict:
    """Make pipeline_summary() output JSON-safe (convert datetimes)."""
    def _convert(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        return obj
    return _convert(snapshot)


def _extract_pipeline_stats(snapshot: dict) -> dict:
    """Compute scalar pipeline metrics from a pipeline_summary snapshot.

    Returns a flat dict of numeric values suitable for persisting
    as scalar columns and printing in the console summary.
    """
    import statistics as _st
    stats: dict[str, Any] = {}

    # --- DT refresh history ---
    rh = snapshot.get("dt_refresh_history", [])
    ok = [
        r for r in rh
        if "ERROR" not in r
        and r.get("DURATION_SECONDS") is not None
    ]
    incr = [
        r for r in ok
        if r.get("REFRESH_ACTION") == "INCREMENTAL"
    ]
    full = [
        r for r in ok
        if r.get("REFRESH_ACTION") == "FULL"
    ]
    stats["dt_refresh_count"] = len(ok)
    stats["dt_incr_count"] = len(incr)
    stats["dt_full_count"] = len(full)

    durations = sorted(
        r["DURATION_SECONDS"] for r in ok
    )
    if durations:
        n = len(durations)
        stats["dt_refresh_p50_s"] = round(
            durations[int(n * 0.5)], 2)
        stats["dt_refresh_p90_s"] = round(
            durations[min(int(n * 0.9), n - 1)], 2)
        stats["dt_refresh_p95_s"] = round(
            durations[min(int(n * 0.95), n - 1)], 2)
        stats["dt_refresh_max_s"] = round(
            durations[-1], 2)
        stats["dt_refresh_mean_s"] = round(
            _st.mean(durations), 2)
    else:
        for k in (
            "dt_refresh_p50_s", "dt_refresh_p90_s",
            "dt_refresh_p95_s", "dt_refresh_max_s",
            "dt_refresh_mean_s",
        ):
            stats[k] = None

    stats["dt_rows_inserted"] = sum(
        r.get("ROWS_INSERTED", 0) or 0 for r in ok
    )

    # Per-DT breakdown (for detailed reporting)
    per_dt: dict[str, list[float]] = {}
    for r in ok:
        dt_short = r["DT"].split("$")[0]
        per_dt.setdefault(dt_short, []).append(
            r["DURATION_SECONDS"]
        )
    stats["per_dt_refresh"] = {
        dt: {
            "count": len(ds),
            "p50_s": round(sorted(ds)[len(ds)//2], 2),
            "max_s": round(max(ds), 2),
            "rows": sum(
                r.get("ROWS_INSERTED", 0) or 0
                for r in ok
                if r["DT"].split("$")[0] == dt
            ),
        }
        for dt, ds in per_dt.items()
    }

    # --- Source / DT freshness ---
    src = snapshot.get("source_freshness", [])
    src_ages = [
        s["AGE_SECONDS"] for s in src
        if s.get("AGE_SECONDS") is not None
    ]
    stats["source_freshness_max_s"] = (
        round(max(src_ages), 1) if src_ages else None
    )

    dtf = snapshot.get("dt_freshness", [])
    dt_ages = [
        d["AGE_SECONDS"] for d in dtf
        if d.get("AGE_SECONDS") is not None
    ]
    stats["dt_freshness_max_s"] = (
        round(max(dt_ages), 1) if dt_ages else None
    )

    # --- Stage latency (source → DT) ---
    stages = snapshot.get("stage_latency", [])
    stage_lats = [
        s["LATENCY_SECONDS"] for s in stages
        if s.get("LATENCY_SECONDS") is not None
    ]
    stats["stage_latency_max_s"] = (
        max(stage_lats) if stage_lats else None
    )
    stats["stage_latency_mean_s"] = (
        round(_st.mean(stage_lats), 1)
        if stage_lats else None
    )

    # --- Batch ingestion ---
    batches = snapshot.get("batch_stats", [])
    stats["batch_count"] = len(batches)
    batch_durs = [
        b["DURATION_MS"] for b in batches
        if b.get("DURATION_MS") is not None
    ]
    stats["avg_batch_duration_ms"] = (
        round(_st.mean(batch_durs), 0)
        if batch_durs else None
    )
    stats["total_events_generated"] = sum(
        b.get("EVENTS_GENERATED", 0) or 0
        for b in batches
    )

    # --- Row counts ---
    stats["row_counts"] = snapshot.get(
        "row_counts", {"source": {}, "dt": {}}
    )

    return stats


def _print_pipeline_step_summary(ps: dict) -> None:
    """Print a console summary of pipeline metrics for a step."""
    sep = "\u2500" * 68
    print(f"\n  {sep}")
    print("  Pipeline Summary (DT Refresh / Ingestion)")
    print(f"  {sep}")

    n = ps.get("dt_refresh_count", 0)
    ni = ps.get("dt_incr_count", 0)
    nf = ps.get("dt_full_count", 0)
    print(f"  DT Refreshes: {n} total "
          f"({ni} incremental, {nf} full)")

    if n > 0:
        p50 = ps.get("dt_refresh_p50_s")
        p90 = ps.get("dt_refresh_p90_s")
        p95 = ps.get("dt_refresh_p95_s")
        mx = ps.get("dt_refresh_max_s")
        mn = ps.get("dt_refresh_mean_s")
        print(
            f"  Duration:  p50={p50}s  p90={p90}s  "
            f"p95={p95}s  max={mx}s  mean={mn}s"
        )
        ri = ps.get("dt_rows_inserted", 0)
        print(f"  Rows inserted: {ri:,}")

        per_dt = ps.get("per_dt_refresh", {})
        if per_dt:
            print("  Per DT:")
            for dt, d in per_dt.items():
                print(
                    f"    {dt:40s} "
                    f"n={d['count']}  "
                    f"p50={d['p50_s']}s  "
                    f"max={d['max_s']}s  "
                    f"rows={d['rows']:,}"
                )

    sf = ps.get("source_freshness_max_s")
    df = ps.get("dt_freshness_max_s")
    print(f"  Freshness: source max-age={sf}s  "
          f"DT max-age={df}s")

    sl = ps.get("stage_latency_max_s")
    sm = ps.get("stage_latency_mean_s")
    if sl is not None:
        print(f"  Source\u2192DT latency: "
              f"max={sl}s  mean={sm}s")

    bc = ps.get("batch_count", 0)
    bd = ps.get("avg_batch_duration_ms")
    te = ps.get("total_events_generated", 0)
    bd_str = f"{bd:.0f}ms" if bd else "N/A"
    print(f"  Batches: {bc} "
          f"(avg {bd_str}, {te:,} events)")

    # Row counts
    rc = ps.get("row_counts", {})
    src_rc = rc.get("source", {})
    dt_rc = rc.get("dt", {})
    if src_rc or dt_rc:
        print("  Row Counts:")
        if src_rc:
            parts = [
                f"{t}={c:,}" for t, c in src_rc.items()
                if c is not None
            ]
            if parts:
                print(f"    Source: {', '.join(parts)}")
        if dt_rc:
            for dt_name, cnt in dt_rc.items():
                if cnt is not None:
                    short = dt_name.split("$")[0]
                    print(f"    {short:42s} {cnt:>8,}")
    print(f"  {sep}")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _write_json(data: dict, path: Path) -> Path:
    """Write JSON, returning the actual path used.

    Falls back to ``$HOME`` then ``/tmp`` if the
    primary location is read-only (e.g. Workspace
    FBE filesystem).
    """
    candidates = [
        path,
        Path.home() / path.name,
        Path("/tmp") / path.name,
    ]
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(data, f,
                          indent=2, default=str)
            return p
        except OSError:
            continue
    return path


def _generate_markdown(data: dict, path: Path) -> None:
    """Generate a human-readable Markdown report from the results dict."""
    lines: list[str] = []
    w = lines.append

    w("# Benchmark Run Report\n")
    w(f"**Run ID:** {data['run_id']}")
    w(f"**Environment:** {data['environment']}")
    ov = data["overall"]
    w(f"**Total Duration:** {ov['total_duration_seconds']:.0f}s")
    w(f"**Steps Completed:** {ov['steps_completed']}")
    w(f"**Total Queries:** {ov['total_queries']:,}")
    w("")

    # Cross-step OFT performance
    w("## Cross-Step Summary — OFT Serving\n")
    w("| Step | Dur | Ingest | Threads "
      "| QPM | p50 | p95 | p99 | Err |")
    w("|------|-----|--------|--------"
      "|-----|-----|-----|-----|-----|")
    for s in data["steps"]:
        c = s["config"]
        b = s["benchmark"]
        p = b["overall_percentiles"]
        thr = c.get("threads_per_cluster", 8)
        cl = c.get("serving_clusters", 1)
        w(f"| {c['name']} "
          f"| {c['duration_minutes']}m "
          f"| {c['sessions_per_batch']}"
          f"/{c['orders_per_batch']} "
          f"| {thr * cl} "
          f"| {b['qpm']:,.0f} "
          f"| {p['p50']:.0f} "
          f"| {p['p95']:.0f} "
          f"| {p['p99']:.0f} "
          f"| {b['total_errors']} |")
    w("")

    # Cross-step pipeline / DT refresh
    w("## Cross-Step Summary — Pipeline\n")
    w("| Step | DT Refreshes (I/F) "
      "| DT p50 | DT p95 | DT max "
      "| Rows Ins | Batches | Events |")
    w("|------|--------------------"
      "|--------|--------|--------"
      "|----------|---------|--------|")
    for s in data["steps"]:
        c = s["config"]
        ps = s.get("pipeline_stats", {})
        ni = ps.get("dt_incr_count", 0)
        nf = ps.get("dt_full_count", 0)
        dp50 = ps.get("dt_refresh_p50_s")
        dp50s = f"{dp50}s" if dp50 is not None else "—"
        dp95 = ps.get("dt_refresh_p95_s")
        dp95s = f"{dp95}s" if dp95 is not None else "—"
        dmx = ps.get("dt_refresh_max_s")
        dmxs = f"{dmx}s" if dmx is not None else "—"
        ri = ps.get("dt_rows_inserted", 0)
        bc = ps.get("batch_count", 0)
        te = ps.get("total_events_generated", 0)
        w(f"| {c['name']} "
          f"| {ni}/{nf} "
          f"| {dp50s} "
          f"| {dp95s} "
          f"| {dmxs} "
          f"| {ri:,} "
          f"| {bc} "
          f"| {te:,} |")
    w("")

    # Row count progression table
    w("## Row Count Progression\n")
    # Gather all source/DT names across steps
    all_src = set()
    all_dt = set()
    for s in data["steps"]:
        rc = s.get("pipeline_stats", {}).get(
            "row_counts", {}
        )
        all_src.update(rc.get("source", {}).keys())
        all_dt.update(rc.get("dt", {}).keys())
    if all_src or all_dt:
        cols = sorted(all_src) + sorted(all_dt)
        hdr = "| Step | " + " | ".join(
            c.split("$")[0] for c in cols
        ) + " |"
        sep_row = "|------|" + "|".join(
            "--------:" for _ in cols
        ) + "|"
        w(hdr)
        w(sep_row)
        for s in data["steps"]:
            rc = s.get("pipeline_stats", {}).get(
                "row_counts", {}
            )
            name = s["config"]["name"]
            vals = []
            for c in cols:
                v = rc.get("source", {}).get(c)
                if v is None:
                    v = rc.get("dt", {}).get(c)
                vals.append(
                    f"{v:,}" if v is not None else "—"
                )
            w(f"| {name} | " + " | ".join(vals) + " |")
        w("")

    # Per-step detail
    for i, s in enumerate(data["steps"]):
        cfg = s["config"]
        b = s["benchmark"]
        p = b["overall_percentiles"]

        w(f"## Step {i+1}: {cfg['name']}\n")
        dur = cfg['duration_minutes']
        sess = cfg['sessions_per_batch']
        ords = cfg['orders_per_batch']
        tpc = cfg.get('threads_per_cluster', 8)
        scl = cfg.get('serving_clusters', 1)
        threads = tpc * scl
        w(f"- **Duration:** {dur} minutes")
        w(f"- **Ingestion:** {sess} sessions, "
          f"{ords} orders/batch")
        w(f"- **Serving:** {threads} threads "
          f"({tpc}/cluster x {scl} cluster(s))")
        if cfg.get("target_qpm"):
            w(f"- **Target QPM:** {cfg['target_qpm']:,.0f}")
        if cfg.get("refresh_clusters"):
            w(f"- **Refresh clusters:** {cfg['refresh_clusters']}")
        if cfg.get("dt_target_lag"):
            w(f"- **DT target lag:** {cfg['dt_target_lag']}")

        if b.get("key_ranges"):
            kr = ", ".join(
                f"{fv} {rng[0]:,}\u2013{rng[1]:,}"
                for fv, rng in b["key_ranges"].items()
            )
            w(f"- **Key ranges:** {kr}")

        w(f"\n**Overall:** QPM={b['qpm']:,.0f}, "
          f"p50={p['p50']:.0f}ms, p90={p['p90']:.0f}ms, "
          f"p95={p['p95']:.0f}ms, p99={p['p99']:.0f}ms\n")

        # Per-minute windows
        wins = b.get("windows", [])
        if len(wins) > 1:
            w("### Per-Minute Windows\n")
            w("| Min | Queries | Errors | QPM | p50 | p90 | p95 | p99 |")
            w("|-----|---------|--------|-----|-----|-----|-----|-----|")
            for wn in wins:
                wp = wn["percentiles"]
                w(f"| {wn['minute']} "
                  f"| {wn['query_count']} "
                  f"| {wn['error_count']} "
                  f"| {wn['qpm']:,.0f} "
                  f"| {wp['p50']:.0f}ms "
                  f"| {wp['p90']:.0f}ms "
                  f"| {wp['p95']:.0f}ms "
                  f"| {wp['p99']:.0f}ms |")
            w("")

        # Per-FV breakdown
        if b.get("per_fv"):
            w("### Per Feature View\n")
            w("| Feature View | p50 | p90 | p95 | p99 | min | max |")
            w("|---|---|---|---|---|---|---|")
            for fv, fp in b["per_fv"].items():
                w(f"| {fv} "
                  f"| {fp['p50']:.0f}ms "
                  f"| {fp['p90']:.0f}ms "
                  f"| {fp['p95']:.0f}ms "
                  f"| {fp['p99']:.0f}ms "
                  f"| {fp['min']:.0f}ms "
                  f"| {fp['max']:.0f}ms |")
            w("")

        # Pipeline snapshot
        snap = s.get("pipeline_snapshot")
        if snap:
            w("### Pipeline Snapshot\n")

            src = snap.get("source_freshness", [])
            if src:
                w("**Source freshness:**\n")
                for f in src:
                    age = f.get("AGE_SECONDS")
                    tbl = f["TABLE"]
                    if age is not None:
                        w(f"- {tbl}: {age}s")
                    else:
                        w(f"- {tbl}: N/A")
                w("")

            dts = snap.get("dt_freshness", [])
            if dts:
                w("**DT freshness:**\n")
                for f in dts:
                    age = f.get("AGE_SECONDS")
                    tbl = f["TABLE"]
                    if age is not None:
                        w(f"- {tbl}: {age}s")
                    else:
                        w(f"- {tbl}: N/A")
                w("")

            # DT refresh history
            rh = snap.get(
                "dt_refresh_history", []
            )
            ok = [r for r in rh if "ERROR" not in r]
            if ok:
                w("**DT refresh history "
                  "(recent):**\n")
                w("| DT | Action | Duration "
                  "| Exec ms | Rows Ins "
                  "| Rows Del |")
                w("|---|---|---|---|---|---|")
                for r in ok:
                    dt = r.get("DT", "")
                    short = dt.split("$")[0]
                    act = r.get(
                        "REFRESH_ACTION", "")
                    dur = r.get("DURATION_SECONDS")
                    dur_s = (f"{dur:.1f}s"
                             if dur else "N/A")
                    exe = r.get("EXECUTION_MS")
                    exe_s = (str(exe)
                             if exe is not None
                             else "N/A")
                    ins = r.get(
                        "ROWS_INSERTED")
                    ins_s = (str(ins)
                             if ins is not None
                             else "")
                    dl = r.get("ROWS_DELETED")
                    dl_s = (str(dl)
                            if dl is not None
                            else "")
                    w(f"| {short} "
                      f"| {act} "
                      f"| {dur_s} "
                      f"| {exe_s} "
                      f"| {ins_s} "
                      f"| {dl_s} |")
                w("")

            # Batch ingestion stats
            batches = snap.get("batch_stats", [])
            if batches:
                w("**Recent ingestion "
                  "batches:**\n")
                w("| Batch | Sessions "
                  "| Events | Orders "
                  "| Gen ms |")
                w("|---|---|---|---|---|")
                for b in batches[:5]:
                    bid = b.get("LOG_ID", "?")
                    sess = b.get(
                        "SESSIONS_GENERATED", 0)
                    evts = b.get(
                        "EVENTS_GENERATED", 0)
                    ords = b.get(
                        "ORDERS_GENERATED", 0)
                    ms = b.get(
                        "DURATION_MS", "N/A")
                    w(f"| {bid} "
                      f"| {sess} "
                      f"| {evts} "
                      f"| {ords} "
                      f"| {ms} |")
                w("")

    content = "\n".join(lines) + "\n"
    candidates = [
        path,
        Path.home() / path.name,
        Path("/tmp") / path.name,
    ]
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
            return
        except OSError:
            continue


# ---------------------------------------------------------------------------
# Snowflake persistence — cross-run comparison
# ---------------------------------------------------------------------------

def _persist_to_snowflake(
    session, env: str, results_data: dict,
) -> tuple[str, str]:
    """Write results to ``BENCHMARK_RUNS`` / ``BENCHMARK_STEPS``.

    Tables are created on first call.  Rows for the same
    ``RUN_ID`` are replaced (idempotent).

    Returns:
        ``(runs_table_fqn, steps_table_fqn)``
    """
    from snowflake.snowpark.functions import (
        parse_json, col,
    )

    cfg_d = get_config(env)
    db = cfg_d["database"]
    fs = cfg_d["fs_schema"]
    runs_tbl = f"{db}.{fs}.BENCHMARK_RUNS"
    steps_tbl = f"{db}.{fs}.BENCHMARK_STEPS"

    # --- DDL (idempotent) ---
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {runs_tbl} (
            RUN_ID           VARCHAR NOT NULL,
            RUN_TS           TIMESTAMP_NTZ NOT NULL,
            ENVIRONMENT      VARCHAR,
            ACCOUNT          VARCHAR,
            NUM_STEPS        NUMBER,
            TOTAL_DURATION_S FLOAT,
            TOTAL_QUERIES    NUMBER,
            WAREHOUSES       VARIANT,
            RESULTS          VARIANT,
            PRIMARY KEY (RUN_ID)
        )
    """).collect()

    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {steps_tbl} (
            RUN_ID              VARCHAR NOT NULL,
            RUN_TS              TIMESTAMP_NTZ NOT NULL,
            STEP_INDEX          NUMBER  NOT NULL,
            STEP_NAME           VARCHAR,
            DURATION_MINUTES    NUMBER,
            SESSIONS_PER_BATCH  NUMBER,
            ORDERS_PER_BATCH    NUMBER,
            SERVING_CLUSTERS    NUMBER,
            REFRESH_CLUSTERS    NUMBER,
            DT_TARGET_LAG       VARCHAR,
            THREADS_PER_CLUSTER NUMBER,
            TARGET_QPM          FLOAT,
            TOTAL_QUERIES       NUMBER,
            TOTAL_ERRORS        NUMBER,
            QPM                 FLOAT,
            P50_MS              FLOAT,
            P90_MS              FLOAT,
            P95_MS              FLOAT,
            P99_MS              FLOAT,
            MEAN_MS             FLOAT,
            MIN_MS              FLOAT,
            MAX_MS              FLOAT,
            DT_REFRESH_COUNT    NUMBER,
            DT_INCR_COUNT       NUMBER,
            DT_FULL_COUNT       NUMBER,
            DT_REFRESH_P50_S    FLOAT,
            DT_REFRESH_P90_S    FLOAT,
            DT_REFRESH_P95_S    FLOAT,
            DT_REFRESH_MAX_S    FLOAT,
            DT_REFRESH_MEAN_S   FLOAT,
            DT_ROWS_INSERTED    NUMBER,
            SOURCE_FRESH_MAX_S  FLOAT,
            DT_FRESH_MAX_S      FLOAT,
            STAGE_LAT_MAX_S     FLOAT,
            STAGE_LAT_MEAN_S    FLOAT,
            BATCH_COUNT         NUMBER,
            AVG_BATCH_DUR_MS    FLOAT,
            TOTAL_EVENTS        NUMBER,
            BENCHMARK_DETAIL    VARIANT,
            PIPELINE_SNAPSHOT   VARIANT,
            PIPELINE_STATS      VARIANT,
            PRIMARY KEY (RUN_ID, STEP_INDEX)
        )
    """).collect()

    # Schema evolution — add columns that may be
    # missing if the table was created by an older
    # version of the orchestrator.
    _new_cols = [
        ("DT_REFRESH_COUNT", "NUMBER"),
        ("DT_INCR_COUNT", "NUMBER"),
        ("DT_FULL_COUNT", "NUMBER"),
        ("DT_REFRESH_P50_S", "FLOAT"),
        ("DT_REFRESH_P90_S", "FLOAT"),
        ("DT_REFRESH_P95_S", "FLOAT"),
        ("DT_REFRESH_MAX_S", "FLOAT"),
        ("DT_REFRESH_MEAN_S", "FLOAT"),
        ("DT_ROWS_INSERTED", "NUMBER"),
        ("SOURCE_FRESH_MAX_S", "FLOAT"),
        ("DT_FRESH_MAX_S", "FLOAT"),
        ("STAGE_LAT_MAX_S", "FLOAT"),
        ("STAGE_LAT_MEAN_S", "FLOAT"),
        ("BATCH_COUNT", "NUMBER"),
        ("AVG_BATCH_DUR_MS", "FLOAT"),
        ("TOTAL_EVENTS", "NUMBER"),
        ("PIPELINE_STATS", "VARIANT"),
    ]
    for cn, ct in _new_cols:
        try:
            session.sql(
                f"ALTER TABLE {steps_tbl} "
                f"ADD COLUMN {cn} {ct}"
            ).collect()
        except Exception:
            pass

    run_id = results_data["run_id"]

    # Idempotent — remove any prior partial write
    for tbl in (runs_tbl, steps_tbl):
        session.sql(
            f"DELETE FROM {tbl} "
            f"WHERE RUN_ID = '{run_id}'"
        ).collect()

    # Timestamp from run_id (2026-04-07T12-55-07Z)
    ts = datetime.strptime(
        run_id, "%Y-%m-%dT%H-%M-%SZ"
    )
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    ov = results_data["overall"]

    # ---- BENCHMARK_RUNS ----
    rdf = session.create_dataframe(
        [[
            run_id, ts_str,
            results_data.get("environment", ""),
            results_data.get("account", ""),
            int(ov["steps_completed"]),
            float(ov["total_duration_seconds"]),
            int(ov["total_queries"]),
            json.dumps(
                results_data.get("warehouses", {}),
                default=str,
            ),
            json.dumps(results_data, default=str),
        ]],
        schema=[
            "RUN_ID", "TS_STR", "ENVIRONMENT",
            "ACCOUNT", "NUM_STEPS",
            "TOTAL_DURATION_S", "TOTAL_QUERIES",
            "WH_JSON", "RESULTS_JSON",
        ],
    )
    rdf = rdf.select(
        col("RUN_ID"),
        col("TS_STR").cast(
            "TIMESTAMP_NTZ"
        ).alias("RUN_TS"),
        col("ENVIRONMENT"),
        col("ACCOUNT"),
        col("NUM_STEPS"),
        col("TOTAL_DURATION_S"),
        col("TOTAL_QUERIES"),
        parse_json(
            col("WH_JSON")
        ).alias("WAREHOUSES"),
        parse_json(
            col("RESULTS_JSON")
        ).alias("RESULTS"),
    )
    rdf.write.mode("append").save_as_table(runs_tbl)

    # ---- BENCHMARK_STEPS ----
    rows: list[tuple] = []
    for idx, sd in enumerate(results_data["steps"]):
        c = sd["config"]
        b = sd["benchmark"]
        p = b.get("overall_percentiles", {})
        ps = sd.get("pipeline_stats", {})
        rows.append((
            run_id, ts_str, idx + 1,
            c["name"],
            c.get("duration_minutes"),
            c.get("sessions_per_batch"),
            c.get("orders_per_batch"),
            c.get("serving_clusters"),
            c.get("refresh_clusters"),
            c.get("dt_target_lag"),
            c.get("threads_per_cluster"),
            c.get("target_qpm"),
            b.get("total_queries"),
            b.get("total_errors"),
            b.get("qpm"),
            p.get("p50"), p.get("p90"),
            p.get("p95"), p.get("p99"),
            p.get("mean"),
            p.get("min"), p.get("max"),
            # Pipeline scalars
            ps.get("dt_refresh_count"),
            ps.get("dt_incr_count"),
            ps.get("dt_full_count"),
            ps.get("dt_refresh_p50_s"),
            ps.get("dt_refresh_p90_s"),
            ps.get("dt_refresh_p95_s"),
            ps.get("dt_refresh_max_s"),
            ps.get("dt_refresh_mean_s"),
            ps.get("dt_rows_inserted"),
            ps.get("source_freshness_max_s"),
            ps.get("dt_freshness_max_s"),
            ps.get("stage_latency_max_s"),
            ps.get("stage_latency_mean_s"),
            ps.get("batch_count"),
            ps.get("avg_batch_duration_ms"),
            ps.get("total_events_generated"),
            # VARIANTs
            json.dumps(b, default=str),
            json.dumps(
                sd.get("pipeline_snapshot", {}),
                default=str,
            ),
            json.dumps(ps, default=str),
        ))

    if rows:
        sdf = session.create_dataframe(
            rows,
            schema=[
                "RUN_ID", "TS_STR",
                "STEP_INDEX", "STEP_NAME",
                "DURATION_MINUTES",
                "SESSIONS_PER_BATCH",
                "ORDERS_PER_BATCH",
                "SERVING_CLUSTERS",
                "REFRESH_CLUSTERS",
                "DT_TARGET_LAG",
                "THREADS_PER_CLUSTER",
                "TARGET_QPM",
                "TOTAL_QUERIES", "TOTAL_ERRORS",
                "QPM", "P50_MS", "P90_MS",
                "P95_MS", "P99_MS", "MEAN_MS",
                "MIN_MS", "MAX_MS",
                "DT_REFRESH_COUNT",
                "DT_INCR_COUNT",
                "DT_FULL_COUNT",
                "DT_REFRESH_P50_S",
                "DT_REFRESH_P90_S",
                "DT_REFRESH_P95_S",
                "DT_REFRESH_MAX_S",
                "DT_REFRESH_MEAN_S",
                "DT_ROWS_INSERTED",
                "SOURCE_FRESH_MAX_S",
                "DT_FRESH_MAX_S",
                "STAGE_LAT_MAX_S",
                "STAGE_LAT_MEAN_S",
                "BATCH_COUNT",
                "AVG_BATCH_DUR_MS",
                "TOTAL_EVENTS",
                "BENCH_JSON", "SNAP_JSON",
                "STATS_JSON",
            ],
        )
        sdf = sdf.select(
            col("RUN_ID"),
            col("TS_STR").cast(
                "TIMESTAMP_NTZ"
            ).alias("RUN_TS"),
            col("STEP_INDEX").cast(
                "NUMBER"
            ).alias("STEP_INDEX"),
            col("STEP_NAME"),
            col("DURATION_MINUTES").cast(
                "NUMBER"
            ).alias("DURATION_MINUTES"),
            col("SESSIONS_PER_BATCH").cast(
                "NUMBER"
            ).alias("SESSIONS_PER_BATCH"),
            col("ORDERS_PER_BATCH").cast(
                "NUMBER"
            ).alias("ORDERS_PER_BATCH"),
            col("SERVING_CLUSTERS").cast(
                "NUMBER"
            ).alias("SERVING_CLUSTERS"),
            col("REFRESH_CLUSTERS").cast(
                "NUMBER"
            ).alias("REFRESH_CLUSTERS"),
            col("DT_TARGET_LAG"),
            col("THREADS_PER_CLUSTER").cast(
                "NUMBER"
            ).alias("THREADS_PER_CLUSTER"),
            col("TARGET_QPM").cast(
                "FLOAT"
            ).alias("TARGET_QPM"),
            col("TOTAL_QUERIES").cast(
                "NUMBER"
            ).alias("TOTAL_QUERIES"),
            col("TOTAL_ERRORS").cast(
                "NUMBER"
            ).alias("TOTAL_ERRORS"),
            col("QPM").cast(
                "FLOAT"
            ).alias("QPM"),
            col("P50_MS").cast(
                "FLOAT"
            ).alias("P50_MS"),
            col("P90_MS").cast(
                "FLOAT"
            ).alias("P90_MS"),
            col("P95_MS").cast(
                "FLOAT"
            ).alias("P95_MS"),
            col("P99_MS").cast(
                "FLOAT"
            ).alias("P99_MS"),
            col("MEAN_MS").cast(
                "FLOAT"
            ).alias("MEAN_MS"),
            col("MIN_MS").cast(
                "FLOAT"
            ).alias("MIN_MS"),
            col("MAX_MS").cast(
                "FLOAT"
            ).alias("MAX_MS"),
            # Pipeline scalar columns
            col("DT_REFRESH_COUNT").cast(
                "NUMBER"
            ).alias("DT_REFRESH_COUNT"),
            col("DT_INCR_COUNT").cast(
                "NUMBER"
            ).alias("DT_INCR_COUNT"),
            col("DT_FULL_COUNT").cast(
                "NUMBER"
            ).alias("DT_FULL_COUNT"),
            col("DT_REFRESH_P50_S").cast(
                "FLOAT"
            ).alias("DT_REFRESH_P50_S"),
            col("DT_REFRESH_P90_S").cast(
                "FLOAT"
            ).alias("DT_REFRESH_P90_S"),
            col("DT_REFRESH_P95_S").cast(
                "FLOAT"
            ).alias("DT_REFRESH_P95_S"),
            col("DT_REFRESH_MAX_S").cast(
                "FLOAT"
            ).alias("DT_REFRESH_MAX_S"),
            col("DT_REFRESH_MEAN_S").cast(
                "FLOAT"
            ).alias("DT_REFRESH_MEAN_S"),
            col("DT_ROWS_INSERTED").cast(
                "NUMBER"
            ).alias("DT_ROWS_INSERTED"),
            col("SOURCE_FRESH_MAX_S").cast(
                "FLOAT"
            ).alias("SOURCE_FRESH_MAX_S"),
            col("DT_FRESH_MAX_S").cast(
                "FLOAT"
            ).alias("DT_FRESH_MAX_S"),
            col("STAGE_LAT_MAX_S").cast(
                "FLOAT"
            ).alias("STAGE_LAT_MAX_S"),
            col("STAGE_LAT_MEAN_S").cast(
                "FLOAT"
            ).alias("STAGE_LAT_MEAN_S"),
            col("BATCH_COUNT").cast(
                "NUMBER"
            ).alias("BATCH_COUNT"),
            col("AVG_BATCH_DUR_MS").cast(
                "FLOAT"
            ).alias("AVG_BATCH_DUR_MS"),
            col("TOTAL_EVENTS").cast(
                "NUMBER"
            ).alias("TOTAL_EVENTS"),
            # VARIANT columns
            parse_json(
                col("BENCH_JSON")
            ).alias("BENCHMARK_DETAIL"),
            parse_json(
                col("SNAP_JSON")
            ).alias("PIPELINE_SNAPSHOT"),
            parse_json(
                col("STATS_JSON")
            ).alias("PIPELINE_STATS"),
        )
        sdf.write.mode("append").save_as_table(
            steps_tbl
        )

    return runs_tbl, steps_tbl


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_e2e_test(
    session,
    steps: list[ScaleStep],
    *,
    env: str = "DEV",
    warmup_seconds: int = 10,
    output_dir: str | Path | None = None,
    session_factory=None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run a multi-step scaled benchmark test.

    Args:
        session: A Snowpark session with sufficient privileges (ACCOUNTADMIN
            or FS_ADMIN_ROLE for warehouse ALTERs and task control).
        steps: Ordered list of scale steps to execute.
        env: Environment key.
        warmup_seconds: Pause after applying step config before starting
            the benchmark (lets warehouse spin up and DTs begin refresh).
        output_dir: Directory for JSON + Markdown output.  Defaults to
            ``_internal_development/benchmark_e2e_demo/results/``.
        session_factory: Passed through to ``run_benchmark()``.  If None,
            the benchmark creates its own sessions per worker thread.
        persist: If True (default), write results to Snowflake tables
            ``BENCHMARK_RUNS`` and ``BENCHMARK_STEPS`` for cross-run
            comparison via SQL.

    Returns:
        The full results dict (same structure as the JSON file).
    """
    from .benchmark import BenchmarkConfig, run_benchmark
    from .generator import resume_task, suspend_task
    from .latency import pipeline_summary

    if output_dir is None:
        base = Path(__file__).resolve().parents[2]
        output_dir = (
            base.parent / "_internal_development"
            / "benchmark_e2e_demo" / "results"
        )
    output_dir = Path(output_dir)

    ts_fmt = "%Y-%m-%dT%H-%M-%SZ"
    run_id = datetime.now(timezone.utc).strftime(ts_fmt)
    json_path = output_dir / f"benchmark_results_{run_id}.json"
    md_path = output_dir / f"benchmark_report_{run_id}.md"

    cfg = get_config(env)

    db_name = cfg.get("database", "") if cfg else ""
    acct = db_name.split("_")[0] if db_name else "unknown"
    results_data: dict[str, Any] = {
        "run_id": run_id,
        "environment": env,
        "account": acct,
        "warehouses": {
            "dev": cfg.get("warehouse"),
            "refresh": cfg.get("refresh_warehouse"),
            "serving": cfg.get("serving_warehouse"),
        },
        "steps": [],
        "overall": {
            "total_duration_seconds": 0,
            "total_queries": 0,
            "steps_completed": 0,
        },
    }

    run_start = time.monotonic()

    # Start ingestion
    banner = "=" * 70
    print(f"\n{banner}")
    print("  E2E Benchmark Orchestrator")
    print(f"  Run ID: {run_id}")
    print(f"  Steps:  {len(steps)}")
    total_min = sum(s.duration_minutes for s in steps)
    print(f"  Planned duration: {total_min} minutes")
    print(f"{banner}\n")

    print("Resuming ingestion task...")
    try:
        resume_task(session, env)
        print("  Task resumed")
    except Exception as e:
        print(f"  Warning: could not resume task ({e})")
        print("  Ingestion will rely on manual "
              "batches or an already-running task")

    prev_step: ScaleStep | None = None

    try:
        for i, step in enumerate(steps):
            step_num = i + 1
            sep = "\u2500" * 70
            print(f"\n{sep}")
            print(f"  Step {step_num}/{len(steps)}: "
                  f"{step.name}")
            print(sep)

            # Apply config changes
            changes = _apply_step(session, env, step, prev_step)
            if changes:
                print("  Config changes:")
                for c in changes:
                    print(f"    - {c}")
            else:
                print("  No config changes "
              "(same as previous step)")

            # Warmup pause
            if warmup_seconds > 0:
                print(f"  Warming up ({warmup_seconds}s)...")
                time.sleep(warmup_seconds)

            # Run benchmark
            bench_cfg = BenchmarkConfig(
                duration_seconds=step.duration_minutes * 60,
                threads_per_cluster=step.threads_per_cluster,
                max_clusters=step.serving_clusters,
                target_qpm=step.target_qpm,
            )

            bench_result = run_benchmark(
                session, env, bench_cfg,
                session_factory=session_factory,
            )
            bench_result.print_summary()

            # Pipeline snapshot — look back over step
            # duration + warmup for refresh history
            hist_min = step.duration_minutes + 2
            print("  Capturing pipeline snapshot "
                  f"(last {hist_min} min)...")
            try:
                snapshot = pipeline_summary(
                    session, env,
                    refresh_history_minutes=hist_min,
                    batch_history_count=hist_min * 2,
                )
            except Exception as e:
                print(
                    "  Warning: pipeline_summary "
                    f"failed ({e})"
                )
                snapshot = {}

            # Extract & print pipeline stats
            pipeline_stats = (
                _extract_pipeline_stats(snapshot)
                if snapshot else {}
            )
            if pipeline_stats:
                _print_pipeline_step_summary(
                    pipeline_stats
                )

            # Record step result
            step_data = {
                "config": asdict(step),
                "benchmark": _benchmark_result_to_dict(bench_result),
                "pipeline_snapshot": _serialise_pipeline_snapshot(snapshot),
                "pipeline_stats": pipeline_stats,
            }
            results_data["steps"].append(step_data)
            results_data["overall"]["steps_completed"] = step_num
            results_data["overall"]["total_queries"] += bench_result.total_queries
            results_data["overall"]["total_duration_seconds"] = round(
                time.monotonic() - run_start, 1
            )

            # Write JSON incrementally
            actual = _write_json(results_data, json_path)
            if actual != json_path:
                json_path = actual
                md_path = actual.parent / md_path.name
            print(f"  Results saved: {json_path}")

            prev_step = step

    except KeyboardInterrupt:
        print("\n\n  Interrupted! Saving partial results...")
        results_data["overall"]["total_duration_seconds"] = round(
            time.monotonic() - run_start, 1
        )

    finally:
        # Shut down ingestion
        print("\nSuspending ingestion task...")
        try:
            suspend_task(session, env)
            print("  Task suspended")
        except Exception as e:
            print(f"  Warning: could not suspend task ({e})")

    # Final JSON write
    actual = _write_json(results_data, json_path)
    if actual != json_path:
        json_path = actual
        md_path = actual.parent / md_path.name

    # Generate Markdown report
    _generate_markdown(results_data, md_path)

    # Persist to Snowflake tables for cross-run comparison
    if persist:
        print("Persisting results to Snowflake...")
        try:
            tbl_names = _persist_to_snowflake(
                session, env, results_data,
            )
            print(f"  \u2192 {tbl_names[0]}")
            print(f"  \u2192 {tbl_names[1]}")
        except Exception as exc:
            print(
                "  Warning: could not persist "
                f"to Snowflake ({exc})"
            )

    done = results_data["overall"]["steps_completed"]
    dur = results_data["overall"]["total_duration_seconds"]
    tot = results_data["overall"]["total_queries"]
    print(f"\n{banner}")
    print(f"  Run complete: {done}/{len(steps)} steps")
    print(f"  Total duration: {dur:.0f}s")
    print(f"  Total queries:  {tot:,}")
    print(f"  JSON:   {json_path}")
    print(f"  Report: {md_path}")
    print(f"{banner}\n")

    return results_data

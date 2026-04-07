"""
Feature Store Operations Dashboard (Streamlit).

Run locally:
    streamlit run streamlit_app.py

Provides a single-pane view of Feature Store health including
DT status, refresh history (Gantt timeline), feature inventory,
pipeline latency, and OFT serving benchmark history.
"""

import time
import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="Feature Store Ops", layout="wide")

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
except Exception:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from feature_definitions.config import get_session, ROLES
    session = get_session(role=ROLES["admin"])

# ---------------------------------------------------------------------------
# Configuration sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Configuration")
database = st.sidebar.text_input("Database", value="FEATURE_STORE_DEMO_DEV")
fs_schema = st.sidebar.text_input("Feature Store Schema", value="FEATURE_STORE")
warehouse = st.sidebar.text_input("Warehouse", value="FS_DEV_WH")

session.sql(
    f"USE WAREHOUSE {warehouse}"
).collect()

st.sidebar.divider()
st.sidebar.subheader("Refresh")
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=False)
refresh_interval = st.sidebar.select_slider(
    "Interval (sec)", options=[15, 30, 60, 120, 300], value=60,
    disabled=not auto_refresh,
)
if st.sidebar.button("Refresh Now"):
    st.rerun()

# ---------------------------------------------------------------------------
# Account timestamp header
# ---------------------------------------------------------------------------
acct_ts = session.sql(
    "SELECT CURRENT_TIMESTAMP() AS TS, CURRENT_DATE() AS DT"
).collect()[0]
st.title("Feature Store Operations Dashboard")

hdr1, hdr2 = st.columns([3, 1])
with hdr2:
    st.caption(f"Account time: **{acct_ts['TS'].strftime('%Y-%m-%d %H:%M:%S %Z')}**")

# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "DT Health", "Refresh Timeline", "Feature Inventory",
    "Datasets & Models", "Pipeline Latency", "Serving Benchmark",
])

# =========================================================================
# Tab 1: DT Health
# =========================================================================
with tab1:
    st.header("Dynamic Table Status")

    try:
        dt_rows = session.sql(f"""
            SHOW DYNAMIC TABLES IN SCHEMA {database}.{fs_schema}
        """).collect()
        dt_data = []
        for r in dt_rows:
            d = r.as_dict()
            dt_data.append({
                "NAME": d["name"],
                "REFRESH_MODE": d.get("refresh_mode", "N/A"),
                "SCHEDULING_STATE": d.get(
                    "scheduling_state", "UNKNOWN"
                ),
                "TARGET_LAG": d.get("target_lag", "N/A"),
                "WAREHOUSE": d.get("warehouse", "N/A"),
            })
        dt_df = pd.DataFrame(dt_data)

        if len(dt_df) > 0:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total DTs", len(dt_df))
            active = len(dt_df[dt_df["SCHEDULING_STATE"] == "ACTIVE"])
            col2.metric("Active", active)
            suspended = len(dt_df[dt_df["SCHEDULING_STATE"] != "ACTIVE"])
            col3.metric("Suspended / Other", suspended)
            st.dataframe(dt_df, use_container_width=True)
        else:
            st.info("No Dynamic Tables found.")
    except Exception as e:
        st.error(f"Error querying DTs: {e}")

# =========================================================================
# Tab 2: Refresh Timeline (Gantt chart + history table)
# =========================================================================
with tab2:
    st.header("DT Refresh Timeline")

    hours = st.slider("Lookback (hours)", 1, 168, 2, key="timeline_hours")
    try:
        hist = session.sql(f"""
            SELECT
                NAME,
                STATE,
                REFRESH_ACTION,
                REFRESH_START_TIME,
                REFRESH_END_TIME,
                DATEDIFF('second', REFRESH_START_TIME, REFRESH_END_TIME)
                    AS DURATION_SEC,
                STATISTICS:numInsertedRows::INT AS INSERTED,
                STATISTICS:numDeletedRows::INT  AS DELETED
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
                NAME_PREFIX => '{database}.{fs_schema}.'
            ))
            WHERE REFRESH_START_TIME >= DATEADD('hour', -{hours},
                                                CURRENT_TIMESTAMP())
            ORDER BY REFRESH_START_TIME DESC
            LIMIT 500
        """).to_pandas()

        if len(hist) > 0:
            # Strip the schema prefix for cleaner labels
            hist["SHORT_NAME"] = hist["NAME"].str.replace(
                f"{database}.{fs_schema}.", "", regex=False
            )

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Refreshes", len(hist))
            col2.metric(
                "Incremental",
                len(hist[hist["REFRESH_ACTION"] == "INCREMENTAL"]),
            )
            col3.metric(
                "Full",
                len(hist[hist["REFRESH_ACTION"] == "FULL"]),
            )
            col4.metric(
                "No Data",
                len(hist[hist["REFRESH_ACTION"] == "NO_DATA"]),
            )

            # ----- Gantt Chart -----
            st.subheader("Refresh Gantt Chart")
            st.caption(
                "Each bar represents a single DT refresh. "
                "Blue = INCREMENTAL, orange = FULL, "
                "gray = NO_DATA (check only, no rows)."
            )

            gantt_df = hist.copy()
            gantt_df["REFRESH_START_TIME"] = pd.to_datetime(
                gantt_df["REFRESH_START_TIME"]
            )
            gantt_df["REFRESH_END_TIME"] = pd.to_datetime(
                gantt_df["REFRESH_END_TIME"]
            )

            color_scale = alt.Scale(
                domain=[
                    "INCREMENTAL", "FULL",
                    "NO_DATA", "INITIALIZE",
                ],
                range=[
                    "#1f77b4", "#ff7f0e",
                    "#cccccc", "#2ca02c",
                ],
            )

            n_fvs = len(
                gantt_df["SHORT_NAME"].unique()
            )
            gantt = (
                alt.Chart(gantt_df)
                .mark_bar(cornerRadiusEnd=2)
                .encode(
                    x=alt.X(
                        "REFRESH_START_TIME:T",
                        title="Time",
                        axis=alt.Axis(format="%H:%M"),
                    ),
                    x2="REFRESH_END_TIME:T",
                    y=alt.Y(
                        "SHORT_NAME:N",
                        title="Feature View",
                        sort=alt.EncodingSortField(
                            field="SHORT_NAME",
                            order="ascending",
                        ),
                    ),
                    color=alt.Color(
                        "REFRESH_ACTION:N",
                        title="Action",
                        scale=color_scale,
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "SHORT_NAME:N", title="FV"
                        ),
                        alt.Tooltip(
                            "REFRESH_ACTION:N",
                            title="Action",
                        ),
                        alt.Tooltip(
                            "REFRESH_START_TIME:T",
                            title="Start",
                            format="%H:%M:%S",
                        ),
                        alt.Tooltip(
                            "REFRESH_END_TIME:T",
                            title="End",
                            format="%H:%M:%S",
                        ),
                        alt.Tooltip(
                            "DURATION_SEC:Q",
                            title="Duration (s)",
                        ),
                        alt.Tooltip(
                            "INSERTED:Q",
                            title="Rows Inserted",
                        ),
                    ],
                )
                .properties(
                    height=max(250, n_fvs * 45)
                )
            )
            st.altair_chart(
                gantt, use_container_width=True
            )

            # ----- Refresh Duration Distribution -----
            st.subheader("Avg Refresh Duration by FV")
            dur_df = (
                hist[hist["REFRESH_ACTION"] != "NO_DATA"]
                .groupby("SHORT_NAME")["DURATION_SEC"]
                .agg(["mean", "max", "count"])
                .reset_index()
                .rename(columns={
                    "SHORT_NAME": "Feature View",
                    "mean": "Avg (sec)",
                    "max": "Max (sec)",
                    "count": "Refreshes",
                })
            )
            if len(dur_df) > 0:
                st.dataframe(dur_df, use_container_width=True)
                st.bar_chart(dur_df.set_index("Feature View")["Avg (sec)"])

            # ----- Raw table -----
            with st.expander("Raw Refresh History"):
                st.dataframe(hist, use_container_width=True)
        else:
            st.info(f"No refreshes in the last {hours} hours.")
    except Exception as e:
        st.error(f"Error querying refresh history: {e}")

# =========================================================================
# Tab 3: Feature Inventory
# =========================================================================
with tab3:
    st.header("Feature View Inventory")

    try:
        from snowflake.ml.feature_store import FeatureStore, CreationMode
        fs = FeatureStore(
            session=session, database=database, name=fs_schema,
            default_warehouse=warehouse,
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        )
        fvs = fs.list_feature_views().to_pandas()

        col1, col2 = st.columns(2)
        col1.metric("Feature Views", len(fvs))
        col2.metric("Entities", fs.list_entities().count())

        st.dataframe(fvs, use_container_width=True)

        st.subheader("Feature Views by Type")
        fvs["TYPE"] = fvs["REFRESH_FREQ"].apply(
            lambda x: "View" if pd.isna(x) or x == "None" else "DT/Tiled"
        )
        st.bar_chart(fvs["TYPE"].value_counts())
    except Exception as e:
        st.error(f"Error: {e}")

# =========================================================================
# Tab 4: Datasets & Models
# =========================================================================
with tab4:
    st.header("Training Datasets & Models")

    st.subheader("Datasets")
    try:
        datasets = session.sql(
            f"SHOW DATASETS IN SCHEMA {database}.{fs_schema}"
        ).to_pandas()
        if len(datasets) > 0:
            st.dataframe(
                datasets[["name", "created_on"]], use_container_width=True
            )
        else:
            st.info("No datasets found.")
    except Exception as e:
        st.warning(f"Dataset listing: {e}")

    st.subheader("Model Registry")
    try:
        from snowflake.ml.registry import Registry
        ml_schema = st.sidebar.text_input("ML Schema", value="ML_DATASETS")
        registry = Registry(
            session=session, database_name=database, schema_name=ml_schema,
        )
        models = registry.show_models()
        if len(models) > 0:
            for _, m in models.iterrows():
                model = registry.get_model(m["name"])
                versions = model.show_versions()
                st.write(f"**{m['name']}** – {len(versions)} version(s)")
                st.dataframe(
                    versions[["name", "created_on"]], use_container_width=True
                )
        else:
            st.info("No models in registry.")
    except Exception as e:
        st.warning(f"Model registry: {e}")

# =========================================================================
# Tab 5: Pipeline Latency
# =========================================================================
with tab5:
    st.header("Pipeline Latency")

    admin_schema = st.sidebar.text_input(
        "Admin Schema", value="CLICKSTREAM_ADMIN"
    )
    source_schema = st.sidebar.text_input(
        "Source Schema", value="CLICKSTREAM_DATA"
    )

    # --- Source table freshness ---
    st.subheader("Source Table Freshness (ROW_TIMESTAMP)")
    try:
        source_tables = ["SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"]
        source_data = []
        for table in source_tables:
            try:
                row = session.sql(f"""
                    SELECT
                        MAX(METADATA$ROW_LAST_COMMIT_TIME) AS LAST_COMMIT,
                        TIMESTAMPDIFF('SECOND',
                            MAX(METADATA$ROW_LAST_COMMIT_TIME),
                            CURRENT_TIMESTAMP()) AS AGE_SEC
                    FROM {database}.{source_schema}.{table}
                """).collect()[0]
                source_data.append({
                    "Table": table,
                    "Last Commit": row["LAST_COMMIT"],
                    "Age (sec)": row["AGE_SEC"],
                })
            except Exception:
                source_data.append({
                    "Table": table, "Last Commit": None, "Age (sec)": None,
                })
        src_df = pd.DataFrame(source_data)
        st.dataframe(src_df, use_container_width=True)
    except Exception as e:
        st.warning(f"Source freshness: {e}")

    # --- DT Feature View freshness ---
    st.subheader("DT Feature View Freshness (ROW_TIMESTAMP)")
    try:
        dt_list = session.sql(
            f"SHOW DYNAMIC TABLES IN SCHEMA {database}.{fs_schema}"
        ).collect()
        dt_fresh = []
        for r in dt_list:
            d = r.as_dict()
            dt_name = d["name"]
            try:
                row = session.sql(f"""
                    SELECT
                        MAX(METADATA$ROW_LAST_COMMIT_TIME) AS LAST_COMMIT,
                        TIMESTAMPDIFF('SECOND',
                            MAX(METADATA$ROW_LAST_COMMIT_TIME),
                            CURRENT_TIMESTAMP()) AS AGE_SEC
                    FROM {database}.{fs_schema}."{dt_name}"
                """).collect()[0]
                dt_fresh.append({
                    "Feature View": dt_name,
                    "Last Commit": row["LAST_COMMIT"],
                    "Age (sec)": row["AGE_SEC"],
                })
            except Exception:
                dt_fresh.append({
                    "Feature View": dt_name,
                    "Last Commit": None,
                    "Age (sec)": None,
                })
        dt_df = pd.DataFrame(dt_fresh)
        if len(dt_df) > 0:
            col1, col2 = st.columns(2)
            valid = dt_df[dt_df["Age (sec)"].notna()]
            if len(valid) > 0:
                col1.metric("Freshest DT", f"{valid['Age (sec)'].min():.0f}s")
                col2.metric("Stalest DT", f"{valid['Age (sec)'].max():.0f}s")
            st.dataframe(dt_df, use_container_width=True)

            if len(valid) > 0:
                st.bar_chart(valid.set_index("Feature View")["Age (sec)"])
    except Exception as e:
        st.warning(f"DT freshness: {e}")

    # --- OFT freshness ---
    st.subheader("Online Feature Table Freshness")
    st.caption(
        "DT last refresh derived from ROW_TIMESTAMP. "
        "OFT sync checked via latest-key presence."
    )
    try:
        from snowflake.ml.feature_store import FeatureStore as FS2
        from snowflake.ml.feature_store import CreationMode as CM2
        from datetime import datetime as dt_mod, timezone

        fs2 = FS2(
            session=session, database=database, name=fs_schema,
            default_warehouse=warehouse, creation_mode=CM2.CREATE_IF_NOT_EXIST,
        )

        oft_specs = [
            {
                "name": "SESSION_BEHAVIOR_FEATURES", "ver": "V01",
                "entity_key": "SESSION_ID", "strategy": "max_key",
            },
            {
                "name": "USER_RECENCY_RAW", "ver": "V01",
                "entity_key": "USER_ID", "strategy": "max_key",
            },
        ]
        oft_data = []
        for spec in oft_specs:
            fv_name = spec["name"]
            ver = spec["ver"]
            entry = {"Feature View": fv_name}

            fqn = f'{database}.{fs_schema}."{fv_name}${ver}"'
            try:
                dt_row = session.sql(f"""
                    SELECT MAX(METADATA$ROW_LAST_COMMIT_TIME) AS TS
                    FROM {fqn}
                """).collect()[0]
                entry["DT Last Refresh"] = dt_row["TS"]
                if dt_row["TS"]:
                    now = dt_mod.now(timezone.utc)
                    dt_utc = (
                        dt_row["TS"].astimezone(timezone.utc)
                        if hasattr(dt_row["TS"], "astimezone")
                        else dt_row["TS"]
                    )
                    entry["DT Age (sec)"] = round(
                        (now - dt_utc).total_seconds(), 1
                    )
            except Exception:
                entry["DT Last Refresh"] = None

            if spec["strategy"] == "max_key":
                try:
                    mk = session.sql(f"""
                        SELECT MAX({spec['entity_key']}) AS MK FROM {fqn}
                    """).collect()[0]["MK"]
                    fv_obj = fs2.get_feature_view(fv_name, ver)
                    rows = fs2.read_feature_view(
                        fv_obj, keys=[[mk]], store_type="online"
                    ).collect()
                    entry["OFT Synced"] = bool(rows and len(rows) > 0)
                    entry["DT Max Key"] = mk
                except Exception as e:
                    entry["OFT Synced"] = False
                    entry["OFT Error"] = str(e)[:100]

            oft_data.append(entry)

        oft_df = pd.DataFrame(oft_data)
        st.dataframe(oft_df, use_container_width=True)
    except Exception as e:
        st.warning(f"OFT freshness: {e}")

    # --- Generator batch log ---
    st.subheader("Generator Batch Log")
    try:
        batch_rows = session.sql(f"""
            SELECT LOG_ID, BATCH_TS, SESSIONS_GENERATED, EVENTS_GENERATED,
                   ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS,
                   STATUS
            FROM {database}.{admin_schema}.GENERATION_LOG
            ORDER BY LOG_ID DESC
            LIMIT 20
        """).to_pandas()
        if len(batch_rows) > 0:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Batches", len(batch_rows))
            col2.metric(
                "Avg Duration (ms)",
                f"{batch_rows['DURATION_MS'].mean():.0f}",
            )
            col3.metric(
                "Total Sessions",
                f"{batch_rows['SESSIONS_GENERATED'].sum():,}",
            )
            st.dataframe(batch_rows, use_container_width=True)

            st.subheader("Batch Volume Over Time")
            st.bar_chart(
                batch_rows.set_index("LOG_ID")[
                    ["SESSIONS_GENERATED", "ORDERS_GENERATED"]
                ]
            )
        else:
            st.info(
                "No generator batches recorded. "
                "Run Notebook 05 to deploy the generator."
            )
    except Exception:
        st.info(
            "Generator not deployed yet. "
            "Run Notebook 05 to create the admin tables."
        )

# =========================================================================
# Tab 6: Serving Benchmark
# =========================================================================
with tab6:
    st.header("OFT Serving Benchmark")

    # ----- Historical benchmark runs from Snowflake tables -----
    st.subheader("Benchmark Run History")
    st.caption(
        "Results persisted to Snowflake tables by the benchmark orchestrator "
        "(Notebook 05b or local runner). Auto-updates on refresh."
    )

    try:
        runs_tbl = f"{database}.{fs_schema}.BENCHMARK_RUNS"
        runs_df = session.sql(f"""
            SELECT
                RUN_ID, RUN_TS, TOTAL_STEPS, TOTAL_QUERIES,
                TOTAL_DURATION_S, STATUS
            FROM {runs_tbl}
            ORDER BY RUN_TS DESC
            LIMIT 20
        """).to_pandas()

        if len(runs_df) > 0:
            st.dataframe(runs_df, use_container_width=True)

            # Per-step detail for selected run
            selected_run = st.selectbox(
                "Select a run to inspect steps",
                runs_df["RUN_ID"].tolist(),
            )

            if selected_run:
                steps_tbl = f"{database}.{fs_schema}.BENCHMARK_STEPS"
                steps_df = session.sql(f"""
                    SELECT
                        STEP_INDEX, STEP_NAME, DURATION_MINUTES,
                        TOTAL_QUERIES, QPM, ERRORS,
                        P50_MS, P90_MS, P95_MS, P99_MS,
                        THREADS, MAX_CLUSTERS,
                        DT_REFRESH_COUNT, DT_INCR_COUNT,
                        DT_REFRESH_P50_S, DT_REFRESH_P90_S,
                        DT_REFRESH_MAX_S,
                        BATCH_COUNT, TOTAL_EVENTS
                    FROM {steps_tbl}
                    WHERE RUN_ID = '{selected_run}'
                    ORDER BY STEP_INDEX
                """).to_pandas()

                if len(steps_df) > 0:
                    st.subheader(f"Steps for {selected_run}")
                    st.dataframe(steps_df, use_container_width=True)

                    # QPM across steps
                    if "QPM" in steps_df.columns:
                        st.subheader("QPM Across Steps")
                        step_order = list(steps_df["STEP_NAME"])
                        qpm_chart = (
                            alt.Chart(steps_df)
                            .mark_bar()
                            .encode(
                                x=alt.X(
                                    "STEP_NAME:N",
                                    title="Step",
                                    sort=step_order,
                                ),
                                y=alt.Y(
                                    "QPM:Q",
                                    title="Queries Per Minute",
                                ),
                                color="STEP_NAME:N",
                                tooltip=[
                                    "STEP_NAME", "QPM",
                                    "THREADS", "MAX_CLUSTERS",
                                ],
                            )
                            .properties(height=300)
                        )
                        st.altair_chart(qpm_chart, use_container_width=True)

                    # Latency across steps
                    lat_cols = [
                        c for c in
                        ["P50_MS", "P90_MS", "P95_MS", "P99_MS"]
                        if c in steps_df.columns
                    ]
                    if lat_cols:
                        st.subheader("Latency Across Steps")
                        lat_melt = steps_df.melt(
                            id_vars=["STEP_NAME"],
                            value_vars=lat_cols,
                            var_name="Percentile",
                            value_name="Latency (ms)",
                        )
                        lat_chart = (
                            alt.Chart(lat_melt)
                            .mark_line(point=True)
                            .encode(
                                x=alt.X(
                                    "STEP_NAME:N",
                                    title="Step",
                                    sort=step_order,
                                ),
                                y=alt.Y("Latency (ms):Q"),
                                color="Percentile:N",
                                tooltip=[
                                    "STEP_NAME",
                                    "Percentile",
                                    "Latency (ms)",
                                ],
                            )
                            .properties(height=300)
                        )
                        st.altair_chart(lat_chart, use_container_width=True)

                    # DT refresh metrics across steps
                    dt_cols = [
                        c for c in [
                            "DT_REFRESH_COUNT",
                            "DT_INCR_COUNT",
                            "DT_REFRESH_P50_S",
                            "DT_REFRESH_MAX_S",
                        ]
                        if c in steps_df.columns
                    ]
                    if dt_cols and steps_df[dt_cols].notna().any().any():
                        st.subheader("DT Refresh Metrics Across Steps")
                        st.dataframe(
                            steps_df[["STEP_NAME"] + dt_cols],
                            use_container_width=True,
                        )
        else:
            st.info("No benchmark runs found in Snowflake tables yet.")
    except Exception:
        st.info(
            "Benchmark tables not created yet. Run the orchestrator "
            "(Notebook 05b) to populate `BENCHMARK_RUNS` / "
            "`BENCHMARK_STEPS`."
        )

    # ----- Interactive benchmark (run from this dashboard) -----
    st.divider()
    st.subheader("Run Ad-Hoc Benchmark")
    st.markdown(
        "Run a one-off concurrent query workload against OFTs from this "
        "dashboard. For multi-step scaled tests, use the orchestrator."
    )

    col_a, col_b, col_c, col_d = st.columns(4)
    bench_duration = col_a.number_input("Duration (sec)", 10, 600, 60)
    bench_threads = col_b.number_input("Threads / cluster", 1, 32, 8)
    bench_clusters = col_c.number_input("Max clusters", 1, 10, 1)
    bench_target_qpm = col_d.number_input(
        "Target QPM (0 = unlimited)", 0, 100000, 0, step=1000,
        help="Rate-limit to this many queries per minute.",
    )

    if st.button("Run Benchmark", type="primary"):
        with st.spinner(
            f"Running {bench_duration}s benchmark with "
            f"{bench_threads * bench_clusters} threads..."
        ):
            try:
                import sys
                sys.path.insert(0, "..")
                from feature_definitions.benchmark import (
                    run_benchmark,
                    BenchmarkConfig,
                )

                bench_cfg = BenchmarkConfig(
                    duration_seconds=int(bench_duration),
                    threads_per_cluster=int(bench_threads),
                    max_clusters=int(bench_clusters),
                    target_qpm=(
                        float(bench_target_qpm)
                        if bench_target_qpm > 0
                        else None
                    ),
                )
                result = run_benchmark(session, "DEV", bench_cfg)

                if result.key_ranges_used:
                    st.caption(
                        "Key ranges auto-discovered from DTs: "
                        + ", ".join(
                            f"**{fv}** {lo:,}–{hi:,}"
                            for fv, (lo, hi)
                            in result.key_ranges_used.items()
                        )
                    )

                pcts = result.percentiles()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("QPM", f"{result.qpm:,.0f}")
                m2.metric("p50", f"{pcts['p50']:.0f}ms")
                m3.metric("p95", f"{pcts['p95']:.0f}ms")
                m4.metric("p99", f"{pcts['p99']:.0f}ms")

                st.markdown(
                    f"**{result.total_queries}** queries in "
                    f"**{result.duration_seconds:.1f}s** "
                    f"({result.total_errors} errors)"
                )

                wins = result.windows()
                if len(wins) > 1:
                    st.subheader("Per-Minute Performance")
                    win_rows = []
                    for w in wins:
                        win_rows.append({
                            "Minute": w.minute,
                            "Queries": w.query_count,
                            "Errors": w.error_count,
                            "QPM": round(w.qpm),
                            "p50 (ms)": round(w.percentiles["p50"], 1),
                            "p90 (ms)": round(w.percentiles["p90"], 1),
                            "p95 (ms)": round(w.percentiles["p95"], 1),
                            "p99 (ms)": round(w.percentiles["p99"], 1),
                        })
                    win_df = pd.DataFrame(win_rows)
                    st.dataframe(win_df, use_container_width=True)
                    st.line_chart(
                        win_df[["Minute", "QPM"]].set_index("Minute"), y="QPM"
                    )
                    st.line_chart(
                        win_df[
                            ["Minute", "p50 (ms)", "p90 (ms)",
                             "p95 (ms)", "p99 (ms)"]
                        ].set_index("Minute")
                    )

                st.subheader("Overall — Per Feature View")
                rows = []
                for fv_name, lats in result.per_fv.items():
                    fp = result.percentiles(lats)
                    rows.append({
                        "Feature View": fv_name,
                        "Queries": len(lats),
                        "p50 (ms)": round(fp["p50"], 1),
                        "p90 (ms)": round(fp["p90"], 1),
                        "p95 (ms)": round(fp["p95"], 1),
                        "p99 (ms)": round(fp["p99"], 1),
                        "min (ms)": round(fp["min"], 1),
                        "max (ms)": round(fp["max"], 1),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

                if len(result.latencies_ms) > 0:
                    st.subheader("Latency Distribution")
                    hist_data = pd.DataFrame(
                        {"Latency (ms)": result.latencies_ms}
                    )
                    st.bar_chart(
                        hist_data["Latency (ms)"]
                        .value_counts(
                            bins=min(
                                50, len(result.latencies_ms) // 2 + 1
                            )
                        )
                        .sort_index()
                    )

            except Exception as e:
                st.error(f"Benchmark failed: {e}")
    else:
        st.info(
            "Click **Run Benchmark** to start. The serving warehouse "
            "`FS_SERVING_WH` must already exist."
        )

# =========================================================================
# Auto-refresh (at end of script so full page renders first)
# =========================================================================
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()

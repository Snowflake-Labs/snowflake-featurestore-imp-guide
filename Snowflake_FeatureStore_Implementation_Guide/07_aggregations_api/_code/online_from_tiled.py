"""
Helper to derive a non-tiled, OFT-ready FeatureView from a tiled FeatureView.

The Aggregations API's tiled Feature Views cannot source a Hybrid Table
Online Feature Table directly (the tiled DT schema has _PARTIAL_* columns,
no original timestamp_col, and View-based alternatives fail because Snowflake
Streams do not support change tracking on queries with GROUP BY).

This module provides ``online_fv_from_tiled()`` which introspects a tiled
FeatureView's ``Feature`` definitions, entity keys, source query, and
timestamp column, then generates a standard GROUP BY query scoped to only
the maximum window needed.  The result is a new FeatureView with
``online_config`` enabled and a ``refresh_freq`` suitable for DT-based
online serving.

Canonical environment: database FEATURE_STORE_DEMO, Feature Store schema
FEATURE_STORE, source schema CLICKSTREAM_DATA, warehouse FS_DEV_WH.

Tested in: tests/test_online_from_tiled.py
"""

from __future__ import annotations

import re
from typing import Optional

from snowflake.snowpark import Session
from snowflake.ml.feature_store import Entity, FeatureView, Feature, feature_view as fv_mod

# ── AggregationType → Snowflake SQL function name ────────────────────

_AGG_SQL_MAP: dict[str, str] = {
    "SUM": "SUM",
    "COUNT": "COUNT",
    "AVG": "AVG",
    "MIN": "MIN",
    "MAX": "MAX",
    "STD": "STDDEV",
    "VAR": "VARIANCE",
    "APPROX_COUNT_DISTINCT": "APPROX_COUNT_DISTINCT",
}

_UNSUPPORTED_AGGS = frozenset({
    "FIRST_N", "LAST_N", "FIRST_DISTINCT_N", "LAST_DISTINCT_N",
    "APPROX_PERCENTILE",
})


# ── Window / offset parsing ──────────────────────────────────────────

def _parse_duration_to_hours(dur: str) -> int:
    """Convert a Feature window/offset string like '7d' or '6h' to hours."""
    m = re.match(r"^(\d+)(h|d)$", dur.strip())
    if not m:
        raise ValueError(
            f"Cannot parse duration string {dur!r}. "
            f"Expected format like '7d' or '6h'."
        )
    val, unit = int(m.group(1)), m.group(2)
    return val if unit == "h" else val * 24


def _hours_to_dateadd(hours: int) -> str:
    """Convert hours to the most readable DATEADD unit+value pair."""
    if hours % 24 == 0 and hours >= 24:
        return f"DATEADD('DAY', -{hours // 24}, CURRENT_TIMESTAMP())"
    return f"DATEADD('HOUR', -{hours}, CURRENT_TIMESTAMP())"


# ── Core helper ──────────────────────────────────────────────────────

def online_fv_from_tiled(
    tiled_fv: FeatureView,
    session: Session,
    *,
    source_query: Optional[str] = None,
    name_suffix: str = "_ONLINE",
    refresh_freq: str = "1 minute",
    target_lag: str = "1 minute",
    window_buffer: str = "1d",
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Derive a non-tiled, OFT-ready FeatureView from a tiled FeatureView.

    Introspects the tiled FV's Feature definitions and generates a standard
    GROUP BY query scoped to only the data needed for current-value
    aggregation (max_window + offset + buffer).

    Parameters
    ----------
    tiled_fv : FeatureView
        A tiled FeatureView (``is_tiled == True``).  Works best with a
        **draft** (pre-registration) FV whose ``.query`` still points at the
        original source table.  For a registered FV, the internal query has
        been rewritten to the tiled form — pass ``source_query`` explicitly.
    session : Session
        Active Snowpark session (needed to create the feature_df DataFrame).
    source_query : str or None
        SQL that selects from the original source table (e.g.,
        ``"SELECT * FROM db.schema.ORDERS"``).  Required when ``tiled_fv``
        is a registered FV (whose ``.query`` has been transformed to the
        tiled DT query).  Optional for draft FVs.
    name_suffix : str
        Appended to ``tiled_fv.name`` to form the online FV's name.
    refresh_freq : str
        Refresh frequency for the online DT (default ``"1 minute"``).
    target_lag : str
        OFT target_lag for the Hybrid Table sync (default ``"1 minute"``).
    window_buffer : str
        Extra time added beyond the max window+offset to avoid edge-case
        data loss at window boundaries (default ``"1d"``).
    desc : str or None
        Description for the online FV.  If None, auto-generated.

    Returns
    -------
    FeatureView
        A non-tiled FeatureView with ``online_config`` enabled, ready for
        ``fs.register_feature_view(..., version="V01", block=True)``.

    Raises
    ------
    ValueError
        If the source FV is not tiled, has no aggregation specs, uses
        unsupported aggregation types, or is a registered FV without
        ``source_query``.

    Notes
    -----
    The generated query uses ``CURRENT_TIMESTAMP()`` in the WHERE clause to
    scope data to the maximum window.  This forces the resulting DT to use
    **FULL refresh** rather than incremental.  Because the data volume is
    bounded by the window size, this is typically fast and cheap.
    """
    # ── Validate input ───────────────────────────────────────────────
    if not tiled_fv.is_tiled:
        raise ValueError(
            f"FeatureView {tiled_fv.name!s} is not tiled. "
            f"This helper is only needed for tiled Feature Views."
        )

    agg_specs = tiled_fv.aggregation_specs
    if not agg_specs:
        raise ValueError(
            f"FeatureView {tiled_fv.name!s} has no aggregation_specs."
        )

    # ── Extract metadata ─────────────────────────────────────────────
    entities: list[Entity] = list(tiled_fv.entities)
    join_keys: list[str] = []
    for ent in entities:
        join_keys.extend(ent.join_keys)

    ts_col: str = str(tiled_fv.timestamp_col)
    online_ts_alias = f"LAST_{ts_col}"

    # Resolve the source query.  A draft FV's .query points at the
    # original source table.  A registered tiled FV's .query has been
    # rewritten to the tiled DT form (TIME_SLICE, _PARTIAL_* columns)
    # which no longer contains the original timestamp column.
    fv_query = tiled_fv.query
    _is_tiled_query = "_PARTIAL_" in fv_query or "TIME_SLICE" in fv_query

    if source_query is not None:
        resolved_source = source_query
    elif _is_tiled_query:
        raise ValueError(
            f"FeatureView {tiled_fv.name!s} appears to be a registered tiled FV "
            f"whose query has been rewritten to the tiled form. Pass the "
            f"original source query via source_query=, e.g. "
            f"source_query='SELECT * FROM db.schema.ORDERS'."
        )
    else:
        resolved_source = fv_query

    # ── Build SELECT expressions and compute max window ──────────────
    select_exprs: list[str] = []
    max_scope_hours = 0

    for spec in agg_specs:
        agg_name = spec.function.name
        if agg_name in _UNSUPPORTED_AGGS:
            raise ValueError(
                f"Aggregation type {agg_name} (feature {spec.output_column!r}) "
                f"cannot be expressed as a simple GROUP BY. "
                f"Remove it or handle this feature separately."
            )

        sql_func = _AGG_SQL_MAP.get(agg_name)
        if sql_func is None:
            raise ValueError(
                f"Unknown aggregation type {agg_name} for feature "
                f"{spec.output_column!r}. Supported: {sorted(_AGG_SQL_MAP)}."
            )

        col = spec.source_column
        alias = spec.output_column
        window = spec.window
        offset = spec.offset

        # WHERE scoping needs the widest reach across all features
        window_hours = _parse_duration_to_hours(window)
        offset_hours = _parse_duration_to_hours(offset) if offset and offset != "0" else 0
        max_scope_hours = max(max_scope_hours, window_hours + offset_hours)

        # For scoped current-value aggregation, we apply the window filter
        # per-feature using a CASE WHEN so that each feature only aggregates
        # rows within its own window (+ offset).  This lets features with
        # different windows coexist in a single GROUP BY.
        total_lookback = window_hours + offset_hours
        if offset_hours > 0:
            # Window is [now - offset - window, now - offset)
            lower = _hours_to_dateadd(total_lookback)
            upper = _hours_to_dateadd(offset_hours)
            case_filter = f"{ts_col} >= {lower} AND {ts_col} < {upper}"
        else:
            lower = _hours_to_dateadd(window_hours)
            case_filter = f"{ts_col} >= {lower}"

        select_exprs.append(
            f"{sql_func}(CASE WHEN {case_filter} THEN {col} END) AS {alias}"
        )

    # ── Add buffer to the max scope ──────────────────────────────────
    buffer_hours = _parse_duration_to_hours(window_buffer)
    scope_hours = max_scope_hours + buffer_hours

    # ── Assemble SQL ─────────────────────────────────────────────────
    group_cols = ", ".join(join_keys)
    select_cols = ",\n            ".join(
        [f"{k}" for k in join_keys]
        + select_exprs
        + [f"MAX({ts_col}) AS {online_ts_alias}"]
    )
    where_clause = f"{ts_col} >= {_hours_to_dateadd(scope_hours)}"

    sql = f"""
        SELECT
            {select_cols}
        FROM ({resolved_source})
        WHERE {where_clause}
        GROUP BY {group_cols}
    """

    feature_df = session.sql(sql)

    # ── Build the online FeatureView ─────────────────────────────────
    online_name = f"{tiled_fv.name!s}{name_suffix}"
    if desc is None:
        desc = (
            f"Auto-generated online companion for tiled FV {tiled_fv.name!s}. "
            f"Non-tiled GROUP BY scoped to {scope_hours}h of source data."
        )

    online_config = fv_mod.OnlineConfig(enable=True, target_lag=target_lag)

    return FeatureView(
        name=online_name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=online_ts_alias,
        refresh_freq=refresh_freq,
        refresh_mode="AUTO",
        online_config=online_config,
        desc=desc,
    )


def online_sql_from_features(
    features: list[Feature],
    *,
    join_keys: list[str],
    source_table: str,
    timestamp_col: str,
    window_buffer: str = "1d",
) -> str:
    """
    Generate the raw SQL for a non-tiled online aggregation query.

    Useful when you want to inspect or customise the SQL before creating
    a FeatureView.

    Parameters
    ----------
    features : list[Feature]
        The same Feature definitions used for the tiled FV.
    join_keys : list[str]
        Entity key column(s), e.g. ``["USER_ID"]``.
    source_table : str
        Fully-qualified source table name.
    timestamp_col : str
        Timestamp column in the source table.
    window_buffer : str
        Extra time beyond max window (default ``"1d"``).

    Returns
    -------
    str
        A complete SQL SELECT statement.
    """
    select_exprs: list[str] = []
    max_scope_hours = 0

    for f in features:
        agg_name = f._function.name
        if agg_name in _UNSUPPORTED_AGGS:
            raise ValueError(
                f"Aggregation type {agg_name} ({f._alias!r}) cannot be "
                f"expressed as a simple GROUP BY."
            )

        sql_func = _AGG_SQL_MAP.get(agg_name)
        if sql_func is None:
            raise ValueError(f"Unknown aggregation type {agg_name}.")

        window_hours = _parse_duration_to_hours(f._window)
        offset_hours = (
            _parse_duration_to_hours(f._offset) if f._offset and f._offset != "0" else 0
        )
        max_scope_hours = max(max_scope_hours, window_hours + offset_hours)

        total_lookback = window_hours + offset_hours
        if offset_hours > 0:
            lower = _hours_to_dateadd(total_lookback)
            upper = _hours_to_dateadd(offset_hours)
            case_filter = f"{timestamp_col} >= {lower} AND {timestamp_col} < {upper}"
        else:
            lower = _hours_to_dateadd(window_hours)
            case_filter = f"{timestamp_col} >= {lower}"

        select_exprs.append(
            f"    {sql_func}(CASE WHEN {case_filter} THEN {f._column} END) AS {f._alias}"
        )

    buffer_hours = _parse_duration_to_hours(window_buffer)
    scope_hours = max_scope_hours + buffer_hours

    group_cols = ", ".join(join_keys)
    key_cols = ",\n".join(f"    {k}" for k in join_keys)
    feature_lines = ",\n".join(select_exprs)
    ts_line = f"    MAX({timestamp_col}) AS LAST_{timestamp_col}"
    where_clause = f"{timestamp_col} >= {_hours_to_dateadd(scope_hours)}"

    return (
        f"SELECT\n{key_cols},\n{feature_lines},\n{ts_line}\n"
        f"FROM {source_table}\n"
        f"WHERE {where_clause}\n"
        f"GROUP BY {group_cols}"
    )


if __name__ == "__main__":
    from snowflake.ml.feature_store import Feature

    features = [
        Feature.sum("TOTAL_AMT", "7d").alias("TOTAL_AMT_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("TOTAL_AMT_SUM_30D"),
        Feature.count("ORDER_ID", "7d").alias("ORDER_ID_CNT_7D"),
        Feature.avg("TOTAL_AMT", "7d").alias("TOTAL_AMT_AVG_7D"),
        Feature.min("TOTAL_AMT", "30d").alias("TOTAL_AMT_MIN_30D"),
        Feature.max("TOTAL_AMT", "30d").alias("TOTAL_AMT_MAX_30D"),
    ]

    sql = online_sql_from_features(
        features,
        join_keys=["USER_ID"],
        source_table="FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS",
        timestamp_col="ORDER_TS",
    )
    print("Generated SQL:")
    print(sql)

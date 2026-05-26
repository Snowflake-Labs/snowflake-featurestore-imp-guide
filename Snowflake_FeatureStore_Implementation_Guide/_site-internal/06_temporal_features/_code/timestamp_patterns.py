"""
timestamp_col patterns for Feature Views (clickstream + orders).

The timestamp_col drives ASOF joins at retrieval time. Choose semantics that match
how you want “as of” to behave (event time vs snapshot time).

Canonical source tables:
- EVENTS: EVENT_TS, EVENT_ID, USER_ID, PRODUCT_ID, EVENT_TYPE, EVENT_NAME
- ORDERS: ORDER_TS, TOTAL_AMT, USER_ID
- SESSIONS: SESSION_START_TS, SESSION_END_TS, IS_CONVERTED

Tested in: tests/test_chapter_06.py
"""
from snowflake.snowpark import Session
from snowflake.snowpark import functions as F
from snowflake.ml.feature_store import Entity, FeatureView

DATABASE = "FEATURE_STORE_DEMO"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"


def fq_table(table: str) -> str:
    return f"{DATABASE}.{SOURCE_SCHEMA}.{table}"


def build_user_event_stats_fv(
    session: Session,
    user_entity: Entity,
    events_table: str | None = None,
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Pattern 1: Last event timestamp (common for streaming-style aggregates).

    timestamp_col = LAST_EVENT_TS (max EVENT_TS per user from EVENTS).
    """
    tbl = events_table or fq_table("EVENTS")
    feature_df = (
        session.table(tbl)
        .group_by("USER_ID")
        .agg(
            F.count("EVENT_ID").alias("EVENT_CNT"),
            F.count_distinct("PRODUCT_ID").alias("PRODUCT_DISTINCT_CNT"),
            F.max("EVENT_TS").alias("LAST_EVENT_TS"),
        )
    )
    return FeatureView(
        name="USER_EVENT_STATS",
        entities=[user_entity],
        feature_df=feature_df,
        timestamp_col="LAST_EVENT_TS",
        refresh_freq=refresh_freq,
        desc="User aggregates from EVENTS; PIT via LAST_EVENT_TS",
    )


def build_user_order_stats_fv(
    session: Session,
    user_entity: Entity,
    orders_table: str | None = None,
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Pattern 2: Purchase aggregates with ORDER_TS-derived feature validity.

    Uses TOTAL_AMT and ORDER_TS from ORDERS; suffix conventions _SUM, _CNT, _AVG, _TS.
    """
    tbl = orders_table or fq_table("ORDERS")
    feature_df = (
        session.table(tbl)
        .group_by("USER_ID")
        .agg(
            F.sum("TOTAL_AMT").alias("ORDER_TOTAL_SUM"),
            F.count("ORDER_TS").alias("ORDER_CNT"),
            F.avg("TOTAL_AMT").alias("ORDER_TOTAL_AVG"),
            F.max("ORDER_TS").alias("LAST_ORDER_TS"),
        )
    )
    return FeatureView(
        name="USER_ORDER_STATS",
        entities=[user_entity],
        feature_df=feature_df,
        timestamp_col="LAST_ORDER_TS",
        refresh_freq=refresh_freq,
        desc="User order totals from ORDERS; PIT via LAST_ORDER_TS",
    )


def build_user_daily_snapshot_fv(
    session: Session,
    user_entity: Entity,
    snapshot_table_fq: str,
    refresh_freq: str | None = None,
) -> FeatureView:
    """
    Pattern 3: Periodic snapshot table — timestamp_col is the snapshot grain (e.g. daily).

    snapshot_table_fq must expose USER_ID, SNAPSHOT_TS, and feature columns.
    Omit refresh_freq (pass None) for a View-backed Feature View if the snapshot is a view.
    """
    params: dict = {
        "name": "USER_DAILY_SNAPSHOT",
        "entities": [user_entity],
        "feature_df": session.table(snapshot_table_fq),
        "timestamp_col": "SNAPSHOT_TS",
        "desc": "Daily (or periodic) user snapshot features",
    }
    if refresh_freq is not None:
        params["refresh_freq"] = refresh_freq
    return FeatureView(**params)


if __name__ == "__main__":
    print("timestamp_patterns require an active Snowflake session.")
    print(f"Example database.schema: {DATABASE}.{SOURCE_SCHEMA}")

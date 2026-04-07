"""
Point-in-time feature retrieval examples.

This module demonstrates how to:
- Configure Feature Views for temporal retrieval (clickstream EVENTS + SESSIONS spine)
- Generate training datasets with PIT correctness
- Use spine_timestamp_col for ASOF joins

Canonical environment: database FEATURE_STORE_DEMO, clickstream schema CLICKSTREAM_DATA,
Feature Store schema FEATURE_STORE, warehouse FS_DEV_WH.

Tested in: tests/test_chapter_06.py
"""
from snowflake.snowpark import Session, DataFrame
from snowflake.snowpark import functions as F
from snowflake.ml.feature_store import Entity, FeatureView

DATABASE = "FEATURE_STORE_DEMO"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
WAREHOUSE = "FS_DEV_WH"


def fq_table(table: str) -> str:
    """Fully qualified clickstream source table name."""
    return f"{DATABASE}.{SOURCE_SCHEMA}.{table}"


def create_training_spine(
    session: Session,
    sessions_table: str | None = None,
    entity_col: str = "USER_ID",
    timestamp_col: str = "EVENT_TS",
    label_col: str = "LABEL",
) -> DataFrame:
    """
    Create a training spine with entity keys, timestamps, and labels.

    Default source is SESSIONS: point-in-time is session start; label is conversion.

    Args:
        session: Active Snowpark session
        sessions_table: Fully qualified SESSIONS table (default: canonical clickstream)
        entity_col: Column name for entity key in output (always USER_ID from SQL)
        timestamp_col: Alias for spine timestamp column
        label_col: Alias for label column

    Returns:
        DataFrame suitable as training spine for generate_dataset
    """
    tbl = sessions_table or fq_table("SESSIONS")
    return session.sql(f"""
        SELECT
            s.USER_ID AS {entity_col},
            s.SESSION_START_TS AS {timestamp_col},
            s.IS_CONVERTED::NUMBER AS {label_col}
        FROM {tbl} s
        WHERE s.USER_ID IS NOT NULL
    """)


def create_training_spine_from_events(
    session: Session,
    events_table: str | None = None,
) -> DataFrame:
    """
    Alternative spine keyed by user + event time (e.g. modeling at each EVENT_TS).

    Uses EVENTS with EVENT_TS as the point-in-time column and a simple label from EVENT_NAME.
    """
    tbl = events_table or fq_table("EVENTS")
    return session.sql(f"""
        SELECT
            e.USER_ID,
            e.EVENT_TS,
            CASE WHEN e.EVENT_NAME = 'Order Completed' THEN 1 ELSE 0 END AS LABEL
        FROM {tbl} e
        WHERE e.USER_ID IS NOT NULL
    """)


def build_user_event_stats_feature_view(
    session: Session,
    user_entity: Entity,
    events_table: str | None = None,
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Feature View over EVENTS: rolling user aggregates with timestamp_col = last event time.

    ASOF joins use LAST_EVENT_TS so each spine row receives the latest row at or before
    the spine timestamp.
    """
    tbl = events_table or fq_table("EVENTS")
    feature_df = (
        session.table(tbl)
        .group_by("USER_ID")
        .agg(
            F.count("EVENT_ID").alias("EVENT_CNT"),
            F.max("EVENT_TS").alias("LAST_EVENT_TS"),
        )
    )
    return FeatureView(
        name="USER_EVENT_STATS",
        entities=[user_entity],
        feature_df=feature_df,
        timestamp_col="LAST_EVENT_TS",
        refresh_freq=refresh_freq,
        desc="User-level clickstream aggregates from EVENTS",
    )


def create_inference_spine(
    session: Session,
    entity_table: str,
    entity_col: str = "USER_ID",
    use_current_time: bool = True,
) -> DataFrame:
    """
    Create an inference spine for batch scoring.

    Args:
        session: Active Snowpark session
        entity_table: Table containing entities to score (fully qualified if needed)
        entity_col: Column name for entity key
        use_current_time: If True, use current timestamp as EVENT_TS

    Returns:
        DataFrame suitable as inference spine
    """
    spine = session.table(entity_table).select(F.col(entity_col))

    if use_current_time:
        spine = spine.with_column("EVENT_TS", F.current_timestamp())

    return spine


if __name__ == "__main__":
    print("PIT retrieval examples require an active Snowflake session.")

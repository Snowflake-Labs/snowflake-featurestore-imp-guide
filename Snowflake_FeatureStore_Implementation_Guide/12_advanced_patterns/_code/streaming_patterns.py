"""
Streaming feature patterns.

This module demonstrates how to:
- Implement near real-time features
- Work with Snowflake Streams
- Design streaming architectures

Tested in: tests/test_chapter_12.py
"""
from typing import List, Optional

from snowflake.snowpark import Session, DataFrame
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_short_refresh_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_query: str,
    version: str = "v1",
    refresh_freq: str = "1 minute",
    timestamp_col: Optional[str] = None,
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Option 1: Near real-time features via a short-refresh Dynamic Table.

    Creates a FeatureView backed by a Dynamic Table with an aggressive refresh
    interval (e.g. 1 minute). The Dynamic Table engine polls the source query
    on each interval, so feature freshness ≈ refresh_freq.

    Trade-offs:
        - Latency: 1-2 minutes (bounded by refresh_freq)
        - Cost: Higher warehouse compute (frequent refreshes)
        - Complexity: Low (standard FeatureView API)

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        source_query: SQL query that computes features from source tables
        version: Version string
        refresh_freq: How often the Dynamic Table refreshes (default "1 minute")
        timestamp_col: Optional timestamp column for point-in-time correctness
        warehouse: Optional warehouse override for refresh compute
        desc: Optional description

    Returns:
        Registered FeatureView backed by a short-refresh Dynamic Table
    """
    feature_df = session.sql(source_query)

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Near real-time features (refresh_freq={refresh_freq})",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Short-refresh FeatureView created: {name}/{version}")
    print(f"  refresh_freq={refresh_freq}, latency≈1-2 min")
    return registered_fv


def create_external_streaming_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    staging_table: str,
    feature_columns: List[str],
    entity_columns: List[str],
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Option 2: Sub-second features via external streaming into a staging table.

    Architecture:
        Kafka / Kinesis → Snowpipe Streaming → STAGING_TABLE → View-based FV

    The external pipeline (Kafka + Snowpipe Streaming, or Kinesis + Snowpipe)
    lands data into a staging table with sub-second latency. The FeatureView
    is created WITHOUT refresh_freq, making it a View-based FeatureView that
    reads directly from the staging table on every query.

    Trade-offs:
        - Latency: Seconds (bounded by external pipeline, not Snowflake)
        - Cost: Variable (Snowpipe ingestion + query-time compute)
        - Complexity: High (requires external streaming infrastructure)

    Prerequisites:
        - A staging table already receiving data from the external pipeline
        - The staging table must contain the entity columns and feature columns
        - Snowpipe or Snowpipe Streaming configured to ingest into the table

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        staging_table: Fully qualified name of the staging table that receives
                       streaming data (e.g. "DB.SCHEMA.EVENTS_STAGING")
        feature_columns: List of feature column names to include
        entity_columns: List of entity/join-key column names
        version: Version string
        timestamp_col: Optional timestamp column for point-in-time correctness
        desc: Optional description

    Returns:
        Registered View-based FeatureView over the streaming staging table
    """
    all_columns = entity_columns + feature_columns
    if timestamp_col and timestamp_col not in all_columns:
        all_columns.append(timestamp_col)
    col_list = ", ".join(all_columns)

    feature_df = session.sql(f"SELECT {col_list} FROM {staging_table}")

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        desc=desc or f"Streaming features from {staging_table} (view-based, no refresh_freq)",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"External streaming FeatureView created: {name}/{version}")
    print(f"  source={staging_table}, latency≈seconds (view-based)")
    return registered_fv


def get_streaming_options() -> dict:
    """
    Get options for implementing streaming features.
    
    Returns:
        Dict with streaming options
    """
    return {
        "short_refresh_dt": {
            "approach": "Dynamic Table with 1-minute refresh",
            "latency": "1-2 minutes",
            "cost": "Higher",
            "complexity": "Low",
            "code": """
                FeatureView(
                    refresh_freq="1 minute",
                    # ...
                )
            """,
        },
        "external_streaming": {
            "approach": "Kafka/Snowpipe → Staging → View FV",
            "latency": "Seconds",
            "cost": "Variable",
            "complexity": "High",
            "code": """
                # External: Kafka → Snowpipe → EVENTS_STAGING
                # FeatureView reads from staging
                FeatureView(
                    feature_df=session.table("EVENTS_STAGING"),
                    # No refresh_freq (View-based)
                )
            """,
        },
        "future_streaming_fv": {
            "approach": "Native Streaming FeatureView (planned)",
            "latency": "Sub-second",
            "cost": "TBD",
            "complexity": "Low",
            "code": """
                # Future API (not yet available)
                FeatureView(
                    source_stream="USER_EVENTS_STREAM",
                    streaming=True,
                )
            """,
        },
    }


if __name__ == "__main__":
    options = get_streaming_options()
    print("Streaming Feature Options:")
    for name, config in options.items():
        print(f"\n{name}:")
        print(f"  Latency: {config['latency']}")
        print(f"  Complexity: {config['complexity']}")

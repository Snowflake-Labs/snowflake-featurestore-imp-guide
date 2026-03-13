"""
External FeatureView patterns.

This module demonstrates how to:
- Integrate Feature Store with dbt-managed tables (external FV)
- Integrate Feature Store with Iceberg storage (Iceberg-backed FV)

Tested in: tests/test_chapter_12.py
"""
from typing import List, Optional

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_dbt_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    dbt_table: str,
    feature_columns: List[str],
    entity_columns: List[str],
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create an external FeatureView backed by a dbt-managed table.

    dbt handles the data transformation and refresh lifecycle. The FeatureView
    is registered WITHOUT refresh_freq, making it a view-based (external)
    FeatureView that reads directly from the dbt output table on every query.

    Architecture:
        Raw Data → dbt Pipeline → Feature Table → External FeatureView (View)

    The Feature Store does NOT manage refresh — dbt does. This is the
    recommended integration pattern per the official Snowflake + dbt guide.

    Trade-offs:
        - Latency: Depends on dbt run schedule
        - Cost: No additional warehouse cost for FV refresh (dbt handles it)
        - Complexity: Medium (requires dbt pipeline + Feature Store registration)

    Prerequisites:
        - A dbt model that materializes the feature table in Snowflake
        - The table must contain entity join-key columns and feature columns
        - dbt must have already run at least once to create the table

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        dbt_table: Fully qualified name of the dbt-managed table
                   (e.g. "ANALYTICS.FEATURES.USER_STATS")
        feature_columns: List of feature column names to include
        entity_columns: List of entity/join-key column names
        version: Version string
        timestamp_col: Optional timestamp column for point-in-time correctness
                       (e.g. dbt's updated_at or a custom timestamp column)
        desc: Optional description

    Returns:
        Registered external (view-based) FeatureView over the dbt table
    """
    all_columns = entity_columns + feature_columns
    if timestamp_col and timestamp_col not in all_columns:
        all_columns.append(timestamp_col)
    col_list = ", ".join(all_columns)

    feature_df = session.sql(f"SELECT {col_list} FROM {dbt_table}")

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        desc=desc or f"External FV backed by dbt table {dbt_table}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"dbt-backed FeatureView created: {name}/{version}")
    print(f"  source={dbt_table}, type=external (view-based)")
    print(f"  Refresh managed by dbt — not by Feature Store")
    return registered_fv


def create_iceberg_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_query: str,
    external_volume: str,
    version: str = "v1",
    refresh_freq: str = "1 day",
    base_location: Optional[str] = None,
    timestamp_col: Optional[str] = None,
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a managed FeatureView that stores output in Iceberg format.

    Uses the FeatureView's storage_config parameter with StorageFormat.ICEBERG
    to persist the feature data as Apache Iceberg tables on an external volume,
    rather than the default Snowflake-native Dynamic Table format.

    This enables interoperability with non-Snowflake query engines (Spark,
    Trino, Flink, etc.) that can read Iceberg tables directly from the
    external volume's object storage (S3, GCS, Azure Blob).

    Architecture:
        Source Data → FeatureView (Dynamic Table, Iceberg format)
                      → External Volume (S3/GCS/Azure)
                      → Other engines read via Iceberg catalog

    Trade-offs:
        - Latency: Same as standard managed FV (bounded by refresh_freq)
        - Cost: Similar to standard DT + external storage costs
        - Complexity: Requires external volume setup
        - Interop: Iceberg files readable by Spark, Trino, Flink, etc.

    Prerequisites:
        - An external volume already created in Snowflake
          (CREATE EXTERNAL VOLUME ... )
        - Appropriate storage permissions on the external volume
        - Enterprise Edition (required for Feature Store)

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        source_query: SQL query that computes features from source tables
        external_volume: Name of the Snowflake external volume for Iceberg storage
        version: Version string
        refresh_freq: How often the Dynamic Table refreshes (default "1 day")
        base_location: Optional sub-path within the external volume
                       (e.g. "feature_store/user_features")
        timestamp_col: Optional timestamp column for point-in-time correctness
        warehouse: Optional warehouse override for refresh compute
        desc: Optional description

    Returns:
        Registered managed FeatureView backed by an Iceberg Dynamic Table
    """
    from snowflake.ml.feature_store import StorageConfig, StorageFormat

    feature_df = session.sql(source_query)

    storage = StorageConfig(
        format=StorageFormat.ICEBERG,
        external_volume=external_volume,
        base_location=base_location or f"feature_store/{name.lower()}",
    )

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        storage_config=storage,
        desc=desc or f"Iceberg-backed FV on volume {external_volume}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Iceberg FeatureView created: {name}/{version}")
    print(f"  external_volume={external_volume}, refresh_freq={refresh_freq}")
    print(f"  Iceberg files readable by Spark, Trino, Flink, etc.")
    return registered_fv

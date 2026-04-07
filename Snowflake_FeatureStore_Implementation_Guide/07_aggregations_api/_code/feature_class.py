"""
Feature class examples for time-windowed aggregations.

This module demonstrates how to:
- Define features using the Feature class
- Configure windows and aliases
- Create tiled Feature Views

Canonical environment: database FEATURE_STORE_DEMO, Feature Store schema FEATURE_STORE,
source schema CLICKSTREAM_DATA, warehouse FS_DEV_WH.

Tested in: tests/test_chapter_07.py

Note: Requires snowflake-ml-python >= 1.21.0
"""
from snowflake.snowpark import Session

try:
    from snowflake.ml.feature_store import FeatureStore, Feature, FeatureView, Entity

    FEATURE_CLASS_AVAILABLE = True
except ImportError:
    from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity

    Feature = None  # type: ignore[misc, assignment]
    FEATURE_CLASS_AVAILABLE = False

# Canonical names (see implementation guide introduction)
DATABASE = "FEATURE_STORE_DEMO"
FEATURE_STORE_SCHEMA = "FEATURE_STORE"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
WAREHOUSE = "FS_DEV_WH"
CANONICAL_ORDERS_TABLE = f"{DATABASE}.{SOURCE_SCHEMA}.ORDERS"
FEATUREVIEW_VERSION_INITIAL = "V01"


def get_purchase_features() -> list:
    """
    Define purchase-related time-windowed features.

    Returns:
        List of Feature definitions
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError("Feature class requires snowflake-ml-python >= 1.21.0")

    return [
        Feature.sum("TOTAL_AMT", "7d").alias("TOTAL_AMT_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("TOTAL_AMT_SUM_30D"),
        Feature.count("ORDER_ID", "7d").alias("ORDER_ID_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_ID_CNT_30D"),
        Feature.avg("TOTAL_AMT", "7d").alias("TOTAL_AMT_AVG_7D"),
        Feature.avg("TOTAL_AMT", "30d").alias("TOTAL_AMT_AVG_30D"),
        Feature.min("TOTAL_AMT", "30d").alias("TOTAL_AMT_MIN_30D"),
        Feature.max("TOTAL_AMT", "30d").alias("TOTAL_AMT_MAX_30D"),
    ]


def get_multi_window_features() -> list:
    """
    Define features with multiple time windows for trend analysis.

    Returns:
        List of Feature definitions
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError("Feature class requires snowflake-ml-python >= 1.21.0")

    return [
        Feature.sum("TOTAL_AMT", "1d").alias("TOTAL_AMT_SUM_1D"),
        Feature.sum("TOTAL_AMT", "7d").alias("TOTAL_AMT_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("TOTAL_AMT_SUM_30D"),
        Feature.sum("TOTAL_AMT", "90d").alias("TOTAL_AMT_SUM_90D"),
        Feature.count("ORDER_ID", "1d").alias("ORDER_ID_CNT_1D"),
        Feature.count("ORDER_ID", "7d").alias("ORDER_ID_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_ID_CNT_30D"),
    ]


def create_aggregation_featureview(
    session: Session,
    entity: Entity,
    source_table: str = CANONICAL_ORDERS_TABLE,
    timestamp_col: str = "ORDER_TS",
    tile_size: str = "1 hour",
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Create a tiled Feature View with time-windowed aggregations.

    Args:
        session: Active Snowpark session
        entity: Entity for the Feature View
        source_table: Fully qualified source table (default: canonical ORDERS)
        timestamp_col: Column containing event timestamp
        tile_size: Feature granularity (tile size)
        refresh_freq: Refresh frequency

    Returns:
        Feature View (not yet registered). Register with version "V01", e.g.:
        fs.register_feature_view(feature_view=fv, version="V01", block=True)
    """
    features = get_purchase_features()

    return FeatureView(
        name="USER_PURCHASE_AGGREGATES",
        entities=[entity],
        feature_df=session.table(source_table),
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        feature_granularity=tile_size,
        features=features,
        desc="User purchase aggregations with multiple time windows",
    )


if __name__ == "__main__":
    if FEATURE_CLASS_AVAILABLE:
        print("Feature class available.")
        features = get_purchase_features()
        print(f"Defined {len(features)} purchase features.")
    else:
        print("Feature class not available. Requires >= 1.21.0")

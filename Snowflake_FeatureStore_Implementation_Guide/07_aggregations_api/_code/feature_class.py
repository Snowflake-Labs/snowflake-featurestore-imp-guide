"""
Feature class examples for time-windowed aggregations.

This module demonstrates how to:
- Define features using the Feature class
- Configure windows and aliases
- Create tiled FeatureViews

Tested in: tests/test_chapter_07.py

Note: Requires snowflake-ml-python >= 1.21.0
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity

try:
    from snowflake.ml.feature_store import Feature
    FEATURE_CLASS_AVAILABLE = True
except ImportError:
    FEATURE_CLASS_AVAILABLE = False


def get_purchase_features() -> list:
    """
    Define purchase-related time-windowed features.
    
    Returns:
        List of Feature definitions
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError("Feature class requires snowflake-ml-python >= 1.21.0")
    
    return [
        # Sum aggregations
        Feature.sum("AMOUNT", "7d").alias("TOTAL_SPEND_7D"),
        Feature.sum("AMOUNT", "30d").alias("TOTAL_SPEND_30D"),
        
        # Count aggregations
        Feature.count("ORDER_ID", "7d").alias("ORDER_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_CNT_30D"),
        
        # Average aggregations
        Feature.avg("AMOUNT", "7d").alias("AVG_ORDER_7D"),
        Feature.avg("AMOUNT", "30d").alias("AVG_ORDER_30D"),
        
        # Min/Max
        Feature.min("AMOUNT", "30d").alias("MIN_ORDER_30D"),
        Feature.max("AMOUNT", "30d").alias("MAX_ORDER_30D"),
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
        # Spend across multiple windows
        Feature.sum("AMOUNT", "1d").alias("SPEND_1D"),
        Feature.sum("AMOUNT", "7d").alias("SPEND_7D"),
        Feature.sum("AMOUNT", "30d").alias("SPEND_30D"),
        Feature.sum("AMOUNT", "90d").alias("SPEND_90D"),
        
        # Order count across multiple windows
        Feature.count("ORDER_ID", "1d").alias("ORDERS_1D"),
        Feature.count("ORDER_ID", "7d").alias("ORDERS_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDERS_30D"),
    ]


def create_aggregation_featureview(
    session: Session,
    entity: Entity,
    source_table: str,
    timestamp_col: str,
    tile_size: str = "1 hour",
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Create a tiled FeatureView with time-windowed aggregations.
    
    Args:
        session: Active Snowpark session
        entity: Entity for the FeatureView
        source_table: Source table name
        timestamp_col: Column containing event timestamp
        tile_size: Feature granularity (tile size)
        refresh_freq: Refresh frequency
        
    Returns:
        FeatureView (not yet registered)
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
        desc="User purchase aggregations with multiple time windows"
    )


if __name__ == "__main__":
    if FEATURE_CLASS_AVAILABLE:
        print("Feature class available.")
        features = get_purchase_features()
        print(f"Defined {len(features)} purchase features.")
    else:
        print("Feature class not available. Requires >= 1.21.0")

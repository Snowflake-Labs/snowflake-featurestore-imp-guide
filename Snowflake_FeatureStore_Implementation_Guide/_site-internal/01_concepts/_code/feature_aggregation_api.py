"""
Feature definition using the Feature Aggregation API.

This module demonstrates how to:
- Use the Feature class for time-windowed aggregations
- Define multiple aggregation windows
- Create tiled Feature Views for efficient computation

Tested in: tests/test_chapter_01.py::TestFeatureAggregation

Note: The Feature aggregation class requires snowflake-ml-python >= 1.21.0
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity

# Feature class import - requires snowflake-ml-python >= 1.21.0
try:
    from snowflake.ml.feature_store import Feature
    FEATURE_CLASS_AVAILABLE = True
except ImportError:
    FEATURE_CLASS_AVAILABLE = False


def get_time_windowed_features() -> list:
    """
    Define time-windowed aggregated features using the Feature class.
    
    Returns:
        List of Feature definitions
        
    Raises:
        ImportError: If Feature class is not available (requires >= 1.21.0)
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError(
            "Feature class requires snowflake-ml-python >= 1.21.0. "
            "Install with: pip install 'snowflake-ml-python>=1.21.0'"
        )
    
    return [
        Feature.sum("TOTAL_AMT", "7d").alias("SPEND_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("SPEND_SUM_30D"),
        Feature.count("ORDER_ID", "7d").alias("ORDER_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_CNT_30D"),
        Feature.avg("TOTAL_AMT", "24h").alias("ORDER_VALUE_AVG_24H"),
        Feature.avg("TOTAL_AMT", "7d").alias("ORDER_VALUE_AVG_7D"),
        Feature.last_n("PRODUCT_ID", "7d", n=5).alias("RECENT_PRODUCTS"),
    ]


def create_tiled_featureview(
    session: Session,
    user_entity: Entity,
    source_table: str = "ORDERS",
) -> FeatureView:
    """
    Create a tiled Feature View with time-windowed aggregations.
    
    Tiled Feature Views use incremental computation for efficiency.
    
    Args:
        session: Active Snowpark session
        user_entity: Entity for user-level features
        source_table: Name of the source orders table
        
    Returns:
        Feature View with tiled aggregations (not yet registered)
        
    Raises:
        ImportError: If Feature class is not available
    """
    features = get_time_windowed_features()
    
    return FeatureView(
        name="USER_ORDER_AGGREGATES",
        entities=[user_entity],
        feature_df=session.table(source_table),
        timestamp_col="ORDER_TS",
        refresh_freq="1h",
        feature_granularity="1h",
        features=features,
        desc="User purchase aggregations with time windows"
    )


def get_multi_window_features() -> list:
    """
    Define features with multiple time windows for comparison.
    
    This pattern is useful for detecting trends (e.g., is recent
    activity higher or lower than historical average?).
    
    Returns:
        List of Feature definitions with multiple windows
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError("Feature class requires snowflake-ml-python >= 1.21.0")
    
    return [
        Feature.sum("TOTAL_AMT", "7d").alias("SPEND_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("SPEND_SUM_30D"),
        Feature.sum("TOTAL_AMT", "90d").alias("SPEND_SUM_90D"),
        
        Feature.count("ORDER_ID", "7d").alias("ORDER_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_CNT_30D"),
        Feature.count("ORDER_ID", "90d").alias("ORDER_CNT_90D"),
        Feature.count("ORDER_ID", "24h").alias("ORDER_CNT_24H"),
        Feature.count("ORDER_ID", "1h").alias("ORDER_CNT_1H"),
    ]


if __name__ == "__main__":
    if FEATURE_CLASS_AVAILABLE:
        print("Feature Aggregation API is available.")
        features = get_time_windowed_features()
        print(f"Defined {len(features)} time-windowed features.")
    else:
        print("Feature class not available. Requires snowflake-ml-python >= 1.21.0")

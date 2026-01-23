"""
Feature definition using the Feature Aggregation API.

This module demonstrates how to:
- Use the Feature class for time-windowed aggregations
- Define multiple aggregation windows
- Create tiled FeatureViews for efficient computation

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
        # Sum aggregations
        Feature.sum("AMOUNT", "7d").alias("TOTAL_SPEND_7D"),
        Feature.sum("AMOUNT", "30d").alias("TOTAL_SPEND_30D"),
        
        # Count aggregations
        Feature.count("ORDER_ID", "7d").alias("ORDER_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_CNT_30D"),
        
        # Average aggregations
        Feature.avg("AMOUNT", "24h").alias("AVG_ORDER_24H"),
        Feature.avg("AMOUNT", "7d").alias("AVG_ORDER_7D"),
        
        # Last N values (for sequence features)
        Feature.last_n("PRODUCT_ID", "7d", n=5).alias("RECENT_PRODUCTS"),
    ]


def create_tiled_featureview(
    session: Session,
    user_entity: Entity,
    source_table: str = "ORDERS",
) -> FeatureView:
    """
    Create a tiled FeatureView with time-windowed aggregations.
    
    Tiled FeatureViews use incremental computation for efficiency.
    
    Args:
        session: Active Snowpark session
        user_entity: Entity for user-level features
        source_table: Name of the source orders table
        
    Returns:
        FeatureView with tiled aggregations (not yet registered)
        
    Raises:
        ImportError: If Feature class is not available
    """
    features = get_time_windowed_features()
    
    return FeatureView(
        name="USER_PURCHASE_AGGREGATES",
        entities=[user_entity],
        feature_df=session.table(source_table),
        timestamp_col="ORDER_TS",
        refresh_freq="1 hour",
        feature_granularity="1 hour",  # Tile size for incremental computation
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
        # Short-term vs long-term spend
        Feature.sum("AMOUNT", "7d").alias("SPEND_7D"),
        Feature.sum("AMOUNT", "30d").alias("SPEND_30D"),
        Feature.sum("AMOUNT", "90d").alias("SPEND_90D"),
        
        # Short-term vs long-term frequency
        Feature.count("ORDER_ID", "7d").alias("ORDERS_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDERS_30D"),
        Feature.count("ORDER_ID", "90d").alias("ORDERS_90D"),
        
        # Recent activity indicators
        Feature.count("ORDER_ID", "24h").alias("ORDERS_24H"),
        Feature.count("ORDER_ID", "1h").alias("ORDERS_1H"),
    ]


if __name__ == "__main__":
    if FEATURE_CLASS_AVAILABLE:
        print("Feature Aggregation API is available.")
        features = get_time_windowed_features()
        print(f"Defined {len(features)} time-windowed features.")
    else:
        print("Feature class not available. Requires snowflake-ml-python >= 1.21.0")

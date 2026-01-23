"""
Temporal Aggregation API feature pipeline pattern.

This module demonstrates how to:
- Define time-windowed features using the Feature class
- Configure tile sizes
- Create tiled FeatureViews

Tested in: tests/test_chapter_05.py

Note: Requires snowflake-ml-python >= 1.21.0
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity

# Feature class import - requires snowflake-ml-python >= 1.21.0
try:
    from snowflake.ml.feature_store import Feature
    FEATURE_CLASS_AVAILABLE = True
except ImportError:
    FEATURE_CLASS_AVAILABLE = False


def get_user_temporal_features() -> list:
    """
    Define time-windowed aggregated features for users.
    
    Returns:
        List of Feature definitions
        
    Raises:
        ImportError: If Feature class is not available
    """
    if not FEATURE_CLASS_AVAILABLE:
        raise ImportError(
            "Feature class requires snowflake-ml-python >= 1.21.0"
        )
    
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
        
        # Approximate distinct count
        Feature.approx_count_distinct("PRODUCT_ID", "7d").alias("UNIQUE_PRODUCTS_7D"),
        
        # Last N values
        Feature.last_n("PRODUCT_ID", "7d", n=5).alias("RECENT_PRODUCTS"),
    ]


def create_tiled_featureview(
    session: Session,
    entity: Entity,
    source_table: str,
    timestamp_col: str,
    tile_size: str = "1 hour",
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Create a tiled FeatureView with temporal aggregations.
    
    Args:
        session: Active Snowpark session
        entity: Entity for the FeatureView
        source_table: Source table name
        timestamp_col: Column containing event timestamp
        tile_size: Granularity for tiling (e.g., "1 hour", "1 day")
        refresh_freq: Refresh frequency
        
    Returns:
        FeatureView (not yet registered)
    """
    features = get_user_temporal_features()
    
    return FeatureView(
        name="USER_TEMPORAL_AGGREGATES",
        entities=[entity],
        feature_df=session.table(source_table),
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        feature_granularity=tile_size,
        features=features,
        desc="User temporal aggregations with tiling"
    )


def get_tile_size_recommendations(data_pattern: str) -> dict:
    """
    Get recommended tile size based on data pattern.
    
    Args:
        data_pattern: Type of data (e.g., "clickstream", "transactions")
        
    Returns:
        Dict with tile size recommendation
    """
    recommendations = {
        "clickstream": {
            "tile_size": "1 hour",
            "reason": "High-frequency events, need fine granularity",
        },
        "transactions": {
            "tile_size": "1 day",
            "reason": "Daily transaction patterns",
        },
        "weekly_aggregates": {
            "tile_size": "1 week",
            "reason": "Slowly changing, coarse granularity OK",
        },
    }
    
    return recommendations.get(data_pattern, recommendations["transactions"])


if __name__ == "__main__":
    if FEATURE_CLASS_AVAILABLE:
        print("Feature class available. Temporal API ready.")
        features = get_user_temporal_features()
        print(f"Defined {len(features)} temporal features.")
    else:
        print("Feature class not available. Requires snowflake-ml-python >= 1.21.0")

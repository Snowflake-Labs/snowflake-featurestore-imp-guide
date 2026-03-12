"""
Online Feature Table examples.

This module demonstrates how to:
- Create Online Feature Tables
- Configure refresh frequencies
- Retrieve online features

Tested in: tests/test_chapter_08.py
"""
from typing import List

from snowflake.snowpark import DataFrame
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity
from snowflake.ml.feature_store.feature_view import OnlineConfig, StoreType

def get_refresh_freq_recommendations() -> dict:
    """
    Get refresh frequency recommendations by use case.
    
    Returns:
        Dict with recommendations
    """
    return {
        "fraud_detection": {
            "refresh_freq": "1 minute",
            "latency": "Very low",
            "cost": "High",
            "reason": "Real-time fraud requires freshest signals"
        },
        "recommendations": {
            "refresh_freq": "5 minutes",
            "latency": "Low",
            "cost": "Medium",
            "reason": "Personalization can tolerate slight lag"
        },
        "marketing": {
            "refresh_freq": "15 minutes",
            "latency": "Moderate",
            "cost": "Low",
            "reason": "Campaign targeting is less time-sensitive"
        },
        "analytics": {
            "refresh_freq": "1 hour",
            "latency": "Higher",
            "cost": "Minimal",
            "reason": "Dashboard metrics don't need real-time"
        },
    }


def create_online_feature_table_config(
    use_case: str,
    warehouse: str = "OFT_REFRESH_WH",
) -> dict:
    """
    Get configuration for Online Feature Table creation.
    
    Args:
        use_case: One of fraud_detection, recommendations, marketing, analytics
        warehouse: Warehouse for OFT refresh
        
    Returns:
        Dict with OFT configuration
    """
    recommendations = get_refresh_freq_recommendations()
    config = recommendations.get(use_case, recommendations["recommendations"])
    
    return {
        "warehouse": warehouse,
        "refresh_freq": config["refresh_freq"],
        "expected_latency": config["latency"],
        "estimated_cost": config["cost"],
    }


def create_online_feature_view(
    fs: FeatureStore,
    name: str,
    entities: List[Entity],
    feature_df: DataFrame,
    version: str = "v1",
    timestamp_col: str = None,
    refresh_freq: str = "5 minutes",
    target_lag: str = "30 seconds",
    desc: str = None,
) -> FeatureView:
    """
    Create a new FeatureView with online serving enabled at creation time.

    Args:
        fs: Initialized FeatureStore instance
        name: Name of the feature view
        entities: List of Entity objects for join keys
        feature_df: Snowpark DataFrame with feature transformations
        version: Version string for the feature view
        timestamp_col: Optional timestamp column for PIT correctness
        refresh_freq: How often offline feature data refreshes
        target_lag: How fresh the online data should be (min 10 seconds)
        desc: Optional description

    Returns:
        Registered FeatureView with online serving enabled
    """
    online_config = OnlineConfig(enable=True, target_lag=target_lag)

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        online_config=online_config,
        desc=desc,
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Online feature view created: {name}/{version}")
    print(f"  refresh_freq={refresh_freq}, target_lag={target_lag}")
    return registered_fv


def enable_online_serving(
    fs: FeatureStore,
    name: str,
    version: str,
    target_lag: str = "5 minutes",
) -> None:
    """
    Enable online serving on an existing registered FeatureView.

    Args:
        fs: Initialized FeatureStore instance
        name: Name of the existing feature view
        version: Version of the existing feature view
        target_lag: How fresh the online data should be
    """
    fs.update_feature_view(
        name=name,
        version=version,
        online_config=OnlineConfig(enable=True, target_lag=target_lag),
    )

    print(f"Online serving enabled for {name}/{version} (target_lag={target_lag})")


def read_online_features(
    fs: FeatureStore,
    feature_view: FeatureView,
    keys: List[List[str]],
    feature_names: List[str],
) -> DataFrame:
    """
    Retrieve features from the online store for given entity keys.

    Args:
        fs: Initialized FeatureStore instance
        feature_view: Registered FeatureView with online serving enabled
        keys: List of key value lists, e.g. [["user_1"], ["user_2"]]
        feature_names: List of feature column names to retrieve

    Returns:
        Snowpark DataFrame with the requested feature values
    """
    result = fs.read_feature_view(
        feature_view=feature_view,
        keys=keys,
        feature_names=feature_names,
        store_type=StoreType.ONLINE,
    )

    print(f"Retrieved {len(feature_names)} features for {len(keys)} keys from online store")
    return result



if __name__ == "__main__":
    recs = get_refresh_freq_recommendations()
    print("OFT Refresh Frequency Recommendations:")
    for use_case, config in recs.items():
        print(f"\n{use_case}:")
        print(f"  refresh_freq: {config['refresh_freq']}")
        print(f"  reason: {config['reason']}")

"""
Online Feature Table examples.

This module demonstrates how to:
- Create Online Feature Tables
- Configure refresh frequencies
- Retrieve online features

Tested in: tests/test_chapter_08.py
"""
from snowflake.ml.feature_store import FeatureStore, FeatureView


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


if __name__ == "__main__":
    recs = get_refresh_freq_recommendations()
    print("OFT Refresh Frequency Recommendations:")
    for use_case, config in recs.items():
        print(f"\n{use_case}:")
        print(f"  refresh_freq: {config['refresh_freq']}")
        print(f"  reason: {config['reason']}")

"""
Dynamic Table-based feature pipeline pattern.

This module demonstrates how to:
- Create Dynamic Table-backed Feature Views
- Configure refresh frequencies
- Chain Dynamic Tables

Tested in: tests/test_chapter_05.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_dynamic_table_featureview(
    session: Session,
    entity: Entity,
    source_table: str = "FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS",
    refresh_freq: str = "15 minutes",
) -> FeatureView:
    """
    Create a Dynamic Table-backed Feature View.
    
    Args:
        session: Active Snowpark session
        entity: Entity for the Feature View
        source_table: Fully qualified source table (default: clickstream ORDERS)
        refresh_freq: Refresh frequency (e.g., "15 minutes", "1 hour")
        
    Returns:
        Feature View (not yet registered)
    """
    # Define transformation logic
    feature_df = session.sql(f"""
        SELECT 
            USER_ID,
            COUNT(DISTINCT ORDER_ID) AS ORDER_CNT,
            SUM(TOTAL_AMT) AS SPEND_SUM,
            AVG(TOTAL_AMT) AS AVG_ORDER_AMT,
            MAX(ORDER_TS) AS LAST_ORDER_TS
        FROM {source_table}
        GROUP BY USER_ID
    """)
    
    return FeatureView(
        name="USER_PURCHASE_STATS",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col="LAST_ORDER_TS",
        refresh_freq=refresh_freq,
        desc=f"User purchase statistics from {source_table}"
    )


def get_refresh_frequency_recommendations(
    update_frequency: str,
) -> dict:
    """
    Get recommended refresh_freq based on source update frequency.
    
    Args:
        update_frequency: How often source data updates
        
    Returns:
        Dict with recommendations
    """
    recommendations = {
        "real-time": {
            "refresh_freq": "1 minute",
            "cost": "High",
            "use_case": "Fraud detection, real-time personalization",
        },
        "hourly": {
            "refresh_freq": "15 minutes",
            "cost": "Medium",
            "use_case": "Standard operational features",
        },
        "daily": {
            "refresh_freq": "1 hour",
            "cost": "Low",
            "use_case": "Daily batch features",
        },
        "weekly": {
            "refresh_freq": "1 day",
            "cost": "Minimal",
            "use_case": "Slowly changing dimensions",
        },
    }
    
    return recommendations.get(update_frequency, recommendations["daily"])


if __name__ == "__main__":
    print("Dynamic Table examples require an active Snowflake session.")

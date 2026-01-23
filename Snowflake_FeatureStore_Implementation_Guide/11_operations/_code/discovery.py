"""
Feature discovery and metadata utilities.

This module demonstrates how to:
- List and search FeatureViews
- Get feature metadata
- Track feature usage

Tested in: tests/test_chapter_11.py
"""
from snowflake.ml.feature_store import FeatureStore


def get_health_check_queries() -> dict:
    """
    Get SQL queries for health checks.
    
    Returns:
        Dict with health check queries
    """
    return {
        "refresh_history": """
            SELECT NAME, STATE, REFRESH_START_TIME
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
            ORDER BY REFRESH_START_TIME DESC
            LIMIT 10
        """,
        "current_lag": """
            SELECT NAME, 
                   TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
            WHERE SCHEMA_NAME = 'FEATURE_STORE'
        """,
        "stale_features": """
            SELECT NAME, DATA_TIMESTAMP
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
            WHERE SCHEMA_NAME = 'FEATURE_STORE'
              AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60
        """,
    }


def get_monitoring_best_practices() -> list:
    """
    Get best practices for Feature Store monitoring.
    
    Returns:
        List of best practices
    """
    return [
        "Set up alerts for stale features (lag > threshold)",
        "Monitor refresh duration trends",
        "Track feature usage via ACCESS_HISTORY",
        "Review compute costs weekly",
        "Document feature owners and SLAs",
        "Implement data quality checks with DMFs",
    ]


if __name__ == "__main__":
    queries = get_health_check_queries()
    print("Health Check Queries:")
    for name, query in queries.items():
        print(f"\n{name}:")
        print(f"  {query[:60]}...")

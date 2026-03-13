"""
Feature discovery and metadata utilities.

This module demonstrates how to:
- List and search FeatureViews
- Get feature metadata
- Track feature usage

Tested in: tests/test_chapter_11.py
"""
from snowflake.ml.feature_store import FeatureStore, FeatureView
from snowflake.snowpark import DataFrame
from snowflake.snowpark import functions as F
from typing import Any, Dict, List, Optional


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


def search_feature_views(
    fs: FeatureStore,
    search_term: str,
    search_columns: Optional[List[str]] = None,
    entity_name: Optional[str] = None,
) -> DataFrame:
    if search_columns is None:
        search_columns = ["NAME", "VERSION", "DESC"]

    fv_df = fs.list_feature_views(entity_name=entity_name)
    term_upper = search_term.upper()
    condition = None
    for col_name in search_columns:
        col_condition = F.upper(F.col(col_name)).contains(F.lit(term_upper))
        condition = col_condition if condition is None else (condition | col_condition)

    return fv_df.filter(condition)


def get_feature_view_details(
    fs: FeatureStore,
    name: str,
    version: str,
) -> Dict[str, Any]:
    fv = fs.get_feature_view(name=name, version=version)

    entities_info = []
    for entity in fv.entities:
        entities_info.append({
            "name": entity.name,
            "join_keys": entity.join_keys,
            "desc": entity.desc,
        })

    details = {
        "name": fv.name,
        "version": fv.version,
        "desc": fv.desc,
        "status": str(fv.status),
        "entities": entities_info,
        "feature_names": fv.feature_names,
        "feature_descs": dict(fv.feature_descs) if fv.feature_descs else {},
        "timestamp_col": fv.timestamp_col,
        "refresh_freq": fv.refresh_freq,
        "refresh_mode": fv.refresh_mode,
        "warehouse": fv.warehouse,
        "online_enabled": fv.online,
        "owner": fv.owner,
        "query": fv.query,
    }

    return details


def get_metadata_queries() -> dict:
    return {
        "describe_feature_view": """
            DESCRIBE DYNAMIC TABLE {feature_view_name};
        """,
        "list_all_features": """
            SELECT
                TABLE_NAME AS FEATURE_VIEW,
                COLUMN_NAME AS FEATURE,
                DATA_TYPE,
                COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'FEATURE_STORE'
              AND TABLE_NAME LIKE '%$%'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
    }


if __name__ == "__main__":
    queries = get_health_check_queries()
    print("Health Check Queries:")
    for name, query in queries.items():
        print(f"\n{name}:")
        print(f"  {query[:60]}...")

"""
Feature discovery and metadata utilities.

This module demonstrates how to:
- List and search Feature Views
- Query column metadata without SQL injection (Snowpark DataFrame filters)
- Track feature usage

Tested in: tests/test_chapter_11.py
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from snowflake.snowpark import Row
from snowflake.snowpark.functions import coalesce, col, lit, lower

if TYPE_CHECKING:
    from snowflake.snowpark import Session


# Canonical demo names (see guide introduction)
FS_DATABASE = "FEATURE_STORE_DEMO"
FS_SCHEMA = "FEATURE_STORE"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"


def get_health_check_queries() -> dict:
    """
    Get SQL queries for health checks.

    Returns:
        Dict with health check queries
    """
    return {
        "refresh_history": """
            SELECT NAME, STATE, REFRESH_START_TIME
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
                NAME_PREFIX => 'FEATURE_STORE_DEMO.FEATURE_STORE.'
            ))
            ORDER BY REFRESH_START_TIME DESC
            LIMIT 10
        """,
        "current_lag": """
            SELECT NAME,
                   TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
            WHERE DATABASE_NAME = 'FEATURE_STORE_DEMO'
              AND SCHEMA_NAME = 'FEATURE_STORE'
        """,
        "stale_features": """
            SELECT NAME, DATA_TIMESTAMP
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
            WHERE DATABASE_NAME = 'FEATURE_STORE_DEMO'
              AND SCHEMA_NAME = 'FEATURE_STORE'
              AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60
        """,
    }


def search_feature_columns(
    session: "Session",
    search_term: str,
    *,
    database: str = FS_DATABASE,
    table_schema: str = FS_SCHEMA,
    limit: int = 20,
) -> List[Row]:
    """
    Search feature-store column metadata via INFORMATION_SCHEMA.COLUMNS using
    Snowpark filters (no f-string SQL). ``search_term`` is wrapped in % for a
    case-insensitive ``LIKE`` (via ``lower``); ``%`` / ``_`` in the term act as
    SQL wildcards.

    For catalog search across registered Feature Views in the Python API, use
    ``FeatureStore.list_feature_views()`` / ``get_feature_view()`` instead.
    """
    pattern = f"%{search_term}%"
    pattern_lower = pattern.lower()
    return (
        session.table(f'{database}.information_schema.columns')
        .filter(col("table_schema") == lit(table_schema))
        .filter(
            (lower(col("column_name")).like(lit(pattern_lower)))
            | (lower(coalesce(col("comment"), lit(""))).like(lit(pattern_lower)))
        )
        .select(
            col("table_name").alias("FEATURE_VIEW"),
            col("column_name").alias("FEATURE_NAME"),
            col("data_type").alias("DATA_TYPE"),
            col("comment").alias("DESCRIPTION"),
        )
        .limit(limit)
        .collect()
    )


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
        "Implement data quality checks with DMFs (system or custom; RETURNS NUMBER)",
        "Monitor online feature tables via ONLINE_FEATURE_TABLE_REFRESH_HISTORY and HYBRID_TABLE* views",
    ]


if __name__ == "__main__":
    queries = get_health_check_queries()
    print("Health Check Queries:")
    for name, query in queries.items():
        print(f"\n{name}:")
        print(f"  {query[:60]}...")

"""
Migration utilities for Feature Store migration.

This module demonstrates how to:
- Validate migration outputs
- Compare features between platforms
- Track migration progress

Canonical environment for examples in this guide:
- Database: FEATURE_STORE_DEMO
- Feature Store schema: FEATURE_STORE
- Source schema: CLICKSTREAM_DATA
  (EVENTS, SESSIONS, ORDERS, USERS, PRODUCTS, …)
- Warehouse: FS_DEV_WH
- Feature View registration versions: V01, V02, …

Tested in: tests/test_chapter_13.py
"""

from typing import Any

# Reference values for docs and runbooks (not Snowflake secrets).
CANONICAL_DATABASE = "FEATURE_STORE_DEMO"
CANONICAL_FEATURE_STORE_SCHEMA = "FEATURE_STORE"
CANONICAL_SOURCE_SCHEMA = "CLICKSTREAM_DATA"
CANONICAL_WAREHOUSE = "FS_DEV_WH"
CANONICAL_FEATURE_VIEW_VERSION = "V01"


def get_canonical_environment() -> dict[str, str]:
    """Return canonical DB, schema, and warehouse names for this guide."""
    return {
        "database": CANONICAL_DATABASE,
        "feature_store_schema": CANONICAL_FEATURE_STORE_SCHEMA,
        "source_schema": CANONICAL_SOURCE_SCHEMA,
        "warehouse": CANONICAL_WAREHOUSE,
        "default_feature_view_version": CANONICAL_FEATURE_VIEW_VERSION,
    }


def get_migration_checklist() -> list[dict[str, Any]]:
    """
    Get migration checklist items.

    Returns:
        List of checklist items
    """
    return [
        {
            "phase": "Assessment",
            "task": "Inventory all existing features",
            "done": False,
        },
        {
            "phase": "Assessment",
            "task": "Map terminology to Snowflake",
            "done": False,
        },
        {
            "phase": "Assessment",
            "task": "Identify dependencies",
            "done": False,
        },
        {
            "phase": "Assessment",
            "task": "Plan migration order",
            "done": False,
        },
        {"phase": "Migration", "task": "Create entities", "done": False},
        {
            "phase": "Migration",
            "task": "Port feature definitions (feature_df)",
            "done": False,
        },
        {
            "phase": "Migration",
            "task": "Setup refresh schedules (refresh_freq, target_lag)",
            "done": False,
        },
        {
            "phase": "Migration",
            "task": "Document backfill path (refresh_feature_view)",
            "done": False,
        },
        {
            "phase": "Migration",
            "task": "Configure online serving (Hybrid Table)",
            "done": False,
        },
        {
            "phase": "Validation",
            "task": "Compare feature outputs",
            "done": False,
        },
        {
            "phase": "Validation",
            "task": "Validate PIT correctness",
            "done": False,
        },
        {
            "phase": "Validation",
            "task": "Update consumer applications",
            "done": False,
        },
        {
            "phase": "Validation",
            "task": "Cutover to Snowflake",
            "done": False,
        },
    ]


def get_validation_metrics() -> dict:
    """
    Get metrics to track during migration validation.

    Returns:
        Dict with validation metric definitions
    """
    return {
        "row_count_match": {
            "description": "Source and target row counts match",
            "threshold": "100%",
            "critical": True,
        },
        "value_match_rate": {
            "description": "Percentage of values that match exactly",
            "threshold": ">99.9%",
            "critical": True,
        },
        "null_rate_comparison": {
            "description": "Null rates within acceptable range",
            "threshold": "Within 1%",
            "critical": False,
        },
        "latency_comparison": {
            "description": "Query latency within acceptable range",
            "threshold": "Within 20%",
            "critical": False,
        },
    }


if __name__ == "__main__":
    checklist = get_migration_checklist()
    print("Migration Checklist:")
    for item in checklist:
        status = "✓" if item["done"] else "○"
        print(f"  {status} [{item['phase']}] {item['task']}")
    print("\nCanonical environment:", get_canonical_environment())

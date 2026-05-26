"""
Spine design examples for training and inference.

Canonical environment: database FEATURE_STORE_DEMO, source schema CLICKSTREAM_DATA,
Feature Store schema FEATURE_STORE, warehouse FS_DEV_WH.

This module demonstrates how to:
- Create training spines (clickstream SESSIONS: SESSION_START_TS, IS_CONVERTED, USER_ID)
- Create inference spines
- Design spines for different use cases

Tested in: tests/test_chapter_10.py
"""


def get_spine_templates() -> dict:
    """
    Get spine SQL templates for common use cases.

    Returns:
        Dict with spine SQL templates
    """
    return {
        "training_conversion": {
            "sql": """
                SELECT
                    USER_ID,
                    SESSION_START_TS,
                    IS_CONVERTED AS LABEL
                FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.SESSIONS
            """,
            "description": "Training spine: session-level conversion (PIT = SESSION_START_TS)",
            "columns": ["USER_ID", "SESSION_START_TS", "LABEL"],
            "spine_timestamp_col": "SESSION_START_TS",
        },
        "batch_inference": {
            "sql": """
                SELECT
                    USER_ID,
                    CURRENT_TIMESTAMP() AS SESSION_START_TS
                FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS
                WHERE IS_ACTIVE = TRUE
            """,
            "description": "Batch inference spine for active users",
            "columns": ["USER_ID", "SESSION_START_TS"],
            "spine_timestamp_col": "SESSION_START_TS",
        },
        "historical_inference": {
            "sql": """
                SELECT
                    USER_ID,
                    ORDER_TS
                FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS
            """,
            "description": "Historical inference at each order time (PIT = ORDER_TS)",
            "columns": ["USER_ID", "ORDER_TS"],
            "spine_timestamp_col": "ORDER_TS",
        },
    }


def get_spine_best_practices() -> list:
    """
    Get best practices for spine design.

    Returns:
        List of best practice guidelines
    """
    return [
        "Always include entity keys that match Feature View entities",
        "Include timestamp column for PIT retrieval; align spine_timestamp_col with the column name",
        "If you alias the timestamp (e.g. SESSION_START_TS AS EVENT_TS), use the alias everywhere downstream",
        "Include label only for training (not inference)",
        "Filter to relevant entities before joining",
        "Validate spine has expected row count",
    ]


if __name__ == "__main__":
    templates = get_spine_templates()
    print("Spine Templates:")
    for name, template in templates.items():
        print(f"\n{name}:")
        print(f"  Columns: {template['columns']}")
        print(f"  Description: {template['description']}")

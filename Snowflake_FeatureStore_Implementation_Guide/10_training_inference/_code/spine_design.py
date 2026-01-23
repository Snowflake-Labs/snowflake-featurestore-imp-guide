"""
Spine design examples for training and inference.

This module demonstrates how to:
- Create training spines
- Create inference spines
- Design spines for different use cases

Tested in: tests/test_chapter_10.py
"""


def get_spine_templates() -> dict:
    """
    Get spine templates for common use cases.
    
    Returns:
        Dict with spine SQL templates
    """
    return {
        "training_churn": {
            "sql": """
                SELECT 
                    USER_ID,
                    CHURN_DATE AS EVENT_TS,
                    CHURNED AS LABEL
                FROM CHURN_EVENTS
            """,
            "description": "Training spine for churn prediction",
            "columns": ["USER_ID", "EVENT_TS", "LABEL"],
        },
        "batch_inference": {
            "sql": """
                SELECT 
                    USER_ID,
                    CURRENT_TIMESTAMP() AS EVENT_TS
                FROM ACTIVE_USERS
            """,
            "description": "Batch inference spine for active users",
            "columns": ["USER_ID", "EVENT_TS"],
        },
        "historical_inference": {
            "sql": """
                SELECT 
                    USER_ID,
                    SCORE_DATE AS EVENT_TS
                FROM SCORING_SCHEDULE
            """,
            "description": "Historical inference at specific dates",
            "columns": ["USER_ID", "EVENT_TS"],
        },
    }


def get_spine_best_practices() -> list:
    """
    Get best practices for spine design.
    
    Returns:
        List of best practice guidelines
    """
    return [
        "Always include entity keys that match FeatureView entities",
        "Include timestamp column for PIT retrieval",
        "Name timestamp column clearly (e.g., EVENT_TS, PREDICTION_TS)",
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

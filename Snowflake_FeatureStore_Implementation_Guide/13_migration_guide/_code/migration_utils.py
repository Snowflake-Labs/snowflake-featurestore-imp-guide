"""
Migration utilities for Feature Store migration.

This module demonstrates how to:
- Validate migration outputs
- Compare features between platforms
- Track migration progress

Tested in: tests/test_chapter_13.py
"""


def get_migration_checklist() -> list:
    """
    Get migration checklist items.
    
    Returns:
        List of checklist items
    """
    return [
        {"phase": "Assessment", "task": "Inventory all existing features", "done": False},
        {"phase": "Assessment", "task": "Map terminology to Snowflake", "done": False},
        {"phase": "Assessment", "task": "Identify dependencies", "done": False},
        {"phase": "Assessment", "task": "Plan migration order", "done": False},
        {"phase": "Migration", "task": "Create entities", "done": False},
        {"phase": "Migration", "task": "Port feature definitions", "done": False},
        {"phase": "Migration", "task": "Setup refresh schedules", "done": False},
        {"phase": "Migration", "task": "Configure online serving", "done": False},
        {"phase": "Validation", "task": "Compare feature outputs", "done": False},
        {"phase": "Validation", "task": "Validate PIT correctness", "done": False},
        {"phase": "Validation", "task": "Update consumer applications", "done": False},
        {"phase": "Validation", "task": "Cutover to Snowflake", "done": False},
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

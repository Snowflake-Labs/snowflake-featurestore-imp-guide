"""
Feature column prefixing for disambiguation.

This module demonstrates how to:
- Use auto_prefix for automatic prefixing
- Use .with_name() for custom prefixes
- Handle multi-FeatureView joins

Tested in: tests/test_chapter_07.py
"""


def get_prefixing_examples() -> dict:
    """
    Get examples of different prefixing strategies.
    
    Returns:
        Dict with prefixing strategy examples
    """
    return {
        "no_prefix": {
            "description": "No prefix - use when column names are unique",
            "code": """
fs.generate_dataset(
    spine_df=spine,
    features=[user_features_fv],  # Single FV, no prefix needed
)
""",
            "result_columns": ["TOTAL_SPEND_7D", "ORDER_CNT_7D"],
        },
        "auto_prefix": {
            "description": "Auto prefix with FeatureView name",
            "code": """
fs.generate_dataset(
    spine_df=spine,
    features=[user_orders_fv, user_sessions_fv],
    auto_prefix=True,
)
""",
            "result_columns": ["USER_ORDERS__TOTAL_SPEND_7D", "USER_SESSIONS__SESSION_CNT_7D"],
        },
        "custom_prefix": {
            "description": "Custom prefix with .with_name()",
            "code": """
fs.generate_dataset(
    spine_df=spine,
    features=[
        user_orders_fv.with_name("orders"),
        user_sessions_fv.with_name("sessions"),
    ],
)
""",
            "result_columns": ["orders__TOTAL_SPEND_7D", "sessions__SESSION_CNT_7D"],
        },
    }


def get_naming_conventions() -> dict:
    """
    Get recommended naming conventions for prefixes.
    
    Returns:
        Dict with naming convention recommendations
    """
    return {
        "short_prefix": {
            "pattern": "3-5 character abbreviation",
            "examples": ["ord", "sess", "usr", "prod"],
            "reason": "Keeps column names manageable",
        },
        "domain_prefix": {
            "pattern": "Domain name",
            "examples": ["purchase", "session", "profile"],
            "reason": "Clear domain context",
        },
        "no_prefix": {
            "pattern": "Include context in feature name",
            "examples": ["PURCHASE_TOTAL_SPEND_7D", "SESSION_PAGE_VIEW_CNT_7D"],
            "reason": "Self-documenting column names",
        },
    }


if __name__ == "__main__":
    examples = get_prefixing_examples()
    print("Prefixing Strategy Examples:")
    for strategy, details in examples.items():
        print(f"\n{strategy}:")
        print(f"  Description: {details['description']}")
        print(f"  Result columns: {details['result_columns']}")

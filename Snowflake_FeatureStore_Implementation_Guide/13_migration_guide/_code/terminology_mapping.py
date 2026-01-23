"""
Terminology mapping between Feature Store platforms.

This module demonstrates how to:
- Map concepts from Tecton/Feast to Snowflake
- Translate API calls
- Understand architectural differences

Tested in: tests/test_chapter_13.py
"""


def get_terminology_mapping() -> dict:
    """
    Get terminology mapping from other platforms to Snowflake.
    
    Returns:
        Dict with terminology mappings
    """
    return {
        "tecton_to_snowflake": {
            "Feature Store": "Feature Store (Schema)",
            "Entity": "Entity",
            "Batch Feature View": "FeatureView (DT)",
            "On-Demand Feature View": "FeatureView (View)",
            "Online Store": "Online Feature Table",
            "Offline Store": "FeatureView (DT)",
            "Feature Service": "FeatureView slice",
            "get_historical_features": "generate_dataset",
            "get_online_features": "get_online_features",
            "schedule": "refresh_freq",
        },
        "feast_to_snowflake": {
            "Feature Store": "Feature Store (Schema)",
            "Entity": "Entity",
            "Feature View": "FeatureView",
            "Online Store": "Online Feature Table",
            "Offline Store": "FeatureView (DT)",
            "Feature Service": "FeatureView slice",
            "get_historical_features": "generate_dataset",
            "get_online_features": "get_online_features",
            "ttl": "refresh_freq (inverse concept)",
        },
    }


def get_api_translation() -> dict:
    """
    Get API call translations.
    
    Returns:
        Dict with API translations
    """
    return {
        "create_entity": {
            "tecton": "Entity(name='user', join_keys=[...])",
            "snowflake": "Entity(name='USER', join_keys=[...])",
            "notes": "Similar API, SCREAMING_SNAKE_CASE convention",
        },
        "create_feature_view": {
            "tecton": "@batch_feature_view decorator",
            "snowflake": "FeatureView(name=..., feature_df=...)",
            "notes": "SQL/Snowpark vs Python transformations",
        },
        "get_training_data": {
            "tecton": "fs.get_historical_features(spine_df, features)",
            "snowflake": "fs.generate_dataset(spine_df, features)",
            "notes": "Similar signature",
        },
    }


if __name__ == "__main__":
    mappings = get_terminology_mapping()
    print("Tecton → Snowflake Terminology:")
    for tecton, snowflake in mappings["tecton_to_snowflake"].items():
        print(f"  {tecton} → {snowflake}")

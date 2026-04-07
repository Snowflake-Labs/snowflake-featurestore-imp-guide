"""
Terminology mapping between Feature Store platforms.

This module demonstrates how to:
- Map concepts from Tecton/Feast to Snowflake
- Translate API calls
- Understand architectural differences

Canonical sample layout: database FEATURE_STORE_DEMO, Feature Store schema FEATURE_STORE,
source schema CLICKSTREAM_DATA, warehouse FS_DEV_WH. Feature View versions use V01 format.

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
            "Feature View": "FeatureView",
            "Entity": "Entity",
            "Batch Feature View": "FeatureView (Dynamic Table, refresh_freq)",
            "On-Demand Feature View": "FeatureView (View; omit refresh_freq / None)",
            "Feature Service": "generate_training_set() / generate_dataset()",
            "Online Store": "Online Feature Table (Hybrid Table)",
            "Offline Store": "Feature Store schema (FEATURE_STORE)",
            "Data Source": "Source table or view (e.g. CLICKSTREAM_DATA.*)",
            "Transformation": "FeatureView query (feature_df)",
            "Backfill": "fs.refresh_feature_view()",
            "TTL": "refresh_freq (offline DT); OnlineConfig.target_lag (online sync)",
            "schedule": "refresh_freq (period or CRON)",
            "get_historical_features": "generate_training_set() / generate_dataset()",
            "get_online_features": "get_online_features",
            "Spine": "Spine DataFrame (spine_timestamp_col)",
        },
        "feast_to_snowflake": {
            "Feature Store": "Feature Store (schema + metadata)",
            "Entity": "Entity",
            "Feature View": "FeatureView",
            "Batch Feature View": "FeatureView (Dynamic Table, refresh_freq)",
            "On-Demand Feature View": "FeatureView (View; omit refresh_freq / None)",
            "Online Store": "Online Feature Table (Hybrid Table)",
            "Offline Store": "Feature Store schema",
            "Feature Service": "generate_training_set() / generate_dataset()",
            "Data Source": "Source table or view",
            "get_historical_features": "generate_training_set() / generate_dataset()",
            "get_online_features": "get_online_features",
            "ttl": "refresh_freq / OnlineConfig.target_lag (layer-dependent)",
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
            "snowflake": "Entity(name='USER', join_keys=['USER_ID'])",
            "notes": "Similar API; this guide uses SCREAMING_SNAKE_CASE for entities",
        },
        "create_feature_view": {
            "tecton": "@batch_feature_view / @on_demand_feature_view",
            "snowflake": "FeatureView(name=..., feature_df=..., refresh_freq=...)",
            "notes": "SQL/Snowpark feature_df; batch → period/CRON refresh_freq; on-demand → None",
        },
        "register_feature_view": {
            "tecton": "Implicit in decorator / workspace push",
            "snowflake": "fs.register_feature_view(feature_view=fv, version='V01')",
            "notes": "Version strings use V01, V02, …",
        },
        "get_training_data_snowpark": {
            "tecton": "fs.get_historical_features(spine_df, features)",
            "snowflake": "fs.generate_training_set(spine_df, features, spine_timestamp_col=...)",
            "notes": "Returns Snowpark DataFrame; optional save_as",
        },
        "get_training_data_dataset": {
            "tecton": "fs.get_historical_features(...)",
            "snowflake": "fs.generate_dataset(..., version='V01')",
            "notes": "Returns versioned Snowflake ML Dataset (Parquet on stage)",
        },
        "backfill": {
            "tecton": "Pipeline backfill / materialization job",
            "snowflake": "fs.refresh_feature_view(fv)",
            "notes": "Trigger refresh outside scheduled refresh_freq when needed",
        },
        "example_source_fqn": {
            "tecton": "BatchDataSource(...)",
            "snowflake": "FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS",
            "notes": "Register Feature Views against fully qualified clickstream tables",
        },
    }


if __name__ == "__main__":
    mappings = get_terminology_mapping()
    print("Tecton → Snowflake Terminology:")
    for tecton, snowflake in mappings["tecton_to_snowflake"].items():
        print(f"  {tecton} → {snowflake}")

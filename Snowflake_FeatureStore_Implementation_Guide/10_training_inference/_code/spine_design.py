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


from typing import List, Optional, Union

from snowflake.ml.feature_store import FeatureStore, FeatureView
from snowflake.snowpark import DataFrame


def generate_training_dataset(
    fs: FeatureStore,                                   # Initialized FeatureStore instance
    spine_df: DataFrame,                                # DataFrame with entity keys, timestamps, and optionally labels
    features: List[FeatureView],                        # FeatureViews (or slices) to join into the spine
    spine_timestamp_col: str = "EVENT_TS",              # Timestamp column in spine_df for PIT lookups
    spine_label_cols: List[str] = None,                 # Label column(s) to preserve in the output (training only)
    save_as: str = None,                                # If set, materializes result to this table name (DataFrame mode only)
    include_feature_view_timestamp_col: bool = False,   # Include FeatureView's own timestamp column in output
    output_type: str = "dataframe",                     # "dataframe" (default) or "dataset" (immutable snapshot)
    dataset_name: str = None,                           # Required when output_type="dataset"; name for the Dataset object
    dataset_version: str = None,                        # Optional version label for the Dataset object
) -> Union[DataFrame, "Dataset"]:
    if output_type == "dataset":
        if dataset_name is None:
            raise ValueError("dataset_name is required when output_type='dataset'")
        dataset = fs.generate_dataset(
            name=dataset_name,
            spine_df=spine_df,
            features=features,
            spine_timestamp_col=spine_timestamp_col,
            spine_label_cols=spine_label_cols,
            include_feature_view_timestamp_col=include_feature_view_timestamp_col,
            version=dataset_version,
        )
        return dataset
    else:
        training_set = fs.generate_training_set(
            spine_df=spine_df,
            features=features,
            spine_timestamp_col=spine_timestamp_col,
            spine_label_cols=spine_label_cols,
            save_as=save_as,
            include_feature_view_timestamp_col=include_feature_view_timestamp_col,
        )
        return training_set


def generate_multi_fv_training_dataset(
    fs: FeatureStore,                                   # Initialized FeatureStore instance
    spine_df: DataFrame,                                # DataFrame with entity keys and timestamps
    features: List[FeatureView],                        # Multiple FeatureViews to join (e.g. purchases, sessions, profile)
    spine_timestamp_col: str = "EVENT_TS",              # Timestamp column for PIT lookups
    spine_label_cols: List[str] = None,                 # Label column(s) to preserve (training only)
    save_as: str = None,                                # If set, materializes result to this table name (DataFrame mode only)
    auto_prefix: bool = True,                           # Prefix feature columns with FeatureView name to avoid collisions
    include_feature_view_timestamp_col: bool = False,   # Include each FeatureView's timestamp in output
    output_type: str = "dataframe",                     # "dataframe" (default) or "dataset" (immutable snapshot)
    dataset_name: str = None,                           # Required when output_type="dataset"; name for the Dataset object
    dataset_version: str = None,                        # Optional version label for the Dataset object
) -> Union[DataFrame, "Dataset"]:
    if output_type == "dataset":
        if dataset_name is None:
            raise ValueError("dataset_name is required when output_type='dataset'")
        dataset = fs.generate_dataset(
            name=dataset_name,
            spine_df=spine_df,
            features=features,
            spine_timestamp_col=spine_timestamp_col,
            spine_label_cols=spine_label_cols,
            auto_prefix=auto_prefix,
            include_feature_view_timestamp_col=include_feature_view_timestamp_col,
            version=dataset_version,
        )
        return dataset
    else:
        training_set = fs.generate_training_set(
            spine_df=spine_df,
            features=features,
            spine_timestamp_col=spine_timestamp_col,
            spine_label_cols=spine_label_cols,
            save_as=save_as,
            auto_prefix=auto_prefix,
            include_feature_view_timestamp_col=include_feature_view_timestamp_col,
        )
        return training_set


if __name__ == "__main__":
    templates = get_spine_templates()
    print("Spine Templates:")
    for name, template in templates.items():
        print(f"\n{name}:")
        print(f"  Columns: {template['columns']}")
        print(f"  Description: {template['description']}")

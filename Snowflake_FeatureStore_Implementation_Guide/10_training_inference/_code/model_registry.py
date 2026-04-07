"""
Model Registry integration examples.

Canonical environment: FEATURE_STORE_DEMO / FEATURE_STORE / CLICKSTREAM_DATA / FS_DEV_WH.
Prefer open-source estimators (sklearn, XGBoost); log with Registry.log_model().

This module demonstrates how to:
- Log models with feature lineage
- Track feature versions (V01-style Feature View versions)
- Retrieve model metadata

Tested in: tests/test_chapter_10.py
"""


def get_model_logging_template() -> dict:
    """
    Get template for logging model with feature lineage.

    Returns:
        Dict with model logging configuration
    """
    return {
        "registry_database": "FEATURE_STORE_DEMO",
        "registry_schema": "MODEL_REGISTRY",
        "model_name": "churn_model",
        "version_name": "V01",
        "comment": "Trained with USER_ORDER_FV V01, USER_SESSION_FV V01; spine SESSIONS",
        "metrics": {
            "auc": 0.85,
            "precision": 0.78,
            "recall": 0.72,
        },
        "feature_views": [
            {"name": "USER_ORDER_FV", "version": "V01"},
            {"name": "USER_SESSION_FV", "version": "V01"},
        ],
        "recommended_estimators": (
            "Use scikit-learn, XGBoost, or similar directly; avoid snowflake.ml.modeling "
            "estimators for new development."
        ),
    }


def get_lineage_tracking_info() -> dict:
    """
    Get information about lineage tracking capabilities.

    Returns:
        Dict with lineage tracking details
    """
    return {
        "source_to_feature": {
            "mechanism": "Dynamic Table dependencies",
            "view": "INFORMATION_SCHEMA.OBJECT_DEPENDENCIES",
        },
        "feature_to_dataset": {
            "mechanism": "generate_dataset (Snowflake ML Dataset) or generate_training_set + save_as",
            "tracking": "Dataset versions and/or table comments documenting Feature View versions",
        },
        "dataset_to_model": {
            "mechanism": "Model Registry log_model comments/tags",
            "best_practice": "Include Feature View versions (e.g. V01) in model comments",
        },
    }


if __name__ == "__main__":
    template = get_model_logging_template()
    print("Model Logging Template:")
    print(f"  Model: {template['model_name']}")
    print(f"  Version: {template['version_name']}")
    print(f"  Feature Views: {template['feature_views']}")

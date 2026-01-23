"""
Model Registry integration examples.

This module demonstrates how to:
- Log models with feature lineage
- Track feature versions
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
        "model_name": "churn_prediction",
        "version_name": "v1",
        "comment": "Trained with USER_PURCHASE_FV V3, USER_SESSION_FV V2",
        "metrics": {
            "auc": 0.85,
            "precision": 0.78,
            "recall": 0.72,
        },
        "feature_views": [
            {"name": "USER_PURCHASE_FV", "version": "V3"},
            {"name": "USER_SESSION_FV", "version": "V2"},
        ],
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
            "mechanism": "generate_dataset metadata",
            "tracking": "Dataset includes source FV versions",
        },
        "dataset_to_model": {
            "mechanism": "Model Registry comments/tags",
            "best_practice": "Include FV versions in model comments",
        },
    }


if __name__ == "__main__":
    template = get_model_logging_template()
    print("Model Logging Template:")
    print(f"  Model: {template['model_name']}")
    print(f"  Version: {template['version_name']}")
    print(f"  Feature Views: {template['feature_views']}")

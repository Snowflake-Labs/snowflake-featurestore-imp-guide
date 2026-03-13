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


from typing import Any, Dict, List, Optional, Union

from snowflake.ml.model import Model, ModelVersion, task
from snowflake.ml.registry import Registry
from snowflake.ml.feature_store import FeatureStore, FeatureView
from snowflake.snowpark import DataFrame, Session


def log_model_with_feature_lineage(
    session: Session,                                       # Active Snowpark session
    model: Any,                                             # Trained model object (sklearn, xgboost, etc.)
    model_name: str,                                        # Name to identify the model in the registry
    version_name: str = None,                               # Version identifier (auto-generated if None)
    comment: str = None,                                    # Description — include FeatureView names/versions for lineage
    metrics: Dict[str, Any] = None,                         # Evaluation metrics (e.g. {"auc": 0.85, "f1": 0.78})
    sample_input_data: DataFrame = None,                    # Sample data for schema inference and lineage capture
    model_task: task.Task = task.Task.UNKNOWN,               # Task type for ML Observability (e.g. TABULAR_BINARY_CLASSIFICATION)
    conda_dependencies: List[str] = None,                   # Conda packages to deploy with the model
    database_name: str = None,                              # Registry database (defaults to session's current database)
    schema_name: str = None,                                # Registry schema (defaults to session's current schema)
) -> ModelVersion:
    registry = Registry(
        session=session,
        database_name=database_name,
        schema_name=schema_name,
    )
    mv = registry.log_model(
        model=model,
        model_name=model_name,
        version_name=version_name,
        comment=comment,
        metrics=metrics,
        sample_input_data=sample_input_data,
        task=model_task,
        conda_dependencies=conda_dependencies,
    )
    return mv


def run_batch_inference(
    session: Session,                                       # Active Snowpark session
    fs: FeatureStore,                                       # Initialized FeatureStore instance
    model_name: str,                                        # Name of the model in the registry
    model_version: str = None,                              # Version to use (None = default version)
    spine_sql: str = None,                                  # SQL to build the inference spine (entities to score)
    spine_df: DataFrame = None,                             # Pre-built spine DataFrame (alternative to spine_sql)
    features: List[FeatureView] = None,                     # FeatureViews to retrieve for inference
    spine_timestamp_col: str = "EVENT_TS",                  # Timestamp column for PIT lookups
    function_name: str = "predict",                         # Model method to invoke (default: "predict")
    output_table: str = None,                               # If set, saves predictions to this table
    database_name: str = None,                              # Registry database (defaults to session's current database)
    schema_name: str = None,                                # Registry schema (defaults to session's current schema)
) -> DataFrame:
    if spine_df is None and spine_sql is None:
        raise ValueError("Either spine_df or spine_sql must be provided")
    if spine_df is None:
        spine_df = session.sql(spine_sql)

    inference_features = fs.generate_training_set(
        spine_df=spine_df,
        features=features,
        spine_timestamp_col=spine_timestamp_col,
    )

    registry = Registry(
        session=session,
        database_name=database_name,
        schema_name=schema_name,
    )
    model = registry.get_model(model_name)
    mv = model.version(model_version) if model_version else model.default
    predictions = mv.run(inference_features, function_name=function_name)

    if output_table:
        predictions.write.save_as_table(output_table, mode="overwrite")

    return predictions


if __name__ == "__main__":
    template = get_model_logging_template()
    print("Model Logging Template:")
    print(f"  Model: {template['model_name']}")
    print(f"  Version: {template['version_name']}")
    print(f"  Feature Views: {template['feature_views']}")

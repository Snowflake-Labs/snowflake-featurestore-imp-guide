"""
Preprocessing pipeline examples.

This module demonstrates how to:
- Build preprocessing pipelines
- Combine encoders and scalers
- Store pipelines with models

Tested in: tests/test_chapter_09.py
"""


def get_pipeline_config(
    categorical_cols: list,
    numeric_cols: list,
    target_col: str = None,
) -> dict:
    """
    Get a standard preprocessing pipeline configuration.
    
    Args:
        categorical_cols: Columns to one-hot encode
        numeric_cols: Columns to scale
        target_col: Target column (excluded from preprocessing)
        
    Returns:
        Dict with pipeline configuration
    """
    return {
        "steps": [
            {
                "name": "encoder",
                "type": "OneHotEncoder",
                "input_cols": categorical_cols,
                "config": {"drop": "first"},
            },
            {
                "name": "scaler",
                "type": "StandardScaler",
                "input_cols": numeric_cols,
                "config": {},
            },
        ],
        "target_col": target_col,
        "passthrough_cols": [],
    }


def get_scaling_recommendations_by_model() -> dict:
    """
    Get scaling recommendations by model type.
    
    Returns:
        Dict with recommendations
    """
    return {
        "xgboost": {
            "scaling_needed": False,
            "encoding_needed": True,  # For categorical
            "reason": "Tree-based, handles raw values well",
        },
        "random_forest": {
            "scaling_needed": False,
            "encoding_needed": True,
            "reason": "Tree-based, scale-invariant",
        },
        "logistic_regression": {
            "scaling_needed": True,
            "encoding_needed": True,
            "reason": "Gradient-based, benefits from normalization",
        },
        "svm": {
            "scaling_needed": True,
            "encoding_needed": True,
            "reason": "Distance-based, requires normalized features",
        },
        "neural_network": {
            "scaling_needed": True,
            "encoding_needed": True,
            "reason": "Gradient-based, faster convergence with scaling",
        },
    }

######## Building a preprocessing Pipeline ########

import pandas as pd
from snowflake.ml.model import custom_model
from snowflake.ml.modeling.pipeline import Pipeline
from snowflake.ml.modeling.preprocessing import OneHotEncoder, StandardScaler
from snowflake.ml.registry import Registry
from snowflake.snowpark import DataFrame, Session


def build_preprocessing_pipeline(
    train_df: DataFrame,
    inference_df: DataFrame = None,
    categorical_cols: list = None,
    categorical_output_cols: list = None,
    numeric_cols: list = None,
    numeric_output_cols: list = None,
    drop: str = "first",
) -> tuple:
    if categorical_cols is None:
        categorical_cols = ["CATEGORY"]
    if categorical_output_cols is None:
        categorical_output_cols = [f"{col}_OHE" for col in categorical_cols]
    if numeric_cols is None:
        numeric_cols = ["AMOUNT"]
    if numeric_output_cols is None:
        numeric_output_cols = [f"{col}_SCALED" for col in numeric_cols]

    pipeline = Pipeline(steps=[
        ("encoder", OneHotEncoder(
            input_cols=categorical_cols,
            output_cols=categorical_output_cols,
            drop=drop,
            handle_unknown="ignore",
        )),
        ("scaler", StandardScaler(
            input_cols=numeric_cols,
            output_cols=numeric_output_cols,
        )),
    ])

    pipeline.fit(train_df)
    train_preprocessed = pipeline.transform(train_df)

    inference_preprocessed = None
    if inference_df is not None:
        inference_preprocessed = pipeline.transform(inference_df)

    return pipeline, train_preprocessed, inference_preprocessed

##### Saving with Model #####

def log_pipeline_as_model(
    session: Session,
    pipeline: Pipeline,
    model_name: str = "churn_model",
    version_name: str = "v1",
    sample_input_data: DataFrame = None,
):
    registry = Registry(session=session)
    registry.log_model(
        model=pipeline,
        model_name=model_name,
        version_name=version_name,
        sample_input_data=sample_input_data,
    )
    print(f"Pipeline logged as {model_name}/{version_name}")


class PreprocessedModel(custom_model.CustomModel):
    @custom_model.inference_api
    def predict(self, input: pd.DataFrame) -> pd.DataFrame:
        features = self.context["feature_preproc"].transform(input)
        predictions = self.context["my_model"].predict(features)
        return pd.DataFrame({"output": predictions})


def log_custom_model_with_preprocessing(
    session: Session,
    preprocessing_pipeline,
    model,
    model_name: str = "churn_model",
    version_name: str = "v1",
    sample_input_data: DataFrame = None,
):
    mc = custom_model.ModelContext(
        feature_preproc=preprocessing_pipeline,
        my_model=model,
    )
    wrapped_model = PreprocessedModel(context=mc)

    registry = Registry(session=session)
    registry.log_model(
        model=wrapped_model,
        model_name=model_name,
        version_name=version_name,
        sample_input_data=sample_input_data,
    )
    print(f"Custom model with preprocessing logged as {model_name}/{version_name}")


if __name__ == "__main__":
    recs = get_scaling_recommendations_by_model()
    print("Scaling Recommendations by Model:")
    for model, config in recs.items():
        print(f"\n{model}:")
        print(f"  Scaling needed: {config['scaling_needed']}")
        print(f"  Encoding needed: {config['encoding_needed']}")

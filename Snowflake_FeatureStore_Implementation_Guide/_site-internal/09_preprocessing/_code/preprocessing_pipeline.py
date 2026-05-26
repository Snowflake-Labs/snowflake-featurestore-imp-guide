"""
Preprocessing pipeline examples (clickstream sample).

Prefer sklearn.pipeline.Pipeline + ColumnTransformer, then Registry.log_model().
See chapter E5: snowflake.ml.modeling.pipeline.Pipeline is a separate API.

Canonical context: FEATURE_STORE_DEMO.FEATURE_STORE, source CLICKSTREAM_DATA,
warehouse FS_DEV_WH.

This module demonstrates how to:
- Build preprocessing pipelines
- Combine encoders and scalers on EVENT_TYPE, PAYMENT_METHOD, DEVICE_TYPE, etc.
- Store pipelines with models (via Model Registry logging)

Tested in: tests/test_chapter_09.py
"""

from encoding import (
    ONEHOT_COLUMNS,
    ORDINAL_COLUMNS,
    ORDINAL_CATEGORIES,
)

NUMERIC_SCALE_COLUMNS = ["TOTAL_AMT", "DURATION_SEC", "ITEM_CNT"]


def get_pipeline_config(
    categorical_cols: list | None = None,
    numeric_cols: list | None = None,
    ordinal_cols: list | None = None,
    target_col: str | None = None,
) -> dict:
    """
    Get a standard preprocessing pipeline configuration (sklearn-oriented).

    Args:
        categorical_cols: Nominal columns to one-hot; default clickstream set
        numeric_cols: Columns to standard-scale; default TOTAL_AMT,
            DURATION_SEC, ITEM_CNT
        ordinal_cols: Ordinal columns; default SUBSCRIPTION_STATUS,
            INCOME_BRACKET
        target_col: Target column (excluded from preprocessing)

    Returns:
        Dict with pipeline configuration
    """
    cat = (
        list(categorical_cols)
        if categorical_cols is not None
        else list(ONEHOT_COLUMNS)
    )
    num = (
        list(numeric_cols)
        if numeric_cols is not None
        else list(NUMERIC_SCALE_COLUMNS)
    )
    ord_ = (
        list(ordinal_cols)
        if ordinal_cols is not None
        else list(ORDINAL_COLUMNS)
    )

    return {
        "database": "FEATURE_STORE_DEMO",
        "schema": "FEATURE_STORE",
        "source": "CLICKSTREAM_DATA",
        "warehouse": "FS_DEV_WH",
        "feature_view_version_format": "V01",
        "steps": [
            {
                "name": "onehot",
                "type": "sklearn.preprocessing.OneHotEncoder",
                "input_cols": cat,
                "output_naming": "_OHE",
                "config": {
                    "drop": "first",
                    "handle_unknown": "ignore",
                    "sparse_output": False,
                },
            },
            {
                "name": "ordinal",
                "type": "sklearn.preprocessing.OrdinalEncoder",
                "input_cols": ord_,
                "output_naming": "_ENCODED",
                "config": {
                    "categories": [ORDINAL_CATEGORIES[c] for c in ord_],
                },
            },
            {
                "name": "scaler",
                "type": "sklearn.preprocessing.StandardScaler",
                "input_cols": num,
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


if __name__ == "__main__":
    recs = get_scaling_recommendations_by_model()
    print("Scaling Recommendations by Model:")
    for model, config in recs.items():
        print(f"\n{model}:")
        print(f"  Scaling needed: {config['scaling_needed']}")
        print(f"  Encoding needed: {config['encoding_needed']}")

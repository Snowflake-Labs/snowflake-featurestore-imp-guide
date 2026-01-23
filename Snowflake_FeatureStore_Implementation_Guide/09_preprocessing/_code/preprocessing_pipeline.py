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


if __name__ == "__main__":
    recs = get_scaling_recommendations_by_model()
    print("Scaling Recommendations by Model:")
    for model, config in recs.items():
        print(f"\n{model}:")
        print(f"  Scaling needed: {config['scaling_needed']}")
        print(f"  Encoding needed: {config['encoding_needed']}")

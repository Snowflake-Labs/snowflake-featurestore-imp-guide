"""
Encoding examples for categorical features.

This module demonstrates how to:
- Apply one-hot encoding
- Apply ordinal encoding
- Choose the right encoding

Tested in: tests/test_chapter_09.py
"""


def get_encoding_recommendations() -> dict:
    """
    Get encoding recommendations by scenario.
    
    Returns:
        Dict with encoding recommendations
    """
    return {
        "nominal_categories": {
            "encoding": "OneHotEncoder",
            "example_columns": ["COLOR", "BRAND", "CATEGORY"],
            "reason": "No inherent order, need separate binary columns",
        },
        "ordinal_categories": {
            "encoding": "OrdinalEncoder",
            "example_columns": ["SIZE", "RATING", "PRIORITY"],
            "reason": "Has inherent order (S < M < L)",
        },
        "high_cardinality": {
            "encoding": "TargetEncoder or Embedding",
            "example_columns": ["ZIP_CODE", "USER_ID"],
            "reason": "Too many categories for one-hot",
        },
        "binary_categories": {
            "encoding": "LabelEncoder or Binary",
            "example_columns": ["GENDER", "IS_ACTIVE"],
            "reason": "Only two values, simple binary encoding",
        },
    }


def get_one_hot_config(
    columns: list,
    drop_first: bool = True,
) -> dict:
    """
    Get configuration for one-hot encoding.
    
    Args:
        columns: Columns to encode
        drop_first: Whether to drop first category (avoid multicollinearity)
        
    Returns:
        Dict with encoder configuration
    """
    return {
        "encoder": "OneHotEncoder",
        "input_cols": columns,
        "output_cols": [f"{col}_ENCODED" for col in columns],
        "drop": "first" if drop_first else None,
        "handle_unknown": "ignore",
    }


if __name__ == "__main__":
    recs = get_encoding_recommendations()
    print("Encoding Recommendations:")
    for scenario, config in recs.items():
        print(f"\n{scenario}:")
        print(f"  Encoding: {config['encoding']}")
        print(f"  Example columns: {config['example_columns']}")

"""
Encoding examples for categorical features (clickstream sample).

Canonical context: FEATURE_STORE_DEMO.FEATURE_STORE, source CLICKSTREAM_DATA,
warehouse FS_DEV_WH.
Naming: one-hot expanded columns use _OHE; ordinal outputs use _ENCODED.

This module demonstrates how to:
- Apply one-hot encoding (EVENT_TYPE, PAYMENT_METHOD, DEVICE_TYPE)
- Apply ordinal encoding (SUBSCRIPTION_STATUS, INCOME_BRACKET)
- Choose the right encoding

Tested in: tests/test_chapter_09.py
"""

CLICKSTREAM_DB = "FEATURE_STORE_DEMO"
CLICKSTREAM_SCHEMA = "FEATURE_STORE"
CLICKSTREAM_SOURCE = "CLICKSTREAM_DATA"
CLICKSTREAM_WH = "FS_DEV_WH"

ONEHOT_COLUMNS = ["EVENT_TYPE", "PAYMENT_METHOD", "DEVICE_TYPE"]

ORDINAL_COLUMNS = ["SUBSCRIPTION_STATUS", "INCOME_BRACKET"]

ORDINAL_CATEGORIES = {
    "SUBSCRIPTION_STATUS": ["none", "basic", "premium"],
    "INCOME_BRACKET": ["low", "medium", "high", "premium"],
}


def get_encoding_recommendations() -> dict:
    """
    Get encoding recommendations by scenario.

    Returns:
        Dict with encoding recommendations
    """
    return {
        "nominal_categories": {
            "encoding": "OneHotEncoder",
            "example_columns": ONEHOT_COLUMNS,
            "reason": (
                "No inherent order; expand to binary columns with _OHE naming"
            ),
        },
        "ordinal_categories": {
            "encoding": "OrdinalEncoder",
            "example_columns": ORDINAL_COLUMNS,
            "reason": (
                "Fixed order (e.g. none < basic < premium; "
                "low < medium < high < premium)"
            ),
        },
        "high_cardinality": {
            "encoding": "TargetEncoder or Embedding",
            "example_columns": ["PRODUCT_ID", "USER_ID"],
            "reason": "Too many categories for one-hot",
        },
        "binary_categories": {
            "encoding": "LabelEncoder or Binary",
            "example_columns": ["IS_CONVERTED", "IS_PREMIUM"],
            "reason": "Only two values, simple binary encoding",
        },
    }


def get_one_hot_config(
    columns: list | None = None,
    drop_first: bool = True,
) -> dict:
    """
    Get configuration for one-hot encoding (sklearn-style).

    Args:
        columns: Columns to encode; defaults to clickstream nominal columns
        drop_first: Whether to drop first category (avoid multicollinearity)

    Returns:
        Dict with encoder configuration
    """
    cols = columns if columns is not None else list(ONEHOT_COLUMNS)
    return {
        "encoder": "sklearn.preprocessing.OneHotEncoder",
        "input_cols": cols,
        "output_naming": "_OHE",
        "drop": "first" if drop_first else None,
        "handle_unknown": "ignore",
        "sparse_output": False,
    }


def get_ordinal_config() -> dict:
    """Ordinal encoding config for clickstream ordered fields."""
    return {
        "encoder": "sklearn.preprocessing.OrdinalEncoder",
        "input_cols": list(ORDINAL_COLUMNS),
        "output_naming": "_ENCODED",
        "categories": [ORDINAL_CATEGORIES[c] for c in ORDINAL_COLUMNS],
    }


if __name__ == "__main__":
    recs = get_encoding_recommendations()
    print("Encoding Recommendations:")
    for scenario, config in recs.items():
        print(f"\n{scenario}:")
        print(f"  Encoding: {config['encoding']}")
        print(f"  Example columns: {config['example_columns']}")

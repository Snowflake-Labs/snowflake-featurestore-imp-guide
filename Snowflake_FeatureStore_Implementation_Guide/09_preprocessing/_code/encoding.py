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

import numpy as np
from snowflake.ml.modeling.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler, MinMaxScaler
from snowflake.snowpark import DataFrame


def one_hot_encode(
    train_df: DataFrame,
    inference_df: DataFrame = None,
    input_cols: list = None,
    output_cols: list = None,
    drop: str = "first",
) -> tuple:
    if input_cols is None:
        input_cols = ["CATEGORY"]
    if output_cols is None:
        output_cols = [f"{col}_OHE" for col in input_cols]

    encoder = OneHotEncoder(
        input_cols=input_cols,
        output_cols=output_cols,
        drop=drop,
        handle_unknown="ignore",
    )

    encoder.fit(train_df)
    train_encoded = encoder.transform(train_df)

    inference_encoded = None
    if inference_df is not None:
        inference_encoded = encoder.transform(inference_df)

    return encoder, train_encoded, inference_encoded


def ordinal_encode(
    train_df: DataFrame,
    inference_df: DataFrame = None,
    input_cols: list = None,
    output_cols: list = None,
    categories: dict = None,
) -> tuple:
    if input_cols is None:
        input_cols = ["SIZE"]
    if output_cols is None:
        output_cols = [f"{col}_ORD" for col in input_cols]
    if categories is None:
        categories = {"SIZE": np.array(["S", "M", "L", "XL"])}

    encoder = OrdinalEncoder(
        input_cols=input_cols,
        output_cols=output_cols,
        categories=categories,
        handle_unknown="use_encoded_value",
        unknown_value=-1,
    )

    encoder.fit(train_df)
    train_encoded = encoder.transform(train_df)

    inference_encoded = None
    if inference_df is not None:
        inference_encoded = encoder.transform(inference_df)

    return encoder, train_encoded, inference_encoded


def standard_scale(
    train_df: DataFrame,
    inference_df: DataFrame = None,
    input_cols: list = None,
    output_cols: list = None,
    with_mean: bool = True,
    with_std: bool = True,
) -> tuple:
    if input_cols is None:
        input_cols = ["PURCHASE_AMOUNT", "SESSION_DURATION"]
    if output_cols is None:
        output_cols = [f"{col}_SCALED" for col in input_cols]

    scaler = StandardScaler(
        input_cols=input_cols,
        output_cols=output_cols,
        with_mean=with_mean,
        with_std=with_std,
    )

    scaler.fit(train_df)
    train_scaled = scaler.transform(train_df)

    inference_scaled = None
    if inference_df is not None:
        inference_scaled = scaler.transform(inference_df)

    return scaler, train_scaled, inference_scaled


def min_max_scale(
    train_df: DataFrame,
    inference_df: DataFrame = None,
    input_cols: list = None,
    output_cols: list = None,
    feature_range: tuple = (0, 1),
    clip: bool = False,
) -> tuple:
    if input_cols is None:
        input_cols = ["PRICE", "QUANTITY"]
    if output_cols is None:
        output_cols = [f"{col}_MINMAX" for col in input_cols]

    scaler = MinMaxScaler(
        input_cols=input_cols,
        output_cols=output_cols,
        feature_range=feature_range,
        clip=clip,
    )

    scaler.fit(train_df)
    train_scaled = scaler.transform(train_df)

    inference_scaled = None
    if inference_df is not None:
        inference_scaled = scaler.transform(inference_df)

    return scaler, train_scaled, inference_scaled


if __name__ == "__main__":
    recs = get_encoding_recommendations()
    print("Encoding Recommendations:")
    for scenario, config in recs.items():
        print(f"\n{scenario}:")
        print(f"  Encoding: {config['encoding']}")
        print(f"  Example columns: {config['example_columns']}")

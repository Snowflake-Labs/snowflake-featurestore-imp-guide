"""
Temporal correctness validation utilities.

This module demonstrates how to:
- Detect data leakage in training datasets
- Validate PIT correctness
- Audit temporal joins

Tested in: tests/test_chapter_06.py
"""
from snowflake.snowpark import DataFrame
from snowflake.snowpark import functions as F


def validate_no_data_leakage(
    training_df: DataFrame,
    spine_timestamp_col: str,
    feature_timestamp_col: str,
) -> dict:
    """
    Validate that no features have timestamps after the spine timestamp.
    
    Data leakage occurs when features computed from future data are used
    to predict past events.
    
    Args:
        training_df: Generated training dataset
        spine_timestamp_col: Spine timestamps (e.g. EVENT_TS from SESSIONS)
        feature_timestamp_col: Feature View PIT column (e.g. LAST_EVENT_TS, LAST_ORDER_TS)
        
    Returns:
        Dict with validation results
    """
    total_rows = training_df.count()
    
    # Check for any features with timestamps after spine timestamp
    leakage_df = training_df.filter(
        F.col(feature_timestamp_col) > F.col(spine_timestamp_col)
    )
    
    leakage_count = leakage_df.count()
    
    return {
        "valid": leakage_count == 0,
        "leakage_count": leakage_count,
        "total_rows": total_rows,
        "leakage_percentage": (leakage_count / total_rows * 100) if total_rows > 0 else 0,
    }


def get_temporal_join_stats(
    training_df: DataFrame,
    spine_timestamp_col: str,
    feature_timestamp_col: str,
) -> dict:
    """
    Get statistics about the temporal joins in a training dataset.
    
    Args:
        training_df: Generated training dataset
        spine_timestamp_col: Column with spine timestamps
        feature_timestamp_col: Column with feature timestamps
        
    Returns:
        Dict with temporal join statistics
    """
    stats_df = training_df.select(
        F.count("*").alias("total_rows"),
        F.avg(
            F.datediff("second", F.col(feature_timestamp_col), F.col(spine_timestamp_col))
        ).alias("avg_lag_seconds"),
        F.max(
            F.datediff("second", F.col(feature_timestamp_col), F.col(spine_timestamp_col))
        ).alias("max_lag_seconds"),
        F.min(
            F.datediff("second", F.col(feature_timestamp_col), F.col(spine_timestamp_col))
        ).alias("min_lag_seconds"),
    ).collect()[0]
    
    return {
        "total_rows": stats_df["TOTAL_ROWS"],
        "avg_lag_seconds": stats_df["AVG_LAG_SECONDS"],
        "max_lag_seconds": stats_df["MAX_LAG_SECONDS"],
        "min_lag_seconds": stats_df["MIN_LAG_SECONDS"],
    }


if __name__ == "__main__":
    print("Validation utilities require an active Snowflake session.")

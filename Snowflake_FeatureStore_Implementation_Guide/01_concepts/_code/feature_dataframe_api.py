"""
Feature definition using Snowpark DataFrame API.

This module demonstrates how to:
- Define features using Snowpark DataFrame transformations
- Use aggregations, joins, and derived columns
- Create Feature Views from DataFrame-defined features

Tested in: tests/test_chapter_01.py::TestFeatureDefinition
"""
from snowflake.snowpark import Session, DataFrame
from snowflake.snowpark import functions as F
from snowflake.ml.feature_store import FeatureView, Entity


def create_user_purchase_features_df(
    session: Session,
    source_table: str = "ORDERS",
) -> DataFrame:
    """
    Create a DataFrame defining user purchase features.
    
    This demonstrates the DataFrame API approach to feature definition.
    
    Args:
        session: Active Snowpark session
        source_table: Name of the source orders table
        
    Returns:
        Snowpark DataFrame with feature columns
    """
    return (
        session.table(source_table)
        .group_by("USER_ID")
        .agg(
            F.sum("AMOUNT").alias("TOTAL_SPEND"),
            F.count("ORDER_ID").alias("ORDER_CNT"),
            F.avg("AMOUNT").alias("AVG_ORDER_AMT"),
            F.max("ORDER_TS").alias("LAST_ORDER_TS"),
        )
    )


def create_user_behavior_features_df(
    session: Session,
    orders_table: str = "ORDERS",
    sessions_table: str = "SESSIONS",
) -> DataFrame:
    """
    Create a DataFrame with joined features from multiple sources.
    
    This demonstrates joining data from multiple tables to create features.
    
    Args:
        session: Active Snowpark session
        orders_table: Name of the source orders table
        sessions_table: Name of the source sessions table
        
    Returns:
        Snowpark DataFrame with combined features
    """
    # Aggregate orders
    order_features = (
        session.table(orders_table)
        .group_by("USER_ID")
        .agg(
            F.sum("AMOUNT").alias("TOTAL_SPEND"),
            F.count("ORDER_ID").alias("ORDER_CNT"),
        )
    )
    
    # Aggregate sessions
    session_features = (
        session.table(sessions_table)
        .group_by("USER_ID")
        .agg(
            F.count("SESSION_ID").alias("SESSION_CNT"),
            F.avg("SESSION_DURATION_SEC").alias("AVG_SESSION_DUR"),
        )
    )
    
    # Join features
    return order_features.join(
        session_features,
        on="USER_ID",
        how="outer"
    )


def create_derived_features_df(
    session: Session,
    source_table: str = "ORDERS",
) -> DataFrame:
    """
    Create a DataFrame with derived (calculated) features.
    
    This demonstrates creating new features from existing columns.
    
    Args:
        session: Active Snowpark session
        source_table: Name of the source orders table
        
    Returns:
        Snowpark DataFrame with derived features
    """
    return (
        session.table(source_table)
        .group_by("USER_ID")
        .agg(
            F.sum("AMOUNT").alias("TOTAL_SPEND"),
            F.count("ORDER_ID").alias("ORDER_CNT"),
            F.sum("DISCOUNT").alias("TOTAL_DISCOUNT"),
            F.max("ORDER_TS").alias("LAST_ORDER_TS"),
        )
        # Add derived features
        .with_column(
            "AVG_ORDER_VALUE",
            F.col("TOTAL_SPEND") / F.col("ORDER_CNT")
        )
        .with_column(
            "DISCOUNT_RATE",
            F.col("TOTAL_DISCOUNT") / F.col("TOTAL_SPEND")
        )
    )


if __name__ == "__main__":
    print("Feature DataFrame examples require an active Snowflake session.")
    print("See tests/test_chapter_01.py for integration tests.")

"""
FeatureView creation examples.

This module demonstrates how to:
- Create FeatureViews with Dynamic Table backing (materialized)
- Create FeatureViews with View backing (query-time)
- Register FeatureViews in the Feature Store

Tested in: tests/test_chapter_01.py::TestFeatureViewExamples

Note: These functions require an active Snowflake session and Feature Store.
"""
from snowflake.snowpark import Session, DataFrame
from snowflake.snowpark import functions as F
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_user_purchase_featureview(
    session: Session,
    user_entity: Entity,
    source_table: str = "ORDERS",
) -> FeatureView:
    """
    Create a FeatureView for user purchase statistics.
    
    This creates a Dynamic Table-backed FeatureView that refreshes hourly.
    
    Args:
        session: Active Snowpark session
        user_entity: Entity for user-level features
        source_table: Name of the source orders table
        
    Returns:
        FeatureView (not yet registered)
    """
    # Define feature transformations using DataFrame API
    user_purchase_df = (
        session.table(source_table)
        .group_by("USER_ID")
        .agg(
            F.sum("AMOUNT").alias("TOTAL_SPEND"),
            F.count("ORDER_ID").alias("ORDER_CNT"),
            F.avg("AMOUNT").alias("AVG_ORDER_AMT"),
            F.max("ORDER_TS").alias("LAST_ORDER_TS"),
        )
    )
    
    # Create FeatureView with Dynamic Table backing
    return FeatureView(
        name="USER_PURCHASE_FEATURES",
        entities=[user_entity],
        feature_df=user_purchase_df,
        timestamp_col="LAST_ORDER_TS",
        refresh_freq="1 hour",  # Dynamic Table refresh frequency
        desc="User purchase behavior features"
    )


def create_user_session_featureview(
    session: Session,
    user_entity: Entity,
    source_table: str = "SESSIONS",
) -> FeatureView:
    """
    Create a FeatureView for user session statistics.
    
    This creates a View-backed FeatureView (query-time computation).
    
    Args:
        session: Active Snowpark session
        user_entity: Entity for user-level features
        source_table: Name of the source sessions table
        
    Returns:
        FeatureView (not yet registered)
    """
    # Define feature transformations
    user_session_df = (
        session.table(source_table)
        .group_by("USER_ID")
        .agg(
            F.count("SESSION_ID").alias("SESSION_CNT"),
            F.avg("SESSION_DURATION_SEC").alias("AVG_SESSION_DUR"),
            F.sum("PAGE_VIEW_CNT").alias("TOTAL_PAGE_VIEWS"),
            F.max("SESSION_END_TS").alias("LAST_SESSION_TS"),
        )
    )
    
    # Create FeatureView WITHOUT refresh_freq = View-backed
    return FeatureView(
        name="USER_SESSION_FEATURES",
        entities=[user_entity],
        feature_df=user_session_df,
        timestamp_col="LAST_SESSION_TS",
        # No refresh_freq = View-backed (query-time computation)
        desc="User session behavior features"
    )


def register_featureview(
    fs: FeatureStore,
    feature_view: FeatureView,
    version: str = "V1",
    block: bool = True,
) -> FeatureView:
    """
    Register a FeatureView in the Feature Store.
    
    Args:
        fs: Feature Store instance
        feature_view: FeatureView to register
        version: Version string (e.g., "V1", "V01")
        block: If True, wait for initial materialization
        
    Returns:
        Registered FeatureView
    """
    return fs.register_feature_view(
        feature_view=feature_view,
        version=version,
        block=block,
    )


if __name__ == "__main__":
    print("FeatureView examples require an active Snowflake session.")
    print("See tests/test_chapter_01.py for integration tests.")

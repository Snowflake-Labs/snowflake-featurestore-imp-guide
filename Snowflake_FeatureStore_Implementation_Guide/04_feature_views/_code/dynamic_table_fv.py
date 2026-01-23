"""
Dynamic Table FeatureView examples.

This module demonstrates how to:
- Create Dynamic Table-backed FeatureViews
- Configure refresh frequencies
- Monitor DT refresh status

Tested in: tests/test_chapter_04.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity


def create_dt_featureview(
    session: Session,
    entity: Entity,
    source_query: str,
    timestamp_col: str,
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Create a Dynamic Table-backed FeatureView.
    
    Args:
        session: Active Snowpark session
        entity: Entity for the FeatureView
        source_query: SQL query defining features
        timestamp_col: Column for PIT retrieval
        refresh_freq: Refresh frequency
        
    Returns:
        FeatureView (not yet registered)
    """
    feature_df = session.sql(source_query)
    
    return FeatureView(
        name="USER_PURCHASE_FEATURES",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        desc="User purchase behavior - auto-refreshed"
    )


def create_view_featureview(
    session: Session,
    entity: Entity,
    source_table: str,
    timestamp_col: str,
) -> FeatureView:
    """
    Create a View-based FeatureView (no refresh_freq).
    
    Args:
        session: Active Snowpark session
        entity: Entity for the FeatureView
        source_table: Source table name
        timestamp_col: Column for PIT retrieval
        
    Returns:
        FeatureView (not yet registered)
    """
    feature_df = session.table(source_table)
    
    return FeatureView(
        name="PRODUCT_ATTRIBUTES",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        # No refresh_freq → View-based
        desc="Product attributes - computed on query"
    )


if __name__ == "__main__":
    print("FeatureView examples require an active Snowflake session.")

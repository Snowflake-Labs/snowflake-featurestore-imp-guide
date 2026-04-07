"""
Dynamic Table and View Feature View examples (clickstream canonical patterns).

This module demonstrates how to:
- Create View-based Feature Views (refresh_freq None / omitted)
- Create Dynamic Table-backed Feature Views (time-period refresh_freq → TARGET_LAG)
- Create CRON-scheduled Feature Views (Dynamic Table + Task)
- Use FEATURE_STORE_DEMO.CLICKSTREAM_DATA tables and naming conventions

Tested in: tests/test_chapter_04.py
"""
from typing import Optional

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity

# Canonical environment (see Chapter 00 setup_session)
SOURCE_DATABASE = "FEATURE_STORE_DEMO"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
FEATURE_STORE_SCHEMA = "FEATURE_STORE"
WAREHOUSE = "FS_DEV_WH"

CLICKSTREAM_ORDERS = f"{SOURCE_DATABASE}.{SOURCE_SCHEMA}.ORDERS"
CLICKSTREAM_PRODUCTS = f"{SOURCE_DATABASE}.{SOURCE_SCHEMA}.PRODUCTS"


def default_user_order_aggregates_sql(
    orders_table: str = CLICKSTREAM_ORDERS,
) -> str:
    """SQL for USER features from ORDERS (TOTAL_AMT, _CNT, _AVG, _TS)."""
    return f"""
        SELECT
            USER_ID,
            SUM(TOTAL_AMT) AS ORDER_TOTAL_AMT_SUM,
            COUNT(ORDER_ID) AS ORDER_CNT,
            AVG(TOTAL_AMT) AS ORDER_TOTAL_AMT_AVG,
            MAX(ORDER_TS) AS LAST_ORDER_TS
        FROM {orders_table}
        GROUP BY USER_ID
    """


def create_dt_featureview(
    session: Session,
    entity: Entity,
    source_query: Optional[str] = None,
    timestamp_col: str = "LAST_ORDER_TS",
    refresh_freq: str = "1 hour",
) -> FeatureView:
    """
    Create a Dynamic Table-backed Feature View (period refresh → TARGET_LAG).

    Args:
        session: Active Snowpark session
        entity: Entity for the Feature View (e.g. USER)
        source_query: SQL defining features; defaults to ORDERS aggregates
        timestamp_col: Column for point-in-time retrieval
        refresh_freq: Snowflake period string (e.g. "1 hour", "15 minutes")

    Returns:
        Feature View (not yet registered)
    """
    q = (
        source_query
        if source_query is not None
        else default_user_order_aggregates_sql()
    )
    feature_df = session.sql(q)

    return FeatureView(
        name="USER_ORDER_FV",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        desc=(
            "USER orders from CLICKSTREAM_DATA.ORDERS; "
            "Dynamic Table (TARGET_LAG)"
        ),
    )


def create_cron_featureview(
    session: Session,
    entity: Entity,
    source_query: Optional[str] = None,
    timestamp_col: str = "LAST_ORDER_TS",
    refresh_freq: str = "0 8 * * *",
) -> FeatureView:
    """
    Create a Feature View with CRON refresh_freq (Dynamic Table + Task).

    Snowflake creates a Dynamic Table (initial full refresh), suspends it for
    ongoing refreshes, and attaches a Task that runs on the CRON schedule.

    Args:
        session: Active Snowpark session
        entity: Entity for the Feature View (e.g. USER)
        source_query: SQL defining features; defaults to ORDERS aggregates
        timestamp_col: Column for point-in-time retrieval
        refresh_freq: CRON expression (e.g. daily at 08:00 UTC)

    Returns:
        Feature View (not yet registered)
    """
    q = (
        source_query
        if source_query is not None
        else default_user_order_aggregates_sql()
    )
    feature_df = session.sql(q)

    return FeatureView(
        name="USER_ORDER_FV",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        desc="USER orders; Dynamic Table + Task (CRON)",
    )


def create_view_featureview(
    session: Session,
    entity: Entity,
    source_table: str = CLICKSTREAM_PRODUCTS,
    timestamp_col: str = "UPDATED_TS",
) -> FeatureView:
    """
    Create a View-based Feature View (refresh_freq None: query-time).

    Args:
        session: Active Snowpark session
        entity: Entity for the Feature View (e.g. PRODUCT)
        source_table: Fully qualified PRODUCTS table
        timestamp_col: Column for point-in-time retrieval (e.g. UPDATED_TS)

    Returns:
        Feature View (not yet registered)
    """
    feature_df = session.table(source_table)

    return FeatureView(
        name="PRODUCT_CATALOG_FV",
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=None,
        desc=(
            "PRODUCT attributes from CLICKSTREAM_DATA.PRODUCTS; "
            "View (query-time)"
        ),
    )


if __name__ == "__main__":
    print("Feature View examples require an active Snowflake session.")

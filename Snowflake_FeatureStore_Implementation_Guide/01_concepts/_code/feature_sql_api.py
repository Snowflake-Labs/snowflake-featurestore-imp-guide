"""
Feature definition using pure SQL via session.sql().

This module demonstrates how to:
- Define features using SQL queries
- Use complex SQL constructs (window functions, CTEs)
- Create FeatureViews from SQL-defined DataFrames

Tested in: tests/test_chapter_01.py::TestFeatureDefinition
"""
from snowflake.snowpark import Session, DataFrame


def create_user_purchase_features_sql(
    session: Session,
    source_table: str = "ORDERS",
) -> DataFrame:
    """
    Create a DataFrame defining user purchase features using SQL.
    
    This demonstrates the session.sql() approach to feature definition.
    
    Args:
        session: Active Snowpark session
        source_table: Name of the source orders table
        
    Returns:
        Snowpark DataFrame with feature columns
    """
    return session.sql(f"""
        SELECT 
            USER_ID,
            COUNT(DISTINCT ORDER_ID) AS ORDER_CNT,
            SUM(AMOUNT) AS TOTAL_SPEND,
            AVG(AMOUNT) AS AVG_ORDER_AMT,
            MAX(ORDER_TS) AS LAST_ORDER_TS,
            DATEDIFF('day', MIN(ORDER_TS), MAX(ORDER_TS)) AS CUSTOMER_TENURE_DAYS
        FROM {source_table}
        GROUP BY USER_ID
    """)


def create_user_rfm_features_sql(
    session: Session,
    source_table: str = "ORDERS",
) -> DataFrame:
    """
    Create RFM (Recency, Frequency, Monetary) features using SQL.
    
    This demonstrates more complex SQL with window functions.
    
    Args:
        session: Active Snowpark session
        source_table: Name of the source orders table
        
    Returns:
        Snowpark DataFrame with RFM features
    """
    return session.sql(f"""
        WITH user_metrics AS (
            SELECT 
                USER_ID,
                COUNT(DISTINCT ORDER_ID) AS FREQUENCY,
                SUM(AMOUNT) AS MONETARY,
                MAX(ORDER_TS) AS LAST_ORDER_TS,
                DATEDIFF('day', MAX(ORDER_TS), CURRENT_TIMESTAMP()) AS RECENCY_DAYS
            FROM {source_table}
            GROUP BY USER_ID
        ),
        user_percentiles AS (
            SELECT
                USER_ID,
                FREQUENCY,
                MONETARY,
                RECENCY_DAYS,
                LAST_ORDER_TS,
                NTILE(5) OVER (ORDER BY RECENCY_DAYS DESC) AS R_SCORE,
                NTILE(5) OVER (ORDER BY FREQUENCY) AS F_SCORE,
                NTILE(5) OVER (ORDER BY MONETARY) AS M_SCORE
            FROM user_metrics
        )
        SELECT
            USER_ID,
            FREQUENCY,
            MONETARY,
            RECENCY_DAYS,
            LAST_ORDER_TS,
            R_SCORE,
            F_SCORE,
            M_SCORE,
            (R_SCORE + F_SCORE + M_SCORE) AS RFM_SCORE
        FROM user_percentiles
    """)


def create_user_window_features_sql(
    session: Session,
    source_table: str = "ORDERS",
) -> DataFrame:
    """
    Create features using SQL window functions.
    
    This demonstrates window functions for time-based features.
    
    Args:
        session: Active Snowpark session
        source_table: Name of the source orders table
        
    Returns:
        Snowpark DataFrame with window-based features
    """
    return session.sql(f"""
        SELECT DISTINCT
            USER_ID,
            -- Running totals
            SUM(AMOUNT) OVER (
                PARTITION BY USER_ID 
                ORDER BY ORDER_TS 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS CUMULATIVE_SPEND,
            
            -- Order sequence
            ROW_NUMBER() OVER (
                PARTITION BY USER_ID 
                ORDER BY ORDER_TS
            ) AS ORDER_SEQUENCE,
            
            -- Days since previous order
            DATEDIFF('day', 
                LAG(ORDER_TS) OVER (PARTITION BY USER_ID ORDER BY ORDER_TS),
                ORDER_TS
            ) AS DAYS_SINCE_PREV_ORDER,
            
            -- Latest timestamp for PIT
            MAX(ORDER_TS) OVER (PARTITION BY USER_ID) AS LAST_ORDER_TS
            
        FROM {source_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY USER_ID 
            ORDER BY ORDER_TS DESC
        ) = 1
    """)


if __name__ == "__main__":
    print("Feature SQL examples require an active Snowflake session.")
    print("See tests/test_chapter_01.py for integration tests.")

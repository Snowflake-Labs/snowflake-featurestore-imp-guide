"""
dbt-sourced Feature View – external pipeline pattern (Ch 05).

Demonstrates a View-based FV sitting on top of a table managed by an
external pipeline (dbt, Airflow, Matillion, etc.).  The Feature Store
owns the *feature definition*; the external tool owns the *transformation*.

Feature Views:
    USER_ORDER_SUMMARY_DBT – View-based, USER entity, from dbt-managed table
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView

from .config import get_config
from .entities import user_entity

# The dbt model materialises this table.  NB 01 creates a simulated version
# if the dbt service is not available.
DBT_TABLE_NAME = "USER_ORDER_SUMMARY"


def create_simulated_dbt_table(session: Session, env: str = "DEV") -> None:
    """Create the table that would normally be produced by a dbt model.

    This is a fallback for environments without the dbt service.  The SQL
    mirrors what a simple dbt model would produce: a cleaned, deduped
    aggregation of order data per user.
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    target_fqn = f"{db}.{src}.{DBT_TABLE_NAME}"

    session.sql(f"""
        CREATE OR REPLACE TABLE {target_fqn} AS
        SELECT
            USER_ID,
            COUNT(DISTINCT ORDER_ID)                         AS TOTAL_ORDER_CNT,
            SUM(TOTAL_AMT)                                   AS LIFETIME_REVENUE_SUM,
            AVG(TOTAL_AMT)                                   AS AVG_ORDER_VALUE,
            MIN(ORDER_TS)                                    AS FIRST_ORDER_TS,
            MAX(ORDER_TS)                                    AS LAST_ORDER_TS,
            COUNT(DISTINCT DATE_TRUNC('month', ORDER_TS))    AS ACTIVE_MONTHS_CNT,
            CURRENT_TIMESTAMP()                              AS _DBT_UPDATED_TS
        FROM {db}.{src}.ORDERS
        GROUP BY USER_ID
    """).collect()


def user_order_summary_dbt(
    session: Session,
    env: str = "DEV",
) -> FeatureView:
    """Feature View on a dbt-managed aggregation table (View-based).

    The timestamp column ``_DBT_UPDATED_TS`` follows the convention where
    external tools stamp the row-level freshness.
    """
    cfg = get_config(env)
    source = f"{cfg['database']}.{cfg['source_schema']}.{DBT_TABLE_NAME}"
    df = session.sql(f"""
        SELECT
            USER_ID,
            TOTAL_ORDER_CNT,
            LIFETIME_REVENUE_SUM,
            AVG_ORDER_VALUE,
            ACTIVE_MONTHS_CNT,
            DATEDIFF('day', FIRST_ORDER_TS, LAST_ORDER_TS)   AS ORDER_SPAN_DAYS,
            _DBT_UPDATED_TS
        FROM {source}
    """)
    return FeatureView(
        name="USER_ORDER_SUMMARY_DBT",
        entities=[user_entity()],
        feature_df=df,
        timestamp_col="_DBT_UPDATED_TS",
        refresh_freq=None,
        desc="Order summary from external dbt pipeline – View-based (external pipeline demo)",
    )

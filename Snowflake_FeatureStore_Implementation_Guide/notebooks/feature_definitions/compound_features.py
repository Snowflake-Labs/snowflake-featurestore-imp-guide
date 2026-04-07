"""
Compound entity Feature View – demonstrates composite join keys.

Feature Views:
    PRODUCT_SUPPLIER_METRICS – View-based, PRODUCT_SUPPLIER entity
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView

from .config import fq_table
from .entities import product_supplier_entity


def product_supplier_metrics(
    session: Session,
    env: str = "DEV",
) -> FeatureView:
    """Supplier-specific product attributes via compound entity (View-based)."""
    source = fq_table(env, "PRODUCT_SUPPLIER")
    df = session.sql(f"""
        SELECT
            PRODUCT_ID,
            SUPPLIER_ID,
            UNIT_COST                                        AS SUPPLIER_PRICE,
            LEAD_TIME_DAYS,
            CASE WHEN IS_PRIMARY THEN 1 ELSE 0 END          AS IS_PREFERRED,
            CREATED_TS                                       AS UPDATED_TS
        FROM {source}
    """)
    return FeatureView(
        name="PRODUCT_SUPPLIER_METRICS",
        entities=[product_supplier_entity()],
        feature_df=df,
        timestamp_col="UPDATED_TS",
        refresh_freq=None,
        desc="Supplier-level product attributes – compound entity demo (View-based)",
    )

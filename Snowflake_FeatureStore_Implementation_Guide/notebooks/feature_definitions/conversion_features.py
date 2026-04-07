"""
Conversion-model-specific Feature View definitions.

These FVs capture session-level behaviour and fine-grained real-time
engagement signals relevant to *session conversion prediction*.

Feature Views:
    SESSION_BEHAVIOR_FEATURES   – DT (period), SESSION entity, from SESSIONS
    USER_ENGAGEMENT_REALTIME    – Tiled (hourly), USER entity, from EVENTS
    PRODUCT_CATALOG_FEATURES    – View-based, PRODUCT entity, from PRODUCTS+CATEGORIES
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Feature

from .config import fq_table
from .entities import session_entity, user_entity, product_entity


# ---------------------------------------------------------------------------
# SESSION_BEHAVIOR_FEATURES (DT – period refresh)
# ---------------------------------------------------------------------------

def session_behavior_features(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """Per-session behavioural signals (DT-based, PIT-aware)."""
    source = fq_table(env, "SESSIONS")
    df = session.sql(f"""
        SELECT
            SESSION_ID,
            DURATION_SEC,
            EVENT_CNT,
            PAGE_VIEW_CNT,
            PRODUCT_VIEW_DCNT,
            CART_ADD_CNT,
            COALESCE(CART_VALUE_SUM, 0)                     AS CART_VALUE_SUM,
            CASE WHEN IS_CONVERTED THEN 1 ELSE 0 END        AS IS_CONVERTED_SESSION,
            COALESCE(ORDER_VALUE_SUM, 0)                     AS ORDER_VALUE_SUM,
            DEVICE_TYPE,
            SESSION_START_TS
        FROM {source}
        WHERE USER_ID IS NOT NULL
    """)
    return FeatureView(
        name="SESSION_BEHAVIOR_FEATURES",
        entities=[session_entity()],
        feature_df=df,
        timestamp_col="SESSION_START_TS",
        refresh_freq=refresh_freq,
        desc="Session-level behavioural signals – DT (conversion-specific)",
    )


# ---------------------------------------------------------------------------
# USER_ENGAGEMENT_REALTIME (Tiled – hourly granularity)
# ---------------------------------------------------------------------------

def user_engagement_realtime(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """Fine-grained hourly engagement – near-real-time features."""
    source = fq_table(env, "EVENTS")
    features = [
        Feature.count("EVENT_ID", "1h").alias("EVENT_ID_CNT_1H"),
        Feature.count("EVENT_ID", "6h").alias("EVENT_ID_CNT_6H"),
        Feature.count("EVENT_ID", "24h").alias("EVENT_ID_CNT_24H"),
    ]
    return FeatureView(
        name="USER_ENGAGEMENT_REALTIME",
        entities=[user_entity()],
        feature_df=session.table(source),
        timestamp_col="EVENT_TS",
        refresh_freq=refresh_freq,
        feature_granularity="1 hour",
        features=features,
        desc="Hourly engagement counts – tiled, near-real-time (conversion-specific)",
    )


# ---------------------------------------------------------------------------
# PRODUCT_CATALOG_FEATURES (View-based)
# ---------------------------------------------------------------------------

def product_catalog_features(
    session: Session,
    env: str = "DEV",
) -> FeatureView:
    """Product dimension features including semi-structured extraction."""
    products_tbl = fq_table(env, "PRODUCTS")
    categories_tbl = fq_table(env, "CATEGORIES")
    df = session.sql(f"""
        SELECT
            p.PRODUCT_ID,
            c.CATEGORY_NAME,
            p.CURRENT_PRICE,
            COALESCE(p.BASE_PRICE, p.CURRENT_PRICE)            AS BASE_PRICE,
            CASE WHEN p.IS_ACTIVE THEN 1 ELSE 0 END            AS IS_ACTIVE_FLAG,
            p.UPDATED_TS
        FROM {products_tbl} p
        LEFT JOIN {categories_tbl} c ON p.CATEGORY_ID = c.CATEGORY_ID
    """)
    return FeatureView(
        name="PRODUCT_CATALOG_FEATURES",
        entities=[product_entity()],
        feature_df=df,
        timestamp_col="UPDATED_TS",
        refresh_freq=None,
        desc="Product catalog dimensions with category join – View-based (conversion-specific)",
    )

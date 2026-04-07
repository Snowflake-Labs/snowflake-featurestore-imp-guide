"""
Shared Feature View definitions – used by BOTH the conversion and churn models.

Each function returns an *unregistered* FeatureView.  The caller is
responsible for ``fs.register_feature_view(fv, version=...)``.

Feature Views:
    USER_PURCHASE_AGGREGATES  – Tiled (Aggregation API), daily, from ORDERS
    USER_SESSION_ENGAGEMENT   – Tiled (Aggregation API), daily, from EVENTS
    USER_PROFILE_FEATURES     – View-based, from USERS
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Entity, Feature

from .config import get_config, fq_table
from .entities import user_entity


# ---------------------------------------------------------------------------
# USER_PURCHASE_AGGREGATES (Tiled – Aggregation API)
# ---------------------------------------------------------------------------

def _purchase_features_v01() -> list:
    """V01/V02 feature set – core purchase aggregations."""
    return [
        Feature.sum("TOTAL_AMT", "7d").alias("TOTAL_AMT_SUM_7D"),
        Feature.sum("TOTAL_AMT", "30d").alias("TOTAL_AMT_SUM_30D"),
        Feature.count("ORDER_ID", "7d").alias("ORDER_ID_CNT_7D"),
        Feature.count("ORDER_ID", "30d").alias("ORDER_ID_CNT_30D"),
        Feature.avg("TOTAL_AMT", "7d").alias("TOTAL_AMT_AVG_7D"),
        Feature.avg("TOTAL_AMT", "30d").alias("TOTAL_AMT_AVG_30D"),
        Feature.min("TOTAL_AMT", "30d").alias("TOTAL_AMT_MIN_30D"),
        Feature.max("TOTAL_AMT", "30d").alias("TOTAL_AMT_MAX_30D"),
    ]


def _purchase_features_v03() -> list:
    """V03 adds discount rate and item count averages."""
    return _purchase_features_v01() + [
        Feature.avg("DISCOUNT_AMT", "30d").alias("DISCOUNT_AMT_AVG_30D"),
        Feature.avg("ITEM_CNT", "30d").alias("ITEM_CNT_AVG_30D"),
    ]


def user_purchase_aggregates(
    session: Session,
    env: str = "DEV",
    *,
    version: str = "V03",
    refresh_freq: str = "1 minute",
    as_view: bool = False,
) -> FeatureView:
    """User purchase aggregations with multiple time windows.

    Args:
        version: ``"V01"`` returns View-based with core features,
                 ``"V02"`` returns DT-based with core features,
                 ``"V03"`` returns DT-based with extended features.
        as_view: Force View-based (``refresh_freq=None``).
    """
    source = fq_table(env, "ORDERS")
    features = _purchase_features_v01() if version in ("V01", "V02") else _purchase_features_v03()
    freq = None if (version == "V01" or as_view) else refresh_freq

    return FeatureView(
        name="USER_PURCHASE_AGGREGATES",
        entities=[user_entity()],
        feature_df=session.table(source),
        timestamp_col="ORDER_TS",
        refresh_freq=freq,
        feature_granularity="1 day",
        features=features,
        desc="User purchase aggregations – multi-window tiled features (shared)",
    )


# ---------------------------------------------------------------------------
# USER_SESSION_ENGAGEMENT (Tiled – Aggregation API)
# ---------------------------------------------------------------------------

def user_session_engagement(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """User engagement metrics aggregated from EVENTS – daily tiling."""
    source = fq_table(env, "EVENTS")
    features = [
        Feature.count("EVENT_ID", "7d").alias("EVENT_ID_CNT_7D"),
        Feature.count("EVENT_ID", "30d").alias("EVENT_ID_CNT_30D"),
    ]
    return FeatureView(
        name="USER_SESSION_ENGAGEMENT",
        entities=[user_entity()],
        feature_df=session.table(source),
        timestamp_col="EVENT_TS",
        refresh_freq=refresh_freq,
        feature_granularity="1 day",
        features=features,
        desc="User session/event engagement – daily tiled counts (shared)",
    )


# ---------------------------------------------------------------------------
# USER_PROFILE_FEATURES (View-based)
# ---------------------------------------------------------------------------

def user_profile_features(
    session: Session,
    env: str = "DEV",
) -> FeatureView:
    """Static / slow-changing user profile attributes (View-based FV).

    ``ACCOUNT_AGE_DAYS`` uses ``CURRENT_TIMESTAMP()`` — correct for
    real-time queries but **not PIT-correct** for training.  For
    training data, use ``REGISTRATION_TS`` from ``USER_RECENCY_RAW``
    with ``enrichment.derive_temporal_features()`` post-retrieval.
    """
    cfg = get_config(env)
    source = fq_table(env, "USERS")
    df = session.sql(f"""
        SELECT
            USER_ID,
            LOYALTY_TIER,
            CASE WHEN IS_ACTIVE THEN 1 ELSE 0 END                          AS IS_ACTIVE_FLAG,
            CASE WHEN EMAIL_VERIFIED THEN 1 ELSE 0 END                     AS IS_EMAIL_VERIFIED,
            COALESCE(PREFERRED_LANGUAGE, 'en')                              AS PREFERRED_LANGUAGE,
            DATEDIFF('day', REGISTRATION_TS, CURRENT_TIMESTAMP())           AS ACCOUNT_AGE_DAYS,
            COALESCE(LOYALTY_POINTS, 0)                                     AS LOYALTY_POINTS,
            REGISTRATION_TS                                                 AS UPDATED_TS
        FROM {source}
    """)
    return FeatureView(
        name="USER_PROFILE_FEATURES",
        entities=[user_entity()],
        feature_df=df,
        timestamp_col="UPDATED_TS",
        refresh_freq=None,
        desc="User profile attributes – View-based, slow-changing (shared)",
    )

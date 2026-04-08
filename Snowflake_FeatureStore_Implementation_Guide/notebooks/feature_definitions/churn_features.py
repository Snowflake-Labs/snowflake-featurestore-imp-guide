"""
Churn-model-specific Feature View definitions.

Two-tier architecture for PIT-correct recency features (see Ch 06):

  USER_RECENCY_RAW      – DT (INCREMENTAL), raw timestamps only
  USER_RECENCY_FEATURES – View, derives DAYS_SINCE_* via CURRENT_TIMESTAMP()
                          (correct at query time; NOT for training – use
                          ``enrichment.derive_temporal_features`` post-retrieval)
  USER_TREND_FEATURES   – Tiled (Aggregation API), USER entity, long windows

RFM components are served by USER_RECENCY_RAW (recency) and
USER_PURCHASE_AGGREGATES (frequency/monetary) – no separate RFM FV needed.
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView, Feature

from .config import get_config, fq_table
from .entities import user_entity


# ---------------------------------------------------------------------------
# USER_RECENCY_RAW  (DT – INCREMENTAL base, raw timestamps)
# ---------------------------------------------------------------------------

def user_recency_raw(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """Raw last-activity timestamps per user.

    Stores the actual timestamps rather than derived DAYS_SINCE metrics,
    so the values are PIT-correct when retrieved via ASOF.

    Downstream consumers:
      * ``USER_RECENCY_FEATURES`` View FV – real-time DAYS_SINCE derivation
      * ``enrichment.derive_temporal_features()`` – PIT-correct post-retrieval
        derivation for training data using the spine timestamp
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]

    df = session.sql(f"""
        SELECT
            u.USER_ID,
            MAX(o.ORDER_TS)                                     AS LAST_ORDER_TS,
            MAX(s.SESSION_START_TS)                              AS LAST_SESSION_TS,
            u.LAST_LOGIN_TS,
            u.REGISTRATION_TS,
            GREATEST(
                COALESCE(MAX(o.ORDER_TS),        '1970-01-01'::TIMESTAMP_NTZ),
                COALESCE(MAX(s.SESSION_START_TS), '1970-01-01'::TIMESTAMP_NTZ),
                COALESCE(u.LAST_LOGIN_TS,         '1970-01-01'::TIMESTAMP_NTZ)
            )                                                    AS LAST_ACTIVE_TS
        FROM {db}.{src}.USERS u
        LEFT JOIN {db}.{src}.ORDERS o   ON u.USER_ID = o.USER_ID
        LEFT JOIN {db}.{src}.SESSIONS s ON u.USER_ID = s.USER_ID
        WHERE u.IS_ACTIVE = TRUE
        GROUP BY u.USER_ID, u.LAST_LOGIN_TS, u.REGISTRATION_TS
    """)
    return FeatureView(
        name="USER_RECENCY_RAW",
        entities=[user_entity()],
        feature_df=df,
        timestamp_col="LAST_ACTIVE_TS",
        refresh_freq=refresh_freq,
        refresh_mode="INCREMENTAL",
        desc="Raw last-activity timestamps – INCREMENTAL DT base for recency (churn)",
    )


# ---------------------------------------------------------------------------
# USER_RECENCY_FEATURES  (View – derived DAYS_SINCE_* for real-time serving)
# ---------------------------------------------------------------------------

def user_recency_features(
    session: Session,
    env: str = "DEV",
) -> FeatureView:
    """DAYS_SINCE derived features for real-time / online serving.

    View-based FV that reads from the ``USER_RECENCY_RAW`` DT and
    computes ``DATEDIFF(... CURRENT_TIMESTAMP())`` at query time.
    Correct for online/batch scoring where "now" is the reference.

    **Not PIT-correct for training.**  For training data, retrieve from
    ``USER_RECENCY_RAW`` and call ``enrichment.derive_temporal_features()``
    with the spine timestamp column.
    """
    cfg = get_config(env)
    db = cfg["database"]
    fs = cfg["fs_schema"]

    df = session.sql(f"""
        SELECT
            USER_ID,
            COALESCE(DATEDIFF('day', LAST_ORDER_TS,   CURRENT_TIMESTAMP()), 9999) AS DAYS_SINCE_LAST_ORDER,
            COALESCE(DATEDIFF('day', LAST_SESSION_TS,  CURRENT_TIMESTAMP()), 9999) AS DAYS_SINCE_LAST_SESSION,
            COALESCE(DATEDIFF('day', LAST_LOGIN_TS,    CURRENT_TIMESTAMP()), 9999) AS DAYS_SINCE_LAST_LOGIN,
            DATEDIFF('day', REGISTRATION_TS, CURRENT_TIMESTAMP())                  AS ACCOUNT_AGE_DAYS,
            LAST_ACTIVE_TS                                                          AS UPDATED_TS
        FROM {db}.{fs}."USER_RECENCY_RAW$V01"
    """)
    return FeatureView(
        name="USER_RECENCY_FEATURES",
        entities=[user_entity()],
        feature_df=df,
        timestamp_col="UPDATED_TS",
        refresh_freq=None,
        desc="Recency derivations via CURRENT_TIMESTAMP – View, real-time only (churn)",
    )


# ---------------------------------------------------------------------------
# USER_TREND_FEATURES (Tiled – Aggregation API, long windows)
# ---------------------------------------------------------------------------

def user_trend_features(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """Long-window aggregations for trend analysis (compare 90d vs 30d)."""
    source = fq_table(env, "ORDERS")
    features = [
        Feature.count("ORDER_ID", "90d").alias("ORDER_ID_CNT_90D"),
        Feature.sum("TOTAL_AMT", "90d").alias("TOTAL_AMT_SUM_90D"),
    ]
    return FeatureView(
        name="USER_TREND_FEATURES",
        entities=[user_entity()],
        feature_df=session.table(source),
        timestamp_col="ORDER_TS",
        refresh_freq=refresh_freq,
        feature_granularity="1 day",
        features=features,
        desc="Long-window (90d) trend aggregations for churn detection (churn-specific)",
    )

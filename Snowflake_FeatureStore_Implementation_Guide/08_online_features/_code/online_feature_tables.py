"""
Online Feature Table examples (clickstream canonical patterns).

This module demonstrates how to:
- Enable online serving via feature_view.OnlineConfig (target_lag / TARGET_LAG)
- Build a Feature View from CLICKSTREAM_DATA.ORDERS aligned with FEATURE_STORE_DEMO.FEATURE_STORE
- Summarize target_lag recommendations by use case

Tested in: tests/test_chapter_08.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import Entity, FeatureStore, FeatureView
from snowflake.ml.feature_store import feature_view

# Canonical environment (see Chapter 00 / design chapters)
SOURCE_DATABASE = "FEATURE_STORE_DEMO"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
FEATURE_STORE_DATABASE = "FEATURE_STORE_DEMO"
FEATURE_STORE_SCHEMA = "FEATURE_STORE"
WAREHOUSE = "FS_DEV_WH"

CLICKSTREAM_ORDERS = f"{SOURCE_DATABASE}.{SOURCE_SCHEMA}.ORDERS"


def default_user_order_aggregates_sql(orders_table: str = CLICKSTREAM_ORDERS) -> str:
    """SQL for USER-level aggregates from CLICKSTREAM_DATA.ORDERS."""
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


def build_user_order_feature_view_with_online(
    session: Session,
    *,
    user_entity: Entity,
    target_lag: str = "10s",
    refresh_freq: str = "1 hour",
    fv_name: str = "USER_ORDER_ONLINE_FV",
    orders_table: str = CLICKSTREAM_ORDERS,
    timestamp_col: str = "LAST_ORDER_TS",
) -> FeatureView:
    """
    Construct a Feature View (not yet registered) with online_config enabled.

    Uses CLICKSTREAM_DATA.ORDERS and canonical naming. Register with
    fs.register_feature_view(..., version=\"V01\").
    """
    feature_df = session.sql(default_user_order_aggregates_sql(orders_table))
    online_config = feature_view.OnlineConfig(enable=True, target_lag=target_lag)
    return FeatureView(
        name=fv_name,
        entities=[user_entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        refresh_mode="AUTO",
        desc=(
            "USER order aggregates from CLICKSTREAM_DATA.ORDERS; "
            "offline Dynamic Table + online Hybrid Table (OFT)"
        ),
        online_config=online_config,
    )


def get_target_lag_recommendations() -> dict:
    """
    Target lag (OnlineConfig.target_lag) recommendations by use case.

    Values are Snowflake duration strings (see CREATE ONLINE FEATURE TABLE TARGET_LAG).
    """
    return {
        "fraud_detection": {
            "target_lag": "30 seconds",
            "latency": "Very low",
            "cost": "Higher refresh churn",
            "reason": "Fraud scoring needs tight bounds on online staleness",
        },
        "recommendations": {
            "target_lag": "2 minutes",
            "latency": "Low",
            "cost": "Moderate",
            "reason": "Ranking can tolerate short lag if offline FV is fresh",
        },
        "marketing": {
            "target_lag": "15 minutes",
            "latency": "Moderate",
            "cost": "Lower",
            "reason": "Campaign features rarely need sub-minute OFT sync",
        },
        "analytics": {
            "target_lag": "1 hour",
            "latency": "Higher",
            "cost": "Minimal online sync",
            "reason": "Dashboard-style serving aligned to hourly offline refresh",
        },
    }


def create_online_feature_table_config(
    use_case: str,
    warehouse: str = WAREHOUSE,
) -> dict:
    """
    Return planning-oriented OFT settings for a use case.

    ``target_lag`` maps to OnlineConfig.target_lag / SQL TARGET_LAG.
    """
    recs = get_target_lag_recommendations()
    row = recs.get(use_case, recs["recommendations"])
    return {
        "warehouse": warehouse,
        "target_lag": row["target_lag"],
        "expected_latency": row["latency"],
        "estimated_cost": row["cost"],
        "notes": row["reason"],
    }


# Backward-compatible alias for older chapter text / imports
def get_refresh_freq_recommendations() -> dict:
    """Deprecated name; returns the same structure keyed by target_lag."""
    out = {}
    for k, v in get_target_lag_recommendations().items():
        out[k] = {**v, "refresh_freq": v["target_lag"]}
    return out


if __name__ == "__main__":
    recs = get_target_lag_recommendations()
    print("OFT target_lag recommendations (CLICKSTREAM_DATA / FEATURE_STORE):")
    for use_case, cfg in recs.items():
        print(f"\n{use_case}:")
        print(f"  target_lag: {cfg['target_lag']}")
        print(f"  reason: {cfg['reason']}")

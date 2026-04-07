"""
FastAPI sketch for serving features from an Online Feature Table.

Uses read_feature_view with StoreType.ONLINE and USER_ID keys from the
clickstream USER order aggregate Feature View pattern.

Wire `fs` and `user_order_fv` to your registered Feature View (version V01).

Tested in: tests/test_chapter_08.py (import/shape only)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from snowflake.ml.feature_store import StoreType

if TYPE_CHECKING:
    from snowflake.ml.feature_store import FeatureStore, FeatureView

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - optional dependency for doc builds
    FastAPI = Any  # type: ignore[misc,assignment]

# Features from USER_ORDER_ONLINE_FV / CLICKSTREAM_DATA.ORDERS aggregates
USER_ORDER_ONLINE_FEATURE_NAMES: List[str] = [
    "ORDER_TOTAL_AMT_SUM",
    "ORDER_CNT",
    "ORDER_TOTAL_AMT_AVG",
    "LAST_ORDER_TS",
]


def create_features_app(fs: "FeatureStore", user_order_fv: "FeatureView"):
    """Return a FastAPI app that reads online features by USER_ID."""
    app = FastAPI(title="OFT feature lookup")

    @app.post("/features")
    async def get_features(user_id: str) -> dict:
        df = fs.read_feature_view(
            feature_view=user_order_fv,
            keys=[[user_id]],
            feature_names=USER_ORDER_ONLINE_FEATURE_NAMES,
            store_type=StoreType.ONLINE,
        )
        rows = df.to_pandas().to_dict(orient="records")
        return rows[0] if rows else {}

    return app

import os

from fastapi import FastAPI, HTTPException
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore
from snowflake.ml.feature_store.feature_view import StoreType

# DATABASE = "..."
# FS_SCHEMA = "..."
# WAREHOUSE = "..."
# FEATURE_VIEW_NAME = "..."
# FEATURE_VIEW_VERSION = "..."

app = FastAPI()

# conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "...")
# session = Session.builder.config("connection_name", conn_name).create()
# session.sql(f"USE WAREHOUSE {WAREHOUSE}").collect()

# fs = FeatureStore(
#     session=session,
#     database=DATABASE,
#     name=FS_SCHEMA,
#     default_warehouse=WAREHOUSE,
# )

user_fv = fs.get_feature_view(
    name=FEATURE_VIEW_NAME,
    version=FEATURE_VIEW_VERSION,
)


@app.post("/features")
async def get_features(user_id: str):
    """Get online features for a user."""
    try:
        result = fs.read_feature_view(
            feature_view=user_fv,
            keys=[[user_id]],
            store_type=StoreType.ONLINE,
        )
        rows = result.to_pandas().to_dict(orient="records")
        if not rows:
            raise HTTPException(status_code=404, detail=f"No features found for user {user_id}")
        return rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

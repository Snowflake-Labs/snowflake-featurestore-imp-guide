"""
VECTOR embedding Feature View – demonstrates VECTOR data type with Cortex.

Uses Snowflake Cortex EMBED_TEXT_768 to generate embeddings from product
NAME + DESCRIPTION, stored as VECTOR(FLOAT, 768).

Feature Views:
    PRODUCT_EMBEDDINGS – DT, PRODUCT entity, VECTOR column
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView

from .config import fq_table
from .entities import product_entity


def product_embeddings(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
    model: str = "e5-base-v2",
) -> FeatureView:
    """Product text embeddings via Cortex EMBED_TEXT_768.

    Args:
        model: Cortex embedding model name (default ``e5-base-v2``).
    """
    source = fq_table(env, "PRODUCTS")
    df = session.sql(f"""
        SELECT
            PRODUCT_ID,
            SNOWFLAKE.CORTEX.EMBED_TEXT_768(
                '{model}',
                COALESCE(PRODUCT_NAME, '') || ' ' || COALESCE(DESCRIPTION, '')
            )                                                AS EMBEDDING,
            UPDATED_TS
        FROM {source}
        WHERE IS_ACTIVE = TRUE
    """)
    return FeatureView(
        name="PRODUCT_EMBEDDINGS",
        entities=[product_entity()],
        feature_df=df,
        timestamp_col="UPDATED_TS",
        refresh_freq=refresh_freq,
        desc="Product text embeddings via Cortex – VECTOR(FLOAT,768) demo",
    )

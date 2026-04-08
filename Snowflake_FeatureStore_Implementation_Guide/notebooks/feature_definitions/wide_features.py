"""
Wide Feature View with OBJECT encapsulation – Ch 12 pattern.

Generates combinatorial interaction features (category x device,
channel x device) that produce many columns.  All features are packed
into a single OBJECT column using OBJECT_CONSTRUCT, demonstrating the
two-tier bundled-DT + expansion-at-training pattern.

Feature Views:
    USER_PERMUTATION_FEATURES_WIDE – DT, USER entity, OBJECT column
"""

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureView

from .config import get_config, fq_table
from .entities import user_entity


def user_permutation_features_wide(
    session: Session,
    env: str = "DEV",
    *,
    refresh_freq: str = "1 minute",
) -> FeatureView:
    """Interaction-count features packed into an OBJECT column.

    The SQL generates per-user counts of (CATEGORY x DEVICE_TYPE) and
    (UTM_SOURCE x DEVICE_TYPE) combinations from EVENTS + SESSIONS,
    then packs them into ``FEATURES_OBJ`` via ``OBJECT_AGG``.

    Unpack on the client side with ``OBJECT_KEYS`` + pandas
    ``json_normalize`` during preprocessing.
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]

    df = session.sql(f"""
        WITH event_enriched AS (
            SELECT
                e.USER_ID,
                COALESCE(e.CATEGORY_ID, 'UNKNOWN')          AS CATEGORY_ID,
                COALESCE(s.DEVICE_TYPE, 'UNKNOWN')           AS DEVICE_TYPE,
                COALESCE(s.UTM_SOURCE, 'DIRECT')             AS UTM_SOURCE
            FROM {db}.{src}.EVENTS e
            JOIN {db}.{src}.SESSIONS s ON e.SESSION_ID = s.SESSION_ID
            WHERE e.USER_ID IS NOT NULL
        ),
        cat_dev_counts AS (
            SELECT
                USER_ID,
                CATEGORY_ID || '_' || DEVICE_TYPE AS KEY,
                COUNT(*) AS CNT
            FROM event_enriched
            GROUP BY USER_ID, KEY
        ),
        src_dev_counts AS (
            SELECT
                USER_ID,
                UTM_SOURCE || '_' || DEVICE_TYPE AS KEY,
                COUNT(*) AS CNT
            FROM event_enriched
            GROUP BY USER_ID, KEY
        ),
        user_cat_dev AS (
            SELECT USER_ID,
                   OBJECT_AGG(KEY, CNT::VARIANT) AS CAT_DEV_OBJ
            FROM cat_dev_counts
            GROUP BY USER_ID
        ),
        user_src_dev AS (
            SELECT USER_ID,
                   OBJECT_AGG(KEY, CNT::VARIANT) AS SRC_DEV_OBJ
            FROM src_dev_counts
            GROUP BY USER_ID
        )
        SELECT
            cd.USER_ID,
            OBJECT_CONSTRUCT(
                'cat_dev', cd.CAT_DEV_OBJ,
                'src_dev', COALESCE(sd.SRC_DEV_OBJ, OBJECT_CONSTRUCT())
            )                                                AS FEATURES_OBJ
        FROM user_cat_dev cd
        LEFT JOIN user_src_dev sd ON cd.USER_ID = sd.USER_ID
    """)
    return FeatureView(
        name="USER_PERMUTATION_FEATURES_WIDE",
        entities=[user_entity()],
        feature_df=df,
        refresh_freq=refresh_freq,
        refresh_mode="INCREMENTAL",
        desc="Interaction permutation features packed into OBJECT – wide/sparse demo",
    )

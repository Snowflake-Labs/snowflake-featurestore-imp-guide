-- =============================================================================
-- Feature Store Monitoring Queries
-- Canonical context: DATABASE FEATURE_STORE_DEMO, schema FEATURE_STORE,
-- source CLICKSTREAM_DATA, warehouse FS_DEV_WH. FeatureView versions use V01.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Check Dynamic Table Refresh History (table function)
-- https://docs.snowflake.com/en/sql-reference/functions/dynamic_table_refresh_history
-- -----------------------------------------------------------------------------

SELECT
    NAME,
    STATE,
    STATE_MESSAGE,
    REFRESH_START_TIME,
    REFRESH_END_TIME,
    REFRESH_TRIGGER,
    STATISTICS:numInsertedRows::INT AS ROWS_INSERTED,
    STATISTICS:numUpdatedRows::INT AS ROWS_UPDATED
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
    NAME => 'FEATURE_STORE_DEMO.FEATURE_STORE.USER_ORDER_FV$V01'
))
ORDER BY REFRESH_START_TIME DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- Check Current Lag for FeatureViews (Dynamic Tables in FEATURE_STORE)
-- -----------------------------------------------------------------------------

SELECT
    NAME,
    TARGET_LAG,
    SCHEDULING_STATE,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE DATABASE_NAME = 'FEATURE_STORE_DEMO'
  AND SCHEMA_NAME = 'FEATURE_STORE'
ORDER BY LAG_MINUTES DESC;

-- -----------------------------------------------------------------------------
-- Feature Store Health Dashboard
-- -----------------------------------------------------------------------------

WITH fv_health AS (
    SELECT
        NAME,
        SCHEDULING_STATE,
        TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES,
        CASE
            WHEN SCHEDULING_STATE = 'RUNNING'
                 AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) < 60
                THEN 'HEALTHY'
            WHEN TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) >= 60
                THEN 'STALE'
            ELSE 'WARNING'
        END AS STATUS
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
    WHERE DATABASE_NAME = 'FEATURE_STORE_DEMO'
      AND SCHEMA_NAME = 'FEATURE_STORE'
)
SELECT
    STATUS,
    COUNT(*) AS COUNT,
    ARRAY_AGG(NAME) AS FEATURE_VIEWS
FROM fv_health
GROUP BY STATUS;

-- -----------------------------------------------------------------------------
-- Find Stale FeatureViews
-- -----------------------------------------------------------------------------

SELECT
    NAME,
    SCHEDULING_STATE,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE DATABASE_NAME = 'FEATURE_STORE_DEMO'
  AND SCHEMA_NAME = 'FEATURE_STORE'
  AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60;

-- -----------------------------------------------------------------------------
-- Online Feature Table (OFT) refresh monitoring
-- https://docs.snowflake.com/en/sql-reference/functions/online-feature-table-refresh-history
-- -----------------------------------------------------------------------------

SELECT
    QUALIFIED_NAME,
    STATE,
    REFRESH_START_TIME,
    REFRESH_END_TIME,
    REFRESH_TRIGGER,
    REFRESH_ACTION,
    STATE_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.ONLINE_FEATURE_TABLE_REFRESH_HISTORY(
    NAME_PREFIX => 'FEATURE_STORE_DEMO.FEATURE_STORE.',
    RESULT_LIMIT => 100
))
ORDER BY REFRESH_START_TIME DESC;

-- Storage footprint (hybrid / online feature tables) — ACCOUNT_USAGE, ~45m lag
-- https://docs.snowflake.com/en/sql-reference/account-usage/hybrid_tables

-- SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.HYBRID_TABLES
--   WHERE TABLE_SCHEMA = 'FEATURE_STORE';

-- Usage — credits / activity
-- https://docs.snowflake.com/en/sql-reference/account-usage/hybrid_table_usage_history

-- SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.HYBRID_TABLE_USAGE_HISTORY
--   WHERE SCHEMA_NAME = 'FEATURE_STORE'
--   ORDER BY START_TIME DESC LIMIT 100;

-- -----------------------------------------------------------------------------
-- Model Registry metadata (use MODEL_VERSIONS — not MODELS / MODEL_DATASETS)
-- -----------------------------------------------------------------------------

-- SELECT MODEL_NAME, MODEL_VERSION, COMMENT
-- FROM FEATURE_STORE_DEMO.INFORMATION_SCHEMA.MODEL_VERSIONS
-- ORDER BY MODEL_NAME, MODEL_VERSION;

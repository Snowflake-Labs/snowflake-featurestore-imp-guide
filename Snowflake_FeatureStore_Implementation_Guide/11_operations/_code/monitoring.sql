-- =============================================================================
-- Feature Store Monitoring Queries
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Check Dynamic Table Refresh History
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
    NAME => 'ML_FEATURES.FEATURE_STORE.USER_PURCHASE_FV$V1' -- Database.Schema.FeatureView$Version
))
ORDER BY REFRESH_START_TIME DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- Check Current Lag for All FeatureViews
-- NOTE: SCHEDULING_STATE is an OBJECT with fields: STATE, REASON_CODE, REASON_MESSAGE.
--       LATEST_DATA_TIMESTAMP is the data timestamp of the last successful refresh.
-- -----------------------------------------------------------------------------

SELECT 
    NAME,
    TARGET_LAG_SEC,
    SCHEDULING_STATE:STATE::STRING AS SCHEDULING_STATE,
    LATEST_DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
ORDER BY LAG_MINUTES DESC;

-- -----------------------------------------------------------------------------
-- Feature Store Health Dashboard
-- Classifies each offline FeatureView (Dynamic Table) into a health status:
--   HEALTHY  = scheduling is RUNNING, last refresh succeeded, lag < 60 min
--   STALE    = lag >= 60 minutes (data is outdated regardless of state)
--   FAILING  = last completed refresh FAILED or UPSTREAM_FAILED
--   WARNING  = anything else (e.g. SUSPENDED with recent data)
-- Uses SCHEDULING_STATE:STATE (OBJECT field) and LATEST_DATA_TIMESTAMP.
-- -----------------------------------------------------------------------------

WITH fv_health AS (
    SELECT 
        NAME,
        SCHEDULING_STATE:STATE::STRING AS SCHED_STATE,
        LAST_COMPLETED_REFRESH_STATE,
        TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES,
        CASE
            WHEN LAST_COMPLETED_REFRESH_STATE IN ('FAILED', 'UPSTREAM_FAILED')
                THEN 'FAILING'
            WHEN TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) >= 60 
                THEN 'STALE'
            WHEN SCHEDULING_STATE:STATE::STRING = 'RUNNING'
                 AND TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) < 60 
                THEN 'HEALTHY'
            ELSE 'WARNING'
        END AS STATUS
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
    WHERE SCHEMA_NAME = 'FEATURE_STORE'
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
    SCHEDULING_STATE:STATE::STRING AS SCHEDULING_STATE,
    LATEST_DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
  AND TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60;

-- -----------------------------------------------------------------------------
-- Alert: Stale FeatureViews (>60 min lag)
-- Prerequisites:
--   1. Create an email notification integration:
--      CREATE NOTIFICATION INTEGRATION feature_store_email_int
--        TYPE = EMAIL
--        ENABLED = TRUE
--        ALLOWED_RECIPIENTS = ('ml-alerts@company.com');
--   2. After creating the alert, resume it:
--      ALTER ALERT feature_staleness_alert RESUME;
-- -----------------------------------------------------------------------------

CREATE OR REPLACE ALERT feature_staleness_alert
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = 'USING CRON 0 * * * * UTC'
  IF (EXISTS (
    SELECT *
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
    WHERE SCHEMA_NAME = 'FEATURE_STORE'
      AND TIMESTAMPDIFF('minute', LATEST_DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60
  ))
  THEN
    CALL SYSTEM$SEND_EMAIL(
      'feature_store_email_int',
      'ml-alerts@company.com',
      'Feature Store Alert: Stale FeatureViews Detected',
      'One or more FeatureViews in FEATURE_STORE have data older than 60 minutes. Please investigate using the monitoring queries in monitoring.sql.'
    );


-- =============================================================================
-- Online Feature Table Monitoring
-- =============================================================================
-- Online-enabled FeatureViews are backed by Online Feature Tables, a first-class
-- Snowflake object type. The queries above (Dynamic Tables) only cover the
-- OFFLINE layer. The queries below cover the ONLINE layer.

-- -----------------------------------------------------------------------------
-- List All Online Feature Tables (identify which FeatureViews have online serving)
-- -----------------------------------------------------------------------------

SHOW ONLINE FEATURE TABLES IN SCHEMA FEATURE_STORE;

-- -----------------------------------------------------------------------------
-- Online Feature Tables: Status, Lag, and Refresh Mode
-- -----------------------------------------------------------------------------

SELECT
    "name"              AS NAME,
    "source"            AS OFFLINE_SOURCE,
    "target_lag"        AS TARGET_LAG,
    "scheduling_state"  AS SCHEDULING_STATE,
    "refresh_mode"      AS REFRESH_MODE,
    "rows"              AS ROW_COUNT
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- -----------------------------------------------------------------------------
-- Online Feature Table Refresh History
-- -----------------------------------------------------------------------------

SELECT
    NAME,
    STATE,
    STATE_MESSAGE,
    REFRESH_START_TIME,
    REFRESH_END_TIME,
    REFRESH_TRIGGER,
    REFRESH_ACTION
FROM TABLE(INFORMATION_SCHEMA.ONLINE_FEATURE_TABLE_REFRESH_HISTORY(
    RESULT_LIMIT => 20
))
ORDER BY REFRESH_START_TIME DESC;

-- -----------------------------------------------------------------------------
-- Online Feature Table: Failed Refreshes (last 24 hours)
-- -----------------------------------------------------------------------------

SELECT
    NAME,
    STATE,
    STATE_MESSAGE,
    REFRESH_START_TIME,
    REFRESH_TRIGGER,
    REFRESH_ACTION
FROM TABLE(INFORMATION_SCHEMA.ONLINE_FEATURE_TABLE_REFRESH_HISTORY(
    REFRESH_START_TIMESTAMP => CURRENT_TIMESTAMP - INTERVAL '1 DAY',
    ERROR_ONLY => TRUE
))
ORDER BY REFRESH_START_TIME DESC;

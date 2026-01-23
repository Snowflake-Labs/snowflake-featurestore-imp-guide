-- =============================================================================
-- Feature Pipeline Monitoring Queries
-- =============================================================================
-- Use these queries to monitor Dynamic Table-based feature pipelines.
--
-- Tested in: tests/test_chapter_05.py (SQL validation only)
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
    STATISTICS:numUpdatedRows::INT AS ROWS_UPDATED,
    STATISTICS:numDeletedRows::INT AS ROWS_DELETED
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
    NAME => 'ML_FEATURES.FEATURE_STORE.USER_PURCHASE_STATS$V1'
))
ORDER BY REFRESH_START_TIME DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- Check Current Lag for All FeatureViews
-- -----------------------------------------------------------------------------

SELECT 
    NAME,
    TARGET_LAG,
    SCHEDULING_STATE,
    LAST_COMPLETED_REFRESH_TIME,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
ORDER BY LAG_MINUTES DESC;

-- -----------------------------------------------------------------------------
-- Find Stale FeatureViews (Lag > 60 minutes)
-- -----------------------------------------------------------------------------

SELECT 
    NAME,
    SCHEDULING_STATE,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
  AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60;

-- -----------------------------------------------------------------------------
-- Check Failed Refreshes
-- -----------------------------------------------------------------------------

SELECT 
    NAME,
    STATE,
    STATE_MESSAGE,
    REFRESH_START_TIME,
    REFRESH_END_TIME
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE STATE = 'FAILED'
  AND REFRESH_START_TIME > DATEADD('day', -1, CURRENT_TIMESTAMP())
ORDER BY REFRESH_START_TIME DESC;

-- -----------------------------------------------------------------------------
-- Calculate Refresh Costs (Approximate)
-- -----------------------------------------------------------------------------

WITH refresh_stats AS (
    SELECT 
        NAME,
        COUNT(*) AS REFRESH_COUNT,
        AVG(TIMESTAMPDIFF('second', REFRESH_START_TIME, REFRESH_END_TIME)) AS AVG_REFRESH_SECONDS,
        SUM(STATISTICS:numInsertedRows::INT) AS TOTAL_ROWS_PROCESSED
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
    WHERE REFRESH_START_TIME > DATEADD('day', -7, CURRENT_TIMESTAMP())
    GROUP BY NAME
)
SELECT 
    NAME,
    REFRESH_COUNT,
    ROUND(AVG_REFRESH_SECONDS, 2) AS AVG_REFRESH_SEC,
    TOTAL_ROWS_PROCESSED,
    ROUND(REFRESH_COUNT * AVG_REFRESH_SECONDS / 3600, 2) AS APPROX_COMPUTE_HOURS
FROM refresh_stats
ORDER BY APPROX_COMPUTE_HOURS DESC;

-- =============================================================================
-- End of Monitoring Queries
-- =============================================================================

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
    NAME => 'ML_FEATURES.FEATURE_STORE.USER_PURCHASE_FV$V1'
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
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
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
            WHEN SCHEDULING_STATE = 'RUNNING' AND 
                 TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) < 60 
                THEN 'HEALTHY'
            WHEN TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) >= 60 
                THEN 'STALE'
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
    SCHEDULING_STATE,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS LAG_MINUTES
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE SCHEMA_NAME = 'FEATURE_STORE'
  AND TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) > 60;

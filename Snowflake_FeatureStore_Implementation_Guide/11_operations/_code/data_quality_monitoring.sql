-- =============================================================================
-- Feature Store Data Quality Monitoring (Data Metric Functions)
-- =============================================================================
-- DMFs require Enterprise Edition. They run on serverless compute.
-- Supported on Dynamic Tables (FeatureViews). NOT supported on hybrid tables.

-- Step 1: Create a custom DMF for null rate
-- The DMF signature requires a table argument name (e.g., arg_t) and column
-- argument names (e.g., col). The body references these argument names.
-- RETURNS must be NUMBER (not DECIMAL or FLOAT).
CREATE OR REPLACE DATA METRIC FUNCTION null_rate(
    arg_t TABLE(col STRING)
)
RETURNS NUMBER
AS
$$
SELECT COALESCE(
    SUM(CASE WHEN col IS NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
    0
)
FROM arg_t
$$;

-- Step 2: Set the DMF schedule on the FeatureView (Dynamic Table)
-- This controls how often ALL associated DMFs run on this table.
-- Default is 1 hour if not set. Can also use 'TRIGGER_ON_CHANGES' for DML-triggered runs.
ALTER TABLE USER_PURCHASE_FV$V1
    SET DATA_METRIC_SCHEDULE = 'USING CRON 0 * * * * UTC';

-- Step 3: Associate the DMF with specific column(s)
-- This is the REQUIRED step that actually attaches the DMF to the table.
-- Setting the schedule alone does NOT run any DMF — you must ADD the DMF ON (columns).
ALTER TABLE USER_PURCHASE_FV$V1
    ADD DATA METRIC FUNCTION null_rate ON (PURCHASE_AMOUNT);

-- =============================================================================
-- Using System DMFs (no custom creation needed)
-- =============================================================================
-- Snowflake provides built-in DMFs under SNOWFLAKE.CORE:
--   NULL_COUNT, NULL_PERCENT, BLANK_COUNT, BLANK_PERCENT,
--   UNIQUE_COUNT, DUPLICATE_COUNT, FRESHNESS, ROW_COUNT,
--   IQR_OUTLIER_COUNT, ACCEPTED_VALUES
ALTER TABLE USER_PURCHASE_FV$V1
    ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT ON (PURCHASE_AMOUNT);

ALTER TABLE USER_PURCHASE_FV$V1
    ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (USER_ID);

ALTER TABLE USER_PURCHASE_FV$V1
    ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ();

-- =============================================================================
-- Checking DMF Results
-- =============================================================================
-- Results are stored in the event table and queryable via:
SELECT *
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS
WHERE TABLE_NAME = 'USER_PURCHASE_FV$V1'
ORDER BY MEASUREMENT_TIME DESC
LIMIT 50;

-- Track DMF credit consumption
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY
ORDER BY START_TIME DESC
LIMIT 20;

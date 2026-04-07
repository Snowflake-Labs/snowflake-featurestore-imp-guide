-- ============================================================================
-- CONTROL SCRIPTS FOR INCREMENTAL DATA GENERATOR
-- ============================================================================
-- Use these scripts to start, stop, configure, and monitor the generator.
-- ============================================================================

USE SCHEMA FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN;

-- ============================================================================
-- START GENERATION
-- ============================================================================
-- Resume the task to start continuous data generation
ALTER TASK INCREMENTAL_DATA_TASK RESUME;

-- Verify task is running
SHOW TASKS LIKE 'INCREMENTAL_DATA_TASK';

-- ============================================================================
-- STOP GENERATION
-- ============================================================================
-- Suspend the task to stop generation
ALTER TASK INCREMENTAL_DATA_TASK SUSPEND;

-- ============================================================================
-- RUN A SINGLE BATCH MANUALLY
-- ============================================================================
-- Useful for testing or one-off generation
CALL GENERATE_INCREMENTAL_BATCH();

-- ============================================================================
-- CONFIGURATION
-- ============================================================================
-- View current configuration
SELECT * FROM GENERATION_CONFIG;

-- Update batch sizes
UPDATE GENERATION_CONFIG SET 
    SESSIONS_PER_BATCH = 100,      -- More sessions per batch
    EVENTS_PER_SESSION_MIN = 5,    -- More events per session
    EVENTS_PER_SESSION_MAX = 20,
    ORDERS_PER_BATCH = 10,         -- More orders per batch
    ITEMS_PER_ORDER_MIN = 1,
    ITEMS_PER_ORDER_MAX = 5,
    UPDATED_AT = CURRENT_TIMESTAMP()
WHERE ID = 1;

-- Enable/disable generation (task will skip if disabled)
UPDATE GENERATION_CONFIG SET IS_ENABLED = TRUE WHERE ID = 1;
UPDATE GENERATION_CONFIG SET IS_ENABLED = FALSE WHERE ID = 1;

-- ============================================================================
-- CHANGE TASK SCHEDULE
-- ============================================================================
-- First suspend the task
ALTER TASK INCREMENTAL_DATA_TASK SUSPEND;

-- Change to 30-second intervals (for faster demo)
ALTER TASK INCREMENTAL_DATA_TASK SET SCHEDULE = '30 SECOND';

-- Change to 5-minute intervals (for slower demo)
ALTER TASK INCREMENTAL_DATA_TASK SET SCHEDULE = '5 MINUTE';

-- Change to 10-second intervals (minimum)
ALTER TASK INCREMENTAL_DATA_TASK SET SCHEDULE = '10 SECOND';

-- Resume after changing schedule
ALTER TASK INCREMENTAL_DATA_TASK RESUME;

-- ============================================================================
-- MONITORING
-- ============================================================================
-- Current status (quick check)
SELECT * FROM GENERATION_STATUS;

-- Recent batch history
SELECT * FROM RECENT_GENERATION_LOG;

-- Detailed state
SELECT 
    BATCHES_RUN,
    TOTAL_SESSIONS_GENERATED,
    TOTAL_EVENTS_GENERATED,
    TOTAL_ORDERS_GENERATED,
    TOTAL_ORDER_ITEMS_GENERATED,
    LAST_BATCH_TS,
    TIMESTAMPDIFF(SECOND, LAST_BATCH_TS, CURRENT_TIMESTAMP()) AS SECONDS_SINCE_LAST_BATCH
FROM GENERATION_STATE
WHERE ID = 1;

-- Check task execution history
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'INCREMENTAL_DATA_TASK',
    RESULT_LIMIT => 20
))
ORDER BY SCHEDULED_TIME DESC;

-- Check for errors
SELECT *
FROM GENERATION_LOG
WHERE STATUS = 'ERROR'
ORDER BY BATCH_TS DESC
LIMIT 10;

-- Generation rate (events per minute)
SELECT 
    DATE_TRUNC('MINUTE', BATCH_TS) AS MINUTE,
    SUM(SESSIONS_GENERATED) AS SESSIONS,
    SUM(EVENTS_GENERATED) AS EVENTS,
    SUM(ORDERS_GENERATED) AS ORDERS,
    COUNT(*) AS BATCHES
FROM GENERATION_LOG
WHERE STATUS = 'SUCCESS'
AND BATCH_TS > DATEADD(HOUR, -1, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;

-- ============================================================================
-- DATA VERIFICATION
-- ============================================================================
-- Check latest data in each table
SELECT 'SESSIONS' AS TABLE_NAME, COUNT(*) AS ROW_COUNT, MAX(SESSION_START_TS) AS LATEST_TS FROM SESSIONS
UNION ALL
SELECT 'EVENTS', COUNT(*), MAX(EVENT_TS) FROM EVENTS
UNION ALL
SELECT 'ORDERS', COUNT(*), MAX(ORDER_TS) FROM ORDERS
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*), MAX(CREATED_TS) FROM ORDER_ITEMS;

-- Check referential integrity
SELECT 
    'Sessions with invalid visitors' AS CHECK_NAME,
    COUNT(*) AS ISSUES
FROM SESSIONS s
WHERE NOT EXISTS (SELECT 1 FROM VISITORS v WHERE v.VISITOR_ID = s.VISITOR_ID)
UNION ALL
SELECT 
    'Events with invalid sessions',
    COUNT(*)
FROM EVENTS e
WHERE NOT EXISTS (SELECT 1 FROM SESSIONS s WHERE s.SESSION_ID = e.SESSION_ID)
UNION ALL
SELECT 
    'Orders with invalid users',
    COUNT(*)
FROM ORDERS o
WHERE NOT EXISTS (SELECT 1 FROM USERS u WHERE u.USER_ID = o.USER_ID)
UNION ALL
SELECT 
    'Order items with invalid orders',
    COUNT(*)
FROM ORDER_ITEMS oi
WHERE NOT EXISTS (SELECT 1 FROM ORDERS o WHERE o.ORDER_ID = oi.ORDER_ID);

-- ============================================================================
-- RESET (USE WITH CAUTION!)
-- ============================================================================
-- Reset state to start fresh (keeps existing data, resets counters)
/*
UPDATE GENERATION_STATE SET
    LAST_SESSION_ID = (SELECT MAX(CAST(REPLACE(SESSION_ID, 'sess_', '') AS INT)) FROM SESSIONS),
    LAST_EVENT_ID = (SELECT MAX(CAST(REPLACE(EVENT_ID, 'evt_', '') AS INT)) FROM EVENTS),
    LAST_ORDER_ID = (SELECT MAX(CAST(REPLACE(ORDER_ID, 'ord_', '') AS INT)) FROM ORDERS),
    LAST_ORDER_ITEM_ID = (SELECT MAX(CAST(REPLACE(ORDER_ITEM_ID, 'oi_', '') AS INT)) FROM ORDER_ITEMS),
    LAST_BATCH_TS = CURRENT_TIMESTAMP(),
    TOTAL_SESSIONS_GENERATED = 0,
    TOTAL_EVENTS_GENERATED = 0,
    TOTAL_ORDERS_GENERATED = 0,
    TOTAL_ORDER_ITEMS_GENERATED = 0,
    BATCHES_RUN = 0,
    UPDATED_AT = CURRENT_TIMESTAMP()
WHERE ID = 1;

-- Clear generation log
TRUNCATE TABLE GENERATION_LOG;
*/

-- ============================================================================
-- CLEANUP (FULL REMOVAL)
-- ============================================================================
-- Remove all generator objects (run if you want to remove the generator)
/*
ALTER TASK INCREMENTAL_DATA_TASK SUSPEND;
DROP TASK IF EXISTS INCREMENTAL_DATA_TASK;
DROP PROCEDURE IF EXISTS GENERATE_INCREMENTAL_BATCH();
DROP VIEW IF EXISTS GENERATION_STATUS;
DROP VIEW IF EXISTS RECENT_GENERATION_LOG;
DROP TABLE IF EXISTS GENERATION_LOG;
DROP TABLE IF EXISTS GENERATION_STATE;
DROP TABLE IF EXISTS GENERATION_CONFIG;
*/

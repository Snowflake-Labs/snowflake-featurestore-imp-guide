-- =============================================================================
-- Development Database Subset - Basic Usage Examples
-- =============================================================================

-- After running:
--   python deploy.py create --prod-db FEATURE_STORE_GUIDE --dev-db FSG_DEV --sample-pct 10

-- =============================================================================
-- 1. Switch to Development Database
-- =============================================================================

USE DATABASE FSG_DEV;
USE SCHEMA CLICKSTREAM_RAW;

-- =============================================================================
-- 2. Verify Data (same queries work as production)
-- =============================================================================

-- Check row counts
SELECT 'USERS' as table_name, COUNT(*) as row_count FROM USERS
UNION ALL
SELECT 'VISITORS', COUNT(*) FROM VISITORS
UNION ALL
SELECT 'SESSIONS', COUNT(*) FROM SESSIONS
UNION ALL
SELECT 'EVENTS', COUNT(*) FROM EVENTS
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM ORDERS
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM ORDER_ITEMS;

-- Sample data preview
SELECT * FROM USERS LIMIT 5;
SELECT * FROM SESSIONS LIMIT 5;
SELECT * FROM EVENTS LIMIT 5;

-- =============================================================================
-- 3. Verify Referential Integrity
-- =============================================================================

-- All sessions should have valid visitors
SELECT COUNT(*) as orphan_sessions
FROM SESSIONS s
LEFT JOIN VISITORS v ON s.VISITOR_ID = v.VISITOR_ID
WHERE v.VISITOR_ID IS NULL;
-- Expected: 0

-- All events should have valid sessions
SELECT COUNT(*) as orphan_events
FROM EVENTS e
LEFT JOIN SESSIONS s ON e.SESSION_ID = s.SESSION_ID
WHERE s.SESSION_ID IS NULL;
-- Expected: 0

-- All order items should have valid orders
SELECT COUNT(*) as orphan_items
FROM ORDER_ITEMS oi
LEFT JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
WHERE o.ORDER_ID IS NULL;
-- Expected: 0

-- =============================================================================
-- 4. Check Subset Configuration
-- =============================================================================

SELECT * FROM _SUBSET_ADMIN.SUBSET_CONFIG;

-- =============================================================================
-- 5. Check Dynamic Table Status
-- =============================================================================

SELECT 
    table_schema,
    table_name,
    scheduling_state,
    target_lag,
    row_count
FROM INFORMATION_SCHEMA.TABLES
WHERE table_type = 'DYNAMIC TABLE'
ORDER BY table_schema, table_name;

-- =============================================================================
-- 6. Cost Management - Suspend/Resume
-- =============================================================================

-- Suspend all Dynamic Tables (save compute costs)
CALL _SUBSET_ADMIN.SP_MANAGE_ALL_DTS('SUSPEND');

-- Resume all Dynamic Tables
CALL _SUBSET_ADMIN.SP_MANAGE_ALL_DTS('RESUME');

-- Suspend/resume individual table
ALTER DYNAMIC TABLE CLICKSTREAM_RAW.EVENTS SUSPEND;
ALTER DYNAMIC TABLE CLICKSTREAM_RAW.EVENTS RESUME;

-- =============================================================================
-- 7. Manual Refresh
-- =============================================================================

-- Refresh specific table
ALTER DYNAMIC TABLE CLICKSTREAM_RAW.SESSIONS REFRESH;

-- =============================================================================
-- 8. Switch Between DEV and PROD
-- =============================================================================

-- Development
USE DATABASE FSG_DEV;
SELECT COUNT(*) as dev_users FROM CLICKSTREAM_RAW.USERS;

-- Production
USE DATABASE FEATURE_STORE_GUIDE;
SELECT COUNT(*) as prod_users FROM CLICKSTREAM_RAW.USERS;

-- Same feature engineering code works in both!
-- Just change USE DATABASE at the top.

-- =============================================================================
-- 9. Feature Store Example (works identically in DEV/PROD)
-- =============================================================================

USE DATABASE FSG_DEV;  -- or FEATURE_STORE_GUIDE for production

-- Create Feature Store
-- CREATE OR REPLACE DATABASE FEATURE_STORE_DEV;
-- ... same feature definitions work in both environments

-- =============================================================================
-- 10. Teardown (when done with development database)
-- =============================================================================

-- Option 1: Via Python
--   python deploy.py drop --dev-db FSG_DEV --confirm

-- Option 2: Via SQL
-- DROP DATABASE IF EXISTS FSG_DEV;

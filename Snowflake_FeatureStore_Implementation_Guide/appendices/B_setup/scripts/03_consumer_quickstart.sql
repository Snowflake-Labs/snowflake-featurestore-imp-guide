-- =============================================================================
-- FEATURE STORE IMPLEMENTATION GUIDE: CONSUMER QUICKSTART
-- =============================================================================
-- 
-- This script demonstrates what a Consumer role user can do.
-- Run this with FS_CONSUMER_ROLE to test privileges.
--
-- The Consumer role CAN:
--   ✅ Query production and development data
--   ✅ Create View-based Feature Views (no ongoing cost)
--   ✅ Generate training datasets
--   ✅ Create personal schemas in development
--   ✅ Monitor Dynamic Table status
--
-- The Consumer role CANNOT:
--   ❌ Create Dynamic Tables (cost control)
--   ❌ Create Tasks (scheduled compute)
--   ❌ Write to production
--   ❌ Modify shared schemas
--
-- Prerequisites:
--   - 01_dba_setup.sql and 02_dev_setup.sql have been run
--   - Initial data has been loaded
--   - Development branch has been created
--   - User has FS_CONSUMER_ROLE granted
--
-- Usage:
--   snowsql -f 03_consumer_quickstart.sql -r FS_CONSUMER_ROLE
--
-- =============================================================================

-- Use Consumer role
USE ROLE FS_CONSUMER_ROLE;
USE WAREHOUSE FS_DEV_WH;

-- =============================================================================
-- SECTION 1: EXPLORE PRODUCTION DATA
-- =============================================================================

-- List available production schemas
SHOW SCHEMAS IN DATABASE FEATURE_STORE_DEMO;

-- List tables in clickstream schema
SHOW TABLES IN SCHEMA FEATURE_STORE_DEMO.CLICKSTREAM_DATA;

-- Query production data
SELECT 'Production Data Row Counts:' AS INFO;

SELECT 'VISITORS' AS TABLE_NAME, COUNT(*) AS ROW_COUNT 
FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.VISITORS
UNION ALL
SELECT 'USERS', COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS
UNION ALL
SELECT 'SESSIONS', COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.SESSIONS
UNION ALL
SELECT 'EVENTS', COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.EVENTS
UNION ALL
SELECT 'ORDERS', COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDER_ITEMS
ORDER BY TABLE_NAME;

-- Sample query: Recent user activity
SELECT 
    u.USER_ID,
    u.FIRST_NAME,
    u.LAST_NAME,
    u.LOYALTY_TIER,
    COUNT(DISTINCT s.SESSION_ID) AS SESSION_CNT,
    COUNT(DISTINCT o.ORDER_ID) AS ORDER_CNT,
    SUM(o.TOTAL_AMT) AS TOTAL_SPEND
FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS u
LEFT JOIN FEATURE_STORE_DEMO.CLICKSTREAM_DATA.SESSIONS s ON u.USER_ID = s.USER_ID
LEFT JOIN FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS o ON u.USER_ID = o.USER_ID
WHERE u.REGISTRATION_TS >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY u.USER_ID, u.FIRST_NAME, u.LAST_NAME, u.LOYALTY_TIER
ORDER BY TOTAL_SPEND DESC NULLS LAST
LIMIT 10;

-- =============================================================================
-- SECTION 2: EXPLORE DEVELOPMENT DATA
-- =============================================================================

-- List development schemas
SHOW SCHEMAS IN DATABASE FEATURE_STORE_DEMO_DEV;

-- Compare dev to production (if dev branch exists)
SELECT 'Development Data Row Counts (if available):' AS INFO;

SELECT 
    'VISITORS' AS TABLE_NAME, 
    (SELECT COUNT(*) FROM FEATURE_STORE_DEMO_DEV.CLICKSTREAM_DATA.VISITORS) AS DEV_COUNT,
    (SELECT COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.VISITORS) AS PROD_COUNT,
    ROUND((SELECT COUNT(*) FROM FEATURE_STORE_DEMO_DEV.CLICKSTREAM_DATA.VISITORS) * 100.0 / 
          NULLIF((SELECT COUNT(*) FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.VISITORS), 0), 1) AS PCT_OF_PROD;

-- =============================================================================
-- SECTION 3: CREATE PERSONAL DEVELOPMENT SCHEMA
-- =============================================================================
-- Consumers can create their own schemas in the development database

USE DATABASE FEATURE_STORE_DEMO_DEV;

-- Create a personal schema (replace YOUR_NAME with your identifier)
CREATE SCHEMA IF NOT EXISTS MY_WORKSPACE
    COMMENT = 'Personal development workspace';

USE SCHEMA MY_WORKSPACE;

-- =============================================================================
-- SECTION 4: CREATE VIEW-BASED FEATURE VIEW
-- =============================================================================
-- Consumers CAN create View-based Feature Views (no Dynamic Tables)

-- Example: User engagement features (View-based)
CREATE OR REPLACE VIEW USER_ENGAGEMENT_FEATURES AS
SELECT
    u.USER_ID,
    -- Registration features
    DATEDIFF(DAY, u.REGISTRATION_TS, CURRENT_TIMESTAMP()) AS DAYS_SINCE_REGISTRATION,
    DATEDIFF(DAY, u.LAST_LOGIN_TS, CURRENT_TIMESTAMP()) AS DAYS_SINCE_LAST_LOGIN,
    
    -- Aggregated session features
    COUNT(DISTINCT s.SESSION_ID) AS TOTAL_SESSION_CNT,
    AVG(s.DURATION_SEC) AS AVG_SESSION_DURATION_SEC,
    SUM(s.PAGE_VIEW_CNT) AS TOTAL_PAGE_VIEWS,
    AVG(s.PAGE_VIEW_CNT) AS AVG_PAGES_PER_SESSION,
    
    -- Aggregated order features
    COUNT(DISTINCT o.ORDER_ID) AS TOTAL_ORDER_CNT,
    SUM(o.TOTAL_AMT) AS LIFETIME_VALUE,
    AVG(o.TOTAL_AMT) AS AVG_ORDER_VALUE,
    MIN(o.ORDER_TS) AS FIRST_ORDER_TS,
    MAX(o.ORDER_TS) AS LAST_ORDER_TS,
    DATEDIFF(DAY, MAX(o.ORDER_TS), CURRENT_TIMESTAMP()) AS DAYS_SINCE_LAST_ORDER,
    
    -- Derived features
    CASE 
        WHEN COUNT(DISTINCT o.ORDER_ID) = 0 THEN 'Never Purchased'
        WHEN DATEDIFF(DAY, MAX(o.ORDER_TS), CURRENT_TIMESTAMP()) <= 30 THEN 'Active'
        WHEN DATEDIFF(DAY, MAX(o.ORDER_TS), CURRENT_TIMESTAMP()) <= 90 THEN 'At Risk'
        ELSE 'Churned'
    END AS CUSTOMER_STATUS,
    
    u.LOYALTY_TIER,
    u.LOYALTY_POINTS
    
FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS u
LEFT JOIN FEATURE_STORE_DEMO.CLICKSTREAM_DATA.SESSIONS s ON u.USER_ID = s.USER_ID
LEFT JOIN FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS o ON u.USER_ID = o.USER_ID
GROUP BY 
    u.USER_ID, 
    u.REGISTRATION_TS, 
    u.LAST_LOGIN_TS, 
    u.LOYALTY_TIER, 
    u.LOYALTY_POINTS;

-- Test the feature view
SELECT * FROM USER_ENGAGEMENT_FEATURES LIMIT 10;

-- =============================================================================
-- SECTION 5: CREATE TRAINING DATA TABLE
-- =============================================================================
-- Consumers can create tables in their personal schema to store training data

-- Create spine table for churn prediction
CREATE OR REPLACE TABLE CHURN_PREDICTION_SPINE AS
SELECT 
    USER_ID,
    DATEADD(DAY, -7, CURRENT_TIMESTAMP()) AS AS_OF_DATE
FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS
WHERE REGISTRATION_TS <= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
SAMPLE (1000 ROWS);

-- Join features to spine
CREATE OR REPLACE TABLE CHURN_TRAINING_DATA AS
SELECT
    s.USER_ID,
    s.AS_OF_DATE,
    f.DAYS_SINCE_REGISTRATION,
    f.DAYS_SINCE_LAST_LOGIN,
    f.TOTAL_SESSION_CNT,
    f.AVG_SESSION_DURATION_SEC,
    f.TOTAL_ORDER_CNT,
    f.LIFETIME_VALUE,
    f.AVG_ORDER_VALUE,
    f.DAYS_SINCE_LAST_ORDER,
    f.CUSTOMER_STATUS,
    -- Label: Did customer churn in the next 30 days?
    CASE WHEN f.DAYS_SINCE_LAST_ORDER > 30 THEN 1 ELSE 0 END AS CHURNED
FROM CHURN_PREDICTION_SPINE s
LEFT JOIN USER_ENGAGEMENT_FEATURES f ON s.USER_ID = f.USER_ID;

-- View training data
SELECT * FROM CHURN_TRAINING_DATA LIMIT 10;

-- =============================================================================
-- SECTION 6: DEMONSTRATE PRIVILEGE BOUNDARIES
-- =============================================================================
-- These statements will FAIL for Consumer role (which is expected!)

SELECT '⚠️ The following statements demonstrate what Consumer CANNOT do:' AS WARNING;

-- This SHOULD FAIL: Create Dynamic Table
-- CREATE DYNAMIC TABLE TEST_DT
--     TARGET_LAG = '1 HOUR'
--     WAREHOUSE = FS_DEV_WH
-- AS SELECT * FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS LIMIT 10;

-- This SHOULD FAIL: Create Task
-- CREATE TASK TEST_TASK
--     WAREHOUSE = FS_DEV_WH
--     SCHEDULE = '1 HOUR'
-- AS SELECT 1;

-- This SHOULD FAIL: Write to production
-- INSERT INTO FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS (USER_ID) VALUES ('test');

-- This SHOULD FAIL: Create schema in production
-- CREATE SCHEMA FEATURE_STORE_DEMO.MY_SCHEMA;

-- =============================================================================
-- SECTION 7: CLEANUP (Optional)
-- =============================================================================
-- Uncomment to clean up test objects

-- DROP TABLE IF EXISTS CHURN_TRAINING_DATA;
-- DROP TABLE IF EXISTS CHURN_PREDICTION_SPINE;
-- DROP VIEW IF EXISTS USER_ENGAGEMENT_FEATURES;
-- DROP SCHEMA IF EXISTS MY_WORKSPACE;

-- =============================================================================
-- SUMMARY
-- =============================================================================
SELECT '
✅ CONSUMER QUICKSTART COMPLETE!

What you can do as a Consumer:
  • Query FEATURE_STORE_DEMO and FEATURE_STORE_DEMO_DEV data
  • Create View-based Feature Views
  • Generate training datasets
  • Create personal schemas in FEATURE_STORE_DEMO_DEV

What requires DEV or DBA role:
  • Create Dynamic Tables (use DEV role)
  • Create Tasks (use DEV or DBA role)
  • Write to production (use DBA role)
  • Deploy incremental generator (use DBA role)

To switch roles:
  USE ROLE FS_DEV_ROLE;
  USE ROLE FS_ADMIN_ROLE;
' AS SUMMARY;

-- =============================================================================
-- END OF CONSUMER QUICKSTART
-- =============================================================================

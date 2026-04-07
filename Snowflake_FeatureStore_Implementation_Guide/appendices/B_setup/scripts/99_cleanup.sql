-- =============================================================================
-- FEATURE STORE IMPLEMENTATION GUIDE: CLEANUP SCRIPT
-- =============================================================================
-- 
-- This script removes ALL objects created by the setup scripts.
-- Use this to start fresh or clean up after testing.
--
-- ⚠️  WARNING: This will permanently delete all data and objects!
--
-- Prerequisites:
--   - Run as ACCOUNTADMIN (or user with ACCOUNTADMIN role)
--
-- Usage:
--   snowsql -a <account> -u <admin_user> -r ACCOUNTADMIN -f 99_cleanup.sql
--
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- SECTION 1: SUSPEND TASKS (must be done before dropping)
-- =============================================================================

-- Suspend any running tasks to avoid errors during drop
ALTER TASK IF EXISTS FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK SUSPEND;

-- =============================================================================
-- SECTION 2: DROP DATABASES
-- =============================================================================
-- Dropping databases removes all schemas, tables, views, procedures, etc.

DROP DATABASE IF EXISTS FEATURE_STORE_DEMO;
DROP DATABASE IF EXISTS FEATURE_STORE_DEMO_DEV;
DROP DATABASE IF EXISTS SECRETS;

-- =============================================================================
-- SECTION 3: DROP WAREHOUSES
-- =============================================================================

DROP WAREHOUSE IF EXISTS FS_DEV_WH;

-- =============================================================================
-- SECTION 4: DROP API INTEGRATION
-- =============================================================================

DROP INTEGRATION IF EXISTS FS_GIT_API_INTEGRATION;

-- =============================================================================
-- SECTION 5: DROP ROLES
-- =============================================================================
-- Drop in reverse hierarchy order (children first, then parents)

DROP ROLE IF EXISTS FS_CONSUMER_ROLE;
DROP ROLE IF EXISTS FS_DEV_ROLE;
DROP ROLE IF EXISTS FS_ADMIN_ROLE;

-- =============================================================================
-- SECTION 6: DROP USER
-- =============================================================================

DROP USER IF EXISTS FS_DEMO_USER;

-- =============================================================================
-- SECTION 7: VERIFY CLEANUP
-- =============================================================================

SELECT '✅ Cleanup Complete!' AS STATUS;

-- Verify nothing remains
SHOW USERS LIKE 'FS_DEMO%'
  ->> SELECT 'Users remaining:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW ROLES LIKE 'FS_%'
  ->> SELECT 'Roles remaining:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW WAREHOUSES LIKE 'FS_%'
  ->> SELECT 'Warehouses remaining:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW DATABASES LIKE 'FEATURE_STORE%'
  ->> SELECT 'Databases remaining:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW INTEGRATIONS LIKE 'FS_%'
  ->> SELECT 'Integrations remaining:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SELECT '
🧹 Environment cleaned. Ready to run:
   1. 00_bootstrap.sql (as ACCOUNTADMIN)
   2. 01_dba_setup.sql (as FS_DEMO_USER with ACCOUNTADMIN)
   3. 02_dev_setup.sql (as FS_DEMO_USER)
   4. 03_consumer_quickstart.sql (as FS_DEMO_USER with CONSUMER role)
' AS NEXT_STEPS;

-- =============================================================================
-- END OF CLEANUP
-- =============================================================================

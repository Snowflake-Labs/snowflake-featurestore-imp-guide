-- =============================================================================
-- FEATURE STORE IMPLEMENTATION GUIDE: BOOTSTRAP
-- =============================================================================
-- 
-- MINIMAL SETUP - Run this with your existing ACCOUNTADMIN user.
-- This creates the FS_DEMO_USER and grants them the system roles needed
-- to complete the rest of the setup independently.
--
-- After running this script:
--   1. Log in as FS_DEMO_USER
--   2. Run 01_dba_setup.sql to create everything else
--
-- Prerequisites:
--   - ACCOUNTADMIN role
--
-- Usage:
--   snowsql -f 00_bootstrap.sql
--
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- STEP 1: CREATE SERVICE USER
-- =============================================================================

CREATE USER IF NOT EXISTS FS_DEMO_USER
    PASSWORD = 'ChangeMe123!'  -- CHANGE THIS IMMEDIATELY!
    DEFAULT_ROLE = SYSADMIN
    DEFAULT_WAREHOUSE = COMPUTE_WH
    MUST_CHANGE_PASSWORD = FALSE  -- Set TRUE for production
    COMMENT = 'Service user for Feature Store Implementation Guide';

-- =============================================================================
-- STEP 2: GRANT SYSTEM ROLES
-- =============================================================================
-- FS_DEMO_USER needs these system roles to create the guide environment:
--   - SYSADMIN: Create warehouses, databases, schemas, objects
--   - SECURITYADMIN: Create roles, manage grants
--   - ACCOUNTADMIN: Required for API Integration (Git) creation

-- Grant system roles
GRANT ROLE SYSADMIN TO USER FS_DEMO_USER;
GRANT ROLE SECURITYADMIN TO USER FS_DEMO_USER;

-- API Integration requires ACCOUNTADMIN - grant temporarily for setup
-- You can revoke this after running 01_dba_setup.sql if desired
GRANT ROLE ACCOUNTADMIN TO USER FS_DEMO_USER;

-- =============================================================================
-- STEP 3: VERIFY
-- =============================================================================

SELECT '✅ Bootstrap Complete!' AS STATUS;
SELECT 'User FS_DEMO_USER created with SYSADMIN, SECURITYADMIN, and ACCOUNTADMIN roles.' AS INFO;

SELECT '
📋 NEXT STEPS:
1. Change the password for FS_DEMO_USER (if not done above)
2. Log in as FS_DEMO_USER:
   snowsql -a <account> -u FS_DEMO_USER
3. Run the main setup:
   USE ROLE ACCOUNTADMIN;  -- For API Integration
   !source 01_dba_setup.sql
   -- OR --
   snowsql -a <account> -u FS_DEMO_USER -r ACCOUNTADMIN -f 01_dba_setup.sql

4. (Optional) After setup, revoke ACCOUNTADMIN if desired:
   USE ROLE ACCOUNTADMIN;
   REVOKE ROLE ACCOUNTADMIN FROM USER FS_DEMO_USER;
' AS NEXT_STEPS;

-- =============================================================================
-- END OF BOOTSTRAP
-- =============================================================================

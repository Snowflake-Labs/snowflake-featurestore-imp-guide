-- =============================================================================
-- GUIDE DEVELOPMENT: TEST ENVIRONMENT SETUP (BYOD)
-- =============================================================================
--
-- Creates a self-contained Snowflake environment for developing and testing
-- the Feature Store Implementation Guide. Each contributor runs this in their
-- own account so artifacts don't interfere with other users.
--
-- What this creates:
--   - FS_GUIDE_ROLE        : Dedicated role (owns all guide objects)
--   - FS_GUIDE_WH          : X-Small warehouse (minimal cost)
--   - FS_GUIDE_DB           : Database for source data + Feature Store schemas
--
-- After running this script:
--   1. Use FS_GUIDE_ROLE for all guide development
--   2. All Feature Store artifacts will be visible in Snowsight under this role
--   3. Run guide_test_env_cleanup.sql to tear everything down
--
-- Prerequisites:
--   - ACCOUNTADMIN or SYSADMIN + SECURITYADMIN roles
--
-- Usage:
--   snowsql -f guide_test_env.sql
--   -- OR --
--   Paste into a Snowflake worksheet and run
--
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- STEP 1: CREATE ROLE
-- =============================================================================

CREATE ROLE IF NOT EXISTS FS_GUIDE_ROLE
    COMMENT = 'Feature Store Implementation Guide - development and testing';

GRANT ROLE FS_GUIDE_ROLE TO ROLE SYSADMIN;
GRANT ROLE FS_GUIDE_ROLE TO USER CURRENT_USER();

-- Task execution (required for Online Feature Table refresh tasks)
GRANT EXECUTE TASK ON ACCOUNT TO ROLE FS_GUIDE_ROLE;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE FS_GUIDE_ROLE;

-- =============================================================================
-- STEP 2: CREATE WAREHOUSE
-- =============================================================================

CREATE WAREHOUSE IF NOT EXISTS FS_GUIDE_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Feature Store Implementation Guide - development warehouse';

GRANT USAGE ON WAREHOUSE FS_GUIDE_WH TO ROLE FS_GUIDE_ROLE;
GRANT OPERATE ON WAREHOUSE FS_GUIDE_WH TO ROLE FS_GUIDE_ROLE;

-- =============================================================================
-- STEP 3: CREATE DATABASE
-- =============================================================================

CREATE DATABASE IF NOT EXISTS FS_GUIDE_DB
    COMMENT = 'Feature Store Implementation Guide - source data, features, and ML artifacts';

GRANT OWNERSHIP ON DATABASE FS_GUIDE_DB TO ROLE FS_GUIDE_ROLE COPY CURRENT GRANTS;

-- =============================================================================
-- STEP 4: CREATE SCHEMAS
-- =============================================================================

USE ROLE FS_GUIDE_ROLE;
USE DATABASE FS_GUIDE_DB;
USE WAREHOUSE FS_GUIDE_WH;

-- Source data (clickstream tables)
CREATE SCHEMA IF NOT EXISTS CLICKSTREAM_DATA
    COMMENT = 'Clickstream source data tables';

-- Feature Store (entities, feature views, metadata)
CREATE SCHEMA IF NOT EXISTS FEATURE_STORE
    COMMENT = 'Feature Store entities and feature views';

-- Public ML datasets (Iris, Titanic, etc.)
CREATE SCHEMA IF NOT EXISTS ML_DATASETS
    COMMENT = 'Public ML datasets for examples';

-- Training data outputs
CREATE SCHEMA IF NOT EXISTS TRAINING_DATA
    COMMENT = 'Generated training datasets';

-- Inference outputs
CREATE SCHEMA IF NOT EXISTS INFERENCE_DATA
    COMMENT = 'Batch inference inputs and outputs';

-- Spine tables
CREATE SCHEMA IF NOT EXISTS SPINES
    COMMENT = 'Entity-timestamp spine tables';

-- =============================================================================
-- STEP 5: VERIFY
-- =============================================================================

SELECT '✅ Guide test environment created!' AS STATUS;
SELECT CURRENT_ROLE() AS ROLE, CURRENT_DATABASE() AS DATABASE, CURRENT_WAREHOUSE() AS WAREHOUSE;

SHOW SCHEMAS IN DATABASE FS_GUIDE_DB;

SELECT '
NEXT STEPS:
1. Use FS_GUIDE_ROLE for all guide development
2. Load sample data (see Appendix A)
3. All Feature Store artifacts are visible in Snowsight under FS_GUIDE_ROLE
4. Run guide_test_env_cleanup.sql when done
' AS NEXT_STEPS;

-- =============================================================================
-- END OF SETUP
-- =============================================================================

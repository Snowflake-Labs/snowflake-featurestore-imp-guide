-- =============================================================================
-- FEATURE STORE IMPLEMENTATION GUIDE: DBA SETUP
-- =============================================================================
-- 
-- Run this script as FS_DEMO_USER after running 00_bootstrap.sql.
-- This creates the foundational infrastructure:
--   - Role hierarchy (ADMIN, DEV, CONSUMER)
--   - Warehouse FS_DEV_WH
--   - API Integration (Git)
--   - Databases (FEATURE_STORE_DEMO, FEATURE_STORE_DEMO_DEV)
--   - Production schemas (admin controls production)
--
-- Key principle: DBA grants DEV ownership of DEV database, so DEV is 
-- self-sufficient to create their own schemas and grant access to Consumer.
-- DEV schemas are created in 02_dev_setup.sql, NOT here.
--
-- After running this script, run 02_dev_setup.sql to create tables and 
-- deploy the data generator.
--
-- Prerequisites:
--   - 00_bootstrap.sql has been run by an ACCOUNTADMIN
--   - You are logged in as FS_DEMO_USER
--   - FS_DEMO_USER has ACCOUNTADMIN role (for API Integration)
--
-- Usage:
--   snowsql -a <account> -u FS_DEMO_USER -r ACCOUNTADMIN -f 01_dba_setup.sql
--
-- =============================================================================

-- Use ACCOUNTADMIN for API Integration creation, then switch to SYSADMIN
USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- SECTION 1: CREATE ROLES
-- =============================================================================
-- Role hierarchy:
--   FS_ADMIN_ROLE
--       └── FS_DEV_ROLE  
--               └── FS_CONSUMER_ROLE
--
-- Each higher role inherits all privileges from roles below it.

-- Consumer Role: Query data, create view-based features, generate training data
CREATE ROLE IF NOT EXISTS FS_CONSUMER_ROLE
    COMMENT = 'Read-only access to feature store, can create view-based features';

-- Developer Role: Full development capabilities, create Dynamic Tables
CREATE ROLE IF NOT EXISTS FS_DEV_ROLE
    COMMENT = 'Feature store development - can create DT-based features';

-- Admin Role: Administrative access, production deployment, promotion
CREATE ROLE IF NOT EXISTS FS_ADMIN_ROLE
    COMMENT = 'Feature store administration - production deployment and promotion';

-- Establish role hierarchy
GRANT ROLE FS_CONSUMER_ROLE TO ROLE FS_DEV_ROLE;
GRANT ROLE FS_DEV_ROLE TO ROLE FS_ADMIN_ROLE;
GRANT ROLE FS_ADMIN_ROLE TO ROLE SYSADMIN;

-- Grant all roles to the service user
GRANT ROLE FS_CONSUMER_ROLE TO USER FS_DEMO_USER;
GRANT ROLE FS_DEV_ROLE TO USER FS_DEMO_USER;
GRANT ROLE FS_ADMIN_ROLE TO USER FS_DEMO_USER;

-- =============================================================================
-- SECTION 2: CREATE WAREHOUSES
-- =============================================================================
-- Canonical guide warehouse (general workloads, DT refresh, training-sized jobs).
-- Larger deployments often split warehouses by workload; this guide uses one name
-- aligned with the main chapters: FS_DEV_WH.

CREATE WAREHOUSE IF NOT EXISTS FS_DEV_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Feature Store Implementation Guide - default warehouse';

GRANT USAGE ON WAREHOUSE FS_DEV_WH TO ROLE FS_CONSUMER_ROLE;
GRANT OPERATE ON WAREHOUSE FS_DEV_WH TO ROLE FS_ADMIN_ROLE;
GRANT USAGE ON WAREHOUSE FS_DEV_WH TO ROLE FS_DEV_ROLE;

-- =============================================================================
-- SECTION 3: CREATE GIT API INTEGRATION
-- =============================================================================
-- This integration enables Git repositories as sources for Snowflake objects.
-- Used for CI/CD workflows and version-controlled development.

CREATE OR REPLACE API INTEGRATION FS_GIT_API_INTEGRATION
    API_PROVIDER = git_https_api
    API_ALLOWED_PREFIXES = ('https://github.com')
    API_USER_AUTHENTICATION = (TYPE = SNOWFLAKE_GITHUB_APP)
    ENABLED = TRUE
    COMMENT = 'GitHub API integration for Feature Store development workflows';

-- Grant usage to roles that need to create Git repositories
-- DEV role can create Git-backed workspaces for development
GRANT USAGE ON INTEGRATION FS_GIT_API_INTEGRATION TO ROLE FS_DEV_ROLE;

-- Admin also gets access (inherited, but explicit for clarity)
GRANT USAGE ON INTEGRATION FS_GIT_API_INTEGRATION TO ROLE FS_ADMIN_ROLE;

CREATE DATABASE IF NOT EXISTS SECRETS;

GRANT OWNERSHIP ON DATABASE SECRETS TO ROLE FS_ADMIN_ROLE COPY CURRENT GRANTS;
GRANT CREATE SCHEMA ON DATABASE SECRETS TO ROLE FS_ADMIN_ROLE;

GRANT USAGE ON DATABASE SECRETS TO ROLE FS_DEV_ROLE;

-- =============================================================================
-- SECTION 4: CREATE DATABASES
-- =============================================================================

-- Production Database: Source of truth for production data
CREATE DATABASE IF NOT EXISTS FEATURE_STORE_DEMO
    COMMENT = 'Feature Store Implementation Guide - source data and production features';

-- Development Database: Development and testing environment
CREATE DATABASE IF NOT EXISTS FEATURE_STORE_DEMO_DEV
    COMMENT = 'Feature Store Implementation Guide - development and testing';

-- =============================================================================
-- SECTION 5: GRANT DATABASE PRIVILEGES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- DBA Role: Full ownership of production
-- -----------------------------------------------------------------------------
GRANT OWNERSHIP ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_ADMIN_ROLE COPY CURRENT GRANTS;
GRANT CREATE SCHEMA ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_ADMIN_ROLE;

-- Production execution privileges (for incremental generator)
GRANT EXECUTE TASK ON ACCOUNT TO ROLE FS_ADMIN_ROLE;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE FS_ADMIN_ROLE;

-- -----------------------------------------------------------------------------
-- DEV Role: Full access to development, read access to production
-- -----------------------------------------------------------------------------
GRANT OWNERSHIP ON DATABASE FEATURE_STORE_DEMO_DEV TO ROLE FS_DEV_ROLE COPY CURRENT GRANTS;
GRANT CREATE SCHEMA ON DATABASE FEATURE_STORE_DEMO_DEV TO ROLE FS_DEV_ROLE;
-- Note: CREATE DYNAMIC TABLE is granted at schema level in Section 10

-- Read access to production
GRANT USAGE ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;

-- Development execution privileges
GRANT EXECUTE TASK ON ACCOUNT TO ROLE FS_DEV_ROLE;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE FS_DEV_ROLE;

-- -----------------------------------------------------------------------------
-- Consumer Role: Read access to both environments
-- -----------------------------------------------------------------------------
GRANT USAGE ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON DATABASE FEATURE_STORE_DEMO_DEV TO ROLE FS_CONSUMER_ROLE;

-- =============================================================================
-- SECTION 6: CREATE PRODUCTION SCHEMAS (Empty)
-- =============================================================================
-- DBA creates the schema structure; DEV setup will populate tables.

USE ROLE FS_ADMIN_ROLE;
USE DATABASE FEATURE_STORE_DEMO;
USE WAREHOUSE FS_DEV_WH;

-- Source data schema (canonical name used in main guide chapters)
CREATE SCHEMA IF NOT EXISTS CLICKSTREAM_DATA
    COMMENT = 'Clickstream source data tables';

-- Admin schema for generator
CREATE SCHEMA IF NOT EXISTS CLICKSTREAM_ADMIN
    COMMENT = 'Incremental generator configuration and state';

-- Feature Store schema
CREATE SCHEMA IF NOT EXISTS FEATURE_STORE
    COMMENT = 'Production feature store entities and feature views';

-- ML Datasets schema (public datasets)
CREATE SCHEMA IF NOT EXISTS ML_DATASETS
    COMMENT = 'Public ML datasets (Iris, Titanic, etc.)';

-- Training data outputs
CREATE SCHEMA IF NOT EXISTS TRAINING_DATA
    COMMENT = 'Generated training datasets';

-- Inference data
CREATE SCHEMA IF NOT EXISTS INFERENCE_DATA
    COMMENT = 'Batch inference inputs and outputs';

-- Spine tables
CREATE SCHEMA IF NOT EXISTS SPINES
    COMMENT = 'Entity-timestamp spine tables for training data generation';

-- =============================================================================
-- SECTION 7: GRANT SCHEMA PRIVILEGES - PRODUCTION
-- =============================================================================

-- DBA: Full control of production schemas
GRANT ALL ON ALL SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_ADMIN_ROLE;
GRANT ALL ON FUTURE SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_ADMIN_ROLE;

-- DEV: Read access to production, can create objects in select schemas
GRANT USAGE ON ALL SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;
GRANT SELECT ON FUTURE TABLES IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;
GRANT SELECT ON FUTURE VIEWS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;

-- Consumer: Read-only on production
GRANT USAGE ON ALL SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;

-- =============================================================================
-- SECTION 8: DEVELOPMENT DATABASE PRIVILEGES
-- =============================================================================
-- DEV owns their database and is self-sufficient to create schemas and objects.
-- DEV is responsible for granting Consumer access to their objects.
-- No schemas are created here - DEV creates their own in 02_dev_setup.sql.

-- DEV has full control: can create schemas, grant to others
-- (OWNERSHIP already granted in Section 5, CREATE SCHEMA already granted)

-- Future grants ensure DEV can manage any schemas they create
GRANT ALL ON FUTURE SCHEMAS IN DATABASE FEATURE_STORE_DEMO_DEV TO ROLE FS_DEV_ROLE;

-- DEV can execute tasks for automation
-- (Already granted at account level in Section 5)

-- Consumer: Can use DEV database, will get schema access from DEV
-- (USAGE on database already granted in Section 5)

-- =============================================================================
-- SECTION 9: VERIFY SETUP
-- =============================================================================

-- Show created objects
SELECT '✅ DBA Setup Complete!' AS STATUS;

-- Use flow operator (->>)  to chain SHOW results into SELECT
-- See: https://docs.snowflake.com/en/sql-reference/operators-flow

SHOW USERS LIKE 'FS_DEMO%'
  ->> SELECT 'Users created:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW ROLES LIKE 'FS_%'
  ->> SELECT 'Roles created:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW WAREHOUSES LIKE 'FS_%'
  ->> SELECT 'Warehouses created:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

SHOW DATABASES LIKE 'FEATURE_STORE%'
  ->> SELECT 'Databases created:' AS CATEGORY, COUNT(*) AS COUNT FROM $1;

-- List production schemas (DBA created these)
SELECT 'Production schemas:' AS INFO;
SHOW SCHEMAS IN DATABASE FEATURE_STORE_DEMO;

-- DEV database has no schemas yet - DEV will create them in 02_dev_setup.sql
SELECT 'Development database ready for DEV to create schemas' AS INFO;

-- =============================================================================
-- NEXT STEPS
-- =============================================================================

-- Update FS_DEMO_USER default role and warehouse now that they exist
ALTER USER FS_DEMO_USER SET DEFAULT_ROLE = FS_ADMIN_ROLE;
ALTER USER FS_DEMO_USER SET DEFAULT_WAREHOUSE = FS_DEV_WH;

SELECT '
📋 NEXT STEPS:
1. Switch to FS_ADMIN_ROLE:
   USE ROLE FS_ADMIN_ROLE;

2. Run 02_dev_setup.sql to create tables and deploy the data generator:
   !source 02_dev_setup.sql
   -- OR --
   snowsql -a <account> -u FS_DEMO_USER -r FS_ADMIN_ROLE -f 02_dev_setup.sql

3. (Optional) Revoke ACCOUNTADMIN from FS_DEMO_USER:
   USE ROLE ACCOUNTADMIN;
   REVOKE ROLE ACCOUNTADMIN FROM USER FS_DEMO_USER;
' AS NEXT_STEPS;

-- =============================================================================
-- END OF DBA SETUP
-- =============================================================================

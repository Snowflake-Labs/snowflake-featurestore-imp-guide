-- =============================================================================
-- Feature Store RBAC Setup
-- =============================================================================
-- This script creates roles and grants for Feature Store access control.
-- Run this with ACCOUNTADMIN or SECURITYADMIN privileges.
--
-- Tested in: tests/test_chapter_02.py (SQL validation only)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Create Feature Store Roles
-- -----------------------------------------------------------------------------

CREATE ROLE IF NOT EXISTS FS_ADMIN_ROLE;
CREATE ROLE IF NOT EXISTS FS_DEV_ROLE;
CREATE ROLE IF NOT EXISTS FS_CONSUMER_ROLE;

-- -----------------------------------------------------------------------------
-- Admin Role Privileges
-- Full control over Feature Store schema
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_ADMIN_ROLE;
GRANT ALL PRIVILEGES ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_ADMIN_ROLE;
GRANT CREATE DYNAMIC TABLE ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_ADMIN_ROLE;
GRANT CREATE VIEW ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_ADMIN_ROLE;
GRANT CREATE TAG ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_ADMIN_ROLE;

-- -----------------------------------------------------------------------------
-- Developer Role Privileges
-- Can create and modify FeatureViews, read source data (CLICKSTREAM_DATA)
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_DEV_ROLE;
GRANT USAGE ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_DEV_ROLE;
GRANT CREATE DYNAMIC TABLE ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_DEV_ROLE;
GRANT CREATE VIEW ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_DEV_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA FEATURE_STORE_DEMO.CLICKSTREAM_DATA TO ROLE FS_DEV_ROLE;

-- Future grants for source data
GRANT SELECT ON FUTURE TABLES IN SCHEMA FEATURE_STORE_DEMO.CLICKSTREAM_DATA TO ROLE FS_DEV_ROLE;

-- -----------------------------------------------------------------------------
-- Consumer Role Privileges
-- Read-only access to FeatureViews
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE FEATURE_STORE_DEMO TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;

-- Future grants for new FeatureViews
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA FEATURE_STORE_DEMO.FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;

-- -----------------------------------------------------------------------------
-- Role Hierarchy
-- Consumer < Developer < Admin < SYSADMIN
-- -----------------------------------------------------------------------------

GRANT ROLE FS_CONSUMER_ROLE TO ROLE FS_DEV_ROLE;
GRANT ROLE FS_DEV_ROLE TO ROLE FS_ADMIN_ROLE;
GRANT ROLE FS_ADMIN_ROLE TO ROLE SYSADMIN;

-- -----------------------------------------------------------------------------
-- Environment-Specific Roles (Optional)
-- -----------------------------------------------------------------------------

-- DEV environment: developers have full access
CREATE ROLE IF NOT EXISTS FS_DEV_ENV_ADMIN;
GRANT ALL PRIVILEGES ON SCHEMA FEATURE_STORE_DEMO.DEV TO ROLE FS_DEV_ENV_ADMIN;

-- TEST environment: CI/CD can write, developers read-only
CREATE ROLE IF NOT EXISTS FS_TEST_WRITER;
CREATE ROLE IF NOT EXISTS FS_TEST_READER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA FEATURE_STORE_DEMO.TEST TO ROLE FS_TEST_READER;
GRANT SELECT ON ALL VIEWS IN SCHEMA FEATURE_STORE_DEMO.TEST TO ROLE FS_TEST_READER;

-- PROD environment: inference only
CREATE ROLE IF NOT EXISTS FS_PROD_INFERENCE;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA FEATURE_STORE_DEMO.PROD TO ROLE FS_PROD_INFERENCE;
GRANT SELECT ON ALL VIEWS IN SCHEMA FEATURE_STORE_DEMO.PROD TO ROLE FS_PROD_INFERENCE;

-- =============================================================================
-- End of RBAC Setup
-- =============================================================================

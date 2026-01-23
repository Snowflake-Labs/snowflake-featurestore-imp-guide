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

CREATE ROLE IF NOT EXISTS FS_ADMIN;
CREATE ROLE IF NOT EXISTS FS_DEVELOPER;
CREATE ROLE IF NOT EXISTS FS_CONSUMER;

-- -----------------------------------------------------------------------------
-- Admin Role Privileges
-- Full control over Feature Store schema
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE ML_FEATURES TO ROLE FS_ADMIN;
GRANT ALL PRIVILEGES ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_ADMIN;
GRANT CREATE DYNAMIC TABLE ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_ADMIN;
GRANT CREATE VIEW ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_ADMIN;
GRANT CREATE TAG ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_ADMIN;

-- -----------------------------------------------------------------------------
-- Developer Role Privileges
-- Can create and modify FeatureViews, read source data
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE ML_FEATURES TO ROLE FS_DEVELOPER;
GRANT USAGE ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_DEVELOPER;
GRANT CREATE DYNAMIC TABLE ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_DEVELOPER;
GRANT CREATE VIEW ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_DEVELOPER;
GRANT SELECT ON ALL TABLES IN SCHEMA ML_FEATURES.SOURCE_DATA TO ROLE FS_DEVELOPER;

-- Future grants for source data
GRANT SELECT ON FUTURE TABLES IN SCHEMA ML_FEATURES.SOURCE_DATA TO ROLE FS_DEVELOPER;

-- -----------------------------------------------------------------------------
-- Consumer Role Privileges
-- Read-only access to FeatureViews
-- -----------------------------------------------------------------------------

GRANT USAGE ON DATABASE ML_FEATURES TO ROLE FS_CONSUMER;
GRANT USAGE ON SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_CONSUMER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_CONSUMER;
GRANT SELECT ON ALL VIEWS IN SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_CONSUMER;

-- Future grants for new FeatureViews
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_CONSUMER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA ML_FEATURES.FEATURE_STORE TO ROLE FS_CONSUMER;

-- -----------------------------------------------------------------------------
-- Role Hierarchy
-- Consumer < Developer < Admin < SYSADMIN
-- -----------------------------------------------------------------------------

GRANT ROLE FS_CONSUMER TO ROLE FS_DEVELOPER;
GRANT ROLE FS_DEVELOPER TO ROLE FS_ADMIN;
GRANT ROLE FS_ADMIN TO ROLE SYSADMIN;

-- -----------------------------------------------------------------------------
-- Environment-Specific Roles (Optional)
-- -----------------------------------------------------------------------------

-- DEV environment: developers have full access
CREATE ROLE IF NOT EXISTS FS_DEV_DEVELOPER;
GRANT ALL PRIVILEGES ON SCHEMA ML_FEATURES.DEV TO ROLE FS_DEV_DEVELOPER;

-- TEST environment: CI/CD can write, developers read-only
CREATE ROLE IF NOT EXISTS FS_TEST_WRITER;
CREATE ROLE IF NOT EXISTS FS_TEST_READER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA ML_FEATURES.TEST TO ROLE FS_TEST_READER;
GRANT SELECT ON ALL VIEWS IN SCHEMA ML_FEATURES.TEST TO ROLE FS_TEST_READER;

-- PROD environment: inference only
CREATE ROLE IF NOT EXISTS FS_PROD_INFERENCE;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA ML_FEATURES.PROD TO ROLE FS_PROD_INFERENCE;
GRANT SELECT ON ALL VIEWS IN SCHEMA ML_FEATURES.PROD TO ROLE FS_PROD_INFERENCE;

-- =============================================================================
-- End of RBAC Setup
-- =============================================================================

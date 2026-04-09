-- =============================================================================
-- GUIDE DEVELOPMENT: CLEANUP
-- =============================================================================
--
-- Tears down everything created by guide_test_env.sql.
-- Run this when you no longer need the guide development environment.
--
-- Usage:
--   snowsql -f guide_test_env_cleanup.sql
--
-- =============================================================================

USE ROLE ACCOUNTADMIN;

DROP DATABASE IF EXISTS FS_GUIDE_DB;
DROP WAREHOUSE IF EXISTS FS_GUIDE_WH;
DROP ROLE IF EXISTS FS_GUIDE_ROLE;

SELECT '✅ Guide test environment removed.' AS STATUS;

-- =============================================================================
-- END OF CLEANUP
-- =============================================================================

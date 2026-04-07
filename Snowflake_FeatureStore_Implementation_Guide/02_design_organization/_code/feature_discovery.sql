-- =============================================================================
-- Feature Discovery Queries
-- =============================================================================
-- Use these queries to find existing features before creating new ones.
-- Helps prevent feature duplication across teams.
--
-- Tested in: tests/test_chapter_02.py (SQL validation only)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Search for features by name pattern
-- -----------------------------------------------------------------------------

SELECT 
    TABLE_NAME AS FEATURE_VIEW,
    COLUMN_NAME AS FEATURE_NAME,
    COMMENT AS DESCRIPTION,
    DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_CATALOG = 'FEATURE_STORE_DEMO'
  AND TABLE_SCHEMA = 'FEATURE_STORE'
  AND (
      COLUMN_NAME LIKE '%ORDER_%' 
      OR COLUMN_NAME LIKE '%ORDER_ITEM_%'
      OR COLUMN_NAME LIKE '%EVENT_%'
      OR COMMENT ILIKE '%order%'
      OR COMMENT ILIKE '%event%'
  )
ORDER BY TABLE_NAME, COLUMN_NAME;

-- -----------------------------------------------------------------------------
-- Search FeatureViews by description
-- -----------------------------------------------------------------------------

SELECT 
    TABLE_NAME AS FEATURE_VIEW,
    TABLE_TYPE,
    COMMENT AS DESCRIPTION,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_CATALOG = 'FEATURE_STORE_DEMO'
  AND TABLE_SCHEMA = 'FEATURE_STORE'
  AND COMMENT ILIKE '%churn%'
ORDER BY CREATED DESC;

-- -----------------------------------------------------------------------------
-- List all FeatureViews (Dynamic Tables and Views)
-- -----------------------------------------------------------------------------

SELECT 
    TABLE_NAME AS FEATURE_VIEW,
    TABLE_TYPE,
    COMMENT AS DESCRIPTION,
    ROW_COUNT,
    CREATED
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_CATALOG = 'FEATURE_STORE_DEMO'
  AND TABLE_SCHEMA = 'FEATURE_STORE'
  AND TABLE_TYPE IN ('DYNAMIC TABLE', 'VIEW')
ORDER BY CREATED DESC;

-- -----------------------------------------------------------------------------
-- List all features across all FeatureViews
-- Excludes common join key columns
-- -----------------------------------------------------------------------------

SELECT 
    t.TABLE_NAME AS FEATURE_VIEW,
    c.COLUMN_NAME AS FEATURE_NAME,
    c.DATA_TYPE,
    c.COMMENT AS DESCRIPTION
FROM INFORMATION_SCHEMA.COLUMNS c
JOIN INFORMATION_SCHEMA.TABLES t 
    ON c.TABLE_NAME = t.TABLE_NAME 
    AND c.TABLE_SCHEMA = t.TABLE_SCHEMA
WHERE c.TABLE_CATALOG = 'FEATURE_STORE_DEMO'
  AND c.TABLE_SCHEMA = 'FEATURE_STORE'
  AND t.TABLE_TYPE IN ('DYNAMIC TABLE', 'VIEW')
  AND c.COLUMN_NAME NOT IN ('USER_ID', 'PRODUCT_ID', 'SESSION_ID', 'ORDER_ID', 'VISITOR_ID')  -- Exclude keys
ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION;

-- -----------------------------------------------------------------------------
-- Find potentially duplicate features
-- Features with similar names across different FeatureViews
-- -----------------------------------------------------------------------------

WITH feature_view_dupes AS (
    SELECT 
        COLUMN_NAME,
        COUNT(DISTINCT TABLE_NAME) AS FEATURE_VIEW_CNT,
        LISTAGG(DISTINCT TABLE_NAME, ', ') AS feature_views
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_CATALOG = 'FEATURE_STORE_DEMO'
      AND TABLE_SCHEMA = 'FEATURE_STORE'
      AND COLUMN_NAME NOT IN ('USER_ID', 'PRODUCT_ID', 'SESSION_ID', 'ORDER_ID', 'VISITOR_ID')
    GROUP BY COLUMN_NAME
)
SELECT *
FROM feature_view_dupes
WHERE FEATURE_VIEW_CNT > 1
ORDER BY FEATURE_VIEW_CNT DESC, COLUMN_NAME;

-- =============================================================================
-- End of Feature Discovery Queries
-- =============================================================================

-- =============================================================================
-- Feature Store Data Lineage Queries
-- =============================================================================

-- Object Dependencies: Upstream Sources of a FeatureView
-- Shows what tables/views the FeatureView (Dynamic Table) depends on.
-- REFERENCING = the FeatureView itself; REFERENCED = upstream source objects.
-- NOTE: Latency up to 3 hours. REFERENCING_OBJECT_DOMAIN = 'DYNAMIC TABLE'
--       because FeatureViews are materialized as Dynamic Tables.
SELECT
    REFERENCED_DATABASE, REFERENCED_SCHEMA, REFERENCED_OBJECT_NAME,
    REFERENCED_OBJECT_DOMAIN, DEPENDENCY_TYPE
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCING_OBJECT_NAME = 'USER_PURCHASE_FV$V1'
  AND REFERENCING_OBJECT_DOMAIN = 'DYNAMIC TABLE';

-- Object Dependencies: Downstream Consumers of a Source Table
-- Shows what FeatureViews (or other objects) consume a given source table.
-- Flip the filter to REFERENCED to find downstream dependents.
SELECT
    REFERENCING_DATABASE, REFERENCING_SCHEMA, REFERENCING_OBJECT_NAME,
    REFERENCING_OBJECT_DOMAIN, DEPENDENCY_TYPE
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCED_OBJECT_NAME = 'RAW_CLICKSTREAM'
  AND REFERENCED_OBJECT_DOMAIN = 'TABLE';

-- Access History: Track Feature Usage
-- Shows which queries accessed a FeatureView's data.
-- NOTE: BASE_OBJECTS_ACCESSED is an ARRAY of JSON objects, not a string.
--       You must FLATTEN the array and filter on the objectName field.
--       Latency up to 3 hours. Enterprise Edition required.
SELECT
    ah.QUERY_ID,
    ah.QUERY_START_TIME,
    ah.USER_NAME,
    obj.VALUE:objectName::STRING AS OBJECT_ACCESSED,
    obj.VALUE:objectDomain::STRING AS OBJECT_DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
     LATERAL FLATTEN(INPUT => ah.BASE_OBJECTS_ACCESSED) obj
WHERE obj.VALUE:objectName::STRING LIKE '%USER_PURCHASE_FV%'
  AND ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
ORDER BY ah.QUERY_START_TIME DESC
LIMIT 100;

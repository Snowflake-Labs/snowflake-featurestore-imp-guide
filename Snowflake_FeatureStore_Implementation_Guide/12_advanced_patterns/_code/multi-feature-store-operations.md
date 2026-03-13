# Multi-Feature Store Operations

## What Is a Feature Store in Snowflake?

A feature store in Snowflake is **simply a schema**. The `FeatureStore` constructor takes a `database` and a `name` (which maps to a schema):

```python
from snowflake.ml.feature_store import FeatureStore, CreationMode

fs = FeatureStore(
    session=session,
    database="MY_DB",
    name="MY_FEATURE_STORE",       # This is the schema name
    default_warehouse="MY_WH",
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)
```

This means:
- **Multiple feature stores = multiple schemas** (in the same or different databases)
- All feature store objects (FeatureViews, Entities, tags) live inside that schema
- Snowflake's standard RBAC applies to every object in the schema

## Cross-Domain ML Architecture

### Why Multiple Feature Stores?

Enterprise ML teams often need domain isolation:

| Concern | Solution |
|---------|----------|
| **Data sensitivity** | Fraud features shouldn't be visible to marketing |
| **Ownership** | Each team owns and operates their own features |
| **Lifecycle** | Different refresh frequencies, SLAs, and deprecation policies |
| **Compliance** | Regulatory boundaries between data domains |
| **Shared features** | Common features (user demographics, product catalog) reused across domains |

### Isolation Strategies

There are three levels of isolation. Choose based on your governance requirements:

#### Strategy 1: Separate Schemas in the Same Database (Recommended Default)

```
DATABASE: ML_FEATURES
├── Schema: MARKETING     ← marketing_fs
├── Schema: FRAUD         ← fraud_fs
├── Schema: RECOMMENDATIONS ← reco_fs
└── Schema: SHARED        ← shared_fs (common features)
```

```python
marketing_fs = FeatureStore(session, database="ML_FEATURES", name="MARKETING", default_warehouse="ML_WH")
fraud_fs     = FeatureStore(session, database="ML_FEATURES", name="FRAUD",     default_warehouse="ML_WH")
shared_fs    = FeatureStore(session, database="ML_FEATURES", name="SHARED",    default_warehouse="ML_WH")
```

**Pros:**
- Simplest RBAC setup (single database, schema-level grants)
- Cross-domain training sets work natively (same database)
- Single replication unit for disaster recovery
- Snowflake docs recommend: *"Storing your feature stores in a dedicated database will make it simpler to replicate them"*

**Cons:**
- All feature stores share the same database-level privileges
- Cannot restrict database-level operations per team

**When to use:** Most organizations. Start here unless you have a specific reason not to.

#### Strategy 2: Separate Databases in the Same Account

```
DATABASE: MARKETING_ML
└── Schema: FEATURE_STORE  ← marketing_fs

DATABASE: FRAUD_ML
└── Schema: FEATURE_STORE  ← fraud_fs

DATABASE: SHARED_ML
└── Schema: FEATURE_STORE  ← shared_fs
```

```python
marketing_fs = FeatureStore(session, database="MARKETING_ML", name="FEATURE_STORE", default_warehouse="MARKETING_WH")
fraud_fs     = FeatureStore(session, database="FRAUD_ML",     name="FEATURE_STORE", default_warehouse="FRAUD_WH")
shared_fs    = FeatureStore(session, database="SHARED_ML",    name="FEATURE_STORE", default_warehouse="SHARED_WH")
```

**Pros:**
- Database-level RBAC isolation (USAGE on database controls visibility)
- Per-database replication and failover
- Each team can have independent warehouses and cost attribution
- Database roles can be used for finer-grained access within each FS

**Cons:**
- More complex RBAC setup (grants needed at each database level)
- Cross-database feature joins require grants across databases
- Each database is a separate replication unit

**When to use:** Regulated industries, strict data classification requirements, or when teams need fully independent administration.

#### Strategy 3: Separate Accounts (Cross-Account Sharing)

```
Account: analytics-prod (us-west-2)
└── SHARED_ML.FEATURE_STORE  ← shared_fs (producer)

Account: fraud-prod (us-west-2)
└── FRAUD_ML.FEATURE_STORE   ← fraud_fs (consumer of shared features)
```

**Pros:**
- Maximum isolation (separate billing, separate admin, separate network policies)
- Required for cross-region or cross-cloud deployments

**Cons:**
- Requires Secure Data Sharing or database replication
- Shared features are read-only in the consumer account
- More operational overhead

**When to use:** Multi-region deployments, separate business units with independent Snowflake accounts, or when sharing features via Snowflake Marketplace.

### Decision Matrix

| Factor | Same-DB Schemas | Separate Databases | Separate Accounts |
|--------|:-:|:-:|:-:|
| Setup complexity | Low | Medium | High |
| RBAC granularity | Schema-level | Database-level | Account-level |
| Cross-domain joins | Native | Cross-DB grants | Sharing/replication |
| Cost attribution | Warehouse-level | Warehouse + storage | Full separation |
| Replication | Single unit | Per-database | Per-account |
| Regulatory isolation | Moderate | Strong | Maximum |

## Cross-Domain Training Sets

The key feature that enables multi-FS ML: `generate_training_set()` and `generate_dataset()` accept FeatureViews from **any** registered feature store, as long as the session's role has the necessary privileges.

```python
marketing_fs = FeatureStore(session, database="ML_FEATURES", name="MARKETING", default_warehouse="ML_WH")
fraud_fs     = FeatureStore(session, database="ML_FEATURES", name="FRAUD",     default_warehouse="ML_WH")
shared_fs    = FeatureStore(session, database="ML_FEATURES", name="SHARED",    default_warehouse="ML_WH")

marketing_fv = marketing_fs.get_feature_view("CAMPAIGN_FEATURES", "v1")
fraud_fv     = fraud_fs.get_feature_view("TRANSACTION_FEATURES", "v1")
user_base_fv = shared_fs.get_feature_view("USER_BASE_FEATURES", "v1")

training_set = fraud_fs.generate_training_set(
    spine_df=labeled_transactions,
    features=[
        fraud_fv,
        marketing_fv.slice(["CAMPAIGN_ENGAGEMENT_SCORE"]),
        user_base_fv,
    ],
    spine_timestamp_col="EVENT_TS",
    spine_label_cols=["IS_FRAUD"],
)
```

From the docs: *"Users who have access to more than one feature store can combine feature views from multiple feature stores to create training and inference datasets."*

### Handling Column Name Collisions

When combining FeatureViews from multiple stores, use `with_name()` or `auto_prefix=True` to avoid column name collisions:

```python
training_set = shared_fs.generate_training_set(
    spine_df=spine,
    features=[
        marketing_fv.with_name("mktg"),
        fraud_fv.with_name("fraud"),
        user_base_fv.with_name("user"),
    ],
    auto_prefix=False,   # with_name() takes precedence
)
# Result columns: mktg_CAMPAIGN_ENGAGEMENT_SCORE, fraud_TRANSACTION_VELOCITY, user_ACCOUNT_AGE, ...
```

Or let the system auto-prefix:

```python
training_set = shared_fs.generate_training_set(
    spine_df=spine,
    features=[marketing_fv, fraud_fv, user_base_fv],
    auto_prefix=True,
)
# Result columns: CAMPAIGN_FEATURES_V1_<col>, TRANSACTION_FEATURES_V1_<col>, USER_BASE_FEATURES_V1_<col>, ...
```

## RBAC Considerations

### Feature Store Access Control Model

The Feature Store defines two role archetypes per the [official docs](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/rbac):

| Role | Can Do | Typical User |
|------|--------|--------------|
| **Producer** | Create/update/delete FeatureViews and Entities, generate datasets, manage refresh | Data engineers, ML engineers |
| **Consumer** | Read FeatureViews, generate training sets, retrieve feature values | Data scientists, ML researchers |

The recommended role hierarchy:

```
SYSADMIN
  └── FS_PRODUCER (per feature store)
        └── FS_CONSUMER (per feature store)
```

Consumers inherit from Producers in the hierarchy — meaning the **Producer role includes all Consumer privileges** plus creation privileges.

### Producer Privileges

```sql
-- Schema-level creation privileges
GRANT CREATE DYNAMIC TABLE ON SCHEMA <fs_schema> TO ROLE <producer_role>;
GRANT CREATE VIEW          ON SCHEMA <fs_schema> TO ROLE <producer_role>;
GRANT CREATE TAG           ON SCHEMA <fs_schema> TO ROLE <producer_role>;
GRANT CREATE TABLE         ON SCHEMA <fs_schema> TO ROLE <producer_role>;
GRANT CREATE DATASET       ON SCHEMA <fs_schema> TO ROLE <producer_role>;

-- Warehouse access
GRANT USAGE ON WAREHOUSE <wh> TO ROLE <producer_role>;
```

Additional requirements:
- `OPERATE` on dynamic tables and tasks in the FS schema (to manage refresh settings)
- For incremental refresh: `OWNERSHIP` on source tables (to enable change tracking), or source tables must already have change tracking enabled
- `CREATE SCHEMA` is optional (only needed if the schema doesn't exist yet)

### Consumer Privileges

```sql
-- Database and schema access
GRANT USAGE ON DATABASE <fs_db> TO ROLE <consumer_role>;
GRANT USAGE ON SCHEMA <fs_schema> TO ROLE <consumer_role>;

-- Read access to FeatureViews (Dynamic Tables + Views)
GRANT SELECT, MONITOR ON FUTURE DYNAMIC TABLES IN SCHEMA <fs_schema> TO ROLE <consumer_role>;
GRANT SELECT, MONITOR ON ALL DYNAMIC TABLES IN SCHEMA <fs_schema> TO ROLE <consumer_role>;

GRANT SELECT, REFERENCES ON FUTURE VIEWS IN SCHEMA <fs_schema> TO ROLE <consumer_role>;
GRANT SELECT, REFERENCES ON ALL VIEWS IN SCHEMA <fs_schema> TO ROLE <consumer_role>;

-- Dataset access
GRANT USAGE ON FUTURE DATASETS IN SCHEMA <fs_schema> TO ROLE <consumer_role>;
GRANT USAGE ON ALL DATASETS IN SCHEMA <fs_schema> TO ROLE <consumer_role>;

-- Warehouse access
GRANT USAGE ON WAREHOUSE <wh> TO ROLE <consumer_role>;
```

### Automated Setup with Python

The `setup_feature_store` utility automates all RBAC setup:

```python
from snowflake.ml.feature_store import setup_feature_store

# Requires ACCOUNTADMIN or a role with MANAGE GRANTS + CREATE ROLE
fs = setup_feature_store(
    session=session,
    database="ML_FEATURES",
    schema="MARKETING",
    warehouse="ML_WH",
    producer_role="MARKETING_FS_PRODUCER",
    consumer_role="MARKETING_FS_CONSUMER",   # Optional; omit to skip consumer role
)
```

This creates:
- The schema (if it doesn't exist)
- The producer and consumer roles
- The role hierarchy (consumer → producer → SYSADMIN)
- All necessary grants (including future grants for new objects)

### Multi-FS RBAC Pattern

For an organization with Marketing, Fraud, and Shared feature stores:

```sql
-- Create domain-specific roles
CREATE ROLE MARKETING_FS_PRODUCER;
CREATE ROLE MARKETING_FS_CONSUMER;
CREATE ROLE FRAUD_FS_PRODUCER;
CREATE ROLE FRAUD_FS_CONSUMER;
CREATE ROLE SHARED_FS_PRODUCER;
CREATE ROLE SHARED_FS_CONSUMER;

-- Build hierarchies
GRANT ROLE MARKETING_FS_CONSUMER TO ROLE MARKETING_FS_PRODUCER;
GRANT ROLE FRAUD_FS_CONSUMER     TO ROLE FRAUD_FS_PRODUCER;
GRANT ROLE SHARED_FS_CONSUMER    TO ROLE SHARED_FS_PRODUCER;

-- Roll up to SYSADMIN
GRANT ROLE MARKETING_FS_PRODUCER TO ROLE SYSADMIN;
GRANT ROLE FRAUD_FS_PRODUCER     TO ROLE SYSADMIN;
GRANT ROLE SHARED_FS_PRODUCER    TO ROLE SYSADMIN;

-- Cross-domain access: marketing team can READ fraud + shared features
GRANT ROLE FRAUD_FS_CONSUMER  TO ROLE MARKETING_FS_PRODUCER;
GRANT ROLE SHARED_FS_CONSUMER TO ROLE MARKETING_FS_PRODUCER;

-- Cross-domain access: fraud team can READ marketing + shared features
GRANT ROLE MARKETING_FS_CONSUMER TO ROLE FRAUD_FS_PRODUCER;
GRANT ROLE SHARED_FS_CONSUMER    TO ROLE FRAUD_FS_PRODUCER;
```

Visual hierarchy:

```
SYSADMIN
├── MARKETING_FS_PRODUCER
│   ├── MARKETING_FS_CONSUMER
│   ├── FRAUD_FS_CONSUMER       ← cross-domain read access
│   └── SHARED_FS_CONSUMER      ← shared features
├── FRAUD_FS_PRODUCER
│   ├── FRAUD_FS_CONSUMER
│   ├── MARKETING_FS_CONSUMER   ← cross-domain read access
│   └── SHARED_FS_CONSUMER      ← shared features
└── SHARED_FS_PRODUCER
    └── SHARED_FS_CONSUMER
```

### Using Database Roles for Per-FS Access (Separate Databases Strategy)

When feature stores live in separate databases, database roles provide cleaner scoping:

```sql
-- In MARKETING_ML database
CREATE DATABASE ROLE MARKETING_ML.FS_READER;
GRANT USAGE ON SCHEMA MARKETING_ML.FEATURE_STORE TO DATABASE ROLE MARKETING_ML.FS_READER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA MARKETING_ML.FEATURE_STORE TO DATABASE ROLE MARKETING_ML.FS_READER;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA MARKETING_ML.FEATURE_STORE TO DATABASE ROLE MARKETING_ML.FS_READER;

-- Grant database role to account role
GRANT DATABASE ROLE MARKETING_ML.FS_READER TO ROLE FRAUD_FS_PRODUCER;
```

Database roles cannot be granted directly to users — they must be granted to account roles first.

### Key RBAC Gotchas

1. **Future grants only affect NEW objects.** Existing FeatureViews need separate `GRANT` statements. Always set up future grants before creating FeatureViews.

2. **USAGE must be granted at every level.** A role needs USAGE on the database AND the schema to see any objects inside.

3. **Entity tags count against limits.** Entities are implemented as tags. Snowflake allows 10,000 tags per account and 50 unique tags per object.

4. **Producers need Consumer privileges too.** The recommended pattern is `GRANT ROLE consumer TO ROLE producer` so producers inherit all read access.

5. **Source table access is separate.** The FS producer role needs SELECT on the source tables the FeatureView queries. These tables may live in a completely different database/schema.

6. **Warehouse is required for both roles.** Both producers and consumers need USAGE on the warehouse passed to the FeatureStore constructor.

## Replication and Sharing

### Replicating a Feature Store (Cross-Region / DR)

To replicate a feature store to another account/region, replicate the **entire database** that contains it. This replicates all schemas (including all feature stores) in the database.

This is why the docs recommend keeping feature stores in a dedicated database — it simplifies replication by avoiding unrelated schemas.

See: [Database Replication](https://docs.snowflake.com/en/user-guide/account-replication-intro)

### Sharing a Feature Store (Cross-Account)

To share features across Snowflake accounts via Secure Data Sharing:

**Option A: Share the entire feature store** — share the underlying schema. All FeatureViews in the store become visible to the consumer account.

**Option B: Share individual FeatureViews** — more granular, but requires sharing the internal tags the feature store uses:

```sql
SET FS_SHARE    = 'MY_SHARE';
SET FS_DATABASE = 'ML_FEATURES';
SET FS_SCHEMA   = 'SHARED';
SET FV_NAME     = 'USER_BASE_FV$V1';          -- name$version format
SET ENTITY_NAME = 'USER';

-- Internal tag FQNs
SET SCHEMA_FQN       = CONCAT($FS_DATABASE, '.', $FS_SCHEMA);
SET TAG_OBJECT_FQN   = CONCAT($SCHEMA_FQN, '.', 'SNOWML_FEATURE_STORE_OBJECT');
SET TAG_METADATA_FQN = CONCAT($SCHEMA_FQN, '.', 'SNOWML_FEATURE_VIEW_METADATA');
SET FULL_ENTITY_NAME = CONCAT('SNOWML_FEATURE_STORE_ENTITY_', $ENTITY_NAME);
SET ENTITY_FQN       = CONCAT($SCHEMA_FQN, '.', $FULL_ENTITY_NAME);
SET FV_FQN           = CONCAT($SCHEMA_FQN, '.', $FV_NAME);

-- Grant to share
GRANT USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO SHARE IDENTIFIER($FS_SHARE);
GRANT REFERENCE_USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO SHARE IDENTIFIER($FS_SHARE);
GRANT USAGE ON SCHEMA IDENTIFIER($SCHEMA_FQN) TO SHARE IDENTIFIER($FS_SHARE);
GRANT READ ON TAG IDENTIFIER($TAG_OBJECT_FQN) TO SHARE IDENTIFIER($FS_SHARE);
GRANT READ ON TAG IDENTIFIER($TAG_METADATA_FQN) TO SHARE IDENTIFIER($FS_SHARE);
GRANT READ ON TAG IDENTIFIER($ENTITY_FQN) TO SHARE IDENTIFIER($FS_SHARE);

-- For managed FeatureView (Dynamic Table):
GRANT SELECT ON DYNAMIC TABLE IDENTIFIER($FV_FQN) TO SHARE IDENTIFIER($FS_SHARE);

-- For external FeatureView (View):
-- GRANT SELECT ON VIEW IDENTIFIER($FV_FQN) TO SHARE IDENTIFIER($FS_SHARE);
```

Key detail: you must share the internal tags (`SNOWML_FEATURE_STORE_OBJECT`, `SNOWML_FEATURE_VIEW_METADATA`, `SNOWML_FEATURE_STORE_ENTITY_<name>`) for the consumer to reconstruct the FeatureView via the Python API.

## Best Practices

### 1. Start with One Database, Multiple Schemas

Unless you have regulatory requirements for database-level isolation, use the same-database strategy. It's the simplest to set up, the easiest to manage, and supports cross-domain training natively.

### 2. Establish a "Shared" Feature Store

Create a dedicated schema for widely-used features (user demographics, product attributes, etc.) that multiple teams consume. Grant consumer access to all domain roles.

### 3. Use `setup_feature_store()` for Consistent RBAC

The Python utility ensures all required grants (including future grants) are set up correctly. Run it once per feature store during initial setup.

### 4. Name Entities Consistently Across Stores

If `USER_ID` is a join key in the marketing FS and the fraud FS, use the same Entity name (e.g., `USER`) in both. This makes cross-domain joins straightforward.

### 5. Use `auto_prefix=True` or `with_name()` for Cross-Domain Training

When combining FeatureViews from multiple stores, column name collisions are likely. Always use prefixing.

### 6. Document Feature Store Boundaries

Maintain a registry of which feature store owns which features, who the producers are, and which teams have consumer access.

### 7. Separate Warehouses for Cost Attribution

Even with same-database schemas, use per-team warehouses for the `default_warehouse` parameter. This enables cost tracking per domain.

### 8. Set Up Future Grants Before Creating FeatureViews

Future grants on dynamic tables, views, and datasets ensure new FeatureViews are automatically accessible to consumers.

## References

- [Feature Store Overview](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/overview) — *"A feature store in Snowflake is simply a schema"*
- [Creating or Connecting to a Feature Store](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/create) — FeatureStore constructor, CreationMode, replication tip
- [Feature Store Access Control Model](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/rbac) — Producer/Consumer roles, SQL setup, Python setup
- [setup_feature_store API](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/feature_store/snowflake.ml.feature_store.setup_feature_store) — Automated RBAC setup
- [FeatureStore Class API](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/feature_store/snowflake.ml.feature_store.FeatureStore) — generate_training_set, generate_dataset, retrieve_feature_values
- [FeatureView Class API](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/feature_store/snowflake.ml.feature_store.FeatureView) — with_name(), slice()
- [Model Training and Inference](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/modeling) — Cross-FS training set generation
- [Replicating and Sharing Features](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/replication-sharing) — Database replication, Secure Data Sharing, per-FV sharing with tags
- [Working with Entities](https://docs.snowflake.com/en/developer-guide/snowflake-ml/feature-store/entities) — Entity as tags, 10K tag limit
- [Overview of Access Control](https://docs.snowflake.com/en/user-guide/security-access-control-overview) — Snowflake RBAC fundamentals
- [Database Roles](https://docs.snowflake.com/en/user-guide/security-access-control-configure#database-roles) — Per-database role scoping
- [Future Grants](https://docs.snowflake.com/en/user-guide/security-access-control-configure#future-grants) — Automatic privilege propagation
- [About Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro) — Cross-account sharing fundamentals
- [Database Replication Intro](https://docs.snowflake.com/en/user-guide/account-replication-intro) — Cross-region/cross-account replication

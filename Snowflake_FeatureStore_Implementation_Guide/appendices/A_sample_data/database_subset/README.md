# Development Database Subset Tool

Create development database "branches" from production data using Dynamic Tables for real-time sync.

> 💡 **Tip**: For an interactive experience, use the [Streamlit Data Manager](../data_manager/README.md) which wraps this CLI tool with a visual interface.

## Overview

This tool enables multi-environment setups (DEV/PROD) that mirror typical customer deployments:

```
┌─────────────────────────────────────────────────────────────────┐
│ "PRODUCTION" DATABASE (e.g., FEATURE_STORE_GUIDE)               │
│   └── CLICKSTREAM_RAW (full data)                               │
│       ├── USERS (100K)                                          │
│       ├── SESSIONS (500K)                                       │
│       ├── EVENTS (4.4M)                                         │
│       └── ... (11 tables)                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                    Dynamic Tables (subset)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ "DEVELOPMENT" DATABASE (e.g., FEATURE_STORE_GUIDE_DEV)          │
│   ├── CLICKSTREAM_RAW (same schema names)                       │
│   │   ├── USERS (1K - 10% sample)                               │
│   │   ├── SESSIONS (~5K)                                        │
│   │   ├── EVENTS (~44K)                                         │
│   │   └── ... (11 tables, referentially integral)               │
│   │                                                             │
│   └── _SUBSET_ADMIN (configuration)                             │
│       ├── USER_SAMPLE (sampled user_ids)                        │
│       ├── SUBSET_CONFIG (table mappings)                        │
│       └── SUBSET_STATUS (creation tracking)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Same Object Names**: All schemas/tables have identical names below database level
- **Environment Switching**: Change `USE DATABASE` to switch between DEV and PROD
- **Real-time Sync**: Dynamic Tables automatically refresh from production
- **Referential Integrity**: Cascading filters maintain FK relationships
- **Configurable Sample Size**: 1%, 5%, 10%, etc. of users

## Quick Start

```bash
# Set Snowflake connection
export SNOWFLAKE_CONNECTION_NAME=your_connection

# Create development database (10% sample)
python deploy.py create \
    --prod-db FEATURE_STORE_GUIDE \
    --dev-db FEATURE_STORE_GUIDE_DEV \
    --sample-pct 10

# Check status
python deploy.py status --dev-db FEATURE_STORE_GUIDE_DEV

# Suspend Dynamic Tables (cost savings)
python deploy.py suspend --dev-db FEATURE_STORE_GUIDE_DEV

# Resume Dynamic Tables
python deploy.py resume --dev-db FEATURE_STORE_GUIDE_DEV

# Teardown
python deploy.py drop --dev-db FEATURE_STORE_GUIDE_DEV
```

## Referential Integrity & Anonymous Sessions

The subset maintains referential integrity by starting from **VISITORS** (not USERS) to include anonymous sessions and events where the user hasn't been identified yet:

```
VISITOR_SAMPLE (N% random - includes anonymous visitors)
├── → VISITORS (Dynamic Table)
├── → SESSIONS (Dynamic Table) - includes anonymous sessions
│   └── → EVENTS (Dynamic Table) - includes anonymous events
│
├── USER_SAMPLE (users linked to sampled visitors)
│   ├── → USERS (Dynamic Table)
│   └── → ORDERS (Dynamic Table) - requires authenticated user
│       └── → ORDER_ITEMS (Dynamic Table)

Dimension tables (full copy - small reference data):
├── CATEGORIES, SUPPLIERS
├── PRODUCTS, PRODUCT_SUPPLIER
└── HOUSEHOLDS
```

### Why Start from Visitors?

In clickstream data, a visitor can have sessions and events **before** they create an account or log in. If we sampled by USER_ID first, we would miss:
- Anonymous browsing sessions
- Cart abandonment events before signup
- Attribution data for conversion funnels

By sampling VISITORS first, we capture the complete customer journey.

## SQL Control

```sql
-- Switch to development
USE DATABASE FEATURE_STORE_GUIDE_DEV;
USE SCHEMA CLICKSTREAM_RAW;

-- Same queries work as production
SELECT COUNT(*) FROM USERS;
SELECT COUNT(*) FROM SESSIONS;

-- Check subset configuration
SELECT * FROM _SUBSET_ADMIN.SUBSET_STATUS;

-- Manually refresh a table
ALTER DYNAMIC TABLE CLICKSTREAM_RAW.SESSIONS REFRESH;

-- Suspend all Dynamic Tables
CALL _SUBSET_ADMIN.SP_MANAGE_ALL_DTS('SUSPEND');

-- Resume all Dynamic Tables
CALL _SUBSET_ADMIN.SP_MANAGE_ALL_DTS('RESUME');
```

## Required Privileges

| Privilege | Object | Required For |
|-----------|--------|--------------|
| `USAGE` | Production database | Read source data |
| `CREATE DATABASE` | Account | Create dev database |
| `USAGE` | Warehouse | Dynamic Table refresh |

```sql
-- Grant to role
GRANT USAGE ON DATABASE FEATURE_STORE_GUIDE TO ROLE dev_role;
GRANT CREATE DATABASE ON ACCOUNT TO ROLE dev_role;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE dev_role;
```

## Sample Sizes

| Sample % | Users | Sessions | Events | Storage ~= |
|----------|-------|----------|--------|------------|
| 1%       | 1K    | ~5K      | ~44K   | ~50 MB     |
| 5%       | 5K    | ~25K     | ~220K  | ~250 MB    |
| 10%      | 10K   | ~50K     | ~440K  | ~500 MB    |

## How It Works

1. **Visitor Sampling**: Randomly select N% of VISITOR_IDs from production (includes anonymous)
2. **Cascading Filters**: Each Dynamic Table filters by the cascaded sample tables
3. **Dimension Tables**: Small reference tables are copied in full
4. **Incremental Refresh**: Dynamic Tables use INNER JOIN pattern for efficient incremental updates

### Dynamic Table Pattern

```sql
-- Sessions filtered by sampled visitors (INCREMENTAL refresh)
CREATE DYNAMIC TABLE CLICKSTREAM_RAW.SESSIONS
TARGET_LAG = '1 HOUR'
WAREHOUSE = COMPUTE_WH
AS
SELECT src.*
FROM FEATURE_STORE_GUIDE.CLICKSTREAM_RAW.SESSIONS src
INNER JOIN _SUBSET_ADMIN.VISITOR_SAMPLE s ON src.VISITOR_ID = s.VISITOR_ID;
```

> **Note**: We use `INNER JOIN` (not subqueries) to enable incremental refresh. Subqueries like `WHERE col IN (SELECT ...)` force FULL refresh mode, which is more expensive.

## File Structure

```
database_subset/
├── README.md                  # This file
├── deploy.py                  # Main deployment script
├── sql/
│   └── 01_admin_schema.sql    # Admin schema DDL
├── procedures/
│   └── 02_sp_manage_dts.sql   # Suspend/resume procedure
└── examples/
    └── 01_basic_usage.sql     # Usage examples
```

## Troubleshooting

### Dynamic Tables not refreshing

```sql
-- Check status
SELECT table_schema, table_name, scheduling_state
FROM INFORMATION_SCHEMA.TABLES
WHERE table_type = 'DYNAMIC TABLE';

-- Check warehouse
SHOW WAREHOUSES;
```

### Empty tables

```sql
-- Check sample table
SELECT COUNT(*) FROM _SUBSET_ADMIN.USER_SAMPLE;

-- Verify source data exists
SELECT COUNT(*) FROM FEATURE_STORE_GUIDE.CLICKSTREAM_RAW.USERS;
```

### Resume after suspension

```sql
-- Resume all
CALL _SUBSET_ADMIN.SP_MANAGE_ALL_DTS('RESUME');

-- Or individually
ALTER DYNAMIC TABLE CLICKSTREAM_RAW.SESSIONS RESUME;
```

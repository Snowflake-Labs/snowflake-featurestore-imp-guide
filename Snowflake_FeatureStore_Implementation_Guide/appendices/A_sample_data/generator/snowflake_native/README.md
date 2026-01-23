# Snowflake-Native Incremental Data Generation

Runs continuous incremental data generation **inside Snowflake** using Tasks and Stored Procedures.

## Schema Organization

```
FEATURE_STORE_GUIDE (Database)
├── CLICKSTREAM_RAW (Data Schema)
│   ├── CATEGORIES, SUPPLIERS, HOUSEHOLDS, PRODUCTS, PRODUCT_SUPPLIER
│   ├── VISITORS, USERS
│   ├── SESSIONS, EVENTS
│   └── ORDERS, ORDER_ITEMS
│
└── CLICKSTREAM_ADMIN (Admin Schema) 
    ├── GENERATION_CONFIG    -- Batch sizes, enabled flag
    ├── GENERATION_STATE     -- ID counters, last batch timestamp
    ├── GENERATION_LOG       -- Batch history and errors
    ├── GENERATION_STATUS    -- Combined view for monitoring
    ├── GENERATE_INCREMENTAL_BATCH()  -- Python stored procedure
    └── INCREMENTAL_DATA_TASK         -- Scheduled task (1 min default)
```

## Quick Start

```bash
# Set connection
export SNOWFLAKE_CONNECTION_NAME=your_connection

# Deploy and test (creates CLICKSTREAM_ADMIN schema)
python deploy.py

# Deploy and start continuous generation
python deploy.py --start

# Check status
python deploy.py --status

# Stop generation
python deploy.py --stop
```

## SQL Commands

```sql
-- Start/stop task
ALTER TASK FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK RESUME;
ALTER TASK FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK SUSPEND;

-- Monitor
SELECT * FROM FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.GENERATION_STATUS;
SELECT * FROM FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.GENERATION_LOG ORDER BY BATCH_TS DESC LIMIT 10;

-- Adjust batch sizes
UPDATE FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.GENERATION_CONFIG 
SET SESSIONS_PER_BATCH = 100, ORDERS_PER_BATCH = 10;

-- Change schedule (minimum 10 seconds)
ALTER TASK FEATURE_STORE_GUIDE.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK 
SET SCHEDULE = '30 SECOND';
```

## Files

| File | Purpose |
|------|---------|
| `deploy.py` | Python deployment script |
| `sproc_generate_batch.sql` | Stored procedure SQL (template) |
| `control_generator.sql` | SQL command reference |

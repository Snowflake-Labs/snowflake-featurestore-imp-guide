# Clickstream Data Generator

Synthetic clickstream dataset generator for the Snowflake Feature Store Implementation Guide.

> 💡 **Tip**: For an interactive experience, use the [Streamlit Data Manager](../data_manager/README.md) which wraps this CLI tool with a visual interface.

## Quick Start

### Option 1: Streamlit UI (Interactive)

```bash
cd ../data_manager/
streamlit run app.py
```

### Option 2: CLI (Scriptable)

```bash
# Set Snowflake connection
export SNOWFLAKE_CONNECTION_NAME=your_connection

# Initial load (scale 0.01 = ~1K users)
python main.py --scale 0.01 --output snowflake

# Custom database (if you can't create new databases)
python main.py --scale 0.01 --output snowflake --database MY_DB --schema MY_SCHEMA
```

## Required Privileges

### Minimum (Using Existing Database)

| Privilege | Object | Required For |
|-----------|--------|--------------|
| `USAGE` | Warehouse | Query execution |
| `USAGE` | Database | Access database |
| `CREATE SCHEMA` | Database | Create CLICKSTREAM_RAW |
| `CREATE TABLE` | Schema | Create data tables |
| `CREATE STAGE` | Schema | Bulk loading (Parquet upload) |

```sql
-- Grant to existing database
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE my_role;
GRANT USAGE ON DATABASE my_database TO ROLE my_role;
GRANT CREATE SCHEMA ON DATABASE my_database TO ROLE my_role;
```

### Full Setup (Creating New Database)

| Privilege | Object | Required For |
|-----------|--------|--------------|
| `CREATE DATABASE` | Account | Create FEATURE_STORE_GUIDE |
| `USAGE` | Warehouse | Query execution |

```sql
-- Grant full privileges
GRANT CREATE DATABASE ON ACCOUNT TO ROLE my_role;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE my_role;
```

### Incremental Generator (Additional)

| Privilege | Object | Required For |
|-----------|--------|--------------|
| `CREATE PROCEDURE` | Schema | Create stored procedure |
| `CREATE TASK` | Schema | Create scheduled task |
| `EXECUTE TASK` | Account | Run tasks |

```sql
-- Grant incremental generator privileges
GRANT CREATE PROCEDURE ON SCHEMA clickstream_admin TO ROLE my_role;
GRANT CREATE TASK ON SCHEMA clickstream_admin TO ROLE my_role;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE my_role;
```

> **Tip**: If you lack `CREATE DATABASE`, use `--database MY_EXISTING_DB` to target an existing database.

## Command Reference

### Initial Load (main.py)

```bash
# Basic usage
python main.py --scale 0.01 --output snowflake

# Custom database/schema
python main.py --scale 0.1 --database MY_DATABASE --schema MY_SCHEMA --output snowflake

# Large scale with bulk loading (Parquet + COPY INTO)
python main.py --scale 1.0 --output snowflake --method bulk

# CSV/Parquet export only
python main.py --scale 0.01 --output csv --output-dir ./data
python main.py --scale 0.01 --output parquet --output-dir ./data

# Custom date range
python main.py --scale 0.1 --start-date 2023-01-01 --end-date 2024-12-31 --output snowflake
```

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--scale` | 0.01 | Scale factor (0.01=1K, 0.1=10K, 1.0=100K users) |
| `--output` | csv | Output: `csv`, `snowflake`, `both`, `parquet` |
| `--method` | simple | Loading: `simple` (in-memory) or `bulk` (Parquet+COPY) |
| `--database` | FEATURE_STORE_GUIDE | Target database name |
| `--schema` | CLICKSTREAM_RAW | Target schema name |
| `--output-dir` | ./output | Directory for CSV/Parquet files |
| `--start-date` | 2022-01-01 | Start date for historical data |
| `--end-date` | 2024-12-31 | End date for historical data |

### Incremental Generation (snowflake_native/)

```bash
cd snowflake_native/

python deploy.py                    # Deploy and test
python deploy.py --start            # Deploy and start task
python deploy.py --status           # Check status  
python deploy.py --stop             # Stop task
```

## Schema Organization

```
<DATABASE> (e.g., FEATURE_STORE_GUIDE)
├── CLICKSTREAM_RAW (Data)
│   ├── CATEGORIES, SUPPLIERS, HOUSEHOLDS
│   ├── PRODUCTS, PRODUCT_SUPPLIER
│   ├── VISITORS, USERS
│   ├── SESSIONS, EVENTS
│   └── ORDERS, ORDER_ITEMS
│
└── CLICKSTREAM_ADMIN (Generator - only if using incremental)
    ├── GENERATION_CONFIG
    ├── GENERATION_STATE
    ├── GENERATION_LOG
    └── INCREMENTAL_DATA_TASK
```

## Scale Factors

| Scale | Users | Sessions | Events | Orders | Memory ~= |
|-------|-------|----------|--------|--------|-----------|
| 0.01  | 1K    | 5K       | 44K    | 250    | 50 MB     |
| 0.1   | 10K   | 50K      | 440K   | 2.5K   | 500 MB    |
| 1.0   | 100K  | 500K     | 4.4M   | 25K    | 5 GB      |

For scale >= 0.5, use `--method bulk` to avoid memory issues.

## Bulk Loading

When using `--method bulk`:
1. Data is written to Parquet files in `../data/scale_{factor}/`
2. Files are uploaded to Snowflake internal stage
3. COPY INTO loads data in parallel
4. Parquet files are retained for inspection

```bash
# Bulk load - files saved to ../data/scale_1.0/
python main.py --scale 1.0 --output snowflake --method bulk

# Check generated files
ls -la ../data/scale_1.0/
```

## SQL Control (Incremental Generator)

```sql
-- Start/stop continuous generation
ALTER TASK <DB>.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK RESUME;
ALTER TASK <DB>.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK SUSPEND;

-- Monitor
SELECT * FROM <DB>.CLICKSTREAM_ADMIN.GENERATION_STATUS;
SELECT * FROM <DB>.CLICKSTREAM_ADMIN.GENERATION_LOG ORDER BY BATCH_TS DESC LIMIT 10;

-- Adjust configuration
UPDATE <DB>.CLICKSTREAM_ADMIN.GENERATION_CONFIG 
SET SESSIONS_PER_BATCH = 100, ORDERS_PER_BATCH = 10;

-- Change schedule (minimum 10 seconds)
ALTER TASK <DB>.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK SET SCHEDULE = '30 SECOND';
```

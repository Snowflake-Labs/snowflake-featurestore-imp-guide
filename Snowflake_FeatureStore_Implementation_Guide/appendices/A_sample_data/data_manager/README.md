# Clickstream Data Manager

A unified interface for managing clickstream data - available as both a **Streamlit UI** and **CLI tools**.

## Quick Start

### Option 1: Streamlit UI (Recommended for Interactive Use)

```bash
# Set connection
export SNOWFLAKE_CONNECTION_NAME=your_connection

# Run the app
cd data_manager/
streamlit run app.py
```

The UI provides:
- 📊 **Overview** - View current data status
- 📥 **Initial Load** - Generate and load synthetic data
- 🔄 **Incremental Generator** - Manage continuous data generation
- 🌿 **Development Branch** - Create sampled dev environments
- 📚 **Public Datasets** - Load standard ML datasets
- 📈 **Monitoring** - Track task and DT executions

### Option 2: CLI Tools

```bash
# Initial data load
cd generator/
python main.py --scale 0.01 --output snowflake

# Incremental generator
cd generator/snowflake_native/
python deploy.py --start

# Development branch
cd database_subset/
python deploy.py create --prod-db PROD --dev-db DEV --sample-pct 10

# Public datasets
cd public_datasets/
python load_datasets.py all
```

### Option 3: Python API

```python
from data_manager.core import DataManager

dm = DataManager()
dm.connect()

# Initial load
result = dm.run_initial_load(scale=0.01)

# Create dev branch
result = dm.create_dev_branch("MY_DEV_DB", sample_pct=10)

# Monitor
row_counts = dm.get_table_row_counts()
```

## Features

| Feature | Streamlit UI | CLI | Python API |
|---------|-------------|-----|------------|
| Initial Data Load | ✅ | ✅ `generator/main.py` | ✅ `dm.run_initial_load()` |
| Incremental Generator | ✅ | ✅ `snowflake_native/deploy.py` | ✅ `dm.deploy_incremental_generator()` |
| Development Branch | ✅ | ✅ `database_subset/deploy.py` | ✅ `dm.create_dev_branch()` |
| Public Datasets | ✅ | ✅ `public_datasets/load_datasets.py` | ✅ `dm.load_public_dataset()` |
| Monitoring | ✅ | - | ✅ `dm.get_*_history()` |

## Screenshots

### Overview Dashboard
```
┌─────────────────────────────────────────────────────────────┐
│ 📊 Data Overview                                            │
├─────────────────────────────────────────────────────────────┤
│  Total Tables: 11    Total Rows: 150K                       │
│  Visitors: 10K       Events: 100K                           │
├─────────────────────────────────────────────────────────────┤
│  [Bar chart of table row counts]                            │
└─────────────────────────────────────────────────────────────┘
```

### Incremental Generator
```
┌─────────────────────────────────────────────────────────────┐
│ 🔄 Incremental Data Generator                               │
├─────────────────────────────────────────────────────────────┤
│  🟢 Task: RUNNING    Sessions/Batch: 50    Orders/Batch: 5  │
├─────────────────────────────────────────────────────────────┤
│  [▶️ Start] [⏹️ Stop] [🚀 Deploy]                           │
├─────────────────────────────────────────────────────────────┤
│  Recent Executions:                                         │
│  | Batch TS           | Sessions | Events | Duration |      │
│  | 2024-01-22 10:00  | 50       | 458    | 2.3s     |      │
└─────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Install dependencies
pip install streamlit pandas

# Streamlit is optional - CLI tools work without it
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SNOWFLAKE_CONNECTION_NAME` | Named connection from connections.toml | - |
| `SNOWFLAKE_ACCOUNT` | Snowflake account (if not using named connection) | - |
| `SNOWFLAKE_USER` | Snowflake username | - |
| `SNOWFLAKE_PASSWORD` | Snowflake password | - |
| `SNOWFLAKE_WAREHOUSE` | Warehouse name | `COMPUTE_WH` |
| `SNOWFLAKE_DATABASE` | Database name | `FEATURE_STORE_GUIDE` |
| `SNOWFLAKE_SCHEMA` | Schema name | `CLICKSTREAM_RAW` |

### Named Connection (Recommended)

Create `~/.snowflake/connections.toml`:

```toml
[my_connection]
account = "your_account"
user = "your_user"
password = "your_password"
warehouse = "COMPUTE_WH"
database = "FEATURE_STORE_GUIDE"
```

Then:
```bash
export SNOWFLAKE_CONNECTION_NAME=my_connection
```

## File Structure

```
data_manager/
├── README.md          # This file
├── app.py             # Streamlit application
├── core.py            # Core operations module (used by CLI and UI)
└── requirements.txt   # Python dependencies
```

## Comparison: UI vs CLI

| Use Case | Recommended |
|----------|-------------|
| First-time setup | 🖥️ Streamlit UI |
| Interactive exploration | 🖥️ Streamlit UI |
| CI/CD automation | 💻 CLI |
| Scripting | 🐍 Python API |
| Production scheduling | 💻 CLI (cron/Airflow) |

## Troubleshooting

### Streamlit not starting

```bash
# Check Streamlit is installed
pip install streamlit

# Verify port is free
streamlit run app.py --server.port 8502
```

### Connection issues

```bash
# Test connection with CLI first
cd generator/
python -c "from main import get_session; get_session()"
```

### Import errors

```bash
# Ensure you're in the data_manager directory
cd Snowflake_FeatureStore_Implementation_Guide/appendices/A_sample_data/data_manager
```

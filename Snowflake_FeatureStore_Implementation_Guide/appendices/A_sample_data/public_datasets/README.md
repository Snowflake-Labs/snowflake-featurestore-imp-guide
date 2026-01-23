# Public ML Datasets Loader

Downloads and loads popular public ML datasets into Snowflake.

> 💡 **Tip**: For an interactive experience, use the [Streamlit Data Manager](../data_manager/README.md) which wraps this CLI tool with a visual interface.

## Required Privileges

| Privilege | Object | Required For |
|-----------|--------|--------------|
| `USAGE` | Warehouse | Query execution |
| `USAGE` | Database | Access database (if using existing) |
| `CREATE DATABASE` | Account | Create new database (optional) |
| `CREATE SCHEMA` | Database | Create PUBLIC_DATASETS schema |
| `CREATE TABLE` | Schema | Create dataset tables |

```sql
-- Minimum privileges (existing database)
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE my_role;
GRANT USAGE ON DATABASE my_database TO ROLE my_role;
GRANT CREATE SCHEMA ON DATABASE my_database TO ROLE my_role;
```

## Quick Start

```bash
# Set Snowflake connection
export SNOWFLAKE_CONNECTION_NAME=your_connection

# List available datasets
python load_datasets.py --list

# Load specific dataset
python load_datasets.py penguins

# Load all datasets
python load_datasets.py all

# Load to custom database/schema
python load_datasets.py penguins titanic --database MY_DB --schema PUBLIC_DATA
```

## Available Datasets

| Dataset | Rows | Sample | Description |
|---------|------|--------|-------------|
| `penguins` | 344 | All | Palmer Penguins - modern Iris replacement |
| `titanic` | 891 | All | Titanic Survival - binary classification |
| `iris` | 150 | All | Iris Flower - classic multiclass |
| `wine` | 1,599 | All | Wine Quality - regression/classification |
| `california_housing` | 20,640 | All | California Housing - regression |
| `nyc_taxi` | ~3M | 50K | NYC Taxi Trips - temporal features, fare prediction |
| `credit_card_fraud` | 284K | 50K | Credit Card Fraud - imbalanced, temporal |

> **Note**: Large datasets (`nyc_taxi`, `credit_card_fraud`) are sampled by default. Use `--full` for complete data.

## Output Options

```bash
# Load to Snowflake (default)
python load_datasets.py penguins --output snowflake

# Save to CSV only
python load_datasets.py penguins --output csv --output-dir ./data

# Both
python load_datasets.py penguins --output both

# Full dataset for large datasets (no sampling)
python load_datasets.py nyc_taxi --full
```

## Data Sources

| Dataset | Source | License |
|---------|--------|---------|
| Penguins | [palmerpenguins](https://allisonhorst.github.io/palmerpenguins/) | CC0 1.0 |
| Titanic | [Kaggle](https://www.kaggle.com/c/titanic) | Public Domain |
| Iris | [UCI ML Repository](https://archive.ics.uci.edu/ml/datasets/iris) | CC BY 4.0 |
| Wine | [UCI ML Repository](https://archive.ics.uci.edu/ml/datasets/wine+quality) | CC BY 4.0 |
| California Housing | [scikit-learn](https://scikit-learn.org/stable/datasets/real_world.html) | Public Domain |
| NYC Taxi | [NYC TLC](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | Public Domain |
| Credit Card Fraud | [Kaggle/ULB](https://www.kaggle.com/mlg-ulb/creditcardfraud) | DbCL 1.0 |

All datasets are open source and suitable for educational use.

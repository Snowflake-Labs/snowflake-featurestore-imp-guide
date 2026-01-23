#!/usr/bin/env python3
"""
Public ML Datasets Loader for Snowflake
=======================================

Downloads and loads popular public ML datasets into Snowflake.

Usage:
    python load_datasets.py --list              # List available datasets
    python load_datasets.py penguins            # Load specific dataset
    python load_datasets.py all                 # Load all datasets
    python load_datasets.py penguins titanic    # Load multiple datasets

Datasets:
    - penguins: Palmer Penguins (344 rows)
    - titanic: Titanic Survival (891 rows)
    - iris: Iris Flower (150 rows)
    - wine: Wine Quality (6497 rows)
    - california_housing: California Housing (20640 rows)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List

import pandas as pd


# Dataset registry with source URLs
DATASETS = {
    "penguins": {
        "name": "Palmer Penguins",
        "url": "https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv",
        "rows": 344,
        "description": "Penguin species classification - modern Iris replacement",
        "table_name": "PENGUINS",
    },
    "titanic": {
        "name": "Titanic Survival",
        "url": "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv",
        "rows": 891,
        "description": "Classic binary classification - survival prediction",
        "table_name": "TITANIC",
    },
    "iris": {
        "name": "Iris Flower",
        "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv",
        "rows": 150,
        "description": "Classic multiclass classification",
        "table_name": "IRIS",
    },
    "wine": {
        "name": "Wine Quality",
        "url": "https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv",
        "rows": 1599,
        "description": "Wine quality score prediction (red wine)",
        "table_name": "WINE_QUALITY",
        "sep": ";",
    },
    "california_housing": {
        "name": "California Housing",
        "url": "sklearn",  # Special case - load from sklearn
        "rows": 20640,
        "description": "House price regression",
        "table_name": "CALIFORNIA_HOUSING",
    },
    "nyc_taxi": {
        "name": "NYC Taxi Trips",
        "url": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet",
        "rows": 2964624,  # January 2024 sample
        "description": "Taxi trip data - temporal features, fare prediction",
        "table_name": "NYC_TAXI_TRIPS",
        "format": "parquet",
        "sample": 50000,  # Sample to keep size manageable
    },
    "credit_card_fraud": {
        "name": "Credit Card Fraud",
        "url": "openml",  # Special case - load from OpenML
        "openml_id": 1597,  # OpenML dataset ID for credit card fraud
        "rows": 284807,
        "description": "Fraud detection - imbalanced classification, temporal",
        "table_name": "CREDIT_CARD_FRAUD",
        "sample": 50000,  # Sample to keep size manageable
    },
}


def list_datasets():
    """Print available datasets."""
    print("\nAvailable Datasets:")
    print("-" * 70)
    for key, info in DATASETS.items():
        print(f"  {key:20} {info['rows']:>8,} rows  {info['description']}")
    print()


def download_dataset(dataset_key: str, full: bool = False) -> pd.DataFrame:
    """Download a dataset and return as DataFrame.
    
    Args:
        dataset_key: Key from DATASETS registry
        full: If True, load full dataset without sampling
    """
    if dataset_key not in DATASETS:
        print(f"Unknown dataset: {dataset_key}")
        list_datasets()
        sys.exit(1)
    
    info = DATASETS[dataset_key]
    print(f"  Downloading {info['name']}...")
    
    if info["url"] == "sklearn":
        # Special case for sklearn datasets
        from sklearn.datasets import fetch_california_housing
        data = fetch_california_housing(as_frame=True)
        df = data.frame
        df.columns = [c.upper().replace(" ", "_") for c in df.columns]
    elif info["url"] == "openml":
        # Special case for OpenML datasets
        try:
            from sklearn.datasets import fetch_openml
            data = fetch_openml(data_id=info["openml_id"], as_frame=True, parser="auto")
            df = data.frame
            df.columns = [c.upper().replace(" ", "_").replace(".", "_") for c in df.columns]
        except Exception as e:
            print(f"    Error loading from OpenML: {e}")
            print(f"    Tip: Install scikit-learn with: pip install scikit-learn")
            sys.exit(1)
    elif info.get("format") == "parquet":
        # Handle parquet files (e.g., NYC Taxi)
        try:
            df = pd.read_parquet(info["url"])
        except Exception as e:
            print(f"    Error loading parquet: {e}")
            print(f"    Tip: Install pyarrow with: pip install pyarrow")
            sys.exit(1)
        df.columns = [c.upper().replace(" ", "_").replace(".", "_") for c in df.columns]
    else:
        sep = info.get("sep", ",")
        df = pd.read_csv(info["url"], sep=sep)
        # Standardize column names
        df.columns = [c.upper().replace(" ", "_").replace(".", "_") for c in df.columns]
    
    # Apply sampling if configured and not requesting full dataset
    sample_size = info.get("sample")
    if sample_size and not full and len(df) > sample_size:
        print(f"    Sampling {sample_size:,} rows from {len(df):,} (use --full for complete dataset)")
        df = df.sample(n=sample_size, random_state=42)
    
    print(f"    Downloaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def get_session():
    """Get Snowflake session."""
    from snowflake.snowpark import Session
    
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        return Session.builder.configs({"connection_name": connection_name}).create()
    
    # Fallback to individual env vars
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    password = os.environ.get("SNOWFLAKE_PASSWORD")
    
    if not all([account, user, password]):
        raise ValueError(
            "Set SNOWFLAKE_CONNECTION_NAME or SNOWFLAKE_ACCOUNT/USER/PASSWORD"
        )
    
    return Session.builder.configs({
        "account": account,
        "user": user,
        "password": password,
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    }).create()


def load_to_snowflake(df: pd.DataFrame, table_name: str, session, database: str, schema: str):
    """Load DataFrame to Snowflake table."""
    print(f"  Loading to {database}.{schema}.{table_name}...")
    
    # Ensure schema exists
    session.sql(f"CREATE DATABASE IF NOT EXISTS {database}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}").collect()
    session.sql(f"USE SCHEMA {database}.{schema}").collect()
    
    # Create Snowpark DataFrame and save
    snow_df = session.create_dataframe(df)
    snow_df.write.mode("overwrite").save_as_table(table_name)
    
    print(f"    ✓ Loaded {len(df):,} rows to {table_name}")


def save_to_csv(df: pd.DataFrame, dataset_key: str, output_dir: Path):
    """Save DataFrame to CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{dataset_key}.csv"
    df.to_csv(file_path, index=False)
    print(f"    Saved to {file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Load public ML datasets into Snowflake",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python load_datasets.py --list
    python load_datasets.py penguins
    python load_datasets.py all --database MY_DB
    python load_datasets.py iris titanic --output csv
        """
    )
    
    parser.add_argument(
        "datasets",
        nargs="*",
        help="Dataset(s) to load. Use 'all' for all datasets."
    )
    parser.add_argument("--list", action="store_true", help="List available datasets")
    parser.add_argument("--database", default="FEATURE_STORE_GUIDE")
    parser.add_argument("--schema", default="PUBLIC_DATASETS")
    parser.add_argument(
        "--output",
        choices=["snowflake", "csv", "both"],
        default="snowflake",
        help="Output destination"
    )
    parser.add_argument(
        "--output-dir",
        default="./data",
        help="Directory for CSV output"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Load full dataset without sampling (for large datasets)"
    )
    
    args = parser.parse_args()
    
    if args.list or not args.datasets:
        list_datasets()
        return
    
    # Expand 'all' to all datasets
    datasets_to_load = (
        list(DATASETS.keys()) if "all" in args.datasets else args.datasets
    )
    
    # Validate
    for ds in datasets_to_load:
        if ds not in DATASETS and ds != "all":
            print(f"Unknown dataset: {ds}")
            list_datasets()
            sys.exit(1)
    
    print(f"\nLoading {len(datasets_to_load)} dataset(s)...")
    print(f"  Target: {args.database}.{args.schema}")
    print()
    
    # Get session if loading to Snowflake
    session = None
    if args.output in ["snowflake", "both"]:
        try:
            session = get_session()
            print(f"  Connected to Snowflake")
        except Exception as e:
            print(f"  ❌ Connection failed: {e}")
            sys.exit(1)
    
    # Load each dataset
    for dataset_key in datasets_to_load:
        info = DATASETS[dataset_key]
        print(f"\n[{info['name']}]")
        
        df = download_dataset(dataset_key, full=args.full)
        
        if args.output in ["csv", "both"]:
            save_to_csv(df, dataset_key, Path(args.output_dir))
        
        if args.output in ["snowflake", "both"]:
            load_to_snowflake(
                df, info["table_name"], session, args.database, args.schema
            )
    
    if session:
        session.close()
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()

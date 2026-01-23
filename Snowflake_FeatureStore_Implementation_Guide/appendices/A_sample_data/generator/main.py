"""
Clickstream Data Generator - Main Entry Point

This script generates synthetic clickstream data and loads it into Snowflake.

Usage:
    # Generate with default settings (small scale for testing)
    python main.py
    
    # Generate with custom scale factor
    python main.py --scale 0.1
    
    # Generate to local CSV files
    python main.py --output csv --output-dir ./data
    
    # Generate and load to Snowflake
    python main.py --output snowflake

Environment Variables (for Snowflake):
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_DATABASE
    SNOWFLAKE_SCHEMA
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import DataConfig, SnowflakeConfig, SCALE_FACTOR
from generators import (
    generate_categories,
    generate_suppliers,
    generate_households,
    generate_products,
    generate_product_suppliers,
    generate_visitors,
    generate_users,
    generate_sessions,
    generate_events,
    generate_orders,
    generate_order_items,
)


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_summary(config: DataConfig):
    """Print expected data summary."""
    print_header("Data Generation Summary")
    print(f"Scale Factor: {config.scale}")
    print(f"Date Range: {config.start_date.date()} to {config.end_date.date()}")
    print("\nExpected Row Counts:")
    for table, count in config.summary().items():
        print(f"  {table:20} {count:>12,}")
    print()


def generate_all_data(config: DataConfig, show_progress: bool = True) -> Dict[str, List[Dict]]:
    """
    Generate all tables in dependency order.
    
    Returns dict mapping table name to list of row dicts.
    """
    data = {}
    
    # 1. Categories (no dependencies)
    print_header("1/11 Generating CATEGORIES")
    data["CATEGORIES"] = generate_categories(config)
    print(f"  Generated {len(data['CATEGORIES']):,} rows")
    
    # 2. Suppliers (no dependencies)
    print_header("2/11 Generating SUPPLIERS")
    data["SUPPLIERS"] = generate_suppliers(config)
    print(f"  Generated {len(data['SUPPLIERS']):,} rows")
    
    # 3. Households (no dependencies)
    print_header("3/11 Generating HOUSEHOLDS")
    data["HOUSEHOLDS"] = generate_households(config)
    print(f"  Generated {len(data['HOUSEHOLDS']):,} rows")
    
    # 4. Products (depends on CATEGORIES)
    print_header("4/11 Generating PRODUCTS")
    data["PRODUCTS"] = generate_products(config, data["CATEGORIES"], data["SUPPLIERS"])
    print(f"  Generated {len(data['PRODUCTS']):,} rows")
    
    # 5. Product Suppliers (depends on PRODUCTS, SUPPLIERS)
    print_header("5/11 Generating PRODUCT_SUPPLIER")
    data["PRODUCT_SUPPLIER"] = generate_product_suppliers(config, data["PRODUCTS"], data["SUPPLIERS"])
    print(f"  Generated {len(data['PRODUCT_SUPPLIER']):,} rows")
    
    # 6. Visitors (no dependencies)
    print_header("6/11 Generating VISITORS")
    data["VISITORS"] = generate_visitors(config)
    print(f"  Generated {len(data['VISITORS']):,} rows")
    
    # 7. Users (depends on VISITORS, HOUSEHOLDS)
    print_header("7/11 Generating USERS")
    data["USERS"] = generate_users(config, data["VISITORS"], data["HOUSEHOLDS"])
    print(f"  Generated {len(data['USERS']):,} rows")
    
    # 8. Sessions (depends on VISITORS, USERS)
    print_header("8/11 Generating SESSIONS")
    data["SESSIONS"] = generate_sessions(config, data["VISITORS"], data["USERS"])
    print(f"  Generated {len(data['SESSIONS']):,} rows")
    
    # 9. Events (depends on SESSIONS, PRODUCTS) - Large table
    print_header("9/11 Generating EVENTS")
    data["EVENTS"] = generate_events(config, data["SESSIONS"], data["PRODUCTS"], show_progress=show_progress)
    print(f"  Generated {len(data['EVENTS']):,} rows")
    
    # 10. Orders (depends on USERS, SESSIONS)
    print_header("10/11 Generating ORDERS")
    data["ORDERS"] = generate_orders(config, data["USERS"], data["SESSIONS"], show_progress=show_progress)
    print(f"  Generated {len(data['ORDERS']):,} rows")
    
    # 11. Order Items (depends on ORDERS, PRODUCT_SUPPLIER, PRODUCTS)
    print_header("11/11 Generating ORDER_ITEMS")
    data["ORDER_ITEMS"] = generate_order_items(
        config, data["ORDERS"], data["PRODUCT_SUPPLIER"], data["PRODUCTS"], show_progress=show_progress
    )
    print(f"  Generated {len(data['ORDER_ITEMS']):,} rows")
    
    return data


def save_to_csv(data: Dict[str, List[Dict]], output_dir: str):
    """Save generated data to CSV files."""
    import csv
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print_header("Saving to CSV")
    
    for table_name, rows in data.items():
        if not rows:
            continue
        
        file_path = output_path / f"{table_name.lower()}.csv"
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"  Saved {table_name} to {file_path}")


def save_to_parquet(data: Dict[str, List[Dict]], output_dir: str):
    """Save generated data to Parquet files (more efficient for large datasets)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print_header("Saving to Parquet")
    
    for table_name, rows in data.items():
        if not rows:
            continue
        
        file_path = output_path / f"{table_name.lower()}.parquet"
        
        # Convert to PyArrow Table
        table = pa.Table.from_pylist(rows)
        
        # Write with compression
        pq.write_table(table, file_path, compression="snappy")
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        print(f"  Saved {table_name} to {file_path} ({file_size_mb:.1f} MB)")


def load_to_snowflake(data: Dict[str, List[Dict]], sf_config: SnowflakeConfig, session=None):
    """Load generated data into Snowflake using Snowpark.
    
    Args:
        data: Dict mapping table name to list of row dicts
        sf_config: Snowflake connection configuration
        session: Optional existing Snowpark session to reuse
    """
    print_header("Loading to Snowflake")
    
    # Reuse existing session or create new one
    close_session = False
    if session is None:
        close_session = True
        try:
            from snowflake.snowpark import Session
        except ImportError:
            print("ERROR: snowflake-snowpark-python not installed.")
            print("Install with: pip install snowflake-snowpark-python")
            sys.exit(1)
        
        # Check config first, then environment variable
        connection_name = sf_config.connection_name or os.environ.get("SNOWFLAKE_CONNECTION_NAME")
        if connection_name:
            print(f"  Using named connection: {connection_name}")
            session = Session.builder.configs({"connection_name": connection_name}).create()
        else:
            connection_params = {
                "account": sf_config.account,
                "user": sf_config.user,
                "password": sf_config.password,
                "role": sf_config.role,
                "warehouse": sf_config.warehouse,
                "database": sf_config.database,
                "schema": sf_config.schema,
            }
            session = Session.builder.configs(connection_params).create()
    else:
        print("  Using existing session")
    
    # Create database and schema if not exists
    session.sql(f"CREATE DATABASE IF NOT EXISTS {sf_config.database}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {sf_config.database}.{sf_config.schema}").collect()
    session.sql(f"USE SCHEMA {sf_config.database}.{sf_config.schema}").collect()
    
    # Table creation order (respects foreign keys)
    table_order = [
        "CATEGORIES", "SUPPLIERS", "HOUSEHOLDS", "PRODUCTS", "PRODUCT_SUPPLIER",
        "VISITORS", "USERS", "SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"
    ]
    
    for table_name in table_order:
        rows = data.get(table_name, [])
        if not rows:
            continue
        
        print(f"  Loading {table_name} ({len(rows):,} rows)...")
        
        # Convert to DataFrame and write
        import pandas as pd
        pdf = pd.DataFrame(rows)
        
        # Write to Snowflake table (overwrite)
        df = session.create_dataframe(pdf)
        df.write.mode("overwrite").save_as_table(table_name)
        
        print(f"    ✓ {table_name} loaded")
    
    # Only close session if we created it
    if close_session:
        session.close()
    print("\n  All tables loaded successfully!")


def load_to_snowflake_bulk(data: Dict[str, List[Dict]], sf_config: SnowflakeConfig, output_dir: Path = None, session=None):
    """
    Load generated data into Snowflake using scalable Parquet + COPY INTO.
    
    This method is more memory-efficient for large datasets:
    1. Writes data to local Parquet files
    2. Uploads to Snowflake internal stage
    3. Uses COPY INTO for fast parallel loading
    
    Args:
        data: Dict mapping table name to list of row dicts
        sf_config: Snowflake connection configuration
        output_dir: Optional directory for Parquet files (kept after load).
                   If None, uses temp directory and cleans up.
        session: Optional existing Snowpark session to reuse
    """
    import tempfile
    import shutil
    import pyarrow as pa
    import pyarrow.parquet as pq
    
    print_header("Loading to Snowflake (Bulk Method)")
    
    # Reuse existing session or create new one
    close_session = False
    if session is None:
        close_session = True
        try:
            from snowflake.snowpark import Session
        except ImportError:
            print("ERROR: snowflake-snowpark-python not installed.")
            sys.exit(1)
        
        connection_name = sf_config.connection_name or os.environ.get("SNOWFLAKE_CONNECTION_NAME")
        if connection_name:
            print(f"  Using named connection: {connection_name}")
            session = Session.builder.configs({"connection_name": connection_name}).create()
        else:
            connection_params = {
                "account": sf_config.account,
                "user": sf_config.user,
                "password": sf_config.password,
                "role": sf_config.role,
                "warehouse": sf_config.warehouse,
            }
            session = Session.builder.configs(connection_params).create()
    else:
        print("  Using existing session")
    
    # Setup database and schema (CREATE IF NOT EXISTS)
    print(f"  Target: {sf_config.database}.{sf_config.schema}")
    session.sql(f"CREATE DATABASE IF NOT EXISTS {sf_config.database}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {sf_config.database}.{sf_config.schema}").collect()
    session.sql(f"USE SCHEMA {sf_config.database}.{sf_config.schema}").collect()
    
    # Create stage and file format
    stage_name = "BULK_LOAD_STAGE"
    file_format_name = "PARQUET_FORMAT"
    session.sql(f"CREATE STAGE IF NOT EXISTS {stage_name}").collect()
    session.sql(f"CREATE FILE FORMAT IF NOT EXISTS {file_format_name} TYPE = PARQUET").collect()
    
    # Table schemas - explicit DDL for each table
    TABLE_SCHEMAS = {
        "CATEGORIES": """
            CREATE OR REPLACE TABLE CATEGORIES (
                CATEGORY_ID VARCHAR(50) PRIMARY KEY,
                NAME VARCHAR(100),
                DISPLAY_ORDER INT
            )""",
        "SUPPLIERS": """
            CREATE OR REPLACE TABLE SUPPLIERS (
                SUPPLIER_ID VARCHAR(50) PRIMARY KEY,
                NAME VARCHAR(200),
                COUNTRY VARCHAR(10),
                RATING FLOAT,
                CREATED_TS TIMESTAMP_NTZ
            )""",
        "HOUSEHOLDS": """
            CREATE OR REPLACE TABLE HOUSEHOLDS (
                HOUSEHOLD_ID VARCHAR(50) PRIMARY KEY,
                ADDRESS_CITY VARCHAR(100),
                ADDRESS_STATE VARCHAR(50),
                ADDRESS_COUNTRY VARCHAR(10),
                CREATED_TS TIMESTAMP_NTZ
            )""",
        "PRODUCTS": """
            CREATE OR REPLACE TABLE PRODUCTS (
                PRODUCT_ID VARCHAR(50) PRIMARY KEY,
                CATEGORY_ID VARCHAR(50),
                NAME VARCHAR(200),
                DESCRIPTION VARCHAR(500),
                BASE_PRICE FLOAT,
                COST FLOAT,
                TAGS VARCHAR(500),
                IS_ACTIVE BOOLEAN,
                CREATED_TS TIMESTAMP_NTZ
            )""",
        "PRODUCT_SUPPLIER": """
            CREATE OR REPLACE TABLE PRODUCT_SUPPLIER (
                PRODUCT_ID VARCHAR(50),
                SUPPLIER_ID VARCHAR(50),
                SUPPLY_COST FLOAT,
                LEAD_TIME_DAYS INT,
                IS_PRIMARY BOOLEAN,
                PRIMARY KEY (PRODUCT_ID, SUPPLIER_ID)
            )""",
        "VISITORS": """
            CREATE OR REPLACE TABLE VISITORS (
                VISITOR_ID VARCHAR(50) PRIMARY KEY,
                DEVICE_TYPE VARCHAR(20),
                BROWSER VARCHAR(50),
                OS VARCHAR(50),
                COUNTRY VARCHAR(10),
                FIRST_SEEN_TS TIMESTAMP_NTZ,
                LAST_SEEN_TS TIMESTAMP_NTZ
            )""",
        "USERS": """
            CREATE OR REPLACE TABLE USERS (
                USER_ID VARCHAR(50) PRIMARY KEY,
                VISITOR_ID VARCHAR(50),
                HOUSEHOLD_ID VARCHAR(50),
                EMAIL VARCHAR(200),
                FIRST_NAME VARCHAR(100),
                LAST_NAME VARCHAR(100),
                PHONE VARCHAR(50),
                LOYALTY_TIER VARCHAR(20),
                LOYALTY_POINTS INT,
                CREATED_TS TIMESTAMP_NTZ,
                UPDATED_TS TIMESTAMP_NTZ
            )""",
        "SESSIONS": """
            CREATE OR REPLACE TABLE SESSIONS (
                SESSION_ID VARCHAR(50) PRIMARY KEY,
                VISITOR_ID VARCHAR(50),
                USER_ID VARCHAR(50),
                STARTED_TS TIMESTAMP_NTZ,
                ENDED_TS TIMESTAMP_NTZ,
                DURATION_SECONDS INT,
                PAGE_VIEWS INT,
                DEVICE_TYPE VARCHAR(20),
                BROWSER VARCHAR(50),
                OS VARCHAR(50),
                COUNTRY VARCHAR(10),
                UTM_SOURCE VARCHAR(50),
                UTM_MEDIUM VARCHAR(50),
                UTM_CAMPAIGN VARCHAR(100),
                IS_CONVERTED BOOLEAN
            )""",
        "EVENTS": """
            CREATE OR REPLACE TABLE EVENTS (
                EVENT_ID VARCHAR(50) PRIMARY KEY,
                SESSION_ID VARCHAR(50),
                VISITOR_ID VARCHAR(50),
                USER_ID VARCHAR(50),
                EVENT_TYPE VARCHAR(50),
                EVENT_TS TIMESTAMP_NTZ,
                PAGE_URL VARCHAR(500),
                PRODUCT_ID VARCHAR(50),
                PRODUCT_QUANTITY INT,
                SEARCH_QUERY VARCHAR(200),
                PROPERTIES VARIANT
            )""",
        "ORDERS": """
            CREATE OR REPLACE TABLE ORDERS (
                ORDER_ID VARCHAR(50) PRIMARY KEY,
                USER_ID VARCHAR(50),
                SESSION_ID VARCHAR(50),
                ORDER_TS TIMESTAMP_NTZ,
                STATUS VARCHAR(20),
                SUBTOTAL FLOAT,
                TAX FLOAT,
                SHIPPING FLOAT,
                TOTAL FLOAT,
                SHIPPING_ADDRESS_CITY VARCHAR(100),
                SHIPPING_ADDRESS_STATE VARCHAR(50),
                SHIPPING_ADDRESS_COUNTRY VARCHAR(10),
                PAYMENT_METHOD VARCHAR(50)
            )""",
        "ORDER_ITEMS": """
            CREATE OR REPLACE TABLE ORDER_ITEMS (
                ORDER_ITEM_ID VARCHAR(50) PRIMARY KEY,
                ORDER_ID VARCHAR(50),
                PRODUCT_ID VARCHAR(50),
                QUANTITY INT,
                UNIT_PRICE FLOAT,
                TOTAL_PRICE FLOAT
            )""",
    }
    
    # Table order (respects foreign keys)
    table_order = [
        "CATEGORIES", "SUPPLIERS", "HOUSEHOLDS", "PRODUCTS", "PRODUCT_SUPPLIER",
        "VISITORS", "USERS", "SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"
    ]
    
    # Use provided output_dir or temp directory
    cleanup_after = output_dir is None
    if output_dir:
        parquet_dir = Path(output_dir)
        parquet_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Parquet files: {parquet_dir}")
    else:
        parquet_dir = Path(tempfile.mkdtemp(prefix="sf_bulk_"))
    
    try:
        for table_name in table_order:
            rows = data.get(table_name, [])
            if not rows:
                continue
            
            print(f"  Loading {table_name} ({len(rows):,} rows)...")
            
            # Write Parquet file
            parquet_path = parquet_dir / f"{table_name.lower()}.parquet"
            table = pa.Table.from_pylist(rows)
            pq.write_table(table, parquet_path, compression="snappy")
            
            # Upload to stage
            stage_path = f"@{stage_name}/{table_name.lower()}/"
            session.file.put(str(parquet_path), stage_path, auto_compress=False, overwrite=True)
            
            # Create table with explicit schema
            session.sql(TABLE_SCHEMAS[table_name]).collect()
            
            # COPY INTO using named file format
            session.sql(f"""
                COPY INTO {table_name}
                FROM {stage_path}
                FILE_FORMAT = {file_format_name}
                MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            """).collect()
            
            # Cleanup stage files
            session.sql(f"REMOVE {stage_path}").collect()
            
            print(f"    ✓ {table_name} loaded")
    
    finally:
        # Only cleanup if using temp directory
        if cleanup_after:
            shutil.rmtree(parquet_dir, ignore_errors=True)
        else:
            print(f"  Parquet files retained at: {parquet_dir}")
    
    # Only close session if we created it
    if close_session:
        session.close()
    print("\n  All tables loaded successfully (bulk method)!")


def run_incremental_mode(args):
    """Run incremental data generation mode."""
    from snowflake.snowpark import Session
    from loaders import IncrementalLoader, IncrementalConfig
    
    print_header("INCREMENTAL DATA GENERATION")
    
    # Connect to Snowflake
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        print(f"  Using named connection: {connection_name}")
        session = Session.builder.configs({"connection_name": connection_name}).create()
    else:
        print("ERROR: SNOWFLAKE_CONNECTION_NAME required for incremental mode")
        sys.exit(1)
    
    sf_config = SnowflakeConfig.from_env()
    session.sql(f"USE SCHEMA {sf_config.database}.{sf_config.schema}").collect()
    
    # Create loader
    incr_config = IncrementalConfig(
        new_sessions_per_batch=args.batch_sessions,
        new_orders_per_batch=args.batch_orders,
    )
    
    loader = IncrementalLoader(session, incr_config, schema=sf_config.schema)
    
    if args.continuous:
        # Continuous mode
        loader.run_continuous(
            interval_seconds=args.interval,
            max_batches=args.max_batches,
        )
    else:
        # Single batch
        stats = loader.generate_batch()
        print("\n  Batch Results:")
        for table, count in stats.items():
            print(f"    {table}: {count:,} rows")
    
    session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate clickstream data for Feature Store Guide",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initial load (small scale)
  python main.py --scale 0.01 --output snowflake
  
  # Bulk load (large scale, scalable method)
  python main.py --scale 1.0 --output snowflake --method bulk
  
  # Incremental batch (single batch)
  python main.py --incremental
  
  # Continuous incremental (for DT demo)
  python main.py --incremental --continuous --interval 60 --max-batches 10
        """
    )
    
    # Mode selection
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental mode: append new data to existing tables"
    )
    
    # Initial load options
    parser.add_argument(
        "--scale", 
        type=float, 
        default=SCALE_FACTOR,
        help=f"Scale factor (default: {SCALE_FACTOR}). 0.01=1K users, 0.1=10K users, 1.0=100K users"
    )
    parser.add_argument(
        "--output",
        choices=["csv", "snowflake", "both", "parquet"],
        default="csv",
        help="Output destination (default: csv)"
    )
    parser.add_argument(
        "--method",
        choices=["simple", "bulk"],
        default="simple",
        help="Loading method: 'simple' (in-memory), 'bulk' (Parquet+COPY INTO, scalable)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory for CSV/Parquet files (default: ./output)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2022-01-01",
        help="Start date for data (default: 2022-01-01)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-12-31",
        help="End date for data (default: 2024-12-31)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    
    # Incremental mode options
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run incremental mode continuously"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between batches in continuous mode (default: 60)"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum batches in continuous mode (default: unlimited)"
    )
    parser.add_argument(
        "--batch-sessions",
        type=int,
        default=50,
        help="Sessions per incremental batch (default: 50)"
    )
    parser.add_argument(
        "--batch-orders",
        type=int,
        default=5,
        help="Orders per incremental batch (default: 5)"
    )
    
    # Snowflake target options
    parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Target database name (default: from SNOWFLAKE_DATABASE env or FEATURE_STORE_GUIDE)"
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="Target schema name (default: from SNOWFLAKE_SCHEMA env or CLICKSTREAM_RAW)"
    )
    
    args = parser.parse_args()
    
    # Handle incremental mode
    if args.incremental:
        run_incremental_mode(args)
        return
    
    # Create configuration
    config = DataConfig(
        scale=args.scale,
        start_date=datetime.strptime(args.start_date, "%Y-%m-%d"),
        end_date=datetime.strptime(args.end_date, "%Y-%m-%d"),
    )
    
    # Print summary
    print_summary(config)
    
    # Warn about scalability for large datasets
    if args.scale >= 0.5 and args.method == "simple":
        print("⚠️  WARNING: Scale >= 0.5 with 'simple' method may run out of memory!")
        print("    Consider using --method bulk for large datasets.\n")
    
    # Generate data
    data = generate_all_data(config, show_progress=not args.quiet)
    
    # Output
    if args.output in ["csv", "both"]:
        save_to_csv(data, args.output_dir)
    
    if args.output == "parquet":
        save_to_parquet(data, args.output_dir)
    
    if args.output in ["snowflake", "both"]:
        # Check for named connection first
        connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
        if not connection_name:
            sf_config = SnowflakeConfig.from_env()
            if not sf_config.account or not sf_config.user:
                print("ERROR: Snowflake credentials not set.")
                print("Option 1: Set SNOWFLAKE_CONNECTION_NAME to use named connection")
                print("Option 2: Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD")
                sys.exit(1)
        else:
            sf_config = SnowflakeConfig.from_env()
        
        # Override with command-line args if provided
        if args.database:
            sf_config.database = args.database
        if args.schema:
            sf_config.schema = args.schema
        
        # Set output directory for bulk loading based on scale
        if args.method == "bulk":
            bulk_output_dir = Path(__file__).parent.parent / "data" / f"scale_{args.scale}"
            load_to_snowflake_bulk(data, sf_config, output_dir=bulk_output_dir)
        else:
            load_to_snowflake(data, sf_config)
    
    print_header("Generation Complete!")
    print(f"Total rows generated: {sum(len(rows) for rows in data.values()):,}")


if __name__ == "__main__":
    main()

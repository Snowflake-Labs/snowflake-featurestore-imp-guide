#!/usr/bin/env python3
"""
Development Database Subset Tool
================================

Create development database branches from production data using Dynamic Tables.

Usage:
    python deploy.py create --prod-db PROD --dev-db DEV --sample-pct 10
    python deploy.py status --dev-db DEV
    python deploy.py suspend --dev-db DEV
    python deploy.py resume --dev-db DEV
    python deploy.py drop --dev-db DEV
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

from snowflake.snowpark import Session


# =============================================================================
# Configuration: Clickstream table relationships
# =============================================================================

# Dimension tables (copied in full - small reference data)
DIMENSION_TABLES = [
    "CATEGORIES",
    "SUPPLIERS", 
    "PRODUCTS",
    "PRODUCT_SUPPLIER",
    "HOUSEHOLDS",
]

# Cascade starts from VISITORS to include anonymous sessions/events
# VISITOR_SAMPLE → USERS, SESSIONS → EVENTS
# USERS → ORDERS → ORDER_ITEMS

# Tables that cascade from VISITOR_ID sample (the root)
VISITOR_CASCADED_TABLES = {
    # table_name: (filter_column, sample_table)
    "VISITORS": ("VISITOR_ID", "VISITOR_SAMPLE"),
    "SESSIONS": ("VISITOR_ID", "VISITOR_SAMPLE"),
}

# Tables that cascade from USER_ID (derived from sampled visitors)
USER_CASCADED_TABLES = {
    "USERS": ("USER_ID", "USER_SAMPLE"),
    "ORDERS": ("USER_ID", "USER_SAMPLE"),
}

# Tables that cascade from SESSION_ID (derived from sampled visitors)
SESSION_CASCADED_TABLES = {
    "EVENTS": ("SESSION_ID", "SESSION_SAMPLE"),
}

# Tables that cascade from ORDER_ID (derived from sampled users)
ORDER_CASCADED_TABLES = {
    "ORDER_ITEMS": ("ORDER_ID", "ORDER_SAMPLE"),
}


# =============================================================================
# Snowflake Connection
# =============================================================================

def get_session() -> Session:
    """Create Snowpark session from named connection or env vars."""
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        return Session.builder.configs({"connection_name": connection_name}).create()
    
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


# =============================================================================
# Subset Creation
# =============================================================================

def create_subset_database(
    session: Session,
    prod_db: str,
    dev_db: str,
    prod_schema: str,
    sample_pct: float,
    warehouse: str,
    target_lag: str = "1 HOUR",
) -> None:
    """Create development database with filtered subset of production data."""
    
    admin_schema = "_SUBSET_ADMIN"
    
    print(f"\n{'='*60}")
    print(f"Creating Development Database Subset")
    print(f"{'='*60}")
    print(f"  Production: {prod_db}.{prod_schema}")
    print(f"  Development: {dev_db}.{prod_schema}")
    print(f"  Sample: {sample_pct}% of users")
    print(f"  Warehouse: {warehouse}")
    print(f"  Target Lag: {target_lag}")
    print(f"{'='*60}\n")
    
    # Step 1: Create development database and schemas
    print("[1/6] Creating database and schemas...")
    session.sql(f"CREATE DATABASE IF NOT EXISTS {dev_db}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_db}.{prod_schema}").collect()
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_db}.{admin_schema}").collect()
    print(f"  ✓ Created {dev_db}")
    
    # Step 2: Create admin tables
    print("\n[2/6] Creating admin tables...")
    create_admin_tables(session, dev_db, admin_schema, prod_db, prod_schema, sample_pct)
    
    # Step 3: Create sample tables (cascading)
    print("\n[3/6] Creating sample tables...")
    create_sample_tables(session, dev_db, admin_schema, prod_db, prod_schema, sample_pct)
    
    # Step 4: Create dimension table copies (full)
    print("\n[4/6] Creating dimension tables (full copy)...")
    for table in DIMENSION_TABLES:
        create_dimension_table(
            session, prod_db, prod_schema, dev_db, prod_schema, 
            table, warehouse, target_lag
        )
    
    # Step 5: Create cascaded Dynamic Tables (in dependency order)
    print("\n[5/6] Creating filtered Dynamic Tables...")
    
    # Visitor-cascaded tables first (VISITORS, SESSIONS - includes anonymous)
    for table, (filter_col, sample_table) in VISITOR_CASCADED_TABLES.items():
        create_filtered_dynamic_table(
            session, prod_db, prod_schema, dev_db, prod_schema, admin_schema,
            table, filter_col, sample_table, warehouse, target_lag
        )
    
    # User-cascaded tables (USERS, ORDERS - identified users only)
    for table, (filter_col, sample_table) in USER_CASCADED_TABLES.items():
        create_filtered_dynamic_table(
            session, prod_db, prod_schema, dev_db, prod_schema, admin_schema,
            table, filter_col, sample_table, warehouse, target_lag
        )
    
    # Session-cascaded tables (EVENTS - includes anonymous events)
    for table, (filter_col, sample_table) in SESSION_CASCADED_TABLES.items():
        create_filtered_dynamic_table(
            session, prod_db, prod_schema, dev_db, prod_schema, admin_schema,
            table, filter_col, sample_table, warehouse, target_lag
        )
    
    # Order-cascaded tables (ORDER_ITEMS)
    for table, (filter_col, sample_table) in ORDER_CASCADED_TABLES.items():
        create_filtered_dynamic_table(
            session, prod_db, prod_schema, dev_db, prod_schema, admin_schema,
            table, filter_col, sample_table, warehouse, target_lag
        )
    
    # Step 6: Create management stored procedure
    print("\n[6/6] Creating management procedures...")
    create_management_procedures(session, dev_db, admin_schema, prod_schema)
    
    print(f"\n{'='*60}")
    print(f"✅ Development database created successfully!")
    print(f"{'='*60}")
    print(f"\nTo use:")
    print(f"  USE DATABASE {dev_db};")
    print(f"  USE SCHEMA {prod_schema};")
    print(f"\nTo manage Dynamic Tables:")
    print(f"  -- Suspend: CALL {admin_schema}.SP_MANAGE_ALL_DTS('SUSPEND');")
    print(f"  -- Resume:  CALL {admin_schema}.SP_MANAGE_ALL_DTS('RESUME');")


def create_admin_tables(
    session: Session,
    dev_db: str,
    admin_schema: str,
    prod_db: str,
    prod_schema: str,
    sample_pct: float,
) -> None:
    """Create admin configuration and tracking tables."""
    
    # Configuration table
    session.sql(f"""
        CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.SUBSET_CONFIG (
            config_key VARCHAR(100) PRIMARY KEY,
            config_value VARCHAR(1000),
            created_ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()
    
    session.sql(f"""
        INSERT INTO {dev_db}.{admin_schema}.SUBSET_CONFIG (config_key, config_value)
        VALUES 
            ('PROD_DATABASE', '{prod_db}'),
            ('PROD_SCHEMA', '{prod_schema}'),
            ('SAMPLE_PCT', '{sample_pct}'),
            ('CREATED_TS', CURRENT_TIMESTAMP()::VARCHAR)
    """).collect()
    
    # Status tracking table
    session.sql(f"""
        CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.SUBSET_STATUS (
            table_name VARCHAR(255) PRIMARY KEY,
            table_type VARCHAR(50),
            filter_type VARCHAR(50),
            source_table VARCHAR(500),
            created_ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
            last_refresh_ts TIMESTAMP_LTZ,
            row_count NUMBER,
            status VARCHAR(50) DEFAULT 'CREATED'
        )
    """).collect()
    
    print(f"  ✓ Created SUBSET_CONFIG, SUBSET_STATUS")


def create_sample_tables(
    session: Session,
    dev_db: str,
    admin_schema: str,
    prod_db: str,
    prod_schema: str,
    sample_pct: float,
) -> None:
    """Create cascading sample tables for referential integrity.
    
    Cascade starts from VISITORS to include anonymous sessions/events:
    VISITOR_SAMPLE (random) → USER_SAMPLE (identified) → ORDER_SAMPLE
                            → SESSION_SAMPLE → (EVENTS via Dynamic Table)
    """
    
    # 1. VISITOR_SAMPLE: Random sample of visitors (includes anonymous)
    # This is the ROOT of the cascade - captures both anonymous and identified traffic
    print(f"  Creating VISITOR_SAMPLE ({sample_pct}% of visitors)...")
    session.sql(f"""CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.VISITOR_SAMPLE AS
SELECT VISITOR_ID
FROM {prod_db}.{prod_schema}.VISITORS
SAMPLE ({sample_pct})""").collect()
    
    visitor_count = session.sql(f"SELECT COUNT(*) FROM {dev_db}.{admin_schema}.VISITOR_SAMPLE").collect()[0][0]
    print(f"    ✓ VISITOR_SAMPLE: {visitor_count:,} visitors")
    
    # 2. USER_SAMPLE: Users linked to sampled visitors (identified only)
    print(f"  Creating USER_SAMPLE (users linked to sampled visitors)...")
    session.sql(f"""CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.USER_SAMPLE AS
SELECT DISTINCT u.USER_ID
FROM {prod_db}.{prod_schema}.USERS u
INNER JOIN {dev_db}.{admin_schema}.VISITOR_SAMPLE v ON u.VISITOR_ID = v.VISITOR_ID""").collect()
    
    user_count = session.sql(f"SELECT COUNT(*) FROM {dev_db}.{admin_schema}.USER_SAMPLE").collect()[0][0]
    print(f"    ✓ USER_SAMPLE: {user_count:,} users")
    
    # 3. SESSION_SAMPLE: Sessions from sampled visitors (includes anonymous sessions)
    print(f"  Creating SESSION_SAMPLE (from sampled visitors)...")
    session.sql(f"""CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.SESSION_SAMPLE AS
SELECT DISTINCT s.SESSION_ID
FROM {prod_db}.{prod_schema}.SESSIONS s
INNER JOIN {dev_db}.{admin_schema}.VISITOR_SAMPLE v ON s.VISITOR_ID = v.VISITOR_ID""").collect()
    
    session_count = session.sql(f"SELECT COUNT(*) FROM {dev_db}.{admin_schema}.SESSION_SAMPLE").collect()[0][0]
    print(f"    ✓ SESSION_SAMPLE: {session_count:,} sessions")
    
    # 4. ORDER_SAMPLE: Orders from sampled users (requires authenticated user)
    print(f"  Creating ORDER_SAMPLE (from sampled users)...")
    session.sql(f"""CREATE OR REPLACE TABLE {dev_db}.{admin_schema}.ORDER_SAMPLE AS
SELECT DISTINCT o.ORDER_ID
FROM {prod_db}.{prod_schema}.ORDERS o
INNER JOIN {dev_db}.{admin_schema}.USER_SAMPLE u ON o.USER_ID = u.USER_ID""").collect()
    
    order_count = session.sql(f"SELECT COUNT(*) FROM {dev_db}.{admin_schema}.ORDER_SAMPLE").collect()[0][0]
    print(f"    ✓ ORDER_SAMPLE: {order_count:,} orders")


def create_dimension_table(
    session: Session,
    prod_db: str,
    prod_schema: str,
    dev_db: str,
    dev_schema: str,
    table_name: str,
    warehouse: str,
    target_lag: str,
) -> None:
    """Create Dynamic Table for dimension (full copy)."""
    
    # CRITICAL: DDL must NOT have leading newline
    ddl = f"""CREATE OR REPLACE DYNAMIC TABLE {dev_db}.{dev_schema}.{table_name}
TARGET_LAG = '{target_lag}'
WAREHOUSE = {warehouse}
AS
SELECT * FROM {prod_db}.{prod_schema}.{table_name}"""
    
    try:
        session.sql(ddl).collect()
        
        # Track in status
        session.sql(f"""
            INSERT INTO {dev_db}._SUBSET_ADMIN.SUBSET_STATUS 
                (table_name, table_type, filter_type, source_table)
            VALUES 
                ('{table_name}', 'DYNAMIC', 'FULL_COPY', '{prod_db}.{prod_schema}.{table_name}')
        """).collect()
        
        print(f"  ✓ {table_name} (full copy)")
    except Exception as e:
        print(f"  ✗ {table_name}: {str(e)[:80]}")


def create_filtered_dynamic_table(
    session: Session,
    prod_db: str,
    prod_schema: str,
    dev_db: str,
    dev_schema: str,
    admin_schema: str,
    table_name: str,
    filter_column: str,
    sample_table: str,
    warehouse: str,
    target_lag: str,
) -> None:
    """Create Dynamic Table filtered by sample table using INNER JOIN for incremental refresh."""
    
    # Use INNER JOIN (not subquery) to enable incremental refresh
    # CRITICAL: 
    # - DDL must NOT have leading newline
    # - Avoid "sample" as alias (reserved keyword in Snowflake)
    ddl = f"""CREATE OR REPLACE DYNAMIC TABLE {dev_db}.{dev_schema}.{table_name}
TARGET_LAG = '{target_lag}'
WAREHOUSE = {warehouse}
AS
SELECT src.*
FROM {prod_db}.{prod_schema}.{table_name} src
INNER JOIN {dev_db}.{admin_schema}.{sample_table} s ON src.{filter_column} = s.{filter_column}"""
    
    try:
        session.sql(ddl).collect()
        
        # Track in status
        session.sql(f"""
            INSERT INTO {dev_db}.{admin_schema}.SUBSET_STATUS 
                (table_name, table_type, filter_type, source_table)
            VALUES 
                ('{table_name}', 'DYNAMIC', 'FILTERED_{filter_column}', '{prod_db}.{prod_schema}.{table_name}')
        """).collect()
        
        print(f"  ✓ {table_name} (filtered by {filter_column})")
    except Exception as e:
        print(f"  ✗ {table_name}: {str(e)[:80]}")


def create_management_procedures(
    session: Session,
    dev_db: str,
    admin_schema: str,
    data_schema: str,
) -> None:
    """Create stored procedures for managing Dynamic Tables."""
    
    # SP_MANAGE_ALL_DTS: Suspend or resume all Dynamic Tables
    proc_sql = f"""
        CREATE OR REPLACE PROCEDURE {dev_db}.{admin_schema}.SP_MANAGE_ALL_DTS(ACTION VARCHAR)
        RETURNS TABLE (table_name VARCHAR, status VARCHAR, message VARCHAR)
        LANGUAGE PYTHON
        RUNTIME_VERSION = '3.9'
        PACKAGES = ('snowflake-snowpark-python')
        HANDLER = 'manage_dts'
        AS
        $$
def manage_dts(session, action):
    import pandas as pd
    
    action = action.upper()
    if action not in ('SUSPEND', 'RESUME'):
        return pd.DataFrame([{{'table_name': 'ERROR', 'status': 'FAILED', 'message': 'Action must be SUSPEND or RESUME'}}])
    
    results = []
    
    # Get all Dynamic Tables in the data schema
    tables = session.sql('''
        SELECT table_name 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE table_schema = \\'{data_schema}\\' 
          AND table_type = \\'DYNAMIC TABLE\\'
    ''').collect()
    
    for row in tables:
        table_name = row[0]
        try:
            session.sql(f'ALTER DYNAMIC TABLE {data_schema}.{{table_name}} {{action}}').collect()
            results.append({{'table_name': table_name, 'status': 'SUCCESS', 'message': f'{{action}}ED'}})
        except Exception as e:
            results.append({{'table_name': table_name, 'status': 'FAILED', 'message': str(e)[:100]}})
    
    return pd.DataFrame(results)
        $$
    """
    
    try:
        session.sql(proc_sql).collect()
        print(f"  ✓ SP_MANAGE_ALL_DTS")
    except Exception as e:
        print(f"  ✗ SP_MANAGE_ALL_DTS: {str(e)[:80]}")


# =============================================================================
# Status and Management
# =============================================================================

def show_status(session: Session, dev_db: str) -> None:
    """Show status of development database."""
    
    admin_schema = "_SUBSET_ADMIN"
    
    print(f"\n{'='*60}")
    print(f"Development Database Status: {dev_db}")
    print(f"{'='*60}\n")
    
    # Configuration
    print("Configuration:")
    try:
        config = session.sql(f"SELECT * FROM {dev_db}.{admin_schema}.SUBSET_CONFIG").collect()
        for row in config:
            print(f"  {row[0]}: {row[1]}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Sample table counts
    print("\nSample Tables:")
    sample_tables = ["USER_SAMPLE", "VISITOR_SAMPLE", "SESSION_SAMPLE", "ORDER_SAMPLE"]
    for table in sample_tables:
        try:
            count = session.sql(f"SELECT COUNT(*) FROM {dev_db}.{admin_schema}.{table}").collect()[0][0]
            print(f"  {table}: {count:,}")
        except Exception:
            print(f"  {table}: not found")
    
    # Dynamic Table status
    print("\nDynamic Tables:")
    try:
        session.sql(f"USE DATABASE {dev_db}").collect()
        # Check CLICKSTREAM_RAW schema for Dynamic Tables
        dt_status = session.sql("SHOW DYNAMIC TABLES IN SCHEMA CLICKSTREAM_RAW").collect()
        
        # SHOW DYNAMIC TABLES columns:
        # [1]: name, [5]: rows, [15]: scheduling_state
        for row in dt_status:
            name = row[1]
            rows = row[5] if len(row) > 5 and row[5] else 0
            state = row[15] if len(row) > 15 else "N/A"
            print(f"  {name:30} {rows:>10,} rows  {state}")
        
        if not dt_status:
            print("  No Dynamic Tables found")
    except Exception as e:
        print(f"  Error: {e}")


def suspend_resume_all(session: Session, dev_db: str, action: str) -> None:
    """Suspend or resume all Dynamic Tables."""
    
    action = action.upper()
    admin_schema = "_SUBSET_ADMIN"
    
    print(f"\n{action}ING all Dynamic Tables in {dev_db}...\n")
    
    try:
        results = session.sql(f"CALL {dev_db}.{admin_schema}.SP_MANAGE_ALL_DTS('{action}')").collect()
        for row in results:
            status_icon = "✓" if row[1] == "SUCCESS" else "✗"
            print(f"  {status_icon} {row[0]}: {row[2]}")
    except Exception as e:
        print(f"Error: {e}")


def drop_subset_database(session: Session, dev_db: str, confirm: bool = False) -> None:
    """Drop the development database."""
    
    if not confirm:
        print(f"\n⚠️  This will DROP DATABASE {dev_db}")
        print(f"    Run with --confirm to execute")
        return
    
    print(f"\nDropping database {dev_db}...")
    try:
        session.sql(f"DROP DATABASE IF EXISTS {dev_db}").collect()
        print(f"  ✓ Dropped {dev_db}")
    except Exception as e:
        print(f"  ✗ Error: {e}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Development Database Subset Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python deploy.py create --prod-db FEATURE_STORE_GUIDE --dev-db FSG_DEV --sample-pct 10
    python deploy.py status --dev-db FSG_DEV
    python deploy.py suspend --dev-db FSG_DEV
    python deploy.py resume --dev-db FSG_DEV
    python deploy.py drop --dev-db FSG_DEV --confirm
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # create command
    create_parser = subparsers.add_parser("create", help="Create development database")
    create_parser.add_argument("--prod-db", required=True, help="Production database name")
    create_parser.add_argument("--dev-db", required=True, help="Development database name")
    create_parser.add_argument("--prod-schema", default="CLICKSTREAM_RAW", help="Production schema (default: CLICKSTREAM_RAW)")
    create_parser.add_argument("--sample-pct", type=float, default=10, help="Sample percentage (default: 10)")
    create_parser.add_argument("--warehouse", default="COMPUTE_WH", help="Warehouse for DT refresh")
    create_parser.add_argument("--target-lag", default="1 HOUR", help="Dynamic Table target lag")
    
    # status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("--dev-db", required=True, help="Development database name")
    
    # suspend command
    suspend_parser = subparsers.add_parser("suspend", help="Suspend Dynamic Tables")
    suspend_parser.add_argument("--dev-db", required=True, help="Development database name")
    
    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume Dynamic Tables")
    resume_parser.add_argument("--dev-db", required=True, help="Development database name")
    
    # drop command
    drop_parser = subparsers.add_parser("drop", help="Drop development database")
    drop_parser.add_argument("--dev-db", required=True, help="Development database name")
    drop_parser.add_argument("--confirm", action="store_true", help="Confirm database drop")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Get session
    try:
        session = get_session()
        print(f"Connected to Snowflake")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)
    
    try:
        if args.command == "create":
            create_subset_database(
                session,
                args.prod_db,
                args.dev_db,
                args.prod_schema,
                args.sample_pct,
                args.warehouse,
                args.target_lag,
            )
        elif args.command == "status":
            show_status(session, args.dev_db)
        elif args.command == "suspend":
            suspend_resume_all(session, args.dev_db, "SUSPEND")
        elif args.command == "resume":
            suspend_resume_all(session, args.dev_db, "RESUME")
        elif args.command == "drop":
            drop_subset_database(session, args.dev_db, args.confirm)
    finally:
        session.close()


if __name__ == "__main__":
    main()

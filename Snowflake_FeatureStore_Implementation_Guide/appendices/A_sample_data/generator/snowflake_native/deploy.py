"""
Deploy the Snowflake-native incremental data generator.

Usage:
    python deploy.py                    # Deploy and test
    python deploy.py --start           # Deploy and start the task
    python deploy.py --status          # Check status
    python deploy.py --stop            # Stop the task
"""

import argparse
import os
import sys


def get_session():
    from snowflake.snowpark import Session
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        return Session.builder.configs({"connection_name": connection_name}).create()
    raise ValueError("Set SNOWFLAKE_CONNECTION_NAME environment variable")


def deploy_generator(session, database="FEATURE_STORE_GUIDE", 
                    data_schema="CLICKSTREAM_DATA", admin_schema="CLICKSTREAM_ADMIN"):
    """Deploy incremental generator to separate admin schema."""
    print(f"Deploying to {database}.{admin_schema}...")
    
    # Create admin schema
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{admin_schema}").collect()
    session.sql(f"USE SCHEMA {database}.{admin_schema}").collect()
    
    full_data_schema = f"{database}.{data_schema}"
    full_admin_schema = f"{database}.{admin_schema}"
    
    # Create config table
    print("  Creating GENERATION_CONFIG...")
    session.sql(f"""
        CREATE OR REPLACE TABLE GENERATION_CONFIG (
            ID INT PRIMARY KEY DEFAULT 1,
            DATA_SCHEMA VARCHAR(256) DEFAULT '{full_data_schema}',
            SESSIONS_PER_BATCH INT DEFAULT 50,
            EVENTS_PER_SESSION_MIN INT DEFAULT 3,
            EVENTS_PER_SESSION_MAX INT DEFAULT 15,
            ORDERS_PER_BATCH INT DEFAULT 5,
            ITEMS_PER_ORDER_MIN INT DEFAULT 1,
            ITEMS_PER_ORDER_MAX INT DEFAULT 5,
            IS_ENABLED BOOLEAN DEFAULT TRUE,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()
    session.sql("INSERT INTO GENERATION_CONFIG (ID) VALUES (1)").collect()
    
    # Create state table  
    print("  Creating GENERATION_STATE...")
    session.sql("""
        CREATE OR REPLACE TABLE GENERATION_STATE (
            ID INT PRIMARY KEY DEFAULT 1,
            LAST_SESSION_ID INT DEFAULT 0,
            LAST_EVENT_ID INT DEFAULT 0,
            LAST_ORDER_ID INT DEFAULT 0,
            LAST_ORDER_ITEM_ID INT DEFAULT 0,
            LAST_BATCH_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            TOTAL_SESSIONS_GENERATED INT DEFAULT 0,
            TOTAL_EVENTS_GENERATED INT DEFAULT 0,
            TOTAL_ORDERS_GENERATED INT DEFAULT 0,
            BATCHES_RUN INT DEFAULT 0
        )
    """).collect()
    
    # Initialize from existing data
    session.sql(f"""
        INSERT INTO GENERATION_STATE (ID, LAST_SESSION_ID, LAST_EVENT_ID, LAST_ORDER_ID, LAST_ORDER_ITEM_ID)
        SELECT 1,
            COALESCE((SELECT MAX(CAST(REPLACE(SESSION_ID, 'sess_', '') AS INT)) FROM {full_data_schema}.SESSIONS), 0),
            COALESCE((SELECT MAX(CAST(REPLACE(EVENT_ID, 'evt_', '') AS INT)) FROM {full_data_schema}.EVENTS), 0),
            COALESCE((SELECT MAX(CAST(REPLACE(ORDER_ID, 'ord_', '') AS INT)) FROM {full_data_schema}.ORDERS), 0),
            COALESCE((SELECT MAX(COALESCE(TRY_CAST(REPLACE(ORDER_ITEM_ID, 'item_', '') AS INT), TRY_CAST(REPLACE(ORDER_ITEM_ID, 'oi_', '') AS INT))) FROM {full_data_schema}.ORDER_ITEMS), 0)
    """).collect()
    
    # Create log table
    print("  Creating GENERATION_LOG...")
    session.sql("""
        CREATE OR REPLACE TABLE GENERATION_LOG (
            LOG_ID INT AUTOINCREMENT PRIMARY KEY,
            BATCH_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            SESSIONS_GENERATED INT, EVENTS_GENERATED INT,
            ORDERS_GENERATED INT, ORDER_ITEMS_GENERATED INT,
            DURATION_MS INT, STATUS VARCHAR(20), ERROR_MESSAGE VARCHAR(10000)
        )
    """).collect()
    
    print("  Creating stored procedure (from file)...")
    # Read SPROC from separate file
    sproc_file = os.path.join(os.path.dirname(__file__), "sproc_generate_batch.sql")
    if os.path.exists(sproc_file):
        with open(sproc_file, 'r') as f:
            sproc_sql = f.read().replace('{ADMIN_SCHEMA}', full_admin_schema)
        session.sql(sproc_sql).collect()
    else:
        print(f"    WARNING: {sproc_file} not found, skipping SPROC creation")
    
    # Create task
    print("  Creating INCREMENTAL_DATA_TASK...")
    warehouse = session.get_current_warehouse().replace('"', '')
    try:
        session.sql("ALTER TASK IF EXISTS INCREMENTAL_DATA_TASK SUSPEND").collect()
    except: pass
    
    session.sql(f"""
        CREATE OR REPLACE TASK INCREMENTAL_DATA_TASK
            WAREHOUSE = {warehouse}
            SCHEDULE = '1 MINUTE'
            ALLOW_OVERLAPPING_EXECUTION = FALSE
        AS CALL GENERATE_INCREMENTAL_BATCH()
    """).collect()
    
    # Create status view
    session.sql("""
        CREATE OR REPLACE VIEW GENERATION_STATUS AS
        SELECT s.*, c.DATA_SCHEMA, c.SESSIONS_PER_BATCH, c.IS_ENABLED
        FROM GENERATION_STATE s CROSS JOIN GENERATION_CONFIG c
        WHERE s.ID = 1 AND c.ID = 1
    """).collect()
    
    print("✅ Deployment complete!")
    return full_admin_schema


def test_batch(session):
    print("\nRunning test batch...")
    result = session.sql("CALL GENERATE_INCREMENTAL_BATCH()").collect()
    print(f"Result: {result[0][0]}")


def show_status(session):
    print("\nGeneration Status:")
    print(session.sql("SELECT * FROM GENERATION_STATUS").to_pandas().to_string(index=False))
    print("\nRecent batches:")
    print(session.sql("SELECT * FROM GENERATION_LOG ORDER BY BATCH_TS DESC LIMIT 5").to_pandas().to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="FEATURE_STORE_GUIDE")
    parser.add_argument("--data-schema", default="CLICKSTREAM_DATA")
    parser.add_argument("--admin-schema", default="CLICKSTREAM_ADMIN")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    
    session = get_session()
    admin_schema = f"{args.database}.{args.admin_schema}"
    
    try:
        if args.status:
            session.sql(f"USE SCHEMA {admin_schema}").collect()
            show_status(session)
        elif args.stop:
            session.sql(f"USE SCHEMA {admin_schema}").collect()
            session.sql("ALTER TASK INCREMENTAL_DATA_TASK SUSPEND").collect()
            print("✅ Task stopped.")
        elif args.start:
            deploy_generator(session, args.database, args.data_schema, args.admin_schema)
            session.sql("ALTER TASK INCREMENTAL_DATA_TASK RESUME").collect()
            print("✅ Task started!")
        else:
            deploy_generator(session, args.database, args.data_schema, args.admin_schema)
            test_batch(session)
            show_status(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()

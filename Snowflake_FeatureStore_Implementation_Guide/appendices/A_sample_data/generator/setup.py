#!/usr/bin/env python3
"""
Clickstream Data Generator - Unified Setup Script
=================================================

Usage:
    python setup.py                    # Interactive setup
    python setup.py --non-interactive  # Use defaults
    python setup.py --scale 0.1        # 10K users
    python setup.py --start-incremental # Start continuous generation
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DataConfig, SnowflakeConfig, SCALE_FACTOR
from setup_helpers import (
    print_banner, print_section, get_session,
    setup_schemas, run_initial_load, 
    deploy_incremental_generator, start_incremental_task,
    show_summary
)


def main():
    parser = argparse.ArgumentParser(description="Clickstream Data Generator Setup")
    
    parser.add_argument("--database", default="FEATURE_STORE_GUIDE")
    parser.add_argument("--data-schema", default="CLICKSTREAM_RAW")
    parser.add_argument("--admin-schema", default="CLICKSTREAM_ADMIN")
    parser.add_argument("--scale", type=float, default=SCALE_FACTOR)
    parser.add_argument("--start-date", default="2022-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--skip-initial-load", action="store_true")
    parser.add_argument("--start-incremental", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    
    args = parser.parse_args()
    
    print_banner()
    
    print_section("Connecting to Snowflake")
    try:
        session = get_session()
        warehouse = session.get_current_warehouse().replace('"', '')
        print(f"  Connected! Warehouse: {warehouse}")
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        sys.exit(1)
    
    try:
        setup_schemas(session, args.database, args.data_schema, args.admin_schema)
        
        if not args.skip_initial_load:
            config = DataConfig(
                scale=args.scale,
                start_date=datetime.strptime(args.start_date, "%Y-%m-%d"),
                end_date=datetime.strptime(args.end_date, "%Y-%m-%d"),
            )
            sf_config = SnowflakeConfig(database=args.database, schema=args.data_schema)
            run_initial_load(session, config, sf_config)
        
        deploy_incremental_generator(
            session, args.database, args.data_schema, args.admin_schema, warehouse
        )
        
        if args.start_incremental:
            start_incremental_task(session, f"{args.database}.{args.admin_schema}")
        
        show_summary(session, args.database, args.data_schema, args.admin_schema)
        
    finally:
        session.close()


if __name__ == "__main__":
    main()

"""
Clickstream Data Generator - Unified Setup Script
=================================================

This script provides a complete setup experience for the clickstream dataset:

1. Initial Load: Generate and load reference + historical data
2. Incremental Setup: Deploy Snowflake-native continuous data generation
3. Both: Complete setup for Feature Store demonstrations

Usage:
    # Interactive mode (prompts for inputs)
    python setup.py
    
    # Non-interactive with defaults
    python setup.py --non-interactive
    
    # Custom configuration
    python setup.py --scale 0.1 --database MY_DB --start-incremental

Requirements:
    - SNOWFLAKE_CONNECTION_NAME environment variable set, OR
    - SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD environment variables
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import DataConfig, SnowflakeConfig, SCALE_FACTOR


def print_banner():
    """Print welcome banner."""
    print("""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   ███████╗███████╗ █████╗ ████████╗██╗   ██╗██████╗ ███████╗                  ║
║   ██╔════╝██╔════╝██╔══██╗╚══██╔══╝██║   ██║██╔══██╗██╔════╝                  ║
║   █████╗  █████╗  ███████║   ██║   ██║   ██║██████╔╝█████╗                    ║
║   ██╔══╝  ██╔══╝  ██╔══██║   ██║   ██║   ██║██╔══██╗██╔══╝                    ║
║   ██║     ███████╗██║  ██║   ██║   ╚██████╔╝██║  ██║███████╗                  ║
║   ╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝                  ║
║                                                                               ║
║         CLICKSTREAM DATA GENERATOR - Feature Store Implementation Guide      ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
""")


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def get_session():
    """Get Snowflake session."""
    from snowflake.snowpark import Session
    
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        print(f"  Using named connection: {connection_name}")
        return Session.builder.configs({"connection_name": connection_name}).create()
    else:
        sf_config = SnowflakeConfig.from_env()
        if not sf_config.account or not sf_config.user:
            raise ValueError(
                "Snowflake credentials not configured.\n"
                "Set SNOWFLAKE_CONNECTION_NAME or SNOWFLAKE_ACCOUNT/USER/PASSWORD"
            )
        return Session.builder.configs({
            "account": sf_config.account,
            "user": sf_config.user,
            "password": sf_config.password,
            "role": sf_config.role,
            "warehouse": sf_config.warehouse,
        }).create()


def setup_schemas(session, database: str, data_schema: str, admin_schema: str):
    """Create database and schemas."""
    print_section("Setting Up Database & Schemas")
    
    print(f"  Creating database: {database}")
    session.sql(f"CREATE DATABASE IF NOT EXISTS {database}").collect()
    
    print(f"  Creating data schema: {data_schema}")
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{data_schema}").collect()
    
    print(f"  Creating admin schema: {admin_schema}")
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{admin_schema}").collect()
    
    print("  ✓ Schemas created")


def run_initial_load(session, config: DataConfig, sf_config: SnowflakeConfig, method: str):
    """Generate and load initial data."""
    print_section("Initial Data Load")
    
    # Import here to avoid circular imports
    from generators import (
        generate_categories, generate_suppliers, generate_households,
        generate_products, generate_product_supplier,
        generate_visitors, generate_users,
        generate_sessions, generate_events,
        generate_orders, generate_order_items
    )
    
    print(f"  Scale factor: {config.scale}")
    print(f"  Expected users: ~{int(100_000 * config.scale):,}")
    print(f"  Date range: {config.start_date.date()} to {config.end_date.date()}")
    print()
    
    # Generate all data
    print("  Generating dimension tables...")
    categories = generate_categories(config)
    suppliers = generate_suppliers(config)
    households = generate_households(config)
    products = generate_products(config, categories)
    product_supplier = generate_product_supplier(config, products, suppliers)
    
    print("  Generating visitor/user tables...")
    visitors = generate_visitors(config)
    users = generate_users(config, households)
    
    print("  Generating event tables...")
    sessions = generate_sessions(config, visitors, users, products, categories)
    events = generate_events(config, sessions, products, categories)
    
    print("  Generating order tables...")
    orders = generate_orders(config, users, sessions)
    order_items = generate_order_items(config, orders, product_supplier)
    
    data = {
        "CATEGORIES": categories,
        "SUPPLIERS": suppliers,
        "HOUSEHOLDS": households,
        "PRODUCTS": products,
        "PRODUCT_SUPPLIER": product_supplier,
        "VISITORS": visitors,
        "USERS": users,
        "SESSIONS": sessions,
        "EVENTS": events,
        "ORDERS": orders,
        "ORDER_ITEMS": order_items,
    }
    
    total_rows = sum(len(rows) for rows in data.values())
    print(f"\n  Total rows generated: {total_rows:,}")
    
    # Load to Snowflake
    print(f"\n  Loading to Snowflake (method: {method})...")
    session.sql(f"USE SCHEMA {sf_config.database}.{sf_config.schema}").collect()
    
    import pandas as pd
    
    table_order = [
        "CATEGORIES", "SUPPLIERS", "HOUSEHOLDS", "PRODUCTS", "PRODUCT_SUPPLIER",
        "VISITORS", "USERS", "SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"
    ]
    
    for table_name in table_order:
        rows = data.get(table_name, [])
        if not rows:
            continue
        
        print(f"    Loading {table_name} ({len(rows):,} rows)...")
        df = session.create_dataframe(pd.DataFrame(rows))
        df.write.mode("overwrite").save_as_table(table_name)
    
    print("\n  ✓ Initial data loaded successfully")
    return data


def deploy_incremental_generator(session, database: str, data_schema: str, admin_schema: str, warehouse: str):
    """Deploy the Snowflake-native incremental generator."""
    print_section("Deploying Incremental Generator")
    
    full_admin_schema = f"{database}.{admin_schema}"
    full_data_schema = f"{database}.{data_schema}"
    
    session.sql(f"USE SCHEMA {full_admin_schema}").collect()
    
    # 1. Create configuration table
    print("  Creating GENERATION_CONFIG...")
    session.sql("""
        CREATE TABLE IF NOT EXISTS GENERATION_CONFIG (
            ID INT PRIMARY KEY DEFAULT 1,
            DATA_SCHEMA VARCHAR(256),
            SESSIONS_PER_BATCH INT DEFAULT 50,
            EVENTS_PER_SESSION_MIN INT DEFAULT 3,
            EVENTS_PER_SESSION_MAX INT DEFAULT 15,
            ORDERS_PER_BATCH INT DEFAULT 5,
            ITEMS_PER_ORDER_MIN INT DEFAULT 1,
            ITEMS_PER_ORDER_MAX INT DEFAULT 5,
            IS_ENABLED BOOLEAN DEFAULT TRUE,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()
    
    session.sql(f"""
        MERGE INTO GENERATION_CONFIG t
        USING (SELECT 1 AS ID, '{full_data_schema}' AS DATA_SCHEMA) s ON t.ID = s.ID
        WHEN NOT MATCHED THEN INSERT (ID, DATA_SCHEMA) VALUES (s.ID, s.DATA_SCHEMA)
        WHEN MATCHED THEN UPDATE SET DATA_SCHEMA = s.DATA_SCHEMA
    """).collect()
    
    # 2. Create state table
    print("  Creating GENERATION_STATE...")
    session.sql("""
        CREATE TABLE IF NOT EXISTS GENERATION_STATE (
            ID INT PRIMARY KEY DEFAULT 1,
            LAST_SESSION_ID INT DEFAULT 0,
            LAST_EVENT_ID INT DEFAULT 0,
            LAST_ORDER_ID INT DEFAULT 0,
            LAST_ORDER_ITEM_ID INT DEFAULT 0,
            LAST_BATCH_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            TOTAL_SESSIONS_GENERATED INT DEFAULT 0,
            TOTAL_EVENTS_GENERATED INT DEFAULT 0,
            TOTAL_ORDERS_GENERATED INT DEFAULT 0,
            TOTAL_ORDER_ITEMS_GENERATED INT DEFAULT 0,
            BATCHES_RUN INT DEFAULT 0,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()
    
    # Initialize state from existing data
    session.sql(f"""
        MERGE INTO GENERATION_STATE t
        USING (
            SELECT 
                1 AS ID,
                COALESCE((SELECT MAX(CAST(REPLACE(SESSION_ID, 'sess_', '') AS INT)) FROM {full_data_schema}.SESSIONS), 0) AS max_session,
                COALESCE((SELECT MAX(CAST(REPLACE(EVENT_ID, 'evt_', '') AS INT)) FROM {full_data_schema}.EVENTS), 0) AS max_event,
                COALESCE((SELECT MAX(CAST(REPLACE(ORDER_ID, 'ord_', '') AS INT)) FROM {full_data_schema}.ORDERS), 0) AS max_order,
                COALESCE((
                    SELECT MAX(COALESCE(
                        TRY_CAST(REPLACE(ORDER_ITEM_ID, 'item_', '') AS INT),
                        TRY_CAST(REPLACE(ORDER_ITEM_ID, 'oi_', '') AS INT)
                    )) FROM {full_data_schema}.ORDER_ITEMS
                ), 0) AS max_item
        ) s ON t.ID = s.ID
        WHEN NOT MATCHED THEN INSERT (
            ID, LAST_SESSION_ID, LAST_EVENT_ID, LAST_ORDER_ID, LAST_ORDER_ITEM_ID
        ) VALUES (
            s.ID, s.max_session, s.max_event, s.max_order, s.max_item
        )
    """).collect()
    
    # 3. Create log table
    print("  Creating GENERATION_LOG...")
    session.sql("""
        CREATE TABLE IF NOT EXISTS GENERATION_LOG (
            LOG_ID INT AUTOINCREMENT,
            BATCH_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            SESSIONS_GENERATED INT,
            EVENTS_GENERATED INT,
            ORDERS_GENERATED INT,
            ORDER_ITEMS_GENERATED INT,
            DURATION_MS INT,
            STATUS VARCHAR(20),
            ERROR_MESSAGE VARCHAR(10000),
            PRIMARY KEY (LOG_ID)
        )
    """).collect()
    
    # 4. Create the stored procedure
    print("  Creating GENERATE_INCREMENTAL_BATCH procedure...")
    sproc_code = f'''
CREATE OR REPLACE PROCEDURE GENERATE_INCREMENTAL_BATCH()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'pandas')
HANDLER = 'generate_batch'
AS
$$
import random
from datetime import datetime, timedelta
import pandas as pd
from snowflake.snowpark import Session

def generate_batch(session: Session) -> dict:
    start_time = datetime.now()
    admin_schema = "{full_admin_schema}"
    
    try:
        config = session.sql(f"SELECT * FROM {{admin_schema}}.GENERATION_CONFIG WHERE ID = 1").collect()[0]
        if not config['IS_ENABLED']:
            return {{"status": "disabled"}}
        
        data_schema = config['DATA_SCHEMA']
        state = session.sql(f"SELECT * FROM {{admin_schema}}.GENERATION_STATE WHERE ID = 1").collect()[0]
        
        visitors = [r['VISITOR_ID'] for r in session.sql(f"SELECT VISITOR_ID FROM {{data_schema}}.VISITORS").collect()]
        users = [r['USER_ID'] for r in session.sql(f"SELECT USER_ID FROM {{data_schema}}.USERS").collect()]
        products = [r['PRODUCT_ID'] for r in session.sql(f"SELECT PRODUCT_ID FROM {{data_schema}}.PRODUCTS").collect()]
        product_suppliers = [(r['PRODUCT_ID'], r['SUPPLIER_ID']) for r in session.sql(f"SELECT PRODUCT_ID, SUPPLIER_ID FROM {{data_schema}}.PRODUCT_SUPPLIER").collect()]
        
        if not all([visitors, users, products, product_suppliers]):
            return {{"status": "error", "message": "Missing reference data"}}
        
        session_id = state['LAST_SESSION_ID']
        event_id = state['LAST_EVENT_ID']
        order_id = state['LAST_ORDER_ID']
        order_item_id = state['LAST_ORDER_ITEM_ID']
        
        batch_ts = datetime.now()
        batch_start = state['LAST_BATCH_TS'] or (batch_ts - timedelta(hours=1))
        
        new_sessions = []
        new_events = []
        
        for _ in range(config['SESSIONS_PER_BATCH']):
            session_id += 1
            sess_id = f"sess_{{session_id:08d}}"
            visitor_id = random.choice(visitors)
            user_id = random.choice(users) if random.random() < 0.6 else None
            
            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            sess_end = sess_start + timedelta(seconds=duration)
            device_type = random.choice(['mobile', 'desktop', 'tablet'])
            
            num_events = random.randint(config['EVENTS_PER_SESSION_MIN'], config['EVENTS_PER_SESSION_MAX'])
            products_viewed = []
            cart_add_cnt = 0
            cart_value = 0.0
            is_converted = False
            event_time = sess_start
            
            event_types = ['Product Viewed', 'Product Clicked', 'Product Added', 'Cart Viewed', 'Checkout Started', 'Order Completed']
            event_weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]
            landing_url = f"/products/{{random.choice(products)}}"
            exit_url = landing_url
            
            session_events = []
            for i in range(num_events):
                event_id += 1
                evt_id = f"evt_{{event_id:010d}}"
                event_type = random.choices(event_types, weights=event_weights)[0]
                product_id = random.choice(products)
                
                if 'Viewed' in event_type or 'Clicked' in event_type:
                    products_viewed.append(product_id)
                if 'Added' in event_type:
                    cart_add_cnt += 1
                    cart_value += random.uniform(20, 100)
                if event_type == 'Order Completed':
                    is_converted = True
                
                page_url = f"/products/{{product_id}}"
                exit_url = page_url
                
                session_events.append({{
                    'EVENT_ID': evt_id, 'VISITOR_ID': visitor_id, 'USER_ID': user_id,
                    'SESSION_ID': sess_id, 'EVENT_TS': event_time,
                    'EVENT_TYPE': event_type.split()[0], 'EVENT_NAME': event_type,
                    'PRODUCT_ID': product_id if 'Product' in event_type else None,
                    'CATEGORY_ID': f"cat_{{random.randint(1,15):02d}}" if 'Product' in event_type else None,
                    'PAGE_URL': page_url, 'PAGE_TITLE': f'Page {{i}}',
                    'REFERRER_URL': None, 'PROPERTIES': '{{}}',
                    'CONTEXT': f'{{{{"device_type": "{{device_type}}"}}}}',
                    'RECEIVED_TS': event_time + timedelta(milliseconds=random.randint(100, 500)),
                }})
                event_time += timedelta(seconds=random.randint(5, 120))
            
            new_events.extend(session_events)
            new_sessions.append({{
                'SESSION_ID': sess_id, 'VISITOR_ID': visitor_id, 'USER_ID': user_id,
                'SESSION_START_TS': sess_start, 'SESSION_END_TS': sess_end,
                'DURATION_SEC': duration, 'EVENT_CNT': len(session_events),
                'PAGE_VIEW_CNT': sum(1 for e in session_events if 'Viewed' in e['EVENT_NAME']),
                'PRODUCT_VIEW_DCNT': len(set(products_viewed)),
                'CART_ADD_CNT': cart_add_cnt, 'CART_VALUE_SUM': round(cart_value, 2),
                'IS_CONVERTED': is_converted, 'ORDER_VALUE_SUM': round(cart_value * 0.8 if is_converted else 0, 2),
                'DEVICE_TYPE': device_type, 'LANDING_PAGE_URL': landing_url,
                'EXIT_PAGE_URL': exit_url,
                'PRODUCTS_VIEWED': str(list(set(products_viewed))),
                'CATEGORIES_VIEWED': '[]',
            }})
        
        new_orders = []
        new_order_items = []
        
        for _ in range(config['ORDERS_PER_BATCH']):
            order_id += 1
            ord_id = f"ord_{{order_id:08d}}"
            user_id = random.choice(users)
            sess_id = f"sess_{{random.randint(max(1, session_id - config['SESSIONS_PER_BATCH']), session_id):08d}}"
            delta = max(1, (batch_ts - batch_start).total_seconds())
            order_ts = batch_start + timedelta(seconds=random.uniform(0, delta))
            
            num_items = random.randint(config['ITEMS_PER_ORDER_MIN'], config['ITEMS_PER_ORDER_MAX'])
            subtotal = 0.0
            
            for _ in range(num_items):
                order_item_id += 1
                item_id = f"item_{{order_item_id:08d}}"
                product_id, supplier_id = random.choice(product_suppliers)
                qty = random.randint(1, 3)
                unit_price = round(random.uniform(10, 200), 2)
                item_discount = round(unit_price * 0.1, 2) if random.random() < 0.3 else 0.0
                item_total = round(qty * (unit_price - item_discount), 2)
                subtotal += item_total
                
                new_order_items.append({{
                    'ORDER_ITEM_ID': item_id, 'ORDER_ID': ord_id,
                    'PRODUCT_ID': product_id, 'SUPPLIER_ID': supplier_id,
                    'QUANTITY': qty, 'UNIT_PRICE_AMT': unit_price,
                    'DISCOUNT_AMT': item_discount, 'TOTAL_AMT': item_total,
                }})
            
            tax = round(subtotal * 0.08, 2)
            shipping = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
            discount = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0.0
            
            new_orders.append({{
                'ORDER_ID': ord_id, 'USER_ID': user_id, 'SESSION_ID': sess_id,
                'ORDER_TS': order_ts, 'STATUS': random.choice(['pending', 'confirmed', 'shipped']),
                'SUBTOTAL_AMT': round(subtotal, 2), 'TAX_AMT': tax,
                'SHIPPING_AMT': shipping, 'DISCOUNT_AMT': discount,
                'TOTAL_AMT': round(subtotal + tax + shipping - discount, 2),
                'ITEM_CNT': num_items, 'COUPON_CODE': None,
                'PAYMENT_METHOD': random.choice(['credit_card', 'paypal']),
                'SHIPPING_ADDRESS': '{{}}', 'BILLING_ADDRESS': '{{}}',
                'CREATED_TS': order_ts, 'UPDATED_TS': order_ts,
            }})
        
        if new_sessions:
            session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table(f"{{data_schema}}.SESSIONS")
        if new_events:
            session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table(f"{{data_schema}}.EVENTS")
        if new_orders:
            session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table(f"{{data_schema}}.ORDERS")
        if new_order_items:
            session.create_dataframe(pd.DataFrame(new_order_items)).write.mode("append").save_as_table(f"{{data_schema}}.ORDER_ITEMS")
        
        session.sql(f"""
            UPDATE {{admin_schema}}.GENERATION_STATE SET
                LAST_SESSION_ID = {{session_id}}, LAST_EVENT_ID = {{event_id}},
                LAST_ORDER_ID = {{order_id}}, LAST_ORDER_ITEM_ID = {{order_item_id}},
                LAST_BATCH_TS = '{{batch_ts.strftime('%Y-%m-%d %H:%M:%S')}}',
                TOTAL_SESSIONS_GENERATED = TOTAL_SESSIONS_GENERATED + {{len(new_sessions)}},
                TOTAL_EVENTS_GENERATED = TOTAL_EVENTS_GENERATED + {{len(new_events)}},
                TOTAL_ORDERS_GENERATED = TOTAL_ORDERS_GENERATED + {{len(new_orders)}},
                TOTAL_ORDER_ITEMS_GENERATED = TOTAL_ORDER_ITEMS_GENERATED + {{len(new_order_items)}},
                BATCHES_RUN = BATCHES_RUN + 1, UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE ID = 1
        """).collect()
        
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        session.sql(f"""
            INSERT INTO {{admin_schema}}.GENERATION_LOG (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS)
            VALUES ({{len(new_sessions)}}, {{len(new_events)}}, {{len(new_orders)}}, {{len(new_order_items)}}, {{duration_ms}}, 'SUCCESS')
        """).collect()
        
        return {{"status": "success", "sessions": len(new_sessions), "events": len(new_events), "orders": len(new_orders), "order_items": len(new_order_items), "duration_ms": duration_ms}}
    
    except Exception as e:
        session.sql(f"INSERT INTO {{admin_schema}}.GENERATION_LOG (STATUS, ERROR_MESSAGE) VALUES ('ERROR', '{{str(e)[:1000]}}')").collect()
        return {{"status": "error", "message": str(e)}}
$$
'''
    session.sql(sproc_code).collect()
    
    # 5. Create the task
    print("  Creating INCREMENTAL_DATA_TASK...")
    try:
        session.sql("ALTER TASK IF EXISTS INCREMENTAL_DATA_TASK SUSPEND").collect()
    except:
        pass
    
    session.sql(f"""
        CREATE OR REPLACE TASK INCREMENTAL_DATA_TASK
            WAREHOUSE = {warehouse}
            SCHEDULE = '1 MINUTE'
            ALLOW_OVERLAPPING_EXECUTION = FALSE
            COMMENT = 'Generates incremental clickstream data for Feature Store demos'
        AS
            CALL GENERATE_INCREMENTAL_BATCH()
    """).collect()
    
    # 6. Create monitoring view
    print("  Creating monitoring views...")
    session.sql(f"""
        CREATE OR REPLACE VIEW GENERATION_STATUS AS
        SELECT 
            s.*,
            c.DATA_SCHEMA,
            c.SESSIONS_PER_BATCH,
            c.ORDERS_PER_BATCH,
            c.IS_ENABLED,
            CASE WHEN c.IS_ENABLED THEN 'ENABLED' ELSE 'DISABLED' END AS STATUS
        FROM GENERATION_STATE s
        CROSS JOIN GENERATION_CONFIG c
        WHERE s.ID = 1 AND c.ID = 1
    """).collect()
    
    print("  ✓ Incremental generator deployed")


def start_incremental_task(session, admin_schema: str):
    """Start the incremental generation task."""
    print("\n  Starting incremental generation task...")
    session.sql(f"USE SCHEMA {admin_schema}").collect()
    session.sql("ALTER TASK INCREMENTAL_DATA_TASK RESUME").collect()
    print("  ✓ Task started (runs every minute)")


def show_summary(session, database: str, data_schema: str, admin_schema: str):
    """Show setup summary."""
    print_section("Setup Complete!")
    
    full_data_schema = f"{database}.{data_schema}"
    full_admin_schema = f"{database}.{admin_schema}"
    
    # Get counts
    session.sql(f"USE SCHEMA {full_data_schema}").collect()
    counts = session.sql("""
        SELECT 'Sessions' AS TBL, COUNT(*) AS CNT FROM SESSIONS
        UNION ALL SELECT 'Events', COUNT(*) FROM EVENTS
        UNION ALL SELECT 'Orders', COUNT(*) FROM ORDERS
        UNION ALL SELECT 'Users', COUNT(*) FROM USERS
    """).collect()
    
    print(f"""
  Database:     {database}
  Data Schema:  {data_schema} (contains data tables)
  Admin Schema: {admin_schema} (contains generator config/state/task)
  
  Data Summary:
""")
    for row in counts:
        print(f"    {row['TBL']}: {row['CNT']:,}")
    
    print(f"""
  Next Steps:
  -----------
  
  1. Start continuous data generation:
     
     ALTER TASK {full_admin_schema}.INCREMENTAL_DATA_TASK RESUME;
  
  2. Monitor generation:
     
     SELECT * FROM {full_admin_schema}.GENERATION_STATUS;
     SELECT * FROM {full_admin_schema}.GENERATION_LOG ORDER BY BATCH_TS DESC LIMIT 10;
  
  3. Stop generation:
     
     ALTER TASK {full_admin_schema}.INCREMENTAL_DATA_TASK SUSPEND;
  
  4. Adjust batch sizes:
     
     UPDATE {full_admin_schema}.GENERATION_CONFIG SET SESSIONS_PER_BATCH = 100;
""")


def main():
    parser = argparse.ArgumentParser(
        description="Clickstream Data Generator - Unified Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup.py                           # Interactive mode
  python setup.py --non-interactive         # Use defaults
  python setup.py --scale 0.1               # 10K users
  python setup.py --database MY_DB          # Custom database
  python setup.py --start-incremental       # Start continuous generation
        """
    )
    
    # Configuration
    parser.add_argument("--database", default="FEATURE_STORE_GUIDE",
                       help="Target database name (default: FEATURE_STORE_GUIDE)")
    parser.add_argument("--data-schema", default="CLICKSTREAM_RAW",
                       help="Schema for data tables (default: CLICKSTREAM_RAW)")
    parser.add_argument("--admin-schema", default="CLICKSTREAM_ADMIN",
                       help="Schema for generator config (default: CLICKSTREAM_ADMIN)")
    parser.add_argument("--scale", type=float, default=SCALE_FACTOR,
                       help=f"Scale factor (default: {SCALE_FACTOR}). 0.01=1K, 0.1=10K, 1.0=100K users")
    parser.add_argument("--start-date", default="2022-01-01",
                       help="Start date for historical data (default: 2022-01-01)")
    parser.add_argument("--end-date", default="2024-12-31",
                       help="End date for historical data (default: 2024-12-31)")
    
    # Actions
    parser.add_argument("--skip-initial-load", action="store_true",
                       help="Skip initial data load (only deploy incremental generator)")
    parser.add_argument("--start-incremental", action="store_true",
                       help="Start incremental task after setup")
    parser.add_argument("--non-interactive", action="store_true",
                       help="Run without prompts")
    
    args = parser.parse_args()
    
    print_banner()
    
    # Validate connection
    print_section("Connecting to Snowflake")
    try:
        session = get_session()
        warehouse = session.get_current_warehouse().replace('"', '')
        print(f"  Connected! Warehouse: {warehouse}")
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        sys.exit(1)
    
    try:
        # Setup schemas
        setup_schemas(session, args.database, args.data_schema, args.admin_schema)
        
        # Initial load
        if not args.skip_initial_load:
            config = DataConfig(
                scale=args.scale,
                start_date=datetime.strptime(args.start_date, "%Y-%m-%d"),
                end_date=datetime.strptime(args.end_date, "%Y-%m-%d"),
            )
            sf_config = SnowflakeConfig(
                database=args.database,
                schema=args.data_schema,
            )
            run_initial_load(session, config, sf_config, "simple")
        
        # Deploy incremental generator
        deploy_incremental_generator(
            session, 
            args.database, 
            args.data_schema, 
            args.admin_schema,
            warehouse
        )
        
        # Start task if requested
        if args.start_incremental:
            start_incremental_task(session, f"{args.database}.{args.admin_schema}")
        
        # Show summary
        show_summary(session, args.database, args.data_schema, args.admin_schema)
        
    finally:
        session.close()


if __name__ == "__main__":
    main()

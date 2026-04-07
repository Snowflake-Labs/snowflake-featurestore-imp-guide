-- ============================================================================
-- SNOWFLAKE-NATIVE INCREMENTAL DATA GENERATOR
-- ============================================================================
-- This script deploys the stored procedures, configuration tables, and tasks
-- for continuous incremental data generation inside Snowflake.
--
-- Run this script after the initial data load to enable incremental updates.
--
-- Usage:
--   1. Run this script: snowsql -f deploy_incremental_generator.sql
--   2. Resume the task: ALTER TASK INCREMENTAL_DATA_TASK RESUME;
--   3. Monitor: SELECT * FROM GENERATION_LOG ORDER BY BATCH_TS DESC LIMIT 10;
-- ============================================================================

USE SCHEMA FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN;

-- ============================================================================
-- CONFIGURATION TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS GENERATION_CONFIG (
    ID INT PRIMARY KEY DEFAULT 1,
    -- Batch sizes
    SESSIONS_PER_BATCH INT DEFAULT 50,
    EVENTS_PER_SESSION_MIN INT DEFAULT 3,
    EVENTS_PER_SESSION_MAX INT DEFAULT 15,
    ORDERS_PER_BATCH INT DEFAULT 5,
    ITEMS_PER_ORDER_MIN INT DEFAULT 1,
    ITEMS_PER_ORDER_MAX INT DEFAULT 5,
    -- Control
    IS_ENABLED BOOLEAN DEFAULT TRUE,
    -- Timestamps
    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Insert default config if not exists
MERGE INTO GENERATION_CONFIG t
USING (SELECT 1 AS ID) s ON t.ID = s.ID
WHEN NOT MATCHED THEN INSERT (ID) VALUES (1);

-- ============================================================================
-- STATE TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS GENERATION_STATE (
    ID INT PRIMARY KEY DEFAULT 1,
    -- ID counters (continue from where initial load left off)
    LAST_SESSION_ID INT DEFAULT 0,
    LAST_EVENT_ID INT DEFAULT 0,
    LAST_ORDER_ID INT DEFAULT 0,
    LAST_ORDER_ITEM_ID INT DEFAULT 0,
    -- Timestamps
    LAST_BATCH_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    -- Statistics
    TOTAL_SESSIONS_GENERATED INT DEFAULT 0,
    TOTAL_EVENTS_GENERATED INT DEFAULT 0,
    TOTAL_ORDERS_GENERATED INT DEFAULT 0,
    TOTAL_ORDER_ITEMS_GENERATED INT DEFAULT 0,
    BATCHES_RUN INT DEFAULT 0,
    -- Metadata
    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Initialize state from existing data if not already set
MERGE INTO GENERATION_STATE t
USING (
    SELECT 
        1 AS ID,
        COALESCE((SELECT MAX(CAST(REPLACE(SESSION_ID, 'sess_', '') AS INT)) FROM SESSIONS), 0) AS max_session,
        COALESCE((SELECT MAX(CAST(REPLACE(EVENT_ID, 'evt_', '') AS INT)) FROM EVENTS), 0) AS max_event,
        COALESCE((SELECT MAX(CAST(REPLACE(ORDER_ID, 'ord_', '') AS INT)) FROM ORDERS), 0) AS max_order,
        COALESCE((SELECT MAX(CAST(REPLACE(ORDER_ITEM_ID, 'oi_', '') AS INT)) FROM ORDER_ITEMS), 0) AS max_item
) s ON t.ID = s.ID
WHEN NOT MATCHED THEN INSERT (
    ID, LAST_SESSION_ID, LAST_EVENT_ID, LAST_ORDER_ID, LAST_ORDER_ITEM_ID
) VALUES (
    s.ID, s.max_session, s.max_event, s.max_order, s.max_item
);

-- ============================================================================
-- LOGGING TABLE
-- ============================================================================
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
);

-- ============================================================================
-- MAIN STORED PROCEDURE: GENERATE_INCREMENTAL_BATCH
-- ============================================================================
CREATE OR REPLACE PROCEDURE GENERATE_INCREMENTAL_BATCH()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'generate_batch'
AS
$$
import random
from datetime import datetime, timedelta
from snowflake.snowpark import Session

def generate_batch(session: Session) -> dict:
    """
    Generate a batch of incremental data (sessions, events, orders, order_items).
    
    Maintains referential integrity by:
    1. Reading existing reference data (visitors, users, products, product_suppliers)
    2. Generating new sessions referencing existing visitors/users
    3. Generating events for the new sessions
    4. Generating orders referencing existing users
    5. Generating order_items for the new orders
    
    All inserts happen in a single transaction.
    """
    start_time = datetime.now()
    
    try:
        # Check if enabled
        config = session.sql("SELECT * FROM GENERATION_CONFIG WHERE ID = 1").collect()[0]
        if not config['IS_ENABLED']:
            return {"status": "disabled", "message": "Generation is disabled"}
        
        # Load state
        state = session.sql("SELECT * FROM GENERATION_STATE WHERE ID = 1").collect()[0]
        
        # Load reference data
        visitors = [r['VISITOR_ID'] for r in session.sql("SELECT VISITOR_ID FROM VISITORS").collect()]
        users = [r['USER_ID'] for r in session.sql("SELECT USER_ID FROM USERS").collect()]
        products = [r['PRODUCT_ID'] for r in session.sql("SELECT PRODUCT_ID FROM PRODUCTS").collect()]
        product_suppliers = [
            (r['PRODUCT_ID'], r['SUPPLIER_ID']) 
            for r in session.sql("SELECT PRODUCT_ID, SUPPLIER_ID FROM PRODUCT_SUPPLIER").collect()
        ]
        
        if not visitors or not users or not products or not product_suppliers:
            return {"status": "error", "message": "Missing reference data"}
        
        # Initialize counters
        session_id = state['LAST_SESSION_ID']
        event_id = state['LAST_EVENT_ID']
        order_id = state['LAST_ORDER_ID']
        order_item_id = state['LAST_ORDER_ITEM_ID']
        
        batch_ts = datetime.now()
        batch_start = state['LAST_BATCH_TS'] or (batch_ts - timedelta(hours=1))
        
        # Generate sessions and events
        new_sessions = []
        new_events = []
        
        for _ in range(config['SESSIONS_PER_BATCH']):
            session_id += 1
            sess_id = f"sess_{session_id:08d}"
            
            visitor_id = random.choice(visitors)
            user_id = random.choice(users) if random.random() < 0.6 else None
            
            # Session timing
            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            sess_end = sess_start + timedelta(seconds=duration)
            
            device_type = random.choice(['mobile', 'desktop', 'tablet'])
            
            # Generate events for this session
            num_events = random.randint(config['EVENTS_PER_SESSION_MIN'], config['EVENTS_PER_SESSION_MAX'])
            products_viewed = []
            categories_viewed = []
            cart_add_cnt = 0
            cart_value = 0.0
            is_converted = False
            order_value = 0.0
            event_time = sess_start
            
            event_types = ['Product Viewed', 'Product Clicked', 'Product Added', 'Cart Viewed', 'Checkout Started', 'Order Completed']
            event_weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]
            
            landing_url = f"/products/{random.choice(products)}"
            exit_url = landing_url
            
            session_events = []
            for i in range(num_events):
                event_id += 1
                evt_id = f"evt_{event_id:010d}"
                
                event_type = random.choices(event_types, weights=event_weights)[0]
                product_id = random.choice(products)
                category_id = f"cat_{random.randint(1, 15):02d}"
                
                if 'Viewed' in event_type or 'Clicked' in event_type:
                    products_viewed.append(product_id)
                    categories_viewed.append(category_id)
                
                if 'Added' in event_type:
                    cart_add_cnt += 1
                    cart_value += random.uniform(20, 100)
                
                if event_type == 'Order Completed':
                    is_converted = True
                    order_value = cart_value * 0.8
                
                page_url = f"/products/{product_id}" if product_id else f"/page_{i}"
                exit_url = page_url
                
                session_events.append({
                    'EVENT_ID': evt_id,
                    'VISITOR_ID': visitor_id,
                    'USER_ID': user_id,
                    'SESSION_ID': sess_id,
                    'EVENT_TS': event_time,
                    'EVENT_TYPE': event_type.split()[0],
                    'EVENT_NAME': event_type,
                    'PRODUCT_ID': product_id if 'Product' in event_type else None,
                    'CATEGORY_ID': category_id if 'Product' in event_type else None,
                    'PAGE_URL': page_url,
                    'PAGE_TITLE': f'Page {i}',
                    'REFERRER_URL': exit_url if i > 0 else None,
                    'PROPERTIES': '{}',
                    'CONTEXT': f'{{"device_type": "{device_type}"}}',
                    'RECEIVED_TS': event_time + timedelta(milliseconds=random.randint(100, 500)),
                })
                
                event_time += timedelta(seconds=random.randint(5, 120))
            
            new_events.extend(session_events)
            
            new_sessions.append({
                'SESSION_ID': sess_id,
                'VISITOR_ID': visitor_id,
                'USER_ID': user_id,
                'SESSION_START_TS': sess_start,
                'SESSION_END_TS': sess_end,
                'DURATION_SEC': duration,
                'EVENT_CNT': len(session_events),
                'PAGE_VIEW_CNT': sum(1 for e in session_events if 'Viewed' in e['EVENT_NAME']),
                'PRODUCT_VIEW_DCNT': len(set(products_viewed)),
                'CART_ADD_CNT': cart_add_cnt,
                'CART_VALUE_SUM': round(cart_value, 2),
                'IS_CONVERTED': is_converted,
                'ORDER_VALUE_SUM': round(order_value, 2),
                'DEVICE_TYPE': device_type,
                'LANDING_PAGE_URL': landing_url,
                'EXIT_PAGE_URL': exit_url,
                'PRODUCTS_VIEWED': str(list(set(products_viewed))),
                'CATEGORIES_VIEWED': str(list(set(categories_viewed))),
            })
        
        # Generate orders and order_items
        new_orders = []
        new_order_items = []
        
        for _ in range(config['ORDERS_PER_BATCH']):
            order_id += 1
            ord_id = f"ord_{order_id:08d}"
            
            user_id = random.choice(users)
            # Link to a recent session
            sess_id = f"sess_{random.randint(max(1, session_id - config['SESSIONS_PER_BATCH']), session_id):08d}"
            
            delta = max(1, (batch_ts - batch_start).total_seconds())
            order_ts = batch_start + timedelta(seconds=random.uniform(0, delta))
            
            # Generate items
            num_items = random.randint(config['ITEMS_PER_ORDER_MIN'], config['ITEMS_PER_ORDER_MAX'])
            subtotal = 0.0
            
            for _ in range(num_items):
                order_item_id += 1
                item_id = f"oi_{order_item_id:010d}"
                
                product_id, supplier_id = random.choice(product_suppliers)
                qty = random.randint(1, 3)
                unit_price = round(random.uniform(10, 200), 2)
                item_discount = round(unit_price * random.uniform(0, 0.2), 2) if random.random() < 0.3 else 0.0
                item_total = round(qty * (unit_price - item_discount), 2)
                subtotal += item_total
                
                new_order_items.append({
                    'ORDER_ITEM_ID': item_id,
                    'ORDER_ID': ord_id,
                    'PRODUCT_ID': product_id,
                    'SUPPLIER_ID': supplier_id,
                    'QUANTITY': qty,
                    'UNIT_PRICE_AMT': unit_price,
                    'DISCOUNT_AMT': item_discount,
                    'TOTAL_AMT': item_total,
                })
            
            tax_amt = round(subtotal * 0.08, 2)
            shipping_amt = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
            discount_amt = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0.0
            total_amt = round(subtotal + tax_amt + shipping_amt - discount_amt, 2)
            
            new_orders.append({
                'ORDER_ID': ord_id,
                'USER_ID': user_id,
                'SESSION_ID': sess_id,
                'ORDER_TS': order_ts,
                'STATUS': random.choice(['pending', 'confirmed', 'shipped', 'delivered']),
                'SUBTOTAL_AMT': round(subtotal, 2),
                'TAX_AMT': tax_amt,
                'SHIPPING_AMT': shipping_amt,
                'DISCOUNT_AMT': discount_amt,
                'TOTAL_AMT': total_amt,
                'ITEM_CNT': num_items,
                'COUPON_CODE': f"SAVE{random.randint(10, 50)}" if discount_amt > 0 else None,
                'PAYMENT_METHOD': random.choice(['credit_card', 'paypal', 'apple_pay']),
                'SHIPPING_ADDRESS': '{"city": "San Francisco", "state": "CA"}',
                'BILLING_ADDRESS': '{"city": "San Francisco", "state": "CA"}',
                'CREATED_TS': order_ts,
                'UPDATED_TS': order_ts,
            })
        
        # Insert data (all in same transaction)
        import pandas as pd
        
        if new_sessions:
            session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table("SESSIONS")
        
        if new_events:
            session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table("EVENTS")
        
        if new_orders:
            session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table("ORDERS")
        
        if new_order_items:
            session.create_dataframe(pd.DataFrame(new_order_items)).write.mode("append").save_as_table("ORDER_ITEMS")
        
        # Update state
        session.sql(f"""
            UPDATE GENERATION_STATE SET
                LAST_SESSION_ID = {session_id},
                LAST_EVENT_ID = {event_id},
                LAST_ORDER_ID = {order_id},
                LAST_ORDER_ITEM_ID = {order_item_id},
                LAST_BATCH_TS = '{batch_ts.strftime('%Y-%m-%d %H:%M:%S')}',
                TOTAL_SESSIONS_GENERATED = TOTAL_SESSIONS_GENERATED + {len(new_sessions)},
                TOTAL_EVENTS_GENERATED = TOTAL_EVENTS_GENERATED + {len(new_events)},
                TOTAL_ORDERS_GENERATED = TOTAL_ORDERS_GENERATED + {len(new_orders)},
                TOTAL_ORDER_ITEMS_GENERATED = TOTAL_ORDER_ITEMS_GENERATED + {len(new_order_items)},
                BATCHES_RUN = BATCHES_RUN + 1,
                UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE ID = 1
        """).collect()
        
        # Log success
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        session.sql(f"""
            INSERT INTO GENERATION_LOG (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS)
            VALUES ({len(new_sessions)}, {len(new_events)}, {len(new_orders)}, {len(new_order_items)}, {duration_ms}, 'SUCCESS')
        """).collect()
        
        return {
            "status": "success",
            "sessions": len(new_sessions),
            "events": len(new_events),
            "orders": len(new_orders),
            "order_items": len(new_order_items),
            "duration_ms": duration_ms
        }
        
    except Exception as e:
        # Log error
        error_msg = str(e).replace("'", "''")[:10000]
        session.sql(f"""
            INSERT INTO GENERATION_LOG (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS, ERROR_MESSAGE)
            VALUES (0, 0, 0, 0, 0, 'ERROR', '{error_msg}')
        """).collect()
        
        return {"status": "error", "message": str(e)}
$$;

-- ============================================================================
-- TASK: INCREMENTAL_DATA_TASK
-- ============================================================================
-- Note: Task is created SUSPENDED - resume it to start generation
CREATE OR REPLACE TASK INCREMENTAL_DATA_TASK
    WAREHOUSE = COMPUTE_WH  -- Adjust to your warehouse
    SCHEDULE = '1 MINUTE'   -- Adjust frequency (minimum: '10 SECOND')
    ALLOW_OVERLAPPING_EXECUTION = FALSE
    COMMENT = 'Generates incremental clickstream data for Feature Store demos'
AS
    CALL GENERATE_INCREMENTAL_BATCH();

-- ============================================================================
-- HELPER VIEWS FOR MONITORING
-- ============================================================================
CREATE OR REPLACE VIEW GENERATION_STATUS AS
SELECT
    s.LAST_SESSION_ID,
    s.LAST_EVENT_ID,
    s.LAST_ORDER_ID,
    s.BATCHES_RUN,
    s.TOTAL_SESSIONS_GENERATED,
    s.TOTAL_EVENTS_GENERATED,
    s.TOTAL_ORDERS_GENERATED,
    s.LAST_BATCH_TS,
    c.SESSIONS_PER_BATCH,
    c.ORDERS_PER_BATCH,
    c.IS_ENABLED,
    CASE WHEN c.IS_ENABLED THEN 'ENABLED' ELSE 'DISABLED' END AS STATUS
FROM GENERATION_STATE s
CROSS JOIN GENERATION_CONFIG c
WHERE s.ID = 1 AND c.ID = 1;

CREATE OR REPLACE VIEW RECENT_GENERATION_LOG AS
SELECT
    LOG_ID,
    BATCH_TS,
    SESSIONS_GENERATED,
    EVENTS_GENERATED,
    ORDERS_GENERATED,
    ORDER_ITEMS_GENERATED,
    DURATION_MS,
    STATUS,
    CASE WHEN ERROR_MESSAGE IS NOT NULL THEN LEFT(ERROR_MESSAGE, 100) ELSE NULL END AS ERROR_PREVIEW
FROM GENERATION_LOG
ORDER BY BATCH_TS DESC
LIMIT 100;

-- ============================================================================
-- GRANT PERMISSIONS (adjust as needed)
-- ============================================================================
-- GRANT EXECUTE ON PROCEDURE GENERATE_INCREMENTAL_BATCH() TO ROLE <your_role>;
-- GRANT OPERATE ON TASK INCREMENTAL_DATA_TASK TO ROLE <your_role>;

-- ============================================================================
-- SUMMARY
-- ============================================================================
SELECT '✅ Incremental generator deployed successfully!' AS STATUS;
SELECT '   To start: ALTER TASK INCREMENTAL_DATA_TASK RESUME;' AS NEXT_STEP;
SELECT '   To stop:  ALTER TASK INCREMENTAL_DATA_TASK SUSPEND;' AS HOW_TO_STOP;
SELECT '   Monitor:  SELECT * FROM GENERATION_STATUS;' AS MONITORING;

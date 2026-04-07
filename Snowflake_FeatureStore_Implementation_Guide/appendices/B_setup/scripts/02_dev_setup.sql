-- =============================================================================
-- FEATURE STORE IMPLEMENTATION GUIDE: DEV SETUP
-- =============================================================================
-- 
-- This script has two parts:
--
-- PART 1 (DBA_ROLE): Production Infrastructure
--   - Production data tables (CLICKSTREAM_DATA) 
--   - Incremental generator stored procedure and task
--   - Development branch management procedures
--
-- PART 2 (DEV_ROLE): Development Environment  
--   - Development schemas (created by DEV, not DBA)
--   - Consumer grants on development objects
--
-- This demonstrates proper separation of concerns:
--   - DBA creates production infrastructure
--   - DEV creates their own development environment
--   - DEV grants Consumer access to their objects
--
-- Prerequisites:
--   - 01_dba_setup.sql has been run
--   - User has both FS_ADMIN_ROLE and FS_DEV_ROLE granted
--   - Warehouses are available
--
-- Usage:
--   snowsql -f 02_dev_setup.sql
--
-- After running this script:
--   - Use Streamlit app or CLI to load initial data
--   - Optionally resume the incremental generator task
--
-- =============================================================================

USE ROLE FS_ADMIN_ROLE;
USE WAREHOUSE FS_DEV_WH;
USE DATABASE FEATURE_STORE_DEMO;

-- =============================================================================
-- SECTION 1: CREATE PRODUCTION DATA TABLES
-- =============================================================================
-- These tables form the clickstream data model used throughout the guide.

USE SCHEMA CLICKSTREAM_DATA;

-- -----------------------------------------------------------------------------
-- Dimension Tables (Static reference data)
-- -----------------------------------------------------------------------------

-- Product Categories
CREATE TABLE IF NOT EXISTS CATEGORIES (
    CATEGORY_ID VARCHAR(20) PRIMARY KEY,
    CATEGORY_NAME VARCHAR(100) NOT NULL,
    PARENT_CATEGORY_ID VARCHAR(20),
    LEVEL INT DEFAULT 1,
    PATH VARCHAR(500),
    IS_ACTIVE BOOLEAN DEFAULT TRUE,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Suppliers
CREATE TABLE IF NOT EXISTS SUPPLIERS (
    SUPPLIER_ID VARCHAR(20) PRIMARY KEY,
    SUPPLIER_NAME VARCHAR(200) NOT NULL,
    CONTACT_EMAIL VARCHAR(200),
    CONTACT_PHONE VARCHAR(50),
    ADDRESS VARCHAR(500),
    CITY VARCHAR(100),
    STATE VARCHAR(50),
    COUNTRY VARCHAR(100) DEFAULT 'USA',
    IS_ACTIVE BOOLEAN DEFAULT TRUE,
    RATING DECIMAL(3,2),
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Products
CREATE TABLE IF NOT EXISTS PRODUCTS (
    PRODUCT_ID VARCHAR(20) PRIMARY KEY,
    PRODUCT_NAME VARCHAR(200) NOT NULL,
    CATEGORY_ID VARCHAR(20) REFERENCES CATEGORIES(CATEGORY_ID),
    BRAND VARCHAR(100),
    DESCRIPTION VARCHAR(2000),
    BASE_PRICE DECIMAL(10,2),
    CURRENT_PRICE DECIMAL(10,2),
    COST DECIMAL(10,2),
    SKU VARCHAR(50),
    WEIGHT_KG DECIMAL(8,3),
    IS_ACTIVE BOOLEAN DEFAULT TRUE,
    LAUNCH_DATE DATE,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Product-Supplier mapping (many-to-many)
CREATE TABLE IF NOT EXISTS PRODUCT_SUPPLIER (
    PRODUCT_ID VARCHAR(20) REFERENCES PRODUCTS(PRODUCT_ID),
    SUPPLIER_ID VARCHAR(20) REFERENCES SUPPLIERS(SUPPLIER_ID),
    IS_PRIMARY BOOLEAN DEFAULT FALSE,
    LEAD_TIME_DAYS INT,
    UNIT_COST DECIMAL(10,2),
    MIN_ORDER_QTY INT DEFAULT 1,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (PRODUCT_ID, SUPPLIER_ID)
);

-- Households
CREATE TABLE IF NOT EXISTS HOUSEHOLDS (
    HOUSEHOLD_ID VARCHAR(20) PRIMARY KEY,
    ADDRESS_LINE1 VARCHAR(200),
    ADDRESS_LINE2 VARCHAR(200),
    CITY VARCHAR(100),
    STATE VARCHAR(50),
    POSTAL_CODE VARCHAR(20),
    COUNTRY VARCHAR(100) DEFAULT 'USA',
    HOUSEHOLD_SIZE INT,
    INCOME_BRACKET VARCHAR(50),
    HOME_OWNERSHIP VARCHAR(50),
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Entity Tables (Core entities for Feature Store)
-- -----------------------------------------------------------------------------

-- Anonymous Visitors
CREATE TABLE IF NOT EXISTS VISITORS (
    VISITOR_ID VARCHAR(40) PRIMARY KEY,
    FIRST_SEEN_TS TIMESTAMP_NTZ NOT NULL,
    LAST_SEEN_TS TIMESTAMP_NTZ,
    FIRST_REFERRER VARCHAR(500),
    FIRST_UTM_SOURCE VARCHAR(100),
    FIRST_UTM_MEDIUM VARCHAR(100),
    FIRST_UTM_CAMPAIGN VARCHAR(200),
    FIRST_DEVICE_TYPE VARCHAR(50),
    FIRST_BROWSER VARCHAR(100),
    FIRST_OS VARCHAR(100),
    FIRST_COUNTRY VARCHAR(100),
    FIRST_REGION VARCHAR(100),
    FIRST_CITY VARCHAR(100),
    SESSION_CNT INT DEFAULT 0,
    PAGE_VIEW_CNT INT DEFAULT 0,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Registered Users
CREATE TABLE IF NOT EXISTS USERS (
    USER_ID VARCHAR(40) PRIMARY KEY,
    VISITOR_ID VARCHAR(40) REFERENCES VISITORS(VISITOR_ID),
    HOUSEHOLD_ID VARCHAR(20) REFERENCES HOUSEHOLDS(HOUSEHOLD_ID),
    EMAIL VARCHAR(200),
    USERNAME VARCHAR(100),
    FIRST_NAME VARCHAR(100),
    LAST_NAME VARCHAR(100),
    PHONE VARCHAR(50),
    GENDER VARCHAR(20),
    BIRTH_DATE DATE,
    REGISTRATION_TS TIMESTAMP_NTZ NOT NULL,
    LAST_LOGIN_TS TIMESTAMP_NTZ,
    IS_ACTIVE BOOLEAN DEFAULT TRUE,
    EMAIL_VERIFIED BOOLEAN DEFAULT FALSE,
    LOYALTY_TIER VARCHAR(50) DEFAULT 'Bronze',
    LOYALTY_POINTS INT DEFAULT 0,
    PREFERRED_LANGUAGE VARCHAR(10) DEFAULT 'en',
    PREFERRED_CURRENCY VARCHAR(10) DEFAULT 'USD',
    MARKETING_OPT_IN BOOLEAN DEFAULT FALSE,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- Event/Fact Tables (Append-only, incrementally updated)
-- -----------------------------------------------------------------------------

-- Sessions
CREATE TABLE IF NOT EXISTS SESSIONS (
    SESSION_ID VARCHAR(40) PRIMARY KEY,
    VISITOR_ID VARCHAR(40) NOT NULL REFERENCES VISITORS(VISITOR_ID),
    USER_ID VARCHAR(40) REFERENCES USERS(USER_ID),
    SESSION_START_TS TIMESTAMP_NTZ NOT NULL,
    SESSION_END_TS TIMESTAMP_NTZ,
    DURATION_SEC INT,
    EVENT_CNT INT DEFAULT 0,
    PAGE_VIEW_CNT INT DEFAULT 0,
    PRODUCT_VIEW_DCNT INT DEFAULT 0,
    CART_ADD_CNT INT DEFAULT 0,
    CART_VALUE_SUM DECIMAL(12,2) DEFAULT 0,
    IS_CONVERTED BOOLEAN DEFAULT FALSE,
    ORDER_VALUE_SUM DECIMAL(12,2) DEFAULT 0,
    DEVICE_TYPE VARCHAR(50),
    BROWSER VARCHAR(100),
    OS VARCHAR(100),
    SCREEN_RESOLUTION VARCHAR(20),
    LANDING_PAGE_URL VARCHAR(500),
    EXIT_PAGE_URL VARCHAR(500),
    REFERRER_URL VARCHAR(500),
    UTM_SOURCE VARCHAR(100),
    UTM_MEDIUM VARCHAR(100),
    UTM_CAMPAIGN VARCHAR(200),
    COUNTRY VARCHAR(100),
    REGION VARCHAR(100),
    CITY VARCHAR(100),
    PRODUCTS_VIEWED VARIANT,
    CATEGORIES_VIEWED VARIANT
);

-- Clickstream Events
CREATE TABLE IF NOT EXISTS EVENTS (
    EVENT_ID VARCHAR(40) PRIMARY KEY,
    VISITOR_ID VARCHAR(40) NOT NULL,
    USER_ID VARCHAR(40),
    SESSION_ID VARCHAR(40) NOT NULL REFERENCES SESSIONS(SESSION_ID),
    EVENT_TS TIMESTAMP_NTZ NOT NULL,
    EVENT_TYPE VARCHAR(50) NOT NULL,
    EVENT_NAME VARCHAR(100),
    PRODUCT_ID VARCHAR(20),
    CATEGORY_ID VARCHAR(20),
    PAGE_URL VARCHAR(500),
    PAGE_TITLE VARCHAR(200),
    REFERRER_URL VARCHAR(500),
    PROPERTIES VARIANT,
    CONTEXT VARIANT,
    RECEIVED_TS TIMESTAMP_NTZ
);

-- Orders
CREATE TABLE IF NOT EXISTS ORDERS (
    ORDER_ID VARCHAR(40) PRIMARY KEY,
    USER_ID VARCHAR(40) NOT NULL REFERENCES USERS(USER_ID),
    SESSION_ID VARCHAR(40),
    ORDER_TS TIMESTAMP_NTZ NOT NULL,
    STATUS VARCHAR(50) DEFAULT 'pending',
    SUBTOTAL_AMT DECIMAL(12,2),
    TAX_AMT DECIMAL(12,2),
    SHIPPING_AMT DECIMAL(12,2),
    DISCOUNT_AMT DECIMAL(12,2),
    TOTAL_AMT DECIMAL(12,2),
    ITEM_CNT INT,
    COUPON_CODE VARCHAR(50),
    PAYMENT_METHOD VARCHAR(50),
    SHIPPING_METHOD VARCHAR(50),
    SHIPPING_ADDRESS VARIANT,
    BILLING_ADDRESS VARIANT,
    CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Order Line Items
CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
    ORDER_ITEM_ID VARCHAR(40) PRIMARY KEY,
    ORDER_ID VARCHAR(40) NOT NULL REFERENCES ORDERS(ORDER_ID),
    PRODUCT_ID VARCHAR(20) NOT NULL REFERENCES PRODUCTS(PRODUCT_ID),
    SUPPLIER_ID VARCHAR(20) REFERENCES SUPPLIERS(SUPPLIER_ID),
    QUANTITY INT NOT NULL,
    UNIT_PRICE_AMT DECIMAL(10,2) NOT NULL,
    DISCOUNT_AMT DECIMAL(10,2) DEFAULT 0,
    TOTAL_AMT DECIMAL(12,2),
    STATUS VARCHAR(50) DEFAULT 'pending',
    SHIPPED_TS TIMESTAMP_NTZ,
    DELIVERED_TS TIMESTAMP_NTZ
);

-- =============================================================================
-- SECTION 2: CREATE ADMIN TABLES FOR INCREMENTAL GENERATOR
-- =============================================================================

USE SCHEMA CLICKSTREAM_ADMIN;

-- Generator Configuration
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

-- Insert default config
MERGE INTO GENERATION_CONFIG t
USING (SELECT 1 AS ID) s ON t.ID = s.ID
WHEN NOT MATCHED THEN INSERT (ID) VALUES (1);

-- Generator State
CREATE TABLE IF NOT EXISTS GENERATION_STATE (
    ID INT PRIMARY KEY DEFAULT 1,
    -- ID counters
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

-- Generation Log
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

-- =============================================================================
-- SECTION 3: DEPLOY INCREMENTAL GENERATOR STORED PROCEDURE
-- =============================================================================

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
    """
    start_time = datetime.now()
    
    try:
        # Check if enabled
        config = session.sql("SELECT * FROM FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATION_CONFIG WHERE ID = 1").collect()[0]
        if not config['IS_ENABLED']:
            return {"status": "disabled", "message": "Generation is disabled"}
        
        # Load state
        state = session.sql("SELECT * FROM FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATION_STATE WHERE ID = 1").collect()[0]
        
        # Load reference data
        visitors = [r['VISITOR_ID'] for r in session.sql("SELECT VISITOR_ID FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.VISITORS").collect()]
        users = [r['USER_ID'] for r in session.sql("SELECT USER_ID FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.USERS").collect()]
        products = [r['PRODUCT_ID'] for r in session.sql("SELECT PRODUCT_ID FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.PRODUCTS").collect()]
        product_suppliers = [
            (r['PRODUCT_ID'], r['SUPPLIER_ID']) 
            for r in session.sql("SELECT PRODUCT_ID, SUPPLIER_ID FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.PRODUCT_SUPPLIER").collect()
        ]
        
        if not visitors or not users or not products or not product_suppliers:
            return {"status": "error", "message": "Missing reference data - run initial load first"}
        
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
            
            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            sess_end = sess_start + timedelta(seconds=duration)
            
            device_type = random.choice(['mobile', 'desktop', 'tablet'])
            
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
            sess_id = f"sess_{random.randint(max(1, session_id - config['SESSIONS_PER_BATCH']), session_id):08d}"
            
            delta = max(1, (batch_ts - batch_start).total_seconds())
            order_ts = batch_start + timedelta(seconds=random.uniform(0, delta))
            
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
        
        # Insert data
        import pandas as pd
        
        if new_sessions:
            session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.SESSIONS")
        
        if new_events:
            session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.EVENTS")
        
        if new_orders:
            session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS")
        
        if new_order_items:
            session.create_dataframe(pd.DataFrame(new_order_items)).write.mode("append").save_as_table("FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDER_ITEMS")
        
        # Update state
        session.sql(f"""
            UPDATE FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATION_STATE SET
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
            INSERT INTO FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATION_LOG 
            (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS)
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
        error_msg = str(e).replace("'", "''")[:10000]
        session.sql(f"""
            INSERT INTO FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATION_LOG 
            (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS, ERROR_MESSAGE)
            VALUES (0, 0, 0, 0, 0, 'ERROR', '{error_msg}')
        """).collect()
        
        return {"status": "error", "message": str(e)}
$$;

-- =============================================================================
-- SECTION 4: CREATE INCREMENTAL GENERATOR TASK
-- =============================================================================
-- Task is created SUSPENDED - resume when ready to start generation

CREATE OR REPLACE TASK INCREMENTAL_DATA_TASK
    WAREHOUSE = FS_DEV_WH
    SCHEDULE = '1 MINUTE'
    ALLOW_OVERLAPPING_EXECUTION = FALSE
    COMMENT = 'Generates incremental clickstream data for Feature Store demos'
AS
    CALL FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.GENERATE_INCREMENTAL_BATCH();

-- =============================================================================
-- SECTION 5: CREATE MONITORING VIEWS
-- =============================================================================

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

-- =============================================================================
-- SECTION 6: CREATE DEV BRANCH PROCEDURE (Python)
-- =============================================================================
-- This procedure creates a development database with Dynamic Tables that 
-- sample from production. Accepts a configurable database name.

CREATE OR REPLACE PROCEDURE CREATE_DEV_BRANCH(
    DEV_DATABASE VARCHAR DEFAULT 'FEATURE_STORE_DEMO_DEV',
    SAMPLE_PCT FLOAT DEFAULT 10.0,
    TARGET_LAG VARCHAR DEFAULT '1 HOUR',
    WAREHOUSE VARCHAR DEFAULT 'FS_DEV_WH'
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'create_dev_branch'
COMMENT = 'Creates development branch database with Dynamic Tables sampling from production'
AS
$$
from snowflake.snowpark import Session
from datetime import datetime

def create_dev_branch(
    session: Session,
    dev_database: str,
    sample_pct: float,
    target_lag: str,
    warehouse: str
) -> dict:
    """
    Create a development branch database with Dynamic Tables that sample from production.
    
    Args:
        session: Snowpark session
        dev_database: Name of the development database to create/populate
        sample_pct: Percentage of visitors to sample (e.g., 10.0 for 10%)
        target_lag: Target lag for Dynamic Tables (e.g., '1 HOUR', '15 MINUTES')
        warehouse: Warehouse to use for DT refresh
    
    Returns:
        dict with status and details
    """
    start_time = datetime.now()
    prod_db = 'FEATURE_STORE_DEMO'
    schema = 'CLICKSTREAM_DATA'
    
    try:
        # Validate inputs
        dev_database = dev_database.upper().strip()
        if not dev_database:
            return {"status": "error", "message": "dev_database cannot be empty"}
        
        if sample_pct <= 0 or sample_pct > 100:
            return {"status": "error", "message": "sample_pct must be between 0 and 100"}
        
        # Create the development database if it doesn't exist
        session.sql(f"CREATE DATABASE IF NOT EXISTS {dev_database}").collect()
        
        # Create schema
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.{schema}").collect()
        
        # Create admin schema for config tracking
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.CLICKSTREAM_ADMIN").collect()
        
        # Track branch configuration
        session.sql(f"""
            CREATE TABLE IF NOT EXISTS {dev_database}.CLICKSTREAM_ADMIN.BRANCH_CONFIG (
                ID INT PRIMARY KEY DEFAULT 1,
                SOURCE_DATABASE VARCHAR DEFAULT '{prod_db}',
                SAMPLE_PCT FLOAT DEFAULT {sample_pct},
                TARGET_LAG VARCHAR DEFAULT '{target_lag}',
                WAREHOUSE VARCHAR DEFAULT '{warehouse}',
                CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
        """).collect()
        
        # Insert or update config
        session.sql(f"""
            MERGE INTO {dev_database}.CLICKSTREAM_ADMIN.BRANCH_CONFIG t
            USING (SELECT 1 AS ID) s ON t.ID = s.ID
            WHEN MATCHED THEN UPDATE SET 
                SAMPLE_PCT = {sample_pct},
                TARGET_LAG = '{target_lag}',
                WAREHOUSE = '{warehouse}',
                UPDATED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (ID, SOURCE_DATABASE, SAMPLE_PCT, TARGET_LAG, WAREHOUSE)
                VALUES (1, '{prod_db}', {sample_pct}, '{target_lag}', '{warehouse}')
        """).collect()
        
        tables_created = []
        
        # -------------------------------------------------------------------------
        # Create Dynamic Tables for entity/fact tables (sampled from production)
        # -------------------------------------------------------------------------
        
        # 1. VISITORS - Sample base entity
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.VISITORS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT * FROM {prod_db}.{schema}.VISITORS
               SAMPLE ({sample_pct})
        """).collect()
        tables_created.append("VISITORS (DT)")
        
        # 2. USERS - Join to sampled visitors
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.USERS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT u.* FROM {prod_db}.{schema}.USERS u
               INNER JOIN {dev_database}.{schema}.VISITORS v 
                   ON u.VISITOR_ID = v.VISITOR_ID
        """).collect()
        tables_created.append("USERS (DT)")
        
        # 3. SESSIONS - Join to sampled visitors
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.SESSIONS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT s.* FROM {prod_db}.{schema}.SESSIONS s
               INNER JOIN {dev_database}.{schema}.VISITORS v 
                   ON s.VISITOR_ID = v.VISITOR_ID
        """).collect()
        tables_created.append("SESSIONS (DT)")
        
        # 4. EVENTS - Join to sampled sessions
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.EVENTS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT e.* FROM {prod_db}.{schema}.EVENTS e
               INNER JOIN {dev_database}.{schema}.SESSIONS s 
                   ON e.SESSION_ID = s.SESSION_ID
        """).collect()
        tables_created.append("EVENTS (DT)")
        
        # 5. ORDERS - Join to sampled users
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.ORDERS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT o.* FROM {prod_db}.{schema}.ORDERS o
               INNER JOIN {dev_database}.{schema}.USERS u 
                   ON o.USER_ID = u.USER_ID
        """).collect()
        tables_created.append("ORDERS (DT)")
        
        # 6. ORDER_ITEMS - Join to sampled orders
        session.sql(f"""
            CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{schema}.ORDER_ITEMS
                TARGET_LAG = '{target_lag}'
                WAREHOUSE = {warehouse}
            AS SELECT oi.* FROM {prod_db}.{schema}.ORDER_ITEMS oi
               INNER JOIN {dev_database}.{schema}.ORDERS o 
                   ON oi.ORDER_ID = o.ORDER_ID
        """).collect()
        tables_created.append("ORDER_ITEMS (DT)")
        
        # -------------------------------------------------------------------------
        # Copy reference/dimension tables as regular tables (rarely change)
        # -------------------------------------------------------------------------
        
        reference_tables = ['CATEGORIES', 'SUPPLIERS', 'PRODUCTS', 'PRODUCT_SUPPLIER', 'HOUSEHOLDS']
        
        for table in reference_tables:
            session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{schema}.{table}
                AS SELECT * FROM {prod_db}.{schema}.{table}
            """).collect()
            tables_created.append(f"{table} (TABLE)")
        
        # -------------------------------------------------------------------------
        # Create Feature Store schema (empty, ready for development)
        # -------------------------------------------------------------------------
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.FEATURE_STORE").collect()
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.TRAINING_DATA").collect()
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.SPINES").collect()
        
        duration_sec = (datetime.now() - start_time).total_seconds()
        
        return {
            "status": "success",
            "dev_database": dev_database,
            "source_database": prod_db,
            "sample_pct": sample_pct,
            "target_lag": target_lag,
            "warehouse": warehouse,
            "tables_created": tables_created,
            "duration_seconds": round(duration_sec, 2),
            "message": f"Development branch '{dev_database}' created successfully with {sample_pct}% sample"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "dev_database": dev_database,
            "message": str(e)
        }
$$;

-- =============================================================================
-- SECTION 7: UPDATE DEV BRANCH TARGET LAG PROCEDURE
-- =============================================================================
-- Updates the target lag for all Dynamic Tables in a development branch

CREATE OR REPLACE PROCEDURE UPDATE_DEV_BRANCH_TARGET_LAG(
    DEV_DATABASE VARCHAR,
    NEW_TARGET_LAG VARCHAR DEFAULT '1 HOUR'
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'update_target_lag'
COMMENT = 'Updates target lag for all Dynamic Tables in a development branch'
AS
$$
from snowflake.snowpark import Session

def update_target_lag(session: Session, dev_database: str, new_target_lag: str) -> dict:
    """Update the target lag for all Dynamic Tables in a development branch."""
    
    dev_database = dev_database.upper().strip()
    schema = 'CLICKSTREAM_DATA'
    dt_tables = ['VISITORS', 'USERS', 'SESSIONS', 'EVENTS', 'ORDERS', 'ORDER_ITEMS']
    
    updated = []
    errors = []
    
    for table in dt_tables:
        try:
            session.sql(f"""
                ALTER DYNAMIC TABLE {dev_database}.{schema}.{table}
                SET TARGET_LAG = '{new_target_lag}'
            """).collect()
            updated.append(table)
        except Exception as e:
            errors.append({"table": table, "error": str(e)})
    
    # Update config table
    try:
        session.sql(f"""
            UPDATE {dev_database}.CLICKSTREAM_ADMIN.BRANCH_CONFIG
            SET TARGET_LAG = '{new_target_lag}', UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE ID = 1
        """).collect()
    except:
        pass  # Config table may not exist in older branches
    
    return {
        "status": "success" if not errors else "partial",
        "dev_database": dev_database,
        "new_target_lag": new_target_lag,
        "tables_updated": updated,
        "errors": errors
    }
$$;

-- =============================================================================
-- SECTION 8: DROP DEV BRANCH PROCEDURE
-- =============================================================================
-- Drops a development branch database

CREATE OR REPLACE PROCEDURE DROP_DEV_BRANCH(
    DEV_DATABASE VARCHAR
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'drop_dev_branch'
COMMENT = 'Drops a development branch database'
AS
$$
from snowflake.snowpark import Session

def drop_dev_branch(session: Session, dev_database: str) -> dict:
    """Drop a development branch database."""
    
    dev_database = dev_database.upper().strip()
    
    # Safety check - don't drop production!
    if dev_database in ('FEATURE_STORE_DEMO',):
        return {"status": "error", "message": "Cannot drop production database"}
    
    try:
        session.sql(f"DROP DATABASE IF EXISTS {dev_database}").collect()
        return {
            "status": "success",
            "message": f"Database '{dev_database}' dropped successfully"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
$$;

-- =============================================================================
-- SECTION 9: GRANT EXECUTE PRIVILEGES ON PROCEDURES
-- =============================================================================

GRANT USAGE ON PROCEDURE GENERATE_INCREMENTAL_BATCH() TO ROLE FS_ADMIN_ROLE;
GRANT OPERATE ON TASK INCREMENTAL_DATA_TASK TO ROLE FS_ADMIN_ROLE;

-- Dev branch procedures - DEV role can create/manage branches
GRANT USAGE ON PROCEDURE CREATE_DEV_BRANCH(VARCHAR, FLOAT, VARCHAR, VARCHAR) TO ROLE FS_DEV_ROLE;
GRANT USAGE ON PROCEDURE UPDATE_DEV_BRANCH_TARGET_LAG(VARCHAR, VARCHAR) TO ROLE FS_DEV_ROLE;
GRANT USAGE ON PROCEDURE DROP_DEV_BRANCH(VARCHAR) TO ROLE FS_DEV_ROLE;

-- DBA also gets dev branch procedures (for production management)
GRANT USAGE ON PROCEDURE CREATE_DEV_BRANCH(VARCHAR, FLOAT, VARCHAR, VARCHAR) TO ROLE FS_ADMIN_ROLE;
GRANT USAGE ON PROCEDURE UPDATE_DEV_BRANCH_TARGET_LAG(VARCHAR, VARCHAR) TO ROLE FS_ADMIN_ROLE;
GRANT USAGE ON PROCEDURE DROP_DEV_BRANCH(VARCHAR) TO ROLE FS_ADMIN_ROLE;

-- =============================================================================
-- SECTION 10: DEV CREATES DEVELOPMENT SCHEMAS (DEV Role)
-- =============================================================================
-- Now switch to DEV role. DEV owns FEATURE_STORE_DEMO_DEV database (granted by DBA in
-- 01_dba_setup.sql) and can create their own schemas and grant access to Consumer.

USE ROLE FS_DEV_ROLE;
USE DATABASE FEATURE_STORE_DEMO_DEV;
USE WAREHOUSE FS_DEV_WH;

-- DEV creates schemas to mirror production structure
CREATE SCHEMA IF NOT EXISTS CLICKSTREAM_DATA
    COMMENT = 'Development clickstream data (subset of production)';

CREATE SCHEMA IF NOT EXISTS CLICKSTREAM_ADMIN
    COMMENT = 'Development admin - DT configuration and state';

CREATE SCHEMA IF NOT EXISTS FEATURE_STORE
    COMMENT = 'Development feature store entities and feature views';

CREATE SCHEMA IF NOT EXISTS ML_DATASETS
    COMMENT = 'Development ML datasets';

CREATE SCHEMA IF NOT EXISTS TRAINING_DATA
    COMMENT = 'Development training datasets';

CREATE SCHEMA IF NOT EXISTS INFERENCE_DATA
    COMMENT = 'Development inference data';

CREATE SCHEMA IF NOT EXISTS SPINES
    COMMENT = 'Development spine tables';

-- =============================================================================
-- SECTION 11: DEV GRANTS CONSUMER ACCESS TO DEV SCHEMAS
-- =============================================================================
-- DEV is responsible for granting Consumer access to their objects.

-- Grant schema usage to Consumer
GRANT USAGE ON SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA CLICKSTREAM_ADMIN TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA ML_DATASETS TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA TRAINING_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA INFERENCE_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT USAGE ON SCHEMA SPINES TO ROLE FS_CONSUMER_ROLE;

-- Grant SELECT on current and future objects to Consumer
GRANT SELECT ON ALL TABLES IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA CLICKSTREAM_DATA TO ROLE FS_CONSUMER_ROLE;

GRANT SELECT ON ALL TABLES IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA FEATURE_STORE TO ROLE FS_CONSUMER_ROLE;

GRANT SELECT ON ALL TABLES IN SCHEMA ML_DATASETS TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA ML_DATASETS TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA ML_DATASETS TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA ML_DATASETS TO ROLE FS_CONSUMER_ROLE;

GRANT SELECT ON ALL TABLES IN SCHEMA TRAINING_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA TRAINING_DATA TO ROLE FS_CONSUMER_ROLE;

GRANT SELECT ON ALL TABLES IN SCHEMA INFERENCE_DATA TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA INFERENCE_DATA TO ROLE FS_CONSUMER_ROLE;

GRANT SELECT ON ALL TABLES IN SCHEMA SPINES TO ROLE FS_CONSUMER_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA SPINES TO ROLE FS_CONSUMER_ROLE;

-- Allow Consumer to create personal schemas in dev for their own work
GRANT CREATE SCHEMA ON DATABASE FEATURE_STORE_DEMO_DEV TO ROLE FS_CONSUMER_ROLE;

-- =============================================================================
-- SECTION 12: VERIFY SETUP
-- =============================================================================

SELECT '✅ DEV Setup Complete!' AS STATUS;

-- Production objects (created as DBA)
SELECT 'Production tables created:' AS INFO;
SELECT TABLE_NAME, TABLE_TYPE 
FROM FEATURE_STORE_DEMO.INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'CLICKSTREAM_DATA'
ORDER BY TABLE_NAME;

SELECT 'Admin tables created:' AS INFO;
SELECT TABLE_NAME, TABLE_TYPE 
FROM FEATURE_STORE_DEMO.INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'CLICKSTREAM_ADMIN'
ORDER BY TABLE_NAME;

-- Development objects (created as DEV)
SELECT 'Development schemas created:' AS INFO;
SHOW SCHEMAS IN DATABASE FEATURE_STORE_DEMO_DEV
  ->> SELECT "name" AS SCHEMA_NAME, "owner" AS OWNER FROM $1 WHERE "name" NOT IN ('INFORMATION_SCHEMA', 'PUBLIC');

-- =============================================================================
-- NEXT STEPS
-- =============================================================================
SELECT '
📋 NEXT STEPS:
1. Load initial data using Streamlit app or CLI:
   - Streamlit: streamlit run data_manager/app.py
   - CLI: python generator/main.py --scale 0.01 --database FEATURE_STORE_DEMO

2. (Optional) Start incremental generation:
   ALTER TASK FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.INCREMENTAL_DATA_TASK RESUME;

3. Create development branch (custom database name):
   CALL FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.CREATE_DEV_BRANCH(
       ''FEATURE_STORE_DEMO_DEV'',      -- dev_database
       10.0,                    -- sample_pct
       ''1 HOUR'',             -- target_lag  
       ''FS_DEV_WH''  -- warehouse
   );

4. Or create a named branch (e.g., for a student):
   CALL FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.CREATE_DEV_BRANCH(
       ''FEATURE_STORE_DEMO_DEV_STUDENT01'', 10.0, ''30 MINUTES'', ''FS_DEV_WH''
   );

5. Update refresh frequency:
   CALL FEATURE_STORE_DEMO.CLICKSTREAM_ADMIN.UPDATE_DEV_BRANCH_TARGET_LAG(
       ''FEATURE_STORE_DEMO_DEV'', ''15 MINUTES''
   );

6. Run 03_consumer_quickstart.sql for consumer-specific setup
' AS NEXT_STEPS;

-- =============================================================================
-- END OF DEV SETUP
-- =============================================================================

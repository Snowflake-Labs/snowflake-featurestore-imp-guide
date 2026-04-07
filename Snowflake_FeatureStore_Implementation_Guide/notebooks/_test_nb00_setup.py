"""
Test script for NB 00 Platform Setup – runs the DBA infrastructure setup.

Run from the notebooks/ directory:
    python _test_nb00_setup.py

This creates: roles, warehouse, databases, schemas, tables, generator,
and dev branch.  Uses ACCOUNTADMIN then hands off to FS_ADMIN_ROLE.
"""

import sys
sys.path.insert(0, ".")

from feature_definitions.config import get_config, ROLES, DATA_SCALE

# ---------------------------------------------------------------------------
# 1. Connect as ACCOUNTADMIN (needed for role creation and grants)
# ---------------------------------------------------------------------------
from feature_definitions.config import get_session

session = get_session(role="ACCOUNTADMIN")
print(f"Connected as {session.get_current_user()} / {session.get_current_role()}")

prod_cfg = get_config("PROD")
dev_cfg = get_config("DEV")
admin_role = ROLES["admin"]
dev_role = ROLES["dev"]
consumer_role = ROLES["consumer"]
warehouse = prod_cfg["warehouse"]
wh_size = prod_cfg["warehouse_size"]
prod_db = prod_cfg["database"]
dev_db = dev_cfg["database"]

# ---------------------------------------------------------------------------
# 2. Create Roles
# ---------------------------------------------------------------------------
print("\n=== Creating roles ===")
for role_name, comment in [
    (consumer_role, "Read-only access to feature store, can create view-based features"),
    (dev_role, "Feature store development - can create DT-based features"),
    (admin_role, "Feature store administration - production deployment and promotion"),
]:
    session.sql(f"CREATE ROLE IF NOT EXISTS {role_name} COMMENT = '{comment}'").collect()
    print(f"  Created/verified: {role_name}")

# Role hierarchy: CONSUMER -> DEV -> ADMIN -> SYSADMIN
session.sql(f"GRANT ROLE {consumer_role} TO ROLE {dev_role}").collect()
session.sql(f"GRANT ROLE {dev_role} TO ROLE {admin_role}").collect()
session.sql(f"GRANT ROLE {admin_role} TO ROLE SYSADMIN").collect()

# Grant to current user
current_user = session.get_current_user().strip('"')
for r in [consumer_role, dev_role, admin_role]:
    session.sql(f"GRANT ROLE {r} TO USER {current_user}").collect()

print("  Role hierarchy established")

# ---------------------------------------------------------------------------
# 3. Create Warehouse
# ---------------------------------------------------------------------------
print("\n=== Creating warehouse ===")
session.sql(f"""
    CREATE WAREHOUSE IF NOT EXISTS {warehouse}
        WAREHOUSE_SIZE = '{wh_size}'
        AUTO_SUSPEND = 60
        AUTO_RESUME = TRUE
        INITIALLY_SUSPENDED = TRUE
        COMMENT = 'Feature Store Implementation Guide - default warehouse'
""").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {warehouse} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {warehouse} TO ROLE {dev_role}").collect()
session.sql(f"GRANT OPERATE ON WAREHOUSE {warehouse} TO ROLE {admin_role}").collect()
print(f"  Created/verified: {warehouse} ({wh_size})")

# Refresh warehouse (dedicated for DT refreshes, multi-cluster capable)
refresh_wh = dev_cfg.get("refresh_warehouse", "FS_REFRESH_WH")
session.sql(f"""
    CREATE WAREHOUSE IF NOT EXISTS {refresh_wh}
        WAREHOUSE_SIZE      = '{wh_size}'
        MIN_CLUSTER_COUNT   = 1
        MAX_CLUSTER_COUNT   = 8
        SCALING_POLICY      = 'STANDARD'
        AUTO_SUSPEND        = 60
        AUTO_RESUME         = TRUE
        INITIALLY_SUSPENDED = TRUE
        COMMENT = 'Dedicated DT refresh warehouse - max clusters = number of DTs'
""").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {refresh_wh} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {refresh_wh} TO ROLE {dev_role}").collect()
session.sql(f"GRANT OPERATE ON WAREHOUSE {refresh_wh} TO ROLE {admin_role}").collect()
print(f"  Created/verified: {refresh_wh} ({wh_size}) [DT refresh]")

# Serving warehouse (dedicated for OFT benchmark, multi-cluster capable)
serving_wh = dev_cfg.get("serving_warehouse", "FS_SERVING_WH")
session.sql(f"""
    CREATE WAREHOUSE IF NOT EXISTS {serving_wh}
        WAREHOUSE_SIZE      = '{wh_size}'
        MIN_CLUSTER_COUNT   = 1
        MAX_CLUSTER_COUNT   = 1
        SCALING_POLICY      = 'STANDARD'
        AUTO_SUSPEND        = 60
        AUTO_RESUME         = TRUE
        INITIALLY_SUSPENDED = TRUE
        COMMENT = 'Feature Store serving benchmark - isolated from ingestion'
""").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {serving_wh} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT USAGE ON WAREHOUSE {serving_wh} TO ROLE {dev_role}").collect()
session.sql(f"GRANT OPERATE ON WAREHOUSE {serving_wh} TO ROLE {admin_role}").collect()
print(f"  Created/verified: {serving_wh} ({wh_size}) [serving benchmark]")

# ---------------------------------------------------------------------------
# 4. Create Databases
# ---------------------------------------------------------------------------
print("\n=== Creating databases ===")
for db_name in [prod_db, dev_db]:
    session.sql(f"CREATE DATABASE IF NOT EXISTS {db_name}").collect()
    print(f"  Created/verified: {db_name}")

# Ownership
session.sql(f"GRANT OWNERSHIP ON DATABASE {prod_db} TO ROLE {admin_role} COPY CURRENT GRANTS").collect()
session.sql(f"GRANT CREATE SCHEMA ON DATABASE {prod_db} TO ROLE {admin_role}").collect()
session.sql(f"GRANT OWNERSHIP ON DATABASE {dev_db} TO ROLE {dev_role} COPY CURRENT GRANTS").collect()
session.sql(f"GRANT CREATE SCHEMA ON DATABASE {dev_db} TO ROLE {dev_role}").collect()

# Cross-env read access
session.sql(f"GRANT USAGE ON DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT USAGE ON DATABASE {prod_db} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT USAGE ON DATABASE {dev_db} TO ROLE {consumer_role}").collect()

# Task execution
session.sql(f"GRANT EXECUTE TASK ON ACCOUNT TO ROLE {admin_role}").collect()
session.sql(f"GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE {admin_role}").collect()
session.sql(f"GRANT EXECUTE TASK ON ACCOUNT TO ROLE {dev_role}").collect()
session.sql(f"GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE {dev_role}").collect()
print("  Grants applied")

# ---------------------------------------------------------------------------
# 5. Switch to ADMIN role for schema/table creation
# ---------------------------------------------------------------------------
session.sql(f"USE ROLE {admin_role}").collect()
session.sql(f"USE WAREHOUSE {warehouse}").collect()
session.sql(f"USE DATABASE {prod_db}").collect()
print(f"\nSwitched to {admin_role}")

# ---------------------------------------------------------------------------
# 6. Create Production Schemas
# ---------------------------------------------------------------------------
print("\n=== Creating production schemas ===")
schemas = {
    "source_schema": "Clickstream source data tables",
    "admin_schema": "Incremental generator configuration and state",
    "fs_schema": "Production feature store entities and feature views",
    "ml_datasets_schema": "Public ML datasets",
    "training_schema": "Generated training datasets",
    "inference_schema": "Batch inference inputs and outputs",
    "spines_schema": "Entity-timestamp spine tables",
}
for key, comment in schemas.items():
    schema_name = prod_cfg[key]
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {prod_db}.{schema_name} COMMENT = '{comment}'").collect()
    print(f"  {schema_name}")

# Schema grants for DEV and CONSUMER
session.sql(f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT USAGE ON FUTURE SCHEMAS IN DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE TABLES IN DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE VIEWS IN DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE {prod_db} TO ROLE {dev_role}").collect()
session.sql(f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {prod_db} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT USAGE ON FUTURE SCHEMAS IN DATABASE {prod_db} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE TABLES IN DATABASE {prod_db} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE VIEWS IN DATABASE {prod_db} TO ROLE {consumer_role}").collect()
session.sql(f"GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE {prod_db} TO ROLE {consumer_role}").collect()

# ---------------------------------------------------------------------------
# 7. Create Source Data Tables (CLICKSTREAM_DATA)
# ---------------------------------------------------------------------------
print("\n=== Creating source data tables ===")
src = prod_cfg["source_schema"]
session.sql(f"USE SCHEMA {prod_db}.{src}").collect()

table_ddl = [
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.CATEGORIES (
        CATEGORY_ID VARCHAR(20) PRIMARY KEY,
        CATEGORY_NAME VARCHAR(100) NOT NULL,
        PARENT_CATEGORY_ID VARCHAR(20),
        LEVEL INT DEFAULT 1,
        PATH VARCHAR(500),
        IS_ACTIVE BOOLEAN DEFAULT TRUE,
        CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        UPDATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.SUPPLIERS (
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.PRODUCTS (
        PRODUCT_ID VARCHAR(20) PRIMARY KEY,
        PRODUCT_NAME VARCHAR(200) NOT NULL,
        CATEGORY_ID VARCHAR(20),
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.PRODUCT_SUPPLIER (
        PRODUCT_ID VARCHAR(20),
        SUPPLIER_ID VARCHAR(20),
        IS_PRIMARY BOOLEAN DEFAULT FALSE,
        LEAD_TIME_DAYS INT,
        UNIT_COST DECIMAL(10,2),
        MIN_ORDER_QTY INT DEFAULT 1,
        CREATED_TS TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        PRIMARY KEY (PRODUCT_ID, SUPPLIER_ID)
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.HOUSEHOLDS (
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.VISITORS (
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.USERS (
        USER_ID VARCHAR(40) PRIMARY KEY,
        VISITOR_ID VARCHAR(40),
        HOUSEHOLD_ID VARCHAR(20),
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.SESSIONS (
        SESSION_ID VARCHAR(40) PRIMARY KEY,
        VISITOR_ID VARCHAR(40) NOT NULL,
        USER_ID VARCHAR(40),
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.EVENTS (
        EVENT_ID VARCHAR(40) PRIMARY KEY,
        VISITOR_ID VARCHAR(40) NOT NULL,
        USER_ID VARCHAR(40),
        SESSION_ID VARCHAR(40) NOT NULL,
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.ORDERS (
        ORDER_ID VARCHAR(40) PRIMARY KEY,
        USER_ID VARCHAR(40) NOT NULL,
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
    )""",
    f"""CREATE TABLE IF NOT EXISTS {prod_db}.{src}.ORDER_ITEMS (
        ORDER_ITEM_ID VARCHAR(40) PRIMARY KEY,
        ORDER_ID VARCHAR(40) NOT NULL,
        PRODUCT_ID VARCHAR(20) NOT NULL,
        SUPPLIER_ID VARCHAR(20),
        QUANTITY INT NOT NULL,
        UNIT_PRICE_AMT DECIMAL(10,2) NOT NULL,
        DISCOUNT_AMT DECIMAL(10,2) DEFAULT 0,
        TOTAL_AMT DECIMAL(12,2),
        STATUS VARCHAR(50) DEFAULT 'pending',
        SHIPPED_TS TIMESTAMP_NTZ,
        DELIVERED_TS TIMESTAMP_NTZ
    )""",
]

for ddl in table_ddl:
    session.sql(ddl).collect()
    tname = ddl.split(f"{prod_db}.{src}.")[1].split()[0]
    print(f"  {tname}")

# Grant SELECT on existing tables to DEV and CONSUMER
session.sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {prod_db}.{src} TO ROLE {dev_role}").collect()
session.sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {prod_db}.{src} TO ROLE {consumer_role}").collect()

# ---------------------------------------------------------------------------
# 8. Load synthetic data (small scale)
# ---------------------------------------------------------------------------
print(f"\n=== Loading synthetic data (scale={DATA_SCALE}) ===")

import random
import uuid
from datetime import datetime, timedelta

import pandas as pd

random.seed(42)
now = datetime.now()
base_ts = now - timedelta(days=365)

# --- Categories ---
categories_data = [
    {"CATEGORY_ID": f"cat_{i:02d}", "CATEGORY_NAME": name, "IS_ACTIVE": True,
     "CREATED_TS": base_ts, "UPDATED_TS": base_ts}
    for i, name in enumerate([
        "ACCESSORIES", "BAGS", "BOOKS", "DRINKWARE", "GIFT",
        "HATS", "KIDS", "OFFICE", "OUTERWEAR", "PETS",
        "SME", "SNOW", "TEES",
    ], 1)
]
session.create_dataframe(pd.DataFrame(categories_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.CATEGORIES"
)
print(f"  CATEGORIES: {len(categories_data)} rows")

# --- Suppliers ---
n_suppliers = 10
suppliers_data = []
for i in range(1, n_suppliers + 1):
    suppliers_data.append({
        "SUPPLIER_ID": f"sup_{i:03d}",
        "SUPPLIER_NAME": f"Supplier {i} Corp",
        "CONTACT_EMAIL": f"contact@supplier{i}.com",
        "COUNTRY": random.choice(["USA", "USA", "USA", "CAN", "GBR"]),
        "IS_ACTIVE": True,
        "RATING": round(random.uniform(3.0, 5.0), 2),
        "CREATED_TS": base_ts, "UPDATED_TS": base_ts,
    })
session.create_dataframe(pd.DataFrame(suppliers_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.SUPPLIERS"
)
print(f"  SUPPLIERS: {len(suppliers_data)} rows")

# --- Products ---
n_products = 50
products_data = []
for i in range(1, n_products + 1):
    cat = random.choice(categories_data)
    base_price = round(random.uniform(10, 200), 2)
    products_data.append({
        "PRODUCT_ID": f"prod_{i:04d}",
        "PRODUCT_NAME": f"{cat['CATEGORY_NAME'].title()} Item {i}",
        "CATEGORY_ID": cat["CATEGORY_ID"],
        "BRAND": f"Brand{random.randint(1,10)}",
        "DESCRIPTION": f"A quality {cat['CATEGORY_NAME'].lower()} product for everyday use.",
        "BASE_PRICE": base_price,
        "CURRENT_PRICE": round(base_price * random.uniform(0.8, 1.0), 2),
        "COST": round(base_price * random.uniform(0.4, 0.6), 2),
        "SKU": f"{cat['CATEGORY_NAME'][:3]}-{i:04d}",
        "IS_ACTIVE": random.random() < 0.9,
        "CREATED_TS": base_ts, "UPDATED_TS": base_ts,
    })
session.create_dataframe(pd.DataFrame(products_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.PRODUCTS"
)
print(f"  PRODUCTS: {len(products_data)} rows")

# --- Product-Supplier ---
ps_data = []
for p in products_data:
    n_sups = random.randint(1, 3)
    sups = random.sample(suppliers_data, n_sups)
    for j, s in enumerate(sups):
        ps_data.append({
            "PRODUCT_ID": p["PRODUCT_ID"],
            "SUPPLIER_ID": s["SUPPLIER_ID"],
            "IS_PRIMARY": j == 0,
            "LEAD_TIME_DAYS": random.randint(3, 30),
            "UNIT_COST": round(p["COST"] * random.uniform(0.9, 1.1), 2),
            "MIN_ORDER_QTY": random.choice([1, 5, 10]),
            "CREATED_TS": base_ts,
        })
session.create_dataframe(pd.DataFrame(ps_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.PRODUCT_SUPPLIER"
)
print(f"  PRODUCT_SUPPLIER: {len(ps_data)} rows")

# --- Households ---
n_households = max(30, int(1000 * DATA_SCALE))
hh_data = []
for i in range(1, n_households + 1):
    hh_data.append({
        "HOUSEHOLD_ID": f"hh_{i:06d}",
        "CITY": random.choice(["San Francisco", "New York", "Seattle", "Austin", "Denver"]),
        "STATE": random.choice(["CA", "NY", "WA", "TX", "CO"]),
        "COUNTRY": "USA",
        "HOUSEHOLD_SIZE": random.randint(1, 5),
        "INCOME_BRACKET": random.choice(["low", "medium", "medium", "high", "premium"]),
        "CREATED_TS": base_ts, "UPDATED_TS": base_ts,
    })
session.create_dataframe(pd.DataFrame(hh_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.HOUSEHOLDS"
)
print(f"  HOUSEHOLDS: {len(hh_data)} rows")

# --- Visitors ---
n_visitors = max(100, int(5000 * DATA_SCALE))
visitors_data = []
for i in range(1, n_visitors + 1):
    first_seen = base_ts + timedelta(days=random.randint(0, 300))
    visitors_data.append({
        "VISITOR_ID": f"vis_{i:08d}",
        "FIRST_SEEN_TS": first_seen,
        "LAST_SEEN_TS": first_seen + timedelta(days=random.randint(1, 60)),
        "FIRST_DEVICE_TYPE": random.choice(["mobile", "desktop", "tablet"]),
        "FIRST_UTM_SOURCE": random.choice(["google", "direct", "facebook", "email", None]),
        "SESSION_CNT": random.randint(1, 20),
        "PAGE_VIEW_CNT": random.randint(5, 100),
        "CREATED_TS": first_seen,
    })
session.create_dataframe(pd.DataFrame(visitors_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.VISITORS"
)
print(f"  VISITORS: {len(visitors_data)} rows")

# --- Users ---
n_users = max(50, int(1000 * DATA_SCALE))
users_data = []
for i in range(1, n_users + 1):
    vis = visitors_data[i - 1] if i <= len(visitors_data) else random.choice(visitors_data)
    hh = random.choice(hh_data)
    reg_ts = vis["FIRST_SEEN_TS"] + timedelta(days=random.randint(0, 30))
    users_data.append({
        "USER_ID": f"usr_{i:08d}",
        "VISITOR_ID": vis["VISITOR_ID"],
        "HOUSEHOLD_ID": hh["HOUSEHOLD_ID"],
        "EMAIL": f"user{i}@example.com",
        "FIRST_NAME": f"First{i}",
        "LAST_NAME": f"Last{i}",
        "REGISTRATION_TS": reg_ts,
        "LAST_LOGIN_TS": reg_ts + timedelta(days=random.randint(0, 200)),
        "IS_ACTIVE": random.random() < 0.85,
        "EMAIL_VERIFIED": random.random() < 0.8,
        "LOYALTY_TIER": random.choice(["Bronze", "Silver", "Gold", "Platinum"]),
        "LOYALTY_POINTS": random.randint(0, 5000),
        "PREFERRED_LANGUAGE": random.choice(["en", "en", "es", "fr"]),
        "CREATED_TS": reg_ts, "UPDATED_TS": reg_ts + timedelta(days=random.randint(0, 100)),
    })
session.create_dataframe(pd.DataFrame(users_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.USERS"
)
print(f"  USERS: {len(users_data)} rows")

# --- Sessions ---
n_sessions = max(200, int(10000 * DATA_SCALE))
sessions_data = []
devices = ["mobile", "desktop", "tablet"]
utm_sources = ["google", "direct", "facebook", "email", None]
for i in range(1, n_sessions + 1):
    user = random.choice(users_data) if random.random() < 0.6 else None
    vis = random.choice(visitors_data)
    start = base_ts + timedelta(seconds=random.randint(0, int(365 * 86400)))
    duration = random.randint(30, 1800)
    event_cnt = random.randint(3, 20)
    cart_adds = random.randint(0, 3)
    is_conv = random.random() < 0.03
    sessions_data.append({
        "SESSION_ID": f"sess_{i:08d}",
        "VISITOR_ID": vis["VISITOR_ID"],
        "USER_ID": user["USER_ID"] if user else None,
        "SESSION_START_TS": start,
        "SESSION_END_TS": start + timedelta(seconds=duration),
        "DURATION_SEC": duration,
        "EVENT_CNT": event_cnt,
        "PAGE_VIEW_CNT": random.randint(1, event_cnt),
        "PRODUCT_VIEW_DCNT": random.randint(0, 5),
        "CART_ADD_CNT": cart_adds,
        "CART_VALUE_SUM": round(cart_adds * random.uniform(20, 80), 2) if cart_adds else 0,
        "IS_CONVERTED": is_conv,
        "ORDER_VALUE_SUM": round(random.uniform(30, 200), 2) if is_conv else 0,
        "DEVICE_TYPE": random.choice(devices),
        "UTM_SOURCE": random.choice(utm_sources),
        "LANDING_PAGE_URL": f"/products/prod_{random.randint(1, n_products):04d}",
    })
session.create_dataframe(pd.DataFrame(sessions_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.SESSIONS"
)
print(f"  SESSIONS: {len(sessions_data)} rows")

# --- Events ---
n_events = max(500, int(50000 * DATA_SCALE))
events_data = []
event_types_names = [
    ("Browsing", "Products Searched"), ("Product", "Product Viewed"),
    ("Product", "Product Clicked"), ("Cart", "Product Added"),
    ("Cart", "Cart Viewed"), ("Checkout", "Checkout Started"),
    ("Order", "Order Completed"),
]
for i in range(1, n_events + 1):
    sess = random.choice(sessions_data)
    et, en = random.choices(event_types_names, weights=[15, 30, 20, 10, 8, 5, 2])[0]
    evt_ts = sess["SESSION_START_TS"] + timedelta(seconds=random.randint(0, max(1, sess["DURATION_SEC"])))
    events_data.append({
        "EVENT_ID": f"evt_{i:010d}",
        "VISITOR_ID": sess["VISITOR_ID"],
        "USER_ID": sess["USER_ID"],
        "SESSION_ID": sess["SESSION_ID"],
        "EVENT_TS": evt_ts,
        "EVENT_TYPE": et,
        "EVENT_NAME": en,
        "PRODUCT_ID": f"prod_{random.randint(1, n_products):04d}" if "Product" in en or "Cart" in en else None,
        "CATEGORY_ID": f"cat_{random.randint(1, 13):02d}" if "Product" in en else None,
        "PAGE_URL": f"/page/{random.randint(1, 100)}",
        "RECEIVED_TS": evt_ts + timedelta(milliseconds=random.randint(100, 500)),
    })
session.create_dataframe(pd.DataFrame(events_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.EVENTS"
)
print(f"  EVENTS: {len(events_data)} rows")

# --- Orders ---
n_orders = max(30, int(3000 * DATA_SCALE))
orders_data = []
for i in range(1, n_orders + 1):
    user = random.choice(users_data)
    order_ts = base_ts + timedelta(days=random.randint(0, 350))
    subtotal = round(random.uniform(20, 300), 2)
    tax = round(subtotal * 0.08, 2)
    ship = round(random.uniform(5, 15), 2) if subtotal < 100 else 0
    disc = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0
    orders_data.append({
        "ORDER_ID": f"ord_{i:08d}",
        "USER_ID": user["USER_ID"],
        "ORDER_TS": order_ts,
        "STATUS": random.choice(["confirmed", "shipped", "delivered"]),
        "SUBTOTAL_AMT": subtotal,
        "TAX_AMT": tax,
        "SHIPPING_AMT": ship,
        "DISCOUNT_AMT": disc,
        "TOTAL_AMT": round(subtotal + tax + ship - disc, 2),
        "ITEM_CNT": random.randint(1, 5),
        "PAYMENT_METHOD": random.choice(["credit_card", "paypal", "apple_pay"]),
        "CREATED_TS": order_ts, "UPDATED_TS": order_ts,
    })
session.create_dataframe(pd.DataFrame(orders_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.ORDERS"
)
print(f"  ORDERS: {len(orders_data)} rows")

# --- Order Items ---
oi_data = []
oi_id = 0
for order in orders_data:
    for _ in range(order["ITEM_CNT"]):
        oi_id += 1
        ps = random.choice(ps_data)
        qty = random.randint(1, 3)
        price = round(random.uniform(10, 150), 2)
        disc = round(price * random.uniform(0, 0.15), 2) if random.random() < 0.2 else 0
        oi_data.append({
            "ORDER_ITEM_ID": f"oi_{oi_id:010d}",
            "ORDER_ID": order["ORDER_ID"],
            "PRODUCT_ID": ps["PRODUCT_ID"],
            "SUPPLIER_ID": ps["SUPPLIER_ID"],
            "QUANTITY": qty,
            "UNIT_PRICE_AMT": price,
            "DISCOUNT_AMT": disc,
            "TOTAL_AMT": round(qty * (price - disc), 2),
        })
session.create_dataframe(pd.DataFrame(oi_data)).write.mode("overwrite").save_as_table(
    f"{prod_db}.{src}.ORDER_ITEMS"
)
print(f"  ORDER_ITEMS: {len(oi_data)} rows")

# ---------------------------------------------------------------------------
# 9. Create Dev schemas (as DEV role)
# ---------------------------------------------------------------------------
print("\n=== Creating dev schemas ===")
session.sql(f"USE ROLE {dev_role}").collect()
session.sql(f"USE DATABASE {dev_db}").collect()

for key, comment in schemas.items():
    schema_name = dev_cfg[key]
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_db}.{schema_name} COMMENT = '{comment}'").collect()
    print(f"  {dev_db}.{schema_name}")

# Grant consumer access to dev
for s in schemas:
    sname = dev_cfg[s]
    session.sql(f"GRANT USAGE ON SCHEMA {dev_db}.{sname} TO ROLE {consumer_role}").collect()
    session.sql(f"GRANT SELECT ON FUTURE TABLES IN SCHEMA {dev_db}.{sname} TO ROLE {consumer_role}").collect()
    session.sql(f"GRANT SELECT ON FUTURE VIEWS IN SCHEMA {dev_db}.{sname} TO ROLE {consumer_role}").collect()
    session.sql(f"GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA {dev_db}.{sname} TO ROLE {consumer_role}").collect()

# ---------------------------------------------------------------------------
# 10. Create Dev Branch (copy dim tables, use simple copy for small scale)
# ---------------------------------------------------------------------------
print("\n=== Creating dev branch (simple copy for small scale) ===")
session.sql(f"USE ROLE {admin_role}").collect()
session.sql(f"USE WAREHOUSE {warehouse}").collect()

dim_tables = ["CATEGORIES", "SUPPLIERS", "PRODUCTS", "PRODUCT_SUPPLIER", "HOUSEHOLDS"]
fact_tables = ["VISITORS", "USERS", "SESSIONS", "EVENTS", "ORDERS", "ORDER_ITEMS"]

for t in dim_tables + fact_tables:
    session.sql(f"CREATE OR REPLACE TABLE {dev_db}.{src}.{t} AS SELECT * FROM {prod_db}.{src}.{t}").collect()
    print(f"  Copied {t}")

# Grant on newly created tables
session.sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {dev_db}.{src} TO ROLE {dev_role}").collect()
session.sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {dev_db}.{src} TO ROLE {consumer_role}").collect()

# ---------------------------------------------------------------------------
# 11. Verify
# ---------------------------------------------------------------------------
print("\n=== Verification ===")
session.sql(f"USE ROLE {admin_role}").collect()
for db_name in [prod_db, dev_db]:
    result = session.sql(f"""
        SELECT TABLE_NAME, ROW_COUNT
        FROM {db_name}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{src}'
        ORDER BY TABLE_NAME
    """).collect()
    print(f"\n{db_name}.{src}:")
    for r in result:
        print(f"  {r['TABLE_NAME']}: {r['ROW_COUNT']} rows")

session.close()
print("\n✅ Platform setup complete!")

"""
Incremental data generator for the Clickstream pipeline.

Provides:
  - Admin table DDL (GENERATION_CONFIG, GENERATION_STATE, GENERATION_LOG)
  - A Python function that mirrors the stored-procedure body
  - Helpers to deploy the stored procedure and task into Snowflake
  - Scale-adjustment helpers for live tuning

The stored procedure reads GENERATION_CONFIG at the start of each cycle,
so batch sizes can be changed live without restarting the task.
"""

from __future__ import annotations

from .config import get_config, fq_table


# ---------------------------------------------------------------------------
# Admin table DDL
# ---------------------------------------------------------------------------

def create_admin_tables(session, env: str = "DEV") -> None:
    """Create GENERATION_CONFIG, GENERATION_STATE, and GENERATION_LOG."""
    cfg = get_config(env)
    db = cfg["database"]
    admin = cfg["admin_schema"]

    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {db}.{admin}.GENERATION_CONFIG (
            ID INT PRIMARY KEY DEFAULT 1,
            SESSIONS_PER_BATCH     INT     DEFAULT 50,
            EVENTS_PER_SESSION_MIN INT     DEFAULT 3,
            EVENTS_PER_SESSION_MAX INT     DEFAULT 15,
            ORDERS_PER_BATCH       INT     DEFAULT 5,
            ITEMS_PER_ORDER_MIN    INT     DEFAULT 1,
            ITEMS_PER_ORDER_MAX    INT     DEFAULT 5,
            IS_ENABLED             BOOLEAN DEFAULT TRUE,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()

    session.sql(f"""
        MERGE INTO {db}.{admin}.GENERATION_CONFIG t
        USING (SELECT 1 AS ID) s ON t.ID = s.ID
        WHEN NOT MATCHED THEN INSERT (ID) VALUES (1)
    """).collect()

    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {db}.{admin}.GENERATION_STATE (
            ID INT PRIMARY KEY DEFAULT 1,
            LAST_SESSION_ID          INT DEFAULT 0,
            LAST_EVENT_ID            INT DEFAULT 0,
            LAST_ORDER_ID            INT DEFAULT 0,
            LAST_ORDER_ITEM_ID       INT DEFAULT 0,
            LAST_BATCH_TS            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            TOTAL_SESSIONS_GENERATED INT DEFAULT 0,
            TOTAL_EVENTS_GENERATED   INT DEFAULT 0,
            TOTAL_ORDERS_GENERATED   INT DEFAULT 0,
            TOTAL_ORDER_ITEMS_GENERATED INT DEFAULT 0,
            BATCHES_RUN              INT DEFAULT 0,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
    """).collect()

    session.sql(f"""
        MERGE INTO {db}.{admin}.GENERATION_STATE t
        USING (SELECT 1 AS ID) s ON t.ID = s.ID
        WHEN NOT MATCHED THEN INSERT (ID) VALUES (1)
    """).collect()

    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {db}.{admin}.GENERATION_LOG (
            LOG_ID         INT AUTOINCREMENT,
            BATCH_TS       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            SESSIONS_GENERATED   INT,
            EVENTS_GENERATED     INT,
            ORDERS_GENERATED     INT,
            ORDER_ITEMS_GENERATED INT,
            DURATION_MS          INT,
            STATUS               VARCHAR(20),
            ERROR_MESSAGE        VARCHAR(10000),
            PRIMARY KEY (LOG_ID)
        )
    """).collect()


def seed_state_from_existing_data(session, env: str = "DEV") -> dict:
    """Set ID counters in GENERATION_STATE from MAX(id) in source tables.

    This ensures the generator picks up where the NB 00 bulk load left off.
    Returns a dict of the seeded counters.
    """
    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    admin = cfg["admin_schema"]

    def _max_id(table: str, col: str, prefix: str) -> int:
        rows = session.sql(f"""
            SELECT MAX(REPLACE({col}, '{prefix}', '')::INT) AS MAX_ID
            FROM {db}.{src}.{table}
        """).collect()
        return rows[0]["MAX_ID"] or 0

    counters = {
        "LAST_SESSION_ID":    _max_id("SESSIONS", "SESSION_ID", "sess_"),
        "LAST_EVENT_ID":      _max_id("EVENTS", "EVENT_ID", "evt_"),
        "LAST_ORDER_ID":      _max_id("ORDERS", "ORDER_ID", "ord_"),
        "LAST_ORDER_ITEM_ID": _max_id("ORDER_ITEMS", "ORDER_ITEM_ID", "oi_"),
    }

    session.sql(f"""
        UPDATE {db}.{admin}.GENERATION_STATE SET
            LAST_SESSION_ID    = {counters['LAST_SESSION_ID']},
            LAST_EVENT_ID      = {counters['LAST_EVENT_ID']},
            LAST_ORDER_ID      = {counters['LAST_ORDER_ID']},
            LAST_ORDER_ITEM_ID = {counters['LAST_ORDER_ITEM_ID']},
            UPDATED_AT = CURRENT_TIMESTAMP()
        WHERE ID = 1
    """).collect()

    return counters


# ---------------------------------------------------------------------------
# Python generator function (runs locally or inside stored procedure)
# ---------------------------------------------------------------------------

def generate_batch(session, env: str = "DEV") -> dict:
    """Generate one batch of incremental clickstream data.

    Reads batch sizes from GENERATION_CONFIG, generates synthetic data,
    inserts into source tables, updates state, and logs the result.
    """
    import random
    from datetime import datetime, timedelta

    cfg = get_config(env)
    db = cfg["database"]
    src = cfg["source_schema"]
    admin = cfg["admin_schema"]

    start_time = datetime.now()

    try:
        config_row = session.sql(
            f"SELECT * FROM {db}.{admin}.GENERATION_CONFIG WHERE ID = 1"
        ).collect()[0]

        if not config_row["IS_ENABLED"]:
            return {"status": "disabled"}

        state = session.sql(
            f"SELECT * FROM {db}.{admin}.GENERATION_STATE WHERE ID = 1"
        ).collect()[0]

        visitors = [r["VISITOR_ID"] for r in session.sql(
            f"SELECT VISITOR_ID FROM {db}.{src}.VISITORS"
        ).collect()]
        users = [r["USER_ID"] for r in session.sql(
            f"SELECT USER_ID FROM {db}.{src}.USERS"
        ).collect()]
        products = [r["PRODUCT_ID"] for r in session.sql(
            f"SELECT PRODUCT_ID FROM {db}.{src}.PRODUCTS"
        ).collect()]
        product_suppliers = [
            (r["PRODUCT_ID"], r["SUPPLIER_ID"])
            for r in session.sql(
                f"SELECT PRODUCT_ID, SUPPLIER_ID FROM {db}.{src}.PRODUCT_SUPPLIER"
            ).collect()
        ]

        if not visitors or not users or not products or not product_suppliers:
            return {"status": "error", "message": "Missing reference data"}

        session_id = state["LAST_SESSION_ID"]
        event_id = state["LAST_EVENT_ID"]
        order_id = state["LAST_ORDER_ID"]
        order_item_id = state["LAST_ORDER_ITEM_ID"]

        batch_ts = datetime.now()
        batch_start = state["LAST_BATCH_TS"] or (batch_ts - timedelta(hours=1))

        new_sessions = []
        new_events = []

        event_types = [
            "Product Viewed", "Product Clicked", "Product Added",
            "Cart Viewed", "Checkout Started", "Order Completed",
        ]
        event_weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]

        for _ in range(config_row["SESSIONS_PER_BATCH"]):
            session_id += 1
            sess_id = f"sess_{session_id:08d}"
            visitor_id = random.choice(visitors)
            user_id = random.choice(users) if random.random() < 0.6 else None

            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            device_type = random.choice(["mobile", "desktop", "tablet"])

            num_events = random.randint(
                config_row["EVENTS_PER_SESSION_MIN"],
                config_row["EVENTS_PER_SESSION_MAX"],
            )
            cart_add_cnt = 0
            cart_value = 0.0
            is_converted = False
            order_value = 0.0
            event_time = sess_start

            for i in range(num_events):
                event_id += 1
                et = random.choices(event_types, weights=event_weights)[0]
                product_id = random.choice(products)

                if "Added" in et:
                    cart_add_cnt += 1
                    cart_value += random.uniform(20, 100)
                if et == "Order Completed":
                    is_converted = True
                    order_value = cart_value * 0.8

                new_events.append({
                    "EVENT_ID": f"evt_{event_id:010d}",
                    "VISITOR_ID": visitor_id,
                    "USER_ID": user_id,
                    "SESSION_ID": sess_id,
                    "EVENT_TS": event_time,
                    "EVENT_TYPE": et.split()[0],
                    "EVENT_NAME": et,
                    "PRODUCT_ID": product_id if "Product" in et else None,
                    "CATEGORY_ID": f"cat_{random.randint(1,13):02d}" if "Product" in et else None,
                    "PAGE_URL": f"/products/{product_id}",
                    "RECEIVED_TS": event_time + timedelta(milliseconds=random.randint(100, 500)),
                })
                event_time += timedelta(seconds=random.randint(5, 120))

            new_sessions.append({
                "SESSION_ID": sess_id,
                "VISITOR_ID": visitor_id,
                "USER_ID": user_id,
                "SESSION_START_TS": sess_start,
                "SESSION_END_TS": sess_start + timedelta(seconds=duration),
                "DURATION_SEC": duration,
                "EVENT_CNT": num_events,
                "PAGE_VIEW_CNT": sum(1 for e in new_events[-num_events:] if "Viewed" in e["EVENT_NAME"]),
                "PRODUCT_VIEW_DCNT": len(set(
                    e["PRODUCT_ID"] for e in new_events[-num_events:] if e["PRODUCT_ID"]
                )),
                "CART_ADD_CNT": cart_add_cnt,
                "CART_VALUE_SUM": round(cart_value, 2),
                "IS_CONVERTED": is_converted,
                "ORDER_VALUE_SUM": round(order_value, 2),
                "DEVICE_TYPE": device_type,
                "UTM_SOURCE": random.choice(["google", "direct", "facebook", "email", None]),
                "LANDING_PAGE_URL": f"/products/{random.choice(products)}",
            })

        new_orders = []
        new_order_items = []

        for _ in range(config_row["ORDERS_PER_BATCH"]):
            order_id += 1
            ord_id = f"ord_{order_id:08d}"
            user_id = random.choice(users)

            delta = max(1, (batch_ts - batch_start).total_seconds())
            order_ts = batch_start + timedelta(seconds=random.uniform(0, delta))

            num_items = random.randint(
                config_row["ITEMS_PER_ORDER_MIN"],
                config_row["ITEMS_PER_ORDER_MAX"],
            )
            subtotal = 0.0

            for _ in range(num_items):
                order_item_id += 1
                pid, sid = random.choice(product_suppliers)
                qty = random.randint(1, 3)
                price = round(random.uniform(10, 200), 2)
                disc = round(price * random.uniform(0, 0.2), 2) if random.random() < 0.3 else 0.0
                item_total = round(qty * (price - disc), 2)
                subtotal += item_total

                new_order_items.append({
                    "ORDER_ITEM_ID": f"oi_{order_item_id:010d}",
                    "ORDER_ID": ord_id,
                    "PRODUCT_ID": pid,
                    "SUPPLIER_ID": sid,
                    "QUANTITY": qty,
                    "UNIT_PRICE_AMT": price,
                    "DISCOUNT_AMT": disc,
                    "TOTAL_AMT": item_total,
                })

            tax = round(subtotal * 0.08, 2)
            ship = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
            disc = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0.0

            new_orders.append({
                "ORDER_ID": ord_id,
                "USER_ID": user_id,
                "ORDER_TS": order_ts,
                "STATUS": random.choice(["confirmed", "shipped", "delivered"]),
                "SUBTOTAL_AMT": round(subtotal, 2),
                "TAX_AMT": tax,
                "SHIPPING_AMT": ship,
                "DISCOUNT_AMT": disc,
                "TOTAL_AMT": round(subtotal + tax + ship - disc, 2),
                "ITEM_CNT": num_items,
                "PAYMENT_METHOD": random.choice(["credit_card", "paypal", "apple_pay"]),
                "CREATED_TS": order_ts,
                "UPDATED_TS": order_ts,
            })

        # Insert via Snowpark DataFrames
        import pandas as pd

        if new_sessions:
            session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table(
                f"{db}.{src}.SESSIONS"
            )
        if new_events:
            session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table(
                f"{db}.{src}.EVENTS"
            )
        if new_orders:
            session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table(
                f"{db}.{src}.ORDERS"
            )
        if new_order_items:
            session.create_dataframe(pd.DataFrame(new_order_items)).write.mode("append").save_as_table(
                f"{db}.{src}.ORDER_ITEMS"
            )

        # Update state
        session.sql(f"""
            UPDATE {db}.{admin}.GENERATION_STATE SET
                LAST_SESSION_ID    = {session_id},
                LAST_EVENT_ID      = {event_id},
                LAST_ORDER_ID      = {order_id},
                LAST_ORDER_ITEM_ID = {order_item_id},
                LAST_BATCH_TS      = '{batch_ts.strftime('%Y-%m-%d %H:%M:%S')}',
                TOTAL_SESSIONS_GENERATED    = TOTAL_SESSIONS_GENERATED + {len(new_sessions)},
                TOTAL_EVENTS_GENERATED      = TOTAL_EVENTS_GENERATED + {len(new_events)},
                TOTAL_ORDERS_GENERATED      = TOTAL_ORDERS_GENERATED + {len(new_orders)},
                TOTAL_ORDER_ITEMS_GENERATED = TOTAL_ORDER_ITEMS_GENERATED + {len(new_order_items)},
                BATCHES_RUN = BATCHES_RUN + 1,
                UPDATED_AT  = CURRENT_TIMESTAMP()
            WHERE ID = 1
        """).collect()

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        session.sql(f"""
            INSERT INTO {db}.{admin}.GENERATION_LOG
            (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED,
             ORDER_ITEMS_GENERATED, DURATION_MS, STATUS)
            VALUES ({len(new_sessions)}, {len(new_events)},
                    {len(new_orders)}, {len(new_order_items)},
                    {duration_ms}, 'SUCCESS')
        """).collect()

        return {
            "status": "success",
            "sessions": len(new_sessions),
            "events": len(new_events),
            "orders": len(new_orders),
            "order_items": len(new_order_items),
            "duration_ms": duration_ms,
        }

    except Exception as e:
        error_msg = str(e).replace("'", "''")[:10000]
        try:
            session.sql(f"""
                INSERT INTO {db}.{admin}.GENERATION_LOG
                (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED,
                 ORDER_ITEMS_GENERATED, DURATION_MS, STATUS, ERROR_MESSAGE)
                VALUES (0, 0, 0, 0, 0, 'ERROR', '{error_msg}')
            """).collect()
        except Exception:
            pass
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Stored Procedure deployment
# ---------------------------------------------------------------------------

_SPROC_BODY = r'''
import random
from datetime import datetime, timedelta
from snowflake.snowpark import Session

def generate_batch(session: Session) -> dict:
    start_time = datetime.now()
    DB = "{database}"
    SRC = "{source_schema}"
    ADMIN = "{admin_schema}"

    try:
        config_row = session.sql(
            f"SELECT * FROM {DB}.{ADMIN}.GENERATION_CONFIG WHERE ID = 1"
        ).collect()[0]
        if not config_row["IS_ENABLED"]:
            return {{"status": "disabled"}}

        state = session.sql(
            f"SELECT * FROM {DB}.{ADMIN}.GENERATION_STATE WHERE ID = 1"
        ).collect()[0]

        visitors = [r["VISITOR_ID"] for r in session.sql(f"SELECT VISITOR_ID FROM {DB}.{SRC}.VISITORS").collect()]
        users = [r["USER_ID"] for r in session.sql(f"SELECT USER_ID FROM {DB}.{SRC}.USERS").collect()]
        products = [r["PRODUCT_ID"] for r in session.sql(f"SELECT PRODUCT_ID FROM {DB}.{SRC}.PRODUCTS").collect()]
        product_suppliers = [(r["PRODUCT_ID"], r["SUPPLIER_ID"]) for r in session.sql(f"SELECT PRODUCT_ID, SUPPLIER_ID FROM {DB}.{SRC}.PRODUCT_SUPPLIER").collect()]

        if not visitors or not users or not products or not product_suppliers:
            return {{"status": "error", "message": "Missing reference data"}}

        session_id = state["LAST_SESSION_ID"]
        event_id = state["LAST_EVENT_ID"]
        order_id = state["LAST_ORDER_ID"]
        order_item_id = state["LAST_ORDER_ITEM_ID"]
        batch_ts = datetime.now()
        batch_start = state["LAST_BATCH_TS"] or (batch_ts - timedelta(hours=1))

        new_sessions, new_events = [], []
        event_types = ["Product Viewed","Product Clicked","Product Added","Cart Viewed","Checkout Started","Order Completed"]
        event_weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]

        for _ in range(config_row["SESSIONS_PER_BATCH"]):
            session_id += 1
            sess_id = f"sess_{{session_id:08d}}"
            visitor_id = random.choice(visitors)
            user_id = random.choice(users) if random.random() < 0.6 else None
            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            device_type = random.choice(["mobile", "desktop", "tablet"])
            num_events = random.randint(config_row["EVENTS_PER_SESSION_MIN"], config_row["EVENTS_PER_SESSION_MAX"])
            cart_add_cnt, cart_value, is_converted, order_value = 0, 0.0, False, 0.0
            event_time = sess_start

            for i in range(num_events):
                event_id += 1
                et = random.choices(event_types, weights=event_weights)[0]
                pid = random.choice(products)
                if "Added" in et: cart_add_cnt += 1; cart_value += random.uniform(20, 100)
                if et == "Order Completed": is_converted = True; order_value = cart_value * 0.8
                new_events.append({{"EVENT_ID": f"evt_{{event_id:010d}}", "VISITOR_ID": visitor_id, "USER_ID": user_id, "SESSION_ID": sess_id, "EVENT_TS": event_time, "EVENT_TYPE": et.split()[0], "EVENT_NAME": et, "PRODUCT_ID": pid if "Product" in et else None, "CATEGORY_ID": f"cat_{{random.randint(1,13):02d}}" if "Product" in et else None, "PAGE_URL": f"/products/{{pid}}", "RECEIVED_TS": event_time + timedelta(milliseconds=random.randint(100, 500))}})
                event_time += timedelta(seconds=random.randint(5, 120))

            new_sessions.append({{"SESSION_ID": sess_id, "VISITOR_ID": visitor_id, "USER_ID": user_id, "SESSION_START_TS": sess_start, "SESSION_END_TS": sess_start + timedelta(seconds=duration), "DURATION_SEC": duration, "EVENT_CNT": num_events, "PAGE_VIEW_CNT": sum(1 for e in new_events[-num_events:] if "Viewed" in e["EVENT_NAME"]), "PRODUCT_VIEW_DCNT": len(set(e["PRODUCT_ID"] for e in new_events[-num_events:] if e["PRODUCT_ID"])), "CART_ADD_CNT": cart_add_cnt, "CART_VALUE_SUM": round(cart_value, 2), "IS_CONVERTED": is_converted, "ORDER_VALUE_SUM": round(order_value, 2), "DEVICE_TYPE": device_type, "UTM_SOURCE": random.choice(["google","direct","facebook","email",None]), "LANDING_PAGE_URL": f"/products/{{random.choice(products)}}"}})

        new_orders, new_order_items = [], []
        for _ in range(config_row["ORDERS_PER_BATCH"]):
            order_id += 1
            ord_id = f"ord_{{order_id:08d}}"
            uid = random.choice(users)
            delta = max(1, (batch_ts - batch_start).total_seconds())
            order_ts = batch_start + timedelta(seconds=random.uniform(0, delta))
            num_items = random.randint(config_row["ITEMS_PER_ORDER_MIN"], config_row["ITEMS_PER_ORDER_MAX"])
            subtotal = 0.0
            for _ in range(num_items):
                order_item_id += 1
                p, s = random.choice(product_suppliers)
                qty = random.randint(1, 3); price = round(random.uniform(10, 200), 2)
                d = round(price * random.uniform(0, 0.2), 2) if random.random() < 0.3 else 0.0
                it = round(qty * (price - d), 2); subtotal += it
                new_order_items.append({{"ORDER_ITEM_ID": f"oi_{{order_item_id:010d}}", "ORDER_ID": ord_id, "PRODUCT_ID": p, "SUPPLIER_ID": s, "QUANTITY": qty, "UNIT_PRICE_AMT": price, "DISCOUNT_AMT": d, "TOTAL_AMT": it}})
            tax = round(subtotal * 0.08, 2); ship = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
            disc = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0.0
            new_orders.append({{"ORDER_ID": ord_id, "USER_ID": uid, "ORDER_TS": order_ts, "STATUS": random.choice(["confirmed","shipped","delivered"]), "SUBTOTAL_AMT": round(subtotal,2), "TAX_AMT": tax, "SHIPPING_AMT": ship, "DISCOUNT_AMT": disc, "TOTAL_AMT": round(subtotal+tax+ship-disc,2), "ITEM_CNT": num_items, "PAYMENT_METHOD": random.choice(["credit_card","paypal","apple_pay"]), "CREATED_TS": order_ts, "UPDATED_TS": order_ts}})

        import pandas as pd
        if new_sessions:  session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table(f"{{DB}}.{{SRC}}.SESSIONS")
        if new_events:    session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table(f"{{DB}}.{{SRC}}.EVENTS")
        if new_orders:    session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table(f"{{DB}}.{{SRC}}.ORDERS")
        if new_order_items: session.create_dataframe(pd.DataFrame(new_order_items)).write.mode("append").save_as_table(f"{{DB}}.{{SRC}}.ORDER_ITEMS")

        session.sql(f"UPDATE {{DB}}.{{ADMIN}}.GENERATION_STATE SET LAST_SESSION_ID={{session_id}}, LAST_EVENT_ID={{event_id}}, LAST_ORDER_ID={{order_id}}, LAST_ORDER_ITEM_ID={{order_item_id}}, LAST_BATCH_TS='{{batch_ts.strftime('%Y-%m-%d %H:%M:%S')}}', TOTAL_SESSIONS_GENERATED=TOTAL_SESSIONS_GENERATED+{{len(new_sessions)}}, TOTAL_EVENTS_GENERATED=TOTAL_EVENTS_GENERATED+{{len(new_events)}}, TOTAL_ORDERS_GENERATED=TOTAL_ORDERS_GENERATED+{{len(new_orders)}}, TOTAL_ORDER_ITEMS_GENERATED=TOTAL_ORDER_ITEMS_GENERATED+{{len(new_order_items)}}, BATCHES_RUN=BATCHES_RUN+1, UPDATED_AT=CURRENT_TIMESTAMP() WHERE ID=1").collect()

        dur = int((datetime.now() - start_time).total_seconds() * 1000)
        session.sql(f"INSERT INTO {{DB}}.{{ADMIN}}.GENERATION_LOG (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS) VALUES ({{len(new_sessions)}}, {{len(new_events)}}, {{len(new_orders)}}, {{len(new_order_items)}}, {{dur}}, 'SUCCESS')").collect()

        return {{"status": "success", "sessions": len(new_sessions), "events": len(new_events), "orders": len(new_orders), "order_items": len(new_order_items), "duration_ms": dur}}

    except Exception as e:
        err = str(e).replace("'", "''")[:10000]
        try:
            session.sql(f"INSERT INTO {{DB}}.{{ADMIN}}.GENERATION_LOG (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS, ERROR_MESSAGE) VALUES (0,0,0,0,0,'ERROR','{{err}}')").collect()
        except Exception:
            pass
        return {{"status": "error", "message": str(e)}}
'''


def deploy_stored_procedure(session, env: str = "DEV") -> None:
    """Create the GENERATE_INCREMENTAL_BATCH stored procedure."""
    cfg = get_config(env)
    body = (_SPROC_BODY
            .replace("{database}", cfg["database"])
            .replace("{source_schema}", cfg["source_schema"])
            .replace("{admin_schema}", cfg["admin_schema"]))
    # Template uses {{/}} for literal braces (format-string convention)
    # but .replace() doesn't unescape them — do it explicitly.
    body = body.replace("{{", "{").replace("}}", "}")
    fqn = f"{cfg['database']}.{cfg['admin_schema']}.GENERATE_INCREMENTAL_BATCH"
    session.sql(f"""
        CREATE OR REPLACE PROCEDURE {fqn}()
        RETURNS VARIANT
        LANGUAGE PYTHON
        RUNTIME_VERSION = '3.11'
        PACKAGES = ('snowflake-snowpark-python', 'pandas')
        HANDLER = 'generate_batch'
        AS $${body}$$
    """).collect()


def deploy_task(session, env: str = "DEV", schedule: str = "1 MINUTE") -> None:
    """Create the INCREMENTAL_DATA_TASK (SUSPENDED by default).

    Uses DROP + CREATE (not CREATE OR REPLACE) to ensure the task
    picks up the latest procedure definition cleanly after any
    procedure redeployment.
    """
    cfg = get_config(env)
    db = cfg["database"]
    admin = cfg["admin_schema"]
    wh = cfg["warehouse"]
    fqn_sproc = f"{db}.{admin}.GENERATE_INCREMENTAL_BATCH"
    fqn_task = f"{db}.{admin}.INCREMENTAL_DATA_TASK"

    try:
        session.sql(
            f"ALTER TASK {fqn_task} SUSPEND"
        ).collect()
    except Exception:
        pass
    session.sql(f"DROP TASK IF EXISTS {fqn_task}").collect()

    session.sql(f"""
        CREATE TASK {fqn_task}
            WAREHOUSE = {wh}
            SCHEDULE  = '{schedule}'
            ALLOW_OVERLAPPING_EXECUTION = FALSE
            COMMENT   = 'Generates incremental clickstream data'
        AS
            CALL {fqn_sproc}()
    """).collect()


# ---------------------------------------------------------------------------
# Scale helpers
# ---------------------------------------------------------------------------

def set_scale(session, env: str = "DEV", *,
              sessions_per_batch: int | None = None,
              orders_per_batch: int | None = None,
              events_per_session_min: int | None = None,
              events_per_session_max: int | None = None) -> None:
    """Update GENERATION_CONFIG with new batch sizes (takes effect next cycle)."""
    cfg = get_config(env)
    fqn = f"{cfg['database']}.{cfg['admin_schema']}.GENERATION_CONFIG"
    sets = []
    if sessions_per_batch is not None:
        sets.append(f"SESSIONS_PER_BATCH = {sessions_per_batch}")
    if orders_per_batch is not None:
        sets.append(f"ORDERS_PER_BATCH = {orders_per_batch}")
    if events_per_session_min is not None:
        sets.append(f"EVENTS_PER_SESSION_MIN = {events_per_session_min}")
    if events_per_session_max is not None:
        sets.append(f"EVENTS_PER_SESSION_MAX = {events_per_session_max}")
    if sets:
        sets.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        session.sql(f"UPDATE {fqn} SET {', '.join(sets)} WHERE ID = 1").collect()


def resume_task(session, env: str = "DEV") -> None:
    cfg = get_config(env)
    fqn = f"{cfg['database']}.{cfg['admin_schema']}.INCREMENTAL_DATA_TASK"
    session.sql(f"ALTER TASK {fqn} RESUME").collect()


def suspend_task(session, env: str = "DEV") -> None:
    cfg = get_config(env)
    fqn = f"{cfg['database']}.{cfg['admin_schema']}.INCREMENTAL_DATA_TASK"
    session.sql(f"ALTER TASK {fqn} SUSPEND").collect()

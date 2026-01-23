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
    """Generate incremental batch of sessions, events, orders matching bulk loader schema."""
    start_time = datetime.now()
    admin_schema = "{ADMIN_SCHEMA}"
    
    try:
        config = session.sql(f"SELECT * FROM {admin_schema}.GENERATION_CONFIG WHERE ID = 1").collect()[0]
        if not config['IS_ENABLED']:
            return {"status": "disabled"}
        
        data_schema = config['DATA_SCHEMA']
        state = session.sql(f"SELECT * FROM {admin_schema}.GENERATION_STATE WHERE ID = 1").collect()[0]
        
        # Get reference data
        visitors = [r['VISITOR_ID'] for r in session.sql(f"SELECT VISITOR_ID FROM {data_schema}.VISITORS").collect()]
        users = [r['USER_ID'] for r in session.sql(f"SELECT USER_ID FROM {data_schema}.USERS").collect()]
        products = [r['PRODUCT_ID'] for r in session.sql(f"SELECT PRODUCT_ID FROM {data_schema}.PRODUCTS").collect()]
        
        if not all([visitors, users, products]):
            return {"status": "error", "message": "Missing reference data"}
        
        session_id = state['LAST_SESSION_ID']
        event_id = state['LAST_EVENT_ID']
        order_id = state['LAST_ORDER_ID']
        order_item_id = state['LAST_ORDER_ITEM_ID']
        
        batch_ts = datetime.now()
        batch_start = state['LAST_BATCH_TS'] or (batch_ts - timedelta(hours=1))
        
        new_sessions, new_events = [], []
        devices = ['mobile', 'desktop', 'tablet']
        browsers = ['Chrome', 'Safari', 'Firefox', 'Edge']
        oss = ['iOS', 'Android', 'Windows', 'macOS']
        countries = ['US', 'UK', 'CA', 'AU', 'DE']
        utm_sources = ['google', 'direct', 'facebook', 'email']
        utm_mediums = ['organic', 'cpc', 'social', 'email']
        event_types = ['Product Viewed', 'Product Clicked', 'Product Added', 'Cart Viewed', 'Checkout Started', 'Order Completed']
        event_weights = [0.40, 0.25, 0.15, 0.10, 0.05, 0.05]
        
        for _ in range(config['SESSIONS_PER_BATCH']):
            session_id += 1
            sess_id = f"sess_{session_id:08d}"
            visitor_id = random.choice(visitors)
            user_id = random.choice(users) if random.random() < 0.6 else None
            
            delta = max(1, (batch_ts - batch_start).total_seconds())
            sess_start = batch_start + timedelta(seconds=random.uniform(0, delta))
            duration = random.randint(30, 1800)
            sess_end = sess_start + timedelta(seconds=duration)
            device = random.choice(devices)
            
            num_events = random.randint(config['EVENTS_PER_SESSION_MIN'], config['EVENTS_PER_SESSION_MAX'])
            is_converted = random.random() < 0.03
            event_time = sess_start
            
            # Generate events for this session - matching EVENTS table schema
            for i in range(num_events):
                event_id += 1
                etype = random.choices(event_types, weights=event_weights)[0]
                pid = random.choice(products) if 'Product' in etype else None
                
                new_events.append({
                    'EVENT_ID': f"evt_{event_id:010d}",
                    'SESSION_ID': sess_id,
                    'VISITOR_ID': visitor_id,
                    'USER_ID': user_id,
                    'EVENT_TYPE': etype,
                    'EVENT_TS': event_time,
                    'PAGE_URL': f"/products/{pid}" if pid else "/browse",
                    'PRODUCT_ID': pid,
                    'PRODUCT_QUANTITY': random.randint(1, 3) if 'Added' in etype else None,
                    'SEARCH_QUERY': None,
                    'PROPERTIES': None,  # VARIANT - leave null for incremental
                })
                event_time += timedelta(seconds=random.randint(5, 120))
            
            # SESSIONS table schema: SESSION_ID, VISITOR_ID, USER_ID, STARTED_TS, ENDED_TS, 
            # DURATION_SECONDS, PAGE_VIEWS, DEVICE_TYPE, BROWSER, OS, COUNTRY, 
            # UTM_SOURCE, UTM_MEDIUM, UTM_CAMPAIGN, IS_CONVERTED
            new_sessions.append({
                'SESSION_ID': sess_id,
                'VISITOR_ID': visitor_id,
                'USER_ID': user_id,
                'STARTED_TS': sess_start,
                'ENDED_TS': sess_end,
                'DURATION_SECONDS': duration,
                'PAGE_VIEWS': num_events,
                'DEVICE_TYPE': device,
                'BROWSER': random.choice(browsers),
                'OS': random.choice(oss),
                'COUNTRY': random.choice(countries),
                'UTM_SOURCE': random.choice(utm_sources) if random.random() < 0.7 else None,
                'UTM_MEDIUM': random.choice(utm_mediums) if random.random() < 0.7 else None,
                'UTM_CAMPAIGN': f"campaign_{random.randint(1, 20)}" if random.random() < 0.3 else None,
                'IS_CONVERTED': is_converted,
            })
        
        # Generate orders - matching ORDERS and ORDER_ITEMS table schemas
        new_orders, new_items = [], []
        for _ in range(config['ORDERS_PER_BATCH']):
            order_id += 1
            oid = f"ord_{order_id:08d}"
            uid = random.choice(users)
            sid = f"sess_{random.randint(max(1, session_id - 50), session_id):08d}"
            delta = max(1, (batch_ts - batch_start).total_seconds())
            ots = batch_start + timedelta(seconds=random.uniform(0, delta))
            
            num_items = random.randint(config['ITEMS_PER_ORDER_MIN'], config['ITEMS_PER_ORDER_MAX'])
            subtotal = 0.0
            
            for _ in range(num_items):
                order_item_id += 1
                pid = random.choice(products)
                qty = random.randint(1, 3)
                price = round(random.uniform(10, 200), 2)
                total = round(qty * price, 2)
                subtotal += total
                
                # ORDER_ITEMS schema: ORDER_ITEM_ID, ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE, TOTAL_PRICE
                new_items.append({
                    'ORDER_ITEM_ID': f"item_{order_item_id:08d}",
                    'ORDER_ID': oid,
                    'PRODUCT_ID': pid,
                    'QUANTITY': qty,
                    'UNIT_PRICE': price,
                    'TOTAL_PRICE': total,
                })
            
            tax = round(subtotal * 0.08, 2)
            ship = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
            
            # ORDERS schema: ORDER_ID, USER_ID, SESSION_ID, ORDER_TS, STATUS, SUBTOTAL, TAX, SHIPPING, TOTAL,
            # SHIPPING_ADDRESS_CITY, SHIPPING_ADDRESS_STATE, SHIPPING_ADDRESS_COUNTRY, PAYMENT_METHOD
            new_orders.append({
                'ORDER_ID': oid,
                'USER_ID': uid,
                'SESSION_ID': sid,
                'ORDER_TS': ots,
                'STATUS': random.choice(['pending', 'confirmed', 'shipped']),
                'SUBTOTAL': round(subtotal, 2),
                'TAX': tax,
                'SHIPPING': ship,
                'TOTAL': round(subtotal + tax + ship, 2),
                'SHIPPING_ADDRESS_CITY': random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston']),
                'SHIPPING_ADDRESS_STATE': random.choice(['NY', 'CA', 'IL', 'TX']),
                'SHIPPING_ADDRESS_COUNTRY': 'US',
                'PAYMENT_METHOD': random.choice(['credit_card', 'paypal', 'apple_pay']),
            })
        
        # Insert data
        if new_sessions:
            session.create_dataframe(pd.DataFrame(new_sessions)).write.mode("append").save_as_table(f"{data_schema}.SESSIONS")
        if new_events:
            session.create_dataframe(pd.DataFrame(new_events)).write.mode("append").save_as_table(f"{data_schema}.EVENTS")
        if new_orders:
            session.create_dataframe(pd.DataFrame(new_orders)).write.mode("append").save_as_table(f"{data_schema}.ORDERS")
        if new_items:
            session.create_dataframe(pd.DataFrame(new_items)).write.mode("append").save_as_table(f"{data_schema}.ORDER_ITEMS")
        
        # Update state
        session.sql(f"""
            UPDATE {admin_schema}.GENERATION_STATE 
            SET LAST_SESSION_ID={session_id}, 
                LAST_EVENT_ID={event_id}, 
                LAST_ORDER_ID={order_id}, 
                LAST_ORDER_ITEM_ID={order_item_id}, 
                LAST_BATCH_TS='{batch_ts.strftime('%Y-%m-%d %H:%M:%S')}', 
                TOTAL_SESSIONS_GENERATED=TOTAL_SESSIONS_GENERATED+{len(new_sessions)}, 
                TOTAL_EVENTS_GENERATED=TOTAL_EVENTS_GENERATED+{len(new_events)}, 
                TOTAL_ORDERS_GENERATED=TOTAL_ORDERS_GENERATED+{len(new_orders)}, 
                BATCHES_RUN=BATCHES_RUN+1 
            WHERE ID=1
        """).collect()
        
        dur = int((datetime.now() - start_time).total_seconds() * 1000)
        session.sql(f"""
            INSERT INTO {admin_schema}.GENERATION_LOG 
            (SESSIONS_GENERATED, EVENTS_GENERATED, ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS) 
            VALUES ({len(new_sessions)}, {len(new_events)}, {len(new_orders)}, {len(new_items)}, {dur}, 'SUCCESS')
        """).collect()
        
        return {
            "status": "success", 
            "sessions": len(new_sessions), 
            "events": len(new_events), 
            "orders": len(new_orders), 
            "items": len(new_items), 
            "duration_ms": dur
        }
    except Exception as e:
        try:
            session.sql(f"INSERT INTO {admin_schema}.GENERATION_LOG (STATUS, ERROR_MESSAGE) VALUES ('ERROR', '{str(e)[:1000]}')").collect()
        except:
            pass
        return {"status": "error", "message": str(e)}
$$;

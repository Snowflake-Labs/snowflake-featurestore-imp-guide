"""
Incremental data loader for continuous/streaming data generation.

This module supports:
1. State tracking (last IDs, timestamps)
2. Generating new data batches
3. Appending to existing tables
4. Integration with Snowflake Streams/Tasks

Use cases:
- Demonstrating Dynamic Table refresh behavior
- Simulating real-time data for Online Feature serving
- Testing Feature Store temporal features
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class IncrementalState:
    """
    Tracks the state of incremental data generation.
    
    Persisted to Snowflake so generation can resume after restarts.
    """
    # ID counters (last generated IDs)
    last_event_id: int = 0
    last_session_id: int = 0
    last_order_id: int = 0
    last_order_item_id: int = 0
    
    # Timestamp tracking
    last_batch_ts: datetime = field(default_factory=lambda: datetime.now() - timedelta(hours=1))
    
    # Statistics
    total_events_generated: int = 0
    total_sessions_generated: int = 0
    total_orders_generated: int = 0
    batches_run: int = 0
    
    STATE_TABLE = "INCREMENTAL_GENERATION_STATE"
    
    @classmethod
    def load_from_snowflake(cls, session) -> "IncrementalState":
        """Load state from Snowflake metadata table."""
        try:
            result = session.sql(f"""
                SELECT *
                FROM {cls.STATE_TABLE}
                WHERE ID = 1
            """).collect()
            
            if result:
                row = result[0].as_dict()
                return cls(
                    last_event_id=row.get("LAST_EVENT_ID", 0) or 0,
                    last_session_id=row.get("LAST_SESSION_ID", 0) or 0,
                    last_order_id=row.get("LAST_ORDER_ID", 0) or 0,
                    last_order_item_id=row.get("LAST_ORDER_ITEM_ID", 0) or 0,
                    last_batch_ts=row.get("LAST_BATCH_TS") or datetime.now() - timedelta(hours=1),
                    total_events_generated=row.get("TOTAL_EVENTS_GENERATED", 0) or 0,
                    total_sessions_generated=row.get("TOTAL_SESSIONS_GENERATED", 0) or 0,
                    total_orders_generated=row.get("TOTAL_ORDERS_GENERATED", 0) or 0,
                    batches_run=row.get("BATCHES_RUN", 0) or 0,
                )
        except Exception:
            pass  # Table doesn't exist yet
        
        return cls()
    
    def save_to_snowflake(self, session):
        """Save state to Snowflake."""
        # Create table if not exists
        session.sql(f"""
            CREATE TABLE IF NOT EXISTS {self.STATE_TABLE} (
                ID INT PRIMARY KEY,
                LAST_EVENT_ID INT,
                LAST_SESSION_ID INT,
                LAST_ORDER_ID INT,
                LAST_ORDER_ITEM_ID INT,
                LAST_BATCH_TS TIMESTAMP_NTZ,
                TOTAL_EVENTS_GENERATED INT,
                TOTAL_SESSIONS_GENERATED INT,
                TOTAL_ORDERS_GENERATED INT,
                BATCHES_RUN INT,
                UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
        """).collect()
        
        # Upsert state
        session.sql(f"""
            MERGE INTO {self.STATE_TABLE} t
            USING (SELECT 1 as ID) s ON t.ID = s.ID
            WHEN MATCHED THEN UPDATE SET
                LAST_EVENT_ID = {self.last_event_id},
                LAST_SESSION_ID = {self.last_session_id},
                LAST_ORDER_ID = {self.last_order_id},
                LAST_ORDER_ITEM_ID = {self.last_order_item_id},
                LAST_BATCH_TS = '{self.last_batch_ts.strftime('%Y-%m-%d %H:%M:%S')}',
                TOTAL_EVENTS_GENERATED = {self.total_events_generated},
                TOTAL_SESSIONS_GENERATED = {self.total_sessions_generated},
                TOTAL_ORDERS_GENERATED = {self.total_orders_generated},
                BATCHES_RUN = {self.batches_run},
                UPDATED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (
                ID, LAST_EVENT_ID, LAST_SESSION_ID, LAST_ORDER_ID, LAST_ORDER_ITEM_ID,
                LAST_BATCH_TS, TOTAL_EVENTS_GENERATED, TOTAL_SESSIONS_GENERATED,
                TOTAL_ORDERS_GENERATED, BATCHES_RUN
            ) VALUES (
                1, {self.last_event_id}, {self.last_session_id}, {self.last_order_id},
                {self.last_order_item_id}, '{self.last_batch_ts.strftime('%Y-%m-%d %H:%M:%S')}',
                {self.total_events_generated}, {self.total_sessions_generated},
                {self.total_orders_generated}, {self.batches_run}
            )
        """).collect()


@dataclass
class IncrementalConfig:
    """Configuration for incremental batch generation."""
    # Batch sizes
    new_sessions_per_batch: int = 50
    events_per_session_min: int = 3
    events_per_session_max: int = 15
    new_orders_per_batch: int = 5
    items_per_order_min: int = 1
    items_per_order_max: int = 5
    
    # Time window for new data (simulates "real-time")
    batch_time_window: timedelta = timedelta(hours=1)
    
    # Event type distribution
    event_type_weights: Dict[str, float] = field(default_factory=lambda: {
        "Product Viewed": 0.40,
        "Product Clicked": 0.25,
        "Product Added": 0.15,
        "Cart Viewed": 0.10,
        "Checkout Started": 0.05,
        "Order Completed": 0.05,
    })


class IncrementalLoader:
    """
    Incremental data loader for continuous data generation.
    
    Usage:
        loader = IncrementalLoader(session)
        
        # Generate a single batch of new data
        stats = loader.generate_batch()
        
        # Continuous generation (blocking)
        loader.run_continuous(interval_seconds=60, max_batches=100)
    """
    
    def __init__(
        self,
        session,
        config: IncrementalConfig = None,
        schema: str = "CLICKSTREAM_RAW",
    ):
        """
        Initialize incremental loader.
        
        Args:
            session: Snowpark Session
            config: IncrementalConfig (optional)
            schema: Schema containing the data tables
        """
        self.session = session
        self.config = config or IncrementalConfig()
        self.schema = schema
        self.state = IncrementalState.load_from_snowflake(session)
        
        # Cache existing reference data
        self._load_reference_data()
    
    def _load_reference_data(self):
        """Load existing visitors, users, products for FK references."""
        print("  Loading reference data...")
        
        self.visitors = [
            r["VISITOR_ID"] 
            for r in self.session.table(f"{self.schema}.VISITORS")
            .select("VISITOR_ID").collect()
        ]
        
        self.users = [
            r["USER_ID"]
            for r in self.session.table(f"{self.schema}.USERS")
            .select("USER_ID").collect()
        ]
        
        self.products = [
            r["PRODUCT_ID"]
            for r in self.session.table(f"{self.schema}.PRODUCTS")
            .select("PRODUCT_ID").collect()
        ]
        
        self.product_suppliers = [
            (r["PRODUCT_ID"], r["SUPPLIER_ID"])
            for r in self.session.table(f"{self.schema}.PRODUCT_SUPPLIER")
            .select("PRODUCT_ID", "SUPPLIER_ID").collect()
        ]
        
        print(f"    Loaded {len(self.visitors):,} visitors, {len(self.users):,} users, {len(self.products):,} products")
    
    def generate_batch(self) -> Dict[str, int]:
        """
        Generate a batch of new incremental data.
        
        Returns:
            Dict with counts of generated records per table
        """
        batch_start = self.state.last_batch_ts
        batch_end = datetime.now()
        
        print(f"\n  Generating batch {self.state.batches_run + 1}...")
        print(f"    Time window: {batch_start} to {batch_end}")
        
        new_data = {
            "SESSIONS": [],
            "EVENTS": [],
            "ORDERS": [],
            "ORDER_ITEMS": [],
        }
        
        # Generate new sessions and events
        for _ in range(self.config.new_sessions_per_batch):
            session_data, events = self._generate_session_with_events(batch_start, batch_end)
            new_data["SESSIONS"].append(session_data)
            new_data["EVENTS"].extend(events)
        
        # Generate new orders
        for _ in range(self.config.new_orders_per_batch):
            order_data, items = self._generate_order_with_items(batch_start, batch_end)
            new_data["ORDERS"].append(order_data)
            new_data["ORDER_ITEMS"].extend(items)
        
        # Append to Snowflake tables
        stats = {}
        for table_name, rows in new_data.items():
            if rows:
                df = self.session.create_dataframe(pd.DataFrame(rows))
                df.write.mode("append").save_as_table(f"{self.schema}.{table_name}")
                stats[table_name] = len(rows)
                print(f"    Appended {len(rows):,} rows to {table_name}")
        
        # Update state
        self.state.last_batch_ts = batch_end
        self.state.total_events_generated += stats.get("EVENTS", 0)
        self.state.total_sessions_generated += stats.get("SESSIONS", 0)
        self.state.total_orders_generated += stats.get("ORDERS", 0)
        self.state.batches_run += 1
        self.state.save_to_snowflake(self.session)
        
        return stats
    
    def _generate_session_with_events(
        self,
        batch_start: datetime,
        batch_end: datetime,
    ) -> Tuple[Dict, List[Dict]]:
        """Generate a session with its events (matches SESSIONS/EVENTS schema)."""
        self.state.last_session_id += 1
        session_id = f"sess_{self.state.last_session_id:08d}"
        
        # Pick visitor and optionally user
        visitor_id = random.choice(self.visitors)
        user_id = random.choice(self.users) if random.random() < 0.6 else None
        
        # Session timing
        delta = (batch_end - batch_start).total_seconds()
        session_start = batch_start + timedelta(seconds=random.uniform(0, max(1, delta)))
        duration = random.randint(30, 1800)  # 30 sec to 30 min
        session_end = session_start + timedelta(seconds=duration)
        
        # Device info
        device_type = random.choice(["mobile", "desktop", "tablet"])
        
        # Generate events for session
        events = []
        num_events = random.randint(
            self.config.events_per_session_min,
            self.config.events_per_session_max
        )
        
        event_time = session_start
        products_viewed = []
        categories_viewed = []
        cart_add_cnt = 0
        cart_value = 0.0
        is_converted = False
        order_value = 0.0
        landing_url = f"/products/{random.choice(self.products)}"
        exit_url = landing_url
        
        for i in range(num_events):
            self.state.last_event_id += 1
            event_id = f"evt_{self.state.last_event_id:010d}"
            
            # Select event type
            event_type = random.choices(
                list(self.config.event_type_weights.keys()),
                weights=list(self.config.event_type_weights.values()),
            )[0]
            
            # Product for event
            product_id = random.choice(self.products)
            category_id = f"cat_{random.randint(1, 15):02d}"  # Simplified
            
            if "Viewed" in event_type or "Clicked" in event_type:
                products_viewed.append(product_id)
                categories_viewed.append(category_id)
            
            if "Added" in event_type:
                cart_add_cnt += 1
                cart_value += random.uniform(20, 100)
            
            if event_type == "Order Completed":
                is_converted = True
                order_value = cart_value * 0.8  # Some items removed
            
            page_url = f"/products/{product_id}" if product_id else f"/page_{i}"
            exit_url = page_url
            
            # Event data matching EVENTS schema
            event_data = {
                "EVENT_ID": event_id,
                "VISITOR_ID": visitor_id,
                "USER_ID": user_id,
                "SESSION_ID": session_id,
                "EVENT_TS": event_time,
                "EVENT_TYPE": event_type.split()[0],  # "Product", "Cart", "Order", etc.
                "EVENT_NAME": event_type,
                "PRODUCT_ID": product_id if "Product" in event_type else None,
                "CATEGORY_ID": category_id if "Product" in event_type else None,
                "PAGE_URL": page_url,
                "PAGE_TITLE": f"Page {i}",
                "REFERRER_URL": exit_url if i > 0 else None,
                "PROPERTIES": "{}",
                "CONTEXT": f'{{"device_type": "{device_type}"}}',
                "RECEIVED_TS": event_time + timedelta(milliseconds=random.randint(100, 500)),
            }
            events.append(event_data)
            
            # Advance time
            event_time += timedelta(seconds=random.randint(5, 120))
        
        # Session data matching SESSIONS schema
        session_data = {
            "SESSION_ID": session_id,
            "VISITOR_ID": visitor_id,
            "USER_ID": user_id,
            "SESSION_START_TS": session_start,
            "SESSION_END_TS": session_end,
            "DURATION_SEC": duration,
            "EVENT_CNT": len(events),
            "PAGE_VIEW_CNT": sum(1 for e in events if "Viewed" in e["EVENT_NAME"]),
            "PRODUCT_VIEW_DCNT": len(set(products_viewed)),
            "CART_ADD_CNT": cart_add_cnt,
            "CART_VALUE_SUM": round(cart_value, 2),
            "IS_CONVERTED": is_converted,
            "ORDER_VALUE_SUM": round(order_value, 2),
            "DEVICE_TYPE": device_type,
            "LANDING_PAGE_URL": landing_url,
            "EXIT_PAGE_URL": exit_url,
            "PRODUCTS_VIEWED": str(list(set(products_viewed))),  # ARRAY as string
            "CATEGORIES_VIEWED": str(list(set(categories_viewed))),  # ARRAY as string
        }
        
        return session_data, events
    
    def _generate_order_with_items(
        self,
        batch_start: datetime,
        batch_end: datetime,
    ) -> Tuple[Dict, List[Dict]]:
        """Generate an order with its line items (matches ORDERS/ORDER_ITEMS schema)."""
        self.state.last_order_id += 1
        order_id = f"ord_{self.state.last_order_id:08d}"
        
        # Pick user
        user_id = random.choice(self.users)
        
        # Order timing
        delta = (batch_end - batch_start).total_seconds()
        order_ts = batch_start + timedelta(seconds=random.uniform(0, max(1, delta)))
        
        # Generate order items
        items = []
        num_items = random.randint(
            self.config.items_per_order_min,
            self.config.items_per_order_max
        )
        
        subtotal = 0.0
        for _ in range(num_items):
            self.state.last_order_item_id += 1
            item_id = f"oi_{self.state.last_order_item_id:010d}"
            
            # Pick product/supplier combination
            product_id, supplier_id = random.choice(self.product_suppliers)
            
            qty = random.randint(1, 3)
            unit_price = round(random.uniform(10, 200), 2)
            item_discount = round(unit_price * random.uniform(0, 0.2), 2) if random.random() < 0.3 else 0.0
            item_total = round(qty * (unit_price - item_discount), 2)
            subtotal += item_total
            
            # ORDER_ITEMS schema match
            item_data = {
                "ORDER_ITEM_ID": item_id,
                "ORDER_ID": order_id,
                "PRODUCT_ID": product_id,
                "SUPPLIER_ID": supplier_id,
                "QUANTITY": qty,
                "UNIT_PRICE_AMT": unit_price,
                "DISCOUNT_AMT": item_discount,
                "TOTAL_AMT": item_total,
            }
            items.append(item_data)
        
        # Calculate order totals
        tax_amt = round(subtotal * 0.08, 2)  # 8% tax
        shipping_amt = round(random.uniform(5, 15), 2) if subtotal < 100 else 0.0
        discount_amt = round(subtotal * 0.1, 2) if random.random() < 0.2 else 0.0
        total_amt = round(subtotal + tax_amt + shipping_amt - discount_amt, 2)
        
        # ORDERS schema match
        order_data = {
            "ORDER_ID": order_id,
            "USER_ID": user_id,
            "SESSION_ID": f"sess_{self.state.last_session_id:08d}",  # Link to a session
            "ORDER_TS": order_ts,
            "STATUS": random.choice(["pending", "confirmed", "shipped", "delivered"]),
            "SUBTOTAL_AMT": round(subtotal, 2),
            "TAX_AMT": tax_amt,
            "SHIPPING_AMT": shipping_amt,
            "DISCOUNT_AMT": discount_amt,
            "TOTAL_AMT": total_amt,
            "ITEM_CNT": num_items,
            "COUPON_CODE": f"SAVE{random.randint(10, 50)}" if discount_amt > 0 else None,
            "PAYMENT_METHOD": random.choice(["credit_card", "paypal", "apple_pay"]),
            "SHIPPING_ADDRESS": '{"city": "San Francisco", "state": "CA"}',
            "BILLING_ADDRESS": '{"city": "San Francisco", "state": "CA"}',
            "CREATED_TS": order_ts,
            "UPDATED_TS": order_ts,
        }
        
        return order_data, items
    
    def run_continuous(
        self,
        interval_seconds: int = 60,
        max_batches: int = None,
        until: datetime = None,
    ):
        """
        Run continuous batch generation.
        
        Args:
            interval_seconds: Seconds between batches
            max_batches: Stop after this many batches (None = infinite)
            until: Stop after this datetime
        """
        import time
        
        print(f"\n{'='*60}")
        print("  CONTINUOUS INCREMENTAL GENERATION")
        print(f"  Interval: {interval_seconds}s, Max batches: {max_batches or 'unlimited'}")
        print(f"{'='*60}")
        
        batch_count = 0
        
        try:
            while True:
                # Check stop conditions
                if max_batches and batch_count >= max_batches:
                    print("\n  Max batches reached. Stopping.")
                    break
                    
                if until and datetime.now() >= until:
                    print("\n  Time limit reached. Stopping.")
                    break
                
                # Generate batch
                stats = self.generate_batch()
                batch_count += 1
                
                print(f"\n  Batch {batch_count} complete. Waiting {interval_seconds}s...")
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\n  Interrupted by user. Stopping.")
        
        print(f"\n  Total batches: {batch_count}")
        print(f"  Total events generated: {self.state.total_events_generated:,}")

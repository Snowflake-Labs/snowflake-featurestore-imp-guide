"""
Event and Session table generators: SESSIONS, EVENTS
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DataConfig,
    EVENT_TYPES,
    DEVICE_TYPES,
    BROWSERS,
    OS_BY_DEVICE,
)
from utils import (
    generate_uuid,
    weighted_choice,
    sample_without_replacement,
    random_timestamp,
    random_timestamp_weighted,
    generate_session_timestamps,
    log_normal_value,
    to_array,
    to_object,
    generate_device_context,
    generate_event_properties,
    progress_bar,
)


# =============================================================================
# SESSIONS
# =============================================================================

def generate_sessions(
    config: DataConfig,
    visitors: List[Dict[str, Any]],
    users: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate SESSIONS table data.
    
    Sessions aggregate events for a visitor/user. Each visitor has
    multiple sessions over time.
    
    Returns list of dicts matching SESSIONS schema.
    """
    sessions = []
    
    # Create visitor -> user mapping
    visitor_to_user = {u["VISITOR_ID"]: u for u in users}
    
    # Calculate sessions per visitor
    total_sessions = config.num_sessions
    avg_sessions_per_visitor = total_sessions / len(visitors)
    
    session_id = 0
    
    for visitor in visitors:
        # Each visitor gets a random number of sessions (around average)
        num_visitor_sessions = max(1, int(random.gauss(avg_sessions_per_visitor, avg_sessions_per_visitor * 0.5)))
        
        # Get user if visitor is identified
        user = visitor_to_user.get(visitor["VISITOR_ID"])
        user_id = user["USER_ID"] if user else None
        
        # User becomes identified after some sessions
        identification_session = random.randint(0, max(0, num_visitor_sessions - 1)) if user else num_visitor_sessions
        
        for s in range(num_visitor_sessions):
            if session_id >= total_sessions:
                break
            
            # Session timing
            session_start = random_timestamp_weighted(
                visitor["FIRST_SEEN_TS"],
                visitor["LAST_SEEN_TS"],
                peak_hours=config.peak_hours,
                low_hours=config.low_hours,
            )
            
            # Session duration (log-normal, median ~3 minutes)
            duration_sec = int(log_normal_value(median=180, sigma=0.8))
            duration_sec = max(10, min(3600, duration_sec))  # 10 sec to 1 hour
            session_end = session_start + timedelta(seconds=duration_sec)
            
            # Event counts
            event_cnt = int(log_normal_value(median=8, sigma=0.6))
            event_cnt = max(1, min(100, event_cnt))
            
            page_view_cnt = max(1, int(event_cnt * random.uniform(0.4, 0.7)))
            product_view_dcnt = max(0, int(page_view_cnt * random.uniform(0.3, 0.8)))
            cart_add_cnt = max(0, int(product_view_dcnt * random.uniform(0, 0.4)))
            cart_value_sum = cart_add_cnt * random.uniform(20, 80) if cart_add_cnt > 0 else 0
            
            # Conversion (3% of sessions)
            is_converted = random.random() < config.session_conversion_rate
            order_value_sum = cart_value_sum * random.uniform(0.8, 1.2) if is_converted else 0
            
            # Device info (consistent with visitor)
            device_type = visitor["DEVICE_TYPE"]
            
            # Landing/exit pages
            pages = [
                "/", "/products", "/products/category", "/product/detail",
                "/cart", "/checkout", "/account", "/search"
            ]
            landing_page = f"https://store.snowflake.com{random.choice(pages)}"
            exit_page = f"https://store.snowflake.com{random.choice(pages)}"
            
            # Products viewed in session (ARRAY)
            products_viewed = [f"prod_{random.randint(0, config.num_products - 1):04d}" 
                              for _ in range(product_view_dcnt + random.randint(0, 3))]
            
            # Categories viewed (ARRAY) - unique
            categories = list(set(random.choices(
                ["DRINKWARE", "TEES", "HATS", "OUTERWEAR", "OFFICE", "ACCESSORIES"],
                k=min(5, max(1, product_view_dcnt))
            )))
            
            sessions.append({
                "SESSION_ID": f"sess_{session_id:08d}",
                "VISITOR_ID": visitor["VISITOR_ID"],
                "USER_ID": user_id if s >= identification_session else None,
                "SESSION_START_TS": session_start,
                "SESSION_END_TS": session_end,
                "DURATION_SEC": duration_sec,
                "EVENT_CNT": event_cnt,
                "PAGE_VIEW_CNT": page_view_cnt,
                "PRODUCT_VIEW_DCNT": product_view_dcnt,
                "CART_ADD_CNT": cart_add_cnt,
                "CART_VALUE_SUM": round(cart_value_sum, 2),
                "IS_CONVERTED": is_converted,
                "ORDER_VALUE_SUM": round(order_value_sum, 2) if is_converted else None,
                "DEVICE_TYPE": device_type,
                "LANDING_PAGE_URL": landing_page,
                "EXIT_PAGE_URL": exit_page,
                "PRODUCTS_VIEWED": to_array(products_viewed),
                "CATEGORIES_VIEWED": to_array(categories),
            })
            
            session_id += 1
        
        if session_id >= total_sessions:
            break
    
    return sessions


# =============================================================================
# EVENTS
# =============================================================================

def generate_events(
    config: DataConfig,
    sessions: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    batch_size: int = 10000,
    show_progress: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate EVENTS table data.
    
    Events are individual clickstream interactions within sessions.
    This is the largest table - uses batched generation for memory efficiency.
    
    Returns list of dicts matching EVENTS schema.
    """
    events = []
    
    # Create product lookup
    product_lookup = {p["PRODUCT_ID"]: p for p in products}
    product_ids = list(product_lookup.keys())
    
    # Event type weights
    event_type_weights = {et: info["weight"] for et, info in EVENT_TYPES.items()}
    
    total_events = sum(s["EVENT_CNT"] for s in sessions)
    event_id = 0
    
    if show_progress:
        print(f"Generating {total_events:,} events...")
    
    for session_idx, session in enumerate(sessions):
        num_events = session["EVENT_CNT"]
        
        # Generate timestamps for events in this session
        timestamps = generate_session_timestamps(
            session["SESSION_START_TS"],
            num_events,
            avg_gap_seconds=session["DURATION_SEC"] / max(1, num_events - 1) if num_events > 1 else 30,
        )
        
        # Track cart state for this session
        cart_items = []
        
        # Device context (consistent for session)
        device_type = session["DEVICE_TYPE"]
        browser = weighted_choice(BROWSERS)
        os = weighted_choice(OS_BY_DEVICE[device_type])
        context = generate_device_context(
            device_type=device_type,
            browser=browser,
            os=os,
            utm_source=random.choice(["google", "direct", "facebook", None]),
            utm_medium=random.choice(["organic", "cpc", "social", None]),
        )
        
        for event_idx, event_ts in enumerate(timestamps):
            # Select event type
            event_type = weighted_choice(event_type_weights)
            event_info = EVENT_TYPES[event_type]
            event_name = random.choice(event_info["events"])
            
            # Get product if needed
            product_id = None
            product = None
            category_id = None
            
            if event_info["requires_product"] or random.random() < 0.7:
                product_id = random.choice(product_ids)
                product = product_lookup[product_id]
                category_id = product["CATEGORY_ID"]
                
                # Add to cart tracking
                if event_name == "Product Added":
                    cart_items.append({
                        "product_id": product_id,
                        "quantity": random.randint(1, 3),
                        "price": product["PRICE"],
                    })
                elif event_name == "Product Removed" and cart_items:
                    # Remove from cart
                    cart_items = [c for c in cart_items if c["product_id"] != product_id]
            
            # Generate event properties (VARIANT)
            properties = generate_event_properties(
                event_name=event_name,
                product_id=product_id,
                product_name=product["NAME"] if product else None,
                price=product["PRICE"] if product else None,
                category=product["CATEGORY_ID"] if product else None,
                cart_items=cart_items if event_name in ["Cart Viewed", "Order Completed"] else None,
            )
            
            # Page URL
            if event_name in ["Product Viewed", "Product Clicked"]:
                page_url = f"https://store.snowflake.com/products/{product_id}"
            elif event_name == "Cart Viewed":
                page_url = "https://store.snowflake.com/cart"
            elif "Checkout" in event_name:
                page_url = "https://store.snowflake.com/checkout"
            elif "Search" in event_name:
                page_url = "https://store.snowflake.com/search"
            else:
                page_url = f"https://store.snowflake.com/{random.choice(['', 'products', 'categories'])}"
            
            events.append({
                "EVENT_ID": f"evt_{event_id:010d}",
                "VISITOR_ID": session["VISITOR_ID"],
                "USER_ID": session["USER_ID"],
                "SESSION_ID": session["SESSION_ID"],
                "EVENT_TS": event_ts,
                "EVENT_TYPE": event_type,
                "EVENT_NAME": event_name,
                "PRODUCT_ID": product_id,
                "CATEGORY_ID": category_id,
                "PAGE_URL": page_url,
                "PAGE_TITLE": f"Snowflake Store - {event_name}",
                "REFERRER_URL": session["LANDING_PAGE_URL"] if event_idx == 0 else None,
                "PROPERTIES": to_object(properties),
                "CONTEXT": to_object(context),
                "RECEIVED_TS": event_ts + timedelta(seconds=random.uniform(0.1, 5)),
            })
            
            event_id += 1
        
        # Progress update
        if show_progress and (session_idx + 1) % 1000 == 0:
            progress_bar(event_id, total_events, prefix="Events")
    
    if show_progress:
        progress_bar(event_id, total_events, prefix="Events")
    
    return events

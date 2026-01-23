"""
Order table generators: ORDERS, ORDER_ITEMS
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from faker import Faker

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DataConfig
from utils import (
    generate_uuid,
    weighted_choice,
    sample_without_replacement,
    random_timestamp,
    log_normal_value,
    to_object,
    generate_address,
    progress_bar,
)

fake = Faker()
Faker.seed(42)


# =============================================================================
# ORDERS
# =============================================================================

def generate_orders(
    config: DataConfig,
    users: List[Dict[str, Any]],
    sessions: List[Dict[str, Any]],
    show_progress: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate ORDERS table data.
    
    Orders are linked to users and optionally to sessions where the 
    purchase occurred.
    
    Returns list of dicts matching ORDERS schema.
    """
    orders = []
    
    # Get converted sessions
    converted_sessions = [s for s in sessions if s["IS_CONVERTED"]]
    
    # Create user -> sessions mapping
    user_sessions = {}
    for s in sessions:
        if s["USER_ID"]:
            user_sessions.setdefault(s["USER_ID"], []).append(s)
    
    # Calculate orders per user
    total_orders = config.num_orders
    
    # Users with orders (not all users have orders)
    users_with_orders = sample_without_replacement(
        users, 
        min(len(users), int(total_orders * 0.8))  # 80% of users have placed orders
    )
    
    order_id = 0
    
    if show_progress:
        print(f"Generating {total_orders:,} orders...")
    
    for user in users_with_orders:
        if order_id >= total_orders:
            break
        
        # Number of orders for this user (power-law: most users have few orders)
        num_user_orders = max(1, int(log_normal_value(median=2, sigma=0.8)))
        num_user_orders = min(num_user_orders, 20)  # Cap at 20 orders per user
        
        # Get user's sessions
        user_sess = user_sessions.get(user["USER_ID"], [])
        
        for o in range(num_user_orders):
            if order_id >= total_orders:
                break
            
            # Order timestamp (after user creation)
            order_ts = random_timestamp(
                user["CREATED_TS"], 
                config.end_date
            )
            
            # Link to session if possible
            session_id = None
            if user_sess:
                # Find session closest to order time
                closest_session = min(
                    user_sess,
                    key=lambda s: abs((s["SESSION_START_TS"] - order_ts).total_seconds())
                )
                if abs((closest_session["SESSION_START_TS"] - order_ts).total_seconds()) < 86400:
                    session_id = closest_session["SESSION_ID"]
            
            # Order amounts
            subtotal = round(log_normal_value(median=60, sigma=0.7), 2)
            subtotal = max(10, min(1000, subtotal))
            
            tax_rate = random.uniform(0.05, 0.10)
            tax_amt = round(subtotal * tax_rate, 2)
            
            shipping_amt = round(random.choice([0, 5.99, 7.99, 9.99, 14.99]), 2)
            if subtotal > 100:  # Free shipping over $100
                shipping_amt = 0
            
            # Discount (20% of orders have discount)
            has_discount = random.random() < 0.20
            discount_amt = round(subtotal * random.uniform(0.05, 0.25), 2) if has_discount else 0
            
            total_amt = round(subtotal + tax_amt + shipping_amt - discount_amt, 2)
            
            # Item count
            item_cnt = random.choices([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 
                                     weights=[30, 30, 20, 10, 5, 2, 1, 1, 0.5, 0.5])[0]
            
            # Coupon (15% of orders)
            coupon_code = None
            if has_discount:
                coupon_code = random.choice(["SNOW20", "WELCOME10", "LOYALTY15", "FLASH25", "SUMMER10"])
            
            # Payment method
            payment_method = weighted_choice({
                "credit": 0.50,
                "debit": 0.20,
                "paypal": 0.20,
                "applepay": 0.10,
            })
            
            # Addresses (VARIANT)
            country = user["ADDRESS_COUNTRY"] or "US"
            shipping_address = generate_address(fake, country)
            billing_address = shipping_address.copy() if random.random() < 0.85 else generate_address(fake, country)
            
            # Status
            status = weighted_choice({
                "delivered": 0.75,
                "shipped": 0.10,
                "confirmed": 0.08,
                "pending": 0.03,
                "cancelled": 0.02,
                "refunded": 0.02,
            })
            
            orders.append({
                "ORDER_ID": f"ord_{order_id:07d}",
                "USER_ID": user["USER_ID"],
                "SESSION_ID": session_id,
                "ORDER_TS": order_ts,
                "STATUS": status,
                "SUBTOTAL_AMT": subtotal,
                "TAX_AMT": tax_amt,
                "SHIPPING_AMT": shipping_amt,
                "DISCOUNT_AMT": discount_amt,
                "TOTAL_AMT": total_amt,
                "ITEM_CNT": item_cnt,
                "COUPON_CODE": coupon_code,
                "PAYMENT_METHOD": payment_method,
                "SHIPPING_ADDRESS": to_object(shipping_address),
                "BILLING_ADDRESS": to_object(billing_address),
                "CREATED_TS": order_ts,
                "UPDATED_TS": random_timestamp(order_ts, config.end_date),
            })
            
            order_id += 1
        
        # Progress update
        if show_progress and (order_id + 1) % 1000 == 0:
            progress_bar(order_id, total_orders, prefix="Orders")
    
    if show_progress:
        progress_bar(order_id, total_orders, prefix="Orders")
    
    return orders


# =============================================================================
# ORDER_ITEMS
# =============================================================================

def generate_order_items(
    config: DataConfig,
    orders: List[Dict[str, Any]],
    product_suppliers: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    show_progress: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate ORDER_ITEMS table data.
    
    Order items reference PRODUCT_SUPPLIER (composite FK) to track
    which supplier fulfilled each item.
    
    Returns list of dicts matching ORDER_ITEMS schema.
    """
    order_items = []
    
    # Create product -> supplier mapping (prefer IS_PREFERRED suppliers)
    # Group by product_id, prioritizing preferred suppliers
    product_to_suppliers = {}
    for ps in product_suppliers:
        if ps["IS_CURRENT"]:  # Only use current records
            pid = ps["PRODUCT_ID"]
            if pid not in product_to_suppliers:
                product_to_suppliers[pid] = {"preferred": [], "other": []}
            
            if ps["IS_PREFERRED"]:
                product_to_suppliers[pid]["preferred"].append(ps)
            else:
                product_to_suppliers[pid]["other"].append(ps)
    
    # Product lookup
    product_lookup = {p["PRODUCT_ID"]: p for p in products}
    product_ids = list(product_lookup.keys())
    
    item_id = 0
    total_items = sum(o["ITEM_CNT"] for o in orders)
    
    if show_progress:
        print(f"Generating {total_items:,} order items...")
    
    for order in orders:
        num_items = order["ITEM_CNT"]
        
        # Select products for this order
        order_products = sample_without_replacement(product_ids, min(num_items, len(product_ids)))
        
        # If we need more items, allow duplicates
        while len(order_products) < num_items:
            order_products.append(random.choice(product_ids))
        
        # Distribute order total across items
        remaining_subtotal = order["SUBTOTAL_AMT"]
        
        for idx, product_id in enumerate(order_products):
            product = product_lookup.get(product_id)
            if not product:
                continue
            
            # Get supplier for this product
            suppliers_info = product_to_suppliers.get(product_id, {"preferred": [], "other": []})
            
            if suppliers_info["preferred"]:
                supplier_record = suppliers_info["preferred"][0]
            elif suppliers_info["other"]:
                supplier_record = random.choice(suppliers_info["other"])
            else:
                # Fallback - use product's default supplier
                supplier_record = {
                    "PRODUCT_ID": product_id,
                    "SUPPLIER_ID": product["SUPPLIER_ID"],
                    "SUPPLIER_PRICE": product["PRICE"],
                }
            
            # Quantity
            quantity = random.choices([1, 2, 3, 4, 5], weights=[60, 25, 10, 3, 2])[0]
            
            # Price at purchase (may differ slightly from current)
            unit_price = product["PRICE"] * random.uniform(0.95, 1.05)
            unit_price = round(unit_price, 2)
            
            # Item discount (10% of items)
            has_discount = random.random() < 0.10
            discount_amt = round(unit_price * quantity * random.uniform(0.05, 0.20), 2) if has_discount else 0
            
            # Total
            total_amt = round(unit_price * quantity - discount_amt, 2)
            
            order_items.append({
                "ORDER_ITEM_ID": f"item_{item_id:08d}",
                "ORDER_ID": order["ORDER_ID"],
                "PRODUCT_ID": product_id,
                "SUPPLIER_ID": supplier_record["SUPPLIER_ID"],
                "QUANTITY": quantity,
                "UNIT_PRICE_AMT": unit_price,
                "DISCOUNT_AMT": discount_amt,
                "TOTAL_AMT": total_amt,
            })
            
            item_id += 1
        
        # Progress update
        if show_progress and (item_id + 1) % 5000 == 0:
            progress_bar(item_id, total_items, prefix="Order Items")
    
    if show_progress:
        progress_bar(item_id, total_items, prefix="Order Items")
    
    return order_items

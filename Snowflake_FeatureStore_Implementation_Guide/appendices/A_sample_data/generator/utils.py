"""
Utility functions for data generation.

Includes:
- UUID generation
- Weighted random selection
- Temporal pattern generation
- Semi-structured data helpers
"""

import hashlib
import json
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid


def generate_uuid(prefix: str = "") -> str:
    """Generate a UUID, optionally with a prefix for readability."""
    uid = str(uuid.uuid4())[:8]  # Short UUID for readability
    return f"{prefix}{uid}" if prefix else uid


def generate_deterministic_uuid(seed: str, prefix: str = "") -> str:
    """Generate a deterministic UUID based on a seed string."""
    hash_obj = hashlib.md5(seed.encode())
    uid = hash_obj.hexdigest()[:8]
    return f"{prefix}{uid}" if prefix else uid


def weighted_choice(choices: Dict[str, float]) -> str:
    """Select a random item based on weights."""
    items = list(choices.keys())
    weights = list(choices.values())
    return random.choices(items, weights=weights, k=1)[0]


def weighted_choices(choices: Dict[str, float], k: int) -> List[str]:
    """Select k random items based on weights (with replacement)."""
    items = list(choices.keys())
    weights = list(choices.values())
    return random.choices(items, weights=weights, k=k)


def sample_without_replacement(items: List[Any], k: int) -> List[Any]:
    """Sample k items without replacement."""
    k = min(k, len(items))
    return random.sample(items, k)


# =============================================================================
# TEMPORAL UTILITIES
# =============================================================================

def random_timestamp(start: datetime, end: datetime) -> datetime:
    """Generate a random timestamp between start and end."""
    if start >= end:
        return start  # Return start if invalid range
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return start
    random_seconds = random.randint(0, total_seconds)
    return start + timedelta(seconds=random_seconds)


def random_timestamp_weighted(
    start: datetime, 
    end: datetime,
    peak_hours: List[int] = None,
    low_hours: List[int] = None,
    weekend_factor: float = 0.8,
    holiday_months: List[int] = None,
    holiday_factor: float = 1.5,
) -> datetime:
    """
    Generate a timestamp with realistic temporal patterns.
    
    - Peak hours have higher probability
    - Weekend has lower traffic
    - Holiday months have higher traffic
    """
    peak_hours = peak_hours or [10, 11, 12, 13, 19, 20, 21]
    low_hours = low_hours or [2, 3, 4, 5]
    holiday_months = holiday_months or [11, 12]
    
    # Generate candidate timestamp
    ts = random_timestamp(start, end)
    
    # Calculate acceptance probability
    prob = 1.0
    
    # Hour of day factor
    hour = ts.hour
    if hour in peak_hours:
        prob *= 1.5
    elif hour in low_hours:
        prob *= 0.3
    
    # Day of week factor (0=Monday, 6=Sunday)
    if ts.weekday() >= 5:  # Weekend
        prob *= weekend_factor
    
    # Month factor (holidays)
    if ts.month in holiday_months:
        prob *= holiday_factor
    
    # Accept/reject sampling
    if random.random() < prob / 2.0:  # Normalize probability
        return ts
    else:
        # Retry (recursive, but bounded by probability)
        return random_timestamp_weighted(
            start, end, peak_hours, low_hours, 
            weekend_factor, holiday_months, holiday_factor
        )


def generate_session_timestamps(
    session_start: datetime,
    num_events: int,
    avg_gap_seconds: int = 30,
) -> List[datetime]:
    """Generate ordered timestamps for events within a session."""
    timestamps = [session_start]
    current = session_start
    
    for _ in range(num_events - 1):
        # Exponential distribution for time between events
        gap = random.expovariate(1.0 / avg_gap_seconds)
        gap = max(1, min(gap, 300))  # Clamp between 1 sec and 5 min
        current = current + timedelta(seconds=gap)
        timestamps.append(current)
    
    return timestamps


def generate_date_range(
    start: datetime, 
    end: datetime, 
    count: int,
) -> List[datetime]:
    """Generate evenly distributed dates within a range."""
    if count <= 1:
        return [start]
    
    delta = (end - start) / (count - 1)
    return [start + delta * i for i in range(count)]


# =============================================================================
# NUMERIC DISTRIBUTIONS
# =============================================================================

def log_normal_value(median: float, sigma: float = 0.5) -> float:
    """Generate a log-normal distributed value with given median."""
    import math
    mu = math.log(median)
    return random.lognormvariate(mu, sigma)


def bounded_normal(mean: float, std: float, min_val: float, max_val: float) -> float:
    """Generate a bounded normal distributed value."""
    value = random.gauss(mean, std)
    return max(min_val, min(max_val, value))


def power_law_value(alpha: float = 2.0, x_min: float = 1.0) -> float:
    """Generate a power-law distributed value (Pareto)."""
    return x_min * (1 - random.random()) ** (-1 / (alpha - 1))


# =============================================================================
# SEMI-STRUCTURED DATA HELPERS
# =============================================================================

def to_variant(data: Any) -> str:
    """Convert Python object to JSON string for VARIANT column."""
    return json.dumps(data)


def to_array(items: List[Any]) -> str:
    """Convert Python list to JSON array string for ARRAY column."""
    return json.dumps(items)


def to_object(data: Dict[str, Any]) -> str:
    """Convert Python dict to JSON object string for OBJECT column."""
    return json.dumps(data)


def generate_address(
    faker_instance,
    country: str = "US",
) -> Dict[str, Any]:
    """Generate a realistic address structure."""
    # State/province based on country
    if country == "US":
        state = faker_instance.state_abbr()
    elif country == "CA":
        state = random.choice(["ON", "BC", "AB", "QC", "MB", "SK", "NS", "NB"])
    elif country == "UK":
        state = random.choice(["England", "Scotland", "Wales", "N. Ireland"])
    elif country == "AU":
        state = random.choice(["NSW", "VIC", "QLD", "WA", "SA", "TAS"])
    else:
        state = ""
    
    return {
        "first_name": faker_instance.first_name(),
        "last_name": faker_instance.last_name(),
        "street": faker_instance.street_address(),
        "street2": faker_instance.secondary_address() if random.random() < 0.3 else None,
        "city": faker_instance.city(),
        "state": state,
        "postal_code": faker_instance.postcode(),
        "country": country,
        "phone": faker_instance.phone_number(),
    }


def generate_device_context(
    device_type: str,
    browser: str,
    os: str,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate device/session context for EVENTS.CONTEXT."""
    context = {
        "device": {
            "type": device_type,
            "manufacturer": "Apple" if "iOS" in os or "macOS" in os else "Various",
            "screen_width": random.choice([390, 414, 428, 1920, 1440, 2560]),
            "screen_height": random.choice([844, 896, 926, 1080, 900, 1440]),
        },
        "os": {
            "name": os,
            "version": f"{random.randint(14, 17)}.{random.randint(0, 5)}",
        },
        "browser": {
            "name": browser,
            "version": f"{random.randint(100, 120)}.0.{random.randint(0, 9999)}",
        },
        "locale": "en-US",
        "timezone": random.choice([
            "America/New_York", "America/Los_Angeles", "America/Chicago",
            "Europe/London", "Europe/Paris", "Australia/Sydney"
        ]),
        "ip": f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.xxx",
    }
    
    # Add UTM if provided
    if utm_source:
        context["campaign"] = {
            "source": utm_source,
            "medium": utm_medium or "organic",
            "name": utm_campaign or f"campaign_{random.randint(1, 100)}",
        }
    
    return context


def generate_event_properties(
    event_name: str,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    price: Optional[float] = None,
    category: Optional[str] = None,
    cart_items: Optional[List[Dict]] = None,
    order_id: Optional[str] = None,
    search_query: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate event-specific properties for EVENTS.PROPERTIES."""
    
    if event_name in ["Product Viewed", "Product Clicked"]:
        return {
            "product_id": product_id,
            "product_name": product_name,
            "price": price,
            "category": category,
            "position": random.randint(1, 20),
            "list_id": random.choice(["homepage_featured", "category_page", "search_results", "recommendations"]),
        }
    
    elif event_name == "Product Added":
        props = {
            "product_id": product_id,
            "quantity": random.randint(1, 3),
            "price": price,
            "cart_id": f"cart_{generate_uuid()}",
        }
        if cart_items:
            props["products"] = cart_items
        return props
    
    elif event_name == "Product Removed":
        return {
            "product_id": product_id,
            "quantity": 1,
            "price": price,
        }
    
    elif event_name == "Cart Viewed":
        return {
            "cart_id": f"cart_{generate_uuid()}",
            "products": cart_items or [],
            "cart_value": sum(item.get("price", 0) * item.get("quantity", 1) for item in (cart_items or [])),
        }
    
    elif event_name == "Products Searched":
        return {
            "query": search_query or random.choice([
                "snowflake hoodie", "data cloud mug", "winter jacket",
                "laptop bag", "stickers", "t-shirt"
            ]),
            "filters": {
                "category": [category] if category else [],
                "price_min": random.choice([0, 10, 20, 50]),
                "price_max": random.choice([50, 100, 200, 500]),
            },
            "result_cnt": random.randint(0, 50),
        }
    
    elif event_name == "Order Completed":
        return {
            "order_id": order_id,
            "total": sum(item.get("price", 0) * item.get("quantity", 1) for item in (cart_items or [])),
            "currency": "USD",
            "products": cart_items or [],
            "coupon": random.choice([None, "SNOW20", "WELCOME10", "LOYALTY15"]),
        }
    
    elif event_name in ["Checkout Started", "Checkout Step Viewed", "Payment Info Entered"]:
        return {
            "cart_id": f"cart_{generate_uuid()}",
            "step": random.randint(1, 4),
            "cart_value": price or random.uniform(25, 200),
        }
    
    elif event_name in ["Product Added to Wishlist", "Product Removed from Wishlist"]:
        return {
            "product_id": product_id,
            "product_name": product_name,
            "price": price,
        }
    
    else:
        return {"event_name": event_name}


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def chunked(iterable: List[Any], chunk_size: int):
    """Yield successive chunks from an iterable."""
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]


def progress_bar(current: int, total: int, prefix: str = "", length: int = 40):
    """Print a simple progress bar."""
    percent = current / total
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    print(f"\r{prefix} |{bar}| {percent*100:.1f}% ({current:,}/{total:,})", end="", flush=True)
    if current >= total:
        print()  # Newline at completion

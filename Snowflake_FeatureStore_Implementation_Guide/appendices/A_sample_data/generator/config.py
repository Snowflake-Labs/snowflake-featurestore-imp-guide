"""
Configuration for Clickstream Data Generator

Scale factors control the size of generated data.
Adjust SCALE_FACTOR to generate larger or smaller datasets.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List

# =============================================================================
# SCALE FACTOR
# =============================================================================
# Base: 1.0 = ~100K users, 50M events
# Small: 0.01 = ~1K users, 500K events (for testing)
# Medium: 0.1 = ~10K users, 5M events
# Large: 10.0 = ~1M users, 500M events

SCALE_FACTOR = 0.01  # Start small for testing


@dataclass
class DataConfig:
    """Configuration for data generation."""
    
    # Scale factor (multiplier for all counts)
    scale: float = SCALE_FACTOR
    
    # Date range for historical data
    start_date: datetime = field(default_factory=lambda: datetime(2022, 1, 1))
    end_date: datetime = field(default_factory=lambda: datetime(2024, 12, 31))
    
    # Base counts (will be multiplied by scale)
    base_users: int = 100_000
    base_products: int = 500
    base_suppliers: int = 50
    base_categories: int = 15  # Fixed, not scaled
    
    # Ratios (relative to users)
    visitors_per_user: float = 5.0      # Anonymous visitors before identification
    households_per_user: float = 0.6    # ~1.7 users per household
    sessions_per_user: float = 50.0     # Avg sessions over time period
    events_per_session: float = 10.0    # Avg events per session
    orders_per_user: float = 3.0        # Avg orders per user
    items_per_order: float = 2.0        # Avg items per order
    suppliers_per_product: float = 3.0  # Avg suppliers per product
    
    # Conversion rates
    visitor_identification_rate: float = 0.20  # % of visitors who become users
    session_conversion_rate: float = 0.03      # % of sessions with purchase
    cart_abandonment_rate: float = 0.70        # % of carts abandoned
    
    # Temporal patterns
    peak_hours: List[int] = field(default_factory=lambda: [10, 11, 12, 13, 19, 20, 21])
    low_hours: List[int] = field(default_factory=lambda: [2, 3, 4, 5])
    weekend_factor: float = 0.8  # 20% less traffic on weekends
    holiday_factor: float = 1.5  # 50% more traffic in Nov-Dec
    
    @property
    def num_users(self) -> int:
        return int(self.base_users * self.scale)
    
    @property
    def num_visitors(self) -> int:
        return int(self.num_users * self.visitors_per_user)
    
    @property
    def num_households(self) -> int:
        return int(self.num_users * self.households_per_user)
    
    @property
    def num_products(self) -> int:
        return max(50, int(self.base_products * min(self.scale, 1.0)))  # Cap products
    
    @property
    def num_suppliers(self) -> int:
        return max(10, int(self.base_suppliers * min(self.scale, 1.0)))  # Cap suppliers
    
    @property
    def num_categories(self) -> int:
        return self.base_categories  # Fixed
    
    @property
    def num_sessions(self) -> int:
        return int(self.num_users * self.sessions_per_user)
    
    @property
    def num_events(self) -> int:
        return int(self.num_sessions * self.events_per_session)
    
    @property
    def num_orders(self) -> int:
        return int(self.num_users * self.orders_per_user)
    
    @property
    def num_order_items(self) -> int:
        return int(self.num_orders * self.items_per_order)
    
    @property
    def num_product_suppliers(self) -> int:
        return int(self.num_products * self.suppliers_per_product)
    
    def summary(self) -> Dict[str, int]:
        """Return summary of expected row counts."""
        return {
            "CATEGORIES": self.num_categories,
            "SUPPLIERS": self.num_suppliers,
            "HOUSEHOLDS": self.num_households,
            "PRODUCTS": self.num_products,
            "PRODUCT_SUPPLIER": self.num_product_suppliers,
            "VISITORS": self.num_visitors,
            "USERS": self.num_users,
            "SESSIONS": self.num_sessions,
            "EVENTS": self.num_events,
            "ORDERS": self.num_orders,
            "ORDER_ITEMS": self.num_order_items,
        }


# =============================================================================
# CATEGORY DATA (Static)
# =============================================================================
CATEGORIES = [
    {"id": "cat_accessories", "name": "ACCESSORIES", "display_order": 1},
    {"id": "cat_bags", "name": "BAGS", "display_order": 2},
    {"id": "cat_books", "name": "BOOKS", "display_order": 3},
    {"id": "cat_drinkware", "name": "DRINKWARE", "display_order": 4},
    {"id": "cat_gift", "name": "GIFT", "display_order": 5},
    {"id": "cat_hats", "name": "HATS", "display_order": 6},
    {"id": "cat_kids", "name": "KIDS", "display_order": 7},
    {"id": "cat_office", "name": "OFFICE", "display_order": 8},
    {"id": "cat_outerwear", "name": "OUTERWEAR", "display_order": 9},
    {"id": "cat_pets", "name": "PETS", "display_order": 10},
    {"id": "cat_sme", "name": "SME", "display_order": 11},
    {"id": "cat_snow", "name": "SNOW", "display_order": 12},
    {"id": "cat_stickers", "name": "STICKERS", "display_order": 13},
    {"id": "cat_tees", "name": "TEES", "display_order": 14},
    {"id": "cat_tech", "name": "TECH", "display_order": 15},
]

# Category weights for product distribution
CATEGORY_WEIGHTS = {
    "ACCESSORIES": 0.08,
    "BAGS": 0.05,
    "BOOKS": 0.03,
    "DRINKWARE": 0.12,
    "GIFT": 0.06,
    "HATS": 0.08,
    "KIDS": 0.04,
    "OFFICE": 0.10,
    "OUTERWEAR": 0.10,
    "PETS": 0.03,
    "SME": 0.05,
    "SNOW": 0.06,
    "STICKERS": 0.05,
    "TEES": 0.12,
    "TECH": 0.03,
}


# =============================================================================
# EVENT TYPES (Segment Ecommerce Spec)
# =============================================================================
EVENT_TYPES = {
    "Browsing": {
        "events": ["Products Searched", "Product List Viewed", "Product List Filtered"],
        "weight": 0.30,
        "requires_product": False,
    },
    "Product": {
        "events": ["Product Clicked", "Product Viewed"],
        "weight": 0.40,
        "requires_product": True,
    },
    "Cart": {
        "events": ["Product Added", "Product Removed", "Cart Viewed"],
        "weight": 0.15,
        "requires_product": True,
    },
    "Checkout": {
        "events": ["Checkout Started", "Checkout Step Viewed", "Payment Info Entered"],
        "weight": 0.08,
        "requires_product": False,
    },
    "Order": {
        "events": ["Order Completed", "Order Refunded", "Order Cancelled"],
        "weight": 0.05,
        "requires_product": False,
    },
    "Wishlist": {
        "events": ["Product Added to Wishlist", "Product Removed from Wishlist"],
        "weight": 0.02,
        "requires_product": True,
    },
}


# =============================================================================
# DEVICE/BROWSER DISTRIBUTIONS
# =============================================================================
DEVICE_TYPES = {"mobile": 0.50, "desktop": 0.40, "tablet": 0.10}

BROWSERS = {
    "Chrome": 0.60,
    "Safari": 0.25,
    "Firefox": 0.10,
    "Edge": 0.05,
}

OS_BY_DEVICE = {
    "mobile": {"iOS": 0.55, "Android": 0.45},
    "desktop": {"Windows": 0.60, "macOS": 0.35, "Linux": 0.05},
    "tablet": {"iOS": 0.65, "Android": 0.35},
}

COUNTRIES = {
    "US": 0.70,
    "UK": 0.10,
    "CA": 0.08,
    "AU": 0.05,
    "DE": 0.04,
    "FR": 0.03,
}

UTM_SOURCES = {
    "google": 0.40,
    "direct": 0.30,
    "facebook": 0.10,
    "instagram": 0.08,
    "email": 0.07,
    "twitter": 0.03,
    "linkedin": 0.02,
}

UTM_MEDIUMS = {
    "organic": 0.35,
    "cpc": 0.25,
    "social": 0.20,
    "email": 0.12,
    "referral": 0.08,
}


# =============================================================================
# PRODUCT TAGS
# =============================================================================
PRODUCT_TAGS = [
    "bestseller", "new-arrival", "eco-friendly", "limited-edition",
    "sale", "premium", "gift-idea", "trending", "staff-pick",
    "sustainable", "handmade", "exclusive", "bundle", "clearance"
]


# =============================================================================
# SNOWFLAKE CONNECTION (Override via environment variables)
# =============================================================================
@dataclass
class SnowflakeConfig:
    """Snowflake connection configuration."""
    connection_name: str = ""  # Named connection from ~/.snowflake/connections.toml
    account: str = ""  # Set via SNOWFLAKE_ACCOUNT env var
    user: str = ""     # Set via SNOWFLAKE_USER env var
    password: str = "" # Set via SNOWFLAKE_PASSWORD env var
    role: str = "ACCOUNTADMIN"
    warehouse: str = "COMPUTE_WH"
    database: str = "FEATURE_STORE_GUIDE"
    schema: str = "CLICKSTREAM_RAW"
    
    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        """Load configuration from environment variables."""
        import os
        return cls(
            connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME", ""),
            account=os.getenv("SNOWFLAKE_ACCOUNT", ""),
            user=os.getenv("SNOWFLAKE_USER", ""),
            password=os.getenv("SNOWFLAKE_PASSWORD", ""),
            role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
            database=os.getenv("SNOWFLAKE_DATABASE", "FEATURE_STORE_GUIDE"),
            schema=os.getenv("SNOWFLAKE_SCHEMA", "CLICKSTREAM_RAW"),
        )
    
    @property
    def is_valid(self) -> bool:
        """Check if configuration has enough credentials."""
        # Either named connection or account+user is required
        if self.connection_name:
            return True
        return bool(self.account and self.user)
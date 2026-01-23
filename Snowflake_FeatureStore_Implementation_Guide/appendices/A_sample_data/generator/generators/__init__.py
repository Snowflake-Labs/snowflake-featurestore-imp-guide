"""
Table generators for clickstream dataset.

Each generator creates data for a specific table following the 
data model specification.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from generators.dimensions import (
    generate_categories,
    generate_suppliers,
    generate_households,
    generate_products,
    generate_product_suppliers,
)
from generators.visitors_users import (
    generate_visitors,
    generate_users,
)
from generators.events import (
    generate_sessions,
    generate_events,
)
from generators.orders import (
    generate_orders,
    generate_order_items,
)

__all__ = [
    "generate_categories",
    "generate_suppliers", 
    "generate_households",
    "generate_products",
    "generate_product_suppliers",
    "generate_visitors",
    "generate_users",
    "generate_sessions",
    "generate_events",
    "generate_orders",
    "generate_order_items",
]

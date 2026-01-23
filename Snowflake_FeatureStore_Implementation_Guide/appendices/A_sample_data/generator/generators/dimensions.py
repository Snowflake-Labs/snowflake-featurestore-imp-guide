"""
Dimension table generators: CATEGORIES, SUPPLIERS, HOUSEHOLDS, PRODUCTS, PRODUCT_SUPPLIER
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from faker import Faker

# Add parent directory to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    CATEGORIES, 
    CATEGORY_WEIGHTS, 
    PRODUCT_TAGS,
    DataConfig,
)
from utils import (
    generate_uuid,
    weighted_choice,
    sample_without_replacement,
    random_timestamp,
    log_normal_value,
    bounded_normal,
    to_array,
    to_object,
)

fake = Faker()
Faker.seed(42)  # Reproducibility


# =============================================================================
# CATEGORIES (Static dimension)
# =============================================================================

def generate_categories(config: DataConfig) -> List[Dict[str, Any]]:
    """
    Generate CATEGORIES table data.
    
    Returns list of dicts matching CATEGORIES schema.
    Static data - always returns the same 15 categories.
    """
    return [
        {
            "CATEGORY_ID": cat["id"],
            "NAME": cat["name"],
            "DISPLAY_ORDER": cat["display_order"],
        }
        for cat in CATEGORIES
    ]


# =============================================================================
# SUPPLIERS
# =============================================================================

SUPPLIER_NAMES = [
    "Arctic Apparel Co", "Snow Peak Industries", "Glacier Goods LLC",
    "Frostbite Fashion", "Avalanche Accessories", "Blizzard Brands",
    "Polar Express Supplies", "Iceberg Imports", "Tundra Trading",
    "Alpine Apparel", "Summit Supply Co", "Everest Enterprises",
    "Snowflake Solutions", "Crystal Clear Co", "Winter Wonder Works",
    "Frozen Frontier", "Cold Chain Corp", "Arctic Circle Supply",
    "Northern Lights LLC", "Snowbound Supplies", "Powder Peak Partners",
    "Flurry Fulfillment", "Chill Factor Corp", "Icicle Industries",
    "Permafrost Products", "Sleet Street Supply", "Hailstone Holdings",
    "Snowstorm Services", "Frost Line LLC", "Subzero Supplies",
    "Whiteout Wholesale", "Drift Distribution", "Snowcap Corp",
    "Ice Age Industries", "Glacier Bay Goods", "Cold Front Co",
    "Snow Day Supply", "Winter Warehouse", "Frozen Assets LLC",
    "Arctic Air Apparel", "Cryogenic Corp", "Snowmelt Manufacturing",
    "Flake Factory", "Powder Room Products", "Ice Crystal Corp",
    "Snow Globe Goods", "Frigid Fulfillment", "Borealis Brands",
    "Aurora Supply Co", "Snowbird Sourcing",
]


def generate_suppliers(config: DataConfig) -> List[Dict[str, Any]]:
    """
    Generate SUPPLIERS table data.
    
    Returns list of dicts matching SUPPLIERS schema.
    """
    suppliers = []
    num_suppliers = config.num_suppliers
    
    # Ensure we have enough names
    names = SUPPLIER_NAMES[:num_suppliers] if num_suppliers <= len(SUPPLIER_NAMES) else \
            SUPPLIER_NAMES + [f"Supplier {i}" for i in range(len(SUPPLIER_NAMES), num_suppliers)]
    
    for i, name in enumerate(names):
        created_ts = random_timestamp(config.start_date, config.start_date + timedelta(days=365))
        
        suppliers.append({
            "SUPPLIER_ID": f"sup_{i:04d}",
            "NAME": name,
            "CONTACT_EMAIL": f"contact@{name.lower().replace(' ', '').replace(',', '')[:20]}.com",
            "COUNTRY": weighted_choice({"US": 0.60, "CN": 0.20, "MX": 0.10, "CA": 0.10}),
            "LEAD_TIME_DAYS_AVG": random.randint(3, 30),
            "QUALITY_RATING_AVG": round(bounded_normal(4.0, 0.5, 2.5, 5.0), 2),
            "CREATED_TS": created_ts,
            "UPDATED_TS": random_timestamp(created_ts, config.end_date),
        })
    
    return suppliers


# =============================================================================
# HOUSEHOLDS
# =============================================================================

def generate_households(config: DataConfig) -> List[Dict[str, Any]]:
    """
    Generate HOUSEHOLDS table data.
    
    Returns list of dicts matching HOUSEHOLDS schema.
    """
    households = []
    
    for i in range(config.num_households):
        created_ts = random_timestamp(config.start_date, config.end_date - timedelta(days=30))
        
        households.append({
            "HOUSEHOLD_ID": f"hh_{i:06d}",
            "MEMBER_CNT": random.choices([1, 2, 3, 4, 5, 6], weights=[30, 35, 20, 10, 4, 1])[0],
            "INCOME_BRACKET": weighted_choice({
                "low": 0.20, "medium": 0.40, "high": 0.30, "premium": 0.10
            }),
            "DWELLING_TYPE": weighted_choice({
                "apartment": 0.40, "house": 0.45, "condo": 0.15
            }),
            "CREATED_TS": created_ts,
            "UPDATED_TS": random_timestamp(created_ts, config.end_date),
        })
    
    return households


# =============================================================================
# PRODUCTS
# =============================================================================

PRODUCT_TEMPLATES = {
    "ACCESSORIES": ["Lanyard", "Keychain", "Pin Set", "Patch", "Badge", "Wristband"],
    "BAGS": ["Backpack", "Tote Bag", "Laptop Sleeve", "Duffel Bag", "Messenger Bag"],
    "BOOKS": ["Data Guide", "Cloud Handbook", "ML Primer", "Analytics Book"],
    "DRINKWARE": ["Mug", "Tumbler", "Water Bottle", "Travel Mug", "Pint Glass"],
    "GIFT": ["Gift Card", "Gift Box", "Mystery Box", "Welcome Kit"],
    "HATS": ["Baseball Cap", "Beanie", "Trucker Hat", "Bucket Hat", "Visor"],
    "KIDS": ["Kids Tee", "Kids Hoodie", "Onesie", "Kids Cap", "Plush Toy"],
    "OFFICE": ["Notebook", "Pen Set", "Mouse Pad", "Desk Mat", "Cable Organizer"],
    "OUTERWEAR": ["Hoodie", "Zip Jacket", "Vest", "Puffer Jacket", "Windbreaker"],
    "PETS": ["Pet Bandana", "Pet Collar", "Pet Bowl", "Pet Toy"],
    "SME": ["Logo Stencil", "Branding Kit", "Sample Pack"],
    "SNOW": ["Ski Pass Holder", "Snow Globe", "Winter Kit", "Hand Warmers"],
    "STICKERS": ["Sticker Pack", "Laptop Stickers", "Vinyl Decal", "Bumper Sticker"],
    "TEES": ["T-Shirt", "Long Sleeve Tee", "V-Neck Tee", "Tank Top", "Polo"],
    "TECH": ["USB Drive", "Power Bank", "Webcam Cover", "Phone Stand"],
}

COLORS = ["Black", "White", "Navy", "Gray", "Blue", "Green", "Red"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]


def generate_products(
    config: DataConfig, 
    categories: List[Dict[str, Any]],
    suppliers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate PRODUCTS table data.
    
    Returns list of dicts matching PRODUCTS schema.
    """
    products = []
    category_map = {cat["NAME"]: cat["CATEGORY_ID"] for cat in categories}
    supplier_ids = [s["SUPPLIER_ID"] for s in suppliers]
    
    product_id = 0
    for category_name, weight in CATEGORY_WEIGHTS.items():
        num_products_in_cat = max(1, int(config.num_products * weight))
        templates = PRODUCT_TEMPLATES.get(category_name, ["Item"])
        
        for _ in range(num_products_in_cat):
            template = random.choice(templates)
            color = random.choice(COLORS)
            
            # Generate product name
            name = f"Snowflake {color} {template}"
            if random.random() < 0.3:
                name = f"{name} - Limited Edition"
            
            # Generate pricing
            base_price = log_normal_value(median=35.0, sigma=0.8)
            base_price = max(5.0, min(500.0, base_price))
            price = round(base_price, 2)
            original_price = round(price * random.uniform(1.0, 1.4), 2)
            cost = round(price * random.uniform(0.4, 0.6), 2)
            
            # Generate tags (ARRAY)
            num_tags = random.choices([0, 1, 2, 3, 4], weights=[10, 30, 35, 20, 5])[0]
            tags = sample_without_replacement(PRODUCT_TAGS, num_tags)
            
            # Generate attributes (OBJECT)
            attributes = {
                "color": color,
                "material": random.choice(["Cotton", "Polyester", "Blend", "Organic Cotton"]),
            }
            if category_name in ["TEES", "OUTERWEAR", "KIDS"]:
                attributes["sizes"] = SIZES
            if random.random() < 0.3:
                attributes["weight_oz"] = round(random.uniform(2, 24), 1)
            
            created_ts = random_timestamp(config.start_date, config.start_date + timedelta(days=180))
            
            products.append({
                "PRODUCT_ID": f"prod_{product_id:04d}",
                "SKU": f"{category_name[:3].upper()}-{product_id:04d}",
                "NAME": name,
                "DESCRIPTION": f"Premium {name} featuring the Snowflake logo. Perfect for data enthusiasts.",
                "CATEGORY_ID": category_map[category_name],
                "SUPPLIER_ID": random.choice(supplier_ids),  # Default supplier
                "PRICE": price,
                "ORIGINAL_PRICE": original_price,
                "COST": cost,
                "IMAGE_URL": f"https://cdn.snowflake-store.com/products/{product_id:04d}.jpg",
                "STATUS": weighted_choice({"active": 0.85, "discontinued": 0.10, "out_of_stock": 0.05}),
                "TAGS": to_array(tags),
                "ATTRIBUTES": to_object(attributes),
                "CREATED_TS": created_ts,
                "UPDATED_TS": random_timestamp(created_ts, config.end_date),
                "POPULARITY_SCORE": round(bounded_normal(50, 25, 0, 100), 2),
            })
            
            product_id += 1
            if product_id >= config.num_products:
                break
        
        if product_id >= config.num_products:
            break
    
    return products


# =============================================================================
# PRODUCT_SUPPLIER (M:N Junction Table)
# =============================================================================

def generate_product_suppliers(
    config: DataConfig,
    products: List[Dict[str, Any]],
    suppliers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate PRODUCT_SUPPLIER table data.
    
    Creates M:N relationships between products and suppliers with
    supplier-specific attributes. Implements SCD Type 2 with 
    VALID_FROM_TS, VALID_TO_TS, IS_CURRENT.
    
    Returns list of dicts matching PRODUCT_SUPPLIER schema.
    """
    product_suppliers = []
    supplier_ids = [s["SUPPLIER_ID"] for s in suppliers]
    
    for product in products:
        # Each product has 1-5 suppliers (avg ~3)
        num_suppliers = random.choices([1, 2, 3, 4, 5], weights=[10, 25, 40, 20, 5])[0]
        num_suppliers = min(num_suppliers, len(supplier_ids))
        
        product_supplier_ids = sample_without_replacement(supplier_ids, num_suppliers)
        
        # Ensure the product's default supplier is included
        default_supplier = product["SUPPLIER_ID"]
        if default_supplier not in product_supplier_ids:
            product_supplier_ids[0] = default_supplier
        
        for idx, supplier_id in enumerate(product_supplier_ids):
            # Supplier-specific pricing (varies around product cost)
            base_cost = product["COST"]
            supplier_price = round(base_cost * random.uniform(0.8, 1.2), 2)
            
            # First record for this product-supplier combination
            valid_from = random_timestamp(config.start_date, config.start_date + timedelta(days=180))
            
            # Is this the preferred supplier?
            is_preferred = (idx == 0)
            
            # Create current record
            product_suppliers.append({
                "PRODUCT_ID": product["PRODUCT_ID"],
                "SUPPLIER_ID": supplier_id,
                "SUPPLIER_PRICE": supplier_price,
                "AVAILABLE_QTY": random.randint(0, 10000),
                "LEAD_TIME_DAYS": random.randint(1, 45),
                "MIN_ORDER_QTY": random.choices([1, 5, 10, 25, 50, 100], weights=[40, 25, 15, 10, 7, 3])[0],
                "QUALITY_SCORE": round(bounded_normal(4.0, 0.5, 3.0, 5.0), 2),
                "IS_PREFERRED": is_preferred,
                "CONTRACT_START_DT": valid_from.date(),
                "CONTRACT_END_DT": None if random.random() > 0.2 else (valid_from + timedelta(days=random.randint(365, 1095))).date(),
                "VALID_FROM_TS": valid_from,
                "VALID_TO_TS": None,
                "IS_CURRENT": True,
                "CREATED_TS": valid_from,
                "UPDATED_TS": random_timestamp(valid_from, config.end_date),
            })
            
            # Optionally create historical records (price changes)
            # Only if there's enough time before the valid_from date
            days_since_start = (valid_from - config.start_date).days
            if random.random() < 0.3 and days_since_start > 60:  # 30% have price history
                num_historical = random.randint(1, min(3, days_since_start // 30))
                prev_valid_from = valid_from
                
                for h in range(num_historical):
                    # Historical record ends when current one starts
                    earliest_date = config.start_date
                    latest_date = prev_valid_from - timedelta(days=30)
                    
                    # Skip if no valid range
                    if latest_date <= earliest_date:
                        break
                    
                    hist_valid_from = random_timestamp(earliest_date, latest_date)
                    hist_price = round(supplier_price * random.uniform(0.85, 1.15), 2)
                    
                    product_suppliers.append({
                        "PRODUCT_ID": product["PRODUCT_ID"],
                        "SUPPLIER_ID": supplier_id,
                        "SUPPLIER_PRICE": hist_price,
                        "AVAILABLE_QTY": random.randint(0, 10000),
                        "LEAD_TIME_DAYS": random.randint(1, 45),
                        "MIN_ORDER_QTY": random.choices([1, 5, 10, 25, 50, 100], weights=[40, 25, 15, 10, 7, 3])[0],
                        "QUALITY_SCORE": round(bounded_normal(4.0, 0.5, 3.0, 5.0), 2),
                        "IS_PREFERRED": is_preferred,
                        "CONTRACT_START_DT": hist_valid_from.date(),
                        "CONTRACT_END_DT": None,
                        "VALID_FROM_TS": hist_valid_from,
                        "VALID_TO_TS": prev_valid_from,
                        "IS_CURRENT": False,
                        "CREATED_TS": hist_valid_from,
                        "UPDATED_TS": prev_valid_from,
                    })
                    
                    prev_valid_from = hist_valid_from
    
    return product_suppliers

"""
Entity creation examples.

This module demonstrates how to:
- Create simple entities with single join keys
- Create compound entities with multiple join keys
- Add descriptions for documentation

Tested in: tests/test_chapter_01.py::TestEntityExamples
"""
from snowflake.ml.feature_store import Entity


# =============================================================================
# Simple Entity (Single Key)
# =============================================================================

def create_user_entity() -> Entity:
    """
    Create a simple user entity with a single join key.
    
    Returns:
        Entity for user-level features
    """
    return Entity(
        name="USER",
        join_keys=["USER_ID"],
        desc="Registered user in the system"
    )


def create_product_entity() -> Entity:
    """
    Create a simple product entity.
    
    Returns:
        Entity for product-level features
    """
    return Entity(
        name="PRODUCT",
        join_keys=["PRODUCT_ID"],
        desc="Product in the catalog"
    )


def create_session_entity() -> Entity:
    """
    Create a session entity for clickstream data.
    
    Returns:
        Entity for session-level features
    """
    return Entity(
        name="SESSION",
        join_keys=["SESSION_ID"],
        desc="User browsing session"
    )


# =============================================================================
# Compound Entity (Multiple Keys)
# =============================================================================

def create_order_item_entity() -> Entity:
    """
    Create a compound entity for order line items.
    
    This demonstrates a composite primary key where both
    ORDER_ID and LINE_NUMBER are required to uniquely
    identify a record.
    
    Returns:
        Entity for order item-level features
    """
    return Entity(
        name="ORDER_ITEM",
        join_keys=["ORDER_ID", "LINE_NUMBER"],
        desc="Individual line item within an order"
    )


def create_product_supplier_entity() -> Entity:
    """
    Create a compound entity for product-supplier relationships.
    
    This represents a many-to-many relationship where a product
    can have multiple suppliers and a supplier can provide
    multiple products.
    
    Returns:
        Entity for product-supplier relationship features
    """
    return Entity(
        name="PRODUCT_SUPPLIER",
        join_keys=["PRODUCT_ID", "SUPPLIER_ID"],
        desc="Product-supplier relationship with pricing and availability"
    )


def create_user_product_entity() -> Entity:
    """
    Create a compound entity for user-product interactions.
    
    Useful for features that describe the relationship between
    a specific user and a specific product (e.g., purchase history,
    ratings, views).
    
    Returns:
        Entity for user-product interaction features
    """
    return Entity(
        name="USER_PRODUCT",
        join_keys=["USER_ID", "PRODUCT_ID"],
        desc="User interactions with a specific product"
    )


# =============================================================================
# Entity Instances (for import in other modules)
# =============================================================================

# Pre-created entities for use in examples
user_entity = create_user_entity()
product_entity = create_product_entity()
session_entity = create_session_entity()
order_item_entity = create_order_item_entity()
product_supplier_entity = create_product_supplier_entity()
user_product_entity = create_user_product_entity()


if __name__ == "__main__":
    # Demo: Print entity information
    entities = [
        user_entity,
        product_entity,
        session_entity,
        order_item_entity,
        product_supplier_entity,
        user_product_entity,
    ]
    
    print("=" * 60)
    print("ENTITY EXAMPLES")
    print("=" * 60)
    
    for entity in entities:
        key_type = "Simple" if len(entity.join_keys) == 1 else "Compound"
        print(f"\n{entity.name} ({key_type} Key)")
        print(f"  Join Keys: {entity.join_keys}")
        print(f"  Description: {entity.desc}")

"""
Compound entity examples.

This module demonstrates how to:
- Define compound (multi-key) entities
- Model many-to-many relationships
- Create intersection entities

Tested in: tests/test_chapter_03.py
"""
from snowflake.ml.feature_store import Entity


def create_product_supplier_entity() -> Entity:
    """Create a compound entity for product-supplier combinations."""
    return Entity(
        name="PRODUCT_SUPPLIER",
        join_keys=["PRODUCT_ID", "SUPPLIER_ID"],
        desc="Product and supplier combination for sourcing features"
    )


def create_user_product_entity() -> Entity:
    """Create a compound entity for user-product interactions."""
    return Entity(
        name="USER_PRODUCT",
        join_keys=["USER_ID", "PRODUCT_ID"],
        desc="User-product affinity features"
    )


def create_order_item_entity() -> Entity:
    """Create a compound entity for order line items."""
    return Entity(
        name="ORDER_ITEM",
        join_keys=["ORDER_ID", "LINE_NUMBER"],
        desc="Individual line item within an order"
    )


def get_compound_entities() -> dict:
    """Get a dictionary of compound entity definitions."""
    return {
        "product_supplier": create_product_supplier_entity(),
        "user_product": create_user_product_entity(),
        "order_item": create_order_item_entity(),
    }


if __name__ == "__main__":
    entities = get_compound_entities()
    for name, entity in entities.items():
        print(f"{name}: {entity.name} - {entity.join_keys}")

"""
Entity definition examples.

This module demonstrates how to:
- Define simple entities for the clickstream demo domain
- Create entity descriptions
- Register entities with Feature Store before Feature Views

Canonical environment: database FEATURE_STORE_DEMO, source schema CLICKSTREAM_DATA,
Feature Store schema FEATURE_STORE, warehouse FS_DEV_WH.

Tested in: tests/test_chapter_03.py
"""
from snowflake.ml.feature_store import Entity

DATABASE = "FEATURE_STORE_DEMO"
FEATURE_STORE_SCHEMA = "FEATURE_STORE"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
WAREHOUSE = "FS_DEV_WH"


def create_visitor_entity() -> Entity:
    """Create a visitor entity (pre- or non-login identity)."""
    return Entity(
        name="VISITOR",
        join_keys=["VISITOR_ID"],
        desc="Site visitor identified by cookie or device before login",
    )


def create_user_entity() -> Entity:
    """Create a simple user entity."""
    return Entity(
        name="USER",
        join_keys=["USER_ID"],
        desc="Registered user in the e-commerce platform"
    )


def create_product_entity() -> Entity:
    """Create a product entity."""
    return Entity(
        name="PRODUCT",
        join_keys=["PRODUCT_ID"],
        desc="Product in the catalog"
    )


def create_session_entity() -> Entity:
    """Create a session entity."""
    return Entity(
        name="SESSION",
        join_keys=["SESSION_ID"],
        desc="User browsing session"
    )


def create_household_entity() -> Entity:
    """Create a household rollup entity."""
    return Entity(
        name="HOUSEHOLD",
        join_keys=["HOUSEHOLD_ID"],
        desc="Household shared by one or more users",
    )


def create_category_entity() -> Entity:
    """Create a product category entity."""
    return Entity(
        name="CATEGORY",
        join_keys=["CATEGORY_ID"],
        desc="Product taxonomy category",
    )


def get_common_entities() -> dict:
    """Get a dictionary of common entity definitions."""
    return {
        "visitor": create_visitor_entity(),
        "user": create_user_entity(),
        "household": create_household_entity(),
        "product": create_product_entity(),
        "category": create_category_entity(),
        "session": create_session_entity(),
    }


if __name__ == "__main__":
    entities = get_common_entities()
    for name, entity in entities.items():
        print(f"{name}: {entity.name} - {entity.join_keys}")

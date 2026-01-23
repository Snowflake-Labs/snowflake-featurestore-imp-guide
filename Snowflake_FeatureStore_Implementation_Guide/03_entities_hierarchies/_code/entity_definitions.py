"""
Entity definition examples.

This module demonstrates how to:
- Define simple entities
- Create entity descriptions
- Register entities with Feature Store

Tested in: tests/test_chapter_03.py
"""
from snowflake.ml.feature_store import Entity


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


def get_common_entities() -> dict:
    """Get a dictionary of common entity definitions."""
    return {
        "user": create_user_entity(),
        "product": create_product_entity(),
        "session": create_session_entity(),
    }


if __name__ == "__main__":
    entities = get_common_entities()
    for name, entity in entities.items():
        print(f"{name}: {entity.name} - {entity.join_keys}")

"""
Clickstream entity hierarchy examples.

This module demonstrates how to:
- Model VISITOR → USER → HOUSEHOLD and PRODUCT → CATEGORY relationships
- Register entities before attaching them to Feature Views
- Name Feature View versions consistently (e.g. V01, V02)

Entities must be registered with the Feature Store (`fs.register_entity`) before use
in Feature Views; registering a Feature View does not create entities automatically.

Tested in: tests/test_chapter_03.py
"""
from __future__ import annotations

from snowflake.ml.feature_store import Entity, FeatureStore

# Canonical demo environment (aligns with setup_session / introduction)
DATABASE = "FEATURE_STORE_DEMO"
FEATURE_STORE_SCHEMA = "FEATURE_STORE"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
WAREHOUSE = "FS_DEV_WH"

# Recommended Feature View version labels for this guide
FEATUREVIEW_VERSION_INITIAL = "V01"


def create_visitor_entity() -> Entity:
    """Anonymous or pre-login visitor (e.g. cookie / device id)."""
    return Entity(
        name="VISITOR",
        join_keys=["VISITOR_ID"],
        desc="Site visitor identified before or without login",
    )


def create_user_entity() -> Entity:
    return Entity(
        name="USER",
        join_keys=["USER_ID"],
        desc="Registered user in the clickstream platform",
    )


def create_household_entity() -> Entity:
    return Entity(
        name="HOUSEHOLD",
        join_keys=["HOUSEHOLD_ID"],
        desc="Household rollup for users sharing an account or address",
    )


def create_session_entity() -> Entity:
    return Entity(
        name="SESSION",
        join_keys=["SESSION_ID"],
        desc="User browsing session containing events",
    )


def create_product_entity() -> Entity:
    return Entity(
        name="PRODUCT",
        join_keys=["PRODUCT_ID"],
        desc="Product in the catalog",
    )


def create_category_entity() -> Entity:
    return Entity(
        name="CATEGORY",
        join_keys=["CATEGORY_ID"],
        desc="Product taxonomy node",
    )


def create_order_entity() -> Entity:
    return Entity(
        name="ORDER",
        join_keys=["ORDER_ID"],
        desc="Customer order placed by a user",
    )


def get_hierarchy_entities() -> dict[str, Entity]:
    """Entities used in multi-level spine joins and rollups."""
    return {
        "visitor": create_visitor_entity(),
        "user": create_user_entity(),
        "household": create_household_entity(),
        "session": create_session_entity(),
        "product": create_product_entity(),
        "category": create_category_entity(),
        "order": create_order_entity(),
    }


def register_clickstream_entities(fs: FeatureStore) -> None:
    """
    Register all hierarchy entities on the Feature Store.

    Call this (or equivalent per-entity registration) before creating Feature Views
    that reference these entities.
    """
    for entity in get_hierarchy_entities().values():
        fs.register_entity(entity)


if __name__ == "__main__":
    for key, ent in get_hierarchy_entities().items():
        print(f"{key}: {ent.name} {ent.join_keys}")

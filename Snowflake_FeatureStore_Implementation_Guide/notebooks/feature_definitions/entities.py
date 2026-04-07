"""
Entity definitions for the Clickstream dataset.

Covers simple entities (single join key), compound entities (composite
join keys), and the entity hierarchy.

Hierarchy:
    VISITOR -> USER -> HOUSEHOLD
    PRODUCT -> CATEGORY
    PRODUCT_SUPPLIER (compound: PRODUCT_ID + SUPPLIER_ID)
    SESSION (child of VISITOR/USER)
"""

from snowflake.ml.feature_store import Entity


# ---------------------------------------------------------------------------
# Simple entities
# ---------------------------------------------------------------------------

def visitor_entity() -> Entity:
    return Entity(name="VISITOR", join_keys=["VISITOR_ID"], desc="Anonymous browser/device visitor")

def user_entity() -> Entity:
    return Entity(name="USER", join_keys=["USER_ID"], desc="Identified registered user")

def household_entity() -> Entity:
    return Entity(name="HOUSEHOLD", join_keys=["HOUSEHOLD_ID"], desc="Household grouping for user rollup")

def product_entity() -> Entity:
    return Entity(name="PRODUCT", join_keys=["PRODUCT_ID"], desc="Product in the catalog")

def category_entity() -> Entity:
    return Entity(name="CATEGORY", join_keys=["CATEGORY_ID"], desc="Product category")

def session_entity() -> Entity:
    return Entity(name="SESSION", join_keys=["SESSION_ID"], desc="Browsing session")

def supplier_entity() -> Entity:
    return Entity(name="SUPPLIER", join_keys=["SUPPLIER_ID"], desc="Product supplier/vendor")


# ---------------------------------------------------------------------------
# Compound entities
# ---------------------------------------------------------------------------

def product_supplier_entity() -> Entity:
    """M:N bridge entity – analogous to TPCH PARTSUPP."""
    return Entity(
        name="PRODUCT_SUPPLIER",
        join_keys=["PRODUCT_ID", "SUPPLIER_ID"],
        desc="Product-supplier relationship (composite key)",
    )


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def get_all_entities() -> dict[str, Entity]:
    """Return a dict of all entities keyed by name."""
    return {
        "VISITOR": visitor_entity(),
        "USER": user_entity(),
        "HOUSEHOLD": household_entity(),
        "PRODUCT": product_entity(),
        "CATEGORY": category_entity(),
        "SESSION": session_entity(),
        "SUPPLIER": supplier_entity(),
        "PRODUCT_SUPPLIER": product_supplier_entity(),
    }


def register_all(fs, session=None) -> dict[str, Entity]:
    """Register every entity in the Feature Store and return them.

    Idempotent – uses the FS API which handles duplicates gracefully.
    """
    entities = get_all_entities()
    for entity in entities.values():
        fs.register_entity(entity)
    return entities

"""
Feature Store organization patterns.

This module demonstrates how to:
- Create single Feature Stores
- Create domain-based Feature Stores
- Set up hybrid organization patterns

Tested in: tests/test_chapter_02.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, CreationMode


def create_single_feature_store(
    session: Session,
    database: str = "FEATURE_STORE_DEMO",
    name: str = "FEATURE_STORE",
    warehouse: str = "FS_DEV_WH",
) -> FeatureStore:
    """
    Create a single Feature Store - simplest organization pattern.
    
    Best for:
    - Small teams (1-5 data scientists)
    - Single ML project or use case
    - Quick proof-of-concept work
    
    Args:
        session: Active Snowpark session
        database: Database name
        name: Feature Store schema name
        warehouse: Default warehouse
        
    Returns:
        FeatureStore instance
    """
    return FeatureStore(
        session=session,
        database=database,
        name=name,
        default_warehouse=warehouse,
        creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
    )


def create_domain_feature_stores(
    session: Session,
    database: str = "FEATURE_STORE_DEMO",
) -> dict:
    """
    Create domain-based Feature Stores for multiple teams.
    
    Best for:
    - Multiple teams sharing a platform
    - Different domains with some shared features
    - Medium-sized organizations
    
    Args:
        session: Active Snowpark session
        database: Shared database name
        
    Returns:
        Dict of FeatureStore instances by domain
    """
    domains = {
        "marketing": FeatureStore(
            session=session,
            database=database,
            name="MARKETING",
            default_warehouse="FS_DEV_WH",
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        ),
        "fraud": FeatureStore(
            session=session,
            database=database,
            name="FRAUD",
            default_warehouse="FS_DEV_WH",
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        ),
        "shared": FeatureStore(
            session=session,
            database=database,
            name="SHARED",
            default_warehouse="FS_DEV_WH",
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        ),
    }
    return domains


if __name__ == "__main__":
    print("Organization pattern examples require an active Snowflake session.")

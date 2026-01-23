"""
Feature Store initialization.

This module demonstrates how to:
- Create a schema for source data
- Initialize a Feature Store
- Verify Feature Store creation

Tested in: tests/test_chapter_00.py::test_create_feature_store
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, CreationMode


def create_feature_store(
    session: Session,
    database: str,
    name: str,
    warehouse: str,
    source_schema: str = None,
) -> FeatureStore:
    """
    Initialize a Snowflake Feature Store.
    
    Args:
        session: Active Snowpark Session
        database: Database name for the Feature Store
        name: Name of the Feature Store (becomes a schema)
        warehouse: Default warehouse for compute
        source_schema: Optional schema for source data (created if provided)
        
    Returns:
        Initialized FeatureStore instance
    """
    # Create source data schema if specified
    if source_schema:
        session.sql(f'CREATE SCHEMA IF NOT EXISTS {database}.{source_schema}').collect()
        print(f'Source schema ready: {database}.{source_schema}')
    
    # Initialize Feature Store
    # This creates a schema with Feature Store metadata tags
    fs = FeatureStore(
        session=session,
        database=database,
        name=name,
        default_warehouse=warehouse,
        creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
    )
    
    print(f'Feature Store initialized: {database}.{name}')
    
    return fs


if __name__ == "__main__":
    from setup_session import create_session, SOURCE_DATABASE, SOURCE_SCHEMA, FS_NAME, WAREHOUSE
    
    session = create_session()
    fs = create_feature_store(
        session=session,
        database=SOURCE_DATABASE,
        name=FS_NAME,
        warehouse=WAREHOUSE,
        source_schema=SOURCE_SCHEMA,
    )
    print(f"Feature Store ready: {fs}")

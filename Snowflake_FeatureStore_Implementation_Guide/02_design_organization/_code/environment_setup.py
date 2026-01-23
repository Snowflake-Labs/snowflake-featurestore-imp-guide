"""
Environment setup for dev/test/prod Feature Stores.

This module demonstrates how to:
- Set up schema-based environments
- Set up database-based environments
- Configure environment-specific warehouses

Tested in: tests/test_chapter_02.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, CreationMode


def create_schema_based_environments(
    session: Session,
    database: str = "ML_FEATURES",
) -> dict:
    """
    Create schema-based environments (DEV/TEST/PROD) in same database.
    
    This is the recommended starting pattern for most teams.
    
    Args:
        session: Active Snowpark session
        database: Database name
        
    Returns:
        Dict of FeatureStore instances by environment
    """
    environments = {}
    
    for env, warehouse in [("DEV", "DEV_WH"), ("TEST", "TEST_WH"), ("PROD", "PROD_WH")]:
        environments[env.lower()] = FeatureStore(
            session=session,
            database=database,
            name=env,
            default_warehouse=warehouse,
            creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
        )
    
    return environments


def setup_environment_warehouses(session: Session) -> None:
    """
    Create environment-specific warehouses with appropriate sizing.
    
    Args:
        session: Active Snowpark session
    """
    warehouses = [
        ("DEV_WH", "XSMALL", 60),
        ("TEST_WH", "SMALL", 120),
        ("PROD_WH", "MEDIUM", 300),
        ("PROD_OFT_WH", "SMALL", 60),  # For Online Feature Table refresh
    ]
    
    for name, size, auto_suspend in warehouses:
        session.sql(f"""
            CREATE WAREHOUSE IF NOT EXISTS {name}
            WITH WAREHOUSE_SIZE = '{size}'
            AUTO_SUSPEND = {auto_suspend}
            AUTO_RESUME = TRUE
        """).collect()
        print(f"Created/verified warehouse: {name}")


if __name__ == "__main__":
    print("Environment setup examples require an active Snowflake session.")

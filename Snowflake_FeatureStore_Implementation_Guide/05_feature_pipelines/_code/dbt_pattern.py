"""
DBT + Feature Store integration pattern.

This module demonstrates how to:
- Register DBT-managed tables as View-based Feature Views
- Integrate external orchestration with Feature Store

Tested in: tests/test_chapter_05.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def register_dbt_feature_view(
    session: Session,
    fs: FeatureStore,
    dbt_table: str,
    entity: Entity,
    timestamp_col: str = "_DBT_UPDATED_TS",
    version: str = "V01",
) -> FeatureView:
    """
    Register a DBT-managed table as a View-based Feature View.
    
    This pattern is used when DBT handles the transformation logic
    and Feature Store provides PIT retrieval and serving.
    
    Args:
        session: Active Snowpark session
        fs: FeatureStore instance
        dbt_table: Fully qualified DBT table name
        entity: Entity for the Feature View
        timestamp_col: Column containing last update timestamp
        version: Version string
        
    Returns:
        Registered Feature View
    """
    # Reference DBT table directly
    feature_df = session.table(dbt_table)
    
    # Extract table name for Feature View naming
    fv_name = dbt_table.split(".")[-1]
    
    # Create View-based Feature View (no refresh_freq)
    fv = FeatureView(
        name=fv_name,
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        # No refresh_freq → View-based (DBT handles refresh)
        desc=f"DBT-managed feature table: {dbt_table}"
    )
    
    return fs.register_feature_view(
        feature_view=fv,
        version=version,
    )


def get_dbt_feature_table_info(
    session: Session,
    schema: str = "FEATURE_STORE",
) -> list:
    """
    List DBT feature tables in a schema.
    
    Args:
        session: Active Snowpark session
        schema: Schema containing DBT tables
        
    Returns:
        List of table info dicts
    """
    result = session.sql(f"""
        SELECT 
            TABLE_NAME,
            ROW_COUNT,
            CREATED,
            LAST_ALTERED,
            COMMENT
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY LAST_ALTERED DESC
    """).collect()
    
    return [
        {
            "table_name": row["TABLE_NAME"],
            "row_count": row["ROW_COUNT"],
            "created": row["CREATED"],
            "last_altered": row["LAST_ALTERED"],
            "comment": row["COMMENT"],
        }
        for row in result
    ]


if __name__ == "__main__":
    print("DBT pattern examples require an active Snowflake session.")

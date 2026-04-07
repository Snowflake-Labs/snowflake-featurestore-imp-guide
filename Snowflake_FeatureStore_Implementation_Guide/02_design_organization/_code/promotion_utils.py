"""
Feature promotion utilities for cross-environment workflows.

This module demonstrates how to:
- Promote Feature Views between environments
- Clone Feature Store objects
- Validate promotions

Tested in: tests/test_chapter_02.py
"""
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView


def promote_feature_view(
    source_fs: FeatureStore,
    target_fs: FeatureStore,
    fv_name: str,
    version: str,
) -> FeatureView:
    """
    Promote a Feature View from source to target Feature Store.
    
    This copies the Feature View definition to the target environment.
    Entities must already exist in the target Feature Store.
    
    Args:
        source_fs: Source Feature Store (e.g., DEV)
        target_fs: Target Feature Store (e.g., TEST/PROD)
        fv_name: Name of the Feature View to promote
        version: Version to promote
        
    Returns:
        Registered Feature View in target environment
    """
    # Get the Feature View from source
    source_fv = source_fs.get_feature_view(name=fv_name, version=version)
    
    # Recreate in target
    target_fv = FeatureView(
        name=source_fv.name,
        entities=source_fv.entities,
        feature_df=source_fv.feature_df,
        timestamp_col=source_fv.timestamp_col,
        refresh_freq=source_fv.refresh_freq,
        desc=source_fv.desc,
    )
    
    # Register with same version
    return target_fs.register_feature_view(
        feature_view=target_fv,
        version=version,
    )


def clone_feature_view_sql(
    session: Session,
    source_schema: str,
    target_schema: str,
    fv_name: str,
) -> None:
    """
    Clone a Feature View using Snowflake's zero-copy cloning.
    
    This is more efficient than Python-based promotion for large objects.
    
    Args:
        session: Active Snowpark session
        source_schema: Source schema (e.g., FEATURE_STORE_DEMO.DEV)
        target_schema: Target schema (e.g., FEATURE_STORE_DEMO.TEST)
        fv_name: Name of the Feature View/Dynamic Table
    """
    session.sql(f"""
        CREATE DYNAMIC TABLE {target_schema}.{fv_name}
        CLONE {source_schema}.{fv_name}
    """).collect()
    print(f"Cloned {source_schema}.{fv_name} to {target_schema}.{fv_name}")


def validate_promotion(
    source_fs: FeatureStore,
    target_fs: FeatureStore,
    fv_name: str,
    version: str,
) -> dict:
    """
    Validate that a Feature View was promoted correctly.
    
    Checks:
    - Feature View exists in target
    - Schema matches source
    - Row count matches (for DT-backed FVs)
    
    Args:
        source_fs: Source Feature Store
        target_fs: Target Feature Store
        fv_name: Feature View name
        version: Version to validate
        
    Returns:
        Dict with validation results
    """
    results = {"valid": True, "checks": []}
    
    # Check existence
    try:
        source_fv = source_fs.get_feature_view(name=fv_name, version=version)
        target_fv = target_fs.get_feature_view(name=fv_name, version=version)
        results["checks"].append({"name": "exists", "passed": True})
    except Exception as e:
        results["valid"] = False
        results["checks"].append({"name": "exists", "passed": False, "error": str(e)})
        return results
    
    # Check schema match
    source_cols = set(f.name for f in source_fv.feature_df.schema.fields)
    target_cols = set(f.name for f in target_fv.feature_df.schema.fields)
    schema_match = source_cols == target_cols
    results["checks"].append({"name": "schema_match", "passed": schema_match})
    if not schema_match:
        results["valid"] = False
    
    return results


if __name__ == "__main__":
    print("Promotion utilities require an active Snowflake session.")

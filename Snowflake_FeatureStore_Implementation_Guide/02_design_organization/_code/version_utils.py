"""
FeatureView version management utilities.

This module demonstrates how to:
- Get the latest version of a FeatureView
- List all versions
- Compare versions

Tested in: tests/test_chapter_02.py
"""
from snowflake.ml.feature_store import FeatureStore, FeatureView
from typing import Optional, List


def get_latest_feature_view(
    fs: FeatureStore,
    feature_view_name: str,
) -> Optional[FeatureView]:
    """
    Get the most recent version of a FeatureView.
    
    Assumes zero-padded version names (V01, V02, etc.) for correct sorting.
    
    Args:
        fs: FeatureStore instance
        feature_view_name: Name of the FeatureView
        
    Returns:
        Latest FeatureView or None if not found
    """
    versions = list(fs.list_feature_views(feature_view_name=feature_view_name).collect())
    
    if not versions:
        return None
    
    # Sort by version string (works with zero-padded versions)
    versions_sorted = sorted(versions, key=lambda fv: fv.version, reverse=True)
    
    latest = versions_sorted[0]
    return fs.get_feature_view(name=latest.name, version=latest.version)


def list_feature_view_versions(
    fs: FeatureStore,
    feature_view_name: str,
) -> List[str]:
    """
    List all versions of a FeatureView.
    
    Args:
        fs: FeatureStore instance
        feature_view_name: Name of the FeatureView
        
    Returns:
        List of version strings sorted newest first
    """
    versions = list(fs.list_feature_views(feature_view_name=feature_view_name).collect())
    return sorted([fv.version for fv in versions], reverse=True)


def compare_feature_view_versions(
    fs: FeatureStore,
    feature_view_name: str,
    version_a: str,
    version_b: str,
) -> dict:
    """
    Compare two versions of a FeatureView.
    
    Args:
        fs: FeatureStore instance
        feature_view_name: Name of the FeatureView
        version_a: First version
        version_b: Second version
        
    Returns:
        Dict with comparison results
    """
    fv_a = fs.get_feature_view(name=feature_view_name, version=version_a)
    fv_b = fs.get_feature_view(name=feature_view_name, version=version_b)
    
    cols_a = set(f.name for f in fv_a.feature_df.schema.fields)
    cols_b = set(f.name for f in fv_b.feature_df.schema.fields)
    
    return {
        "version_a": version_a,
        "version_b": version_b,
        "columns_added": list(cols_b - cols_a),
        "columns_removed": list(cols_a - cols_b),
        "columns_unchanged": list(cols_a & cols_b),
    }


if __name__ == "__main__":
    print("Version utilities require an active Snowflake session.")

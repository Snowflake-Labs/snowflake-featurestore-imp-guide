"""
Feature View versioning utilities.

Uses canonical Feature View names (e.g. USER_ORDER_FV, PRODUCT_CATALOG_FV)
and zero-padded versions (V01, V02) with FEATURE_STORE_DEMO.FEATURE_STORE.

This module demonstrates how to:
- Version Feature Views correctly
- List and manage versions
- Get the latest version

Tested in: tests/test_chapter_04.py
"""
from snowflake.ml.feature_store import FeatureStore
from typing import Optional, List


def get_version_naming_examples() -> dict:
    """
    Get examples of version naming conventions.

    Returns:
        Dict with version naming examples
    """
    return {
        "zero_padded": {
            "pattern": "V01, V02, ..., V10",
            "examples": ["V01", "V02", "V03", "V10"],
            "pros": "Sorts correctly lexicographically",
            "cons": "Limited to 99 versions with 2 digits",
        },
        "environment_prefixed": {
            "pattern": "<ENV>_V<NUM>",
            "examples": ["DEV_V01", "TEST_V01", "PROD_V01"],
            "pros": "Clear environment context",
            "cons": "Same FV can have different versions per env",
        },
        "semantic": {
            "pattern": "MAJOR.MINOR.PATCH",
            "examples": ["1.0.0", "1.1.0", "2.0.0"],
            "pros": "Conveys change significance",
            "cons": "More complex to manage",
        },
        "date_based": {
            "pattern": "YYYYMMDD",
            "examples": ["20250115", "20250116"],
            "pros": "Easy to identify when created",
            "cons": "Multiple versions per day need suffix",
        },
    }


def get_latest_version(
    fs: FeatureStore,
    fv_name: str,
) -> Optional[str]:
    """
    Get the latest version string for a Feature View.

    Args:
        fs: FeatureStore instance
        fv_name: Feature View name

    Returns:
        Latest version string or None
    """
    versions = list(fs.list_feature_views(feature_view_name=fv_name).collect())

    if not versions:
        return None

    return sorted([v.version for v in versions], reverse=True)[0]


def list_versions(
    fs: FeatureStore,
    fv_name: str,
) -> List[str]:
    """
    List all versions for a Feature View.

    Args:
        fs: FeatureStore instance
        fv_name: Feature View name

    Returns:
        List of version strings
    """
    versions = list(fs.list_feature_views(feature_view_name=fv_name).collect())
    return sorted([v.version for v in versions])


if __name__ == "__main__":
    examples = get_version_naming_examples()
    print("Version Naming Conventions:")
    for name, details in examples.items():
        print(f"\n{name}:")
        print(f"  Pattern: {details['pattern']}")
        print(f"  Examples: {details['examples']}")

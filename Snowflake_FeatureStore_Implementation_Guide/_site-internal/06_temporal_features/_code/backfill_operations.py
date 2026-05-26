"""
Backfill and manual refresh operations for Feature Views.

Use with Dynamic Table-backed Feature Views (refresh_freq set). View-backed
Feature Views compute at query time and do not require refresh for backfill
semantics.

Canonical registration uses version strings such as "V01", "V02".

Tested in: tests/test_chapter_06.py
"""
from snowflake.ml.feature_store import FeatureStore, FeatureView


def refresh_feature_view_now(
    fs: FeatureStore,
    registered_fv: FeatureView,
) -> None:
    """
    Trigger a manual refresh of a registered Dynamic Table-backed Feature View.

    Wraps fs.refresh_feature_view(registered_fv). Use after pipeline fixes,
    scope changes, or when you need materialization before the next scheduled
    refresh.
    """
    fs.refresh_feature_view(registered_fv)


def register_initial_version(
    fs: FeatureStore,
    feature_view: FeatureView,
    version: str = "V01",
    block: bool = True,
) -> FeatureView:
    """Register a Feature View at a given version (default V01)."""
    return fs.register_feature_view(
        feature_view=feature_view,
        version=version,
        block=block,
    )


if __name__ == "__main__":
    print("backfill_operations require an active Feature Store session.")

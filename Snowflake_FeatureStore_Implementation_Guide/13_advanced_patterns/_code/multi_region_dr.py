"""
Multi-region and disaster recovery for Feature Store deployments.

Full DR architecture is account-specific; use Snowflake docs for planning.

Tested in: tests/test_chapter_12.py
"""

from __future__ import annotations


def get_multi_region_dr_considerations() -> dict:
    """
    Summary points for documentation and onboarding (not a runbook).

    Returns:
        Dict of DR / multi-region topics aligned with Snowflake capabilities.
    """
    return {
        "database_replication": (
            "Snowflake database replication can replicate Feature Store "
            "schemas (FEATURE_STORE) and underlying objects subject to "
            "replication support and licensing."
        ),
        "feature_definitions": (
            "Feature definitions (Feature Views) can be promoted via clone, "
            "CI/CD redeploy, or definition-only replication patterns "
            "depending on whether metadata and dynamic tables must match "
            "exactly across regions."
        ),
        "online_feature_tables": (
            "Online Feature Tables are provisioned per region; expect "
            "separate setup, sync strategy, and serving endpoints in each "
            "primary/secondary."
        ),
        "scope": (
            "End-to-end multi-region and DR planning is beyond this guide; "
            "refer to current Snowflake documentation on replication, "
            "failover, and business continuity."
        ),
    }

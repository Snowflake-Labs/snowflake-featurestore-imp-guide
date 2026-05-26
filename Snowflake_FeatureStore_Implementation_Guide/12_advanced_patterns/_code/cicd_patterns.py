"""
CI/CD patterns for Feature Store.

This module demonstrates how to:
- Define features as code
- Automate deployments
- Test feature pipelines

Tested in: tests/test_chapter_12.py
"""


def get_feature_config_template() -> dict:
    """
    Get template for feature configuration as code.

    Returns:
        Dict with feature configuration template
    """
    return {
        "name": "USER_ORDER_FV",
        "version": "V01",
        "entities": ["USER"],
        "query": """
            SELECT
                USER_ID,
                COUNT(*) AS ORDER_CNT,
                SUM(TOTAL_AMT) AS TOTAL_AMT_SUM,
                MAX(ORDER_TS) AS LAST_ORDER_TS
            FROM FEATURE_STORE_DEMO.CLICKSTREAM_DATA.ORDERS
            GROUP BY USER_ID
        """,
        "timestamp_col": "LAST_ORDER_TS",
        "refresh_freq": "1 hour",
        "description": "User purchase behavior features",
        "owner": "ml-platform@company.com",
        "sla": {
            "max_lag_minutes": 90,
            "availability": "99.9%",
        },
    }


def get_deployment_workflow() -> dict:
    """
    Get CI/CD workflow configuration.

    Returns:
        Dict with workflow configuration
    """
    return {
        "trigger": {
            "branches": ["main"],
            "paths": ["features/**"],
        },
        "steps": [
            {
                "name": "Validate Configuration",
                "command": "python scripts/validate_features.py",
            },
            {
                "name": "Run Tests",
                "command": "pytest tests/features/",
            },
            {
                "name": "Deploy to DEV",
                "command": "python scripts/deploy_features.py --env DEV",
            },
            {
                "name": "Integration Tests",
                "command": "pytest tests/integration/",
            },
            {
                "name": "Deploy to PROD",
                "command": "python scripts/deploy_features.py --env PROD",
                "requires_approval": True,
            },
        ],
    }


def reconcile_feature_state(
    fs,
    desired: list[dict],
) -> dict:
    """
    Compare desired feature config against live Feature Store state.

    Parameters:
        fs: FeatureStore instance
        desired: List of dicts, each with at least "name" and "version" keys

    Returns:
        Dict with keys: missing_in_live, unexpected_in_live,
        version_mismatch, in_sync (bool)
    """
    live_fvs = {
        fv.name: [v.version for v in fv.versions]
        for fv in fs.list_feature_views()
    }
    desired_map = {d["name"]: d["version"] for d in desired}

    missing = [n for n in desired_map if n not in live_fvs]
    extra = [n for n in live_fvs if n not in desired_map]
    mismatch = [
        n
        for n in desired_map
        if n in live_fvs and desired_map[n] not in live_fvs[n]
    ]

    return {
        "missing_in_live": missing,
        "unexpected_in_live": extra,
        "version_mismatch": mismatch,
        "in_sync": len(missing) == 0
        and len(extra) == 0
        and len(mismatch) == 0,
    }


if __name__ == "__main__":
    template = get_feature_config_template()
    print("Feature Configuration Template:")
    print(f"  Name: {template['name']}")
    print(f"  Version: {template['version']}")
    print(f"  Refresh: {template['refresh_freq']}")

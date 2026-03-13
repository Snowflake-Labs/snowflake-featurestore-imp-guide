"""
Deployment script for Feature Store feature views.

This module demonstrates how to:
- Deploy feature views from configuration (feature-as-code)
- Resolve entities and build FeatureViews programmatically
- Integrate with CI/CD pipelines (called by feature-deploy.yml)

Usage:
    python scripts/deploy_features.py --env DEV
    python scripts/deploy_features.py --env PROD --config features/user_features.yaml

Tested in: tests/test_chapter_12.py
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from snowflake.snowpark import Session
from snowflake.ml.feature_store import (
    CreationMode,
    Entity,
    FeatureStore,
    FeatureView,
)


DEFAULT_CONFIGS: Dict[str, dict] = {
    "user_purchase_features": {
        "name": "USER_PURCHASE_FEATURES",
        "version": "V01",
        "entities": ["USER"],
        "query": """
            SELECT
                USER_ID,
                COUNT(*) AS ORDER_CNT,
                SUM(AMOUNT) AS TOTAL_SPEND,
                MAX(ORDER_TS) AS LAST_ORDER_TS
            FROM ORDERS
            GROUP BY USER_ID
        """,
        "timestamp_col": "LAST_ORDER_TS",
        "refresh_freq": "1 hour",
        "description": "User purchase behavior features",
        "warehouse": None,
    },
}

ENV_SETTINGS: Dict[str, dict] = {
    "DEV": {
        "database": "FEATURE_STORE_DEV",
        "schema": "FEATURES",
        "warehouse": "DEV_WH",
        "creation_mode": CreationMode.CREATE_IF_NOT_EXIST,
    },
    "PROD": {
        "database": "FEATURE_STORE_PROD",
        "schema": "FEATURES",
        "warehouse": "PROD_WH",
        "creation_mode": CreationMode.CREATE_IF_NOT_EXIST,
    },
}


def create_session() -> Session:
    connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        return Session.builder.config("connection_name", connection_name).create()

    return Session.builder.configs({
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "private_key_file": os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE", ""),
        "role": os.getenv("SNOWFLAKE_ROLE", "SYSADMIN"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": os.getenv("SNOWFLAKE_DATABASE", ""),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", ""),
    }).create()


def resolve_entities(
    fs: FeatureStore,
    entity_names: List[str],
) -> List[Entity]:
    resolved = []
    for name in entity_names:
        try:
            entity = fs.get_entity(name)
            resolved.append(entity)
        except Exception as exc:
            print(f"ERROR: Entity '{name}' not found in Feature Store: {exc}")
            raise
    return resolved


def deploy_feature_view(
    fs: FeatureStore,
    session: Session,
    config: dict,
    environment: str,
    warehouse: Optional[str] = None,
) -> FeatureView:
    entities = resolve_entities(fs, config["entities"])

    feature_df = session.sql(config["query"])

    fv = FeatureView(
        name=config["name"],
        entities=entities,
        feature_df=feature_df,
        timestamp_col=config.get("timestamp_col"),
        refresh_freq=config.get("refresh_freq"),
        desc=config.get("description"),
        warehouse=warehouse or config.get("warehouse"),
    )

    version = f"{environment}_{config['version']}"

    try:
        registered_fv = fs.register_feature_view(
            feature_view=fv,
            version=version,
            block=True,
        )
    except Exception as exc:
        if "already exists" in str(exc).lower():
            print(f"WARN: {config['name']}/{version} already exists, skipping.")
            return fs.get_feature_view(config["name"], version)
        raise

    print(f"Deployed: {config['name']}/{version}")
    fv_type = "managed" if config.get("refresh_freq") else "external"
    print(f"  type={fv_type}, refresh_freq={config.get('refresh_freq', 'N/A')}")
    return registered_fv


def load_configs(config_path: Optional[str] = None) -> List[dict]:
    if config_path:
        path = Path(config_path)
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                with open(path) as f:
                    data = yaml.safe_load(f)
            except ImportError:
                print("ERROR: PyYAML required for YAML configs. pip install pyyaml")
                sys.exit(1)
        else:
            with open(path) as f:
                data = json.load(f)

        if isinstance(data, list):
            return data
        return [data]

    return list(DEFAULT_CONFIGS.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Feature Store feature views")
    parser.add_argument(
        "--env",
        required=True,
        choices=["DEV", "PROD"],
        help="Target environment",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to feature config file (JSON or YAML)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configs without deploying",
    )
    args = parser.parse_args()

    env = ENV_SETTINGS[args.env]
    configs = load_configs(args.config)
    print(f"Environment: {args.env}")
    print(f"Database: {env['database']}, Schema: {env['schema']}")
    print(f"Feature views to deploy: {len(configs)}")

    if args.dry_run:
        for cfg in configs:
            print(f"  [DRY RUN] Would deploy: {cfg['name']}/{args.env}_{cfg['version']}")
        return

    session = create_session()
    try:
        fs = FeatureStore(
            session=session,
            database=env["database"],
            name=env["schema"],
            default_warehouse=env["warehouse"],
            creation_mode=env["creation_mode"],
        )

        deployed = []
        failed = []
        for cfg in configs:
            try:
                fv = deploy_feature_view(
                    fs=fs,
                    session=session,
                    config=cfg,
                    environment=args.env,
                    warehouse=env["warehouse"],
                )
                deployed.append(fv)
            except Exception as exc:
                print(f"FAILED: {cfg['name']} — {exc}")
                failed.append(cfg["name"])

        print(f"\nDeployment summary: {len(deployed)} succeeded, {len(failed)} failed")
        if failed:
            print(f"Failed: {', '.join(failed)}")
            sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()

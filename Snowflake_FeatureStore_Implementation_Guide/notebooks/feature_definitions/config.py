"""
Environment configuration for Feature Store notebooks.

All database, schema, warehouse, and role names are parameterised here.
Override any value via environment variables (prefix FS_) or by editing
the ENVIRONMENTS dict directly.

Aligned with Chapter 02: "never hard-code environment names".
"""

import os
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Environment definitions
# ---------------------------------------------------------------------------

ENVIRONMENTS = {
    "DEV": {
        "database": os.environ.get("FS_DEV_DATABASE", "FEATURE_STORE_DEMO_DEV"),
        "source_schema": os.environ.get("FS_SOURCE_SCHEMA", "CLICKSTREAM_DATA"),
        "admin_schema": os.environ.get("FS_ADMIN_SCHEMA", "CLICKSTREAM_ADMIN"),
        "fs_schema": os.environ.get("FS_SCHEMA", "FEATURE_STORE"),
        "training_schema": os.environ.get("FS_TRAINING_SCHEMA", "TRAINING_DATA"),
        "inference_schema": os.environ.get("FS_INFERENCE_SCHEMA", "INFERENCE_DATA"),
        "spines_schema": os.environ.get("FS_SPINES_SCHEMA", "SPINES"),
        "ml_datasets_schema": os.environ.get("FS_ML_DATASETS_SCHEMA", "ML_DATASETS"),
        "warehouse": os.environ.get("FS_DEV_WAREHOUSE", "FS_DEV_WH"),
        "warehouse_size": os.environ.get("FS_DEV_WAREHOUSE_SIZE", "X-SMALL"),
        "refresh_warehouse": os.environ.get("FS_REFRESH_WAREHOUSE", "FS_REFRESH_WH"),
        "serving_warehouse": os.environ.get("FS_SERVING_WAREHOUSE", "FS_SERVING_WH"),
    },
    "PROD": {
        "database": os.environ.get("FS_PROD_DATABASE", "FEATURE_STORE_DEMO"),
        "source_schema": os.environ.get("FS_SOURCE_SCHEMA", "CLICKSTREAM_DATA"),
        "admin_schema": os.environ.get("FS_ADMIN_SCHEMA", "CLICKSTREAM_ADMIN"),
        "fs_schema": os.environ.get("FS_SCHEMA", "FEATURE_STORE"),
        "training_schema": os.environ.get("FS_TRAINING_SCHEMA", "TRAINING_DATA"),
        "inference_schema": os.environ.get("FS_INFERENCE_SCHEMA", "INFERENCE_DATA"),
        "spines_schema": os.environ.get("FS_SPINES_SCHEMA", "SPINES"),
        "ml_datasets_schema": os.environ.get("FS_ML_DATASETS_SCHEMA", "ML_DATASETS"),
        "warehouse": os.environ.get("FS_PROD_WAREHOUSE", "FS_DEV_WH"),
        "warehouse_size": os.environ.get("FS_PROD_WAREHOUSE_SIZE", "X-SMALL"),
        "refresh_warehouse": os.environ.get("FS_REFRESH_WAREHOUSE", "FS_REFRESH_WH"),
        "serving_warehouse": os.environ.get("FS_SERVING_WAREHOUSE", "FS_SERVING_WH"),
    },
}

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ROLES = {
    "admin": os.environ.get("FS_ADMIN_ROLE", "FS_ADMIN_ROLE"),
    "dev": os.environ.get("FS_DEV_ROLE", "FS_DEV_ROLE"),
    "consumer": os.environ.get("FS_CONSUMER_ROLE", "FS_CONSUMER_ROLE"),
}

# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

DATA_SCALE = float(os.environ.get("FS_DATA_SCALE", "0.01"))

# ---------------------------------------------------------------------------
# Feature View version convention
# ---------------------------------------------------------------------------

FEATUREVIEW_VERSION_INITIAL = "V01"

# ---------------------------------------------------------------------------
# Connection profile (for local development outside Workspace Notebooks)
# ---------------------------------------------------------------------------

CONNECTION_PROFILE = os.environ.get("FS_CONNECTION_PROFILE", "ak32940_remote_dev")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_config(env: Optional[str] = None) -> dict:
    """Return the config dict for the given environment.

    Args:
        env: ``"DEV"`` or ``"PROD"``.  Defaults to the ``FS_ENV``
             environment variable, falling back to ``"DEV"``.
    """
    env = (env or os.environ.get("FS_ENV", "DEV")).upper()
    if env not in ENVIRONMENTS:
        raise ValueError(f"Unknown environment '{env}'. Choose from: {list(ENVIRONMENTS)}")
    return ENVIRONMENTS[env]


def fq_table(env: str, table: str, schema_key: str = "source_schema") -> str:
    """Return a fully-qualified ``database.schema.table`` name.

    Example::

        fq_table("DEV", "ORDERS")
        # -> "FEATURE_STORE_DEMO_DEV.CLICKSTREAM_DATA.ORDERS"
    """
    cfg = get_config(env)
    return f"{cfg['database']}.{cfg[schema_key]}.{table}"


_SPCS_TOKEN_PATH = Path("/snowflake/session/token")


def is_workspace() -> bool:
    """Detect if running inside a Snowflake Workspace
    (SPCS container with injected OAuth token)."""
    return (
        _SPCS_TOKEN_PATH.is_file()
        and os.environ.get("SNOWFLAKE_HOST") is not None
    )


def get_session(role: Optional[str] = None):
    """Create a Snowpark Session.

    Inside Workspace Notebooks ``get_active_session()``
    is used automatically.  Locally, falls back to key-pair
    auth via ``FS_PRIVATE_KEY_PATH``.
    """
    try:
        from snowflake.snowpark.context import (
            get_active_session,
        )
        session = get_active_session()
    except Exception:
        from snowflake.snowpark import Session
        from cryptography.hazmat.primitives import (
            serialization,
        )
        from cryptography.hazmat.backends import (
            default_backend,
        )

        key_path = os.environ.get(
            "FS_PRIVATE_KEY_PATH",
            os.path.expanduser(
                "~/.snowflake/keys/simon_rsa_key.p8"
            ),
        )
        with open(key_path, "rb") as f:
            pk = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend(),
            )
        pkb = pk.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        session = Session.builder.configs(
            {
                "account": os.environ.get(
                    "FS_ACCOUNT", "ak32940"
                ),
                "user": os.environ.get(
                    "FS_USER", "SIMON"
                ),
                "private_key": pkb,
                "role": role or ROLES["admin"],
                "warehouse": ENVIRONMENTS["DEV"][
                    "warehouse"
                ],
                "database": ENVIRONMENTS["DEV"][
                    "database"
                ],
                "schema": ENVIRONMENTS["DEV"][
                    "source_schema"
                ],
            }
        ).create()

    if role:
        session.sql(f"USE ROLE {role}").collect()
    return session


def workspace_session_factory(
    role: Optional[str] = None,
    warehouse: Optional[str] = None,
    database: Optional[str] = None,
    schema: Optional[str] = None,
):
    """Return a callable that creates independent Snowpark
    sessions using the SPCS OAuth token.

    Each call to the returned function:
      1. Re-reads ``/snowflake/session/token`` (handles
         platform token refresh for long-running workloads)
      2. Connects via ``SNOWFLAKE_HOST`` (internal SPCS
         gateway) with ``authenticator=oauth``
      3. Returns a new, independent ``Session``

    Only usable inside a Workspace container.
    """
    host = os.environ.get("SNOWFLAKE_HOST", "")
    account = os.environ.get("SNOWFLAKE_ACCOUNT", "")

    def _create():
        from snowflake.snowpark import Session
        token = _SPCS_TOKEN_PATH.read_text().strip()
        cfg_dict = {
            "host": host,
            "account": account,
            "authenticator": "oauth",
            "token": token,
        }
        if role:
            cfg_dict["role"] = role
        if warehouse:
            cfg_dict["warehouse"] = warehouse
        if database:
            cfg_dict["database"] = database
        if schema:
            cfg_dict["schema"] = schema
        return Session.builder.configs(cfg_dict).create()

    return _create

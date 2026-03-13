"""
Session setup and environment configuration.

This module demonstrates how to:
- Import required packages
- Create a Snowpark session
- Configure the Feature Store environment

Tested in: tests/test_chapter_00.py::test_session_setup
"""
# ==============================================================================
# IMPORTS
# ==============================================================================

# Python standard library
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal

# Data processing
import pandas as pd
import numpy as np

# Snowpark
from snowflake.snowpark import Session
from snowflake.snowpark.version import VERSION
from snowflake.snowpark import functions as F
from snowflake.snowpark import types as T
from snowflake.snowpark.context import get_active_session

# Feature Store
from snowflake.ml.feature_store import (
    FeatureStore, 
    FeatureView, 
    Entity,
    CreationMode
)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Default configuration - override as needed
SOURCE_DATABASE = '...'
SOURCE_SCHEMA = '...'
FS_NAME = '...'
WAREHOUSE = '...'


# ==============================================================================
# SESSION CREATION
# ==============================================================================

def create_session(connection_params: dict = None, connection_name: str = None) -> Session:
    """
    Create a Snowpark session.
    
    Args:
        connection_params: Optional dict with connection parameters.
        connection_name: Optional connection name from ~/.snowflake/config.toml.
                         Falls back to SNOWFLAKE_CONNECTION_NAME env var or 'default'.
    
    Returns:
        Active Snowpark Session
    """
    if connection_params:
        session = Session.builder.configs(connection_params).create()
    else:
        try:
            session = get_active_session()
        except Exception:
            conn_name = connection_name or os.getenv('SNOWFLAKE_CONNECTION_NAME', '...')
            session = Session.builder.config('connection_name', conn_name).create()

    session.sql_simplifier_enabled = True

    session.sql(f'USE WAREHOUSE {WAREHOUSE}').collect()
    session.sql(f'USE DATABASE {SOURCE_DATABASE}').collect()
    session.sql(f'USE SCHEMA {SOURCE_SCHEMA}').collect()

    return session


if __name__ == "__main__":
    # Demo: Create session and print info
    session = create_session()
    print(f"Session created. Current database: {session.get_current_database()}")

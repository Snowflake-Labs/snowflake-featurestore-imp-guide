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

SOURCE_DATABASE = "FEATURE_STORE_DEMO"
SOURCE_SCHEMA = "CLICKSTREAM_DATA"
FS_NAME = "FEATURE_STORE"
WAREHOUSE = "FS_DEV_WH"


# ==============================================================================
# SESSION CREATION
# ==============================================================================

def create_session(connection_params: dict = None) -> Session:
    """
    Create a Snowpark session.
    
    Args:
        connection_params: Optional dict with connection parameters.
                          If None, attempts to get active session (Snowflake Notebook)
                          or reads ~/.snowflake/connections.toml [default].
    
    Returns:
        Active Snowpark Session
    """
    if connection_params:
        session = Session.builder.configs(connection_params).create()
    else:
        try:
            session = get_active_session()
        except Exception:
            session = Session.builder.config("connection_name", "default").create()
    
    # Enable SQL simplifier for cleaner generated SQL
    session.sql_simplifier_enabled = True
    
    return session


if __name__ == "__main__":
    # Demo: Create session and print info
    session = create_session()
    print(f"Session created. Current database: {session.get_current_database()}")

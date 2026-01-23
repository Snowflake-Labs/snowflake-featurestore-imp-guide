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

# Default configuration - override as needed
SOURCE_DATABASE = 'FEATURE_STORE_GUIDE'
SOURCE_SCHEMA = 'CLICKSTREAM_RAW'
FS_NAME = 'GUIDE_FEATURE_STORE'
WAREHOUSE = 'COMPUTE_WH'


# ==============================================================================
# SESSION CREATION
# ==============================================================================

def create_session(connection_params: dict = None) -> Session:
    """
    Create a Snowpark session.
    
    Args:
        connection_params: Optional dict with connection parameters.
                          If None, attempts to get active session (Snowflake Notebook)
                          or use SnowflakeLoginOptions.
    
    Returns:
        Active Snowpark Session
    """
    if connection_params:
        session = Session.builder.configs(connection_params).create()
    else:
        # Option 1: Running in Snowflake Notebook
        try:
            session = get_active_session()
        except Exception:
            # Option 2: Running locally with connection config
            from snowflake.ml.utils import connection_params as cp
            session = Session.builder.configs(cp.SnowflakeLoginOptions()).create()
    
    # Enable SQL simplifier for cleaner generated SQL
    session.sql_simplifier_enabled = True
    
    return session


if __name__ == "__main__":
    # Demo: Create session and print info
    session = create_session()
    print(f"Session created. Current database: {session.get_current_database()}")

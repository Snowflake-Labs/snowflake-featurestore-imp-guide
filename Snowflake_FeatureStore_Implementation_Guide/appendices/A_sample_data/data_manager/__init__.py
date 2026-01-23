"""
Clickstream Data Manager
========================

A unified interface for managing clickstream data.
Available as Streamlit UI, CLI tools, or Python API.

Usage:
    # Python API
    from data_manager import DataManager
    
    dm = DataManager()
    dm.connect()
    dm.run_initial_load(scale=0.01)
    
    # CLI
    streamlit run data_manager/app.py
"""

from .core import DataManager, ConnectionConfig, LoadResult

__all__ = ["DataManager", "ConnectionConfig", "LoadResult"]

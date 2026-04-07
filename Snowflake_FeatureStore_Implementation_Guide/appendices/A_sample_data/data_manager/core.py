"""
Core Data Management Operations
===============================

This module provides programmatic access to all data management operations.
Used by both the CLI tools and the Streamlit UI.

Usage:
    from core import DataManager
    
    dm = DataManager()
    dm.connect()
    
    # Initial load
    dm.run_initial_load(scale=0.01, method='simple')
    
    # Incremental generator
    dm.deploy_incremental_generator()
    dm.start_incremental_task()
    
    # Development branch
    dm.create_dev_branch('MY_DEV_DB', sample_pct=10)
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Add parent paths for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "generator"))
sys.path.insert(0, str(SCRIPT_DIR.parent / "database_subset"))
sys.path.insert(0, str(SCRIPT_DIR.parent / "public_datasets"))


@dataclass
class ConnectionConfig:
    """Snowflake connection configuration."""
    connection_name: Optional[str] = None
    account: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    warehouse: str = "FS_DEV_WH"
    role: str = "FS_ADMIN_ROLE"
    database: str = "FEATURE_STORE_DEMO"
    schema: str = "CLICKSTREAM_DATA"
    
    @classmethod
    def from_env(cls) -> "ConnectionConfig":
        """Load from environment variables."""
        return cls(
            connection_name=os.environ.get("SNOWFLAKE_CONNECTION_NAME"),
            account=os.environ.get("SNOWFLAKE_ACCOUNT"),
            user=os.environ.get("SNOWFLAKE_USER"),
            password=os.environ.get("SNOWFLAKE_PASSWORD"),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "FS_DEV_WH"),
            role=os.environ.get("SNOWFLAKE_ROLE", "FS_ADMIN_ROLE"),
            database=os.environ.get("SNOWFLAKE_DATABASE", "FEATURE_STORE_DEMO"),
            schema=os.environ.get("SNOWFLAKE_SCHEMA", "CLICKSTREAM_DATA"),
        )


@dataclass 
class LoadResult:
    """Result of a data loading operation."""
    success: bool
    message: str
    tables_created: List[str] = field(default_factory=list)
    row_counts: Dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


class DataManager:
    """Unified interface for all data management operations."""
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        self.config = config or ConnectionConfig.from_env()
        self._session = None
        
    @property
    def session(self):
        """Get or create Snowpark session."""
        if self._session is None:
            self.connect()
        return self._session
    
    def connect(self) -> bool:
        """Establish Snowflake connection."""
        try:
            from snowflake.snowpark import Session
            
            if self.config.connection_name:
                self._session = Session.builder.configs({
                    "connection_name": self.config.connection_name
                }).create()
            else:
                if not all([self.config.account, self.config.user, self.config.password]):
                    raise ValueError("Missing credentials")
                self._session = Session.builder.configs({
                    "account": self.config.account,
                    "user": self.config.user,
                    "password": self.config.password,
                    "warehouse": self.config.warehouse,
                    "role": self.config.role,
                }).create()
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to connect: {e}")
    
    def disconnect(self):
        """Close Snowflake connection."""
        if self._session:
            self._session.close()
            self._session = None
    
    # =========================================================================
    # Initial Data Load
    # =========================================================================
    
    def run_initial_load(
        self,
        scale: float = 0.01,
        method: str = "simple",
        database: Optional[str] = None,
        schema: Optional[str] = None,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31",
    ) -> LoadResult:
        """Run initial clickstream data load.
        
        Args:
            scale: Scale factor (0.01=1K users, 0.1=10K, 1.0=100K)
            method: 'simple' (in-memory) or 'bulk' (Parquet+COPY)
            database: Target database (default from config)
            schema: Target schema (default from config)
            start_date: Historical data start date
            end_date: Historical data end date
            
        Returns:
            LoadResult with status and details
        """
        from config import DataConfig, SnowflakeConfig
        from main import generate_all_data, load_to_snowflake, load_to_snowflake_bulk
        
        database = database or self.config.database
        schema = schema or self.config.schema
        
        start_time = datetime.now()
        result = LoadResult(success=False, message="")
        
        try:
            # Create data config
            data_config = DataConfig(
                scale=scale,
                start_date=datetime.strptime(start_date, "%Y-%m-%d"),
                end_date=datetime.strptime(end_date, "%Y-%m-%d"),
            )
            
            # Create Snowflake config (used for database/schema info)
            sf_config = SnowflakeConfig(
                connection_name=self.config.connection_name or "",
                account=self.config.account or "",
                user=self.config.user or "",
                password=self.config.password or "",
                warehouse=self.config.warehouse,
                database=database,
                schema=schema,
                role=self.config.role,
            )
            
            # Generate data
            data = generate_all_data(data_config, show_progress=False)
            
            # Load to Snowflake - reuse existing session to avoid re-authentication
            if method == "bulk":
                load_to_snowflake_bulk(data, sf_config, session=self._session)
            else:
                load_to_snowflake(data, sf_config, session=self._session)
            
            # Collect results
            result.success = True
            result.tables_created = list(data.keys())
            result.row_counts = {k: len(v) for k, v in data.items()}
            result.message = f"Loaded {sum(result.row_counts.values()):,} rows to {database}.{schema}"
            
        except Exception as e:
            result.success = False
            result.message = str(e)
            result.errors.append(str(e))
        
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result
    
    # =========================================================================
    # Incremental Generator
    # =========================================================================
    
    def deploy_incremental_generator(
        self,
        database: Optional[str] = None,
        data_schema: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> LoadResult:
        """Deploy the Snowflake-native incremental data generator.
        
        Creates stored procedure and task for continuous data generation.
        """
        database = database or self.config.database
        data_schema = data_schema or self.config.schema
        
        result = LoadResult(success=False, message="")
        
        try:
            # Use the actual deploy function from snowflake_native
            sys.path.insert(0, str(SCRIPT_DIR.parent / "generator" / "snowflake_native"))
            from deploy import deploy_generator
            
            # Deploy everything: config tables, stored procedure, and task
            deploy_generator(
                session=self._session,
                database=database,
                data_schema=data_schema,
                admin_schema=admin_schema,
            )
            
            result.success = True
            result.message = f"Deployed incremental generator to {database}.{admin_schema}"
            result.tables_created = [
                "GENERATION_CONFIG", "GENERATION_STATE", "GENERATION_LOG",
                "GENERATE_INCREMENTAL_BATCH (stored procedure)", 
                "INCREMENTAL_DATA_TASK (task)"
            ]
            
        except Exception as e:
            result.success = False
            result.message = str(e)
            result.errors.append(str(e))
        
        return result
    
    def get_incremental_config(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> Dict[str, Any]:
        """Get current incremental generator configuration."""
        database = database or self.config.database
        
        try:
            rows = self.session.sql(f"""
                SELECT SESSIONS_PER_BATCH, ORDERS_PER_BATCH, IS_ENABLED
                FROM {database}.{admin_schema}.GENERATION_CONFIG
                WHERE ID = 1
            """).collect()
            if rows:
                return {
                    "SESSIONS_PER_BATCH": rows[0][0],
                    "ORDERS_PER_BATCH": rows[0][1],
                    "IS_ENABLED": rows[0][2],
                }
            return {}
        except:
            return {}
    
    def update_incremental_config(
        self,
        sessions_per_batch: Optional[int] = None,
        orders_per_batch: Optional[int] = None,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> bool:
        """Update incremental generator configuration."""
        database = database or self.config.database
        
        try:
            updates = []
            if sessions_per_batch is not None:
                updates.append(f"SESSIONS_PER_BATCH = {sessions_per_batch}")
            if orders_per_batch is not None:
                updates.append(f"ORDERS_PER_BATCH = {orders_per_batch}")
            
            if updates:
                self.session.sql(f"""
                    UPDATE {database}.{admin_schema}.GENERATION_CONFIG
                    SET {', '.join(updates)}
                    WHERE ID = 1
                """).collect()
            
            return True
        except:
            return False
    
    def get_task_status(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> Dict[str, Any]:
        """Get incremental task status."""
        database = database or self.config.database
        
        try:
            self.session.sql(f"USE DATABASE {database}").collect()
            rows = self.session.sql(f"""
                SHOW TASKS LIKE 'INCREMENTAL_DATA_TASK' IN SCHEMA {admin_schema}
            """).collect()
            
            if rows:
                return {
                    "name": rows[0][1],
                    "state": rows[0][10],  # STARTED or SUSPENDED
                    "schedule": rows[0][8],
                    "warehouse": rows[0][5],
                }
            return {"state": "NOT_FOUND"}
        except:
            return {"state": "ERROR"}
    
    def start_incremental_task(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> Tuple[bool, str]:
        """Start the incremental data generation task.
        
        Returns:
            Tuple of (success, message)
        """
        database = database or self.config.database
        task_name = f"{database}.{admin_schema}.INCREMENTAL_DATA_TASK"
        
        try:
            self.session.sql(f"ALTER TASK {task_name} RESUME").collect()
            return True, f"Task {task_name} resumed successfully"
        except Exception as e:
            return False, f"Failed to resume task {task_name}: {str(e)}"
    
    def stop_incremental_task(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
    ) -> Tuple[bool, str]:
        """Stop the incremental data generation task.
        
        Returns:
            Tuple of (success, message)
        """
        database = database or self.config.database
        task_name = f"{database}.{admin_schema}.INCREMENTAL_DATA_TASK"
        
        try:
            self.session.sql(f"ALTER TASK {task_name} SUSPEND").collect()
            return True, f"Task {task_name} suspended successfully"
        except Exception as e:
            return False, f"Failed to suspend task {task_name}: {str(e)}"
    
    def get_generation_log(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
        limit: int = 20,
    ) -> pd.DataFrame:
        """Get recent generation log entries."""
        database = database or self.config.database
        
        try:
            df = self.session.sql(f"""
                SELECT BATCH_TS, SESSIONS_GENERATED, EVENTS_GENERATED, 
                       ORDERS_GENERATED, ORDER_ITEMS_GENERATED, DURATION_MS, STATUS
                FROM {database}.{admin_schema}.GENERATION_LOG
                ORDER BY BATCH_TS DESC
                LIMIT {limit}
            """).to_pandas()
            return df
        except:
            return pd.DataFrame()
    
    # =========================================================================
    # Development Branch
    # =========================================================================
    
    def create_dev_branch(
        self,
        dev_database: str,
        prod_database: Optional[str] = None,
        prod_schema: Optional[str] = None,
        sample_pct: float = 10.0,
        target_lag: str = "1 HOUR",
        warehouse: Optional[str] = None,
    ) -> LoadResult:
        """Create a development database branch with sampled data.
        
        This implements the subset creation step-by-step with error tracking.
        
        Args:
            dev_database: Name of the development database to create
            prod_database: Source production database (default: from config)
            prod_schema: Source schema (default: from config)
            sample_pct: Percentage of visitors to sample
            target_lag: Target lag for Dynamic Tables
            warehouse: Warehouse for DT refresh (default: FS_DEV_WH)
        """
        prod_database = prod_database or self.config.database
        prod_schema = prod_schema or self.config.schema
        admin_schema = "CLICKSTREAM_ADMIN"
        # Use feature store dev warehouse for DT refresh by default
        warehouse = warehouse or "FS_DEV_WH"
        
        result = LoadResult(success=False, message="")
        start_time = datetime.now()
        tables_created = []
        
        try:
            # Step 1: Create database and schemas
            self.session.sql(f"CREATE DATABASE IF NOT EXISTS {dev_database}").collect()
            self.session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.{prod_schema}").collect()
            self.session.sql(f"CREATE SCHEMA IF NOT EXISTS {dev_database}.{admin_schema}").collect()
            
            # Step 2: Create config table
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{admin_schema}.SUBSET_CONFIG (
                    config_key VARCHAR(100) PRIMARY KEY,
                    config_value VARCHAR(1000),
                    created_ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
                )
            """).collect()
            
            self.session.sql(f"""
                INSERT INTO {dev_database}.{admin_schema}.SUBSET_CONFIG (config_key, config_value)
                VALUES 
                    ('PROD_DATABASE', '{prod_database}'),
                    ('PROD_SCHEMA', '{prod_schema}'),
                    ('SAMPLE_PCT', '{sample_pct}'),
                    ('TARGET_LAG', '{target_lag}'),
                    ('WAREHOUSE', '{warehouse}')
            """).collect()
            tables_created.append("SUBSET_CONFIG")
            
            # Step 3: Create sample tables (cascading from VISITORS)
            # VISITOR_SAMPLE (root - random sample of visitors)
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{admin_schema}.VISITOR_SAMPLE AS
                SELECT VISITOR_ID 
                FROM {prod_database}.{prod_schema}.VISITORS 
                SAMPLE ({sample_pct})
            """).collect()
            tables_created.append("VISITOR_SAMPLE")
            
            # USER_SAMPLE (users linked to sampled visitors via VISITOR_ID)
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{admin_schema}.USER_SAMPLE AS
                SELECT DISTINCT u.USER_ID
                FROM {prod_database}.{prod_schema}.USERS u
                INNER JOIN {dev_database}.{admin_schema}.VISITOR_SAMPLE vs ON u.VISITOR_ID = vs.VISITOR_ID
                WHERE u.USER_ID IS NOT NULL
            """).collect()
            tables_created.append("USER_SAMPLE")
            
            # SESSION_SAMPLE (sessions for sampled visitors)
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{admin_schema}.SESSION_SAMPLE AS
                SELECT DISTINCT s.SESSION_ID
                FROM {prod_database}.{prod_schema}.SESSIONS s
                INNER JOIN {dev_database}.{admin_schema}.VISITOR_SAMPLE vs ON s.VISITOR_ID = vs.VISITOR_ID
            """).collect()
            tables_created.append("SESSION_SAMPLE")
            
            # ORDER_SAMPLE (orders for sampled users)
            self.session.sql(f"""
                CREATE OR REPLACE TABLE {dev_database}.{admin_schema}.ORDER_SAMPLE AS
                SELECT DISTINCT o.ORDER_ID
                FROM {prod_database}.{prod_schema}.ORDERS o
                INNER JOIN {dev_database}.{admin_schema}.USER_SAMPLE us ON o.USER_ID = us.USER_ID
            """).collect()
            tables_created.append("ORDER_SAMPLE")
            
            # Step 4: Create dimension tables (full copy)
            dimension_tables = ["CATEGORIES", "SUPPLIERS", "PRODUCTS", "PRODUCT_SUPPLIER", "HOUSEHOLDS"]
            for table in dimension_tables:
                try:
                    self.session.sql(f"""
                        CREATE OR REPLACE TABLE {dev_database}.{prod_schema}.{table} AS
                        SELECT * FROM {prod_database}.{prod_schema}.{table}
                    """).collect()
                    tables_created.append(table)
                except Exception as e:
                    result.errors.append(f"Dimension {table}: {str(e)[:50]}")
            
            # Step 5: Create filtered Dynamic Tables
            dt_configs = [
                ("VISITORS", "VISITOR_ID", "VISITOR_SAMPLE"),
                ("SESSIONS", "VISITOR_ID", "VISITOR_SAMPLE"),
                ("USERS", "USER_ID", "USER_SAMPLE"),
                ("ORDERS", "USER_ID", "USER_SAMPLE"),
                ("EVENTS", "SESSION_ID", "SESSION_SAMPLE"),
                ("ORDER_ITEMS", "ORDER_ID", "ORDER_SAMPLE"),
            ]
            
            for table, filter_col, sample_table in dt_configs:
                ddl = f"""CREATE OR REPLACE DYNAMIC TABLE {dev_database}.{prod_schema}.{table}
TARGET_LAG = '{target_lag}'
WAREHOUSE = {warehouse}
AS
SELECT src.*
FROM {prod_database}.{prod_schema}.{table} src
INNER JOIN {dev_database}.{admin_schema}.{sample_table} s ON src.{filter_col} = s.{filter_col}"""
                try:
                    self.session.sql(ddl).collect()
                    tables_created.append(f"DT:{table}")
                except Exception as e:
                    result.errors.append(f"DT {table}: {str(e)[:100]}")
            
            # Step 6: Create management procedure
            proc_sql = f"""
                CREATE OR REPLACE PROCEDURE {dev_database}.{admin_schema}.SP_MANAGE_ALL_DTS(ACTION VARCHAR)
                RETURNS VARCHAR
                LANGUAGE SQL
                AS
                BEGIN
                    IF (ACTION = 'SUSPEND') THEN
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.VISITORS SUSPEND;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.SESSIONS SUSPEND;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.USERS SUSPEND;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.ORDERS SUSPEND;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.EVENTS SUSPEND;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.ORDER_ITEMS SUSPEND;
                        RETURN 'All Dynamic Tables suspended';
                    ELSEIF (ACTION = 'RESUME') THEN
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.VISITORS RESUME;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.SESSIONS RESUME;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.USERS RESUME;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.ORDERS RESUME;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.EVENTS RESUME;
                        ALTER DYNAMIC TABLE {dev_database}.{prod_schema}.ORDER_ITEMS RESUME;
                        RETURN 'All Dynamic Tables resumed';
                    ELSE
                        RETURN 'Invalid action. Use SUSPEND or RESUME.';
                    END IF;
                END;
            """
            try:
                self.session.sql(proc_sql).collect()
                tables_created.append("SP_MANAGE_ALL_DTS")
            except Exception as e:
                result.errors.append(f"Procedure: {str(e)[:50]}")
            
            # Determine success
            dt_count = len([t for t in tables_created if t.startswith("DT:")])
            if dt_count == 6:
                result.success = True
                result.message = f"Created {dev_database} with {sample_pct}% sample ({dt_count} Dynamic Tables)"
            elif dt_count > 0:
                result.success = True
                result.message = f"Partially created {dev_database} ({dt_count}/6 Dynamic Tables). Check errors."
            else:
                result.success = False
                result.message = f"Failed to create Dynamic Tables. Errors: {'; '.join(result.errors[:3])}"
            
            result.tables_created = tables_created
            
        except Exception as e:
            result.success = False
            result.message = f"Failed: {str(e)}"
            result.errors.append(str(e))
        
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result
    
    def get_dev_branch_status(self, dev_database: str) -> Dict[str, Any]:
        """Get status of a development branch."""
        try:
            self.session.sql(f"USE DATABASE {dev_database}").collect()
            
            # Get config
            config = {}
            try:
                rows = self.session.sql(f"""
                    SELECT CONFIG_KEY, CONFIG_VALUE 
                    FROM _SUBSET_ADMIN.SUBSET_CONFIG
                """).collect()
                config = {row[0]: row[1] for row in rows}
            except:
                pass
            
            # Get sample counts
            samples = {}
            for table in ["USER_SAMPLE", "VISITOR_SAMPLE", "SESSION_SAMPLE", "ORDER_SAMPLE"]:
                try:
                    count = self.session.sql(f"""
                        SELECT COUNT(*) FROM _SUBSET_ADMIN.{table}
                    """).collect()[0][0]
                    samples[table] = count
                except:
                    pass
            
            # Get Dynamic Tables
            dts = []
            try:
                rows = self.session.sql("""
                    SHOW DYNAMIC TABLES IN SCHEMA CLICKSTREAM_DATA
                """).collect()
                for row in rows:
                    dts.append({
                        "name": row[1],
                        "rows": row[5] if row[5] else 0,
                        "refresh_mode": row[9],
                        "state": row[15],
                    })
            except:
                pass
            
            return {
                "exists": True,
                "config": config,
                "samples": samples,
                "dynamic_tables": dts,
            }
        except:
            return {"exists": False}
    
    def suspend_dev_branch(self, dev_database: str) -> bool:
        """Suspend all Dynamic Tables in a dev branch."""
        try:
            self.session.sql(f"""
                CALL {dev_database}._SUBSET_ADMIN.SP_MANAGE_ALL_DTS('SUSPEND')
            """).collect()
            return True
        except:
            return False
    
    def resume_dev_branch(self, dev_database: str) -> bool:
        """Resume all Dynamic Tables in a dev branch."""
        try:
            self.session.sql(f"""
                CALL {dev_database}._SUBSET_ADMIN.SP_MANAGE_ALL_DTS('RESUME')
            """).collect()
            return True
        except:
            return False
    
    def drop_dev_branch(self, dev_database: str) -> bool:
        """Drop a development database branch."""
        try:
            self.session.sql(f"DROP DATABASE IF EXISTS {dev_database}").collect()
            return True
        except:
            return False
    
    def update_dev_branch_target_lag(
        self, 
        dev_database: str, 
        schema: str,
        new_target_lag: str
    ) -> Tuple[bool, str]:
        """Update the target lag for all Dynamic Tables in a dev branch.
        
        Args:
            dev_database: The development database name
            schema: The schema containing Dynamic Tables
            new_target_lag: New target lag (e.g., '1 MINUTE', '15 MINUTES', '1 HOUR')
            
        Returns:
            Tuple of (success, message)
        """
        # List of Dynamic Tables in a typical dev branch
        dt_tables = ["VISITORS", "SESSIONS", "USERS", "ORDERS", "EVENTS", "ORDER_ITEMS"]
        
        updated = []
        errors = []
        
        for table in dt_tables:
            try:
                self.session.sql(f"""
                    ALTER DYNAMIC TABLE {dev_database}.{schema}.{table}
                    SET TARGET_LAG = '{new_target_lag}'
                """).collect()
                updated.append(table)
            except Exception as e:
                error_msg = str(e)
                # Skip if table doesn't exist (not all branches have all tables)
                if "does not exist" in error_msg.lower():
                    continue
                errors.append(f"{table}: {error_msg[:50]}")
        
        # Also update the config table if it exists (try both old and new schema names)
        for admin_schema in ['CLICKSTREAM_ADMIN', '_SUBSET_ADMIN']:
            try:
                self.session.sql(f"""
                    UPDATE {dev_database}.{admin_schema}.SUBSET_CONFIG
                    SET CONFIG_VALUE = '{new_target_lag}'
                    WHERE CONFIG_KEY = 'TARGET_LAG'
                """).collect()
                break  # Success, stop trying
            except:
                continue  # Try next schema name
        
        if updated:
            if errors:
                return True, f"Updated {len(updated)} DTs to {new_target_lag}. Errors: {len(errors)}"
            else:
                return True, f"Updated {len(updated)} Dynamic Tables to {new_target_lag}"
        else:
            if errors:
                return False, f"Failed to update: {'; '.join(errors[:3])}"
            else:
                return False, "No Dynamic Tables found to update"
    
    # =========================================================================
    # Public Datasets
    # =========================================================================
    
    def list_public_datasets(self) -> List[Dict[str, Any]]:
        """List available public ML datasets."""
        from load_datasets import DATASETS
        return [
            {
                "key": k,
                "name": v["name"],
                "rows": v["rows"],
                "description": v["description"],
                "sample": v.get("sample"),
            }
            for k, v in DATASETS.items()
        ]
    
    def load_public_dataset(
        self,
        dataset_key: str,
        database: Optional[str] = None,
        schema: str = "PUBLIC_DATASETS",
        full: bool = False,
    ) -> LoadResult:
        """Load a public ML dataset."""
        from load_datasets import DATASETS, download_dataset, load_to_snowflake
        
        database = database or self.config.database
        result = LoadResult(success=False, message="")
        
        try:
            if dataset_key not in DATASETS:
                raise ValueError(f"Unknown dataset: {dataset_key}")
            
            info = DATASETS[dataset_key]
            df = download_dataset(dataset_key, full=full)
            load_to_snowflake(df, info["table_name"], self.session, database, schema)
            
            result.success = True
            result.message = f"Loaded {len(df):,} rows to {database}.{schema}.{info['table_name']}"
            result.tables_created = [info["table_name"]]
            result.row_counts = {info["table_name"]: len(df)}
            
        except Exception as e:
            result.success = False
            result.message = str(e)
            result.errors.append(str(e))
        
        return result
    
    # =========================================================================
    # Monitoring
    # =========================================================================
    
    def get_dynamic_table_refresh_history(
        self,
        database: Optional[str] = None,
        schema: Optional[str] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Get Dynamic Table refresh history.
        
        Uses INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY() table function
        which provides real-time data (no latency).
        
        See: https://docs.snowflake.com/en/sql-reference/functions/dynamic_table_refresh_history
        
        Args:
            database: Database name
            schema: Schema name  
            limit: Maximum number of rows to return (applied after sorting)
        """
        database = database or self.config.database
        schema = schema or self.config.schema
        
        try:
            # Use INFORMATION_SCHEMA table function - real-time, no latency
            # NAME_PREFIX filters to a specific database.schema
            # Fetch more rows than needed, then sort and limit externally
            df = self.session.sql(f"""
                SELECT 
                    NAME,
                    SCHEMA_NAME,
                    STATE,
                    STATE_MESSAGE,
                    REFRESH_START_TIME,
                    REFRESH_END_TIME,
                    REFRESH_ACTION,
                    REFRESH_TRIGGER,
                    DATEDIFF('second', REFRESH_START_TIME, REFRESH_END_TIME) as DURATION_SEC
                FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
                    NAME_PREFIX => '{database}.{schema}.',
                    RESULT_LIMIT => 1000
                ))
                ORDER BY REFRESH_START_TIME DESC
                LIMIT {limit}
            """).to_pandas()
            return df
        except Exception as e:
            # Fallback to ACCOUNT_USAGE if INFORMATION_SCHEMA fails
            # (e.g., missing MONITOR privilege on DTs)
            try:
                df = self.session.sql(f"""
                    SELECT 
                        NAME,
                        SCHEMA_NAME,
                        STATE,
                        '' as STATE_MESSAGE,
                        REFRESH_START_TIME,
                        REFRESH_END_TIME,
                        REFRESH_ACTION,
                        REFRESH_TRIGGER,
                        DATEDIFF('second', REFRESH_START_TIME, REFRESH_END_TIME) as DURATION_SEC
                    FROM SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY
                    WHERE DATABASE_NAME = '{database}'
                      AND SCHEMA_NAME = '{schema}'
                      AND REFRESH_START_TIME > DATEADD('day', -7, CURRENT_TIMESTAMP())
                    ORDER BY REFRESH_START_TIME DESC
                    LIMIT {limit}
                """).to_pandas()
                return df
            except Exception as e2:
                print(f"DT History Error: INFORMATION_SCHEMA: {e}, ACCOUNT_USAGE: {e2}")
                return pd.DataFrame()
    
    def get_task_history(
        self,
        database: Optional[str] = None,
        admin_schema: str = "CLICKSTREAM_ADMIN",
        limit: int = 50,
    ) -> pd.DataFrame:
        """Get task execution history.
        
        Uses SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY view which requires 
        access to the SNOWFLAKE database.
        """
        database = database or self.config.database
        task_name = f"{database}.{admin_schema}.INCREMENTAL_DATA_TASK"
        
        try:
            # Use ACCOUNT_USAGE view which has better historical data
            # Note: ACCOUNT_USAGE has up to 45 minute latency
            df = self.session.sql(f"""
                SELECT 
                    NAME,
                    STATE,
                    SCHEDULED_TIME,
                    COMPLETED_TIME,
                    DATEDIFF('second', SCHEDULED_TIME, COMPLETED_TIME) as DURATION_SEC,
                    ERROR_CODE,
                    ERROR_MESSAGE
                FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
                WHERE DATABASE_NAME = '{database}'
                  AND SCHEMA_NAME = '{admin_schema}'
                  AND NAME = 'INCREMENTAL_DATA_TASK'
                  AND SCHEDULED_TIME > DATEADD('day', -7, CURRENT_TIMESTAMP())
                ORDER BY SCHEDULED_TIME DESC
                LIMIT {limit}
            """).to_pandas()
            return df
        except Exception as e1:
            # Fallback to INFORMATION_SCHEMA (real-time but requires specific context)
            try:
                self.session.sql(f"USE DATABASE {database}").collect()
                df = self.session.sql(f"""
                    SELECT 
                        NAME,
                        STATE,
                        SCHEDULED_TIME,
                        COMPLETED_TIME,
                        DATEDIFF('second', SCHEDULED_TIME, COMPLETED_TIME) as DURATION_SEC,
                        ERROR_CODE,
                        ERROR_MESSAGE
                    FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
                        TASK_NAME => '{task_name}',
                        RESULT_LIMIT => {limit}
                    ))
                    ORDER BY SCHEDULED_TIME DESC
                """).to_pandas()
                return df
            except Exception as e2:
                # Return empty with error info for debugging
                print(f"Task History Error: ACCOUNT_USAGE: {e1}, INFORMATION_SCHEMA: {e2}")
                return pd.DataFrame()
    
    def get_table_row_counts(
        self,
        database: Optional[str] = None,
        schema: Optional[str] = None,
    ) -> Dict[str, int]:
        """Get row counts for all tables in a schema."""
        database = database or self.config.database
        schema = schema or self.config.schema
        
        try:
            rows = self.session.sql(f"""
                SELECT TABLE_NAME, ROW_COUNT
                FROM {database}.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = '{schema}'
                ORDER BY TABLE_NAME
            """).collect()
            return {row[0]: row[1] or 0 for row in rows}
        except:
            return {}

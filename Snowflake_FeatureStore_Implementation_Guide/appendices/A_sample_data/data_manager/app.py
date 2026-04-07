"""
Clickstream Data Manager - Streamlit UI
=======================================

A unified interface for managing clickstream data for the Feature Store Guide.

Run with:
    streamlit run app.py
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
import pandas as pd

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core import DataManager, ConnectionConfig, LoadResult


# =============================================================================
# Connection Discovery
# =============================================================================

def get_available_connections() -> List[Dict[str, Any]]:
    """Read available named connections from ~/.snowflake/connections.toml."""
    connections = []
    toml_path = Path.home() / ".snowflake" / "connections.toml"
    
    if not toml_path.exists():
        return connections
    
    try:
        # Try to use tomllib (Python 3.11+) or tomli
        try:
            import tomllib
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
        except ImportError:
            try:
                import tomli
                with open(toml_path, "rb") as f:
                    config = tomli.load(f)
            except ImportError:
                # Fallback: simple TOML parsing for connection names
                with open(toml_path, "r") as f:
                    content = f.read()
                # Extract section names [name]
                import re
                sections = re.findall(r'^\[([^\]]+)\]', content, re.MULTILINE)
                for section in sections:
                    if not section.startswith("default"):
                        connections.append({
                            "name": section,
                            "account": "",
                            "user": "",
                        })
                return connections
        
        # Parse the TOML config
        for name, values in config.items():
            if isinstance(values, dict):
                connections.append({
                    "name": name,
                    "account": values.get("account", values.get("accountname", "")),
                    "user": values.get("user", values.get("username", "")),
                    "warehouse": values.get("warehouse", ""),
                    "database": values.get("database", ""),
                })
    except Exception as e:
        st.sidebar.warning(f"Could not read connections.toml: {str(e)[:30]}")
    
    return connections


def get_connection_display_name(conn: Dict[str, Any]) -> str:
    """Format connection for display in dropdown."""
    name = conn["name"]
    account = conn.get("account", "")
    if account:
        # Extract just the account identifier (before any dots)
        account_short = account.split(".")[0] if "." in account else account
        return f"{name} ({account_short})"
    return name

# =============================================================================
# Page Configuration
# =============================================================================

st.set_page_config(
    page_title="Clickstream Data Manager",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .info-box {
        background-color: #cce5ff;
        border: 1px solid #b8daff;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Session State Initialization
# =============================================================================

def init_session_state():
    """Initialize session state variables."""
    if "dm" not in st.session_state:
        st.session_state.dm = None
    if "connected" not in st.session_state:
        st.session_state.connected = False
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = None


init_session_state()


# =============================================================================
# Sidebar - Connection & Navigation
# =============================================================================

def render_sidebar():
    """Render sidebar with connection and navigation."""
    st.sidebar.title("🔄 Data Manager")
    st.sidebar.markdown("---")
    
    # Connection section
    st.sidebar.subheader("Connection")
    
    # Get available connections
    available_connections = get_available_connections()
    
    connection_method = st.sidebar.radio(
        "Connection Method",
        ["Named Connection", "Manual Credentials"],
        help="Use named connection from ~/.snowflake/connections.toml or enter credentials manually"
    )
    
    if connection_method == "Named Connection":
        if available_connections:
            # Create dropdown options
            connection_options = [""] + [conn["name"] for conn in available_connections]
            display_options = ["-- Select Connection --"] + [
                get_connection_display_name(conn) for conn in available_connections
            ]
            
            # Get default selection from environment
            default_conn = os.environ.get("SNOWFLAKE_CONNECTION_NAME", "")
            default_index = 0
            if default_conn in connection_options:
                default_index = connection_options.index(default_conn)
            
            selected_display = st.sidebar.selectbox(
                "Connection",
                options=display_options,
                index=default_index,
                help="Select from available connections in ~/.snowflake/connections.toml"
            )
            
            # Map display back to connection name
            if selected_display == "-- Select Connection --":
                connection_name = ""
            else:
                selected_index = display_options.index(selected_display)
                connection_name = connection_options[selected_index]
            
            # Show connection details
            if connection_name:
                conn_info = next((c for c in available_connections if c["name"] == connection_name), None)
                if conn_info:
                    with st.sidebar.expander("Connection Details", expanded=False):
                        st.text(f"Account: {conn_info.get('account', 'N/A')}")
                        st.text(f"User: {conn_info.get('user', 'N/A')}")
                        if conn_info.get('warehouse'):
                            st.text(f"Warehouse: {conn_info.get('warehouse')}")
                        if conn_info.get('database'):
                            st.text(f"Database: {conn_info.get('database')}")
        else:
            st.sidebar.warning("No connections found in ~/.snowflake/connections.toml")
            connection_name = st.sidebar.text_input(
                "Connection Name",
                value=os.environ.get("SNOWFLAKE_CONNECTION_NAME", ""),
                help="Enter connection name manually"
            )
        
        config = ConnectionConfig(connection_name=connection_name)
    else:
        account = st.sidebar.text_input("Account", value=os.environ.get("SNOWFLAKE_ACCOUNT", ""))
        user = st.sidebar.text_input("User", value=os.environ.get("SNOWFLAKE_USER", ""))
        password = st.sidebar.text_input("Password", type="password")
        config = ConnectionConfig(account=account, user=user, password=password)
    
    # Common config
    warehouse = st.sidebar.text_input(
        "Warehouse",
        value=os.environ.get("SNOWFLAKE_WAREHOUSE", "FS_DEV_WH")
    )
    database = st.sidebar.text_input(
        "Database",
        value=os.environ.get("SNOWFLAKE_DATABASE", "FEATURE_STORE_DEMO")
    )
    schema = st.sidebar.text_input(
        "Schema",
        value="CLICKSTREAM_DATA"
    )
    
    config.warehouse = warehouse
    config.database = database
    config.schema = schema
    
    # Connect button
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("Connect", type="primary", use_container_width=True):
            try:
                dm = DataManager(config)
                dm.connect()
                st.session_state.dm = dm
                st.session_state.connected = True
                st.sidebar.success("✅ Connected!")
            except Exception as e:
                st.sidebar.error(f"❌ {str(e)[:50]}")
    
    with col2:
        if st.button("Disconnect", use_container_width=True):
            if st.session_state.dm:
                st.session_state.dm.disconnect()
            st.session_state.dm = None
            st.session_state.connected = False
            st.rerun()
    
    # Connection status
    if st.session_state.connected:
        st.sidebar.markdown("🟢 **Connected**")
    else:
        st.sidebar.markdown("🔴 **Disconnected**")
    
    st.sidebar.markdown("---")
    
    # Navigation
    st.sidebar.subheader("Navigation")
    page = st.sidebar.radio(
        "Go to",
        [
            "📊 Overview",
            "📥 Initial Load",
            "🔄 Incremental Generator",
            "🌿 Development Branch",
            "📚 Public Datasets",
            "📈 Monitoring",
        ]
    )
    
    return page, config


# =============================================================================
# Overview Page
# =============================================================================

def render_overview():
    """Render overview dashboard."""
    st.title("📊 Data Overview")
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first (see sidebar)")
        return
    
    dm = st.session_state.dm
    
    # Get table counts
    with st.spinner("Loading data..."):
        row_counts = dm.get_table_row_counts()
    
    if not row_counts:
        st.info("No tables found in the current schema. Use 'Initial Load' to create data.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tables", len(row_counts))
    with col2:
        st.metric("Total Rows", f"{sum(row_counts.values()):,}")
    with col3:
        st.metric("Visitors", f"{row_counts.get('VISITORS', 0):,}")
    with col4:
        st.metric("Events", f"{row_counts.get('EVENTS', 0):,}")
    
    # Table breakdown
    st.subheader("Table Row Counts")
    
    df = pd.DataFrame([
        {"Table": k, "Rows": v}
        for k, v in sorted(row_counts.items())
    ])
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.bar_chart(df.set_index("Table"))
    with col2:
        st.dataframe(df, use_container_width=True, hide_index=True)


# =============================================================================
# Initial Load Page
# =============================================================================

def render_initial_load():
    """Render initial data load page."""
    st.title("📥 Initial Data Load")
    
    st.markdown("""
    Generate and load synthetic clickstream data into Snowflake.
    
    **Scale Guide:**
    - `0.01` = ~1K users, ~50K events (development)
    - `0.1` = ~10K users, ~500K events (testing)
    - `1.0` = ~100K users, ~5M events (full scale)
    """)
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first")
        return
    
    dm = st.session_state.dm
    
    # Configuration
    st.subheader("Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        scale = st.slider(
            "Scale Factor",
            min_value=0.01,
            max_value=1.0,
            value=0.01,
            step=0.01,
            help="0.01 = 1K users, 1.0 = 100K users"
        )
        
        method = st.selectbox(
            "Loading Method",
            ["simple", "bulk"],
            help="'simple' loads in-memory, 'bulk' uses Parquet files"
        )
    
    with col2:
        database = st.text_input(
            "Target Database",
            value=dm.config.database
        )
        
        schema = st.text_input(
            "Target Schema",
            value=dm.config.schema
        )
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Historical Start Date",
            value=datetime(2022, 1, 1)
        )
    with col2:
        end_date = st.date_input(
            "Historical End Date",
            value=datetime.now() - timedelta(days=1)  # Yesterday
        )
    
    # Estimated data size
    estimated_users = int(100000 * scale)
    estimated_events = int(5000000 * scale)
    
    st.info(f"""
    **Estimated Data:**
    - Users: ~{estimated_users:,}
    - Events: ~{estimated_events:,}
    - Method: {method} ({"Parquet + COPY INTO" if method == "bulk" else "In-memory"})
    """)
    
    # Run button
    if st.button("🚀 Generate & Load Data", type="primary"):
        with st.spinner(f"Generating and loading data (scale={scale})..."):
            progress = st.progress(0)
            status = st.empty()
            
            status.text("Generating data...")
            progress.progress(25)
            
            result = dm.run_initial_load(
                scale=scale,
                method=method,
                database=database,
                schema=schema,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            
            progress.progress(100)
            
            if result.success:
                st.success(f"✅ {result.message}")
                st.markdown(f"**Duration:** {result.duration_seconds:.1f}s")
                
                # Show row counts
                if result.row_counts:
                    st.subheader("Loaded Tables")
                    df = pd.DataFrame([
                        {"Table": k, "Rows": v}
                        for k, v in result.row_counts.items()
                    ])
                    st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.error(f"❌ {result.message}")
    
    # CLI equivalent
    with st.expander("💻 CLI Equivalent"):
        st.code(f"""
# Navigate to generator directory
cd generator/

# Run initial load
python main.py \\
    --scale {scale} \\
    --output snowflake \\
    --method {method} \\
    --database {database} \\
    --schema {schema} \\
    --start-date {start_date.strftime("%Y-%m-%d")} \\
    --end-date {end_date.strftime("%Y-%m-%d")}
        """, language="bash")


# =============================================================================
# Incremental Generator Page
# =============================================================================

def render_incremental_generator():
    """Render incremental generator management page."""
    st.title("🔄 Incremental Data Generator")
    
    st.markdown("""
    Manage the Snowflake-native incremental data generator that continuously 
    adds new sessions, events, and orders to simulate live traffic.
    """)
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first")
        return
    
    dm = st.session_state.dm
    
    # Configuration
    st.subheader("Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        database = st.text_input("Database", value=dm.config.database, key="inc_db")
        data_schema = st.text_input("Data Schema", value=dm.config.schema, key="inc_data_schema")
    with col2:
        admin_schema = st.text_input("Admin Schema", value="CLICKSTREAM_ADMIN", key="inc_admin_schema")
    
    # Current status
    st.subheader("Status")
    
    if st.button("🔄 Refresh Status"):
        st.session_state.last_refresh = datetime.now()
    
    task_status = dm.get_task_status(database, admin_schema)
    config = dm.get_incremental_config(database, admin_schema)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        state = task_status.get("state", "UNKNOWN")
        if state == "started":
            st.success("🟢 Task: RUNNING")
        elif state == "suspended":
            st.warning("🟡 Task: SUSPENDED")
        else:
            st.info(f"⚪ Task: {state}")
    
    with col2:
        st.metric("Sessions/Batch", config.get("SESSIONS_PER_BATCH", "N/A"))
    
    with col3:
        st.metric("Orders/Batch", config.get("ORDERS_PER_BATCH", "N/A"))
    
    # Control buttons
    st.subheader("Controls")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("▶️ Start Task", type="primary"):
            success, message = dm.start_incremental_task(database, admin_schema)
            if success:
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    
    with col2:
        if st.button("⏹️ Stop Task"):
            success, message = dm.stop_incremental_task(database, admin_schema)
            if success:
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")
    
    with col3:
        if st.button("🚀 Deploy Generator"):
            result = dm.deploy_incremental_generator(database, data_schema, admin_schema)
            if result.success:
                st.success(result.message)
            else:
                st.error(result.message)
    
    # Update configuration
    st.subheader("Update Configuration")
    
    col1, col2 = st.columns(2)
    with col1:
        new_sessions = st.number_input(
            "Sessions per Batch",
            min_value=1,
            max_value=1000,
            value=int(config.get("SESSIONS_PER_BATCH", 50))
        )
    with col2:
        new_orders = st.number_input(
            "Orders per Batch",
            min_value=0,
            max_value=100,
            value=int(config.get("ORDERS_PER_BATCH", 5))
        )
    
    if st.button("💾 Update Config"):
        if dm.update_incremental_config(new_sessions, new_orders, database, admin_schema):
            st.success("Configuration updated!")
        else:
            st.error("Failed to update configuration")
    
    # Recent executions
    st.subheader("Recent Executions")
    
    log_df = dm.get_generation_log(database, admin_schema, limit=10)
    if not log_df.empty:
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("No execution logs found")
    
    # CLI equivalent
    with st.expander("💻 CLI Equivalent"):
        st.code(f"""
# Navigate to snowflake_native directory
cd generator/snowflake_native/

# Deploy generator
python deploy.py --database {database}

# Start task
python deploy.py --start

# Stop task
python deploy.py --stop

# Check status
python deploy.py --status
        """, language="bash")


# =============================================================================
# Development Branch Page
# =============================================================================

def render_dev_branch():
    """Render development branch management page."""
    st.title("🌿 Development Branch")
    
    st.markdown("""
    Create development database "branches" with sampled subsets of production data.
    Uses Dynamic Tables for real-time sync with configurable sample size.
    """)
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first")
        return
    
    dm = st.session_state.dm
    
    # Create new branch
    st.subheader("Create New Branch")
    
    col1, col2 = st.columns(2)
    with col1:
        prod_database = st.text_input(
            "Production Database",
            value=dm.config.database,
            key="prod_db"
        )
        dev_database = st.text_input(
            "Development Database Name",
            value=f"{dm.config.database}_DEV",
            key="dev_db"
        )
    
    with col2:
        sample_pct = st.slider(
            "Sample Percentage",
            min_value=1,
            max_value=100,
            value=10,
            help="Percentage of visitors to include"
        )
        target_lag = st.selectbox(
            "Dynamic Table Refresh Lag",
            ["1 MINUTE", "10 MINUTES", "15 MINUTES", "30 MINUTES", "1 HOUR", "2 HOURS", "6 HOURS"],
            index=4,  # Default to 1 HOUR
            help="How frequently Dynamic Tables refresh from production"
        )
        dt_warehouse = st.text_input(
            "DT Refresh Warehouse",
            value="FS_DEV_WH",
            help="Warehouse used for Dynamic Table refresh operations"
        )
    
    # Estimated size
    st.info(f"""
    **Estimated Development Data:**
    - ~{sample_pct}% of production visitors
    - Dynamic Tables with {target_lag} refresh lag
    - DT refresh using warehouse: {dt_warehouse}
    - Includes anonymous sessions and events
    """)
    
    if st.button("🌿 Create Development Branch", type="primary"):
        with st.spinner("Creating development branch..."):
            result = dm.create_dev_branch(
                dev_database,
                prod_database,
                dm.config.schema,
                sample_pct,
                target_lag.replace(" ", " "),
                warehouse=dt_warehouse,
            )
            
            if result.success:
                st.success(f"✅ {result.message}")
                st.markdown(f"**Duration:** {result.duration_seconds:.1f}s")
                
                # Show what was created
                if result.tables_created:
                    with st.expander("📋 Objects Created", expanded=True):
                        sample_tables = [t for t in result.tables_created if "SAMPLE" in t or "CONFIG" in t]
                        dim_tables = [t for t in result.tables_created if not t.startswith("DT:") and "SAMPLE" not in t and "CONFIG" not in t and "SP_" not in t]
                        dt_tables = [t.replace("DT:", "") for t in result.tables_created if t.startswith("DT:")]
                        procs = [t for t in result.tables_created if t.startswith("SP_")]
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Sample Tables:**")
                            for t in sample_tables:
                                st.text(f"  ✓ {t}")
                            st.markdown("**Dimension Tables:**")
                            for t in dim_tables:
                                st.text(f"  ✓ {t}")
                        with col2:
                            st.markdown("**Dynamic Tables:**")
                            for t in dt_tables:
                                st.text(f"  ✓ {t}")
                            if procs:
                                st.markdown("**Procedures:**")
                                for t in procs:
                                    st.text(f"  ✓ {t}")
            else:
                st.error(f"❌ {result.message}")
            
            # Show any errors
            if result.errors:
                with st.expander("⚠️ Errors/Warnings", expanded=True):
                    for err in result.errors:
                        st.warning(err)
    
    st.markdown("---")
    
    # Manage existing branch
    st.subheader("Manage Existing Branch")
    
    manage_db = st.text_input(
        "Branch Database Name",
        value=f"{dm.config.database}_DEV",
        key="manage_dev_db"
    )
    
    if st.button("🔍 Load Branch Status"):
        status = dm.get_dev_branch_status(manage_db)
        
        if status.get("exists"):
            st.success(f"Branch '{manage_db}' exists")
            
            # Config
            if status.get("config"):
                st.markdown("**Configuration:**")
                for k, v in status["config"].items():
                    st.text(f"  {k}: {v}")
            
            # Sample counts
            if status.get("samples"):
                st.markdown("**Sample Tables:**")
                cols = st.columns(4)
                for i, (k, v) in enumerate(status["samples"].items()):
                    with cols[i % 4]:
                        st.metric(k.replace("_SAMPLE", ""), f"{v:,}")
            
            # Dynamic Tables
            if status.get("dynamic_tables"):
                st.markdown("**Dynamic Tables:**")
                df = pd.DataFrame(status["dynamic_tables"])
                st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning(f"Branch '{manage_db}' not found")
    
    # Control buttons - Row 1: Suspend/Resume
    st.markdown("**Control Dynamic Tables:**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("⏸️ Suspend DTs"):
            if dm.suspend_dev_branch(manage_db):
                st.success("Dynamic Tables suspended")
            else:
                st.error("Failed to suspend")
    
    with col2:
        if st.button("▶️ Resume DTs"):
            if dm.resume_dev_branch(manage_db):
                st.success("Dynamic Tables resumed")
            else:
                st.error("Failed to resume")
    
    with col3:
        if st.button("🗑️ Drop Branch", type="secondary"):
            st.warning(f"This will DROP DATABASE {manage_db}")
            if st.button("⚠️ Confirm Drop", key="confirm_drop"):
                if dm.drop_dev_branch(manage_db):
                    st.success("Branch dropped")
                else:
                    st.error("Failed to drop branch")
    
    # Adjust refresh frequency
    st.markdown("**Adjust Refresh Frequency:**")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        new_target_lag = st.selectbox(
            "New Target Lag",
            ["1 MINUTE", "10 MINUTES", "15 MINUTES", "30 MINUTES", "1 HOUR", "2 HOURS", "6 HOURS"],
            index=4,  # Default to 1 HOUR
            key="manage_target_lag",
            help="Change how frequently Dynamic Tables refresh from production"
        )
    
    with col2:
        st.markdown("")  # Spacing
        st.markdown("")  # Spacing
        if st.button("⚡ Update Refresh Rate"):
            with st.spinner(f"Updating Dynamic Tables to {new_target_lag}..."):
                success, message = dm.update_dev_branch_target_lag(
                    manage_db, 
                    dm.config.schema, 
                    new_target_lag
                )
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    # CLI equivalent
    with st.expander("💻 CLI Equivalent"):
        st.code(f"""
# Navigate to database_subset directory
cd database_subset/

# Create branch
python deploy.py create \\
    --prod-db {prod_database} \\
    --dev-db {dev_database} \\
    --sample-pct {sample_pct} \\
    --warehouse {dm.config.warehouse} \\
    --target-lag "{target_lag}"

# Check status
python deploy.py status --dev-db {manage_db}

# Suspend/Resume
python deploy.py suspend --dev-db {manage_db}
python deploy.py resume --dev-db {manage_db}

# Drop
python deploy.py drop --dev-db {manage_db} --confirm
        """, language="bash")


# =============================================================================
# Public Datasets Page
# =============================================================================

def render_public_datasets():
    """Render public datasets page."""
    st.title("📚 Public ML Datasets")
    
    st.markdown("""
    Load standard ML datasets for testing and examples.
    These are commonly used datasets like Iris, Titanic, NYC Taxi, etc.
    """)
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first")
        return
    
    dm = st.session_state.dm
    
    # List datasets
    datasets = dm.list_public_datasets()
    
    st.subheader("Available Datasets")
    
    df = pd.DataFrame(datasets)
    df["Sample"] = df["sample"].apply(lambda x: f"{x:,}" if x else "All")
    df = df[["key", "name", "rows", "Sample", "description"]]
    df.columns = ["Key", "Name", "Total Rows", "Default Sample", "Description"]
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Load dataset
    st.subheader("Load Dataset")
    
    col1, col2 = st.columns(2)
    with col1:
        selected = st.selectbox(
            "Select Dataset",
            [d["key"] for d in datasets],
            format_func=lambda x: next(d["name"] for d in datasets if d["key"] == x)
        )
        
        full_load = st.checkbox(
            "Load Full Dataset (no sampling)",
            help="For large datasets, default is sampled to 50K rows"
        )
    
    with col2:
        database = st.text_input(
            "Target Database",
            value=dm.config.database,
            key="pub_db"
        )
        schema = st.text_input(
            "Target Schema",
            value="PUBLIC_DATASETS",
            key="pub_schema"
        )
    
    if st.button("📥 Load Dataset", type="primary"):
        with st.spinner(f"Loading {selected}..."):
            result = dm.load_public_dataset(
                selected,
                database,
                schema,
                full=full_load
            )
            
            if result.success:
                st.success(f"✅ {result.message}")
            else:
                st.error(f"❌ {result.message}")
    
    # Load all button
    if st.button("📥 Load All Datasets"):
        progress = st.progress(0)
        for i, dataset in enumerate(datasets):
            with st.spinner(f"Loading {dataset['name']}..."):
                result = dm.load_public_dataset(
                    dataset["key"],
                    database,
                    schema,
                    full=full_load
                )
                if result.success:
                    st.success(f"✅ {dataset['name']}: {result.message}")
                else:
                    st.error(f"❌ {dataset['name']}: {result.message}")
            progress.progress((i + 1) / len(datasets))
    
    # CLI equivalent
    with st.expander("💻 CLI Equivalent"):
        st.code(f"""
# Navigate to public_datasets directory
cd public_datasets/

# List available datasets
python load_datasets.py --list

# Load specific dataset
python load_datasets.py {selected} --database {database} --schema {schema}

# Load all datasets
python load_datasets.py all --database {database} --schema {schema}

# Load full dataset (no sampling)
python load_datasets.py {selected} --full
        """, language="bash")


# =============================================================================
# Monitoring Page
# =============================================================================

def render_monitoring():
    """Render monitoring dashboard."""
    st.title("📈 Monitoring Dashboard")
    
    if not st.session_state.connected:
        st.warning("Please connect to Snowflake first")
        return
    
    dm = st.session_state.dm
    
    # Auto-refresh at top
    col1, col2 = st.columns([3, 1])
    with col1:
        auto_refresh = st.checkbox("Auto-refresh (every 60s)")
        if auto_refresh:
            st.caption("🔄 Auto-refreshing...")
    with col2:
        if st.button("🔄 Refresh Now"):
            st.session_state.last_refresh = datetime.now()
            st.rerun()
    
    if st.session_state.last_refresh:
        st.caption(f"Last refreshed: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    # =========================================================================
    # SECTION 1: Production - Incremental Generator
    # =========================================================================
    st.markdown("---")
    st.header("🏭 Production Data")
    st.caption("Monitor the incremental data generator and production table row counts")
    
    # Production settings
    col1, col2, col3 = st.columns(3)
    with col1:
        prod_database = st.text_input(
            "Production Database",
            value=dm.config.database,
            key="mon_prod_db",
            help="Database where production data and incremental generator are deployed"
        )
    with col2:
        prod_schema = st.text_input(
            "Data Schema",
            value=dm.config.schema,
            key="mon_prod_schema"
        )
    with col3:
        admin_schema = st.text_input(
            "Admin Schema",
            value="CLICKSTREAM_ADMIN",
            key="mon_admin_schema"
        )
    
    # Production row counts
    st.subheader(f"📊 Production Row Counts")
    
    prod_row_counts = dm.get_table_row_counts(prod_database, prod_schema)
    if prod_row_counts:
        df_prod = pd.DataFrame([
            {"Table": k, "Rows": v}
            for k, v in sorted(prod_row_counts.items())
        ])
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(df_prod.set_index("Table"))
        with col2:
            st.dataframe(df_prod, use_container_width=True, hide_index=True)
            total_rows = sum(prod_row_counts.values())
            st.metric("Total Rows", f"{total_rows:,}")
    else:
        st.info(f"No tables found in {prod_database}.{prod_schema}")
    
    # Generation log
    st.subheader("⏰ Incremental Generator History")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("From GENERATION_LOG table (sorted by BATCH_TS descending)")
    with col2:
        gen_limit = st.selectbox(
            "Rows",
            options=[25, 50, 100, 250],
            index=1,  # Default to 50
            key="gen_history_limit",
            help="Maximum rows to display"
        )
    
    try:
        log_df = dm.get_generation_log(prod_database, admin_schema, limit=gen_limit)
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.info("No generation log entries. Deploy and start the incremental generator to see data here.")
    except Exception as e:
        st.info("Generation log not available (generator may not be deployed)")
    
    # Task status from ACCOUNT_USAGE (collapsed)
    with st.expander("Task Execution History (ACCOUNT_USAGE)", expanded=False):
        st.caption("Requires SNOWFLAKE.ACCOUNT_USAGE access - has up to 45 min latency")
        try:
            task_history = dm.get_task_history(prod_database, admin_schema, limit=20)
            if not task_history.empty:
                st.dataframe(task_history, use_container_width=True, hide_index=True)
            else:
                st.info("No task history from ACCOUNT_USAGE.")
        except Exception as e:
            st.warning(f"Cannot access ACCOUNT_USAGE: {str(e)[:80]}")
    
    # =========================================================================
    # SECTION 2: Development Branch - Dynamic Tables
    # =========================================================================
    st.markdown("---")
    st.header("🌿 Development Branch")
    st.caption("Monitor Dynamic Tables in a development branch that syncs from production")
    
    # Dev branch settings
    col1, col2 = st.columns(2)
    with col1:
        dev_database = st.text_input(
            "Development Database",
            value=f"{dm.config.database}_DEV01",
            help="Enter the name of your development branch database",
            key="mon_dev_db"
        )
    
    with col2:
        dev_schema = st.text_input(
            "Data Schema",
            value=dm.config.schema,
            key="mon_dev_schema"
        )
    
    # Dev branch row counts
    st.subheader(f"📊 Development Branch Row Counts")
    
    dev_row_counts = dm.get_table_row_counts(dev_database, dev_schema)
    if dev_row_counts:
        df_dev = pd.DataFrame([
            {"Table": k, "Rows": v}
            for k, v in sorted(dev_row_counts.items())
        ])
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(df_dev.set_index("Table"))
        with col2:
            st.dataframe(df_dev, use_container_width=True, hide_index=True)
            total_dev_rows = sum(dev_row_counts.values())
            st.metric("Total Rows", f"{total_dev_rows:,}")
            
            # Show comparison to production if both have data
            if prod_row_counts:
                total_prod = sum(prod_row_counts.values())
                if total_prod > 0:
                    pct = (total_dev_rows / total_prod) * 100
                    st.caption(f"≈ {pct:.1f}% of production")
    else:
        st.info(f"No tables found in {dev_database}.{dev_schema}")
        st.markdown("""
        **To create a development branch:**
        1. Go to **🌿 Development Branch** page
        2. Create a new branch with your desired sample percentage
        """)
    
    # Dynamic Table refresh history
    st.subheader("🔄 Dynamic Table Refresh History")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("Real-time data from INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY()")
    with col2:
        dt_limit = st.selectbox(
            "Rows",
            options=[25, 50, 100, 250, 500],
            index=2,  # Default to 100
            key="dt_history_limit",
            help="Maximum rows to display"
        )
    
    try:
        dt_history = dm.get_dynamic_table_refresh_history(dev_database, dev_schema, limit=dt_limit)
        if not dt_history.empty:
            st.dataframe(dt_history, use_container_width=True, hide_index=True)
        else:
            st.info("No Dynamic Table refresh history available.")
            with st.expander("Why might this be empty?"):
                st.markdown(f"""
                - No Dynamic Tables exist in `{dev_database}.{dev_schema}`
                - DTs haven't refreshed yet (newly created or suspended)
                - Missing MONITOR privilege on the Dynamic Tables
                - Database or schema name is incorrect
                """)
    except Exception as e:
        st.error(f"Error fetching DT history: {str(e)[:100]}")
    
    # =========================================================================
    # Troubleshooting
    # =========================================================================
    st.markdown("---")
    with st.expander("🔧 Troubleshooting"):
        st.markdown(f"""
        **If data isn't showing:**
        
        1. **Production Generator**: Check that the incremental generator is deployed and running
           - Go to **🔄 Incremental Generator** page to deploy/start
        
        2. **Development Branch**: Ensure you've created a dev branch with Dynamic Tables
           - Go to **🌿 Development Branch** page to create one
        
        3. **ACCOUNT_USAGE Access**: For detailed history, grant privileges:
           ```sql
           GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE your_role;
           ```
        
        4. **Verify objects exist**:
           ```sql
           -- Check production tables
           SELECT TABLE_NAME, ROW_COUNT FROM {prod_database}.INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = '{prod_schema}';
           
           -- Check Dynamic Tables in dev branch
           SHOW DYNAMIC TABLES IN DATABASE {dev_database};
           
           -- Check task status
           SHOW TASKS LIKE 'INCREMENTAL_DATA_TASK' IN SCHEMA {prod_database}.{admin_schema};
           ```
        """)
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(60)
        st.rerun()


# =============================================================================
# Main App
# =============================================================================

def main():
    """Main application entry point."""
    page, config = render_sidebar()
    
    if page == "📊 Overview":
        render_overview()
    elif page == "📥 Initial Load":
        render_initial_load()
    elif page == "🔄 Incremental Generator":
        render_incremental_generator()
    elif page == "🌿 Development Branch":
        render_dev_branch()
    elif page == "📚 Public Datasets":
        render_public_datasets()
    elif page == "📈 Monitoring":
        render_monitoring()


if __name__ == "__main__":
    main()

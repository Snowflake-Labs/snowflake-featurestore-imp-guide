"""
Environment verification utilities.

This module demonstrates how to:
- Verify Snowflake connection details
- Check warehouse status
- Display environment information

Tested in: tests/test_chapter_00.py::test_verify_environment
"""
from snowflake.snowpark import Session
from snowflake.snowpark.version import VERSION


def verify_environment(session: Session) -> dict:
    """
    Verify and display the current Snowflake environment.
    
    Args:
        session: Active Snowpark Session
        
    Returns:
        dict with environment details
    """
    # Capture environment details
    snowflake_env = session.sql('SELECT current_user(), current_version()').collect()
    snowpark_version = VERSION
    
    # Get session details (remove quotes)
    session_role = session.get_current_role().replace('"', "")
    session_database = session.get_current_database().replace('"', "")
    session_schema = session.get_current_schema().replace('"', "")
    session_warehouse = session.get_current_warehouse().replace('"', "")
    
    # Check warehouse status
    wh_status = session.sql(f"SHOW WAREHOUSES LIKE '{session_warehouse}'").collect()[0]
    
    env_info = {
        "account": session.sql("SELECT current_account()").collect()[0][0],
        "user": snowflake_env[0][0],
        "role": session_role,
        "database": session_database,
        "schema": session_schema,
        "warehouse": session_warehouse,
        "warehouse_size": wh_status["size"].upper(),
        "warehouse_state": wh_status["state"],
        "snowflake_version": snowflake_env[0][1],
        "snowpark_version": f"{snowpark_version[0]}.{snowpark_version[1]}.{snowpark_version[2]}",
    }
    
    return env_info


def print_environment(env_info: dict) -> None:
    """Pretty print environment information."""
    print('=' * 70)
    print('CONNECTION ESTABLISHED')
    print('=' * 70)
    print(f'Account                : {env_info["account"]}')
    print(f'User                   : {env_info["user"]}')
    print(f'Role                   : {env_info["role"]}')
    print(f'Database               : {env_info["database"]}')
    print(f'Schema                 : {env_info["schema"]}')
    print(f'Warehouse              : {env_info["warehouse"]}')
    print(f'Warehouse Size         : {env_info["warehouse_size"]}')
    print(f'Warehouse State        : {env_info["warehouse_state"]}')
    print(f'Snowflake Version      : {env_info["snowflake_version"]}')
    print(f'Snowpark Version       : {env_info["snowpark_version"]}')
    print('=' * 70)


if __name__ == "__main__":
    from setup_session import create_session
    session = create_session()
    env_info = verify_environment(session)
    print_environment(env_info)

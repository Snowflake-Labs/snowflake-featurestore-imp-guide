"""
Sample data creation for quick examples.

This module demonstrates how to:
- Create inline sample data using DataFrames
- Use the Row constructor for quick data creation
- Save sample data as tables

Tested in: tests/test_chapter_00.py::test_sample_data_creation
"""
from snowflake.snowpark import Session, Row


def create_sample_events(session: Session, table_name: str = "SAMPLE_EVENTS") -> None:
    """
    Create a sample events table for quick testing.
    
    This demonstrates the inline snippet pattern for self-contained examples.
    
    Args:
        session: Active Snowpark Session
        table_name: Name for the sample table
    """
    sample_events = session.create_dataframe([
        Row(USER_ID='usr_001', EVENT_TS='2025-01-01 10:00:00', EVENT_TYPE='page_view', VALUE=1.0),
        Row(USER_ID='usr_001', EVENT_TS='2025-01-01 10:05:00', EVENT_TYPE='click', VALUE=1.0),
        Row(USER_ID='usr_001', EVENT_TS='2025-01-01 10:10:00', EVENT_TYPE='purchase', VALUE=99.0),
        Row(USER_ID='usr_002', EVENT_TS='2025-01-01 11:00:00', EVENT_TYPE='page_view', VALUE=1.0),
        Row(USER_ID='usr_002', EVENT_TS='2025-01-01 11:02:00', EVENT_TYPE='page_view', VALUE=1.0),
    ])
    
    sample_events.write.save_as_table(table_name, mode="overwrite")
    print(f"Created sample events table: {table_name}")
    
    # Show the data
    return session.table(table_name)


if __name__ == "__main__":
    from setup_session import create_session
    
    session = create_session()
    df = create_sample_events(session)
    df.show()

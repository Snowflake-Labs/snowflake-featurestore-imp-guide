"""
Spine creation examples for training and inference.

This module demonstrates how to:
- Create training spines with labels
- Create batch inference spines
- Create online inference spines

Tested in: tests/test_chapter_01.py::TestSpineExamples
"""
from snowflake.snowpark import Session, DataFrame


def create_training_spine(
    session: Session,
    source_table: str = "SESSIONS",
) -> DataFrame:
    """
    Create a training spine with entity keys, timestamps, and labels.
    
    The training spine defines:
    - Which entities to get features for (USER_ID)
    - When to get features as-of (EVENT_TS)
    - What we're predicting (LABEL)
    
    Args:
        session: Active Snowpark session
        source_table: Table containing labeled events
        
    Returns:
        Snowpark DataFrame suitable as a training spine
    """
    return session.sql(f"""
        SELECT 
            s.USER_ID,                         -- Entity key
            s.SESSION_START_TS AS EVENT_TS,    -- Point-in-time timestamp
            s.IS_CONVERTED AS LABEL            -- Target: did the session convert?
        FROM {source_table} s
        WHERE s.USER_ID IS NOT NULL
    """)


def create_batch_inference_spine(
    session: Session,
    source_table: str = "USERS",
) -> DataFrame:
    """
    Create a batch inference spine (no labels).
    
    For batch inference, we only need entity keys and timestamps.
    The label is what the model will predict.
    
    Args:
        session: Active Snowpark session
        source_table: Table containing entities to score
        
    Returns:
        Snowpark DataFrame suitable as an inference spine
    """
    return session.sql(f"""
        SELECT 
            USER_ID,                           -- Entity key
            CURRENT_TIMESTAMP() AS EVENT_TS    -- Features as of now
        FROM {source_table}
    """)


def create_historical_inference_spine(
    session: Session,
    source_table: str = "SCORING_REQUESTS",
) -> DataFrame:
    """
    Create a historical inference spine for backtesting.
    
    This is useful for evaluating model performance on historical data.
    
    Args:
        session: Active Snowpark session
        source_table: Table containing historical scoring requests
        
    Returns:
        Snowpark DataFrame suitable as a historical inference spine
    """
    return session.sql(f"""
        SELECT 
            USER_ID,                           -- Entity key
            REQUEST_TS AS EVENT_TS             -- Historical timestamp
        FROM {source_table}
        WHERE REQUEST_TS >= DATEADD('day', -30, CURRENT_DATE())
    """)


def create_online_inference_spine(
    session: Session,
    user_ids: list,
) -> DataFrame:
    """
    Create an online inference spine from a list of user IDs.
    
    For online serving, we typically don't need timestamps since
    Online Feature Tables store only current values.
    
    Args:
        session: Active Snowpark session
        user_ids: List of user IDs to get features for
        
    Returns:
        Snowpark DataFrame suitable as an online inference spine
    """
    # Create DataFrame from list of user IDs
    data = [{"USER_ID": uid} for uid in user_ids]
    return session.create_dataframe(data)


def create_multi_entity_spine(
    session: Session,
    source_table: str = "EVENTS",
) -> DataFrame:
    """
    Create a spine with multiple entity keys.
    
    This is used when retrieving features from Feature Views
    with different entities (e.g., user features AND product features).
    
    Args:
        session: Active Snowpark session
        source_table: Table containing multi-entity events
        
    Returns:
        Snowpark DataFrame with multiple entity keys
    """
    return session.sql(f"""
        SELECT 
            USER_ID,                           -- User entity key
            PRODUCT_ID,                        -- Product entity key
            EVENT_TS,                          -- Point-in-time timestamp
            CASE WHEN EVENT_NAME = 'Order Completed'
                 THEN 1 ELSE 0 END AS LABEL   -- Target: did user purchase?
        FROM {source_table}
        WHERE EVENT_NAME = 'Product Viewed'
          AND USER_ID IS NOT NULL
          AND EVENT_TS >= DATEADD('day', -90, CURRENT_DATE())
    """)


if __name__ == "__main__":
    print("Spine examples require an active Snowflake session.")
    print("See tests/test_chapter_01.py for integration tests.")

"""
Point-in-time feature retrieval examples.

This module demonstrates how to:
- Configure FeatureViews for temporal retrieval
- Generate training datasets with PIT correctness
- Use spine_timestamp_col for ASOF joins

Tested in: tests/test_chapter_06.py
"""
from snowflake.snowpark import Session, DataFrame
from snowflake.snowpark import functions as F


def create_training_spine(
    session: Session,
    label_table: str,
    entity_col: str = "USER_ID",
    timestamp_col: str = "EVENT_TS",
    label_col: str = "LABEL",
) -> DataFrame:
    """
    Create a training spine with entity keys, timestamps, and labels.
    
    Args:
        session: Active Snowpark session
        label_table: Table containing labeled events
        entity_col: Column name for entity key
        timestamp_col: Column name for event timestamp
        label_col: Column name for label
        
    Returns:
        DataFrame suitable as training spine
    """
    return session.table(label_table).select(
        F.col(entity_col),
        F.col(timestamp_col),
        F.col(label_col),
    )


def create_inference_spine(
    session: Session,
    entity_table: str,
    entity_col: str = "USER_ID",
    use_current_time: bool = True,
) -> DataFrame:
    """
    Create an inference spine for batch scoring.
    
    Args:
        session: Active Snowpark session
        entity_table: Table containing entities to score
        entity_col: Column name for entity key
        use_current_time: If True, use current timestamp
        
    Returns:
        DataFrame suitable as inference spine
    """
    spine = session.table(entity_table).select(F.col(entity_col))
    
    if use_current_time:
        spine = spine.with_column("EVENT_TS", F.current_timestamp())
    
    return spine


if __name__ == "__main__":
    print("PIT retrieval examples require an active Snowflake session.")

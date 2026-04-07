"""
Late-arriving data patterns for clickstream Feature Views.

Choose event time vs processing time for timestamp_col, or shift the spine when
you need a conservative feature cutoff.

Canonical EVENTS columns: EVENT_TS, EVENT_ID, USER_ID, PRODUCT_ID, EVENT_TYPE,
EVENT_NAME.

Tested in: tests/test_chapter_06.py
"""
from snowflake.snowpark import Session, DataFrame

_DATABASE = "FEATURE_STORE_DEMO"
_SOURCE_SCHEMA = "CLICKSTREAM_DATA"


def _fq_table(table: str) -> str:
    return f"{_DATABASE}.{_SOURCE_SCHEMA}.{table}"


def feature_view_event_time_example() -> dict:
    """
    Document pattern: timestamp_col = business event time (when click occurred).

    Feature values reflect what happened in the world; late landing in the
    warehouse does not change EVENT_TS.
    """
    return {
        "timestamp_col": "EVENT_TS",
        "rationale": (
            "ASOF uses true event ordering; Dynamic Tables pick up late rows "
            "on refresh."
        ),
    }


def feature_view_processing_time_example() -> dict:
    """
    Document pattern: timestamp_col = processing / ingest time.

    Use when governance requires 'what we knew at wall-clock time'.
    """
    return {
        "timestamp_col": "RECORDED_TS",
        "rationale": "Requires RECORDED_TS on the feature source table.",
    }


def conservative_spine_with_buffer(
    session: Session,
    events_table: str | None = None,
    buffer_hours: int = 2,
) -> DataFrame:
    """
    Shift the feature cutoff earlier than the label time (latency buffer).

    Labels stay at true EVENT_TS; FEATURE_CUTOFF_TS can be used as
    spine_timestamp_col when that matches governance (features slightly stale).
    """
    tbl = events_table or _fq_table("EVENTS")
    return session.sql(f"""
        SELECT
            e.USER_ID,
            e.EVENT_TS,
            DATEADD('hour', -{buffer_hours}, e.EVENT_TS) AS FEATURE_CUTOFF_TS,
            CASE WHEN e.EVENT_NAME = 'Order Completed' THEN 1 ELSE 0 END AS LABEL
        FROM {tbl} e
        WHERE e.USER_ID IS NOT NULL
    """)


if __name__ == "__main__":
    print(
        "late_data patterns require an active Snowflake session for DataFrame "
        "examples."
    )

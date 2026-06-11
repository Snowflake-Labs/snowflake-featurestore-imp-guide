"""
Testing strategies for Feature Store pipelines.

Patterns covered:
- Unit tests for feature logic (DataFrame / Snowpark transformations)
- Point-in-time (PIT) correctness (no future leakage in training datasets)
- Schema validation for Feature View outputs

Tested in: tests/test_chapter_12.py
"""

from __future__ import annotations

# Canonical demo identifiers (align with other guide chapters)
CANONICAL_DATABASE = "FEATURE_STORE_DEMO"
CANONICAL_FS_SCHEMA = "FEATURE_STORE"
CANONICAL_SOURCE_SCHEMA = "CLICKSTREAM_DATA"
CANONICAL_WAREHOUSE = "FS_DEV_WH"
CANONICAL_FV_VERSION = "V01"


def get_canonical_table_fqn(table: str) -> str:
    """Fully qualified name for a clickstream source table."""
    return f"{CANONICAL_DATABASE}.{CANONICAL_SOURCE_SCHEMA}.{table}"


def get_testing_patterns() -> dict:
    """
    High-level testing patterns for Feature Store work.

    Returns:
        Dict describing unit, PIT, and schema validation approaches.
    """
    return {
        "unit_feature_logic": {
            "summary": (
                "Test Snowpark or pandas transformations in isolation: fixed "
                "input DataFrames, assert expected columns, types, and "
                "row-level outputs (_CNT, _SUM, _AVG, _TS, IS_*, TOTAL_AMT)."
            ),
            "example_focus": (
                "Extract pure functions from FV SQL or Snowpark builders; "
                "pytest + local/session.table sample fixtures."
            ),
        },
        "pit_correctness": {
            "summary": (
                "After fs.generate_dataset, assert no feature timestamps "
                "exceed the spine event time (no future leakage)."
            ),
            "spine_timestamp_col": "EVENT_TS",
            "feature_view_ts_col": "FV_TS",
            "note": (
                "Use include_feature_view_timestamp_col=True when generating "
                "datasets so FV_TS is available for assertions."
            ),
        },
        "schema_validation": {
            "summary": (
                "Compare registered Feature View output columns to an "
                "expected schema (names, order where relevant, types)."
            ),
            "approaches": [
                "DESCRIBE FEATURE VIEW ...$V01 vs expected column manifest",
                "Information schema or fs.get_feature_view(...).lineage",
                "Contract tests in CI before register_feature_view",
            ],
        },
    }


def expected_user_order_fv_columns() -> list[str]:
    """
    Example expected schema for a USER × ORDERS aggregate FV (illustrative).

    Real projects should generate this from a single manifest (YAML/JSON)
    shared by registration code and tests.
    """
    return [
        "USER_ID",
        "ORDER_CNT",
        "TOTAL_AMT_SUM",
        "LAST_ORDER_TS",
    ]


def pit_no_future_leakage_assertion_docstring() -> str:
    """
    Reference sketch for docs (Snowpark col names must match spine/FV).

    Callers in tests use the same pattern with their session and FVs.
    """
    return '''def test_no_future_leakage():
    dataset = fs.generate_dataset(
        spine_df=test_spine,
        features=[fv],
        spine_timestamp_col="EVENT_TS",
        include_feature_view_timestamp_col=True,
    )
    df = dataset.read.to_snowpark_dataframe()
    assert df.filter(col("FV_TS") > col("EVENT_TS")).count() == 0'''

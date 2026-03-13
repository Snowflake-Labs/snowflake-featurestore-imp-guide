"""
Object-wrapped feature patterns.

This module demonstrates how to:
- Store embedding vectors (VECTOR type) as features
- Store JSON/semi-structured data (VARIANT/OBJECT) as features
- Store arrays (ARRAY) as features
- Consume complex-typed features for training and inference

Key concepts:
- FeatureView feature_df can contain ANY Snowflake column type
- VECTOR(FLOAT, N) is the native type for ML embeddings (max 4096 dimensions)
- VARIANT/OBJECT columns store nested JSON structures natively
- ARRAY columns store ordered lists of values
- Online serving (Hybrid Tables) supports VARIANT/OBJECT/ARRAY in non-indexed
  columns, but does NOT support VECTOR as primary/index key
- VECTOR is NOT supported in Iceberg tables

Tested in: tests/test_chapter_12.py
"""
from typing import Dict, List, Optional

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_embedding_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_table: str,
    entity_columns: List[str],
    embedding_column: str,
    vector_dimension: int,
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 day",
    warehouse: Optional[str] = None,
    extra_columns: Optional[List[str]] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView containing embedding vectors.

    Snowflake's VECTOR(FLOAT, N) type stores fixed-dimension float vectors
    efficiently. This is the recommended type for ML embeddings (e.g., from
    SNOWFLAKE.CORTEX.EMBED_TEXT_768, sentence-transformers, or custom models).

    The source table must already have the embedding column as VECTOR(FLOAT, N)
    or ARRAY (which can be cast to VECTOR in the query). If the source stores
    embeddings as ARRAY, use the `source_query` variant or pre-cast in the
    source table.

    Architecture:
        Embedding Model → Source Table (VECTOR column) → FeatureView (DT)
            → generate_training_data / retrieve_feature_values
            → Model training (cosine similarity, classification, etc.)

    Gotchas:
        - VECTOR max dimension is 4096
        - VECTOR is NOT supported in Iceberg tables
        - VECTOR is NOT supported in VARIANT columns
        - VECTOR works in Hybrid Tables (online serving) but NOT as
          primary key or secondary index key
        - For Snowpark DataFrames, VECTOR columns round-trip correctly
          through generate_training_set() and retrieve_feature_values()
        - Direct loading/unloading of VECTOR requires ARRAY cast

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name (e.g. "USER_EMBEDDINGS")
        entities: Entity objects defining join keys
        source_table: Fully qualified table with the embedding column
        entity_columns: Join-key column names (e.g. ["USER_ID"])
        embedding_column: Name of the VECTOR or ARRAY embedding column
        vector_dimension: Dimension of the embedding vector (1-4096)
        version: Version string
        timestamp_col: Optional timestamp column for point-in-time lookup
        refresh_freq: Refresh frequency (None = external/view-based)
        warehouse: Warehouse for refresh compute
        extra_columns: Additional scalar columns to include alongside embeddings
        desc: Optional description

    Returns:
        Registered FeatureView with embedding feature column
    """
    cols = list(entity_columns)
    cols.append(embedding_column)
    if extra_columns:
        cols.extend(extra_columns)
    if timestamp_col and timestamp_col not in cols:
        cols.append(timestamp_col)
    col_list = ", ".join(cols)

    feature_df = session.sql(f"SELECT {col_list} FROM {source_table}")

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Embedding FV ({vector_dimension}-dim) from {source_table}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Embedding FeatureView created: {name}/{version}")
    print(f"  vector_dim={vector_dimension}, column={embedding_column}")
    fv_type = "managed" if refresh_freq else "external"
    print(f"  type={fv_type}, source={source_table}")
    return registered_fv


def create_json_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_table: str,
    entity_columns: List[str],
    variant_columns: List[str],
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 day",
    warehouse: Optional[str] = None,
    extra_columns: Optional[List[str]] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView containing VARIANT/OBJECT (JSON) columns.

    VARIANT columns store semi-structured data (JSON, Avro, etc.) natively.
    This pattern is useful for features with dynamic schemas, nested structures,
    or when you want to store a bag of attributes that varies per entity.

    Common use cases:
        - User preferences / settings (nested JSON)
        - Product attributes (variable schema per category)
        - Session metadata (browser info, device, geo, etc.)
        - Model prediction outputs stored as structured JSON

    Consumption patterns:
        - At training time: extract fields with col:field notation in SQL
          e.g., PREFERENCES:theme::STRING, PREFERENCES:notifications:email::BOOLEAN
        - The raw VARIANT column is passed through generate_training_set()
          and retrieve_feature_values() as-is
        - Post-retrieval, parse in Python: json.loads(row["PREFERENCES"])

    Gotchas:
        - VARIANT max size is 128 MB uncompressed (practical limit is lower)
        - Dates/timestamps inside VARIANT are stored as strings (slower queries)
        - JSON null != SQL NULL (use TO_VARCHAR to convert)
        - Snowflake auto-extracts up to 200 elements for columnar optimization;
          keys with mixed types or null values are NOT extracted (slower scans)
        - Hybrid Tables (online serving) support VARIANT/OBJECT/ARRAY in
          non-indexed columns — so online serving works for JSON features
        - For best query performance on frequently accessed fields, consider
          extracting them as scalar columns alongside the VARIANT column

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name (e.g. "USER_PREFERENCES")
        entities: Entity objects defining join keys
        source_table: Fully qualified table with VARIANT/OBJECT columns
        entity_columns: Join-key column names
        variant_columns: Names of VARIANT/OBJECT columns to include as features
        version: Version string
        timestamp_col: Optional timestamp for point-in-time lookup
        refresh_freq: Refresh frequency (None = external/view-based)
        warehouse: Warehouse for refresh compute
        extra_columns: Additional scalar columns to include
        desc: Optional description

    Returns:
        Registered FeatureView with VARIANT/OBJECT feature columns
    """
    cols = list(entity_columns)
    cols.extend(variant_columns)
    if extra_columns:
        cols.extend(extra_columns)
    if timestamp_col and timestamp_col not in cols:
        cols.append(timestamp_col)
    col_list = ", ".join(cols)

    feature_df = session.sql(f"SELECT {col_list} FROM {source_table}")

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"JSON feature view from {source_table}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"JSON FeatureView created: {name}/{version}")
    print(f"  variant_columns={variant_columns}")
    fv_type = "managed" if refresh_freq else "external"
    print(f"  type={fv_type}, source={source_table}")
    return registered_fv


def create_array_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_query: str,
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 day",
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView containing ARRAY-typed feature columns.

    ARRAY columns store ordered lists of values. This pattern is useful for:
        - Tag lists (e.g., user interests: ['sports', 'tech', 'food'])
        - Recent activity sequences (last N items viewed, last N purchases)
        - Multi-hot encoded categorical features
        - Aggregated lists (ARRAY_AGG results)

    The source_query is a SQL string (not a table name) because ARRAY features
    often require aggregation (ARRAY_AGG, ARRAY_CONSTRUCT) that's best expressed
    in SQL directly.

    Consumption patterns:
        - ARRAY columns pass through generate_training_set() as-is
        - In Python: convert to list with list(row["TAGS"])
        - For ML models: often needs ARRAY_SIZE() for length, or
          ARRAY_TO_STRING() for text-based models, or one-hot encoding
        - Can cast ARRAY to VECTOR for similarity operations:
          col::VECTOR(FLOAT, N)

    Gotchas:
        - ARRAY is semi-structured — same 128 MB VARIANT limit applies
        - ARRAY elements can be mixed types (not enforced) — be careful
        - For fixed-size numeric arrays used in ML, prefer VECTOR type
        - Hybrid Tables (online serving) support ARRAY in non-indexed columns

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        source_query: SQL query producing entity columns + ARRAY feature columns
        version: Version string
        timestamp_col: Optional timestamp for point-in-time lookup
        refresh_freq: Refresh frequency (None = external/view-based)
        warehouse: Warehouse for refresh compute
        desc: Optional description

    Returns:
        Registered FeatureView with ARRAY feature columns
    """
    feature_df = session.sql(source_query)

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Array feature view: {name}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Array FeatureView created: {name}/{version}")
    fv_type = "managed" if refresh_freq else "external"
    print(f"  type={fv_type}")
    return registered_fv


def create_hybrid_json_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_table: str,
    entity_columns: List[str],
    variant_column: str,
    extracted_fields: Dict[str, str],
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 hour",
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView that stores both raw JSON and extracted scalar fields.

    This is the recommended pattern when you need:
    1. Fast scalar queries on frequently-used fields (extracted as columns)
    2. Full JSON access for ad-hoc analysis or complex nested structures

    The extracted_fields dict maps output column names to VARIANT path
    expressions with type casts, e.g.:
        {
            "THEME": "PREFERENCES:theme::STRING",
            "EMAIL_OPT_IN": "PREFERENCES:notifications:email::BOOLEAN",
            "ITEM_COUNT": "CART:items_count::INT",
        }

    This hybrid approach gives best-of-both-worlds:
    - Scalar columns: fast, type-safe, prunable by micro-partition
    - Raw VARIANT: flexible, preserves full structure for future fields

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: Entity objects defining join keys
        source_table: Fully qualified table with the VARIANT column
        entity_columns: Join-key column names
        variant_column: Name of the VARIANT/OBJECT column to keep raw
        extracted_fields: Map of output_col_name → VARIANT path expression
        version: Version string
        timestamp_col: Optional timestamp for point-in-time lookup
        refresh_freq: Refresh frequency
        warehouse: Warehouse for refresh compute
        desc: Optional description

    Returns:
        Registered FeatureView with both raw JSON and extracted scalar features
    """
    entity_cols = ", ".join(entity_columns)
    extracted_exprs = ", ".join(
        f"{expr} AS {col_name}" for col_name, expr in extracted_fields.items()
    )
    ts_col = f", {timestamp_col}" if timestamp_col else ""

    query = (
        f"SELECT {entity_cols}, {variant_column}, "
        f"{extracted_exprs}{ts_col} "
        f"FROM {source_table}"
    )

    feature_df = session.sql(query)

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Hybrid JSON FV: raw {variant_column} + extracted fields",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Hybrid JSON FeatureView created: {name}/{version}")
    print(f"  raw_column={variant_column}")
    print(f"  extracted_fields={list(extracted_fields.keys())}")
    return registered_fv


def consume_complex_features_example(
    fs: FeatureStore,
    session: Session,
    embedding_fv_name: str,
    embedding_fv_version: str,
    json_fv_name: str,
    json_fv_version: str,
    spine_table: str,
    spine_timestamp_col: Optional[str] = None,
    label_cols: Optional[List[str]] = None,
) -> None:
    """
    Demonstrate how to consume complex-typed features for training.

    Shows the end-to-end pattern of retrieving VECTOR and VARIANT features
    via generate_training_set() and preparing them for model training.

    This function is for illustration — it prints the schema and sample data
    rather than training a model.

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        embedding_fv_name: Name of the embedding FeatureView
        embedding_fv_version: Version of the embedding FeatureView
        json_fv_name: Name of the JSON FeatureView
        json_fv_version: Version of the JSON FeatureView
        spine_table: Table with entity IDs (and optional timestamps + labels)
        spine_timestamp_col: Timestamp column in spine for point-in-time join
        label_cols: Label columns to include in training set
    """
    embedding_fv = fs.get_feature_view(embedding_fv_name, embedding_fv_version)
    json_fv = fs.get_feature_view(json_fv_name, json_fv_version)

    spine_df = session.table(spine_table)

    training_set = fs.generate_training_set(
        spine_df=spine_df,
        features=[embedding_fv, json_fv],
        spine_timestamp_col=spine_timestamp_col,
        spine_label_cols=label_cols or [],
        include_feature_view_timestamp_col=False,
    )

    print("Training set schema (complex types preserved):")
    for field in training_set.schema.fields:
        print(f"  {field.name}: {field.datatype}")

    print(f"\nRow count: {training_set.count()}")
    training_set.show(5)

    print("\nTo use in Python after .to_pandas():")
    print("  - VECTOR columns → numpy arrays (use for cosine similarity, etc.)")
    print("  - VARIANT columns → JSON strings (use json.loads() to parse)")
    print("  - ARRAY columns → Python lists")
    print("  - Use fv.slice(['COL']) to select specific features from a FV")

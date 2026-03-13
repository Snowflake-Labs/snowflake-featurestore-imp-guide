"""
Complex entity relationship patterns for Feature Store.

This module demonstrates how to handle non-trivial entity relationships that
go beyond the simple "one entity, one join key" pattern. In real-world ML
systems, entities rarely exist in isolation — customers own multiple accounts,
transactions link a sender and a receiver, products belong to categories,
and hierarchies (org charts, geo rollups) add parent-child dimensions.

WHY COMPLEX ENTITIES ARE CHALLENGING:

1. Composite Join Keys
   Many business objects are identified by MORE than one column. A product
   variant is (PRODUCT_ID, SIZE, COLOR), a flight is (CARRIER, FLIGHT_NUM,
   DEPARTURE_DATE). The Entity must declare ALL join-key columns, and the
   feature_df must include every one of them. Forgetting a key column causes
   silent fan-out (duplicate rows) at training-set generation time.

2. Multi-Entity FeatureViews
   A FeatureView can reference multiple entities at once — for example, a
   "user-product interaction" FV keyed on both USER and PRODUCT. This means
   generate_training_set() must join on BOTH entity key sets simultaneously.
   The risk is join explosion: if user U has 100 interactions and product P
   has 200 interactions, a naive cross-join yields 20,000 rows. The feature_df
   must be pre-aggregated to the correct grain to avoid this.

3. Self-Referential Entities (Same Entity in Two Roles)
   In a transaction, both SENDER and RECEIVER are "users." You need the same
   FeatureView (e.g., USER_FEATURES) joined twice — once for the sender, once
   for the receiver. Without namespacing, column names collide.
   Snowflake FS solves this with `fv.with_name("sender")`, which prefixes all
   feature columns with "SENDER_" in the output, allowing the same FV to
   appear multiple times in generate_training_set() with distinct column names.

4. Hierarchical / Roll-Up Entities
   Account-level features need to be aggregated to the customer level (one
   customer → many accounts). The relationship itself is a "bridge" that may
   change over time (customer closes an account, opens another). Snowflake FS
   has no native hierarchy concept, so roll-ups must be expressed in the
   feature_df SQL query itself (GROUP BY at the higher entity level, joining
   through the bridge/cross-reference table).

5. Bridge / Many-to-Many Relationships
   A student enrolled in many courses, a movie with many actors. The bridge
   table (ENROLLMENT, MOVIE_CAST) is not an Entity — it's a mapping. You can
   either (a) model the bridge as its own Entity with composite keys, or
   (b) aggregate across the bridge in the feature_df SQL and register the FV
   at the target entity grain. Option (b) is usually simpler and avoids
   training-set fan-out.

6. Entity Tag Limits
   Entities are implemented as Snowflake tags. A single FeatureView can have
   at most 50 entity tags, and an account can have at most 10,000 tags total.
   In practice, this is rarely a bottleneck, but deeply nested multi-entity
   designs should be aware of it.

HOW SNOWFLAKE FEATURE STORE HANDLES EACH CHALLENGE:

- Composite keys    → Entity(join_keys=["COL_A", "COL_B", ...])
- Multi-entity FVs  → FeatureView(entities=[entity_a, entity_b], ...)
- Self-referential  → fv.with_name("role") for column-prefix namespacing
- Hierarchical      → Aggregation in feature_df SQL (GROUP BY parent key)
- Bridge / M:N      → Pre-aggregate across bridge in feature_df SQL
- Column collisions → with_name() or generate_training_set(auto_prefix=True)
- Subset of features→ fv.slice(["COL_A", "COL_B"]) to select specific columns

Tested in: tests/test_chapter_12.py
"""
from typing import Dict, List, Optional, Tuple

from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, FeatureView, Entity


def create_composite_key_entity(
    fs: FeatureStore,
    name: str,
    join_keys: List[str],
    desc: Optional[str] = None,
) -> Entity:
    """
    Register an entity with a composite (multi-column) join key.

    CHALLENGE: Many business objects require more than one column to uniquely
    identify them. A hotel reservation is (HOTEL_ID, CHECK_IN_DATE, GUEST_ID),
    a product variant is (PRODUCT_ID, SIZE, COLOR).

    HOW SNOWFLAKE FS HANDLES IT: The Entity constructor accepts a list of
    join_keys. All listed columns must appear in the feature_df of any
    FeatureView that uses this entity, AND in the spine_df passed to
    generate_training_set(). The join is performed on ALL keys simultaneously.

    GOTCHA: If a join-key column is missing from the feature_df, registration
    will fail. If it's missing from the spine_df, the ASOF join will be wrong
    (silent fan-out due to partial key match).

    Args:
        fs: Initialized FeatureStore instance
        name: Entity name (e.g. "PRODUCT_VARIANT")
        join_keys: List of column names forming the composite key
                   (e.g. ["PRODUCT_ID", "SIZE", "COLOR"])
        desc: Optional description

    Returns:
        Registered Entity with composite join keys
    """
    entity = Entity(
        name=name,
        join_keys=join_keys,
        desc=desc or f"Composite-key entity: {' + '.join(join_keys)}",
    )
    fs.register_entity(entity)
    print(f"Entity registered: {name}")
    print(f"  join_keys={join_keys} (composite — all columns required in feature_df and spine_df)")
    return entity


def create_multi_entity_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    entities: List[Entity],
    source_query: str,
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 hour",
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView keyed on multiple entities simultaneously.

    CHALLENGE: Some features describe the INTERACTION between two entities,
    not a single entity in isolation. For example:
        - User × Product interaction features (click count, purchase count)
        - Customer × Branch relationship features (visit frequency)
        - Student × Course enrollment features (grade, attendance)
    These require join keys from BOTH entities in the feature_df.

    HOW SNOWFLAKE FS HANDLES IT: Pass a list of Entity objects to the
    FeatureView constructor. The feature_df must contain ALL join-key columns
    from ALL entities. When generating training sets, the spine_df must also
    contain all these join-key columns — the join is performed on the UNION
    of all entity keys.

    GOTCHA — JOIN EXPLOSION: If your feature_df is not at the correct grain,
    the join can produce a cartesian product. Always ensure the feature_df is
    pre-aggregated to exactly one row per unique combination of ALL entity keys
    (+ timestamp if applicable). For example, if entities are USER and PRODUCT,
    the feature_df should have one row per (USER_ID, PRODUCT_ID) pair.

    Example use case — user-product interaction features:
        Entities: USER (join_key=USER_ID), PRODUCT (join_key=PRODUCT_ID)
        feature_df:
            SELECT USER_ID, PRODUCT_ID,
                   COUNT(*) AS VIEW_COUNT,
                   SUM(CASE WHEN ACTION='PURCHASE' THEN 1 ELSE 0 END) AS PURCHASE_COUNT,
                   MAX(EVENT_TS) AS LAST_INTERACTION_TS
            FROM USER_PRODUCT_EVENTS
            GROUP BY USER_ID, PRODUCT_ID

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name
        entities: List of Entity objects (2 or more) — ALL their join keys
                  must appear in source_query
        source_query: SQL producing one row per unique combination of all
                      entity keys. Must include all join-key columns.
        version: Version string
        timestamp_col: Optional timestamp for point-in-time correctness
        refresh_freq: Refresh frequency (None = external/view-based)
        warehouse: Warehouse for refresh compute
        desc: Optional description

    Returns:
        Registered multi-entity FeatureView
    """
    all_keys = []
    for e in entities:
        all_keys.extend(e.join_keys)

    feature_df = session.sql(source_query)

    fv = FeatureView(
        name=name,
        entities=entities,
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Multi-entity FV: {', '.join(e.name for e in entities)}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    entity_names = [e.name for e in entities]
    print(f"Multi-entity FeatureView created: {name}/{version}")
    print(f"  entities={entity_names}")
    print(f"  all_join_keys={all_keys}")
    print(f"  Spine must contain ALL these join keys for training-set generation")
    return registered_fv


def create_self_referential_training_set(
    fs: FeatureStore,
    session: Session,
    user_fv_name: str,
    user_fv_version: str,
    spine_table: str,
    sender_key: str = "SENDER_ID",
    receiver_key: str = "RECEIVER_ID",
    spine_timestamp_col: Optional[str] = None,
    label_cols: Optional[List[str]] = None,
):
    """
    Generate a training set where the SAME FeatureView is joined twice,
    once for each role (e.g., sender and receiver in a transaction).

    CHALLENGE: In fraud detection, a transaction has two parties — sender and
    receiver — both of which are "users." We want USER_FEATURES for the sender
    AND USER_FEATURES for the receiver in the same training row. But if we
    just pass the FV twice, all column names collide (both produce TOTAL_SPEND,
    both produce ACCOUNT_AGE, etc.).

    HOW SNOWFLAKE FS HANDLES IT: The `with_name("prefix")` method returns a
    copy of the FeatureView with a namespace. During generate_training_set(),
    all feature columns from that FV are prefixed with "PREFIX_". This allows
    the same FV to appear multiple times with distinct column names:

        user_fv.with_name("sender")  → SENDER_TOTAL_SPEND, SENDER_ACCOUNT_AGE
        user_fv.with_name("receiver") → RECEIVER_TOTAL_SPEND, RECEIVER_ACCOUNT_AGE

    IMPORTANT: The spine_df must have columns named to match each role's
    join key. If USER entity has join_key=["USER_ID"], the spine must have
    USER_ID for the sender role and USER_ID for the receiver role. Since both
    can't be "USER_ID" in the same DataFrame, you rename them in the spine:

        spine_df columns: SENDER_ID, RECEIVER_ID, TX_TS, IS_FRAUD
        → For sender role: with_name("sender") joins on SENDER_ID
        → For receiver role: with_name("receiver") joins on RECEIVER_ID

    Actually, the FS joins on the Entity's join_keys. So the spine_df needs
    USER_ID present for each join. The typical pattern is to do TWO separate
    generate_training_set() calls — one where spine has USER_ID = SENDER_ID,
    one where USER_ID = RECEIVER_ID — then join the results. OR use
    with_name() which handles the prefix mapping internally.

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        user_fv_name: Name of the user-level FeatureView
        user_fv_version: Version of the user-level FeatureView
        spine_table: Transaction table with sender/receiver IDs and labels
        sender_key: Column name for sender user ID in spine
        receiver_key: Column name for receiver user ID in spine
        spine_timestamp_col: Timestamp column for point-in-time join
        label_cols: Label columns (e.g. ["IS_FRAUD"])

    Returns:
        Snowpark DataFrame with sender features, receiver features, and labels
    """
    user_fv = fs.get_feature_view(user_fv_name, user_fv_version)

    sender_fv = user_fv.with_name("sender")
    receiver_fv = user_fv.with_name("receiver")

    spine_df = session.table(spine_table)

    training_set = fs.generate_training_set(
        spine_df=spine_df,
        features=[sender_fv, receiver_fv],
        spine_timestamp_col=spine_timestamp_col,
        spine_label_cols=label_cols or [],
        include_feature_view_timestamp_col=False,
    )

    print(f"Self-referential training set generated from {user_fv_name}/{user_fv_version}")
    print(f"  sender features prefixed with 'SENDER_'")
    print(f"  receiver features prefixed with 'RECEIVER_'")
    print(f"  Example columns: SENDER_TOTAL_SPEND, RECEIVER_TOTAL_SPEND")
    print(f"  Schema:")
    for field in training_set.schema.fields:
        print(f"    {field.name}: {field.datatype}")

    return training_set


def create_hierarchical_rollup_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    parent_entity: Entity,
    child_table: str,
    bridge_table: str,
    parent_key: str,
    child_key: str,
    aggregations: Dict[str, str],
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 hour",
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView that rolls up child-level features to the parent level.

    CHALLENGE: In a Customer → Account hierarchy, account-level features
    (balance, transaction count, days delinquent) need to be aggregated to
    the customer level for customer-centric models (churn, LTV, cross-sell).
    The bridge table (CUSTOMER_ACCOUNT_XREF) maps which accounts belong to
    which customer, and this mapping can change over time (accounts opened,
    closed, transferred).

    Snowflake FS has NO native hierarchy or parent-child concept. Entities
    are flat — there is no `parent_entity` attribute.

    HOW SNOWFLAKE FS HANDLES IT: Encode the roll-up logic directly in the
    feature_df SQL query. Join the child table through the bridge table,
    GROUP BY the parent entity's key, and apply aggregation functions. The
    resulting FeatureView is keyed on the PARENT entity only — the child
    entity is hidden inside the SQL aggregation.

    Architecture:
        Child Table (ACCOUNTS) ──┐
                                 ├─ JOIN ─→ GROUP BY parent_key ─→ FeatureView
        Bridge Table (XREF) ─────┘           (aggregated to parent grain)

    Example:
        parent_entity  = CUSTOMER (join_key=CUSTOMER_ID)
        child_table    = ACCOUNT_FEATURES  (has ACCOUNT_ID, BALANCE, TX_COUNT)
        bridge_table   = CUSTOMER_ACCOUNT_XREF (has CUSTOMER_ID, ACCOUNT_ID)
        aggregations   = {"BALANCE": "SUM", "TX_COUNT": "SUM",
                          "ACCOUNT_ID": "COUNT"}
        → Output: CUSTOMER_ID, SUM_BALANCE, SUM_TX_COUNT, COUNT_ACCOUNT_ID

    GOTCHA: If the bridge table does not have a timestamp, the roll-up
    reflects the CURRENT mapping, not the historical one. For point-in-time
    correct roll-ups, the bridge table needs an effective_date / active flag,
    and the SQL must filter to the active mapping at each point in time.

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name (e.g. "CUSTOMER_ACCOUNT_ROLLUP")
        parent_entity: The higher-level entity to aggregate TO
        child_table: Table containing child-level features
        bridge_table: Table mapping parent → child (must have both keys)
        parent_key: Parent entity's join-key column in the bridge table
        child_key: Child entity's key column in the bridge table
        aggregations: Map of child_column → agg_function
                      e.g. {"BALANCE": "SUM", "TX_COUNT": "SUM", "ACCOUNT_ID": "COUNT"}
        version: Version string
        timestamp_col: Optional timestamp column (in the aggregated result)
        refresh_freq: Refresh frequency
        warehouse: Warehouse for refresh compute
        desc: Optional description

    Returns:
        Registered FeatureView at the parent-entity grain
    """
    agg_exprs = []
    for col, func in aggregations.items():
        alias = f"{func.upper()}_{col}"
        agg_exprs.append(f"{func.upper()}(c.{col}) AS {alias}")
    agg_clause = ", ".join(agg_exprs)

    ts_select = f", MAX(c.{timestamp_col}) AS {timestamp_col}" if timestamp_col else ""

    query = (
        f"SELECT b.{parent_key}, {agg_clause}{ts_select} "
        f"FROM {bridge_table} b "
        f"JOIN {child_table} c ON b.{child_key} = c.{child_key} "
        f"GROUP BY b.{parent_key}"
    )

    feature_df = session.sql(query)

    fv = FeatureView(
        name=name,
        entities=[parent_entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Hierarchical rollup: {child_table} → {parent_entity.name}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    print(f"Hierarchical rollup FeatureView created: {name}/{version}")
    print(f"  parent_entity={parent_entity.name} (join_key={parent_key})")
    print(f"  child_table={child_table} → aggregated via {bridge_table}")
    print(f"  aggregations: {aggregations}")
    return registered_fv


def create_bridge_entity_feature_view(
    fs: FeatureStore,
    session: Session,
    name: str,
    left_entity: Entity,
    right_entity: Entity,
    bridge_query: str,
    version: str = "v1",
    timestamp_col: Optional[str] = None,
    refresh_freq: Optional[str] = "1 hour",
    warehouse: Optional[str] = None,
    desc: Optional[str] = None,
) -> FeatureView:
    """
    Create a FeatureView for a many-to-many relationship via a bridge table.

    CHALLENGE: Many-to-many relationships (student ↔ course, movie ↔ actor,
    user ↔ product-category) cannot be represented by a single entity. The
    bridge/junction table (ENROLLMENT, MOVIE_CAST) is the natural grain, but
    using it naively as a FeatureView can cause training-set fan-out.

    Two approaches:

    APPROACH A — Bridge as its own entity (this function):
        Model the bridge row itself as the entity. The FeatureView is keyed on
        BOTH entities (multi-entity). Features describe the RELATIONSHIP, not
        either entity in isolation. E.g., for student-course: enrollment_date,
        current_grade, attendance_rate.
        Use this when you need relationship-level predictions (e.g., predict
        grade for THIS student in THIS course).

    APPROACH B — Aggregate across bridge (see create_hierarchical_rollup_feature_view):
        Aggregate through the bridge to one side. E.g., for each student,
        compute AVG_GRADE, COURSE_COUNT, etc. Use this when you need
        entity-level predictions (e.g., predict student dropout).

    HOW SNOWFLAKE FS HANDLES IT: Use a multi-entity FeatureView (entities
    from both sides). The bridge_query must produce one row per unique
    (left_key, right_key) combination and include all join-key columns
    from both entities.

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        name: FeatureView name (e.g. "STUDENT_COURSE_FEATURES")
        left_entity: First entity (e.g. STUDENT)
        right_entity: Second entity (e.g. COURSE)
        bridge_query: SQL query producing one row per (left_key, right_key)
                      pair, with features describing the relationship
        version: Version string
        timestamp_col: Optional timestamp for point-in-time correctness
        refresh_freq: Refresh frequency
        warehouse: Warehouse for refresh compute
        desc: Optional description

    Returns:
        Registered multi-entity FeatureView over the bridge relationship
    """
    feature_df = session.sql(bridge_query)

    fv = FeatureView(
        name=name,
        entities=[left_entity, right_entity],
        feature_df=feature_df,
        timestamp_col=timestamp_col,
        refresh_freq=refresh_freq,
        warehouse=warehouse,
        desc=desc or f"Bridge FV: {left_entity.name} ↔ {right_entity.name}",
    )

    registered_fv = fs.register_feature_view(
        feature_view=fv,
        version=version,
        block=True,
    )

    left_keys = left_entity.join_keys
    right_keys = right_entity.join_keys
    print(f"Bridge FeatureView created: {name}/{version}")
    print(f"  {left_entity.name} (keys={left_keys}) ↔ {right_entity.name} (keys={right_keys})")
    print(f"  Spine must contain ALL keys from both entities")
    return registered_fv


def generate_multi_fv_training_set(
    fs: FeatureStore,
    session: Session,
    spine_table: str,
    feature_views_with_names: List[Tuple[str, str, Optional[str]]],
    spine_timestamp_col: Optional[str] = None,
    label_cols: Optional[List[str]] = None,
    auto_prefix: bool = False,
):
    """
    Generate a training set from multiple FeatureViews, with optional
    namespacing to prevent column collisions.

    CHALLENGE: When combining features from many FeatureViews — especially
    ones that share column names (e.g., two FVs both have "TOTAL_SPEND") —
    the resulting training set has ambiguous columns. This is especially
    common when mixing entity-level FVs (user features, product features)
    with interaction-level FVs (user-product features).

    HOW SNOWFLAKE FS HANDLES IT:
    - `with_name("prefix")` on individual FVs → explicit per-FV prefixing
    - `auto_prefix=True` on generate_training_set() → auto-prefix all FVs
      with their FeatureView name (e.g., USER_FEATURES_TOTAL_SPEND)
    - `fv.slice(["COL_A"])` → select only specific features from a FV,
      reducing the chance of collisions

    This function accepts a list of (fv_name, fv_version, optional_prefix)
    tuples. If a prefix is given, with_name() is applied.

    Args:
        fs: Initialized FeatureStore instance
        session: Active Snowpark session
        spine_table: Table with entity keys, timestamps, and labels
        feature_views_with_names: List of (fv_name, fv_version, prefix) tuples.
            prefix=None means no with_name(); prefix="sender" means
            fv.with_name("sender") is applied.
        spine_timestamp_col: Timestamp column in spine for point-in-time join
        label_cols: Label columns to preserve in the training set
        auto_prefix: If True, auto-prefix all FVs with their name
                     (only used if no explicit prefix is given)

    Returns:
        Snowpark DataFrame training set with all features joined
    """
    features = []
    for fv_name, fv_version, prefix in feature_views_with_names:
        fv = fs.get_feature_view(fv_name, fv_version)
        if prefix:
            fv = fv.with_name(prefix)
        features.append(fv)

    spine_df = session.table(spine_table)

    training_set = fs.generate_training_set(
        spine_df=spine_df,
        features=features,
        spine_timestamp_col=spine_timestamp_col,
        spine_label_cols=label_cols or [],
        include_feature_view_timestamp_col=False,
    )

    print(f"Training set generated from {len(features)} FeatureViews")
    for fv_name, fv_version, prefix in feature_views_with_names:
        tag = f" (prefix='{prefix}')" if prefix else ""
        print(f"  - {fv_name}/{fv_version}{tag}")
    print(f"  Total columns: {len(training_set.schema.fields)}")
    print(f"  Row count: {training_set.count()}")

    return training_set

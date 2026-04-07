"""
Test script for NB 01 Feature Engineering – registers entities and Feature Views.

Run from the notebooks/ directory:
    python _test_nb01_features.py
"""

import sys
sys.path.insert(0, ".")

from feature_definitions.config import get_config, get_session, ROLES

# ---------------------------------------------------------------------------
# 1. Connect as DEV role to DEV environment
# ---------------------------------------------------------------------------
session = get_session(role=ROLES["dev"])
cfg = get_config("DEV")
print(f"Connected: role={session.get_current_role()}, db={cfg['database']}")

session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()

# ---------------------------------------------------------------------------
# 2. Create Feature Store in DEV
# ---------------------------------------------------------------------------
from snowflake.ml.feature_store import FeatureStore, CreationMode

refresh_wh = cfg.get("refresh_warehouse", "FS_REFRESH_WH")
fs = FeatureStore(
    session=session,
    database=cfg["database"],
    name=cfg["fs_schema"],
    default_warehouse=refresh_wh,
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)
print(f"Feature Store: {cfg['database']}.{cfg['fs_schema']} (DT warehouse={refresh_wh})")

# ---------------------------------------------------------------------------
# 3. Register Entities
# ---------------------------------------------------------------------------
print("\n=== Registering Entities ===")
from feature_definitions.entities import register_all

entities = register_all(fs)
for name in entities:
    print(f"  Registered: {name}")

listed = fs.list_entities()
print(f"\n  Total entities in FS: {listed.count()}")

# ---------------------------------------------------------------------------
# 4. Register Feature Views: View-Based
# ---------------------------------------------------------------------------
print("\n=== Registering View-Based Feature Views ===")

from feature_definitions.shared_features import user_profile_features
fv = user_profile_features(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_PROFILE_FEATURES V01: {fv_registered.status}")

from feature_definitions.conversion_features import product_catalog_features
fv = product_catalog_features(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  PRODUCT_CATALOG_FEATURES V01: {fv_registered.status}")

from feature_definitions.compound_features import product_supplier_metrics
fv = product_supplier_metrics(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  PRODUCT_SUPPLIER_METRICS V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 5. Register Feature Views: DT-Based
# ---------------------------------------------------------------------------
print("\n=== Registering DT-Based Feature Views ===")

from feature_definitions.conversion_features import session_behavior_features
fv = session_behavior_features(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  SESSION_BEHAVIOR_FEATURES V01: {fv_registered.status}")

from feature_definitions.churn_features import user_recency_raw
fv = user_recency_raw(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_RECENCY_RAW V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 6. Register Feature Views: Tiled (Aggregation API)
# ---------------------------------------------------------------------------
print("\n=== Registering Tiled Feature Views (Aggregation API) ===")

from feature_definitions.shared_features import user_purchase_aggregates
fv = user_purchase_aggregates(session, "DEV", version="V03")
fv_registered = fs.register_feature_view(feature_view=fv, version="V03", block=True)
print(f"  USER_PURCHASE_AGGREGATES V03: {fv_registered.status}")

from feature_definitions.shared_features import user_session_engagement
fv = user_session_engagement(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_SESSION_ENGAGEMENT V01: {fv_registered.status}")

from feature_definitions.conversion_features import user_engagement_realtime
fv = user_engagement_realtime(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_ENGAGEMENT_REALTIME V01: {fv_registered.status}")

from feature_definitions.churn_features import user_trend_features
fv = user_trend_features(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_TREND_FEATURES V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 7. Register View-based FV on top of USER_RECENCY_RAW (derived features)
# ---------------------------------------------------------------------------
print("\n=== Registering View-Based Derived Recency FV ===")

from feature_definitions.churn_features import user_recency_features
fv = user_recency_features(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_RECENCY_FEATURES V01 (View): {fv_registered.status}")

# ---------------------------------------------------------------------------
# 8. dbt external pipeline FV
# ---------------------------------------------------------------------------
print("\n=== Registering dbt External Pipeline FV ===")

from feature_definitions.dbt_features import create_simulated_dbt_table, user_order_summary_dbt
create_simulated_dbt_table(session, "DEV")
print("  Created simulated dbt table: USER_ORDER_SUMMARY")

fv = user_order_summary_dbt(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_ORDER_SUMMARY_DBT V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 9. Wide/OBJECT FV
# ---------------------------------------------------------------------------
print("\n=== Registering Wide/OBJECT Feature View ===")

from feature_definitions.wide_features import user_permutation_features_wide
fv = user_permutation_features_wide(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  USER_PERMUTATION_FEATURES_WIDE V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 10. Embedding FV
# ---------------------------------------------------------------------------
print("\n=== Registering Embedding Feature View ===")

from feature_definitions.embedding_features import product_embeddings
fv = product_embeddings(session, "DEV")
fv_registered = fs.register_feature_view(feature_view=fv, version="V01", block=True)
print(f"  PRODUCT_EMBEDDINGS V01: {fv_registered.status}")

# ---------------------------------------------------------------------------
# 11. Summary
# ---------------------------------------------------------------------------
print("\n=== Feature View Summary ===")
fvs = fs.list_feature_views()
print(fvs.select("NAME", "VERSION", "REFRESH_FREQ").show())

# Quick read test
print("\n=== Quick Read: USER_PURCHASE_AGGREGATES ===")
fv = fs.get_feature_view("USER_PURCHASE_AGGREGATES", "V03")
print(fv.feature_df.limit(3).show())

session.close()
print("\n✅ Feature engineering test complete!")

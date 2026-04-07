"""
Test script for NB 02 ML Development – training data generation and model training.

Tests:
  - Spine creation for both models
  - generate_dataset (conversion model, SQL-level sampling)
  - generate_training_set (churn model, Python-level sampling)
  - Preprocessing + model training
  - Model Registry persistence
"""

import sys
sys.path.insert(0, ".")

from feature_definitions.config import get_config, get_session, ROLES

session = get_session(role=ROLES["dev"])
cfg = get_config("DEV")
session.sql(f"USE WAREHOUSE {cfg['warehouse']}").collect()
print(f"Connected: {session.get_current_role()}")

from snowflake.ml.feature_store import FeatureStore, CreationMode

fs = FeatureStore(
    session=session,
    database=cfg["database"],
    name=cfg["fs_schema"],
    default_warehouse=cfg["warehouse"],
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)

# ---------------------------------------------------------------------------
# 1. Feature Discovery
# ---------------------------------------------------------------------------
print("\n=== Feature Discovery ===")
fvs = fs.list_feature_views().to_pandas()
print(f"Available FVs: {len(fvs)}")

entities = fs.list_entities().to_pandas()
print(f"Available Entities: {len(entities)}")

# Explore a specific FV
fv = fs.get_feature_view("USER_PURCHASE_AGGREGATES", "V03")
print(f"\nUSER_PURCHASE_AGGREGATES description: {fv.desc}")
print(f"  Entities: {[e.name for e in fv.entities]}")

# ---------------------------------------------------------------------------
# 2. Conversion Model: Spine + generate_dataset (SQL sampling)
# ---------------------------------------------------------------------------
print("\n=== Conversion Model: Spine & generate_dataset ===")
db = cfg["database"]
src = cfg["source_schema"]
spines = cfg["spines_schema"]

# Create conversion spine: sessions with labels
session.sql(f"""
    CREATE OR REPLACE TABLE {db}.{spines}.CONVERSION_SPINE AS
    SELECT
        SESSION_ID,
        USER_ID,
        SESSION_START_TS AS LABEL_TS,
        IS_CONVERTED
    FROM {db}.{src}.SESSIONS
    WHERE USER_ID IS NOT NULL
""").collect()

row_count = session.sql(f"SELECT COUNT(*) AS CNT FROM {db}.{spines}.CONVERSION_SPINE").collect()[0]["CNT"]
print(f"  Conversion spine: {row_count} rows")

# For generate_dataset we need to use the full spine as a DF + TABLESAMPLE for SQL-level sampling
spine_df = session.sql(f"""
    SELECT * FROM {db}.{spines}.CONVERSION_SPINE
    TABLESAMPLE BERNOULLI (80)
""")
print(f"  Sampled spine (SQL TABLESAMPLE 80%): {spine_df.count()} rows")

# Get the Feature Views we need
fv_session  = fs.get_feature_view("SESSION_BEHAVIOR_FEATURES", "V01")
fv_profile  = fs.get_feature_view("USER_PROFILE_FEATURES", "V01")
fv_purchase = fs.get_feature_view("USER_PURCHASE_AGGREGATES", "V03")
fv_engage   = fs.get_feature_view("USER_SESSION_ENGAGEMENT", "V01")

# generate_dataset returns a Dataset
print("\n  Generating dataset (generate_dataset)...")
ds = fs.generate_dataset(
    name="CONVERSION_TRAINING",
    version="V03",
    spine_df=spine_df,
    features=[fv_session, fv_profile, fv_purchase, fv_engage],
    spine_timestamp_col="LABEL_TS",
    spine_label_cols=["IS_CONVERTED"],
    output_type="dataset",
    join_method="cte",
    desc="Conversion model training dataset with SQL-sampled spine",
)
print(f"  Dataset created: {ds.fully_qualified_name}")

# Read back and inspect
ds_df = ds.read.to_snowpark_dataframe()
print(f"  Dataset rows: {ds_df.count()}")
print(f"  Dataset columns: {ds_df.columns}")
sample = ds_df.limit(3).to_pandas()
print(f"  Sample:\n{sample.head(3).to_string()}")

# ---------------------------------------------------------------------------
# 3. Churn Model: Spine + generate_training_set (Python sampling)
# ---------------------------------------------------------------------------
print("\n=== Churn Model: Spine & generate_training_set ===")

# Create churn spine: users with active label at various time points
session.sql(f"""
    CREATE OR REPLACE TABLE {db}.{spines}.CHURN_SPINE AS
    SELECT
        USER_ID,
        UPDATED_TS AS LABEL_TS,
        CASE WHEN IS_ACTIVE THEN 0 ELSE 1 END AS IS_CHURNED
    FROM {db}.{src}.USERS
""").collect()

churn_spine_count = session.sql(f"SELECT COUNT(*) AS CNT FROM {db}.{spines}.CHURN_SPINE").collect()[0]["CNT"]
print(f"  Churn spine: {churn_spine_count} rows")

spine_df = session.table(f"{db}.{spines}.CHURN_SPINE")

# Get FVs for churn model — use USER_RECENCY_RAW (raw timestamps, PIT-correct)
# RFM components come from USER_PURCHASE_AGGREGATES (frequency/monetary) and
# USER_RECENCY_RAW (recency) — no separate RFM FV needed.
fv_recency_raw = fs.get_feature_view("USER_RECENCY_RAW", "V01")
fv_trend       = fs.get_feature_view("USER_TREND_FEATURES", "V01")

# generate_training_set returns a Snowpark DataFrame
print("\n  Generating training set (generate_training_set)...")
training_df = fs.generate_training_set(
    spine_df=spine_df,
    features=[fv_profile, fv_purchase, fv_recency_raw, fv_trend],
    spine_timestamp_col="LABEL_TS",
    spine_label_cols=["IS_CHURNED"],
    join_method="cte",
)
print(f"  Training set rows: {training_df.count()}")
print(f"  Training set columns: {training_df.columns}")

# Python-level sampling
sampled_pd = training_df.to_pandas().sample(frac=0.8, random_state=42)
print(f"  After Python sampling (80%): {len(sampled_pd)} rows")

# Post-retrieval PIT-correct enrichment (Ch 06 best practice)
from feature_definitions.enrichment import derive_temporal_features
sampled_pd = derive_temporal_features(sampled_pd, spine_ts_col="LABEL_TS")
print(f"  After temporal enrichment: columns={list(sampled_pd.columns)}")

# ---------------------------------------------------------------------------
# 4. Simple model training (conversion)
# ---------------------------------------------------------------------------
print("\n=== Model Training: Conversion ===")
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
import warnings
warnings.filterwarnings("ignore")

conv_pd = ds_df.to_pandas()
print(f"  Conversion dataset shape: {conv_pd.shape}")

# Select numeric features only for a quick test
numeric_cols = conv_pd.select_dtypes(include=["number"]).columns.tolist()
label_col = "IS_CONVERTED"
if label_col not in numeric_cols:
    # Convert bool -> int
    conv_pd[label_col] = conv_pd[label_col].astype(int)
    numeric_cols = [c for c in numeric_cols if c != label_col]

feature_cols = [c for c in numeric_cols if c not in [label_col, "SESSION_ID", "USER_ID"]]
print(f"  Feature columns: {feature_cols}")

X = conv_pd[feature_cols].fillna(0)
y = conv_pd[label_col]

try:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
except ValueError:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"  Train/test: {len(X_train)}/{len(X_test)}")
print(f"  Label distribution: {y.value_counts().to_dict()}")

model = GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=42)
model.fit(X_train, y_train)

y_pred_proba = model.predict_proba(X_test)[:, 1]
try:
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"  AUC: {auc:.4f}")
except:
    print("  AUC: could not compute (single class in test)")

print("  Conversion model trained successfully")

# ---------------------------------------------------------------------------
# 5. Model Registry
# ---------------------------------------------------------------------------
print("\n=== Model Registry ===")
from snowflake.ml.registry import Registry

registry = Registry(session=session, database_name=cfg["database"], schema_name=cfg["ml_datasets_schema"])

mv = registry.log_model(
    model=model,
    model_name="CONVERSION_PREDICTION",
    version_name="V01",
    sample_input_data=X_train.head(10),
    comment="GBM conversion prediction model – e2e demo",
)
print(f"  Logged: {mv.model_name} / {mv.version_name}")

# List models
models = registry.show_models()
print(f"  Models in registry: {len(models)}")
for _, row in models.iterrows():
    print(f"    {row['name']}")

session.close()
print("\n✅ ML development test complete!")

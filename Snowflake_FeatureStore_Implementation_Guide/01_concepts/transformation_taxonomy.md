# Transformation Taxonomy: MIT vs MDT vs ODT

Understanding where transformations should be performed is critical for building maintainable ML systems. This taxonomy, aligned with industry best practices (see [Dowling, 2025](../appendices/references.md)), helps you decide where each transformation belongs.

---

## The Three Types

### MIT: Model-Independent Transformations

**Where**: Feature Pipelines → Feature Store  
**Reusable**: ✅ Yes, across all models  
**Stored**: ✅ Yes, in FeatureViews

Model-Independent Transformations create features that are:
- Meaningful business metrics (total_orders_30d, avg_session_duration)
- Independent of any specific model's requirements
- Reusable by multiple teams and models

**Examples**:
```python
# Aggregations
total_spent_30d = Feature.sum("amount", "30d")
order_count_7d = Feature.count("order_id", "7d")

# Joins
user_events_with_products = events.join(products, on="product_id")

# Parsing
city = F.col("address")["city"].cast("string")

# Derived calculations
discount_rate = F.col("discount") / F.col("subtotal")
```

**Snowflake Implementation**:
- Dynamic Table-based FeatureViews
- View-based FeatureViews
- Temporal Aggregation API (Feature class)

---

### MDT: Model-Dependent Transformations

**Where**: Training Pipeline + Inference Pipeline  
**Reusable**: ⚠️ Only for the same model  
**Stored**: ✅ Yes, in Model Registry (with model)

Model-Dependent Transformations are:
- Tied to a specific model's requirements
- Must be consistent between training and inference
- Parameterized by training data statistics

**Examples**:
```python
# Scaling (parameters learned from training data)
from snowflake.ml.modeling.preprocessing import StandardScaler
scaler = StandardScaler(input_cols=["amount"], output_cols=["amount_scaled"])
scaler.fit(training_df)

# Encoding (categories from training data)
from snowflake.ml.modeling.preprocessing import OneHotEncoder
encoder = OneHotEncoder(input_cols=["category"], output_cols=["category_encoded"])

# Imputation (statistics from training data)
from snowflake.ml.modeling.impute import SimpleImputer
imputer = SimpleImputer(strategy="median")
```

**Snowflake Implementation**:
- `snowflake.ml.modeling.preprocessing` classes
- Scikit-learn pipelines saved to Model Registry
- Custom models with preprocessing logic

---

### ODT: On-Demand Transformations

**Where**: Inference time only  
**Reusable**: ⚠️ Per inference request  
**Stored**: ❌ No (computed fresh)

On-Demand Transformations are:
- Computed at request time
- Depend on current context (timestamp, request parameters)
- Too expensive or volatile to precompute

**Examples**:
```python
# Time-relative calculations
time_since_last_purchase = current_timestamp - last_purchase_ts
is_business_hours = F.hour("request_ts").between(9, 17)

# Request-context dependent
distance_to_store = haversine(user_lat, user_lon, store_lat, store_lon)

# Expensive API lookups
current_weather = fetch_weather_api(user_location)
```

**Snowflake Implementation**:
- View-based FeatureViews (query-time computation)
- Python UDFs in inference pipeline
- Post-retrieval transformations in application code

---

## Decision Framework

```
┌─────────────────────────────────────────────────────────────────┐
│                    Where Should This Transform Go?              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Is it reusable across multiple models?                        │
│      │                                                          │
│      ├── YES → MIT (Feature Pipeline)                          │
│      │         Store in FeatureView                             │
│      │                                                          │
│      └── NO → Does it depend on training data statistics?      │
│               │                                                 │
│               ├── YES → MDT (Training + Inference Pipeline)    │
│               │         Store with model in Registry            │
│               │                                                 │
│               └── NO → Does it depend on request context?      │
│                        │                                        │
│                        ├── YES → ODT (Inference time)          │
│                        │         Compute on-demand              │
│                        │                                        │
│                        └── NO → Probably MIT                   │
│                                 (re-evaluate reusability)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Examples by Use Case

### E-commerce Clickstream

| Transformation | Type | Rationale |
|----------------|------|-----------|
| `total_orders_30d` | MIT | Reusable metric, multiple models use it |
| `cart_abandonment_rate_7d` | MIT | Business metric, model-independent |
| `scaled_order_value` | MDT | Depends on training data min/max |
| `category_one_hot` | MDT | Categories fixed at training time |
| `time_since_last_visit` | ODT | Depends on inference timestamp |
| `is_sale_active` | ODT | Depends on current promotions |

### Fraud Detection

| Transformation | Type | Rationale |
|----------------|------|-----------|
| `txn_count_1h` | MIT | Reusable across fraud models |
| `avg_txn_amount_24h` | MIT | Model-independent metric |
| `amount_zscore` | MDT | Needs training data mean/std |
| `merchant_risk_score` | MIT | Pre-computed, reusable |
| `velocity_since_last_txn` | ODT | Real-time calculation |
| `device_fingerprint_match` | ODT | Request-specific lookup |

---

## Anti-Patterns to Avoid

### ❌ MDT in Feature Pipeline
```python
# BAD: Scaling in FeatureView ties it to one model
feature_df = events.with_column("amount_scaled", 
    (F.col("amount") - 45.2) / 23.1)  # Hard-coded parameters!
```

### ❌ MIT in Training Pipeline
```python
# BAD: Aggregation in training creates duplication
training_df = events.group_by("user_id").agg(
    F.sum("amount").alias("total_spent"))  # Should be in FeatureView!
```

### ❌ ODT for Stable Features
```python
# BAD: Expensive computation for stable data
def get_features(user_id):
    # Computing 30-day aggregates at request time is wasteful
    return db.query(f"SELECT SUM(amount) FROM orders WHERE ...")
```

---

## Summary

| Type | Location | Stored | Reusable | Examples |
|------|----------|--------|----------|----------|
| **MIT** | Feature Pipeline | FeatureView | ✅ All models | Aggregations, joins, parsing |
| **MDT** | Train + Inference | Model Registry | ⚠️ Same model | Scaling, encoding, imputation |
| **ODT** | Inference only | Not stored | ⚠️ Per request | Time-relative, context-dependent |

> **📖 Further Reading**: 
> - [Chapter 04: Feature Pipelines](../04_feature_pipelines/) - MIT implementation
> - [Chapter 08: Model-Dependent Preprocessing](../08_model_dependent_preprocessing/) - MDT patterns
> - [Dowling, "Building ML Systems with a Feature Store"](../appendices/references.md)

---

*Taxonomy aligned with industry best practices*

"""
Post-retrieval feature enrichment for PIT-correct training data.

Features that depend on ``CURRENT_TIMESTAMP()`` (e.g. DAYS_SINCE_LAST_ORDER,
ACCOUNT_AGE_DAYS) are silently wrong when retrieved via ASOF against a
historical spine – the value reflects DT refresh time or query time, not the
spine timestamp.

The solution (Ch 06 best practice): store raw timestamps in Feature Views,
then derive the time-relative metrics *after* retrieval using the spine's
own timestamp column.  The same function is reusable for training (with
``EVENT_TS`` / ``LABEL_TS``) and inference (with ``CURRENT_TIMESTAMP``).
"""

from __future__ import annotations

import pandas as pd


_RAW_TS_COLS = [
    "LAST_ORDER_TS",
    "LAST_SESSION_TS",
    "LAST_LOGIN_TS",
    "REGISTRATION_TS",
]


def derive_temporal_features(
    df: pd.DataFrame,
    spine_ts_col: str = "LABEL_TS",
    *,
    drop_raw: bool = True,
) -> pd.DataFrame:
    """Derive DAYS_SINCE_* and ACCOUNT_AGE_DAYS from raw timestamps.

    Args:
        df: Training or scoring DataFrame containing the raw timestamp
            columns from ``USER_RECENCY_RAW`` and/or ``USER_PROFILE_FEATURES``.
        spine_ts_col: Column holding the reference timestamp.  For training
            this is typically the spine label timestamp; for inference it
            can be a column set to ``CURRENT_TIMESTAMP()``.
        drop_raw: If True, drop the raw timestamp columns after derivation.

    Returns:
        DataFrame with derived ``DAYS_SINCE_*`` and ``ACCOUNT_AGE_DAYS``
        columns added (and raw timestamps optionally removed).
    """
    df = df.copy()
    ref = pd.to_datetime(df[spine_ts_col], utc=True)

    mapping = {
        "LAST_ORDER_TS":   "DAYS_SINCE_LAST_ORDER",
        "LAST_SESSION_TS": "DAYS_SINCE_LAST_SESSION",
        "LAST_LOGIN_TS":   "DAYS_SINCE_LAST_LOGIN",
        "REGISTRATION_TS": "ACCOUNT_AGE_DAYS",
    }

    for raw_col, derived_col in mapping.items():
        if raw_col not in df.columns:
            continue
        raw = pd.to_datetime(df[raw_col], utc=True, errors="coerce")
        delta_days = (ref - raw).dt.total_seconds() / 86400.0
        if "DAYS_SINCE" in derived_col:
            delta_days = delta_days.fillna(9999.0)
        df[derived_col] = delta_days.round(0).astype("Int64")

    if drop_raw:
        df = df.drop(
            columns=[c for c in _RAW_TS_COLS if c in df.columns],
            errors="ignore",
        )

    return df

"""
Chapter 06: Temporal Features - Code Examples

Point-in-time correctness, ASOF joins, data leakage prevention, backfill, and
clickstream-oriented patterns (EVENTS, SESSIONS, ORDERS).

Modules:
- pit_retrieval: spines and EVENTS-based Feature View builder
- timestamp_patterns: timestamp_col patterns for EVENTS / ORDERS / snapshots
- late_data: event vs processing time and conservative spines
- backfill_operations: manual refresh and version registration (V01, …)
- validation: leakage checks and temporal join stats
"""

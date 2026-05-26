"""
Streaming feature patterns.

This module demonstrates how to:
- Implement near real-time features
- Work with Snowflake Streams
- Design streaming architectures

Tested in: tests/test_chapter_12.py
"""


def get_streaming_options() -> dict:
    """
    Get options for implementing streaming features.
    
    Returns:
        Dict with streaming options
    """
    return {
        "short_refresh_dt": {
            "approach": "Dynamic Table with 1-minute refresh",
            "latency": "1-2 minutes",
            "cost": "Higher",
            "complexity": "Low",
            "code": """
                FeatureView(
                    name="USER_REALTIME_FEATURES",
                    refresh_freq="1 minute",
                    # feature_df from FEATURE_STORE_DEMO.CLICKSTREAM_DATA.EVENTS
                    # ...
                )
            """,
        },
        "external_streaming": {
            "approach": "Kafka/Snowpipe → Staging → View FV",
            "latency": "Seconds",
            "cost": "Variable",
            "complexity": "High",
            "code": """
                # External: Kafka → Snowpipe → clickstream staging
                # Feature View reads from FEATURE_STORE_DEMO.CLICKSTREAM_DATA (or staging)
                FeatureView(
                    name="SESSION_EVENT_FEATURES",
                    feature_df=session.table(
                        "FEATURE_STORE_DEMO.CLICKSTREAM_DATA.EVENTS_STAGING"
                    ),
                    # No refresh_freq (View-based)
                )
            """,
        },
        "future_streaming_fv": {
            "approach": "Native Streaming Feature View (rollout; verify availability in your account)",
            "latency": "Sub-second (target)",
            "cost": "TBD",
            "complexity": "Low",
            "code": """
                # Streaming Feature View API — confirm preview/GA status in release notes
                FeatureView(
                    name="USER_STREAMING_FEATURES",
                    source_stream="USER_EVENTS_STREAM",
                    streaming=True,
                )
            """,
        },
    }


if __name__ == "__main__":
    options = get_streaming_options()
    print("Streaming Feature Options:")
    for name, config in options.items():
        print(f"\n{name}:")
        print(f"  Latency: {config['latency']}")
        print(f"  Complexity: {config['complexity']}")

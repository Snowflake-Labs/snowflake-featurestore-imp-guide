"""
Feature definitions package – "features-as-code".

Import from sub-modules to get Entity and FeatureView factory functions
that return *unregistered* objects ready for ``fs.register_feature_view()``.

All definitions are parameterised by environment via ``config.get_config()``.
"""

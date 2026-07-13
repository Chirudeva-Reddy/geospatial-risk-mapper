"""Smoke tests: the package imports and core wiring exists."""

import importlib


def test_package_imports() -> None:
    """Test that package imports successfully."""
    mod = importlib.import_module("geo_risk")
    assert hasattr(mod, "__version__")


def test_config_loads() -> None:
    """Test that configuration loads."""
    from geo_risk.config import settings

    assert settings.app_name == "geospatial-risk-mapper"
    assert settings.target_crs == "EPSG:4326"

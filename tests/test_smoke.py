"""Smoke tests: the package imports and core wiring exists.
Every repo replaces/extends these with real unit tests."""

import importlib


def test_package_imports() -> None:
    mod = importlib.import_module("project_name")
    assert hasattr(mod, "__version__")


def test_config_loads() -> None:
    from project_name.config import settings

    assert settings.app_name

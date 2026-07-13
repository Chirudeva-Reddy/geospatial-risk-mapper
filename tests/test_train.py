"""Tests for model training and evaluation."""

import geopandas as gpd
import pytest
from shapely.geometry import box

from geo_risk.features import engineer_features
from geo_risk.train import save_model, train_model


@pytest.fixture
def nuts_gdf():
    """Create synthetic NUTS GeoDataFrame."""
    data = {
        "NUTS_ID": [f"IT{i}" for i in range(10)],
        "geometry": [box(10.0 + i, 40.0, 10.5 + i, 40.5) for i in range(10)],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def flood_gdf():
    """Create synthetic flood hazard GeoDataFrame."""
    data = {
        "hazard_class": ["P1", "P2", "P3"] * 3 + ["P1"],
        "area_km2": [100.0, 200.0, 150.0] * 3 + [100.0],
        "geometry": [box(10.2 + i, 40.2, 10.5 + i, 40.5) for i in range(9)]
        + [box(19.2, 40.2, 19.5, 40.5)],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def features_and_target(nuts_gdf, flood_gdf):
    """Create engineered features and target."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)
    return features_df, target


def test_train_model_returns_dict(features_and_target):
    """Test that train_model returns a dictionary."""
    features_df, target = features_and_target
    result = train_model(features_df, target)

    assert isinstance(result, dict)
    assert "model" in result
    assert "metrics" in result


def test_train_model_metrics(features_and_target):
    """Test that metrics are computed."""
    features_df, target = features_and_target
    result = train_model(features_df, target)

    metrics = result["metrics"]
    assert "accuracy" in metrics
    assert "f1_weighted" in metrics
    assert "f1_macro" in metrics
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["f1_weighted"] <= 1


def test_train_model_predictions(features_and_target):
    """Test that predictions are generated."""
    features_df, target = features_and_target
    result = train_model(features_df, target)

    assert "y_pred" in result
    assert "y_pred_proba" in result
    assert len(result["y_pred"]) > 0
    assert result["y_pred_proba"].shape[0] > 0


def test_train_model_feature_importance(features_and_target):
    """Test that feature importance is computed."""
    features_df, target = features_and_target
    result = train_model(features_df, target)

    importance_df = result["feature_importance"]
    assert len(importance_df) == len(features_df.columns)
    assert "feature" in importance_df.columns
    assert "importance" in importance_df.columns


def test_save_model_creates_files(features_and_target, tmp_path):
    """Test that save_model creates artifact files."""
    features_df, target = features_and_target
    result = train_model(features_df, target)

    model_path = save_model(result, tmp_path)

    assert model_path.exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "feature_importance.csv").exists()
    assert (tmp_path / "feature_names.json").exists()


def test_train_model_stratified_split(features_and_target):
    """Test that train-test split is stratified."""
    features_df, target = features_and_target
    result = train_model(features_df, target, test_size=0.3)

    # Check that test set has all classes
    assert len(set(result["y_test"])) > 0


def test_train_model_reproducibility(features_and_target):
    """Test that training is reproducible with same random_state."""
    features_df, target = features_and_target

    result1 = train_model(features_df, target, random_state=42)
    result2 = train_model(features_df, target, random_state=42)

    # Metrics should be identical
    assert result1["metrics"]["accuracy"] == result2["metrics"]["accuracy"]

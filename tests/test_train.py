"""Tests for model training and evaluation."""


import geopandas as gpd
import pytest
from shapely.geometry import box

from geo_risk.features import engineer_features
from geo_risk.train import save_model, train_classifier, train_regressor

N_REGIONS = 20


@pytest.fixture
def nuts_gdf():
    """Create synthetic NUTS GeoDataFrame with N_REGIONS non-overlapping regions."""
    data = {
        "NUTS_ID": [f"IT{i}" for i in range(N_REGIONS)],
        "geometry": [box(10.0 + i, 40.0, 11.0 + i, 41.0) for i in range(N_REGIONS)],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def flood_gdf():
    """Create synthetic flood hazard GeoDataFrame with a genuinely varying,
    monotonically increasing overlap fraction per region (roughly 5%-95%),
    so the quantile-based target in engineer_features has enough distinct
    values to split into balanced tertiles (avoids all regions collapsing to
    an identical flood_fraction, which previously happened when every flood
    box used the same fixed proportional offset as its region)."""
    hazard_classes = ["P1", "P2", "P3"]
    geometries = []
    for i in range(N_REGIONS):
        frac = (i + 1) / (N_REGIONS + 1)  # distinct, increasing, strictly in (0, 1)
        x0 = 10.0 + i
        geometries.append(box(x0, 40.0, x0 + frac, 41.0))
    data = {
        "hazard_class": [hazard_classes[i % 3] for i in range(N_REGIONS)],
        "area_km2": [1.0] * N_REGIONS,  # unused by engineer_features (area is
        # computed from geometry), kept only for schema compatibility
        "geometry": geometries,
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def features_and_target(nuts_gdf, flood_gdf):
    """Create engineered features and target."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)
    return features_df, target


def test_train_classifier_returns_dict(features_and_target):
    """Test that train_classifier returns a dictionary."""
    features_df, target = features_and_target
    result = train_classifier(features_df, target)

    assert isinstance(result, dict)
    assert "model" in result
    assert "metrics" in result
    assert result["model_type"] == "classifier"


def test_train_classifier_metrics(features_and_target):
    """Test that classifier metrics are computed."""
    features_df, target = features_and_target
    result = train_classifier(features_df, target)

    metrics = result["metrics"]
    assert "accuracy" in metrics
    assert "f1_weighted" in metrics
    assert "f1_macro" in metrics
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["f1_weighted"] <= 1


def test_train_regressor_returns_dict(features_and_target):
    """Test that train_regressor returns a dictionary."""
    features_df, target = features_and_target
    target_continuous = features_df["flood_fraction"]
    result = train_regressor(features_df, target_continuous)

    assert isinstance(result, dict)
    assert "model" in result
    assert "metrics" in result
    assert result["model_type"] == "regressor"


def test_train_regressor_metrics(features_and_target):
    """Test that regressor metrics are computed."""
    features_df, target = features_and_target
    target_continuous = features_df["flood_fraction"]
    result = train_regressor(features_df, target_continuous)

    metrics = result["metrics"]
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "r2" in metrics
    assert metrics["mae"] >= 0
    assert metrics["rmse"] >= 0


def test_train_classifier_feature_importance(features_and_target):
    """Test that classifier feature importance is computed."""
    features_df, target = features_and_target
    result = train_classifier(features_df, target)

    importance_df = result["feature_importance"]
    assert len(importance_df) == len(features_df.columns)
    assert "feature" in importance_df.columns
    assert "importance" in importance_df.columns


def test_save_model_creates_files(features_and_target, tmp_path):
    """Test that save_model creates artifact files."""
    features_df, target = features_and_target
    result = train_classifier(features_df, target)

    model_path = save_model(result, tmp_path, "test_model")

    assert model_path.exists()
    assert (tmp_path / "test_model_metrics.json").exists()
    assert (tmp_path / "test_model_feature_importance.csv").exists()
    assert (tmp_path / "test_model_feature_names.json").exists()


def test_train_classifier_reproducibility(features_and_target):
    """Test that classifier training is reproducible."""
    features_df, target = features_and_target

    result1 = train_classifier(features_df, target, random_state=42)
    result2 = train_classifier(features_df, target, random_state=42)

    # Metrics should be identical
    assert result1["metrics"]["accuracy"] == result2["metrics"]["accuracy"]


def test_train_regressor_reproducibility(features_and_target):
    """Test that regressor training is reproducible."""
    features_df, target = features_and_target
    target_continuous = features_df["flood_fraction"]

    result1 = train_regressor(features_df, target_continuous, random_state=42)
    result2 = train_regressor(features_df, target_continuous, random_state=42)

    # Metrics should be nearly identical (allow for floating-point precision)
    assert result1["metrics"]["mae"] == pytest.approx(result2["metrics"]["mae"])

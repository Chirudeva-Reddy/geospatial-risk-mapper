"""Tests for prediction utilities."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from geo_risk.features import engineer_features
from geo_risk.predict import PredictionRequest, PredictionResponse, RiskPredictor
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
def trained_model(nuts_gdf, flood_gdf, tmp_path):
    """Create and save a trained model."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)
    result = train_model(features_df, target)
    save_model(result, tmp_path)
    return tmp_path


def test_prediction_request_validation():
    """Test that PredictionRequest validates inputs."""
    # Valid request
    req = PredictionRequest(
        flood_area_km2=100.0,
        flood_fraction=0.1,
        hazard_p3_fraction=0.05,
        hazard_p2_fraction=0.05,
        region_area_km2=1000.0,
    )
    assert req.flood_area_km2 == 100.0

    # Invalid: negative area
    with pytest.raises(ValueError):
        PredictionRequest(
            flood_area_km2=-100.0,
            flood_fraction=0.1,
            hazard_p3_fraction=0.05,
            hazard_p2_fraction=0.05,
            region_area_km2=1000.0,
        )

    # Invalid: fraction > 1
    with pytest.raises(ValueError):
        PredictionRequest(
            flood_area_km2=100.0,
            flood_fraction=1.5,
            hazard_p3_fraction=0.05,
            hazard_p2_fraction=0.05,
            region_area_km2=1000.0,
        )


def test_prediction_response_schema():
    """Test that PredictionResponse has correct schema."""
    resp = PredictionResponse(
        risk_class=1,
        risk_label="Medium",
        confidence=0.85,
        probabilities={"low": 0.1, "medium": 0.85, "high": 0.05},
    )

    assert resp.risk_class == 1
    assert resp.risk_label == "Medium"
    assert 0 <= resp.confidence <= 1


def test_risk_predictor_loads_model(trained_model):
    """Test that RiskPredictor loads trained model."""
    predictor = RiskPredictor(trained_model)

    assert predictor.model is not None
    assert len(predictor.feature_names) > 0


def test_risk_predictor_predict(trained_model):
    """Test that RiskPredictor can make predictions."""
    predictor = RiskPredictor(trained_model)

    features = {
        "flood_area_km2": 100.0,
        "flood_fraction": 0.1,
        "hazard_p3_fraction": 0.05,
        "hazard_p2_fraction": 0.05,
        "region_area_km2": 1000.0,
        "p3_p2_ratio": 1.0,
        "high_hazard_indicator": 0,
    }

    response = predictor.predict(features)

    assert isinstance(response, PredictionResponse)
    assert 0 <= response.risk_class <= 2
    assert 0 <= response.confidence <= 1
    assert sum(response.probabilities.values()) == pytest.approx(1.0)


def test_risk_predictor_predict_batch(trained_model):
    """Test that RiskPredictor can make batch predictions."""
    predictor = RiskPredictor(trained_model)

    features_df = pd.DataFrame(
        {
            "flood_area_km2": [100.0, 200.0, 50.0],
            "flood_fraction": [0.1, 0.2, 0.05],
            "hazard_p3_fraction": [0.05, 0.1, 0.02],
            "hazard_p2_fraction": [0.05, 0.1, 0.03],
            "region_area_km2": [1000.0, 1000.0, 1000.0],
            "p3_p2_ratio": [1.0, 1.0, 0.67],
            "high_hazard_indicator": [0, 1, 0],
        },
        index=["IT1", "IT2", "IT3"],
    )

    results = predictor.predict_batch(features_df)

    assert len(results) == 3
    assert "NUTS_ID" in results.columns
    assert "risk_class" in results.columns
    assert "confidence" in results.columns


def test_risk_predictor_missing_model(tmp_path):
    """Test that RiskPredictor raises error if model not found."""
    with pytest.raises(FileNotFoundError):
        RiskPredictor(tmp_path)


def test_risk_predictor_missing_features(trained_model):
    """Test that predict raises error if features are missing."""
    predictor = RiskPredictor(trained_model)

    features = {
        "flood_area_km2": 100.0,
        # Missing other features
    }

    with pytest.raises(ValueError, match="Missing features"):
        predictor.predict(features)

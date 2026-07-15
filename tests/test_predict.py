"""Tests for prediction utilities."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from geo_risk.features import engineer_features
from geo_risk.predict import (
    ClassificationResponse,
    PredictionRequest,
    RegressionResponse,
    RiskPredictor,
)
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
def trained_models(nuts_gdf, flood_gdf, tmp_path):
    """Create and save trained classifier and regressor."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)
    target_continuous = features_df["flood_fraction"]

    classifier_result = train_classifier(features_df, target)
    regressor_result = train_regressor(features_df, target_continuous)

    save_model(classifier_result, tmp_path, "classifier")
    save_model(regressor_result, tmp_path, "regressor")

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


def test_classification_response_schema():
    """Test that ClassificationResponse has correct schema."""
    resp = ClassificationResponse(
        risk_class=1,
        risk_label="Medium",
        confidence=0.85,
        probabilities={"low": 0.1, "medium": 0.85, "high": 0.05},
    )

    assert resp.risk_class == 1
    assert resp.risk_label == "Medium"
    assert 0 <= resp.confidence <= 1


def test_regression_response_schema():
    """Test that RegressionResponse has correct schema."""
    resp = RegressionResponse(
        risk_score=0.65,
        risk_label="Medium",
    )

    assert 0 <= resp.risk_score <= 1
    assert resp.risk_label == "Medium"


def test_risk_predictor_loads_models(trained_models):
    """Test that RiskPredictor loads both models."""
    predictor = RiskPredictor(trained_models)

    assert predictor.classifier is not None
    assert predictor.regressor is not None
    assert len(predictor.feature_names) > 0


def test_risk_predictor_classification(trained_models):
    """Test that RiskPredictor can make classification predictions."""
    predictor = RiskPredictor(trained_models)

    features = {
        "flood_area_km2": 100.0,
        "flood_fraction": 0.1,
        "hazard_p3_fraction": 0.05,
        "hazard_p2_fraction": 0.05,
        "region_area_km2": 1000.0,
        "p3_p2_ratio": 1.0,
        "high_hazard_indicator": 0,
    }

    response = predictor.predict_classification(features)

    assert isinstance(response, ClassificationResponse)
    assert 0 <= response.risk_class <= 2
    assert 0 <= response.confidence <= 1
    assert sum(response.probabilities.values()) == pytest.approx(1.0)


def test_risk_predictor_regression(trained_models):
    """Test that RiskPredictor can make regression predictions."""
    predictor = RiskPredictor(trained_models)

    features = {
        "flood_area_km2": 100.0,
        "flood_fraction": 0.1,
        "hazard_p3_fraction": 0.05,
        "hazard_p2_fraction": 0.05,
        "region_area_km2": 1000.0,
        "p3_p2_ratio": 1.0,
        "high_hazard_indicator": 0,
    }

    response = predictor.predict_regression(features)

    assert isinstance(response, RegressionResponse)
    assert 0 <= response.risk_score <= 1
    assert response.risk_label in ["Low", "Medium", "High"]


def test_risk_predictor_batch_classification(trained_models):
    """Test that RiskPredictor can make batch classification predictions."""
    predictor = RiskPredictor(trained_models)

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

    results = predictor.predict_batch_classification(features_df)

    assert len(results) == 3
    assert "NUTS_ID" in results.columns
    assert "risk_class" in results.columns
    assert "confidence" in results.columns


def test_risk_predictor_batch_regression(trained_models):
    """Test that RiskPredictor can make batch regression predictions."""
    predictor = RiskPredictor(trained_models)

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

    results = predictor.predict_batch_regression(features_df)

    assert len(results) == 3
    assert "NUTS_ID" in results.columns
    assert "risk_score" in results.columns
    assert "risk_label" in results.columns


def test_risk_predictor_missing_models(tmp_path):
    """Test that RiskPredictor raises error if models not found."""
    with pytest.raises(FileNotFoundError):
        RiskPredictor(tmp_path)


def test_risk_predictor_missing_features(trained_models):
    """Test that predict raises error if features are missing."""
    predictor = RiskPredictor(trained_models)

    features = {
        "flood_area_km2": 100.0,
        # Missing other features
    }

    with pytest.raises(ValueError, match="Missing features"):
        predictor.predict_classification(features)

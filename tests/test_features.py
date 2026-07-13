"""Tests for feature engineering and spatial joins."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from geo_risk.features import add_spatial_features, engineer_features


@pytest.fixture
def nuts_gdf():
    """Create synthetic NUTS GeoDataFrame."""
    data = {
        "NUTS_ID": ["IT1", "IT2", "IT3"],
        "geometry": [
            box(10.0, 40.0, 11.0, 41.0),
            box(11.0, 40.0, 12.0, 41.0),
            box(12.0, 40.0, 13.0, 41.0),
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def flood_gdf():
    """Create synthetic flood hazard GeoDataFrame."""
    data = {
        "hazard_class": ["P1", "P2", "P3"],
        "area_km2": [100.0, 200.0, 150.0],
        "geometry": [
            box(10.2, 40.2, 10.5, 40.5),
            box(11.2, 40.2, 11.5, 40.5),
            box(12.2, 40.2, 12.5, 40.5),
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


def test_engineer_features_returns_dataframe(nuts_gdf, flood_gdf):
    """Test that engineer_features returns a DataFrame."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)

    assert isinstance(features_df, pd.DataFrame)
    assert isinstance(target, pd.Series)


def test_engineer_features_shape(nuts_gdf, flood_gdf):
    """Test that engineered features have correct shape."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)

    assert len(features_df) == len(nuts_gdf)
    assert len(target) == len(nuts_gdf)


def test_engineer_features_columns(nuts_gdf, flood_gdf):
    """Test that engineered features have expected columns."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)

    expected_cols = [
        "flood_area_km2",
        "flood_fraction",
        "hazard_p3_fraction",
        "hazard_p2_fraction",
        "region_area_km2",
    ]
    for col in expected_cols:
        assert col in features_df.columns


def test_engineer_features_target_values(nuts_gdf, flood_gdf):
    """Test that target has valid risk classes."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)

    assert target.dtype == int
    assert all(target.isin([0, 1, 2]))


def test_engineer_features_index(nuts_gdf, flood_gdf):
    """Test that features are indexed by NUTS_ID."""
    features_df, target = engineer_features(nuts_gdf, flood_gdf)

    assert features_df.index.name == "NUTS_ID"
    assert all(features_df.index.isin(nuts_gdf["NUTS_ID"]))


def test_add_spatial_features(nuts_gdf, flood_gdf):
    """Test that add_spatial_features adds new columns."""
    features_df, _ = engineer_features(nuts_gdf, flood_gdf)
    original_cols = len(features_df.columns)

    features_df = add_spatial_features(features_df)
    new_cols = len(features_df.columns)

    assert new_cols > original_cols
    assert "p3_p2_ratio" in features_df.columns
    assert "high_hazard_indicator" in features_df.columns


def test_flood_fraction_bounds(nuts_gdf, flood_gdf):
    """Test that flood_fraction is between 0 and 1."""
    features_df, _ = engineer_features(nuts_gdf, flood_gdf)

    assert (features_df["flood_fraction"] >= 0).all()
    assert (features_df["flood_fraction"] <= 1).all()


def test_hazard_fractions_bounds(nuts_gdf, flood_gdf):
    """Test that hazard fractions are between 0 and 1."""
    features_df, _ = engineer_features(nuts_gdf, flood_gdf)

    assert (features_df["hazard_p3_fraction"] >= 0).all()
    assert (features_df["hazard_p3_fraction"] <= 1).all()
    assert (features_df["hazard_p2_fraction"] >= 0).all()
    assert (features_df["hazard_p2_fraction"] <= 1).all()


def test_crs_mismatch_raises(nuts_gdf, flood_gdf):
    """Test that CRS mismatch raises ValueError."""
    flood_gdf_wrong_crs = flood_gdf.to_crs("EPSG:3857")

    with pytest.raises(ValueError, match="CRS mismatch"):
        engineer_features(nuts_gdf, flood_gdf_wrong_crs)

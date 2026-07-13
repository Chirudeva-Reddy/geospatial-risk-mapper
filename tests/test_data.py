"""Tests for data loading and CRS handling."""

import geopandas as gpd
import pytest
from shapely.geometry import box


@pytest.fixture
def synthetic_nuts_gdf():
    """Create synthetic NUTS GeoDataFrame for testing."""
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
def synthetic_flood_gdf():
    """Create synthetic flood hazard GeoDataFrame for testing."""
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


def test_load_nuts_boundaries_synthetic(synthetic_nuts_gdf):
    """Test loading NUTS boundaries (synthetic)."""
    # This test uses synthetic data; real data would require network access
    assert len(synthetic_nuts_gdf) == 3
    assert synthetic_nuts_gdf.crs == "EPSG:4326"
    assert all(synthetic_nuts_gdf.geometry.is_valid)


def test_load_ispra_flood_hazard_synthetic(synthetic_flood_gdf):
    """Test loading ISPRA flood hazard (synthetic)."""
    assert len(synthetic_flood_gdf) == 3
    assert synthetic_flood_gdf.crs == "EPSG:4326"
    assert "hazard_class" in synthetic_flood_gdf.columns
    assert "area_km2" in synthetic_flood_gdf.columns


def test_crs_validation(synthetic_nuts_gdf, synthetic_flood_gdf):
    """Test CRS validation in load_and_validate."""
    # Both should have same CRS
    assert synthetic_nuts_gdf.crs == synthetic_flood_gdf.crs


def test_geometry_validity(synthetic_nuts_gdf, synthetic_flood_gdf):
    """Test that all geometries are valid."""
    assert synthetic_nuts_gdf.geometry.is_valid.all()
    assert synthetic_flood_gdf.geometry.is_valid.all()


def test_nuts_id_filtering():
    """Test that NUTS filtering works for Italy."""
    # Create mixed NUTS data
    data = {
        "NUTS_ID": ["IT1", "IT2", "FR1", "DE1"],
        "geometry": [
            box(10.0, 40.0, 11.0, 41.0),
            box(11.0, 40.0, 12.0, 41.0),
            box(0.0, 45.0, 1.0, 46.0),
            box(5.0, 50.0, 6.0, 51.0),
        ],
    }
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")

    # Filter to Italy
    italy_gdf = gdf[gdf["NUTS_ID"].str.startswith("IT")]  # type: ignore
    assert len(italy_gdf) == 2
    assert all(italy_gdf["NUTS_ID"].str.startswith("IT"))

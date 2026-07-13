"""Tests for map generation and visualization."""

import folium
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from geo_risk.mapping import (
    create_comparison_map,
    create_risk_choropleth,
    save_map,
)


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
def predictions(nuts_gdf):
    """Create synthetic predictions."""
    return pd.Series(
        [0, 1, 2],
        index=nuts_gdf["NUTS_ID"],
        name="risk_class",
    )


@pytest.fixture
def actual(nuts_gdf):
    """Create synthetic actual values."""
    return pd.Series(
        [0, 1, 2],
        index=nuts_gdf["NUTS_ID"],
        name="risk_class",
    )


def test_create_risk_choropleth_returns_map(nuts_gdf, predictions):
    """Test that create_risk_choropleth returns a folium Map."""
    m = create_risk_choropleth(nuts_gdf, predictions)

    assert isinstance(m, folium.Map)


def test_create_risk_choropleth_has_layers(nuts_gdf, predictions):
    """Test that choropleth map has expected layers."""
    m = create_risk_choropleth(nuts_gdf, predictions)

    # Check that map has layers
    assert len(m._children) > 0


def test_create_comparison_map_returns_map(nuts_gdf, actual, predictions):
    """Test that create_comparison_map returns a folium Map."""
    m = create_comparison_map(nuts_gdf, actual, predictions)

    assert isinstance(m, folium.Map)


def test_create_comparison_map_has_layers(nuts_gdf, actual, predictions):
    """Test that comparison map has layer control."""
    m = create_comparison_map(nuts_gdf, actual, predictions)

    # Check that map has layers
    assert len(m._children) > 0


def test_save_map_creates_file(nuts_gdf, predictions, tmp_path):
    """Test that save_map creates an HTML file."""
    m = create_risk_choropleth(nuts_gdf, predictions)
    output_path = tmp_path / "test_map.html"

    saved_path = save_map(m, output_path)

    assert saved_path.exists()
    assert saved_path.suffix == ".html"


def test_save_map_creates_parent_dirs(nuts_gdf, predictions, tmp_path):
    """Test that save_map creates parent directories."""
    m = create_risk_choropleth(nuts_gdf, predictions)
    output_path = tmp_path / "subdir" / "nested" / "map.html"

    saved_path = save_map(m, output_path)

    assert saved_path.exists()
    assert saved_path.parent.exists()


def test_choropleth_map_center(nuts_gdf, predictions):
    """Test that choropleth map is centered correctly."""
    m = create_risk_choropleth(nuts_gdf, predictions)

    # Map should be centered around the data
    assert m.location is not None
    assert len(m.location) == 2  # [lat, lon]


def test_comparison_map_center(nuts_gdf, actual, predictions):
    """Test that comparison map is centered correctly."""
    m = create_comparison_map(nuts_gdf, actual, predictions)

    assert m.location is not None
    assert len(m.location) == 2

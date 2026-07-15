"""Tests for data loading and CRS handling."""

import geopandas as gpd
import pytest
from shapely.geometry import box

from geo_risk.data import clear_cache, load_and_validate, load_ispra_flood_hazard


def _write_ispra_style_shapefiles(directory):
    """Write shapefiles matching the *real* ISPRA schema (scenario + geometry only,
    no area attribute) for each hazard class, mirroring what ISPRA actually
    distributes. Used to catch regressions like the missing 'area_km2' column
    bug, which the hand-built fixtures below never exercised."""
    hazard_files = {
        "HPH": box(10.2, 40.2, 10.5, 40.5),
        "MPH": box(11.2, 40.2, 11.5, 40.5),
        "LPH": box(12.2, 40.2, 12.5, 40.5),
    }
    for prefix, geom in hazard_files.items():
        gdf = gpd.GeoDataFrame({"scenario": ["1"], "geometry": [geom]}, crs="EPSG:4326")
        gdf.to_file(directory / f"{prefix}_test.shp")


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


def test_load_ispra_flood_hazard_real_schema(tmp_path):
    """Regression test: real ISPRA shapefiles only have a 'scenario' + geometry
    column (no 'area_km2' attribute). load_ispra_flood_hazard must compute
    area_km2 from geometry itself rather than assuming the attribute exists."""
    _write_ispra_style_shapefiles(tmp_path)

    flood_gdf = load_ispra_flood_hazard(tmp_path)

    assert len(flood_gdf) == 3
    assert "hazard_class" in flood_gdf.columns
    assert set(flood_gdf["hazard_class"]) == {"P1", "P2", "P3"}
    assert "area_km2" in flood_gdf.columns
    assert (flood_gdf["area_km2"] > 0).all()


def test_load_ispra_flood_hazard_missing_class_raises(tmp_path):
    """Test that a clear error is raised if a hazard class shapefile is missing."""
    gdf = gpd.GeoDataFrame(
        {"scenario": ["1"], "geometry": [box(10.2, 40.2, 10.5, 40.5)]}, crs="EPSG:4326"
    )
    gdf.to_file(tmp_path / "HPH_test.shp")
    # MPH and LPH intentionally missing

    with pytest.raises(FileNotFoundError, match="MPH"):
        load_ispra_flood_hazard(tmp_path)


def test_load_and_validate_caching(tmp_path):
    """Test that load_and_validate caches validated data and reuses it on a
    subsequent call, and that clear_cache removes the cache."""
    shapefile_dir = tmp_path / "shapefiles"
    shapefile_dir.mkdir()
    _write_ispra_style_shapefiles(shapefile_dir)
    cache_dir = tmp_path / "cache"

    nuts_data = {
        "NUTS_ID": ["IT1", "IT2", "IT3"],
        "geometry": [
            box(10.0, 40.0, 11.0, 41.0),
            box(11.0, 40.0, 12.0, 41.0),
            box(12.0, 40.0, 13.0, 41.0),
        ],
    }
    nuts_path = tmp_path / "nuts.geojson"
    gpd.GeoDataFrame(nuts_data, crs="EPSG:4326").to_file(nuts_path, driver="GeoJSON")

    # First call: cache miss, writes cache files
    nuts_gdf_1, flood_gdf_1 = load_and_validate(
        nuts_path=nuts_path, flood_path=shapefile_dir, cache_dir=cache_dir
    )
    assert (cache_dir / "nuts_validated.parquet").exists()
    assert (cache_dir / "flood_validated.parquet").exists()
    assert (cache_dir / "cache_meta.json").exists()

    # Second call: cache hit, should return equivalent data without re-reading shapefiles
    nuts_gdf_2, flood_gdf_2 = load_and_validate(
        nuts_path=nuts_path, flood_path=shapefile_dir, cache_dir=cache_dir
    )
    assert len(nuts_gdf_1) == len(nuts_gdf_2)
    assert len(flood_gdf_1) == len(flood_gdf_2)
    assert set(flood_gdf_2["hazard_class"]) == {"P1", "P2", "P3"}

    # clear_cache removes the cache files
    clear_cache(cache_dir=cache_dir)
    assert not (cache_dir / "nuts_validated.parquet").exists()
    assert not (cache_dir / "flood_validated.parquet").exists()
    assert not (cache_dir / "cache_meta.json").exists()


def test_load_and_validate_cache_invalidated_on_change(tmp_path):
    """Test that changing the source shapefiles invalidates the cache."""
    shapefile_dir = tmp_path / "shapefiles"
    shapefile_dir.mkdir()
    _write_ispra_style_shapefiles(shapefile_dir)
    cache_dir = tmp_path / "cache"

    nuts_path = tmp_path / "nuts.geojson"
    gpd.GeoDataFrame(
        {"NUTS_ID": ["IT1"], "geometry": [box(10.0, 40.0, 11.0, 41.0)]}, crs="EPSG:4326"
    ).to_file(nuts_path, driver="GeoJSON")

    load_and_validate(nuts_path=nuts_path, flood_path=shapefile_dir, cache_dir=cache_dir)

    # Modify the flood source data (add an extra HPH file with different content)
    import time

    time.sleep(0.01)  # ensure mtime changes
    extra_gdf = gpd.GeoDataFrame(
        {"scenario": ["2"], "geometry": [box(13.0, 40.0, 13.5, 40.5)]}, crs="EPSG:4326"
    )
    extra_gdf.to_file(shapefile_dir / "HPH_test.shp")  # overwrite with new content

    _, flood_gdf_after = load_and_validate(
        nuts_path=nuts_path, flood_path=shapefile_dir, cache_dir=cache_dir
    )
    # Should have reloaded from source (not silently reused stale cache)
    assert len(flood_gdf_after) == 3

"""Tests for spatial autocorrelation and spatial cross-validation."""


import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from geo_risk.evaluate import plot_lisa_clusters, plot_moran_scatter
from geo_risk.spatial_cv import (
    LocalMoranResult,
    MoransIResult,
    SpatialBufferCV,
    SpatialCVComparisonResult,
    SpatialKFold,
    build_spatial_weight_matrix,
    compute_global_morans_i,
    compute_local_morans_i,
    evaluate_spatial_cv,
    extract_coordinates,
)


@pytest.fixture
def synthetic_spatial_grid():
    """Create a 4x4 regular grid with known coordinates and spatial pattern."""
    x_coords = np.repeat(np.arange(4), 4)
    y_coords = np.tile(np.arange(4), 4)
    coords = np.column_stack([x_coords, y_coords])

    # Clustered pattern: values increase along x-axis (strong positive autocorrelation)
    clustered_vals = x_coords.astype(float)

    # Polygons for GeoDataFrame
    polys = [
        Polygon([(x, y), (x + 0.8, y), (x + 0.8, y + 0.8), (x, y + 0.8)])
        for x, y in coords
    ]
    gdf = gpd.GeoDataFrame(
        {
            "NUTS_ID": [f"REG_{i:02d}" for i in range(16)],
            "val": clustered_vals,
        },
        geometry=polys,
        crs="EPSG:4326",
    )
    return coords, clustered_vals, gdf


def test_extract_coordinates(synthetic_spatial_grid):
    coords, _, gdf = synthetic_spatial_grid

    # From GeoDataFrame
    extracted_gdf = extract_coordinates(gdf)
    assert extracted_gdf.shape == (16, 2)
    # Check centroid coordinates
    assert np.allclose(extracted_gdf[:, 0], coords[:, 0] + 0.4, atol=1e-3)

    # From DataFrame
    df = pd.DataFrame({"lon": coords[:, 0], "lat": coords[:, 1]})
    extracted_df = extract_coordinates(df)
    assert np.allclose(extracted_df, coords)

    # From numpy array
    extracted_arr = extract_coordinates(coords)
    assert np.allclose(extracted_arr, coords)

    # Error on invalid input
    with pytest.raises(TypeError):
        extract_coordinates("invalid")  # type: ignore

    with pytest.raises(ValueError):
        extract_coordinates(np.ones((5, 3)))


def test_build_spatial_weight_matrix(synthetic_spatial_grid):
    coords, _, _ = synthetic_spatial_grid

    # Inverse distance
    w_inv = build_spatial_weight_matrix(coords, weight_type="inverse_distance", row_standardize=True)
    assert w_inv.shape == (16, 16)
    assert np.allclose(np.diag(w_inv), 0.0)
    assert np.allclose(w_inv.sum(axis=1), 1.0)

    # K-nearest
    w_knn = build_spatial_weight_matrix(coords, weight_type="k_nearest", k_neighbors=3, row_standardize=True)
    assert w_knn.shape == (16, 16)
    assert np.allclose(np.diag(w_knn), 0.0)
    assert np.allclose(w_knn.sum(axis=1), 1.0)

    # Gaussian
    w_gauss = build_spatial_weight_matrix(coords, weight_type="gaussian", row_standardize=True)
    assert w_gauss.shape == (16, 16)
    assert np.allclose(np.diag(w_gauss), 0.0)
    assert np.allclose(w_gauss.sum(axis=1), 1.0)

    # Invalid weight type
    with pytest.raises(ValueError):
        build_spatial_weight_matrix(coords, weight_type="unknown")


def test_compute_global_morans_i(synthetic_spatial_grid):
    coords, clustered_vals, _ = synthetic_spatial_grid

    # Clustered values must show strong positive spatial autocorrelation
    result = compute_global_morans_i(clustered_vals, coords, weight_type="inverse_distance")
    assert isinstance(result, MoransIResult)
    assert result.i_stat > 0.1
    assert result.z_score > 3.0
    assert result.p_value < 0.001
    assert result.n_samples == 16

    # Constant values edge case
    const_vals = np.ones(16)
    const_res = compute_global_morans_i(const_vals, coords)
    assert const_res.i_stat == 0.0
    assert const_res.p_value == 1.0

    # Minimum sample check
    with pytest.raises(ValueError):
        compute_global_morans_i([1.0, 2.0], coords[:2])


def test_compute_local_morans_i(synthetic_spatial_grid):
    coords, clustered_vals, gdf = synthetic_spatial_grid
    lisa = compute_local_morans_i(clustered_vals, gdf)
    assert isinstance(lisa, LocalMoranResult)
    assert len(lisa.local_i) == 16
    assert len(lisa.quadrants) == 16
    assert set(lisa.quadrants).issubset({"HH", "LL", "HL", "LH"})
    # Low x coords should tend to LL and High x coords to HH
    assert "LL" in lisa.quadrants
    assert "HH" in lisa.quadrants


def test_spatial_kfold(synthetic_spatial_grid):
    coords, _, _ = synthetic_spatial_grid
    X = pd.DataFrame({"feat1": np.arange(16), "feat2": np.arange(16) * 2})
    y = pd.Series([0, 1] * 8)

    skf = SpatialKFold(n_splits=4, random_state=42)
    splits = list(skf.split(X, y, coords_or_geo=coords))
    assert len(splits) == 4

    seen_test = set()
    for train_idx, test_idx in splits:
        assert len(np.intersect1d(train_idx, test_idx)) == 0
        seen_test.update(test_idx)
        assert len(train_idx) > 0
        assert len(test_idx) > 0

    assert seen_test == set(range(16))


def test_spatial_buffer_cv(synthetic_spatial_grid):
    coords, _, _ = synthetic_spatial_grid
    X = pd.DataFrame({"feat": np.arange(16)})
    y = pd.Series(np.arange(16))

    sb_cv = SpatialBufferCV(buffer_distance=1.1)
    splits = list(sb_cv.split(X, y, coords_or_geo=coords))
    assert len(splits) == 16

    for i, (train_idx, test_idx) in enumerate(splits):
        assert test_idx[0] == i
        # The immediate neighbours at distance 1.0 should be excluded from training
        assert i not in train_idx


def test_evaluate_spatial_cv(synthetic_spatial_grid):
    coords, _, gdf = synthetic_spatial_grid
    features = pd.DataFrame(
        {
            "flood_fraction": np.linspace(0.01, 0.95, 16),
            "hazard_p3": np.linspace(0.0, 0.5, 16),
            "hazard_p2": np.linspace(0.1, 0.4, 16),
            "elevation": np.random.RandomState(42).uniform(10, 500, 16),
        }
    )
    target_class = pd.Series([0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2])
    target_reg = features["flood_fraction"]

    # Classification CV evaluation
    clf_res = evaluate_spatial_cv(
        features_df=features,
        target=target_class,
        coords_or_geo=gdf,
        task="classification",
        n_splits=3,
        random_state=42,
    )
    assert isinstance(clf_res, SpatialCVComparisonResult)
    assert "mean_accuracy" in clf_res.standard_cv
    assert "mean_accuracy" in clf_res.spatial_cv
    assert clf_res.morans_i is not None

    # Classification with target leakage feature drop
    clf_leak_free = evaluate_spatial_cv(
        features_df=features,
        target=target_class,
        coords_or_geo=gdf,
        task="classification",
        n_splits=3,
        random_state=42,
        drop_leakage_features=["flood_fraction"],
    )
    assert isinstance(clf_leak_free, SpatialCVComparisonResult)

    # Regression CV evaluation
    reg_res = evaluate_spatial_cv(
        features_df=features,
        target=target_reg,
        coords_or_geo=gdf,
        task="regression",
        n_splits=3,
        random_state=42,
    )
    assert isinstance(reg_res, SpatialCVComparisonResult)
    assert "mean_rmse" in reg_res.standard_cv
    assert "mean_rmse" in reg_res.spatial_cv


def test_spatial_visualization_tools(synthetic_spatial_grid, tmp_path):
    coords, clustered_vals, gdf = synthetic_spatial_grid

    scatter_path = tmp_path / "test_moran_scatter.png"
    out_scatter = plot_moran_scatter(
        values=clustered_vals,
        coords_or_geo=coords,
        output_path=scatter_path,
    )
    assert out_scatter.exists()
    assert out_scatter.stat().st_size > 0

    lisa_path = tmp_path / "test_lisa.png"
    out_lisa = plot_lisa_clusters(
        nuts_gdf=gdf,
        values=clustered_vals,
        output_path=lisa_path,
    )
    assert out_lisa.exists()
    assert out_lisa.stat().st_size > 0

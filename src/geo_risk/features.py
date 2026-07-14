"""Feature engineering for geospatial flood risk prediction.

Performs spatial joins between NUTS regions and flood hazard areas,
extracts per-region features, and creates target labels.
"""

import logging

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

# Equal-area CRS used only for area computation (ETRS89-extended / LAEA Europe),
# consistent with the area calculation used for flood hazard polygons in data.py.
# Geometries are NOT stored in this CRS; it's used transiently for accurate km² areas.
_EQUAL_AREA_CRS = "EPSG:3035"


def engineer_features(
    nuts_gdf: gpd.GeoDataFrame,
    flood_gdf: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """Engineer features from spatial join of NUTS and flood hazard data.

    Computes per-region features:
    - flood_area_km2: Total flood hazard area in region
    - flood_fraction: Fraction of region covered by flood hazard
    - hazard_p3_fraction: Fraction covered by high-risk (P3) hazard
    - hazard_p2_fraction: Fraction covered by medium-risk (P2) hazard
    - region_area_km2: Total region area

    Target: flood_risk_class (0=low, 1=medium, 2=high) based on flood_fraction.

    Args:
        nuts_gdf: GeoDataFrame with NUTS regions.
        flood_gdf: GeoDataFrame with flood hazard areas.

    Returns:
        Tuple of (features_df, target_series) with aligned indices.

    Raises:
        ValueError: If spatial join fails or data is invalid.
    """
    if nuts_gdf.crs != flood_gdf.crs:
        raise ValueError(f"CRS mismatch: {nuts_gdf.crs} != {flood_gdf.crs}")

    # Region area in km², computed via an equal-area projection for accuracy
    # (a naive degrees-to-km conversion is latitude-dependent and was previously
    # a rough approximation here).
    region_area_km2 = (
        nuts_gdf.set_index("NUTS_ID").geometry.to_crs(_EQUAL_AREA_CRS).area / 1e6
    ).rename("region_area_km2")

    # Spatial join: find flood areas within each NUTS region
    logger.info(
        f"Performing spatial join ({len(nuts_gdf)} regions x {len(flood_gdf)} hazard polygons)"
    )
    joined = gpd.sjoin(
        nuts_gdf[["NUTS_ID", "geometry"]],
        flood_gdf[["hazard_class", "area_km2", "geometry"]],
        how="left",
        predicate="intersects",
    )
    logger.info(f"Spatial join produced {len(joined)} matched rows")

    # Aggregate flood area per region (vectorized groupby, not a per-region Python loop)
    logger.info("Aggregating flood exposure per region (groupby)")
    total_flood_area = joined.groupby("NUTS_ID")["area_km2"].sum().rename("flood_area_km2")
    p3_area = (
        joined[joined["hazard_class"] == "P3"]
        .groupby("NUTS_ID")["area_km2"]
        .sum()
        .rename("p3_area_km2")
    )
    p2_area = (
        joined[joined["hazard_class"] == "P2"]
        .groupby("NUTS_ID")["area_km2"]
        .sum()
        .rename("p2_area_km2")
    )

    # Combine into a single features frame, filling regions with no matches as 0
    features_df = pd.concat([region_area_km2, total_flood_area, p3_area, p2_area], axis=1)
    features_df[["flood_area_km2", "p3_area_km2", "p2_area_km2"]] = features_df[
        ["flood_area_km2", "p3_area_km2", "p2_area_km2"]
    ].fillna(0.0)

    features_df["flood_fraction"] = (
        features_df["flood_area_km2"] / features_df["region_area_km2"]
    ).clip(upper=1.0)
    features_df["hazard_p3_fraction"] = (
        features_df["p3_area_km2"] / features_df["region_area_km2"]
    ).clip(upper=1.0)
    features_df["hazard_p2_fraction"] = (
        features_df["p2_area_km2"] / features_df["region_area_km2"]
    ).clip(upper=1.0)

    features_df = features_df[
        [
            "flood_area_km2",
            "flood_fraction",
            "hazard_p3_fraction",
            "hazard_p2_fraction",
            "region_area_km2",
        ]
    ]
    features_df.index.name = "NUTS_ID"

    # Create target: flood risk class based on flood_fraction
    # 0 = low (< 5%), 1 = medium (5-15%), 2 = high (> 15%)
    target = pd.Series(
        index=features_df.index,
        dtype="int64",
        name="flood_risk_class",
    )
    target.loc[features_df["flood_fraction"] < 0.05] = 0
    target.loc[(features_df["flood_fraction"] >= 0.05) & (features_df["flood_fraction"] < 0.15)] = 1
    target.loc[features_df["flood_fraction"] >= 0.15] = 2
    target = target.astype(int)

    logger.info(
        f"Engineered {len(features_df)} regions; "
        f"target distribution: {target.value_counts().to_dict()}"
    )

    return features_df, target


def add_spatial_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """Add additional spatial features (optional).

    Args:
        features_df: DataFrame with base features.

    Returns:
        DataFrame with additional engineered features.
    """
    df = features_df.copy()

    # Interaction features
    df["p3_p2_ratio"] = df["hazard_p3_fraction"] / (df["hazard_p2_fraction"] + 1e-6)
    df["high_hazard_indicator"] = (df["hazard_p3_fraction"] > 0.05).astype(int)

    return df

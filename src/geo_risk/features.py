"""Feature engineering for geospatial flood risk prediction.

Performs spatial joins between NUTS regions and flood hazard areas,
extracts per-region features, and creates target labels.
"""

import logging

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)


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

    # Spatial join: find flood areas within each NUTS region
    logger.info("Performing spatial join (NUTS intersect flood hazard)")
    joined = gpd.sjoin(
        nuts_gdf[["NUTS_ID", "geometry"]],
        flood_gdf[["hazard_class", "area_km2", "geometry"]],
        how="left",
        predicate="intersects",
    )

    # Aggregate flood features per NUTS region
    features_list = []
    for nuts_id in nuts_gdf["NUTS_ID"]:
        region_data = joined[joined["NUTS_ID"] == nuts_id]
        region_geom = nuts_gdf[nuts_gdf["NUTS_ID"] == nuts_id].geometry.iloc[0]

        # Calculate region area in km²
        # Use simple area approximation (degrees to km at equator ~111 km/degree)
        region_area_km2 = region_geom.area * 111 * 111  # Rough approximation

        if len(region_data) == 0:
            # No flood hazard in region
            flood_area_km2 = 0.0
            flood_fraction = 0.0
            hazard_p3_fraction = 0.0
            hazard_p2_fraction = 0.0
        else:
            # Sum flood areas
            flood_area_km2 = region_data["area_km2"].sum()
            flood_fraction = min(flood_area_km2 / region_area_km2, 1.0)

            # Fraction by hazard class
            p3_area = region_data[region_data["hazard_class"] == "P3"]["area_km2"].sum()
            p2_area = region_data[region_data["hazard_class"] == "P2"]["area_km2"].sum()
            hazard_p3_fraction = min(p3_area / region_area_km2, 1.0)
            hazard_p2_fraction = min(p2_area / region_area_km2, 1.0)

        features_list.append(
            {
                "NUTS_ID": nuts_id,
                "flood_area_km2": flood_area_km2,
                "flood_fraction": flood_fraction,
                "hazard_p3_fraction": hazard_p3_fraction,
                "hazard_p2_fraction": hazard_p2_fraction,
                "region_area_km2": region_area_km2,
            }
        )

    features_df = pd.DataFrame(features_list)
    features_df.set_index("NUTS_ID", inplace=True)

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

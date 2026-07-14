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
    - flood_area_km2: Total flood hazard area in region (union of clipped
      P1/P2/P3 polygons, so overlapping hazard classes are not double-counted)
    - flood_fraction: Fraction of region covered by flood hazard
    - hazard_p3_fraction: Fraction covered by high-risk (P3) hazard
    - hazard_p2_fraction: Fraction covered by medium-risk (P2) hazard
    - region_area_km2: Total region area

    Target: flood_risk_class (0=low, 1=medium, 2=high), assigned via tertile
    (quantile) binning of flood_fraction so classes stay roughly balanced
    regardless of the underlying exposure distribution — see notes below.

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

    # Spatial join: find flood polygons that intersect each NUTS region.
    # NOTE: "intersects" only tells us a flood polygon touches the region at
    # all — ISPRA hazard polygons follow rivers/coastlines and routinely span
    # multiple regions, so a large polygon can intersect a small region while
    # extending far outside it. Summing each matched polygon's *whole* area
    # (as a naive sjoin+groupby would) massively overcounts exposure — we saw
    # flood_area_km2 exceed region_area_km2 by 10x for most regions. We must
    # clip each matched flood polygon to the region and use the *intersected*
    # area instead.
    logger.info(
        f"Performing spatial join ({len(nuts_gdf)} regions x {len(flood_gdf)} hazard polygons)"
    )
    flood_cols = flood_gdf[["hazard_class", "geometry"]].copy()
    flood_cols["flood_geometry"] = flood_cols.geometry  # carried through as a plain column
    joined = gpd.sjoin(
        nuts_gdf[["NUTS_ID", "geometry"]],
        flood_cols[["hazard_class", "flood_geometry", "geometry"]],
        how="left",
        predicate="intersects",
    )
    logger.info(f"Spatial join produced {len(joined)} candidate matched rows")

    matched = joined[joined["flood_geometry"].notna()].copy()
    logger.info(f"Clipping {len(matched)} matched flood polygons to their region geometry")
    region_geom = gpd.GeoSeries(matched.geometry.to_numpy(), crs=matched.crs)
    flood_geom = gpd.GeoSeries(matched["flood_geometry"].to_numpy(), crs=matched.crs)
    intersection = region_geom.intersection(flood_geom)

    # Build a GeoDataFrame of the clipped pieces and union them per region.
    # The per-class P3/P2 areas are taken as the *sum* of clipped areas for
    # that class (ISPRA mosaics are non-overlapping within a class), while the
    # total flood area is the union of all three classes to avoid double
    # counting where P1/P2/P3 overlap.
    matched["inter_area_km2"] = (
        intersection.to_crs(_EQUAL_AREA_CRS).area / 1e6
    ).to_numpy()

    clipped = gpd.GeoDataFrame(
        {"NUTS_ID": matched["NUTS_ID"].to_numpy(), "hazard_class": matched["hazard_class"].to_numpy()},
        geometry=intersection,
        crs=matched.crs,
    )
    # Drop empty touches/lines and make invalid geometries valid before unioning.
    clipped = clipped[~clipped.geometry.is_empty].copy()
    if not clipped.geometry.is_valid.all():
        clipped.geometry = clipped.geometry.buffer(0)

    logger.info("Unioning clipped hazard polygons per region")
    total_union = clipped.dissolve(by="NUTS_ID")
    total_union["area_km2"] = total_union.geometry.to_crs(_EQUAL_AREA_CRS).area / 1e6

    total_flood_area = total_union["area_km2"].rename("flood_area_km2")
    p3_area = (
        matched[matched["hazard_class"] == "P3"]
        .groupby("NUTS_ID")["inter_area_km2"]
        .sum()
        .rename("p3_area_km2")
    )
    p2_area = (
        matched[matched["hazard_class"] == "P2"]
        .groupby("NUTS_ID")["inter_area_km2"]
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

    # Create target: flood risk class based on flood_fraction.
    #
    # Uses quantile-based (tertile) binning rather than fixed absolute cutoffs
    # (e.g. <5%/5-15%/>15%). Fixed cutoffs picked without seeing the real data
    # produced a severely imbalanced target against actual ISPRA national
    # hazard-mosaic exposure (which covers a substantial fraction of nearly
    # every Italian NUTS 2 region) — 20 of 21 regions landed in a single
    # class, which also breaks stratified train/test splitting downstream.
    # Tertiles guarantee a roughly balanced 3-class target regardless of the
    # underlying distribution, at the cost of the class boundaries being
    # relative (this dataset) rather than fixed absolute thresholds.
    target = pd.qcut(
        features_df["flood_fraction"], q=3, labels=[0, 1, 2], duplicates="drop"
    ).astype(int)
    target.name = "flood_risk_class"

    logger.info(
        f"Engineered {len(features_df)} regions; "
        f"target distribution: {target.value_counts().to_dict()}"
    )

    return features_df, target


def add_spatial_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """Add derived interaction features from the base hazard fractions.

    Computes:
    - p3_p2_ratio: hazard_p3_fraction / (hazard_p2_fraction + 1e-6)
    - high_hazard_indicator: 1 if hazard_p3_fraction > 0.05 else 0

    Args:
        features_df: DataFrame with base features.

    Returns:
        DataFrame with the additional engineered columns above.
    """
    df = features_df.copy()

    # Interaction features
    df["p3_p2_ratio"] = df["hazard_p3_fraction"] / (df["hazard_p2_fraction"] + 1e-6)
    df["high_hazard_indicator"] = (df["hazard_p3_fraction"] > 0.05).astype(int)

    return df

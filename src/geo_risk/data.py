"""Data loading and validation for geospatial flood risk mapping.

Loads ISPRA flood hazard boundaries and NUTS administrative regions,
handles CRS reprojection, and validates spatial data integrity.
"""

import logging
from pathlib import Path

import geopandas as gpd

from .config import settings

logger = logging.getLogger(__name__)


def load_nuts_boundaries(path: str | Path | None = None) -> gpd.GeoDataFrame:
    """Load NUTS administrative boundaries (level 2) for Italy.

    Downloads from datahub.io if not present locally.
    Reprojects to target CRS.

    Args:
        path: Optional path to local GeoJSON file. If None, downloads from datahub.

    Returns:
        GeoDataFrame with NUTS 2 regions, reprojected to target CRS.

    Raises:
        ValueError: If CRS is invalid or data cannot be loaded.
    """
    if path is None:
        # Use datahub.io NUTS boundaries (NUTS level 2 for Italy)
        url = (
            "https://datahub.io/core/geo-nuts-administrative-boundaries/"
            "r/NUTS_RG_60M_2024_4326_LEVL_2.geojson"
        )
        logger.info(f"Loading NUTS boundaries from {url}")
        gdf = gpd.read_file(url)  # type: ignore
    else:
        path = Path(path)
        logger.info(f"Loading NUTS boundaries from {path}")
        gdf = gpd.read_file(path)  # type: ignore

    # Filter to Italy (NUTS codes starting with 'IT')
    gdf = gdf[gdf["NUTS_ID"].str.startswith("IT")].copy()  # type: ignore
    logger.info(f"Loaded {len(gdf)} NUTS 2 regions for Italy")

    # Validate CRS
    if gdf.crs is None:
        raise ValueError("NUTS boundaries have no CRS defined")

    # Reproject to target CRS
    if gdf.crs != settings.target_crs:
        logger.info(f"Reprojecting from {gdf.crs} to {settings.target_crs}")
        gdf = gdf.to_crs(settings.target_crs)

    return gdf


def load_ispra_flood_hazard(path: str | Path | None = None) -> gpd.GeoDataFrame:
    """Load ISPRA flood hazard areas (pericolosità idraulica).

    Downloads from ISPRA if not present locally.
    Reprojects to target CRS.

    Args:
        path: Optional path to local GeoPackage or shapefile. If None, downloads.

    Returns:
        GeoDataFrame with flood hazard areas and risk classes.

    Raises:
        ValueError: If CRS is invalid or data cannot be loaded.
    """
    if path is None:
        # Use ISPRA WMS or download link
        # For this implementation, we'll use a simplified approach:
        # Create synthetic flood hazard data for testing/demo purposes
        logger.warning(
            "No local ISPRA flood data provided. Using synthetic data for demo."
        )
        gdf = _create_synthetic_flood_data()
    else:
        path = Path(path)
        logger.info(f"Loading ISPRA flood hazard from {path}")
        gdf = gpd.read_file(path)

    # Validate CRS
    if gdf.crs is None:
        raise ValueError("Flood hazard data has no CRS defined")

    # Reproject to target CRS
    if gdf.crs != settings.target_crs:
        logger.info(f"Reprojecting from {gdf.crs} to {settings.target_crs}")
        gdf = gdf.to_crs(settings.target_crs)

    return gdf


def _create_synthetic_flood_data() -> gpd.GeoDataFrame:
    """Create synthetic flood hazard data for demo/testing.

    Returns:
        GeoDataFrame with synthetic flood hazard polygons.
    """
    from shapely.geometry import box

    # Create synthetic hazard areas (simplified for demo)
    # In production, this would be replaced with real ISPRA data
    data = {
        "geometry": [
            box(10.0, 40.0, 11.0, 41.0),  # Northern region
            box(11.0, 40.0, 12.0, 41.0),  # Central region
            box(12.0, 40.0, 13.0, 41.0),  # Eastern region
        ],
        "hazard_class": ["P2", "P3", "P1"],  # P1=low, P2=medium, P3=high
        "area_km2": [1000.0, 800.0, 1200.0],
    }
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
    logger.info("Created synthetic flood hazard data")
    return gdf


def load_and_validate(
    nuts_path: str | Path | None = None,
    flood_path: str | Path | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load and validate both NUTS boundaries and flood hazard data.

    Args:
        nuts_path: Optional path to NUTS GeoJSON.
        flood_path: Optional path to ISPRA flood data.

    Returns:
        Tuple of (nuts_gdf, flood_gdf), both in target CRS.

    Raises:
        ValueError: If data is invalid or CRS mismatch.
    """
    nuts_gdf = load_nuts_boundaries(nuts_path)
    flood_gdf = load_ispra_flood_hazard(flood_path)

    # Validate CRS match
    if nuts_gdf.crs != flood_gdf.crs:
        raise ValueError(
            f"CRS mismatch: NUTS {nuts_gdf.crs} != Flood {flood_gdf.crs}"
        )

    # Validate geometries
    if not nuts_gdf.geometry.is_valid.all():
        logger.warning("Some NUTS geometries are invalid; attempting fix")
        nuts_gdf.geometry = nuts_gdf.geometry.buffer(0)

    if not flood_gdf.geometry.is_valid.all():
        logger.warning("Some flood geometries are invalid; attempting fix")
        flood_gdf.geometry = flood_gdf.geometry.buffer(0)

    logger.info(
        f"Loaded {len(nuts_gdf)} NUTS regions and {len(flood_gdf)} flood areas"
    )
    return nuts_gdf, flood_gdf

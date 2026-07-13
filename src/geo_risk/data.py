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

    Requires manual download from ISPRA (no automatic download).
    Reprojects to target CRS.

    Args:
        path: Path to local GeoPackage or shapefile with ISPRA flood data.
              Required — no automatic download available.

    Returns:
        GeoDataFrame with flood hazard areas and risk classes.

    Raises:
        FileNotFoundError: If path not provided or file not found.
        ValueError: If CRS is invalid or data cannot be loaded.
    """
    if path is None:
        raise FileNotFoundError(
            "ISPRA flood hazard data must be manually downloaded and provided.\n"
            "Download instructions:\n"
            "1. Visit IdroGEO (official ISPRA platform):\n"
            "   https://idrogeo.isprambiente.it/app/page/open-data\n"
            "2. Or use Italian Geoportal:\n"
            "   https://geodati.gov.it/ (search 'pericolosità idraulica')\n"
            "3. Download as GeoPackage (.gpkg) or Shapefile\n"
            "4. Pass path to load_ispra_flood_hazard(path='path/to/file.gpkg')\n"
            "\nFor WMS access (advanced):\n"
            "https://www.isprambiente.gov.it/en/geospatial-data-and-maps"
        )

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ISPRA flood data file not found: {path}")

    logger.info(f"Loading ISPRA flood hazard from {path}")
    gdf = gpd.read_file(path)  # type: ignore

    # Validate CRS
    if gdf.crs is None:
        raise ValueError("Flood hazard data has no CRS defined")

    # Reproject to target CRS
    if gdf.crs != settings.target_crs:
        logger.info(f"Reprojecting from {gdf.crs} to {settings.target_crs}")
        gdf = gdf.to_crs(settings.target_crs)

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

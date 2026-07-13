"""Data loading and validation for geospatial flood risk mapping.

Loads ISPRA flood hazard boundaries and NUTS administrative regions,
handles CRS reprojection, and validates spatial data integrity.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

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

    Loads all three hazard classes (P1, P2, P3) from ISPRA shapefiles.
    ISPRA provides separate shapefiles for each hazard class:
    - HPH: High hazard (P3 - pericolosità elevata)
    - MPH: Medium hazard (P2 - pericolosità media)
    - LPH: Low hazard (P1 - pericolosità bassa)

    Requires manual download from ISPRA (no automatic download).
    Reprojects to target CRS.

    Args:
        path: Path to directory containing ISPRA shapefiles.
              Must contain HPH_*.shp, MPH_*.shp, and LPH_*.shp files.
              Required — no automatic download available.

    Returns:
        GeoDataFrame with all flood hazard areas and risk classes (P1, P2, P3).

    Raises:
        FileNotFoundError: If path not provided or required shapefiles not found.
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
            "3. Download the complete Shapefile package (contains 3 hazard classes)\n"
            "4. Extract all files to a directory\n"
            "5. Pass directory path to load_ispra_flood_hazard():\n"
            "   load_ispra_flood_hazard(path='path/to/shapefile_directory')\n"
            "\nExpected files in directory:\n"
            "- HPH_*.shp (High hazard - P3)\n"
            "- MPH_*.shp (Medium hazard - P2)\n"
            "- LPH_*.shp (Low hazard - P1)\n"
            "Plus associated .shx, .dbf, .prj files for each.\n"
            "\nFor WMS access (advanced):\n"
            "https://www.isprambiente.gov.it/en/geospatial-data-and-maps"
        )

    path = Path(path)
    
    if not path.is_dir():
        raise ValueError(
            f"Path must be a directory containing ISPRA shapefiles: {path}"
        )

    # Find shapefiles for each hazard class
    hazard_classes = {
        "P3": ("HPH", "High hazard (pericolosità elevata)"),
        "P2": ("MPH", "Medium hazard (pericolosità media)"),
        "P1": ("LPH", "Low hazard (pericolosità bassa)"),
    }

    gdfs = []
    for hazard_class, (prefix, description) in hazard_classes.items():
        shp_files = list(path.glob(f"{prefix}_*.shp"))
        if not shp_files:
            raise FileNotFoundError(
                f"No shapefile found for {description} ({prefix}_*.shp) in {path}"
            )
        if len(shp_files) > 1:
            logger.warning(
                f"Multiple {prefix} shapefiles found. Using: {shp_files[0]}"
            )

        shp_path = shp_files[0]
        logger.info(f"Loading {description} from {shp_path}")
        gdf = gpd.read_file(shp_path)  # type: ignore

        # Validate CRS
        if gdf.crs is None:
            raise ValueError(f"{description} shapefile has no CRS defined")

        # Add hazard class column
        gdf["hazard_class"] = hazard_class

        # Reproject to target CRS
        if gdf.crs != settings.target_crs:
            logger.info(f"Reprojecting {description} to {settings.target_crs}")
            gdf = gdf.to_crs(settings.target_crs)

        gdfs.append(gdf)

    # Combine all hazard classes
    combined_gdf = pd.concat(gdfs, ignore_index=True)
    logger.info(
        f"Loaded {len(combined_gdf)} flood hazard polygons "
        f"(P3: {len(gdfs[0])}, P2: {len(gdfs[1])}, P1: {len(gdfs[2])})"
    )

    return combined_gdf


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

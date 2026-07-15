"""Data loading and validation for geospatial flood risk mapping.

Loads ISPRA flood hazard boundaries and NUTS administrative regions,
handles CRS reprojection, and validates spatial data integrity.
"""

import hashlib
import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import settings

logger = logging.getLogger(__name__)

# Equal-area CRS used only for area computation (ETRS89-extended / LAEA Europe).
# Chosen because it gives accurate km² areas for Italy/Europe; geometries are
# NOT stored in this CRS, it's used transiently to compute area_km2.
_EQUAL_AREA_CRS = "EPSG:3035"

# Cache of validated GeoDataFrames, so a downstream failure (e.g. in feature
# engineering or training) doesn't force re-reading/re-validating large
# shapefiles from scratch. See load_and_validate(use_cache=...).
_CACHE_SUBDIR = "processed"
_NUTS_CACHE_NAME = "nuts_validated.parquet"
_FLOOD_CACHE_NAME = "flood_validated.parquet"
_CACHE_META_NAME = "cache_meta.json"


def _area_km2(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Compute per-geometry area in km² using an equal-area projection.

    Does not mutate or reproject the input GeoDataFrame; the equal-area
    projection is only used transiently for an accurate area calculation.

    Args:
        gdf: GeoDataFrame with a valid CRS.

    Returns:
        Series of areas in km², aligned to gdf's index.
    """
    return gdf.geometry.to_crs(_EQUAL_AREA_CRS).area / 1e6


def _fingerprint_dir(path: Path, patterns: tuple[str, ...]) -> str:
    """Compute a cheap content fingerprint for files matching patterns in a directory.

    Used to detect when cached data is stale (e.g. flood_path points at
    different/updated files) without re-reading the (large) files themselves.

    Args:
        path: Directory to fingerprint.
        patterns: Glob patterns to include (e.g. ("*.shp", "*.dbf")).

    Returns:
        Hex digest summarizing file names, sizes, and modification times.
    """
    entries = []
    for pattern in patterns:
        for f in sorted(path.glob(pattern)):
            stat = f.stat()
            entries.append(f"{f.name}:{stat.st_size}:{stat.st_mtime}")
    digest = hashlib.sha256("|".join(entries).encode()).hexdigest()
    return digest


def _cache_dir(cache_dir: str | Path | None) -> Path:
    resolved = Path(cache_dir) if cache_dir is not None else Path(settings.data_dir) / _CACHE_SUBDIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def clear_cache(cache_dir: str | Path | None = None) -> None:
    """Delete cached validated GeoDataFrames, forcing a fresh reload next time.

    Args:
        cache_dir: Directory containing cache files. Defaults to
            {settings.data_dir}/processed.
    """
    resolved = _cache_dir(cache_dir)
    removed = []
    for name in (_NUTS_CACHE_NAME, _FLOOD_CACHE_NAME, _CACHE_META_NAME):
        f = resolved / name
        if f.exists():
            f.unlink()
            removed.append(f.name)
    if removed:
        print(f"Removed cache files: {', '.join(removed)}")
    else:
        print("No cache files found; nothing to remove.")


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
        raise ValueError(f"Path must be a directory containing ISPRA shapefiles: {path}")

    # Find shapefiles for each hazard class
    hazard_classes = {
        "P3": ("HPH", "High hazard (pericolosità elevata)"),
        "P2": ("MPH", "Medium hazard (pericolosità media)"),
        "P1": ("LPH", "Low hazard (pericolosità bassa)"),
    }

    gdfs = []
    for i, (hazard_class, (prefix, description)) in enumerate(hazard_classes.items(), start=1):
        shp_files = list(path.glob(f"{prefix}_*.shp"))
        if not shp_files:
            raise FileNotFoundError(
                f"No shapefile found for {description} ({prefix}_*.shp) in {path}"
            )
        if len(shp_files) > 1:
            logger.warning(f"Multiple {prefix} shapefiles found. Using: {shp_files[0]}")

        shp_path = shp_files[0]
        size_mb = shp_path.stat().st_size / (1024 * 1024)
        print(
            f"        ({i}/3) Reading {prefix} shapefile [{description}] ({size_mb:.0f} MB)...",
            end=" ",
            flush=True,
        )
        logger.info(f"Loading {description} from {shp_path} ({size_mb:.0f} MB)")
        gdf = gpd.read_file(shp_path)  # type: ignore
        print(f"done ({len(gdf)} polygons)")

        # Validate CRS
        if gdf.crs is None:
            raise ValueError(f"{description} shapefile has no CRS defined")

        # Add hazard class column
        gdf["hazard_class"] = hazard_class

        # ISPRA shapefiles do not include a usable area attribute (real files
        # only carry a 'scenario' column + geometry) — compute area ourselves
        # from geometry using an equal-area projection rather than assuming
        # an 'area_km2' column exists.
        if "area_km2" not in gdf.columns:
            print("            Computing area from geometry...", end=" ", flush=True)
            gdf["area_km2"] = _area_km2(gdf)
            print("done")

        # Reproject to target CRS
        if gdf.crs != settings.target_crs:
            print(f"            Reprojecting to {settings.target_crs}...", end=" ", flush=True)
            logger.info(f"Reprojecting {description} to {settings.target_crs}")
            gdf = gdf.to_crs(settings.target_crs)
            print("done")

        gdfs.append(gdf)

    # Combine all hazard classes
    print("        Combining hazard classes...", end=" ", flush=True)
    combined_gdf = pd.concat(gdfs, ignore_index=True)
    print("done")
    logger.info(
        f"Loaded {len(combined_gdf)} flood hazard polygons "
        f"(P3: {len(gdfs[0])}, P2: {len(gdfs[1])}, P1: {len(gdfs[2])})"
    )

    return combined_gdf


def load_and_validate(
    nuts_path: str | Path | None = None,
    flood_path: str | Path | None = None,
    use_cache: bool = True,
    cache_dir: str | Path | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load and validate both NUTS boundaries and flood hazard data.

    Caches the validated result to GeoParquet so that a failure in a later
    pipeline stage (feature engineering, training) doesn't force re-reading
    and re-validating large ISPRA shapefiles from scratch. The cache is
    automatically invalidated if the source files change (by size/mtime).

    Args:
        nuts_path: Optional path to NUTS GeoJSON.
        flood_path: Optional path to ISPRA flood data.
        use_cache: If True (default), reuse a cached validated result when
            available and the source files haven't changed. Set False to
            force a full reload.
        cache_dir: Directory for cache files. Defaults to
            {settings.data_dir}/processed.

    Returns:
        Tuple of (nuts_gdf, flood_gdf), both in target CRS.

    Raises:
        ValueError: If data is invalid or CRS mismatch.
    """
    resolved_cache_dir = _cache_dir(cache_dir)
    nuts_cache_path = resolved_cache_dir / _NUTS_CACHE_NAME
    flood_cache_path = resolved_cache_dir / _FLOOD_CACHE_NAME
    meta_path = resolved_cache_dir / _CACHE_META_NAME

    nuts_fingerprint = (
        str(Path(nuts_path).resolve()) if nuts_path is not None else "remote:datahub.io"
    )
    flood_fingerprint = (
        _fingerprint_dir(Path(flood_path), ("*.shp", "*.dbf", "*.shx", "*.prj"))
        if flood_path is not None
        else None
    )

    if use_cache and nuts_cache_path.exists() and flood_cache_path.exists() and meta_path.exists():
        try:
            cached_meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            cached_meta = {}
        cache_matches = (
            cached_meta.get("nuts_fingerprint") == nuts_fingerprint
            and cached_meta.get("flood_fingerprint") == flood_fingerprint
        )
        if cache_matches:
            print(
                "        Cache hit — loading validated data from "
                f"{resolved_cache_dir}/ (skipping shapefile read + validation)...",
                end=" ",
                flush=True,
            )
            nuts_gdf = gpd.read_parquet(nuts_cache_path)
            flood_gdf = gpd.read_parquet(flood_cache_path)
            print(f"done ({len(nuts_gdf)} regions, {len(flood_gdf)} hazard polygons)")
            logger.info("Loaded validated NUTS and flood data from cache")
            return nuts_gdf, flood_gdf
        else:
            print("        Cache found but source data has changed — reloading from source.")

    nuts_gdf = load_nuts_boundaries(nuts_path)
    flood_gdf = load_ispra_flood_hazard(flood_path)

    # Validate CRS match
    if nuts_gdf.crs != flood_gdf.crs:
        raise ValueError(f"CRS mismatch: NUTS {nuts_gdf.crs} != Flood {flood_gdf.crs}")

    # Validate geometries
    print("        Validating NUTS geometries...", end=" ", flush=True)
    nuts_valid = nuts_gdf.geometry.is_valid
    print("done")
    if not nuts_valid.all():
        n_invalid = int((~nuts_valid).sum())
        print(
            f"        Fixing {n_invalid} invalid NUTS geometries (buffer(0))...",
            end=" ",
            flush=True,
        )
        logger.warning(f"{n_invalid} NUTS geometries are invalid; attempting fix")
        nuts_gdf.geometry = nuts_gdf.geometry.buffer(0)
        print("done")

    print(
        f"        Validating {len(flood_gdf)} flood geometries "
        "(this can take a while for large national mosaics)...",
        end=" ",
        flush=True,
    )
    flood_valid = flood_gdf.geometry.is_valid
    print("done")
    if not flood_valid.all():
        n_invalid = int((~flood_valid).sum())
        print(
            f"        Fixing {n_invalid} invalid flood geometries (buffer(0))...",
            end=" ",
            flush=True,
        )
        logger.warning(f"{n_invalid} flood geometries are invalid; attempting fix")
        flood_gdf.geometry = flood_gdf.geometry.buffer(0)
        print("done")

    logger.info(f"Loaded {len(nuts_gdf)} NUTS regions and {len(flood_gdf)} flood areas")

    if use_cache:
        print(
            f"        Caching validated data to {resolved_cache_dir}/ for faster re-runs...",
            end=" ",
            flush=True,
        )
        nuts_gdf.to_parquet(nuts_cache_path)
        flood_gdf.to_parquet(flood_cache_path)
        meta_path.write_text(
            json.dumps(
                {"nuts_fingerprint": nuts_fingerprint, "flood_fingerprint": flood_fingerprint}
            )
        )
        print("done")

    return nuts_gdf, flood_gdf

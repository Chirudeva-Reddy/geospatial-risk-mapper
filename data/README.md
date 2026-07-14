# Data Documentation

## Overview

This directory contains raw geospatial data for the flood risk prediction project. **Raw data files are not committed** to the repository — they are downloaded on-demand by the data loading pipeline.

## Data Sources

### 1. NUTS Administrative Boundaries (Italy)

**Source**: Eurostat GISCO (Geographic Information System of the Commission)

- **Dataset**: NUTS 2 regions (Nomenclature of Territorial Units for Statistics, Level 2)
- **Format**: GeoJSON
- **CRS**: EPSG:4326 (WGS84)
- **Coverage**: Italy (21 NUTS 2 regions)
- **License**: CC-BY (Creative Commons Attribution)
- **URL**: https://datahub.io/core/geo-nuts-administrative-boundaries/
- **File**: `NUTS_RG_60M_2024_4326_LEVL_2.geojson` (downloaded on-demand)

**Attributes**:
- `NUTS_ID`: NUTS code (e.g., "ITH1" for Piemonte)
- `NUTS_NAME`: Region name
- `geometry`: Polygon boundary

### 2. ISPRA Flood Hazard Areas

**Source**: ISPRA (Istituto Superiore per la Protezione e la Ricerca Ambientale) / Italian Ministry of Environment

- **Dataset**: Aree a pericolosità idraulica (Flood Hazard Areas)
- **Format**: Shapefile (see "ISPRA Flood Data" section above — one shapefile per hazard class)
- **CRS**: Native shapefile CRS (typically EPSG:4326 or EPSG:32632/33); reprojected automatically
- **Coverage**: Italy (national mosaic)
- **License**: CC BY-SA 4.0 IT (Creative Commons Attribution-ShareAlike)
- **Download**: https://idrogeo.isprambiente.it/app/page/open-data
- **Reference**: D.Lgs. 49/2010 (Flood Directive implementation)

**Hazard Classes**:
- **P1**: Scarsa probabilità (Low probability) — return period > 200 years
- **P2**: Media probabilità (Medium probability) — return period 100-200 years
- **P3**: Elevata probabilità (High probability) — return period 20-50 years

**Raw attributes (as distributed by ISPRA)**:
- `scenario`: Hazard scenario code (the *only* attribute column in the real shapefiles)
- `geometry`: Polygon boundary

**Derived attributes (computed by `geo_risk.data.load_ispra_flood_hazard`)**:
- `hazard_class`: P1, P2, or P3 — inferred from which shapefile (LPH/MPH/HPH) a
  polygon came from, since ISPRA does not encode this in a shared attribute.
- `area_km2`: Area of hazard zone in km² — computed from geometry via an
  equal-area projection (EPSG:3035), since ISPRA does not provide a
  pre-computed area attribute. **Do not assume `area_km2` exists as a raw
  column if you inspect the shapefiles directly** — it's derived, not native.

## Coordinate Reference System (CRS)

All data is reprojected to **EPSG:4326 (WGS84)** for consistency:
- Latitude/Longitude (degrees)
- Global standard for web mapping
- Suitable for folium and Streamlit visualization

**Note**: ISPRA data may be distributed in EPSG:3857 (Web Mercator) or local Italian projections (e.g., EPSG:3003 Gauss-Boaga). The data loading pipeline (`data.py`) automatically reprojects to EPSG:4326.

## Data Download

### NUTS Boundaries (Automatic)

NUTS boundaries are downloaded automatically from Eurostat GISCO:

```python
from geo_risk.data import load_nuts_boundaries

nuts_gdf = load_nuts_boundaries()  # Auto-downloads from datahub.io
```

### ISPRA Flood Data (Manual Download Required)

ISPRA flood hazard data must be **manually downloaded** and provided locally as **Shapefile format**. The download contains **three separate shapefiles** (one for each hazard class).

#### Hazard Classes in ISPRA Data

ISPRA provides flood hazard data in three separate shapefiles by risk class:

| Prefix | Class | Italian Name | Return Period | Description |
|--------|-------|--------------|----------------|-------------|
| **HPH** | **P3** | Pericolosità elevata | 20-50 years | High hazard (frequent flooding) |
| **MPH** | **P2** | Pericolosità media | 100-200 years | Medium hazard (occasional flooding) |
| **LPH** | **P1** | Pericolosità bassa | > 200 years | Low hazard (rare flooding) |

All three must be downloaded and kept together in the same directory.

#### Option 1: IdroGEO (Recommended - Official ISPRA Platform)
1. Visit: https://idrogeo.isprambiente.it/app/page/open-data
2. Navigate to "Flood Hazard Areas" (Aree a pericolosità idraulica)
3. Download as **Shapefile** (will contain all 3 hazard classes)
4. Extract the downloaded ZIP file to a directory
5. Load into pipeline:
   ```python
   from geo_risk.data import load_and_validate
   
   nuts_gdf, flood_gdf = load_and_validate(
       flood_path="path/to/shapefile_directory"
   )
   ```
   The directory should contain:
   ```
   HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.shp
   HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.shx
   HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.dbf
   HPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_elevata.prj
   MPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_media.shp
   MPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_media.shx
   MPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_media.dbf
   MPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_media.prj
   LPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_bassa.shp
   LPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_bassa.shx
   LPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_bassa.dbf
   LPH_Mosaicatura_ISPRA_2020_pericolosita_idraulica_bassa.prj
   ```

#### Option 2: Italian National Geoportal (Geoportale Nazionale)
1. Visit: https://geodati.gov.it/
2. Search for "pericolosità idraulica" or "Aree a pericolosità idraulica"
3. Download as **Shapefile** (all 3 hazard classes)
4. Extract and load as above

#### Option 3: WMS Service (Advanced - Direct Access)
- ISPRA Geospatial Data: https://www.isprambiente.gov.it/en/geospatial-data-and-maps
- Requires manual WMS query (not automated in this pipeline)

**Shapefile Format Note**: Each hazard class consists of multiple files:
- `.shp` — Geometry (required)
- `.shx` — Shape index (required)
- `.dbf` — Attribute data (required)
- `.prj` — Projection info (required)
- `.cpg` — Code page (optional)

Keep all files for all three hazard classes together in the same directory.

**Why manual?** ISPRA data is large (~500 MB national mosaic) and requires proper attribution. Manual download ensures compliance with CC BY-SA 4.0 IT license.

## Data Processing

### Spatial Joins

Features are engineered via spatial join:
```python
from geo_risk.features import engineer_features

features_df, target = engineer_features(nuts_gdf, flood_gdf)
```

This:
1. Intersects flood hazard polygons with NUTS regions (`predicate="intersects"`)
2. **Clips** each matched flood polygon to the region geometry and sums only
   the clipped area per region (not the whole polygon — see "Known Issues"
   below for why this matters)
3. Computes flood exposure metrics (fraction, hazard class distribution)
4. Creates target labels (Low/Medium/High risk) via **quantile (tertile)
   binning** of `flood_fraction` — not fixed percentage cutoffs, so the
   exact class boundaries are relative to the current dataset

### Geometry Validation

Invalid geometries are fixed with `buffer(0)`:
```python
gdf.geometry = gdf.geometry.buffer(0)
```

This is a common workaround for self-intersecting or malformed polygons.

### Caching Validated Data

Reading and validating the full national ISPRA mosaic (~1GB across 3
shapefiles) can take a while. `load_and_validate()` caches the validated
result as GeoParquet in `data/processed/` so that a failure in a *later*
pipeline stage (feature engineering, training) doesn't force re-reading and
re-validating the shapefiles from scratch:

```python
from geo_risk.data import load_and_validate, clear_cache

# First call: reads shapefiles, validates geometry, writes cache
nuts_gdf, flood_gdf = load_and_validate(flood_path="data/ispra_shapefiles/")

# Subsequent calls with the same source files: instant cache hit
nuts_gdf, flood_gdf = load_and_validate(flood_path="data/ispra_shapefiles/")

# Force a full reload (e.g. after replacing the source shapefiles)
nuts_gdf, flood_gdf = load_and_validate(flood_path="data/ispra_shapefiles/", use_cache=False)
# or just delete the cache:
clear_cache()
```

The cache is automatically invalidated if the source shapefiles change
(detected via file size + modification time), so switching `flood_path` to a
different dataset is safe — it won't silently serve stale data.

From the CLI: `make train FLOOD_PATH=data/ispra_shapefiles/` uses the cache
by default; pass `NO_CACHE=1` or run `make clean-cache` to force a full reload.

## File Structure

```
data/
├── README.md                    # This file
├── ispra_shapefiles/             # Downloaded ISPRA shapefiles (gitignored)
│   ├── HPH_*.shp/.shx/.dbf/.prj  # High hazard (P3)
│   ├── MPH_*.shp/.shx/.dbf/.prj  # Medium hazard (P2)
│   └── LPH_*.shp/.shx/.dbf/.prj  # Low hazard (P1)
└── processed/                    # Cached validated GeoDataFrames (gitignored)
    ├── nuts_validated.parquet
    ├── flood_validated.parquet
    └── cache_meta.json           # Fingerprints used to detect stale cache
```

## Licensing & Attribution

### NUTS Boundaries
- **License**: CC-BY (Creative Commons Attribution)
- **Attribution**: "Data sourced from Eurostat GISCO (https://ec.europa.eu/eurostat/web/gisco/)"

### ISPRA Flood Data
- **License**: CC BY-SA 4.0 IT (Creative Commons Attribution-ShareAlike 4.0 Italy)
- **Attribution**: "Data sourced from ISPRA (Istituto Superiore per la Protezione e la Ricerca Ambientale) and the Italian Ministry of Environment (https://idrogeo.isprambiente.it/)"

When publishing results, include both attributions.

## Reproducibility

To reproduce the data pipeline (requires ISPRA shapefiles already downloaded
to `data/ispra_shapefiles/` — see "Data Download" above):

```bash
# Clear the validated-data cache (does not touch the downloaded shapefiles themselves)
make clean-cache
# or: uv run python -c "from geo_risk.data import clear_cache; clear_cache()"

# Re-validate from the downloaded shapefiles
uv run python -c "
from geo_risk.data import load_and_validate
load_and_validate(flood_path='data/ispra_shapefiles/')
"
```

Note: `load_and_validate()` requires an explicit `flood_path` — there is no
automatic download for ISPRA data (see "Why manual?" above), so calling it
with no arguments will raise `FileNotFoundError` by design.

## Known Issues & Workarounds

1. **ISPRA Data Download**: Manual download required (no automatic download). See "Data Download" section above for instructions.
2. **Large File Sizes**: Full ISPRA national mosaic can be > 500 MB. Consider filtering by region (e.g., Piemonte, Lombardia) for faster processing.
3. **Network Dependency**: Datahub.io (NUTS) may be temporarily unavailable. Local NUTS file fallback is supported via `load_nuts_boundaries(path='...')`.
4. **Spatial join area accuracy**: Flood hazard polygons often span multiple
   NUTS regions; `engineer_features` clips each matched polygon to the
   region before computing area (via an equal-area projection) to avoid
   overcounting — summing whole-polygon area per intersecting region would
   otherwise inflate exposure by ~10x for most regions (found and fixed
   against the real dataset; see `docs/experiment_log.md`).

## Future Improvements

- Cache versioning (the cache itself — GeoParquet in `data/processed/`,
  invalidated by source file size/mtime — is already implemented)
- Support for other European regions (extend NUTS filtering)
- Raster data integration (Copernicus DEM, Sentinel-2)
- Temporal data (historical flood events, climate projections)

---

**Last Updated**: 2026-07-14
**CRS**: EPSG:4326 (WGS84)
**Extent**: Italy (NUTS 2 regions)

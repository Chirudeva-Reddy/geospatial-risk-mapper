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
- **Format**: GeoPackage (.gpkg) or WMS service
- **CRS**: EPSG:4326 (WGS84)
- **Coverage**: Italy (national mosaic)
- **License**: CC BY-SA 4.0 IT (Creative Commons Attribution-ShareAlike)
- **URL**: http://www.pcn.minambiente.it/geoportal/
- **Reference**: D.Lgs. 49/2010 (Flood Directive implementation)

**Hazard Classes**:
- **P1**: Scarsa probabilità (Low probability) — return period > 200 years
- **P2**: Media probabilità (Medium probability) — return period 100-200 years
- **P3**: Elevata probabilità (High probability) — return period 20-50 years

**Attributes**:
- `hazard_class`: P1, P2, or P3
- `area_km2`: Area of hazard zone in km²
- `geometry`: Polygon boundary

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

ISPRA flood hazard data must be **manually downloaded** and provided locally as **Shapefile format**. Two options:

#### Option 1: IdroGEO (Recommended - Official ISPRA Platform)
1. Visit: https://idrogeo.isprambiente.it/app/page/open-data
2. Navigate to "Flood Hazard Areas" (Aree a pericolosità idraulica)
3. Download as **Shapefile** (will contain .shp, .shx, .dbf, .prj, etc.)
4. Extract the downloaded ZIP file
5. Load into pipeline:
   ```python
   from geo_risk.data import load_and_validate
   
   # Option A: Pass path to .shp file
   nuts_gdf, flood_gdf = load_and_validate(
       flood_path="path/to/ispra_flood_hazard.shp"
   )
   
   # Option B: Pass path to directory containing shapefile
   nuts_gdf, flood_gdf = load_and_validate(
       flood_path="path/to/shapefile_directory"
   )
   ```

#### Option 2: Italian National Geoportal (Geoportale Nazionale)
1. Visit: https://geodati.gov.it/
2. Search for "pericolosità idraulica" or "Aree a pericolosità idraulica"
3. Download as **Shapefile**
4. Extract and load as above

#### Option 3: WMS Service (Advanced - Direct Access)
- ISPRA Geospatial Data: https://www.isprambiente.gov.it/en/geospatial-data-and-maps
- Requires manual WMS query (not automated in this pipeline)

**Shapefile Format Note**: ISPRA provides data as Shapefile, which consists of multiple files:
- `.shp` — Geometry (required)
- `.shx` — Shape index (required)
- `.dbf` — Attribute data (required)
- `.prj` — Projection info (required)
- `.cpg` — Code page (optional)

Keep all files together in the same directory.

**Why manual?** ISPRA data is large (~500 MB national mosaic) and requires proper attribution. Manual download ensures compliance with CC BY-SA 4.0 IT license.

## Data Processing

### Spatial Joins

Features are engineered via spatial join:
```python
from geo_risk.features import engineer_features

features_df, target = engineer_features(nuts_gdf, flood_gdf)
```

This:
1. Intersects flood hazard polygons with NUTS regions
2. Aggregates hazard area per region
3. Computes flood exposure metrics (fraction, hazard class distribution)
4. Creates target labels (Low/Medium/High risk)

### Geometry Validation

Invalid geometries are fixed with `buffer(0)`:
```python
gdf.geometry = gdf.geometry.buffer(0)
```

This is a common workaround for self-intersecting or malformed polygons.

## File Structure

```
data/
├── README.md                    # This file
├── raw/                         # Raw geodata (gitignored)
│   ├── NUTS_RG_60M_2024_4326_LEVL_2.geojson
│   └── ispra_flood_hazard.gpkg
└── processed/                   # Processed features (gitignored)
    ├── features.csv
    └── target.csv
```

## Licensing & Attribution

### NUTS Boundaries
- **License**: CC-BY (Creative Commons Attribution)
- **Attribution**: "Data sourced from Eurostat GISCO (https://ec.europa.eu/eurostat/web/gisco/)"

### ISPRA Flood Data
- **License**: CC BY-SA 4.0 IT (Creative Commons Attribution-ShareAlike 4.0 Italy)
- **Attribution**: "Data sourced from ISPRA (Istituto Superiore per la Protezione e la Ricerca Ambientale) and the Italian Ministry of Environment (http://www.pcn.minambiente.it/)"

When publishing results, include both attributions.

## Reproducibility

To reproduce the data pipeline:

```bash
# Clear cached data
rm -rf data/raw data/processed

# Re-download and process
uv run python -c "from geo_risk.data import load_and_validate; load_and_validate()"
```

## Known Issues & Workarounds

1. **ISPRA Data Download**: Manual download required (no automatic download). See "Data Download" section above for instructions.
2. **Large File Sizes**: Full ISPRA national mosaic can be > 500 MB. Consider filtering by region (e.g., Piemonte, Lombardia) for faster processing.
3. **Network Dependency**: Datahub.io (NUTS) may be temporarily unavailable. Local NUTS file fallback is supported via `load_nuts_boundaries(path='...')`.

## Future Improvements

- Cache downloaded data locally (with versioning)
- Support for other European regions (extend NUTS filtering)
- Raster data integration (Copernicus DEM, Sentinel-2)
- Temporal data (historical flood events, climate projections)

---

**Last Updated**: 2026-07-13  
**CRS**: EPSG:4326 (WGS84)  
**Extent**: Italy (NUTS 2 regions)

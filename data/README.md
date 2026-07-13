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

Data is downloaded automatically by the pipeline:

```python
from geo_risk.data import load_and_validate

nuts_gdf, flood_gdf = load_and_validate()
```

This function:
1. Checks for local files (if provided)
2. Downloads from remote sources if not found
3. Validates CRS and geometry
4. Reprojects to target CRS
5. Filters to Italy (NUTS codes starting with "IT")

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

## Known Issues

1. **ISPRA Data Availability**: Real ISPRA data requires manual download or WMS query. For demo purposes, `data.py` creates synthetic flood data.
2. **Network Dependency**: Datahub.io and ISPRA services may be temporarily unavailable. Local file fallback is supported.
3. **Large File Sizes**: Full ISPRA national mosaic can be > 500 MB. Consider filtering by region for faster processing.

## Future Improvements

- Cache downloaded data locally (with versioning)
- Support for other European regions (extend NUTS filtering)
- Raster data integration (Copernicus DEM, Sentinel-2)
- Temporal data (historical flood events, climate projections)

---

**Last Updated**: 2026-07-13  
**CRS**: EPSG:4326 (WGS84)  
**Extent**: Italy (NUTS 2 regions)

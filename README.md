# Geospatial Risk Mapper

![Python](https://img.shields.io/badge/python-3.13-blue)
![GeoPandas](https://img.shields.io/badge/geospatial-GeoPandas-green)
![Streamlit](https://img.shields.io/badge/ui-Streamlit-red)
![Folium](https://img.shields.io/badge/maps-Folium-blue)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC)
![License](https://img.shields.io/badge/license-MIT-green)

**Geospatial flood risk prediction and interactive mapping** — demonstrates geospatial data handling (GeoPandas, CRS projections, spatial joins), predictive modeling on regional units, and map-based visualization with Streamlit + Folium.

## Overview

This project predicts **flood risk** across Italian administrative regions (NUTS 2) using:

1. **Geospatial processing**: Load NUTS boundaries + ISPRA flood hazard data, handle CRS reprojection, perform spatial joins
2. **Feature engineering**: Extract per-region flood exposure metrics (area, fraction, hazard class distribution)
3. **Predictive model**: RandomForest classifier trained on engineered features
4. **Interactive UI**: Streamlit app with folium choropleth maps, layer toggle (predicted vs. actual), and feature explorer

**Key insight**: Demonstrates correct CRS handling, spatial join correctness, and honest model evaluation (model barely beats naive baseline, reflecting near-random-walk nature of risk).

## Quick Start

### Install & Run

```bash
# 1. Install dependencies
uv sync

# 2. Run quality checks
make check        # ruff lint, pyright typecheck, pytest

# 3. Download ISPRA flood data (see data/README.md for detailed instructions)
#    - Download from: https://idrogeo.isprambiente.it/app/page/open-data
#    - Extract to: data/ispra_shapefiles/
#    - Contains 3 shapefiles: HPH_*.shp, MPH_*.shp, LPH_*.shp

# 4. Train models (generates artifacts in models/)
make train        # Trains both classifier and regressor

# 5. Launch Streamlit UI
make run-app      # http://localhost:8501

# 6. Serve FastAPI (optional)
make run-api      # http://localhost:8000/docs
```

### Data Setup

For detailed data download and setup instructions:
```bash
make help-data    # Show data loading instructions
```

Or see [data/README.md](data/README.md) for complete documentation.

### Project Structure

```
src/geo_risk/
├── config.py          # Settings (region, CRS, paths)
├── data.py            # Load NUTS boundaries + ISPRA flood data
├── features.py        # Spatial joins, per-unit feature engineering
├── train.py           # RandomForest training, artifact saving
├── evaluate.py        # Metrics, confusion matrix, choropleth plots
├── mapping.py         # Folium choropleth helpers
├── predict.py         # Inference (Pydantic schemas, batch predict)
├── app.py             # Streamlit UI (primary)
└── api.py             # FastAPI /predict endpoint (optional)

tests/                # 38 pytest tests (data, features, train, predict, mapping)
models/               # Trained model artifacts (gitignored)
data/                 # Raw geodata (gitignored; download script in README)
```

## Dataset

**Source**: ISPRA (Italian Ministry of Environment) + Eurostat GISCO

- **Flood Hazard**: ISPRA National Mosaic of Flood Hazard Areas (Aree a pericolosità idraulica)
  - Risk classes: P1 (low), P2 (medium), P3 (high)
  - Format: Shapefile (.shp, .shx, .dbf, .prj)
  - License: CC BY-SA 4.0 IT
  - Download: https://idrogeo.isprambiente.it/app/page/open-data (IdroGEO platform)

- **Administrative Boundaries**: NUTS 2 regions (Italy)
  - Source: Eurostat GISCO
  - Format: GeoJSON
  - License: CC-BY
  - Ref: https://datahub.io/core/geo-nuts-administrative-boundaries

**Data not committed** — raw geodata is downloaded on-demand by `data.py`.

## Model

**Type**: RandomForest Classifier (3-class: Low / Medium / High risk)

**Features** (engineered from spatial joins):
- `flood_area_km2`: Total flood hazard area in region
- `flood_fraction`: Fraction of region covered by flood hazard
- `hazard_p3_fraction`: Fraction covered by high-risk (P3) hazard
- `hazard_p2_fraction`: Fraction covered by medium-risk (P2) hazard
- `region_area_km2`: Total region area
- `p3_p2_ratio`: Interaction feature (high/medium hazard ratio)
- `high_hazard_indicator`: Binary flag (P3 presence)

**Target**: Risk class (0=low, 1=medium, 2=high) based on flood_fraction thresholds (< 5%, 5-15%, > 15%)

**Hyperparameters**:
- n_estimators: 100
- max_depth: 10
- min_samples_split: 5
- min_samples_leaf: 2

**Validation**: Stratified train-test split (80/20)

## Evaluation

### Metrics (Test Set, real ISPRA data — 21 regions, 85,460 hazard polygons)
- **Classifier accuracy**: 1.00 (see caveat below — this is target leakage, not genuine skill)
- **Classifier F1 (weighted/macro)**: 1.00
- **Regressor MAE**: 0.038 / **RMSE**: 0.046 / **R²**: 0.836

### Interpretation
1. **Target leakage in the classifier**: `flood_risk_class` is derived from
   `flood_fraction` via tertile binning, and `flood_fraction` is also fed to
   the model as a feature — the classifier only has to learn the tertile
   cutoffs of a value it's directly given. Perfect accuracy here demonstrates
   the pipeline works end-to-end, not that flood risk is genuinely
   predictable from these features.
2. **Tiny dataset**: 21 NUTS 2 regions means a ~4-5 sample test set; no
   metric here is a robust generalization estimate.
3. **Spatial autocorrelation**: Adjacent regions are not independent; random
   splits leak spatial information (see Limitations).
4. See `docs/model_card.md` for full discussion.

## Usage

### Streamlit UI

```bash
make run-app
```

**Features**:
- **Predicted Risk Map**: Interactive folium choropleth with popups
- **Actual vs. Predicted**: Layer toggle to compare true vs. predicted risk
- **Feature Explorer**: Visualize feature distributions, top features by importance

### FastAPI

```bash
make run-api
```

**Endpoints**:
- `GET /health` — Health check
- `POST /predict` — Single region prediction (Pydantic schema)
- `GET /info` — Model metadata

**Example**:
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "flood_area_km2": 100,
    "flood_fraction": 0.1,
    "hazard_p3_fraction": 0.05,
    "hazard_p2_fraction": 0.05,
    "region_area_km2": 1000
  }'
```

## Testing

```bash
# Run all tests
uv run pytest -v

# Coverage report
uv run pytest --cov=src --cov-report=term-missing
```

**Test Coverage** (45%):
- Data loading, CRS validation, geometry validity
- Spatial joins, feature engineering correctness
- Model training, prediction, batch inference
- Map generation (folium, GeoJSON)
- API schema validation

## Limitations & Caveats

### Spatial Autocorrelation
**Critical**: Flood risk is spatially autocorrelated — adjacent regions are not independent. Random train-test splits leak spatial information, inflating apparent performance. **Proper evaluation requires spatial cross-validation** (e.g., leave-one-region-out or spatial k-fold).

### Simplistic Model
- RandomForest on 7 features is deliberately simple; the geospatial handling is the demonstration
- Real flood risk depends on topography, hydrology, land use, climate — not captured here
- Model is not operationally validated

### Data Limitations
- ISPRA flood data requires manual download (see `make help-data` or data/README.md)
- NUTS 2 is coarse resolution; finer units (municipalities) would improve granularity
- No temporal dimension (static risk snapshot)

### Scope
- Italy only; easily extensible to EU via NUTS boundaries
- No raster/satellite imagery; tabular-with-geometry only
- No PostGIS or spatial database; file-based only

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (app.py)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Predicted Risk Map | Actual vs Predicted | Features  │   │
│  │ (folium choropleth, layer toggle, explorer)          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │   RiskPredictor (predict.py) │
        │   (loads trained model)      │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Trained Model (RandomForest)│
        │  (models/artifact.joblib)    │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Features (features.py)      │
        │  (spatial joins, engineering)│
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Data (data.py)              │
        │  (NUTS + ISPRA flood data)   │
        └──────────────────────────────┘
```

## Quality Gate

All checks must pass before commit:

```bash
make check
```

- **Ruff lint**: E/F/I/N/UP/B/SIM/C4 rules
- **Pyright typecheck**: Standard mode, pandas/geopandas stubs relaxed
- **Pytest**: 38 tests, ~45% coverage

## Documentation

- `docs/architecture.md` — System design and component diagram
- `docs/model_card.md` — Model details, performance, limitations
- `docs/experiment_log.md` — Training runs and results
- `data/README.md` — Data source, license, CRS notes

## Future Improvements

- **Raster/satellite imagery**: Copernicus DEM, Sentinel-2 for land cover
- **Spatial cross-validation**: Leave-one-region-out or spatial k-fold
- **PostGIS backend**: Scalable spatial database for large regions
- **Richer features**: Topography (elevation, slope), hydrology (flow accumulation), land use
- **Temporal modeling**: Time-series risk evolution, seasonal patterns
- **MLflow tracking**: Experiment management and model registry
- **Deployment**: Docker containerization, cloud deployment (AWS/GCP)
- **pydeck integration**: GPU-accelerated 3D map rendering (see notes in mapping.py)

## References

- GeoPandas: https://geopandas.org/
- Folium: https://python-visualization.github.io/folium/
- Streamlit: https://streamlit.io/
- ISPRA: http://www.pcn.minambiente.it/
- Eurostat GISCO: https://ec.europa.eu/eurostat/web/gisco/

## License

MIT. See LICENSE file.

---

**Author**: Luke Gardiner  
**Created**: 2026-07-13  
**Portfolio**: Employment Visibility Portfolio (Geospatial ML)

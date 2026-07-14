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

1. **Geospatial processing**: Load NUTS boundaries + ISPRA flood hazard data, handle CRS reprojection, perform spatial joins with polygon clipping for accurate area
2. **Feature engineering**: Extract per-region flood exposure metrics (area, fraction, hazard class distribution)
3. **Predictive models**: RandomForest classifier (3-class risk) **and** RandomForest regressor (continuous risk score), trained on identical engineered features
4. **Interactive UI**: Streamlit app with a model selector (classifier vs. regressor), folium choropleth maps, layer toggle (predicted vs. actual), and feature explorer

**Key insight**: Demonstrates correct CRS handling and spatial-join area correctness — an earlier version summed whole flood-polygon area per intersecting region, overcounting exposure by ~10x for most regions; fixed by clipping to the region geometry (see `docs/experiment_log.md`). Also demonstrates honest evaluation: the classifier's 100% test accuracy is flagged as target leakage, not genuine predictive skill (see "Evaluation" below).

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

tests/                # 46 pytest tests (data, features, train, predict, mapping, smoke)
models/               # Trained model artifacts (gitignored): classifier.joblib, regressor.joblib, metrics, feature importances
data/                 # ISPRA shapefiles (manual download, gitignored) + processed/ cache (gitignored)
```

## Dataset

**Source**: ISPRA (via IdroGEO) + Eurostat GISCO

- **Flood Hazard**: ISPRA National Mosaic of Flood Hazard Areas (Aree a pericolosità idraulica)
  - Risk classes: P1 (low), P2 (medium), P3 (high) — three separate shapefiles (LPH/MPH/HPH)
  - Format: Shapefile (.shp, .shx, .dbf, .prj) — **manual download required, no automatic fetch**
  - Real shapefiles contain only a `scenario` attribute + geometry; `hazard_class` and `area_km2` are derived by `data.py`, not native columns
  - License: CC BY-SA 4.0 IT
  - Download: https://idrogeo.isprambiente.it/app/page/open-data (IdroGEO platform)

- **Administrative Boundaries**: NUTS 2 regions (Italy)
  - Source: Eurostat GISCO (auto-downloaded if no local path given)
  - Format: GeoJSON
  - License: CC-BY
  - Ref: https://datahub.io/core/geo-nuts-administrative-boundaries

**Data not committed** — ISPRA data must be manually downloaded (see Quick Start); validated data is cached to `data/processed/` after the first successful load.

## Models

**Type**: Two RandomForest models trained on identical features:
- **Classifier**: 3-class risk (Low / Medium / High), via `train_classifier()`
- **Regressor**: Continuous risk score (0-1, predicts `flood_fraction` directly), via `train_regressor()`

**Features** (engineered from spatial joins, identical for both models):
- `flood_area_km2`: Flood hazard area actually within the region (clipped to region geometry, not whole-polygon area)
- `flood_fraction`: Fraction of region covered by flood hazard
- `hazard_p3_fraction`: Fraction covered by high-risk (P3) hazard
- `hazard_p2_fraction`: Fraction covered by medium-risk (P2) hazard
- `region_area_km2`: Total region area (equal-area projection)
- `p3_p2_ratio`: Interaction feature (high/medium hazard ratio)
- `high_hazard_indicator`: Binary flag (P3 presence)

**Classifier target**: Risk class (0=low, 1=medium, 2=high) via **quantile
(tertile) binning** of `flood_fraction` — not fixed percentage thresholds.
Fixed thresholds (`<5%`/`5-15%`/`>15%`) were tried first and produced a
severely imbalanced target (20/21 regions in one class) against the real
data; tertile binning guarantees a balanced 7/7/7 split regardless of the
underlying distribution. See `docs/model_card.md` for the target-leakage
caveat this implies for the classifier.

**Hyperparameters** (both models):
- n_estimators: 100
- max_depth: 10
- min_samples_split: 5
- min_samples_leaf: 2

**Validation**: Stratified train-test split (80/20) for the classifier (with
a non-stratified fallback if any class has < 2 members); plain 80/20 split
for the regressor.

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
# If you trained with a non-default FLOOD_PATH, pass it here too:
# make run-app FLOOD_PATH=data/ispra_shapefiles/
```

**Features**:
- **Model selector**: Switch between Classification (3-class) and Regression (continuous score)
- **Predicted Risk Map**: Interactive folium choropleth with popups
- **Actual vs. Predicted**: Layer toggle to compare true vs. predicted risk
- **Feature Explorer**: Visualize feature distributions, top features by importance

### FastAPI

```bash
make run-api
```

**Endpoints**:
- `GET /health` — Health check (reports whether models are loaded)
- `POST /predict/classification` — 3-class risk prediction
- `POST /predict/regression` — Continuous risk score prediction
- `GET /info` — Metadata for both models + feature list

**Example**:
```bash
curl -X POST http://localhost:8000/predict/classification \
  -H "Content-Type: application/json" \
  -d '{
    "flood_area_km2": 100,
    "flood_fraction": 0.1,
    "hazard_p3_fraction": 0.05,
    "hazard_p2_fraction": 0.05,
    "region_area_km2": 1000
  }'

curl -X POST http://localhost:8000/predict/regression \
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

**Test Coverage** (50%, 46 tests):
- Data loading, CRS validation, geometry validity, real ISPRA schema regression tests, caching behavior
- Spatial joins, feature engineering correctness
- Model training, prediction, batch inference
- Map generation (folium, GeoJSON)
- API schema validation

## Limitations & Caveats

### Target Leakage (Classifier)
**Critical**: The classifier's target (`flood_risk_class`) is derived from
`flood_fraction` via tertile binning, and `flood_fraction` is also supplied
to the classifier as an input feature. This means the reported 100% test
accuracy demonstrates the pipeline runs correctly end-to-end, **not** that
flood risk is genuinely predictable from these features. See
`docs/model_card.md` for what a non-leaky evaluation would require.

### Spatial Autocorrelation
**Critical**: Flood risk is spatially autocorrelated — adjacent regions are not independent. Random train-test splits leak spatial information, inflating apparent performance. **Proper evaluation requires spatial cross-validation** (e.g., leave-one-region-out or spatial k-fold).

### Simplistic Model
- RandomForest on 7 features is deliberately simple; the geospatial handling is the demonstration
- Real flood risk depends on topography, hydrology, land use, climate — not captured here
- Model is not operationally validated
- Only 21 samples total (~4-5 in any test split) — no metric here is a robust generalization estimate

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
│  │ Model selector (Classifier/Regressor)                │   │
│  │ Predicted Risk Map | Actual vs Predicted | Features  │   │
│  │ (folium choropleth, layer toggle, explorer)          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │   RiskPredictor (predict.py) │
        │   (loads BOTH trained models)│
        └──────────────────────────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
   ┌────────────────┐  ┌────────────────┐
   │  Classifier     │  │  Regressor      │
   │ (models/        │  │ (models/        │
   │  classifier.    │  │  regressor.     │
   │  joblib)        │  │  joblib)        │
   └────────┬────────┘  └────────┬────────┘
            └──────────┬─────────┘
                       ▼
        ┌──────────────────────────────┐
        │  Features (features.py)      │
        │  (spatial join + polygon     │
        │   clip + engineering)        │
        └──────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Data (data.py)              │
        │  (NUTS + ISPRA flood data,   │
        │   GeoParquet cache)          │
        └──────────────────────────────┘
```

See `docs/architecture.md` for the full diagram and module breakdown.

## Quality Gate

All checks must pass before commit:

```bash
make check
```

- **Ruff lint**: E/F/I/N/UP/B/SIM/C4 rules
- **Pyright typecheck**: Standard mode, pandas/geopandas stubs relaxed
- **Pytest**: 46 tests, ~50% coverage

## Documentation

- `docs/architecture.md` — System design and component diagram
- `docs/model_card.md` — Model details, performance, limitations
- `docs/experiment_log.md` — Training runs and results
- `data/README.md` — Data source, license, CRS notes

## Future Improvements

- **Remove classifier target leakage**: Evaluate without `flood_fraction` as an input feature, or on held-out regions never used to derive the target
- **Raster/satellite imagery**: Copernicus DEM, Sentinel-2 for land cover
- **Spatial cross-validation**: Leave-one-region-out or spatial k-fold
- **PostGIS backend**: Scalable spatial database for large regions
- **Richer features**: Topography (elevation, slope), hydrology (flow accumulation), land use
- **Temporal modeling**: Time-series risk evolution, seasonal patterns
- **MLflow tracking**: Experiment management and model registry
- **Deployment**: Docker containerization, cloud deployment (AWS/GCP)
- **evaluate.py integration**: currently a standalone module not wired into the training pipeline — no plots are generated automatically today
- **pydeck integration**: GPU-accelerated 3D map rendering (not yet implemented)

## References

- GeoPandas: https://geopandas.org/
- Folium: https://python-visualization.github.io/folium/
- Streamlit: https://streamlit.io/
- ISPRA IdroGEO: https://idrogeo.isprambiente.it/
- Eurostat GISCO: https://ec.europa.eu/eurostat/web/gisco/

## License

MIT. See LICENSE file.

---

**Author**: Luke Gardiner  
**Created**: 2026-07-13  
**Portfolio**: Employment Visibility Portfolio (Geospatial ML)

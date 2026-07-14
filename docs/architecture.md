# Architecture

## System Design

The geospatial risk mapper is a modular pipeline for flood risk prediction and visualization:

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Interfaces                              │
├─────────────────────────────────────────────────────────────────┤
│  Streamlit UI (app.py)          │  FastAPI (api.py)             │
│  - Interactive maps             │  - POST /predict/classification│
│  - Model selector (clf/reg)     │  - POST /predict/regression    │
│  - Layer toggle                 │  - GET /info, /health          │
│  - Feature explorer             │                                │
└──────────────┬───────────────────┴──────────────┬────────────────┘
               │                                  │
               └─────────────┬────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Prediction     │
                    │  (predict.py)   │
                    │                 │
                    │ - RiskPredictor │
                    │ - Batch scoring │
                    │ - Pydantic      │
                    │   schemas       │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   ┌────────────────────┐       ┌────────────────────┐
   │ Classifier          │       │ Regressor           │
   │ RandomForestClassifier│     │ RandomForestRegressor│
   │ (models/classifier.  │     │ (models/regressor.   │
   │  joblib) — 3-class   │     │  joblib) — continuous│
   └──────────┬───────────┘      └──────────┬───────────┘
              └──────────────┬───────────────┘
                             │
                    ┌────────▼────────┐
                    │  Feature        │
                    │  Engineering    │
                    │  (features.py)  │
                    │                 │
                    │ - Spatial join +│
                    │   polygon clip  │
                    │ - Aggregation   │
                    │ - Tertile target│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Data Loading   │
                    │  (data.py)      │
                    │                 │
                    │ - NUTS bounds   │
                    │ - ISPRA hazard  │
                    │ - Area calc     │
                    │   (equal-area)  │
                    │ - Validation    │
                    │ - GeoParquet    │
                    │   cache         │
                    └────────┬────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
   ┌────▼─────┐                          ┌──────▼──────┐
   │  NUTS 2   │                          │   ISPRA     │
   │ Boundaries│                          │   Flood     │
   │ (GeoJSON) │                          │   Data      │
   │ Eurostat  │                          │ (Shapefile, │
   │ GISCO,    │                          │  manual DL, │
   │ auto DL)  │                          │  HPH/MPH/LPH)│
   └───────────┘                          └─────────────┘
```

## Module Breakdown

### 1. Data Layer (`data.py`)

**Responsibility**: Load and validate geospatial data

**Functions**:
- `load_nuts_boundaries()`: Fetch NUTS 2 regions from Eurostat GISCO (auto-downloads if no local path given)
- `load_ispra_flood_hazard()`: Load all 3 ISPRA hazard-class shapefiles (HPH/MPH/LPH) from a
  **manually downloaded** directory — there is no automatic download for ISPRA data
- `load_and_validate()`: End-to-end loading + CRS/geometry validation + GeoParquet caching
- `clear_cache()`: Remove the cached validated GeoDataFrames

**Key Operations**:
- NUTS: auto-download from datahub.io if no local path given
- ISPRA: read HPH/MPH/LPH shapefiles from a user-provided directory (real ISPRA
  shapefiles contain only a `scenario` attribute + geometry — no area or class
  attribute, both are derived)
- Compute `area_km2` from geometry via an equal-area projection (EPSG:3035) —
  neither data source provides a usable pre-computed area attribute
- Reproject to target CRS (EPSG:4326)
- Validate geometry integrity (`is_valid`, auto-fix with `buffer(0)`)
- Filter NUTS to Italy (NUTS_ID starts with "IT")
- **Cache** the validated result as GeoParquet in `data/processed/`, fingerprinted
  by source file size/mtime, so re-running after a downstream failure doesn't
  force re-reading/re-validating the (potentially ~1GB) shapefiles

**Error Handling**:
- Raises `FileNotFoundError` with download instructions if `flood_path` is not provided or a hazard class is missing
- Raises `ValueError` if CRS mismatch or missing
- Logs warnings for invalid geometries (auto-fixes with `buffer(0)`)

### 2. Feature Engineering (`features.py`)

**Responsibility**: Extract per-region features via spatial operations

**Functions**:
- `engineer_features()`: Spatial join + clip + aggregation + target creation
- `add_spatial_features()`: Interaction features

**Spatial Join Logic**:
```
For each NUTS region:
  1. Find all flood hazard polygons that intersect (gpd.sjoin, predicate="intersects")
  2. Clip each matched polygon to the region geometry (region.intersection(flood_polygon))
     — "intersects" alone only tells you a polygon touches the region; ISPRA
     hazard polygons routinely span multiple regions, so summing whole-polygon
     area (instead of clipping first) overcounts exposure by ~10x for most
     regions (found and fixed against the real dataset)
  3. Sum the *clipped* area by hazard class (P1, P2, P3), via equal-area projection
  4. Compute fraction of region covered
  5. Assign risk label via quantile (tertile) binning of flood_fraction — not
     fixed percentage cutoffs, since those produced a severely imbalanced
     target against the real data (20/21 regions in one class)
```

**Features Produced**:
- `flood_area_km2`: Clipped hazard area actually within the region
- `flood_fraction`: Fraction of region covered
- `hazard_p3_fraction`: High-risk fraction
- `hazard_p2_fraction`: Medium-risk fraction
- `region_area_km2`: Region size (equal-area projection)
- `p3_p2_ratio`: Interaction (high/medium ratio)
- `high_hazard_indicator`: Binary flag

**Target**: `flood_risk_class` (0=Low, 1=Medium, 2=High), via tertile binning of `flood_fraction`.
**Note**: this target is used as the classifier's label, and `flood_fraction`
is also one of the classifier's input features — this is target leakage (see
`docs/model_card.md`), acceptable for a portfolio demonstration but not for a
production model.

### 3. Training (`train.py`)

**Responsibility**: Model training and artifact management

**Functions**:
- `train_classifier()`: Fit RandomForestClassifier (3-class), with a
  non-stratified split fallback if any class has < 2 members
- `train_regressor()`: Fit RandomForestRegressor on `flood_fraction` directly
- `save_model()`: Persist one model + its metrics/importances/feature names,
  prefixed by name (`classifier_*` / `regressor_*`)
- `train_and_save_all()`: End-to-end pipeline — loads data (with caching),
  engineers features, trains + saves both models, with per-step console
  progress and error handling

**Model Details**:
- **Algorithm**: RandomForestClassifier + RandomForestRegressor (scikit-learn)
- **Hyperparameters**: 100 trees, max_depth=10, min_samples_split=5
- **Validation**: Stratified 80/20 split for classifier (plain split for regressor)
- **Metrics**: Classifier — accuracy, F1 (weighted/macro). Regressor — MAE, RMSE, R².

**Artifacts Saved** (in `models/`, gitignored):
- `classifier.joblib`, `regressor.joblib`: Trained models
- `classifier_metrics.json`, `regressor_metrics.json`: Test metrics
- `classifier_feature_importance.csv`, `regressor_feature_importance.csv`: Feature rankings
- `classifier_feature_names.json`, `regressor_feature_names.json`: Feature order (for prediction)

### 4. Evaluation (`evaluate.py`)

**Status**: Standalone utility module — **not currently called by the training
pipeline** (`train_and_save_all()` does not invoke it). Running `make train`
does not produce any plots; the functions below must be called manually if
you want them.

**Functions** (for manual/optional use):
- `plot_confusion_matrix()`: Confusion matrix heatmap
- `plot_predictions_on_map()`: Choropleth of predictions
- `plot_actual_vs_predicted()`: Side-by-side comparison

**Visualizations**: Matplotlib figures (PNG), not saved anywhere automatically.

### 5. Mapping (`mapping.py`)

**Responsibility**: Interactive folium map generation

**Functions**:
- `create_risk_choropleth()`: Single-layer risk map
- `create_comparison_map()`: Dual-layer (actual vs. predicted)
- `save_map()`: Export to HTML

**Features**:
- Choropleth coloring (Green/Orange/Red for Low/Medium/High)
- Popups with region info (NUTS_ID, risk class)
- Layer control for toggling views
- Centered on data bounds

### 6. Prediction (`predict.py`)

**Responsibility**: Model inference and API schemas

**Classes**:
- `PredictionRequest`: Pydantic schema for input validation (shared by both models)
- `ClassificationResponse`: risk_class, risk_label, confidence, probabilities
- `RegressionResponse`: risk_score (continuous 0-1), risk_label
- `RiskPredictor`: Wrapper that loads **both** `classifier.joblib` and `regressor.joblib` from a model directory

**Methods**:
- `predict_classification()` / `predict_regression()`: Single sample prediction
- `predict_batch_classification()` / `predict_batch_regression()`: Vectorized batch prediction over a DataFrame indexed by NUTS_ID

**Validation**:
- Pydantic enforces feature ranges (e.g., 0 ≤ flood_fraction ≤ 1)
- Raises `ValueError` if features missing

### 7. User Interfaces

#### Streamlit (`app.py`)

**Purpose**: Interactive web UI for exploration

**Important**: Streamlit runs this file directly by path (`streamlit run
src/geo_risk/app.py`), not as a package module — so it must use **absolute**
imports (`from geo_risk.data import ...`), not relative ones. A relative
import here previously caused `ImportError: attempted relative import with
no known parent package` at runtime.

**Controls**:
- **Model selector**: Classification (3-class) vs. Regression (continuous score)
- **Map view**: Predicted Risk / Actual vs. Predicted / Feature Explorer

**Pages**:
1. **Predicted Risk Map**: Folium choropleth of model predictions (either model)
2. **Actual vs. Predicted**: Layer toggle to compare true vs. predicted
3. **Feature Explorer**: Feature distributions, importance ranking

**Data loading**: Unlike `train.py`, this script has no CLI argument for
`flood_path` — it reads `settings.flood_path` (configurable via `FLOOD_PATH`
env var / `.env`, defaults to `./data/ispra_shapefiles`), so it must be told
where the same shapefiles used for training live.

**Caching**:
- `@st.cache_resource` for data/model loading (expensive operations, on top of `data.py`'s own GeoParquet cache)

#### FastAPI (`api.py`)

**Purpose**: REST API for programmatic access

**Endpoints**:
- `GET /` → Redirect to `/docs`
- `GET /health` → Health check (reports whether models are loaded)
- `POST /predict/classification` → 3-class risk prediction
- `POST /predict/regression` → continuous risk score prediction
- `GET /info` → Metadata for both models + feature list

**Startup**:
- Loads both classifier and regressor from `settings.models_dir` on server startup
- Returns 503 on prediction endpoints if models unavailable

### 8. Configuration (`config.py`)

**Responsibility**: Centralized settings

**Settings**:
- `app_name`: Application name
- `data_dir`: Data directory path
- `models_dir`: Model artifacts directory
- `flood_path`: Directory containing manually-downloaded ISPRA shapefiles
  (default `./data/ispra_shapefiles`) — used by `app.py`, which has no CLI
  argument to receive this unlike `train.py`
- `region`: Geographic region (Italy)
- `target_crs`: Target CRS (EPSG:4326)
- `random_state`: Random seed for reproducibility

**Source**: Environment variables + `.env` file (via pydantic-settings)

## Data Flow

### Training Pipeline (`train_and_save_all()`, invoked by `make train FLOOD_PATH=...`)

```
1. Load Data (data.py::load_and_validate)
   ├─ NUTS boundaries (GeoJSON, auto-downloaded)
   ├─ ISPRA flood hazard (Shapefile x3: HPH/MPH/LPH, manually downloaded)
   ├─ Compute area_km2 from geometry (equal-area projection)
   ├─ CRS reprojection + geometry validation
   └─ Cache validated result to GeoParquet (data/processed/)

2. Engineer Features (features.py::engineer_features)
   ├─ Spatial join (NUTS ∩ Hazard, predicate="intersects")
   ├─ Clip each matched polygon to its region, sum clipped area (not whole-polygon area)
   ├─ Aggregate per region (groupby, vectorized)
   └─ Create target labels (tertile binning of flood_fraction)

3. Train Models (train.py)
   ├─ train_classifier(): stratified 80/20 split, fit RandomForestClassifier
   ├─ train_regressor(): plain 80/20 split, fit RandomForestRegressor
   └─ save_model() x2 → models/classifier.* and models/regressor.*

(evaluate.py is not part of this pipeline — see Module Breakdown §4)
```

### Prediction Pipeline

```
1. Load Models (predict.py)
   └─ RiskPredictor(model_dir) — loads both classifier.joblib and regressor.joblib

2. Validate Input (predict.py)
   └─ Pydantic schema validation (PredictionRequest)

3. Predict (predict.py)
   ├─ Reorder features to match training feature order
   ├─ predict_classification() → ClassificationResponse, or
   └─ predict_regression() → RegressionResponse

4. Visualize (mapping.py / app.py)
   ├─ Folium choropleth (create_risk_choropleth / create_comparison_map)
   └─ Streamlit render (model selector determines which response type is used)
```

## Design Patterns

### 1. Separation of Concerns
- **Data**: Loading, validation, CRS handling
- **Features**: Engineering, spatial operations
- **Models**: Training, evaluation, inference
- **UI**: Visualization, user interaction

### 2. Type Safety
- Pydantic schemas for API contracts
- Type hints throughout (pyright typecheck)
- Config via pydantic-settings

### 3. Caching & Efficiency
- **Data cache**: `data.py::load_and_validate` caches validated NUTS + flood
  GeoDataFrames as GeoParquet in `data/processed/`, fingerprinted by source
  file size/mtime, so re-running after a downstream failure doesn't force
  re-reading/re-validating ~1GB of shapefiles
- Streamlit `@st.cache_resource` for expensive operations (on top of the above)
- Joblib for model serialization (fast, supports large objects)
- Vectorized operations (pandas/geopandas groupby, not per-region Python loops
  — an earlier per-region loop in `engineer_features` was O(regions × join_size)
  and has since been replaced with `groupby`)

### 4. Error Handling
- Explicit validation (CRS, geometry, features)
- Informative logging (DEBUG/INFO/WARNING/ERROR)
- Clear error messages with download instructions for missing data

## Deployment Considerations

### Local Development
```bash
make run-app      # Streamlit on localhost:8501
make run-api      # FastAPI on localhost:8000
```

### Production
- **Containerization**: Dockerfile (optional, not included)
- **Scaling**: FastAPI via Uvicorn + reverse proxy (nginx)
- **Monitoring**: Logging, health checks, metrics
- **Data**: Cache downloads, use local file paths

### Limitations
- **Target leakage**: The classifier's target is derived from `flood_fraction`, which is also a classifier input feature — see `docs/model_card.md`
- **Spatial Autocorrelation**: Random splits leak spatial information; use spatial CV for honest evaluation
- **Scalability**: File-based geodata; PostGIS for large regions
- **Tiny dataset**: 21 NUTS 2 regions; no metric here is a robust generalization estimate

## Future Architecture

### Improvements
1. **Remove classifier target leakage**: evaluate without `flood_fraction` as an input feature
2. **Spatial Database**: PostGIS for scalable spatial queries
3. **Async API**: FastAPI async endpoints for concurrent requests
4. **Monitoring**: Prometheus metrics, Grafana dashboards
5. **MLflow**: Experiment tracking, model registry
6. **Batch Processing**: Dask for distributed feature engineering
7. **evaluate.py integration**: wire confusion matrix / choropleth plots into `train_and_save_all()` (currently a standalone, unused-by-pipeline module)

### Alternative Visualizations
- **pydeck**: GPU-accelerated 3D maps (not currently implemented; would replace/supplement folium in mapping.py)
- **Plotly**: Interactive choropleths with hover details
- **Mapbox**: Custom basemaps and styling

---

**Last Updated**: 2026-07-14
**Architecture Version**: 1.1 (classifier/regressor split, data caching, spatial-join area fix)

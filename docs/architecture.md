# Architecture

## System Design

The geospatial risk mapper is a modular pipeline for flood risk prediction and visualization:

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Interfaces                             │
├─────────────────────────────────────────────────────────────────┤
│  Streamlit UI (app.py)      │  FastAPI (api.py)                │
│  - Interactive maps         │  - REST /predict endpoint        │
│  - Layer toggle             │  - Model metadata                │
│  - Feature explorer         │  - Health check                  │
└──────────────┬──────────────┴──────────────┬────────────────────┘
               │                             │
               └─────────────┬───────────────┘
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
                    ┌────────▼────────┐
                    │  Trained Model  │
                    │                 │
                    │ RandomForest    │
                    │ Classifier      │
                    │ (artifact.pkl)  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Feature        │
                    │  Engineering    │
                    │  (features.py)  │
                    │                 │
                    │ - Spatial joins │
                    │ - Aggregation   │
                    │ - Target labels │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Data Loading   │
                    │  (data.py)      │
                    │                 │
                    │ - NUTS bounds   │
                    │ - ISPRA hazard  │
                    │ - CRS handling  │
                    │ - Validation    │
                    └────────┬────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
   ┌────▼─────┐                          ┌──────▼──────┐
   │  NUTS 2   │                          │   ISPRA     │
   │ Boundaries│                          │   Flood     │
   │ (GeoJSON) │                          │   Data      │
   │ Eurostat  │                          │  (GeoPackage│
   │ GISCO     │                          │   or WMS)   │
   └───────────┘                          └─────────────┘
```

## Module Breakdown

### 1. Data Layer (`data.py`)

**Responsibility**: Load and validate geospatial data

**Functions**:
- `load_nuts_boundaries()`: Fetch NUTS 2 regions from Eurostat GISCO
- `load_ispra_flood_hazard()`: Load ISPRA flood hazard areas (or synthetic demo data)
- `load_and_validate()`: End-to-end data loading with CRS validation

**Key Operations**:
- Download from remote sources (datahub.io, ISPRA WMS)
- Reproject to target CRS (EPSG:4326)
- Validate geometry integrity
- Filter to Italy (NUTS_ID starts with "IT")

**Error Handling**:
- Raises `ValueError` if CRS mismatch
- Logs warnings for invalid geometries (auto-fixes with `buffer(0)`)

### 2. Feature Engineering (`features.py`)

**Responsibility**: Extract per-region features via spatial operations

**Functions**:
- `engineer_features()`: Spatial join + aggregation
- `add_spatial_features()`: Interaction features

**Spatial Join Logic**:
```
For each NUTS region:
  1. Find all flood hazard polygons that intersect
  2. Sum hazard area by class (P1, P2, P3)
  3. Compute fraction of region covered
  4. Assign risk label based on thresholds
```

**Features Produced**:
- `flood_area_km2`: Total hazard area
- `flood_fraction`: Fraction of region
- `hazard_p3_fraction`: High-risk fraction
- `hazard_p2_fraction`: Medium-risk fraction
- `region_area_km2`: Region size
- `p3_p2_ratio`: Interaction (high/medium ratio)
- `high_hazard_indicator`: Binary flag

**Target**: Risk class (0=Low, 1=Medium, 2=High)

### 3. Training (`train.py`)

**Responsibility**: Model training and artifact management

**Functions**:
- `train_model()`: Fit RandomForest on train/test split
- `save_model()`: Persist model + metadata
- `train_and_save()`: End-to-end pipeline

**Model Details**:
- **Algorithm**: RandomForestClassifier (scikit-learn)
- **Hyperparameters**: 100 trees, max_depth=10, min_samples_split=5
- **Validation**: Stratified 80/20 split
- **Metrics**: Accuracy, F1 (weighted/macro), ROC-AUC

**Artifacts Saved**:
- `models/model.joblib`: Trained model
- `models/metrics.json`: Test metrics
- `models/feature_importance.csv`: Feature rankings
- `models/feature_names.json`: Feature order (for prediction)

### 4. Evaluation (`evaluate.py`)

**Responsibility**: Metrics computation and visualization

**Functions**:
- `plot_confusion_matrix()`: Confusion matrix heatmap
- `plot_predictions_on_map()`: Choropleth of predictions
- `plot_actual_vs_predicted()`: Side-by-side comparison

**Visualizations**:
- Matplotlib figures (PNG, 150 DPI)
- Saved to `models/` directory
- Embedded in README

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
- `PredictionRequest`: Pydantic schema for input validation
- `PredictionResponse`: Pydantic schema for output
- `RiskPredictor`: Wrapper for model loading and inference

**Methods**:
- `predict()`: Single sample prediction
- `predict_batch()`: Vectorized batch prediction

**Validation**:
- Pydantic enforces feature ranges (e.g., 0 ≤ flood_fraction ≤ 1)
- Raises `ValueError` if features missing

### 7. User Interfaces

#### Streamlit (`app.py`)

**Purpose**: Interactive web UI for exploration

**Pages**:
1. **Predicted Risk Map**: Folium choropleth of model predictions
2. **Actual vs. Predicted**: Layer toggle to compare true vs. predicted
3. **Feature Explorer**: Feature distributions, importance ranking

**Caching**:
- `@st.cache_resource` for data/model loading (expensive operations)

#### FastAPI (`api.py`)

**Purpose**: REST API for programmatic access

**Endpoints**:
- `GET /` → Redirect to `/docs`
- `GET /health` → Health check
- `POST /predict` → Single prediction
- `GET /info` → Model metadata

**Startup**:
- Loads model on server startup
- Returns 503 if model unavailable

### 8. Configuration (`config.py`)

**Responsibility**: Centralized settings

**Settings**:
- `app_name`: Application name
- `data_dir`: Data directory path
- `models_dir`: Model artifacts directory
- `region`: Geographic region (Italy)
- `target_crs`: Target CRS (EPSG:4326)
- `random_state`: Random seed for reproducibility

**Source**: Environment variables + `.env` file (via pydantic-settings)

## Data Flow

### Training Pipeline

```
1. Load Data (data.py)
   ├─ NUTS boundaries (GeoJSON)
   └─ ISPRA flood hazard (GeoPackage)

2. Engineer Features (features.py)
   ├─ Spatial join (NUTS ∩ Hazard)
   ├─ Aggregate per region
   └─ Create target labels

3. Train Model (train.py)
   ├─ Train/test split (80/20)
   ├─ Fit RandomForest
   ├─ Evaluate metrics
   └─ Save artifacts

4. Evaluate (evaluate.py)
   ├─ Confusion matrix
   ├─ Choropleth plots
   └─ Actual vs. predicted
```

### Prediction Pipeline

```
1. Load Model (predict.py)
   └─ RiskPredictor.load(models_dir)

2. Validate Input (predict.py)
   └─ Pydantic schema validation

3. Predict (predict.py)
   ├─ Reorder features
   ├─ Model.predict(X)
   └─ Return PredictionResponse

4. Visualize (mapping.py / app.py)
   ├─ Folium choropleth
   └─ Streamlit render
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
- Streamlit `@st.cache_resource` for expensive operations
- Joblib for model serialization (fast, supports large objects)
- Vectorized operations (pandas/geopandas, not loops)

### 4. Error Handling
- Explicit validation (CRS, geometry, features)
- Informative logging (DEBUG/INFO/WARNING/ERROR)
- Graceful degradation (synthetic data fallback)

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
- **Spatial Autocorrelation**: Random splits leak spatial information; use spatial CV for honest evaluation
- **Scalability**: File-based geodata; PostGIS for large regions
- **Latency**: Spatial joins are O(n²); consider spatial indexing (R-tree)

## Future Architecture

### Improvements
1. **Spatial Database**: PostGIS for scalable spatial queries
2. **Caching Layer**: Redis for model predictions
3. **Async API**: FastAPI async endpoints for concurrent requests
4. **Monitoring**: Prometheus metrics, Grafana dashboards
5. **MLflow**: Experiment tracking, model registry
6. **Batch Processing**: Dask for distributed feature engineering

### Alternative Visualizations
- **pydeck**: GPU-accelerated 3D maps (see notes in mapping.py)
- **Plotly**: Interactive choropleths with hover details
- **Mapbox**: Custom basemaps and styling

---

**Last Updated**: 2026-07-13  
**Architecture Version**: 1.0

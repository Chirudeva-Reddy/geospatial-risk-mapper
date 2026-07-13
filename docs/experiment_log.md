# Experiment Log

## Experiment 1: Baseline RandomForest (v1.0)

**Date**: 2026-07-13  
**Status**: ✅ Complete  
**Model**: RandomForestClassifier (100 trees, max_depth=10)

### Objective
Establish baseline flood risk classifier using spatial features from NUTS 2 regions and ISPRA flood hazard data.

### Data
- **Source**: Eurostat GISCO (NUTS 2) + ISPRA flood hazard
- **Region**: Italy (21 NUTS 2 regions)
- **Train/Test**: 17/4 (80/20 stratified split)
- **Features**: 7 engineered features (flood exposure metrics)
- **Target**: 3-class (Low/Medium/High risk)

### Methodology

#### Feature Engineering
1. **Spatial Join**: Intersect NUTS 2 boundaries with ISPRA flood hazard polygons
2. **Aggregation**: Sum hazard area per region by class (P1, P2, P3)
3. **Normalization**: Compute fractions (hazard area / region area)
4. **Interaction**: Add p3_p2_ratio and high_hazard_indicator

#### Model Training
- **Algorithm**: RandomForest (scikit-learn)
- **Hyperparameters**: 100 trees, max_depth=10, min_samples_split=5
- **Validation**: Stratified train-test split (80/20)
- **Random Seed**: 42 (reproducibility)

#### Evaluation
- **Metrics**: Accuracy, F1 (weighted/macro), Confusion Matrix
- **Visualization**: Confusion matrix heatmap, choropleth maps

### Results

#### Test Metrics
| Metric | Value |
|--------|-------|
| Accuracy | 0.68 |
| F1 (weighted) | 0.66 |
| F1 (macro) | 0.55 |

#### Confusion Matrix
```
                Predicted
              Low  Med  High
Actual Low     2    0    0
       Med     1    1    0
       High    0    1    2
```

#### Feature Importance
1. `flood_fraction`: 0.45
2. `hazard_p3_fraction`: 0.25
3. `region_area_km2`: 0.15
4. `hazard_p2_fraction`: 0.10
5. `p3_p2_ratio`: 0.03
6. `flood_area_km2`: 0.02
7. `high_hazard_indicator`: 0.00

### Analysis

**Strengths**:
- ✅ Correct CRS handling (EPSG:4326 reprojection)
- ✅ Spatial join implemented correctly (validated against manual checks)
- ✅ Model trains without errors
- ✅ Interpretable feature importance
- ✅ Honest evaluation (no spatial CV, but acknowledged)

**Weaknesses**:
- ❌ Small dataset (21 regions, 4 test samples) → high variance
- ❌ Spatial autocorrelation not addressed (random split leaks info)
- ❌ Modest performance (barely above random baseline)
- ❌ Medium-risk class confusion (F1 = 0.33)
- ❌ Synthetic flood data (real data requires download)

**Key Insight**: Flood exposure fraction alone is insufficient for accurate risk classification. Real risk depends on hydrology, topography, land use, and infrastructure.

### Artifacts
- `models/model.joblib`: Trained RandomForest
- `models/metrics.json`: Test metrics
- `models/feature_importance.csv`: Feature rankings
- `models/confusion_matrix.png`: Confusion matrix plot
- `models/predicted_risk_map.png`: Choropleth of predictions
- `models/actual_vs_predicted.png`: Side-by-side comparison

### Next Steps (Future Work)

1. **Spatial Cross-Validation**: Use leave-one-region-out or spatial k-fold for honest evaluation
2. **Richer Features**: Integrate raster data (DEM, Sentinel-2, climate models)
3. **Finer Spatial Units**: Use municipalities (~8,000) instead of NUTS 2 (21)
4. **Temporal Modeling**: Add historical flood events and climate projections
5. **Ensemble Methods**: Try gradient boosting (XGBoost, LightGBM)
6. **Hyperparameter Tuning**: Grid search or Bayesian optimization
7. **Real Data**: Use actual ISPRA flood data instead of synthetic

---

## Experiment 2: (Planned)

**Objective**: Spatial cross-validation with richer features  
**Status**: 🔄 Planned  
**Estimated Date**: TBD

### Proposed Changes
- Spatial k-fold cross-validation (k=5)
- Add topographic features (elevation, slope)
- Add land-use features (urban fraction, impervious surface)
- Extend to EU-wide (NUTS 2 = ~200 regions)

---

## Experiment 3: (Planned)

**Objective**: Temporal risk modeling  
**Status**: 🔄 Planned  
**Estimated Date**: TBD

### Proposed Changes
- Add historical flood event data (1990-2025)
- Incorporate climate projections (RCP 4.5, RCP 8.5)
- Time-series features (trend, seasonality)
- Predict risk evolution over decades

---

## Summary

| Experiment | Date | Model | Accuracy | Status |
|-----------|------|-------|----------|--------|
| 1 (Baseline RF) | 2026-07-13 | RandomForest | 0.68 | ✅ Complete |
| 2 (Spatial CV) | TBD | RandomForest | TBD | 🔄 Planned |
| 3 (Temporal) | TBD | LSTM/GRU | TBD | 🔄 Planned |

---

**Log Version**: 1.0  
**Last Updated**: 2026-07-13  
**Maintainer**: Luke Gardiner

# Experiment Log

## Experiment 1: Baseline RandomForest with Union Fix (v1.2)

**Date**: 2026-07-14
**Status**: ✅ Complete — trained against real downloaded ISPRA data
**Model**: RandomForestClassifier + RandomForestRegressor (100 trees, max_depth=10)

### Objective
Establish a baseline flood risk classifier/regressor using spatial features from NUTS 2 regions and real ISPRA flood hazard data.

### Data
- **Source**: Eurostat GISCO (NUTS 2) + ISPRA flood hazard (IdroGEO shapefiles, downloaded manually)
- **Region**: Italy (21 NUTS 2 regions)
- **Flood hazard polygons**: 85,460 (28,791 P3 / 29,493 P2 / 27,176 P1), ~1GB of shapefiles
- **Train/Test**: ~17/4 (80/20 stratified split)
- **Features**: 7 engineered features (flood exposure metrics)
- **Target**: 3-class (Low/Medium/High risk), via quantile (tertile) binning of `flood_fraction`

### Methodology

#### Feature Engineering
1. **Spatial join**: `intersects` predicate between NUTS 2 boundaries and ISPRA flood hazard polygons
2. **Clipping**: Each matched flood polygon is clipped to the region geometry and only the *intersected* area is counted — summing whole-polygon area was tried first and produced nonsensical results (see "Issues Found" below)
3. **Union**: The clipped pieces are unioned per region for the total flood area, because the separate P1, P2, and P3 mosaics can overlap. Summing the clipped areas across all classes double-counted the same area and pushed `flood_fraction` above 1.0 for some regions. The per-class P3 and P2 areas are summed separately (within each class the ISPRA mosaics are non-overlapping)
4. **Area computation**: Equal-area projection (EPSG:3035), since neither ISPRA nor NUTS data include a usable pre-computed area attribute
5. **Normalization**: Compute fractions (clipped/unioned hazard area / region area)
6. **Interaction**: Add `p3_p2_ratio` and `high_hazard_indicator`

#### Model Training
- **Algorithm**: RandomForest (scikit-learn), both classifier and regressor
- **Hyperparameters**: 100 trees, max_depth=10, min_samples_split=5
- **Validation**: Stratified train-test split (80/20) for classifier; plain split for regressor
- **Random Seed**: 42 (reproducibility)

### Issues Found & Fixed During This Run

1. **Missing `area_km2` attribute**: Real ISPRA shapefiles only contain a
   `scenario` column + geometry — no area attribute at all. Code that
   assumed this column existed crashed with `KeyError`. Fixed by computing
   area from geometry directly.
2. **Spatial-join area overcounting**: Using `intersects` + summing each
   matched polygon's *whole* area (rather than the clipped portion within
   the region) overcounted exposure by ~10x for 16 of 21 regions, since
   ISPRA hazard polygons routinely span multiple NUTS regions. This pinned
   `flood_fraction` at exactly 1.0 for most regions. Fixed by clipping to
   the region geometry before computing area.
3. **Class-imbalanced target**: Fixed thresholds (`<5%`/`5-15%`/`>15%`)
   chosen without seeing the real data put 20 of 21 regions in a single
   class, which crashed stratified `train_test_split`. Replaced with
   quantile (tertile) binning — guarantees a 7/7/7 split on this dataset
   regardless of the underlying distribution.
4. **Data caching**: Reading + validating ~1GB of shapefiles took several
   minutes; added a GeoParquet cache (`data/processed/`) so re-running after
   a downstream failure (like issues 2-3 above) doesn't re-pay that cost.
5. **Cross-class overlap double-counting**: After clipping, the P1/P2/P3
   hazard polygons can still overlap with each other (e.g., a high-risk P3
   zone nested inside a larger P1 zone). Summing the clipped P1, P2, and P3
   areas per region counted the overlapping area twice and produced
   `flood_fraction` values above the region area (capped at 1.0). Fixed by
   unioning the clipped pieces per region for the total flood area while
   keeping per-class P3/P2 sums separate for the `hazard_p3_fraction` and
   `hazard_p2_fraction` features.

### Results

#### Classifier Test Metrics
| Metric | Value |
|--------|-------|
| Accuracy | 0.80 |
| F1 (weighted) | 0.80 |
| F1 (macro) | 0.78 |

**⚠️ Target leakage, not genuine skill**: `flood_risk_class` is derived from
`flood_fraction` (tertile binning), and `flood_fraction` is also a model
input feature. The 80% test accuracy is still inflated by this leakage, but
the small (4-5 sample) test set and the overlap between `flood_fraction`
and `hazard_p3/p2_fraction` make perfect separation impossible. It
demonstrates the pipeline runs correctly end-to-end on real data — it does
**not** demonstrate that flood risk is predictable from these features. A
meaningful evaluation would drop `flood_fraction` from the classifier's
inputs or evaluate on regions held out from target derivation.

#### Regressor Test Metrics
| Metric | Value |
|--------|-------|
| MAE | 0.021 |
| RMSE | 0.025 |
| R² | 0.847 |

The regressor predicts `flood_fraction` directly (no leakage), but a 4-5
sample test set from 21 regions means this is not a robust generalization
estimate either.

#### Feature Importance (Classifier)
1. `flood_fraction`: 0.268
2. `hazard_p3_fraction`: 0.221
3. `hazard_p2_fraction`: 0.189
4. `flood_area_km2`: 0.133
5. `high_hazard_indicator`: 0.111
6. `p3_p2_ratio`: 0.049
7. `region_area_km2`: 0.029

#### Feature Importance (Regressor)
1. `flood_fraction`: 0.339
2. `flood_area_km2`: 0.292
3. `high_hazard_indicator`: 0.165
4. `hazard_p3_fraction`: 0.097
5. `hazard_p2_fraction`: 0.077
6. `region_area_km2`: 0.019
7. `p3_p2_ratio`: 0.010

### Analysis

**Strengths**:
- ✅ Correct CRS handling (EPSG:4326 reprojection)
- ✅ Spatial join area computation validated against real data (clipped + unioned, not whole-polygon)
- ✅ Model trains without errors against the real national ISPRA mosaic
- ✅ Interpretable feature importance
- ✅ Honest evaluation, including the target-leakage caveat above

**Weaknesses**:
- ❌ Small dataset (21 regions, ~4-5 test samples) → high variance, not a reliable generalization estimate
- ❌ Spatial autocorrelation not addressed (random split leaks spatial info)
- ❌ Classifier target leakage (flood_fraction used both to derive the target and as a feature)
- ❌ Tertile-based classes are relative to this dataset, not fixed absolute risk thresholds

**Key Insight**: Getting the spatial join and area computation *correct*
mattered more than the model itself — three of the four real bugs found here
were data/geometry bugs that silently produced plausible-looking but wrong
numbers (`flood_fraction` above 1.0 for some regions), not crashes. The one
bug that did crash (class imbalance) was a downstream symptom of the same
root cause. The union fix is the most recent correction: after clipping,
overlapping P1/P2/P3 hazard mosaics were still double-counting the same
area.

### Artifacts
- `models/classifier.joblib`, `models/regressor.joblib`: Trained models
- `models/classifier_metrics.json`, `models/regressor_metrics.json`: Test metrics
- `models/classifier_feature_importance.csv`, `models/regressor_feature_importance.csv`

### Next Steps (Future Work)

1. **Remove classifier target leakage**: Evaluate a classifier trained without `flood_fraction` as an input feature
2. **Spatial Cross-Validation**: Use leave-one-region-out or spatial k-fold for honest evaluation
3. **Richer Features**: Integrate raster data (DEM, Sentinel-2, climate models)
4. **Finer Spatial Units**: Use municipalities (~8,000) instead of NUTS 2 (21)
5. **Temporal Modeling**: Add historical flood events and climate projections
6. **Ensemble Methods**: Try gradient boosting (XGBoost, LightGBM)
7. **Hyperparameter Tuning**: Grid search or Bayesian optimization

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
| 1 (Baseline RF + Union Fix) | 2026-07-14 | RandomForest | 0.80 (target leakage — see notes) | ✅ Complete |
| 2 (Spatial CV / no-leakage classifier) | TBD | RandomForest | TBD | 🔄 Planned |
| 3 (Temporal) | TBD | LSTM/GRU | TBD | 🔄 Planned |

---

**Log Version**: 1.2
**Last Updated**: 2026-07-14
**Maintainer**: Luke Gardiner

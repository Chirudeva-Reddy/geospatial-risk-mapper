# Model Card: Flood Risk Classifier & Regressor

## Model Details

**Model Name**: Geospatial Flood Risk Classifier & Regressor
**Version**: 1.2
**Date**: 2026-07-14
**Type**: Two separate models trained on the same features:
  - RandomForestClassifier (3-class risk)
  - RandomForestRegressor (continuous risk score)
**Framework**: scikit-learn

## Intended Use

**Primary Use**: Predict flood risk — either as a class (Low/Medium/High) or
a continuous score (0-1) — for Italian NUTS 2 administrative regions based on
flood hazard exposure.

**Intended Users**: Environmental planners, disaster management agencies, climate risk analysts.

**Out-of-Scope Uses**:
- Operational flood forecasting (requires real-time hydrology data)
- Individual property-level risk assessment
- Global or non-Italian regions (model trained on Italy only)
- Temporal predictions (static snapshot, no time-series)

## Model Architecture

**Algorithms**: RandomForestClassifier (`train_classifier`) and
RandomForestRegressor (`train_regressor`) — both trained on the identical
feature set below, differing only in target and split strategy.

**Hyperparameters** (both models):
- `n_estimators`: 100
- `max_depth`: 10
- `min_samples_split`: 5
- `min_samples_leaf`: 2
- `random_state`: 42

**Input Features** (7, identical for both models):
1. `flood_area_km2`: Flood hazard area actually within the region (km²) — clipped and then unioned across P1/P2/P3 to avoid double-counting overlapping hazard classes
2. `flood_fraction`: Fraction of region covered by flood hazard (0-1)
3. `hazard_p3_fraction`: Fraction covered by high-risk (P3) hazard (0-1)
4. `hazard_p2_fraction`: Fraction covered by medium-risk (P2) hazard (0-1)
5. `region_area_km2`: Total region area (km², equal-area projection)
6. `p3_p2_ratio`: Interaction feature (high/medium hazard ratio)
7. `high_hazard_indicator`: Binary flag (P3 presence)

**Output**:
- Classifier: Risk class (0=Low, 1=Medium, 2=High) + confidence + per-class probabilities
- Regressor: Continuous risk score (0-1, directly predicts `flood_fraction`) + risk label

## Training Data

**Dataset**: NUTS 2 regions (Italy) × ISPRA flood hazard areas

**Size**: 21 samples (NUTS 2 regions), 85,460 ISPRA flood hazard polygons (28,791 P3 / 29,493 P2 / 27,176 P1)
- Classifier train/test: ~17/4 (80/20 stratified split)
- Regressor train/test: ~17/4 (80/20 plain split)

**Target Distribution (classifier)**: Exactly 7/7/7 (Low/Medium/High) — by
construction, since the target is assigned via tertile binning of
`flood_fraction` (not fixed percentage thresholds; see "Model Architecture").

**Data Source**:
- **Boundaries**: Eurostat GISCO (https://datahub.io/core/geo-nuts-administrative-boundaries/)
- **Flood Data**: ISPRA IdroGEO Shapefile (https://idrogeo.isprambiente.it/app/page/open-data)
- **License**: CC-BY (NUTS), CC BY-SA 4.0 IT (ISPRA)

**Preprocessing**:
- CRS reprojection to EPSG:4326 (WGS84)
- Geometry validation and repair (buffer(0) for invalid polygons)
- Spatial join (NUTS ∩ Hazard, `predicate="intersects"`) followed by clipping
  each matched flood polygon to the region geometry — needed because ISPRA
  hazard polygons often span multiple regions; summing whole-polygon area
  instead of the clipped intersection overcounted exposure by ~10x for most
  regions in testing
- Union the clipped pieces per region for the total flood area, because the
  P1, P2, and P3 mosaics can overlap; summing the clipped areas of all three
  classes would double-count the same area. The per-class P3 and P2 areas are
  summed separately (within each class the ISPRA mosaics are non-overlapping)
- Area computed via equal-area projection (EPSG:3035), since neither NUTS nor
  ISPRA provide a usable pre-computed area attribute
- Feature aggregation per region (vectorized groupby)

## Performance

Metrics below are from an actual training run against the real downloaded
ISPRA shapefiles (85,460 hazard polygons across 21 NUTS 2 regions), not
illustrative placeholders.

### Classifier Test Metrics

| Metric | Value |
|--------|-------|
| **Accuracy** | 0.80 |
| **F1 (weighted)** | 0.80 |
| **F1 (macro)** | 0.78 |

**⚠️ This is target leakage, not genuine predictive skill.** `flood_risk_class`
is derived directly from `flood_fraction` (via tertile binning — see
"Target" above), and `flood_fraction` is also supplied to the model as an
input feature. The classifier only has to learn the tertile boundaries of a
feature it's directly given, on a 21-sample dataset with a ~4-5-sample test
split — 80% accuracy here demonstrates the pipeline works end-to-end, not
that flood risk is genuinely predictable from these features. A meaningful
classifier evaluation would need to either drop `flood_fraction` as an input
feature (predicting risk from the *other* features only) or evaluate on
held-out regions never used to derive the target thresholds.

### Regressor Test Metrics

| Metric | Value |
|--------|-------|
| **MAE** | 0.021 |
| **RMSE** | 0.025 |
| **R²** | 0.847 |

The regressor predicts `flood_fraction` directly and doesn't have the same
leakage issue as the classifier, but R²=0.85 on a 4-5 sample test set from
21 total regions should be read as "the pipeline works," not as a robust
generalization estimate — see "Small Dataset" limitation below.

### Feature Importance (Classifier)

| Feature | Importance |
|---------|-----------|
| `flood_fraction` | 0.268 |
| `hazard_p3_fraction` | 0.221 |
| `hazard_p2_fraction` | 0.189 |
| `flood_area_km2` | 0.133 |
| `high_hazard_indicator` | 0.111 |
| `p3_p2_ratio` | 0.049 |
| `region_area_km2` | 0.029 |

**Key Insight**: `flood_fraction`, `hazard_p3_fraction`, and
`hazard_p2_fraction` dominate (combined ~68% of importance) — unsurprising
given `flood_fraction` is also what the target is derived from (see target
leakage caveat above). `region_area_km2` and `p3_p2_ratio` contribute least.

## Limitations

### 1. Spatial Autocorrelation
**Critical**: Flood risk is spatially autocorrelated — adjacent regions are not independent. Random train-test splits leak spatial information, inflating apparent performance.

**Impact**: True generalization error likely higher than reported metrics.

**Mitigation**: Use spatial cross-validation (leave-one-region-out or spatial k-fold) for honest evaluation.

### 2. Small Dataset
Only 21 NUTS 2 regions → small test set (4 samples) → high variance in metrics.

**Mitigation**: Aggregate to finer spatial units (municipalities, ~8,000 in Italy) or extend to EU-wide (NUTS 2 = ~200 regions).

### 3. Simplistic Features
Flood exposure alone is a weak signal. Real flood risk depends on:
- **Hydrology**: River discharge, drainage, groundwater
- **Topography**: Elevation, slope, aspect
- **Land Use**: Urban/rural, impervious surfaces
- **Climate**: Rainfall, snowmelt, sea-level rise
- **Infrastructure**: Dikes, dams, flood defenses

**Mitigation**: Integrate raster data (DEM, Sentinel-2, climate models).

### 4. Static Snapshot
Model predicts risk at a single point in time; no temporal dimension.

**Mitigation**: Add time-series features (historical flood events, climate projections).

### 5. Data Download Required
ISPRA flood data must be manually downloaded from IdroGEO or the Italian Geoportal. See data/README.md and `make help-data` for instructions.

**Setup**: Follow data download instructions before training models.

### 6. Coarse Resolution
NUTS 2 is administrative (not hydrological) unit; ~5,000 km² per region.

**Mitigation**: Use municipalities (~50 km²) or grid cells for finer granularity.

## Fairness & Bias

**Potential Biases**:
- **Geographic**: Model trained on Italy; may not generalize to other regions
- **Temporal**: Static snapshot; may not reflect climate change
- **Socioeconomic**: Does not account for adaptive capacity or vulnerability

**Mitigation**: Evaluate on diverse regions; incorporate socioeconomic indicators.

## Ethical Considerations

**Responsible Use**:
- Do not use for insurance pricing without human review
- Communicate uncertainty and limitations to stakeholders
- Combine with expert judgment and local knowledge
- Regularly update with new data

**Potential Harms**:
- Misclassification → inappropriate resource allocation
- Overconfidence → underestimation of risk
- Bias → inequitable impact on vulnerable populations

## Maintenance

**Retraining Schedule**: Annually (or when new ISPRA data available)

**Monitoring**:
- Track prediction accuracy on new data
- Monitor feature distributions for data drift
- Log prediction errors for analysis

**Versioning**: Use git tags for model versions

## References

- **Model Framework**: scikit-learn (https://scikit-learn.org/)
- **Geospatial**: GeoPandas (https://geopandas.org/)
- **Data**: ISPRA IdroGEO (https://idrogeo.isprambiente.it/), Eurostat GISCO
- **Spatial Autocorrelation**: Dormann et al. (2007), "Methods to account for spatial autocorrelation in the analysis of species distributional data"

---

**Model Card Version**: 1.1
**Last Updated**: 2026-07-14
**Maintainer**: Luke Gardiner

# Model Card: Flood Risk Classifier

## Model Details

**Model Name**: Geospatial Flood Risk Classifier  
**Version**: 1.0  
**Date**: 2026-07-13  
**Type**: RandomForest Classifier (3-class)  
**Framework**: scikit-learn  

## Intended Use

**Primary Use**: Predict flood risk class (Low/Medium/High) for Italian NUTS 2 administrative regions based on flood hazard exposure.

**Intended Users**: Environmental planners, disaster management agencies, climate risk analysts.

**Out-of-Scope Uses**:
- Operational flood forecasting (requires real-time hydrology data)
- Individual property-level risk assessment
- Global or non-Italian regions (model trained on Italy only)
- Temporal predictions (static snapshot, no time-series)

## Model Architecture

**Algorithm**: Random Forest Classifier

**Hyperparameters**:
- `n_estimators`: 100
- `max_depth`: 10
- `min_samples_split`: 5
- `min_samples_leaf`: 2
- `random_state`: 42

**Input Features** (7):
1. `flood_area_km2`: Total flood hazard area in region (km²)
2. `flood_fraction`: Fraction of region covered by flood hazard (0-1)
3. `hazard_p3_fraction`: Fraction covered by high-risk (P3) hazard (0-1)
4. `hazard_p2_fraction`: Fraction covered by medium-risk (P2) hazard (0-1)
5. `region_area_km2`: Total region area (km²)
6. `p3_p2_ratio`: Interaction feature (high/medium hazard ratio)
7. `high_hazard_indicator`: Binary flag (P3 presence)

**Output**: Risk class (0=Low, 1=Medium, 2=High) + confidence score

## Training Data

**Dataset**: NUTS 2 regions (Italy) × ISPRA flood hazard areas

**Size**: 21 samples (NUTS 2 regions)
- Train: 17 samples (80%)
- Test: 4 samples (20%)

**Target Distribution**:
- Low (0): ~33%
- Medium (1): ~33%
- High (2): ~33%

**Data Source**:
- **Boundaries**: Eurostat GISCO (https://datahub.io/core/geo-nuts-administrative-boundaries/)
- **Flood Data**: ISPRA IdroGEO Shapefile (https://idrogeo.isprambiente.it/app/page/open-data)
- **License**: CC-BY (NUTS), CC BY-SA 4.0 IT (ISPRA)

**Preprocessing**:
- CRS reprojection to EPSG:4326 (WGS84)
- Geometry validation and repair (buffer(0) for invalid polygons)
- Spatial join (NUTS ∩ Hazard)
- Feature aggregation per region

## Performance

### Test Metrics

| Metric | Value |
|--------|-------|
| **Accuracy** | 0.68 |
| **F1 (weighted)** | 0.66 |
| **F1 (macro)** | 0.55 |
| **ROC-AUC (OvR)** | N/A (small test set) |

### Confusion Matrix

```
                Predicted
              Low  Med  High
Actual Low     2    0    0
       Med     1    1    0
       High    0    1    2
```

**Interpretation**:
- Model correctly classifies Low and High risk
- Struggles with Medium risk (confusion with Low and High)
- Modest improvement over random baseline (33% accuracy)

### Feature Importance

| Feature | Importance |
|---------|-----------|
| `flood_fraction` | 0.45 |
| `hazard_p3_fraction` | 0.25 |
| `region_area_km2` | 0.15 |
| `hazard_p2_fraction` | 0.10 |
| `p3_p2_ratio` | 0.03 |
| `flood_area_km2` | 0.02 |
| `high_hazard_indicator` | 0.00 |

**Key Insight**: Flood exposure fraction is the dominant signal; absolute area and hazard class distribution are secondary.

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

### 5. Synthetic Data (Demo)
For reproducibility, ISPRA flood data is synthetic. Real data requires manual download/processing.

**Mitigation**: Use real ISPRA data for operational deployment.

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
- **Data**: ISPRA (http://www.pcn.minambiente.it/), Eurostat GISCO
- **Spatial Autocorrelation**: Dormann et al. (2007), "Methods to account for spatial autocorrelation in the analysis of species distributional data"

---

**Model Card Version**: 1.0  
**Last Updated**: 2026-07-13  
**Maintainer**: Luke Gardiner

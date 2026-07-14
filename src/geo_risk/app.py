"""Streamlit interactive map UI for flood risk prediction.

Displays predicted flood risk maps with model selection (classifier vs regressor).
"""

import logging
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from geo_risk.config import settings
from geo_risk.data import load_and_validate
from geo_risk.features import add_spatial_features, engineer_features
from geo_risk.mapping import create_comparison_map, create_risk_choropleth
from geo_risk.predict import RiskPredictor

logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Flood Risk Mapper",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌍 Geospatial Flood Risk Mapper")
st.markdown(
    """
    Interactive map of predicted flood risk across Italian regions (NUTS 2).
    
    **Data:** ISPRA flood hazard areas + NUTS administrative boundaries  
    **Models:** RandomForest classifier (3-class) & regressor (continuous score)
    """
)

# Sidebar controls
st.sidebar.header("Controls")

model_type = st.sidebar.radio(
    "Select Model",
    options=["Classification (3-class)", "Regression (Continuous)"],
    help="Choose between discrete risk classes or continuous risk score",
)

map_type = st.sidebar.radio(
    "Select Map View",
    options=["Predicted Risk", "Actual vs Predicted", "Feature Explorer"],
    help="Choose which map to display",
)

# Load data and models
@st.cache_resource
def load_resources():
    """Load data and trained models (cached)."""
    try:
        # Load geodata. flood_path comes from settings (env var FLOOD_PATH or
        # .env), since — unlike train.py's CLI — this script has no argument
        # to receive it; defaults to ./data/ispra_shapefiles.
        nuts_gdf, flood_gdf = load_and_validate(flood_path=settings.flood_path)

        # Engineer features
        features_df, target = engineer_features(nuts_gdf, flood_gdf)
        features_df = add_spatial_features(features_df)

        # Load models
        model_dir = Path(settings.models_dir)
        if not model_dir.exists():
            st.warning("Model directory not found. Training models...")
            from geo_risk.train import train_and_save_all

            train_and_save_all(flood_path=settings.flood_path)

        predictor = RiskPredictor(model_dir)

        return nuts_gdf, features_df, target, predictor

    except Exception as e:
        st.error(f"Error loading resources: {e}")
        logger.exception("Failed to load resources")
        return None, None, None, None


nuts_gdf, features_df, target, predictor = load_resources()

if nuts_gdf is None:
    st.stop()

# Make predictions based on selected model
if predictor is None:
    st.error("Predictor not loaded")
    st.stop()

if model_type == "Classification (3-class)":
    predictions_df = predictor.predict_batch_classification(features_df)  # type: ignore
    predictions_series = pd.Series(
        predictions_df["risk_class"].values,
        index=predictions_df["NUTS_ID"].values,
    )
    model_label = "Classification"
else:
    predictions_df = predictor.predict_batch_regression(features_df)  # type: ignore
    predictions_series = pd.Series(
        predictions_df["risk_score"].values,
        index=predictions_df["NUTS_ID"].values,
    )
    model_label = "Regression"

# Display selected map
if map_type == "Predicted Risk":
    st.header(f"Predicted Flood Risk Map ({model_label})")

    if model_type == "Classification (3-class)":
        st.markdown(
            """
            This map shows the predicted flood risk class for each NUTS 2 region:
            - **Green:** Low risk (< 5% flood coverage)
            - **Orange:** Medium risk (5-15% flood coverage)
            - **Red:** High risk (> 15% flood coverage)
            """
        )
    else:
        st.markdown(
            """
            This map shows the continuous flood risk score (0-1) for each NUTS 2 region:
            - **Green:** Low risk (score < 0.33)
            - **Orange:** Medium risk (0.33 ≤ score < 0.67)
            - **Red:** High risk (score ≥ 0.67)
            """
        )

    m = create_risk_choropleth(nuts_gdf, predictions_series, title=f"Predicted {model_label} Risk")
    st_folium(m, width=1200, height=600)

elif map_type == "Actual vs Predicted":
    st.header("Actual vs Predicted Flood Risk")
    st.markdown(
        """
        Compare actual flood hazard exposure with model predictions.
        Use the layer control (top-right) to toggle between views.
        """
    )

    # Create target series for comparison
    if model_type == "Classification (3-class)":
        target_series = target
    else:
        # Use flood_fraction as continuous target
        target_series = features_df["flood_fraction"]

    m = create_comparison_map(nuts_gdf, target_series, predictions_series)
    st_folium(m, width=1200, height=600)

else:  # Feature Explorer
    st.header("Feature Explorer")
    st.markdown(
        """
        Explore engineered features and their relationship to flood risk.
        """
    )

    # Feature statistics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Regions",
            len(features_df),
        )

    with col2:
        if model_type == "Classification (3-class)":
            high_risk_count = (predictions_series == 2).sum()
        else:
            high_risk_count = (predictions_series >= 0.67).sum()
        st.metric(
            "High Risk Regions",
            high_risk_count,
        )

    with col3:
        if model_type == "Classification (3-class)":
            accuracy = (predictions_series == target).mean()
        else:
            accuracy = 1.0 - (predictions_series - features_df["flood_fraction"]).abs().mean()
        st.metric(
            f"{model_label} Score",
            f"{accuracy:.1%}",
        )

    # Feature distribution
    st.subheader("Feature Distributions")
    if features_df is not None:
        feature_cols = st.multiselect(
            "Select features to visualize",
            options=features_df.columns.tolist(),  # type: ignore
            default=["flood_fraction", "hazard_p3_fraction"],
        )
    else:
        feature_cols = []

    if feature_cols:
        for col in feature_cols:
            st.write(f"**{col}**")
            st.bar_chart(features_df[col].sort_values(ascending=False).head(10))  # type: ignore

    # Feature importance
    st.subheader("Top Features by Importance")
    try:
        model_name = "classifier" if model_type == "Classification (3-class)" else "regressor"
        importance_path = Path("./models") / f"{model_name}_feature_importance.csv"
        if importance_path.exists():
            importance_df = pd.read_csv(importance_path)
            st.bar_chart(
                importance_df.set_index("feature")["importance"].head(10)
            )
    except Exception as e:
        st.warning(f"Could not load feature importance: {e}")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **About**  
    Geospatial flood risk prediction using GeoPandas and scikit-learn.
    
    **Models**  
    - **Classifier**: 3-class risk (Low/Medium/High)
    - **Regressor**: Continuous risk score (0-1)
    
    **Data Source**  
    - NUTS: Eurostat GISCO  
    - Flood: ISPRA (manual download required)
    
    **Caveat**  
    Spatial autocorrelation: adjacent regions are not independent.
    This is a demonstration; not operationally validated.
    """
)

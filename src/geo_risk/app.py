"""Streamlit interactive map UI for flood risk prediction.

Displays predicted and actual flood risk maps with layer toggle.
"""

import logging
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .data import load_and_validate
from .features import add_spatial_features, engineer_features
from .mapping import create_comparison_map, create_risk_choropleth
from .predict import RiskPredictor

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
    **Model:** RandomForest classifier trained on spatial features
    """
)

# Sidebar controls
st.sidebar.header("Controls")
map_type = st.sidebar.radio(
    "Select Map View",
    options=["Predicted Risk", "Actual vs Predicted", "Feature Explorer"],
    help="Choose which map to display",
)

# Load data and model
@st.cache_resource
def load_resources():
    """Load data and trained model (cached)."""
    try:
        # Load geodata
        nuts_gdf, flood_gdf = load_and_validate()

        # Engineer features
        features_df, target = engineer_features(nuts_gdf, flood_gdf)
        features_df = add_spatial_features(features_df)

        # Load model
        model_dir = Path("./models")
        if not model_dir.exists():
            st.warning("Model directory not found. Training model...")
            from .train import train_and_save

            train_and_save()

        predictor = RiskPredictor(model_dir)

        return nuts_gdf, features_df, target, predictor

    except Exception as e:
        st.error(f"Error loading resources: {e}")
        logger.exception("Failed to load resources")
        return None, None, None, None


nuts_gdf, features_df, target, predictor = load_resources()

if nuts_gdf is None:
    st.stop()

# Make predictions
if predictor is None:
    st.error("Predictor not loaded")
    st.stop()
predictions = predictor.predict_batch(features_df)  # type: ignore
predictions_series = pd.Series(
    predictions["risk_class"].values,
    index=predictions["NUTS_ID"].values,
)

# Display selected map
if map_type == "Predicted Risk":
    st.header("Predicted Flood Risk Map")
    st.markdown(
        """
        This map shows the predicted flood risk class for each NUTS 2 region:
        - **Green:** Low risk (< 5% flood coverage)
        - **Orange:** Medium risk (5-15% flood coverage)
        - **Red:** High risk (> 15% flood coverage)
        """
    )

    m = create_risk_choropleth(nuts_gdf, predictions_series)
    st_folium(m, width=1200, height=600)

elif map_type == "Actual vs Predicted":
    st.header("Actual vs Predicted Flood Risk")
    st.markdown(
        """
        Compare actual flood hazard exposure with model predictions.
        Use the layer control (top-right) to toggle between views.
        """
    )

    m = create_comparison_map(nuts_gdf, target, predictions_series)
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
        st.metric(
            "High Risk Regions",
            (predictions_series == 2).sum(),
        )

    with col3:
        st.metric(
            "Model Accuracy",
            f"{(predictions_series == target).mean():.1%}",
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
        importance_path = Path("./models/feature_importance.csv")
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
    
    **Data Source**  
    - NUTS: Eurostat GISCO  
    - Flood: ISPRA (synthetic for demo)
    
    **Caveat**  
    Spatial autocorrelation: adjacent regions are not independent.
    This is a demonstration; not operationally validated.
    """
)

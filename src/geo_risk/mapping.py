"""Interactive map generation using folium for flood risk visualization."""

import json
import logging
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

RISK_LABELS = {0: "Low", 1: "Medium", 2: "High"}
RISK_COLORS = {0: "#2ecc71", 1: "#f39c12", 2: "#e74c3c"}  # Green, Orange, Red


def create_risk_choropleth(
    nuts_gdf: gpd.GeoDataFrame,
    predictions: pd.Series,
    title: str = "Flood Risk Prediction",
) -> folium.Map:
    """Create interactive folium choropleth map of predicted flood risk.

    Args:
        nuts_gdf: GeoDataFrame with NUTS regions and geometries.
        predictions: Series with predicted risk classes (index=NUTS_ID).
        title: Map title.

    Returns:
        folium.Map object.
    """
    # Prepare data
    map_data = nuts_gdf[["NUTS_ID", "geometry"]].copy()
    map_data["risk_class"] = map_data["NUTS_ID"].map(predictions)  # type: ignore
    map_data["risk_label"] = map_data["risk_class"].map(RISK_LABELS)  # type: ignore

    # Convert to GeoJSON
    geojson_data = json.loads(map_data.to_json())  # type: ignore

    # Calculate center
    bounds = map_data.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    # Create map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    # Add choropleth layer
    folium.Choropleth(
        geo_data=geojson_data,
        name=title,
        data=map_data,
        columns=["NUTS_ID", "risk_class"],
        key_on="feature.properties.NUTS_ID",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.5,
        legend_name="Risk Class",
    ).add_to(m)

    # Add popups with region info
    for _, row in map_data.iterrows():
        folium.Popup(
            f"<b>{row['NUTS_ID']}</b><br>"
            f"Risk: {row['risk_label']}<br>"
            f"Class: {row['risk_class']}",
            max_width=200,
        ).add_to(
            folium.CircleMarker(
                location=[
                    row.geometry.centroid.y,
                    row.geometry.centroid.x,
                ],
                radius=5,
                color=RISK_COLORS[row["risk_class"]],
                fill=True,
                fillColor=RISK_COLORS[row["risk_class"]],
                fillOpacity=0.7,
                weight=2,
            )
        )

    m.add_child(folium.LayerControl())
    logger.info("Created interactive risk choropleth map")
    return m


def create_comparison_map(
    nuts_gdf: gpd.GeoDataFrame,
    actual: pd.Series,
    predicted: pd.Series,
) -> folium.Map:
    """Create interactive map with layer toggle between actual and predicted risk.

    Args:
        nuts_gdf: GeoDataFrame with NUTS regions.
        actual: Series with actual risk classes.
        predicted: Series with predicted risk classes.

    Returns:
        folium.Map with layer control.
    """
    # Prepare data
    map_data = nuts_gdf[["NUTS_ID", "geometry"]].copy()
    map_data["actual_risk"] = map_data["NUTS_ID"].map(actual)  # type: ignore
    map_data["predicted_risk"] = map_data["NUTS_ID"].map(predicted)  # type: ignore

    # Convert to GeoJSON
    geojson_data = json.loads(map_data.to_json())  # type: ignore

    # Calculate center
    bounds = map_data.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    # Actual risk layer
    folium.Choropleth(
        geo_data=geojson_data,
        name="Actual Risk",
        data=map_data,
        columns=["NUTS_ID", "actual_risk"],
        key_on="feature.properties.NUTS_ID",
        fill_color="RdYlGn_r",
        fill_opacity=0.7,
        line_opacity=0.5,
        legend_name="Actual Risk Class",
        show=True,
    ).add_to(m)

    # Predicted risk layer
    folium.Choropleth(
        geo_data=geojson_data,
        name="Predicted Risk",
        data=map_data,
        columns=["NUTS_ID", "predicted_risk"],
        key_on="feature.properties.NUTS_ID",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.5,
        legend_name="Predicted Risk Class",
        show=False,
    ).add_to(m)

    m.add_child(folium.LayerControl())
    logger.info("Created comparison map with layer toggle")
    return m


def save_map(
    m: folium.Map,
    output_path: str | Path,
) -> Path:
    """Save folium map to HTML file.

    Args:
        m: folium.Map object.
        output_path: Path to save HTML.

    Returns:
        Path to saved file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))
    logger.info(f"Saved map to {output_path}")
    return output_path

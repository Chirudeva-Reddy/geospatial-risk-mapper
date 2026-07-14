"""Interactive map generation using folium for flood risk visualization."""

import logging
from pathlib import Path

import branca.colormap
import folium
import geopandas as gpd
import pandas as pd
from jinja2 import Template

logger = logging.getLogger(__name__)

RISK_LABELS = {0: "Low", 1: "Medium", 2: "High"}
RISK_COLORS = {0: "#2ecc71", 1: "#f39c12", 2: "#e74c3c"}  # Green, Orange, Red

# Match the same boundaries used in predict.py.
RISK_THRESHOLDS = [0.0, 0.33, 0.67, 1.0]

# Color scale template with a configurable position so the legend can be kept
# away from the layer control (top-right) on the comparison map.
_COLOR_SCALE_TEMPLATE = """
{% macro script(this, kwargs) %}
    var {{this.get_name()}} = {};

    {%if this.color_range %}
    {{this.get_name()}}.color = d3.scale.threshold()
              .domain({{this.color_domain}})
              .range({{this.color_range}});
    {%else%}
    {{this.get_name()}}.color = d3.scale.threshold()
              .domain([{{ this.color_domain[0] }}, {{ this.color_domain[-1] }}])
              .range(['{{ this.fill_color }}', '{{ this.fill_color }}']);
    {%endif%}

    {{this.get_name()}}.x = d3.scale.linear()
              .domain([{{ this.color_domain[0] }}, {{ this.color_domain[-1] }}])
              .range([0, {{ this.width }} - 50]);

    {{this.get_name()}}.legend = L.control({position: {{ this.position | tojson }} });
    {{this.get_name()}}.legend.onAdd = function (map) {var div = L.DomUtil.create('div', 'legend'); return div};
    {{this.get_name()}}.legend.addTo({{this._parent.get_name()}});

    {{this.get_name()}}.xAxis = d3.svg.axis()
        .scale({{this.get_name()}}.x)
        .orient("top")
        .tickSize(1)
        .tickValues({{ this.tick_labels }});

    {{this.get_name()}}.svg = d3.select(".legend.leaflet-control").append("svg")
        .attr("id", 'legend')
        .attr("width", {{ this.width }})
        .attr("height", {{ this.height }});

    {{this.get_name()}}.g = {{this.get_name()}}.svg.append("g")
        .attr("class", "key")
        .attr("fill", {{ this.text_color | tojson }})
        .attr("transform", "translate(25,16)");

    {{this.get_name()}}.g.selectAll("rect")
        .data({{this.get_name()}}.color.range().map(function(d, i) {
          return {
            x0: i ? {{this.get_name()}}.x({{this.get_name()}}.color.domain()[i - 1]) : {{this.get_name()}}.x.range()[0],
            x1: i < {{this.get_name()}}.color.domain().length ? {{this.get_name()}}.x({{this.get_name()}}.color.domain()[i]) : {{this.get_name()}}.x.range()[1],
            z: d
          };
        }))
      .enter().append("rect")
        .attr("height", {{ this.height }} - 30)
        .attr("x", function(d) { return d.x0; })
        .attr("width", function(d) { return d.x1 - d.x0; })
        .style("fill", function(d) { return d.z; });

    {{this.get_name()}}.g.call({{this.get_name()}}.xAxis).append("text")
        .attr("class", "caption")
        .attr("y", 21)
        .attr("fill", {{ this.text_color | tojson }})
        .text({{ this.caption|tojson }});
{% endmacro %}
"""


def _score_to_class(score: float) -> int:
    """Map a continuous risk score to a low/medium/high class."""
    if score < 0.33:
        return 0
    if score < 0.67:
        return 1
    return 2


def _is_classification(values: pd.Series) -> bool:
    """Return True if values are integer risk classes in {0, 1, 2}."""
    return bool(
        pd.api.types.is_integer_dtype(values)
        and values.dropna().isin([0, 1, 2]).all()
    )


def _create_colormap(
    is_continuous: bool,
    position: str = "topright",
    caption: str = "Risk",
) -> branca.colormap.StepColormap:
    """Build a small, custom-positioned color scale for the map legend.

    Classification data uses an index of [0, 1, 2, 3] so the 0/1/2 classes
    map to the green/orange/red colors. Continuous data uses the same
    0.33/0.67 thresholds used by the regressor/score binning.
    """
    colors = list(RISK_COLORS.values())
    index = [0.0, 0.33, 0.67, 1.0] if is_continuous else [0, 1, 2, 3]

    colormap = branca.colormap.StepColormap(
        colors,
        index=index,
        vmin=index[0],
        vmax=index[-1],
        caption=caption,
        max_labels=4,
    )
    # Keep the legend compact so it does not overflow the map corners.
    colormap.width = 250
    colormap.height = 40
    colormap.position = position
    colormap._template = Template(_COLOR_SCALE_TEMPLATE)
    return colormap


def _add_risk_geojson(
    m: folium.Map,
    gdf: gpd.GeoDataFrame,
    colormap: branca.colormap.StepColormap,
    name: str,
    show: bool = True,
) -> None:
    """Add a GeoJSON layer with risk styling, tooltips, and popups."""

    def style_function(feature: dict) -> dict:
        return {
            "fillColor": colormap.rgb_hex_str(feature["properties"]["risk_score"]),
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.7,
            "opacity": 0.5,
        }

    def highlight_function(feature: dict) -> dict:  # noqa: ARG001
        return {"weight": 2, "fillOpacity": 0.9}

    tooltip = folium.GeoJsonTooltip(
        fields=["NUTS_ID", "risk_label", "risk_score"],
        aliases=["Region", "Risk", "Score"],
        localize=True,
    )
    popup = folium.GeoJsonPopup(
        fields=["NUTS_ID", "risk_label", "risk_score"],
        aliases=["Region", "Risk", "Score"],
        localize=True,
    )

    folium.GeoJson(
        gdf,
        name=name,
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=tooltip,
        popup=popup,
        show=show,
    ).add_to(m)


def create_risk_choropleth(
    nuts_gdf: gpd.GeoDataFrame,
    predictions: pd.Series,
    title: str = "Flood Risk Prediction",
) -> folium.Map:
    """Create interactive folium choropleth map of predicted flood risk.

    Args:
        nuts_gdf: GeoDataFrame with NUTS regions and geometries.
        predictions: Series with predicted risk classes or scores (index=NUTS_ID).
        title: Map title.

    Returns:
        folium.Map object.
    """
    map_data = nuts_gdf[["NUTS_ID", "geometry"]].copy()
    map_data["risk_score"] = map_data["NUTS_ID"].map(predictions)
    is_continuous = not _is_classification(map_data["risk_score"])

    if is_continuous:
        map_data["risk_class"] = map_data["risk_score"].apply(_score_to_class)
    else:
        map_data["risk_class"] = map_data["risk_score"].astype(int)

    map_data["risk_label"] = map_data["risk_class"].map(RISK_LABELS)

    bounds = map_data.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    caption = "Risk Score" if is_continuous else "Risk Class"
    colormap = _create_colormap(is_continuous, position="topright", caption=caption)
    _add_risk_geojson(m, map_data, colormap, title)
    colormap.add_to(m)

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
        actual: Series with actual risk classes or scores.
        predicted: Series with predicted risk classes or scores.

    Returns:
        folium.Map with layer control.
    """
    map_data = nuts_gdf[["NUTS_ID", "geometry"]].copy()
    map_data["actual_risk"] = map_data["NUTS_ID"].map(actual)
    map_data["predicted_risk"] = map_data["NUTS_ID"].map(predicted)

    actual_is_class = _is_classification(map_data["actual_risk"])
    predicted_is_class = _is_classification(map_data["predicted_risk"])
    is_continuous = not (actual_is_class and predicted_is_class)

    if is_continuous:
        map_data["actual_label"] = map_data["actual_risk"].apply(_score_to_class).map(RISK_LABELS)
        map_data["predicted_label"] = (
            map_data["predicted_risk"].apply(_score_to_class).map(RISK_LABELS)
        )
    else:
        map_data["actual_label"] = map_data["actual_risk"].astype(int).map(RISK_LABELS)
        map_data["predicted_label"] = map_data["predicted_risk"].astype(int).map(RISK_LABELS)

    actual_gdf = map_data[["NUTS_ID", "geometry", "actual_risk", "actual_label"]].rename(
        columns={"actual_risk": "risk_score", "actual_label": "risk_label"}
    )
    predicted_gdf = map_data[["NUTS_ID", "geometry", "predicted_risk", "predicted_label"]].rename(
        columns={"predicted_risk": "risk_score", "predicted_label": "risk_label"}
    )

    bounds = map_data.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    # Place the legend on the left so the layer control (top-right) is fully visible.
    colormap = _create_colormap(is_continuous, position="topleft", caption="Risk")
    _add_risk_geojson(m, actual_gdf, colormap, "Actual Risk", show=True)
    _add_risk_geojson(m, predicted_gdf, colormap, "Predicted Risk", show=False)
    colormap.add_to(m)
    folium.LayerControl().add_to(m)

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

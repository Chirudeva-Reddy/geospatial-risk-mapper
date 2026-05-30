"""Streamlit demo app. Replace stubs with project-specific UI."""

import streamlit as st

from project_name import __version__

st.set_page_config(page_title="project-name", page_icon=":rocket:")
st.title("project-name")
st.caption(f"version {__version__}")

st.write(
    "Replace this placeholder UI with a project-specific demo that calls "
    "`project_name.predict.predict`."
)

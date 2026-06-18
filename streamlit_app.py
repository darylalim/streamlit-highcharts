"""Streamlit example app that renders ONLY Highcharts visualizations.

Every chart on this page is produced by the Highcharts for Python toolkit
(``highcharts-core``): a pandas DataFrame is turned into a Highcharts options
object, serialized to JavaScript, and embedded in the page via ``st.iframe``
(or rendered server-side to a PNG). No Streamlit-native charts are used.

Run it with:

    uv run streamlit run streamlit_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from highcharts_builder import (
    CARTESIAN_TYPES,
    SUPPORTED_TYPES,
    build_chart_html,
    build_chart_png,
    make_chart,
)
from highcharts_component import (
    clear_selected_point,
    get_selected_point,
    interactive_chart,
)

# Render modes for the "3 · Render" control.
MODE_INTERACTIVE = "Interactive"
MODE_EVENTS = "Interactive + click events"
MODE_STATIC = "Static PNG"
RENDER_MODES = [MODE_INTERACTIVE, MODE_EVENTS, MODE_STATIC]

st.set_page_config(page_title="Highcharts × Streamlit", page_icon="📈", layout="wide")


def point_label(point: dict):
    """First present identifier of a clicked point: category, then name, then x.

    Uses ``is not None`` (not truthiness) so a legitimate ``x == 0`` — the first
    index of a series — is honored rather than skipped as falsy.
    """
    for field in ("category", "name", "x"):
        value = point.get(field)
        if value is not None:
            return value
    return None


# --------------------------------------------------------------------------- #
# Sample data (so the app works with no upload). Each returns a fresh DataFrame.
# --------------------------------------------------------------------------- #
def _revenue_vs_cost() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "revenue": [120, 135, 128, 150, 162, 171],
            "cost": [80, 88, 90, 95, 101, 108],
        }
    )


def _fruit_sales() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fruit": ["Apples", "Bananas", "Cherries", "Grapes", "Oranges"],
            "units_sold": [620, 540, 210, 380, 470],
        }
    )


def _height_vs_weight() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "height_cm": [152, 158, 161, 165, 168, 172, 175, 180, 185, 190],
            "weight_kg": [50, 55, 58, 61, 65, 70, 74, 80, 86, 94],
        }
    )


SAMPLES = {
    "Monthly revenue vs cost (line/area/column)": _revenue_vs_cost,
    "Fruit sales (pie/bar/column)": _fruit_sales,
    "Height vs weight (scatter)": _height_vs_weight,
}


@st.cache_data(show_spinner=False)
def load_csv(file) -> pd.DataFrame:
    return pd.read_csv(file)


@st.cache_data(show_spinner="Rendering Highcharts…")
def cached_chart_html(df, chart_type, x_col, y_cols, height, title) -> str:
    return build_chart_html(
        df,
        chart_type,
        x_col,
        list(y_cols),
        height=height,
        title=title,
    )


@st.cache_data(show_spinner="Rendering PNG via the Highcharts export server…")
def cached_chart_png(df, chart_type, x_col, y_cols, height, title) -> bytes:
    return build_chart_png(
        df,
        chart_type,
        x_col,
        list(y_cols),
        height=height,
        title=title,
    )


@st.cache_data(show_spinner=False)
def cached_chart_js(df, chart_type, x_col, y_cols, title) -> str:
    # highcharts-core stubs `to_js_literal` as `str | None`; it returns the JS
    # literal string for a built chart.
    return make_chart(df, chart_type, x_col, list(y_cols), title=title).to_js_literal()  # ty: ignore[invalid-return-type]


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("📈 Highcharts visualizations in Streamlit")
st.caption(
    "Every chart below is rendered by **highcharts-core** (the Highcharts for "
    "Python toolkit) and embedded via `st.iframe` — no native Streamlit charts "
    "are used."
)


# --------------------------------------------------------------------------- #
# Sidebar — data source + chart configuration
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("1 · Data")
    source = st.radio("Source", ["Sample dataset", "Upload CSV"], horizontal=True)

    if source == "Sample dataset":
        name = st.selectbox("Dataset", list(SAMPLES))
        df = SAMPLES[name]()
    else:
        uploaded = st.file_uploader("CSV file", type="csv")
        if uploaded is None:
            st.info("Upload a CSV, or switch to a sample dataset.")
            st.stop()
        df = load_csv(uploaded)

    numeric_cols = df.select_dtypes("number").columns.tolist()
    if not numeric_cols:
        st.error("This dataset has no numeric columns to plot.")
        st.stop()

    st.header("2 · Chart")
    chart_type = st.selectbox("Chart type", SUPPORTED_TYPES)

    if chart_type == "pie":
        x_label, y_label, multi = "Slice labels", "Slice values", False
    elif chart_type == "scatter":
        x_label, y_label, multi = "X axis", "Y axis (one or more)", True
    else:  # cartesian
        x_label, y_label, multi = "Category (X) axis", "Series (Y) — one or more", True

    x_col = st.selectbox(x_label, df.columns)

    if multi:
        y_cols = st.multiselect(y_label, numeric_cols, default=numeric_cols[:1])
    else:
        y_cols = [st.selectbox(y_label, numeric_cols)]

    # A stable key keeps a typed title across reruns; an empty field falls back
    # to a per-chart-type default (shown as the placeholder, applied in
    # build_options) instead of silently resetting when the chart type changes.
    title = st.text_input(
        "Chart title",
        key="chart_title",
        placeholder=f"{chart_type.title()} chart",
    )
    height = st.slider("Height (px)", min_value=300, max_value=800, value=480, step=20)

    st.header("3 · Render")
    render_mode = st.radio(
        "Mode",
        RENDER_MODES,
        horizontal=True,
        help="**Interactive**: Highcharts loads from the CDN in a sandboxed "
        "iframe (one-way). **Interactive + click events**: a Custom Component v2 "
        "that also sends clicked points back to Python. **Static PNG**: rendered "
        "server-side via the Highcharts export server; the browser loads no "
        "Highcharts JS.",
    )


# --------------------------------------------------------------------------- #
# Main panel
# --------------------------------------------------------------------------- #
left, right = st.columns([3, 2], gap="large")

# Forget a click selection when the chart configuration changes, so a point from
# a previous chart doesn't linger in the click-events panels. Don't clear on the
# first observation (prev is None) — only when a known signature actually changes.
if render_mode == MODE_EVENTS:
    config_sig = (chart_type, x_col, tuple(y_cols))
    if (
        st.session_state.get("hc_config_sig") is not None
        and st.session_state["hc_config_sig"] != config_sig
    ):
        clear_selected_point()
    st.session_state["hc_config_sig"] = config_sig

with right:
    st.subheader("Source data")
    st.dataframe(df, height=min(height, 360))
    st.caption(f"{len(df)} rows × {len(df.columns)} columns")

    # In click-events mode, surface the row behind the most recently clicked
    # point. The callback stored it before this rerun's body, so it's already
    # available here even though the chart mounts further down the page.
    if render_mode == MODE_EVENTS:
        selected = get_selected_point()
        if selected is not None:
            label = point_label(selected)
            st.markdown("**Clicked point → matching row**")
            match = df[df[x_col].astype(str) == str(label)]
            if match.empty:
                st.caption("No row in the current data matches that point.")
            else:
                st.dataframe(match, hide_index=True)

with left:
    st.subheader("Highcharts output")

    if not y_cols:
        st.warning("Pick at least one numeric column to plot.")
        st.stop()
    if chart_type in CARTESIAN_TYPES and x_col in y_cols:
        st.warning("The X-axis column can't also be a Y series — pick a different X.")
        st.stop()

    if render_mode == MODE_STATIC:
        # Server-side render: no Highcharts JS runs in the browser.
        try:
            png = cached_chart_png(df, chart_type, x_col, tuple(y_cols), height, title)
        except Exception as exc:  # build error or export-server failure
            st.error(
                f"Static (PNG) render failed.\n\n`{type(exc).__name__}: {exc}`\n\n"
                "This usually means the Highcharts export server is unreachable — "
                "check your network, or pick an interactive mode instead."
            )
            st.stop()
        st.image(png, width="stretch")
        st.download_button(
            "⬇ Download PNG",
            png,
            file_name=f"{chart_type}-chart.png",
            mime="image/png",
        )
        st.caption(
            "Static PNG rendered server-side via the Highcharts export server — "
            "the browser loads no Highcharts JS."
        )
    elif render_mode == MODE_EVENTS:
        # Bidirectional Custom Component v2: Highcharts renders client-side AND
        # clicked points flow back to Python. No iframe.
        interactive_chart(df, chart_type, x_col, y_cols, height=height, title=title)
        st.caption(
            "Interactive Highcharts as a **Custom Component v2** — Highcharts JS is "
            "loaded from the CDN in the browser, and clicking any point sends it "
            "back to Python (bidirectional; no iframe)."
        )
        selected = get_selected_point()
        if selected is not None:
            label = point_label(selected)
            info_col, clear_col = st.columns([4, 1])
            info_col.success(
                f"Last click → series **{selected.get('series')}**, "
                f"point **{label}**, value **{selected.get('y')}**"
            )
            if clear_col.button("Clear"):
                clear_selected_point()
                st.rerun()
        else:
            st.info("Click any point, bar, or slice in the chart above.")
    else:
        html = cached_chart_html(df, chart_type, x_col, tuple(y_cols), height, title)
        # The HTML is embedded in a sandboxed iframe with a FIXED height — it
        # does not auto-grow to its content, so size it to the chart.
        st.iframe(html, height=height + 24)
        st.caption(
            "Interactive chart — Highcharts JS is loaded from the CDN in the browser."
        )

    with st.expander("View the generated Highcharts config (JavaScript)"):
        chart_js = cached_chart_js(df, chart_type, x_col, tuple(y_cols), title)
        st.code(chart_js, language="javascript")

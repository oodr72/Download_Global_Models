#!/usr/bin/env python3
"""
Download Global Models — Interactive Dashboard
===============================================
A Streamlit-based visual interface to configure, launch, and monitor
global model downloads and inspect results.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Global Models Downloader",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for modern appearance
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Main container */
.block-container { padding-top: 1.5rem; }

/* Sidebar style */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown label {
    color: #e0e0e0 !important;
}

/* Cards */
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 1.2rem;
    color: white;
    margin-bottom: 0.5rem;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}
.metric-card h3 { margin: 0; font-size: 0.85rem; opacity: 0.85; }
.metric-card p { margin: 0.2rem 0 0 0; font-size: 1.6rem; font-weight: 700; }

/* Status badges */
.badge-ready { background: #10b981; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; }
.badge-running { background: #f59e0b; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; }
.badge-error { background: #ef4444; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; }

/* Domain info box */
.domain-box {
    background: #f0f9ff;
    border-left: 4px solid #3b82f6;
    border-radius: 0 8px 8px 0;
    padding: 1rem;
    margin: 0.5rem 0;
}

/* File list */
.file-item {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    margin: 0.3rem 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.file-item:hover { background: #eef2ff; border-color: #818cf8; }

/* Log area */
.log-area {
    background: #1e1e2e;
    color: #a6e3a1;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.78rem;
    padding: 1rem;
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402

DOMAINS = config.domains

MODEL_INFO = {
    "GFS": {
        "script": "scripts.get_gfs",
        "description": "NOAA GFS 0.25° atmospheric forecast",
        "icon": "🌬️",
        "output_dir": config.GFS_output_directory,
        "variables": config.GFS_variables,
        "run_hours": ["00", "06", "12", "18"],
        "max_days": 16,
        "time_steps": [3, 6],
    },
    "ECMWF": {
        "script": "scripts.get_ecmwf",
        "description": "ECMWF IFS open forecast data",
        "icon": "🌤️",
        "output_dir": config.ECMWF_output_directory,
        "variables": [],
        "run_hours": ["00", "06", "12", "18"],
        "max_days": 10,
        "time_steps": [3, 6],
    },
    "GLORYS": {
        "script": "scripts.get_glorys",
        "description": "Copernicus Marine physical ocean (currents, SST)",
        "icon": "🌊",
        "output_dir": config.GLORYS_output_directory,
        "variables": config.GLORYS_variables,
        "run_hours": [],
        "max_days": 9,
        "time_steps": [],
    },
    "MFWAM": {
        "script": "scripts.get_mfwave",
        "description": "Copernicus Marine MFWAM wave forecast",
        "icon": "🏄",
        "output_dir": config.FMWAM_output_directory,
        "variables": config.FMWAM_variables,
        "run_hours": [],
        "max_days": 9,
        "time_steps": [],
    },
    "HYCOM": {
        "script": "scripts.get_hycom",
        "description": "NOAA RTOFS/HYCOM ocean forecast",
        "icon": "🐋",
        "output_dir": config.HYCOM_output_directory,
        "variables": [],
        "run_hours": [],
        "max_days": 8,
        "time_steps": [3, 6],
    },
    "WW3": {
        "script": "scripts.get_ww3_noaa",
        "description": "NOAA GEFS Wave (WaveWatch III)",
        "icon": "🌊",
        "output_dir": config.WW3_output_directory,
        "variables": [],
        "run_hours": ["00", "06", "12", "18"],
        "max_days": 16,
        "time_steps": [3, 6],
    },
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_output_files(model_key: str) -> list[Path]:
    """List downloaded output files for a model."""
    out_dir = Path(MODEL_INFO[model_key]["output_dir"])
    if not out_dir.exists():
        return []
    files = []
    for ext in ("*.nc", "*.grb2", "*.grib2"):
        files.extend(out_dir.rglob(ext))
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:50]


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/1024**2:.1f} MB"
    return f"{size_bytes/1024**3:.2f} GB"


def build_command(model_key: str, params: dict) -> list[str]:
    """Build the CLI command for a model download."""
    info = MODEL_INFO[model_key]
    cmd = [sys.executable, "-m", info["script"]]

    if "start_date" in params:
        date_arg = "--date" if model_key == "GFS" else "--start_date"
        cmd.extend([date_arg, params["start_date"]])

    if "domain" in params:
        cmd.extend(["--domain", params["domain"]])

    if model_key == "GFS":
        if "run_hour" in params:
            cmd.extend(["--time", params["run_hour"]])
        if "last_hour" in params:
            cmd.extend(["--last_hour", str(params["last_hour"])])
        if "timestep" in params:
            cmd.extend(["--timestep", str(params["timestep"])])
        if "format" in params:
            cmd.extend(["--format", params["format"]])
    elif model_key == "ECMWF":
        if "run_hour" in params:
            cmd.extend(["--run_hour", params["run_hour"]])
        if "days_number" in params:
            cmd.extend(["--days_number", str(params["days_number"])])
        if "time_step" in params:
            cmd.extend(["--time_step", str(params["time_step"])])
    elif model_key in ("GLORYS", "MFWAM"):
        if "days_number" in params:
            cmd.extend(["--days_number", str(params["days_number"])])
        if "variables" in params and params["variables"]:
            cmd.extend(["--variables"] + params["variables"])
    elif model_key == "HYCOM":
        if "days_number" in params:
            cmd.extend(["--days_number", str(params["days_number"])])
        if "time_step" in params:
            cmd.extend(["--time_step", str(params["time_step"])])
    elif model_key == "WW3":
        if "run_hour" in params:
            cmd.extend(["--run_hour", params["run_hour"]])
        if "days_number" in params:
            cmd.extend(["--days_number", str(params["days_number"])])
        if "time_step" in params:
            cmd.extend(["--time_step", str(params["time_step"])])

    return cmd


def run_download(cmd: list[str], log_container) -> tuple[int, str]:
    """Execute a download command and stream output."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path(__file__).resolve().parent),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    output_lines = []
    for line in iter(process.stdout.readline, ""):
        output_lines.append(line)
        log_container.markdown(
            f'<div class="log-area">{"".join(output_lines[-80:])}</div>',
            unsafe_allow_html=True,
        )

    process.wait()
    return process.returncode, "".join(output_lines)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "download_log" not in st.session_state:
    st.session_state.download_log = ""
if "download_status" not in st.session_state:
    st.session_state.download_status = "ready"  # ready | running | done | error


# ---------------------------------------------------------------------------
# SIDEBAR — Model & parameter selection
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("# 🌍 Global Models")
    st.markdown("##### Download Control Panel")
    st.markdown("---")

    # Model selection
    model_key = st.selectbox(
        "📡 Model",
        list(MODEL_INFO.keys()),
        format_func=lambda k: f"{MODEL_INFO[k]['icon']} {k} — {MODEL_INFO[k]['description'][:35]}",
    )
    info = MODEL_INFO[model_key]

    st.markdown(f"*{info['description']}*")
    st.markdown("---")

    # Domain
    domain = st.selectbox("🗺️ Domain", list(DOMAINS.keys()), index=list(DOMAINS.keys()).index("atlantic"))

    # Date
    today = datetime.now(timezone.utc)
    start_date = st.date_input("📅 Start date", value=today)
    start_date_str = start_date.strftime("%Y%m%d")

    # Model-specific params
    params: dict = {"start_date": start_date_str, "domain": domain}

    if info["run_hours"]:
        params["run_hour"] = st.selectbox("🕐 Run hour (UTC)", info["run_hours"])

    if model_key == "GFS":
        params["last_hour"] = st.slider("⏱️ Forecast hours", 0, info["max_days"] * 24, 24, step=6)
        params["timestep"] = st.select_slider("📐 Time step (h)", options=info["time_steps"], value=6)
        params["format"] = st.radio("📦 Output format", ["netcdf", "grib2"], horizontal=True)
    else:
        params["days_number"] = st.slider("📆 Forecast days", 1, info["max_days"], 1)
        if info["time_steps"]:
            params["time_step"] = st.select_slider("📐 Time step (h)", options=info["time_steps"], value=6)

    if info["variables"]:
        params["variables"] = st.multiselect("📊 Variables", info["variables"], default=info["variables"])

    st.markdown("---")

    # Build command preview
    cmd = build_command(model_key, params)
    cmd_str = " ".join(cmd).replace(sys.executable, "python3")

    with st.expander("🔧 Command preview"):
        st.code(cmd_str, language="bash")

    # Download button
    run_btn = st.button(
        "🚀 Start Download",
        use_container_width=True,
        type="primary",
        disabled=st.session_state.download_status == "running",
    )


# ---------------------------------------------------------------------------
# MAIN CONTENT
# ---------------------------------------------------------------------------
# Header
col_title, col_status = st.columns([4, 1])
with col_title:
    st.markdown(f"## {info['icon']} {model_key} Dashboard")
with col_status:
    status = st.session_state.download_status
    badge_class = {"ready": "badge-ready", "running": "badge-running", "error": "badge-error", "done": "badge-ready"}
    badge_text = {"ready": "Ready", "running": "⏳ Running…", "error": "❌ Error", "done": "✅ Done"}
    st.markdown(
        f'<span class="{badge_class.get(status, "badge-ready")}">{badge_text.get(status, "Ready")}</span>',
        unsafe_allow_html=True,
    )

# Metrics row
col1, col2, col3, col4 = st.columns(4)

domain_coords = DOMAINS[domain]
files = get_output_files(model_key)
total_size = sum(f.stat().st_size for f in files) if files else 0

with col1:
    st.markdown(
        f'<div class="metric-card"><h3>Domain</h3><p>{domain}</p></div>',
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        f'<div class="metric-card"><h3>Downloaded Files</h3><p>{len(files)}</p></div>',
        unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        f'<div class="metric-card"><h3>Total Size</h3><p>{format_size(total_size)}</p></div>',
        unsafe_allow_html=True,
    )
with col4:
    forecast_info = f"{params.get('last_hour', params.get('days_number', 1)*24)}h"
    st.markdown(
        f'<div class="metric-card"><h3>Forecast Range</h3><p>{forecast_info}</p></div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# Tabs
tab_map, tab_download, tab_files, tab_data = st.tabs(["🗺️ Domain Map", "📥 Download", "📁 Files", "📊 Data Preview"])

# --- TAB: Domain Map ---
with tab_map:
    st.markdown("### Selected Domain")
    st.markdown(
        f"""<div class="domain-box">
        <strong>{domain}</strong><br>
        Longitude: {domain_coords['lon_min']}° to {domain_coords['lon_max']}°<br>
        Latitude: {domain_coords['lat_min']}° to {domain_coords['lat_max']}°
        </div>""",
        unsafe_allow_html=True,
    )

    # Interactive map using Plotly
    try:
        import plotly.graph_objects as go

        lon_min, lon_max = domain_coords["lon_min"], domain_coords["lon_max"]
        lat_min, lat_max = domain_coords["lat_min"], domain_coords["lat_max"]

        fig = go.Figure()

        # Domain bounding box
        fig.add_trace(go.Scattergeo(
            lon=[lon_min, lon_max, lon_max, lon_min, lon_min],
            lat=[lat_min, lat_min, lat_max, lat_max, lat_min],
            mode="lines",
            line=dict(color="#ef4444", width=3),
            name="Domain",
            fill="toself",
            fillcolor="rgba(239, 68, 68, 0.1)",
        ))

        # Center marker
        center_lon = (lon_min + lon_max) / 2
        center_lat = (lat_min + lat_max) / 2
        fig.add_trace(go.Scattergeo(
            lon=[center_lon],
            lat=[center_lat],
            mode="markers+text",
            marker=dict(size=10, color="#3b82f6"),
            text=[domain],
            textposition="top center",
            name="Center",
        ))

        fig.update_geos(
            projection_type="natural earth",
            showland=True,
            landcolor="#e8e8e8",
            showocean=True,
            oceancolor="#d4e6f1",
            showcountries=True,
            countrycolor="#999",
            showcoastlines=True,
            coastlinecolor="#666",
            lataxis=dict(range=[lat_min - 5, lat_max + 5]),
            lonaxis=dict(range=[lon_min - 5, lon_max + 5]),
        )

        fig.update_layout(
            height=500,
            margin=dict(l=0, r=0, t=30, b=0),
            showlegend=False,
            geo=dict(bgcolor="rgba(0,0,0,0)"),
        )

        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        st.warning("Install `plotly` for interactive maps: `pip install plotly`")
        st.markdown(f"""
        **Domain Bounds:**
        - Lon: [{lon_min}, {lon_max}]
        - Lat: [{lat_min}, {lat_max}]
        """)

    # All domains overview
    with st.expander("📋 All configured domains"):
        domain_data = []
        for name, coords in DOMAINS.items():
            domain_data.append({
                "Domain": name,
                "Lon Min": coords["lon_min"],
                "Lon Max": coords["lon_max"],
                "Lat Min": coords["lat_min"],
                "Lat Max": coords["lat_max"],
            })
        st.dataframe(domain_data, use_container_width=True, hide_index=True)

# --- TAB: Download ---
with tab_download:
    st.markdown("### Download Execution")

    if run_btn:
        st.session_state.download_status = "running"
        st.session_state.download_log = ""

        st.info(f"**Command:** `{cmd_str}`")
        log_container = st.empty()

        with st.spinner("Downloading…"):
            returncode, output = run_download(cmd, log_container)

        st.session_state.download_log = output

        if returncode == 0:
            st.session_state.download_status = "done"
            st.success("✅ Download completed successfully!")
        else:
            st.session_state.download_status = "error"
            st.error(f"❌ Download failed (exit code {returncode})")

        st.rerun()

    elif st.session_state.download_log:
        st.markdown("#### Last download log")
        st.markdown(
            f'<div class="log-area">{st.session_state.download_log[-5000:]}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("""
        Configure your download parameters in the sidebar and click **🚀 Start Download**.

        The process will run in the background and stream output here.
        """)

# --- TAB: Files ---
with tab_files:
    st.markdown("### Downloaded Files")

    out_dir = Path(info["output_dir"])
    if not out_dir.exists():
        st.info(f"Output directory `{out_dir}` does not exist yet. Run a download to create it.")
    elif not files:
        st.info("No downloaded files found in the output directory.")
    else:
        # Summary
        st.markdown(f"**{len(files)} files** in `{out_dir}/` — Total: **{format_size(total_size)}**")

        # File table
        file_data = []
        for f in files[:30]:
            file_data.append({
                "📄 File": f.name,
                "📁 Path": str(f.relative_to(out_dir)),
                "💾 Size": format_size(f.stat().st_size),
                "🕐 Modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        st.dataframe(file_data, use_container_width=True, hide_index=True)

# --- TAB: Data Preview ---
with tab_data:
    st.markdown("### Data Preview")

    if not files:
        st.info("No files available for preview. Download data first.")
    else:
        nc_files = [f for f in files if f.suffix == ".nc"]
        if not nc_files:
            st.info("No NetCDF files found for preview. Only `.nc` files can be inspected here.")
        else:
            selected_file = st.selectbox("Select a file to inspect", nc_files, format_func=lambda f: f.name)

            if selected_file:
                try:
                    import xarray as xr

                    ds = xr.open_dataset(selected_file)

                    col_info, col_vars = st.columns(2)

                    with col_info:
                        st.markdown("#### Dataset Info")
                        st.markdown(f"- **Dimensions:** {dict(ds.dims)}")
                        st.markdown(f"- **Coordinates:** {list(ds.coords)}")
                        st.markdown(f"- **Variables:** {list(ds.data_vars)}")

                    with col_vars:
                        st.markdown("#### Attributes")
                        attrs = dict(ds.attrs) if ds.attrs else {"(no global attributes)": ""}
                        st.json(attrs)

                    # Variable quick plot
                    if ds.data_vars:
                        var_name = st.selectbox("Variable to plot", list(ds.data_vars))
                        var = ds[var_name]

                        st.markdown(f"**{var_name}** — shape: `{var.dims}` {var.shape}")

                        if len(var.dims) >= 2:
                            try:
                                import plotly.express as px
                                import numpy as np

                                # Handle time dimension
                                plot_data = var
                                if "time" in var.dims and var.sizes["time"] > 1:
                                    time_idx = st.slider("Time step", 0, var.sizes["time"] - 1, 0)
                                    plot_data = var.isel(time=time_idx)
                                elif "time" in var.dims:
                                    plot_data = var.isel(time=0)

                                # Handle level/depth
                                for dim in ("level", "depth", "Depth"):
                                    if dim in plot_data.dims and plot_data.sizes[dim] > 1:
                                        level_idx = st.slider(f"{dim}", 0, plot_data.sizes[dim] - 1, 0)
                                        plot_data = plot_data.isel(**{dim: level_idx})
                                    elif dim in plot_data.dims:
                                        plot_data = plot_data.isel(**{dim: 0})

                                if len(plot_data.dims) == 2:
                                    values = plot_data.values
                                    fig_data = px.imshow(
                                        values,
                                        color_continuous_scale="viridis",
                                        labels={"color": var_name},
                                        aspect="auto",
                                    )
                                    fig_data.update_layout(height=450, margin=dict(l=0, r=0, t=30, b=0))
                                    st.plotly_chart(fig_data, use_container_width=True)
                                else:
                                    st.warning(f"Cannot auto-plot variable with dims: {plot_data.dims}")

                            except ImportError:
                                st.warning("Install `plotly` for interactive data plots.")
                        else:
                            st.line_chart(var.values)

                    ds.close()

                except ImportError:
                    st.error("Install `xarray` and `netCDF4` for data preview.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    '<p style="text-align:center;color:#94a3b8;font-size:0.8rem;">'
    "Global Models Downloader v1.0 — Built with Streamlit"
    "</p>",
    unsafe_allow_html=True,
)

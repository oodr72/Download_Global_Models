#!/usr/bin/env python3
"""
windy_animator.py

Create Windy-style visualizations from Copernicus-like NetCDF files:

Modes
-----
- scalar        : animated scalar field (e.g. temperature, wave height)
- quiver        : animated arrows for vector fields (e.g. wind, currents)
- particles     : animated advected dots (Lagrangian particles)
- streamlines   : animated streaklines (Windy-style flowing hair)
- currents_map  : animated dense streamlines (Perpetual-Ocean style)
- wave          : combined scalar+quiver for wave height + mean direction

Output
------
- If --out ends with .mp4 → MP4 video via FFMpegWriter (requires ffmpeg).
- Otherwise → GIF via PillowWriter.

Extras
------
- Spatial subdomain:      --lon-min/max --lat-min/max
- Grid upsampling:        --upsample-factor F (>1 → smoother fields)
- Discrete colormap:      --discrete-colors N
- Streamlines colored:    --streamlines-colored
- Themes:                 --theme {dark,dark-contrast,paper}
- Optional title & fonts: --title, --title-fontsize, --time-fontsize
"""

from __future__ import annotations

import argparse
from pathlib import Path
import logging
import time
import warnings

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import matplotlib.collections as mcoll
from matplotlib.animation import FuncAnimation, PillowWriter, FFMpegWriter
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.ticker as mticker
import matplotlib as mpl

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from mpl_toolkits.axes_grid1 import make_axes_locatable

# Optional smoothing for currents_map
try:
    from scipy.ndimage import gaussian_filter

    HAS_SCIPY = True
except Exception:
    HAS_SCIPY = False

# Matplotlib sometimes divides by zero for arrow heads in streamplot; harmless for us.
warnings.filterwarnings(
    "ignore",
    message="invalid value encountered in scalar divide",
    category=RuntimeWarning,
    module="matplotlib.patches",
)

logger = logging.getLogger("windy_animator")

# ---------------------------------------------------------------------------
# Theme system
# ---------------------------------------------------------------------------

THEMES: dict[str, dict] = {
    # Present look (default)
    "dark": {
        "fig_facecolor": "black",
        "ax_facecolor": "#050711",      # dark ocean
        "land_facecolor": "#2a2a2a",    # slightly lighter land for contrast
        "land_edgecolor": "#505050",
        "land_lw": 0.4,
        "coast_color": "#d8d8d8",
        "coast_lw": 0.5,
        "border_color": "#666666",
        "border_lw": 0.3,
        "grid_color": "#222222",
        "grid_alpha": 0.5,
        "title_color": "white",
        "text_color": "white",
        "textbox_facecolor": "black",
    },
    # Higher contrast between land and ocean
    "dark-contrast": {
        "fig_facecolor": "black",
        "ax_facecolor": "#02030a",      # very dark ocean
        "land_facecolor": "#383838",    # brighter land
        "land_edgecolor": "#aaaaaa",
        "land_lw": 0.6,
        "coast_color": "#ffffff",
        "coast_lw": 0.8,
        "border_color": "#bbbbbb",
        "border_lw": 0.4,
        "grid_color": "#303030",
        "grid_alpha": 0.6,
        "title_color": "white",
        "text_color": "white",
        "textbox_facecolor": "black",
    },
    # Light / paper style (for reports)
    "paper": {
        "fig_facecolor": "white",
        "ax_facecolor": "white",
        "land_facecolor": "#f2f2f2",
        "land_edgecolor": "#666666",
        "land_lw": 0.5,
        "coast_color": "black",
        "coast_lw": 0.6,
        "border_color": "#555555",
        "border_lw": 0.4,
        "grid_color": "#cccccc",
        "grid_alpha": 0.7,
        "title_color": "black",
        "text_color": "black",
        "textbox_facecolor": "white",
    },
}


def get_theme(name: str) -> dict:
    if name not in THEMES:
        logger.warning("Unknown theme '%s', falling back to 'dark'", name)
        return THEMES["dark"]
    return THEMES[name]


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def setup_logging():
    """Configure a simple global logger (idempotent)."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def load_copernicus_dataset(path: str | Path) -> xr.Dataset:
    """Load NetCDF with xarray."""
    logger.info("Loading dataset from %s", path)
    t0 = time.perf_counter()
    ds = xr.open_dataset(path)
    logger.info(
        "Dataset loaded: %d variables, dimensions=%s (%.2f s)",
        len(ds.data_vars),
        dict(ds.dims),
        time.perf_counter() - t0,
    )
    return ds


def subset_domain(
    ds: xr.Dataset,
    lon_min: float | None,
    lon_max: float | None,
    lat_min: float | None,
    lat_max: float | None,
) -> xr.Dataset:
    """
    Optionally subset the dataset to a lon/lat bounding box.

    Called early, before any heavy processing, for efficiency.
    """
    if all(v is None for v in (lon_min, lon_max, lat_min, lat_max)):
        logger.info("Using full spatial domain (no subsetting requested).")
        return ds

    lon_vals = ds["longitude"].values
    lat_vals = ds["latitude"].values

    lon_min_eff = float(lon_vals.min()) if lon_min is None else float(lon_min)
    lon_max_eff = float(lon_vals.max()) if lon_max is None else float(lon_max)
    lat_min_eff = float(lat_vals.min()) if lat_min is None else float(lat_min)
    lat_max_eff = float(lat_vals.max()) if lat_max is None else float(lat_max)

    lon_min_eff = max(lon_min_eff, float(lon_vals.min()))
    lon_max_eff = min(lon_max_eff, float(lon_vals.max()))
    lat_min_eff = max(lat_min_eff, float(lat_vals.min()))
    lat_max_eff = min(lat_max_eff, float(lat_vals.max()))

    logger.info(
        "Requested subdomain: lon=[%.2f, %.2f], lat=[%.2f, %.2f]",
        lon_min_eff,
        lon_max_eff,
        lat_min_eff,
        lat_max_eff,
    )

    lon_asc = lon_vals[0] <= lon_vals[-1]
    lat_asc = lat_vals[0] <= lat_vals[-1]

    lon_slice = slice(lon_min_eff, lon_max_eff) if lon_asc else slice(lon_max_eff, lon_min_eff)
    lat_slice = slice(lat_min_eff, lat_max_eff) if lat_asc else slice(lat_max_eff, lat_min_eff)

    ds_sub = ds.sel(longitude=lon_slice, latitude=lat_slice)

    if ds_sub.dims.get("longitude", 0) == 0 or ds_sub.dims.get("latitude", 0) == 0:
        raise ValueError(
            "Subdomain selection resulted in an empty grid. "
            "Check lon/lat limits against dataset domain."
        )

    lon_sub = ds_sub["longitude"].values
    lat_sub = ds_sub["latitude"].values
    logger.info(
        "Subdomain dims: longitude=%d (%.2f..%.2f), latitude=%d (%.2f..%.2f)",
        lon_sub.size,
        float(lon_sub.min()),
        float(lon_sub.max()),
        lat_sub.size,
        float(lat_sub.min()),
        float(lat_sub.max()),
    )

    return ds_sub


def upscale_grid(ds: xr.Dataset, factor: float) -> xr.Dataset:
    """
    Optionally upsample the lon/lat grid by a constant factor using
    bilinear interpolation (xarray.interp), after subdomain selection.

    factor <= 1.0 → returns ds unchanged.
    """
    if factor is None or factor <= 1.0:
        logger.info("No grid upsampling applied (factor <= 1).")
        return ds

    lon = ds["longitude"].values
    lat = ds["latitude"].values

    if lon.size < 2 or lat.size < 2:
        logger.info("Grid too small to upsample; skipping.")
        return ds

    lon_asc = lon[0] <= lon[-1]
    lat_asc = lat[0] <= lat[-1]

    nlon_new = int((lon.size - 1) * factor) + 1
    nlat_new = int((lat.size - 1) * factor) + 1

    if nlon_new <= lon.size and nlat_new <= lat.size:
        logger.info(
            "Upsample factor %.2f results in no effective increase; skipping.",
            factor,
        )
        return ds

    if lon_asc:
        lon_new = np.linspace(float(lon[0]), float(lon[-1]), nlon_new)
    else:
        lon_new = np.linspace(float(lon[-1]), float(lon[0]), nlon_new)[::-1]

    if lat_asc:
        lat_new = np.linspace(float(lat[0]), float(lat[-1]), nlat_new)
    else:
        lat_new = np.linspace(float(lat[-1]), float(lat[0]), nlat_new)[::-1]

    logger.info(
        "Upsampling grid by factor %.2f: lon %d→%d, lat %d→%d",
        factor,
        lon.size,
        nlon_new,
        lat.size,
        nlat_new,
    )
    if factor > 3:
        logger.warning(
            "Upsample factor %.1f is large; this may increase memory usage "
            "and runtime significantly.",
            factor,
        )

    t0 = time.perf_counter()
    ds_hi = ds.interp(longitude=lon_new, latitude=lat_new, method="linear")
    logger.info("Upsampling complete (%.2f s).", time.perf_counter() - t0)

    return ds_hi


def _transpose_t_lat_lon(da: xr.DataArray) -> xr.DataArray:
    """Return view with dims ordered as (time, latitude, longitude) if possible."""
    wanted = ("time", "latitude", "longitude")
    if all(dim in da.dims for dim in wanted):
        return da.transpose(*wanted)
    return da


def get_lon_lat(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    lon = ds["longitude"].values
    lat = ds["latitude"].values
    return lon, lat


def compute_figsize_from_domain(
    lon: np.ndarray,
    lat: np.ndarray,
    base_width: float = 8.0,
) -> tuple[float, float]:
    """
    Compute a reasonable figure size based on lon/lat extent and latitude.
    Keeps aspect reasonable for different domains.
    """
    lon_range = float(lon.max() - lon.min())
    lat_range = float(lat.max() - lat.min())
    if lon_range <= 0 or lat_range <= 0:
        return (base_width, base_width * 0.6)

    mid_lat = 0.5 * (float(lat.min()) + float(lat.max()))
    # Account for lat distortion in PlateCarree
    aspect = (lat_range / lon_range) / max(np.cos(np.deg2rad(mid_lat)), 0.2)
    height = base_width * aspect
    height = float(np.clip(height, base_width * 0.4, base_width * 1.2))
    return (base_width, height)


def setup_map_axes(
    lon: np.ndarray,
    lat: np.ndarray,
    figsize: tuple[float, float] | None = None,
    projection: ccrs.Projection | None = None,
    theme_name: str = "dark",
) -> tuple[plt.Figure, plt.Axes]:
    """
    Create a Cartopy map with styling controlled by the selected theme.
    """
    theme = get_theme(theme_name)

    if projection is None:
        projection = ccrs.PlateCarree()
    proj = projection

    if figsize is None:
        figsize = compute_figsize_from_domain(lon, lat, base_width=8.0)

    fig = plt.figure(figsize=figsize)
    ax = plt.axes(projection=proj)

    fig.patch.set_facecolor(theme["fig_facecolor"])
    ax.set_facecolor(theme["ax_facecolor"])

    ax.add_feature(
        cfeature.LAND,
        facecolor=theme["land_facecolor"],
        edgecolor=theme["land_edgecolor"],
        linewidth=theme["land_lw"],
        zorder=1,
    )
    ax.add_feature(
        cfeature.BORDERS,
        linewidth=theme["border_lw"],
        edgecolor=theme["border_color"],
        zorder=2,
    )
    ax.coastlines(color=theme["coast_color"], linewidth=theme["coast_lw"], zorder=3)

    ax.set_extent(
        [float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max())],
        crs=proj,
    )

    gl = ax.gridlines(
        draw_labels=False,
        linewidth=0.3,
        color=theme["grid_color"],
        alpha=theme["grid_alpha"],
    )
    gl.xlines = False
    gl.ylines = False

    return fig, ax


def add_colorbar(
    fig: plt.Figure,
    ax: plt.Axes,
    mappable,
    label: str | None = None,
    ticks: np.ndarray | None = None,
    fmt: str | None = None,
    tick_color: str | None = None,
):
    """
    Attach a colorbar whose size scales nicely with the map axes.
    """
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4%", pad=0.05, axes_class=plt.Axes)
    cbar = fig.colorbar(mappable, cax=cax, ticks=ticks)

    if label:
        cbar.set_label(label)

    if fmt is not None:
        cbar.ax.yaxis.set_major_formatter(mticker.FormatStrFormatter(fmt))

    if tick_color is not None:
        cbar.outline.set_edgecolor(tick_color)
        cbar.ax.yaxis.set_tick_params(color=tick_color)
        plt.setp(cbar.ax.get_yticklabels(), color=tick_color)

    return cbar


def auto_ticks_and_fmt(vmin: float, vmax: float, n_ticks: int = 7):
    """
    Compute "nice" tick positions and a suitable number format
    for the given data range.
    """
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        return np.array([vmin]), "%.2f"

    locator = mticker.MaxNLocator(nbins=n_ticks)
    ticks = locator.tick_values(vmin, vmax)
    ticks = ticks[(ticks >= vmin) & (ticks <= vmax)]
    if ticks.size < 2:
        ticks = np.linspace(vmin, vmax, n_ticks)

    step = ticks[1] - ticks[0] if ticks.size >= 2 else (vmax - vmin)
    max_abs = max(abs(vmin), abs(vmax))

    if abs(step) >= 10 or max_abs >= 100:
        fmt = "%.0f"
    elif abs(step) >= 1:
        fmt = "%.1f"
    else:
        fmt = "%.2f"

    return ticks, fmt


def make_colormap_and_norm(
    base_cmap: str,
    vmin: float,
    vmax: float,
    discrete_colors: int = 0,
):
    """
    Create a colormap + normalization pair.

    If discrete_colors > 0:
        - ListedColormap with N bands + BoundaryNorm.
    Else:
        - continuous colormap with linear Normalize.
    """
    # Use the modern Matplotlib colormap API (avoids deprecation warning)
    base = mpl.colormaps.get_cmap(base_cmap)

    if discrete_colors and discrete_colors > 0:
        colors = base(np.linspace(0, 1, discrete_colors))
        cmap = ListedColormap(colors, name=f"{base_cmap}_disc{discrete_colors}")
        bounds = np.linspace(vmin, vmax, discrete_colors + 1)
        norm = BoundaryNorm(boundaries=bounds, ncolors=cmap.N)
    else:
        cmap = base
        norm = plt.Normalize(vmin=vmin, vmax=vmax)

    return cmap, norm



def format_time_label(time_val) -> str:
    """Format xarray time value nicely for the title/time label."""
    try:
        return str(np.datetime_as_string(time_val, unit="h"))
    except Exception:
        return str(time_val)


def get_animation_writer(out_path: Path, fps: int):
    """
    Choose writer based on output extension.

    - .mp4 → FFMpegWriter (if available)
    - otherwise → PillowWriter (GIF / raster)
    """
    suffix = out_path.suffix.lower()
    if suffix == ".mp4":
        try:
            if hasattr(FFMpegWriter, "isAvailable") and FFMpegWriter.isAvailable():
                logger.info("Using FFMpegWriter for MP4 output.")
                return FFMpegWriter(fps=fps, codec="libx264", bitrate=-1)
            else:
                logger.warning(
                    "FFMpegWriter/ffmpeg not available; falling back to PillowWriter (GIF)."
                )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Error checking FFMpegWriter availability (%s); falling back to PillowWriter.",
                exc,
            )
    logger.info("Using PillowWriter (GIF / raster output).")
    return PillowWriter(fps=fps)


def infer_scalar_cmap(da: xr.DataArray, default: str = "turbo") -> str:
    """
    Heuristic choice of colormap based on variable name / units.

    - Temperatures → 'coolwarm'
    - Wave heights / sea state → 'turbo'
    - Currents / velocities / winds → 'turbo'
    """
    name = (da.name or "").lower()
    long_name = da.attrs.get("long_name", "").lower()
    units = da.attrs.get("units", "").lower()
    txt = f"{name} {long_name} {units}"

    if "temperature" in txt or units in ("k", "degc", "°c", "c"):
        return "coolwarm"
    if "wave" in txt and "height" in txt:
        return "turbo"
    if "wave" in txt and "period" in txt:
        return "plasma"
    if "current" in txt or "velocity" in txt:
        return "turbo"
    if "wind" in txt or "gust" in txt:
        return "plasma"
    return default


# ---------------------------------------------------------------------------
# Scalar field animation (dark / themed style)
# ---------------------------------------------------------------------------

def animate_scalar_field(
    ds: xr.Dataset,
    var_name: str,
    out_path: str | Path,
    fps: int = 4,
    cmap: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    discrete_colors: int = 0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Animate a scalar variable (e.g. 2t, VHM0_WW) over time as a colored field.
    """
    logger.info("Preparing scalar field animation for '%s'", var_name)
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    data_var = _transpose_t_lat_lon(ds[var_name])
    lon, lat = get_lon_lat(ds)

    data_vals = data_var.values  # (time, lat, lon)
    nt = data_vals.shape[0]

    if vmin is None:
        vmin = float(np.nanmin(data_vals))
    if vmax is None:
        vmax = float(np.nanmax(data_vals))
    logger.info("Scalar global range: vmin=%.3f, vmax=%.3f", vmin, vmax)

    if cmap is None:
        cmap = infer_scalar_cmap(data_var, default="turbo")
    cmap_obj, norm = make_colormap_and_norm(cmap, vmin, vmax, discrete_colors)

    fig, ax = setup_map_axes(lon, lat, figsize=None, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    lon2d, lat2d = np.meshgrid(lon, lat)

    quad = ax.pcolormesh(
        lon2d,
        lat2d,
        data_vals[0],
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap=cmap_obj,
        norm=norm,
    )

    units = data_var.attrs.get("units", "")
    if units:
        cbar_label = f"{data_var.attrs.get('long_name', var_name)} [{units}]"
    else:
        cbar_label = data_var.attrs.get("long_name", var_name)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    sm.set_array([])
    ticks, fmt = auto_ticks_and_fmt(vmin, vmax)
    add_colorbar(
        fig,
        ax,
        sm,
        cbar_label,
        ticks=ticks,
        fmt=fmt,
        tick_color=theme["text_color"],
    )

    time_vals = ds["time"].values
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.7, edgecolor="none"
        ),
    )

    fig.tight_layout()

    def update(frame: int):
        quad.set_array(data_vals[frame].ravel())
        time_text.set_text(format_time_label(time_vals[frame]))
        if frame % 5 == 0:
            logger.debug("Scalar frame %d/%d", frame + 1, nt)
        return quad, time_text

    logger.info("Rendering %d frames at %d fps (scalar)", nt, fps)
    anim = FuncAnimation(fig, update, frames=nt, interval=1000 / fps, blit=False)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Scalar field animation saved to %s (%.2f s)",
        out_path,
        time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# Vector field: quiver animation (themed)
# ---------------------------------------------------------------------------

def animate_quiver(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_path: str | Path,
    fps: int = 4,
    stride: int = 10,
    scale: float | None = None,
    discrete_colors: int = 0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Animate vector field using quiver (arrows) over a themed PlateCarree map.
    """
    logger.info("Preparing quiver animation for '%s'/'%s'", u_name, v_name)
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    u = _transpose_t_lat_lon(ds[u_name])
    v = _transpose_t_lat_lon(ds[v_name])
    lon, lat = get_lon_lat(ds)

    u_data = u.values
    v_data = v.values
    speed_data = np.sqrt(u_data**2 + v_data**2)
    nt = u_data.shape[0]

    speed_max = float(np.nanmax(speed_data))
    logger.info("Quiver speed range: [0, %.3f]", speed_max)

    lon_sub = lon[::stride]
    lat_sub = lat[::stride]
    lon2d, lat2d = np.meshgrid(lon_sub, lat_sub)

    u_sub = u_data[:, ::stride, ::stride]
    v_sub = v_data[:, ::stride, ::stride]
    speed_sub = speed_data[:, ::stride, ::stride]

    cmap_obj, norm = make_colormap_and_norm("turbo", 0.0, speed_max, discrete_colors)

    fig, ax = setup_map_axes(lon, lat, figsize=None, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    q = ax.quiver(
        lon2d,
        lat2d,
        u_sub[0],
        v_sub[0],
        speed_sub[0],
        transform=ccrs.PlateCarree(),
        cmap=cmap_obj,
        norm=norm,
        scale=scale,
        width=0.003,
        headwidth=3,
        minlength=0.1,
    )

    units = u.attrs.get("units", "")
    cbar_label = f"Speed [{units}]" if units else "Speed"
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    sm.set_array([])
    ticks, fmt = auto_ticks_and_fmt(0.0, speed_max)
    add_colorbar(
        fig,
        ax,
        sm,
        cbar_label,
        ticks=ticks,
        fmt=fmt,
        tick_color=theme["text_color"],
    )

    time_vals = ds["time"].values
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.7, edgecolor="none"
        ),
    )

    fig.tight_layout()

    def update(frame: int):
        q.set_UVC(u_sub[frame], v_sub[frame], speed_sub[frame])
        time_text.set_text(format_time_label(time_vals[frame]))
        if frame % 5 == 0:
            logger.debug("Quiver frame %d/%d", frame + 1, nt)
        return q, time_text

    logger.info("Rendering %d frames at %d fps (quiver)", nt, fps)
    anim = FuncAnimation(fig, update, frames=nt, interval=1000 / fps, blit=False)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Quiver animation saved to %s (%.2f s)", out_path, time.perf_counter() - t0
    )


# ---------------------------------------------------------------------------
# Vector field: particle advection (dots)
# ---------------------------------------------------------------------------

def animate_particles(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_path: str | Path,
    fps: int = 12,
    n_particles: int = 2000,
    speed_factor: float = 1.0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Animate particles advected by the vector field (Windy-style dots).
    """
    logger.info(
        "Preparing particle animation for '%s'/'%s' with %d particles",
        u_name,
        v_name,
        n_particles,
    )
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    u = _transpose_t_lat_lon(ds[u_name])
    v = _transpose_t_lat_lon(ds[v_name])
    lon, lat = get_lon_lat(ds)
    nt = u.sizes["time"]

    fig, ax = setup_map_axes(lon, lat, figsize=None, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    time_vals = ds["time"].values
    if nt > 1:
        dt_seconds = float(
            (np.array(time_vals[1]) - np.array(time_vals[0]))
            / np.timedelta64(1, "s")
        )
    else:
        dt_seconds = 6 * 3600
    dt_seconds *= speed_factor
    logger.info(
        "Base dt between model steps: %.1f s (speed_factor=%.2f)",
        dt_seconds,
        speed_factor,
    )

    k_lat = dt_seconds / 111_000.0

    lon_min, lon_max = float(lon.min()), float(lon.max())
    lat_min, lat_max = float(lat.min()), float(lat.max())
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])

    rng = np.random.default_rng(42)
    x = rng.uniform(lon_min, lon_max, size=n_particles)
    y = rng.uniform(lat_min, lat_max, size=n_particles)

    scat = ax.scatter(
        x,
        y,
        s=1,
        color=theme["text_color"],
        alpha=0.7,
        transform=ccrs.PlateCarree(),
        linewidths=0,
    )

    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.7, edgecolor="none"
        ),
    )

    fig.tight_layout()

    u_data = u.values
    v_data = v.values
    lon_width = lon_max - lon_min

    def step_particles(t_idx: int, x: np.ndarray, y: np.ndarray):
        ix = ((x - lon_min) / dlon).astype(int)
        iy = ((y - lat_min) / dlat).astype(int)

        ix = np.clip(ix, 0, lon.size - 1)
        iy = np.clip(iy, 0, lat.size - 1)

        u_now = u_data[t_idx, iy, ix]
        v_now = v_data[t_idx, iy, ix]

        lat_rad = np.deg2rad(y)
        deg_lon_per_ms = 1.0 / (111_000.0 * np.cos(lat_rad) + 1e-9)

        x_new = x + u_now * dt_seconds * deg_lon_per_ms
        y_new = y + v_now * k_lat

        x_new = ((x_new - lon_min) % lon_width) + lon_min
        y_new = np.clip(y_new, lat_min, lat_max)

        return x_new, y_new

    n_loops = 4
    total_frames = nt * n_loops
    logger.info("Rendering %d frames at %d fps (particles)", total_frames, fps)

    def update(frame: int):
        nonlocal x, y
        t_idx = frame % nt
        x, y = step_particles(t_idx, x, y)
        scat.set_offsets(np.column_stack((x, y)))
        time_text.set_text(format_time_label(time_vals[t_idx]))
        if frame % 20 == 0:
            logger.debug("Particle frame %d/%d", frame + 1, total_frames)
        return scat, time_text

    anim = FuncAnimation(
        fig,
        update,
        frames=total_frames,
        interval=1000 / fps,
        blit=False,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Particle animation saved to %s (%.2f s)",
        out_path,
        time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# Streamlines + streaking particles (Windy-style animated)
# ---------------------------------------------------------------------------

def animate_streamlines_with_particles(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_path: str | Path,
    fps: int = 18,
    n_particles: int = 3000,
    speed_factor: float = 0.6,
    trail_length: int = 25,
    substeps_per_field: int = 6,
    colored: bool = False,
    discrete_colors: int = 0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Windy-style animation:

      - Background: time-mean speed as a subtle field.
      - On top: dense streaklines (particles with trails) advected by
        the time-varying vector field.

    If `colored` is True:
      - Streaklines are colored by speed using the **jet** colormap.
      - A colorbar with the same colormap + fixed [vmin, vmax]
        from the full time range is shown.

    If `colored` is False:
      - Streaklines are golden with speed-dependent brightness.
    """
    logger.info(
        "Preparing streamlines+particles animation for '%s'/'%s' (%d particles, colored=%s)",
        u_name,
        v_name,
        n_particles,
        colored,
    )
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    u = _transpose_t_lat_lon(ds[u_name])
    v = _transpose_t_lat_lon(ds[v_name])
    lon, lat = get_lon_lat(ds)
    nt = u.sizes["time"]
    time_vals = ds["time"].values

    if nt > 1:
        u_base = u.mean(dim="time").values
        v_base = v.mean(dim="time").values
    else:
        u_base = u.isel(time=0).values
        v_base = v.isel(time=0).values

    speed_base = np.sqrt(u_base**2 + v_base**2)

    u_data = u.values
    v_data = v.values
    speed_all = np.sqrt(u_data**2 + v_data**2)
    speed_min = float(np.nanmin(speed_all))
    speed_max = np.nanpercentile(speed_all, 98.0)
    logger.info("Streamlines speed range (subset): [%.3f, %.3f]", speed_min, speed_max)

    vmin = 0.0
    vmax = speed_max
    cmap_name = "jet" if colored else "cividis"
    cmap_obj, norm = make_colormap_and_norm(cmap_name, vmin, vmax, discrete_colors)
    cmap_lines = cmap_obj

    fig, ax = setup_map_axes(lon, lat, figsize=None, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    lon2d, lat2d = np.meshgrid(lon, lat)
    quad = ax.pcolormesh(
        lon2d,
        lat2d,
        speed_base,
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap=cmap_obj,
        norm=norm,
        alpha=0.18,
    )

    units = u.attrs.get("units", "")
    cbar_label = f"Speed [{units}]" if units else "Speed"

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    sm.set_array([])
    ticks, fmt = auto_ticks_and_fmt(vmin, vmax)
    add_colorbar(
        fig,
        ax,
        sm,
        cbar_label,
        ticks=ticks,
        fmt=fmt,
        tick_color=theme["text_color"],
    )

    valid_mask = np.isfinite(speed_base)
    flat_valid = np.where(valid_mask.ravel())[0]
    if flat_valid.size == 0:
        raise RuntimeError("No valid points to seed particles.")

    rng = np.random.default_rng(42)

    def random_valid_positions(n: int) -> tuple[np.ndarray, np.ndarray]:
        idx = rng.choice(flat_valid, size=n, replace=True)
        iy, ix = np.unravel_index(idx, valid_mask.shape)
        return lon[ix], lat[iy]

    x, y = random_valid_positions(n_particles)

    trail_x = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_y = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_speed = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_x[:, 0] = x
    trail_y[:, 0] = y

    lc = mcoll.LineCollection(
        [],
        linewidths=1.0,
        linestyle="solid",
        capstyle="round",
        transform=ccrs.PlateCarree(),
    )
    ax.add_collection(lc)

    gold_rgb = (249 / 255.0, 229 / 255.0, 102 / 255.0)

    alpha_levels = np.linspace(1.0, 0.05, trail_length - 1)
    alpha_pattern_flat = np.tile(alpha_levels, n_particles)

    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.6, edgecolor="none"
        ),
    )

    fig.tight_layout()

    lon_min, lon_max = float(lon.min()), float(lon.max())
    lat_min, lat_max = float(lat.min()), float(lat.max())
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])

    jump_lon = 3.0 * dlon
    jump_lat = 3.0 * dlat

    if nt > 1:
        dt_model = float(
            (np.array(time_vals[1]) - np.array(time_vals[0]))
            / np.timedelta64(1, "s")
        )
    else:
        dt_model = 6 * 3600.0
    dt_seconds = (dt_model / substeps_per_field) * speed_factor
    logger.info(
        "Streamlines dt=%.1f s, substeps=%d, speed_factor=%.2f",
        dt_seconds,
        substeps_per_field,
        speed_factor,
    )

    def step_particles(
        t_idx: int, x: np.ndarray, y: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        ix = ((x - lon_min) / dlon).astype(int)
        iy = ((y - lat_min) / dlat).astype(int)

        ix = np.clip(ix, 0, lon.size - 1)
        iy = np.clip(iy, 0, lat.size - 1)

        u_now = u_data[t_idx, iy, ix]
        v_now = v_data[t_idx, iy, ix]

        speed_now = np.sqrt(u_now**2 + v_now**2)

        lat_rad = np.deg2rad(y)
        deg_lat_per_ms = 1.0 / 111_000.0
        deg_lon_per_ms = 1.0 / (111_000.0 * np.cos(lat_rad) + 1e-9)

        x_new = x + u_now * dt_seconds * deg_lon_per_ms
        y_new = y + v_now * dt_seconds * deg_lat_per_ms

        out_of_lon = (x_new < lon_min) | (x_new > lon_max)
        out_of_lat = (y_new < lat_min) | (y_new > lat_max)
        bad_field = ~np.isfinite(u_now) | ~np.isfinite(v_now)
        reseeded = out_of_lon | out_of_lat | bad_field

        if np.any(reseeded):
            new_x, new_y = random_valid_positions(reseeded.sum())
            x_new = x_new.copy()
            y_new = y_new.copy()
            x_new[reseeded] = new_x
            y_new[reseeded] = new_y
            speed_now[reseeded] = np.nan

        return x_new, y_new, speed_now, reseeded

    n_loops = 4
    total_frames = nt * substeps_per_field * n_loops
    logger.info("Rendering %d frames at %d fps (streamlines)", total_frames, fps)

    def update(frame: int):
        nonlocal x, y, trail_x, trail_y, trail_speed

        coarse_idx = (frame // substeps_per_field) % nt

        x_new, y_new, speed_now, reseeded = step_particles(coarse_idx, x, y)
        x, y = x_new, y_new

        trail_x[:, 1:] = trail_x[:, :-1]
        trail_y[:, 1:] = trail_y[:, :-1]
        trail_speed[:, 1:] = trail_speed[:, :-1]
        trail_x[:, 0] = x
        trail_y[:, 0] = y
        trail_speed[:, 0] = speed_now

        if np.any(reseeded):
            trail_x[reseeded, 1:] = np.nan
            trail_y[reseeded, 1:] = np.nan
            trail_speed[reseeded, 1:] = np.nan

        dx_all = np.abs(trail_x[:, :-1] - trail_x[:, 1:])
        dy_all = np.abs(trail_y[:, :-1] - trail_y[:, 1:])
        big_jump_all = (dx_all > jump_lon) | (dy_all > jump_lat)

        xs0 = trail_x[:, :-1]
        ys0 = trail_y[:, :-1]
        xs1 = trail_x[:, 1:]
        ys1 = trail_y[:, 1:]

        segments = np.stack(
            [
                np.stack([xs0, ys0], axis=-1),
                np.stack([xs1, ys1], axis=-1),
            ],
            axis=2,
        ).reshape(-1, 2, 2)

        seg_speed = (trail_speed[:, :-1] + trail_speed[:, 1:]) * 0.5
        seg_speed_flat = seg_speed.ravel()
        big_jump_flat = big_jump_all.ravel()

        valid_points = (
            np.isfinite(xs0) & np.isfinite(ys0) & np.isfinite(xs1) & np.isfinite(ys1)
        )
        valid_flat = valid_points.ravel()
        mask = valid_flat & (~big_jump_flat) & np.isfinite(seg_speed_flat)

        if not np.any(mask):
            lc.set_segments([])
            lc.set_color([])
        else:
            segments_valid = segments[mask]
            speed_valid = seg_speed_flat[mask]

            if colored:
                speed_clipped = np.clip(speed_valid, vmin, vmax)
                if isinstance(norm, BoundaryNorm):
                    idx = norm(speed_clipped)
                    colors = cmap_lines(idx / max(cmap_lines.N - 1, 1))
                else:
                    colors = cmap_lines(norm(speed_clipped))
                alpha_valid = alpha_pattern_flat[mask]
                colors[:, 3] *= alpha_valid
            else:
                s_norm = np.clip(speed_valid / (speed_max + 1e-9), 0.0, 1.0)
                intensity = 0.2 + 0.8 * s_norm
                alpha_valid = alpha_pattern_flat[mask] * intensity

                colors = np.empty((segments_valid.shape[0], 4), dtype=float)
                colors[:, 0] = gold_rgb[0]
                colors[:, 1] = gold_rgb[1]
                colors[:, 2] = gold_rgb[2]
                colors[:, 3] = alpha_valid

            lc.set_segments(segments_valid)
            lc.set_color(colors)

        time_text.set_text(format_time_label(time_vals[coarse_idx]))
        if frame % 20 == 0:
            logger.debug("Streamline frame %d/%d", frame + 1, total_frames)
        return lc, time_text

    anim = FuncAnimation(
        fig,
        update,
        frames=total_frames,
        interval=1000 / fps,
        blit=False,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Streamlines + particles animation saved to %s (%.2f s)",
        out_path,
        time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# Animated currents map (Perpetual-Ocean style)
# ---------------------------------------------------------------------------

def animate_currents_map(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_path: str | Path,
    fps: int = 6,
    stride: int = 1,
    density: float = 5.0,
    arrowsize: float = 0.0,
    discrete_colors: int = 0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Animate sea-surface currents using dense colored streamlines
    with a global, fixed color scale (on the subset/upsampled domain).

    Parameters
    ----------
    arrowsize : float, optional
        Arrowhead size for streamplot. 0.0 (default) = effectively no visible heads.
    """
    logger.info(
        "Preparing currents_map animation for '%s'/'%s' (arrowsize=%.2f)",
        u_name,
        v_name,
        arrowsize,
    )
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    u = _transpose_t_lat_lon(ds[u_name])
    v = _transpose_t_lat_lon(ds[v_name])
    lon, lat = get_lon_lat(ds)
    time_vals = ds["time"].values

    lon2d, lat2d = np.meshgrid(lon, lat)

    u_all = u.values
    v_all = v.values
    nt = u_all.shape[0]
    logger.info("Currents_map grid: time=%d, lat=%d, lon=%d", nt, lat.size, lon.size)

    if HAS_SCIPY:
        logger.info("Applying Gaussian smoothing (sigma=1.0)")
        u_smooth = np.empty_like(u_all)
        v_smooth = np.empty_like(v_all)
        for t in range(nt):
            u_smooth[t] = gaussian_filter(u_all[t], sigma=1.0, mode="nearest")
            v_smooth[t] = gaussian_filter(v_all[t], sigma=1.0, mode="nearest")
    else:
        logger.info("SciPy not available: skipping smoothing.")
        u_smooth = u_all
        v_smooth = v_all

    lon_s = lon2d[::stride, ::stride]
    lat_s = lat2d[::stride, ::stride]
    u_s = u_smooth[:, ::stride, ::stride]
    v_s = v_smooth[:, ::stride, ::stride]

    speed_s = np.sqrt(u_s**2 + v_s**2)

    vmin = 0.0
    vmax = np.nanpercentile(speed_s, 97.0)
    cmap_obj, norm = make_colormap_and_norm("turbo", vmin, vmax, discrete_colors)
    logger.info("Currents_map speed range: [%.3f, %.3f]", vmin, vmax)

    figsize = compute_figsize_from_domain(lon, lat, base_width=12.0)
    fig, ax = setup_map_axes(lon, lat, figsize=figsize, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    sm = plt.cm.ScalarMappable(cmap=cmap_obj, norm=norm)
    sm.set_array([])
    units = u.attrs.get("units", "")
    cbar_label = f"Surface current speed [{units}]" if units else "Surface current speed"
    ticks, fmt = auto_ticks_and_fmt(vmin, vmax)
    cbar = add_colorbar(
        fig,
        ax,
        sm,
        cbar_label,
        ticks=ticks,
        fmt=fmt,
        tick_color=theme["text_color"],
    )
    cbar.ax.set_facecolor(theme["ax_facecolor"])

    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.6, edgecolor="none"
        ),
        zorder=10,
    )

    fig.tight_layout()

    current_lines: dict[str, mcoll.LineCollection | None] = {"lc": None}

    def draw_streamlines(t_idx: int):
        u_t = u_s[t_idx]
        v_t = v_s[t_idx]
        speed_t = speed_s[t_idx]

        if current_lines["lc"] is not None:
            current_lines["lc"].remove()
            current_lines["lc"] = None

        strm = ax.streamplot(
            lon_s,
            lat_s,
            u_t,
            v_t,
            density=density,
            color=speed_t,
            cmap=cmap_obj,
            norm=norm,
            linewidth=0.45,
            arrowsize=arrowsize,
            minlength=0.1,
            zorder=5,
        )
        lc = strm.lines
        lc.set_alpha(0.85)
        current_lines["lc"] = lc

    draw_streamlines(0)

    def update(frame: int):
        draw_streamlines(frame)
        time_text.set_text(format_time_label(time_vals[frame]))
        if frame % 2 == 0:
            logger.debug("Currents_map frame %d/%d", frame + 1, nt)
        return current_lines["lc"], time_text

    logger.info("Rendering %d frames at %d fps (currents_map)", nt, fps)
    anim = FuncAnimation(
        fig,
        update,
        frames=nt,
        interval=1000 / fps,
        blit=False,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Animated currents map saved to %s (%.2f s)",
        out_path,
        time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# New mode: wave height + mean wave direction (scalar + quiver)
# ---------------------------------------------------------------------------

def animate_wave_height_direction(
    ds: xr.Dataset,
    height_name: str,
    dir_name: str,
    out_path: str | Path,
    fps: int = 6,
    stride: int = 6,
    discrete_colors: int = 0,
    title: str | None = None,
    title_fontsize: float = 12,
    time_fontsize: float = 9,
    theme_name: str = "dark",
):
    """
    Combined scalar + quiver visualization for waves:

      - Background scalar = wave height (e.g. VHM0_WW).
      - Quiver arrows = mean wave direction (from 'degree_from_north').
        Arrows are unit-length vectors colored by wave height.

    Direction variables are usually 'from' direction in degrees from
    true north. We display propagation 'towards' direction by adding 180°.
    """
    logger.info(
        "Preparing wave height+direction animation for '%s' & '%s'",
        height_name,
        dir_name,
    )
    t0 = time.perf_counter()
    theme = get_theme(theme_name)

    h = _transpose_t_lat_lon(ds[height_name])
    d = _transpose_t_lat_lon(ds[dir_name])
    lon, lat = get_lon_lat(ds)

    h_data = h.values
    dir_deg = d.values
    nt = h_data.shape[0]

    vmin = float(np.nanmin(h_data))
    vmax = float(np.nanpercentile(h_data, 99.0))
    logger.info("Wave height range: [%.3f, %.3f]", vmin, vmax)

    cmap_name = infer_scalar_cmap(h, default="turbo")
    cmap_obj, norm = make_colormap_and_norm(cmap_name, vmin, vmax, discrete_colors)

    theta = np.deg2rad(dir_deg + 180.0)
    u_dir = np.sin(theta)
    v_dir = np.cos(theta)

    lon2d, lat2d = np.meshgrid(lon, lat)
    lon_q = lon2d[::stride, ::stride]
    lat_q = lat2d[::stride, ::stride]
    u_q = u_dir[:, ::stride, ::stride]
    v_q = v_dir[:, ::stride, ::stride]
    h_q = h_data[:, ::stride, ::stride]

    fig, ax = setup_map_axes(lon, lat, figsize=None, theme_name=theme_name)

    if title:
        ax.set_title(title, fontsize=title_fontsize, color=theme["title_color"], pad=6)

    quad = ax.pcolormesh(
        lon2d,
        lat2d,
        h_data[0],
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap=cmap_obj,
        norm=norm,
        alpha=0.9,
    )

    q = ax.quiver(
        lon_q,
        lat_q,
        u_q[0],
        v_q[0],
        h_q[0],
        transform=ccrs.PlateCarree(),
        cmap=cmap_obj,
        norm=norm,
        scale=None,
        width=0.003,
        headwidth=3,
        minlength=0.1,
    )

    units = h.attrs.get("units", "")
    cbar_label = (
        f"{h.attrs.get('long_name', height_name)} [{units}]"
        if units
        else h.attrs.get("long_name", height_name)
    )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)
    sm.set_array([])
    ticks, fmt = auto_ticks_and_fmt(vmin, vmax)
    add_colorbar(
        fig,
        ax,
        sm,
        cbar_label,
        ticks=ticks,
        fmt=fmt,
        tick_color=theme["text_color"],
    )

    time_vals = ds["time"].values
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=time_fontsize,
        color=theme["text_color"],
        bbox=dict(
            facecolor=theme["textbox_facecolor"], alpha=0.7, edgecolor="none"
        ),
    )

    fig.tight_layout()

    logger.info("Rendering %d frames at %d fps (wave)", nt, fps)

    def update(frame: int):
        quad.set_array(h_data[frame].ravel())
        q.set_UVC(u_q[frame], v_q[frame], h_q[frame])
        time_text.set_text(format_time_label(time_vals[frame]))
        if frame % 5 == 0:
            logger.debug("Wave frame %d/%d", frame + 1, nt)
        return quad, q, time_text

    anim = FuncAnimation(fig, update, frames=nt, interval=1000 / fps, blit=False)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = get_animation_writer(out_path, fps)
    anim.save(out_path, writer=writer)

    plt.close(fig)
    logger.info(
        "Wave height+direction animation saved to %s (%.2f s)",
        out_path,
        time.perf_counter() - t0,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Create Windy-style GIF/MP4 visualizations from Copernicus NetCDF."
    )
    p.add_argument("--nc", required=True, help="Path to NetCDF file")
    p.add_argument(
        "--mode",
        choices=["scalar", "quiver", "particles", "streamlines", "currents_map", "wave"],
        required=True,
        help="Type of visualization to create",
    )
    p.add_argument("--var", help="Scalar variable name (for mode=scalar or wave height)")
    p.add_argument(
        "--dirvar",
        help="Direction variable name (degree_from_north) for mode=wave",
    )
    p.add_argument("--uvar", help="U-component variable name (for vector modes)")
    p.add_argument("--vvar", help="V-component variable name (for vector modes)")
    p.add_argument("--out", required=True, help="Output file path (.gif or .mp4)")
    p.add_argument(
        "--fps", type=int, default=6, help="Frames per second (for animations)"
    )
    p.add_argument(
        "--time-index",
        type=int,
        default=0,
        help="(Parsed but unused for animated modes)",
    )
    p.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Grid stride for currents_map/wave streamlines (larger = coarser).",
    )
    p.add_argument(
        "--density",
        type=float,
        default=5.0,
        help="Streamline density for currents_map animation.",
    )
    p.add_argument(
        "--arrowsize",
        type=float,
        default=0.0,
        help="Arrow head size for currents_map (0 = no visible heads).",
    )
    p.add_argument(
        "--lon-min",
        type=float,
        default=None,
        help="Minimum longitude of subdomain (optional).",
    )
    p.add_argument(
        "--lon-max",
        type=float,
        default=None,
        help="Maximum longitude of subdomain (optional).",
    )
    p.add_argument(
        "--lat-min",
        type=float,
        default=None,
        help="Minimum latitude of subdomain (optional).",
    )
    p.add_argument(
        "--lat-max",
        type=float,
        default=None,
        help="Maximum latitude of subdomain (optional).",
    )
    p.add_argument(
        "--upsample-factor",
        type=float,
        default=1.0,
        help=(
            "Optional grid upsampling factor applied AFTER subdomain selection "
            "(>1 increases resolution; e.g. 2.0 ≈ 2x more points in each direction)."
        ),
    )
    p.add_argument(
        "--streamlines-colored",
        action="store_true",
        help=(
            "For mode=streamlines: color streaklines by speed with jet colormap "
            "and use a matching colorbar with fixed limits across all frames."
        ),
    )
    p.add_argument(
        "--discrete-colors",
        type=int,
        default=0,
        help=(
            "If >0, use a discrete colormap with N bands (BoundaryNorm). "
            "Recommended for GIF output to reduce colorbar flicker."
        ),
    )
    p.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional figure title to place above the map.",
    )
    p.add_argument(
        "--title-fontsize",
        type=float,
        default=12.0,
        help="Font size for the optional figure title.",
    )
    p.add_argument(
        "--time-fontsize",
        type=float,
        default=9.0,
        help="Font size for the time annotation in the lower-left corner.",
    )
    p.add_argument(
        "--theme",
        type=str,
        choices=list(THEMES.keys()),
        default="dark",
        help="Visual theme for map (colors, background, land contrast).",
    )
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    start_all = time.perf_counter()

    ds = load_copernicus_dataset(args.nc)
    ds = subset_domain(ds, args.lon_min, args.lon_max, args.lat_min, args.lat_max)
    ds = upscale_grid(ds, args.upsample_factor)

    mode = args.mode
    title = args.title
    title_fs = args.title_fontsize
    time_fs = args.time_fontsize
    theme_name = args.theme

    if mode == "scalar":
        if args.var is None:
            raise SystemExit("--var is required for mode=scalar")
        animate_scalar_field(
            ds,
            var_name=args.var,
            out_path=args.out,
            fps=args.fps,
            discrete_colors=args.discrete_colors,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    elif mode == "quiver":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=quiver")
        animate_quiver(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_path=args.out,
            fps=args.fps,
            discrete_colors=args.discrete_colors,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    elif mode == "particles":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=particles")
        animate_particles(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_path=args.out,
            fps=args.fps,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    elif mode == "streamlines":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=streamlines")
        animate_streamlines_with_particles(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_path=args.out,
            fps=args.fps,
            colored=args.streamlines_colored,
            discrete_colors=args.discrete_colors,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    elif mode == "currents_map":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=currents_map")
        animate_currents_map(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_path=args.out,
            fps=args.fps,
            stride=args.stride,
            density=args.density,
            arrowsize=args.arrowsize,
            discrete_colors=args.discrete_colors,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    elif mode == "wave":
        if args.var is None or args.dirvar is None:
            raise SystemExit(
                "--var (wave height) and --dirvar (mean direction) are required for mode=wave"
            )
        animate_wave_height_direction(
            ds,
            height_name=args.var,
            dir_name=args.dirvar,
            out_path=args.out,
            fps=args.fps,
            stride=max(1, args.stride),
            discrete_colors=args.discrete_colors,
            title=title,
            title_fontsize=title_fs,
            time_fontsize=time_fs,
            theme_name=theme_name,
        )

    logger.info("Total execution time: %.2f s", time.perf_counter() - start_all)


if __name__ == "__main__":
    main()

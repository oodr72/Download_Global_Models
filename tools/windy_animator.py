#!/usr/bin/env python3
"""
windy_animator.py

Create Windy-style animated GIFs from Copernicus-like NetCDF:
- Scalar fields (temperature, wave height, etc.)
- Vector fields (winds, currents) as quiver
- Particle flow animations (dots)
- Streamlines + streaking particles (Windy-style pathlines)

Requires:
    pip install xarray netCDF4 numpy matplotlib cartopy pillow

Examples:

    # Scalar field (2 m temperature)
    python windy_animator.py \
        --nc ./data/copernicus/20251206/integrated_copernicus_20251206.nc \
        --mode scalar --var 2t --out gifs/temp2m.gif

    # Quiver currents
    python windy_animator.py \
        --nc ./data/copernicus/20251206/integrated_copernicus_20251206.nc \
        --mode quiver --uvar uo --vvar vo --out gifs/currents_quiver.gif

    # Particle flow (dots only)
    python windy_animator.py \
        --nc ./data/copernicus/20251206/integrated_copernicus_20251206.nc \
        --mode particles --uvar uo --vvar vo --out gifs/currents_particles.gif

    # Windy-style streaklines (streamlines + particles)
    python windy_animator.py \
        --nc ./data/copernicus/20251206/integrated_copernicus_20251206.nc \
        --mode streamlines --uvar uo --vvar vo \
        --out gifs/currents_streamlines_particles.gif
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import matplotlib.collections as mcoll

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from mpl_toolkits.axes_grid1 import make_axes_locatable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_copernicus_dataset(path: str | Path) -> xr.Dataset:
    """
    Load NetCDF and reorder dimensions to (time, latitude, longitude) when possible.
    """
    ds = xr.open_dataset(path)

    # Ensure dimension order is (time, lat, lon) if possible
    if {"time", "latitude", "longitude"} <= set(ds.dims):
        ds = ds.transpose("time", "latitude", "longitude")

    return ds


def get_lon_lat(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    lon = ds["longitude"].values
    lat = ds["latitude"].values
    return lon, lat


def setup_map_axes(
    lon: np.ndarray,
    lat: np.ndarray,
    figsize: tuple[float, float] = (8, 5),
) -> tuple[plt.Figure, plt.Axes]:
    """
    Create a Cartopy PlateCarree map, set extent to data lon/lat.
    """
    proj = ccrs.PlateCarree()
    fig = plt.figure(figsize=figsize)
    ax = plt.axes(projection=proj)

    # Background map
    ax.coastlines(linewidth=0.5)
    ax.add_feature(cfeature.LAND, facecolor="0.9", edgecolor="none")
    ax.add_feature(cfeature.BORDERS, linewidth=0.3)

    # Domain extent
    ax.set_extent(
        [float(lon.min()), float(lon.max()),
         float(lat.min()), float(lat.max())],
        crs=proj,
    )

    return fig, ax


def add_colorbar(fig: plt.Figure, ax: plt.Axes, mappable, label: str | None = None):
    """
    Attach a colorbar whose size scales nicely with the map axes.

    IMPORTANT: Use a plain Matplotlib Axes for the colorbar (axes_class=plt.Axes)
    so Cartopy doesn't complain about missing 'projection'.
    """
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="4%", pad=0.05, axes_class=plt.Axes)
    cbar = fig.colorbar(mappable, cax=cax)
    if label:
        cbar.set_label(label)
    return cbar


def format_time_label(time_val) -> str:
    """
    Format xarray time value nicely for the title.
    """
    try:
        # numpy.datetime64 → string
        return str(np.datetime_as_string(time_val, unit="h"))
    except Exception:
        # fallback for cftime or others
        return str(time_val)


# ---------------------------------------------------------------------------
# Scalar field animation
# ---------------------------------------------------------------------------

def animate_scalar_field(
    ds: xr.Dataset,
    var_name: str,
    out_gif: str | Path,
    fps: int = 4,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
):
    """
    Animate a scalar variable (e.g. 2t, VHM0_WW) over time as a colored field.
    """
    data_var = ds[var_name]
    lon, lat = get_lon_lat(ds)

    nt = data_var.sizes["time"]

    # Common color scale
    if vmin is None:
        vmin = float(data_var.min(skipna=True))
    if vmax is None:
        vmax = float(data_var.max(skipna=True))

    fig, ax = setup_map_axes(lon, lat, figsize=(8, 5))
    fig.suptitle(data_var.attrs.get("long_name", var_name), fontsize=12)

    lon2d, lat2d = np.meshgrid(lon, lat)

    field0 = data_var.isel(time=0).values
    quad = ax.pcolormesh(
        lon2d,
        lat2d,
        field0,
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
    )

    units = data_var.attrs.get("units", "")
    if units:
        cbar_label = f"{data_var.attrs.get('long_name', var_name)} [{units}]"
    else:
        cbar_label = data_var.attrs.get("long_name", var_name)
    add_colorbar(fig, ax, quad, cbar_label)

    time_vals = ds["time"].values
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=9,
        bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
    )

    fig.tight_layout()

    def update(frame: int):
        field = data_var.isel(time=frame).values
        quad.set_array(field.ravel())
        time_text.set_text(format_time_label(time_vals[frame]))
        return quad, time_text

    anim = FuncAnimation(fig, update, frames=nt, interval=1000 / fps, blit=False)

    out_gif = Path(out_gif)
    out_gif.parent.mkdir(parents=True, exist_ok=True)

    writer = PillowWriter(fps=fps)
    anim.save(out_gif, writer=writer)

    plt.close(fig)
    print(f"Scalar field animation saved to {out_gif}")


# ---------------------------------------------------------------------------
# Vector field: quiver animation
# ---------------------------------------------------------------------------

def animate_quiver(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_gif: str | Path,
    fps: int = 4,
    stride: int = 10,
    scale: float | None = None,
):
    """
    Animate vector field using quiver (arrows) over a PlateCarree map.
    """
    u = ds[u_name]
    v = ds[v_name]
    lon, lat = get_lon_lat(ds)
    nt = u.sizes["time"]

    speed = np.sqrt(u ** 2 + v ** 2)
    speed_max = float(speed.max(skipna=True))

    fig, ax = setup_map_axes(lon, lat, figsize=(8, 5))
    title = f"{u.attrs.get('long_name', u_name)} / {v.attrs.get('long_name', v_name)}"
    fig.suptitle(title, fontsize=12)

    # Subsample grid
    lon_sub = lon[::stride]
    lat_sub = lat[::stride]
    lon2d, lat2d = np.meshgrid(lon_sub, lat_sub)

    u0 = u.isel(time=0).values[::stride, ::stride]
    v0 = v.isel(time=0).values[::stride, ::stride]
    speed0 = speed.isel(time=0).values[::stride, ::stride]

    norm = plt.Normalize(vmin=0, vmax=speed_max)
    q = ax.quiver(
        lon2d,
        lat2d,
        u0,
        v0,
        speed0,
        transform=ccrs.PlateCarree(),
        cmap="turbo",
        norm=norm,
        scale=scale,
        width=0.003,
        headwidth=3,
        minlength=0.1,
    )

    units = u.attrs.get("units", "")
    cbar_label = f"Speed [{units}]" if units else "Speed"
    add_colorbar(fig, ax, q, cbar_label)

    time_vals = ds["time"].values
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=9,
        bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
    )

    fig.tight_layout()

    def update(frame: int):
        u_f = u.isel(time=frame).values[::stride, ::stride]
        v_f = v.isel(time=frame).values[::stride, ::stride]
        s_f = speed.isel(time=frame).values[::stride, ::stride]
        q.set_UVC(u_f, v_f, s_f)
        time_text.set_text(format_time_label(time_vals[frame]))
        return q, time_text

    anim = FuncAnimation(fig, update, frames=nt, interval=1000 / fps, blit=False)

    out_gif = Path(out_gif)
    out_gif.parent.mkdir(parents=True, exist_ok=True)

    writer = PillowWriter(fps=fps)
    anim.save(out_gif, writer=writer)

    plt.close(fig)
    print(f"Quiver animation saved to {out_gif}")


# ---------------------------------------------------------------------------
# Vector field: particle advection (dots)
# ---------------------------------------------------------------------------

def animate_particles(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_gif: str | Path,
    fps: int = 12,
    n_particles: int = 2000,
    speed_factor: float = 1.0,
):
    """
    Animate particles advected by the vector field (Windy-style dots).
    """
    u = ds[u_name]
    v = ds[v_name]
    lon, lat = get_lon_lat(ds)
    nt = u.sizes["time"]

    fig, ax = setup_map_axes(lon, lat, figsize=(8, 5))
    title = f"Particle flow: {u_name}/{v_name}"
    fig.suptitle(title, fontsize=12)

    # dt between time steps (seconds)
    time_vals = ds["time"].values
    if nt > 1:
        t0 = time_vals[0]
        t1 = time_vals[1]
        dt_seconds = float((np.array(t1) - np.array(t0)) / np.timedelta64(1, "s"))
    else:
        dt_seconds = 6 * 3600  # fallback

    dt_seconds *= speed_factor

    lon_min, lon_max = float(lon.min()), float(lon.max())
    lat_min, lat_max = float(lat.min()), float(lat.max())
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])

    # Seed particles
    rng = np.random.default_rng(42)
    x = rng.uniform(lon_min, lon_max, size=n_particles)
    y = rng.uniform(lat_min, lat_max, size=n_particles)

    scat = ax.scatter(
        x,
        y,
        s=1,
        color="black",
        alpha=0.7,
        transform=ccrs.PlateCarree(),
        linewidths=0,
    )

    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=9,
        bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
    )

    fig.tight_layout()

    u_data = u.values  # (time, lat, lon)
    v_data = v.values

    lon_width = lon_max - lon_min

    def step_particles(t_idx: int, x: np.ndarray, y: np.ndarray):
        ix = ((x - lon_min) / dlon).astype(int)
        iy = ((y - lat_min) / dlat).astype(int)

        ix = np.clip(ix, 0, lon.size - 1)
        iy = np.clip(iy, 0, lat.size - 1)

        u_now = u_data[t_idx, iy, ix]
        v_now = v_data[t_idx, iy, ix]

        # Convert m/s to deg/s
        lat_rad = np.deg2rad(y)
        deg_lat_per_ms = 1.0 / 111_000.0
        deg_lon_per_ms = 1.0 / (111_000.0 * np.cos(lat_rad) + 1e-9)

        x_new = x + u_now * dt_seconds * deg_lon_per_ms
        y_new = y + v_now * dt_seconds * deg_lat_per_ms

        # Wrap/clamp
        x_new = ((x_new - lon_min) % lon_width) + lon_min
        y_new = np.clip(y_new, lat_min, lat_max)

        return x_new, y_new

    # Loop through time indices multiple times
    n_loops = 4
    total_frames = nt * n_loops

    def update(frame: int):
        nonlocal x, y
        t_idx = frame % nt
        x, y = step_particles(t_idx, x, y)
        scat.set_offsets(np.column_stack((x, y)))
        time_text.set_text(format_time_label(time_vals[t_idx]))
        return scat, time_text

    anim = FuncAnimation(
        fig,
        update,
        frames=total_frames,
        interval=1000 / fps,
        blit=False,
    )

    out_gif = Path(out_gif)
    out_gif.parent.mkdir(parents=True, exist_ok=True)

    writer = PillowWriter(fps=fps)
    anim.save(out_gif, writer=writer)

    plt.close(fig)
    print(f"Particle animation saved to {out_gif}")


# ---------------------------------------------------------------------------
# Streamlines + streaking particles (Windy-style)
# ---------------------------------------------------------------------------

def animate_streamlines_with_particles(
    ds: xr.Dataset,
    u_name: str,
    v_name: str,
    out_gif: str | Path,
    fps: int = 18,
    n_particles: int = 3000,
    speed_factor: float = 0.6,
    trail_length: int = 25,
    substeps_per_field: int = 6,
):
    """
    Windy-style animation:

      - Background: very subtle magnitude field (time-mean speed).
      - On top: dense glowing streaklines – particles advected by the
        time-varying vector field, with speed-dependent brightness.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset with dims (time, latitude, longitude).
    u_name, v_name : str
        U and V components, e.g. "uo"/"vo" or "10u"/"10v".
    out_gif : str or Path
        Output GIF path.
    fps : int
        Frames per second.
    n_particles : int
        Number of moving streaks (higher = denser).
    speed_factor : float
        Scales physical dt (lower → slower motion).
    trail_length : int
        Number of stored positions per particle (longer trail).
    substeps_per_field : int
        Animation frames between two consecutive model times.
    """
    u = ds[u_name]
    v = ds[v_name]
    lon, lat = get_lon_lat(ds)
    nt = u.sizes["time"]
    time_vals = ds["time"].values

    # ---- Background: time-mean speed ----
    if nt > 1:
        u_base = u.mean(dim="time").values
        v_base = v.mean(dim="time").values
    else:
        u_base = u.isel(time=0).values
        v_base = v.isel(time=0).values

    speed_base = np.sqrt(u_base ** 2 + v_base ** 2)

    # Global speed for brightness scaling
    speed_all = np.sqrt(u.values ** 2 + v.values ** 2)
    speed_max = np.nanpercentile(speed_all, 98.0)

    fig, ax = setup_map_axes(lon, lat, figsize=(8, 5))
    title = f"Streaklines: {u_name}/{v_name}"
    fig.suptitle(title, fontsize=12)

    # Dark theme
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000814")

    # Subtle background magnitude field
    lon2d, lat2d = np.meshgrid(lon, lat)
    vmax = np.nanpercentile(speed_base, 99.0)
    quad = ax.pcolormesh(
        lon2d,
        lat2d,
        speed_base,
        transform=ccrs.PlateCarree(),
        shading="auto",
        cmap="cividis",
        vmin=0,
        vmax=vmax,
        alpha=0.18,      # much more subtle than before
    )

    units = u.attrs.get("units", "")
    cbar_label = f"Speed [{units}]" if units else "Speed"
    add_colorbar(fig, ax, quad, cbar_label)

    # Bright coasts on top
    ax.coastlines(color="white", linewidth=0.5)

    # ---- Particle seeding over valid ocean points ----
    valid_mask = np.isfinite(speed_base)
    flat_valid = np.where(valid_mask.ravel())[0]
    if flat_valid.size == 0:
        raise RuntimeError("No valid points to seed particles.")

    rng = np.random.default_rng(42)

    def random_valid_positions(n: int) -> tuple[np.ndarray, np.ndarray]:
        idx = rng.choice(flat_valid, size=n, replace=True)
        iy, ix = np.unravel_index(idx, valid_mask.shape)
        return lon[ix], lat[iy]

    # Initial particle positions
    x, y = random_valid_positions(n_particles)

    # Trail buffers: col 0 = newest, last col = oldest
    trail_x = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_y = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_speed = np.full((n_particles, trail_length), np.nan, dtype=float)
    trail_x[:, 0] = x
    trail_y[:, 0] = y

    # LineCollection for streaks
    n_segments = n_particles * (trail_length - 1)
    dummy_segments = np.zeros((n_segments, 2, 2), dtype=float)
    lc = mcoll.LineCollection(
        dummy_segments,
        linewidths=1.0,     # a bit thicker
        linestyle="solid",
        capstyle="round",
    )

    # Base golden RGB
    gold_rgb = (249 / 255.0, 229 / 255.0, 102 / 255.0)

    # Fading alpha along each trail (newest → oldest)
    alpha_levels = np.linspace(1.0, 0.05, trail_length - 1)
    alpha_seg_template = np.tile(alpha_levels, n_particles)

    # Initial color array (will be updated every frame)
    colors = np.empty((n_segments, 4), dtype=float)
    colors[:, 0] = gold_rgb[0]
    colors[:, 1] = gold_rgb[1]
    colors[:, 2] = gold_rgb[2]
    colors[:, 3] = alpha_seg_template
    lc.set_color(colors)
    lc.set_transform(ccrs.PlateCarree())
    ax.add_collection(lc)

    # Time label
    time_text = ax.text(
        0.01,
        0.01,
        format_time_label(time_vals[0]),
        transform=ax.transAxes,
        fontsize=9,
        color="white",
        bbox=dict(facecolor="black", alpha=0.6, edgecolor="none"),
    )

    fig.tight_layout()

    # ---- Vector data & geometric constants ----
    u_data = u.values  # (time, lat, lon)
    v_data = v.values

    lon_min, lon_max = float(lon.min()), float(lon.max())
    lat_min, lat_max = float(lat.min()), float(lat.max())
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])
    lon_width = lon_max - lon_min

    # Threshold for "too big" jumps (for breaking trails)
    jump_lon = 5.0 * dlon
    jump_lat = 5.0 * dlat

    # Physical dt per model step
    if nt > 1:
        t0 = time_vals[0]
        t1 = time_vals[1]
        dt_model = float((np.array(t1) - np.array(t0)) / np.timedelta64(1, "s"))
    else:
        dt_model = 6 * 3600.0

    dt_seconds = (dt_model / substeps_per_field) * speed_factor

    def step_particles(
        t_idx: int, x: np.ndarray, y: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Move particles one small step using field at coarse time index t_idx.

        Returns
        -------
        x_new, y_new : new positions
        speed_now    : speed at new positions
        reseeded     : boolean mask where particle was reseeded
        """
        ix = ((x - lon_min) / dlon).astype(int)
        iy = ((y - lat_min) / dlat).astype(int)

        ix = np.clip(ix, 0, lon.size - 1)
        iy = np.clip(iy, 0, lat.size - 1)

        u_now = u_data[t_idx, iy, ix]
        v_now = v_data[t_idx, iy, ix]

        # handle invalid / land points by reseeding
        bad = ~np.isfinite(u_now) | ~np.isfinite(v_now)
        if np.any(bad):
            new_x, new_y = random_valid_positions(bad.sum())
            x = x.copy()
            y = y.copy()
            x[bad] = new_x
            y[bad] = new_y
            u_now[bad] = 0.0
            v_now[bad] = 0.0

        speed_now = np.sqrt(u_now ** 2 + v_now ** 2)

        # Convert m/s to deg/s
        lat_rad = np.deg2rad(y)
        deg_lat_per_ms = 1.0 / 111_000.0
        deg_lon_per_ms = 1.0 / (111_000.0 * np.cos(lat_rad) + 1e-9)

        x_new = x + u_now * dt_seconds * deg_lon_per_ms
        y_new = y + v_now * dt_seconds * deg_lat_per_ms

        # Wrap longitude, clip latitude
        x_new = ((x_new - lon_min) % lon_width) + lon_min
        y_new = np.clip(y_new, lat_min, lat_max)

        return x_new, y_new, speed_now, bad

    # Total frames: multiple loops over time, with substeps per model time
    n_loops = 4
    total_frames = nt * substeps_per_field * n_loops

    def update(frame: int):
        nonlocal x, y, trail_x, trail_y, trail_speed

        # Which coarse model time index we are between
        coarse_idx = (frame // substeps_per_field) % nt

        # Move particles
        x_new, y_new, speed_now, reseeded = step_particles(coarse_idx, x, y)
        x, y = x_new, y_new

        # Shift trails to the right, insert new head
        trail_x[:, 1:] = trail_x[:, :-1]
        trail_y[:, 1:] = trail_y[:, :-1]
        trail_speed[:, 1:] = trail_speed[:, :-1]
        trail_x[:, 0] = x
        trail_y[:, 0] = y
        trail_speed[:, 0] = speed_now

        # Break trails where particles were reseeded
        if np.any(reseeded):
            trail_x[reseeded, 1:] = np.nan
            trail_y[reseeded, 1:] = np.nan
            trail_speed[reseeded, 1:] = np.nan

        # Break trails for excessively large jumps (wrap/glitches)
        dx = np.abs(trail_x[:, 0] - trail_x[:, 1])
        dy = np.abs(trail_y[:, 0] - trail_y[:, 1])
        dx = np.minimum(dx, lon_width - dx)  # periodic lon
        big_jump = (dx > jump_lon) | (dy > jump_lat)
        if np.any(big_jump):
            trail_x[big_jump, 1:] = np.nan
            trail_y[big_jump, 1:] = np.nan
            trail_speed[big_jump, 1:] = np.nan

        # Build segments from trail buffers (vectorized)
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

        lc.set_segments(segments)

        # --- Speed-dependent brightness along the trails ---
        # Segment speed = mean of speed at its two end points
        seg_speed = (trail_speed[:, :-1] + trail_speed[:, 1:]) * 0.5
        seg_speed_flat = seg_speed.ravel()

        # Normalize speed to [0, 1]
        s_norm = np.clip(seg_speed_flat / (speed_max + 1e-9), 0.0, 1.0)
        # Intensity between 0.2 and 1.0 (so slow flows still visible)
        intensity = 0.2 + 0.8 * s_norm

        # Update alpha: fade along trail *and* with speed
        colors[:, 0] = gold_rgb[0]
        colors[:, 1] = gold_rgb[1]
        colors[:, 2] = gold_rgb[2]
        colors[:, 3] = alpha_seg_template * intensity
        lc.set_color(colors)

        time_text.set_text(format_time_label(time_vals[coarse_idx]))
        return lc, time_text

    anim = FuncAnimation(
        fig,
        update,
        frames=total_frames,
        interval=1000 / fps,
        blit=False,
    )

    out_gif = Path(out_gif)
    out_gif.parent.mkdir(parents=True, exist_ok=True)

    writer = PillowWriter(fps=fps)
    anim.save(out_gif, writer=writer)

    plt.close(fig)
    print(f"Streamlines + streaking particles animation saved to {out_gif}")




# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Create Windy-style GIFs from Copernicus NetCDF.")
    p.add_argument("--nc", required=True, help="Path to NetCDF file")
    p.add_argument(
        "--mode",
        choices=["scalar", "quiver", "particles", "streamlines"],
        required=True,
        help="Type of animation to create",
    )
    p.add_argument("--var", help="Scalar variable name (for mode=scalar)")
    p.add_argument("--uvar", help="U-component variable name (for vector modes)")
    p.add_argument("--vvar", help="V-component variable name (for vector modes)")
    p.add_argument("--out", required=True, help="Output GIF path")
    p.add_argument("--fps", type=int, default=6, help="Frames per second")
    return p.parse_args()


def main():
    args = parse_args()
    ds = load_copernicus_dataset(args.nc)

    # Note: variables like "2t", "10u", "10v" might appear in ncdump as \2t, \10u, \10v.
    # Check with:
    #   import xarray as xr
    #   print(xr.open_dataset(path).data_vars)

    mode = args.mode

    if mode == "scalar":
        if args.var is None:
            raise SystemExit("--var is required for mode=scalar")
        animate_scalar_field(
            ds,
            var_name=args.var,
            out_gif=args.out,
            fps=args.fps,
        )

    elif mode == "quiver":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=quiver")
        animate_quiver(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_gif=args.out,
            fps=args.fps,
        )

    elif mode == "particles":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=particles")
        animate_particles(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_gif=args.out,
            fps=args.fps,
        )

    elif mode == "streamlines":
        if args.uvar is None or args.vvar is None:
            raise SystemExit("--uvar and --vvar are required for mode=streamlines")
        animate_streamlines_with_particles(
            ds,
            u_name=args.uvar,
            v_name=args.vvar,
            out_gif=args.out,
            fps=args.fps,
        )


if __name__ == "__main__":
    main()

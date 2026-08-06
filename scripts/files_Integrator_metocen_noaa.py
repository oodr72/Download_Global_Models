#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrador NOAA (GFS + HYCOM + WW3) en una malla común (por defecto: WW3)
--------------------------------------------------------------------------

Autores: Amilcar E. Calzada & Oscar O. Diaz
Colaboración: (asistencia de IA)
Objetivo: Creación de datos atmosféricos y oceánicos para una región predeterminada
          a partir de modelos globales (NOAA: GFS, HYCOM, WW3)
Tipo de datos: Rejilla regular lon/lat sin niveles (superficie), paso temporal 6 h
Interpolación: Bilineal por defecto hacia la malla objetivo (WW3 u otra provista)

Entradas (archivos por tiempo, cada 6 horas):
  - Atmosférico (GFS): 2t, 10u, 10v  (niveles lógicos: 2t -> nivel 0; 10u/10v -> nivel 1)
      patrón: ./gfs/gfs_aaaammddHH.nc
  - Hidrodinámico (HYCOM): u_velocity, v_velocity, sst (grilla curvilínea)
      patrón: ./hycom/hycom_aaaammddHH.nc
  - Oleaje (WW3): swh, perpw, dirpw, shww, mpww, wvdir, ws, wdir, shts, mpts
      patrón: ./ww3/ww3_aaaammddHH.nc

Salida:
  - Un archivo NetCDF único con dimensiones (longitude, latitude, time) y todas
    las variables integradas.

Uso (ejemplo):
  python Integrator_ocean-atmosphere_noaa_project.py \
    --start 2024010100 --end 2024010300 --dt_hours 6 \
    --path_ahm "./hycom/hycom_aaaammddHH.nc" \
    --path_aam "./gfs/gfs_aaaammddHH.nc" \
    --path_awm "./ww3/ww3_aaaammddHH.nc" \
    --out integrated_ww3_grid.nc

Notas:
  - Manejo de memoria con xarray + chunks (dask opcional).
  - Lectura con engine 'h5netcdf' para evitar segfaults de netCDF4/HDF5.
  - decode_timedelta=True para silenciar warnings futuros de xarray.
  - Remapeo curvilíneo con xESMF si disponible; SciPy griddata como fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import numpy as np
import xarray as xr

# xESMF opcional (puede fallar si no hay esmpy/ESMF)
try:
    import xesmf as xe  # type: ignore
    _HAS_XESMF = True
except Exception:
    xe = None  # type: ignore
    _HAS_XESMF = False

from scipy.interpolate import griddata

# --------------------------
# Helpers
# --------------------------
_LEVEL_NAMES = ("level", "lev", "hybrid", "isobaricInhPa", "depth", "Layer", "z")


def _to_numpy(a):
    return a.data if hasattr(a, "data") else np.asarray(a)


def _ensure_dataarray_2d(a, dim_y="y", dim_x="x"):
    if isinstance(a, xr.DataArray):
        if a.ndim != 2:
            raise ValueError(
                f"Se esperaba 2D para lon/lat; llegó con dims {a.dims} y shape {a.shape}"
            )
        da = a
        # Normalizar nombres de dims a (y,x)
        map_dims: dict[str, str] = {}
        if dim_y not in da.dims or dim_x not in da.dims:
            cand_y = [
                d for d in da.dims if d.lower() in ("y", "lat", "latitude", "j", "ny")
            ]
            cand_x = [
                d for d in da.dims if d.lower() in ("x", "lon", "longitude", "i", "nx")
            ]
            if cand_y and cand_x:
                map_dims = {cand_y[0]: dim_y, cand_x[0]: dim_x}
        if map_dims:
            da = da.rename(map_dims)
        return da
    else:
        arr = np.asarray(a)
        if arr.ndim != 2:
            raise ValueError(
                f"Se esperaba 2D numpy para lon/lat; llegó con shape {arr.shape}"
            )
        return xr.DataArray(arr, dims=(dim_y, dim_x))


def _rename_spatial_dims_to_yx(da: xr.DataArray) -> xr.DataArray:
    """Renombra dims espaciales a (y,x) sin tocar time/otras."""
    rename: dict[str, str] = {}
    for d in da.dims:
        dl = d.lower()
        if dl in ("lat", "latitude", "j", "ny"):
            rename[d] = "y"
        if dl in ("lon", "longitude", "i", "nx"):
            rename[d] = "x"
    if rename:
        da = da.rename(rename)
    return da


def _squeeze_singleton_levels(da: xr.DataArray) -> xr.DataArray:
    """Quita dimensión vertical si es singleton."""
    for zn in _LEVEL_NAMES:
        if zn in da.dims:
            if da.sizes.get(zn, 1) == 1:
                da = da.isel({zn: 0}).squeeze(drop=True)
    return da


def _guess_weights_name(method: str, src_shape, tgt_shape) -> str:
    key = f"{method}|src:{src_shape}|tgt:{tgt_shape}"
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"weights_{method}_{src_shape[0]}x{src_shape[1]}_to_{tgt_shape[0]}x{tgt_shape[1]}_{h}.nc"


def _make_regridder(src, tgt, method="bilinear", filename=None, periodic=None):
    if not _HAS_XESMF:
        raise RuntimeError("xESMF no disponible; no se puede crear Regridder.")
    if filename is None:
        filename = _guess_weights_name(method, src["lon"].shape, tgt["lon"].shape)
    kw = dict(filename=filename)
    if periodic is not None:
        kw["periodic"] = periodic
    if os.path.exists(filename):
        return xe.Regridder(src, tgt, method, reuse_weights=True, **kw)
    else:
        return xe.Regridder(src, tgt, method, reuse_weights=False, **kw)


# --------------------------
# Interpolación curvilínea
# --------------------------
def _interp_curvilinear_to_regular(
    ds: xr.Dataset,
    lon2d,
    lat2d,
    lon_tgt,
    lat_tgt,
    variables=None,
    *,
    method: str = "bilinear",
    weights_name: Optional[str] = None,
    periodic: Optional[bool] = None,
) -> xr.Dataset:
    """
    Interpola un Dataset curvilíneo (lon2d, lat2d) a grilla regular (lon_tgt, lat_tgt).

    - Si xESMF está disponible -> usa xESMF (bilinear, etc.).
    - Si xESMF NO está disponible -> fallback con SciPy griddata (linear/nearest).

    Devuelve Dataset con dims (longitude, latitude, time, ...) cuando aplica.
    """
    # --- Normalizar lon/lat fuente a DataArray 2D con dims (y,x)
    lon2d = _ensure_dataarray_2d(lon2d, "y", "x")
    lat2d = _ensure_dataarray_2d(lat2d, "y", "x")

    # --- Asegurar target 1D numpy
    lon1 = _to_numpy(lon_tgt).ravel()
    lat1 = _to_numpy(lat_tgt).ravel()

    # ------------------------#
    # Camino con xESMF        #
    # ------------------------#
    if _HAS_XESMF:
        lon2d_tgt, lat2d_tgt = np.meshgrid(lon1, lat1)
        src = xr.Dataset({"lon": lon2d, "lat": lat2d})
        tgt = xr.Dataset(
            {
                "lon": (["y", "x"], lon2d_tgt),
                "lat": (["y", "x"], lat2d_tgt),
            }
        )

        regridder = _make_regridder(
            src, tgt, method=method, filename=weights_name, periodic=periodic
        )

        if variables is None:
            variables = [
                v for v in ds.data_vars if np.issubdtype(ds[v].dtype, np.number)
            ]

        out = xr.Dataset()
        for v in variables:
            if v not in ds:
                continue
            da = ds[v]
            da = _squeeze_singleton_levels(da)
            da = _rename_spatial_dims_to_yx(da)

            if not {"y", "x"}.issubset(set(da.dims)):
                raise ValueError(
                    f"La variable '{v}' no tiene dims espaciales (y,x) tras normalización; dims={da.dims}"
                )

            # Recortar si lon2d tiene una columna extra respecto a la variable
            ny_src, nx_src = lon2d.shape
            ny, nx = da.sizes["y"], da.sizes["x"]
            lon2d_v = lon2d
            lat2d_v = lat2d
            if ny_src != ny or nx_src != nx:
                if ny_src < ny or nx_src < nx:
                    raise ValueError(
                        f"lon/lat 2D ({ny_src},{nx_src}) más pequeños que datos ({ny},{nx}) para '{v}'"
                    )
                lon2d_v = lon2d_v.isel(y=slice(0, ny), x=slice(0, nx))
                lat2d_v = lat2d_v.isel(y=slice(0, ny), x=slice(0, nx))

            # Regridder ignora coords; usamos el original regridder construido
            out[v] = regridder(da)

        out = out.assign_coords(
            {
                "latitude": ("y", lat1),
                "longitude": ("x", lon1),
            }
        ).swap_dims({"y": "latitude", "x": "longitude"})
        out = out.transpose("longitude", "latitude", "time", ...)
        return out

    # ------------------------#
    # Fallback con SciPy      #
    # ------------------------#
    if variables is None:
        variables = [v for v in ds.data_vars if np.issubdtype(ds[v].dtype, np.number)]

    method_scipy = "linear" if method in ("bilinear", "linear") else "nearest"

    # Precomputar malla destino
    lon2d_tgt, lat2d_tgt = np.meshgrid(lon1, lat1)
    points_tgt = np.column_stack([lon2d_tgt.ravel(), lat2d_tgt.ravel()])

    out = xr.Dataset()

    for v in variables:
        if v not in ds:
            continue
        da = ds[v]
        da = _squeeze_singleton_levels(da)
        da = _rename_spatial_dims_to_yx(da)

        dims = list(da.dims)
        if "y" not in dims or "x" not in dims:
            raise ValueError(
                f"La variable '{v}' no tiene dims espaciales (y,x) tras normalización; dims={da.dims}"
            )

        ny, nx = da.sizes["y"], da.sizes["x"]

        # Alinear lon/lat a las dimensiones de la variable
        lon2d_v = lon2d
        lat2d_v = lat2d
        ny_src, nx_src = lon2d_v.shape
        if ny_src != ny or nx_src != nx:
            if ny_src < ny or nx_src < nx:
                raise ValueError(
                    f"lon/lat 2D ({ny_src},{nx_src}) más pequeños que datos ({ny},{nx}) para '{v}'"
                )
            lon2d_v = lon2d_v.isel(y=slice(0, ny), x=slice(0, nx))
            lat2d_v = lat2d_v.isel(y=slice(0, ny), x=slice(0, nx))

        lon_src = lon2d_v.values
        lat_src = lat2d_v.values
        points_src = np.column_stack([lon_src.ravel(), lat_src.ravel()])

        if "time" in dims:
            da = da.transpose("time", "y", "x")
            data = da.values  # (nt, ny, nx)
            nt, ny, nx = data.shape
            out_vals = np.full(
                (nt, lat1.size, lon1.size),
                np.nan,
                dtype=float,
            )

            for it in range(nt):
                vals_src = np.asarray(data[it]).ravel()
                mask = np.isfinite(vals_src)
                if mask.sum() < 3:
                    continue
                vals_tgt = griddata(
                    points_src[mask],
                    vals_src[mask],
                    points_tgt,
                    method=method_scipy,
                    fill_value=np.nan,
                )
                out_vals[it] = vals_tgt.reshape(lat1.size, lon1.size)

            da_new = xr.DataArray(
                out_vals,
                dims=("time", "latitude", "longitude"),
                coords={
                    "time": da["time"].values,
                    "latitude": lat1,
                    "longitude": lon1,
                },
                attrs=da.attrs,
                name=v,
            )
        else:
            da = da.transpose("y", "x")
            data = da.values  # (ny, nx)
            vals_src = np.asarray(data).ravel()
            mask = np.isfinite(vals_src)
            if mask.sum() < 3:
                out_vals = np.full((lat1.size, lon1.size), np.nan, dtype=float)
            else:
                vals_tgt = griddata(
                    points_src[mask],
                    vals_src[mask],
                    points_tgt,
                    method=method_scipy,
                    fill_value=np.nan,
                )
                out_vals = vals_tgt.reshape(lat1.size, lon1.size)

            da_new = xr.DataArray(
                out_vals,
                dims=("latitude", "longitude"),
                coords={"latitude": lat1, "longitude": lon1},
                attrs=da.attrs,
                name=v,
            )

        out[v] = da_new

    # Asegurar orden de dims
    for v in out.data_vars:
        if set(out[v].dims) >= {"longitude", "latitude", "time"}:
            out[v] = out[v].transpose("longitude", "latitude", "time", ...)
        elif set(out[v].dims) >= {"longitude", "latitude"}:
            out[v] = out[v].transpose("longitude", "latitude", ...)

    return out


# ------------------------------------------------------------------
# Tiempo y paths
# ------------------------------------------------------------------
def _build_times(start: str, end: str, dt_hours: int = 6) -> List[datetime]:
    t0 = datetime.strptime(start, "%Y%m%d%H")
    t1 = datetime.strptime(end, "%Y%m%d%H")
    if t1 < t0:
        raise ValueError("--end debe ser >= --start")
    out = []
    cur = t0
    step = timedelta(hours=dt_hours)
    while cur <= t1:
        out.append(cur)
        cur += step
    return out


def _ensure_template(path_or_template: str, model: str) -> str:
    """Garantiza un template con 'aaaammddHH' o construye uno desde un directorio."""
    if os.path.isdir(path_or_template):
        defaults = {
            "HYCOM": "hycom_aaaammddHH.nc",
            "GFS": "gfs_aaaammddHH.nc",
            "WW3": "ww3_aaaammddHH.nc",
        }
        fname = defaults.get(model.upper(), "file_aaaammddHH.nc")
        return os.path.join(path_or_template, fname)
    if "aaaammddHH" not in path_or_template:
        raise ValueError(
            f"El argumento para {model} debe contener 'aaaammddHH' o ser un directorio. "
            f"Recibido: {path_or_template}"
        )
    return path_or_template


def _expand_template(template: str, t: datetime) -> str:
    return template.replace("aaaammddHH", t.strftime("%Y%m%d%H"))


def _exists_all(paths: List[str]) -> List[str]:
    return [p for p in paths if not os.path.exists(p)]


def _ensure_latlon_names(
    ds: xr.Dataset,
    lon_aliases=("lon", "longitude", "x"),
    lat_aliases=("lat", "latitude", "y"),
) -> xr.Dataset:
    """Renombra coordenadas/dimensiones 1D a 'longitude'/'latitude' si aplica.
    No fuerza nada si son variables 2D (curvilíneo).
    """
    if (
        "longitude" in ds
        and "latitude" in ds
        and (ds["longitude"].ndim == 2 or ds["latitude"].ndim == 2)
    ):
        return ds
    lon_name = None
    lat_name = None
    for n in lon_aliases:
        if n in ds.coords or n in ds.dims:
            lon_name = n
            break
    for n in lat_aliases:
        if n in ds.coords or n in ds.dims:
            lat_name = n
            break
    rename: dict[str, str] = {}
    if lon_name and lon_name != "longitude":
        rename[lon_name] = "longitude"
    if lat_name and lat_name != "latitude":
        rename[lat_name] = "latitude"
    if rename:
        ds = ds.rename(rename)
    return ds


def _standardize_lon_to_180(
    ds: xr.Dataset, lon_names: Tuple[str, ...] = ("lon", "longitude")
) -> xr.Dataset:
    lon_name = None
    for name in lon_names:
        if name in ds.coords or name in ds.dims:
            lon_name = name
            break
    if lon_name is None:
        return ds
    lon = ds[lon_name]
    if np.nanmax(lon.values) > 180:
        new_lon = ((lon + 180) % 360) - 180
        ds = ds.assign_coords({lon_name: new_lon})
        ds = ds.sortby(lon_name)
    return ds


def _open_concat(
    files: List[str],
    chunks: Optional[dict] = None,
    vars_keep: Optional[List[str]] = None,
    engine: str = "h5netcdf",
) -> xr.Dataset:
    """Abre secuencialmente una lista de archivos y concatena en 'time'."""
    if len(files) == 0:
        raise ValueError("No se proporcionaron archivos para abrir.")

    datasets: list[xr.Dataset] = []
    for f in files:
        if not os.path.exists(f):
            raise FileNotFoundError(f"Archivo no encontrado: {f}")
        ds = xr.open_dataset(
            f,
            engine=engine,
            chunks=chunks if chunks is not None else "auto",
            decode_times=True,
            decode_timedelta=True,
        )
        if vars_keep is not None:
            keep = [v for v in vars_keep if v in ds]
            ds = ds[keep]
        datasets.append(ds)

    ds_all = xr.concat(datasets, dim="time")
    return ds_all


# ------------------------------------------------------------------
# Construcción de malla objetivo
# ------------------------------------------------------------------
def _grid_from_griddes_txt(path_txt: str) -> Tuple[np.ndarray, np.ndarray]:
    with open(path_txt, "r") as f:
        txt = f.read()

    def _get(key: str, cast=float):
        m = re.search(rf"{key}\s*=\s*([\-0-9\.eE]+)", txt)
        if not m:
            raise ValueError(f"Clave '{key}' no encontrada en griddes")
        return cast(m.group(1))

    xsize = int(_get("xsize", int))
    ysize = int(_get("ysize", int))
    xfirst = _get("xfirst")
    yfirst = _get("yfirst")
    xinc = _get("xinc")
    yinc = _get("yinc")
    lon = xfirst + np.arange(xsize) * xinc
    lat = yfirst + np.arange(ysize) * yinc
    return lon, lat


# ------------------------------------------------------------------
# Model readers
# ------------------------------------------------------------------
def _read_gfs(path_template: str, times: List[datetime]) -> xr.Dataset:
    files = [_expand_template(path_template, t) for t in times]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError(f"GFS files not found: {missing}")
    vars_keep = ["2t", "10u", "10v", "t", "u", "v", "UGRD", "VGRD", "TMP"]
    ds = _open_concat(files, vars_keep=vars_keep, engine="h5netcdf")
    # Normalize variable names
    rename_map = {
        "UGRD": "10u", "VGRD": "10v", "TMP": "2t",
        "u": "10u", "v": "10v", "t": "2t"
    }
    ds = ds.rename({k: v for k, v in rename_map.items() if k in ds})
    # Keep only surface levels
    if "10u" in ds:
        ds_10u = ds["10u"]
        ds_10v = ds["10v"]
        ds_2t = ds.get("2t", ds.get("TMP", None))
        if ds_10u is not None and "level" in ds_10u.dims and ds_10u.sizes.get("level", 1) > 1:
            # Keep only level=10 or level=10m equivalent
            levels = ds_10u["level"].values
            idx = np.argmin(np.abs(levels - 10))
            ds_10u = ds_10u.isel(level=int(idx))
            ds_10v = ds["10v"].isel(level=int(idx)) if "10v" in ds else None
            if ds_2t is not None and "isobaricInhPa" in ds_2t.dims:
                ds_2t = ds_2t.isel(isobaricInhPa=0)
        ds_final = xr.Dataset()
        ds_final["10u"] = ds_10u
        if ds_10v is not None:
            ds_final["10v"] = ds_10v
        if ds_2t is not None:
            ds_final["2t"] = ds_2t
        return _ensure_latlon_names(ds_final)
    return _ensure_latlon_names(ds[[v for v in ["10u", "10v", "2t"] if v in ds]])


def _read_hycom(path_template: str, times: List[datetime]) -> xr.Dataset:
    files = [_expand_template(path_template, t) for t in times]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError(f"HYCOM/RTOFS files not found: {missing}")
    vars_keep = ["u_velocity", "v_velocity", "sst", "water_u", "water_v", "water_temp"]
    ds = _open_concat(files, vars_keep=vars_keep, engine="h5netcdf")
    # Rename to standard names
    rename_map = {
        "water_u": "u_velocity", "water_v": "v_velocity",
        "water_temp": "sst"
    }
    ds = ds.rename({k: v for k, v in rename_map.items() if k in ds})
    return ds[[v for v in ["u_velocity", "v_velocity", "sst"] if v in ds]]


def _read_ww3(path_template: str, times: List[datetime]) -> xr.Dataset:
    files = [_expand_template(path_template, t) for t in times]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError(f"WW3 files not found: {missing}")
    vars_keep = ["swh", "perpw", "dirpw", "shww", "mpww", "wvdir", "ws", "wdir", 
                 "shts", "mpts", "wave_height", "wave_period", "wave_direction"]
    ds = _open_concat(files, vars_keep=vars_keep, engine="h5netcdf")
    # Normalize variable names if needed
    rename_map = {
        "wave_height": "swh", "wave_period": "mpww", "wave_direction": "wvdir"
    }
    ds = ds.rename({k: v for k, v in rename_map.items() if k in ds})
    return ds[[v for v in vars_keep if v in ds]]


# ------------------------------------------------------------------
# Template from directory (auto-discover files)
# ------------------------------------------------------------------
def _auto_template_from_dir(dirpath: str, model: str) -> str:
    """If input is a directory, auto-discover file pattern and build template."""
    if not os.path.isdir(dirpath):
        return None  # Not a directory, use as-is
    files = sorted([f for f in os.listdir(dirpath) if f.endswith(".nc")])
    if not files:
        raise FileNotFoundError(f"No .nc files in {dirpath}")
    # Default template based on model
    defaults = {
        "HYCOM": "hycom_aaaammddHH.nc",
        "GFS": "gfs_aaaammddHH.nc",
        "WW3": "ww3_aaaammddHH.nc",
    }
    fname = defaults.get(model.upper(), "file_aaaammddHH.nc")
    return os.path.join(dirpath, fname)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Integrador NOAA: GFS + HYCOM/RTOFS + WW3 en malla com\u00fan"
    )
    parser.add_argument("--start", required=True, help="Start time YYYYMMDDHH")
    parser.add_argument("--end", required=True, help="End time YYYYMMDDHH")
    parser.add_argument("--dt_hours", type=int, default=6, help="Time step in hours")
    parser.add_argument("--path_ahm", required=True,
                        help="Path template for HYCOM (with 'aaaammddHH') or directory")
    parser.add_argument("--path_aam", required=True,
                        help="Path template for GFS (with 'aaaammddHH') or directory")
    parser.add_argument("--path_awm", required=True,
                        help="Path template for WW3 (with 'aaaammddHH') or directory")
    parser.add_argument("--out", required=True, help="Output NetCDF path")
    parser.add_argument("--target_grid", default=None,
                        help="griddes.txt path for target grid (optional)")
    parser.add_argument("--method", default="bilinear",
                        choices=["bilinear", "nearest"],
                        help="Interpolation method")
    parser.add_argument("--chunk_lon", type=int, default=200,
                        help="Chunk size for longitude")
    parser.add_argument("--chunk_lat", type=int, default=200,
                        help="Chunk size for latitude")
    parser.add_argument("--chunk_time", type=int, default=10,
                        help="Chunk size for time")

    args = parser.parse_args()

    # Build file templates
    path_hycom = _auto_template_from_dir(args.path_ahm, "HYCOM") or args.path_ahm
    path_gfs = _auto_template_from_dir(args.path_aam, "GFS") or args.path_aam
    path_ww3 = _auto_template_from_dir(args.path_awm, "WW3") or args.path_awm

    path_hycom = _ensure_template(path_hycom, "HYCOM")
    path_gfs = _ensure_template(path_gfs, "GFS")
    path_ww3 = _ensure_template(path_ww3, "WW3")

    # Build time list
    times = _build_times(args.start, args.end, args.dt_hours)
    print(f"Processing {len(times)} time steps: {times[0]} to {times[-1]}")

    # ------------------------------------------------ 
    # 1. Read and concatenate source datasets
    # ------------------------------------------------ 
    print("Reading GFS data...")
    ds_gfs = _read_gfs(path_gfs, times)
    ds_gfs = _standardize_lon_to_180(ds_gfs)
    print(f"  GFS: {dict(ds_gfs.sizes)}")

    print("Reading HYCOM/RTOFS data...")
    ds_hycom = _read_hycom(path_hycom, times)
    print(f"  HYCOM: {dict(ds_hycom.sizes)}")

    print("Reading WW3 data...")
    ds_ww3 = _read_ww3(path_ww3, times)
    ds_ww3 = _standardize_lon_to_180(ds_ww3)
    print(f"  WW3: {dict(ds_ww3.sizes)}")

    # ------------------------------------------------ 
    # 2. Determine target grid (default: WW3)
    # ------------------------------------------------ 
    if args.target_grid:
        lon_tgt, lat_tgt = _grid_from_griddes_txt(args.target_grid)
        print(f"Using target grid from griddes.txt: {len(lon_tgt)}x{len(lat_tgt)}")
    else:
        # Use WW3 grid as target
        lon_tgt = _to_numpy(ds_ww3["longitude"] if "longitude" in ds_ww3 else ds_ww3["lon"])
        lat_tgt = _to_numpy(ds_ww3["latitude"] if "latitude" in ds_ww3 else ds_ww3["lat"])
        print(f"Using WW3 grid as target: {len(lon_tgt)}x{len(lat_tgt)}")

    # ------------------------------------------------ 
    # 3. Interpolate to target grid
    # ------------------------------------------------ 
    out_datasets = []

    # WW3: already on target grid (or close)
    if set(ds_ww3.dims) >= {"longitude", "latitude"}:
        out_datasets.append(ds_ww3)
    else:
        # If WW3 has different grid, interpolate
        lon2d = ds_ww3["longitude"] if "longitude" in ds_ww3 else ds_ww3["lon"]
        lat2d = ds_ww3["latitude"] if "latitude" in ds_ww3 else ds_ww3["lat"]
        if lon2d.ndim == 2:
            ww3_regridded = _interp_curvilinear_to_regular(
                ds_ww3, lon2d, lat2d, lon_tgt, lat_tgt, method=args.method
            )
            out_datasets.append(ww3_regridded)
        else:
            out_datasets.append(ds_ww3)

    # GFS: regular grid, interpolate to target
    gfs_ds = ds_gfs
    if "longitude" not in gfs_ds and "lon" in gfs_ds:
        gfs_ds = gfs_ds.rename({"lon": "longitude", "lat": "latitude"})
    gfs_1d_lon = _to_numpy(gfs_ds["longitude"])
    gfs_1d_lat = _to_numpy(gfs_ds["latitude"])
    if not np.allclose(gfs_1d_lon, lon_tgt) or not np.allclose(gfs_1d_lat, lat_tgt):
        print("Regridding GFS to target grid...")
        # Create 2D mesh from 1D for interpolation (GFS has regular grid)
        lon2d, lat2d = np.meshgrid(gfs_1d_lon, gfs_1d_lat)
        gfs_2d = xr.Dataset({
            "lon": (["y", "x"], lon2d),
            "lat": (["y", "x"], lat2d)
        })
        for v in gfs_ds.data_vars:
            gfs_2d[v] = gfs_ds[v].values
            if "longitude" in gfs_ds[v].dims:
                gfs_2d[v] = gfs_2d[v].rename({"longitude": "x", "latitude": "y"})
        gfs_regridded = _interp_curvilinear_to_regular(
            gfs_2d, gfs_2d["lon"], gfs_2d["lat"], lon_tgt, lat_tgt,
            variables=list(gfs_2d.data_vars), method=args.method
        )
        out_datasets.append(gfs_regridded)
    else:
        out_datasets.append(gfs_ds)

    # HYCOM: curvilinear grid (needs special handling)
    if "longitude" in ds_hycom and ds_hycom["longitude"].ndim == 2:
        print("Regridding HYCOM (curvilinear) to target grid...")
        hycom_regridded = _interp_curvilinear_to_regular(
            ds_hycom,
            ds_hycom["longitude"],
            ds_hycom["latitude"],
            lon_tgt,
            lat_tgt,
            variables=[v for v in ds_hycom.data_vars],
            method=args.method
        )
        out_datasets.append(hycom_regridded)
    else:
        out_datasets.append(ds_hycom)

    # ------------------------------------------------ 
    # 4. Merge all datasets
    # ------------------------------------------------ 
    print("Merging all datasets...")
    ds_merged = xr.merge(out_datasets)

    # ------------------------------------------------ 
    # 5. Save output with compression
    # ------------------------------------------------ 
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    
    encoding = {}
    for var_name in ds_merged.data_vars:
        encoding[var_name] = {
            "zlib": True,
            "complevel": 4,
            "chunksizes": (args.chunk_time, args.chunk_lat, args.chunk_lon)
        }
    
    ds_merged.to_netcdf(
        args.out,
        engine="netcdf4",
        encoding=encoding,
        format="NETCDF4",
        mode="w"
    )
    print(f"\nSaved integrated file: {args.out}")
    print(f"  Dimensions: {dict(ds_merged.sizes)}")
    print(f"  Variables: {list(ds_merged.data_vars)}")


if __name__ == "__main__":
    main()


def _grid_from_nc(path_nc: str) -> Tuple[np.ndarray, np.ndarray]:
    ds = xr.open_dataset(path_nc, engine="h5netcdf", decode_timedelta=True)
    ds = _ensure_latlon_names(ds)
    lon = ds["longitude"].values
    lat = ds["latitude"].values
    ds.close()
    return lon, lat


# ------------------------------------------------------------------
# Remapeos regulares
# ------------------------------------------------------------------
def _interp_regular_to_regular(
    ds: xr.Dataset, lon_tgt: xr.DataArray, lat_tgt: xr.DataArray
) -> xr.Dataset:
    return ds.interp(longitude=lon_tgt, latitude=lat_tgt, method="linear")


# ------------------------------------------------------------------
# Pipeline principal
# ------------------------------------------------------------------
def build_and_save_integrated(
    start: str,
    end: str,
    dt_hours: int,
    path_ahm: str,  # HYCOM
    path_aam: str,  # GFS
    path_awm: str,  # WW3
    out_path: str,
    target_grid: str = "ww3",  # 'ww3' | 'griddes:/ruta.txt' | 'nc:/ruta.nc'
    chunks: Optional[dict] = None,
    compression_level: int = 4,
):
    # Normalizar templates
    path_ahm = _ensure_template(path_ahm, "HYCOM")
    path_aam = _ensure_template(path_aam, "GFS")
    path_awm = _ensure_template(path_awm, "WW3")

    times = _build_times(start, end, dt_hours)

    files_ahm = [_expand_template(path_ahm, t) for t in times]
    files_aam = [_expand_template(path_aam, t) for t in times]
    files_awm = [_expand_template(path_awm, t) for t in times]

    miss_ahm = _exists_all(files_ahm)
    miss_aam = _exists_all(files_aam)
    miss_awm = _exists_all(files_awm)
    if miss_ahm or miss_aam or miss_awm:
        msg = []
        if miss_ahm:
            msg.append(
                f"HYCOM faltantes ({len(miss_ahm)}):\n  - "
                + "\n  - ".join(miss_ahm[:5])
                + ("\n  ..." if len(miss_ahm) > 5 else "")
            )
        if miss_aam:
            msg.append(
                f"GFS faltantes ({len(miss_aam)}):\n  - "
                + "\n  - ".join(miss_aam[:5])
                + ("\n  ..." if len(miss_aam) > 5 else "")
            )
        if miss_awm:
            msg.append(
                f"WW3 faltantes ({len(miss_awm)}):\n  - "
                + "\n  - ".join(miss_awm[:5])
                + ("\n  ..." if len(miss_awm) > 5 else "")
            )
        raise FileNotFoundError("\n".join(msg))

    # -------------------------
    # 1) Malla objetivo
    # -------------------------
    if target_grid == "ww3":
        ds_ww3_head = xr.open_dataset(
            files_awm[0], engine="h5netcdf", decode_timedelta=True
        )
        ds_ww3_head = _ensure_latlon_names(ds_ww3_head)
        lon_tgt = ds_ww3_head["longitude"]
        lat_tgt = ds_ww3_head["latitude"]
        ds_ww3_head.close()
    elif target_grid.startswith("griddes:"):
        lon_vals, lat_vals = _grid_from_griddes_txt(target_grid.split(":", 1)[1])
        lon_tgt = xr.DataArray(lon_vals, dims=("longitude",), name="longitude")
        lat_tgt = xr.DataArray(lat_vals, dims=("latitude",), name="latitude")
    elif target_grid.startswith("nc:"):
        lon_vals, lat_vals = _grid_from_nc(target_grid.split(":", 1)[1])
        lon_tgt = xr.DataArray(lon_vals, dims=("longitude",), name="longitude")
        lat_tgt = xr.DataArray(lat_vals, dims=("latitude",), name="latitude")
    else:
        raise ValueError(
            "target_grid debe ser 'ww3' o comenzar con 'griddes:' o 'nc:'"
        )

    # -------------------------
    # 2) Abrir datasets
    # -------------------------
    # 2a) WW3 (variables de oleaje)
    ww3_vars_pref = [
        "swh",
        "perpw",
        "dirpw",
        "shww",
        "mpww",
        "wvdir",
        "ws",
        "wdir",
        "shts",
        "mpts",
    ]
    ds_ww3 = _open_concat(
        files_awm,
        chunks=chunks if chunks else {"time": 1, "latitude": 360, "longitude": 360},
        vars_keep=[v for v in ww3_vars_pref if v],
    )
    ds_ww3 = _ensure_latlon_names(ds_ww3)
    if not (
        np.array_equal(ds_ww3["longitude"].values, lon_tgt.values)
        and np.array_equal(ds_ww3["latitude"].values, lat_tgt.values)
    ):
        ds_ww3 = _interp_regular_to_regular(ds_ww3, lon_tgt, lat_tgt)

    # -------------------------
    # 2b) GFS (2t, 10u, 10v)
    # -------------------------
    def _preprocess_gfs(ds: xr.Dataset) -> xr.Dataset:
        if "MT" in ds.dims:
            ds = ds.rename({"MT": "time"})

        rename_map: dict[str, str] = {}
        if "lat" in ds.dims:
            rename_map["lat"] = "latitude"
        if "lon" in ds.dims:
            rename_map["lon"] = "longitude"
        ds = ds.rename(rename_map)

        level_map = {"2t": 0, "10u": 1, "10v": 1}
        for v, lvl in level_map.items():
            if v in ds:
                da = ds[v]
                for zname in ["level", "lev", "isobaricInhPa", "hybrid"]:
                    if zname in da.dims or zname in da.coords:
                        if da.sizes.get(zname, 1) > lvl:
                            ds[v] = da.isel({zname: lvl}).squeeze(drop=True)
                        break
        return ds

    datasets_gfs: list[xr.Dataset] = []
    for f in files_aam:
        ds_tmp = xr.open_dataset(
            f,
            engine="h5netcdf",
            chunks={"time": chunks["time"]} if chunks and "time" in chunks else "auto",
            decode_times=True,
            decode_timedelta=True,
        )
        ds_tmp = _preprocess_gfs(ds_tmp)
        datasets_gfs.append(ds_tmp)
    ds_gfs = xr.concat(datasets_gfs, dim="time")

    alias = {
        "2t": "2t",
        "t2m": "2t",
        "2_metre_temperature": "2t",
        "10u": "10u",
        "u10": "10u",
        "10_metre_u_wind_component": "10u",
        "10v": "10v",
        "v10": "10v",
        "10_metre_v_wind_component": "10v",
        "latitude": "latitude",
        "lat": "latitude",
        "longitude": "longitude",
        "lon": "longitude",
    }
    rename = {k: v for k, v in alias.items() if k in ds_gfs and k != v}
    if rename:
        ds_gfs = ds_gfs.rename(rename)

    is_curvi_gfs = (
        ("longitude" in ds_gfs and getattr(ds_gfs["longitude"], "ndim", 1) == 2)
        or ("latitude" in ds_gfs and getattr(ds_gfs["latitude"], "ndim", 1) == 2)
    )

    if is_curvi_gfs:
        ds_gfs_i = _interp_curvilinear_to_regular(
            ds_gfs,
            ds_gfs["longitude"],
            ds_gfs["latitude"],
            lon_tgt,
            lat_tgt,
            [v for v in ["2t", "10u", "10v"] if v in ds_gfs],
        )
    else:
        ds_gfs = _standardize_lon_to_180(ds_gfs)
        ds_gfs_i = _interp_regular_to_regular(ds_gfs, lon_tgt, lat_tgt)

    # -------------------------
    # 2c) HYCOM (curvilíneo)
    # -------------------------
    def _preprocess_hycom(ds: xr.Dataset) -> xr.Dataset:
        if "MT" in ds.dims:
            ds = ds.rename({"MT": "time"})
        if "Layer" in ds.dims:
            ds = ds.isel(Layer=0).squeeze(drop=True)
        ds = ds.rename({"Y": "y", "X": "x"})
        return ds

    datasets_hy: list[xr.Dataset] = []
    for f in files_ahm:
        ds_tmp = xr.open_dataset(
            f,
            engine="h5netcdf",
            chunks={"time": chunks["time"]} if chunks and "time" in chunks else "auto",
            decode_times=True,
            decode_timedelta=True,
        )
        ds_tmp = _preprocess_hycom(ds_tmp)
        datasets_hy.append(ds_tmp)
    ds_hy = xr.concat(datasets_hy, dim="time")

    lon2d_hy = ds_hy["Longitude"]
    lat2d_hy = ds_hy["Latitude"]

    for v in ["u_velocity", "v_velocity", "sst", "sss"]:
        if v in ds_hy:
            print(f"[HYCOM] {v}: dims={ds_hy[v].dims}, shape={ds_hy[v].shape}")

    ds_hy_i = _interp_curvilinear_to_regular(
        ds_hy,
        lon2d_hy,
        lat2d_hy,
        lon_tgt,
        lat_tgt,
        [v for v in ["u_velocity", "v_velocity", "sst", "sss"] if v in ds_hy],
    )

    # -------------------------
    # 3) Alinear tiempos y combinar
    # -------------------------
    tvec = np.array(times, dtype="datetime64[ns]")
    for d in (ds_ww3, ds_gfs_i, ds_hy_i):
        if "time" in d.coords:
            d["time"] = tvec

    ds_all = xr.merge([ds_ww3, ds_gfs_i, ds_hy_i], compat="override", join="exact")
    ds_all = ds_all.transpose("longitude", "latitude", "time")

    # -------------------------
    # 4) Atributos
    # -------------------------
    ds_all.attrs.update(
        {
            "title": "Archivo Integrado Atmosférico-Oceánico en Malla Objetivo (NOAA)",
            "summary": (
                "Variables atmosféricas (GFS: 2t, 10u, 10v), oceánicas (HYCOM: "
                "u_velocity, v_velocity, sst) y de oleaje (WW3: swh, perpw, dirpw, "
                "shww, mpww, wvdir, ws, wdir, shts, mpts), reamostradas/interpoladas "
                "a una malla común (por defecto WW3). Tiempo cada 6 h."
            ),
            "authors": "Amilcar E. Calzada & Oscar O. Diaz",
            "institution": "Integración meteo-oceánica (NOAA models)",
            "source_models": "weather_model=gfs; hydrodynamic_model=hycom; wave_model=ww3",
            "grid_target": f"{target_grid}",
            "method_interpolation": "Bilineal (xarray.interp) + remapeo curvilíneo (xESMF/SciPy griddata)",
            "time_step_hours": dt_hours,
            "created_on": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conventions": "CF-1.8",
            "note": "GFS puede traer lon/lat 2D; HYCOM curvilíneo remapeado; engine=h5netcdf; manejo de memoria con chunks.",
        }
    )

    var_attrs = {
        # GFS
        "2t": dict(long_name="2-metre temperature", units="K"),
        "10u": dict(long_name="10-metre U wind component", units="m s-1"),
        "10v": dict(long_name="10-metre V wind component", units="m s-1"),
        # HYCOM
        "u_velocity": dict(
            long_name="Sea water velocity U (surface)", units="m s-1"
        ),
        "v_velocity": dict(
            long_name="Sea water velocity V (surface)", units="m s-1"
        ),
        "sst": dict(long_name="Sea surface temperature", units="degC"),
        # WW3
        "swh": dict(
            long_name="Significant height of combined wind waves and swell", units="m"
        ),
        "perpw": dict(long_name="Primary wave mean period", units="s"),
        "dirpw": dict(long_name="Primary wave mean direction", units="degree_from_north"),
        "shww": dict(long_name="Significant height of wind waves", units="m"),
        "mpww": dict(long_name="Mean period of wind waves", units="s"),
        "wvdir": dict(long_name="Direction of wind waves", units="degree_from_north"),
        "ws": dict(long_name="Wind speed (from WW3 forcing)", units="m s-1"),
        "wdir": dict(
            long_name="Wind direction (from WW3 forcing)", units="degree_from_north"
        ),
        "shts": dict(long_name="Significant height of total swell", units="m"),
        "mpts": dict(long_name="Mean period of total swell", units="s"),
    }
    for v, a in var_attrs.items():
        if v in ds_all:
            ds_all[v].attrs.update(a)
            if ds_all[v].dims != ("longitude", "latitude", "time"):
                ds_all[v] = ds_all[v].transpose("longitude", "latitude", "time")

    # -------------------------
    # 5) Escritura con compresión
    # -------------------------
    enc = {
        v: {"zlib": True, "complevel": compression_level, "_FillValue": np.nan}
        for v in ds_all.data_vars
    }

    base, ext = os.path.splitext(out_path)
    out_path = f"{base}_{start}_{end}{ext}"
    ds_all.to_netcdf(out_path, format="NETCDF4", engine="h5netcdf", encoding=enc)
    print(f"Archivo escrito: {out_path}")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Integra NOAA (GFS + HYCOM + WW3) en malla WW3 o provista (bilineal)."
    )
    p.add_argument(
        "--start",
        type=lambda s: re.sub(r"[^\d]", "", s),
        required=True,
        help="Fecha/hora inicio YYYYMMDDHH o similar (se extraen sólo dígitos)",
    )
    p.add_argument(
        "--end",
        type=lambda s: re.sub(r"[^\d]", "", s),
        required=True,
        help="Fecha/hora fin YYYYMMDDHH o similar (se extraen sólo dígitos)",
    )
    p.add_argument(
        "--dt_hours", type=int, default=6, help="Paso temporal en horas (default=6)"
    )
    p.add_argument(
        "--path_ahm",
        required=True,
        help="Template HYCOM (ej. ./hycom/hycom_aaaammddHH.nc)",
    )
    p.add_argument(
        "--path_aam",
        required=True,
        help="Template GFS (ej. ./gfs/gfs_aaaammddHH.nc)",
    )
    p.add_argument(
        "--path_awm",
        required=True,
        help="Template WW3 (ej. ./ww3/ww3_aaaammddHH.nc)",
    )
    p.add_argument(
        "--out", default="integrated_ww3_grid.nc", help="Ruta base del NetCDF de salida"
    )
    p.add_argument(
        "--chunk_lon",
        type=int,
        default=360,
        help="Chunk en longitud (default=360)",
    )
    p.add_argument(
        "--chunk_lat",
        type=int,
        default=360,
        help="Chunk en latitud (default=360)",
    )
    p.add_argument(
        "--chunk_time",
        type=int,
        default=1,
        help="Chunk en tiempo (default=1)",
    )
    p.add_argument(
        "--compression",
        type=int,
        default=4,
        help="Nivel de compresión zlib (0-9)",
    )
    p.add_argument(
        "--target_grid",
        default="ww3",
        help=(
            "'ww3' para tomar la grilla del WW3; "
            "'griddes:/ruta.txt' para usar un descriptor de CDO; "
            "'nc:/ruta.nc' para usar lon/lat desde un NetCDF"
        ),
    )
    return p.parse_args()


def main():
    args = parse_args()

    chunks = {
        "longitude": args.chunk_lon,
        "latitude": args.chunk_lat,
        "time": args.chunk_time,
    }

    build_and_save_integrated(
        start=args.start,
        end=args.end,
        dt_hours=args.dt_hours,
        path_ahm=args.path_ahm,
        path_aam=args.path_aam,
        path_awm=args.path_awm,
        out_path=args.out,
        target_grid=args.target_grid,
        chunks=chunks,
        compression_level=args.compression,
    )


if __name__ == "__main__":
    main()

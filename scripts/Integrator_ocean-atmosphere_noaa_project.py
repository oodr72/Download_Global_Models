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
    --path_ehm "./hycom/hycom_aaaammddHH.nc" \
    --path_eam "./gfs/gfs_aaaammddHH.nc" \
    --path_ewm "./ww3/ww3_aaaammddHH.nc" \
    --out integrated_glorys_grid.nc
	
Notas:
  - Manejo de memoria con xarray + chunks (dask opcional).
  - Lectura con engine 'h5netcdf' para evitar segfaults de netCDF4/HDF5.
  - decode_timedelta=True para silenciar warnings futuros de xarray.
  - Remapeo curvilíneo con xESMF si disponible; SciPy griddata como fallback.
"""
from __future__ import annotations
import argparse
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import hashlib
import xesmf as xe
import numpy as np
import xarray as xr
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from scipy.spatial import Delaunay

# --------------------------
# Helpers
# --------------------------
_LEVEL_NAMES = ("level","lev","hybrid","isobaricInhPa","depth","Layer","z")
# ------------------------------------------------------------------
# Utilidades generales
# ------------------------------------------------------------------
def _to_numpy(a):
    return a.data if hasattr(a, "data") else np.asarray(a)

def _ensure_dataarray_2d(a, dim_y="y", dim_x="x"):
    if isinstance(a, xr.DataArray):
        if a.ndim != 2:
            raise ValueError(f"Se esperaba 2D para lon/lat; llegó con dims {a.dims} y shape {a.shape}")
        da = a
        # Normalizar nombres de dims a (y,x)
        map_dims = {}
        if dim_y not in da.dims or dim_x not in da.dims:
            # Intentar mapear nombres comunes
            cand_y = [d for d in da.dims if d.lower() in ("y","lat","latitude","j","ny")]
            cand_x = [d for d in da.dims if d.lower() in ("x","lon","longitude","i","nx")]
            if cand_y and cand_x:
                map_dims = {cand_y[0]: dim_y, cand_x[0]: dim_x}
        if map_dims:
            da = da.rename(map_dims)
        return da
    else:
        arr = np.asarray(a)
        if arr.ndim != 2:
            raise ValueError(f"Se esperaba 2D numpy para lon/lat; llegó con shape {arr.shape}")
        return xr.DataArray(arr, dims=(dim_y, dim_x))

def _rename_spatial_dims_to_yx(da):
    """Renombra dims espaciales a (y,x) sin tocar time/otras."""
    rename = {}
    for d in da.dims:
        dl = d.lower()
        if dl in ("lat","latitude","j","ny"): rename[d] = "y"
        if dl in ("lon","longitude","i","nx"): rename[d] = "x"
    # Si ya tiene y/x, no pasa nada
    if rename:
        da = da.rename(rename)
    return da

def _squeeze_singleton_levels(da):
    """Quita dimensión vertical si es singleton."""
    for zn in _LEVEL_NAMES:
        if zn in da.dims:
            if da.sizes.get(zn, 1) == 1:
                da = da.isel({zn: 0}).squeeze(drop=True)
    return da

def _guess_weights_name(method, src_shape, tgt_shape):
    key = f"{method}|src:{src_shape}|tgt:{tgt_shape}"
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"weights_{method}_{src_shape[0]}x{src_shape[1]}_to_{tgt_shape[0]}x{tgt_shape[1]}_{h}.nc"

def _make_regridder(src, tgt, method="bilinear", filename=None, periodic=None):
    if filename is None:
        filename = _guess_weights_name(method, src["lon"].shape, tgt["lon"].shape)
    kw = dict(filename=filename)
    if periodic is not None:
        kw["periodic"] = periodic
    if os.path.exists(filename):
        return xe.Regridder(src, tgt, method, reuse_weights=True, **kw)
    else:
        # Primera vez: calcula y guarda
        return xe.Regridder(src, tgt, method, reuse_weights=False, **kw)

# --------------------------
# Función principal
# --------------------------
def _interp_curvilinear_to_regular(
    ds,
    lon2d,
    lat2d,
    lon_tgt,
    lat_tgt,
    variables=None,
    *,
    method="bilinear",
    weights_name=None,
    periodic=None # usa True si trabajas global 0–360
):

    """
    Interpola un Dataset curvilíneo (lon2d, lat2d) a grilla regular (lon_tgt, lat_tgt) con xESMF.
    - Maneja dims variadas -> (y,x)
    - Quita niveles verticales 'singleton' (lev=1) por variable
    - Ajusta caso 365 -> 364 cols (0°/360° redundante) si es necesario
    - Cachea pesos automáticamente (filename inferido si no se pasa)
    - Devuelve dims (longitude, latitude, time, ...)

    ds        : xr.Dataset (contiene variables con dims espaciales 2D)
    lon2d/lat2d: lon/lat 2D (DataArray o ndarray)
    lon_tgt/lat_tgt: 1D (DataArray o ndarray) de la malla destino
    variables : lista de nombres a interpolar (None -> detecta todas numéricas con (y,x))
    method    : 'bilinear'|'nearest_s2d'|'conservative'...
    weights_name : nombre del archivo de pesos (opcional)
    periodic  : True si grilla global periódica; None/False en caso contrario
    """

    # --- Normalizar lon/lat fuente a DataArray 2D con dims (y,x)
    lon2d = _ensure_dataarray_2d(lon2d, "y", "x")
    lat2d = _ensure_dataarray_2d(lat2d, "y", "x")

    # --- Asegurar target 1D numpy
    lon1 = _to_numpy(lon_tgt).ravel()
    lat1 = _to_numpy(lat_tgt).ravel()

    # --- Caso global: fuente 365 y destino 364 -> recortar última col
    if lon2d.shape[1] == lon1.size + 1:
        lon2d = lon2d.isel(x=slice(0, -1))
        lat2d = lat2d.isel(x=slice(0, -1))

    # --- Construir grids src/tgt
    src = xr.Dataset({"lon": lon2d, "lat": lat2d})
    lon2d_tgt, lat2d_tgt = np.meshgrid(lon1, lat1)
    tgt = xr.Dataset(
        {"lon": (["y", "x"], lon2d_tgt),
         "lat": (["y", "x"], lat2d_tgt)}
    )

    # --- Regridder con caché de pesos
    regridder = _make_regridder(
        src, tgt, method=method,
        filename=weights_name, periodic=periodic
    )

    # --- Elegir variables a interpolar
    if variables is None:
        variables = [v for v in ds.data_vars if np.issubdtype(ds[v].dtype, np.number)]

    # --- Interpolación variable por variable ---
    out = xr.Dataset()
    for v in variables:
        if v not in ds:
            continue
        da = ds[v]

        # Quitar niveles singleton
        da = _squeeze_singleton_levels(da)

        # Renombrar dims espaciales
        da = _rename_spatial_dims_to_yx(da)

        # Verificar dims espaciales
        if not {"y", "x"}.issubset(set(da.dims)):
            raise ValueError(
                f"La variable '{v}' no tiene dims espaciales (y,x) tras normalización; dims={da.dims}"
            )

        # Recortar si sobra una columna
        if "x" in da.dims and da.sizes["x"] == lon1.size + 1:
            da = da.isel(x=slice(0, -1))

        # Aplicar regridder (maneja automáticamente time u otras dims)
        out[v] = regridder(da)

    # --- Asignar coords destino ---
    out = out.assign_coords({
        "latitude": ("y", lat1),
        "longitude": ("x", lon1),
    }).swap_dims({"y": "latitude", "x": "longitude"})

    # --- Orden final robusto: (longitude, latitude, time, ...)
    out = out.transpose("longitude", "latitude", "time", ...)

    return out

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


def _ensure_latlon_names(ds: xr.Dataset,
                         lon_aliases=("lon", "longitude", "x"),
                         lat_aliases=("lat", "latitude", "y")) -> xr.Dataset:
    """Renombra coordenadas/dimensiones 1D a 'longitude'/'latitude' si aplica.
    No fuerza nada si son variables 2D (curvilíneo)."""
    # Si ya existen lon/lat 2D como variables, no tocamos nada aquí
    if 'longitude' in ds and 'latitude' in ds and (ds['longitude'].ndim == 2 or ds['latitude'].ndim == 2):
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
    rename = {}
    if lon_name and lon_name != "longitude":
        rename[lon_name] = "longitude"
    if lat_name and lat_name != "latitude":
        rename[lat_name] = "latitude"
    if rename:
        ds = ds.rename(rename)
    return ds


def _standardize_lon_to_180(ds: xr.Dataset,
                            lon_names: Tuple[str, ...] = ("lon", "longitude")) -> xr.Dataset:
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


def _open_concat(files: List[str],
                 chunks: Optional[dict] = None,
                 vars_keep: Optional[List[str]] = None,
                 engine: str = "h5netcdf") -> xr.Dataset:
    if len(files) == 0:
        raise ValueError("No se proporcionaron archivos para abrir.")

    def _preprocess(ds: xr.Dataset) -> xr.Dataset:
        if vars_keep is not None:
            keep = [v for v in vars_keep if v in ds]
            ds = ds[keep]
        return ds

    ds = xr.open_mfdataset(
        files,
        combine="nested",
        concat_dim="time",
        parallel=False,
        preprocess=_preprocess,
        chunks="auto",
        engine=engine,
        decode_times=True,
        decode_timedelta=True,
        coords="minimal",
        compat="override"
    )
    return ds


# ------------------------------------------------------------------
# Construcción de malla objetivo
# ------------------------------------------------------------------

def _grid_from_griddes_txt(path_txt: str) -> Tuple[np.ndarray, np.ndarray]:
    with open(path_txt, 'r') as f:
        txt = f.read()
    def _get(key: str, cast=float):
        import re
        m = re.search(rf"{key}\s*=\s*([\-0-9\.eE]+)", txt)
        if not m:
            raise ValueError(f"Clave '{key}' no encontrada en griddes")
        return cast(m.group(1))
    xsize = int(_get('xsize', int))
    ysize = int(_get('ysize', int))
    xfirst = _get('xfirst')
    yfirst = _get('yfirst')
    xinc = _get('xinc')
    yinc = _get('yinc')
    lon = xfirst + np.arange(xsize) * xinc
    lat = yfirst + np.arange(ysize) * yinc
    return lon, lat


def _grid_from_nc(path_nc: str) -> Tuple[np.ndarray, np.ndarray]:
    ds = xr.open_dataset(path_nc, engine='h5netcdf', decode_timedelta=True)
    ds = _ensure_latlon_names(ds)
    lon = ds['longitude'].values
    lat = ds['latitude'].values
    ds.close()
    return lon, lat
# ------------------------------------------------------------------
# Remapeos
# ------------------------------------------------------------------
def _interp_regular_to_regular(ds: xr.Dataset, lon_tgt: xr.DataArray, lat_tgt: xr.DataArray) -> xr.Dataset:
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
    target_grid: str = 'ww3',  # 'ww3' | 'griddes:/ruta.txt' | 'nc:/ruta.nc'
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
            msg.append(f"HYCOM faltantes ({len(miss_ahm)}):\n  - " + "\n  - ".join(miss_ahm[:5]) + ("\n  ..." if len(miss_ahm) > 5 else ""))
        if miss_aam:
            msg.append(f"GFS faltantes ({len(miss_aam)}):\n  - " + "\n  - ".join(miss_aam[:5]) + ("\n  ..." if len(miss_aam) > 5 else ""))
        if miss_awm:
            msg.append(f"WW3 faltantes ({len(miss_awm)}):\n  - " + "\n  - ".join(miss_awm[:5]) + ("\n  ..." if len(miss_awm) > 5 else ""))
        raise FileNotFoundError("\n".join(msg))

    # -------------------------
    # 1) Malla objetivo
    # -------------------------
    if target_grid == 'ww3':
        ds_ww3_head = xr.open_dataset(files_awm[0], engine='h5netcdf', decode_timedelta=True)
        ds_ww3_head = _ensure_latlon_names(ds_ww3_head)
        lon_tgt = ds_ww3_head['longitude']
        lat_tgt = ds_ww3_head['latitude']
        ds_ww3_head.close()
    elif target_grid.startswith('griddes:'):
        lon_vals, lat_vals = _grid_from_griddes_txt(target_grid.split(':', 1)[1])
        lon_tgt = xr.DataArray(lon_vals, dims=('longitude',), name='longitude')
        lat_tgt = xr.DataArray(lat_vals, dims=('latitude',), name='latitude')
    elif target_grid.startswith('nc:'):
        lon_vals, lat_vals = _grid_from_nc(target_grid.split(':', 1)[1])
        lon_tgt = xr.DataArray(lon_vals, dims=('longitude',), name='longitude')
        lat_tgt = xr.DataArray(lat_vals, dims=('latitude',), name='latitude')
    else:
        raise ValueError("target_grid debe ser 'ww3' o comenzar con 'griddes:' o 'nc:'")

    # -------------------------
    # 2) Abrir datasets
    # -------------------------
    # 2a) WW3 (variables de oleaje)
    ww3_vars_pref = [
        'swh', 'perpw', 'dirpw', 'shww', 'mpww', 'wvdir', 'ws', 'wdir', 'shts', 'mpts'
    ]
    ds_ww3 = _open_concat(
        files_awm,
        chunks=chunks if chunks else {"time": 1, "latitude": 360, "longitude": 360},
        vars_keep=[v for v in ww3_vars_pref if v]
    )
    ds_ww3 = _ensure_latlon_names(ds_ww3)
    # Si no coincide exactamente con la malla objetivo, reinterpolar
    if not (np.array_equal(ds_ww3['longitude'].values, lon_tgt.values) and
            np.array_equal(ds_ww3['latitude'].values, lat_tgt.values)):
        ds_ww3 = _interp_regular_to_regular(ds_ww3, lon_tgt, lat_tgt)

    # -------------------------
    # 2b) GFS (2t, 10u, 10v)
    # -------------------------

    def _preprocess_gfs(ds):
        """Normaliza GFS: MT->time, selecciona niveles adecuados, renombra lon/lat"""
        # MT = tiempo
        if "MT" in ds.dims:
            ds = ds.rename({"MT": "time"})
        
        # Renombrar lat/lon a estándar
        rename_map = {}
        if "lat" in ds.dims: rename_map["lat"] = "latitude"
        if "lon" in ds.dims: rename_map["lon"] = "longitude"
        ds = ds.rename(rename_map)
        
        # Selección de niveles verticales específica
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

    # Abrir y preprocesar cada archivo GFS
    datasets = []
    for f in files_aam:
        ds_tmp = xr.open_dataset(f, chunks=chunks if chunks else {"time": 1})
        ds_tmp = _preprocess_gfs(ds_tmp)
        datasets.append(ds_tmp)

    # Concatenar sobre tiempo
    ds_gfs = xr.concat(datasets, dim="time")

    # Alias posibles
    alias = {
        "2t": "2t", "t2m": "2t", "2_metre_temperature": "2t",
        "10u": "10u", "u10": "10u", "10_metre_u_wind_component": "10u",
        "10v": "10v", "v10": "10v", "10_metre_v_wind_component": "10v",
        "latitude": "latitude", "lat": "latitude",
        "longitude": "longitude", "lon": "longitude"
    }
    rename = {k: v for k, v in alias.items() if k in ds_gfs and k != v}
    if rename:
        ds_gfs = ds_gfs.rename(rename)

    # ¿GFS curvilíneo (lon/lat 2D)?
    is_curvi_gfs = (
        ("longitude" in ds_gfs and getattr(ds_gfs["longitude"], "ndim", 1) == 2) or
        ("latitude" in ds_gfs and getattr(ds_gfs["latitude"], "ndim", 1) == 2)
    )

    if is_curvi_gfs:
        ds_gfs_i = _interp_curvilinear_to_regular(
            ds_gfs,
            ds_gfs["longitude"], ds_gfs["latitude"],
            lon_tgt, lat_tgt,
            [v for v in ["2t", "10u", "10v"] if v in ds_gfs]
        )
    else:
        ds_gfs = _standardize_lon_to_180(ds_gfs)
        ds_gfs_i = _interp_regular_to_regular(ds_gfs, lon_tgt, lat_tgt)

    # -------------------------
    # 2c) HYCOM (u_velocity, v_velocity, sst, sss) -> curvilíneo
    # -------------------------

    def _preprocess_hycom(ds):
        """Normaliza HYCOM: MT->time, elimina Layer único, renombra Y/X -> y/x"""
        # MT = tiempo
        if "MT" in ds.dims:
            ds = ds.rename({"MT": "time"})
        # Layer = nivel único → seleccionar primer nivel
        if "Layer" in ds.dims:
            ds = ds.isel(Layer=0).squeeze(drop=True)
        # Renombrar Y/X a y/x
        ds = ds.rename({"Y": "y", "X": "x"})
        return ds

    # Abrir y preprocesar cada archivo HYCOM
    datasets = []
    for f in files_ahm:
        ds_tmp = xr.open_dataset(f, chunks=chunks if chunks else {"time": 1})
        ds_tmp = _preprocess_hycom(ds_tmp)
        datasets.append(ds_tmp)

    # Concatenar sobre tiempo
    ds_hy = xr.concat(datasets, dim="time")

    # --- Detectar lon/lat 2D (siempre en HYCOM) ---
    lon2d_hy = ds_hy["Longitude"]
    lat2d_hy = ds_hy["Latitude"]

    # --- Debug opcional ---
    for v in ["u_velocity", "v_velocity", "sst", "sss"]:
        if v in ds_hy:
            print(f"[HYCOM] {v}: dims={ds_hy[v].dims}, shape={ds_hy[v].shape}")

    # --- Interpolación HYCOM → malla objetivo ---
    ds_hy_i = _interp_curvilinear_to_regular(
        ds_hy,
        lon2d_hy, lat2d_hy,
        lon_tgt, lat_tgt,
        [v for v in ["u_velocity", "v_velocity", "sst", "sss"] if v in ds_hy]
    )

    # -------------------------
    # 3) Alinear tiempos y combinar
    # -------------------------
    tvec = np.array(times, dtype='datetime64[ns]')
    for d in (ds_ww3, ds_gfs_i, ds_hy_i):
        if 'time' in d.coords:
            d['time'] = tvec

    ds_all = xr.merge([ds_ww3, ds_gfs_i, ds_hy_i], compat='override', join='exact')

    # Orden final de dimensiones
    ds_all = ds_all.transpose('longitude', 'latitude', 'time')

    # -------------------------
    # 4) Atributos globales y por variable
    # -------------------------
    ds_all.attrs.update({
        'title': 'Archivo Integrado Atmosférico-Oceánico en Malla Objetivo (NOAA)',
        'summary': (
            'Variables atmosféricas (GFS: 2t, 10u, 10v), oceánicas (HYCOM: u_velocity, v_velocity, sst) '
            'y de oleaje (WW3: swh, perpw, dirpw, shww, mpww, wvdir, ws, wdir, shts, mpts), '
            'reamostradas/interpoladas a una malla común (por defecto WW3). Tiempo cada 6 h.'
        ),
        'authors': 'Amilcar E. Calzada & Oscar O. Diaz',
        'institution': 'Integración meteo-oceánica (NOAA models)',
        'source_models': 'weather_model=gfs; hydrodynamic_model=hycom; wave_model=ww3',
        'grid_target': f'{target_grid}',
        'method_interpolation': 'Bilineal (xarray.interp) + remapeo curvilíneo (xESMF/SciPy)',
        'time_step_hours': dt_hours,
        'created_on': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'conventions': 'CF-1.8',
        'note': 'GFS puede traer lon/lat 2D; HYCOM curvilíneo remapeado; engine=h5netcdf; manejo de memoria con chunks.'
    })

    var_attrs = {
        # GFS
        '2t': dict(long_name='2-metre temperature', units='K'),
        '10u': dict(long_name='10-metre U wind component', units='m s-1'),
        '10v': dict(long_name='10-metre V wind component', units='m s-1'),
        # HYCOM
        'u_velocity': dict(long_name='Sea water velocity U (surface)', units='m s-1'),
        'v_velocity': dict(long_name='Sea water velocity V (surface)', units='m s-1'),
        'sst': dict(long_name='Sea surface temperature', units='degC'),
        # WW3
        'swh': dict(long_name='Significant height of combined wind waves and swell', units='m'),
        'perpw': dict(long_name='Primary wave mean period', units='s'),
        'dirpw': dict(long_name='Primary wave mean direction', units='degree_from_north'),
        'shww': dict(long_name='Significant height of wind waves', units='m'),
        'mpww': dict(long_name='Mean period of wind waves', units='s'),
        'wvdir': dict(long_name='Direction of wind waves', units='degree_from_north'),
        'ws': dict(long_name='Wind speed (from WW3 forcing)', units='m s-1'),
        'wdir': dict(long_name='Wind direction (from WW3 forcing)', units='degree_from_north'),
        'shts': dict(long_name='Significant height of total swell', units='m'),
        'mpts': dict(long_name='Mean period of total swell', units='s'),
    }
    for v, a in var_attrs.items():
        if v in ds_all:
            ds_all[v].attrs.update(a)
            if ds_all[v].dims != ('longitude', 'latitude', 'time'):
                ds_all[v] = ds_all[v].transpose('longitude', 'latitude', 'time')

    # -------------------------
    # 5) Escritura con compresión
    # -------------------------
    enc = {v: {"zlib": True, "complevel": compression_level, "_FillValue": np.nan}
           for v in ds_all.data_vars}
    
    # Construir nombre de salida con fechas
    base, ext = os.path.splitext(out_path)
    out_path = f"{base}_{start}_{end}{ext}"
    ds_all.to_netcdf(out_path, format='NETCDF4', engine='h5netcdf', encoding=enc)
    print(f"Archivo escrito: {out_path}")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Integra NOAA (GFS + HYCOM + WW3) en malla WW3 o provista (bilineal)."
    )
    p.add_argument("--start", required=True, help="Fecha/hora inicio YYYYMMDDHH")
    p.add_argument("--end", required=True, help="Fecha/hora fin YYYYMMDDHH")
    p.add_argument("--dt_hours", type=int, default=6, help="Paso temporal en horas (default=6)")
    p.add_argument("--path_ahm", required=True, help="Template HYCOM (ej. ./hycom/hycom_aaaammddHH.nc)")
    p.add_argument("--path_aam", required=True, help="Template GFS (ej. ./gfs/gfs_aaaammddHH.nc)")
    p.add_argument("--path_awm", required=True, help="Template WW3 (ej. ./ww3/ww3_aaaammddHH.nc)")
    p.add_argument("--out", default="integrated_ww3_grid.nc", help="Ruta del NetCDF de salida")
    p.add_argument("--chunk_lon", type=int, default=360, help="Chunk en longitud (default=360)")
    p.add_argument("--chunk_lat", type=int, default=360, help="Chunk en latitud (default=360)")
    p.add_argument("--chunk_time", type=int, default=1, help="Chunk en tiempo (default=1)")
    p.add_argument("--compression", type=int, default=4, help="Nivel de compresión zlib (0-9)")
    p.add_argument("--target_grid", default='ww3',
                   help=("'ww3' para tomar la grilla del WW3; 'griddes:/ruta.txt' para usar un descriptor de CDO; "
                         "'nc:/ruta.nc' para usar lon/lat desde un NetCDF"))
    return p.parse_args()


def main():
    args = parse_args()
    build_and_save_integrated(
        start=args.start,
        end=args.end,
        dt_hours=args.dt_hours,
        path_ahm=args.path_ahm,
        path_aam=args.path_aam,
        path_awm=args.path_awm,
        out_path=args.out,
        target_grid="ww3"
    )


if __name__ == "__main__":
    main()

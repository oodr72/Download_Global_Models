#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrating CMEMS Projects (ECMWF + GLORYS_024 + FMWAM)
Creates a single NetCDF file containing atmospheric and oceanic variables on the GLORYS grid.

Authors: Amilcar E. Calzada & Oscar O. Diaz
Objective: Creation of atmospheric and oceanic data for a predefined region
           based on global models, with a temporal step of 6 hours.
Interpolation method: Bilinear (xarray.interp linear in 2D)
Time handling: Assumes that the files are already time-aligned and available
               in each folder with one file per time step (every 6 hours).

Expected inputs (path patterns):
- path_EHM (hydrodynamic / GLORYS): ./glorys/glorys024_aaaammddHH.nc
- path_EAM (atmospheric / ECMWF)  : ./ecmwf/ecmwf_aaaammddHH.nc
- path_EWM (wave / FMWAM)         : ./fmwam/fmwam_aaaammddHH.nc

Output:
- A single NetCDF file with dimensions (longitude, latitude, time) containing all variables:
  Atmospheric (t2m, u10, v10), Hydrodynamic (thetao, uo, vo), and Wave
  (VHM0_WW, VHM0_SW1, VMDR_WW, VMDR_SW1, VTM01_WW, VTM01_SW1)
"""
import argparse
import sys
from datetime import datetime, timedelta
import re
import warnings

import numpy as np
import xarray as xr

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def parse_datetime_arg(s):
    """Convierte 'YYYYMMDDHH' a datetime naive (UTC)."""
    try:
        return datetime.strptime(s, "%Y%m%d%H")
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Date/time inválida '{s}': use YYYYMMDDHH") from e


def daterange_6h(start_dt, end_dt):
    """Genera datetimes de 6 horas de start_dt a end_dt inclusive."""
    if end_dt < start_dt:
        raise ValueError("end_dt no puede ser menor que start_dt")
    t = start_dt
    delta = timedelta(hours=6)
    while t <= end_dt:
        yield t
        t += delta


def format_timestamp(dt):
    """Formatea datetime -> 'YYYYMMDDHH' para nombres de archivo."""
    return dt.strftime("%Y%m%d%H")


def ensure_lon_lat_order(ds, lon_name="longitude", lat_name="latitude"):
    """Ordena longitudes de menor a mayor y latitudes de menor a mayor, si fuese necesario."""
    if lon_name in ds.coords:
        lons = ds[lon_name]
        if (np.diff(lons.values) < 0).any():
            ds = ds.sortby(lon_name)
    if lat_name in ds.coords:
        lats = ds[lat_name]
        if (np.diff(lats.values) < 0).any():
            ds = ds.sortby(lat_name)
    return ds


def ecmwf_fix_coordinates(ds):
    """
    Arregla coordenadas de ECMWF:
    - Convierte longitudes 0..360 a rango (-180..180] y ordena.
    - Renombra coordenadas a 'longitude'/'latitude' si fuese necesario.
    - Renombra variables a convenciones: t2m, u10, v10.
    """
    # Renombres de coordenadas comunes en productos ECMWF
    cr = {}
    if 'longitude' not in ds.coords and 'lon' in ds.coords:
        cr['lon'] = 'longitude'
    if 'latitude' not in ds.coords and 'lat' in ds.coords:
        cr['lat'] = 'latitude'
    if cr:
        ds = ds.rename(cr)

    # Variables con nombres no válidos en Python (inician con dígitos) suelen llegar ya mapeadas;
    # tratamos casos típicos vistos en encabezados:
    var_rename = {}
    for v in list(ds.data_vars):
        vn = v.strip().lower().replace(' ', '_')
        if '2_metre_temperature' in vn or vn.endswith('_2m_temperature'):
            var_rename[v] = 't2m'
        elif '10_metre_u_wind_component' in vn or re.search(r'(^|_)u10($|_)', vn):
            var_rename[v] = 'u10'
        elif '10_metre_v_wind_component' in vn or re.search(r'(^|_)v10($|_)', vn):
            var_rename[v] = 'v10'
    if var_rename:
        ds = ds.rename(var_rename)

    # Asegurar presencia de variables esperadas (si existían con otros alias)
    expected = {'t2m', 'u10', 'v10'}
    if not expected.issubset(set(ds.data_vars)):
        warnings.warn(f"ECMWF: variables esperadas faltantes {expected - set(ds.data_vars)}")

    # Convertir 0..360 a -180..180
    if 'longitude' in ds.coords:
        lon = ds['longitude'].copy()
        lon = xr.where(lon > 180, lon - 360, lon)
        ds = ds.assign_coords(longitude=lon)
    ds = ensure_lon_lat_order(ds)
    return ds


def regrid_to_target(ds, target_lon, target_lat, method="linear"):
    """
    Interpola bilinearmente (xarray.interp) un dataset a (target_lon, target_lat).
    Requiere que ds tenga coords 'longitude' y 'latitude' crecientes.
    """
    ds = ensure_lon_lat_order(ds)
    # Si hay coordenadas 1D de lon/lat, interp lineal en 2D es bilinear.
    return ds.interp(longitude=target_lon, latitude=target_lat, method=method)


def load_glorys(path):
    """Abre GLORYS para un time, extrae superficie (depth índice 0)."""
    ds = xr.open_dataset(path, decode_cf=True, chunks={'time': 1, 'latitude': 270, 'longitude': 270})
    # Variables de interés
    keep = [v for v in ['thetao', 'uo', 'vo'] if v in ds.data_vars]
    ds = ds[keep]
    # Extraer superficie (depth=0) si existe dimensión 'depth'
    if 'depth' in ds.dims:
        ds = ds.isel(depth=0).drop_vars('depth')
    # Asegurar nombres de coords
    cr = {}
    if 'lon' in ds.coords and 'longitude' not in ds.coords:
        cr['lon'] = 'longitude'
    if 'lat' in ds.coords and 'latitude' not in ds.coords:
        cr['lat'] = 'latitude'
    if cr:
        ds = ds.rename(cr)
    ds = ensure_lon_lat_order(ds)
    return ds


def load_fmwam(path):
    """Abre FMWAM para un time (variables de wave)."""
    ds = xr.open_dataset(path, decode_cf=True, chunks={'time': 1, 'latitude': 270, 'longitude': 270})
    keep = [v for v in ['VHM0_WW','VHM0_SW1','VMDR_WW','VMDR_SW1','VTM01_WW','VTM01_SW1'] if v in ds.data_vars]
    ds = ds[keep]
    # Asegurar nombres de coords
    cr = {}
    if 'lon' in ds.coords and 'longitude' not in ds.coords:
        cr['lon'] = 'longitude'
    if 'lat' in ds.coords and 'latitude' not in ds.coords:
        cr['lat'] = 'latitude'
    if cr:
        ds = ds.rename(cr)
    ds = ensure_lon_lat_order(ds)
    return ds


def load_ecmwf(path):
    """Abre ECMWF para un time, renombra y arregla longitudes."""
    ds = xr.open_dataset(path, decode_cf=True, chunks={'time': 1, 'latitude': 181, 'longitude': 365})
    ds = ecmwf_fix_coordinates(ds)
    # Seleccionar sólo las variables esperadas si están presentes
    keep = [v for v in ['t2m','u10','v10'] if v in ds.data_vars]
    if keep:
        ds = ds[keep]
    return ds


def build_target_grid(glorys_example_path):
    """Obtiene (target_lon, target_lat) 1D desde un archivo GLORYS ejemplo."""
    ds = xr.open_dataset(glorys_example_path, decode_cf=True)
    # Renombrar si fuese necesario
    cr = {}
    if 'lon' in ds.coords and 'longitude' not in ds.coords:
        cr['lon'] = 'longitude'
    if 'lat' in ds.coords and 'latitude' not in ds.coords:
        cr['lat'] = 'latitude'
    if cr:
        ds = ds.rename(cr)
    lon = ds['longitude']
    lat = ds['latitude']
    # Asegurar orden creciente
    if (np.diff(lon.values) < 0).any():
        lon = lon.sortby(lon)
    if (np.diff(lat.values) < 0).any():
        lat = lat.sortby(lat)
    ds.close()
    return lon, lat


def attach_common_attributes(ds_merged, start_dt, end_dt):
    """Añade metadatos globales solicitados y útiles."""
    ds_merged = ds_merged.assign_attrs({
        "title": "Producto integrado (ECMWF + GLORYS_024 + FMWAM) re-muestreado a grid GLORYS",
        "summary": "File 3D (longitude, latitude, time) con variables atmosféricas, oceanic y de wave.",
        "authors": "Amilcar E. Calzada & Oscar O. Diaz",
        "objective": "Creation of atmospheric and oceanic data for a predefined region based on global models, with a temporal step of 6 hours."
        "source_models": "ECMWF (atmosférico), GLORYS_024 (hydrodynamic), FMWAM (wave)",
        "temporal_step": "6 hours",
        "interpolation_method": "Bilineal (xarray.interp lineal 2D)",
        "time_handling": "Files aligned por time en cada carpeta",
        "created_with": "Python + xarray",
        "created_on": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ"),
        "time_span_utc": f"{start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')}",
    })
    return ds_merged


def build_encoding(ds, chunk_lon=256, chunk_lat=256):
    """Deende compresión y chunking razonable por variable, con dtype float32."""
    enc = {}
    # Dim order será (longitude, latitude, time); chunksizes deben respetar esto
    # Para time hacemos chunks de 1 para facilitar append
    for v in ds.data_vars:
        enc[v] = {
            "zlib": True,
            "complevel": 4,
            "dtype": "float32",
            "chunksizes": (min(chunk_lon, ds.dims['longitude']),
                           min(chunk_lat, ds.dims['latitude']),
                           1)
        }
    # Coord time
    if 'time' in ds.coords:
        enc['time'] = {"zlib": False}
    return enc


def write_first(out_path, ds, encoding):
    """Escribe el primer bloque creando el archivo."""
    ds.to_netcdf(out_path, mode='w', format='NETCDF4', encoding=encoding, unlimited_dims=['time'])


def append_to_file(out_path, ds, encoding):
    """Anexa nuevos times al NetCDF existente."""
    ds.to_netcdf(out_path, mode='a', format='NETCDF4', encoding=encoding, unlimited_dims=['time'])


# -----------------------------------------------------------------------------
# Main flow
# -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Integrador ECMWF + GLORYS_024 + FMWAM a grid GLORYS")
    ap.add_argument("--start", required=True, type=parse_datetime_arg, help="Date/time start (UTC) en formato YYYYMMDDHH")
    ap.add_argument("--end", required=True, type=parse_datetime_arg, help="Date/time end (UTC) en formato YYYYMMDDHH")
    ap.add_argument("--path_EHM", required=True, help="Path base GLORYS (ej: ./glorys)")
    ap.add_argument("--path_EAM", required=True, help="Path base ECMWF (ej: ./ecmwf)")
    ap.add_argument("--path_EWM", required=True, help="Path base FMWAM (ej: ./fmwam)")
    ap.add_argument("--out", required=True, help="Path del NetCDF de salida (ej: ./integrado_glorys_grid.nc)")
    ap.add_argument("--dryrun", action="store_true", help="Does not write file; only validates availability")
    args = ap.parse_args()

    start_dt = args.start
    end_dt = args.end

    # File GLORYS ejemplo para deendir la grilla objetivo
    first_ts = format_timestamp(start_dt)
    glorys_example = f"{args.path_EHM.rstrip('/')}/glorys024_{first_ts}.nc"

    # Construir grilla objetivo (longitude, latitude)
    try:
        target_lon, target_lat = build_target_grid(glorys_example)
    except FileNotFoundError:
        print(f"[ERROR] No se encontró archivo GLORYS ejemplo: {glorys_example}", file=sys.stderr)
        sys.exit(2)

    wrote_first = False
    out_path = args.out

    missing = []
    processed = 0

    for dt in daterange_6h(start_dt, end_dt):
        ts = format_timestamp(dt)
        f_glorys = f"{args.path_EHM.rstrip('/')}/glorys024_{ts}.nc"
        f_ecmwf  = f"{args.path_EAM.rstrip('/')}/ecmwf_{ts}.nc"
        f_fmwam  = f"{args.path_EWM.rstrip('/')}/fmwam_{ts}.nc"

        # Verificar existencia
        try:
            ds_glo = load_glorys(f_glorys)
        except FileNotFoundError:
            missing.append(f_glorys)
            continue
        try:
            ds_fmw = load_fmwam(f_fmwam)
        except FileNotFoundError:
            missing.append(f_fmwam)
            ds_fmw = None
        try:
            ds_ecm = load_ecmwf(f_ecmwf)
        except FileNotFoundError:
            missing.append(f_ecmwf)
            ds_ecm = None

        # Rejilla objetivo para ECMWF: recortar y reinterpolar
        if ds_ecm is not None:
            # Recorte aproximado al bbox de GLORYS para acelerar interp
            lon_min = float(target_lon.min().values)
            lon_max = float(target_lon.max().values)
            lat_min = float(target_lat.min().values)
            lat_max = float(target_lat.max().values)
            ds_ecm = ds_ecm.sel(longitude=slice(lon_min, lon_max), latitude=slice(lat_min, lat_max))
            ds_ecm = regrid_to_target(ds_ecm, target_lon, target_lat, method="linear")

        # FMWAM y GLORYS deben estar ya en la misma rejilla; por seguridad, reindex like
        ds_glo = ds_glo.reindex(longitude=target_lon, latitude=target_lat, method=None)
        if ds_fmw is not None:
            ds_fmw = ds_fmw.reindex(longitude=target_lon, latitude=target_lat, method=None)

        # Unificar time explícitamente desde el nombre del archivo
        tcoord = xr.DataArray(np.array([np.datetime64(dt)]), dims=("time",), coords={"time": [np.datetime64(dt)]})
        parts = []

        # Hidrodinámico (superficie)
        parts.append(ds_glo.expand_dims(time=tcoord))

        # Oleaje
        if ds_fmw is not None:
            parts.append(ds_fmw.expand_dims(time=tcoord))

        # Atmosférico (interp a grilla objetivo)
        if ds_ecm is not None:
            parts.append(ds_ecm.expand_dims(time=tcoord))

        # Merge
        ds_merged = xr.merge(parts, compat="override", combine_attrs="drop_conflicts")

        # Asegurar orden de dimensiones (longitude, latitude, time)
        order = ("longitude", "latitude", "time")
        ds_merged = ds_merged.transpose(*order)

        # Añadir metadatos globales (solo la primera vez; luego se preservan)
        if not wrote_first:
            ds_global = attach_common_attributes(ds_merged, start_dt, end_dt)
        else:
            ds_global = ds_merged

        if args.dryrun:
            processed += 1
            continue

        # Encoding y escritura incremental
        enc = build_encoding(ds_global)
        if not wrote_first:
            write_first(out_path, ds_global, enc)
            wrote_first = True
        else:
            append_to_file(out_path, ds_global, enc)

        # Liberar referencias antes de siguiente iteración
        del ds_glo, ds_fmw, ds_ecm, ds_merged, ds_global

        processed += 1

    # Reporte endal
    print(f"[OK] Tiempos procesados: {processed}")
    if missing:
        print("[WARN] Files faltantes:")
        for m in missing:
            print("  -", m)

    if args.dryrun and processed > 0:
        print("[DRYRUN] Ejecución de prueba exitosa (no se creó archivo).")

if __name__ == "__main__":
    # Silenciar warnings CF no críticos
    warnings.filterwarnings("ignore", category=UserWarning)
    main()

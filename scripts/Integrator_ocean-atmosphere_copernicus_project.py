#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrador de datos oceánicos y atmosféricos en una malla común (GLORYS_024)
-----------------------------------------------------------------------------

Autor(es): Amilcar E. Calzada & Oscar O. Diaz
Colaboración: (asistencia de IA)
Objetivo: Creación de datos atmosféricos y oceánicos para una región predeterminada
          a partir de modelos globales (GLORYS_024, ECMWF, FMWAM)
Tipo de datos: Rejilla regular lon/lat sin niveles (capa superficial), resol. ~1/12°
Interpolación: Bilineal por defecto hacia la malla de GLORYS_024

Entradas (archivos por tiempo, cada 6 horas):
  - Hidrodinámico (GLORYS_024): thetao, uo, vo
      patrón ejemplo: ./glorys/glorys024_aaaammddHH.nc
  - Atmosférico (ECMWF): 2t, 10u, 10v (lon 0–360 -> convertido a -180–180)
      patrón ejemplo: ./ecmwf/ecmwf_aaaammddHH.nc
  - Oleaje (FMWAM): VHM0_WW, VHM0_SW1, VMDR_WW, VMDR_SW1, VTM01_WW, VTM01_SW1
      patrón ejemplo: ./fmwam/fmwam_aaaammddHH.nc

Salida:
  - Un archivo NetCDF único con dimensiones (longitude, latitude, time) y todas
    las variables integradas.

Uso (ejemplo):
  python integrador_oceano_atmosfera_nc.py \
    --start 2024010100 --end 2024010300 --dt_hours 6 \
    --path_ehm "./glorys/glorys024_aaaammddHH.nc" \
    --path_eam "./ecmwf/ecmwf_aaaammddHH.nc" \
    --path_ewm "./fmwam/fmwam_aaaammddHH.nc" \
    --out integrated_glorys_grid.nc

Notas:
  - Manejo de memoria con dask + xarray (chunking configurable)
  - Selección de superficie para GLORYS si existen niveles (depth/deptht/lev)
  - Los tiempos deben existir en cada carpeta; el script verifica presencia
  - Orden final de dimensiones: (longitude, latitude, time)

"""
from __future__ import annotations
import argparse
import re
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
import xarray as xr

# ---------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------

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
    """Asegura que recibimos un *template* con 'aaaammddHH'.
    Si nos pasan un directorio, construye un template por modelo.
    Si nos pasan un path sin el token, lanza error explícito.
    """
    if os.path.isdir(path_or_template):
        # Construir por defecto según el modelo
        defaults = {
            "GLORYS": "glorys024_aaaammddHH.nc",
            "ECMWF": "ecmwf_aaaammddHH.nc",
            "FMWAM": "fmwam_aaaammddHH.nc",
        }
        fname = defaults.get(model.upper(), "file_aaaammddHH.nc")
        return os.path.join(path_or_template, fname)
    if "aaaammddHH" not in path_or_template:
        raise ValueError(
            f"El argumento para {model} debe ser un template con 'aaaammddHH' o un directorio. "
            f"Recibido: {path_or_template}"
        )
    return path_or_template


def _expand_template(template: str, t: datetime) -> str:
    """Reemplaza 'aaaammddHH' en el template por la fecha/hora formateada."""
    return template.replace("aaaammddHH", t.strftime("%Y%m%d%H"))


def _exists_all(paths: List[str]) -> List[str]:
    missing = [p for p in paths if not os.path.exists(p)]
    return missing


def _standardize_lon_to_180(da: xr.DataArray | xr.Dataset,
                            lon_names: Tuple[str, ...] = ("lon", "longitude")) -> xr.Dataset:
    """Convierte longitudes de 0–360 a -180–180 y ordena crecientemente.
    Devuelve Dataset (si entra DataArray, lo convierte temporalmente).
    """
    ds = da.to_dataset(name=da.name) if isinstance(da, xr.DataArray) else da

    lon_name = None
    for name in lon_names:
        if name in ds.coords:
            lon_name = name
            break
        if name in ds.dims:
            lon_name = name
            break
    if lon_name is None:
        return ds  # no-op si no encontramos lon

    lon = ds[lon_name]
    if lon.max() > 180:
        new_lon = ((lon + 180) % 360) - 180
        ds = ds.assign_coords({lon_name: new_lon})
        ds = ds.sortby(lon_name)
    return ds


def _select_surface_if_present(ds: xr.Dataset) -> xr.Dataset:
    """Si existen niveles, seleccionar el de superficie.
    Busca coordenadas típicas: depth, deptht, lev, z, o nivel equivalente.
    """
    for zname in ["depth", "deptht", "lev", "depthu", "depthv", "z"]:
        if zname in ds.dims or zname in ds.coords:
            coord = ds[zname]
            # Preferir el nivel más cercano a 0
            if np.issubdtype(coord.dtype, np.number):
                idx = int(np.abs(coord - 0).argmin())
            else:
                idx = 0
            ds = ds.isel({zname: idx})
            # Limpia el nombre de dimensión si queda como coord auxiliar
            if zname in ds.dims and ds.sizes.get(zname, 1) == 1:
                ds = ds.squeeze(dim=zname, drop=True)
            break
    return ds


def _open_concat(files: List[str], chunks: Optional[dict] = None,
                 vars_keep: Optional[List[str]] = None,
                 engine: Optional[str] = None) -> xr.Dataset:
    if len(files) == 0:
        raise ValueError("No se proporcionaron archivos para abrir.")

    def _preprocess(ds: xr.Dataset) -> xr.Dataset:
        if vars_keep is not None:
            keep = [v for v in vars_keep if v in ds]
            ds = ds[keep]
        return ds

    try:
        ds = xr.open_mfdataset(
            files,
            combine='nested',
            concat_dim='time',
            parallel=True,
            preprocess=_preprocess,
            chunks=chunks,
            engine="netcdf4",   # Fuerza el motor netcdf4 para mayor robustez
            decode_times=True,
            coords='minimal',
            compat='override'
        )
    except Exception as e:
        # Mensaje más claro cuando accidentalmente se pasa un directorio
        first = files[0]
        if os.path.isdir(first):
            raise RuntimeError(
                f"Se intentó abrir un directorio como NetCDF: {first}. "
                f"Asegúrate de pasar un *template* con 'aaaammddHH.nc' o un directorio válido."
            ) from e
        raise
    return ds


def _ensure_latlon_names(ds: xr.Dataset,
                         lon_aliases=("lon", "longitude"),
                         lat_aliases=("lat", "latitude")) -> xr.Dataset:
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
    if lon_name is None or lat_name is None:
        return ds
    # Renombrar a (longitude, latitude) si fuera necesario
    rename = {}
    if lon_name != "longitude":
        rename[lon_name] = "longitude"
    if lat_name != "latitude":
        rename[lat_name] = "latitude"
    if rename:
        ds = ds.rename(rename)
    return ds


# ---------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------

def build_and_save_integrated(
    start: str,
    end: str,
    dt_hours: int,
    path_ehm: str,  # GLORYS
    path_eam: str,  # ECMWF
    path_ewm: str,  # FMWAM
    out_path: str,
    chunks: Optional[dict] = None,
    compression_level: int = 4,
):
    # Normalizar templates (acepta directorios o template con token)
    path_ehm = _ensure_template(path_ehm, "GLORYS")
    path_eam = _ensure_template(path_eam, "ECMWF")
    path_ewm = _ensure_template(path_ewm, "FMWAM")

    times = _build_times(start, end, dt_hours)

    files_ehm = [_expand_template(path_ehm, t) for t in times]
    files_eam = [_expand_template(path_eam, t) for t in times]
    files_ewm = [_expand_template(path_ewm, t) for t in times]

    # Verificación de existencia
    miss_ehm = _exists_all(files_ehm)
    miss_eam = _exists_all(files_eam)
    miss_ewm = _exists_all(files_ewm)
    if miss_ehm or miss_eam or miss_ewm:
        msg = []
        if miss_ehm:
            msg.append(f"GLORYS faltantes ({len(miss_ehm)}):\n  - " + "\n  - ".join(miss_ehm[:5]) + ("\n  ..." if len(miss_ehm) > 5 else ""))
        if miss_eam:
            msg.append(f"ECMWF faltantes ({len(miss_eam)}):\n  - " + "\n  - ".join(miss_eam[:5]) + ("\n  ..." if len(miss_eam) > 5 else ""))
        if miss_ewm:
            msg.append(f"FMWAM faltantes ({len(miss_ewm)}):\n  - " + "\n  - ".join(miss_ewm[:5]) + ("\n  ..." if len(miss_ewm) > 5 else ""))
        raise FileNotFoundError("\n".join(msg))

    # Log breve de resolución
    print("Ejemplo de resoluciones:")
    print("  GLORYS ->", files_ehm[0])
    print("  ECMWF  ->", files_eam[0])
    print("  FMWAM  ->", files_ewm[0])

    # 1) Abrir GLORYS (grid objetivo) y reducir a superficie si aplica
    ds_ehm = _open_concat(
        files_ehm,
        chunks=chunks if chunks else {"time": 1, "latitude": 540, "longitude": 540},
        vars_keep=["thetao", "uo", "vo"],
    )
    ds_ehm = _ensure_latlon_names(ds_ehm)
    ds_ehm = _select_surface_if_present(ds_ehm)

    # Guardar grilla objetivo
    lon_tgt = ds_ehm["longitude"]
    lat_tgt = ds_ehm["latitude"]

    # 2) Abrir ECMWF, estandarizar lon y renombrar coords
    ds_eam = _open_concat(
        files_eam,
        chunks=chunks if chunks else {"time": 1, "latitude": 540, "longitude": 540},
        vars_keep=None,
    )
    ds_eam = _ensure_latlon_names(ds_eam)
    ds_eam = _standardize_lon_to_180(ds_eam)

    # Normalizar nombres de variables ECMWF a aliases canónicos
    ecmwf_alias = {
        "10_metre_u_wind_component": "10u",
        "10_metre_v_wind_component": "10v",
        "2_metre_temperature": "2t",
        "u10": "10u",
        "v10": "10v",
        "t2m": "2t",
        "10u": "10u",
        "10v": "10v",
        "2t": "2t",
    }
    rename_map = {k: v for k, v in ecmwf_alias.items() if k in ds_eam}
    if rename_map:
        ds_eam = ds_eam.rename(rename_map)
    # Filtrar a las tres deseadas si existen
    keep_vars = [v for v in ["2t", "10u", "10v"] if v in ds_eam]
    if keep_vars:
        ds_eam = ds_eam[keep_vars]

    # Interpolar ECMWF -> grilla GLORYS (bilineal)
    ds_eam_i = ds_eam.interp(longitude=lon_tgt, latitude=lat_tgt, method="linear")

    # 3) Abrir FMWAM (posible misma grilla que GLORYS)
    ds_ewm = _open_concat(
        files_ewm,
        chunks=chunks if chunks else {"time": 1, "latitude": 540, "longitude": 540},
        vars_keep=[
            "VHM0_WW", "VHM0_SW1",
            "VMDR_WW", "VMDR_SW1",
            "VTM01_WW", "VTM01_SW1",
        ],
    )
    ds_ewm = _ensure_latlon_names(ds_ewm)

    # Si difiere levemente, interpolar a la grilla objetivo
    if not (np.array_equal(ds_ewm["longitude"].values, lon_tgt.values) and
            np.array_equal(ds_ewm["latitude"].values, lat_tgt.values)):
        ds_ewm = ds_ewm.interp(longitude=lon_tgt, latitude=lat_tgt, method="linear")

    # 4) Alinear tiempos (en caso de diferencias minúsculas por decodificación)
    # Forzamos el mismo vector de tiempo
    ds_ehm["time"] = np.array(times, dtype="datetime64[ns]")
    ds_eam_i["time"] = np.array(times, dtype="datetime64[ns]")
    ds_ewm["time"] = np.array(times, dtype="datetime64[ns]")

    # 5) Merge
    ds_all = xr.merge([ds_ehm, ds_eam_i, ds_ewm], compat="override", join="exact")

    # 6) Orden final de dimensiones (longitude, latitude, time)
    # xarray suele preferir (time, lat, lon); aquí se transpone a pedido
    ds_all = ds_all.transpose("longitude", "latitude", "time")

    # 7) Atributos globales
    ds_all.attrs.update({
        "title": "Archivo Integrado Atmosférico-Oceánico en Malla GLORYS_024",
        "summary": (
            "Variables atmosféricas (ECMWF: 2t, 10u, 10v), oceánicas (GLORYS_024: "
            "thetao, uo, vo) y de oleaje (FMWAM: VHM0_WW, VHM0_SW1, VMDR_WW, "
            "VMDR_SW1, VTM01_WW, VTM01_SW1) reamostradas/interpoladas a la malla "
            "GLORYS_024. Tiempo cada 6 h."
        ),
        "authors": "Amilcar E. Calzada & Oscar O. Diaz",
        "institution": "Proyecto de integración meteo-oceánica",
        "source_models": "hydrodynamic_model=glorys_24; weather_model=ecmwf; wave_model=fmwam",
        "grid_target": "GLORYS_024 lon/lat (xfirst=-90, yfirst=9, dx≈0.083333°, dy≈0.083333°)",
        "method_interpolation": "Bilineal (xarray.interp, método='linear')",
        "time_step_hours": dt_hours,
        "created_on": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conventions": "CF-1.8",
        "note": (
            "ECMWF lon 0–360 convertido a -180–180 y ordenado; selección de superficie "
            "para GLORYS si aplica; manejo de memoria con chunks (dask)."
        ),
    })

    # Atributos por variable (si existen)
    var_attrs = {
        "2t": dict(long_name="2-metre temperature", units="K"),
        "10u": dict(long_name="10-metre U wind component", units="m s-1"),
        "10v": dict(long_name="10-metre V wind component", units="m s-1"),
        "thetao": dict(long_name="Sea water potential temperature (surface)", units="degC"),
        "uo": dict(long_name="Sea water velocity U (surface)", units="m s-1"),
        "vo": dict(long_name="Sea water velocity V (surface)", units="m s-1"),
        "VHM0_WW": dict(long_name="Significant wind wave height", units="m"),
        "VHM0_SW1": dict(long_name="Significant primary swell wave height", units="m"),
        "VMDR_WW": dict(long_name="Wind-sea mean wave direction", units="degree_from_north"),
        "VMDR_SW1": dict(long_name="Primary swell mean wave direction", units="degree_from_north"),
        "VTM01_WW": dict(long_name="Wind-sea mean wave period (Tm01)", units="s"),
        "VTM01_SW1": dict(long_name="Primary swell mean wave period (Tm01)", units="s"),
    }
    for v, a in var_attrs.items():
        if v in ds_all:
            ds_all[v].attrs.update(a)

    # 8) Compresión y escritura
    enc = {}
    for v in ds_all.data_vars:
        enc[v] = {"zlib": True, "complevel": compression_level, "_FillValue": np.nan}
        # Reordenar dimensiones a (longitude, latitude, time) si es necesario
        dims = ds_all[v].dims
        target_dims = ("longitude", "latitude", "time")
        if dims != target_dims:
            ds_all[v] = ds_all[v].transpose(*target_dims)

    # Escribir NetCDF final
    ds_all.to_netcdf(out_path, format="NETCDF4", encoding=enc)
    print(f"Archivo escrito: {out_path}")


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Integra ECMWF + GLORYS_024 + FMWAM en malla GLORYS (bilineal)"
    )
    p.add_argument("--start", type=lambda s: re.sub(r'[^\d]', '', s), 
                    required=True,
                    help="Initial date/hour in YYYYMMDDHH or YYYY-MM-DD-HH format.")
    p.add_argument("--end", type=lambda s: re.sub(r'[^\d]', '', s), 
                    required=True,
                    help="Final date/hour in YYYYMMDDHH or YYYY-MM-DD-HH format.")
    p.add_argument("--dt_hours", type=int, default=6, help="Paso temporal en horas (default=6)")
    p.add_argument("--path_ehm", required=True, help="Directorio o template GLORYS (ej. ./glorys o ./glorys/glorys024_aaaammddHH.nc)")
    p.add_argument("--path_eam", required=True, help="Directorio o template ECMWF (ej. ./ecmwf o ./ecmwf/ecmwf_aaaammddHH.nc)")
    p.add_argument("--path_ewm", required=True, help="Directorio o template FMWAM (ej. ./fmwam o ./fmwam/fmwam_aaaammddHH.nc)")
    p.add_argument("--out", default="integrated_glorys_grid.nc", help="Ruta del NetCDF de salida")
    p.add_argument("--chunk_lon", type=int, default=540, help="Chunk en longitud (default=540)")
    p.add_argument("--chunk_lat", type=int, default=540, help="Chunk en latitud (default=540)")
    p.add_argument("--chunk_time", type=int, default=1, help="Chunk en tiempo (default=1)")
    p.add_argument("--compression", type=int, default=4, help="Nivel de compresión zlib (0-9)")
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
        path_ehm=args.path_ehm,
        path_eam=args.path_eam,
        path_ewm=args.path_ewm,
        out_path=args.out,
        chunks=chunks,
        compression_level=args.compression,
    )


if __name__ == "__main__":
    main()

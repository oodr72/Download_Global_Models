#!/usr/bin/env python3
# coding: utf-8
"""
Download and subset ECMWF HRES (0.25°) forecast fields to a custom
longitude/latitude box and write them to compressed NetCDF files.

Changes 2025‑08‑07
------------------
* **Fix pygrib sub‑setting** – convert longitude field to 0‑360 before
  masking so dateline‑crossing domains work correctly (bug showed up as
  725×181 grids instead of 365×181 for –90→1°E).
* Replace deprecated `datetime.utcnow()` with timezone‑aware
  `datetime.now(timezone.utc)`.

Usage examples
--------------
$ python -m scripts.get_ecmwf
$ python -m scripts.get_ecmwf --start_date 20250805 \
        --run_hour 12 --days_number 1 --time_step 3 \
        --domain atlantic --variables 2t 10u 10v

The script needs a ``config.py`` providing the keys documented in the
header of the previous version.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
import timeit
from datetime import datetime, timedelta, timezone
from typing import Sequence
from urllib.parse import urlparse

import numpy as np
import requests
import xarray as xr
import pygrib  # type: ignore
from netCDF4 import Dataset as ncdf4Dataset  # type: ignore

from config import config

# -----------------------------------------------------------------------------
# CLI helpers
# -----------------------------------------------------------------------------

def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and subset ECMWF forecast data to a lon/lat box.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start_date", type=str, default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD format.")
    parser.add_argument("--days_number", type=int, default=config.ECMWF_days_number,
                        help="Number of forecast days to download (max 10).")
    parser.add_argument("--domain", type=str, default=config.ECMWF_domain,
                        help="Domain name defined in config.domains.")
    parser.add_argument("--run_hour", type=str, default=config.ECMWF_run_hour,
                        help="IFS run hour (00, 06, 12 or 18).")
    parser.add_argument("--time_step", type=int, default=config.ECMWF_time_step,
                        help="Time‑step between forecast files in hours.")
    parser.add_argument("--outpath", type=str, default=config.ECMWF_output_directory,
                        help="Base output directory.")
    parser.add_argument("--engine", choices=["cfgrib", "pygrib"], default="pygrib",
                        help="Engine to use for GRIB→NetCDF conversion.")
    parser.add_argument("--variables", nargs="*", default=config.ECMWF_variables,
                        help="Space‑separated list of GRIB shortNames to retain (e.g. 2t 10u 10v).")
    return parser.parse_args()

# -----------------------------------------------------------------------------
# URL generation
# -----------------------------------------------------------------------------

def _generate_ecmwf_urls(date: str, hour: str, max_forecast_hour: int, step: int,
                         variables: Sequence[str] | None) -> list[str]:
    base = "https://data.ecmwf.int/forecasts"
    pfilter = f"?param={'/'.join(variables)}" if variables else ""
    urls: list[str] = []
    for fh in range(0, max_forecast_hour + 1, step):
        fstr = f"{fh}h" if fh else "0h"
        fname = f"{date}{hour}0000-{fstr}-oper-fc.grib2"
        urls.append(f"{base}/{date}/{hour}z/ifs/0p25/oper/{fname}{pfilter}")
    return urls

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _remove_idx_files(grib_path: str) -> None:
    for idx in glob.glob(f"{grib_path}.*.idx"):
        try:
            os.remove(idx)
        except OSError:
            pass

# -----------------------------------------------------------------------------
# Subsetting routines
# -----------------------------------------------------------------------------

def _subset_bbox(ds: xr.Dataset, lon_min: float, lon_max: float, lat_min: float, lat_max: float) -> xr.Dataset:
    ds = ds.assign_coords(longitude=((ds.longitude + 360) % 360))
    lon_min %= 360
    lon_max %= 360
    if lon_min <= lon_max:
        ds = ds.sel(longitude=slice(lon_min, lon_max))
    else:
        east = ds.sel(longitude=slice(lon_min, 360))
        west = ds.sel(longitude=slice(0, lon_max))
        ds = xr.concat([east, west], dim="longitude")
    if lat_max < lat_min:
        lat_min, lat_max = lat_max, lat_min
    ds = ds.sel(latitude=slice(lat_max, lat_min))
    return ds

# -----------------------------------------------------------------------------
# cfgrib path
# -----------------------------------------------------------------------------

def _process_with_cfgrib(grib_path: str, nc_path: str, bbox: dict[str, float],
                         variables: Sequence[str] | None) -> tuple[int, int]:
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    if variables:
        keep = [v for v in ds.data_vars if ds[v].attrs.get("GRIB_shortName") in set(variables)]
        if not keep:
            raise RuntimeError("Requested variables not present in GRIB file.")
        ds = ds[keep]
    ds = _subset_bbox(ds, bbox["lon_min"], bbox["lon_max"], bbox["lat_min"], bbox["lat_max"])
    enc = {v: {"zlib": True, "complevel": 4} for v in ds.data_vars}
    ds.to_netcdf(nc_path, format="NETCDF4_CLASSIC", encoding=enc)
    return ds.dims.get("longitude", 0), ds.dims.get("latitude", 0)

# -----------------------------------------------------------------------------
# pygrib path (fixed)
# -----------------------------------------------------------------------------

def _process_with_pygrib(grib_path: str, nc_path: str, bbox: dict[str, float], fh: int,
                         variables: Sequence[str] | None) -> tuple[int, int]:
    lon_min, lon_max, lat_min, lat_max = bbox.values()
    lon_min_mod = lon_min % 360
    lon_max_mod = lon_max % 360

    grbs = pygrib.open(grib_path)
    lats, lons = grbs[1].latlons()
    lons = (lons + 360) % 360  # <‑‑‑ key fix: put grid in 0‑360 before masking

    if lon_min_mod <= lon_max_mod:
        mask = ((lats >= lat_min) & (lats <= lat_max) &
                (lons >= lon_min_mod) & (lons <= lon_max_mod))
    else:
        mask = ((lats >= lat_min) & (lats <= lat_max) &
                ((lons >= lon_min_mod) | (lons <= lon_max_mod)))

    lats_sub = np.unique(lats[mask]); lats_sub.sort()
    lons_sub = np.unique(lons[mask]); lons_sub.sort()

    with ncdf4Dataset(nc_path, "w", format="NETCDF4") as nc:
        nc.createDimension("time", None)
        nc.createDimension("latitude", len(lats_sub))
        nc.createDimension("longitude", len(lons_sub))

        tvar = nc.createVariable("time", "f8", ("time",))
        tvar.units = f"hours since {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}"
        tvar[:] = [fh]
        nc.createVariable("latitude", "f4", ("latitude",))[:] = lats_sub
        nc.createVariable("longitude", "f4", ("longitude",))[:] = lons_sub

        written: set[str] = set()
        for g in grbs:
            if g.typeOfLevel not in {"surface", "meanSea", "heightAboveGround", "atmosphereSingleLayer", "depthBelowLand"}:
                continue
            if variables and g.shortName not in variables:
                continue
            base = g.name.replace(" ", "_").lower()
            if base in written:
                base = f"{base}_{g.typeOfLevel}_{g.level}"
            i = 1
            while base in written:
                base = f"{base}_{i}"; i += 1
            written.add(base)

            data = np.full((len(lats_sub), len(lons_sub)), np.nan, dtype=np.float32)
            vals = g.values
            for irow in range(lats.shape[0]):
                for jcol in range(lats.shape[1]):
                    if mask[irow, jcol]:
                        ilat = np.where(lats_sub == lats[irow, jcol])[0][0]
                        ilon = np.where(lons_sub == lons[irow, jcol])[0][0]
                        data[ilat, ilon] = vals[irow, jcol]
            v = nc.createVariable(base, "f4", ("time", "latitude", "longitude"), zlib=True, complevel=4)
            v.units = g.units
            v[0, :, :] = data
    return len(lons_sub), len(lats_sub)

# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------

def _process_grib(
    grib_path: str,
    nc_path: str,
    bbox: dict[str, float],
    engine: str,
    fh: int,
    variables: Sequence[str] | None,
) -> tuple[int, int]:
    if engine == "cfgrib":
        return _process_with_cfgrib(grib_path, nc_path, bbox, variables)
    if engine == "pygrib":
        return _process_with_pygrib(grib_path, nc_path, bbox, fh, variables)
    raise ValueError(f"Unknown engine '{engine}'.")

# -----------------------------------------------------------------------------
# Driver routine
# -----------------------------------------------------------------------------

def _download_and_process(
    start_date: str,
    run_hour: str,
    days_number: int,
    time_step: int,
    bbox: dict[str, float],
    out_dir: str,
    engine: str,
    variables: Sequence[str] | None,
) -> str:
    max_hour = min(240, days_number * 24)

    raw_dir = os.path.join(out_dir, "raw_downloads")
    #proc_dir = os.path.join(out_dir, f"{start_date}_{run_hour}")
    os.makedirs(raw_dir, exist_ok=True)
    #os.makedirs(proc_dir, exist_ok=True)

    log_file = os.path.join(out_dir, "ecmwf_download.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.info(
        "Start ECMWF download: date=%s run=%sz range=0-%sh step=%s engine=%s vars=%s bbox=%s",
        start_date,
        run_hour,
        max_hour,
        time_step,
        engine,
        "all" if not variables else " ".join(variables),
        bbox,
    )

    urls = _generate_ecmwf_urls(start_date, run_hour, max_hour, time_step, variables)

    for url in urls:
        fname = os.path.basename(urlparse(url).path)
        # forecast hour extraction ------------------------------------------------------
        try:
            fh = 0 if fname.endswith("0h-oper-fc.grib2") else int(re.search(r"-(\d+)h-oper", fname).group(1))  # type: ignore
        except Exception as ex:  # pragma: no cover
            logging.error("Cannot parse forecast hour from %s: %s", fname, ex)
            continue

        valid_dt = datetime.strptime(f"{start_date}{run_hour}", "%Y%m%d%H") + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")
        grib_path = os.path.join(raw_dir, fname)
        #nc_path = os.path.join(proc_dir, f"ecmwf_{valid_str}.nc")
        nc_path = os.path.join(out_dir, f"ecmwf_{valid_str}.nc")

        if os.path.exists(nc_path):
            logging.info("Skip existing %s", nc_path)
            continue

        # download ---------------------------------------------------------------------
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            with open(grib_path, "wb") as f:
                f.write(r.content)
            logging.info("Downloaded %s", fname)
        except Exception as ex:
            logging.warning("Failed download %s: %s", url, ex)
            continue

        # process ----------------------------------------------------------------------
        try:
            nx, ny = _process_grib(grib_path, nc_path, bbox, engine, fh, variables)
            logging.info("Saved %s (%dx%d)", nc_path, nx, ny)
        except Exception as ex:
            logging.exception("Processing failed for %s: %s", fname, ex)
        finally:
            _remove_idx_files(grib_path)
            try:
                os.remove(grib_path)
            except OSError:
                pass

    return log_file

# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    args = _parse_arguments()
    print("Execution parameters:")
    for k, v in vars(args).items():
        print(f"  {k}: {v}")

    if args.domain not in config.domains:
        print(f"Domain '{args.domain}' not in config.domains; available: {list(config.domains)}")
        sys.exit(1)

    bbox = config.domains[args.domain]

    t0 = timeit.default_timer()
    log_file = _download_and_process(
        start_date=args.start_date,
        run_hour=args.run_hour,
        days_number=args.days_number,
        time_step=args.time_step,
        bbox=bbox,
        out_dir=args.outpath,
        engine=args.engine,
        variables=args.variables,
    )
    elapsed = timeit.default_timer() - t0
    print(f"Finished in {elapsed/60:.1f} min – see log {log_file}")


if __name__ == "__main__":
    main()

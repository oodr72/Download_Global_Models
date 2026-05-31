#!/usr/bin/env python3
"""
downloading_gfs.py
------------------
Download GFS 0.25° GRIB2 files and convert them to NetCDF, keeping:

  • surface fields
  • mean‑sea‑level fields
  • height‑above‑ground fields at 0 m, 2 m and 10 m

All files for one run are stored in <outpath>/<YYYYMMDDHH>/.

Requires
--------
* requests
* xarray + cfgrib  (default engine)
* pygrib           (optional engine --engine pygrib)
* netCDF4 / h5netcdf
* eccodes libs on the system
"""
from __future__ import annotations

import argparse
import sys
import timeit
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from config import config  # your project's config/config.py
from src.model_utils import forecast_hours


# ========================================================================= #
# CLI                                                                       #
# ========================================================================= #
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Download GFS grids and convert to NetCDF keeping "
            "surface, meanSea and heightAboveGround (0/2/10 m) fields."
        )
    )
    p.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                   help='Initial date in "yyyymmdd"')
    p.add_argument("--time", default=config.GFS_run_time,
                   choices=["00", "06", "12", "18"],
                   help='Run initialisation ("00", "06", "12", "18")')
    p.add_argument("--timestep", type=int, default=config.GFS_timestep,
                   help="Forecast‑hour step (h)")
    p.add_argument("--last_hour", type=int, default=int(config.GFS_last_hour),
                   help="Last forecast hour to fetch (inclusive)")
    p.add_argument("--variables", nargs="+", default=config.GFS_variables,
                   help="GRIB variables, e.g. UGRD VGRD TMP HGT")
    p.add_argument("--outpath", default=config.GFS_output_directory,
                   help="Root output folder")
    p.add_argument("--domain", default=config.GFS_domain,
                   help="Key name of the domain in config.domains")
    p.add_argument("--format", choices=["grib2", "netcdf"], default="netcdf",
                   help="Store files as GRIB2 (raw) or NetCDF (default)")
    p.add_argument("--keep-grib2", action="store_true",
                   help="When --format netcdf, keep the original GRIB2 files")
    p.add_argument("--engine", choices=["cfgrib", "pygrib"], default="cfgrib",
                   help="Backend to read GRIB2 files")
    return p.parse_args()


# ========================================================================= #
# Helpers                                                                   #
# ========================================================================= #
def make_run_folder(root: str | Path, date: str, init: str) -> Path:
    run_dir = Path(root).expanduser().resolve() / f"{date}{init}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def build_url(date: str, init: str, fhour: str, vars_string: str,
              lon_left: float, lon_right: float, lat_top: float, lat_bottom: float) -> str:
    base = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    file_param = f"gfs.t{init}z.pgrb2.0p25.{fhour}"
    return (f"{base}?file={file_param}&{vars_string}"
            f"&subregion=&leftlon={lon_left}&rightlon={lon_right}"
            f"&toplat={lat_top}&bottomlat={lat_bottom}"
            f"&dir=%2Fgfs.{date}%2F{init}%2Fatmos")


def download_file(url: str, dest: Path, min_kb: int = 100) -> None:
    if dest.is_file() and dest.stat().st_size / 1024 > min_kb:
        print(f"✔ {dest.name} exists ({dest.stat().st_size/1024:.0f} KB) – skipping")
        return
    print(f"⇩  Downloading {dest.name} …")
    r = requests.get(url, timeout=60)
    if r.status_code == 200:
        dest.write_bytes(r.content)
        print(f"   Saved {dest}")
    else:
        raise RuntimeError(f"HTTP {r.status_code} while fetching {dest.name}")


# ========================================================================= #
# GRIB → NetCDF conversion helpers                                           #
# ========================================================================= #
SURFACE_TYPES = {"surface", "meanSea"}
HAG_TYPE = "heightAboveGround"
HAG_LEVELS = {0, 2, 10}  # metres

# --------------------- cfgrib backend ------------------------------------ #
def convert_with_cfgrib(
    grib_path: Path, keep_grib: bool
) -> Path:
    import xarray as xr
    import cfgrib
    import warnings

    nc_path = grib_path.with_suffix(".nc")
    if nc_path.exists() and nc_path.stat().st_size > 0:
        print(f"✔ {nc_path.name} already converted – skipping")
        return nc_path

    idx = cfgrib.open_fileindex(str(grib_path))
    # pre‑select messages we want
    wanted_msgs = [
        msg for msg in idx if (
            (msg["typeOfLevel"] in SURFACE_TYPES) or
            (msg["typeOfLevel"] == HAG_TYPE and msg["level"] in HAG_LEVELS)
        )
    ]
    idx.close()
    if not wanted_msgs:
        raise RuntimeError("No desired messages found in file")

    # split by (typeOfLevel, level) -----------------------------------------
    datasets = []
    for msg in wanted_msgs:
        fkeys = {"typeOfLevel": msg["typeOfLevel"]}
        if msg["typeOfLevel"] == HAG_TYPE:
            fkeys["level"] = msg["level"]

        try:
            ds = xr.open_dataset(
                grib_path,
                engine="cfgrib",
                backend_kwargs={"filter_by_keys": fkeys},
            )
            datasets.append(ds)
        except Exception as exc:
            warnings.warn(f"Skipped subset {fkeys}: {exc}")

    if not datasets:
        raise RuntimeError("cfgrib could not open any desired subset")

    try:
        merged = xr.merge(datasets, compat="override")
        try:
            merged.to_netcdf(nc_path)
        finally:
            merged.close()
    finally:
        for ds in datasets:
            ds.close()
    print(f"   NetCDF saved: {nc_path}")

    if not keep_grib:
        grib_path.unlink()
    return nc_path


# --------------------- pygrib backend ------------------------------------ #
def convert_with_pygrib(
    grib_path: Path, keep_grib: bool
) -> Path:
    import pygrib
    import numpy as np
    import xarray as xr

    nc_path = grib_path.with_suffix(".nc")
    if nc_path.exists() and nc_path.stat().st_size > 0:
        print(f"✔ {nc_path.name} already converted – skipping")
        return nc_path

    print(f"⚙  pygrib: {grib_path.name} → NetCDF")

    ds_vars = {}
    with pygrib.open(str(grib_path)) as grbs:
        store: dict[str, dict[int, pygrib.message]] = defaultdict(dict)

        for g in grbs:
            if g.typeOfLevel in SURFACE_TYPES:
                store[g.shortName][0] = g                       # level 0 for 2‑D
            elif g.typeOfLevel == HAG_TYPE and g.level in HAG_LEVELS:
                store[g.shortName][g.level] = g
            # ignore everything else

        if not store:
            raise RuntimeError("No desired messages found")

        for short, msgs_by_level in store.items():
            levels = sorted(msgs_by_level)
            msgs = [msgs_by_level[lev] for lev in levels]
            sample = msgs[0]
            lats, lons = sample.latlons()

            if sample.typeOfLevel == HAG_TYPE:
                data = np.stack([m.values for m in msgs], axis=0)  # (level,y,x)
                da = xr.DataArray(
                    data,
                    coords=dict(level=("level", levels),
                                latitude=(("y", "x"), lats),
                                longitude=(("y", "x"), lons)),
                    dims=("level", "y", "x"),
                    name=short,
                    attrs=dict(units=sample.units, long_name=sample.name),
                )
            else:  # surface / meanSea
                da = xr.DataArray(
                    sample.values,
                    coords=dict(latitude=(("y", "x"), lats),
                                longitude=(("y", "x"), lons)),
                    dims=("y", "x"),
                    name=short,
                    attrs=dict(units=sample.units, long_name=sample.name),
                )
            ds_vars[short] = da

    xr.Dataset(ds_vars).to_netcdf(nc_path)
    print(f"   NetCDF saved: {nc_path}")

    if not keep_grib:
        grib_path.unlink()
    return nc_path


def convert_to_netcdf(
    grib_path: Path,
    keep_grib: bool,
    engine: str,
) -> Path:
    if engine == "pygrib":
        return convert_with_pygrib(grib_path, keep_grib)
    else:
        return convert_with_cfgrib(grib_path, keep_grib)


# ========================================================================= #
# Main logic                                                                #
# ========================================================================= #
def main(
    date_str: str,
    init_str: str,
    timestep: int,
    last_hour: int,
    variables: Iterable[str],
    run_dir: Path,
    domain_coords: dict[str, float],
    fmt: str,
    keep_grib2: bool,
    engine: str,
) -> None:
    lon_left, lon_right = domain_coords["lon_min"], domain_coords["lon_max"]
    lat_top, lat_bottom = domain_coords["lat_max"], domain_coords["lat_min"]

    var_params = "&".join(f"var_{v}=on" for v in variables)

    # analysis ----------------------------------------------------------------
    anl_url = build_url(date_str, init_str, "anl", var_params,
                        lon_left, lon_right, lat_top, lat_bottom)
    anl_path = run_dir / f"gfs_{date_str}{init_str}.grb2"
    download_file(anl_url, anl_path)

    # forecasts ---------------------------------------------------------------
    for fh in forecast_hours(last_hour, timestep, include_zero=False):
        fh_str = f"f{fh:03d}"
        forecast_date = (datetime.strptime(date_str + init_str, "%Y%m%d%H")
                         + timedelta(hours=fh)).strftime("%Y%m%d%H")
        fcst_path = run_dir / f"gfs_{forecast_date}.grb2"
        fcst_url = build_url(date_str, init_str, fh_str, var_params,
                             lon_left, lon_right, lat_top, lat_bottom)
        download_file(fcst_url, fcst_path)

    # convert -----------------------------------------------------------------
    if fmt == "netcdf":
        print("\n=== Converting downloaded GRIB2 files to NetCDF ===")
        for grib in run_dir.glob("*.grb2"):
            try:
                convert_to_netcdf(grib,
                                  keep_grib=keep_grib2,
                                  engine=engine)
            except Exception as exc:
                print(f"⚠  {grib.name}: conversion failed ({exc})")


# ========================================================================= #
# Entrypoint                                                                #
# ========================================================================= #
if __name__ == "__main__":
    opts = parse_cli()

    try:
        domain_coords = config.domains[opts.domain]
    except KeyError:
        print(f"Domain “{opts.domain}” not found; choose from {list(config.domains)}")
        sys.exit(1)

    run_folder = make_run_folder(opts.outpath, opts.date, opts.time)

    print("\n=== PARAMETERS =====================================================")
    for k, v in vars(opts).items():
        print(f"{k:12s}: {v}")
    print(f"run_folder : {run_folder}")
    print("====================================================================\n")

    t0 = timeit.default_timer()

    main(
        date_str=opts.date,
        init_str=opts.time,
        timestep=opts.timestep,
        last_hour=opts.last_hour,
        variables=opts.variables,
        run_dir=run_folder,
        domain_coords=domain_coords,
        fmt=opts.format,
        keep_grib2=opts.keep_grib2,
        engine=opts.engine,
    )

    mins, secs = divmod(timeit.default_timer() - t0, 60)
    print(f"\n✓ Done in {int(mins)} min {secs:.1f} s")

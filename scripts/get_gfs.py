#!/usr/bin/env python3
"""
downloading_gfs.py
------------------
Download GFS 0.25° GRIB2 files and convert them to NetCDF, keeping:

  • surface fields
  • mean-sea-level fields
  • height-above-ground fields at 0 m, 2 m and 10 m

All files for one run are stored in <outpath>/<YYYYMMDDHH>/.

Example
-------
python -m scripts.get_gfs --start_date 20250805 --time 06 --engine pygrib
python -m scripts.get_gfs --start_date 20250805 
"""
from __future__ import annotations
import re
import argparse
import sys
import timeit
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from config import config               # project-specific settings

# ========================================================================= #
# CLI                                                                       #
# ========================================================================= #
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Download GFS grids and convert to NetCDF keeping "
            "surface, meanSea and heightAboveGround (0/2/10 m) fields."
        )
    )
    p.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s), 
                        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD or YYYY-MM-DD format.")
    p.add_argument("--run_hour", default=config.GFS_run_time,
                   choices=["00", "06", "12", "18"],
                   help='Run initialisation ("00", "06", "12", "18")')
    p.add_argument("--timestep", type=int, default=config.GFS_timestep,
                   help="Forecast-hour step (h)")
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
    p.add_argument("--engine", choices=["cfgrib", "pygrib"], default="pygrib",
                   help="Backend to read GRIB2 files")
    p.add_argument("--force-redownload", action="store_true",
                   help="Force re-download even if files exist")
    return p.parse_args()

# ========================================================================= #
# Helpers                                                                   #
# ========================================================================= #
def make_run_folder(root: str | Path, date: str, init: str) -> Path:
    run_dir = Path(root).expanduser().resolve() / f"{date}_{init}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def build_url(date: str, init: str, fhour: str, vars_string: str,
              lon_left: float, lon_right: float,
              lat_top: float, lat_bottom: float) -> str:
    base = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    file_param = f"gfs.t{init}z.pgrb2.0p25.{fhour}"
    return (f"{base}?file={file_param}&{vars_string}"
            f"&subregion=&leftlon={lon_left}&rightlon={lon_right}"
            f"&toplat={lat_top}&bottomlat={lat_bottom}"
            f"&dir=%2Fgfs.{date}%2F{init}%2Fatmos")

# ========================================================================= #
# File integrity check                                                      #
# ========================================================================= #

def is_valid_grib2(file_path: Path, min_kb: int = 100) -> bool:
    """Check if a GRIB2 file exists and is not corrupt."""
    if not file_path.exists():
        return False
    
    try:
        # Check file size
        if file_path.stat().st_size < min_kb * 1024:
            return False
        
        # Try to open with pygrib to validate
        import pygrib
        with pygrib.open(str(file_path)) as grbs:
            # Read at least one message to verify file integrity
            grbs.seek(0)
            count = grbs.messages
            if count == 0:
                return False
            # Try to read first message
            grb = grbs[1]
            # Check if we can read values
            _ = grb.values
            return True
    except Exception as e:
        return False


def is_valid_netcdf(file_path: Path) -> bool:
    """Check if a NetCDF file exists and is not corrupt."""
    if not file_path.exists():
        return False
    
    try:
        # Try to open with xarray
        import xarray as xr
        with xr.open_dataset(file_path) as ds:
            # Check basic structure
            if len(ds.data_vars) == 0:
                return False
            # Check for required coordinates (lat/lon or similar)
            if not any(coord in ds.coords for coord in ['latitude', 'lat', 'y']):
                return False
            if not any(coord in ds.coords for coord in ['longitude', 'lon', 'x']):
                return False
            # Try to read a small amount of data
            first_var = list(ds.data_vars.keys())[0]
            _ = ds[first_var].isel({ds[first_var].dims[0]: 0}).values
            return True
    except Exception as e:
        return False


def download_file(url: str, dest: Path, min_kb: int = 100, force: bool = False) -> bool:
    """Download file with validation check. Returns True if downloaded successfully."""
    # Check if we should skip download
    if dest.exists() and not force:
        if is_valid_grib2(dest, min_kb):
            print(f"✔ {dest.name} exists and is valid ({dest.stat().st_size/1024:.0f} KB) – skipping download")
            return True
        else:
            print(f"⚠ {dest.name} exists but appears corrupt – will re-download")
            try:
                dest.unlink()
            except Exception as e:
                print(f"  Failed to remove corrupt file: {e}")
    
    print(f"⇩  Downloading {dest.name} …")
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"   Saved {dest}")
        
        # Verify downloaded file
        if is_valid_grib2(dest, min_kb):
            return True
        else:
            print(f"⚠  Downloaded file {dest.name} appears corrupt")
            dest.unlink()
            return False
    except Exception as e:
        print(f"✗  Failed to download {dest.name}: {e}")
        return False

# ========================================================================= #
# GRIB → NetCDF conversion helpers                                          #
# ========================================================================= #
SURFACE_TYPES = {"surface", "meanSea"}
HAG_TYPE = "heightAboveGround"
HAG_LEVELS = {0, 2, 10}           # metres

# ------------------------- cfgrib backend --------------------------------- #
def convert_with_cfgrib(grib_path: Path, keep_grib: bool, force: bool = False) -> Path:
    import xarray as xr
    import cfgrib
    import warnings

    nc_path = grib_path.with_suffix(".nc")
    
    # Check if we should skip conversion
    if nc_path.exists() and not force:
        if is_valid_netcdf(nc_path):
            print(f"✔ {nc_path.name} already converted and valid – skipping")
            return nc_path
        else:
            print(f"⚠ {nc_path.name} exists but appears corrupt – will re-convert")
            try:
                nc_path.unlink()
            except Exception as e:
                print(f"  Failed to remove corrupt file: {e}")

    idx = cfgrib.open_fileindex(str(grib_path))
    wanted_msgs = [
        m for m in idx if (
            (m["typeOfLevel"] in SURFACE_TYPES) or
            (m["typeOfLevel"] == HAG_TYPE and m["level"] in HAG_LEVELS)
        )
    ]
    idx.close()

    if not wanted_msgs:
        raise RuntimeError("No desired messages found in file")

    datasets = []
    for msg in wanted_msgs:
        keys = {"typeOfLevel": msg["typeOfLevel"]}
        if msg["typeOfLevel"] == HAG_TYPE:
            keys["level"] = msg["level"]

        try:
            ds = xr.open_dataset(
                grib_path,
                engine="cfgrib",
                backend_kwargs={"filter_by_keys": keys},
            )
            datasets.append(ds)
        except Exception as exc:
            warnings.warn(f"Skipped subset {keys}: {exc}")

    if not datasets:
        raise RuntimeError("cfgrib could not open any desired subset")

    xr.merge(datasets, compat="override").to_netcdf(nc_path)
    print(f"   NetCDF saved: {nc_path}")

    if not keep_grib:
        grib_path.unlink()
    return nc_path

# ------------------------- pygrib backend --------------------------------- #
def convert_with_pygrib(grib_path: Path, keep_grib: bool, force: bool = False) -> Path:
    import pygrib
    import numpy as np
    import xarray as xr

    nc_path = grib_path.with_suffix(".nc")
    
    # Check if we should skip conversion
    if nc_path.exists() and not force:
        if is_valid_netcdf(nc_path):
            print(f"✔ {nc_path.name} already converted and valid – skipping")
            return nc_path
        else:
            print(f"⚠ {nc_path.name} exists but appears corrupt – will re-convert")
            try:
                nc_path.unlink()
            except Exception as e:
                print(f"  Failed to remove corrupt file: {e}")

    print(f"⚙  pygrib: {grib_path.name} → NetCDF")

    ds_vars = {}
    with pygrib.open(str(grib_path)) as grbs:
        store: dict[str, dict[int, pygrib.message]] = defaultdict(dict)

        for g in grbs:
            if g.typeOfLevel in SURFACE_TYPES:
                store[g.shortName][0] = g
            elif g.typeOfLevel == HAG_TYPE and g.level in HAG_LEVELS:
                store[g.shortName][g.level] = g
            # ignore everything else

        if not store:
            raise RuntimeError("No desired messages found")

        for short, msgs_by_level in store.items():
            levels = sorted(msgs_by_level)
            msgs = [msgs_by_level[l] for l in levels]
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
            else:
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


def convert_to_netcdf(grib_path: Path, keep_grib: bool, engine: str, force: bool = False) -> Path:
    if engine == "pygrib":
        return convert_with_pygrib(grib_path, keep_grib, force)
    return convert_with_cfgrib(grib_path, keep_grib, force)

# ========================================================================= #
# Main logic                                                                #
# ========================================================================= #
def main(*,
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
         force_redownload: bool = False) -> None:

    lon_left, lon_right = domain_coords["lon_min"], domain_coords["lon_max"]
    lat_top, lat_bottom = domain_coords["lat_max"], domain_coords["lat_min"]

    var_params = "&".join(f"var_{v}=on" for v in variables)

    # Track download/processing status
    downloaded_files = []
    converted_files = []
    
    # --------------------------------------------------------------------- #
    # 0-h forecast (f000) **replaces** the legacy analysis (*.anl) file
    # --------------------------------------------------------------------- #
    for fh in range(0, last_hour + timestep, timestep):
        fh_str = f"f{fh:03d}"
        forecast_date = (datetime.strptime(date_str + init_str, "%Y%m%d%H")
                         + timedelta(hours=fh)).strftime("%Y%m%d%H")
        
        # Determine target file path based on format
        if fmt == "netcdf":
            target_path = run_dir / f"gfs_{forecast_date}.nc"
            # Check if NetCDF file already exists and is valid
            if target_path.exists() and not force_redownload:
                if is_valid_netcdf(target_path):
                    print(f"✔ NetCDF file {target_path.name} exists and is valid – skipping")
                    continue
                else:
                    print(f"⚠ NetCDF file {target_path.name} exists but appears corrupt – will re-process")
                    try:
                        target_path.unlink()
                    except Exception as e:
                        print(f"  Failed to remove corrupt file: {e}")
        
        grib_path = run_dir / f"gfs_{forecast_date}.grb2"
        nc_path = run_dir / f"gfs_{forecast_date}.nc"
        
        # Build URL
        grib_url = build_url(date_str, init_str, fh_str, var_params,
                            lon_left, lon_right, lat_top, lat_bottom)
        
        # Download GRIB2 file if needed
        download_needed = True
        if grib_path.exists() and not force_redownload:
            if is_valid_grib2(grib_path):
                print(f"✔ GRIB2 file {grib_path.name} exists and is valid")
                download_needed = False
        
        if download_needed:
            if download_file(grib_url, grib_path, force=force_redownload):
                downloaded_files.append(grib_path)
            else:
                continue  # Skip processing if download failed
        
        # Convert to NetCDF if requested
        if fmt == "netcdf":
            try:
                convert_to_netcdf(grib_path, keep_grib2, engine, force=force_redownload)
                converted_files.append(nc_path)
            except Exception as exc:
                print(f"⚠  {grib_path.name}: conversion failed ({exc})")

    # Print summary
    print(f"\n=== SUMMARY ======================================================")
    print(f"Downloaded GRIB2 files: {len(downloaded_files)}")
    if fmt == "netcdf":
        print(f"Converted NetCDF files: {len(converted_files)}")
    print("====================================================================\n")

# ========================================================================= #
# Entrypoint                                                                #
# ========================================================================= #
if __name__ == "__main__":
    opts = parse_cli()

    # domain checks
    try:
        domain_coords = config.domains[opts.domain]
    except KeyError:
        print(f"Domain “{opts.domain}” not found; choose from {list(config.domains)}")
        sys.exit(1)

    run_folder = make_run_folder(opts.outpath, opts.start_date, opts.run_hour)

    print("\n=== PARAMETERS =====================================================")
    for k, v in vars(opts).items():
        print(f"{k:12s}: {v}")
    print(f"run_folder : {run_folder}")
    print("====================================================================\n")

    t0 = timeit.default_timer()

    main(
        date_str=opts.start_date,
        init_str=opts.run_hour,
        timestep=opts.timestep,
        last_hour=opts.last_hour,
        variables=opts.variables,
        run_dir=run_folder,
        domain_coords=domain_coords,
        fmt=opts.format,
        keep_grib2=opts.keep_grib2,
        engine=opts.engine,
        force_redownload=opts.force_redownload,
    )

    mins, secs = divmod(timeit.default_timer() - t0, 60)
    print(f"\n✓ Done in {int(mins)} min {secs:.1f} s")
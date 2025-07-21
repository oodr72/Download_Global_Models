#!/usr/bin/env python3
"""
downloading_gfs.py
------------------

Download GFS analysis + forecast grids from NOMADS.

Examples
--------
# Default (GRIB2)           →   <outpath>/<YYYYMMDDHH>/gfs_*.grb2
python downloading_gfs.py --date 20250717 --time 00

# Convert to NetCDF         →   <outpath>/<YYYYMMDDHH>/gfs_*.nc
python downloading_gfs.py --date 20250717 --time 06 --format netcdf
"""
from __future__ import annotations

import argparse
import os
import sys
import timeit
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from config import config  # <-- your existing config/config.py

# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download (and optionally convert) GFS grids")
    p.add_argument("--date",   default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                   help='Initial date in "yyyymmdd"')
    p.add_argument("--time",   default=config.GFS_run_time,
                   choices=["00", "06", "12", "18"],
                   help='Run initialisation ("00", "06", "12", "18")')
    p.add_argument("--timestep", type=int, default=config.GFS_timestep,
                   help="Forecast hour step (h)")
    p.add_argument("--last_hour", type=int, default=int(config.GFS_last_hour),
                   help="Last forecast hour to fetch (inclusive)")
    p.add_argument("--variables", nargs="+", default=config.GFS_variables,
                   help="List of variables, e.g. TMP UGRD VGRD …")
    p.add_argument("--outpath", default=config.GFS_output_directory,
                   help="Root output folder")
    p.add_argument("--domain", default=config.GFS_domain,
                   help="Key name of the domain in config.domains")
    p.add_argument("--format", choices=["grib2", "netcdf"], default="grib2",
                   help="Store files as GRIB2 (raw) or NetCDF")
    p.add_argument("--keep-grib2", action="store_true",
                   help="When --format netcdf, keep the original GRIB2 file")
    return p.parse_args()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def make_run_folder(root: str | Path, date: str, init: str) -> Path:
    run_dir = Path(root).expanduser().resolve() / f"{date}{init}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def build_url(date: str, init: str, fhour: str, vars_string: str,
              lon_left: float, lon_right: float, lat_top: float, lat_bottom: float) -> str:
    base = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    file_param = f"gfs.t{init}z.pgrb2.0p25.{fhour}"
    return (
        f"{base}?file={file_param}"
        f"&{vars_string}"
        f"&subregion=&leftlon={lon_left}&rightlon={lon_right}"
        f"&toplat={lat_top}&bottomlat={lat_bottom}"
        f"&dir=%2Fgfs.{date}%2F{init}%2Fatmos"
    )


def download_file(url: str, dest: Path, min_kb: int = 100) -> None:
    """Download *url* → *dest* if the file doesn't already exist (or is tiny)."""
    if dest.is_file() and dest.stat().st_size / 1024 > min_kb:
        print(f"✔ {dest.name} already present ({dest.stat().st_size/1024:.0f} KB) – skipping")
        return

    print(f"⇩  Downloading {dest.name} …")
    r = requests.get(url, timeout=60)
    if r.status_code == 200:
        dest.write_bytes(r.content)
        print(f"   Saved {dest}")
    else:
        raise RuntimeError(f"HTTP {r.status_code} while fetching {dest.name}")


def convert_to_netcdf(grib_path: Path, keep_grib: bool) -> Path:
    """Convert GRIB2 → NetCDF using xarray+cfgrib."""
    import xarray as xr  # local import so users of grib2-only don't need xarray

    nc_path = grib_path.with_suffix(".nc")
    if nc_path.is_file() and nc_path.stat().st_size > 0:
        print(f"✔ {nc_path.name} already converted – skipping")
        return nc_path

    print(f"⚙  Converting {grib_path.name} → NetCDF …")
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    ds.to_netcdf(nc_path)
    ds.close()
    print(f"   NetCDF saved: {nc_path}")

    if not keep_grib:
        grib_path.unlink()
        print(f"   Removed original GRIB2")

    return nc_path


# --------------------------------------------------------------------------- #
# Main logic                                                                  #
# --------------------------------------------------------------------------- #
def main(
    date_str: str,
    init_str: str,
    timestep: int,
    last_hour: int,
    variables: Iterable[str],
    run_dir: Path,
    domain_coords: dict[str, float],
    fmt: str = "grib2",
    keep_grib2: bool = False,
) -> None:
    lon_left  = domain_coords["lon_min"]
    lon_right = domain_coords["lon_max"]
    lat_top   = domain_coords["lat_max"]
    lat_bottom= domain_coords["lat_min"]

    var_params = "&".join(f"var_{v}=on" for v in variables)

    # ----------------- analysis (anl) --------------------------------------- #
    anl_url = build_url(date_str, init_str, "anl", var_params,
                        lon_left, lon_right, lat_top, lat_bottom)
    anl_name = f"gfs_{date_str}{init_str}.grb2"
    anl_path = run_dir / anl_name
    download_file(anl_url, anl_path)

    # ----------------- forecasts ------------------------------------------- #
    for fh in range(timestep, last_hour + timestep, timestep):
        fh_str = f"f{fh:03d}"
        forecast_date = (datetime.strptime(date_str + init_str, "%Y%m%d%H")
                         + timedelta(hours=fh)).strftime("%Y%m%d%H")
        fcst_name = f"gfs_{forecast_date}.grb2"
        fcst_path = run_dir / fcst_name

        fcst_url = build_url(date_str, init_str, fh_str, var_params,
                             lon_left, lon_right, lat_top, lat_bottom)
        download_file(fcst_url, fcst_path)

    # ----------------- optional conversion --------------------------------- #
    if fmt == "netcdf":
        print("\n=== Converting downloaded GRIB2 files to NetCDF ===")
        for grib in run_dir.glob("*.grb2"):
            try:
                convert_to_netcdf(grib, keep_grib2)
            except Exception as exc:
                print(f"⚠  {grib.name}: conversion failed ({exc})")


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    opts = parse_cli()

    # --- get domain --------------------------------------------------------- #
    try:
        domain_coords = config.domains[opts.domain]
    except KeyError:
        print(f"Domain “{opts.domain}” not found in config.domains.\n"
              f"Available: {list(config.domains)}")
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
    )

    mins, secs = divmod(timeit.default_timer() - t0, 60)
    print(f"\n✓ Done in {int(mins)} min {secs:.1f} s")

#!/usr/bin/env python3
# coding: utf-8
"""
Single-time-step downloader for CMEMS GLORYS
File name: glorys024_YYYYMMDDHH.nc
python -m scripts.get_glorys --start_date --end_date --timestep_hours
"""

from pathlib import Path
import sys
import copernicusmarine
from src.files_functions import get_copernicus_key
from datetime import datetime, timedelta, timezone
import os
from config import config
import argparse
import timeit


def parse_cli():
    p = argparse.ArgumentParser(description="Download GLORYS – one file per instant")
    p.add_argument("--start_date", type=str,
                   default=config.GLORYS_start_date,
                   help="Initial date YYYYMMDDHH")
    p.add_argument("--end_date", type=str,
                   default=config.GLORYS_end_date,
                   help="Final date YYYYMMDDHH")
    p.add_argument("--timestep_hours", type=int,
                   default=config.GLORYS_timestep_hours,
                   help="Time-step between files (h)")
    p.add_argument("--domain", type=str,
                   default=config.GLORYS_domain,
                   help="Domain name from config")
    p.add_argument("--variables", nargs='+',
                   default=config.GLORYS_variables,
                   help="List of variables to download")
    p.add_argument("--outpath", type=str,
                   default=config.GLORYS_output_directory,
                   help="Output directory")
    return p.parse_args()


def download_one_step(date: datetime, coords: dict, variables: list,
                      outpath: Path, disable_progress_bar=True):
    """Download a single hourly GLORYS step."""
    minsize = 100  # KB
    outpath.mkdir(parents=True, exist_ok=True)

    fname = f"glorys024_{date.strftime('%Y%m%d%H')}.nc"
    fpath = outpath / fname

    if fpath.exists() and fpath.stat().st_size / 1024 >= minsize:
        print(f"Already exists: {fname}")
        return

    print(f"Downloading: {fname}")
    copernicusmarine.subset(
        dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        dataset_version="202406",
        variables=variables,
        minimum_longitude=coords["lon_min"],
        maximum_longitude=coords["lon_max"],
        minimum_latitude=coords["lat_min"],
        maximum_latitude=coords["lat_max"],
        minimum_depth=config.GLORYS_minimum_depth,
        maximum_depth=config.GLORYS_maximum_depth,
        start_datetime=date.isoformat(timespec="seconds"),
        #end_datetime=(date + timedelta(hours=1)).isoformat(timespec="seconds"),
        end_datetime=date.isoformat(timespec="seconds"),
        coordinates_selection_method="strict-inside",
        disable_progress_bar=disable_progress_bar,
        output_directory=str(outpath),
        output_filename=fname
    )


if __name__ == "__main__":
    args = parse_cli()

    # --- credentials ------------------------------------------------
    cred = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    if not cred.exists():
        user, pwd, _ = get_copernicus_key()
        copernicusmarine.login(username=user, password=pwd)
        print("Logged in to Copernicus")
    else:
        print("Using existing credentials")

    # --- date loop --------------------------------------------------
    start = datetime.strptime(args.start_date, "%Y%m%d%H")
    end   = datetime.strptime(args.end_date,   "%Y%m%d%H")
    step  = timedelta(hours=args.timestep_hours)

    try:
        coords = config.domains[args.domain]
    except KeyError:
        print(f"Domain '{args.domain}' not found in config")
        sys.exit(1)

    out_dir = Path(args.outpath)
    t0 = timeit.default_timer()

    current = start
    while current <= end:
        download_one_step(current, coords, args.variables, out_dir)
        current += step

    elapsed = timeit.default_timer() - t0
    mins, secs = divmod(elapsed, 60)
    print(f"Finished in {int(mins)}m {secs:.2f}s")
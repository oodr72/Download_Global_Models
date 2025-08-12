#!/usr/bin/env python3
# coding: utf-8
"""
Single-time-step downloader for CMEMS FMWAM
File name: fmwam_YYYY-MM-DD-HH.nc

python -m script.get_mfwave --start_date --end_date --timestep_hours
"""

from pathlib import Path
import sys
import copernicusmarine
from src.files_functions import get_copernicus_key
from datetime import datetime, timedelta, timezone
import os
from config import config
import argparse

# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def parse_cli():
    parser = argparse.ArgumentParser(description="Download FMWAM – one file per time-step")
    parser.add_argument("--start_date", type=str,
                        default=config.FMWAM_start_date,
                        help="Initial date YYYYMMDDHH")
    parser.add_argument("--end_date", type=str,
                        default=config.FMWAM_end_date,
                        help="Final date YYYYMMDDHH")
    parser.add_argument("--timestep_hours", type=int,
                        default=config.FMWAM_timestep_hours,
                        help="Time-step between files (h)")
    parser.add_argument("--domain", type=str,
                        default=config.FMWAM_domain,
                        help="Name of the domain")
    parser.add_argument("--variables", type=str,
                        default=config.FMWAM_variables,
                        help="List of variables to be saved")
    parser.add_argument("--outpath", type=str,
                        default=config.FMWAM_output_directory,
                        help="Folder where downloaded files will be saved")
    return parser.parse_args()

# ------------------------------------------------------------------
# Download helper
# ------------------------------------------------------------------
def download_one_step(date: datetime, coords: dict, variables: list,
                      outpath: Path, disable_progress_bar=True):
    """Download a single 3-hourly FMWAM step."""
    minsize = 100  # KB
    outpath.mkdir(parents=True, exist_ok=True)

    file_name = f"fmwam_{date.strftime('%Y-%m-%d-%H')}.nc"
    file_path = outpath / file_name

    if file_path.exists() and file_path.stat().st_size / 1024 >= minsize:
        print(f"Already exists: {file_name}")
        return

    print(f"Downloading: {file_name}")
    copernicusmarine.subset(
        dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
        dataset_version="202411",
        variables=variables,
        minimum_longitude=coords["lon_min"],
        maximum_longitude=coords["lon_max"],
        minimum_latitude=coords["lat_min"],
        maximum_latitude=coords["lat_max"],
        start_datetime=date.isoformat(timespec="seconds"),
        end_datetime=(date + timedelta(hours=3)).isoformat(timespec="seconds"),
        coordinates_selection_method="strict-inside",
        disable_progress_bar=disable_progress_bar,
        output_directory=str(outpath),
        output_filename=file_name
    )

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    args = parse_cli()

    # Credentials --------------------------------------------------
    cred_file = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    if not cred_file.exists():
        user, pwd, _ = get_copernicus_key()
        copernicusmarine.login(username=user, password=pwd)
        print("Logged in to Copernicus")
    else:
        print("Using existing credentials")

    # Parse dates --------------------------------------------------
    start = datetime.strptime(args.start_date, "%Y%m%d%H")
    end   = datetime.strptime(args.end_date,   "%Y%m%d%H")
    step  = timedelta(hours=args.timestep_hours)

    # Domain -------------------------------------------------------
    try:
        coords = config.domains[args.domain]
    except KeyError:
        print(f"Domain '{args.domain}' not in config.domains")
        sys.exit(1)

    # Loop over requested times ------------------------------------
    out_dir = Path(args.outpath)
    current = start
    while current <= end:
        download_one_step(current, coords, args.variables, out_dir)
        current += step

    print("Done.")
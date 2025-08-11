#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes MFWave data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
    python3 -m scripts.get_mfwave
"""

from pathlib import Path
import sys
import copernicusmarine
from src.files_functions import get_copernicus_key
from datetime import datetime, timedelta, timezone
import os 
from config import config
import argparse


def args():
    parser = argparse.ArgumentParser(description='Download MFWave files')
    parser.add_argument('--start_date', type=str, default=datetime.now(timezone.utc).strftime('%Y%m%d')
    , help='Initial date in "yyyymmdd" format')
    parser.add_argument('--days_number', type=int, default=config.FMWAM_days_number, help='Timestep in hours')
    parser.add_argument('--domain', type=str, default=config.FMWAM_domain, help='Name of the domain')
    parser.add_argument('--variables', type=str, default=config.FMWAM_variables, help='List of variables to be saved')
    parser.add_argument('--outpath', type=str, default=config.FMWAM_output_directory, help='Folder where downloaded files will be saved')
    return parser.parse_args()


def download_fmwam(start_date, end_date, coordinates, variables, output_filename, outpath, disable_progress_bar=True):

    minsize = 100 # Minimum file size in KB for a valid file
    print(f"Downloading files from {start_date} to {end_date}")

    outpath = os.path.join(outpath, start_date)
    full_path = os.path.join(outpath, output_filename)

    if not os.path.exists(outpath):
        print(f"'{outpath}' does not exist. Creating folder...")
        os.makedirs(outpath)

    # variables = ["VHM0_WW", "VHM0_SW1", "VMDR_WW", "VMDR_SW1", "VTM01_WW", "VTM01_SW1"]

    if not os.path.exists(f"{outpath}/{output_filename}") or os.stat(f"{outpath}/{output_filename}").st_size/1024 < minsize:
        print(f"Downloading {output_filename}")
        copernicusmarine.subset(
            dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
            dataset_version="202411",
            variables=variables,
            minimum_longitude=coordinates["lon_min"],
            maximum_longitude=coordinates["lon_max"],
            minimum_latitude=coordinates["lat_min"],
            maximum_latitude=coordinates["lat_max"],
            start_datetime=f"{start_date}T00:00:00",
            end_datetime=f"{end_date}T23:59:00",
            coordinates_selection_method="strict-inside",
            disable_progress_bar=disable_progress_bar,
            output_directory=outpath,
            output_filename=output_filename
        )

        print(f"File {output_filename} downloaded to {outpath}")
    else:
        print(f"File {output_filename} already exists in {outpath}")


if __name__ == '__main__':
    args = args()
    for key, value in args.__dict__.items():
        print(f"{key}: {value}")

    # Get the base URL and token from the environment variables
    credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"

    if not credentials_path.exists():
        user, key, _ = get_copernicus_key()
        copernicusmarine.login(username=user, password=key)
        print("Copernicus Marine credentials set")
    else:
        # Use existing credentials without re-authenticating
        print("Using existing Copernicus Marine credentials")

    # Range dates
    end_date = (datetime.strptime(args.start_date, "%Y%m%d") + timedelta(days=args.days_number)).strftime("%Y-%m-%d")
    print(f"Range dates: {args.start_date} to {end_date}")

    # Oout file name
    output_filename = f"fmwam_wave_{args.start_date}.nc"

    # Get domain
    domain = args.domain

    try:
        coordinates = config.domains[domain]
    except KeyError:
        print(f"Domain '{domain}' not found in config file")
        print("Available domains: ", list(config.domains.keys()))
        sys.exit(1)

    print(f"Domain: '{domain}', coordinates:", coordinates)

    # Timeit start
    import timeit
    start_time = timeit.default_timer()

    # Download GFS files
    download_fmwam(
        start_date=args.start_date, 
        end_date=end_date, 
        coordinates=coordinates,
        variables=args.variables,
        output_filename=output_filename,
        outpath=args.outpath
        )
        
    print("Done")

    # Timeit end
    end_time = timeit.default_timer()
    minutes, seconds = divmod(end_time - start_time, 60)
    print(f"Execution time: {int(minutes)} minutes {seconds:.2f} seconds")


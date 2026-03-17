#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes GLORYS data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
    python3 -m scripts.get_glorys
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


def parse_arguments():
    parser = argparse.ArgumentParser(description='Download CMEMS physical oceanography files')
    parser.add_argument('--start_date', type=str, default=datetime.now(timezone.utc).strftime('%Y%m%d'),
                        help='Start date in "YYYY-MM-DD" format')
    parser.add_argument('--days_number', type=int, default=config.GLORYS_days_number, 
                        help='Number of days to download')
    parser.add_argument('--domain', type=str, default=config.GLORYS_domain, 
                        help='Domain name from config')
    parser.add_argument('--variables', nargs='+', default=config.GLORYS_variables,
                        help='List of variables to download')
    parser.add_argument('--outpath', type=str, default=config.GLORYS_output_directory,
                        help='Output directory for downloaded files')
    return parser.parse_args()

def download_cmems(start_date, end_date, coordinates, variables, output_filename, outpath, 
                   disable_progress_bar=True):
    
    minsize = 100  # Minimum file size in KB for valid download
    outpath = os.path.join(outpath, start_date)
    full_path = os.path.join(outpath, output_filename)


    print(f"Downloading files from {start_date} to {end_date}")
    
    # Create output directory if missing
    if not os.path.exists(outpath):
        print(f"Creating output directory: {outpath}")
        os.makedirs(outpath)
    
    # Check if file exists and meets size requirements
    if not os.path.exists(full_path) or os.path.getsize(full_path)/1024 < minsize:
        print(f"Downloading {output_filename}...")
        
        copernicusmarine.subset(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            dataset_version="202406",
            variables=variables,
            minimum_longitude=coordinates["lon_min"],
            maximum_longitude=coordinates["lon_max"],
            minimum_latitude=coordinates["lat_min"],
            maximum_latitude=coordinates["lat_max"],
            minimum_depth=config.GLORYS_minimum_depth,
            maximum_depth=config.GLORYS_maximum_depth,
            start_datetime=f"{start_date}T00:00:00",
            end_datetime=f"{end_date}T23:00:00",
            coordinates_selection_method="strict-inside",
            disable_progress_bar=disable_progress_bar,
            output_directory=outpath,
            output_filename=output_filename
        )
        print(f"File saved to: {full_path}")
    else:
        print(f"Skipping download - file exists: {full_path}")

if __name__ == '__main__':
    args = parse_arguments()
    
    # Print arguments for verification
    print("Execution parameters:")
    for key, value in vars(args).items():
        print(f"{key}: {value}")

    # Configure Copernicus Marine credentials
    credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    
    if not credentials_path.exists():
        user, key, _ = get_copernicus_key()
        copernicusmarine.login(username=user, password=key)
        print("Copernicus Marine credentials configured")
    else:
        print("Using existing Copernicus Marine credentials")

    # Calculate end date
    end_date = (datetime.strptime(args.start_date, "%Y%m%d") + 
                timedelta(days=args.days_number)).strftime("%Y%m%d")
    print(f"Date range: {args.start_date} to {end_date}")

    # Configure output filename
    output_filename = f"glorys024_uv_{args.start_date}.nc"

    # Get domain coordinates
    try:
        domain_coords = config.domains[args.domain]
    except KeyError:
        print(f"Error: Domain '{args.domain}' not found in configuration")
        print("Available domains:", list(config.domains.keys()))
        sys.exit(1)

    print(f"Using domain '{args.domain}': {domain_coords}")

    # Execute download with timing
    start_time = timeit.default_timer()
    
    download_cmems(
        start_date=args.start_date,
        end_date=end_date,
        coordinates=domain_coords,
        variables=args.variables,
        output_filename=output_filename,
        outpath=args.outpath
    )
    
    # Calculate and display execution time
    elapsed = timeit.default_timer() - start_time
    minutes, seconds = divmod(elapsed, 60)
    print(f"Download completed in {int(minutes)}m {seconds:.2f}s")
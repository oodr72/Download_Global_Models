#!/usr/bin/env python3
# coding: utf-8

import os
import requests
import xarray as xr
from datetime import datetime, timedelta, timezone
from config import config
import argparse
import timeit
import sys
import logging
from pathlib import Path

def parse_arguments():
    parser = argparse.ArgumentParser(description='Download HYCOM ocean forecast data')
    parser.add_argument('--start_date', type=str, default=datetime.now(timezone.utc).strftime('%Y%m%d'),
                        help='Forecast base date in "YYYYMMDD" format')
    parser.add_argument('--days_number', type=int, default=config.HYCOM_days_number,
                        help='Number of forecast days to download (max 8)')
    parser.add_argument('--domain', type=str, default=config.HYCOM_domain,
                        help='Domain name from config')
    parser.add_argument('--outpath', type=str, default=config.HYCOM_output_directory,
                        help='Output directory for processed files')
    parser.add_argument('--time_step', type=int, default=config.HYCOM_time_step,
                        help='Time step between forecast files in hours')
    return parser.parse_args()

def process_and_save_subset(file_path, output_folder, coordinates, log_path):
    try:
        ds = xr.open_dataset(file_path)
        
        # Extract coordinates
        lon_min = coordinates["lon_min"]
        lon_max = coordinates["lon_max"]
        lat_min = coordinates["lat_min"]
        lat_max = coordinates["lat_max"]
        
        # Normalize longitude to 0-360 range
        lat = ds["Latitude"].values
        lon = ds["Longitude"].values % 360
        lon_min_mod = lon_min % 360
        lon_max_mod = lon_max % 360
        
        # Create spatial mask
        if lon_min_mod < lon_max_mod:
            mask = (
                (lat >= lat_min) & (lat <= lat_max) &
                (lon >= lon_min_mod) & (lon <= lon_max_mod)
            )
        else:
            mask = (
                (lat >= lat_min) & (lat <= lat_max) &
                ((lon >= lon_min_mod) | (lon <= lon_max_mod))
            )

        if not mask.any():
            message = f"⚠️ No data found within region for {os.path.basename(file_path)}"
            logging.warning(message)
            return False

        # Get subset indices
        iy, ix = mask.nonzero()
        y0, y1 = iy.min(), iy.max()
        x0, x1 = ix.min(), ix.max()
        
        # Create subset dataset
        ds_subset = ds.isel(Y=slice(y0, y1 + 1), X=slice(x0, x1 + 1))
        ds.close()

        # Create output filename
        base_name = os.path.basename(file_path)
        output_path = os.path.join(output_folder, f"subset_{base_name}")

        # Save subset with compression
        compression = {var: {"zlib": True, "complevel": 4} for var in ds_subset.data_vars}
        ds_subset.to_netcdf(output_path, format="NETCDF4_CLASSIC", encoding=compression)

        # Log success
        dims_y = ds_subset.sizes["Y"]
        dims_x = ds_subset.sizes["X"]
        lat_min_actual = ds_subset["Latitude"].min().item()
        lat_max_actual = ds_subset["Latitude"].max().item()
        lon_min_actual = ds_subset["Longitude"].min().item()
        lon_max_actual = ds_subset["Longitude"].max().item()

        message = (
            f"✅ {base_name} processed\n"
            f"   Dimensions: Y={dims_y}, X={dims_x}\n"
            f"   Latitude: {lat_min_actual:.2f} → {lat_max_actual:.2f}\n"
            f"   Longitude: {lon_min_actual:.2f} → {lon_max_actual:.2f}"
        )
        logging.info(message)
        
        return True

    except Exception as e:
        error_msg = f"❌ Error processing {file_path}: {str(e)}"
        logging.error(error_msg)
        return False

def download_hycom_forecast(start_date, days_number, time_step, coordinates, outpath):
    # Base URL for HYCOM/RTOFS forecasts
    base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod/"
    
    # Calculate maximum forecast hours (max 192 hours/8 days)
    max_fh = min(192, days_number * 24)
    
    # Create directories
    raw_folder = os.path.join(outpath, "raw_downloads")
    processed_folder = os.path.join(outpath, start_date)
    log_path = os.path.join(outpath, "hycom_download.log")
    
    os.makedirs(raw_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Log start of process
    start_msg = (
        f"🌊 Starting HYCOM forecast download\n"
        f"   Base date: {start_date}\n"
        f"   Forecast days: {days_number} (max FH: {max_fh})\n"
        f"   Time step: {time_step} hours\n"
        f"   Domain: {coordinates}"
    )
    print(start_msg)
    logging.info(start_msg)
    
    # Convert start_date to datetime
    date_dt = datetime.strptime(start_date, "%Y%m%d")
    remote_folder = f"rtofs.{start_date}/"
    
    # Process each forecast hour
    for fh in range(0, max_fh + 1, time_step):
        # Generate filenames
        remote_filename = f"rtofs_glo_2ds_f{fh:03d}_prog.nc"
        url = f"{base_url}{remote_folder}{remote_filename}"
        
        valid_dt = date_dt + timedelta(hours=fh)
        local_filename = f"hycom_{valid_dt.strftime('%Y%m%d%H')}.nc"
        raw_path = os.path.join(raw_folder, local_filename)
        processed_path = os.path.join(processed_folder, f"subset_{local_filename}")
        
        # Skip if processed file already exists
        if os.path.exists(processed_path):
            msg = f"⏩ Skipping existing file: {processed_path}"
            print(msg)
            logging.info(msg)
            continue
            
        # Download file
        print(f"\n→ Downloading forecast hour {fh:03d}...")
        try:
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                with open(raw_path, 'wb') as f:
                    f.write(response.content)
                msg = f"   ✅ Download completed: {local_filename}"
                print(msg)
                logging.info(msg)
            else:
                msg = f"   ⚠️ Server error ({response.status_code}) for {url}"
                print(msg)
                logging.warning(msg)
                continue
        except Exception as e:
            msg = f"   ❌ Download failed: {str(e)}"
            print(msg)
            logging.error(msg)
            continue
            
        # Process and subset the file
        print(f"   Processing {local_filename}...")
        if process_and_save_subset(raw_path, processed_folder, coordinates, log_path):
            # Clean up raw file after successful processing
            try:
                os.remove(raw_path)
                logging.info("   🧹 Original file deleted")
            except Exception as e:
                msg = f"   ⚠️ Could not delete raw file: {str(e)}"
                print(msg)
                logging.warning(msg)
    
    return log_path

if __name__ == "__main__":
    args = parse_arguments()
    
    # Print arguments for verification
    print("Execution parameters:")
    for key, value in vars(args).items():
        print(f"{key}: {value}")
    
    # Start timer
    start_time = timeit.default_timer()
    
    # Get domain coordinates
    try:
        domain_coords = config.domains[args.domain]
    except KeyError:
        print(f"Error: Domain '{args.domain}' not found in configuration")
        print("Available domains:", list(config.domains.keys()))
        sys.exit(1)
    
    # Download and process HYCOM forecast
    log_file = download_hycom_forecast(
        start_date=args.start_date,
        days_number=args.days_number,
        time_step=args.time_step,
        coordinates=domain_coords,
        outpath=args.outpath
    )
    
    # Calculate and display execution time
    end_time = timeit.default_timer()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)
    
    time_msg = f"Total execution time: {int(minutes)} minutes {seconds:.2f} seconds"
    print(f"\n{time_msg}")
    logging.info(time_msg)
    
    print(f"\nProcess completed. See log for details: {log_file}")
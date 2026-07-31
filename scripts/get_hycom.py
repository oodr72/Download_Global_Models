#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes HYCOM ocean forecast data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
    python3 -m scripts.get_hycom
"""
import os
import re
import requests
import xarray as xr
from datetime import datetime, timedelta, timezone
from config import config
import argparse
import timeit
import sys
import logging
from pathlib import Path
import numpy as np
from netCDF4 import Dataset as ncdf4Dataset


def parse_arguments():
    parser = argparse.ArgumentParser(description='Download HYCOM ocean forecast data')
    parser.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s), 
                        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD or YYYY-MM-DD format.")
    parser.add_argument('--days_number', type=int, default=config.HYCOM_days_number,
                        help='Number of forecast days to download (max 8)')
    parser.add_argument('--domain', type=str, default=config.HYCOM_domain,
                        help='Domain name from config')
    parser.add_argument('--outpath', type=str, default=config.HYCOM_output_directory,
                        help='Output directory for processed files')
    parser.add_argument('--time_step', type=int, default=config.HYCOM_time_step,
                        help='Time step between forecast files in hours')
    parser.add_argument('--force_redownload', action='store_true',
                        help='Force re-download and reprocessing even if files exist')
    parser.add_argument('--log_level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='Set the logging level')
    return parser.parse_args()

def setup_logging(log_level='INFO', log_file=None):
    """Setup logging configuration"""
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,  # Set to debug to allow both handlers to work
        handlers=handlers
    )

def is_valid_netcdf(file_path, expected_variables=None, min_size_kb=100):
    """
    Check if a NetCDF file exists and is not corrupt.
    
    Args:
        file_path: Path to the NetCDF file
        expected_variables: List of expected variable names (optional)
        min_size_kb: Minimum file size in KB to be considered valid
        
    Returns:
        bool: True if file is valid, False otherwise
    """
    if not os.path.exists(file_path):
        logging.debug(f"File does not exist: {file_path}")
        return False
    
    # Check file size
    file_size_kb = os.path.getsize(file_path) / 1024
    if file_size_kb < min_size_kb:
        logging.warning(f"File too small ({file_size_kb:.1f} KB < {min_size_kb} KB): {file_path}")
        return False
    
    try:
        # Try to open with netCDF4
        with ncdf4Dataset(file_path, 'r') as nc:
            # Check basic structure
            if not hasattr(nc, 'dimensions') or not hasattr(nc, 'variables'):
                logging.debug(f"File lacks basic NetCDF structure: {file_path}")
                return False
            
            # Check for required dimensions (HYCOM uses Y, X, MT, Depth)
            required_dims = ['Y', 'X', 'MT']
            if not all(dim in nc.dimensions for dim in required_dims):
                logging.debug(f"Missing required dimensions in {file_path}: found {list(nc.dimensions.keys())}")
                return False
            
            # Check if file has at least one data variable
            data_vars = [var for var in nc.variables if var not in required_dims + ['Latitude', 'Longitude', 'Depth']]
            if not data_vars:
                logging.debug(f"No data variables found: {file_path}")
                return False
            
            # Check expected variables if provided
            if expected_variables:
                nc_vars = list(nc.variables.keys())
                # HYCOM variables might have different names, check for common ones
                common_vars = ['water_temp', 'salinity', 'water_u', 'water_v']
                found_vars = [var for var in common_vars if var in nc_vars]
                if not found_vars:
                    logging.warning(f"No expected variables found in {file_path}")
                    return False
            
            # Try to read a small sample of data from the first variable
            first_var = data_vars[0]
            var_data = nc.variables[first_var]
            
            # Check variable shape and try to read first element
            if hasattr(var_data, 'shape'):
                try:
                    # For 4D vars (time, depth, lat, lon)
                    if len(var_data.shape) == 4:
                        _ = var_data[0, 0, 0, 0]
                    # For 3D vars (time, lat, lon) - surface variables
                    elif len(var_data.shape) == 3:
                        _ = var_data[0, 0, 0]
                    # For 2D vars (lat, lon)
                    elif len(var_data.shape) == 2:
                        _ = var_data[0, 0]
                except (IndexError, ValueError, TypeError) as e:
                    logging.debug(f"Failed to read data sample from {first_var}: {e}")
                    return False
            
            # Check if coordinates exist
            if 'Latitude' in nc.variables and 'Longitude' in nc.variables:
                try:
                    lat_data = nc.variables['Latitude'][:]
                    lon_data = nc.variables['Longitude'][:]
                    if lat_data.size == 0 or lon_data.size == 0:
                        logging.debug(f"Coordinate data is empty in {file_path}")
                        return False
                except:
                    logging.debug(f"Failed to read coordinate data in {file_path}")
                    return False
            
            logging.debug(f"File validation passed: {file_path}")
            return True
            
    except Exception as e:
        logging.warning(f"NetCDF file appears corrupt ({file_path}): {e}")
        return False

def remove_corrupt_file(file_path):
    """Safely remove a corrupt file"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Removed corrupt file: {file_path}")
            return True
    except Exception as e:
        logging.error(f"Failed to remove corrupt file {file_path}: {e}")
    return False

def process_and_save_subset(file_path, output_folder, coordinates, force_reprocess=False):
    """
    Process and save subset of HYCOM data with integrity check
    
    Args:
        file_path: Path to input file
        output_folder: Output directory
        coordinates: Dictionary with lon_min, lon_max, lat_min, lat_max
        force_reprocess: Force reprocessing even if output exists
        
    Returns:
        bool: True if processing successful, False otherwise
    """
    # Create output filename
    base_name = os.path.basename(file_path)
    output_path = os.path.join(output_folder, f"{base_name}")
    
    # Check if processed file already exists and is valid
    if os.path.exists(output_path) and not force_reprocess:
        if is_valid_netcdf(output_path, min_size_kb=100):
            logging.info(f"Skipping processing - valid processed file exists: {output_path}")
            return True
        else:
            logging.warning(f"Processed file exists but appears corrupt: {output_path}")
            remove_corrupt_file(output_path)
    
    try:
        # Open and process the dataset
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
            message = f"No data found within region for {base_name}"
            logging.warning(message)
            return False

        # Get subset indices
        iy, ix = mask.nonzero()
        y0, y1 = iy.min(), iy.max()
        x0, x1 = ix.min(), ix.max()
        
        # Create subset dataset
        ds_subset = ds.isel(Y=slice(y0, y1 + 1), X=slice(x0, x1 + 1))
        ds.close()

        # Save subset with compression
        compression = {var: {"zlib": True, "complevel": 4} for var in ds_subset.data_vars}
        ds_subset.to_netcdf(output_path, format="NETCDF4_CLASSIC", encoding=compression)

        # Log success with details
        dims_y = ds_subset.sizes["Y"]
        dims_x = ds_subset.sizes["X"]
        lat_min_actual = ds_subset["Latitude"].min().item()
        lat_max_actual = ds_subset["Latitude"].max().item()
        lon_min_actual = ds_subset["Longitude"].min().item()
        lon_max_actual = ds_subset["Longitude"].max().item()

        message = (
            f"Successfully processed {base_name}\n"
            f"  Dimensions: Y={dims_y}, X={dims_x}\n"
            f"  Latitude: {lat_min_actual:.2f} → {lat_max_actual:.2f}\n"
            f"  Longitude: {lon_min_actual:.2f} → {lon_max_actual:.2f}"
        )
        logging.info(message)
        
        # Verify the saved file
        if is_valid_netcdf(output_path, min_size_kb=100):
            return True
        else:
            logging.error(f"Processed file validation failed: {output_path}")
            remove_corrupt_file(output_path)
            return False

    except Exception as e:
        error_msg = f"Error processing {file_path}: {str(e)}"
        logging.error(error_msg)
        return False

def download_file(url, dest_path, min_size_kb=100, force=False):
    """
    Download file with validation check
    
    Args:
        url: URL to download from
        dest_path: Destination file path
        min_size_kb: Minimum file size in KB
        force: Force re-download even if file exists
        
    Returns:
        bool: True if download successful, False otherwise
    """
    # Check if we should skip download
    if os.path.exists(dest_path) and not force:
        if is_valid_netcdf(dest_path, min_size_kb=min_size_kb):
            logging.info(f"Raw file exists and is valid: {os.path.basename(dest_path)}")
            return True
        else:
            logging.warning(f"Raw file exists but appears corrupt: {dest_path}")
            remove_corrupt_file(dest_path)
    
    logging.info(f"Downloading from {url}...")
    try:
        response = requests.get(url, timeout=120)
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                f.write(response.content)
            
            # Verify downloaded file
            if is_valid_netcdf(dest_path, min_size_kb=min_size_kb):
                file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                logging.info(f"Download successful: {os.path.basename(dest_path)} ({file_size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Downloaded file appears corrupt: {dest_path}")
                remove_corrupt_file(dest_path)
                return False
        else:
            logging.error(f"Server error ({response.status_code}) for {url}")
            return False
            
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while downloading {url}")
        return False
    except Exception as e:
        logging.error(f"Download failed: {str(e)}")
        # Clean up partial file if it exists
        if os.path.exists(dest_path):
            remove_corrupt_file(dest_path)
        return False

def download_hycom_forecast(start_date, days_number, time_step, coordinates, outpath, force_redownload=False):
    """Download and process HYCOM forecast data"""
    
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
    
    # Log start of process
    start_msg = (
        f"Starting HYCOM forecast download\n"
        f"  Base date: {start_date}\n"
        f"  Forecast days: {days_number} (max FH: {max_fh})\n"
        f"  Time step: {time_step} hours\n"
        f"  Domain: {coordinates}\n"
        f"  Force re-download: {force_redownload}"
    )
    logging.info(start_msg)
    
    # Convert start_date to datetime
    date_dt = datetime.strptime(start_date, "%Y%m%d")
    remote_folder = f"rtofs.{start_date}/"
    
    # Track statistics
    stats = {
        'total': 0,
        'skipped': 0,
        'downloaded': 0,
        'processed': 0,
        'failed': 0
    }
    
    # Process each forecast hour
    for fh in range(0, max_fh + 1, time_step):
        stats['total'] += 1
        
        # Generate filenames
        remote_filename = f"rtofs_glo_2ds_f{fh:03d}_prog.nc"
        url = f"{base_url}{remote_folder}{remote_filename}"
        
        valid_dt = date_dt + timedelta(hours=fh)
        local_filename = f"hycom_{valid_dt.strftime('%Y%m%d%H')}.nc"
        raw_path = os.path.join(raw_folder, local_filename)
        processed_path = os.path.join(processed_folder, f"{local_filename}")
        
        # Check if processed file already exists and is valid
        if os.path.exists(processed_path) and not force_redownload:
            if is_valid_netcdf(processed_path, min_size_kb=100):
                logging.info(f"Skipping existing processed file: {processed_path}")
                stats['skipped'] += 1
                continue
            else:
                logging.warning(f"Processed file exists but appears corrupt: {processed_path}")
                remove_corrupt_file(processed_path)
        
        # Download file
        logging.info(f"Processing forecast hour {fh:03d}...")
        download_success = download_file(url, raw_path, min_size_kb=100, force=force_redownload)
        
        if not download_success:
            stats['failed'] += 1
            continue
        
        stats['downloaded'] += 1
            
        # Process and subset the file
        logging.info(f"Processing {local_filename}...")
        if process_and_save_subset(raw_path, processed_folder, coordinates, force_redownload):
            stats['processed'] += 1
            
            # Clean up raw file after successful processing
            try:
                os.remove(raw_path)
                logging.debug(f"Original file deleted: {raw_path}")
            except Exception as e:
                logging.warning(f"Could not delete raw file: {str(e)}")
        else:
            stats['failed'] += 1
    
    # Print summary
    summary_msg = (
        f"\nDownload Summary:\n"
        f"  Total forecast hours: {stats['total']}\n"
        f"  Skipped (valid existing): {stats['skipped']}\n"
        f"  Downloaded: {stats['downloaded']}\n"
        f"  Processed: {stats['processed']}\n"
        f"  Failed: {stats['failed']}"
    )
    logging.info(summary_msg)
    
    return log_path

if __name__ == "__main__":
    args = parse_arguments()
    
    # Setup logging
    log_path = os.path.join(args.outpath, "hycom_download.log")
    setup_logging(args.log_level, log_path)
    
    # Print arguments for verification
    logging.info("Execution parameters:")
    for key, value in vars(args).items():
        logging.info(f"  {key}: {value}")
    
    # Start timer
    start_time = timeit.default_timer()
    
    # Get domain coordinates
    try:
        domain_coords = config.domains[args.domain]
        logging.info(f"Using domain '{args.domain}': {domain_coords}")
    except KeyError:
        logging.error(f"Domain '{args.domain}' not found in configuration")
        logging.error("Available domains: %s", list(config.domains.keys()))
        sys.exit(1)
    
    # Download and process HYCOM forecast
    log_file = download_hycom_forecast(
        start_date=args.start_date,
        days_number=args.days_number,
        time_step=args.time_step,
        coordinates=domain_coords,
        outpath=args.outpath,
        force_redownload=args.force_redownload
    )
    
    # Calculate and display execution time
    end_time = timeit.default_timer()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)
    
    time_msg = f"Total execution time: {int(minutes)} minutes {seconds:.2f} seconds"
    logging.info(time_msg)
    
    print(f"\nProcess completed. See log for details: {log_file}")
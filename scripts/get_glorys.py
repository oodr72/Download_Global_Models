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
import re
import sys
import copernicusmarine
from src.files_functions import get_copernicus_key
from datetime import datetime, timedelta, timezone
import os
from config import config
import argparse
import timeit
import logging
from netCDF4 import Dataset as ncdf4Dataset


def parse_arguments():
    parser = argparse.ArgumentParser(description='Download CMEMS physical oceanography files')
    parser.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s), 
                        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD or YYYY-MM-DD format.")
    parser.add_argument('--days_number', type=int, default=config.GLORYS_days_number, 
                        help='Number of days to download')
    parser.add_argument('--domain', type=str, default=config.GLORYS_domain, 
                        help='Domain name from config')
    parser.add_argument('--variables', nargs='+', default=config.GLORYS_variables,
                        help='List of variables to download')
    parser.add_argument('--outpath', type=str, default=config.GLORYS_output_directory,
                        help='Output directory for downloaded files')
    parser.add_argument('--force_redownload', action='store_true',
                        help='Force re-download even if files exist')
    parser.add_argument('--log_level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='Set the logging level')
    return parser.parse_args()

def setup_logging(log_level='INFO'):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
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
            
            # Check for required dimensions
            required_dims = ['time', 'latitude', 'longitude']
            if not all(dim in nc.dimensions for dim in required_dims):
                logging.debug(f"Missing required dimensions: {file_path}")
                return False
            
            # Check if file has at least one data variable
            data_vars = [var for var in nc.variables if var not in required_dims]
            if not data_vars:
                logging.debug(f"No data variables found: {file_path}")
                return False
            
            # Check expected variables if provided
            if expected_variables:
                nc_vars = list(nc.variables.keys())
                missing_vars = [var for var in expected_variables if var not in nc_vars]
                if missing_vars:
                    logging.warning(f"Missing expected variables {missing_vars} in {file_path}")
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
            
            # Check time dimension has valid values
            time_var = nc.variables.get('time')
            if time_var is not None:
                try:
                    time_data = time_var[:]
                    if len(time_data) == 0 or not all(time_data.mask == False):
                        logging.debug(f"Time variable has invalid data in {file_path}")
                        return False
                except:
                    logging.debug(f"Failed to read time variable in {file_path}")
            
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

def download_cmems(start_date, end_date, coordinates, variables, output_filename, outpath, 
                   force_redownload=False, disable_progress_bar=True):
    """
    Download CMEMS data with file integrity checks
    
    Args:
        start_date: Start date in YYYYMMDD format
        end_date: End date in YYYYMMDD format
        coordinates: Dictionary with lon_min, lon_max, lat_min, lat_max
        variables: List of variables to download
        output_filename: Output filename
        outpath: Output directory
        force_redownload: Force re-download even if file exists
        disable_progress_bar: Disable download progress bar
    """
    
    minsize_kb = 100  # Minimum file size in KB for valid download
    outpath = os.path.join(outpath, start_date)
    full_path = os.path.join(outpath, output_filename)
    
    logging.info(f"Download range: {start_date} to {end_date}")
    logging.info(f"Target file: {full_path}")
    
    # Create output directory if missing
    if not os.path.exists(outpath):
        logging.info(f"Creating output directory: {outpath}")
        os.makedirs(outpath, exist_ok=True)
    
    # Check if file exists and is valid
    if os.path.exists(full_path) and not force_redownload:
        if is_valid_netcdf(full_path, expected_variables=variables, min_size_kb=minsize_kb):
            logging.info(f"Skipping download - valid file exists: {full_path}")
            return True
        else:
            logging.warning(f"File exists but appears corrupt: {full_path}")
            if remove_corrupt_file(full_path):
                logging.info("Will re-download corrupt file")
            else:
                logging.error("Failed to remove corrupt file, cannot re-download")
                return False
    
    # Download the file
    logging.info(f"Downloading {output_filename}...")
    
    try:
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
        
        # Verify downloaded file
        if os.path.exists(full_path):
            if is_valid_netcdf(full_path, expected_variables=variables, min_size_kb=minsize_kb):
                file_size_mb = os.path.getsize(full_path) / (1024 * 1024)
                logging.info(f"Download successful: {full_path} ({file_size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Downloaded file appears corrupt: {full_path}")
                remove_corrupt_file(full_path)
                return False
        else:
            logging.error(f"Download failed - file not created: {full_path}")
            return False
            
    except Exception as e:
        logging.error(f"Download failed with error: {e}")
        # Clean up partial file if it exists
        if os.path.exists(full_path):
            remove_corrupt_file(full_path)
        return False

def check_copernicus_credentials():
    """Check and configure Copernicus Marine credentials"""
    credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    
    if not credentials_path.exists():
        logging.info("No Copernicus Marine credentials found, configuring...")
        try:
            user, key, _ = get_copernicus_key()
            copernicusmarine.login(username=user, password=key)
            logging.info("Copernicus Marine credentials configured successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to configure Copernicus Marine credentials: {e}")
            return False
    else:
        logging.debug("Using existing Copernicus Marine credentials")
        return True

if __name__ == '__main__':
    args = parse_arguments()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Print arguments for verification
    logging.info("Execution parameters:")
    for key, value in vars(args).items():
        logging.info(f"  {key}: {value}")

    # Configure Copernicus Marine credentials
    if not check_copernicus_credentials():
        logging.error("Failed to configure Copernicus Marine credentials. Exiting.")
        sys.exit(1)

    # Calculate end date
    start_date_obj = datetime.strptime(args.start_date, "%Y%m%d")
    end_date_obj = start_date_obj + timedelta(days=args.days_number)
    end_date = end_date_obj.strftime("%Y%m%d")
    
    logging.info(f"Date range: {args.start_date} to {end_date}")
    logging.info(f"Total days: {args.days_number}")

    # Configure output filename
    output_filename = f"glorys024_uv_{args.start_date}.nc"
    logging.info(f"Output filename: {output_filename}")

    # Get domain coordinates
    try:
        domain_coords = config.domains[args.domain]
        logging.info(f"Using domain '{args.domain}': {domain_coords}")
    except KeyError:
        logging.error(f"Domain '{args.domain}' not found in configuration")
        logging.error("Available domains: %s", list(config.domains.keys()))
        sys.exit(1)

    # Execute download with timing
    start_time = timeit.default_timer()
    
    success = download_cmems(
        start_date=args.start_date,
        end_date=end_date,
        coordinates=domain_coords,
        variables=args.variables,
        output_filename=output_filename,
        outpath=args.outpath,
        force_redownload=args.force_redownload,
        disable_progress_bar=True  # Disable progress bar for cleaner logging
    )
    
    # Calculate and display execution time
    elapsed = timeit.default_timer() - start_time
    minutes, seconds = divmod(elapsed, 60)
    
    if success:
        logging.info(f"Download completed successfully in {int(minutes)}m {seconds:.2f}s")
    else:
        logging.error(f"Download failed after {int(minutes)}m {seconds:.2f}s")
        sys.exit(1)
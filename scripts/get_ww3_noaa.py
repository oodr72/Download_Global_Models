#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes NOAA WW3 wave forecast data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
python -m scripts.get_ww3_noaa --start_date 20231001 --days_number 3 --domain global --run_hour 00 --time_step 6 --outpath ./ww3_data

Changes 2025-12-03:
* Added file integrity checks
* Skip existing files if not corrupt
* Added force_redownload option
* Enhanced logging and error handling
"""
import os
import re
import requests
import xarray as xr
from datetime import datetime, timedelta, timezone
import argparse
import timeit
import sys
from config import config
import logging
from netCDF4 import Dataset as ncdf4Dataset
import numpy as np

def parse_arguments():
    parser = argparse.ArgumentParser(description='Download and process NOAA WW3 wave forecast data')
    parser.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s), 
                        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD or YYYY-MM-DD format.")
    parser.add_argument('--days_number', type=int, default=config.WW3_days_number,
                        help='Number of forecast days to download (max 16)')
    parser.add_argument('--domain', type=str, default=config.WW3_domain,
                        help='Domain name from configuration')
    parser.add_argument('--run_hour', type=str, default=config.WW3_run_hour,
                        help='Model run hour (00, 06, 12, or 18)')
    parser.add_argument('--time_step', type=int, default=config.WW3_time_step,
                        help='Time step between forecasts in hours')
    parser.add_argument('--outpath', type=str, default=config.WW3_output_directory,
                        help='Output directory for processed files')
    parser.add_argument('--force_redownload', action='store_true',
                        help='Force re-download even if files exist')
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
                # Wave variables are specific, we'll check if any wave-related vars exist
                wave_keywords = ['hs', 'dir', 'tp', 'period', 'wave', 'height']
                has_wave_var = any(keyword in var.lower() for var in nc_vars for keyword in wave_keywords)
                if not has_wave_var:
                    logging.debug(f"No wave-related variables found in {file_path}")
                    return False
            
            # Try to read a small sample of data from the first variable
            first_var = data_vars[0]
            var_data = nc.variables[first_var]
            
            # Check variable shape and try to read first element
            if hasattr(var_data, 'shape'):
                try:
                    # For 3D vars (time, lat, lon) - wave variables
                    if len(var_data.shape) == 3:
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
                    if len(time_data) == 0:
                        logging.debug(f"Time variable has no data in {file_path}")
                        return False
                except:
                    logging.debug(f"Failed to read time variable in {file_path}")
            
            logging.debug(f"File validation passed: {file_path}")
            return True
            
    except Exception as e:
        logging.warning(f"NetCDF file appears corrupt ({file_path}): {e}")
        return False

def is_valid_grib(file_path, min_size_kb=100):
    """
    Check if a GRIB file exists and is not corrupt by attempting to read with cfgrib.
    
    Args:
        file_path: Path to the GRIB file
        min_size_kb: Minimum file size in KB
        
    Returns:
        bool: True if file is valid, False otherwise
    """
    if not os.path.exists(file_path):
        return False
    
    # Check file size
    file_size_kb = os.path.getsize(file_path) / 1024
    if file_size_kb < min_size_kb:
        logging.warning(f"GRIB file too small ({file_size_kb:.1f} KB < {min_size_kb} KB): {file_path}")
        return False
    
    try:
        # Try to open with cfgrib
        ds = xr.open_dataset(file_path, engine="cfgrib")
        # Check basic structure
        if len(ds.data_vars) == 0:
            ds.close()
            return False
        # Try to read metadata
        _ = ds.attrs
        ds.close()
        return True
    except Exception as e:
        logging.debug(f"GRIB file appears corrupt ({file_path}): {e}")
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

def remove_index_files(grib_path):
    """Remove any index files associated with a GRIB file"""
    try:
        base_name = os.path.basename(grib_path).split('.')[0]
        outpath = os.path.dirname(grib_path)
        for file in os.listdir(outpath):
            if file.startswith(base_name) and file.endswith(".idx"):
                index_path = os.path.join(outpath, file)
                os.remove(index_path)
                logging.debug(f"Removed index file: {index_path}")
    except Exception as e:
        logging.debug(f"Error removing index files: {e}")

def download_file(url, params, dest_path, min_size_kb=100, force=False):
    """
    Download file with validation check
    
    Args:
        url: URL to download from
        params: Query parameters
        dest_path: Destination file path
        min_size_kb: Minimum file size in KB
        force: Force re-download even if file exists
        
    Returns:
        bool: True if download successful, False otherwise
    """
    # Check if we should skip download
    if os.path.exists(dest_path) and not force:
        if is_valid_grib(dest_path, min_size_kb=min_size_kb):
            file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            logging.info(f"GRIB file exists and is valid: {os.path.basename(dest_path)} ({file_size_mb:.2f} MB)")
            return True
        else:
            logging.warning(f"GRIB file exists but appears corrupt: {dest_path}")
            remove_corrupt_file(dest_path)
            remove_index_files(dest_path)
    
    logging.info(f"Downloading from {url}...")
    try:
        response = requests.get(url, params=params, timeout=120)
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                f.write(response.content)
            
            # Verify downloaded file
            if is_valid_grib(dest_path, min_size_kb=min_size_kb):
                file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                logging.info(f"Download successful: {os.path.basename(dest_path)} ({file_size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Downloaded file appears corrupt: {dest_path}")
                remove_corrupt_file(dest_path)
                remove_index_files(dest_path)
                return False
        else:
            logging.error(f"Server error ({response.status_code}) for {url}")
            return False
            
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while downloading from {url}")
        return False
    except Exception as e:
        logging.error(f"Download failed: {str(e)}")
        # Clean up partial file if it exists
        if os.path.exists(dest_path):
            remove_corrupt_file(dest_path)
            remove_index_files(dest_path)
        return False

def convert_grib_to_netcdf(grib_path, nc_path, force=False):
    """
    Convert GRIB file to NetCDF format
    
    Args:
        grib_path: Path to GRIB file
        nc_path: Path for output NetCDF file
        force: Force reconversion even if file exists
        
    Returns:
        bool: True if conversion successful, False otherwise
    """
    # Check if NetCDF file already exists and is valid
    if os.path.exists(nc_path) and not force:
        if is_valid_netcdf(nc_path, min_size_kb=100):
            file_size_mb = os.path.getsize(nc_path) / (1024 * 1024)
            logging.info(f"NetCDF file exists and is valid: {os.path.basename(nc_path)} ({file_size_mb:.2f} MB)")
            return True
        else:
            logging.warning(f"NetCDF file exists but appears corrupt: {nc_path}")
            remove_corrupt_file(nc_path)
    
    logging.info(f"Converting to NetCDF: {os.path.basename(nc_path)}")
    try:
        # Check if cfgrib engine is available
        if 'cfgrib' not in xr.backends.list_engines():
            raise ImportError("cfgrib engine not available. Install with: pip install cfgrib eccodes")
        
        # Use cfgrib engine to open the GRIB file
        ds = xr.open_dataset(grib_path, engine="cfgrib")
        compression = {var: {"zlib": True, "complevel": 4} for var in ds.data_vars}
        ds.to_netcdf(nc_path, format="NETCDF4_CLASSIC", encoding=compression)
        ds.close()
        
        # Verify the converted file
        if is_valid_netcdf(nc_path, min_size_kb=100):
            file_size_mb = os.path.getsize(nc_path) / (1024 * 1024)
            logging.info(f"NetCDF saved successfully: {nc_path} ({file_size_mb:.2f} MB)")
            return True
        else:
            logging.error(f"Converted NetCDF file appears corrupt: {nc_path}")
            remove_corrupt_file(nc_path)
            return False
            
    except ImportError as e:
        logging.error(f"Conversion failed - missing dependency: {str(e)}")
        logging.error("Install required packages with: pip install cfgrib eccodes")
        return False
    except Exception as e:
        logging.error(f"Conversion failed: {str(e)}")
        return False

def download_and_convert_ww3(target_date, run_hour, time_step, coordinates, outpath, force_redownload=False):
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_wave_0p25.pl"
    max_forecast_hours = min(384, config.WW3_days_number * 24)  # Max 16 days
    forecast_hours = list(range(0, max_forecast_hours + 1, time_step))
    
    # Create output directory
    outpath = os.path.join(outpath, f"{target_date}_{run_hour}")
    os.makedirs(outpath, exist_ok=True)

    # Setup logging
    log_path = os.path.join(outpath, "ww3_download.log")
    setup_logging('INFO', log_path)
    
    # Extract domain coordinates
    lon_min = coordinates["lon_min"]
    lon_max = coordinates["lon_max"]
    lat_min = coordinates["lat_min"]
    lat_max = coordinates["lat_max"]
    
    # Log start information
    start_msg = (
        f"Starting WW3 forecast download\n"
        f"  Date: {target_date} Run: {run_hour}z\n"
        f"  Forecast range: 0-{max_forecast_hours} hours\n"
        f"  Time step: {time_step} hours\n"
        f"  Domain: Lon [{lon_min}, {lon_max}] Lat [{lat_min}, {lat_max}]\n"
        f"  Force re-download: {force_redownload}"
    )
    logging.info(start_msg)
    
    # Convert target_date to datetime
    dt = datetime.strptime(target_date, "%Y%m%d")
    remote_dir = f"/gefs.{target_date}/{run_hour}/wave/gridded"
    
    # Track statistics
    stats = {
        'total': 0,
        'skipped': 0,
        'downloaded': 0,
        'converted': 0,
        'failed': 0
    }
    
    # Process each forecast hour
    for fh in forecast_hours:
        stats['total'] += 1
        f_str = f"{fh:03d}"
        remote_filename = f"gefs.wave.t{run_hour}z.mean.global.0p25.f{f_str}.grib2"
        valid_dt = dt + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")
        
        grib_name = f"ww3_{valid_str}.grib2"
        nc_name = f"ww3_{valid_str}.nc"
        grib_path = os.path.join(outpath, grib_name)
        nc_path = os.path.join(outpath, nc_name)
        
        logging.info(f"=== Processing FH {fh:03d} → valid {valid_str} ===")
        
        # Check if NetCDF file already exists and is valid
        if os.path.exists(nc_path) and not force_redownload:
            if is_valid_netcdf(nc_path, min_size_kb=100):
                file_size_mb = os.path.getsize(nc_path) / (1024 * 1024)
                logging.info(f"NetCDF file exists and is valid: {nc_name} ({file_size_mb:.2f} MB) – skipping")
                stats['skipped'] += 1
                continue
            else:
                logging.warning(f"NetCDF file exists but appears corrupt: {nc_path}")
                remove_corrupt_file(nc_path)
        
        # Set download parameters
        params = {
            "file": remote_filename,
            "all_var": "on",
            "all_lev": "on",
            "subregion": "",
            "toplat": lat_max,
            "leftlon": lon_min,
            "rightlon": lon_max,
            "bottomlat": lat_min,
            "dir": remote_dir
        }
        
        # Download GRIB file
        download_success = download_file(base_url, params, grib_path, 
                                        min_size_kb=100, force=force_redownload)
        
        if not download_success:
            stats['failed'] += 1
            continue
        
        stats['downloaded'] += 1
            
        # Convert to NetCDF
        conversion_success = convert_grib_to_netcdf(grib_path, nc_path, force_redownload)
        
        if conversion_success:
            stats['converted'] += 1
            
            # Clean up GRIB files after successful conversion
            try:
                remove_corrupt_file(grib_path)
                remove_index_files(grib_path)
                logging.debug("Removed GRIB file and index files")
            except Exception as e:
                logging.warning(f"Cleanup failed: {str(e)}")
        else:
            stats['failed'] += 1
    
    # Print summary
    summary_msg = (
        f"\nDownload Summary:\n"
        f"  Total forecast hours: {stats['total']}\n"
        f"  Skipped (valid existing): {stats['skipped']}\n"
        f"  Downloaded: {stats['downloaded']}\n"
        f"  Converted: {stats['converted']}\n"
        f"  Failed: {stats['failed']}"
    )
    logging.info(summary_msg)
    
    return log_path

if __name__ == "__main__":
    args = parse_arguments()
    
    # Setup console logging initially
    setup_logging(args.log_level)
    
    # Print execution parameters
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
    
    # Download and process WW3 data
    log_file = download_and_convert_ww3(
        target_date=args.start_date,
        run_hour=args.run_hour,
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
#!/usr/bin/env python3
# coding: utf-8
"""
Single-time-step downloader for CMEMS GLORYS
File name: glorys024_YYYYMMDDHH.nc
python -m scripts.get_glorys --start_date --end_date --timestep_hours

Changes 2025-12-03:
* Added file integrity checks
* Skip existing files if not corrupt
* Added force_redownload option
* Enhanced logging and error handling
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
import logging
from netCDF4 import Dataset as ncdf4Dataset
import re


def parse_cli():
    p = argparse.ArgumentParser(description="Download GLORYS – one file per instant")
    p.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s),
                   default=datetime.now(timezone.utc).strftime("%Y%m%d%H"),
                   help="Initial date YYYYMMDDHH or YYYY-MM-DD-HH format")
    p.add_argument("--end_date", type=lambda s: re.sub(r'[^\d]', '', s),
                   default=(datetime.now(timezone.utc)+timedelta(days=1)).strftime("%Y%m%d%H"),
                   help="Final date YYYYMMDDHH or YYYY-MM-DD-HH format")
    p.add_argument('--days_number', type=int, default=config.GLORYS_days_number, 
                   help='Number of days to download')
    p.add_argument("--timestep_hours", type=int,
                   default=config.GLORYS_time_step,
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
    p.add_argument("--force_redownload", action='store_true',
                   help="Force re-download even if files exist")
    p.add_argument("--log_level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                   default='INFO', help="Set the logging level")
    p.add_argument("--disable_progress_bar", action='store_true',
                   help="Disable download progress bar")
    return p.parse_args()


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
            data_vars = [var for var in nc.variables if var not in required_dims + ['depth', 'Depth']]
            if not data_vars:
                logging.debug(f"No data variables found: {file_path}")
                return False
            
            # Check expected variables if provided
            if expected_variables:
                nc_vars = list(nc.variables.keys())
                missing_vars = [var for var in expected_variables if var not in nc_vars]
                if missing_vars:
                    # Check if at least some expected variables are present
                    found_vars = [var for var in expected_variables if var in nc_vars]
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


def check_copernicus_credentials():
    """Check and configure Copernicus Marine credentials"""
    credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    
    if not credentials_path.exists():
        logging.info("No Copernicus Marine credentials found, configuring...")
        try:
            user, pwd, _ = get_copernicus_key()
            copernicusmarine.login(username=user, password=pwd)
            logging.info("Copernicus Marine credentials configured successfully")
            return True
        except Exception as e:
            logging.error(f"Failed to configure Copernicus Marine credentials: {e}")
            return False
    else:
        logging.debug("Using existing Copernicus Marine credentials")
        return True


def download_one_step(date: datetime, coords: dict, variables: list,
                      outpath: Path, force_redownload: bool = False,
                      disable_progress_bar: bool = True):
    """Download a single hourly GLORYS step."""
    minsize_kb = 100  # KB
    outpath.mkdir(parents=True, exist_ok=True)

    fname = f"glorys024_{date.strftime('%Y%m%d%H')}.nc"
    fpath = outpath / fname
    
    logging.info(f"Processing: {fname}")

    # Check if file already exists and is valid
    if fpath.exists() and not force_redownload:
        if is_valid_netcdf(fpath, expected_variables=variables, min_size_kb=minsize_kb):
            file_size_mb = fpath.stat().st_size / (1024 * 1024)
            logging.info(f"File exists and is valid: {fname} ({file_size_mb:.2f} MB) - skipping")
            return True
        else:
            logging.warning(f"File exists but appears corrupt: {fpath}")
            remove_corrupt_file(fpath)

    logging.info(f"Downloading: {fname}")
    try:
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
            end_datetime=date.isoformat(timespec="seconds"),
            coordinates_selection_method="strict-inside",
            disable_progress_bar=disable_progress_bar,
            output_directory=str(outpath),
            output_filename=fname
        )
        
        # Verify downloaded file
        if fpath.exists():
            if is_valid_netcdf(fpath, expected_variables=variables, min_size_kb=minsize_kb):
                file_size_mb = fpath.stat().st_size / (1024 * 1024)
                logging.info(f"Download successful: {fname} ({file_size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Downloaded file appears corrupt: {fpath}")
                remove_corrupt_file(fpath)
                return False
        else:
            logging.error(f"Download failed - file not created: {fpath}")
            return False
            
    except Exception as e:
        logging.error(f"Download failed with error: {e}")
        # Clean up partial file if it exists
        if fpath.exists():
            remove_corrupt_file(fpath)
        return False


def main():
    args = parse_cli()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Print arguments for verification
    logging.info("Execution parameters:")
    for key, value in vars(args).items():
        logging.info(f"  {key}: {value}")
    
    # --- credentials ------------------------------------------------
    if not check_copernicus_credentials():
        logging.error("Failed to configure Copernicus Marine credentials. Exiting.")
        sys.exit(1)
    
    # --- date loop --------------------------------------------------
    if args.days_number is not None:
        args.end_date = (datetime.strptime(args.start_date, "%Y%m%d%H") + 
                         timedelta(days=args.days_number)).strftime("%Y%m%d%H")
    
    if args.start_date > args.end_date:
        logging.error("Start date must be before end date")
        sys.exit(1)
    start = datetime.strptime(args.start_date, "%Y%m%d%H")
    end   = datetime.strptime(args.end_date, "%Y%m%d%H")
    step  = timedelta(hours=args.timestep_hours)

    try:
        coords = config.domains[args.domain]
        logging.info(f"Using domain '{args.domain}': {coords}")
    except KeyError:
        logging.error(f"Domain '{args.domain}' not found in config")
        logging.error("Available domains: %s", list(config.domains.keys()))
        sys.exit(1)
    
    # Calculate total steps for progress tracking
    total_steps = ((end - start) // step) + 1
    logging.info(f"Processing {total_steps} time steps from {start} to {end}")
    
    out_dir = Path(args.outpath)
    
    # Track statistics
    stats = {
        'total': 0,
        'skipped': 0,
        'downloaded': 0,
        'failed': 0
    }
    
    t0 = timeit.default_timer()

    current = start
    while current <= end:
        stats['total'] += 1
        logging.info(f"=== Processing time step {current.strftime('%Y%m%d%H')} ({stats['total']}/{total_steps}) ===")
        
        success = download_one_step(
            current, 
            coords, 
            args.variables, 
            out_dir,
            force_redownload=args.force_redownload,
            disable_progress_bar=args.disable_progress_bar
        )
        
        if success:
            # Check if it was a skip or a successful download
            fname = f"glorys024_{current.strftime('%Y%m%d%H')}.nc"
            fpath = out_dir / fname
            if fpath.exists() and not args.force_redownload:
                # File existed and was valid
                stats['skipped'] += 1
            else:
                # File was downloaded
                stats['downloaded'] += 1
        else:
            stats['failed'] += 1
        
        current += step

    elapsed = timeit.default_timer() - t0
    mins, secs = divmod(elapsed, 60)
    
    # Print summary
    summary_msg = (
        f"\nDownload Summary:\n"
        f"  Total time steps: {stats['total']}\n"
        f"  Skipped (valid existing): {stats['skipped']}\n"
        f"  Downloaded: {stats['downloaded']}\n"
        f"  Failed: {stats['failed']}\n"
        f"  Execution time: {int(mins)}m {secs:.2f}s"
    )
    logging.info(summary_msg)
    
    if stats['failed'] > 0:
        logging.warning(f"Some downloads failed. Check the logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
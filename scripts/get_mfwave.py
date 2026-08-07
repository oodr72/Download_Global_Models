#!/usr/bin/env python3
# coding: utf-8
"""
Single-time-step downloader for CMEMS FMWAM
File name: fmwam_YYYY-MM-DD-HH.nc

python -m scripts.get_mfwave --start_date --end_date --timestep_hours

Changes 2025-12-03:
* Added file integrity checks
* Skip existing files if not corrupt
* Added force_redownload option
* Enhanced logging and error handling
* Fixed variable handling (now accepts list)
"""

from pathlib import Path
import re
import sys
import copernicusmarine
from src.files_functions import get_copernicus_key
from datetime import datetime, timedelta, timezone
import logging
import os
from config import config
import argparse
import timeit
from netCDF4 import Dataset as ncdf4Dataset


def parse_cli():
    parser = argparse.ArgumentParser(description="Download FMWAM – one file per time-step")
    parser.add_argument("--start_date", type=lambda s: re.sub(r'[^\d]', '', s), 
                        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                        help="Initial forecast date in YYYYMMDD or YYYY-MM-DD format.")
    parser.add_argument("--end_date", type=str,
                        default=None,
                        help="Final date YYYYMMDDHH")
    parser.add_argument('--last_hour', type=int, default=getattr(config, 'FMWAM_last_hour', 24), 
                   help='Number of hours to download')
    parser.add_argument("--timestep_hours", type=int,
                        default=getattr(config, 'FMWAM_timestep_hours', 3),
                        help="Time-step between files (h)")
    parser.add_argument("--domain", type=str,
                        default=getattr(config, 'FMWAM_domain', 'global'),
                        help="Name of the domain")
    parser.add_argument("--variables", nargs='+',
                        default=getattr(config, 'FMWAM_variables', ['VHM0_WW', 'VHM0_SW1', 'VMDR_WW', 'VMDR_SW1', 'VTM01_WW', 'VTM01_SW1']),
                        help="List of variables to be saved")
    parser.add_argument("--outpath", type=str,
                        default=getattr(config, 'FMWAM_output_directory', 'data/fmwam'),
                        help="Folder where downloaded files will be saved")
    parser.add_argument("--force_redownload", action='store_true',
                        help="Force re-download even if files exist")
    parser.add_argument("--log_level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help="Set the logging level")
    parser.add_argument("--disable_progress_bar", action='store_true',
                        help="Disable download progress bar")
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
            
            # Check for required dimensions (FMWAM uses time, latitude, longitude)
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
    """Download a single (6)-hourly FMWAM step."""
    minsize_kb = 100  # KB
    outpath.mkdir(parents=True, exist_ok=True)

    file_name = f"fmwam_{date.strftime('%Y%m%d%H')}.nc"
    file_path = outpath / file_name
    
    logging.info(f"Processing: {file_name}")

    # Check if file already exists and is valid
    if file_path.exists() and not force_redownload:
        if is_valid_netcdf(file_path, expected_variables=variables, min_size_kb=minsize_kb):
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            logging.info(f"File exists and is valid: {file_name} ({file_size_mb:.2f} MB) - skipping")
            return True
        else:
            logging.warning(f"File exists but appears corrupt: {file_path}")
            remove_corrupt_file(file_path)

    logging.info(f"Downloading: {file_name}")
    try:
        # Ensure variables is a list (for backward compatibility)
        if isinstance(variables, str):
            variables = [variables]
        
        copernicusmarine.subset(
            dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
            dataset_version="202411",
            variables=variables,
            minimum_longitude=coords["lon_min"],
            maximum_longitude=coords["lon_max"],
            minimum_latitude=coords["lat_min"],
            maximum_latitude=coords["lat_max"],
            start_datetime=date.isoformat(timespec="seconds"),
            end_datetime=date.isoformat(timespec="seconds"),
            coordinates_selection_method="strict-inside",
            disable_progress_bar=disable_progress_bar,
            output_directory=str(outpath),
            output_filename=file_name
        )
        
        # Verify downloaded file
        if file_path.exists():
            if is_valid_netcdf(file_path, expected_variables=variables, min_size_kb=minsize_kb):
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                logging.info(f"Download successful: {file_name} ({file_size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Downloaded file appears corrupt: {file_path}")
                remove_corrupt_file(file_path)
                return False
        else:
            logging.error(f"Download failed - file not created: {file_path}")
            return False
            
    except Exception as e:
        logging.error(f"Download failed with error: {e}")
        # Clean up partial file if it exists
        if file_path.exists():
            remove_corrupt_file(file_path)
        return False


def main():
    args = parse_cli()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Print arguments for verification
    logging.info("Execution parameters:")
    for key, value in vars(args).items():
        logging.info(f"  {key}: {value}")
    
    # Credentials --------------------------------------------------
    if not check_copernicus_credentials():
        logging.error("Failed to configure Copernicus Marine credentials. Exiting.")
        sys.exit(1)
    
    # Parse dates --------------------------------------------------
    try:
        start = datetime.strptime(args.start_date, "%Y%m%d%H")
    except ValueError:
        try:
            # Try without hour
            start = datetime.strptime(args.start_date, "%Y%m%d")
            # Set to 00Z
            start = datetime(start.year, start.month, start.day, 0, 0, 0)
            logging.info(f"Using start time 00Z: {start}")
        except ValueError as e:
            logging.error(f"Invalid start_date format: {args.start_date}. Use YYYYMMDD or YYYYMMDDHH")
            sys.exit(1)
    
    if args.end_date is None:
        if args.last_hour is None:
            logging.error("No end_date or last_hour provided")
            sys.exit(1)
        end = start + timedelta(hours=args.last_hour)
        logging.info(f"No end_date provided, setting end_date to {end.strftime('%Y%m%d%H')} based on last_hour: {args.last_hour}")
    else:
        try:
            end = datetime.strptime(args.end_date, "%Y%m%d%H")
        except ValueError:
            try:
                # Try without hour
                end = datetime.strptime(args.end_date, "%Y%m%d")
                # Set to 00Z
                end = datetime(end.year, end.month, end.day, 0, 0, 0)
                logging.info(f"Using end time 00Z: {end}")
            except ValueError as e:
                logging.error(f"Invalid end_date format: {args.end_date}. Use YYYYMMDD or YYYYMMDDHH")
                sys.exit(1)
        logging.info(f"Using end_date: {end.strftime('%Y%m%d%H')}")
    
    if start > end:
        logging.error("Start date must be before end date")
        sys.exit(1)
    
    step = timedelta(hours=args.timestep_hours)
    logging.info(f"Time step: {args.timestep_hours} hours")

    # Domain -------------------------------------------------------
    try:
        coords = config.domains[args.domain]
        logging.info(f"Using domain '{args.domain}': {coords}")
    except KeyError:
        logging.error(f"Domain '{args.domain}' not in config.domains")
        logging.error("Available domains: %s", list(config.domains.keys()))
        sys.exit(1)

    # Calculate total steps for progress tracking
    total_steps = ((end - start) // step) + 1
    logging.info(f"Processing {total_steps} time steps from {start} to {end}")
    
    # Loop over requested times ------------------------------------
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
            file_name = f"fmwam_{current.strftime('%Y%m%d%H')}.nc"
            file_path = out_dir / file_name
            if file_path.exists() and not args.force_redownload:
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
    
    logging.info("Done.")


if __name__ == "__main__":
    main()
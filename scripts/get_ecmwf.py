#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes ECMWF forecast data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
    python3 -m scripts.get_ecmwf
    python3 -m scripts.get_ecmwf --start_date 20250802
    python3 -m scripts.get_ecmwf --start_date 20231001 --days_number 3 --domain global --run_hour 00 --time_step 6 --outpath ./ecmwf_data --engine pygrib --variables 2t,10u,msl
"""
import os
import requests
import xarray as xr
import glob
from datetime import datetime, timedelta, timezone
import argparse
import timeit
import sys
from config import config
import logging
import warnings
import numpy as np
import pygrib
from netCDF4 import Dataset as ncdf4Dataset
import re
from urllib.parse import urlparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Download and process ECMWF forecast data')
    parser.add_argument('--start_date', type=str, default=datetime.now(timezone.utc).strftime('%Y%m%d'),
                        help='Initial date in YYYYMMDD format')
    parser.add_argument('--days_number', type=int, default=config.ECMWF_days_number,
                        help='Number of forecast days to download (max 10)')
    parser.add_argument('--domain', type=str, default=config.ECMWF_domain,
                        help='Domain name from configuration')
    parser.add_argument('--run_hour', type=str, default=config.ECMWF_run_hour,
                        help='Model run hour (00, 06, 12, or 18)')
    parser.add_argument('--time_step', type=int, default=config.ECMWF_time_step,
                        help='Time step between forecasts in hours')
    parser.add_argument('--outpath', type=str, default=config.ECMWF_output_directory,
                        help='Output directory for processed files')
    parser.add_argument('--engine', type=str, default='cfgrib',
                        choices=['cfgrib', 'pygrib'],
                        help='Engine to use for GRIB to NetCDF conversion')
    parser.add_argument('--variables', type=str, default=config.ECMWF_variables,
                        help='Comma-separated list of variables to download (e.g., "2t,10u,msl")')
    return parser.parse_args()

def generate_ecmwf_urls(date, hour, max_forecast_hour, step, variables=None):
    """Generate ECMWF forecast URLs with proper formatting and variable filtering"""
    base_url = "https://data.ecmwf.int/forecasts"
    urls = []
    
    # Create parameter filter if variables are specified
    param_filter = ""
    if variables:
        # Convert to ECMWF parameter IDs
        param_filter = f"?param={variables.replace(',', '/')}"
    
    for fh in range(0, max_forecast_hour + 1, step):
        forecast_str = f"{fh}h" if fh != 0 else "0h"
        filename = f"{date}{hour}0000-{forecast_str}-oper-fc.grib2"
        url = f"{base_url}/{date}/{hour}z/ifs/0p25/oper/{filename}{param_filter}"
        urls.append(url)
    return urls

def remove_idx_files(grib_path: str) -> None:
    """Remove any .idx files associated with a GRIB file"""
    for idx_file in glob.glob(grib_path + ".*.idx"):
        try:
            os.remove(idx_file)
            print(f"   🧹 Removed index file: {os.path.basename(idx_file)}")
        except Exception as e:
            print(f"   ⚠️ Could not remove index file {os.path.basename(idx_file)}: {str(e)}")

def process_with_pygrib(grib_file, nc_file, coordinates, forecast_time, requested_vars=None):
    """Process GRIB file using pygrib engine for 2D variables only with correct orientation"""
    # Extract coordinates
    lon_min = coordinates["lon_min"]
    lon_max = coordinates["lon_max"]
    lat_min = coordinates["lat_min"]
    lat_max = coordinates["lat_max"]
    
    # Open GRIB file
    grbs = pygrib.open(grib_file)
    
    # Get first message to extract grid info
    first_msg = grbs[1]
    lats, lons = first_msg.latlons()
    
    # Create domain mask
    lon_min_mod = lon_min % 360
    lon_max_mod = lon_max % 360
    
    if lon_min_mod <= lon_max_mod:
        mask = (
            (lats >= lat_min) & 
            (lats <= lat_max) &
            (lons >= lon_min_mod) & 
            (lons <= lon_max_mod)
        )
    else:
        mask = (
            (lats >= lat_min) & 
            (lats <= lat_max) &
            ((lons >= lon_min_mod) | 
             (lons <= lon_max_mod))
        )
    
    # Create NetCDF file
    with ncdf4Dataset(nc_file, 'w', format='NETCDF4') as nc:
        # Create dimensions
        time_dim = nc.createDimension('time', None)
        lat_dim = nc.createDimension('latitude', np.sum(mask.any(axis=1)))
        lon_dim = nc.createDimension('longitude', np.sum(mask.any(axis=0)))
        
        # Create variables
        times = nc.createVariable('time', 'f8', ('time',))
        latitudes = nc.createVariable('latitude', 'f4', ('latitude',))
        longitudes = nc.createVariable('longitude', 'f4', ('longitude',))
        
        # Get unique latitudes and sort them in ascending order (south to north)
        unique_lats = np.unique(lats[mask])
        sorted_lats = np.sort(unique_lats)
        
        # Get unique longitudes and sort them in ascending order (west to east)
        unique_lons = np.unique(lons[mask])
        sorted_lons = np.sort(unique_lons)
        
        # Write coordinate data
        latitudes[:] = sorted_lats
        longitudes[:] = sorted_lons
        
        # Write time coordinate (forecast time in hours)
        times[:] = [forecast_time]
        times.units = f"hours since {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Track variable names to prevent duplicates
        var_names = set()
        processed_messages = 0
        
        # Create a set of requested short names for faster lookup
        requested_short_names = set(requested_vars.split(',')) if requested_vars else None
        
        # Process all messages but filter for 2D variables
        for grb in grbs:
            # Filter for surface and single-level parameters
            if grb.typeOfLevel not in ['surface', 'meanSea', 'heightAboveGround', 
                                      'depthBelowLand', 'atmosphereSingleLayer']:
                continue
                
            # Filter by requested variables if specified
            if requested_short_names and grb.shortName not in requested_short_names:
                continue
                
            # Extract data and metadata
            data = grb.values
            base_name = grb.name.replace(' ', '_').lower()
            units = grb.units
            
            # Handle duplicate names
            if base_name in var_names:
                # Add level information to make name unique
                level_info = f"_{grb.typeOfLevel}_{grb.level}"
                name = base_name + level_info.replace(' ', '_').lower()
            else:
                name = base_name
            
            # Ensure name is still unique
            original_name = name
            counter = 1
            while name in var_names:
                name = f"{original_name}_{counter}"
                counter += 1
            
            var_names.add(name)
            
            # Create empty array for reordered data
            reordered_data = np.full((len(sorted_lats), len(sorted_lons)), np.nan)
            
            # Build mapping between grid points and array indices
            for i in range(lats.shape[0]):
                for j in range(lats.shape[1]):
                    if mask[i, j]:
                        # Find position in sorted arrays
                        lat_idx = np.where(sorted_lats == lats[i, j])[0][0]
                        lon_idx = np.where(sorted_lons == lons[i, j])[0][0]
                        reordered_data[lat_idx, lon_idx] = data[i, j]
            
            # Create variable in NetCDF
            var = nc.createVariable(
                name, 'f4', ('time', 'latitude', 'longitude'),
                zlib=True, complevel=4
            )
            var.units = units
            var[0, :, :] = reordered_data  # South to north, west to east
            processed_messages += 1
        
        if processed_messages == 0:
            raise ValueError("No requested 2D variables found in GRIB file")
    
    return len(sorted_lons), len(sorted_lats)

def process_ecmwf_grib(file_path, output_path, coordinates, engine='cfgrib', forecast_time=0, variables=None):
    """Process ECMWF GRIB file: subset to domain and convert to NetCDF"""
    try:
        if engine == 'cfgrib':
            # Open GRIB file with cfgrib
            ds = xr.open_dataset(file_path, engine="cfgrib")
            
            # Filter variables if requested
            if variables:
                # Create a set of requested short names
                requested_short_names = set(variables.split(','))
                
                # Filter dataset variables
                vars_to_keep = []
                for var in ds.data_vars:
                    # Get short name from attributes
                    short_name = ds[var].attrs.get('GRIB_shortName', '')
                    if short_name in requested_short_names:
                        vars_to_keep.append(var)
                
                if not vars_to_keep:
                    raise ValueError(f"No requested variables found in GRIB file: {variables}")
                
                ds = ds[vars_to_keep]
            
            # Extract coordinates
            lon_min = coordinates["lon_min"]
            lon_max = coordinates["lon_max"]
            lat_min = coordinates["lat_min"]
            lat_max = coordinates["lat_max"]
            
            # Handle longitude range (ECMWF uses 0-360)
            lon = ds.longitude.values
            lon_min_mod = lon_min % 360
            lon_max_mod = lon_max % 360
            
            # Create spatial mask
            if lon_min_mod <= lon_max_mod:
                mask = (
                    (ds.latitude >= lat_min) & 
                    (ds.latitude <= lat_max) &
                    (ds.longitude >= lon_min_mod) & 
                    (ds.longitude <= lon_max_mod)
                )
            else:
                mask = (
                    (ds.latitude >= lat_min) & 
                    (ds.latitude <= lat_max) &
                    ((ds.longitude >= lon_min_mod) | 
                     (ds.longitude <= lon_max_mod))
                )
            
            # Apply mask and subset
            ds_subset = ds.where(mask, drop=True)
            
            # Save to NetCDF with compression
            compression = {var: {"zlib": True, "complevel": 4} for var in ds_subset.data_vars}
            ds_subset.to_netcdf(output_path, format="NETCDF4_CLASSIC", encoding=compression)
            
            # Return dimensions for logging
            return ds_subset.dims.get('longitude', 0), ds_subset.dims.get('latitude', 0)
        
        elif engine == 'pygrib':
            # Use pygrib for conversion
            return process_with_pygrib(file_path, output_path, coordinates, forecast_time, variables)
    
    except Exception as e:
        logging.error(f"Error processing {file_path}: {str(e)}")
        raise
    finally:
        # Always remove index files after processing
        remove_idx_files(file_path)

def download_and_process_ecmwf(start_date, run_hour, days_number, time_step, coordinates, outpath, engine='cfgrib', variables=None):
    """Download and process ECMWF forecast data"""
    # Calculate max forecast hours (ECMWF max is 240 hours/10 days)
    max_forecast_hour = min(240, days_number * 24)
    
    # Setup directories
    raw_folder = os.path.join(outpath, "raw_downloads")
    processed_folder = os.path.join(outpath,  f"{start_date}_{run_hour}")
    os.makedirs(raw_folder, exist_ok=True)
    os.makedirs(processed_folder, exist_ok=True)
    
    # Setup logging
    log_path = os.path.join(outpath, "ecmwf_download.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Log start information
    start_msg = (
        f"🌊 Starting ECMWF forecast download\n"
        f"   Date: {start_date} Run: {run_hour}z\n"
        f"   Forecast range: 0-{max_forecast_hour} hours\n"
        f"   Time step: {time_step} hours\n"
        f"   Engine: {engine}\n"
        f"   Variables: {variables if variables else 'All'}\n"
        f"   Domain: Lon [{coordinates['lon_min']}, {coordinates['lon_max']}] "
        f"Lat [{coordinates['lat_min']}, {coordinates['lat_max']}]"
    )
    print(start_msg)
    logging.info(start_msg)
    
    # Generate URLs
    urls = generate_ecmwf_urls(start_date, run_hour, max_forecast_hour, time_step, variables)
    
    # Process each forecast file
    for url in urls:
        # Parse URL to extract filename properly
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        
        # Extract forecast hour from filename
        try:
            # Handle different filename patterns
            if "0h-oper-fc.grib2" in filename:
                fh = 0
            else:
                # Extract the forecast hour part
                fh_part = filename.split("-")[1]
                fh = int(fh_part.replace("h", "").replace("oper-fc.grib2", ""))
        except Exception as e:
            print(f"   ⚠️ Could not extract forecast hour from {filename}: {str(e)}")
            logging.error(f"Could not extract forecast hour from {filename}: {str(e)}")
            continue
        
        # Calculate validation time
        valid_dt = datetime.strptime(start_date + run_hour, "%Y%m%d%H") + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")
        
        # Create file paths
        grib_path = os.path.join(raw_folder, filename)
        nc_filename = f"ecmwf_{valid_str}.nc"
        nc_path = os.path.join(processed_folder, nc_filename)
        
        # Skip if processed file exists
        if os.path.exists(nc_path):
            msg = f"⏩ Skipping existing file: {nc_filename}"
            print(msg)
            logging.info(msg)
            continue
            
        # Download file
        print(f"\n→ Downloading {filename} (Forecast hour: {fh})...")
        try:
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                with open(grib_path, 'wb') as f:
                    f.write(response.content)
                msg = f"   ✅ Download complete: {filename}"
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
            
        # Process file
        print(f"   🔄 Processing and converting to NetCDF using {engine}...")
        try:
            lon_dim, lat_dim = process_ecmwf_grib(
                grib_path, 
                nc_path, 
                coordinates,
                engine=engine,
                forecast_time=fh,
                variables=variables
            )
            msg = f"   📦 Saved subset: {nc_filename} ({lon_dim}x{lat_dim} grid)"
            print(msg)
            logging.info(msg)
        except Exception as e:
            msg = f"   ❌ Processing failed: {str(e)}"
            print(msg)
            logging.error(msg)
            continue
            
        # Cleanup
        try:
            os.remove(grib_path)
            print("   🧹 Removed GRIB file")
        except Exception as e:
            msg = f"   ⚠️ Cleanup failed: {str(e)}"
            print(msg)
            logging.warning(msg)
    
    return log_path

if __name__ == "__main__":
    args = parse_arguments()
    
    # Print execution parameters
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
    
    # Download and process ECMWF data
    log_file = download_and_process_ecmwf(
        start_date=args.start_date,
        run_hour=args.run_hour,
        days_number=args.days_number,
        time_step=args.time_step,
        coordinates=domain_coords,
        outpath=args.outpath,
        engine=args.engine,
        variables=args.variables
    )
    
    # Calculate and display execution time
    end_time = timeit.default_timer()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)
    
    time_msg = f"Total execution time: {int(minutes)} minutes {seconds:.2f} seconds"
    print(f"\n{time_msg}")
    
    print(f"\nProcess completed. See log for details: {log_file}")
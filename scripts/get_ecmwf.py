#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes ECMWF forecast data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
    python3 -m scripts.get_ecmwf

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
    return parser.parse_args()

def generate_ecmwf_urls(date, hour, max_forecast_hour, step):
    """Generate ECMWF forecast URLs with proper formatting"""
    base_url = "https://data.ecmwf.int/forecasts"
    urls = []
    for fh in range(0, max_forecast_hour + 1, step):
        forecast_str = f"{fh}h" if fh != 0 else "0h"
        filename = f"{date}{hour}0000-{forecast_str}-oper-fc.grib2"
        url = f"{base_url}/{date}/{hour}z/ifs/0p25/oper/{filename}"
        urls.append(url)
    return urls

def remove_idx_files(grib_path: str) -> None:
    """Remove any .idx files associated with a GRIB file"""
    idx_pattern = f"{grib_path}.*.idx"
    for idx_file in glob.glob(grib_path + ".*.idx"):
        try:
            os.remove(idx_file)
            print(f"   🧹 Removed index file: {os.path.basename(idx_file)}")
        except Exception as e:
            print(f"   ⚠️ Could not remove index file {os.path.basename(idx_file)}: {str(e)}")

def process_ecmwf_grib(file_path, output_path, coordinates):
    """Process ECMWF GRIB file: subset to domain and convert to NetCDF"""
    try:
        # Open GRIB file
        ds = xr.open_dataset(file_path, engine="cfgrib")
        
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
    
    except Exception as e:
        logging.error(f"Error processing {file_path}: {str(e)}")
        raise
    finally:
        # Always remove index files after processing
        remove_idx_files(file_path)

def download_and_process_ecmwf(start_date, run_hour, days_number, time_step, coordinates, outpath):
    """Download and process ECMWF wave forecast data"""
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
        f"🌊 Starting ECMWF wave forecast download\n"
        f"   Date: {start_date} Run: {run_hour}z\n"
        f"   Forecast range: 0-{max_forecast_hour} hours\n"
        f"   Time step: {time_step} hours\n"
        f"   Domain: Lon [{coordinates['lon_min']}, {coordinates['lon_max']}] "
        f"Lat [{coordinates['lat_min']}, {coordinates['lat_max']}]"
    )
    print(start_msg)
    logging.info(start_msg)
    
    # Generate URLs
    urls = generate_ecmwf_urls(start_date, run_hour, max_forecast_hour, time_step)
    
    # Process each forecast file
    for url in urls:
        # Extract filename and validation time
        filename = url.split("/")[-1]
        fh = int(filename.split("-")[1].replace("h", ""))
        valid_dt = datetime.strptime(start_date + run_hour, "%Y%m%d%H") + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")
        
        # Create file paths
        grib_path = os.path.join(raw_folder, filename)
        nc_filename = f"ecmwf_wave_{valid_str}.nc"
        nc_path = os.path.join(processed_folder, nc_filename)
        
        # Skip if processed file exists
        if os.path.exists(nc_path):
            msg = f"⏩ Skipping existing file: {nc_filename}"
            print(msg)
            logging.info(msg)
            continue
            
        # Download file
        print(f"\n→ Downloading {filename}...")
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
        print(f"   🔄 Processing and converting to NetCDF...")
        try:
            lon_dim, lat_dim = process_ecmwf_grib(grib_path, nc_path, coordinates)
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
        outpath=args.outpath
    )
    
    # Calculate and display execution time
    end_time = timeit.default_timer()
    elapsed = end_time - start_time
    minutes, seconds = divmod(elapsed, 60)
    
    time_msg = f"Total execution time: {int(minutes)} minutes {seconds:.2f} seconds"
    print(f"\n{time_msg}")
    
    print(f"\nProcess completed. See log for details: {log_file}")
#!/usr/bin/env python3
# coding: utf-8
"""
This script downloads and processes NOAA WW3 wave forecast data
Needs acces to the config file
If the date is not provided as an argument, the script will use the current date
Example:
python -m scripts.get_ww3_noaa --start_date 20231001 --days_number 3 --domain global --run_hour 00 --time_step 6 --outpath ./ww3_data
"""
import os
import re
import requests
from datetime import datetime, timedelta, timezone
import argparse
import timeit
import sys
from config import config
import logging

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
    return parser.parse_args()

def download_and_convert_ww3(target_date, run_hour, days_number, time_step, coordinates, outpath):
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_wave_0p25.pl"
    max_forecast_hours = min(384, days_number * 24)  # Max 16 days
    forecast_hours = list(range(0, max_forecast_hours + 1, time_step))
    
    # Create output directory
    outpath = os.path.join(outpath, f"{target_date}_{run_hour}")
    os.makedirs(outpath, exist_ok=True)

    # Setup logging
    log_path = os.path.join(outpath, "ww3_download.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Extract domain coordinates
    lon_min = coordinates["lon_min"]
    lon_max = coordinates["lon_max"]
    lat_min = coordinates["lat_min"]
    lat_max = coordinates["lat_max"]
    
    # Log start information
    start_msg = (
        f"🌊 Starting WW3 forecast download\n"
        f"   Date: {target_date} Run: {run_hour}z\n"
        f"   Forecast range: 0-{max_forecast_hours} hours\n"
        f"   Time step: {time_step} hours\n"
        f"   Domain: Lon [{lon_min}, {lon_max}] Lat [{lat_min}, {lat_max}]"
    )
    print(start_msg)
    logging.info(start_msg)
    
    # Convert target_date to datetime
    dt = datetime.strptime(target_date, "%Y%m%d")
    remote_dir = f"/gefs.{target_date}/{run_hour}/wave/gridded"
    
    # Process each forecast hour
    for fh in forecast_hours:
        f_str = f"{fh:03d}"
        remote_filename = f"gefs.wave.t{run_hour}z.mean.global.0p25.f{f_str}.grib2"
        valid_dt = dt + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")
        
        grib_name = f"ww3_{valid_str}.grib2"
        nc_name = f"ww3_{valid_str}.nc"
        grib_path = os.path.join(outpath, grib_name)
        nc_path = os.path.join(outpath, nc_name)
        
        # Skip processing if NetCDF file already exists
        if os.path.exists(nc_path):
            msg = f"⏩ Skipping existing file: {nc_name}"
            print(msg)
            logging.info(msg)
            continue
            
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
        print(f"\n→ Downloading {grib_name} (FH {fh:03d})...")
        try:
            response = requests.get(base_url, params=params, timeout=120)
            if response.status_code == 200:
                with open(grib_path, 'wb') as f:
                    f.write(response.content)
                msg = f"   ✅ Download complete: {grib_name}"
                print(msg)
                logging.info(msg)
            else:
                msg = f"   ⚠️ Server error ({response.status_code}) for {remote_filename}"
                print(msg)
                logging.warning(msg)
                continue
        except Exception as e:
            msg = f"   ❌ Download failed: {str(e)}"
            print(msg)
            logging.error(msg)
            continue
            
        # Convert to NetCDF
        print(f"   🔄 Converting to NetCDF: {nc_name}")
        try:
            import xarray as xr

            # Check if cfgrib engine is available
            if 'cfgrib' not in xr.backends.list_engines():
                raise ImportError("cfgrib engine not available. Install with: pip install cfgrib eccodes")
            
            # Use cfgrib engine to open the GRIB file
            with xr.open_dataset(grib_path, engine="cfgrib") as ds:
                compression = {var: {"zlib": True, "complevel": 4} for var in ds.data_vars}
                ds.to_netcdf(nc_path, format="NETCDF4_CLASSIC", encoding=compression)
            msg = f"   📦 Saved NetCDF: {nc_path}"
            print(msg)
            logging.info(msg)
        except ImportError as e:
            msg = f"   ❌ Conversion failed: {str(e)}"
            print(msg)
            logging.error(msg)
            print("   💡 Install required packages with: pip install cfgrib eccodes")
            sys.exit(1)
        except Exception as e:
            msg = f"   ❌ Conversion failed: {str(e)}"
            print(msg)
            logging.error(msg)
            continue
            
        # Clean up GRIB files
        try:
            os.remove(grib_path)
            print("   🧹 Removed GRIB file")
            
            # Remove any index files
            for file in os.listdir(outpath):
                if file.startswith(grib_name.split('.')[0]) and file.endswith(".idx"):
                    os.remove(os.path.join(outpath, file))
                    print(f"   🧹 Removed index file: {file}")
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
    
    # Download and process WW3 data
    log_file = download_and_convert_ww3(
        target_date=args.start_date,
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
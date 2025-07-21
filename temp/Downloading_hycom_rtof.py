#!/usr/bin/env python3
# coding: utf-8

import os
import requests
import xarray as xr
from datetime import datetime, timedelta

def process_and_save_subset(file_path, output_folder, lon_min, lon_max, lat_min, lat_max, log_path):
    try:
        ds = xr.open_dataset(file_path)

        lat = ds["Latitude"].values
        lon = ds["Longitude"].values % 360

        lon_min_mod = lon_min % 360
        lon_max_mod = lon_max % 360

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
            message = f"⚠️ No data found within region for {file_path}."
            print("   " + message)
            with open(log_path, 'a') as log:
                log.write(message + "\n")
            return False

        iy, ix = mask.nonzero()
        y0, y1 = iy.min(), iy.max()
        x0, x1 = ix.min(), ix.max()

        ds_subset = ds.isel(Y=slice(y0, y1 + 1), X=slice(x0, x1 + 1))

        base_name = os.path.basename(file_path)
        output_path = os.path.join(output_folder, f"subset_{base_name}")

        compression = {var: {"zlib": True, "complevel": 4} for var in ds_subset.data_vars}
        ds_subset.to_netcdf(output_path, format="NETCDF4_CLASSIC", encoding=compression)

        dims_y = ds_subset.sizes["Y"]
        dims_x = ds_subset.sizes["X"]
        lat_min_actual = ds_subset["Latitude"].min().item()
        lat_max_actual = ds_subset["Latitude"].max().item()
        lon_min_actual = ds_subset["Longitude"].min().item()
        lon_max_actual = ds_subset["Longitude"].max().item()

        message = (
            f"✅ {base_name} processed:\n"
            f"   Subset: Y={dims_y}, X={dims_x}\n"
            f"   Lat: {lat_min_actual:.2f} → {lat_max_actual:.2f}\n"
            f"   Lon: {lon_min_actual:.2f} → {lon_max_actual:.2f}"
        )
        print(message)

        with open(log_path, 'a') as log:
            log.write(message + "\n")

        ds.close()
        return True

    except Exception as e:
        error_msg = f"❌ Error processing {file_path}: {e}"
        print("   " + error_msg)
        with open(log_path, 'a') as log:
            log.write(error_msg + "\n")
        return False

def download_rtofs_forecast(base_date, time_step, raw_folder, output_folder, lon_min, lon_max, lat_min, lat_max):
    base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod/"
    log_path = os.path.join(output_folder, "log.txt")

    base_date = str(base_date)
    date_dt = datetime.strptime(base_date, "%Y%m%d")
    remote_folder = f"rtofs.{base_date}/"

    os.makedirs(raw_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)

    print(f"\n🌊 RTOFS forecast download for date: {base_date}")
    with open(log_path, 'w') as log:
        log.write(f"🌊 RTOFS processing log - Base date: {base_date}\n")
        log.write(f"   Region: Lon [{lon_min}, {lon_max}], Lat [{lat_min}, {lat_max}]\n\n")

    for fh in range(0, 193, time_step):
        f_str = f"{fh:03d}"
        remote_filename = f"rtofs_glo_2ds_f{f_str}_prog.nc"
        url = f"{base_url}{remote_folder}{remote_filename}"

        valid_dt = date_dt + timedelta(hours=fh)
        local_filename = f"rtofs_{valid_dt.strftime('%Y%m%d%H')}.nc"
        local_path = os.path.join(raw_folder, local_filename)

        print(f"\n→ Downloading {local_filename} ...")

        download_success = False
        processing_success = False

        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                print("   ✅ Download completed.")
                download_success = True
            else:
                print(f"   ⚠️ Server responded with status: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Download error: {e}")

        if download_success:
            processing_success = process_and_save_subset(
                file_path=local_path,
                output_folder=output_folder,
                lon_min=lon_min,
                lon_max=lon_max,
                lat_min=lat_min,
                lat_max=lat_max,
                log_path=log_path
            )

        if download_success and processing_success:
            try:
                os.remove(local_path)
                print("   🧹 Original file deleted.")
            except Exception as e:
                print(f"   ⚠️ Could not delete original file: {e}")

# === SCRIPT USAGE ===
if __name__ == "__main__":
    download_rtofs_forecast(
        base_date="20250714",
        time_step=6,
        raw_folder="./rtofs_raw_downloads",
        output_folder="./rtofs_processed",
        lon_min=-90,
        lon_max=1,
        lat_min=10,
        lat_max=54
    )

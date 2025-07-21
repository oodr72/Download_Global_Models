#!/usr/bin/env python3
# coding: utf-8

import os
import requests
import xarray as xr
from datetime import datetime, timedelta

def download_and_convert_ww3_to_netcdf(target_date, run_hour, time_step, output_folder):
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_wave_0p25.pl"
    dt = datetime.strptime(str(target_date), "%Y%m%d")

    forecast_hours = list(range(0, 385, time_step))
    os.makedirs(output_folder, exist_ok=True)

    print(f"\n🌊 WW3 forecast download and NetCDF conversion for {target_date} run {run_hour}z")

    for fh in forecast_hours:
        f_str = f"{fh:03d}"
        remote_filename = f"gefs.wave.t{run_hour}z.mean.global.0p25.f{f_str}.grib2"
        remote_dir = f"/gefs.{target_date}/{run_hour}/wave/gridded"
        valid_dt = dt + timedelta(hours=fh)
        valid_str = valid_dt.strftime("%Y%m%d%H")

        grib_name = f"ww3_noaa_{valid_str}.grib2"
        nc_name = f"ww3_noaa_{valid_str}.nc"
        grib_path = os.path.join(output_folder, grib_name)
        nc_path = os.path.join(output_folder, nc_name)

        params = {
            "file": remote_filename,
            "all_var": "on",
            "all_lev": "on",
            "subregion": "",
            "toplat": 54,
            "leftlon": -90,
            "rightlon": 1,
            "bottomlat": 10,
            "dir": remote_dir
        }

        print(f"→ Downloading {grib_name} ...")
        try:
            response = requests.get(base_url, params=params, timeout=60)
            if response.status_code == 200:
                with open(grib_path, 'wb') as f:
                    f.write(response.content)
                print("   ✅ Download complete.")

                print("   🔄 Converting to NetCDF ...")
                ds = xr.open_dataset(grib_path, engine="cfgrib")
                compression = {var: {"zlib": True, "complevel": 4} for var in ds.data_vars}
                ds.to_netcdf(nc_path, format="NETCDF4_CLASSIC", encoding=compression)
                ds.close()
                print(f"   📦 Saved NetCDF to: {nc_path}")

                os.remove(grib_path)
                for file in os.listdir(output_folder):
                    if file.startswith(os.path.basename(grib_path)) and file.endswith(".idx"):
                        try:
                            os.remove(os.path.join(output_folder, file))
                            print(f"   🧹 Index file {file} removed.")
                        except Exception as e:
                            print(f"   ⚠️ Could not remove idx file {file}: {e}")

                print("   🧹 Original GRIB2 file removed.")
            elif response.status_code == 404:
                print("   ⚠️ File not found on server (404)")
            else:
                print(f"   ⚠️ Server response: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

# === SCRIPT USAGE ===
if __name__ == "__main__":
    download_and_convert_ww3_to_netcdf(
        target_date="20250713",
        run_hour="06",
        time_step=6,
        output_folder="./ww3_netcdf"
    )

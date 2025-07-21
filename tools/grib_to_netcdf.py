import os
import shutil
import sys
from glob import glob
import xarray as xr
import cfgrib

def convert_grib_to_netcdf(folder_path):
    """
    Convert all GRIB2 files in a folder to NetCDF4 format using cfgrib/xarray integration.
    
    Args:
        folder_path (str): Path to directory containing GRIB2 files
    """
    # Find all grib2 files in the directory
    grib_files = glob(os.path.join(folder_path, "*.grb2")) + \
                 glob(os.path.join(folder_path, "*.grib2"))
    
    if not grib_files:
        print(f"No GRIB files found in {folder_path}")
        return

    for grib_file in grib_files:
        temp_nc = None
        try:
            # Generate corresponding netCDF filename
            if grib_file.endswith('.grb2'):
                nc_file = grib_file.replace('.grb2', '.nc')
            else:
                nc_file = grib_file.replace('.grib2', '.nc')
            temp_nc = nc_file + '.temp'
            
            print(f"Converting: {os.path.basename(grib_file)}")
            
            # Approach 1: Try standard xarray opening
            try:
                ds = xr.open_dataset(grib_file, engine='cfgrib')
                ds.to_netcdf(temp_nc)
                ds.close()
                
            # Approach 2: Handle complex files with multiple hypercubes
            except Exception as e:
                print(f"  Standard open failed: {str(e)}")
                print("  Attempting advanced handling with open_datasets...")
                
                datasets = cfgrib.open_datasets(grib_file)
                
                if len(datasets) == 1:
                    datasets[0].to_netcdf(temp_nc)
                    datasets[0].close()
                else:
                    # Write as multiple groups
                    for i, ds in enumerate(datasets):
                        mode = 'w' if i == 0 else 'a'
                        ds.to_netcdf(temp_nc, group=f"group_{i}", mode=mode)
                        ds.close()
                    print(f"  Saved {len(datasets)} groups in NetCDF file")
            
            # Replace original GRIB with new NetCDF
            os.remove(grib_file)
            shutil.move(temp_nc, nc_file)
            print(f"Successfully created: {os.path.basename(nc_file)}")
            
        except Exception as e:
            print(f"Error processing {grib_file}: {str(e)}")
            if temp_nc and os.path.exists(temp_nc):
                os.remove(temp_nc)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python grib_to_netcdf.py <folder_path>")
        sys.exit(1)
    
    target_folder = sys.argv[1]
    convert_grib_to_netcdf(target_folder)
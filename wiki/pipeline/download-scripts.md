# Download Scripts

## Atmosphere Models

### GFS (NOAA)
- **Script**: `scripts/get_gfs.py`
- **Source**: NOMADS (NOAA Global Forecast System)
- **Resolution**: 0.25°
- **Variables**: Wind (u10, v10), temperature (2t), pressure (msl), precipitation, humidity
- **Usage**: `python3 -m scripts.get_gfs --start_date YYYYMMDD --domain NAME --last_hour N`

### ECMWF HRES
- **Script**: `scripts/get_ecmwf.py`
- **Source**: ECMWF Open Data API
- **Resolution**: 0.25°
- **Variables**: Wind, temperature, pressure, precipitation, geopotential
- **Usage**: `python3 -m scripts.get_ecmwf --start_date YYYYMMDD --run_hour HH --domain NAME`
- **Note**: pygrib path is O(n²) for large domains; cfgrib recommended

## Ocean Models

### GLORYS (Copernicus)
- **Script**: `scripts/get_glorys.py`
- **Source**: Copernicus Marine Service
- **Resolution**: 0.083°
- **Variables**: Currents (uo, vo), SST, salinity, temperature, sea ice
- **Usage**: `python3 -m scripts.get_glorys --start_date YYYYMMDD --domain NAME --last_hour N`

### HYCOM/RTOFS (NOAA)
- **Script**: `scripts/get_hycom.py`
- **Source**: NOMADS (RTOFS global analysis)
- **Resolution**: 0.08° (HYCOM), 0.25° (RTOFS)
- **Variables**: Currents, SST, salinity, temperature

### RTOFS 2D (Advanced)
- **Script**: `scripts/get_rtofs_ocean2d.py`
- **Source**: NCSS/OPeNDAP (server-side subsetting)
- **Features**: HTTP range requests, intelligent subsetting

## Wave Models

### FMWAM (Copernicus)
- **Script**: `scripts/get_mfwave.py`
- **Source**: Copernicus Marine Service
- **Variables**: Significant wave height, direction, period

### WW3 (NOAA)
- **Script**: `scripts/get_ww3_noaa1.py`
- **Source**: NOMADS
- **Variables**: Significant wave height, direction, period

## Integrators

### Copernicus Integrator
- **Script**: `scripts/files_integrator_metocen_copernicus.py`
- **Shell**: `run/run_files_integrator_copernicus.sh`
- **Input**: GLORYS + ECMWF + FMWAM NetCDF files
- **Output**: Single integrated NetCDF with all variables on common grid

### NOAA Integrator
- **Script**: `scripts/files_Integrator_metocen_noaa.py`
- **Shell**: `run/run_files_integrator_noaa.sh`
- **Input**: HYCOM + GFS + WW3 NetCDF files
- **Output**: Single integrated NetCDF with curvilinear regridding
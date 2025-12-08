'''
config.py
Configuration file for global weather and ocean models
This file contains parameters for various global models including GFS, ECMWF, FMWAM, GLORYS, HYCOM, and WW3.
'''

# General configuration for global models
#------------------------------------------------
# Set the domain name
domain_name = "atlantic" # ["atlantic", "mediterranean", "arctic", "north_atlantic", "south_atlantic"]
# Set the number of days to forecast
days_number = 1 # [1, 3, 6]
time_step = 6  # Time step in hours

# Calculate the last hour and total number of hours for the forecast
last_hour = days_number * 24 # Latest forecast hour
number_of_hours = last_hour / time_step # Total number of forecast hours
#------------------------------------------------


# GFS model parameters
#------------------------------------------------
# GFS_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/WIND/Data_gfs"
GFS_output_directory="data/gfs"
GFS_run_time =  "00" # ["00", "06", "12", "18"]
GFS_timestep = time_step # [1, 3, 6]
GFS_last_hour = last_hour # 16 days (384 hours)
GFS_domain = domain_name

# GFS atmospheric variables
GFS_variables = [
    "UGRD", #   U-Component of Wind (zonal wind) in m/s
    "VGRD", #	V-Component of Wind (meridional wind) in m/s
    "TMP", #	Temperature in Kelvin (K)
    "VIS", #	Visibility in meters (m)
    "PRMSL", #	Pressure Reduced to Mean Sea Level (Pa)
    "PRES", #	Atmospheric Pressure at specified level (Pa)
    "GUST", #	Maximum Wind Speed (Gust) in m/s
    "APCP", #	Accumulated Precipitation (usually in kg/m²)
    "DPT", #	Dew Point Temperature (often in Kelvin or Celsius)
    "DSWRF", #	Downward Shortwave Radiation Flux
    "SPFH", #	Specific Humidity (kg/kg)
    ]
# GFS_variables = ["UGRD", "VGRD", "TMP", "PRMSL"]
#------------------------------------------------


# RTOFS Configuration
#------------------------------------------------
# RTOFS_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/OCEAN/Data_RTOFS"
# RTOFS_output_directory = "/media/amilcar/STORE/DATA/OPERATIVE_MODELS/OCEAN/Data_RTOFS"
RTOFS_output_directory = "data/rtofs"
RTOFS_run_time = "00" # ["00", "06", "12", "18"]
RTOFS_timestep = time_step # [1, 3, 6]
RTOFS_last_hour = last_hour # 16 days (72 hours) 
RTOFS_days_number = days_number
RTOFS_domain = domain_name

RTOFS_variables = [
   "SST", # Surface Temperature (K)
    "SSS", # Surface Salinity (psu)
    "UVEL", # U Velocity (m/s)
    "VVEL", # V Velocity (m/s)
    "SSH", # Sea Surface Height (m)
    "SIC", # Sea Ice Concentration (fraction)
    "SITHICK", # Sea Ice Thickness (m)
    "UICE", # Eastward Sea Ice Velocity (m/s)
    "VICE", # Northward Sea Ice Velocity (m/s)
    "SEAICE_CONCENTRATION", # Sea Ice Concentration (fraction)
    "SEAICE_THICKNESS", # Sea Ice Thickness (m)
    "MLD" # Mixed Layer Depth (m)
]
RTOFS_variables = ["SST", "SSS", "SSH", "UVEL", "VVEL", "SEAICE_THICKNESS"]
#------------------------------------------------


# ECMWF Configuration
#------------------------------------------------
ECMWF_days_number = days_number
ECMWF_domain = domain_name
ECMWF_run_hour = "12"
ECMWF_time_step = time_step
ECMWF_last_hour = last_hour
ECMWF_output_directory = "data/ecmwf"
ECMWF_variables = [
    "2t", # 2m temperature (K)
    "2d", # 2m dew point temperature (K)
    "10u", # 10m U wind component (m/s)
    "10v", # 10m V wind component (m/s)
    "10fg", # 10m wind gust (m/s)
    "100u", # 100m U wind component (m/s)
    "100v", # 100m V wind component (m/s)
    "msl", # Mean sea level pressure (Pa)
    "sst", # Sea surface temperature (K)
    "ssh", # Sea surface height (m)
    "tp", # Total precipitation (m)
    "tpr", # Total precipitation rate (kg m⁻² s⁻¹)
    "ssrd", # Integrated downward solar radiation (J m⁻²)
    "tisr", # Top incoming solar radiation (W m⁻²)
    "ets", # Evapotranspiration
    "nts", # Net surface solar radiation
    "sice", # Sea ice cover
    "usurf", # Ocean surface current (eastward)
    "vsurf" # Ocean surface current (northward)
    ]
ECMWF_variables = ["2t", "2d","msl","10u", "10v"]
# ECMWF_variables = None # Uncomment this line to set default variables
#------------------------------------------------

# FMWAM model parameters
#------------------------------------------------
# FMWAM_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/WAVE/Data_FMWAM"
FMWAM_output_directory="data/fmwam"
FMWAM_variables = [
    "VHM0_WW", # Significant Wave Height (SWH) of Wind Waves
    "VHM0_SW1", # Significant Wave Height (SWH) of Primary Swell Waves
    "VMDR_WW",  # Mean Direction of Wind Waves
    "VMDR_SW1", # Mean Direction of Primary Swell Waves
    "VTM01_WW", # Mean Period of Wind Waves
    "VTM01_SW1" # Mean Period of Primary Swell Waves
    ]
FMWAM_timestep_hours = time_step
FMWAM_days_number = days_number  # 9 (number of days to forecast)
FMWAM_last_hour = last_hour
FMWAM_domain = domain_name
#------------------------------------------------

# GLORYS model parameters
#------------------------------------------------
# GLORYS_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/MARINE_CURRENT/Data_Glorys"
GLORYS_output_directory = "data/glorys"
GLORYS_days_number = days_number
GLORYS_last_hour = last_hour
GLORYS_time_step = time_step
GLORYS_domain = domain_name
GLORYS_minimum_depth=0.49402499198913574
GLORYS_maximum_depth=0.49402499198913574

GLORYS_variables = [
    "thetao", # Potential Temperature
    "so",    # Salinity
    "zos",   # Sea Surface Height
    "uo",  # Eastward Sea Water Velocity
    "vo" # Northward Sea Water Velocity
    "siconc", # Sea Ice Concentration
    "sithick", # Sea Ice Thickness
    "usi", # Eastward Sea Ice Velocity
    "vsi", # Northward Sea Ice Velocity
    "mlotst" # Mixed Layer Depth
    ]
GLORYS_variables = ["uo", "vo"]
#------------------------------------------------

# HYCOM Configuration
HYCOM_days_number = days_number
HYCOM_last_hour = last_hour
HYCOM_domain = domain_name
HYCOM_output_directory = "data/hycom"
HYCOM_time_step = time_step

# WW3 Configuration
WW3_days_number = days_number
WW3_domain = domain_name
WW3_run_hour = "06"
WW3_time_step = time_step
WW3_output_directory = "data/ww3"

domains = {
    "atlantic": {  # North Atlantic and Carribean
        "lon_min": -90,
        "lon_max": 1,
        "lat_min": 9,
        "lat_max": 54
    },
    "mediterranean": {
        "lon_min": -5,
        "lon_max": 36,
        "lat_min": 30,
        "lat_max": 46 
    },
    "arctic": {
        "lon_min": -180,
        "lon_max": 180,
        "lat_min": 66.5,  # Arctic Circle
        "lat_max": 90
    },
    "north_atlantic": {
        "lon_min": -90,
        "lon_max": 0,
        "lat_min": 0,      # Equator
        "lat_max": 66.5    # Arctic Circle
    },
    "south_atlantic": {
        "lon_min": -90,
        "lon_max": 20,     # Cape Agulhas (20°E)
        "lat_min": -60,     # Antarctic Convergence
        "lat_max": 0       # Equator
    },
    "north_pacific": {
        "lon_min": 120,    # East Asia
        "lon_max": -100,   # West Americas (crosses dateline)
        "lat_min": 0,
        "lat_max": 66.5
    },
    "south_pacific": {
        "lon_min": 120,    # East Australia
        "lon_max": -70,    # West South America (crosses dateline)
        "lat_min": -60,
        "lat_max": 0
    },
    "indian": {
        "lon_min": 20,     # South Africa
        "lon_max": 120,    # West Australia
        "lat_min": -60,
        "lat_max": 30      # Persian Gulf
    },
    "southern": {          # Southern Ocean
        "lon_min": -180,
        "lon_max": 180,
        "lat_min": -80,    # Antarctic coast (approx.)
        "lat_max": -60     # Antarctic Convergence
    },
    "red_sea": {
        "lon_min": 32,     # Suez Canal
        "lon_max": 44,     # Bab-el-Mandeb
        "lat_min": 12,     # Southern entrance
        "lat_max": 30      # Gulf of Aqaba
    },
    "caribbean": {
        "lon_min": -90,    # Central America
        "lon_max": -60,    # Lesser Antilles
        "lat_min": 9,      # Panama/Caribbean Colombia
        "lat_max": 25      # Bahamas/Cuba
    }
}

# Output directory path

# Set the domain name
domain_name = "atlantic"
# Set the number of days to forecast
days_number = 5
number_of_hours = days_number * 24

# GFS model parameters
#------------------------------------------------
# GFS_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/WIND/Data_gfs"
GFS_output_directory="data/gfs"
# GFS_variables = ["UGRD", "VGRD", "TMP", "VIS", "SLP", "PRES", "PRMSL", "GUST", "APCP", "DPT", "DSWRF", "SPFH"]
GFS_atmospheric_variables = ["UGRD", "VGRD", "TMP", "VIS", "PRMSL", "PRES", "GUST", "APCP", "DPT", "DSWRF", "SPFH"]
# GFS_sea_variables = ["ICEC", "SST", "SSS", "SSH", "UVEL", "VVEL", "SIC", "SEAICE_THICKNESS"]
# GFS_sea_variables = ["ICEC"]
GFS_variables = GFS_atmospheric_variables #+ GFS_sea_variables
GFS_run_time =  "00" 
GFS_timestep = 6 
GFS_last_hour = number_of_hours # 16 days (384 hours)

GFS_domain = domain_name
GFS_days_number = days_number
GFS_run_hour = "00" # ["00", "06", "12", "18"]
GFS_time_step = 6 # [1, 3, 6]
#------------------------------------------------

#------------------------------------------------
# ECMWF Forecast Configuration
# ECMWF_forecast_days = 3      # Forecast duration in days
# ECMWF_run_hour = "00"         # Model run hour (00, 06, 12, 18)
# ECMWF_output_directory = "data/ecmwf"
# ECMWF_variables = ["UGRD", "VGRD", "TMP", "SPFH", "HGT"]
# ECMWF_resolution = 0.25  # Grid resolution in degrees
# ECMWF_time_step = 3  # Forecast step interval (hours)
# ECMWF_domain = domain_name

# ECMWF Configuration
ECMWF_days_number = days_number
ECMWF_domain = domain_name
ECMWF_run_hour = "00"
ECMWF_time_step = 6
ECMWF_output_directory = "data/ecmwf"


# FMWAM model parameters
#------------------------------------------------
# FMWAM_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/WAVE/Data_FMWAM"
FMWAM_output_directory="data/fmwam"
FMWAM_variables = ["VHM0_WW", "VHM0_SW1", "VMDR_WW", "VMDR_SW1", "VTM01_WW", "VTM01_SW1"]
FMWAM_days_number = days_number  # 9 (number of days to forecast)
FMWAM_domain = domain_name
#------------------------------------------------

# GLORYS model parameters
#------------------------------------------------
# GLORYS_output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/MARINE_CURRENT/Data_Glorys"
GLORYS_output_directory = "data/glorys"
GLORYS_variables = ["thetao", "uo", "vo"]
GLORYS_days_number = days_number
GLORYS_domain = domain_name
GLORYS_minimum_depth=0.49402499198913574
GLORYS_maximum_depth=0.49402499198913574
#------------------------------------------------

# HYCOM Configuration
HYCOM_days_number = days_number
HYCOM_domain = domain_name
HYCOM_output_directory = "data/hycom"
HYCOM_time_step = 6

# WW3 Configuration
WW3_days_number = days_number
WW3_domain = domain_name
WW3_run_hour = "06"
WW3_time_step = 6
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

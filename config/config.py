# Output directory path

# Set the domain name
domain_name = "atlantic"
# Set the number of days to forecast
days_number = 1
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
ECMWF_run_hour = "12"
ECMWF_time_step = 3
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
    "atlantic":{
        "lon_min": -90,
        "lon_max": 1,
        "lat_min": 9,
        "lat_max": 54
            },
    "d2":{
        "lon_min": -90,
        "lon_max": 1,
        "lat_min": 9,
        "lat_max": 54
            },    
    "caribbean": {
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
    }
}

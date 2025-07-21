import copernicusmarine
from config.config import MFWave_output_directory

# Fechas de inicio y fin
start_date = "2025-07-10"
end_date = "2025-07-19"

# Construir el nombre del archivo
output_filename = f"fmwam_wave_{start_date}_to_{end_date}.nc"

copernicusmarine.subset(
    dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
    dataset_version="202411",
    variables=["VHM0_WW", "VHM0_SW1", "VMDR_WW", "VMDR_SW1", "VTM01_WW", "VTM01_SW1"],
    minimum_longitude=-90,
    maximum_longitude=1,
    minimum_latitude=9,
    maximum_latitude=54,
    start_datetime=f"{start_date}T00:00:00",
    end_datetime=f"{end_date}T23:59:00",
    coordinates_selection_method="strict-inside",
    disable_progress_bar=True,
    output_directory=MFWave_output_directory,
    output_filename=output_filename
)

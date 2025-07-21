import copernicusmarine

# Fechas de inicio y fin
start_date = "2025-07-10"
end_date = "2025-07-19"

# Construir el nombre del archivo
output_filename = f"Glorys024_uv_{start_date}_to_{end_date}.nc"

copernicusmarine.subset(
    dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
    dataset_version="202406",
    variables=["thetao", "uo", "vo"],
    minimum_longitude=-90,
    maximum_longitude=1,
    minimum_latitude=9,
    maximum_latitude=54,
    start_datetime=f"{start_date}T00:00:00",
    end_datetime=f"{end_date}T23:00:00",
    minimum_depth=0.49402499198913574,
    maximum_depth=0.49402499198913574,
    coordinates_selection_method="strict-inside",
    disable_progress_bar=True,
    output_directory="/media/amilcar/STORE/DATA/OPERATIVE_MODELS/MARINE_CURRENT/Data_Glorys",
    output_filename=output_filename
)
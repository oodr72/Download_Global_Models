import xarray as xr
import cfgrib
from pathlib import Path

grib = Path("gfs_2025071900.grb2")
subsets = []

# ---- Surface-only fields --------------------------------------------------
surface_vars = ["pres", "tprate", "skintemp"]   # use your list
subsets.append(
    xr.open_dataset(
        grib,
        engine="cfgrib",
        backend_kwargs=dict(
            filter_by_keys={"typeOfLevel": "surface"},
            read_keys=["shortName"],            # speeds things up
        ),
    )[surface_vars]     # trim to keep only wanted variables
)

# ---- Height‑above‑ground (HAG) 10 m & 2 m ---------------------------------
hag_filters = [
    {"typeOfLevel": "heightAboveGround", "level": 10},   # 10 m winds
    {"typeOfLevel": "heightAboveGround", "level": 2},    # 2 m thermo
]
for f in hag_filters:
    subsets.append(
        xr.open_dataset(
            grib,
            engine="cfgrib",
            backend_kwargs=dict(filter_by_keys=f),
        )
    )

# ---- Merge & save ---------------------------------------------------------
ds = xr.merge(subsets, compat="override")
ds.to_netcdf("gfs_2025071900_near_surface.nc", encoding={"time": {"dtype": "int"}})
print("✅  Wrote gfs_2025071900_near_surface.nc")

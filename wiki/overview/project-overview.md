---
Title: Project Overview
Updated: 2026-05-31
Sources: Local repository audit, 2026-05-31
Raw: [Repository Audit and Implementation Notes](../../raw/ops/2026-05-31-repo-audit.md)
---

# Project Overview

Download_Global_Models is an operational downloader collection for global meteorological, oceanographic, and wave forecast products.

## Active Scripts

- `scripts/get_gfs.py`: NOAA GFS 0.25 deg GRIB2 downloads with optional NetCDF conversion.
- `scripts/get_ecmwf.py`: ECMWF public forecast GRIB2 downloads, domain subsetting, and NetCDF output.
- `scripts/get_glorys.py`: Copernicus Marine GLORYS physical ocean subset downloads.
- `scripts/get_mfwave.py`: Copernicus Marine MFWAM wave subset downloads.
- `scripts/get_hycom.py`: NOAA RTOFS/HYCOM NetCDF downloads and spatial subsetting.
- `scripts/get_ww3_noaa.py`: NOAA GEFS Wave / WW3 GRIB2 downloads and NetCDF conversion.

## Shared Surfaces

- `config/config.py` owns default domains, output folders, forecast lengths, variables, and run hours.
- `src/files_functions.py` owns credential helpers and dynamic config loading.
- `src/model_utils.py` owns shared date, forecast-hour, domain, file, directory, and GRIB index helpers.
- `tools/` contains optional operational tools for credential setup, GRIB conversion, and domain maps.

## Maintenance Direction

The repository should keep one active script per model under `scripts/`, with historical or experimental files treated as legacy examples. Tests should be offline by default and live downloads should be opt-in.

## See Also

- [Maintenance And Validation](../ops/maintenance-and-validation.md)
- [Implementation 2026-05-31](../ops/implementation-2026-05-31.md)
# Repository Audit and Implementation Notes

Source URL: Local workspace audit
Collected: 2026-05-31
Published: Unknown

## Source Context

The repository contains operational scripts for global model downloads: GFS, ECMWF, GLORYS, MFWAM, HYCOM/RTOFS, and WW3. It also contains tools for domain maps, GRIB to NetCDF conversion, and Copernicus Marine credential setup.

## Baseline Findings

- `src/files_functions.py` defined `get_copernicus_key()` twice. The second definition returned two values while scripts expected three.
- `.env` exists in the repository and is currently tracked by git. It was not read or modified during the implementation.
- `.gitignore` did not protect future `.env` changes, GRIB/NetCDF products, cfgrib indexes, logs, pytest cache, or generated figures.
- `requirements.txt` omitted imports used by the scripts and tools, including `requests`, `numpy`, `matplotlib`, `cartopy`, and pytest-related development dependencies.
- `test/` contained script copies/experiments rather than an executable offline pytest suite.
- `tools/grib_to_netcdf.py` deleted source GRIB files by default.
- `tools/get_domain_map.py` parsed CLI arguments and imported Cartopy at module import time.

## Implemented Actions

- Consolidated credential loading in `src/files_functions.py`.
- Added shared helpers in `src/model_utils.py` for dates, forecast hours, domains, directories, file checks, and GRIB index cleanup.
- Improved GFS, ECMWF, GLORYS, MFWAM, HYCOM, WW3, and tools with safer imports, better resource handling, and corrected parameter handling.
- Added offline pytest coverage for each major script area.
- Updated dependency files, README, operational docs, credentials docs, testing docs, workspace instructions, and a repo-specific maintenance skill.

## Validation

- `python3 -m compileall config src scripts tools test`
- `python3 -m pytest -q`: 15 passed, 2 warnings from the local xarray/netCDF4/numpy stack.
- All primary script and tool `--help` commands loaded without downloads.
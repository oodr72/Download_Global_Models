# Project Overview

## Purpose
Download, subset, and integrate global meteorological, oceanographic, and wave forecast models to user-defined geographic domains.

## Architecture
```
config/config.py (single source of truth)
    ↓
Downloader scripts (scripts/get_*.py)
    ↓
Integrators (scripts/files_integrator_*.py)
    ↓
Visualization tools (tools/windy_animator.py, etc.)
```

## Two Parallel Pipelines
1. **Copernicus**: GLORYS (ocean) + ECMWF HRES (atmosphere) + FMWAM (waves)
2. **NOAA**: HYCOM/RTOFS (ocean) + GFS (atmosphere) + WW3 (waves)

## Key Libraries
- xarray 2025.7.1, netCDF4 1.7.2
- cfgrib 0.9.15.0, pygrib
- copernicusmarine 2.2.0, cdsapi 0.7.6
- ecmwf-opendata 0.3.19

## Domains
12 pre-defined domains: atlantic, mediterranean, arctic, north_atlantic, south_atlantic, north_pacific, south_pacific, indian, southern, red_sea, caribbean

## Status
Operational — all critical bugs fixed as of 2025-06-17.
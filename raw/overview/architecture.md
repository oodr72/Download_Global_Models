# Repository Architecture

## Core Components

### Configuration
- `config/config.py` — Single source of truth for all model parameters, domains, variables, paths
- `src/files_functions.py` — Credential loaders for Copernicus and ECMWF APIs

### Download Scripts (`scripts/`)
| Script | Model | Type | Source |
|--------|-------|------|--------|
| `get_gfs.py` | NOAA GFS | Atmosphere | NOMADS |
| `get_ecmwf.py` | ECMWF HRES | Atmosphere | ECMWF Open Data |
| `get_glorys.py` | Copernicus GLORYS | Ocean | Copernicus Marine |
| `get_hycom.py` | NOAA RTOFS/HYCOM | Ocean | NOMADS |
| `get_mfwave.py` | Copernicus FMWAM | Waves | Copernicus Marine |
| `get_ww3_noaa1.py` | NOAA GEFS WW3 | Waves | NOMADS |
| `get_rtofs_ocean2d.py` | RTOFS 2D (advanced) | Ocean | NCSS/OPeNDAP |

### Integrators (`scripts/`)
- `files_integrator_metocen_copernicus.py` — Integrates GLORYS + ECMWF + FMWAM onto common grid
- `files_Integrator_metocen_noaa.py` — Integrates HYCOM + GFS + WW3 onto common grid (curvilinear regridding)

### Orchestration (`run/`)
- `run_files_integrator_copernicus.sh` — Shell wrapper for Copernicus workflow
- `run_files_integrator_noaa.sh` — Shell wrapper for NOAA workflow

### Visualization (`tools/`)
- `windy_animator.py` — Windy-style vector field animations
- `grib_to_netcdf.py` — GRIB to NetCDF conversion
- `get_domain_map.py` — Domain visualization

## Data Flow
1. Config defines domains → 2. Downloader scripts fetch & sub → 3. Integrators merge → 4. Visualization tools output

## Domains (12)
- atlantic, mediterranean, arctic, north_atlantic, south_atlantic
- north_pacific, south_pacific, indian, southern, red_sea, caribbean

## Two Parallel Pipelines
- **Copernicus**: GLORYS (ocean) + ECMWF (atm) + FMWAM (waves)
- **NOAA**: HYCOM/RTOFS (ocean) + GFS (atm) + WW3 (waves)
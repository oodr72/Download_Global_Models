# Download_Global_Models

Operational Python scripts to download, subset, and convert global forecast model data for meteorological, oceanographic, and wave workflows.

## Models

| Script | Provider/model | Main output | Notes |
| --- | --- | --- | --- |
| `scripts/get_gfs.py` | NOAA GFS 0.25 deg | GRIB2 or NetCDF | Downloads analysis and forecast hours from NOMADS. |
| `scripts/get_ecmwf.py` | ECMWF open forecast data | NetCDF subsets | Downloads GRIB2 files, subsets by configured domain, converts to NetCDF. |
| `scripts/get_glorys.py` | Copernicus GLORYS physical ocean | NetCDF | Requires Copernicus Marine credentials. |
| `scripts/get_mfwave.py` | Copernicus MFWAM wave | NetCDF | Requires Copernicus Marine credentials. |
| `scripts/get_hycom.py` | NOAA RTOFS/HYCOM | NetCDF subsets | Downloads and subsets ocean forecast files. |
| `scripts/get_ww3_noaa.py` | NOAA GEFS Wave / WW3 | NetCDF | Downloads wave GRIB2 files and converts with cfgrib. |

Default domains and output directories are configured in `config/config.py`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
```

GRIB and geospatial packages may also require system libraries:

```bash
sudo apt-get install libeccodes0 libeccodes-dev libproj-dev proj-bin proj-data
```

## Credentials

Copy `.env.example` to `.env` and fill local credentials only on your machine. Do not commit secrets.

```bash
cp .env.example .env
python3 -m tools.set_copernicusmarine_credentials
```

Supported Copernicus variables are `COPERNICUS_USER` and `COPERNICUS_KEY`; aliases `COPERNICUS_UID` and `COPERNICUS_API_TOKEN` are also accepted for compatibility.

## Usage

Always inspect CLI options before running a download:

```bash
python3 -m scripts.get_gfs --help
python3 -m scripts.get_ecmwf --help
python3 -m scripts.get_glorys --help
python3 -m scripts.get_mfwave --help
python3 -m scripts.get_hycom --help
python3 -m scripts.get_ww3_noaa --help
```

Examples:

```bash
python3 -m scripts.get_gfs --date 20260531 --time 00 --last_hour 24 --format grib2
python3 -m scripts.get_glorys --start_date 20260531 --days_number 1 --domain atlantic
python3 -m scripts.get_mfwave --start_date 20260531 --days_number 1 --variables VHM0_WW VMDR_WW
python3 -m tools.get_domain_map --domain atlantic --save
```

Downloaded model artifacts are ignored by git. Use temporary output folders for experiments and avoid committing NetCDF/GRIB products unless a small fixture is intentionally added.

## Visual Dashboard

An interactive Streamlit dashboard provides a graphical interface to configure, launch, and monitor downloads, visualize domains on a map, browse downloaded files, and preview NetCDF data.

```bash
streamlit run app.py
```

Features:
- Model/domain/date selector with per-model parameter panels
- Interactive Plotly geo-map of selected domain
- One-click download execution with live log streaming
- File browser with size and timestamp info
- NetCDF variable inspector with interactive 2-D plots

## Testing

The default test suite is offline and uses mocks or synthetic datasets.

```bash
python3 -m compileall config src scripts tools test
python3 -m pytest -q
```

Live provider downloads should be explicit and isolated from the normal test path. Use small date/hour windows and a temporary output folder.

## Maintenance

This repository includes an LLM wiki workflow in `.github/skills/llm-wiki.md`. After substantive changes, update `raw/`, `wiki/`, `wiki/index.md`, and `wiki/log.md` in the same pass as README/docs updates.

Future maintenance agents can use `.github/skills/download-global-models-maintenance/SKILL.md` for the standard audit, refactor, test, and wiki-update workflow.

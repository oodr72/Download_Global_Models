# Operations Runbook

## Configuration

Default output directories, domains, variables, run hours, and forecast lengths live in `config/config.py`.

Use domain names from `config.domains`. Scripts fail early with available domain names when an unknown domain is requested.

## Standard Commands

GFS:

```bash
python3 -m scripts.get_gfs --date 20260531 --time 00 --last_hour 24 --format grib2
```

ECMWF:

```bash
python3 -m scripts.get_ecmwf --start_date 20260531 --run_hour 12 --days_number 1
```

GLORYS:

```bash
python3 -m scripts.get_glorys --start_date 20260531 --days_number 1 --domain atlantic
```

MFWAM:

```bash
python3 -m scripts.get_mfwave --start_date 20260531 --days_number 1 --variables VHM0_WW VMDR_WW
```

HYCOM/RTOFS:

```bash
python3 -m scripts.get_hycom --start_date 20260531 --days_number 1 --time_step 6
```

WW3:

```bash
python3 -m scripts.get_ww3_noaa --start_date 20260531 --run_hour 06 --days_number 1
```

## Tools

Convert GRIB files without deleting originals:

```bash
python3 -m tools.grib_to_netcdf /path/to/grib-folder
```

Delete originals only after successful conversion when explicitly requested:

```bash
python3 -m tools.grib_to_netcdf /path/to/grib-folder --delete-originals
```

Save a domain map:

```bash
python3 -m tools.get_domain_map --domain atlantic --save
```

## Live Download Safety

Live downloads can be large and provider-dependent. Prefer small windows such as `--last_hour 0` or `--days_number 0` for smoke checks, and keep outputs in ignored temporary folders.
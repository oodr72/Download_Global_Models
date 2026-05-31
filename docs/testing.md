# Testing

The default suite is offline. It uses mocked HTTP/provider calls and synthetic `xarray` datasets.

## Commands

```bash
python3 -m compileall config src scripts tools test
python3 -m pytest -q
```

## Coverage Areas

- Shared date/domain/forecast-hour utilities.
- Copernicus credential environment handling.
- GFS URL generation and bounded forecast-hour downloads.
- GLORYS and MFWAM `copernicusmarine.subset` parameters without real credentials.
- WW3 use of CLI `days_number` without downloading successful payloads.
- HYCOM spatial subsetting with a synthetic NetCDF file.
- Import-safe tools for `grib_to_netcdf` and `get_domain_map`.

## Live Tests

Do not add live downloads to the default suite. If live smoke checks are needed, gate them behind an explicit flag such as `RUN_LIVE_DOWNLOADS=1` and use small time windows plus temporary output directories.
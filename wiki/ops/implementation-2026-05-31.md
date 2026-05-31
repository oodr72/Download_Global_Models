---
Title: Implementation 2026-05-31
Updated: 2026-05-31
Sources: Local repository audit, 2026-05-31
Raw: [Repository Audit and Implementation Notes](../../raw/ops/2026-05-31-repo-audit.md)
---

# Implementation 2026-05-31

## Code Changes

- Consolidated Copernicus credential loading and preserved compatibility with both primary and alias environment variable names.
- Added `src/model_utils.py` for date conversion, forecast-hour generation, domain lookup, directory creation, file validation, and GRIB index cleanup.
- Updated GFS to use bounded forecast-hour generation and close datasets after cfgrib conversion.
- Updated ECMWF and HYCOM to materialize subsets safely before source files are closed.
- Updated GLORYS and MFWAM to use ISO API dates and avoid importing Copernicus at CLI help/import time.
- Updated WW3 so `days_number` from the CLI controls the forecast range.
- Updated `grib_to_netcdf` so source GRIB files are preserved by default.
- Updated `get_domain_map` so help/import paths do not require Cartopy until plotting is requested.

## Tests

Added offline pytest coverage for utilities, credentials, GFS, Copernicus scripts, WW3, HYCOM synthetic processing, and import-safe tools.

## Documentation And Customization

- Expanded README with setup, credentials, usage, testing, and maintenance guidance.
- Added docs for credentials, operations, and testing.
- Added `.github/copilot-instructions.md` and `.github/skills/download-global-models-maintenance/SKILL.md`.
- Initialized `raw/` and `wiki/` according to `.github/skills/llm-wiki.md`.

## Residual Risks

- `.env` is currently tracked by git in this checkout. It was not read or modified. Future remediation should untrack and rotate secrets deliberately.
- Live provider behavior still depends on external availability, credentials, and installed GRIB/geospatial system libraries.

## See Also

- [Project Overview](../overview/project-overview.md)
- [Maintenance And Validation](maintenance-and-validation.md)
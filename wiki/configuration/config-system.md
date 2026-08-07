# Configuration System

## config/config.py

Single source of truth for all model parameters, domains, variables, and paths.

### Domain Definitions
Domains are defined as dictionaries with longitude/latitude bounds:
```python
domains = {
    "atlantic": {"lon": (-90, 1), "lat": (9, 54)},
    "caribbean": {"lon": (-90, -60), "lat": (9, 25)},
    ...
}
```

### Variable Lists
- `GLORYS_variables` — 10 variables (uo, vo, sst, salo, sithic, etc.)
- `ECMWF_variables` — 18 variables (2t, t, msl, u, v, etc.)
- `RTOFS_variables` — 12 variables (water_u, water_v, water_temp, etc.)
- `GFS_variables` — Full set from NOMADS
- `FMWAM_variables` — Wave parameters
- `WW3_variables` — Wave parameters

### Paths
- `data_dir` — Base directory for downloaded data
- `output_dir` — Directory for integrated outputs

## src/files_functions.py

Credential loaders for external APIs:
- `get_copernicus_key()` — Returns (user, key) tuple from .env
- ECMWF credential handling via `~/.ecmwfap_rc`

## .env.example

Template for credentials:
```bash
cp .env.example .env
# Edit .env with actual credentials
```

Sections:
- COPENICUS MARINE (GLORYS + FMWAM)
- ECMWF OPEN DATA API
- NCSS/OPENDAP ENDPOINTS (optional, for RTOFS 2D)
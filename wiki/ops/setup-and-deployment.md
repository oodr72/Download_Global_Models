# Setup and Deployment

## System Dependencies

### Ubuntu/Debian
```bash
# ECMWF grib APIs (for cfgrib)
sudo apt-get install libeccodes0 libeccodes-dev libproj-dev proj-bin proj-data

# NetCDF support
sudo apt-get install netcdf-bin libnetcdf-dev libhdf5-dev
```

### Python Dependencies
```bash
pip install -r requirements.txt
```

## Requirements Groups
- **Core**: xarray, netCDF4, numpy, scipy
- **GRIB**: cfgrib, pygrib
- **API clients**: copernicusmarine, cdsapi, ecmwf-opendata
- **HTTP**: requests
- **Config**: decouple, dotenv, python-decouple
- **Visualization**: matplotlib, cartopy, pillow
- **Engines**: h5netcdf
- **Re-gridding**: xesmf (optional)
- **Parallel**: dask (optional)
- **Testing**: pytest, pytest-cov

## Credentials Setup

### Copernicus Marine
```bash
python3 -c "import copernicusmarine; copernicusmarine.login(username='USER', password='KEY')"
```

### ECMWF
```bash
echo "apikey=EMAIL:KEY" > ~/.ecmwfap_rc
```

## Running Tests
```bash
pytest test/ -v
```

## Troubleshooting

### SyntaxError in config.py
- Check comma separation in variable lists
- Verify no duplicate variable list assignments

### IndentationError in scripts
- Common after manual editing of control flow blocks
- Verify `if/else/try/except` blocks are properly indented

### Function shadowing
- Check for duplicate function definitions (`grep -r 'def NAME' scripts/`)

### Module import errors
- Ensure `__init__.py` exists in package directories
- Check module names match file names
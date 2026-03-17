import cdsapi

c = cdsapi.Client()

c.retrieve(
    'reanalysis-era5-single-levels',
    {
        'product_type': 'reanalysis',
        'variable': [
            '2m_temperature', 'mean_sea_level_pressure',
        ],
        'year': '2024',
        'month': '08',
        'day': '06',
        'time': [
            '00:00', '06:00', '12:00', '18:00',
        ],
        'area': [50, -130, 30, -60], # North, West, South, East
        'format': 'netcdf', # or 'grib'
    },
    'download.nc'
)
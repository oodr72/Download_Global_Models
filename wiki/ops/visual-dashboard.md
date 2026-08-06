# Visual Dashboard

## Purpose

`app.py` is an interactive Streamlit web application that provides a graphical interface for controlling the global model download system and inspecting results.

## Launch

```bash
streamlit run app.py
```

Accessible at `http://localhost:8501` by default.

## Features

| Area | Capability |
| --- | --- |
| Sidebar | Model selection (GFS, ECMWF, GLORYS, MFWAM, HYCOM, WW3), domain picker, date, per-model parameters (run hour, time step, forecast length, output format, variables) |
| Domain Map tab | Interactive Plotly geo-map showing selected domain bounding box; table of all configured domains |
| Download tab | One-click download execution with real-time log streaming and status badges (ready / running / done / error) |
| Files tab | File browser showing downloaded NetCDF/GRIB2 files with size and modification time |
| Data Preview tab | xarray-powered inspector for NetCDF files with interactive Plotly 2-D heatmaps supporting time/depth dimension sliders |

## Architecture

- Reads model configuration from `config/config.py` (domains, variables, paths, run hours, time steps).
- Builds CLI commands via `build_command()` and executes them with `subprocess.Popen`, streaming stdout to the log area.
- Uses Plotly for maps and data visualization (no heavy cartopy dependency at runtime).
- xarray + netCDF4 for data inspection (optional—gracefully degrades if not installed).

## Dependencies

- `streamlit>=1.32.0`
- `plotly>=5.18.0`
- Optional: `xarray`, `netCDF4` (for Data Preview tab)

## Custom CSS

The app injects custom CSS for:
- Gradient sidebar (dark navy)
- Gradient metric cards
- Status badges (green/amber/red)
- Monospace log area with dark background
- Hover-highlight file items

import xarray as xr
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.animation import FuncAnimation

# === HELPER FUNCTIONS ===
def load_dataset(path):
    return xr.open_dataset(path, engine="netcdf4")

def get_variable(ds, name):
    var = ds[name]
    attrs = var.attrs
    fill_value = attrs.get('_FillValue', None)
    scale_factor = attrs.get('scale_factor', 1.0)
    add_offset = attrs.get('add_offset', 0.0)
    var = var.astype('float32')
    if fill_value is not None:
        var = var.where(var != fill_value)
    var = var * scale_factor + add_offset
    return var

def plot_spatial_map(data, lon, lat, title, output_file, cmap='viridis', contours=None):
    """Mapa espacial: colorbar completa, labels solo inferior/izquierda"""
    fig = plt.figure(figsize=(14, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([-85, -60, 9, 25])
    ax.coastlines(resolution='10m', linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.5)
    gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
    gl.top_labels = False    # Sin labels superior
    gl.right_labels = False  # Sin labels derecha
    ax.add_feature(cfeature.LAND, color='lightgray', alpha=0.5)
    ax.add_feature(cfeature.OCEAN, color='lightblue', alpha=0.3)
    
    if data.shape == lon.shape:
        img = ax.pcolormesh(lon, lat, data, cmap=cmap, shading='nearest')
    else:
        img = ax.pcolormesh(lon, lat, data.T, cmap=cmap, shading='nearest')
    
    fig.subplots_adjust(right=0.85)
    cbar_ax = fig.add_axes([0.88, 0.15, 0.03, 0.7])
    cbar = fig.colorbar(img, cax=cbar_ax, orientation='vertical')
    cbar.set_label(data.attrs.get("units", ""), size=14)
    cbar.ax.tick_params(labelsize=14)
    
    if contours:
        if data.shape == lon.shape:
            cs = ax.contour(lon, lat, data, levels=contours, colors='k', linewidths=0.5)
        else:
            cs = ax.contour(lon, lat, data.T, levels=contours, colors='k', linewidths=0.5)
        ax.clabel(cs, inline=True, fontsize=8)
    
    plt.title(title, fontsize=16, fontweight='bold', pad=20)
    plt.savefig(output_file, dpi=500, bbox_inches='tight')
    plt.close()

def plot_vector_map(u, v, lon_grid, lat_grid, title, output_file, density=3, scale=None, cmap='plasma'):
    """Campo vectorial: labels inferior/izquierda, TÍTULO CENTRADO"""
    fig = plt.figure(figsize=(16, 10))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([-85, -60, 9, 25])
    ax.coastlines(resolution='10m', linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.5)
    gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
    gl.top_labels = False
    gl.right_labels = False
    ax.add_feature(cfeature.LAND, color='lightgray', alpha=0.5)
    ax.add_feature(cfeature.OCEAN, color='lightblue', alpha=0.3)
    
    if u.ndim == 3:
        u_2d = u.values[0] if u.dims[0] == 'time' else u.values
        v_2d = v.values[0] if v.dims[0] == 'time' else v.values
    else:
        u_2d = u.values
        v_2d = v.values
    
    skip_lat = slice(None, None, density)
    skip_lon = slice(None, None, density)
    lon_sub = lon_grid[skip_lat, skip_lon]
    lat_sub = lat_grid[skip_lat, skip_lon]
    u_sub = u_2d[skip_lat, skip_lon]
    v_sub = v_2d[skip_lat, skip_lon]
    
    magnitude = np.sqrt(u_sub**2 + v_sub**2)
    max_magnitude = np.max(magnitude) if np.max(magnitude) > 0 else 1
    if scale is None:
        scale = 200 if max_magnitude > 10 else 50
    
    quiver = ax.quiver(lon_sub, lat_sub, u_sub, v_sub, magnitude, cmap=cmap, scale=scale,
                       width=0.003, minlength=0.5, headwidth=2, headlength=4)
    
    fig.subplots_adjust(right=0.85)
    cbar_ax = fig.add_axes([0.88, 0.15, 0.03, 0.7])
    cbar = fig.colorbar(quiver, cax=cbar_ax, orientation='vertical')
    cbar.set_label('Magnitude (m/s)', size=14)
    cbar.ax.tick_params(labelsize=14)
    
    ref_value = 5 if np.max(magnitude) > 3 else 2
    ax.quiverkey(quiver, 0.85, 0.92, ref_value, f'{ref_value} m/s',
                 coordinates='axes', labelpos='E', fontproperties={'size': 12})
    
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20, loc='center')  # TÍTULO CENTRADO
    plt.savefig(output_file, dpi=500, bbox_inches='tight')
    plt.close()

def animate_variable(var, lon, lat, times, output_file, title_base, interval_ms=1000, cmap='tab20b'):
    """Animación escalar: labels solo inferior/izquierda"""
    fig, ax = plt.subplots(figsize=(14, 10), subplot_kw={'projection': ccrs.PlateCarree()})
    ax.set_extent([-85, -60, 9, 25])
    ax.coastlines(resolution='10m', linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.5)
    gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
    gl.top_labels = False
    gl.right_labels = False
    ax.add_feature(cfeature.LAND, color='lightgray', alpha=0.5)
    ax.add_feature(cfeature.OCEAN, color='lightblue', alpha=0.3)
    
    img = ax.pcolormesh(lon, lat, var.isel(time=0), cmap=cmap, shading='nearest')
    fig.subplots_adjust(right=0.85)
    cbar_ax = fig.add_axes([0.88, 0.15, 0.03, 0.7])
    cbar = fig.colorbar(img, cax=cbar_ax, orientation='vertical')
    cbar.set_label(var.attrs.get("units", ""))
    cbar.ax.tick_params(labelsize=14)
    
    title = ax.set_title("", fontsize=14, fontweight='bold')
    
    def update(i):
        frame = var.isel(time=i)
        img.set_array(frame.values.ravel())
        timestamp = str(pd.to_datetime(times[i].values))[:16]
        title.set_text(f"{title_base}\n{timestamp}")
        return img, title
    
    ani = FuncAnimation(fig, update, frames=len(times), interval=interval_ms, blit=False)
    ani.save(output_file, writer='pillow', fps=1000/interval_ms, dpi=500)
    plt.close()

def animate_vector_field(u, v, lon_grid, lat_grid, times, output_file, title_base, interval_ms=1000, density=4, scale=None, cmap='plasma'):
    """Animación vectorial: labels solo inferior/izquierda"""
    fig, ax = plt.subplots(figsize=(16, 10), subplot_kw={'projection': ccrs.PlateCarree()})
    ax.set_extent([-85, -60, 9, 25])
    ax.coastlines(resolution='10m', linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=':', linewidth=0.5)
    gl = ax.gridlines(draw_labels=True, dms=True, x_inline=False, y_inline=False)
    gl.top_labels = False
    gl.right_labels = False
    ax.add_feature(cfeature.LAND, color='lightgray', alpha=0.5)
    ax.add_feature(cfeature.OCEAN, color='lightblue', alpha=0.3)
    
    skip_lat = slice(None, None, density)
    skip_lon = slice(None, None, density)
    lon_sub = lon_grid[skip_lat, skip_lon]
    lat_sub = lat_grid[skip_lat, skip_lon]
    
    u_first = u.isel(time=0).values
    v_first = v.isel(time=0).values
    u_sub_first = u_first[skip_lat, skip_lon]
    v_sub_first = v_first[skip_lat, skip_lon]
    magnitude_first = np.sqrt(u_sub_first**2 + v_sub_first**2)
    max_magnitude_first = np.max(magnitude_first) if np.max(magnitude_first) > 0 else 1
    if scale is None:
        scale = 200 if max_magnitude_first > 10 else 50
    
    quiver = ax.quiver(lon_sub, lat_sub, u_sub_first, v_sub_first, magnitude_first,
                       cmap=cmap, scale=scale, width=0.003, minlength=0.5, headwidth=2, headlength=3)
    quiver.set_clim(0, 1.2)
    
    fig.subplots_adjust(right=0.85)
    cbar_ax = fig.add_axes([0.88, 0.15, 0.03, 0.7])
    cbar = fig.colorbar(quiver, cax=cbar_ax, extend='max')
    cbar.set_label('Marine current speed (m/s)', size=14)
    
    ref_value = 5 if np.max(magnitude_first) > 3 else 2
    ax.quiverkey(quiver, 0.85, 0.92, ref_value, f'{ref_value} m/s',
                 coordinates='axes', labelpos='E', fontproperties={'size': 12})
    
    title = ax.set_title("", fontsize=14, fontweight='bold')
    
    def update(i):
        u_frame = u.isel(time=i).values
        v_frame = v.isel(time=i).values
        u_sub_frame = u_frame[skip_lat, skip_lon]
        v_sub_frame = v_frame[skip_lat, skip_lon]
        magnitude_frame = np.sqrt(u_sub_frame**2 + v_sub_frame**2)
        quiver.set_UVC(u_sub_frame, v_sub_frame)
        quiver.set_array(magnitude_frame.ravel())
        timestamp = str(pd.to_datetime(times[i].values))[:16]
        title.set_text(f"{title_base}")
        return quiver, title
    
    ani = FuncAnimation(fig, update, frames=len(times), interval=interval_ms, blit=False)
    ani.save(output_file, writer='pillow', fps=1000/interval_ms, dpi=500)
    plt.close()

# Resto del código main() permanece igual...
# (Incluye create_grid_coordinates, main(), etc. del original)

def plot_wind_time_series(u_wind, v_wind, times, output_file, title, location_info):
    """
    Gráfico mejorado de serie temporal con magnitud y dirección del viento
    """
    # Crear figura con gridspec para mejor control
    fig = plt.figure(figsize=(16, 10))
    gs = plt.GridSpec(3, 1, height_ratios=[1, 1, 0.08], hspace=0.3)  # 3 filas: 2 gráficos + colorbar
    
    ax1 = plt.subplot(gs[0])  # Gráfico superior
    ax2 = plt.subplot(gs[1])  # Gráfico medio
    cbar_ax = plt.subplot(gs[2])  # Área para colorbar
    
    # Calcular magnitud y dirección
    wind_magnitude = np.sqrt(u_wind**2 + v_wind**2)
    wind_direction = np.degrees(np.arctan2(-u_wind, -v_wind)) % 360  # Dirección meteorológica
    
    # Gráfico de magnitud (superior)
    ax1.plot(times, wind_magnitude, linewidth=2.5, color='darkred', label='Wind Speed')
    ax1.fill_between(times, wind_magnitude, alpha=0.3, color='darkred')
    ax1.set_ylabel('Wind Speed (m/s)', fontsize=14, fontweight='bold')
    ax1.set_title(f'{title} - Wind Speed', fontsize=16, fontweight='bold', pad=20)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=12)
    ax1.tick_params(axis='both', which='major', labelsize=14)
    
    # Estadísticas en el gráfico
    mean_speed = np.mean(wind_magnitude)
    max_speed = np.max(wind_magnitude)
    ax1.text(0.02, 0.98, f'Mean: {mean_speed:.2f} m/s\nMax: {max_speed:.2f} m/s', 
             transform=ax1.transAxes, verticalalignment='top', 
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
             fontsize=11, fontweight='bold')
    
    # Gráfico de dirección (medio)
    scatter = ax2.scatter(times, wind_direction, c=wind_magnitude, cmap='plasma', 
               s=180, alpha=0.7, edgecolors='black', linewidth=0.5)
    ax2.set_ylabel('Wind Direction (°)', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=14, fontweight='bold')
    ax2.set_title(f'{title} - Wind Direction', fontsize=16, fontweight='bold', pad=20)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='both', which='major', labelsize=16)
    
    # Leyenda de direcciones
    direction_labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    direction_values = [0, 45, 90, 135, 180, 225, 270, 315]
    ax2.set_yticks(direction_values)
    ax2.set_yticklabels(direction_labels)
    
    # Colorbar horizontal en área dedicada
    cbar = plt.colorbar(scatter, cax=cbar_ax, orientation='horizontal')
    cbar.set_label('Wind Speed (m/s)', fontsize=14, fontweight='bold')
    cbar.ax.tick_params(labelsize=12)
    
    # Compartir eje X
    ax1.sharex(ax2)
    
    # Ajustar fechas en eje X
    plt.setp(ax1.get_xticklabels(), visible=False)  # Ocultar labels en ax1
    
    plt.suptitle(f'Wind Analysis at {location_info}', fontsize=18, fontweight='bold', y=0.98)
    plt.savefig(output_file, dpi=500, bbox_inches='tight')
    plt.close()

# === MAIN PROGRAM ===

def main():
    print("=== Ocean Wave Analysis Tool - Scientific Service ===")
    
    path = "/media/amilcar/STORE/COMPARTIDA/TRABAJO/01_PYTHON_PROJECTS/DATA_PROCESSING/Making_IntegratedFiles/Outputs_Copernicus/integrated_european_file_20250816_20250819.nc"  # Ruta real del archivo
    
    try:
        ds = load_dataset(path)
        print(f"Dataset cargado correctamente: {len(ds.time)} tiempos disponibles")
    except Exception as e:
        print(f"Error: No se pudo cargar el dataset en {path}: {e}")
        return

    # CREAR LA GRILLA UNA VEZ aquí mismo
    def create_grid_coordinates(ds):
        """Crea coordenadas de grilla consistentes para todo el plotting"""
        lon = ds.longitude
        lat = ds.latitude
        
        # Si ya son 2D, usarlas directamente
        if lon.ndim == 2 and lat.ndim == 2:
            return lon.values, lat.values
        # Si son 1D, crear meshgrid
        else:
            lon_1d = lon.values
            lat_1d = lat.values
            lon_grid, lat_grid = np.meshgrid(lon_1d, lat_1d, indexing='ij')
            return lon_grid, lat_grid

    # Crear las coordenadas de grilla
    lon_grid, lat_grid = create_grid_coordinates(ds)

    var_names = list(ds.data_vars)
    print(f"Variables disponibles: {var_names}")

    # 1. Altura significativa de la ola animada
    print("\n1. Generando animación de altura significativa de ola...")
    try:
        wave_height_vars = [v for v in var_names if any(keyword.lower() in v.lower() for keyword in ['VHM0', 'swh', 'hs', 'wave_height', 'significant'])]
        if wave_height_vars:
            wave_height_name = wave_height_vars[0]
            wave_height = get_variable(ds, wave_height_name)
            animate_variable(wave_height, lon_grid, lat_grid, 
                           ds.time, "1_significant_wave_height_animation.gif", 
                           "Significant Wave Height", cmap='tab20b', interval_ms=500)
            print("✓ Animación de altura de ola guardada: 1_significant_wave_height_animation.gif")
        else:
            print("✗ No se encontró variable de altura significativa de ola")
    except Exception as e:
        print(f"✗ Error en animación de ola: {e}")

    # 2. Campo vectorial del viento en el primer instante de tiempo
    print("\n2. Generando campo vectorial del viento...")
    try:
        u_wind_vars = [v for v in var_names if any(keyword in v.lower() for keyword in ['u10', '10u', 'uwnd', 'u_wind'])]
        v_wind_vars = [v for v in var_names if any(keyword in v.lower() for keyword in ['v10', '10v', 'vwnd', 'v_wind'])]
        
        if u_wind_vars and v_wind_vars:
            u_wind_name = u_wind_vars[0]
            v_wind_name = v_wind_vars[0]
            u_wind = get_variable(ds, u_wind_name)
            v_wind = get_variable(ds, v_wind_name)
            
            timestamp = str(pd.to_datetime(ds.time[0].values))[:16]
            plot_vector_map(u_wind.isel(time=0), v_wind.isel(time=0),
                            lon_grid, lat_grid, 
                            f"Wind Vector Field", 
                            "2_wind_vector_field.png", 
                            density=8, scale=200, cmap='coolwarm')  # density=4 para mejor visualización
            print("✓ Campo vectorial del viento guardado: 2_wind_vector_field.png")
        else:
            print("✗ No se encontraron componentes U/V del viento")
    except Exception as e:
        print(f"✗ Error en campo vectorial del viento: {e}")

    # 3. Campo vectorial de la corriente marina animada
    print("\n3. Generando animación de corrientes marinas...")
    try:
        u_current_vars = [v for v in var_names if any(keyword in v.lower() for keyword in ['uo', 'uoc', 'u_current', 'curr_u'])]
        v_current_vars = [v for v in var_names if any(keyword in v.lower() for keyword in ['vo', 'voc', 'v_current', 'curr_v'])]
        
        if u_current_vars and v_current_vars:
            u_current_name = u_current_vars[0]
            v_current_name = v_current_vars[0]
            u_current = get_variable(ds, u_current_name)
            v_current = get_variable(ds, v_current_name)
            
            n_frames = min(10, len(ds.time))
            animate_vector_field(u_current.isel(time=slice(0, n_frames)),
                                 v_current.isel(time=slice(0, n_frames)),
                                 lon_grid, lat_grid,
                                 ds.time.isel(time=slice(0, n_frames)), 
                                 "3_ocean_currents_animation.gif", 
                                 "Ocean Currents Vector Field", 
                                 interval_ms=800, density=8, scale=40, cmap='viridis')  # density=5 para corrientes
            print("✓ Animación de corrientes marinas guardada: 3_ocean_currents_animation.gif")
        else:
            print("✗ No se encontraron componentes U/V de corrientes marinas")
    except Exception as e:
        print(f"✗ Error en animación de corrientes: {e}")

    # 4. Gráfico mejorado de magnitud y dirección del viento
    print("\n4. Generando análisis completo de viento...")
    try:
        if 'u_wind' in locals() and 'v_wind' in locals():
            target_lon = -9.0
            target_lat = 39.0
            
            u_point = u_wind.sel(longitude=target_lon, latitude=target_lat, method="nearest")
            v_point = v_wind.sel(longitude=target_lon, latitude=target_lat, method="nearest")
            
            actual_lon = u_point.longitude.values
            actual_lat = u_point.latitude.values
            location_info = f"({actual_lon:.2f}°E, {actual_lat:.2f}°N)"
            
            plot_wind_time_series(u_point, v_point, pd.to_datetime(ds.time.values), 
                                "4_wind_analysis_timeseries.png", 
                                "Wind Analysis", location_info)
            print("✓ Análisis completo de viento guardado: 4_wind_analysis_timeseries.png")
        else:
            print("✗ No se encontraron datos de viento para el análisis")
    except Exception as e:
        print(f"✗ Error en análisis de viento: {e}")

    print("\n=== Proceso completado ===")
    print("Figuras generadas con 500 dpi de resolución para servicio científico-tecnológico")

if __name__ == "__main__":
    main()

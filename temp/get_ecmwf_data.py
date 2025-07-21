import os
import subprocess
import argparse

def generate_ecmwf_urls(date, hour, max_forecast_hour, step=3):
    """
    Genera una lista de URLs para los archivos .grib2 del modelo ECMWF.
    
    :param date: Fecha del ciclo en formato YYYYMMDD.
    :param hour: Hora del ciclo (e.g., "12z").
    :param max_forecast_hour: Máximo plazo de pronóstico en horas.
    :param step: Intervalo de tiempo entre las salidas, por defecto 3 horas.
    :return: Lista de URLs generados.
    """
    base_url = "https://data.ecmwf.int/forecasts"
    urls = []
    for forecast_hour in range(0, max_forecast_hour + 1, step):
        # Manejar el formato de horas
        forecast_str = f"{forecast_hour}h" if forecast_hour != 0 else "0h"
        filename = f"{date}{hour[:2]}0000-{forecast_str}-oper-fc.grib2"
        url = f"{base_url}/{date}/{hour}/ifs/0p25/oper/{filename}"
        urls.append(url)
    return urls

def create_download_directory(base_path, date, hour):
    """
    Crea un directorio basado en la fecha y hora.
    
    :param base_path: Ruta base donde se crearán las carpetas.
    :param date: Fecha del ciclo en formato YYYYMMDD.
    :param hour: Hora del ciclo (e.g., "12z").
    :return: Ruta completa del directorio creado.
    """
    folder_name = f"{date}{hour[:-1]}"  # Crear nombre de carpeta YYYYMMDDhh
    full_path = os.path.join(base_path, folder_name)
    os.makedirs(full_path, exist_ok=True)
    return full_path

def download_files(urls, download_dir):
    """
    Descarga los archivos desde una lista de URLs a un directorio especificado.
    
    :param urls: Lista de URLs a descargar.
    :param download_dir: Directorio donde se guardarán los archivos.
    """
    for url in urls:
        filename = url.split("/")[-1]
        destination = os.path.join(download_dir, filename)
        print(f"Downloading {url} to {destination}...")
        try:
            subprocess.run(["wget", "-c", "--tries=15", "-O", destination, url], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error downloading {url}: {e}")

if __name__ == "__main__":
    # Configuración del parser de argumentos
    parser = argparse.ArgumentParser(description="Descarga archivos del modelo ECMWF.")
    parser.add_argument("-d", "--date", type=str, required=True, help="Fecha del ciclo en formato YYYYMMDD")
    parser.add_argument("-t", "--time", type=str, required=True, help="Hora del ciclo en formato HHz (e.g., 12z)")
    parser.add_argument("-m", "--max_forecast_hour", type=int, default=186, help="Máximo plazo de pronóstico en horas (default: 186)")
    parser.add_argument("-s", "--step", type=int, default=3, help="Intervalo de horas entre pronósticos (default: 3)")
    
    args = parser.parse_args()
    
    # Parámetros
    base_path = "data/ecmwf"
    date = args.date
    hour = args.time
    max_forecast_hour = args.max_forecast_hour
    step = args.step

    if not os.path.exists(base_path):
        os.makedirs(base_path)
        

    # Generar URLs
    urls = generate_ecmwf_urls(date, hour, max_forecast_hour, step)

    # Crear directorio para la descarga
    download_dir = create_download_directory(base_path, date, hour)

    # Descargar archivos
    download_files(urls, download_dir)


    # Example:
    # python3 get_ecmwf_data.py -d 20250102 -t 12z


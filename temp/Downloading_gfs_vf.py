import requests
from datetime import datetime, timedelta
import os

def descargar_gfs(fecha_str, hora_str="00", ruta_guardado=".", lon_left=-90, lon_right=1, lat_top=54, lat_bottom=9):
    """
    Descarga archivos GFS desde análisis (anl) y pronósticos (f006, f012, ..., f384).
    - fecha_str: fecha inicial en formato 'yyyymmdd'
    - hora_str: hora de corrida '00', '06', '12' o '18'
    - ruta_guardado: carpeta donde se guardarán los archivos descargados
    """
    base_url = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    variables = ["UGRD", "U-GWD", "VGRD", "V-GWD"]
    var_params = "&".join([f"var_{v}=on" for v in variables])
    
    # Crear carpeta si no existe
    if not os.path.exists(ruta_guardado):
        os.makedirs(ruta_guardado)
    
    # Parsear fecha y hora inicial a datetime
    fecha_hora_inicial = datetime.strptime(fecha_str + hora_str, "%Y%m%d%H")
    
    def construir_url_nombre(tipo, fhour=None):
        if tipo == "anl":
            file_param = f"gfs.t{hora_str}z.pgrb2.0p25.anl"
            fecha_carpeta = fecha_str
            nombre_archivo = f"gfs_{fecha_str}{hora_str}.grb2"
        else:
            fhour_str = f"{fhour:03d}"
            file_param = f"gfs.t{hora_str}z.pgrb2.0p25.f{fhour_str}"
            fecha_pron = fecha_hora_inicial + timedelta(hours=fhour)
            fecha_pron_str = fecha_pron.strftime("%Y%m%d%H")
            nombre_archivo = f"gfs_{fecha_pron_str}.grb2"
            fecha_carpeta = fecha_str
        
        url = (f"{base_url}?file={file_param}&{var_params}"
               f"&subregion=&leftlon={lon_left}&rightlon={lon_right}"
               f"&toplat={lat_top}&bottomlat={lat_bottom}"
               f"&dir=%2Fgfs.{fecha_carpeta}%2F{hora_str}%2Fatmos")
        return url, nombre_archivo

    def descargar(url, nombre):
        ruta_completa = os.path.join(ruta_guardado, nombre)
        print(f"Descargando {nombre} ...")
        r = requests.get(url)
        if r.status_code == 200:
            with open(ruta_completa, "wb") as f:
                f.write(r.content)
            print(f"Guardado {ruta_completa}")
        else:
            print(f"Error al descargar {nombre}: HTTP {r.status_code}")

    # Descargar análisis
    url_anl, archivo_anl = construir_url_nombre("anl")
    descargar(url_anl, archivo_anl)

    # Descargar pronósticos de 6 en 6 horas hasta 384h
    for fh in range(6, 385, 6):
        url_f, archivo_f = construir_url_nombre("f", fhour=fh)
        descargar(url_f, archivo_f)

# Ejemplo de uso:
fecha_inicial = "20250710"
hora_corrida = "12"
ruta_datos = "/media/amilcar/STORE/DATA/OPERATIVE_MODELS/WIND/Data_gfs"

descargar_gfs(fecha_inicial, hora_corrida, ruta_guardado=ruta_datos)

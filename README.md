# Download_Global_Models

> Sistema para descarga, subconjunto y integración de modelos meteorológicos y oceanográficos globales.

## 🌍 Modelos disponibles

### Pila Copernicus
| Modelo | Variable | Fuente | Script |
|--------|----------|--------|--------|
| GLORYS 0.083° | Corrientes, SST, salinidad, hielo | Copernicus Marine | `scripts/get_glorys.py` |
| ECMWF HRES 0.25° | Viento, temperatura, presión, precipitación | ECMWF Open Data | `scripts/get_ecmwf.py` |
| FMWAM | Altura, dirección y período de olas | Copernicus Marine | `scripts/get_mfwave.py` |

### Pila NOAA
| Modelo | Variable | Fuente | Script |
|--------|----------|--------|--------|
| GFS 0.25° | Viento, temperatura, presión, precipitación | NOMADS (NOAA) | `scripts/get_gfs.py` |
| RTOFS/HYCOM | Corrientes, SST, salinidad | NOMADS (NOAA) | `scripts/get_hycom.py`, `scripts/get_rtofs_ocean2d.py` |
| GEFS/WW3 | Altura, dirección y período de olas | NOMADS (NOAA) | `scripts/get_ww3_noaa1.py` |

## ⚡ Setup rápido

### 1. Clonar y crear entorno virtual
```bash
git clone https://github.com/oodr72/Download_Global_Models.git
cd Download_Global_Models
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias
```bash
# Dependencias del sistema (Ubuntu/Debian)
sudo apt-get install libeccodes0 libeccodes-dev libproj-dev proj-bin proj-data
sudo apt-get install netcdf-bin libnetcdf-dev libhdf5-dev

# Dependencias Python
pip install -r requirements.txt
```

### 3. Configurar credenciales
```bash
cp .env.example .env
# Editar .env con tus credenciales
```

#### Copernicus Marine
```bash
python3 -c "import copernicusmarine; copernicusmarine.login(username='TU_USUARIO', password='TU_CLAVE')"
```

#### ECMWF
```bash
echo "apikey=TU_EMAIL:TU_KEY" > ~/.ecmwfap_rc
```

### 4. Configurar dominio

Editar `config/config.py` para cambiar el dominio:
```python
domain_name = "atlantic"  # Opciones:
# atlantic, mediterranean, arctic, north_atlantic, south_atlantic
# north_pacific, south_pacific, indian, southern, red_sea, caribbean
```

## 🚀 Uso

### Descargar datos de un modelo individual
```bash
# GFS today
python3 -m scripts.get_gfs --start_date 20251206 --domain atlantic --last_hour 24

# ECMWF with specific run
python3 -m scripts.get_ecmwf --start_date 20251206 --run_hour 12 --domain caribbean

# GLORYS
python3 -m scripts.get_glorys --start_date 20251206 --domain atlantic --last_hour 48

# FMWAM
python3 -m scripts.get_mfwave --start_date 20251206 --domain atlantic --last_hour 24

# HYCOM/RTOFS
python3 -m scripts.get_hycom --start_date 20251206 --domain atlantic

# RTOFS 2D con subsetting
python3 -m scripts.get_rtofs_ocean2d --start_date 20251206 --domain atlantic --last_hour 72
```

### Integrar múltiples modelos (Copernicus)
```bash
# Descarga e integra GLORYS + ECMWF + FMWAM
bash run/run_files_integrator_copernicus.sh
```

### Integrar múltiples modelos (NOAA)
```bash
# Descarga e integra HYCOM + GFS + WW3
bash run/run_files_integrator_noaa.sh
```

### Visualización
```bash
# Animación estilo Windy (corrientes)
python3 -m tools.windy_animator \
  --nc data/copernicus/20251206/integrated_copernicus_20251206.nc \
  --mode currents_map --uvar uo --vvar vo \
  --out figures/gifs/20251206/currents.gif

# Mapa de dominios
python3 -m tools.get_domain_map
```

## 📁 Estructura del proyecto

```
Download_Global_Models/
├── config/              # Configuración centralizada (dominios, variables, rutas)
│   └── config.py
├── scripts/             # Scripts de descarga e integración
│   ├── get_gfs.py       # NOAA GFS (atmósfera)
│   ├── get_ecmwf.py     # ECMWF HRES (atmósfera)
│   ├── get_glorys.py    # Copernicus GLORYS (océano)
│   ├── get_hycom.py     # NOAA RTOFS/HYCOM (océano)
│   ├── get_mfwave.py    # Copernicus FMWAM (olas)
│   ├── get_ww3_noaa1.py # NOAA GEFS WW3 (olas)
│   ├── get_rtofs_ocean2d.py  # RTOFS 2D avanzado
│   ├── files_integrator_metocen_copernicus.py  # Integrador Copernicus
│   └── files_Integrator_metocen_noaa.py        # Integrador NOAA
├── src/                 # Utilidades compartidas
│   └── files_functions.py  # Credenciales y configuración
├── tools/               # Herramientas auxiliares
│   ├── windy_animator.py
│   ├── grib_to_netcdf.py
│   ├── get_domain_map.py
│   └── ...
├── run/                 # Scripts de orquestación (shell)
│   ├── run_files_integrator_copernicus.sh
│   └── run_files_integrator_noaa.sh
├── test/                # Pruebas (pytest)
└── data/                # Datos descargados (generado)
    ├── gfs/, ecmwf/, glorys/, fmwam/, hycom/, ww3/
    └── integrated/      # Resultados de integración
```

## 🧪 Tests

```bash
# Ejecutar pruebas
pytest test/ -v
```

## 📊 Dominios disponibles

| Dominio | Región | Lon [°] | Lat [°] |
|---------|--------|---------|---------|
| atlantic | Atlántico N + Caribe | -90 → 1 | 9 → 54 |
| mediterranean | Mediterráneo | -5 → 36 | 30 → 46 |
| arctic | Ártico | -180 → 180 | 66.5 → 90 |
| caribbean | Caribe | -90 → -60 | 9 → 25 |
| north_atlantic | Atlántico Norte | -90 → 0 | 0 → 66.5 |
| south_atlantic | Atlántico Sur | -90 → 20 | -60 → 0 |
| north_pacific | Pacífico Norte | 120 → -100 | 0 → 66.5 |
| south_pacific | Pacífico Sur | 120 → -70 | -60 → 0 |
| indian | Índico | 20 → 120 | -60 → 30 |
| southern | Océano Austral | -180 → 180 | -80 → -60 |
| red_sea | Mar Rojo | 32 → 44 | 12 → 30 |

## ⚠️ Notas

- **Saltarse archivos válidos**: Todos los scripts verifican integridad de archivos NetCDF y saltan descargas si ya existen archivos válidos.
- **Forzar re-descarga**: Usa `--force_redownload` para forzar la descarga completa.
- **Logging**: Usa `--log_level DEBUG` para diagnosticar problemas.
- **ECMWF pygrib**: La ruta con pygrib es lenta para dominios grandes (O(n²)). Se recomienda usar `cfgrib` (predeterminado).

## 🤝 Autores

- **Amilcar E. Calzada** — Arquitectura y diseño del sistema
- **Oscar O. Diaz** — Desarrollo, integración y mantenimiento
- Colaboración con asistencia de IA

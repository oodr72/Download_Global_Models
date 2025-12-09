#!/bin/bash

start_date=20251206
start_hour=00
final_hour=23
start_time=${start_date}-${start_hour}
end_time=${start_date}-${final_hour}
dt_hours=6
path_ehm="./data/glorys"
path_eam="./data/ecmwf/${start_date}_12"
path_ewm="./data/fmwam"
output_dir="data/copernicus"
mkdir -p ${output_dir}/${start_date}


python3 -m scripts.Integrator_ocean-atmosphere_copernicus_project \
    --start ${start_time} \
    --end ${end_time} \
    --dt_hours ${dt_hours} \
    --path_ehm ${path_ehm} \
    --path_eam ${path_eam} \
    --path_ewm ${path_ewm} \
    --out ${output_dir}/${start_date}/integrated_copernicus_${start_date}.nc
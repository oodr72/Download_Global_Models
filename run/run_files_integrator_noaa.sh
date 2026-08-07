#!/bin/bash

start_date=20251206
start_hour=00
final_hour=23
start_time=${start_date}-${start_hour}
end_time=${start_date}-${final_hour}
dt_hours=6
path_ehm="./data/hycom/${start_date}"
path_eam="./data/gfs/${start_date}_00"
path_ewm="./data/ww3/${start_date}_06"
output_dir="data/integrated"
mkdir -p ${output_dir}/${start_date}


python3 -m scripts.files_Integrator_metocen_noaa \
    --start ${start_time} \
    --end ${end_time} \
    --dt_hours ${dt_hours} \
    --path_ahm ${path_ehm} \
    --path_aam ${path_eam} \
    --path_awm ${path_ewm} \
    --out ${output_dir}/${start_date}/integrated_noaa_${start_date}.nc
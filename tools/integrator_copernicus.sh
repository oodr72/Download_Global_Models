#!/bin/bash

start_date=20250805
output_dir="data/copernicus/${start_date}"


python3 -m scripts.integrator_ocean-atmosphere_copernicus_project \
    --start_date ${start_date} \
    --run_hour ${run_hour} \
    --days_number ${days_number} \
    --domain ${domain} \
    --time_step ${time_step} \
    --outpath ${output_dir}
#!/bin/bash

start_date=20250805
run_hour=06
domain=06
time_step=6
output_dir="data/ecmwf/${start_date}_${run_hour}"


python3 -m scripts.get_ecmwf \
    --start_date ${start_date} \
    --run_hour ${run_hour} \
    --days_number ${days_number} \
    --domain ${domain} \
    --time_step ${time_step} \
    --outpath ${output_dir}
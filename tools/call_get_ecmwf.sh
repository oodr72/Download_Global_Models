#!/bin/bash
# Wrapper to call get_ecmwf.py with specific parameters
# Usage: ./call_get_ecmwf.sh [start_date] [run_hour] [days_number] [domain]

start_date=${1:-20250805}
run_hour=${2:-12}
days_number=${3:-1}
domain=${4:-atlantic}
time_step=6
output_dir="data/ecmwf/${start_date}_${run_hour}"

python3 -m scripts.get_ecmwf \
    --start_date ${start_date} \
    --run_hour ${run_hour} \
    --days_number ${days_number} \
    --domain ${domain} \
    --time_step ${time_step} \
    --outpath ${output_dir}
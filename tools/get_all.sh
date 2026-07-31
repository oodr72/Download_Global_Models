#!/bin/bash

start_date=${start_date}:-$(date -u +"%Y%m%d")}

# Check if start_date contains non-digit characters and remove them
start_date=$(echo "$start_date" | tr -cd '[:digit:]')

# Run the Python script 
python3 -m scripts.get_ecmwf  --start_date ${start_date} 
python3 -m scripts.get_gfs    --start_date ${start_date}
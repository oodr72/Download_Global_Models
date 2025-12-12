#!/bin/bash

# Call the windy animator tool with specific parameters for wind animation
data_path=./data/copernicus/20251206/integrated_copernicus_20251206.nc

# Sea current animation parameters for copernicus
#------------------------------------------------
# data_path=./data/integrated/integrated_glorys_20251206.nc
# mode=streamlines
# output_gif=gifs/sea_current_streamlines.gif
# uvar=uo
# vvar=vo
# fps=18
#------------------------------------------------

# Wind animation parameters for copernicus
#------------------------------------------------
data_path=./data/integrated/integrated_noaa_20251206.nc
mode=particles
output_gif=gifs/wind_particles.gif
uvar=10u
vvar=10v
fps=18
#------------------------------------------------


# Call the windy animator tool with specified parameters
python3 tools/windy_animator.py \
  --nc $data_path \
  --mode $mode \
  --uvar $uvar --vvar $vvar \
  --out $output_gif \
  --fps $fps


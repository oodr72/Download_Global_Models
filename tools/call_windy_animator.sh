#!/bin/bash

# Call the windy animator tool with specific parameters for wind animation
#------------------------------------------------
date=20251206
project=copernicus
mode=currents_map # "scalar", "quiver", "particles", "streamlines", wave, currents_map
# variable=wind
# variable=wave_height
variable=sea_current
title="Wave Height [m]"
theme="dark-contrast" #  "dark", "dark-contrast", "paper"

#------------------------------------------------

# Define paths and output based on parameters
data_path=./data/${project}/${date}/integrated_${project}_${date}.nc
output_gif=figures/gifs/${date}/${variable}_${mode}_${project}_${date}.gif

# Sea current animation parameters
#------------------------------------------------
if [ "$variable" == "sea_current" ] && [ "$project" == "copernicus" ]; then
    uvar=uo; vvar=vo 
    fps=100
    title="Sea Surface Currents [m/s]"
fi
#------------------------------------------------

# Wind animation parameters
#------------------------------------------------
if [ "$variable" == "wind" ] && [ "$project" == "copernicus" ]; then
    uvar=10u; vvar=10v
    fps=18
    title="10m Wind Speed [m/s]"
fi
#------------------------------------------------


# Wave height animation parameters
#------------------------------------------------
if [ "$variable" == "wave_height" ] && [ "$project" == "copernicus" ]; then
    var=VHM0_WW; dirvar=VMDR_WW
    fps=3
    title="Significant Wave Height [m]"
fi
#------------------------------------------------

# Create output directory if it doesn't exist
if [ ! -d "$(dirname "$output_gif")" ]; then
  mkdir -p "$(dirname "$output_gif")"
fi

# Call the windy animator tool
if [ ! -f "$data_path" ]; then
  echo "Data file not found: $data_path"
  exit 1
fi

echo "Creating $variable animation for $project on $date..."

# Special case for currents_map mode
if [ "$mode" == "currents_map" ] && [ "$variable" == "sea_current" ]; then
python3 tools/windy_animator.py \
  --nc $data_path \
  --mode $mode \
  --theme $theme \
  --uvar $uvar --vvar $vvar \
  --lon-min -50 --lon-max -0 \
  --lat-min 0 --lat-max 80 \
  --discrete-colors 20 \
  --out $output_gif \
  --title $title \
  --fps 3 --stride 2 --density 15 --arrowsize 0.0
  exit
fi

# Call the windy animator tool for wind or sea current
if [ "$variable" == "wind" ] || [ "$variable" == "sea_current" ]; then
python3 tools/windy_animator.py \
  --nc $data_path \
  --mode $mode \
  --uvar $uvar --vvar $vvar \
  --out $output_gif \
  --fps $fps \
  --theme $theme \
  --lon-min -23 --lon-max -0 \
  --lat-min 25 --lat-max 45 \
  --streamlines-colored \
  --discrete-colors 12 \
  --title $title \
  --time-fontsize 9 \
  --title-fontsize 10
  exit
fi

if [ "$variable" == "wave_height" ]; then
python3 tools/windy_animator.py \
  --nc $data_path \
  --mode scalar \
  --var $var \
  --out $output_gif \
  --fps $fps \
  --upsample-factor 5 \
  --lon-min -30 --lon-max -0 \
  --lat-min 0 --lat-max 70 \
  --theme $theme \
  --discrete-colors 20 \
  --title $title \
  --time-fontsize 9 \
  --title-fontsize 10 
  exit
fi

if [ "$mode" == "wave" ]; then
python3 tools/windy_animator.py \
  --nc $data_path \
  --mode wave \
  --var VHM0_WW --dirvar VMDR_WW \
  --out $output_gif \
  --fps 6 --stride 6 --discrete-colors 10 \
  --title "Wind height (m) & direction" \
  --title-fontsize 10 \
  --time-fontsize 9
  exit
fi

echo "Animation saved to $output_gif"
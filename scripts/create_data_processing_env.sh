#!/usr/bin/env bash
# Script to create a Conda environment for CMEMS data processing

# Stop if any command fails
set -e

# Name of the environment
ENV_NAME="data_processing"

# Create the environment with Python 3.11 (you can change version if needed)
conda create -n "$ENV_NAME" python=3.12.2 -y

# Activate the environment
conda activate "$ENV_NAME"

# Install core libraries via conda-forge to ensure compatibility
conda install -c conda-forge \
    xarray \
    netCDF4 \
    numpy \
    pandas \
    cftime \
    dask \
    -y

# Optional: install plotting tools (useful for quick checks)
conda install -c conda-forge matplotlib -y

# Optional: install pip (in case you want to add more packages via pip)
conda install pip -y

echo "Conda environment '$ENV_NAME' is ready."
echo "To activate it later, run:"
echo "conda activate $ENV_NAME"

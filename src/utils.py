"""
Shared utilities for Download_Global_Models.

Centralized helpers used across multiple scripts:
- is_valid_netcdf(): Validate NetCDF file integrity
"""

import logging
from pathlib import Path
from typing import List, Optional

import netCDF4 as nc4

logger = logging.getLogger(__name__)


def is_valid_netcdf(
    file_path,
    expected_variables: Optional[List[str]] = None,
    min_size_kb: int = 100,
) -> bool:
    """
    Check if a NetCDF file exists and is not corrupt.

    Args:
        file_path: Path to the NetCDF file.
        expected_variables: List of expected variable names (optional).
        min_size_kb: Minimum file size in KB to be considered valid.

    Returns:
        True if the file passes all checks, False otherwise.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.debug("File does not exist: %s", file_path)
        return False

    # Check file size
    file_size_kb = file_path.stat().st_size / 1024
    if file_size_kb < min_size_kb:
        logger.warning(
            "File too small (%.1f KB < %d KB): %s", file_size_kb, min_size_kb, file_path
        )
        return False

    try:
        with nc4.Dataset(str(file_path), "r") as nc:
            # Check basic structure
            if not hasattr(nc, "dimensions") or not hasattr(nc, "variables"):
                logger.debug("File lacks basic NetCDF structure: %s", file_path)
                return False

            # Check if file has at least one data variable
            coord_names = {"time", "latitude", "longitude", "lat", "lon", "Longitude", "Latitude"}
            data_vars = [var for var in nc.variables if var not in coord_names]
            if not data_vars:
                logger.debug("No data variables found: %s", file_path)
                return False

            # Check expected variables if provided
            if expected_variables:
                missing = [v for v in expected_variables if v not in nc.variables]
                if missing:
                    logger.warning(
                        "Missing expected variables %s in %s", missing, file_path
                    )
                    return False

        return True

    except Exception as e:
        logger.error("Error reading NetCDF file %s: %s", file_path, e)
        return False

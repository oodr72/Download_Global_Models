"""
This script sets the Copernicus Marine credentials in the user's home directory.
If the credentials file already exists, it will not overwrite it.
Example usage:
    python3 -m tools.set_copernicusmarine_credentials
"""

import os
from pathlib import Path
import copernicusmarine
from src.files_functions import get_copernicus_key

# Check if credentials file exists before trying to overwrite
credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"

if not credentials_path.exists():
    user, key, _ = get_copernicus_key()
    copernicusmarine.login(username=user, password=key)
    print("Copernicus Marine credentials set")
else:
    # Use existing credentials without re-authenticating
    print("Using existing Copernicus Marine credentials")
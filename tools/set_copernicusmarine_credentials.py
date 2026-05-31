"""
This script sets the Copernicus Marine credentials in the user's home directory.
If the credentials file already exists, it will not overwrite it.
Example usage:
    python3 -m tools.set_copernicusmarine_credentials
"""

from pathlib import Path

from src.files_functions import get_copernicus_key


def configure_credentials() -> None:
    credentials_path = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    if credentials_path.exists():
        print("Using existing Copernicus Marine credentials")
        return

    import copernicusmarine

    user, key, _loaded_env = get_copernicus_key()
    copernicusmarine.login(username=user, password=key)
    print("Copernicus Marine credentials set")


if __name__ == "__main__":
    configure_credentials()
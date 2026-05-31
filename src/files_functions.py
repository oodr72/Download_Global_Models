from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType


def _load_dotenv() -> bool:
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return False

    env_path = find_dotenv(".env", usecwd=True)
    if not env_path:
        return False
    return bool(load_dotenv(env_path))


def _get_required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise ValueError(f"Missing required environment variable. Tried: {', '.join(names)}")


def get_copernicus_key() -> tuple[str, str, bool]:
    """Return Copernicus Marine credentials as username, key and dotenv status."""
    loaded_env = _load_dotenv()
    user = _get_required_env("COPERNICUS_USER", "COPERNICUS_UID")
    key = _get_required_env("COPERNICUS_KEY", "COPERNICUS_API_TOKEN")
    return user, key, loaded_env


def get_ecmwf_key() -> tuple[str, str, str]:
    """Return ECMWF URL, key and email credentials."""
    _load_dotenv()
    url = _get_required_env("ECMWF_URL")
    key = _get_required_env("ECMWF_KEY")
    email = _get_required_env("ECMWF_EMAIL")
    return url, key, email


def load_config(config_file: str | Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("config", config_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load config file: {config_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
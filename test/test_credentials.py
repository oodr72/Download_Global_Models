import pytest

from src import files_functions


def test_get_copernicus_key_uses_primary_env_names(monkeypatch):
    monkeypatch.setattr(files_functions, "_load_dotenv", lambda: False)
    monkeypatch.setenv("COPERNICUS_USER", "user")
    monkeypatch.setenv("COPERNICUS_KEY", "key")

    assert files_functions.get_copernicus_key() == ("user", "key", False)


def test_get_copernicus_key_supports_aliases(monkeypatch):
    monkeypatch.setattr(files_functions, "_load_dotenv", lambda: True)
    monkeypatch.delenv("COPERNICUS_USER", raising=False)
    monkeypatch.delenv("COPERNICUS_KEY", raising=False)
    monkeypatch.setenv("COPERNICUS_UID", "alias-user")
    monkeypatch.setenv("COPERNICUS_API_TOKEN", "alias-key")

    assert files_functions.get_copernicus_key() == ("alias-user", "alias-key", True)


def test_get_copernicus_key_reports_missing_env(monkeypatch):
    monkeypatch.setattr(files_functions, "_load_dotenv", lambda: False)
    for name in ("COPERNICUS_USER", "COPERNICUS_KEY", "COPERNICUS_UID", "COPERNICUS_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="COPERNICUS_USER"):
        files_functions.get_copernicus_key()
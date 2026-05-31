import sys
from types import SimpleNamespace

from scripts import get_glorys, get_mfwave


def test_glorys_subset_call_uses_iso_dates(monkeypatch, tmp_path):
    calls = []
    fake_module = SimpleNamespace(subset=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "copernicusmarine", fake_module)

    get_glorys.download_cmems(
        start_date="20260531",
        end_date="20260601",
        coordinates={"lon_min": -90, "lon_max": 1, "lat_min": 9, "lat_max": 54},
        variables=["uo", "vo"],
        output_filename="glorys.nc",
        outpath=tmp_path,
    )

    assert calls[0]["start_datetime"] == "2026-05-31T00:00:00"
    assert calls[0]["end_datetime"] == "2026-06-01T23:00:00"
    assert calls[0]["variables"] == ["uo", "vo"]


def test_fmwam_subset_call_uses_list_variables_and_iso_dates(monkeypatch, tmp_path):
    calls = []
    fake_module = SimpleNamespace(subset=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "copernicusmarine", fake_module)

    get_mfwave.download_fmwam(
        start_date="20260531",
        end_date="20260601",
        coordinates={"lon_min": -90, "lon_max": 1, "lat_min": 9, "lat_max": 54},
        variables=["VHM0_WW", "VMDR_WW"],
        output_filename="fmwam.nc",
        outpath=tmp_path,
    )

    assert calls[0]["start_datetime"] == "2026-05-31T00:00:00"
    assert calls[0]["end_datetime"] == "2026-06-01T23:59:00"
    assert calls[0]["variables"] == ["VHM0_WW", "VMDR_WW"]
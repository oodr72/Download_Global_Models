import pytest

from src.model_utils import add_days_yyyymmdd, forecast_hours, get_domain, yyyymmdd_to_iso


def test_forecast_hours_respects_last_hour():
    assert forecast_hours(24, 6) == [0, 6, 12, 18, 24]
    assert forecast_hours(12, 5) == [0, 5, 10]
    assert forecast_hours(0, 6, include_zero=False) == []


def test_forecast_hours_validates_step():
    with pytest.raises(ValueError):
        forecast_hours(24, 0)


def test_date_helpers_use_compact_and_iso_formats():
    assert yyyymmdd_to_iso("20260531") == "2026-05-31"
    assert add_days_yyyymmdd("20260531", 1) == "20260601"


def test_get_domain_returns_float_copy():
    domain = get_domain({"demo": {"lon_min": "-1", "lon_max": 2, "lat_min": 3, "lat_max": 4}}, "demo")
    assert domain == {"lon_min": -1.0, "lon_max": 2.0, "lat_min": 3.0, "lat_max": 4.0}


def test_get_domain_reports_available_names():
    with pytest.raises(KeyError, match="demo"):
        get_domain({"demo": {"lon_min": 0, "lon_max": 1, "lat_min": 2, "lat_max": 3}}, "missing")
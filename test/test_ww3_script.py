from scripts import get_ww3_noaa


class _Response:
    status_code = 500
    content = b""


def test_ww3_honors_days_number_argument(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params, timeout))
        return _Response()

    monkeypatch.setattr(get_ww3_noaa.requests, "get", fake_get)

    get_ww3_noaa.download_and_convert_ww3(
        target_date="20260531",
        run_hour="06",
        days_number=0,
        time_step=6,
        coordinates={"lon_min": -90, "lon_max": 1, "lat_min": 9, "lat_max": 54},
        outpath=tmp_path,
    )

    assert len(calls) == 1
    assert calls[0][1]["file"] == "gefs.wave.t06z.mean.global.0p25.f000.grib2"
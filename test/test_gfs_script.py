from scripts import get_gfs


def test_build_url_contains_expected_gfs_parts():
    url = get_gfs.build_url("20260531", "00", "f006", "var_UGRD=on", -90, 1, 54, 9)

    assert "filter_gfs_0p25.pl" in url
    assert "file=gfs.t00z.pgrb2.0p25.f006" in url
    assert "var_UGRD=on" in url
    assert "dir=%2Fgfs.20260531%2F00%2Fatmos" in url


def test_main_downloads_analysis_and_bounded_forecasts(monkeypatch, tmp_path):
    calls = []

    def fake_download_file(url, dest, min_kb=100):
        calls.append((url, dest.name, min_kb))

    monkeypatch.setattr(get_gfs, "download_file", fake_download_file)

    get_gfs.main(
        date_str="20260531",
        init_str="00",
        timestep=6,
        last_hour=12,
        variables=["UGRD", "VGRD"],
        run_dir=tmp_path,
        domain_coords={"lon_min": -90, "lon_max": 1, "lat_min": 9, "lat_max": 54},
        fmt="grib2",
        keep_grib2=False,
        engine="cfgrib",
    )

    assert [name for _url, name, _min_kb in calls] == [
        "gfs_2026053100.grb2",
        "gfs_2026053106.grb2",
        "gfs_2026053112.grb2",
    ]
    assert all("var_UGRD=on&var_VGRD=on" in url for url, _name, _min_kb in calls)
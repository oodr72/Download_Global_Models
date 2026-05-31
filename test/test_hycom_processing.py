import pytest

from scripts import get_hycom


def test_hycom_process_subset_with_synthetic_dataset(tmp_path):
    xr = pytest.importorskip("xarray")
    np = pytest.importorskip("numpy")

    raw_path = tmp_path / "hycom_2026053100.nc"
    latitudes = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]])
    longitudes = np.array([[350.0, 355.0, 5.0], [350.0, 355.0, 5.0], [350.0, 355.0, 5.0]])
    values = np.arange(9).reshape(3, 3)
    ds = xr.Dataset(
        {"ssh": (("Y", "X"), values)},
        coords={
            "Latitude": (("Y", "X"), latitudes),
            "Longitude": (("Y", "X"), longitudes),
        },
    )
    ds.to_netcdf(raw_path)

    ok = get_hycom.process_and_save_subset(
        file_path=raw_path,
        output_folder=tmp_path,
        coordinates={"lon_min": -10, "lon_max": 10, "lat_min": 0, "lat_max": 2},
        log_path=tmp_path / "hycom.log",
    )

    assert ok is True
    assert (tmp_path / "subset_hycom_2026053100.nc").is_file()
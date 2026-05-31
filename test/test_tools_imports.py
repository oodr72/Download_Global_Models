import importlib


def test_tools_import_without_optional_runtime_dependencies():
    grib_to_netcdf = importlib.import_module("tools.grib_to_netcdf")
    get_domain_map = importlib.import_module("tools.get_domain_map")

    assert callable(grib_to_netcdf.convert_grib_to_netcdf)
    assert callable(get_domain_map.plot_domain)
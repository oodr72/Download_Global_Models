#!/usr/bin/env python3
"""
plot_domain.py  –  Quickly visualise a predefined geographic domain.

Usage examples
--------------
# Show the Mediterranean domain
python3 -m tools.get_domain_map --domain mediterranean

# Save a PNG of “atlantic” instead of displaying it
python3 -m tools.get_domain_map --domain atlantic --save
"""
from pathlib import Path
import argparse
from config import config

# --------------------------------------------------------------------------- #
# 1.  Import domain definitions                                               #
# --------------------------------------------------------------------------- #
# # The config file lives at  project_root/config/config.py
# import importlib.util

# CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.py"
# spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
# config = importlib.util.module_from_spec(spec)
# spec.loader.exec_module(config)          # type: ignore[attr-defined]

# DOMAINS: dict[str, dict[str, float]] = config.domains
DOMAINS = config.domains


def parse_arguments():
    parser = argparse.ArgumentParser(description="Plot a predefined geographic domain.")
    parser.add_argument(
        "--domain",
        "-d",
        default="caribbean",
        choices=list(DOMAINS.keys()),
        help="Domain name to draw (default: %(default)s)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the plot as domain_<name>.png instead of showing it.",
    )
    return parser.parse_args()


def plot_domain(domain_name, save=False):
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    bounds = DOMAINS[domain_name]
    lon_min, lon_max = bounds["lon_min"], bounds["lon_max"]
    lat_min, lat_max = bounds["lat_min"], bounds["lat_max"]

    proj = ccrs.PlateCarree()
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=proj)

    ax.coastlines(resolution="10m")
    ax.add_feature(cfeature.LAND, facecolor="#eeeeee")
    ax.add_feature(cfeature.OCEAN, facecolor="#aaccee")
    ax.gridlines(draw_labels=True, linewidth=0.5, alpha=0.5, linestyle="--")

    ax.plot(
        [lon_min, lon_max, lon_max, lon_min, lon_min],
        [lat_min, lat_min, lat_max, lat_max, lat_min],
        transform=proj,
        linestyle=":",
        linewidth=2,
        color="red",
    )

    ax.set_title(f"Domain: {domain_name}", fontsize=14)

    if save:
        out_dir = Path("figures")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"domain_{domain_name}.png"
        fig.savefig(out_file, dpi=150, bbox_inches="tight")
        print(f"Saved -> {out_file.resolve()}")
    else:
        plt.show()

    print("Done.")


if __name__ == "__main__":
    args = parse_arguments()
    plot_domain(args.domain, save=args.save)
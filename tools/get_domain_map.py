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

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

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
# --------------------------------------------------------------------------- #
# 2.  CLI                                                                     #
# --------------------------------------------------------------------------- #
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
args = parser.parse_args()

bounds = DOMAINS[args.domain]
lon_min, lon_max = bounds["lon_min"], bounds["lon_max"]
lat_min, lat_max = bounds["lat_min"], bounds["lat_max"]

# --------------------------------------------------------------------------- #
# 3.  Plot                                                                    #
# --------------------------------------------------------------------------- #
proj = ccrs.PlateCarree()
fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(1, 1, 1, projection=proj)
ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=proj)

# Add some context (coastlines, land/sea colouring)
ax.coastlines(resolution="10m")
ax.add_feature(cfeature.LAND, facecolor="#eeeeee")
ax.add_feature(cfeature.OCEAN, facecolor="#aaccee")
ax.gridlines(draw_labels=True, linewidth=0.5, alpha=0.5, linestyle="--")

# Highlight the bounding box
ax.plot(
    [lon_min, lon_max, lon_max, lon_min, lon_min],
    [lat_min, lat_min, lat_max, lat_max, lat_min],
    transform=proj,
    linestyle=":",
    linewidth=2,
    color="red",
)

title = f"Domain: {args.domain}"
ax.set_title(title, fontsize=14)

# --------------------------------------------------------------------------- #
# 4.  Output                                                                  #
# --------------------------------------------------------------------------- #
if args.save:
    out_file = Path(f"figures/domain_{args.domain}.png")
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    print(f"Saved → {out_file.resolve()}")
else:
    plt.show()

print("Done.")
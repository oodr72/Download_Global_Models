#!/usr/bin/env python3
"""
get_rtofs_ocean2d.py
--------------------
Download ocean surface variables with optional server-side subsetting.

Priority:
  1) If --bbox is provided, use it and try NCSS/OPeNDAP first, then fallback to
     full-file download + local crop.
  2) If --bbox is NOT provided but --domain is, use the domain's bbox with the same
     "server-side first → local-crop fallback" path.
  3) If neither --bbox nor --domain is given, download full RTOFS files only
     (no server-side subsetting, no merged per-time tiles).

Supported canonical variables:
  SST, SSS, SSH, UVEL, VVEL, SIC, SEAICE_THICKNESS

Examples:
python3 -m scripts.get_rtofs_ocean2d --start_date 20250809 --timestep 6 --last_hour 24

Requires: requests, xarray, netCDF4 (or h5netcdf), numpy
"""

from __future__ import annotations

import argparse
import sys
import timeit
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Dict, List, Tuple, Optional

import numpy as np
import requests
import xarray as xr

from config import config  # expects domains and optional NCSS settings

# ============================ CLI ========================================= #
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download RTOFS 2-D ocean variables with optional NCSS subsetting."
    )
    p.add_argument("--start_date", default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                   help='Initial date "yyyymmdd" (RTOFS/HYCOM directory date)')
    p.add_argument("--time", default="00", choices=["00", "06", "12", "18"],
                   help="Nominal cycle (for output folder naming only).")
    p.add_argument("--timestep", type=int, default=getattr(config, "RTOFS_timestep", 6),
                   help="Forecast-hour step, typically 3 or 6")
    p.add_argument("--last_hour", type=int, default=int(getattr(config, "RTOFS_last_hour", 24)),
                   help="Last forecast hour inclusive")
    p.add_argument("--variables", nargs="+",
                   default=getattr(config, "RTOFS_variables",
                                   ["SST", "SSS", "SSH", "UVEL", "VVEL", "SEAICE_THICKNESS"]),
                   help="Ocean vars: SST SSS SSH UVEL VVEL SIC SEAICE_THICKNESS")
    p.add_argument("--outpath", default=getattr(config, "RTOFS_output_directory", "data/rtofs"),
                   help="Root output folder")
    p.add_argument("--domain", default=getattr(config, "RTOFS_domain", None),
                   help="Key in config.domains. If provided (and --bbox not set), we use its bbox.")
    p.add_argument("--engine", choices=["netcdf4", "h5netcdf"], default="netcdf4",
                   help="xarray read/write engine")
    p.add_argument("--min_kb", type=int, default=100,
                   help="Skip download if file exists and larger than this (KB)")
    p.add_argument("--combine-into", choices=["per_time", "single_file"], default="per_time",
                   help="(Only used when cropping) Write one file per time or a single combined file")
    p.add_argument("--bbox", type=str, default=None,
                   help='Override bbox as "lon_min lon_max lat_min lat_max" (quotes required)')
    return p.parse_args()

# ============================ Constants & Maps ============================= #
# Canonical → RTOFS 2ds NetCDF variable names (native)
CANON_TO_RTOFS = {
    "SST": "sst",
    "SSS": "sss",
    "UVEL": "u_velocity",
    "VVEL": "v_velocity",
    "SSH": "ssh",
    "SIC": "ice_coverage",
    "SEAICE_THICKNESS": "ice_thickness",
}

# Canonical → HYCOM/GOFS NCSS variable names (surface)
CANON_TO_HYCOM = {
    "SST": "water_temp",
    "SSS": "salinity",
    "UVEL": "water_u",
    "VVEL": "water_v",
    "SSH": "surf_el",
    "SIC": "ice_conc",
    "SEAICE_THICKNESS": "ice_thickness",
}

# Which RTOFS family holds which canonical var
FAMILY_BY_CANON = {
    "SST": "prog",
    "SSS": "prog",
    "UVEL": "prog",
    "VVEL": "prog",
    "SSH": "diag",
    "SIC": "ice",
    "SEAICE_THICKNESS": "ice",
}

NOMADS_ROOT = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod"
AWS_ROOT    = "https://noaa-nws-rtofs-pds.s3.amazonaws.com"

# Optional NCSS datasets (plug your endpoints here if you have them)
RTOFS_NCSS_DATASET = getattr(config, "RTOFS_NCSS_DATASET", None)     # e.g., full NCSS URL if available
HYCOM_NCSS_BASE    = getattr(config, "HYCOM_NCSS_BASE", "https://ncss.hycom.org/thredds/ncss")
HYCOM_NCSS_DATASET = getattr(config, "HYCOM_NCSS_DATASET", "GLBy0.08/expt_93.0/analysis")

# ============================ Helpers ===================================== #
def parse_bbox(s: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not s:
        return None
    parts = s.split()
    if len(parts) != 4:
        raise ValueError("--bbox must have 4 numbers: 'lon_min lon_max lat_min lat_max'")
    return tuple(float(x) for x in parts)  # type: ignore

def make_run_folder(root: str | Path, date: str, init: str) -> Path:
    run_dir = Path(root).expanduser().resolve() / f"{date}{init}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def valid_time(date_str: str, init_str: str, fh: int) -> datetime:
    return datetime.strptime(date_str + init_str, "%Y%m%d%H") + timedelta(hours=fh)

def rtofs_family_filename(fhour: int, family: str) -> str:
    return f"rtofs_glo_2ds_f{fhour:03d}_{family}.nc"

def rtofs_url_candidates(date: str, filename: str) -> List[str]:
    path = f"rtofs.{date}/{filename}"
    return [f"{NOMADS_ROOT}/{path}", f"{AWS_ROOT}/{path}"]

def download_one(url: str, dest: Path, min_kb: int) -> bool:
    if dest.is_file() and dest.stat().st_size / 1024 > min_kb:
        print(f"✔ {dest.name} exists ({dest.stat().st_size/1024:.0f} KB) – skipping")
        return True
    try:
        r = requests.get(url, timeout=120)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            print(f"   Saved {dest}")
            return True
        print(f"   … HTTP {r.status_code} at {url}")
        return False
    except requests.RequestException as e:
        print(f"   … request error at {url}: {e}")
        return False

def subset_bbox_2d(ds: xr.Dataset,
                   bbox: Tuple[float, float, float, float],
                   lon_candidates=("Longitude", "lon", "longitude"),
                   lat_candidates=("Latitude", "lat", "latitude")) -> xr.Dataset:
    lon_name = next((n for n in lon_candidates if n in ds.variables or n in ds.coords), None)
    lat_name = next((n for n in lat_candidates if n in ds.variables or n in ds.coords), None)
    if lon_name is None or lat_name is None:
        print("⚠ could not find lon/lat; returning dataset unchanged")
        return ds
    lon2d = ds[lon_name].values
    lat2d = ds[lat_name].values

    lon_min, lon_max, lat_min, lat_max = bbox
    # handle 0..360 grids
    if lon2d.min() >= 0:
        lon_min = lon_min if lon_min >= 0 else lon_min + 360
        lon_max = lon_max if lon_max >= 0 else lon_max + 360
    mask = (lon2d >= lon_min) & (lon2d <= lon_max) & (lat2d >= lat_min) & (lat2d <= lat_max)
    if mask.sum() == 0:
        print("⚠ bbox mask empty; returning dataset unchanged")
        return ds
    dims = list(ds[lon_name].dims)
    if len(dims) != 2:
        print("⚠ lon/lat not 2-D; returning dataset unchanged")
        return ds
    yy, xx = np.where(mask)
    y_min, y_max = int(yy.min()), int(yy.max())
    x_min, x_max = int(xx.min()), int(xx.max())
    return ds.isel({dims[0]: slice(y_min, y_max + 1), dims[1]: slice(x_min, x_max + 1)})

def rename_vars(ds: xr.Dataset, mapping: Dict[str, str]) -> xr.Dataset:
    present = {v: mapping[v] for v in mapping if v in ds.variables}
    inv = {k: v for v, k in present.items()}  # dataset_name -> canonical
    return ds.rename(inv)

def build_output_name(valid_dt: datetime) -> str:
    return f"ocean2d_{valid_dt.strftime('%Y%m%d%H')}.nc"

# ---------------- NCSS builders ---------------- #
def build_hycom_ncss_url(time_dt: datetime,
                         bbox: Tuple[float, float, float, float],
                         vars_hycom: List[str]) -> str:
    base = f"{HYCOM_NCSS_BASE}/{HYCOM_NCSS_DATASET}"
    north = bbox[3]; south = bbox[2]; east = bbox[1]; west = bbox[0]
    params = (
        [("var", v) for v in vars_hycom] +
        [("north", f"{north}"),
         ("south", f"{south}"),
         ("east", f"{east}"),
         ("west", f"{west}"),
         ("time", time_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
         ("accept", "netcdf4"),
         ("addLatLon", "true")]
    )
    qs = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params)
    return f"{base}?{qs}"

def try_fetch_hycom_ncss(time_dt: datetime,
                         bbox: Tuple[float, float, float, float],
                         vars_canon: List[str],
                         dest: Path) -> bool:
    vars_hycom = [CANON_TO_HYCOM[v] for v in vars_canon if v in CANON_TO_HYCOM]
    if not vars_hycom:
        return False
    url = build_hycom_ncss_url(time_dt, bbox, vars_hycom)
    print(f"⇩  HYCOM NCSS → {dest.name}\n    {url}")
    try:
        r = requests.get(url, timeout=180)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            print(f"   Saved {dest}")
            return True
        print(f"   … HYCOM NCSS HTTP {r.status_code}")
        return False
    except requests.RequestException as e:
        print(f"   … HYCOM NCSS error: {e}")
        return False

def try_fetch_rtofs_ncss(time_dt: datetime,
                         bbox: Tuple[float, float, float, float],
                         vars_canon: List[str],
                         dest: Path) -> bool:
    dataset = getattr(config, "RTOFS_NCSS_DATASET", None)
    if not dataset:
        return False
    base = dataset if dataset.startswith("http") else f"{dataset}"
    vars_rtofs = [CANON_TO_RTOFS[v] for v in vars_canon if v in CANON_TO_RTOFS]
    north = bbox[3]; south = bbox[2]; east = bbox[1]; west = bbox[0]
    params = (
        [("var", v) for v in vars_rtofs] +
        [("north", f"{north}"),
         ("south", f"{south}"),
         ("east", f"{east}"),
         ("west", f"{west}"),
         ("time", time_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
         ("accept", "netcdf4"),
         ("addLatLon", "true")]
    )
    qs = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params)
    url = f"{base}?{qs}"
    print(f"⇩  RTOFS NCSS → {dest.name}\n    {url}")
    try:
        r = requests.get(url, timeout=180)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            print(f"   Saved {dest}")
            return True
        print(f"   … RTOFS NCSS HTTP {r.status_code}")
        return False
    except requests.RequestException as e:
        print(f"   … RTOFS NCSS error: {e}")
        return False

# ------------- RTOFS full-file download & local crop ---------------------- #
def fetch_rtofs_family(date: str, fh: int, family: str, run_dir: Path, min_kb: int) -> Optional[Path]:
    fname = rtofs_family_filename(fh, family)
    dest = run_dir / fname
    print(f"⇩  {fname}")
    for u in rtofs_url_candidates(date, fname):
        if download_one(u, dest, min_kb):
            return dest
    # Fallbacks for ICE naming variations seen on some mirrors
    if family == "ice":
        for alt in (f"rtofs_glo_2ds_f{fh:03d}_ice.nc",
                    f"rtofs_glo_3dz_f{fh:03d}_ice.nc"):
            dest_alt = run_dir / alt
            for u in rtofs_url_candidates(date, alt):
                if download_one(u, dest_alt, min_kb):
                    return dest_alt
    return None

def local_crop_and_merge_rtofs(family_files: List[Path],
                               vars_canon: List[str],
                               engine: str,
                               bbox: Optional[Tuple[float, float, float, float]],
                               valid_dt: datetime) -> Optional[xr.Dataset]:
    if not family_files:
        return None
    wanted_rtofs = [CANON_TO_RTOFS[v] for v in vars_canon if v in CANON_TO_RTOFS]
    pieces = []
    for f in family_files:
        try:
            ds = xr.open_dataset(f, engine=engine)
        except Exception as exc:
            print(f"⚠  failed to open {f.name}: {exc}")
            continue
        subset = subset_bbox_2d(ds, bbox) if bbox is not None else ds
        present = {v: subset[v] for v in wanted_rtofs if v in subset.variables}
        if not present:
            ds.close()
            continue
        rename_map = {v: k for k, v in CANON_TO_RTOFS.items() if v in present}
        sel = subset[list(present.keys())].rename(rename_map)
        ds.close()
        sel = sel.assign_coords(time=np.array([np.datetime64(valid_dt)]))
        for vn in list(sel.data_vars):
            if "time" not in sel[vn].coords:
                sel[vn] = sel[vn].expand_dims("time")
        pieces.append(sel)
    if not pieces:
        return None
    return xr.merge(pieces, compat="override")

# ============================ Main ======================================== #
def main(*,
         date_str: str,
         init_str: str,
         timestep: int,
         last_hour: int,
         variables: Iterable[str],
         run_dir: Path,
         domain_coords: Optional[dict],
         engine: str,
         min_kb: int,
         combine_into: str,
         bbox_cli: Optional[Tuple[float, float, float, float]]) -> None:

    # Resolve bbox & whether we intend server-side subsetting
    server_subset_intent = False
    bbox: Optional[Tuple[float, float, float, float]] = None

    if bbox_cli is not None:
        bbox = bbox_cli
        server_subset_intent = True
        print(f"→ Using --bbox {bbox} (server-side first)")
    elif domain_coords is not None:
        bbox = (domain_coords["lon_min"], domain_coords["lon_max"],
                domain_coords["lat_min"], domain_coords["lat_max"])
        server_subset_intent = True
        print(f"→ Using domain bbox {bbox} from config.domains (server-side first)")
    else:
        print("→ No --bbox and no --domain: will download full RTOFS files (no server-side subsetting)")

    vars_canon = [v.upper() for v in variables]
    out_list = []

    for fh in range(0, last_hour + 1, timestep):
        vdt = valid_time(date_str, init_str, fh)
        out_path = run_dir / build_output_name(vdt)

        print(f"\n=== FH {fh:03d} → valid {vdt:%Y-%m-%d %H:%MZ} =========================")

        ds_final: Optional[xr.Dataset] = None

        if server_subset_intent and bbox is not None:
            # (A1) RTOFS NCSS/OPeNDAP (if configured)
            tmp_nc = run_dir / f"_tmp_rtofs_ncss_{vdt:%Y%m%d%H}.nc"
            got = False
            if RTOFS_NCSS_DATASET:
                if try_fetch_rtofs_ncss(vdt, bbox, vars_canon, tmp_nc):
                    try:
                        ds = xr.open_dataset(tmp_nc, engine=engine)
                        rename_map = {CANON_TO_RTOFS[k]: k for k in vars_canon if k in CANON_TO_RTOFS}
                        ds = rename_vars(ds, rename_map)
                        ds_final = ds
                        got = True
                    except Exception as exc:
                        print(f"⚠  failed to open RTOFS NCSS file: {exc}")
                    finally:
                        tmp_nc.unlink(missing_ok=True)

            # (A2) HYCOM NCSS
            if not got:
                tmp_nc = run_dir / f"_tmp_hycom_ncss_{vdt:%Y%m%d%H}.nc"
                if try_fetch_hycom_ncss(vdt, bbox, vars_canon, tmp_nc):
                    try:
                        ds = xr.open_dataset(tmp_nc, engine=engine)
                        rename_map = {CANON_TO_HYCOM[k]: k for k in vars_canon if k in CANON_TO_HYCOM}
                        ds = rename_vars(ds, rename_map)
                        ds_final = ds
                        got = True
                    except Exception as exc:
                        print(f"⚠  failed to open HYCOM NCSS file: {exc}")
                    finally:
                        tmp_nc.unlink(missing_ok=True)

            # (B) Fallback: full files + local crop/merge
            if not got:
                families_needed = sorted({FAMILY_BY_CANON[v] for v in vars_canon if v in FAMILY_BY_CANON})
                family_files: List[Path] = []
                for fam in families_needed:
                    local = fetch_rtofs_family(date_str, fh, fam, run_dir, min_kb)
                    if local:
                        family_files.append(local)
                    else:
                        print(f"⚠  missing RTOFS {fam} for fh={fh}")
                ds_final = local_crop_and_merge_rtofs(family_files, vars_canon, engine, bbox, vdt)

        else:
            # No bbox/domain path: full-file download only (no server-side subsetting, no merged tiles)
            families_needed = sorted({FAMILY_BY_CANON[v] for v in vars_canon if v in FAMILY_BY_CANON})
            got_any = False
            for fam in families_needed:
                path = fetch_rtofs_family(date_str, fh, fam, run_dir, min_kb)
                got_any = got_any or bool(path)
            if not got_any:
                print("⚠  nothing gathered for this FH; skipping")
            # continue to next FH (skip writing ocean2d_*.nc)
            if combine_into == "per_time":
                # In this mode without bbox/domain we don't create merged tiles.
                continue

        if ds_final is None:
            print("⚠  nothing gathered for this FH; skipping")
            continue

        if combine_into == "per_time":
            encoding = {vn: {"zlib": True, "complevel": 3} for vn in ds_final.data_vars}
            ds_final.to_netcdf(out_path, engine=engine, encoding=encoding)
            print(f"   NetCDF saved: {out_path}")
            ds_final.close()
        else:
            out_list.append(ds_final)

    if combine_into == "single_file" and out_list:
        big = xr.concat(out_list, dim="time")
        combined = run_dir / f"ocean2d_{date_str}{init_str}_fh{0:03d}-{last_hour:03d}.nc"
        encoding = {vn: {"zlib": True, "complevel": 3} for vn in big.data_vars}
        big.to_netcdf(combined, engine=engine, encoding=encoding)
        print(f"\n   Combined NetCDF saved: {combined}")

# ============================ Entrypoint =================================== #
if __name__ == "__main__":
    opts = parse_cli()

    # domain is optional now
    domain_coords = None
    if opts.domain:
        try:
            domain_coords = config.domains[opts.domain]
        except KeyError:
            print(f"⚠ Domain “{opts.domain}” not found in config.domains; continuing without it")
            domain_coords = None

    bbox_cli = parse_bbox(opts.bbox)

    run_folder = (Path(opts.outpath).expanduser().resolve() / f"{opts.start_date}{opts.time}")
    run_folder.mkdir(parents=True, exist_ok=True)

    print("\n=== PARAMETERS =====================================================")
    for k, v in vars(opts).items():
        print(f"{k:14s}: {v}")
    print(f"run_folder   : {run_folder}")
    if bbox_cli is not None:
        print(f"bbox_resolved: {bbox_cli}")
    elif domain_coords is not None:
        print(f"bbox_resolved: {(domain_coords['lon_min'], domain_coords['lon_max'], domain_coords['lat_min'], domain_coords['lat_max'])}")
    else:
        print("bbox_resolved: None (full files mode)")
    print("====================================================================\n")

    t0 = timeit.default_timer()

    main(
        date_str=opts.start_date,
        init_str=opts.time,
        timestep=opts.timestep,
        last_hour=opts.last_hour,
        variables=opts.variables,
        run_dir=run_folder,
        domain_coords=domain_coords,
        engine=opts.engine,
        min_kb=opts.min_kb,
        combine_into=opts.combine_into,
        bbox_cli=bbox_cli,
    )

    mins, secs = divmod(timeit.default_timer() - t0, 60)
    print(f"\n✓ Done in {int(mins)} min {secs:.1f} s")

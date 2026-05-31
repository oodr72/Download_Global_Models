from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping


Domain = Mapping[str, float]


def parse_yyyymmdd(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Expected YYYYMMDD.") from exc


def yyyymmdd_to_iso(value: str) -> str:
    return parse_yyyymmdd(value).strftime("%Y-%m-%d")


def add_days_yyyymmdd(value: str, days: int) -> str:
    if days < 0:
        raise ValueError("days must be greater than or equal to 0")
    return (parse_yyyymmdd(value) + timedelta(days=days)).strftime("%Y%m%d")


def forecast_hours(last_hour: int, time_step: int, *, include_zero: bool = True) -> list[int]:
    if time_step <= 0:
        raise ValueError("time_step must be greater than 0")
    if last_hour < 0:
        raise ValueError("last_hour must be greater than or equal to 0")

    first_hour = 0 if include_zero else time_step
    if first_hour > last_hour:
        return []
    return list(range(first_hour, last_hour + 1, time_step))


def get_domain(domains: Mapping[str, Domain], name: str) -> dict[str, float]:
    try:
        domain = domains[name]
    except KeyError as exc:
        available = ", ".join(sorted(domains))
        raise KeyError(f"Domain '{name}' not found. Available domains: {available}") from exc
    return {key: float(value) for key, value in domain.items()}


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def file_is_valid(path: str | Path, min_kb: int = 100) -> bool:
    candidate = Path(path)
    return candidate.is_file() and candidate.stat().st_size / 1024 >= min_kb


def remove_idx_files(grib_path: str | Path) -> list[Path]:
    grib = Path(grib_path)
    removed: list[Path] = []
    for idx_file in grib.parent.glob(f"{grib.name}*.idx"):
        idx_file.unlink(missing_ok=True)
        removed.append(idx_file)
    return removed
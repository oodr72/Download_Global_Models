# Bug Fix Log

## 2025-06-17 — Comprehensive Audit

### Critical Bugs Fixed
1. **config/config.py SyntaxError** — Missing comma in GLORYS_variables list
2. **config/config.py Silent overwrites** — GLORYS_variables, ECMWF_variables, RTOFS_variables were overwritten by reduced lists
3. **src/files_functions.py Function shadowing** — Duplicate `get_copernicus_key()` definitions
4. **scripts/get_glorys.py IndentationError** — Misaligned code after `else:` block
5. **scripts/files_Integrator_metocen_noaa.py Incomplete** — No main() function (~250 lines added)
6. **run/run_files_integrator_noaa.sh Wrong module** — Referenced non-existent module name
7. **tools/get_all.sh Shell syntax** — Extra `}` in parameter expansion
8. **tools/call_get_ecmwf.sh Bad defaults** — `domain=06` invalid, `${days_number}` unset

### New Files Created
- `.env.example` — Credentials template
- `src/utils.py` — Centralized is_valid_netcdf() utility
- `config/__init__.py`, `src/__init__.py`, `scripts/__init__.py`, `tools/__init__.py`
- Expanded `README.md` (2 lines → comprehensive operational guide)
- Expanded `.gitignore` (6 lines → comprehensive patterns)

### Items Still Pending (Non-Blocking)
- [ ] Centralize `is_valid_netcdf()` imports (utility created, not yet imported in all scripts)
- [ ] Clean up `temp/` directory (8 legacy files)
- [ ] Remove/rename duplicates (`get_mfwave1.py`, `get_ww3_noaa1.py`)
- [ ] Write comprehensive pytest tests
- [ ] Update hardcoded dates in shell scripts
- [ ] Pygrib path in get_ecmwf.py is O(n²) — needs vectorization
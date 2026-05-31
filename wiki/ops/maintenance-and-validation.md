---
Title: Maintenance And Validation
Updated: 2026-05-31
Sources: Local repository audit, 2026-05-31
Raw: [Repository Audit and Implementation Notes](../../raw/ops/2026-05-31-repo-audit.md)
---

# Maintenance And Validation

## Standard Validation

Run these checks after substantive code, docs, dependency, or customization changes:

```bash
python3 -m compileall config src scripts tools test
python3 -m pytest -q
python3 -m scripts.get_gfs --help
python3 -m scripts.get_ecmwf --help
python3 -m scripts.get_glorys --help
python3 -m scripts.get_mfwave --help
python3 -m scripts.get_hycom --help
python3 -m scripts.get_ww3_noaa --help
python3 -m tools.grib_to_netcdf --help
python3 -m tools.get_domain_map --help
```

## Live Download Policy

Default tests must not perform live downloads. Live checks should be opt-in, use temporary ignored output directories, and keep forecast windows minimal.

## Wiki Rule

Every substantive iteration must update the LLM wiki in the same pass using `.github/skills/llm-wiki.md`:

- ingest or update `raw/` source material
- update affected `wiki/` articles
- update `wiki/index.md`
- append to `wiki/log.md`

## See Also

- [Project Overview](../overview/project-overview.md)
- [Implementation 2026-05-31](implementation-2026-05-31.md)
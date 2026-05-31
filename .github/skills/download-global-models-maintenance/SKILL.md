---
name: download-global-models-maintenance
description: "Use when: auditing, refactoring, testing, documenting, or maintaining the Download_Global_Models repository, including model download scripts, mocked tests, requirements, credentials, docs, and LLM wiki updates."
---

# Download Global Models Maintenance

Use this skill for future maintenance passes in this repository.

## Workflow

1. Establish a baseline without live downloads:
   - `python3 -m compileall config src scripts tools test`
   - `python3 -m pytest -q`
   - `python3 -m scripts.<script> --help` for each operational script.
2. Protect secrets and data:
   - Do not read or print `.env`.
   - Keep downloaded data, GRIB, NetCDF, `.idx`, logs, and generated figures ignored unless the user explicitly asks to version a fixture.
3. Work script by script:
   - Keep CLIs import-safe.
   - Use mocks for provider APIs and HTTP requests in tests.
   - Gate live downloads behind explicit user approval or `RUN_LIVE_DOWNLOADS=1`.
4. Keep dependencies honest:
   - Update `requirements.txt` for runtime imports.
   - Update `requirements-dev.txt` for test and development tooling.
5. Update knowledge base and docs in the same pass:
   - Read `../llm-wiki.md` and follow its ingest/update protocol.
   - Update `raw/`, `wiki/`, `wiki/index.md`, and `wiki/log.md` after substantive changes.
   - Reconcile README/docs with actual scripts, configuration, validation, and dependency changes.

## Final Checks

- `python3 -m compileall config src scripts tools test`
- `python3 -m pytest -q`
- all script/tool `--help` commands
- wiki index/log and raw references present
- no secrets or large model artifacts in the diff
# Download_Global_Models Instructions

- Do not run live model downloads by default. Use mocked tests unless the user explicitly requests a live smoke test or sets `RUN_LIVE_DOWNLOADS=1`.
- Keep credentials out of source files and outputs. Do not read or print `.env` contents.
- After substantive changes to scripts, configuration, tests, dependencies, documentation, agents, or skills, update the LLM wiki using `.github/skills/llm-wiki.md` in the same pass.
- Keep README/docs, requirements, tests, `raw/`, `wiki/index.md`, and `wiki/log.md` aligned with operational changes.
- Prefer import-safe CLIs: `python3 -m <module> --help` should not require optional heavy runtime dependencies or credentials.
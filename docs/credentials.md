# Credentials

This repository should never store real credentials in source files, logs, tests, documentation, or wiki pages.

## Copernicus Marine

Create a local `.env` from `.env.example`:

```bash
cp .env.example .env
```

Required variables:

```bash
COPERNICUS_USER=<your-user>
COPERNICUS_KEY=<your-key>
```

Backward-compatible aliases are also supported:

```bash
COPERNICUS_UID=<your-user>
COPERNICUS_API_TOKEN=<your-key>
```

Configure the Copernicus Marine client credentials file:

```bash
python3 -m tools.set_copernicusmarine_credentials
```

The command is safe to import from tests and only logs in when executed as a script.

## ECMWF

The current ECMWF downloader uses public forecast URLs. Variables `ECMWF_URL`, `ECMWF_KEY`, and `ECMWF_EMAIL` remain supported by `src.files_functions.get_ecmwf_key()` for workflows that need authenticated ECMWF APIs.

## Git Hygiene

`.env` is ignored for future changes, but if a local clone already tracks `.env`, remove it from version control with care and rotate any exposed credentials according to the provider policy.
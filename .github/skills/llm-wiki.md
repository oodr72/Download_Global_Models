# LLM Wiki Workflow

This repository uses an LLM-driven wiki for knowledge management.

## Workflow

### 1. Ingest (`raw/`)
Drop source material into `raw/<topic>/`:
- Configuration files, scripts, analysis results
- Architecture decisions, error logs, run outputs
- Any new information about the codebase

### 2. Compile (`wiki/`)
Process `raw/` material into `wiki/<topic>/` articles:
- Clear, concise documentation
- Cross-references to related articles
- Code examples where relevant

### 3. Cascade Updates
After compiling:
- Update `wiki/index.md` with new/changed articles
- Append to `wiki/log.md` with dated entry

## Topic Map
- `overview/` — Project overview, architecture, model pipelines
- `pipeline/` — Download scripts, integration workflow
- `configuration/` — Config system, domains, credentials
- `ops/` — Setup, deployment, testing, troubleshooting

## Closeout Order
1. `raw/<topic>/` — ingest new material
2. `wiki/<topic>/` — update affected articles
3. `wiki/index.md` — update article index
4. `wiki/log.md` — append dated log entry

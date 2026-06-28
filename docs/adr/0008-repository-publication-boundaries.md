# ADR 0008: Repository Publication Boundaries

- **Status**: Accepted
- **Date**: 2026-06-26

## Context

VALENCE GRC is published as an open, professional repository on GitHub. Internal working artifacts — demo recordings, scratch notes, competitive roadmaps, local databases, and environment secrets — degrade trust, inflate clone size, and may leak sensitive or misleading information if committed.

Public repositories from enterprise GRC vendors (Vanta, Drata, Sprinto, etc.) present a curated surface: source code, compliance documentation, operational runbooks, and contributor guidelines — not internal planning decks or developer scratchpads.

## Decision

The following categories are **strictly banned** from the public repository. They must never be committed, pushed, or included in releases.

### 1. Demo and media artifacts

| Pattern | Reason |
|---------|--------|
| `*.mp4`, `*.mov`, `*.webm`, `*.avi`, `*.mkv` | Large binaries; marketing demos belong outside git |
| `*demo*.log`, `demo_record.log`, `advance_demo_record.log` | Local recording session output |
| `.demo_video_tmp/`, `.advance_demo_tmp/` | Ephemeral Playwright/ffmpeg workspaces |

### 2. Internal planning and research (not for external readers)

| Path | Reason |
|------|--------|
| `docs/PRODUCT_ROADMAP.md` | Competitive positioning and pricing strategy |
| `docs/LAUNCH_READINESS.md` | Internal go-to-market checklist |
| `annotated_file_structure.md` | Developer scratch notes |
| `research_synthesis_report.md` | Internal research synthesis |
| Root-level `ADR.md` | Superseded by `docs/adr/` (authoritative index) |

### 3. Secrets, credentials, and local runtime state

| Pattern | Reason |
|---------|--------|
| `.env`, `.env.local`, `.env.*` (except `*.example`) | Secrets and API keys |
| `data/demo_credentials.json` | Generated credential material |
| `*.db`, `valence.db` | Local SQLite databases |
| `.valence-api.pid` | Process lock files |

### 4. Generated and cache output

| Pattern | Reason |
|---------|--------|
| `output/` (except `.gitkeep`) | Generated PDFs, HTML, logs |
| `.coverage`, `htmlcov/` | Test coverage artifacts |
| `__pycache__/`, `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/` | Tooling caches |

## Enforcement

1. **`.gitignore`** — primary guard; all patterns above are listed explicitly.
2. **`scripts/verify_public_repo.sh`** — fails CI and local pre-push checks if banned paths are tracked or present in the index.
3. **`.github/banned-paths.txt`** — machine-readable manifest consumed by the verify script.
4. **Code review** — pull requests that add media, roadmaps, or local state are rejected.

## Rationale

- Keeps repository clone size small and professional.
- Prevents accidental exposure of strategy documents or credentials.
- Aligns public documentation with what auditors and contributors actually need: architecture (ADRs), compliance matrices, security policy, and runbooks.

## Consequences

- Demo videos are distributed via release assets, a trust center, or internal storage — not git history.
- Product roadmap and launch readiness remain in private issue trackers or internal wikis.
- Contributors run `./scripts/verify_public_repo.sh` before opening a pull request.
- Existing ADRs live under `docs/adr/`; the legacy root `ADR.md` is removed.

## What remains public (intentionally)

| Area | Examples |
|------|----------|
| Architecture | `docs/adr/` |
| Compliance | `docs/compliance/` |
| Operations | `RUNBOOK.md`, `SECURITY.md` |
| Application source | `src/`, `frontend/`, `rules/`, `tests/` |
| Infrastructure | `Dockerfile`, `docker-compose.yml`, `.github/workflows/` |
